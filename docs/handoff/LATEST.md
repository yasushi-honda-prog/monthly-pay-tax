# ハンドオフメモ - monthly-pay-tax

**更新日**: 2026-04-12（WAM Must要件 3/3 完了: #55 #56 #57）
**フェーズ**: 6完了 + グループ機能 + グループ一括登録・自動同期 + UX改善 + 数値変換リファクタ + 報告入力機能（デプロイ済み）＋ **WAM助成金対応 Phase 1b 完了 + Must要件 全完了**
**最新デプロイ**: Collector rev 00023-w7s（立替金シート収集対応）+ Dashboard rev 00226-fbg（支払明細書PDF追加）
**Cloud Run設定**: 2026-04-07 `--no-cpu-throttling --max-instances=3` 適用済み（ADR 0004）
**テストスイート**: Dashboard 235 + Cloud Run 42 = **277テスト全PASS**

## 🆕 2026-04-11 WAM助成金事業 要件受領セッション

### 概要

WAM助成金事業（令和8年4月1日〜令和9年3月31日）の経理対応システム改修要件を受領。要件・背景・会議資料・立替金シート構造調査・Phase 0 質問リストを `docs/requirements/` に整理。**コード変更は一切なし、ドキュメントのみ**。

### 追加されたファイル

```
docs/requirements/
├── REQ_20260409_wam-grant-workflow.md          メイン要件 + Phase 1a/1b/2〜5 実装ロードマップ
├── REF_20260408_wam-accounting-issues.md       ヒデスさんの経理課題文書（案1/2/★3）
├── REF_20260409_wam-accounting-mtg.md          4/9 MTG メモ（WAM制度要注意ポイント）
├── REF_20260411_reimbursement-sheet-discovery.md 立替金シート構造調査結果
├── QUESTIONS_20260411_wam-phase0.md            Phase 0 質問リスト（Q-A〜Q-E、全18項目）
├── DRAFT_20260411_yuri-consultation.md         🆕 ゆりさん向け相談下書き（PR #60）
├── DRAFT_20260411_miyaya-reply.md              🆕 ミヤヤさん向け返信下書き（PR #61）
└── DRAFT_20260411_hiros-hides-mtg.md           🆕 ヒロス/ヒデスMTG質問リスト（PR #62）
```

### 🎉 Phase 0 下書き完成: 18/18項目（100%達成、2026-04-11夜）

本セッション後半で、Phase 0 全18項目を解消するための下書きを3本すべて作成・マージ済み:

| PR | 対象 | 項目数（初版） | 項目一覧 |
|----|-----|-------|---------|
| [#60](https://github.com/yasushi-honda-prog/monthly-pay-tax/pull/60) | ゆりさん | 6項目 | Q-E1〜E4, Q-B3, Q-B4 |
| [#61](https://github.com/yasushi-honda-prog/monthly-pay-tax/pull/61) | ミヤヤさん | 8項目 | REQ §4 相談①〜④ + Q-A1〜A4 |
| [#62](https://github.com/yasushi-honda-prog/monthly-pay-tax/pull/62) | ヒロス/ヒデスMTG（45分）| 8項目 | Q-A5, Q-B1/B2, Q-C1〜C3, Q-D1/D2 |

**各下書きの特徴**:
- 選択肢式（回答者の負荷最小化、30分で回答可能な想定）
- 技術調査済みを明示（Playwright調査結果を尊重ベースで記載）
- 推奨案を先出し（議論効率化）
- 回答記録用テンプレート付き（受領後すぐに整理可）

**技術回答サマリー（ミヤヤ下書き PR #61 より）**:
- 要件①: 既存PDFの集約を推奨（新規生成不要）
- 要件②: 新規振込ツール作成を推奨（GMOあおぞら用、既存PayPayと並列モジュール）
- 要件③: 既存 pay-dashboard への新ページ追加を推奨（独立ツール不要）
- 要件④: Want扱いで後回し可（Phase 3）
- 全体: 「入力1本・出力分離」ハイブリッド戦略、ブラスト半径ゼロ

### 📝 2026-04-11 夜（2回目） ADR_0005 適用: GCP側処理完結原則（18→14項目に縮小）

初版の下書きには「既存ツール・シートへの改修依頼」が含まれていた（ゆりさん配布ツールに列追加・プルダウン値追加・年度追加ツール改修など）。技術決裁者ヤススの判断により、**「処理・加工はすべてGCP取得側（pay-collector / BQ / pay-dashboard）で完結させ、既存ツール・シートには一切触らない」** 原則を採択。

**新規追加**: [`docs/adr/0005-wam-gcp-side-processing-principle.md`](../adr/0005-wam-gcp-side-processing-principle.md)

**質問リスト再分類（18項目）**:

| 扱い | 項目数 | 項目 |
|------|--------|------|
| ❌ GCP側で自己解決（質問削除） | 5 | Q-A4（活動分類）, Q-B3（対象PJ）, Q-E1（URL列）, Q-E2（smart chip）, Q-E4（年度追加） |
| ❌ 技術決裁済み（決定事項共有） | 3 | 相談①（PDF集約）, 相談②（振込新規モジュール）, 相談③（既存ダッシュボード拡張） |
| ⭕ ビジネス/会計/運用確認（残す） | 14 | Q-A1/A2/A3/A5, Q-B1/B2/B4, Q-C1/C2/C3, Q-D1/D2, Q-E3, 相談④ |

**下書き修正内容**:

| ファイル | 変更 |
|---------|-----|
| `DRAFT_20260411_yuri-consultation.md` | 6項目 → **2項目**（Q-E3, Q-B4 のみ、改修依頼ゼロ、10分で回答可能） |
| `DRAFT_20260411_miyaya-reply.md` | 8項目 → **4項目**（Q-A1〜A3 + 相談④、相談①②③は「技術決裁済み」として共有） |
| `DRAFT_20260411_hiros-hides-mtg.md` | 変更なし（8項目すべて会計ルール・現物確認で GCP 吸収不可） |
| `QUESTIONS_20260411_wam-phase0.md` | Q-A4/B3/E1/E2/E4 に `✅ GCP側で吸収` マーク追加、優先度マトリクス更新 |

**効果**:
- ゆりさんの作業負荷: 30分 → **10分**
- ミヤヤさんの決裁項目: 8 → **4**
- 既存運用・既存ツールへの改修依頼: **ゼロ**
- ADR として原則を記録し、今後の Phase 1a/1b 設計時にも適用

### 要件サマリー

| # | 要件 | 優先度 |
|---|------|-------|
| ① | 領収書の自動生成・振込一括化（業務委託費＋旅費を合算した1枚PDF＋1振込） | Must |
| ② | 振込データ抽出とCSV出力（GMOあおぞらネット銀行フォーマット、PayPayと別系統） | Must |
| ③ | WAM月別報酬・源泉徴収確認ツール | Must |
| ④ | 支払調書作成ツールへの連携 | Want |

### 重要な技術的発見（Phase 1b 基盤調査）

本セッションで **Playwright経由で Google Drive を調査し、立替金シート周りの完全な構造を把握**:

1. **立替金等入力シートは既に202件配布済み**（作成者: 近藤ゆりさん／GASツール）
   - フォルダID: `1jXs3cbO6gBvgDbotK0ODa9mL4x-iDooI`
   - 配布リストID: `1EYh1MUqP7_i8Ox8Qqn7ZHKTh7MWBiIQCMa3n_4EchkY`
   - タブ名: `入力シート`（全202件で統一）

2. **ヘッダー構造が完全統一（12列）**: 年 / 月日 / **対象PJ** / 分類 / 支払用途 / 支払金額 / 仮払金額 / 利用区間（発/着）/ 訪問目的 / **請求書PDF保存先URL**

3. **対象PJ プルダウンで WAM/非WAM の自動判別が可能**
   - 現状の値: `ケアプーPJ` / `神奈川県PJ` / `経産省PJ` / `その他`
   - 新値 `WAM-出張タダスクPJ` 等を追加するだけで判別成立

4. **既存の pay-collector インフラから立替金シートに到達可能**
   - 業務報告シートの `【月１入力】補助＆立替報告＋月締め` タブの **K3セル** に立替金シートURLが埋め込まれている（配布ツールが自動設置）
   - セル位置はメンバー別（K3/L3/K6/K7/K8/K12/L4/L13）→ 配布リストがセル番地を管理

5. **既存テーブル（gyomu_reports/hojo_reports）への影響なしで統合可能**
   - 新規テーブル: `reimbursement_items`（明細レベル）+ `wam_target_projects`（WAM判定マスタ）
   - 新規VIEW: `v_reimbursement_enriched` + `v_wam_monthly_summary`
   - 既存の分析系・ダッシュボードは無変更

### GitHub Issues（追跡用）

| Issue | 優先度 | 内容 | 状態 |
|-------|-------|------|------|
| [#54](https://github.com/yasushi-honda-prog/monthly-pay-tax/issues/54) | P2 | WAM Phase 0: ステークホルダー確認事項（参考情報） | 参考情報に格下げ |
| [#55](https://github.com/yasushi-honda-prog/monthly-pay-tax/issues/55) | P1 | WAM要件① 領収書の自動生成と振込一括化 (Must) | ✅ **完了** PR #86 |
| [#56](https://github.com/yasushi-honda-prog/monthly-pay-tax/issues/56) | P1 | WAM要件② 振込データ抽出とCSV出力（GMOあおぞら） (Must) | ✅ **完了** PR #83 |
| [#57](https://github.com/yasushi-honda-prog/monthly-pay-tax/issues/57) | P1 | WAM要件③ WAM月別報酬・源泉徴収確認ツール (Must) | ✅ **完了** PR #81 |
| [#58](https://github.com/yasushi-honda-prog/monthly-pay-tax/issues/58) | P2 | WAM要件④ 支払調書作成ツールへの連携 (Want) | 着手可能（後回し可） |

### 🚀 2026-04-11 深夜 方針転換: プロトタイプ駆動 + Phase 1b 実装着手

**重要な方針転換**: 「回答待ち → 実装」ではなく「**先にプロトタイプを作って見せて判断を進める**」方式に転換。回答待ちは発生しない。

#### PR #65（Open）: 立替金シート収集パイプライン

`feat/reimbursement-collection-pipeline` ブランチに実装済み。**main にはまだマージされていない**。

**実装済み（ブランチ上）**:
- `cloud-run/config.py`: REIMBURSEMENT_* 定数、TABLE_COLUMNS 追加
- `cloud-run/sheets_collector.py`: `_get_dwd_credentials(scopes=None)` パラメータ化 + Drive API フォルダ一覧 → nickname 抽出 → 立替金シートデータ取得（5関数追加）
- `cloud-run/main.py`: Step 6 追加（try/except で本体処理に影響なし）
- `infra/bigquery/schema.sql`: `reimbursement_items` + `wam_target_projects` テーブル
- `infra/bigquery/views.sql`: `v_reimbursement_enriched` VIEW（members.nickname JOIN + WAM判定 + 数値化）
- `cloud-run/tests/test_reimbursement_collector.py`: 15テスト新規（全35テスト PASS）

**メンバー紐付け**: スプレッドシート名 `【ニックネーム】委託事業_...` → regex `【(.+?)】` → `members.nickname` で JOIN

**追加の紐付け参考資料（ユーザー情報提供）**:
- 各タダメンの業務報告シート「【月１入力】」タブの L3 付近にスマートチップでリンクあり
- `管理用_ファイルアドレス取得ツール`（`1rOTPfwAX2PVnA-jxObbbDvLfLfjrrnLGqGC5MErigiI`）で管理（完全ではない可能性あり）

### 次セッションの開始点

#### ✅ PR #65 マージ完了 + 実データ調査に基づく修正完了

**PR #65 マージ**（498d314）後、Playwright で立替金シート10件の実データ調査を実施。
3つの重要な事実を発見し、コード修正済み（4afa41a）:

| 発見事項 | 旧値 | 修正後 |
|---------|------|--------|
| タブ名 | `入力シート`（完全一致） | `{0\|1\|2}入力シート`（サフィックスマッチ） |
| データ開始行 | Row 2 | Row 4（Row 3=ヘッダー、Row 4-5=例データ→フィルタ除外） |
| H/I列 | マージセル仮説 | **独立カラム: H=仮払金額, I=利用区間(発)（実データ2,250行で相互排他確認）** |

**テスト**: 42 PASS（既存20 + 立替金収集22）

#### ✅ デプロイ前提条件（全完了、2026-04-12）

1. ✅ **DWD スコープ追加**: `drive.readonly`（Admin Console設定済み）
2. ✅ **Drive API有効化**: `gcloud services enable drive.googleapis.com`
3. ✅ **BQ テーブル作成**: `reimbursement_items` + `wam_target_projects`
4. ✅ **BQ VIEW作成**: `v_reimbursement_enriched`
5. ✅ **Shared Drive対応**: `supportsAllDrives` / `includeItemsFromAllDrives` パラメータ追加（PR #73）
6. ✅ **Collector デプロイ**: rev 00023-w7s（立替金シート収集対応）
7. ✅ **実データ収集検証**: 2,250行、68ニックネーム、5対象PJ

#### 🟢 BQ 実データサマリー（reimbursement_items）

| 指標 | 値 |
|------|-----|
| 総行数 | 2,250 |
| ユニークニックネーム | 68人（members 202人中） |
| 対象PJ | 5種 |
| advance_amount(仮払)あり | 25行 |
| from_station(発駅)あり | 1,335行 |
| 両方にデータ | 0行（相互排他） |
| receipt_url あり | 1,205行 |

#### ✅ WAM立替金確認ページ デプロイ完了（PR #75, rev 00222-fb2）

`dashboard/_pages/wam_monthly.py` 新規追加（admin限定）:
- Tab 1: PJ別サマリー（支払金額・仮払金額集計）
- Tab 2: メンバー別明細（対象PJ・メンバーフィルタ、WAM対象列付き）
- Tab 3: 領収書添付状況（添付率・メンバー別未添付一覧）

テスト: 12テスト新規（Dashboard 210 + Cloud Run 42 = 252テスト全PASS）

#### ✅ wam_target_projects シードデータ投入 + ブラウザ動作確認（2026-04-12 午後）

**wam_target_projects シードデータ**（4件投入）:

| target_project | wam_flag | note |
|----------------|----------|------|
| ケアプーPJ | N | Phase 0回答後にWAM判定を更新 |
| 神奈川県PJ | N | Phase 0回答後にWAM判定を更新 |
| 経産省PJ | N | Phase 0回答後にWAM判定を更新 |
| その他 | N | Phase 0回答後にWAM判定を更新 |

**PM判断**: Phase 0回答前だが、全PJを `wam_flag='N'` で登録。回答後に対象PJのみ `'Y'` に UPDATE するだけで済む。空テーブルのままよりデータフロー検証・デモ価値が高い。

**ブラウザ動作確認結果**（Playwright MCP、管理者アカウント yasushi-honda@tadakayo.jp）:

| テスト項目 | 結果 |
|-----------|------|
| ページアクセス（admin権限） | OK |
| Tab 1: PJ別サマリー | OK |
| Tab 2: メンバー別明細（WAM対象列表示） | OK |
| Tab 3: 領収書添付状況 | OK |
| 年度フィルタ切替（2024/2025/2026） | OK |
| 月フィルタ切替 | OK |
| 対象PJフィルタ（ケアプーPJ等） | OK |
| データ0件時の空表示 | OK（「該当データがありません」） |
| VIEW is_wam 判定（シードデータ反映） | OK（全行false） |
| コンソールエラー | なし（Streamlit内部404のみ、影響なし） |

**Phase 0回答後のWAM判定更新手順**:
```sql
-- WAM対象PJが判明したら1行UPDATEするだけ
UPDATE `monthly-pay-tax.pay_reports.wam_target_projects`
SET wam_flag = 'Y', note = 'WAM助成金対象', ingested_at = CURRENT_TIMESTAMP()
WHERE target_project = 'ケアプーPJ'  -- 実際の対象PJに変更
```

#### ✅ WAM確認ページ UX強化（PR #78, rev 00223-m56, 2026-04-12）

Phase 0回答待ち中の先行準備。wam_flag更新後に即座に活用可能な仕組みを事前構築。

**追加機能**:
- サイドバー: 「WAM対象のみ表示」チェックボックス（is_wamフィルタ）
- Tab 2: CSVダウンロードボタン（明細エクスポート）

**ブラウザ検証結果**（Playwright MCP）:
| テスト項目 | 結果 |
|-----------|------|
| WAMフィルタチェックボックス表示 | OK |
| WAMフィルタON → 0件表示（全wam_flag='N'のため期待通り） | OK |
| CSVダウンロードボタン表示 | OK |
| コンソールエラー | なし |

テスト: Dashboard 213 + Cloud Run 42 = 255テスト全PASS

#### ✅ #57 WAM月別報酬・振込確認タブ追加（PR #81, rev 00224-867, 2026-04-12）

既存wam_monthly.pyにTab 4「月別報酬・振込確認」を追加。v_monthly_compensation VIEWから報酬・源泉徴収データを取得。

**追加内容**:
- Tab 4: メンバー別の報酬・源泉・DX補助・立替・支払額一覧
- KPI: 対象メンバー数 / 報酬合計 / 源泉合計 / 支払額合計
- CSVダウンロード対応
- constants.py: MONTHLY_COMPENSATION_VIEW定数追加

**設計判断**:
- 新規ページではなく既存ページにTab追加（WAMデータ1ページ集約）
- 報酬はWAMフィルタ対象外（gyomu側にWAM分類なし、将来対応可能な設計）

**ブラウザ検証結果**（Playwright MCP）:
| テスト項目 | 結果 |
|-----------|------|
| Tab 4 表示 | OK |
| KPI: 110名 / ¥10,514,861 / ¥-115,486 / ¥12,140,644 | OK |
| メンバー別テーブル | OK |
| CSVダウンロードボタン | OK |

テスト: Dashboard 218 + Cloud Run 42 = 260テスト全PASS

#### ✅ #56 GMOあおぞら振込CSV出力（PR #83, rev 00225-jjs, 2026-04-12）

Tab 4にGMOあおぞらネット銀行フォーマット（8カラム）の振込CSV出力機能を追加。

**追加内容**:
- 「振込CSV（GMOあおぞら形式）」ダウンロードボタン（報酬明細CSVと並列配置）
- payment > 0 のメンバーのみ出力、Shift_JIS
- 口座情報はプレースホルダー（口座マスタ未整備、手動補完運用）
- Phase B で口座マスタテーブル追加 → 完全自動化予定

テスト: Dashboard 235 + Cloud Run 42 = 277テスト全PASS

#### ✅ #55 支払明細書PDF生成（PR #86, 2026-04-12）

`fpdf2` による支払明細書PDF生成機能を Tab 5 に追加。

**追加内容**:
- `dashboard/lib/receipt_pdf.py` (新規): PDF生成ロジック（`generate_payment_statement` + `generate_all_statements_zip`）
- Tab 5「支払明細書」: メンバー選択 → A(業務委託費)+B(立替経費) プレビュー → PDF/ZIPダウンロード
- 日本語フォント: Dockerfile に `fonts-noto-cjk` 追加
- `@st.cache_data` でPDF生成キャッシュ化（再レンダリング時の再生成防止）
- per-memberエラーハンドリング（1件失敗でもZIP全体は継続、`_errors.txt` 付与）

**Phase B（将来）**: receipt_url の実ファイルダウンロード・バンドル（Drive API必要）

テスト: Dashboard 235 + Cloud Run 42 = 277テスト全PASS

#### 🔴 次セッションの開始点

**WAM Must要件 3/3 完了 + 全機能デプロイ済み**。残りはWant要件とインフラ改善。

1. **Playwright 動作確認**: Tab 5 個別メンバー選択 → KPIプレビュー → PDFダウンロード → 日本語レンダリング目視確認
2. **wam_target_projects の wam_flag 更新** — Phase 0回答後に対象PJを `'Y'` に UPDATE
3. **口座マスタテーブル追加** — #56 振込CSV の口座情報自動化（Phase B）
4. **#58 支払調書連携 (Want, P2)** — 後回し可

#### 📋 下書き送信（並行作業、ユーザー側）

ADR_0005 適用後の下書き3本（PR #60-62 初版 → PR #64 で改訂済み）:
- ゆりさん: 2項目（運用継続確認のみ、改修依頼ゼロ）
- ミヤヤさん: 4項目（Q-A1〜A3 + 相談④）+ 技術決裁済み3項目の共有
- ヒロス/ヒデスMTG: 8項目（変更なし）

---

> テスト件数は `python3 -m pytest dashboard/tests/ -q` で確認（235件、2026-04-12時点）

## 残タスク・監視事項

### 要対応
- **BQテーブル未作成**: `app_gyomu_reports` / `app_hojo_reports`（報告入力機能の保存に必要、schema.sql定義済み）
- **口座マスタテーブル追加** — #56 振込CSV の口座情報自動化（Phase B）

### 監視
- Cloud Run コスト削減効果測定（ADR 0004、`--no-cpu-throttling` 適用済み）
- 予算アラート設定（月¥3,000閾値）

---

> 過去の変更履歴・ファイル構成・アーキテクチャ図・BQスキーマ・環境情報は CLAUDE.md および `docs/handoff/archive/` を参照
