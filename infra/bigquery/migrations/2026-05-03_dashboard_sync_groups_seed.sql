-- 2026-05-03: dashboard_sync_groups の初期 seed
--
-- 既存 dashboard_users.source_group から enabled=TRUE で seed する冪等マイグレーション。
-- PR #132 デプロイ時に1回だけ実行し、以降は user_management UI からの操作で行が増減する。
--
-- 実行コマンド:
--   bq query --use_legacy_sql=false --project_id=monthly-pay-tax \
--     < infra/bigquery/migrations/2026-05-03_dashboard_sync_groups_seed.sql
--
-- 前提: schema.sql で dashboard_sync_groups テーブル作成済みであること

MERGE `monthly-pay-tax.pay_reports.dashboard_sync_groups` T
USING (
  SELECT DISTINCT source_group AS group_email
  FROM `monthly-pay-tax.pay_reports.dashboard_users`
  WHERE source_group IS NOT NULL
) S
ON T.group_email = S.group_email
WHEN NOT MATCHED THEN
  INSERT (group_email, enabled, last_synced_at, updated_at, updated_by)
  VALUES (S.group_email, TRUE, NULL, CURRENT_TIMESTAMP(), 'migration');
