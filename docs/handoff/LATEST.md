# ハンドオフメモ - monthly-pay-tax

**更新日**: 2026-06-11 (Phase 2 完遂 + 実機 UX 改善 + race condition 緊急修正)
**フェーズ**: 予実管理機能 Phase 2 (PR-E + PR-F) **稼働開始** + **🆕 実機運用フェーズ突入** + **インシデント対応完了**
**最新デプロイ**: pay-dashboard PR #222 適用中 (Deploy Dashboard workflow 走行中)
**テストスイート**: Dashboard **437** + Cloud Run **226** + scripts **127** = **790 テスト全 PASS** (CI 自動実行)

## 2026-06-11 セッション完了サマリー (追加対応分)

前回 handoff (PR #218、Phase 2 完遂) 直後の本田様実機操作で UX 課題 + インシデントが判明。本セッションで対応完了。

| PR | 内容 | マージ | 備考 |
|----|------|--------|------|
| #219 | fix(dashboard): 予実階層設定の placeholder 例を変更 | 0604dab | 「シロロ+ゆずるん統括隊」→「ヤスス+ヒデデン統括隊」 |
| #220 | fix(dashboard): 未マッピング隊 selectbox を「隊」サフィックスでフィルタ | 7619ddc | dashboard 管理対象を「〜隊」14 件に限定、主要分類 18 件は CLI 管轄 |
| #221 | fix(dashboard): team_hierarchy 重複行による Streamlit duplicate key error 修正 | a50e553 | 緊急 UI 復旧 (drop_duplicates + widget key idx 化 + warning 表示) |
| #222 | fix(dashboard): race condition 予防策 (form 二重 submit ロック) | 795dd98 | 5 秒間の session_state ロックで再発防止 (UI レベル一次防御) |

### 実機インシデント詳細 (PR #221 / #222 の起源)

本田様が予実階層設定ページで UNMAPPED 補完を実機操作中:

1. **二重 INSERT 発生**: 連続クリック等で MERGE が race condition により同時実行され、`team_hierarchy` の「しっかり法人を経営し隊」が 2 秒差で重複 INSERT (09:34:46.925282 UTC / 09:34:48.681846 UTC)
2. **dashboard ロード時クラッシュ**: 重複行により `for _, row in df_view.iterrows()` で同じ widget key (`edit_leader_しっかり法人を経営し隊`) が複数 mount され `StreamlitDuplicateElementKey` で「予実階層設定」ページが落ちた
3. **本セッションで復旧**: PR #221 で UI 側 drop_duplicates + key idx 化 + 警告表示、本田様明示認可で BQ DELETE 1 件実行 (古い方の行を削除)、PR #222 で 5 秒 form ロック実装

### 本番データ修正実行 (本田様明示認可済)

| クエリ | 実行結果 |
|---|---|
| `DELETE FROM team_hierarchy WHERE activity_category='しっかり法人を経営し隊' AND UNIX_MICROS(updated_at)=1781170486925282` | 1 row deleted |
| `SELECT activity_category, COUNT(*) FROM team_hierarchy GROUP BY activity_category HAVING COUNT(*)>1` | 0 件 (重複ゼロ確認) |

---

## 環境状態

- **Git**: clean、main = `795dd98` (PR #222)
- **CI**: Test ✅ / Deploy Dashboard ⏳ in_progress (PR #222 由来、1m46s 経過)
- **OPEN PR**: 0 件 (handoff PR は本セッション末尾で作成予定)
- **OPEN Issues**: 3 件 (#94 / #58 / #54、すべて P2、本セッションで触っていない既存 backlog)
- **残留プロセス**: なし
- **グローバル memory 変更**: なし (scope チェック発動条件外)

---

## ドキュメント整合性

| 項目 | 状態 |
|---|---|
| CLAUDE.md ↔ dashboard ページ表 | ✅ PR #217 で「予実階層設定」を adminのみ で記載済、本セッションの変更は内部実装 (page 構成変わらず) |
| `dashboard/_pages/team_hierarchy_settings.py` ↔ コメント | ✅ 2026-06-11 インシデント経緯 + ADD_LOCK_KEY 設計理由を inline で記載 |
| 構造的整合性チェック | ⏭ 内部実装変更のみ、新規 BQ テーブル / API / フィールド追加なし |
| 運用 doc (`docs/operations/20260611_四半期予算投入手順.md`) | ✅ Phase 2 投入手順は PR-E で完成、UI 操作は不要 |

---

## Issue Net 変化

- **Close 数**: 0 件
- **起票数**: 0 件
- **Net**: ±0 件

本セッションは「ユーザーから明示指示された個別タスク」(CLAUDE.md GitHub Issues triage 基準 #5) で 4 PR + DELETE 1 件を完遂したため、Issue 起票なしが正しい運用。残課題 (PR-G 候補 3 件) は本 doc 「却下候補」で記録、別途 Issue 起票はしていない。

---

## 次のアクション

### 即着手タスク (0 件)

**executor 領分の即着手作業ゼロ**。

理由:
- 本セッションで PR #219〜#222 を完遂、本番 BQ の重複データ削除も完了
- 残課題は全て decision-maker (本田様) 判断待ち、または期日待ち
- 既存 OPEN Issues 3 件は本セッション関与なしの backlog (着手指示待ち)

### 条件待ち (2 件、明示 trigger 付き)

#### 1. 本田様による hierarchy 編集 + Q3 2026 予算投入 (PR-E + PR-F の本来の目的)

- **trigger**: 本田様の dashboard 画面操作 (PR-F 機能利用) + Q3 2026 予算 CSV 完成
- **trigger 充足時の作業**: 本田様自身が完了 (AI 関与なし)。完了後にダッシュボード `v_team_budget_actuals_quarterly` で予実比較を確認できる
- **confirm 方法**:
  ```sql
  -- 残 UNMAPPED 確認 (本田様作業進捗の目安)
  SELECT activity_category FROM `monthly-pay-tax.pay_reports.v_team_hierarchy_coverage`
  WHERE status = 'UNMAPPED' AND activity_category LIKE '%隊';

  -- Q3 2026 予実比較 (予算投入完了後)
  SELECT * FROM `monthly-pay-tax.pay_reports.v_team_budget_actuals_quarterly`
  WHERE fiscal_year = 2026 AND fiscal_quarter = 3 AND actual_mapping_status = 'mapped';
  ```
- **想定工数**: 本田様作業のみ。AI 工数 0 (問い合わせ対応のみ)
- **failure 時**: 本田様から問い合わせがあれば対応 (UNMAPPED 残 / typo / 集計ズレ / UI バグ等)

#### 2. 2026-07-01 07:00 JST: Cloud Scheduler 月次バッチ初回自動実行確認

- **trigger**: 期日到来 (3 週間後)
- **trigger 充足時の作業**: Chat スペースに評価バッチの完了通知 / BQ で SELECT COUNT(*) FROM team_monthly_eval WHERE generated_at >= '2026-07-01' を確認
- **confirm 方法**: 上記 SQL + Cloud Run ログ (gcloud logging read で /eval/team-monthly のリクエスト記録)
- **想定工数**: 確認 5 分、失敗時の原因特定は別途
- **failure 時**: Cloud Run revision + Vertex AI quota + IAM `roles/aiplatform.user` 付与状態を順に確認

### 却下候補 (PR-G 候補 + 既存 backlog、すべて明示指示待ち)

#### A. PR-G-1: BQ レベル根本対策 (staging table + single MERGE 化)

- **検討経緯**: Codex H1 (PR-E) と Codex H2 (PR-F) で繰り返し指摘。本セッションのインシデントで race condition が現実化し再認識
- **着手しない理由**: 横断 refactor (PR-A の upload_budgets.py / PR-E の upload_team_hierarchy.py + upload_team_budgets_quarterly.py / PR-F の insert_hierarchy_row 全てが同じパターン)。decision-maker の優先度判断必要
- **明示指示があった場合の参照先**: `scripts/upload_budgets.py` の MERGE_SQL_OPTIMISTIC、`scripts/upload_team_hierarchy.py`、`dashboard/lib/team_hierarchy_repo.py:insert_hierarchy_row`

#### B. PR-G-2: 二重 submit ロックを rename_leader_team / update_hierarchy_row にも適用

- **検討経緯**: PR #222 で `insert_hierarchy_row` 呼び出し箇所 (UNMAPPED 補完) のみロック実装。残る編集 / リネーム / 削除も race の可能性あり
- **着手しない理由**: update は optimistic lock があるため race による重複は起きない (lock 競合で affected=0 になる)。rename は単一 leader_team のリネームで重複は生まれない。delete は冪等。つまり、現状 race による現実的な実害は insert のみ
- **明示指示があった場合の参照先**: `dashboard/_pages/team_hierarchy_settings.py` の他の form section、`ADD_LOCK_KEY` パターンを `RENAME_LOCK_KEY` / `EDIT_LOCK_KEY` に拡張

#### C. PR-G-3: 削除時の actor 記録 (schema 拡張)

- **検討経緯**: PR-F Evaluator 指摘で既知の制約。`delete_hierarchy_row` で `updated_by` を残せず監査証跡なし
- **着手しない理由**: schema 拡張 (deleted_by 列追加) は decision-maker 領分、運用上 BQ ログで補完可能
- **明示指示があった場合の参照先**: `dashboard/lib/team_hierarchy_repo.py:delete_hierarchy_row`、`infra/bigquery/schema.sql:team_hierarchy`

#### D. 既存 OPEN Issues 3 件 (#94 / #58 / #54)

- **検討経緯**: P2 backlog、本セッション関与なし
- **着手しない理由**: 本田様の優先度判断待ち (4-12 で起票後 2 ヶ月放置中)
- **明示指示があった場合の参照先**: `gh issue view 94` 等

---

## 最終結論

✅ **セッション終了可** — 実機インシデント完全解消、本番データ修正完了、予防策デプロイ進行中、790 テスト全 PASS、Git clean、OPEN PR ゼロ、即着手タスク 0 件、条件待ち 2 件はすべて executor 領分外。

- OPEN PR: 0 件 (本 handoff 補強 PR を作成予定、認可後マージ)
- Git: docs/handoff-2026-06-11-pr-g-prep ブランチ
- 即着手タスク: **0 件** (executor 領分の作業ゼロ)
- 条件待ち: 2 件 (本田様の dashboard + CSV 作業 / 7/1 Scheduler 期日)
- 却下候補: PR-G 候補 3 件 + 既存 Issues 3 件 (すべて明示指示待ち)
- 残留プロセス: なし
- 既知 blocker: なし

**次セッション再開時のプロンプト案**:

```
catchup → docs/handoff/LATEST.md の「即着手 0 件、条件待ち 2 件」を確認
→ 本田様の明示指示があれば該当タスクに着手 (UNMAPPED 補完進捗 / Q3 2026 予算投入 / PR-G 候補 / 既存 Issues #94 #58 #54)
→ 指示なければセッション終了推奨 (idle skip プロトコル)
→ 実機インシデントの再発が報告された場合は PR #221 / #222 の経緯を参照
```
