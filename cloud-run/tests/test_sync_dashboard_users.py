"""sync_dashboard_users_from_groups のユニットテスト

グループベースのdashboard_users同期ロジックを検証。
- 追加: グループに新メンバー → INSERT
- 削除: グループから脱退 → DELETE
- 手動登録ユーザーの不可侵
- 既存ユーザーのスキップ
"""

from unittest.mock import MagicMock, patch, call

import pytest


class FakeQueryResult:
    """BQ query().result() のモック"""

    def __init__(self, num_dml_affected_rows=0, rows=None):
        self.num_dml_affected_rows = num_dml_affected_rows
        self._rows = rows or []

    def __iter__(self):
        return iter(self._rows)

    def __next__(self):
        return next(iter(self._rows))

    def result(self):
        return self


class FakeRow:
    """BQ行のモック"""

    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)


@pytest.fixture
def mock_bq_client():
    with patch("bq_loader._build_bq_client") as mock_build:
        client = MagicMock()
        mock_build.return_value = client
        yield client


class TestReadGroupBasedUsers:
    """read_group_based_users のテスト"""

    def test_returns_grouped_users(self, mock_bq_client):
        """グループごとにユーザーをまとめて返すこと"""
        import pandas as pd
        from bq_loader import read_group_based_users

        mock_bq_client.query().to_dataframe.return_value = pd.DataFrame([
            {"email": "alice@tadakayo.jp", "role": "viewer", "source_group": "group-a@tadakayo.jp"},
            {"email": "bob@tadakayo.jp", "role": "viewer", "source_group": "group-a@tadakayo.jp"},
            {"email": "carol@tadakayo.jp", "role": "checker", "source_group": "group-b@tadakayo.jp"},
        ])

        result = read_group_based_users()

        assert len(result) == 2
        assert len(result["group-a@tadakayo.jp"]) == 2
        assert len(result["group-b@tadakayo.jp"]) == 1

    def test_returns_empty_when_no_group_users(self, mock_bq_client):
        """グループ由来ユーザーがない場合空dictを返すこと"""
        import pandas as pd
        from bq_loader import read_group_based_users

        mock_bq_client.query().to_dataframe.return_value = pd.DataFrame(
            columns=["email", "role", "source_group"]
        )

        result = read_group_based_users()

        assert result == {}


class TestSyncDashboardUsersFromGroups:
    """sync_dashboard_users_from_groups のテスト"""

    def test_adds_new_members(self, mock_bq_client):
        """グループに新メンバーが追加された場合INSERTされること"""
        import pandas as pd
        from bq_loader import sync_dashboard_users_from_groups

        # read_group_based_users: 現在のグループ由来ユーザー（空）
        mock_bq_client.query().to_dataframe.return_value = pd.DataFrame(
            columns=["email", "role", "source_group"]
        )

        # 手動登録チェック: 該当なし、MERGE: 1行追加
        query_results = [
            FakeQueryResult(rows=[FakeRow(cnt=0)]),  # check: not manually registered
            FakeQueryResult(num_dml_affected_rows=1),  # merge: inserted
        ]
        result_iter = iter(query_results)
        mock_bq_client.query().result.side_effect = lambda: next(result_iter)

        result = sync_dashboard_users_from_groups({
            "group-a@tadakayo.jp": ["alice@tadakayo.jp"],
        })

        assert result["added"] == 1
        assert result["removed"] == 0

    def test_removes_departed_members(self, mock_bq_client):
        """グループから脱退したメンバーがDELETEされること"""
        import pandas as pd
        from bq_loader import sync_dashboard_users_from_groups

        # 現在: aliceがgroup-aに登録済み
        mock_bq_client.query().to_dataframe.return_value = pd.DataFrame([
            {"email": "alice@tadakayo.jp", "role": "viewer", "source_group": "group-a@tadakayo.jp"},
        ])

        # DELETE result
        mock_bq_client.query().result.return_value = FakeQueryResult()

        # 最新グループメンバー: 空（aliceが脱退）
        result = sync_dashboard_users_from_groups({
            "group-a@tadakayo.jp": [],
        })

        assert result["removed"] == 1
        assert result["added"] == 0

    def test_skips_manually_registered_users(self, mock_bq_client):
        """手動登録ユーザーはグループ追加時にスキップされること"""
        import pandas as pd
        from bq_loader import sync_dashboard_users_from_groups

        # read_group_based_users: グループ由来ユーザーなし
        mock_bq_client.query().to_dataframe.return_value = pd.DataFrame(
            columns=["email", "role", "source_group"]
        )

        # 手動登録チェック: alice は手動登録済み (cnt=1)
        mock_bq_client.query().result.side_effect = [
            FakeQueryResult(rows=[FakeRow(cnt=1)]),  # manually registered → skip
        ]

        result = sync_dashboard_users_from_groups({
            "group-a@tadakayo.jp": ["alice@tadakayo.jp"],
        })

        assert result["added"] == 0
        assert result["removed"] == 0

    def test_no_changes_when_in_sync(self, mock_bq_client):
        """既にメンバーが同期済みの場合変更なし"""
        import pandas as pd
        from bq_loader import sync_dashboard_users_from_groups

        # 現在: aliceがgroup-aに登録済み
        mock_bq_client.query().to_dataframe.return_value = pd.DataFrame([
            {"email": "alice@tadakayo.jp", "role": "viewer", "source_group": "group-a@tadakayo.jp"},
        ])

        # 最新: aliceがgroup-aに所属（変更なし）
        result = sync_dashboard_users_from_groups({
            "group-a@tadakayo.jp": ["alice@tadakayo.jp"],
        })

        assert result["added"] == 0
        assert result["removed"] == 0

    def test_empty_group_members_map(self, mock_bq_client):
        """group_members_mapが空の場合、既存グループユーザーが全削除されること"""
        import pandas as pd
        from bq_loader import sync_dashboard_users_from_groups

        # 現在: aliceが登録済み
        mock_bq_client.query().to_dataframe.return_value = pd.DataFrame([
            {"email": "alice@tadakayo.jp", "role": "viewer", "source_group": "group-a@tadakayo.jp"},
        ])

        mock_bq_client.query().result.return_value = FakeQueryResult()

        # group_members_mapに該当グループがない → aliceは削除対象
        result = sync_dashboard_users_from_groups({})

        assert result["removed"] == 1

    def test_uses_existing_role_for_new_members(self, mock_bq_client):
        """新メンバー追加時に既存メンバーのロールを引き継ぐこと"""
        import pandas as pd
        from bq_loader import sync_dashboard_users_from_groups

        # 現在: aliceがcheckerとして登録済み
        mock_bq_client.query().to_dataframe.return_value = pd.DataFrame([
            {"email": "alice@tadakayo.jp", "role": "checker", "source_group": "group-a@tadakayo.jp"},
        ])

        # bobを追加: 手動登録なし → MERGE
        query_results = [
            FakeQueryResult(rows=[FakeRow(cnt=0)]),  # not manually registered
            FakeQueryResult(num_dml_affected_rows=1),  # inserted
        ]
        result_iter = iter(query_results)
        mock_bq_client.query().result.side_effect = lambda: next(result_iter)

        result = sync_dashboard_users_from_groups({
            "group-a@tadakayo.jp": ["alice@tadakayo.jp", "bob@tadakayo.jp"],
        })

        assert result["added"] == 1

        # MERGEクエリに渡されたロールを検証
        query_calls = mock_bq_client.query.call_args_list
        # MERGEクエリのパラメータにcheckerが含まれていること
        merge_calls = [c for c in query_calls if "MERGE" in str(c)]
        assert len(merge_calls) > 0
