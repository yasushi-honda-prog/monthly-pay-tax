"""業務報告スプレッドシートのコンテナバインド GAS Script ID を巡回収集し BigQuery へ MERGE。

ローカル半手動実行ツール（Google 手動ログイン依存・CI/Cloud Run では動かない）。

Google の仕様上、スプレッドシート ID からコンテナバインドの Script ID を取得する
公開 API は存在しないため、各シートをブラウザで開いて「拡張機能 → Apps Script」を
起動し、遷移先 URL（.../projects/{SCRIPT_ID}/edit）から Script ID を抽出する。

安全装置:
  - 段階化: --limit で 1 実行あたりの処理件数を絞る（10 → 25 → 50 → 残り）。
  - MERGE: 取得済みの正常 script_id を、再取得失敗で上書きしない。
  - createTime 検知: 取得 script_id の作成時刻が巡回開始以降なら「新規空プロジェクト
    生成（unexpected_new_project）」を疑い、その実行を停止扱いにする（被害の早期検知）。

認証:
  - BigQuery I/O は `bq` CLI 経由（gcloud active account = yasushi-honda@tadakayo.jp）。
    ※ python の ADC は別アカウントを指す環境のため、ADC は使わない。
  - createTime 検証は ~/.clasprc.json の default トークン（clasp ログイン）を流用。

前提セットアップ:
  pip install playwright && python3 -m playwright install chromium

使い方:
  python3 scripts/collect_gas_bindings.py --headed --limit 10   # 初回ログイン + パイロット
  python3 scripts/collect_gas_bindings.py --limit 25            # 段階的に拡大
  python3 scripts/collect_gas_bindings.py                       # 残り全件
  python3 scripts/collect_gas_bindings.py --retry-errors        # 失敗分のみ再試行
  python3 scripts/collect_gas_bindings.py --dry-run --limit 5   # BQ 書込なし（ロジック確認）
"""
from __future__ import annotations

import argparse
import json
import os
import random
import re
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

# --- 定数 ---
PROJECT = "monthly-pay-tax"
DATASET = "pay_reports"
TABLE_FQ = f"{PROJECT}.{DATASET}.gas_bindings"           # backtick 用（クエリ）
STAGING_SHORT = "gas_bindings_staging"
STAGING_LOAD = f"{PROJECT}:{DATASET}.{STAGING_SHORT}"    # bq load 用
STAGING_FQ = f"{PROJECT}.{DATASET}.{STAGING_SHORT}"      # backtick 用

SCRIPT_DIR = Path(__file__).resolve().parent
AUTH_DIR = SCRIPT_DIR / ".gas_auth"
NDJSON_PATH = SCRIPT_DIR / ".gas_bindings_attempts.ndjson"
SHOT_DIR = SCRIPT_DIR / ".gas_screenshots"
CRAWLER_VERSION = "1.0.0"

SS_ID_RE = re.compile(r"/spreadsheets/d/([\w-]+)")
SCRIPT_ID_RE = re.compile(r"/projects/([\w-]+)")

STRING_COLS = [
    "spreadsheet_id", "report_url", "script_id", "editor_url",
    "member_id", "nickname", "url_source",
    "status", "error_type", "error_detail",
]
LOAD_SCHEMA = ",".join(
    [f"{c}:STRING" for c in STRING_COLS] + ["fetched_at:TIMESTAMP", "ingested_at:TIMESTAMP"]
)
GOTO_TIMEOUT_MS = 60_000
MENU_TIMEOUT_MS = 30_000
NEWTAB_TIMEOUT_MS = 45_000

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
    try:
        rows = _bq_query_json(
            f"SELECT spreadsheet_id, status, "
            f"FORMAT_TIMESTAMP('%Y-%m-%dT%H:%M:%SZ', fetched_at) AS fetched_at_iso "
            f"FROM `{TABLE_FQ}`"
        )
    except Exception:
        return {}
    return {r["spreadsheet_id"]: {"status": r["status"], "fetched_at_iso": r.get("fetched_at_iso")}
            for r in rows}


def select_targets(targets, existing, args) -> list[dict]:
    """スキップ規則を適用して今回処理する対象を返す。"""
    out = []
    for t in targets:
        ex = existing.get(t["spreadsheet_id"])
        if args.force:
            out.append(t)
            continue
        if ex is None:
            out.append(t)
            continue
        st = ex["status"]
        if args.retry_errors:
            if st in ("error", "pending", "auth_required"):
                out.append(t)
            continue
        if st == "ok":
            if args.refresh_older_than is not None and ex.get("fetched_at_iso"):
                try:
                    ft = datetime.fromisoformat(ex["fetched_at_iso"].replace("Z", "+00:00"))
                    if (datetime.now(timezone.utc) - ft).days >= args.refresh_older_than:
                        out.append(t)
                except Exception:
                    pass
            continue
        # ok 以外（error/pending/no_gas/unexpected_new_project）は通常実行では再試行しない
        # （no_gas / unexpected は空プロジェクト再生成リスクのため --retry-errors でも触らない）
    if args.limit is not None:
        out = out[: args.limit]
    return out


# --- Playwright 巡回 ---
def crawl_one(context, target: dict) -> dict:
    from playwright.sync_api import TimeoutError as PWTimeout

    ss_id = target["spreadsheet_id"]
    result = dict(target)
    result.update({"script_id": None, "editor_url": None,
                   "status": "error", "error_type": None, "error_detail": None,
                   "fetched_at": None})
    page = context.new_page()
    try:
        page.goto(target["report_url"], wait_until="domcontentloaded", timeout=GOTO_TIMEOUT_MS)
        if "accounts.google.com" in page.url:
            result.update(status="error", error_type="auth_required",
                          error_detail="redirected to login")
            return result
        if "/spreadsheets/d/" not in page.url:
            result.update(status="error", error_type="permission_denied",
                          error_detail=f"unexpected url: {page.url[:200]}")
            return result

        page.wait_for_selector("#docs-extensions-menu", timeout=MENU_TIMEOUT_MS)
        page.click("#docs-extensions-menu")
        item = page.get_by_role("menuitem").filter(has_text="Apps Script").first
        with context.expect_page(timeout=NEWTAB_TIMEOUT_MS) as new_info:
            item.click()
        editor = new_info.value
        try:
            editor.wait_for_url("**/projects/**", timeout=NEWTAB_TIMEOUT_MS)
            url = editor.url
        finally:
            editor.close()

        m = SCRIPT_ID_RE.search(url)
        if not m:
            result.update(status="error", error_type="parse_error",
                          error_detail=f"no script id in: {url[:200]}")
            return result
        result.update(status="ok", script_id=m.group(1), editor_url=url,
                      error_type=None, error_detail=None, fetched_at=utcnow_iso())
        return result
    except PWTimeout as e:
        result.update(status="error", error_type="ui_timeout", error_detail=str(e)[:300])
        _save_shot(page, ss_id)
        return result
    except Exception as e:  # noqa: BLE001 — 1 件失敗で止めず分類して継続
        result.update(status="error", error_type="parse_error", error_detail=str(e)[:300])
        _save_shot(page, ss_id)
        return result
    finally:
        page.close()


def _save_shot(page, ss_id: str) -> None:
    try:
        SHOT_DIR.mkdir(exist_ok=True)
        page.screenshot(path=str(SHOT_DIR / f"{ss_id}.png"))
    except Exception:
        pass


def _append_ndjson(rec: dict, status: str, error_type, final_url, duration_ms: int) -> None:
    line = {
        "attempted_at": utcnow_iso(),
        "spreadsheet_id": rec["spreadsheet_id"],
        "status": status,
        "error_type": error_type,
        "final_url": final_url,
        "duration_ms": duration_ms,
        "crawler_version": CRAWLER_VERSION,
    }
    with open(NDJSON_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(line, ensure_ascii=False) + "\n")


# --- createTime 安全装置（clasp default トークン流用） ---
def check_create_times(results: list[dict], crawl_start: datetime) -> int:
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
    except Exception as e:  # noqa: BLE001 — 安全装置が使えない場合は警告のみ
        print(f"  ⚠ createTime 検証スキップ（clasp トークン利用不可）: {e}", file=sys.stderr)
        return 0

    suspicious = 0
    for r in ok:
        try:
            proj = svc.projects().get(scriptId=r["script_id"]).execute()
            ct_raw = proj.get("createTime")
            if not ct_raw:
                continue
            ct = datetime.fromisoformat(ct_raw.replace("Z", "+00:00"))
            if ct >= crawl_start:
                r.update(status="unexpected_new_project", error_type="unexpected_new_project",
                         error_detail=f"createTime={ct_raw} >= crawl_start", script_id=None)
                suspicious += 1
                print(f"  🛑 新規プロジェクト生成の疑い: {r['spreadsheet_id']} "
                      f"({r['nickname']}) createTime={ct_raw}", file=sys.stderr)
        except Exception as e:  # noqa: BLE001
            print(f"  ⚠ createTime 取得失敗 {r['script_id']}: {e}", file=sys.stderr)
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


def _do_login() -> int:
    """ブラウザを開き、Google ログイン状態を persistent context に保存する（初回1回）。

    ログイン完了（スプレッドシート一覧への到達）を自動検知して保存・終了する。
    非対話実行（! プレフィックス）でも動くよう input は使わない。
    """
    from playwright.sync_api import sync_playwright
    AUTH_DIR.mkdir(exist_ok=True)
    print("ブラウザで yasushi-honda@tadakayo.jp にログインしてください。")
    print("ログインしてスプレッドシート一覧が表示されると、自動で保存して終了します（最大5分待機）。")
    saved = False
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            user_data_dir=str(AUTH_DIR), headless=False, locale="ja-JP",
            viewport={"width": 1280, "height": 900})
        page = ctx.new_page()
        page.goto("https://docs.google.com/spreadsheets/u/0/")
        deadline = time.time() + 300
        while time.time() < deadline:
            try:
                cur = page.url
            except Exception:
                break
            if "accounts.google.com" not in cur and "/spreadsheets" in cur:
                time.sleep(4)  # Cookie / セッションの書き込み待ち
                saved = True
                break
            time.sleep(2)
        ctx.close()
    print("ログインプロファイルを保存しました（scripts/.gas_auth/）。" if saved else
          "⚠ ログインを検知できませんでした。もう一度 --login を実行してください。", file=sys.stderr if not saved else sys.stdout)
    return 0 if saved else 1


def main() -> int:
    ap = argparse.ArgumentParser(description="Collect container-bound GAS Script IDs into BigQuery.")
    ap.add_argument("--limit", type=int, default=None, help="今回処理する未処理対象の最大件数（段階化）")
    ap.add_argument("--force", action="store_true", help="status=ok も含め全件再取得")
    ap.add_argument("--retry-errors", action="store_true", help="status=error/pending のみ再試行")
    ap.add_argument("--refresh-older-than", type=int, default=None, metavar="DAYS",
                    help="status=ok でも fetched_at が指定日数より古ければ再取得")
    ap.add_argument("--dry-run", action="store_true", help="BQ へ書き込まず NDJSON と結果出力のみ")
    ap.add_argument("--headed", action="store_true", help="ブラウザを表示（巡回をその場で見たい時）")
    ap.add_argument("--login", action="store_true",
                    help="ブラウザを開き Google ログイン済みプロファイルを保存して終了（初回1回）")
    args = ap.parse_args()

    if args.login:
        return _do_login()

    targets = build_targets()
    existing = load_existing()
    todo = select_targets(targets, existing, args)

    print(f"対象総数: {len(targets)} / 既存記録: {len(existing)} / 今回処理: {len(todo)}")
    if not todo:
        print("処理対象なし（全件取得済み or スキップ条件）。")
        return 0

    from playwright.sync_api import sync_playwright

    AUTH_DIR.mkdir(exist_ok=True)
    crawl_start = datetime.now(timezone.utc)
    results: list[dict] = []

    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            user_data_dir=str(AUTH_DIR),
            headless=not args.headed,
            locale="ja-JP",
            viewport={"width": 1280, "height": 900},
        )
        try:
            for i, t in enumerate(todo, 1):
                t0 = time.time()
                r = crawl_one(context, t)
                dur = int((time.time() - t0) * 1000)
                results.append(r)
                _append_ndjson(r, r["status"], r["error_type"], r.get("editor_url"), dur)
                mark = "✓" if r["status"] == "ok" else "✗"
                print(f"  [{i}/{len(todo)}] {mark} {t['nickname']} "
                      f"{t['spreadsheet_id'][:12]}… → {r['status']}"
                      + (f" ({r['error_type']})" if r["error_type"] else ""))
                if r["status"] == "error" and r["error_type"] == "auth_required":
                    print("  🛑 ログインが必要です。--headed で再ログインしてください。中断します。",
                          file=sys.stderr)
                    break
                time.sleep(2 + random.random() * 2)  # jitter（bot 判定回避）
        finally:
            context.close()

    suspicious = check_create_times(results, crawl_start)

    ok = sum(1 for r in results if r["status"] == "ok")
    print(f"\n結果: ok={ok} / 試行={len(results)} / 新規生成疑い={suspicious}")

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
