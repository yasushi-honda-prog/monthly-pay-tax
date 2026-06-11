"""team_hierarchy テーブルへの BQ DML 関数 (PR-F)

PR-E で構築した team_hierarchy テーブルを dashboard から編集するための repository。
DML 関数を page から分離することで、page 側は UI ロジックのみ、本モジュールは
BQ アクセスのみという責務分離を実現。

主要関数:
    - fetch_hierarchy: 全行取得 (DataFrame)
    - fetch_unmapped_activity_categories: UNMAPPED 隊リスト
    - fetch_distinct_leader_teams: 既存の統括隊名 distinct リスト
    - upsert_hierarchy_row: MERGE (optimistic lock 付き)
    - rename_leader_team: leader_team の一括 UPDATE
    - delete_hierarchy_row: 単一行 DELETE
"""

from __future__ import annotations

from typing import Optional

import pandas as pd
from google.cloud import bigquery

from lib.bq_client import get_bq_client
from lib.constants import TEAM_HIERARCHY_TABLE, TEAM_HIERARCHY_COVERAGE_VIEW


def fetch_hierarchy(client: Optional[bigquery.Client] = None) -> pd.DataFrame:
    """team_hierarchy の全行を DataFrame で取得。

    Returns:
        columns: activity_category, leader_team, leader_team_type, note,
                 version, updated_at, updated_by
    """
    client = client or get_bq_client()
    query = f"""
    SELECT activity_category, leader_team, leader_team_type, note,
           version, updated_at, updated_by
    FROM `{TEAM_HIERARCHY_TABLE}`
    ORDER BY leader_team, activity_category
    """
    return client.query(query).to_dataframe()


def fetch_unmapped_activity_categories(
    client: Optional[bigquery.Client] = None,
) -> pd.DataFrame:
    """v_team_hierarchy_coverage から UNMAPPED 隊を取得。

    Returns:
        columns: activity_category (UNMAPPED のもの。gyomu 出現するが hierarchy 未定義)
    """
    client = client or get_bq_client()
    query = f"""
    SELECT activity_category
    FROM `{TEAM_HIERARCHY_COVERAGE_VIEW}`
    WHERE status = 'UNMAPPED'
    ORDER BY activity_category
    """
    return client.query(query).to_dataframe()


def fetch_distinct_leader_teams(
    client: Optional[bigquery.Client] = None,
) -> list[str]:
    """team_hierarchy で既出の統括隊名 distinct リストを取得 (UI selectbox 用)。"""
    client = client or get_bq_client()
    query = f"""
    SELECT DISTINCT leader_team
    FROM `{TEAM_HIERARCHY_TABLE}`
    ORDER BY leader_team
    """
    return [row.leader_team for row in client.query(query).result()]


_COMMON_USING = """
USING (SELECT @activity_category AS activity_category,
              @leader_team AS leader_team,
              @leader_team_type AS leader_team_type,
              @note AS note,
              @actor AS actor) s
ON t.activity_category = s.activity_category
""".strip()

_MATCHED_UPDATE = """
UPDATE SET leader_team = s.leader_team,
           leader_team_type = s.leader_team_type,
           note = s.note,
           version = t.version + 1,
           updated_at = CURRENT_TIMESTAMP(),
           updated_by = s.actor
""".strip()

_NOT_MATCHED_INSERT = """
INSERT (activity_category, leader_team, leader_team_type, note, version,
        created_at, created_by, updated_at, updated_by)
VALUES (s.activity_category, s.leader_team, s.leader_team_type, s.note, 1,
        CURRENT_TIMESTAMP(), s.actor, CURRENT_TIMESTAMP(), s.actor)
""".strip()


def _scalar_params(activity_category: str, leader_team: str, leader_team_type: str,
                   note: Optional[str], actor: str) -> list[bigquery.ScalarQueryParameter]:
    return [
        bigquery.ScalarQueryParameter("activity_category", "STRING", activity_category),
        bigquery.ScalarQueryParameter("leader_team", "STRING", leader_team),
        bigquery.ScalarQueryParameter("leader_team_type", "STRING", leader_team_type),
        bigquery.ScalarQueryParameter("note", "STRING", note),
        bigquery.ScalarQueryParameter("actor", "STRING", actor),
    ]


def insert_hierarchy_row(
    activity_category: str,
    leader_team: str,
    leader_team_type: str,
    note: Optional[str],
    actor: str,
    *,
    client: Optional[bigquery.Client] = None,
) -> int:
    """新規追加 (UNMAPPED 補完用)。既存があれば force で上書き。

    UNMAPPED の隊を「初回登録」する用途。既存行があれば現在値を上書きするが、
    その場合は本来 update_hierarchy_row を呼ぶべきなので、UI 側で UNMAPPED に
    限定して呼び出すことで誤上書きを防ぐ。

    Returns:
        affected_rows (1 = 成功)
    """
    client = client or get_bq_client()
    sql = f"""
    MERGE `{TEAM_HIERARCHY_TABLE}` t
    {_COMMON_USING}
    WHEN MATCHED THEN
      {_MATCHED_UPDATE}
    WHEN NOT MATCHED THEN
      {_NOT_MATCHED_INSERT}
    """
    params = _scalar_params(activity_category, leader_team, leader_team_type, note, actor)
    job = client.query(sql, job_config=bigquery.QueryJobConfig(query_parameters=params))
    job.result()
    return job.num_dml_affected_rows or 0


def update_hierarchy_row(
    activity_category: str,
    leader_team: str,
    leader_team_type: str,
    note: Optional[str],
    actor: str,
    expected_version: int,
    *,
    client: Optional[bigquery.Client] = None,
) -> int:
    """既存行を optimistic lock で UPDATE のみ (削除済み行への再 INSERT 防止)。

    Codex H1 反映: optimistic 版で WHEN NOT MATCHED を持つと、画面表示後に
    別ユーザーが行を削除した場合、保存操作で削除済み行を再 INSERT してしまう。
    本関数は UPDATE のみ実行し、行が存在しない/lock 競合の場合は affected=0 を返す。

    Returns:
        affected_rows (0 = lock 競合 or 行削除済み)
    """
    client = client or get_bq_client()
    sql = f"""
    UPDATE `{TEAM_HIERARCHY_TABLE}`
    SET leader_team = @leader_team,
        leader_team_type = @leader_team_type,
        note = @note,
        version = version + 1,
        updated_at = CURRENT_TIMESTAMP(),
        updated_by = @actor
    WHERE activity_category = @activity_category
      AND version = @expected_version
    """
    params = _scalar_params(activity_category, leader_team, leader_team_type, note, actor)
    params.append(
        bigquery.ScalarQueryParameter("expected_version", "INT64", expected_version),
    )
    job = client.query(sql, job_config=bigquery.QueryJobConfig(query_parameters=params))
    job.result()
    return job.num_dml_affected_rows or 0


def rename_leader_team(
    old_name: str,
    new_name: str,
    actor: str,
    *,
    client: Optional[bigquery.Client] = None,
) -> int:
    """leader_team を一括 UPDATE で書き換える (統括隊名のリネーム用)。

    既存 team_budgets_quarterly の leader_team も連動で書き換える必要があるが、
    PR-F のスコープ外 (本田様判断: team_hierarchy のみ編集対象)。
    rename 後に CSV 再投入で予算側も合わせる運用とする。

    Returns:
        affected_rows (rename 対象の行数)
    """
    if not new_name.strip():
        raise ValueError("new_name が空文字")
    if old_name == new_name:
        return 0
    client = client or get_bq_client()
    sql = f"""
    UPDATE `{TEAM_HIERARCHY_TABLE}`
    SET leader_team = @new_name,
        version = version + 1,
        updated_at = CURRENT_TIMESTAMP(),
        updated_by = @actor
    WHERE leader_team = @old_name
    """
    params = [
        bigquery.ScalarQueryParameter("new_name", "STRING", new_name),
        bigquery.ScalarQueryParameter("old_name", "STRING", old_name),
        bigquery.ScalarQueryParameter("actor", "STRING", actor),
    ]
    job = client.query(sql, job_config=bigquery.QueryJobConfig(query_parameters=params))
    job.result()
    return job.num_dml_affected_rows or 0


def delete_hierarchy_row(
    activity_category: str,
    *,
    client: Optional[bigquery.Client] = None,
) -> int:
    """activity_category 行を DELETE。

    削除しても gyomu_reports / team_budgets_quarterly 側に影響なし
    (整合性は v_team_hierarchy_coverage で監視)。

    Returns:
        affected_rows (1 なら成功、0 なら対象なし)
    """
    client = client or get_bq_client()
    sql = f"""
    DELETE FROM `{TEAM_HIERARCHY_TABLE}`
    WHERE activity_category = @activity_category
    """
    params = [
        bigquery.ScalarQueryParameter("activity_category", "STRING", activity_category),
    ]
    job = client.query(sql, job_config=bigquery.QueryJobConfig(query_parameters=params))
    job.result()
    return job.num_dml_affected_rows or 0
