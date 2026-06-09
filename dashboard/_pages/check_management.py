"""業務チェック管理表（checker/admin専用）

メンバーの補助＆立替報告を確認し、チェックステータス・メモを管理する。
"""

import json
import logging
from datetime import datetime, timezone

import pandas as pd
import streamlit as st
from google.cloud import bigquery

import google.auth.transport.requests
import google.oauth2.id_token
import requests as _requests

from lib.auth import require_checker
from lib.bq_client import get_bq_client
from lib.constants import PROJECT_ID, DATASET, CHECK_LOGS_TABLE, COLLECTOR_URL
from lib.ui_helpers import clean_numeric_scalar, render_kpi, render_sidebar_year_month

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
    "確認完了": "✅ 確認完了", "差戻し": "🔶 個別確認",
}
DISPLAY_TO_STATUS = {v: k for k, v in STATUS_DISPLAY.items()}


def _derive_status(check1: bool, check2: bool, indiv: bool) -> str:
    """チェックボックス3値からステータスを導出"""
    if indiv:
        return "差戻し"
    if check2:
        return "確認完了"
    if check1:
        return "確認中"
    return "未確認"


def _is_complete(val) -> bool:
    """月締め完了判定"""
    return str(val).strip().lower() in ("true", "1", "○", "済")


# --- サイドバー（前半: 期間・ステータス）---
with st.sidebar:
    selected_year, selected_month = render_sidebar_year_month(
        year_key="check_year", month_key="check_month",
    )

    st.markdown('<div class="sidebar-section-title">フィルタ</div>', unsafe_allow_html=True)
    # 表示名→内部値マップ（「差戻し」を「個別確認」として表示）
    _filter_opts = {"すべて": "すべて"} | {STATUS_DISPLAY[s]: s for s in CHECK_STATUSES}
    _filter_display = st.selectbox(
        "ステータス", list(_filter_opts.keys()), key="chk_filter",
    )
    status_filter = _filter_opts[_filter_display]


# --- データ読み込み ---
@st.cache_data(ttl=300)
def load_check_data(year: int, month: int):
    """メンバー + hojo + check_logs を結合して取得"""
    client = get_bq_client()
    query = f"""
    SELECT
        m.report_url,
        m.nickname,
        m.full_name,
        m.member_id,
        h.hours,
        h.compensation,
        h.dx_subsidy,
        h.reimbursement,
        h.total_amount,
        h.monthly_complete,
        h.dx_receipt,
        h.expense_receipt,
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
# nicknameが空の場合はfull_nameをフォールバックに使用
df["nickname"] = df["nickname"].fillna("").apply(lambda x: x.strip() if x else "")
df["full_name"] = df["full_name"].fillna("").apply(lambda x: x.strip() if x else "")
df.loc[df["nickname"] == "", "nickname"] = df.loc[df["nickname"] == "", "full_name"]
df.loc[df["nickname"] == "", "nickname"] = "(未設定)"

# --- サイドバー（後半: メンバー選択）---
with st.sidebar:
    st.markdown('<div class="sidebar-section-title">メンバー</div>', unsafe_allow_html=True)
    member_search = st.text_input(
        "検索", key="chk_search", placeholder="名前で絞り込み...",
        label_visibility="collapsed",
    )

    all_members = sorted(df["nickname"].unique().tolist())
    _nick_to_full = dict(zip(df["nickname"], df["full_name"]))
    nick_to_label = {
        m: (f"{m}（{_nick_to_full[m]}）" if _nick_to_full.get(m, "").strip() else m)
        for m in all_members
    }
    if member_search:
        _q = member_search.lower()
        display_members = [
            m for m in all_members
            if _q in m.lower() or _q in _nick_to_full.get(m, "").lower()
        ]
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
            if st.checkbox(nick_to_label.get(m, m), key=f"chk_{m}"):
                selected_members.append(m)

    count = len(selected_members)
    total_members = len(all_members)
    if count == 0:
        st.caption(f"全 {total_members} 名表示中")
    else:
        st.caption(f"{count} / {total_members} 名を選択中")


# --- チェック対象の特定（金額あり OR エラー値あり）---
# エラー値を持つメンバーのセット
_err_check_cols = ["hours", "compensation", "dx_subsidy", "reimbursement", "total_amount"]
_has_error_nick = set()
for _, _row in df.iterrows():
    for _col in _err_check_cols:
        if str(_row.get(_col, "") or "").strip().startswith("#"):
            _has_error_nick.add(_row["nickname"])
            break

# チェック対象 = 金額あり OR エラー値あり
_check_target = df[
    (df["total_amount_num"] > 0) |
    (df["nickname"].isin(_has_error_nick))
]
target_total = len(_check_target)
target_counts = _check_target["check_status"].value_counts()

# --- KPIカード ---
total = len(df)
counts = df["check_status"].value_counts()

k1, k2, k3, k4, k5 = st.columns(5)
with k1:
    render_kpi("確認完了", f"{target_counts.get('確認完了', 0)} / {target_total}")
with k2:
    render_kpi("確認中", str(target_counts.get("確認中", 0)))
with k3:
    render_kpi("個別確認", str(target_counts.get("差戻し", 0)))
with k4:
    render_kpi("未確認", str(target_counts.get("未確認", 0)))
with k5:
    mc_done = df["monthly_complete"].apply(_is_complete).sum()
    render_kpi("当月入力完了", f"{mc_done} / {total}")

# --- 進捗バー ---
completed = target_counts.get("確認完了", 0)
progress_val = completed / target_total if target_total > 0 else 0
st.progress(progress_val, text=f"チェック進捗: {completed}/{target_total} 件完了（チェック対象のみ）")

# --- 未締め確認（金額あり・当月入力完了チェックなし）---
_mishinme = df[
    (df["total_amount_num"] > 0) &
    (~df["monthly_complete"].apply(_is_complete))
].copy()
if not _mishinme.empty:
    with st.expander(
        f"⚠️ 未締め確認（補助＆立替シートに金額あり・当月入力未完了）　{len(_mishinme)} 名",
        expanded=False,
    ):
        st.caption(
            "補助＆立替シートに金額が入力されているにも関わらず、"
            "「当月入力完了」チェックボックスがオフのメンバーです。"
        )
        _mishinme_display = _mishinme[["nickname", "full_name", "report_url", "total_amount_num",
                                       "compensation_num", "dx_subsidy_num", "reimbursement_num"]].rename(columns={
            "nickname": "メンバー",
            "full_name": "本名",
            "report_url": "URL",
            "total_amount_num": "総額",
            "compensation_num": "報酬",
            "dx_subsidy_num": "DX補助",
            "reimbursement_num": "立替",
        })
        st.dataframe(
            _mishinme_display.style.format({c: "¥{:,.0f}" for c in ["総額", "報酬", "DX補助", "立替"]}),
            column_config={"URL": st.column_config.LinkColumn(display_text="開く")},
            hide_index=True,
            use_container_width=True,
        )

# --- エラー値検出（#REF! / #VALUE! 等）---
_err_cols = {
    "hours": "時間", "compensation": "報酬",
    "dx_subsidy": "DX補助", "reimbursement": "立替", "total_amount": "合計金額",
}
_err_rows = []
for _, row in df.iterrows():
    for col, label in _err_cols.items():
        val = str(row.get(col, "") or "").strip()
        if val.startswith("#"):
            _err_rows.append({
                "メンバー": row["nickname"],
                "本名": row.get("full_name", ""),
                "URL": row.get("report_url", ""),
                "項目": label,
                "エラー値": val,
            })

if _err_rows:
    _err_df = pd.DataFrame(_err_rows)
    with st.expander(
        f"🔴 データエラー検出（#REF! / #VALUE! 等）　{_err_df['メンバー'].nunique()} 名",
        expanded=True,
    ):
        st.caption(
            "補助＆立替シートの金額欄にエラー値（#REF!、#VALUE! 等）が含まれているメンバーです。"
            "シートの数式を確認してください。"
        )
        st.dataframe(
            _err_df,
            column_config={"URL": st.column_config.LinkColumn(display_text="開く")},
            hide_index=True,
            use_container_width=True,
        )

filtered = df.copy()
if status_filter != "すべて":
    filtered = filtered[filtered["check_status"] == status_filter]
if selected_members:
    filtered = filtered[filtered["nickname"].isin(selected_members)]

_total_filtered = len(filtered)
filtered_display = filtered

# フレーム高さセレクタ
# "全行（スクロール不要）"は行数に応じて動的に計算
_HEIGHT_SENTINEL = "FULL"
_height_opts = {
    "自動": None,
    "25行分": 870,
    "50行分": 1720,
    "100行分": 3420,
    "全行（スクロール不要）": _HEIGHT_SENTINEL,
}
_col_cnt, _col_ht, _col_sp = st.columns([2, 2, 3])
with _col_cnt:
    st.markdown(f'<div class="count-badge">{_total_filtered} 件</div>', unsafe_allow_html=True)
with _col_ht:
    _ht_label = st.selectbox(
        "表示行数",
        list(_height_opts.keys()),
        index=0,
        key="chk_frame_height",
        label_visibility="collapsed",
    )
_raw_height = _height_opts[_ht_label]
# 全行表示：1行≈35px + ヘッダー50px
_editor_height = (_total_filtered * 35 + 50) if _raw_height == _HEIGHT_SENTINEL else _raw_height


# --- 一覧テーブル（直接編集） ---
if filtered.empty:
    st.info("表示するメンバーがありません")
    st.stop()

edit_df = pd.DataFrame({
    "名前": filtered_display["nickname"].values,
    "URL": filtered_display["report_url"].values,
    "時間": filtered_display["hours_num"].values,
    "報酬": filtered_display["compensation_num"].values,
    "DX補助": filtered_display["dx_subsidy_num"].values,
    "立替": filtered_display["reimbursement_num"].values,
    "総額": filtered_display["total_amount_num"].values,
    "当月入力完了": filtered_display["monthly_complete"].apply(lambda x: "○" if _is_complete(x) else "").values,
    "DX領収書": filtered_display["dx_receipt"].fillna("").values,
    "立替領収書": filtered_display["expense_receipt"].fillna("").values,
    "第一弾確認": filtered_display["check_status"].apply(lambda s: s in ["確認中", "確認完了"]).values,
    "第二弾確認": filtered_display["check_status"].apply(lambda s: s == "確認完了").values,
    "個別確認": filtered_display["check_status"].apply(lambda s: s == "差戻し").values,
    "メモ": filtered_display["memo"].fillna("").values,
})

edited_df = st.data_editor(
    edit_df,
    column_config={
        "URL": st.column_config.LinkColumn(display_text="開く"),
        "第一弾確認": st.column_config.CheckboxColumn("第一弾確認", help="第一弾確認者がチェック"),
        "第二弾確認": st.column_config.CheckboxColumn("第二弾確認", help="第二弾確認者がチェック"),
        "個別確認": st.column_config.CheckboxColumn("個別確認", help="個別確認が必要な場合にチェック"),
        "メモ": st.column_config.TextColumn(max_chars=1000),
        "時間": st.column_config.NumberColumn(format="%.1f"),
        "報酬": st.column_config.NumberColumn(format="¥%d"),
        "DX補助": st.column_config.NumberColumn(format="¥%d"),
        "立替": st.column_config.NumberColumn(format="¥%d"),
        "総額": st.column_config.NumberColumn(format="¥%d"),
    },
    disabled=["名前", "URL", "時間", "報酬", "DX補助", "立替", "総額", "当月入力完了", "DX領収書", "立替領収書"],
    use_container_width=True,
    hide_index=True,
    key="check_editor",
    **({"height": _editor_height} if _editor_height else {}),
)

# 変更検出 & 一括保存
indices = filtered_display.index.tolist()
changes = []
for i in range(len(edit_df)):
    orig_status = _derive_status(
        bool(edit_df.iloc[i]["第一弾確認"]),
        bool(edit_df.iloc[i]["第二弾確認"]),
        bool(edit_df.iloc[i]["個別確認"]),
    )
    orig_memo = edit_df.iloc[i]["メモ"]
    new_status = _derive_status(
        bool(edited_df.iloc[i]["第一弾確認"]),
        bool(edited_df.iloc[i]["第二弾確認"]),
        bool(edited_df.iloc[i]["個別確認"]),
    )
    new_memo = edited_df.iloc[i]["メモ"]

    if new_status != orig_status or new_memo != orig_memo:
        actions = []
        if new_status != orig_status:
            actions.append(f"ステータス: {STATUS_DISPLAY[orig_status]} → {STATUS_DISPLAY[new_status]}")
        if new_memo != orig_memo:
            actions.append("メモ更新")
        changes.append((indices[i], new_status, new_memo, actions))

if changes:
    saved = 0
    for idx, new_status, new_memo, actions in changes:
        member = filtered_display.loc[idx]
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
    # 最終保存者をデフォルト選択
    def _latest_log_ts(log_str):
        if not log_str or not pd.notna(log_str):
            return ""
        try:
            logs = json.loads(log_str)
            if logs and isinstance(logs, list):
                return max((e.get("ts", "") for e in logs if isinstance(e, dict)), default="")
        except (json.JSONDecodeError, TypeError):
            pass
        return ""
    _log_ts_map = {i: _latest_log_ts(filtered.loc[i, "action_log"]) for i in indices}
    _best_ts = max(_log_ts_map.values(), default="")
    _default_log_idx = max(_log_ts_map, key=lambda i: _log_ts_map[i]) if _best_ts else None

    log_member = st.selectbox(
        "メンバー", indices,
        index=indices.index(_default_log_idx) if _default_log_idx is not None else None,
        format_func=lambda i: filtered.loc[i, "nickname"],
        placeholder="選択してください",
        key="log_member",
    )
    if log_member is None:
        log_str = None
    else:
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


# --- データ更新（手動） ---
with st.expander("データ更新（手動）"):
    st.caption("スプレッドシートの最新データをBigQueryに反映します。通常は毎朝6時に自動更新されます。約4分かかります。")
    if st.button("データを今すぐ更新する", type="secondary"):
        with st.spinner("更新中です。約4分かかります..."):
            try:
                _auth_req = google.auth.transport.requests.Request()
                _token = google.oauth2.id_token.fetch_id_token(_auth_req, COLLECTOR_URL)
                _resp = _requests.post(
                    COLLECTOR_URL,
                    headers={"Authorization": f"Bearer {_token}"},
                    timeout=1800,
                )
                if _resp.status_code == 200:
                    st.success("更新が完了しました")
                else:
                    st.error(f"更新に失敗しました（HTTP {_resp.status_code}）")
            except Exception as e:
                logger.error("手動更新エラー: %s", e, exc_info=True)
                st.error(f"更新エラー: {e}")
