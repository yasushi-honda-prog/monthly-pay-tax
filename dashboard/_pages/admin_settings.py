"""管理設定ページ（管理者のみ）"""

from datetime import timezone, timedelta

import streamlit as st
from google.cloud import bigquery

JST = timezone(timedelta(hours=9))

from lib.auth import require_admin, clear_role_cache
from lib.bq_client import get_bq_client, load_data
from lib.cloud_run_client import invoke_collector
from lib.constants import PROJECT_ID, DATASET, USERS_TABLE

# --- 認証チェック ---
email = st.session_state.get("user_email", "")
role = st.session_state.get("user_role", "")
require_admin(email, role)

st.header("管理設定")


# === キャッシュ制御 ===
st.subheader("キャッシュ制御")
st.markdown("ダッシュボードのデータは1時間キャッシュされます。手動でクリアできます。")

col1, col2 = st.columns(2)
with col1:
    if st.button("データキャッシュをクリア", use_container_width=True):
        st.cache_data.clear()
        st.success("データキャッシュをクリアしました")
with col2:
    if st.button("ロールキャッシュをクリア", use_container_width=True):
        clear_role_cache()
        st.success("ロールキャッシュをクリアしました（次回リロードで再取得）")


# === BQテーブル情報 ===
st.subheader("BigQuery テーブル情報")

tables = [
    "gyomu_reports", "hojo_reports", "reimbursement_items",
    "members", "member_master",
    "withholding_targets", "wam_target_projects",
    "dashboard_users", "check_logs", "groups_master",
]

try:
    client = get_bq_client()
    rows = []
    for table_name in tables:
        table_ref = f"{PROJECT_ID}.{DATASET}.{table_name}"
        try:
            table = client.get_table(table_ref)
            rows.append({
                "テーブル": table_name,
                "行数": f"{table.num_rows:,}",
                "サイズ": f"{table.num_bytes / 1024 / 1024:.1f} MB" if table.num_bytes else "-",
                "最終更新": table.modified.replace(tzinfo=timezone.utc).astimezone(JST).strftime("%Y-%m-%d %H:%M") if table.modified else "-",
            })
        except Exception:
            rows.append({
                "テーブル": table_name,
                "行数": "取得エラー",
                "サイズ": "-",
                "最終更新": "-",
            })

    import pandas as pd
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
except Exception as e:
    st.error(f"テーブル情報の取得に失敗しました: {e}")


# === ユーザー統計 ===
st.subheader("ユーザー統計")

try:
    query = f"""
    SELECT
        role,
        COUNT(*) as count
    FROM `{USERS_TABLE}`
    GROUP BY role
    """
    df_stats = load_data(query)
    if not df_stats.empty:
        col1, col2, col3 = st.columns(3)
        total = df_stats["count"].sum()
        admin_count = df_stats[df_stats["role"] == "admin"]["count"].sum()
        viewer_count = df_stats[df_stats["role"] == "viewer"]["count"].sum()
        with col1:
            st.metric("総ユーザー数", total)
        with col2:
            st.metric("管理者 (admin)", admin_count)
        with col3:
            st.metric("閲覧者 (viewer)", viewer_count)
    else:
        st.info("登録ユーザーがいません")
except Exception as e:
    st.error(f"ユーザー統計の取得に失敗しました: {e}")


# === 手動同期 ===
st.subheader("手動同期")
st.markdown(
    "Cloud Run pay-collector を直接呼び出して BigQuery を今すぐ最新化します。"
    "通常は毎朝 6 時のバッチで自動更新されます。同期完了後、上の「BigQuery テーブル情報」をリロードすると最終更新時刻を確認できます。"
)
st.warning(
    "「メイン報告」は約 5.5 分かかります（Step 1-3 + グループ情報復元）。"
    "同期中はタブを閉じず、他のボタンも押さないでください。"
)

_SYNC_BUTTONS = [
    ("メイン報告（業務 / 補助 / メンバー + グループ）", "/sync/main-reports", "main_reports", "約 5.5 分"),
    ("立替金シート", "/sync/reimbursement", "reimbursement", "約 1 分"),
    ("タダメンMマスタ", "/sync/member-master", "member_master", "数十秒"),
    ("グループ情報のみ（dashboard_users 含む）", "/update-groups", "groups", "約 2 分"),
]

for label, endpoint, btn_key, eta in _SYNC_BUTTONS:
    btn_col, eta_col = st.columns([3, 2])
    with btn_col:
        clicked = st.button(label, key=f"sync_btn_{btn_key}", use_container_width=True)
    with eta_col:
        st.caption(f"目安: {eta} / endpoint: `{endpoint}`")
    if clicked:
        with st.spinner(f"{label} を同期中..."):
            try:
                result = invoke_collector(endpoint)
                elapsed = result.get("elapsed_seconds", "?")
                # BQ 更新済みデータを dashboard が即座に表示できるよう、データキャッシュをクリア
                st.cache_data.clear()
                st.success(f"{label}: 完了（{elapsed} 秒、データキャッシュもクリア済）")
                st.json(result)
            except Exception as exc:
                st.error(f"{label}: 失敗 — {exc}")


# === システム情報 ===
st.subheader("システム情報")

st.markdown(f"""
| 項目 | 値 |
|:---|:---|
| GCPプロジェクト | `{PROJECT_ID}` |
| BQデータセット | `{DATASET}` |
| データキャッシュTTL | 1時間 |
| ログインユーザー | `{email}` |
| ロール | `{role}` |
""")
