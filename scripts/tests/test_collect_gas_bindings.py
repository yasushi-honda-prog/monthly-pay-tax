"""scripts/collect_gas_bindings.py の回帰テスト。

カバー範囲:
- Codex #1 check_create_times の fail-closed
- Codex #3 load_existing の例外伝播
- select_targets のスキップ規則
- _read_input の入力検証（型/非空/重複/ok↔script_id 整合）
- _enrich_with_metadata（メタ補完 + master miss カウント）
- load_merge の MERGE SQL（メタ列の COALESCE 保持）
- _resolve_suspect_after（検知フロア時刻の決定）

bq CLI / clasp トークン / build_targets をモックし、本番 BQ / Apps Script API には接続しない。
"""
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import collect_gas_bindings as c  # noqa: E402


def _now():
    return datetime(2026, 5, 31, tzinfo=timezone.utc)


# --- #3: load_existing は BQ エラーを握り潰さず伝播する（fail-closed）---
def test_load_existing_propagates_bq_error(monkeypatch):
    def boom(_sql):
        raise RuntimeError("bq query failed: dataset not found")
    monkeypatch.setattr(c, "_bq_query_json", boom)
    with pytest.raises(RuntimeError, match="bq query failed"):
        c.load_existing()


def test_load_existing_returns_map_on_success(monkeypatch):
    monkeypatch.setattr(c, "_bq_query_json", lambda _sql: [
        {"spreadsheet_id": "AAA", "status": "ok", "fetched_at_iso": "2026-05-31T00:00:00Z"},
        {"spreadsheet_id": "BBB", "status": "error", "fetched_at_iso": None},
    ])
    existing = c.load_existing()
    assert existing["AAA"]["status"] == "ok"
    assert existing["BBB"]["fetched_at_iso"] is None


# --- #1: check_create_times は検証不能時に fail-closed（例外で停止）---
def test_check_create_times_no_ok_returns_zero():
    results = [{"status": "error", "script_id": None},
               {"status": "ok", "script_id": None}]
    assert c.check_create_times(results, _now()) == 0


def test_check_create_times_raises_when_clasp_unavailable(monkeypatch):
    monkeypatch.setattr(c.os.path, "expanduser", lambda _p: "/nonexistent/.clasprc.json")
    results = [{"status": "ok", "script_id": "SID1", "nickname": "x", "spreadsheet_id": "AAA"}]
    with pytest.raises(RuntimeError, match="fail-closed"):
        c.check_create_times(results, _now())


# --- select_targets のスキップ規則（明示キーワード引数 / 巡回対象算出の補助）---
def test_select_targets_skips_ok_by_default():
    targets = [{"spreadsheet_id": "AAA"}, {"spreadsheet_id": "BBB"}]
    existing = {"AAA": {"status": "ok", "fetched_at_iso": None}}
    out = c.select_targets(targets, existing)
    assert [t["spreadsheet_id"] for t in out] == ["BBB"]


def test_select_targets_force_includes_all():
    targets = [{"spreadsheet_id": "AAA"}, {"spreadsheet_id": "BBB"}]
    existing = {"AAA": {"status": "ok", "fetched_at_iso": None}}
    out = c.select_targets(targets, existing, force=True)
    assert len(out) == 2


def test_select_targets_retry_errors_only():
    targets = [{"spreadsheet_id": "AAA"}, {"spreadsheet_id": "BBB"}, {"spreadsheet_id": "CCC"}]
    existing = {
        "AAA": {"status": "ok", "fetched_at_iso": None},
        "BBB": {"status": "error", "fetched_at_iso": None},
        "CCC": {"status": "no_gas", "fetched_at_iso": None},
    }
    out = c.select_targets(targets, existing, retry_errors=True)
    assert [t["spreadsheet_id"] for t in out] == ["BBB"]


def test_select_targets_limit():
    targets = [{"spreadsheet_id": f"S{i}"} for i in range(5)]
    out = c.select_targets(targets, {}, limit=2)
    assert len(out) == 2


# --- 入力パーサ（二重 JSON 文字列 + 行レベル検証）---
def test_read_input_plain_array(tmp_path):
    p = tmp_path / "r.json"
    p.write_text('[{"spreadsheet_id": "AAA", "status": "ok", "script_id": "S1"}]', encoding="utf-8")
    assert c._read_input(str(p)) == [{"spreadsheet_id": "AAA", "status": "ok", "script_id": "S1"}]


def test_read_input_double_encoded(tmp_path):
    # MCP run_code が結果を JSON 文字列として返すケース（先頭が `"`）
    p = tmp_path / "r.json"
    p.write_text(
        '"[{\\"spreadsheet_id\\": \\"AAA\\", \\"status\\": \\"ok\\", \\"script_id\\": \\"S1\\"}]"',
        encoding="utf-8")
    assert c._read_input(str(p)) == [{"spreadsheet_id": "AAA", "status": "ok", "script_id": "S1"}]


def test_read_input_empty_returns_empty(tmp_path):
    p = tmp_path / "r.json"
    p.write_text("   ", encoding="utf-8")
    assert c._read_input(str(p)) == []


def test_read_input_rejects_non_list(tmp_path):
    p = tmp_path / "r.json"
    p.write_text('{"spreadsheet_id": "AAA"}', encoding="utf-8")
    with pytest.raises(ValueError, match="JSON 配列"):
        c._read_input(str(p))


def test_read_input_rejects_row_without_spreadsheet_id(tmp_path):
    p = tmp_path / "r.json"
    p.write_text('[{"status": "ok", "script_id": "S1"}]', encoding="utf-8")
    with pytest.raises(ValueError, match="spreadsheet_id"):
        c._read_input(str(p))


def test_read_input_rejects_row_without_status(tmp_path):
    p = tmp_path / "r.json"
    p.write_text('[{"spreadsheet_id": "AAA"}]', encoding="utf-8")
    with pytest.raises(ValueError, match="status"):
        c._read_input(str(p))


def test_read_input_rejects_blank_spreadsheet_id(tmp_path):
    # finding 4: trim 後の非空検証
    p = tmp_path / "r.json"
    p.write_text('[{"spreadsheet_id": "  ", "status": "ok", "script_id": "S1"}]', encoding="utf-8")
    with pytest.raises(ValueError, match="spreadsheet_id"):
        c._read_input(str(p))


def test_read_input_rejects_non_string_status(tmp_path):
    # finding 4: status の型検証（数値を弾く）
    p = tmp_path / "r.json"
    p.write_text('[{"spreadsheet_id": "AAA", "status": 1}]', encoding="utf-8")
    with pytest.raises(ValueError, match="status"):
        c._read_input(str(p))


def test_read_input_rejects_ok_without_script_id(tmp_path):
    # finding 1: status=ok なのに script_id 欠落 → 既存 script_id の NULL 上書きを防ぐ
    p = tmp_path / "r.json"
    p.write_text('[{"spreadsheet_id": "AAA", "status": "ok"}]', encoding="utf-8")
    with pytest.raises(ValueError, match="script_id"):
        c._read_input(str(p))


def test_read_input_rejects_ok_with_blank_script_id(tmp_path):
    p = tmp_path / "r.json"
    p.write_text('[{"spreadsheet_id": "AAA", "status": "ok", "script_id": "  "}]', encoding="utf-8")
    with pytest.raises(ValueError, match="script_id"):
        c._read_input(str(p))


def test_read_input_accepts_non_ok_without_script_id(tmp_path):
    # ok 以外（no_gas/error 等）は script_id 任意
    p = tmp_path / "r.json"
    p.write_text('[{"spreadsheet_id": "AAA", "status": "no_gas"}]', encoding="utf-8")
    assert c._read_input(str(p)) == [{"spreadsheet_id": "AAA", "status": "no_gas"}]


def test_read_input_rejects_duplicate_spreadsheet_id(tmp_path):
    # finding 3: 重複 spreadsheet_id は MERGE 複数マッチ/重複 INSERT を招くため境界で弾く
    p = tmp_path / "r.json"
    p.write_text('[{"spreadsheet_id": "AAA", "status": "no_gas"}, '
                 '{"spreadsheet_id": "AAA", "status": "error"}]', encoding="utf-8")
    with pytest.raises(ValueError, match="重複"):
        c._read_input(str(p))


# --- _enrich_with_metadata（メタ補完 + 欠損補完 + master miss カウント）---
def test_enrich_with_metadata_fills_and_counts_misses(monkeypatch):
    monkeypatch.setattr(c, "build_targets", lambda: [
        {"spreadsheet_id": "AAA", "member_id": "1", "nickname": "a",
         "url_source": "url_1", "report_url": "https://docs.google.com/spreadsheets/d/AAA/edit"},
    ])
    results = [
        {"spreadsheet_id": "AAA", "status": "ok", "script_id": "S1"},
        {"spreadsheet_id": "ZZZ", "status": "ok", "script_id": "S2"},  # master に無い
    ]
    missing = c._enrich_with_metadata(results)
    assert missing == 1
    assert results[0]["nickname"] == "a"
    assert results[1]["nickname"] is None
    assert results[1]["report_url"].endswith("/ZZZ/edit")
    assert results[0]["fetched_at"] is not None
    assert results[0]["editor_url"] is None


def test_enrich_with_metadata_nulls_fetched_at_for_non_ok(monkeypatch):
    monkeypatch.setattr(c, "build_targets", lambda: [])
    results = [{"spreadsheet_id": "AAA", "status": "error"}]
    c._enrich_with_metadata(results)
    assert results[0]["fetched_at"] is None


# --- load_merge の MERGE SQL（finding 5: メタ列の COALESCE 保持）---
def test_load_merge_preserves_meta_with_coalesce(monkeypatch):
    captured = []
    monkeypatch.setattr(c, "_bq_load_ndjson", lambda rows: None)
    monkeypatch.setattr(c, "_bq_exec", lambda sql: captured.append(sql))
    results = [{"spreadsheet_id": "AAA", "status": "ok", "script_id": "S1",
                "member_id": "1", "nickname": "a", "url_source": "url_1",
                "report_url": "https://x/AAA", "editor_url": "https://e/S1",
                "error_type": None, "error_detail": None, "fetched_at": "2026-05-31T00:00:00Z"}]
    c.load_merge(results)
    merge_sql = captured[0]
    # member_master 由来のメタは COALESCE で既存保持、script_id/status は S 優先
    assert "member_id=COALESCE(S.member_id, T.member_id)" in merge_sql
    assert "nickname=COALESCE(S.nickname, T.nickname)" in merge_sql
    assert "report_url=COALESCE(S.report_url, T.report_url)" in merge_sql
    assert "script_id=S.script_id" in merge_sql
    assert "status=S.status" in merge_sql


# --- _resolve_suspect_after（finding 2: 検知フロア時刻の決定）---
def test_resolve_suspect_after_uses_crawl_started_at():
    dt = c._resolve_suspect_after("2026-05-31T10:30:00Z")
    assert dt == datetime(2026, 5, 31, 10, 30, tzinfo=timezone.utc)


def test_resolve_suspect_after_defaults_to_midnight():
    dt = c._resolve_suspect_after(None)
    assert dt.hour == 0 and dt.minute == 0 and dt.second == 0
    assert dt.tzinfo == timezone.utc


def test_resolve_suspect_after_rejects_bad_format():
    with pytest.raises(ValueError):
        c._resolve_suspect_after("not-a-date")
