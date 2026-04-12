# ハンドオフメモ - monthly-pay-tax

**更新日**: 2026-04-12（Phase 1b バックエンド完了: Collector デプロイ + 実データ2,250行収集成功）
**フェーズ**: 6完了 + グループ機能 + グループ一括登録・自動同期 + UX改善 + 数値変換リファクタ + 報告入力機能（デプロイ済み）＋ **WAM助成金対応 Phase 1b バックエンド完了**
**最新デプロイ**: Collector rev 00023-w7s（立替金シート収集対応）+ Dashboard rev 00221-hjn
**Cloud Run設定**: 2026-04-07 `--no-cpu-throttling --max-instances=3` 適用済み（ADR 0004）
**テストスイート**: Dashboard 198 + Cloud Run 42 = **240テスト全PASS**

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

| Issue | 優先度 | 内容 | ブロック |
|-------|-------|------|---------|
| [#54](https://github.com/yasushi-honda-prog/monthly-pay-tax/issues/54) | **P0** | WAM Phase 0: ステークホルダー合意形成（18項目Q&A） | Blocks #55〜#58 |
| [#55](https://github.com/yasushi-honda-prog/monthly-pay-tax/issues/55) | P1 | WAM要件① 領収書の自動生成と振込一括化 (Must) | Blocked by #54 |
| [#56](https://github.com/yasushi-honda-prog/monthly-pay-tax/issues/56) | P1 | WAM要件② 振込データ抽出とCSV出力（GMOあおぞら） (Must) | Blocked by #54 |
| [#57](https://github.com/yasushi-honda-prog/monthly-pay-tax/issues/57) | P1 | WAM要件③ WAM月別報酬・源泉徴収確認ツール (Must) | Blocked by #54 |
| [#58](https://github.com/yasushi-honda-prog/monthly-pay-tax/issues/58) | P2 | WAM要件④ 支払調書作成ツールへの連携 (Want) | Blocked by #54 |

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

#### 🔴 次セッションの開始点: フロントエンド（WAM確認ページ）

**目的**: BQ実データを使って、ステークホルダーに「こういうデータが取れています」と見せられるドラフト提案ページ

**実装方針**:
1. `dashboard/pages/wam_monthly.py` を新規追加（st.navigation）
2. `v_reimbursement_enriched` VIEW からデータ取得
3. 閲覧権限: 当面 admin 限定（提案ドラフトのため）
4. 既存ページに影響なし、BQ読み取りのみ

**表示候補**:
- WAM対象PJ別の立替金額サマリー（月別）
- メンバー別の明細一覧（フィルタ付き）
- 領収書PDF添付状況（receipt_url の有無）

#### 📋 下書き送信（並行作業、ユーザー側）

ADR_0005 適用後の下書き3本（PR #60-62 初版 → PR #64 で改訂済み）:
- ゆりさん: 2項目（運用継続確認のみ、改修依頼ゼロ）
- ミヤヤさん: 4項目（Q-A1〜A3 + 相談④）+ 技術決裁済み3項目の共有
- ヒロス/ヒデスMTG: 8項目（変更なし）

---

> テスト件数は `python3 -m pytest dashboard/tests/ -q` で確認（198件、2026-03-28時点）

## 現在の状態

Cloud Run + BigQuery + Streamlitダッシュボード本番稼働中。
**Googleグループ機能デプロイ済み** - Admin SDK経由でメンバーのグループ所属を収集。
groups_master テーブル: 69グループ登録済み。members テーブル: 192件にgroups列付与済み。

### 直近の変更（2026-04-07 コスト調査・Cloud Run設定変更）

**Cloud Run CPU billing mode変更（ADR 0004）**

- pay-dashboard のコスト増加（1月¥15 → 3月¥6,961）を調査
- BQは月¥12（全体0.1%）で無罪。Cloud Run CPUが¥4,536（92%）が真犯人
- 原因: 正規ユーザーがブラウザ開きっぱなし → Streamlit WebSocket常時接続 → vCPU秒積算
- **対策**: `--no-cpu-throttling --max-instances=3` 適用（単価-25%、¥4,536 → 約¥3,400見込み）
- 検証コマンド: `curl -I https://pay-dashboard-...` HTTP 200確認済み（94ms応答）
- 3〜5日後にCloud Billing Reportsで日次コスト確認要

**残課題**:
- 請求書PDF確認（¥10,079 vs ¥4,903のズレ解明）
- 予算アラート設定（月¥3,000閾値）

### 直近の変更（2026-03-28 PR #51 コミット済み・未デプロイ）

**報告入力機能の追加（プロトタイプ）**

| ファイル | 変更内容 |
|---------|---------|
| `dashboard/pages/report_input.py` | 新規: 業務報告（日次）・補助報告（月次）の入力ページ |
| `dashboard/tests/test_pages_report_input.py` | 新規: report_inputページのユニットテスト（9件） |
| `dashboard/app.py` | `user_pages` リスト追加 + `user`ロール対応ナビゲーション |
| `dashboard/lib/auth.py` | `require_user()` 追加（user/viewer/checker/adminを許可） |
| `dashboard/lib/constants.py` | `APP_GYOMU_TABLE`, `APP_HOJO_TABLE` 定数追加 |
| `dashboard/pages/user_management.py` | ロール選択肢に `user` を追加（3箇所） |
| `dashboard/tests/conftest.py` | `st.tabs`, `mock_columns(int)`, `st.cache_data.clear`, 各種mock追加 |
| `infra/bigquery/schema.sql` | `app_gyomu_reports`, `app_hojo_reports` テーブル定義追加 |

**report_input.py の仕様**:
- アクセス権: user/viewer/checker/admin（`require_user()` で制御）
- Tab 1「業務報告入力」: 業務マスタ（35業務分類）から選択→MERGE保存、当月一覧表示
- Tab 2「補助報告入力」: 月次補助報告（時間・報酬・DX補助・立替）MERGE保存
- データ保存先: `pay_reports.app_gyomu_reports` / `pay_reports.app_hojo_reports`
- Collectorが管理するgyomu_reports/hojo_reportsとは独立（スプレッドシート不要の直接入力）
- `GYOMU_MASTER`: 35エントリ（活動分類・業務分類・単価・単位・説明）
- `SPONSOR_LIST`: 20スポンサー
- `TEAM_LIST`: 9隊

**BQ テーブル（未作成 — デプロイ前に要実行）**:
```sql
-- infra/bigquery/schema.sql の末尾に追加済み
-- 実行: bq query --use_legacy_sql=false < infra/bigquery/schema.sql
-- または BQ Console で CREATE TABLE IF NOT EXISTS を個別実行
```

### 直近の変更（2026-03-28 コミット済み）

**b786eed: Tab1にメンバー別月次活動時間ピボットを追加**（未デプロイ）

- Tab1「月別報酬サマリー」のサブタブを4→5に拡張（mtab1〜mtab5）
- 新サブタブ「メンバー別 月次活動時間」を2番目に追加（`total_work_hours` の月×メンバーピボット）
- 表示形式は小数1桁（`{:,.1f}`）

### 直近の変更（2026-03-21 デプロイ済み rev 00166-k42）

**PR #48: 数値変換の重複排除とヘルパー関数抽出**（ce35430）

- `_COMP_NUM_COLS` 定数を導入し `num_cols` 定義の2箇所重複を解消
- `_ensure_numeric_pivot()` ヘルパー関数を抽出し、ピボット表示前の数値保証処理（3箇所重複）を統一

**PR #47: 数値フォーマットが文字列型カラムに適用されるValueErrorを修正**（09d6f5a）

- BQからのデータが文字列型のまま残るケースで `style.format("¥{:,.0f}")` が `ValueError` を発生させていた問題を修正
- `fillna(0).astype(float)` を `pd.to_numeric(errors="coerce")` に置換

**PR #49 + 追加修正: Altairチャート防御的ガード追加**（5719d56〜04ffad5）

- 月次推移チャート: NaNデータに対し `dropna()` + 空DataFrameガードを追加
- 活動分類チャート: 金額0のカテゴリを除外するガード追加
- Altairチャート全般: `stack=False` を明示してstack変換を抑止
- **結論**: コンソール警告（Infinite extent / fit-x / Vega-Lite version）はStreamlitのVega-Lite v5→v6互換の副作用。表示に影響なし

### 過去の変更（2026-03-17 以前、デプロイ済み）

詳細はアーカイブ参照: `docs/handoff/archive/2026-03-history.md`

- rev 00144-q9z: 人数・件数バッジをタイトル右にインライン表示
- rev 00140-rs8: 業務チェックページ — 手動データ更新ボタン追加
- rev 00139-bmf: TTL延長（1時間→6時間）
- rev 00079-tl7: PR #26〜#46（ダッシュボード名変更、グループ機能、UX改善）
- rev 00020-g6b: Collector（グループ同期 Step 5）

---

## 次のアクション

### 未デプロイ

なし（2026-04-08 時点、全コミット済みコードをデプロイ済み）

### 要対応（BQテーブル未作成）

1. **BQテーブル作成（報告入力機能の保存に必要）**
   - `app_gyomu_reports` / `app_hojo_reports` を本番BQに作成（schema.sql に定義済み）
   - 作成前は報告入力ページの保存操作がエラーになる（開発中のため暫定）

### 監視・確認（進行中）

3. **Cloud Run コスト削減効果測定（2026-04-10〜12頃）**
   - 3〜5日後にCloud Billing Reportsで日次コスト確認
   - 日次¥95前後に収まるか確認
   - 不十分なら追加対策: Streamlit fragment idle timeout / Looker Studio分離

4. **請求書PDF確認**（ADR 0004 残課題）
   - ユーザー報告¥10,079 vs Reports ¥4,903 ズレの解明

5. **予算アラート設定**（ADR 0004 残課題）
   - 月¥3,000閾値で 50/90/100% 通知

### 検討中

6. **`userロール` の運用方針確定**
   - 現在 `user` ロールは `viewer` と同等の閲覧権限 + 報告入力権限
   - BQテーブル作成後、実際のメンバーに付与してテスト

---

## ファイル構成

```
dashboard/
  app.py                    # エントリポイント: 認証 + st.navigation ルーター
  pages/
    dashboard.py            # 月別報酬サマリー（5サブタブ）/スポンサー別/業務報告一覧/グループ別
    check_management.py     # 業務チェック管理表（checker/admin）
    report_input.py         # 報告入力（user/viewer/checker/admin）★新規
    architecture.py         # Mermaidアーキテクチャ図
    user_management.py      # 管理者: ホワイトリスト管理
    admin_settings.py       # 管理者: 設定・システム情報
    help.py                 # ヘルプ/マニュアル
  lib/
    auth.py                 # Streamlit OIDC認証 + require_admin/checker/user
    bq_client.py            # 共有BQクライアント
    constants.py            # 定数（APP_GYOMU_TABLE, APP_HOJO_TABLE追加）
    styles.py               # 共有CSS
    ui_helpers.py           # 共通UIユーティリティ
  tests/
    conftest.py             # Streamlit/BQモック（st.tabs, mock_columns(int)対応済み）
    test_pages_report_input.py  # 報告入力テスト（9件）
    test_pages_check_management.py
    test_pages_user_management.py
    test_lib_auth.py
    test_lib_ui_helpers.py
```

## デプロイ手順

```bash
# Dashboard（dashboard/ ディレクトリから実行）
# ⚠️ --allow-unauthenticated 必須（Streamlit OIDCが内部でOAuth認証を処理するため）
gcloud builds submit --tag asia-northeast1-docker.pkg.dev/monthly-pay-tax/cloud-run-images/pay-dashboard
gcloud run deploy pay-dashboard \
  --image asia-northeast1-docker.pkg.dev/monthly-pay-tax/cloud-run-images/pay-dashboard \
  --platform managed --region asia-northeast1 --memory 512Mi \
  --allow-unauthenticated

# BQテーブル作成（初回のみ）
# app_gyomu_reports, app_hojo_reports を BQ Console または bq CLI で作成
```

## デプロイ済み状態

- **Collector**: rev 00020-g6b（グループ同期 Step 5）
- **Dashboard**: rev 00166-k42（数値変換リファクタ + Altairガード）
  - 未デプロイ: b786eed（活動時間ピボット）+ 今セッション変更（報告入力機能）
- **BQ VIEWs**: v_gyomu_enriched, v_hojo_enriched, v_monthly_compensation デプロイ済み
- **BQ Tables**: gyomu_reports, hojo_reports, members, withholding_targets, dashboard_users, check_logs, groups_master
  - 未作成: app_gyomu_reports, app_hojo_reports（schema.sql に定義済み）

## アーキテクチャ

```
Cloud Scheduler (毎朝6時JST)
    │ OIDC認証
    ▼
Cloud Run "pay-collector" (Python 3.12 / Flask / gunicorn / 2GiB)
    ├─ Workload Identity + IAM signBlob でDWD認証
    ├─ 管理表 → 190件のURLリスト取得
    ├─ 各スプレッドシート巡回 → Sheets API v4 でデータ収集
    ├─ BigQuery に load_table_from_dataframe (WRITE_TRUNCATE)
    └─ Step 5: dashboard_users をグループメンバーと自動同期
          │
          ▼
    BigQuery (pay_reports dataset)
    ├─ gyomu_reports: ~17,000行（業務報告）
    ├─ hojo_reports: ~1,100行（補助＆立替報告）
    ├─ members: 192行（タダメンMマスタ）
    ├─ withholding_targets: 17行（源泉対象リスト）
    ├─ dashboard_users: ダッシュボードアクセス制御
    ├─ check_logs: 業務チェック操作ログ
    ├─ groups_master: 69グループ
    ├─ app_gyomu_reports: アプリ入力業務報告 ★未作成
    ├─ app_hojo_reports: アプリ入力補助報告 ★未作成
    ├─ v_gyomu_enriched: VIEW
    ├─ v_hojo_enriched: VIEW
    └─ v_monthly_compensation: VIEW（月別報酬＆源泉徴収 6 CTE）
          │
          ▼
Cloud Run "pay-dashboard" (Streamlit / 512MiB / マルチページ)
    アクセス: https://pay-dashboard-209715990891.asia-northeast1.run.app
    認証: Streamlit OIDC → BQ dashboard_users → admin/checker/viewer/user ロール分岐
    ページ: ダッシュボード / 報告入力(user+) / 業務チェック(checker+) / アーキテクチャ / ヘルプ / ユーザー管理(admin) / 管理設定(admin)
```

## 環境情報

| 項目 | 値 |
|------|-----|
| GCPプロジェクトID | `monthly-pay-tax` |
| GCPアカウント | yasushi-honda@tadakayo.jp |
| GitHub | yasushi-honda-prog/monthly-pay-tax |
| Collector URL | `https://pay-collector-209715990891.asia-northeast1.run.app` |
| Dashboard URL | `https://pay-dashboard-209715990891.asia-northeast1.run.app` |
| SA Email | `pay-collector@monthly-pay-tax.iam.gserviceaccount.com` |

## BQスキーマ（主要テーブル）

**gyomu_reports**: source_url, year, date, day_of_week, activity_category, work_category, sponsor, description, unit_price, hours, amount, ingested_at

**hojo_reports**: source_url, year, month, hours, compensation, dx_subsidy, reimbursement, total_amount, monthly_complete, dx_receipt, expense_receipt, ingested_at

**members**: report_url, member_id, nickname, gws_account, full_name, qualification_allowance, position_rate, corporate_sheet, donation_sheet, qualification_sheet, sheet_number, groups, ingested_at

**app_gyomu_reports**: user_email, date, year, month, day_of_week, team, activity_category, work_category, sponsor, description, unit_price, hours, amount, created_at, updated_at（★未作成）

**app_hojo_reports**: user_email, year, month, hours, compensation, dx_subsidy, reimbursement, total_amount, monthly_complete, dx_receipt, expense_receipt, created_at, updated_at（★未作成）

**dashboard_users**: email, role, display_name, added_by, source_group, created_at, updated_at

**check_logs**: source_url, year, month, status, checker_email, memo, action_log, updated_at

**groups_master**: group_email, group_name, ingested_at（69グループ登録済み）

結合キー: `source_url` (gyomu/hojo) = `report_url` (members) = `source_url` (check_logs)

### BQ VIEWs

**v_gyomu_enriched**: gyomu_reports + members JOIN + 月抽出 + 距離分離 + 日給制フラグ + total_work_hours

**v_hojo_enriched**: hojo_reports + members JOIN + 年月正規化（数値/日付文字列/Excelシリアル値対応）

**v_monthly_compensation**: 月別報酬＆源泉徴収（6 CTE: gyomu_agg → hojo_agg → member_attrs → all_keys → base_calc → with_tax）

## Secret Manager

- シークレット名: `dashboard-auth-config`
- マウント先: `/app/.streamlit/secrets.toml`
- 内容: Streamlit OIDC設定（client_id, client_secret, redirect_uri, cookie_secret, server_metadata_url）
- OAuthブランド: `orgInternalOnly=true`（tadakayo.jpドメイン限定）
