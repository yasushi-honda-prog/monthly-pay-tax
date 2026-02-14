"""共有CSS"""

import streamlit as st

CUSTOM_CSS = """
<style>
    /* ヘッダー */
    .dashboard-header {
        padding: 0.5rem 0 1rem 0;
        border-bottom: 2px solid #0EA5E9;
        margin-bottom: 1rem;
    }
    .dashboard-header h1 {
        font-size: 1.6rem;
        font-weight: 700;
        margin: 0;
        letter-spacing: 0.02em;
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
    .sidebar-section-title {
        font-size: 0.7rem;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 0.1em;
        opacity: 0.5;
        margin: 1rem 0 0.3rem 0;
        padding-top: 0.8rem;
        border-top: 1px solid rgba(255,255,255,0.1);
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
