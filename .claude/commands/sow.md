---
description: 本日のセッション作業内容からSOWを生成し、Markdownファイル保存とGoogle DocへのGAS書き込みを行う
allowed-tools: Bash(git log:*), Bash(git diff:*), Write, mcp__playwright__browser_navigate, mcp__playwright__browser_click, mcp__playwright__browser_snapshot, mcp__playwright__browser_evaluate, mcp__playwright__browser_press_key, mcp__playwright__browser_take_screenshot
---

本日のセッションで行った作業内容をもとに、SOW（作業範囲記述書）を作成してください。

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

`docs/sow/SOW_YYYYMMDD_<概要>.md` に保存：

```markdown
# 作業報告書（SOW）

プロジェクト: タダカヨ 活動時間・報酬マネジメントダッシュボード
対象システム: pay-dashboard（Cloud Run / Streamlit）
作業日: YYYY年M月D日（曜日）
作業者: Claude Code（AI開発支援）

---

## 作業概要

（本日の作業を1〜2文で要約）

---

## 実施内容

### 1. （カテゴリ名）

| 項目 | 内容 |
|------|------|
| （変更項目） | （詳細説明） |

---

## デプロイ履歴

| リビジョン | 内容 |
|-----------|------|
| pay-dashboard-XXXXX | （内容） |

---

## コミット数

- 本日合計: **N コミット**（feat: N、fix: N、...）

---

## 変更ファイル

- `パス/ファイル名` — 変更内容

---

## サービス情報

サービスURL: https://pay-dashboard-209715990891.asia-northeast1.run.app
```

### 3. Google Doc に GAS で書式付き記録

**対象ドキュメント**: `活動時間・報酬マネジメントダッシュボード機能拡張_作業範囲記述書`
- Doc ID: `1-ZoJpStrmEngNZ60GMdgyppM3gzYKFIlA5szAp2SJYc`

**手順**:

#### 3-1. Playwright でドキュメントを開き、新タブを追加
1. `https://docs.google.com/document/d/1-ZoJpStrmEngNZ60GMdgyppM3gzYKFIlA5szAp2SJYc/edit` を開く
2. 「タブを追加」ボタンをクリック
3. タブ名を `SOW-YYYYMMDD-TDKY` に変更（例: `SOW-20260317-TDKY`）

#### 3-2. 新タブ上で Apps Script を開く
- メニュー「拡張機能」→「Apps Script」をクリック
- Apps Script エディタが開く

#### 3-3. GAS スクリプトを書き込んで実行

以下の `createSOW` 関数テンプレートを、**本日の作業内容で埋めて**エディタに貼り付け・実行する：

```javascript
function createSOW() {
  // ★ 対象タブのIDを指定（タブ作成後にURLから確認: ?tab=t.XXXXXXXX）
  var doc = DocumentApp.openById('1-ZoJpStrmEngNZ60GMdgyppM3gzYKFIlA5szAp2SJYc');
  var tab = doc.getTab('TAB_ID_HERE').asDocumentTab(); // タブIDに変更
  var body = tab.getBody();
  body.clear();

  // ===== タイトル =====
  var title = body.appendParagraph('作業範囲記述書（SOW）');
  title.setHeading(DocumentApp.ParagraphHeading.TITLE);

  var subtitle = body.appendParagraph('タダカヨ 活動時間・報酬マネジメントダッシュボード 機能追加・拡張');
  subtitle.setHeading(DocumentApp.ParagraphHeading.HEADING1);

  // ===== メタ情報 =====
  var metaLines = [
    ['文書番号：', 'SOW-YYYYMMDD-TDKY'],
    ['対象システム：', 'pay-dashboard（Cloud Run / Streamlit）'],
    ['報告日：', 'YYYY年M月D日'],
    ['作業期間：', 'YYYY年M月D日'],
    ['作成：', 'Claude Code（AI開発支援）　初期開発：本田康志（ヤスス）'],
    ['作業者：', 'しっかり法人を経営し隊／すごいシステムつくり隊　近藤ゆり（ゆり）'],
    ['サービスURL：', 'https://pay-dashboard-209715990891.asia-northeast1.run.app'],
  ];
  metaLines.forEach(function(row) {
    var p = body.appendParagraph('');
    p.appendText(row[0]).setBold(true);
    p.appendText(row[1]).setBold(false);
  });

  body.appendHorizontalRule();

  // ===== 1. エグゼクティブ・サマリー =====
  body.appendParagraph('1. エグゼクティブ・サマリー (Executive Summary)')
      .setHeading(DocumentApp.ParagraphHeading.HEADING2);
  body.appendParagraph('（本日の作業概要を1〜2文で記載）');

  body.appendHorizontalRule();

  // ===== 2. 実施内容詳細 =====
  body.appendParagraph('2. 実施内容詳細 (Technical Scope of Work)')
      .setHeading(DocumentApp.ParagraphHeading.HEADING2);

  // セクションデータ（本日の内容に合わせて編集）
  var sections = [
    {
      title: '2.1 （カテゴリ名）',
      rows: [
        ['（変更項目）', '（詳細説明）'],
      ]
    },
    // 必要に応じてセクションを追加
  ];

  sections.forEach(function(section) {
    body.appendParagraph(section.title)
        .setHeading(DocumentApp.ParagraphHeading.HEADING3);
    var table = body.appendTable();
    // ヘッダー行
    var headerRow = table.appendTableRow();
    ['項目', '内容'].forEach(function(h) {
      var cell = headerRow.appendTableCell(h);
      cell.setBackgroundColor('#D9D9D9');
      cell.getChild(0).asParagraph().setAttributes(
        {[DocumentApp.Attribute.BOLD]: true}
      );
    });
    // データ行
    section.rows.forEach(function(row) {
      var r = table.appendTableRow();
      r.appendTableCell(row[0]);
      r.appendTableCell(row[1]);
    });
  });

  body.appendHorizontalRule();

  // ===== 3. デプロイ履歴 =====
  body.appendParagraph('3. デプロイ履歴')
      .setHeading(DocumentApp.ParagraphHeading.HEADING2);
  var deployTable = body.appendTable();
  var dHeader = deployTable.appendTableRow();
  ['リビジョン', '内容'].forEach(function(h) {
    var cell = dHeader.appendTableCell(h);
    cell.setBackgroundColor('#D9D9D9');
    cell.getChild(0).asParagraph().setAttributes(
      {[DocumentApp.Attribute.BOLD]: true}
    );
  });
  // デプロイデータ（本日の内容に合わせて編集）
  var deployData = [
    ['pay-dashboard-XXXXX', '（内容）'],
  ];
  deployData.forEach(function(row) {
    var r = deployTable.appendTableRow();
    row.forEach(function(cell) { r.appendTableCell(cell); });
  });

  body.appendHorizontalRule();

  // ===== 4. 変更ファイル =====
  body.appendParagraph('4. 変更ファイル')
      .setHeading(DocumentApp.ParagraphHeading.HEADING2);
  var changedFiles = [
    ['dashboard/pages/dashboard.py', '（変更内容）'],
    // 必要に応じて追加
  ];
  changedFiles.forEach(function(f) {
    var p = body.appendParagraph('');
    p.appendText(f[0]).setBold(true);
    p.appendText('　—　' + f[1]).setBold(false);
    p.setIndentStart(20);
  });

  body.appendHorizontalRule();

  // ===== 5. コミット数 =====
  body.appendParagraph('5. コミット数')
      .setHeading(DocumentApp.ParagraphHeading.HEADING2);
  body.appendParagraph('本日合計：Nコミット（feat: N、fix: N、...）');

  doc.saveAndClose();
  return 'SOW作成完了';
}
```

#### 3-4. タブIDの確認方法
新タブ作成後、ドキュメントのURLを確認：
```
https://docs.google.com/document/d/DOC_ID/edit?tab=t.XXXXXXXX
                                                        ^^^^^^^^ これがタブID
```

#### 3-5. 実行
- エディタ上部の関数セレクタで `createSOW` を選択
- ▷ 実行ボタンをクリック
- 権限承認が出たら許可する

---

## SOW文書番号ルール

`SOW-{YYYYMMDD}-TDKY`

- `YYYYMMDD`: 作業日（例: `20260317`）
- `TDKY`: タダカヨの略称（固定）

## 注意事項

- コミット数は `git log --oneline --since="今日の日付 00:00"` で確認
- デプロイリビジョンは会話履歴から確認（`gcloud run revisions list` でも可）
- GASのタブ指定は `doc.getTab('TAB_ID').asDocumentTab()` — タブIDはURLの `?tab=t.XXXXXXXX` の `XXXXXXXX` 部分
