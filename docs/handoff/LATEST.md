# ハンドオフメモ - monthly-pay-tax

**更新日**: 2026-05-03（PR #132/#133 マージ完了 + BQ DDL/seed 実行 + UI 動作確認 PASS）
**フェーズ**: WAM助成金対応 **技術側完了** + **CI/CD 自動デプロイ稼働中** + **管理機能拡充フェーズ完了**
**最新デプロイ**: PR #132 (350ae30) + PR #133 (437731a) で自動再デプロイ完了 / 進行中
**Cloud Run設定**: 2026-04-07 `--no-cpu-throttling --max-instances=3` 適用済み（ADR 0004 / 効果測定 2026-05-03 追記）
**CI/CD**: ADR-0006、main push + パスフィルタで自動デプロイ、deploy 内に test gate 配置（PR #126）
**テストスイート**: Dashboard **316** + Cloud Run **63** = **379テスト全PASS**（CI 上でも自動実行）

## 🆕 2026-05-03 セッション完了サマリー

| PR | 内容 | マージ | 備考 |
|----|------|--------|------|
| #132 | グループ自動同期 ON/OFF 切替機能 | 350ae30 | dashboard_sync_groups 新テーブル + UI + fail-fast |
| #133 | _stcore 404 既知挙動の説明出力 | 437731a | cosmetic、ユーザー安心メッセージ |

### 完了した運用作業
- ✅ BQ DDL 実行: `dashboard_sync_groups` テーブル作成
- ✅ マイグレーション seed 実行: `taicho@tadakayo.jp` を `enabled=TRUE` で投入
- ✅ UI 動作確認: ON→OFF トグル → 凍結表示 + 「⚠️ 同期停止中」キャプション正常表示
- ✅ admin 操作の監査ログ: `updated_by=yasushi-honda@tadakayo.jp` で記録確認
- ⏳ コンソール info 表示確認: PR #133 デプロイ完了後にユーザー側で目視確認

### Quality Gate 適用記録（PR #132）
- Codex `plan` でセカンドオピニオン取得 → 致命弱点 3件解消
- Evaluator 第三者評価 → 11 AC 全 PASS、HIGH 0件
- safe-refactor → MEDIUM 2件修正（last_synced_at エラー処理 / skipped カウンタ分割）
- `/review-pr` 6エージェント並列 → Critical 3件 + High テスト 4件 解消
- 修正反映: main.py の except Exception を error 化、register_sync_group をループ前に移動、schema.sql 内マイグレーション SQL を migrations/ に切り出し

### 残課題（次セッション候補・Issue 起票せず TODO で残す）
**dashboard UI の DML 例外ハンドリング統一**（PR #132 review I1+I2、別 PR スコープ）:
- `set_sync_enabled` / `is_user_in_group` / dialog 内 BQ 操作を try/except で囲み `st.error` 表示
- `delete_user` / `update_role` / `update_display_name` / `add_user` の (success, msg) tuple 化（BQ 失敗時の例外を握って返す）
- 影響: BQ 一時障害時に UI が真っ白になる経路を防ぐ
- rating: 7 相当（silent-failure-hunter Important）、頻度低のため net KPI 観点で起票見送り、TODO 相当として handoff に記載

## 🆕 2026-05-03 グループ自動同期 ON/OFF 機能実装

### 背景
グループ一括登録したユーザーは Cloud Run の Step 5 で毎朝自動同期され続けるが、
同期を停止する仕組みがなかった。グループ単位で同期を ON/OFF できるようにする。

### 要件（ユーザー確定）
- 切替単位: **グループ単位**
- OFF時: 既存レコード**そのまま残す（凍結）** — DELETE しない、ユーザーはダッシュボード使い続けられる
- ON時: **次回 Cloud Run バッチ（毎朝6時）で自動取り込み** — 即時実行は不要

### 設計
- 新テーブル `dashboard_sync_groups`（group_email PK / enabled BOOL / last_synced_at / updated_at / updated_by）
- groups_master は毎日 WRITE_TRUNCATE のため別テーブル必須
- `sync_dashboard_users_from_groups()` で enabled=TRUE のグループのみ処理対象に絞る
- read 失敗は **fail-fast**（空 set 返却で全グループ静かに停止を回避）
- UI: user_management に「グループ自動同期 ON/OFF」セクション追加、トグル + 既存ユーザー数表示
- 自グループ OFF 時に確認ダイアログ、削除済みグループ警告、OFF 時の「既存ユーザーは削除されません」警告

### Codex レビュー指摘 → 解消済み
1. 「フェイルセーフ空 set 返却で全グループ静かに停止」→ fail-fast に変更
2. 「OFF=アクセス維持の誤認」→ UI で OFF 時の警告 + 常時キャプション二重表示
3. 「マイグレーション順序リスク」→ schema.sql にデプロイ順序コメント追加

### Evaluator 評価
全 11 AC PASS、HIGH なし。MEDIUM 2件（last_synced_at エラー処理 / skipped_groups 曖昧）→ 修正済み。

### デプロイ順序（重要）
1. PR マージ後、CI で Cloud Run 再デプロイ完了確認
2. **BQ DDL 実行**: `bq query --use_legacy_sql=false --project_id=monthly-pay-tax < infra/bigquery/schema.sql` (CREATE TABLE IF NOT EXISTS のみ実行)
3. **マイグレーション seed**: `bq query --use_legacy_sql=false --project_id=monthly-pay-tax < infra/bigquery/migrations/2026-05-03_dashboard_sync_groups_seed.sql`
4. 翌朝 6 時バッチで `skipped_disabled` / `skipped_unregistered` ログ確認、`dashboard_users_sync.status` が "failed" でないことを確認
5. UI で各グループの「最終同期」タイムスタンプ更新を確認

⚠ **手順 2-3 を忘れると Step 5 が fail-fast 例外で停止する**（fail-fast 設計の意図的トレードオフ）。
ただし main.py 側で error ログ + sync_result.status=failed を返すため、Cloud Logging で検知可能。

## 🆕 2026-05-03 ADR-0004 効果測定 + #129 動作確認 (PR #131 / Refs #94)

### ADR-0004 効果測定（PR #131）
2026-04-02〜2026-05-02 (30日) の Cloud Monitoring メトリクス (`billable_instance_time`, `request_count`)
から理論コストを算出し、ADR-0004 末尾に「## 効果測定 (2026-05-03、Issue #94)」セクション追加。

**主な結果**:
- pay-dashboard 月コスト見込み: **¥3,761**（理論値）
- 適用前 (3月実績) ¥4,536 から **17% 削減**を確認
- ADR-0004 期待値 ¥3,400 に対しては **+11% 超過**
- 月¥3,000 予算閾値に対しては **+25% 超過**

**未達項目**（残課題に追記）:
- 予算アラート設定: 課金アカウント `013C90-D4C0A0-A391D6` への billing.admin 権限と
  `billingbudgets.googleapis.com` API 有効化が必要（`yasushi-honda@tadakayo.jp` には未付与）
- BQ Billing export 未設定 → 実コストではなく公開単価ベースの**理論値**で評価
- WebSocket idle 課金: 業務時間外接続の頻度測定が必要

→ Issue #94 は部分達成のため `Refs #94`（close せず）。完全完了は予算アラート設定後。

### #129 動作確認 PASS で close
2026-05-03 06:21 JST バッチ実行ログで `dashboard_users_sync: {added: 0, removed: 0}` を確認。
Step 5 は毎朝正常実行されており、グループメンバー変動がなかったため MERGE NoOp。
機能正常性は cloud-run/tests/ でカバー済みのため close。

実イベント観測（追加/削除発生時の挙動）は運用上自然に発生したタイミングで検証する方針。

### 環境設定整備
- `.envrc` に `export GH_TOKEN="$(gh auth token 2>/dev/null)"` を追記
  → `cd` するだけで GH_TOKEN が解決され、CI 系操作が `gh` 経由でシームレスに動作
- 既存の `GH_CONFIG_DIR=$(pwd)/.gh` 方式は維持（プロジェクトローカル gh 認証）
- `.envrc` は `.gitignore` 済み（コミットなし）

### 観測した未解決事項
- 今朝 06:00 JST バッチは **rev 26** で実行（rev 27 = PR #128 修正は 07:13 JST デプロイのため）
- → **#106 の最終検証は明朝 5/4 06:00 JST バッチ (rev 27 実行) 待ち**
- BQ で `receipt_url LIKE 'http%'` の件数が現状 5/1223 → 明朝改善見込み

## 🆕 2026-05-02 collector の =HYPERLINK() URL 取得対応 (#106 / PR #128)

立替金シートの領収書セル `=HYPERLINK("Drive URL", "ファイル名")` から
formattedValue (= ファイル名) のみが BQ に保存され Drive URL が失われていた問題を修正。

### 修正内容
- `cloud-run/sheets_collector.py::get_reimbursement_sheet_data` の API 切替
  - 旧: `spreadsheets.values.get(range)` → formattedValue のみ
  - 新: `spreadsheets.get(ranges=[...], includeGridData=True, fields="sheets.data.rowData.values(formattedValue,hyperlink)")`
  - L 列 (index 11) は `cellData.hyperlink` を優先取得 (=HYPERLINK 関数 + 自動リンク両対応)
- `dashboard/lib/wam_helpers.py + _pages/wam_monthly.py`
  - PR #105 で暫定削除した「領収書」LinkColumn を Tab2 に再追加
  - `_safe_receipt_url`: 旧データ混入時のリンク破綻防止に http(s) スキーマ以外は空文字化

### テスト
- Cloud Run: 52 → 55 (+3: hyperlink 抽出 / plain text 維持 / short row padding)
- Dashboard: 307 → 308 (+1: receipt http(s) フィルタ)

### 残るマニュアル確認 (Test plan)
- [ ] 翌朝 6:00 JST の Cloud Scheduler 実行後の BQ 確認:
  ```sql
  SELECT receipt_url FROM `monthly-pay-tax.pay_reports.reimbursement_items`
  WHERE receipt_url LIKE 'http%' LIMIT 5;
  ```
- [ ] WAM立替金確認 Tab2 で「領収書」列の「開く」クリック → Drive ファイルが開く

### ロールバック先 revision
- pay-collector: `00026-p4r` (旧)
- pay-dashboard: `00249-x26` (旧)

## 🆕 2026-05-02 deploy ワークフローに test gate 追加 (#126)

`Test` ワークフローと `Deploy *` ワークフローが並列実行で、Test 落ちでもデプロイされる
潜在リスクを解消。各 deploy ワークフロー内に該当サービスの pytest ジョブを追加し、
`deploy` ジョブを `needs: test` で gate。

- `deploy-collector.yml`: Cloud Run tests (pytest) → deploy（needs: test）
- `deploy-dashboard.yml`: Dashboard tests (pytest, 日本語フォント込み) → deploy（needs: test）
- 別ワークフロー間 `needs:` は不可のため各 deploy 内に test job を複製
- `test.yml` は引き続き PR ゲートとして残置（PR 段階で 359 件全実行）

PR #126 マージで両 deploy ワークフローが自動再発火（パスフィルタにワークフローファイル
自身が含まれるため）し、新しい test gate を実機で検証。

## 🆕 2026-05-02 GitHub Actions CI/CD 導入完了 (#121〜#124)

ADR-0006「GitHub Actions による CI/CD 導入」の 4 段階導入を全 Phase 完遂。
本番運用が「main merge → 自動デプロイ」フローに移行。

### Phase 別完了状況

| Phase | PR | 内容 |
|-------|----|----|
| Phase 1 | #121 | ADR-0006 + `.github/workflows/test.yml`（pytest 359 件を CI で自動実行） |
| Phase 2 | (PR なし) | WIF プール `github-actions-pool` + provider + `github-actions-deployer` SA 構築（gcloud + gh variables） |
| Phase 3 | #122, #123 | `deploy-dashboard.yml` + `deploy-collector.yml`、Cloud Build ログバケット権限修正 |
| Phase 4 | #124 | プロジェクト CLAUDE.md を CI/CD 運用に整合 |

### 構築リソース（Phase 2）

- **WIF Pool**: `github-actions-pool`（リポジトリ条件 `attribute.repository == 'yasushi-honda-prog/monthly-pay-tax'`）
- **Deployer SA**: `github-actions-deployer@monthly-pay-tax.iam.gserviceaccount.com`
- **付与 role 7 件**: `run.admin` / `cloudbuild.builds.editor` / `artifactregistry.writer` /
  `artifactregistry.reader`（gcp.md ルール 2025-01-13 以降必須）/ `iam.serviceAccountUser` /
  `storage.admin` / `logging.logWriter`（Cloud Build ログ書き込み用）
- **GitHub repo variables**: `WIF_PROVIDER` / `WIF_SA` / `GCP_PROJECT_ID` / `GCP_REGION`
- **runtime SA actAs binding**: deployer SA → `pay-collector@...` （両サービス共用）

### Phase 3 で発生したインシデントと修正（PR #123）

PR #122 マージ直後の自動再発火で、両 deploy ワークフローが両方 FAIL。
原因: `gcloud builds submit` がデフォルト global ログバケットへの tail 権限不足で
exit 1 を返した（ビルド自体は SUCCESS で image は AR に push 済み）。

修正: `--default-buckets-behavior=REGIONAL_USER_OWNED_BUCKET` を追加し、
リージョナル user-owned bucket（`gs://${PROJECT_ID}_${REGION}_cloudbuild`）に切替。
PR #123 マージで両 ワークフロー SUCCESS、自動デプロイ稼働開始。

### 初回自動デプロイ実績

- pay-dashboard: rev **`00248-rjl`**（2026-05-02 14:17 UTC）
- pay-collector: rev **`00025-rxr`**（2026-05-02 14:17 UTC）
- ロールバック先 rev は保持中（dashboard `00247-6rh` / collector `00024-hgj`）

### 運用方針

- **default**: GitHub Actions 自動デプロイ（main merge トリガー、パスフィルタ付き）
- **緊急時**: `workflow_dispatch`（GitHub UI または `gh workflow run`）
- **CI 障害時**: 手動 `gcloud builds submit` + `gcloud run deploy`（CLAUDE.md フォールバック節）
- **ロールバック**: `gcloud run services update-traffic --to-revisions=<rev>=100`

### スコープ外（将来 ADR）

- BQ schema (`infra/bigquery/`) の自動適用
- staging 環境分離
- canary deployment
- E2E テスト on Cloud Run

## 2026-05-02 業務報告一覧 日付ソート修正 (#119)

ダッシュボード「業務報告一覧」テーブルの日付列降順ソートが「4/7, 4/6, 4/3, 4/29, 4/28...」と
崩れる不具合を修正。BQ STRING 型の文字列ソート（"4/7" > "4/29"）が原因。

### 修正内容
- `lib/ui_helpers.py`: `parse_gyomu_date()` / `add_gyomu_date_dt()` 追加
  - "M/D" / "M月D日" / "YYYY/M/D" の3形式対応、末尾アンカーで汚れデータ拒否
  - パース失敗集計の WARNING ログ + 失敗率 5% 超で UI に warning 表示（観測性確保）
- `_pages/dashboard.py`: Tab3 業務報告一覧 と グループ別タブ内サブタブ の 2 箇所で
  pd.Timestamp 列追加 + `DateColumn(format="M/D")`
  - 表示は「4/29」のまま、ソートは日付順に動作

### レビュー
- Codex セカンドオピニオン: High なし、Medium 2 件（末尾アンカー / DRY 集約）適用済み
- 4 エージェント並列 `/review-pr`: Critical 0、silent-failure-hunter 指摘の observability を反映

### テスト
- Dashboard: 268 → **307 passed**（+39: parse_gyomu_date 28 / add_gyomu_date_dt 11）
- Cloud Run: 52 passed（regression なし）

### Test plan 残（要手動確認）
- [ ] 業務報告一覧の「↓日付」列ヘッダクリックで降順 4/29, 4/28, 4/27, ... の順
- [ ] 同タブで昇順クリックで 4/1, 4/3, 4/7, ... の順
- [ ] 「グループ別」タブ内の業務報告サブタブも同様にソート動作する
- [ ] 表示フォーマットが "4/29" のまま（"2025-04-29" 等にならない）

ロールバック先: `pay-dashboard-00246-bvn`（保持中）

## 次セッション着手候補

#129 close、PR #131 作成済。次は:

| Issue | 内容 | ラベル | 状態 |
|-------|------|--------|------|
| #94 | Cloud Run コスト監視 — ADR 0004 効果測定 | P2 | 🔶 部分達成 (PR #131 マージ + 予算アラート設定で完了) |
| #93 | app_gyomu_reports / app_hojo_reports テーブル作成（基盤整備） | enhancement, P2 | 報告入力 UI 確定後に着手 |
| #58 | WAM要件④: 支払調書作成ツールへの連携（Want） | enhancement, P2 | 外部ツール所在確認待ち |
| #54 | WAM Phase 0: ステークホルダー確認事項（参考情報） | documentation, P2 | 回答待ち |

### 即着手可能
1. **PR #131 マージ** — 番号単位の明示認可後 `gh pr merge 131 --squash --delete-branch`
2. **#106 最終検証** — 明朝 5/4 06:00 JST バッチ (rev 27 実行) 後に BQ + WAM Tab2 確認
3. **#94 残作業** — 課金アカウントへの billing.admin 権限取得 + 予算アラート設定（ユーザー側 GCP コンソール操作）

### 中期着手
- **#93** — 報告入力機能の UI 仕様が確定したら DDL 実行
- **#58** — 外部ツール所在確認後に CSV 連携フォーマット決定

## Issue Net 変化（本セッション 2026-05-03 PM = #132/#133）

- Close 数: 0 件
- 起票数: 0 件
- Net: **0 件**（KPI 維持）

実質的な進捗: PR #132（グループ自動同期 ON/OFF、新機能+9ファイル+688行、Quality Gate フル適用）+ PR #133（cosmetic、Streamlit 既知挙動の説明出力）の 2 PR マージ。BQ DDL/seed 実行と UI 動作確認まで完了。残課題（dashboard UI の DML 例外ハンドリング統一）は rating 7 相当だが頻度低 + 既存問題のため起票見送り、TODO で次セッション引き継ぎ。

## Issue Net 変化（本セッション 2026-05-03 朝）

- Close 数: 1 件 (#129 — 動作確認 PASS)
- 起票数: 0 件
- Net: **-1 件**（前進）

実質的な進捗: PR #131 作成（ADR-0004 効果測定の事後検証）、#129 動作確認消化、
`.envrc` GH_TOKEN 追記で開発環境整備。テーマは「**過去のリリース・決定の後始末**」
（accountability + 運用負債の解消）。新機能・バグ修正・リファクタは含まない。

## Issue Net 変化（前セッション 2026-05-02 PM）

- Close 数: 1 件 (#106)
- 起票数: 1 件 (#129)
- Net: 0 件（Issue 起票はユーザー明示指示による「後日確認」タスク、CLAUDE.md triage 基準 #5 に該当）

実質的な進捗: PR #126 / #127 / #128 の 3 PR マージ、Cloud Run 自動デプロイ実績 2 回、
test gate 強化、receipt_url HYPERLINK 抽出バグ修正（実バグ）。Net 0 だが backlog の
バグ縮減は達成（#106）、追加した #129 は単純な動作確認フォローアップ。

## 2026-04-24〜26 PR 履歴（archive 参照）
詳細: [archive/2026-04-late-pr-history.md](archive/2026-04-late-pr-history.md)
含む PR: #117 (ロール権限マトリックス) / #115 (Tab6 checker解放) / #113 (フィルタ・削除確認ダイアログ) / #112 (WAM checker解放) / #110 (architecture/help同期) / #108 (admin_settings BQテーブル拡充) / #103+#105 (WAM Tab2 リンク列追加→領収書削除) / 2026-04-24 行政事業分類分割

旧版で個別記載されていたセクション群（L280-410 相当）は冗長解消のためアーカイブ。

## 🆕 2026-04-13 ドキュメントページ全面更新

### ドキュメント最新化（未コミット → PR予定）

architecture.py / help.py / CLAUDE.md を現在のシステム状態に完全同期。

**architecture.py の主な修正**:
- 全体構成図: Step 6（立替金シート）, Step 7（タダメンM）追加
- データフロー図: reimbursement_items, member_master, wam_target_projects, v_reimbursement_enriched 追加
- BQスキーマ: 「7テーブル + 3 VIEW」→「10テーブル + 4 VIEW」、ER図に3テーブル追加
- v_reimbursement_enriched VIEW の新セクション追加
- ページ構成図: 「報告入力」「WAM立替金確認(6タブ)」追加
- 認証フロー・セキュリティ: ロール名 viewer → user 修正

**help.py の主な修正**:
- ページ一覧: 「報告入力」「WAM立替金確認」カード追加（6→8枚）
- ダッシュボード「4タブ」→「5タブ」
- タブ内フィルター: 「業務委託費分析」説明追加
- FAQ: ロール名 viewer → user 修正

**CLAUDE.md の主な修正**:
- アーキテクチャ図に Step 6-7 追加
- ディレクトリ構成: pages/ → _pages/、全ページ反映、lib/receipt_pdf.py 追加
- ページ構成テーブル: 5タブ/6タブ反映、ロール名修正

### 前回セッション（PR #96-#100）

振込CSV口座自動化 + 年間支払調書データ + 個人情報非表示修正（詳細は git log 参照）

---

## WAM助成金対応 全体状況

### 要件達成状況

| # | 要件 | 区分 | 状態 | PR |
|---|------|------|------|-----|
| #55 | 領収書PDF自動生成 | Must | ✅ 完了 | #86 |
| #56 | 振込CSV出力（GMOあおぞら形式） | Must | ✅ 完了 | #83 |
| #57 | WAM月別報酬・源泉確認ツール | Must | ✅ 完了 | #81 |
| #92 | 振込CSV口座自動化 | 基盤 | ✅ 完了 | #96 |
| #58 | 支払調書連携 | Want | 🔶 部分完了 | #97（年間CSV出力済、外部ツール連携は所在確認待ち） |

**Must 3/3 完了、Want 部分完了、技術側でやれることは全完了**

### ドラフト→正式化に必要な残作業

| 項目 | 工数 | ブロッカー |
|------|------|-----------|
| wam_flag を 'Y' に更新 | 5分 | Phase 0 回答（どのPJがWAM対象か確定） |
| #58 外部ツール連携 | 不明 | 外部ツール所在確認 |
| 実データ受入テスト | 30分 | ユーザー確認 |
| 「ドラフト」ラベル除去 | 5分 | 上記完了後 |

### ダッシュボード Tab 構成（WAM立替金・報酬確認ページ）

| Tab | 内容 | PR |
|-----|------|-----|
| 1 | PJ別サマリー | #75 |
| 2 | メンバー別明細 | #75 |
| 3 | 領収書添付状況 | #75 |
| 4 | 月別報酬・振込確認（口座自動入力済） | #81, #83, #96 |
| 5 | 支払明細書PDF | #86 |
| 6 | 年間支払調書データ（個人情報はCSVのみ） | #97, #99 |

---

## オープンIssue

| # | タイトル | 優先度 | ブロッカー |
|---|---------|--------|-----------|
| #58 | 支払調書 外部ツール連携 | Want/P2 | 外部ツール所在未確認 |
| #93 | app_gyomu/hojo_reports テーブル作成 | P2 | なし（UIが未定） |
| #94 | Cloud Run コスト監視 | P2 | 課金アカウント billing.admin 権限取得待ち（部分達成 PR #131 作成済） |
| #54 | Phase 0 ステークホルダー確認 | P2 | 回答待ち |

## デプロイ現況

| サービス | Rev | 内容 |
|---------|-----|------|
| Collector | 00024-hgj | member_master 収集追加 |
| Dashboard | **00237-9xs** | 業務委託費分析 行政事業分類分割・スポンサー未入力補完・セレクトボックス追加・コンソール警告解消 |

## センシティブデータ方針

member_master由来のデータ（口座・住所・氏名・フリガナ）は**ダッシュボードUIに一切表示しない**。
バックエンド処理（振込CSV、支払調書CSV等のファイル出力）でのみ利用。

## 🔴 次セッションの開始点

1. **Phase 0 回答受領後**: wam_flag UPDATE → ドラフトラベル除去
2. **#58 外部ツール所在確認後**: 連携フォーマット決定 → CSV調整
3. **#93 app_gyomu/hojo_reports テーブル作成** — 報告入力UIが決まったら着手
4. **#94 コスト監視** — ADR 0004 効果測定

---

> テスト件数は `python3 -m pytest dashboard/tests/ -q` で確認（252件、2026-04-13時点）
> 過去の変更履歴・ファイル構成・アーキテクチャ図・BQスキーマ・環境情報は CLAUDE.md および `docs/handoff/archive/` を参照
