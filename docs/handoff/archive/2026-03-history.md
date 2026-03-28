# ハンドオフ変更履歴アーカイブ - 2026年3月以前

アーカイブ日: 2026-03-28
元ファイル: docs/handoff/LATEST.md（行200〜290相当）

---

## 直近の変更（2026-03-01）

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

**PR #28: st.bar_chart() を altair に置換しVega-Lite警告を解消**（デプロイ済み）

**PR #27: 月次推移チャートの空データガードを追加**（デプロイ済み）

**PR #26: ヘルプ・アーキテクチャページのドキュメント整合性修正**（デプロイ済み）

---

## 直近の変更（2026-02-28）

1. **dashboard_usersに30名追加**: 役職手当率が設定されているメンバー（トモゾウ除外）のうち未登録の30名をviewerロールで一括登録。合計44名（admin 8 / checker 3 / viewer 33）。
2. **管理設定JST修正（Issue #24, PR #25）**: `admin_settings.py` の BQテーブル最終更新時間を UTC→JST 変換。
3. **CLAUDE.mdにダッシュボードデプロイ手順追記**: `--allow-unauthenticated` 必須の注意書き付き。

**解決済み**: 管理設定JST変換のコードは正しい。BQ Python client の `table.modified` は `_EPOCH(UTC-aware) + timedelta` で返されるため timezone-aware (UTC)。

---

## 直近の変更（2026-02-22）

**`dashboard/pages/dashboard.py`**: ダッシュボード各テーブルにスプレッドシートURLリンクを追加

---

## 直近の変更（2026-02-21 - Googleグループ機能）

**PR #23: メンバーのGoogleグループ所属収集 + PR #22: groups_masterテーブル + グループ別Tab**

1. `cloud-run/sheets_collector.py`: `collect_member_groups()` で Admin Directory API からグループ一覧を取得
2. `cloud-run/main.py`: `/update-groups` エンドポイント追加 + グループ更新を POST / に統合（rev 00019-hlp）
3. `cloud-run/config.py`: `BQ_TABLE_GROUPS_MASTER = "groups_master"` 追加
4. `infra/bigquery/schema.sql`: `groups_master` テーブル定義追加
5. `dashboard/pages/dashboard.py`: Tab 4「グループ別」追加（3サブタブ）
6. `db-dtypes` パッケージ追加（BQ `to_dataframe` に必要）
7. `@st.fragment` でグループ選択時のタブリセットを防止（rev 00050-qbh）
8. `load_member_name_map()` 追加、メンバー名を「ニックネーム（本名）」形式で統一（rev 00051-l7v）

**PR #38: グループ単位のユーザー一括登録 + 定時自動同期**（337bbd7、デプロイ済み）

- `dashboard_users` に `source_group` 列追加
- ユーザー管理UI: グループ選択→プレビュー→一括登録
- `cloud-run/bq_loader.py`: `sync_dashboard_users_from_groups()` 追加
- `cloud-run/main.py`: 定時更新 Step 5 で自動同期
- ユニットテスト14件追加

**PR #39/#40: BQ予約語 GROUPS をバッククォートでエスケープ**（0846a95）

**PR #41/#42: グループプレビューの重複表示を DISTINCT で解消**（d8d530d）

**PR #43/#44: グループ一括登録にプログレスバーを追加**（b3fefff）

**PR #45: アーキテクチャ図にグループ一括登録・自動同期を反映**（d18c8fe）

---

## 直近の変更（2026-02-16 rev 00048）

**Sidebar UX Reorganization (rev 00048)**
- サイドバー構造の最適化: 期間・メンバー選択を上部に、ユーザー情報・ログアウトを下部に移動

---

## 直近の変更（rev 00045-00047）

**PR #19: 業務チェック欠落カラム追加 + ヘルプページリデザイン（rev 00047）**

1. 業務チェック管理表のカラム補完: URL、当月入力完了、DX領収書、立替領収書
2. ヘルプページ全面リデザイン: @keyframes 3種、クイックスタート3ステップカード、FAQ拡充

**PR #18: 業務チェック管理表 テーブル直接編集化（rev 00041）**

- `st.data_editor()` で即時保存・競合エラー対応

**PR #17: 業務チェック管理表 UX改善（rev 00039）**

- 進捗バー、ステータスボタン化、「次の未確認へ」ナビ

**PR #16: DRYリファクタ + サイドバーUI統一（rev 00038）**

- `lib/ui_helpers.py` 新規作成: `render_kpi`, `clean_numeric_scalar/series`, `render_sidebar_year_month`

**PR #15: 業務チェック管理表（rev 00037）**

- BQテーブル `check_logs` 追加
- checkerロール追加
- 新ページ `check_management.py`
- 状態遷移: 未確認 → 確認中 → 確認完了 / 差戻し

---

（PR #9〜#14、Phase 5以前はgit logを参照）
