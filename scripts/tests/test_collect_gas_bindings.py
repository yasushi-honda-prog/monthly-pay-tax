"""scripts/collect_gas_bindings.py の回帰テスト（Codex 指摘 #1/#3 + スキップ規則 + 入力検証）。

ローカル半手動ロードツールの純粋ロジック部分を、bq CLI / clasp トークン / build_targets を
モックして検証する。本番 BQ / Apps Script API には接続しない。
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
    # script_id を持つ ok 行が無ければ検証対象なし → 0（安全装置の起動不要）
    results = [{"status": "error", "script_id": None},
               {"status": "ok", "script_id": None}]
    assert c.check_create_times(results, _now()) == 0


def test_check_create_times_raises_when_clasp_unavailable(monkeypatch):
    # clasp トークンが読めない（= 安全装置を初期化できない）→ 検証不能で RuntimeError
    monkeypatch.setattr(c.os.path, "expanduser", lambda _p: "/nonexistent/.clasprc.json")
    results = [{"status": "ok", "script_id": "SID1", "nickname": "x", "spreadsheet_id": "AAA"}]
    with pytest.raises(RuntimeError, match="fail-closed"):
        c.check_create_times(results, _now())


# --- select_targets のスキップ規則（明示キーワード引数 / 巡回対象算出の補助）---
def test_select_targets_skips_ok_by_default():
    targets = [{"spreadsheet_id": "AAA"}, {"spreadsheet_id": "BBB"}]
    existing = {"AAA": {"status": "ok", "fetched_at_iso": None}}
    out = c.select_targets(targets, existing)
    assert [t["spreadsheet_id"] for t in out] == ["BBB"]  # AAA=ok スキップ / BBB=未登録で対象


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
    # error のみ再試行。ok / no_gas（空プロジェクト再生成リスク）は触らない
    assert [t["spreadsheet_id"] for t in out] == ["BBB"]


def test_select_targets_limit():
    targets = [{"spreadsheet_id": f"S{i}"} for i in range(5)]
    out = c.select_targets(targets, {}, limit=2)
    assert len(out) == 2


# --- 入力パーサ（_read_input は二重 JSON 文字列 + 行レベル検証に対応）---
def test_read_input_plain_array(tmp_path):
    p = tmp_path / "r.json"
    p.write_text('[{"spreadsheet_id": "AAA", "status": "ok"}]', encoding="utf-8")
    assert c._read_input(str(p)) == [{"spreadsheet_id": "AAA", "status": "ok"}]


def test_read_input_double_encoded(tmp_path):
    # MCP run_code が結果を JSON 文字列として返すケース（先頭が `"`）
    p = tmp_path / "r.json"
    p.write_text('"[{\\"spreadsheet_id\\": \\"AAA\\", \\"status\\": \\"ok\\"}]"', encoding="utf-8")
    assert c._read_input(str(p)) == [{"spreadsheet_id": "AAA", "status": "ok"}]


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
    # 行レベル検証: spreadsheet_id 欠落は境界で弾く（下流の生 KeyError を防ぐ）
    p = tmp_path / "r.json"
    p.write_text('[{"status": "ok"}]', encoding="utf-8")
    with pytest.raises(ValueError, match="spreadsheet_id"):
        c._read_input(str(p))


def test_read_input_rejects_row_without_status(tmp_path):
    p = tmp_path / "r.json"
    p.write_text('[{"spreadsheet_id": "AAA"}]', encoding="utf-8")
    with pytest.raises(ValueError, match="status"):
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
    # 補完: master ヒット行はメタが入り、miss 行は None + フォールバック URL
    assert results[0]["nickname"] == "a"
    assert results[1]["nickname"] is None
    assert results[1]["report_url"].endswith("/ZZZ/edit")
    # 欠損フィールド補完: ok 行は fetched_at が埋まり、欠損キーは None で揃う
    assert results[0]["fetched_at"] is not None
    assert results[0]["editor_url"] is None


def test_enrich_with_metadata_nulls_fetched_at_for_non_ok(monkeypatch):
    monkeypatch.setattr(c, "build_targets", lambda: [])
    results = [{"spreadsheet_id": "AAA", "status": "error"}]
    c._enrich_with_metadata(results)
    assert results[0]["fetched_at"] is None  # 非 ok は fetched_at を立てない
