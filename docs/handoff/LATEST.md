# ハンドオフメモ - monthly-pay-tax

**更新日**: 2026-02-22
**フェーズ**: 6完了 + グループ機能追加 + UX改善
**最新デプロイ**: Collector rev 00019-hlp（グループ更新を毎朝バッチに統合）+ Dashboard rev 00053-4cx（アーキテクチャ図更新）
**テストスイート**: 189テスト（全PASS、8.5秒）

## 現在の状態

Cloud Run + BigQuery + Streamlitダッシュボード本番稼働中。
**Googleグループ機能デプロイ済み** - Admin SDK経由でメンバーのグループ所属を収集し、グループ別ダッシュボードタブを追加（PR #22/#23、2026-02-21デプロイ済み）。
groups_master テーブル: 69グループ登録済み。members テーブル: 192件にgroups列付与済み。

### 直近の変更（2026-02-22）

**`dashboard/pages/dashboard.py`**: ダッシュボード各テーブルにスプレッドシートURLリンクを追加（業務チェック管理表と同じ「開く」LinkColumn）

1. `load_monthly_compensation()`: `report_url` を SELECT に追加
2. `load_gyomu_with_members()`: `source_url` を SELECT に追加
3. `load_members_with_groups()`: `report_url` を SELECT に追加
4. **Tab1「メンバー別報酬明細」**: `groupby` に `report_url` を追加 → `reset_index()` → `"メンバー"` 列の隣に `"URL"` LinkColumn を表示
5. **Tab3「業務報告一覧」**: `source_url` → `"URL"` 列を `"メンバー"` 列の直後に追加
6. **Tab4 グループ別「メンバー一覧」**: `report_url` → `"URL"` 列を「本名」の隣に追加

### 直近の変更（今セッション: 2026-02-21）

**PR #23: メンバーのGoogleグループ所属収集 + PR #22: groups_masterテーブル + グループ別Tab**

1. **`cloud-run/sheets_collector.py`**: `collect_member_groups()` で Admin Directory API からグループ一覧を取得。`update_member_groups_from_bq()` で BQ の gws_account リストを使い members テーブルを groups フィールド付きで更新。`(updated_members, groups_master)` のタプルを返す。
2. **`cloud-run/main.py`**: `/update-groups` エンドポイント追加。シート再収集なしで約2分で完了。members + groups_master を同時更新。
3. **`cloud-run/config.py`**: `BQ_TABLE_GROUPS_MASTER = "groups_master"` 追加。スキーマ定義に `group_email`, `group_name` カラム追加。
4. **`infra/bigquery/schema.sql`**: `groups_master` テーブル定義追加。`members` テーブルに `groups STRING` カラム追加。
5. **`dashboard/pages/dashboard.py`**: Tab 4「グループ別」追加（3サブタブ: メンバー一覧 / 月別報酬サマリー / 業務報告）。`load_groups_master()`, `load_members_with_groups()` 関数追加。
6. **fix**: `db-dtypes` パッケージ追加（BQ `to_dataframe` に必要）。
7. **refactor**: グループ取得を `/update-groups` エンドポイントに分離（メインバッチから独立）。

**注意**: `/update-groups` は手動呼び出し（Cloud Run に POST）。Cloud Scheduler への追加は検討中。

8. **`dashboard/pages/dashboard.py`** (fix, rev 00050-qbh): `_render_group_tab()` を `@st.fragment` でラップし、グループ選択時のタブリセットを防止。内側サブタブ「月別報酬サマリー」→「月別報酬」にリネーム（外側Tab1との名前衝突解消）。
9. **`dashboard/pages/dashboard.py`** (feat, rev 00051-l7v): `load_member_name_map()` 追加。サイドバーのチェックボックス・Tab1〜4の全ピボット・詳細テーブル・業務報告一覧でメンバー名を「ニックネーム（本名）」形式で統一表示。`load_gyomu_with_members()` と `load_members_with_groups()` に `full_name` を追加。
10. **`cloud-run/main.py`** (feat, rev 00019-hlp): `POST /` のバッチ処理にグループ更新（Step 4）を統合。シート収集・BQ投入完了後、Admin SDK でグループ情報を自動更新。Admin SDK エラー時は本体処理を成功扱いにして warning ログ。`/update-groups` エンドポイントは手動再実行用として維持。

### 直近の変更（rev 00048: 2026-02-16）

**Sidebar UX Reorganization (rev 00048)**
- サイドバー構造の最適化: 期間・メンバー選択を上部に、ユーザー情報・ログアウトを下部に移動
- `app.py`: メール/ログアウトを `nav.run()` 後に配置、ブランディング統一
- `dashboard.py` / `check_management.py`: タイトル/ユーザー情報の重複削除
- Cloud Run デプロイ (rev 00048)、未認証アクセスIAM修正
- テストスイート全PASS（189テスト）

### 直近の変更（rev 00045-00047）

**PR #19: 業務チェック欠落カラム追加 + ヘルプページリデザイン（rev 00047）**

1. **業務チェック管理表のカラム補完**
   - 欠落していたカラムを追加: URL、当月入力完了、DX領収書、立替領収書
   - SQL: `h.dx_receipt`, `h.expense_receipt` をクエリに追加
   - UI: LinkColumn（「開く」テキスト）、編集不可列に追加
   - 「月締め」→「当月入力完了」にリネーム、未完了は「×」から空文字に変更（見やすさ向上）

2. **ヘルプページ全面リデザイン** (`pages/help.py`)
   - **CSS**: @keyframes 3種（fadeInUp, fadeIn, slideInLeft）で段階的な表示アニメーション
   - **ヒーロー**: グラデーション背景（#0EA5E9→#0369A1）+ 放射状グロー装飾
   - **クイックスタート**: 3ステップカード（ログイン→期間選択→データ確認）
   - **ページ一覧**: 3列グリッド × 2行（ダッシュボード/業務チェック/アーキテクチャ/ヘルプ/ユーザー管理/管理設定）
   - **フィルターガイド**: 期間・メンバー・タブ内フィルターの3カード
   - **業務チェック管理表ガイド（新規）**:
     * ステータスフロー: 未確認 → 確認中 → 確認完了/差戻し のビジュアル図
     * カラム説明表: 読取専用（灰色）/ 編集可（緑色）の区別
     * 操作のコツ: セルクリック、ダブルクリック、自動保存、競合エラー、URL遷移、進捗バー、操作ログ
   - **チェック業務の進め方**: 3ステップガイド（期間設定→項目確認→ステータス更新、緑テーマ）
   - **データ用語集**: 2列グリッド × 8行（16項目）、ホバーで背景色変更
   - **FAQ**: 既存3項目 + 新規2項目（業務チェックのステータス保存エラー、デプロイ後のページ表示問題）

### 直近の変更（rev 00043-00044）

1. **PR #19: ナビゲーション順序変更・メンバー選択チェックボックス化（rev 00043）**
   - メニュー順: ダッシュボード → **業務チェック** → アーキテクチャ → ヘルプ
   - 業務チェックページのサイドバー: テキスト検索 → ダッシュボード相同のチェックボックス方式（全選択/全解除ボタン + 高さ制限スクロール）
   - `app.py`のナビゲーション定義を`base_pages + checker_pages + utility_pages`に再構成

2. **PR #20: full_name フォールバック修正（rev 00044）**
   - `members`テーブルにnicknameが空のメンバー2名がいるため、nicknameが空の場合はfull_nameをフォールバック
   - 「森田 圭吾」「鈴木 裕史」が正しく表示されるように修正

### PR #18: 業務チェック管理表 テーブル直接編集化（デプロイ済み rev 00041）

- `st.dataframe()`読み取り専用 → `st.data_editor()`へ置換
- **ステータス列**: SelectboxColumn（⬜🔵✅🔴 アイコン付き）でドロップダウン選択
- **メモ列**: TextColumn（1000文字まで）で直接入力
- **編集不可列**: 名前、時間、報酬等（disabled設定）
- **変更検出**: 元DataFrameと編集後DataFrameを比較して自動検出
- **即時保存**: 変更検出時にBQへMERGE保存、競合エラーで即rerun
- **操作ログ**: テーブル下でメンバー選択 → expander内に履歴表示
- **詳細パネル削除**: 従来のメンバー選択+ステータスボタン+メモ入力は廃止

### PR #17: 業務チェック管理表 UX改善（デプロイ済み rev 00039）

1. **進捗バー追加**: KPIカード下にチェック完了率をプログレスバーで表示
2. **ステータスボタン化**: selectboxからワンクリックボタン式に変更（未確認/確認中/確認完了/差戻し）
3. **「次の未確認へ」ナビ**: 未確認メンバーへのジャンプボタン（残件数表示）
4. **ワークフローヒント**: 操作方法の案内テキストを追加
5. **メンバーセレクタ改善**: ドロップダウンにステータスアイコン表示

### PR #16: DRYリファクタ + サイドバーUI統一（デプロイ済み rev 00038）

1. **`lib/ui_helpers.py` 新規作成**: `render_kpi`, `clean_numeric_scalar/series`, `fill_empty_nickname`, `valid_years`, `render_sidebar_year_month` を集約
2. **dashboard.py**: 重複関数をインポートに置換、サイドバー年月セレクタを共通化
3. **check_management.py**: インラインフィルタをサイドバーに移動、重複関数をインポートに置換

### PR #15: 業務チェック管理表（デプロイ済み rev 00037）

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
    ui_helpers.py           # 共通UIユーティリティ（KPI, 数値変換, 年月セレクタ）
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

1. ~~**旧LBインフラ削除**~~: ✅ 完了
2. ~~**レート制限改善**~~: ✅ 完了（rev 00014）
3. ~~**業務チェック管理表 テーブル直接編集化**~~: ✅ 完了（rev 00044）
4. ~~**業務チェック欠落カラム補完**~~: ✅ 完了（rev 00047）
5. ~~**ヘルプページリデザイン**~~: ✅ 完了（rev 00047）
6. ~~**0値データ調査**~~: ✅ 対処不要（2026-02-15調査完了）
   - position_rate空文字139名 → 役職なしで正常（値は5/10/12の3段階）
   - qualification_allowance "0" vs 空文字混在 → VIEWのSAFE_CASTで両方0になり計算影響なし
   - member_id重複16組 → 1メンバー=複数シート（sheet_number 1/2）の正常構造。JOINキーがreport_url(=source_url)のため二重計上なし
7. ~~**Googleグループ収集機能**~~: ✅ 実装・デプロイ完了（PR #22/#23、2026-02-21）
8. ~~**グループ機能デプロイ**~~: ✅ 完了（Collector rev 00018-pbj + Dashboard rev 00049-gm2）
   - `/update-groups` 初回実行済み: 192メンバー更新、69グループ登録
9. ~~**(検討) `/update-groups` のスケジュール化**~~: ✅ 完了（rev 00019-hlp: POST / に統合、毎朝6時に自動実行）
10. ~~**グループ選択時タブリセット修正**~~: ✅ 完了（rev 00050-qbh、@st.fragment）
11. ~~**メンバー名に本名を全箇所で併記**~~: ✅ 完了（rev 00051-l7v）
12. ~~**ダッシュボード各テーブルにURLリンク追加**~~: ✅ 完了（2026-02-22、要デプロイ）

### デプロイ済み状態

- **Collector**: rev 00019-hlp（2026-02-21: グループ更新を POST / に統合）
  - rev 00018-pbj: グループ機能 + /update-groups エンドポイント
  - rev 00017: db-dtypes 追加（BQ to_dataframe 依存）
  - rev 00014: レート制限改善（throttle 0.5s + num_retries=5）
- **Dashboard**: rev 00053-4cx（2026-02-22: アーキテクチャ図を最新状態に更新）
  - rev 00052-tcb: ダッシュボード各テーブルにURLリンク追加
  - rev 00051-l7v: メンバー名に本名を全箇所で併記
  - rev 00050-qbh: グループ選択時のタブリセット修正（@st.fragment）
  - rev 00049-gm2: Tab 4「グループ別」追加
  - rev 00048: サイドバーUX改善
  - rev 00047: 業務チェック欠落カラム補完 + ヘルプページリデザイン
  - rev 00046: ヘルプページのカード型レイアウト・アニメーション実装
  - rev 00045: 業務チェック カラム追加（URL、当月入力完了、DX領収書、立替領収書）
  - rev 00044: テーブル直接編集化 + full_name フォールバック
  - rev 00043: ナビ順序変更、メンバー選択チェックボックス化
- **BQ VIEWs**: v_gyomu_enriched, v_hojo_enriched, v_monthly_compensation デプロイ済み
- **BQ Table**: withholding_targets, dashboard_users, check_logs, groups_master デプロイ済み
- **BQ Table members**: groups カラム追加済み（192件・69グループ登録済み）

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

**members**: report_url, member_id, nickname, gws_account, full_name, qualification_allowance, position_rate, corporate_sheet, donation_sheet, qualification_sheet, sheet_number, groups, ingested_at

**groups_master**: group_email, group_name, ingested_at（69グループ登録済み）

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
