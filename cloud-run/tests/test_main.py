"""手動同期エンドポイントのユニットテスト

POST /sync/main-reports, POST /sync/reimbursement, POST /sync/member-master の
正常系・異常系を検証。実際の Sheets/BQ アクセスはモック。
"""

import pytest
from unittest.mock import patch, MagicMock

from main import app


@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


class TestSyncMainReports:
    """POST /sync/main-reports"""

    @patch("main.bq_loader")
    @patch("main.sheets_collector")
    def test_success(self, mock_sheets, mock_bq, client):
        mock_sheets.run_collection.return_value = {"gyomu_reports": [["r1"]]}
        mock_bq.load_all.return_value = {
            "gyomu_reports": 100,
            "hojo_reports": 50,
            "members": 60,
        }

        response = client.post("/sync/main-reports")

        assert response.status_code == 200
        payload = response.get_json()
        assert payload["status"] == "success"
        assert payload["endpoint"] == "/sync/main-reports"
        assert payload["tables"]["gyomu_reports"] == 100
        assert "elapsed_seconds" in payload

    @patch("main.sheets_collector")
    def test_error(self, mock_sheets, client):
        mock_sheets.run_collection.side_effect = RuntimeError("boom")

        response = client.post("/sync/main-reports")

        assert response.status_code == 500
        payload = response.get_json()
        assert payload["status"] == "error"
        assert payload["endpoint"] == "/sync/main-reports"
        assert "boom" in payload["message"]


class TestSyncReimbursement:
    """POST /sync/reimbursement"""

    @patch("main.bq_loader")
    @patch("main.sheets_collector")
    def test_success(self, mock_sheets, mock_bq, client):
        mock_sheets.run_reimbursement_collection.return_value = {
            "reimbursement_items": [["r1"]],
        }
        mock_bq.load_all.return_value = {"reimbursement_items": 2250}

        response = client.post("/sync/reimbursement")

        assert response.status_code == 200
        payload = response.get_json()
        assert payload["status"] == "success"
        assert payload["endpoint"] == "/sync/reimbursement"
        assert payload["tables"]["reimbursement_items"] == 2250

    @patch("main.sheets_collector")
    def test_error(self, mock_sheets, client):
        mock_sheets.run_reimbursement_collection.side_effect = RuntimeError("fail")

        response = client.post("/sync/reimbursement")

        assert response.status_code == 500
        payload = response.get_json()
        assert payload["status"] == "error"
        assert "fail" in payload["message"]


class TestSyncMemberMaster:
    """POST /sync/member-master"""

    @patch("main.bq_loader")
    @patch("main.sheets_collector")
    def test_success(self, mock_sheets, mock_bq, client):
        mock_sheets._build_sheets_service.return_value = MagicMock()
        mock_sheets.collect_member_master.return_value = [["m1"]]
        mock_bq.load_to_bigquery.return_value = 240
        mock_bq.config.BQ_TABLE_MEMBER_MASTER = "member_master"

        response = client.post("/sync/member-master")

        assert response.status_code == 200
        payload = response.get_json()
        assert payload["status"] == "success"
        assert payload["endpoint"] == "/sync/member-master"
        assert payload["tables"]["member_master"] == 240

    @patch("main.sheets_collector")
    def test_error(self, mock_sheets, client):
        mock_sheets._build_sheets_service.side_effect = RuntimeError("auth failed")

        response = client.post("/sync/member-master")

        assert response.status_code == 500
        payload = response.get_json()
        assert payload["status"] == "error"
        assert "auth failed" in payload["message"]


class TestHealth:
    """GET /health (既存エンドポイント、回帰確認)"""

    def test_health_ok(self, client):
        response = client.get("/health")
        assert response.status_code == 200
        assert response.get_json() == {"status": "ok"}
