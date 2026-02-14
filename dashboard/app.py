"""タダカヨ 月次報酬ダッシュボード - エントリポイント

Streamlit OIDC認証 + BQホワイトリスト照合 → st.navigationでページルーティング。
"""

import streamlit as st

from lib.auth import get_user_email, get_user_role
from lib.styles import apply_custom_css

st.set_page_config(
    page_title="タダカヨ 月次報酬ダッシュボード",
    page_icon="📊",
    layout="wide",
)

apply_custom_css()

# --- 認証 ---
if not st.user.is_logged_in:
    st.markdown("### タダカヨ 月次報酬ダッシュボード")
    st.button("Googleでログイン", on_click=st.login)
    st.stop()

email = get_user_email()
role = get_user_role(email)

if role is None:
    st.error("アクセス権限がありません。管理者にお問い合わせください。")
    if email:
        st.caption(f"ログイン中: {email}")
    st.button("ログアウト", on_click=st.logout)
    st.stop()

# --- ページ定義 ---
common_pages = [
    st.Page("pages/dashboard.py", title="ダッシュボード", icon="📊", default=True),
    st.Page("pages/architecture.py", title="アーキテクチャ", icon="🏗️"),
    st.Page("pages/help.py", title="ヘルプ", icon="❓"),
]

checker_pages = [
    st.Page("pages/check_management.py", title="業務チェック", icon="✅"),
]

admin_pages = [
    st.Page("pages/user_management.py", title="ユーザー管理", icon="👥"),
    st.Page("pages/admin_settings.py", title="管理設定", icon="⚙️"),
]

if role == "admin":
    nav = st.navigation(common_pages + checker_pages + admin_pages)
elif role == "checker":
    nav = st.navigation(common_pages + checker_pages)
else:
    nav = st.navigation(common_pages)

# ユーザー情報をsession_stateに保存（各ページで参照）
st.session_state["user_email"] = email
st.session_state["user_role"] = role

# サイドバーにユーザー情報 + ログアウトボタン
with st.sidebar:
    st.caption(f"{email}")
    st.button("ログアウト", on_click=st.logout)

nav.run()
