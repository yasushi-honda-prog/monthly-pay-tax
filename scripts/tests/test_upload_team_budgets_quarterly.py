"""scripts/upload_team_budgets_quarterly.py の単体テスト。

カバー範囲:
- detect_format: long / matrix 判別
- parse_long_csv: 正常系 + validation エラー
- parse_matrix_csv: 正常系 + '計' 行スキップ + カンマ数値 + 空セル + fiscal_year/quarter 値域
- parse_csv: ディスパッチと matrix 時の必須 option チェック
- find_duplicates: 4-tuple PK 重複
- validate_expense_categories: typo 検出
- preview_changes: 新規/更新/変更なし判定
- do_merge_single: optimistic / force / lock 競合
- merge_in_batches: skipped / failed / unchanged
- resolve_actor: 優先順位
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import upload_team_budgets_quarterly as ubq  # noqa: E402


def _write_csv(tmp_path: Path, content: str, name: str = "budgets.csv") -> Path:
    p = tmp_path / name
    p.write_text(content, encoding="utf-8")
    return p


# --- detect_format ---


def test_detect_format_long(tmp_path):
    csv_path = _write_csv(tmp_path,
        "fiscal_year,fiscal_quarter,leader_team,expense_category,budget_amount,memo\n"
        "2026,3,シロロ統括隊,タダメン業務委託費,1000000,\n")
    assert ubq.detect_format(str(csv_path)) == "long"


def test_detect_format_matrix(tmp_path):
    csv_path = _write_csv(tmp_path,
        ",タダメン業務委託費,旅費交通費\n"
        "シロロ統括隊,1000000,200000\n")
    assert ubq.detect_format(str(csv_path)) == "matrix"


def test_detect_format_empty_raises(tmp_path):
    csv_path = _write_csv(tmp_path, "")
    with pytest.raises(ValueError, match="CSV が空"):
        ubq.detect_format(str(csv_path))


# --- parse_long_csv ---


def test_parse_long_happy_path(tmp_path):
    csv_path = _write_csv(tmp_path,
        "fiscal_year,fiscal_quarter,leader_team,expense_category,budget_amount,memo\n"
        "2026,3,シロロ統括隊,タダメン業務委託費,5289363,Q3 仮予算\n"
        "2026,3,ヤスス統括隊,タダメン業務委託費,3770728,\n")
    rows = ubq.parse_long_csv(str(csv_path))
    assert len(rows) == 2
    assert rows[0].fiscal_year == 2026
    assert rows[0].fiscal_quarter == 3
    assert rows[0].leader_team == "シロロ統括隊"
    assert rows[0].budget_amount == 5289363
    assert rows[0].memo == "Q3 仮予算"
    assert rows[1].memo is None


def test_parse_long_missing_header(tmp_path):
    csv_path = _write_csv(tmp_path,
        "fiscal_year,fiscal_quarter,leader_team\n2026,3,A\n")
    with pytest.raises(ValueError, match="long CSV ヘッダに必須列が不足"):
        ubq.parse_long_csv(str(csv_path))


def test_parse_long_invalid_fiscal_year(tmp_path):
    csv_path = _write_csv(tmp_path,
        "fiscal_year,fiscal_quarter,leader_team,expense_category,budget_amount,memo\n"
        "2020,3,A,B,1000,\n")
    with pytest.raises(ValueError, match="fiscal_year 値域外"):
        ubq.parse_long_csv(str(csv_path))


def test_parse_long_invalid_fiscal_quarter(tmp_path):
    csv_path = _write_csv(tmp_path,
        "fiscal_year,fiscal_quarter,leader_team,expense_category,budget_amount,memo\n"
        "2026,5,A,B,1000,\n")
    with pytest.raises(ValueError, match="fiscal_quarter 値域外"):
        ubq.parse_long_csv(str(csv_path))


def test_parse_long_negative_budget(tmp_path):
    csv_path = _write_csv(tmp_path,
        "fiscal_year,fiscal_quarter,leader_team,expense_category,budget_amount,memo\n"
        "2026,3,A,B,-100,\n")
    with pytest.raises(ValueError, match="budget_amount が負値"):
        ubq.parse_long_csv(str(csv_path))


# --- parse_matrix_csv ---


def test_parse_matrix_happy_path(tmp_path):
    csv_path = _write_csv(tmp_path,
        ",タダメン業務委託費,旅費交通費,共通費\n"
        "シロロ統括隊,5289363,200000,300000\n"
        "ヤスス統括隊,3770728,150000,300000\n")
    rows = ubq.parse_matrix_csv(str(csv_path), 2026, 3)
    assert len(rows) == 6  # 2 統括隊 × 3 カテゴリ
    # シロロ × タダメン業務委託費
    keyset = {r.key for r in rows}
    assert (2026, 3, "シロロ統括隊", "タダメン業務委託費") in keyset
    assert (2026, 3, "ヤスス統括隊", "共通費") in keyset
    sum_amt = sum(r.budget_amount for r in rows)
    assert sum_amt == 5289363 + 200000 + 300000 + 3770728 + 150000 + 300000


def test_parse_matrix_skip_total_row(tmp_path):
    """Excel で残しがちな集計行 (計 / 合計 / 総計 / 小計 / total / sum / subtotal) を skip。"""
    csv_path = _write_csv(tmp_path,
        ",タダメン業務委託費,旅費交通費\n"
        "シロロ統括隊,5289363,200000\n"
        "ヤスス統括隊,3770728,150000\n"
        "計,9060091,350000\n"
        "合計,9060091,350000\n"
        "総計,9060091,350000\n"
        "小計,9060091,350000\n"
        "Total,9060091,350000\n"
        "SUBTOTAL,9060091,350000\n")
    rows = ubq.parse_matrix_csv(str(csv_path), 2026, 3)
    assert len(rows) == 4  # シロロ / ヤスス × 2 カテゴリ
    leader_teams = {r.leader_team for r in rows}
    for label in {"計", "合計", "総計", "小計", "Total", "SUBTOTAL"}:
        assert label not in leader_teams


def test_parse_matrix_comma_in_numbers(tmp_path):
    """日本語表記の '5,289,363' を正しく int 変換する。"""
    csv_path = _write_csv(tmp_path,
        ",タダメン業務委託費\n"
        '"シロロ統括隊","5,289,363"\n')
    rows = ubq.parse_matrix_csv(str(csv_path), 2026, 3)
    assert len(rows) == 1
    assert rows[0].budget_amount == 5289363


def test_parse_matrix_fullwidth_comma_and_space(tmp_path):
    """全角コンマ '，' および半角空白を含む数値も正しく int 変換する (CR-H1 修正検証)。"""
    csv_path = _write_csv(tmp_path,
        ",タダメン業務委託費,旅費交通費\n"
        '"シロロ統括隊","5，289，363","1 000 000"\n')
    rows = ubq.parse_matrix_csv(str(csv_path), 2026, 3)
    by_cat = {r.expense_category: r.budget_amount for r in rows}
    assert by_cat["タダメン業務委託費"] == 5289363
    assert by_cat["旅費交通費"] == 1000000


def test_parse_matrix_column_overflow_error(tmp_path):
    """列数がヘッダを超過する行は CSV ずれの可能性として error (Codex M4 反映)。"""
    csv_path = _write_csv(tmp_path,
        ",タダメン業務委託費,旅費交通費\n"
        "シロロ統括隊,1000,2000,EXTRA_VALUE,EXTRA2\n")
    with pytest.raises(ValueError, match="列数 .* がヘッダ列数 .* を超過"):
        ubq.parse_matrix_csv(str(csv_path), 2026, 3)


def test_parse_matrix_empty_cells_skipped(tmp_path):
    csv_path = _write_csv(tmp_path,
        ",タダメン業務委託費,旅費交通費,共通費\n"
        "シロロ統括隊,5289363,,300000\n"
        "ヤスス統括隊,3770728,-,\n")
    rows = ubq.parse_matrix_csv(str(csv_path), 2026, 3)
    # 空セル と '-' はスキップ → 3 行 (シロロ業務 + シロロ共通 + ヤスス業務)
    assert len(rows) == 3


def test_parse_matrix_fiscal_year_out_of_range(tmp_path):
    csv_path = _write_csv(tmp_path,
        ",タダメン業務委託費\nシロロ統括隊,1000\n")
    with pytest.raises(ValueError, match="fiscal_year 値域外"):
        ubq.parse_matrix_csv(str(csv_path), 2020, 3)


def test_parse_matrix_fiscal_quarter_out_of_range(tmp_path):
    csv_path = _write_csv(tmp_path,
        ",タダメン業務委託費\nシロロ統括隊,1000\n")
    with pytest.raises(ValueError, match="fiscal_quarter 値域外"):
        ubq.parse_matrix_csv(str(csv_path), 2026, 5)


def test_parse_matrix_empty_category_header(tmp_path):
    csv_path = _write_csv(tmp_path,
        ",タダメン業務委託費,,共通費\n"
        "シロロ統括隊,1000,2000,3000\n")
    with pytest.raises(ValueError, match="ヘッダの expense_category 列に空文字"):
        ubq.parse_matrix_csv(str(csv_path), 2026, 3)


def test_parse_matrix_non_numeric_cell(tmp_path):
    csv_path = _write_csv(tmp_path,
        ",タダメン業務委託費\nシロロ統括隊,not_a_number\n")
    with pytest.raises(ValueError, match="数値変換不能"):
        ubq.parse_matrix_csv(str(csv_path), 2026, 3)


# --- parse_csv (dispatch) ---


def test_parse_csv_dispatches_to_long(tmp_path):
    csv_path = _write_csv(tmp_path,
        "fiscal_year,fiscal_quarter,leader_team,expense_category,budget_amount,memo\n"
        "2026,3,A,B,1000,\n")
    fmt, rows = ubq.parse_csv(str(csv_path), None, None)
    assert fmt == "long"
    assert len(rows) == 1


def test_parse_csv_matrix_requires_fiscal_args(tmp_path):
    csv_path = _write_csv(tmp_path,
        ",タダメン業務委託費\nシロロ統括隊,1000\n")
    with pytest.raises(ValueError, match="--fiscal-year"):
        ubq.parse_csv(str(csv_path), None, None)


def test_parse_csv_dispatches_to_matrix(tmp_path):
    csv_path = _write_csv(tmp_path,
        ",タダメン業務委託費\nシロロ統括隊,1000\n")
    fmt, rows = ubq.parse_csv(str(csv_path), 2026, 3)
    assert fmt == "matrix"
    assert len(rows) == 1


# --- find_duplicates ---


def test_find_duplicates_no_dup():
    rows = [
        ubq.QuarterlyBudgetRow(2026, 3, "A", "業務委託費", 100, None),
        ubq.QuarterlyBudgetRow(2026, 3, "B", "業務委託費", 200, None),
        ubq.QuarterlyBudgetRow(2026, 4, "A", "業務委託費", 300, None),
    ]
    assert ubq.find_duplicates(rows) == []


def test_find_duplicates_detects():
    rows = [
        ubq.QuarterlyBudgetRow(2026, 3, "A", "業務委託費", 100, None),
        ubq.QuarterlyBudgetRow(2026, 3, "A", "業務委託費", 999, None),  # dup
        ubq.QuarterlyBudgetRow(2026, 3, "A", "旅費交通費", 200, None),  # not dup
    ]
    dups = ubq.find_duplicates(rows)
    assert (2026, 3, "A", "業務委託費") in dups
    assert len(dups) == 1


# --- validate_expense_categories ---


def test_validate_expense_categories_all_known():
    rows = [
        ubq.QuarterlyBudgetRow(2026, 3, "A", "タダメン業務委託費", 100, None),
        ubq.QuarterlyBudgetRow(2026, 3, "A", "旅費交通費", 200, None),
    ]
    known = {"タダメン業務委託費", "旅費交通費", "共通費"}
    assert ubq.validate_expense_categories(rows, known) == []


def test_validate_expense_categories_detects_typo():
    rows = [
        ubq.QuarterlyBudgetRow(2026, 3, "A", "タダメン業務委託費", 100, None),
        ubq.QuarterlyBudgetRow(2026, 3, "A", "タダメンギョウムイタクヒ", 200, None),  # typo
    ]
    known = {"タダメン業務委託費", "旅費交通費"}
    unknown = ubq.validate_expense_categories(rows, known)
    assert "タダメンギョウムイタクヒ" in unknown


# --- preview_changes ---


def _mock_bq_with_existing(existing_rows: list[dict]) -> MagicMock:
    client = MagicMock()
    job = MagicMock()
    mock_rows = []
    for r in existing_rows:
        mr = MagicMock(items=lambda r=r: r.items())
        for k, v in r.items():
            setattr(mr, k, v)
        mock_rows.append(mr)
    job.result.return_value = iter(mock_rows)
    client.query.return_value = job
    return client


def test_preview_all_new():
    client = _mock_bq_with_existing([])
    rows = [ubq.QuarterlyBudgetRow(2026, 3, "A", "業務委託費", 100, None)]
    preview = ubq.preview_changes(client, rows)
    assert preview.new_count == 1
    assert preview.update_count == 0


def test_preview_unchanged():
    existing = [{"fiscal_year": 2026, "fiscal_quarter": 3, "leader_team": "A",
                 "expense_category": "業務委託費",
                 "budget_amount": 100, "memo": None, "version": 1}]
    client = _mock_bq_with_existing(existing)
    rows = [ubq.QuarterlyBudgetRow(2026, 3, "A", "業務委託費", 100, None)]
    preview = ubq.preview_changes(client, rows)
    assert preview.unchanged_count == 1


def test_preview_update_amount():
    existing = [{"fiscal_year": 2026, "fiscal_quarter": 3, "leader_team": "A",
                 "expense_category": "業務委託費",
                 "budget_amount": 100, "memo": None, "version": 1}]
    client = _mock_bq_with_existing(existing)
    rows = [ubq.QuarterlyBudgetRow(2026, 3, "A", "業務委託費", 200, None)]
    preview = ubq.preview_changes(client, rows)
    assert preview.update_count == 1


def test_preview_empty():
    client = MagicMock()
    preview = ubq.preview_changes(client, [])
    assert preview.new_count == 0
    client.query.assert_not_called()


# --- do_merge_single ---


def test_do_merge_single_optimistic():
    client = MagicMock()
    job = MagicMock(num_dml_affected_rows=1)
    client.query.return_value = job
    row = ubq.QuarterlyBudgetRow(2026, 3, "A", "業務委託費", 1000, "memo")
    affected = ubq.do_merge_single(client, row, "actor", force=False, expected_version=2)
    assert affected == 1
    sql = client.query.call_args[0][0]
    assert "version = @expected_version" in sql
    params = client.query.call_args[1]["job_config"].query_parameters
    assert any(p.name == "expected_version" and p.value == 2 for p in params)


def test_do_merge_single_passes_decimal_for_numeric(monkeypatch):
    """budget_amount は NUMERIC 型に Decimal で渡される (CR-H2 修正検証)。"""
    from decimal import Decimal
    client = MagicMock()
    job = MagicMock(num_dml_affected_rows=1)
    client.query.return_value = job
    row = ubq.QuarterlyBudgetRow(2026, 3, "A", "業務委託費", 5289363, None)
    ubq.do_merge_single(client, row, "actor", force=True)
    params = client.query.call_args[1]["job_config"].query_parameters
    budget_param = next(p for p in params if p.name == "budget_amount")
    assert budget_param.type_ == "NUMERIC"
    assert isinstance(budget_param.value, Decimal)
    assert budget_param.value == Decimal(5289363)


def test_merge_sql_preserves_audit_fields_on_match():
    """MERGE WHEN MATCHED で created_at / created_by が更新対象に含まれないこと
    (Partial Update MUST、CLAUDE.md / CR-L1 反映)。"""
    # MERGE SQL の WHEN MATCHED ... UPDATE SET 句に created_at / created_by が含まれてはいけない
    matched_section = ubq.MERGE_SQL_OPTIMISTIC.split("WHEN MATCHED")[1].split("WHEN NOT MATCHED")[0]
    assert "created_at" not in matched_section
    assert "created_by" not in matched_section
    # 更新対象は budget_amount / memo / version / updated_at / updated_by のみ
    assert "budget_amount = s.budget_amount" in matched_section
    assert "version = t.version + 1" in matched_section
    assert "updated_by = s.actor" in matched_section
    # FORCE 版も同様
    matched_force = ubq.MERGE_SQL_FORCE.split("WHEN MATCHED")[1].split("WHEN NOT MATCHED")[0]
    assert "created_at" not in matched_force
    assert "created_by" not in matched_force


def test_do_merge_single_force():
    client = MagicMock()
    job = MagicMock(num_dml_affected_rows=1)
    client.query.return_value = job
    row = ubq.QuarterlyBudgetRow(2026, 3, "A", "業務委託費", 1000, None)
    ubq.do_merge_single(client, row, "actor", force=True)
    sql = client.query.call_args[0][0]
    assert "version = @expected_version" not in sql


def test_do_merge_single_lock_conflict():
    client = MagicMock()
    job = MagicMock(num_dml_affected_rows=0)
    client.query.return_value = job
    row = ubq.QuarterlyBudgetRow(2026, 3, "A", "業務委託費", 1000, None)
    affected = ubq.do_merge_single(client, row, "actor", force=False, expected_version=1)
    assert affected == 0


# --- merge_in_batches ---


def test_merge_in_batches_counts(monkeypatch):
    client = MagicMock()
    rows = [
        ubq.QuarterlyBudgetRow(2026, 3, "A", "業務委託費", 100, None),
        ubq.QuarterlyBudgetRow(2026, 3, "B", "業務委託費", 200, None),
        ubq.QuarterlyBudgetRow(2026, 3, "C", "業務委託費", 300, None),
    ]
    preview = ubq.PreviewResult(0, 3, 0, [
        ("update", rows[0], {"version": 1}),
        ("update", rows[1], {"version": 1}),
        ("update", rows[2], {"version": 1}),
    ])
    call_n = {"n": 0}
    def fake(c, r, actor, force, expected_version=None):
        call_n["n"] += 1
        if call_n["n"] == 1:
            return 1
        if call_n["n"] == 2:
            return 0
        raise RuntimeError("fail")
    monkeypatch.setattr(ubq, "do_merge_single", fake)
    success, skipped, unchanged, failed = ubq.merge_in_batches(
        client, rows, "actor", False, preview)
    assert (success, skipped, unchanged, failed) == (1, 1, 0, 1)


def test_merge_in_batches_skip_unchanged(monkeypatch):
    client = MagicMock()
    rows = [
        ubq.QuarterlyBudgetRow(2026, 3, "A", "業務委託費", 100, None),
        ubq.QuarterlyBudgetRow(2026, 3, "B", "業務委託費", 200, None),
    ]
    preview = ubq.PreviewResult(0, 1, 1, [
        ("unchanged", rows[0], {"version": 3, "budget_amount": 100, "memo": None}),
        ("update", rows[1], {"version": 1, "budget_amount": 999, "memo": None}),
    ])
    merge_calls = []
    def fake(c, r, actor, force, expected_version=None):
        merge_calls.append(r.key)
        return 1
    monkeypatch.setattr(ubq, "do_merge_single", fake)
    success, skipped, unchanged, failed = ubq.merge_in_batches(
        client, rows, "actor", False, preview)
    assert (success, skipped, unchanged, failed) == (1, 0, 1, 0)
    assert merge_calls == [(2026, 3, "B", "業務委託費")]


# --- print_preview total mismatch (CR-H3/Codex H3) ---


def test_print_preview_returns_true_when_expected_total_matches(capsys):
    preview = ubq.PreviewResult(0, 0, 0, [])
    ok = ubq.print_preview(preview, 23457444, expected_total=23457444)
    assert ok is True


def test_print_preview_returns_false_on_total_mismatch(capsys):
    preview = ubq.PreviewResult(0, 0, 0, [])
    ok = ubq.print_preview(preview, 23000000, expected_total=23457444)
    assert ok is False


def test_print_preview_returns_true_when_no_expected_total(capsys):
    preview = ubq.PreviewResult(0, 0, 0, [])
    ok = ubq.print_preview(preview, 1000, expected_total=None)
    assert ok is True


# --- fiscal_quarter equivalent logic (案 N11、CR-M2 反映) ---


def _fiscal_quarter_py(year: int, month: int) -> tuple[int, int]:
    """upload_team_budgets_quarterly では使わないが、UDF fiscal_quarter の Python 同等実装
    (テストの対称検証用)。BQ UDF と同じロジック:
        fiscal_year = year + 1 if month >= 11 else year
        fiscal_quarter = 1 + (((month - 11 + 12) % 12) // 3)
    """
    fy = year + 1 if month >= 11 else year
    fq = 1 + (((month - 11 + 12) % 12) // 3)
    return fy, fq


@pytest.mark.parametrize("year,month,expected_fy,expected_fq", [
    # Q1 = 11-12-1月
    (2025, 11, 2026, 1),  # 暦 2025-11 → FY2026 Q1
    (2025, 12, 2026, 1),
    (2026,  1, 2026, 1),
    # Q2 = 2-3-4月
    (2026,  2, 2026, 2),
    (2026,  3, 2026, 2),
    (2026,  4, 2026, 2),
    # Q3 = 5-6-7月 (画像「第3Q 5-7月」と一致)
    (2026,  5, 2026, 3),
    (2026,  6, 2026, 3),
    (2026,  7, 2026, 3),
    # Q4 = 8-9-10月
    (2026,  8, 2026, 4),
    (2026,  9, 2026, 4),
    (2026, 10, 2026, 4),
    # 翌 FY 境界
    (2026, 11, 2027, 1),
])
def test_fiscal_quarter_boundary_cases(year, month, expected_fy, expected_fq):
    fy, fq = _fiscal_quarter_py(year, month)
    assert fy == expected_fy
    assert fq == expected_fq


# --- resolve_actor ---


def test_resolve_actor_prefers_git_author_email(monkeypatch):
    monkeypatch.setenv("GIT_AUTHOR_EMAIL", "a@x")
    monkeypatch.setenv("USER", "fallback")
    assert ubq.resolve_actor() == "script:upload_team_budgets_quarterly:a@x"


def test_resolve_actor_unknown(monkeypatch):
    monkeypatch.delenv("GIT_AUTHOR_EMAIL", raising=False)
    monkeypatch.delenv("GIT_COMMITTER_EMAIL", raising=False)
    monkeypatch.delenv("USER", raising=False)
    assert ubq.resolve_actor() == "script:upload_team_budgets_quarterly:unknown"
