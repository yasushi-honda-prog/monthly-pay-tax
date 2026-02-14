# ハンドオフメモ - monthly-pay-tax

**更新日**: 2026-02-14
**フェーズ**: 6完了 + 業務チェック管理表

## 現在の状態

Cloud Run + BigQuery + Streamlitダッシュボード本番稼働中。
ダッシュボードをマルチページ化し、BQベースのユーザー認可、アーキテクチャドキュメント、管理設定を追加。
業務チェック管理表を追加し、checkerロールによるhojoデータの確認・管理が可能に。

### 業務チェック管理表（未デプロイ）

1. **BQテーブル `check_logs` 追加**: ステータス・メモ・操作ログの永続化（`schema.sql`）
2. **checkerロール追加**: `auth.py`に`require_checker()`、`user_management.py`でchecker選択肢追加
3. **新ページ `check_management.py`**: メンバーのhojo報告一覧 + チェックステータス管理 + メモ + 操作ログ
4. **app.pyルーティング**: checker/admin向けに「業務チェック」ページを表示
5. **状態遷移**: 未確認 → 確認中 → 確認完了 / 差戻し（MERGE文で原子的更新）
6. **機能**: 年月セレクタ、KPIカード（完了/未確認/差戻し数）、フィルタ、スプレッドシートリンク、操作ログ自動記録

### PR #13-#14: ユーザー管理 表示名編集機能（デプロイ済み rev 00036）

1. **`update_display_name()` 関数追加** (`user_management.py`): BQの`dashboard_users.display_name`をパラメータ化クエリで更新
2. **インライン編集UI**: 各ユーザー行の名前横に✏️ポップオーバーを配置、表示名を即時編集・保存
3. **レイアウト改善** (PR #14): 編集ボタンを専用列から名前横のインラインに移動、4列→3列レイアウトでスペース効率化

### PR #12: Sheets APIレート制限改善（デプロイ済み rev 00014）

1. **`_execute_with_throttle` ヘルパー追加** (`sheets_collector.py`): 全Sheets APIリクエストにスロットリング（0.5秒間隔）+ 自動リトライ（`num_retries=5`, exponential backoff）を適用
2. **設定定数追加** (`config.py`): `SHEETS_API_NUM_RETRIES=5`, `SHEETS_API_SLEEP_BETWEEN_REQUESTS=0.5`
3. **3箇所の`.execute()`置換**: `get_url_list`, `get_sheet_data`, `collect_members` で `_execute_with_throttle()` を使用
4. **ログ改善**: HttpError時にtransient(429/5xx)/permanentのログレベル分離 + ステータスコード記録
5. **エラーハンドリング**: `get_url_list`にtry-except追加（レビュー指摘対応）
6. **ユニットテスト6件追加** (`tests/test_sheets_collector.py`): 全PASS
7. **処理時間**: ~217秒 → ~409秒（Cloud Run 1800秒に対し余裕あり）

### PR #11: Mermaid図レンダリング修正

1. **`streamlit-mermaid` → `components.html()` + Mermaid.js v11 CDN**: サードパーティライブラリを廃止し、CDN直接読み込みに変更
2. **ダークモード対応**: `prefers-color-scheme` メディアクエリでライト/ダーク自動切替
3. **erDiagram PKアノテーション削除**: パースエラーの原因だった `PK` を除去
4. **図のサイズ改善**: SVG幅100%、フォント18px、ノード間隔拡大、各図の高さを個別設定
5. **`streamlit-mermaid==0.2.0` を requirements.txt から削除**

**技術的教訓**: `st.html()` はsandboxed iframeでESMモジュールインポートがブロックされる → `streamlit.components.v1.html()` + 通常の `<script>` タグで解決

### PR #9: Phase 6 IAP → Streamlit OIDC移行

1. **認証方式変更**: Cloud IAP → Streamlit OIDC（Google OAuth, `st.login`/`st.user`）
2. **アクセスURL変更**: `sslip.io`（自己署名証明書） → `*.run.app`（Google管理SSL証明書）
3. **lib/auth.py**: `get_iap_user_email()` → `get_user_email()`（`st.user.email`ベース）
4. **app.py**: `st.login`/`st.logout`フロー + サイドバーにログアウトボタン
5. **architecture.py**: 認証フロー図をOIDCに更新
6. **Secret Manager**: `dashboard-auth-config` → `/app/.streamlit/secrets.toml`にマウント
7. **Cloud Run設定**: `ingress=all` + `allUsers:run.invoker`（アプリ層で認証）

### Phase 5: Dashboard Multipage

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
  requirements.txt          # Mermaid.js CDN利用（streamlit-mermaid廃止）
  pages/
    dashboard.py            # 既存3タブ（app.pyから抽出）
    check_management.py     # 業務チェック管理表（checker/admin）
    architecture.py         # Mermaidアーキテクチャ図
    user_management.py      # 管理者: ホワイトリスト管理 + 表示名編集
    admin_settings.py       # 管理者: 設定・システム情報
    help.py                 # ヘルプ/マニュアル
  lib/
    __init__.py
    auth.py                 # Streamlit OIDC認証 + BQホワイトリスト照合
    bq_client.py            # 共有BQクライアント + load_data()
    styles.py               # 共有CSS
    constants.py            # 定数
```

### デプロイ手順

```bash
# ビルド
gcloud builds submit --tag asia-northeast1-docker.pkg.dev/monthly-pay-tax/cloud-run-images/pay-dashboard dashboard/

# デプロイ（Secret Managerマウント付き）
gcloud run deploy pay-dashboard \
  --image asia-northeast1-docker.pkg.dev/monthly-pay-tax/cloud-run-images/pay-dashboard \
  --platform managed --region asia-northeast1 --memory 512Mi \
  --update-secrets=/app/.streamlit/secrets.toml=dashboard-auth-config:latest
```

### Secret Manager

- シークレット名: `dashboard-auth-config`
- マウント先: `/app/.streamlit/secrets.toml`
- 内容: Streamlit OIDC設定（client_id, client_secret, redirect_uri, cookie_secret, server_metadata_url）
- OAuthブランド: `orgInternalOnly=true`（tadakayo.jpドメイン限定）

### スプレッドシートの役割整理

| SS | 用途 | BQ取り込み |
|----|------|-----------|
| 管理表（`1fBN...`） | URLリスト + タダメンMマスタ（A:K完全） | 対象 |
| 190個の個別報告SS | gyomu/hojoデータ | 対象 |
| GASバインドSS（`16V9...`） | 旧タダメンM参照（A:E） | 使用しない |
| 統計分析SS（`1Kyv...`） | **参照・確認用** | 対象外 |

### 次のアクション

1. ~~**旧LBインフラ削除**~~: ✅ 確認済み（全リソース削除済み）
2. ~~**レート制限改善**~~: ✅ PR #12 マージ済み、rev 00014 デプロイ済み
3. **将来課題**: position_rate/qualification_allowanceの一部メンバーで0値 → データ投入確認

### デプロイ済み状態

- **Collector**: rev 00014（レート制限改善: throttle 0.5s + num_retries=5）
- **Dashboard**: rev 00036（表示名インライン編集 + コンパクトレイアウト）
- **BQ VIEWs**: v_gyomu_enriched, v_hojo_enriched, v_monthly_compensation デプロイ済み
- **BQ Table**: withholding_targets, dashboard_users シードデータ投入済み

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
    アクセス: https://pay-dashboard-209715990891.asia-northeast1.run.app
    認証: Streamlit OIDC (Google OAuth) → BQ dashboard_users → admin/checker/viewer ロール分岐
    ページ: ダッシュボード / 業務チェック(checker/admin) / アーキテクチャ / ヘルプ / ユーザー管理(admin) / 管理設定(admin)
```

## 環境情報

| 項目 | 値 |
|------|-----|
| GCPプロジェクトID | `monthly-pay-tax` |
| GCPアカウント | yasushi-honda@tadakayo.jp |
| GitHub | yasushi-honda-prog/monthly-pay-tax |
| Collector URL | `https://pay-collector-209715990891.asia-northeast1.run.app` |
| Dashboard URL | `https://pay-dashboard-209715990891.asia-northeast1.run.app`（Streamlit OIDC認証） |
| SA Email | `pay-collector@monthly-pay-tax.iam.gserviceaccount.com` |

## BQスキーマ

**gyomu_reports**: source_url, year, date, day_of_week, activity_category, work_category, sponsor, description, unit_price, hours, amount, ingested_at

**hojo_reports**: source_url, year, month, hours, compensation, dx_subsidy, reimbursement, total_amount, monthly_complete, dx_receipt, expense_receipt, ingested_at

**members**: report_url, member_id, nickname, gws_account, full_name, qualification_allowance, position_rate, corporate_sheet, donation_sheet, qualification_sheet, sheet_number, ingested_at

**withholding_targets**: work_category, licensed_member_id

**dashboard_users**: email, role, display_name, added_by, created_at, updated_at

**check_logs**: source_url, year, month, status, checker_email, memo, action_log, updated_at

結合キー: `source_url` (gyomu/hojo) = `report_url` (members) = `source_url` (check_logs)

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
