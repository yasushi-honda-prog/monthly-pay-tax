"""list_group_members のユニットテスト

Admin Directory API members().list() のページネーション・エラーハンドリングを検証。
"""

import httplib2
from unittest.mock import MagicMock, patch

from googleapiclient.errors import HttpError

from sheets_collector import list_group_members


class TestListGroupMembers:
    """list_group_members のテスト"""

    @patch("sheets_collector.time.sleep")
    def test_returns_member_emails(self, mock_sleep):
        """正常時にUSERタイプのメンバーメールアドレスを返すこと"""
        mock_service = MagicMock()
        mock_service.members().list().execute.return_value = {
            "members": [
                {"type": "USER", "email": "alice@tadakayo.jp"},
                {"type": "USER", "email": "Bob@tadakayo.jp"},
                {"type": "GROUP", "email": "nested-group@tadakayo.jp"},
            ]
        }

        result = list_group_members(mock_service, "test-group@tadakayo.jp")

        assert result == ["alice@tadakayo.jp", "bob@tadakayo.jp"]
        assert "nested-group@tadakayo.jp" not in result

    @patch("sheets_collector.time.sleep")
    def test_handles_pagination(self, mock_sleep):
        """ページネーションで全メンバーを取得すること"""
        mock_service = MagicMock()
        mock_list = mock_service.members().list
        # 1ページ目
        mock_list().execute.side_effect = [
            {
                "members": [{"type": "USER", "email": "alice@tadakayo.jp"}],
                "nextPageToken": "page2",
            },
        ]
        # ページネーション呼び出しを再設定
        call_count = [0]
        pages = [
            {
                "members": [{"type": "USER", "email": "alice@tadakayo.jp"}],
                "nextPageToken": "page2",
            },
            {
                "members": [{"type": "USER", "email": "bob@tadakayo.jp"}],
            },
        ]

        def side_effect(*args, **kwargs):
            idx = call_count[0]
            call_count[0] += 1
            return pages[idx] if idx < len(pages) else {}

        mock_list().execute.side_effect = side_effect

        result = list_group_members(mock_service, "test-group@tadakayo.jp")

        assert len(result) == 2
        assert "alice@tadakayo.jp" in result
        assert "bob@tadakayo.jp" in result

    @patch("sheets_collector.time.sleep")
    def test_empty_group_email_returns_empty(self, mock_sleep):
        """空のグループメールで空リストを返すこと"""
        mock_service = MagicMock()
        assert list_group_members(mock_service, "") == []
        assert list_group_members(mock_service, None) == []

    @patch("sheets_collector.time.sleep")
    def test_http_error_returns_empty(self, mock_sleep):
        """HttpError時に空リストを返すこと"""
        mock_service = MagicMock()
        mock_service.members().list().execute.side_effect = HttpError(
            httplib2.Response({"status": 403}), b"Forbidden"
        )

        result = list_group_members(mock_service, "test-group@tadakayo.jp")

        assert result == []

    @patch("sheets_collector.time.sleep")
    def test_generic_error_returns_empty(self, mock_sleep):
        """一般例外時に空リストを返すこと"""
        mock_service = MagicMock()
        mock_service.members().list().execute.side_effect = Exception("network error")

        result = list_group_members(mock_service, "test-group@tadakayo.jp")

        assert result == []

    @patch("sheets_collector.time.sleep")
    def test_filters_out_members_without_email(self, mock_sleep):
        """emailがないメンバーを除外すること"""
        mock_service = MagicMock()
        mock_service.members().list().execute.return_value = {
            "members": [
                {"type": "USER", "email": "alice@tadakayo.jp"},
                {"type": "USER"},  # emailなし
                {"type": "USER", "email": ""},  # 空文字
            ]
        }

        result = list_group_members(mock_service, "test-group@tadakayo.jp")

        assert result == ["alice@tadakayo.jp"]
