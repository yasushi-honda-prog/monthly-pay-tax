# ハンドオフメモ - monthly-pay-tax

**更新日**: 2026-02-07
**フェーズ**: 0 - インフラ準備完了 / 実装計画前

## 現在の状態

GAS（Google Apps Script）で運用していた月次給与データ集約スクリプトを、GCP（Cloud Run + BigQuery）ベースの分析基盤に移行するプロジェクト。

### 完了済み

| 項目 | 状態 | 詳細 |
|------|------|------|
| GASコードのclasp clone | ✅ | アカウント: yasushi-honda@tadakayo.jp |
| GitHubリポジトリ | ✅ | https://github.com/yasushi-honda-prog/monthly-pay-tax (public) |
| GCPプロジェクト | ✅ | プロジェクトID: `monthly-pay-tax` |
| 環境分離 | ✅ | .envrc, .gitconfig.local, gcloud config 設定済み |

### 未完了（次セッション）

| 項目 | 優先度 | 備考 |
|------|--------|------|
| `/impl-plan` で実装計画策定 | **最優先** | Cloud Run + BigQuery + 可視化の設計 |
| BigQuery API有効化 | 高 | GCPプロジェクトでAPI有効化が必要 |
| Cloud Run デプロイ基盤 | 高 | Python + Sheets API + BigQuery Client |
| 可視化レイヤー決定 | 中 | Looker Studio（即時）→ Streamlit（カスタム） |

## アーキテクチャ決定事項

### 採用: パターンB（Cloud Run全置換）

```
Cloud Scheduler (毎日定時)
    │
    ▼
Cloud Run (Python)
    ├─ Google Sheets API で200件巡回
    ├─ データ整形
    └─ BigQuery に投入
          │
          ▼
    可視化レイヤー
    ├─ Looker Studio（すぐ使える）
    └─ Streamlit or カスタムHTML（後から追加）
```

**理由**: 200件のスプレッドシート巡回はGASの6分制限を超えるため

### 既存GASの概要（移行元）

- `consolidateReports()`: 管理表URLリストから各スプレッドシートのデータを収集
- 2種類のシートを対象:
  - `【都度入力】業務報告` (7行目〜, B〜K列)
  - `【月１入力】補助＆立替報告＋月締め` (4行目〜, B〜K列)
- 各行に元URL付加 → 集約先スプレッドシートに全件書き込み
- 管理表: `1fBNfkFBARSpT-OpLOytbAfoa0Xo5LTWv7irimssxcUU`
- 集約先: `16V9fs2kf2IzxdVz1GOJHY9mR1MmGjbmwm5L0ECiMLrc`

## 環境情報

| 項目 | 値 |
|------|-----|
| GCPプロジェクトID | `monthly-pay-tax` |
| GCPアカウント | yasushi-honda@tadakayo.jp |
| GitHub | yasushi-honda-prog/monthly-pay-tax |
| Gitユーザー | yasushi-honda / yasushi-honda@tadakayo.jp |
| GASスクリプトID | `1D4FgEZRhg3X9rgU2EMjqnAN_6yQCmtP3Ixzo0pl87yR-aD9tNHLKRl-M` |
| gcloud config名 | `monthly-pay-tax` |
