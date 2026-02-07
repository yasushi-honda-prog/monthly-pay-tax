"""Google Sheets APIデータ取得モジュール

GASのconsolidateReports/getSheetData_/findLastRow_をPythonに移植。
Domain-Wide Delegation認証でSheets API v4を使用。
"""

import logging
import re

from google.oauth2 import service_account
from googleapiclient.discovery import build

import config

logger = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/spreadsheets.readonly"]


def _build_sheets_service():
    """DWD認証でSheets APIサービスを構築

    ローカル: SA_KEY_PATHからキーファイル読み込み
    Cloud Run: IAM signBlob API経由でキーレスDWD（Workload Identity）
    """
    sa_email = config.SA_EMAIL

    if config.SA_KEY_PATH:
        # ローカル開発: キーファイルから直接
        credentials = service_account.Credentials.from_service_account_file(
            config.SA_KEY_PATH, scopes=SCOPES, subject=config.DELEGATE_USER_EMAIL
        )
    else:
        # Cloud Run: IAM signBlob APIでキーレスDWD
        import google.auth
        from google.auth import iam
        from google.auth.transport import requests as google_requests

        base_credentials, _ = google.auth.default()
        base_credentials.refresh(google_requests.Request())

        signer = iam.Signer(
            request=google_requests.Request(),
            credentials=base_credentials,
            service_account_email=sa_email,
        )
        credentials = service_account.Credentials(
            signer=signer,
            service_account_email=sa_email,
            token_uri="https://oauth2.googleapis.com/token",
            scopes=SCOPES,
            subject=config.DELEGATE_USER_EMAIL,
        )

    return build("sheets", "v4", credentials=credentials, cache_discovery=False)


def _extract_spreadsheet_id(url: str) -> str:
    """スプレッドシートURLからIDを抽出"""
    match = re.search(r"/spreadsheets/d/([a-zA-Z0-9_-]+)", url)
    if not match:
        raise ValueError(f"Invalid spreadsheet URL: {url}")
    return match.group(1)



def get_url_list(service) -> list[str]:
    """管理表からURLリストを取得（GAS Step 1に対応）"""
    sheet = service.spreadsheets()
    result = sheet.values().get(
        spreadsheetId=config.MASTER_SPREADSHEET_ID,
        range=f"'{config.MASTER_SHEET_NAME}'!A{config.URL_START_ROW}:A",
    ).execute()

    values = result.get("values", [])
    urls = []
    for row in values:
        if row and row[0]:
            url = row[0].strip()
            should_skip = any(url.startswith(skip) for skip in config.SKIP_URLS)
            if not should_skip:
                urls.append(url)

    logger.info("管理表から %d 件のURLを取得しました", len(urls))
    return urls


def get_sheet_data(
    service, spreadsheet_id: str, sheet_name: str, start_row: int, end_column: str
) -> list[list]:
    """シートからデータを取得（GAS getSheetData_に対応）

    B列~end_column列のstart_row行以降を取得し、B列が空でない行をフィルタリング。
    """
    range_notation = f"'{sheet_name}'!B{start_row}:{end_column}"

    try:
        result = service.spreadsheets().values().get(
            spreadsheetId=spreadsheet_id,
            range=range_notation,
        ).execute()
    except Exception:
        logger.warning("シート '%s' が見つからないか読み取れません", sheet_name)
        return []

    values = result.get("values", [])

    # B列（index 0）が空でない行のみ（GASのフィルタリングに対応）
    filtered = [row for row in values if row and row[0]]

    return filtered


def collect_all_data(service) -> dict[str, list[list]]:
    """全スプレッドシートからデータを収集（GAS Step 2に対応）

    Returns:
        {"gyomu_reports": [[url, b, c, ...], ...], "hojo_reports": [...]}
    """
    urls = get_url_list(service)

    all_data: dict[str, list[list]] = {}
    for cfg in config.SHEET_CONFIGS:
        all_data[cfg["bq_table"]] = []

    for i, url in enumerate(urls):
        progress = f"({i + 1}/{len(urls)})"
        logger.info("[処理中 %s] %s", progress, url)

        try:
            spreadsheet_id = _extract_spreadsheet_id(url)
        except ValueError as e:
            logger.warning("[スキップ %s] URL解析エラー: %s", progress, e)
            continue

        for cfg in config.SHEET_CONFIGS:
            try:
                data = get_sheet_data(
                    service,
                    spreadsheet_id,
                    cfg["report_sheet_name"],
                    cfg["data_start_row"],
                    cfg["data_end_column"],
                )
                if data:
                    # 各行の先頭にURLを付加（GASと同じ）
                    data_with_url = [[url] + row for row in data]
                    all_data[cfg["bq_table"]].extend(data_with_url)
                    logger.info(
                        "  '%s': %d行取得 (合計: %d行)",
                        cfg["report_sheet_name"],
                        len(data),
                        len(all_data[cfg["bq_table"]]),
                    )
                else:
                    logger.info("  '%s': 0行", cfg["report_sheet_name"])
            except Exception as e:
                logger.warning(
                    "  [シートエラー] '%s': %s", cfg["report_sheet_name"], e
                )

    return all_data


def run_collection() -> dict[str, list[list]]:
    """データ収集のエントリポイント"""
    service = _build_sheets_service()
    return collect_all_data(service)
