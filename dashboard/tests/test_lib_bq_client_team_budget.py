"""dashboard/lib/bq_client.py の予実管理関数 (PR-D) のユニットテスト

spec: docs/specs/2026-06-10-team-budget-eval-design.md §6.6

BQ クライアントは conftest.py の MagicMock で差し替え済み (streamlit と同じく)。
本テストでは get_bq_client() を直接 patch する。
"""

from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from lib import bq_client


@pytest.fixture
def mock_client():
    """get_bq_client を mock 化 + DataFrame/Row を返す"""
    client = MagicMock()
    with patch("lib.bq_client.get_bq_client", return_value=client):
        yield client


def _to_dataframe_mock(client, df: pd.DataFrame):
    """client.query(...).to_dataframe() が df を返す"""
    job = MagicMock()
    job.to_dataframe.return_value = df
    client.query.return_value = job


def _result_mock(client, rows):
    """client.query(...).result() が rows を返す"""
    job = MagicMock()
    job.result.return_value = rows
    client.query.return_value = job


class TestLoadTeamBudgetActuals:
    def test_returns_dataframe(self, mock_client):
        df = pd.DataFrame({
            "year": [2026], "month": [5], "team": ["X"],
            "actual_amount": [480000.0], "actual_count": [12], "reporter_count": [3],
            "budget_amount": [500000.0], "achievement_rate": [96.0],
            "diff_amount": [-20000.0], "has_budget": [True], "has_actual": [True],
        })
        _to_dataframe_mock(mock_client, df)
        result = bq_client.load_team_budget_actuals(2026, 2026, 5, 5)
        assert len(result) == 1
        assert result.iloc[0]["team"] == "X"

    def test_sql_uses_view_name(self, mock_client):
        _to_dataframe_mock(mock_client, pd.DataFrame())
        bq_client.load_team_budget_actuals(2026, 2026, 5, 5)
        sql = mock_client.query.call_args.args[0]
        assert "v_team_budget_actuals" in sql
        assert "@y_start" in sql and "@m_end" in sql

    def test_params_bound(self, mock_client):
        _to_dataframe_mock(mock_client, pd.DataFrame())
        bq_client.load_team_budget_actuals(2026, 2026, 4, 6)
        job_config = mock_client.query.call_args.kwargs["job_config"]
        params = {p.name: p.value for p in job_config.query_parameters}
        assert params["y_start"] == 2026
        assert params["m_start"] == 4
        assert params["m_end"] == 6


class TestLoadTeamMonthlyEval:
    def test_all_teams_when_team_none(self, mock_client):
        _to_dataframe_mock(mock_client, pd.DataFrame())
        bq_client.load_team_monthly_eval(2026, 5, team=None)
        sql = mock_client.query.call_args.args[0]
        assert "team_monthly_eval" in sql
        # WHERE 句に team = は含まれない
        assert "team = @team" not in sql

    def test_single_team_when_specified(self, mock_client):
        _to_dataframe_mock(mock_client, pd.DataFrame())
        bq_client.load_team_monthly_eval(2026, 5, team="X")
        sql = mock_client.query.call_args.args[0]
        assert "team = @team" in sql
        assert "LIMIT 1" in sql

    def test_team_param_bound(self, mock_client):
        _to_dataframe_mock(mock_client, pd.DataFrame())
        bq_client.load_team_monthly_eval(2026, 5, team="Z 隊")
        job_config = mock_client.query.call_args.kwargs["job_config"]
        params = {p.name: p.value for p in job_config.query_parameters}
        assert params["team"] == "Z 隊"


class TestLoadActiveTeams:
    def test_returns_team_list(self, mock_client):
        rows = [{"team": "A"}, {"team": "B"}, {"team": "C"}]
        _result_mock(mock_client, rows)
        teams = bq_client.load_active_teams(2026, 2026, 5, 5)
        assert teams == ["A", "B", "C"]

    def test_uses_distinct(self, mock_client):
        _result_mock(mock_client, [])
        bq_client.load_active_teams(2026, 2026, 5, 5)
        sql = mock_client.query.call_args.args[0]
        assert "DISTINCT" in sql
        assert "team IS NOT NULL" in sql


class TestComputeCurrentHashes:
    def test_empty_teams_returns_empty_dict(self, mock_client):
        result = bq_client.compute_current_hashes(2026, 5, ())
        assert result == {}
        # クエリも発行しない
        assert mock_client.query.call_count == 0

    def test_returns_team_hash_dict(self, mock_client):
        rows = [
            {"team": "A", "data_hash": "h-a"},
            {"team": "B", "data_hash": "h-b"},
        ]
        _result_mock(mock_client, rows)
        result = bq_client.compute_current_hashes(2026, 5, ("A", "B"))
        assert result == {"A": "h-a", "B": "h-b"}

    def test_missing_team_falls_back_to_empty_string(self, mock_client):
        """指定 team が結果に含まれない (= 該当データなし) は '' で埋める
        (cloud-run 側の IFNULL(..., '') と整合)"""
        rows = [{"team": "A", "data_hash": "h-a"}]  # B は返らない
        _result_mock(mock_client, rows)
        result = bq_client.compute_current_hashes(2026, 5, ("A", "B"))
        assert result == {"A": "h-a", "B": ""}

    def test_sql_uses_unnest(self, mock_client):
        _result_mock(mock_client, [])
        bq_client.compute_current_hashes(2026, 5, ("A", "B"))
        sql = mock_client.query.call_args.args[0]
        assert "UNNEST(@teams)" in sql
        # PR-C と同じ tie-breaker
        assert "ORDER BY row_hash, row_json" in sql

    def test_sql_avoids_reserved_keyword_rows(self, mock_client):
        """CTE 名に `rows` を使うと BigQuery 予約語 ROWS と衝突する。回帰防止。"""
        _result_mock(mock_client, [])
        bq_client.compute_current_hashes(2026, 5, ("A",))
        sql = mock_client.query.call_args.args[0]
        assert "WITH rows AS" not in sql
        assert "FROM rows" not in sql

    def test_teams_array_param(self, mock_client):
        _result_mock(mock_client, [])
        bq_client.compute_current_hashes(2026, 5, ("X", "Y"))
        job_config = mock_client.query.call_args.kwargs["job_config"]
        teams_param = [p for p in job_config.query_parameters if p.name == "teams"][0]
        assert teams_param.values == ["X", "Y"]
