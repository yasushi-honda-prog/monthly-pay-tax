"""ヘルプ / マニュアル

全面リデザイン: カード型レイアウト、CSSアニメーション、
ステップガイド、業務チェック管理表ガイド追加。
"""

import streamlit as st

# --- ヘルプ専用CSS ---
HELP_CSS = """
<style>
@keyframes fadeInUp {
    from { opacity: 0; transform: translateY(24px); }
    to { opacity: 1; transform: translateY(0); }
}
@keyframes fadeIn {
    from { opacity: 0; }
    to { opacity: 1; }
}
@keyframes slideInLeft {
    from { opacity: 0; transform: translateX(-16px); }
    to { opacity: 1; transform: translateX(0); }
}

/* ヒーロー */
.help-hero {
    background: linear-gradient(135deg, #0EA5E9 0%, #0284C7 50%, #0369A1 100%);
    border-radius: 16px;
    padding: 2.5rem 2rem;
    margin-bottom: 2rem;
    animation: fadeInUp 0.6s ease-out;
    position: relative;
    overflow: hidden;
}
.help-hero::before {
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
.help-hero::after {
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
.help-hero h1 {
    color: white;
    font-size: 1.8rem;
    font-weight: 800;
    margin: 0 0 0.5rem 0;
    letter-spacing: 0.02em;
    position: relative;
}
.help-hero p {
    color: rgba(255,255,255,0.88);
    font-size: 1rem;
    margin: 0;
    line-height: 1.7;
    position: relative;
}

/* セクションヘッダー */
.sh {
    display: flex;
    align-items: center;
    gap: 0.7rem;
    margin: 2.5rem 0 1rem 0;
    padding-bottom: 0.6rem;
    border-bottom: 2px solid rgba(14,165,233,0.15);
    animation: slideInLeft 0.5s ease-out;
}
.sh-icon {
    font-size: 1.3rem;
    width: 42px;
    height: 42px;
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
.sh h2 {
    font-size: 1.25rem;
    font-weight: 800;
    margin: 0;
    letter-spacing: 0.01em;
}

/* クイックスタート */
.steps {
    display: flex;
    gap: 1rem;
    margin: 1.2rem 0 0.5rem 0;
}
.steps > div { animation: fadeInUp 0.55s ease-out both; }
.steps > div:nth-child(1) { animation-delay: 0.1s; }
.steps > div:nth-child(2) { animation-delay: 0.22s; }
.steps > div:nth-child(3) { animation-delay: 0.34s; }
.step {
    flex: 1;
    border: 1px solid rgba(14,165,233,0.12);
    border-radius: 14px;
    padding: 1.4rem 1.2rem;
    background: linear-gradient(170deg, rgba(14,165,233,0.06) 0%, transparent 60%);
    transition: transform 0.22s ease, box-shadow 0.22s ease;
}
.step:hover {
    transform: translateY(-4px);
    box-shadow: 0 10px 30px rgba(14,165,233,0.1);
}
.step-num {
    width: 34px; height: 34px;
    background: linear-gradient(135deg, #0EA5E9, #0284C7);
    color: white;
    font-weight: 800;
    font-size: 0.95rem;
    border-radius: 50%;
    display: flex;
    align-items: center;
    justify-content: center;
    margin-bottom: 0.9rem;
    box-shadow: 0 3px 10px rgba(14,165,233,0.25);
}
.step h3 {
    font-size: 0.95rem;
    font-weight: 700;
    margin: 0 0 0.35rem 0;
}
.step p {
    font-size: 0.82rem;
    opacity: 0.72;
    margin: 0;
    line-height: 1.55;
}

/* ページカード */
.pg {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 0.9rem;
    margin: 1.2rem 0 0.5rem 0;
}
.pg > div { animation: fadeInUp 0.5s ease-out both; }
.pg > div:nth-child(1) { animation-delay: 0.08s; }
.pg > div:nth-child(2) { animation-delay: 0.16s; }
.pg > div:nth-child(3) { animation-delay: 0.24s; }
.pg > div:nth-child(4) { animation-delay: 0.32s; }
.pg > div:nth-child(5) { animation-delay: 0.40s; }
.pg > div:nth-child(6) { animation-delay: 0.48s; }
.pc {
    border-radius: 13px;
    padding: 1.2rem;
    transition: transform 0.2s ease, box-shadow 0.2s ease;
    border: 1px solid transparent;
}
.pc:hover {
    transform: translateY(-3px);
    box-shadow: 0 8px 24px rgba(0,0,0,0.12);
}
.pc.b  { border-left: 3px solid #0EA5E9; background: linear-gradient(150deg, rgba(14,165,233,0.07) 0%, rgba(14,165,233,0.01) 100%); }
.pc.g  { border-left: 3px solid #10B981; background: linear-gradient(150deg, rgba(16,185,129,0.07) 0%, rgba(16,185,129,0.01) 100%); }
.pc.pr { border-left: 3px solid #8B5CF6; background: linear-gradient(150deg, rgba(139,92,246,0.07) 0%, rgba(139,92,246,0.01) 100%); }
.pc-icon { font-size: 1.4rem; margin-bottom: 0.5rem; }
.pc h3 { font-size: 0.92rem; font-weight: 700; margin: 0 0 0.3rem 0; }
.pc p  { font-size: 0.78rem; opacity: 0.68; margin: 0; line-height: 1.45; }
.badge {
    display: inline-block;
    font-size: 0.62rem;
    font-weight: 700;
    padding: 0.18rem 0.55rem;
    border-radius: 10px;
    margin-top: 0.6rem;
    letter-spacing: 0.02em;
}
.badge.ba { background: rgba(14,165,233,0.12); color: #0EA5E9; }
.badge.bc { background: rgba(16,185,129,0.12); color: #10B981; }
.badge.bp { background: rgba(139,92,246,0.12); color: #8B5CF6; }

/* フィルターガイド */
.filter-cards {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 0.9rem;
    margin: 1rem 0;
    animation: fadeInUp 0.5s ease-out 0.15s both;
}
.fc {
    border: 1px solid rgba(14,165,233,0.1);
    border-radius: 12px;
    padding: 1.1rem;
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

/* チェック管理 ステータスフロー */
.cf {
    display: flex;
    align-items: center;
    gap: 0.6rem;
    margin: 1.2rem 0;
    padding: 1.1rem 1.3rem;
    background: linear-gradient(135deg, rgba(16,185,129,0.06) 0%, rgba(16,185,129,0.01) 100%);
    border-radius: 14px;
    border: 1px solid rgba(16,185,129,0.15);
    animation: fadeInUp 0.5s ease-out 0.15s both;
    flex-wrap: wrap;
}
.fs {
    display: flex;
    align-items: center;
    gap: 0.35rem;
    padding: 0.45rem 0.85rem;
    border-radius: 9px;
    font-size: 0.82rem;
    font-weight: 600;
    white-space: nowrap;
}
.fs.u  { background: rgba(156,163,175,0.13); }
.fs.c  { background: rgba(59,130,246,0.13); color: #60A5FA; }
.fs.d  { background: rgba(16,185,129,0.13); color: #34D399; }
.fs.r  { background: rgba(239,68,68,0.13); color: #F87171; }
.fa    { font-size: 1.1rem; opacity: 0.35; }
.fa-br { font-size: 0.8rem; opacity: 0.3; transform: rotate(90deg); display: inline-block; margin: 0 -0.1rem; }

/* カラムテーブル */
.ct {
    width: 100%;
    border-collapse: separate;
    border-spacing: 0;
    margin: 1.2rem 0;
    animation: fadeIn 0.5s ease-out 0.1s both;
    border-radius: 12px;
    overflow: hidden;
}
.ct th {
    background: rgba(14,165,233,0.1);
    padding: 0.75rem 1rem;
    font-size: 0.78rem;
    font-weight: 700;
    text-align: left;
    letter-spacing: 0.06em;
    text-transform: uppercase;
}
.ct td {
    padding: 0.65rem 1rem;
    font-size: 0.83rem;
    border-bottom: 1px solid rgba(255,255,255,0.04);
    transition: background 0.15s;
}
.ct tr:last-child td { border-bottom: none; }
.ct tr:hover td { background: rgba(14,165,233,0.04); }
.ct .ce { color: #34D399; font-weight: 700; }
.ct .cr { opacity: 0.5; font-size: 0.78rem; }

/* ティップス */
.tip {
    background: linear-gradient(135deg, rgba(245,158,11,0.07) 0%, rgba(245,158,11,0.01) 100%);
    border: 1px solid rgba(245,158,11,0.18);
    border-radius: 12px;
    padding: 1.1rem 1.3rem;
    margin: 1.2rem 0;
    animation: fadeIn 0.5s ease-out 0.2s both;
}
.tip-t {
    font-weight: 800;
    font-size: 0.88rem;
    color: #FBBF24;
    margin-bottom: 0.4rem;
}
.tip-c {
    font-size: 0.83rem;
    opacity: 0.78;
    line-height: 1.75;
}

/* 用語集グリッド */
.gg {
    display: grid;
    grid-template-columns: repeat(2, 1fr);
    gap: 0.7rem;
    margin: 1rem 0;
}
.gg > div { animation: fadeIn 0.4s ease-out both; }
.gg > div:nth-child(odd)  { animation-delay: 0.05s; }
.gg > div:nth-child(even) { animation-delay: 0.12s; }
.gi {
    padding: 0.85rem 1rem;
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
    margin-bottom: 0.2rem;
}
.gi-d {
    font-size: 0.78rem;
    opacity: 0.68;
    line-height: 1.5;
}

/* FAQ */
.faq-intro {
    font-size: 0.82rem;
    opacity: 0.55;
    margin-bottom: 0.8rem;
    font-style: italic;
    animation: fadeIn 0.4s ease-out;
}

/* レスポンシブ */
@media (max-width: 800px) {
    .steps, .filter-cards { flex-direction: column; }
    .pg { grid-template-columns: 1fr; }
    .gg { grid-template-columns: 1fr; }
    .filter-cards { grid-template-columns: 1fr; }
}
</style>
"""

st.markdown(HELP_CSS, unsafe_allow_html=True)


# ============================================================
# ヒーロー
# ============================================================
st.markdown("""
<div class="help-hero">
    <h1>📘 ヘルプ &amp; マニュアル</h1>
    <p>
        タダカヨ月次報酬ダッシュボードの使い方ガイドです。<br>
        各機能の操作方法、用語の解説、よくある質問をまとめています。
    </p>
</div>
""", unsafe_allow_html=True)


# ============================================================
# クイックスタート
# ============================================================
st.markdown("""
<div class="sh">
    <div class="sh-icon blue">🚀</div>
    <h2>はじめに — 3ステップ</h2>
</div>
<div class="steps">
    <div class="step">
        <div class="step-num">1</div>
        <h3>ログイン</h3>
        <p>Googleアカウント（tadakayo.jpドメイン）でログイン。管理者に事前登録が必要です。</p>
    </div>
    <div class="step">
        <div class="step-num">2</div>
        <h3>期間を選択</h3>
        <p>左サイドバーで確認したい年度・月を選択します。デフォルトは最新の年月です。</p>
    </div>
    <div class="step">
        <div class="step-num">3</div>
        <h3>データを確認</h3>
        <p>ダッシュボードの各タブや業務チェックページでデータを確認・操作します。</p>
    </div>
</div>
""", unsafe_allow_html=True)


# ============================================================
# ページ一覧
# ============================================================
st.markdown("""
<div class="sh">
    <div class="sh-icon blue">📑</div>
    <h2>ページ一覧</h2>
</div>
<div class="pg">
    <div class="pc b">
        <div class="pc-icon">📊</div>
        <h3>ダッシュボード</h3>
        <p>月別報酬サマリー、スポンサー別業務委託費、業務報告一覧の3タブで全体を把握</p>
        <span class="badge ba">全ユーザー</span>
    </div>
    <div class="pc g">
        <div class="pc-icon">✅</div>
        <h3>業務チェック</h3>
        <p>メンバーの補助＆立替報告を確認し、ステータス・メモを管理</p>
        <span class="badge bc">checker / admin</span>
    </div>
    <div class="pc b">
        <div class="pc-icon">🏗️</div>
        <h3>アーキテクチャ</h3>
        <p>システム構成、データフロー、BQスキーマの技術ドキュメント</p>
        <span class="badge ba">全ユーザー</span>
    </div>
    <div class="pc b">
        <div class="pc-icon">❓</div>
        <h3>ヘルプ</h3>
        <p>このページ。操作ガイド・用語集・よくある質問</p>
        <span class="badge ba">全ユーザー</span>
    </div>
    <div class="pc pr">
        <div class="pc-icon">👥</div>
        <h3>ユーザー管理</h3>
        <p>アクセス権・ロール・表示名の管理</p>
        <span class="badge bp">admin のみ</span>
    </div>
    <div class="pc pr">
        <div class="pc-icon">⚙️</div>
        <h3>管理設定</h3>
        <p>キャッシュ制御・テーブル情報・統計</p>
        <span class="badge bp">admin のみ</span>
    </div>
</div>
""", unsafe_allow_html=True)


# ============================================================
# フィルターの使い方
# ============================================================
st.markdown("""
<div class="sh">
    <div class="sh-icon blue">🔍</div>
    <h2>ダッシュボード — フィルターの使い方</h2>
</div>
<div class="filter-cards">
    <div class="fc">
        <h4>📅 期間フィルター</h4>
        <ul>
            <li>「年度」で対象年を選択</li>
            <li>「月」で対象月を選択</li>
            <li>「全月」で年間表示</li>
            <li>デフォルト: 最新年月</li>
        </ul>
    </div>
    <div class="fc">
        <h4>👤 メンバーフィルター</h4>
        <ul>
            <li>テキストで名前を絞り込み</li>
            <li>チェックボックスで個別選択</li>
            <li>「全選択 / 全解除」で一括操作</li>
            <li>未選択 = 全メンバー表示</li>
        </ul>
    </div>
    <div class="fc">
        <h4>🏷️ タブ内フィルター</h4>
        <ul>
            <li>スポンサー別: スポンサー名</li>
            <li>業務報告一覧: 活動分類</li>
            <li>各タブ独立で動作</li>
        </ul>
    </div>
</div>
""", unsafe_allow_html=True)


# ============================================================
# 業務チェック管理表ガイド（NEW）
# ============================================================
st.markdown("""
<div class="sh">
    <div class="sh-icon green">✅</div>
    <h2>業務チェック管理表の使い方</h2>
</div>
""", unsafe_allow_html=True)

st.markdown(
    "メンバーの月次報告（補助＆立替）を確認し、チェックステータスを管理するページです。"
    "**checker** または **admin** ロールが必要です。"
)

# ステータスフロー
st.markdown("""
<div class="cf">
    <div class="fs u">⬜ 未確認</div>
    <span class="fa">→</span>
    <div class="fs c">🔵 確認中</div>
    <span class="fa">→</span>
    <div class="fs d">✅ 確認完了</div>
    <span style="opacity:0.25; margin: 0 0.2rem;">／</span>
    <div class="fs r">🔴 差戻し</div>
    <span class="fa">→</span>
    <div class="fs u">⬜ 未確認</div>
</div>
""", unsafe_allow_html=True)

# カラム一覧テーブル
st.markdown("""
<table class="ct">
<thead>
    <tr><th>カラム</th><th>内容</th><th>編集</th></tr>
</thead>
<tbody>
    <tr><td>名前</td><td>ニックネーム（空の場合は本名を表示）</td><td class="cr">読取専用</td></tr>
    <tr><td>URL</td><td>メンバーのスプレッドシートへのリンク（「開く」で遷移）</td><td class="cr">読取専用</td></tr>
    <tr><td>時間</td><td>当月の業務時間合計</td><td class="cr">読取専用</td></tr>
    <tr><td>報酬</td><td>当月の報酬額（¥表示）</td><td class="cr">読取専用</td></tr>
    <tr><td>DX補助</td><td>デジタル化推進補助金（メンバーがSSで手入力）</td><td class="cr">読取専用</td></tr>
    <tr><td>立替</td><td>個人立替経費（メンバーがSSで手入力）</td><td class="cr">読取専用</td></tr>
    <tr><td>総額</td><td>報酬 + DX補助 + 立替の合計</td><td class="cr">読取専用</td></tr>
    <tr><td>当月入力完了</td><td>メンバーが当月の入力完了を申告したか（○ = 完了）</td><td class="cr">読取専用</td></tr>
    <tr><td>DX領収書</td><td>DX補助用の領収書添付状況</td><td class="cr">読取専用</td></tr>
    <tr><td>立替領収書</td><td>個人立替用の領収書添付状況（立替シート利用者はシート添付欄）</td><td class="cr">読取専用</td></tr>
    <tr><td><strong>ステータス</strong></td><td>チェック進捗（ドロップダウンで選択）</td><td class="ce">✏️ 編集可</td></tr>
    <tr><td><strong>メモ</strong></td><td>チェック時の備考・コメント（最大1000文字）</td><td class="ce">✏️ 編集可</td></tr>
</tbody>
</table>
""", unsafe_allow_html=True)

# 操作ティップス
st.markdown("""
<div class="tip">
    <div class="tip-t">💡 操作のコツ</div>
    <div class="tip-c">
        ・「ステータス」セルをクリック → ドロップダウンから選択<br>
        ・「メモ」セルをダブルクリック → 直接テキスト入力<br>
        ・変更は自動検出され、即座にBigQueryへ保存されます<br>
        ・別のチェック者と同時編集した場合、競合エラーが表示されます（ページ再読み込みで解決）<br>
        ・「URL」列の「開く」をクリックすると、メンバーのスプレッドシートを直接確認できます<br>
        ・KPIカード下の進捗バーでチェック完了率を一目で把握できます<br>
        ・操作ログ（ページ下部）で過去のチェック履歴を確認できます
    </div>
</div>
""", unsafe_allow_html=True)


# ============================================================
# チェック業務の流れ
# ============================================================
st.markdown("""
<div class="sh">
    <div class="sh-icon green">📋</div>
    <h2>チェック業務の進め方</h2>
</div>
""", unsafe_allow_html=True)

st.markdown("""
<div class="steps">
    <div class="step" style="border-color: rgba(16,185,129,0.15); background: linear-gradient(170deg, rgba(16,185,129,0.06) 0%, transparent 60%);">
        <div class="step-num" style="background: linear-gradient(135deg, #10B981, #059669);">1</div>
        <h3>サイドバーで期間設定</h3>
        <p>チェック対象の年月を選択。ステータスフィルターで「未確認」に絞ると効率的です。</p>
    </div>
    <div class="step" style="border-color: rgba(16,185,129,0.15); background: linear-gradient(170deg, rgba(16,185,129,0.06) 0%, transparent 60%);">
        <div class="step-num" style="background: linear-gradient(135deg, #10B981, #059669);">2</div>
        <h3>各項目を確認</h3>
        <p>「当月入力完了」が○か、DX領収書・立替領収書の添付があるか、金額に不整合がないか確認。URLからSSを直接確認。</p>
    </div>
    <div class="step" style="border-color: rgba(16,185,129,0.15); background: linear-gradient(170deg, rgba(16,185,129,0.06) 0%, transparent 60%);">
        <div class="step-num" style="background: linear-gradient(135deg, #10B981, #059669);">3</div>
        <h3>ステータス更新</h3>
        <p>確認完了ならステータスを「✅ 確認完了」に。問題があれば「🔴 差戻し」にしてメモに理由を記載。</p>
    </div>
</div>
""", unsafe_allow_html=True)


# ============================================================
# データ用語集
# ============================================================
st.markdown("""
<div class="sh">
    <div class="sh-icon amber">📖</div>
    <h2>データ用語集</h2>
</div>
<div class="gg">
    <div class="gi"><div class="gi-t">業務報酬</div><div class="gi-d">時間報酬 + 距離報酬に役職手当率・資格手当を適用した金額</div></div>
    <div class="gi"><div class="gi-t">時間報酬</div><div class="gi-d">業務時間 × 単価で計算された報酬</div></div>
    <div class="gi"><div class="gi-t">距離報酬</div><div class="gi-d">自家用車使用時の移動距離に対する報酬</div></div>
    <div class="gi"><div class="gi-t">役職手当率</div><div class="gi-d">メンバーの役職に応じた報酬加算率（%）</div></div>
    <div class="gi"><div class="gi-t">資格手当</div><div class="gi-d">特定資格保有者への固定加算額</div></div>
    <div class="gi"><div class="gi-t">源泉徴収</div><div class="gi-d">源泉対象額 × 10.21% を控除（法人・寄付シートは免除）</div></div>
    <div class="gi"><div class="gi-t">DX補助</div><div class="gi-d">デジタル化推進のための補助金（メンバーがSSで手入力）</div></div>
    <div class="gi"><div class="gi-t">立替</div><div class="gi-d">メンバーが立て替えた経費の精算額（メンバーがSSで手入力）</div></div>
    <div class="gi"><div class="gi-t">総額</div><div class="gi-d">報酬 + DX補助 + 立替の合計金額</div></div>
    <div class="gi"><div class="gi-t">支払い</div><div class="gi-d">業務報酬 − 源泉徴収 + DX補助 + 立替</div></div>
    <div class="gi"><div class="gi-t">寄付支払い</div><div class="gi-d">寄付先シートに紐づくメンバーの報酬（別会計）</div></div>
    <div class="gi"><div class="gi-t">1立て</div><div class="gi-d">日給制の業務。全日稼働(6h) / 半日稼働(3h) の固定時間</div></div>
    <div class="gi"><div class="gi-t">総稼働時間</div><div class="gi-d">通常の業務時間 + 1立て固定時間の合算</div></div>
    <div class="gi"><div class="gi-t">当月入力完了</div><div class="gi-d">メンバーがSSで当月分の入力完了を申告した状態</div></div>
    <div class="gi"><div class="gi-t">DX領収書</div><div class="gi-d">DX補助用の領収書添付欄の記入状況</div></div>
    <div class="gi"><div class="gi-t">立替領収書</div><div class="gi-d">個人立替用の領収書添付欄（立替シート利用者はシート添付欄）</div></div>
</div>
""", unsafe_allow_html=True)


# ============================================================
# よくある質問
# ============================================================
st.markdown("""
<div class="sh">
    <div class="sh-icon blue">💬</div>
    <h2>よくある質問</h2>
</div>
<div class="faq-intro">クリックして回答を表示</div>
""", unsafe_allow_html=True)

with st.expander("データはいつ更新されますか？"):
    st.markdown("""
    毎朝 **6時（JST）** にCloud Schedulerが自動でバッチ処理を実行します。
    約190件のスプレッドシートを巡回するため、処理には約4分かかります。

    ダッシュボードのデータは **5分間キャッシュ** されるため、
    バッチ実行直後でも最大5分のラグがあります。
    """)

with st.expander("統計分析スプレッドシートと数値が異なります"):
    st.markdown("""
    統計分析スプレッドシートは **IMPORTRANGE経由のライブデータ** を使用していますが、
    BQは **毎朝6時のスナップショット** です。データの鮮度の違いにより差異が生じます。

    また、一部のカラム定義（例: 報酬列）はSSとBQで計算方法が異なる場合があります。
    """)

with st.expander("アクセス権限を追加してほしい"):
    st.markdown("""
    **admin（管理者）** に依頼してください。
    管理者は「ユーザー管理」ページからメールアドレスを登録できます。

    - **viewer**: ダッシュボード閲覧のみ
    - **checker**: ダッシュボード閲覧 + 業務チェック管理
    - **admin**: 全機能（ユーザー管理・管理設定を含む）

    対象は **tadakayo.jpドメイン** のGWSアカウントのみです。
    """)

with st.expander("データが表示されません"):
    st.markdown("""
    以下を順番に確認してください:

    1. サイドバーの **フィルター設定**（年度・月・メンバー選択）
    2. 該当期間に **データが存在するか**（バッチ実行前のデータは取得不可）
    3. ブラウザの **キャッシュをクリア**（Ctrl+Shift+R で強制リロード）
    4. それでも解決しない場合は **管理者にお問い合わせ** ください
    """)

with st.expander("業務チェックのステータスが保存されません"):
    st.markdown("""
    以下を確認してください:

    1. **ロール**: checker または admin ロールが必要です
    2. **競合**: 別のチェック者が同じメンバーを同時に更新した場合、競合エラーが発生します。
       ページを再読み込みしてから再度操作してください。
    3. **ネットワーク**: 通信エラーの場合はしばらく待ってから再試行してください
    """)

with st.expander("デプロイ後にページが正しく表示されません"):
    st.markdown("""
    デプロイ直後はセッションがリセットされるため、一時的にナビゲーションが崩れることがあります。

    **対処法**: ルートURL（ `https://pay-dashboard-....run.app/` ）にアクセスして、
    再度ログインしてください。ブックマークからのアクセスでも解消します。
    """)
