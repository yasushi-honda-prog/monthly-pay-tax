# ハンドオフメモ - monthly-pay-tax

**更新日**: 2026-02-07
**フェーズ**: 1 - Cloud Run + BigQuery 本番稼働中

## 現在の状態

GASからCloud Run + BigQueryへの移行が完了し、本番稼働中。毎朝6時にCloud Schedulerが自動実行。

### 完了済み

| 項目 | 状態 | 詳細 |
|------|------|------|
| GASコードのclasp clone | ✅ | アカウント: yasushi-honda@tadakayo.jp |
| GitHubリポジトリ | ✅ | yasushi-honda-prog/monthly-pay-tax (public) |
| GCPプロジェクト | ✅ | `monthly-pay-tax` |
| 環境分離 | ✅ | .envrc, .gitconfig.local, gcloud config |
| GCP API有効化 | ✅ | BigQuery, Sheets, Run, AR, Scheduler, Build |
| サービスアカウント | ✅ | `pay-collector@monthly-pay-tax.iam.gserviceaccount.com` |
| Domain-Wide Delegation | ✅ | Workload Identity + IAM signBlob（キーレス） |
| BigQueryスキーマ | ✅ | `pay_reports.gyomu_reports`, `pay_reports.hojo_reports` |
| Cloud Run デプロイ | ✅ | v2, 2GiB メモリ, asia-northeast1 |
| Cloud Scheduler | ✅ | 毎朝6時JST、OIDC認証 |
| Artifact Registry | ✅ | クリーンアップポリシー: 最新2イメージ保持 |
| E2Eテスト | ✅ | 190件巡回、gyomu: 14,029行、hojo: 942行、217.5秒 |
| ADR-0001 | ✅ | アーキテクチャ決定記録 |

### 未完了

| 項目 | 優先度 | 備考 |
|------|--------|------|
| Looker Studio接続 | 高 | BQネイティブコネクタで接続 |
| BQカラム名の意味付け | 中 | col_b~col_kを実際のフィールド名に変更 |
| Gitコミット＆push | 高 | 今セッションの変更をコミット |

## アーキテクチャ

```
Cloud Scheduler (毎朝6時JST)
    │ OIDC認証
    ▼
Cloud Run (Python 3.12 / Flask / gunicorn)
    ├─ Workload Identity + IAM signBlob でDWD認証
    ├─ 管理表 → 190件のURLリスト取得
    ├─ 各スプレッドシート巡回 → Sheets API v4 でデータ収集
    ├─ pandas DataFrame に整形
    └─ BigQuery に load_table_from_dataframe (WRITE_TRUNCATE)
          │
          ▼
    BigQuery (pay_reports dataset)
    ├─ gyomu_reports: 14,029行
    └─ hojo_reports: 942行
          │
          ▼
    Looker Studio（未接続）
```

## GCPリソース一覧

| リソース | 名前 | リージョン |
|---------|------|----------|
| Cloud Run | pay-collector | asia-northeast1 |
| BigQuery Dataset | pay_reports | asia-northeast1 |
| Artifact Registry | cloud-run-images | asia-northeast1 |
| Cloud Scheduler | pay-collector-daily | asia-northeast1 |
| Service Account | pay-collector | - |

## 環境情報

| 項目 | 値 |
|------|-----|
| GCPプロジェクトID | `monthly-pay-tax` |
| GCPアカウント | yasushi-honda@tadakayo.jp |
| GitHub | yasushi-honda-prog/monthly-pay-tax |
| Cloud Run URL | `https://pay-collector-209715990891.asia-northeast1.run.app` |
| SA Email | `pay-collector@monthly-pay-tax.iam.gserviceaccount.com` |
| DWD Client ID | `105293708004584950257` |
