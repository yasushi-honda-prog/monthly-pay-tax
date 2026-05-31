"""GAS Script ID 管理ページ（管理者のみ）

業務報告スプレッドシートのコンテナバインド Apps Script の Script ID を一元管理する。
収集は scripts/collect_gas_bindings.py（ログイン済みブラウザ巡回 → BQ MERGE）で行い、
本ページは閲覧専用（status 別フィルタ / 一覧 / エディタリンク / clasp clone 手順）。

読み取り専用方針: 各シートの GAS を書き換える push 機能は提供しない。
"""

import streamlit as st

from lib.auth import require_admin
from lib.bq_client import get_bq_client
from lib.constants import GAS_BINDINGS_TABLE, MEMBER_MASTER_TABLE

# --- 認証チェック ---
email = st.session_state.get("user_email", "")
role = st.session_state.get("user_role", "")
require_admin(email, role)

st.header("GAS Script ID 管理")
st.caption("業務報告スプレッドシートのコンテナバインド Apps Script を一元管理します（閲覧専用）")


def load_bindings():
    """gas_bindings を status 優先 + member_id 順で取得"""
    client = get_bq_client()
    query = f"""
    SELECT spreadsheet_id, report_url, script_id, editor_url,
           member_id, nickname, url_source, status, error_type, error_detail, fetched_at
    FROM `{GAS_BINDINGS_TABLE}`
    ORDER BY
      CASE status
        WHEN 'ok' THEN 0
        WHEN 'no_gas' THEN 1
        WHEN 'unexpected_new_project' THEN 2
        ELSE 3
      END,
      member_id
    """
    return client.query(query).to_dataframe()


def count_targets() -> int:
    """member_master の有効 report_url（url_1 + url_2）から巡回対象の総数を算出"""
    client = get_bq_client()
    query = f"""
    SELECT COUNT(DISTINCT sid) AS n FROM (
      SELECT REGEXP_EXTRACT(report_url_1, r'/spreadsheets/d/([\\w-]+)') AS sid
      FROM `{MEMBER_MASTER_TABLE}`
      WHERE report_url_1 IS NOT NULL AND report_url_1 != ''
      UNION DISTINCT
      SELECT REGEXP_EXTRACT(report_url_2, r'/spreadsheets/d/([\\w-]+)')
      FROM `{MEMBER_MASTER_TABLE}`
      WHERE report_url_2 IS NOT NULL AND report_url_2 != ''
    )
    WHERE sid IS NOT NULL
    """
    rows = list(client.query(query).result())
    return int(rows[0].n) if rows else 0


try:
    df = load_bindings()
except Exception as e:  # noqa: BLE001
    st.error(f"GAS Script ID 一覧の取得に失敗しました: {e}")
    st.stop()

try:
    total_targets = count_targets()
    targets_failed = False
except Exception:  # noqa: BLE001
    total_targets = 0
    targets_failed = True

# --- メトリクス ---
n_ok = int((df["status"] == "ok").sum()) if not df.empty else 0
n_error = int((df["status"] == "error").sum()) if not df.empty else 0
n_no_gas = int((df["status"] == "no_gas").sum()) if not df.empty else 0
n_suspicious = int((df["status"] == "unexpected_new_project").sum()) if not df.empty else 0
collected_ids = df["spreadsheet_id"].nunique() if not df.empty else 0
n_remaining = max(total_targets - collected_ids, 0)

m1, m2, m3, m4, m5 = st.columns(5)
m1.metric("巡回対象", "—" if targets_failed else total_targets)
m2.metric("取得済 (ok)", n_ok)
m3.metric("エラー", n_error)
m4.metric("GAS無し", n_no_gas)
m5.metric("未巡回", "—" if targets_failed else n_remaining)

if targets_failed:
    st.warning(
        "巡回対象数の取得に失敗しました（BQ 接続を確認してください）。"
        "「巡回対象」「未巡回」の値は不正確です。"
    )

if n_suspicious > 0:
    st.error(
        f"🛑 新規プロジェクト生成の疑い: {n_suspicious} 件。"
        " 巡回を停止し、対象シートに既存 GAS があるか確認してください。"
    )

st.divider()

# --- フィルタ + 一覧 ---
if df.empty:
    st.info(
        "まだ収集データがありません。"
        " `scripts/collect_gas_bindings.py`（またはログイン済みブラウザ巡回）で取得してください。"
    )
    st.stop()

status_options = ["全て"] + sorted(df["status"].dropna().unique().tolist())
fcol1, fcol2 = st.columns([1, 3])
with fcol1:
    sel_status = st.selectbox("ステータスで絞り込み", status_options)
with fcol2:
    kw = st.text_input("ニックネーム / メンバーID 検索", placeholder="部分一致")

view = df.copy()
if sel_status != "全て":
    view = view[view["status"] == sel_status]
if kw:
    kw_low = kw.strip().lower()
    # regex=False: 検索欄に [ や ( 等の正規表現記号を入れても re.error で落ちない
    view = view[
        view["nickname"].str.lower().str.contains(kw_low, regex=False, na=False)
        | view["member_id"].str.lower().str.contains(kw_low, regex=False, na=False)
    ]

st.caption(f"表示件数: {len(view)} / 全 {len(df)} 件")

st.dataframe(
    view[
        [
            "nickname", "member_id", "url_source", "status",
            "script_id", "editor_url", "report_url", "error_type", "fetched_at",
        ]
    ],
    use_container_width=True,
    hide_index=True,
    column_config={
        "nickname": "ニックネーム",
        "member_id": "メンバーID",
        "url_source": "URL種別",
        "status": "状態",
        "script_id": "Script ID",
        "editor_url": st.column_config.LinkColumn("エディタ", display_text="開く"),
        "report_url": st.column_config.LinkColumn("シート", display_text="開く"),
        "error_type": "エラー種別",
        "fetched_at": "取得日時",
    },
)

st.divider()

# --- clasp clone 手順 ---
st.subheader("clasp clone 手順")
st.caption("Script ID を選ぶと、ローカルで GAS コードを取得するコマンドを表示します。")

ok_df = df[(df["status"] == "ok") & df["script_id"].notna()]
if ok_df.empty:
    st.info("取得済みの Script ID がありません。")
else:
    options = {
        f"{row['nickname']} ({row['member_id']}) — {str(row['script_id'])[:16]}…": row["script_id"]
        for _, row in ok_df.iterrows()
    }
    sel_label = st.selectbox("対象シート", list(options.keys()))
    sel_script_id = options.get(sel_label)
    if sel_script_id:
        st.code(
            "# 事前に yasushi-honda@tadakayo.jp で clasp login 済みであること\n"
            f"clasp clone {sel_script_id}",
            language="bash",
        )
        st.caption("※ 本システムは読み取り専用方針です。`clasp push` でシート側 GAS を書き換えないでください。")
