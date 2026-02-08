-- 源泉対象リスト seedデータ
-- 源泉対象の業務分類 + 士業さん（全額源泉対象メンバー）
--
-- 実行:
--   bq query --use_legacy_sql=false < infra/bigquery/seed_withholding_targets.sql

-- テーブル初期化
DELETE FROM `monthly-pay-tax.pay_reports.withholding_targets` WHERE TRUE;

-- 源泉対象の業務分類（15種類）
INSERT INTO `monthly-pay-tax.pay_reports.withholding_targets` (work_category, licensed_member_id)
VALUES
  ('タダスク研修講師', NULL),
  ('出張タダスク講師', NULL),
  ('タダサポ', NULL),
  ('タダレク事務局・司会', NULL),
  ('タダカヨ広報業務', NULL),
  ('タダスク関連', NULL),
  ('出張タダスク関連', NULL),
  ('タダサポ（個別支援）関連', NULL),
  ('タダレク関連', NULL),
  ('タダカヨ広報関連', NULL),
  ('タダスク関連【1講座ごと】', NULL),
  ('タダマニュ関連', NULL),
  ('フロント（新ルール）【開催日に包括算定】', NULL),
  ('出張タダスク講師（新ルール）【開催日に包括算定】', NULL),
  ('出張タダスク講師（旧ルール）', NULL);

-- 士業さん（全ての金額に源泉計算：加算も全部）
-- 士業メンバー1: タダスク研修講師
INSERT INTO `monthly-pay-tax.pay_reports.withholding_targets` (work_category, licensed_member_id)
VALUES ('タダスク研修講師', '2d0910f7');

-- 士業メンバー2: 出張タダスク講師
INSERT INTO `monthly-pay-tax.pay_reports.withholding_targets` (work_category, licensed_member_id)
VALUES ('出張タダスク講師', '144dcaaf');
