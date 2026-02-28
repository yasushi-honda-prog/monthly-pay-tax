"""管理設定ページ（管理者のみ）"""

from datetime import timezone, timedelta

import streamlit as st
from google.cloud import bigquery

JST = timezone(timedelta(hours=9))

from lib.auth import require_admin, clear_role_cache
from lib.bq_client import get_bq_client, load_data
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

tables = ["gyomu_reports", "hojo_reports", "members", "withholding_targets", "dashboard_users"]

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
