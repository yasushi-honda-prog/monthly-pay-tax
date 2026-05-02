# ADR 0006: GitHub Actions による CI/CD 導入

## ステータス
採用 (2026-05-02) — Phase 1〜4 全て稼働中（PR #121, #122, #123, #124 でマージ完了、初回自動デプロイ検証済み）

## 背景

これまで本プロジェクトには CI/CD パイプラインが存在せず、`gcloud builds submit` および `gcloud run deploy` コマンドを開発者がローカル端末から手動実行する運用だった（プロジェクト CLAUDE.md にも「CI/CDなし。テストは手動実行」と明記）。

直近の運用で以下の課題が顕在化:

1. **テストの実行漏れリスク**: PR レビュー時に、レビュアーが手元で pytest を回さない限りテスト結果を確認できない。Definition of Done「テスト・lint・型チェック全 PASS 確認」を機械的に保証できない
2. **デプロイの再現性**: ローカル環境の差異（gcloud SDK バージョン、direnv 設定、認証状態）がデプロイ結果に影響する可能性
3. **デプロイ作業者の限定**: 手動コマンドを実行できる権限を持つ開発者にデプロイが集中する
4. **監査ログの欠如**: いつ誰がどのリビジョンをデプロイしたかが Cloud Run の revision 履歴のみに依存し、PR との紐付けが弱い
5. **PR レビューでの hook 要求**: `post-pr-review` hook が large tier PR で「Review required before merge」を出すが、CI 上での自動テスト結果がないため hook の要求が形式的になりがち

## 検討した選択肢

| 案 | 評価 | 備考 |
|---|---|---|
| **CI/CD 不採用継続**（手動運用維持） | ❌ | 上記 5 課題が解消されない |
| **GitLab CI / CircleCI 採用** | ❌ | 既存リポジトリは GitHub にあり、別 CI 導入は管理コスト増 |
| **Cloud Build トリガー直結**（GitHub Actions 経由なし） | △ | ビルドのみ自動化可能だが、テスト実行・パスフィルタ・ステップ間制御が弱い |
| **GitHub Actions 採用（WIF キーレス認証）** | ⭕ | **採用**: GitHub と統合、リポジトリ PUBLIC でも安全、段階導入可能 |

### 認証方式の検討

| 方式 | 評価 | 不採用理由 |
|---|---|---|
| **SA キーを GitHub Secrets に保存** | ❌ | リポジトリ PUBLIC で漏洩リスク高、ローテーション運用コスト、CLAUDE.md のキーレス DWD 方針と矛盾 |
| **Workload Identity Federation (WIF)** | ⭕ | **採用**: キーレス、GitHub OIDC token を GCP で検証、ローテーション不要 |

## 決定

GitHub Actions ワークフローを 4 段階の PR で漸進的に導入する。

### Phase 1（PR-1、本 ADR でカバー）: テストワークフロー

- `.github/workflows/test.yml` を追加
- トリガー: `pull_request`（全ブランチ）と `push` to `main`
- ジョブ: `dashboard-tests` / `cloud-run-tests` の 2 並列
- Python 3.12（Dockerfile と一致）、pytest 単体
- BQ・Streamlit・GCP API は既存 conftest.py でモック化済みのため CI でも追加設定不要

### Phase 2（PR-2、別 ADR 不要、運用ログのみ）: WIF + デプロイ用 SA 構築

- Workload Identity Pool: `github-actions-pool`
- Provider: `github-actions-provider`（GitHub OIDC、`yasushi-honda-prog/monthly-pay-tax` リポジトリ限定）
- デプロイ専用 SA: `github-actions-deployer@monthly-pay-tax.iam.gserviceaccount.com`
- 必要 role:
  - `roles/run.admin`（Cloud Run deploy）
  - `roles/cloudbuild.builds.editor`（Cloud Build submit）
  - `roles/artifactregistry.writer`（AR push）
  - `roles/iam.serviceAccountUser`（runtime SA `pay-collector` を assign する権限）
  - `roles/storage.admin`（Cloud Build staging bucket 用）
- WIF ↔ SA バインド: `roles/iam.workloadIdentityUser`
- GitHub repo variables: `WIF_PROVIDER`, `WIF_SA`（secrets ではなく vars で十分、機密性なし）

### Phase 3（PR-3）: デプロイワークフロー

- `.github/workflows/deploy-dashboard.yml`
- `.github/workflows/deploy-collector.yml`
- トリガー: `push` to `main` + パスフィルタ
  - `dashboard/**` 変更 → pay-dashboard デプロイ
  - `cloud-run/**` 変更 → pay-collector デプロイ
- `workflow_dispatch` も追加し、緊急時の手動実行を可能に
- Action: `google-github-actions/auth@v2`（WIF）+ `google-github-actions/setup-gcloud@v2`
- 既存 Dockerfile・既存 SA・既存 Cloud Run 構成を踏襲

### Phase 4（PR-4）: ドキュメント整合

- プロジェクト CLAUDE.md の「CI/CDなし」記述を更新
- `## ビルド・デプロイ` セクションに自動デプロイ情報を追記、手動コマンドはフォールバックとして残す
- README.md に CI/CD バッジ追加（オプション）

### ブラスト半径

```
触らない（既存維持）:
  - Dockerfile（dashboard / cloud-run 両方）
  - runtime SA pay-collector とその IAM 設定
  - Cloud Run サービス設定（メモリ・タイムアウト・--no-cpu-throttling 等）
  - Secret Manager dashboard-auth-config のマウント
  - 既存の手動 gcloud コマンド（フォールバックとして残す）
  - direnv ローカル開発環境

新規追加のみ:
  - .github/workflows/ ディレクトリと yml ファイル群
  - WIF プール・プロバイダ
  - github-actions-deployer SA（runtime SA とは別）
  - ADR-0006（本ファイル）
```

## 期待される効果

1. **テスト実行の機械化**: PR 作成時に Dashboard 307 + Cloud Run 52 = 359 テストが自動実行され、PASS/FAIL が PR チェックに表示
2. **デプロイの再現性**: GitHub Actions runner の固定環境（ubuntu-latest + Python 3.12）でビルド・デプロイが行われる
3. **監査性向上**: PR 番号 → Cloud Run revision の紐付けが Actions log に残り、いつ何をデプロイしたかが追跡可能
4. **手動運用の維持**: `workflow_dispatch` と既存 gcloud コマンドはフォールバックとして残し、CI 障害時もデプロイ可能
5. **コスト管理**: GitHub Actions の無料枠（PUBLIC リポジトリは無制限）+ Cloud Build の従量課金（既存運用と同等）でランニングコスト増は最小

## 適用範囲

### 自動化される操作
- PR 作成時の pytest 実行
- main merge 時の Docker build + Cloud Run deploy（パスフィルタ付き）
- 緊急時の手動デプロイ（`workflow_dispatch`）

### 自動化されない操作（手動継続）
- BQ schema (`infra/bigquery/schema.sql`) の適用
- BQ VIEW (`infra/bigquery/views.sql`) の更新
- Cloud Scheduler の設定変更
- Secret Manager のシークレット更新
- IAM ロール変更（Phase 2 の WIF セットアップ後はインフラ側で固定）

## 残課題

- **Phase 2 の GCP 側設定変更**: WIF プール・SA 作成は IAM レベルの変更で取り消しが面倒なため、AI が gcloud コマンドを実行する際は各コマンドのログをユーザーに提示し、想定外の挙動があれば即時中断
- **初回デプロイの動作確認**: Phase 3 完了後、最初の自動デプロイが手動デプロイと同等の結果になるかを 1 回手動検証する（PR-3 の Test plan に含める）
- **デプロイ失敗時のロールバック手順**: Cloud Run の revision 切り戻し手順を README に明記（`gcloud run services update-traffic` で前 revision に traffic を戻す）
- **将来の staging 環境**: 本 ADR では staging 分離はスコープ外。本番直 deploy のリスクは Cloud Run の revision 切り戻しで吸収する前提
- **secrets の取り扱い**: 現状 Secret Manager 経由でマウントしているもの（`dashboard-auth-config`）は CI/CD で触れない。CI 経由で secret を更新したい場合は別途追加 ADR
