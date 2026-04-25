"""Unit tests for pages/wam_monthly.py

集計・フィルタ・領収書統計ロジックのテスト。
モジュールレベルのStreamlit実行を回避するため、関数を直接定義してテスト。
"""

from __future__ import annotations

import pandas as pd
import pytest


# --- テスト対象の関数を直接定義（モジュールレベルSt実行回避） ---

def _filter_by_year_month(df: pd.DataFrame, year: int, month: int) -> pd.DataFrame:
    return df[(df["normalized_year"] == year) & (df["month"] == month)]


def _summarize_by_project(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame(columns=["対象PJ", "件数", "支払金額合計", "仮払金額合計"])
    summary = df.groupby("target_project", dropna=False).agg(
        件数=("payment_amount_numeric", "size"),
        支払金額合計=("payment_amount_numeric", "sum"),
        仮払金額合計=("advance_amount_numeric", "sum"),
    ).reset_index()
    summary.rename(columns={"target_project": "対象PJ"}, inplace=True)
    summary["対象PJ"] = summary["対象PJ"].fillna("(未設定)")
    return summary.sort_values("支払金額合計", ascending=False)


def _is_receipt_attached(series: pd.Series) -> pd.Series:
    return series.notna() & (series.str.strip() != "")


def _receipt_stats(df: pd.DataFrame) -> dict:
    total = len(df)
    if total == 0:
        return {"total": 0, "attached": 0, "missing": 0, "rate": 0.0}
    n_attached = int(_is_receipt_attached(df["receipt_url"]).sum())
    return {
        "total": total,
        "attached": n_attached,
        "missing": total - n_attached,
        "rate": n_attached / total * 100,
    }


# --- Fixtures ---

@pytest.fixture
def sample_df():
    return pd.DataFrame({
        "source_url": ["url1", "url2", "url3", "url4", "url5"],
        "nickname": ["太郎", "花子", "太郎", "次郎", "花子"],
        "normalized_year": [2026, 2026, 2026, 2025, 2026],
        "month": [4, 4, 3, 4, 4],
        "target_project": ["ケアプーPJ", "神奈川県PJ", "ケアプーPJ", "経産省PJ", None],
        "category": ["旅費", "物品", "旅費", "旅費", "物品"],
        "payment_purpose": ["出張", "購入", "出張", "出張", "購入"],
        "payment_amount": ["¥10,000", "¥5,000", "¥8,000", "¥3,000", "¥2,000"],
        "payment_amount_numeric": [10000.0, 5000.0, 8000.0, 3000.0, 2000.0],
        "advance_amount": [None, None, "¥5,000", None, None],
        "advance_amount_numeric": [0.0, 0.0, 5000.0, 0.0, 0.0],
        "from_station": ["東京", None, "横浜", "新宿", None],
        "to_station": ["大阪", None, "名古屋", "池袋", None],
        "visit_purpose": ["訪問", None, "訪問", "訪問", None],
        "receipt_url": ["https://example.com/1", "", "https://example.com/3", None, "https://example.com/5"],
    })


# --- _filter_by_year_month ---

class TestFilterByYearMonth:
    def test_filters_correctly(self, sample_df):
        result = _filter_by_year_month(sample_df, 2026, 4)
        assert len(result) == 3
        assert set(result["nickname"]) == {"太郎", "花子"}

    def test_no_match(self, sample_df):
        result = _filter_by_year_month(sample_df, 2024, 1)
        assert len(result) == 0

    def test_different_year(self, sample_df):
        result = _filter_by_year_month(sample_df, 2025, 4)
        assert len(result) == 1
        assert result.iloc[0]["nickname"] == "次郎"

    def test_different_month(self, sample_df):
        result = _filter_by_year_month(sample_df, 2026, 3)
        assert len(result) == 1


# --- _summarize_by_project ---

class TestSummarizeByProject:
    def test_basic_summary(self, sample_df):
        filtered = _filter_by_year_month(sample_df, 2026, 4)
        summary = _summarize_by_project(filtered)
        assert len(summary) == 3  # ケアプーPJ, 神奈川県PJ, (未設定)
        care = summary[summary["対象PJ"] == "ケアプーPJ"]
        assert care["件数"].values[0] == 1
        assert care["支払金額合計"].values[0] == 10000.0

    def test_empty_df(self):
        empty = pd.DataFrame(columns=["target_project", "payment_amount_numeric", "advance_amount_numeric"])
        summary = _summarize_by_project(empty)
        assert len(summary) == 0
        assert "対象PJ" in summary.columns

    def test_null_project_becomes_unset(self, sample_df):
        filtered = _filter_by_year_month(sample_df, 2026, 4)
        summary = _summarize_by_project(filtered)
        assert "(未設定)" in summary["対象PJ"].values

    def test_sorted_by_amount_desc(self, sample_df):
        filtered = _filter_by_year_month(sample_df, 2026, 4)
        summary = _summarize_by_project(filtered)
        amounts = summary["支払金額合計"].tolist()
        assert amounts == sorted(amounts, reverse=True)


# --- _receipt_stats ---

class TestReceiptStats:
    def test_basic_stats(self, sample_df):
        filtered = _filter_by_year_month(sample_df, 2026, 4)
        stats = _receipt_stats(filtered)
        assert stats["total"] == 3
        # url1=有, url2=空文字(無), url5=有
        assert stats["attached"] == 2
        assert stats["missing"] == 1
        assert 60.0 < stats["rate"] < 70.0

    def test_empty_df(self):
        empty = pd.DataFrame(columns=["receipt_url"])
        stats = _receipt_stats(empty)
        assert stats["total"] == 0
        assert stats["rate"] == 0.0

    def test_all_attached(self):
        df = pd.DataFrame({"receipt_url": ["https://a.com", "https://b.com"]})
        stats = _receipt_stats(df)
        assert stats["attached"] == 2
        assert stats["rate"] == 100.0

    def test_none_attached(self):
        df = pd.DataFrame({"receipt_url": [None, "", "  "]})
        stats = _receipt_stats(df)
        assert stats["attached"] == 0
        assert stats["missing"] == 3


# --- WAMフィルタ ---

class TestWamFilter:
    def test_filter_wam_only(self):
        df = pd.DataFrame({
            "normalized_year": [2026, 2026, 2026],
            "month": [4, 4, 4],
            "is_wam": [True, False, True],
            "payment_amount_numeric": [10000.0, 5000.0, 3000.0],
        })
        filtered = df[df["is_wam"] == True]  # noqa: E712
        assert len(filtered) == 2
        assert filtered["payment_amount_numeric"].sum() == 13000.0

    def test_filter_wam_all_false(self):
        df = pd.DataFrame({
            "is_wam": [False, False, False],
            "payment_amount_numeric": [10000.0, 5000.0, 3000.0],
        })
        filtered = df[df["is_wam"] == True]  # noqa: E712
        assert len(filtered) == 0

    def test_filter_wam_missing_column(self):
        """is_wamカラムがない場合はフィルタしない"""
        df = pd.DataFrame({
            "payment_amount_numeric": [10000.0, 5000.0],
        })
        # is_wamカラムがなければフィルタをスキップ（アプリの動作と同じ）
        if "is_wam" in df.columns:
            df = df[df["is_wam"] == True]  # noqa: E712
        assert len(df) == 2


# --- 報酬データ関連 ---

def _filter_comp_by_year_month(df: pd.DataFrame, year: int, month: int) -> pd.DataFrame:
    return df[(df["year"] == year) & (df["month"] == month)]


def _summarize_compensation(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame(columns=[
            "メンバー", "報酬", "源泉徴収", "DX補助", "立替", "支払額",
        ])
    summary = df[["nickname", "qualification_adjusted_compensation",
                   "withholding_tax", "dx_subsidy", "reimbursement", "payment"]].copy()
    summary = summary.rename(columns={
        "nickname": "メンバー",
        "qualification_adjusted_compensation": "報酬",
        "withholding_tax": "源泉徴収",
        "dx_subsidy": "DX補助",
        "reimbursement": "立替",
        "payment": "支払額",
    })
    return summary.sort_values("支払額", ascending=False, na_position="last")


@pytest.fixture
def comp_df():
    return pd.DataFrame({
        "year": [2026, 2026, 2026, 2025],
        "month": [4, 4, 3, 4],
        "nickname": ["太郎", "花子", "太郎", "次郎"],
        "qualification_adjusted_compensation": [100000.0, 50000.0, 80000.0, 30000.0],
        "withholding_tax": [-10210.0, -5105.0, -8168.0, -3063.0],
        "dx_subsidy": [0.0, 5000.0, 0.0, 0.0],
        "reimbursement": [10000.0, 0.0, 5000.0, 3000.0],
        "payment": [99790.0, 49895.0, 76832.0, 29937.0],
    })


class TestFilterCompByYearMonth:
    def test_filters_correctly(self, comp_df):
        result = _filter_comp_by_year_month(comp_df, 2026, 4)
        assert len(result) == 2
        assert set(result["nickname"]) == {"太郎", "花子"}

    def test_no_match(self, comp_df):
        result = _filter_comp_by_year_month(comp_df, 2024, 1)
        assert len(result) == 0


class TestSummarizeCompensation:
    def test_basic_summary(self, comp_df):
        filtered = _filter_comp_by_year_month(comp_df, 2026, 4)
        summary = _summarize_compensation(filtered)
        assert len(summary) == 2
        assert "メンバー" in summary.columns
        assert "報酬" in summary.columns
        assert "支払額" in summary.columns

    def test_empty_df(self):
        empty = pd.DataFrame(columns=[
            "nickname", "qualification_adjusted_compensation",
            "withholding_tax", "dx_subsidy", "reimbursement", "payment",
        ])
        summary = _summarize_compensation(empty)
        assert len(summary) == 0
        assert "メンバー" in summary.columns

    def test_sorted_by_payment_desc(self, comp_df):
        filtered = _filter_comp_by_year_month(comp_df, 2026, 4)
        summary = _summarize_compensation(filtered)
        payments = summary["支払額"].tolist()
        assert payments == sorted(payments, reverse=True)


# --- 振込CSV生成 ---

def _safe_str(val) -> str:
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return ""
    s = str(val).strip()
    return "" if s == "nan" else s


def _deposit_type_code(deposit_type: str) -> str:
    mapping = {"普通": "1", "当座": "2", "貯蓄": "4"}
    return mapping.get(deposit_type.strip(), "1") if deposit_type.strip() else "1"


def _generate_transfer_csv(df: pd.DataFrame, df_bank: pd.DataFrame) -> bytes:
    if df.empty:
        return b""
    target = df[df["payment"].notna() & (df["payment"] > 0)].copy()
    if target.empty:
        return b""
    if not df_bank.empty:
        target = target.merge(df_bank, on="report_url", how="left")
    rows = []
    for _, r in target.iterrows():
        amount = int(r["payment"])
        bank_code = _safe_str(r.get("bank_code"))
        branch_code = _safe_str(r.get("branch_code"))
        deposit_type = _deposit_type_code(_safe_str(r.get("deposit_type")))
        account_number = _safe_str(r.get("account_number"))
        holder_name = _safe_str(r.get("holder_name")) or _safe_str(r.get("full_name")) or _safe_str(r.get("nickname"))
        rows.append(f"{bank_code},{branch_code},{deposit_type},{account_number},{holder_name},{amount},,")
    return "\n".join(rows).encode("shift_jis", errors="replace")


@pytest.fixture
def bank_df():
    """口座情報のDataFrame"""
    return pd.DataFrame({
        "report_url": ["url_taro", "url_hanako"],
        "bank_code": ["0310", "0033"],
        "branch_code": ["101", "001"],
        "deposit_type": ["普通", "普通"],
        "account_number": ["1234567", "7654321"],
        "holder_name": ["タナカ タロウ", "ハナコ"],
    })


@pytest.fixture
def comp_df_with_url():
    """report_url付きの報酬DataFrame"""
    return pd.DataFrame({
        "year": [2026, 2026],
        "month": [4, 4],
        "nickname": ["太郎", "花子"],
        "full_name": ["田中太郎", "鈴木花子"],
        "report_url": ["url_taro", "url_hanako"],
        "qualification_adjusted_compensation": [100000.0, 50000.0],
        "withholding_tax": [-10210.0, -5105.0],
        "dx_subsidy": [0.0, 5000.0],
        "reimbursement": [10000.0, 0.0],
        "payment": [99790.0, 49895.0],
    })


class TestGenerateTransferCsv:
    def test_basic_csv_without_bank(self, comp_df):
        """口座データなしでも動作すること（フォールバック）"""
        comp_df["report_url"] = ["url1", "url2", "url3", "url4"]
        filtered = _filter_comp_by_year_month(comp_df, 2026, 4)
        csv_bytes = _generate_transfer_csv(filtered, pd.DataFrame())
        csv_text = csv_bytes.decode("shift_jis")
        lines = csv_text.strip().split("\n")
        assert len(lines) == 2
        for line in lines:
            assert line.count(",") == 7
        assert "99790" in csv_text
        assert "49895" in csv_text

    def test_empty_df(self):
        empty = pd.DataFrame(columns=["payment", "full_name", "nickname", "report_url"])
        assert _generate_transfer_csv(empty, pd.DataFrame()) == b""

    def test_zero_payment_excluded(self):
        df = pd.DataFrame({
            "payment": [0.0, 50000.0, None],
            "full_name": ["A", "B", "C"],
            "nickname": ["a", "b", "c"],
            "report_url": ["u1", "u2", "u3"],
        })
        csv_bytes = _generate_transfer_csv(df, pd.DataFrame())
        csv_text = csv_bytes.decode("shift_jis")
        lines = csv_text.strip().split("\n")
        assert len(lines) == 1
        assert "50000" in csv_text

    def test_bank_data_merged(self, comp_df_with_url, bank_df):
        """口座データがCSVに反映されること"""
        csv_bytes = _generate_transfer_csv(comp_df_with_url, bank_df)
        csv_text = csv_bytes.decode("shift_jis")
        lines = csv_text.strip().split("\n")
        assert len(lines) == 2
        # 太郎: 0310,101,1(普通),1234567,タナカ タロウ,99790,,
        taro_line = [l for l in lines if "99790" in l][0]
        fields = taro_line.split(",")
        assert fields[0] == "0310"       # bank_code
        assert fields[1] == "101"        # branch_code
        assert fields[2] == "1"          # deposit_type (普通→1)
        assert fields[3] == "1234567"    # account_number
        assert fields[4] == "タナカ タロウ"  # holder_name

    def test_unmatched_member_gets_empty_bank(self, bank_df):
        """口座マスタにないメンバーは口座欄が空になること"""
        df = pd.DataFrame({
            "payment": [30000.0],
            "full_name": ["新人"],
            "nickname": ["しんじん"],
            "report_url": ["url_unknown"],
        })
        csv_bytes = _generate_transfer_csv(df, bank_df)
        csv_text = csv_bytes.decode("shift_jis")
        line = csv_text.strip()
        fields = line.split(",")
        assert fields[0] == ""           # bank_code 空
        assert fields[1] == ""           # branch_code 空
        assert fields[3] == ""           # account_number 空
        assert fields[4] == "新人"       # full_name フォールバック
        assert fields[5] == "30000"

    def test_holder_name_preferred_over_full_name(self, comp_df_with_url, bank_df):
        """holder_nameがある場合はfull_nameよりholder_nameを使うこと"""
        csv_bytes = _generate_transfer_csv(comp_df_with_url, bank_df)
        csv_text = csv_bytes.decode("shift_jis")
        assert "タナカ タロウ" in csv_text
        assert "田中太郎" not in csv_text  # full_nameは使われない


class TestDepositTypeCode:
    def test_futsu(self):
        assert _deposit_type_code("普通") == "1"

    def test_toza(self):
        assert _deposit_type_code("当座") == "2"

    def test_chochiku(self):
        assert _deposit_type_code("貯蓄") == "4"

    def test_empty(self):
        assert _deposit_type_code("") == "1"

    def test_unknown_defaults_to_1(self):
        assert _deposit_type_code("その他") == "1"

    def test_with_whitespace(self):
        assert _deposit_type_code("  普通  ") == "1"


# --- 年間支払調書データ ---

def _build_annual_withholding_data(
    df_comp_all: pd.DataFrame, year: int, df_member: pd.DataFrame
) -> pd.DataFrame:
    df_year = df_comp_all[df_comp_all["year"] == year].copy()
    if df_year.empty:
        return pd.DataFrame()
    agg = df_year.groupby(["report_url", "nickname", "full_name"], dropna=False).agg(
        年間報酬=("qualification_adjusted_compensation", "sum"),
        年間源泉徴収=("withholding_tax", "sum"),
        年間DX補助=("dx_subsidy", "sum"),
        年間立替=("reimbursement", "sum"),
        年間支払額=("payment", "sum"),
    ).reset_index()
    if not df_member.empty:
        agg = agg.merge(df_member, on="report_url", how="left")
    return agg.sort_values("年間支払額", ascending=False, na_position="last")


def _generate_withholding_csv(df: pd.DataFrame) -> bytes:
    if df.empty:
        return b""
    cols = [
        "member_id", "last_name", "first_name", "last_name_kana", "first_name_kana",
        "postal_code", "prefecture", "address",
        "nickname", "full_name",
        "年間報酬", "年間源泉徴収", "年間DX補助", "年間立替", "年間支払額",
    ]
    out = df[[c for c in cols if c in df.columns]].copy()
    csv_str = out.to_csv(index=False)
    return b"\xef\xbb\xbf" + csv_str.encode("utf-8")


@pytest.fixture
def annual_comp_df():
    """年間報酬データ（複数月）"""
    return pd.DataFrame({
        "year": [2026, 2026, 2026, 2026, 2025],
        "month": [1, 2, 1, 2, 12],
        "nickname": ["太郎", "太郎", "花子", "花子", "太郎"],
        "full_name": ["田中太郎", "田中太郎", "鈴木花子", "鈴木花子", "田中太郎"],
        "report_url": ["url_t", "url_t", "url_h", "url_h", "url_t"],
        "qualification_adjusted_compensation": [100000.0, 120000.0, 50000.0, 60000.0, 80000.0],
        "withholding_tax": [-10210.0, -12252.0, -5105.0, -6126.0, -8168.0],
        "dx_subsidy": [0.0, 0.0, 5000.0, 3000.0, 0.0],
        "reimbursement": [10000.0, 0.0, 0.0, 2000.0, 5000.0],
        "payment": [99790.0, 107748.0, 49895.0, 58874.0, 76832.0],
    })


@pytest.fixture
def member_info_df():
    """member_master氏名・住所データ"""
    return pd.DataFrame({
        "report_url": ["url_t", "url_h"],
        "member_id": ["TM001", "TM002"],
        "last_name": ["田中", "鈴木"],
        "first_name": ["太郎", "花子"],
        "last_name_kana": ["タナカ", "スズキ"],
        "first_name_kana": ["タロウ", "ハナコ"],
        "postal_code": ["100-0001", "200-0002"],
        "prefecture": ["東京都", "神奈川県"],
        "address": ["千代田区1-1", "横浜市2-2"],
    })


class TestBuildAnnualWithholdingData:
    def test_aggregates_by_year(self, annual_comp_df, member_info_df):
        """年間集計が正しいこと"""
        result = _build_annual_withholding_data(annual_comp_df, 2026, member_info_df)
        assert len(result) == 2  # 太郎 + 花子
        taro = result[result["nickname"] == "太郎"].iloc[0]
        assert taro["年間報酬"] == 220000.0  # 100000 + 120000
        assert taro["年間源泉徴収"] == -22462.0  # -10210 + -12252
        assert taro["年間支払額"] == 207538.0  # 99790 + 107748

    def test_member_info_joined(self, annual_comp_df, member_info_df):
        """member_masterの氏名・住所がJOINされること"""
        result = _build_annual_withholding_data(annual_comp_df, 2026, member_info_df)
        taro = result[result["nickname"] == "太郎"].iloc[0]
        assert taro["last_name"] == "田中"
        assert taro["postal_code"] == "100-0001"
        assert taro["address"] == "千代田区1-1"

    def test_no_data_for_year(self, annual_comp_df, member_info_df):
        """対象年のデータがない場合は空DataFrame"""
        result = _build_annual_withholding_data(annual_comp_df, 2024, member_info_df)
        assert result.empty

    def test_without_member_info(self, annual_comp_df):
        """member_infoなしでも集計は動作すること"""
        result = _build_annual_withholding_data(annual_comp_df, 2026, pd.DataFrame())
        assert len(result) == 2
        assert "last_name" not in result.columns

    def test_sorted_by_payment_desc(self, annual_comp_df, member_info_df):
        """支払額降順でソートされること"""
        result = _build_annual_withholding_data(annual_comp_df, 2026, member_info_df)
        payments = result["年間支払額"].tolist()
        assert payments == sorted(payments, reverse=True)


class TestGenerateWithholdingCsv:
    def test_basic_csv(self, annual_comp_df, member_info_df):
        """CSVが正しく生成されること"""
        df = _build_annual_withholding_data(annual_comp_df, 2026, member_info_df)
        csv_bytes = _generate_withholding_csv(df)
        assert csv_bytes[:3] == b"\xef\xbb\xbf"  # BOM
        csv_text = csv_bytes[3:].decode("utf-8")
        assert "member_id" in csv_text
        assert "田中" in csv_text
        assert "220000" in csv_text

    def test_empty(self):
        assert _generate_withholding_csv(pd.DataFrame()) == b""

    def test_without_member_columns(self, annual_comp_df):
        """member_info未JOINでもCSV生成できること"""
        df = _build_annual_withholding_data(annual_comp_df, 2026, pd.DataFrame())
        csv_bytes = _generate_withholding_csv(df)
        csv_text = csv_bytes[3:].decode("utf-8")
        assert "nickname" in csv_text
        assert "member_id" not in csv_text  # JOINされていないので含まれない


# --- Tab2 メンバー別明細: URL/領収書リンク列の構築ロジック ---

_TAB2_CSV_COLS = [
    "nickname", "date", "target_project", "is_wam", "category",
    "payment_purpose", "payment_amount", "advance_amount",
    "from_station", "to_station", "visit_purpose",
]
_TAB2_DISPLAY_COLS = _TAB2_CSV_COLS + ["source_url", "receipt_url"]
_TAB2_COL_LABELS = {
    "nickname": "メンバー", "date": "月日", "target_project": "対象PJ",
    "is_wam": "WAM対象", "category": "分類", "payment_purpose": "支払用途",
    "payment_amount": "支払金額", "advance_amount": "仮払金額",
    "from_station": "発", "to_station": "着", "visit_purpose": "訪問目的",
    "source_url": "URL", "receipt_url": "領収書",
}


def _build_tab2_display_df(df_detail: pd.DataFrame) -> pd.DataFrame:
    # wam_monthly.py Tab2 の表示用DF構築ロジックを抽出（モジュールレベルSt実行回避のため）
    existing = [c for c in _TAB2_DISPLAY_COLS if c in df_detail.columns]
    df_display = df_detail[existing].rename(columns=_TAB2_COL_LABELS).copy()
    for url_col in ("URL", "領収書"):
        if url_col in df_display.columns:
            df_display[url_col] = df_display[url_col].apply(_safe_str)
    return df_display


def _build_tab2_csv_df(df_detail: pd.DataFrame) -> pd.DataFrame:
    # wam_monthly.py Tab2 の CSV用DF構築ロジックを抽出（モジュールレベルSt実行回避のため）
    existing = [c for c in _TAB2_CSV_COLS if c in df_detail.columns]
    return df_detail[existing].rename(columns=_TAB2_COL_LABELS)


class TestTab2DisplayDf:
    def test_url_column_renamed(self, sample_df):
        result = _build_tab2_display_df(sample_df)
        assert "URL" in result.columns
        assert "source_url" not in result.columns

    def test_receipt_column_renamed(self, sample_df):
        result = _build_tab2_display_df(sample_df)
        assert "領収書" in result.columns
        assert "receipt_url" not in result.columns

    def test_url_normalized_for_nan_none_empty_nan_string(self):
        """NaN/None/空文字/'nan'/空白のみ のURLが空文字になる"""
        df = pd.DataFrame({
            "nickname": ["A", "B", "C", "D", "E", "F"],
            "date": ["1/1", "1/2", "1/3", "1/4", "1/5", "1/6"],
            "source_url": [
                "https://example.com/1",  # 正常URL
                None,                      # None
                "",                        # 空文字
                "nan",                     # "nan" 文字列
                float("nan"),              # NaN
                "  ",                      # 空白のみ
            ],
            "receipt_url": [
                None,                      # None
                "https://example.com/r2", # 正常URL
                "  ",                      # 空白のみ
                "nan",                     # "nan" 文字列
                "",                        # 空文字
                float("nan"),              # NaN
            ],
        })
        result = _build_tab2_display_df(df)
        # URL列の正規化確認
        assert result.iloc[0]["URL"] == "https://example.com/1"
        assert result.iloc[1]["URL"] == ""
        assert result.iloc[2]["URL"] == ""
        assert result.iloc[3]["URL"] == ""
        assert result.iloc[4]["URL"] == ""
        assert result.iloc[5]["URL"] == ""
        # 領収書列の正規化確認
        assert result.iloc[0]["領収書"] == ""
        assert result.iloc[1]["領収書"] == "https://example.com/r2"
        assert result.iloc[2]["領収書"] == ""
        assert result.iloc[3]["領収書"] == ""
        assert result.iloc[4]["領収書"] == ""
        assert result.iloc[5]["領収書"] == ""

    def test_missing_url_columns_no_error(self):
        """source_url / receipt_url がないDFでもエラーにならない"""
        df = pd.DataFrame({"nickname": ["A"], "date": ["1/1"]})
        result = _build_tab2_display_df(df)
        assert "URL" not in result.columns
        assert "領収書" not in result.columns
        assert "メンバー" in result.columns


class TestTab2CsvDf:
    def test_url_columns_excluded_from_csv(self, sample_df):
        # CSV は既存仕様維持のため URL/領収書 列を含めない
        result = _build_tab2_csv_df(sample_df)
        assert "URL" not in result.columns
        assert "領収書" not in result.columns
        assert "source_url" not in result.columns
        assert "receipt_url" not in result.columns

    def test_csv_existing_columns_preserved(self, sample_df):
        # 既存のCSV列構成が維持される（sample_dfに含まれる列のみ）
        result = _build_tab2_csv_df(sample_df)
        for orig_col in _TAB2_CSV_COLS:
            if orig_col in sample_df.columns:
                assert _TAB2_COL_LABELS[orig_col] in result.columns

    def test_display_df_column_order_stable(self, sample_df):
        # 表示用DFの列順がリファクタで崩れないことを担保（CSV列 → URL → 領収書）
        result = _build_tab2_display_df(sample_df)
        actual = list(result.columns)
        expected_csv_labels = [
            _TAB2_COL_LABELS[c] for c in _TAB2_CSV_COLS if c in sample_df.columns
        ]
        url_labels = [
            _TAB2_COL_LABELS[c]
            for c in ("source_url", "receipt_url")
            if c in sample_df.columns
        ]
        assert actual == expected_csv_labels + url_labels
