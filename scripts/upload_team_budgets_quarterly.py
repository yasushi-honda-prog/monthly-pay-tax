"""予実管理機能 PR-E: 四半期 × 統括隊 × カテゴリの予算 (team_budgets_quarterly) を CSV から BQ に MERGE。

使い方:
    # long 形式 (システム用、自動判別)
    python3 scripts/upload_team_budgets_quarterly.py path/to/long.csv

    # matrix 形式 (画像通りの人間用) + fiscal_year/quarter 必須
    python3 scripts/upload_team_budgets_quarterly.py path/to/matrix.csv \\
        --fiscal-year 2026 --fiscal-quarter 3

CSV フォーマット:
    [long 形式]: fiscal_year,fiscal_quarter,leader_team,expense_category,budget_amount,memo
        2026,3,シロロ+ゆずるん統括隊,タダメン業務委託費,5289363,Q3 仮予算

    [matrix 形式]:
        ,タダメン業務委託費,旅費交通費,消耗品費,通信運搬費,広告宣伝費,自由に使える10万円,共通費
        シロロ+ゆずるん統括隊,5289363,200000,...,...,...,100000,300000
        ヤスス+ヒデデン統括隊,3770728,...,...,...,...,...,...

オプション:
    --fiscal-year       matrix 形式時に必須 (long 形式では無視)
    --fiscal-quarter    matrix 形式時に必須 (1-4、long 形式では無視)
    --expected-total    投入合計の検算値 (例: 23457444)。不一致でも warn のみで継続。
    --force             optimistic lock を無視して強制上書き
    --dry-run           BQ に書き込まず、変更プレビューのみ表示
    --yes               confirm prompt をスキップ
    --no-validate-categories  expense_categories マスタ照合をスキップ (debug 用、本番では使わない)

設計仕様: docs/specs/2026-06-10-team-budget-eval-design.md §Phase 2
踏襲元: scripts/upload_budgets.py (PR-A)
Codex Medium-7 (matrix/long 両受け) + Medium-6 (typo 防止) 反映済み。
"""

from __future__ import annotations

import argparse
import csv
import os
import re
import sys
from collections import Counter
from dataclasses import dataclass
from decimal import Decimal

from google.cloud import bigquery

PROJECT = "monthly-pay-tax"
DATASET = "pay_reports"
TABLE = "team_budgets_quarterly"
FULL_TABLE = f"`{PROJECT}.{DATASET}.{TABLE}`"
EXPENSE_CATEGORIES_TABLE = f"`{PROJECT}.{DATASET}.expense_categories`"

LONG_REQUIRED_COLS = {"fiscal_year", "fiscal_quarter", "leader_team", "expense_category", "budget_amount"}


@dataclass
class QuarterlyBudgetRow:
    fiscal_year: int
    fiscal_quarter: int
    leader_team: str
    expense_category: str
    budget_amount: int
    memo: str | None

    @property
    def key(self) -> tuple[int, int, str, str]:
        return (self.fiscal_year, self.fiscal_quarter, self.leader_team, self.expense_category)


def detect_format(csv_path: str) -> str:
    """CSV ヘッダから 'long' or 'matrix' を判別。"""
    with open(csv_path, encoding="utf-8") as f:
        reader = csv.reader(f)
        try:
            header = next(reader)
        except StopIteration:
            raise ValueError("CSV が空です")
    cols = {c.strip() for c in header}
    if "fiscal_year" in cols:
        return "long"
    return "matrix"


def parse_long_csv(csv_path: str) -> list[QuarterlyBudgetRow]:
    rows: list[QuarterlyBudgetRow] = []
    with open(csv_path, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        actual_cols = set(reader.fieldnames or [])
        missing = LONG_REQUIRED_COLS - actual_cols
        if missing:
            raise ValueError(f"long CSV ヘッダに必須列が不足: {sorted(missing)}")
        for line_no, raw in enumerate(reader, start=2):
            try:
                fy = int(raw["fiscal_year"])
                fq = int(raw["fiscal_quarter"])
                lt = (raw["leader_team"] or "").strip()
                ec = (raw["expense_category"] or "").strip()
                amt = int(raw["budget_amount"])
                memo = (raw.get("memo") or "").strip() or None
            except (ValueError, KeyError, TypeError) as e:
                raise ValueError(f"行 {line_no}: フィールド値が不正: {e}")
            _validate_row(line_no, fy, fq, lt, ec, amt)
            rows.append(QuarterlyBudgetRow(fy, fq, lt, ec, amt, memo))
    return rows


def parse_matrix_csv(csv_path: str, fiscal_year: int, fiscal_quarter: int
                     ) -> list[QuarterlyBudgetRow]:
    """matrix CSV を long に展開する。

    Matrix 形式の前提:
        - ヘッダ行: 1 列目空 (or 'leader_team' 等), 2 列目以降が expense_category
        - データ行: 1 列目が leader_team, 2 列目以降が予算金額 (空セルは 0)
        - '計' / 'total' / 'sum' 行 (1 列目がこれら) は検算用としてスキップ
    """
    if not (2026 <= fiscal_year <= 2100):
        raise ValueError(f"fiscal_year 値域外 (2026-2100): {fiscal_year}")
    if not (1 <= fiscal_quarter <= 4):
        raise ValueError(f"fiscal_quarter 値域外 (1-4): {fiscal_quarter}")

    # 検算用の集計行 (人間が CSV を編集するときに残しがちな行) を skip
    # Evaluator 指摘: 本田さんが Excel で頻用する「総計」「小計」も含める
    SKIP_LEADER_LABELS = {"計", "合計", "総計", "小計", "total", "sum", "subtotal", ""}
    rows: list[QuarterlyBudgetRow] = []
    with open(csv_path, encoding="utf-8") as f:
        reader = csv.reader(f)
        try:
            header = next(reader)
        except StopIteration:
            raise ValueError("matrix CSV が空です")
        if len(header) < 2:
            raise ValueError("matrix CSV のヘッダ列数が不足 (>=2 必要)")
        expected_cols = len(header)
        # ヘッダ 2 列目以降が expense_category
        expense_categories = [c.strip() for c in header[1:]]
        if not all(expense_categories):
            raise ValueError("matrix CSV ヘッダの expense_category 列に空文字を含む")

        for line_no, raw in enumerate(reader, start=2):
            if not raw or all(not c.strip() for c in raw):
                continue  # 完全空行スキップ
            leader_team = (raw[0] or "").strip()
            if leader_team.lower() in SKIP_LEADER_LABELS:
                continue
            # Codex M4: 列数超過は CSV ずれの可能性が高いので明示的に error
            if len(raw) > expected_cols:
                raise ValueError(
                    f"行 {line_no}: 列数 {len(raw)} がヘッダ列数 {expected_cols} を超過 "
                    f"(CSV ずれの可能性)"
                )
            if len(raw) < expected_cols:
                raw = raw + [""] * (expected_cols - len(raw))
            for col_idx, ec in enumerate(expense_categories, start=1):
                raw_amt = (raw[col_idx] or "").strip()
                # 空セル / '-' / '—' (em dash) は「未指定」として skip。
                # 予算を 0 に戻したい場合は明示的に "0" を記載する運用。
                if raw_amt in {"", "-", "—"}:
                    continue
                # 半角コンマ "," / 全角コンマ "，" / 半角空白を除去
                cleaned = re.sub(r"[,，\s]", "", raw_amt)
                try:
                    amt = int(cleaned)
                except ValueError:
                    raise ValueError(
                        f"行 {line_no} 列 '{ec}': 数値変換不能: {raw_amt!r}"
                    )
                _validate_row(line_no, fiscal_year, fiscal_quarter, leader_team, ec, amt)
                rows.append(QuarterlyBudgetRow(
                    fiscal_year=fiscal_year,
                    fiscal_quarter=fiscal_quarter,
                    leader_team=leader_team,
                    expense_category=ec,
                    budget_amount=amt,
                    memo=None,
                ))
    return rows


def _validate_row(line_no: int, fy: int, fq: int, lt: str, ec: str, amt: int) -> None:
    if not (2026 <= fy <= 2100):
        raise ValueError(f"行 {line_no}: fiscal_year 値域外 (2026-2100): {fy}")
    if not (1 <= fq <= 4):
        raise ValueError(f"行 {line_no}: fiscal_quarter 値域外 (1-4): {fq}")
    if not lt:
        raise ValueError(f"行 {line_no}: leader_team が空文字")
    if not ec:
        raise ValueError(f"行 {line_no}: expense_category が空文字")
    if amt < 0:
        raise ValueError(f"行 {line_no}: budget_amount が負値: {amt}")


def parse_csv(csv_path: str, fiscal_year: int | None,
              fiscal_quarter: int | None) -> tuple[str, list[QuarterlyBudgetRow]]:
    """CSV 形式を判別して parse。(format_name, rows) を返す。"""
    fmt = detect_format(csv_path)
    if fmt == "long":
        return "long", parse_long_csv(csv_path)
    # matrix
    if fiscal_year is None or fiscal_quarter is None:
        raise ValueError(
            "matrix CSV では --fiscal-year と --fiscal-quarter が必須"
        )
    return "matrix", parse_matrix_csv(csv_path, fiscal_year, fiscal_quarter)


def find_duplicates(rows: list[QuarterlyBudgetRow]) -> list[tuple[int, int, str, str]]:
    counter = Counter(r.key for r in rows)
    return sorted(k for k, n in counter.items() if n > 1)


def fetch_expense_categories(client: bigquery.Client) -> set[str]:
    """expense_categories マスタから登録済みカテゴリ名を取得。"""
    job = client.query(f"SELECT expense_category FROM {EXPENSE_CATEGORIES_TABLE}")
    return {row.expense_category for row in job.result()}


def validate_expense_categories(rows: list[QuarterlyBudgetRow],
                                 known_categories: set[str]) -> list[str]:
    """rows の expense_category が known に含まれているか検証。未知のものを返す。"""
    csv_categories = {r.expense_category for r in rows}
    return sorted(csv_categories - known_categories)


@dataclass
class PreviewResult:
    new_count: int
    update_count: int
    unchanged_count: int
    details: list[tuple[str, QuarterlyBudgetRow, dict | None]]


def preview_changes(client: bigquery.Client,
                    rows: list[QuarterlyBudgetRow]) -> PreviewResult:
    if not rows:
        return PreviewResult(0, 0, 0, [])
    keys_param = bigquery.ArrayQueryParameter(
        "keys",
        "STRUCT<fiscal_year INT64, fiscal_quarter INT64, leader_team STRING, expense_category STRING>",
        [{"fiscal_year": r.fiscal_year, "fiscal_quarter": r.fiscal_quarter,
          "leader_team": r.leader_team, "expense_category": r.expense_category} for r in rows],
    )
    query = f"""
    SELECT fiscal_year, fiscal_quarter, leader_team, expense_category,
           budget_amount, memo, version
    FROM {FULL_TABLE}
    WHERE STRUCT(fiscal_year, fiscal_quarter, leader_team, expense_category) IN UNNEST(@keys)
    """
    job = client.query(query, job_config=bigquery.QueryJobConfig(query_parameters=[keys_param]))
    existing_map: dict[tuple[int, int, str, str], dict] = {}
    for row in job.result():
        k = (row.fiscal_year, row.fiscal_quarter, row.leader_team, row.expense_category)
        existing_map[k] = dict(row.items())

    new_count = update_count = unchanged_count = 0
    details: list[tuple[str, QuarterlyBudgetRow, dict | None]] = []
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


def print_preview(preview: PreviewResult, total: int,
                  expected_total: int | None = None) -> bool:
    """Returns True if expected_total matches (or not specified), False on mismatch."""
    print(f"  新規:     {preview.new_count} 件")
    print(f"  更新:     {preview.update_count} 件")
    print(f"  変更なし: {preview.unchanged_count} 件")
    print(f"  合計予算: ¥{total:,}")
    total_ok = True
    if expected_total is not None:
        if total == expected_total:
            print(f"  ✓ 期待値 ¥{expected_total:,} と一致")
        else:
            diff = total - expected_total
            print(f"  ⚠ 期待値 ¥{expected_total:,} と差分: {diff:+,}",
                  file=sys.stderr)
            total_ok = False
    if preview.update_count > 0:
        print("\n  --- 更新内容 (先頭 5 件) ---")
        for _, row, existing in [d for d in preview.details if d[0] == "update"][:5]:
            print(f"  - FY{row.fiscal_year} Q{row.fiscal_quarter} "
                  f"{row.leader_team} / {row.expense_category}: "
                  f"¥{int(existing['budget_amount']):,} → ¥{row.budget_amount:,}")
    return total_ok


MERGE_SQL_OPTIMISTIC = f"""
MERGE {FULL_TABLE} t
USING (SELECT @fiscal_year AS fiscal_year, @fiscal_quarter AS fiscal_quarter,
              @leader_team AS leader_team, @expense_category AS expense_category,
              @budget_amount AS budget_amount, @memo AS memo,
              @actor AS actor, CURRENT_TIMESTAMP() AS now) s
ON t.fiscal_year = s.fiscal_year AND t.fiscal_quarter = s.fiscal_quarter
   AND t.leader_team = s.leader_team AND t.expense_category = s.expense_category
WHEN MATCHED AND t.version = @expected_version THEN
  UPDATE SET budget_amount = s.budget_amount, memo = s.memo,
             version = t.version + 1, updated_at = s.now, updated_by = s.actor
WHEN NOT MATCHED THEN
  INSERT (fiscal_year, fiscal_quarter, leader_team, expense_category,
          budget_amount, memo, version,
          created_at, created_by, updated_at, updated_by)
  VALUES (s.fiscal_year, s.fiscal_quarter, s.leader_team, s.expense_category,
          s.budget_amount, s.memo, 1,
          s.now, s.actor, s.now, s.actor);
"""

MERGE_SQL_FORCE = f"""
MERGE {FULL_TABLE} t
USING (SELECT @fiscal_year AS fiscal_year, @fiscal_quarter AS fiscal_quarter,
              @leader_team AS leader_team, @expense_category AS expense_category,
              @budget_amount AS budget_amount, @memo AS memo,
              @actor AS actor, CURRENT_TIMESTAMP() AS now) s
ON t.fiscal_year = s.fiscal_year AND t.fiscal_quarter = s.fiscal_quarter
   AND t.leader_team = s.leader_team AND t.expense_category = s.expense_category
WHEN MATCHED THEN
  UPDATE SET budget_amount = s.budget_amount, memo = s.memo,
             version = t.version + 1, updated_at = s.now, updated_by = s.actor
WHEN NOT MATCHED THEN
  INSERT (fiscal_year, fiscal_quarter, leader_team, expense_category,
          budget_amount, memo, version,
          created_at, created_by, updated_at, updated_by)
  VALUES (s.fiscal_year, s.fiscal_quarter, s.leader_team, s.expense_category,
          s.budget_amount, s.memo, 1,
          s.now, s.actor, s.now, s.actor);
"""


def do_merge_single(client: bigquery.Client, row: QuarterlyBudgetRow, actor: str,
                    force: bool, expected_version: int | None = None) -> int:
    params = [
        bigquery.ScalarQueryParameter("fiscal_year", "INT64", row.fiscal_year),
        bigquery.ScalarQueryParameter("fiscal_quarter", "INT64", row.fiscal_quarter),
        bigquery.ScalarQueryParameter("leader_team", "STRING", row.leader_team),
        bigquery.ScalarQueryParameter("expense_category", "STRING", row.expense_category),
        bigquery.ScalarQueryParameter("budget_amount", "NUMERIC", Decimal(row.budget_amount)),
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
    job.result()
    return job.num_dml_affected_rows or 0


def merge_in_batches(client: bigquery.Client, rows: list[QuarterlyBudgetRow], actor: str,
                     force: bool, preview: PreviewResult) -> tuple[int, int, int, int]:
    existing_versions: dict[tuple[int, int, str, str], int] = {}
    unchanged_keys: set[tuple[int, int, str, str]] = set()
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
                print(f"  SKIPPED (lock 競合): FY{r.fiscal_year} Q{r.fiscal_quarter} "
                      f"{r.leader_team} / {r.expense_category}", file=sys.stderr)
                skipped += 1
            else:
                success += 1
        except Exception as e:
            print(f"  FAILED: FY{r.fiscal_year} Q{r.fiscal_quarter} "
                  f"{r.leader_team} / {r.expense_category}: {e}", file=sys.stderr)
            failed += 1
    return success, skipped, unchanged, failed


def resolve_actor() -> str:
    user_email = (
        os.environ.get("GIT_AUTHOR_EMAIL")
        or os.environ.get("GIT_COMMITTER_EMAIL")
        or os.environ.get("USER")
        or "unknown"
    )
    return f"script:upload_team_budgets_quarterly:{user_email}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="予実管理 PR-E: 四半期×統括隊×カテゴリ予算 CSV を team_budgets_quarterly に MERGE",
    )
    parser.add_argument("csv_path", help="CSV ファイルパス (long or matrix 自動判別)")
    parser.add_argument("--fiscal-year", type=int, help="matrix 形式時に必須 (2026-2100)")
    parser.add_argument("--fiscal-quarter", type=int, help="matrix 形式時に必須 (1-4)")
    parser.add_argument("--expected-total", type=int,
                        help="投入合計の検算値 (例: 23457444)。不一致時はデフォルトで abort、"
                        "--allow-total-mismatch で継続可。")
    parser.add_argument("--allow-total-mismatch", action="store_true",
                        help="--expected-total 不一致でも warn のみで継続 (default は abort)")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--yes", action="store_true")
    parser.add_argument("--no-validate-categories", action="store_true",
                        help="expense_categories マスタ照合をスキップ (debug 用、本番では使わない)")
    args = parser.parse_args(argv)

    try:
        fmt, rows = parse_csv(args.csv_path, args.fiscal_year, args.fiscal_quarter)
    except (ValueError, FileNotFoundError) as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1
    if not rows:
        print("CSV にデータ行がありません")
        return 0

    duplicates = find_duplicates(rows)
    if duplicates:
        print(f"ERROR: CSV 内に重複キー (fiscal_year, fiscal_quarter, leader_team, expense_category): "
              f"{duplicates}", file=sys.stderr)
        return 1

    actor = resolve_actor()
    print(f"=== {len(rows)} 件を team_budgets_quarterly に MERGE "
          f"(形式: {fmt}) {'(dry-run)' if args.dry_run else ''} ===")
    print(f"actor: {actor}")

    client = bigquery.Client(project=PROJECT)

    # expense_category typo 検証 (Codex Medium-6 + 再 review M1: 取得失敗時 abort)
    if not args.no_validate_categories:
        try:
            known = fetch_expense_categories(client)
        except Exception as e:
            print(f"ERROR: expense_categories マスタ取得失敗: {e}", file=sys.stderr)
            print("  --no-validate-categories で照合スキップ可 (debug 用、本番非推奨)",
                  file=sys.stderr)
            return 1
        unknown = validate_expense_categories(rows, known)
        if unknown:
            print(f"ERROR: 未登録の expense_category: {unknown}", file=sys.stderr)
            print(f"  既知のカテゴリ: {sorted(known)}", file=sys.stderr)
            print("  ヒント: infra/bigquery/migrations/2026-06-11_quarterly_budgets.sql "
                  "の seed を更新し再実行する", file=sys.stderr)
            return 1

    preview = preview_changes(client, rows)
    total = sum(r.budget_amount for r in rows)
    total_ok = print_preview(preview, total, args.expected_total)

    # Codex H3 / Review CR-H3: --expected-total 不一致は default abort
    if not total_ok and not args.allow_total_mismatch:
        print("ERROR: --expected-total と差分があります。投入を中止しました。",
              file=sys.stderr)
        print("  本当に投入する場合は --allow-total-mismatch を付けて再実行してください。",
              file=sys.stderr)
        return 1

    if args.dry_run:
        return 0

    if not args.yes:
        confirm = input("\n実行しますか? [y/N]: ")
        if confirm.lower() != "y":
            print("中止しました")
            return 1

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
