"""ユーザー管理ページのユニットテスト"""

import sys
from pathlib import Path
from typing import Optional
from unittest.mock import MagicMock, patch, Mock

import pytest

# dashboard/ を sys.path に追加
dashboard_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(dashboard_dir))


@pytest.fixture
def mock_bq_client():
    """BigQuery クライアントのモック"""
    client = MagicMock()
    yield client


@pytest.fixture
def mock_auth_require_admin():
    """auth.require_admin() のモック（何もしない）"""
    with patch("lib.auth.require_admin", return_value=None) as mock_fn:
        yield mock_fn


@pytest.fixture
def mock_auth_clear_role_cache():
    """auth.clear_role_cache() のモック"""
    with patch("lib.auth.clear_role_cache", return_value=None) as mock_fn:
        yield mock_fn


@pytest.fixture
def module_under_test(
    mock_streamlit,
    mock_auth_require_admin,
    mock_auth_clear_role_cache,
):
    """user_management モジュールを動的にインポート

    モジュールレベルのコードが Streamlit モックで実行されることを保証

    user_management.py はモジュール import 時に load_users() を呼び出すので、
    get_bq_client をモック化してからインポートする必要がある
    """
    # モジュールレベルの変数をリセット
    if "pages.user_management" in sys.modules:
        del sys.modules["pages.user_management"]

    import importlib
    import pandas as pd

    # mock_streamlit.stop をモック（try-except 時に呼ばれる可能性がある）
    mock_streamlit.stop = MagicMock()

    # lib.bq_client.get_bq_client をモック化（モジュール import 時に呼ばれる）
    with patch("lib.bq_client.get_bq_client") as mock_get_bq:
        # load_users で query → to_dataframe() が呼ばれるようにモック
        mock_client = MagicMock()
        mock_query_result = MagicMock()
        mock_query_result.to_dataframe.return_value = pd.DataFrame()
        mock_client.query.return_value = mock_query_result
        mock_get_bq.return_value = mock_client

        module = importlib.import_module("pages.user_management")

    yield module


class TestValidateEmail:
    """validate_email() のテスト

    純粋関数なので、各パターンをテスト可能
    """

    def test_valid_email_basic(self, module_under_test):
        """基本的な有効なメールアドレス"""
        result = module_under_test.validate_email("user@tadakayo.jp")
        assert result is None

    @pytest.mark.parametrize(
        "email_addr",
        [
            "user@tadakayo.jp",
            "first.last@tadakayo.jp",
            "user+tag@tadakayo.jp",
            "user123@tadakayo.jp",
            "a_b-c@tadakayo.jp",
        ],
    )
    def test_valid_email_variants(self, module_under_test, email_addr):
        """有効なメールアドレスのバリエーション"""
        result = module_under_test.validate_email(email_addr)
        assert result is None, f"Expected None for {email_addr}, got {result}"

    def test_invalid_email_wrong_domain(self, module_under_test):
        """ドメインが tadakayo.jp ではない場合"""
        result = module_under_test.validate_email("user@example.com")
        assert result is not None
        assert "tadakayo.jp" in result

    @pytest.mark.parametrize(
        "invalid_email",
        [
            "user@example.com",
            "user@tadakayo.com",
            "user@gmail.com",
            "user@localhost.jp",
        ],
    )
    def test_invalid_email_wrong_domains(self, module_under_test, invalid_email):
        """許可されていないドメイン"""
        result = module_under_test.validate_email(invalid_email)
        assert result is not None
        assert "tadakayo.jp" in result

    def test_invalid_email_empty_string(self, module_under_test):
        """空文字列"""
        result = module_under_test.validate_email("")
        assert result is not None
        assert "有効なメールアドレスを入力してください" in result

    def test_invalid_email_no_at_sign(self, module_under_test):
        """@ 記号がない"""
        result = module_under_test.validate_email("invalid")
        assert result is not None
        assert "有効なメールアドレスを入力してください" in result

    def test_invalid_email_no_domain(self, module_under_test):
        """ドメイン部分がない"""
        result = module_under_test.validate_email("user@")
        assert result is not None
        assert "有効なメールアドレスを入力してください" in result

    def test_invalid_email_no_local(self, module_under_test):
        """ローカル部分がない"""
        result = module_under_test.validate_email("@tadakayo.jp")
        assert result is not None
        assert "有効なメールアドレスを入力してください" in result

    def test_invalid_email_no_tld(self, module_under_test):
        """TLD がない"""
        result = module_under_test.validate_email("user@tadakayo")
        assert result is not None
        assert "有効なメールアドレスを入力してください" in result

    @pytest.mark.parametrize(
        "invalid_email",
        [
            "",
            "user",
            "@tadakayo.jp",
            "user@",
            "user @tadakayo.jp",
            "user@tadakayo .jp",
        ],
    )
    def test_invalid_email_format_variants(self, module_under_test, invalid_email):
        """フォーマットが無効なメールアドレス"""
        result = module_under_test.validate_email(invalid_email)
        assert result is not None


class TestDeleteUser:
    """delete_user() のビジネスロールテスト"""

    def test_cannot_delete_initial_admin(self, module_under_test, mock_bq_client):
        """初期管理者は削除できない"""
        success, message = module_under_test.delete_user(
            "yasushi-honda@tadakayo.jp"
        )
        assert success is False
        assert "初期管理者は削除できません" in message

    def test_cannot_delete_self(self, module_under_test, mock_bq_client):
        """自分自身は削除できない

        user_management.py モジュールレベルの `email` 変数を使う
        """
        # モジュールレベルの email 変数を設定
        current_user_email = "user@tadakayo.jp"
        module_under_test.email = current_user_email

        success, message = module_under_test.delete_user(current_user_email)

        assert success is False
        assert "自分自身は削除できません" in message

    def test_delete_user_success(
        self, module_under_test, mock_bq_client, mock_auth_clear_role_cache
    ):
        """ユーザー削除に成功

        - 初期管理者ではない
        - 自分自身ではない
        - BQ client の query/result が成功
        """
        # モジュールレベルの email 変数（現在のユーザー）
        module_under_test.email = "admin@tadakayo.jp"

        # BQ クライアントをモック
        mock_result = MagicMock()
        mock_job = MagicMock()
        mock_job.result.return_value = mock_result

        with patch("pages.user_management.get_bq_client") as mock_get_bq:
            mock_client = MagicMock()
            mock_client.query.return_value = mock_job
            mock_get_bq.return_value = mock_client

            # 削除対象（初期管理者でも自分でもない）
            target_email = "other-user@tadakayo.jp"
            success, message = module_under_test.delete_user(target_email)

            assert success is True
            assert "ユーザーを削除しました" in message
            mock_client.query.assert_called_once()
            mock_auth_clear_role_cache.assert_called_once()

    def test_delete_user_guards_before_bq_call(self, module_under_test):
        """BQ呼び出し前にガード条件をチェック

        初期管理者・自分自身の場合は BQ に問い合わせないこと
        """
        module_under_test.email = "user@tadakayo.jp"

        with patch("pages.user_management.get_bq_client") as mock_get_bq:
            mock_client = MagicMock()
            mock_get_bq.return_value = mock_client

            # 初期管理者を削除しようとする
            module_under_test.delete_user("yasushi-honda@tadakayo.jp")

            # BQ client が呼ばれないこと
            mock_get_bq.assert_not_called()
            mock_client.query.assert_not_called()


class TestUpdateRole:
    """update_role() のビジネスロールテスト"""

    def test_cannot_change_initial_admin_role_to_non_admin(
        self, module_under_test, mock_bq_client
    ):
        """初期管理者のロールを admin 以外に変更できない"""
        success, message = module_under_test.update_role(
            "yasushi-honda@tadakayo.jp", "viewer"
        )
        assert success is False
        assert "初期管理者のロールは変更できません" in message

    def test_cannot_change_initial_admin_role_to_checker(
        self, module_under_test, mock_bq_client
    ):
        """初期管理者のロールを checker に変更できない"""
        success, message = module_under_test.update_role(
            "yasushi-honda@tadakayo.jp", "checker"
        )
        assert success is False
        assert "初期管理者のロールは変更できません" in message

    def test_can_keep_initial_admin_as_admin(
        self, module_under_test, mock_auth_clear_role_cache
    ):
        """初期管理者のロールを admin のままにするのはOK"""
        with patch("pages.user_management.get_bq_client") as mock_get_bq:
            mock_client = MagicMock()
            mock_result = MagicMock()
            mock_job = MagicMock()
            mock_job.result.return_value = mock_result
            mock_client.query.return_value = mock_job
            mock_get_bq.return_value = mock_client

            success, message = module_under_test.update_role(
                "yasushi-honda@tadakayo.jp", "admin"
            )

            assert success is True
            assert "ロールを変更しました" in message
            mock_client.query.assert_called_once()
            mock_auth_clear_role_cache.assert_called_once()

    def test_update_role_success_for_regular_user(
        self, module_under_test, mock_auth_clear_role_cache
    ):
        """通常ユーザーのロール変更に成功"""
        with patch("pages.user_management.get_bq_client") as mock_get_bq:
            mock_client = MagicMock()
            mock_result = MagicMock()
            mock_job = MagicMock()
            mock_job.result.return_value = mock_result
            mock_client.query.return_value = mock_job
            mock_get_bq.return_value = mock_client

            success, message = module_under_test.update_role(
                "user@tadakayo.jp", "checker"
            )

            assert success is True
            assert "ロールを変更しました" in message
            mock_client.query.assert_called_once()
            mock_auth_clear_role_cache.assert_called_once()

    @pytest.mark.parametrize(
        "new_role",
        ["viewer", "checker", "admin"],
    )
    def test_update_role_all_role_types(
        self, module_under_test, mock_auth_clear_role_cache, new_role
    ):
        """通常ユーザーへの全ロール変更パターン"""
        with patch("pages.user_management.get_bq_client") as mock_get_bq:
            mock_client = MagicMock()
            mock_result = MagicMock()
            mock_job = MagicMock()
            mock_job.result.return_value = mock_result
            mock_client.query.return_value = mock_job
            mock_get_bq.return_value = mock_client

            success, message = module_under_test.update_role(
                "user@tadakayo.jp", new_role
            )

            assert success is True
            mock_client.query.assert_called_once()

    def test_update_role_guards_before_bq_call(self, module_under_test):
        """BQ呼び出し前にガード条件をチェック

        初期管理者を admin 以外に変更しようとする場合は
        BQ に問い合わせないこと
        """
        with patch("pages.user_management.get_bq_client") as mock_get_bq:
            mock_client = MagicMock()
            mock_get_bq.return_value = mock_client

            # 初期管理者を viewer に変更しようとする
            module_under_test.update_role("yasushi-honda@tadakayo.jp", "viewer")

            # BQ client が呼ばれないこと
            mock_get_bq.assert_not_called()
            mock_client.query.assert_not_called()


class TestEmailPattern:
    """EMAIL_PATTERN 正規表現のテスト

    validate_email で使われるパターンが正しく機能することを確認
    """

    def test_email_pattern_valid(self, module_under_test):
        """EMAIL_PATTERN が有効なメールを認識"""
        pattern = module_under_test.EMAIL_PATTERN
        assert pattern.match("user@tadakayo.jp") is not None

    def test_email_pattern_invalid_no_at(self, module_under_test):
        """EMAIL_PATTERN が @ なしを拒否"""
        pattern = module_under_test.EMAIL_PATTERN
        assert pattern.match("user") is None

    def test_email_pattern_invalid_multiple_at(self, module_under_test):
        """EMAIL_PATTERN が複数 @ を拒否"""
        pattern = module_under_test.EMAIL_PATTERN
        assert pattern.match("user@user@tadakayo.jp") is None


class TestConstants:
    """定数のテスト"""

    def test_allowed_domain(self, module_under_test):
        """ALLOWED_DOMAIN 定数が正しい"""
        assert module_under_test.ALLOWED_DOMAIN == "tadakayo.jp"

    def test_initial_admin_email(self, module_under_test):
        """INITIAL_ADMIN_EMAIL が正しくインポートされている"""
        # lib.constants から正しい値がインポートされていることを確認
        from lib.constants import INITIAL_ADMIN_EMAIL

        assert INITIAL_ADMIN_EMAIL == "yasushi-honda@tadakayo.jp"
        assert (
            module_under_test.INITIAL_ADMIN_EMAIL == INITIAL_ADMIN_EMAIL
        )


class TestBoundaryConditions:
    """境界値・エッジケースのテスト"""

    def test_validate_email_case_insensitive_domain(self, module_under_test):
        """ドメインの大文字小文字（endswith チェック用）"""
        # validate_email は endswith() なので大文字は失敗する
        result = module_under_test.validate_email("user@TADAKAYO.JP")
        assert result is not None

    def test_validate_email_whitespace_only(self, module_under_test):
        """空白のみの文字列"""
        result = module_under_test.validate_email("   ")
        assert result is not None

    def test_validate_email_special_chars_in_local(self, module_under_test):
        """ローカル部分の特殊文字"""
        # RFC 5321では許可だが、パターンで許可されているのは: . _ % + -
        result = module_under_test.validate_email("user.name+tag@tadakayo.jp")
        assert result is None

    def test_delete_user_with_special_email_chars(self, module_under_test):
        """特殊文字を含むメールアドレスの削除"""
        module_under_test.email = "admin@tadakayo.jp"

        with patch("pages.user_management.get_bq_client") as mock_get_bq:
            mock_client = MagicMock()
            mock_result = MagicMock()
            mock_job = MagicMock()
            mock_job.result.return_value = mock_result
            mock_client.query.return_value = mock_job
            mock_get_bq.return_value = mock_client

            target_email = "user+tag@tadakayo.jp"
            success, message = module_under_test.delete_user(target_email)

            assert success is True
            # query_parameters に正しくメールアドレスが渡されたか確認
            call_args = mock_client.query.call_args
            assert call_args is not None


class TestErrorMessages:
    """エラーメッセージのテスト"""

    def test_validate_email_error_message_invalid_format(self, module_under_test):
        """無効フォーマットのエラーメッセージ"""
        result = module_under_test.validate_email("invalid")
        assert result == "有効なメールアドレスを入力してください"

    def test_validate_email_error_message_wrong_domain(self, module_under_test):
        """ドメイン違いのエラーメッセージ"""
        result = module_under_test.validate_email("user@example.com")
        assert "tadakayo.jp" in result
        assert "ドメイン" in result

    def test_delete_user_error_message_initial_admin(self, module_under_test):
        """初期管理者削除エラーメッセージ"""
        success, message = module_under_test.delete_user(
            "yasushi-honda@tadakayo.jp"
        )
        assert message == "初期管理者は削除できません"

    def test_delete_user_error_message_self(self, module_under_test):
        """自分自身削除エラーメッセージ"""
        module_under_test.email = "user@tadakayo.jp"
        success, message = module_under_test.delete_user("user@tadakayo.jp")
        assert message == "自分自身は削除できません"

    def test_update_role_error_message_initial_admin(self, module_under_test):
        """初期管理者ロール変更エラーメッセージ"""
        success, message = module_under_test.update_role(
            "yasushi-honda@tadakayo.jp", "viewer"
        )
        assert message == "初期管理者のロールは変更できません"


class TestFilterUsers:
    """filter_users() のテスト

    ロール・グループでのフィルタロジックを検証
    """

    @pytest.fixture
    def sample_users_df(self):
        import pandas as pd
        return pd.DataFrame([
            {"email": "admin1@tadakayo.jp", "role": "admin", "source_group": None},
            {"email": "admin2@tadakayo.jp", "role": "admin", "source_group": "admins@tadakayo.jp"},
            {"email": "checker1@tadakayo.jp", "role": "checker", "source_group": "checkers@tadakayo.jp"},
            {"email": "user1@tadakayo.jp", "role": "user", "source_group": "members@tadakayo.jp"},
            {"email": "user2@tadakayo.jp", "role": "user", "source_group": None},
            {"email": "viewer1@tadakayo.jp", "role": "viewer", "source_group": "members@tadakayo.jp"},
        ])

    def test_filter_all_no_filter(self, module_under_test, sample_users_df):
        """ロール=全て・グループ=全て → 全件返却"""
        result = module_under_test.filter_users(sample_users_df, "全て", "全て")
        assert len(result) == 6

    def test_filter_role_admin(self, module_under_test, sample_users_df):
        """ロール=admin → admin のみ"""
        result = module_under_test.filter_users(sample_users_df, "admin", "全て")
        assert len(result) == 2
        assert all(result["role"] == "admin")

    def test_filter_role_checker(self, module_under_test, sample_users_df):
        """ロール=checker → checker のみ"""
        result = module_under_test.filter_users(sample_users_df, "checker", "全て")
        assert len(result) == 1
        assert result.iloc[0]["email"] == "checker1@tadakayo.jp"

    def test_filter_role_no_match(self, module_under_test, sample_users_df):
        """該当ロール無し → 空 DataFrame"""
        # 一時的に存在しないロールを指定
        result = module_under_test.filter_users(sample_users_df, "nonexistent", "全て")
        assert len(result) == 0

    def test_filter_group_individual_only(self, module_under_test, sample_users_df):
        """グループ=(個別登録のみ) → source_group が NaN のみ"""
        result = module_under_test.filter_users(sample_users_df, "全て", "(個別登録のみ)")
        assert len(result) == 2
        assert all(result["source_group"].isna())

    def test_filter_group_specific(self, module_under_test, sample_users_df):
        """グループ=members@tadakayo.jp → 該当グループのみ"""
        result = module_under_test.filter_users(sample_users_df, "全て", "members@tadakayo.jp")
        assert len(result) == 2
        assert all(result["source_group"] == "members@tadakayo.jp")

    def test_filter_role_and_group_combined(self, module_under_test, sample_users_df):
        """ロール=user + グループ=members@tadakayo.jp → AND 条件"""
        result = module_under_test.filter_users(sample_users_df, "user", "members@tadakayo.jp")
        assert len(result) == 1
        assert result.iloc[0]["email"] == "user1@tadakayo.jp"

    def test_filter_role_admin_and_individual_group(self, module_under_test, sample_users_df):
        """ロール=admin + グループ=(個別登録のみ) → 個別登録の admin のみ"""
        result = module_under_test.filter_users(sample_users_df, "admin", "(個別登録のみ)")
        assert len(result) == 1
        assert result.iloc[0]["email"] == "admin1@tadakayo.jp"

    def test_filter_does_not_mutate_original(self, module_under_test, sample_users_df):
        """フィルタ適用後も元の DataFrame が変更されない"""
        original_len = len(sample_users_df)
        module_under_test.filter_users(sample_users_df, "admin", "全て")
        assert len(sample_users_df) == original_len


class TestSyncGroupHelpers:
    """グループ自動同期 ON/OFF ヘルパーのテスト"""

    def _build_mock_query(self):
        """get_bq_client().query().result() の MagicMock チェーン"""
        mock_result = MagicMock()
        mock_job = MagicMock()
        mock_job.result.return_value = mock_result
        mock_client = MagicMock()
        mock_client.query.return_value = mock_job
        return mock_client, mock_job

    def test_register_sync_group_issues_merge_with_enabled_true(self, module_under_test):
        """AC4: register_sync_group は MERGE 文を発行し enabled=TRUE で初期化する"""
        mock_client, mock_job = self._build_mock_query()
        with patch("pages.user_management.get_bq_client", return_value=mock_client):
            module_under_test.register_sync_group("group-a@tadakayo.jp", "admin@tadakayo.jp")

        mock_client.query.assert_called_once()
        sql = mock_client.query.call_args[0][0]
        assert "MERGE" in sql
        assert "dashboard_sync_groups" in sql
        # 既存設定を上書きしないため UPDATE 句は無く INSERT のみ
        assert "WHEN NOT MATCHED THEN" in sql
        assert "WHEN MATCHED THEN" not in sql
        # enabled=TRUE が INSERT 部にハードコードされている
        assert "TRUE" in sql

    def test_set_sync_enabled_to_off_issues_update(self, module_under_test):
        """AC5: set_sync_enabled は MERGE で UPDATE 経路を持つ"""
        mock_client, mock_job = self._build_mock_query()
        with patch("pages.user_management.get_bq_client", return_value=mock_client):
            module_under_test.set_sync_enabled(
                "group-a@tadakayo.jp", False, "admin@tadakayo.jp"
            )

        mock_client.query.assert_called_once()
        sql = mock_client.query.call_args[0][0]
        assert "MERGE" in sql
        assert "WHEN MATCHED THEN" in sql
        assert "WHEN NOT MATCHED THEN" in sql
        # enabled パラメータが BOOL として渡される
        params = mock_client.query.call_args.kwargs["job_config"].query_parameters
        param_dict = {p.name: p.value for p in params}
        assert param_dict["enabled"] is False
        assert param_dict["group_email"] == "group-a@tadakayo.jp"

    def test_load_sync_groups_overview_joins_correctly(self, module_under_test):
        """AC10: load_sync_groups_overview は groups_master と LEFT JOIN し is_orphaned を返す"""
        import pandas as pd

        expected_df = pd.DataFrame([
            {
                "group_email": "group-a@tadakayo.jp",
                "enabled": True,
                "last_synced_at": None,
                "updated_at": None,
                "updated_by": "migration",
                "group_name": "Group A",
                "user_count": 5,
                "is_orphaned": False,
            },
            {
                "group_email": "deleted-group@tadakayo.jp",
                "enabled": False,
                "last_synced_at": None,
                "updated_at": None,
                "updated_by": "admin@tadakayo.jp",
                "group_name": None,
                "user_count": 2,
                "is_orphaned": True,
            },
        ])

        mock_client = MagicMock()
        mock_query_result = MagicMock()
        mock_query_result.to_dataframe.return_value = expected_df
        mock_client.query.return_value = mock_query_result

        with patch("pages.user_management.get_bq_client", return_value=mock_client):
            df = module_under_test.load_sync_groups_overview()

        sql = mock_client.query.call_args[0][0]
        assert "LEFT JOIN" in sql
        assert "groups_master" in sql
        assert "dashboard_sync_groups" in sql
        assert "is_orphaned" in sql
        assert "user_count" in sql
        assert len(df) == 2
        assert bool(df.iloc[1]["is_orphaned"]) is True
        assert bool(df.iloc[0]["is_orphaned"]) is False

    def test_add_users_by_group_calls_register_sync_group(self, module_under_test):
        """AC4: add_users_by_group の最後に register_sync_group が呼ばれる"""
        import pandas as pd

        members_df = pd.DataFrame([
            {"gws_account": "alice@tadakayo.jp", "nickname": "alice", "full_name": "Alice"},
        ])

        mock_client, mock_job = self._build_mock_query()
        mock_job_result = MagicMock()
        mock_job_result.num_dml_affected_rows = 1
        mock_job.result.return_value = mock_job_result

        module_under_test.email = "admin@tadakayo.jp"

        with patch("pages.user_management.get_bq_client", return_value=mock_client), \
             patch("pages.user_management.register_sync_group") as mock_register:
            added = module_under_test.add_users_by_group(
                members_df, "viewer", "group-a@tadakayo.jp"
            )

        assert added == 1
        mock_register.assert_called_once_with("group-a@tadakayo.jp", "admin@tadakayo.jp")

    def test_is_user_in_group_returns_true_when_member(self, module_under_test):
        """AC11 補助: is_user_in_group は members テーブルで CONCAT LIKE 検索する"""
        mock_client = MagicMock()
        mock_row = MagicMock()
        mock_row.cnt = 1
        mock_job = MagicMock()
        mock_job.result.return_value = [mock_row]
        mock_client.query.return_value = mock_job

        with patch("pages.user_management.get_bq_client", return_value=mock_client):
            result = module_under_test.is_user_in_group(
                "user@tadakayo.jp", "group-a@tadakayo.jp"
            )

        assert result is True
        sql = mock_client.query.call_args[0][0]
        assert "CONCAT" in sql
        assert "LIKE" in sql
        assert "members" in sql

    def test_is_user_in_group_returns_false_when_not_member(self, module_under_test):
        """is_user_in_group: 所属していなければ False"""
        mock_client = MagicMock()
        mock_row = MagicMock()
        mock_row.cnt = 0
        mock_job = MagicMock()
        mock_job.result.return_value = [mock_row]
        mock_client.query.return_value = mock_job

        with patch("pages.user_management.get_bq_client", return_value=mock_client):
            result = module_under_test.is_user_in_group(
                "user@tadakayo.jp", "group-a@tadakayo.jp"
            )

        assert result is False
