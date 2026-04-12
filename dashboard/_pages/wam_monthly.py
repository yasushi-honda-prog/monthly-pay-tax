"""WAM立替金確認ページ（admin限定・ドラフト提案用）

v_reimbursement_enriched VIEW から立替金データを取得し、
PJ別サマリー・メンバー別明細・領収書添付状況を表示する。
v_monthly_compensation VIEW から報酬・源泉徴収データを表示する。
"""

import io

import pandas as pd
import streamlit as st

from lib.auth import require_admin
from lib.bq_client import load_data
from lib.constants import MONTHLY_COMPENSATION_VIEW, REIMBURSEMENT_VIEW
from lib.receipt_pdf import generate_all_statements_zip, generate_payment_statement
from lib.ui_helpers import fill_empty_nickname, render_kpi, render_sidebar_year_month

# --- 認証チェック ---
email = st.session_state.get("user_email", "")
role = st.session_state.get("user_role", "")
require_admin(email, role)

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


def _generate_transfer_csv(df: pd.DataFrame) -> bytes:
    """GMOあおぞらネット銀行 総合振込CSVを生成（Shift_JIS、ヘッダーなし）

    フォーマット: 銀行番号,支店番号,預金種目,口座番号,受取人名,振込金額,EDI情報,識別表示
    口座情報はプレースホルダー（口座マスタ未整備のため経理が手動補完）
    """
    if df.empty:
        return b""
    # payment > 0 のメンバーのみ
    target = df[df["payment"].notna() & (df["payment"] > 0)].copy()
    if target.empty:
        return b""
    rows = []
    for _, r in target.iterrows():
        amount = int(r["payment"])
        name = str(r.get("full_name", r.get("nickname", "")))
        rows.append(f",,1,,{name},{amount},,")
    return "\n".join(rows).encode("shift_jis", errors="replace")


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
tab1, tab2, tab3, tab4, tab5 = st.tabs(["PJ別サマリー", "メンバー別明細", "領収書添付状況", "月別報酬・振込確認", "支払明細書"])

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

        display_cols = [
            "nickname", "date", "target_project", "is_wam", "category",
            "payment_purpose", "payment_amount", "advance_amount",
            "from_station", "to_station", "visit_purpose",
        ]
        existing_cols = [c for c in display_cols if c in df_detail.columns]
        col_labels = {
            "nickname": "メンバー", "date": "月日", "target_project": "対象PJ",
            "is_wam": "WAM対象", "category": "分類", "payment_purpose": "支払用途",
            "payment_amount": "支払金額", "advance_amount": "仮払金額",
            "from_station": "発", "to_station": "着", "visit_purpose": "訪問目的",
        }
        st.dataframe(
            df_detail[existing_cols].rename(columns=col_labels),
            use_container_width=True,
            hide_index=True,
        )
        st.caption(f"{len(df_detail):,} 件表示")

        # CSVダウンロード
        csv_data = df_detail[existing_cols].rename(columns=col_labels).to_csv(index=False)
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
            transfer_csv = _generate_transfer_csv(df_comp)
            st.download_button(
                "振込CSV（GMOあおぞら形式）",
                transfer_csv,
                file_name=f"wam_transfer_{selected_year}_{selected_month:02d}.csv",
                mime="text/csv",
                key="wam_transfer_csv_download",
            )
        st.caption("※ 振込CSVの口座情報（銀行番号・支店番号・口座番号）は未入力です。ダウンロード後に手動で補完してください。")

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
