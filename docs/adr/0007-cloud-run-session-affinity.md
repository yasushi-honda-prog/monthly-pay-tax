# ADR 0007: pay-dashboard の Cloud Run sessionAffinity 有効化（Streamlit OIDC リダイレクトループ解消）

## ステータス
採用 (2026-06-07)

## 背景

ユーザー報告: よもぎ (`asayo-shimizu@tadakayo.jp`, role=viewer) がダッシュボードにアクセスすると「リダイレクトされて見れない」状態だった。

BQ `dashboard_users` には登録済 (`role=viewer`, `created_at=2026-02-28`)、`lib/auth.py` 上 viewer は正規ロールとして許可されている。コード・データ・認証ロジックには欠陥なし。

Cloud Run のログ調査で決定的な兆候を発見:
- `/oauth2callback` の 302 リダイレクトが約 10 分間に 13 回頻発
- **同じ `state` パラメータが数秒間隔で複数回呼び出されている** (例: `qAD9Fag...` を 22:26:16 と 22:26:19 で再呼出)
- `prompt=none` (silent re-auth) フラグが多数
- これらは **OAuth セッションが確定できず認証ループしている典型症状**

調査の結果、Cloud Run の `sessionAffinity` 設定が **未設定** であることが判明:

```bash
gcloud run services describe pay-dashboard --region=asia-northeast1 --format=json | \
  jq '.spec.template.metadata.annotations."run.googleapis.com/sessionAffinity"'
# → null (未設定)
```

ADR-0004 で `max-instances=3` を採用しているため、Cloud Run は複数インスタンスにスケールし得る。`sessionAffinity` 未設定だと **各リクエストがランダムなインスタンスにルーティング** され、Streamlit OIDC の認証 state がインスタンス間で共有されないため OAuth callback で別インスタンスに振られると再認証ループに陥る。

### 発生メカニズム

1. ユーザーがアクセス → インスタンス **A** で Google OAuth リダイレクト
2. `/oauth2callback` で戻ってきたリクエストが **別インスタンス B** にルーティング
3. インスタンス B は OAuth state を持っていないため再認証 → リダイレクトループ
4. **コールドスタート時 / 久しぶりのアクセス時に発生確率が高い**
   - 頻繁にアクセスしている admin は同じインスタンス (ホット) に振られやすく症状を体感しない
   - 久しぶりのアクセスは別インスタンスに振られるリスクが高い → よもぎさんの症状の原因

## 検討した選択肢

| 案 | 評価 | 採否理由 |
|---|---|---|
| `max-instances=1` で単一インスタンスに固定 | ❌ | ADR-0004 で 3 にした暴走防止策と矛盾、スケーラビリティ低下 |
| Streamlit OIDC を外部 session store (Redis 等) に置換 | ❌ | Streamlit 公式仕様外、追加インフラと運用コスト |
| `cookie_secret` の見直し (Streamlit OIDC) | ❌ | cookie 自体は署名済で問題なし。サーバー側 state がインスタンス間で共有されないのが本質 |
| **`--session-affinity` 有効化 (Cloud Run 機能)** | ⭕ | **採用**: cookie ベースで同じインスタンスにルーティング固定、副作用なし、料金影響なし、設定変更 1 コマンド |

## 決定

pay-dashboard に Cloud Run の sessionAffinity を有効化する。

```bash
gcloud run services update pay-dashboard \
  --session-affinity \
  --region=asia-northeast1 \
  --project=monthly-pay-tax
```

設定確認:

```bash
gcloud run services describe pay-dashboard --region=asia-northeast1 --project=monthly-pay-tax --format=json | \
  python3 -c "import json,sys; d=json.load(sys.stdin); print(d['spec']['template']['metadata']['annotations'].get('run.googleapis.com/sessionAffinity'))"
# → true
```

## 影響

| 項目 | 影響 |
|------|------|
| 認証フロー | OAuth callback が同じインスタンスにルーティングされ、再認証ループ解消 |
| パフォーマンス | 同じユーザーが同じインスタンスに振られるため、Streamlit の WebSocket 接続も維持されやすい (副次的に体感速度向上) |
| 料金 | **影響なし** (Cloud Run の標準機能、課金単位は変わらない) |
| スケーラビリティ | max-instances=3 のまま。session affinity は cookie ベースなので新規ユーザーは引き続き複数インスタンスに分散 |
| ロールバック | `gcloud run services update pay-dashboard --no-session-affinity --region=asia-northeast1` で即座に元に戻せる |

## 関連 ADR

- **ADR-0003**: Streamlit OIDC 認証 (Google OAuth, tadakayo.jp ドメイン)
- **ADR-0004**: Cloud Run `--no-cpu-throttling --max-instances=3` (この PR と組み合わせて適切に運用)

## 副次的に発見した別件 (本 ADR 範囲外)

直近 7 日で Cloud Run pay-dashboard に **OOM (Memory 512MiB exceeded) が 4 件発生**。session affinity 修正で OAuth リダイレクトループは解消するが、OOM は別問題。memory 増強 (512 → 1 GiB) は別 PR / ADR で検討予定。

## 運用への適用

切り分け手順は `docs/operations/20260607_OAuth_リダイレクトループ_切り分け.md` に整備。同様の症状が再発した際の調査手順としてダッシュボードの「運用ドキュメント」ページから user/checker/admin 全員が閲覧可能。
