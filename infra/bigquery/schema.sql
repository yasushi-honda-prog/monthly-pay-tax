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

-- タダメンMマスタ（メンバー情報、管理表 A:K 列）
CREATE TABLE IF NOT EXISTS `monthly-pay-tax.pay_reports.members` (
  report_url STRING NOT NULL,            -- 報告シートURL（gyomu/hojoのsource_urlと結合キー）
  member_id STRING,                      -- タダメンID
  nickname STRING,                       -- ニックネーム
  gws_account STRING,                    -- GWSアカウント
  full_name STRING,                      -- 本名
  qualification_allowance STRING,        -- 資格手当（現在空）
  position_rate STRING,                  -- 役職手当率（現在空）
  corporate_sheet STRING,                -- 法人シート（シート番号）
  donation_sheet STRING,                 -- 寄付先シート（シート番号）
  qualification_sheet STRING,            -- 資格手当加算先シート（シート番号）
  sheet_number STRING,                   -- シート番号（法人/寄付判定に使用）
  groups STRING,                         -- 所属Googleグループ（カンマ区切り, Admin Directory APIから取得）
  ingested_at TIMESTAMP NOT NULL         -- データ取得日時
);

-- 源泉対象リスト（源泉徴収対象の業務分類 + 士業メンバー）
CREATE TABLE IF NOT EXISTS `monthly-pay-tax.pay_reports.withholding_targets` (
  work_category STRING NOT NULL,         -- 源泉対象の業務分類
  licensed_member_id STRING              -- 士業さんのタダメンID（全額源泉対象）
);

-- ダッシュボードユーザー（ホワイトリスト + ロール管理）
CREATE TABLE IF NOT EXISTS `monthly-pay-tax.pay_reports.dashboard_users` (
  email STRING NOT NULL,                 -- GWSメールアドレス
  role STRING NOT NULL,                  -- "admin" | "checker" | "viewer"
  display_name STRING,                   -- 表示名
  added_by STRING NOT NULL,              -- 追加者メールアドレス
  source_group STRING,                   -- グループ由来の場合グループメール（NULLなら手動登録）
  created_at TIMESTAMP NOT NULL,         -- 作成日時
  updated_at TIMESTAMP NOT NULL          -- 更新日時
);

-- 業務チェック管理表（チェックステータス・メモ・操作ログ）
CREATE TABLE IF NOT EXISTS `monthly-pay-tax.pay_reports.check_logs` (
  source_url STRING NOT NULL,      -- メンバーの報告シートURL（members.report_url と結合）
  year INT64 NOT NULL,             -- 年
  month INT64 NOT NULL,            -- 月
  status STRING NOT NULL,          -- 未確認 | 確認中 | 確認完了 | 差戻し
  checker_email STRING NOT NULL,   -- チェック者メール
  memo STRING,                     -- メモ（自由記述）
  action_log STRING,               -- 操作ログ（JSON配列: [{"ts":"...","user":"...","action":"...","note":"..."}]）
  updated_at TIMESTAMP NOT NULL    -- 最終更新日時（楽観的ロック用）
);

-- グループマスター（Admin Directory APIから取得したGWSグループ一覧）
CREATE TABLE IF NOT EXISTS `monthly-pay-tax.pay_reports.groups_master` (
  group_email STRING NOT NULL,            -- グループメールアドレス
  group_name STRING,                      -- グループ表示名
  ingested_at TIMESTAMP NOT NULL          -- データ取得日時
);

-- グループ自動同期設定（dashboard_users のグループベース同期 ON/OFF 制御）
-- groups_master は毎日 WRITE_TRUNCATE されるため、設定を持てない → 別テーブルで保持
CREATE TABLE IF NOT EXISTS `monthly-pay-tax.pay_reports.dashboard_sync_groups` (
  group_email STRING NOT NULL,            -- 同期対象グループメール
  enabled BOOL NOT NULL,                  -- TRUE=自動同期実行 / FALSE=凍結（既存ユーザーは保持、追加・削除のみ停止）
  last_synced_at TIMESTAMP,               -- 最終同期反映時刻（バッチ成功時に更新）
  updated_at TIMESTAMP NOT NULL,          -- 設定最終更新日時
  updated_by STRING NOT NULL              -- 最終更新者メール（'migration' / admin email）
);
-- 初期 seed は infra/bigquery/migrations/2026-05-03_dashboard_sync_groups_seed.sql 参照

-- アプリ入力: 業務報告（Collector管理テーブルとは独立）
CREATE TABLE IF NOT EXISTS `monthly-pay-tax.pay_reports.app_gyomu_reports` (
  user_email STRING NOT NULL,              -- 入力者GWSメール
  date DATE NOT NULL,                      -- 業務日
  year INT64 NOT NULL,                     -- 年（dateから導出）
  month INT64 NOT NULL,                    -- 月（dateから導出）
  day_of_week STRING,                      -- 曜日（dateから導出）
  team STRING,                             -- 隊（チーム）
  activity_category STRING,                -- 活動分類
  work_category STRING,                    -- 業務分類
  sponsor STRING,                          -- スポンサー
  description STRING,                      -- 業務内容
  unit_price FLOAT64,                      -- 業務単価（円/h）
  hours FLOAT64,                           -- 所要時間（H）or 距離（km）
  amount FLOAT64,                          -- 金額
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP(),
  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP()
);

-- アプリ入力: 補助＆立替報告（Collector管理テーブルとは独立）
CREATE TABLE IF NOT EXISTS `monthly-pay-tax.pay_reports.app_hojo_reports` (
  user_email STRING NOT NULL,              -- 入力者GWSメール
  year INT64 NOT NULL,                     -- 年
  month INT64 NOT NULL,                    -- 月
  hours FLOAT64,                           -- 時間
  compensation FLOAT64,                    -- 報酬
  dx_subsidy FLOAT64,                      -- DX補助
  reimbursement FLOAT64,                   -- 立替
  total_amount FLOAT64,                    -- 総額
  monthly_complete BOOL DEFAULT FALSE,     -- 当月入力完了フラグ
  dx_receipt STRING,                       -- DX補助用 領収書メモ
  expense_receipt STRING,                  -- 個人立替用 領収書メモ
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP(),
  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP()
);

-- 立替金シート明細（Phase 1b: WAM助成金対応）
CREATE TABLE IF NOT EXISTS `monthly-pay-tax.pay_reports.reimbursement_items` (
  source_url STRING NOT NULL,
  nickname STRING,
  marker STRING,
  year STRING,
  date STRING,
  target_project STRING,
  category STRING,
  payment_purpose STRING,
  payment_amount STRING,
  advance_amount STRING,                  -- 仮払金額
  from_station STRING,                   -- 利用区間（発）
  to_station STRING,
  visit_purpose STRING,
  receipt_url STRING,
  ingested_at TIMESTAMP NOT NULL
);

-- タダメンMマスタ（タダメンMシートから全有用データを収集）
CREATE TABLE IF NOT EXISTS `monthly-pay-tax.pay_reports.member_master` (
  member_id STRING,
  last_name STRING,
  first_name STRING,
  last_name_kana STRING,
  first_name_kana STRING,
  nickname STRING,
  email STRING,
  postal_code STRING,
  prefecture STRING,
  address STRING,
  gws_account STRING,
  report_url_1 STRING,
  report_url_2 STRING,
  shipping_postal_code STRING,
  shipping_address STRING,
  qualification_allowance STRING,
  position_rate STRING,
  corporate_sheet STRING,
  donation_sheet STRING,
  qualification_sheet STRING,
  bank1_type STRING,
  bank1_name STRING,
  bank1_code STRING,
  bank1_branch_name STRING,
  bank1_branch_code STRING,
  bank1_account_number STRING,
  bank1_deposit_type STRING,
  bank1_holder_name STRING,
  bank2_type STRING,
  bank2_name STRING,
  bank2_code STRING,
  bank2_branch_name STRING,
  bank2_branch_code STRING,
  bank2_account_number STRING,
  bank2_deposit_type STRING,
  bank2_holder_name STRING,
  ingested_at TIMESTAMP NOT NULL
);

-- WAM対象PJマスタ（WAM判定ルール）
CREATE TABLE IF NOT EXISTS `monthly-pay-tax.pay_reports.wam_target_projects` (
  target_project STRING NOT NULL,
  wam_flag STRING NOT NULL,
  note STRING,
  ingested_at TIMESTAMP NOT NULL
);

-- GASバインディング（業務報告シート ↔ コンテナバインドGAS Script ID の紐付けメタデータ）
-- ローカル半手動巡回（scripts/collect_gas_bindings.py）が staging→MERGE で投入。
-- GASコード本体は保存しない（必要時に script_id から clasp clone）。読み取り専用。
-- 詳細・実行手順は infra/bigquery/migrations/2026-05-31_gas_bindings.sql 参照。
CREATE TABLE IF NOT EXISTS `monthly-pay-tax.pay_reports.gas_bindings` (
  spreadsheet_id STRING NOT NULL,  -- report_url から抽出したスプレッドシートID（MERGEキー）
  report_url     STRING NOT NULL,  -- 元の報告シートURL（members/member_master 結合キー）
  script_id      STRING,           -- コンテナバインドGASのScript ID（status=ok のみ非NULL）
  editor_url     STRING,           -- script.google.com エディタURL
  member_id      STRING,           -- タダメンID
  nickname       STRING,           -- ニックネーム
  url_source     STRING,           -- "url_1" | "url_2"
  status         STRING NOT NULL,  -- ok | no_gas | error | pending | unexpected_new_project
  error_type     STRING,           -- auth_required | permission_denied | ui_timeout | parse_error | unexpected_new_project
  error_detail   STRING,
  fetched_at     TIMESTAMP,        -- Script ID を取得した時刻
  ingested_at    TIMESTAMP NOT NULL -- BQ 書き込み時刻
);

-- 予実管理機能: 隊×月の予算データ。
-- optimistic lock (version) で並列更新制御。MERGE は WHERE t.version = expected_version 付き。
-- 入力経路: scripts/upload_budgets.py (CSV → BQ MERGE) または admin 画面 st.data_editor。
-- 詳細・実行手順: infra/bigquery/migrations/2026-06-10_team_budget_eval.sql / docs/specs/2026-06-10-team-budget-eval-design.md
CREATE TABLE IF NOT EXISTS `monthly-pay-tax.pay_reports.team_budgets` (
  year INT64 NOT NULL,                  -- 例: 2026
  month INT64 NOT NULL,                 -- 例: 5
  team STRING NOT NULL,                 -- gyomu_reports.activity_category と同一値
  budget_amount NUMERIC NOT NULL,
  memo STRING,
  version INT64 NOT NULL,               -- optimistic lock 用（初期値 1、UPDATE で +1）
  created_at TIMESTAMP NOT NULL,
  created_by STRING NOT NULL,
  updated_at TIMESTAMP NOT NULL,
  updated_by STRING NOT NULL
)
PARTITION BY DATE(updated_at)
CLUSTER BY year, month, team;

-- 予実管理機能: AI 評価キャッシュ。
-- (year, month, team) 単位で 1 行を保持 (history なし、UPSERT 方式)。
-- claim row パターンで並列実行制御（lock_token / lock_until / lock_actor）。
-- 入力経路: Cloud Run pay-collector POST /eval/team-monthly (Vertex AI Gemini 経由)。
CREATE TABLE IF NOT EXISTS `monthly-pay-tax.pay_reports.team_monthly_eval` (
  year INT64 NOT NULL,
  month INT64 NOT NULL,
  team STRING NOT NULL,
  actual_amount NUMERIC,
  budget_amount NUMERIC,
  achievement_rate FLOAT64,             -- actual/budget*100
  diff_amount NUMERIC,                  -- actual - budget
  actual_data_hash STRING,              -- TO_HEX(SHA256(...)) 差分検知用
  ai_comment STRING,                    -- Gemini 生成コメント 3-5 行
  ai_model STRING,                      -- 例: "gemini-2.5-flash"
  ai_prompt_tokens INT64,
  ai_output_tokens INT64,
  prompt_version STRING,                -- 例: "v1"
  sample_query_version STRING,          -- 例: "v1"
  location STRING,                      -- 例: "asia-northeast1"
  generation_config_json STRING,        -- {"max_tokens":350,"temperature":0.3,"top_p":0.8}
  generated_at TIMESTAMP,
  generated_by STRING,                  -- "scheduler" or email
  -- claim row パターン
  lock_token STRING,                    -- 処理中の job_id
  lock_until TIMESTAMP,                 -- claim 期限（CURRENT_TIMESTAMP() + 5 min）
  lock_actor STRING
)
-- 小規模テーブル（年間 24 隊 × 12 月 ≒ 288 行）のため CLUSTER のみで partition なし。
CLUSTER BY year, month, team;

-- 予実管理機能 PR-E: 支出カテゴリマスタ (7 行 seed)。
-- team_budgets_quarterly の expense_category typo 防止のため JOIN 検証必須。
-- 詳細: infra/bigquery/migrations/2026-06-11_quarterly_budgets.sql
CREATE TABLE IF NOT EXISTS `monthly-pay-tax.pay_reports.expense_categories` (
  sort INT64 NOT NULL,                    -- 表示順 (1-7)
  expense_category STRING NOT NULL,       -- 支出カテゴリ名 (PK)
  actual_source STRING NOT NULL,          -- 'gyomu' | 'reimbursement' | 'none'
  is_phase1_supported BOOL NOT NULL,      -- Phase 1 で実額紐付け済か
  note STRING
);

-- 予実管理機能 PR-E: activity_category (隊) ↔ leader_team (統括隊) 階層マッピング。
-- 案 T-NOW: 現在値のみ保持 (組織再編は schema migration で対応)。
-- 入力経路: scripts/upload_team_hierarchy.py
CREATE TABLE IF NOT EXISTS `monthly-pay-tax.pay_reports.team_hierarchy` (
  activity_category STRING NOT NULL,      -- gyomu_reports.activity_category と同一値 (PK)
  leader_team STRING NOT NULL,            -- 統括隊名
  leader_team_type STRING NOT NULL,       -- 'operating' | 'common'
  note STRING,
  version INT64 NOT NULL,                 -- optimistic lock 用
  created_at TIMESTAMP NOT NULL,
  created_by STRING NOT NULL,
  updated_at TIMESTAMP NOT NULL,
  updated_by STRING NOT NULL
)
PARTITION BY DATE(updated_at)
CLUSTER BY leader_team, activity_category;

-- 予実管理機能 PR-E: 四半期 × 統括隊 × 支出カテゴリの予算。
-- 既存 team_budgets (月別×隊) と並存。fiscal_year は 11 月始まり (案 N11)。
-- 入力経路: scripts/upload_team_budgets_quarterly.py
CREATE TABLE IF NOT EXISTS `monthly-pay-tax.pay_reports.team_budgets_quarterly` (
  fiscal_year INT64 NOT NULL,             -- 11 月始まり、Q1 開始月の翌暦年
  fiscal_quarter INT64 NOT NULL,          -- 1-4
  leader_team STRING NOT NULL,            -- team_hierarchy.leader_team と JOIN
  expense_category STRING NOT NULL,       -- expense_categories.expense_category と JOIN
  budget_amount NUMERIC NOT NULL,
  memo STRING,
  version INT64 NOT NULL,
  created_at TIMESTAMP NOT NULL,
  created_by STRING NOT NULL,
  updated_at TIMESTAMP NOT NULL,
  updated_by STRING NOT NULL
)
PARTITION BY DATE(updated_at)
CLUSTER BY fiscal_year, fiscal_quarter, leader_team;

-- シード: 初期管理者
-- INSERT INTO `monthly-pay-tax.pay_reports.dashboard_users`
--   (email, role, display_name, added_by, created_at, updated_at)
-- VALUES
--   ('yasushi-honda@tadakayo.jp', 'admin', 'Y.Honda', 'system', CURRENT_TIMESTAMP(), CURRENT_TIMESTAMP());
