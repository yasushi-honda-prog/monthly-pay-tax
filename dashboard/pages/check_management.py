"""業務チェック管理表（checker/admin専用）

メンバーの補助＆立替報告を確認し、チェックステータス・メモを管理する。
"""

import json
import logging
from datetime import datetime, timezone

import pandas as pd
import streamlit as st
from google.cloud import bigquery

from lib.auth import require_checker
from lib.bq_client import get_bq_client
from lib.constants import PROJECT_ID, DATASET, CHECK_LOGS_TABLE
from lib.ui_helpers import clean_numeric_scalar, fill_empty_nickname, render_kpi, render_sidebar_year_month

logger = logging.getLogger(__name__)

# --- 認証チェック ---
email = st.session_state.get("user_email", "")
role = st.session_state.get("user_role", "")
require_checker(email, role)

st.header("業務チェック管理表")
st.caption("メンバーの補助＆立替報告を確認・管理します")

CHECK_STATUSES = ["未確認", "確認中", "確認完了", "差戻し"]
STATUS_DISPLAY = {
    "未確認": "⬜ 未確認", "確認中": "🔵 確認中",
    "確認完了": "✅ 確認完了", "差戻し": "🔴 差戻し",
}
DISPLAY_TO_STATUS = {v: k for k, v in STATUS_DISPLAY.items()}


def _is_complete(val) -> bool:
    """月締め完了判定"""
    return str(val).strip().lower() in ("true", "1", "○", "済")


# --- サイドバー（前半: 期間・ステータス）---
with st.sidebar:
    st.markdown("### ✅ 業務チェック")
    st.divider()

    selected_year, selected_month = render_sidebar_year_month(
        year_key="check_year", month_key="check_month",
    )

    st.markdown('<div class="sidebar-section-title">フィルタ</div>', unsafe_allow_html=True)
    status_filter = st.selectbox(
        "ステータス", ["すべて"] + CHECK_STATUSES, key="chk_filter",
    )


# --- データ読み込み ---
@st.cache_data(ttl=300)
def load_check_data(year: int, month: int):
    """メンバー + hojo + check_logs を結合して取得"""
    client = get_bq_client()
    query = f"""
    SELECT
        m.report_url,
        m.nickname,
        m.member_id,
        h.hours,
        h.compensation,
        h.dx_subsidy,
        h.reimbursement,
        h.total_amount,
        h.monthly_complete,
        cl.status AS check_status,
        cl.checker_email,
        cl.memo,
        cl.action_log,
        cl.updated_at AS check_updated_at
    FROM `{PROJECT_ID}.{DATASET}.members` m
    LEFT JOIN `{PROJECT_ID}.{DATASET}.v_hojo_enriched` h
        ON m.report_url = h.source_url
        AND h.year = @year AND h.month = @month
    LEFT JOIN `{CHECK_LOGS_TABLE}` cl
        ON m.report_url = cl.source_url
        AND cl.year = @year AND cl.month = @month
    WHERE m.report_url IS NOT NULL
    ORDER BY m.nickname
    """
    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter("year", "INT64", year),
            bigquery.ScalarQueryParameter("month", "INT64", month),
        ]
    )
    return client.query(query, job_config=job_config).to_dataframe()


def save_check(source_url, year, month, status, memo, checker_email, existing_log, action_desc, expected_updated_at=None):
    """チェックログを保存（MERGE + 楽観的ロック）"""
    client = get_bq_client()

    # 操作ログ追記（型安全）
    try:
        logs = json.loads(existing_log) if existing_log and pd.notna(existing_log) else []
        if not isinstance(logs, list):
            logs = []
    except (json.JSONDecodeError, TypeError):
        logs = []
    logs = [e for e in logs if isinstance(e, dict)]
    logs.append({
        "ts": datetime.now(timezone.utc).isoformat(),
        "user": checker_email,
        "action": action_desc,
    })
    new_log = json.dumps(logs, ensure_ascii=False)

    params = [
        bigquery.ScalarQueryParameter("source_url", "STRING", source_url),
        bigquery.ScalarQueryParameter("year", "INT64", year),
        bigquery.ScalarQueryParameter("month", "INT64", month),
        bigquery.ScalarQueryParameter("status", "STRING", status),
        bigquery.ScalarQueryParameter("checker_email", "STRING", checker_email),
        bigquery.ScalarQueryParameter("memo", "STRING", memo or None),
        bigquery.ScalarQueryParameter("action_log", "STRING", new_log),
    ]

    # 楽観的ロック: 既存レコードがある場合はupdated_atを検証
    if expected_updated_at is not None and pd.notna(expected_updated_at):
        params.append(bigquery.ScalarQueryParameter("expected_updated_at", "TIMESTAMP", expected_updated_at))
        query = f"""
        MERGE `{CHECK_LOGS_TABLE}` T
        USING (SELECT @source_url AS source_url, @year AS year, @month AS month) S
        ON T.source_url = S.source_url AND T.year = S.year AND T.month = S.month
        WHEN MATCHED AND T.updated_at = @expected_updated_at THEN
          UPDATE SET
            status = @status, checker_email = @checker_email, memo = @memo,
            action_log = @action_log, updated_at = CURRENT_TIMESTAMP()
        WHEN NOT MATCHED THEN
          INSERT (source_url, year, month, status, checker_email, memo, action_log, updated_at)
          VALUES (@source_url, @year, @month, @status, @checker_email, @memo, @action_log, CURRENT_TIMESTAMP())
        """
    else:
        query = f"""
        MERGE `{CHECK_LOGS_TABLE}` T
        USING (SELECT @source_url AS source_url, @year AS year, @month AS month) S
        ON T.source_url = S.source_url AND T.year = S.year AND T.month = S.month
        WHEN MATCHED THEN
          UPDATE SET
            status = @status, checker_email = @checker_email, memo = @memo,
            action_log = @action_log, updated_at = CURRENT_TIMESTAMP()
        WHEN NOT MATCHED THEN
          INSERT (source_url, year, month, status, checker_email, memo, action_log, updated_at)
          VALUES (@source_url, @year, @month, @status, @checker_email, @memo, @action_log, CURRENT_TIMESTAMP())
        """

    job_config = bigquery.QueryJobConfig(query_parameters=params)
    result = client.query(query, job_config=job_config).result()

    # 楽観的ロック競合検出
    if expected_updated_at is not None and pd.notna(expected_updated_at) and result.num_dml_affected_rows == 0:
        raise ValueError("別のチェック者が先に更新しました。ページを再読み込みしてください。")

    load_check_data.clear()


# --- データロード ---
try:
    df = load_check_data(selected_year, selected_month)
except Exception as e:
    logger.error("チェックデータ取得失敗: %s", e, exc_info=True)
    st.error(f"データ取得エラー: {e}")
    st.stop()

if df.empty:
    st.info("メンバーデータがありません")
    st.stop()

# データ加工
for col in ["hours", "compensation", "dx_subsidy", "reimbursement", "total_amount"]:
    df[f"{col}_num"] = df[col].apply(clean_numeric_scalar)
df["check_status"] = df["check_status"].fillna("未確認")
df = fill_empty_nickname(df)

# --- サイドバー（後半: メンバー選択）---
with st.sidebar:
    st.markdown('<div class="sidebar-section-title">メンバー</div>', unsafe_allow_html=True)
    member_search = st.text_input(
        "検索", key="chk_search", placeholder="名前で絞り込み...",
        label_visibility="collapsed",
    )

    all_members = sorted(df["nickname"].unique().tolist())
    if member_search:
        display_members = [m for m in all_members if member_search.lower() in m.lower()]
    else:
        display_members = all_members

    col_a, col_b = st.columns(2)
    with col_a:
        if st.button("全選択", key="chk_all", use_container_width=True):
            for m in display_members:
                st.session_state[f"chk_{m}"] = True
    with col_b:
        if st.button("全解除", key="chk_clear", use_container_width=True):
            for m in display_members:
                st.session_state[f"chk_{m}"] = False

    selected_members = []
    with st.container(height=250):
        for m in display_members:
            if st.checkbox(m, key=f"chk_{m}"):
                selected_members.append(m)

    count = len(selected_members)
    total_members = len(all_members)
    if count == 0:
        st.caption(f"全 {total_members} 名表示中")
    else:
        st.caption(f"{count} / {total_members} 名を選択中")


# --- KPIカード ---
total = len(df)
counts = df["check_status"].value_counts()

k1, k2, k3, k4, k5 = st.columns(5)
with k1:
    render_kpi("確認完了", f"{counts.get('確認完了', 0)} / {total}")
with k2:
    render_kpi("確認中", str(counts.get("確認中", 0)))
with k3:
    render_kpi("差戻し", str(counts.get("差戻し", 0)))
with k4:
    render_kpi("未確認", str(counts.get("未確認", 0)))
with k5:
    mc_done = df["monthly_complete"].apply(_is_complete).sum()
    render_kpi("月締め完了", f"{mc_done} / {total}")

# --- 進捗バー ---
completed = counts.get("確認完了", 0)
progress_val = completed / total if total > 0 else 0
st.progress(progress_val, text=f"チェック進捗: {completed}/{total} 件完了")

filtered = df.copy()
if status_filter != "すべて":
    filtered = filtered[filtered["check_status"] == status_filter]
if selected_members:
    filtered = filtered[filtered["nickname"].isin(selected_members)]

st.markdown(f'<div class="count-badge">{len(filtered)} 件</div>', unsafe_allow_html=True)


# --- 一覧テーブル（直接編集） ---
if filtered.empty:
    st.info("表示するメンバーがありません")
    st.stop()

edit_df = pd.DataFrame({
    "名前": filtered["nickname"].values,
    "時間": filtered["hours_num"].values,
    "報酬": filtered["compensation_num"].values,
    "DX補助": filtered["dx_subsidy_num"].values,
    "立替": filtered["reimbursement_num"].values,
    "総額": filtered["total_amount_num"].values,
    "月締め": filtered["monthly_complete"].apply(lambda x: "○" if _is_complete(x) else "×").values,
    "ステータス": filtered["check_status"].map(STATUS_DISPLAY).values,
    "メモ": filtered["memo"].fillna("").values,
})

edited_df = st.data_editor(
    edit_df,
    column_config={
        "ステータス": st.column_config.SelectboxColumn(
            options=list(STATUS_DISPLAY.values()), required=True,
        ),
        "メモ": st.column_config.TextColumn(max_chars=1000),
        "時間": st.column_config.NumberColumn(format="%.1f"),
        "報酬": st.column_config.NumberColumn(format="¥%d"),
        "DX補助": st.column_config.NumberColumn(format="¥%d"),
        "立替": st.column_config.NumberColumn(format="¥%d"),
        "総額": st.column_config.NumberColumn(format="¥%d"),
    },
    disabled=["名前", "時間", "報酬", "DX補助", "立替", "総額", "月締め"],
    use_container_width=True,
    hide_index=True,
    key="check_editor",
)

# 変更検出 & 一括保存
indices = filtered.index.tolist()
changes = []
for i in range(len(edit_df)):
    orig_display = edit_df.iloc[i]["ステータス"]
    orig_memo = edit_df.iloc[i]["メモ"]
    new_display = edited_df.iloc[i]["ステータス"]
    new_memo = edited_df.iloc[i]["メモ"]
    orig_status = DISPLAY_TO_STATUS.get(orig_display, orig_display)
    new_status = DISPLAY_TO_STATUS.get(new_display, new_display)

    if new_status != orig_status or new_memo != orig_memo:
        actions = []
        if new_status != orig_status:
            actions.append(f"ステータス: {orig_status} → {new_status}")
        if new_memo != orig_memo:
            actions.append("メモ更新")
        changes.append((indices[i], new_status, new_memo, actions))

if changes:
    saved = 0
    for idx, new_status, new_memo, actions in changes:
        member = filtered.loc[idx]
        try:
            save_check(
                member["report_url"], selected_year, selected_month,
                new_status, new_memo, email,
                member["action_log"], " / ".join(actions),
                expected_updated_at=member["check_updated_at"] if pd.notna(member.get("check_updated_at")) else None,
            )
            saved += 1
        except ValueError as e:
            st.error(f"競合エラー ({member['nickname']}): {e}")
            load_check_data.clear()
            st.rerun()
        except Exception as e:
            st.error(f"保存エラー ({member['nickname']}): {e}")
            load_check_data.clear()
            st.rerun()

    st.toast(f"{saved}件の変更を保存しました")
    load_check_data.clear()
    st.rerun()


# --- 操作ログ ---
st.divider()
with st.expander("操作ログを確認"):
    log_member = st.selectbox(
        "メンバー", indices,
        format_func=lambda i: filtered.loc[i, "nickname"],
        key="log_member",
    )
    log_str = filtered.loc[log_member, "action_log"]
    if pd.notna(log_str) and log_str:
        try:
            logs = json.loads(log_str)
            if logs:
                for entry in reversed(logs):
                    ts = entry.get("ts", "")[:19].replace("T", " ")
                    user = entry.get("user", "")
                    action = entry.get("action", "")
                    st.markdown(f"**{ts}** {user} — {action}")
            else:
                st.caption("操作ログはありません")
        except (json.JSONDecodeError, TypeError):
            st.caption("操作ログはありません")
    else:
        st.caption("操作ログはありません")
