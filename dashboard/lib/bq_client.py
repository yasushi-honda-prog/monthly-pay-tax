"""共有BigQueryクライアント"""

from typing import Optional

import pandas as pd
import streamlit as st
from google.cloud import bigquery

from lib.constants import (
    DATASET,
    FISCAL_QUARTER_UDF,
    PROJECT_ID,
    TEAM_BUDGET_ACTUALS_VIEW,
    TEAM_BUDGETS_QUARTERLY_TABLE,
    TEAM_MONTHLY_EVAL_TABLE,
)


@st.cache_resource
def get_bq_client():
    return bigquery.Client(project=PROJECT_ID)


@st.cache_data(ttl=21600)
def load_data(query: str):
    client = get_bq_client()
    return client.query(query).to_dataframe()


# ----- 予実管理 (PR-D) -----


@st.cache_data(ttl=300)
def load_team_budget_actuals(
    year_start: int, year_end: int, month_start: int, month_end: int
) -> pd.DataFrame:
    """v_team_budget_actuals から期間内の予実データを取得 (spec §6.6, ttl=5 分)。

    PR-A (2026-06-12) で leader_team 列を追加。team_hierarchy INNER JOIN により
    operating 統括隊配下の隊のみ取得 (非「隊」活動分類は VIEW 層で根本除外)。

    Returns:
        columns: year, month, team, leader_team, actual_amount, actual_count,
                 reporter_count, budget_amount, achievement_rate, diff_amount,
                 has_budget, has_actual
    """
    client = get_bq_client()
    sql = f"""
    SELECT year, month, team, leader_team, actual_amount, actual_count,
           reporter_count, budget_amount, achievement_rate, diff_amount,
           has_budget, has_actual
    FROM `{TEAM_BUDGET_ACTUALS_VIEW}`
    WHERE year BETWEEN @y_start AND @y_end
      AND month BETWEEN @m_start AND @m_end
    ORDER BY leader_team, team, year, month
    """
    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter("y_start", "INT64", year_start),
            bigquery.ScalarQueryParameter("y_end", "INT64", year_end),
            bigquery.ScalarQueryParameter("m_start", "INT64", month_start),
            bigquery.ScalarQueryParameter("m_end", "INT64", month_end),
        ]
    )
    return client.query(sql, job_config=job_config).to_dataframe()


@st.cache_data(ttl=300)
def load_team_monthly_eval(
    year: int, month: int, team: Optional[str] = None
) -> pd.DataFrame:
    """team_monthly_eval から評価データを取得 (spec §6.6, ttl=5 分)。

    team=None なら (year, month) の全隊、指定ありなら 1 隊だけ。
    """
    client = get_bq_client()
    if team is None:
        sql = f"""
        SELECT year, month, team, actual_amount, budget_amount, achievement_rate,
               diff_amount, actual_data_hash, ai_comment, ai_model, prompt_version,
               generated_at, generated_by
        FROM `{TEAM_MONTHLY_EVAL_TABLE}`
        WHERE year = @year AND month = @month
        ORDER BY team
        """
        params = [
            bigquery.ScalarQueryParameter("year", "INT64", year),
            bigquery.ScalarQueryParameter("month", "INT64", month),
        ]
    else:
        sql = f"""
        SELECT year, month, team, actual_amount, budget_amount, achievement_rate,
               diff_amount, actual_data_hash, ai_comment, ai_model, prompt_version,
               generated_at, generated_by
        FROM `{TEAM_MONTHLY_EVAL_TABLE}`
        WHERE year = @year AND month = @month AND team = @team
        LIMIT 1
        """
        params = [
            bigquery.ScalarQueryParameter("year", "INT64", year),
            bigquery.ScalarQueryParameter("month", "INT64", month),
            bigquery.ScalarQueryParameter("team", "STRING", team),
        ]
    job_config = bigquery.QueryJobConfig(query_parameters=params)
    return client.query(sql, job_config=job_config).to_dataframe()


@st.cache_data(ttl=600)
def load_active_teams(
    year_start: int, year_end: int, month_start: int, month_end: int
) -> list[str]:
    """期間内に予算 or 実額が存在する全 active 隊の一覧 (ttl=10 分、マスタ系)。

    PR-A (2026-06-12) で v_team_budget_actuals が team_hierarchy INNER JOIN
    によって 隊 (operating 統括隊配下) のみに絞られたため、本関数も自動的に
    非「隊」を除外する (VIEW 層フィルタ任せ、UI 二重フィルタは持たない方針)。
    """
    client = get_bq_client()
    sql = f"""
    SELECT DISTINCT team
    FROM `{TEAM_BUDGET_ACTUALS_VIEW}`
    WHERE year BETWEEN @y_start AND @y_end
      AND month BETWEEN @m_start AND @m_end
      AND team IS NOT NULL AND team != ''
    ORDER BY team
    """
    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter("y_start", "INT64", year_start),
            bigquery.ScalarQueryParameter("y_end", "INT64", year_end),
            bigquery.ScalarQueryParameter("m_start", "INT64", month_start),
            bigquery.ScalarQueryParameter("m_end", "INT64", month_end),
        ]
    )
    return [row["team"] for row in client.query(sql, job_config=job_config).result()]


@st.cache_data(ttl=600)
def load_leader_team_yearly_monthly_budgets(year: int) -> dict[int, float]:
    """指定 year の 12 ヶ月分の統括隊月予算合計を返す (hotfix 2026-06-13)。

    全体タブの月次推移グラフ用。各月について
    `team_budgets_quarterly` から fiscal_quarter UDF 経由で四半期予算を引き、
    SUM(全統括隊×全カテゴリ予算) / 3 を月予算とする。

    本田様要望: 全体タブは「統括隊レベル集約」、隊×月予算 (team_budgets)
    ではなく統括隊予算 (team_budgets_quarterly) を月次推移グラフに反映する。

    Returns:
        {month: monthly_budget}  (12 ヶ月、未投入月は 0.0)
    """
    client = get_bq_client()
    sql = f"""
    WITH months AS (
      SELECT m AS month,
             {FISCAL_QUARTER_UDF}(@year, m).fiscal_year AS fy,
             {FISCAL_QUARTER_UDF}(@year, m).fiscal_quarter AS fq
      FROM UNNEST(GENERATE_ARRAY(1, 12)) AS m
    ),
    quarterly_totals AS (
      SELECT fiscal_year, fiscal_quarter,
             SUM(budget_amount) AS total_quarterly
      FROM `{TEAM_BUDGETS_QUARTERLY_TABLE}`
      GROUP BY fiscal_year, fiscal_quarter
    )
    SELECT m.month,
           IFNULL(SAFE_DIVIDE(q.total_quarterly, 3), 0) AS monthly_budget
    FROM months m
    LEFT JOIN quarterly_totals q
      ON m.fy = q.fiscal_year AND m.fq = q.fiscal_quarter
    ORDER BY m.month
    """
    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter("year", "INT64", year),
        ]
    )
    return {
        int(row["month"]): float(row["monthly_budget"])
        for row in client.query(sql, job_config=job_config).result()
    }


@st.cache_data(ttl=600)
def load_leader_team_monthly_budgets(year: int, month: int) -> pd.DataFrame:
    """指定 (year, month) の統括隊別 月予算を team_budgets_quarterly から算出 (PR-Q2M)。

    四半期予算の各カテゴリ合計を 3 等分して月予算とする (本田様判断:
    四半期予算 / 3 = 1 月あたりの統括隊予算)。fiscal_quarter UDF で
    暦年月 → fiscal (year, quarter) を取得し、その四半期の合計を集計。

    team_budgets_quarterly が空 (=データ未投入) の場合は空 DataFrame を返す。

    Returns:
        columns: leader_team (STRING), monthly_budget (NUMERIC)
        leader_team の昇順でソート
    """
    client = get_bq_client()
    sql = f"""
    WITH fy AS (
      SELECT
        {FISCAL_QUARTER_UDF}(@year, @month).fiscal_year AS fiscal_year,
        {FISCAL_QUARTER_UDF}(@year, @month).fiscal_quarter AS fiscal_quarter
    )
    SELECT
      q.leader_team,
      SAFE_DIVIDE(SUM(q.budget_amount), 3) AS monthly_budget
    FROM `{TEAM_BUDGETS_QUARTERLY_TABLE}` q
    CROSS JOIN fy
    WHERE q.fiscal_year = fy.fiscal_year
      AND q.fiscal_quarter = fy.fiscal_quarter
    GROUP BY q.leader_team
    ORDER BY q.leader_team
    """
    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter("year", "INT64", year),
            bigquery.ScalarQueryParameter("month", "INT64", month),
        ]
    )
    return client.query(sql, job_config=job_config).to_dataframe()


@st.cache_data(ttl=600)
def load_active_leader_teams(
    year_start: int, year_end: int, month_start: int, month_end: int
) -> list[str]:
    """期間内に予算 or 実額が存在する全 active 統括隊の一覧 (PR-A、ttl=10 分)。

    v_team_budget_actuals の INNER JOIN により operating の統括隊のみが返る。
    UI の統括隊フィルタ selectbox / 統括隊タブのランキング軸として使用。
    """
    client = get_bq_client()
    sql = f"""
    SELECT DISTINCT leader_team
    FROM `{TEAM_BUDGET_ACTUALS_VIEW}`
    WHERE year BETWEEN @y_start AND @y_end
      AND month BETWEEN @m_start AND @m_end
      AND leader_team IS NOT NULL AND leader_team != ''
    ORDER BY leader_team
    """
    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter("y_start", "INT64", year_start),
            bigquery.ScalarQueryParameter("y_end", "INT64", year_end),
            bigquery.ScalarQueryParameter("m_start", "INT64", month_start),
            bigquery.ScalarQueryParameter("m_end", "INT64", month_end),
        ]
    )
    return [
        row["leader_team"]
        for row in client.query(sql, job_config=job_config).result()
    ]


@st.cache_data(ttl=300)
def compute_current_hashes(
    year: int, month: int, teams: tuple[str, ...],
    prompt_version: str,
) -> dict[str, str]:
    """各隊の現在の actual_data_hash を計算 (spec §6.6 + 2026-06-13 拡張)。

    2026-06-13 拡張: 既存 BQ SQL hash (gyomu_reports 集計) に加え、
    team_budgets.budget_amount と prompt_version を Python 側で合成して
    composite hash を返す。これにより予算編集時にも outdated 判定が発火する
    (docs/specs/2026-06-13-team-monthly-budget-input.md §4.2 / §5.3)。

    code-review MEDIUM: prompt_version を関数引数化することで cache key に
    含め、env var 変更時の stale cache を防ぐ。呼び出し側は lib.constants から
    import して渡す責務。

    team_monthly_eval.actual_data_hash と突き合わせて outdated バッジ表示に使う。
    引数 teams は cache key 化のため tuple で受ける。

    Returns:
        {team: composite_hash}
    """
    if not teams:
        return {}
    from lib.team_budget_hash import compose_actual_data_hash
    client = get_bq_client()
    # CTE 名に `rows` は使わない (BigQuery の予約語 ROWS と衝突して
    #  "Unexpected keyword ROWS" 構文エラーになる)。
    sql = f"""
    WITH row_data AS (
      SELECT
        g.activity_category AS team,
        TO_JSON_STRING(STRUCT(
          g.activity_category, g.date, g.source_url, g.work_category, g.sponsor,
          g.description, g.unit_price, g.hours, g.amount
        )) AS row_json,
        TO_HEX(SHA256(TO_JSON_STRING(STRUCT(
          g.activity_category, g.date, g.source_url, g.work_category, g.sponsor,
          g.description, g.unit_price, g.hours, g.amount
        )))) AS row_hash
      FROM `{PROJECT_ID}.{DATASET}.gyomu_reports` g
      WHERE SAFE_CAST(g.year AS INT64) = @year
        AND `{PROJECT_ID}.{DATASET}`.extract_month(g.date) = @month
        AND g.activity_category IN UNNEST(@teams)
    )
    SELECT team,
           IFNULL(
             TO_HEX(SHA256(STRING_AGG(row_hash, '' ORDER BY row_hash, row_json))),
             ''
           ) AS data_hash
    FROM row_data
    GROUP BY team
    """
    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter("year", "INT64", year),
            bigquery.ScalarQueryParameter("month", "INT64", month),
            bigquery.ArrayQueryParameter("teams", "STRING", list(teams)),
        ]
    )
    bq_hashes = {
        row["team"]: row["data_hash"]
        for row in client.query(sql, job_config=job_config).result()
    }
    # データなし隊は cloud-run 側の hash 計算と整合させるため "" を入れる
    # (cloud-run/vertex_evaluator.compute_actual_data_hash も IFNULL(..., '') で
    #  「データなし」を空文字として表現する。dashboard 側で None のままだと
    #  is_outdated が「未判定」と扱い、データ削除を outdated と検知できない)
    bq_hashes = {team: bq_hashes.get(team, "") for team in teams}

    # team_budgets から budget_amount を一括取得 (UNNEST IN で 1 query)
    budget_sql = f"""
    SELECT team, budget_amount
    FROM `{PROJECT_ID}.{DATASET}.team_budgets`
    WHERE year = @year AND month = @month
      AND team IN UNNEST(@teams)
    """
    budget_job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter("year", "INT64", year),
            bigquery.ScalarQueryParameter("month", "INT64", month),
            bigquery.ArrayQueryParameter("teams", "STRING", list(teams)),
        ]
    )
    budgets = {
        row["team"]: row["budget_amount"]
        for row in client.query(budget_sql, job_config=budget_job_config).result()
    }
    # 未設定隊は None で composite に渡す
    return {
        team: compose_actual_data_hash(
            bq_hashes[team], budgets.get(team), prompt_version
        )
        for team in teams
    }
