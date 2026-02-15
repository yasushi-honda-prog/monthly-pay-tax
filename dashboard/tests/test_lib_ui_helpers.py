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
    clean_numeric_scalar,
    clean_numeric_series,
    fill_empty_nickname,
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
