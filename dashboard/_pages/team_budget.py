"""予実管理ページ (spec §6)

3 サブタブ:
- 📊 全体サマリー: 全体 KPI + 隊×月達成率ヒートマップ + 隊別累積実額ランキング
- 🏷️ 隊×月マトリクス: 隊 × 月の達成率マトリクス
- 🔍 隊ドリルダウン: 1 隊の KPI + AI 評価コメント + 業務報告詳細
"""

import logging

import altair as alt
import pandas as pd
import streamlit as st

from lib.auth import require_user
from lib.bq_client import (
    compute_current_hashes,
    load_active_teams,
    load_data,
    load_team_budget_actuals,
    load_team_monthly_eval,
)
from lib.cloud_run_client import invoke_team_eval
from lib.constants import DATASET, PROJECT_ID
from lib.team_budget_view import (
    achievement_color,
    build_matrix_df,
    classify_achievement,
    format_diff,
    format_rate,
    format_yen,
    is_outdated,
    render_ai_comment_card,
    render_kpi_row,
    summarize_actuals,
)
from lib.ui_helpers import render_sidebar_year_month

logger = logging.getLogger(__name__)

# --- 認証 ---
email = st.session_state.get("user_email", "")
role = st.session_state.get("user_role", "")
require_user(email, role)
is_admin = role == "admin"

st.header("予実管理")
st.caption(
    "隊（活動）分類ごとの月次予算と実額を比較し、AI 評価コメントを表示します。"
    " 2026/05 以降のデータが対象です。"
)

# --- サイドバー: 期間選択 ---
year, month = render_sidebar_year_month(year_key="tb_year", month_key="tb_month")

tab_overview, tab_matrix, tab_drilldown = st.tabs([
    "📊 全体サマリー", "🏷️ 隊×月マトリクス", "🔍 隊ドリルダウン",
])

# ============ 📊 全体サマリー ============

with tab_overview:
    actuals_year = load_team_budget_actuals(year, year, 1, 12)
    if not actuals_year.empty and "month" in actuals_year.columns:
        actuals_month = actuals_year[actuals_year["month"] == month]
    else:
        actuals_month = actuals_year

    st.subheader(f"{year}年{month}月 全体サマリー")
    summary = summarize_actuals(actuals_month)
    render_kpi_row(summary)

    if actuals_month.empty:
        st.info("当月のデータがありません。")
    else:
        # 隊×月達成率ヒートマップ (年内全月)
        st.subheader(f"{year}年 隊×月達成率ヒートマップ")
        if not actuals_year.empty:
            # 累積実額順で隊ソート
            team_order = (
                actuals_year.groupby("team")["actual_amount"]
                .sum().sort_values(ascending=False).index.tolist()
            )
            # classify_achievement と同じ bucket で離散色付け
            # (Codex Medium-1: continuous color scale だと rate=140 が赤寄りに
            # 補間されて classify_achievement の "warning" 黄と乖離するため修正)
            hm_df = actuals_year.dropna(subset=["achievement_rate"]).copy()
            hm_df["bucket"] = hm_df["achievement_rate"].apply(classify_achievement)
            bucket_label = {"ok": "適正(80-120%)", "warning": "注意(60-80/120-150%)",
                            "danger": "乖離大(<60/>150%)", "no_data": "データなし"}
            hm_df["bucket_label"] = hm_df["bucket"].map(bucket_label)
            heatmap = (
                alt.Chart(hm_df)
                .mark_rect()
                .encode(
                    x=alt.X("month:O", title="月"),
                    y=alt.Y("team:N", title="隊", sort=team_order),
                    color=alt.Color(
                        "bucket_label:N",
                        scale=alt.Scale(
                            domain=[bucket_label["ok"], bucket_label["warning"],
                                    bucket_label["danger"]],
                            range=["#d4edda", "#fff3cd", "#f8d7da"],
                        ),
                        title="達成率",
                    ),
                    tooltip=["team", "month", "achievement_rate",
                             "actual_amount", "budget_amount"],
                )
                .properties(height=max(200, 28 * len(team_order)))
            )
            st.altair_chart(heatmap, use_container_width=True)

        # 隊別累積実額ランキング
        st.subheader(f"{year}年 隊別累積実額ランキング (累積)")
        ranking = (
            actuals_year.groupby("team", as_index=False)
            .agg(actual_amount=("actual_amount", "sum"),
                 budget_amount=("budget_amount", "sum"))
            .sort_values("actual_amount", ascending=False)
        )
        if not ranking.empty:
            ranking_chart = (
                alt.Chart(ranking)
                .mark_bar()
                .encode(
                    x=alt.X("actual_amount:Q", title="累積実額"),
                    y=alt.Y("team:N", title="隊", sort="-x"),
                    tooltip=["team", "actual_amount", "budget_amount"],
                )
                .properties(height=max(200, 28 * len(ranking)))
            )
            budget_marker = (
                alt.Chart(ranking)
                .mark_tick(color="red", thickness=2, size=20)
                .encode(x="budget_amount:Q", y=alt.Y("team:N", sort="-x"))
            )
            st.altair_chart(ranking_chart + budget_marker, use_container_width=True)

# ============ 🏷️ 隊×月マトリクス ============

with tab_matrix:
    st.subheader(f"{year}年 隊×月マトリクス (達成率%)")
    actuals_year = load_team_budget_actuals(year, year, 1, 12)
    if actuals_year.empty:
        st.info(f"{year}年のデータがありません。")
    else:
        rate_matrix = build_matrix_df(actuals_year, value="achievement_rate")
        # セル色付けは Styler 経由
        def _style_cell(v):
            return f"background-color: {achievement_color(v)}"

        styled = rate_matrix.style.map(_style_cell).format(
            lambda v: format_rate(v) if pd.notna(v) else "⚠ 未設定"
        )
        st.dataframe(styled, use_container_width=True)
        st.caption(
            "セル色: 緑=80-120% 適正 / 黄=60-80%・120-150% 注意 / 赤=<60%・>150% 乖離大 / 灰=データなし"
        )

        # セルクリック相当の隊ジャンプ用: 隊一覧 → セッション state にセット → ドリルダウン側に渡す
        with st.expander("ドリルダウンへ移動 (隊選択)"):
            selectable_teams = sorted(rate_matrix.index.tolist())
            chosen = st.selectbox(
                "隊を選んでドリルダウンタブへ反映", [""] + selectable_teams,
                key="tb_matrix_jump_team",
            )
            if chosen:
                st.session_state["tb_selected_team"] = chosen
                st.success(f"「{chosen}」をドリルダウンタブで開けます。")

# ============ 🔍 隊ドリルダウン ============

with tab_drilldown:
    st.subheader(f"{year}年{month}月 隊ドリルダウン")
    teams = load_active_teams(year, year, month, month)
    if not teams:
        st.warning(f"{year}/{month} には active な隊がありません。")
    else:
        # マトリクスから選択された隊 (またはセッション state) を初期値に
        # session_state のスタイルキーが新 teams に含まれていない場合は事前に
        # クリアして StreamlitAPIException を避ける (Agent F6)
        if st.session_state.get("tb_drill_team") not in teams:
            st.session_state.pop("tb_drill_team", None)
        prev_team = st.session_state.get("tb_selected_team")
        default_idx = teams.index(prev_team) if prev_team in teams else 0
        team = st.selectbox("隊を選択", teams, index=default_idx, key="tb_drill_team")

        # 1 隊の集計
        actuals_team = load_team_budget_actuals(year, year, month, month)
        if not actuals_team.empty and "team" in actuals_team.columns:
            actuals_team = actuals_team[actuals_team["team"] == team]

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
                       compute_current_hashes, load_active_teams):
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
            # cache クリア + rerun で新しいコメントを表示
            # (Codex Medium-2: clear() だけだと現在の eval_row が古いまま画面に残る)
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
        # load_data は単純な query 受付なのでパラメータ化のためここで client 直接利用
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
