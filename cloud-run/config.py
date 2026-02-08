"""アプリケーション設定"""

import os

# GCPプロジェクト
GCP_PROJECT_ID = os.environ.get("GCP_PROJECT_ID", "monthly-pay-tax")

# BigQuery
BQ_DATASET = os.environ.get("BQ_DATASET", "pay_reports")
BQ_TABLE_GYOMU = "gyomu_reports"
BQ_TABLE_HOJO = "hojo_reports"
BQ_TABLE_MEMBERS = "members"

# 管理表スプレッドシート
MASTER_SPREADSHEET_ID = "1fBNfkFBARSpT-OpLOytbAfoa0Xo5LTWv7irimssxcUU"
MASTER_SHEET_NAME = "報告シート（「説明用」以外はタダメンMから関数生成）M"
URL_COLUMN_INDEX = 0  # A列
URL_START_ROW = 2

# GASバインドスプレッドシート（タダメンMマスタの所在）
GAS_SPREADSHEET_ID = "16V9fs2kf2IzxdVz1GOJHY9mR1MmGjbmwm5L0ECiMLrc"
MEMBER_SHEET_NAME = "タダメンM"
MEMBER_START_ROW = 2  # 1行目はヘッダー

# スキップ対象URL
SKIP_URLS = [
    "https://docs.google.com/spreadsheets/d/17PMx-smOoj2ZzsG7A6A4FGXEfxXiZGkukERXJc1Cbi0/edit",
]

# サービスアカウント
SA_EMAIL = os.environ.get("SA_EMAIL", "pay-collector@monthly-pay-tax.iam.gserviceaccount.com")
SA_KEY_PATH = os.environ.get("SA_KEY_PATH", "")  # ローカル開発用のみ

# Domain-Wide Delegation 対象ユーザー
DELEGATE_USER_EMAIL = os.environ.get("DELEGATE_USER_EMAIL", "yasushi-honda@tadakayo.jp")

# シート設定（GASのsheetConfigsに対応）
SHEET_CONFIGS = [
    {
        "report_sheet_name": "【都度入力】業務報告",
        "bq_table": BQ_TABLE_GYOMU,
        "data_start_row": 7,  # 1-indexed
        "data_end_column": "K",  # B~K列 = 10列
        "num_columns": 10,
    },
    {
        "report_sheet_name": "【月１入力】補助＆立替報告＋月締め",
        "bq_table": BQ_TABLE_HOJO,
        "data_start_row": 4,  # 1-indexed
        "data_end_column": "K",  # B~K列 = 10列
        "num_columns": 10,
    },
]

# テーブル別カラム名定義
TABLE_COLUMNS = {
    BQ_TABLE_GYOMU: [
        "source_url",
        "year", "date", "day_of_week",
        "activity_category", "work_category", "sponsor",
        "description", "unit_price", "hours", "amount",
    ],
    BQ_TABLE_HOJO: [
        "source_url",
        "year", "month", "hours",
        "compensation", "dx_subsidy", "reimbursement",
        "total_amount", "monthly_complete", "dx_receipt", "expense_receipt",
    ],
    BQ_TABLE_MEMBERS: [
        "report_url", "member_id", "nickname",
        "gws_account", "full_name",
    ],
}
