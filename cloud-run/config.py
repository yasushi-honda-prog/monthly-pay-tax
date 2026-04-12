"""アプリケーション設定"""

import os

# GCPプロジェクト
GCP_PROJECT_ID = os.environ.get("GCP_PROJECT_ID", "monthly-pay-tax")

# BigQuery
BQ_DATASET = os.environ.get("BQ_DATASET", "pay_reports")
BQ_TABLE_GYOMU = "gyomu_reports"
BQ_TABLE_HOJO = "hojo_reports"
BQ_TABLE_MEMBERS = "members"
BQ_TABLE_GROUPS_MASTER = "groups_master"
BQ_TABLE_REIMBURSEMENT = "reimbursement_items"
BQ_TABLE_WAM_PROJECTS = "wam_target_projects"
BQ_TABLE_MEMBER_MASTER = "member_master"

# 管理表スプレッドシート
MASTER_SPREADSHEET_ID = "1fBNfkFBARSpT-OpLOytbAfoa0Xo5LTWv7irimssxcUU"
MASTER_SHEET_NAME = "報告シート（「説明用」以外はタダメンMから関数生成）M"
URL_COLUMN_INDEX = 0  # A列
URL_START_ROW = 2

# GASバインドスプレッドシート（旧タダメンMマスタの所在、参照用）
GAS_SPREADSHEET_ID = "16V9fs2kf2IzxdVz1GOJHY9mR1MmGjbmwm5L0ECiMLrc"

# タダメンMマスタ（管理表から直接読み取り、A:K列の完全データ）
MEMBER_SPREADSHEET_ID = MASTER_SPREADSHEET_ID  # 管理表に完全データあり
MEMBER_SHEET_NAME = "報告シート（「説明用」以外はタダメンMから関数生成）M"
MEMBER_START_ROW = 2  # 1行目はヘッダー

# タダメンMマスタ全量取得（タダメンMタブから口座・住所等を含む全有用データ）
MEMBER_MASTER_SHEET_NAME = "タダメンM"
MEMBER_MASTER_START_ROW = 2
# タダメンMタブの列インデックス(0-based) → member_masterカラムへのマッピング
MEMBER_MASTER_COLUMN_INDICES = [
    0,   # A: member_id
    1,   # B: last_name
    2,   # C: first_name
    3,   # D: last_name_kana
    4,   # E: first_name_kana
    5,   # F: nickname
    8,   # I: email
    9,   # J: postal_code
    10,  # K: prefecture
    11,  # L: address
    14,  # O: gws_account
    15,  # P: report_url_1
    16,  # Q: report_url_2
    19,  # T: shipping_postal_code
    20,  # U: shipping_address
    29,  # AD: qualification_allowance
    30,  # AE: position_rate
    31,  # AF: corporate_sheet
    32,  # AG: donation_sheet
    33,  # AH: qualification_sheet
    34,  # AI: bank1_type
    35,  # AJ: bank1_name
    36,  # AK: bank1_code
    37,  # AL: bank1_branch_name
    38,  # AM: bank1_branch_code
    39,  # AN: bank1_account_number
    40,  # AO: bank1_deposit_type
    41,  # AP: bank1_holder_name
    42,  # AQ: bank2_type
    43,  # AR: bank2_name
    44,  # AS: bank2_code
    45,  # AT: bank2_branch_name
    46,  # AU: bank2_branch_code
    47,  # AV: bank2_account_number
    48,  # AW: bank2_deposit_type
    49,  # AX: bank2_holder_name
]

# スキップ対象URL
SKIP_URLS = [
    "https://docs.google.com/spreadsheets/d/17PMx-smOoj2ZzsG7A6A4FGXEfxXiZGkukERXJc1Cbi0/edit",
]

# 立替金シート
REIMBURSEMENT_FOLDER_ID = "1jXs3cbO6gBvgDbotK0ODa9mL4x-iDooI"
REIMBURSEMENT_TAB_SUFFIX = "入力シート"
REIMBURSEMENT_DATA_START_ROW = 4
REIMBURSEMENT_NICKNAME_REGEX = r"【(.+?)】"

# Sheets API レート制限対策
SHEETS_API_NUM_RETRIES = 5
SHEETS_API_SLEEP_BETWEEN_REQUESTS = 0.5

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
        "qualification_allowance", "position_rate",
        "corporate_sheet", "donation_sheet",
        "qualification_sheet", "sheet_number",
        "groups",
    ],
    BQ_TABLE_GROUPS_MASTER: [
        "group_email", "group_name",
    ],
    BQ_TABLE_REIMBURSEMENT: [
        "source_url", "nickname",
        "marker", "year", "date",
        "target_project", "category", "payment_purpose",
        "payment_amount", "advance_amount",
        "from_station", "to_station",
        "visit_purpose", "receipt_url",
    ],
    BQ_TABLE_WAM_PROJECTS: [
        "target_project", "wam_flag", "note",
    ],
    BQ_TABLE_MEMBER_MASTER: [
        "member_id", "last_name", "first_name",
        "last_name_kana", "first_name_kana", "nickname",
        "email", "postal_code", "prefecture", "address",
        "gws_account", "report_url_1", "report_url_2",
        "shipping_postal_code", "shipping_address",
        "qualification_allowance", "position_rate",
        "corporate_sheet", "donation_sheet", "qualification_sheet",
        "bank1_type", "bank1_name", "bank1_code",
        "bank1_branch_name", "bank1_branch_code",
        "bank1_account_number", "bank1_deposit_type", "bank1_holder_name",
        "bank2_type", "bank2_name", "bank2_code",
        "bank2_branch_name", "bank2_branch_code",
        "bank2_account_number", "bank2_deposit_type", "bank2_holder_name",
    ],
}
