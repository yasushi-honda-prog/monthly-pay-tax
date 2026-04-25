"""WAM立替金確認ページ（checker/admin・ドラフト提案用）

v_reimbursement_enriched VIEW から立替金データを取得し、
PJ別サマリー・メンバー別明細・領収書添付状況を表示する。
v_monthly_compensation VIEW から報酬・源泉徴収データを表示する。

ロール制御:
- checker / admin: Tab1〜Tab5 アクセス可
- admin のみ: Tab6（年間支払調書データ、氏名・住所等の個人情報を含む）
"""

import io

import pandas as pd
import streamlit as st

from lib.auth import require_checker
from lib.bq_client import load_data
from lib.constants import MEMBER_MASTER_TABLE, MONTHLY_COMPENSATION_VIEW, REIMBURSEMENT_VIEW
from lib.receipt_pdf import generate_all_statements_zip, generate_payment_statement
from lib.ui_helpers import fill_empty_nickname, render_kpi, render_sidebar_year_month
from lib.wam_helpers import build_tab2_csv_df, build_tab2_display_df

# --- 認証チェック ---
email = st.session_state.get("user_email", "")
role = st.session_state.get("user_role", "")
require_checker(email, role)

st.header("WAM 立替金・報酬確認")
st.caption("立替金シートデータ・月別報酬の確認・分析（ドラフト）")


# --- データ取得 ---
def _load_reimbursement():
    query = f"SELECT * FROM `{REIMBURSEMENT_VIEW}`"
    return load_data(query)  # load_data側で@st.cache_data(ttl=21600)済み


def _filter_by_year_month(df: pd.DataFrame, year: int, month: int) -> pd.DataFrame:
    """年月でフィルタ"""
    return df[(df["normalized_year"] == year) & (df["month"] == month)]


def _summarize_by_project(df: pd.DataFrame) -> pd.DataFrame:
    """対象PJ別の立替金サマリーを作成"""
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
    """receipt_url の添付判定（True=添付済み）"""
    return series.notna() & (series.str.strip() != "")


def _receipt_stats(df: pd.DataFrame) -> dict:
    """領収書添付状況の統計を返す"""
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


# --- 報酬データ関連 ---
_COMP_NUM_COLS = [
    "qualification_adjusted_compensation", "withholding_tax",
    "dx_subsidy", "reimbursement", "payment",
]


def _load_compensation():
    query = f"SELECT * FROM `{MONTHLY_COMPENSATION_VIEW}`"
    return load_data(query)


def _filter_comp_by_year_month(df: pd.DataFrame, year: int, month: int) -> pd.DataFrame:
    """報酬データの年月フィルタ"""
    return df[(df["year"] == year) & (df["month"] == month)]


def _summarize_compensation(df: pd.DataFrame) -> pd.DataFrame:
    """メンバー別の報酬サマリーを作成"""
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


def _load_bank_accounts() -> pd.DataFrame:
    """member_masterから report_url → 口座情報のマッピングを取得

    report_url_1 → bank1_*, report_url_2 → bank2_* の1:1対応をUNIONで正規化。
    """
    query = f"""
    SELECT report_url_1 AS report_url,
           bank1_code AS bank_code, bank1_branch_code AS branch_code,
           bank1_deposit_type AS deposit_type, bank1_account_number AS account_number,
           bank1_holder_name AS holder_name
    FROM `{MEMBER_MASTER_TABLE}` WHERE report_url_1 IS NOT NULL AND report_url_1 != ''
    UNION ALL
    SELECT report_url_2 AS report_url,
           bank2_code AS bank_code, bank2_branch_code AS branch_code,
           bank2_deposit_type AS deposit_type, bank2_account_number AS account_number,
           bank2_holder_name AS holder_name
    FROM `{MEMBER_MASTER_TABLE}` WHERE report_url_2 IS NOT NULL AND report_url_2 != ''
    """
    return load_data(query)


def _load_member_info() -> pd.DataFrame:
    """member_masterから report_url → 氏名・住所のマッピングを取得（支払調書用）"""
    query = f"""
    SELECT report_url_1 AS report_url,
           member_id, last_name, first_name, last_name_kana, first_name_kana,
           postal_code, prefecture, address
    FROM `{MEMBER_MASTER_TABLE}` WHERE report_url_1 IS NOT NULL AND report_url_1 != ''
    UNION ALL
    SELECT report_url_2 AS report_url,
           member_id, last_name, first_name, last_name_kana, first_name_kana,
           postal_code, prefecture, address
    FROM `{MEMBER_MASTER_TABLE}` WHERE report_url_2 IS NOT NULL AND report_url_2 != ''
    """
    return load_data(query)


def _build_annual_withholding_data(
    df_comp_all: pd.DataFrame, year: int, df_member: pd.DataFrame
) -> pd.DataFrame:
    """年間支払調書データを構築

    v_monthly_compensationの月別データを年間集計し、member_masterの氏名・住所をJOIN。
    """
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

    # member_master の氏名・住所をJOIN
    if not df_member.empty:
        agg = agg.merge(df_member, on="report_url", how="left")

    return agg.sort_values("年間支払額", ascending=False, na_position="last")


def _generate_withholding_csv(df: pd.DataFrame) -> bytes:
    """支払調書用CSVを生成（UTF-8 BOM付き、Excel対応）"""
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


def _generate_transfer_csv(df: pd.DataFrame, df_bank: pd.DataFrame) -> bytes:
    """GMOあおぞらネット銀行 総合振込CSVを生成（Shift_JIS、ヘッダーなし）

    フォーマット: 銀行番号,支店番号,預金種目,口座番号,受取人名,振込金額,EDI情報,識別表示
    口座情報は member_master から自動取得（マッチしない場合は空欄）。
    """
    if df.empty:
        return b""
    # payment > 0 のメンバーのみ
    target = df[df["payment"].notna() & (df["payment"] > 0)].copy()
    if target.empty:
        return b""

    # 口座データをreport_urlで結合
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


def _safe_str(val) -> str:
    """NaN/None を空文字に変換"""
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return ""
    s = str(val).strip()
    return "" if s == "nan" else s


def _deposit_type_code(deposit_type: str) -> str:
    """預金種目の文字列を数値コードに変換（GMOあおぞら形式）"""
    mapping = {"普通": "1", "当座": "2", "貯蓄": "4"}
    return mapping.get(deposit_type.strip(), "1") if deposit_type.strip() else "1"


# --- サイドバー ---
with st.sidebar:
    selected_year, selected_month = render_sidebar_year_month(
        year_key="wam_year", month_key="wam_month",
    )

# --- データ読み込み & フィルタ ---
try:
    df_all = _load_reimbursement()
except Exception as e:
    st.error(f"データ取得エラー: {e}")
    st.stop()

df_all = fill_empty_nickname(df_all)
df = _filter_by_year_month(df_all, selected_year, selected_month)

# --- 報酬データ読み込み ---
try:
    df_comp_all = _load_compensation()
    df_comp_all = fill_empty_nickname(df_comp_all)
    df_comp_all = df_comp_all[df_comp_all["year"].notna()]
    df_comp_all["year"] = df_comp_all["year"].astype(int)
    df_comp_all["month"] = df_comp_all["month"].astype("Int64")
    df_comp_all[_COMP_NUM_COLS] = df_comp_all[_COMP_NUM_COLS].apply(
        pd.to_numeric, errors="coerce"
    ).fillna(0)
    df_comp = _filter_comp_by_year_month(df_comp_all, selected_year, selected_month)
    comp_loaded = True
except Exception as e:
    st.warning(f"報酬データの取得に失敗しました: {e}")
    df_comp = pd.DataFrame()
    comp_loaded = False

# --- サイドバー: 対象PJフィルタ ---
with st.sidebar:
    all_projects = sorted(df_all["target_project"].dropna().unique().tolist())
    selected_project = st.selectbox(
        "対象PJ",
        ["すべて"] + all_projects,
        key="wam_project",
    )

if selected_project != "すべて":
    df = df[df["target_project"] == selected_project]

# --- サイドバー: WAM対象フィルタ ---
with st.sidebar:
    wam_only = st.checkbox("WAM対象のみ表示", key="wam_only")

if wam_only and "is_wam" in df.columns:
    df = df[df["is_wam"] == True]  # noqa: E712

# --- KPI ---
cols = st.columns(4)
with cols[0]:
    render_kpi("対象月データ件数", f"{len(df):,}")
with cols[1]:
    total_payment = df["payment_amount_numeric"].sum() if not df.empty else 0
    render_kpi("支払金額合計", f"¥{total_payment:,.0f}")
with cols[2]:
    total_advance = df["advance_amount_numeric"].sum() if not df.empty else 0
    render_kpi("仮払金額合計", f"¥{total_advance:,.0f}")
with cols[3]:
    stats = _receipt_stats(df)
    render_kpi("領収書添付率", f"{stats['rate']:.0f}%")

# --- タブ ---
# Tab6（年間支払調書データ）は氏名・住所等の個人情報を含むため admin 限定
if role == "admin":
    tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
        "PJ別サマリー", "メンバー別明細", "領収書添付状況",
        "月別報酬・振込確認", "支払明細書", "年間支払調書データ",
    ])
else:
    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "PJ別サマリー", "メンバー別明細", "領収書添付状況",
        "月別報酬・振込確認", "支払明細書",
    ])
    tab6 = None

with tab1:
    st.subheader("対象PJ別 立替金サマリー")
    summary = _summarize_by_project(df)
    if summary.empty:
        st.info("該当データがありません")
    else:
        summary_display = summary.copy()
        summary_display["支払金額合計"] = summary_display["支払金額合計"].apply(lambda x: f"¥{x:,.0f}")
        summary_display["仮払金額合計"] = summary_display["仮払金額合計"].apply(lambda x: f"¥{x:,.0f}")
        st.dataframe(summary_display, use_container_width=True, hide_index=True)

with tab2:
    st.subheader("メンバー別明細")
    if df.empty:
        st.info("該当データがありません")
    else:
        members = sorted(df["nickname"].unique().tolist())
        selected_member = st.selectbox("メンバー", ["すべて"] + members, key="wam_member")
        df_detail = df if selected_member == "すべて" else df[df["nickname"] == selected_member]

        st.dataframe(
            build_tab2_display_df(df_detail),
            column_config={
                "URL": st.column_config.LinkColumn(display_text="開く"),
            },
            use_container_width=True,
            hide_index=True,
        )
        st.caption(f"{len(df_detail):,} 件表示")

        csv_data = build_tab2_csv_df(df_detail).to_csv(index=False)
        st.download_button(
            "CSVダウンロード",
            csv_data,
            file_name=f"wam_reimbursement_{selected_year}_{selected_month:02d}.csv",
            mime="text/csv",
            key="wam_csv_download",
        )

with tab3:
    st.subheader("領収書添付状況")
    if df.empty:
        st.info("該当データがありません")
    else:
        stats = _receipt_stats(df)
        cols3 = st.columns(3)
        with cols3[0]:
            render_kpi("総件数", f"{stats['total']:,}")
        with cols3[1]:
            render_kpi("添付済み", f"{stats['attached']:,}")
        with cols3[2]:
            render_kpi("未添付", f"{stats['missing']:,}")

        # メンバー別の添付状況
        receipt_by_member = df.groupby("nickname").apply(
            lambda g: pd.Series({
                "総件数": len(g),
                "添付済み": int(_is_receipt_attached(g["receipt_url"]).sum()),
            })
        ).reset_index()
        receipt_by_member["未添付"] = receipt_by_member["総件数"] - receipt_by_member["添付済み"]
        receipt_by_member["添付率"] = (
            receipt_by_member["添付済み"] / receipt_by_member["総件数"] * 100
        ).round(1).astype(str) + "%"
        receipt_by_member.rename(columns={"nickname": "メンバー"}, inplace=True)
        st.dataframe(
            receipt_by_member.sort_values("未添付", ascending=False),
            use_container_width=True,
            hide_index=True,
        )

with tab4:
    st.subheader("月別報酬・振込確認")
    if not comp_loaded:
        st.warning("報酬データの取得に失敗しました")
    elif df_comp.empty:
        st.info("該当データがありません")
    else:
        # KPI
        cols4 = st.columns(4)
        with cols4[0]:
            render_kpi("対象メンバー数", f"{len(df_comp):,}")
        with cols4[1]:
            total_comp = df_comp["qualification_adjusted_compensation"].sum()
            render_kpi("報酬合計", f"¥{total_comp:,.0f}")
        with cols4[2]:
            total_tax = df_comp["withholding_tax"].sum()
            render_kpi("源泉徴収合計", f"¥{total_tax:,.0f}")
        with cols4[3]:
            total_pay = df_comp["payment"].sum()
            render_kpi("支払額合計", f"¥{total_pay:,.0f}")

        # メンバー別テーブル
        comp_summary = _summarize_compensation(df_comp)
        comp_display = comp_summary.copy()
        for col in ["報酬", "源泉徴収", "DX補助", "立替", "支払額"]:
            comp_display[col] = comp_display[col].apply(lambda x: f"¥{x:,.0f}")
        st.dataframe(comp_display, use_container_width=True, hide_index=True)
        st.caption(f"{len(comp_summary):,} 名表示")

        # CSVダウンロード（報酬明細）
        comp_csv = comp_summary.to_csv(index=False)
        dl_col1, dl_col2 = st.columns(2)
        with dl_col1:
            st.download_button(
                "報酬明細CSV",
                comp_csv,
                file_name=f"wam_compensation_{selected_year}_{selected_month:02d}.csv",
                mime="text/csv",
                key="wam_comp_csv_download",
            )
        with dl_col2:
            try:
                df_bank = _load_bank_accounts()
            except Exception:
                df_bank = pd.DataFrame()
            transfer_csv = _generate_transfer_csv(df_comp, df_bank)
            st.download_button(
                "振込CSV（GMOあおぞら形式）",
                transfer_csv,
                file_name=f"wam_transfer_{selected_year}_{selected_month:02d}.csv",
                mime="text/csv",
                key="wam_transfer_csv_download",
            )
        if df_bank.empty:
            st.caption("※ 口座情報を取得できませんでした。ダウンロード後に手動で補完してください。")
        else:
            st.caption("※ 口座情報は member_master から自動入力済みです。マッチしないメンバーは空欄のため手動補完してください。")

@st.cache_data(show_spinner="PDF生成中...")
def _cached_generate_statement(member_name, full_name, year, month, comp_tuple, reimb_csv):
    """キャッシュ付きPDF生成（Streamlit再レンダリング時の再生成を防止）"""
    comp = dict(zip(
        ["qualification_adjusted_compensation", "withholding_tax", "dx_subsidy", "reimbursement", "payment"],
        comp_tuple,
    ))
    reimb_df = pd.read_csv(io.StringIO(reimb_csv)) if reimb_csv else pd.DataFrame()
    return generate_payment_statement(member_name, full_name, year, month, comp, reimb_df)


@st.cache_data(show_spinner="ZIP生成中...")
def _cached_generate_zip(comp_csv, reimb_csv, year, month):
    """キャッシュ付きZIP生成"""
    comp_df = pd.read_csv(io.StringIO(comp_csv))
    reimb_df = pd.read_csv(io.StringIO(reimb_csv)) if reimb_csv else pd.DataFrame()
    return generate_all_statements_zip(comp_df, reimb_df, year, month)


with tab5:
    st.subheader("支払明細書")
    if not comp_loaded or df_comp.empty:
        st.info("報酬データがありません（支払明細書の生成には報酬データが必要です）")
    else:
        # メンバー選択
        comp_members = sorted(df_comp["nickname"].dropna().unique().tolist())
        selected_stmt_member = st.selectbox(
            "メンバー選択", ["全メンバー"] + comp_members, key="wam_stmt_member",
        )

        if selected_stmt_member == "全メンバー":
            # 全メンバーサマリー
            st.caption(f"{len(comp_members):,} 名分の支払明細書を一括生成します")
            try:
                zip_bytes = _cached_generate_zip(
                    comp_csv=df_comp.to_csv(index=False),
                    reimb_csv=df.to_csv(index=False) if not df.empty else "",
                    year=selected_year,
                    month=selected_month,
                )
                st.download_button(
                    "全メンバー一括ダウンロード (ZIP)",
                    zip_bytes,
                    file_name=f"payment_statements_{selected_year}_{selected_month:02d}.zip",
                    mime="application/zip",
                    key="wam_stmt_zip_download",
                )
            except Exception as e:
                st.error(f"ZIP生成に失敗しました: {e}")
        else:
            # 個別メンバー
            member_comp = df_comp[df_comp["nickname"] == selected_stmt_member].iloc[0]
            member_reimb = df[df["nickname"] == selected_stmt_member] if not df.empty else pd.DataFrame()

            comp_data = {
                "qualification_adjusted_compensation": float(member_comp.get("qualification_adjusted_compensation", 0) or 0),
                "withholding_tax": float(member_comp.get("withholding_tax", 0) or 0),
                "dx_subsidy": float(member_comp.get("dx_subsidy", 0) or 0),
                "reimbursement": float(member_comp.get("reimbursement", 0) or 0),
                "payment": float(member_comp.get("payment", 0) or 0),
            }

            # プレビュー
            cols5 = st.columns(3)
            with cols5[0]:
                subtotal_a = (
                    comp_data["qualification_adjusted_compensation"]
                    + comp_data["withholding_tax"]
                    + comp_data["dx_subsidy"]
                )
                render_kpi("業務委託費 (A)", f"¥{subtotal_a:,.0f}")
            with cols5[1]:
                subtotal_b = member_reimb["payment_amount_numeric"].sum() if not member_reimb.empty else 0
                render_kpi("立替経費 (B)", f"¥{subtotal_b:,.0f}")
            with cols5[2]:
                render_kpi("合計 (A+B)", f"¥{subtotal_a + subtotal_b:,.0f}")

            # PDF生成・ダウンロード（キャッシュ済み）
            full_name = str(member_comp.get("full_name", selected_stmt_member))
            comp_tuple = tuple(comp_data[k] for k in [
                "qualification_adjusted_compensation", "withholding_tax",
                "dx_subsidy", "reimbursement", "payment",
            ])
            reimb_csv = member_reimb.to_csv(index=False) if not member_reimb.empty else ""
            try:
                pdf_bytes = _cached_generate_statement(
                    selected_stmt_member, full_name,
                    selected_year, selected_month,
                    comp_tuple, reimb_csv,
                )
                st.download_button(
                    "支払明細書PDFダウンロード",
                    pdf_bytes,
                    file_name=f"payment_statement_{selected_stmt_member}_{selected_year}_{selected_month:02d}.pdf",
                    mime="application/pdf",
                    key="wam_stmt_pdf_download",
                )
            except Exception as e:
                st.error(f"PDF生成に失敗しました: {e}")

            # 領収書URL一覧
            if not member_reimb.empty and "receipt_url" in member_reimb.columns:
                urls = member_reimb["receipt_url"].dropna()
                urls = urls[urls.str.strip() != ""]
                if not urls.empty:
                    with st.expander(f"添付書類一覧（{len(urls)}件）"):
                        for i, url in enumerate(urls, 1):
                            st.markdown(f"{i}. {url}")

if tab6 is not None:
    with tab6:
        st.subheader("年間支払調書データ")
        st.caption("メンバー別の年間報酬・源泉徴収合計＋氏名住所（支払調書作成用）")
        if not comp_loaded:
            st.warning("報酬データの取得に失敗しました")
        else:
            try:
                df_member_info = _load_member_info()
            except Exception:
                df_member_info = pd.DataFrame()

            df_annual = _build_annual_withholding_data(df_comp_all, selected_year, df_member_info)

            if df_annual.empty:
                st.info(f"{selected_year}年のデータがありません")
            else:
                # KPI
                cols6 = st.columns(4)
                with cols6[0]:
                    render_kpi("対象者数", f"{len(df_annual):,}")
                with cols6[1]:
                    render_kpi("年間報酬合計", f"¥{df_annual['年間報酬'].sum():,.0f}")
                with cols6[2]:
                    render_kpi("年間源泉徴収合計", f"¥{abs(df_annual['年間源泉徴収'].sum()):,.0f}")
                with cols6[3]:
                    render_kpi("年間支払額合計", f"¥{df_annual['年間支払額'].sum():,.0f}")

                # テーブル表示（個人情報は非表示 — 氏名・住所はCSVのみ）
                display_cols = ["nickname"]
                display_cols += ["年間報酬", "年間源泉徴収", "年間DX補助", "年間立替", "年間支払額"]
                df_display = df_annual[[c for c in display_cols if c in df_annual.columns]].copy()

                # 金額列をフォーマット
                for col in ["年間報酬", "年間源泉徴収", "年間DX補助", "年間立替", "年間支払額"]:
                    if col in df_display.columns:
                        df_display[col] = df_display[col].apply(lambda x: f"¥{x:,.0f}")

                st.dataframe(df_display, use_container_width=True, hide_index=True)
                st.caption(f"{len(df_annual):,} 名表示（{selected_year}年 年間集計）")

                # CSVダウンロード
                csv_bytes = _generate_withholding_csv(df_annual)
                st.download_button(
                    "支払調書データCSV",
                    csv_bytes,
                    file_name=f"withholding_data_{selected_year}.csv",
                    mime="text/csv",
                    key="wam_withholding_csv_download",
                )
                st.caption("※ 支払調書の正式作成には別途マイナンバー等の情報が必要です。")
