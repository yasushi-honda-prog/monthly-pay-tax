# 作業報告書（SOW）

プロジェクト: タダカヨ 活動時間・報酬マネジメントダッシュボード
対象システム: pay-dashboard（Cloud Run / Streamlit）
作業日: 2026年4月4日（土）
作業者: Claude Code（AI開発支援）

---

## 作業概要

業務委託費分析における令和8年度行政事業の業務分類マッピング追加、キャプションへの人数表示追加、Altairチャートツールバーの表示復活、およびDockerfileへのGoogle翻訳無効化設定追加を実施した。全3回のデプロイを完了。

---

## 実施内容

### 1. 業務委託費分析 — 業務分類マッピング追加

| 項目 | 内容 |
|------|------|
| 対象ファイル | `dashboard/_pages/dashboard.py`、`dashboard/prototype_cost_analysis.py` |
| 変更箇所 | `_COST_GROUP_MAP` 辞書 |
| 追加分類（3件） | `令和8年度行政事業（共通）`<br>`行政事業（ケアプー：全日稼働）※日給制`<br>`行政事業（ケアプー：半日稼働）※日給制` |
| 分類先グループ | `行政事業（行政事業：ケアプランデータ連携システムを広め隊＆神奈川県事業）` |
| 背景 | 令和8年度の行政事業業務分類が「未分類」として表示されていたため |

### 2. 業務委託費チャート — キャプションに人数表示追加

| 項目 | 内容 |
|------|------|
| 対象ファイル | `dashboard/_pages/dashboard.py` |
| 変更箇所 | `_render_cost_chart()` 関数内 `st.caption()` |
| 変更前 | `件数：X,XXX 件  ／  分類バーをクリックするとメンバー別にドリルダウンします` |
| 変更後 | `件数：X,XXX 件  ／  人数：XX 人  ／  分類バーをクリックするとメンバー別にドリルダウンします` |
| 実装 | `df["nickname"].nunique()` で重複排除メンバー数を算出 |

### 3. Altairチャートツールバーの表示復活

| 項目 | 内容 |
|------|------|
| 対象ファイル | `dashboard/lib/styles.py` |
| 変更内容 | `stElementToolbar` を全非表示にしていたCSSブロック（7行）を削除 |
| 背景 | 「チャートをリセット」ボタンが実装済みのため、テーブル表示になっても復旧可能。全画面表示・テーブル表示・PNG保存ボタンを利用可能に |

### 4. Dockerfile — Google翻訳無効化設定追加

| 項目 | 内容 |
|------|------|
| 対象ファイル | `dashboard/Dockerfile` |
| 追加内容 | `sed` でStreamlit HTMLテンプレートに `translate="no" lang="ja"` を注入 |
| 効果 | ブラウザのGoogle翻訳ポップアップが表示されなくなる |

### 5. コンソール警告の調査・解説

| 項目 | 内容 |
|------|------|
| 警告種別 | `fit-x` 警告 / `Infinite extent` 警告 / `preventOverflow` 警告 |
| 調査結果 | すべてStreamlit 1.55.0 + Altair 6.0.0（Vega-Lite v5 spec）とフロントエンドVega-Lite v6の互換性問題。CLAUDE.mdに既知として記載済み |
| 対処方針 | アプリコードからは修正不可。Streamlitのバージョンアップ待ち。表示・機能への影響なし |

---

## デプロイ履歴

| リビジョン | 内容 |
|-----------|------|
| pay-dashboard-00206-vrm | 業務分類マッピング3件追加（令和8年度行政事業） |
| pay-dashboard-00207-8xz | キャプションに人数表示追加 |
| pay-dashboard-00208-fcq | Altairチャートツールバー表示復活 |

---

## コミット数

- 本日合計: **0 コミット**（未コミット — デプロイのみ実施）

---

## 変更ファイル

- `dashboard/_pages/dashboard.py` — 業務分類マッピング3件追加、キャプション人数表示追加
- `dashboard/prototype_cost_analysis.py` — 業務分類マッピング3件追加（プロトタイプ同期）
- `dashboard/lib/styles.py` — Altairチャートツールバー非表示CSSを削除
- `dashboard/Dockerfile` — Google翻訳無効化設定追加

---

## サービス情報

サービスURL: https://pay-dashboard-209715990891.asia-northeast1.run.app
