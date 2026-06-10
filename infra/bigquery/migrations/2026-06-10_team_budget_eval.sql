-- 2026-06-10: 隊（活動）分類ごとの月次予実管理機能の BQ 基盤
--
-- 設計仕様: docs/specs/2026-06-10-team-budget-eval-design.md (PR #209)
-- brainstorm セッション: 2026-06-10、Codex セカンドオピニオン 3 ラウンド適用
--
-- 追加内容:
--   1. SQL UDF: extract_month(date_str) - 月抽出ロジックの一元化
--   2. テーブル: team_budgets - 隊×月の予算データ (optimistic lock 付き)
--   3. テーブル: team_monthly_eval - AI 評価キャッシュ (claim row パターン付き)
--   4. VIEW: v_team_budget_actuals - 予実集計の中核 (重複防御 + 月値域チェック)
--
-- 実行コマンド（初回1回のみ。冪等）:
--   bq query --use_legacy_sql=false --project_id=monthly-pay-tax \
--     < infra/bigquery/migrations/2026-06-10_team_budget_eval.sql
--
-- 注意:
--   - VIEW は CREATE OR REPLACE のため、既存 v_team_budget_actuals があれば置換される（本機能では新規なので影響なし）
--   - team_budgets は scripts/upload_budgets.py で投入、または admin 画面の st.data_editor で編集
--   - team_monthly_eval は Cloud Run /eval/team-monthly で UPSERT、history なし

-- ============================================================
-- 1. SQL UDF: extract_month
-- ============================================================
-- gyomu_reports.date の複数形式から月を INT64 で抽出。
-- 既存 v_gyomu_enriched の月抽出ロジックは互換性のため touch しない。
-- 本 UDF は v_team_budget_actuals と Cloud Run の hash 計算 SQL で使用。

CREATE OR REPLACE FUNCTION `monthly-pay-tax.pay_reports.extract_month`(date_str STRING)
AS (
  SAFE_CAST(
    CASE
      -- YYYY/M/D を最優先で判定（先頭 2 桁誤マッチ回避）
      WHEN REGEXP_CONTAINS(date_str, r'^\d{4}/\d{1,2}/') THEN REGEXP_EXTRACT(date_str, r'^\d{4}/(\d{1,2})/')
      -- M/D 形式
      WHEN REGEXP_CONTAINS(date_str, r'^\d{1,2}/') THEN REGEXP_EXTRACT(date_str, r'^(\d{1,2})/')
      -- M月D日 形式
      WHEN REGEXP_CONTAINS(date_str, r'^\d{1,2}月') THEN REGEXP_EXTRACT(date_str, r'^(\d{1,2})月')
      ELSE NULL
    END AS INT64
  )
);


-- ============================================================
-- 2. team_budgets テーブル
-- ============================================================
-- 隊×月の予算データ。optimistic lock (version) で並列更新制御。
-- MERGE は WHERE t.version = expected_version 付きで実行（affected_rows=0 で競合検知）。
-- 入力経路: scripts/upload_budgets.py (CSV → BQ MERGE)、admin 画面 st.data_editor

CREATE TABLE IF NOT EXISTS `monthly-pay-tax.pay_reports.team_budgets` (
  year INT64 NOT NULL,                  -- 例: 2026
  month INT64 NOT NULL,                 -- 例: 5
  team STRING NOT NULL,                 -- gyomu_reports.activity_category と同一値
  budget_amount NUMERIC NOT NULL,       -- 予算金額
  memo STRING,                          -- 任意メモ
  version INT64 NOT NULL,               -- optimistic lock 用（初期値 1、UPDATE で +1）
  created_at TIMESTAMP NOT NULL,
  created_by STRING NOT NULL,           -- email or "script:upload_budgets:<email>"
  updated_at TIMESTAMP NOT NULL,
  updated_by STRING NOT NULL
)
PARTITION BY DATE(updated_at)
CLUSTER BY year, month, team;


-- ============================================================
-- 3. team_monthly_eval テーブル
-- ============================================================
-- AI 評価キャッシュ。(year, month, team) 単位で 1 行を保持 (history なし、UPSERT 方式)。
-- claim row パターンで並列実行制御（lock_token / lock_until / lock_actor）。
-- メタデータ (prompt_version, sample_query_version, location, generation_config_json) を保存し再現性確保。

CREATE TABLE IF NOT EXISTS `monthly-pay-tax.pay_reports.team_monthly_eval` (
  year INT64 NOT NULL,
  month INT64 NOT NULL,
  team STRING NOT NULL,
  actual_amount NUMERIC,                -- 評価生成時点の実額（claim 中は NULL）
  budget_amount NUMERIC,                -- 予算未設定隊は NULL
  achievement_rate FLOAT64,             -- actual/budget*100（budget NULL なら NULL）
  diff_amount NUMERIC,                  -- actual - budget
  actual_data_hash STRING,              -- TO_HEX(SHA256(...)) 差分検知用（claim 中は NULL）
  ai_comment STRING,                    -- Gemini 生成コメント 3-5 行（claim 中は NULL）
  ai_model STRING,                      -- 例: "gemini-2.5-flash"
  ai_prompt_tokens INT64,
  ai_output_tokens INT64,
  prompt_version STRING,                -- 例: "v1"（プロンプト改訂時に新値）
  sample_query_version STRING,          -- 例: "v1"
  location STRING,                      -- 例: "asia-northeast1"
  generation_config_json STRING,        -- 例: {"max_tokens":350,"temperature":0.3,"top_p":0.8}
  generated_at TIMESTAMP,               -- claim 中は NULL
  generated_by STRING,                  -- "scheduler" or email
  -- claim row パターン (並列実行制御、5 分の lock 期限付き)
  lock_token STRING,                    -- 処理中の job_id（NULL なら未 claim、期限切れも未 claim 扱い）
  lock_until TIMESTAMP,                 -- claim 期限（CURRENT_TIMESTAMP() + 5 min）
  lock_actor STRING                     -- claim した actor
)
-- BQ の PARTITION BY は単一カラムのみ許可（COALESCE 等の関数式は不可）。
-- 本テーブルは年間 24 隊 × 12 月 ≒ 288 行の小規模で、CLUSTER のみで十分。
CLUSTER BY year, month, team;


-- ============================================================
-- 4. v_team_budget_actuals VIEW
-- ============================================================
-- 予実集計の中核 VIEW。
--   - actuals_agg: gyomu_reports から 2026/05 以降の隊×月集計を生成（月値域チェック付き）
--   - budgets_latest: team_budgets の重複防御（QUALIFY ROW_NUMBER で最新 updated_at を採用）
--   - FULL OUTER JOIN で予算/実額の有無 4 パターンに対応:
--       * 予算あり/実額あり → 通常表示
--       * 予算なし/実額あり → has_budget=FALSE（UI で「予算未設定」バッジ）
--       * 予算あり/実額なし → has_actual=FALSE（達成率 0%、diff=-budget）
--       * 予算なし/実額なし → 出現しない

CREATE OR REPLACE VIEW `monthly-pay-tax.pay_reports.v_team_budget_actuals` AS
WITH budgets_latest AS (
  -- 重複防御: (year, month, team) で最新を採用
  SELECT * EXCEPT(rn)
  FROM (
    SELECT *, ROW_NUMBER() OVER (
      PARTITION BY year, month, team ORDER BY updated_at DESC, version DESC
    ) AS rn
    FROM `monthly-pay-tax.pay_reports.team_budgets`
  )
  WHERE rn = 1
),
actuals_agg AS (
  -- subquery で year/month を pre-compute し WHERE で filter（GROUP BY 前に prune してコスト削減）
  SELECT year, month, team,
         SUM(amount_numeric) AS actual_amount,
         COUNT(*) AS actual_count,
         COUNT(DISTINCT source_url) AS reporter_count
  FROM (
    SELECT
      SAFE_CAST(g.year AS INT64) AS year,
      `monthly-pay-tax.pay_reports.extract_month`(g.date) AS month,
      g.activity_category AS team,
      SAFE_CAST(REGEXP_REPLACE(g.amount, r'[^0-9.-]', '') AS NUMERIC) AS amount_numeric,
      g.source_url
    FROM `monthly-pay-tax.pay_reports.gyomu_reports` g
    WHERE g.activity_category IS NOT NULL AND g.activity_category != ''
  )
  WHERE year IS NOT NULL AND month IS NOT NULL
    AND month BETWEEN 1 AND 12  -- 値域チェック
    AND (year > 2026 OR (year = 2026 AND month >= 5))  -- 2026/05 以降のみ
  GROUP BY year, month, team
)
SELECT
  COALESCE(a.year, b.year) AS year,
  COALESCE(a.month, b.month) AS month,
  COALESCE(a.team, b.team) AS team,
  a.actual_amount,
  a.actual_count,
  a.reporter_count,
  b.budget_amount,
  CASE WHEN b.budget_amount IS NULL OR b.budget_amount = 0 THEN NULL
       ELSE SAFE_DIVIDE(a.actual_amount, b.budget_amount) * 100 END AS achievement_rate,
  CASE WHEN b.budget_amount IS NULL THEN NULL
       ELSE COALESCE(a.actual_amount, 0) - b.budget_amount END AS diff_amount,
  (b.budget_amount IS NOT NULL) AS has_budget,
  (a.actual_amount IS NOT NULL) AS has_actual
FROM actuals_agg a
FULL OUTER JOIN budgets_latest b
  ON a.year = b.year AND a.month = b.month AND a.team = b.team;
