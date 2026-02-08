# ハンドオフメモ - monthly-pay-tax

**更新日**: 2026-02-08
**フェーズ**: 2 完了 - BQリネーム + ダッシュボード + タダメンM取込

## 現在の状態

Cloud Run + BigQuery + Streamlitダッシュボード本番稼働中。
PR #2 マージ済み、Cloud Run再デプロイ完了。monthly_compensation関連のクリーンアップ完了。

### 判明事項

1. **タダメンM F/G列は元データが空** → qualification_allowance / position_rate のNULLは正常
2. **position_rate / qualification_allowance** は統計分析SSの数式内にのみ存在（5%/10%/12%の3パターン）
3. **統計分析SSはBQデータソースとして不適** → インタラクティブ単月表示ツール

### スプレッドシートの役割整理

| SS | 用途 | BQ取り込み |
|----|------|-----------|
| 管理表（`1fBN...`） | URLリスト | URLのみ |
| 190個の個別報告SS | gyomu/hojoデータ | ✅ 対象 |
| GASバインドSS（`16V9...`） | タダメンMマスタ | ✅ 対象 |
| 統計分析SS（`1Kyv...`） | **参照・確認用** | ❌ 対象外 |

### 次のアクション

1. **SAキー削除**: `431e84cf...` → FAILED_PRECONDITION（組織ポリシー制約、GCPコンソールから手動削除）
2. **将来課題**: position_rate/qualification_allowanceの取得方法検討（タダメンMにデータ投入 or 別途マスタ管理）

### デプロイ済み状態

- **Collector**: rev 00009（monthly_compensation削除済みコード）✅
- **Dashboard**: rev 00021（monthly_compensation参照削除済み）✅

## アーキテクチャ

```
Cloud Scheduler (毎朝6時JST)
    │ OIDC認証
    ▼
Cloud Run "pay-collector" (Python 3.12 / Flask / gunicorn / 2GiB)
    ├─ Workload Identity + IAM signBlob でDWD認証
    ├─ 管理表 → 190件のURLリスト取得
    ├─ 各スプレッドシート巡回 → Sheets API v4 でデータ収集
    ├─ タダメンMマスタ取得
    ├─ pandas DataFrame に整形
    └─ BigQuery に load_table_from_dataframe (WRITE_TRUNCATE)
          │
          ▼
    BigQuery (pay_reports dataset)
    ├─ gyomu_reports: ~18,800行（業務報告）
    ├─ hojo_reports: ~1,000行（補助＆立替報告）
    └─ members: 190行（タダメンMマスタ）
          │
          ▼
Cloud Run "pay-dashboard" (Streamlit / 512MiB)
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
| ⚠️ 残SAキー | `431e84cf48b58c4b119e0f6ba6a3a742338ede1f`（要手動削除） |

## BQスキーマ

**gyomu_reports**: source_url, year, date, day_of_week, activity_category, work_category, sponsor, description, unit_price, hours, amount, ingested_at

**hojo_reports**: source_url, year, month, hours, compensation, dx_subsidy, reimbursement, total_amount, monthly_complete, dx_receipt, expense_receipt, ingested_at

**members**: report_url, member_id, nickname, gws_account, full_name, qualification_allowance(⚠️ALL NULL), position_rate(⚠️ALL NULL), ingested_at

結合キー: `source_url` (gyomu/hojo) = `report_url` (members)
