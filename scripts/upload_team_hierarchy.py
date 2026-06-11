"""予実管理機能 PR-E: 隊 ↔ 統括隊の階層 (team_hierarchy) を CSV から BQ に MERGE する CLI ツール

使い方:
    python3 scripts/upload_team_hierarchy.py path/to/hierarchy.csv [--force] [--dry-run] [--check-coverage]

CSV フォーマット (UTF-8、ヘッダ必須):
    activity_category,leader_team,leader_team_type,note
    タダスク,シロロ+ゆずるん統括隊,operating,
    法人本部,共通,common,共通枠の virtual 統括隊

オプション:
    --force            optimistic lock を無視して強制上書き
    --dry-run          BQ に書き込まず、変更プレビューのみ表示
    --check-coverage   実行後に v_team_hierarchy_coverage を参照し UNMAPPED 隊を warn
    --yes              confirm prompt をスキップ (自動化用)

設計仕様: docs/specs/2026-06-10-team-budget-eval-design.md §Phase 2
踏襲元: scripts/upload_budgets.py (PR-A)
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
TABLE = "team_hierarchy"
FULL_TABLE = f"`{PROJECT}.{DATASET}.{TABLE}`"
COVERAGE_VIEW = f"`{PROJECT}.{DATASET}.v_team_hierarchy_coverage`"

VALID_LEADER_TEAM_TYPES = {"operating", "common"}


@dataclass
class HierarchyRow:
    activity_category: str
    leader_team: str
    leader_team_type: str
    note: str | None

    @property
    def key(self) -> str:
        return self.activity_category


def parse_csv(csv_path: str) -> list[HierarchyRow]:
    """CSV を読み込み、validation 済み HierarchyRow のリストを返す。

    Validation:
        - activity_category は非空
        - leader_team は非空
        - leader_team_type は 'operating' | 'common'
        - note は任意 (空文字なら None)

    Raises:
        ValueError: CSV パースまたは validation 失敗
    """
    rows: list[HierarchyRow] = []
    with open(csv_path, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        required_cols = {"activity_category", "leader_team", "leader_team_type"}
        actual_cols = set(reader.fieldnames or [])
        missing = required_cols - actual_cols
        if missing:
            raise ValueError(f"CSV ヘッダに必須列が不足: {sorted(missing)}")
        for line_no, raw in enumerate(reader, start=2):
            activity_category = (raw.get("activity_category") or "").strip()
            leader_team = (raw.get("leader_team") or "").strip()
            leader_team_type = (raw.get("leader_team_type") or "").strip()
            note = (raw.get("note") or "").strip() or None
            if not activity_category:
                raise ValueError(f"行 {line_no}: activity_category が空文字")
            if not leader_team:
                raise ValueError(f"行 {line_no}: leader_team が空文字")
            if leader_team_type not in VALID_LEADER_TEAM_TYPES:
                raise ValueError(
                    f"行 {line_no}: leader_team_type 値域外 "
                    f"('operating' or 'common'): {leader_team_type!r}"
                )
            rows.append(HierarchyRow(
                activity_category=activity_category,
                leader_team=leader_team,
                leader_team_type=leader_team_type,
                note=note,
            ))
    return rows


def find_duplicates(rows: list[HierarchyRow]) -> list[str]:
    """CSV 内の activity_category 重複キーを抽出。"""
    counter = Counter(r.key for r in rows)
    return sorted(k for k, n in counter.items() if n > 1)


@dataclass
class PreviewResult:
    new_count: int
    update_count: int
    unchanged_count: int
    details: list[tuple[str, HierarchyRow, dict | None]]


def preview_changes(client: bigquery.Client, rows: list[HierarchyRow]) -> PreviewResult:
    """既存 team_hierarchy と比較して新規/更新/変更なしを判定。"""
    if not rows:
        return PreviewResult(0, 0, 0, [])
    keys_param = bigquery.ArrayQueryParameter(
        "keys", "STRING", [r.activity_category for r in rows],
    )
    query = f"""
    SELECT activity_category, leader_team, leader_team_type, note, version
    FROM {FULL_TABLE}
    WHERE activity_category IN UNNEST(@keys)
    """
    job = client.query(query, job_config=bigquery.QueryJobConfig(query_parameters=[keys_param]))
    existing_map: dict[str, dict] = {}
    for row in job.result():
        existing_map[row.activity_category] = dict(row.items())

    new_count = update_count = unchanged_count = 0
    details: list[tuple[str, HierarchyRow, dict | None]] = []
    for r in rows:
        existing = existing_map.get(r.key)
        if existing is None:
            new_count += 1
            details.append(("new", r, None))
        else:
            same_leader = existing.get("leader_team") == r.leader_team
            same_type = existing.get("leader_team_type") == r.leader_team_type
            same_note = (existing.get("note") or None) == r.note
            if same_leader and same_type and same_note:
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
        for _, row, existing in [d for d in preview.details if d[0] == "update"][:5]:
            old = f"{existing.get('leader_team')}/{existing.get('leader_team_type')}"
            new = f"{row.leader_team}/{row.leader_team_type}"
            print(f"  - {row.activity_category}: {old} → {new}")


MERGE_SQL_OPTIMISTIC = f"""
MERGE {FULL_TABLE} t
USING (SELECT @activity_category AS activity_category, @leader_team AS leader_team,
              @leader_team_type AS leader_team_type, @note AS note,
              @actor AS actor, CURRENT_TIMESTAMP() AS now) s
ON t.activity_category = s.activity_category
WHEN MATCHED AND t.version = @expected_version THEN
  UPDATE SET leader_team = s.leader_team, leader_team_type = s.leader_team_type,
             note = s.note, version = t.version + 1,
             updated_at = s.now, updated_by = s.actor
WHEN NOT MATCHED THEN
  INSERT (activity_category, leader_team, leader_team_type, note, version,
          created_at, created_by, updated_at, updated_by)
  VALUES (s.activity_category, s.leader_team, s.leader_team_type, s.note, 1,
          s.now, s.actor, s.now, s.actor);
"""

MERGE_SQL_FORCE = f"""
MERGE {FULL_TABLE} t
USING (SELECT @activity_category AS activity_category, @leader_team AS leader_team,
              @leader_team_type AS leader_team_type, @note AS note,
              @actor AS actor, CURRENT_TIMESTAMP() AS now) s
ON t.activity_category = s.activity_category
WHEN MATCHED THEN
  UPDATE SET leader_team = s.leader_team, leader_team_type = s.leader_team_type,
             note = s.note, version = t.version + 1,
             updated_at = s.now, updated_by = s.actor
WHEN NOT MATCHED THEN
  INSERT (activity_category, leader_team, leader_team_type, note, version,
          created_at, created_by, updated_at, updated_by)
  VALUES (s.activity_category, s.leader_team, s.leader_team_type, s.note, 1,
          s.now, s.actor, s.now, s.actor);
"""


def do_merge_single(client: bigquery.Client, row: HierarchyRow, actor: str,
                    force: bool, expected_version: int | None = None) -> int:
    """単一行を MERGE。affected_rows を返す (0 なら lock 競合)。"""
    params = [
        bigquery.ScalarQueryParameter("activity_category", "STRING", row.activity_category),
        bigquery.ScalarQueryParameter("leader_team", "STRING", row.leader_team),
        bigquery.ScalarQueryParameter("leader_team_type", "STRING", row.leader_team_type),
        bigquery.ScalarQueryParameter("note", "STRING", row.note),
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
    job.result()
    return job.num_dml_affected_rows or 0


def merge_in_batches(client: bigquery.Client, rows: list[HierarchyRow], actor: str,
                     force: bool, preview: PreviewResult) -> tuple[int, int, int, int]:
    """rows を 1 件ずつ MERGE。UNCHANGED はスキップ。

    Returns:
        (success_count, skipped_count, unchanged_count, failed_count)
    """
    existing_versions: dict[str, int] = {}
    unchanged_keys: set[str] = set()
    for kind, r, existing in preview.details:
        if kind == "unchanged":
            unchanged_keys.add(r.key)
        if kind in ("update", "unchanged") and existing is not None:
            existing_versions[r.key] = int(existing.get("version", 1))
    success = skipped = unchanged = failed = 0
    for r in rows:
        if r.key in unchanged_keys:
            unchanged += 1
            continue
        expected_version = existing_versions.get(r.key)
        try:
            affected = do_merge_single(client, r, actor, force, expected_version)
            if affected == 0:
                print(f"  SKIPPED (lock 競合): {r.activity_category}", file=sys.stderr)
                skipped += 1
            else:
                success += 1
        except Exception as e:
            print(f"  FAILED: {r.activity_category}: {e}", file=sys.stderr)
            failed += 1
    return success, skipped, unchanged, failed


def check_coverage(client: bigquery.Client) -> tuple[int, int]:
    """v_team_hierarchy_coverage を参照し UNMAPPED / UNUSED 件数を返して表示。

    BQ クエリ失敗時は warn のみ出して (0, 0) を返す (補助情報なので main 結果を壊さない)。
    """
    query = f"""
    SELECT status, COUNT(*) AS cnt, ARRAY_AGG(activity_category ORDER BY activity_category LIMIT 10) AS sample
    FROM {COVERAGE_VIEW}
    WHERE status IN ('UNMAPPED', 'UNUSED')
    GROUP BY status
    """
    try:
        job = client.query(query)
        result = job.result()
    except Exception as e:
        print(f"  WARN: check_coverage 失敗 (main 結果には影響しません): {e}",
              file=sys.stderr)
        return 0, 0
    unmapped = unused = 0
    for row in result:
        if row.status == "UNMAPPED":
            unmapped = int(row.cnt)
            sample = list(row.sample or [])
            print(f"  ⚠ UNMAPPED (gyomu 出現するが hierarchy 未定義): {unmapped} 件",
                  file=sys.stderr)
            if sample:
                print(f"    例: {', '.join(sample)}", file=sys.stderr)
        elif row.status == "UNUSED":
            unused = int(row.cnt)
            sample = list(row.sample or [])
            print(f"  ℹ UNUSED (hierarchy 定義あるが gyomu 出現なし): {unused} 件",
                  file=sys.stderr)
            if sample:
                print(f"    例: {', '.join(sample)}", file=sys.stderr)
    return unmapped, unused


def resolve_actor() -> str:
    """gcloud 認証ユーザーから actor 文字列を構築。"""
    user_email = (
        os.environ.get("GIT_AUTHOR_EMAIL")
        or os.environ.get("GIT_COMMITTER_EMAIL")
        or os.environ.get("USER")
        or "unknown"
    )
    return f"script:upload_team_hierarchy:{user_email}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="予実管理 PR-E: 隊×統括隊階層 CSV を team_hierarchy に MERGE する",
    )
    parser.add_argument("csv_path",
                        help="CSV ファイルパス (activity_category,leader_team,leader_team_type,note)")
    parser.add_argument("--force", action="store_true",
                        help="optimistic lock を無視して強制上書き")
    parser.add_argument("--dry-run", action="store_true",
                        help="BQ に書き込まず、変更プレビューのみ表示")
    parser.add_argument("--check-coverage", action="store_true",
                        help="MERGE 後に UNMAPPED 隊を v_team_hierarchy_coverage で warn")
    parser.add_argument("--yes", action="store_true",
                        help="confirm prompt をスキップ (自動化用)")
    args = parser.parse_args(argv)

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
        print(f"ERROR: CSV 内に重複 activity_category: {duplicates}", file=sys.stderr)
        return 1

    actor = resolve_actor()
    print(f"=== {len(rows)} 件を team_hierarchy に MERGE {'(dry-run)' if args.dry_run else ''} ===")
    print(f"actor: {actor}")

    client = bigquery.Client(project=PROJECT)
    preview = preview_changes(client, rows)
    print_preview(preview)

    if args.dry_run:
        if args.check_coverage:
            print("\n--- v_team_hierarchy_coverage (dry-run なので現在の BQ 状態を参照) ---")
            check_coverage(client)
        return 0

    if not args.yes:
        confirm = input("\n実行しますか? [y/N]: ")
        if confirm.lower() != "y":
            print("中止しました")
            return 1

    success, skipped, unchanged, failed = merge_in_batches(client, rows, actor, args.force, preview)
    print(f"\n=== 完了: 成功 {success} 件 / 変更なしスキップ {unchanged} 件 / "
          f"lock競合スキップ {skipped} 件 / 失敗 {failed} 件 ===")

    if args.check_coverage:
        print("\n--- v_team_hierarchy_coverage ---")
        check_coverage(client)

    if failed > 0 or (skipped > 0 and not args.force):
        if skipped > 0:
            print("ヒント: --force で lock 競合を強制上書きできます", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
