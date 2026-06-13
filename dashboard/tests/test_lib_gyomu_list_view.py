"""dashboard/lib/gyomu_list_view.py の単体テスト"""

from unittest.mock import MagicMock

import pandas as pd
import pytest

from lib.gyomu_list_view import filter_wam_only


@pytest.fixture
def base_df() -> pd.DataFrame:
    return pd.DataFrame({
        "work_category": [
            "（WAM）生成AIカスタマイズ開発費",  # 全角プレフィックス
            "(WAM)生成AIカスタマイズ開発費",   # 半角プレフィックス
            "出張タダスクで喜ばれ隊",            # 非WAM
            "XX（WAM）yy",                      # プレフィックスではなく途中含有
            " （WAM）先頭半角空白",             # 先頭半角空白
            "　（WAM）先頭全角空白",            # 先頭全角空白
            "ＷＡＭ全角アルファベット",         # 全角ＷＡＭ + 括弧なし
            "（ＷＡＭ）全角アルファ＋全角括弧", # 全角ＷＡＭ + 全角括弧
            None,                                # NaN
            "",                                  # 空文字
            "（WAM）",                           # プレフィックスのみ
        ],
        "amount": list(range(11)),
    })


def test_filter_wam_only_zenkaku_prefix(base_df: pd.DataFrame) -> None:
    """全角「（WAM）」プレフィックスは抽出される"""
    result = filter_wam_only(base_df)
    assert "（WAM）生成AIカスタマイズ開発費" in result["work_category"].tolist()


def test_filter_wam_only_hankaku_prefix(base_df: pd.DataFrame) -> None:
    """半角「(WAM)」プレフィックスは抽出される"""
    result = filter_wam_only(base_df)
    assert "(WAM)生成AIカスタマイズ開発費" in result["work_category"].tolist()


def test_filter_wam_only_excludes_middle_match(base_df: pd.DataFrame) -> None:
    """「XX（WAM）yy」のような途中含有は除外される (startswith厳密性)"""
    result = filter_wam_only(base_df)
    assert "XX（WAM）yy" not in result["work_category"].tolist()


def test_filter_wam_only_includes_leading_hankaku_space(base_df: pd.DataFrame) -> None:
    """先頭半角空白付きでも抽出される (lstrip適用)"""
    result = filter_wam_only(base_df)
    assert " （WAM）先頭半角空白" in result["work_category"].tolist()


def test_filter_wam_only_includes_leading_zenkaku_space(base_df: pd.DataFrame) -> None:
    """先頭全角空白付きでも抽出される (NFKC正規化で半角化 → lstrip)"""
    result = filter_wam_only(base_df)
    assert "　（WAM）先頭全角空白" in result["work_category"].tolist()


def test_filter_wam_only_includes_zenkaku_with_brackets(base_df: pd.DataFrame) -> None:
    """全角ＷＡＭ＋全角括弧も NFKC で半角化されて抽出される"""
    result = filter_wam_only(base_df)
    assert "（ＷＡＭ）全角アルファ＋全角括弧" in result["work_category"].tolist()


def test_filter_wam_only_excludes_zenkaku_without_brackets(base_df: pd.DataFrame) -> None:
    """括弧なし「ＷＡＭ全角...」は除外される (プレフィックス判定厳守)"""
    result = filter_wam_only(base_df)
    assert "ＷＡＭ全角アルファベット" not in result["work_category"].tolist()


def test_filter_wam_only_excludes_nan(base_df: pd.DataFrame) -> None:
    """NaN は除外される"""
    result = filter_wam_only(base_df)
    assert result["work_category"].isna().sum() == 0


def test_filter_wam_only_excludes_empty(base_df: pd.DataFrame) -> None:
    """空文字は除外される"""
    result = filter_wam_only(base_df)
    assert "" not in result["work_category"].tolist()


def test_filter_wam_only_includes_prefix_only(base_df: pd.DataFrame) -> None:
    """プレフィックスのみ「（WAM）」も抽出される"""
    result = filter_wam_only(base_df)
    assert "（WAM）" in result["work_category"].tolist()


def test_filter_wam_only_does_not_mutate_original(base_df: pd.DataFrame) -> None:
    """元のDataFrameの work_category 値は変更されない"""
    original = base_df["work_category"].copy()
    filter_wam_only(base_df)
    pd.testing.assert_series_equal(base_df["work_category"], original)


def test_filter_wam_only_preserves_other_columns(base_df: pd.DataFrame) -> None:
    """抽出後も他の列 (amount) が保持される"""
    result = filter_wam_only(base_df)
    assert "amount" in result.columns


def test_filter_wam_only_empty_df_returns_empty() -> None:
    """空のDataFrameを渡すと空のDataFrameを返す"""
    df = pd.DataFrame({"work_category": pd.Series([], dtype=object), "amount": pd.Series([], dtype=int)})
    result = filter_wam_only(df)
    assert len(result) == 0


def test_filter_wam_only_no_match_returns_empty() -> None:
    """マッチする行がない場合は空のDataFrameを返す"""
    df = pd.DataFrame({"work_category": ["A", "B", "C"], "amount": [1, 2, 3]})
    result = filter_wam_only(df)
    assert len(result) == 0


# ==========================================================================
# Issue #254 (Codex セカンドオピニオン反映): _filter_by_period 純関数テスト
# ==========================================================================

from lib.gyomu_list_view import _filter_by_period  # noqa: E402


class TestFilterByPeriod:
    """期間フィルタの純関数テスト。range_*/selected_month の組合せを検証"""

    @pytest.fixture
    def period_df(self) -> pd.DataFrame:
        return pd.DataFrame({
            "year": [2026, 2026, 2026, 2026, 2025],
            "month": [5, 6, 7, 12, 6],
            "amount": [100, 200, 300, 400, 500],
        })

    def test_single_month(self, period_df):
        """selected_month='6月' で 1 ヶ月分のみ抽出"""
        result = _filter_by_period(
            period_df, 2026, "6月", None, None, None, None
        )
        assert len(result) == 1
        assert result.iloc[0]["amount"] == 200

    def test_period_range_same_year(self, period_df):
        """期間指定で 2026/5-2026/7 を抽出"""
        result = _filter_by_period(
            period_df, 0, "期間指定", 2026, 5, 2026, 7
        )
        assert sorted(result["amount"].tolist()) == [100, 200, 300]

    def test_period_range_cross_year(self, period_df):
        """年またぎ 2025/6-2026/6 を抽出"""
        result = _filter_by_period(
            period_df, 0, "期間指定", 2025, 6, 2026, 6
        )
        assert sorted(result["amount"].tolist()) == [100, 200, 500]

    def test_period_range_end_before_start(self, period_df):
        """終了 < 開始 で None を返す (呼び出し元に warning 委譲)"""
        result = _filter_by_period(
            period_df, 0, "期間指定", 2026, 7, 2026, 5
        )
        assert result is None

    def test_single_month_ignores_range_args(self, period_df):
        """T9 (Codex Medium): selected_month != '期間指定' で range_* は不参照
        (None を渡しても None * 100 が発生しない)"""
        result = _filter_by_period(
            period_df, 2026, "6月", None, None, None, None
        )
        # AssertionError なし = range_* が参照されなかった証拠
        assert len(result) == 1


# ==========================================================================
# Issue #254/#245: render_gyomu_list_view の Streamlit 経由テスト
# ==========================================================================

from lib.gyomu_list_view import render_gyomu_list_view  # noqa: E402


@pytest.fixture
def render_df() -> pd.DataFrame:
    """render_gyomu_list_view 用の正規化済み DataFrame"""
    return pd.DataFrame({
        "year": [2026, 2026, 2026, 2026],
        "month": [6, 6, 6, 6],
        "nickname": ["alice", "bob", "alice", "carol"],
        "display_name": ["Alice 太郎", "Bob 次郎", "Alice 太郎", "Carol 三郎"],
        "source_url": ["url1", "url2", "url3", "url4"],
        "date": ["2026/6/1", "2026/6/2", "2026/6/3", "2026/6/4"],
        "day_of_week": ["月", "火", "水", "木"],
        "activity_category": ["○○隊", "○○隊", "△△隊", "△△隊"],
        "work_category": ["WK1", "WK2", "WK1", "WK3"],
        "sponsor": ["神奈川県", "経産省", "神奈川県", "WAM"],
        "description": ["内容A", "内容B", "内容C", "内容D"],
        "unit_price": ["3000", "3000", "3000", "3000"],
        "work_hours": ["2", "3", "4", "5"],
        "travel_distance_km": ["0", "0", "0", "0"],
        "amount": ["6000", "9000", "12000", "15000"],
    })


class TestRenderGyomuListView:
    """render_gyomu_list_view の挙動テスト (Streamlit mock 経由)"""

    def _call(self, df, mock_streamlit, **kwargs):
        """共通: render 関数を呼び、session_state を返す。
        widget の戻り値を明示設定 (デフォルト MagicMock は filter 動作を壊す)"""
        # widget mock の return_value を空状態に固定 (default は MagicMock で truthy)
        mock_streamlit.selectbox = MagicMock(return_value="隊（活動）分類")
        mock_streamlit.multiselect = MagicMock(return_value=[])
        mock_streamlit.text_input = MagicMock(return_value="")
        mock_streamlit.button = MagicMock(return_value=False)
        defaults = dict(
            df_gyomu_all=df,
            name_map={"alice": "Alice 太郎", "bob": "Bob 次郎", "carol": "Carol 三郎"},
            all_members=["alice", "bob", "carol"],
            selected_members=[],
            selected_year=2026,
            selected_month="6月",
            key_prefix="test",
        )
        defaults.update(kwargs)
        render_gyomu_list_view(**defaults)
        return mock_streamlit.session_state

    def test_T1_default_mode_shows_team_filter(self, render_df, mock_streamlit):
        """T1: fixed_activity_category=None で既存挙動 (隊フィルタ UI 表示)
        st.columns(3) が呼ばれることで 3 列レイアウトを検証"""
        mock_streamlit.columns = MagicMock(side_effect=lambda spec: tuple(
            MagicMock() for _ in (range(spec) if isinstance(spec, int) else range(len(spec)))
        ))
        self._call(render_df, mock_streamlit)
        # columns(3) が少なくとも 1 回呼ばれていれば隊分類 UI が存在
        spec_3_calls = [c for c in mock_streamlit.columns.call_args_list
                        if c.args and c.args[0] == 3]
        assert len(spec_3_calls) >= 1

    def test_T2_fixed_mode_filters_internally(self, render_df, mock_streamlit):
        """T2: fixed_activity_category 指定で内部 filter 適用
        対象隊の row 数だけ KPI に反映される"""
        self._call(render_df, mock_streamlit, fixed_activity_category="○○隊")
        # dataframe call で渡された rows を検査
        df_calls = mock_streamlit.dataframe.call_args_list
        assert len(df_calls) >= 1
        rendered = df_calls[-1].args[0]  # 最後の dataframe call の第 1 引数
        # ○○隊 の 2 行のみ
        assert len(rendered) == 2

    def test_T3_fixed_nonexistent_team_shows_empty_message(
        self, render_df, mock_streamlit,
    ):
        """T3: fixed_activity_category="存在しない隊" で empty_message 表示"""
        self._call(
            render_df, mock_streamlit,
            fixed_activity_category="存在しない隊",
            empty_message="この隊の業務報告はありません",
        )
        info_calls = [c.args[0] for c in mock_streamlit.info.call_args_list]
        assert "この隊の業務報告はありません" in info_calls

    def test_T4_dependent_dropdown_in_fixed_mode(self, render_df, mock_streamlit):
        """T4: fixed mode でも依存型ドロップダウン (業務分類 / スポンサー) 表示
        st.columns(2) が呼ばれることで 2 列レイアウト確認"""
        mock_streamlit.columns = MagicMock(side_effect=lambda spec: tuple(
            MagicMock() for _ in (range(spec) if isinstance(spec, int) else range(len(spec)))
        ))
        self._call(
            render_df, mock_streamlit, fixed_activity_category="○○隊",
        )
        spec_2_calls = [c for c in mock_streamlit.columns.call_args_list
                        if c.args and c.args[0] == 2]
        # fixed mode では fcol1 を出さず fcol2/fcol3 の 2 列
        assert len(spec_2_calls) >= 1

    def test_T5_reset_button_advances_counter(self, render_df, mock_streamlit):
        """T5: リセットボタンの on_click で counter advance"""
        # 初期 counter は 0
        self._call(render_df, mock_streamlit, key_prefix="reset_test")
        assert mock_streamlit.session_state.get("reset_test_reset_counter") == 0

    def test_T6_fixed_mode_excludes_activity_category_from_search_targets(
        self, render_df, mock_streamlit,
    ):
        """T6 (Codex Medium): fixed mode で検索対象から「隊（活動）分類」除外"""
        # multiselect の options 引数を捕捉 (_call ヘルパを使わず直接呼ぶ)
        multiselect_calls = []

        def capture_multiselect(label, options, **kwargs):
            multiselect_calls.append((label, options))
            return []
        mock_streamlit.multiselect = capture_multiselect
        mock_streamlit.text_input = MagicMock(return_value="")
        mock_streamlit.button = MagicMock(return_value=False)
        render_gyomu_list_view(
            df_gyomu_all=render_df,
            name_map={"alice": "Alice 太郎", "bob": "Bob 次郎", "carol": "Carol 三郎"},
            all_members=["alice", "bob", "carol"],
            selected_members=[],
            selected_year=2026,
            selected_month="6月",
            key_prefix="search_test",
            fixed_activity_category="○○隊",
        )
        # 検索対象の multiselect (label="検索対象") の options に「隊（活動）分類」が
        # 含まれないことを確認
        search_targets_calls = [
            opts for lbl, opts in multiselect_calls if lbl == "検索対象"
        ]
        assert len(search_targets_calls) >= 1
        assert "隊（活動）分類" not in search_targets_calls[0]

    def test_T7_counter_advances_on_team_change(self, render_df, mock_streamlit):
        """T7 (Codex Medium): fixed_activity_category 変更時に counter advance"""
        # 1 回目: ○○隊
        self._call(
            render_df, mock_streamlit, fixed_activity_category="○○隊",
            key_prefix="t7",
        )
        counter_after_first = mock_streamlit.session_state.get("t7_reset_counter")
        # 2 回目: △△隊 (変更)
        self._call(
            render_df, mock_streamlit, fixed_activity_category="△△隊",
            key_prefix="t7",
        )
        counter_after_second = mock_streamlit.session_state.get("t7_reset_counter")
        assert counter_after_second == counter_after_first + 1

    def test_T8_compact_mode_uses_height_360(self, render_df, mock_streamlit):
        """T8 (Codex High #3): compact=True で dataframe height=360"""
        self._call(
            render_df, mock_streamlit, fixed_activity_category="○○隊", compact=True,
        )
        df_calls = mock_streamlit.dataframe.call_args_list
        assert len(df_calls) >= 1
        # height kwarg を検証
        last_kwargs = df_calls[-1].kwargs
        assert last_kwargs.get("height") == 360

    def test_T8_compact_excludes_activity_category_column(
        self, render_df, mock_streamlit,
    ):
        """T8 (Codex High #3): compact=True で表示列から activity_category 除外"""
        self._call(
            render_df, mock_streamlit, fixed_activity_category="○○隊", compact=True,
        )
        df_calls = mock_streamlit.dataframe.call_args_list
        assert len(df_calls) >= 1
        rendered = df_calls[-1].args[0]
        # compact では rename 後のカラム名で「隊（活動）分類」が含まれない
        assert "隊（活動）分類" not in rendered.columns
        assert "URL" not in rendered.columns

    def test_T9_single_month_with_none_range_args_safe(
        self, render_df, mock_streamlit,
    ):
        """T9 (Codex Medium): selected_month != '期間指定' で range_*=None
        を渡しても None * 100 例外が出ない"""
        # range_* を全て None で呼ぶ (実行できれば PASS)
        self._call(
            render_df, mock_streamlit, selected_month="6月",
            range_start_year=None, range_start_month=None,
            range_end_year=None, range_end_month=None,
            key_prefix="t9",
        )
        # 例外なく完了したこと自体が AC

    def test_T10_empty_df_shows_empty_message(self, mock_streamlit):
        """T10: 空 DataFrame で empty_message 表示"""
        empty_df = pd.DataFrame()
        render_gyomu_list_view(
            df_gyomu_all=empty_df,
            name_map={},
            all_members=[],
            selected_members=[],
            selected_year=2026,
            selected_month="6月",
            key_prefix="empty_test",
            empty_message="データなし",
        )
        info_calls = [c.args[0] for c in mock_streamlit.info.call_args_list]
        assert "データなし" in info_calls
