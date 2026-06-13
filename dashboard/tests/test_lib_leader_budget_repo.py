"""leader_budget_repo の DML / dataclass テスト (Issue #248 T5a/T5b/T5c)。

設計: docs/specs/2026-06-14-leader-team-monthly-budget.md §5.2 / AC6-AC8, AC14

team_budget_repo パターン踏襲 + bulk 操作用 BulkUpsertResult + defensive ROW_NUMBER。
"""

from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock

import pytest

from lib.leader_budget_repo import (
    BulkUpsertResult,
    LeaderBudgetRow,
    UpsertConflict,
    delete,
    fetch_one,
    fetch_yearly,
    load_active_leader_teams_for_budget_input,
    preview_seed_from_quarterly,
    seed_from_quarterly,
    upsert,
)


# --------- Helpers ---------


def _make_client_with_rows(rows):
    """client.query(sql).result() が rows を返す"""
    client = MagicMock()
    job = MagicMock()
    job.result.return_value = rows
    client.query.return_value = job
    return client


def _row(month=5, leader_team="L1", amount=100000, version=1):
    """BQ Row 模倣 (dict 形式で row["x"] アクセス可能)"""
    return {
        "fiscal_year": 2026,
        "month": month,
        "leader_team": leader_team,
        "budget_amount": amount,
        "version": version,
        "created_at": datetime(2026, 1, 1),
        "created_by": "user@example.com",
        "updated_at": datetime(2026, 1, 1),
        "updated_by": "user@example.com",
    }


# --------- DataClasses ---------


class TestLeaderBudgetRow:
    def test_frozen_and_int_amount(self):
        """budget_amount は int (Codex L1)、frozen dataclass。"""
        row = LeaderBudgetRow(
            fiscal_year=2026, month=5, leader_team="L1",
            budget_amount=100000, version=1,
            created_at=datetime(2026, 1, 1), created_by="u@e.com",
            updated_at=datetime(2026, 1, 1), updated_by="u@e.com",
        )
        assert row.budget_amount == 100000
        assert isinstance(row.budget_amount, int)
        with pytest.raises(Exception):
            row.budget_amount = 200000  # frozen のため変更不可


class TestBulkUpsertResult:
    """6×12=72 セル bulk edit の結果集約 (PR #246 と差別化)。"""

    def test_default_empty(self):
        result = BulkUpsertResult()
        assert result.saved_count == 0
        assert result.deleted_count == 0
        assert result.conflicts == []
        assert result.errors == []

    def test_with_values(self):
        result = BulkUpsertResult(
            saved_count=10,
            deleted_count=2,
            conflicts=[("L1", 5)],
            errors=[("L2", 6, "BQ timeout")],
        )
        assert result.saved_count == 10
        assert result.deleted_count == 2
        assert result.conflicts == [("L1", 5)]
        assert result.errors == [("L2", 6, "BQ timeout")]


class TestUpsertConflict:
    def test_is_exception(self):
        assert issubclass(UpsertConflict, Exception)


# --------- fetch_yearly ---------


class TestFetchYearly:
    def test_returns_list_of_rows(self):
        client = _make_client_with_rows([_row(month=11), _row(month=12)])
        result = fetch_yearly(client, 2026)
        assert len(result) == 2
        assert all(isinstance(r, LeaderBudgetRow) for r in result)
        assert result[0].month == 11

    def test_empty_when_no_rows(self):
        client = _make_client_with_rows([])
        result = fetch_yearly(client, 2026)
        assert result == []

    def test_sql_uses_row_number_defensive(self):
        """Codex H2: ROW_NUMBER で defensive 正規化"""
        client = _make_client_with_rows([])
        fetch_yearly(client, 2026)
        sql = client.query.call_args.args[0]
        assert "ROW_NUMBER" in sql
        assert "PARTITION BY fiscal_year, month, leader_team" in sql
        assert "leader_team_monthly_budgets" in sql

    def test_sql_filter_fiscal_year(self):
        client = _make_client_with_rows([])
        fetch_yearly(client, 2027)
        job_config = client.query.call_args.kwargs["job_config"]
        params = {p.name: p.value for p in job_config.query_parameters}
        assert params["fiscal_year"] == 2027

    def test_row_conversion(self):
        client = _make_client_with_rows([_row(amount=500000)])
        result = fetch_yearly(client, 2026)
        assert result[0].budget_amount == 500000
        assert isinstance(result[0].budget_amount, int)


# --------- fetch_one ---------


class TestFetchOne:
    def test_returns_row_when_exists(self):
        client = _make_client_with_rows([_row(month=7, leader_team="L1")])
        result = fetch_one(client, 2026, 7, "L1")
        assert result is not None
        assert result.month == 7
        assert result.leader_team == "L1"

    def test_returns_none_when_not_exists(self):
        client = _make_client_with_rows([])
        result = fetch_one(client, 2026, 7, "L1")
        assert result is None

    def test_sql_with_full_pk_params(self):
        client = _make_client_with_rows([])
        fetch_one(client, 2026, 7, "L1")
        job_config = client.query.call_args.kwargs["job_config"]
        params = {p.name: p.value for p in job_config.query_parameters}
        assert params["fiscal_year"] == 2026
        assert params["month"] == 7
        assert params["leader_team"] == "L1"


# --------- load_active_leader_teams_for_budget_input ---------


class TestLoadActiveLeaderTeams:
    """Codex L2: load_other_leader_teams → load_active_leader_teams_for_budget_input rename"""

    def test_returns_distinct_leader_teams(self):
        rows = [{"leader_team": "L1"}, {"leader_team": "L2"}]
        client = _make_client_with_rows(rows)
        result = load_active_leader_teams_for_budget_input(client, 2026)
        assert result == ["L1", "L2"]

    def test_empty_when_no_data(self):
        client = _make_client_with_rows([])
        result = load_active_leader_teams_for_budget_input(client, 2026)
        assert result == []

    def test_sql_uses_distinct(self):
        client = _make_client_with_rows([])
        load_active_leader_teams_for_budget_input(client, 2026)
        sql = client.query.call_args.args[0]
        assert "DISTINCT" in sql
        assert "leader_team IS NOT NULL" in sql


# --------- upsert ---------


def _client_with_dml_and_fetch(affected: int, fetched_row=None):
    """upsert/delete 用: DML 完了後の fetch_one 結果も模倣"""
    client = MagicMock()
    # 1 回目の query は DML、2 回目 (fetch_one) は SELECT
    dml_job = MagicMock()
    dml_job.num_dml_affected_rows = affected
    dml_job.result.return_value = None

    fetch_job = MagicMock()
    fetch_job.result.return_value = [fetched_row] if fetched_row else []
    # 連続呼出で異なる job を返す
    client.query.side_effect = [dml_job, fetch_job]
    return client


class TestUpsertInsert:
    """新規 INSERT (expected_version=None)"""

    def test_insert_success_returns_row(self):
        client = _client_with_dml_and_fetch(affected=1, fetched_row=_row(amount=100000))
        result = upsert(
            client,
            fiscal_year=2026, month=5, leader_team="L1",
            budget_amount=100000, expected_version=None,
            actor_email="admin@example.com",
        )
        assert isinstance(result, LeaderBudgetRow)
        assert result.budget_amount == 100000

    def test_insert_conflict_when_existing(self):
        """既存 row あり (NOT EXISTS の WHERE 句で 0 件挿入)"""
        client = MagicMock()
        dml_job = MagicMock()
        dml_job.num_dml_affected_rows = 0
        dml_job.result.return_value = None
        client.query.return_value = dml_job

        with pytest.raises(UpsertConflict, match="INSERT conflict"):
            upsert(
                client,
                fiscal_year=2026, month=5, leader_team="L1",
                budget_amount=100000, expected_version=None,
                actor_email="admin@example.com",
            )

    def test_insert_sql_has_insert_and_not_exists(self):
        client = _client_with_dml_and_fetch(affected=1, fetched_row=_row())
        upsert(
            client,
            fiscal_year=2026, month=5, leader_team="L1",
            budget_amount=100000, expected_version=None,
            actor_email="admin@example.com",
        )
        # 1 回目の query が INSERT SQL
        first_call_sql = client.query.call_args_list[0].args[0]
        assert "INSERT INTO" in first_call_sql
        assert "WHERE NOT EXISTS" in first_call_sql


class TestUpsertUpdate:
    """既存 UPDATE (expected_version=int)"""

    def test_update_success_returns_row(self):
        client = _client_with_dml_and_fetch(
            affected=1, fetched_row=_row(amount=200000, version=2)
        )
        result = upsert(
            client,
            fiscal_year=2026, month=5, leader_team="L1",
            budget_amount=200000, expected_version=1,
            actor_email="admin@example.com",
        )
        assert result.budget_amount == 200000

    def test_update_conflict_version_mismatch(self):
        """version 不一致 (別 admin の同時編集)"""
        client = MagicMock()
        dml_job = MagicMock()
        dml_job.num_dml_affected_rows = 0
        dml_job.result.return_value = None
        client.query.return_value = dml_job

        with pytest.raises(UpsertConflict, match="UPDATE conflict"):
            upsert(
                client,
                fiscal_year=2026, month=5, leader_team="L1",
                budget_amount=200000, expected_version=1,
                actor_email="admin@example.com",
            )

    def test_update_sql_uses_version_check(self):
        client = _client_with_dml_and_fetch(
            affected=1, fetched_row=_row(version=2)
        )
        upsert(
            client,
            fiscal_year=2026, month=5, leader_team="L1",
            budget_amount=200000, expected_version=1,
            actor_email="admin@example.com",
        )
        first_call_sql = client.query.call_args_list[0].args[0]
        assert "UPDATE" in first_call_sql
        assert "version = version + 1" in first_call_sql
        assert "AND version = @expected_version" in first_call_sql


# --------- delete ---------


class TestDelete:
    def test_delete_success(self):
        """version 一致 → DELETE 成功 (1 row affected)"""
        client = MagicMock()
        dml_job = MagicMock()
        dml_job.num_dml_affected_rows = 1
        dml_job.result.return_value = None
        client.query.return_value = dml_job

        delete(
            client,
            fiscal_year=2026, month=5, leader_team="L1",
            expected_version=1, actor_email="admin@example.com",
        )
        # 例外を出さない

    def test_delete_conflict_version_mismatch(self):
        client = MagicMock()
        dml_job = MagicMock()
        dml_job.num_dml_affected_rows = 0
        dml_job.result.return_value = None
        client.query.return_value = dml_job

        with pytest.raises(UpsertConflict, match="DELETE conflict"):
            delete(
                client,
                fiscal_year=2026, month=5, leader_team="L1",
                expected_version=1, actor_email="admin@example.com",
            )

    def test_delete_sql_uses_version_check(self):
        client = MagicMock()
        dml_job = MagicMock()
        dml_job.num_dml_affected_rows = 1
        dml_job.result.return_value = None
        client.query.return_value = dml_job
        delete(
            client,
            fiscal_year=2026, month=5, leader_team="L1",
            expected_version=3, actor_email="admin@example.com",
        )
        sql = client.query.call_args.args[0]
        assert "DELETE FROM" in sql
        assert "AND version = @expected_version" in sql


# --------- preview_seed_from_quarterly (AC14) ---------


class TestPreviewSeedFromQuarterly:
    """Codex M3 反映: seed 実行前の preview"""

    def test_returns_aggregated_summary(self):
        """changed_count / current_total / seed_total / top_diffs"""
        # 3 行: 同値1件、差異2件
        preview_rows = [
            {"leader_team": "L1", "month": 11, "current_amount": 100, "seed_amount": 100},
            {"leader_team": "L1", "month": 12, "current_amount": 80, "seed_amount": 120},
            {"leader_team": "L2", "month": 11, "current_amount": 0, "seed_amount": 300},
        ]
        client = _make_client_with_rows(preview_rows)
        result = preview_seed_from_quarterly(client, 2026)
        assert result["changed_count"] == 2  # L1/12, L2/11 が差異あり
        assert result["current_total"] == 180  # 100+80+0
        assert result["seed_total"] == 520  # 100+120+300
        assert len(result["rows"]) == 3

    def test_top_diffs_sorted_by_abs(self):
        """差額絶対値降順で top_diffs"""
        preview_rows = [
            {"leader_team": "L1", "month": 11, "current_amount": 100, "seed_amount": 90},  # -10
            {"leader_team": "L2", "month": 11, "current_amount": 100, "seed_amount": 400},  # +300
            {"leader_team": "L3", "month": 11, "current_amount": 200, "seed_amount": 150},  # -50
        ]
        client = _make_client_with_rows(preview_rows)
        result = preview_seed_from_quarterly(client, 2026)
        # 上位 3 件は abs(diff) 降順: +300, -50, -10
        assert result["top_diffs"][0]["leader_team"] == "L2"
        assert result["top_diffs"][1]["leader_team"] == "L3"
        assert result["top_diffs"][2]["leader_team"] == "L1"

    def test_empty_rows_returns_zero_aggregates(self):
        """quarterly 未投入時は全 0"""
        client = _make_client_with_rows([])
        result = preview_seed_from_quarterly(client, 2026)
        assert result["changed_count"] == 0
        assert result["current_total"] == 0
        assert result["seed_total"] == 0
        assert result["rows"] == []
        assert result["top_diffs"] == []

    def test_sql_references_quarterly_and_current(self):
        client = _make_client_with_rows([])
        preview_seed_from_quarterly(client, 2026)
        sql = client.query.call_args.args[0]
        assert "team_budgets_quarterly" in sql
        assert "leader_team_monthly_budgets" in sql
        assert "ROW_NUMBER" in sql  # current_data の defensive


# --------- seed_from_quarterly (AC14) ---------


class TestSeedFromQuarterly:
    """seed 実行 (overwrite=False で新規、True で既存上書き)"""

    def test_overwrite_false_raises_when_existing(self):
        """既存 row あり + overwrite=False → ValueError"""
        # fetch_yearly が既存 row を返す + preview が成功
        client = MagicMock()
        preview_job = MagicMock()
        preview_job.result.return_value = [
            {"leader_team": "L1", "month": 11, "current_amount": 100, "seed_amount": 100},
        ]
        fetch_job = MagicMock()
        fetch_job.result.return_value = [_row()]  # 既存 row あり
        client.query.side_effect = [preview_job, fetch_job]

        with pytest.raises(ValueError, match="既に"):
            seed_from_quarterly(client, 2026, "admin@example.com", overwrite=False)

    def test_overwrite_false_inserts_when_empty(self):
        """既存 row なし + overwrite=False → 新規 INSERT"""
        client = MagicMock()
        preview_job = MagicMock()
        preview_job.result.return_value = [
            {"leader_team": "L1", "month": 11, "current_amount": 0, "seed_amount": 100},
        ]
        empty_fetch = MagicMock()
        empty_fetch.result.return_value = []
        insert_job = MagicMock()
        insert_job.num_dml_affected_rows = 1
        insert_job.result.return_value = None
        post_insert_fetch = MagicMock()
        post_insert_fetch.result.return_value = [_row(month=11, amount=100)]
        client.query.side_effect = [
            preview_job, empty_fetch, insert_job, post_insert_fetch,
        ]

        result = seed_from_quarterly(
            client, 2026, "admin@example.com", overwrite=False
        )
        assert isinstance(result, BulkUpsertResult)
        assert result.saved_count == 1
        assert result.conflicts == []
        assert result.errors == []
