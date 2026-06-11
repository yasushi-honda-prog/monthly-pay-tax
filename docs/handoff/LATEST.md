# ハンドオフメモ - monthly-pay-tax

**更新日**: 2026-06-11 (予実管理機能 Phase 2 完遂: PR-E BQ 基盤 + PR-F dashboard 編集 UI、本番 migration 適用済)
**フェーズ**: WAM助成金対応 **技術側完了** + **CI/CD 自動デプロイ稼働中** + **予実管理機能 Phase 1 (隊×月) 稼働中** + **🆕 予実管理機能 Phase 2 (四半期×統括隊×カテゴリ) BQ 基盤稼働開始** + **🆕 dashboard 予実階層設定ページ稼働開始**
**最新デプロイ**: pay-dashboard PR #217 適用中 (Deploy Dashboard workflow 走行中)
**テストスイート**: Dashboard **437** + Cloud Run **226** + scripts **127** = **790 テスト全 PASS** (CI 自動実行)

## 2026-06-11 セッション完了サマリー — Phase 2 (PR-E / PR-F) 完遂

PR-E (前セッション設計合意済) と本セッション着想の PR-F を 1 セッション内で完遂。

| PR | 内容 | マージ | 備考 |
|----|------|--------|------|
| #216 | feat(team-budget): PR-E 四半期×統括隊×カテゴリ予算 BQ 基盤 + 投入 script (Phase 2) | 7655f42 | 15 ファイル +2509 行、3 並列セカンドオピニオン → 必須修正 15 件反映、Evaluator APPROVE、本番 BQ migration 適用済 |
| #217 | feat(dashboard): PR-F 予実階層設定ページ (admin only、team_hierarchy 編集 UI) | 8e70b45 | 7 ファイル +1039 行、3 並列セカンドオピニオン → 必須修正 8 件反映、Evaluator 修正後 APPROVE (全 10 AC PASS) |

### 完成機能 (実装 + テスト pass + 本番反映)

#### PR-E (BQ 基盤 + CLI)

1. ✅ **UDF `fiscal_quarter(year, month)`** — 案 N11 (11月始まり、Q1=11-1月 / Q2=2-4月 / Q3=5-7月 / Q4=8-10月)。本番 BQ で 9 境界値検証 PASS
2. ✅ **`expense_categories` テーブル + 7 行 seed** — 画像と一致 (タダメン業務委託費 〜 共通費)。typo 防止のため JOIN 検証必須
3. ✅ **`team_hierarchy` テーブル** — 案 T-NOW で現在値のみ保持、optimistic lock
4. ✅ **`team_budgets_quarterly` テーブル** — 4 列 PK (fiscal_year, fiscal_quarter, leader_team, expense_category)、optimistic lock
5. ✅ **`v_team_budget_actuals_quarterly` VIEW** — 4 状態 `actual_mapping_status` (mapped / no_actual_rows / not_supported_in_phase1 / budget_missing)
6. ✅ **`v_team_hierarchy_coverage` VIEW** — MAPPED / UNMAPPED / UNUSED で差分検知。初期状態で UNMAPPED 32 件確認
7. ✅ **`scripts/upload_team_hierarchy.py`** — CSV → MERGE (optimistic lock)、`--check-coverage` で UNMAPPED warn
8. ✅ **`scripts/upload_team_budgets_quarterly.py`** — matrix / long CSV 両形式自動判別、`expense_categories` typo 検知、`--expected-total` 検算 (default abort + `--allow-total-mismatch`)、全角コンマ・空白除去、'計' '合計' '総計' '小計' 'total' 'sum' 'subtotal' 自動 skip
9. ✅ **snapshot 拡張** — `BQ_SNAPSHOT_TABLES` に新規 3 テーブル追加 (Step0 で 90 日 snapshot)

#### PR-F (dashboard 編集 UI)

10. ✅ **`_pages/team_hierarchy_settings.py` (admin only)** — 5 セクション構成: カバレッジサマリー / UNMAPPED 補完 (1-click 割当) / 統括隊リネーム (一括 UPDATE) / 編集 (optimistic lock) / 削除 (確認ダイアログ)
11. ✅ **`lib/team_hierarchy_repo.py`** — `insert_hierarchy_row` (force MERGE) / `update_hierarchy_row` (**UPDATE only、削除済み行への再 INSERT 防止**) / `rename_leader_team` / `delete_hierarchy_row` + fetch 3 種
12. ✅ **rename 成功時の警告** — `team_budgets_quarterly` は自動連動しないため、CSV 再投入が必要な旨を明示

### セカンドオピニオン履歴

| PR | Codex | code-reviewer | Evaluator | 必須修正反映 |
|---|---|---|---|---|
| #216 (PR-E) | High 2 + Medium 4 | High 3 + Medium 4 + Low 2 | APPROVE (Medium 1 + Low 2 + エッジ) | 15 件 (全角コンマ / Decimal NUMERIC / --expected-total abort / 集計行 skip / COUNTIF / matrix 列数超過 / check_coverage try-except / fiscal_quarter 13 境界値 / Partial Update assertion / 運用 doc 拡張 ほか) |
| #217 (PR-F) | High 2 + Medium 1 + Low 2 | High 1 + Medium 2 + Low 3 | 修正後 APPROVE (Low 1 + Medium 1 + エッジ) | 8 件 (insert/update 分離 / rename 警告 / dialog トップ移動 / lock 競合 st.error / SQL 共通化 / BQ 例外伝播 5 件テスト / 型注釈) |

### 本番インフラ反映

| 項目 | 値 | 実行日時 |
|---|---|---|
| **BQ migration 適用** | `bq query < infra/bigquery/migrations/2026-06-11_quarterly_budgets.sql` | 2026-06-11 16:18 JST |
| **新規 BQ オブジェクト 6** | UDF fiscal_quarter / 3 テーブル / 2 VIEW | 同上 |
| **expense_categories seed** | 7 行 INSERT | 同上 |
| **Cloud Run deploy** | pay-dashboard PR #217 (Deploy Dashboard 走行中) | 2026-06-11 自動 |

---

## 環境状態

- **Git**: clean、main = `8e70b45` (PR #217)、すべて origin と同期
- **CI**: Test ✅ success (59s) / Deploy Dashboard ⏳ in_progress (走行中)
- **OPEN PR**: 0 件
- **OPEN Issues**: 3 件 (#94 / #58 / #54、すべて P2、本セッションで触っていない既存 backlog)
- **残留プロセス**: なし
- **グローバル memory 変更**: なし (scope チェック発動条件外)

---

## ドキュメント整合性

| 項目 | 状態 |
|---|---|
| spec doc (`2026-06-11-team-budget-quarterly.md`) ↔ 実装 | ✅ 整合 (本 PR で新規作成) |
| CLAUDE.md ↔ 新規 BQ テーブル + UDF + VIEW + script + dashboard ページ | ✅ PR-E / PR-F で同期 |
| `infra/bigquery/schema.sql` / `views.sql` ↔ migration SQL | ✅ 反映済 |
| `cloud-run/config.py` ↔ snapshot 対象 | ✅ 新規 3 テーブル追加 |
| `dashboard/lib/constants.py` ↔ 新規ページ | ✅ TEAM_HIERARCHY_TABLE / TEAM_HIERARCHY_COVERAGE_VIEW / LEADER_TEAM_TYPES 追加 |
| `dashboard/app.py` ↔ navigation | ✅ admin_pages に「予実階層設定」追加 |
| 運用 doc (`20260611_四半期予算投入手順.md`) ↔ script CLI | ✅ 整合 (PR-E で新規作成、エッジケース + リカバリ手順含む) |
| 構造的整合性チェック | ⏭ 新規 BQ テーブル / 新規 dashboard ページを追加したが `/new-resource` 等は未実施。代わりに 3 並列セカンドオピニオン (Evaluator AC 検証含む) + 790 テスト全 PASS で補完済 |

---

## Issue Net 変化

- **Close 数**: 0 件
- **起票数**: 0 件
- **Net**: 0 件

本セッションは「ユーザーから明示指示された個別タスク」(CLAUDE.md GitHub Issues triage 基準 #5) で 2 PR を完遂したため、Issue 起票なしが正しい運用。残課題 (PR-G 候補 3 件) は PR-F 本文に明示して decision-maker 判断材料として残してあり、別途 Issue 起票はしていない。

---

## 次のアクション

### 即着手タスク (0 件)

**executor 領分の即着手作業ゼロ**。

理由:
- 本セッションで PR-E (BQ 基盤) + PR-F (dashboard 編集 UI) を完遂、本番 migration も適用済
- PR-E 残課題 (Q3 2026 予算投入) は decision-maker (本田様) による画面操作・CSV 作成が必要
- 既存 OPEN Issues 3 件は本セッション関与なしの既存 backlog (decision-maker からの着手指示待ち)

### 条件待ち (2 件、明示 trigger 付き)

#### 1. dashboard で UNMAPPED 32 件の統括隊割当 + Q3 2026 予算投入

- **trigger**: 本田様による dashboard 画面操作 (PR-F 機能利用) + Q3 2026 予算 CSV 完成
- **trigger 充足時の作業**: 本田様自身が完了 (AI 関与なし)。完了後にダッシュボード `v_team_budget_actuals_quarterly` で予実比較を確認できる
- **confirm 方法**:
  ```sql
  SELECT * FROM `monthly-pay-tax.pay_reports.v_team_hierarchy_coverage`
  WHERE status = 'UNMAPPED';  -- 0 件になれば全マッピング完了

  SELECT * FROM `monthly-pay-tax.pay_reports.v_team_budget_actuals_quarterly`
  WHERE fiscal_year = 2026 AND fiscal_quarter = 3 AND actual_mapping_status = 'mapped';
  ```
- **想定工数**: 本田様作業 (dashboard 操作 + CSV 作成)、AI 想定工数 0
- **失敗時の対応**: 本田様から問い合わせがあれば対応 (UNMAPPED 残り / typo / 集計ズレ等)

#### 2. 2026-07-01 07:00 JST: Cloud Scheduler 月次バッチ初回自動実行確認

- **trigger**: 期日到来 (3 週間後)
- **trigger 充足時の作業**: Chat スペースに評価バッチの完了通知 / BQ で SELECT COUNT(*) FROM team_monthly_eval WHERE generated_at >= '2026-07-01' を確認
- **confirm 方法**: 上記 SQL + Cloud Run ログ (gcloud logging read で /eval/team-monthly のリクエスト記録)
- **想定工数**: 確認 5 分、失敗時の原因特定は別途
- **failure 時の対応**: Cloud Run revision + Vertex AI quota + IAM `roles/aiplatform.user` 付与状態を順に確認

### 却下候補 (4 件、記録のみ)

#### 1. PR-G: 削除時の actor 記録 (schema 拡張)

- **検討経緯**: PR-F の Evaluator 指摘。`delete_hierarchy_row` に `updated_by` を残せず監査証跡なし
- **着手しない理由**: schema 拡張 (`team_hierarchy.deleted_by` 列追加) は decision-maker 領分、運用上 BQ ログで補完可能
- **明示指示があった場合の参照先**: `dashboard/lib/team_hierarchy_repo.py:delete_hierarchy_row`、schema migration SQL の追加

#### 2. PR-G: staging table + single MERGE 化 (PR-A 含む横断 refactor)

- **検討経緯**: Codex H2 指摘 (PR-E)。1 行ずつ MERGE のため部分失敗で整合性崩壊リスク
- **着手しない理由**: PR-A の `upload_budgets.py` も同パターンなので横断 refactor が必要、大規模変更
- **明示指示があった場合の参照先**: `scripts/upload_budgets.py` / `upload_team_hierarchy.py` / `upload_team_budgets_quarterly.py` の MERGE ロジック

#### 3. PR-G: `resolve_actor` / `merge_in_batches` の共通 helper 化

- **検討経緯**: code-reviewer M1 指摘 (PR-E、PR-F)。3 ファイル横断で同一パターン
- **着手しない理由**: 横断 refactor で PR-A も触る必要があり、ROI と影響範囲が要 decision-maker 判断
- **明示指示があった場合の参照先**: `scripts/bq_merge_utils.py` (新規) を作成、3 script から import

#### 4. PR-G: rename 後の team_budgets_quarterly 自動連動

- **検討経緯**: Codex H2 / Evaluator 指摘 (PR-F)。leader_team rename で予算側の leader_team が乖離
- **着手しない理由**: 本田様判断で「rename 時の連動は意図的に行わず、CSV 再投入運用」とした (PR-F 本文明記)
- **明示指示があった場合の参照先**: `dashboard/lib/team_hierarchy_repo.py:rename_leader_team` に `team_budgets_quarterly` 連動 UPDATE を追加

---

## 最終結論

✅ **セッション終了可** — Phase 2 (PR-E + PR-F) 完遂、本番 BQ migration 適用済、790 テスト全 PASS、Git clean、OPEN PR ゼロ、即着手タスク 0 件、条件待ち 2 件 (本田様作業 + 期日到来) はすべて executor 領分外。

- OPEN PR: 0 件 (本 handoff 補強 PR 作成予定、認可後マージ)
- Git: docs/handoff-2026-06-11-pr-ef ブランチ
- 即着手タスク: **0 件** (executor 領分の作業ゼロ)
- 条件待ち: 2 件 (本田様の dashboard 操作 + 7/1 Scheduler 期日)
- 却下候補: 4 件 (PR-G 候補、すべて明示指示待ち)
- 残留プロセス: なし
- 既知 blocker: なし

**次セッション再開時のプロンプト案**:

```
catchup → docs/handoff/LATEST.md の「即着手タスク = 0 件」を確認
→ 本田様から明示指示があれば該当タスクに着手 (Q3 2026 予算投入 / PR-G の 4 候補 / 既存 Issues #94 #58 #54)
→ 指示なければセッション終了推奨 (idle skip プロトコル)
```
