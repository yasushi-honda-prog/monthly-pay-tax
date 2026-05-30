"""Google Chat 障害通知（chat_notifier）のユニットテスト

notify の no-op / 投稿 / 失敗の握り、フォーマット、および main 統合
（致命的=即通知 / 部分失敗=集約通知）を検証。HTTP 送信はモック。
"""

import json
import os
import urllib.error
from unittest.mock import patch, MagicMock

import pytest

import chat_notifier
from main import app


@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


class TestNotify:
    @patch("chat_notifier.urllib.request.urlopen")
    def test_noop_when_url_unset(self, mock_urlopen):
        """CHAT_WEBHOOK_URL 未設定 → 投稿せず False（no-op）"""
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("CHAT_WEBHOOK_URL", None)
            result = chat_notifier.notify("hello")
        assert result is False
        mock_urlopen.assert_not_called()

    @patch("chat_notifier.urllib.request.urlopen")
    def test_posts_when_url_set(self, mock_urlopen):
        """URL 設定時は webhook へ JSON payload を POST"""
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_urlopen.return_value.__enter__.return_value = mock_resp

        with patch.dict(os.environ, {"CHAT_WEBHOOK_URL": "https://chat.example/post"}):
            result = chat_notifier.notify("hello")

        assert result is True
        mock_urlopen.assert_called_once()
        req = mock_urlopen.call_args.args[0]
        assert req.full_url == "https://chat.example/post"
        assert req.get_method() == "POST"
        body = json.loads(req.data.decode("utf-8"))
        assert body == {"text": "hello"}

    @patch("chat_notifier.urllib.request.urlopen")
    def test_send_failure_is_swallowed(self, mock_urlopen):
        """送信失敗（URLError）でも例外を送出せず False を返す"""
        mock_urlopen.side_effect = urllib.error.URLError("boom")
        with patch.dict(os.environ, {"CHAT_WEBHOOK_URL": "https://chat.example/post"}):
            result = chat_notifier.notify("hello")
        assert result is False

    @patch("chat_notifier.urllib.request.urlopen")
    def test_noop_when_url_blank(self, mock_urlopen):
        """空白のみの URL も no-op（strip 後に空）"""
        with patch.dict(os.environ, {"CHAT_WEBHOOK_URL": "   "}):
            result = chat_notifier.notify("hello")
        assert result is False
        mock_urlopen.assert_not_called()

    @patch("chat_notifier.urllib.request.urlopen")
    def test_send_failure_does_not_log_url(self, mock_urlopen, caplog):
        """送信失敗ログに webhook URL（key/token）が漏れない（例外型名のみ）"""
        secret_url = "https://chat.example/post?key=KEY_LEAK&token=TOKEN_LEAK"
        # URL 全体を含む例外（Request 構築失敗の ValueError 等を模す）
        mock_urlopen.side_effect = ValueError(f"unknown url type: {secret_url}")
        with patch.dict(os.environ, {"CHAT_WEBHOOK_URL": secret_url}):
            with caplog.at_level("ERROR"):
                result = chat_notifier.notify("hi")
        assert result is False
        # ログに key/token が漏れていないこと
        assert "KEY_LEAK" not in caplog.text
        assert "TOKEN_LEAK" not in caplog.text
        assert "ValueError" in caplog.text  # 例外型名は記録される


class TestFormat:
    def test_format_failures(self):
        text = chat_notifier.format_failures(
            "毎朝バッチ POST /",
            [("Step6 立替金", "HttpError: denied"), ("Step0 snapshot", "check_logs 失敗")],
        )
        assert "(2件)" in text
        assert "Step6 立替金" in text
        assert "HttpError: denied" in text
        assert "毎朝バッチ POST /" in text
        assert "JST" in text  # 発生時刻フィールド
        assert chat_notifier.SYSTEM_NAME in text  # 正式システム名称
        assert "データ収集バッチ" in text  # 発生元コンポーネント

    def test_format_fatal(self):
        with patch.dict(os.environ, {"K_REVISION": "pay-collector-test"}):
            text = chat_notifier.format_fatal("POST /", RuntimeError("boom"))
        assert "RuntimeError" in text
        assert "boom" in text
        assert "致命的" in text
        # AC2 の必須フィールド（時刻・リビジョン・発生元）を保護
        assert "JST" in text
        assert "pay-collector-test" in text
        assert "POST /" in text
        assert chat_notifier.SYSTEM_NAME in text  # 正式システム名称

    def test_notify_failures_empty_is_noop(self):
        """部分失敗が空なら通知しない"""
        with patch("chat_notifier.notify") as mock_notify:
            result = chat_notifier.notify_failures("ctx", [])
        assert result is False
        mock_notify.assert_not_called()

    def test_notify_failures_swallows_formatter_error(self):
        """format_failures が例外でも notify_failures は波及させず False"""
        with patch("chat_notifier.format_failures", side_effect=RuntimeError("fmt boom")):
            result = chat_notifier.notify_failures("ctx", [("s", "d")])
        assert result is False

    def test_notify_fatal_swallows_formatter_error(self):
        """format_fatal が例外でも notify_fatal は波及させず False"""
        with patch("chat_notifier.format_fatal", side_effect=RuntimeError("fmt boom")):
            result = chat_notifier.notify_fatal("ctx", RuntimeError("x"))
        assert result is False


class TestMainIntegration:
    """main の致命的=即通知 / 部分失敗=集約通知"""

    @patch("main.chat_notifier")
    @patch("main.bq_loader")
    @patch("main.sheets_collector")
    def test_fatal_triggers_notify_fatal(self, mock_sheets, mock_bq, mock_notifier, client):
        """致命的エラー(500)時に notify_fatal が呼ばれる"""
        mock_bq.create_snapshots.return_value = {"dashboard_users": 1}
        mock_sheets.run_collection.side_effect = RuntimeError("collection boom")

        response = client.post("/")

        assert response.status_code == 500
        mock_notifier.notify_fatal.assert_called_once()
        assert mock_notifier.notify_fatal.call_args.args[0] == "毎朝バッチ POST /"

    @patch("main.chat_notifier")
    @patch("main.bq_loader")
    @patch("main.sheets_collector")
    def test_partial_failures_aggregated(self, mock_sheets, mock_bq, mock_notifier, client):
        """部分失敗(Step6例外 + Step0 snapshot -1)が集約1通知にまとまる"""
        mock_bq.create_snapshots.return_value = {"dashboard_users": 1, "check_logs": -1}
        mock_sheets.run_collection.return_value = {"gyomu_reports": [["r"]]}
        mock_bq.load_all.return_value = {"gyomu_reports": 1}
        mock_sheets.update_member_groups_from_bq.return_value = (
            [["m1"]],
            [["g@x.com", "G"]],
        )
        mock_bq.load_to_bigquery.return_value = 1
        mock_bq.config.BQ_TABLE_MEMBERS = "members"
        mock_bq.config.BQ_TABLE_GROUPS_MASTER = "groups_master"
        mock_bq.config.BQ_TABLE_MEMBER_MASTER = "member_master"
        mock_bq.read_group_based_users.return_value = {}
        # Step6 で例外 → 部分失敗
        mock_sheets.run_reimbursement_collection.side_effect = RuntimeError("reimb boom")
        mock_sheets._build_sheets_service.return_value = MagicMock()
        mock_sheets.collect_member_master.return_value = [["m"]]

        response = client.post("/")

        assert response.status_code == 200  # 部分失敗は本体成功扱い
        mock_notifier.notify_failures.assert_called_once()
        ctx, failures = mock_notifier.notify_failures.call_args.args
        assert ctx == "毎朝バッチ POST /"
        assert len(failures) == 2  # Step6 立替金 + Step0 snapshot(check_logs) の2件のみ
        steps = [f[0] for f in failures]
        assert "Step6 立替金" in steps
        assert "Step0 snapshot" in steps  # check_logs の -1

    @patch("main.chat_notifier")
    @patch("main.bq_loader")
    @patch("main.sheets_collector")
    def test_no_failure_no_notify(self, mock_sheets, mock_bq, mock_notifier, client):
        """全 Step 成功時は notify_failures が呼ばれても空リスト（通知されない）"""
        mock_bq.create_snapshots.return_value = {"dashboard_users": 1}
        mock_sheets.run_collection.return_value = {"gyomu_reports": [["r"]]}
        mock_bq.load_all.return_value = {"gyomu_reports": 1}
        mock_sheets.update_member_groups_from_bq.return_value = (
            [["m1"]],
            [["g@x.com", "G"]],
        )
        mock_bq.load_to_bigquery.return_value = 1
        mock_bq.config.BQ_TABLE_MEMBERS = "members"
        mock_bq.config.BQ_TABLE_GROUPS_MASTER = "groups_master"
        mock_bq.config.BQ_TABLE_MEMBER_MASTER = "member_master"
        mock_bq.read_group_based_users.return_value = {}
        mock_sheets.run_reimbursement_collection.return_value = {
            "reimbursement_items": [["r"]]
        }
        mock_sheets._build_sheets_service.return_value = MagicMock()
        mock_sheets.collect_member_master.return_value = [["m"]]

        response = client.post("/")

        assert response.status_code == 200
        # 集約通知は呼ばれるが、渡される失敗リストは空
        ctx, failures = mock_notifier.notify_failures.call_args.args
        assert failures == []

    @patch("main.chat_notifier")
    @patch("main.sheets_collector")
    def test_sync_endpoint_fatal_triggers_notify(self, mock_sheets, mock_notifier, client):
        """手動同期エンドポイントの致命的エラーでも notify_fatal が呼ばれる"""
        mock_sheets.run_reimbursement_collection.side_effect = RuntimeError("boom")

        response = client.post("/sync/reimbursement")

        assert response.status_code == 500
        mock_notifier.notify_fatal.assert_called_once()
        assert mock_notifier.notify_fatal.call_args.args[0] == "POST /sync/reimbursement"

    @patch("main.chat_notifier")
    @patch("main.bq_loader")
    @patch("main.sheets_collector")
    def test_update_groups_fatal_notify(self, mock_sheets, mock_bq, mock_notifier, client):
        """/update-groups の致命的エラーで notify_fatal が呼ばれる"""
        mock_sheets.update_member_groups_from_bq.side_effect = RuntimeError("boom")

        response = client.post("/update-groups")

        assert response.status_code == 500
        mock_notifier.notify_fatal.assert_called_once()
        assert mock_notifier.notify_fatal.call_args.args[0] == "POST /update-groups"

    @patch("main.chat_notifier")
    @patch("main.bq_loader")
    @patch("main.sheets_collector")
    def test_sync_main_reports_fatal_notify(self, mock_sheets, mock_bq, mock_notifier, client):
        """/sync/main-reports の致命的エラーで notify_fatal が呼ばれる"""
        mock_sheets.run_collection.side_effect = RuntimeError("boom")

        response = client.post("/sync/main-reports")

        assert response.status_code == 500
        mock_notifier.notify_fatal.assert_called_once()
        assert mock_notifier.notify_fatal.call_args.args[0] == "POST /sync/main-reports"

    @patch("main.chat_notifier")
    @patch("main.sheets_collector")
    def test_sync_member_master_fatal_notify(self, mock_sheets, mock_notifier, client):
        """/sync/member-master の致命的エラーで notify_fatal が呼ばれる"""
        mock_sheets._build_sheets_service.side_effect = RuntimeError("boom")

        response = client.post("/sync/member-master")

        assert response.status_code == 500
        mock_notifier.notify_fatal.assert_called_once()
        assert mock_notifier.notify_fatal.call_args.args[0] == "POST /sync/member-master"

    @patch("main.chat_notifier")
    @patch("main.bq_loader")
    @patch("main.sheets_collector")
    def test_update_groups_partial_sync_failure_notifies(
        self, mock_sheets, mock_bq, mock_notifier, client
    ):
        """/update-groups の内側 dashboard_users 同期失敗(部分失敗)も集約通知される"""
        mock_sheets.update_member_groups_from_bq.return_value = (
            [["m1"]],
            [["g@x.com", "G"]],
        )
        mock_bq.load_to_bigquery.return_value = 1
        mock_bq.config.BQ_TABLE_MEMBERS = "members"
        mock_bq.config.BQ_TABLE_GROUPS_MASTER = "groups_master"
        mock_bq.read_group_based_users.return_value = {"g@x.com": []}  # truthy → 同期試行
        # 同期の内側で例外 → except sync_err で握り 200、ただし通知
        mock_sheets._build_admin_service.side_effect = RuntimeError("sync boom")

        response = client.post("/update-groups")

        assert response.status_code == 200  # 内側部分失敗は握って本体成功扱い
        mock_notifier.notify_failures.assert_called_once()
        ctx, failures = mock_notifier.notify_failures.call_args.args
        assert ctx == "POST /update-groups"
        assert len(failures) == 1
        assert failures[0][0] == "dashboard_users同期"
