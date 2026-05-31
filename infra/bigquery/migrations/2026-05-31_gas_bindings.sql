-- 2026-05-31: gas_bindings テーブル作成
--
-- 業務報告スプレッドシート（約215件）のコンテナバインド Apps Script の Script ID を、
-- スプレッドシート・メンバーと紐付けて一元管理するメタデータテーブル。
-- GASコード本体は保存しない（必要時に script_id から clasp clone）。読み取り専用。
--
-- 収集は scripts/collect_gas_bindings.py（ローカル半手動巡回、Playwright）が
-- staging table 経由の MERGE（spreadsheet_id キー upsert）で投入する。
-- WRITE_TRUNCATE は使わない（中断時に正常データを欠損させるため）。
--
-- 実行コマンド（初回1回のみ。CREATE TABLE IF NOT EXISTS なので冪等）:
--   bq query --use_legacy_sql=false --project_id=monthly-pay-tax \
--     < infra/bigquery/migrations/2026-05-31_gas_bindings.sql

CREATE TABLE IF NOT EXISTS `monthly-pay-tax.pay_reports.gas_bindings` (
  spreadsheet_id STRING NOT NULL,  -- report_url から抽出したスプレッドシートID（MERGEキー）
  report_url     STRING NOT NULL,  -- 元の報告シートURL（members/member_master 結合キー）
  script_id      STRING,           -- コンテナバインドGASのScript ID（status=ok のみ非NULL）
  editor_url     STRING,           -- script.google.com エディタURL
  member_id      STRING,           -- タダメンID
  nickname       STRING,           -- ニックネーム
  url_source     STRING,           -- "url_1" | "url_2"（member_master のどちらの列由来か）
  status         STRING NOT NULL,  -- ok | no_gas | error | pending | unexpected_new_project
  error_type     STRING,           -- auth_required | permission_denied | ui_timeout | parse_error | unexpected_new_project
  error_detail   STRING,           -- 失敗時の詳細メッセージ
  fetched_at     TIMESTAMP,        -- Script ID を実際に取得した時刻
  ingested_at    TIMESTAMP NOT NULL -- BQ 書き込み時刻
);
