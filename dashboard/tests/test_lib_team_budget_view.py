"""dashboard/lib/team_budget_view.py の純関数テスト

Streamlit レンダラは _pages 側の統合テストでカバーするため、本ファイルは
計算ヘルパに集中する。
"""

import math

import pandas as pd
import pytest

from lib import team_budget_view as tbv


class TestClassifyAchievement:
    @pytest.mark.parametrize("rate, expected", [
        (None, "no_data"),
        (float("nan"), "no_data"),
        (80, "ok"),
        (100, "ok"),
        (120, "ok"),
        (79.9, "warning"),
        (60, "warning"),
        (120.1, "warning"),
        (150, "warning"),
        (59.9, "danger"),
        (150.1, "danger"),
        (200, "danger"),
    ])
    def test_buckets(self, rate, expected):
        assert tbv.classify_achievement(rate) == expected


class TestAchievementColor:
    def test_returns_hex_strings(self):
        # 各分類で異なる色を返す
        assert tbv.achievement_color(100) != tbv.achievement_color(70)
        assert tbv.achievement_color(70) != tbv.achievement_color(30)
        assert tbv.achievement_color(None).startswith("#")


class TestFormatYen:
    @pytest.mark.parametrize("val, expected", [
        (1234567, "¥1,234,567"),
        (0, "¥0"),
        (-500, "¥-500"),
        (None, "—"),
        (float("nan"), "—"),
    ])
    def test_format(self, val, expected):
        assert tbv.format_yen(val) == expected


class TestFormatRate:
    @pytest.mark.parametrize("val, expected", [
        (96.5, "96.5%"),
        (100, "100.0%"),
        (0, "0.0%"),
        (None, "—"),
        (float("nan"), "—"),
    ])
    def test_format(self, val, expected):
        assert tbv.format_rate(val) == expected


class TestFormatDiff:
    @pytest.mark.parametrize("val, expected", [
        (1234, "+1,234"),
        (-5678, "-5,678"),
        (0, "+0"),
        (None, "—"),
        (float("nan"), "—"),
    ])
    def test_format(self, val, expected):
        assert tbv.format_diff(val) == expected


class TestIsOutdated:
    def test_match_returns_false(self):
        assert tbv.is_outdated("abc", "abc") is False

    def test_mismatch_returns_true(self):
        assert tbv.is_outdated("abc", "xyz") is True

    def test_none_returns_false(self):
        """どちらかが空なら判定不可で False (誤って更新を促さない)"""
        assert tbv.is_outdated(None, "xyz") is False
        assert tbv.is_outdated("abc", None) is False
        assert tbv.is_outdated("", "") is False


class TestSummarizeActuals:
    def test_empty_dataframe(self):
        r = tbv.summarize_actuals(pd.DataFrame())
        assert r["total_budget"] == 0
        assert r["overall_rate"] is None

    def test_aggregates_correctly(self):
        df = pd.DataFrame({
            "budget_amount": [100000, 200000, None],
            "actual_amount": [90000, 180000, 50000],
        })
        r = tbv.summarize_actuals(df)
        assert r["total_budget"] == 300000
        assert r["total_actual"] == 320000
        assert r["overall_rate"] == pytest.approx(320000 / 300000 * 100, rel=1e-6)
        assert r["overall_diff"] == 20000

    def test_zero_budget_yields_none_rate(self):
        df = pd.DataFrame({
            "budget_amount": [0, 0],
            "actual_amount": [50000, 30000],
        })
        r = tbv.summarize_actuals(df)
        assert r["total_budget"] == 0
        assert r["overall_rate"] is None
        assert r["overall_diff"] == 80000


class TestBuildMatrixDf:
    def test_empty(self):
        assert tbv.build_matrix_df(pd.DataFrame()).empty

    def test_pivots_team_x_month(self):
        df = pd.DataFrame({
            "team": ["A", "A", "B", "B"],
            "month": [5, 6, 5, 6],
            "achievement_rate": [90, 110, 70, None],
        })
        m = tbv.build_matrix_df(df, value="achievement_rate")
        assert list(m.index) == ["A", "B"]
        assert 5 in m.columns and 6 in m.columns
        assert m.loc["A", 5] == 90
        assert m.loc["A", 6] == 110

    def test_uses_specified_value_column(self):
        df = pd.DataFrame({
            "team": ["X"], "month": [5],
            "actual_amount": [500000], "achievement_rate": [80],
        })
        m = tbv.build_matrix_df(df, value="actual_amount")
        assert m.loc["X", 5] == 500000
