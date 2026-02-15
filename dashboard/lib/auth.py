"""Streamlit OIDC認証 + BQホワイトリスト照合"""

from __future__ import annotations

import logging

import streamlit as st
from google.cloud import bigquery

from lib.bq_client import get_bq_client
from lib.constants import INITIAL_ADMIN_EMAIL, USERS_TABLE

logger = logging.getLogger(__name__)


def get_user_email() -> str:
    """Streamlit OIDC (st.user) からユーザーメールを取得"""
    if st.user.is_logged_in:
        return st.user.email or ""
    return ""


def _fetch_user_role(email: str) -> str | None:
    """BQからユーザーロールを取得。未登録ならNone。"""
    client = get_bq_client()
    query = f"""
    SELECT role FROM `{USERS_TABLE}`
    WHERE email = @email
    LIMIT 1
    """
    job_config = bigquery.QueryJobConfig(
        query_parameters=[bigquery.ScalarQueryParameter("email", "STRING", email)]
    )
    rows = list(client.query(query, job_config=job_config).result())
    if rows:
        return rows[0].role
    return None


def get_user_role(email: str) -> str | None:
    """ユーザーのロールを取得。session_stateにキャッシュ。BQ障害時は初期管理者のみ許可。"""
    if not email:
        return None

    cache_key = f"_user_role_{email}"
    if cache_key in st.session_state:
        return st.session_state[cache_key]

    try:
        role = _fetch_user_role(email)
    except Exception:
        logger.exception("BQ user lookup failed for %s", email)
        role = "admin" if email == INITIAL_ADMIN_EMAIL else None

    st.session_state[cache_key] = role
    return role


def clear_role_cache():
    """ロールキャッシュをクリア（ユーザー管理操作後に使用）"""
    keys_to_remove = [k for k in st.session_state if k.startswith("_user_role_")]
    for k in keys_to_remove:
        del st.session_state[k]


def require_auth() -> tuple[str, str]:
    """認証を要求。(email, role)を返す。未認証ならst.stopで停止。"""
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
        st.stop()

    return email, role


def require_admin(email: str, role: str):
    """adminロールを要求。viewerならst.stopで停止。"""
    if role != "admin":
        st.error("このページは管理者のみアクセスできます。")
        st.stop()


def require_checker(email: str, role: str):
    """checker以上のロールを要求。viewerならst.stopで停止。"""
    if role not in ("checker", "admin"):
        st.error("このページはチェック担当者のみアクセスできます。")
        st.stop()
