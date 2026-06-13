"""統括隊×月予算 (leader_team_monthly_budgets) の DML repository (Issue #248)。

設計: docs/specs/2026-06-14-leader-team-monthly-budget.md §5.2

dashboard から admin 限定で leader_team_monthly_budgets を編集する UI 用のリポジトリ層。
team_budget_repo.py パターンを踏襲 (UPDATE-only + INSERT 分離 + 楽観ロック)。

Issue #248 固有の追加要素:
- BulkUpsertResult: 6×12=72 セル bulk edit 用の構造化結果 (Codex 指摘反映、PR #246 は
  単一セル編集寄りのため共通化せず repo 局所定義)
- seed_from_quarterly: team_budgets_quarterly÷3 で 1 fiscal_year を一括初期投入
- preview_seed_from_quarterly: seed 実行前のプレビュー (Codex M3 反映、二段階確認用)
- fetch_yearly: ROW_NUMBER で defensive に最新 1 件正規化 (Codex H2 反映、重複 row 防御)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from lib.constants import (
    LEADER_TEAM_MONTHLY_BUDGETS_TABLE,
    TEAM_BUDGETS_QUARTERLY_TABLE,
)


@dataclass(frozen=True)
class LeaderBudgetRow:
    """leader_team_monthly_budgets テーブルの 1 row。

    budget_amount は NUMERIC を **int** 化 (Codex L1: 円整数運用、精度差問題回避)。
    """

    fiscal_year: int
    month: int  # 1-12 (FY 内の暦月、Q1=11,12,1 / ... / Q4=8,9,10)
    leader_team: str
    budget_amount: int
    version: int
    created_at: datetime
    created_by: str
    updated_at: datetime
    updated_by: str


@dataclass(frozen=True)
class BulkUpsertResult:
    """6×12=72 セル bulk edit の結果集約 (Codex 指摘反映)。

    PR #246 の team_budget_repo は単一セル編集寄りで、bulk 操作は局所的に集計が必要。
    UI 側 (_persist_diff) は本構造体を受けて success / warning / error を表示する。
    """

    saved_count: int = 0
    deleted_count: int = 0
    conflicts: list[tuple[str, int]] = field(default_factory=list)
    """楽観ロック競合: [(leader_team, month), ...]"""
    errors: list[tuple[str, int, str]] = field(default_factory=list)
    """BQ 一時障害等の error: [(leader_team, month, error_msg), ...]"""


class UpsertConflict(Exception):
    """楽観ロック競合または INSERT 競合。

    - UPDATE WHERE version=expected_version で affected_rows=0
    - DELETE WHERE version=expected_version で affected_rows=0
    - INSERT 試行時に既存 row が同 PK で存在 (NOT EXISTS 句で 0 件挿入)

    UI 側は本例外をキャッチして該当セルだけ赤反転 + 他セルは保存継続。
    """


# --------- BQ SQL constants ---------

# Codex H2 反映: ROW_NUMBER で defensive に最新 1 件正規化。
# 重複 row 発生時 (migration バグ等) も UI が壊れない。
_FETCH_YEARLY_SQL = f"""
SELECT * EXCEPT(rn) FROM (
  SELECT fiscal_year, month, leader_team, budget_amount, version,
         created_at, created_by, updated_at, updated_by,
         ROW_NUMBER() OVER(
           PARTITION BY fiscal_year, month, leader_team
           ORDER BY updated_at DESC, version DESC
         ) AS rn
  FROM `{LEADER_TEAM_MONTHLY_BUDGETS_TABLE}`
  WHERE fiscal_year = @fiscal_year
) WHERE rn = 1
ORDER BY leader_team, month
"""

_FETCH_ONE_SQL = f"""
SELECT * EXCEPT(rn) FROM (
  SELECT fiscal_year, month, leader_team, budget_amount, version,
         created_at, created_by, updated_at, updated_by,
         ROW_NUMBER() OVER(
           PARTITION BY fiscal_year, month, leader_team
           ORDER BY updated_at DESC, version DESC
         ) AS rn
  FROM `{LEADER_TEAM_MONTHLY_BUDGETS_TABLE}`
  WHERE fiscal_year = @fiscal_year
    AND month = @month
    AND leader_team = @leader_team
) WHERE rn = 1
LIMIT 1
"""

_INSERT_SQL = f"""
INSERT INTO `{LEADER_TEAM_MONTHLY_BUDGETS_TABLE}`
  (fiscal_year, month, leader_team, budget_amount, version,
   created_at, created_by, updated_at, updated_by)
SELECT @fiscal_year, @month, @leader_team, @budget, 1,
       CURRENT_TIMESTAMP(), @actor, CURRENT_TIMESTAMP(), @actor
WHERE NOT EXISTS (
  SELECT 1 FROM `{LEADER_TEAM_MONTHLY_BUDGETS_TABLE}`
  WHERE fiscal_year = @fiscal_year
    AND month = @month
    AND leader_team = @leader_team
)
"""

_UPDATE_SQL = f"""
UPDATE `{LEADER_TEAM_MONTHLY_BUDGETS_TABLE}`
SET budget_amount = @budget,
    version = version + 1,
    updated_at = CURRENT_TIMESTAMP(),
    updated_by = @actor
WHERE fiscal_year = @fiscal_year
  AND month = @month
  AND leader_team = @leader_team
  AND version = @expected_version
"""

_DELETE_SQL = f"""
DELETE FROM `{LEADER_TEAM_MONTHLY_BUDGETS_TABLE}`
WHERE fiscal_year = @fiscal_year
  AND month = @month
  AND leader_team = @leader_team
  AND version = @expected_version
"""

_LOAD_ACTIVE_LEADER_TEAMS_SQL = f"""
SELECT DISTINCT leader_team
FROM `{LEADER_TEAM_MONTHLY_BUDGETS_TABLE}`
WHERE fiscal_year = @fiscal_year
  AND leader_team IS NOT NULL AND leader_team != ''
ORDER BY leader_team
"""

# seed_from_quarterly: fiscal_quarter→month 展開 + ÷3 を 1 SQL で計算
_SEED_FROM_QUARTERLY_PREVIEW_SQL = f"""
WITH expanded AS (
  SELECT
    q.fiscal_year,
    m AS month,
    q.leader_team,
    CAST(SAFE_DIVIDE(SUM(q.budget_amount), 3) AS NUMERIC) AS seed_amount
  FROM `{TEAM_BUDGETS_QUARTERLY_TABLE}` q
  CROSS JOIN UNNEST(
    CASE q.fiscal_quarter
      WHEN 1 THEN [11, 12, 1]
      WHEN 2 THEN [2, 3, 4]
      WHEN 3 THEN [5, 6, 7]
      WHEN 4 THEN [8, 9, 10]
    END
  ) AS m
  WHERE q.fiscal_year = @fiscal_year
  GROUP BY q.fiscal_year, q.leader_team, m
),
current_data AS (
  SELECT * EXCEPT(rn) FROM (
    SELECT fiscal_year, month, leader_team, budget_amount,
      ROW_NUMBER() OVER(
        PARTITION BY fiscal_year, month, leader_team
        ORDER BY updated_at DESC, version DESC
      ) AS rn
    FROM `{LEADER_TEAM_MONTHLY_BUDGETS_TABLE}`
    WHERE fiscal_year = @fiscal_year
  ) WHERE rn = 1
)
SELECT
  e.leader_team,
  e.month,
  -- code-review high CONFIRMED 反映: CAST AS INT64 は truncate のため
  -- ROUND() を先に通して四捨五入 (Codex R9: 'int(round())' 統一)。
  IFNULL(CAST(ROUND(c.budget_amount) AS INT64), 0) AS current_amount,
  CAST(ROUND(e.seed_amount) AS INT64) AS seed_amount
FROM expanded e
LEFT JOIN current_data c
  ON c.leader_team = e.leader_team AND c.month = e.month
ORDER BY e.leader_team, e.month
"""


# --------- 公開 API ---------


def _row_to_leader_budget(row) -> LeaderBudgetRow:
    """BQ Row → LeaderBudgetRow dataclass。NUMERIC は int 化 (Codex L1)。"""
    return LeaderBudgetRow(
        fiscal_year=int(row["fiscal_year"]),
        month=int(row["month"]),
        leader_team=str(row["leader_team"]),
        budget_amount=int(row["budget_amount"]),
        version=int(row["version"]),
        created_at=row["created_at"],
        created_by=str(row["created_by"]),
        updated_at=row["updated_at"],
        updated_by=str(row["updated_by"]),
    )


def fetch_yearly(client, fiscal_year: int) -> list[LeaderBudgetRow]:
    """指定 fiscal_year の全 row を返す (最大 72 行)。

    Defensive (Codex H2): ROW_NUMBER で重複 row 防御。leader_team ASC, month ASC ソート。
    """
    from google.cloud import bigquery

    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter("fiscal_year", "INT64", fiscal_year),
        ]
    )
    rows = client.query(_FETCH_YEARLY_SQL, job_config=job_config).result()
    return [_row_to_leader_budget(r) for r in rows]


def fetch_one(
    client, fiscal_year: int, month: int, leader_team: str
) -> Optional[LeaderBudgetRow]:
    """1 row 取得。存在しなければ None。

    UI が「編集対象セルだけ最新を再読込」する用途。
    """
    from google.cloud import bigquery

    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter("fiscal_year", "INT64", fiscal_year),
            bigquery.ScalarQueryParameter("month", "INT64", month),
            bigquery.ScalarQueryParameter("leader_team", "STRING", leader_team),
        ]
    )
    rows = list(client.query(_FETCH_ONE_SQL, job_config=job_config).result())
    if not rows:
        return None
    return _row_to_leader_budget(rows[0])


def load_active_leader_teams_for_budget_input(
    client, fiscal_year: int
) -> list[str]:
    """指定 fiscal_year に登場する全 leader_team を返す (Codex L2: rename 反映)。

    予算入力 UI の grid 行選択用。leader_team ASC ソート。
    """
    from google.cloud import bigquery

    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter("fiscal_year", "INT64", fiscal_year),
        ]
    )
    rows = client.query(
        _LOAD_ACTIVE_LEADER_TEAMS_SQL, job_config=job_config
    ).result()
    return [row["leader_team"] for row in rows]


def upsert(
    client,
    *,
    fiscal_year: int,
    month: int,
    leader_team: str,
    budget_amount: int,
    expected_version: Optional[int],
    actor_email: str,
) -> LeaderBudgetRow:
    """新規 INSERT または UPDATE (楽観ロック)。

    Args:
        expected_version: None → 新規 INSERT (既存行があれば UpsertConflict)
                          N    → UPDATE WHERE version=N (不一致なら UpsertConflict)
        budget_amount: NUMERIC NOT NULL のため None 不可、0 以上の int (円整数)
        actor_email: updated_by / created_by に記録

    Returns:
        DML 成功後に再 SELECT で取得した最新の LeaderBudgetRow

    Raises:
        UpsertConflict: 楽観ロック競合または INSERT 衝突
    """
    from google.cloud import bigquery

    if expected_version is None:
        params = [
            bigquery.ScalarQueryParameter("fiscal_year", "INT64", fiscal_year),
            bigquery.ScalarQueryParameter("month", "INT64", month),
            bigquery.ScalarQueryParameter("leader_team", "STRING", leader_team),
            bigquery.ScalarQueryParameter("budget", "NUMERIC", budget_amount),
            bigquery.ScalarQueryParameter("actor", "STRING", actor_email),
        ]
        sql = _INSERT_SQL
    else:
        params = [
            bigquery.ScalarQueryParameter("fiscal_year", "INT64", fiscal_year),
            bigquery.ScalarQueryParameter("month", "INT64", month),
            bigquery.ScalarQueryParameter("leader_team", "STRING", leader_team),
            bigquery.ScalarQueryParameter("budget", "NUMERIC", budget_amount),
            bigquery.ScalarQueryParameter("actor", "STRING", actor_email),
            bigquery.ScalarQueryParameter(
                "expected_version", "INT64", expected_version
            ),
        ]
        sql = _UPDATE_SQL

    job = client.query(sql, job_config=bigquery.QueryJobConfig(query_parameters=params))
    job.result()  # 完了待ち + 例外 raise
    affected = getattr(job, "num_dml_affected_rows", None)
    # PR #246 と同様: affected が None / 0 / その他 1 以外は conflict 扱い厳格化
    if affected != 1:
        msg = (
            "INSERT conflict (既存行が存在 or BQ unclear)"
            if expected_version is None
            else f"UPDATE conflict (version mismatch or row missing, expected v{expected_version})"
        )
        raise UpsertConflict(msg)

    # 成功後の最新値を再取得 (cache 経由しない direct read)
    result = fetch_one(client, fiscal_year, month, leader_team)
    if result is None:
        # 直後の SELECT で 0 件は異常 (別 admin が同時 DELETE 等)
        raise UpsertConflict(
            f"row disappeared after upsert ({leader_team}, {month})"
        )
    return result


def delete(
    client,
    *,
    fiscal_year: int,
    month: int,
    leader_team: str,
    expected_version: int,
    actor_email: str,  # 監査記録: 削除前の最終操作者は updated_by だが actor も診断ログ用に受け取る
) -> None:
    """1 row DELETE (楽観ロック)。

    Raises:
        UpsertConflict: version 不一致または既に削除済
    """
    from google.cloud import bigquery

    params = [
        bigquery.ScalarQueryParameter("fiscal_year", "INT64", fiscal_year),
        bigquery.ScalarQueryParameter("month", "INT64", month),
        bigquery.ScalarQueryParameter("leader_team", "STRING", leader_team),
        bigquery.ScalarQueryParameter("expected_version", "INT64", expected_version),
    ]
    job = client.query(
        _DELETE_SQL, job_config=bigquery.QueryJobConfig(query_parameters=params)
    )
    job.result()
    affected = getattr(job, "num_dml_affected_rows", None)
    if affected != 1:
        raise UpsertConflict(
            f"DELETE conflict (version mismatch or row missing, "
            f"expected v{expected_version}) for ({leader_team}, {month})"
        )


def preview_seed_from_quarterly(client, fiscal_year: int) -> dict:
    """seed 再投入の preview (Codex M3 反映、二段階確認用)。

    Returns:
        {
          'changed_count': int,    # 現在値と seed 値が異なるセル数
          'current_total': int,    # 現在の全 leader_team 合計
          'seed_total': int,       # seed 後の全 leader_team 合計
          'rows': [
            {'leader_team': str, 'month': int, 'current': int, 'seed': int, 'diff': int},
            ...
          ],
          'top_diffs': [...]       # 差額大きい上位 10 件
        }
    """
    from google.cloud import bigquery

    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter("fiscal_year", "INT64", fiscal_year),
        ]
    )
    rows = list(
        client.query(
            _SEED_FROM_QUARTERLY_PREVIEW_SQL, job_config=job_config
        ).result()
    )

    detail = []
    current_total = 0
    seed_total = 0
    changed_count = 0
    for row in rows:
        current = int(row["current_amount"])
        seed = int(row["seed_amount"])
        diff = seed - current
        detail.append({
            "leader_team": str(row["leader_team"]),
            "month": int(row["month"]),
            "current": current,
            "seed": seed,
            "diff": diff,
        })
        current_total += current
        seed_total += seed
        if diff != 0:
            changed_count += 1

    # 差額大きい上位 10 件 (abs(diff) DESC)
    top_diffs = sorted(detail, key=lambda r: abs(r["diff"]), reverse=True)[:10]

    return {
        "changed_count": changed_count,
        "current_total": current_total,
        "seed_total": seed_total,
        "rows": detail,
        "top_diffs": top_diffs,
    }


def seed_from_quarterly(
    client,
    fiscal_year: int,
    actor_email: str,
    overwrite: bool,
) -> BulkUpsertResult:
    """team_budgets_quarterly÷3 で 1 fiscal_year を一括 seed (AC14)。

    Args:
        overwrite:
          - False: 既存 row があれば ValueError raise (新規 fiscal_year 用の安全策)
          - True: 既存 row を全 UPDATE (version+1)、preview で本田様承認済の前提

    Returns:
        BulkUpsertResult: saved_count / conflicts / errors
    """
    preview = preview_seed_from_quarterly(client, fiscal_year)
    detail = preview["rows"]

    # 既存 row 件数を確認
    existing = fetch_yearly(client, fiscal_year)
    if existing and not overwrite:
        raise ValueError(
            f"fiscal_year={fiscal_year} は既に {len(existing)} 行投入済。"
            f"overwrite=True で再投入を承認してください。"
        )

    existing_map = {(r.leader_team, r.month): r for r in existing}
    # safe-refactor MEDIUM 反映: frozen dataclass の incremental 再生成を
    # mutable 集計 + ループ後 1 回生成に統一 (leader_budget_input._persist_diff と同 pattern)
    saved_count = 0
    conflicts: list[tuple[str, int]] = []
    errors: list[tuple[str, int, str]] = []

    for row in detail:
        lt = row["leader_team"]
        m = row["month"]
        seed_amount = row["seed"]
        existing_row = existing_map.get((lt, m))
        try:
            upsert(
                client,
                fiscal_year=fiscal_year, month=m, leader_team=lt,
                budget_amount=seed_amount,
                expected_version=existing_row.version if existing_row else None,
                actor_email=actor_email,
            )
            saved_count += 1
        except UpsertConflict:
            conflicts.append((lt, m))
        except Exception as e:
            errors.append((lt, m, str(e)))

    return BulkUpsertResult(
        saved_count=saved_count,
        deleted_count=0,
        conflicts=conflicts,
        errors=errors,
    )
