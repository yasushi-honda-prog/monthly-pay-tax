"""GAS Script ID 管理ページのユニットテスト

gas_management.py はモジュール import 時に load_bindings() / count_targets() を
呼ぶため、get_bq_client をモック化してからインポートして描画パスを検証する。
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

dashboard_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(dashboard_dir))

COLS = [
    "spreadsheet_id", "report_url", "script_id", "editor_url", "member_id",
    "nickname", "url_source", "status", "error_type", "error_detail", "fetched_at",
]


@pytest.fixture
def mock_auth_require_admin():
    with patch("lib.auth.require_admin", return_value=None) as m:
        yield m


def _load_module(df, target_count=215):
    """get_bq_client をモック化して gas_management を import"""
    if "pages.gas_management" in sys.modules:
        del sys.modules["pages.gas_management"]
    import importlib

    with patch("lib.bq_client.get_bq_client") as mock_get_bq:
        mock_client = MagicMock()
        mock_qr = MagicMock()
        mock_qr.to_dataframe.return_value = df  # load_bindings
        mock_qr.result.return_value = [MagicMock(n=target_count)]  # count_targets
        mock_client.query.return_value = mock_qr
        mock_get_bq.return_value = mock_client
        return importlib.import_module("pages.gas_management")


@pytest.fixture
def sample_df():
    return pd.DataFrame(
        [
            {
                "spreadsheet_id": "a", "report_url": "https://s/a", "script_id": "sid_ok",
                "editor_url": "https://e/a", "member_id": "m1", "nickname": "ニック",
                "url_source": "url_1", "status": "ok", "error_type": None,
                "error_detail": None, "fetched_at": None,
            },
            {
                "spreadsheet_id": "b", "report_url": "https://s/b", "script_id": None,
                "editor_url": None, "member_id": "m2", "nickname": "ニック2",
                "url_source": "url_1", "status": "error", "error_type": "auth_required",
                "error_detail": "x", "fetched_at": None,
            },
        ],
        columns=COLS,
    )


def test_module_loads_with_data(mock_streamlit, mock_auth_require_admin, sample_df):
    """データありで描画パスが例外なく通り、認証ガードが呼ばれる"""
    mod = _load_module(sample_df, target_count=215)
    assert mod is not None
    mock_auth_require_admin.assert_called_once()


def test_module_loads_empty(mock_streamlit, mock_auth_require_admin):
    """空 DataFrame（列のみ）でも描画パスが例外なく通る"""
    empty = pd.DataFrame(columns=COLS)
    mod = _load_module(empty, target_count=215)
    assert mod is not None


def test_dataframe_rendered(mock_streamlit, mock_auth_require_admin, sample_df):
    """データありパスで一覧（st.dataframe）が描画される"""
    _load_module(sample_df, target_count=215)
    assert mock_streamlit.dataframe.called
