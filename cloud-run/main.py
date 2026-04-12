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

        # Step 4: グループ情報更新（Admin SDK、失敗しても本体は成功扱い）
        try:
            logger.info("--- グループ情報更新開始 ---")
            updated_members, groups_master = sheets_collector.update_member_groups_from_bq()
            results[bq_loader.config.BQ_TABLE_MEMBERS] = bq_loader.load_to_bigquery(
                bq_loader.config.BQ_TABLE_MEMBERS, updated_members
            )
            results[bq_loader.config.BQ_TABLE_GROUPS_MASTER] = bq_loader.load_to_bigquery(
                bq_loader.config.BQ_TABLE_GROUPS_MASTER, groups_master
            )
            logger.info(
                "--- グループ情報更新完了 (members: %d, groups: %d) ---",
                results[bq_loader.config.BQ_TABLE_MEMBERS],
                results[bq_loader.config.BQ_TABLE_GROUPS_MASTER],
            )
        except Exception as grp_err:
            logger.warning("グループ情報更新スキップ（本体処理は完了）: %s", grp_err, exc_info=True)

        # Step 5: dashboard_usersグループベース自動同期（失敗しても本体は成功扱い）
        try:
            logger.info("--- dashboard_usersグループ同期開始 ---")
            group_users = bq_loader.read_group_based_users()
            if group_users:
                admin_service = sheets_collector._build_admin_service()
                group_members_map = {}
                for group_email in group_users:
                    members_list = sheets_collector.list_group_members(admin_service, group_email)
                    group_members_map[group_email] = members_list
                sync_result = bq_loader.sync_dashboard_users_from_groups(group_members_map)
                results["dashboard_users_sync"] = sync_result
                logger.info(
                    "--- dashboard_usersグループ同期完了 (追加: %d, 削除: %d) ---",
                    sync_result["added"],
                    sync_result["removed"],
                )
            else:
                logger.info("--- dashboard_usersグループ同期: 対象グループなし ---")
        except Exception as sync_err:
            logger.warning("dashboard_usersグループ同期スキップ: %s", sync_err, exc_info=True)

        # Step 6: 立替金シート収集（失敗しても本体は成功扱い）
        try:
            logger.info("--- 立替金シート収集開始 ---")
            reimbursement_data = sheets_collector.run_reimbursement_collection()
            reimbursement_results = bq_loader.load_all(reimbursement_data)
            results.update(reimbursement_results)
            logger.info(
                "--- 立替金シート収集完了 (reimbursement_items: %d) ---",
                reimbursement_results.get(bq_loader.config.BQ_TABLE_REIMBURSEMENT, 0),
            )
        except Exception as reimb_err:
            logger.warning(
                "立替金シート収集スキップ（本体処理は完了）: %s", reimb_err, exc_info=True
            )

        # Step 7: タダメンMマスタ全量取得（失敗しても本体は成功扱い）
        try:
            logger.info("--- タダメンMマスタ収集開始 ---")
            service = sheets_collector._build_sheets_service()
            member_master_data = sheets_collector.collect_member_master(service)
            member_master_count = bq_loader.load_to_bigquery(
                bq_loader.config.BQ_TABLE_MEMBER_MASTER, member_master_data
            )
            results[bq_loader.config.BQ_TABLE_MEMBER_MASTER] = member_master_count
            logger.info(
                "--- タダメンMマスタ収集完了 (member_master: %d) ---",
                member_master_count,
            )
        except Exception as mm_err:
            logger.warning(
                "タダメンMマスタ収集スキップ（本体処理は完了）: %s", mm_err, exc_info=True
            )

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

        # dashboard_usersグループ同期
        sync_result = {"added": 0, "removed": 0}
        try:
            group_users = bq_loader.read_group_based_users()
            if group_users:
                admin_service = sheets_collector._build_admin_service()
                group_members_map = {}
                for group_email in group_users:
                    members_list = sheets_collector.list_group_members(admin_service, group_email)
                    group_members_map[group_email] = members_list
                sync_result = bq_loader.sync_dashboard_users_from_groups(group_members_map)
                logger.info(
                    "dashboard_usersグループ同期完了 (追加: %d, 削除: %d)",
                    sync_result["added"],
                    sync_result["removed"],
                )
        except Exception as sync_err:
            logger.warning("dashboard_usersグループ同期スキップ: %s", sync_err, exc_info=True)

        elapsed = round(time.time() - start, 1)
        summary = {
            "status": "success",
            "elapsed_seconds": elapsed,
            "members_updated": count,
            "groups_master": groups_count,
            "dashboard_users_sync": sync_result,
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
