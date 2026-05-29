-- BQバックアップ用データセット
--
-- 用途: BQが唯一のソースであるテーブル（Sheets/Admin Directoryから再生成できない）の
--       誤操作・誤DELETE/MERGEからの復旧用 snapshot を保持する。
--       cloud-run の毎朝バッチ Step8 (bq_loader.create_snapshots) が日次で snapshot を作成し、
--       各 snapshot は90日後に自動失効する。
--
-- 制約: pay_reports と同一リージョン(asia-northeast1)であること。
--       BigQuery の SNAPSHOT TABLE CLONE はクロスリージョン不可のため。
--
-- 権限: snapshot 作成に必要な権限は pay-collector@ SA が project-level の
--       roles/bigquery.dataEditor + roles/bigquery.jobUser で既に保持しているため、
--       dataset-level の追加権限付与は不要（同一プロジェクト内データセット）。

CREATE SCHEMA IF NOT EXISTS `monthly-pay-tax.pay_reports_backup`
OPTIONS (
  location = 'asia-northeast1',
  description = 'BQ唯一ソーステーブルの誤操作復旧用 snapshot 保管。Step8が日次作成、各snapshotは90日で自動失効。'
);
