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
STATUS_ICONS = {"未確認": "⬜", "確認中": "🔵", "確認完了": "✅", "差戻し": "🔴"}


def _is_complete(val) -> bool:
    """月締め完了判定"""
    return str(val).strip().lower() in ("true", "1", "○", "済")


# --- サイドバー ---
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
    name_search = st.text_input(
        "名前検索", key="chk_search",
        placeholder="ニックネームで絞り込み...",
        label_visibility="collapsed",
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
if name_search:
    filtered = filtered[filtered["nickname"].str.contains(name_search, case=False, na=False)]

st.markdown(f'<div class="count-badge">{len(filtered)} 件</div>', unsafe_allow_html=True)


# --- 一覧テーブル ---
display_df = pd.DataFrame({
    "名前": filtered["nickname"],
    "時間": filtered["hours_num"],
    "報酬": filtered["compensation_num"],
    "DX補助": filtered["dx_subsidy_num"],
    "立替": filtered["reimbursement_num"],
    "総額": filtered["total_amount_num"],
    "月締め": filtered["monthly_complete"].apply(lambda x: "○" if _is_complete(x) else "×"),
    "ステータス": filtered["check_status"].apply(lambda x: f"{STATUS_ICONS.get(x, '')} {x}"),
    "担当": filtered["checker_email"].fillna(""),
    "メモ": filtered["memo"].fillna(""),
})

st.dataframe(
    display_df,
    use_container_width=True,
    hide_index=True,
    column_config={
        "時間": st.column_config.NumberColumn(format="%.1f"),
        "報酬": st.column_config.NumberColumn(format="¥%d"),
        "DX補助": st.column_config.NumberColumn(format="¥%d"),
        "立替": st.column_config.NumberColumn(format="¥%d"),
        "総額": st.column_config.NumberColumn(format="¥%d"),
    },
)


# --- メンバーチェック ---
st.divider()

if filtered.empty:
    st.info("表示するメンバーがありません")
    st.stop()

st.markdown("""<div class="check-flow-hint">
    <b>使い方:</b> 下のドロップダウンでメンバーを選択 → ステータスボタンをクリックして確認状態を更新
</div>""", unsafe_allow_html=True)

# メンバー選択 + 「次の未確認へ」ナビゲーション
unchecked_indices = [i for i in filtered.index if filtered.loc[i, "check_status"] == "未確認"]
sel_col, nav_col = st.columns([3, 1])

indices = filtered.index.tolist()
with sel_col:
    selected_idx = st.selectbox(
        "メンバーを選択", indices,
        format_func=lambda i: f"{STATUS_ICONS.get(filtered.loc[i, 'check_status'], '')} {filtered.loc[i, 'nickname']}",
        key="chk_member",
    )

with nav_col:
    st.markdown("<div style='height: 1.6rem'></div>", unsafe_allow_html=True)
    remaining = len(unchecked_indices)
    if remaining > 0:
        # 現在選択中の次の未確認を探す
        next_candidates = [i for i in unchecked_indices if i != selected_idx]
        if next_candidates and st.button(f"次の未確認へ ({remaining}件)", key="next_unchecked", use_container_width=True):
            st.session_state["chk_member"] = next_candidates[0]
            st.rerun()
    else:
        st.success("全件確認済み", icon="🎉")

member = filtered.loc[selected_idx]
src = member["report_url"]
current_status = member["check_status"]
current_memo = member["memo"] if pd.notna(member["memo"]) else ""
widget_key = f"{src}_{selected_year}_{selected_month}"
expected_ts = member["check_updated_at"] if pd.notna(member.get("check_updated_at")) else None

with st.container(border=True):
    # ヘッダー（名前 + スプレッドシートリンク）
    h1, h2 = st.columns([3, 1])
    with h1:
        st.markdown(f"### {member['nickname']}")
    with h2:
        if pd.notna(src) and src:
            st.link_button("📄 スプレッドシート", src, use_container_width=True)

    # hojoデータ表示
    d1, d2, d3, d4, d5, d6 = st.columns(6)
    with d1:
        st.metric("時間", f"{clean_numeric_scalar(member['hours']):.1f}")
    with d2:
        st.metric("報酬", f"¥{clean_numeric_scalar(member['compensation']):,.0f}")
    with d3:
        st.metric("DX補助", f"¥{clean_numeric_scalar(member['dx_subsidy']):,.0f}")
    with d4:
        st.metric("立替", f"¥{clean_numeric_scalar(member['reimbursement']):,.0f}")
    with d5:
        st.metric("総額", f"¥{clean_numeric_scalar(member['total_amount']):,.0f}")
    with d6:
        st.metric("月締め", "○" if _is_complete(member["monthly_complete"]) else "×")

    st.divider()

    # ステータス変更（ボタン式 — クリックで即座に保存）
    st.markdown('<div class="status-section-label">チェックステータス</div>', unsafe_allow_html=True)
    btn_cols = st.columns(len(CHECK_STATUSES))
    for i, status in enumerate(CHECK_STATUSES):
        with btn_cols[i]:
            is_current = status == current_status
            if st.button(
                f"{STATUS_ICONS[status]} {status}",
                key=f"btn_{status}_{widget_key}",
                disabled=is_current,
                type="primary" if is_current else "secondary",
                use_container_width=True,
            ):
                try:
                    save_check(
                        src, selected_year, selected_month,
                        status, current_memo, email,
                        member["action_log"],
                        f"ステータス: {current_status} → {status}",
                        expected_updated_at=expected_ts,
                    )
                    st.toast(f"ステータスを「{status}」に更新しました")
                    st.rerun()
                except ValueError as e:
                    st.warning(str(e))
                    load_check_data.clear()
                    st.rerun()
                except Exception as e:
                    st.error(f"更新エラー: {e}")

    # メモ
    new_memo = st.text_area("メモ", value=current_memo, key=f"me_{widget_key}", height=80, max_chars=1000)
    if st.button("メモを保存", key=f"sv_{widget_key}", use_container_width=False):
        if new_memo != current_memo:
            try:
                save_check(
                    src, selected_year, selected_month,
                    current_status, new_memo, email,
                    member["action_log"], "メモ更新",
                    expected_updated_at=expected_ts,
                )
                st.toast("メモを保存しました")
                st.rerun()
            except ValueError as e:
                st.warning(str(e))
                load_check_data.clear()
                st.rerun()
            except Exception as e:
                st.error(f"保存エラー: {e}")
        else:
            st.info("変更がありません")

    # 操作ログ
    with st.expander("操作ログ"):
        log_str = member["action_log"]
        if pd.notna(log_str) and log_str:
            try:
                logs = json.loads(log_str)
                if logs:
                    for entry in reversed(logs):
                        ts = entry.get("ts", "")[:19].replace("T", " ")
                        user = entry.get("user", "")
                        action = entry.get("action", "")
                        st.markdown(f"**{ts}** {user} - {action}")
                else:
                    st.caption("操作ログはありません")
            except (json.JSONDecodeError, TypeError):
                st.caption("操作ログはありません")
        else:
            st.caption("操作ログはありません")
