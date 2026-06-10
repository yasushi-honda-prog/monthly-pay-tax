"""アーキテクチャドキュメント（Mermaid図 + 説明）"""

import streamlit as st

from lib.doc_styles import apply_doc_styles, render_hero, render_section_header
from lib.mermaid_renderer import render_mermaid


# --- 共通トンマナ CSS ---
apply_doc_styles()

# --- ヒーロー ---
render_hero(
    "🏗️ アーキテクチャ",
    "システム構成・データフロー・BQスキーマ・認証フロー・<br>"
    "セキュリティ設計までの全体像を Mermaid 図と表で解説します。",
    color="blue",
)


# === 1. 全体構成図 ===
render_section_header("1. 全体構成", icon="🌐", color="blue")
st.markdown("""
毎朝6時にCloud Schedulerがバッチを起動し、約190件のスプレッドシートからデータを収集してBigQueryに書き込みます。
ダッシュボードはBQ VIEWs経由でデータを取得し、Streamlit OIDC（Google OAuth）でアクセス制御されています。
""")

render_mermaid("""
graph LR
    CS[Cloud Scheduler<br/>毎朝6時 JST] -->|OIDC認証| CR[Cloud Run<br/>pay-collector]
    CS2[Cloud Scheduler<br/>毎月1日7時 JST<br/>予実評価] -->|OIDC認証| CR
    CR -->|Step0: BQ唯一ソース7表を<br/>日次snapshot| BKUP[(pay_reports_backup<br/>90日自動失効)]
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
    CR -->|POST /eval/team-monthly<br/>Gemini 2.5 Flash| VTX[Vertex AI<br/>asia-northeast1]
    VTX -->|評価コメント生成| TME[team_monthly_eval<br/>claim row pattern]
    TME --> BQ
    CR -.->|障害時| CHAT[Google Chat<br/>障害自動通知]
    BQ -->|VIEWs| DB[Cloud Run<br/>pay-dashboard]
    BR[ブラウザ] -->|HTTPS *.run.app| DB
    DB -->|Streamlit OIDC<br/>Google OAuth| GOOG[Google IdP<br/>tadakayo.jp]
""", height=520)

st.markdown("""
| コンポーネント | 仕様 |
|:---|:---|
| Collector | Python 3.12 / Flask / gunicorn / 2GiB（Step 0-7: snapshot → SS巡回 → BQ投入 → グループ → 同期 → 立替金 → タダメンM。障害時 Google Chat 通知） |
| Dashboard | Python 3.12 / Streamlit / 512MiB（9ページ: ダッシュボード6タブ / 予実管理3サブタブ / 報告入力 / 業務チェック / WAM立替金確認6タブ / アーキテクチャ / ヘルプ / ユーザー管理 / 管理設定） |
| Collector認証 | Workload Identity + IAM signBlob (キーレスDWD) |
| Dashboard認証 | Streamlit OIDC (Google OAuth, tadakayo.jpドメイン) |
| BQ取り込み | WRITE_TRUNCATE（毎回全データ置換）|
| BQスキーマ | 10テーブル + 4 VIEW + バックアップ用データセット pay_reports_backup |
| BQバックアップ | Step0: BQ唯一ソース7表（dashboard_users / dashboard_sync_groups / check_logs / wam_target_projects / withholding_targets / team_budgets / team_monthly_eval）を pay_reports_backup へ日次snapshot（90日自動失効、誤操作復旧用） |
| 予実評価 | 毎月1日7時 JST、Cloud Scheduler 起動 → pay-collector の /eval/team-monthly が前月の隊×月予実を Vertex AI Gemini 2.5 Flash (asia-northeast1) で評価し team_monthly_eval へ書き込み |
| グループ更新 | Step4: Admin Directory API でグループ情報を自動更新 |
| ユーザー同期 | Step5: グループ由来のdashboard_usersをグループメンバーと自動同期（追加/削除） |
| 立替金収集 | Step6: 立替金シートを巡回し reimbursement_items テーブルへ投入 |
| メンバーマスタ | Step7: 管理表タダメンMタブから member_master（36列×240件）を全量取得 |
| 障害通知 | 全エンドポイント（バッチ / 手動同期）の致命的エラー + 毎朝バッチの部分失敗を Google Chat スペースへ自動通知 |
""")


# === 2. データフロー ===
render_section_header("2. データフロー", icon="🔁", color="blue")
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
render_section_header("3. BQスキーマ", icon="🗄️", color="blue")
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
render_section_header("4. v_monthly_compensation 計算チェーン", icon="🧮", color="amber")
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
render_section_header("4.5 v_reimbursement_enriched", icon="💸", color="amber")
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
render_section_header("5. ダッシュボード ページ構成", icon="🧭", color="purple")
st.markdown("""
マルチページ構成（`st.navigation`）。ロールによってアクセスできるページが異なります。
ロールは `user` / `viewer` / `checker` / `admin` の4段階（viewer は user と同等の閲覧専用、歴史的互換ロール）。
""")

render_mermaid("""
graph TD
    APP[pay-dashboard<br/>Streamlit App] --> P1[ダッシュボード 6タブ<br/>全ロール]
    APP --> P2[業務チェック<br/>checker / admin]
    APP --> P7[WAM立替金確認 6タブ<br/>checker / admin]
    APP --> P3[アーキテクチャ<br/>全ロール]
    APP --> P8[運用ドキュメント<br/>全ロール]
    APP --> P4[ヘルプ<br/>全ロール]
    APP --> P1B["(仮) 報告入力<br/>admin のみ"]
    APP --> P9[GAS管理<br/>admin のみ]
    APP --> P5[ユーザー管理<br/>admin のみ]
    APP --> P6[管理設定<br/>admin のみ]

    P1 --> T1[月別報酬サマリー<br/>月次支払額/活動時間/報酬明細/月次推移]
    P1 --> T2[スポンサー別業務委託費<br/>メンバー別月次/隊（活動）分類別]
    P1 --> T3[業務報告一覧<br/>全明細フィルタ/検索]
    P1 --> T3W[WAM業務報告<br/>業務分類が「（WAM）」始まりのみ]
    P1 --> T4[グループ別<br/>メンバー一覧/月別報酬/業務報告]
    P1 --> T5[業務委託費分析<br/>分類別集計/非営利活動]

    P7 --> W1[PJ別サマリー]
    P7 --> W2[メンバー別明細]
    P7 --> W3[領収書添付状況]
    P7 --> W4[月別報酬・振込確認]
    P7 --> W5[支払明細書]
    P7 --> W6[年間支払調書データ]
""", height=780)


# === 6. 認証フロー ===
render_section_header("6. 認証フロー", icon="🔐", color="purple")

render_mermaid("""
graph TD
    USER[ユーザー] -->|HTTPS *.run.app| APP[Dashboard App]
    APP -->|未ログイン| LOGIN[Googleでログイン<br/>st.login]
    LOGIN -->|Google OIDC| GOOG[Google IdP<br/>tadakayo.jpドメイン限定]
    GOOG -->|st.user.email| APP
    APP -->|email照合| BQ[(BQ dashboard_users)]
    BQ -->|未登録| DENY[アクセス拒否]
    BQ -->|user / viewer| VIEW[ダッシュボード<br/>+ アーキテクチャ<br/>+ 運用ドキュメント<br/>+ ヘルプ]
    BQ -->|checker| CHECK[上記 +<br/>業務チェック管理表<br/>+ WAM立替金確認 6タブ]
    BQ -->|admin| ADMIN["上記 +<br/>ユーザー管理<br/>+ 管理設定<br/>+ GAS管理<br/>+ (仮)報告入力"]
    ADMIN -->|グループ一括登録| GRP[groups_master<br/>からメンバー取得]
    GRP -->|MERGE INSERT| BQ
    BQ -->|BQ障害時| FB{フォールバック}
    FB -->|初期管理者| ADMIN
    FB -->|その他| DENY
""", height=650)


# === 6.5 ロール権限マトリックス ===
render_section_header("6.5 ロール権限マトリックス", icon="🎭", color="purple")

st.markdown("#### ページ × ロール アクセス可否")
st.markdown("""
| ページ / 機能 | user | viewer | checker | admin |
|---|:---:|:---:|:---:|:---:|
| ダッシュボード（6タブ：月別報酬／スポンサー別／業務報告一覧／WAM業務報告／グループ別／業務委託費分析） | ✅ | ✅ | ✅ | ✅ |
| アーキテクチャ / 運用ドキュメント / ヘルプ | ✅ | ✅ | ✅ | ✅ |
| 業務チェック管理 | ❌ | ❌ | ✅ | ✅ |
| WAM立替金確認（6タブ） | ❌ | ❌ | ✅ | ✅ |
| (仮) 報告入力 | ❌ | ❌ | ❌ | ✅ |
| GAS管理 | ❌ | ❌ | ❌ | ✅ |
| ユーザー管理 | ❌ | ❌ | ❌ | ✅ |
| 管理設定 | ❌ | ❌ | ❌ | ✅ |

※ `viewer` は user と同等の閲覧専用ロール（歴史的互換）。新規登録は `user` を推奨。
""")

st.markdown("#### 機密情報 × ロール 露出マトリックス")
st.caption("各画面・出力ファイルに含まれる個人情報・機密情報のロール別アクセス可否")
st.markdown("""
| 出力箇所 | 含む情報 | user / viewer | checker | admin |
|---|---|:---:|:---:|:---:|
| ダッシュボード6タブ | 集計値 / nickname / 金額 | ✅ | ✅ | ✅ |
| 業務チェック管理 | 報告URL / チェックステータス / コメント | ❌ | ✅ | ✅ |
| WAM Tab2 メンバー別明細 | 立替明細 / シートURL | ❌ | ✅ | ✅ |
| **WAM Tab4 振込CSV** | **氏名 / 銀行コード / 口座番号** | ❌ | ✅ | ✅ |
| **WAM Tab5 支払明細書PDF** | **氏名** / 業務委託費・立替経費明細 | ❌ | ✅ | ✅ |
| **WAM Tab6 年間支払調書CSV** | **氏名 / カナ氏名 / 住所 / 口座 / member_id** | ❌ | ✅ | ✅ |
| ユーザー管理 | メールアドレス / ロール / source_group | ❌ | ❌ | ✅ |
| 管理設定 | BQテーブル更新時刻 / 手動同期 / システム設定 | ❌ | ❌ | ✅ |
| **member_master 直接閲覧** | **全口座・住所・カナ等** | (UI非表示) | (UI非表示) | (UI非表示・CSV出力経由のみ) |

※ 太字は個人情報を含む箇所。`member_master` テーブル自体は UI 非表示で、CSV/PDF 出力経由でのみ部分露出する設計。
""")

st.markdown("#### 設計方針")
st.markdown("""
- **user / viewer** は閲覧専用の一般メンバー。viewer は歴史的経緯で残る互換ロールで、新規登録は user 推奨
- **checker** は業務チェック・WAM立替金確認の実務担当ロール
- **admin** はユーザー管理・システム設定・GAS管理・(仮)報告入力を含む管理者ロール
- 個人情報（氏名・口座・住所）はすべて checker / admin に統一して可視化（一貫性重視）
- ロール変更時はこのマトリックスを更新し、`dashboard/app.py` の `*_pages` 配列および `lib/doc_styles.py` の `ROLE_DEFINITIONS` と整合させる
""")


# === 7. セキュリティアーキテクチャ ===
render_section_header("7. セキュリティアーキテクチャ", icon="🛡️", color="red")
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
| データ | BQ唯一ソーステーブルの日次snapshotバックアップ（誤操作・誤DELETE/MERGE復旧、90日保持） | `cloud-run/bq_loader.py` `create_snapshots()` / Step0 |
| 可用性 | バッチ障害の Google Chat 自動通知（致命的 + 部分失敗集約、テクニカル内容のみ） | `cloud-run/chat_notifier.py` |
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
| Google Chat webhook URL | Secret Manager → `chat-webhook-url`（env `CHAT_WEBHOOK_URL`、未設定なら通知 no-op） |
| Collector SA 認証情報 | Workload Identity（鍵ファイルなし） |
| BQ アクセス | SA のIAMロール（BQ Data Editor + Secret Accessor） |
| Dashboard SA 認証情報 | Cloud Run デフォルトSA + Workload Identity |
""")

st.markdown("**今後の改善候補**")
st.markdown("""
| 項目 | 現状 | 改善案 |
|:---|:---|:---|
| Collectorエンドポイント認証 | Cloud Run IAM（インフラ層）で保護 | アプリ層でもOIDCトークン検証を追加 |
| ロール変更監査ログ | 未実装 | `user_role_audit_log` テーブルで変更履歴を記録 |
""")
