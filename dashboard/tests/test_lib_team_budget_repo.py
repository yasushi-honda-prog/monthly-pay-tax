"""team_budget_repo の dataclass / Exception + 実装関数テスト (Step 1a + 1b-4)。"""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from lib.team_budget_repo import (
    TeamBudgetRow,
    UpsertConflict,
    delete_team_budget,
    load_other_team_budgets_in_leader,
    load_team_budget,
    upsert_team_budget,
)


# ---- mock helpers ----


def _select_row_mock(client, row):
    """client.query(SELECT).result() が [row] を返す mock"""
    job = MagicMock()
    job.result.return_value = [row] if row is not None else []
    client.query.return_value = job


def _select_no_rows_mock(client):
    job = MagicMock()
    job.result.return_value = []
    client.query.return_value = job


def _dml_then_select_mock(client, affected_rows, post_select_row):
    """DML query → SELECT query の順次 mock"""
    dml_job = MagicMock()
    dml_job.num_dml_affected_rows = affected_rows
    dml_job.result.return_value = []  # DML は result も呼ぶ

    select_job = MagicMock()
    select_job.result.return_value = [post_select_row] if post_select_row else []
    client.query.side_effect = [dml_job, select_job]


def _make_row(year=2026, month=5, team="A 隊", budget=1000.0, memo="m",
              version=1, updated_at=None, updated_by="admin@example.com"):
    return {
        "year": year,
        "month": month,
        "team": team,
        "budget_amount": Decimal(str(budget)),
        "memo": memo,
        "version": version,
        "updated_at": updated_at or datetime(2026, 6, 13, tzinfo=timezone.utc),
        "updated_by": updated_by,
    }


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


class TestLoadTeamBudget:
    def test_returns_row_when_exists(self):
        client = MagicMock()
        _select_row_mock(client, _make_row(budget=1500.0, version=2))
        row = load_team_budget(client, 2026, 5, "A 隊")
        assert row is not None
        assert row.year == 2026
        assert row.month == 5
        assert row.team == "A 隊"
        assert row.budget_amount == 1500.0
        assert row.version == 2

    def test_returns_none_when_not_exists(self):
        client = MagicMock()
        _select_no_rows_mock(client)
        row = load_team_budget(client, 2026, 5, "X 隊")
        assert row is None

    def test_uses_pk_params(self):
        client = MagicMock()
        _select_no_rows_mock(client)
        load_team_budget(client, 2026, 7, "Z 隊")
        params = client.query.call_args.kwargs["job_config"].query_parameters
        names = {p.name: p.value for p in params}
        assert names == {"year": 2026, "month": 7, "team": "Z 隊"}


class TestUpsertTeamBudgetInsert:
    """expected_version=None で INSERT 経路"""

    def test_insert_success_returns_row(self):
        client = MagicMock()
        _dml_then_select_mock(
            client,
            affected_rows=1,
            post_select_row=_make_row(budget=1000.0, version=1),
        )
        result = upsert_team_budget(
            client, year=2026, month=5, team="A 隊",
            budget_amount=1000.0, memo="新規入力",
            expected_version=None, actor="admin@example.com",
        )
        assert result.budget_amount == 1000.0
        assert result.version == 1

    def test_insert_conflict_when_affected_zero(self):
        """INSERT で既存 row があると NOT EXISTS 句で 0 件挿入 → conflict"""
        client = MagicMock()
        dml_job = MagicMock()
        dml_job.num_dml_affected_rows = 0
        client.query.return_value = dml_job
        with pytest.raises(UpsertConflict, match="INSERT conflict"):
            upsert_team_budget(
                client, year=2026, month=5, team="A 隊",
                budget_amount=1000.0, memo=None,
                expected_version=None, actor="admin@example.com",
            )

    def test_insert_sql_uses_not_exists(self):
        client = MagicMock()
        _dml_then_select_mock(client, 1, _make_row())
        upsert_team_budget(
            client, year=2026, month=5, team="A 隊",
            budget_amount=1000.0, memo=None,
            expected_version=None, actor="admin@example.com",
        )
        sql = client.query.call_args_list[0].args[0]
        assert "INSERT INTO" in sql
        assert "WHERE NOT EXISTS" in sql

    def test_insert_records_actor_in_created_and_updated_by(self):
        client = MagicMock()
        _dml_then_select_mock(client, 1, _make_row())
        upsert_team_budget(
            client, year=2026, month=5, team="A 隊",
            budget_amount=1000.0, memo=None,
            expected_version=None, actor="honda@example.com",
        )
        params = client.query.call_args_list[0].kwargs["job_config"].query_parameters
        actor_param = [p for p in params if p.name == "actor"][0]
        assert actor_param.value == "honda@example.com"


class TestUpsertTeamBudgetUpdate:
    """expected_version=N で UPDATE 経路"""

    def test_update_success_returns_new_row(self):
        client = MagicMock()
        _dml_then_select_mock(
            client,
            affected_rows=1,
            post_select_row=_make_row(budget=2000.0, version=3),
        )
        result = upsert_team_budget(
            client, year=2026, month=5, team="A 隊",
            budget_amount=2000.0, memo="改訂",
            expected_version=2, actor="admin@example.com",
        )
        assert result.budget_amount == 2000.0
        assert result.version == 3

    def test_update_conflict_when_version_mismatch(self):
        client = MagicMock()
        dml_job = MagicMock()
        dml_job.num_dml_affected_rows = 0
        client.query.return_value = dml_job
        with pytest.raises(UpsertConflict, match="version mismatch"):
            upsert_team_budget(
                client, year=2026, month=5, team="A 隊",
                budget_amount=2000.0, memo=None,
                expected_version=2, actor="admin@example.com",
            )

    def test_update_sql_uses_version_filter(self):
        client = MagicMock()
        _dml_then_select_mock(client, 1, _make_row(version=3))
        upsert_team_budget(
            client, year=2026, month=5, team="A 隊",
            budget_amount=2000.0, memo=None,
            expected_version=2, actor="admin@example.com",
        )
        sql = client.query.call_args_list[0].args[0]
        assert "UPDATE" in sql
        assert "version = version + 1" in sql
        assert "version = @expected_version" in sql

    def test_post_select_returns_latest_via_direct_read(self):
        """Codex 指摘 i: DML 後に load_team_budget で直 SELECT、cache 経由しない"""
        client = MagicMock()
        _dml_then_select_mock(
            client,
            affected_rows=1,
            post_select_row=_make_row(budget=2000.0, version=3),
        )
        upsert_team_budget(
            client, year=2026, month=5, team="A 隊",
            budget_amount=2000.0, memo=None,
            expected_version=2, actor="admin@example.com",
        )
        # 2 query: DML → SELECT
        assert client.query.call_count == 2
        select_sql = client.query.call_args_list[1].args[0]
        assert "SELECT" in select_sql
        assert "team_budgets" in select_sql


class TestDeleteTeamBudget:
    def test_delete_success(self):
        client = MagicMock()
        dml_job = MagicMock()
        dml_job.num_dml_affected_rows = 1
        client.query.return_value = dml_job
        delete_team_budget(
            client, year=2026, month=5, team="A 隊",
            expected_version=1, actor="admin@example.com",
        )
        sql = client.query.call_args.args[0]
        assert "DELETE FROM" in sql
        assert "team_budgets" in sql

    def test_delete_conflict_when_version_mismatch(self):
        client = MagicMock()
        dml_job = MagicMock()
        dml_job.num_dml_affected_rows = 0
        client.query.return_value = dml_job
        with pytest.raises(UpsertConflict, match="version mismatch on delete"):
            delete_team_budget(
                client, year=2026, month=5, team="A 隊",
                expected_version=1, actor="admin@example.com",
            )

    def test_delete_uses_pk_and_version_params(self):
        client = MagicMock()
        dml_job = MagicMock()
        dml_job.num_dml_affected_rows = 1
        client.query.return_value = dml_job
        delete_team_budget(
            client, year=2026, month=7, team="Z 隊",
            expected_version=5, actor="admin@example.com",
        )
        params = client.query.call_args.kwargs["job_config"].query_parameters
        names = {p.name: p.value for p in params}
        assert names == {"year": 2026, "month": 7, "team": "Z 隊", "expected_version": 5}


class TestLoadOtherTeamBudgetsInLeader:
    def _sum_mock(self, client, total):
        job = MagicMock()
        job.result.return_value = [{"total": total}] if total is not None else []
        client.query.return_value = job

    def test_returns_sum(self):
        client = MagicMock()
        self._sum_mock(client, Decimal("3000000"))
        result = load_other_team_budgets_in_leader(
            client, year=2026, month=5,
            leader_team="シロロ統括隊", exclude_team="A 隊",
        )
        assert result == 3000000.0

    def test_returns_zero_when_no_rows(self):
        client = MagicMock()
        self._sum_mock(client, None)
        result = load_other_team_budgets_in_leader(
            client, year=2026, month=5,
            leader_team="シロロ統括隊", exclude_team="A 隊",
        )
        assert result == 0.0

    def test_returns_zero_when_sum_is_none(self):
        """IFNULL(SUM, 0) で None は来ない想定だが防御的に"""
        client = MagicMock()
        job = MagicMock()
        job.result.return_value = [{"total": None}]
        client.query.return_value = job
        result = load_other_team_budgets_in_leader(
            client, year=2026, month=5,
            leader_team="シロロ統括隊", exclude_team="A 隊",
        )
        assert result == 0.0

    def test_sql_inner_joins_hierarchy_with_operating_filter(self):
        """Codex 指摘 i: operating 配下に限定する INNER JOIN を必須化"""
        client = MagicMock()
        self._sum_mock(client, Decimal("0"))
        load_other_team_budgets_in_leader(
            client, year=2026, month=5,
            leader_team="シロロ統括隊", exclude_team="A 隊",
        )
        sql = client.query.call_args.args[0]
        assert "INNER JOIN" in sql
        assert "team_hierarchy" in sql
        assert "leader_team_type = 'operating'" in sql
        assert "b.team != @exclude_team" in sql

    def test_excludes_self_team(self):
        client = MagicMock()
        self._sum_mock(client, Decimal("0"))
        load_other_team_budgets_in_leader(
            client, year=2026, month=5,
            leader_team="シロロ統括隊", exclude_team="A 隊",
        )
        params = client.query.call_args.kwargs["job_config"].query_parameters
        excl = [p for p in params if p.name == "exclude_team"][0]
        assert excl.value == "A 隊"
