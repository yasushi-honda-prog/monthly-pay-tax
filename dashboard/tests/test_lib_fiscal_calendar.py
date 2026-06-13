"""fiscal_calendar の pure helper テスト (Issue #248 T1)。

設計: docs/specs/2026-06-14-leader-team-monthly-budget.md §5.1 / AC11
"""

from __future__ import annotations

import pytest

from lib.fiscal_calendar import (
    calendar_to_fiscal,
    fiscal_quarter_to_months,
    fiscal_year_month_range,
    fiscal_year_to_calendar_months,
)


class TestFiscalYearToCalendarMonths:
    """FY を構成する 12 ヶ月の (calendar_year, month) tuple を Q1 順で返す。"""

    def test_fy2026_returns_12_months_starting_from_2025_nov(self):
        """FY2026 → [(2025,11),(2025,12),(2026,1),...,(2026,10)] の 12 ヶ月。"""
        result = fiscal_year_to_calendar_months(2026)
        assert len(result) == 12
        assert result[0] == (2025, 11)  # Q1 start
        assert result[1] == (2025, 12)
        assert result[2] == (2026, 1)
        assert result[-1] == (2026, 10)  # Q4 end

    def test_fy2026_quarters_in_order(self):
        """Q1=(11,12,1) Q2=(2,3,4) Q3=(5,6,7) Q4=(8,9,10) の順。"""
        result = fiscal_year_to_calendar_months(2026)
        # Q1
        assert result[0:3] == [(2025, 11), (2025, 12), (2026, 1)]
        # Q2
        assert result[3:6] == [(2026, 2), (2026, 3), (2026, 4)]
        # Q3
        assert result[6:9] == [(2026, 5), (2026, 6), (2026, 7)]
        # Q4
        assert result[9:12] == [(2026, 8), (2026, 9), (2026, 10)]

    def test_fy2027_boundary(self):
        """FY2027 → [(2026,11),(2026,12),(2027,1),...,(2027,10)]。"""
        result = fiscal_year_to_calendar_months(2027)
        assert result[0] == (2026, 11)
        assert result[2] == (2027, 1)
        assert result[-1] == (2027, 10)


class TestCalendarToFiscal:
    """暦年月 → (fiscal_year, fiscal_quarter) (BQ fiscal_quarter UDF と整合)。"""

    def test_2025_11_is_fy2026_q1(self):
        assert calendar_to_fiscal(2025, 11) == (2026, 1)

    def test_2025_12_is_fy2026_q1(self):
        assert calendar_to_fiscal(2025, 12) == (2026, 1)

    def test_2026_1_is_fy2026_q1(self):
        assert calendar_to_fiscal(2026, 1) == (2026, 1)

    def test_2026_2_is_fy2026_q2(self):
        assert calendar_to_fiscal(2026, 2) == (2026, 2)

    def test_2026_5_is_fy2026_q3(self):
        assert calendar_to_fiscal(2026, 5) == (2026, 3)

    def test_2026_8_is_fy2026_q4(self):
        assert calendar_to_fiscal(2026, 8) == (2026, 4)

    def test_2026_10_is_fy2026_q4(self):
        assert calendar_to_fiscal(2026, 10) == (2026, 4)

    def test_2026_11_is_fy2027_q1(self):
        """2026/11 は FY2027 の Q1 開始。"""
        assert calendar_to_fiscal(2026, 11) == (2027, 1)


class TestFiscalQuarterToMonths:
    """fiscal_quarter → 構成月リスト。"""

    def test_q1(self):
        assert fiscal_quarter_to_months(1) == [11, 12, 1]

    def test_q2(self):
        assert fiscal_quarter_to_months(2) == [2, 3, 4]

    def test_q3(self):
        assert fiscal_quarter_to_months(3) == [5, 6, 7]

    def test_q4(self):
        assert fiscal_quarter_to_months(4) == [8, 9, 10]

    def test_invalid_quarter_raises(self):
        with pytest.raises(ValueError):
            fiscal_quarter_to_months(5)
        with pytest.raises(ValueError):
            fiscal_quarter_to_months(0)


class TestFiscalYearMonthRange:
    """load_team_budget_actuals に渡せる範囲を返す (年跨ぎ対応)。"""

    def test_fy2026_returns_year_month_range(self):
        """FY2026 → (2025, 2026, 11, 10): year_start=2025 year_end=2026 month_start=11 month_end=10."""
        year_start, year_end, month_start, month_end = fiscal_year_month_range(2026)
        assert year_start == 2025
        assert year_end == 2026
        assert month_start == 11
        assert month_end == 10

    def test_fy2027_returns_year_month_range(self):
        year_start, year_end, month_start, month_end = fiscal_year_month_range(2027)
        assert year_start == 2026
        assert year_end == 2027
        assert month_start == 11
        assert month_end == 10


class TestRoundTrip:
    """fiscal_year_to_calendar_months と calendar_to_fiscal の往復一致。"""

    def test_round_trip_fy2026(self):
        """FY2026 の全 12 ヶ月で round trip 一致 (fiscal_year 部分のみ)。"""
        for cy, cm in fiscal_year_to_calendar_months(2026):
            fy, _fq = calendar_to_fiscal(cy, cm)
            assert fy == 2026, f"({cy},{cm}) round trip: expected FY2026, got FY{fy}"
