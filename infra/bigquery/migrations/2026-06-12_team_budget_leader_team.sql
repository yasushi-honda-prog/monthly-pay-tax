-- ============================================================
-- v_team_budget_actuals VIEW 改訂: 統括隊ベース再構成 (PR-A)
-- ============================================================
-- 詳細: docs/specs/2026-06-12-team-budget-leader-team-restructure.md
--
-- 変更点:
--   1. team_hierarchy を INNER JOIN し、隊 (operating 統括隊配下) のみに絞る
--   2. leader_team 列を新規追加 (UI で統括隊集計に使用)
--   3. 非「隊」活動分類 (その他/移動/電話対応 等) を VIEW 層で根本除外
--
-- 設計根拠:
--   - LEFT JOIN だと NULL leader_team 行が残り UI 側で除外する必要があるが、
--     UI 二重フィルタは漏れの原因 (Codex セカンドオピニオン)
--   - COALESCE(a.team, b.team) で予算 only / 実額 only 両方を捕捉した後に
--     hierarchy JOIN するため、team_budgets に非隊を投入してしまった場合の
--     フェールセーフにもなる
--
-- 影響範囲:
--   - dashboard: load_team_budget_actuals / load_active_teams が 隊 only に
--   - cloud-run: team_eval_service.list_active_teams() も VIEW 経由のため
--     AI 評価対象が 隊 のみに自動的に絞られる (要件と合致)
--   - vertex_evaluator.compute_actual_data_hash の hash 計算は gyomu_reports
--     を activity_category=@team で直読するため不変
--
-- 実行コマンド:
--   bq query --use_legacy_sql=false --project_id=monthly-pay-tax \
--     < infra/bigquery/migrations/2026-06-12_team_budget_leader_team.sql
--
-- ロールバック手順:
--   migration apply 前に下記でバックアップ取得:
--     bq show --view --format=prettyjson \
--       monthly-pay-tax:pay_reports.v_team_budget_actuals > /tmp/v_team_budget_actuals_backup.json
--   問題発生時は backup から query を取り出して CREATE OR REPLACE VIEW で復元

CREATE OR REPLACE VIEW `monthly-pay-tax.pay_reports.v_team_budget_actuals` AS
WITH budgets_latest AS (
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
    AND month BETWEEN 1 AND 12
    AND (year > 2026 OR (year = 2026 AND month >= 5))
  GROUP BY year, month, team
),
combined AS (
  -- FULL OUTER JOIN で予算 only / 実額 only / 両方ある の 3 パターンに対応
  SELECT
    COALESCE(a.year, b.year) AS year,
    COALESCE(a.month, b.month) AS month,
    COALESCE(a.team, b.team) AS team,
    a.actual_amount,
    a.actual_count,
    a.reporter_count,
    b.budget_amount
  FROM actuals_agg a
  FULL OUTER JOIN budgets_latest b
    ON a.year = b.year AND a.month = b.month AND a.team = b.team
)
SELECT
  c.year,
  c.month,
  c.team,
  h.leader_team,                                                    -- 新規列 (PR-A)
  c.actual_amount,
  c.actual_count,
  c.reporter_count,
  c.budget_amount,
  CASE WHEN c.budget_amount IS NULL OR c.budget_amount = 0 THEN NULL
       ELSE SAFE_DIVIDE(c.actual_amount, c.budget_amount) * 100 END AS achievement_rate,
  CASE WHEN c.budget_amount IS NULL THEN NULL
       ELSE COALESCE(c.actual_amount, 0) - c.budget_amount END AS diff_amount,
  (c.budget_amount IS NOT NULL) AS has_budget,
  (c.actual_amount IS NOT NULL) AS has_actual
FROM combined c
INNER JOIN `monthly-pay-tax.pay_reports.team_hierarchy` h
  ON c.team = h.activity_category
WHERE h.leader_team_type = 'operating';
