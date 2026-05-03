"""ユーザー管理ページ（管理者のみ）"""

import re
from typing import Optional

import pandas as pd
import streamlit as st
from google.cloud import bigquery

from lib.auth import require_admin, clear_role_cache
from lib.bq_client import get_bq_client
from lib.constants import (
    USERS_TABLE,
    INITIAL_ADMIN_EMAIL,
    GROUPS_MASTER_TABLE,
    MEMBERS_TABLE,
    SYNC_GROUPS_TABLE,
)

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
    SELECT email, role, display_name, added_by, source_group, created_at, updated_at
    FROM `{USERS_TABLE}`
    ORDER BY created_at
    """
    return client.query(query).to_dataframe()


def load_groups_master():
    """groups_masterテーブルからグループ一覧を取得"""
    client = get_bq_client()
    query = f"""
    SELECT group_email, group_name
    FROM `{GROUPS_MASTER_TABLE}`
    ORDER BY group_name
    """
    return client.query(query).to_dataframe()


def load_group_members(group_email: str):
    """指定グループに所属するメンバーのgws_accountを取得"""
    client = get_bq_client()
    query = f"""
    SELECT DISTINCT gws_account, nickname, full_name
    FROM `{MEMBERS_TABLE}`
    WHERE gws_account IS NOT NULL
      AND gws_account != ''
      AND CONCAT(',', `groups`, ',') LIKE CONCAT('%,', @group_email, ',%')
    ORDER BY nickname
    """
    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter("group_email", "STRING", group_email)
        ]
    )
    return client.query(query, job_config=job_config).to_dataframe()


def add_users_by_group(members_df, role: str, group_email: str, progress_callback=None):
    """グループメンバーを一括登録（既存ユーザーはスキップ）"""
    # ループ前に sync_groups を冪等登録：途中失敗してもユーザー追加分が
    # 「未登録グループ」扱いになり翌朝バッチで取り残される事故を防ぐ
    register_sync_group(group_email, email)
    client = get_bq_client()
    added = 0
    total = len(members_df)
    for i, (_, row) in enumerate(members_df.iterrows()):
        gws = row["gws_account"]
        display = row["nickname"] or row["full_name"] or ""
        merge_query = f"""
        MERGE `{USERS_TABLE}` T
        USING (SELECT @email AS email) S
        ON T.email = S.email
        WHEN NOT MATCHED THEN
          INSERT (email, role, display_name, added_by, source_group, created_at, updated_at)
          VALUES (@email, @role, @display_name, @added_by, @source_group, CURRENT_TIMESTAMP(), CURRENT_TIMESTAMP())
        """
        job_config = bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ScalarQueryParameter("email", "STRING", gws),
                bigquery.ScalarQueryParameter("role", "STRING", role),
                bigquery.ScalarQueryParameter("display_name", "STRING", display),
                bigquery.ScalarQueryParameter("added_by", "STRING", email),
                bigquery.ScalarQueryParameter("source_group", "STRING", group_email),
            ]
        )
        result = client.query(merge_query, job_config=job_config).result()
        if result.num_dml_affected_rows > 0:
            added += 1
        if progress_callback:
            progress_callback((i + 1) / total, f"{i + 1}/{total} 処理中...")
    return added


def register_sync_group(group_email: str, updated_by: str) -> None:
    """グループ一括登録時に dashboard_sync_groups へ enabled=TRUE で MERGE

    既に登録済み（enabled の状態問わず）の場合は何もしない（管理者の OFF 設定を尊重）。
    """
    client = get_bq_client()
    merge_query = f"""
    MERGE `{SYNC_GROUPS_TABLE}` T
    USING (SELECT @group_email AS group_email) S
    ON T.group_email = S.group_email
    WHEN NOT MATCHED THEN
      INSERT (group_email, enabled, last_synced_at, updated_at, updated_by)
      VALUES (@group_email, TRUE, NULL, CURRENT_TIMESTAMP(), @updated_by)
    """
    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter("group_email", "STRING", group_email),
            bigquery.ScalarQueryParameter("updated_by", "STRING", updated_by),
        ]
    )
    client.query(merge_query, job_config=job_config).result()


def set_sync_enabled(group_email: str, enabled: bool, updated_by: str) -> None:
    """dashboard_sync_groups の enabled を切り替える（無ければ INSERT）"""
    client = get_bq_client()
    merge_query = f"""
    MERGE `{SYNC_GROUPS_TABLE}` T
    USING (SELECT @group_email AS group_email) S
    ON T.group_email = S.group_email
    WHEN MATCHED THEN
      UPDATE SET enabled = @enabled, updated_at = CURRENT_TIMESTAMP(), updated_by = @updated_by
    WHEN NOT MATCHED THEN
      INSERT (group_email, enabled, last_synced_at, updated_at, updated_by)
      VALUES (@group_email, @enabled, NULL, CURRENT_TIMESTAMP(), @updated_by)
    """
    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter("group_email", "STRING", group_email),
            bigquery.ScalarQueryParameter("enabled", "BOOL", enabled),
            bigquery.ScalarQueryParameter("updated_by", "STRING", updated_by),
        ]
    )
    client.query(merge_query, job_config=job_config).result()


def load_sync_groups_overview():
    """同期設定済みグループ + 既存ユーザー数 + グループ存続確認を一覧で取得

    Returns DataFrame with columns:
        group_email, enabled, last_synced_at, updated_at, updated_by,
        group_name (NULL if deleted), user_count (dashboard_users source_group由来), is_orphaned
    """
    client = get_bq_client()
    query = f"""
    WITH user_counts AS (
      SELECT source_group AS group_email, COUNT(*) AS user_count
      FROM `{USERS_TABLE}`
      WHERE source_group IS NOT NULL
      GROUP BY source_group
    )
    SELECT
      sg.group_email,
      sg.enabled,
      sg.last_synced_at,
      sg.updated_at,
      sg.updated_by,
      gm.group_name,
      COALESCE(uc.user_count, 0) AS user_count,
      gm.group_email IS NULL AS is_orphaned
    FROM `{SYNC_GROUPS_TABLE}` sg
    LEFT JOIN `{GROUPS_MASTER_TABLE}` gm USING (group_email)
    LEFT JOIN user_counts uc USING (group_email)
    ORDER BY sg.enabled DESC, COALESCE(gm.group_name, sg.group_email)
    """
    return client.query(query).to_dataframe()


def is_user_in_group(user_email: str, group_email: str) -> bool:
    """指定ユーザーが指定グループに所属しているかを members.groups から判定

    members テーブルは Cloud Run の毎朝バッチで WRITE_TRUNCATE 更新されるため、
    前回バッチ後に追加されたユーザーは判定漏れる可能性がある（自グループ OFF 警告は
    ベストエフォート）。
    """
    client = get_bq_client()
    query = f"""
    SELECT COUNT(*) AS cnt
    FROM `{MEMBERS_TABLE}`
    WHERE gws_account = @user_email
      AND CONCAT(',', `groups`, ',') LIKE CONCAT('%,', @group_email, ',%')
    """
    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter("user_email", "STRING", user_email),
            bigquery.ScalarQueryParameter("group_email", "STRING", group_email),
        ]
    )
    rows = list(client.query(query, job_config=job_config).result())
    return rows[0].cnt > 0 if rows else False


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
      INSERT (email, role, display_name, added_by, source_group, created_at, updated_at)
      VALUES (@email, @role, @display_name, @added_by, NULL, CURRENT_TIMESTAMP(), CURRENT_TIMESTAMP())
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


def filter_users(df, role_filter: str, group_filter: str):
    """ユーザー一覧 DataFrame にロール・グループフィルタを適用して返す

    role_filter: "全て" / "admin" / "checker" / "viewer" / "user"
    group_filter: "全て" / "(個別登録のみ)" / 具体的な source_group メール
    """
    result = df.copy()
    if role_filter != "全て":
        result = result[result["role"] == role_filter]
    if group_filter == "(個別登録のみ)":
        result = result[result["source_group"].isna()]
    elif group_filter != "全て":
        result = result[result["source_group"] == group_filter]
    return result


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


# --- グループ一括登録 ---
st.subheader("グループ一括登録")
st.caption("Googleグループを選択してメンバーを一括登録します")

try:
    df_groups = load_groups_master()
except Exception as e:
    st.error(f"グループ一覧の取得に失敗しました: {e}")
    df_groups = None

if df_groups is not None and not df_groups.empty:
    group_options = {
        f"{row['group_name']} ({row['group_email']})": row["group_email"]
        for _, row in df_groups.iterrows()
    }
    with st.form("group_add_form"):
        col_g1, col_g2 = st.columns([3, 1])
        with col_g1:
            selected_label = st.selectbox("グループ", list(group_options.keys()))
        with col_g2:
            group_role = st.selectbox("ロール", ["user", "viewer", "checker", "admin"], key="group_role")

        selected_group_email = group_options[selected_label] if selected_label else None

        group_submitted = st.form_submit_button("メンバーをプレビュー", use_container_width=True)

    if group_submitted and selected_group_email:
        st.session_state["group_preview_email"] = selected_group_email
        st.session_state["group_preview_role"] = group_role

    if st.session_state.get("group_preview_email"):
        preview_email = st.session_state["group_preview_email"]
        preview_role = st.session_state["group_preview_role"]
        df_members = load_group_members(preview_email)
        if df_members.empty:
            st.warning("このグループに所属するメンバーが見つかりません")
        else:
            st.info(f"対象メンバー: {len(df_members)}名（ロール: {preview_role}）")
            st.dataframe(
                df_members[["gws_account", "nickname", "full_name"]],
                use_container_width=True,
                hide_index=True,
            )
            col_exec, col_cancel = st.columns(2)
            with col_exec:
                if st.button("一括登録を実行", type="primary", use_container_width=True):
                    progress_bar = st.progress(0, text="登録処理を開始しています...")
                    added = add_users_by_group(
                        df_members, preview_role, preview_email,
                        progress_callback=lambda pct, text: progress_bar.progress(pct, text=text),
                    )
                    progress_bar.progress(1.0, text="完了!")
                    del st.session_state["group_preview_email"]
                    del st.session_state["group_preview_role"]
                    st.success(f"{added}名を新規登録しました（既存ユーザーはスキップ）")
                    st.rerun()
            with col_cancel:
                if st.button("キャンセル", use_container_width=True):
                    del st.session_state["group_preview_email"]
                    del st.session_state["group_preview_role"]
                    st.rerun()
else:
    st.info("グループマスターが未登録です")

st.divider()

# --- グループ自動同期 ON/OFF ---
st.subheader("グループ自動同期 ON/OFF")
st.caption(
    "グループ一括登録したグループの自動同期（毎朝6時のバッチでメンバー増減を反映）を切り替えます。"
    " OFFにしてもユーザーアクセス権は維持されます（凍結）。アクセスを止めるには下の「登録ユーザー一覧」から個別削除してください。"
)

try:
    df_sync = load_sync_groups_overview()
except Exception as e:
    st.error(f"同期設定の取得に失敗しました: {e}")
    df_sync = None

if df_sync is None or df_sync.empty:
    st.info("同期設定済みグループはありません。「グループ一括登録」を実行すると自動でON状態で登録されます。")
else:
    # 自グループ OFF 確認ダイアログ
    @st.dialog("自分の所属グループを OFF にしますか？")
    def _confirm_self_group_off(group_email: str, group_label: str):
        st.warning(
            f"あなたが所属するグループ **{group_label}** の自動同期を OFF にします。"
            " このグループから抜けてもダッシュボードには残り続けますが、新規メンバーの自動取込も止まります。"
        )
        col_ok, col_cancel = st.columns(2)
        with col_ok:
            if st.button("OFF にする", type="primary", use_container_width=True, key="self_off_ok"):
                set_sync_enabled(group_email, False, email)
                st.success(f"{group_label} を OFF にしました")
                st.rerun()
        with col_cancel:
            if st.button("キャンセル", use_container_width=True, key="self_off_cancel"):
                st.rerun()

    _self_off_target = st.session_state.pop("self_off_target", None)
    if _self_off_target is not None:
        _confirm_self_group_off(_self_off_target[0], _self_off_target[1])

    # ヘッダ
    h1, h2, h3, h4, h5 = st.columns([4, 1, 2, 2, 1])
    with h1:
        st.markdown("**グループ**")
    with h2:
        st.markdown("**同期**")
    with h3:
        st.markdown("**最終同期**")
    with h4:
        st.markdown("**登録済ユーザー**")
    with h5:
        st.markdown("**操作**")

    for _, row in df_sync.iterrows():
        with st.container(border=True):
            c1, c2, c3, c4, c5 = st.columns([4, 1, 2, 2, 1])
            with c1:
                label = row["group_name"] or row["group_email"]
                if row["is_orphaned"]:
                    st.markdown(f"⚠️ **{label}** (グループ削除済み)")
                else:
                    st.markdown(f"**{label}**")
                st.caption(row["group_email"])
            with c2:
                if row["enabled"]:
                    st.markdown("🟢 **ON**")
                else:
                    st.markdown("⚪ **OFF**")
            with c3:
                if row["last_synced_at"] is not None and not pd.isna(row["last_synced_at"]):
                    st.caption(row["last_synced_at"].strftime("%Y-%m-%d %H:%M"))
                else:
                    st.caption("未実行")
            with c4:
                count = int(row["user_count"])
                st.caption(f"{count} 名")
            with c5:
                btn_label = "OFFにする" if row["enabled"] else "ONにする"
                btn_key = f"toggle_{row['group_email']}"
                if st.button(btn_label, key=btn_key, use_container_width=True):
                    if row["enabled"] and is_user_in_group(email, row["group_email"]):
                        # 自グループを OFF にする場合は確認ダイアログ
                        st.session_state["self_off_target"] = (
                            row["group_email"],
                            row["group_name"] or row["group_email"],
                        )
                        st.rerun()
                    else:
                        new_enabled = not row["enabled"]
                        set_sync_enabled(row["group_email"], new_enabled, email)
                        if new_enabled:
                            st.success(f"{label} を ON にしました（次回バッチで反映）")
                        else:
                            st.warning(f"{label} を OFF にしました（既存ユーザーは削除されません）")
                        st.rerun()
            if not row["enabled"]:
                st.caption("⚠️ 同期停止中: 既存ユーザーは削除されません。アクセスを停止するには個別削除してください。")
            elif row["is_orphaned"]:
                st.caption("⚠️ groups_master に存在しないグループです（GWS で削除された可能性）")

    st.caption("※ ON/OFF 切替は次回バッチ（翌朝6時 JST）で反映されます。")

st.divider()

# --- ユーザー追加フォーム ---
st.subheader("個別ユーザー追加")
with st.form("add_user_form"):
    col1, col2, col3 = st.columns([3, 1, 2])
    with col1:
        new_email = st.text_input("メールアドレス", placeholder="user@tadakayo.jp")
    with col2:
        new_role = st.selectbox("ロール", ["user", "viewer", "checker", "admin"])
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
    # --- フィルタUI ---
    role_options_filter = ["全て", "admin", "checker", "viewer", "user"]
    # source_group の選択肢: 個別登録(NULL) + 登録済みグループの distinct
    distinct_groups = sorted(df_users["source_group"].dropna().unique().tolist())
    group_options_filter = ["全て", "(個別登録のみ)"] + distinct_groups

    col_f1, col_f2 = st.columns(2)
    with col_f1:
        filter_role = st.selectbox(
            "ロールで絞り込み", role_options_filter, key="filter_role"
        )
    with col_f2:
        filter_group = st.selectbox(
            "グループで絞り込み", group_options_filter, key="filter_group"
        )

    # --- フィルタ適用 ---
    df_filtered = filter_users(df_users, filter_role, filter_group)

    st.caption(f"表示件数: {len(df_filtered)} / 全 {len(df_users)} 件")

    # --- 削除確認ダイアログ ---
    # st.dialog は ESC/×/モーダル外クリックで閉じてもコールバックが発火しないため、
    # session_state["delete_target"] はダイアログ起動時に pop（ワンショット消費）し、
    # 残置による「次回 rerun で復活」を防ぐ。
    @st.dialog("ユーザー削除の確認")
    def _confirm_delete_dialog(target_email: str, display_label: str):
        st.warning("以下のユーザーを削除します。元に戻せません。")
        st.markdown(f"- メールアドレス: **{target_email}**")
        st.markdown(f"- 表示名: **{display_label or '(未設定)'}**")
        st.caption("OKを押すと即座にBigQueryから削除されます。")

        col_ok, col_cancel = st.columns(2)
        with col_ok:
            if st.button("削除を実行（OK）", type="primary", use_container_width=True, key="dialog_delete_ok"):
                success, msg = delete_user(target_email)
                if success:
                    st.success(msg)
                else:
                    st.error(f"削除に失敗しました: {msg}（再度「削除」ボタンから操作してください）")
                st.rerun()
        with col_cancel:
            if st.button("キャンセル", use_container_width=True, key="dialog_delete_cancel"):
                st.rerun()

    # ダイアログ表示制御（ワンショット消費 — ESC/×で閉じても再表示されない）
    _delete_target = st.session_state.pop("delete_target", None)
    if _delete_target is not None:
        _target_email, _display_label = _delete_target
        _confirm_delete_dialog(_target_email, _display_label)

    if df_filtered.empty:
        st.info("該当するユーザーがいません")
    for idx, row in df_filtered.iterrows():
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
                source_info = f"追加者: {row['added_by']} | {row['created_at'].strftime('%Y-%m-%d')}"
                if row.get("source_group"):
                    source_info += f" | グループ: {row['source_group']}"
                st.caption(source_info)
            with c2:
                is_initial = row["email"] == INITIAL_ADMIN_EMAIL
                if is_initial:
                    st.markdown(f"🔒 **{row['role']}**")
                else:
                    current_role = row["role"]
                    role_options = ["admin", "checker", "viewer", "user"]
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
                        # ダイアログで確認後に delete_user を呼ぶ
                        st.session_state["delete_target"] = (
                            row["email"],
                            row["display_name"] or "",
                        )
                        st.rerun()
