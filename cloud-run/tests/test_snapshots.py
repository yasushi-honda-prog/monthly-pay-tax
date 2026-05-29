"""snapshot バックアップ（Step8）のユニットテスト

bq_loader.create_snapshots の正常系・SQL内容・部分失敗系、および
main の Step8 が失敗してもバッチ本体は成功扱い(200)になることを検証。
GCP アクセスはモック。
"""

import pytest
from unittest.mock import patch, MagicMock

import bq_loader
import config
from main import app


@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


class TestCreateSnapshots:
    """bq_loader.create_snapshots 単体"""

    @patch("bq_loader._build_bq_client")
    def test_all_tables_success(self, mock_build_client):
        mock_client = MagicMock()
        mock_build_client.return_value = mock_client

        result = bq_loader.create_snapshots("20260529")

        # 対象5テーブル全て成功（1）
        assert result == {t: 1 for t in config.BQ_SNAPSHOT_TABLES}
        # query が対象テーブル数だけ呼ばれ、各 .result() で完了待機
        assert mock_client.query.call_count == len(config.BQ_SNAPSHOT_TABLES)
        assert mock_client.query.return_value.result.call_count == len(
            config.BQ_SNAPSHOT_TABLES
        )

    @patch("bq_loader._build_bq_client")
    def test_sql_content(self, mock_build_client):
        """発行SQLが CREATE SNAPSHOT / CLONE / expiration / 正しいテーブル名・日付を含む"""
        mock_client = MagicMock()
        mock_build_client.return_value = mock_client

        bq_loader.create_snapshots("20260529")

        first_table = config.BQ_SNAPSHOT_TABLES[0]
        sql = mock_client.query.call_args_list[0].args[0]
        assert "CREATE SNAPSHOT TABLE IF NOT EXISTS" in sql
        assert (
            f"{config.BQ_BACKUP_DATASET}.{first_table}_20260529" in sql
        ), "別データセット + テーブル名 + 日付サフィックスが正しいこと"
        assert (
            f"CLONE `{config.GCP_PROJECT_ID}.{config.BQ_DATASET}.{first_table}`"
            in sql
        ), "CLONE元が本番データセットの当該テーブルであること"
        assert f"INTERVAL {config.BQ_SNAPSHOT_EXPIRATION_DAYS} DAY" in sql, (
            "expiration が config の保持日数であること"
        )

    @patch("bq_loader._build_bq_client")
    def test_partial_failure_continues(self, mock_build_client):
        """1テーブルの作成が失敗しても残りのテーブルは継続する（部分失敗許容）"""
        mock_client = MagicMock()
        mock_build_client.return_value = mock_client

        failing_table = config.BQ_SNAPSHOT_TABLES[1]

        def query_side_effect(sql):
            if f".{failing_table}_20260529" in sql:
                raise RuntimeError("snapshot boom")
            return MagicMock()

        mock_client.query.side_effect = query_side_effect

        result = bq_loader.create_snapshots("20260529")

        # 失敗テーブルは -1、他は 1、全テーブルが試行される
        assert result[failing_table] == -1
        assert mock_client.query.call_count == len(config.BQ_SNAPSHOT_TABLES)
        success = [t for t, v in result.items() if v == 1]
        assert len(success) == len(config.BQ_SNAPSHOT_TABLES) - 1

    @patch("bq_loader._build_bq_client")
    def test_target_tables_are_bq_only_source(self, mock_build_client):
        """snapshot対象がBQ唯一ソース5テーブルに限定されている（再生成可能テーブルは含めない）"""
        mock_client = MagicMock()
        mock_build_client.return_value = mock_client

        bq_loader.create_snapshots("20260529")

        snapshotted = set(config.BQ_SNAPSHOT_TABLES)
        assert snapshotted == {
            config.BQ_TABLE_DASHBOARD_USERS,
            config.BQ_TABLE_SYNC_GROUPS,
            config.BQ_TABLE_CHECK_LOGS,
            config.BQ_TABLE_WAM_PROJECTS,
            config.BQ_TABLE_WITHHOLDING,
        }
        # 毎朝WRITE_TRUNCATEで再生成されるテーブルは対象外
        assert config.BQ_TABLE_GYOMU not in snapshotted
        assert config.BQ_TABLE_HOJO not in snapshotted
        assert config.BQ_TABLE_MEMBER_MASTER not in snapshotted

    @patch("bq_loader._build_bq_client")
    def test_all_tables_fail(self, mock_build_client):
        """全テーブルの作成が失敗しても全件 -1 でサマリーに残る（沈黙しない）"""
        mock_client = MagicMock()
        mock_build_client.return_value = mock_client
        mock_client.query.side_effect = RuntimeError("all down")

        result = bq_loader.create_snapshots("20260529")

        assert result == {t: -1 for t in config.BQ_SNAPSHOT_TABLES}
        assert mock_client.query.call_count == len(config.BQ_SNAPSHOT_TABLES)

    @patch("bq_loader._build_bq_client")
    def test_result_failure_recorded(self, mock_build_client):
        """query() は成功するが .result() で BQ ジョブ実行時エラー → -1 で記録"""
        mock_client = MagicMock()
        mock_build_client.return_value = mock_client
        # query() 自体は返るが、ジョブ完了待ち .result() で例外
        mock_client.query.return_value.result.side_effect = RuntimeError("job failed")

        result = bq_loader.create_snapshots("20260529")

        assert result == {t: -1 for t in config.BQ_SNAPSHOT_TABLES}


class TestStep8Integration:
    """main の Step8 統合（バッチ POST /）"""

    @patch("main.bq_loader")
    @patch("main.sheets_collector")
    def test_snapshot_failure_does_not_fail_batch(self, mock_sheets, mock_bq, client):
        """Step8 snapshot が例外でもバッチ本体は成功扱い(200)"""
        # Step 1-3
        mock_sheets.run_collection.return_value = {"gyomu_reports": [["r1"]]}
        mock_bq.load_all.return_value = {"gyomu_reports": 1}
        # Step 4
        mock_sheets.update_member_groups_from_bq.return_value = (
            [["m1"]],
            [["g@x.com", "G"]],
        )
        mock_bq.load_to_bigquery.return_value = 1
        # results の dict キーになる定数は文字列で固定（MagicMock だと jsonify が落ちる）
        mock_bq.config.BQ_TABLE_MEMBERS = "members"
        mock_bq.config.BQ_TABLE_GROUPS_MASTER = "groups_master"
        mock_bq.config.BQ_TABLE_MEMBER_MASTER = "member_master"
        # Step 5: 対象グループなしで簡潔に通す
        mock_bq.read_group_based_users.return_value = {}
        # Step 6
        mock_sheets.run_reimbursement_collection.return_value = {
            "reimbursement_items": [["r"]]
        }
        # Step 7
        mock_sheets._build_sheets_service.return_value = MagicMock()
        mock_sheets.collect_member_master.return_value = [["m"]]
        # Step 8: snapshot だけ失敗させる
        mock_bq.create_snapshots.side_effect = RuntimeError("snapshot down")

        response = client.post("/")

        assert response.status_code == 200
        assert response.get_json()["status"] == "success"
        mock_bq.create_snapshots.assert_called_once()

    @patch("main.bq_loader")
    @patch("main.sheets_collector")
    def test_snapshot_results_in_summary(self, mock_sheets, mock_bq, client):
        """成功時は snapshot 結果がサマリーに含まれる"""
        mock_sheets.run_collection.return_value = {"gyomu_reports": [["r1"]]}
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
        mock_bq.create_snapshots.return_value = {"dashboard_users": 1}

        response = client.post("/")

        assert response.status_code == 200
        payload = response.get_json()
        assert payload["tables"]["snapshots"] == {"dashboard_users": 1}

    @patch("main.bq_loader")
    @patch("main.sheets_collector")
    def test_snapshot_runs_before_collection(self, mock_sheets, mock_bq, client):
        """snapshot(Step0)はデータ収集(Step1)より前に実行される=更新前バックアップ"""
        call_order = []
        mock_bq.create_snapshots.side_effect = (
            lambda d: call_order.append("snapshot") or {"dashboard_users": 1}
        )
        mock_sheets.run_collection.side_effect = (
            lambda: call_order.append("collection") or {"gyomu_reports": [["r"]]}
        )
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
        # snapshot が最初に実行され、データ収集より前であること
        assert call_order[0] == "snapshot"
        assert call_order.index("snapshot") < call_order.index("collection")
