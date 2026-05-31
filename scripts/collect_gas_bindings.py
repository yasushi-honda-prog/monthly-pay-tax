"""業務報告スプレッドシートの GAS Script ID 巡回結果を BigQuery へ MERGE するロードツール。

ローカル半手動実行ツール（CI / Cloud Run では動かない）。

Google の仕様上、スプレッドシート ID からコンテナバインドの Script ID を取得する
公開 API は存在しない。そのため各シートをログイン済みブラウザ（Playwright MCP）で開いて
「拡張機能 → Apps Script」の遷移先 URL（.../projects/{SCRIPT_ID}/edit）から Script ID を
抽出する。巡回そのものは Playwright MCP 側の run_code ループで行い（python-playwright は
Google の auth_required で失敗するため）、本スクリプトはその巡回結果（JSON 配列）を
受け取って安全装置を通し BigQuery へ MERGE する「結果ロード」に専念する。

安全装置:
  - MERGE: 取得済みの正常 script_id を、再取得失敗で上書きしない。
  - createTime 検知: 取得 script_id の作成時刻が巡回開始以降なら「新規空プロジェクト
    生成（unexpected_new_project）」を疑い停止扱いにする（被害の早期検知）。
    安全装置自体が機能しない場合（clasp トークン利用不可 / createTime 取得失敗）は、
    検証不能のまま MERGE せず例外で停止する（fail-closed）。

認証:
  - BigQuery I/O は `bq` CLI 経由（gcloud active account = yasushi-honda@tadakayo.jp）。
    ※ python の ADC は別アカウントを指す環境のため、ADC は使わない。
  - createTime 検証は ~/.clasprc.json の default トークン（clasp ログイン）を流用。

巡回対象の算出（どのシートを巡回するか）は build_targets / load_existing /
select_targets を import して別途行い、その結果を Playwright MCP の巡回ループへ渡す。

使い方:
  python3 scripts/collect_gas_bindings.py results.json          # JSON ファイルをロード
  cat results.json | python3 scripts/collect_gas_bindings.py -  # stdin からロード
  python3 scripts/collect_gas_bindings.py results.json --dry-run  # BQ 書込なし（検証のみ）

入力 JSON 形式（巡回結果オブジェクトの配列。MCP 結果が二重 JSON 文字列でも可）:
  [{"spreadsheet_id": "...", "status": "ok"|"error"|...,
    "script_id": "..."|null, "editor_url": "..."|null,
    "error_type": ...|null, "error_detail": ...|null}, ...]
  ※ member_id / nickname / url_source / report_url は member_master から自動補完する。
  ※ fetched_at は status=ok の行に無ければ現在時刻を補完する。
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

# --- 定数 ---
PROJECT = "monthly-pay-tax"
DATASET = "pay_reports"
TABLE_FQ = f"{PROJECT}.{DATASET}.gas_bindings"           # backtick 用（クエリ）
STAGING_SHORT = "gas_bindings_staging"
STAGING_LOAD = f"{PROJECT}:{DATASET}.{STAGING_SHORT}"    # bq load 用
STAGING_FQ = f"{PROJECT}.{DATASET}.{STAGING_SHORT}"      # backtick 用

SS_ID_RE = re.compile(r"/spreadsheets/d/([\w-]+)")

STRING_COLS = [
    "spreadsheet_id", "report_url", "script_id", "editor_url",
    "member_id", "nickname", "url_source",
    "status", "error_type", "error_detail",
]
LOAD_SCHEMA = ",".join(
    [f"{c}:STRING" for c in STRING_COLS] + ["fetched_at:TIMESTAMP", "ingested_at:TIMESTAMP"]
)

_BQ = ["bq", f"--project_id={PROJECT}"]


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# --- bq CLI ラッパ ---
def _bq_query_json(sql: str) -> list[dict]:
    r = subprocess.run(_BQ + ["query", "--use_legacy_sql=false", "--max_rows=100000",
                              "--format=json", sql],
                       capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"bq query failed: {r.stderr.strip()[-500:]}")
    out = r.stdout.strip()
    return json.loads(out) if out else []


def _bq_exec(sql: str) -> None:
    r = subprocess.run(_BQ + ["query", "--use_legacy_sql=false", "--format=none", sql],
                       capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"bq query failed: {r.stderr.strip()[-500:]}")


def _bq_load_ndjson(rows: list[dict]) -> None:
    with tempfile.NamedTemporaryFile("w", suffix=".ndjson", delete=False, encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
        path = f.name
    try:
        r = subprocess.run(
            _BQ + ["load", "--source_format=NEWLINE_DELIMITED_JSON", "--replace",
                   f"--schema={LOAD_SCHEMA}", STAGING_LOAD, path],
            capture_output=True, text=True,
        )
        if r.returncode != 0:
            raise RuntimeError(f"bq load failed: {r.stderr.strip()[-800:]}")
    finally:
        os.unlink(path)


# --- 対象リスト構築（member_master の url_1/url_2 を正規化） ---
def build_targets() -> list[dict]:
    query = f"""
    SELECT report_url, member_id, nickname, url_source FROM (
      SELECT report_url_1 AS report_url, member_id, nickname, 'url_1' AS url_source
      FROM `{PROJECT}.{DATASET}.member_master` WHERE COALESCE(report_url_1, '') != ''
      UNION ALL
      SELECT report_url_2 AS report_url, member_id, nickname, 'url_2' AS url_source
      FROM `{PROJECT}.{DATASET}.member_master` WHERE COALESCE(report_url_2, '') != ''
    )
    """
    targets: dict[str, dict] = {}
    for r in _bq_query_json(query):
        m = SS_ID_RE.search(r.get("report_url") or "")
        if not m:
            continue
        ss_id = m.group(1)
        targets.setdefault(ss_id, {
            "spreadsheet_id": ss_id,
            "report_url": r.get("report_url"),
            "member_id": r.get("member_id"),
            "nickname": r.get("nickname"),
            "url_source": r.get("url_source"),
        })
    return list(targets.values())


# --- 既存 status の読み込み（冪等スキップ用） ---
def load_existing() -> dict[str, dict]:
    """gas_bindings の既存 status を読み込む。

    BQ クエリが失敗した場合は例外を伝播する（「既存なし」と誤認して全件再取得・
    上書きするのを防ぐ fail-closed）。
    """
    rows = _bq_query_json(
        f"SELECT spreadsheet_id, status, "
        f"FORMAT_TIMESTAMP('%Y-%m-%dT%H:%M:%SZ', fetched_at) AS fetched_at_iso "
        f"FROM `{TABLE_FQ}`"
    )
    return {r["spreadsheet_id"]: {"status": r["status"], "fetched_at_iso": r.get("fetched_at_iso")}
            for r in rows}


def select_targets(targets, existing, *, force=False, retry_errors=False,
                   refresh_older_than=None, limit=None) -> list[dict]:
    """スキップ規則を適用して今回巡回すべき対象を返す（巡回対象算出の補助）。

    main() からは呼ばれない。Playwright MCP の巡回ループが import して
    「どのシートを巡回するか」を決めるための公開関数。引数は明示キーワードで受け、
    特定の CLI namespace 形状には依存しない。
    """
    out = []
    for t in targets:
        ex = existing.get(t["spreadsheet_id"])
        if force:
            out.append(t)
            continue
        if ex is None:
            out.append(t)
            continue
        st = ex["status"]
        if retry_errors:
            if st in ("error", "pending", "auth_required"):
                out.append(t)
            continue
        if st == "ok":
            if refresh_older_than is not None and ex.get("fetched_at_iso"):
                # 対象選定の補助判定。日付フォーマット不正時は再取得対象に含めない
                # （fail-open だが BQ への書き込みには影響しない選定ロジックのため許容）。
                try:
                    ft = datetime.fromisoformat(ex["fetched_at_iso"].replace("Z", "+00:00"))
                    if (datetime.now(timezone.utc) - ft).days >= refresh_older_than:
                        out.append(t)
                except (ValueError, TypeError):
                    pass
            continue
        # ok 以外（error/pending/no_gas/unexpected_new_project）は通常実行では再試行しない
        # （no_gas / unexpected は空プロジェクト再生成リスクのため retry_errors でも触らない）
    if limit is not None:
        out = out[: limit]
    return out


# --- createTime 安全装置（clasp default トークン流用 / fail-closed） ---
def check_create_times(results: list[dict], suspect_after: datetime) -> int:
    """取得 script_id の createTime を検証し、suspect_after 以降に作られた疑わしいものを停止扱いにする。

    suspect_after は「これ以降に作成された script は新規生成を疑う」検知フロア時刻。
    返り値は「新規プロジェクト生成の疑い」件数。該当行は script_id を無効化し
    status=unexpected_new_project に書き換える（MERGE では既存の ok を保全）。

    安全装置自体が機能しない場合（clasp トークン利用不可 / createTime 取得失敗 /
    createTime 欠落）は、検証不能のまま MERGE させないため RuntimeError を送出する
    （fail-closed）。
    """
    ok = [r for r in results if r["status"] == "ok" and r.get("script_id")]
    if not ok:
        return 0
    try:
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build
        d = json.load(open(os.path.expanduser("~/.clasprc.json")))
        t = d["tokens"]["default"]
        creds = Credentials(
            token=t.get("access_token"),
            refresh_token=t["refresh_token"],
            client_id=t["client_id"],
            client_secret=t["client_secret"],
            token_uri="https://oauth2.googleapis.com/token",
        )
        svc = build("script", "v1", credentials=creds, cache_discovery=False)
    except Exception as e:
        raise RuntimeError(
            f"createTime 安全装置を初期化できません（clasp トークン利用不可）: {e}. "
            f"検証不能のため BQ ロードを中止します（fail-closed）。"
            f"`clasp login` でトークンを更新してから再実行してください。"
        ) from e

    suspicious = 0
    for r in ok:
        try:
            proj = svc.projects().get(scriptId=r["script_id"]).execute()
        except Exception as e:
            raise RuntimeError(
                f"createTime の取得に失敗しました（script_id={r['script_id']}）: {e}. "
                f"検証不能のため BQ ロードを中止します（fail-closed）。"
            ) from e
        ct_raw = proj.get("createTime")
        if not ct_raw:
            raise RuntimeError(
                f"createTime が空でした（script_id={r['script_id']}）。"
                f"検証不能のため BQ ロードを中止します（fail-closed）。"
            )
        ct = datetime.fromisoformat(ct_raw.replace("Z", "+00:00"))
        if ct >= suspect_after:
            r.update(status="unexpected_new_project", error_type="unexpected_new_project",
                     error_detail=f"createTime={ct_raw} >= suspect_after", script_id=None)
            suspicious += 1
            print(f"  🛑 新規プロジェクト生成の疑い: {r['spreadsheet_id']} "
                  f"({r['nickname']}) createTime={ct_raw}", file=sys.stderr)
    return suspicious


# --- BQ staging → MERGE ---
def load_merge(results: list[dict]) -> None:
    ingested = utcnow_iso()
    rows = []
    for r in results:
        row = {c: r.get(c) for c in STRING_COLS}
        row["fetched_at"] = r.get("fetched_at")
        row["ingested_at"] = ingested
        rows.append(row)
    _bq_load_ndjson(rows)

    cols = STRING_COLS + ["fetched_at", "ingested_at"]
    set_all = ", ".join(f"{c}=S.{c}" for c in cols)
    set_fail = ", ".join(f"{c}=S.{c}" for c in
                         ["report_url", "member_id", "nickname", "url_source",
                          "status", "error_type", "error_detail", "ingested_at"])
    insert_cols = ", ".join(cols)
    insert_vals = ", ".join(f"S.{c}" for c in cols)
    merge_sql = f"""
    MERGE `{TABLE_FQ}` T USING `{STAGING_FQ}` S ON T.spreadsheet_id = S.spreadsheet_id
    WHEN MATCHED AND S.status = 'ok' THEN UPDATE SET {set_all}
    WHEN MATCHED AND S.status != 'ok' AND T.status != 'ok' THEN UPDATE SET {set_fail}
    WHEN NOT MATCHED THEN INSERT ({insert_cols}) VALUES ({insert_vals})
    """
    _bq_exec(merge_sql)
    _bq_exec(f"DROP TABLE IF EXISTS `{STAGING_FQ}`")


# --- MCP 巡回結果のロード CLI ---
def _read_input(source: str) -> list[dict]:
    """巡回結果 JSON を読み込む（'-' で stdin、それ以外はファイルパス）。

    MCP の run_code 結果が JSON 文字列として二重エンコードされている場合
    （先頭が `"`）にも対応する。
    """
    raw = (sys.stdin.read() if source == "-" else Path(source).read_text(encoding="utf-8")).strip()
    if not raw:
        return []
    data = json.loads(raw)
    if isinstance(data, str):  # 二重 JSON エンコード（MCP 文字列結果）
        data = json.loads(data)
    if not isinstance(data, list):
        raise ValueError("入力は巡回結果オブジェクトの JSON 配列である必要があります。")
    for i, r in enumerate(data):
        if not isinstance(r, dict) or not r.get("spreadsheet_id") or not r.get("status"):
            raise ValueError(
                f"入力 {i} 件目が不正です（dict かつ spreadsheet_id / status が必須）: {r!r}")
    return data


def _enrich_with_metadata(results: list[dict]) -> int:
    """member_master 由来のメタと MERGE スキーマの欠損フィールドを1パスで補完する。

    member_master に無い spreadsheet_id（マスタ更新で消えた等）はメタを補完できない。
    その件数を返し、呼び出し側で警告する（silent な null 化を避ける）。
    """
    meta = {t["spreadsheet_id"]: t for t in build_targets()}
    now = utcnow_iso()
    missing = 0
    for r in results:
        m = meta.get(r["spreadsheet_id"])
        if m is None:
            missing += 1
            m = {}
        r["member_id"] = m.get("member_id")
        r["nickname"] = m.get("nickname")
        r["url_source"] = m.get("url_source")
        r["report_url"] = m.get("report_url") or \
            f"https://docs.google.com/spreadsheets/d/{r['spreadsheet_id']}/edit"
        r.setdefault("script_id", None)
        r.setdefault("editor_url", None)
        r.setdefault("error_type", None)
        r.setdefault("error_detail", None)
        r["fetched_at"] = (r.get("fetched_at") or now) if r.get("status") == "ok" else None
    return missing


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Playwright MCP の巡回結果（GAS Script ID）を BigQuery gas_bindings へ MERGE する。")
    ap.add_argument("input", help="巡回結果 JSON 配列のファイルパス（'-' で stdin から読む）")
    ap.add_argument("--dry-run", action="store_true",
                    help="BQ へ書き込まず、検証（createTime 安全装置）と集計のみ出力")
    args = ap.parse_args()

    results = _read_input(args.input)
    if not results:
        print("入力が空です。処理対象なし。")
        return 0

    missing = _enrich_with_metadata(results)
    if missing:
        print(f"  ⚠ member_master に無い spreadsheet_id が {missing} 件（メタ未補完）。"
              f"マスタ URL の更新漏れの可能性があります。", file=sys.stderr)

    # 安全装置: createTime 検証（検証不能なら例外で停止 = fail-closed）。
    # 入力 JSON には巡回セッションの開始時刻が無いため、「ロード当日 0:00 UTC 以降に
    # 作成された script は新規生成を疑う」保守的な検知フロアを用いる（過検知方向＝安全側。
    # 巡回とロードは同日運用が前提。日をまたぐ場合は前日生成分の検知漏れに注意）。
    suspect_after = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    suspicious = check_create_times(results, suspect_after)

    ok = sum(1 for r in results if r["status"] == "ok")
    print(f"結果: ok={ok} / 総数={len(results)} / 新規生成疑い={suspicious}")

    if args.dry_run:
        print("--dry-run のため BQ へは書き込みません。")
    else:
        load_merge(results)
        print(f"BQ `{TABLE_FQ}` へ MERGE 完了。")

    if suspicious:
        print("⚠ unexpected_new_project を検出。前提（全件 GAS あり）を再確認し、"
              "残りの巡回を止めてください。", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
