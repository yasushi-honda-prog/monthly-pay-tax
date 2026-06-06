"""業務報告一覧ビュー関連のヘルパー (Streamlit 非依存の純関数群)"""

from __future__ import annotations

import unicodedata

import pandas as pd


def _normalized_starts_with_wam(val: object) -> bool:
    if val is None:
        return False
    try:
        if pd.isna(val):
            return False
    except (TypeError, ValueError):
        pass
    if not isinstance(val, str):
        val = str(val)
    # NFKC: 全角ＷＡＭ → WAM、全角（）→ ()、全角空白 → 半角空白
    # lstrip: 入力者のタイポによる先頭空白を許容
    return unicodedata.normalize("NFKC", val).lstrip().startswith("(WAM)")


def filter_wam_only(df: pd.DataFrame) -> pd.DataFrame:
    """業務分類が「（WAM）」または「(WAM)」で始まる行のみを抽出する。

    判定は NFKC 正規化 + 先頭空白除去後に半角「(WAM)」プレフィックスで行う。
    これにより全角/半角括弧、全角/半角アルファベット、先頭空白の混在を吸収する。
    元の DataFrame の値は変更しない (新しい DataFrame を返す)。
    """
    if df.empty or "work_category" not in df.columns:
        return df.iloc[0:0].copy()
    mask = df["work_category"].map(_normalized_starts_with_wam)
    return df[mask].copy()
