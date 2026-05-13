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
def mock_auth_require_admin():
    """auth.require_admin() のモック"""
    with patch("lib.auth.require_admin", return_value=None) as mock_fn:
        yield mock_fn


@pytest.fixture
def module_under_test(mock_streamlit, mock_auth_require_admin):
    """report_input モジュールを動的にインポート"""
    if "pages.report_input" in sys.modules:
        del sys.modules["pages.report_input"]

    import importlib

    mock_streamlit.session_state = {"user_email": "test@tadakayo.jp", "user_role": "admin"}

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
    """_save_gyomu() のテスト（dry-run: BQ 書き込みなし、logger.info のみ）"""

    def test_save_gyomu_does_not_call_bq(self, module_under_test):
        """dry-run のため BQ クライアントは呼ばれない"""
        with patch("pages.report_input.get_bq_client") as mock_get_bq:
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
            mock_get_bq.assert_not_called()

    def test_save_gyomu_logs_dry_run(self, module_under_test, caplog):
        """dry-run ログに [DRY-RUN] プレフィックスとペイロード詳細が出る"""
        with caplog.at_level("INFO", logger="pages.report_input"):
            module_under_test._save_gyomu(
                user_email="test@tadakayo.jp",
                report_date=date(2026, 3, 28),
                team="チームA",
                activity_category="タダスク",
                work_category="講師",
                sponsor="",
                description="土曜講座",
                unit_price=1500.0,
                hours=2.0,
                amount=3000.0,
            )
        assert any("[DRY-RUN]" in r.message and "_save_gyomu" in r.message for r in caplog.records)
        # 曜日（2026-03-28 は土曜）と email が payload に含まれる
        joined = " ".join(r.message for r in caplog.records)
        assert "test@tadakayo.jp" in joined
        assert "'day_of_week': '土'" in joined


class TestSaveHojo:
    """_save_hojo() のテスト（dry-run）"""

    def test_save_hojo_does_not_call_bq(self, module_under_test):
        """dry-run のため BQ クライアントは呼ばれない"""
        with patch("pages.report_input.get_bq_client") as mock_get_bq:
            module_under_test._save_hojo(
                user_email="test@tadakayo.jp",
                year=2026, month=3,
                hours=10.0, compensation=50000.0,
                dx_subsidy=5000.0, reimbursement=1000.0,
                total_amount=56000.0,
                monthly_complete=True,
                dx_receipt="領収書A", expense_receipt="領収書B",
            )
            mock_get_bq.assert_not_called()

    def test_save_hojo_logs_payload(self, module_under_test, caplog):
        """dry-run ログにペイロードが含まれる"""
        with caplog.at_level("INFO", logger="pages.report_input"):
            module_under_test._save_hojo(
                user_email="test@tadakayo.jp",
                year=2026, month=3,
                hours=10.0, compensation=50000.0,
                dx_subsidy=0.0, reimbursement=0.0,
                total_amount=50000.0,
                monthly_complete=False,
                dx_receipt="", expense_receipt="",
            )
        joined = " ".join(r.message for r in caplog.records)
        assert "[DRY-RUN]" in joined
        assert "_save_hojo" in joined
        assert "'compensation': 50000.0" in joined
        assert "'monthly_complete': False" in joined


class TestDeleteGyomu:
    """_delete_gyomu() のテスト（dry-run）"""

    def test_delete_gyomu_does_not_call_bq(self, module_under_test):
        """dry-run のため BQ クライアントは呼ばれない"""
        with patch("pages.report_input.get_bq_client") as mock_get_bq:
            module_under_test._delete_gyomu(
                user_email="test@tadakayo.jp",
                report_date=date(2026, 3, 28),
                work_category="テスト",
                description="テスト内容",
            )
            mock_get_bq.assert_not_called()

    def test_delete_gyomu_logs_dry_run(self, module_under_test, caplog):
        """dry-run ログに [DRY-RUN] と DELETE 対象テーブルが出る"""
        with caplog.at_level("INFO", logger="pages.report_input"):
            module_under_test._delete_gyomu(
                user_email="test@tadakayo.jp",
                report_date=date(2026, 3, 28),
                work_category="テスト",
                description="テスト内容",
            )
        joined = " ".join(r.message for r in caplog.records)
        assert "[DRY-RUN]" in joined
        assert "_delete_gyomu" in joined
        assert "app_gyomu_reports" in joined


class TestModuleImport:
    """モジュールインポートのテスト"""

    def test_require_admin_called(self, mock_streamlit, mock_auth_require_admin):
        """require_admin()がモジュールロード時に呼ばれる（admin 限定ドラフトのため）"""
        if "pages.report_input" in sys.modules:
            del sys.modules["pages.report_input"]

        mock_streamlit.session_state = {"user_email": "test@tadakayo.jp", "user_role": "admin"}

        with patch("lib.bq_client.get_bq_client") as mock_get_bq:
            mock_client = MagicMock()
            mock_query_result = MagicMock()
            mock_query_result.to_dataframe.return_value = pd.DataFrame()
            mock_query_result.result.return_value = mock_query_result
            mock_client.query.return_value = mock_query_result
            mock_get_bq.return_value = mock_client

            import importlib
            importlib.import_module("pages.report_input")

        mock_auth_require_admin.assert_called_once()
