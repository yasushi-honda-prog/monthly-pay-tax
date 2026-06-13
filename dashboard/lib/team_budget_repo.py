"""隊×月予算 (team_budgets) の DML repository。

設計: docs/specs/2026-06-13-team-monthly-budget-input.md

dashboard から admin 限定で team_budgets を編集する UI 用のリポジトリ層。
既存 scripts/upload_budgets.py の MERGE ロジックとは別系統 (Codex 指摘 c:
upload_budgets.py 流用は新規 INSERT 競合で上書き発生のため不採用)。

team_hierarchy_repo.py パターンを踏襲し UPDATE-only + INSERT 分離。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass(frozen=True)
class TeamBudgetRow:
    """team_budgets テーブルの 1 row。

    UI ロード時 / upsert 成功時の戻り値として利用する。
    """

    year: int
    month: int
    team: str
    budget_amount: float
    memo: Optional[str]
    version: int
    updated_at: datetime
    updated_by: str


class UpsertConflict(Exception):
    """楽観ロック競合または INSERT 競合。

    - UPDATE WHERE version=expected_version で affected_rows=0
    - DELETE WHERE version=expected_version で affected_rows=0
    - INSERT 試行時に既存 row が同 PK で存在 (NOT EXISTS 句で 0 件挿入)

    UI 側は本例外をキャッチして「他の管理者が同時編集中の可能性があります」
    エラーを表示し、再読込ボタンで st.rerun() する。
    """


# --------- BQ table / SQL constants ---------

_PROJECT_DATASET_TABLE = "monthly-pay-tax.pay_reports.team_budgets"
_HIERARCHY_TABLE = "monthly-pay-tax.pay_reports.team_hierarchy"

_SELECT_BY_PK_SQL = f"""
SELECT year, month, team, budget_amount, memo, version, updated_at, updated_by
FROM `{_PROJECT_DATASET_TABLE}`
WHERE year = @year AND month = @month AND team = @team
LIMIT 1
"""

_INSERT_SQL = f"""
INSERT INTO `{_PROJECT_DATASET_TABLE}`
  (year, month, team, budget_amount, memo, version,
   created_at, created_by, updated_at, updated_by)
SELECT @year, @month, @team, @budget, @memo, 1,
       CURRENT_TIMESTAMP(), @actor, CURRENT_TIMESTAMP(), @actor
WHERE NOT EXISTS (
  SELECT 1 FROM `{_PROJECT_DATASET_TABLE}`
  WHERE year = @year AND month = @month AND team = @team
)
"""

_UPDATE_SQL = f"""
UPDATE `{_PROJECT_DATASET_TABLE}`
SET budget_amount = @budget,
    memo = @memo,
    version = version + 1,
    updated_at = CURRENT_TIMESTAMP(),
    updated_by = @actor
WHERE year = @year AND month = @month AND team = @team
  AND version = @expected_version
"""

_DELETE_SQL = f"""
DELETE FROM `{_PROJECT_DATASET_TABLE}`
WHERE year = @year AND month = @month AND team = @team
  AND version = @expected_version
"""

_OTHER_TEAM_BUDGETS_SUM_SQL = f"""
SELECT IFNULL(SUM(b.budget_amount), 0) AS total
FROM `{_PROJECT_DATASET_TABLE}` b
INNER JOIN `{_HIERARCHY_TABLE}` h
  ON b.team = h.activity_category
WHERE h.leader_team = @leader_team
  AND h.leader_team_type = 'operating'
  AND b.year = @year AND b.month = @month
  AND b.team != @exclude_team
"""


# --------- 公開 API ---------


def _row_to_team_budget(row) -> TeamBudgetRow:
    """BQ Row → TeamBudgetRow dataclass。NUMERIC は float 化。"""
    return TeamBudgetRow(
        year=int(row["year"]),
        month=int(row["month"]),
        team=str(row["team"]),
        budget_amount=float(row["budget_amount"]),
        memo=row["memo"],
        version=int(row["version"]),
        updated_at=row["updated_at"],
        updated_by=str(row["updated_by"]),
    )


def load_team_budget(client, year: int, month: int, team: str) -> Optional[TeamBudgetRow]:
    """1 row 取得。存在しなければ None。

    Codex 指摘 i: upsert 成功後の戻り値もこの関数経由で取得する (cache 経由しない
    direct read で最新値を保証)。
    """
    from google.cloud import bigquery

    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter("year", "INT64", year),
            bigquery.ScalarQueryParameter("month", "INT64", month),
            bigquery.ScalarQueryParameter("team", "STRING", team),
        ]
    )
    rows = list(client.query(_SELECT_BY_PK_SQL, job_config=job_config).result())
    if not rows:
        return None
    return _row_to_team_budget(rows[0])


def upsert_team_budget(
    client,
    *,
    year: int,
    month: int,
    team: str,
    budget_amount: float,
    memo: Optional[str],
    expected_version: Optional[int],
    actor: str,
) -> TeamBudgetRow:
    """新規 INSERT または UPDATE。

    Args:
        expected_version: None → 新規 INSERT (既存行があれば UpsertConflict)
                          N    → UPDATE WHERE version=N (不一致なら UpsertConflict)
        budget_amount: NUMERIC NOT NULL のため None 不可、0 以上
        memo: NULL 許容
        actor: updated_by / created_by に記録するメールアドレス等

    Returns:
        DML 成功後に再 SELECT で取得した最新の TeamBudgetRow

    Raises:
        UpsertConflict: 楽観ロック競合または INSERT 衝突
    """
    from google.cloud import bigquery

    if expected_version is None:
        params = [
            bigquery.ScalarQueryParameter("year", "INT64", year),
            bigquery.ScalarQueryParameter("month", "INT64", month),
            bigquery.ScalarQueryParameter("team", "STRING", team),
            bigquery.ScalarQueryParameter("budget", "NUMERIC", budget_amount),
            bigquery.ScalarQueryParameter("memo", "STRING", memo),
            bigquery.ScalarQueryParameter("actor", "STRING", actor),
        ]
        sql = _INSERT_SQL
    else:
        params = [
            bigquery.ScalarQueryParameter("year", "INT64", year),
            bigquery.ScalarQueryParameter("month", "INT64", month),
            bigquery.ScalarQueryParameter("team", "STRING", team),
            bigquery.ScalarQueryParameter("budget", "NUMERIC", budget_amount),
            bigquery.ScalarQueryParameter("memo", "STRING", memo),
            bigquery.ScalarQueryParameter("actor", "STRING", actor),
            bigquery.ScalarQueryParameter(
                "expected_version", "INT64", expected_version
            ),
        ]
        sql = _UPDATE_SQL

    job = client.query(sql, job_config=bigquery.QueryJobConfig(query_parameters=params))
    job.result()  # 完了待ち + 例外 raise
    affected = getattr(job, "num_dml_affected_rows", None)
    if affected == 0:
        msg = (
            "INSERT conflict (既存行が存在)"
            if expected_version is None
            else f"version mismatch (expected={expected_version})"
        )
        raise UpsertConflict(msg)

    # Codex 指摘 i: DML 後に直 SELECT で最新値を取得
    result = load_team_budget(client, year, month, team)
    if result is None:
        # 通常ありえない (INSERT/UPDATE 成功直後に row 不在)
        raise RuntimeError(
            f"team_budgets row not found after upsert: ({year}, {month}, {team})"
        )
    return result


def delete_team_budget(
    client,
    *,
    year: int,
    month: int,
    team: str,
    expected_version: int,
    actor: str,  # noqa: ARG001 - 監査用 reserved (現状は updated_by 不変、将来拡張用)
) -> None:
    """DELETE WHERE version=expected_version。conflict 時 UpsertConflict。

    Phase 1 は row DELETE (NUMERIC NOT NULL のため NULL 化不可)。
    soft delete (deleted_at/deleted_by 列) は follow-up PR。

    actor 引数は将来の audit log 用 reserved。現状の team_budgets schema には
    削除アクター列がないため未使用だが、UI 側 API の対称性のため受け取る。
    """
    from google.cloud import bigquery

    params = [
        bigquery.ScalarQueryParameter("year", "INT64", year),
        bigquery.ScalarQueryParameter("month", "INT64", month),
        bigquery.ScalarQueryParameter("team", "STRING", team),
        bigquery.ScalarQueryParameter("expected_version", "INT64", expected_version),
    ]
    job = client.query(
        _DELETE_SQL, job_config=bigquery.QueryJobConfig(query_parameters=params)
    )
    job.result()
    affected = getattr(job, "num_dml_affected_rows", None)
    if affected == 0:
        raise UpsertConflict(f"version mismatch on delete (expected={expected_version})")


def load_other_team_budgets_in_leader(
    client,
    *,
    year: int,
    month: int,
    leader_team: str,
    exclude_team: str,
) -> float:
    """超過判定用: 統括隊 leader_team 配下の operating 隊で exclude_team を除く
    同月の budget_amount 合計を返す (該当なしは 0)。

    Codex 指摘 f: 本関数は cache 不使用。UI 側で TTL 60s cache wrapper を別途用意し、
    保存直前は本関数を直接呼んで fresh fetch する。
    """
    from google.cloud import bigquery

    params = [
        bigquery.ScalarQueryParameter("year", "INT64", year),
        bigquery.ScalarQueryParameter("month", "INT64", month),
        bigquery.ScalarQueryParameter("leader_team", "STRING", leader_team),
        bigquery.ScalarQueryParameter("exclude_team", "STRING", exclude_team),
    ]
    rows = list(
        client.query(
            _OTHER_TEAM_BUDGETS_SUM_SQL,
            job_config=bigquery.QueryJobConfig(query_parameters=params),
        ).result()
    )
    if not rows:
        return 0.0
    total = rows[0]["total"]
    return float(total) if total is not None else 0.0
