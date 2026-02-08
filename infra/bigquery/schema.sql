-- BigQuery スキーマ定義
-- データセット: pay_reports

-- データセット作成
-- bq mk --dataset --location=asia-northeast1 monthly-pay-tax:pay_reports

-- 【都度入力】業務報告
CREATE TABLE IF NOT EXISTS `monthly-pay-tax.pay_reports.gyomu_reports` (
  source_url STRING NOT NULL,            -- 元スプレッドシートURL
  year STRING,                           -- 年
  date STRING,                           -- 月日（例: 6/30）
  day_of_week STRING,                    -- 曜日
  activity_category STRING,              -- 活動分類（タダスク, 法人本部 等）
  work_category STRING,                  -- 業務分類（タダスク研修講師 等）
  sponsor STRING,                        -- スポンサー
  description STRING,                    -- 業務内容
  unit_price STRING,                     -- 業務単価（円/h）
  hours STRING,                          -- 所要時間（H）
  amount STRING,                         -- 金額
  ingested_at TIMESTAMP NOT NULL         -- データ取得日時
);

-- 【月１入力】補助＆立替報告＋月締め
CREATE TABLE IF NOT EXISTS `monthly-pay-tax.pay_reports.hojo_reports` (
  source_url STRING NOT NULL,            -- 元スプレッドシートURL
  year STRING,                           -- 年
  month STRING,                          -- 月
  hours STRING,                          -- 時間
  compensation STRING,                   -- 報酬
  dx_subsidy STRING,                     -- DX補助
  reimbursement STRING,                  -- 立替
  total_amount STRING,                   -- 総額
  monthly_complete STRING,               -- 当月入力完了フラグ
  dx_receipt STRING,                     -- DX補助用 領収書添付欄
  expense_receipt STRING,                -- 個人立替用 領収書添付欄
  ingested_at TIMESTAMP NOT NULL         -- データ取得日時
);

-- タダメンMマスタ（メンバー情報）
CREATE TABLE IF NOT EXISTS `monthly-pay-tax.pay_reports.members` (
  report_url STRING NOT NULL,            -- 報告シートURL（gyomu/hojoのsource_urlと結合キー）
  member_id STRING,                      -- タダメンID
  nickname STRING,                       -- ニックネーム
  gws_account STRING,                    -- GWSアカウント
  full_name STRING,                      -- 本名
  ingested_at TIMESTAMP NOT NULL         -- データ取得日時
);
