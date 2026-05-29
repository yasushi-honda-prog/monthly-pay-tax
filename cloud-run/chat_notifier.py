"""Google Chat への障害通知モジュール

毎朝バッチや手動同期で障害が発生した際、Google Chat スペースへ
Incoming Webhook 経由でテクニカルな障害内容を投稿する。

- 投稿先 webhook URL は環境変数 CHAT_WEBHOOK_URL（Secret Manager 由来）で注入する。
- URL が未設定の場合は no-op（投稿せず即 return）。これにより URL 取得前でも
  バッチは正常動作し、URL 設定後に通知が有効化される。
- 通知の送信自体が失敗してもバッチ本体を落とさない（POST 例外はログのみで握る）。
- 通知内容はテクニカル情報（Step名 / 例外型 / メッセージ / 時刻 / リビジョン）に限定。
"""

import json
import logging
import os
import urllib.request
from datetime import datetime, timedelta, timezone

logger = logging.getLogger(__name__)

# Google Chat webhook URL（Secret Manager → Cloud Run env で注入。未設定なら no-op）
CHAT_WEBHOOK_URL_ENV = "CHAT_WEBHOOK_URL"
# Cloud Run が自動で設定するリビジョン名（ローカルでは未設定 → "unknown"）
REVISION_ENV = "K_REVISION"

_JST = timezone(timedelta(hours=9))
_POST_TIMEOUT_SEC = 10


def _now_jst_str() -> str:
    """現在時刻を JST の 'YYYY-MM-DD HH:MM JST' 形式で返す。"""
    return datetime.now(_JST).strftime("%Y-%m-%d %H:%M JST")


def notify(text: str) -> bool:
    """Google Chat へ text メッセージを投稿する。

    CHAT_WEBHOOK_URL が未設定なら no-op（False を返す）。
    投稿失敗時も例外を送出せず False を返す（呼び出し元のバッチを落とさない）。

    Returns:
        投稿に成功した場合 True、no-op または失敗した場合 False。
    """
    webhook_url = os.environ.get(CHAT_WEBHOOK_URL_ENV, "").strip()
    if not webhook_url:
        logger.info("CHAT_WEBHOOK_URL 未設定のため Chat 通知をスキップ（no-op）")
        return False

    # 通知は付随処理。payload 構築〜送信のいかなる失敗もバッチ本体に波及させない
    # ため、本体全体を広く捕捉する（urlopen の URLError/OSError に限らない）。
    try:
        payload = json.dumps({"text": text}).encode("utf-8")
        req = urllib.request.Request(
            webhook_url,
            data=payload,
            headers={"Content-Type": "application/json; charset=UTF-8"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=_POST_TIMEOUT_SEC) as resp:
            logger.info("Chat 通知を送信しました (status=%s)", resp.status)
            return True
    except Exception as send_err:  # noqa: BLE001 — 通知失敗を本体に波及させない
        logger.error("Chat 通知の送信に失敗（本体処理は継続）: %s", send_err, exc_info=True)
        return False


def _revision() -> str:
    return os.environ.get(REVISION_ENV, "unknown")


def format_failures(context: str, failures: list[tuple[str, str]]) -> str:
    """部分失敗のリストを Chat 投稿用 text に整形する。

    Args:
        context: 発生元（例 "毎朝バッチ POST /"）。
        failures: (Step表示名, 詳細メッセージ) のリスト。

    Returns:
        投稿用の複数行 text。
    """
    header = (
        f"🔴 pay-collector 障害 ({len(failures)}件)\n"
        f"発生: {_now_jst_str()} / rev: {_revision()} / {context}"
    )
    lines = [f"• [{step}] {detail}" for step, detail in failures]
    return header + "\n" + "\n".join(lines)


def format_fatal(context: str, exc: BaseException) -> str:
    """致命的エラー（処理全体の停止）を Chat 投稿用 text に整形する。

    Args:
        context: 発生元エンドポイント（例 "POST /"）。
        exc: 捕捉した例外。

    Returns:
        投稿用の text。
    """
    return (
        f"🔴 pay-collector 致命的エラー\n"
        f"発生: {_now_jst_str()} / rev: {_revision()} / {context}\n"
        f"• {type(exc).__name__}: {exc}"
    )


def notify_failures(context: str, failures: list[tuple[str, str]]) -> bool:
    """部分失敗が1件以上あれば集約して通知する。空なら no-op。"""
    if not failures:
        return False
    return notify(format_failures(context, failures))


def notify_fatal(context: str, exc: BaseException) -> bool:
    """致命的エラーを即時通知する。"""
    return notify(format_fatal(context, exc))
