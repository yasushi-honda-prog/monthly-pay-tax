# アーカイブ: 2026-04-12以前の状態セクション

LATEST.md から移動。詳細はCLAUDE.mdおよびinfra/bigquery/を参照。

## 現在の状態（2026-04-07時点）

Cloud Run + BigQuery + Streamlitダッシュボード本番稼働中。
Googleグループ機能デプロイ済み - Admin SDK経由でメンバーのグループ所属を収集。
groups_master テーブル: 69グループ登録済み。members テーブル: 192件にgroups列付与済み。

### Cloud Run CPU billing mode変更（ADR 0004）

- pay-dashboard のコスト増加（1月¥15 → 3月¥6,961）を調査
- Cloud Run CPUが¥4,536（92%）が真犯人
- 対策: `--no-cpu-throttling --max-instances=3` 適用（単価-25%）
- 残課題: 請求書PDF確認（¥10,079 vs ¥4,903のズレ解明）、予算アラート設定

### 報告入力機能（2026-03-28 PR #51 コミット済み・デプロイ済み）

- report_input.py: 業務報告入力 + 補助報告入力
- BQテーブル: app_gyomu_reports, app_hojo_reports（未作成、schema.sql定義済み）

### 3月の変更履歴

- b786eed: Tab1にメンバー別月次活動時間ピボット追加
- PR #48: 数値変換の重複排除とヘルパー関数抽出
- PR #47: 数値フォーマットValueError修正
- PR #49: Altairチャート防御的ガード追加

### 過去の変更（2026-03-17 以前）

詳細: `docs/handoff/archive/2026-03-history.md`
