# 予実管理ダッシュボード 前月比 (MoM Delta) 表示 設計仕様書

| 項目 | 値 |
|---|---|
| 作成日 | 2026-06-14 |
| 対応 Issue | #257 [予実管理] 前月比表示 — 全体タブ・統括隊ランキング・隊ドリルダウンの 3 軸対応 |
| ブランチ | `feat/257-team-budget-mom-delta` |
| 経緯 | brainstorm 2026-06-14 (本田様 + Claude Code) |

---

## 1. 概要 / 動機

予実管理ダッシュボード (`dashboard/_pages/team_budget.py`) に、当月の予実数値が前月と比べてどう変化したかを視覚的に表示する。
本田様の指示 (2026-06-14):

> 前月比が見れるようにもしたい（全体、統括隊、隊）issue化して対応

3 タブ (全体 / 統括隊 / 隊ドリルダウン) で前月比 (Month-over-Month delta, 以下 MoM delta) を表示する。
隊マトリクスは year-wide pivot で月次概念に合致しないため、本仕様のスコープ外。

---

## 2. 要件

### 2.1 機能要件

| ID | 要件 |
|---|---|
| F1 | tab_overall で全体集計の **実額** と **達成率** の前月比 delta を表示 |
| F2 | tab_leader で統括隊別 DataFrame の各統括隊行に **実額前月比** と **達成率前月比** 列を追加 |
| F3 | tab_drilldown で選択隊の **実額** と **達成率** の前月比 delta を `st.metric` の `delta` 引数で表示 (達成率の既存 delta=予実差額 は削除して前月比に置換) |
| F4 | FY 初月 (11 月) は前月比 delta を表示せず、caption で「FY 初月のため前月比なし」を補足 |
| F5 | 前月データなし (新隊 / 月予算未投入) の場合は `delta=None` で省略 |
| F6 | 前月予算 0 のため達成率前月比が計算不可な場合は `delta=None` で省略 |

### 2.2 非機能要件

| ID | 要件 |
|---|---|
| NF1 | actuals は既存 `actuals_year = load_team_budget_actuals(fiscal_year=fiscal_year)` の取得結果 (FY 12 ヶ月分) を月フィルタで流用 (追加呼び出しなし)。統括隊月予算 override は前月分を `load_leader_team_monthly_budgets(fiscal_year, prev_month)` で 1 件追加取得 (達成率前月比の分母不一致解消、code-review MEDIUM 反映) |
| NF2 | 純粋関数を `dashboard/lib/team_budget_view.py` に分離、Streamlit 非依存 (テスタブル) |
| NF3 | 既存 UI の表示挙動は変えない (新規 metric 追加と delta 引数の置換のみ) |
| NF4 | テスト: 純粋関数の単体テスト + UI 統合テスト (既存 `TestRenderTeamBudgetEditor` パターン流用) |

---

## 3. アーキテクチャ

### 3.1 レイヤー構成

```
UI 層 (dashboard/_pages/team_budget.py)
  ↓ 呼び出し
集計層 (dashboard/lib/team_budget_view.py)
  - summarize_actuals (既存)
  - summarize_by_leader_team (既存)
  - compute_mom_delta (新規)  ← 本仕様の追加点
  ↓ 入力
データ層 (dashboard/lib/bq_client.py)
  - load_team_budget_actuals (既存、FY 12 ヶ月分)
```

### 3.2 依存方向

新規関数 `compute_mom_delta` は純粋関数 (pandas / dict 入出力)、Streamlit 非依存。
UI 層から呼び出し、結果を `st.metric` の `delta` 引数に渡す。

---

## 4. データモデル

### 4.1 入力

- `actuals_year`: 既存の `load_team_budget_actuals(fiscal_year=...)` 戻り値 DataFrame
  - 列: `year, month, team, leader_team, actual_amount, budget_amount, achievement_rate, diff_amount, ...`
  - FY 12 ヶ月分 (例: FY2026 → 2026/11 〜 2026/10)

### 4.2 前月データ抽出

```python
prev_month = month - 1 if month > 1 else 12
actuals_prev_month = actuals_year[actuals_year["month"] == prev_month]
```

FY 初月 (11 月) のケース: `prev_month = 10`、ただし `actuals_year` には前 FY の 10 月データが含まれない → `actuals_prev_month` は空 DataFrame → 全体・統括隊・隊いずれも `delta=None` フォールバック。

### 4.3 永続化

なし。表示時の計算のみ。

---

## 5. インターフェース

### 5.1 純粋関数 `compute_mom_delta`

```python
def compute_mom_delta(
    current: Optional[dict],
    previous: Optional[dict],
) -> dict:
    """前月比 delta を計算する純粋関数 (Streamlit 非依存)。

    Args:
        current: {"actual_amount": float, "achievement_rate": Optional[float]}
        previous: 同上、None なら前月データなし

    Returns:
        {
          "actual_delta": Optional[float],       # 当月実額 - 前月実額
          "rate_delta": Optional[float],          # 当月達成率 - 前月達成率 (pt)
        }
        以下のケースで対応する delta は None:
        - previous が None (前月データなし)
        - current[key] が None / NaN
        - 達成率: previous["achievement_rate"] が None
    """
```

### 5.2 UI 層の呼び出し

#### tab_overall
```python
summary_current = summarize_actuals(actuals_month)
prev_month = month - 1 if month > 1 else 12
actuals_prev_month = actuals_year[actuals_year["month"] == prev_month]
summary_prev = (
    summarize_actuals(actuals_prev_month)
    if not actuals_prev_month.empty and month != 11
    else None
)
mom = compute_mom_delta(
    {"actual_amount": summary_current["total_actual"],
     "achievement_rate": summary_current["overall_rate"]},
    {"actual_amount": summary_prev["total_actual"],
     "achievement_rate": summary_prev["overall_rate"]} if summary_prev else None,
)
# render_kpi_row に mom を渡して st.metric の delta 引数で表示
```

#### tab_leader
```python
leader_summary = summarize_by_leader_team(actuals_month, _lt_budget_override)
leader_prev = (
    summarize_by_leader_team(actuals_prev_month, _lt_budget_override)
    if not actuals_prev_month.empty and month != 11
    else None
)
# leader_team で JOIN し、各行に actual_delta / rate_delta 列追加 → st.dataframe で表示
```

#### tab_drilldown
```python
actuals_team_prev = (
    actuals_prev_month[actuals_prev_month["team"] == team]
    if not actuals_prev_month.empty and month != 11
    else pd.DataFrame()
)
prev_row = actuals_team_prev.iloc[0] if not actuals_team_prev.empty else None
mom = compute_mom_delta(
    {"actual_amount": row["actual_amount"],
     "achievement_rate": row["achievement_rate"]},
    {"actual_amount": prev_row["actual_amount"],
     "achievement_rate": prev_row["achievement_rate"]} if prev_row is not None else None,
)
col_a.metric("実額", format_yen(row["actual_amount"]),
             delta=format_mom_yen(mom["actual_delta"]))
col_r.metric("達成率", format_rate(row["achievement_rate"]),
             delta=format_mom_pt(mom["rate_delta"]))  # ← 既存の予実差額 delta を置換
```

### 5.3 表示フォーマット関数 (新規)

```python
def format_mom_yen(delta: Optional[float]) -> Optional[str]:
    """前月比実額を ±¥XXX 形式に整形。None は None で返す (st.metric が delta 省略)"""
def format_mom_pt(delta: Optional[float]) -> Optional[str]:
    """前月比達成率 pt を ±X.Xpt 形式に整形。None は None で返す"""
```

---

## 6. エラー処理

| ケース | 挙動 |
|---|---|
| 前月データなし (`actuals_prev_month.empty`) | `delta=None` で `st.metric` の delta 省略 |
| FY 初月 (11 月) | 前月計算 skip、caption で「FY 初月のため前月比なし」表示 |
| 前月達成率が None (前月予算 0) | `rate_delta=None` で省略 |
| 当月達成率が None (当月予算 0) | `rate_delta=None` で省略 |
| 当月/前月実額が None / NaN | `actual_delta=None` で省略 |

---

## 7. テスト戦略

### 7.1 純粋関数の単体テスト (`dashboard/tests/test_lib_team_budget_view.py` 追記)

| テストケース | 入力 | 期待出力 |
|---|---|---|
| `test_mom_delta_both_present` | current={500k, 90%}, previous={400k, 80%} | {actual_delta=+100k, rate_delta=+10.0} |
| `test_mom_delta_previous_none` | current={500k, 90%}, previous=None | {actual_delta=None, rate_delta=None} |
| `test_mom_delta_current_actual_nan` | current={NaN, 90%}, previous={400k, 80%} | {actual_delta=None, rate_delta=+10.0} |
| `test_mom_delta_previous_rate_none` | current={500k, 90%}, previous={400k, None} | {actual_delta=+100k, rate_delta=None} |
| `test_mom_delta_negative` | current={300k, 60%}, previous={500k, 100%} | {actual_delta=-200k, rate_delta=-40.0} |

### 7.2 UI 統合テスト

| テストケース | 検証内容 |
|---|---|
| `test_overall_tab_renders_mom_delta` | tab_overall で当月 / 前月データありなら `st.metric` の `delta` 引数に値が渡る |
| `test_overall_tab_fy_initial_no_delta` | FY 初月 (month=11) では `st.metric` の `delta=None`、caption に「FY 初月」含む |
| `test_drilldown_metric_delta_replaced_with_mom` | tab_drilldown の達成率 metric の delta が前月比 (pt 形式) に変わっている |

### 7.3 Acceptance Criteria

- [x] AC1: 全体タブで実額・達成率の前月比が `st.metric` の delta で表示される
- [x] AC2: 統括隊タブの DataFrame に「実額前月比」「達成率前月比」列が追加される
- [x] AC3: 隊ドリルダウンの実額 metric に delta=前月比実額、達成率 metric に delta=前月比達成率
- [x] AC4: FY 初月 (11 月) では delta 省略 + caption「FY 初月のため前月比なし」表示
- [x] AC5: 新隊 / 予算未投入で前月データなしの場合、delta が省略される (None)
- [x] AC6: 既存テスト 651 件 + 新規 22 件 = **673 件全 pass**、回帰なし (本 PR で追加した新規テスト含む)
- [ ] AC7: 本田様の実機検証 (デプロイ後)

---

## 8. スコープ外 / 将来課題

| 項目 | 理由 |
|---|---|
| 隊マトリクスタブの前月比対応 | year-wide pivot で月次概念に合致しないため (Issue #257 で明示除外) |
| 前月比のグラフ表示 (推移チャート) | 既存の月次推移グラフ (tab_overall) で代替済、追加グラフは UI 過密化 |
| 予算・差額の前月比 | 達成率と相関高、情報重複のため除外 (brainstorm で本田様了承) |
| 前年同月比 (YoY) | 別 Issue として将来検討、本仕様は MoM のみ |

---

## 9. Open Questions

(なし、brainstorm で全項目確定済)

---

## 10. 実装ステップ概要

詳細は impl-plan で展開:

1. 純粋関数 `compute_mom_delta` + `format_mom_yen` / `format_mom_pt` を `team_budget_view.py` に追加 + 単体テスト (RED → GREEN)
2. `tab_overall` の `render_kpi_row` または直接呼出箇所で MoM delta を渡す + UI テスト
3. `tab_leader` の DataFrame に列追加 + UI テスト
4. `tab_drilldown` の `st.metric` delta 引数を MoM に置換 + UI テスト
5. FY 初月 caption 追加 + テスト
6. 全 651 件 + 新規テスト pass 確認
7. safe-refactor + code-review (任意)
8. commit + push + PR 作成
