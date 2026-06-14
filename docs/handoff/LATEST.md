# ハンドオフメモ - monthly-pay-tax

**更新日**: 2026-06-14 (本セッション完走 / Issue #257 + #263 完走 + #264 仕様確認 close)
**フェーズ**: 予実管理機能 Phase 5 (前月比 MoM delta 3 軸対応 + 月予算編集バリデーション改善、本田様実機検証待ち)
**最新デプロイ**: pay-dashboard PR #265 + #266 反映済 (Deploy Dashboard 自動 workflow 起動済) / pay-collector 変更なし
**テストスイート**: Dashboard **673** (+24 本セッション) + Cloud Run **276** + scripts **152** = **1101 件 全 PASS**

---

## 2026-06-14 本セッション完了サマリー (PR 2 件 merge + Issue 3 件 close + 起票 2 件)

前 handoff #262 終了後、本田様が本番 dashboard で発見した 2 件のバグを即 Issue 化 (#263 / #264)。#264 は仕様確認結果 not planned で close、#263 は fix 実装 + merge。並行して Issue #257 (前月比 MoM delta 3 軸対応) を brainstorm → impl-plan → TDD で完走 + merge。

### PR #265: 月予算編集の入力中リアルタイム超過警告 (fix Issue #263)

統括隊月予算の残額を超過する金額を入力中に視覚的フィードバックがない問題。本田様判断「案 A: リアルタイム警告 + 保存時ソフトブロック保持」を採用。

- 2 files / +64/-0 行 (commit `1f0c8b4`)
- 既存純粋関数 `overflow_amount` を再利用、`_render_team_budget_editor` の caption 直後に 5 行追加
- tests: `test_input_overflow_shows_realtime_warning` + `test_input_within_remaining_no_overflow_warning` の 2 件追加
- CI: Cloud Run tests ✅ / Dashboard tests ✅

### PR #266: 前月比 (MoM delta) 表示 3 軸対応 (feat Issue #257)

全体 / 統括隊 / 隊ドリルダウンの 3 タブで前月比表示を追加。brainstorm で 5 要確認事項を本田様と確定 → impl-plan で T1-T7 に分解 → TDD で完走。code-review MEDIUM finding (達成率分母不一致) は本 PR 内で fix 反映 (オプション A 採用)。

- 5 files / +884/-19 行、3 commits (commit `399d203`)
- 設計仕様書: `docs/specs/2026-06-14-team-budget-mom-delta.md` (256 行、AC1-AC7)
- 純粋関数 4 件: `compute_mom_delta` / `format_mom_yen` / `format_mom_pt` / `attach_mom_columns` を `lib/team_budget_view.py` に追加
- `render_kpi_row` API 拡張 (`mom` kwarg、既存の達成率 delta=予実差額を MoM 達成率に置換)
- UI 関数化: `_render_drilldown_summary` (隊ドリルダウン集計セクション、関数化で test 容易化)
- tests: +22 件 (純粋関数 17 + UI 統合 3 + render_kpi_row 2)
- **Quality Gate 全 4 段順守**: safe-refactor (LOW 1 件反映) + code-review medium (MEDIUM 2 件 → オプション A で本 PR 内 fix) + Evaluator 第三者検証 (SHOULD 1 件反映、MAY 2 件は follow-up TODO) + pytest 673/673 pass
- CI: Cloud Run tests ✅ / Dashboard tests ✅

### PR #266 内 fix: 達成率前月比の分母不一致 (code-review MEDIUM、オプション A)

修正前: 当月達成率は `_lt_budget_override` (統括隊月予算) で計算、前月達成率は素の budget 集計 → 分母不一致で達成率前月比が運用実態と乖離。

修正後: `load_leader_team_monthly_budgets(fiscal_year, prev_month)` を前月用に追加取得、`_lt_budget_override_prev` として tab_overall / tab_leader の前月集計に適用。当月と対称な分母構造に。

---

## 教訓 (本セッション)

### 教訓 #1: 本田様の本番スクショ報告は即時 Issue 化で記録

Issue #257 brainstorm 中盤、本田様が本番 dashboard でスクショ報告した 2 件のバグを brainstorm 中断して即 Issue 化 (#263 / #264)。triage 基準 #5「ユーザー明示指示」+ #1「実害あり / 再現可能なバグ」で起票。後で議論できる形を確保し、brainstorm を再開。

**学び**: 進行中作業の中断コストよりも、報告内容を Issue として永続化する価値が高い。本田様のスクショ + 一言は揮発する情報源。

### 教訓 #2: 仕様確認結果「現状維持」は close (not planned) + 理由記録で残す

Issue #264 (集計予算未反映) は本田様判断「案 A: 現状維持」となり、コード変更なし。ただし「仕様未理解からの疑問」であることを Issue コメントに記録して not planned close。コードベース履歴に「なぜ現状仕様にしたか」が残る。同様の疑問が再発した時に Issue 検索で答えに辿り着ける。

### 教訓 #3: code-review MEDIUM finding は本 PR 内 fix の選択肢を必ず提示

PR #266 で code-review が「達成率前月比の分母不一致」を MEDIUM 検出。spec で「scope 外」と明示済の既知制限だったが、本田様判断「オプション A: 本 PR で fix」採用 → `_lt_budget_override_prev` 追加で当月/前月の分母を統一。

**学び**: MEDIUM finding は「follow-up TODO」だけでなく「本 PR 内 fix」も選択肢として提示する。spec で許容済でも、実装コストが低ければ取り込んだ方が長期負債を抑える。本田様の判断材料を増やす。

---

## Issue Net 変化

| 項目 | 値 |
|---|---|
| Close | 3 件 (#257 + #263 + #264) |
| 起票 | 2 件 (#263 + #264) |
| **Net** | **-1 件** ✅ |

triage 基準遵守: 起票 2 件とも triage 基準 #5「ユーザー明示指示」+ #1 (#263 は実害ありバリデーション欠落、#264 は仕様確認のため起票)。rating 5-6 の review agent 提案を機械的に Issue 化していない。

---

## 次のアクション

### 即着手タスク

なし。

### 条件待ち (明示 trigger 付き)

| # | 項目 | A/B/C | trigger | 充足時のタスク |
|---|---|---|---|---|
| 1 | 本田様 PR #265 + #266 実機検証 | 本田様判断 (B 検出後の write 待ち) | 本田様から「OK」or 問題報告 | OK なら Issue #257 AC7 達成宣言、問題なら hotfix Issue 起票 |
| 2 | Issue #258 (統括隊 ID 化 refactor, P1) | C 起点指示済み待ち | 本田様「#258 を進めて」明示指示 | impl-plan で破壊的 migration 設計 (BQ schema + team_hierarchy / team_budgets_quarterly / leader_team_monthly_budgets / team_monthly_eval + VIEW 群)、Codex セカンドオピニオン必須、複数 PR 分割の可能性高 |
| 3 | PR #266 follow-up TODO 3 件 (page-level MoM 統合テスト追加 / `compute_mom_delta` Decimal 型テスト / `prev_month_calc` 3 タブ重複を `fiscal_calendar` helper に集約) | C 起点指示済み待ち | 本田様明示指示 | tests 追加 + refactor を別 PR で起票・対応 |
| 4 | Issue #94 Cloud Run コスト監視 (P2、ADR-0004 効果測定) | C 起点指示済み待ち | 本田様明示指示 + 監視 dashboard / 期間指定 | metrics 取得 SQL 確定後に impl-plan |
| 5 | Issue #58 / #54 WAM 関連 (P2) | 本田様判断 | Phase 0 ステークホルダー回答 | 回答内容に応じて `wam_target_projects` 更新 PR |
| 6 | Issue #245 (postponed) | C 起点指示済み待ち | 本田様「#245 を進めて」明示指示 + 再開条件確認 | 着手不可、monitor のみ |

### 却下候補 (記録のみ・包括指示の対象外)

| # | 項目 | 着手しない理由 |
|---|---|---|
| 1 | memory / docs の整理・再 grep | A housekeeping、明示指示なし |
| 2 | AI 起点の新規 enhancement 発想 | 4 原則 §1 違反 (decision-maker 領分) |
| 3 | dependabot / deprecation 残務確認 | 直近で大きな依存変更なし、検出ニーズ低 |

---

## 残留プロセス (情報のみ)

検出 2 件は **別プロジェクト `visitcare-shift-optimizer` の Firebase emulators + Firestore emulator JAR** で、本プロジェクトとは無関係。本プロジェクトのセッション終了とは独立。

停止する場合: `~/.claude/scripts/cleanup-node.sh --kill`

---

## セッション終了可否

✅ **セッション終了可** — 本セッション主目的 (PR #265 + #266 merge) 完了、executor 領分の残作業ゼロ

根拠:
- 即着手タスクゼロ、PR #265 / #266 とも main merge 完了 + CI 成功 + 自動デプロイ進行中
- main は clean、リモート同期済 (`399d203`)、CI 全 ✅
- Issue Net **-1 件** (進捗あり ✅)
- 次の起点は本田様の実機検証 (Issue #257 AC7 + #263 確認)、または #258 着手指示

### 次セッション再開時の推奨プロンプト

```
catchup → docs/handoff/LATEST.md 確認
→ 本田様 PR #265 + #266 実機検証結果待ち
  - 検証 OK → Issue #257 AC7 達成宣言 (Issue は既 close、PR コメントで実機検証完了報告)
  - 問題報告 → hotfix Issue 起票 + 修正
  - #258 着手指示 → impl-plan で統括隊 ID 化の破壊的 migration 設計、Codex セカンドオピニオン
  - PR #266 follow-up TODO 着手指示 → 別 PR で tests 追加 + refactor
```

---

## 本セッション通算

| 項目 | 値 |
|---|---|
| PR merge | **2 件** (#265 / #266) |
| Issue close | 3 件 (#257 / #263 / #264) |
| Issue 起票 | 2 件 (#263 / #264) |
| Issue Net | **-1 件** ✅ |
| brainstorm セッション | 1 件 (#257 前月比表示、5 要確認事項確定) |
| impl-plan セッション | 1 件 (#257 T1-T7 分解 + Acceptance Criteria 確定) |
| 設計文書 | 1 件 (`docs/specs/2026-06-14-team-budget-mom-delta.md`) |
| QG 4 段 | safe-refactor + code-review medium + Evaluator + pytest (PR #266) |
| テスト | 649 → 673 件 (+24、PR #265 で +2、PR #266 で +22) |
| 教訓記録 | 3 件 (本番スクショ即 Issue 化 / not planned close 理由記録 / MEDIUM finding 本 PR fix) |

---

**本日もお疲れさまでした。** PR #265 + #266 デプロイ後のハードリロード (Cmd+Shift+R) で実機検証をお願いします。
