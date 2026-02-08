# ハンドオフメモ - monthly-pay-tax

**更新日**: 2026-02-08
**フェーズ**: 5 - ダッシュボードマルチページ化 + 認可 + ドキュメント

## 現在の状態

Cloud Run + BigQuery + Streamlitダッシュボード本番稼働中。
ダッシュボードをマルチページ化し、BQベースのユーザー認可、アーキテクチャドキュメント、管理設定を追加。

### 今回の変更（Phase 5: Dashboard Multipage）

1. **マルチページ化**: app.py（649行） → app.py（ルーター ~50行） + pages/ + lib/
2. **BQユーザー認可**: `dashboard_users` テーブル + IAP email照合 + admin/viewer ロール
3. **ユーザー管理ページ**: admin専用。追加/削除/ロール変更（BQ DML、重複チェック付き）
4. **アーキテクチャページ**: 5つのMermaid図（全体構成/データフロー/ER図/VIEW計算チェーン/認証フロー）
5. **ヘルプページ**: ページガイド/フィルター使い方/用語集/FAQ
6. **管理設定ページ**: admin専用。キャッシュクリア/BQテーブル情報/ユーザー統計
7. **共有ライブラリ**: lib/auth.py, lib/bq_client.py, lib/styles.py, lib/constants.py

### ファイル構成

```
dashboard/
  app.py                    # エントリポイント: 認証 + st.navigation ルーター
  requirements.txt          # streamlit-mermaid 追加
  pages/
    dashboard.py            # 既存3タブ（app.pyから抽出）
    architecture.py         # Mermaidアーキテクチャ図
    user_management.py      # 管理者: ホワイトリスト管理
    admin_settings.py       # 管理者: 設定・システム情報
    help.py                 # ヘルプ/マニュアル
  lib/
    __init__.py
    auth.py                 # IAP認証 + BQホワイトリスト照合
    bq_client.py            # 共有BQクライアント + load_data()
    styles.py               # 共有CSS
    constants.py            # 定数
```

### デプロイ前の手順

1. **BQテーブル作成**: `dashboard_users` テーブルを作成
2. **シードデータ投入**: 初期管理者をINSERT
3. **Cloud Runデプロイ**: `dashboard/` ディレクトリからビルド + デプロイ
4. **IAP経由で動作確認**

```bash
# 1. BQテーブル作成
bq query --use_legacy_sql=false "$(cat <<'EOF'
CREATE TABLE IF NOT EXISTS `monthly-pay-tax.pay_reports.dashboard_users` (
  email STRING NOT NULL,
  role STRING NOT NULL,
  display_name STRING,
  added_by STRING NOT NULL,
  created_at TIMESTAMP NOT NULL,
  updated_at TIMESTAMP NOT NULL
)
EOF
)"

# 2. シードデータ
bq query --use_legacy_sql=false "$(cat <<'EOF'
INSERT INTO `monthly-pay-tax.pay_reports.dashboard_users`
  (email, role, display_name, added_by, created_at, updated_at)
VALUES
  ('yasushi-honda@tadakayo.jp', 'admin', 'Y.Honda', 'system', CURRENT_TIMESTAMP(), CURRENT_TIMESTAMP())
EOF
)"

# 3. デプロイ
cd dashboard
gcloud builds submit --tag asia-northeast1-docker.pkg.dev/monthly-pay-tax/cloud-run-images/pay-dashboard
gcloud run deploy pay-dashboard \
  --image asia-northeast1-docker.pkg.dev/monthly-pay-tax/cloud-run-images/pay-dashboard \
  --platform managed --region asia-northeast1 --memory 512Mi \
  --no-allow-unauthenticated
```

### スプレッドシートの役割整理

| SS | 用途 | BQ取り込み |
|----|------|-----------|
| 管理表（`1fBN...`） | URLリスト + タダメンMマスタ（A:K完全） | 対象 |
| 190個の個別報告SS | gyomu/hojoデータ | 対象 |
| GASバインドSS（`16V9...`） | 旧タダメンM参照（A:E） | 使用しない |
| 統計分析SS（`1Kyv...`） | **参照・確認用** | 対象外 |

### 次のアクション

1. **デプロイ**: BQテーブル作成 → シード投入 → Cloud Runデプロイ → IAP動作確認
2. **レート制限改善**: バッチの~380回のSheets API読み取りでレート制限に到達 → backoff/リトライ追加を検討
3. **将来課題**: position_rate/qualification_allowanceの一部メンバーで0値 → データ投入確認

### デプロイ済み状態

- **Collector**: rev 00013（members A:K対応 + 先行読み取り）
- **Dashboard**: **未デプロイ**（マルチページ化の変更待ち）
- **BQ VIEWs**: v_gyomu_enriched, v_hojo_enriched, v_monthly_compensation デプロイ済み
- **BQ Table**: withholding_targets シードデータ投入済み、**dashboard_users 未作成**

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
    ├─ dashboard_users: ダッシュボードアクセス制御
    ├─ v_gyomu_enriched: VIEW（メンバーJOIN + 月抽出 + 距離分離 + 総稼働時間）
    ├─ v_hojo_enriched: VIEW（メンバーJOIN + 年月正規化）
    └─ v_monthly_compensation: VIEW（月別報酬＆源泉徴収 6 CTE）
          │
          ▼
Cloud Run "pay-dashboard" (Streamlit / 512MiB / マルチページ)
    アクセス: https://34.107.163.68.sslip.io/ (Cloud IAP経由)
    認証: IAP → BQ dashboard_users → admin/viewer ロール分岐
    ページ: ダッシュボード / アーキテクチャ / ヘルプ / ユーザー管理(admin) / 管理設定(admin)
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

**dashboard_users**: email, role, display_name, added_by, created_at, updated_at

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
