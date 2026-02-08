# ハンドオフメモ - monthly-pay-tax

**更新日**: 2026-02-08
**フェーズ**: 4 完了 - 月別報酬＆源泉徴収VIEW + ダッシュボードTab1全面改修

## 現在の状態

Cloud Run + BigQuery + Streamlitダッシュボード本番稼働中。
PR #4 マージ済み。v_monthly_compensation VIEW + withholding_targets テーブル + ダッシュボードTab1改修。

### 今回の変更（Phase 4）

1. **v_monthly_compensation VIEW**: 月別報酬＆源泉徴収の完全計算パイプライン（6 CTE構成）
   - gyomu_agg → hojo_agg → member_attrs → all_keys → base_calc → with_tax → 最終SELECT
   - 源泉徴収: -FLOOR(T * 0.1021)、法人/寄付は免除、士業は全額対象
2. **withholding_targets テーブル**: 源泉対象15業務分類 + 士業2名のシードデータ
3. **members拡張**: A:K列（qualification_allowance, position_rate, corporate_sheet, donation_sheet, qualification_sheet, sheet_number）
4. **ダッシュボードTab1**: KPI cards(5項目) + メンバー×月ピボット + 報酬明細テーブル + 月次推移チャート
5. **コレクター修正**: members先行読み取り（レート制限対策）+ 明示的BQスキーマ
6. **safe-refactor**: SQL DRY化（with_tax CTE）、logging追加、num_cols統合

### スプレッドシートの役割整理

| SS | 用途 | BQ取り込み |
|----|------|-----------|
| 管理表（`1fBN...`） | URLリスト + タダメンMマスタ（A:K完全） | ✅ 対象 |
| 190個の個別報告SS | gyomu/hojoデータ | ✅ 対象 |
| GASバインドSS（`16V9...`） | 旧タダメンM参照（A:E） | ❌ 使用しない |
| 統計分析SS（`1Kyv...`） | **参照・確認用** | ❌ 対象外 |

### 次のアクション

1. **レート制限改善**: バッチの~380回のSheets API読み取りでレート制限に到達 → backoff/リトライ追加を検討
2. **将来課題**: position_rate/qualification_allowanceの一部メンバーで0値 → データ投入確認
3. **SAキー**: `431e84cf...` → SYSTEM_MANAGED確認済み、対応不要

### デプロイ済み状態

- **Collector**: rev 00013（members A:K対応 + 先行読み取り）✅
- **Dashboard**: rev 00025（Tab1全面改修 + logging）✅
- **BQ VIEWs**: v_gyomu_enriched, v_hojo_enriched, v_monthly_compensation デプロイ済み ✅
- **BQ Table**: withholding_targets シードデータ投入済み ✅

## アーキテクチャ

```
Cloud Scheduler (毎朝6時JST)
    │ OIDC認証
    ▼
Cloud Run "pay-collector" (Python 3.12 / Flask / gunicorn / 2GiB)
    ├─ Workload Identity + IAM signBlob でDWD認証
    ├─ タダメンMマスタ先行取得（A:K列、1 APIコール）
    ├─ 管理表 → 190件のURLリスト取得
    ├─ 各スプレッドシート巡回 → Sheets API v4 でデータ収集
    ├─ pandas DataFrame に整形（明示的STRINGスキーマ）
    └─ BigQuery に load_table_from_dataframe (WRITE_TRUNCATE)
          │
          ▼
    BigQuery (pay_reports dataset)
    ├─ gyomu_reports: ~17,000行（業務報告）
    ├─ hojo_reports: ~1,100行（補助＆立替報告）
    ├─ members: 190行（タダメンMマスタ、A:K完全）
    ├─ withholding_targets: 17行（源泉対象リスト）
    ├─ v_gyomu_enriched: VIEW（メンバーJOIN + 月抽出 + 距離分離 + 総稼働時間）
    ├─ v_hojo_enriched: VIEW（メンバーJOIN + 年月正規化）
    └─ v_monthly_compensation: VIEW（月別報酬＆源泉徴収 6 CTE）
          │
          ▼
Cloud Run "pay-dashboard" (Streamlit / 512MiB)
    アクセス: https://34.107.163.68.sslip.io/ (Cloud IAP経由)
    Tab1: 月別報酬サマリー（v_monthly_compensation）
    Tab2: スポンサー別業務委託費（v_gyomu_enriched）
    Tab3: 業務報告一覧（v_gyomu_enriched）
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

## BQスキーマ

**gyomu_reports**: source_url, year, date, day_of_week, activity_category, work_category, sponsor, description, unit_price, hours, amount, ingested_at

**hojo_reports**: source_url, year, month, hours, compensation, dx_subsidy, reimbursement, total_amount, monthly_complete, dx_receipt, expense_receipt, ingested_at

**members**: report_url, member_id, nickname, gws_account, full_name, qualification_allowance, position_rate, corporate_sheet, donation_sheet, qualification_sheet, sheet_number, ingested_at

**withholding_targets**: work_category, licensed_member_id

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

**v_monthly_compensation**: 月別報酬＆源泉徴収（6 CTE構成）
- gyomu_agg: 業務報告の月別集計（時間報酬, 距離報酬, 1立て, 源泉対象額）
- hojo_agg: 補助報告の月別集計（DX補助, 立替）
- member_attrs: メンバー属性（法人/寄付/士業フラグ, 資格手当）
- all_keys: gyomu/hojoのキー統合
- base_calc: 小計 → 役職手当 → 資格手当加算
- with_tax: 源泉対象額 → 源泉徴収 → 支払い計算
- 源泉率: 10.21%（FLOOR）、法人/寄付は免除、士業は全額対象
- 通貨フォーマット対応: REGEXP_REPLACE(r'[^0-9.\-]', '')
