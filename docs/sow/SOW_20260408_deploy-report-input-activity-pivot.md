# 作業報告書（SOW）

プロジェクト: タダカヨ 活動時間・報酬マネジメントダッシュボード
対象システム: pay-dashboard（Cloud Run / Streamlit）
作業日: 2026年4月8日（水）
作業者: Claude Code（AI開発支援）

---

## 作業概要

コミット済み・未デプロイだった報告入力機能（PR #51）およびTab1メンバー別月次活動時間ピボット（b786eed）を本番環境へ一括デプロイした。合わせてBigQueryに app_gyomu_reports / app_hojo_reports テーブルを新規作成した。

---

## 実施内容

### 1. BigQuery テーブル作成

| 項目 | 内容 |
|------|------|
| app_gyomu_reports | アプリ入力業務報告テーブル（新規作成） |
| app_hojo_reports | アプリ入力補助報告テーブル（新規作成） |
| 定義元 | infra/bigquery/schema.sql（CREATE TABLE IF NOT EXISTS） |

### 2. 報告入力機能デプロイ（PR #51）

| 項目 | 内容 |
|------|------|
| dashboard/pages/report_input.py | 新規: 業務報告（日次）・補助報告（月次）の入力ページ |
| dashboard/app.py | user_pages リスト追加・user ロール対応ナビゲーション |
| dashboard/lib/auth.py | require_user() 追加（user/viewer/checker/admin を許可） |
| dashboard/lib/constants.py | APP_GYOMU_TABLE / APP_HOJO_TABLE 定数追加 |
| dashboard/pages/user_management.py | ロール選択肢に user を追加（3箇所） |
| アクセス権 | user / viewer / checker / admin |
| データ保存先 | pay_reports.app_gyomu_reports / pay_reports.app_hojo_reports |

### 3. Tab1 メンバー別月次活動時間ピボット（b786eed）

| 項目 | 内容 |
|------|------|
| dashboard/pages/dashboard.py | Tab1「月別報酬サマリー」サブタブを 4→5 に拡張 |
| 新サブタブ | 「メンバー別 月次活動時間」（total_work_hours の月×メンバーピボット） |
| 表示形式 | 小数1桁（{:,.1f}） |

---

## デプロイ履歴

| リビジョン | 内容 |
|-----------|------|
| pay-dashboard-TBD | 報告入力機能 + Tab1 活動時間ピボット 一括デプロイ |

---

## コミット数

- 本日合計: **0 コミット**（デプロイのみ、コード変更なし）

---

## 変更ファイル

- `dashboard/pages/report_input.py` — 新規: 報告入力ページ（業務/補助）
- `dashboard/app.py` — user ロール対応ナビゲーション追加
- `dashboard/lib/auth.py` — require_user() 追加
- `dashboard/lib/constants.py` — APP_GYOMU_TABLE / APP_HOJO_TABLE 追加
- `dashboard/pages/user_management.py` — user ロール選択肢追加
- `dashboard/tests/test_pages_report_input.py` — 報告入力テスト（9件）
- `dashboard/tests/conftest.py` — st.tabs / mock_columns(int) 対応追加
- `infra/bigquery/schema.sql` — app_gyomu_reports / app_hojo_reports テーブル定義追加

---

## サービス情報

サービスURL: https://pay-dashboard-209715990891.asia-northeast1.run.app
