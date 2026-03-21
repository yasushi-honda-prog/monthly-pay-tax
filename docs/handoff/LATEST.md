# ハンドオフメモ - monthly-pay-tax

**更新日**: 2026-03-21（今セッション末）
**フェーズ**: 6完了 + グループ機能追加 + グループ一括登録・自動同期 + UX改善 + ドキュメント整備 + 数値変換リファクタ
**最新デプロイ**: Collector rev 00020-g6b + Dashboard rev 00144-q9z（PR #47/#48はデプロイ待ち）
**テストスイート**: 203テスト（全PASS、PR #38で14テスト追加）

## 現在の状態

Cloud Run + BigQuery + Streamlitダッシュボード本番稼働中。
**Googleグループ機能デプロイ済み** - Admin SDK経由でメンバーのグループ所属を収集し、グループ別ダッシュボードタブを追加（PR #22/#23、2026-02-21デプロイ済み）。
groups_master テーブル: 69グループ登録済み。members テーブル: 192件にgroups列付与済み。

### 直近の変更（2026-03-21: 今セッション）

**PR #48: 数値変換の重複排除とヘルパー関数抽出**（ce35430、デプロイ待ち）

- `_COMP_NUM_COLS` 定数を導入し `num_cols` 定義の2箇所重複を解消
- `_ensure_numeric_pivot()` ヘルパー関数を抽出し、ピボット表示前の数値保証処理（3箇所重複）を統一
- 18列の個別 `for` ループを `.apply(pd.to_numeric)` に最適化
- object型列のみ変換する条件付きロジックで不要な変換をスキップ

**PR #47: 数値フォーマットが文字列型カラムに適用されるValueErrorを修正**（09d6f5a、デプロイ待ち）

- BQからのデータが文字列型のまま残るケースで `style.format("¥{:,.0f}")` が `ValueError` を発生させていた問題を修正
- `fillna(0).astype(float)` を `pd.to_numeric(errors="coerce")` に置換
- ピボット表示前にも再正規化を追加
- Closes #25

**PR #49 + 追加修正: Altairチャート Infinite extent警告を解消**（5719d56〜04ffad5、デプロイ待ち）

- 月次推移チャート: NaNデータに対し `dropna()` + 空DataFrameガードを追加（5719d56）
- 活動分類チャート: 金額0/空データ時の `y` スケール範囲が無限になる問題を修正、`scale=alt.Scale(zero=True)` を追加（bc323f1）
- Altairチャート全般: `stack=False` を明示してVega-Lite v5/v6互換のInfinite extent警告を解消（04ffad5）

### 直近の変更（2026-03-17）

**人数・件数バッジをタイトル右にインライン表示**（32485f1、デプロイ済み rev 00144-q9z）

- Tab1「メンバー別 月次支払額」タイトル右に「○ 名」バッジを追加
- Tab1「メンバー別 報酬明細」タイトル右に「○ 件」バッジを追加
- flexboxでタイトルとバッジを横並び表示（既存 count-badge CSSを活用）

**業務チェックページ — 手動データ更新ボタン追加**（88afdb2、デプロイ済み rev 00140-rs8）

- ページ最下部に expander「データ更新（手動）」を追加（checker/admin のみ）
- Cloud Run Collector に OIDC IDトークン認証付き POST リクエストを送信
- 完了待機型（約4分スピナー表示）、成功/失敗を画面に表示
- `lib/constants.py` に `COLLECTOR_URL` 追加、`requirements.txt` に `requests` 明示追加

**業務チェックページ — 操作ログ改善**（3f124e6〜1db0de9、デプロイ済み rev 00141-6ls〜00142-kr2）

- 操作ログのデフォルト選択を最終保存者（最新タイムスタンプのメンバー）に変更
- 当月誰も操作していない場合は「選択してください」（未選択状態）で表示
- 未選択時に「操作ログはありません」が2行表示されるバグを修正

**TTL延長のみ再適用**（10f47af、デプロイ済み rev 00139-bmf）

- 全 `@st.cache_data(ttl=3600)` → `ttl=21600`（6時間）に延長（dashboard.py・bq_client.py）
- グループ処理リファクタリングは不安定のため含まず、TTL延長のみ実施

**パフォーマンス改善・freeze_columns・グループ修正をリバート**（f4f3b46、rev 00138-hvs）

- 前セッションのパフォーマンス改善（グループキャッシュ化）・freeze_columns=1 が不安定だったためリバート
- モバイル修正後（336c715）の安定状態に戻した

**モバイルでメンバー別月次支払額のピボットテーブルが名前しか表示されない問題を修正**（336c715、デプロイ済み rev 00131-gbc）

- Tab1「メンバー別 月次支払額」・グループ別タブの2箇所を修正
- `pivot_table` のインデックス（display_name）を `reset_index()` で通常列に変換し `hide_index=True` を設定
- Streamlit でインデックス列がモバイルの横スクロール対象外になる挙動を解消

### 直近の変更（2026-03-07）

**PR #46: ダッシュボード名を「活動時間・報酬マネジメントダッシュボード」に変更**（54ed9c5、デプロイ済み rev 00079-tl7）

- `dashboard/app.py`: page_title、ログイン画面、サイドバーキャプション（4箇所）
- `dashboard/pages/dashboard.py`: docstring、ページヘッダー（2箇所）
- `dashboard/pages/help.py`: ヒーローセクション（1箇所）
- `dashboard/lib/auth.py`: 未認証時の表示（1箇所）
- `docs/handoff/LATEST.md`: デプロイ済み状態を反映

**PR #38: グループ単位のユーザー一括登録 + 定時自動同期**（337bbd7、デプロイ済み）

- `dashboard_users` に `source_group` 列追加（グループ由来/手動登録の識別）
- ユーザー管理UI: グループ選択→プレビュー→一括登録のフロー追加
- `cloud-run/bq_loader.py`: `sync_dashboard_users_from_groups()` 追加（追加/削除/手動登録不可侵/ロール継承）
- `cloud-run/sheets_collector.py`: `list_group_members()` 追加（Admin Directory API、ページネーション対応）
- `cloud-run/main.py`: 定時更新 Step 5 で `dashboard_users` をグループメンバーと自動同期
- ユニットテスト14件追加（`test_list_group_members.py` 6件 + `test_sync_dashboard_users.py` 8件）

**PR #39/#40: BQ予約語 GROUPS をバッククォートでエスケープ**（0846a95、デプロイ済み）

- `user_management.py`: `GROUPS` → `` `groups` `` でエスケープ（BQ予約語エラー修正）

**PR #41/#42: グループプレビューの重複表示を DISTINCT で解消**（d8d530d、デプロイ済み）

- `user_management.py`: グループメンバープレビュークエリに `DISTINCT` 追加

**PR #43/#44: グループ一括登録にプログレスバーを追加**（b3fefff、デプロイ済み）

- `user_management.py`: 一括登録処理に `st.progress` + 進捗テキスト表示を追加

**PR #45: アーキテクチャ図にグループ一括登録・自動同期を反映**（d18c8fe、デプロイ済み）

- 全体構成図: Step5 dashboard_users同期を追加
- データフロー: グループ→dashboard_usersの同期・Dashboard一括登録を追加
- ER図: `dashboard_users` に `source_group` 列、`groups_master` との関連を追加
- 認証フロー: admin→グループ一括登録の経路を追加

### 直近の変更（2026-03-01）

**CLAUDE.md: ダッシュボードデプロイ前チェックリスト追加**（e0a8333）

Issue #31対応で4PRを要した反省から、BQ接続必須環境でのデプロイ前検証手順を明文化。import整合性、戻り値の型変更時の呼び出し元確認、スタブ行の全カラム定義、空DataFrameパスの確認。

**PR #35: データ未登録メンバーの報酬明細テーブルにreport_urlを表示**（デプロイ済み）

- `load_member_name_map` に `report_url` マッピングを追加
- スタブ行（0値行）の URL 列にも `members` テーブルの `report_url` を設定

**PR #34: dashboard.pyにpandas importを追加**（デプロイ済み）

- `pd.DataFrame` を使用しているが `import pandas` が欠落していたためインポートを追加

**PR #33: pivot空時のValueError修正（データ未登録メンバー選択時）**（デプロイ済み）

- `filtered` が空の場合 `pivot_table` がカラムなし DataFrame を返し `pivot.loc[disp]=0` が ValueError になる問題を修正
- 空 pivot の場合は年間合計=0 の DataFrame を直接作成するよう変更

**PR #32: 月次報酬ダッシュボードでデータ未登録メンバーを0値で表示**（デプロイ済み）

- `load_all_members()` に `members` テーブルを追加し全登録メンバーをサイドバーに表示
- Tab1の pivot テーブル・詳細テーブルにデータ未登録メンバーの0値行を追加
- メンバー明示選択時のみ0値行を追加（未選択時の大量0行を防止）

**PR #30: メンバー検索でニックネームに加え本名(full_name)でも絞り込み可能に**（デプロイ済み）

- `dashboard.py` / `check_management.py` でメンバーチェックボックスフィルターを `nickname` のみから `nickname OR full_name` に拡張

**PR #28: st.bar_chart() を altair に置換しVega-Lite警告を解消**（デプロイ済み）

- Tab1（月次推移）とTab2（活動分類別金額）の `st.bar_chart()` を `st.altair_chart()` に置換
- `st.bar_chart()` の内部で追加されるVega-Liteのscale bindings（離散軸で "Infinite extent"/"Scale bindings unsupported" 警告）を除外

**PR #27: 月次推移チャートの空データガードを追加**（デプロイ済み）

- Tab1月次推移チャートで `filtered` が空の場合に `st.bar_chart()` が空DataFrameで呼ばれる問題を修正
- `if not filtered.empty:` ガードを追加し、データなし時は infoメッセージを表示

**PR #26: ヘルプ・アーキテクチャページのドキュメント整合性修正**（デプロイ済み）

1. **`dashboard/pages/help.py`**: 実装との不一致4箇所を修正
   - タブ数: 3タブ → 4タブ（グループ別タブを追加記載）
   - フィルター: グループ別フィルターの説明を追加
   - デフォルト期間: 「最新月」 → 「最新年・全月」に修正
   - キャッシュ時間: 5分 → 1時間に修正
2. **`dashboard/pages/architecture.py`**: 2箇所修正 + セキュリティセクション新規追加
   - BQテーブル数: 6 → 7（groups_master追加後の正しい数）
   - セキュリティアーキテクチャセクション追加（4層構成図・制御一覧・データ保護フロー・シークレット管理・今後の改善候補）

PR #26〜#46 全てデプロイ済み（Collector rev 00020-g6b / Dashboard rev 00079-tl7）。

### 直近の変更（2026-02-28）

1. **dashboard_usersに30名追加**: 役職手当率が設定されているメンバー（トモゾウ除外）のうち未登録の30名をviewerロールで一括登録。合計44名（admin 8 / checker 3 / viewer 33）。
2. **管理設定JST修正（Issue #24, PR #25）**: `admin_settings.py` の BQテーブル最終更新時間を UTC→JST 変換。`table.modified.replace(tzinfo=timezone.utc).astimezone(JST)` で変換。
3. **CLAUDE.mdにダッシュボードデプロイ手順追記**: `--allow-unauthenticated` 必須の注意書き付き。

**解決済み**: 管理設定JST変換のコードは正しい。BQ Python client の `table.modified` は `_EPOCH(UTC-aware) + timedelta` で返されるため timezone-aware (UTC)。`replace(tzinfo=UTC)` は実質no-opだが `.astimezone(JST)` で正しくJST変換される。2026-03-07 ソースコード調査で確認。

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

<!-- 旧変更履歴（PR #9〜#14、Phase 5）はアーカイブへ移動済み。git log参照 -->

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
# ビルド（dashboard/ ディレクトリから実行）
gcloud builds submit --tag asia-northeast1-docker.pkg.dev/monthly-pay-tax/cloud-run-images/pay-dashboard

# デプロイ
# ⚠️ --allow-unauthenticated 必須（Streamlit OIDCが内部でOAuth認証を処理するため）
# --no-allow-unauthenticated にすると403エラーでアクセス不可になる
gcloud run deploy pay-dashboard \
  --image asia-northeast1-docker.pkg.dev/monthly-pay-tax/cloud-run-images/pay-dashboard \
  --platform managed --region asia-northeast1 --memory 512Mi \
  --allow-unauthenticated
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
12. ~~**ダッシュボード各テーブルにURLリンク追加**~~: ✅ 完了（rev 00052-tcb）
13. ~~**アーキテクチャ図を最新状態に更新**~~: ✅ 完了（rev 00053-4cx）
14. ~~**メンバー検索でニックネームに加え本名でも絞り込み可能に**~~: ✅ 完了（PR #30）
15. ~~**データ未登録メンバーを0値で表示**~~: ✅ 完了（PR #32/#33/#34/#35: 4段階修正）
16. ~~**Dashboard + Collector 再デプロイ**~~: ✅ 完了（Collector rev 00020-g6b / Dashboard rev 00078-hm4、BQ `source_group` 列追加済み）
17. ~~**管理設定JST修正確認**~~: ✅ 解決済み（BQ client の `table.modified` は UTC-aware、コードは正しくJST変換される。2026-03-07確認）

### デプロイ済み状態

- **Collector**: rev 00020-g6b（PR #38: グループ同期 Step 5 + source_group 列書き込み）
  - rev 00019-hlp: グループ更新を POST / に統合
  - rev 00018-pbj: グループ機能 + /update-groups エンドポイント
  - rev 00017: db-dtypes 追加（BQ to_dataframe 依存）
  - rev 00014: レート制限改善（throttle 0.5s + num_retries=5）
- **Dashboard**: rev 00144-q9z（人数・件数バッジ追加）
  - rev 00142-kr2: 操作ログ2行表示バグ修正
  - rev 00141-6ls: 操作ログ未選択状態対応
  - rev 00140-rs8: 手動データ更新ボタン・操作ログ最終保存者デフォルト
  - rev 00139-bmf: TTL延長のみ再適用（1時間→6時間）
  - rev 00138-hvs: 安定状態へリバート（モバイル修正後）
  - rev 00131-gbc: モバイル ピボットテーブル修正
  - rev 00079-tl7: PR #26〜#46 全てデプロイ済み、ダッシュボード名変更反映
  - rev 00053-4cx: アーキテクチャ図を最新状態に更新
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
- **BQ Table**: withholding_targets, dashboard_users（source_group列追加済み）, check_logs, groups_master デプロイ済み
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

**dashboard_users**: email, role, display_name, added_by, source_group, created_at, updated_at

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
