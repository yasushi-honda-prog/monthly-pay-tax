"""タダカヨ 活動時間・報酬マネジメントダッシュボード - エントリポイント

Streamlit OIDC認証 + BQホワイトリスト照合 → st.navigationでページルーティング。
"""

import streamlit as st

from lib.auth import get_user_email, get_user_role
from lib.styles import apply_custom_css

st.set_page_config(
    page_title="タダカヨ 活動時間・報酬マネジメントダッシュボード",
    page_icon="📊",
    layout="wide",
)

apply_custom_css()


# --- 未認証/未登録ユーザー用ページ ---
def _login_page():
    st.markdown("### タダカヨ 活動時間・報酬マネジメントダッシュボード")
    st.button("Googleでログイン", on_click=st.login)


def _no_access_page():
    st.error("アクセス権限がありません。管理者にお問い合わせください。")
    email = get_user_email()
    if email:
        st.caption(f"ログイン中: {email}")
    st.button("ログアウト", on_click=st.logout)


# --- 認証 & ページルーティング ---
# st.navigationを常に呼び出し、レガシーモードへのフォールバックを防止する
if not st.user.is_logged_in:
    nav = st.navigation([st.Page(_login_page, title="ログイン", icon="🔑", default=True)])
    nav.run()
    st.stop()

email = get_user_email()
role = get_user_role(email)

if role is None:
    nav = st.navigation([st.Page(_no_access_page, title="アクセス拒否", icon="🚫", default=True)])
    nav.run()
    st.stop()

# --- ページ定義 ---
base_pages = [
    st.Page("pages/dashboard.py", title="ダッシュボード", icon="📊", default=True),
]

checker_pages = [
    st.Page("pages/check_management.py", title="業務チェック", icon="✅"),
]

utility_pages = [
    st.Page("pages/architecture.py", title="アーキテクチャ", icon="🏗️"),
    st.Page("pages/help.py", title="ヘルプ", icon="❓"),
]

admin_pages = [
    st.Page("pages/user_management.py", title="ユーザー管理", icon="👥"),
    st.Page("pages/admin_settings.py", title="管理設定", icon="⚙️"),
]

if role == "admin":
    nav = st.navigation(base_pages + checker_pages + utility_pages + admin_pages)
elif role == "checker":
    nav = st.navigation(base_pages + checker_pages + utility_pages)
else:
    nav = st.navigation(base_pages + utility_pages)

# ユーザー情報をsession_stateに保存（各ページで参照）
st.session_state["user_email"] = email
st.session_state["user_role"] = role

nav.run()

# サイドバー下部: ブランディング + アカウント情報
with st.sidebar:
    st.divider()
    st.markdown("### 📊 タダカヨ")
    st.caption("活動時間・報酬マネジメントダッシュボード")
    st.caption(f"{email}")
    st.button("ログアウト", on_click=st.logout)
