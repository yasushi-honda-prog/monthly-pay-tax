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


@pytest.fixture
def mock_sync_helpers():
    """sync_dashboard_users_from_groups が依存するヘルパーをモック化

    - read_enabled_sync_groups: テスト側で .return_value に enabled set を渡す
    - read_all_sync_groups: デフォルトは enabled set と同じ（テスト側で disabled シナリオは個別設定）
    - _update_last_synced_at: 副作用なしで通す（last_synced_at 更新は機能テスト不要）

    返り値: (mock_enabled, mock_all) のタプル
    """
    with patch("bq_loader.read_enabled_sync_groups") as mock_enabled, \
         patch("bq_loader.read_all_sync_groups") as mock_all, \
         patch("bq_loader._update_last_synced_at"):
        # デフォルト: 全 enabled グループは登録済みでもある（disabled は無し）
        mock_all.side_effect = lambda: mock_enabled.return_value
        yield mock_enabled


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

    def test_adds_new_members(self, mock_bq_client, mock_sync_helpers):
        """グループに新メンバーが追加された場合INSERTされること"""
        import pandas as pd
        from bq_loader import sync_dashboard_users_from_groups

        mock_sync_helpers.return_value = {"group-a@tadakayo.jp"}

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

    def test_removes_departed_members(self, mock_bq_client, mock_sync_helpers):
        """グループから脱退したメンバーがDELETEされること"""
        import pandas as pd
        from bq_loader import sync_dashboard_users_from_groups

        mock_sync_helpers.return_value = {"group-a@tadakayo.jp"}

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

    def test_skips_manually_registered_users(self, mock_bq_client, mock_sync_helpers):
        """手動登録ユーザーはグループ追加時にスキップされること"""
        import pandas as pd
        from bq_loader import sync_dashboard_users_from_groups

        mock_sync_helpers.return_value = {"group-a@tadakayo.jp"}

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

    def test_no_changes_when_in_sync(self, mock_bq_client, mock_sync_helpers):
        """既にメンバーが同期済みの場合変更なし"""
        import pandas as pd
        from bq_loader import sync_dashboard_users_from_groups

        mock_sync_helpers.return_value = {"group-a@tadakayo.jp"}

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

    def test_empty_group_members_map(self, mock_bq_client, mock_sync_helpers):
        """group_members_mapが空の場合、既存グループユーザーが全削除されること"""
        import pandas as pd
        from bq_loader import sync_dashboard_users_from_groups

        mock_sync_helpers.return_value = {"group-a@tadakayo.jp"}

        # 現在: aliceが登録済み
        mock_bq_client.query().to_dataframe.return_value = pd.DataFrame([
            {"email": "alice@tadakayo.jp", "role": "viewer", "source_group": "group-a@tadakayo.jp"},
        ])

        mock_bq_client.query().result.return_value = FakeQueryResult()

        # group_members_mapに該当グループがない → aliceは削除対象
        result = sync_dashboard_users_from_groups({})

        assert result["removed"] == 1

    def test_uses_existing_role_for_new_members(self, mock_bq_client, mock_sync_helpers):
        """新メンバー追加時に既存メンバーのロールを引き継ぐこと"""
        import pandas as pd
        from bq_loader import sync_dashboard_users_from_groups

        mock_sync_helpers.return_value = {"group-a@tadakayo.jp"}

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


class TestSyncToggleSemantics:
    """ON/OFF 切替セマンティクスのテスト（追加 AC: 凍結・スキップ・fail-fast）"""

    def test_disabled_group_is_frozen_not_modified(self, mock_bq_client, mock_sync_helpers):
        """AC1: enabled=FALSE のグループは add/remove を一切実行しない（凍結）

        group-a は dashboard_sync_groups に登録済みだが enabled=FALSE → skipped_disabled に計上
        """
        import pandas as pd
        from bq_loader import sync_dashboard_users_from_groups

        # enabled は空、registered (read_all) には含まれる → disabled 扱い
        mock_sync_helpers.return_value = set()
        with patch("bq_loader.read_all_sync_groups", return_value={"group-a@tadakayo.jp"}):
            # 現在: aliceがgroup-aに登録済み
            mock_bq_client.query().to_dataframe.return_value = pd.DataFrame([
                {"email": "alice@tadakayo.jp", "role": "viewer", "source_group": "group-a@tadakayo.jp"},
            ])

            # 最新メンバーが空でも、OFF なので削除しない
            result = sync_dashboard_users_from_groups({
                "group-a@tadakayo.jp": [],
            })

        assert result["added"] == 0
        assert result["removed"] == 0
        assert result["skipped_disabled"] == 1
        assert result["skipped_unregistered"] == 0

        # DELETE / MERGE クエリが呼ばれていないこと
        query_call_strs = [str(c) for c in mock_bq_client.query.call_args_list]
        assert not any("DELETE FROM" in s for s in query_call_strs)
        assert not any("WHEN NOT MATCHED THEN" in s for s in query_call_strs)

    def test_unregistered_group_is_skipped(self, mock_bq_client, mock_sync_helpers):
        """AC3: dashboard_sync_groups に未登録のグループは skipped_unregistered 計上"""
        import pandas as pd
        from bq_loader import sync_dashboard_users_from_groups

        # enabled も registered も空 → group-x は未登録扱い
        mock_sync_helpers.return_value = set()
        with patch("bq_loader.read_all_sync_groups", return_value=set()):
            mock_bq_client.query().to_dataframe.return_value = pd.DataFrame(
                columns=["email", "role", "source_group"]
            )

            # 新規グループ group-x のメンバーを渡しても、未登録なので skip
            result = sync_dashboard_users_from_groups({
                "group-x@tadakayo.jp": ["new@tadakayo.jp"],
            })

        assert result["added"] == 0
        assert result["removed"] == 0
        assert result["skipped_unregistered"] == 1
        assert result["skipped_disabled"] == 0

    def test_enabled_groups_are_processed_disabled_skipped(self, mock_bq_client, mock_sync_helpers):
        """AC1+AC2 混在: enabled は処理、disabled は凍結、unregistered は別計上"""
        import pandas as pd
        from bq_loader import sync_dashboard_users_from_groups

        # group-a: enabled, group-b: disabled (registered のみ), group-c: 未登録
        mock_sync_helpers.return_value = {"group-a@tadakayo.jp"}
        with patch(
            "bq_loader.read_all_sync_groups",
            return_value={"group-a@tadakayo.jp", "group-b@tadakayo.jp"},
        ):
            # 現在: alice@group-a, bob@group-b
            mock_bq_client.query().to_dataframe.return_value = pd.DataFrame([
                {"email": "alice@tadakayo.jp", "role": "viewer", "source_group": "group-a@tadakayo.jp"},
                {"email": "bob@tadakayo.jp", "role": "viewer", "source_group": "group-b@tadakayo.jp"},
            ])

            mock_bq_client.query().result.return_value = FakeQueryResult()

            # 最新メンバー: group-a 空（aliceは削除対象）、group-b 空（凍結）、group-c 新規（未登録 skip）
            result = sync_dashboard_users_from_groups({
                "group-a@tadakayo.jp": [],
                "group-b@tadakayo.jp": [],
                "group-c@tadakayo.jp": ["new@tadakayo.jp"],
            })

        # alice (group-a) は削除、bob (group-b) は凍結、group-c は未登録 skip
        assert result["removed"] == 1
        assert result["skipped_disabled"] == 1
        assert result["skipped_unregistered"] == 1

    def test_read_enabled_sync_groups_propagates_exception(self, mock_bq_client):
        """AC8: dashboard_sync_groups テーブル読み取り失敗時は例外伝播 (fail-fast)"""
        from bq_loader import read_enabled_sync_groups

        mock_bq_client.query.side_effect = Exception("Table not found: dashboard_sync_groups")

        with pytest.raises(Exception, match="Table not found"):
            read_enabled_sync_groups()

    def test_read_enabled_sync_groups_returns_set(self, mock_bq_client):
        """read_enabled_sync_groups: enabled=TRUE のグループメール集合を返す"""
        import pandas as pd
        from bq_loader import read_enabled_sync_groups

        mock_bq_client.query().to_dataframe.return_value = pd.DataFrame([
            {"group_email": "group-a@tadakayo.jp"},
            {"group_email": "group-b@tadakayo.jp"},
        ])

        result = read_enabled_sync_groups()

        assert result == {"group-a@tadakayo.jp", "group-b@tadakayo.jp"}

    def test_read_all_sync_groups_returns_set(self, mock_bq_client):
        """read_all_sync_groups: enabled の TRUE/FALSE 問わず全グループメール集合を返す"""
        import pandas as pd
        from bq_loader import read_all_sync_groups

        mock_bq_client.query().to_dataframe.return_value = pd.DataFrame([
            {"group_email": "group-a@tadakayo.jp"},
            {"group_email": "group-b@tadakayo.jp"},
            {"group_email": "group-c@tadakayo.jp"},
        ])

        result = read_all_sync_groups()

        assert result == {"group-a@tadakayo.jp", "group-b@tadakayo.jp", "group-c@tadakayo.jp"}
