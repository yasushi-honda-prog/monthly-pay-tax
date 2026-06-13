# 隊ドリルダウン UX 改善 設計仕様 (Issue #254 + Issue #245 統合)

- 起票日: 2026-06-14
- 関連 Issue: #254 (隊ドリルダウン UX 改善), #245 (要望 4 / 業務報告詳細強化, postponed → 本 spec で統合)
- 前提 PR: #246 (隊ドリルダウン初版), #250 (Issue #248 実装), #256 (#253 隊マトリクス差額表示)
- ステータス: ✅ 本田様承認済 (Phase 5)

---

## 概要 / 動機

Issue #248 (PR #250) の実機検証中、本田様から下記指摘:

> 隊ドリルダウンの UI が分かりにくい。selector 多階層 + 業務報告詳細の大量行スクロール + 中段の縦スクロール、すべて該当。

現状の隊ドリルダウン (`dashboard/_pages/team_budget.py:546-714`、PR #246 実装) は以下 3 軸の UX 課題が複合発生:

| 軸 | 課題 |
|---|---|
| 軸 1 | selector 多階層 (年月 + 統括隊フィルタ + 隊 selectbox の 3 ステップ) |
| 軸 2 | 業務報告詳細の大量行 (1 隊 × 1 月で 100+ 行) — 「何を見ればいいか」が分からない |
| 軸 3 | 中段縦スクロール (KPI / 月予算編集 / AI 評価 / 業務報告詳細を縦並びに詰め込み) |

軸 2 は Issue #245 (要望 4 / postponed) と直接重複するため、本 spec で **umbrella 統合** する。

---

## 要件

### 機能要件

1. **2 カラム横分割レイアウト** (案 B 確定)
   - 上部: 年月 (既存サイドバー由来) + 統括隊フィルタ + 隊 selectbox を **横並び** 配置
   - 左カラム: 集計 (KPI metric) + AI 評価コメント
   - 右カラム: 月予算編集 (admin) + 業務報告詳細 (強化版)

2. **業務報告詳細の強化** (#245 統合)
   - 既存「業務報告一覧」タブ (`dashboard.py` tab3) と同等の UX
   - 依存型ドロップダウン: 業務分類 + スポンサー (隊 = activity_category は **固定** のため UI 非表示)
   - キーワード検索 (検索対象選択 + リセット)
   - 件数表示

3. **隊 fix モード** (新規)
   - lib 抽出した関数に `fixed_activity_category` keyword 引数を追加
   - 指定時は `activity_category == fixed_activity_category` で内部 filter + 隊フィルタ UI 非表示

4. **期間範囲は 1 ヶ月分のみ** (確定事項)
   - 隊ドリルダウンは year/month で 1 ヶ月単位、期間指定モード不要
   - 期間指定は「業務報告一覧」タブの責務

### 非機能要件

- 既存「業務報告一覧」タブの挙動は **regression なし**
- admin 専用機能 (月予算編集) の表示制御は維持
- 既存テストは全 PASS、新規テスト追加 (隊 fix モード)
- 5+ ファイル + 新機能 → CLAUDE.md Quality Gate Evaluator 分離プロトコル発動

---

## アーキテクチャ

### 共通モジュール化方式 (確定: 案 i = lib 抽出)

`dashboard.py` 内の `_render_gyomu_list_view` 関数を `dashboard/lib/gyomu_list_view.py` に **抽出** し、両ページから import する。

```
dashboard/
├── lib/
│   └── gyomu_list_view.py  (新規: 抽出した render_gyomu_list_view)
├── _pages/
│   ├── dashboard.py        (修正: import + 呼出のみに簡素化)
│   └── team_budget.py      (修正: 2 カラム化 + render_gyomu_list_view 呼出)
└── tests/
    ├── test_lib_gyomu_list_view.py  (新規: 隊 fix モード etc.)
    └── test_pages_team_budget.py    (修正: ドリルダウンタブのレイアウト整合性)
```

### 関数シグネチャ拡張

```python
def render_gyomu_list_view(
    df_gyomu_all: pd.DataFrame,
    name_map: dict,
    selected_members: list,
    selected_year: int,
    selected_month: str,            # "6月" or "期間指定"
    range_start_year: int | None,
    range_start_month: int | None,
    range_end_year: int | None,
    range_end_month: int | None,
    *,
    key_prefix: str,
    wam_only: bool = False,
    empty_message: str = "データがありません",
    # ↓ 新規追加 (Issue #254/#245)
    fixed_activity_category: str | None = None,
) -> None:
    """業務報告一覧のテーブルビューを描画する。

    fixed_activity_category 指定時:
      - 内部 filter: activity_category == fixed_activity_category
      - 隊（活動）分類 selectbox を UI 非表示 (fcol1 を空 col に置換 or 2 列レイアウト)
      - 業務分類 / スポンサーの依存型ドロップダウンは継承
    """
```

### 隊ドリルダウンタブの再構築

```python
# team_budget.py 隊ドリルダウンタブの新構造
with tab_drilldown:
    st.subheader(f"{year}年{month}月 隊ドリルダウン")
    all_teams = load_active_teams(year, year, month, month)
    if not all_teams:
        st.warning(...)
    else:
        # 上部 selector 横並び (3 列)
        sel_col1, sel_col2, _spacer = st.columns([2, 3, 5])
        with sel_col1:
            drill_filter_leader = st.selectbox("統括隊で絞り込み", ..., key="tb_drilldown_filter_leader")
        with sel_col2:
            team = st.selectbox("隊を選択", teams, ..., key="tb_drill_team")

        # 2 カラム横分割
        col_left, col_right = st.columns([1, 1])

        with col_left:
            # 集計 (KPI metric)
            st.markdown("### 集計")
            if actuals_team.empty:
                st.warning("当月の集計データがありません。")
            else:
                row = actuals_team.iloc[0]
                col_b, col_a, col_r = st.columns(3)
                col_b.metric("予算", format_yen(row["budget_amount"]))
                col_a.metric("実額", format_yen(row["actual_amount"]))
                col_r.metric("達成率", format_rate(row["achievement_rate"]),
                            delta=format_diff(row["diff_amount"]))

            # AI 評価コメント (既存ロジック維持)
            st.markdown("### AI 評価コメント")
            ...
            render_ai_comment_card(eval_row, outdated=outdated, is_admin=is_admin, ...)

        with col_right:
            # 月予算編集 (admin 限定)
            if is_admin:
                _render_team_budget_editor(...)

            # 業務報告詳細 (lib 関数呼出に置換)
            st.markdown("### 業務報告詳細")
            render_gyomu_list_view(
                df_gyomu_all=load_gyomu_with_members(),
                name_map=name_map,
                selected_members=[],            # 全メンバー
                selected_year=year,
                selected_month=f"{month}月",
                range_start_year=None, ..., range_end_year=None, ...,
                key_prefix="drilldown",
                fixed_activity_category=team,
                empty_message="この隊・月の業務報告はありません",
            )
```

---

## データモデル / インターフェース

### 入力データ

| 引数 | 型 | 説明 |
|---|---|---|
| `df_gyomu_all` | `pd.DataFrame` | `load_gyomu_with_members()` 由来、全件 |
| `name_map` | `dict[str, str]` | nickname → display_name |
| `fixed_activity_category` | `str \| None` | 隊 fix モード (None なら隊フィルタ UI 表示) |

### 状態 (session_state)

`key_prefix="drilldown"` でユニーク化:
- `drilldown_reset_counter` (フィルタ counter)
- `drilldown_cat_0`, `drilldown_wcat_0`, `drilldown_sponsor_0`, `drilldown_kw_0`, `drilldown_target_0`
- `tb_drill_team` (既存、隊 selectbox)
- `tb_drilldown_filter_leader` (既存、統括隊フィルタ)
- `tb_selected_team` (既存、隊マトリクスからのジャンプ)

---

## エラー処理

- `df_gyomu_all.empty` → `st.info(empty_message)` で早期 return
- BQ 取得失敗 → `st.error()` + `st.stop()` (既存ロジック踏襲)
- `fixed_activity_category` 指定で該当行ゼロ → `empty_message` 表示
- 既存 silent failure ハンドリング (例: `pd.to_numeric` の `errors="coerce"`) は維持

---

## テスト戦略

### 新規テスト (`test_lib_gyomu_list_view.py`)

| テストケース | 目的 |
|---|---|
| `fixed_activity_category=None` で既存挙動 | regression check (隊フィルタ UI 表示) |
| `fixed_activity_category="○○隊"` で隊 fix | 内部 filter 適用、UI 非表示確認 |
| `fixed_activity_category="存在しない隊"` で 0 件 | empty_message 表示 |
| 依存型ドロップダウン (業務分類 / スポンサー) | fixed mode でも動作する |
| キーワード検索 + リセット | fixed mode で counter increment 動作 |

### 既存テスト regression check

- `test_pages_dashboard.py` の `_render_gyomu_list_view` 関連テスト → import path 変更で `from lib.gyomu_list_view import render_gyomu_list_view` に追従
- `test_pages_team_budget.py` の ドリルダウンテスト → 2 カラムレイアウトの import smoke で例外なし確認

### Acceptance Criteria

- **AC1**: 隊ドリルダウンタブが 2 カラム横分割で表示 (上部 selector 横並び)
- **AC2**: 左カラム = 集計 KPI + AI 評価、右カラム = 月予算編集 (admin のみ) + 業務報告詳細
- **AC3**: 業務報告詳細が「業務報告一覧」と同等の UX (隊分類は fix、業務分類 + スポンサーの依存型ドロップダウン、キーワード検索、件数表示)
- **AC4**: 既存「業務報告一覧」タブの挙動は無変更 (regression なし)
- **AC5**: admin 専用機能 (月予算編集) の表示制御は維持
- **AC6**: 全テスト PASS + 新規 lib テスト 5 ケース以上 PASS
- **AC7**: Streamlit の `st.columns` レイアウトが 2 カラム表示で破綻しない (横スクロール発生なし、各 KPI metric が読める幅)

---

## スコープ外 / 将来課題

- **期間指定モード**: 隊ドリルダウンには追加しない (「業務報告一覧」タブで対応)
- **隊チップ表示** (案 C): 案 B で UX 改善目標達成のため対応せず
- **subtab レイアウト** (案 A): 同上
- **業務報告詳細の追加ソート機能**: 別 Issue (ROI 評価後)
- **format_diff と format_diff_yen の統合** (PR #256 follow-up): 別 Issue

---

## Open Questions

なし (Phase 3-5 で全主要判断完了)。

---

## 実装ステップ (impl-plan で具体化予定)

1. **T1**: `_render_gyomu_list_view` を `lib/gyomu_list_view.py` に抽出 (機能変更なし、純粋な move + rename)
   - `dashboard.py` から該当関数 + 依存ヘルパ移動
   - `dashboard.py` 側を `from lib.gyomu_list_view import render_gyomu_list_view` に置換
   - 既存テスト全 PASS 確認
2. **T2**: `fixed_activity_category` keyword 追加 + filter 適用 + 隊 UI 条件分岐
   - 新規テスト 5 ケース追加 (test_lib_gyomu_list_view.py)
3. **T3**: `team_budget.py` の隊ドリルダウンタブを 2 カラムレイアウトに再構築
   - 上部 selector 横並び (st.columns([2, 3, 5]))
   - 左 (集計 + AI 評価) / 右 (月予算編集 + 業務報告詳細) の st.columns([1, 1])
   - 業務報告詳細を `render_gyomu_list_view` 呼出に置換
   - 既存テスト regression check
4. **T4**: Quality Gate 3 段 (safe-refactor → code-review high → Evaluator)
5. **T5**: PR 作成 + 6 エージェントレビュー + Codex セカンドオピニオン候補

---

## QG 発動条件チェック

- 変更ファイル数: 5+ (lib 新規 + dashboard.py 修正 + team_budget.py 修正 + tests 2 ファイル) → **5+ ファイル** ✅
- 新規機能の追加: 業務報告一覧と同等の UX を隊ドリルダウンで提供 → **新規機能** ✅
- アーキテクチャ影響: `lib/gyomu_list_view.py` 新規モジュール導入 → **新パターン** ✅

→ Evaluator 分離プロトコル (`/safe-refactor` → `/code-review high` → `evaluator` agent) を **発動**。

---

## 参考

- 既存「業務報告一覧」実装: `dashboard/_pages/dashboard.py:532-` (`_render_gyomu_list_view`)
- 既存「隊ドリルダウン」実装: `dashboard/_pages/team_budget.py:546-714`
- 関連 Issue: #254 (本 Issue), #245 (postponed, 軸 2 と統合)
- 前 PR: #246 (初版), #250 (#248), #256 (#253)
