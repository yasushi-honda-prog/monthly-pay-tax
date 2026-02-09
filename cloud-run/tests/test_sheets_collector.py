"""sheets_collector のユニットテスト

_execute_with_throttle のスロットリング・リトライ・エラーハンドリングを検証。
"""

import httplib2
import pytest
from unittest.mock import MagicMock, patch

from googleapiclient.errors import HttpError

import config
from sheets_collector import (
    _execute_with_throttle,
    get_sheet_data,
)


class TestExecuteWithThrottle:
    """_execute_with_throttle のテスト"""

    @patch("sheets_collector.time.sleep")
    def test_normal_execution_calls_num_retries(self, mock_sleep):
        """正常時に execute(num_retries=5) が呼ばれること"""
        mock_request = MagicMock()
        mock_request.execute.return_value = {"values": [["a", "b"]]}

        result = _execute_with_throttle(mock_request, context="test")

        mock_request.execute.assert_called_once_with(
            num_retries=config.SHEETS_API_NUM_RETRIES
        )
        assert result == {"values": [["a", "b"]]}

    @patch("sheets_collector.time.sleep")
    def test_sleep_called_before_execute(self, mock_sleep):
        """time.sleep が execute 前に呼ばれること"""
        mock_request = MagicMock()
        mock_request.execute.return_value = {}

        _execute_with_throttle(mock_request)

        mock_sleep.assert_called_once_with(config.SHEETS_API_SLEEP_BETWEEN_REQUESTS)

    @patch("sheets_collector.time.sleep")
    def test_permanent_error_reraises(self, mock_sleep):
        """permanent error (400) が再raiseされること"""
        resp = httplib2.Response({"status": 400})
        error = HttpError(resp, b"Bad Request")

        mock_request = MagicMock()
        mock_request.execute.side_effect = error

        with pytest.raises(HttpError) as exc_info:
            _execute_with_throttle(mock_request, context="test_perm")

        assert exc_info.value.resp.status == 400

    @patch("sheets_collector.time.sleep")
    def test_transient_error_reraises_with_error_log(self, mock_sleep):
        """transient error (429) が再raiseされ、ログレベルがerrorであること"""
        resp = httplib2.Response({"status": 429})
        error = HttpError(resp, b"Rate Limit Exceeded")

        mock_request = MagicMock()
        mock_request.execute.side_effect = error

        with pytest.raises(HttpError), \
             patch("sheets_collector.logger") as mock_logger:
            _execute_with_throttle(mock_request, context="test_transient")

        mock_logger.error.assert_called_once()
        assert "transient" in mock_logger.error.call_args[0][0]


class TestGetSheetData:
    """get_sheet_data のエラーハンドリングテスト"""

    @patch("sheets_collector._execute_with_throttle")
    def test_returns_empty_list_on_error(self, mock_throttle):
        """エラー時に空リスト返却（既存動作維持）"""
        mock_throttle.side_effect = HttpError(
            httplib2.Response({"status": 403}), b"Forbidden"
        )

        mock_service = MagicMock()
        result = get_sheet_data(mock_service, "id123", "Sheet1", 1, "K")

        assert result == []
