# ハンドオフメモ - monthly-pay-tax

**更新日**: 2026-02-08
**フェーズ**: 3 完了 - BQ VIEWs + members cleanup + ダッシュボードVIEW化

## 現在の状態

Cloud Run + BigQuery + Streamlitダッシュボード本番稼働中。
PR #3 マージ済み。BQ VIEWsデプロイ済み、ダッシュボードVIEW参照に移行完了。

### 今回の変更（Phase 3）

1. **BQ VIEWs追加**: GASバインドSSのスプレッドシート関数パイプラインをSQL化
   - `v_gyomu_enriched`: メンバーJOIN + 月抽出 + 距離分離 + 1立てフラグ + 総稼働時間
   - `v_hojo_enriched`: メンバーJOIN + 年月正規化（数値/日付文字列/Excelシリアル値対応）
2. **members schema cleanup**: qualification_allowance / position_rate 削除（元データ空確認済み）
3. **ダッシュボード更新**: VIEW経由クエリ、月フィルター全3タブ対応、距離分離カラム表示

### スプレッドシートの役割整理

| SS | 用途 | BQ取り込み |
|----|------|-----------|
| 管理表（`1fBN...`） | URLリスト | URLのみ |
| 190個の個別報告SS | gyomu/hojoデータ | ✅ 対象 |
| GASバインドSS（`16V9...`） | タダメンMマスタ | ✅ 対象（A:E列のみ） |
| 統計分析SS（`1Kyv...`） | **参照・確認用** | ❌ 対象外 |

### 次のアクション

1. **SAキー削除**: `431e84cf...` → FAILED_PRECONDITION（組織ポリシー制約、GCPコンソールから手動削除）
2. **将来課題**: position_rate/qualification_allowanceの取得方法検討（タダメンMにデータ投入 or 別途マスタ管理）

### デプロイ済み状態

- **Collector**: rev 00010（members A:E対応）✅
- **Dashboard**: rev 00023（VIEW参照 + 月フィルター全タブ対応）✅
- **BQ VIEWs**: v_gyomu_enriched, v_hojo_enriched デプロイ済み ✅

## アーキテクチャ

```
Cloud Scheduler (毎朝6時JST)
    │ OIDC認証
    ▼
Cloud Run "pay-collector" (Python 3.12 / Flask / gunicorn / 2GiB)
    ├─ Workload Identity + IAM signBlob でDWD認証
    ├─ 管理表 → 190件のURLリスト取得
    ├─ 各スプレッドシート巡回 → Sheets API v4 でデータ収集
    ├─ タダメンMマスタ取得（A:E列）
    ├─ pandas DataFrame に整形
    └─ BigQuery に load_table_from_dataframe (WRITE_TRUNCATE)
          │
          ▼
    BigQuery (pay_reports dataset)
    ├─ gyomu_reports: ~18,800行（業務報告）
    ├─ hojo_reports: ~1,000行（補助＆立替報告）
    ├─ members: 190行（タダメンMマスタ）
    ├─ v_gyomu_enriched: VIEW（メンバーJOIN + 月抽出 + 距離分離 + 総稼働時間）
    └─ v_hojo_enriched: VIEW（メンバーJOIN + 年月正規化）
          │
          ▼
Cloud Run "pay-dashboard" (Streamlit / 512MiB)
    アクセス: https://34.107.163.68.sslip.io/ (Cloud IAP経由)
```

## 環境情報

| 項目 | 値 |
|------|-----|
| GCPプロジェクトID | `monthly-pay-tax` |
| GCPアカウント | yasushi-honda@tadakayo.jp |
| GitHub | yasushi-honda-prog/monthly-pay-tax |
| Collector URL | `https://pay-collector-209715990891.asia-northeast1.run.app` |
| Dashboard URL | `https://34.107.163.68.sslip.io/`（Cloud IAP経由） |
| SA Email | `pay-collector@monthly-pay-tax.iam.gserviceaccount.com` |
| ⚠️ 残SAキー | `431e84cf48b58c4b119e0f6ba6a3a742338ede1f`（要手動削除） |

## BQスキーマ

**gyomu_reports**: source_url, year, date, day_of_week, activity_category, work_category, sponsor, description, unit_price, hours, amount, ingested_at

**hojo_reports**: source_url, year, month, hours, compensation, dx_subsidy, reimbursement, total_amount, monthly_complete, dx_receipt, expense_receipt, ingested_at

**members**: report_url, member_id, nickname, gws_account, full_name, ingested_at

結合キー: `source_url` (gyomu/hojo) = `report_url` (members)

### BQ VIEWs

**v_gyomu_enriched**: gyomu_reports + members JOIN + 以下の加工フィールド
- `month` (INT64): dateカラムから月抽出（"M/D", "M月D日", "YYYY/M/D" 対応）
- `work_hours`: 自家用車使用以外のhours
- `travel_distance_km`: 自家用車使用時のhours
- `daily_wage_flag`: 日給制を含む場合 = 1
- `total_work_hours`: work_hours + 全日稼働(+6h) / 半日稼働(+3h)

**v_hojo_enriched**: hojo_reports + members JOIN + 以下の正規化
- `year` (INT64): 数値年 / "YYYY/MM/DD" / Excelシリアル値(>40000) を統一
- `month` (INT64): 同上の正規化
