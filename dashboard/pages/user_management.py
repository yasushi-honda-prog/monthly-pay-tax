"""ユーザー管理ページ（管理者のみ）"""

import re
from typing import Optional

import streamlit as st
from google.cloud import bigquery

from lib.auth import require_admin, clear_role_cache
from lib.bq_client import get_bq_client
from lib.constants import USERS_TABLE, INITIAL_ADMIN_EMAIL

# --- 認証チェック ---
email = st.session_state.get("user_email", "")
role = st.session_state.get("user_role", "")
require_admin(email, role)

st.header("ユーザー管理")
st.caption("ダッシュボードにアクセスできるユーザーを管理します")


# --- ユーザー一覧取得 ---
def load_users():
    client = get_bq_client()
    query = f"""
    SELECT email, role, display_name, added_by, created_at, updated_at
    FROM `{USERS_TABLE}`
    ORDER BY created_at
    """
    return client.query(query).to_dataframe()


EMAIL_PATTERN = re.compile(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$')
ALLOWED_DOMAIN = "tadakayo.jp"


def validate_email(addr: str) -> Optional[str]:
    """メールアドレスを検証。エラーメッセージを返す（Noneなら有効）。"""
    if not addr or not EMAIL_PATTERN.match(addr):
        return "有効なメールアドレスを入力してください"
    if not addr.endswith(f"@{ALLOWED_DOMAIN}"):
        return f"{ALLOWED_DOMAIN}ドメインのメールアドレスのみ登録できます"
    return None


def add_user(new_email: str, new_role: str, display_name: str):
    """ユーザーを追加（MERGE文で原子的に重複チェック + 挿入）"""
    client = get_bq_client()
    merge_query = f"""
    MERGE `{USERS_TABLE}` T
    USING (SELECT @email AS email) S
    ON T.email = S.email
    WHEN NOT MATCHED THEN
      INSERT (email, role, display_name, added_by, created_at, updated_at)
      VALUES (@email, @role, @display_name, @added_by, CURRENT_TIMESTAMP(), CURRENT_TIMESTAMP())
    """
    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter("email", "STRING", new_email),
            bigquery.ScalarQueryParameter("role", "STRING", new_role),
            bigquery.ScalarQueryParameter("display_name", "STRING", display_name or None),
            bigquery.ScalarQueryParameter("added_by", "STRING", email),
        ]
    )
    result = client.query(merge_query, job_config=job_config).result()
    if result.num_dml_affected_rows == 0:
        return False, "このメールアドレスは既に登録されています"
    return True, "ユーザーを追加しました"


def delete_user(target_email: str):
    """ユーザーを削除"""
    if target_email == INITIAL_ADMIN_EMAIL:
        return False, "初期管理者は削除できません"
    if target_email == email:
        return False, "自分自身は削除できません"

    client = get_bq_client()
    delete_query = f"""
    DELETE FROM `{USERS_TABLE}` WHERE email = @email
    """
    job_config = bigquery.QueryJobConfig(
        query_parameters=[bigquery.ScalarQueryParameter("email", "STRING", target_email)]
    )
    client.query(delete_query, job_config=job_config).result()
    clear_role_cache()
    return True, "ユーザーを削除しました"


def update_display_name(target_email: str, new_name: str):
    """表示名を変更"""
    client = get_bq_client()
    update_query = f"""
    UPDATE `{USERS_TABLE}`
    SET display_name = @display_name, updated_at = CURRENT_TIMESTAMP()
    WHERE email = @email
    """
    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter("display_name", "STRING", new_name or None),
            bigquery.ScalarQueryParameter("email", "STRING", target_email),
        ]
    )
    client.query(update_query, job_config=job_config).result()
    return True, "表示名を変更しました"


def update_role(target_email: str, new_role: str):
    """ロールを変更"""
    if target_email == INITIAL_ADMIN_EMAIL and new_role != "admin":
        return False, "初期管理者のロールは変更できません"

    client = get_bq_client()
    update_query = f"""
    UPDATE `{USERS_TABLE}`
    SET role = @role, updated_at = CURRENT_TIMESTAMP()
    WHERE email = @email
    """
    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter("role", "STRING", new_role),
            bigquery.ScalarQueryParameter("email", "STRING", target_email),
        ]
    )
    client.query(update_query, job_config=job_config).result()
    clear_role_cache()
    return True, "ロールを変更しました"


# --- ユーザー追加フォーム ---
st.subheader("ユーザー追加")
with st.form("add_user_form"):
    col1, col2, col3 = st.columns([3, 1, 2])
    with col1:
        new_email = st.text_input("メールアドレス", placeholder="user@tadakayo.jp")
    with col2:
        new_role = st.selectbox("ロール", ["viewer", "checker", "admin"])
    with col3:
        display_name = st.text_input("表示名（任意）", placeholder="ニックネーム")

    submitted = st.form_submit_button("追加", use_container_width=True)
    if submitted:
        cleaned_email = new_email.strip().lower()
        validation_error = validate_email(cleaned_email)
        if validation_error:
            st.error(validation_error)
        else:
            success, msg = add_user(cleaned_email, new_role, display_name.strip())
            if success:
                st.success(msg)
                st.rerun()
            else:
                st.error(msg)


# --- ユーザー一覧 ---
st.subheader("登録ユーザー一覧")
try:
    df_users = load_users()
except Exception as e:
    st.error(f"ユーザー一覧の取得に失敗しました: {e}")
    st.stop()

if df_users.empty:
    st.info("登録ユーザーがいません")
else:
    for idx, row in df_users.iterrows():
        with st.container(border=True):
            c1, c2, c3 = st.columns([4, 1, 1])
            with c1:
                name_col, edit_col = st.columns([6, 1])
                with name_col:
                    label = row["email"]
                    if row["display_name"]:
                        label = f"{row['display_name']} ({row['email']})"
                    st.markdown(f"**{label}**")
                with edit_col:
                    with st.popover("✏️"):
                        edited_name = st.text_input(
                            "表示名",
                            value=row["display_name"] or "",
                            key=f"name_{row['email']}",
                            placeholder="表示名を入力",
                        )
                        if st.button("保存", key=f"save_name_{row['email']}"):
                            new_name = edited_name.strip()
                            if new_name != (row["display_name"] or ""):
                                success, msg = update_display_name(row["email"], new_name)
                                if success:
                                    st.success(msg)
                                    st.rerun()
                            else:
                                st.info("変更がありません")
                st.caption(f"追加者: {row['added_by']} | {row['created_at'].strftime('%Y-%m-%d')}")
            with c2:
                is_initial = row["email"] == INITIAL_ADMIN_EMAIL
                if is_initial:
                    st.markdown(f"🔒 **{row['role']}**")
                else:
                    current_role = row["role"]
                    role_options = ["admin", "checker", "viewer"]
                    new_r = st.selectbox(
                        "ロール",
                        role_options,
                        index=role_options.index(current_role) if current_role in role_options else 2,
                        key=f"role_{row['email']}",
                        label_visibility="collapsed",
                    )
                    if new_r != current_role:
                        success, msg = update_role(row["email"], new_r)
                        if success:
                            st.rerun()
                        else:
                            st.error(msg)
            with c3:
                is_self = row["email"] == email
                can_delete = not is_initial and not is_self
                if can_delete:
                    if st.button("削除", key=f"del_{row['email']}", type="secondary"):
                        success, msg = delete_user(row["email"])
                        if success:
                            st.success(msg)
                            st.rerun()
                        else:
                            st.error(msg)
