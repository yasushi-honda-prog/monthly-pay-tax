# 作業範囲記述書（SOW）

タダカヨ 活動時間・報酬マネジメントダッシュボード 期間指定UI刷新・数値変換リファクタ・Altairチャート堅牢化

文書番号：SOW-20260321-TDKY
対象システム：pay-dashboard（Cloud Run / Streamlit）
報告日：2026年3月21日
作業期間：2026年3月21日
作成：Claude Code（AI開発支援）　初期開発：本田康志（ヤスス）
作業者：しっかり法人を経営し隊／すごいシステムつくり隊　近藤ゆり（ゆり）
サービスURL：https://pay-dashboard-209715990891.asia-northeast1.run.app

---

## 1. エグゼクティブ・サマリー (Executive Summary)

期間指定UIの全面刷新・業務分類フィルターのモバイル対応・月次推移グラフの試行と復元・数値変換リファクタ・Altairチャートの堅牢化を実施し、Cloud Runへデプロイした。select_sliderを廃止してselectboxに統一することでReact null refエラーを根本解消、BQ文字列型データによるValueErrorを `pd.to_numeric(errors="coerce")` で修正、Vega-Lite v5/v6互換の `stack=False` 明示により描画警告を解消した。

---

## 2. プロジェクトの目的と背景 (Objectives & Background)

期間指定スライダー（select_slider）がReactのnull refエラーを断続的に引き起こし、モバイル環境での業務分類フィルター表示も崩れていた。BQからのデータが文字列型のまま残るケースで `style.format("¥{:,.0f}")` がValueErrorを発生させており、数値変換ロジックの重複定義も保守性を低下させていた。Altairチャートのstack変換がVega-Lite v5/v6間の互換問題でInfinite extent警告を出していた。これらを一括して解消し、ダッシュボードの安定性と保守性を向上させることを目的とした。

---

## 3. 実施内容詳細 (Technical Scope of Work)

### 3.1 期間指定プルダウン改善

| 項目 | 内容 |
|------|------|
| スライダー廃止・プルダウン2つに統一 | select_sliderを廃止し、開始月・終了月の2つのselectboxに統一。React null ref エラーを根本解消 |
| 表示範囲との自動連動 | 「当期」「直近1年」などの表示範囲選択に応じてプルダウンのデフォルト値が自動設定される |
| 当期終了月のデフォルト改善 | 当期終了月のデフォルトを最新データ月に変更 |
| レイアウト修正 | プルダウンを縦積みにして月名が切れないよう修正 |
| session_state 競合解消 | selectbox の `index=` と session_state の競合による警告・TypeError を解消 |

### 3.2 業務分類 multiselect 表示改善

| 項目 | 内容 |
|------|------|
| モバイル縦積み対応 | 業務報告一覧の業務分類フィルター（multiselect）をモバイルで縦積みに変更 |
| 項目重なり解消 | モバイル表示時に項目が重なって見づらい問題を解消 |

### 3.3 月次推移グラフ — 試行とオリジナル復元

| 項目 | 内容 |
|------|------|
| レイアウト改善試行 | デュアルY軸・横並び・上下分割・積み上げ棒など8パターンを試行 |
| 復元判断 | Altair の xoffset 左右順序が不安定なため安定した表示が困難と判断 |
| オリジナルに復元 | 業務報酬・源泉徴収・DX補助・立替の4項目集合棒グラフ（オリジナル）に戻した |

### 3.4 数値変換リファクタ（PR #47・#48）

| 項目 | 内容 |
|------|------|
| ValueErrorを修正（#47） | BQからのデータが文字列型のまま残るケースで `style.format("¥{:,.0f}")` が ValueError を発生させていた問題を修正。`fillna(0).astype(float)` を `pd.to_numeric(errors="coerce")` に置換 |
| 重複排除・ヘルパー関数抽出（#48） | `_COMP_NUM_COLS` 定数を導入し重複定義を解消。`_ensure_numeric_pivot()` ヘルパーを抽出しピボット表示前の数値保証処理（3箇所）を統一 |

### 3.5 Altairチャート防御的ガード追加（PR #49）

| 項目 | 内容 |
|------|------|
| 月次推移チャート | NaNデータに対し `dropna()` + 空DataFrameガードを追加 |
| 活動分類チャート | 金額0のカテゴリを除外するガード追加 |
| 全チャート共通 | `stack=False` を明示してVega-Lite v5/v6互換のstack変換を抑止 |

---

## 4. 技術的成果物 (Deliverables)

- `dashboard/pages/dashboard.py` — 期間指定プルダウン改善・月次推移グラフ復元・Altairガード
- `dashboard/lib/ui_helpers.py` — 期間指定プルダウン共通部品
- `CLAUDE.md` — テストコマンド追加・タブ数・制約更新
- Cloud Runデプロイ（pay-dashboard-00150〜00166-k42）

---

## 5. 品質保証と受入基準 (Quality Assurance & Acceptance)

- 27コミット（feat: 7、fix: 10、revert: 3、refactor: 1、docs: 3、chore: 3）で段階的に実装・検証
- 月次推移グラフ8パターンを試行し、xoffset順序の不安定さを確認した上でオリジナルへ意図的に復元
- `pd.to_numeric(errors="coerce")` による数値変換を3箇所に統一し、ValueErrorの再発を防止
- `stack=False` 明示によりVega-Lite v5/v6両バージョンで描画警告が出ないことを確認

---

## 6. 今後の推奨事項 (Recommendations)

- AltairのxoffsetによるグループドバーチャートはStreamlit/Vega-Liteバージョンアップ後に再挑戦を検討する
- `_ensure_numeric_pivot()` のカバレッジをさらに広げ、すべてのピボット表示前に適用する
- StreamlitのAltair統合がVega-Lite v6に正式対応した際にstack=False記述が不要になるか確認する

---

## デプロイ履歴

| リビジョン | 内容 |
|-----------|------|
| pay-dashboard-00150〜00153 | 期間指定プルダウン改善・各種バグ修正 |
| pay-dashboard-00162-ktq | 月次推移グラフをオリジナル（4項目集合棒）に復元 |
| pay-dashboard-00163〜00165 | 数値変換リファクタ（#47・#48）・Altairガード（#49） |
| pay-dashboard-00166-k42 | Altairチャート `stack=False` 追加・Infinite extent警告解消 |
