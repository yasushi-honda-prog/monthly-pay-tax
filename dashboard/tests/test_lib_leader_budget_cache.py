"""leader_budget_cache の cache + invalidation テスト (Issue #248 T6 / AC9)。

設計: docs/specs/2026-06-14-leader-team-monthly-budget.md §5.3 / AC9

Codex M2 反映: invalidate_all は影響先 6 関数を clear。
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from lib import leader_budget_cache


class TestCachedFetchYearly:
    def test_calls_underlying_fetch_yearly(self):
        with patch("lib.leader_budget_cache.fetch_yearly") as mock_fetch, \
             patch("lib.leader_budget_cache.get_bq_client") as mock_client:
            mock_fetch.return_value = []
            leader_budget_cache.cached_fetch_yearly.clear()
            result = leader_budget_cache.cached_fetch_yearly(2026)
            assert result == []
            mock_fetch.assert_called_once()
            # fiscal_year=2026 で呼ばれたか
            assert mock_fetch.call_args.args[1] == 2026


class TestCachedLoadQuarterlySeed:
    def test_calls_underlying_loader(self):
        with patch(
            "lib.leader_budget_cache.load_leader_team_quarterly_budgets_for_seed"
        ) as mock_loader:
            mock_loader.return_value = MagicMock()  # DataFrame mock
            leader_budget_cache.cached_load_quarterly_seed.clear()
            leader_budget_cache.cached_load_quarterly_seed(2026)
            mock_loader.assert_called_with(2026)


class TestCachedLoadActiveLeaderTeams:
    def test_calls_underlying_loader(self):
        with patch(
            "lib.leader_budget_cache.load_active_leader_teams_for_budget_input"
        ) as mock_loader, \
             patch("lib.leader_budget_cache.get_bq_client"):
            mock_loader.return_value = ["L1"]
            leader_budget_cache.cached_load_active_leader_teams_for_input.clear()
            result = leader_budget_cache.cached_load_active_leader_teams_for_input(2026)
            assert result == ["L1"]


class TestInvalidateAll:
    """AC9: 影響先 6 関数の clear を検証"""

    def test_clears_all_6_targets(self):
        """Codex M2 反映: 4 関数固定ではなく影響先ベース 6 関数を clear"""
        targets = [
            "cached_fetch_yearly",
            "cached_load_quarterly_seed",
            "cached_load_active_leader_teams_for_input",
        ]
        bq_targets = [
            "load_leader_team_yearly_monthly_budgets",
            "load_leader_team_monthly_budgets",
            "load_active_leader_teams",
        ]
        with patch.object(leader_budget_cache.cached_fetch_yearly, "clear") as m1, \
             patch.object(leader_budget_cache.cached_load_quarterly_seed, "clear") as m2, \
             patch.object(
                 leader_budget_cache.cached_load_active_leader_teams_for_input, "clear"
             ) as m3, \
             patch.object(
                 leader_budget_cache.load_leader_team_yearly_monthly_budgets, "clear"
             ) as m4, \
             patch.object(
                 leader_budget_cache.load_leader_team_monthly_budgets, "clear"
             ) as m5, \
             patch.object(
                 leader_budget_cache.load_active_leader_teams, "clear"
             ) as m6:
            leader_budget_cache.invalidate_all(2026)
            assert m1.called, "cached_fetch_yearly.clear not called"
            assert m2.called, "cached_load_quarterly_seed.clear not called"
            assert m3.called, "cached_load_active_leader_teams_for_input.clear not called"
            assert m4.called, "load_leader_team_yearly_monthly_budgets.clear not called"
            assert m5.called, "load_leader_team_monthly_budgets.clear not called"
            assert m6.called, "load_active_leader_teams.clear not called"

    def test_no_error_when_clear_attribute_missing(self):
        """AttributeError が出ても他の clear は実行される (defensive)"""
        # 何も patch せずに呼んでも例外を出さない
        leader_budget_cache.invalidate_all(2026)  # no raise

    def test_accepts_fiscal_year_argument(self):
        """fiscal_year 引数は将来の部分 clear 用 (Codex R10 reflect)"""
        leader_budget_cache.invalidate_all(fiscal_year=2026)
        leader_budget_cache.invalidate_all(fiscal_year=2027)
        # no raise
