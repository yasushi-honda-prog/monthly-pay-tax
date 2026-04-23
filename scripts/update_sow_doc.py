"""
SOW Google Doc タブ更新スクリプト
TAB: SOW-20260424-TDKY (t.mn1xtqult6qj)
"""
import json
import subprocess
import urllib.request
import urllib.error

DOC_ID = "1-ZoJpStrmEngNZ60GMdgyppM3gzYKFIlA5szAp2SJYc"
TAB_ID = "t.mn1xtqult6qj"

def get_token():
    import os
    token = os.environ.get("SOW_TOKEN", "").strip()
    if token:
        return token
    # Try gcloud paths
    gcloud_paths = [
        r"C:\Users\Yuri\AppData\Local\Google\Cloud SDK\google-cloud-sdk\bin\gcloud.cmd",
        r"C:\Program Files (x86)\Google\Cloud SDK\google-cloud-sdk\bin\gcloud.cmd",
    ]
    for gcloud in gcloud_paths:
        if os.path.exists(gcloud):
            r = subprocess.run([gcloud, "auth", "print-access-token"], capture_output=True, text=True)
            if r.returncode == 0:
                return r.stdout.strip()
    raise RuntimeError("Could not get access token. Set SOW_TOKEN env var.")

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
        print(f"Error {e.code}: {e.read().decode()}")
        return None

def main():
    token = get_token()
    print(f"Token obtained: {token[:20]}...")

    # 1. 現在のタブのendIndexを取得
    doc = docs_request("GET", f"documents/{DOC_ID}?includeTabsContent=true", token=token)
    if not doc:
        print("Failed to get document")
        return

    tab = next((t for t in doc["tabs"] if t["tabProperties"]["tabId"] == TAB_ID), None)
    if not tab:
        print(f"Tab {TAB_ID} not found")
        return

    body_content = tab["documentTab"]["body"]["content"]
    end_index = body_content[-1]["endIndex"]
    print(f"Tab endIndex: {end_index}, elements: {len(body_content)}")

    # 2. タブのコンテンツをクリア (index 1 〜 end_index-1)
    if end_index > 2:
        clear_requests = [{
            "deleteContentRange": {
                "range": {
                    "startIndex": 1,
                    "endIndex": end_index - 1,
                    "tabId": TAB_ID
                }
            }
        }]
        result = docs_request("POST", f"documents/{DOC_ID}:batchUpdate",
                              {"requests": clear_requests}, token=token)
        print(f"Cleared content: {result is not None}")

    # 3. SOWコンテンツを挿入
    # テキストブロックを順番に挿入（index 1 から）
    # 各挿入後にインデックスが増加

    sow_lines = [
        # (text, style, bold, size, color)
        ("作業範囲記述書（SOW）", "TITLE", True, 26, "#1a1a1a"),
        ("タダカヨ 活動時間・報酬マネジメントダッシュボード ＜業務委託費分析タブ 行政事業分類分割・分析機能強化＞", "HEADING_1", True, 16, "#1a1a1a"),
        ("", "NORMAL_TEXT", False, 10.5, "#000000"),
        ("文書番号：SOW-20260424-TDKY", "NORMAL_TEXT", False, 10.5, "#000000"),
        ("対象システム：pay-dashboard（Cloud Run / Streamlit）", "NORMAL_TEXT", False, 10.5, "#000000"),
        ("報告日：2026年4月24日（木）", "NORMAL_TEXT", False, 10.5, "#000000"),
        ("作業期間：2026年4月24日（木）", "NORMAL_TEXT", False, 10.5, "#000000"),
        ("作成：Claude Code（AI開発支援）　初期開発：本田康志（ヤスス）", "NORMAL_TEXT", False, 10.5, "#000000"),
        ("作業者：しっかり法人を経営し隊／すごいシステムつくり隊　近藤ゆり（ゆり）", "NORMAL_TEXT", False, 10.5, "#000000"),
        ("サービスURL：https://pay-dashboard-209715990891.asia-northeast1.run.app", "NORMAL_TEXT", False, 10.5, "#000000"),
        ("", "NORMAL_TEXT", False, 10.5, "#000000"),
        ("1. エグゼクティブ・サマリー (Executive Summary)", "HEADING_2", True, 14, "#1565c0"),
        ("業務委託費分析タブの「行政事業」分類をケアプーと神奈川DXの2分類に分割し、スポンサー未入力行の内容欄キーワード補完・令和8年度新業務分類の追加・ドリルダウン用セレクトボックスの追加・コンソール警告の解消を行い、分析精度とUXを改善した。", "NORMAL_TEXT", False, 10.5, "#000000"),
        ("", "NORMAL_TEXT", False, 10.5, "#000000"),
        ("2. プロジェクトの目的と背景 (Objectives & Background)", "HEADING_2", True, 14, "#1565c0"),
        ("2.1 背景", "HEADING_3", True, 12, "#333333"),
        ("直近の統括隊長会議で神奈川DXプロジェクトの管轄が変更となった。これにより、これまで一括表示していた「行政事業」分類では両プロジェクトの費用が混在し、各管轄での集計・確認が困難な状態となっていた。また、スポンサー未入力のメンバーが多く正確な分類が困難であること、棒グラフが小さい場合のドリルダウン操作しにくさも課題となっていた。", "NORMAL_TEXT", False, 10.5, "#000000"),
        ("2.2 目的", "HEADING_3", True, 12, "#333333"),
        ("神奈川DX（スポンサー：神奈川県DX）とケアプー（スポンサー：ケアプー事業（全国統一））の業務委託費をグラフ上で別分類として表示する", "NORMAL_TEXT", False, 10.5, "#000000"),
        ("スポンサー未入力行は内容欄キーワードで神奈川DXを補完し、分析精度を高める", "NORMAL_TEXT", False, 10.5, "#000000"),
        ("令和8年度行政事業（各事業のPM・AM）を分類マップに追加する", "NORMAL_TEXT", False, 10.5, "#000000"),
        ("バーが小さくて選択しにくい場合のセレクトボックス代替手段を提供する", "NORMAL_TEXT", False, 10.5, "#000000"),
        ("Vega-Lite コンソール警告を解消する", "NORMAL_TEXT", False, 10.5, "#000000"),
        ("", "NORMAL_TEXT", False, 10.5, "#000000"),
        ("3. 実施内容詳細 (Technical Scope of Work)", "HEADING_2", True, 14, "#1565c0"),
        ("3.1 分類マッピング変更（_COST_GROUP_MAP）", "HEADING_3", True, 12, "#333333"),
        ("変更前: 行政事業分類すべてを「行政事業（ケアプランデータ連携＆神奈川県事業）」に統合", "NORMAL_TEXT", False, 10.5, "#000000"),
        ("変更後: デフォルトを「行政事業（ケアプー：ケアプランデータ連携システムを広め隊）」に変更", "NORMAL_TEXT", False, 10.5, "#000000"),
        ("振り替えロジック①: sponsor == \"神奈川県DX\" かつ対象分類の行を「行政事業（神奈川DX）」に上書き（スポンサー対応2分類・エリアリーダー分類含む）", "NORMAL_TEXT", False, 10.5, "#000000"),
        ("振り替えロジック②: スポンサー未入力補完：description に「神奈川DX」「神奈川県DX」「神奈川県」を含む行を「行政事業（神奈川DX）」に振り替え", "NORMAL_TEXT", False, 10.5, "#000000"),
        ("令和8年度追加: 令和8年度行政事業（各事業のPM・AM）を _COST_GROUP_MAP に新規追加", "NORMAL_TEXT", False, 10.5, "#000000"),
        ("3.2 カラードメイン・非営利活動除外設定の更新", "HEADING_3", True, 12, "#333333"),
        ("_COST_COLOR_DOMAIN: 「行政事業（神奈川DX）」を色ドメインに追加（グラフ凡例に固定色で表示）", "NORMAL_TEXT", False, 10.5, "#000000"),
        ("_COST_GROUP_EXCLUDE_NONPROFIT: 旧ラベルを削除し、ケアプー・神奈川DXの2ラベルを追加（非営利活動タブでは両方除外）", "NORMAL_TEXT", False, 10.5, "#000000"),
        ("3.3 ドリルダウン用セレクトボックス追加", "HEADING_3", True, 12, "#333333"),
        ("追加UI: チャート下部にドロップダウンを追加。バーが小さくて選択しにくい分類（神奈川DX等）をドロップダウンからも選択可能", "NORMAL_TEXT", False, 10.5, "#000000"),
        ("既存動作: バークリックによるドリルダウンはそのまま維持", "NORMAL_TEXT", False, 10.5, "#000000"),
        ("選択解除: 「選択解除」ボタン・「チャートをリセット」ボタンでドロップダウンも同時リセット", "NORMAL_TEXT", False, 10.5, "#000000"),
        ("3.4 Vega-Lite コンソール警告対応", "HEADING_3", True, 12, "#333333"),
        ("警告内容: Infinite extent for field \"合計\": [Infinity, -Infinity] 等 9件", "NORMAL_TEXT", False, 10.5, "#000000"),
        ("原因: total_hover チャートの Y エンコーディングに stack=False が未設定で、Vega-Lite v6 がスタック計算を試みていた", "NORMAL_TEXT", False, 10.5, "#000000"),
        ("修正: y=alt.Y(\"合計:Q\", stack=False) を明示設定", "NORMAL_TEXT", False, 10.5, "#000000"),
        ("結果: エラー 0件・警告 0件に改善", "NORMAL_TEXT", False, 10.5, "#000000"),
        ("", "NORMAL_TEXT", False, 10.5, "#000000"),
        ("4. 技術的成果物 (Deliverables)", "HEADING_2", True, 14, "#1565c0"),
        ("dashboard/_pages/dashboard.py — _COST_GROUP_MAP・_COST_GROUP_EXCLUDE_NONPROFIT・_COST_COLOR_DOMAIN更新、Tab5にスポンサー別振り替えロジック（①スポンサーフィールド・②内容欄キーワード）追加、令和8年度行政事業（各事業のPM・AM）追加、ドリルダウン用セレクトボックス追加、Vega-Lite警告修正", "NORMAL_TEXT", False, 10.5, "#000000"),
        ("", "NORMAL_TEXT", False, 10.5, "#000000"),
        ("5. 品質保証と受入基準 (Quality Assurance & Acceptance)", "HEADING_2", True, 14, "#1565c0"),
        ("sponsor == \"神奈川県DX\" の行は「行政事業（神奈川DX）」に分類されること", "NORMAL_TEXT", False, 10.5, "#000000"),
        ("スポンサー未入力でも内容欄に「神奈川DX」「神奈川県DX」「神奈川県」を含む行が「行政事業（神奈川DX）」に分類されること", "NORMAL_TEXT", False, 10.5, "#000000"),
        ("令和8年度行政事業（各事業のPM・AM）がスポンサーに応じて正しく振り分けられること", "NORMAL_TEXT", False, 10.5, "#000000"),
        ("ドロップダウンで分類を選択するとドリルダウン内訳が表示されること", "NORMAL_TEXT", False, 10.5, "#000000"),
        ("「選択解除」「チャートをリセット」でドロップダウンがリセットされること", "NORMAL_TEXT", False, 10.5, "#000000"),
        ("ブラウザコンソールにエラー・警告が出ないこと", "NORMAL_TEXT", False, 10.5, "#000000"),
        ("非営利活動タブでは神奈川DX・ケアプー両分類とも除外されること", "NORMAL_TEXT", False, 10.5, "#000000"),
        ("", "NORMAL_TEXT", False, 10.5, "#000000"),
        ("6. 今後の推奨事項 (Recommendations)", "HEADING_2", True, 14, "#1565c0"),
        ("実データでの動作確認を行い、神奈川DX・ケアプー双方の件数・金額が期待通りに分かれているか目視確認することを推奨", "NORMAL_TEXT", False, 10.5, "#000000"),
        ("スポンサー未入力補完のキーワード（「神奈川DX」「神奈川県DX」「神奈川県」）は dashboard/_pages/dashboard.py の _kw_target / str.contains 引数で管理。キーワード追加・変更時はここを更新する", "NORMAL_TEXT", False, 10.5, "#000000"),
        ("今後スポンサー名が変更・追加された場合は _COST_GROUP_MAP のコメントと振り替えロジックの比較値（\"神奈川県DX\"）の両方を更新する", "NORMAL_TEXT", False, 10.5, "#000000"),
        ("", "NORMAL_TEXT", False, 10.5, "#000000"),
        ("デプロイ履歴", "HEADING_2", True, 14, "#1565c0"),
        ("pay-dashboard-00232-h64: 行政事業分類をケアプー/神奈川DXに分割", "NORMAL_TEXT", False, 10.5, "#000000"),
        ("pay-dashboard-00233-k66: 神奈川DX：スポンサー対応2分類・エリアリーダー分類を追加", "NORMAL_TEXT", False, 10.5, "#000000"),
        ("pay-dashboard-00234-cx4: 令和8年度行政事業（各事業のPM・AM）を行政事業分類に追加", "NORMAL_TEXT", False, 10.5, "#000000"),
        ("pay-dashboard-00235-hgg: ドリルダウン用セレクトボックスを追加", "NORMAL_TEXT", False, 10.5, "#000000"),
        ("pay-dashboard-00236-z65: スポンサー未入力補完ロジック追加（内容欄キーワード判定）", "NORMAL_TEXT", False, 10.5, "#000000"),
        ("pay-dashboard-00237-9xs: Vega-Lite Infinite extent コンソール警告を解消", "NORMAL_TEXT", False, 10.5, "#000000"),
        ("", "NORMAL_TEXT", False, 10.5, "#000000"),
        ("コミット数", "HEADING_2", True, 14, "#1565c0"),
        ("本日合計：6コミット", "NORMAL_TEXT", True, 10.5, "#000000"),
        ("87b4413  feat: 業務委託費分析タブで行政事業をケアプー/神奈川DXに分割表示", "NORMAL_TEXT", False, 10.5, "#000000"),
        ("2f64629  feat: 神奈川DX分類をスポンサー対応2分類・エリアリーダー分類にも拡張 + SOW個人名削除", "NORMAL_TEXT", False, 10.5, "#000000"),
        ("a7fc9ec  feat: 令和8年度行政事業（各事業のPM・AM）を行政事業分類に追加", "NORMAL_TEXT", False, 10.5, "#000000"),
        ("a1919fc  feat: 業務委託費分析タブにドリルダウン用セレクトボックスを追加", "NORMAL_TEXT", False, 10.5, "#000000"),
        ("cff5783  feat: 業務委託費分析タブにスポンサー未入力補完ロジックを追加", "NORMAL_TEXT", False, 10.5, "#000000"),
        ("f34008b  fix: total_hoverチャートにstack=Falseを追加（Vega-Lite Infinite extent警告対応）", "NORMAL_TEXT", False, 10.5, "#000000"),
        ("以上", "NORMAL_TEXT", True, 10.5, "#000000"),
    ]

    # Build requests: insert text from bottom to top to avoid index shifts
    # Actually, insert from top to bottom tracking current index
    requests = []
    current_index = 1  # Start after the initial empty paragraph

    for text, style, bold, size, color in sow_lines:
        insert_text = text + "\n"
        text_len = len(insert_text)

        # Insert text
        requests.append({
            "insertText": {
                "location": {"index": current_index, "tabId": TAB_ID},
                "text": insert_text
            }
        })

        # Apply paragraph style
        heading_map = {
            "TITLE": "TITLE",
            "HEADING_1": "HEADING_1",
            "HEADING_2": "HEADING_2",
            "HEADING_3": "HEADING_3",
            "NORMAL_TEXT": "NORMAL_TEXT",
        }
        requests.append({
            "updateParagraphStyle": {
                "range": {
                    "startIndex": current_index,
                    "endIndex": current_index + text_len,
                    "tabId": TAB_ID
                },
                "paragraphStyle": {
                    "namedStyleType": heading_map[style],
                    "alignment": "START"
                },
                "fields": "namedStyleType,alignment"
            }
        })

        # Apply text style (font, size, color, bold)
        if text:  # Only apply style if text is non-empty
            requests.append({
                "updateTextStyle": {
                    "range": {
                        "startIndex": current_index,
                        "endIndex": current_index + text_len - 1,  # Exclude newline
                        "tabId": TAB_ID
                    },
                    "textStyle": {
                        "bold": bold,
                        "fontSize": {"magnitude": size, "unit": "PT"},
                        "foregroundColor": {
                            "color": {"rgbColor": {
                                "red": int(color[1:3], 16) / 255,
                                "green": int(color[3:5], 16) / 255,
                                "blue": int(color[5:7], 16) / 255
                            }}
                        },
                        "weightedFontFamily": {"fontFamily": "Noto Sans JP"}
                    },
                    "fields": "bold,fontSize,foregroundColor,weightedFontFamily"
                }
            })

        current_index += text_len

    # Send in batches of 50 requests
    batch_size = 50
    total_requests = len(requests)
    print(f"Total requests: {total_requests}")

    for i in range(0, total_requests, batch_size):
        batch = requests[i:i+batch_size]
        result = docs_request("POST", f"documents/{DOC_ID}:batchUpdate",
                              {"requests": batch}, token=token)
        if result:
            print(f"Batch {i//batch_size + 1}/{(total_requests+batch_size-1)//batch_size}: OK")
        else:
            print(f"Batch {i//batch_size + 1}: FAILED")
            return

    print("SOW Google Doc updated successfully!")


if __name__ == "__main__":
    main()
