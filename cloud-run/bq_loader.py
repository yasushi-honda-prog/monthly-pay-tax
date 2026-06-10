"""BigQueryデータ投入モジュール

pandas DataFrame → BigQuery load_table_from_dataframe でバッチ投入。
"""

import logging
from datetime import datetime, timezone
from typing import Optional

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


def create_snapshots(snapshot_date: str) -> dict[str, int]:
    """BQが唯一のソースであるテーブルの snapshot を backup データセットへ作成する。

    対象は config.BQ_SNAPSHOT_TABLES（Sheets/Admin Directory から再生成できない
    =誤操作・誤DELETE/MERGEで失われると復旧不可能なテーブル）。
    各テーブルを別データセット config.BQ_BACKUP_DATASET へ CLONE し、
    config.BQ_SNAPSHOT_EXPIRATION_DAYS 日後に自動失効する snapshot を作る。

    同日に複数回呼ばれても最初の1断面を保持する（IF NOT EXISTS）。
    1テーブルの作成が失敗しても残りのテーブルは継続する（部分失敗許容、付随処理のため）。

    Args:
        snapshot_date: snapshot名のサフィックス（例 "20260529"）。
            冪等性の担保とテスト時の固定値注入のため引数化している。

    Returns:
        {テーブル名: 1（成功）または -1（失敗）} の dict。
    """
    client = _build_bq_client()
    project = config.GCP_PROJECT_ID
    expiration_days = config.BQ_SNAPSHOT_EXPIRATION_DAYS
    results: dict[str, int] = {}

    for table_name in config.BQ_SNAPSHOT_TABLES:
        source_id = f"{project}.{config.BQ_DATASET}.{table_name}"
        snapshot_id = (
            f"{project}.{config.BQ_BACKUP_DATASET}.{table_name}_{snapshot_date}"
        )
        query = (
            f"CREATE SNAPSHOT TABLE IF NOT EXISTS `{snapshot_id}` "
            f"CLONE `{source_id}` "
            f"OPTIONS (expiration_timestamp = "
            f"TIMESTAMP_ADD(CURRENT_TIMESTAMP(), INTERVAL {expiration_days} DAY))"
        )
        try:
            client.query(query).result()  # 完了まで待機
            logger.info("snapshot作成: %s", snapshot_id)
            results[table_name] = 1
        except Exception as snap_err:
            logger.error(
                "snapshot作成失敗 %s（他テーブルは継続）: %s",
                table_name, snap_err, exc_info=True,
            )
            results[table_name] = -1

    return results


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


def read_enabled_sync_groups() -> set[str]:
    """dashboard_sync_groups から enabled=TRUE のグループメール集合を取得

    fail-fast: テーブル不在・権限不足・BQ 障害時は例外を伝播させる。
    （静かに空 set を返すと「OFF にされたつもりが全グループ凍結」を見分けられない）

    Returns:
        {group_email, ...} enabled=TRUE のグループメール集合
    """
    client = _build_bq_client()
    table_id = f"{config.GCP_PROJECT_ID}.{config.BQ_DATASET}.{config.BQ_TABLE_SYNC_GROUPS}"
    query = f"SELECT group_email FROM `{table_id}` WHERE enabled = TRUE"
    try:
        df = client.query(query).to_dataframe()
    except Exception as exc:
        logger.error(
            "dashboard_sync_groups テーブル読み取り失敗 (fail-fast): %s", exc, exc_info=True
        )
        raise
    return set(df["group_email"].tolist())


def read_all_sync_groups() -> set[str]:
    """dashboard_sync_groups の全グループメール集合を取得 (enabled の TRUE/FALSE 問わず)

    enabled=FALSE で意図的に凍結されたグループと、未登録のグループを区別するために使用。
    fail-fast: 失敗時は例外を伝播させる（read_enabled_sync_groups と同方針）。
    """
    client = _build_bq_client()
    table_id = f"{config.GCP_PROJECT_ID}.{config.BQ_DATASET}.{config.BQ_TABLE_SYNC_GROUPS}"
    query = f"SELECT group_email FROM `{table_id}`"
    try:
        df = client.query(query).to_dataframe()
    except Exception as exc:
        logger.error(
            "dashboard_sync_groups テーブル読み取り失敗 (fail-fast): %s", exc, exc_info=True
        )
        raise
    return set(df["group_email"].tolist())


def _update_last_synced_at(group_email: str) -> None:
    """同期処理が走った enabled グループの last_synced_at を現在時刻で更新

    last_synced_at は UI 表示用の補助情報であり、書込失敗で sync 全体を止める
    必要はない。warning ログのみ出して続行する（read 部の fail-fast とは意図的に非対称）。
    """
    client = _build_bq_client()
    table_id = f"{config.GCP_PROJECT_ID}.{config.BQ_DATASET}.{config.BQ_TABLE_SYNC_GROUPS}"
    query = f"""
    UPDATE `{table_id}`
    SET last_synced_at = CURRENT_TIMESTAMP()
    WHERE group_email = @group_email
    """
    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter("group_email", "STRING", group_email)
        ]
    )
    try:
        client.query(query, job_config=job_config).result()
    except Exception as exc:
        logger.warning(
            "last_synced_at 更新失敗 (group=%s, 同期処理は継続): %s",
            group_email, exc, exc_info=True,
        )


def sync_dashboard_users_from_groups(
    group_members_map: dict[str, list[str]],
) -> dict[str, int]:
    """グループ由来のdashboard_usersを最新のグループメンバーと同期

    enabled=TRUE のグループのみ処理対象。enabled=FALSE/未登録のグループは
    既存 dashboard_users レコードを残したまま add/remove を一切行わない（凍結）。

    Args:
        group_members_map: {group_email: [member_email, ...]} Admin Directory APIから取得した最新データ

    Returns:
        {"added": N, "removed": N, "skipped_disabled": N, "skipped_unregistered": N}
        - skipped_disabled: dashboard_sync_groups に enabled=FALSE で登録されているグループ数
        - skipped_unregistered: dashboard_sync_groups に未登録のグループ数（新規グループ等）
    """
    client = _build_bq_client()
    table_id = f"{config.GCP_PROJECT_ID}.{config.BQ_DATASET}.dashboard_users"

    enabled_groups = read_enabled_sync_groups()
    registered_groups = read_all_sync_groups()  # enabled の TRUE/FALSE 問わず登録済みグループ
    current = read_group_based_users()
    candidate_groups = set(current.keys()) | set(group_members_map.keys())
    all_groups = candidate_groups & enabled_groups
    skipped_disabled = len(candidate_groups & registered_groups - enabled_groups)
    skipped_unregistered = len(candidate_groups - registered_groups)
    if skipped_disabled or skipped_unregistered:
        logger.info(
            "同期スキップグループ: disabled=%d, unregistered=%d",
            skipped_disabled, skipped_unregistered,
        )

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

        _update_last_synced_at(group_email)

    return {
        "added": total_added,
        "removed": total_removed,
        "skipped_disabled": skipped_disabled,
        "skipped_unregistered": skipped_unregistered,
    }


def claim_team_eval_row(
    client,
    *,
    year: int,
    month: int,
    team: str,
    job_id: str,
    actor: str,
    lock_duration_min: Optional[int] = None,
) -> bool:
    """team_monthly_eval テーブルに claim を取得する（spec §4.3.1）。

    既存 claim が無いか expired していれば claim 成功、進行中なら失敗。

    Returns:
        True: claim 取得成功（自分の job_id がセットされた）。
        False: 他者が claim 中（lock_until が未来）。
    """
    lock_min = lock_duration_min or config.EVAL_LOCK_DURATION_MIN
    table_id = f"{config.GCP_PROJECT_ID}.{config.BQ_DATASET}.{config.BQ_TABLE_TEAM_MONTHLY_EVAL}"
    sql = f"""
    MERGE `{table_id}` t
    USING (
      SELECT @year AS year, @month AS month, @team AS team,
             @job_id AS lock_token, @actor AS lock_actor,
             TIMESTAMP_ADD(CURRENT_TIMESTAMP(), INTERVAL {lock_min} MINUTE) AS lock_until
    ) s
    ON t.year = s.year AND t.month = s.month AND t.team = s.team
    WHEN MATCHED AND (t.lock_token IS NULL OR t.lock_until < CURRENT_TIMESTAMP()) THEN
      UPDATE SET lock_token = s.lock_token,
                 lock_until = s.lock_until,
                 lock_actor = s.lock_actor
    WHEN NOT MATCHED THEN
      INSERT (year, month, team, lock_token, lock_until, lock_actor)
      VALUES (s.year, s.month, s.team, s.lock_token, s.lock_until, s.lock_actor)
    """
    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter("year", "INT64", year),
            bigquery.ScalarQueryParameter("month", "INT64", month),
            bigquery.ScalarQueryParameter("team", "STRING", team),
            bigquery.ScalarQueryParameter("job_id", "STRING", job_id),
            bigquery.ScalarQueryParameter("actor", "STRING", actor),
        ]
    )
    job = client.query(sql, job_config=job_config)
    job.result()
    # MERGE で affected_rows=1 なら成功（INSERT or UPDATE）、0 なら他者 claim 中
    num_affected = job.num_dml_affected_rows or 0
    success = num_affected >= 1
    if not success:
        logger.info("claim 失敗 (他者 claim 中): year=%s month=%s team=%s", year, month, team)
        return False

    # BigQuery には UNIQUE 制約がないため、同時 2 ジョブの WHEN NOT MATCHED
    # 経路で重複行が INSERT されうる。claim 成功直後に dedup して 1 行に絞る。
    # 自分の lock_token 以外の行（他者 claim 残骸 / 古い NULL row）を削除する。
    _dedup_after_claim(client, year=year, month=month, team=team, job_id=job_id)
    return True


def _dedup_after_claim(client, *, year: int, month: int, team: str, job_id: str) -> int:
    """claim 成功後に同 (year, month, team) の重複行を 1 行に絞る。

    残すべき行は厳密に「自分の lock_token + 最新 lock_until を持つ 1 行」のみ。
    BigQuery の DML には ROW_NUMBER 直接フィルタが書きにくいので、
    SELECT で残すべき行の row_hash を 1 件取得 → その row_hash 以外を DELETE する
    2 段階方式で同 lock_until の owned 重複も確実に 1 行に絞る。

    また他者のアクティブな claim (lock_until > NOW()) は誤削除しないよう保護する
    (PR-C Codex High-1)。

    Returns:
        削除した行数（通常 0。レース発生時のみ >0）。
    """
    table_id = f"{config.GCP_PROJECT_ID}.{config.BQ_DATASET}.{config.BQ_TABLE_TEAM_MONTHLY_EVAL}"
    # 1. 残すべき 1 行を特定: 自分の token のうち最新 lock_until + 一意 hash で 1 件確定。
    pick_sql = f"""
    SELECT TO_HEX(SHA256(TO_JSON_STRING(t))) AS row_hash
    FROM `{table_id}` AS t
    WHERE year = @year AND month = @month AND team = @team
      AND lock_token = @job_id
    ORDER BY lock_until DESC, row_hash
    LIMIT 1
    """
    job_config_pick = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter("year", "INT64", year),
            bigquery.ScalarQueryParameter("month", "INT64", month),
            bigquery.ScalarQueryParameter("team", "STRING", team),
            bigquery.ScalarQueryParameter("job_id", "STRING", job_id),
        ]
    )
    rows = list(client.query(pick_sql, job_config=job_config_pick).result())
    if not rows:
        # 自分の claim が即座に他者に奪われた稀ケース。
        return 0
    keep_row_hash = rows[0]["row_hash"]

    # 2. 残すべき 1 行 (row_hash 完全一致) 以外を DELETE。
    #    削除対象は厳密に「自分の token の重複行」 OR 「期限切れ orphan」のみ。
    #    他者のアクティブな claim (lock_until > NOW()) は絶対に保護する
    #    (PR-C Codex High-1 / Agent #3 対策)。
    delete_sql = f"""
    DELETE FROM `{table_id}` AS t
    WHERE year = @year AND month = @month AND team = @team
      AND TO_HEX(SHA256(TO_JSON_STRING(t))) != @keep_row_hash
      AND (
        t.lock_token = @job_id
        OR t.lock_token IS NULL
        OR t.lock_until IS NULL
        OR t.lock_until <= CURRENT_TIMESTAMP()
      )
    """
    job_config_del = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter("year", "INT64", year),
            bigquery.ScalarQueryParameter("month", "INT64", month),
            bigquery.ScalarQueryParameter("team", "STRING", team),
            bigquery.ScalarQueryParameter("job_id", "STRING", job_id),
            bigquery.ScalarQueryParameter("keep_row_hash", "STRING", keep_row_hash),
        ]
    )
    job = client.query(delete_sql, job_config=job_config_del)
    job.result()
    deleted = job.num_dml_affected_rows or 0
    if deleted > 0:
        logger.warning(
            "claim 重複 dedup: year=%s month=%s team=%s deleted=%s",
            year, month, team, deleted,
        )
    return deleted


def load_existing_eval(client, *, year: int, month: int, team: str) -> Optional[dict]:
    """既存の team_monthly_eval レコードを 1 件取得する（差分検知 hash 比較用）。

    Returns:
        該当行が無ければ None。
    """
    table_id = f"{config.GCP_PROJECT_ID}.{config.BQ_DATASET}.{config.BQ_TABLE_TEAM_MONTHLY_EVAL}"
    sql = f"""
    SELECT actual_data_hash, ai_comment, ai_model, prompt_version,
           generated_at, generated_by
    FROM `{table_id}`
    WHERE year = @year AND month = @month AND team = @team
    LIMIT 1
    """
    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter("year", "INT64", year),
            bigquery.ScalarQueryParameter("month", "INT64", month),
            bigquery.ScalarQueryParameter("team", "STRING", team),
        ]
    )
    rows = list(client.query(sql, job_config=job_config).result())
    if not rows:
        return None
    row = rows[0]
    return {
        "actual_data_hash": row["actual_data_hash"],
        "ai_comment": row["ai_comment"],
        "ai_model": row["ai_model"],
        "prompt_version": row["prompt_version"],
        "generated_at": row["generated_at"],
        "generated_by": row["generated_by"],
    }


def upsert_team_monthly_eval(client, *, record: dict, expected_lock_token: str) -> bool:
    """評価結果を MERGE で書き込み、claim を release する（spec §5.2 step 6）。

    expected_lock_token と一致する claim のみ更新（他者 claim 中なら no-op）。

    Args:
        record: 必須キー: year, month, team, actual_amount, budget_amount,
                achievement_rate, diff_amount, actual_data_hash, ai_comment,
                ai_model, ai_prompt_tokens, ai_output_tokens, prompt_version,
                sample_query_version, location, generation_config_json,
                generated_by.
        expected_lock_token: 自分が取った claim の job_id。これと一致しないと
                             UPDATE が走らない（他者に奪われた / 期限切れ後の事後書き込み防御）。

    Returns:
        True: 書き込み成功。False: claim 不一致で no-op。
    """
    table_id = f"{config.GCP_PROJECT_ID}.{config.BQ_DATASET}.{config.BQ_TABLE_TEAM_MONTHLY_EVAL}"
    sql = f"""
    MERGE `{table_id}` t
    USING (
      SELECT @year AS year, @month AS month, @team AS team
    ) s
    ON t.year = s.year AND t.month = s.month AND t.team = s.team
       AND t.lock_token = @expected_lock_token
       AND t.lock_until > CURRENT_TIMESTAMP()
    WHEN MATCHED THEN
      UPDATE SET
        actual_amount = @actual_amount,
        budget_amount = @budget_amount,
        achievement_rate = @achievement_rate,
        diff_amount = @diff_amount,
        actual_data_hash = @actual_data_hash,
        ai_comment = @ai_comment,
        ai_model = @ai_model,
        ai_prompt_tokens = @ai_prompt_tokens,
        ai_output_tokens = @ai_output_tokens,
        prompt_version = @prompt_version,
        sample_query_version = @sample_query_version,
        location = @location,
        generation_config_json = @generation_config_json,
        generated_at = CURRENT_TIMESTAMP(),
        generated_by = @generated_by,
        lock_token = NULL,
        lock_until = NULL,
        lock_actor = NULL
    """
    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter("year", "INT64", record["year"]),
            bigquery.ScalarQueryParameter("month", "INT64", record["month"]),
            bigquery.ScalarQueryParameter("team", "STRING", record["team"]),
            bigquery.ScalarQueryParameter("expected_lock_token", "STRING", expected_lock_token),
            bigquery.ScalarQueryParameter("actual_amount", "NUMERIC", record.get("actual_amount")),
            bigquery.ScalarQueryParameter("budget_amount", "NUMERIC", record.get("budget_amount")),
            bigquery.ScalarQueryParameter("achievement_rate", "FLOAT64", record.get("achievement_rate")),
            bigquery.ScalarQueryParameter("diff_amount", "NUMERIC", record.get("diff_amount")),
            bigquery.ScalarQueryParameter("actual_data_hash", "STRING", record.get("actual_data_hash")),
            bigquery.ScalarQueryParameter("ai_comment", "STRING", record.get("ai_comment")),
            bigquery.ScalarQueryParameter("ai_model", "STRING", record.get("ai_model")),
            bigquery.ScalarQueryParameter("ai_prompt_tokens", "INT64", record.get("ai_prompt_tokens") or 0),
            bigquery.ScalarQueryParameter("ai_output_tokens", "INT64", record.get("ai_output_tokens") or 0),
            bigquery.ScalarQueryParameter("prompt_version", "STRING", record["prompt_version"]),
            bigquery.ScalarQueryParameter("sample_query_version", "STRING", record["sample_query_version"]),
            bigquery.ScalarQueryParameter("location", "STRING", record["location"]),
            bigquery.ScalarQueryParameter("generation_config_json", "STRING", record.get("generation_config_json")),
            bigquery.ScalarQueryParameter("generated_by", "STRING", record["generated_by"]),
        ]
    )
    job = client.query(sql, job_config=job_config)
    job.result()
    affected = job.num_dml_affected_rows or 0
    if affected == 0:
        logger.warning(
            "upsert no-op (claim 不一致): year=%s month=%s team=%s",
            record["year"], record["month"], record["team"],
        )
        return False
    return True


def release_team_eval_claim(
    client, *, year: int, month: int, team: str, expected_lock_token: str
) -> bool:
    """途中エラー時に claim だけ release する（評価結果は更新しない）。

    Returns:
        True: release 成功。False: claim が他者に奪われた / 既に release 済み。
    """
    table_id = f"{config.GCP_PROJECT_ID}.{config.BQ_DATASET}.{config.BQ_TABLE_TEAM_MONTHLY_EVAL}"
    sql = f"""
    UPDATE `{table_id}`
    SET lock_token = NULL, lock_until = NULL, lock_actor = NULL
    WHERE year = @year AND month = @month AND team = @team
      AND lock_token = @expected_lock_token
    """
    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter("year", "INT64", year),
            bigquery.ScalarQueryParameter("month", "INT64", month),
            bigquery.ScalarQueryParameter("team", "STRING", team),
            bigquery.ScalarQueryParameter("expected_lock_token", "STRING", expected_lock_token),
        ]
    )
    job = client.query(sql, job_config=job_config)
    job.result()
    return (job.num_dml_affected_rows or 0) > 0


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
