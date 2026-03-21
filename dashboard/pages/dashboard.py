"""活動時間・報酬マネジメントダッシュボード（3タブ構成）

BigQueryのpay_reportsデータセットを可視化。
BQ VIEWs (v_gyomu_enriched, v_hojo_enriched, v_monthly_compensation) 経由でデータを取得。
"""

import logging
import re
from datetime import date as _date

import altair as alt
import pandas as pd
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

# v_monthly_compensation の数値カラム（BQ STRING → float 変換対象）
_COMP_NUM_COLS = [
    "work_hours", "hour_compensation", "travel_distance_km",
    "distance_compensation", "subtotal_compensation",
    "position_rate", "position_adjusted_compensation",
    "qualification_allowance", "qualification_adjusted_compensation",
    "withholding_target_amount", "withholding_tax",
    "dx_subsidy", "reimbursement", "payment",
    "donation_payment", "daily_wage_count", "full_day_compensation",
    "total_work_hours",
]


def _ensure_numeric_pivot(df, exclude_col=None):
    """ピボット表示前にobject型混入列を数値化する（missing_members補完後の型修復用）"""
    obj_cols = [c for c in df.columns if c != exclude_col and df[c].dtype == object]
    for col in obj_cols:
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)
    return df


# --- データ読み込み ---
@st.cache_data(ttl=21600)
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


@st.cache_data(ttl=21600)
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


@st.cache_data(ttl=21600)
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


@st.cache_data(ttl=21600)
def load_available_year_months() -> list[str]:
    """データが存在する年月を昇順で返す（期間指定スライダー用）"""
    query = f"""
    SELECT DISTINCT CAST(year AS INT64) AS year, CAST(month AS INT64) AS month
    FROM `{PROJECT_ID}.{DATASET}.v_gyomu_enriched`
    WHERE year IS NOT NULL AND month IS NOT NULL
    UNION DISTINCT
    SELECT DISTINCT CAST(year AS INT64) AS year, CAST(month AS INT64) AS month
    FROM `{PROJECT_ID}.{DATASET}.v_hojo_enriched`
    WHERE year IS NOT NULL AND month IS NOT NULL
    ORDER BY year, month
    """
    df = load_data(query)
    return [f"{int(row.year)}年{int(row.month)}月" for _, row in df.iterrows()]


@st.cache_data(ttl=21600)
def load_groups_master():
    query = f"""
    SELECT group_email, group_name
    FROM `{PROJECT_ID}.{DATASET}.groups_master`
    ORDER BY group_name
    """
    return load_data(query)


@st.cache_data(ttl=21600)
def load_members_with_groups():
    query = f"""
    SELECT nickname, full_name, report_url, `groups`
    FROM `{PROJECT_ID}.{DATASET}.members`
    WHERE nickname IS NOT NULL AND TRIM(nickname) != ''
        AND `groups` IS NOT NULL AND `groups` != ''
    """
    return load_data(query)


@st.cache_data(ttl=21600)
def load_all_members():
    query = f"""
    SELECT nickname, has_empty FROM (
        SELECT DISTINCT nickname, FALSE AS has_empty FROM (
            SELECT nickname FROM `{PROJECT_ID}.{DATASET}.v_hojo_enriched`
            UNION DISTINCT
            SELECT nickname FROM `{PROJECT_ID}.{DATASET}.v_gyomu_enriched`
            UNION DISTINCT
            SELECT nickname FROM `{PROJECT_ID}.{DATASET}.members`
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


@st.cache_data(ttl=21600)
def load_member_name_map() -> tuple[dict[str, str], dict[str, str]]:
    """nickname → "ニックネーム（本名）" と nickname → report_url の辞書を返す"""
    query = f"""
    SELECT DISTINCT nickname, full_name, report_url
    FROM `{PROJECT_ID}.{DATASET}.members`
    WHERE nickname IS NOT NULL AND TRIM(nickname) != ''
    """
    df = load_data(query)
    name_result: dict[str, str] = {}
    url_result: dict[str, str] = {}
    for _, row in df.iterrows():
        nick = str(row["nickname"])
        full = str(row.get("full_name", "") or "").strip()
        name_result[nick] = f"{nick}（{full}）" if full else nick
        url = str(row.get("report_url", "") or "").strip()
        if url:
            url_result[nick] = url
    name_result["(未設定)"] = "(未設定)"
    return name_result, url_result


# --- サイドバー ---
with st.sidebar:
    selected_year, selected_month = render_sidebar_year_month(
        year_key="global_year", month_key="global_month", include_all_month=True,
    )

    # 期間指定選択時: 月スライダーで期間指定
    if selected_month == "期間指定":
        _t = _date.today()
        _fy_start_year = _t.year - 1 if _t.month < 11 else _t.year
        _fy_end_year = _fy_start_year + 1
        try:
            _all_data_yms = load_available_year_months()
        except Exception:
            _all_data_yms = [f"{y}年{m}月" for y in range(2024, 2028) for m in range(1, 13)]

        # 当期: _fy_start_year年11月 〜 _fy_end_year年10月
        _fy_start_str = f"{_fy_start_year}年11月"
        _fy_end_str = f"{_fy_end_year}年10月"

        # 表示範囲セレクタ（スライダーに表示する月数を絞る）
        _view_options = {"当期": "当期", "直近1年": 12, "直近2年": 24, "直近3年": 36, "全期間": None}
        _prev_view = st.session_state.get("_prev_range_view_scope", None)
        _view_label = st.selectbox(
            "表示範囲", list(_view_options.keys()), index=0, key="range_view_scope",
            label_visibility="collapsed",
        )
        # 表示範囲が変わったらプルダウンの選択をリセット
        if _view_label != _prev_view:
            st.session_state.pop("dd_range_start", None)
            st.session_state.pop("dd_range_end", None)
        st.session_state["_prev_range_view_scope"] = _view_label
        _months_limit = _view_options[_view_label]

        def _ym_tuple(s):
            _mm = re.match(r"(\d+)年(\d+)月", s)
            return int(_mm.group(1)), int(_mm.group(2))

        if _months_limit == "当期":
            _fy_s, _fy_e = _ym_tuple(_fy_start_str), _ym_tuple(_fy_end_str)
            _ym_options = [ym for ym in _all_data_yms if _fy_s <= _ym_tuple(ym) <= _fy_e]
            if not _ym_options:
                _ym_options = _all_data_yms
            _default_start_str = _ym_options[0]
            # 終了デフォルト: 当期内の最新データ月（全データ最新月が当期内ならそれを使用）
            _latest_all = _all_data_yms[-1] if _all_data_yms else _ym_options[-1]
            _default_end_str = _latest_all if _fy_s <= _ym_tuple(_latest_all) <= _fy_e else _ym_options[-1]
        elif _months_limit is not None:
            _ym_options = _all_data_yms[-_months_limit:]
            _default_start_str = _ym_options[0]
            _default_end_str = _ym_options[-1]
        else:
            _ym_options = _all_data_yms
            _default_start_str = _ym_options[0]
            _default_end_str = _ym_options[-1]
        if not _ym_options:
            _ym_options = [f"{_t.year}年{_t.month}月"]
            _default_start_str = _default_end_str = _ym_options[0]

        # 初期値（未設定時のみ）
        if "dd_range_start" not in st.session_state:
            st.session_state["dd_range_start"] = _default_start_str
        if "dd_range_end" not in st.session_state:
            st.session_state["dd_range_end"] = _default_end_str

        st.selectbox("開始月", _ym_options, key="dd_range_start")
        st.selectbox("終了月", _ym_options, key="dd_range_end")

        def _parse_ym(s):
            m = re.match(r"(\d+)年(\d+)月", s)
            return int(m.group(1)), int(m.group(2))
        _dd_start_val = st.session_state.get("dd_range_start", _default_start_str)
        _dd_end_val   = st.session_state.get("dd_range_end",   _default_end_str)
        # 開始 > 終了の場合はスワップ
        if _ym_tuple(_dd_start_val) > _ym_tuple(_dd_end_val):
            _dd_start_val, _dd_end_val = _dd_end_val, _dd_start_val
        range_start_year, range_start_month = _parse_ym(_dd_start_val)
        range_end_year, range_end_month = _parse_ym(_dd_end_val)
    else:
        range_start_year = range_start_month = range_end_year = range_end_month = None

    # グループ選択
    st.markdown('<div class="sidebar-section-title">グループ</div>', unsafe_allow_html=True)
    try:
        df_gm_sb = load_groups_master()
        df_mwg_sb = load_members_with_groups()
        email_to_name_sb: dict[str, str] = dict(zip(df_gm_sb["group_email"], df_gm_sb["group_name"]))
        group_to_members_sb: dict[str, list[str]] = {}
        for _, mrow in df_mwg_sb.iterrows():
            if not mrow["groups"]:
                continue
            for email in str(mrow["groups"]).split(","):
                email = email.strip()
                if not email or email not in email_to_name_sb:
                    continue
                gname = email_to_name_sb[email]
                if gname not in group_to_members_sb:
                    group_to_members_sb[gname] = []
                if mrow["nickname"] not in group_to_members_sb[gname]:
                    group_to_members_sb[gname].append(mrow["nickname"])
        group_options = ["全グループ"] + sorted(group_to_members_sb.keys())
    except Exception:
        group_options = ["全グループ"]
        group_to_members_sb = {}

    selected_group_sb = st.selectbox(
        "グループ", group_options, key="sb_group", label_visibility="collapsed",
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
        name_map, url_map = load_member_name_map()
    except Exception:
        name_map, url_map = {}, {}

    # グループ選択で絞り込み
    if selected_group_sb != "全グループ":
        group_filtered_members = group_to_members_sb.get(selected_group_sb, [])
        base_members = [m for m in all_members if m in group_filtered_members]
    else:
        base_members = all_members

    # グループ変更時: 前グループのチェックを全解除 → 特定グループなら自動全選択
    _prev_group = st.session_state.get("_prev_group_sb", "全グループ")
    if selected_group_sb != _prev_group:
        _prev_grp_members = group_to_members_sb.get(_prev_group, [])
        for m in (_prev_grp_members if _prev_grp_members else all_members):
            st.session_state[f"sb_{m}"] = False
        if selected_group_sb != "全グループ":
            for m in base_members:
                st.session_state[f"sb_{m}"] = True
    st.session_state["_prev_group_sb"] = selected_group_sb

    if member_search:
        _q = member_search.lower()
        display_members = [
            m for m in base_members
            if _q in m.lower() or _q in name_map.get(m, "").lower()
        ]
    else:
        display_members = base_members

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
    with st.container(height=460):
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
    <h1 style="font-size: 1.75rem; font-weight: 700; margin: 0; letter-spacing: 0.02em;">活動時間・報酬マネジメントダッシュボード</h1>
</div>
""", unsafe_allow_html=True)


# --- Tab 4 フラグメント定義（グループ選択時にスクリプト全体を再実行させない） ---
@st.fragment
def _render_group_tab(
    selected_year: int, selected_month: str,
    selected_members: list,
    range_start_year, range_start_month, range_end_year, range_end_month,
) -> None:
    """グループ別タブ本体。@st.fragment により外側タブのリセットを防ぐ。"""
    try:
        df_gm = load_groups_master()
        df_mwg = load_members_with_groups()
        _name_map, _ = load_member_name_map()
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
            ["全グループ"] + all_group_names,
            key="group_selector",
            label_visibility="collapsed",
        )

    if selected_group == "全グループ":
        all_group_members = sorted({m for members in group_to_members.values() for m in members})
        group_members = all_group_members
    else:
        group_members = group_to_members.get(selected_group, [])
    # サイドバーのメンバーフィルターも適用
    if selected_members:
        group_members = [m for m in group_members if m in selected_members]
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
            height=600,
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
        df_comp_g[_COMP_NUM_COLS] = df_comp_g[_COMP_NUM_COLS].apply(pd.to_numeric, errors="coerce").fillna(0)

        df_comp_g["display_name"] = df_comp_g["nickname"].map(lambda n: _name_map.get(n, n))
        if selected_month != "期間指定":
            filtered_gc = df_comp_g[
                (df_comp_g["year"] == selected_year)
                & (df_comp_g["month"] == int(selected_month.replace("月", "")))
                & (df_comp_g["nickname"].isin(group_members))
            ]
        else:
            _ym_gc = df_comp_g["year"].astype(int) * 100 + df_comp_g["month"].astype(int)
            filtered_gc = df_comp_g[
                (_ym_gc >= range_start_year * 100 + range_start_month)
                & (_ym_gc <= range_end_year * 100 + range_end_month)
                & (df_comp_g["nickname"].isin(group_members))
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
            _piv_gc_src = filtered_gc.copy()
            _multi_year_gc = _piv_gc_src["year"].nunique() > 1
            if _multi_year_gc:
                _piv_gc_src["_col"] = (
                    _piv_gc_src["year"].astype(int).astype(str) + "年" +
                    _piv_gc_src["month"].astype(int).astype(str) + "月"
                )
            else:
                _piv_gc_src["_col"] = _piv_gc_src["month"].astype(int).astype(str) + "月"
            _sort_map_gc = dict(zip(
                _piv_gc_src["_col"],
                _piv_gc_src["year"].astype(int) * 100 + _piv_gc_src["month"].astype(int),
            ))
            pivot_gc = _piv_gc_src.pivot_table(
                values="payment",
                index="display_name",
                columns="_col",
                aggfunc="sum",
                fill_value=0,
            )
            pivot_gc = pivot_gc[sorted(pivot_gc.columns, key=lambda c: _sort_map_gc.get(c, 9999))]
            pivot_gc["合計"] = pivot_gc.sum(axis=1)
            pivot_gc = pivot_gc.sort_values("合計", ascending=False)
            pivot_gc_display = pivot_gc.reset_index().rename(columns={"display_name": "メンバー"})
            _fmt_gc = {col: "¥{:,.0f}" for col in pivot_gc_display.columns if col != "メンバー"}
            _ensure_numeric_pivot(pivot_gc_display, exclude_col="メンバー")
            st.dataframe(pivot_gc_display.style.format(_fmt_gc), hide_index=True, use_container_width=True, height=600)
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

        if selected_month != "期間指定":
            result_g = df_gyomu_g[
                (df_gyomu_g["year"] == selected_year)
                & (df_gyomu_g["nickname"].isin(group_members))
            ]
            result_g = result_g[
                result_g["month"] == int(selected_month.replace("月", ""))
            ]
        else:
            _ym_rg = df_gyomu_g["year"].astype(int) * 100 + df_gyomu_g["month"].astype("Int64").fillna(0).astype(int)
            result_g = df_gyomu_g[
                (_ym_rg >= range_start_year * 100 + range_start_month)
                & (_ym_rg <= range_end_year * 100 + range_end_month)
                & (df_gyomu_g["nickname"].isin(group_members))
            ]

        work_cats_g = ["全業務分類"] + sorted(
            result_g["work_category"].dropna().unique().tolist()
        )
        col_wc, col_sp_wc = st.columns([1, 3])
        with col_wc:
            sel_wcat_g = st.selectbox("業務分類", work_cats_g, key="group_wcat", label_visibility="collapsed")
        if sel_wcat_g != "全業務分類":
            result_g = result_g[result_g["work_category"] == sel_wcat_g]

        k1, k2, k3 = st.columns(3)
        with k1:
            render_kpi("総額", f"¥{result_g['amount_num'].sum():,.0f}")
        with k2:
            render_kpi("件数", f"{len(result_g):,}")
        with k3:
            render_kpi("メンバー数", f"{result_g['nickname'].nunique()}")

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
                height=600,
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

        df_comp[_COMP_NUM_COLS] = df_comp[_COMP_NUM_COLS].apply(pd.to_numeric, errors="coerce").fillna(0)

        df_comp["display_name"] = df_comp["nickname"].map(lambda n: name_map.get(n, n))

        if selected_month != "期間指定":
            filtered = df_comp[
                (df_comp["year"] == selected_year) &
                (df_comp["month"] == int(selected_month.replace("月", "")))
            ]
        else:
            # 全月選択時: 指定期間（年またぎ対応）
            _start_ym = range_start_year * 100 + range_start_month
            _end_ym = range_end_year * 100 + range_end_month
            _ym_num = df_comp["year"].astype(int) * 100 + df_comp["month"].astype(int)
            if _end_ym < _start_ym:
                st.warning("終了年月が開始年月より前になっています")
                filtered = df_comp.iloc[0:0]
            else:
                filtered = df_comp[(_ym_num >= _start_ym) & (_ym_num <= _end_ym)]
        if selected_members:
            filtered = filtered[filtered["nickname"].isin(selected_members)]

        # 選択されたメンバーのうちデータ未登録のものを検出
        if selected_members:
            existing_nicks = set(filtered["nickname"].unique())
            missing_members = [m for m in selected_members if m not in existing_nicks]
        else:
            missing_members = []

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

        mtab1, mtab2, mtab3, mtab4 = st.tabs(["メンバー別 月次支払額", "メンバー別 報酬明細", "月次 報酬明細", "月次推移"])

        # メンバー×月ピボット
        with mtab1:
            _piv_src = filtered.copy()
            _multi_year = _piv_src["year"].nunique() > 1
            if _multi_year:
                _piv_src["_col"] = (
                    _piv_src["year"].astype(int).astype(str) + "年" +
                    _piv_src["month"].astype(int).astype(str) + "月"
                )
            else:
                _piv_src["_col"] = _piv_src["month"].astype(int).astype(str) + "月"
            _sort_map = dict(zip(
                _piv_src["_col"],
                _piv_src["year"].astype(int) * 100 + _piv_src["month"].astype(int),
            ))
            pivot = _piv_src.pivot_table(
                values="payment",
                index="display_name",
                columns="_col",
                aggfunc="sum",
                fill_value=0,
            )
            pivot = pivot[sorted(pivot.columns, key=lambda c: _sort_map.get(c, 9999))]
            # データ未登録メンバーを0行として追加
            if missing_members and pivot.empty:
                pivot = pd.DataFrame(
                    {"合計": 0},
                    index=[name_map.get(m, m) for m in missing_members],
                )
            else:
                for m in missing_members:
                    disp = name_map.get(m, m)
                    if disp not in pivot.index:
                        pivot.loc[disp] = 0
                pivot["合計"] = pivot.sum(axis=1)
            pivot = pivot.sort_values("合計", ascending=False)
            pivot_display = pivot.reset_index().rename(columns={"display_name": "メンバー"})
            _fmt = {col: "¥{:,.0f}" for col in pivot_display.columns if col != "メンバー"}
            _ensure_numeric_pivot(pivot_display, exclude_col="メンバー")
            st.markdown(f'<div style="display:flex;align-items:center;gap:0.75rem;margin-bottom:0.5rem"><h3 style="margin:0">メンバー別 月次支払額</h3><span class="count-badge" style="margin-bottom:0">{len(pivot_display)} 名</span></div>', unsafe_allow_html=True)
            st.dataframe(
                pivot_display.style.format(_fmt),
                hide_index=True,
                use_container_width=True,
                height=600,
            )

        # メンバー別詳細テーブル
        with mtab2:
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
            # データ未登録メンバーを0行として追加
            for m in missing_members:
                disp = name_map.get(m, m)
                if disp not in detail["メンバー"].values:
                    zero_row = {"メンバー": disp, "URL": url_map.get(m, "")}
                    for c in detail.columns:
                        if c not in zero_row:
                            zero_row[c] = 0
                    detail = pd.concat([detail, pd.DataFrame([zero_row])], ignore_index=True)
            st.markdown(f'<div style="display:flex;align-items:center;gap:0.75rem;margin-bottom:0.5rem"><h3 style="margin:0">メンバー別 報酬明細</h3><span class="count-badge" style="margin-bottom:0">{len(detail)} 件</span></div>', unsafe_allow_html=True)
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
                height=600,
            )

        # 月次 報酬明細（月ごと）
        with mtab3:
            st.subheader("月次 報酬明細")
            detail_m = filtered.copy()
            detail_m["年月"] = detail_m["year"].astype(int).astype(str) + "年" + detail_m["month"].astype(int).astype(str) + "月"
            detail_m["_ym_sort"] = detail_m["year"].astype(int) * 100 + detail_m["month"].astype(int)
            detail_m = detail_m.groupby(["_ym_sort", "年月", "display_name", "report_url"]).agg(
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
            ).reset_index().rename(columns={"display_name": "メンバー", "report_url": "URL"})
            detail_m = detail_m.sort_values(["_ym_sort", "支払い"], ascending=[True, False]).drop(columns=["_ym_sort"])
            st.dataframe(
                detail_m.style.format({
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
                height=600,
            )

        # 月次推移チャート
        with mtab4:
            st.subheader("月次推移")
            if not filtered.empty:
                monthly = filtered.groupby(["year", "month"]).agg(
                    業務報酬=("qualification_adjusted_compensation", "sum"),
                    源泉徴収=("withholding_tax", "sum"),
                    DX補助=("dx_subsidy", "sum"),
                    立替=("reimbursement", "sum"),
                ).reset_index()
                monthly["year"] = monthly["year"].astype(int)
                monthly["month"] = monthly["month"].apply(
                    lambda x: int(float(x)) if str(x).replace(".", "").isdigit() else 0
                )
                monthly["ym_sort"] = monthly["year"] * 100 + monthly["month"]
                monthly["ym_label"] = monthly["year"].astype(str) + "年" + monthly["month"].astype(str) + "月"
                monthly = monthly.sort_values("ym_sort")
                _ym_order = monthly["ym_label"].tolist()
                chart_data = monthly.melt(
                    id_vars="ym_label", value_vars=["業務報酬", "源泉徴収", "DX補助", "立替"],
                    var_name="項目", value_name="金額",
                )
                chart_data = chart_data.dropna(subset=["金額"])
                if not chart_data.empty:
                    chart = alt.Chart(chart_data).mark_bar().encode(
                        x=alt.X("ym_label:O", title="年月", sort=_ym_order),
                        y=alt.Y("金額:Q", title="金額", axis=alt.Axis(format=",.0f")),
                        color=alt.Color("項目:N", title="項目"),
                        xOffset="項目:N",
                    )
                    st.altair_chart(chart, use_container_width=True)
                else:
                    st.info("該当するデータがありません")
            else:
                st.info("該当するデータがありません")


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

        if selected_month != "期間指定":
            filtered_g = df_gyomu[
                (df_gyomu["year"] == selected_year) &
                (df_gyomu["month_num"] == str(int(selected_month.replace("月", ""))))
            ]
        else:
            _gm_ym_g = df_gyomu["year"] * 100 + df_gyomu["month_num"].apply(
                lambda x: int(x) if x.isdigit() else 0
            )
            filtered_g = df_gyomu[
                (_gm_ym_g >= range_start_year * 100 + range_start_month) &
                (_gm_ym_g <= range_end_year * 100 + range_end_month)
            ]

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

        stab1, stab2 = st.tabs(["メンバー別 月次金額", "活動分類別 金額"])

        with stab1:
            st.subheader("メンバー別 月次金額")
            if not filtered_g.empty:
                _piv_g = filtered_g[filtered_g["month_num"].str.isdigit()].copy()
                _piv_g["ym_label"] = (
                    _piv_g["year"].astype(int).astype(str) + "年" +
                    _piv_g["month_num"] + "月"
                )
                _ym_sort_g = dict(zip(
                    _piv_g["ym_label"],
                    _piv_g["year"].astype(int) * 100 + _piv_g["month_num"].apply(lambda x: int(x) if x.isdigit() else 0),
                ))
                pivot_g = _piv_g.pivot_table(
                    values="amount_num",
                    index="display_name",
                    columns="ym_label",
                    aggfunc="sum",
                    fill_value=0,
                )
                pivot_g = pivot_g[sorted(pivot_g.columns, key=lambda c: _ym_sort_g.get(c, 9999))]
                # 期間指定時: 範囲内の全月を列として強制表示（データなしは0）
                if selected_month == "期間指定" and range_start_year is not None:
                    _all_cols_g = []
                    _y, _m = range_start_year, range_start_month
                    while _y * 100 + _m <= range_end_year * 100 + range_end_month:
                        _all_cols_g.append(f"{_y}年{_m}月")
                        _m += 1
                        if _m > 12:
                            _m, _y = 1, _y + 1
                    pivot_g = pivot_g.reindex(columns=_all_cols_g, fill_value=0)
                pivot_g["合計"] = pivot_g.sum(axis=1)
                pivot_g = pivot_g.sort_values("合計", ascending=False)
                # pivot_gはreset_index()前のためインデックスが文字列だが列は数値のみ
                _ensure_numeric_pivot(pivot_g)
                st.dataframe(
                    pivot_g.style.format("¥{:,.0f}"),
                    use_container_width=True,
                    height=600,
                )

        with stab2:
            st.subheader("活動分類別 金額")
            cat_summary = (
                filtered_g.groupby("activity_category")["amount_num"]
                .sum()
                .sort_values(ascending=False)
            )
            cat_summary = cat_summary[cat_summary > 0]
            if not cat_summary.empty:
                cat_df = cat_summary.reset_index()
                cat_df.columns = ["活動分類", "金額"]
                chart = alt.Chart(cat_df).mark_bar().encode(
                    x=alt.X("活動分類:N", sort="-y"),
                    y=alt.Y("金額:Q", axis=alt.Axis(format=",.0f")),
                )
                st.altair_chart(chart, use_container_width=True)
            else:
                st.info("該当するデータがありません")


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
        if selected_month != "期間指定":
            month_val = int(selected_month.replace("月", ""))
            result = result[result["month"] == month_val]

        categories = ["活動分類"] + sorted(
            result["activity_category"].dropna().unique().tolist()
        )
        work_categories = sorted(
            result["work_category"].dropna().unique().tolist()
        )
        sel_cat = st.selectbox("活動分類", categories, key="list_cat", label_visibility="collapsed")
        sel_wcat = st.multiselect("業務分類", work_categories, key="list_wcat", placeholder="全業務分類", label_visibility="collapsed")

        if selected_members:
            result = result[result["nickname"].isin(selected_members)]
        if sel_cat != "活動分類":
            result = result[result["activity_category"] == sel_cat]
        if sel_wcat:
            result = result[result["work_category"].isin(sel_wcat)]

        result["amount_num"] = clean_numeric_series(result["amount"])

        k1, k2, k3 = st.columns(3)
        with k1:
            render_kpi("総額", f"¥{result['amount_num'].sum():,.0f}")
        with k2:
            render_kpi("件数", f"{len(result):,}")
        with k3:
            render_kpi("メンバー数", f"{result['nickname'].nunique()}")

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
            height=600,
        )


# ===== Tab 4: グループ別 =====
with tab4:
    _render_group_tab(
        selected_year, selected_month,
        selected_members,
        range_start_year, range_start_month, range_end_year, range_end_month,
    )
