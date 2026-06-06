"""dashboard/lib/gyomu_list_view.py の単体テスト"""

import pandas as pd
import pytest

from lib.gyomu_list_view import filter_wam_only


@pytest.fixture
def base_df() -> pd.DataFrame:
    return pd.DataFrame({
        "work_category": [
            "（WAM）生成AIカスタマイズ開発費",  # 全角プレフィックス
            "(WAM)生成AIカスタマイズ開発費",   # 半角プレフィックス
            "出張タダスクで喜ばれ隊",            # 非WAM
            "XX（WAM）yy",                      # プレフィックスではなく途中含有
            " （WAM）先頭半角空白",             # 先頭半角空白
            "　（WAM）先頭全角空白",            # 先頭全角空白
            "ＷＡＭ全角アルファベット",         # 全角ＷＡＭ + 括弧なし
            "（ＷＡＭ）全角アルファ＋全角括弧", # 全角ＷＡＭ + 全角括弧
            None,                                # NaN
            "",                                  # 空文字
            "（WAM）",                           # プレフィックスのみ
        ],
        "amount": list(range(11)),
    })


def test_filter_wam_only_zenkaku_prefix(base_df: pd.DataFrame) -> None:
    """全角「（WAM）」プレフィックスは抽出される"""
    result = filter_wam_only(base_df)
    assert "（WAM）生成AIカスタマイズ開発費" in result["work_category"].tolist()


def test_filter_wam_only_hankaku_prefix(base_df: pd.DataFrame) -> None:
    """半角「(WAM)」プレフィックスは抽出される"""
    result = filter_wam_only(base_df)
    assert "(WAM)生成AIカスタマイズ開発費" in result["work_category"].tolist()


def test_filter_wam_only_excludes_middle_match(base_df: pd.DataFrame) -> None:
    """「XX（WAM）yy」のような途中含有は除外される (startswith厳密性)"""
    result = filter_wam_only(base_df)
    assert "XX（WAM）yy" not in result["work_category"].tolist()


def test_filter_wam_only_includes_leading_hankaku_space(base_df: pd.DataFrame) -> None:
    """先頭半角空白付きでも抽出される (lstrip適用)"""
    result = filter_wam_only(base_df)
    assert " （WAM）先頭半角空白" in result["work_category"].tolist()


def test_filter_wam_only_includes_leading_zenkaku_space(base_df: pd.DataFrame) -> None:
    """先頭全角空白付きでも抽出される (NFKC正規化で半角化 → lstrip)"""
    result = filter_wam_only(base_df)
    assert "　（WAM）先頭全角空白" in result["work_category"].tolist()


def test_filter_wam_only_includes_zenkaku_with_brackets(base_df: pd.DataFrame) -> None:
    """全角ＷＡＭ＋全角括弧も NFKC で半角化されて抽出される"""
    result = filter_wam_only(base_df)
    assert "（ＷＡＭ）全角アルファ＋全角括弧" in result["work_category"].tolist()


def test_filter_wam_only_excludes_zenkaku_without_brackets(base_df: pd.DataFrame) -> None:
    """括弧なし「ＷＡＭ全角...」は除外される (プレフィックス判定厳守)"""
    result = filter_wam_only(base_df)
    assert "ＷＡＭ全角アルファベット" not in result["work_category"].tolist()


def test_filter_wam_only_excludes_nan(base_df: pd.DataFrame) -> None:
    """NaN は除外される"""
    result = filter_wam_only(base_df)
    assert result["work_category"].isna().sum() == 0


def test_filter_wam_only_excludes_empty(base_df: pd.DataFrame) -> None:
    """空文字は除外される"""
    result = filter_wam_only(base_df)
    assert "" not in result["work_category"].tolist()


def test_filter_wam_only_includes_prefix_only(base_df: pd.DataFrame) -> None:
    """プレフィックスのみ「（WAM）」も抽出される"""
    result = filter_wam_only(base_df)
    assert "（WAM）" in result["work_category"].tolist()


def test_filter_wam_only_does_not_mutate_original(base_df: pd.DataFrame) -> None:
    """元のDataFrameの work_category 値は変更されない"""
    original = base_df["work_category"].copy()
    filter_wam_only(base_df)
    pd.testing.assert_series_equal(base_df["work_category"], original)


def test_filter_wam_only_preserves_other_columns(base_df: pd.DataFrame) -> None:
    """抽出後も他の列 (amount) が保持される"""
    result = filter_wam_only(base_df)
    assert "amount" in result.columns


def test_filter_wam_only_empty_df_returns_empty() -> None:
    """空のDataFrameを渡すと空のDataFrameを返す"""
    df = pd.DataFrame({"work_category": pd.Series([], dtype=object), "amount": pd.Series([], dtype=int)})
    result = filter_wam_only(df)
    assert len(result) == 0


def test_filter_wam_only_no_match_returns_empty() -> None:
    """マッチする行がない場合は空のDataFrameを返す"""
    df = pd.DataFrame({"work_category": ["A", "B", "C"], "amount": [1, 2, 3]})
    result = filter_wam_only(df)
    assert len(result) == 0
