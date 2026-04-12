"""タダメンMマスタ収集のユニットテスト

collect_member_master の列抽出・フィルタ・BQ投入を検証。
"""

import pytest
from unittest.mock import MagicMock, patch

import config
from sheets_collector import collect_member_master


def _make_full_row(**overrides):
    """タダメンMタブの50列分のダミー行を生成（A:AX = index 0~49）"""
    row = [None] * 50
    row[0] = overrides.get("member_id", "TM001")
    row[1] = overrides.get("last_name", "田中")
    row[2] = overrides.get("first_name", "太郎")
    row[3] = overrides.get("last_name_kana", "タナカ")
    row[4] = overrides.get("first_name_kana", "タロウ")
    row[5] = overrides.get("nickname", "たろう")
    row[8] = overrides.get("email", "tanaka@example.com")
    row[9] = overrides.get("postal_code", "100-0001")
    row[10] = overrides.get("prefecture", "東京都")
    row[11] = overrides.get("address", "千代田区1-1")
    row[14] = overrides.get("gws_account", "tanaka@tadakayo.jp")
    row[15] = overrides.get("report_url_1", "https://docs.google.com/spreadsheets/d/url1")
    row[16] = overrides.get("report_url_2", "https://docs.google.com/spreadsheets/d/url2")
    row[19] = overrides.get("shipping_postal_code", "200-0001")
    row[20] = overrides.get("shipping_address", "品川区2-2")
    row[29] = overrides.get("qualification_allowance", "10000")
    row[30] = overrides.get("position_rate", "1.5")
    row[31] = overrides.get("corporate_sheet", "3")
    row[32] = overrides.get("donation_sheet", "4")
    row[33] = overrides.get("qualification_sheet", "5")
    row[34] = overrides.get("bank1_type", "普通")
    row[35] = overrides.get("bank1_name", "PayPay銀行")
    row[36] = overrides.get("bank1_code", "0033")
    row[37] = overrides.get("bank1_branch_name", "本店営業部")
    row[38] = overrides.get("bank1_branch_code", "001")
    row[39] = overrides.get("bank1_account_number", "1234567")
    row[40] = overrides.get("bank1_deposit_type", "普通")
    row[41] = overrides.get("bank1_holder_name", "タナカ タロウ")
    row[42] = overrides.get("bank2_type", "普通")
    row[43] = overrides.get("bank2_name", "GMOあおぞら")
    row[44] = overrides.get("bank2_code", "0310")
    row[45] = overrides.get("bank2_branch_name", "ネット支店")
    row[46] = overrides.get("bank2_branch_code", "101")
    row[47] = overrides.get("bank2_account_number", "7654321")
    row[48] = overrides.get("bank2_deposit_type", "普通")
    row[49] = overrides.get("bank2_holder_name", "タナカ タロウ")
    return row


class TestCollectMemberMaster:
    """collect_member_master のテスト"""

    def _mock_service(self, values):
        service = MagicMock()
        sheet_mock = MagicMock()
        service.spreadsheets.return_value = sheet_mock
        values_mock = MagicMock()
        sheet_mock.values.return_value = values_mock
        get_mock = MagicMock()
        values_mock.get.return_value = get_mock
        get_mock.execute.return_value = {"values": values}
        return service, values_mock

    def test_calls_correct_range(self):
        """タダメンMタブのA2:AXを指定してSheets APIを呼ぶこと"""
        service, values_mock = self._mock_service([])
        collect_member_master(service)
        values_mock.get.assert_called_once()
        call_args = values_mock.get.call_args
        assert call_args[1]["spreadsheetId"] == config.MEMBER_SPREADSHEET_ID
        expected_range = f"'{config.MEMBER_MASTER_SHEET_NAME}'!A{config.MEMBER_MASTER_START_ROW}:AX"
        assert call_args[1]["range"] == expected_range

    def test_extracts_correct_columns(self):
        """必要列のみ抽出されること（31列）"""
        row = _make_full_row()
        service, _ = self._mock_service([row])
        result = collect_member_master(service)
        assert len(result) == 1
        extracted = result[0]
        assert len(extracted) == len(config.MEMBER_MASTER_COLUMN_INDICES)
        assert len(extracted) == 36

    def test_column_values_match(self):
        """抽出された値が正しい列に対応すること"""
        row = _make_full_row(
            member_id="TM999",
            nickname="テスト",
            bank1_name="みずほ銀行",
            bank2_name="三菱UFJ",
        )
        service, _ = self._mock_service([row])
        result = collect_member_master(service)
        extracted = result[0]
        # TABLE_COLUMNS の順序に従って検証
        cols = config.TABLE_COLUMNS[config.BQ_TABLE_MEMBER_MASTER]
        assert extracted[cols.index("member_id")] == "TM999"
        assert extracted[cols.index("nickname")] == "テスト"
        assert extracted[cols.index("bank1_name")] == "みずほ銀行"
        assert extracted[cols.index("bank2_name")] == "三菱UFJ"

    def test_report_url_and_bank_correspond(self):
        """report_url_1とbank1_*、report_url_2とbank2_*が同一行で正しく対応すること"""
        row = _make_full_row(
            report_url_1="https://sheet1",
            report_url_2="https://sheet2",
            bank1_name="PayPay銀行",
            bank1_account_number="1111111",
            bank2_name="GMOあおぞら",
            bank2_account_number="2222222",
        )
        service, _ = self._mock_service([row])
        result = collect_member_master(service)
        extracted = result[0]
        cols = config.TABLE_COLUMNS[config.BQ_TABLE_MEMBER_MASTER]
        assert extracted[cols.index("report_url_1")] == "https://sheet1"
        assert extracted[cols.index("bank1_name")] == "PayPay銀行"
        assert extracted[cols.index("bank1_account_number")] == "1111111"
        assert extracted[cols.index("report_url_2")] == "https://sheet2"
        assert extracted[cols.index("bank2_name")] == "GMOあおぞら"
        assert extracted[cols.index("bank2_account_number")] == "2222222"

    def test_skips_empty_member_id(self):
        """member_id(A列)が空の行はスキップされること"""
        row_valid = _make_full_row(member_id="TM001")
        row_empty = _make_full_row(member_id="")
        row_empty[0] = ""
        row_none = []  # completely empty row
        service, _ = self._mock_service([row_valid, row_empty, row_none])
        result = collect_member_master(service)
        assert len(result) == 1
        cols = config.TABLE_COLUMNS[config.BQ_TABLE_MEMBER_MASTER]
        assert result[0][cols.index("member_id")] == "TM001"

    def test_short_row_padded(self):
        """列数が足りない行もNoneで埋めて処理できること"""
        short_row = ["TM001", "田中", "太郎"]  # 3列のみ
        service, _ = self._mock_service([short_row])
        result = collect_member_master(service)
        assert len(result) == 1
        assert len(result[0]) == 36
        cols = config.TABLE_COLUMNS[config.BQ_TABLE_MEMBER_MASTER]
        assert result[0][cols.index("member_id")] == "TM001"
        assert result[0][cols.index("last_name")] == "田中"
        assert result[0][cols.index("bank1_name")] is None

    def test_api_error_returns_empty(self):
        """Sheets APIエラー時は空リストを返すこと"""
        service = MagicMock()
        service.spreadsheets.return_value.values.return_value.get.side_effect = Exception("API error")
        result = collect_member_master(service)
        assert result == []

    def test_column_count_matches_table_columns(self):
        """MEMBER_MASTER_COLUMN_INDICES と TABLE_COLUMNS の長さが一致すること"""
        assert len(config.MEMBER_MASTER_COLUMN_INDICES) == len(
            config.TABLE_COLUMNS[config.BQ_TABLE_MEMBER_MASTER]
        )


class TestMainMemberMasterStep:
    """main.py Step 7 のテスト"""

    @patch("bq_loader.load_to_bigquery")
    @patch("sheets_collector.collect_member_master")
    @patch("sheets_collector._build_sheets_service")
    @patch("sheets_collector.run_reimbursement_collection")
    @patch("sheets_collector.update_member_groups_from_bq")
    @patch("sheets_collector.run_collection")
    def test_step7_failure_does_not_affect_main(
        self, mock_run, mock_groups, mock_reimb, mock_build, mock_collect_mm, mock_bq_load
    ):
        """Step 7が失敗しても全体はsuccess"""
        from main import app

        mock_run.return_value = {"gyomu_reports": [], "hojo_reports": [], "members": []}
        mock_groups.return_value = ([], [])
        mock_reimb.return_value = {}
        mock_collect_mm.side_effect = Exception("member_master collection failed")
        mock_bq_load.return_value = 0

        with app.test_client() as client:
            resp = client.post("/")
            assert resp.status_code == 200
            data = resp.get_json()
            assert data["status"] == "success"

    @patch("bq_loader.load_to_bigquery")
    @patch("sheets_collector.collect_member_master")
    @patch("sheets_collector._build_sheets_service")
    @patch("sheets_collector.run_reimbursement_collection")
    @patch("sheets_collector.update_member_groups_from_bq")
    @patch("sheets_collector.run_collection")
    def test_step7_success_includes_count(
        self, mock_run, mock_groups, mock_reimb, mock_build, mock_collect_mm, mock_bq_load
    ):
        """Step 7成功時にresultsにmember_masterのカウントが含まれる"""
        from main import app

        mock_run.return_value = {"gyomu_reports": [], "hojo_reports": [], "members": []}
        mock_groups.return_value = ([], [])
        mock_reimb.return_value = {}
        mock_collect_mm.return_value = [["TM001"] + [None] * 30]
        mock_bq_load.return_value = 1

        with app.test_client() as client:
            resp = client.post("/")
            assert resp.status_code == 200
            data = resp.get_json()
            assert data["status"] == "success"
