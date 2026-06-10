"""pay-collector Cloud Run への OIDC 認証付き呼び出しヘルパ

dashboard / pay-collector は現状同一 SA (pay-collector@...) で動作するため、
SA 自身に roles/run.invoker を付与する self-invoke 構成。
TODO(Phase 2): pay-dashboard 専用 SA に分離し、collector への invoker のみ付与する。

呼び出し例:
    from lib.cloud_run_client import invoke_collector
    result = invoke_collector("/sync/main-reports")
"""
from __future__ import annotations

import logging
from typing import Optional

import google.auth.transport.requests
import google.oauth2.id_token
import requests

from lib.constants import COLLECTOR_URL

logger = logging.getLogger(__name__)

# endpoint → タイムアウト秒数（処理想定時間 + バッファ）
ENDPOINT_TIMEOUTS: dict[str, int] = {
    "/sync/main-reports": 600,
    "/sync/reimbursement": 180,
    "/sync/member-master": 120,
    "/update-groups": 240,
}

# 全体バッチ用（既存 check_management.py 経路と互換）
FULL_BATCH_TIMEOUT = 1800


def _base_url() -> str:
    return COLLECTOR_URL.rstrip("/")


def invoke_collector(endpoint: str) -> dict:
    """指定 endpoint を OIDC 認証付きで POST し、レスポンス JSON を返す

    Args:
        endpoint: "/sync/main-reports" 等。ENDPOINT_TIMEOUTS のキーである必要あり

    Returns:
        Cloud Run からのレスポンス JSON (dict)

    Raises:
        ValueError: 未知 endpoint
        requests.HTTPError: HTTP 4xx/5xx
        requests.Timeout: タイムアウト
    """
    if endpoint not in ENDPOINT_TIMEOUTS:
        raise ValueError(f"未知の endpoint: {endpoint}")

    url = f"{_base_url()}{endpoint}"
    timeout = ENDPOINT_TIMEOUTS[endpoint]

    auth_req = google.auth.transport.requests.Request()
    token = google.oauth2.id_token.fetch_id_token(auth_req, COLLECTOR_URL)

    logger.info("Cloud Run 呼び出し: %s (timeout=%ss)", endpoint, timeout)
    response = requests.post(
        url,
        headers={"Authorization": f"Bearer {token}"},
        timeout=timeout,
    )
    response.raise_for_status()
    return response.json()


# 隊×月評価 (PR-D)
# 単独隊: 1 隊 30s + Gemini 数 retry を見込んで 90s。全隊: scheduler 同等の 1800s 上限。
TEAM_EVAL_SINGLE_TIMEOUT = 90
TEAM_EVAL_BULK_TIMEOUT = 1800


def invoke_team_eval(
    *,
    year: Optional[int] = None,
    month: Optional[int] = None,
    teams: Optional[list[str]] = None,
    force: bool = False,
) -> dict:
    """POST /eval/team-monthly を OIDC 認証付きで呼ぶ (spec §5.4)。

    Args:
        year/month: None で前月解決 (server 側 JST)
        teams: None で全 active 隊、リストで単独 or 複数隊
        force: True で hash 一致でも再生成

    Returns:
        sync レスポンス: {year, month, job_id, summary: {total, generated, ...}, results: [...]}

    Raises:
        requests.HTTPError: 4xx/5xx
        requests.Timeout
    """
    url = f"{_base_url()}/eval/team-monthly"
    # 単独隊呼び出し (dashboard ボタン) は短めタイムアウト、全隊一括は long
    timeout = TEAM_EVAL_SINGLE_TIMEOUT if teams and len(teams) <= 3 else TEAM_EVAL_BULK_TIMEOUT

    auth_req = google.auth.transport.requests.Request()
    token = google.oauth2.id_token.fetch_id_token(auth_req, COLLECTOR_URL)

    body = {"year": year, "month": month, "teams": teams, "force": force}
    logger.info(
        "team-eval 呼び出し: year=%s month=%s teams=%s force=%s timeout=%ss",
        year, month, teams, force, timeout,
    )
    response = requests.post(
        url,
        headers={"Authorization": f"Bearer {token}"},
        json=body,
        timeout=timeout,
    )
    response.raise_for_status()
    return response.json()
