"""ui_helpers.py のユニットテスト

純粋ロジック関数をテスト対象とする:
- clean_numeric_scalar
- clean_numeric_series
- fill_empty_nickname
- valid_years
"""

import pandas as pd
import pytest

from lib.ui_helpers import (
    add_gyomu_date_dt,
    clean_numeric_scalar,
    clean_numeric_series,
    fill_empty_nickname,
    parse_gyomu_date,
    valid_years,
)


class TestCleanNumericScalar:
    """clean_numeric_scalar() のテストクラス"""

    # ========== 正常系 ==========

    def test_通常の整数(self):
        """整数文字列を float に変換"""
        assert clean_numeric_scalar("100") == 100.0

    def test_通常の浮動小数点(self):
        """浮動小数点文字列を float に変換"""
        assert clean_numeric_scalar("123.45") == 123.45

    def test_負数(self):
        """負数を正しく変換"""
        assert clean_numeric_scalar("-50") == -50.0

    def test_ゼロ(self):
        """ゼロを正しく変換"""
        assert clean_numeric_scalar("0") == 0.0

    def test_通貨記号_ドル(self):
        """$ 記号を除去"""
        assert clean_numeric_scalar("$100") == 100.0

    def test_通貨記号_円(self):
        """¥ 記号を除去"""
        assert clean_numeric_scalar("¥100") == 100.0

    def test_通貨記号_全角ドル(self):
        """＄ 記号を除去"""
        assert clean_numeric_scalar("＄100") == 100.0

    def test_カンマ除去(self):
        """カンマを除去"""
        assert clean_numeric_scalar("1,000,000") == 1000000.0

    def test_カンマと通貨記号の組み合わせ(self):
        """通貨記号とカンマを同時に除去"""
        assert clean_numeric_scalar("¥1,000,000") == 1000000.0
        assert clean_numeric_scalar("$1,234.56") == 1234.56

    def test_前後のスペース(self):
        """前後のスペースを除去"""
        assert clean_numeric_scalar("  100  ") == 100.0
        assert clean_numeric_scalar("\t100\t") == 100.0

    # ========== 境界値テスト ==========

    @pytest.mark.parametrize("val", ["2020", "2030", "-2030"])
    def test_大きな数値(self, val):
        """大きな数値を正しく変換"""
        result = clean_numeric_scalar(val)
        assert isinstance(result, float)
        assert result == float(val)

    def test_非常に小さい浮動小数点(self):
        """非常に小さい浮動小数点"""
        assert clean_numeric_scalar("0.0001") == 0.0001

    # ========== エラーケース: None/NaN ==========

    def test_None(self):
        """None → 0.0"""
        assert clean_numeric_scalar(None) == 0.0

    def test_NaN(self):
        """NaN → 0.0"""
        assert clean_numeric_scalar(float("nan")) == 0.0

    def test_pd_NA(self):
        """pd.NA → 0.0"""
        assert clean_numeric_scalar(pd.NA) == 0.0

    # ========== エラーケース: 文字列 ==========

    def test_文字列_None(self):
        """文字列の "None" → 0.0"""
        assert clean_numeric_scalar("None") == 0.0

    def test_文字列_nan(self):
        """文字列の "nan" → 0.0"""
        assert clean_numeric_scalar("nan") == 0.0

    def test_空文字(self):
        """空文字列 → 0.0"""
        assert clean_numeric_scalar("") == 0.0

    def test_スペースのみ(self):
        """スペースのみ → 0.0"""
        assert clean_numeric_scalar("   ") == 0.0

    # ========== エラーケース: スプレッドシート ==========

    @pytest.mark.parametrize("error", ["#N/A", "#ERROR!", "#VALUE!", "#DIV/0!", "#REF!"])
    def test_スプレッドシートエラー(self, error):
        """スプレッドシートエラー → 0.0"""
        assert clean_numeric_scalar(error) == 0.0

    def test_スプレッドシートエラー_小文字(self):
        """小文字のエラーも処理"""
        assert clean_numeric_scalar("#n/a") == 0.0

    # ========== エラーケース: 不正な文字列 ==========

    def test_純粋なアルファベット(self):
        """純粋なアルファベット → 0.0"""
        assert clean_numeric_scalar("abc") == 0.0

    def test_記号のみ(self):
        """記号のみ → 0.0"""
        assert clean_numeric_scalar("@#$%") == 0.0

    def test_数字混在の不正文字列(self):
        """数字混在の不正文字列 → 0.0"""
        assert clean_numeric_scalar("12abc") == 0.0
        assert clean_numeric_scalar("abc12") == 0.0

    # ========== 型テスト ==========

    def test_整数入力(self):
        """整数入力を float に変換"""
        assert clean_numeric_scalar(100) == 100.0
        assert isinstance(clean_numeric_scalar(100), float)

    def test_浮動小数点入力(self):
        """浮動小数点入力をそのまま float に"""
        result = clean_numeric_scalar(123.45)
        assert result == 123.45

    def test_ブール値入力(self):
        """ブール値 True/False の処理（pd.isna判定がTrue）"""
        # ブール値は Python では True=1, False=0 だが、
        # 文字列化後に "True"/"False" となり変換失敗 → 0.0
        # ただし pd.isna(True) は False なので、実装依存
        result_true = clean_numeric_scalar(True)
        result_false = clean_numeric_scalar(False)
        # 実装では True/False を "True"/"False" に変換 → ValueError → 0.0
        assert result_true == 0.0
        assert result_false == 0.0


class TestCleanNumericSeries:
    """clean_numeric_series() のテストクラス"""

    def test_基本的なSeries変換(self):
        """Series 全要素に clean_numeric_scalar が適用される"""
        series = pd.Series(["100", "200", "300"])
        result = clean_numeric_series(series)
        expected = pd.Series([100.0, 200.0, 300.0])
        pd.testing.assert_series_equal(result, expected)

    def test_Series_通貨記号とカンマ(self):
        """Series で通貨記号・カンマが除去される"""
        series = pd.Series(["¥1,000", "$2,000", "3,000"])
        result = clean_numeric_series(series)
        expected = pd.Series([1000.0, 2000.0, 3000.0])
        pd.testing.assert_series_equal(result, expected)

    def test_Series_エラー混在(self):
        """Series にエラー値が混在する場合"""
        series = pd.Series(["100", "#N/A", None, "200", ""])
        result = clean_numeric_series(series)
        expected = pd.Series([100.0, 0.0, 0.0, 200.0, 0.0])
        pd.testing.assert_series_equal(result, expected)

    def test_Series_NaN混在(self):
        """Series に NaN が含まれる場合"""
        series = pd.Series([100.0, float("nan"), 200.0])
        result = clean_numeric_series(series)
        expected = pd.Series([100.0, 0.0, 200.0])
        pd.testing.assert_series_equal(result, expected)

    def test_Series_空(self):
        """空の Series"""
        series = pd.Series([], dtype=object)
        result = clean_numeric_series(series)
        assert len(result) == 0

    def test_Series_単一要素(self):
        """単一要素の Series"""
        series = pd.Series(["999"])
        result = clean_numeric_series(series)
        expected = pd.Series([999.0])
        pd.testing.assert_series_equal(result, expected)


class TestFillEmptyNickname:
    """fill_empty_nickname() のテストクラス"""

    def test_基本的な動作_空の場合(self):
        """空の nickname を "(未設定)" に置換"""
        df = pd.DataFrame({"nickname": ["Alice", "", "Bob"]})
        result = fill_empty_nickname(df)
        assert result["nickname"].tolist() == ["Alice", "(未設定)", "Bob"]

    def test_None_の置換(self):
        """None の nickname を "(未設定)" に置換"""
        df = pd.DataFrame({"nickname": ["Alice", None, "Bob"]})
        result = fill_empty_nickname(df)
        assert result["nickname"].tolist() == ["Alice", "(未設定)", "Bob"]

    def test_前後のスペース除去(self):
        """前後のスペースが strip される"""
        df = pd.DataFrame({"nickname": ["  Alice  ", "  Bob  ", ""]})
        result = fill_empty_nickname(df)
        assert result["nickname"].tolist() == ["Alice", "Bob", "(未設定)"]

    def test_複数の空値(self):
        """複数の空値が全て置換される"""
        df = pd.DataFrame({"nickname": ["", None, "", "Alice"]})
        result = fill_empty_nickname(df)
        assert result["nickname"].tolist() == ["(未設定)", "(未設定)", "(未設定)", "Alice"]

    def test_全て空(self):
        """全て空の場合"""
        df = pd.DataFrame({"nickname": ["", None, ""]})
        result = fill_empty_nickname(df)
        assert all(v == "(未設定)" for v in result["nickname"])

    def test_全て有効な名前(self):
        """全て有効な名前（変更なし）"""
        df = pd.DataFrame({"nickname": ["Alice", "Bob", "Charlie"]})
        result = fill_empty_nickname(df)
        assert result["nickname"].tolist() == ["Alice", "Bob", "Charlie"]

    def test_スペースのみ(self):
        """スペースのみのエントリ"""
        df = pd.DataFrame({"nickname": ["   ", "\t", "\n"]})
        result = fill_empty_nickname(df)
        assert all(v == "(未設定)" for v in result["nickname"])

    def test_返り値はDataFrame(self):
        """関数が DataFrame を返す"""
        df = pd.DataFrame({"nickname": ["Alice"]})
        result = fill_empty_nickname(df)
        assert isinstance(result, pd.DataFrame)

    def test_元の列はコピーではなく変更(self):
        """元の DataFrame が変更される（またはコピーが返される）"""
        df = pd.DataFrame({"nickname": ["", "Alice"]})
        result = fill_empty_nickname(df)
        assert result["nickname"].iloc[0] == "(未設定)"

    def test_複数列がある場合_nickname列のみ処理(self):
        """nickname 列以外は影響を受けない"""
        df = pd.DataFrame({
            "nickname": ["", "Alice"],
            "id": [1, 2],
            "email": ["a@example.com", "b@example.com"]
        })
        result = fill_empty_nickname(df)
        assert result["nickname"].tolist() == ["(未設定)", "Alice"]
        assert result["id"].tolist() == [1, 2]
        assert result["email"].tolist() == ["a@example.com", "b@example.com"]


class TestValidYears:
    """valid_years() のテストクラス"""

    # ========== 正常系 ==========

    def test_有効な年_単一値(self):
        """有効な年（2020-2030）は そのまま"""
        series = pd.Series([2020, 2025, 2030])
        result = valid_years(series)
        assert result.tolist() == [2020, 2025, 2030]

    def test_有効な年_文字列(self):
        """文字列の年を int に変換"""
        series = pd.Series(["2020", "2025", "2030"])
        result = valid_years(series)
        assert result.tolist() == [2020, 2025, 2030]

    def test_浮動小数点文字列(self):
        """浮動小数点文字列は int に変換"""
        series = pd.Series(["2020.0", "2025.9", "2030.1"])
        result = valid_years(series)
        assert result.tolist() == [2020, 2025, 2030]

    # ========== 境界値テスト ==========

    def test_境界値_最小有効年(self):
        """2020（最小有効年）"""
        assert valid_years(pd.Series([2020]))[0] == 2020

    def test_境界値_最大有効年(self):
        """2030（最大有効年）"""
        assert valid_years(pd.Series([2030]))[0] == 2030

    def test_境界値_範囲外_最小より1小さい(self):
        """2019（範囲外）→ None"""
        assert valid_years(pd.Series([2019]))[0] is None

    def test_境界値_範囲外_最大より1大きい(self):
        """2031（範囲外）→ None"""
        assert valid_years(pd.Series([2031]))[0] is None

    # ========== エラーケース ==========

    def test_範囲外_過去(self):
        """過去の年（2000, 2010）→ None"""
        series = pd.Series([2000, 2010, 2015])
        result = valid_years(series)
        assert all(v is None for v in result)

    def test_範囲外_将来(self):
        """将来の年（2040, 2050）→ None"""
        series = pd.Series([2040, 2050, 2100])
        result = valid_years(series)
        assert all(v is None for v in result)

    def test_None入力(self):
        """None → None"""
        assert valid_years(pd.Series([None]))[0] is None

    def test_NaN入力(self):
        """NaN → None"""
        assert valid_years(pd.Series([float("nan")]))[0] is None

    def test_pd_NA入力(self):
        """pd.NA → None"""
        assert valid_years(pd.Series([pd.NA]))[0] is None

    def test_空文字(self):
        """空文字列 → None"""
        assert valid_years(pd.Series([""]))[0] is None

    def test_不正な文字列(self):
        """不正な文字列 → None"""
        series = pd.Series(["abc", "xyz", "year"])
        result = valid_years(series)
        assert all(v is None for v in result)

    def test_混在する値(self):
        """有効/無効な値が混在"""
        series = pd.Series([2020, 2019, 2025, 2031, None, "2022"])
        result = valid_years(series)
        # Series に None が含まれると float NaN に変換される
        result_list = result.tolist()
        assert result_list[0] == 2020
        assert pd.isna(result_list[1])  # 2019 は範囲外 → None → NaN
        assert result_list[2] == 2025
        assert pd.isna(result_list[3])  # 2031 は範囲外 → None → NaN
        assert pd.isna(result_list[4])  # None → NaN
        assert result_list[5] == 2022

    # ========== 型テスト ==========

    def test_整数型Series(self):
        """整数型 Series"""
        series = pd.Series([2020, 2025, 2030], dtype="int64")
        result = valid_years(series)
        assert result.tolist() == [2020, 2025, 2030]

    def test_オブジェクト型Series(self):
        """オブジェクト型 Series（混在型）"""
        series = pd.Series([2020, "2025", 2030.0], dtype=object)
        result = valid_years(series)
        assert result.tolist() == [2020, 2025, 2030]

    # ========== 空Series ==========

    def test_空のSeries(self):
        """空の Series"""
        series = pd.Series([], dtype=object)
        result = valid_years(series)
        assert len(result) == 0

    def test_単一要素_有効(self):
        """単一要素の有効な年"""
        result = valid_years(pd.Series([2025]))[0]
        assert result == 2025

    def test_単一要素_無効(self):
        """単一要素の無効な年"""
        result = valid_years(pd.Series([2040]))[0]
        assert result is None


class TestParseGyomuDate:
    """parse_gyomu_date() のテスト

    BQ の gyomu_reports.date は STRING 型 ("4/29" / "4月29日" / "2025/4/29")
    のため、ソート可能な pd.Timestamp に変換するヘルパをカバーする。
    """

    # ========== 正常系: M/D 形式 ==========

    def test_md形式の通常入力(self):
        result = parse_gyomu_date(2025, "4/29")
        assert result == pd.Timestamp(year=2025, month=4, day=29)

    def test_md形式の月初(self):
        result = parse_gyomu_date(2025, "4/1")
        assert result == pd.Timestamp(year=2025, month=4, day=1)

    def test_md形式の年末(self):
        result = parse_gyomu_date(2025, "12/31")
        assert result == pd.Timestamp(year=2025, month=12, day=31)

    def test_md形式_前後空白(self):
        result = parse_gyomu_date(2025, " 4/29 ")
        assert result == pd.Timestamp(year=2025, month=4, day=29)

    # ========== 正常系: M月D日 形式 ==========

    def test_jp形式の通常入力(self):
        result = parse_gyomu_date(2025, "4月29日")
        assert result == pd.Timestamp(year=2025, month=4, day=29)

    def test_jp形式_1桁月日(self):
        result = parse_gyomu_date(2025, "1月3日")
        assert result == pd.Timestamp(year=2025, month=1, day=3)

    # ========== 正常系: YYYY/M/D 形式 ==========

    def test_full形式_年が引数より優先される(self):
        """YYYY/M/D 形式では文字列の年を優先（year 引数は無視）"""
        result = parse_gyomu_date(2099, "2024/4/29")
        assert result == pd.Timestamp(year=2024, month=4, day=29)

    def test_full形式_2桁月日(self):
        result = parse_gyomu_date(None, "2025/12/31")
        assert result == pd.Timestamp(year=2025, month=12, day=31)

    # ========== year が int 以外 ==========

    def test_year_が文字列(self):
        """year が文字列でも int 化されればパース成功"""
        result = parse_gyomu_date("2025", "4/29")
        assert result == pd.Timestamp(year=2025, month=4, day=29)

    def test_year_が浮動小数(self):
        """year が float でも int 化"""
        result = parse_gyomu_date(2025.0, "4/29")
        assert result == pd.Timestamp(year=2025, month=4, day=29)

    # ========== 異常系: NaT 返却 ==========

    def test_None入力(self):
        assert pd.isna(parse_gyomu_date(2025, None))

    def test_空文字列(self):
        assert pd.isna(parse_gyomu_date(2025, ""))

    def test_空白のみ(self):
        assert pd.isna(parse_gyomu_date(2025, "   "))

    def test_NaN入力(self):
        assert pd.isna(parse_gyomu_date(2025, float("nan")))

    def test_year_None_かつ_md形式(self):
        """year が無く M/D だけでは年補完不能 → NaT"""
        assert pd.isna(parse_gyomu_date(None, "4/29"))

    def test_year_NaN_かつ_md形式(self):
        assert pd.isna(parse_gyomu_date(float("nan"), "4/29"))

    def test_year_不正文字列(self):
        """year が int 化できない → NaT"""
        assert pd.isna(parse_gyomu_date("abc", "4/29"))

    def test_全く不正なdate(self):
        assert pd.isna(parse_gyomu_date(2025, "xyz"))

    def test_不正な月日(self):
        """月日として無効（13月など）→ NaT"""
        assert pd.isna(parse_gyomu_date(2025, "13/1"))

    def test_存在しない日付(self):
        """2月30日など → NaT"""
        assert pd.isna(parse_gyomu_date(2025, "2/30"))

    def test_閏年の2月29日_成功(self):
        """閏年 (2024) の 2/29 は YYYY/M/D 形式で成功"""
        result = parse_gyomu_date(None, "2024/2/29")
        assert result == pd.Timestamp(year=2024, month=2, day=29)

    def test_非閏年の2月29日_NaT(self):
        """非閏年 (2025) の 2/29 → NaT"""
        assert pd.isna(parse_gyomu_date(2025, "2/29"))

    # ========== 末尾アンカーによる汚れデータ拒否 ==========

    def test_md形式の後ろにゴミ文字(self):
        """末尾アンカーで "4/29 abc" は受理しない"""
        assert pd.isna(parse_gyomu_date(2025, "4/29 abc"))

    def test_full形式の後ろにゴミ文字(self):
        """末尾アンカーで "2025/4/29foo" は受理しない"""
        assert pd.isna(parse_gyomu_date(None, "2025/4/29foo"))

    def test_jp形式の後ろにゴミ文字(self):
        """末尾アンカーで "4月29日(火)" は受理しない"""
        assert pd.isna(parse_gyomu_date(2025, "4月29日(火)"))

    # ========== ソート整合性: バグ再現の回帰テスト ==========

    def test_ソートが文字列でなく日付として動作する(self):
        """文字列ソートだと "4/29" が "4/7"/"4/15" より前に並んでしまうバグ
        (スクリーンショット報告) の回帰防止。Timestamp 化で正しい日付ソート
        になることを確認。
        """
        dates = ["4/7", "4/29", "4/3", "4/15"]
        df = pd.DataFrame({"year": [2025] * 4, "date": dates})
        df["dt"] = df.apply(
            lambda r: parse_gyomu_date(r["year"], r["date"]), axis=1
        )
        sorted_desc = df.sort_values("dt", ascending=False)["date"].tolist()
        assert sorted_desc == ["4/29", "4/15", "4/7", "4/3"]
        sorted_asc = df.sort_values("dt", ascending=True)["date"].tolist()
        assert sorted_asc == ["4/3", "4/7", "4/15", "4/29"]

    def test_月跨ぎソート(self):
        """1〜12月の混在で正しく日付順に並ぶこと。
        文字列ソートだと "11/15" < "12/31" < "1/3" となる回帰の防止。
        """
        dates = ["12/31", "1/3", "11/15", "5/20"]
        df = pd.DataFrame({"year": [2025] * 4, "date": dates})
        df["dt"] = df.apply(
            lambda r: parse_gyomu_date(r["year"], r["date"]), axis=1
        )
        sorted_asc = df.sort_values("dt", ascending=True)["date"].tolist()
        assert sorted_asc == ["1/3", "5/20", "11/15", "12/31"]


class TestAddGyomuDateDt:
    """add_gyomu_date_dt() のテスト

    DataFrame に date_dt 列を追加するヘルパ。dashboard.py の重複ロジックを集約。
    """

    def test_date_dt列が追加される(self):
        df = pd.DataFrame({"year": [2025, 2025], "date": ["4/29", "4/3"]})
        out = add_gyomu_date_dt(df)
        assert "date_dt" in out.columns
        assert out["date_dt"].iloc[0] == pd.Timestamp(year=2025, month=4, day=29)
        assert out["date_dt"].iloc[1] == pd.Timestamp(year=2025, month=4, day=3)

    def test_元のDataFrameは変更されない(self):
        """ヘルパは copy を返し、元の df に列を追加しない"""
        df = pd.DataFrame({"year": [2025], "date": ["4/29"]})
        add_gyomu_date_dt(df)
        assert "date_dt" not in df.columns

    def test_元のdate列は保持される(self):
        """date_dt 追加後も元の date 列（STRING）は残る"""
        df = pd.DataFrame({"year": [2025], "date": ["4/29"]})
        out = add_gyomu_date_dt(df)
        assert out["date"].iloc[0] == "4/29"

    def test_列名カスタマイズ(self):
        """col_name 引数で別名指定可能"""
        df = pd.DataFrame({"year": [2025], "date": ["4/29"]})
        out = add_gyomu_date_dt(df, col_name="my_dt")
        assert "my_dt" in out.columns
        assert out["my_dt"].iloc[0] == pd.Timestamp(year=2025, month=4, day=29)

    def test_空DataFrame(self):
        """空 DataFrame でもエラーなし、date_dt 列は追加される"""
        df = pd.DataFrame({"year": pd.Series([], dtype="Int64"), "date": pd.Series([], dtype=object)})
        out = add_gyomu_date_dt(df)
        assert "date_dt" in out.columns
        assert len(out) == 0

    def test_NaT行が混在(self):
        """パース失敗行は NaT、成功行はそのまま"""
        df = pd.DataFrame({"year": [2025, 2025, 2025], "date": ["4/29", "xyz", "4/1"]})
        out = add_gyomu_date_dt(df)
        assert out["date_dt"].iloc[0] == pd.Timestamp(year=2025, month=4, day=29)
        assert pd.isna(out["date_dt"].iloc[1])
        assert out["date_dt"].iloc[2] == pd.Timestamp(year=2025, month=4, day=1)

    def test_date_dt列がdatetime64型(self):
        """Streamlit DateColumn が認識するため datetime64 dtype であること"""
        df = pd.DataFrame({"year": [2025], "date": ["4/29"]})
        out = add_gyomu_date_dt(df)
        assert pd.api.types.is_datetime64_any_dtype(out["date_dt"])

    # ========== 観測性: パース失敗時のログ + UI warning ==========

    def test_全行成功時はwarningログ出ない(self, caplog, mock_streamlit):
        """全行パース成功なら WARNING ログも st.warning も出ない"""
        mock_streamlit.warning.reset_mock()
        df = pd.DataFrame({"year": [2025, 2025], "date": ["4/29", "4/1"]})
        with caplog.at_level("WARNING", logger="lib.ui_helpers"):
            add_gyomu_date_dt(df)
        assert not any("parse_gyomu_date failed" in r.message for r in caplog.records)
        mock_streamlit.warning.assert_not_called()

    def test_失敗行があればWARNINGログ(self, caplog, mock_streamlit):
        """1行でも失敗があれば logger.warning が呼ばれる"""
        mock_streamlit.warning.reset_mock()
        df = pd.DataFrame({"year": [2025] * 3, "date": ["4/29", "xyz", "4/1"]})
        with caplog.at_level("WARNING", logger="lib.ui_helpers"):
            add_gyomu_date_dt(df)
        assert any(
            "parse_gyomu_date failed" in r.message and "1/3" in r.message
            for r in caplog.records
        )

    def test_失敗率5パーセント以上でst_warning(self, mock_streamlit):
        """失敗率が閾値 (5%) 以上なら st.warning が呼ばれる"""
        mock_streamlit.warning.reset_mock()
        # 10 行中 1 行失敗 = 10% (>= 5%)
        df = pd.DataFrame(
            {"year": [2025] * 10, "date": ["4/29"] * 9 + ["xyz"]}
        )
        add_gyomu_date_dt(df)
        mock_streamlit.warning.assert_called_once()
        call_msg = mock_streamlit.warning.call_args[0][0]
        assert "1件" in call_msg
        assert "全10件" in call_msg

    def test_失敗率5パーセント未満ではst_warning呼ばれない(self, mock_streamlit):
        """失敗率が閾値未満なら ログのみ、UI warning なし"""
        mock_streamlit.warning.reset_mock()
        # 100 行中 1 行失敗 = 1% (< 5%)
        df = pd.DataFrame(
            {"year": [2025] * 100, "date": ["4/29"] * 99 + ["xyz"]}
        )
        add_gyomu_date_dt(df)
        mock_streamlit.warning.assert_not_called()

    def test_空DataFrameではログもwarningも出ない(self, caplog, mock_streamlit):
        """空 df では nat_count=0 のため何もログされない"""
        mock_streamlit.warning.reset_mock()
        df = pd.DataFrame(
            {"year": pd.Series([], dtype="Int64"), "date": pd.Series([], dtype=object)}
        )
        with caplog.at_level("WARNING", logger="lib.ui_helpers"):
            add_gyomu_date_dt(df)
        assert not any("parse_gyomu_date failed" in r.message for r in caplog.records)
        mock_streamlit.warning.assert_not_called()
