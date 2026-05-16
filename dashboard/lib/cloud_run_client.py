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
