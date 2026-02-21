"""Google Sheets APIデータ取得モジュール

GASのconsolidateReports/getSheetData_/findLastRow_をPythonに移植。
Domain-Wide Delegation認証でSheets API v4を使用。
"""

import logging
import re
import time

import httplib2
import google_auth_httplib2
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

import config

logger = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/spreadsheets.readonly"]
ADMIN_SCOPES = ["https://www.googleapis.com/auth/admin.directory.group.readonly"]


def _get_dwd_credentials():
    """DWD認証情報を取得

    ローカル: SA_KEY_PATHからキーファイル読み込み
    Cloud Run: IAM signBlob API経由でキーレスDWD（Workload Identity）
    """
    sa_email = config.SA_EMAIL

    if config.SA_KEY_PATH:
        return service_account.Credentials.from_service_account_file(
            config.SA_KEY_PATH, scopes=SCOPES, subject=config.DELEGATE_USER_EMAIL
        )

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
    return service_account.Credentials(
        signer=signer,
        service_account_email=sa_email,
        token_uri="https://oauth2.googleapis.com/token",
        scopes=SCOPES,
        subject=config.DELEGATE_USER_EMAIL,
    )


def _build_sheets_service(timeout=60):
    """DWD認証でSheets APIサービスを構築"""
    credentials = _get_dwd_credentials()
    http = httplib2.Http(timeout=timeout)
    authorized_http = google_auth_httplib2.AuthorizedHttp(credentials, http=http)
    return build("sheets", "v4", http=authorized_http, cache_discovery=False)


def _get_admin_credentials():
    """Admin Directory API用DWD認証情報を取得

    DWD スコープに admin.directory.group.readonly が必要。
    Google管理コンソール → セキュリティ → APIコントロール → ドメイン全体の委任で設定。
    """
    sa_email = config.SA_EMAIL

    if config.SA_KEY_PATH:
        return service_account.Credentials.from_service_account_file(
            config.SA_KEY_PATH, scopes=ADMIN_SCOPES, subject=config.DELEGATE_USER_EMAIL
        )

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
    return service_account.Credentials(
        signer=signer,
        service_account_email=sa_email,
        token_uri="https://oauth2.googleapis.com/token",
        scopes=ADMIN_SCOPES,
        subject=config.DELEGATE_USER_EMAIL,
    )


def _build_admin_service(timeout=60):
    """DWD認証でAdmin Directory APIサービスを構築"""
    credentials = _get_admin_credentials()
    http = httplib2.Http(timeout=timeout)
    authorized_http = google_auth_httplib2.AuthorizedHttp(credentials, http=http)
    return build("admin", "directory_v1", http=authorized_http, cache_discovery=False)


def collect_member_groups(
    admin_service, gws_account: str
) -> tuple[str, list[tuple[str, str]]]:
    """Directory APIでメンバーのグループ一覧を取得

    ページネーションを考慮して全グループを取得する。
    エラー時は空文字列/空リストを返してバッチ全体を止めない。

    Returns:
        (カンマ区切りemailリスト, [(email, name), ...])
    """
    if not gws_account:
        return "", []
    try:
        group_pairs: list[tuple[str, str]] = []
        page_token = None
        while True:
            result = (
                admin_service.groups()
                .list(userKey=gws_account, pageToken=page_token, maxResults=200)
                .execute()
            )
            for g in result.get("groups", []):
                group_pairs.append((g["email"], g.get("name", g["email"])))
            page_token = result.get("nextPageToken")
            if not page_token:
                break
        time.sleep(config.SHEETS_API_SLEEP_BETWEEN_REQUESTS)
        emails_csv = ",".join(email for email, _ in group_pairs)
        return emails_csv, group_pairs
    except HttpError as e:
        logger.warning("グループ取得エラー (%s): %s", gws_account, e)
        return "", []
    except Exception as e:
        logger.warning("グループ取得エラー (%s): %s", gws_account, e)
        return "", []


def _extract_spreadsheet_id(url: str) -> str:
    """スプレッドシートURLからIDを抽出"""
    match = re.search(r"/spreadsheets/d/([a-zA-Z0-9_-]+)", url)
    if not match:
        raise ValueError(f"Invalid spreadsheet URL: {url}")
    return match.group(1)



def _execute_with_throttle(request, context: str = ""):
    """Sheets APIリクエストをスロットリング+リトライ付きで実行

    - time.sleep でリクエスト間隔を空け、レート制限(60 reads/min)内に収める
    - num_retries で429/5xx/ネットワークエラーをexponential backoffで自動リトライ
    - HttpError はログ出力後に再raise（呼び出し元の既存except処理に委ねる）
    """
    time.sleep(config.SHEETS_API_SLEEP_BETWEEN_REQUESTS)
    try:
        return request.execute(num_retries=config.SHEETS_API_NUM_RETRIES)
    except HttpError as e:
        status_code = e.resp.status if e.resp else None
        if status_code in (429, 500, 503):
            logger.error("[transient %s] %s (HTTP %s)", context, e, status_code)
        else:
            logger.warning("[permanent %s] %s (HTTP %s)", context, e, status_code)
        raise


def get_url_list(service) -> list[str]:
    """管理表からURLリストを取得（GAS Step 1に対応）"""
    sheet = service.spreadsheets()
    request = sheet.values().get(
        spreadsheetId=config.MASTER_SPREADSHEET_ID,
        range=f"'{config.MASTER_SHEET_NAME}'!A{config.URL_START_ROW}:A",
    )
    try:
        result = _execute_with_throttle(request, context="get_url_list")
    except Exception as e:
        logger.error("管理表URLリストの読み取りエラー: %s", e)
        return []

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
        request = service.spreadsheets().values().get(
            spreadsheetId=spreadsheet_id,
            range=range_notation,
        )
        result = _execute_with_throttle(request, context=f"get_sheet_data({sheet_name})")
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


def collect_members(service) -> list[list]:
    """タダメンMマスタを取得

    管理表のタダメンMシートからメンバー情報を取得。
    A~K列: 報告シートURL, タダメンID, ニックネーム, GWSアカウント, 本名,
           資格手当, 役職手当率, 法人シート, 寄付先シート, 資格手当加算先シート, シート番号
    """
    sheet = service.spreadsheets()
    range_notation = f"'{config.MEMBER_SHEET_NAME}'!A{config.MEMBER_START_ROW}:K"

    try:
        request = sheet.values().get(
            spreadsheetId=config.MEMBER_SPREADSHEET_ID,
            range=range_notation,
        )
        result = _execute_with_throttle(request, context="collect_members")
    except Exception as e:
        logger.error("タダメンMの読み取りエラー: %s", e)
        return []

    values = result.get("values", [])

    # A列（報告シートURL）が空でない行のみ、スキップURL除外
    filtered = []
    for row in values:
        if not row or not row[0]:
            continue
        url = row[0].strip()
        should_skip = any(url.startswith(skip) for skip in config.SKIP_URLS)
        if not should_skip and len(row) >= 2 and row[1]:  # IDがある行のみ
            filtered.append(row)

    logger.info("タダメンM: %d件のメンバーを取得しました", len(filtered))
    return filtered


def run_collection() -> dict[str, list[list]]:
    """データ収集のエントリポイント（シート収集のみ、グループ更新は /update-groups で実行）"""
    service = _build_sheets_service()
    # membersを先に読む（1 APIコールのみ、レート制限回避）
    members = collect_members(service)
    # groups列を空文字で埋めてカラム数を合わせる
    members_padded = [row + [""] for row in members]
    all_data = collect_all_data(service)
    all_data[config.BQ_TABLE_MEMBERS] = members_padded
    return all_data


def update_member_groups_from_bq() -> tuple[list[list], list[list]]:
    """BQのmembersテーブルを読み込み、Admin SDKでグループ情報を付加して返す

    /update-groups エンドポイントから呼び出す。
    シート再収集なしで ~2分で完了する。

    Returns:
        (updated_members, groups_master_rows)
        groups_master_rows: [[group_email, group_name], ...]（重複なし）
    """
    import bq_loader

    rows = bq_loader.read_members_from_bq()
    admin_service = _build_admin_service()

    columns = config.TABLE_COLUMNS[config.BQ_TABLE_MEMBERS]
    gws_idx = columns.index("gws_account")
    groups_idx = columns.index("groups")

    updated = []
    groups_dict: dict[str, str] = {}  # email → name（重複排除）

    for row in rows:
        row = list(row)
        gws_account = row[gws_idx] or ""
        emails_csv, group_pairs = collect_member_groups(admin_service, gws_account)
        row[groups_idx] = emails_csv
        updated.append(row)
        for email, name in group_pairs:
            groups_dict[email] = name

    groups_master = [[email, name] for email, name in groups_dict.items()]
    logger.info(
        "グループ情報を %d 件更新しました（ユニークグループ: %d）",
        len(updated),
        len(groups_master),
    )
    return updated, groups_master
