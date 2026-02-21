"""Cloud Run エントリポイント

Cloud Scheduler → HTTP POST → データ収集 → BigQuery投入
"""

import logging
import os
import time

from flask import Flask, jsonify

import sheets_collector
import bq_loader

app = Flask(__name__)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


@app.route("/", methods=["POST"])
def run_consolidation():
    """データ集約のメインエンドポイント（Cloud Schedulerから呼び出し）"""
    start = time.time()
    logger.info("--- 処理開始: 全スプレッドシートのデータ集約 ---")

    try:
        # Step 1-2: Sheets APIでデータ収集
        all_data = sheets_collector.run_collection()

        # Step 3: BigQueryに投入
        results = bq_loader.load_all(all_data)

        elapsed = round(time.time() - start, 1)
        summary = {
            "status": "success",
            "elapsed_seconds": elapsed,
            "tables": results,
        }
        logger.info("--- 処理完了 (%s秒) --- 結果: %s", elapsed, results)
        return jsonify(summary), 200

    except Exception as e:
        elapsed = round(time.time() - start, 1)
        logger.error("致命的エラー (%s秒): %s", elapsed, e, exc_info=True)
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/update-groups", methods=["POST"])
def update_groups():
    """メンバーグループ情報更新エンドポイント

    BQ の gws_account リストを使い Admin SDK でグループを取得して members テーブルを更新。
    シート再収集なし・約2分で完了。
    """
    start = time.time()
    logger.info("--- グループ情報更新開始 ---")
    try:
        updated_members, groups_master = sheets_collector.update_member_groups_from_bq()
        count = bq_loader.load_to_bigquery(bq_loader.config.BQ_TABLE_MEMBERS, updated_members)
        groups_count = bq_loader.load_to_bigquery(
            bq_loader.config.BQ_TABLE_GROUPS_MASTER, groups_master
        )
        elapsed = round(time.time() - start, 1)
        summary = {
            "status": "success",
            "elapsed_seconds": elapsed,
            "members_updated": count,
            "groups_master": groups_count,
        }
        logger.info("--- グループ情報更新完了 (%s秒) ---", elapsed)
        return jsonify(summary), 200
    except Exception as e:
        elapsed = round(time.time() - start, 1)
        logger.error("グループ情報更新エラー (%s秒): %s", elapsed, e, exc_info=True)
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/health", methods=["GET"])
def health():
    """ヘルスチェック"""
    return jsonify({"status": "ok"}), 200


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port, debug=True)
