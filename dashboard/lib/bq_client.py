"""共有BigQueryクライアント"""

from typing import Optional

import pandas as pd
import streamlit as st
from google.cloud import bigquery

from lib.constants import (
    DATASET,
    PROJECT_ID,
    TEAM_BUDGET_ACTUALS_VIEW,
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

    Returns:
        columns: year, month, team, actual_amount, actual_count, reporter_count,
                 budget_amount, achievement_rate, diff_amount, has_budget, has_actual
    """
    client = get_bq_client()
    sql = f"""
    SELECT year, month, team, actual_amount, actual_count, reporter_count,
           budget_amount, achievement_rate, diff_amount, has_budget, has_actual
    FROM `{TEAM_BUDGET_ACTUALS_VIEW}`
    WHERE year BETWEEN @y_start AND @y_end
      AND month BETWEEN @m_start AND @m_end
    ORDER BY year, month, team
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
    """期間内に予算 or 実額が存在する全 active 隊の一覧 (ttl=10 分、マスタ系)。"""
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


@st.cache_data(ttl=300)
def compute_current_hashes(
    year: int, month: int, teams: tuple[str, ...]
) -> dict[str, str]:
    """各隊の現在の actual_data_hash を計算 (spec §6.6)。

    team_monthly_eval.actual_data_hash と突き合わせて outdated バッジ表示に使う。
    引数 teams は cache key 化のため tuple で受ける。

    Returns:
        {team: data_hash}
    """
    if not teams:
        return {}
    client = get_bq_client()
    sql = f"""
    WITH rows AS (
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
    FROM rows
    GROUP BY team
    """
    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter("year", "INT64", year),
            bigquery.ScalarQueryParameter("month", "INT64", month),
            bigquery.ArrayQueryParameter("teams", "STRING", list(teams)),
        ]
    )
    return {
        row["team"]: row["data_hash"]
        for row in client.query(sql, job_config=job_config).result()
    }
