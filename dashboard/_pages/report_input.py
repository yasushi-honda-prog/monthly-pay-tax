"""（仮）報告入力（UI 提案ドラフト / admin 限定プレビュー）

業務報告（日次）・補助報告（月次）の UI プロトタイプ。
現状はドラフト位置づけで、DB への保存は接続されていない（admin 内部レビュー用）。
"""

import logging
from datetime import date

import pandas as pd
import streamlit as st
from google.cloud import bigquery

from lib.auth import require_admin
from lib.bq_client import get_bq_client
from lib.constants import APP_GYOMU_TABLE, APP_HOJO_TABLE
from lib.ui_helpers import render_sidebar_year_month

logger = logging.getLogger(__name__)

# --- 認証チェック（admin 限定: UI 提案ドラフトのため） ---
email = st.session_state.get("user_email", "")
role = st.session_state.get("user_role", "")
require_admin(email, role)

st.header("(仮) 報告入力")
st.caption("UI 提案ドラフト（admin プレビュー）｜ 業務報告（日次）・補助報告（月次）")
st.warning("このページは UI 提案のドラフトです。保存先 DB はまだ接続されていません。", icon=":material/info:")

WEEKDAY_JP = ["月", "火", "水", "木", "金", "土", "日"]

TEAM_LIST = [
    "みんなでスキルアップ隊",
    "介護DXで包括の未来を応援し隊",
    "色んな企業とwin-winになり隊",
    "ひとり一人を大切にし隊",
    "しっかり法人を経営し隊",
    "ちゃんとお金を管理し隊",
    "広報がんばり隊",
    "スマート介護士を推進し隊",
    "もっと寄付を集め隊",
]

# ====================================================================
# 業務マスタ（タダカヨ業務別報酬テーブルに基づく）
# ====================================================================

GYOMU_MASTER = [
    {"activity": "タダスク", "work": "タダスク関連", "price": 3000, "unit": "所要時間",
     "desc": "新規メンバー対応 / 関連チーム業務（みんなでスキルアップ隊、介護DXで包括の未来を応援し隊）"},
    {"activity": "タダスク", "work": "タダスク事務局関連", "price": 4000, "unit": "所要時間",
     "desc": "タダスク講義調整・取りまとめ"},
    {"activity": "タダスク", "work": "タダスク関連【1講座ごと】", "price": 5000, "unit": "1講座",
     "desc": "講義運営・講師担当 / 受講生サポート / チャレンジ講師"},
    {"activity": "タダスク", "work": "タダスク関連打合せ【1講座ごと】", "price": 3000, "unit": "1講座",
     "desc": "ゲスト講師との事前打合せ（8時だョ）"},
    {"activity": "タダスク", "work": "タダマニュ関連", "price": 3000, "unit": "所要時間",
     "desc": "eラーニング企画・開発・保守 / コンテンツ作成 / 利用事業所対応"},
    {"activity": "タダスク", "work": "タダサポ（個別支援）関連", "price": 3000, "unit": "所要時間",
     "desc": "タダサポ対応（原則1回1h、年間10回まで）"},
    {"activity": "出張タダスク【新ルール】", "work": "フロント（新ルール）【開催日に包括算定】", "price": 5000, "unit": "1開催",
     "desc": "フロント業務一式（ヒアリング、連絡調整、サイト作成、kintone入力、司会進行、移動費）"},
    {"activity": "出張タダスク【新ルール】", "work": "フロントサポーター（新ルール）【開催日に包括算定】", "price": 3000, "unit": "1開催",
     "desc": "フロントサポーター業務一式"},
    {"activity": "出張タダスク【新ルール】", "work": "出張タダスク講師（新ルール）【開催日に包括算定】", "price": 5000, "unit": "開催時間",
     "desc": "講師業務一式（資料作成+研修登壇、上限2.5h）"},
    {"activity": "出張タダスク【旧ルール】", "work": "フロント・フロントサポーター（旧ルール）", "price": 4000, "unit": "所要時間",
     "desc": "主催者との事前打合せ/日程調整/事後フォロー/ポータルサイト作成"},
    {"activity": "出張タダスク【旧ルール】", "work": "出張タダスク講師（旧ルール）", "price": 3000, "unit": "所要時間",
     "desc": "当日の講師・ホスト・進行 / 資料作成（上限2h）/ フォローアップ"},
    {"activity": "タダレク", "work": "タダレク関連", "price": 3000, "unit": "所要時間",
     "desc": "出演者調整・打合せ / LP・フォーム制作 / 司会・Zoomホスト / 色んな企業とwin-winになり隊"},
    {"activity": "法人本部", "work": "タダカヨ経営戦略・業務管理", "price": 3500, "unit": "所要時間",
     "desc": "事業戦略 / 財務・経理・法務 / IT・システム運用 / 法人内教育 / 関連チーム業務"},
    {"activity": "法人本部", "work": "社内タダスク", "price": 5000, "unit": "1開催",
     "desc": "社内タダスク講師、資料作成"},
    {"activity": "法人本部", "work": "スペシャリスト業務", "price": 7000, "unit": "所要時間",
     "desc": "専門的な知見を持ったタダメン業務"},
    {"activity": "広報", "work": "タダカヨ広報関連", "price": 3000, "unit": "所要時間",
     "desc": "SNS・動画編集・YouTube / メルマガ / 営業活動 / 広報がんばり隊"},
    {"activity": "スポンサー＆業務委託対応", "work": "スポンサー対応（プロジェクトマネージャー業務）", "price": 4000, "unit": "所要時間",
     "desc": "プロジェクト全体の進捗管理 / メンバーへのディレクション / 社外担当者対応"},
    {"activity": "スポンサー＆業務委託対応", "work": "スポンサー対応（一般業務）", "price": 3000, "unit": "所要時間",
     "desc": "展示会サポート / セミナー企画・登壇 / 記事監修・執筆 / 行政委託事業 / スマート介護士を推進し隊"},
    {"activity": "スポンサー＆業務委託対応", "work": "令和7年度行政事業（共通）", "price": 5000, "unit": "所要時間",
     "desc": "経産省事業 / ケアプランデータ連携 / 神奈川県介護ロボット事業"},
    {"activity": "スポンサー＆業務委託対応", "work": "令和7年度行政事業（PM・経産省各リーダー担当者以上）", "price": 6000, "unit": "所要時間",
     "desc": "エリアリーダー / リージョンマネージャー / ケアプー事業PM・リーダー"},
    {"activity": "スポンサー＆業務委託対応", "work": "令和7年度行政事業（ケアプー：半日稼働）※日給制", "price": 15000, "unit": "稼働日",
     "desc": "ケアプー現地支援：3時間以内の稼働（時間欄は1.0hを入力）"},
    {"activity": "スポンサー＆業務委託対応", "work": "令和7年度行政事業（ケアプー：全日稼働）※日給制", "price": 30000, "unit": "稼働日",
     "desc": "ケアプー現地支援：6時間以内の稼働（時間欄は1.0hを入力）"},
    {"activity": "電話対応", "work": "待機時間", "price": 2000, "unit": "所要時間",
     "desc": "行政事業代表番号の受け答え / FAQ回答 / 問い合わせ連携"},
    {"activity": "電話対応", "work": "1件対応", "price": 1000, "unit": "所要時間",
     "desc": "待機時間1hのうち1件対応"},
    {"activity": "電話対応", "work": "2件対応", "price": 2000, "unit": "所要時間",
     "desc": "待機時間1hのうち2件対応"},
    {"activity": "電話対応", "work": "3件対応 or 合計30分以上対応", "price": 3000, "unit": "所要時間",
     "desc": "待機時間1hのうち3件以上 or 1件30分以上"},
    {"activity": "システム関連", "work": "オペレーション業務", "price": 3500, "unit": "所要時間",
     "desc": "ルーティン保守 / 簡易更新 / タダスクLP作成（ドキュメント不要）"},
    {"activity": "システム関連", "work": "テクニカル業務", "price": 5000, "unit": "所要時間",
     "desc": "設計・開発（ドキュメント必須）"},
    {"activity": "その他", "work": "イベント企画・運営関連", "price": 3000, "unit": "所要時間",
     "desc": "交流会企画・運営 / 展示会出展 / タダコミュ管理"},
    {"activity": "その他", "work": "社内イベント参加", "price": 1500, "unit": "1回参加分",
     "desc": "1,3,6ヶ月タダメンオリエンテーション参加"},
    {"activity": "その他", "work": "発送業務", "price": 2000, "unit": "所要時間",
     "desc": "発送業務全般"},
    {"activity": "その他", "work": "法人内MTG", "price": 2500, "unit": "所要時間",
     "desc": "各隊・各PJのMTG / 新タダメンオンボーディングMTG"},
    {"activity": "その他", "work": "その他（収益事業）", "price": 3000, "unit": "所要時間",
     "desc": "ファンドレイジング / イベント出展（収益） / もっと寄付を集め隊"},
    {"activity": "その他", "work": "新講師（メンティー）", "price": 5000, "unit": "包括算定",
     "desc": "新講師としてスキルアップ隊サポートを受けて稼働（2回まで）"},
    {"activity": "その他", "work": "チャレンジ講師（メンティー）", "price": 4000, "unit": "包括算定",
     "desc": "チャレンジ講師としてスキルアップ隊サポートを受けて稼働（3回まで）"},
    {"activity": "移動", "work": "移動時間", "price": 1500, "unit": "所要時間",
     "desc": "タダカヨ業務全般にかかる移動時間"},
    {"activity": "移動", "work": "自家用車使用", "price": 30, "unit": "移動距離(km)",
     "desc": "自家用車を使用した移動（30円/km）"},
]

# マスタからカテゴリリストを導出
ACTIVITY_CATEGORIES = list(dict.fromkeys(m["activity"] for m in GYOMU_MASTER))


def _get_work_categories(activity: str) -> list[dict]:
    """活動分類に紐づく業務分類リストを取得"""
    return [m for m in GYOMU_MASTER if m["activity"] == activity]


SPONSOR_LIST = [
    "善光会", "ケアプー事業（全国統一）", "神奈川県DX", "経産省PJ",
    "中央法規", "LINE WORKS", "ACG", "AUTOCARE", "オフィスニート",
    "Giver Link", "グッドツリー", "GLC", "Aba", "日本介護福祉士会",
    "山梨県庁", "お茶の水ケアサービス", "介安_島根県支部", "ケアきょう",
    "老健事業", "LYNXS",
]


@st.cache_data(ttl=300)
def _load_user_gyomu(user_email: str, year: int, month: int) -> pd.DataFrame:
    """ユーザーの業務報告を取得"""
    client = get_bq_client()
    query = f"""
    SELECT date, day_of_week, team, activity_category, work_category,
           sponsor, description, unit_price, hours, amount
    FROM `{APP_GYOMU_TABLE}`
    WHERE user_email = @email AND year = @year AND month = @month
    ORDER BY date DESC
    """
    job_config = bigquery.QueryJobConfig(query_parameters=[
        bigquery.ScalarQueryParameter("email", "STRING", user_email),
        bigquery.ScalarQueryParameter("year", "INT64", year),
        bigquery.ScalarQueryParameter("month", "INT64", month),
    ])
    try:
        return client.query(query, job_config=job_config).result().to_dataframe()
    except Exception:
        logger.warning("業務報告取得失敗: %s %d-%d", user_email, year, month)
        return pd.DataFrame()


@st.cache_data(ttl=300)
def _load_user_hojo(user_email: str, year: int, month: int) -> pd.DataFrame:
    """ユーザーの補助報告を取得"""
    client = get_bq_client()
    query = f"""
    SELECT hours, compensation, dx_subsidy, reimbursement, total_amount,
           monthly_complete, dx_receipt, expense_receipt
    FROM `{APP_HOJO_TABLE}`
    WHERE user_email = @email AND year = @year AND month = @month
    LIMIT 1
    """
    job_config = bigquery.QueryJobConfig(query_parameters=[
        bigquery.ScalarQueryParameter("email", "STRING", user_email),
        bigquery.ScalarQueryParameter("year", "INT64", year),
        bigquery.ScalarQueryParameter("month", "INT64", month),
    ])
    try:
        return client.query(query, job_config=job_config).result().to_dataframe()
    except Exception:
        logger.warning("補助報告取得失敗: %s %d-%d", user_email, year, month)
        return pd.DataFrame()


# ====================================================================
# 保存処理
# ====================================================================

def _save_gyomu(user_email: str, report_date: date, team: str,
                activity_category: str, work_category: str,
                sponsor: str, description: str,
                unit_price: float, hours: float, amount: float):
    """業務報告を保存（MERGE）"""
    client = get_bq_client()
    query = f"""
    MERGE `{APP_GYOMU_TABLE}` T
    USING (SELECT @email AS user_email, @date AS date,
                  @work_category AS work_category, @description AS description) S
    ON T.user_email = S.user_email AND T.date = S.date
       AND T.work_category = S.work_category AND T.description = S.description
    WHEN MATCHED THEN UPDATE SET
        year = @year, month = @month, day_of_week = @dow,
        team = @team, activity_category = @activity_category, sponsor = @sponsor,
        unit_price = @unit_price, hours = @hours, amount = @amount,
        updated_at = CURRENT_TIMESTAMP()
    WHEN NOT MATCHED THEN INSERT
        (user_email, date, year, month, day_of_week,
         team, activity_category, work_category, sponsor, description,
         unit_price, hours, amount, created_at, updated_at)
    VALUES
        (@email, @date, @year, @month, @dow,
         @team, @activity_category, @work_category, @sponsor, @description,
         @unit_price, @hours, @amount, CURRENT_TIMESTAMP(), CURRENT_TIMESTAMP())
    """
    dow = WEEKDAY_JP[report_date.weekday()]
    job_config = bigquery.QueryJobConfig(query_parameters=[
        bigquery.ScalarQueryParameter("email", "STRING", user_email),
        bigquery.ScalarQueryParameter("date", "DATE", report_date),
        bigquery.ScalarQueryParameter("year", "INT64", report_date.year),
        bigquery.ScalarQueryParameter("month", "INT64", report_date.month),
        bigquery.ScalarQueryParameter("dow", "STRING", dow),
        bigquery.ScalarQueryParameter("team", "STRING", team),
        bigquery.ScalarQueryParameter("activity_category", "STRING", activity_category),
        bigquery.ScalarQueryParameter("work_category", "STRING", work_category),
        bigquery.ScalarQueryParameter("sponsor", "STRING", sponsor),
        bigquery.ScalarQueryParameter("description", "STRING", description),
        bigquery.ScalarQueryParameter("unit_price", "FLOAT64", unit_price),
        bigquery.ScalarQueryParameter("hours", "FLOAT64", hours),
        bigquery.ScalarQueryParameter("amount", "FLOAT64", amount),
    ])
    client.query(query, job_config=job_config).result()
    _load_user_gyomu.clear()


def _save_hojo(user_email: str, year: int, month: int,
               hours: float, compensation: float, dx_subsidy: float,
               reimbursement: float, total_amount: float,
               monthly_complete: bool, dx_receipt: str, expense_receipt: str):
    """補助報告を保存（MERGE）"""
    client = get_bq_client()
    query = f"""
    MERGE `{APP_HOJO_TABLE}` T
    USING (SELECT @email AS user_email, @year AS year, @month AS month) S
    ON T.user_email = S.user_email AND T.year = S.year AND T.month = S.month
    WHEN MATCHED THEN UPDATE SET
        hours = @hours, compensation = @compensation,
        dx_subsidy = @dx_subsidy, reimbursement = @reimbursement,
        total_amount = @total_amount, monthly_complete = @monthly_complete,
        dx_receipt = @dx_receipt, expense_receipt = @expense_receipt,
        updated_at = CURRENT_TIMESTAMP()
    WHEN NOT MATCHED THEN INSERT
        (user_email, year, month, hours, compensation, dx_subsidy,
         reimbursement, total_amount, monthly_complete,
         dx_receipt, expense_receipt, created_at, updated_at)
    VALUES
        (@email, @year, @month, @hours, @compensation, @dx_subsidy,
         @reimbursement, @total_amount, @monthly_complete,
         @dx_receipt, @expense_receipt, CURRENT_TIMESTAMP(), CURRENT_TIMESTAMP())
    """
    job_config = bigquery.QueryJobConfig(query_parameters=[
        bigquery.ScalarQueryParameter("email", "STRING", user_email),
        bigquery.ScalarQueryParameter("year", "INT64", year),
        bigquery.ScalarQueryParameter("month", "INT64", month),
        bigquery.ScalarQueryParameter("hours", "FLOAT64", hours),
        bigquery.ScalarQueryParameter("compensation", "FLOAT64", compensation),
        bigquery.ScalarQueryParameter("dx_subsidy", "FLOAT64", dx_subsidy),
        bigquery.ScalarQueryParameter("reimbursement", "FLOAT64", reimbursement),
        bigquery.ScalarQueryParameter("total_amount", "FLOAT64", total_amount),
        bigquery.ScalarQueryParameter("monthly_complete", "BOOL", monthly_complete),
        bigquery.ScalarQueryParameter("dx_receipt", "STRING", dx_receipt),
        bigquery.ScalarQueryParameter("expense_receipt", "STRING", expense_receipt),
    ])
    client.query(query, job_config=job_config).result()
    _load_user_hojo.clear()


def _delete_gyomu(user_email: str, report_date: date,
                  work_category: str, description: str):
    """業務報告を削除（UI側の削除ボタンは今後実装予定）"""
    client = get_bq_client()
    query = f"""
    DELETE FROM `{APP_GYOMU_TABLE}`
    WHERE user_email = @email AND date = @date
      AND work_category = @work_category AND description = @description
    """
    job_config = bigquery.QueryJobConfig(query_parameters=[
        bigquery.ScalarQueryParameter("email", "STRING", user_email),
        bigquery.ScalarQueryParameter("date", "DATE", report_date),
        bigquery.ScalarQueryParameter("work_category", "STRING", work_category),
        bigquery.ScalarQueryParameter("description", "STRING", description),
    ])
    client.query(query, job_config=job_config).result()
    _load_user_gyomu.clear()


# ====================================================================
# UIヘルパー
# ====================================================================


def _get_field(row, field: str, default=0.0) -> float:
    """DataFrameの行からフィールド値を安全に取得"""
    if field in row:
        val = row[field]
        if pd.notna(val):
            return float(val)
    return default


# ====================================================================
# サイドバー
# ====================================================================

with st.sidebar:
    st.markdown("#### 対象年月")
    _sel_year, _sel_month = render_sidebar_year_month(
        year_key="report_year", month_key="report_month",
    )
    try:
        selected_year = int(_sel_year)
        selected_month = int(_sel_month)
    except (ValueError, TypeError):
        selected_year = date.today().year
        selected_month = date.today().month

# ====================================================================
# タブ構成
# ====================================================================

tab_gyomu, tab_hojo = st.tabs(["業務報告（日次）", "補助報告（月次）"])

# ====================================================================
# Tab 1: 業務報告（日次）
# ====================================================================

with tab_gyomu:
    st.subheader("業務報告を入力")

    # --- 隊（チーム）選択 ---
    sel_team = st.selectbox("隊", ["（なし）"] + TEAM_LIST, key="gyomu_team")
    if sel_team == "（なし）":
        sel_team = ""

    # --- 活動分類 → 業務分類 カスケード選択（form外で即時反応） ---
    sel_ac = st.selectbox("活動分類", ACTIVITY_CATEGORIES, key="gyomu_ac")

    # 選択した活動分類に紐づく業務分類を取得
    work_items = _get_work_categories(sel_ac) or _get_work_categories(ACTIVITY_CATEGORIES[0])
    work_labels = [m["work"] for m in work_items]
    sel_wc = st.selectbox("業務分類", work_labels, key="gyomu_wc")
    selected_master = next((m for m in work_items if m["work"] == sel_wc), work_items[0])
    default_price = float(selected_master["price"])

    # 業務内容の例をヘルプとして表示
    st.caption(f"例: {selected_master['desc']}　｜　算定: {selected_master['unit']}")

    # スポンサー
    sel_sp = st.selectbox("スポンサー", ["（なし）"] + SPONSOR_LIST + ["その他（手入力）"], key="gyomu_sp")
    if sel_sp == "その他（手入力）":
        sel_sp = st.text_input("スポンサーを入力", key="gyomu_sp_other")
    elif sel_sp == "（なし）":
        sel_sp = ""

    # 時間/距離のラベル切替
    is_car = sel_wc == "自家用車使用"
    hours_label = "距離 (km)" if is_car else "時間 (h)"

    # フォーム
    with st.form("gyomu_form"):
        _today = date.today()
        _default_date = date(selected_year, selected_month, min(_today.day, 28))
        report_date = st.date_input("日付", value=_default_date, key="gyomu_date")

        description = st.text_area("業務内容", key="gyomu_desc", height=80)

        col_p, col_h, col_a = st.columns(3)
        with col_p:
            unit_price = st.number_input("単価 (円/h)", min_value=0.0, value=default_price,
                                         step=100.0, key="gyomu_price")
        with col_h:
            hours_val = st.number_input(hours_label, min_value=0.0, step=0.5, key="gyomu_hours")
        with col_a:
            auto_amount = unit_price * hours_val
            amount = st.number_input("金額", min_value=0.0, value=auto_amount, step=100.0, key="gyomu_amount")

        submitted = st.form_submit_button("保存", use_container_width=True)

        if submitted:
            errors = []
            if not sel_wc:
                errors.append("業務分類を選択してください")
            if not description.strip():
                errors.append("業務内容を入力してください")
            if hours_val <= 0:
                errors.append(f"{hours_label}を入力してください")

            if errors:
                for e in errors:
                    st.error(e)
            else:
                try:
                    _save_gyomu(email, report_date, sel_team, sel_ac, sel_wc,
                                sel_sp, description.strip(), unit_price, hours_val, amount)
                    st.toast("業務報告を保存しました")
                    st.rerun()
                except Exception as exc:
                    logger.error("業務報告保存失敗: %s", exc, exc_info=True)
                    st.error(f"保存に失敗しました: {exc}")

    # --- 入力済みデータ一覧 ---
    st.divider()
    df_gyomu = _load_user_gyomu(email, selected_year, selected_month)

    if df_gyomu.empty:
        st.info(f"{selected_year}年{selected_month}月の業務報告はまだありません")
    else:
        st.subheader(f"入力済み業務報告（{len(df_gyomu)}件）")
        display_cols = {
            "date": "日付", "day_of_week": "曜日", "team": "隊",
            "activity_category": "活動分類", "work_category": "業務分類",
            "sponsor": "スポンサー", "description": "内容",
            "unit_price": "単価", "hours": "時間", "amount": "金額",
        }
        available_cols = [c for c in display_cols if c in df_gyomu.columns]
        st.dataframe(
            df_gyomu[available_cols].rename(columns=display_cols),
            use_container_width=True,
            hide_index=True,
            height=min(400, 35 * len(df_gyomu) + 38),
        )

# ====================================================================
# Tab 2: 補助報告（月次）
# ====================================================================

with tab_hojo:
    st.subheader("補助報告を入力")
    st.caption(f"対象: {selected_year}年{selected_month}月")

    # 既存データがあればプリフィル
    df_hojo = _load_user_hojo(email, selected_year, selected_month)
    has_existing = not df_hojo.empty
    existing = df_hojo.iloc[0] if has_existing else {}

    if has_existing:
        st.info("既存データがあります。変更して保存すると上書きされます。")

    with st.form("hojo_form"):
        col1, col2 = st.columns(2)
        with col1:
            h_hours = st.number_input("時間", min_value=0.0, step=0.5,
                                      value=_get_field(existing, "hours"), key="hojo_hours")
            h_compensation = st.number_input("報酬", min_value=0.0, step=1000.0,
                                             value=_get_field(existing, "compensation"), key="hojo_comp")
        with col2:
            h_dx = st.number_input("DX補助", min_value=0.0, step=1000.0,
                                   value=_get_field(existing, "dx_subsidy"), key="hojo_dx")
            h_reimb = st.number_input("立替", min_value=0.0, step=100.0,
                                      value=_get_field(existing, "reimbursement"), key="hojo_reimb")

        h_total = h_compensation + h_dx + h_reimb
        st.metric("総額（自動計算）", f"¥{h_total:,.0f}")

        h_complete = st.checkbox(
            "当月入力完了",
            value=bool(existing.get("monthly_complete", False)),
            key="hojo_complete",
        )

        col_r1, col_r2 = st.columns(2)
        with col_r1:
            h_dx_receipt = st.text_area(
                "DX補助用 領収書メモ", height=60,
                value=str(existing.get("dx_receipt", "") or ""),
                key="hojo_dx_receipt",
            )
        with col_r2:
            h_exp_receipt = st.text_area(
                "個人立替用 領収書メモ", height=60,
                value=str(existing.get("expense_receipt", "") or ""),
                key="hojo_exp_receipt",
            )

        submitted_hojo = st.form_submit_button("保存", use_container_width=True)

        if submitted_hojo:
            try:
                _save_hojo(email, selected_year, selected_month,
                           h_hours, h_compensation, h_dx, h_reimb, h_total,
                           h_complete, h_dx_receipt.strip(), h_exp_receipt.strip())
                st.toast("補助報告を保存しました")
                st.rerun()
            except Exception as exc:
                logger.error("補助報告保存失敗: %s", exc, exc_info=True)
                st.error(f"保存に失敗しました: {exc}")
