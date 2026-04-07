# ハンドオフメモ - monthly-pay-tax

**更新日**: 2026-04-07
**フェーズ**: 6完了 + グループ機能 + グループ一括登録・自動同期 + UX改善 + 数値変換リファクタ + 報告入力機能（コミット済み・未デプロイ）
**最新デプロイ**: Collector rev 00020-g6b + Dashboard rev 00166-k42（PR #47/#48/#49 + Infinite extent修正すべてデプロイ済み）
**Cloud Run設定**: 2026-04-07 `--no-cpu-throttling --max-instances=3` 適用済み（ADR 0004）
**テストスイート**: 218テスト全PASS（dashboard 198 + cloud-run 20）

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

### 未デプロイ（コミット済み・デプロイ待ち）

1. **報告入力機能をデプロイ（PR #51 コミット済み）**
   - BQテーブル `app_gyomu_reports` / `app_hojo_reports` を本番BQに作成（schema.sql に定義済み）
   - dashboard ビルド・デプロイで反映可能

2. **Tab1 活動時間ピボット（b786eed）のデプロイ**
   - b786eed はコミット済みだが未デプロイ
   - dashboard ビルド・デプロイで反映可能（上記 #1 と同時にデプロイ可）

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
