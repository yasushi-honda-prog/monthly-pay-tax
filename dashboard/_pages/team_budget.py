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
from lib.bq_client import (
    compute_current_hashes,
    load_active_leader_teams,
    load_active_teams,
    load_leader_team_monthly_budgets,
    load_team_budget_actuals,
    load_team_monthly_eval,
)
from lib.cloud_run_client import invoke_team_eval
from lib.constants import DATASET, PROJECT_ID
from lib.team_budget_view import (
    achievement_color,
    build_leader_team_matrix_df,
    build_matrix_df,
    build_monthly_trend,
    classify_achievement,
    format_diff,
    format_rate,
    format_yen,
    is_outdated,
    render_ai_comment_card,
    render_kpi_row,
    summarize_actuals,
    summarize_by_leader_team,
)
from lib.ui_helpers import render_sidebar_year_month

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
year, month = render_sidebar_year_month(year_key="tb_year", month_key="tb_month")

tab_overall, tab_leader, tab_matrix, tab_drilldown = st.tabs([
    "📊 全体", "🏢 統括隊", "🏷️ 隊マトリクス", "🔍 隊ドリルダウン",
])

# 共通データ取得 (タブ間で共有)。BQ 取得は cache_data でラップされており重複呼出無害
actuals_year = load_team_budget_actuals(year, year, 1, 12)
if not actuals_year.empty and "month" in actuals_year.columns:
    actuals_month = actuals_year[actuals_year["month"] == month]
else:
    actuals_month = actuals_year

# PR-Q2M: 統括隊別月予算 (team_budgets_quarterly の四半期予算 / 3)。
# 空 DataFrame の場合 (データ未投入時) は dict 空で扱い、従来通り actuals
# 由来の budget_amount にフォールバックする (隊×月予算 team_budgets は別系統)。
_leader_budget_df = load_leader_team_monthly_budgets(year, month)
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
    render_kpi_row(summary)

    if actuals_year.empty:
        st.info(f"{year}年のデータがありません。")
    else:
        # 月次推移 (実額 vs 予算、年内全月)
        st.subheader(f"{year}年 月次推移 (実額 vs 予算)")
        monthly_trend = build_monthly_trend(actuals_year)
        trend_long = monthly_trend.melt(
            id_vars="month",
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
                x=alt.X("month:O", title="月"),
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
            # 統括隊別 KPI table
            display_df = leader_summary.copy()
            display_df["予算"] = display_df["budget_amount"].apply(format_yen)
            display_df["実額"] = display_df["actual_amount"].apply(format_yen)
            display_df["達成率"] = display_df["achievement_rate"].apply(format_rate)
            display_df["差額"] = display_df["diff_amount"].apply(format_diff)
            display_df["配下隊数"] = display_df["team_count"].astype(int)
            st.dataframe(
                display_df[["leader_team", "予算", "実額", "達成率", "差額", "配下隊数"]]
                .rename(columns={"leader_team": "統括隊"}),
                use_container_width=True,
                hide_index=True,
            )

    if actuals_year.empty:
        st.info(f"{year}年の統括隊データがありません。")
    else:
        # 統括隊×月 達成率ヒートマップ
        st.subheader(f"{year}年 統括隊×月 達成率ヒートマップ")
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
        st.subheader(f"{year}年 統括隊別累積実額ランキング")
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
    st.subheader(f"{year}年 隊×月マトリクス (達成率%)")
    if actuals_year.empty:
        st.info(f"{year}年のデータがありません。")
    else:
        # 統括隊フィルタ
        leader_options = load_active_leader_teams(year, year, 1, 12)
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
            rate_matrix = build_matrix_df(filtered, value="achievement_rate")

            def _style_cell(v):
                return f"background-color: {achievement_color(v)}"

            styled = rate_matrix.style.map(_style_cell).format(
                lambda v: format_rate(v) if pd.notna(v) else "⚠ 未設定"
            )
            st.dataframe(styled, use_container_width=True)
            st.caption(
                "セル色: 緑=80-120% 適正 / 黄=60-80%・120-150% 注意 / "
                "赤=<60%・>150% 乖離大 / 灰=データなし"
            )

            # セルクリック相当の隊ジャンプ用
            with st.expander("ドリルダウンへ移動 (隊選択)"):
                selectable_teams = sorted(rate_matrix.index.tolist())
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
        # 統括隊フィルタ (selectbox の隊リストを絞り込む)
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
            team = st.selectbox(
                "隊を選択", teams, index=default_idx, key="tb_drill_team",
            )

            # 1 隊の集計 (期間内 actuals_month から抽出)
            if not actuals_month.empty and "team" in actuals_month.columns:
                actuals_team = actuals_month[actuals_month["team"] == team]
            else:
                actuals_team = actuals_month

            st.markdown("### 集計")
            if actuals_team.empty:
                st.warning("当月の集計データがありません。")
            else:
                row = actuals_team.iloc[0]
                col_b, col_a, col_r = st.columns(3)
                col_b.metric("予算", format_yen(row["budget_amount"]))
                col_a.metric("実額", format_yen(row["actual_amount"]))
                col_r.metric(
                    "達成率",
                    format_rate(row["achievement_rate"]),
                    delta=format_diff(row["diff_amount"]),
                )

            # AI 評価コメント
            st.markdown("### AI 評価コメント")
            eval_df = load_team_monthly_eval(year, month, team=team)
            eval_row = eval_df.iloc[0].to_dict() if not eval_df.empty else None

            current = compute_current_hashes(year, month, (team,))
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
                        # cache_data でラップされていない場合は no-op
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
                    except Exception as exc:  # noqa: BLE001 - ユーザー向け表示
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
                    except Exception as exc:  # noqa: BLE001 - ユーザー向け表示
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

            # 業務報告詳細
            st.markdown("### 業務報告詳細")
            search_kw = st.text_input("キーワード検索 (内容・業務分類・スポンサー対象)", "")
            gyomu_sql = f"""
            SELECT
              g.date, g.work_category, g.sponsor, g.description,
              g.unit_price, g.hours, g.amount, m.full_name AS reporter
            FROM `{PROJECT_ID}.{DATASET}.gyomu_reports` g
            LEFT JOIN `{PROJECT_ID}.{DATASET}.members` m ON g.source_url = m.report_url
            WHERE SAFE_CAST(g.year AS INT64) = {int(year)}
              AND `{PROJECT_ID}.{DATASET}`.extract_month(g.date) = {int(month)}
              AND g.activity_category = @team_param
            ORDER BY g.date
            """
            try:
                from google.cloud import bigquery as _bq
                from lib.bq_client import get_bq_client as _get_client
                _cfg = _bq.QueryJobConfig(
                    query_parameters=[_bq.ScalarQueryParameter("team_param", "STRING", team)]
                )
                gyomu_df = _get_client().query(gyomu_sql, job_config=_cfg).to_dataframe()
            except Exception as exc:  # noqa: BLE001
                logger.exception("gyomu detail query failed")
                st.error(f"業務報告取得失敗: {exc}")
                gyomu_df = pd.DataFrame()

            if not gyomu_df.empty and search_kw:
                # NaN を 'nan' に str 化して誤マッチするのを避けるため na=False を渡す
                # (Agent F5)。全列に対する OR マッチ。
                mask = (
                    gyomu_df.astype(str)
                    .apply(lambda col: col.str.contains(search_kw, case=False, na=False, regex=False))
                    .any(axis=1)
                )
                gyomu_df = gyomu_df[mask]

            st.dataframe(gyomu_df, use_container_width=True, hide_index=True)
            st.caption(f"件数: {len(gyomu_df)} 件")
