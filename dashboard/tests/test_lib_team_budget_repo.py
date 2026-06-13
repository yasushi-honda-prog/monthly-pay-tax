"""team_budget_repo の dataclass / Exception 定義テスト (Step 1a)。

実装関数 (load / upsert / delete / load_other) のテストは Step 1b で追加する。
"""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import datetime, timezone

import pytest

from lib.team_budget_repo import TeamBudgetRow, UpsertConflict


class TestTeamBudgetRow:
    """TeamBudgetRow dataclass の構造テスト"""

    def test_construct_with_all_fields(self):
        row = TeamBudgetRow(
            year=2026,
            month=5,
            team="A 隊",
            budget_amount=1000000.0,
            memo="初期入力",
            version=1,
            updated_at=datetime(2026, 6, 13, 9, 0, tzinfo=timezone.utc),
            updated_by="sanwaminamihonda@gmail.com",
        )
        assert row.year == 2026
        assert row.month == 5
        assert row.team == "A 隊"
        assert row.budget_amount == 1000000.0
        assert row.memo == "初期入力"
        assert row.version == 1
        assert row.updated_by == "sanwaminamihonda@gmail.com"

    def test_memo_can_be_none(self):
        row = TeamBudgetRow(
            year=2026, month=5, team="A 隊", budget_amount=0.0,
            memo=None, version=1,
            updated_at=datetime(2026, 6, 13, tzinfo=timezone.utc),
            updated_by="admin@example.com",
        )
        assert row.memo is None

    def test_frozen_immutable(self):
        """frozen=True なので mutation 不可"""
        row = TeamBudgetRow(
            year=2026, month=5, team="A 隊", budget_amount=1000.0,
            memo=None, version=1,
            updated_at=datetime(2026, 6, 13, tzinfo=timezone.utc),
            updated_by="admin@example.com",
        )
        with pytest.raises(FrozenInstanceError):
            row.budget_amount = 2000.0  # type: ignore[misc]


class TestUpsertConflict:
    """UpsertConflict 例外の構造テスト"""

    def test_is_exception_subclass(self):
        assert issubclass(UpsertConflict, Exception)

    def test_can_be_raised_with_message(self):
        with pytest.raises(UpsertConflict, match="version mismatch"):
            raise UpsertConflict("version mismatch")
