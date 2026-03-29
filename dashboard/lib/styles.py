"""共有CSS"""

import streamlit as st

CUSTOM_CSS = """
<style>
    /* ページ上部の余白を縮小 */
    .main .block-container,
    section.main .block-container,
    [data-testid="stMain"] .block-container,
    .stMainBlockContainer {
        padding-top: 1.5rem !important;
    }

    /* multiselect タグのテキストを省略せず全表示 */
    [data-baseweb="tag"] span[class] {
        white-space: normal !important;
        overflow: visible !important;
        text-overflow: unset !important;
        max-width: none !important;
    }

    /* ヘッダー */
    .dashboard-header {
        padding: 0.25rem 0 1rem 0;
        border-bottom: 2px solid #0EA5E9;
        margin-bottom: 1rem;
    }
    .dashboard-header h1 {
        font-size: 1.75rem !important;
        font-weight: 700;
        margin: 0;
        letter-spacing: 0.02em;
    }

    /* サイドバーナビゲーションメニューのフォントサイズ（複数セレクタで対応） */
    [data-testid="stSidebarNavLink"],
    [data-testid="stSidebarNavLink"] span,
    [data-testid="stSidebarNavLink"] p,
    section[data-testid="stSidebar"] nav a,
    section[data-testid="stSidebar"] ul li a {
        font-size: 1rem !important;
    }

    /* ナビゲーションアイコン: サイズ拡大 */
    section[data-testid="stSidebar"] [data-testid="stSidebarNavLink"] svg {
        width: 1.4rem !important;
        height: 1.4rem !important;
        min-width: 1.4rem !important;
        transition: color 0.15s, fill 0.15s;
    }

    /* ホバー時: 青 */
    section[data-testid="stSidebar"] [data-testid="stSidebarNavLink"]:hover svg,
    section[data-testid="stSidebar"] [data-testid="stSidebarNavLink"]:hover svg path,
    section[data-testid="stSidebar"] [data-testid="stSidebarNavLink"]:hover svg circle,
    section[data-testid="stSidebar"] [data-testid="stSidebarNavLink"]:hover svg rect {
        color: #0EA5E9 !important;
        fill: #0EA5E9 !important;
    }

    /* 選択中（アクティブ）: 赤 */
    section[data-testid="stSidebar"] [data-testid="stSidebarNavLink"][aria-current="page"] svg,
    section[data-testid="stSidebar"] [data-testid="stSidebarNavLink"][aria-current="page"] svg path,
    section[data-testid="stSidebar"] [data-testid="stSidebarNavLink"][aria-current="page"] svg circle,
    section[data-testid="stSidebar"] [data-testid="stSidebarNavLink"][aria-current="page"] svg rect {
        color: #EF4444 !important;
        fill: #EF4444 !important;
    }
    .dashboard-header .user-email {
        font-size: 0.8rem;
        opacity: 0.6;
        margin-top: 0.2rem;
    }

    /* KPIカード */
    .kpi-card {
        border: 1px solid rgba(14, 165, 233, 0.3);
        border-radius: 8px;
        padding: 1rem 1.2rem;
        background: linear-gradient(135deg, rgba(14, 165, 233, 0.08) 0%, rgba(14, 165, 233, 0.02) 100%);
        margin-bottom: 0.5rem;
    }
    .kpi-card .kpi-label {
        font-size: 0.75rem;
        font-weight: 500;
        text-transform: uppercase;
        letter-spacing: 0.08em;
        opacity: 0.6;
        margin-bottom: 0.3rem;
    }
    .kpi-card .kpi-value {
        font-size: 1.5rem;
        font-weight: 700;
        color: #0EA5E9;
        line-height: 1.2;
    }

    /* サイドバー */
    section[data-testid="stSidebar"] {
        width: 280px !important;
    }
    section[data-testid="stSidebar"] .stSelectbox label,
    section[data-testid="stSidebar"] .stTextInput label {
        font-size: 0.8rem;
        font-weight: 600;
        letter-spacing: 0.03em;
    }

    /* サイドバー内コンポーネントの余白を統一 */
    section[data-testid="stSidebar"] .stSelectbox,
    section[data-testid="stSidebar"] .stTextInput,
    section[data-testid="stSidebar"] .stMultiSelect {
        margin-bottom: 0.5rem !important;
        margin-top: 0 !important;
    }

    /* メンバーリストのチェックボックス：フォント小さめ・行間を詰める */
    section[data-testid="stSidebar"] .stCheckbox {
        margin-bottom: 0 !important;
        margin-top: 0 !important;
    }
    section[data-testid="stSidebar"] .stCheckbox label,
    section[data-testid="stSidebar"] .stCheckbox label p {
        font-size: 0.78rem !important;
        line-height: 1.2 !important;
    }

    .sidebar-section-title {
        font-size: 0.8rem;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 0.1em;
        opacity: 0.5;
        margin: 0 0 0.1rem 0;
        padding-top: 0;
    }

    /* タブ */
    .stTabs [data-baseweb="tab-list"] {
        gap: 0;
    }
    .stTabs [data-baseweb="tab"] {
        padding: 0.6rem 1.5rem;
        font-weight: 600;
        font-size: 0.85rem;
    }

    /* データフレーム */
    .stDataFrame {
        border-radius: 6px;
        overflow: hidden;
    }

    /* Altairチャートのツールバーを非表示（テーブル切り替えで戻れなくなるため） */
    [data-testid="element-container"]:has([data-testid="stVegaLiteChart"]) [data-testid="stElementToolbar"] {
        display: none !important;
    }

    /* 件数バッジ */
    .count-badge {
        display: inline-block;
        background: rgba(14, 165, 233, 0.15);
        color: #0EA5E9;
        font-weight: 700;
        font-size: 0.85rem;
        padding: 0.3rem 0.8rem;
        border-radius: 20px;
        margin-bottom: 0.5rem;
    }

    /* 選択カウント */
    .member-count {
        font-size: 0.75rem;
        opacity: 0.5;
        margin-top: 0.2rem;
    }

</style>
"""


def apply_custom_css():
    st.markdown(CUSTOM_CSS, unsafe_allow_html=True)
