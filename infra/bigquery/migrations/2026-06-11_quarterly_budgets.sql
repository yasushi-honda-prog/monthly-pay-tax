-- 2026-06-11: 四半期 × 統括隊 × 支出カテゴリ予算 (PR-E)
--
-- 設計仕様: docs/specs/2026-06-10-team-budget-eval-design.md §Phase 2 (PR #215)
-- セッション: 2026-06-10 末尾の AskUserQuestion + Codex セカンドオピニオン (High 3 + Medium 4) で確定
--
-- 追加内容:
--   1. SQL UDF: fiscal_quarter(year, month) → STRUCT<fiscal_year, fiscal_quarter>
--      会計年度は 11 月始まり (案 N11): Q1=11-1月 / Q2=2-4月 / Q3=5-7月 / Q4=8-10月
--   2. テーブル: expense_categories - 支出カテゴリマスタ (7 行 seed)
--   3. テーブル: team_hierarchy - activity_category ↔ leader_team の階層 (現在値のみ、案 T-NOW)
--   4. テーブル: team_budgets_quarterly - 四半期 × 統括隊 × カテゴリの予算 (optimistic lock)
--   5. VIEW: v_team_budget_actuals_quarterly - 予実集計 (actual_mapping_status 4 状態)
--   6. VIEW: v_team_hierarchy_coverage - hierarchy ↔ gyomu 出現の差分検知
--
-- 既存テーブル team_budgets (隊×月) は維持。本機能は四半期×統括隊×カテゴリの別軸。
--
-- 実行コマンド (初回1回のみ。冪等):
--   bq query --use_legacy_sql=false --project_id=monthly-pay-tax \
--     < infra/bigquery/migrations/2026-06-11_quarterly_budgets.sql

-- ============================================================
-- 1. SQL UDF: fiscal_quarter (案 N11: 11 月始まり)
-- ============================================================
-- 入力: 暦年 (INT64) + 暦月 (INT64)
-- 返値: STRUCT<fiscal_year INT64, fiscal_quarter INT64>
--
-- Q1 = 11-12-1月  / Q2 = 2-3-4月 / Q3 = 5-6-7月 / Q4 = 8-9-10月
-- fiscal_year は終了月 (10月) の暦年に整列:
--   暦 2025-11 → FY2026 Q1, 暦 2025-12 → FY2026 Q1, 暦 2026-01 → FY2026 Q1
--   暦 2026-02 → FY2026 Q2, ..., 暦 2026-10 → FY2026 Q4
--   暦 2026-11 → FY2027 Q1
--
-- Codex High-1 指摘 (暦年 Q3=7-9月 ではなく会計 Q3=5-7月) を反映。

CREATE OR REPLACE FUNCTION `monthly-pay-tax.pay_reports.fiscal_quarter`(year INT64, month INT64)
AS (
  STRUCT(
    IF(month >= 11, year + 1, year) AS fiscal_year,
    1 + DIV(MOD(month - 11 + 12, 12), 3) AS fiscal_quarter
  )
);


-- ============================================================
-- 2. expense_categories テーブル + 7 行 seed
-- ============================================================
-- 支出カテゴリマスタ。typo 防止のため team_budgets_quarterly の expense_category は JOIN 検証必須。
-- actual_source: Phase 1 で実額紐付け実装したソース ('gyomu'/'reimbursement'/'none')
-- is_phase1_supported: Phase 1 で実額紐付けが機能するか (Phase 2 で順次拡張)
--
-- Codex Medium-6 指摘 (日本語表記揺れ) を反映。

CREATE TABLE IF NOT EXISTS `monthly-pay-tax.pay_reports.expense_categories` (
  sort INT64 NOT NULL,                    -- 表示順 (1-7、画像と同一)
  expense_category STRING NOT NULL,       -- 支出カテゴリ名 (PK)
  actual_source STRING NOT NULL,          -- 'gyomu' | 'reimbursement' | 'none'
  is_phase1_supported BOOL NOT NULL,      -- Phase 1 で実額紐付け済か
  note STRING                             -- 任意メモ
);

-- seed (冪等。MERGE で再アップロード時の差分のみ反映)
MERGE `monthly-pay-tax.pay_reports.expense_categories` t
USING (
  SELECT * FROM UNNEST([
    STRUCT(1 AS sort, 'タダメン業務委託費' AS expense_category, 'gyomu' AS actual_source,
           TRUE AS is_phase1_supported, 'gyomu_reports.amount を統括隊で集計' AS note),
    STRUCT(2, '旅費交通費', 'reimbursement', FALSE,
           'reimbursement_items.category マッピングは Phase 2'),
    STRUCT(3, '消耗品費', 'reimbursement', FALSE,
           'reimbursement_items.category マッピングは Phase 2'),
    STRUCT(4, '通信運搬費', 'reimbursement', FALSE,
           'reimbursement_items.category マッピングは Phase 2'),
    STRUCT(5, '広告宣伝費', 'reimbursement', FALSE,
           'reimbursement_items.category マッピングは Phase 2'),
    STRUCT(6, '自由に使える10万円', 'none', FALSE,
           '利用追跡仕様は Phase 2 で確認'),
    STRUCT(7, '共通費', 'none', FALSE,
           '本部費按分ロジックは Phase 2 で確認')
  ])
) s
ON t.expense_category = s.expense_category
WHEN MATCHED THEN UPDATE SET
  sort = s.sort, actual_source = s.actual_source,
  is_phase1_supported = s.is_phase1_supported, note = s.note
WHEN NOT MATCHED THEN INSERT
  (sort, expense_category, actual_source, is_phase1_supported, note)
  VALUES (s.sort, s.expense_category, s.actual_source, s.is_phase1_supported, s.note);


-- ============================================================
-- 3. team_hierarchy テーブル
-- ============================================================
-- activity_category (隊) ↔ leader_team (統括隊) の階層マッピング。
-- 案 T-NOW: 現在値のみ保持 (organization 履歴は持たない、組織再編は schema migration で対応)。
--
-- leader_team_type:
--   - 'operating': 通常の統括隊 (6 つの想定: シロロ+ゆずるん統括隊 等)
--   - 'common':    共通枠の virtual 統括隊 (Phase 2 で「共通費」「自由10万」を持たせる予定)
--
-- 入力経路: scripts/upload_team_hierarchy.py (CSV → MERGE)
-- Codex High-2 指摘 (組織再編脆弱性) を反映: PK = activity_category 単独だが現在値のみ前提で許容。

CREATE TABLE IF NOT EXISTS `monthly-pay-tax.pay_reports.team_hierarchy` (
  activity_category STRING NOT NULL,      -- gyomu_reports.activity_category と同一値 (PK)
  leader_team STRING NOT NULL,            -- 統括隊名 (例: 'シロロ+ゆずるん統括隊')
  leader_team_type STRING NOT NULL,       -- 'operating' | 'common'
  note STRING,                            -- 任意メモ
  version INT64 NOT NULL,                 -- optimistic lock 用
  created_at TIMESTAMP NOT NULL,
  created_by STRING NOT NULL,
  updated_at TIMESTAMP NOT NULL,
  updated_by STRING NOT NULL
)
PARTITION BY DATE(updated_at)
CLUSTER BY leader_team, activity_category;


-- ============================================================
-- 4. team_budgets_quarterly テーブル
-- ============================================================
-- 四半期 × 統括隊 × 支出カテゴリの予算データ。
-- PK: (fiscal_year, fiscal_quarter, leader_team, expense_category)
-- 既存 team_budgets (隊×月) と並存し、別軸の予算管理を実現。
--
-- 入力経路: scripts/upload_team_budgets_quarterly.py (matrix or long CSV → MERGE)
-- Codex Medium-4 指摘 (粒度差) を反映: 月別予算は team_budgets、四半期予算は本テーブル。

CREATE TABLE IF NOT EXISTS `monthly-pay-tax.pay_reports.team_budgets_quarterly` (
  fiscal_year INT64 NOT NULL,             -- 例: 2026 (11月始まり、Q1 開始月の翌暦年)
  fiscal_quarter INT64 NOT NULL,          -- 1-4
  leader_team STRING NOT NULL,            -- team_hierarchy.leader_team と JOIN
  expense_category STRING NOT NULL,       -- expense_categories.expense_category と JOIN
  budget_amount NUMERIC NOT NULL,         -- 予算金額
  memo STRING,                            -- 任意メモ
  version INT64 NOT NULL,                 -- optimistic lock 用
  created_at TIMESTAMP NOT NULL,
  created_by STRING NOT NULL,
  updated_at TIMESTAMP NOT NULL,
  updated_by STRING NOT NULL
)
PARTITION BY DATE(updated_at)
CLUSTER BY fiscal_year, fiscal_quarter, leader_team;


-- ============================================================
-- 5. v_team_budget_actuals_quarterly VIEW
-- ============================================================
-- 予実集計 (四半期 × 統括隊 × カテゴリ)。Phase 1 は actual_source='gyomu' のみ実額マッピング。
--
-- actual_mapping_status (4 状態):
--   - 'mapped': Phase 1 対応カテゴリ + 予算あり + 実額あり
--   - 'no_actual_rows': Phase 1 対応カテゴリ + 予算あり + 実額 0 件
--   - 'not_supported_in_phase1': Phase 2 以降対応カテゴリ (旅費/消耗品/通信/広告/自由10万/共通費)
--   - 'budget_missing': 実額あり + 予算未設定
--
-- Codex High-3 指摘 (NULL と Phase1 未対応の区別不能) を反映。

CREATE OR REPLACE VIEW `monthly-pay-tax.pay_reports.v_team_budget_actuals_quarterly` AS
WITH
-- gyomu_reports から金額を pre-parse し fiscal_year × fiscal_quarter × leader_team × expense_category 単位で集計
-- Codex M3 反映: SAFE_CAST 失敗 (parse 不能行) は actual_count から除外し、invalid_amount_count として別カウント
gyomu_parsed AS (
  SELECT
    fq.fiscal_year,
    fq.fiscal_quarter,
    th.leader_team,
    SAFE_CAST(REGEXP_REPLACE(g.amount, r'[^0-9.-]', '') AS NUMERIC) AS parsed_amount
  FROM `monthly-pay-tax.pay_reports.gyomu_reports` g
  JOIN `monthly-pay-tax.pay_reports.team_hierarchy` th
    ON g.activity_category = th.activity_category
  CROSS JOIN UNNEST([`monthly-pay-tax.pay_reports.fiscal_quarter`(
    SAFE_CAST(g.year AS INT64),
    `monthly-pay-tax.pay_reports.extract_month`(g.date)
  )]) AS fq
  WHERE g.activity_category IS NOT NULL AND g.activity_category != ''
    AND SAFE_CAST(g.year AS INT64) IS NOT NULL
    AND `monthly-pay-tax.pay_reports.extract_month`(g.date) IS NOT NULL
    AND `monthly-pay-tax.pay_reports.extract_month`(g.date) BETWEEN 1 AND 12
    AND th.leader_team_type = 'operating'
),
gyomu_actuals AS (
  SELECT
    fiscal_year,
    fiscal_quarter,
    leader_team,
    'タダメン業務委託費' AS expense_category,
    SUM(parsed_amount) AS actual_amount,
    COUNTIF(parsed_amount IS NOT NULL) AS actual_count,
    COUNTIF(parsed_amount IS NULL) AS invalid_amount_count
  FROM gyomu_parsed
  GROUP BY fiscal_year, fiscal_quarter, leader_team
),
-- team_budgets_quarterly の重複防御 (同 PK の重複は (updated_at DESC, version DESC) で最新を採用)
budgets_latest AS (
  SELECT * EXCEPT(rn)
  FROM (
    SELECT *, ROW_NUMBER() OVER (
      PARTITION BY fiscal_year, fiscal_quarter, leader_team, expense_category
      ORDER BY updated_at DESC, version DESC
    ) AS rn
    FROM `monthly-pay-tax.pay_reports.team_budgets_quarterly`
  )
  WHERE rn = 1
)
SELECT
  COALESCE(b.fiscal_year, a.fiscal_year) AS fiscal_year,
  COALESCE(b.fiscal_quarter, a.fiscal_quarter) AS fiscal_quarter,
  COALESCE(b.leader_team, a.leader_team) AS leader_team,
  COALESCE(b.expense_category, a.expense_category) AS expense_category,
  ec.actual_source,
  ec.is_phase1_supported,
  b.budget_amount,
  a.actual_amount,
  a.actual_count,
  a.invalid_amount_count,
  CASE
    WHEN b.budget_amount IS NULL THEN NULL
    WHEN b.budget_amount = 0 THEN NULL
    ELSE SAFE_DIVIDE(COALESCE(a.actual_amount, 0), b.budget_amount) * 100
  END AS achievement_rate,
  CASE
    WHEN b.budget_amount IS NULL THEN NULL
    ELSE COALESCE(a.actual_amount, 0) - b.budget_amount
  END AS diff_amount,
  CASE
    WHEN ec.is_phase1_supported IS NULL THEN 'unknown_category'
    WHEN NOT ec.is_phase1_supported AND b.budget_amount IS NOT NULL THEN 'not_supported_in_phase1'
    WHEN b.budget_amount IS NULL AND a.actual_amount IS NOT NULL THEN 'budget_missing'
    WHEN b.budget_amount IS NOT NULL AND a.actual_amount IS NULL THEN 'no_actual_rows'
    WHEN b.budget_amount IS NOT NULL AND a.actual_amount IS NOT NULL THEN 'mapped'
    ELSE 'unknown'
  END AS actual_mapping_status
FROM budgets_latest b
FULL OUTER JOIN gyomu_actuals a
  ON b.fiscal_year = a.fiscal_year
  AND b.fiscal_quarter = a.fiscal_quarter
  AND b.leader_team = a.leader_team
  AND b.expense_category = a.expense_category
LEFT JOIN `monthly-pay-tax.pay_reports.expense_categories` ec
  ON COALESCE(b.expense_category, a.expense_category) = ec.expense_category;


-- ============================================================
-- 6. v_team_hierarchy_coverage VIEW
-- ============================================================
-- team_hierarchy 定義と gyomu_reports 出現 activity_category の差分検知。
-- 運用ガイド: 'UNMAPPED' があれば hierarchy CSV を更新、'UNUSED' は組織変更で実額ゼロ。
--
-- Codex Medium-5 指摘 (hierarchy 再アップロード silent change) を反映: 隊が漏れたら本 VIEW で検知。

CREATE OR REPLACE VIEW `monthly-pay-tax.pay_reports.v_team_hierarchy_coverage` AS
WITH
gyomu_categories AS (
  SELECT DISTINCT activity_category
  FROM `monthly-pay-tax.pay_reports.gyomu_reports`
  WHERE activity_category IS NOT NULL AND activity_category != ''
),
hierarchy_categories AS (
  SELECT activity_category, leader_team, leader_team_type
  FROM `monthly-pay-tax.pay_reports.team_hierarchy`
)
SELECT
  COALESCE(g.activity_category, h.activity_category) AS activity_category,
  h.leader_team,
  h.leader_team_type,
  CASE
    WHEN g.activity_category IS NOT NULL AND h.activity_category IS NOT NULL THEN 'MAPPED'
    WHEN g.activity_category IS NOT NULL AND h.activity_category IS NULL THEN 'UNMAPPED'
    WHEN g.activity_category IS NULL AND h.activity_category IS NOT NULL THEN 'UNUSED'
    ELSE 'UNKNOWN'
  END AS status
FROM gyomu_categories g
FULL OUTER JOIN hierarchy_categories h
  ON g.activity_category = h.activity_category;
