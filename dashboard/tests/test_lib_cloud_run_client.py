"""dashboard/lib/cloud_run_client.py のユニットテスト

invoke_collector (既存) + invoke_team_eval (PR-D) をカバー。
OIDC token 取得 + requests.post をモック。
"""

from unittest.mock import MagicMock, patch

import pytest

from lib import cloud_run_client


@pytest.fixture
def mock_token(monkeypatch):
    """OIDC token 取得をモック"""
    monkeypatch.setattr(
        "google.oauth2.id_token.fetch_id_token",
        lambda req, url: "fake-token",
    )
    monkeypatch.setattr(
        "google.auth.transport.requests.Request",
        lambda: MagicMock(),
    )


class TestInvokeCollector:
    def test_known_endpoint_returns_json(self, mock_token):
        with patch("lib.cloud_run_client.requests.post") as mock_post:
            resp = MagicMock()
            resp.json.return_value = {"status": "ok"}
            mock_post.return_value = resp
            result = cloud_run_client.invoke_collector("/sync/main-reports")
        assert result == {"status": "ok"}
        # bearer token がついている
        _, kwargs = mock_post.call_args
        assert kwargs["headers"]["Authorization"] == "Bearer fake-token"

    def test_unknown_endpoint_raises(self):
        with pytest.raises(ValueError):
            cloud_run_client.invoke_collector("/unknown")


class TestInvokeTeamEval:
    def test_default_body(self, mock_token):
        with patch("lib.cloud_run_client.requests.post") as mock_post:
            resp = MagicMock()
            resp.json.return_value = {"summary": {"total": 0}}
            mock_post.return_value = resp
            cloud_run_client.invoke_team_eval()
        _, kwargs = mock_post.call_args
        body = kwargs["json"]
        assert body == {"year": None, "month": None, "teams": None, "force": False}

    def test_single_team_uses_short_timeout(self, mock_token):
        with patch("lib.cloud_run_client.requests.post") as mock_post:
            resp = MagicMock()
            resp.json.return_value = {}
            mock_post.return_value = resp
            cloud_run_client.invoke_team_eval(
                year=2026, month=5, teams=["X"], force=False,
            )
        _, kwargs = mock_post.call_args
        assert kwargs["timeout"] == cloud_run_client.TEAM_EVAL_SINGLE_TIMEOUT
        assert kwargs["json"]["teams"] == ["X"]

    def test_bulk_uses_long_timeout(self, mock_token):
        with patch("lib.cloud_run_client.requests.post") as mock_post:
            resp = MagicMock()
            resp.json.return_value = {}
            mock_post.return_value = resp
            cloud_run_client.invoke_team_eval(
                year=2026, month=5, teams=None, force=True,
            )
        _, kwargs = mock_post.call_args
        assert kwargs["timeout"] == cloud_run_client.TEAM_EVAL_BULK_TIMEOUT
        assert kwargs["json"]["force"] is True

    def test_many_teams_uses_long_timeout(self, mock_token):
        """teams が 4 件以上 → 全隊一括相当 timeout"""
        with patch("lib.cloud_run_client.requests.post") as mock_post:
            resp = MagicMock()
            resp.json.return_value = {}
            mock_post.return_value = resp
            cloud_run_client.invoke_team_eval(
                year=2026, month=5, teams=["A", "B", "C", "D"],
            )
        _, kwargs = mock_post.call_args
        assert kwargs["timeout"] == cloud_run_client.TEAM_EVAL_BULK_TIMEOUT

    def test_raise_for_status_propagates_http_error(self, mock_token):
        import requests as _r
        with patch("lib.cloud_run_client.requests.post") as mock_post:
            resp = MagicMock()
            resp.raise_for_status.side_effect = _r.HTTPError("500")
            mock_post.return_value = resp
            with pytest.raises(_r.HTTPError):
                cloud_run_client.invoke_team_eval(year=2026, month=5, teams=["X"])

    def test_audience_url_is_collector(self, mock_token):
        """OIDC token の audience が COLLECTOR_URL (Cloud Run service URL) であること"""
        captured = {}
        def _fake_fetch(req, url):
            captured["url"] = url
            return "tok"
        with patch("google.oauth2.id_token.fetch_id_token", side_effect=_fake_fetch):
            with patch("lib.cloud_run_client.requests.post") as mock_post:
                resp = MagicMock()
                resp.json.return_value = {}
                mock_post.return_value = resp
                cloud_run_client.invoke_team_eval(year=2026, month=5, teams=["X"])
        assert captured["url"] == cloud_run_client.COLLECTOR_URL
