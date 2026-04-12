"""立替金シート収集のユニットテスト

extract_nickname / list_reimbursement_sheets / get_reimbursement_sheet_data /
collect_reimbursement_data の動作を検証。
"""

import httplib2
import pytest
from unittest.mock import MagicMock, patch, call

from googleapiclient.errors import HttpError

import config
from sheets_collector import (
    extract_nickname,
    list_reimbursement_sheets,
    get_reimbursement_sheet_data,
    collect_reimbursement_data,
    run_reimbursement_collection,
)


class TestExtractNickname:
    """ファイル名からのニックネーム抽出テスト"""

    def test_standard_ascii_name(self):
        name = "【KOU】委託事業_立替金等入力シート_仮払い機能付"
        assert extract_nickname(name) == "KOU"

    def test_japanese_name(self):
        name = "【みっつ】委託事業_立替金等入力シート_仮払い機能付"
        assert extract_nickname(name) == "みっつ"

    def test_name_with_number_suffix(self):
        name = "【ゆり①】委託事業_立替金等入力シート_仮払い機能付"
        assert extract_nickname(name) == "ゆり①"

    def test_no_brackets_returns_none(self):
        name = "配布管理用_立替金シート"
        assert extract_nickname(name) is None

    def test_empty_brackets(self):
        name = "【】委託事業_立替金等入力シート"
        assert extract_nickname(name) is None or extract_nickname(name) == ""


class TestListReimbursementSheets:
    """Drive API フォルダ一覧取得のテスト"""

    @patch("sheets_collector.time.sleep")
    def test_returns_sheet_list(self, mock_sleep):
        mock_drive = MagicMock()
        mock_drive.files().list().execute.return_value = {
            "files": [
                {"id": "abc123", "name": "【KOU】委託事業_立替金等入力シート_仮払い機能付"},
                {"id": "def456", "name": "【みっつ】委託事業_立替金等入力シート_仮払い機能付"},
            ],
        }

        result = list_reimbursement_sheets(mock_drive)

        assert len(result) == 2
        assert result[0]["id"] == "abc123"
        assert result[0]["nickname"] == "KOU"
        assert result[1]["nickname"] == "みっつ"

    @patch("sheets_collector.time.sleep")
    def test_handles_pagination(self, mock_sleep):
        mock_drive = MagicMock()
        mock_drive.files().list().execute.side_effect = [
            {
                "files": [{"id": "a1", "name": "【A】委託事業_立替金等入力シート_仮払い機能付"}],
                "nextPageToken": "page2",
            },
            {
                "files": [{"id": "b2", "name": "【B】委託事業_立替金等入力シート_仮払い機能付"}],
            },
        ]

        result = list_reimbursement_sheets(mock_drive)

        assert len(result) == 2
        assert result[0]["nickname"] == "A"
        assert result[1]["nickname"] == "B"

    @patch("sheets_collector.time.sleep")
    def test_skips_files_without_nickname(self, mock_sleep):
        mock_drive = MagicMock()
        mock_drive.files().list().execute.return_value = {
            "files": [
                {"id": "a1", "name": "【KOU】委託事業_立替金等入力シート_仮払い機能付"},
                {"id": "b2", "name": "管理用_テンプレート"},
            ],
        }

        result = list_reimbursement_sheets(mock_drive)

        assert len(result) == 1
        assert result[0]["nickname"] == "KOU"

    @patch("sheets_collector.time.sleep")
    def test_api_error_returns_empty(self, mock_sleep):
        mock_drive = MagicMock()
        resp = httplib2.Response({"status": 403})
        mock_drive.files().list().execute.side_effect = HttpError(resp, b"Forbidden")

        result = list_reimbursement_sheets(mock_drive)

        assert result == []


class TestGetReimbursementSheetData:
    """立替金シートデータ取得のテスト"""

    @patch("sheets_collector.time.sleep")
    def test_filters_example_rows(self, mock_sleep):
        mock_service = MagicMock()
        mock_service.spreadsheets().values().get().execute.return_value = {
            "values": [
                ["例", "2026年", "3月20日", "ケアプーPJ", "旅費交通費", "新幹線代", "¥21,510", "", "東京", "大阪", "訪問", "url"],
                ["", "2026年", "4月1日", "経産省PJ", "個人立替費", "文具", "¥500", "", "", "", "事務", "url2"],
            ],
        }

        result = get_reimbursement_sheet_data(mock_service, "test_id")

        assert len(result) == 1
        assert result[0][1] == "2026年"
        assert result[0][3] == "経産省PJ"

    @patch("sheets_collector.time.sleep")
    def test_filters_empty_rows(self, mock_sleep):
        mock_service = MagicMock()
        mock_service.spreadsheets().values().get().execute.return_value = {
            "values": [
                ["", "2026年", "3月20日", "ケアプーPJ", "旅費交通費", "テスト", "¥1,000"],
                [],
                ["", "", "", "", "", "", ""],
            ],
        }

        result = get_reimbursement_sheet_data(mock_service, "test_id")

        assert len(result) == 1

    @patch("sheets_collector.time.sleep")
    def test_keeps_valid_rows(self, mock_sleep):
        mock_service = MagicMock()
        mock_service.spreadsheets().values().get().execute.return_value = {
            "values": [
                ["", "2026年", "3月20日", "WAM-出張タダスクPJ", "旅費交通費", "新幹線代", "¥21,510", "", "東京", "仙台", "訪問", "pdf_url"],
                ["", "2026年", "4月5日", "その他", "個人立替費", "文具", "¥300", "", "", "", "事務", ""],
            ],
        }

        result = get_reimbursement_sheet_data(mock_service, "test_id")

        assert len(result) == 2

    @patch("sheets_collector.time.sleep")
    def test_returns_empty_on_error(self, mock_sleep):
        mock_service = MagicMock()
        resp = httplib2.Response({"status": 404})
        mock_service.spreadsheets().values().get().execute.side_effect = HttpError(resp, b"Not Found")

        result = get_reimbursement_sheet_data(mock_service, "test_id")

        assert result == []


class TestCollectReimbursementData:
    """collect_reimbursement_data の統合テスト"""

    @patch("sheets_collector.get_reimbursement_sheet_data")
    @patch("sheets_collector.list_reimbursement_sheets")
    @patch("sheets_collector.time.sleep")
    def test_prepends_url_and_nickname(self, mock_sleep, mock_list, mock_data):
        mock_list.return_value = [
            {"id": "abc123", "name": "【KOU】テスト", "nickname": "KOU"},
        ]
        mock_data.return_value = [
            ["", "2026年", "3月20日", "ケアプーPJ", "旅費交通費", "新幹線", "¥21,510"],
        ]

        result = collect_reimbursement_data(MagicMock(), MagicMock())

        assert len(result) == 1
        assert result[0][0] == "https://docs.google.com/spreadsheets/d/abc123/edit"
        assert result[0][1] == "KOU"
        assert result[0][2] == ""
        assert result[0][3] == "2026年"

    @patch("sheets_collector.get_reimbursement_sheet_data")
    @patch("sheets_collector.list_reimbursement_sheets")
    @patch("sheets_collector.time.sleep")
    def test_handles_sheet_with_no_data(self, mock_sleep, mock_list, mock_data):
        mock_list.return_value = [
            {"id": "abc", "name": "【KOU】テスト", "nickname": "KOU"},
            {"id": "def", "name": "【A】テスト", "nickname": "A"},
        ]
        mock_data.side_effect = [[], [["", "2026年", "5月1日"]]]

        result = collect_reimbursement_data(MagicMock(), MagicMock())

        assert len(result) == 1
        assert result[0][1] == "A"


class TestRunReimbursementCollection:
    """run_reimbursement_collection エントリポイントのテスト"""

    @patch("sheets_collector._build_drive_service")
    @patch("sheets_collector._build_sheets_service")
    @patch("sheets_collector.collect_reimbursement_data")
    def test_returns_correct_table_structure(self, mock_collect, mock_sheets, mock_drive):
        mock_sheets.return_value = MagicMock()
        mock_drive.return_value = MagicMock()
        mock_collect.return_value = [
            [
                "https://docs.google.com/spreadsheets/d/test1/edit",
                "KOU",
                "",
                "2026年",
                "3月20日",
                "ケアプーPJ",
                "旅費交通費",
                "新幹線代",
                "¥21,510",
                "¥10,000",
                "東京",
                "大阪",
                "訪問",
                "https://example.com/receipt.pdf",
            ]
        ]

        result = run_reimbursement_collection()

        assert config.BQ_TABLE_REIMBURSEMENT in result
        assert len(result[config.BQ_TABLE_REIMBURSEMENT]) == 1
        assert result[config.BQ_TABLE_REIMBURSEMENT][0][1] == "KOU"

    @patch("sheets_collector._build_drive_service")
    @patch("sheets_collector._build_sheets_service")
    @patch("sheets_collector.collect_reimbursement_data")
    def test_handles_no_data_gracefully(self, mock_collect, mock_sheets, mock_drive):
        mock_sheets.return_value = MagicMock()
        mock_drive.return_value = MagicMock()
        mock_collect.return_value = []

        result = run_reimbursement_collection()

        assert config.BQ_TABLE_REIMBURSEMENT in result
        assert len(result[config.BQ_TABLE_REIMBURSEMENT]) == 0
