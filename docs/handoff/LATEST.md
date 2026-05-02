# ハンドオフメモ - monthly-pay-tax

**更新日**: 2026-05-02（GitHub Actions CI/CD 導入完了、初回自動デプロイ検証済み）
**フェーズ**: WAM助成金対応 **技術側完了** + **CI/CD 自動デプロイ稼働中**
**最新デプロイ**: Collector rev **00025-rxr** + Dashboard rev **00248-rjl**（両方とも GitHub Actions 経由）
**Cloud Run設定**: 2026-04-07 `--no-cpu-throttling --max-instances=3` 適用済み（ADR 0004）
**CI/CD**: ADR-0006、main push + パスフィルタで自動デプロイ、`workflow_dispatch` で手動実行可
**テストスイート**: Dashboard **307** + Cloud Run 52 = **359テスト全PASS**（CI 上でも自動実行）

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

CI/CD 導入は完了。次は積み残し Issue の triage と着手:

| Issue | 内容 | ラベル |
|-------|------|--------|
| #106 | collector が `=HYPERLINK()` の URL を取得できていない（receipt_url 無効） | bug, P2 |
| #93 | app_gyomu_reports / app_hojo_reports テーブル作成（基盤整備） | enhancement, P2 |
| #94 | Cloud Run コスト監視 — ADR 0004 効果測定 | P2 |
| #58 | WAM要件④: 支払調書作成ツールへの連携（Want） | enhancement, P2 |
| #54 | WAM Phase 0: ステークホルダー確認事項（参考情報） | documentation, P2 |

優先候補: bug ラベル付きの **#106** が最優先。次に基盤整備 #93。
WAM 系（#58, #54）はステークホルダー回答待ちで後回し可。

## Issue Net 変化（本セッション）

- Close 数: 0 件
- 起票数: 0 件
- Net: 0 件

本セッションの作業（PR #119 マージ・デプロイ + CI/CD 4 PR 導入）は機能追加・
インフラ改善であり、Issue Triage 対象の修正・要望ではないため起票なし。
既存 Issue にも触れていないため close もなし。CI/CD 完了後の次セッションで
#106 などに着手することで Net を減らす想定。

## 2026-04-26 ロール権限マトリックス追加 (#117)

architecture.py に新セクション **6.5 ロール権限マトリックス** を追加。
LATEST.md にアドホック記載していた機密度マッピングを恒久ドキュメント化。

### 追加内容
1. **ページ × ロール アクセス可否表**: 7ページ × user/checker/admin
2. **機密情報 × ロール 露出マトリックス**: 各画面・出力ファイルの個人情報露出を可視化（太字で強調）
3. **設計方針**: checker/admin の役割定義、ロール変更時の更新手順

### 効果
- セキュリティレビュー時に「どの情報がどのロールに露出するか」一目で確認可
- ロール設計変更（PR #112→#115 のような）の判断材料が永続化
- 新規メンバー教育用ドキュメントとして機能

ロールバック先: `pay-dashboard-00245-2br`（保持中）

## 2026-04-26 WAM Tab6 を checker ロールにも解放 (#115)

PR #112 で「Tab6 admin 限定」としていた制限を撤廃し、6タブすべて checker/admin 解放に統一。

### 判断根拠
- checker は限定的な担当者ロール
- Tab4 振込CSV / Tab5 支払明細書PDF で **既に氏名・口座情報は checker から取得可能**
- Tab6 解放で追加されるのは住所・カナ氏名・member_id のみ
- 主要個人情報（氏名・口座）が解放済の状態で、住所だけ admin 限定にする実効性は限定的

### 機密度マッピング（最終形）
| 情報 | 露出箇所 | アクセス権 |
|------|---------|----------|
| 氏名（フルネーム） | Tab4 振込CSV / Tab5 PDF / Tab6 CSV | checker / admin |
| 口座情報 | Tab4 振込CSV | checker / admin |
| 住所・カナ氏名 | Tab6 CSV のみ | **checker / admin（本PRで解放）** |
| ニックネーム・金額 | 全タブ | 全ロール（user 含む） |

### 変更
- `wam_monthly.py`: tabs() の role 分岐削除、Tab6 ガード撤去
- `architecture.py` / `help.py` / `CLAUDE.md`: Tab6 admin 限定の注釈削除

ロールバック先: `pay-dashboard-00244-tps`（保持中）

## 2026-04-26 ユーザー管理画面 フィルタ・削除確認ダイアログ追加 (#113)

### フィルタ機能
- ロール（admin/checker/viewer/user）・グループ（source_group）の絞り込み
- 「(個別登録のみ)」選択で source_group が NULL のユーザーを抽出
- 表示件数キャプション「N / 全 M 件」

### 削除確認ダイアログ
- `@st.dialog` ベース（Streamlit 1.55）
- 削除ボタン押下 → モーダル表示 →「削除を実行（OK）」or「キャンセル」
- ESC/×で閉じても session_state に残らない**ワンショット消費パターン**を採用（レビュー指摘 silent-failure-hunter 対応）

### テスト追加
- `TestFilterUsers` クラス 9テスト（ロール/グループ単独・複合・(個別登録のみ)・元 DataFrame 不変）
- Dashboard tests: 259 → **268 passed** (+9)

ロールバック先: `pay-dashboard-00243-zr7`（保持中）

## 2026-04-26 WAM立替金確認を checker 解放 (#112)

WAM立替金確認ページを admin 限定 → **checker/admin 解放**（β案）。
※ 同日 #115 で Tab6 も追加解放され、最終的に6タブすべて checker/admin 可となった。

### Tab1〜Tab5: checker/admin 表示（#112）
- PJ別サマリー / メンバー別明細 / 領収書添付状況 / 月別報酬・振込確認 / 支払明細書

### Tab6: 当初 admin 限定 → #115 で checker 解放
- 年間支払調書データ

### 二重防御（現行）
1. ナビゲーションレベル: `app.py` で `wam_monthly` を `checker_pages` に配置
2. ページレベル: `require_checker(email, role)`

### ドキュメント同期
- `architecture.py` Mermaid: ロール表記更新（Tab1-5 / Tab6 分離）
- `help.py`: ページバッジ「checker / admin」、FAQ ロール説明更新
- `CLAUDE.md`: ページ構成テーブル・ファイル説明更新

ロールバック先: `pay-dashboard-00243-zr7`（保持中）

## 2026-04-26 architecture/help 同期 (#110)

未マージのまま残っていた `docs/add-wam-help-guide` (c423875) の内容を取り込み、
今回セッションの変更（PR #103 Tab2 URL列追加）も反映。

- `architecture.py`: ページ数表記 7→8（実体と整合）、ラベル `支払明細書PDF → 支払明細書`
- `help.py`: WAM立替金確認の操作ガイド・FAQ・用語集を追加
  + メンバー別明細タブの説明に「立替金シートURL」「URLクリックで原本シート表示」を追記
- `docs/add-wam-help-guide` ブランチは本PRで吸収のため delete 済み

## 2026-04-26 admin_settings BQテーブル一覧拡充 (#108)

admin_settings ページの「BigQuery テーブル情報」一覧に CLAUDE.md 記載の10テーブル全て表示。
立替金・タダメンマスタ等のデータ収録タイミングが admin から確認可能に。

追加テーブル:
- `reimbursement_items`（立替金シート、約2,300行、毎朝06:21更新）
- `member_master`（タダメンMマスタ、244件、毎朝06:21更新）
- `wam_target_projects`（WAM対象PJマスタ、4件、変更時のみ）

ロールバック先: `pay-dashboard-00239-j5z` / `00238-4cx`（保持中）

## 2026-04-25 WAM Tab2 リンク列追加 (#103) → 領収書列削除 (#105)

### #103: URL/領収書 LinkColumn 追加
WAM立替金確認 Tab2「メンバー別明細」に「URL」（立替金シート）と「領収書」の2列を追加し、
`st.column_config.LinkColumn(display_text="開く")` でクリッカブル化。
- 新規 `dashboard/lib/wam_helpers.py`: Tab2 の DF 構築ヘルパーを分離（test/prod 共通化）
- CSV出力は既存仕様維持（URL列を含めない）

### #105: 領収書列を暫定削除（バグ修正）
admin 動作確認で「領収書リンクが機能しない」と判明。
原因: collector が `=HYPERLINK("url", "ファイル名")` の `formattedValue` を取得しており、
BQ `receipt_url` には **ファイル名のみ** が入っていた（URL は失われている）。

→ Tab2 から領収書列を削除（暫定）。`source_url`（立替金シート、正規URL）は維持。

### 中期対応: Issue #106
collector で `=HYPERLINK()` の URL を取得するロジック追加（推奨: Sheets API `cellData.hyperlink` 属性）。
完了後に Tab2 に領収書列を再追加して復活。

ロールバック先: `pay-dashboard-00238-4cx` / `pay-dashboard-00237-9xs`（保持中）

## 2026-04-24 行政事業分類分割（ケアプー/神奈川DX）

業務委託費分析タブの「行政事業」分類を、スポンサーフィールドを基に2分類に分割。
- `sponsor == "神奈川県DX"` → 「行政事業（神奈川DX）」
- その他（ケアプー事業・移動手当等）→ 「行政事業（ケアプー：ケアプランデータ連携システムを広め隊）」
- 対象ファイル: `dashboard/_pages/dashboard.py`（_COST_GROUP_MAP / _COST_GROUP_EXCLUDE_NONPROFIT / _COST_COLOR_DOMAIN + Tab5振り替えロジック）

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
| #94 | Cloud Run コスト監視 | P2 | なし |
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
