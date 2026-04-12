"""アーキテクチャドキュメント（Mermaid図 + 説明）"""

import streamlit as st
import streamlit.components.v1 as components


def render_mermaid(code: str, height: int = 500):
    """Mermaid図をダークモード対応でレンダリング"""
    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <script src="https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.min.js"></script>
        <style>
            body {{
                background: transparent;
                margin: 0;
                padding: 0;
                display: flex;
                justify-content: center;
                align-items: flex-start;
            }}
            .mermaid {{
                width: 100%;
            }}
            .mermaid svg {{
                width: 100% !important;
                max-height: {height - 20}px;
            }}
        </style>
    </head>
    <body>
        <pre class="mermaid">{code}</pre>
        <script>
            const isDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
            mermaid.initialize({{
                startOnLoad: true,
                theme: isDark ? 'dark' : 'default',
                themeVariables: isDark ? {{
                    primaryColor: '#1e3a5f',
                    primaryTextColor: '#e0e0e0',
                    lineColor: '#4a9eff',
                    secondaryColor: '#2d2d2d',
                    tertiaryColor: '#1a1a2e',
                    fontSize: '18px',
                }} : {{
                    primaryColor: '#e8f4fd',
                    primaryTextColor: '#1a1a1a',
                    lineColor: '#0EA5E9',
                    fontSize: '18px',
                }},
                flowchart: {{ curve: 'basis', padding: 20, nodeSpacing: 50, rankSpacing: 60 }},
                fontSize: 18,
            }});
        </script>
    </body>
    </html>
    """
    components.html(html, height=height)


st.header("アーキテクチャ")
st.caption("システム構成・データフロー・スキーマの全体像")


# === 1. 全体構成図 ===
st.subheader("1. 全体構成")
st.markdown("""
毎朝6時にCloud Schedulerがバッチを起動し、約190件のスプレッドシートからデータを収集してBigQueryに書き込みます。
ダッシュボードはBQ VIEWs経由でデータを取得し、Streamlit OIDC（Google OAuth）でアクセス制御されています。
""")

render_mermaid("""
graph LR
    CS[Cloud Scheduler<br/>毎朝6時 JST] -->|OIDC認証| CR[Cloud Run<br/>pay-collector]
    CR -->|Step1-3: Sheets API v4<br/>キーレスDWD| SS[(190個の<br/>スプレッドシート)]
    CR -->|WRITE_TRUNCATE| BQ[(BigQuery<br/>pay_reports)]
    CR -->|Step4: Admin Directory API| ADK[Google Admin SDK<br/>グループ情報]
    ADK -->|groups_master / members更新| BQ
    CR -->|Step5: グループ同期| DU[dashboard_users<br/>自動追加/削除]
    DU --> BQ
    CR -->|Step6: 立替金シート巡回| RS[立替金シート<br/>reimbursement_items]
    RS --> BQ
    CR -->|Step7: タダメンM取得| MM[member_master<br/>240件]
    MM --> BQ
    BQ -->|VIEWs| DB[Cloud Run<br/>pay-dashboard]
    BR[ブラウザ] -->|HTTPS *.run.app| DB
    DB -->|Streamlit OIDC<br/>Google OAuth| GOOG[Google IdP<br/>tadakayo.jp]
""", height=420)

st.markdown("""
| コンポーネント | 仕様 |
|:---|:---|
| Collector | Python 3.12 / Flask / gunicorn / 2GiB（Step 1-7: SS巡回 → BQ投入 → グループ → 同期 → 立替金 → タダメンM） |
| Dashboard | Python 3.12 / Streamlit / 512MiB（8ページ: ダッシュボード5タブ / 報告入力 / 業務チェック / WAM立替金確認6タブ / アーキテクチャ / ヘルプ / ユーザー管理 / 管理設定） |
| Collector認証 | Workload Identity + IAM signBlob (キーレスDWD) |
| Dashboard認証 | Streamlit OIDC (Google OAuth, tadakayo.jpドメイン) |
| BQ取り込み | WRITE_TRUNCATE（毎回全データ置換）|
| BQスキーマ | 10テーブル + 4 VIEW |
| グループ更新 | Step4: Admin Directory API でグループ情報を自動更新 |
| ユーザー同期 | Step5: グループ由来のdashboard_usersをグループメンバーと自動同期（追加/削除） |
| 立替金収集 | Step6: 立替金シートを巡回し reimbursement_items テーブルへ投入 |
| メンバーマスタ | Step7: 管理表タダメンMタブから member_master（36列×240件）を全量取得 |
""")


# === 2. データフロー ===
st.subheader("2. データフロー")
st.markdown("""
管理表から190件のスプレッドシートURLを取得し、各シートから業務報告(gyomu)と補助報告(hojo)を収集します。
メンバーマスタ(members)は管理表のA:K列から取得。立替金シートとタダメンMマスタも定期収集しています。
""")

render_mermaid("""
graph TD
    MGR[管理表<br/>URLリスト + メンバーマスタ] -->|URL一覧| COL[Collector]
    COL -->|Step1-2: 各SSを巡回| G[gyomu_reports<br/>~14,000行]
    COL -->|Step1-2: 各SSを巡回| H[hojo_reports<br/>~950行]
    MGR -->|A:K列| M[members<br/>192行 + groups列]
    ADK[Admin Directory API] -->|Step4: グループ所属| GM[groups_master<br/>69グループ]
    ADK -->|groups列更新| M
    ADK -->|Step5: グループメンバー同期| DU[dashboard_users<br/>グループ由来ユーザー<br/>自動追加/削除]
    COL -->|Step6: 立替金シート巡回| RI[reimbursement_items<br/>~2,250行]
    MGR -->|Step7: タダメンMタブ| MM[member_master<br/>36列×240件]
    WT[withholding_targets<br/>源泉対象リスト] -.->|手動管理| BQ
    WTP[wam_target_projects<br/>WAM対象PJマスタ] -.->|手動管理| BQ
    G --> BQ[(BigQuery)]
    H --> BQ
    M --> BQ
    GM --> BQ
    DU --> BQ
    RI --> BQ
    MM --> BQ
    BQ --> VG[v_gyomu_enriched]
    BQ --> VH[v_hojo_enriched]
    VG --> VMC[v_monthly_compensation]
    VH --> VMC
    BQ --> VRE[v_reimbursement_enriched]
    DB[Dashboard] -->|checker/admin操作| CL[check_logs]
    DB -->|admin: グループ一括登録| DU
    CL --> BQ
""", height=780)


# === 3. BQスキーマ ER図 ===
st.subheader("3. BQスキーマ")
st.markdown("""
10テーブル + 4 VIEW。`source_url = report_url` でメンバー結合。`member_master`は口座・住所等のセンシティブデータを含む（UI非表示、CSV出力のみ）。
""")

render_mermaid("""
erDiagram
    gyomu_reports ||--o{ members : "source_url = report_url"
    hojo_reports ||--o{ members : "source_url = report_url"
    check_logs ||--o{ members : "source_url = report_url"
    reimbursement_items ||--o{ members : "source_url = report_url"
    member_master ||--o{ members : "member_id"
    gyomu_reports {
        STRING source_url
        STRING year
        STRING date
        STRING activity_category
        STRING work_category
        STRING sponsor
        STRING amount
    }
    hojo_reports {
        STRING source_url
        STRING year
        STRING month
        STRING dx_subsidy
        STRING reimbursement
        STRING total_amount
    }
    members {
        STRING report_url
        STRING member_id
        STRING nickname
        STRING full_name
        STRING position_rate
        STRING qualification_allowance
        STRING groups
    }
    reimbursement_items {
        STRING source_url
        STRING nickname
        STRING date
        STRING target_project
        STRING category
        STRING payment_amount
        STRING receipt_url
    }
    member_master {
        STRING member_id
        STRING nickname
        STRING email
        STRING bank1_bank_name
        STRING bank1_account_number
    }
    wam_target_projects {
        STRING target_project
        STRING wam_flag
        STRING note
    }
    withholding_targets {
        STRING work_category
        STRING licensed_member_id
    }
    groups_master ||--o{ dashboard_users : "group_email = source_group"
    dashboard_users {
        STRING email
        STRING role
        STRING display_name
        STRING source_group
    }
    check_logs {
        STRING source_url
        STRING year
        STRING month
        STRING status
        STRING checker_email
        STRING memo
    }
    groups_master {
        STRING group_email
        STRING group_name
    }
    reimbursement_items }o--|| wam_target_projects : "target_project"
""", height=950)


# === 4. VIEW計算チェーン ===
st.subheader("4. v_monthly_compensation 計算チェーン")
st.markdown("""
月別報酬は6つのCTE（共通テーブル式）を経て最終的な支払額を算出します。
源泉徴収は `-FLOOR(対象額 * 0.1021)` で計算。法人・寄付シートは源泉免除、士業は全額対象。
""")

render_mermaid("""
graph TD
    CTE1[gyomu_agg<br/>業務報告の月別集計<br/>時間/距離/金額/源泉対象額] --> CTE4
    CTE2[hojo_agg<br/>補助報告の月別集計<br/>DX補助/立替] --> CTE4
    CTE3[member_attrs<br/>メンバー属性<br/>法人/寄付/士業フラグ] --> CTE5
    CTE4[all_keys<br/>gyomu+hojo キー統合] --> CTE5
    CTE5[base_calc<br/>小計 → 役職手当 → 資格手当] --> CTE6
    CTE6[with_tax<br/>源泉対象額 → 源泉徴収] --> FINAL
    FINAL[最終SELECT<br/>支払い = 報酬 + 源泉 + DX + 立替]
""", height=550)

st.markdown("""
| CTE | 内容 | 主要カラム |
|:---|:---|:---|
| gyomu_agg | 業務報告を source_url/year/month で集計 | work_hours, hour_compensation, travel_distance_km |
| hojo_agg | 補助報告を source_url/year/month で集計 | dx_subsidy, reimbursement |
| member_attrs | メンバーの属性フラグを算出 | is_corporate, is_donation, is_licensed |
| all_keys | gyomu + hojo のキーを UNION | source_url, year, month |
| base_calc | 小計 → 役職手当率 → 資格手当加算 | subtotal, position_adjusted, qualification_adjusted |
| with_tax | 源泉対象額と源泉徴収を計算 | withholding_target_amount, withholding_tax |
""")

# === 4.5 v_reimbursement_enriched ===
st.subheader("4.5 v_reimbursement_enriched")
st.markdown("""
立替金シート明細にメンバー情報とWAM対象PJ判定を結合するVIEW。WAM立替金確認ページのデータソース。
""")

render_mermaid("""
graph LR
    RI[reimbursement_items] -->|nickname JOIN| M[members]
    RI -->|target_project JOIN| WTP[wam_target_projects]
    M --> VRE[v_reimbursement_enriched<br/>立替金 + メンバー + WAM判定]
    WTP --> VRE
""", height=250)

st.markdown("""
| 結合元 | 結合キー | 追加情報 |
|:---|:---|:---|
| reimbursement_items | ベーステーブル | 立替金明細（日付、対象PJ、金額、領収書URL等） |
| members | nickname | member_id, report_url, gws_account |
| wam_target_projects | target_project | wam_flag（WAM対象PJかどうか） |
""")


# === 5. ダッシュボード ページ構成 ===
st.subheader("5. ダッシュボード ページ構成")
st.markdown("""
マルチページ構成（`st.navigation`）。ロールによってアクセスできるページが異なります。
ロールは `user` / `checker` / `admin` の3段階です。
""")

render_mermaid("""
graph TD
    APP[pay-dashboard<br/>Streamlit App] --> P1[ダッシュボード 5タブ<br/>全ロール]
    APP --> P1B[報告入力<br/>全ロール]
    APP --> P2[業務チェック<br/>checker / admin]
    APP --> P3[アーキテクチャ<br/>全ロール]
    APP --> P4[ヘルプ<br/>全ロール]
    APP --> P7[WAM立替金確認 6タブ<br/>admin のみ]
    APP --> P5[ユーザー管理<br/>admin のみ]
    APP --> P6[管理設定<br/>admin のみ]

    P1 --> T1[月別報酬サマリー<br/>月次支払額/活動時間/報酬明細/月次推移]
    P1 --> T2[スポンサー別業務委託費<br/>メンバー別月次/活動分類別]
    P1 --> T3[業務報告一覧<br/>全明細フィルタ/検索]
    P1 --> T4[グループ別<br/>メンバー一覧/月別報酬/業務報告]
    P1 --> T5[業務委託費分析<br/>分類別集計/非営利活動]

    P7 --> W1[PJ別サマリー]
    P7 --> W2[メンバー別明細]
    P7 --> W3[領収書添付状況]
    P7 --> W4[月別報酬・振込確認]
    P7 --> W5[支払明細書]
    P7 --> W6[年間支払調書データ]
""", height=700)


# === 6. 認証フロー ===
st.subheader("6. 認証フロー")

render_mermaid("""
graph TD
    USER[ユーザー] -->|HTTPS *.run.app| APP[Dashboard App]
    APP -->|未ログイン| LOGIN[Googleでログイン<br/>st.login]
    LOGIN -->|Google OIDC| GOOG[Google IdP<br/>tadakayo.jpドメイン限定]
    GOOG -->|st.user.email| APP
    APP -->|email照合| BQ[(BQ dashboard_users)]
    BQ -->|未登録| DENY[アクセス拒否]
    BQ -->|user| VIEW[ダッシュボード<br/>+ 報告入力<br/>+ アーキテクチャ<br/>+ ヘルプ]
    BQ -->|checker| CHECK[上記 +<br/>業務チェック管理表]
    BQ -->|admin| ADMIN[上記 +<br/>WAM立替金確認<br/>+ ユーザー管理<br/>+ 管理設定]
    ADMIN -->|グループ一括登録| GRP[groups_master<br/>からメンバー取得]
    GRP -->|MERGE INSERT| BQ
    BQ -->|BQ障害時| FB{フォールバック}
    FB -->|初期管理者| ADMIN
    FB -->|その他| DENY
""", height=650)


# === 7. セキュリティアーキテクチャ ===
st.subheader("7. セキュリティアーキテクチャ")
st.markdown("""
本システムのセキュリティは4つのレイヤーで構成されています。
""")

render_mermaid("""
graph TD
    subgraph NW["ネットワーク層"]
        HTTPS[HTTPS終端<br/>Cloud Run マネージド SSL]
        IAM[Cloud Run IAM認証<br/>Collector: OIDC トークン検証]
    end

    subgraph AUTH["認証層"]
        OIDC[Streamlit OIDC<br/>Google OAuth<br/>tadakayo.jpドメイン限定]
        DWD[キーレスDWD<br/>IAM signBlob API<br/>SA鍵ファイル不要]
    end

    subgraph AUTHZ["認可層"]
        RBAC[RBAC 3段階<br/>user / checker / admin]
        WL[ホワイトリスト<br/>BQ dashboard_users<br/>登録メールのみ許可]
    end

    subgraph DATA["データ層"]
        PQ[パラメータ化クエリ<br/>SQLインジェクション防止]
        ENC[BQ暗号化<br/>Google管理キー<br/>保存時自動暗号化]
    end

    NW --> AUTH
    AUTH --> AUTHZ
    AUTHZ --> DATA
""", height=650)

st.markdown("""
| カテゴリ | 制御 | 実装箇所 |
|:---|:---|:---|
| ネットワーク | HTTPS終端（マネージドSSL証明書） | Cloud Run |
| ネットワーク | Collector呼び出しはOIDCトークン必須 | Cloud Scheduler → Cloud Run IAM |
| 認証 | Googleドメイン制限（tadakayo.jpのみ） | Streamlit OIDC / OAuthブランド orgInternalOnly |
| 認証 | キーレスDWD（SA鍵ファイル不使用） | IAM signBlob API |
| 認可 | ロールベースアクセス制御（3段階） | `lib/auth.py` → BQ `dashboard_users` |
| 認可 | 未登録ユーザーのアクセス拒否 | `lib/auth.py` ホワイトリスト照合 |
| データ | パラメータ化クエリ（SQLインジェクション防止） | `lib/bq_client.py` / 各ページ |
| データ | 楽観的ロック（check_logs同時編集制御） | `pages/check_management.py` |
| データ | 操作ログ記録（action_log） | BQ `check_logs.action_log` |
| データ | BQ保存時暗号化（Google管理キー） | BigQuery デフォルト |
""")

st.markdown("**データ保護フロー**")

render_mermaid("""
graph LR
    INPUT[ユーザー入力<br/>ステータス・メモ] --> VALID[入力バリデーション<br/>Enum制約・文字数制限]
    VALID --> PARAM[パラメータ化クエリ<br/>query_parameters]
    PARAM --> BQ_ENC[BQ書き込み<br/>保存時自動暗号化]
    PARAM --> LOCK[楽観的ロック<br/>updated_at照合]
    LOCK -->|競合検出| ERR[競合エラー表示<br/>ページ再読込で解決]
    LOCK -->|OK| LOG[操作ログ記録<br/>action_log に追記]
    LOG --> BQ_ENC
""", height=400)

st.markdown("""
| シークレット | 保管方法 |
|:---|:---|
| OAuth クライアントID / シークレット | Secret Manager → `dashboard-auth-config` |
| Collector SA 認証情報 | Workload Identity（鍵ファイルなし） |
| BQ アクセス | SA のIAMロール（BQ Data Editor） |
| Dashboard SA 認証情報 | Cloud Run デフォルトSA + Workload Identity |
""")

st.markdown("**今後の改善候補**")
st.markdown("""
| 項目 | 現状 | 改善案 |
|:---|:---|:---|
| Collectorエンドポイント認証 | Cloud Run IAM（インフラ層）で保護 | アプリ層でもOIDCトークン検証を追加 |
| ロール変更監査ログ | 未実装 | `user_role_audit_log` テーブルで変更履歴を記録 |
""")
