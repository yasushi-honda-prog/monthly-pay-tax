"""共通UIユーティリティ

dashboard.py と check_management.py で共用する関数を集約。
"""

import logging
import re
from datetime import date

import pandas as pd
import streamlit as st

logger = logging.getLogger(__name__)


# gyomu_reports.date は元 GAS シートの自由入力で 3 形式混在 (M/D, M月D日, YYYY/M/D)
_DATE_FULL_RE = re.compile(r"^\s*(\d{4})/(\d{1,2})/(\d{1,2})\s*$")
_DATE_JP_RE = re.compile(r"^\s*(\d{1,2})月(\d{1,2})日\s*$")
_DATE_MD_RE = re.compile(r"^\s*(\d{1,2})/(\d{1,2})\s*$")

# パース失敗率がこれ以上で UI に warning を出す (運用観測性)
_DATE_PARSE_FAILURE_WARN_THRESHOLD = 0.05


def parse_gyomu_date(year, date_str) -> pd.Timestamp:
    """gyomu_reports.date (STRING) を pd.Timestamp に変換する。

    元 GAS シートの自由入力により 3 形式が混在する。"YYYY/M/D" 形式では
    cell 内の年を source of truth とし、year 引数 (シート名・ファイル由来)
    と食い違う場合に備える。

    対応形式:
        "M/D"      (例: "4/29")    → year 引数で年を補完
        "M月D日"   (例: "4月29日") → year 引数で年を補完
        "YYYY/M/D" (例: "2025/4/29") → 文字列内の年を優先 (year 引数は無視)

    Args:
        year: 年補完用。int / 文字列 / float に対応し、None / NaN は補完不能。
              "YYYY/M/D" 形式では未使用
        date_str: 日付文字列。None / NaN / 空文字列なら NaT を返す

    Returns:
        pd.Timestamp。パース不能なら pd.NaT
    """
    if date_str is None or (isinstance(date_str, float) and pd.isna(date_str)):
        return pd.NaT
    s = str(date_str).strip()
    if not s:
        return pd.NaT

    m = _DATE_FULL_RE.match(s)
    if m:
        try:
            return pd.Timestamp(year=int(m.group(1)), month=int(m.group(2)), day=int(m.group(3)))
        except (ValueError, TypeError):
            return pd.NaT

    if year is None or (isinstance(year, float) and pd.isna(year)):
        return pd.NaT
    try:
        year_int = int(year)
    except (ValueError, TypeError):
        return pd.NaT

    m = _DATE_JP_RE.match(s)
    if m:
        try:
            return pd.Timestamp(year=year_int, month=int(m.group(1)), day=int(m.group(2)))
        except (ValueError, TypeError):
            return pd.NaT

    m = _DATE_MD_RE.match(s)
    if m:
        try:
            return pd.Timestamp(year=year_int, month=int(m.group(1)), day=int(m.group(2)))
        except (ValueError, TypeError):
            return pd.NaT

    return pd.NaT


def add_gyomu_date_dt(df: pd.DataFrame, col_name: str = "date_dt") -> pd.DataFrame:
    """gyomu DataFrame に Timestamp 列を追加した copy を返す。

    DataFrame は year / date 列を持つ前提。Streamlit の dataframe で日付ソート
    可能にするためのヘルパ。元の date 列は STRING のまま残す。

    パース失敗行は NaT。失敗率を WARNING ログに集計し、閾値 (5%) を超えると
    UI に Streamlit warning を出してユーザーに通知する (運用観測性確保)。

    Args:
        df: year (int / STRING どちらも可) と date (STRING) 列を持つ DataFrame
        col_name: 追加する列名（デフォルト "date_dt"）

    Returns:
        新しい列を持つ DataFrame の copy
    """
    out = df.copy()
    out[col_name] = out.apply(
        lambda r: parse_gyomu_date(r["year"], r["date"]), axis=1
    )

    if len(out) > 0:
        nat_count = int(out[col_name].isna().sum())
        if nat_count > 0:
            failure_rate = nat_count / len(out)
            sample = (
                out.loc[out[col_name].isna(), ["year", "date"]]
                .head(5)
                .to_dict("records")
            )
            logger.warning(
                "parse_gyomu_date failed for %d/%d rows (%.1f%%). samples=%s",
                nat_count,
                len(out),
                failure_rate * 100,
                sample,
            )
            if failure_rate >= _DATE_PARSE_FAILURE_WARN_THRESHOLD:
                st.warning(
                    f"日付列の解析に失敗した行が {nat_count}件 / 全{len(out)}件 あります。"
                    "元データに想定外の日付形式が含まれている可能性があります。"
                )
    return out


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
    all_years = list(range(2026, 2023, -1))
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
