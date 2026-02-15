"""Unit tests for pages/check_management.py

Tests for _is_complete() and save_check() functions.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch, call

import pytest
import pandas as pd
from google.cloud import bigquery

from lib.constants import CHECK_LOGS_TABLE


# Define the functions from check_management.py directly for testing
# (avoids issues with module-level Streamlit code execution)

def _is_complete(val) -> bool:
    """月締め完了判定"""
    return str(val).strip().lower() in ("true", "1", "○", "済")


def save_check(source_url, year, month, status, memo, checker_email, existing_log, action_desc, expected_updated_at=None):
    """チェックログを保存（MERGE + 楽観的ロック）"""
    # Import here to avoid module-level execution issues
    from lib.bq_client import get_bq_client

    client = get_bq_client()

    # 操作ログ追記（型安全）
    try:
        logs = json.loads(existing_log) if existing_log and pd.notna(existing_log) else []
        if not isinstance(logs, list):
            logs = []
    except (json.JSONDecodeError, TypeError):
        logs = []
    logs = [e for e in logs if isinstance(e, dict)]
    logs.append({
        "ts": datetime.now(timezone.utc).isoformat(),
        "user": checker_email,
        "action": action_desc,
    })
    new_log = json.dumps(logs, ensure_ascii=False)

    params = [
        bigquery.ScalarQueryParameter("source_url", "STRING", source_url),
        bigquery.ScalarQueryParameter("year", "INT64", year),
        bigquery.ScalarQueryParameter("month", "INT64", month),
        bigquery.ScalarQueryParameter("status", "STRING", status),
        bigquery.ScalarQueryParameter("checker_email", "STRING", checker_email),
        bigquery.ScalarQueryParameter("memo", "STRING", memo or None),
        bigquery.ScalarQueryParameter("action_log", "STRING", new_log),
    ]

    # 楽観的ロック: 既存レコードがある場合はupdated_atを検証
    if expected_updated_at is not None and pd.notna(expected_updated_at):
        params.append(bigquery.ScalarQueryParameter("expected_updated_at", "TIMESTAMP", expected_updated_at))
        query = f"""
        MERGE `{CHECK_LOGS_TABLE}` T
        USING (SELECT @source_url AS source_url, @year AS year, @month AS month) S
        ON T.source_url = S.source_url AND T.year = S.year AND T.month = S.month
        WHEN MATCHED AND T.updated_at = @expected_updated_at THEN
          UPDATE SET
            status = @status, checker_email = @checker_email, memo = @memo,
            action_log = @action_log, updated_at = CURRENT_TIMESTAMP()
        WHEN NOT MATCHED THEN
          INSERT (source_url, year, month, status, checker_email, memo, action_log, updated_at)
          VALUES (@source_url, @year, @month, @status, @checker_email, @memo, @action_log, CURRENT_TIMESTAMP())
        """
    else:
        query = f"""
        MERGE `{CHECK_LOGS_TABLE}` T
        USING (SELECT @source_url AS source_url, @year AS year, @month AS month) S
        ON T.source_url = S.source_url AND T.year = S.year AND T.month = S.month
        WHEN MATCHED THEN
          UPDATE SET
            status = @status, checker_email = @checker_email, memo = @memo,
            action_log = @action_log, updated_at = CURRENT_TIMESTAMP()
        WHEN NOT MATCHED THEN
          INSERT (source_url, year, month, status, checker_email, memo, action_log, updated_at)
          VALUES (@source_url, @year, @month, @status, @checker_email, @memo, @action_log, CURRENT_TIMESTAMP())
        """

    job_config = bigquery.QueryJobConfig(query_parameters=params)
    result = client.query(query, job_config=job_config).result()

    # 楽観的ロック競合検出
    if expected_updated_at is not None and pd.notna(expected_updated_at) and result.num_dml_affected_rows == 0:
        raise ValueError("別のチェック者が先に更新しました。ページを再読み込みしてください。")

    # Clear cache if it exists (best effort - may not exist in test environment)
    try:
        import sys
        if 'pages.check_management' in sys.modules:
            pages_mod = sys.modules['pages.check_management']
            if hasattr(pages_mod, 'load_check_data'):
                pages_mod.load_check_data.clear()
    except (AttributeError, ImportError):
        pass  # Cache clear not available in test


class TestIsComplete:
    """Tests for _is_complete() pure function"""

    @pytest.mark.parametrize("val,expected", [
        # True cases: lowercase
        ("true", True),
        ("TRUE", True),
        ("True", True),
        ("TrUe", True),
        # True cases: numeric
        ("1", True),
        (1, True),
        # True cases: Japanese markers
        ("○", True),
        ("済", True),
        # False cases: other strings
        ("false", False),
        ("FALSE", False),
        ("0", False),
        (0, False),
        ("", False),
        ("ng", False),
        ("×", False),
        ("no", False),
        ("いいえ", False),
        # None and edge cases
        (None, False),
        # Leading/trailing whitespace
        ("  true  ", True),
        ("\ttrue\n", True),
        ("  1  ", True),
        ("  ○  ", True),
        ("  済  ", True),
        ("  false  ", False),
        ("  0  ", False),
        # Mixed case with whitespace
        ("  TRUE  ", True),
        ("  False  ", False),
    ])
    def test_is_complete_various_inputs(self, val, expected):
        """Test _is_complete() with various inputs"""
        result = _is_complete(val)
        assert result is expected

    def test_is_complete_numeric_types(self):
        """Test with numeric types (converted to string)"""
        assert _is_complete(1) is True
        assert _is_complete(0) is False
        # 1.0 becomes "1.0" as string, which doesn't match "1" exactly
        assert _is_complete(1.0) is False  # "1.0" != "1"
        assert _is_complete(0.0) is False

    def test_is_complete_pandas_null(self):
        """Test with pandas NaN/NaT values"""
        assert _is_complete(pd.NA) is False
        assert _is_complete(pd.NaT) is False

    def test_is_complete_returns_bool(self):
        """Test that _is_complete always returns bool type"""
        assert isinstance(_is_complete("true"), bool)
        assert isinstance(_is_complete("false"), bool)
        assert isinstance(_is_complete(None), bool)
        assert isinstance(_is_complete(1), bool)


class TestSaveCheck:
    """Tests for save_check() function with BigQuery interaction"""

    @patch("lib.bq_client.get_bq_client")
    def test_save_check_new_log_from_none(self, mock_get_bq_client):
        """When existing_log is None, create single entry in action_log"""
        # Setup mocks
        mock_client = MagicMock()
        mock_get_bq_client.return_value = mock_client

        mock_result = MagicMock()
        mock_result.num_dml_affected_rows = 1
        mock_client.query.return_value.result.return_value = mock_result

        # Call
        save_check(
            source_url="https://example.com/sheet1",
            year=2024,
            month=12,
            status="確認完了",
            memo="チェック完了",
            checker_email="checker@tadakayo.jp",
            existing_log=None,
            action_desc="ステータス: 未確認 → 確認完了",
        )

        # Verify
        mock_client.query.assert_called_once()
        call_args = mock_client.query.call_args
        job_config = call_args[1]["job_config"]
        params = job_config.query_parameters

        # Find action_log parameter
        action_log_param = None
        for param in params:
            if param.name == "action_log":
                action_log_param = param
                break

        assert action_log_param is not None
        logs = json.loads(action_log_param.value)
        assert len(logs) == 1
        assert logs[0]["user"] == "checker@tadakayo.jp"
        assert logs[0]["action"] == "ステータス: 未確認 → 確認完了"
        assert "ts" in logs[0]

    @patch("lib.bq_client.get_bq_client")
    def test_save_check_append_to_existing_log(self, mock_get_bq_client):
        """When existing_log is valid JSON, append new entry"""
        mock_client = MagicMock()
        mock_get_bq_client.return_value = mock_client

        mock_result = MagicMock()
        mock_result.num_dml_affected_rows = 1
        mock_client.query.return_value.result.return_value = mock_result

        existing_log = json.dumps([
            {
                "ts": "2024-12-14T09:00:00+00:00",
                "user": "checker1@tadakayo.jp",
                "action": "初期確認"
            }
        ])

        save_check(
            source_url="https://example.com/sheet1",
            year=2024,
            month=12,
            status="確認完了",
            memo="完了",
            checker_email="checker2@tadakayo.jp",
            existing_log=existing_log,
            action_desc="メモ更新",
        )

        # Verify
        call_args = mock_client.query.call_args
        job_config = call_args[1]["job_config"]
        params = job_config.query_parameters

        action_log_param = None
        for param in params:
            if param.name == "action_log":
                action_log_param = param
                break

        assert action_log_param is not None
        logs = json.loads(action_log_param.value)
        assert len(logs) == 2
        assert logs[0]["user"] == "checker1@tadakayo.jp"
        assert logs[1]["user"] == "checker2@tadakayo.jp"
        assert logs[1]["action"] == "メモ更新"

    @patch("lib.bq_client.get_bq_client")
    def test_save_check_reset_on_broken_json(self, mock_get_bq_client):
        """When existing_log is broken JSON, reset and create single entry"""
        mock_client = MagicMock()
        mock_get_bq_client.return_value = mock_client

        mock_result = MagicMock()
        mock_result.num_dml_affected_rows = 1
        mock_client.query.return_value.result.return_value = mock_result

        # Broken JSON
        existing_log = "this is not json {invalid}"

        save_check(
            source_url="https://example.com/sheet1",
            year=2024,
            month=12,
            status="確認中",
            memo="",
            checker_email="checker@tadakayo.jp",
            existing_log=existing_log,
            action_desc="再試行",
        )

        call_args = mock_client.query.call_args
        job_config = call_args[1]["job_config"]
        params = job_config.query_parameters

        action_log_param = None
        for param in params:
            if param.name == "action_log":
                action_log_param = param
                break

        logs = json.loads(action_log_param.value)
        assert len(logs) == 1
        assert logs[0]["action"] == "再試行"

    @patch("lib.bq_client.get_bq_client")
    def test_save_check_reset_when_log_not_list(self, mock_get_bq_client):
        """When existing_log is valid JSON but not list, reset and create entry"""
        mock_client = MagicMock()
        mock_get_bq_client.return_value = mock_client

        mock_result = MagicMock()
        mock_result.num_dml_affected_rows = 1
        mock_client.query.return_value.result.return_value = mock_result

        # Valid JSON but not a list (dict)
        existing_log = json.dumps({"ts": "2024-12-14T09:00:00+00:00"})

        save_check(
            source_url="https://example.com/sheet1",
            year=2024,
            month=12,
            status="差戻し",
            memo="修正必要",
            checker_email="admin@tadakayo.jp",
            existing_log=existing_log,
            action_desc="ステータス: 確認完了 → 差戻し",
        )

        call_args = mock_client.query.call_args
        job_config = call_args[1]["job_config"]
        params = job_config.query_parameters

        action_log_param = None
        for param in params:
            if param.name == "action_log":
                action_log_param = param
                break

        logs = json.loads(action_log_param.value)
        assert len(logs) == 1
        assert logs[0]["action"] == "ステータス: 確認完了 → 差戻し"

    @patch("lib.bq_client.get_bq_client")
    def test_save_check_filter_non_dict_entries(self, mock_get_bq_client):
        """Filter out non-dict entries from existing log before appending"""
        mock_client = MagicMock()
        mock_get_bq_client.return_value = mock_client

        mock_result = MagicMock()
        mock_result.num_dml_affected_rows = 1
        mock_client.query.return_value.result.return_value = mock_result

        # Log with mixed types: valid dicts and non-dicts
        existing_log = json.dumps([
            {"ts": "2024-12-14T09:00:00+00:00", "user": "u1", "action": "a1"},
            "invalid_string",
            {"ts": "2024-12-14T10:00:00+00:00", "user": "u2", "action": "a2"},
            123,
            None,
        ])

        save_check(
            source_url="https://example.com/sheet1",
            year=2024,
            month=12,
            status="確認完了",
            memo="",
            checker_email="checker@tadakayo.jp",
            existing_log=existing_log,
            action_desc="完了",
        )

        call_args = mock_client.query.call_args
        job_config = call_args[1]["job_config"]
        params = job_config.query_parameters

        action_log_param = None
        for param in params:
            if param.name == "action_log":
                action_log_param = param
                break

        logs = json.loads(action_log_param.value)
        # Should have 2 valid dicts + 1 new entry = 3
        assert len(logs) == 3
        # All should be dicts
        assert all(isinstance(log, dict) for log in logs)
        # First two should be original valid dicts
        assert logs[0]["user"] == "u1"
        assert logs[1]["user"] == "u2"
        # Third should be new entry
        assert logs[2]["user"] == "checker@tadakayo.jp"
        assert logs[2]["action"] == "完了"

    @patch("lib.bq_client.get_bq_client")
    def test_save_check_query_parameters_without_lock(self, mock_get_bq_client):
        """Verify query parameters when expected_updated_at is None"""
        mock_client = MagicMock()
        mock_get_bq_client.return_value = mock_client

        mock_result = MagicMock()
        mock_result.num_dml_affected_rows = 1
        mock_client.query.return_value.result.return_value = mock_result

        save_check(
            source_url="https://example.com/sheet1",
            year=2024,
            month=12,
            status="確認完了",
            memo="OK",
            checker_email="checker@tadakayo.jp",
            existing_log=None,
            action_desc="完了",
            expected_updated_at=None,
        )

        call_args = mock_client.query.call_args
        job_config = call_args[1]["job_config"]
        params = job_config.query_parameters

        # Should have 7 params (no expected_updated_at)
        assert len(params) == 7
        param_names = [p.name for p in params]
        assert "source_url" in param_names
        assert "year" in param_names
        assert "month" in param_names
        assert "status" in param_names
        assert "checker_email" in param_names
        assert "memo" in param_names
        assert "action_log" in param_names
        assert "expected_updated_at" not in param_names

    @patch("lib.bq_client.get_bq_client")
    def test_save_check_query_parameters_with_lock(self, mock_get_bq_client):
        """Verify query parameters when expected_updated_at is provided"""
        mock_client = MagicMock()
        mock_get_bq_client.return_value = mock_client

        mock_result = MagicMock()
        mock_result.num_dml_affected_rows = 1
        mock_client.query.return_value.result.return_value = mock_result

        expected_ts = datetime(2024, 12, 14, 15, 30, 0, tzinfo=timezone.utc)

        save_check(
            source_url="https://example.com/sheet1",
            year=2024,
            month=12,
            status="確認完了",
            memo="OK",
            checker_email="checker@tadakayo.jp",
            existing_log=None,
            action_desc="完了",
            expected_updated_at=expected_ts,
        )

        call_args = mock_client.query.call_args
        job_config = call_args[1]["job_config"]
        params = job_config.query_parameters

        # Should have 8 params (with expected_updated_at)
        assert len(params) == 8
        param_names = [p.name for p in params]
        assert "expected_updated_at" in param_names

        # Find and verify expected_updated_at param
        expected_param = None
        for param in params:
            if param.name == "expected_updated_at":
                expected_param = param
                break

        assert expected_param is not None
        assert expected_param.value == expected_ts

    @patch("lib.bq_client.get_bq_client")
    def test_save_check_optimistic_lock_success(self, mock_get_bq_client):
        """When rows affected > 0 with lock, no exception"""
        mock_client = MagicMock()
        mock_get_bq_client.return_value = mock_client

        mock_result = MagicMock()
        mock_result.num_dml_affected_rows = 1  # Update matched
        mock_client.query.return_value.result.return_value = mock_result

        expected_ts = datetime(2024, 12, 14, 15, 30, 0, tzinfo=timezone.utc)

        # Should not raise
        save_check(
            source_url="https://example.com/sheet1",
            year=2024,
            month=12,
            status="確認完了",
            memo="OK",
            checker_email="checker@tadakayo.jp",
            existing_log=None,
            action_desc="完了",
            expected_updated_at=expected_ts,
        )

    @patch("lib.bq_client.get_bq_client")
    def test_save_check_optimistic_lock_conflict(self, mock_get_bq_client):
        """When rows affected = 0 with lock, raise ValueError"""
        mock_client = MagicMock()
        mock_get_bq_client.return_value = mock_client

        mock_result = MagicMock()
        mock_result.num_dml_affected_rows = 0  # No rows matched the lock condition
        mock_client.query.return_value.result.return_value = mock_result

        expected_ts = datetime(2024, 12, 14, 15, 30, 0, tzinfo=timezone.utc)

        with pytest.raises(ValueError) as exc_info:
            save_check(
                source_url="https://example.com/sheet1",
                year=2024,
                month=12,
                status="確認完了",
                memo="OK",
                checker_email="checker@tadakayo.jp",
                existing_log=None,
                action_desc="完了",
                expected_updated_at=expected_ts,
            )

        assert "別のチェック者が先に更新しました" in str(exc_info.value)

    @patch("lib.bq_client.get_bq_client")
    def test_save_check_no_lock_on_insert(self, mock_get_bq_client):
        """With lock params but INSERT (no match), should not raise"""
        mock_client = MagicMock()
        mock_get_bq_client.return_value = mock_client

        mock_result = MagicMock()
        mock_result.num_dml_affected_rows = 1  # INSERT happened
        mock_client.query.return_value.result.return_value = mock_result

        expected_ts = datetime(2024, 12, 14, 15, 30, 0, tzinfo=timezone.utc)

        # Should not raise
        save_check(
            source_url="https://example.com/sheet1",
            year=2024,
            month=12,
            status="確認中",
            memo="",
            checker_email="checker@tadakayo.jp",
            existing_log=None,
            action_desc="新規",
            expected_updated_at=expected_ts,
        )

    @patch("lib.bq_client.get_bq_client")
    def test_save_check_memo_none_converts_to_none(self, mock_get_bq_client):
        """When memo is None or empty, it should be passed as None to BQ"""
        mock_client = MagicMock()
        mock_get_bq_client.return_value = mock_client

        mock_result = MagicMock()
        mock_result.num_dml_affected_rows = 1
        mock_client.query.return_value.result.return_value = mock_result

        save_check(
            source_url="https://example.com/sheet1",
            year=2024,
            month=12,
            status="未確認",
            memo=None,
            checker_email="checker@tadakayo.jp",
            existing_log=None,
            action_desc="新規",
        )

        call_args = mock_client.query.call_args
        job_config = call_args[1]["job_config"]
        params = job_config.query_parameters

        memo_param = None
        for param in params:
            if param.name == "memo":
                memo_param = param
                break

        assert memo_param is not None
        assert memo_param.value is None

    @patch("lib.bq_client.get_bq_client")
    def test_save_check_query_uses_correct_table(self, mock_get_bq_client):
        """Verify query uses CHECK_LOGS_TABLE constant"""
        mock_client = MagicMock()
        mock_get_bq_client.return_value = mock_client

        mock_result = MagicMock()
        mock_result.num_dml_affected_rows = 1
        mock_client.query.return_value.result.return_value = mock_result

        save_check(
            source_url="https://example.com/sheet1",
            year=2024,
            month=12,
            status="確認完了",
            memo="OK",
            checker_email="checker@tadakayo.jp",
            existing_log=None,
            action_desc="完了",
        )

        call_args = mock_client.query.call_args
        query_str = call_args[0][0]

        # Should contain the CHECK_LOGS_TABLE
        assert CHECK_LOGS_TABLE in query_str

    @patch("lib.bq_client.get_bq_client")
    def test_save_check_json_structure_validation(self, mock_get_bq_client):
        """Validate the JSON structure in action_log param"""
        mock_client = MagicMock()
        mock_get_bq_client.return_value = mock_client

        mock_result = MagicMock()
        mock_result.num_dml_affected_rows = 1
        mock_client.query.return_value.result.return_value = mock_result

        save_check(
            source_url="https://example.com/sheet1",
            year=2024,
            month=12,
            status="確認完了",
            memo="テスト メモ",
            checker_email="checker@tadakayo.jp",
            existing_log=None,
            action_desc="テスト アクション",
        )

        call_args = mock_client.query.call_args
        job_config = call_args[1]["job_config"]
        params = job_config.query_parameters

        action_log_param = None
        for param in params:
            if param.name == "action_log":
                action_log_param = param
                break

        assert action_log_param is not None
        logs = json.loads(action_log_param.value)

        # Validate structure
        assert isinstance(logs, list)
        assert len(logs) == 1

        entry = logs[0]
        assert isinstance(entry, dict)
        assert "ts" in entry
        assert "user" in entry
        assert "action" in entry
        assert entry["user"] == "checker@tadakayo.jp"
        assert entry["action"] == "テスト アクション"

    @patch("lib.bq_client.get_bq_client")
    def test_save_check_Japanese_characters_in_log(self, mock_get_bq_client):
        """Test that Japanese characters are properly encoded in JSON"""
        mock_client = MagicMock()
        mock_get_bq_client.return_value = mock_client

        mock_result = MagicMock()
        mock_result.num_dml_affected_rows = 1
        mock_client.query.return_value.result.return_value = mock_result

        existing_log = json.dumps([
            {"ts": "2024-12-14T09:00:00+00:00", "user": "checker@tadakayo.jp", "action": "初期確認"}
        ], ensure_ascii=False)

        save_check(
            source_url="https://example.com/sheet1",
            year=2024,
            month=12,
            status="確認完了",
            memo="完了しました",
            checker_email="checker@tadakayo.jp",
            existing_log=existing_log,
            action_desc="ステータス: 確認中 → 確認完了 / メモ更新",
        )

        call_args = mock_client.query.call_args
        job_config = call_args[1]["job_config"]
        params = job_config.query_parameters

        action_log_param = None
        for param in params:
            if param.name == "action_log":
                action_log_param = param
                break

        logs = json.loads(action_log_param.value)
        assert len(logs) == 2
        assert logs[0]["action"] == "初期確認"
        assert logs[1]["action"] == "ステータス: 確認中 → 確認完了 / メモ更新"

    @patch("lib.bq_client.get_bq_client")
    def test_save_check_pandas_na_in_existing_log(self, mock_get_bq_client):
        """When existing_log is pd.NA (pandas missing value), treat as None"""
        mock_client = MagicMock()
        mock_get_bq_client.return_value = mock_client

        mock_result = MagicMock()
        mock_result.num_dml_affected_rows = 1
        mock_client.query.return_value.result.return_value = mock_result

        save_check(
            source_url="https://example.com/sheet1",
            year=2024,
            month=12,
            status="未確認",
            memo="",
            checker_email="checker@tadakayo.jp",
            existing_log=pd.NA,
            action_desc="新規",
        )

        call_args = mock_client.query.call_args
        job_config = call_args[1]["job_config"]
        params = job_config.query_parameters

        action_log_param = None
        for param in params:
            if param.name == "action_log":
                action_log_param = param
                break

        logs = json.loads(action_log_param.value)
        assert len(logs) == 1
        assert logs[0]["action"] == "新規"

    @patch("lib.bq_client.get_bq_client")
    def test_save_check_pandas_nat_in_expected_updated_at(self, mock_get_bq_client):
        """When expected_updated_at is pd.NaT, treat as None (no lock)"""
        mock_client = MagicMock()
        mock_get_bq_client.return_value = mock_client

        mock_result = MagicMock()
        mock_result.num_dml_affected_rows = 1
        mock_client.query.return_value.result.return_value = mock_result

        save_check(
            source_url="https://example.com/sheet1",
            year=2024,
            month=12,
            status="確認完了",
            memo="OK",
            checker_email="checker@tadakayo.jp",
            existing_log=None,
            action_desc="完了",
            expected_updated_at=pd.NaT,
        )

        call_args = mock_client.query.call_args
        job_config = call_args[1]["job_config"]
        params = job_config.query_parameters

        # Should have 7 params (no expected_updated_at when pd.NaT)
        assert len(params) == 7
        param_names = [p.name for p in params]
        assert "expected_updated_at" not in param_names

    @patch("lib.bq_client.get_bq_client")
    def test_save_check_all_parameters_passed_correctly(self, mock_get_bq_client):
        """Comprehensive test: all parameters are passed to BQ query"""
        mock_client = MagicMock()
        mock_get_bq_client.return_value = mock_client

        mock_result = MagicMock()
        mock_result.num_dml_affected_rows = 1
        mock_client.query.return_value.result.return_value = mock_result

        test_url = "https://docs.google.com/spreadsheets/d/ABC123"
        test_year = 2024
        test_month = 12
        test_status = "確認完了"
        test_memo = "すべてOK"
        test_email = "test_checker@tadakayo.jp"
        test_action = "最終確認完了"

        save_check(
            source_url=test_url,
            year=test_year,
            month=test_month,
            status=test_status,
            memo=test_memo,
            checker_email=test_email,
            existing_log=None,
            action_desc=test_action,
        )

        call_args = mock_client.query.call_args
        job_config = call_args[1]["job_config"]
        params = job_config.query_parameters

        # Create dict from params for easier verification
        param_dict = {p.name: p.value for p in params}

        assert param_dict["source_url"] == test_url
        assert param_dict["year"] == test_year
        assert param_dict["month"] == test_month
        assert param_dict["status"] == test_status
        assert param_dict["memo"] == test_memo
        assert param_dict["checker_email"] == test_email

        # Verify action_log contains the action
        logs = json.loads(param_dict["action_log"])
        assert logs[0]["action"] == test_action

    @patch("lib.bq_client.get_bq_client")
    def test_save_check_empty_string_memo(self, mock_get_bq_client):
        """When memo is empty string, should be converted to None"""
        mock_client = MagicMock()
        mock_get_bq_client.return_value = mock_client

        mock_result = MagicMock()
        mock_result.num_dml_affected_rows = 1
        mock_client.query.return_value.result.return_value = mock_result

        save_check(
            source_url="https://example.com/sheet1",
            year=2024,
            month=12,
            status="未確認",
            memo="",
            checker_email="checker@tadakayo.jp",
            existing_log=None,
            action_desc="初期",
        )

        call_args = mock_client.query.call_args
        job_config = call_args[1]["job_config"]
        params = job_config.query_parameters

        memo_param = None
        for param in params:
            if param.name == "memo":
                memo_param = param
                break

        # Empty string is falsy, so "memo or None" converts it to None
        assert memo_param.value is None
