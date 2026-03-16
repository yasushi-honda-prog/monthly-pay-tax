"""共通UIユーティリティ

dashboard.py と check_management.py で共用する関数を集約。
"""

from datetime import date

import pandas as pd
import streamlit as st


def render_kpi(label: str, value: str):
    """KPIカードを描画"""
    st.markdown(f"""
    <div class="kpi-card">
        <div class="kpi-label">{label}</div>
        <div class="kpi-value">{value}</div>
    </div>
    """, unsafe_allow_html=True)


def clean_numeric_scalar(val) -> float:
    """単一値を float に変換（通貨記号・カンマ・スプレッドシートエラー対応）"""
    if pd.isna(val) or val is None:
        return 0.0
    s = str(val).replace("¥", "").replace(",", "").replace("＄", "").replace("$", "").strip()
    if not s or s in ("None", "nan") or s.startswith("#"):
        return 0.0
    try:
        return float(s)
    except (ValueError, TypeError):
        return 0.0


def clean_numeric_series(series):
    """Series 一括で float 変換（内部で clean_numeric_scalar を利用）"""
    return series.apply(clean_numeric_scalar)


def fill_empty_nickname(df):
    """空の nickname を「(未設定)」に置換"""
    df["nickname"] = df["nickname"].fillna("").apply(lambda x: x.strip() if x else "")
    df.loc[df["nickname"] == "", "nickname"] = "(未設定)"
    return df


def valid_years(series):
    """年カラムから有効な年（2020-2030 の整数）のみ抽出"""
    def to_year(v):
        try:
            y = int(float(v))
            return y if 2020 <= y <= 2030 else None
        except (ValueError, TypeError):
            return None
    return series.apply(to_year)


def render_sidebar_year_month(*, year_key: str, month_key: str, include_all_month: bool = False):
    """サイドバー用の年月セレクタを描画し (year, month_value) を返す。

    include_all_month=True の場合、月選択に「全月」を含め、
    返り値の month_value は "全月" または "N月" 文字列。
    include_all_month=False の場合、月選択は 1-12 の整数を返す。
    """
    all_years = list(range(2024, 2027))
    _today = date.today()
    _prev_month = _today.month - 1 if _today.month > 1 else 12
    _prev_year = _today.year if _today.month > 1 else _today.year - 1
    _default_year_idx = all_years.index(_prev_year) if _prev_year in all_years else len(all_years) - 1
    selected_year = st.selectbox("年度", all_years, index=_default_year_idx, key=year_key, format_func=lambda y: f"{y}年")

    if include_all_month:
        month_options = ["期間指定"] + [f"{m}月" for m in range(1, 13)]
        selected_month = st.selectbox("月", month_options, index=_prev_month, key=month_key)
    else:
        selected_month = st.selectbox(
            "月", list(range(1, 13)),
            index=_prev_month - 1,
            key=month_key,
        )

    return selected_year, selected_month
