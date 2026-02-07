-- BigQuery スキーマ定義
-- データセット: pay_reports
-- GASの元データ: B~K列（10列）+ 先頭にURL付加 = 11列

-- データセット作成
-- bq mk --dataset --location=asia-northeast1 monthly-pay-tax:pay_reports

-- 【都度入力】業務報告
CREATE TABLE IF NOT EXISTS `monthly-pay-tax.pay_reports.gyomu_reports` (
  source_url STRING NOT NULL,       -- 元スプレッドシートURL
  col_b STRING,                     -- B列
  col_c STRING,                     -- C列
  col_d STRING,                     -- D列
  col_e STRING,                     -- E列
  col_f STRING,                     -- F列
  col_g STRING,                     -- G列
  col_h STRING,                     -- H列
  col_i STRING,                     -- I列
  col_j STRING,                     -- J列
  col_k STRING,                     -- K列
  ingested_at TIMESTAMP NOT NULL    -- データ取得日時
);

-- 【月１入力】補助＆立替報告＋月締め
CREATE TABLE IF NOT EXISTS `monthly-pay-tax.pay_reports.hojo_reports` (
  source_url STRING NOT NULL,       -- 元スプレッドシートURL
  col_b STRING,                     -- B列
  col_c STRING,                     -- C列
  col_d STRING,                     -- D列
  col_e STRING,                     -- E列
  col_f STRING,                     -- F列
  col_g STRING,                     -- G列
  col_h STRING,                     -- H列
  col_i STRING,                     -- I列
  col_j STRING,                     -- J列
  col_k STRING,                     -- K列
  ingested_at TIMESTAMP NOT NULL    -- データ取得日時
);
