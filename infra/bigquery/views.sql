-- BigQuery VIEW 定義
-- データセット: pay_reports
--
-- GASバインドSSのスプレッドシート関数パイプラインを SQL で再現:
--   - タダメンID / メンバー情報の結合
--   - 月抽出（gyomu の date カラムから）
--   - 距離分離（自家用車使用の場合 hours → travel_distance_km）
--   - 1立てフラグ（日給制）
--   - 総稼働時間（全日稼働 +6h / 半日稼働 +3h）
--   - hojo の年月正規化（Excel シリアル値・日付文字列対応）

-- ============================================================
-- v_gyomu_enriched: 業務報告 + メンバー情報 + 加工フィールド
-- ============================================================
CREATE OR REPLACE VIEW `monthly-pay-tax.pay_reports.v_gyomu_enriched` AS
SELECT
  g.source_url,
  g.year,
  g.date,
  g.day_of_week,
  g.activity_category,
  g.work_category,
  g.sponsor,
  g.description,
  g.unit_price,
  g.amount,
  -- メンバー情報
  m.member_id,
  m.nickname,
  m.full_name,
  -- 月抽出: "M/D" or "M月D日" 形式から月を取得
  SAFE_CAST(
    CASE
      WHEN REGEXP_CONTAINS(g.date, r'^\d{1,2}/') THEN REGEXP_EXTRACT(g.date, r'^(\d{1,2})/')
      WHEN REGEXP_CONTAINS(g.date, r'^\d{1,2}月') THEN REGEXP_EXTRACT(g.date, r'^(\d{1,2})月')
      WHEN REGEXP_CONTAINS(g.date, r'^\d{4}/(\d{1,2})/') THEN REGEXP_EXTRACT(g.date, r'^\d{4}/(\d{1,2})/')
      ELSE NULL
    END AS INT64
  ) AS month,
  -- 距離分離: 自家用車使用なら hours は移動距離
  CASE
    WHEN g.work_category = '自家用車使用' THEN NULL
    ELSE g.hours
  END AS work_hours,
  CASE
    WHEN g.work_category = '自家用車使用' THEN g.hours
    ELSE NULL
  END AS travel_distance_km,
  -- 1立てフラグ: 日給制を含む場合
  CASE
    WHEN REGEXP_CONTAINS(g.work_category, r'日給制') THEN 1
    ELSE NULL
  END AS daily_wage_flag,
  -- 総稼働時間: 所要時間 + 全日稼働(+6h) / 半日稼働(+3h)
  SAFE_CAST(
    CASE WHEN g.work_category = '自家用車使用' THEN NULL ELSE g.hours END
    AS FLOAT64
  ) + CASE
    WHEN REGEXP_CONTAINS(g.work_category, r'全日稼働') THEN 6.0
    WHEN REGEXP_CONTAINS(g.work_category, r'半日稼働') THEN 3.0
    ELSE 0.0
  END AS total_work_hours,
  g.ingested_at
FROM `monthly-pay-tax.pay_reports.gyomu_reports` g
LEFT JOIN `monthly-pay-tax.pay_reports.members` m
  ON g.source_url = m.report_url;


-- ============================================================
-- v_hojo_enriched: 補助報告 + メンバー情報 + 年月正規化
-- ============================================================
CREATE OR REPLACE VIEW `monthly-pay-tax.pay_reports.v_hojo_enriched` AS
SELECT
  h.source_url,
  h.hours,
  h.compensation,
  h.dx_subsidy,
  h.reimbursement,
  h.total_amount,
  h.monthly_complete,
  h.dx_receipt,
  h.expense_receipt,
  -- メンバー情報
  m.member_id,
  m.nickname,
  m.full_name,
  -- 年の正規化: 数値年 / 日付文字列 / Excel シリアル値を統一
  SAFE_CAST(
    CASE
      WHEN SAFE_CAST(h.year AS INT64) BETWEEN 2020 AND 2030
        THEN h.year
      WHEN REGEXP_CONTAINS(h.year, r'^\d{4}/\d{1,2}/\d{1,2}$')
        THEN REGEXP_EXTRACT(h.year, r'^(\d{4})/')
      WHEN SAFE_CAST(h.year AS INT64) > 40000
        THEN CAST(EXTRACT(YEAR FROM DATE_ADD(DATE '1899-12-30', INTERVAL CAST(h.year AS INT64) DAY)) AS STRING)
      ELSE NULL
    END AS INT64
  ) AS year,
  -- 月の正規化
  SAFE_CAST(
    CASE
      WHEN SAFE_CAST(h.month AS INT64) BETWEEN 1 AND 12
        THEN h.month
      WHEN REGEXP_CONTAINS(h.month, r'^\d{4}/\d{1,2}/\d{1,2}$')
        THEN REGEXP_EXTRACT(h.month, r'^\d{4}/(\d{1,2})/')
      WHEN SAFE_CAST(h.month AS INT64) > 40000
        THEN CAST(EXTRACT(MONTH FROM DATE_ADD(DATE '1899-12-30', INTERVAL CAST(h.month AS INT64) DAY)) AS STRING)
      ELSE NULL
    END AS INT64
  ) AS month,
  h.ingested_at
FROM `monthly-pay-tax.pay_reports.hojo_reports` h
LEFT JOIN `monthly-pay-tax.pay_reports.members` m
  ON h.source_url = m.report_url;
