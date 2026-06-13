"""team_budget_cache の wrapper + invalidation テスト (Step 2)。"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from lib.team_budget_repo import TeamBudgetRow


@pytest.fixture(autouse=True)
def _reset_caches():
    """各テスト前後で cache を初期化 (st.cache_data の TTL 依存を排除)"""
    from lib import team_budget_cache as cache_mod
    cache_mod.load_team_budget_cached.clear()
    cache_mod.load_other_team_budgets_cached.clear()
    yield
    cache_mod.load_team_budget_cached.clear()
    cache_mod.load_other_team_budgets_cached.clear()


class TestLoadTeamBudgetCached:
    def test_delegates_to_repo(self):
        from lib import team_budget_cache as cache_mod
        row = TeamBudgetRow(
            year=2026, month=5, team="A 隊",
            budget_amount=1000.0, memo=None, version=1,
            updated_at=datetime(2026, 6, 13, tzinfo=timezone.utc),
            updated_by="admin@example.com",
        )
        with patch("lib.team_budget_cache.load_team_budget", return_value=row) as m, \
             patch("lib.team_budget_cache.get_bq_client", return_value=MagicMock()):
            result = cache_mod.load_team_budget_cached(2026, 5, "A 隊")
        assert result == row
        m.assert_called_once()

    def test_returns_none_when_repo_returns_none(self):
        from lib import team_budget_cache as cache_mod
        with patch("lib.team_budget_cache.load_team_budget", return_value=None), \
             patch("lib.team_budget_cache.get_bq_client", return_value=MagicMock()):
            result = cache_mod.load_team_budget_cached(2026, 5, "X 隊")
        assert result is None


class TestLoadOtherTeamBudgetsCached:
    def test_delegates_to_repo(self):
        from lib import team_budget_cache as cache_mod
        with patch(
            "lib.team_budget_cache.load_other_team_budgets_in_leader",
            return_value=3000000.0,
        ) as m, patch("lib.team_budget_cache.get_bq_client", return_value=MagicMock()):
            result = cache_mod.load_other_team_budgets_cached(
                2026, 5, "シロロ統括隊", "A 隊",
            )
        assert result == 3000000.0
        m.assert_called_once()


class TestInvalidateTeamBudgetCaches:
    def test_clears_all_listed_wrappers(self):
        """Codex 指摘 j: clear 対象一覧に漏れがないことを mock で検証"""
        from lib import team_budget_cache as cache_mod

        clear_calls = []
        # cache_data wrapper の .clear を mock 化
        targets = [
            "load_team_budget_cached",
            "load_other_team_budgets_cached",
            "load_team_budget_actuals",
            "load_active_teams",
            "load_active_leader_teams",
            "load_team_monthly_eval",
            "compute_current_hashes",
            "load_leader_team_monthly_budgets",
        ]
        patches = []
        for name in targets:
            fn = getattr(cache_mod, name)
            clear_mock = MagicMock(side_effect=lambda n=name: clear_calls.append(n))
            patches.append(patch.object(fn, "clear", clear_mock))

        for p in patches:
            p.start()
        try:
            cache_mod.invalidate_team_budget_caches()
        finally:
            for p in patches:
                p.stop()

        # 全 8 wrapper の clear が呼ばれた
        assert set(clear_calls) == set(targets)

    def test_no_op_when_clear_missing(self):
        """cache_data wrap されていない関数 (.clear AttributeError) は no-op"""
        from lib import team_budget_cache as cache_mod
        # raw 関数 (cache_data wrap されていないもの) を一時差し替え
        plain_fn = MagicMock(spec=[])  # spec=[] で属性なし → .clear AttributeError
        with patch.object(cache_mod, "load_team_budget_cached", plain_fn):
            # 例外を投げず通る
            cache_mod.invalidate_team_budget_caches()
