# ADR-0003: 認証方式 Cloud IAP → Streamlit OIDC 移行

## ステータス
採用

## コンテキスト
Phase 5（Dashboard Multipage化）当初、Cloud IAP + Load Balancer 構成で認証を実装していた。

課題:
- Cloud IAPにはロール概念がなく、admin/viewer の粒度制御はアプリ層で別途必要
- Load Balancer（L7）のコストが月額約$20かかる
- SSL証明書を自己署名 + sslip.io ドメインで管理する運用負担
- IAP認証後に `X-Goog-IAP-JWT-Assertion` ヘッダーを検証する実装が必要

## 決定
PR #9 にて Cloud IAP を廃止し、Streamlit 1.36+ のネイティブ OIDC（`st.login` / `st.user`）に移行。

## 理由

1. **コスト削減**: Load Balancer 廃止により月額約$20削減。Cloud Run の `--allow-unauthenticated` + アプリ層認証に移行。
2. **URL簡略化**: `*.run.app` ドメインで Google 管理 SSL 証明書を無償利用。sslip.io / 自己署名証明書が不要に。
3. **実装簡略化**: `st.user.email` でメールアドレスを直接取得できるため、JWTヘッダー検証コードが不要。
4. **ドメイン制限**: OAuthブランドを `orgInternalOnly: true` に設定することで、tadakayo.jp ドメイン限定アクセスを IdP レベルで保証。

## 技術構成

```
ブラウザ → Cloud Run pay-dashboard (--allow-unauthenticated)
  → 未ログイン時: st.login() → Google OAuth (tadakayo.jp限定)
  → ログイン済み: st.user.email → BQ dashboard_users 照合 → ロール付与
```

- Secret Manager `dashboard-auth-config` → `/app/.streamlit/secrets.toml` にマウント
- secrets.toml: client_id, client_secret, redirect_uri, cookie_secret, server_metadata_url
- `st.session_state` にロールをキャッシュ（BQ照合は初回のみ）

## 影響

- アクセスURL変更: `https://pay-dashboard.sslip.io` → `https://pay-dashboard-209715990891.asia-northeast1.run.app`
- Cloud IAP / Load Balancer / 静的IPリソースを削除
- `lib/auth.py`: `get_iap_user_email()` → `get_user_email()`（`st.user.email` ベース）に置換
- BQ障害時フォールバック: 初期管理者メールアドレスをハードコードで admin として扱う
