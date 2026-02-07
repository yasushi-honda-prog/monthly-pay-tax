"""BigQueryデータ投入モジュール

pandas DataFrame → BigQuery load_table_from_dataframe でバッチ投入。
"""

import logging
from datetime import datetime, timezone

import pandas as pd
from google.cloud import bigquery

import config

logger = logging.getLogger(__name__)

# カラム名定義（source_url + col_b~col_k）
COLUMNS = [
    "source_url",
    "col_b", "col_c", "col_d", "col_e", "col_f",
    "col_g", "col_h", "col_i", "col_j", "col_k",
]


def _build_bq_client() -> bigquery.Client:
    """BigQueryクライアントを構築"""
    return bigquery.Client(project=config.GCP_PROJECT_ID)


def _rows_to_dataframe(rows: list[list]) -> pd.DataFrame:
    """2次元配列をDataFrameに変換

    GASのデータは列数が不揃いの場合があるため、不足分をNoneで埋める。
    """
    normalized = []
    expected_cols = len(COLUMNS)  # 11列（URL + B~K）

    for row in rows:
        if len(row) < expected_cols:
            row = row + [None] * (expected_cols - len(row))
        elif len(row) > expected_cols:
            row = row[:expected_cols]
        # 全値を文字列に変換（BQスキーマがSTRING）
        normalized.append([str(v) if v is not None else None for v in row])

    df = pd.DataFrame(normalized, columns=COLUMNS)
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

    client = _build_bq_client()
    table_id = f"{config.GCP_PROJECT_ID}.{config.BQ_DATASET}.{table_name}"

    df = _rows_to_dataframe(rows)

    job_config = bigquery.LoadJobConfig(
        write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE,
    )

    job = client.load_table_from_dataframe(df, table_id, job_config=job_config)
    job.result()  # 完了まで待機

    logger.info(
        "テーブル %s: %d行を書き込みました", table_name, len(df)
    )
    return len(df)


def load_all(all_data: dict[str, list[list]]) -> dict[str, int]:
    """全テーブルにデータをロード

    Returns:
        {"gyomu_reports": 行数, "hojo_reports": 行数}
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
