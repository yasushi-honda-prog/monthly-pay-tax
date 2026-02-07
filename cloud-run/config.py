"""アプリケーション設定"""

import os

# GCPプロジェクト
GCP_PROJECT_ID = os.environ.get("GCP_PROJECT_ID", "monthly-pay-tax")

# BigQuery
BQ_DATASET = os.environ.get("BQ_DATASET", "pay_reports")
BQ_TABLE_GYOMU = "gyomu_reports"
BQ_TABLE_HOJO = "hojo_reports"

# 管理表スプレッドシート
MASTER_SPREADSHEET_ID = "1fBNfkFBARSpT-OpLOytbAfoa0Xo5LTWv7irimssxcUU"
MASTER_SHEET_NAME = "報告シート（「説明用」以外はタダメンMから関数生成）M"
URL_COLUMN_INDEX = 0  # A列
URL_START_ROW = 2

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
