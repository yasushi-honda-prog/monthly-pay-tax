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
  -- 総稼働時間: 全日稼働→6h / 半日稼働→3h に置換、それ以外は所要時間
  CASE
    WHEN g.work_category = '自家用車使用' THEN NULL
    WHEN REGEXP_CONTAINS(g.work_category, r'全日稼働') THEN 6.0
    WHEN REGEXP_CONTAINS(g.work_category, r'半日稼働') THEN 3.0
    ELSE SAFE_CAST(g.hours AS FLOAT64)
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


-- ============================================================
-- v_monthly_compensation: 月別報酬＆源泉徴収（スプレッドシート完全再現）
-- ============================================================
-- メンバー × 年 × 月 で gyomu + hojo を集計し、
-- 報酬計算 → 役職手当 → 資格手当 → 源泉徴収 → 支払い を算出。
-- 源泉対象リスト（withholding_targets テーブル）を参照。
CREATE OR REPLACE VIEW `monthly-pay-tax.pay_reports.v_monthly_compensation` AS
WITH
-- ─── CTE 1: 業務報告の月別集計 ───
gyomu_agg AS (
  SELECT
    g.source_url,
    SAFE_CAST(g.year AS INT64) AS year,
    g.month,
    -- K: 時間（自家用車使用以外）
    SUM(SAFE_CAST(g.work_hours AS FLOAT64)) AS work_hours,
    -- L: (時間)報酬 = 所要時間ありの金額合計
    SUM(CASE WHEN g.work_hours IS NOT NULL AND g.work_hours != ''
         THEN SAFE_CAST(REGEXP_REPLACE(g.amount, r'[^0-9.\-]', '') AS FLOAT64) END) AS hour_compensation,
    -- M: 距離
    SUM(SAFE_CAST(g.travel_distance_km AS FLOAT64)) AS travel_distance_km,
    -- N: (距離)報酬 = 移動距離ありの金額合計
    SUM(CASE WHEN g.travel_distance_km IS NOT NULL AND g.travel_distance_km != ''
         THEN SAFE_CAST(REGEXP_REPLACE(g.amount, r'[^0-9.\-]', '') AS FLOAT64) END) AS distance_compensation,
    -- AB: 1立て件数
    SUM(g.daily_wage_flag) AS daily_wage_count,
    -- AC: 全日稼働の報酬（1立て報酬）
    SUM(CASE WHEN REGEXP_CONTAINS(g.work_category, r'全日稼働')
         THEN SAFE_CAST(REGEXP_REPLACE(g.amount, r'[^0-9.\-]', '') AS FLOAT64) END) AS full_day_compensation,
    -- AD: 総稼働時間（1立て込み）
    SUM(g.total_work_hours) AS total_work_hours,
    -- 源泉対象業務分類のみの金額合計（士業以外用）
    SUM(CASE WHEN g.work_category IN (
           SELECT DISTINCT work_category
           FROM `monthly-pay-tax.pay_reports.withholding_targets`
           WHERE licensed_member_id IS NULL
         ) THEN SAFE_CAST(REGEXP_REPLACE(g.amount, r'[^0-9.\-]', '') AS FLOAT64) END) AS withholding_eligible_amount
  FROM `monthly-pay-tax.pay_reports.v_gyomu_enriched` g
  WHERE g.year IS NOT NULL AND g.month IS NOT NULL
  GROUP BY g.source_url, SAFE_CAST(g.year AS INT64), g.month
),

-- ─── CTE 2: 補助報告の月別集計 ───
hojo_agg AS (
  SELECT
    h.source_url,
    h.year,
    h.month,
    -- V: DX補助
    SUM(SAFE_CAST(REGEXP_REPLACE(NULLIF(h.dx_subsidy, ''), r'[^0-9.\-]', '') AS FLOAT64)) AS dx_subsidy,
    -- W: 立替
    SUM(SAFE_CAST(REGEXP_REPLACE(NULLIF(h.reimbursement, ''), r'[^0-9.\-]', '') AS FLOAT64)) AS reimbursement
  FROM `monthly-pay-tax.pay_reports.v_hojo_enriched` h
  WHERE h.year IS NOT NULL AND h.month IS NOT NULL
  GROUP BY h.source_url, h.year, h.month
),

-- ─── CTE 3: メンバー属性（法人/寄付/士業フラグ） ───
member_attrs AS (
  SELECT
    m.report_url,
    m.member_id,
    m.nickname,
    m.full_name,
    SAFE_CAST(NULLIF(CAST(m.position_rate AS STRING), '') AS FLOAT64) AS position_rate,
    SAFE_CAST(NULLIF(CAST(m.qualification_allowance AS STRING), '') AS FLOAT64) AS qualification_allowance,
    m.sheet_number,
    m.corporate_sheet,
    m.donation_sheet,
    m.qualification_sheet,
    -- 法人判定: TRIM(ASC(sheet_number)) = TRIM(ASC(corporate_sheet))
    CASE
      WHEN COALESCE(TRIM(m.sheet_number), '') != ''
        AND TRIM(m.sheet_number) = TRIM(m.corporate_sheet)
      THEN TRUE ELSE FALSE
    END AS is_corporate,
    -- 寄付判定: sheet_number = donation_sheet
    CASE
      WHEN COALESCE(TRIM(m.sheet_number), '') != ''
        AND TRIM(m.sheet_number) = TRIM(m.donation_sheet)
      THEN TRUE ELSE FALSE
    END AS is_donation,
    -- 士業判定: member_id が withholding_targets.licensed_member_id に存在
    CASE
      WHEN m.member_id IN (
        SELECT DISTINCT licensed_member_id
        FROM `monthly-pay-tax.pay_reports.withholding_targets`
        WHERE licensed_member_id IS NOT NULL
      ) THEN TRUE ELSE FALSE
    END AS is_licensed,
    -- 資格手当加算対象: sheet_number = qualification_sheet
    CASE
      WHEN COALESCE(TRIM(m.sheet_number), '') != ''
        AND TRIM(m.sheet_number) = TRIM(m.qualification_sheet)
        AND SAFE_CAST(NULLIF(CAST(m.qualification_allowance AS STRING), '') AS FLOAT64) > 0
      THEN SAFE_CAST(CAST(m.qualification_allowance AS STRING) AS FLOAT64)
      ELSE 0
    END AS effective_qualification_allowance
  FROM `monthly-pay-tax.pay_reports.members` m
),

-- ─── CTE 4: gyomu と hojo のキー統合 ───
all_keys AS (
  SELECT source_url, year, month FROM gyomu_agg
  UNION DISTINCT
  SELECT source_url, year, month FROM hojo_agg
),

-- ─── CTE 5: 基本計算（小計 → 役職手当 → 資格手当加算） ───
base_calc AS (
  SELECT
    k.year,
    k.month,
    ma.member_id,
    ma.nickname,
    ma.full_name,
    ma.is_corporate,
    ma.is_donation,
    ma.is_licensed,
    ma.position_rate,
    ma.effective_qualification_allowance,
    ma.report_url,

    -- gyomu 集計値
    COALESCE(g.work_hours, 0) AS work_hours,
    COALESCE(g.hour_compensation, 0) AS hour_compensation,
    COALESCE(g.travel_distance_km, 0) AS travel_distance_km,
    COALESCE(g.distance_compensation, 0) AS distance_compensation,
    COALESCE(g.daily_wage_count, 0) AS daily_wage_count,
    COALESCE(g.full_day_compensation, 0) AS full_day_compensation,
    COALESCE(g.total_work_hours, 0) AS total_work_hours,
    COALESCE(g.withholding_eligible_amount, 0) AS withholding_eligible_amount,

    -- O: (小計)報酬
    COALESCE(g.hour_compensation, 0) + COALESCE(g.distance_compensation, 0) AS subtotal,

    -- Q: (役職手当率計算)報酬 = FLOOR(subtotal * (1 + position_rate / 100))
    CAST(FLOOR(
      (COALESCE(g.hour_compensation, 0) + COALESCE(g.distance_compensation, 0))
      * (1 + COALESCE(ma.position_rate, 0) / 100.0)
    ) AS INT64) AS position_adjusted,

    -- S: (資格手当加算)報酬 = position_adjusted + qualification_allowance
    CAST(FLOOR(
      (COALESCE(g.hour_compensation, 0) + COALESCE(g.distance_compensation, 0))
      * (1 + COALESCE(ma.position_rate, 0) / 100.0)
    ) AS INT64) + CAST(ma.effective_qualification_allowance AS INT64) AS qualification_adjusted,

    -- hojo 集計値
    COALESCE(h.dx_subsidy, 0) AS dx_subsidy,
    COALESCE(h.reimbursement, 0) AS reimbursement
  FROM all_keys k
  JOIN member_attrs ma ON k.source_url = ma.report_url
  LEFT JOIN gyomu_agg g
    ON k.source_url = g.source_url AND k.year = g.year AND k.month = g.month
  LEFT JOIN hojo_agg h
    ON k.source_url = h.source_url AND k.year = h.year AND k.month = h.month
),

-- ─── CTE 6: 源泉対象額 → 源泉徴収を事前計算 ───
with_tax AS (
  SELECT
    bc.*,
    -- T: 源泉対象業務合計金額
    CASE
      WHEN bc.is_licensed THEN bc.qualification_adjusted + bc.dx_subsidy + bc.reimbursement
      ELSE bc.withholding_eligible_amount
    END AS withholding_target_amount,
    -- U: 源泉 = -FLOOR(T * 0.1021)  ※法人・寄付は除外
    CASE
      WHEN NOT bc.is_corporate AND NOT bc.is_donation THEN
        -1 * CAST(FLOOR(
          CASE
            WHEN bc.is_licensed THEN bc.qualification_adjusted + bc.dx_subsidy + bc.reimbursement
            ELSE bc.withholding_eligible_amount
          END * 0.1021
        ) AS INT64)
      ELSE 0
    END AS withholding_tax
  FROM base_calc bc
)

-- ─── 最終 SELECT: 支払い を算出 ───
SELECT
  t.year,
  t.month,
  t.member_id,
  t.nickname,
  t.full_name,
  t.is_corporate,
  t.is_donation,
  t.is_licensed,
  t.report_url,

  -- K: 時間
  t.work_hours,
  -- L: (時間)報酬
  t.hour_compensation,
  -- M: 距離
  t.travel_distance_km,
  -- N: (距離)報酬
  t.distance_compensation,
  -- O: (小計)報酬
  t.subtotal AS subtotal_compensation,
  -- P: 役職手当率
  COALESCE(t.position_rate, 0) AS position_rate,
  -- Q: (役職手当率計算)報酬
  t.position_adjusted AS position_adjusted_compensation,
  -- R: 資格手当
  t.effective_qualification_allowance AS qualification_allowance,
  -- S: (資格手当加算)報酬
  t.qualification_adjusted AS qualification_adjusted_compensation,
  -- T: 源泉対象業務合計金額
  t.withholding_target_amount,
  -- U: 源泉
  t.withholding_tax,
  -- V: DX補助
  t.dx_subsidy,
  -- W: 立替
  t.reimbursement,

  -- J: 支払い（条件分岐）
  CASE
    WHEN t.qualification_adjusted = 0 AND t.dx_subsidy = 0 AND t.reimbursement = 0 THEN NULL
    WHEN t.member_id = 'b16b4132' THEN t.dx_subsidy + t.reimbursement
    WHEN t.is_donation THEN
      CASE WHEN t.reimbursement = 0 THEN NULL ELSE t.reimbursement END
    ELSE t.qualification_adjusted + t.withholding_tax + t.dx_subsidy + t.reimbursement
  END AS payment,

  -- AA: 寄付支払い
  CASE
    WHEN t.is_donation AND t.qualification_adjusted > 0
    THEN t.qualification_adjusted
    ELSE NULL
  END AS donation_payment,

  -- AB: 1立て件数
  t.daily_wage_count,
  -- AC: 1立て報酬（全日稼働分）
  t.full_day_compensation,
  -- AD: 総稼働時間
  t.total_work_hours

FROM with_tax t
WHERE t.qualification_adjusted > 0
   OR t.dx_subsidy > 0
   OR t.reimbursement > 0
   OR t.work_hours > 0;
