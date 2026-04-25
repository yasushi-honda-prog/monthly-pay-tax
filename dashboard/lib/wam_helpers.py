"""WAM立替金確認ページ Tab2（メンバー別明細）のテーブル構築ヘルパー

production と test の双方から参照できるようロジックをページから分離。
"""

from __future__ import annotations

import pandas as pd

TAB2_CSV_COLS = [
    "nickname", "date", "target_project", "is_wam", "category",
    "payment_purpose", "payment_amount", "advance_amount",
    "from_station", "to_station", "visit_purpose",
]
# receipt_url は collector が =HYPERLINK() の表示テキストのみ取得しており URL 化されていないため、
# collector 改修まではリンク列として扱わない（#TODO: 別Issue で改修）
TAB2_DISPLAY_COLS = TAB2_CSV_COLS + ["source_url"]
TAB2_COL_LABELS = {
    "nickname": "メンバー", "date": "月日", "target_project": "対象PJ",
    "is_wam": "WAM対象", "category": "分類", "payment_purpose": "支払用途",
    "payment_amount": "支払金額", "advance_amount": "仮払金額",
    "from_station": "発", "to_station": "着", "visit_purpose": "訪問目的",
    "source_url": "URL",
}


def _safe_url(val) -> str:
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return ""
    s = str(val).strip()
    return "" if s == "nan" else s


def build_tab2_display_df(df_detail: pd.DataFrame) -> pd.DataFrame:
    existing = [c for c in TAB2_DISPLAY_COLS if c in df_detail.columns]
    df_display = df_detail[existing].rename(columns=TAB2_COL_LABELS).copy()
    # LinkColumn は "nan"/空文字も href として描画するため、空欄化してリンク化を抑止
    if "URL" in df_display.columns:
        df_display["URL"] = df_display["URL"].apply(_safe_url)
    return df_display


def build_tab2_csv_df(df_detail: pd.DataFrame) -> pd.DataFrame:
    # CSV は既存仕様維持のため URL/領収書 を含めない
    existing = [c for c in TAB2_CSV_COLS if c in df_detail.columns]
    return df_detail[existing].rename(columns=TAB2_COL_LABELS)
