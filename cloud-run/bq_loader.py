"""BigQueryデータ投入モジュール

pandas DataFrame → BigQuery load_table_from_dataframe でバッチ投入。
"""

import logging
from datetime import datetime, timezone

import pandas as pd
from google.cloud import bigquery

import config

logger = logging.getLogger(__name__)


def _build_bq_client() -> bigquery.Client:
    """BigQueryクライアントを構築"""
    return bigquery.Client(project=config.GCP_PROJECT_ID)


def _rows_to_dataframe(rows: list[list], columns: list[str]) -> pd.DataFrame:
    """2次元配列をDataFrameに変換

    GASのデータは列数が不揃いの場合があるため、不足分をNoneで埋める。
    """
    normalized = []
    expected_cols = len(columns)

    for row in rows:
        if len(row) < expected_cols:
            row = row + [None] * (expected_cols - len(row))
        elif len(row) > expected_cols:
            row = row[:expected_cols]
        # 全値を文字列に変換（BQスキーマがSTRING）
        normalized.append([str(v) if v is not None else None for v in row])

    df = pd.DataFrame(normalized, columns=columns)
    df["ingested_at"] = datetime.now(timezone.utc)
    return df


def load_to_bigquery(table_name: str, rows: list[list]) -> int:
    """データをBigQueryテーブルにロード

    既存データを削除（WRITE_TRUNCATE）してから書き込み（GASと同じ動作）。

    Returns:
        投入した行数
    """
    if not rows:
        logger.info("テーブル %s: 書き込むデータなし", table_name)
        return 0

    columns = config.TABLE_COLUMNS.get(table_name)
    if not columns:
        raise ValueError(f"テーブル {table_name} のカラム定義が見つかりません")

    client = _build_bq_client()
    table_id = f"{config.GCP_PROJECT_ID}.{config.BQ_DATASET}.{table_name}"

    df = _rows_to_dataframe(rows, columns)

    # BQスキーマを明示（pandas型推論でSTRING→INTEGERに変わるのを防止）
    schema = [bigquery.SchemaField(col, "STRING") for col in columns]
    schema.append(bigquery.SchemaField("ingested_at", "TIMESTAMP"))

    job_config = bigquery.LoadJobConfig(
        write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE,
        schema=schema,
    )

    job = client.load_table_from_dataframe(df, table_id, job_config=job_config)
    job.result()  # 完了まで待機

    logger.info(
        "テーブル %s: %d行を書き込みました", table_name, len(df)
    )
    return len(df)


def read_members_from_bq() -> list[list]:
    """BQ membersテーブルを list[list] 形式で読み取る（TABLE_COLUMNS順）

    ingested_at は除外して返す（load_to_bigquery が再付与する）。
    """
    client = _build_bq_client()
    columns = config.TABLE_COLUMNS[config.BQ_TABLE_MEMBERS]
    col_list = ", ".join(f"`{c}`" for c in columns)
    query = f"SELECT {col_list} FROM `{config.GCP_PROJECT_ID}.{config.BQ_DATASET}.{config.BQ_TABLE_MEMBERS}`"
    df = client.query(query).to_dataframe()
    return df.where(df.notna(), None).values.tolist()


def read_group_based_users() -> dict[str, list[dict]]:
    """dashboard_usersからグループ由来ユーザーを取得

    Returns:
        {group_email: [{"email": ..., "role": ...}, ...]}
    """
    client = _build_bq_client()
    table_id = f"{config.GCP_PROJECT_ID}.{config.BQ_DATASET}.dashboard_users"
    query = f"""
    SELECT email, role, source_group
    FROM `{table_id}`
    WHERE source_group IS NOT NULL
    """
    df = client.query(query).to_dataframe()
    result: dict[str, list[dict]] = {}
    for _, row in df.iterrows():
        group = row["source_group"]
        if group not in result:
            result[group] = []
        result[group].append({"email": row["email"], "role": row["role"]})
    return result


def sync_dashboard_users_from_groups(
    group_members_map: dict[str, list[str]],
) -> dict[str, int]:
    """グループ由来のdashboard_usersを最新のグループメンバーと同期

    Args:
        group_members_map: {group_email: [member_email, ...]} Admin Directory APIから取得した最新データ

    Returns:
        {"added": N, "removed": N}
    """
    client = _build_bq_client()
    table_id = f"{config.GCP_PROJECT_ID}.{config.BQ_DATASET}.dashboard_users"

    current = read_group_based_users()
    all_groups = set(current.keys()) | set(group_members_map.keys())

    total_added = 0
    total_removed = 0

    for group_email in all_groups:
        current_users = {u["email"] for u in current.get(group_email, [])}
        latest_members = set(group_members_map.get(group_email, []))

        # このグループの既存ロールを取得（新規追加時に使用）
        existing_roles = current.get(group_email, [])
        default_role = existing_roles[0]["role"] if existing_roles else "viewer"

        # 追加: 最新メンバーにいるが現在登録されていないユーザー
        to_add = latest_members - current_users
        for member_email in to_add:
            # 手動登録済みユーザーはスキップ（source_group IS NULL のレコードが存在する場合）
            check_query = f"""
            SELECT COUNT(*) AS cnt FROM `{table_id}`
            WHERE email = @email AND source_group IS NULL
            """
            job_config = bigquery.QueryJobConfig(
                query_parameters=[
                    bigquery.ScalarQueryParameter("email", "STRING", member_email)
                ]
            )
            rows = list(client.query(check_query, job_config=job_config).result())
            if rows[0].cnt > 0:
                continue

            insert_query = f"""
            MERGE `{table_id}` T
            USING (SELECT @email AS email, @source_group AS source_group) S
            ON T.email = S.email AND T.source_group = S.source_group
            WHEN NOT MATCHED THEN
              INSERT (email, role, display_name, added_by, source_group, created_at, updated_at)
              VALUES (@email, @role, NULL, 'system-sync', @source_group, CURRENT_TIMESTAMP(), CURRENT_TIMESTAMP())
            """
            job_config = bigquery.QueryJobConfig(
                query_parameters=[
                    bigquery.ScalarQueryParameter("email", "STRING", member_email),
                    bigquery.ScalarQueryParameter("role", "STRING", default_role),
                    bigquery.ScalarQueryParameter("source_group", "STRING", group_email),
                ]
            )
            result = client.query(insert_query, job_config=job_config).result()
            if result.num_dml_affected_rows > 0:
                total_added += 1

        # 削除: 現在登録されているがグループから抜けたユーザー
        to_remove = current_users - latest_members
        for member_email in to_remove:
            delete_query = f"""
            DELETE FROM `{table_id}`
            WHERE email = @email AND source_group = @source_group
            """
            job_config = bigquery.QueryJobConfig(
                query_parameters=[
                    bigquery.ScalarQueryParameter("email", "STRING", member_email),
                    bigquery.ScalarQueryParameter("source_group", "STRING", group_email),
                ]
            )
            client.query(delete_query, job_config=job_config).result()
            total_removed += 1

    return {"added": total_added, "removed": total_removed}


def load_all(all_data: dict[str, list[list]]) -> dict[str, int]:
    """全テーブルにデータをロード

    Returns:
        {"gyomu_reports": 行数, "hojo_reports": 行数, "members": 行数}
    """
    results = {}
    for table_name, rows in all_data.items():
        try:
            count = load_to_bigquery(table_name, rows)
            results[table_name] = count
        except Exception as e:
            logger.error("テーブル %s への書き込みエラー: %s", table_name, e)
            results[table_name] = -1
    return results
