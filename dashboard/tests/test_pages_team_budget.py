"""dashboard/_pages/team_budget.py のページレベルテスト

Streamlit と BQ クライアントは conftest.py で全モック化。本テストでは:
- ページモジュールが import 時にエラーを起こさないこと
- 認証ガード (require_user) が呼ばれること
- session_state["user_role"] による admin 表示分岐
を検証する。

ページの細かい UI レンダリングは team_budget_view の純関数テストでカバー済み。
"""

from __future__ import annotations

import importlib
import sys
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest


@pytest.fixture
def reset_module():
    """前回 import のキャッシュを除去 + selectbox を年月リテラルを返すよう patch"""
    sys.modules.pop("pages.team_budget", None)
    sys.modules.pop("_pages.team_budget", None)

    # render_sidebar_year_month が selectbox 経由で 'viewer' を返す問題を回避し、
    # 確定的に (2026, 5) を返すよう patch
    with patch("lib.ui_helpers.render_sidebar_year_month", return_value=(2026, 5)):
        yield
    sys.modules.pop("pages.team_budget", None)
    sys.modules.pop("_pages.team_budget", None)


@pytest.fixture
def mock_bq_data():
    """予実関連 BQ 関数を全てモック (PR-B: leader_team 列追加 + load_active_leader_teams)"""
    sample_actuals = pd.DataFrame({
        "year": [2026, 2026],
        "month": [5, 5],
        "team": ["A 隊", "B 隊"],
        "leader_team": ["L1 統括隊", "L1 統括隊"],
        "actual_amount": [480000.0, 350000.0],
        "actual_count": [12, 8],
        "reporter_count": [3, 2],
        "budget_amount": [500000.0, 300000.0],
        "achievement_rate": [96.0, 116.7],
        "diff_amount": [-20000.0, 50000.0],
        "has_budget": [True, True],
        "has_actual": [True, True],
    })
    eval_df = pd.DataFrame({
        "year": [2026], "month": [5], "team": ["A 隊"],
        "actual_amount": [480000.0], "budget_amount": [500000.0],
        "achievement_rate": [96.0], "diff_amount": [-20000.0],
        "actual_data_hash": ["hash-a"],
        "ai_comment": ["達成率は適正範囲内です。"],
        "ai_model": ["gemini-2.5-flash"],
        "prompt_version": ["v1"],
        "generated_at": [None],
        "generated_by": ["scheduler"],
    })

    with patch("lib.bq_client.load_team_budget_actuals", return_value=sample_actuals), \
         patch("lib.bq_client.load_team_monthly_eval", return_value=eval_df), \
         patch("lib.bq_client.load_active_teams", return_value=["A 隊", "B 隊"]), \
         patch("lib.bq_client.load_active_leader_teams", return_value=["L1 統括隊"]), \
         patch("lib.bq_client.load_leader_team_monthly_budgets", return_value=pd.DataFrame()), \
         patch("lib.bq_client.compute_current_hashes", return_value={"A 隊": "hash-a"}), \
         patch("lib.bq_client.get_bq_client"):
        yield


class TestTeamBudgetPage:
    def test_imports_without_error_for_user(self, reset_module, mock_bq_data):
        """user ロールでもページ全体が import + 実行可能"""
        import streamlit as st
        st.session_state["user_email"] = "u@example.com"
        st.session_state["user_role"] = "user"
        with patch("lib.auth.require_user"):
            importlib.import_module("pages.team_budget")

    def test_imports_for_admin(self, reset_module, mock_bq_data):
        """admin ロールでもエラーなくロード可能"""
        import streamlit as st
        st.session_state["user_email"] = "a@example.com"
        st.session_state["user_role"] = "admin"
        with patch("lib.auth.require_user"):
            importlib.import_module("pages.team_budget")

    def test_calls_require_user_gate(self, reset_module, mock_bq_data):
        """全ロール許容の認証ガードが呼ばれる"""
        import streamlit as st
        st.session_state["user_email"] = "x@example.com"
        st.session_state["user_role"] = "user"
        with patch("lib.auth.require_user") as mock_gate:
            importlib.import_module("pages.team_budget")
            assert mock_gate.called

    def test_no_active_teams_path(self, reset_module):
        """active teams が空でも例外を出さない (ドリルダウンで warning 表示のみ)"""
        import streamlit as st
        st.session_state["user_email"] = "u@example.com"
        st.session_state["user_role"] = "user"
        with patch("lib.bq_client.load_team_budget_actuals", return_value=pd.DataFrame()), \
             patch("lib.bq_client.load_team_monthly_eval", return_value=pd.DataFrame()), \
             patch("lib.bq_client.load_active_teams", return_value=[]), \
             patch("lib.bq_client.load_active_leader_teams", return_value=[]), \
             patch("lib.bq_client.load_leader_team_monthly_budgets", return_value=pd.DataFrame()), \
             patch("lib.bq_client.compute_current_hashes", return_value={}), \
             patch("lib.bq_client.get_bq_client"), \
             patch("lib.auth.require_user"):
            importlib.import_module("pages.team_budget")

    def test_empty_hierarchy_no_leader_teams(self, reset_module):
        """PR-B Evaluator 指摘: team_hierarchy 空時に統括隊フィルタ selectbox が
        「全て」のみで起動し例外を出さない"""
        import streamlit as st
        st.session_state["user_email"] = "u@example.com"
        st.session_state["user_role"] = "user"
        sample_actuals = pd.DataFrame({
            "year": [2026], "month": [5], "team": ["A 隊"],
            "leader_team": [None],  # hierarchy 不在 (本来 VIEW で除外される、防御的テスト)
            "actual_amount": [100.0], "actual_count": [1], "reporter_count": [1],
            "budget_amount": [200.0], "achievement_rate": [50.0],
            "diff_amount": [-100.0], "has_budget": [True], "has_actual": [True],
        })
        with patch("lib.bq_client.load_team_budget_actuals", return_value=sample_actuals), \
             patch("lib.bq_client.load_team_monthly_eval", return_value=pd.DataFrame()), \
             patch("lib.bq_client.load_active_teams", return_value=["A 隊"]), \
             patch("lib.bq_client.load_active_leader_teams", return_value=[]), \
             patch("lib.bq_client.load_leader_team_monthly_budgets", return_value=pd.DataFrame()), \
             patch("lib.bq_client.compute_current_hashes", return_value={"A 隊": ""}), \
             patch("lib.bq_client.get_bq_client"), \
             patch("lib.auth.require_user"):
            importlib.import_module("pages.team_budget")

    def test_leader_team_filter_drops_unmatched(self, reset_module):
        """PR-B: 統括隊フィルタで配下隊がないケースで info 表示し例外を出さない"""
        import streamlit as st
        st.session_state["user_email"] = "u@example.com"
        st.session_state["user_role"] = "user"
        # 配下隊が一つも matched しない構造
        sample_actuals = pd.DataFrame({
            "year": [2026], "month": [5], "team": ["A 隊"],
            "leader_team": ["L1 統括隊"],
            "actual_amount": [100.0], "actual_count": [1], "reporter_count": [1],
            "budget_amount": [200.0], "achievement_rate": [50.0],
            "diff_amount": [-100.0], "has_budget": [True], "has_actual": [True],
        })
        with patch("lib.bq_client.load_team_budget_actuals", return_value=sample_actuals), \
             patch("lib.bq_client.load_team_monthly_eval", return_value=pd.DataFrame()), \
             patch("lib.bq_client.load_active_teams", return_value=["A 隊"]), \
             patch("lib.bq_client.load_active_leader_teams", return_value=["L1 統括隊"]), \
             patch("lib.bq_client.load_leader_team_monthly_budgets", return_value=pd.DataFrame()), \
             patch("lib.bq_client.compute_current_hashes", return_value={"A 隊": ""}), \
             patch("lib.bq_client.get_bq_client"), \
             patch("lib.auth.require_user"):
            importlib.import_module("pages.team_budget")
