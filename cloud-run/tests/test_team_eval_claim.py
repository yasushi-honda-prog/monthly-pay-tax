"""team_monthly_eval テーブルへの claim / upsert / release ユニットテスト

spec: docs/specs/2026-06-10-team-budget-eval-design.md §4.3.1 / §5.2

BQ クライアントは MagicMock で差し替え。
"""

from unittest.mock import MagicMock, patch

import pytest

import bq_loader
import config


def _make_mock_client(num_dml_affected_rows: int = 1):
    """num_dml_affected_rows を持つ mock query job を返す client"""
    client = MagicMock()
    job = MagicMock()
    job.num_dml_affected_rows = num_dml_affected_rows
    job.result.return_value = None
    client.query.return_value = job
    return client


def _sql_called(client) -> str:
    return client.query.call_args.args[0]


def _params_called(client) -> dict:
    job_config = client.query.call_args.kwargs["job_config"]
    return {p.name: p.value for p in job_config.query_parameters}


class TestClaimTeamEvalRow:
    def test_success_when_affected_rows_ge_one(self):
        client = _make_mock_client(1)
        ok = bq_loader.claim_team_eval_row(
            client, year=2026, month=5, team="X",
            job_id="job-abc", actor="user@x",
        )
        assert ok is True

    def test_failure_when_no_rows_affected(self):
        """他者が claim 中 → MERGE WHEN MATCHED 不発で affected_rows=0"""
        client = _make_mock_client(0)
        ok = bq_loader.claim_team_eval_row(
            client, year=2026, month=5, team="X",
            job_id="job-abc", actor="user@x",
        )
        assert ok is False

    def test_sql_includes_merge_keywords(self):
        client = _make_mock_client(1)
        bq_loader.claim_team_eval_row(
            client, year=2026, month=5, team="X",
            job_id="job-abc", actor="user@x",
        )
        sql = _sql_called(client)
        assert "MERGE" in sql
        assert "team_monthly_eval" in sql
        assert "lock_token" in sql
        assert "WHEN MATCHED AND" in sql
        assert "WHEN NOT MATCHED" in sql

    def test_sql_uses_configured_lock_duration(self):
        client = _make_mock_client(1)
        bq_loader.claim_team_eval_row(
            client, year=2026, month=5, team="X",
            job_id="job", actor="u",
        )
        sql = _sql_called(client)
        assert f"INTERVAL {config.EVAL_LOCK_DURATION_MIN} MINUTE" in sql

    def test_custom_lock_duration_overrides(self):
        client = _make_mock_client(1)
        bq_loader.claim_team_eval_row(
            client, year=2026, month=5, team="X",
            job_id="job", actor="u", lock_duration_min=15,
        )
        assert "INTERVAL 15 MINUTE" in _sql_called(client)

    def test_parameters_bound(self):
        client = _make_mock_client(1)
        bq_loader.claim_team_eval_row(
            client, year=2026, month=5, team="X 隊",
            job_id="job-xyz", actor="alice@example.com",
        )
        params = _params_called(client)
        assert params["year"] == 2026
        assert params["month"] == 5
        assert params["team"] == "X 隊"
        assert params["job_id"] == "job-xyz"
        assert params["actor"] == "alice@example.com"


class TestLoadExistingEval:
    def test_returns_none_when_no_rows(self):
        client = MagicMock()
        client.query.return_value.result.return_value = []
        result = bq_loader.load_existing_eval(client, year=2026, month=5, team="X")
        assert result is None

    def test_returns_dict(self):
        row = {
            "actual_data_hash": "abc",
            "ai_comment": "ok",
            "ai_model": "gemini-2.5-flash",
            "prompt_version": "v1",
            "generated_at": None,
            "generated_by": "scheduler",
        }
        client = MagicMock()
        client.query.return_value.result.return_value = [row]
        result = bq_loader.load_existing_eval(client, year=2026, month=5, team="X")
        assert result["actual_data_hash"] == "abc"
        assert result["ai_comment"] == "ok"
        assert result["prompt_version"] == "v1"


class TestUpsertTeamMonthlyEval:
    def _record(self, **overrides):
        base = {
            "year": 2026,
            "month": 5,
            "team": "X 隊",
            "actual_amount": 480000,
            "budget_amount": 500000,
            "achievement_rate": 96.0,
            "diff_amount": -20000,
            "actual_data_hash": "h1",
            "ai_comment": "ok",
            "ai_model": "gemini-2.5-flash",
            "ai_prompt_tokens": 200,
            "ai_output_tokens": 80,
            "prompt_version": "v1",
            "sample_query_version": "v1",
            "location": "asia-northeast1",
            "generation_config_json": '{"temperature": 0.3}',
            "generated_by": "scheduler",
        }
        base.update(overrides)
        return base

    def test_success_when_lock_matches(self):
        client = _make_mock_client(1)
        ok = bq_loader.upsert_team_monthly_eval(
            client, record=self._record(), expected_lock_token="job-abc",
        )
        assert ok is True

    def test_no_op_when_lock_mismatch(self):
        """expected_lock_token と一致しない → WHEN MATCHED 不発 → 0 affected"""
        client = _make_mock_client(0)
        ok = bq_loader.upsert_team_monthly_eval(
            client, record=self._record(), expected_lock_token="job-other",
        )
        assert ok is False

    def test_sql_clears_lock_columns(self):
        client = _make_mock_client(1)
        bq_loader.upsert_team_monthly_eval(
            client, record=self._record(), expected_lock_token="job-abc",
        )
        sql = _sql_called(client)
        assert "lock_token = NULL" in sql
        assert "lock_until = NULL" in sql
        assert "lock_actor = NULL" in sql

    def test_sql_sets_generated_at_now(self):
        client = _make_mock_client(1)
        bq_loader.upsert_team_monthly_eval(
            client, record=self._record(), expected_lock_token="job-abc",
        )
        sql = _sql_called(client)
        assert "generated_at = CURRENT_TIMESTAMP()" in sql

    def test_sql_guards_against_stale_lock(self):
        """5 分以上の処理で lock_until が過去になっていた場合、自分の token
        と一致していても書き込み禁止 (Codex review Medium)"""
        client = _make_mock_client(1)
        bq_loader.upsert_team_monthly_eval(
            client, record=self._record(), expected_lock_token="job-abc",
        )
        sql = _sql_called(client)
        assert "lock_until > CURRENT_TIMESTAMP()" in sql

    def test_parameters_include_record_fields(self):
        client = _make_mock_client(1)
        bq_loader.upsert_team_monthly_eval(
            client, record=self._record(), expected_lock_token="job-abc",
        )
        params = _params_called(client)
        assert params["expected_lock_token"] == "job-abc"
        assert params["actual_amount"] == 480000
        assert params["achievement_rate"] == 96.0
        assert params["ai_comment"] == "ok"
        assert params["prompt_version"] == "v1"

    def test_default_token_counts_to_zero(self):
        """ai_prompt_tokens / ai_output_tokens が None なら 0 にフォールバック"""
        client = _make_mock_client(1)
        bq_loader.upsert_team_monthly_eval(
            client,
            record=self._record(ai_prompt_tokens=None, ai_output_tokens=None),
            expected_lock_token="job",
        )
        params = _params_called(client)
        assert params["ai_prompt_tokens"] == 0
        assert params["ai_output_tokens"] == 0


class TestReleaseTeamEvalClaim:
    def test_success(self):
        client = _make_mock_client(1)
        ok = bq_loader.release_team_eval_claim(
            client, year=2026, month=5, team="X",
            expected_lock_token="job-abc",
        )
        assert ok is True
        sql = _sql_called(client)
        assert "UPDATE" in sql
        assert "lock_token = NULL" in sql

    def test_failure_when_lock_taken_by_other(self):
        client = _make_mock_client(0)
        ok = bq_loader.release_team_eval_claim(
            client, year=2026, month=5, team="X",
            expected_lock_token="job-other",
        )
        assert ok is False
