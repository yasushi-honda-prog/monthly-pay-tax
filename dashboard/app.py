"""タダカヨ 月次報酬ダッシュボード - エントリポイント

Cloud IAP認証 + BQホワイトリスト照合 → st.navigationでページルーティング。
"""

import streamlit as st

from lib.auth import get_iap_user_email, get_user_role
from lib.styles import apply_custom_css

st.set_page_config(
    page_title="タダカヨ 月次報酬ダッシュボード",
    page_icon="📊",
    layout="wide",
)

apply_custom_css()

# --- 認証 ---
email = get_iap_user_email()
role = get_user_role(email)

if role is None:
    st.error("アクセス権限がありません。管理者にお問い合わせください。")
    if email:
        st.caption(f"ログイン中: {email}")
    st.stop()

# --- ページ定義 ---
common_pages = [
    st.Page("pages/dashboard.py", title="ダッシュボード", icon="📊", default=True),
    st.Page("pages/architecture.py", title="アーキテクチャ", icon="🏗️"),
    st.Page("pages/help.py", title="ヘルプ", icon="❓"),
]

admin_pages = [
    st.Page("pages/user_management.py", title="ユーザー管理", icon="👥"),
    st.Page("pages/admin_settings.py", title="管理設定", icon="⚙️"),
]

if role == "admin":
    nav = st.navigation(common_pages + admin_pages)
else:
    nav = st.navigation(common_pages)

# ユーザー情報をsession_stateに保存（各ページで参照）
st.session_state["user_email"] = email
st.session_state["user_role"] = role

nav.run()
