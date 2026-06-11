"""scripts/upload_team_hierarchy.py の単体テスト。

カバー範囲:
- parse_csv: 正常系 + 全 validation エラーパス
- find_duplicates: 重複検出
- preview_changes: 新規/更新/変更なし判定 (leader_team / leader_team_type / note 変更)
- do_merge_single: MERGE SQL パラメータ構築 (optimistic / force)
- merge_in_batches: skipped (lock 競合) / failed のカウント、UNCHANGED 行スキップ
- resolve_actor: 優先順位

BQ client は MagicMock で差し替え。
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import upload_team_hierarchy as uth  # noqa: E402


# --- parse_csv ---


def _write_csv(tmp_path: Path, content: str) -> Path:
    p = tmp_path / "hierarchy.csv"
    p.write_text(content, encoding="utf-8")
    return p


def test_parse_csv_happy_path(tmp_path):
    csv_path = _write_csv(tmp_path, "activity_category,leader_team,leader_team_type,note\n"
                          "タダスク,シロロ+ゆずるん統括隊,operating,本格運用\n"
                          "法人本部,共通,common,\n"
                          "ケアプー隊,ヤスス+ヒデデン統括隊,operating,\n")
    rows = uth.parse_csv(str(csv_path))
    assert len(rows) == 3
    assert rows[0] == uth.HierarchyRow("タダスク", "シロロ+ゆずるん統括隊", "operating", "本格運用")
    assert rows[1].note is None
    assert rows[1].leader_team_type == "common"
    assert rows[2].leader_team == "ヤスス+ヒデデン統括隊"


def test_parse_csv_missing_header(tmp_path):
    csv_path = _write_csv(tmp_path, "activity_category,leader_team\nA,B\n")
    with pytest.raises(ValueError, match="必須列が不足"):
        uth.parse_csv(str(csv_path))


def test_parse_csv_empty_activity_category(tmp_path):
    csv_path = _write_csv(tmp_path, "activity_category,leader_team,leader_team_type,note\n"
                          ",シロロ統括隊,operating,\n")
    with pytest.raises(ValueError, match="activity_category が空文字"):
        uth.parse_csv(str(csv_path))


def test_parse_csv_empty_leader_team(tmp_path):
    csv_path = _write_csv(tmp_path, "activity_category,leader_team,leader_team_type,note\n"
                          "タダスク,,operating,\n")
    with pytest.raises(ValueError, match="leader_team が空文字"):
        uth.parse_csv(str(csv_path))


def test_parse_csv_invalid_leader_team_type(tmp_path):
    csv_path = _write_csv(tmp_path, "activity_category,leader_team,leader_team_type,note\n"
                          "タダスク,シロロ統括隊,invalid_type,\n")
    with pytest.raises(ValueError, match="leader_team_type 値域外"):
        uth.parse_csv(str(csv_path))


def test_parse_csv_file_not_found():
    with pytest.raises(FileNotFoundError):
        uth.parse_csv("/nonexistent/path/hierarchy.csv")


# --- find_duplicates ---


def test_find_duplicates_no_dup():
    rows = [
        uth.HierarchyRow("A", "Leader1", "operating", None),
        uth.HierarchyRow("B", "Leader2", "operating", None),
    ]
    assert uth.find_duplicates(rows) == []


def test_find_duplicates_detects():
    rows = [
        uth.HierarchyRow("A", "L1", "operating", None),
        uth.HierarchyRow("A", "L2", "operating", None),  # 重複
        uth.HierarchyRow("B", "L1", "operating", None),
        uth.HierarchyRow("C", "L1", "common", None),
        uth.HierarchyRow("C", "L1", "operating", None),  # 重複
    ]
    dups = uth.find_duplicates(rows)
    assert "A" in dups
    assert "C" in dups
    assert len(dups) == 2


# --- preview_changes ---


def _mock_bq_client_with_existing(existing_rows: list[dict]) -> MagicMock:
    client = MagicMock()
    job = MagicMock()
    rows = []
    for r in existing_rows:
        mr = MagicMock(items=lambda r=r: r.items())
        for k, v in r.items():
            setattr(mr, k, v)
        rows.append(mr)
    job.result.return_value = iter(rows)
    client.query.return_value = job
    return client


def test_preview_changes_all_new():
    client = _mock_bq_client_with_existing([])
    rows = [uth.HierarchyRow("タダスク", "シロロ統括隊", "operating", None)]
    preview = uth.preview_changes(client, rows)
    assert preview.new_count == 1
    assert preview.update_count == 0
    assert preview.unchanged_count == 0


def test_preview_changes_unchanged():
    existing = [{"activity_category": "タダスク", "leader_team": "シロロ統括隊",
                 "leader_team_type": "operating", "note": None, "version": 1}]
    client = _mock_bq_client_with_existing(existing)
    rows = [uth.HierarchyRow("タダスク", "シロロ統括隊", "operating", None)]
    preview = uth.preview_changes(client, rows)
    assert preview.unchanged_count == 1


def test_preview_changes_update_leader_team():
    existing = [{"activity_category": "タダスク", "leader_team": "古い統括隊",
                 "leader_team_type": "operating", "note": None, "version": 1}]
    client = _mock_bq_client_with_existing(existing)
    rows = [uth.HierarchyRow("タダスク", "新しい統括隊", "operating", None)]
    preview = uth.preview_changes(client, rows)
    assert preview.update_count == 1


def test_preview_changes_update_type():
    existing = [{"activity_category": "X", "leader_team": "L",
                 "leader_team_type": "operating", "note": None, "version": 2}]
    client = _mock_bq_client_with_existing(existing)
    rows = [uth.HierarchyRow("X", "L", "common", None)]
    preview = uth.preview_changes(client, rows)
    assert preview.update_count == 1


def test_preview_changes_update_note():
    existing = [{"activity_category": "X", "leader_team": "L",
                 "leader_team_type": "operating", "note": "old", "version": 1}]
    client = _mock_bq_client_with_existing(existing)
    rows = [uth.HierarchyRow("X", "L", "operating", "new")]
    preview = uth.preview_changes(client, rows)
    assert preview.update_count == 1


def test_preview_changes_empty_rows():
    client = MagicMock()
    preview = uth.preview_changes(client, [])
    assert (preview.new_count, preview.update_count, preview.unchanged_count) == (0, 0, 0)
    client.query.assert_not_called()


# --- do_merge_single ---


def test_do_merge_single_optimistic_uses_expected_version():
    client = MagicMock()
    job = MagicMock(num_dml_affected_rows=1)
    client.query.return_value = job
    row = uth.HierarchyRow("X", "L", "operating", "note")
    affected = uth.do_merge_single(client, row, "actor", force=False, expected_version=5)
    assert affected == 1
    sql = client.query.call_args[0][0]
    assert "version = @expected_version" in sql
    params = client.query.call_args[1]["job_config"].query_parameters
    assert any(p.name == "expected_version" and p.value == 5 for p in params)


def test_do_merge_single_force_skips_version():
    client = MagicMock()
    job = MagicMock(num_dml_affected_rows=1)
    client.query.return_value = job
    row = uth.HierarchyRow("X", "L", "operating", None)
    uth.do_merge_single(client, row, "actor", force=True)
    sql = client.query.call_args[0][0]
    assert "version = @expected_version" not in sql
    params = client.query.call_args[1]["job_config"].query_parameters
    assert all(p.name != "expected_version" for p in params)


def test_do_merge_single_returns_zero_on_lock_conflict():
    client = MagicMock()
    job = MagicMock(num_dml_affected_rows=0)
    client.query.return_value = job
    row = uth.HierarchyRow("X", "L", "operating", None)
    affected = uth.do_merge_single(client, row, "actor", force=False, expected_version=1)
    assert affected == 0


# --- merge_in_batches ---


def test_merge_in_batches_counts_success_skip_failed(monkeypatch):
    client = MagicMock()
    rows = [
        uth.HierarchyRow("A", "L", "operating", None),
        uth.HierarchyRow("B", "L", "operating", None),
        uth.HierarchyRow("C", "L", "operating", None),
    ]
    preview = uth.PreviewResult(0, 3, 0, [
        ("update", rows[0], {"version": 1}),
        ("update", rows[1], {"version": 1}),
        ("update", rows[2], {"version": 1}),
    ])

    call_count = {"n": 0}
    def fake_merge(c, r, actor, force, expected_version=None):
        call_count["n"] += 1
        if call_count["n"] == 1:
            return 1
        if call_count["n"] == 2:
            return 0  # lock conflict
        raise RuntimeError("BQ error")
    monkeypatch.setattr(uth, "do_merge_single", fake_merge)

    success, skipped, unchanged, failed = uth.merge_in_batches(
        client, rows, "actor", force=False, preview=preview)
    assert (success, skipped, unchanged, failed) == (1, 1, 0, 1)


def test_merge_in_batches_skips_unchanged(monkeypatch):
    client = MagicMock()
    rows = [
        uth.HierarchyRow("A", "L1", "operating", None),
        uth.HierarchyRow("B", "L1", "operating", None),
    ]
    preview = uth.PreviewResult(0, 1, 1, [
        ("unchanged", rows[0], {"version": 3, "leader_team": "L1",
                                 "leader_team_type": "operating", "note": None}),
        ("update", rows[1], {"version": 1, "leader_team": "old",
                              "leader_team_type": "operating", "note": None}),
    ])

    merge_calls = []
    def fake_merge(c, r, actor, force, expected_version=None):
        merge_calls.append(r.key)
        return 1
    monkeypatch.setattr(uth, "do_merge_single", fake_merge)

    success, skipped, unchanged, failed = uth.merge_in_batches(
        client, rows, "actor", force=False, preview=preview)
    assert (success, skipped, unchanged, failed) == (1, 0, 1, 0)
    assert merge_calls == ["B"]


# --- check_coverage ---


def test_check_coverage_reports_unmapped_unused():
    client = MagicMock()
    job = MagicMock()
    unmapped_row = MagicMock(status="UNMAPPED", cnt=3, sample=["X", "Y", "Z"])
    unused_row = MagicMock(status="UNUSED", cnt=2, sample=["OldA", "OldB"])
    job.result.return_value = iter([unmapped_row, unused_row])
    client.query.return_value = job

    unmapped, unused = uth.check_coverage(client)
    assert unmapped == 3
    assert unused == 2


def test_check_coverage_zero_when_clean():
    client = MagicMock()
    job = MagicMock()
    job.result.return_value = iter([])
    client.query.return_value = job
    unmapped, unused = uth.check_coverage(client)
    assert (unmapped, unused) == (0, 0)


# --- resolve_actor ---


def test_resolve_actor_prefers_git_author_email(monkeypatch):
    monkeypatch.setenv("GIT_AUTHOR_EMAIL", "author@example.com")
    monkeypatch.setenv("GIT_COMMITTER_EMAIL", "committer@example.com")
    monkeypatch.setenv("USER", "fallback")
    assert uth.resolve_actor() == "script:upload_team_hierarchy:author@example.com"


def test_resolve_actor_fallback_to_user(monkeypatch):
    monkeypatch.delenv("GIT_AUTHOR_EMAIL", raising=False)
    monkeypatch.delenv("GIT_COMMITTER_EMAIL", raising=False)
    monkeypatch.setenv("USER", "localuser")
    assert uth.resolve_actor() == "script:upload_team_hierarchy:localuser"


def test_resolve_actor_unknown(monkeypatch):
    monkeypatch.delenv("GIT_AUTHOR_EMAIL", raising=False)
    monkeypatch.delenv("GIT_COMMITTER_EMAIL", raising=False)
    monkeypatch.delenv("USER", raising=False)
    assert uth.resolve_actor() == "script:upload_team_hierarchy:unknown"
