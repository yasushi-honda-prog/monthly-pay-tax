# 運用ドキュメント

業務報告スプレッドシート構造変更、システム運用上の判断記録、業務オペレーション変更などを記録するディレクトリ。

dashboard の「運用ドキュメント」ページから閲覧可能。

## ファイル命名規則

`YYYYMMDD_<topic>_<kind>.md`

例:
- `20260516_活動分類_rename.md`
- `20260601_新規スポンサー_追加.md`

## frontmatter フォーマット

各 Markdown ファイルの先頭に YAML frontmatter を記述する:

```markdown
---
title: タイトル
date: 2026-05-16
status: active
tags: [運用変更, スプレッドシート]
---

## 本文...
```

| フィールド | 必須 | 値 |
|---------|------|---|
| title | ◯ | dashboard selectbox 表示名 |
| date | ◯ | ドキュメント作成日（YYYY-MM-DD） |
| status | △ | active / draft / archived（省略時は active 扱い） |
| tags | △ | タグリスト（将来のフィルタ用） |

## Mermaid 図の埋め込み

通常の Markdown コードフェンス記法で記述:

````markdown
```mermaid
flowchart LR
  A --> B
```
````

dashboard は ```mermaid``` ブロックを検出して自動でレンダリングする。
