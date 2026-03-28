"""業務委託費分析タブ プロトタイプ（モックデータ）

実装前の確認用。BQ接続不要。
実行: streamlit run dashboard/prototype_cost_analysis.py
"""

import altair as alt
import pandas as pd
import streamlit as st

st.set_page_config(page_title="業務委託費分析 プロトタイプ", layout="wide")

# --- work_category → 分類グループ マッピング ---
_COST_GROUP_MAP: dict[str, str] = {
    # 行政事業
    "移動時間": "行政事業（行政事業：ケアプランデータ連携システムを広め隊＆神奈川県事業）",
    "自家用車使用": "行政事業（行政事業：ケアプランデータ連携システムを広め隊＆神奈川県事業）",
    "令和7年度行政事業（PM・経産省各リーダー担当者以上）": "行政事業（行政事業：ケアプランデータ連携システムを広め隊＆神奈川県事業）",
    "令和7年度行政事業（ケアブー：全日稼働）※日給制": "行政事業（行政事業：ケアプランデータ連携システムを広め隊＆神奈川県事業）",
    "令和7年度行政事業（ケアブー：半日稼働）※日給制": "行政事業（行政事業：ケアプランデータ連携システムを広め隊＆神奈川県事業）",
    "令和7年度行政事業（共通）": "行政事業（行政事業：ケアプランデータ連携システムを広め隊＆神奈川県事業）",
    # スポンサー対応
    "スポンサー対応（PM業務）": "スポンサー対応（主にスマート介護士を推進し隊）",
    "スポンサー対応（一般業務）": "スポンサー対応（主にスマート介護士を推進し隊）",
    # タダスク
    "タダスク関連": "タダスク（主にタダスクわいわい盛り上げ隊）",
    "タダスク関連【1講座ごと】": "タダスク（主にタダスクわいわい盛り上げ隊）",
    "タダスク関連打合せ【1講座ごと】": "タダスク（主にタダスクわいわい盛り上げ隊）",
    "タダスク事務局関連": "タダスク（主にタダスクわいわい盛り上げ隊）",
    # タダサポ
    "タダサポ（個別支援）関連": "タダサポ（主にタダスクわいわい盛り上げ隊）",
    # 出張タダスク
    "フロント・フロントサポーター（旧ルール）": "出張タダスク（主に出張タダスクで喜ばれ隊）",
    "フロント（新ルール）【開催日に包括算定】": "出張タダスク（主に出張タダスクで喜ばれ隊）",
    "フロントサポーター（新ルール）【開催日に包括算定】": "出張タダスク（主に出張タダスクで喜ばれ隊）",
    "出張タダスク関連": "出張タダスク（主に出張タダスクで喜ばれ隊）",
    "出張タダスク講師（旧ルール）": "出張タダスク（主に出張タダスクで喜ばれ隊）",
    "出張タダスク講師（新ルール）【開催日に包括算定】": "出張タダスク（主に出張タダスクで喜ばれ隊）",
    # タダレク
    "タダレク関連": "タダレク（主に色んな企業とwin-winになり隊）",
    # イベント企画/コミュニティ
    "イベント企画・運営関連": "イベント企画/コミュニティ（主にみんなと仲良くし隊）",
    "コミュニティ運営（タダコミュ関連）": "イベント企画/コミュニティ（主にみんなと仲良くし隊）",
    "社内イベント参加": "イベント企画/コミュニティ（主にみんなと仲良くし隊）",
    # テクニカル・オペレーション業務
    "オペレーション業務": "テクニカル・オペレーション業務（主にすごいシステムつくり隊）",
    "テクニカル業務": "テクニカル・オペレーション業務（主にすごいシステムつくり隊）",
    # タダカヨ経営戦略・業務管理
    "スペシャリスト業務": "タダカヨ経営戦略・業務管理（主にしっかり法人を経営し隊）",
    "タダカヨ経営戦略・業務管理": "タダカヨ経営戦略・業務管理（主にしっかり法人を経営し隊）",
    "社内タダスク": "タダカヨ経営戦略・業務管理（主にしっかり法人を経営し隊）",
    # 広報
    "タダカヨ広報関連": "広報（主に広報がんばり隊、シン・もっと寄付を集め隊）",
    # 法人内MTG
    "法人内MTG": "法人内MTG（全隊）",
    # 電話対応
    "1件対応": "電話対応（主に行政事業中心）",
    "2件対応": "電話対応（主に行政事業中心）",
    "3件対応 or 合計30分以上対応": "電話対応（主に行政事業中心）",
    "待機時間": "電話対応（主に行政事業中心）",
    # その他
    "その他（収益事業）": "その他",
    "発送業務": "その他",
}

# --- モックデータ生成 ---
import random
random.seed(42)

months = [(2025, 11), (2025, 12), (2026, 1), (2026, 2), (2026, 3)]
work_categories_mapped = list(_COST_GROUP_MAP.keys())
# 未分類のwork_categoryも含める（将来追加された想定）
work_categories_unmapped = ["新規AI業務", "DX推進支援"]

rows = []
for year, month in months:
    for wcat in work_categories_mapped:
        amount = random.randint(10000, 500000)
        rows.append({
            "year": year,
            "month": month,
            "month_num": str(month),
            "work_category": wcat,
            "amount_num": float(amount),
        })
    for wcat in work_categories_unmapped:
        amount = random.randint(5000, 100000)
        rows.append({
            "year": year,
            "month": month,
            "month_num": str(month),
            "work_category": wcat,
            "amount_num": float(amount),
        })

df = pd.DataFrame(rows)

# --- マッピング適用 ---
df["cost_group"] = df["work_category"].map(_COST_GROUP_MAP)
df["ym_label"] = df["year"].astype(str) + "年" + df["month_num"] + "月"
ym_sort = {f"{y}年{m}月": y * 100 + m for y, m in months}
ym_order = sorted(ym_sort.keys(), key=lambda k: ym_sort[k])

# 未分類
unmapped_mask = df["cost_group"].isna()
df.loc[unmapped_mask, "cost_group"] = "(未分類)"

# --- UI ---
st.title("業務委託費分析（プロトタイプ）")
st.caption("※ モックデータで表示しています。レイアウト確認用です。")

ctab1, ctab2 = st.tabs(["業務委託費全体", "非営利活動"])


def _render_cost_chart(data: pd.DataFrame, x_title: str = "") -> None:
    if data.empty:
        st.info("対象期間のデータがありません")
        return

    agg = (
        data.groupby(["ym_label", "cost_group"])["amount_num"]
        .sum()
        .reset_index()
    )
    agg.columns = ["年月", "分類", "金額"]
    agg = agg[agg["金額"] > 0]

    st.metric("総額", f"¥{data['amount_num'].sum():,.0f}")
    st.caption(f"件数：{len(data):,} 件")

    if agg.empty:
        st.info("対象期間の金額データがありません")
        return

    x_enc = alt.X("年月:O", title=x_title or None, sort=ym_order, axis=alt.Axis(labelAngle=0, labelFontSize=12))

    bar = alt.Chart(agg).mark_bar(size=40).encode(
        x=x_enc,
        y=alt.Y("金額:Q", title="金額（円）", axis=alt.Axis(format=",.0f")),
        color=alt.Color("分類:N", title="分類",
        scale=alt.Scale(scheme="tableau20"),
        legend=alt.Legend(orient="right", labelLimit=300, labelFontSize=10),
    ),
        tooltip=["年月:O", "分類:N", alt.Tooltip("金額:Q", format=",.0f")],
    )

    totals = agg.groupby("年月")["金額"].sum().reset_index()
    totals.columns = ["年月", "合計"]
    totals["label"] = totals["合計"].apply(lambda x: f"¥{x:,.0f}")
    label = alt.Chart(totals).mark_text(
        dy=-8, fontSize=11, color="#666666"
    ).encode(
        x=alt.X("年月:O", sort=ym_order),
        y=alt.Y("合計:Q", stack="zero"),
        text=alt.Text("label:N"),
    )

    chart = (bar + label).resolve_scale(color="shared").properties(height=580)
    st.altair_chart(chart, use_container_width=True)

    # 集計テーブル
    pivot = agg.pivot_table(
        values="金額", index="分類", columns="年月",
        aggfunc="sum", fill_value=0,
    )
    pivot = pivot[sorted(pivot.columns, key=lambda c: ym_sort.get(c, 9999))]
    pivot["合計"] = pivot.sum(axis=1)
    pivot = pivot.sort_values("合計", ascending=False)
    st.dataframe(pivot.style.format("¥{:,.0f}"), use_container_width=True)

    # 未分類一覧
    unmapped = data[data["cost_group"] == "(未分類)"]["work_category"].drop_duplicates().sort_values()
    if not unmapped.empty:
        with st.expander(f"未分類の業務分類（{len(unmapped)} 件）", expanded=True):
            items = "".join(f"<li>{v}</li>" for v in unmapped)
            st.markdown(f'<ul style="color:#888888;font-size:0.9rem;margin:0">{items}</ul>', unsafe_allow_html=True)


with ctab1:
    st.subheader("業務委託費全体（分類別・月次推移）")
    _render_cost_chart(df, x_title="人件費（全体）")

with ctab2:
    st.subheader("非営利活動（分類別・月次推移）")
    _df_np = df[~df["cost_group"].isin({
        "行政事業（行政事業：ケアプランデータ連携システムを広め隊＆神奈川県事業）",
        "電話対応（主に行政事業中心）",
    })].copy()
    _render_cost_chart(_df_np, x_title="人件費（行政事業以外）")
