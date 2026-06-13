"""隊×月 予実評価サービス（POST /eval/team-monthly のビジネスロジック層）

設計: docs/specs/2026-06-10-team-budget-eval-design.md §5

main.py は薄い HTTP ラッパーに留め、本ファイルがオーケストレーション
（claim → hash → 比較 → Gemini → upsert）を担う。テスト容易性のため
BQ / Gemini クライアントは外部から差し替え可能。
"""

import json
import logging
import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from google.auth.transport import requests as google_requests
from google.oauth2 import id_token

import bq_loader
import config
import pii_masker
import vertex_evaluator

logger = logging.getLogger(__name__)

_JST = timezone(timedelta(hours=9))


# -------- 入力解決 --------


def resolve_year_month(year: Optional[int], month: Optional[int]) -> tuple[int, int]:
    """year/month が null なら JST 前月を返す。両方指定されていればそのまま返す。"""
    if year is not None and month is not None:
        return int(year), int(month)
    now = datetime.now(_JST)
    first_of_this_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    last_of_prev = first_of_this_month - timedelta(days=1)
    return last_of_prev.year, last_of_prev.month


def extract_actor(request) -> str:
    """request から actor を確定する（spec §5.1: server 側で OIDC subject から確定）。

    優先順位:
      1. X-Goog-Authenticated-User-Email (IAP / Cloud Run authenticated invocation)
      2. Authorization: Bearer <JWT> → google.oauth2.id_token.verify_token で
         signature + issuer + (audience 設定時) audience 検証
      3. "unknown"

    PR-C 修正: 旧実装は JWT payload を decode するだけで署名検証なし。
    Cloud Run IAM 認証は普通 --no-allow-unauthenticated で deploy する前提だが、
    誤って --allow-unauthenticated でデプロイした場合に任意の bearer token で
    actor 詐称可能だった (audit log 偽装)。verify_token で防ぐ。
    audience は環境変数 SERVICE_AUDIENCE_URL（Cloud Run service URL）で指定。
    """
    email = request.headers.get("X-Goog-Authenticated-User-Email", "")
    if email:
        return email.split(":", 1)[-1]

    auth = request.headers.get("Authorization", "")
    if auth.lower().startswith("bearer "):
        token = auth[7:]
        audience = os.environ.get("SERVICE_AUDIENCE_URL") or None
        try:
            # google.auth.transport.requests.Request は requests.Session を内部に持ち
            # thread-safe ではないため、リクエスト毎に新規作成する (Agent #4 対策)。
            transport = google_requests.Request()
            payload = id_token.verify_token(token, transport, audience=audience)
            return payload.get("email") or payload.get("sub") or "unknown"
        except Exception as exc:  # noqa: BLE001 — 検証失敗は unknown 扱い
            # デバッグのため例外メッセージも残す (Agent #5 対策)
            logger.warning(
                "JWT verify failed (actor=unknown): %s: %s",
                type(exc).__name__, exc,
            )

    return "unknown"


def generate_job_id() -> str:
    """job_id を生成する。`evj-YYYYMMDDHHMMSS-<8桁hex>` 形式。"""
    now = datetime.now(_JST)
    return f"evj-{now.strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:8]}"


# -------- 隊一覧取得 --------


def list_active_teams(bq_client, year: int, month: int) -> list[str]:
    """対象月に実額がある（または予算がある）隊一覧を取得する。

    v_team_budget_actuals VIEW を使うと予算 only / 実額 only も含まれる。
    spec §3.1 「2026/05 以降」フィルタは VIEW 内で適用済み。
    """
    table_id = (
        f"{config.GCP_PROJECT_ID}.{config.BQ_DATASET}."
        f"{config.BQ_VIEW_TEAM_BUDGET_ACTUALS}"
    )
    sql = f"""
    SELECT DISTINCT team
    FROM `{table_id}`
    WHERE year = @year AND month = @month
      AND team IS NOT NULL AND team != ''
    ORDER BY team
    """
    from google.cloud import bigquery

    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter("year", "INT64", year),
            bigquery.ScalarQueryParameter("month", "INT64", month),
        ]
    )
    rows = bq_client.query(sql, job_config=job_config).result()
    return [row["team"] for row in rows if row["team"]]


def load_team_aggregate(bq_client, year: int, month: int, team: str) -> dict:
    """1 隊の集計値（budget / actual / rate / diff）を VIEW から取得する。"""
    table_id = (
        f"{config.GCP_PROJECT_ID}.{config.BQ_DATASET}."
        f"{config.BQ_VIEW_TEAM_BUDGET_ACTUALS}"
    )
    sql = f"""
    SELECT budget_amount, actual_amount, achievement_rate, diff_amount,
           has_budget, has_actual
    FROM `{table_id}`
    WHERE year = @year AND month = @month AND team = @team
    LIMIT 1
    """
    from google.cloud import bigquery

    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter("year", "INT64", year),
            bigquery.ScalarQueryParameter("month", "INT64", month),
            bigquery.ScalarQueryParameter("team", "STRING", team),
        ]
    )
    rows = list(bq_client.query(sql, job_config=job_config).result())
    if not rows:
        return {
            "budget_amount": None, "actual_amount": None,
            "achievement_rate": None, "diff_amount": None,
            "has_budget": False, "has_actual": False,
        }
    row = rows[0]
    # NUMERIC → float 化（json 化を考慮）
    def _num(v):
        return float(v) if v is not None else None

    return {
        "budget_amount": _num(row["budget_amount"]),
        "actual_amount": _num(row["actual_amount"]),
        "achievement_rate": _num(row["achievement_rate"]),
        "diff_amount": _num(row["diff_amount"]),
        "has_budget": bool(row["has_budget"]),
        "has_actual": bool(row["has_actual"]),
    }


# -------- 1 隊の処理 --------


def process_one_team(
    *,
    bq_client,
    genai_client,
    year: int,
    month: int,
    team: str,
    force: bool,
    job_id: str,
    actor: str,
    member_names: set,
) -> dict:
    """1 隊の評価を処理する。

    Returns:
        {"team": team, "status": "generated|skipped_claim|skipped_hash_match|no_actual|failed", ...}
    """
    result: dict = {"team": team}

    # 1. claim
    claimed = bq_loader.claim_team_eval_row(
        bq_client, year=year, month=month, team=team, job_id=job_id, actor=actor,
    )
    if not claimed:
        result["status"] = "skipped_claim"
        return result

    try:
        # 2. hash 計算
        data_hash = vertex_evaluator.compute_actual_data_hash(
            bq_client, year, month, team,
        )
        # 3. 集計値取得
        agg = load_team_aggregate(bq_client, year, month, team)

        if not agg["has_actual"]:
            bq_loader.release_team_eval_claim(
                bq_client, year=year, month=month, team=team,
                expected_lock_token=job_id,
            )
            result.update({"status": "no_actual", "actual_amount": None,
                          "budget_amount": agg["budget_amount"]})
            return result

        # 4. 既存比較
        existing = bq_loader.load_existing_eval(
            bq_client, year=year, month=month, team=team,
        )
        if not force and existing and existing.get("actual_data_hash") == data_hash:
            bq_loader.release_team_eval_claim(
                bq_client, year=year, month=month, team=team,
                expected_lock_token=job_id,
            )
            result.update({
                "status": "skipped_hash_match",
                "actual_amount": agg["actual_amount"],
                "budget_amount": agg["budget_amount"],
                "achievement_rate": agg["achievement_rate"],
            })
            return result

        # 5. Gemini 呼び出し (R5 設計: PII 対策は入口 mask_pii に一本化)
        top_categories, samples_raw = vertex_evaluator.load_team_samples(
            bq_client, year, month, team,
        )
        samples_text, mask_results = vertex_evaluator.build_samples_text(
            samples_raw, member_names,
        )
        # R5 fail-safe: mask 通過済 samples_text に raw PII が残っていないか assert
        # (実装バグ検知)。prompt 全体は team 名 / top_categories の raw 埋め込みで
        # 偶然一致が起き false positive するので scan しない (設計判断)
        pii_masker.assert_no_raw_pii(samples_text, mask_results)
        user_prompt = vertex_evaluator.build_user_prompt(
            year=year, month=month, team=team,
            budget=agg["budget_amount"], actual=agg["actual_amount"],
            achievement_rate=agg["achievement_rate"], diff=agg["diff_amount"],
            top_categories=top_categories, samples_text=samples_text,
        )
        comment, usage = vertex_evaluator.generate_comment(genai_client, user_prompt)

        # 6. upsert + claim release
        gen_cfg_json = json.dumps({
            "max_tokens": config.GEMINI_MAX_TOKENS,
            "temperature": config.GEMINI_TEMPERATURE,
            "top_p": config.GEMINI_TOP_P,
        })
        record = {
            "year": year, "month": month, "team": team,
            "actual_amount": agg["actual_amount"],
            "budget_amount": agg["budget_amount"],
            "achievement_rate": agg["achievement_rate"],
            "diff_amount": agg["diff_amount"],
            "actual_data_hash": data_hash,
            "ai_comment": comment,
            "ai_model": config.GEMINI_MODEL,
            "ai_prompt_tokens": usage.get("prompt_tokens", 0),
            "ai_output_tokens": usage.get("output_tokens", 0),
            "prompt_version": config.PROMPT_VERSION,
            "sample_query_version": config.SAMPLE_QUERY_VERSION,
            "location": config.GEMINI_REGION,
            "generation_config_json": gen_cfg_json,
            "generated_by": actor,
        }
        upserted = bq_loader.upsert_team_monthly_eval(
            bq_client, record=record, expected_lock_token=job_id,
        )
        if not upserted:
            # claim を他者に奪われた稀ケース
            result.update({"status": "failed", "error": "claim_lost_during_processing"})
            return result

        result.update({
            "status": "generated",
            "actual_amount": agg["actual_amount"],
            "budget_amount": agg["budget_amount"],
            "achievement_rate": agg["achievement_rate"],
            "ai_comment": comment,
            "regen_attempts": usage.get("attempts", 1),
        })
        return result

    except Exception as exc:  # noqa: BLE001 — チームごとの失敗は集約に載せて継続
        logger.error("team eval failed: %s (%s)", team, type(exc).__name__, exc_info=True)
        # claim を release（後続呼び出しが進めるように）
        try:
            bq_loader.release_team_eval_claim(
                bq_client, year=year, month=month, team=team,
                expected_lock_token=job_id,
            )
        except Exception:  # noqa: BLE001
            pass
        result.update({"status": "failed", "error": type(exc).__name__})
        return result


# -------- まとめて処理 --------


def process_teams(
    *,
    year: int,
    month: int,
    teams: Optional[list[str]],
    force: bool,
    actor: str,
    job_id: str,
    bq_client=None,
    genai_client=None,
) -> dict:
    """teams のリストを順に処理して summary を返す。

    teams=None なら active な隊一覧を VIEW から取得する。
    bq_client / genai_client が None なら本物を構築する（テスト時は注入）。
    """
    from google.cloud import bigquery as _bq  # 関数内 import で循環回避

    bq_client = bq_client or _bq.Client(project=config.GCP_PROJECT_ID)
    genai_client = genai_client or vertex_evaluator.build_genai_client()
    member_names = pii_masker.load_member_names(bq_client)
    # silent PII bypass 防止: load_member_names が空 set を返すと mask_pii が no-op に
    # なり raw 名前を含む description が Gemini に送られる。空のときは abort し、Cloud
    # Run は HTTP 500 を返す。main.py の既存 chat_notifier がエンドポイント例外を catch
    # して通知する (本層では追加通知しない)。
    if not member_names:
        raise RuntimeError(
            "member_names is empty: load_member_names が空 set を返した "
            "(BQ 取得失敗 / member_master が空 等)。"
            "raw 名前マスキングが no-op になり Gemini に PII が漏れるため評価を abort。"
            "BQ 状態を確認の上で再実行してください。"
        )

    if teams is None:
        teams = list_active_teams(bq_client, year, month)

    results: list[dict] = []
    for team in teams:
        r = process_one_team(
            bq_client=bq_client, genai_client=genai_client,
            year=year, month=month, team=team,
            force=force, job_id=job_id, actor=actor,
            member_names=member_names,
        )
        results.append(r)

    counts = {"total": len(results), "generated": 0, "skipped_hash_match": 0,
              "skipped_claim": 0, "failed": 0, "no_actual": 0}
    for r in results:
        key = {
            "generated": "generated",
            "skipped_hash_match": "skipped_hash_match",
            "skipped_claim": "skipped_claim",
            "failed": "failed",
            "no_actual": "no_actual",
        }.get(r.get("status"), "failed")
        counts[key] += 1

    return {
        "year": year, "month": month, "job_id": job_id, "actor": actor,
        "summary": counts, "results": results,
    }
