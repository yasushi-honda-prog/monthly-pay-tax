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
    _find_input_tab_name,
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


class TestFindInputTabName:
    """タブ名動的検索のテスト"""

    @patch("sheets_collector.time.sleep")
    def test_finds_tab_with_prefix_0(self, mock_sleep):
        mock_service = MagicMock()
        mock_service.spreadsheets().get().execute.return_value = {
            "sheets": [
                {"properties": {"title": "0入力シート"}},
                {"properties": {"title": "0リスト用"}},
            ],
        }

        assert _find_input_tab_name(mock_service, "test_id") == "0入力シート"

    @patch("sheets_collector.time.sleep")
    def test_finds_tab_with_prefix_2(self, mock_sleep):
        mock_service = MagicMock()
        mock_service.spreadsheets().get().execute.return_value = {
            "sheets": [
                {"properties": {"title": "2入力シート"}},
                {"properties": {"title": "0リスト用"}},
            ],
        }

        assert _find_input_tab_name(mock_service, "test_id") == "2入力シート"

    @patch("sheets_collector.time.sleep")
    def test_returns_none_when_no_match(self, mock_sleep):
        mock_service = MagicMock()
        mock_service.spreadsheets().get().execute.return_value = {
            "sheets": [
                {"properties": {"title": "リスト用"}},
            ],
        }

        assert _find_input_tab_name(mock_service, "test_id") is None

    @patch("sheets_collector.time.sleep")
    def test_returns_none_on_api_error(self, mock_sleep):
        mock_service = MagicMock()
        resp = httplib2.Response({"status": 403})
        mock_service.spreadsheets().get().execute.side_effect = HttpError(resp, b"Forbidden")

        assert _find_input_tab_name(mock_service, "test_id") is None


def _row(*cells_text, hyperlink_at=None) -> dict:
    """rowData の 1 行をテキストのみ (+任意の hyperlink) から組み立てる"""
    values = []
    for i, text in enumerate(cells_text):
        cell: dict = {"formattedValue": text} if text else {}
        if hyperlink_at and i in hyperlink_at:
            cell["hyperlink"] = hyperlink_at[i]
        values.append(cell)
    return {"values": values}


def _mock_service_with_tab(tab_name="0入力シート"):
    """タブ名検索 + spreadsheets.get(includeGridData) の両方をモックしたサービスを作成"""
    mock_service = MagicMock()
    mock_spreadsheets = MagicMock()
    mock_service.spreadsheets.return_value = mock_spreadsheets

    # 1 回目: spreadsheets().get(fields="sheets.properties.title") → タブ名検索
    # 2 回目: spreadsheets().get(includeGridData=True, ...) → データ取得
    # MagicMock の get() は呼ぶたびに同じ MagicMock を返すので、
    # side_effect ではなく context マネージャ風に切り替えるため、
    # `get` 自体に side_effect を仕掛ける
    tab_lookup_response = MagicMock()
    tab_lookup_response.execute.return_value = {
        "sheets": [{"properties": {"title": tab_name}}],
    }
    grid_response = MagicMock()
    # grid_response.execute.return_value はテストごとに上書き
    mock_spreadsheets.get.side_effect = [tab_lookup_response, grid_response]

    return mock_service, grid_response


class TestGetReimbursementSheetData:
    """立替金シートデータ取得のテスト"""

    @patch("sheets_collector.time.sleep")
    def test_filters_example_rows(self, mock_sleep):
        mock_service, grid_response = _mock_service_with_tab()
        grid_response.execute.return_value = {
            "sheets": [{"data": [{"rowData": [
                _row("例", "2026年", "3月20日", "ケアプーPJ", "旅費交通費", "新幹線代", "¥21,510", "", "東京", "大阪", "訪問", "url"),
                _row("", "2026年", "4月1日", "経産省PJ", "個人立替費", "文具", "¥500", "", "", "", "事務", "url2"),
            ]}]}]
        }

        result = get_reimbursement_sheet_data(mock_service, "test_id")

        assert len(result) == 1
        assert result[0][1] == "2026年"
        assert result[0][3] == "経産省PJ"

    @patch("sheets_collector.time.sleep")
    def test_filters_empty_rows(self, mock_sleep):
        mock_service, grid_response = _mock_service_with_tab()
        grid_response.execute.return_value = {
            "sheets": [{"data": [{"rowData": [
                _row("", "2026年", "3月20日", "ケアプーPJ", "旅費交通費", "テスト", "¥1,000"),
                {},  # 完全空行 (values キーなし)
                _row("", "", "", "", "", "", ""),
            ]}]}]
        }

        result = get_reimbursement_sheet_data(mock_service, "test_id")

        assert len(result) == 1

    @patch("sheets_collector.time.sleep")
    def test_keeps_valid_rows(self, mock_sleep):
        mock_service, grid_response = _mock_service_with_tab()
        grid_response.execute.return_value = {
            "sheets": [{"data": [{"rowData": [
                _row("", "2026年", "3月20日", "WAM-出張タダスクPJ", "旅費交通費", "新幹線代", "¥21,510", "", "東京", "仙台", "訪問", "pdf_url"),
                _row("", "2026年", "4月5日", "その他", "個人立替費", "文具", "¥300", "", "", "", "事務", ""),
            ]}]}]
        }

        result = get_reimbursement_sheet_data(mock_service, "test_id")

        assert len(result) == 2

    @patch("sheets_collector.time.sleep")
    def test_extracts_hyperlink_from_receipt_cell(self, mock_sleep):
        """=HYPERLINK("url", "text") を含むセルから URL を抽出する (#106)"""
        mock_service, grid_response = _mock_service_with_tab()
        grid_response.execute.return_value = {
            "sheets": [{"data": [{"rowData": [
                _row(
                    "", "2026年", "4月1日", "経産省PJ", "個人立替費", "文具",
                    "¥500", "", "", "", "事務", "ファイル名.pdf",
                    hyperlink_at={11: "https://drive.google.com/file/d/abc123/view"},
                ),
            ]}]}]
        }

        result = get_reimbursement_sheet_data(mock_service, "test_id")

        assert len(result) == 1
        # L 列 (index 11) には formattedValue ではなく hyperlink が入る
        assert result[0][11] == "https://drive.google.com/file/d/abc123/view"

    @patch("sheets_collector.time.sleep")
    def test_keeps_plain_text_when_no_hyperlink(self, mock_sleep):
        """hyperlink 属性がないセルは formattedValue を維持 (後方互換)"""
        mock_service, grid_response = _mock_service_with_tab()
        grid_response.execute.return_value = {
            "sheets": [{"data": [{"rowData": [
                _row("", "2026年", "4月1日", "経産省PJ", "個人立替費", "文具",
                     "¥500", "", "", "", "事務", "領収書なし"),
            ]}]}]
        }

        result = get_reimbursement_sheet_data(mock_service, "test_id")

        assert len(result) == 1
        assert result[0][11] == "領収書なし"

    @patch("sheets_collector.time.sleep")
    def test_pads_short_row_when_hyperlink_present(self, mock_sleep):
        """API が trailing 空セルを省略して 12 列未満の row を返しても受領書 hyperlink は拾う"""
        mock_service, grid_response = _mock_service_with_tab()
        # K 列 (index 10) までしかないが、L 列 (index 11) に hyperlink のみ
        # （実際の API では起こりにくいが念のため defensive にカバー）
        grid_response.execute.return_value = {
            "sheets": [{"data": [{"rowData": [
                {
                    "values": [
                        {"formattedValue": ""},
                        {"formattedValue": "2026年"},
                        {"formattedValue": "4月1日"},
                        {"formattedValue": "経産省PJ"},
                        {"formattedValue": "個人立替費"},
                        {"formattedValue": "文具"},
                        {"formattedValue": "¥500"},
                        {},
                        {},
                        {},
                        {"formattedValue": "事務"},
                        {"hyperlink": "https://drive.google.com/file/d/xyz/view"},
                    ]
                }
            ]}]}]
        }

        result = get_reimbursement_sheet_data(mock_service, "test_id")

        assert len(result) == 1
        assert result[0][11] == "https://drive.google.com/file/d/xyz/view"

    @patch("sheets_collector.time.sleep")
    def test_returns_empty_on_values_error(self, mock_sleep):
        mock_service, grid_response = _mock_service_with_tab()
        resp = httplib2.Response({"status": 404})
        grid_response.execute.side_effect = HttpError(resp, b"Not Found")

        result = get_reimbursement_sheet_data(mock_service, "test_id")

        assert result == []

    @patch("sheets_collector.time.sleep")
    def test_returns_empty_when_tab_not_found(self, mock_sleep):
        mock_service = MagicMock()
        mock_service.spreadsheets().get().execute.return_value = {
            "sheets": [{"properties": {"title": "リスト用"}}],
        }

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
                "¥10,000",       # advance_amount (H: 仮払金額)
                "東京",          # from_station (I: 利用区間・発)
                "大阪",          # to_station (J: 利用区間・着)
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
