"""予実管理ページ (spec §6, PR-B 4 タブ再構成 2026-06-12)

4 サブタブ:
- 📊 全体: 法人全体の予実 KPI + 月次推移
- 🏢 統括隊: 統括隊別 KPI + 統括隊×月達成率ヒートマップ + 統括隊別累積実額ランキング
- 🏷️ 隊マトリクス: 統括隊絞り込み + 隊 × 月の達成率マトリクス
- 🔍 隊ドリルダウン: 統括隊絞り込み + 1 隊の KPI + AI 評価コメント + 業務報告詳細

PR-A (BQ VIEW 改訂) と組み合わせて、非「隊」活動分類 (その他/移動/電話対応 等) は
VIEW 層で根本除外される。本ページは leader_team 列の存在を前提に統括隊集計を行う。
"""

import logging

import altair as alt
import pandas as pd
import streamlit as st

from lib.auth import require_user
from lib.bq_client import load_data
from lib.bq_client import (
    compute_current_hashes,
    get_bq_client,
    load_active_leader_teams,
    load_active_teams,
    load_leader_team_monthly_budgets,
    load_leader_team_yearly_monthly_budgets,
    load_team_budget_actuals,
    load_team_monthly_eval,
)
from lib.cloud_run_client import invoke_team_eval
from lib.constants import DATASET, PROJECT_ID, PROMPT_VERSION
from lib.fiscal_calendar import calendar_to_fiscal
from lib.team_budget_cache import (
    invalidate_team_budget_caches,
    load_other_team_budgets_cached,
    load_team_budget_cached,
)
from lib.team_budget_edit_logic import (
    DeleteConfirmState,
    OverflowConfirmState,
    compute_remaining_budget,
    overflow_amount,
    transition_on_confirm_cancel,
    transition_on_confirm_continue,
    transition_on_delete_click,
    transition_on_delete_confirm_cancel,
    transition_on_save_click,
)
from lib.team_budget_repo import (
    UpsertConflict,
    delete_team_budget,
    load_other_team_budgets_in_leader,
    upsert_team_budget,
)
from lib.gyomu_list_view import render_gyomu_list_view
from lib.team_budget_view import (
    achievement_color,
    attach_mom_columns,
    build_leader_team_matrix_df,
    build_matrix_df,
    build_monthly_trend,
    classify_achievement,
    compute_mom_delta,
    format_diff,
    format_diff_yen,
    format_mom_pt,
    format_mom_yen,
    format_rate,
    format_yen,
    is_outdated,
    render_ai_comment_card,
    render_kpi_row,
    summarize_actuals,
    summarize_by_leader_team,
)
from lib.ui_helpers import (
    fill_empty_nickname,
    render_sidebar_year_month,
    valid_years,
)

logger = logging.getLogger(__name__)

# --- bucket label / 離散色付け定義 (heatmap で共通使用) ---
_BUCKET_LABEL = {
    "ok": "適正(80-120%)",
    "warning": "注意(60-80/120-150%)",
    "danger": "乖離大(<60/>150%)",
    "no_data": "データなし",
}
_BUCKET_COLOR_RANGE = ["#d4edda", "#fff3cd", "#f8d7da"]
_LEADER_TEAM_FILTER_ALL = "全て"


# --- Issue #254 ドリルダウン業務報告詳細用 loader ---
# dashboard.py の同名関数と同じ SQL を持つ二重定義。本来は lib/bq_client.py に
# 共通化すべきだが、本 PR のスコープを #254 + #245 に絞るため次 PR で対応予定。
# (code-review #3 指摘、TODO Issue 起票候補)


@st.cache_data(ttl=21600)
def _drill_load_gyomu_with_members() -> pd.DataFrame:
    """業務報告 + メンバー結合 DF を取得 (dashboard.py 同等)"""
    query = f"""
    SELECT
        source_url,
        nickname, full_name, year, date, month, day_of_week,
        activity_category, work_category, sponsor, description,
        unit_price, work_hours, travel_distance_km, amount
    FROM `{PROJECT_ID}.{DATASET}.v_gyomu_enriched`
    WHERE year IS NOT NULL
        AND (date IS NOT NULL OR amount IS NOT NULL)
    ORDER BY year, date
    """
    return load_data(query)


@st.cache_data(ttl=21600)
def _drill_load_all_members() -> list:
    """全メンバー nickname list (dashboard.py 同等の縮小版、ドリルダウン分母用)"""
    query = f"""
    SELECT DISTINCT nickname
    FROM `{PROJECT_ID}.{DATASET}.members`
    WHERE nickname IS NOT NULL AND TRIM(nickname) != ''
    ORDER BY nickname
    """
    return load_data(query)["nickname"].tolist()


@st.cache_data(ttl=21600)
def _drill_load_name_map() -> dict[str, str]:
    """nickname → display_name 辞書 (dashboard.py 同等)"""
    query = f"""
    SELECT DISTINCT nickname, full_name
    FROM `{PROJECT_ID}.{DATASET}.members`
    WHERE nickname IS NOT NULL AND TRIM(nickname) != ''
    """
    df = load_data(query)
    result: dict[str, str] = {}
    for _, row in df.iterrows():
        nick = str(row["nickname"])
        full = str(row.get("full_name", "") or "").strip()
        result[nick] = f"{nick}（{full}）" if full else nick
    return result


def _drill_load_normalized_gyomu(name_map: dict[str, str]) -> pd.DataFrame:
    """業務報告 DF をロードし、render_gyomu_list_view 用に正規化する。
    dashboard.py の _load_normalized_gyomu_for_view と同等ロジック。

    BQ 取得失敗時は st.error 表示後、空 DF を返す (code-review #4 反映、
    st.stop だと上の集計 / AI 評価 / 月予算編集 UI まで停止する cascading
    failure になるため、業務報告詳細セクションのみ empty_message 表示に
    フォールバックする設計)。
    """
    try:
        df = _drill_load_gyomu_with_members()
    except Exception as e:
        st.error(f"業務報告データ取得エラー: {e}")
        return pd.DataFrame()
    if df.empty:
        return df
    df = fill_empty_nickname(df)
    df["year"] = valid_years(df["year"])
    df = df[df["year"].notna()]
    df["year"] = df["year"].astype(int)
    df["display_name"] = df["nickname"].map(lambda n: name_map.get(n, n))
    return df


def _infer_leader_team(actuals_month: pd.DataFrame, team: str):
    """actuals_month から指定隊の leader_team を引く (なければ None)"""
    if actuals_month.empty or "leader_team" not in actuals_month.columns:
        return None
    rows = actuals_month[actuals_month["team"] == team]
    if rows.empty:
        return None
    val = rows.iloc[0]["leader_team"]
    return val if pd.notna(val) else None


def _render_drilldown_summary(
    *,
    actuals_team: pd.DataFrame,
    actuals_team_prev: pd.DataFrame,
    year: int,
    month: int,
) -> None:
    """隊ドリルダウン「集計」セクション (Issue #257 で MoM delta 対応)。

    - 実額 / 達成率に前月比 delta を表示 (compute_mom_delta)
    - FY 初月 (month=11) は前月比省略 + caption 「FY 初月のため前月比なし」
    - 前月データなしも delta=None で省略 (st.metric が delta=None で省略表示)
    - 達成率の delta は予実差額 → 前月比達成率 に置換 (PR #259 由来の delta=format_diff を廃止)
    """
    st.markdown("### 集計")
    if actuals_team.empty:
        st.warning("当月の集計データがありません。")
        return
    row = actuals_team.iloc[0]

    # MoM 計算: FY 初月 (11 月) または前月データ空なら previous=None
    prev_data = None
    if month != 11 and not actuals_team_prev.empty:
        prev = actuals_team_prev.iloc[0]
        prev_data = {
            "actual_amount": prev["actual_amount"],
            "achievement_rate": prev["achievement_rate"],
        }
    mom = compute_mom_delta(
        current={
            "actual_amount": row["actual_amount"],
            "achievement_rate": row["achievement_rate"],
        },
        previous=prev_data,
    )

    col_b, col_a, col_r = st.columns(3)
    col_b.metric("予算", format_yen(row["budget_amount"]))
    col_a.metric(
        "実額",
        format_yen(row["actual_amount"]),
        delta=format_mom_yen(mom["actual_delta"]),
    )
    col_r.metric(
        "達成率",
        format_rate(row["achievement_rate"]),
        delta=format_mom_pt(mom["rate_delta"]),
    )
    if month == 11:
        st.caption("💡 FY 初月のため前月比なし")


def _render_team_budget_editor(
    *,
    year: int,
    month: int,
    team: str,
    actuals_month: pd.DataFrame,
    leader_team_monthly_budgets: dict,
    user_email: str,
) -> None:
    """隊×月予算の admin 編集セクション (要望 1b/2/3、spec 2026-06-13)。

    - 統括隊月予算未投入なら保存ボタン disabled (Codex 指摘 g)
    - 超過時はソフトブロック (確認ダイアログ + 続行可、Codex 指摘 l)
    - 楽観ロック競合は UpsertConflict → 画面更新誘導 (Codex 指摘 c)
    - 削除は row DELETE + 確認ダイアログ (Codex 指摘 b)
    """
    st.markdown("### 月予算編集 (admin)")

    leader = _infer_leader_team(actuals_month, team)
    if leader is None:
        st.info(
            "統括隊情報がありません。team_hierarchy への登録を確認してください。"
        )
        return

    leader_monthly_budget = (
        leader_team_monthly_budgets.get(leader)
        if leader_team_monthly_budgets else None
    )
    current_row = load_team_budget_cached(year, month, team)
    other_total = load_other_team_budgets_cached(year, month, leader, team)
    remaining = compute_remaining_budget(leader_monthly_budget, other_total)

    # ---- 参考表示 ----
    ref1, ref2, ref3 = st.columns(3)
    ref1.metric(
        "統括隊月予算",
        format_yen(leader_monthly_budget)
        if leader_monthly_budget is not None else "未投入",
    )
    ref2.metric("配下他隊合計", format_yen(other_total))
    ref3.metric(
        "残額",
        format_yen(remaining) if remaining is not None else "—",
    )
    if remaining is not None and remaining < 0:
        st.warning(
            f"⚠ 配下他隊合計が統括隊月予算を超過しています "
            f"(¥{abs(remaining):,.0f} 超)"
        )

    if leader_monthly_budget is None:
        st.warning(
            f"⚠ 統括隊「{leader}」の四半期予算が未投入です。"
            "先に統括隊四半期予算を投入してください (scripts/upload_team_budgets_quarterly.py)。"
        )
        return

    # ---- 入力 widget ----
    edit_key = f"tb_edit_{year}_{month}_{team}"
    overflow_key = f"{edit_key}_overflow"
    delete_key = f"{edit_key}_delete"

    # Issue #248 確定方針「円単位 int 統一」(Codex R9 反映、CAST(ROUND(...) AS INT64))
    # に合わせて int 化。float 表示だと UX 上 0.00 / 643729.00 となり違和感、
    # 円単位の予算管理に小数点は不要 (本田様実機検証フィードバック 2026-06-14)。
    initial_amount = (
        int(round(float(current_row.budget_amount))) if current_row else 0
    )
    new_amount = st.number_input(
        "予算金額",
        min_value=0, step=10000, value=initial_amount,
        format="%d",
        key=f"{edit_key}_amount",
    )
    new_memo = st.text_input(
        "メモ (任意)",
        value=(current_row.memo or "") if current_row else "",
        max_chars=255,
        key=f"{edit_key}_memo",
    )
    # Codex 最終レビュー指摘 c: 0 円明示と削除の区別を caption で明示
    st.caption(
        "💡 「0 円」は明示的な予算 (¥0 で達成率算出)、"
        "予算を未設定状態に戻すには「予算削除」ボタンを使用してください。"
    )

    # Issue #263: 入力中のリアルタイム超過警告 (UX 用途、cache 値で十分)。
    # 保存時の判定は _do_save 内で fresh_other を再取得して確定する。
    _input_overflow_by = overflow_amount(
        float(new_amount), other_total, leader_monthly_budget
    )
    if _input_overflow_by > 0:
        st.warning(
            f"⚠ 入力値が統括隊月予算の残額を ¥{_input_overflow_by:,.0f} "
            "超過しています。保存時に「続行確認ダイアログ」が表示されます。"
        )

    overflow_state: OverflowConfirmState = st.session_state.get(
        overflow_key, OverflowConfirmState()
    )
    delete_state: DeleteConfirmState = st.session_state.get(
        delete_key, DeleteConfirmState()
    )

    def _do_save():
        # code-review MEDIUM: overflow_state の cleanup を finally で確実に
        # (失敗時に confirmed=True が残ると次回 save で超過チェック skip する bug)
        try:
            try:
                upsert_team_budget(
                    get_bq_client(),
                    year=year, month=month, team=team,
                    budget_amount=float(new_amount),
                    memo=new_memo or None,
                    expected_version=current_row.version if current_row else None,
                    actor=user_email,
                )
            except UpsertConflict as exc:
                st.error(
                    f"⚠ 競合検知: {exc}。他の管理者が編集中の可能性があります。"
                    "画面を更新してください。"
                )
                return
            except Exception as exc:  # noqa: BLE001
                logger.exception("team_budget save failed")
                st.error(f"保存失敗: {exc}")
                return

            invalidate_team_budget_caches()
            st.success("予算を保存しました")
            prev_amount = current_row.budget_amount if current_row else None
            if prev_amount != float(new_amount):
                st.info(
                    "💡 予算が変更されたため、AI 評価コメントの再生成を推奨します"
                )
            st.rerun()
        finally:
            # 成功/失敗いずれも confirm state をクリア (失敗時の再試行は仕切り直し)
            st.session_state.pop(overflow_key, None)
            st.session_state.pop(delete_key, None)

    # ---- confirm 状態優先表示 ----
    if overflow_state.pending:
        st.error(
            f"⚠ 統括隊月予算を ¥{overflow_state.pending_overflow_by:,.0f} "
            "超過します。続行しますか？"
        )
        cy, cn = st.columns(2)
        if cy.button("続行して保存", key=f"{edit_key}_confirm_yes"):
            st.session_state[overflow_key] = (
                transition_on_confirm_continue(overflow_state)
            )
            _do_save()
        if cn.button("キャンセル", key=f"{edit_key}_confirm_no"):
            st.session_state[overflow_key] = transition_on_confirm_cancel()
            st.rerun()
    elif delete_state.pending and current_row:
        st.error(
            f"予算 ¥{current_row.budget_amount:,.0f} を削除しますか？"
        )
        dy, dn = st.columns(2)
        if dy.button("削除する", key=f"{edit_key}_delete_yes"):
            try:
                delete_team_budget(
                    get_bq_client(),
                    year=year, month=month, team=team,
                    expected_version=current_row.version,
                    actor=f"delete:{user_email}",
                )
            except UpsertConflict as exc:
                st.error(
                    f"⚠ 削除競合: {exc}。画面を更新してください。"
                )
            else:
                invalidate_team_budget_caches()
                st.session_state.pop(delete_key, None)
                st.success("予算を削除しました")
                st.info(
                    "💡 予算が削除されたため、AI 評価コメントの再生成を推奨します"
                )
                st.rerun()
        if dn.button("削除キャンセル", key=f"{edit_key}_delete_no"):
            st.session_state[delete_key] = transition_on_delete_confirm_cancel()
            st.rerun()
    else:
        # 通常: 保存 + 削除ボタン
        col_save, col_del = st.columns(2)
        if col_save.button("保存", key=f"{edit_key}_save"):
            # 保存直前に他隊合計を fresh fetch (cache 不使用、Codex 指摘 f)
            fresh_other = load_other_team_budgets_in_leader(
                get_bq_client(),
                year=year, month=month,
                leader_team=leader, exclude_team=team,
            )
            new_state, save_now = transition_on_save_click(
                current=overflow_state,
                new_amount=float(new_amount),
                new_memo=new_memo or None,
                other_total=fresh_other,
                leader_monthly_budget=leader_monthly_budget,
            )
            st.session_state[overflow_key] = new_state
            if save_now:
                _do_save()
            else:
                st.rerun()
        if current_row and col_del.button("予算削除", key=f"{edit_key}_delete_btn"):
            st.session_state[delete_key] = transition_on_delete_click()
            st.rerun()

# --- 認証 ---
email = st.session_state.get("user_email", "")
role = st.session_state.get("user_role", "")
require_user(email, role)
is_admin = role == "admin"

st.header("予実管理")
st.caption(
    "隊（活動）分類ごとの月次予算と実額を比較し、AI 評価コメントを表示します。"
    " 2026/05 以降のデータが対象です。"
    " 非「隊」活動分類 (その他/移動/電話対応 等) は本画面から除外されます (PR-A)。"
)

# --- サイドバー: 期間選択 ---
# selector は暦年のまま (PR #246 隊×月予算編集が team_budgets.year=暦年で動作するため、
# R7 回帰リスク回避)。内部で fiscal_year を導出し、全体タブ/統括隊タブの集計を
# FY ベース (11月始まり) で行う (Issue #248、Codex H1、AC13)。
year, month = render_sidebar_year_month(year_key="tb_year", month_key="tb_month")
fiscal_year, _fq = calendar_to_fiscal(year, month)

tab_overall, tab_leader, tab_matrix, tab_drilldown = st.tabs([
    "📊 全体", "🏢 統括隊", "🏷️ 隊マトリクス", "🔍 隊ドリルダウン",
])

# 共通データ取得 (タブ間で共有)。BQ 取得は cache_data でラップされており重複呼出無害。
# Issue #248: 暦年 12 ヶ月でなく FY 12 ヶ月 (年跨ぎ) を取得する (Codex H1、AC13)。
actuals_year = load_team_budget_actuals(0, 0, 0, 0, fiscal_year=fiscal_year)
if not actuals_year.empty and "month" in actuals_year.columns:
    actuals_month = actuals_year[actuals_year["month"] == month]
else:
    actuals_month = actuals_year

# Issue #248: leader_team_monthly_budgets 新テーブル参照 (fiscal_year, month) で 1 ヶ月分取得。
# 空 DataFrame の場合 (データ未投入時) は dict 空で扱い、従来通り actuals 由来の
# budget_amount にフォールバックする (隊×月予算 team_budgets は別系統で継続)。
_leader_budget_df = load_leader_team_monthly_budgets(fiscal_year, month)
if _leader_budget_df.empty:
    leader_team_monthly_budgets: dict[str, float] = {}
else:
    # NaN は truthy なため `or 0.0` で fallback できない。pd.isna で明示チェック
    leader_team_monthly_budgets = {
        str(row["leader_team"]): (
            0.0 if pd.isna(row["monthly_budget"]) else float(row["monthly_budget"])
        )
        for _, row in _leader_budget_df.iterrows()
    }
# 月予算が 1 件でも入っているなら override で集計、空なら従来通り None で集計
_lt_budget_override = leader_team_monthly_budgets if leader_team_monthly_budgets else None

# Issue #257: 前月用の統括隊月予算 override も取得し、達成率前月比の分母を当月と
# 揃える (code-review MEDIUM、evaluator 指摘の budget 基準不一致解消)。
# FY 初月 (month=11) は前月比表示なしのため取得不要。
_prev_month_for_override = month - 1 if month > 1 else 12
if month == 11:
    leader_team_monthly_budgets_prev: dict[str, float] = {}
else:
    _leader_budget_prev_df = load_leader_team_monthly_budgets(
        fiscal_year, _prev_month_for_override
    )
    if _leader_budget_prev_df.empty:
        leader_team_monthly_budgets_prev = {}
    else:
        leader_team_monthly_budgets_prev = {
            str(row["leader_team"]): (
                0.0 if pd.isna(row["monthly_budget"]) else float(row["monthly_budget"])
            )
            for _, row in _leader_budget_prev_df.iterrows()
        }
_lt_budget_override_prev = (
    leader_team_monthly_budgets_prev if leader_team_monthly_budgets_prev else None
)


# ============ 📊 全体 ============

with tab_overall:
    st.subheader(f"{year}年{month}月 全体サマリー")
    summary = summarize_actuals(actuals_month)
    # PR-Q2M: 統括隊月予算が投入されている場合は法人全体予算を上書き
    if _lt_budget_override:
        total_lt_budget = sum(leader_team_monthly_budgets.values())
        summary["total_budget"] = total_lt_budget
        summary["overall_diff"] = summary["total_actual"] - total_lt_budget
        summary["overall_rate"] = (
            (summary["total_actual"] / total_lt_budget * 100)
            if total_lt_budget > 0 else None
        )

    # Issue #257: 前月比 (MoM delta) 計算。
    # FY 初月 (month=11) または前月データなしは mom=None で delta 省略。
    # 達成率前月比は当月/前月の budget 構成が同じ前提で算出 (前月の統括隊月予算
    # override は本 PR スコープ外、actuals_prev_month の素 budget で集計)。
    prev_month_calc = month - 1 if month > 1 else 12
    if (
        month != 11
        and not actuals_year.empty
        and "month" in actuals_year.columns
    ):
        actuals_prev_month = actuals_year[actuals_year["month"] == prev_month_calc]
    else:
        actuals_prev_month = pd.DataFrame()
    if not actuals_prev_month.empty:
        summary_prev = summarize_actuals(actuals_prev_month)
        # Issue #257: 前月達成率の分母を当月と揃える (code-review MEDIUM)。
        # 前月用 _lt_budget_override_prev があれば total_budget を上書きし、
        # 前月 overall_rate を再計算 (当月の override 適用と対称構造)。
        if _lt_budget_override_prev:
            total_lt_budget_prev = sum(leader_team_monthly_budgets_prev.values())
            summary_prev["total_budget"] = total_lt_budget_prev
            summary_prev["overall_rate"] = (
                (summary_prev["total_actual"] / total_lt_budget_prev * 100)
                if total_lt_budget_prev > 0 else None
            )
        mom_overall = compute_mom_delta(
            current={
                "actual_amount": summary["total_actual"],
                "achievement_rate": summary["overall_rate"],
            },
            previous={
                "actual_amount": summary_prev["total_actual"],
                "achievement_rate": summary_prev["overall_rate"],
            },
        )
    else:
        mom_overall = None
    render_kpi_row(summary, mom=mom_overall)
    if month == 11:
        st.caption("💡 FY 初月のため前月比なし")

    if actuals_year.empty:
        st.info(f"FY{fiscal_year} のデータがありません。")
    else:
        # 月次推移 (実額 vs 予算、FY 内全月、Issue #248 で月別予算正規化)
        # Issue #248: 全体タブは新規 leader_team_monthly_budgets テーブルから
        # 月毎の予算合計を取得 (同四半期内 3 ヶ月別値、AC4)。
        st.subheader(f"FY{fiscal_year} 月次推移 (実額 vs 予算)")
        _leader_yearly_budgets = load_leader_team_yearly_monthly_budgets(fiscal_year)
        monthly_trend = build_monthly_trend(actuals_year, _leader_yearly_budgets)
        # Issue #248 Codex review C-M2 反映: x 軸を FY 順 (11→12→1→...→10) で固定。
        # build_monthly_trend が fiscal_month_order 列 (0-11) を付与済。
        trend_long = monthly_trend.melt(
            id_vars=["month", "fiscal_month_order"],
            value_vars=["actual_amount", "budget_amount"],
            var_name="metric",
            value_name="amount",
        )
        trend_long["metric_label"] = trend_long["metric"].map({
            "actual_amount": "実額",
            "budget_amount": "予算",
        })
        trend_chart = (
            alt.Chart(trend_long)
            .mark_line(point=True)
            .encode(
                x=alt.X(
                    "month:O",
                    title="月 (FY 順: 11→10)",
                    sort=alt.SortField(field="fiscal_month_order", order="ascending"),
                ),
                y=alt.Y("amount:Q", title="金額 (円)"),
                color=alt.Color(
                    "metric_label:N",
                    title="種別",
                    scale=alt.Scale(domain=["実額", "予算"], range=["#1f77b4", "#ff7f0e"]),
                ),
                tooltip=["month", "metric_label", "amount"],
            )
            .properties(height=320)
        )
        st.altair_chart(trend_chart, use_container_width=True)


# ============ 🏢 統括隊 ============

with tab_leader:
    st.subheader(f"{year}年{month}月 統括隊別サマリー")

    if actuals_month.empty:
        st.info("当月のデータがありません。")
    else:
        leader_summary = summarize_by_leader_team(actuals_month, _lt_budget_override)
        if leader_summary.empty:
            st.info("当月の統括隊データがありません。")
        else:
            # Issue #257: 前月集計を取得して attach_mom_columns で delta 列追加。
            # FY 初月 (11 月) は前月計算 skip (mom 列は None で省略表示)。
            _prev_month_calc = month - 1 if month > 1 else 12
            if (
                month != 11
                and not actuals_year.empty
                and "month" in actuals_year.columns
            ):
                _actuals_prev_for_leader = actuals_year[
                    actuals_year["month"] == _prev_month_calc
                ]
                # Issue #257: 前月集計には前月用 override を渡す (code-review MEDIUM)。
                # 当月用 _lt_budget_override を使い回すと前月予算が当月値で上書きされ、
                # 達成率前月比の分母が当月と異なり混乱の元となる。
                _leader_summary_prev = (
                    summarize_by_leader_team(
                        _actuals_prev_for_leader, _lt_budget_override_prev
                    )
                    if not _actuals_prev_for_leader.empty
                    else None
                )
            else:
                _leader_summary_prev = None
            leader_summary_with_mom = attach_mom_columns(
                leader_summary, _leader_summary_prev, key_col="leader_team",
            )

            # 統括隊別 KPI table
            display_df = leader_summary_with_mom.copy()
            display_df["予算"] = display_df["budget_amount"].apply(format_yen)
            display_df["実額"] = display_df["actual_amount"].apply(format_yen)
            display_df["達成率"] = display_df["achievement_rate"].apply(format_rate)
            display_df["差額"] = display_df["diff_amount"].apply(format_diff)
            display_df["実額前月比"] = (
                display_df["actual_delta"].apply(format_mom_yen).fillna("—")
            )
            display_df["達成率前月比"] = (
                display_df["rate_delta"].apply(format_mom_pt).fillna("—")
            )
            display_df["配下隊数"] = display_df["team_count"].astype(int)
            st.dataframe(
                display_df[[
                    "leader_team", "予算", "実額", "達成率", "差額",
                    "実額前月比", "達成率前月比", "配下隊数",
                ]]
                .rename(columns={"leader_team": "統括隊"}),
                use_container_width=True,
                hide_index=True,
            )
            if month == 11:
                st.caption("💡 FY 初月のため前月比なし")

    if actuals_year.empty:
        st.info(f"FY{fiscal_year} の統括隊データがありません。")
    else:
        # 統括隊×月 達成率ヒートマップ
        st.subheader(f"FY{fiscal_year} 統括隊×月 達成率ヒートマップ")
        leader_rate_matrix = build_leader_team_matrix_df(
            actuals_year, value="achievement_rate"
        )
        if not leader_rate_matrix.empty:
            # ヒートマップは long format で altair に渡す
            hm_df = leader_rate_matrix.reset_index().melt(
                id_vars="leader_team",
                var_name="month",
                value_name="achievement_rate",
            ).dropna(subset=["achievement_rate"])
            hm_df["bucket"] = hm_df["achievement_rate"].apply(classify_achievement)
            hm_df["bucket_label"] = hm_df["bucket"].map(_BUCKET_LABEL)
            leader_heatmap = (
                alt.Chart(hm_df)
                .mark_rect()
                .encode(
                    x=alt.X("month:O", title="月"),
                    y=alt.Y("leader_team:N", title="統括隊"),
                    color=alt.Color(
                        "bucket_label:N",
                        scale=alt.Scale(
                            domain=[_BUCKET_LABEL["ok"], _BUCKET_LABEL["warning"],
                                    _BUCKET_LABEL["danger"]],
                            range=_BUCKET_COLOR_RANGE,
                        ),
                        title="達成率",
                    ),
                    tooltip=["leader_team", "month", "achievement_rate"],
                )
                .properties(height=max(180, 32 * len(leader_rate_matrix)))
            )
            st.altair_chart(leader_heatmap, use_container_width=True)

        # 統括隊別累積実額ランキング (棒グラフ + 予算マーカー)
        # PR-Q2M: ランキングは「年累計実額」を表示。予算マーカーは team_budgets_quarterly
        # に投入された範囲でのみ意味を持つため、現状は actuals_year 由来の budget をそのまま
        # 使う (データ未投入時は ¥0 マーカーなし)。投入計画次第で本ロジックを年累計予算
        # 集計に拡張予定 (follow-up)。
        st.subheader(f"FY{fiscal_year} 統括隊別累積実額ランキング")
        leader_ranking = summarize_by_leader_team(actuals_year)
        if not leader_ranking.empty:
            ranking_chart = (
                alt.Chart(leader_ranking)
                .mark_bar()
                .encode(
                    x=alt.X("actual_amount:Q", title="累積実額 (円)"),
                    y=alt.Y("leader_team:N", title="統括隊", sort="-x"),
                    tooltip=[
                        "leader_team", "actual_amount", "budget_amount",
                        "achievement_rate", "team_count",
                    ],
                )
                .properties(height=max(180, 36 * len(leader_ranking)))
            )
            budget_marker = (
                alt.Chart(leader_ranking)
                .mark_tick(color="red", thickness=2, size=24)
                .encode(x="budget_amount:Q", y=alt.Y("leader_team:N", sort="-x"))
            )
            st.altair_chart(ranking_chart + budget_marker, use_container_width=True)
            st.caption("赤いマーカーは累積予算 (年内の予算合計)")


# ============ 🏷️ 隊マトリクス ============

with tab_matrix:
    st.subheader(f"FY{fiscal_year} 隊×月マトリクス (差額)")
    if actuals_year.empty:
        st.info(f"FY{fiscal_year} のデータがありません。")
    else:
        # 統括隊フィルタ (Issue #248: FY 12 ヶ月範囲で active 統括隊取得)
        leader_options = load_active_leader_teams(0, 0, 0, 0, fiscal_year=fiscal_year)
        filter_leader = st.selectbox(
            "統括隊で絞り込み",
            [_LEADER_TEAM_FILTER_ALL] + leader_options,
            key="tb_matrix_filter_leader",
        )
        if filter_leader != _LEADER_TEAM_FILTER_ALL and "leader_team" in actuals_year.columns:
            filtered = actuals_year[actuals_year["leader_team"] == filter_leader]
        else:
            filtered = actuals_year

        if filtered.empty:
            st.info(f"統括隊「{filter_leader}」配下の隊にデータがありません。")
        else:
            # 予算入力状況を集計: 各隊について FY 内のいずれかの月で予算が入っているか。
            # has_budget=True が 1 件でもあれば「予算あり」、ゼロなら「未登録」とする。
            # 全隊未登録だと pivot_table の dropna=True で diff_matrix が空テーブル
            # ("team" index 名と "empty" だけが表示される無言バグ) になっていた。
            budget_by_team = filtered.groupby("team")["has_budget"].any()
            unbudgeted_teams = sorted(budget_by_team[~budget_by_team].index.tolist())
            has_any_budget = bool(budget_by_team.any())

            if not has_any_budget:
                unbudgeted_list = "\n".join(f"- {t}" for t in unbudgeted_teams)
                st.warning(
                    f"🚨 「{filter_leader}」配下 {len(unbudgeted_teams)} 隊すべてに"
                    "月次予算が未登録です。\n\n"
                    "隊マトリクスは隊単位の月次予算 (team_budgets) から"
                    "達成率・差額を計算するため、予算が無いと表示できません。\n\n"
                    "**入力場所:** 隊ドリルダウンタブ → 該当隊を選択 → 月予算編集\n\n"
                    f"**未登録の隊:**\n{unbudgeted_list}"
                )
            else:
                if unbudgeted_teams:
                    unbudgeted_list = "\n".join(f"- {t}" for t in unbudgeted_teams)
                    st.info(
                        f"💡 以下 {len(unbudgeted_teams)} 隊は月次予算未登録のため、"
                        "達成率・差額が表示されません:\n"
                        f"{unbudgeted_list}\n\n"
                        "隊ドリルダウンタブから予算を入力してください。"
                    )

                # Issue #253: セル値は差額 (実額 - 予算)、セル色は達成率レンジで判定。
                # diff_matrix と rate_matrix は同じ filtered から pivot 生成するが、
                # pivot_table(aggfunc="first") は全 NaN 行/列を結果から落とす仕様のため
                # 非対称になりうる (例: budget=0 で achievement_rate が NaN、
                # diff_amount は actual_amount をそのまま持つケース)。
                # → rate_matrix で参照不能なセルは achievement_color(None) で灰色
                # にフォールバックし、凡例「灰=データなし」と一貫させる。
                diff_matrix = build_matrix_df(filtered, value="diff_amount")
                rate_matrix = build_matrix_df(filtered, value="achievement_rate")
                _no_data_bg = f"background-color: {achievement_color(None)}"

                def _color_col_by_rate(col):
                    """列ごとに、対応する達成率 (rate_matrix の同じ team/month セル)
                    でセル背景色を決定する。rate_matrix に該当セルが無ければ
                    灰色 (データなし) で表示 (Issue #253)"""
                    if col.name not in rate_matrix.columns:
                        return [_no_data_bg for _ in col.index]
                    return [
                        f"background-color: {achievement_color(rate_matrix.loc[idx, col.name])}"
                        if idx in rate_matrix.index
                        else _no_data_bg
                        for idx in col.index
                    ]

                styled = (
                    diff_matrix.style
                    .apply(_color_col_by_rate, axis=0)
                    .format(lambda v: format_diff_yen(v) if pd.notna(v) else "⚠ 未設定")
                )
                st.dataframe(styled, use_container_width=True)
                st.caption(
                    "セル値: 差額 = 実額 - 予算 / セル色: 達成率で判定 (緑=80-120% 適正 / "
                    "黄=60-80%・120-150% 注意 / 赤=<60%・>150% 乖離大 / 灰=データなし)"
                )

                # セルクリック相当の隊ジャンプ用
                with st.expander("ドリルダウンへ移動 (隊選択)"):
                    selectable_teams = sorted(diff_matrix.index.tolist())
                    chosen = st.selectbox(
                        "隊を選んでドリルダウンタブへ反映",
                        [""] + selectable_teams,
                        key="tb_matrix_jump_team",
                    )
                    if chosen:
                        st.session_state["tb_selected_team"] = chosen
                        st.success(f"「{chosen}」をドリルダウンタブで開けます。")


# ============ 🔍 隊ドリルダウン ============

with tab_drilldown:
    st.subheader(f"{year}年{month}月 隊ドリルダウン")
    all_teams = load_active_teams(year, year, month, month)
    if not all_teams:
        st.warning(f"{year}/{month} には active な隊がありません。")
    else:
        # Issue #254: 上部 selector を横並び (統括隊 + 隊)
        sel_col1, sel_col2, _spacer = st.columns([2, 3, 5])
        with sel_col1:
            leader_options = load_active_leader_teams(year, year, month, month)
            drill_filter_leader = st.selectbox(
                "統括隊で絞り込み",
                [_LEADER_TEAM_FILTER_ALL] + leader_options,
                key="tb_drilldown_filter_leader",
            )
        if (
            drill_filter_leader != _LEADER_TEAM_FILTER_ALL
            and not actuals_month.empty
            and "leader_team" in actuals_month.columns
        ):
            filtered_teams = sorted(
                actuals_month[actuals_month["leader_team"] == drill_filter_leader]["team"]
                .dropna().unique().tolist()
            )
            teams = [t for t in all_teams if t in filtered_teams]
        else:
            teams = all_teams

        if not teams:
            st.info(f"統括隊「{drill_filter_leader}」配下の active な隊がありません。")
        else:
            # session_state のスタイルキーが新 teams に含まれていない場合は事前に
            # クリアして StreamlitAPIException を避ける (Agent F6)
            if st.session_state.get("tb_drill_team") not in teams:
                st.session_state.pop("tb_drill_team", None)
            prev_team = st.session_state.get("tb_selected_team")
            default_idx = teams.index(prev_team) if prev_team in teams else 0
            with sel_col2:
                team = st.selectbox(
                    "隊を選択", teams, index=default_idx, key="tb_drill_team",
                )

            # Issue #254: 2 カラム横分割 (左=集計+AI評価 / 右=月予算編集+業務報告詳細)
            col_left, col_right = st.columns([1, 1])

            with col_left:
                # 1 隊の集計 (期間内 actuals_month から抽出)
                if not actuals_month.empty and "team" in actuals_month.columns:
                    actuals_team = actuals_month[actuals_month["team"] == team]
                else:
                    actuals_team = actuals_month

                # Issue #257: 前月データ抽出 (actuals_year を月フィルタで流用、
                # 追加 BQ 呼び出しなし)。FY 初月 (11 月) は _render_drilldown_summary
                # 側で previous=None 扱いするので、ここでは prev_month を素直に算出。
                prev_month_calc = month - 1 if month > 1 else 12
                if (
                    not actuals_year.empty
                    and "month" in actuals_year.columns
                    and "team" in actuals_year.columns
                ):
                    actuals_team_prev = actuals_year[
                        (actuals_year["month"] == prev_month_calc)
                        & (actuals_year["team"] == team)
                    ]
                else:
                    actuals_team_prev = pd.DataFrame()

                _render_drilldown_summary(
                    actuals_team=actuals_team,
                    actuals_team_prev=actuals_team_prev,
                    year=year,
                    month=month,
                )

                # AI 評価コメント
                st.markdown("### AI 評価コメント")
                eval_df = load_team_monthly_eval(year, month, team=team)
                eval_row = eval_df.iloc[0].to_dict() if not eval_df.empty else None

                current = compute_current_hashes(year, month, (team,), PROMPT_VERSION)
                stored = eval_row.get("actual_data_hash") if eval_row else None
                outdated = is_outdated(stored, current.get(team))

                def _clear_team_eval_cache():
                    """予実管理関連の cache のみクリア (Codex Low-1: 全 cache nuke を回避)"""
                    for fn in (load_team_monthly_eval, load_team_budget_actuals,
                               compute_current_hashes, load_active_teams,
                               load_active_leader_teams):
                        try:
                            fn.clear()
                        except AttributeError:
                            pass

                def _on_update():
                    with st.spinner("Vertex AI Gemini で評価生成中... (約 30 秒)"):
                        try:
                            result = invoke_team_eval(
                                year=year, month=month, teams=[team], force=False,
                            )
                            s = result.get("summary", {})
                            st.success(
                                f"評価生成完了 (generated={s.get('generated', 0)}"
                                f" skipped_hash={s.get('skipped_hash_match', 0)}"
                                f" failed={s.get('failed', 0)})"
                            )
                        except Exception as exc:  # noqa: BLE001
                            logger.exception("invoke_team_eval failed")
                            st.error(f"評価生成失敗: {exc}")
                            return
                    _clear_team_eval_cache()
                    st.rerun()

                def _on_force_update():
                    with st.spinner("Vertex AI Gemini で強制再生成中... (約 30 秒)"):
                        try:
                            result = invoke_team_eval(
                                year=year, month=month, teams=[team], force=True,
                            )
                            s = result.get("summary", {})
                            st.success(f"強制再生成完了 (generated={s.get('generated', 0)})")
                        except Exception as exc:  # noqa: BLE001
                            logger.exception("invoke_team_eval force failed")
                            st.error(f"強制再生成失敗: {exc}")
                            return
                    _clear_team_eval_cache()
                    st.rerun()

                render_ai_comment_card(
                    eval_row,
                    outdated=outdated,
                    is_admin=is_admin,
                    on_update=_on_update,
                    on_force_update=_on_force_update,
                    key_suffix=f"{year}-{month}-{team}",
                )

            with col_right:
                # 月予算編集 (admin 限定、Issue #244 / spec 2026-06-13)
                if is_admin:
                    _render_team_budget_editor(
                        year=year, month=month, team=team,
                        actuals_month=actuals_month,
                        leader_team_monthly_budgets=leader_team_monthly_budgets,
                        user_email=email,
                    )

            # 業務報告詳細 (Issue #254 + #245 統合: render_gyomu_list_view 呼出に置換)
            # 本田様実機 FB (2026-06-14): 2 カラム右側に置くと列幅不足で見づらいため
            # 2 カラムの外 (下段) にフル幅で配置、compact=False で URL/隊分類列も表示
            st.markdown("### 業務報告詳細")
            _drill_name_map = _drill_load_name_map()
            _drill_df_gyomu = _drill_load_normalized_gyomu(_drill_name_map)
            _drill_all_members = _drill_load_all_members()
            # safe-refactor HIGH #1 反映: key_prefix に team を含めることで
            # 隊切替時の widget key 衝突 (StreamlitAPIException) を防ぐ
            render_gyomu_list_view(
                df_gyomu_all=_drill_df_gyomu,
                name_map=_drill_name_map,
                all_members=_drill_all_members,
                selected_members=[],
                selected_year=year,
                selected_month=f"{month}月",
                key_prefix=f"drilldown_{team}",
                fixed_activity_category=team,
                compact=False,
                empty_message=f"{year}年{month}月 「{team}」の業務報告はありません",
            )
