# ハンドオフメモ - monthly-pay-tax

**更新日**: 2026-06-12 (予実管理ページ 統括隊ベース再構成 + 第3Q仮予算投入完了)
**フェーズ**: 予実管理機能 Phase 2.5 (PR-A/B/Q2M 完了) + **第3Q仮予算データ投入済**
**最新デプロイ**: pay-dashboard PR #231 適用済 (revision `pay-dashboard-00315-lmc`)
**テストスイート**: Dashboard **461** + Cloud Run **227** + scripts **131** = **819 テスト全 PASS** (CI 自動実行)

## 2026-06-12 セッション完了サマリー

本セッションは大規模な予実管理ページ再構成を完遂。8 PR merge + BQ migration apply + 第3Q仮予算 42 行投入 + Playwright 実機検証完了。

### PR 一覧 (8 件すべて merged)

| PR | 内容 | マージ commit |
|----|------|--------------|
| #224 | hash SQL CTE 名 `rows`→`row_data` (BQ 予約語衝突修正) | 7290402 |
| #225 | `leader_team_type` UI selectbox 削除 (operating 固定運用) | 0314b4d |
| #226 | `leader_team_options` を df_hierarchy 派生 (cache drift 防止) | 5232304 |
| #227 | 追加 form の連続入力バグ修正 (disabled= 削除 + reset flag pattern) | d0a3458 |
| #228 | リネーム section に登録済み統括隊一覧 caption (UX 改善) | 08b49c2 |
| #229 | **PR-A**: BQ + lib 基盤整備 (VIEW 改訂 + 統括隊集計ヘルパー) | a46b430 |
| #230 | **PR-B**: Page UI 4 タブ再構成 (全体/統括隊/マトリクス/ドリルダウン) | 2fe3403 |
| #231 | **PR-Q2M**: 四半期予算→月予算表示 (統括隊レベル) | e8174db |

### BQ migration / データ投入実行

| 操作 | 結果 |
|---|---|
| `v_team_budget_actuals` VIEW 改訂 apply (PR-A) | ✅ INNER JOIN team_hierarchy + WHERE operating で非「隊」を根本除外、`leader_team` 列追加 |
| Post-migration 検証 | ✅ 28 行 / 14 隊 / 6 統括隊 (期待通り) |
| 第3Q (5-7月) 仮予算 42 行 INSERT (画像 #11 ベース) | ✅ team_budgets_quarterly に 6 統括隊 × 7 カテゴリ投入、合計 23,457,444 (タダカヨ合計と一致) |

### 投入した第3Q (5-7月) 仮予算 (月予算 = 四半期 / 3)

| 統括隊 | 四半期予算 | 月予算 |
|---|---|---|
| つくつく統括隊 | 11,029,721 | 3,676,574 |
| ゆずるん統括隊 (画像「シロロ＋ゆずるん」) | 5,289,363 | 1,763,121 |
| ヤスス＋ヒデデン統括隊 | 3,770,729 | 1,256,910 |
| ミヤヤ統括隊 | 1,931,187 | 643,729 |
| タケルン＋まこと統括隊 | 782,467 | 260,822 |
| ノブブ統括隊 | 653,977 | 217,992 |
| **合計** | **23,457,444** | **7,819,148** |

### Playwright 実機検証 (PR-B 後)

- ✅ 4 タブが正しく表示
- ✅ 非「隊」(その他/移動/電話対応/タダスク 等) 完全除外
- ✅ 統括隊タブで 6 統括隊 KPI 行表示
- ✅ 統括隊フィルタ dropdown に「全て」+ 6 統括隊 = 7 選択肢
- ✅ ページロード体感 < 5 秒

---

## 環境状態

- **Git**: `?? scripts/data/2026_q3_budgets.csv` (本 handoff で git に残す予定)
- **CI**: Test ✅ / Deploy Dashboard ✅ (PR #231 完了、revision `pay-dashboard-00315-lmc`)
- **OPEN PR**: 0 件 (本 handoff PR は末尾で作成)
- **OPEN Issues**: 3 件 (#94 / #58 / #54、すべて P2、前セッション同様 backlog)
- **残留プロセス**: 3 件検出 (すべて別プロジェクト `ACG/visitcare-shift-optimizer` の next dev + firebase emulators、本プロジェクト外)
- **グローバル memory 変更**: なし

---

## ドキュメント整合性

| 項目 | 状態 |
|---|---|
| CLAUDE.md ↔ dashboard ページ表 | ✅ PR-A で「ダッシュボード デプロイ後の cache 注意」セクション追加済、ページ構成変わらず |
| `docs/specs/2026-06-12-team-budget-leader-team-restructure.md` (新規 spec) | ✅ PR-A で作成、PR-B 実装と一致 |
| BQ 仕様 ↔ VIEW 実装 | ✅ migration / views.sql 同期済、team_budgets_quarterly に 42 行 |
| 構造的整合性チェック | ✅ load_leader_team_monthly_budgets / summarize_by_leader_team override は test カバー (新規 7 件) |

---

## Issue Net 変化

- **Close 数**: 0 件
- **起票数**: 0 件
- **Net**: ±0 件

本セッションは「ユーザーから明示指示された個別タスク」(本田様の予実管理ページ改修要望) と PR-Q2M 緊急対応で 8 PR を完遂したため、Issue 起票なしが正しい運用。既存 backlog Issues (#94 / #58 / #54) は本セッション関与なし。

---

## 次のアクション

### 即着手タスク (0 件)

**executor 領分の即着手作業ゼロ**。

理由:
- 本セッションで 8 PR 完遂 (#224〜#231) + BQ data 投入完了
- 残課題は全て decision-maker (本田様) 判断待ち、または期日待ち
- 既存 OPEN Issues 3 件は本セッション関与なしの backlog (着手指示待ち)

### 条件待ち (3 件、明示 trigger 付き)

#### 1. 本田様による実機での予実表示確認 (PR-Q2M + 第3Q予算投入の効果検証)

- **trigger**: 本田様の dashboard `team_budget` ページアクセス + Cmd+Shift+R ハードリロード
- **trigger 充足時の作業**: 本田様自身で視認。期待表示:
  - 📊 全体タブ: 全体予算 ¥7,819,148 / 達成率 (¥4,229,055 / ¥7,819,148 ≒ 54.1%) が表示
  - 🏢 統括隊タブ: 各統括隊行に上記月予算 + 達成率が表示
- **confirm 方法**:
  ```sql
  SELECT leader_team, SUM(budget_amount) AS quarter_total
  FROM `monthly-pay-tax.pay_reports.team_budgets_quarterly`
  WHERE fiscal_year = 2026 AND fiscal_quarter = 3
  GROUP BY leader_team ORDER BY quarter_total DESC;
  -- BQ には正常投入済、UI は cache 600s なので Cmd+Shift+R で即反映
  ```
- **想定工数**: 本田様作業のみ
- **failure 時**: 統括隊名の表記揺れ / Streamlit cache 問題等。AI 側は次セッションで状況を聞いて対応

#### 2. Q4 2026 (8-10月) 仮予算 CSV 投入 (継続運用)

- **trigger**: 本田様から Q4 (8-10月) 仮予算データ画像 / CSV 提供
- **trigger 充足時の作業**: 画像から CSV 抽出 → BQ INSERT (Q3 と同様の手順)。fiscal_year=2026, fiscal_quarter=4 (8月以降は FY2026 Q4)
- **confirm 方法**: 投入後 `SELECT * FROM team_budgets_quarterly WHERE fiscal_year=2026 AND fiscal_quarter=4`
- **想定工数**: CSV 作成 5 分 + 投入 + 検証 10 分
- **failure 時**: 統括隊名の不整合 / カテゴリ名の typo / 桁ずれ等を本田様確認のうえ修正

#### 3. 2026-07-01 07:00 JST: Cloud Scheduler 月次バッチ初回自動実行確認 (前 handoff から継続)

- **trigger**: 期日到来 (約 2 週間後)
- **trigger 充足時の作業**: Chat スペースに評価バッチの完了通知 / BQ で `SELECT COUNT(*) FROM team_monthly_eval WHERE generated_at >= '2026-07-01'` を確認
- **confirm 方法**: 上記 SQL + Cloud Run ログ (gcloud logging read で /eval/team-monthly のリクエスト記録)
- **想定工数**: 確認 5 分、失敗時の原因特定は別途
- **failure 時**: Cloud Run revision + Vertex AI quota + IAM `roles/aiplatform.user` 付与状態を順に確認

### 却下候補 (記録のみ、明示指示待ち)

#### A. 年累計ランキングの予算マーカー拡張 (Codex follow-up)

- **検討経緯**: PR-Q2M Codex review で「ランキングは累積予算と読めるが、現状 ¥0 マーカー」と指摘
- **着手しない理由**: 「年累計予算」をどう計算するか (現四半期のみ / 将来予測込み等) は decision-maker 判断必要。仕様未確定
- **明示指示があった場合の参照先**: `dashboard/_pages/team_budget.py:222-230` 付近 (`leader_ranking = summarize_by_leader_team(actuals_year)` の引数に annual budget dict を渡す)

#### B. マトリクスジャンプ → ドリルダウン UX 改善 (Codex follow-up)

- **検討経緯**: PR-B Codex review で「マトリクスから選んだ隊が、ドリルダウン側で別統括隊フィルタのままだと先頭隊にフォールバックする stale UX」と指摘
- **着手しない理由**: UX の改善方針が複数考えられる (filter リセット / 自動フォーカス / 別ページ遷移)、decision-maker 判断必要
- **明示指示があった場合の参照先**: `dashboard/_pages/team_budget.py` の `tb_matrix_jump_team` セッション state 周辺

#### C. 月次推移グラフの欠損月表示方針 (Codex follow-up)

- **検討経緯**: PR-B Codex review で「データがない月は軸から消える」と指摘
- **着手しない理由**: 「1-12 月を常に表示」が仕様なら `reindex(range(1, 13), fill_value=0)` が必要だが、現状の「データがある月の推移」が仕様の可能性もあり、決定者領分
- **明示指示があった場合の参照先**: `dashboard/_pages/team_budget.py` の tab_overall `monthly_trend` 集計

#### D. `summarize_by_leader_team` の `diff_amount` セマンティクス決定 (Codex follow-up)

- **検討経緯**: PR-A Codex review で「actual-only 隊 (予算 0 だが実額あり) の扱いを spec で明文化すべき」と指摘
- **着手しない理由**: ビジネスルールの解釈問題、decision-maker 判断必要
- **明示指示があった場合の参照先**: `dashboard/lib/team_budget_view.py:summarize_by_leader_team`

#### E. AI 評価 (vertex_evaluator) の統括隊レベル拡張 (将来 phase)

- **検討経緯**: 現状 AI 評価は隊×月のみ、本田様要望次第で統括隊レベル評価も追加可能
- **着手しない理由**: プロンプト設計 + cloud-run 修正 + コスト試算が必要、別 phase
- **明示指示があった場合の参照先**: `cloud-run/vertex_evaluator.py` / `cloud-run/team_eval_service.py`

#### F. 統括隊名のリネーム (シロロ＋ゆずるん統括隊 への改名)

- **検討経緯**: 画像 #11 では「シロロ＋ゆずるん統括隊」だが BQ 投入時は「ゆずるん統括隊」(team_hierarchy の現状名)
- **着手しない理由**: 改名するかどうかは本田様判断。改名する場合は dashboard `team_hierarchy_settings` ページのリネーム機能で実施可
- **明示指示があった場合の参照先**: dashboard `/team_hierarchy_settings` ページのリネーム section

#### G. 既存 OPEN Issues 3 件 (#94 / #58 / #54)

- **検討経緯**: P2 backlog、本セッション関与なし
- **着手しない理由**: 本田様の優先度判断待ち (2 ヶ月前起票後放置中)
- **明示指示があった場合の参照先**: `gh issue view 94` 等

---

## 残留プロセス

3 件検出 (すべて別プロジェクト):
- `node /Users/yyyhhh/Projects/ACG/visitcare-shift-optimizer/web/node_modules/.bin/next dev`
- `firebase emulators:start --project demo-visitcare ...`
- `java ... cloud-firestore-emulator ...` (firebase emulator 子プロセス)

**本プロジェクト (monthly-pay-tax) のプロセスはなし**。別プロジェクトの開発を中断するなら `~/.claude/scripts/cleanup-node.sh --kill` で停止可。

---

## 最終結論

✅ **セッション終了可** — 8 PR 全 merge、BQ migration apply 完了、第3Q仮予算 42 行投入完了、Playwright 実機検証 PASS、819 テスト全 PASS、Git clean (CSV は本 handoff PR でコミット予定)、OPEN PR ゼロ、即着手タスク 0 件、条件待ち 3 件はすべて executor 領分外。

- OPEN PR: 0 件 (本 handoff PR を末尾で作成)
- Git: docs/handoff-2026-06-12-pr-q2m ブランチ + `scripts/data/2026_q3_budgets.csv` untracked
- 即着手タスク: **0 件** (executor 領分の作業ゼロ)
- 条件待ち: 3 件 (本田様の実機確認 / Q4 予算投入 / 7/1 Scheduler 期日)
- 却下候補: PR-Q2M follow-up 4 件 + AI 評価拡張 + 統括隊名リネーム + 既存 Issues 3 件 (すべて明示指示待ち)
- 残留プロセス: 別プロジェクトのみ (本プロジェクト外)
- 既知 blocker: なし

**次セッション再開時のプロンプト案**:

```
catchup → docs/handoff/LATEST.md の「即着手 0 件、条件待ち 3 件」を確認
→ 本田様の明示指示があれば該当タスクに着手 (実機確認結果報告 / Q4 予算 / PR-Q2M follow-up / 既存 Issues #94 #58 #54)
→ 指示なければセッション終了推奨 (idle skip プロトコル)
→ 統括隊名リネーム指示があれば dashboard の team_hierarchy_settings リネーム機能で対応
```
