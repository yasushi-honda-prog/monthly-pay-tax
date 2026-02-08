# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## プロジェクト概要

GASベースの給与スプレッドシートデータ集約を、Cloud Run + BigQuery に移行したバッチ処理システム。
毎朝6時にCloud Schedulerが起動し、約190件のスプレッドシートからデータを収集してBigQueryに書き込む。

## アーキテクチャ

```
Cloud Scheduler (0 6 * * * JST, OIDC認証)
  → Cloud Run "pay-collector" (Python 3.12 / Flask / gunicorn)
    → Sheets API v4 (IAM signBlobによるキーレスDWD認証)
    → BigQuery pay_reports.{gyomu_reports, hojo_reports} (WRITE_TRUNCATE)
```

認証はWorkload Identity + IAM signBlob APIによるキーレスDomain-Wide Delegation。
SA鍵ファイルは使わない（ローカル開発時のみ `SA_KEY_PATH` 環境変数で鍵ファイル指定）。

## ディレクトリ構成

- `cloud-run/` - Cloud Runアプリケーション（本体）
  - `main.py` - Flaskエントリポイント（`POST /` でバッチ実行、`GET /health`）
  - `sheets_collector.py` - Sheets API経由のデータ収集（DWD認証含む）
  - `bq_loader.py` - BigQueryへのデータロード（pandas DataFrame経由）
  - `config.py` - GCPプロジェクトID、BQテーブル名、マスタスプレッドシートID等の設定値
  - `tests/` - テストディレクトリ（未実装）
- `コード.js` - 旧GASコード（参照用、稼働していない）
- `infra/bigquery/schema.sql` - BQテーブルスキーマ定義
- `infra/ar-cleanup-policy.json` - Artifact Registryクリーンアップポリシー
- `docs/adr/` - Architecture Decision Records
- `docs/handoff/LATEST.md` - ハンドオフドキュメント

## ビルド・デプロイ

```bash
# Cloud Runへのデプロイ（cloud-run/ ディレクトリから）
gcloud builds submit --tag asia-northeast1-docker.pkg.dev/monthly-pay-tax/cloud-run-images/pay-collector
gcloud run deploy pay-collector \
  --image asia-northeast1-docker.pkg.dev/monthly-pay-tax/cloud-run-images/pay-collector \
  --platform managed --region asia-northeast1 --memory 2Gi --timeout 1800 \
  --no-allow-unauthenticated
```

メモリは2GiB必須（190件巡回で512MBはOOM）。gunicornは1worker/1thread/1800sタイムアウト。

## GCP環境

| リソース | 値 |
|---------|-----|
| プロジェクト | `monthly-pay-tax` |
| リージョン | `asia-northeast1` |
| SA | `pay-collector@monthly-pay-tax.iam.gserviceaccount.com` |
| Cloud Run URL | `https://pay-collector-209715990891.asia-northeast1.run.app` |
| BQデータセット | `pay_reports` |
| BQテーブル | `gyomu_reports`（業務報告）, `hojo_reports`（補助報告） |
| AR | `cloud-run-images`（最新2イメージ保持） |

## BQスキーマ

3テーブル構成。すべてSTRING型 + ingested_at (TIMESTAMP)。

- `gyomu_reports`: source_url, year, date, day_of_week, activity_category, work_category, sponsor, description, unit_price, hours, amount
- `hojo_reports`: source_url, year, month, hours, compensation, dx_subsidy, reimbursement, total_amount, monthly_complete, dx_receipt, expense_receipt
- `members`: report_url, member_id, nickname, gws_account, full_name, qualification_allowance, position_rate

`source_url`（gyomu/hojo）= `report_url`（members）で結合してメンバー名を取得。

## ダッシュボード

`dashboard/` - Streamlitアプリ（別Cloud Runサービス `pay-dashboard`）

- URL: `https://pay-dashboard-209715990891.asia-northeast1.run.app`
- 512MiBメモリ、SA: `pay-collector@...`（BQ読み取り用）
- 3タブ構成: 月別報酬サマリー / スポンサー別業務委託費 / 業務報告一覧
- BQの `members` テーブルと結合してメンバー名を表示

## 環境分離

direnvで環境分離済み。`.envrc`で`GH_CONFIG_DIR`、`CLOUDSDK_ACTIVE_CONFIG_NAME`、`GCLOUD_PROJECT`を設定。
GitHub CLIは`.gh/`ディレクトリ、gitユーザーは`.gitconfig.local`で管理。

## 既知の技術的制約

- Cloud RunのデフォルトSA認証（`google.auth.default()`）は`with_subject`非対応 → IAM signBlob API経由でキーレスDWD
- バッチ処理は約217秒（190件巡回、gyomu: 14,029行 / hojo: 942行）
- 毎回WRITE_TRUNCATEで全データ置換（差分更新ではない）
