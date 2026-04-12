"""WAM立替金確認ページ（admin限定・ドラフト提案用）

v_reimbursement_enriched VIEW から立替金データを取得し、
PJ別サマリー・メンバー別明細・領収書添付状況を表示する。
v_monthly_compensation VIEW から報酬・源泉徴収データを表示する。
"""

import pandas as pd
import streamlit as st

from lib.auth import require_admin
from lib.bq_client import load_data
from lib.constants import MONTHLY_COMPENSATION_VIEW, REIMBURSEMENT_VIEW
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
except Exception:
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
tab1, tab2, tab3, tab4 = st.tabs(["PJ別サマリー", "メンバー別明細", "領収書添付状況", "月別報酬・振込確認"])

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

        # CSVダウンロード
        comp_csv = comp_summary.to_csv(index=False)
        st.download_button(
            "CSVダウンロード",
            comp_csv,
            file_name=f"wam_compensation_{selected_year}_{selected_month:02d}.csv",
            mime="text/csv",
            key="wam_comp_csv_download",
        )
