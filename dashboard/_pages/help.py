"""ヘルプ / マニュアル

共通ドキュメント CSS (`lib/doc_styles.py`) を使い、
アーキテクチャ / 運用ドキュメント / ユーザー管理とトンマナを統一する。
"""

import streamlit as st

from lib.doc_styles import (
    apply_doc_styles,
    render_hero,
    render_section_header,
    render_role_cards,
)


# --- 共通トンマナ CSS ---
apply_doc_styles()


# ============================================================
# ヒーロー
# ============================================================
render_hero(
    "📘 ヘルプ &amp; マニュアル",
    "タダカヨ活動時間・報酬マネジメントダッシュボードの使い方ガイドです。<br>"
    "各機能の操作方法、用語の解説、よくある質問をまとめています。",
    color="blue",
)


# ============================================================
# クイックスタート
# ============================================================
render_section_header("はじめに — 3ステップ", icon="🚀", color="blue")

st.markdown("""
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
# ロール（権限）の種類
# ============================================================
render_section_header("ロール（権限）の種類", icon="🎭", color="purple")
st.markdown(
    "ダッシュボードは 4 つのロールでアクセス権を制御します。"
    "新規登録は最小権限の `user` から始め、必要に応じて昇格します。"
)
render_role_cards()
st.caption(
    "🔒 取り消し線は当該ロールが**利用できない**機能。"
    " 権限の追加・変更は **admin** に依頼してください。"
)


# ============================================================
# ページ一覧
# ============================================================
render_section_header("ページ一覧", icon="📑", color="blue")

st.markdown("""
<div class="pg">
    <div class="pc b">
        <div class="pc-icon">📊</div>
        <h3>ダッシュボード</h3>
        <p>月別報酬サマリー、スポンサー別業務委託費、業務報告一覧、WAM業務報告、グループ別、業務委託費分析の6タブで全体を把握</p>
        <span class="badge ba">全ユーザー</span>
    </div>
    <div class="pc g">
        <div class="pc-icon">✅</div>
        <h3>業務チェック</h3>
        <p>メンバーの補助&amp;立替報告を確認し、ステータス・メモを管理</p>
        <span class="badge bc">checker / admin</span>
    </div>
    <div class="pc g">
        <div class="pc-icon">💰</div>
        <h3>WAM立替金確認</h3>
        <p>立替金シートデータ・月別報酬の確認、振込CSV・支払明細書PDF・年間支払調書データの出力</p>
        <span class="badge bc">checker / admin</span>
    </div>
    <div class="pc b">
        <div class="pc-icon">🏗️</div>
        <h3>アーキテクチャ</h3>
        <p>システム構成、データフロー、BQスキーマ、認証フロー、セキュリティ設計の技術ドキュメント</p>
        <span class="badge ba">全ユーザー</span>
    </div>
    <div class="pc b">
        <div class="pc-icon">📔</div>
        <h3>運用ドキュメント</h3>
        <p>業務報告スプレッドシートの構造変更・運用判断記録・障害対応手順などを時系列で蓄積</p>
        <span class="badge ba">全ユーザー</span>
    </div>
    <div class="pc b">
        <div class="pc-icon">❓</div>
        <h3>ヘルプ</h3>
        <p>このページ。操作ガイド・ロール説明・用語集・FAQ</p>
        <span class="badge ba">全ユーザー</span>
    </div>
    <div class="pc pr">
        <div class="pc-icon">📝</div>
        <h3>(仮) 報告入力</h3>
        <p>業務報告（日次）・補助報告（月次）をダッシュボードから直接入力（プロトタイプ）</p>
        <span class="badge bp">admin のみ</span>
    </div>
    <div class="pc pr">
        <div class="pc-icon">💻</div>
        <h3>GAS管理</h3>
        <p>GASバインド済みスプレッドシートの実行・スクリプト管理</p>
        <span class="badge bp">admin のみ</span>
    </div>
    <div class="pc pr">
        <div class="pc-icon">👥</div>
        <h3>ユーザー管理</h3>
        <p>アクセス権・ロール・グループ同期・表示名の管理</p>
        <span class="badge bp">admin のみ</span>
    </div>
    <div class="pc pr">
        <div class="pc-icon">⚙️</div>
        <h3>管理設定</h3>
        <p>キャッシュ制御・BQテーブル情報・手動同期（メイン報告/立替金/タダメンM/グループ）・ユーザー統計</p>
        <span class="badge bp">admin のみ</span>
    </div>
</div>
""", unsafe_allow_html=True)


# ============================================================
# フィルターの使い方
# ============================================================
render_section_header("ダッシュボード — フィルターの使い方", icon="🔍", color="blue")

st.markdown("""
<div class="filter-cards">
    <div class="fc">
        <h4>📅 期間フィルター</h4>
        <ul>
            <li>「年度」で対象年を選択</li>
            <li>「月」で対象月を選択</li>
            <li>「全月」で年間表示</li>
            <li><strong>期間指定モード</strong>: 業務報告一覧・WAM業務報告は<br>「期間指定」で年跨ぎ範囲を絞り込み可能</li>
            <li>デフォルト: 最新年・全月</li>
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
            <li>業務報告一覧: 活動分類・業務分類</li>
            <li>WAM業務報告: 業務分類が「（WAM）」始まりの行のみ抽出</li>
            <li>グループ別: グループ名・業務分類</li>
            <li>業務委託費分析: 業務委託費全体/非営利活動</li>
            <li>各タブ独立で動作</li>
        </ul>
    </div>
</div>
""", unsafe_allow_html=True)


# ============================================================
# 業務報告一覧 / WAM業務報告 タブの詳細機能
# ============================================================
render_section_header("業務報告一覧 / WAM業務報告 タブの詳細機能", icon="📋", color="blue")

st.markdown(
    "ダッシュボードの「**業務報告一覧**」「**WAM業務報告**」タブには、"
    "大量の明細を効率よく絞り込み・確認するための専用フィルターが揃っています。"
    "WAM業務報告は業務分類が「（WAM）」始まりの行のみを対象に同じUIで操作できます。"
)

# 機能カード
st.markdown("""
<div class="filter-cards">
    <div class="fc">
        <h4>📅 期間指定モード</h4>
        <ul>
            <li>サイドバーの「期間モード」で「期間指定」を選択</li>
            <li>開始 年/月 ～ 終了 年/月 で範囲指定</li>
            <li><strong>年跨ぎ</strong>（例: 2025-11〜2026-06）に対応</li>
            <li>業務報告一覧・WAM業務報告タブで有効</li>
        </ul>
    </div>
    <div class="fc">
        <h4>🔗 依存型ドロップダウン</h4>
        <ul>
            <li>「活動分類」を選ぶと、その分類に紐づく「業務分類」「スポンサー」だけが選択肢に絞り込まれる</li>
            <li>選択肢が大量にあって迷う問題を解消</li>
        </ul>
    </div>
    <div class="fc">
        <h4>🏢 スポンサー絞り込み</h4>
        <ul>
            <li>multiselect で複数スポンサーを同時指定可能</li>
            <li>依存型ドロップダウンと連動</li>
        </ul>
    </div>
    <div class="fc">
        <h4>🔎 キーワード検索 + 対象カラム選択</h4>
        <ul>
            <li>テキスト入力欄でキーワード検索</li>
            <li>「検索対象カラム」を multiselect で選択（空 = 全カラム横断 / 選択あり = ピンポイント）</li>
            <li>横断検索とピンポイント検索を一つの UI で切替</li>
        </ul>
    </div>
    <div class="fc">
        <h4>📜 内容列の折り返し表示</h4>
        <ul>
            <li>長文の「内容」列を自動改行で表示（22文字目安）</li>
            <li>横スクロール不要で全文確認</li>
        </ul>
    </div>
    <div class="fc">
        <h4>👤 「報告者数 X / Y 名」KPI</h4>
        <ul>
            <li>絞り込みなし: 「<strong>198 / 198 名</strong>」（全在籍 / 分母）</li>
            <li>絞り込みあり: 「<strong>X / 選択数 名</strong>」</li>
            <li>分子 X = 現在の絞り込み結果に出てくる<strong>実際に報告した人</strong>の数</li>
        </ul>
    </div>
</div>
""", unsafe_allow_html=True)

# 報告者数の意味を補強
st.markdown("""
<div class="tip info">
    <div class="tip-t">💡 「報告者数 X / Y 名」の読み方</div>
    <div class="tip-c">
        旧表記「メンバー数 100」は「全在籍 198 名のうち 100 名」と「サイドバー選択 100 名のうち 100 名」を見分けられない問題がありました。<br>
        新表記では <strong>分母</strong> がフィルター条件に応じて自動切替されます:<br>
        ・サイドバーで全選択 → 分母 = 全在籍 198<br>
        ・サイドバーで一部選択 → 分母 = 選択した人数<br>
        分子は「期間 + フィルター適用後に1件以上報告した人」の実数なので、「報告していない人がどれだけ居るか」が直感的にわかります。
    </div>
</div>
""", unsafe_allow_html=True)

# リセット
st.markdown("""
<div class="tip">
    <div class="tip-t">🔄 リセットボタン</div>
    <div class="tip-c">
        タブ内の「リセット」ボタンで活動分類・業務分類・スポンサー・検索キーワード・検索対象カラムをまとめてクリアできます。
        サイドバーの期間・メンバー選択はそのまま残ります（別系統の絞り込みのため）。
    </div>
</div>
""", unsafe_allow_html=True)


# ============================================================
# 業務チェック管理表ガイド
# ============================================================
render_section_header("業務チェック管理表の使い方", icon="✅", color="green")

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
render_section_header("チェック業務の進め方", icon="📋", color="green")

st.markdown("""
<div class="steps">
    <div class="step green">
        <div class="step-num">1</div>
        <h3>サイドバーで期間設定</h3>
        <p>チェック対象の年月を選択。ステータスフィルターで「未確認」に絞ると効率的です。</p>
    </div>
    <div class="step green">
        <div class="step-num">2</div>
        <h3>各項目を確認</h3>
        <p>「当月入力完了」が○か、DX領収書・立替領収書の添付があるか、金額に不整合がないか確認。URLからSSを直接確認。</p>
    </div>
    <div class="step green">
        <div class="step-num">3</div>
        <h3>ステータス更新</h3>
        <p>確認完了ならステータスを「✅ 確認完了」に。問題があれば「🔴 差戻し」にしてメモに理由を記載。</p>
    </div>
</div>
""", unsafe_allow_html=True)


# ============================================================
# WAM立替金確認ガイド
# ============================================================
render_section_header("WAM立替金確認の使い方", icon="💰", color="purple")

st.markdown(
    "立替金シートのデータ確認、振込CSV出力、支払明細書PDF生成、年間支払調書データ出力を行うページです。"
    "**checker** または **admin** ロールが必要です。"
)

st.markdown("""
<div class="tip info">
    <div class="tip-t">📥 データの仕組み</div>
    <div class="tip-c">
        立替金データは、各メンバーのスプレッドシートから<strong>毎朝6時に自動収集</strong>されます。<br>
        収集された明細はBigQuery（reimbursement_items）に格納され、WAM対象PJ判定と結合して表示されます。
    </div>
</div>
""", unsafe_allow_html=True)

# 6タブ説明テーブル
st.markdown("""
<table class="ct">
<thead>
    <tr><th>タブ</th><th>内容</th><th>操作</th></tr>
</thead>
<tbody>
    <tr>
        <td><strong>PJ別サマリー</strong></td>
        <td>対象PJ別の立替金集計（件数・支払金額・仮払金額）</td>
        <td class="cr">閲覧のみ</td>
    </tr>
    <tr>
        <td><strong>メンバー別明細</strong></td>
        <td>メンバーごとの立替経費明細（日付・PJ・分類・金額・立替金シートURL）</td>
        <td class="ce">✏️ CSVダウンロード / URLクリックで原本シート表示</td>
    </tr>
    <tr>
        <td><strong>領収書添付状況</strong></td>
        <td>メンバー別の領収書添付率（KPI + 未添付数ソート）</td>
        <td class="cr">閲覧のみ</td>
    </tr>
    <tr>
        <td><strong>月別報酬・振込確認</strong></td>
        <td>月別の報酬集計（対象メンバー数・報酬・源泉・支払額）</td>
        <td class="ce">✏️ 報酬明細CSV / 振込CSV（GMOあおぞら形式）</td>
    </tr>
    <tr>
        <td><strong>支払明細書</strong></td>
        <td>メンバー別の支払明細書プレビュー（業務委託費 + 立替経費）</td>
        <td class="ce">✏️ PDF生成 / ZIP一括生成</td>
    </tr>
    <tr>
        <td><strong>年間支払調書データ</strong></td>
        <td>メンバー別の年間報酬・源泉徴収集計</td>
        <td class="ce">✏️ CSVダウンロード（BOM付UTF-8）</td>
    </tr>
</tbody>
</table>
""", unsafe_allow_html=True)

# WAM操作フロー
render_section_header("WAM立替金確認の進め方", icon="📋", color="purple")

st.markdown("""
<div class="steps">
    <div class="step purple">
        <div class="step-num">1</div>
        <h3>期間・PJを選択</h3>
        <p>サイドバーで年月を選択。対象PJフィルターやWAM対象チェックボックスで絞り込めます。</p>
    </div>
    <div class="step purple">
        <div class="step-num">2</div>
        <h3>明細・領収書を確認</h3>
        <p>PJ別サマリー・メンバー別明細で金額を確認。領収書添付状況で未添付のメンバーをチェック。</p>
    </div>
    <div class="step purple">
        <div class="step-num">3</div>
        <h3>CSV/PDF出力</h3>
        <p>振込CSVで銀行振込データを出力。支払明細書PDFを個別またはZIP一括で生成。年間支払調書CSVで税務用データを出力。</p>
    </div>
</div>
""", unsafe_allow_html=True)

# WAM操作ティップス
st.markdown("""
<div class="tip">
    <div class="tip-t">💡 操作のコツ</div>
    <div class="tip-c">
        ・振込CSVはGMOあおぞらネット銀行の総合振込フォーマット（Shift_JIS）です<br>
        ・口座情報はタダメンMマスタから自動取得されます（手入力不要）<br>
        ・支払明細書は「全メンバー」選択でZIP一括生成、個別選択で1枚ずつ生成できます<br>
        ・年間支払調書CSVはBOM付きUTF-8のため、Excelで直接開いても文字化けしません<br>
        ・個人情報（氏名・住所・口座）は画面に表示されず、CSV/PDFファイル出力のみに含まれます
    </div>
</div>
""", unsafe_allow_html=True)


# ============================================================
# 運用ドキュメントの使い方
# ============================================================
render_section_header("運用ドキュメントの使い方", icon="📔", color="blue")

st.markdown(
    "業務報告スプレッドシートの構造変更、運用判断記録、障害対応手順などの履歴を時系列で蓄積するページです。"
    "全ユーザーが閲覧可能。Mermaid 図も自動レンダリングされます。"
)

st.markdown("""
<div class="tip info">
    <div class="tip-t">📌 利用シーン</div>
    <div class="tip-c">
        ・スプレッドシートのカラム名が変わったとき、いつ・なぜ変わったかを確認<br>
        ・BigQuery snapshot からの復旧手順を確認<br>
        ・Chat 障害通知の設定・運用ガイドを参照<br>
        ・OAuth リダイレクトループ等の障害切り分け手順を参照
    </div>
</div>
""", unsafe_allow_html=True)


# ============================================================
# データ用語集
# ============================================================
render_section_header("データ用語集", icon="📖", color="amber")

st.markdown("""
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
    <div class="gi"><div class="gi-t">WAM</div><div class="gi-d">立替金管理の対象プロジェクト判定の仕組み。wam_target_projectsマスタで管理</div></div>
    <div class="gi"><div class="gi-t">対象PJ</div><div class="gi-d">立替金が紐づくプロジェクト名。WAM対象かどうかはマスタで判定</div></div>
    <div class="gi"><div class="gi-t">振込CSV</div><div class="gi-d">GMOあおぞらネット銀行の総合振込用データ（Shift_JIS形式）</div></div>
    <div class="gi"><div class="gi-t">支払明細書</div><div class="gi-d">メンバー別の業務委託費+立替経費の内訳をまとめたPDF帳票</div></div>
    <div class="gi"><div class="gi-t">年間支払調書</div><div class="gi-d">メンバー別の年間報酬・源泉徴収の集計データ（税務用CSV出力）</div></div>
    <div class="gi"><div class="gi-t">グループ自動同期</div><div class="gi-d">Googleグループのメンバー増減を毎朝6時のバッチで dashboard_users に反映する仕組み</div></div>
</div>
""", unsafe_allow_html=True)


# ============================================================
# よくある質問
# ============================================================
render_section_header("よくある質問", icon="💬", color="blue")

st.markdown('<div class="faq-intro">クリックして回答を表示</div>', unsafe_allow_html=True)

with st.expander("データはいつ更新されますか？"):
    st.markdown("""
    毎朝 **6時（JST）** にCloud Schedulerが自動でバッチ処理を実行します。
    約190件のスプレッドシートを巡回するため、処理には約4分かかります。

    ダッシュボードのデータは **1時間キャッシュ** されるため、最新データの反映にはキャッシュクリアが必要な場合があります。
    管理者は「管理設定」ページからキャッシュを手動クリアできます。
    管理設定からは **手動同期**（メイン報告 / 立替金 / タダメンM / グループ情報）も実行可能です。
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

    ロール別の権限はこのページ上部の「ロール（権限）の種類」セクションで詳しく確認できます。

    - **user** / **viewer**: ダッシュボード・運用ドキュメント・ヘルプの閲覧
    - **checker**: 上記 + 業務チェック管理 + WAM立替金確認（全6タブ）
    - **admin**: 全機能（ユーザー管理・管理設定・GAS管理・(仮)報告入力を含む）

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

with st.expander("WAM立替金確認にデータが表示されません"):
    st.markdown("""
    以下を確認してください:

    1. **ロール**: checker または admin ロールが必要です
    2. **期間**: サイドバーの年月選択が正しいか確認してください
    3. **立替金シート**: 対象メンバーのスプレッドシートに立替金シートが存在するか確認してください
    4. **収集タイミング**: データは毎朝6時に自動収集されます。当日入力分は翌朝の反映です
    """)

with st.expander("振込CSVの口座情報が空です"):
    st.markdown("""
    振込CSVの口座情報はタダメンMマスタ（member_master）から自動取得されます。

    口座が空の場合、管理表のタダメンMタブに該当メンバーの口座情報が未登録の可能性があります。
    管理表で口座情報を登録すれば、翌朝のバッチ処理後に反映されます（または管理設定の「タダメンMマスタ」手動同期で即時反映）。
    """)

with st.expander("デプロイ後にページが正しく表示されません"):
    st.markdown("""
    デプロイ直後はセッションがリセットされるため、一時的にナビゲーションが崩れることがあります。

    **対処法**: ルートURL（ `https://pay-dashboard-....run.app/` ）にアクセスして、
    再度ログインしてください。ブックマークからのアクセスでも解消します。

    OAuth リダイレクトループが発生した場合は、運用ドキュメント
    「OAuth リダイレクトループ 切り分け」を参照してください。
    """)

with st.expander("「報告者数 100」と「198 名」のどっちが正しい？"):
    st.markdown("""
    どちらも正しい数字ですが、**意味が違います**:

    - **報告者数 100**: 期間 + フィルター適用後に **1 件以上報告した人** の実数
    - **198 名**: 在籍メンバー（タダメンMマスタ）の総数。サイドバーで全選択した場合の分母

    新しい「報告者数 X / Y 名」表記は、**サイドバーで何人選んでいるか** に応じて分母が変わります:

    - サイドバーで全選択 → 「100 / 198 名」（全在籍 198 のうち報告者 100）
    - サイドバーで特定 50 名選択 → 「30 / 50 名」（選んだ 50 のうち報告者 30）

    つまり「**報告していない人が何人いるか**」が一目でわかる表記です。
    """)

with st.expander("年跨ぎで絞り込みたい（例: 2025-11〜2026-06）"):
    st.markdown("""
    業務報告一覧・WAM業務報告タブには「**期間指定モード**」があります:

    1. サイドバーの「期間モード」で **「期間指定」** を選択
    2. 開始 年/月 と 終了 年/月 を指定
    3. 年跨ぎ範囲（例: 2025-11〜2026-06）に対応

    他のタブ（月別報酬サマリーなど）は単月 / 全月モードのみのため、
    範囲指定したい場合は業務報告一覧 / WAM業務報告タブで確認してください。
    """)

with st.expander("業務報告一覧の検索は何を対象にしている？"):
    st.markdown("""
    「検索対象カラム」セレクターで切替可能です:

    - **空のまま**: 表示中の **全カラムを横断検索**（活動分類・業務分類・スポンサー・内容・名前など）
    - **カラム選択あり**: 選択したカラムのみで検索（複数選択 OR）

    例えば「内容」だけ選べば、活動分類やスポンサー名にヒットせず内容欄のみでの検索になります。
    """)

with st.expander("「内容」列が読みにくい / 長文が切れる"):
    st.markdown("""
    業務報告一覧の「内容」列は **22 文字目安で自動改行** されるようになっています（PR #179/#180）。

    - 横スクロール不要で全文確認可能
    - 1 行あたり高さが自動調整されるためテーブル全体は縦長になります

    短い行と長い行で行高が大きく異なる点はトレードオフですが、視認性を優先しています。
    """)

with st.expander("グループ自動同期 ON/OFF の挙動は？"):
    st.markdown("""
    ユーザー管理ページの「グループ自動同期 ON/OFF」セクションで設定します。

    - **ON**: 毎朝6時のバッチでグループメンバーの追加/削除を `dashboard_users` に自動反映
    - **OFF（凍結）**: 既存ユーザーは残ったまま、新規追加・削除を停止

    OFF 中はグループ側でメンバーが削除されても `dashboard_users` には反映されません。
    アクセスを完全に止めたい場合は「登録ユーザー一覧」から個別に削除してください。
    切替は次回バッチ（翌朝6時 JST）で反映されます。
    """)
