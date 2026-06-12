# 予実管理ページ 統括隊ベース再構成 設計仕様書

**作成日**: 2026-06-12
**前提**: PR-A〜D (隊×月予実、`docs/specs/2026-06-10-team-budget-eval-design.md`) と PR-E/F (統括隊階層 + 階層編集 UI、`docs/specs/2026-06-11-team-budget-quarterly.md`) を基盤とする
**ステータス**: 本田様承認待ち

---

## 1. 背景

PR-F で `team_hierarchy` テーブルの populate が完了 (14 隊 → 6 統括隊にマッピング済) したことで、予実管理ページ (`dashboard/_pages/team_budget.py`) の段階的ドリルダウン UI が実現可能になった。

### 1.1 現状の課題

実機での本田様報告 (2026-06-12 セッション):

1. **隊以外の活動分類が混入**: 「隊別累積実額ランキング」グラフに「その他」「移動」「電話対応」「神奈川県事業」等が表示される
2. **統括隊との紐付けがない**: 統括隊ごとの集約ビューがなく、隊単位の細かい表示しかない
3. **隊サフィックスのフィルタ未実装**: ドリルダウンタブの隊 selectbox にも非「隊」が含まれる

### 1.2 求められる UX

本田様の理想像「**隊全体と統括隊として、と隊それぞれの段階的な見方**」を実現する:

1. **全体**: 法人全体の予実 KPI + 月次推移
2. **統括隊**: 6 統括隊それぞれの KPI、ランキング、配下隊一覧
3. **隊マトリクス**: 隊×月の達成率マトリクス
4. **隊ドリルダウン**: 個別隊の詳細 + AI 評価コメント

---

## 2. 確定済み設計判断 (2026-06-12 セッション)

| 論点 | 採択案 | 根拠 |
|---|---|---|
| 非「隊」活動分類の扱い | **UI から完全除外** | 主要分類 (その他/移動/電話対応) は `team_hierarchy` 管理対象外、運用方針と一致 |
| UI 構造 | **新規 4 タブ**: 全体 / 統括隊 / 隊マトリクス / 隊ドリルダウン | 段階的ドリルダウンが最も直感的 |
| AI 評価コメント | **現状維持** (隊×月のみ、ドリルダウンで表示) | 統括隊レベル AI 評価はプロンプト設計 + cloud-run 修正が必要、別 PR |
| フィルタ位置 | **VIEW 層で根本除外** (UI 層フィルタは持たない) | Codex セカンドオピニオン: UI 二重フィルタは漏れの原因 |
| 既存非隊評価レコード | **削除せず UI で非表示** | `team_monthly_eval` の既存行は残置、新規生成のみ隊限定 |

---

## 3. BQ VIEW 改訂

### 3.1 v_team_budget_actuals (改訂版)

**変更点**: `team_hierarchy` を INNER JOIN し `leader_team_type='operating'` でフィルタ。`leader_team` 列を追加。

```sql
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
  h.leader_team,                                                    -- ★新規列
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
INNER JOIN `monthly-pay-tax.pay_reports.team_hierarchy` h        -- ★INNER JOIN で非隊除外
  ON c.team = h.activity_category
WHERE h.leader_team_type = 'operating';                           -- ★common の virtual 統括隊も除外
```

### 3.2 設計の根拠

- **INNER JOIN**: `LEFT JOIN` だと `leader_team IS NULL` の行 (非隊) が残り、UI 側で除外する必要がある。Codex 指摘の通り、UI 二重フィルタは漏れの原因なので VIEW で根本除外。
- **`leader_team_type='operating'` フィルタ**: 四半期 VIEW (`v_team_budget_actuals_quarterly`) と同じ思想で、'common' (共通枠 virtual 統括隊) も除外。現状 PR-G の方針で UI は operating 固定運用 (PR #225)。
- **`COALESCE` 後に hierarchy JOIN**: 予算 only 行 (team_budgets にあるが gyomu_reports に出ない隊) も hierarchy 経由で除外される。team_budgets に非隊を投入してしまった場合のフェールセーフ。

### 3.3 影響範囲

#### 3.3.1 直接的な影響
- `dashboard/lib/bq_client.py:load_team_budget_actuals()` の戻り列に `leader_team` が追加される
- `dashboard/lib/bq_client.py:load_active_teams()` の結果から非隊が除外される
- `dashboard/_pages/team_budget.py` の全タブで非隊が表示されなくなる

#### 3.3.2 間接的な影響 (Cloud Run 側)
- `cloud-run/team_eval_service.list_active_teams()` は `v_team_budget_actuals` を参照 → 自動評価対象が「team_hierarchy 登録済み operating 隊」のみに自動で絞られる
- **これは要件と合致**: 月次バッチ AI 評価の対象が隊に限定される

#### 3.3.3 影響しないもの
- `cloud-run/vertex_evaluator.compute_actual_data_hash()` の hash 計算 SQL は `gyomu_reports` を `activity_category=@team` で直読するため不変
- 既に生成済みの `team_monthly_eval` 非隊レコード: 削除しない、UI で非表示にする運用方針

---

## 4. UI 改訂

### 4.1 4 タブ構造

| タブ | 内容 | 主な要素 |
|---|---|---|
| 📊 全体 | 法人全体の予実 KPI + 月次推移 | 全体 KPI (予算/実額/達成率) + 月次推移グラフ |
| 🏢 統括隊 | 統括隊別 KPI + ヒートマップ + ランキング | 統括隊一覧 + 統括隊×月達成率ヒートマップ + 統括隊別累積実額ランキング |
| 🏷️ 隊マトリクス | 隊×月の達成率マトリクス | 統括隊フィルタ + 隊×月マトリクス |
| 🔍 隊ドリルダウン | 1 隊の KPI + AI 評価コメント + 業務報告詳細 | 統括隊フィルタ + 隊 selectbox + KPI + AI コメント |

### 4.2 各タブの詳細

#### 📊 全体タブ
- `summarize_actuals(actuals_year)` で法人全体 KPI を集計
- 月次推移: 全隊集計の line/bar chart

#### 🏢 統括隊タブ
- `summarize_by_leader_team(actuals_year)` で統括隊別に集計
- 統括隊×月の達成率ヒートマップ (既存の隊×月ヒートマップを統括隊版に転用)
- 統括隊別累積実額ランキング (棒グラフ + 予算マーカー)

#### 🏷️ 隊マトリクスタブ
- 「統括隊で絞り込み」selectbox を追加 (デフォルト「全て」)
- 既存の隊×月マトリクスを統括隊フィルタで絞り込み

#### 🔍 隊ドリルダウンタブ
- 「統括隊で絞り込み」selectbox を追加 (デフォルト「全て」)
- 統括隊フィルタで絞り込まれた隊 selectbox
- 1 隊の KPI + AI 評価コメント (既存)

### 4.3 lib/team_budget_view.py の新規ヘルパー

```python
def summarize_by_leader_team(actuals_df: pd.DataFrame) -> pd.DataFrame:
    """統括隊別の KPI 集計 (leader_team 列必須)。

    Returns:
        columns: leader_team, actual_amount, budget_amount,
                 achievement_rate, diff_amount, team_count
    """
    ...

def build_leader_team_matrix_df(
    actuals_df: pd.DataFrame, value: str = "achievement_rate"
) -> pd.DataFrame:
    """統括隊×月のマトリクス DataFrame を構築。"""
    ...
```

---

## 5. スクリプト改修

### 5.1 scripts/upload_budgets.py に hierarchy validation 追加

Codex 指摘: 「CSV upload で team_hierarchy に存在しない `team` を投入できてしまう」リスク対策。

```python
def validate_hierarchy_coverage(client, df):
    """team_budgets CSV の team が team_hierarchy に存在するか確認。

    存在しない team があれば warning (失敗にはしない、運用判断)。
    --strict フラグで失敗にする選択肢を提供。
    """
    ...
```

`--strict` フラグなしの場合は warning のみ。`--strict` 付きの場合は exit 1。

---

## 6. デプロイ手順 (Cache 対策)

Codex 指摘: Streamlit cache TTL (300s / 600s) により migration 直後 10 分間古い分類が残る。

**手順 (順序厳守)**:
1. **BQ migration apply** (PR-A merge **前** に実施): `bq query --use_legacy_sql=false --project_id=monthly-pay-tax < infra/bigquery/migrations/2026-06-12_team_budget_leader_team.sql`
   - これより前に PR-A を merge してアプリがデプロイされると、`load_team_budget_actuals` が SELECT する `leader_team` 列が VIEW に存在せず BQ クエリエラーになる
2. migration apply 後に PR-A を merge → Deploy Dashboard 自動起動
3. デプロイ後、Cloud Run revision が新しく start するので in-process cache は自動で空になる
4. **ただし**: 既存 instance が serve 中の WebSocket セッションは古い cache を持つ可能性あり → 利用者は Cmd+Shift+R が必要

**Evaluator 指摘 (2026-06-12)**: CI/CD のフローで migration → deploy 順序を強制する仕組みはないため、本 PR レビュー時に手順遵守を確認すること。

**Runbook 更新**: CLAUDE.md の「ダッシュボード デプロイ前チェック」に追記。

---

## 7. テスト計画

### 7.1 BQ 層 (manual verification)
- `SELECT * FROM v_team_budget_actuals LIMIT 5` で `leader_team` 列が含まれることを確認
- `SELECT DISTINCT team FROM v_team_budget_actuals` で非隊が含まれないことを確認
- `SELECT COUNT(DISTINCT leader_team) FROM v_team_budget_actuals` で operating 統括隊数 (現状 6) と一致

### 7.2 dashboard 層 (unit tests)
- `test_lib_bq_client_team_budget.py`: load_team_budget_actuals の戻り列に leader_team 含まれる
- `test_lib_bq_client_team_budget.py`: load_active_teams が hierarchy 由来でフィルタされる
- `test_team_budget_view.py` (新規 or 拡張): summarize_by_leader_team / build_leader_team_matrix_df の集計ロジック
- `test_pages_team_budget.py`: 4 タブ smoke test (admin/user ロール、空データ、エラー時)

### 7.3 cloud-run 層
- `test_team_eval_endpoint.py`: list_active_teams が 隊のみ返すこと (mock VIEW)

---

## 8. Acceptance Criteria

| # | 基準 | 検証方法 |
|---|---|---|
| AC1 | 全タブで非「隊」活動分類が表示されない | unit test + 実機確認 |
| AC2 | 統括隊タブで `leader_team_type='operating'` の distinct = 6 件、各 KPI 行が出る | unit test (固定 fixture) + 実機確認 |
| AC3 | 隊マトリクス・ドリルダウンに「統括隊で絞り込み」selectbox がある | 実機確認 |
| AC4 | `v_team_budget_actuals` に `leader_team` 列が追加される | `bq query` で SELECT 確認 |
| AC5 | team_hierarchy 空時に適切な info 表示 | unit test (空 DataFrame mock) |
| AC6 | ページロード < 5 秒 | 実機計測 (体感ベースライン) |
| AC7 | team_hierarchy にない隊が gyomu に出現 → どこにも表示されない | unit test + 実機確認 (新規 unmapped 隊で再現) |
| AC8 | `load_team_budget_actuals` の戻り DataFrame に `leader_team` 列が含まれる | unit test |
| AC9 | デプロイ runbook に cache clear / hard refresh 手順が記載される | CLAUDE.md 更新確認 |
| AC10 | `upload_budgets.py` に hierarchy coverage validation がある | unit test + dry-run 確認 |

---

## 9. 段階的実装 (2 PR 構成)

### PR-A: BQ + lib 基盤整備
- A1: 本 spec doc 確定
- A2: VIEW 改訂 (migration SQL + views.sql 同期)
- A3: `load_team_budget_actuals` 戻り列に leader_team 追加
- A4: `load_active_teams` を hierarchy JOIN ベースに変更
- A5: `team_budget_view.py` に統括隊集計ヘルパー追加
- A6: unit tests 更新
- A7: `upload_budgets.py` に hierarchy validation 追加
- A8: CLAUDE.md デプロイ runbook 更新 (cache clear 手順)
- A9: BQ 本番 migration apply

### PR-B: Page UI 4 タブ再構成
- B1: tab_overall (全体サマリー)
- B2: tab_leader (統括隊別)
- B3: tab_team_matrix (既存 + 統括隊フィルタ)
- B4: tab_drilldown (既存 + 統括隊フィルタ)
- B5: page tests 更新
- B6: 実機動作確認 (本田様確認)

---

## 10. 既存非隊評価レコードの運用方針

`team_monthly_eval` テーブルには PR-A 以前に生成された「その他」「移動」等の非隊評価レコードが残る可能性がある。

**方針**:
- **削除しない**: 既存データは historical archive として保持
- **UI で非表示**: VIEW フィルタにより自動的に表示されなくなる (`v_team_budget_actuals` の INNER JOIN で非隊が消えるため、ドリルダウンで該当評価を引くこと自体ができない)
- **次月以降の自動評価**: `team_eval_service.list_active_teams()` も VIEW 経由なので、隊のみが対象になる

**将来検討**: 必要に応じて手動 DELETE で cleanup 可。本 PR では touch しない。

---

## 11. ロールバック手順

万一の問題発生時:

1. **VIEW のみロールバック**: migration の old definition を再 apply (新 migration の前に backup を取得しておく)
2. **Cloud Run dashboard**: `gcloud run services update-traffic` で直前 revision に戻す
3. **`team_hierarchy` データ**: 触らない (PR-F で populate 済み、本 PR では参照のみ)

---

## 12. 関連 PR

- PR #209-#213: 予実管理 PR-A〜D (隊×月)
- PR #214-#218: 予実管理 PR-E/F (四半期×統括隊×カテゴリ + 階層編集 UI)
- PR #222-#227: 2026-06-11/12 セッションのバグ修正
- 本 PR: 統括隊ベース再構成 (PR-A: 基盤 / PR-B: UI)
