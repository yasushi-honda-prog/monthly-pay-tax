"""支払明細書PDF生成モジュール

メンバー×月ごとの支払明細書（業務委託費 + 立替経費）をPDFで出力する。
WAM助成金の証拠書類として使用。
"""

from __future__ import annotations

import io
import logging
import zipfile
from pathlib import Path

import pandas as pd
from fpdf import FPDF

logger = logging.getLogger(__name__)

# --- フォント探索 ---
_FONT_SEARCH_PATHS = [
    # Docker (fonts-noto-cjk)
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    # macOS
    "/System/Library/Fonts/ヒラギノ角ゴシック W3.ttc",
    "/System/Library/Fonts/ヒラギノ角ゴシック W4.ttc",
    "/System/Library/Fonts/ヒラギノ角ゴシック W6.ttc",
    "/Library/Fonts/Arial Unicode.ttf",
]


def _find_japanese_font() -> str | None:
    """日本語フォントのパスを返す。見つからなければNone。"""
    for p in _FONT_SEARCH_PATHS:
        if Path(p).exists():
            return p
    return None


# --- PDF生成 ---

def _fmt_yen(amount: float) -> str:
    """金額を ¥XX,XXX 形式にフォーマット"""
    if amount < 0:
        return f"-¥{abs(amount):,.0f}"
    return f"¥{amount:,.0f}"


class _StatementPDF(FPDF):
    """支払明細書用のカスタムPDFクラス"""

    def __init__(self):
        super().__init__(orientation="P", unit="mm", format="A4")
        self._has_jp_font = False
        font_path = _find_japanese_font()
        if font_path:
            try:
                self.add_font("jp", "", font_path)
                self.add_font("jp", "B", font_path)
                self._has_jp_font = True
            except Exception:
                logger.warning("日本語フォント読み込み失敗: %s", font_path)
        self.add_page()
        self.set_auto_page_break(auto=True, margin=15)

    def _set_font(self, style: str = "", size: int = 10):
        family = "jp" if self._has_jp_font else "Helvetica"
        self.set_font(family, style, size)

    def _draw_header(self, year: int, month: int):
        self._set_font("B", 16)
        self.cell(0, 12, "支 払 明 細 書", align="C", new_x="LMARGIN", new_y="NEXT")
        self._set_font("", 11)
        self.cell(0, 8, f"{year}年{month}月分", align="C", new_x="LMARGIN", new_y="NEXT")
        self.ln(4)

    def _draw_member_info(self, full_name: str, member_name: str):
        self._set_font("", 11)
        label = full_name if full_name and full_name != member_name else member_name
        if full_name and full_name != member_name:
            label += f" ({member_name})"
        self.cell(0, 8, f"支払先: {label}", new_x="LMARGIN", new_y="NEXT")
        self.ln(2)

    def _draw_section_title(self, title: str):
        self._set_font("B", 11)
        self.set_fill_color(230, 230, 230)
        self.cell(0, 8, title, fill=True, new_x="LMARGIN", new_y="NEXT")
        self._set_font("", 10)

    def _draw_compensation(self, comp: dict) -> float:
        """業務委託費セクションを描画し、小計(A)を返す"""
        self._draw_section_title("1. 業務委託費")
        self.ln(2)

        rows = [
            ("報酬額", comp.get("qualification_adjusted_compensation", 0)),
            ("源泉徴収", comp.get("withholding_tax", 0)),
            ("DX補助", comp.get("dx_subsidy", 0)),
        ]
        subtotal_a = sum(v for _, v in rows)
        for label, val in rows:
            self.cell(80, 7, f"  {label}", new_x="RIGHT")
            self.cell(60, 7, _fmt_yen(val), align="R", new_x="LMARGIN", new_y="NEXT")

        self.ln(1)
        self._set_font("B", 10)
        self.cell(80, 7, "  小計 (A)", new_x="RIGHT")
        self.cell(60, 7, _fmt_yen(subtotal_a), align="R", new_x="LMARGIN", new_y="NEXT")
        self._set_font("", 10)
        self.ln(4)
        return subtotal_a

    def _draw_reimbursement(self, items: pd.DataFrame) -> float:
        """旅費・立替経費セクションを描画し、小計(B)を返す"""
        self._draw_section_title("2. 旅費・立替経費")
        self.ln(2)

        if items.empty:
            self.cell(0, 7, "  (該当なし)", new_x="LMARGIN", new_y="NEXT")
            self.ln(4)
            return 0.0

        # テーブルヘッダー
        col_widths = [22, 30, 40, 35, 25, 18]
        headers = ["月日", "対象PJ", "支払用途", "分類", "金額", "領収書"]
        self._set_font("B", 9)
        for i, (w, h) in enumerate(zip(col_widths, headers)):
            last = i == len(headers) - 1
            self.cell(w, 6, h, border="B",
                      new_x="LMARGIN" if last else "RIGHT",
                      new_y="NEXT" if last else "TOP")
        self._set_font("", 9)

        # テーブル行
        subtotal_b = 0.0
        for _, row in items.iterrows():
            amount = float(row.get("payment_amount_numeric", 0) or 0)
            subtotal_b += amount
            receipt = row.get("receipt_url", "")
            has_receipt = bool(receipt and str(receipt).strip())

            vals = [
                str(row.get("date", "")),
                str(row.get("target_project", ""))[:8],
                str(row.get("payment_purpose", ""))[:12],
                str(row.get("category", ""))[:8],
                _fmt_yen(amount),
                "○" if has_receipt else "-",
            ]
            for i, (w, v) in enumerate(zip(col_widths, vals)):
                align = "R" if i == 4 else "L"
                last = i == len(vals) - 1
                self.cell(w, 6, v, align=align,
                          new_x="LMARGIN" if last else "RIGHT",
                          new_y="NEXT" if last else "TOP")

        self.ln(1)
        self._set_font("B", 10)
        self.cell(80, 7, "  小計 (B)", new_x="RIGHT")
        self.cell(60, 7, _fmt_yen(subtotal_b), align="R", new_x="LMARGIN", new_y="NEXT")
        self._set_font("", 10)
        self.ln(4)
        return subtotal_b

    def _draw_total(self, total: float):
        self.set_draw_color(0, 0, 0)
        self.line(10, self.get_y(), 200, self.get_y())
        self.ln(2)
        self._set_font("B", 12)
        self.cell(80, 10, "合計支払額 (A+B)", new_x="RIGHT")
        self.cell(60, 10, _fmt_yen(total), align="R", new_x="LMARGIN", new_y="NEXT")
        self.line(10, self.get_y(), 200, self.get_y())
        self._set_font("", 10)
        self.ln(6)

    def _draw_receipt_urls(self, items: pd.DataFrame):
        urls = []
        if not items.empty and "receipt_url" in items.columns:
            for url in items["receipt_url"]:
                if url and str(url).strip():
                    urls.append(str(url).strip())
        if not urls:
            return

        self._set_font("B", 10)
        self.cell(0, 7, "添付書類一覧", new_x="LMARGIN", new_y="NEXT")
        self._set_font("", 8)
        for i, url in enumerate(urls, 1):
            display = url if len(url) <= 70 else url[:67] + "..."
            self.cell(0, 5, f"  {i}. {display}", new_x="LMARGIN", new_y="NEXT")


def generate_payment_statement(
    member_name: str,
    full_name: str,
    year: int,
    month: int,
    compensation: dict,
    reimbursement_items: pd.DataFrame,
) -> bytes:
    """1メンバー×1月の支払明細書PDFを生成

    Args:
        member_name: ニックネーム
        full_name: 本名
        year: 対象年
        month: 対象月
        compensation: 報酬データ dict
            - qualification_adjusted_compensation: 報酬額
            - withholding_tax: 源泉徴収
            - dx_subsidy: DX補助
            - reimbursement: 立替合計（参考値）
            - payment: 支払額
        reimbursement_items: 立替明細 DataFrame
            - date, target_project, category, payment_purpose,
              payment_amount_numeric, receipt_url

    Returns:
        PDF bytes
    """
    pdf = _StatementPDF()
    pdf._draw_header(year, month)
    pdf._draw_member_info(full_name, member_name)
    subtotal_a = pdf._draw_compensation(compensation)
    subtotal_b = pdf._draw_reimbursement(reimbursement_items)
    pdf._draw_total(subtotal_a + subtotal_b)
    pdf._draw_receipt_urls(reimbursement_items)

    return bytes(pdf.output())


def generate_all_statements_zip(
    members_comp: pd.DataFrame,
    reimbursement_df: pd.DataFrame,
    year: int,
    month: int,
) -> bytes:
    """全メンバーの支払明細書PDFをZIPにまとめる

    Args:
        members_comp: 報酬データ（年月フィルタ済み）
        reimbursement_df: 立替明細（年月フィルタ済み）
        year: 対象年
        month: 対象月

    Returns:
        ZIP bytes
    """
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for _, row in members_comp.iterrows():
            nickname = str(row.get("nickname", ""))
            full_name = str(row.get("full_name", nickname))
            comp = {
                "qualification_adjusted_compensation": float(
                    row.get("qualification_adjusted_compensation", 0) or 0
                ),
                "withholding_tax": float(row.get("withholding_tax", 0) or 0),
                "dx_subsidy": float(row.get("dx_subsidy", 0) or 0),
                "reimbursement": float(row.get("reimbursement", 0) or 0),
                "payment": float(row.get("payment", 0) or 0),
            }
            # メンバーの立替明細を抽出
            member_reimb = reimbursement_df[
                reimbursement_df["nickname"] == nickname
            ] if not reimbursement_df.empty else pd.DataFrame()

            pdf_bytes = generate_payment_statement(
                member_name=nickname,
                full_name=full_name,
                year=year,
                month=month,
                compensation=comp,
                reimbursement_items=member_reimb,
            )
            safe_name = nickname.replace("/", "_").replace("\\", "_")
            filename = f"{safe_name}_{year}_{month:02d}.pdf"
            zf.writestr(filename, pdf_bytes)

    return buf.getvalue()
