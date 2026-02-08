"""月次報酬ダッシュボード

BigQueryのpay_reportsデータセットを可視化するStreamlitアプリ。
BQ VIEWs (v_gyomu_enriched, v_hojo_enriched) 経由でデータを取得。
Cloud IAP経由でtadakayo.jpドメインのみアクセス可能。
"""

import streamlit as st
from google.cloud import bigquery

st.set_page_config(
    page_title="タダカヨ 月次報酬ダッシュボード",
    page_icon="📊",
    layout="wide",
)

# --- カスタムCSS ---
st.markdown("""
<style>
    /* ヘッダー */
    .dashboard-header {
        padding: 0.5rem 0 1rem 0;
        border-bottom: 2px solid #0EA5E9;
        margin-bottom: 1rem;
    }
    .dashboard-header h1 {
        font-size: 1.6rem;
        font-weight: 700;
        margin: 0;
        letter-spacing: 0.02em;
    }
    .dashboard-header .user-email {
        font-size: 0.8rem;
        opacity: 0.6;
        margin-top: 0.2rem;
    }

    /* KPIカード */
    .kpi-card {
        border: 1px solid rgba(14, 165, 233, 0.3);
        border-radius: 8px;
        padding: 1rem 1.2rem;
        background: linear-gradient(135deg, rgba(14, 165, 233, 0.08) 0%, rgba(14, 165, 233, 0.02) 100%);
        margin-bottom: 0.5rem;
    }
    .kpi-card .kpi-label {
        font-size: 0.75rem;
        font-weight: 500;
        text-transform: uppercase;
        letter-spacing: 0.08em;
        opacity: 0.6;
        margin-bottom: 0.3rem;
    }
    .kpi-card .kpi-value {
        font-size: 1.5rem;
        font-weight: 700;
        color: #0EA5E9;
        line-height: 1.2;
    }

    /* サイドバー */
    section[data-testid="stSidebar"] {
        width: 280px !important;
    }
    section[data-testid="stSidebar"] .stSelectbox label,
    section[data-testid="stSidebar"] .stTextInput label {
        font-size: 0.8rem;
        font-weight: 600;
        letter-spacing: 0.03em;
    }
    .sidebar-section-title {
        font-size: 0.7rem;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 0.1em;
        opacity: 0.5;
        margin: 1rem 0 0.3rem 0;
        padding-top: 0.8rem;
        border-top: 1px solid rgba(255,255,255,0.1);
    }

    /* タブ */
    .stTabs [data-baseweb="tab-list"] {
        gap: 0;
    }
    .stTabs [data-baseweb="tab"] {
        padding: 0.6rem 1.5rem;
        font-weight: 600;
        font-size: 0.85rem;
    }

    /* データフレーム */
    .stDataFrame {
        border-radius: 6px;
        overflow: hidden;
    }

    /* 件数バッジ */
    .count-badge {
        display: inline-block;
        background: rgba(14, 165, 233, 0.15);
        color: #0EA5E9;
        font-weight: 700;
        font-size: 0.85rem;
        padding: 0.3rem 0.8rem;
        border-radius: 20px;
        margin-bottom: 0.5rem;
    }

    /* 選択カウント */
    .member-count {
        font-size: 0.75rem;
        opacity: 0.5;
        margin-top: 0.2rem;
    }
</style>
""", unsafe_allow_html=True)


# --- IAP認証情報取得 ---
def get_iap_user_email() -> str:
    """Cloud IAPが設定するヘッダーからユーザーメールを取得"""
    headers = st.context.headers
    return headers.get("X-Goog-Authenticated-User-Email", "").replace("accounts.google.com:", "")


PROJECT_ID = "monthly-pay-tax"
DATASET = "pay_reports"


def valid_years(series):
    """年カラムから有効な年（2020-2030の整数）のみ抽出"""
    def to_year(v):
        try:
            y = int(float(v))
            return y if 2020 <= y <= 2030 else None
        except (ValueError, TypeError):
            return None
    return series.apply(to_year)


def fill_empty_nickname(df):
    """空のnicknameを「(未設定)」に置換"""
    df["nickname"] = df["nickname"].fillna("").apply(lambda x: x.strip() if x else "")
    df.loc[df["nickname"] == "", "nickname"] = "(未設定)"
    return df


def clean_numeric(series):
    """文字列の数値カラムをfloatに変換（通貨記号, カンマ, スプレッドシートエラー対応）"""
    cleaned = (
        series.astype(str)
        .str.replace("¥", "", regex=False)
        .str.replace("＄", "", regex=False)
        .str.replace("$", "", regex=False)
        .str.replace(",", "", regex=False)
        .str.strip()
    )
    def safe_float(x):
        if not x or x in ("", "None", "nan") or x.startswith("#"):
            return 0.0
        try:
            return float(x)
        except (ValueError, TypeError):
            return 0.0
    return cleaned.apply(safe_float)


def render_kpi(label: str, value: str):
    """カスタムKPIカードを描画"""
    st.markdown(f"""
    <div class="kpi-card">
        <div class="kpi-label">{label}</div>
        <div class="kpi-value">{value}</div>
    </div>
    """, unsafe_allow_html=True)


@st.cache_resource
def get_bq_client():
    return bigquery.Client(project=PROJECT_ID)


@st.cache_data(ttl=3600)
def load_data(query: str):
    client = get_bq_client()
    return client.query(query).to_dataframe()


# --- データ読み込み ---
@st.cache_data(ttl=3600)
def load_hojo_with_members():
    """補助報告（VIEW経由: メンバー結合 + 年月正規化済み）"""
    query = f"""
    SELECT
        nickname,
        full_name,
        year,
        month,
        hours,
        compensation,
        dx_subsidy,
        reimbursement,
        total_amount,
        monthly_complete
    FROM `{PROJECT_ID}.{DATASET}.v_hojo_enriched`
    WHERE year IS NOT NULL
    ORDER BY year, month
    """
    return load_data(query)


@st.cache_data(ttl=3600)
def load_gyomu_with_members():
    """業務報告（VIEW経由: メンバー結合 + 月抽出 + 距離分離済み）"""
    query = f"""
    SELECT
        nickname,
        year,
        date,
        month,
        day_of_week,
        activity_category,
        work_category,
        sponsor,
        description,
        unit_price,
        work_hours,
        travel_distance_km,
        amount
    FROM `{PROJECT_ID}.{DATASET}.v_gyomu_enriched`
    WHERE year IS NOT NULL
        AND (date IS NOT NULL OR amount IS NOT NULL)
    ORDER BY year, date
    """
    return load_data(query)


# --- サイドバー ---
with st.sidebar:
    st.markdown("### 📊 タダカヨ")
    st.caption("月次報酬ダッシュボード")
    user_email = get_iap_user_email()
    if user_email:
        st.markdown(f"<div style='font-size:0.8rem; opacity:0.6; margin-bottom:1rem;'>{user_email}</div>",
                    unsafe_allow_html=True)
    st.divider()

    # 年選択
    st.markdown('<div class="sidebar-section-title">期間</div>', unsafe_allow_html=True)
    # 年リストはデータロード前にデフォルト値を設定、タブ内で使用
    all_years = list(range(2024, 2027))
    selected_year = st.selectbox("年度", all_years, index=len(all_years) - 1, key="global_year")
    month_options = ["全月"] + [f"{m}月" for m in range(1, 13)]
    selected_month = st.selectbox("月", month_options, key="global_month")

    # メンバー選択
    st.markdown('<div class="sidebar-section-title">メンバー</div>', unsafe_allow_html=True)
    member_search = st.text_input("検索", key="member_search", placeholder="名前で絞り込み...",
                                  label_visibility="collapsed")

    # データから全メンバーリストを構築
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

    try:
        all_members = load_all_members()
    except Exception:
        all_members = []

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
            if st.checkbox(m, key=f"sb_{m}"):
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


# --- タブ ---
tab1, tab2, tab3 = st.tabs([
    "月別報酬サマリー",
    "スポンサー別業務委託費",
    "業務報告一覧",
])


# ===== Tab 1: 月別報酬サマリー =====
with tab1:
    try:
        df_hojo = load_hojo_with_members()
    except Exception as e:
        st.error(f"データ取得エラー: {e}")
        st.stop()

    if df_hojo.empty:
        st.info("データがありません")
    else:
        df_hojo = fill_empty_nickname(df_hojo)
        for col in ["hours", "compensation", "dx_subsidy", "reimbursement", "total_amount"]:
            df_hojo[col] = clean_numeric(df_hojo[col])

        # VIEWで年月はINT64に正規化済み
        df_hojo = df_hojo[df_hojo["year"].notna()]
        df_hojo["year"] = df_hojo["year"].astype(int)
        df_hojo["month"] = df_hojo["month"].astype("Int64")

        filtered = df_hojo[df_hojo["year"] == selected_year]
        if selected_month != "全月":
            filtered = filtered[filtered["month"] == int(selected_month.replace("月", ""))]
        if selected_members:
            filtered = filtered[filtered["nickname"].isin(selected_members)]

        # KPIカード
        k1, k2, k3, k4 = st.columns(4)
        with k1:
            render_kpi("総報酬", f"¥{filtered['compensation'].sum():,.0f}")
        with k2:
            render_kpi("総時間", f"{filtered['hours'].sum():,.1f}h")
        with k3:
            render_kpi("DX補助", f"¥{filtered['dx_subsidy'].sum():,.0f}")
        with k4:
            render_kpi("総額合計", f"¥{filtered['total_amount'].sum():,.0f}")

        # メンバー×月ピボット
        st.subheader("メンバー別 月次総額")
        pivot = filtered.pivot_table(
            values="total_amount",
            index="nickname",
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

        # 月次推移チャート
        st.subheader("月次報酬推移")
        monthly = filtered.groupby("month").agg(
            報酬=("compensation", "sum"),
            DX補助=("dx_subsidy", "sum"),
            立替=("reimbursement", "sum"),
        ).reset_index()
        monthly["month"] = monthly["month"].apply(
            lambda x: int(float(x)) if str(x).replace(".", "").isdigit() else 0
        )
        monthly = monthly.sort_values("month")
        monthly = monthly.set_index("month")
        st.bar_chart(monthly[["報酬", "DX補助", "立替"]])


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
        df_gyomu["amount_num"] = clean_numeric(df_gyomu["amount"])
        # VIEWで月抽出済み（month列）
        df_gyomu["month_num"] = df_gyomu["month"].astype("Int64").astype(str).replace("<NA>", "")
        df_gyomu["year"] = valid_years(df_gyomu["year"])
        df_gyomu = df_gyomu[df_gyomu["year"].notna()]
        df_gyomu["year"] = df_gyomu["year"].astype(int)

        filtered_g = df_gyomu[df_gyomu["year"] == selected_year]
        if selected_month != "全月":
            filtered_g = filtered_g[filtered_g["month_num"] == str(int(selected_month.replace("月", "")))]

        # タブ内フィルター（スポンサーのみ）
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

        # KPIカード
        k1, k2, k3 = st.columns(3)
        with k1:
            render_kpi("総額", f"¥{filtered_g['amount_num'].sum():,.0f}")
        with k2:
            render_kpi("件数", f"{len(filtered_g):,}")
        with k3:
            render_kpi("メンバー数", f"{filtered_g['nickname'].nunique()}")

        # ピボット
        st.subheader("メンバー別 月次金額")
        if not filtered_g.empty:
            pivot_g = filtered_g.pivot_table(
                values="amount_num",
                index="nickname",
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

        # 活動分類別サマリー
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

        result = df_gyomu_all[df_gyomu_all["year"] == selected_year]
        if selected_month != "全月":
            month_val = int(selected_month.replace("月", ""))
            result = result[result["month"] == month_val]

        # タブ内フィルター
        categories = ["全分類"] + sorted(
            result["activity_category"].dropna().unique().tolist()
        )
        col_cat, col_spacer = st.columns([1, 3])
        with col_cat:
            sel_cat = st.selectbox("活動分類", categories, key="list_cat", label_visibility="collapsed")

        if selected_members:
            result = result[result["nickname"].isin(selected_members)]
        if sel_cat != "全分類":
            result = result[result["activity_category"] == sel_cat]

        st.markdown(f'<div class="count-badge">{len(result):,} 件</div>', unsafe_allow_html=True)
        st.dataframe(
            result[
                [
                    "nickname", "date", "day_of_week",
                    "activity_category", "work_category",
                    "sponsor", "description",
                    "unit_price", "work_hours", "travel_distance_km", "amount",
                ]
            ].rename(columns={
                "nickname": "メンバー",
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
            use_container_width=True,
            hide_index=True,
        )
