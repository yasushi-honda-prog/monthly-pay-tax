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
            "year": [2026], "month": [5], "team": ["X"], "leader_team": ["L"],
            "actual_amount": [480000.0], "actual_count": [12], "reporter_count": [3],
            "budget_amount": [500000.0], "achievement_rate": [96.0],
            "diff_amount": [-20000.0], "has_budget": [True], "has_actual": [True],
        })
        _to_dataframe_mock(mock_client, df)
        result = bq_client.load_team_budget_actuals(2026, 2026, 5, 5)
        assert len(result) == 1
        assert result.iloc[0]["team"] == "X"
        # PR-A: leader_team 列を返す
        assert result.iloc[0]["leader_team"] == "L"

    def test_sql_uses_view_name(self, mock_client):
        _to_dataframe_mock(mock_client, pd.DataFrame())
        bq_client.load_team_budget_actuals(2026, 2026, 5, 5)
        sql = mock_client.query.call_args.args[0]
        assert "v_team_budget_actuals" in sql
        assert "@y_start" in sql and "@m_end" in sql

    def test_sql_selects_leader_team_column(self, mock_client):
        """PR-A: load_team_budget_actuals は leader_team 列を SELECT する"""
        _to_dataframe_mock(mock_client, pd.DataFrame())
        bq_client.load_team_budget_actuals(2026, 2026, 5, 5)
        sql = mock_client.query.call_args.args[0]
        assert "leader_team" in sql

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


class TestLoadLeaderTeamMonthlyBudgets:
    """Issue #248: leader_team_monthly_budgets 新テーブル参照に切替"""

    def test_returns_dataframe_with_leader_team_and_monthly_budget(self, mock_client):
        df = pd.DataFrame({
            "leader_team": ["L1", "L2"],
            "monthly_budget": [1000.0, 2000.0],
        })
        _to_dataframe_mock(mock_client, df)
        result = bq_client.load_leader_team_monthly_budgets(2026, 5)
        assert len(result) == 2
        assert "leader_team" in result.columns
        assert "monthly_budget" in result.columns

    def test_returns_empty_when_table_empty(self, mock_client):
        """leader_team_monthly_budgets が空なら empty DataFrame"""
        _to_dataframe_mock(mock_client, pd.DataFrame())
        result = bq_client.load_leader_team_monthly_budgets(2026, 5)
        assert result.empty

    def test_sql_uses_new_table_with_row_number(self, mock_client):
        """新テーブル参照 + ROW_NUMBER で defensive (Codex H2)"""
        _to_dataframe_mock(mock_client, pd.DataFrame())
        bq_client.load_leader_team_monthly_budgets(2026, 5)
        sql = mock_client.query.call_args.args[0]
        assert "leader_team_monthly_budgets" in sql
        # 旧 quarterly 参照は無いこと
        assert "team_budgets_quarterly" not in sql
        # defensive ROW_NUMBER
        assert "ROW_NUMBER" in sql
        assert "PARTITION BY fiscal_year, month, leader_team" in sql

    def test_params_bound_as_fiscal_year(self, mock_client):
        _to_dataframe_mock(mock_client, pd.DataFrame())
        bq_client.load_leader_team_monthly_budgets(2026, 5)
        job_config = mock_client.query.call_args.kwargs["job_config"]
        params = {p.name: p.value for p in job_config.query_parameters}
        # Issue #248 で意味変更: year 引数は fiscal_year として扱う
        assert params["fiscal_year"] == 2026
        assert params["month"] == 5


class TestLoadLeaderTeamYearlyMonthlyBudgets:
    """Issue #248: leader_team_monthly_budgets 新テーブル参照、12 ヶ月分集計"""

    def test_returns_month_budget_dict(self, mock_client):
        from decimal import Decimal
        bq_client.load_leader_team_yearly_monthly_budgets.clear()
        rows = [
            {"month": i, "monthly_budget": Decimal("1000000") if 5 <= i <= 7
             else Decimal("0")}
            for i in range(1, 13)
        ]
        _result_mock(mock_client, rows)
        result = bq_client.load_leader_team_yearly_monthly_budgets(2026)
        assert len(result) == 12
        # int 型 (Codex L1: 円整数運用)
        assert result[5] == 1000000
        assert result[1] == 0
        assert isinstance(result[5], int)

    def test_sql_uses_new_table_with_generate_array(self, mock_client):
        bq_client.load_leader_team_yearly_monthly_budgets.clear()
        _result_mock(mock_client, [])
        bq_client.load_leader_team_yearly_monthly_budgets(2026)
        sql = mock_client.query.call_args.args[0]
        assert "GENERATE_ARRAY(1, 12)" in sql
        assert "leader_team_monthly_budgets" in sql
        # 旧 quarterly 参照は無いこと
        assert "team_budgets_quarterly" not in sql
        # defensive ROW_NUMBER (Codex H2)
        assert "ROW_NUMBER" in sql

    def test_returns_12_months_when_table_empty(self, mock_client):
        """leader_team_monthly_budgets 未投入時は LEFT JOIN + IFNULL で 12 ヶ月 0"""
        bq_client.load_leader_team_yearly_monthly_budgets.clear()
        rows = [{"month": i, "monthly_budget": 0} for i in range(1, 13)]
        _result_mock(mock_client, rows)
        result = bq_client.load_leader_team_yearly_monthly_budgets(2026)
        assert all(v == 0 for v in result.values())
        assert len(result) == 12


class TestLoadLeaderTeamQuarterlyBudgetsForSeed:
    """Issue #248 新規: seed/差分表示用 quarterly÷3 month 展開"""

    def test_returns_dataframe(self, mock_client):
        from decimal import Decimal
        df = pd.DataFrame({
            "leader_team": ["L1", "L1", "L2"],
            "month": [11, 12, 11],
            "quarterly_div3": [Decimal("100000"), Decimal("100000"), Decimal("200000")],
        })
        _to_dataframe_mock(mock_client, df)
        result = bq_client.load_leader_team_quarterly_budgets_for_seed(2026)
        assert len(result) == 3
        assert "leader_team" in result.columns
        assert "month" in result.columns
        assert "quarterly_div3" in result.columns

    def test_sql_references_quarterly_with_month_expansion(self, mock_client):
        _to_dataframe_mock(mock_client, pd.DataFrame())
        bq_client.load_leader_team_quarterly_budgets_for_seed(2026)
        sql = mock_client.query.call_args.args[0]
        assert "team_budgets_quarterly" in sql
        # Q1=[11,12,1] 展開
        assert "WHEN 1 THEN [11, 12, 1]" in sql
        assert "WHEN 4 THEN [8, 9, 10]" in sql
        assert "SAFE_DIVIDE" in sql

    def test_filter_fiscal_year(self, mock_client):
        _to_dataframe_mock(mock_client, pd.DataFrame())
        bq_client.load_leader_team_quarterly_budgets_for_seed(2027)
        job_config = mock_client.query.call_args.kwargs["job_config"]
        params = {p.name: p.value for p in job_config.query_parameters}
        assert params["fiscal_year"] == 2027


class TestLoadTeamBudgetActualsFiscalYear:
    """Issue #248: fiscal_year keyword arg で年跨ぎ範囲取得 (Codex H1、AC13)"""

    def test_fiscal_year_2026_uses_year_crossing_range(self, mock_client):
        """FY2026 (2025/11-2026/10) を fiscal_year=2026 で渡したとき、年跨ぎ SQL を使う"""
        df = pd.DataFrame({
            "year": [2025], "month": [11], "team": ["A"], "leader_team": ["L"],
            "actual_amount": [100.0], "actual_count": [1], "reporter_count": [1],
            "budget_amount": [200.0], "achievement_rate": [50.0],
            "diff_amount": [-100.0], "has_budget": [True], "has_actual": [True],
        })
        _to_dataframe_mock(mock_client, df)
        # fiscal_year を指定 → 位置引数は無視
        bq_client.load_team_budget_actuals.clear()
        result = bq_client.load_team_budget_actuals(0, 0, 0, 0, fiscal_year=2026)
        assert len(result) == 1
        # job_config 検証
        job_config = mock_client.query.call_args.kwargs["job_config"]
        params = {p.name: p.value for p in job_config.query_parameters}
        # fiscal_calendar.fiscal_year_month_range(2026) → (2025, 2026, 11, 10)
        assert params["y_start"] == 2025
        assert params["y_end"] == 2026
        assert params["m_start"] == 11
        assert params["m_end"] == 10

    def test_sql_handles_month_start_greater_than_month_end(self, mock_client):
        """m_start > m_end 用の年跨ぎ OR SQL が含まれる"""
        _to_dataframe_mock(mock_client, pd.DataFrame())
        bq_client.load_team_budget_actuals.clear()
        bq_client.load_team_budget_actuals(0, 0, 0, 0, fiscal_year=2026)
        sql = mock_client.query.call_args.args[0]
        # m_start <= m_end / m_start > m_end の OR 分岐
        assert "@m_start <= @m_end" in sql
        assert "@m_start > @m_end" in sql

    def test_backward_compat_without_fiscal_year(self, mock_client):
        """fiscal_year 未指定なら位置引数をそのまま使う (後方互換)"""
        _to_dataframe_mock(mock_client, pd.DataFrame())
        bq_client.load_team_budget_actuals.clear()
        bq_client.load_team_budget_actuals(2026, 2026, 5, 5)
        job_config = mock_client.query.call_args.kwargs["job_config"]
        params = {p.name: p.value for p in job_config.query_parameters}
        assert params["y_start"] == 2026
        assert params["y_end"] == 2026
        assert params["m_start"] == 5
        assert params["m_end"] == 5


class TestLoadActiveLeaderTeams:
    """PR-A: 統括隊 distinct リスト取得関数のテスト"""

    def test_returns_leader_team_list(self, mock_client):
        rows = [
            {"leader_team": "ゆずるん統括隊"},
            {"leader_team": "ヤスス＋ヒデデン統括隊"},
        ]
        _result_mock(mock_client, rows)
        leaders = bq_client.load_active_leader_teams(2026, 2026, 5, 5)
        assert leaders == ["ゆずるん統括隊", "ヤスス＋ヒデデン統括隊"]

    def test_returns_empty_when_no_rows(self, mock_client):
        _result_mock(mock_client, [])
        leaders = bq_client.load_active_leader_teams(2026, 2026, 5, 5)
        assert leaders == []

    def test_sql_uses_distinct_leader_team(self, mock_client):
        _result_mock(mock_client, [])
        bq_client.load_active_leader_teams(2026, 2026, 5, 5)
        sql = mock_client.query.call_args.args[0]
        assert "DISTINCT leader_team" in sql
        assert "leader_team IS NOT NULL" in sql
        assert "v_team_budget_actuals" in sql

    def test_params_bound(self, mock_client):
        _result_mock(mock_client, [])
        bq_client.load_active_leader_teams(2026, 2026, 4, 6)
        job_config = mock_client.query.call_args.kwargs["job_config"]
        params = {p.name: p.value for p in job_config.query_parameters}
        assert params["y_start"] == 2026
        assert params["m_start"] == 4
        assert params["m_end"] == 6


def _hash_and_budget_mock(client, hash_rows, budget_rows):
    """compute_current_hashes は 2 query (hash SQL → budget SELECT) を順次発行。
    side_effect で順序対応する mock を作る。
    """
    hash_job = MagicMock()
    hash_job.result.return_value = hash_rows
    budget_job = MagicMock()
    budget_job.result.return_value = budget_rows
    client.query.side_effect = [hash_job, budget_job]


def _expected_composite(bq_hash, budget):
    """compose_actual_data_hash の期待値計算 helper"""
    from lib.constants import PROMPT_VERSION
    from lib.team_budget_hash import compose_actual_data_hash
    return compose_actual_data_hash(bq_hash, budget, PROMPT_VERSION)


class TestComputeCurrentHashes:
    def test_empty_teams_returns_empty_dict(self, mock_client):
        # cache 残留対策
        bq_client.compute_current_hashes.clear()
        result = bq_client.compute_current_hashes(2026, 5, (), "v1")
        assert result == {}
        # クエリも発行しない
        assert mock_client.query.call_count == 0

    def test_returns_composite_hash_dict(self, mock_client):
        from decimal import Decimal
        bq_client.compute_current_hashes.clear()
        hash_rows = [
            {"team": "A", "data_hash": "h-a"},
            {"team": "B", "data_hash": "h-b"},
        ]
        budget_rows = [
            {"team": "A", "budget_amount": Decimal("1000")},
            # B は budget 未設定
        ]
        _hash_and_budget_mock(mock_client, hash_rows, budget_rows)
        result = bq_client.compute_current_hashes(2026, 5, ("A", "B"), "v1")
        assert result == {
            "A": _expected_composite("h-a", Decimal("1000")),
            "B": _expected_composite("h-b", None),
        }

    def test_missing_team_falls_back_to_empty_bq_hash(self, mock_client):
        """指定 team が hash SQL 結果に含まれない (= データなし) は bq_hash='' で
        compose に渡す (cloud-run 側の IFNULL(..., '') と整合)"""
        bq_client.compute_current_hashes.clear()
        hash_rows = [{"team": "A", "data_hash": "h-a"}]  # B は返らない
        budget_rows = []
        _hash_and_budget_mock(mock_client, hash_rows, budget_rows)
        result = bq_client.compute_current_hashes(2026, 5, ("A", "B"), "v1")
        assert result == {
            "A": _expected_composite("h-a", None),
            "B": _expected_composite("", None),
        }

    def test_budget_changes_hash(self, mock_client):
        """同 bq_hash でも budget 違いで composite hash が変わる
        (予算編集 → outdated 判定の根拠)"""
        from decimal import Decimal
        bq_client.compute_current_hashes.clear()
        hash_rows = [{"team": "A", "data_hash": "samebq"}]
        budget_rows_1 = [{"team": "A", "budget_amount": Decimal("1000")}]
        _hash_and_budget_mock(mock_client, hash_rows, budget_rows_1)
        h1 = bq_client.compute_current_hashes(2026, 5, ("A",), "v1")["A"]

        bq_client.compute_current_hashes.clear()
        hash_rows_2 = [{"team": "A", "data_hash": "samebq"}]
        budget_rows_2 = [{"team": "A", "budget_amount": Decimal("2000")}]
        _hash_and_budget_mock(mock_client, hash_rows_2, budget_rows_2)
        h2 = bq_client.compute_current_hashes(2026, 5, ("A",), "v1")["A"]

        assert h1 != h2

    def test_hash_sql_uses_unnest(self, mock_client):
        """1 回目 query (hash SQL) が UNNEST + ORDER BY tie-breaker を使う"""
        bq_client.compute_current_hashes.clear()
        _hash_and_budget_mock(mock_client, [], [])
        bq_client.compute_current_hashes(2026, 5, ("A", "B"), "v1")
        sql = mock_client.query.call_args_list[0].args[0]
        assert "UNNEST(@teams)" in sql
        assert "ORDER BY row_hash, row_json" in sql

    def test_budget_sql_selects_team_budgets(self, mock_client):
        """2 回目 query (budget SELECT) が team_budgets を参照"""
        bq_client.compute_current_hashes.clear()
        _hash_and_budget_mock(mock_client, [], [])
        bq_client.compute_current_hashes(2026, 5, ("A",), "v1")
        sql = mock_client.query.call_args_list[1].args[0]
        assert "team_budgets" in sql
        assert "UNNEST(@teams)" in sql

    def test_sql_avoids_reserved_keyword_rows(self, mock_client):
        """CTE 名に `rows` を使うと BigQuery 予約語 ROWS と衝突する。回帰防止。"""
        bq_client.compute_current_hashes.clear()
        _hash_and_budget_mock(mock_client, [], [])
        bq_client.compute_current_hashes(2026, 5, ("A",), "v1")
        sql = mock_client.query.call_args_list[0].args[0]
        assert "WITH rows AS" not in sql
        assert "FROM rows" not in sql

    def test_teams_array_param(self, mock_client):
        bq_client.compute_current_hashes.clear()
        _hash_and_budget_mock(mock_client, [], [])
        bq_client.compute_current_hashes(2026, 5, ("X", "Y"), "v1")
        # hash SQL (1 回目) の teams param
        job_config = mock_client.query.call_args_list[0].kwargs["job_config"]
        teams_param = [p for p in job_config.query_parameters if p.name == "teams"][0]
        assert teams_param.values == ["X", "Y"]

    def test_prompt_version_in_cache_key(self, mock_client):
        """Evaluator 見落 #3: prompt_version 引数が cache key に含まれ、
        異なる prompt_version で別 cache (異なる query 実行) になることを確認"""
        from decimal import Decimal
        bq_client.compute_current_hashes.clear()

        # v1 で 1 回目
        _hash_and_budget_mock(
            mock_client,
            [{"team": "A", "data_hash": "h-a"}],
            [{"team": "A", "budget_amount": Decimal("1000")}],
        )
        h1 = bq_client.compute_current_hashes(2026, 5, ("A",), "v1")
        call_count_after_v1 = mock_client.query.call_count

        # v2 で 2 回目: cache miss なら新 query (call_count 増加) + 異なる hash
        _hash_and_budget_mock(
            mock_client,
            [{"team": "A", "data_hash": "h-a"}],
            [{"team": "A", "budget_amount": Decimal("1000")}],
        )
        h2 = bq_client.compute_current_hashes(2026, 5, ("A",), "v2")
        # v1 と v2 で異なる cache key → 新規 query が走った
        assert mock_client.query.call_count > call_count_after_v1
        # composite hash も別 (prompt_version 反映)
        assert h1["A"] != h2["A"]
