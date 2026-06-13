"""dashboard/pages.team_budget.py のページレベルテスト

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
    sys.modules.pop("pages.team_budget", None)

    # render_sidebar_year_month が selectbox 経由で 'viewer' を返す問題を回避し、
    # 確定的に (2026, 5) を返すよう patch
    with patch("lib.ui_helpers.render_sidebar_year_month", return_value=(2026, 5)):
        yield
    sys.modules.pop("pages.team_budget", None)
    sys.modules.pop("pages.team_budget", None)


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


class TestFiscalYearLoading:
    """Issue #248 AC13: 11/12 月境界の年度ズレ無し検証。

    fiscal_year 経由で load_team_budget_actuals が呼ばれることを検証する。
    selector で (year=2025, month=11) を選んだとき、内部で fiscal_year=2026 として
    扱われ、load_team_budget_actuals が fiscal_year=2026 で呼ばれる。
    """

    @pytest.fixture
    def reset_module_fy(self):
        sys.modules.pop("pages.team_budget", None)
        # selector を (2025, 11) で固定 → calendar_to_fiscal(2025,11) = (2026, 1)
        with patch("lib.ui_helpers.render_sidebar_year_month", return_value=(2025, 11)):
            yield
        sys.modules.pop("pages.team_budget", None)

    def test_load_team_budget_actuals_called_with_fiscal_year(self, reset_module_fy):
        """selector (2025, 11) → fiscal_year=2026 で load_team_budget_actuals 呼出"""
        import streamlit as st
        st.session_state["user_email"] = "u@example.com"
        st.session_state["user_role"] = "user"
        empty_df = pd.DataFrame({
            "year": [], "month": [], "team": [], "leader_team": [],
            "actual_amount": [], "actual_count": [], "reporter_count": [],
            "budget_amount": [], "achievement_rate": [], "diff_amount": [],
            "has_budget": [], "has_actual": [],
        })
        with patch("lib.bq_client.load_team_budget_actuals", return_value=empty_df) as mock_load, \
             patch("lib.bq_client.load_team_monthly_eval", return_value=pd.DataFrame()), \
             patch("lib.bq_client.load_active_teams", return_value=[]), \
             patch("lib.bq_client.load_active_leader_teams", return_value=[]), \
             patch("lib.bq_client.load_leader_team_monthly_budgets", return_value=pd.DataFrame()), \
             patch("lib.bq_client.load_leader_team_yearly_monthly_budgets", return_value={}), \
             patch("lib.bq_client.compute_current_hashes", return_value={}), \
             patch("lib.bq_client.get_bq_client"), \
             patch("lib.auth.require_user"):
            importlib.import_module("pages.team_budget")
        # selector (2025, 11) → fiscal_year=2026 (calendar_to_fiscal で算出)
        # load_team_budget_actuals が fiscal_year=2026 で呼ばれていること
        assert mock_load.called
        call_kwargs = mock_load.call_args.kwargs
        assert call_kwargs.get("fiscal_year") == 2026, (
            f"AC13: 2025/11 は FY2026 として扱われるべき。"
            f"actual fiscal_year={call_kwargs.get('fiscal_year')}"
        )

    def test_load_active_leader_teams_called_with_fiscal_year_in_matrix(
        self, reset_module_fy,
    ):
        """tab_matrix の load_active_leader_teams も fiscal_year= で呼ばれる"""
        import streamlit as st
        st.session_state["user_email"] = "u@example.com"
        st.session_state["user_role"] = "user"
        # actuals_year に 1 行入れて tab_matrix の if not empty 分岐に入る
        actuals_with_data = pd.DataFrame({
            "year": [2025], "month": [11], "team": ["A 隊"],
            "leader_team": ["L1 統括隊"],
            "actual_amount": [100.0], "actual_count": [1], "reporter_count": [1],
            "budget_amount": [200.0], "achievement_rate": [50.0],
            "diff_amount": [-100.0], "has_budget": [True], "has_actual": [True],
        })
        with patch("lib.bq_client.load_team_budget_actuals", return_value=actuals_with_data), \
             patch("lib.bq_client.load_team_monthly_eval", return_value=pd.DataFrame()), \
             patch("lib.bq_client.load_active_teams", return_value=["A 隊"]), \
             patch("lib.bq_client.load_active_leader_teams",
                   return_value=["L1 統括隊"]) as mock_aleader, \
             patch("lib.bq_client.load_leader_team_monthly_budgets",
                   return_value=pd.DataFrame()), \
             patch("lib.bq_client.load_leader_team_yearly_monthly_budgets", return_value={}), \
             patch("lib.bq_client.compute_current_hashes", return_value={"A 隊": ""}), \
             patch("lib.bq_client.get_bq_client"), \
             patch("lib.auth.require_user"):
            importlib.import_module("pages.team_budget")
        # tab_matrix の呼出 (fiscal_year=2026 kwarg) を検出
        fy_calls = [
            call for call in mock_aleader.call_args_list
            if call.kwargs.get("fiscal_year") == 2026
        ]
        assert len(fy_calls) >= 1, (
            f"AC13: tab_matrix で fiscal_year=2026 の呼出が必要。"
            f"calls={mock_aleader.call_args_list}"
        )

    def test_load_leader_team_yearly_uses_fiscal_year(self, reset_module_fy):
        """全体タブの月次推移グラフ予算ラインも fiscal_year で呼ばれる"""
        import streamlit as st
        st.session_state["user_email"] = "u@example.com"
        st.session_state["user_role"] = "user"
        actuals_with_data = pd.DataFrame({
            "year": [2025], "month": [11], "team": ["A 隊"],
            "leader_team": ["L1 統括隊"],
            "actual_amount": [100.0], "actual_count": [1], "reporter_count": [1],
            "budget_amount": [200.0], "achievement_rate": [50.0],
            "diff_amount": [-100.0], "has_budget": [True], "has_actual": [True],
        })
        with patch("lib.bq_client.load_team_budget_actuals", return_value=actuals_with_data), \
             patch("lib.bq_client.load_team_monthly_eval", return_value=pd.DataFrame()), \
             patch("lib.bq_client.load_active_teams", return_value=["A 隊"]), \
             patch("lib.bq_client.load_active_leader_teams", return_value=["L1 統括隊"]), \
             patch("lib.bq_client.load_leader_team_monthly_budgets",
                   return_value=pd.DataFrame()), \
             patch("lib.bq_client.load_leader_team_yearly_monthly_budgets",
                   return_value={i: 0 for i in range(1, 13)}) as mock_yearly, \
             patch("lib.bq_client.compute_current_hashes", return_value={"A 隊": ""}), \
             patch("lib.bq_client.get_bq_client"), \
             patch("lib.auth.require_user"):
            importlib.import_module("pages.team_budget")
        # selector (2025, 11) → fiscal_year=2026 で呼出
        mock_yearly.assert_called_with(2026)


class TestRenderTeamBudgetEditor:
    """code-review MEDIUM: admin role の月予算編集セクション統合テスト。

    page module 全体の実行は既存 test_imports_for_admin がカバー済。
    本クラスでは _render_team_budget_editor を直接呼んで挙動を検証する。
    """

    @pytest.fixture(autouse=True)
    def _patch_bq_and_load(self, monkeypatch):
        """page import 中の BQ アクセスを全 mock。各 test 内でも patch 維持"""
        import streamlit as st
        st.session_state["user_email"] = "admin@example.com"
        st.session_state["user_role"] = "admin"
        sys.modules.pop("pages.team_budget", None)
        sys.modules.pop("pages.team_budget", None)
        with patch("lib.ui_helpers.render_sidebar_year_month", return_value=(2026, 5)), \
             patch("lib.bq_client.load_team_budget_actuals", return_value=pd.DataFrame()), \
             patch("lib.bq_client.load_team_monthly_eval", return_value=pd.DataFrame()), \
             patch("lib.bq_client.load_active_teams", return_value=[]), \
             patch("lib.bq_client.load_active_leader_teams", return_value=[]), \
             patch("lib.bq_client.load_leader_team_monthly_budgets", return_value=pd.DataFrame()), \
             patch("lib.bq_client.compute_current_hashes", return_value={}), \
             patch("lib.bq_client.get_bq_client"), \
             patch("lib.auth.require_user"):
            mod = importlib.import_module("pages.team_budget")
            self._render = mod._render_team_budget_editor
            yield

    def _actuals_with_leader(self):
        return pd.DataFrame({
            "year": [2026], "month": [5], "team": ["A 隊"],
            "leader_team": ["L1 統括隊"],
        })

    @staticmethod
    def _setup_st_mock(st_mock):
        """st.columns(N) が N 個の mock を tuple で返すよう設定 + button defaults"""
        st_mock.session_state = {}
        st_mock.button.return_value = False
        st_mock.columns.side_effect = (
            lambda spec: tuple(
                MagicMock() for _ in range(
                    spec if isinstance(spec, int) else len(spec)
                )
            )
        )

    def test_warns_when_leader_team_unknown(self):
        empty_actuals = pd.DataFrame({"year": [], "month": [], "team": [],
                                       "leader_team": []})
        with patch("pages.team_budget.load_team_budget_cached") as load_b, \
             patch("pages.team_budget.load_other_team_budgets_cached") as load_o, \
             patch("pages.team_budget.st") as st_mock:
            self._render(
                year=2026, month=5, team="A 隊",
                actuals_month=empty_actuals,
                leader_team_monthly_budgets={},
                user_email="admin@example.com",
            )
        st_mock.info.assert_called_once()
        load_b.assert_not_called()
        load_o.assert_not_called()

    def test_warns_when_leader_monthly_budget_none(self):
        """code-review MEDIUM g: 統括隊予算未投入時は保存禁止 + 誘導 warning"""
        with patch("pages.team_budget.load_team_budget_cached", return_value=None), \
             patch("pages.team_budget.load_other_team_budgets_cached", return_value=0.0), \
             patch("pages.team_budget.st") as st_mock:
            self._setup_st_mock(st_mock)
            self._render(
                year=2026, month=5, team="A 隊",
                actuals_month=self._actuals_with_leader(),
                leader_team_monthly_budgets={},
                user_email="admin@example.com",
            )
        assert st_mock.warning.called

    def test_renders_widgets_when_budget_available(self):
        """通常: 統括隊予算あり → 入力 widget 表示"""
        with patch("pages.team_budget.load_team_budget_cached", return_value=None), \
             patch("pages.team_budget.load_other_team_budgets_cached", return_value=500000.0), \
             patch("pages.team_budget.st") as st_mock:
            self._setup_st_mock(st_mock)
            self._render(
                year=2026, month=5, team="A 隊",
                actuals_month=self._actuals_with_leader(),
                leader_team_monthly_budgets={"L1 統括隊": 1000000.0},
                user_email="admin@example.com",
            )
        # 入力 widget が呼ばれた (保存ボタンは col_save.button で st.button とは別 attribute)
        assert st_mock.number_input.called
        assert st_mock.text_input.called

    def test_user_role_does_not_call_editor(self):
        """Evaluator AC2: user role では _render_team_budget_editor が呼ばれない

        page module の `if is_admin:` ガードによって editor 関数が skip される
        ことを `assert_not_called` で直接検証する。
        """
        import streamlit as st
        st.session_state["user_email"] = "u@example.com"
        st.session_state["user_role"] = "user"
        sys.modules.pop("pages.team_budget", None)

        # active_teams を 1 件以上にして tab_drilldown の if is_admin: ガードまで到達
        sample_actuals = pd.DataFrame({
            "year": [2026], "month": [5], "team": ["A 隊"],
            "leader_team": ["L1 統括隊"],
            "actual_amount": [100.0], "actual_count": [1], "reporter_count": [1],
            "budget_amount": [200.0], "achievement_rate": [50.0],
            "diff_amount": [-100.0], "has_budget": [True], "has_actual": [True],
        })
        with patch("lib.ui_helpers.render_sidebar_year_month", return_value=(2026, 5)), \
             patch("lib.bq_client.load_team_budget_actuals", return_value=sample_actuals), \
             patch("lib.bq_client.load_team_monthly_eval", return_value=pd.DataFrame()), \
             patch("lib.bq_client.load_active_teams", return_value=["A 隊"]), \
             patch("lib.bq_client.load_active_leader_teams", return_value=["L1 統括隊"]), \
             patch("lib.bq_client.load_leader_team_monthly_budgets", return_value=pd.DataFrame()), \
             patch("lib.bq_client.compute_current_hashes", return_value={"A 隊": ""}), \
             patch("lib.bq_client.get_bq_client"), \
             patch("lib.auth.require_user"), \
             patch("_pages.team_budget._render_team_budget_editor") as render_mock:
            importlib.import_module("pages.team_budget")
            # user role なので editor は呼ばれない
            render_mock.assert_not_called()

    def test_upsert_conflict_renders_error_with_reload_hint(self):
        """Evaluator AC7: UpsertConflict 時に「画面を更新」を含む st.error が呼ばれる"""
        from lib.team_budget_repo import TeamBudgetRow, UpsertConflict
        from datetime import datetime, timezone
        existing = TeamBudgetRow(
            year=2026, month=5, team="A 隊", budget_amount=1000.0,
            memo=None, version=1,
            updated_at=datetime(2026, 6, 13, tzinfo=timezone.utc),
            updated_by="admin@example.com",
        )
        # 保存ボタン押下を模す: 1 番目の columns 呼出 (parent cols) で
        # ref1/ref2/ref3、2 番目の呼出 (save/delete cols) で col_save.button=True
        col_save = MagicMock()
        col_save.button.return_value = True  # 「保存」押下
        col_del = MagicMock()
        col_del.button.return_value = False
        ref_cols = (MagicMock(), MagicMock(), MagicMock())
        with patch("pages.team_budget.load_team_budget_cached", return_value=existing), \
             patch("pages.team_budget.load_other_team_budgets_cached", return_value=0.0), \
             patch("pages.team_budget.load_other_team_budgets_in_leader", return_value=0.0), \
             patch("pages.team_budget.upsert_team_budget",
                   side_effect=UpsertConflict("version mismatch (expected=1, affected=0)")), \
             patch("pages.team_budget.st") as st_mock:
            self._setup_st_mock(st_mock)
            # 1 回目: ref1/ref2/ref3, 2 回目: col_save/col_del
            st_mock.columns.side_effect = [ref_cols, (col_save, col_del)]
            st_mock.number_input.return_value = 1500.0
            st_mock.text_input.return_value = "memo"
            self._render(
                year=2026, month=5, team="A 隊",
                actuals_month=self._actuals_with_leader(),
                leader_team_monthly_budgets={"L1 統括隊": 2000.0},
                user_email="admin@example.com",
            )
        # error が呼ばれ、メッセージに「更新」を含む
        assert st_mock.error.called
        error_msg = str(st_mock.error.call_args)
        assert "更新" in error_msg

    def test_delete_confirm_yes_calls_delete_team_budget(self):
        """Evaluator AC9 + AC17: 削除確認「削除する」→ delete_team_budget 呼出 + 再生成 info"""
        from lib.team_budget_repo import TeamBudgetRow
        from datetime import datetime, timezone
        existing = TeamBudgetRow(
            year=2026, month=5, team="A 隊", budget_amount=1000.0,
            memo=None, version=2,
            updated_at=datetime(2026, 6, 13, tzinfo=timezone.utc),
            updated_by="admin@example.com",
        )
        # delete_state.pending=True で confirm dialog 経路に入り「削除する」押下
        dy = MagicMock()
        dy.button.return_value = True  # 「削除する」押下
        dn = MagicMock()
        dn.button.return_value = False
        ref_cols = (MagicMock(), MagicMock(), MagicMock())
        with patch("pages.team_budget.load_team_budget_cached", return_value=existing), \
             patch("pages.team_budget.load_other_team_budgets_cached", return_value=0.0), \
             patch("pages.team_budget.delete_team_budget") as del_mock, \
             patch("pages.team_budget.st") as st_mock:
            self._setup_st_mock(st_mock)
            st_mock.columns.side_effect = [ref_cols, (dy, dn)]
            st_mock.number_input.return_value = 1000.0
            st_mock.text_input.return_value = ""
            # 削除待機状態を session_state にセット
            from lib.team_budget_edit_logic import DeleteConfirmState
            st_mock.session_state = {
                f"tb_edit_2026_5_A 隊_delete": DeleteConfirmState(pending=True),
            }
            self._render(
                year=2026, month=5, team="A 隊",
                actuals_month=self._actuals_with_leader(),
                leader_team_monthly_budgets={"L1 統括隊": 2000.0},
                user_email="admin@example.com",
            )
        # delete_team_budget が呼ばれた (actor は "delete:" プレフィックス付き)
        del_mock.assert_called_once()
        call_kwargs = del_mock.call_args.kwargs
        assert call_kwargs["expected_version"] == 2
        assert call_kwargs["actor"].startswith("delete:")
        # 「再生成を推奨」info も呼ばれた
        assert st_mock.info.called
        info_msg = str(st_mock.info.call_args)
        assert "再生成" in info_msg

    def test_initial_amount_preserves_decimal_precision(self):
        """code-review MEDIUM: 既存 row の Decimal 値 (1500.50) を切り捨てない"""
        from lib.team_budget_repo import TeamBudgetRow
        from datetime import datetime, timezone
        existing = TeamBudgetRow(
            year=2026, month=5, team="A 隊",
            budget_amount=1500.50,
            memo=None, version=1,
            updated_at=datetime(2026, 6, 13, tzinfo=timezone.utc),
            updated_by="admin@example.com",
        )
        with patch("pages.team_budget.load_team_budget_cached", return_value=existing), \
             patch("pages.team_budget.load_other_team_budgets_cached", return_value=0.0), \
             patch("pages.team_budget.st") as st_mock:
            self._setup_st_mock(st_mock)
            self._render(
                year=2026, month=5, team="A 隊",
                actuals_month=self._actuals_with_leader(),
                leader_team_monthly_budgets={"L1 統括隊": 1000000.0},
                user_email="admin@example.com",
            )
        call_kwargs = st_mock.number_input.call_args.kwargs
        assert call_kwargs["value"] == 1500.50
        assert isinstance(call_kwargs["step"], float)
