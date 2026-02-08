"""アーキテクチャドキュメント（Mermaid図 + 説明）"""

import streamlit as st
from streamlit_mermaid import st_mermaid

st.header("アーキテクチャ")
st.caption("システム構成・データフロー・スキーマの全体像")


# === 1. 全体構成図 ===
st.subheader("1. 全体構成")
st.markdown("""
毎朝6時にCloud Schedulerがバッチを起動し、約190件のスプレッドシートからデータを収集してBigQueryに書き込みます。
ダッシュボードはBQ VIEWs経由でデータを取得し、Cloud IAP経由でアクセス制御されています。
""")

st_mermaid("""
graph LR
    CS[Cloud Scheduler<br/>毎朝6時 JST] -->|OIDC認証| CR[Cloud Run<br/>pay-collector]
    CR -->|Sheets API v4<br/>キーレスDWD| SS[(190個の<br/>スプレッドシート)]
    CR -->|WRITE_TRUNCATE| BQ[(BigQuery<br/>pay_reports)]
    BQ -->|VIEWs| DB[Cloud Run<br/>pay-dashboard]
    IAP[Cloud IAP<br/>tadakayo.jp] -->|認証| DB
    DB -->|Streamlit| BR[ブラウザ]
""")

st.markdown("""
| コンポーネント | 仕様 |
|:---|:---|
| Collector | Python 3.12 / Flask / gunicorn / 2GiB |
| Dashboard | Python 3.12 / Streamlit / 512MiB |
| 認証 | Workload Identity + IAM signBlob (キーレスDWD) |
| BQ取り込み | WRITE_TRUNCATE（毎回全データ置換） |
""")


# === 2. データフロー ===
st.subheader("2. データフロー")
st.markdown("""
管理表から190件のスプレッドシートURLを取得し、各シートから業務報告(gyomu)と補助報告(hojo)を収集します。
メンバーマスタ(members)は管理表のA:K列から取得。
""")

st_mermaid("""
graph TD
    MGR[管理表<br/>URLリスト + メンバーマスタ] -->|URL一覧| COL[Collector]
    COL -->|各SSを巡回| G[gyomu_reports<br/>~17,000行]
    COL -->|各SSを巡回| H[hojo_reports<br/>~1,100行]
    MGR -->|A:K列| M[members<br/>190行]
    WT[withholding_targets<br/>源泉対象リスト] -.->|手動管理| BQ
    G --> BQ[(BigQuery)]
    H --> BQ
    M --> BQ
    BQ --> VG[v_gyomu_enriched]
    BQ --> VH[v_hojo_enriched]
    VG --> VMC[v_monthly_compensation]
    VH --> VMC
""")


# === 3. BQスキーマ ER図 ===
st.subheader("3. BQスキーマ")
st.markdown("""
4テーブル + 3 VIEW。`source_url = report_url` でメンバー結合。
""")

st_mermaid("""
erDiagram
    gyomu_reports ||--o{ members : "source_url = report_url"
    hojo_reports ||--o{ members : "source_url = report_url"
    gyomu_reports {
        STRING source_url PK
        STRING year
        STRING date
        STRING activity_category
        STRING work_category
        STRING sponsor
        STRING amount
    }
    hojo_reports {
        STRING source_url PK
        STRING year
        STRING month
        STRING dx_subsidy
        STRING reimbursement
        STRING total_amount
    }
    members {
        STRING report_url PK
        STRING member_id
        STRING nickname
        STRING full_name
        STRING position_rate
        STRING qualification_allowance
    }
    withholding_targets {
        STRING work_category PK
        STRING licensed_member_id
    }
    dashboard_users {
        STRING email PK
        STRING role
        STRING display_name
    }
""")


# === 4. VIEW計算チェーン ===
st.subheader("4. v_monthly_compensation 計算チェーン")
st.markdown("""
月別報酬は6つのCTE（共通テーブル式）を経て最終的な支払額を算出します。
源泉徴収は `-FLOOR(対象額 * 0.1021)` で計算。法人・寄付シートは源泉免除、士業は全額対象。
""")

st_mermaid("""
graph TD
    CTE1[gyomu_agg<br/>業務報告の月別集計<br/>時間/距離/金額/源泉対象額] --> CTE4
    CTE2[hojo_agg<br/>補助報告の月別集計<br/>DX補助/立替] --> CTE4
    CTE3[member_attrs<br/>メンバー属性<br/>法人/寄付/士業フラグ] --> CTE5
    CTE4[all_keys<br/>gyomu+hojo キー統合] --> CTE5
    CTE5[base_calc<br/>小計 → 役職手当 → 資格手当] --> CTE6
    CTE6[with_tax<br/>源泉対象額 → 源泉徴収] --> FINAL
    FINAL[最終SELECT<br/>支払い = 報酬 + 源泉 + DX + 立替]
""")

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


# === 5. 認証フロー ===
st.subheader("5. 認証フロー")

st_mermaid("""
graph TD
    USER[ユーザー] -->|HTTPS| IAP[Cloud IAP<br/>tadakayo.jpドメイン認証]
    IAP -->|X-Goog-Authenticated-User-Email| APP[Dashboard App]
    APP -->|email照合| BQ[(BQ dashboard_users)]
    BQ -->|未登録| DENY[アクセス拒否]
    BQ -->|viewer| VIEW[ダッシュボード<br/>+ ドキュメント<br/>+ ヘルプ]
    BQ -->|admin| ADMIN[上記 +<br/>ユーザー管理<br/>+ 管理設定]
    BQ -->|BQ障害時| FB{フォールバック}
    FB -->|初期管理者| ADMIN
    FB -->|その他| DENY
""")
