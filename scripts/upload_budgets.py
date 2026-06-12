"""予実管理機能: 隊×月の予算データ (team_budgets) を CSV から BQ に MERGE する CLI ツール

使い方:
    python3 scripts/upload_budgets.py path/to/budgets.csv [--force] [--dry-run]

CSV フォーマット (UTF-8、ヘッダ必須):
    year,month,team,budget_amount,memo
    2026,5,ケアプランデータ連携システムを広め隊,1000000,本格運用開始
    2026,5,広報がんばり隊,500000,

オプション:
    --force      optimistic lock を無視して強制上書き (管理者操作前提)
    --dry-run    BQ に書き込まず、変更プレビューのみ表示

設計仕様: docs/specs/2026-06-10-team-budget-eval-design.md §8
"""

from __future__ import annotations

import argparse
import csv
import os
import sys
from collections import Counter
from dataclasses import dataclass

from google.cloud import bigquery

PROJECT = "monthly-pay-tax"
DATASET = "pay_reports"
TABLE = "team_budgets"
FULL_TABLE = f"`{PROJECT}.{DATASET}.{TABLE}`"


@dataclass
class BudgetRow:
    year: int
    month: int
    team: str
    budget_amount: int
    memo: str | None

    @property
    def key(self) -> tuple[int, int, str]:
        return (self.year, self.month, self.team)


def parse_csv(csv_path: str) -> list[BudgetRow]:
    """CSV を読み込み、validation 済み BudgetRow のリストを返す。

    Validation:
        - year は 2026 以上 2100 以下
        - month は 1-12
        - team は非空
        - budget_amount は 0 以上の整数
        - memo は任意 (空文字なら None)

    Raises:
        ValueError: CSV パースまたは validation 失敗
    """
    rows: list[BudgetRow] = []
    with open(csv_path, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        required_cols = {"year", "month", "team", "budget_amount"}
        actual_cols = set(reader.fieldnames or [])
        missing = required_cols - actual_cols
        if missing:
            raise ValueError(f"CSV ヘッダに必須列が不足: {sorted(missing)}")
        for line_no, raw in enumerate(reader, start=2):  # ヘッダを 1 行目とカウント
            try:
                year = int(raw["year"])
                month = int(raw["month"])
                team = (raw["team"] or "").strip()
                budget_amount = int(raw["budget_amount"])
                memo = (raw.get("memo") or "").strip() or None
            except (ValueError, KeyError, TypeError) as e:
                raise ValueError(f"行 {line_no}: フィールド値が不正: {e}")
            if not (2026 <= year <= 2100):
                raise ValueError(f"行 {line_no}: year 値域外 (2026-2100): {year}")
            if not (1 <= month <= 12):
                raise ValueError(f"行 {line_no}: month 値域外 (1-12): {month}")
            if not team:
                raise ValueError(f"行 {line_no}: team が空文字")
            if budget_amount < 0:
                raise ValueError(f"行 {line_no}: budget_amount が負値: {budget_amount}")
            rows.append(BudgetRow(year=year, month=month, team=team,
                                  budget_amount=budget_amount, memo=memo))
    return rows


def find_duplicates(rows: list[BudgetRow]) -> list[tuple[int, int, str]]:
    """CSV 内の (year, month, team) 重複キーを抽出。重複なしなら空リスト。"""
    counter = Counter(r.key for r in rows)
    return sorted(k for k, n in counter.items() if n > 1)


def fetch_hierarchy_teams(client: bigquery.Client) -> set[str]:
    """team_hierarchy テーブルから operating の activity_category 集合を取得 (PR-A)。

    Returns:
        operating 隊として登録されている activity_category の集合。
        空集合の場合は team_hierarchy が未投入の状態。
    """
    query = f"""
    SELECT DISTINCT activity_category
    FROM `{PROJECT}.{DATASET}.team_hierarchy`
    WHERE leader_team_type = 'operating'
    """
    return {row.activity_category for row in client.query(query).result()}


def validate_hierarchy_coverage(
    client: bigquery.Client,
    rows: list[BudgetRow],
    *,
    strict: bool = False,
) -> int:
    """CSV の team が team_hierarchy に存在するか確認 (PR-A、Codex セカンドオピニオン反映)。

    Codex 指摘: 「CSV upload で team_hierarchy に存在しない team を投入できてしまう」
    → 表示で除外できても、予算 only 行混入の原因になる。

    Args:
        client: BQ クライアント
        rows: parse 済み CSV 行
        strict: True なら未登録 team があったら exit 1、False なら warning のみ
    Returns:
        exit code (0 なら継続、1 なら strict モードで未登録あり)
    """
    hierarchy_teams = fetch_hierarchy_teams(client)
    if not hierarchy_teams:
        print(
            "WARN: team_hierarchy が空です。hierarchy coverage check はスキップします。",
            file=sys.stderr,
        )
        return 0
    csv_teams = {r.team for r in rows}
    unregistered = csv_teams - hierarchy_teams
    if not unregistered:
        return 0
    print(
        f"WARN: CSV の team のうち {len(unregistered)} 件が team_hierarchy に未登録です:",
        file=sys.stderr,
    )
    for t in sorted(unregistered):
        print(f"  - {t}", file=sys.stderr)
    print(
        "  → これらの予算行は v_team_budget_actuals (隊フィルタ後 VIEW) に出現しません。",
        file=sys.stderr,
    )
    print(
        "  → 隊として表示したい場合は scripts/upload_team_hierarchy.py で先に登録してください。",
        file=sys.stderr,
    )
    if strict:
        print(
            "ERROR: --strict-hierarchy 指定のため、未登録 team の存在で中止します。",
            file=sys.stderr,
        )
        return 1
    return 0


@dataclass
class PreviewResult:
    new_count: int
    update_count: int
    unchanged_count: int
    details: list[tuple[str, BudgetRow, dict | None]]  # ("new"|"update"|"unchanged", row, existing_dict|None)


def preview_changes(client: bigquery.Client, rows: list[BudgetRow]) -> PreviewResult:
    """既存 team_budgets と比較して、新規/更新/変更なしの件数とプレビューを返す。"""
    if not rows:
        return PreviewResult(0, 0, 0, [])
    keys_param = bigquery.ArrayQueryParameter(
        "keys", "STRUCT<year INT64, month INT64, team STRING>",
        [{"year": r.year, "month": r.month, "team": r.team} for r in rows],
    )
    query = f"""
    SELECT year, month, team, budget_amount, memo, version
    FROM {FULL_TABLE}
    WHERE STRUCT(year, month, team) IN UNNEST(@keys)
    """
    job = client.query(query, job_config=bigquery.QueryJobConfig(query_parameters=[keys_param]))
    existing_map: dict[tuple[int, int, str], dict] = {}
    for row in job.result():
        existing_map[(row.year, row.month, row.team)] = dict(row.items())

    new_count = update_count = unchanged_count = 0
    details = []
    for r in rows:
        existing = existing_map.get(r.key)
        if existing is None:
            new_count += 1
            details.append(("new", r, None))
        else:
            same_amount = int(existing["budget_amount"]) == r.budget_amount
            same_memo = (existing.get("memo") or None) == r.memo
            if same_amount and same_memo:
                unchanged_count += 1
                details.append(("unchanged", r, existing))
            else:
                update_count += 1
                details.append(("update", r, existing))
    return PreviewResult(new_count, update_count, unchanged_count, details)


def print_preview(preview: PreviewResult) -> None:
    print(f"  新規:     {preview.new_count} 件")
    print(f"  更新:     {preview.update_count} 件")
    print(f"  変更なし: {preview.unchanged_count} 件")
    if preview.update_count > 0:
        print("\n  --- 更新内容 (先頭 5 件) ---")
        update_details = [d for d in preview.details if d[0] == "update"][:5]
        for _, row, existing in update_details:
            print(f"  - {row.year}/{row.month:02d} {row.team}: "
                  f"¥{int(existing['budget_amount']):,} → ¥{row.budget_amount:,}")


MERGE_SQL_OPTIMISTIC = f"""
MERGE {FULL_TABLE} t
USING (SELECT @year AS year, @month AS month, @team AS team,
              @budget_amount AS budget_amount, @memo AS memo,
              @actor AS actor, CURRENT_TIMESTAMP() AS now) s
ON t.year = s.year AND t.month = s.month AND t.team = s.team
WHEN MATCHED AND t.version = @expected_version THEN
  UPDATE SET budget_amount = s.budget_amount, memo = s.memo,
             version = t.version + 1, updated_at = s.now, updated_by = s.actor
WHEN NOT MATCHED THEN
  INSERT (year, month, team, budget_amount, memo, version,
          created_at, created_by, updated_at, updated_by)
  VALUES (s.year, s.month, s.team, s.budget_amount, s.memo, 1,
          s.now, s.actor, s.now, s.actor);
"""

MERGE_SQL_FORCE = f"""
MERGE {FULL_TABLE} t
USING (SELECT @year AS year, @month AS month, @team AS team,
              @budget_amount AS budget_amount, @memo AS memo,
              @actor AS actor, CURRENT_TIMESTAMP() AS now) s
ON t.year = s.year AND t.month = s.month AND t.team = s.team
WHEN MATCHED THEN
  UPDATE SET budget_amount = s.budget_amount, memo = s.memo,
             version = t.version + 1, updated_at = s.now, updated_by = s.actor
WHEN NOT MATCHED THEN
  INSERT (year, month, team, budget_amount, memo, version,
          created_at, created_by, updated_at, updated_by)
  VALUES (s.year, s.month, s.team, s.budget_amount, s.memo, 1,
          s.now, s.actor, s.now, s.actor);
"""


def do_merge_single(client: bigquery.Client, row: BudgetRow, actor: str,
                    force: bool, expected_version: int | None = None) -> int:
    """単一行を MERGE。affected_rows を返す (0 なら lock 競合)。"""
    params = [
        bigquery.ScalarQueryParameter("year", "INT64", row.year),
        bigquery.ScalarQueryParameter("month", "INT64", row.month),
        bigquery.ScalarQueryParameter("team", "STRING", row.team),
        bigquery.ScalarQueryParameter("budget_amount", "NUMERIC", str(row.budget_amount)),
        bigquery.ScalarQueryParameter("memo", "STRING", row.memo),
        bigquery.ScalarQueryParameter("actor", "STRING", actor),
    ]
    if force:
        sql = MERGE_SQL_FORCE
    else:
        sql = MERGE_SQL_OPTIMISTIC
        params.append(
            bigquery.ScalarQueryParameter("expected_version", "INT64",
                                          expected_version if expected_version is not None else 1),
        )
    job = client.query(sql, job_config=bigquery.QueryJobConfig(query_parameters=params))
    job.result()  # 完了待ち
    return job.num_dml_affected_rows or 0


def merge_in_batches(client: bigquery.Client, rows: list[BudgetRow], actor: str,
                     force: bool, preview: PreviewResult) -> tuple[int, int, int, int]:
    """rows を 1 件ずつ MERGE。UNCHANGED 行はスキップ（version インクリメント回避）、
    affected_rows = 0 (lock 競合) も skipped に分類。

    Returns:
        (success_count, skipped_count, unchanged_count, failed_count)
    """
    existing_versions: dict[tuple[int, int, str], int] = {}
    unchanged_keys: set[tuple[int, int, str]] = set()
    for kind, r, existing in preview.details:
        if kind == "unchanged":
            unchanged_keys.add(r.key)
        if kind in ("update", "unchanged") and existing is not None:
            existing_versions[r.key] = int(existing.get("version", 1))
    success = skipped = unchanged = failed = 0
    for r in rows:
        if r.key in unchanged_keys:
            unchanged += 1
            continue  # 値が同じなら MERGE しない（version 無駄インクリメント回避）
        expected_version = existing_versions.get(r.key)
        try:
            affected = do_merge_single(client, r, actor, force, expected_version)
            if affected == 0:
                print(f"  SKIPPED (lock 競合): {r.year}/{r.month:02d} {r.team}",
                      file=sys.stderr)
                skipped += 1
            else:
                success += 1
        except Exception as e:
            print(f"  FAILED: {r.year}/{r.month:02d} {r.team}: {e}", file=sys.stderr)
            failed += 1
    return success, skipped, unchanged, failed


def resolve_actor() -> str:
    """gcloud 認証ユーザーから actor 文字列を構築。"""
    user_email = (
        os.environ.get("GIT_AUTHOR_EMAIL")
        or os.environ.get("GIT_COMMITTER_EMAIL")
        or os.environ.get("USER")
        or "unknown"
    )
    return f"script:upload_budgets:{user_email}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="予実管理: 隊×月予算 CSV を team_budgets テーブルに MERGE する",
    )
    parser.add_argument("csv_path", help="CSV ファイルパス (year,month,team,budget_amount,memo)")
    parser.add_argument("--force", action="store_true",
                        help="optimistic lock を無視して強制上書き")
    parser.add_argument("--dry-run", action="store_true",
                        help="BQ に書き込まず、変更プレビューのみ表示")
    parser.add_argument("--yes", action="store_true",
                        help="confirm prompt をスキップ (自動化用)")
    parser.add_argument("--strict-hierarchy", action="store_true",
                        help=("team が team_hierarchy に未登録なら exit 1 で中止 (PR-A)。"
                              "ただし team_hierarchy が空の場合は WARN のみで継続。"))
    parser.add_argument("--skip-hierarchy-check", action="store_true",
                        help="team_hierarchy coverage check を完全にスキップ (緊急投入時のみ)")
    args = parser.parse_args(argv)

    # CSV 読み込み + validation
    try:
        rows = parse_csv(args.csv_path)
    except (ValueError, FileNotFoundError) as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1
    if not rows:
        print("CSV にデータ行がありません")
        return 0

    duplicates = find_duplicates(rows)
    if duplicates:
        print(f"ERROR: CSV 内に重複キー: {duplicates}", file=sys.stderr)
        return 1

    actor = resolve_actor()
    print(f"=== {len(rows)} 件を team_budgets に MERGE {'(dry-run)' if args.dry_run else ''} ===")
    print(f"actor: {actor}")

    # team_hierarchy coverage 確認 (PR-A)
    client = bigquery.Client(project=PROJECT)
    if not args.skip_hierarchy_check:
        rc = validate_hierarchy_coverage(client, rows, strict=args.strict_hierarchy)
        if rc != 0:
            return rc

    # プレビュー
    preview = preview_changes(client, rows)
    print_preview(preview)

    if args.dry_run:
        return 0

    if not args.yes:
        confirm = input("\n実行しますか? [y/N]: ")
        if confirm.lower() != "y":
            print("中止しました")
            return 1

    # MERGE 実行
    success, skipped, unchanged, failed = merge_in_batches(client, rows, actor, args.force, preview)
    print(f"\n=== 完了: 成功 {success} 件 / 変更なしスキップ {unchanged} 件 / "
          f"lock競合スキップ {skipped} 件 / 失敗 {failed} 件 ===")
    if failed > 0 or (skipped > 0 and not args.force):
        if skipped > 0:
            print("ヒント: --force で lock 競合を強制上書きできます", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
