"""報告入力ページのユニットテスト"""

import sys
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

dashboard_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(dashboard_dir))


@pytest.fixture
def mock_auth_require_user():
    """auth.require_user() のモック"""
    with patch("lib.auth.require_user", return_value=None) as mock_fn:
        yield mock_fn


@pytest.fixture
def module_under_test(mock_streamlit, mock_auth_require_user):
    """report_input モジュールを動的にインポート"""
    if "pages.report_input" in sys.modules:
        del sys.modules["pages.report_input"]

    import importlib

    mock_streamlit.session_state = {"user_email": "test@tadakayo.jp", "user_role": "user"}

    with patch("lib.bq_client.get_bq_client") as mock_get_bq:
        mock_client = MagicMock()
        mock_query_result = MagicMock()
        mock_query_result.to_dataframe.return_value = pd.DataFrame()
        mock_query_result.result.return_value = mock_query_result
        mock_client.query.return_value = mock_query_result
        mock_get_bq.return_value = mock_client

        module = importlib.import_module("pages.report_input")

    yield module


class TestWeekdayJp:
    """曜日定数のテスト"""

    def test_weekday_jp_length(self, module_under_test):
        assert len(module_under_test.WEEKDAY_JP) == 7

    def test_weekday_jp_monday(self, module_under_test):
        assert module_under_test.WEEKDAY_JP[0] == "月"

    def test_weekday_jp_sunday(self, module_under_test):
        assert module_under_test.WEEKDAY_JP[6] == "日"


class TestSaveGyomu:
    """_save_gyomu() のテスト"""

    def test_save_gyomu_calls_bq(self, module_under_test):
        """BQクエリが正しく呼ばれる"""
        with patch("pages.report_input.get_bq_client") as mock_get_bq:
            mock_client = MagicMock()
            mock_result = MagicMock()
            mock_client.query.return_value = mock_result
            mock_get_bq.return_value = mock_client

            module_under_test._save_gyomu(
                user_email="test@tadakayo.jp",
                report_date=date(2026, 3, 28),
                team="みんなでスキルアップ隊",
                activity_category="タダスク",
                work_category="タダスク研修講師",
                sponsor="スポンサーA",
                description="テスト業務",
                unit_price=1500.0,
                hours=2.0,
                amount=3000.0,
            )

            mock_client.query.assert_called_once()
            call_args = mock_client.query.call_args
            query_str = call_args[0][0]
            assert "MERGE" in query_str
            assert "app_gyomu_reports" in query_str

    def test_save_gyomu_day_of_week(self, module_under_test):
        """曜日がdateから正しく導出される"""
        with patch("pages.report_input.get_bq_client") as mock_get_bq:
            mock_client = MagicMock()
            mock_result = MagicMock()
            mock_client.query.return_value = mock_result
            mock_get_bq.return_value = mock_client

            # 2026-03-28 は土曜日
            module_under_test._save_gyomu(
                user_email="test@tadakayo.jp",
                report_date=date(2026, 3, 28),
                team="",
                activity_category="テスト",
                work_category="テスト",
                sponsor="",
                description="テスト",
                unit_price=0,
                hours=1.0,
                amount=0,
            )

            call_args = mock_client.query.call_args
            job_config = call_args[1]["job_config"]
            params = {p.name: p.value for p in job_config.query_parameters}
            assert params["dow"] == "土"


class TestSaveHojo:
    """_save_hojo() のテスト"""

    def test_save_hojo_calls_bq(self, module_under_test):
        """BQクエリが正しく呼ばれる"""
        with patch("pages.report_input.get_bq_client") as mock_get_bq:
            mock_client = MagicMock()
            mock_result = MagicMock()
            mock_client.query.return_value = mock_result
            mock_get_bq.return_value = mock_client

            module_under_test._save_hojo(
                user_email="test@tadakayo.jp",
                year=2026, month=3,
                hours=10.0, compensation=50000.0,
                dx_subsidy=5000.0, reimbursement=1000.0,
                total_amount=56000.0,
                monthly_complete=True,
                dx_receipt="領収書A", expense_receipt="領収書B",
            )

            mock_client.query.assert_called_once()
            call_args = mock_client.query.call_args
            query_str = call_args[0][0]
            assert "MERGE" in query_str
            assert "app_hojo_reports" in query_str

    def test_save_hojo_parameters(self, module_under_test):
        """パラメータが正しく渡される"""
        with patch("pages.report_input.get_bq_client") as mock_get_bq:
            mock_client = MagicMock()
            mock_result = MagicMock()
            mock_client.query.return_value = mock_result
            mock_get_bq.return_value = mock_client

            module_under_test._save_hojo(
                user_email="test@tadakayo.jp",
                year=2026, month=3,
                hours=10.0, compensation=50000.0,
                dx_subsidy=0.0, reimbursement=0.0,
                total_amount=50000.0,
                monthly_complete=False,
                dx_receipt="", expense_receipt="",
            )

            call_args = mock_client.query.call_args
            job_config = call_args[1]["job_config"]
            params = {p.name: p.value for p in job_config.query_parameters}
            assert params["email"] == "test@tadakayo.jp"
            assert params["year"] == 2026
            assert params["month"] == 3
            assert params["compensation"] == 50000.0
            assert params["monthly_complete"] is False


class TestDeleteGyomu:
    """_delete_gyomu() のテスト"""

    def test_delete_gyomu_calls_bq(self, module_under_test):
        """DELETE文が正しく呼ばれる"""
        with patch("pages.report_input.get_bq_client") as mock_get_bq:
            mock_client = MagicMock()
            mock_result = MagicMock()
            mock_client.query.return_value = mock_result
            mock_get_bq.return_value = mock_client

            module_under_test._delete_gyomu(
                user_email="test@tadakayo.jp",
                report_date=date(2026, 3, 28),
                work_category="テスト",
                description="テスト内容",
            )

            mock_client.query.assert_called_once()
            call_args = mock_client.query.call_args
            query_str = call_args[0][0]
            assert "DELETE" in query_str


class TestModuleImport:
    """モジュールインポートのテスト"""

    def test_require_user_called(self, mock_streamlit, mock_auth_require_user):
        """require_user()がモジュールロード時に呼ばれる"""
        if "pages.report_input" in sys.modules:
            del sys.modules["pages.report_input"]

        mock_streamlit.session_state = {"user_email": "test@tadakayo.jp", "user_role": "user"}

        with patch("lib.bq_client.get_bq_client") as mock_get_bq:
            mock_client = MagicMock()
            mock_query_result = MagicMock()
            mock_query_result.to_dataframe.return_value = pd.DataFrame()
            mock_query_result.result.return_value = mock_query_result
            mock_client.query.return_value = mock_query_result
            mock_get_bq.return_value = mock_client

            import importlib
            importlib.import_module("pages.report_input")

        mock_auth_require_user.assert_called_once()
