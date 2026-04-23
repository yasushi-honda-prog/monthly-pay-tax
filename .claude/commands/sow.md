---
description: 本日のセッション作業内容からSOWを生成し、Markdownファイル保存・Google Doc書き込み・SOW管理スプレッドシート更新を行う
allowed-tools: Bash(git log:*), Bash(git diff:*), Write, mcp__playwright__browser_navigate, mcp__playwright__browser_click, mcp__playwright__browser_snapshot, mcp__playwright__browser_evaluate, mcp__playwright__browser_press_key, mcp__playwright__browser_take_screenshot, mcp__playwright__browser_tabs, mcp__playwright__browser_wait_for
---

本日のセッションで行った作業内容をもとに、SOW（作業範囲記述書）を作成してください。

## 必須セクション（順序・名称変更禁止・省略禁止）

| # | セクション名 |
|---|------------|
| 1 | エグゼクティブ・サマリー (Executive Summary) |
| 2 | プロジェクトの目的と背景 (Objectives & Background) |
| 3 | 実施内容詳細 (Technical Scope of Work) |
| 4 | 技術的成果物 (Deliverables) |
| 5 | 品質保証と受入基準 (Quality Assurance & Acceptance) |
| 6 | 今後の推奨事項 (Recommendations) |
| F | デプロイ履歴（フッター） |
| F | コミット数（フッター） |
| F | 以上（右揃え・太字、フッター末尾） |

---

## 手順

### 1. 本日の作業内容を収集

```bash
# 本日のコミット一覧
git log --oneline --since="$(date +%Y-%m-%d) 00:00"

# 変更ファイル一覧
git diff HEAD~$(git log --oneline --since="$(date +%Y-%m-%d) 00:00" | wc -l) HEAD --name-only 2>/dev/null
```

会話履歴からデプロイリビジョン（pay-dashboard-XXXXX）も確認する。

### 2. SOW Markdownファイルを作成

`docs/sow/SOW_YYYYMMDD_<概要>.md` に保存。全6セクション＋フッター必須：

```markdown
# 作業範囲記述書（SOW）

タダカヨ 活動時間・報酬マネジメントダッシュボード ＜作業概要＞

文書番号：SOW-YYYYMMDD-TDKY
対象システム：pay-dashboard（Cloud Run / Streamlit）
報告日：YYYY年M月D日
作業期間：YYYY年M月D日（曜日）
作成：Claude Code（AI開発支援）　初期開発：本田康志（ヤスス）
作業者：しっかり法人を経営し隊／すごいシステムつくり隊　近藤ゆり（ゆり）
サービスURL：https://pay-dashboard-209715990891.asia-northeast1.run.app

---

## 1. エグゼクティブ・サマリー (Executive Summary)

（本日の作業を1〜2文で要約）

---

## 2. プロジェクトの目的と背景 (Objectives & Background)

### 2.1 背景
（なぜこの作業が必要だったか）

### 2.2 目的
- （目的1）
- （目的2）

---

## 3. 実施内容詳細 (Technical Scope of Work)

### 3.1 （カテゴリ名）

| 項目 | 内容 |
|------|------|
| （変更項目） | （詳細説明） |

### 3.2 （カテゴリ名）

| 項目 | 内容 |
|------|------|
| （変更項目） | （詳細説明） |

---

## 4. 技術的成果物 (Deliverables)

- `パス/ファイル名` — 変更内容

---

## 5. 品質保証と受入基準 (Quality Assurance & Acceptance)

- （受入基準1）
- （受入基準2）

---

## 6. 今後の推奨事項 (Recommendations)

- （推奨事項1）

---

## デプロイ履歴

| リビジョン | 内容 |
|-----------|------|
| pay-dashboard-XXXXX | （内容） |

---

## コミット数

本日合計：**N コミット**

- `xxxxxxx` feat: （内容）
- `xxxxxxx` fix: （内容）

---

**以上**
```

### 3. Google Doc に GAS で書式付き記録

**対象ドキュメント**: `活動時間・報酬マネジメントダッシュボード機能拡張_作業範囲記述書`
- Doc ID: `1-ZoJpStrmEngNZ60GMdgyppM3gzYKFIlA5szAp2SJYc`

#### 3-1. Playwright でドキュメントを開き、新タブを追加
1. `https://docs.google.com/document/d/1-ZoJpStrmEngNZ60GMdgyppM3gzYKFIlA5szAp2SJYc/edit` を開く
2. 「タブを追加」ボタンをクリック
3. タブ名を `SOW-YYYYMMDD-TDKY` に変更

#### 3-2. 新タブ上で Apps Script を開く
- メニュー「拡張機能」→「Apps Script」をクリック

#### 3-3. GAS スクリプトを書き込んで実行

以下のテンプレートを**本日の作業内容で埋めて**エディタに貼り付け・実行する。
**フォント・サイズ・色は必ず全属性を明示設定すること（省略禁止。省略するとArialになる）。**

```javascript
function createSOW() {
  // ============================================================
  // ★ フォント・色定数（変更禁止）
  // ============================================================
  var FONT        = 'Noto Sans JP';
  var SIZE_TITLE  = 26;
  var SIZE_H1     = 16;
  var SIZE_H2     = 14;
  var SIZE_H3     = 12;
  var SIZE_BODY   = 10.5;
  var COLOR_TITLE = '#1a1a1a';
  var COLOR_H2    = '#1565c0';   // 青
  var COLOR_H3    = '#333333';
  var COLOR_BODY  = '#000000';
  var COLOR_TH    = '#D9D9D9';   // テーブルヘッダー背景

  // ============================================================
  // ★ ここを本日の内容に書き換える
  // ============================================================
  var SOW_DATE_JP  = 'YYYY年M月D日（曜日）';
  var SOW_DOC_NO   = 'SOW-YYYYMMDD-TDKY';
  var SOW_SUBTITLE = 'タダカヨ 活動時間・報酬マネジメントダッシュボード ＜作業概要＞';
  var SERVICE_URL  = 'https://pay-dashboard-209715990891.asia-northeast1.run.app';

  // 1. エグゼクティブ・サマリー
  var SUMMARY = '（作業全体を1〜2文で要約）';

  // 2. 背景・目的
  var BACKGROUND = '（なぜこの作業が必要だったかの背景）';
  var OBJECTIVES = [
    '（目的1）',
    '（目的2）',
  ];

  // 3. 実施内容セクション（3.1, 3.2 … を全て記載）
  var SECTIONS = [
    {
      title: '3.1 （カテゴリ名）',
      rows: [
        ['（変更項目）', '（詳細説明）'],
      ]
    },
    {
      title: '3.2 （カテゴリ名）',
      rows: [
        ['（変更項目）', '（詳細説明）'],
      ]
    },
  ];

  // 4. 技術的成果物（`ファイルパス`, 説明）
  var DELIVERABLES = [
    ['dashboard/pages/dashboard.py', '（変更内容）'],
  ];

  // 5. 品質保証と受入基準
  var QA_ITEMS = [
    '（受入基準1）',
    '（受入基準2）',
  ];

  // 6. 今後の推奨事項
  var RECOMMENDATIONS = [
    '（推奨事項1）',
  ];

  // デプロイ履歴テーブル
  var DEPLOY_DATA = [
    ['pay-dashboard-XXXXX', '（内容）'],
  ];

  // コミット一覧（ハッシュ, メッセージ）
  var COMMITS = [
    ['xxxxxxx', 'feat: （内容）'],
    ['xxxxxxx', 'fix: （内容）'],
  ];

  // ============================================================
  // ★ 対象タブIDを指定（URLの ?tab=t.XXXXXXXX の t.XXXXXXXX）
  // ============================================================
  var TAB_ID = 't.XXXXXXXX'; // ← タブ作成後に書き換える

  // ============================================================
  // ドキュメント操作（以下は変更不要）
  // ============================================================
  var doc  = DocumentApp.openById('1-ZoJpStrmEngNZ60GMdgyppM3gzYKFIlA5szAp2SJYc');
  var tab  = doc.getTab(TAB_ID).asDocumentTab();
  var body = tab.getBody();
  body.clear();

  // ---------- ヘルパー関数 ----------
  function applyStyle(para, size, color, bold) {
    var s = {};
    s[DocumentApp.Attribute.FONT_FAMILY]     = FONT;
    s[DocumentApp.Attribute.FONT_SIZE]        = size;
    s[DocumentApp.Attribute.FOREGROUND_COLOR] = color;
    s[DocumentApp.Attribute.BOLD]             = bold;
    para.setAttributes(s);
    return para;
  }

  function addH2(text) {
    var p = body.appendParagraph(text);
    p.setHeading(DocumentApp.ParagraphHeading.HEADING2);
    applyStyle(p, SIZE_H2, COLOR_H2, true);
    return p;
  }

  function addH3(text) {
    var p = body.appendParagraph(text);
    p.setHeading(DocumentApp.ParagraphHeading.HEADING3);
    applyStyle(p, SIZE_H3, COLOR_H3, true);
    return p;
  }

  function addBody(text) {
    return applyStyle(body.appendParagraph(text), SIZE_BODY, COLOR_BODY, false);
  }

  function addListItem(text) {
    var item = body.appendListItem(text);
    item.setGlyphType(DocumentApp.GlyphType.BULLET);
    applyStyle(item, SIZE_BODY, COLOR_BODY, false);
    return item;
  }

  function applyCell(cell, bold) {
    var cp = cell.getChild(0).asParagraph();
    var s = {};
    s[DocumentApp.Attribute.FONT_FAMILY]     = FONT;
    s[DocumentApp.Attribute.FONT_SIZE]        = SIZE_BODY;
    s[DocumentApp.Attribute.FOREGROUND_COLOR] = COLOR_BODY;
    s[DocumentApp.Attribute.BOLD]             = bold;
    cp.setAttributes(s);
  }

  function addTable(headers, rows) {
    var table = body.appendTable();
    var hRow = table.appendTableRow();
    headers.forEach(function(h) {
      var cell = hRow.appendTableCell(h);
      cell.setBackgroundColor(COLOR_TH);
      applyCell(cell, true);
    });
    rows.forEach(function(row) {
      var r = table.appendTableRow();
      row.forEach(function(text) {
        applyCell(r.appendTableCell(text), false);
      });
    });
    return table;
  }

  // ============================================================
  // タイトルブロック
  // ============================================================
  var titlePara = body.appendParagraph('作業範囲記述書（SOW）');
  titlePara.setHeading(DocumentApp.ParagraphHeading.TITLE);
  applyStyle(titlePara, SIZE_TITLE, COLOR_TITLE, true);

  var subPara = body.appendParagraph(SOW_SUBTITLE);
  subPara.setHeading(DocumentApp.ParagraphHeading.HEADING1);
  applyStyle(subPara, SIZE_H1, COLOR_TITLE, true);

  addBody('');

  var metaLines = [
    ['文書番号：',    SOW_DOC_NO],
    ['対象システム：', 'pay-dashboard（Cloud Run / Streamlit）'],
    ['報告日：',      SOW_DATE_JP],
    ['作業期間：',    SOW_DATE_JP],
    ['作成：',        'Claude Code（AI開発支援）　初期開発：本田康志（ヤスス）'],
    ['作業者：',      'しっかり法人を経営し隊／すごいシステムつくり隊　近藤ゆり（ゆり）'],
    ['サービスURL：',  SERVICE_URL],
  ];
  metaLines.forEach(function(row) {
    var p = body.appendParagraph('');
    var label = p.appendText(row[0]);
    label.setFontFamily(FONT); label.setFontSize(SIZE_BODY);
    label.setForegroundColor(COLOR_BODY); label.setBold(true);
    var val = p.appendText(row[1]);
    val.setFontFamily(FONT); val.setFontSize(SIZE_BODY); val.setBold(false);
    if (row[0] === 'サービスURL：') {
      val.setLinkUrl(row[1]); val.setForegroundColor('#1155CC');
    } else {
      val.setForegroundColor(COLOR_BODY);
    }
  });

  addBody('');

  // ============================================================
  // 1. エグゼクティブ・サマリー
  // ============================================================
  body.appendHorizontalRule();
  addH2('1. エグゼクティブ・サマリー (Executive Summary)');
  addBody(SUMMARY);

  // ============================================================
  // 2. プロジェクトの目的と背景
  // ============================================================
  body.appendHorizontalRule();
  addH2('2. プロジェクトの目的と背景 (Objectives & Background)');
  addH3('2.1 背景');
  addBody(BACKGROUND);
  addH3('2.2 目的');
  OBJECTIVES.forEach(function(obj) { addListItem(obj); });

  // ============================================================
  // 3. 実施内容詳細
  // ============================================================
  body.appendHorizontalRule();
  addH2('3. 実施内容詳細 (Technical Scope of Work)');
  SECTIONS.forEach(function(sec) {
    addH3(sec.title);
    addTable(['項目', '内容'], sec.rows);
    addBody('');
  });

  // ============================================================
  // 4. 技術的成果物
  // ============================================================
  body.appendHorizontalRule();
  addH2('4. 技術的成果物 (Deliverables)');
  DELIVERABLES.forEach(function(d) {
    var p = body.appendParagraph('');
    var bold = p.appendText(d[0]);
    bold.setFontFamily(FONT); bold.setFontSize(SIZE_BODY);
    bold.setForegroundColor(COLOR_BODY); bold.setBold(true);
    var desc = p.appendText(' — ' + d[1]);
    desc.setFontFamily(FONT); desc.setFontSize(SIZE_BODY);
    desc.setForegroundColor(COLOR_BODY); desc.setBold(false);
    p.setIndentStart(20);
  });

  // ============================================================
  // 5. 品質保証と受入基準
  // ============================================================
  body.appendHorizontalRule();
  addH2('5. 品質保証と受入基準 (Quality Assurance & Acceptance)');
  QA_ITEMS.forEach(function(item) { addListItem(item); });

  // ============================================================
  // 6. 今後の推奨事項
  // ============================================================
  body.appendHorizontalRule();
  addH2('6. 今後の推奨事項 (Recommendations)');
  RECOMMENDATIONS.forEach(function(item) { addListItem(item); });

  // ============================================================
  // フッター：デプロイ履歴
  // ============================================================
  body.appendHorizontalRule();
  addH2('デプロイ履歴');
  addTable(['リビジョン', '内容'], DEPLOY_DATA);

  // ============================================================
  // フッター：コミット数
  // ============================================================
  body.appendHorizontalRule();
  addH2('コミット数');
  applyStyle(
    body.appendParagraph('本日合計：' + COMMITS.length + 'コミット'),
    SIZE_BODY, COLOR_BODY, true
  );
  COMMITS.forEach(function(c) { addListItem(c[0] + '  ' + c[1]); });

  // ============================================================
  // フッター：以上
  // ============================================================
  body.appendHorizontalRule();
  var ijo = body.appendParagraph('以上');
  ijo.setAlignment(DocumentApp.HorizontalAlignment.RIGHT);
  applyStyle(ijo, SIZE_BODY, COLOR_BODY, true);

  doc.saveAndClose();
  return 'SOW作成完了';
}
```

#### 3-4. タブIDの確認方法
```
https://docs.google.com/document/d/DOC_ID/edit?tab=t.XXXXXXXX
                                                    ^^^^^^^^^^ TAB_IDに設定する
```
`t.` プレフィックスを含めた文字列をそのまま使う。

#### 3-5. 実行
- エディタ上部の関数セレクタで `createSOW` を選択
- ▷ 実行ボタンをクリック
- 権限承認が出たら許可する

---

## スタイル仕様（変更禁止）

| 要素 | フォント | サイズ | 色 | 太字 |
|------|---------|--------|-----|------|
| TITLE（作業範囲記述書） | Noto Sans JP | 26pt | #1a1a1a | ✓ |
| HEADING1（サブタイトル） | Noto Sans JP | 16pt | #1a1a1a | ✓ |
| HEADING2（セクション見出し） | Noto Sans JP | 14pt | #1565c0（青） | ✓ |
| HEADING3（サブ見出し） | Noto Sans JP | 12pt | #333333 | ✓ |
| NORMAL（本文・メタ情報） | Noto Sans JP | 10.5pt | #000000 | ✗ |
| LIST_ITEM（箇条書き） | Noto Sans JP | 10.5pt | #000000 | ✗ |
| テーブルヘッダー背景 | — | — | #D9D9D9 | ✓ |
| サービスURL | — | — | #1155CC（リンク） | ✗ |

## 文書番号ルール

`SOW-{YYYYMMDD}-TDKY`（例: SOW-20260410-TDKY）

## 注意事項

- コミット数は `git log --oneline --since="今日の日付 00:00"` で確認
- デプロイリビジョンは会話履歴から確認（`gcloud run revisions list` でも可）
- GASのタブ指定は `doc.getTab('t.XXXXXXXX').asDocumentTab()` — `t.` プレフィックス必須
- **全セクション（1〜6 + デプロイ履歴）は省略禁止**

---

## 4. SOW管理スプレッドシートを更新（必須）

**対象スプレッドシート**: `活動時間・報酬マネジメントダッシュボードSOW管理表_ゆり`
- Spreadsheet ID: `1MWXDcissrUBJcpp0RsvpOW9I7jO_XM7BumBo-TD6YRE`
- シート名: `活動時間・報酬マネジメントダッシュボード機能追加・拡張_SOW`

**列構成**:
| 列 | 内容 |
|----|------|
| A | 日時（YYYY/MM/DD形式） |
| B | リビジョン（pay-dashboard-XXXXX または範囲） |
| C | 主な内容（作業の要約） |
| D | SOWタブタイトル（SOW-YYYYMMDD-TDKY） |

**手順**: Google DocのApps Scriptを開いた後、同じスクリプトエディタで以下を追記して実行する（または別途スプレッドシートのApps Scriptから実行）。

```javascript
function appendToSOWSheet() {
  var ss = SpreadsheetApp.openById('1MWXDcissrUBJcpp0RsvpOW9I7jO_XM7BumBo-TD6YRE');
  var sheet = ss.getSheets()[0];
  var lastRow = sheet.getLastRow() + 1;

  // ★ ここを本日の内容に書き換える
  var date     = 'YYYY/MM/DD';
  var revision = 'pay-dashboard-XXXXX';
  var content  = '（作業の主な内容を1文で）';
  var sowTitle = 'SOW-YYYYMMDD-TDKY';

  sheet.getRange(lastRow, 1).setValue(date);
  sheet.getRange(lastRow, 2).setValue(revision);
  sheet.getRange(lastRow, 3).setValue(content);
  sheet.getRange(lastRow, 4).setValue(sowTitle);
  SpreadsheetApp.flush();
  return '追加完了: 行' + lastRow;
}
```
