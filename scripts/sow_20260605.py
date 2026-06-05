"""SOW Google Doc タブ更新スクリプト - SOW-20260605-TDKY"""
import json
import subprocess
import urllib.request
import urllib.error

DOC_ID = "1-ZoJpStrmEngNZ60GMdgyppM3gzYKFIlA5szAp2SJYc"
TAB_ID = "t.9d3bghmcpx54"  # SOW-20260605-TDKY

def get_token():
    import os
    token = os.environ.get("SOW_TOKEN", "").strip()
    if token:
        return token
    gcloud_paths = [
        r"C:\Users\Yuri\AppData\Local\Google\Cloud SDK\google-cloud-sdk\bin\gcloud.cmd",
    ]
    for gcloud in gcloud_paths:
        if os.path.exists(gcloud):
            r = subprocess.run([gcloud, "auth", "print-access-token"], capture_output=True, text=True)
            if r.stdout.strip():
                return r.stdout.strip()
    raise RuntimeError("Could not get access token.")

def docs_request(method, path, body=None, token=None):
    url = f"https://docs.googleapis.com/v1/{path}"
    data = json.dumps(body).encode("utf-8") if body else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("Content-Type", "application/json; charset=utf-8")
    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        print(f"Error {e.code}: {e.read().decode()}")
        return None

def sheets_request(method, path, body=None, token=None):
    url = f"https://sheets.googleapis.com/v4/{path}"
    data = json.dumps(body).encode("utf-8") if body else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("Content-Type", "application/json; charset=utf-8")
    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        print(f"Sheets Error {e.code}: {e.read().decode()}")
        return None

def main():
    token = get_token()
    print(f"Token: {token[:20]}...")

    doc = docs_request("GET", f"documents/{DOC_ID}?includeTabsContent=true", token=token)
    if not doc:
        print("Failed to get document"); return

    tab = next((t for t in doc["tabs"] if t["tabProperties"]["tabId"] == TAB_ID), None)
    if not tab:
        print(f"Tab {TAB_ID} not found"); return

    body_content = tab["documentTab"]["body"]["content"]
    end_index = body_content[-1]["endIndex"]
    print(f"Tab endIndex: {end_index}")

    # Clear content
    if end_index > 2:
        result = docs_request("POST", f"documents/{DOC_ID}:batchUpdate", {
            "requests": [{"deleteContentRange": {"range": {
                "startIndex": 1, "endIndex": end_index - 1, "tabId": TAB_ID
            }}}]
        }, token=token)
        print(f"Cleared: {result is not None}")

    # SOW content
    FONT = "Noto Sans JP"
    sow_lines = [
        ("作業範囲記述書（SOW）", "TITLE", True, 26, "#1a1a1a"),
        ("タダカヨ 活動時間・報酬マネジメントダッシュボード ＜業務委託費分析ドリルダウン機能改善・隊並び順整理・コンソールエラー確認＞", "HEADING_1", True, 16, "#1a1a1a"),
        ("", "NORMAL_TEXT", False, 10.5, "#000000"),
        ("文書番号：SOW-20260605-TDKY", "NORMAL_TEXT", False, 10.5, "#000000"),
        ("対象システム：pay-dashboard（Cloud Run / Streamlit）", "NORMAL_TEXT", False, 10.5, "#000000"),
        ("報告日：2026年6月5日（金）", "NORMAL_TEXT", False, 10.5, "#000000"),
        ("作業期間：2026年6月5日（金）", "NORMAL_TEXT", False, 10.5, "#000000"),
        ("作成：Claude Code（AI開発支援）　初期開発：本田康志（ヤスス）", "NORMAL_TEXT", False, 10.5, "#000000"),
        ("作業者：しっかり法人を経営し隊／すごいシステムつくり隊　近藤ゆり（ゆり）", "NORMAL_TEXT", False, 10.5, "#000000"),
        ("サービスURL：https://pay-dashboard-209715990891.asia-northeast1.run.app", "NORMAL_TEXT", False, 10.5, "#000000"),
        ("", "NORMAL_TEXT", False, 10.5, "#000000"),
        ("1. エグゼクティブ・サマリー (Executive Summary)", "HEADING_2", True, 14, "#1565c0"),
        ("業務委託費分析タブのドリルダウン機能を強化した。業務分類別内訳の表に複数行選択フィルタを追加し、選択した業務分類に絞り込んで分類合計・メンバー数・グラフを確認できるようにした。あわせて円表記バグを修正し、グラフ・凡例の隊の並び順を業務別報酬単価表のスプレッドシート順に変更した。また、ダッシュボードのブラウザコンソールエラーを確認・分析し、アプリ起因のエラーがないことを確認した。", "NORMAL_TEXT", False, 10.5, "#000000"),
        ("", "NORMAL_TEXT", False, 10.5, "#000000"),
        ("2. プロジェクトの目的と背景 (Objectives & Background)", "HEADING_2", True, 14, "#1565c0"),
        ("2.1 背景", "HEADING_3", True, 12, "#333333"),
        ("隊を選択してドリルダウンを開いた際、業務分類別内訳の表が表示専用で、特定の業務分類を選択してもKPI（分類合計・メンバー数）やグラフが絞り込まれない問題があった。また隊の並び順がアルファベット順になっており、スプレッドシートとの対応がとれていなかった。", "NORMAL_TEXT", False, 10.5, "#000000"),
        ("2.2 目的", "HEADING_3", True, 12, "#333333"),
        ("業務分類別内訳の表で行を選択し、KPI・グラフをその業務分類に絞り込めるようにする", "NORMAL_TEXT", False, 10.5, "#000000"),
        ("複数業務分類の同時選択・合算表示を可能にする", "NORMAL_TEXT", False, 10.5, "#000000"),
        ("グラフ・凡例の隊の並び順をスプレッドシートに合わせる", "NORMAL_TEXT", False, 10.5, "#000000"),
        ("コンソールエラーの確認・分析を行い、アプリ起因のエラーがないことを確認する", "NORMAL_TEXT", False, 10.5, "#000000"),
        ("", "NORMAL_TEXT", False, 10.5, "#000000"),
        ("3. 実施内容詳細 (Technical Scope of Work)", "HEADING_2", True, 14, "#1565c0"),
        ("3.1 業務分類別内訳 行選択フィルタ追加（PR #168）", "HEADING_3", True, 12, "#333333"),
        ("変更前: 表は表示専用、KPI・グラフは常に隊全体の合計", "NORMAL_TEXT", False, 10.5, "#000000"),
        ("変更後: 行を選択（複数可）するとKPI・グラフが選択した業務分類に絞り込まれる", "NORMAL_TEXT", False, 10.5, "#000000"),
        ("対応: PC版（_render_cost_chart）・モバイル版（_render_cost_chart_mobile）両方に対応", "NORMAL_TEXT", False, 10.5, "#000000"),
        ("3.2 円表記バグ修正・複数選択対応（PR #169）", "HEADING_3", True, 12, "#333333"),
        ("不具合: column_config.NumberColumn(format=\"¥{:,.0f}\")がリテラル表示されていた", "NORMAL_TEXT", False, 10.5, "#000000"),
        ("修正: style.format()に変更して正しく¥1,000形式で表示", "NORMAL_TEXT", False, 10.5, "#000000"),
        ("追加: selection_mode=\"multi-row\"で複数業務分類の同時選択が可能に", "NORMAL_TEXT", False, 10.5, "#000000"),
        ("3.3 on_select 選択不具合修正（PR #170）", "HEADING_3", True, 12, "#333333"),
        ("不具合: Stylerオブジェクトを渡すとon_selectが動作しないStreamlitの制約", "NORMAL_TEXT", False, 10.5, "#000000"),
        ("修正: apply(lambda x: f\"¥{x:,.0f}\")で事前フォーマット済み文字列列に変換してから渡す", "NORMAL_TEXT", False, 10.5, "#000000"),
        ("3.4 隊分類の並び順をスプレッドシート順に変更（PR #171）", "HEADING_3", True, 12, "#333333"),
        ("変更前: sorted()による五十音順", "NORMAL_TEXT", False, 10.5, "#000000"),
        ("変更後: 業務別報酬単価表（gid=700881857）の隊分類の並び順に一致", "NORMAL_TEXT", False, 10.5, "#000000"),
        ("対象: グラフの積み上げ順・凡例・ピボット表の行順", "NORMAL_TEXT", False, 10.5, "#000000"),
        ("3.5 コンソールエラー確認（診断作業）", "HEADING_3", True, 12, "#333333"),
        ("chrome-extension:// ERR_FAILED（5件）: ブラウザ拡張機能のリソース読み込みエラー → 対応不要", "NORMAL_TEXT", False, 10.5, "#000000"),
        ("Google iframe sandbox警告（1件）: Google DriveのiFrame設定に関するブラウザ警告 → 対応不要", "NORMAL_TEXT", False, 10.5, "#000000"),
        ("結論: ダッシュボードアプリケーション自体にエラーなし", "NORMAL_TEXT", False, 10.5, "#000000"),
        ("", "NORMAL_TEXT", False, 10.5, "#000000"),
        ("4. 技術的成果物 (Deliverables)", "HEADING_2", True, 14, "#1565c0"),
        ("dashboard/_pages/dashboard.py 更新（PR #168 / #169 / #170 / #171）", "NORMAL_TEXT", False, 10.5, "#000000"),
        ("  — 業務分類別内訳 on_select/multi-row / 円表記修正 / _COST_COLOR_DOMAIN スプレッドシート順", "NORMAL_TEXT", False, 10.5, "#000000"),
        ("docs/sow/SOW_20260605_業務委託費分析ドリルダウン機能改善.md 作成・git push 完了", "NORMAL_TEXT", False, 10.5, "#000000"),
        ("", "NORMAL_TEXT", False, 10.5, "#000000"),
        ("5. 品質保証と受入基準 (Quality Assurance & Acceptance)", "HEADING_2", True, 14, "#1565c0"),
        ("CI テスト全PASS（Dashboard 338 + Cloud Run 100 = 438件、4PR全て）", "NORMAL_TEXT", False, 10.5, "#000000"),
        ("業務分類別内訳の行を選択 → 分類合計・メンバー数・グラフが絞り込まれる", "NORMAL_TEXT", False, 10.5, "#000000"),
        ("複数選択時は合算が表示される", "NORMAL_TEXT", False, 10.5, "#000000"),
        ("グラフ・凡例の隊の並び順がスプレッドシートと一致する", "NORMAL_TEXT", False, 10.5, "#000000"),
        ("ブラウザコンソールにアプリ起因のエラーなし", "NORMAL_TEXT", False, 10.5, "#000000"),
        ("", "NORMAL_TEXT", False, 10.5, "#000000"),
        ("6. 今後の推奨事項 (Recommendations)", "HEADING_2", True, 14, "#1565c0"),
        ("業務分類の並び順（現在は金額の大きい順）は現状維持", "NORMAL_TEXT", False, 10.5, "#000000"),
        ("他タブ（業務報告一覧・グループ別等）の隊分類対応はユーザー要望が出た際に対応", "NORMAL_TEXT", False, 10.5, "#000000"),
        ("コンソールエラーは定期的に /check-console コマンドで確認する", "NORMAL_TEXT", False, 10.5, "#000000"),
        ("", "NORMAL_TEXT", False, 10.5, "#000000"),
        ("デプロイ履歴", "HEADING_2", True, 14, "#1565c0"),
        ("#168 行選択フィルタ追加: 2026-06-05（JST）", "NORMAL_TEXT", False, 10.5, "#000000"),
        ("#169 円表記修正・複数選択: 2026-06-05（JST）", "NORMAL_TEXT", False, 10.5, "#000000"),
        ("#170 on_select修正: 2026-06-05（JST）", "NORMAL_TEXT", False, 10.5, "#000000"),
        ("#171 隊並び順整理: 2026-06-05（JST）", "NORMAL_TEXT", False, 10.5, "#000000"),
        ("", "NORMAL_TEXT", False, 10.5, "#000000"),
        ("コミット数", "HEADING_2", True, 14, "#1565c0"),
        ("本日合計：5コミット", "NORMAL_TEXT", True, 10.5, "#000000"),
        ("4f69d2e  feat(dashboard): 業務委託費分析の内訳表に行選択フィルタを追加", "NORMAL_TEXT", False, 10.5, "#000000"),
        ("428f0cb  fix(dashboard): 内訳表の円表記修正・複数選択対応", "NORMAL_TEXT", False, 10.5, "#000000"),
        ("fa1168e  fix(dashboard): Stylerをやめて事前フォーマット列でon_selectを修正", "NORMAL_TEXT", False, 10.5, "#000000"),
        ("a381721  feat(dashboard): 業務委託費分析の隊分類をスプレッドシート順に並び替え", "NORMAL_TEXT", False, 10.5, "#000000"),
        ("1c73436  docs: SOW-20260605 業務委託費分析ドリルダウン機能改善", "NORMAL_TEXT", False, 10.5, "#000000"),
        ("以上", "NORMAL_TEXT", True, 10.5, "#000000"),
    ]

    requests = []
    current_index = 1

    for text, style, bold, size, color in sow_lines:
        insert_text = text + "\n"
        text_len = len(insert_text)

        requests.append({"insertText": {
            "location": {"index": current_index, "tabId": TAB_ID},
            "text": insert_text
        }})

        heading_map = {"TITLE": "TITLE", "HEADING_1": "HEADING_1",
                       "HEADING_2": "HEADING_2", "HEADING_3": "HEADING_3",
                       "NORMAL_TEXT": "NORMAL_TEXT"}
        requests.append({"updateParagraphStyle": {
            "range": {"startIndex": current_index, "endIndex": current_index + text_len, "tabId": TAB_ID},
            "paragraphStyle": {"namedStyleType": heading_map[style], "alignment": "START"},
            "fields": "namedStyleType,alignment"
        }})

        if text:
            requests.append({"updateTextStyle": {
                "range": {"startIndex": current_index, "endIndex": current_index + text_len - 1, "tabId": TAB_ID},
                "textStyle": {
                    "bold": bold,
                    "fontSize": {"magnitude": size, "unit": "PT"},
                    "foregroundColor": {"color": {"rgbColor": {
                        "red": int(color[1:3], 16) / 255,
                        "green": int(color[3:5], 16) / 255,
                        "blue": int(color[5:7], 16) / 255
                    }}},
                    "weightedFontFamily": {"fontFamily": FONT}
                },
                "fields": "bold,fontSize,foregroundColor,weightedFontFamily"
            }})

        current_index += text_len

    batch_size = 50
    total = len(requests)
    print(f"Total requests: {total}")

    for i in range(0, total, batch_size):
        batch = requests[i:i+batch_size]
        result = docs_request("POST", f"documents/{DOC_ID}:batchUpdate",
                              {"requests": batch}, token=token)
        if result:
            print(f"Batch {i//batch_size+1}/{(total+batch_size-1)//batch_size}: OK")
        else:
            print(f"Batch {i//batch_size+1}: FAILED"); return

    # SOW管理スプレッドシートに追記
    SS_ID = "1MWXDcissrUBJcpp0RsvpOW9I7jO_XM7BumBo-TD6YRE"
    ss = sheets_request("GET", f"spreadsheets/{SS_ID}/values/A:D", token=token)
    if ss:
        last_row = len(ss.get("values", [])) + 1
        sheets_request("PUT", f"spreadsheets/{SS_ID}/values/A{last_row}:D{last_row}?valueInputOption=USER_ENTERED", {
            "values": [["2026/06/05", "#168-#171", "業務委託費分析ドリルダウン機能改善・隊並び順整理・コンソールエラー確認", "SOW-20260605-TDKY"]]
        }, token=token)
        print(f"SOW管理シート 行{last_row} 追記完了")

    print("完了!")

if __name__ == "__main__":
    main()
