---
title: BQ snapshot バックアップ 復旧手順書
date: 2026-05-30
status: active
tags: [運用手順, BigQuery, バックアップ, 復旧]
---

## 1. 概要

毎朝のバッチ処理（Cloud Run `pay-collector` の `POST /`）が、本処理の**前**（Step 0）に
**BQが唯一のソースである5テーブル**の snapshot を別データセット `pay_reports_backup` へ取得する。
各 snapshot は **90日で自動失効**する。

| 項目 | 内容 |
|------|------|
| 取得タイミング | 毎朝6時バッチの冒頭（Step 0）。本処理が更新する前の状態を保全 |
| 保管先 | `monthly-pay-tax.pay_reports_backup`（`pay_reports` と同一リージョン `asia-northeast1`） |
| 命名規則 | `{テーブル名}_{YYYYMMDD}`（日付サフィックスは JST） |
| 保持期間 | 90日（`expiration_timestamp` で自動失効） |
| 同日再実行 | `IF NOT EXISTS` で最初の1断面を保持（手動同期と朝バッチが同日でも上書きしない） |

### 対象5テーブル（BQが唯一のソース＝Sheets/Admin Directoryから再生成不可）

| テーブル | 更新元 | 失われると |
|---|---|---|
| `dashboard_users` | UI（ユーザー管理）+ Step5 グループ同期 | ホワイトリスト・ロール喪失 |
| `dashboard_sync_groups` | UI（ユーザー管理）+ Step5 | グループ自動同期 ON/OFF 設定喪失 |
| `check_logs` | UI（業務チェック管理） | チェック履歴=監査証跡の喪失 |
| `wam_target_projects` | seed / 手動 | WAM対象PJ設定喪失 |
| `withholding_targets` | seed / 手動 | 源泉徴収対象設定喪失 |

> 毎朝 WRITE_TRUNCATE で再生成される `gyomu_reports` / `hojo_reports` / `members` / `groups_master` /
> `reimbursement_items` / `member_master` は **対象外**（Sheets/Admin Directory がソースのため、
> バッチ再実行で復元可能）。これらの保全が必要な場面（活動分類 rename 等）は
> `20260516_活動分類_rename.md` の §5.5 に従い、作業直前に手動 snapshot する。

## 2. snapshot 一覧と最新取得状況の確認

```bash
# backup データセットの snapshot 一覧（テーブル名 + 種別）
bq ls --format=prettyjson monthly-pay-tax:pay_reports_backup \
  | python3 -c "import sys,json; [print(t['tableReference']['tableId'], t.get('type')) for t in json.load(sys.stdin)]"

# 特定テーブルの最新 snapshot を日付降順で確認（例: dashboard_users）
bq ls --max_results 1000 monthly-pay-tax:pay_reports_backup \
  | grep dashboard_users | sort -r | head -5
```

毎朝の取得成否は Cloud Logging（`pay-collector`）で確認する。

```bash
# Step0 snapshot の完了ログ（結果 dict に各テーブル 1=成功 / -1=失敗）
gcloud logging read \
  'resource.type=cloud_run_revision AND resource.labels.service_name=pay-collector AND textPayload:"snapshotバックアップ完了"' \
  --project=monthly-pay-tax --limit=3 --format='value(timestamp,textPayload)'
```

## 3. 復元手順

### 3.1 復元前の確認（必須）

1. **どの時点に戻すか決める**: snapshot 一覧（§2）から、破損より前の日付の snapshot を選ぶ
2. **現在のテーブル状態を確認**: 上書きする前に現状の行数・内容を控える

```bash
# 復元対象の現在の行数（例: dashboard_users）
bq query --use_legacy_sql=false \
  "SELECT COUNT(*) AS cnt FROM \`monthly-pay-tax.pay_reports.dashboard_users\`"

# 復元候補 snapshot の行数（戻し先と件数を比較）
bq query --use_legacy_sql=false \
  "SELECT COUNT(*) AS cnt FROM \`monthly-pay-tax.pay_reports_backup.dashboard_users_YYYYMMDD\`"
```

3. **念のため現状も退避**: 復元自体が誤りだった場合に戻せるよう、現在の状態を snapshot しておく

```bash
NOW=$(date +%Y%m%d_%H%M)
bq query --use_legacy_sql=false \
  "CREATE SNAPSHOT TABLE \`monthly-pay-tax.pay_reports_backup.dashboard_users_prerestore_${NOW}\` \
   CLONE \`monthly-pay-tax.pay_reports.dashboard_users\` \
   OPTIONS(expiration_timestamp = TIMESTAMP_ADD(CURRENT_TIMESTAMP(), INTERVAL 30 DAY))"
```

### 3.2 復元の実行

```bash
# snapshot で本番テーブルを上書き復元（-f で確認プロンプトを省略）
bq cp -f \
  monthly-pay-tax:pay_reports_backup.dashboard_users_YYYYMMDD \
  monthly-pay-tax:pay_reports.dashboard_users
```

### 3.3 復元後の確認

```bash
bq query --use_legacy_sql=false \
  "SELECT COUNT(*) AS cnt FROM \`monthly-pay-tax.pay_reports.dashboard_users\`"
```

- dashboard で該当テーブルの内容が正しく戻っているか確認
- 必要に応じて dashboard 管理画面の「キャッシュクリア」を実行

## 4. 部分失敗時の判断

Step0 の snapshot はテーブル単位で `try/except` し、1テーブルが失敗しても残りは継続する。
戻り値・ログの結果 dict で `-1` のテーブルが失敗。

| 状況 | 判断 |
|---|---|
| 一部テーブルが `-1` | 当日そのテーブルの断面は無い。前日以前の snapshot が有効。次回バッチで自動再取得されるため、緊急時のみ手動 snapshot |
| 全テーブルが `-1` | backup データセット不在 / 権限 / リージョン不整合を疑う。`bq show pay_reports_backup` で存在とロケーションを確認 |
| ログに「スキップ」 | `create_snapshots` 呼び出し自体が失敗（クライアント生成等）。本体バッチは正常完了している |

## 5. 関連

- 実装: `cloud-run/bq_loader.py` `create_snapshots()` / `cloud-run/main.py` Step 0
- データセット定義: `infra/bigquery/backup_dataset.sql`
- 再生成可能テーブルの非常時バックアップ: `20260516_活動分類_rename.md` §5.5
