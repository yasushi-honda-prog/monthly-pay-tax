"""ヘルプ・アーキテクチャ・運用ドキュメント・ユーザー管理など
「説明 / リファレンス系」ページで共通利用するスタイル & ヘルパー。

トンマナを揃えるため、ヒーロー・セクションヘッダー・カード・ロールバッジ・
ティップス・用語集ピル・ステータスチップ等の CSS をまとめて定義する。
"""

from __future__ import annotations

from typing import Literal

import streamlit as st

# render_hero / render_section_header の color パラメータ
# CSS で定義された値のみ受け付ける（未定義の値を渡すと既定値 (青) で描画される）
HeroColor = Literal["blue", "green", "purple", "amber"]
SectionColor = Literal["blue", "green", "purple", "amber", "red"]


# ============================================================
# 共通 CSS
# ============================================================
# - .doc-hero            : 各ページ冒頭のヒーロー（既定は青系グラデーション）
# - .doc-hero.green      : 業務系ページ用（運用ドキュメント）
# - .doc-hero.purple     : 管理系ページ用（ユーザー管理）
# - .doc-hero.amber      : amber バリアント（render_hero(color="amber") 対応）
#                          ※ render_hero / .doc-hero 側に .doc-hero.red は未定義。
#                            セクションヘッダ (.sh-icon) のみ red を許容
# - .sh / .sh-icon       : セクションヘッダー（アイコン + タイトル、色は blue/green/purple/amber/red）
# - .pg / .pc            : ページカードグリッド
# - .role-cards / .rc    : ロール説明カード
# - .badge               : ロール色付きバッジ
# - .tip / .tip.info / .tip.warn : ティップス / 情報 / 警告ボックス
# - .gg / .gi            : 用語集グリッド
# - .ct                  : カラム説明テーブル
# - .status-pill         : 運用ドキュメントの status バッジ
# - .tag-pill            : tags ピル

DOC_CSS = """
<style>
@keyframes docFadeInUp {
    from { opacity: 0; transform: translateY(20px); }
    to   { opacity: 1; transform: translateY(0); }
}
@keyframes docFadeIn {
    from { opacity: 0; }
    to   { opacity: 1; }
}
@keyframes docSlideInLeft {
    from { opacity: 0; transform: translateX(-14px); }
    to   { opacity: 1; transform: translateX(0); }
}

/* ============ ヒーロー ============ */
.doc-hero {
    background: linear-gradient(135deg, #0EA5E9 0%, #0284C7 50%, #0369A1 100%);
    border-radius: 16px;
    padding: 2.3rem 2rem;
    margin-bottom: 1.8rem;
    animation: docFadeInUp 0.55s ease-out;
    position: relative;
    overflow: hidden;
}
.doc-hero.green {
    background: linear-gradient(135deg, #10B981 0%, #059669 50%, #047857 100%);
}
.doc-hero.purple {
    background: linear-gradient(135deg, #8B5CF6 0%, #7C3AED 50%, #6D28D9 100%);
}
.doc-hero.amber {
    background: linear-gradient(135deg, #F59E0B 0%, #D97706 50%, #B45309 100%);
}
.doc-hero::before {
    content: '';
    position: absolute;
    top: -60%;
    right: -15%;
    width: 320px;
    height: 320px;
    background: radial-gradient(circle, rgba(255,255,255,0.1) 0%, transparent 70%);
    border-radius: 50%;
    pointer-events: none;
}
.doc-hero::after {
    content: '';
    position: absolute;
    bottom: -40%;
    left: 10%;
    width: 200px;
    height: 200px;
    background: radial-gradient(circle, rgba(255,255,255,0.06) 0%, transparent 70%);
    border-radius: 50%;
    pointer-events: none;
}
.doc-hero h1 {
    color: white;
    font-size: 1.7rem;
    font-weight: 800;
    margin: 0 0 0.45rem 0;
    letter-spacing: 0.02em;
    position: relative;
}
.doc-hero p {
    color: rgba(255,255,255,0.9);
    font-size: 0.95rem;
    margin: 0;
    line-height: 1.7;
    position: relative;
}

/* ============ セクションヘッダー ============ */
.sh {
    display: flex;
    align-items: center;
    gap: 0.7rem;
    margin: 2.2rem 0 1rem 0;
    padding-bottom: 0.55rem;
    border-bottom: 2px solid rgba(14,165,233,0.15);
    animation: docSlideInLeft 0.45s ease-out;
}
.sh-icon {
    font-size: 1.25rem;
    width: 40px;
    height: 40px;
    display: flex;
    align-items: center;
    justify-content: center;
    border-radius: 11px;
    flex-shrink: 0;
}
.sh-icon.blue   { background: rgba(14,165,233,0.12); }
.sh-icon.green  { background: rgba(16,185,129,0.12); }
.sh-icon.purple { background: rgba(139,92,246,0.12); }
.sh-icon.amber  { background: rgba(245,158,11,0.12); }
.sh-icon.red    { background: rgba(239,68,68,0.12); }
.sh h2 {
    font-size: 1.2rem;
    font-weight: 800;
    margin: 0;
    letter-spacing: 0.01em;
}

/* ============ クイックスタート 3 ステップ ============ */
.steps {
    display: flex;
    gap: 1rem;
    margin: 1.1rem 0 0.5rem 0;
}
.steps > div { animation: docFadeInUp 0.5s ease-out both; }
.steps > div:nth-child(1) { animation-delay: 0.08s; }
.steps > div:nth-child(2) { animation-delay: 0.18s; }
.steps > div:nth-child(3) { animation-delay: 0.28s; }
.step {
    flex: 1;
    border: 1px solid rgba(14,165,233,0.12);
    border-radius: 14px;
    padding: 1.3rem 1.15rem;
    background: linear-gradient(170deg, rgba(14,165,233,0.06) 0%, transparent 60%);
    transition: transform 0.2s ease, box-shadow 0.2s ease;
}
.step.green {
    border-color: rgba(16,185,129,0.15);
    background: linear-gradient(170deg, rgba(16,185,129,0.06) 0%, transparent 60%);
}
.step.purple {
    border-color: rgba(139,92,246,0.15);
    background: linear-gradient(170deg, rgba(139,92,246,0.06) 0%, transparent 60%);
}
.step:hover {
    transform: translateY(-3px);
    box-shadow: 0 9px 26px rgba(14,165,233,0.1);
}
.step-num {
    width: 32px; height: 32px;
    background: linear-gradient(135deg, #0EA5E9, #0284C7);
    color: white;
    font-weight: 800;
    font-size: 0.92rem;
    border-radius: 50%;
    display: flex;
    align-items: center;
    justify-content: center;
    margin-bottom: 0.85rem;
    box-shadow: 0 3px 9px rgba(14,165,233,0.25);
}
.step.green  .step-num { background: linear-gradient(135deg, #10B981, #059669); }
.step.purple .step-num { background: linear-gradient(135deg, #8B5CF6, #7C3AED); }
.step h3 {
    font-size: 0.93rem;
    font-weight: 700;
    margin: 0 0 0.3rem 0;
}
.step p {
    font-size: 0.81rem;
    opacity: 0.72;
    margin: 0;
    line-height: 1.55;
}

/* ============ ページカードグリッド ============ */
.pg {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 0.85rem;
    margin: 1.1rem 0 0.5rem 0;
}
.pg > div { animation: docFadeInUp 0.45s ease-out both; }
.pg > div:nth-child(1) { animation-delay: 0.06s; }
.pg > div:nth-child(2) { animation-delay: 0.12s; }
.pg > div:nth-child(3) { animation-delay: 0.18s; }
.pg > div:nth-child(4) { animation-delay: 0.24s; }
.pg > div:nth-child(5) { animation-delay: 0.30s; }
.pg > div:nth-child(6) { animation-delay: 0.36s; }
.pg > div:nth-child(7) { animation-delay: 0.42s; }
.pg > div:nth-child(8) { animation-delay: 0.48s; }
.pg > div:nth-child(9) { animation-delay: 0.54s; }
.pg > div:nth-child(10){ animation-delay: 0.60s; }
.pc {
    border-radius: 13px;
    padding: 1.15rem;
    transition: transform 0.2s ease, box-shadow 0.2s ease;
    border: 1px solid transparent;
}
.pc:hover {
    transform: translateY(-3px);
    box-shadow: 0 8px 22px rgba(0,0,0,0.12);
}
.pc.b  { border-left: 3px solid #0EA5E9; background: linear-gradient(150deg, rgba(14,165,233,0.07) 0%, rgba(14,165,233,0.01) 100%); }
.pc.g  { border-left: 3px solid #10B981; background: linear-gradient(150deg, rgba(16,185,129,0.07) 0%, rgba(16,185,129,0.01) 100%); }
.pc.pr { border-left: 3px solid #8B5CF6; background: linear-gradient(150deg, rgba(139,92,246,0.07) 0%, rgba(139,92,246,0.01) 100%); }
.pc.am { border-left: 3px solid #F59E0B; background: linear-gradient(150deg, rgba(245,158,11,0.07) 0%, rgba(245,158,11,0.01) 100%); }
.pc-icon { font-size: 1.35rem; margin-bottom: 0.45rem; }
.pc h3 { font-size: 0.92rem; font-weight: 700; margin: 0 0 0.3rem 0; }
.pc p  { font-size: 0.78rem; opacity: 0.68; margin: 0; line-height: 1.5; }

/* ============ ロール色付きバッジ（共通） ============ */
.badge {
    display: inline-block;
    font-size: 0.62rem;
    font-weight: 700;
    padding: 0.18rem 0.6rem;
    border-radius: 10px;
    margin-top: 0.55rem;
    letter-spacing: 0.02em;
}
.badge.ba  { background: rgba(14,165,233,0.12);  color: #0EA5E9; }  /* 全ロール (blue) */
.badge.bc  { background: rgba(16,185,129,0.12);  color: #10B981; }  /* checker (green) */
.badge.bp  { background: rgba(139,92,246,0.12);  color: #8B5CF6; }  /* admin (purple) */
.badge.bv  { background: rgba(156,163,175,0.18); color: #9CA3AF; }  /* viewer (gray) */
.badge.bu  { background: rgba(14,165,233,0.12);  color: #0EA5E9; }  /* user (blue) */

/* ============ ロール説明カード（user_management 用） ============ */
.role-cards {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 0.85rem;
    margin: 1rem 0 0.5rem 0;
}
.role-cards > div { animation: docFadeInUp 0.45s ease-out both; }
.role-cards > div:nth-child(1) { animation-delay: 0.06s; }
.role-cards > div:nth-child(2) { animation-delay: 0.14s; }
.role-cards > div:nth-child(3) { animation-delay: 0.22s; }
.role-cards > div:nth-child(4) { animation-delay: 0.30s; }
.rc {
    border-radius: 12px;
    padding: 1.1rem 1.15rem 1.2rem 1.15rem;
    border: 1px solid rgba(255,255,255,0.06);
    background: rgba(255,255,255,0.015);
    transition: transform 0.2s ease, box-shadow 0.2s ease;
    border-top: 3px solid transparent;
}
.rc:hover {
    transform: translateY(-2px);
    box-shadow: 0 8px 22px rgba(0,0,0,0.12);
}
.rc.user    { border-top-color: #0EA5E9; }
.rc.viewer  { border-top-color: #9CA3AF; }
.rc.checker { border-top-color: #10B981; }
.rc.admin   { border-top-color: #8B5CF6; }
.rc-head {
    display: flex;
    align-items: center;
    gap: 0.45rem;
    margin-bottom: 0.55rem;
}
.rc-icon {
    font-size: 1.05rem;
    width: 28px; height: 28px;
    display: flex; align-items: center; justify-content: center;
    border-radius: 8px;
}
.rc.user    .rc-icon { background: rgba(14,165,233,0.14);  color: #0EA5E9; }
.rc.viewer  .rc-icon { background: rgba(156,163,175,0.20); color: #9CA3AF; }
.rc.checker .rc-icon { background: rgba(16,185,129,0.14);  color: #10B981; }
.rc.admin   .rc-icon { background: rgba(139,92,246,0.14);  color: #8B5CF6; }
.rc-title  { font-weight: 800; font-size: 0.95rem; letter-spacing: 0.01em; }
.rc-sub    { font-size: 0.74rem; opacity: 0.55; margin-bottom: 0.65rem; line-height: 1.5; }
.rc ul     { margin: 0; padding-left: 1.05rem; font-size: 0.78rem; line-height: 1.65; opacity: 0.82; }
.rc ul li  { margin-bottom: 0.12rem; }
.rc ul li.muted { opacity: 0.4; text-decoration: line-through; }

/* ============ フィルターガイド ============ */
.filter-cards {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 0.85rem;
    margin: 1rem 0;
    animation: docFadeInUp 0.45s ease-out 0.1s both;
}
.fc {
    border: 1px solid rgba(14,165,233,0.1);
    border-radius: 12px;
    padding: 1.05rem;
    background: rgba(14,165,233,0.03);
}
.fc h4 {
    font-size: 0.85rem;
    font-weight: 700;
    margin: 0 0 0.5rem 0;
    color: #0EA5E9;
}
.fc ul {
    margin: 0;
    padding-left: 1.1rem;
    font-size: 0.8rem;
    line-height: 1.7;
    opacity: 0.78;
}

/* ============ チェック管理 ステータスフロー ============ */
.cf {
    display: flex;
    align-items: center;
    gap: 0.55rem;
    margin: 1.15rem 0;
    padding: 1.05rem 1.25rem;
    background: linear-gradient(135deg, rgba(16,185,129,0.06) 0%, rgba(16,185,129,0.01) 100%);
    border-radius: 14px;
    border: 1px solid rgba(16,185,129,0.15);
    animation: docFadeInUp 0.45s ease-out 0.12s both;
    flex-wrap: wrap;
}
.fs {
    display: flex;
    align-items: center;
    gap: 0.32rem;
    padding: 0.42rem 0.8rem;
    border-radius: 9px;
    font-size: 0.8rem;
    font-weight: 600;
    white-space: nowrap;
}
.fs.u  { background: rgba(156,163,175,0.13); }
.fs.c  { background: rgba(59,130,246,0.13);  color: #60A5FA; }
.fs.d  { background: rgba(16,185,129,0.13);  color: #34D399; }
.fs.r  { background: rgba(239,68,68,0.13);   color: #F87171; }
.fa    { font-size: 1.05rem; opacity: 0.35; }

/* ============ カラムテーブル ============ */
.ct {
    width: 100%;
    border-collapse: separate;
    border-spacing: 0;
    margin: 1.15rem 0;
    animation: docFadeIn 0.45s ease-out 0.08s both;
    border-radius: 12px;
    overflow: hidden;
}
.ct th {
    background: rgba(14,165,233,0.1);
    padding: 0.7rem 1rem;
    font-size: 0.76rem;
    font-weight: 700;
    text-align: left;
    letter-spacing: 0.06em;
    text-transform: uppercase;
}
.ct td {
    padding: 0.6rem 1rem;
    font-size: 0.82rem;
    border-bottom: 1px solid rgba(255,255,255,0.04);
    transition: background 0.15s;
}
.ct tr:last-child td { border-bottom: none; }
.ct tr:hover td { background: rgba(14,165,233,0.04); }
.ct .ce { color: #34D399; font-weight: 700; }
.ct .cr { opacity: 0.5; font-size: 0.78rem; }

/* ============ ティップス / 警告 ============ */
.tip {
    background: linear-gradient(135deg, rgba(245,158,11,0.07) 0%, rgba(245,158,11,0.01) 100%);
    border: 1px solid rgba(245,158,11,0.18);
    border-radius: 12px;
    padding: 1.05rem 1.25rem;
    margin: 1.15rem 0;
    animation: docFadeIn 0.45s ease-out 0.18s both;
}
.tip.info {
    background: linear-gradient(135deg, rgba(14,165,233,0.07) 0%, rgba(14,165,233,0.01) 100%);
    border-color: rgba(14,165,233,0.2);
}
.tip.warn {
    background: linear-gradient(135deg, rgba(239,68,68,0.07) 0%, rgba(239,68,68,0.01) 100%);
    border-color: rgba(239,68,68,0.22);
}
.tip-t {
    font-weight: 800;
    font-size: 0.88rem;
    color: #FBBF24;
    margin-bottom: 0.38rem;
}
.tip.info .tip-t { color: #38BDF8; }
.tip.warn .tip-t { color: #F87171; }
.tip-c {
    font-size: 0.83rem;
    opacity: 0.78;
    line-height: 1.75;
}

/* ============ 用語集グリッド ============ */
.gg {
    display: grid;
    grid-template-columns: repeat(2, 1fr);
    gap: 0.65rem;
    margin: 0.95rem 0;
}
.gg > div { animation: docFadeIn 0.35s ease-out both; }
.gg > div:nth-child(odd)  { animation-delay: 0.04s; }
.gg > div:nth-child(even) { animation-delay: 0.1s; }
.gi {
    padding: 0.8rem 1rem;
    border-radius: 10px;
    border: 1px solid rgba(255,255,255,0.05);
    background: rgba(255,255,255,0.015);
    transition: background 0.18s, border-color 0.18s;
}
.gi:hover {
    background: rgba(14,165,233,0.04);
    border-color: rgba(14,165,233,0.15);
}
.gi-t {
    font-weight: 700;
    font-size: 0.83rem;
    color: #38BDF8;
    margin-bottom: 0.18rem;
}
.gi-d {
    font-size: 0.78rem;
    opacity: 0.68;
    line-height: 1.5;
}

/* ============ ドキュメント一覧（operations_docs） ============ */
.doc-meta {
    display: inline-flex;
    align-items: center;
    gap: 0.4rem;
    margin-right: 0.45rem;
    font-size: 0.75rem;
    opacity: 0.75;
}
.status-pill {
    display: inline-block;
    font-size: 0.7rem;
    font-weight: 700;
    padding: 0.15rem 0.55rem;
    border-radius: 9px;
    letter-spacing: 0.02em;
}
.status-pill.active   { background: rgba(16,185,129,0.14); color: #34D399; }
.status-pill.draft    { background: rgba(245,158,11,0.14); color: #FBBF24; }
.status-pill.archived { background: rgba(156,163,175,0.18); color: #9CA3AF; }
.tag-pill {
    display: inline-block;
    font-size: 0.7rem;
    padding: 0.15rem 0.55rem;
    margin-right: 0.25rem;
    margin-bottom: 0.18rem;
    border-radius: 9px;
    background: rgba(14,165,233,0.1);
    color: #38BDF8;
    letter-spacing: 0.02em;
}
.doc-toc {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
    gap: 0.7rem;
    margin: 1rem 0 1.4rem 0;
}
.doc-toc-item {
    padding: 0.85rem 1rem;
    border-radius: 11px;
    border: 1px solid rgba(255,255,255,0.05);
    background: rgba(255,255,255,0.02);
    transition: border-color 0.15s, background 0.15s;
}
.doc-toc-item.selected {
    border-color: rgba(14,165,233,0.35);
    background: rgba(14,165,233,0.06);
}
.doc-toc-title {
    font-weight: 700;
    font-size: 0.88rem;
    margin-bottom: 0.25rem;
}
.doc-toc-meta {
    font-size: 0.72rem;
    opacity: 0.6;
}

/* ============ FAQ ============ */
.faq-intro {
    font-size: 0.82rem;
    opacity: 0.55;
    margin-bottom: 0.7rem;
    font-style: italic;
    animation: docFadeIn 0.35s ease-out;
}

/* ============ レスポンシブ ============ */
@media (max-width: 800px) {
    .steps, .filter-cards { flex-direction: column; }
    .pg { grid-template-columns: 1fr; }
    .gg { grid-template-columns: 1fr; }
    .filter-cards { grid-template-columns: 1fr; }
    .role-cards { grid-template-columns: 1fr 1fr; }
}
@media (max-width: 520px) {
    .role-cards { grid-template-columns: 1fr; }
}
</style>
"""


def apply_doc_styles() -> None:
    """共通ドキュメント用 CSS を適用する。各ページの先頭で呼び出す。"""
    st.markdown(DOC_CSS, unsafe_allow_html=True)


# ============================================================
# パーツヘルパー
# ============================================================

def render_hero(title: str, description: str, color: HeroColor = "blue") -> None:
    """ページ冒頭のヒーローセクションを描画する。

    Parameters
    ----------
    title : str
        ヒーロー見出し。絵文字を含めて良い。**HTML エスケープしないため、
        信頼できる文字列のみ渡すこと**（ユーザー入力を渡す場合は呼び出し側で
        ``html.escape()`` する）。
    description : str
        補足説明。``<br>`` 等の HTML を含めて良い。``title`` と同じく
        **HTML エスケープしない**。
    color : HeroColor
        "blue" (default) / "green" / "purple" / "amber"。
        これ以外の値（例: "red"）を渡すと CSS に対応クラスが無いため、
        ベース色 (青) で描画される（silent fallback）。
    """
    cls = "doc-hero"
    if color and color != "blue":
        cls += f" {color}"
    st.markdown(
        f"""
<div class="{cls}">
    <h1>{title}</h1>
    <p>{description}</p>
</div>
""",
        unsafe_allow_html=True,
    )


def render_section_header(
    title: str, icon: str = "📄", color: SectionColor = "blue"
) -> None:
    """セクションヘッダー（アイコン + タイトル）を描画する。

    Parameters
    ----------
    title : str
        セクション見出し。**HTML エスケープしないため、信頼できる文字列のみ渡すこと**。
    icon : str
        アイコン絵文字。
    color : SectionColor
        "blue" / "green" / "purple" / "amber" / "red"。
        対応する ``.sh-icon.<color>`` クラスが CSS に必要。
    """
    st.markdown(
        f"""
<div class="sh">
    <div class="sh-icon {color}">{icon}</div>
    <h2>{title}</h2>
</div>
""",
        unsafe_allow_html=True,
    )


# ============================================================
# ロール権限定義（user_management / help / architecture で共有）
# ============================================================
# 実コードと一致させる:
#   user     : ダッシュボード / 各種説明ページの閲覧（一般メンバー想定）
#   viewer   : 同上（user と同等の閲覧専用扱い、historical 互換ロール）
#   checker  : 上記 + 業務チェック管理 + WAM立替金確認
#   admin    : 全機能（ユーザー管理 / 管理設定 / GAS管理 / (仮)報告入力）
#
# require_user()    : user / viewer / checker / admin を許可 (dashboard/lib/auth.py)
# require_checker() : checker / admin を許可 (dashboard/lib/auth.py)
# require_admin()   : admin のみを許可 (dashboard/lib/auth.py)
#
# admin の cannot は意図的に空（全機能アクセス可能のため）

ROLE_DEFINITIONS = [
    {
        "key": "user",
        "label": "user",
        "title": "user",
        "subtitle": "一般メンバー",
        "icon": "👤",
        "can": [
            "ダッシュボード（6タブ）の閲覧",
            "アーキテクチャ / ヘルプ / 運用ドキュメントの閲覧",
        ],
        "cannot": [
            "業務チェック管理",
            "WAM立替金確認",
            "ユーザー管理 / 管理設定",
        ],
    },
    {
        "key": "viewer",
        "label": "viewer",
        "title": "viewer",
        "subtitle": "閲覧専用（user と同等の権限。歴史的互換ロール）",
        "icon": "👁️",
        "can": [
            "ダッシュボード（6タブ）の閲覧",
            "アーキテクチャ / ヘルプ / 運用ドキュメントの閲覧",
        ],
        "cannot": [
            "業務チェック管理",
            "WAM立替金確認",
            "ユーザー管理 / 管理設定",
        ],
    },
    {
        "key": "checker",
        "label": "checker",
        "title": "checker",
        "subtitle": "チェック担当（業務チェック・立替金確認）",
        "icon": "✅",
        "can": [
            "user の全権限",
            "業務チェック管理表（ステータス更新 / メモ）",
            "WAM立替金確認 6タブ（CSV / PDF 出力）",
        ],
        "cannot": [
            "ユーザー管理",
            "管理設定 / GAS管理 / 報告入力",
        ],
    },
    {
        "key": "admin",
        "label": "admin",
        "title": "admin",
        "subtitle": "管理者（全機能 + ユーザー管理）",
        "icon": "🛡️",
        "can": [
            "checker の全権限",
            "ユーザー管理（追加 / 削除 / ロール変更 / グループ同期）",
            "管理設定（キャッシュ / 手動同期 / BQ情報）",
            "GAS管理 / 報告入力（プロトタイプ）",
        ],
        "cannot": [],
    },
]


def render_role_cards() -> None:
    """4 ロールの権限説明カードを描画する。

    user_management.py / help.py 双方で使用。
    """
    cards_html = ['<div class="role-cards">']
    for r in ROLE_DEFINITIONS:
        can_items = "".join(f"<li>{item}</li>" for item in r["can"])
        cannot_items = "".join(f'<li class="muted">{item}</li>' for item in r["cannot"])
        items = can_items + cannot_items
        cards_html.append(
            f"""
<div class="rc {r['key']}">
    <div class="rc-head">
        <div class="rc-icon">{r['icon']}</div>
        <div class="rc-title">{r['title']}</div>
    </div>
    <div class="rc-sub">{r['subtitle']}</div>
    <ul>{items}</ul>
</div>
"""
        )
    cards_html.append("</div>")
    st.markdown("".join(cards_html), unsafe_allow_html=True)
