# ADR 0002: ダッシュボードマルチページ化 + BQベースの認可

## Status
Accepted

## Context
- ダッシュボードが単一ファイル(app.py, 649行)に肥大化
- Cloud IAPで認証はされているが、アプリ内のアクセス制御がない
- 管理者機能（ユーザー管理）とドキュメントページの追加が必要

## Decision

### マルチページ構成
- Streamlitの `st.navigation` APIを使用してマルチページ化
- `app.py` はルーター（認証 + ページ定義）に特化（~50行）
- 共有ロジックは `lib/` ディレクトリに分離

### 認可方式
- BQ `dashboard_users` テーブルによるホワイトリスト方式
- admin/viewer の2ロール構成
- BQ障害時は初期管理者のみadminとしてフォールバック
- `st.session_state` にロールをキャッシュ

### 代替案の検討
1. **Firestore**: リアルタイム性は不要。既存BQインフラとの一貫性を優先
2. **Cloud IAP条件**: IAP自体にロール概念がない。アプリ層で制御が必要
3. **環境変数によるハードコード**: スケーラビリティに欠ける
4. **Streamlitネイティブのマルチページ(ファイルベース)**: `st.navigation` APIの方が認証との統合が容易

## Consequences
- BQにUNIQUE制約がないため、アプリ層でemail重複チェックが必要
- ユーザー管理操作後はロールキャッシュのクリアが必要
- `st.set_page_config` はapp.pyでのみ1回呼び出し
- `streamlit-mermaid` パッケージの追加依存
