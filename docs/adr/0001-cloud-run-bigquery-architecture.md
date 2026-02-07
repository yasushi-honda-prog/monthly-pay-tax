# ADR-0001: Cloud Run + BigQuery アーキテクチャ採用

## ステータス
採用

## コンテキスト
GAS（Google Apps Script）で運用していた月次給与データ集約スクリプトが、200件のスプレッドシート巡回によりGASの6分実行制限を超過するリスクがあった。

## 検討した選択肢

### パターンA: GAS最適化（分割実行+トリガーチェーン）
- GASの6分制限内で実行できるよう処理を分割
- PropertiesServiceで進捗管理、トリガーで再開
- メリット: 既存コードベース活用、追加コストなし
- デメリット: 複雑な状態管理、デバッグ困難、スケーラビリティ低

### パターンB: Cloud Run全置換（採用）
- Cloud Run(Python) → BigQuery → Looker Studio
- Cloud Schedulerで定期実行
- メリット: タイムアウト30分、並列処理可、BigQueryの分析機能
- デメリット: 新規構築コスト、GCP学習コスト

## 決定
パターンB（Cloud Run全置換）を採用。

## 理由
1. 200件のスプレッドシート巡回は推定20-30分かかり、GAS 6分制限の回避が困難
2. BigQueryにデータを集約することで、Looker Studioでの可視化・分析が容易
3. GCP無料枠内で運用可能（月額$0見込み）
4. Pythonエコシステム（pandas等）による柔軟なデータ処理

## 技術スタック
- Python 3.12 / Flask / gunicorn
- google-api-python-client（Sheets API v4）
- google-cloud-bigquery（BigQuery Client）
- Domain-Wide Delegation認証
- Cloud Scheduler（OIDC認証）
- Artifact Registry（クリーンアップ: 最新2イメージ保持）
- Looker Studio（BQネイティブコネクタ）

## 影響
- 既存GASスクリプトは移行完了後に停止（即削除はしない）
- 集約先スプレッドシートはBigQuery + Looker Studioに置換
- 管理表スプレッドシート（URLリスト）は引き続き使用
