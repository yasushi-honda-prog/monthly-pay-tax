"""scripts/upload_budgets.py の単体テスト。

カバー範囲:
- parse_csv の正常系と全 validation エラーパス
- find_duplicates の重複検出
- preview_changes の新規/更新/変更なし判定
- do_merge_single の MERGE SQL パラメータ構築 (optimistic / force)
- merge_in_batches の skipped (lock 競合) / failed のカウント
- resolve_actor の優先順位

BQ client / API には接続せず、google.cloud.bigquery のクラスは MagicMock で差し替える。
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import upload_budgets as ub  # noqa: E402


# --- parse_csv ---


def _write_csv(tmp_path: Path, content: str) -> Path:
    p = tmp_path / "budgets.csv"
    p.write_text(content, encoding="utf-8")
    return p


def test_parse_csv_happy_path(tmp_path):
    csv_path = _write_csv(tmp_path, "year,month,team,budget_amount,memo\n"
                          "2026,5,ケアプー隊,1000000,本格運用\n"
                          "2026,5,広報がんばり隊,500000,\n"
                          "2026,6,すごい隊,800000,\n")
    rows = ub.parse_csv(str(csv_path))
    assert len(rows) == 3
    assert rows[0] == ub.BudgetRow(2026, 5, "ケアプー隊", 1000000, "本格運用")
    assert rows[1].memo is None  # 空文字 → None
    assert rows[2].team == "すごい隊"


def test_parse_csv_missing_header_column(tmp_path):
    csv_path = _write_csv(tmp_path, "year,month,team\n2026,5,test\n")
    with pytest.raises(ValueError, match="必須列が不足"):
        ub.parse_csv(str(csv_path))


def test_parse_csv_year_out_of_range(tmp_path):
    csv_path = _write_csv(tmp_path, "year,month,team,budget_amount,memo\n"
                          "2020,5,test,1000,\n")
    with pytest.raises(ValueError, match="year 値域外"):
        ub.parse_csv(str(csv_path))


def test_parse_csv_month_out_of_range(tmp_path):
    csv_path = _write_csv(tmp_path, "year,month,team,budget_amount,memo\n"
                          "2026,13,test,1000,\n")
    with pytest.raises(ValueError, match="month 値域外"):
        ub.parse_csv(str(csv_path))


def test_parse_csv_team_empty(tmp_path):
    csv_path = _write_csv(tmp_path, "year,month,team,budget_amount,memo\n"
                          "2026,5,,1000,\n")
    with pytest.raises(ValueError, match="team が空文字"):
        ub.parse_csv(str(csv_path))


def test_parse_csv_budget_negative(tmp_path):
    csv_path = _write_csv(tmp_path, "year,month,team,budget_amount,memo\n"
                          "2026,5,test,-100,\n")
    with pytest.raises(ValueError, match="budget_amount が負値"):
        ub.parse_csv(str(csv_path))


def test_parse_csv_non_numeric_budget(tmp_path):
    csv_path = _write_csv(tmp_path, "year,month,team,budget_amount,memo\n"
                          "2026,5,test,abc,\n")
    with pytest.raises(ValueError, match="フィールド値が不正"):
        ub.parse_csv(str(csv_path))


def test_parse_csv_file_not_found():
    with pytest.raises(FileNotFoundError):
        ub.parse_csv("/nonexistent/path/budgets.csv")


# --- find_duplicates ---


def test_find_duplicates_no_dup():
    rows = [
        ub.BudgetRow(2026, 5, "A", 100, None),
        ub.BudgetRow(2026, 5, "B", 200, None),
        ub.BudgetRow(2026, 6, "A", 300, None),
    ]
    assert ub.find_duplicates(rows) == []


def test_find_duplicates_detects():
    rows = [
        ub.BudgetRow(2026, 5, "A", 100, None),
        ub.BudgetRow(2026, 5, "A", 200, None),
        ub.BudgetRow(2026, 5, "B", 300, None),
        ub.BudgetRow(2026, 6, "B", 400, None),
        ub.BudgetRow(2026, 6, "B", 500, None),
    ]
    dups = ub.find_duplicates(rows)
    assert (2026, 5, "A") in dups
    assert (2026, 6, "B") in dups
    assert len(dups) == 2


# --- preview_changes ---


def _mock_bq_client_with_existing(existing_rows: list[dict]) -> MagicMock:
    """既存 team_budgets レコードをモック返却する Client を生成"""
    client = MagicMock()
    job = MagicMock()
    rows = [MagicMock(items=lambda r=r: r.items(), **r) for r in existing_rows]
    for i, row in enumerate(rows):
        for k, v in existing_rows[i].items():
            setattr(row, k, v)
    job.result.return_value = iter(rows)
    client.query.return_value = job
    return client


def test_preview_changes_all_new():
    client = _mock_bq_client_with_existing([])
    rows = [ub.BudgetRow(2026, 5, "A", 100, None)]
    preview = ub.preview_changes(client, rows)
    assert preview.new_count == 1
    assert preview.update_count == 0
    assert preview.unchanged_count == 0


def test_preview_changes_unchanged():
    existing = [{"year": 2026, "month": 5, "team": "A",
                 "budget_amount": 100, "memo": None, "version": 1}]
    client = _mock_bq_client_with_existing(existing)
    rows = [ub.BudgetRow(2026, 5, "A", 100, None)]
    preview = ub.preview_changes(client, rows)
    assert preview.unchanged_count == 1
    assert preview.new_count == 0
    assert preview.update_count == 0


def test_preview_changes_update_amount_change():
    existing = [{"year": 2026, "month": 5, "team": "A",
                 "budget_amount": 100, "memo": None, "version": 1}]
    client = _mock_bq_client_with_existing(existing)
    rows = [ub.BudgetRow(2026, 5, "A", 200, None)]  # amount 変更
    preview = ub.preview_changes(client, rows)
    assert preview.update_count == 1
    assert preview.unchanged_count == 0


def test_preview_changes_update_memo_change():
    existing = [{"year": 2026, "month": 5, "team": "A",
                 "budget_amount": 100, "memo": "old", "version": 1}]
    client = _mock_bq_client_with_existing(existing)
    rows = [ub.BudgetRow(2026, 5, "A", 100, "new")]  # memo 変更
    preview = ub.preview_changes(client, rows)
    assert preview.update_count == 1


def test_preview_changes_empty_rows():
    client = MagicMock()
    preview = ub.preview_changes(client, [])
    assert (preview.new_count, preview.update_count, preview.unchanged_count) == (0, 0, 0)
    client.query.assert_not_called()


# --- do_merge_single ---


def test_do_merge_single_optimistic_uses_expected_version():
    client = MagicMock()
    job = MagicMock(num_dml_affected_rows=1)
    client.query.return_value = job
    row = ub.BudgetRow(2026, 5, "A", 1000, "memo")
    affected = ub.do_merge_single(client, row, "actor", force=False, expected_version=3)
    assert affected == 1
    sql = client.query.call_args[0][0]
    assert "version = @expected_version" in sql
    params = client.query.call_args[1]["job_config"].query_parameters
    assert any(p.name == "expected_version" and p.value == 3 for p in params)


def test_do_merge_single_force_skips_version():
    client = MagicMock()
    job = MagicMock(num_dml_affected_rows=1)
    client.query.return_value = job
    row = ub.BudgetRow(2026, 5, "A", 1000, None)
    ub.do_merge_single(client, row, "actor", force=True)
    sql = client.query.call_args[0][0]
    assert "version = @expected_version" not in sql
    params = client.query.call_args[1]["job_config"].query_parameters
    assert all(p.name != "expected_version" for p in params)


def test_do_merge_single_returns_zero_when_no_rows_affected():
    """optimistic lock 競合時は num_dml_affected_rows=0 で返る"""
    client = MagicMock()
    job = MagicMock(num_dml_affected_rows=0)
    client.query.return_value = job
    row = ub.BudgetRow(2026, 5, "A", 1000, None)
    affected = ub.do_merge_single(client, row, "actor", force=False, expected_version=1)
    assert affected == 0


# --- merge_in_batches ---


def test_merge_in_batches_counts_success_skip_failed(monkeypatch):
    client = MagicMock()
    rows = [
        ub.BudgetRow(2026, 5, "A", 100, None),
        ub.BudgetRow(2026, 5, "B", 200, None),
        ub.BudgetRow(2026, 5, "C", 300, None),
    ]
    preview = ub.PreviewResult(new_count=0, update_count=3, unchanged_count=0,
                               details=[
                                   ("update", rows[0], {"version": 1}),
                                   ("update", rows[1], {"version": 1}),
                                   ("update", rows[2], {"version": 1}),
                               ])

    call_count = {"n": 0}
    def fake_merge(c, r, actor, force, expected_version=None):
        call_count["n"] += 1
        if call_count["n"] == 1:
            return 1  # success
        if call_count["n"] == 2:
            return 0  # skipped (lock conflict)
        raise RuntimeError("BQ error")
    monkeypatch.setattr(ub, "do_merge_single", fake_merge)

    success, skipped, unchanged, failed = ub.merge_in_batches(client, rows, "actor", force=False, preview=preview)
    assert success == 1
    assert skipped == 1
    assert unchanged == 0
    assert failed == 1


def test_merge_in_batches_skips_unchanged_rows(monkeypatch):
    """UNCHANGED 行は MERGE 呼び出しせず unchanged にカウントされる（version 無駄インクリメント回避）"""
    client = MagicMock()
    rows = [
        ub.BudgetRow(2026, 5, "A", 100, None),
        ub.BudgetRow(2026, 5, "B", 200, None),
    ]
    preview = ub.PreviewResult(new_count=0, update_count=1, unchanged_count=1,
                               details=[
                                   ("unchanged", rows[0], {"version": 3,
                                                            "budget_amount": 100, "memo": None}),
                                   ("update", rows[1], {"version": 1,
                                                         "budget_amount": 999, "memo": None}),
                               ])

    merge_calls = []
    def fake_merge(c, r, actor, force, expected_version=None):
        merge_calls.append(r.key)
        return 1
    monkeypatch.setattr(ub, "do_merge_single", fake_merge)

    success, skipped, unchanged, failed = ub.merge_in_batches(
        client, rows, "actor", force=False, preview=preview)
    assert success == 1
    assert unchanged == 1
    assert skipped == 0
    assert failed == 0
    assert merge_calls == [(2026, 5, "B")]  # UNCHANGED の A は呼ばれない


# --- resolve_actor ---


def test_resolve_actor_prefers_git_author_email(monkeypatch):
    monkeypatch.setenv("GIT_AUTHOR_EMAIL", "author@example.com")
    monkeypatch.setenv("GIT_COMMITTER_EMAIL", "committer@example.com")
    monkeypatch.setenv("USER", "fallback")
    assert ub.resolve_actor() == "script:upload_budgets:author@example.com"


def test_resolve_actor_fallback_to_user(monkeypatch):
    monkeypatch.delenv("GIT_AUTHOR_EMAIL", raising=False)
    monkeypatch.delenv("GIT_COMMITTER_EMAIL", raising=False)
    monkeypatch.setenv("USER", "localuser")
    assert ub.resolve_actor() == "script:upload_budgets:localuser"


def test_resolve_actor_unknown(monkeypatch):
    monkeypatch.delenv("GIT_AUTHOR_EMAIL", raising=False)
    monkeypatch.delenv("GIT_COMMITTER_EMAIL", raising=False)
    monkeypatch.delenv("USER", raising=False)
    assert ub.resolve_actor() == "script:upload_budgets:unknown"


# --- validate_hierarchy_coverage (PR-A) ---


def _mock_hierarchy_client(activity_categories: list[str]) -> MagicMock:
    """team_hierarchy SELECT に対して指定 activity_category を返す mock client"""
    client = MagicMock()
    rows = [MagicMock(activity_category=cat) for cat in activity_categories]
    client.query.return_value.result.return_value = rows
    return client


def test_validate_hierarchy_all_registered():
    """全 team が hierarchy に登録済み → exit 0"""
    client = _mock_hierarchy_client(["A 隊", "B 隊", "C 隊"])
    rows = [
        ub.BudgetRow(year=2026, month=5, team="A 隊", budget_amount=100, memo=None),
        ub.BudgetRow(year=2026, month=5, team="B 隊", budget_amount=200, memo=None),
    ]
    assert ub.validate_hierarchy_coverage(client, rows) == 0


def test_validate_hierarchy_unregistered_warns_but_continues():
    """未登録 team があっても strict なしなら exit 0 (warning のみ)"""
    client = _mock_hierarchy_client(["A 隊"])
    rows = [
        ub.BudgetRow(year=2026, month=5, team="A 隊", budget_amount=100, memo=None),
        ub.BudgetRow(year=2026, month=5, team="未登録隊", budget_amount=200, memo=None),
    ]
    assert ub.validate_hierarchy_coverage(client, rows, strict=False) == 0


def test_validate_hierarchy_unregistered_strict_fails():
    """未登録 team + strict モード → exit 1"""
    client = _mock_hierarchy_client(["A 隊"])
    rows = [
        ub.BudgetRow(year=2026, month=5, team="A 隊", budget_amount=100, memo=None),
        ub.BudgetRow(year=2026, month=5, team="未登録隊", budget_amount=200, memo=None),
    ]
    assert ub.validate_hierarchy_coverage(client, rows, strict=True) == 1


def test_validate_hierarchy_empty_table_skips_check():
    """team_hierarchy が空 → check skip (warning のみ、exit 0)"""
    client = _mock_hierarchy_client([])
    rows = [
        ub.BudgetRow(year=2026, month=5, team="任意隊", budget_amount=100, memo=None),
    ]
    assert ub.validate_hierarchy_coverage(client, rows, strict=True) == 0
