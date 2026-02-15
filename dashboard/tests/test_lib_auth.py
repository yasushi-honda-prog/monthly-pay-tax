"""Unit tests for lib/auth.py"""

from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch, call
from google.cloud import bigquery

# Import after streamlit mock is set up (via conftest.py)
from lib.auth import (
    get_user_email,
    _fetch_user_role,
    get_user_role,
    clear_role_cache,
)
from lib.constants import INITIAL_ADMIN_EMAIL, USERS_TABLE


class TestGetUserEmail:
    """Tests for get_user_email()"""

    def test_get_user_email_logged_in(self, mock_streamlit):
        """When user is logged in, return email"""
        mock_streamlit.user.is_logged_in = True
        mock_streamlit.user.email = "test@example.com"

        result = get_user_email()

        assert result == "test@example.com"

    def test_get_user_email_not_logged_in(self, mock_streamlit):
        """When user is not logged in, return empty string"""
        mock_streamlit.user.is_logged_in = False

        result = get_user_email()

        assert result == ""

    def test_get_user_email_logged_in_but_no_email(self, mock_streamlit):
        """When logged in but email is None, return empty string"""
        mock_streamlit.user.is_logged_in = True
        mock_streamlit.user.email = None

        result = get_user_email()

        assert result == ""

    def test_get_user_email_logged_in_but_empty_email(self, mock_streamlit):
        """When logged in but email is empty string, return empty string"""
        mock_streamlit.user.is_logged_in = True
        mock_streamlit.user.email = ""

        result = get_user_email()

        assert result == ""


class TestFetchUserRole:
    """Tests for _fetch_user_role()"""

    @patch("lib.auth.get_bq_client")
    def test_fetch_user_role_found(self, mock_get_bq_client):
        """When user exists in BQ, return role"""
        mock_client = MagicMock()
        mock_get_bq_client.return_value = mock_client

        # Mock BQ query result
        mock_row = MagicMock()
        mock_row.role = "checker"
        mock_result = MagicMock()
        mock_result.__iter__ = MagicMock(return_value=iter([mock_row]))
        mock_client.query.return_value.result.return_value = mock_result

        result = _fetch_user_role("test@example.com")

        assert result == "checker"
        mock_client.query.assert_called_once()
        # Verify query contains email parameter
        call_args = mock_client.query.call_args
        assert call_args[0][0]  # Query string exists
        assert "dashboard_users" in call_args[0][0]

    @patch("lib.auth.get_bq_client")
    def test_fetch_user_role_not_found(self, mock_get_bq_client):
        """When user does not exist in BQ, return None"""
        mock_client = MagicMock()
        mock_get_bq_client.return_value = mock_client

        # Mock empty result
        mock_result = MagicMock()
        mock_result.__iter__ = MagicMock(return_value=iter([]))
        mock_client.query.return_value.result.return_value = mock_result

        result = _fetch_user_role("unknown@example.com")

        assert result is None

    @patch("lib.auth.get_bq_client")
    def test_fetch_user_role_query_structure(self, mock_get_bq_client):
        """Verify query structure and parameters"""
        mock_client = MagicMock()
        mock_get_bq_client.return_value = mock_client

        mock_result = MagicMock()
        mock_result.__iter__ = MagicMock(return_value=iter([]))
        mock_client.query.return_value.result.return_value = mock_result

        test_email = "test@example.com"
        _fetch_user_role(test_email)

        # Get call arguments
        call_args = mock_client.query.call_args
        query_str = call_args[0][0]
        job_config = call_args[1]["job_config"]

        # Verify query contains required elements
        assert "SELECT role FROM" in query_str
        assert USERS_TABLE in query_str
        assert "@email" in query_str
        assert "LIMIT 1" in query_str

        # Verify job config has query parameter
        assert len(job_config.query_parameters) == 1
        param = job_config.query_parameters[0]
        assert param.name == "email"
        assert param.value == test_email


class TestGetUserRole:
    """Tests for get_user_role()"""

    @patch("lib.auth._fetch_user_role")
    def test_get_user_role_empty_email(self, mock_fetch, mock_streamlit):
        """When email is empty, return None without fetching"""
        result = get_user_role("")

        assert result is None
        mock_fetch.assert_not_called()

    @patch("lib.auth._fetch_user_role")
    def test_get_user_role_none_email(self, mock_fetch, mock_streamlit):
        """When email is None, return None without fetching"""
        result = get_user_role(None)

        assert result is None
        mock_fetch.assert_not_called()

    @patch("lib.auth._fetch_user_role")
    def test_get_user_role_from_cache(self, mock_fetch, mock_streamlit):
        """When role is cached in session_state, return cached value"""
        test_email = "test@example.com"
        cache_key = f"_user_role_{test_email}"
        mock_streamlit.session_state[cache_key] = "admin"

        result = get_user_role(test_email)

        assert result == "admin"
        mock_fetch.assert_not_called()

    @patch("lib.auth._fetch_user_role")
    def test_get_user_role_cache_miss(self, mock_fetch, mock_streamlit):
        """When role is not cached, fetch from BQ and cache it"""
        test_email = "test@example.com"
        mock_fetch.return_value = "viewer"

        result = get_user_role(test_email)

        assert result == "viewer"
        # Verify cache was set
        cache_key = f"_user_role_{test_email}"
        assert mock_streamlit.session_state[cache_key] == "viewer"
        mock_fetch.assert_called_once_with(test_email)

    @patch("lib.auth._fetch_user_role")
    def test_get_user_role_bq_exception_initial_admin(self, mock_fetch, mock_streamlit):
        """When BQ fails but user is INITIAL_ADMIN_EMAIL, return 'admin'"""
        mock_fetch.side_effect = Exception("BQ error")

        result = get_user_role(INITIAL_ADMIN_EMAIL)

        assert result == "admin"
        # Verify fallback was cached
        cache_key = f"_user_role_{INITIAL_ADMIN_EMAIL}"
        assert mock_streamlit.session_state[cache_key] == "admin"

    @patch("lib.auth._fetch_user_role")
    def test_get_user_role_bq_exception_regular_user(self, mock_fetch, mock_streamlit):
        """When BQ fails and user is not INITIAL_ADMIN_EMAIL, return None"""
        mock_fetch.side_effect = Exception("BQ error")

        result = get_user_role("regular@example.com")

        assert result is None
        # Verify None was cached
        cache_key = "_user_role_regular@example.com"
        assert mock_streamlit.session_state[cache_key] is None

    @patch("lib.auth._fetch_user_role")
    def test_get_user_role_bq_exception_logs_warning(self, mock_fetch, mock_streamlit):
        """When BQ fails, exception is logged"""
        mock_fetch.side_effect = Exception("Connection timeout")

        with patch("lib.auth.logger") as mock_logger:
            get_user_role("test@example.com")
            mock_logger.exception.assert_called_once()
            # Verify email is logged
            call_args = mock_logger.exception.call_args
            assert "test@example.com" in str(call_args)

    @patch("lib.auth._fetch_user_role")
    def test_get_user_role_multiple_calls_same_email_uses_cache(
        self, mock_fetch, mock_streamlit
    ):
        """Multiple calls with same email should only fetch once"""
        test_email = "test@example.com"
        mock_fetch.return_value = "checker"

        # First call
        result1 = get_user_role(test_email)
        # Second call
        result2 = get_user_role(test_email)

        assert result1 == "checker"
        assert result2 == "checker"
        # Should only fetch once
        assert mock_fetch.call_count == 1

    @patch("lib.auth._fetch_user_role")
    def test_get_user_role_different_emails_separate_cache(
        self, mock_fetch, mock_streamlit
    ):
        """Different emails should have separate cache entries"""
        email1 = "user1@example.com"
        email2 = "user2@example.com"
        mock_fetch.side_effect = ["admin", "viewer"]

        result1 = get_user_role(email1)
        result2 = get_user_role(email2)

        assert result1 == "admin"
        assert result2 == "viewer"
        # Both should be cached separately
        assert (
            mock_streamlit.session_state[f"_user_role_{email1}"] == "admin"
        )
        assert (
            mock_streamlit.session_state[f"_user_role_{email2}"] == "viewer"
        )

    @patch("lib.auth._fetch_user_role")
    def test_get_user_role_bq_returns_none(self, mock_fetch, mock_streamlit):
        """When BQ returns None (user not found), cache and return None"""
        test_email = "unknown@example.com"
        mock_fetch.return_value = None

        result = get_user_role(test_email)

        assert result is None
        cache_key = f"_user_role_{test_email}"
        assert mock_streamlit.session_state[cache_key] is None


class TestClearRoleCache:
    """Tests for clear_role_cache()"""

    def test_clear_role_cache_removes_user_role_keys(self, mock_streamlit):
        """clear_role_cache() removes all _user_role_* keys"""
        # Set up session state with cache entries
        mock_streamlit.session_state["_user_role_user1@example.com"] = "admin"
        mock_streamlit.session_state["_user_role_user2@example.com"] = "viewer"
        mock_streamlit.session_state["other_key"] = "value"

        clear_role_cache()

        # User role caches should be removed
        assert "_user_role_user1@example.com" not in mock_streamlit.session_state
        assert "_user_role_user2@example.com" not in mock_streamlit.session_state
        # Other keys should remain
        assert "other_key" in mock_streamlit.session_state
        assert mock_streamlit.session_state["other_key"] == "value"

    def test_clear_role_cache_idempotent(self, mock_streamlit):
        """Calling clear_role_cache() twice should be safe"""
        mock_streamlit.session_state["_user_role_test@example.com"] = "admin"
        mock_streamlit.session_state["other_key"] = "value"

        clear_role_cache()
        clear_role_cache()  # Should not raise

        assert "_user_role_test@example.com" not in mock_streamlit.session_state
        assert mock_streamlit.session_state["other_key"] == "value"

    def test_clear_role_cache_empty_session_state(self, mock_streamlit):
        """clear_role_cache() should not raise when session_state is empty"""
        mock_streamlit.session_state.clear()

        # Should not raise
        clear_role_cache()

    def test_clear_role_cache_mixed_keys(self, mock_streamlit):
        """clear_role_cache() removes only _user_role_* keys"""
        # Set up various keys
        mock_streamlit.session_state["_user_role_a@example.com"] = "admin"
        mock_streamlit.session_state["_user_role_b@example.com"] = "viewer"
        mock_streamlit.session_state["_other_cache_key"] = "value1"
        mock_streamlit.session_state["unrelated_key"] = "value2"

        clear_role_cache()

        # Only _user_role_* with email should be removed
        assert "_user_role_a@example.com" not in mock_streamlit.session_state
        assert "_user_role_b@example.com" not in mock_streamlit.session_state
        # Other keys remain
        assert "_other_cache_key" in mock_streamlit.session_state
        assert "unrelated_key" in mock_streamlit.session_state

    def test_clear_role_cache_integration(self, mock_streamlit):
        """Integration: cache after clear is independent"""
        test_email = "test@example.com"

        # Set cache
        with patch("lib.auth._fetch_user_role") as mock_fetch:
            mock_fetch.return_value = "admin"
            result1 = get_user_role(test_email)
            assert result1 == "admin"

        # Cache exists
        assert f"_user_role_{test_email}" in mock_streamlit.session_state

        # Clear cache
        clear_role_cache()
        assert f"_user_role_{test_email}" not in mock_streamlit.session_state

        # Fetch again (new cache)
        with patch("lib.auth._fetch_user_role") as mock_fetch:
            mock_fetch.return_value = "viewer"
            result2 = get_user_role(test_email)
            assert result2 == "viewer"
            # Cache should be updated
            assert (
                mock_streamlit.session_state[f"_user_role_{test_email}"]
                == "viewer"
            )


class TestIntegration:
    """Integration tests combining multiple functions"""

    @patch("lib.auth._fetch_user_role")
    def test_full_auth_flow_successful(self, mock_fetch, mock_streamlit):
        """Full flow: get email -> get role -> use cached role"""
        mock_streamlit.user.is_logged_in = True
        mock_streamlit.user.email = "test@example.com"
        mock_fetch.return_value = "checker"

        # Step 1: Get email
        email = get_user_email()
        assert email == "test@example.com"

        # Step 2: Get role (not cached yet)
        role1 = get_user_role(email)
        assert role1 == "checker"
        assert mock_fetch.call_count == 1

        # Step 3: Get role again (should use cache)
        role2 = get_user_role(email)
        assert role2 == "checker"
        assert mock_fetch.call_count == 1  # No additional fetch

        # Step 4: Clear cache
        clear_role_cache()

        # Step 5: Get role again (fetch again)
        role3 = get_user_role(email)
        assert role3 == "checker"
        assert mock_fetch.call_count == 2  # Cache was cleared

    @patch("lib.auth._fetch_user_role")
    def test_full_auth_flow_with_fallback(self, mock_fetch, mock_streamlit):
        """Full flow with BQ failure -> fallback to admin for INITIAL_ADMIN"""
        mock_streamlit.user.is_logged_in = True
        mock_streamlit.user.email = INITIAL_ADMIN_EMAIL
        mock_fetch.side_effect = Exception("BQ unavailable")

        email = get_user_email()
        assert email == INITIAL_ADMIN_EMAIL

        role = get_user_role(email)
        assert role == "admin"  # Fallback succeeded
