# ハンドオフメモ - monthly-pay-tax

**更新日**: 2026-06-13 (本番障害 4 件解消 + google-genai SDK 1.x 移行 + docs 追記)
**フェーズ**: 予実管理機能 Phase 2.5 (PR-A/B/Q2M 本番稼働、PR #233 #236 #238 #239 で連鎖障害 4 件解消)
**最新デプロイ**: pay-dashboard (PR #238) + pay-collector (PR #239) 自動デプロイ進行中
**テストスイート**: Dashboard **467** + Cloud Run **236** + scripts **131** = **834 テスト全 PASS** (CI 自動実行)

## 2026-06-12 PM 〜 2026-06-13 セッション完了サマリー

午前セッション (PR #224-#231 / 第3Q仮予算投入) 直後、本田様による実機確認で **4 件の本番障害**と **4 件の新規要望 (1b/2/3/4)** が顕在化。障害 4 件はすべて解消、要望 4 件は別セッションへ引き継ぎ。

### 本セッションで対応した本番障害 4 件

#### 1. 統括隊タブ Decimal/float TypeError (PR #233)

| 項目 | 内容 |
|---|---|
| 症状 | 予実管理ページ「🏢 統括隊」タブ表示時に `TypeError: unsupported operand type(s) for /: 'decimal.Decimal' and 'float'` |
| 原因 | `v_team_budget_actuals` の NUMERIC 列が pandas で `Decimal` になり、PR-Q2M (#231) で導入した `leader_team_budgets` override の `float` 値と混在 |
| 修正 | `summarize_by_leader_team` の groupby agg 直後に `actual_amount` / `budget_amount` を `float` 化 |
| マージ commit | `9cd424b` (PR #233) |

#### 2. AI 評価コメント生成 403 PERMISSION_DENIED (Vertex AI API 未有効化)

| 項目 | 内容 |
|---|---|
| 症状 | 「🔍 隊ドリルダウン」タブの「評価を更新」ボタンで AI コメント生成不可 |
| 原因 | Vertex AI / Agent Platform API (`aiplatform.googleapis.com`) が未有効化、PR-B (#218 系列) 実装時に有効化手順漏れ |
| 修正 | `gcloud services enable aiplatform.googleapis.com --project=monthly-pay-tax` 実行 (本田様明示認可後) |
| docs 追記 | PR #234: CLAUDE.md に Vertex AI API 有効化手順追加 |

#### 3. AI 評価コメント生成 `validation NG: empty` (Gemini 2.5 系 thinking バグ + SDK 古い)

| 項目 | 内容 |
|---|---|
| 症状 | API 有効化後も「評価を更新」で 3 リトライ後 `EvaluationValidationError: max regen reached: empty` |
| 原因 | Gemini 2.5 Flash は `thinking_budget` 未設定時に最大 8,192 tokens 自動思考、`max_output_tokens=350` を完全消費 → 応答テキスト空 |
| 修正 | `google-genai` を `0.8.0` → `>=1.47.0,<2.0` アップグレード + `types.ThinkingConfig(thinking_budget=0)` 追加 |
| マージ commit | `48802df` (PR #236) |
| プロセス上の教訓 | 初手で `rules/tech-selection.md`「LLMモデル指定 → WebSearch」/ memory `reference_vertex_ai_to_gemini_enterprise_2026.md` を踏まず本田様に指摘されて補完。次セッション以降の予防策として handoff 末尾に記録 |

#### 4. 月次推移グラフ Y 軸桁異常 (PR #238)

| 項目 | 内容 |
|---|---|
| 症状 | 全体タブ月次推移グラフで実額 Y 軸が ¥4,500,000,000,000 (4.5 兆) と桁違いに表示 |
| 原因 | `v_team_budget_actuals` の NUMERIC 列が Decimal で altair / vega-lite に渡って文字列解釈 (PR #233 と同系統で `monthly_trend` agg が未対応で残存) |
| 修正 | `team_budget_view.py` に `build_monthly_trend` 純関数を切り出し、agg 直後に float 化 |
| マージ commit | `f90b0c9` (PR #238) |

#### 5. AI 評価コメント生成 `validation NG: PIIリーク:名前` false positive (PR #239)

| 項目 | 内容 |
|---|---|
| 症状 | PR #236 で empty 解消後も「評価を更新」で 3 リトライ後 `EvaluationValidationError: max regen reached: PIIリーク:名前` |
| 切り分け | PR #237 のレスポンス構造ログから `finish_reason=STOP / safety NEGLIGIBLE / thoughts=None / candidates=148 tokens` を確認、Gemini は応答テキスト生成済み、validate が reject していると判明 |
| 真因 | member_master の 2 文字 last_name 233 件 / first_name 198 件 / nickname 25 件 = 計 456 件が member_names セットに登録。隊名「すごいシステムつくり隊」内の「すごい」が nickname と一致して false positive |
| 修正 | `validate_ai_comment` に `exclude_substrings` パラメータ追加、`team_eval_service.process_one_team` で `validation_context=(team,)` を渡す。隊名と無関係の本物の人名は引き続き検出 |
| マージ commit | `ffa6449` (PR #239) |

### 副次的観察 (障害ではない)

Cloud Run ログに `JWT verify failed: Token has wrong audience https://...run.app/, expected one of ['https://...run.app']` の WARNING が記録されているが、これは audience 末尾スラッシュの差で `actor="unknown"` 扱いになるだけ。リクエスト自体は処理されるため無関係。優先度低の cleanup 候補として残置。

### PR 一覧 (7 件すべて merged)

| PR | 内容 | マージ commit |
|----|------|--------------|
| #233 | 統括隊タブの Decimal/float TypeError 修正 + 回帰防止テスト 2 件 | 9cd424b |
| #234 | CLAUDE.md に Vertex AI API 有効化手順を追記 | de490a7 |
| #235 | handoff (LATEST.md) を PR #233 / #234 時点で一時更新 | f7d0d9d |
| #236 | google-genai 1.x upgrade + `thinking_budget=0` で Gemini 2.5 thinking 無効化 + テスト 1 件 | 48802df |
| #237 | validation NG 時の response 構造ログ出力 (障害切り分け) + テスト 4 件 | c209bda |
| #238 | 月次推移グラフの Decimal/float 不整合修正 + テスト 4 件 | f90b0c9 |
| #239 | PII validate に `exclude_substrings` 追加で隊名 false positive 解消 + テスト 4 件 | ffa6449 |

### 本田様報告の新規要望 4 件 (1b / 2 / 3 / 4)

本セッションでは扱わず、別セッションで `/brainstorm` → `/impl-plan` で進める想定:

| # | 概要 | 推奨アプローチ |
|---|------|--------------|
| **1b** | 月次推移グラフの予算が ¥0 フラットライン (PR-Q2M 月予算が KPI のみ反映、グラフ未反映) | 統括隊月予算合計の各月展開 / 隊×月予算投入 / 別系統テーブル新設 のいずれか |
| **2** | 隊マトリクスタブが空表示「意味が分からない」 | team_budgets 未投入で達成率算出不可。#3 と連動して解消、または達成率→実額ヒートマップに変更 |
| **3** | 隊ドリルダウンに各隊月予算入力 UI 追加 (統括隊予算との整合性チェック付き) | PR-F の team_hierarchy 編集ページと同系統の DML UI |
| **4** | 隊ドリルダウンの業務報告詳細を「業務報告一覧」と同等にする (依存型ドロップダウン / 検索 / KPI / 詳細テーブル) | 既存コード共有化 or 局所版作成の設計判断要 |

---

## 前セッション (2026-06-12 AM) サマリー (要約)

| 項目 | 状態 |
|---|---|
| PR #224-#231 (8 件) | ✅ すべて merged: hash CTE 修正 / UI cleanup / **PR-A** BQ + lib 基盤 / **PR-B** 4 タブ再構成 / **PR-Q2M** 四半期予算→月予算表示 |
| BQ migration apply | ✅ `v_team_budget_actuals` VIEW 改訂 (INNER JOIN team_hierarchy + WHERE operating)、`leader_team` 列追加 |
| 第3Q (5-7月) 仮予算投入 | ✅ `team_budgets_quarterly` に 6 統括隊 × 7 カテゴリ = 42 行投入、合計 23,457,444 |
| Playwright 実機検証 | ✅ 4 タブ表示 / 非「隊」除外 / 統括隊フィルタ等 |

---

## 環境状態

- **Git**: clean (本 handoff PR でこのコミットを作成予定)
- **CI**: Test ✅ (本セッション全 PR で Dashboard / Cloud Run tests pass)
- **本番デプロイ**: pay-dashboard (PR #238) + pay-collector (PR #239) 自動デプロイ進行中
- **OPEN PR**: 0 件 (本 handoff PR は末尾で作成)
- **OPEN Issues**: 3 件 (#94 / #58 / #54、すべて P2 backlog、本セッション関与なし)
- **残留プロセス**: 確認時点で本プロジェクト関連プロセスなし
- **グローバル memory 変更**: なし

---

## ドキュメント整合性

| 項目 | 状態 |
|---|---|
| CLAUDE.md ↔ Cloud Run エンドポイント仕様 | ✅ PR #234 で Vertex AI API 有効化手順追加 |
| CLAUDE.md 行数 | ⚠ 333 行 (200 行公式推奨値を超過、表面化していないため次セッションで分割検討候補) |
| `dashboard/lib/team_budget_view.py` ↔ テスト | ✅ Decimal 入力ケース対称性確保 (PR #233 #238) |
| `cloud-run/vertex_evaluator.py` / `pii_masker.py` ↔ テスト | ✅ thinking_budget / debug log / PII context 除外 を新規テスト 9 件で監視 |
| `cloud-run/requirements.txt` SDK pin | ✅ `google-genai>=1.47.0,<2.0` に固定 |
| handoff LATEST.md | ✅ 本 PR で更新 (障害 4 件 + 要望 4 件 + 教訓を反映) |

---

## Issue Net 変化

- **Close 数**: 0 件
- **起票数**: 0 件
- **Net**: ±0 件

本セッションは本番障害対応のため Issue 起票なしが正しい運用 (triage 基準 #1 実害ありに該当するが、即時 PR で解消したため Issue 化せず PR で完結)。要望 1b / 2 / 3 / 4 も本 handoff で記録するため Issue 化不要。

---

## 次のアクション

### 即着手タスク (0 件)

**executor 領分の即着手作業ゼロ**。

理由:
- 本セッションで本番障害 4 件をすべて解消
- 残課題は全て decision-maker (本田様) 判断待ち、または期日待ち

### 条件待ち (5 件、明示 trigger 付き)

#### 1. 本田様による AI 評価コメント生成の最終実機確認 (PR #239 効果検証)

- **trigger**: Cloud Run pay-collector のデプロイ完了 (約 3-5 分) + 本田様の「評価を更新」ボタン押下
- **trigger 充足時の作業**: 本田様自身で視認。期待動作:
  - 「評価を更新」ボタン押下 → spinner 約 5-15 秒 → 緑のメッセージ `評価生成完了 (generated=1 skipped_hash_match=0 failed=0)`
  - rerun 後にカード本文に Gemini 2.5 Flash の評価コメント表示 (2-6 行、100-400 文字)
- **failure 時**:
  - 別の reason で reject (例: `行数不正` / `文字数不正`) → validation ロジックの閾値調整が必要 (別 PR)
  - 別の `PIIリーク:名前` reason → 隊名以外の context (統括隊名等) も exclude_substrings に追加する PR
  - SDK / API 系の新エラー → Cloud Run ログを再確認
- **想定工数**: 本田様作業のみ

#### 2. 本田様による統括隊タブ + 月次推移グラフ実機確認 (PR #233 + #238 効果検証)

- **trigger**: 本田様の dashboard `team_budget` → 各タブアクセス + Cmd+Shift+R ハードリロード
- **trigger 充足時の作業**: 統括隊タブで TypeError 出ず KPI 表示、全体タブで月次推移グラフが ¥4M〜¥5M レンジで正常表示
- **想定工数**: 本田様作業のみ

#### 3. 本田様報告 1b / 2 / 3 / 4 の要件具体化 (新規要望、別セッション推奨)

- **trigger**: 別セッション開始時の本田様の優先度指示
- **trigger 充足時の作業**: `/brainstorm` で要件整理 → `docs/specs/` 出力 → `/impl-plan` → 実装
- **想定工数**: 要件 1 件あたり brainstorm 30-45 分、impl-plan + 実装 1-3 セッション

#### 4. Q4 2026 (8-10月) 仮予算 CSV 投入 (継続運用、前セッションから継続)

- **trigger**: 本田様から Q4 (8-10月) 仮予算データ画像 / CSV 提供
- **trigger 充足時の作業**: CSV 抽出 → BQ INSERT (Q3 同手順)、fiscal_year=2026 fiscal_quarter=4
- **想定工数**: 15 分

#### 5. 2026-07-01 07:00 JST: Cloud Scheduler 月次バッチ初回自動実行確認 (前 handoff から継続)

- **trigger**: 期日到来 (約 2 週間後)
- **trigger 充足時の作業**: Chat 通知 / BQ `SELECT COUNT(*) FROM team_monthly_eval WHERE generated_at >= '2026-07-01'` を確認
- **想定工数**: 5 分

### 却下候補 (記録のみ、明示指示待ち)

#### A〜D. 前セッションから引き継ぎの Codex follow-up 4 件

前 handoff (PR #232) の「却下候補 A〜D」をそのまま継続:
- A. 年累計ランキングの予算マーカー拡張
- B. マトリクスジャンプ → ドリルダウン UX 改善
- C. 月次推移グラフの欠損月表示方針
- D. `summarize_by_leader_team` の `diff_amount` セマンティクス決定

#### E. AI 評価 (vertex_evaluator) の統括隊レベル拡張 (将来 phase)

#### F. 統括隊名のリネーム (シロロ＋ゆずるん統括隊 への改名)

#### G. JWT audience 末尾スラッシュ整合 (副次 WARNING の cleanup)

#### H. CLAUDE.md 200 行超対応 (333 行)

#### I. Gemini 3 Flash GA 公開後の `thinking_level="minimal"` 移行 (中期 deadline: 2026-10-16)

- **検討経緯**: PR #236 は Gemini 2.5 Flash + `thinking_budget=0` の暫定対応
- **trigger**: Gemini 3 Flash の GA 公開 ([Vertex AI release notes](https://docs.cloud.google.com/vertex-ai/generative-ai/docs/release-notes) で確認)
- **trigger 充足時の作業**: モデル ID 切替 + `thinking_budget=0` → `thinking_level="minimal"` 置換
- **deadline 想定**: 2026-10-16 までに完了

#### J. 既存 OPEN Issues 3 件 (#94 / #58 / #54)

---

## 本セッションで顕在化した AI 側の改善ポイント (プロセス教訓)

### 1. LLM モデル / SDK 関連の初手手順漏れ

PR #236 着手時に `rules/tech-selection.md`「LLMモデル指定 → WebSearch」を実行せず、`memory/reference_vertex_ai_to_gemini_enterprise_2026.md` も読まずに先走り、本田様から「VertexAI（現：GeminiEnterpriseAgentPlatform）の 2026 年 6 月 12 日時点 web 公式最新情報から取得しましたか？そしてグローバルにある rules などハーネスに書いてませんでしたか？」と指摘された。

**次セッション以降の予防策**:
- LLM モデル / SDK 関連の修正は **最初に必ず** WebSearch + 関連 memory 読み込み
- 「思いついた解」を実装する前に rules / memory の関連 entry を grep して本文確認

### 2. Bug 連鎖切り分けの方法論 (今回うまくいったこと)

PR #237 でレスポンス構造ログを追加 → 本番再現で真因確定 → PR #239 で根治、というデバッグサイクルが機能した。今後も「empty / 不明な error が連続したらまずログ強化 PR を 1 本入れて切り分け」を定石にする価値あり。

---

## 残留プロセス

本プロジェクト (monthly-pay-tax) のプロセスはなし。

---

## 最終結論

✅ **セッション終了可** — 本番障害 4 件解消 (PR #233 / Vertex AI API 有効化 / PR #236 / PR #238 / PR #239)、再発防止 docs 追記 (PR #234)、ログ強化 (PR #237)、834 テスト全 PASS、Git clean (本 handoff PR で確定予定)、OPEN PR ゼロ、即着手タスク 0 件、条件待ち 5 件はすべて executor 領分外。

- OPEN PR: 0 件 (本 handoff PR を末尾で作成)
- 即着手タスク: **0 件** (executor 領分の作業ゼロ)
- 条件待ち: 5 件 (AI 評価実機確認 / グラフ実機確認 / 要望 1b-4 要件整理 / Q4 予算 / 7/1 Scheduler 期日)
- 却下候補: 引き継ぎ 4 件 + 6 件 (E〜J、すべて明示指示待ち)
- 既知 blocker: なし

**次セッション再開時のプロンプト案**:

```
catchup → docs/handoff/LATEST.md の「即着手 0 件、条件待ち 5 件」を確認
→ AI 評価コメント生成の実機確認結果報告があれば対応
→ 本田様要望 1b / 2 / 3 / 4 のいずれかに着手指示があれば /brainstorm で要件整理から開始
→ Q4 予算データ提供があれば BQ INSERT (Q3 同手順)
→ 2026-10-16 までに Gemini 3 Flash GA 公開状況を監視、GA 後に thinking_level 移行 PR
→ 指示なければセッション終了推奨 (idle skip プロトコル)
```
