"""月次報酬ダッシュボード（3タブ構成）

BigQueryのpay_reportsデータセットを可視化。
BQ VIEWs (v_gyomu_enriched, v_hojo_enriched, v_monthly_compensation) 経由でデータを取得。
"""

import logging

import streamlit as st

from lib.bq_client import load_data
from lib.constants import PROJECT_ID, DATASET
from lib.ui_helpers import (
    clean_numeric_series,
    fill_empty_nickname,
    render_kpi,
    render_sidebar_year_month,
    valid_years,
)

logger = logging.getLogger(__name__)


# --- データ読み込み ---
@st.cache_data(ttl=3600)
def load_hojo_with_members():
    query = f"""
    SELECT
        nickname, full_name, year, month,
        hours, compensation, dx_subsidy, reimbursement,
        total_amount, monthly_complete
    FROM `{PROJECT_ID}.{DATASET}.v_hojo_enriched`
    WHERE year IS NOT NULL
    ORDER BY year, month
    """
    return load_data(query)


@st.cache_data(ttl=3600)
def load_monthly_compensation():
    query = f"""
    SELECT
        year, month, member_id, nickname, full_name,
        report_url,
        is_corporate, is_donation, is_licensed,
        work_hours, hour_compensation, travel_distance_km,
        distance_compensation, subtotal_compensation,
        position_rate, position_adjusted_compensation,
        qualification_allowance, qualification_adjusted_compensation,
        withholding_target_amount, withholding_tax,
        dx_subsidy, reimbursement, payment,
        donation_payment, daily_wage_count, full_day_compensation,
        total_work_hours
    FROM `{PROJECT_ID}.{DATASET}.v_monthly_compensation`
    ORDER BY year, month
    """
    return load_data(query)


@st.cache_data(ttl=3600)
def load_gyomu_with_members():
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


@st.cache_data(ttl=3600)
def load_groups_master():
    query = f"""
    SELECT group_email, group_name
    FROM `{PROJECT_ID}.{DATASET}.groups_master`
    ORDER BY group_name
    """
    return load_data(query)


@st.cache_data(ttl=3600)
def load_members_with_groups():
    query = f"""
    SELECT nickname, full_name, report_url, `groups`
    FROM `{PROJECT_ID}.{DATASET}.members`
    WHERE nickname IS NOT NULL AND TRIM(nickname) != ''
        AND `groups` IS NOT NULL AND `groups` != ''
    """
    return load_data(query)


@st.cache_data(ttl=3600)
def load_all_members():
    query = f"""
    SELECT nickname, has_empty FROM (
        SELECT DISTINCT nickname, FALSE AS has_empty FROM (
            SELECT nickname FROM `{PROJECT_ID}.{DATASET}.v_hojo_enriched`
            UNION DISTINCT
            SELECT nickname FROM `{PROJECT_ID}.{DATASET}.v_gyomu_enriched`
        )
        WHERE nickname IS NOT NULL AND TRIM(nickname) != ''
        UNION ALL
        SELECT '(未設定)' AS nickname, TRUE AS has_empty FROM (
            SELECT 1 FROM (
                SELECT nickname FROM `{PROJECT_ID}.{DATASET}.v_hojo_enriched`
                WHERE nickname IS NULL OR TRIM(nickname) = ''
                UNION ALL
                SELECT nickname FROM `{PROJECT_ID}.{DATASET}.v_gyomu_enriched`
                WHERE nickname IS NULL OR TRIM(nickname) = ''
            ) LIMIT 1
        )
    )
    ORDER BY has_empty DESC, nickname
    """
    return load_data(query)["nickname"].tolist()


@st.cache_data(ttl=3600)
def load_member_name_map() -> dict[str, str]:
    """nickname → "ニックネーム（本名）" の辞書を返す"""
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
    result["(未設定)"] = "(未設定)"
    return result


# --- サイドバー ---
with st.sidebar:
    selected_year, selected_month = render_sidebar_year_month(
        year_key="global_year", month_key="global_month", include_all_month=True,
    )

    # メンバー選択
    st.markdown('<div class="sidebar-section-title">メンバー</div>', unsafe_allow_html=True)
    member_search = st.text_input("検索", key="member_search", placeholder="名前で絞り込み...",
                                  label_visibility="collapsed")

    try:
        all_members = load_all_members()
    except Exception:
        all_members = []

    try:
        name_map = load_member_name_map()
    except Exception:
        name_map = {}

    if member_search:
        display_members = [m for m in all_members if member_search.lower() in m.lower()]
    else:
        display_members = all_members

    col_a, col_b = st.columns(2)
    with col_a:
        if st.button("全選択", key="sb_all", use_container_width=True):
            for m in display_members:
                st.session_state[f"sb_{m}"] = True
    with col_b:
        if st.button("全解除", key="sb_clear", use_container_width=True):
            for m in display_members:
                st.session_state[f"sb_{m}"] = False

    selected_members = []
    with st.container(height=250):
        for m in display_members:
            label = name_map.get(m, m)
            if st.checkbox(label, key=f"sb_{m}"):
                selected_members.append(m)

    count = len(selected_members)
    total = len(all_members)
    if count == 0:
        st.caption(f"全 {total} 名表示中")
    else:
        st.caption(f"{count} / {total} 名を選択中")


# --- ヘッダー ---
st.markdown("""
<div class="dashboard-header">
    <h1>月次報酬ダッシュボード</h1>
</div>
""", unsafe_allow_html=True)


# --- Tab 4 フラグメント定義（グループ選択時にスクリプト全体を再実行させない） ---
@st.fragment
def _render_group_tab(selected_year: int, selected_month: str) -> None:
    """グループ別タブ本体。@st.fragment により外側タブのリセットを防ぐ。"""
    try:
        df_gm = load_groups_master()
        df_mwg = load_members_with_groups()
        _name_map = load_member_name_map()
    except Exception as e:
        logger.error("グループデータ取得失敗: %s", e, exc_info=True)
        st.error(f"データ取得エラー: {e}")
        return

    if df_gm.empty:
        st.info("グループマスターデータがありません。管理者に /update-groups の実行を依頼してください。")
        return

    email_to_name: dict[str, str] = dict(zip(df_gm["group_email"], df_gm["group_name"]))

    group_to_members: dict[str, list[str]] = {}
    for _, mrow in df_mwg.iterrows():
        if not mrow["groups"]:
            continue
        for email in str(mrow["groups"]).split(","):
            email = email.strip()
            if not email or email not in email_to_name:
                continue
            gname = email_to_name[email]
            if gname not in group_to_members:
                group_to_members[gname] = []
            if mrow["nickname"] not in group_to_members[gname]:
                group_to_members[gname].append(mrow["nickname"])

    all_group_names = sorted(group_to_members.keys())
    if not all_group_names:
        st.info("グループに所属するメンバーが見つかりません。")
        return

    col_grp, col_spacer = st.columns([1, 3])
    with col_grp:
        selected_group = st.selectbox(
            "グループ選択",
            all_group_names,
            key="group_selector",
            label_visibility="collapsed",
        )

    group_members = group_to_members.get(selected_group, [])
    st.markdown(
        f'<div class="count-badge">{selected_group} &nbsp;|&nbsp; {len(group_members)} 名</div>',
        unsafe_allow_html=True,
    )

    # サブタブ（外側の「月別報酬サマリー」「業務報告一覧」と区別できる名称）
    gtab1, gtab2, gtab3 = st.tabs(["メンバー一覧", "月別報酬", "業務報告"])

    with gtab1:
        member_df = (
            df_mwg[df_mwg["nickname"].isin(group_members)][["nickname", "full_name", "report_url"]]
            .copy()
            .rename(columns={"nickname": "ニックネーム", "full_name": "本名", "report_url": "URL"})
            .sort_values("ニックネーム")
            .reset_index(drop=True)
        )
        st.dataframe(
            member_df,
            column_config={
                "URL": st.column_config.LinkColumn(display_text="開く"),
            },
            hide_index=True,
            use_container_width=True,
        )

    with gtab2:
        try:
            df_comp_g = load_monthly_compensation()
        except Exception as e:
            st.error(f"データ取得エラー: {e}")
            return

        df_comp_g = fill_empty_nickname(df_comp_g)
        df_comp_g = df_comp_g[df_comp_g["year"].notna()]
        df_comp_g["year"] = df_comp_g["year"].astype(int)
        df_comp_g["month"] = df_comp_g["month"].astype("Int64")
        for col in [
            "work_hours", "hour_compensation", "travel_distance_km",
            "distance_compensation", "subtotal_compensation",
            "position_rate", "position_adjusted_compensation",
            "qualification_allowance", "qualification_adjusted_compensation",
            "withholding_target_amount", "withholding_tax",
            "dx_subsidy", "reimbursement", "payment",
            "donation_payment", "daily_wage_count", "full_day_compensation",
            "total_work_hours",
        ]:
            df_comp_g[col] = df_comp_g[col].fillna(0).astype(float)

        df_comp_g["display_name"] = df_comp_g["nickname"].map(lambda n: _name_map.get(n, n))
        filtered_gc = df_comp_g[
            (df_comp_g["year"] == selected_year)
            & (df_comp_g["nickname"].isin(group_members))
        ]
        if selected_month != "全月":
            filtered_gc = filtered_gc[
                filtered_gc["month"] == int(selected_month.replace("月", ""))
            ]

        k1, k2, k3 = st.columns(3)
        with k1:
            render_kpi("総支払額", f"¥{filtered_gc['payment'].sum():,.0f}")
        with k2:
            render_kpi("業務報酬", f"¥{filtered_gc['qualification_adjusted_compensation'].sum():,.0f}")
        with k3:
            render_kpi("源泉徴収", f"¥{filtered_gc['withholding_tax'].sum():,.0f}")

        if not filtered_gc.empty:
            st.subheader("メンバー別 月次支払額")
            pivot_gc = filtered_gc.pivot_table(
                values="payment",
                index="display_name",
                columns="month",
                aggfunc="sum",
                fill_value=0,
            )
            pivot_gc.columns = pivot_gc.columns.astype(str)
            month_order_gc = sorted(
                pivot_gc.columns,
                key=lambda x: int(float(x)) if x.replace(".", "").isdigit() else 99,
            )
            pivot_gc = pivot_gc[month_order_gc]
            pivot_gc["合計"] = pivot_gc.sum(axis=1)
            pivot_gc = pivot_gc.sort_values("合計", ascending=False)
            st.dataframe(pivot_gc.style.format("¥{:,.0f}"), use_container_width=True)
        else:
            st.info("対象期間のデータがありません")

    with gtab3:
        try:
            df_gyomu_g = load_gyomu_with_members()
        except Exception as e:
            st.error(f"データ取得エラー: {e}")
            return

        df_gyomu_g = fill_empty_nickname(df_gyomu_g)
        df_gyomu_g["year"] = valid_years(df_gyomu_g["year"])
        df_gyomu_g = df_gyomu_g[df_gyomu_g["year"].notna()]
        df_gyomu_g["year"] = df_gyomu_g["year"].astype(int)
        df_gyomu_g["amount_num"] = clean_numeric_series(df_gyomu_g["amount"])
        df_gyomu_g["display_name"] = df_gyomu_g["nickname"].map(lambda n: _name_map.get(n, n))

        result_g = df_gyomu_g[
            (df_gyomu_g["year"] == selected_year)
            & (df_gyomu_g["nickname"].isin(group_members))
        ]
        if selected_month != "全月":
            result_g = result_g[
                result_g["month"] == int(selected_month.replace("月", ""))
            ]

        work_cats_g = ["全業務分類"] + sorted(
            result_g["work_category"].dropna().unique().tolist()
        )
        col_wc, col_sp_wc = st.columns([1, 3])
        with col_wc:
            sel_wcat_g = st.selectbox("業務分類", work_cats_g, key="group_wcat", label_visibility="collapsed")
        if sel_wcat_g != "全業務分類":
            result_g = result_g[result_g["work_category"] == sel_wcat_g]

        k1, k2 = st.columns(2)
        with k1:
            render_kpi("総額", f"¥{result_g['amount_num'].sum():,.0f}")
        with k2:
            render_kpi("件数", f"{len(result_g):,}")

        if not result_g.empty:
            st.dataframe(
                result_g[[
                    "display_name", "date", "day_of_week",
                    "activity_category", "work_category",
                    "sponsor", "description",
                    "unit_price", "work_hours", "amount",
                ]].rename(columns={
                    "display_name": "メンバー",
                    "date": "日付",
                    "day_of_week": "曜日",
                    "activity_category": "活動分類",
                    "work_category": "業務分類",
                    "sponsor": "スポンサー",
                    "description": "内容",
                    "unit_price": "単価",
                    "work_hours": "時間",
                    "amount": "金額",
                }),
                use_container_width=True,
                hide_index=True,
            )
        else:
            st.info("対象期間のデータがありません")


# --- タブ ---
tab1, tab2, tab3, tab4 = st.tabs([
    "月別報酬サマリー",
    "スポンサー別業務委託費",
    "業務報告一覧",
    "グループ別",
])


# ===== Tab 1: 月別報酬サマリー =====
with tab1:
    try:
        df_comp = load_monthly_compensation()
    except Exception as e:
        logger.error("v_monthly_compensation取得失敗: %s", e, exc_info=True)
        st.error(f"データ取得エラー: {e}")
        st.stop()

    if df_comp.empty:
        st.info("データがありません")
    else:
        df_comp = fill_empty_nickname(df_comp)
        df_comp = df_comp[df_comp["year"].notna()]
        df_comp["year"] = df_comp["year"].astype(int)
        df_comp["month"] = df_comp["month"].astype("Int64")

        num_cols = [
            "work_hours", "hour_compensation", "travel_distance_km",
            "distance_compensation", "subtotal_compensation",
            "position_rate", "position_adjusted_compensation",
            "qualification_allowance", "qualification_adjusted_compensation",
            "withholding_target_amount", "withholding_tax",
            "dx_subsidy", "reimbursement", "payment",
            "donation_payment", "daily_wage_count", "full_day_compensation",
            "total_work_hours",
        ]
        for col in num_cols:
            df_comp[col] = df_comp[col].fillna(0).astype(float)

        df_comp["display_name"] = df_comp["nickname"].map(lambda n: name_map.get(n, n))

        filtered = df_comp[df_comp["year"] == selected_year]
        if selected_month != "全月":
            filtered = filtered[filtered["month"] == int(selected_month.replace("月", ""))]
        if selected_members:
            filtered = filtered[filtered["nickname"].isin(selected_members)]

        # KPIカード
        k1, k2, k3, k4, k5 = st.columns(5)
        with k1:
            render_kpi("総支払額", f"¥{filtered['payment'].sum():,.0f}")
        with k2:
            render_kpi("業務報酬", f"¥{filtered['qualification_adjusted_compensation'].sum():,.0f}")
        with k3:
            render_kpi("源泉徴収", f"¥{filtered['withholding_tax'].sum():,.0f}")
        with k4:
            render_kpi("DX補助", f"¥{filtered['dx_subsidy'].sum():,.0f}")
        with k5:
            render_kpi("立替", f"¥{filtered['reimbursement'].sum():,.0f}")

        # メンバー×月ピボット
        st.subheader("メンバー別 月次支払額")
        pivot = filtered.pivot_table(
            values="payment",
            index="display_name",
            columns="month",
            aggfunc="sum",
            fill_value=0,
        )
        pivot.columns = pivot.columns.astype(str)
        month_order = sorted(pivot.columns, key=lambda x: int(float(x)) if x.replace(".", "").isdigit() else 99)
        pivot = pivot[month_order]
        pivot["年間合計"] = pivot.sum(axis=1)
        pivot = pivot.sort_values("年間合計", ascending=False)
        st.dataframe(
            pivot.style.format("¥{:,.0f}"),
            use_container_width=True,
        )

        # メンバー別詳細テーブル
        st.subheader("メンバー別 報酬明細")
        detail = filtered.groupby(["display_name", "report_url"]).agg(
            時間=("work_hours", "sum"),
            時間報酬=("hour_compensation", "sum"),
            距離=("travel_distance_km", "sum"),
            距離報酬=("distance_compensation", "sum"),
            小計=("subtotal_compensation", "sum"),
            役職手当後=("position_adjusted_compensation", "sum"),
            資格手当加算後=("qualification_adjusted_compensation", "sum"),
            源泉対象額=("withholding_target_amount", "sum"),
            源泉徴収=("withholding_tax", "sum"),
            DX補助=("dx_subsidy", "sum"),
            立替=("reimbursement", "sum"),
            支払い=("payment", "sum"),
            寄付支払い=("donation_payment", "sum"),
            一立て件数=("daily_wage_count", "sum"),
            一立て報酬=("full_day_compensation", "sum"),
            総稼働時間=("total_work_hours", "sum"),
        ).reset_index().rename(columns={"display_name": "メンバー", "report_url": "URL"}).sort_values("支払い", ascending=False)
        st.dataframe(
            detail.style.format({
                "時間": "{:,.1f}",
                "時間報酬": "¥{:,.0f}",
                "距離": "{:,.1f}",
                "距離報酬": "¥{:,.0f}",
                "小計": "¥{:,.0f}",
                "役職手当後": "¥{:,.0f}",
                "資格手当加算後": "¥{:,.0f}",
                "源泉対象額": "¥{:,.0f}",
                "源泉徴収": "¥{:,.0f}",
                "DX補助": "¥{:,.0f}",
                "立替": "¥{:,.0f}",
                "支払い": "¥{:,.0f}",
                "寄付支払い": "¥{:,.0f}",
                "一立て件数": "{:,.0f}",
                "一立て報酬": "¥{:,.0f}",
                "総稼働時間": "{:,.1f}",
            }),
            column_config={
                "URL": st.column_config.LinkColumn(display_text="開く"),
            },
            hide_index=True,
            use_container_width=True,
        )

        # 月次推移チャート
        st.subheader("月次推移")
        monthly = filtered.groupby("month").agg(
            業務報酬=("qualification_adjusted_compensation", "sum"),
            源泉徴収=("withholding_tax", "sum"),
            DX補助=("dx_subsidy", "sum"),
            立替=("reimbursement", "sum"),
        ).reset_index()
        monthly["month"] = monthly["month"].apply(
            lambda x: int(float(x)) if str(x).replace(".", "").isdigit() else 0
        )
        monthly = monthly.sort_values("month")
        monthly = monthly.set_index("month")
        st.bar_chart(monthly[["業務報酬", "源泉徴収", "DX補助", "立替"]])


# ===== Tab 2: スポンサー別業務委託費 =====
with tab2:
    try:
        df_gyomu = load_gyomu_with_members()
    except Exception as e:
        st.error(f"データ取得エラー: {e}")
        st.stop()

    if df_gyomu.empty:
        st.info("データがありません")
    else:
        df_gyomu = fill_empty_nickname(df_gyomu)
        df_gyomu["amount_num"] = clean_numeric_series(df_gyomu["amount"])
        df_gyomu["month_num"] = df_gyomu["month"].astype("Int64").astype(str).replace("<NA>", "")
        df_gyomu["year"] = valid_years(df_gyomu["year"])
        df_gyomu = df_gyomu[df_gyomu["year"].notna()]
        df_gyomu["year"] = df_gyomu["year"].astype(int)
        df_gyomu["display_name"] = df_gyomu["nickname"].map(lambda n: name_map.get(n, n))

        filtered_g = df_gyomu[df_gyomu["year"] == selected_year]
        if selected_month != "全月":
            filtered_g = filtered_g[filtered_g["month_num"] == str(int(selected_month.replace("月", "")))]

        sponsors = filtered_g["sponsor"].dropna().unique().tolist()
        sponsors = [s for s in sponsors if s and s.strip()]

        col_sp, col_spacer = st.columns([1, 3])
        with col_sp:
            selected_sponsor = st.selectbox(
                "スポンサー",
                ["全スポンサー"] + sorted(sponsors),
                key="gyomu_sponsor",
                label_visibility="collapsed",
            )

        if selected_sponsor != "全スポンサー":
            filtered_g = filtered_g[filtered_g["sponsor"] == selected_sponsor]
        if selected_members:
            filtered_g = filtered_g[filtered_g["nickname"].isin(selected_members)]

        k1, k2, k3 = st.columns(3)
        with k1:
            render_kpi("総額", f"¥{filtered_g['amount_num'].sum():,.0f}")
        with k2:
            render_kpi("件数", f"{len(filtered_g):,}")
        with k3:
            render_kpi("メンバー数", f"{filtered_g['nickname'].nunique()}")

        st.subheader("メンバー別 月次金額")
        if not filtered_g.empty:
            pivot_g = filtered_g.pivot_table(
                values="amount_num",
                index="display_name",
                columns="month_num",
                aggfunc="sum",
                fill_value=0,
            )
            month_order_g = sorted(
                pivot_g.columns,
                key=lambda x: int(x) if x.isdigit() else 99,
            )
            pivot_g = pivot_g[month_order_g]
            pivot_g["年間合計"] = pivot_g.sum(axis=1)
            pivot_g = pivot_g.sort_values("年間合計", ascending=False)
            st.dataframe(
                pivot_g.style.format("¥{:,.0f}"),
                use_container_width=True,
            )

        st.subheader("活動分類別 金額")
        cat_summary = (
            filtered_g.groupby("activity_category")["amount_num"]
            .sum()
            .sort_values(ascending=False)
        )
        if not cat_summary.empty:
            st.bar_chart(cat_summary)


# ===== Tab 3: 業務報告一覧 =====
with tab3:
    try:
        df_gyomu_all = load_gyomu_with_members()
    except Exception as e:
        st.error(f"データ取得エラー: {e}")
        st.stop()

    if df_gyomu_all.empty:
        st.info("データがありません")
    else:
        df_gyomu_all = fill_empty_nickname(df_gyomu_all)
        df_gyomu_all["year"] = valid_years(df_gyomu_all["year"])
        df_gyomu_all = df_gyomu_all[df_gyomu_all["year"].notna()]
        df_gyomu_all["year"] = df_gyomu_all["year"].astype(int)
        df_gyomu_all["display_name"] = df_gyomu_all["nickname"].map(lambda n: name_map.get(n, n))

        result = df_gyomu_all[df_gyomu_all["year"] == selected_year]
        if selected_month != "全月":
            month_val = int(selected_month.replace("月", ""))
            result = result[result["month"] == month_val]

        categories = ["全分類"] + sorted(
            result["activity_category"].dropna().unique().tolist()
        )
        work_categories = ["全業務分類"] + sorted(
            result["work_category"].dropna().unique().tolist()
        )
        col_cat, col_wcat, col_spacer = st.columns([1, 1, 2])
        with col_cat:
            sel_cat = st.selectbox("活動分類", categories, key="list_cat", label_visibility="collapsed")
        with col_wcat:
            sel_wcat = st.selectbox("業務分類", work_categories, key="list_wcat", label_visibility="collapsed")

        if selected_members:
            result = result[result["nickname"].isin(selected_members)]
        if sel_cat != "全分類":
            result = result[result["activity_category"] == sel_cat]
        if sel_wcat != "全業務分類":
            result = result[result["work_category"] == sel_wcat]

        st.markdown(f'<div class="count-badge">{len(result):,} 件</div>', unsafe_allow_html=True)
        st.dataframe(
            result[
                [
                    "display_name", "source_url", "date", "day_of_week",
                    "activity_category", "work_category",
                    "sponsor", "description",
                    "unit_price", "work_hours", "travel_distance_km", "amount",
                ]
            ].rename(columns={
                "display_name": "メンバー",
                "source_url": "URL",
                "date": "日付",
                "day_of_week": "曜日",
                "activity_category": "活動分類",
                "work_category": "業務分類",
                "sponsor": "スポンサー",
                "description": "内容",
                "unit_price": "単価",
                "work_hours": "時間",
                "travel_distance_km": "移動距離(km)",
                "amount": "金額",
            }),
            column_config={
                "URL": st.column_config.LinkColumn(display_text="開く"),
            },
            use_container_width=True,
            hide_index=True,
        )


# ===== Tab 4: グループ別 =====
with tab4:
    _render_group_tab(selected_year, selected_month)
