# ハンドオフメモ - monthly-pay-tax

**更新日**: 2026-06-14 (Issue #248 PR #250 作成完了、本田様 merge/migration 判断待ち)
**フェーズ**: 予実管理機能 Phase 4 (統括隊×月予算 UI 完成、本番反映待ち)
**最新デプロイ**: pay-dashboard PR #247 反映済 (hotfix 暫定状態) / pay-collector PR #246 反映済
**テストスイート**: Dashboard **628** + Cloud Run **276** + scripts **152** = **1056 件 全 PASS**

## 2026-06-14 セッション完了サマリー (Issue #248 完成 → PR #250 作成)

本日 1 セッションで Issue #248 「[予実管理] 統括隊×月予算 UI 追加 - 月次推移グラフの月別予算反映」の brainstorm Phase 1-5 → 設計確定 → impl-plan → 実装 → QG 4 段 → PR 作成までを完走。Codex セカンドオピニオン 4 巡で最終マージ可判定。残作業は本田様の番号単位明示認可 + 本番 migration apply + マージ + 実機検証。

### 1. brainstorm Phase 1-5 (`/brainstorm` skill)

handoff 教訓 #1「全タブ × データソース マトリクス先行確定」を反映し、Phase 3 質問 5 件で核心確定:

| 確定事項 | 内容 |
|---|---|
| データソース統一 | 全体タブ・統括隊タブとも新規 leader_team_monthly_budgets 参照 (隊マトリクス/ドリルダウンは team_budgets 継続) |
| 初期投入 | migration apply 時に fiscal_year=2026 を quarterly÷3 で seed |
| 年軸 | fiscal_year + month (会計年度 11 月始まり、views.sql `fiscal_quarter` UDF 準拠) |
| UI 配置 | 新規 page `leader_budget_input.py` (admin 専用 6×12 grid) |
| quarterly | そのまま残す (カテゴリ別予算用途で継続) |
| Phase 4 案 | B 案 (seed 自動 + 警告 + 差分 tooltip) |

設計仕様書: `docs/specs/2026-06-14-leader-team-monthly-budget.md` (626 行、AC14 件、commit 47afc53 → a01641c で Codex 反映済)

### 2. Codex セカンドオピニオン 4 巡

| 巡 | タイミング | 評価 | 主要指摘 | 反映状況 |
|---|---|---|---|---|
| 1 | 設計時 | 中規模修正必要 | fiscal_calendar 追加 / migration 冪等性 / cache 影響先列挙 等 | High 2 / Medium 5 / Low 3 全反映 |
| 2 | impl-plan 時 | 軽微修正で可 | T8 を Round 2 に / Round 3 順序 / デプロイ skew | Medium 5 / Low 3 全反映 |
| 3 | QG Stage 4 | 軽微修正で可 | C-M1 (preview FY 紐付け) / C-M2 (グラフ FY 順) / AC9 spec | 本 PR で C-M1 + C-M2 + AC9 修正 |
| 4 | 完成形 | **マージ可** | 該当なし | (なし) |

### 3. impl-plan + 実装 (T1-T12)

12 タスクを 4 Round で逐次実装 (想定 7-10 時間 → 実工数約 5.5 時間):

| Round | タスク | 規模 | テスト増分 |
|---|---|---|---|
| Round 1 | T1 fiscal_calendar / T2 migration / T3 constants | 小・中・小 | +19 / +21 / 0 |
| Round 2 | T4 bq_client / T8 team_budget.py | 中・中 | +25 / +3 |
| Round 3 | T5a-c repo / T6 cache / T9 view / T7 page / T10 navigation | 大・小・小・大・小 | +30 / +6 / +5 / +12 / 0 |
| Round 4 | T11 QG 4 段 / T12 PR 作成 | 大・中 | +4 (QG 修正含む) |

#### 重要な実装判断 (R7 PR #246 編集回帰対応)

設計書 §5.4 では「team_budget.py の selector を fiscal_year selector に切替」と明記していたが、Codex R7 指摘「team_budgets.year=暦年想定の編集ロジックが壊れる」リスクを最小化するため、**selector は暦年維持 + 内部で calendar_to_fiscal(year, month) で fiscal_year 導出**に変更。本田様承認済 (Round 2 完了報告時)。

UI 表示は subheader を `FY{fiscal_year}` に変更、load_* 関数呼び出しを fiscal_year 経由に。AC13 (11/12 月境界年度ズレ無し) は 3 件の追加テストで検証済。

### 4. Quality Gate 4 段

| Stage | 内容 | 結果 |
|---|---|---|
| 1 safe-refactor | MEDIUM 2 件修正 | frozen 再生成 → mutable 集計 / 未使用 import 3 件削除 |
| 2 code-review high | CONFIRMED 2 件修正 | CAST AS INT64 → CAST(ROUND(...) AS INT64) (truncate 防止、Codex R9 反映) |
| 3 Evaluator 分離 | AC14 件評価 | PASS 12 / UNTESTABLE 2 (BQ emulator なし、AC1+AC12 は本番 apply 時実機検証) |
| 4 Codex final | 軽微修正で可 | C-M1 (preview FY 紐付け) + C-M2 (グラフ FY 順) + AC9 spec 修正を本 PR で対応 |

QG 中の追加修正:
- C-M1: `_lbi_preview` を `{fiscal_year, preview}` 構造で保存、年度切替時に破棄
- C-M2: `build_monthly_trend` に fiscal_month_order 列追加、altair の `alt.SortField` で 11→10 順固定
- AC9 spec: 「影響先 5 cache 関数」→「影響先 6 cache 関数」(`cached_load_active_leader_teams_for_input` 明示列挙)

### 5. PR #250 作成完了

| 項目 | 値 |
|---|---|
| URL | https://github.com/yasushi-honda-prog/monthly-pay-tax/pull/250 |
| Title | feat(team-budget): 統括隊×月予算入力 UI + 月次推移グラフ恒久対応 (Issue #248) |
| Branch | feature/leader-team-monthly-budget-design → main |
| Diff | +3442 / -111 (19 files、commit 3 件: 47afc53 設計初版 + a01641c Codex 反映 + efd6c2a 実装) |
| Mergeable | MERGEABLE |
| 規模 tier | large (hook が review required を要求) |
| Status | **本田様 review + 番号単位明示認可待ち** |

---

## 環境状態

- **Git**: docs/handoff-2026-06-14 ブランチで本 handoff PR 作成準備中
- **CI**: 未確認 (PR #250 の CI は GitHub 側で実行待ち)
- **本番デプロイ**: PR #247 hotfix が稼働中、PR #250 のデプロイは本田様判断待ち
- **OPEN PR**: 1 件 (#250、本 handoff PR を末尾で作成)
- **OPEN Issues**: 4 件 (#248 は PR #250 で close 予定 / #245 postponed / #94/#58/#54 P2 backlog)
- **残留プロセス**: 本プロジェクト関連なし
- **グローバル memory 変更**: なし

---

## ドキュメント整合性

| 項目 | 状態 |
|---|---|
| CLAUDE.md ↔ 新規 BQ table | ⚠ 未更新 (CLAUDE.md L98 のテーブル一覧に leader_team_monthly_budgets 追加が必要、PR #250 merge 後の follow-up) |
| `docs/specs/2026-06-14-*.md` | ✅ AC9 文言訂正済 (改訂版 commit a01641c) |
| BQ schema / dashboard 実装 ↔ tests | ✅ 1056 件 PASS で機械的に保証 |
| handoff LATEST.md | ✅ 本 PR で全面更新 |

---

## Issue Net 変化

- **Close 予定**: 1 件 (#248、PR #250 merge 後)
- **起票数**: 0 件 (follow-up 9 件は PR description に記載、Issue 起票は本田様明示指示時のみ)
- **Net**: -1 件 (close 予定が起票を上回り、進捗あり)

---

## 次のアクション

### 即着手タスク

**executor 領分の即着手作業ゼロ**。

理由:
- PR #250 で本日 Issue #248 完成、QG 4 段全完了、Codex 4 巡最終マージ可判定
- 残課題は全て decision-maker (本田様) 領分: ① PR review ② 本番 migration apply ③ PR merge ④ 実機検証

### 条件待ち (6 件、明示 trigger 付き)

#### 1. PR #250 マージ + 本番 BQ migration apply + 実機検証

- **trigger**: 本田様の番号単位明示認可 (CLAUDE.md §3「PR #250 をマージしてよい」)
- **trigger 充足時の作業順序** (CRITICAL R6 デプロイ skew 対応):
  1. 本番 BQ に migration apply (本田様手動):
     ```bash
     bq query --use_legacy_sql=false --project_id=monthly-pay-tax \
       < infra/bigquery/migrations/2026-06-14_leader_team_monthly_budgets.sql
     ```
  2. seed 件数/合計確認:
     ```bash
     bq query --use_legacy_sql=false \
       "SELECT COUNT(*), SUM(budget_amount) FROM \`monthly-pay-tax.pay_reports.leader_team_monthly_budgets\` WHERE fiscal_year=2026"
     ```
     → 72 行 / SUM が team_budgets_quarterly の fiscal_year=2026 合計と一致確認
  3. PR #250 merge (squash recommended)
  4. GitHub Actions で dashboard 自動デプロイ完了確認
  5. 本田様実機検証 (全体タブ月次推移グラフが月毎別値で描画 + 統括隊タブ + admin 入力 page で grid 編集/保存)
- **A/B/C 分類**: C 起点指示済み (本田様明示認可必須)

#### 2. PR #250 merge 後の handoff PR (本ファイル)

- **trigger**: PR #250 merge 後
- **trigger 充足時の作業**: 本 handoff PR を merge (#250 と独立、small tier)
- **A/B/C 分類**: B housekeeping

#### 3. Issue #245 隊ドリルダウン強化 (要望 4、postponed)

- **trigger**: 本田様から「#245 を進めて」明示指示 + PR #250 merge 完了
- **trigger 充足時の作業**: `/brainstorm` で要件深掘り → 実装
- **A/B/C 分類**: C 起点指示済み (postponed ラベル付き、要明示指示)

#### 4. Q4 2026 (8-10月) 仮予算 CSV 投入 (継続運用)

- **trigger**: 本田様から Q4 (8-10月) 仮予算データ提供
- **想定工数**: 15 分

#### 5. 2026-07-01 07:00 JST: Cloud Scheduler 月次バッチ初回自動実行確認

- **trigger**: 期日到来 (2 週間後)
- **想定工数**: 5 分

#### 6. 2026-10-16 までに Gemini 3 Flash GA 後 `thinking_level="minimal"` 移行

- **trigger**: Gemini 3 Flash GA (Vertex AI release notes)
- **deadline**: 2026-10-16

### 却下候補 (記録のみ、明示指示待ち)

#### A. PR #250 follow-up 9 件 (Codex 4 巡目で整理)

Codex final review の結論通り、本 PR では止めずに follow-up Issue 候補として記録 (Issue 起票は本田様明示指示時のみ可、現状未起票):

| 優先度 | 内容 |
|---|---|
| Medium | 1. 0 円入力と削除の区別 (PR #246 同型問題) |
| Medium | 2. 統括隊×月ヒートマップを新テーブル予算で再計算 |
| Medium | 3. bulk MERGE 化 (seed_from_quarterly + _persist_diff の N query → 1 query) |
| Medium | 4. seed_from_quarterly の overwrite=False デッドコード整理 |
| Low | 5. NUMERIC→int 丸め方針の完全統一 (一部 `int()` truncate 残) |
| Low | 6. st.rerun() 後の成功メッセージを session_state に flash 化 |
| Low | 7. grid 列 help を統括隊別差分表示に強化 |
| Low | 8. 年跨ぎ OR 句 SQL の helper 抽出 (3 関数 24 行 copy-paste 解消) |
| Low | 9. _persist_diff の page level 統合テスト追加 |

→ **A/B/C 分類**: C (起点アイデアは decision-maker 領分、Issue 起票は本田様明示指示時のみ)

#### B. 既存 OPEN Issues 3 件 (#94 / #58 / #54)

- すべて P2 backlog、更新日 2 ヶ月以上前
- **A/B/C 分類**: C (decision-maker 明示指示時のみ着手)

#### C. CLAUDE.md L98 のテーブル一覧に leader_team_monthly_budgets 追加

- PR #250 merge 後の small housekeeping、本 PR では実装に集中
- **A/B/C 分類**: A housekeeping、PR #250 merge 後の次セッションで対応推奨

---

## 本セッションで顕在化した AI 側の学び (プロセス教訓)

### 1. handoff 教訓 #1 (全タブ × データソース マトリクス先行確定) の効果実証

前セッション (2026-06-13 夜) で「brainstorm 段階の意図汲み取り失敗 → 大規模 hotfix の連鎖」と記録した教訓を本セッションで実証:

Phase 3 質問 #1 で「データソース統一」を最初に確定 → Phase 4 マトリクス表で全タブ × データソースを明示提示 → 本田様 1 度の承認で確定 → hotfix 連鎖回避。実装後の Codex セカンドオピニオンも軽微修正のみで完走。

**今後の教訓**:
- 設計の核心となる「データソース選択」「年度軸選択」等は brainstorm Phase 3 で必ず先行確定する
- 確定事項はマトリクス表で可視化し、本田様承認を 1 度の round で取る

### 2. Codex セカンドオピニオン 4 巡の有効性

設計 → impl-plan → QG Stage 4 → 完成形で計 4 回 Codex review を実施。各巡で適切な粒度の指摘を得て段階的に品質向上:

| 巡 | 主な指摘の性質 |
|---|---|
| 1 (設計時) | アーキテクチャ / データモデル / インターフェース (大粒度) |
| 2 (impl-plan 時) | 依存関係 / Round 順序 / デプロイ skew (実行戦略) |
| 3 (QG Stage 4) | コード品質 / 仕様乖離 (実装詳細) |
| 4 (完成形) | マージ判定 / follow-up 整理 (最終判定) |

**今後の教訓**:
- 大規模 PR (5+ ファイル) は Codex review を複数巡実施が有効
- 各巡で異なる視点 (設計 / 計画 / 実装 / マージ判定) を引き出す質問プロンプトを設計する

### 3. R7 (PR #246 回帰リスク) を実装判断で minimize した事例

設計書では「team_budget.py の selector を fiscal_year selector に切替」と明記していたが、実装中に Codex R7 を再評価し「selector は暦年維持 + 内部 fiscal_year 導出」に変更。本田様承認を得て進めた結果、PR #246 編集 UI は無回帰で AC13 (11/12 月境界) も達成。

**今後の教訓**:
- 設計書承認後でも、実装中に発見した回帰リスクは Round 完了報告時に本田様判断を仰ぐ
- 「selector 変更」のような UI 全面改修は最小スコープで AC を達成する代替手段を優先検討

---

## 残留プロセス

本プロジェクト (monthly-pay-tax) のプロセスはなし。

---

## 最終結論

⚠ **セッション終了可、ただし PR #250 マージ判断のみ本田様アクション必須**

- 本日 Issue #248 完成、PR #250 作成、QG 4 段完了、Codex 4 巡最終マージ可判定
- executor 領分の作業ゼロ (即着手なし、テスト 1056 件全 PASS、git clean、リモート同期済)
- 条件待ち 6 件中、最重要は #1 (PR #250 マージ + 本番 migration apply、本田様判断待ち)
- handoff PR (本ファイル) は PR #250 と独立、別 review でマージ可

**次セッション再開時のプロンプト案**:

```
catchup → docs/handoff/LATEST.md の「条件待ち #1 (PR #250 マージ + 本番 migration apply)」を確認
→ 本田様から「PR #250 をマージしてよい」明示指示があれば:
  1. 本番 BQ に migration apply (手動実行確認)
  2. seed 72 行 + SUM 一致確認
  3. PR #250 merge
  4. dashboard 自動デプロイ確認
  5. 本田様実機検証完了報告
→ 実機検証で問題発見時は hotfix Issue 起票
→ 問題なしなら handoff PR (本ファイル更新) もマージ
→ 残った条件待ち #3-#6 は trigger 未充足なら idle skip プロトコルでセッション終了
```
