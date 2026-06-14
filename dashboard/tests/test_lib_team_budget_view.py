"""dashboard/lib/team_budget_view.py の純関数テスト

Streamlit レンダラは _pages 側の統合テストでカバーするため、本ファイルは
計算ヘルパに集中する。
"""

import math
from decimal import Decimal
from unittest.mock import MagicMock, patch

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


class TestFormatDiffYen:
    """Issue #253: マトリクスセル用の '¥+1,234,567' / '¥-5,678' / '—' 形式"""

    @pytest.mark.parametrize("val, expected", [
        (1234567, "¥+1,234,567"),
        (-2345678, "¥-2,345,678"),
        (0, "¥+0"),
        (None, "—"),
        (float("nan"), "—"),
    ])
    def test_format(self, val, expected):
        assert tbv.format_diff_yen(val) == expected


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

    def test_leader_team_budgets_override_replaces_budget_amount(self):
        """PR-Q2M: leader_team_budgets dict が actuals の budget_amount を上書きする"""
        df = pd.DataFrame({
            "team": ["A 隊", "B 隊"],
            "leader_team": ["L1", "L2"],
            "actual_amount": [100.0, 200.0],
            "budget_amount": [9999.0, 9999.0],  # 上書きされる
        })
        override = {"L1": 500.0, "L2": 1000.0}
        result = tbv.summarize_by_leader_team(df, leader_team_budgets=override)
        l1 = result[result["leader_team"] == "L1"].iloc[0]
        l2 = result[result["leader_team"] == "L2"].iloc[0]
        assert l1["budget_amount"] == 500.0
        assert l2["budget_amount"] == 1000.0
        # 達成率も override 後の budget で再計算
        assert l1["achievement_rate"] == 20.0  # 100/500*100
        assert l2["achievement_rate"] == 20.0  # 200/1000*100
        # diff_amount も上書き
        assert l1["diff_amount"] == -400.0
        assert l2["diff_amount"] == -800.0

    def test_leader_team_budgets_override_zero_for_missing_key(self):
        """override dict にない統括隊は budget=0 で扱う"""
        df = pd.DataFrame({
            "team": ["A 隊", "C 隊"],
            "leader_team": ["L1", "L3"],
            "actual_amount": [100.0, 300.0],
            "budget_amount": [0.0, 0.0],
        })
        override = {"L1": 500.0}  # L3 はキーなし
        result = tbv.summarize_by_leader_team(df, leader_team_budgets=override)
        l3 = result[result["leader_team"] == "L3"].iloc[0]
        assert l3["budget_amount"] == 0.0
        # 複数行で float と None が混じると pandas が NaN に変換するため pd.isna でチェック
        assert pd.isna(l3["achievement_rate"])  # budget=0 → None/NaN

    def test_no_override_keeps_actuals_budget(self):
        """leader_team_budgets=None なら従来通り actuals の budget を集計"""
        df = pd.DataFrame({
            "team": ["A 隊"],
            "leader_team": ["L1"],
            "actual_amount": [100.0],
            "budget_amount": [500.0],
        })
        result = tbv.summarize_by_leader_team(df, leader_team_budgets=None)
        assert result.iloc[0]["budget_amount"] == 500.0

    def test_decimal_amounts_with_float_override(self):
        """BQ NUMERIC 列 (Decimal) と PR-Q2M override (float) の混在で TypeError が起きないこと。

        v_team_budget_actuals の actual_amount / budget_amount は NUMERIC 型のため
        to_dataframe() で Decimal になる。一方 leader_team_budgets override は
        team_budget.py:95 で float に変換される。両者を _compute_rate / 引き算で
        混ぜると `Decimal / float` および `Decimal - float` で TypeError が出る (本番障害)。
        """
        df = pd.DataFrame({
            "team": ["A 隊", "B 隊"],
            "leader_team": ["L1", "L1"],
            "actual_amount": [Decimal("100"), Decimal("200")],
            "budget_amount": [Decimal("9999"), Decimal("9999")],
        })
        override = {"L1": 500.0}
        result = tbv.summarize_by_leader_team(df, leader_team_budgets=override)
        l1 = result.iloc[0]
        assert l1["budget_amount"] == 500.0
        assert l1["actual_amount"] == 300.0
        assert l1["achievement_rate"] == 60.0  # 300/500*100
        assert l1["diff_amount"] == -200.0

    def test_decimal_amounts_without_override(self):
        """BQ NUMERIC 列 (Decimal) 入力でも override なしのケースが動作すること。"""
        df = pd.DataFrame({
            "team": ["A 隊"],
            "leader_team": ["L1"],
            "actual_amount": [Decimal("100")],
            "budget_amount": [Decimal("400")],
        })
        result = tbv.summarize_by_leader_team(df, leader_team_budgets=None)
        assert result.iloc[0]["achievement_rate"] == 25.0  # 100/400*100
        assert result.iloc[0]["diff_amount"] == -300.0


class TestBuildMonthlyTrend:
    """PR-Q2M follow-up: 月次推移グラフの Decimal/float 不整合修正テスト"""

    def test_empty_returns_schema(self):
        result = tbv.build_monthly_trend(pd.DataFrame())
        assert result.empty
        for col in ("month", "actual_amount", "budget_amount"):
            assert col in result.columns

    def test_aggregates_by_month(self):
        df = pd.DataFrame({
            "month": [5, 5, 6, 6],
            "actual_amount": [100.0, 200.0, 50.0, 150.0],
            "budget_amount": [300.0, 100.0, 80.0, 120.0],
        })
        result = tbv.build_monthly_trend(df)
        assert len(result) == 2
        m5 = result[result["month"] == 5].iloc[0]
        assert m5["actual_amount"] == 300.0
        assert m5["budget_amount"] == 400.0
        m6 = result[result["month"] == 6].iloc[0]
        assert m6["actual_amount"] == 200.0
        assert m6["budget_amount"] == 200.0

    def test_decimal_amounts_converted_to_float(self):
        """本番障害: BQ NUMERIC 列 (Decimal) を altair に渡すと Y 軸スケールが
        桁違いになる (例: ¥4,232,055 → ¥4.5 兆表記)。float 化で正常表示する。
        """
        df = pd.DataFrame({
            "month": [5, 6],
            "actual_amount": [Decimal("4232055"), Decimal("1000000")],
            "budget_amount": [Decimal("0"), Decimal("0")],
        })
        result = tbv.build_monthly_trend(df)
        assert result["actual_amount"].dtype == float
        assert result["budget_amount"].dtype == float
        assert result.iloc[0]["actual_amount"] == 4232055.0
        assert result.iloc[1]["actual_amount"] == 1000000.0

    def test_sorted_by_month_ascending(self):
        df = pd.DataFrame({
            "month": [12, 5, 8],
            "actual_amount": [1.0, 2.0, 3.0],
            "budget_amount": [10.0, 20.0, 30.0],
        })
        result = tbv.build_monthly_trend(df)
        assert list(result["month"]) == [5, 8, 12]

    def test_leader_yearly_budgets_overrides_budget(self):
        """hotfix 2026-06-13: 全体タブで leader_yearly_monthly_budgets override 動作"""
        df = pd.DataFrame({
            "month": [5, 6],
            "actual_amount": [100.0, 200.0],
            "budget_amount": [0.0, 0.0],  # team_budgets 空 (今までの ¥0 状態)
        })
        leader_yearly = {5: 7819148.0, 6: 7819148.0}
        result = tbv.build_monthly_trend(df, leader_yearly)
        m5 = result[result["month"] == 5].iloc[0]
        m6 = result[result["month"] == 6].iloc[0]
        assert m5["budget_amount"] == 7819148.0
        assert m6["budget_amount"] == 7819148.0

    def test_leader_yearly_budgets_missing_month_falls_back_to_zero(self):
        """leader_yearly_monthly_budgets に該当月がない時は 0 (例: 四半期データなし)"""
        df = pd.DataFrame({
            "month": [5, 11],
            "actual_amount": [100.0, 200.0],
            "budget_amount": [0.0, 0.0],
        })
        leader_yearly = {5: 1000000.0}  # 11 月の予算なし
        result = tbv.build_monthly_trend(df, leader_yearly)
        m5 = result[result["month"] == 5].iloc[0]
        m11 = result[result["month"] == 11].iloc[0]
        assert m5["budget_amount"] == 1000000.0
        assert m11["budget_amount"] == 0.0

    def test_none_leader_budgets_keeps_actuals_budget(self):
        """leader_yearly_monthly_budgets=None なら従来通り actuals 由来"""
        df = pd.DataFrame({
            "month": [5],
            "actual_amount": [100.0],
            "budget_amount": [300.0],
        })
        result = tbv.build_monthly_trend(df, None)
        assert result.iloc[0]["budget_amount"] == 300.0

    def test_issue_248_same_quarter_months_have_different_budgets(self):
        """Issue #248 AC4: 同四半期内 3 ヶ月 (Q3=5,6,7) が別値で描画されること。

        PR #247 hotfix (quarterly÷3) では同四半期内 3 ヶ月が同値だったが、
        新規 leader_team_monthly_budgets テーブルでは月別予算が独立した値を持つため、
        本田様が月毎に手調整した結果が推移グラフで「変化する線」として可視化される。
        """
        df = pd.DataFrame({
            "month": [5, 6, 7],
            "actual_amount": [1000000.0, 1500000.0, 2000000.0],
            "budget_amount": [0.0, 0.0, 0.0],  # actuals 由来は空
        })
        # 同四半期 (Q3) の 3 ヶ月でそれぞれ別値の月別予算
        leader_yearly = {
            5: 5000000,  # 5月
            6: 7000000,  # 6月 (本田様が手調整で増額)
            7: 6000000,  # 7月
        }
        result = tbv.build_monthly_trend(df, leader_yearly)
        m5 = result[result["month"] == 5].iloc[0]
        m6 = result[result["month"] == 6].iloc[0]
        m7 = result[result["month"] == 7].iloc[0]
        # 同四半期内でも 3 ヶ月別値であること (PR #247 で同値だった問題の解消)
        assert m5["budget_amount"] != m6["budget_amount"]
        assert m6["budget_amount"] != m7["budget_amount"]
        assert m5["budget_amount"] == 5000000.0
        assert m6["budget_amount"] == 7000000.0
        assert m7["budget_amount"] == 6000000.0

    def test_issue_248_int_values_from_new_table_accepted(self):
        """Issue #248: leader_team_monthly_budgets テーブルは int (円整数) で値を持つ。

        Codex L1: budget_amount は int 統一。build_monthly_trend は int 値も受け取り
        正しく float 化 (altair 互換) する。
        """
        df = pd.DataFrame({
            "month": [11, 12, 1],  # FY Q1
            "actual_amount": [100.0, 200.0, 300.0],
            "budget_amount": [0.0, 0.0, 0.0],
        })
        # int 値で渡す (新テーブルは int 統一)
        leader_yearly = {11: 1000000, 12: 1100000, 1: 1200000}
        result = tbv.build_monthly_trend(df, leader_yearly)
        # 3 ヶ月とも別値
        m11 = result[result["month"] == 11].iloc[0]
        m12 = result[result["month"] == 12].iloc[0]
        m1 = result[result["month"] == 1].iloc[0]
        assert m11["budget_amount"] == 1000000.0
        assert m12["budget_amount"] == 1100000.0
        assert m1["budget_amount"] == 1200000.0

    def test_issue_248_fy_full_range_11_to_10(self):
        """Issue #248: FY 12 ヶ月 (11-12-1-...-10) で月次推移を表示できる。

        従来 (PR #247) は year_start=year_end=year で 1-12 月のみ。
        新規 FY 範囲取得 (load_team_budget_actuals fiscal_year=) で
        actuals に 11 月 (前暦年) と 1-10 月 (当暦年) が混在する。
        """
        df = pd.DataFrame({
            "month": [11, 12, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10],
            "actual_amount": [100.0] * 12,
            "budget_amount": [0.0] * 12,
        })
        leader_yearly = {m: m * 100000 for m in range(1, 13)}
        result = tbv.build_monthly_trend(df, leader_yearly)
        assert len(result) == 12
        # FY 順 (11, 12, 1, ..., 10) ではなく、build_monthly_trend は month ASC ソート
        # (1, 2, ..., 12)。altair で表示時に列順を制御。
        assert list(result["month"]) == sorted(range(1, 13))

    def test_codex_cm2_fiscal_month_order_column_added(self):
        """Codex review C-M2 反映: fiscal_month_order 列で FY 順を altair sort に渡す。

        順序: 11=0, 12=1, 1=2, 2=3, ..., 10=11 (FY 順 → 0-based index)。
        """
        df = pd.DataFrame({
            "month": [1, 5, 11, 12],
            "actual_amount": [100.0, 200.0, 50.0, 75.0],
            "budget_amount": [0.0, 0.0, 0.0, 0.0],
        })
        result = tbv.build_monthly_trend(df)
        assert "fiscal_month_order" in result.columns
        # 各月の fiscal_month_order 値
        order_map = dict(zip(result["month"], result["fiscal_month_order"]))
        assert order_map[11] == 0  # FY Q1 1月目
        assert order_map[12] == 1  # FY Q1 2月目
        assert order_map[1] == 2   # FY Q1 3月目
        assert order_map[5] == 6   # FY Q3 1月目 (11,12,1,2,3,4,5)

    def test_codex_cm2_empty_dataframe_includes_order_column(self):
        """empty 入力でも schema として fiscal_month_order 列が含まれる。"""
        result = tbv.build_monthly_trend(pd.DataFrame())
        assert result.empty
        assert "fiscal_month_order" in result.columns


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


class TestComputeMomDelta:
    """Issue #257: 前月比 (MoM) delta 計算の純粋関数テスト。

    docs/specs/2026-06-14-team-budget-mom-delta.md §7.1 の 5 ケース。
    """

    def test_mom_delta_both_present(self):
        result = tbv.compute_mom_delta(
            current={"actual_amount": 500000.0, "achievement_rate": 90.0},
            previous={"actual_amount": 400000.0, "achievement_rate": 80.0},
        )
        assert result["actual_delta"] == 100000.0
        assert result["rate_delta"] == 10.0

    def test_mom_delta_previous_none(self):
        result = tbv.compute_mom_delta(
            current={"actual_amount": 500000.0, "achievement_rate": 90.0},
            previous=None,
        )
        assert result["actual_delta"] is None
        assert result["rate_delta"] is None

    def test_mom_delta_current_actual_nan(self):
        result = tbv.compute_mom_delta(
            current={"actual_amount": float("nan"), "achievement_rate": 90.0},
            previous={"actual_amount": 400000.0, "achievement_rate": 80.0},
        )
        assert result["actual_delta"] is None
        assert result["rate_delta"] == 10.0

    def test_mom_delta_previous_rate_none(self):
        result = tbv.compute_mom_delta(
            current={"actual_amount": 500000.0, "achievement_rate": 90.0},
            previous={"actual_amount": 400000.0, "achievement_rate": None},
        )
        assert result["actual_delta"] == 100000.0
        assert result["rate_delta"] is None

    def test_mom_delta_negative(self):
        result = tbv.compute_mom_delta(
            current={"actual_amount": 300000.0, "achievement_rate": 60.0},
            previous={"actual_amount": 500000.0, "achievement_rate": 100.0},
        )
        assert result["actual_delta"] == -200000.0
        assert result["rate_delta"] == -40.0


class TestFormatMomYen:
    def test_positive(self):
        assert tbv.format_mom_yen(100000.0) == "+¥100,000"

    def test_negative(self):
        assert tbv.format_mom_yen(-50000.0) == "-¥50,000"

    def test_zero(self):
        assert tbv.format_mom_yen(0.0) == "±¥0"

    def test_none(self):
        # st.metric は delta=None で省略表示するため None を返す
        assert tbv.format_mom_yen(None) is None


class TestFormatMomPt:
    def test_positive(self):
        assert tbv.format_mom_pt(10.5) == "+10.5pt"

    def test_negative(self):
        assert tbv.format_mom_pt(-7.2) == "-7.2pt"

    def test_zero(self):
        assert tbv.format_mom_pt(0.0) == "±0.0pt"

    def test_none(self):
        assert tbv.format_mom_pt(None) is None


class TestRenderKpiRow:
    """Issue #257: render_kpi_row の mom 引数による前月比 delta 表示テスト。"""

    @staticmethod
    def _setup_st_mock(st_mock):
        cols = (MagicMock(), MagicMock(), MagicMock())
        st_mock.columns.return_value = cols
        return cols

    def test_mom_none_no_delta(self):
        """mom=None (デフォルト) で従来通り delta 引数なし → backward compatible"""
        summary = {
            "total_budget": 1000000.0, "total_actual": 800000.0,
            "overall_rate": 80.0, "overall_diff": -200000.0,
        }
        from unittest.mock import patch
        with patch("streamlit.columns") as mock_cols:
            cols = (MagicMock(), MagicMock(), MagicMock())
            mock_cols.return_value = cols
            tbv.render_kpi_row(summary)  # mom 引数なし
        # 全 metric 呼び出しの delta 引数が None
        all_calls = [c for col in cols for c in col.metric.call_args_list]
        deltas = [c.kwargs.get("delta") for c in all_calls]
        non_none = [d for d in deltas if d is not None]
        assert non_none == [], f"mom=None で delta が渡っている: {non_none}"

    def test_mom_present_delta_passed(self):
        """mom={...} 渡しで実額 / 達成率 metric の delta 引数に MoM 値が入る"""
        summary = {
            "total_budget": 1000000.0, "total_actual": 800000.0,
            "overall_rate": 80.0, "overall_diff": -200000.0,
        }
        mom = {"actual_delta": 100000.0, "rate_delta": 5.0}
        from unittest.mock import patch
        with patch("streamlit.columns") as mock_cols:
            cols = (MagicMock(), MagicMock(), MagicMock())
            mock_cols.return_value = cols
            tbv.render_kpi_row(summary, mom=mom)
        all_calls = [c for col in cols for c in col.metric.call_args_list]
        deltas = [c.kwargs.get("delta") for c in all_calls]
        assert "+¥100,000" in deltas, f"実額 MoM delta なし: {deltas}"
        assert "+5.0pt" in deltas, f"達成率 MoM delta なし: {deltas}"


class TestAttachMomColumns:
    """Issue #257: DataFrame に前月比 (actual_delta / rate_delta) 列を追加する純粋関数。"""

    def test_both_rows_present(self):
        current = pd.DataFrame({
            "leader_team": ["L1", "L2"],
            "actual_amount": [500000.0, 300000.0],
            "achievement_rate": [90.0, 60.0],
        })
        previous = pd.DataFrame({
            "leader_team": ["L1", "L2"],
            "actual_amount": [400000.0, 350000.0],
            "achievement_rate": [80.0, 70.0],
        })
        result = tbv.attach_mom_columns(current, previous, key_col="leader_team")
        assert result.loc[0, "actual_delta"] == 100000.0
        assert result.loc[0, "rate_delta"] == 10.0
        assert result.loc[1, "actual_delta"] == -50000.0
        assert result.loc[1, "rate_delta"] == -10.0

    def test_previous_none(self):
        current = pd.DataFrame({
            "leader_team": ["L1"], "actual_amount": [500000.0],
            "achievement_rate": [90.0],
        })
        result = tbv.attach_mom_columns(current, None, key_col="leader_team")
        # None or NaN (pandas の dtype 変換で NaN になる可能性、両方許容)
        assert pd.isna(result.loc[0, "actual_delta"]) or result.loc[0, "actual_delta"] is None
        assert pd.isna(result.loc[0, "rate_delta"]) or result.loc[0, "rate_delta"] is None

    def test_previous_empty(self):
        current = pd.DataFrame({
            "leader_team": ["L1"], "actual_amount": [500000.0],
            "achievement_rate": [90.0],
        })
        result = tbv.attach_mom_columns(current, pd.DataFrame(), key_col="leader_team")
        assert pd.isna(result.loc[0, "actual_delta"]) or result.loc[0, "actual_delta"] is None
        assert pd.isna(result.loc[0, "rate_delta"]) or result.loc[0, "rate_delta"] is None

    def test_key_only_in_current(self):
        """前月にない leader_team は delta=None (新規隊扱い)"""
        current = pd.DataFrame({
            "leader_team": ["L1", "L_NEW"],
            "actual_amount": [500000.0, 100000.0],
            "achievement_rate": [90.0, 50.0],
        })
        previous = pd.DataFrame({
            "leader_team": ["L1"], "actual_amount": [400000.0],
            "achievement_rate": [80.0],
        })
        result = tbv.attach_mom_columns(current, previous, key_col="leader_team")
        assert result.loc[0, "actual_delta"] == 100000.0
        # 前月にない L_NEW は None (pandas dtype 変換で NaN になる可能性、両方許容)
        assert pd.isna(result.loc[1, "actual_delta"]) or result.loc[1, "actual_delta"] is None
        assert pd.isna(result.loc[1, "rate_delta"]) or result.loc[1, "rate_delta"] is None
