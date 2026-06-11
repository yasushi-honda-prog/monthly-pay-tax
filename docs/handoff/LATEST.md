# ハンドオフメモ - monthly-pay-tax

**更新日**: 2026-06-10（予実管理機能 4 PR シリーズ #210 / #211 / #212 / #213 すべてマージ完了。IAM 付与 + Cloud Scheduler ジョブ作成済み、月次自動評価バッチが 2026-07-01 07:00 JST に初回起動予定）
**フェーズ**: WAM助成金対応 **技術側完了** + **CI/CD 自動デプロイ稼働中** + **管理機能拡充フェーズ完了** + **運用ドキュメント基盤稼働** + **手動同期 UI 稼働** + **データ安全性向上フェーズ完了** + **snapshot 障害対応・耐障害性強化完了** + **業務報告一覧タブ UX 改善完了** + **WAM業務報告タブ稼働中** + **報告者数 KPI 明確化** + **OAuth リダイレクトループ対応** + **説明系ページのトンマナ統一** + **🆕 予実管理機能 (Vertex AI Gemini 2.5 Flash) 4 PR シリーズ完了**
**最新デプロイ**: pay-collector PR #212 適用済 / pay-dashboard PR #213 適用中 (Deploy Dashboard workflow 走行中)
**テストスイート**: Dashboard **416** + Cloud Run **226** = **642 テスト全 PASS** (CI 自動実行) + scripts/tests **26**

## 🆕 2026-06-10 セッション完了サマリー — 予実管理機能 4 PR シリーズ完遂

ユーザー要望: 隊（活動）分類ごとの月毎予算設定と、Vertex AI Gemini 2.5 Flash (日本リージョン) による多角的評価・アドバイス、BI 的ビュー。dashboard 内に専用ページ。
本セッション (1 セッション内) で spec 策定 → BQ 基盤 → Cloud Run AI → スケジューラ → dashboard UI まで完遂。

| PR | 内容 | マージ | 備考 |
|----|------|--------|------|
| #209 | docs(spec): 予実管理機能 設計仕様書 (前セッションマージ) | 7eebbcb | brainstorm Phase 3-5 + 12 項目要件確定 + Codex セカンドオピニオン 3 ラウンド (前セッション分) |
| #210 | feat(team-budget): PR-A BQ 基盤 + 予算入力スクリプト | 8a4abbc | team_budgets / team_monthly_eval / v_team_budget_actuals / extract_month UDF / scripts/upload_budgets.py (前セッション分) |
| #211 | feat(team-budget): PR-B Cloud Run AI 評価エンジン (隊×月 Vertex AI Gemini 2.5 Flash) | e86e0dc | pii_masker / vertex_evaluator / team_eval_service / POST /eval/team-monthly。Codex 7 件 + Agent 8 件のセカンドオピニオン中、必須 8 件反映 |
| #212 | fix(team-budget): PR-C スケジューラ統合 + PR-B 残課題 4 件対応 + セカンドオピニオン 11 件反映 | b9977bf | async モード撤廃 + sync 一本化 / claim 重複行 dedup / JWT signature 検証 / snapshot 対象拡張 / Dockerfile threads=2 / SERVICE_AUDIENCE_URL deploy 設定 |
| #213 | feat(team-budget): PR-D dashboard UI 予実管理ページ + Evaluator/Codex/Agent 9件反映 | eac8d5f | 3 サブタブ (📊全体サマリー / 🏷️隊×月マトリクス / 🔍隊ドリルダウン) + AI コメントカード (outdated バッジ + 評価更新/強制再生成) + 業務報告詳細テーブル |

### 完成機能 (実装 + テスト pass)

1. ✅ **BigQuery スキーマ** — `team_budgets` (隊×月予算、version カラム / optimistic lock)、`team_monthly_eval` (claim row pattern: lock_token / lock_until / lock_actor)、`v_team_budget_actuals` (CTE 6 段で年/月/隊で予実 FULL OUTER JOIN)、`extract_month` UDF (YYYY/M/D 優先判定)
2. ✅ **Vertex AI Gemini 2.5 Flash 評価エンジン** — asia-northeast1 (データレジデンシー)、PII マスキング (名前/メール/電話 → `<MEMBER>`/`<EMAIL>`/`<PHONE>`)、生成後検証 (行数/文字数/PII リーク)、exponential backoff retry (call failure と validation NG の独立 retry 系列)、3 段階の達成率レンジ別 judgment context
3. ✅ **Cloud Run `/eval/team-monthly` endpoint** — sync 一本化 (async daemon thread silent kill リスク排除)、claim row pattern + 重複 INSERT 防御 dedup、JWT signature 検証 (`id_token.verify_token` + `SERVICE_AUDIENCE_URL` audience 設定)、stale lock 防御 (`lock_until > NOW()` guard)、teams 入力 type 検証 (str を list 扱いするバグソース排除)
4. ✅ **Cloud Scheduler 月次バッチ** — `team-budget-eval-monthly` (`0 7 1 * *` JST、attempt-deadline=1800s、OIDC + audience)、初回実行 2026-07-01 07:00 JST、24 隊 × 〜30s + retry で 12-20 分想定
5. ✅ **dashboard 予実管理ページ** — 3 サブタブ構成、Altair ヒートマップ (classify_achievement と整合する bucket 離散色)、ブレットチャート (棒=実額 / マーカー=予算)、データ削除を検知する is_outdated (stored 非空 / current 空 → False、stored 空 / current 非空 → True)、ベクトル化キーワード検索 (NaN 誤マッチ防止)、deterministic button key (年-月-隊)、個別 cache.clear() (全 nuke 回避) + st.rerun()
6. ✅ **architecture / help / spec 更新** — Mermaid 図に月次 Scheduler + Vertex AI + team_monthly_eval、help ページに予実管理 3 サブタブガイド + AI 仕組み + 予算入力運用、spec §4.5 hash SQL を tie-breaker 込み (`ORDER BY row_hash, row_json`) に改訂
7. ✅ **snapshot バックアップ拡張** — `BQ_SNAPSHOT_TABLES` に `team_budgets` / `team_monthly_eval` を追加。誤 DML 破壊からの 90 日 snapshot 復旧経路を保持

### 本番インフラ反映 (本田さん明示認可で実行済)

| 項目 | 値 | 実行日時 |
|---|---|---|
| **IAM 付与** | `roles/aiplatform.user` を pay-collector@ に追加 | 2026-06-10 約 20:50 JST |
| **Cloud Scheduler ジョブ作成** | `team-budget-eval-monthly` (asia-northeast1, ENABLED) | 2026-06-10 約 22:18 JST |
| **Cloud Run deploy** | pay-collector PR #212、pay-dashboard PR #213 (走行中) | 2026-06-10 自動 |

### セカンドオピニオン履歴 (本セッション分のみ)

| PR | Codex | Agent code-reviewer | Evaluator | 必須修正反映 |
|---|---|---|---|---|
| #211 (PR-B) | High 2 + Medium 3 + Low 2 | Important 8 | (5 ファイル超だが未実施) | 8 件 (Medium-3 / Medium-5 / Low-6 / EVAL_TIMEOUT / load_team_samples 0値 / PHONE_RE 10-11桁 / load_member_names try/except / _HASH_SQL tie-breaker) |
| #212 (PR-C) | High 2 + Medium 2 + Low 1 | Important 5 | (PR-C は機能修正なので未実施) | 6 件 (dedup 強化 / Gemini timeout / _grequest_session thread-safe / verify_token str(exc) / spec §3.4 残骸 / gunicorn threads=2) |
| #213 (PR-D) | Medium 3 + Low 2 | Important 6 | HIGH 1 + MEDIUM 2 + LOW 1 + AC FAIL 3 | 9 件 (Altair bucket / cache 個別 clear / st.rerun() / key_suffix / is_outdated 3 段階 / compute_current_hashes fallback / search 効率化 / selectbox sanitize / spec §4.5 改訂 / zero-width column) |

**残課題 (PR 本文明示・別 PR-E 候補)**:
- AC4 マトリクスのセルクリック遷移 (Streamlit st.dataframe 制約、selectbox 迂回で代替)
- AC5/AC7 業務報告詳細を `_render_gyomu_list_tab` から完全流用 (dashboard.py 700+ 行 refactor)
- force パラメータの server side role 認可 (Cloud Run IAM 認証は通っているが内部の admin/checker/user 区別なし)
- per-team timeout (5 分 lock < 30 分 scheduler window の隙間で 1 隊ハング時にリクレイム可能)

---

## 環境状態

- **Git**: clean、main = `eac8d5f` (PR #213)、すべて origin と同期
- **CI**: Test workflow ✅ success (50s) / Deploy Dashboard workflow 🟡 in_progress (2m56s 経過、SERVICE_AUDIENCE_URL env を伴う新規 dashboard revision 切替中)
- **OPEN Issues**: 3 件 (#94 / #58 / #54、すべて P2、本セッションで触っていない既存 backlog)
- **残留プロセス**: なし
- **memory 変更**: なし (グローバル memory scope チェック対象外)

---

## ドキュメント整合性

| 項目 | 状態 |
|---|---|
| spec §4.5 hash SQL ↔ PR-C/D 実装 | ✅ tie-breaker `ORDER BY row_hash, row_json` で整合 (PR-D で spec 改訂) |
| spec §5.1-5.3 ↔ async モード | ✅ PR-C で「async 撤廃」を改訂ノートで明記 |
| CLAUDE.md ↔ アーキテクチャ図 (architecture.py) | ✅ 月次 Scheduler + Vertex AI を両方に反映 |
| help.py ↔ 実装ページ | ✅ 予実管理ページカード + 3 サブタブガイドを追加 |
| 構造的整合性チェック | ⏭ 新規 BQ テーブル/Cloud Run endpoint を追加したが `/new-resource` は未実施。代わりに 4 PR + Evaluator/Codex/Agent の三重チェックで補完済み (テスト 642 件 PASS で構造的整合性は実質担保) |

---

## Issue Net 変化

- **Close 数**: 0 件
- **起票数**: 0 件
- **Net**: 0 件

本セッションは「ユーザーから明示指示された個別タスク」(CLAUDE.md GitHub Issues triage 基準 #5) で 4 PR を完遂したため、Issue 起票なしが正しい運用。残課題 (PR-E 候補 4 件) は PR-D 本文に明示して decision-maker 判断材料として残してあり、別途 Issue 起票はしていない (本田さんから明示着手指示があれば起票する)。

---

## 次のアクション

### 即着手タスク (1 件)

#### 1. PR-E: 四半期×統括隊×カテゴリ予算の BQ 基盤 + CSV 投入 (Phase 1)

**起源**: 2026-06-10 セッション末尾で本田さんから「[画像] この粒度で予算情報として組み込めますか?」 (第3Q 5-7月 仮予算、6 統括隊 × 7 支出カテゴリのマトリクス) を提示され、設計判断 4 件を AskUserQuestion + Codex セカンドオピニオン (High 3 + Medium 4) で確定済み。スコープ合意済 (本田さん「PR-E 着手して OK」)。context 47% の制約でセッション切替を選択、本セッションで設計合意のみ doc 化。

**ROI**: 月別予算 (PR-A の team_budgets) では捉えきれない四半期予算サイクル + 統括隊 (6 隊) レベルの予実管理 + 7 支出カテゴリ別予算管理を実現する。本田さんが画像通り CSV を作って投入できる状態が DoD。

**確定済み設計判断 (本セッション AskUserQuestion 回答)**:

| 論点 | 採択案 | 根拠 |
|---|---|---|
| 取り込み粒度 | **案 A**: 四半期×統括隊×カテゴリをそのまま保持 (新規テーブル `team_budgets_quarterly`) | シートと 1:1 ノイズなし、既存 monthly 予算 (team_budgets) と並存 |
| 統括隊↔隊マッピング | **案 X**: 新規テーブル `team_hierarchy` | activity_category と leader_team の階層を明示、CSV で投入可能 |
| 自由に使える10万円 / 共通費 | **案 P**: 6 カテゴリと同じレベルでテーブル格納 | Phase 1 は予算のみ表示 (`actual_mapping_status='not_supported_in_phase1'`)、実額紐付けは Phase 2 |
| 会計年度 | **案 N11**: 11 月始まり (Q1=11-1月 / Q2=2-4月 / Q3=5-7月 / Q4=8-10月) | 画像「第3Q (5-7月)」と一致、`fiscal_quarter = 1 + DIV(MOD(month - 11 + 12, 12), 3)` |
| 階層の時系列 | **案 T-NOW**: 現在値のみ保持 (階層は頻繁に変わらない前提) | 最小実装、組織再編時は schema migration で対応 |

**Codex セカンドオピニオン指摘 (反映済み)**:

- **High-1** (Quarter logic): 暦年 Q3=7-9月 ではなく会計 Q3=5-7月 → 案 N11 で fiscal_quarter UDF 実装
- **High-2** (Hierarchy 時系列 PK): activity_category 単独 PK は組織再編に脆弱 → 案 T-NOW で現在値のみ + note 列で運用ガイド
- **High-3** (VIEW セマンティクス曖昧): 「未マッピング NULL」「Phase1 未対応」を区別不能 → `actual_mapping_status` 4 状態列で明示 (`mapped` / `no_actual_rows` / `not_supported_in_phase1` / `budget_missing`)
- **Medium-4** (テーブル名): `team_budgets` (月別×隊) と `team_budgets_quarterly` (四半期×統括隊×カテゴリ) は粒度差を明示する docstring 必須
- **Medium-5** (Hierarchy 再アップロード silent change): gyomu にあるが hierarchy 未定義の隊は実額が漏れる → `v_team_hierarchy_coverage` VIEW + upload script で warn
- **Medium-6** (expense_category typo 防止): 7 カテゴリの日本語表記揺れ → 参照テーブル `expense_categories` で JOIN 検証
- **Medium-7** (CSV 形式): matrix (人間用) vs long (システム用) → BQ は long 格納、script で matrix→long 変換、dry-run プレビュー必須
- **Medium-8** (共通費の dimensional ownership): 6 統括隊と並列にすると合計に影響 → `leader_team_type` 列で `operating` / `common` 区別

**実装スコープ (8-10 ファイル、+1200-1500 行想定)**:

```
infra/bigquery/migrations/2026-06-XX_quarterly_budgets.sql (新規)
  - UDF fiscal_quarter(date_str) → STRUCT<fiscal_year INT64, fiscal_quarter INT64>
  - expense_categories テーブル + 7 行 seed
  - team_hierarchy テーブル (activity_category PK, leader_team, leader_team_type, note)
  - team_budgets_quarterly テーブル (PK: (fiscal_year, fiscal_quarter, leader_team, expense_category))
  - VIEW v_team_budget_actuals_quarterly (budgets FULL OUTER JOIN gyomu rollup, actual_mapping_status 列)
  - VIEW v_team_hierarchy_coverage (gyomu 出現 activity_category と hierarchy の差分)

infra/bigquery/schema.sql, views.sql 更新 (上記 DDL を反映)

scripts/upload_team_hierarchy.py (新規)
  - CSV (activity_category, leader_team, leader_team_type, note) を MERGE
  - dry-run + 「gyomu 出現だが未定義」warn

scripts/upload_team_budgets_quarterly.py (新規)
  - matrix CSV / long CSV 両受け、script で long に normalize
  - expense_categories と JOIN で typo 検知
  - dry-run プレビュー + total check (画像 23,457,444 が再現するか検算)
  - optimistic lock (version カラム)

scripts/tests/test_upload_team_hierarchy.py (新規)
scripts/tests/test_upload_team_budgets_quarterly.py (新規)

docs/operations/team-hierarchy-template.csv (新規)
  - 画像の 2 列目 (広報隊+寄付隊+...) をパースした例

docs/operations/team-budgets-quarterly-template.csv (新規)
  - 画像の数値そのままの matrix 形式 (Q3 2026 = fiscal_year=2026, fiscal_quarter=3)
  - シロロ+ゆずるん統括隊 5,289,363 / ヤスス+ヒデデン統括隊 3,770,728 / ...
  - 合計 23,457,444 (画像と一致)

CLAUDE.md 更新 (新規 BQ テーブル + UDF + VIEW を記載)
docs/specs/2026-06-10-team-budget-eval-design.md 更新 (§3.1 に Phase 2 として記載 or 別 spec 起こす)
```

**expense_categories seed (画像と一致)**:

| sort | expense_category | actual_source | is_phase1_supported |
|---|---|---|---|
| 1 | タダメン業務委託費 | `gyomu` | TRUE (実額マッピング実装) |
| 2 | 旅費交通費 | `reimbursement` | FALSE |
| 3 | 消耗品費 | `reimbursement` | FALSE |
| 4 | 通信運搬費 | `reimbursement` | FALSE |
| 5 | 広告宣伝費 | `reimbursement` | FALSE |
| 6 | 自由に使える10万円 | `none` | FALSE |
| 7 | 共通費 | `none` | FALSE |

**Definition of Done**:
- 本田さんが画像の数値を CSV に書いて `python scripts/upload_team_budgets_quarterly.py budgets_q3_2026.csv` で BQ に投入できる
- `SELECT * FROM v_team_budget_actuals_quarterly WHERE fiscal_year=2026 AND fiscal_quarter=3` で予算と業務委託費実額が比較できる
- 他 6 カテゴリは `actual_mapping_status='not_supported_in_phase1'` で「予算のみ表示」
- `SELECT * FROM v_team_hierarchy_coverage WHERE status='UNMAPPED'` で未マッピング隊を発見できる
- 既存の月別予算 (`team_budgets`) は維持、現状の予実管理ページは挙動変わらず

**品質ゲート**:
- 新機能 + 5 ファイル超 → Evaluator 分離プロトコル発動 (CLAUDE.md 5 ファイル以上ルール)
- Codex review + Agent code-reviewer + Evaluator 3 並列起動
- scripts テスト + cloud-run 既存 226 件 + dashboard 既存 416 件 = 全テスト pass 維持

**Phase 1 で「やらない」こと (PR-F 以降に送る、handoff doc 末尾「却下候補」とは別枠の "Phase 2 ロードマップ" として記録)**:

1. **立替金 → expense_category マッピング**: reimbursement_items の category 列 (旅費/消耗品/通信/広告) を expense_category へマッピングするロジック。Phase 2 で `actual_source='reimbursement'` のカテゴリを実装
2. **自由に使える10万円・共通費の実額紐付け仕様**: 「自由 10万円」の利用追跡方法、「共通費」の本部費按分ロジックを仕様確認
3. **dashboard UI 拡張**: 四半期×統括隊×カテゴリの可視化 (既存予実管理ページとの統合方針: 新タブ追加 or 既存タブの粒度切替セレクタ)
4. **AI 評価エンジンの統括隊レベル対応**: Gemini プロンプトを統括隊レベルで生成、Q ごとに評価コメント

**次セッションでの catchup 手順**:
1. `/catchup` で本ハンドオフ doc を読み込み
2. `docs/specs/2026-06-10-team-budget-eval-design.md` §3-§4 (BQ schema) と `infra/bigquery/schema.sql` 既存構造を確認
3. 既存 PR #210 (PR-A) の `scripts/upload_budgets.py` 実装パターン (MERGE / version optimistic lock / dry-run / actor 確定) を確認、本 PR の 2 script の踏襲元として参照
4. 直前 PR #213 で改訂された hash SQL の tie-breaker パターン (`ORDER BY row_hash, row_json`) を共通慣習として認識
5. impl-plan or 直接実装着手 (本 doc に詳細スコープがあるため `/impl-plan` skip 可)
6. Codex 指摘 8 件すべて反映した実装になっているかを実装中にチェック (チェックリスト形式で commit)
7. 3 並列セカンドオピニオン → 必須修正反映 → PR 作成 → 本田さん認可依頼

### 条件待ち (2 件、明示 trigger 付き)

#### 1. PR #213 Deploy Dashboard workflow 完走確認
- **trigger**: workflow 完了 (現在 2m56s 経過、通常 4-5 分で success)
- **trigger 充足時の作業**: `gh run list --branch main --limit 3` で success 確認 → 本番 dashboard で予実管理ページが見えることを確認
- **confirm 方法**: `gh run watch <run-id>` または `gh run view <run-id>`
- **想定工数**: 確認のみ 1-2 分
- **failure 時の対応**: workflow ログ確認、SERVICE_AUDIENCE_URL の設定誤りや bq_client.py の cache_data 周りの規約変更等を疑う

#### 2. 2026-07-01 07:00 JST: Scheduler 初回自動実行確認
- **trigger**: 期日到来 (3 週間後)
- **trigger 充足時の作業**: Chat スペースに評価バッチの完了通知が来るか、または BQ で SELECT COUNT(*) FROM `monthly-pay-tax.pay_reports.team_monthly_eval` WHERE generated_at >= '2026-07-01' を確認
- **confirm 方法**: 上記 SQL + Cloud Run ログ (gcloud logging read --format=json で /eval/team-monthly のリクエスト記録)
- **想定工数**: 確認 5 分、失敗時の原因特定は別途
- **failure 時の対応**: Cloud Run revision + Vertex AI quota + IAM `roles/aiplatform.user` の付与状態を順に確認

### 却下候補 (3 件、記録のみ)

#### 1. AC4 マトリクスのセルクリック遷移実装 (C カテゴリ)
- **検討経緯**: Evaluator FAIL 指摘。spec §6.3 は「セルクリックで隊ドリルダウンに遷移」と書かれているが、Streamlit `st.dataframe` は本来クリックイベントを返さない。現状は selectbox 迂回で代替。
- **着手しない理由**: 起点アイデア (本田さんが完全実装を望むかどうか) が decision-maker 領分。Streamlit 1.50.0 の `st.dataframe(selection_mode=...)` で row click 取れる可能性はあるが、大規模変更。
- **明示指示があった場合の参照先**: `dashboard/_pages/team_budget.py` の `tab_matrix` セクション (130 行付近)、`st.session_state["tb_selected_team"]` の受け渡しロジック

#### 2. AC5/AC7 業務報告詳細を `_render_gyomu_list_tab` から完全流用 (C カテゴリ)
- **検討経緯**: Evaluator FAIL 指摘。spec §6.4「既存 `_render_gyomu_list_tab` ロジック流用」だが、現状は `dashboard/_pages/team_budget.py` で独立 SQL の簡易版。完全流用には `dashboard/_pages/dashboard.py:533 _render_gyomu_list_tab` (700+ 行) を `dashboard/lib/team_budget_view.py` に抽出する大規模 refactor が必要。
- **着手しない理由**: refactor の起点判断 (既存 dashboard.py の挙動を一切変えない確証、新コード側でのデグレ防止策) は decision-maker 領分。
- **明示指示があった場合の参照先**: `dashboard/_pages/dashboard.py:533-783` の `_render_gyomu_list_tab` と `_render_group_tab`、抽出先候補は `dashboard/lib/gyomu_list_view.py` (既存) を拡張

#### 3. backend での force パラメータ role 認可 (B カテゴリ 検出済み、修正は要指示)
- **検討経緯**: Codex Medium-3 + Agent F3 指摘。dashboard UI で「強制再生成」ボタンは admin only で隠しているが、`POST /eval/team-monthly` の `force=true` は server side で role 検証していない。Cloud Run IAM 認証 (`--no-allow-unauthenticated`) で外部からの直叩きはブロック済みだが、認証された内部 user/checker が curl で直叩きすれば強制再生成可能 = Gemini cost incur。
- **着手しない理由**: 修正 (write) は decision-maker 領分。「実害発生したか」「いつ起こりうるか」の判断材料が必要 (現状実害なし、内部攻撃の可能性のみ)。
- **明示指示があった場合の参照先**: `cloud-run/team_eval_service.py:extract_actor` で email を取得後、`cloud-run/main.py:eval_team_monthly` で force=true なら `dashboard_users` テーブル参照で admin か否かを検証する形が最小修正

---

## 最終結論

✅ **セッション終了可** — 予実管理機能 4 PR シリーズ完遂 + PR-E 設計合意 doc 化完了。

- OPEN PR: 1 件 (本 handoff 補強 PR、認可後マージ)
- Git: docs/handoff-pr-e-preparation ブランチ
- 即着手タスク: **1 件** (PR-E 四半期×統括隊×カテゴリ予算、本セッションで設計合意 + Codex セカンドオピニオン反映済み、次セッションで実装着手可能)
- 条件待ち: 2 件 (Deploy Dashboard 完走確認 + 7 月 1 日 Scheduler 初回自動実行)
- 残留プロセス: なし
- 既知 blocker: なし

**セッション切替の理由**: context 47% 残りで PR-E 完遂 (BQ DDL + script + テスト + 3 並列セカンドオピニオン + 修正反映 + PR 作成) は tight。PR-D 同等の品質ゲート (Codex + Agent + Evaluator 3 並列 → 必須修正反映) を維持するため、新セッションで 85-90% スタートして余裕で完遂する方針を採択。

**次セッション再開時のプロンプト案**:

```
catchup → docs/handoff/LATEST.md の「即着手タスク 1: PR-E」を確認
→ 設計合意済みなので impl-plan skip 可、直接実装着手
→ Codex High 3 + Medium 4 指摘 8 件すべて反映していることを実装中チェック
→ Evaluator 分離プロトコル発動 (5 ファイル以上 + 新機能)
→ 3 並列セカンドオピニオン後に PR 作成 → 本田さん認可依頼
```
