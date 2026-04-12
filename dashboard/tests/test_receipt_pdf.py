"""Unit tests for lib/receipt_pdf.py

支払明細書PDF生成ロジックのテスト。
フォントなし環境ではHelveticaフォールバック（日本語は文字化け、構造テストは通る）。
"""

from __future__ import annotations

import io
import zipfile

import pandas as pd
import pytest

from lib.receipt_pdf import (
    generate_all_statements_zip,
    generate_payment_statement,
)


# --- Fixtures ---

@pytest.fixture
def compensation():
    return {
        "qualification_adjusted_compensation": 100000.0,
        "withholding_tax": -10210.0,
        "dx_subsidy": 0.0,
        "reimbursement": 15000.0,
        "payment": 104790.0,
    }


@pytest.fixture
def reimbursement_items():
    return pd.DataFrame({
        "date": ["3月20日", "3月22日"],
        "target_project": ["ケアプーPJ", "経産省PJ"],
        "category": ["旅費交通費", "個人立替費"],
        "payment_purpose": ["新幹線代", "宿泊費"],
        "payment_amount_numeric": [10000.0, 5000.0],
        "receipt_url": ["https://drive.google.com/file/d/abc", ""],
    })


@pytest.fixture
def comp_df_multi():
    return pd.DataFrame({
        "year": [2026, 2026],
        "month": [4, 4],
        "nickname": ["太郎", "花子"],
        "full_name": ["山田太郎", "鈴木花子"],
        "qualification_adjusted_compensation": [100000.0, 50000.0],
        "withholding_tax": [-10210.0, -5105.0],
        "dx_subsidy": [0.0, 5000.0],
        "reimbursement": [15000.0, 0.0],
        "payment": [104790.0, 49895.0],
    })


@pytest.fixture
def reimb_df_multi():
    return pd.DataFrame({
        "nickname": ["太郎", "太郎", "花子"],
        "normalized_year": [2026, 2026, 2026],
        "month": [4, 4, 4],
        "date": ["3月20日", "3月22日", "4月1日"],
        "target_project": ["ケアプーPJ", "経産省PJ", "神奈川県PJ"],
        "category": ["旅費交通費", "個人立替費", "旅費交通費"],
        "payment_purpose": ["新幹線代", "宿泊費", "バス代"],
        "payment_amount_numeric": [10000.0, 5000.0, 3000.0],
        "receipt_url": ["https://drive.google.com/1", "", "https://drive.google.com/3"],
    })


# --- generate_payment_statement ---

class TestGeneratePaymentStatement:
    def test_returns_bytes(self, compensation, reimbursement_items):
        result = generate_payment_statement(
            member_name="太郎",
            full_name="山田太郎",
            year=2026,
            month=4,
            compensation=compensation,
            reimbursement_items=reimbursement_items,
        )
        assert isinstance(result, bytes)
        assert len(result) > 0

    def test_pdf_header(self, compensation, reimbursement_items):
        result = generate_payment_statement(
            member_name="太郎",
            full_name="山田太郎",
            year=2026,
            month=4,
            compensation=compensation,
            reimbursement_items=reimbursement_items,
        )
        assert result[:5] == b"%PDF-"

    def test_empty_reimbursement(self, compensation):
        empty_items = pd.DataFrame(columns=[
            "date", "target_project", "category", "payment_purpose",
            "payment_amount_numeric", "receipt_url",
        ])
        result = generate_payment_statement(
            member_name="太郎",
            full_name="山田太郎",
            year=2026,
            month=4,
            compensation=compensation,
            reimbursement_items=empty_items,
        )
        assert isinstance(result, bytes)
        assert result[:5] == b"%PDF-"

    def test_zero_compensation(self, reimbursement_items):
        zero_comp = {
            "qualification_adjusted_compensation": 0.0,
            "withholding_tax": 0.0,
            "dx_subsidy": 0.0,
            "reimbursement": 15000.0,
            "payment": 15000.0,
        }
        result = generate_payment_statement(
            member_name="太郎",
            full_name="山田太郎",
            year=2026,
            month=4,
            compensation=zero_comp,
            reimbursement_items=reimbursement_items,
        )
        assert isinstance(result, bytes)
        assert len(result) > 0

    def test_missing_receipt_urls(self, compensation):
        items = pd.DataFrame({
            "date": ["3月20日"],
            "target_project": ["ケアプーPJ"],
            "category": ["旅費交通費"],
            "payment_purpose": ["新幹線代"],
            "payment_amount_numeric": [10000.0],
            "receipt_url": [None],
        })
        result = generate_payment_statement(
            member_name="太郎",
            full_name="山田太郎",
            year=2026,
            month=4,
            compensation=compensation,
            reimbursement_items=items,
        )
        assert isinstance(result, bytes)


# --- generate_all_statements_zip ---

class TestGenerateAllStatementsZip:
    def test_returns_valid_zip(self, comp_df_multi, reimb_df_multi):
        result = generate_all_statements_zip(
            members_comp=comp_df_multi,
            reimbursement_df=reimb_df_multi,
            year=2026,
            month=4,
        )
        assert isinstance(result, bytes)
        zf = zipfile.ZipFile(io.BytesIO(result))
        assert len(zf.namelist()) == 2  # 太郎 + 花子

    def test_zip_file_names(self, comp_df_multi, reimb_df_multi):
        result = generate_all_statements_zip(
            members_comp=comp_df_multi,
            reimbursement_df=reimb_df_multi,
            year=2026,
            month=4,
        )
        zf = zipfile.ZipFile(io.BytesIO(result))
        names = sorted(zf.namelist())
        assert all(name.endswith(".pdf") for name in names)
        assert all("2026_04" in name for name in names)

    def test_empty_comp_returns_empty_zip(self):
        empty_comp = pd.DataFrame(columns=[
            "year", "month", "nickname", "full_name",
            "qualification_adjusted_compensation", "withholding_tax",
            "dx_subsidy", "reimbursement", "payment",
        ])
        empty_reimb = pd.DataFrame(columns=[
            "nickname", "normalized_year", "month", "date",
            "target_project", "category", "payment_purpose",
            "payment_amount_numeric", "receipt_url",
        ])
        result = generate_all_statements_zip(
            members_comp=empty_comp,
            reimbursement_df=empty_reimb,
            year=2026,
            month=4,
        )
        assert isinstance(result, bytes)
        zf = zipfile.ZipFile(io.BytesIO(result))
        assert len(zf.namelist()) == 0

    def test_member_without_reimbursement(self, comp_df_multi):
        # 花子には立替明細なし
        reimb_only_taro = pd.DataFrame({
            "nickname": ["太郎", "太郎"],
            "normalized_year": [2026, 2026],
            "month": [4, 4],
            "date": ["3月20日", "3月22日"],
            "target_project": ["ケアプーPJ", "経産省PJ"],
            "category": ["旅費交通費", "個人立替費"],
            "payment_purpose": ["新幹線代", "宿泊費"],
            "payment_amount_numeric": [10000.0, 5000.0],
            "receipt_url": ["https://a.com", ""],
        })
        result = generate_all_statements_zip(
            members_comp=comp_df_multi,
            reimbursement_df=reimb_only_taro,
            year=2026,
            month=4,
        )
        zf = zipfile.ZipFile(io.BytesIO(result))
        assert len(zf.namelist()) == 2  # 花子も空明細で生成される

    def test_each_pdf_is_valid(self, comp_df_multi, reimb_df_multi):
        result = generate_all_statements_zip(
            members_comp=comp_df_multi,
            reimbursement_df=reimb_df_multi,
            year=2026,
            month=4,
        )
        zf = zipfile.ZipFile(io.BytesIO(result))
        for name in zf.namelist():
            pdf_bytes = zf.read(name)
            assert pdf_bytes[:5] == b"%PDF-"
