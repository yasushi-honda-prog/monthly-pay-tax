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

    def test_stored_empty_current_non_empty_returns_true(self):
        """評価レコードが古い形式 (stored が空) で実データがあるなら再生成促す"""
        assert tbv.is_outdated(None, "xyz") is True
        assert tbv.is_outdated("", "xyz") is True

    def test_current_empty_returns_false(self):
        """データなし (current が空) なら outdated 判定材料がない"""
        assert tbv.is_outdated("abc", None) is False
        assert tbv.is_outdated("abc", "") is False
        assert tbv.is_outdated(None, None) is False

    def test_both_non_empty_match(self):
        assert tbv.is_outdated("abc", "abc") is False
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


class TestSummarizeByLeaderTeam:
    """PR-A: 統括隊別集計関数のテスト"""

    def test_empty_dataframe_returns_empty_with_schema(self):
        result = tbv.summarize_by_leader_team(pd.DataFrame())
        assert result.empty
        # 必須列が定義されている (UI 側で empty 時に列参照しても KeyError にならない)
        for col in ("leader_team", "actual_amount", "budget_amount",
                    "achievement_rate", "diff_amount", "team_count"):
            assert col in result.columns

    def test_missing_leader_team_column_returns_empty(self):
        """PR-A 以前の load 出力 (leader_team 列なし) は空 DataFrame で返す (後方互換)"""
        df = pd.DataFrame({"team": ["A"], "actual_amount": [100], "budget_amount": [200]})
        result = tbv.summarize_by_leader_team(df)
        assert result.empty

    def test_groups_by_leader_team(self):
        df = pd.DataFrame({
            "team": ["A 隊", "B 隊", "C 隊", "D 隊"],
            "leader_team": ["L1", "L1", "L2", "L2"],
            "month": [5, 5, 5, 5],
            "actual_amount": [100.0, 200.0, 50.0, 150.0],
            "budget_amount": [300.0, 100.0, 80.0, 120.0],
        })
        result = tbv.summarize_by_leader_team(df)
        assert len(result) == 2
        # 昇順ソート
        assert result.iloc[0]["leader_team"] == "L1"
        # 合計値
        assert result.iloc[0]["actual_amount"] == 300.0
        assert result.iloc[0]["budget_amount"] == 400.0
        # 配下隊 count
        assert result.iloc[0]["team_count"] == 2
        # 達成率は actual/budget*100 で再計算
        assert result.iloc[0]["achievement_rate"] == 75.0
        # 差額
        assert result.iloc[0]["diff_amount"] == -100.0

    def test_null_leader_team_rows_excluded(self):
        """leader_team NULL 行は除外する (VIEW 層で除外済みだが念のため)"""
        df = pd.DataFrame({
            "team": ["A 隊", "X"],
            "leader_team": ["L1", None],
            "actual_amount": [100.0, 999.0],
            "budget_amount": [200.0, 999.0],
        })
        result = tbv.summarize_by_leader_team(df)
        assert len(result) == 1
        assert result.iloc[0]["leader_team"] == "L1"
        assert result.iloc[0]["actual_amount"] == 100.0

    def test_zero_budget_returns_none_rate(self):
        df = pd.DataFrame({
            "team": ["A 隊"],
            "leader_team": ["L1"],
            "actual_amount": [100.0],
            "budget_amount": [0.0],
        })
        result = tbv.summarize_by_leader_team(df)
        assert result.iloc[0]["achievement_rate"] is None


class TestBuildLeaderTeamMatrixDf:
    """PR-A: 統括隊×月マトリクス関数のテスト"""

    def test_empty(self):
        assert tbv.build_leader_team_matrix_df(pd.DataFrame()).empty

    def test_missing_leader_team_column_returns_empty(self):
        df = pd.DataFrame({"team": ["A"], "month": [5], "actual_amount": [100]})
        assert tbv.build_leader_team_matrix_df(df).empty

    def test_pivots_leader_team_x_month(self):
        df = pd.DataFrame({
            "team": ["A 隊", "A 隊", "B 隊", "B 隊"],
            "leader_team": ["L1", "L1", "L2", "L2"],
            "month": [5, 6, 5, 6],
            "actual_amount": [100.0, 200.0, 300.0, 400.0],
            "budget_amount": [50.0, 100.0, 150.0, 200.0],
        })
        m = tbv.build_leader_team_matrix_df(df, value="achievement_rate")
        assert list(m.index) == ["L1", "L2"]
        # achievement_rate は actual/budget*100 で再計算
        assert m.loc["L1", 5] == 200.0
        assert m.loc["L2", 6] == 200.0

    def test_value_actual_amount_uses_sum(self):
        df = pd.DataFrame({
            "team": ["A 隊", "B 隊"],
            "leader_team": ["L1", "L1"],
            "month": [5, 5],
            "actual_amount": [100.0, 200.0],
            "budget_amount": [0.0, 0.0],
        })
        m = tbv.build_leader_team_matrix_df(df, value="actual_amount")
        # 統括隊×月の単純合計
        assert m.loc["L1", 5] == 300.0
