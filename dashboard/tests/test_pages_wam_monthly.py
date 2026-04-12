"""Unit tests for pages/wam_monthly.py

集計・フィルタ・領収書統計ロジックのテスト。
モジュールレベルのStreamlit実行を回避するため、関数を直接定義してテスト。
"""

from __future__ import annotations

import pandas as pd
import pytest


# --- テスト対象の関数を直接定義（モジュールレベルSt実行回避） ---

def _filter_by_year_month(df: pd.DataFrame, year: int, month: int) -> pd.DataFrame:
    return df[(df["normalized_year"] == year) & (df["month"] == month)]


def _summarize_by_project(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame(columns=["対象PJ", "件数", "支払金額合計", "仮払金額合計"])
    summary = df.groupby("target_project", dropna=False).agg(
        件数=("payment_amount_numeric", "size"),
        支払金額合計=("payment_amount_numeric", "sum"),
        仮払金額合計=("advance_amount_numeric", "sum"),
    ).reset_index()
    summary.rename(columns={"target_project": "対象PJ"}, inplace=True)
    summary["対象PJ"] = summary["対象PJ"].fillna("(未設定)")
    return summary.sort_values("支払金額合計", ascending=False)


def _is_receipt_attached(series: pd.Series) -> pd.Series:
    return series.notna() & (series.str.strip() != "")


def _receipt_stats(df: pd.DataFrame) -> dict:
    total = len(df)
    if total == 0:
        return {"total": 0, "attached": 0, "missing": 0, "rate": 0.0}
    n_attached = int(_is_receipt_attached(df["receipt_url"]).sum())
    return {
        "total": total,
        "attached": n_attached,
        "missing": total - n_attached,
        "rate": n_attached / total * 100,
    }


# --- Fixtures ---

@pytest.fixture
def sample_df():
    return pd.DataFrame({
        "source_url": ["url1", "url2", "url3", "url4", "url5"],
        "nickname": ["太郎", "花子", "太郎", "次郎", "花子"],
        "normalized_year": [2026, 2026, 2026, 2025, 2026],
        "month": [4, 4, 3, 4, 4],
        "target_project": ["ケアプーPJ", "神奈川県PJ", "ケアプーPJ", "経産省PJ", None],
        "category": ["旅費", "物品", "旅費", "旅費", "物品"],
        "payment_purpose": ["出張", "購入", "出張", "出張", "購入"],
        "payment_amount": ["¥10,000", "¥5,000", "¥8,000", "¥3,000", "¥2,000"],
        "payment_amount_numeric": [10000.0, 5000.0, 8000.0, 3000.0, 2000.0],
        "advance_amount": [None, None, "¥5,000", None, None],
        "advance_amount_numeric": [0.0, 0.0, 5000.0, 0.0, 0.0],
        "from_station": ["東京", None, "横浜", "新宿", None],
        "to_station": ["大阪", None, "名古屋", "池袋", None],
        "visit_purpose": ["訪問", None, "訪問", "訪問", None],
        "receipt_url": ["https://example.com/1", "", "https://example.com/3", None, "https://example.com/5"],
    })


# --- _filter_by_year_month ---

class TestFilterByYearMonth:
    def test_filters_correctly(self, sample_df):
        result = _filter_by_year_month(sample_df, 2026, 4)
        assert len(result) == 3
        assert set(result["nickname"]) == {"太郎", "花子"}

    def test_no_match(self, sample_df):
        result = _filter_by_year_month(sample_df, 2024, 1)
        assert len(result) == 0

    def test_different_year(self, sample_df):
        result = _filter_by_year_month(sample_df, 2025, 4)
        assert len(result) == 1
        assert result.iloc[0]["nickname"] == "次郎"

    def test_different_month(self, sample_df):
        result = _filter_by_year_month(sample_df, 2026, 3)
        assert len(result) == 1


# --- _summarize_by_project ---

class TestSummarizeByProject:
    def test_basic_summary(self, sample_df):
        filtered = _filter_by_year_month(sample_df, 2026, 4)
        summary = _summarize_by_project(filtered)
        assert len(summary) == 3  # ケアプーPJ, 神奈川県PJ, (未設定)
        care = summary[summary["対象PJ"] == "ケアプーPJ"]
        assert care["件数"].values[0] == 1
        assert care["支払金額合計"].values[0] == 10000.0

    def test_empty_df(self):
        empty = pd.DataFrame(columns=["target_project", "payment_amount_numeric", "advance_amount_numeric"])
        summary = _summarize_by_project(empty)
        assert len(summary) == 0
        assert "対象PJ" in summary.columns

    def test_null_project_becomes_unset(self, sample_df):
        filtered = _filter_by_year_month(sample_df, 2026, 4)
        summary = _summarize_by_project(filtered)
        assert "(未設定)" in summary["対象PJ"].values

    def test_sorted_by_amount_desc(self, sample_df):
        filtered = _filter_by_year_month(sample_df, 2026, 4)
        summary = _summarize_by_project(filtered)
        amounts = summary["支払金額合計"].tolist()
        assert amounts == sorted(amounts, reverse=True)


# --- _receipt_stats ---

class TestReceiptStats:
    def test_basic_stats(self, sample_df):
        filtered = _filter_by_year_month(sample_df, 2026, 4)
        stats = _receipt_stats(filtered)
        assert stats["total"] == 3
        # url1=有, url2=空文字(無), url5=有
        assert stats["attached"] == 2
        assert stats["missing"] == 1
        assert 60.0 < stats["rate"] < 70.0

    def test_empty_df(self):
        empty = pd.DataFrame(columns=["receipt_url"])
        stats = _receipt_stats(empty)
        assert stats["total"] == 0
        assert stats["rate"] == 0.0

    def test_all_attached(self):
        df = pd.DataFrame({"receipt_url": ["https://a.com", "https://b.com"]})
        stats = _receipt_stats(df)
        assert stats["attached"] == 2
        assert stats["rate"] == 100.0

    def test_none_attached(self):
        df = pd.DataFrame({"receipt_url": [None, "", "  "]})
        stats = _receipt_stats(df)
        assert stats["attached"] == 0
        assert stats["missing"] == 3


# --- WAMフィルタ ---

class TestWamFilter:
    def test_filter_wam_only(self):
        df = pd.DataFrame({
            "normalized_year": [2026, 2026, 2026],
            "month": [4, 4, 4],
            "is_wam": [True, False, True],
            "payment_amount_numeric": [10000.0, 5000.0, 3000.0],
        })
        filtered = df[df["is_wam"] == True]  # noqa: E712
        assert len(filtered) == 2
        assert filtered["payment_amount_numeric"].sum() == 13000.0

    def test_filter_wam_all_false(self):
        df = pd.DataFrame({
            "is_wam": [False, False, False],
            "payment_amount_numeric": [10000.0, 5000.0, 3000.0],
        })
        filtered = df[df["is_wam"] == True]  # noqa: E712
        assert len(filtered) == 0

    def test_filter_wam_missing_column(self):
        """is_wamカラムがない場合はフィルタしない"""
        df = pd.DataFrame({
            "payment_amount_numeric": [10000.0, 5000.0],
        })
        # is_wamカラムがなければフィルタをスキップ（アプリの動作と同じ）
        if "is_wam" in df.columns:
            df = df[df["is_wam"] == True]  # noqa: E712
        assert len(df) == 2
