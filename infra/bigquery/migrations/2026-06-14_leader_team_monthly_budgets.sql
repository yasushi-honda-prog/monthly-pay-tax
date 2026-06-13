-- ============================================================
-- leader_team_monthly_budgets テーブル新規作成 + 2026 seed MERGE (Issue #248)
-- ============================================================
-- 詳細: docs/specs/2026-06-14-leader-team-monthly-budget.md
--
-- 目的:
--   PR #247 で全体タブ月次推移グラフを team_budgets_quarterly ÷3 ベースに修正したが
--   同四半期内 3 ヶ月が同値になり「月毎の推移」として意味をなさない問題への恒久対応。
--   統括隊レベルの月別予算を fiscal_year × month × leader_team で持つことで
--   月毎に手調整可能にし、月次推移グラフを本来の用途に戻す。
--
-- 設計判断:
--   - PK 相当: (fiscal_year, month, leader_team) を MERGE で保証 (BQ は PK 制約なし)
--   - partition なし: 1 fiscal_year あたり 72 行のみ、最大数年で 300 行程度
--   - cluster: fiscal_year, leader_team で fetch_yearly の filter 効率化
--   - 型: budget_amount は NUMERIC (既存 team_budgets / team_budgets_quarterly と統一)、
--     Python 側で int 化 (円整数運用、Codex L1 反映)
--
-- 冪等性 (Codex H2 反映):
--   seed は MERGE で WHEN NOT MATCHED のみ INSERT。再実行で既存 row は上書きしない。
--   手動編集後の再実行でも編集値は保護される。
--
-- 実行コマンド:
--   bq query --use_legacy_sql=false --project_id=monthly-pay-tax \
--     < infra/bigquery/migrations/2026-06-14_leader_team_monthly_budgets.sql
--
-- 事前確認 (R8: 本番 apply 前バックアップ):
--   bq query --use_legacy_sql=false \
--     "SELECT COUNT(*), SUM(budget_amount) \
--      FROM \`monthly-pay-tax.pay_reports.team_budgets_quarterly\` \
--      WHERE fiscal_year=2026"
--   → 件数・合計を記録しておき、apply 後の seed 値と突き合わせ
--
-- 事後検証 (R6: デプロイ skew 対応、PR merge 前に実施):
--   bq query --use_legacy_sql=false \
--     "SELECT COUNT(*), SUM(budget_amount) \
--      FROM \`monthly-pay-tax.pay_reports.leader_team_monthly_budgets\` \
--      WHERE fiscal_year=2026"
--   → 72 行 / 合計が quarterly 合計と一致することを確認 (3 ヶ月展開で同値)
--
-- ロールバック:
--   新規 table のため、問題時は DROP TABLE で removal:
--   bq rm -f -t monthly-pay-tax:pay_reports.leader_team_monthly_budgets
--   ※ PR #247 hotfix (team_budgets_quarterly ÷3) は dashboard コード側で
--     fall back ロジックを残しているため、テーブル不在でも UI は壊れない (defensive)
-- ============================================================

CREATE TABLE IF NOT EXISTS `monthly-pay-tax.pay_reports.leader_team_monthly_budgets` (
  fiscal_year     INT64    NOT NULL,
  month           INT64    NOT NULL,           -- 1-12
  leader_team     STRING   NOT NULL,
  budget_amount   NUMERIC  NOT NULL,
  version         INT64    NOT NULL DEFAULT 1,
  created_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP(),
  created_by      STRING   NOT NULL,
  updated_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP(),
  updated_by      STRING   NOT NULL
)
CLUSTER BY fiscal_year, leader_team;

-- ============================================================
-- 2026 seed MERGE (冪等)
-- ============================================================
-- fiscal_quarter UDF (infra/bigquery/views.sql) と整合:
--   Q1: 11, 12, 1 月 / Q2: 2, 3, 4 月 / Q3: 5, 6, 7 月 / Q4: 8, 9, 10 月
-- 端数: SAFE_DIVIDE → CAST(... AS NUMERIC) で円単位精度を保持、Python 側で int 化
-- (Codex R9 反映: SAFE_DIVIDE 端数は NUMERIC で保持、Python 側で int(round(...)) 統一)

MERGE `monthly-pay-tax.pay_reports.leader_team_monthly_budgets` T
USING (
  SELECT
    q.fiscal_year,
    m AS month,
    q.leader_team,
    CAST(SAFE_DIVIDE(SUM(q.budget_amount), 3) AS NUMERIC) AS budget_amount
  FROM `monthly-pay-tax.pay_reports.team_budgets_quarterly` q
  CROSS JOIN UNNEST(
    CASE q.fiscal_quarter
      WHEN 1 THEN [11, 12, 1]
      WHEN 2 THEN [2, 3, 4]
      WHEN 3 THEN [5, 6, 7]
      WHEN 4 THEN [8, 9, 10]
    END
  ) AS m
  WHERE q.fiscal_year = 2026
  GROUP BY q.fiscal_year, q.leader_team, m
) S
ON T.fiscal_year = S.fiscal_year
   AND T.month = S.month
   AND T.leader_team = S.leader_team
WHEN NOT MATCHED THEN INSERT (
  fiscal_year, month, leader_team, budget_amount,
  version, created_by, updated_by
) VALUES (
  S.fiscal_year, S.month, S.leader_team, S.budget_amount,
  1, 'migration@2026-06-14', 'migration@2026-06-14'
);
-- 注: WHEN MATCHED は意図的に省略 (再実行で既存値を上書きしない、冪等性確保)
