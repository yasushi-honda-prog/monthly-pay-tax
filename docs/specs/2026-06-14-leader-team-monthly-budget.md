# 統括隊×月予算 UI 追加 設計仕様書

| 項目 | 内容 |
|---|---|
| 起票 Issue | [#248](https://github.com/tadakayo/monthly-pay-tax/issues/248) |
| 起票日 | 2026-06-13 |
| 設計確定日 | 2026-06-14 (初版) / 2026-06-14 改訂版 (Codex review 反映) |
| 承認 Phase 4 案 | **B 案 (seed 自動 + 警告 + 差分 tooltip)** |
| 承認者 | 本田様 (brainstorm Phase 1-5 全セクション承認 + 改訂版承認) |
| Codex セカンドオピニオン | 中規模修正必要 → High 2 / Medium 5 / Low 3 反映済 |
| 後続コマンド | `/impl-plan` → `/tdd` |

---

## 1. 概要 / 動機

### 1.1 背景

PR #246 (要望 1b/2/3 隊×月予算入力 UI) + PR #247 (月次推移グラフ hotfix) のデプロイ後、本田様実機検証で発覚した残課題。

PR #247 で全体タブ月次推移グラフを `team_budgets_quarterly` (四半期÷3) ベースに修正したが、**同四半期内 3 ヶ月が同値**になるため「月次推移」として推移が見えない (5/6/7 月とも ¥7,819,148 フラット表示)。

本田様コメント:「**このグラフの意図は? 毎月の推移が見れるのでは?**」

### 1.2 動機

統括隊レベルの月別予算を「四半期÷3 一律値」ではなく「本田様が月ごとに手調整可能な値」として持つことで、月次推移グラフを本来の用途 (月毎の予算 vs 実額の推移可視化) に戻す。

### 1.3 ゴール

- 全体タブ・統括隊タブの月次推移グラフ予算ラインが「月毎に別値」で描画される
- admin (本田様) が 6 統括隊 × 12 ヶ月 = 72 セルを GUI から手入力できる
- 翌年度 (fiscal_year=2027 以降) の seed 手段が UI 側に存在する

---

## 2. 要件

### 2.1 機能要件

| F# | 要件 | 検証 |
|---|---|---|
| F1 | 新規 BQ table `leader_team_monthly_budgets` (fiscal_year×month×leader_team) を持つ | migration apply |
| F2 | migration apply 時に fiscal_year=2026 の 72 行を `team_budgets_quarterly` ÷3 で seed | migration テスト |
| F3 | admin 専用 page `leader_budget_input.py` で 6×12 grid 入力可能 | UI テスト + 実機 |
| F4 | grid 各セルに `quarterly÷3` 推定値を tooltip 表示 | UI テスト |
| F5 | 任意 fiscal_year に対し「quarterly÷3 で再 seed」ボタン提供 | UI テスト |
| F6 | 全体タブ月次推移グラフが新テーブル参照で同四半期内 3 ヶ月別値表示 | 実機検証 + 単体テスト |
| F7 | 統括隊タブ統括隊別月予算が新テーブル参照 | 実機検証 + 単体テスト |
| F8 | 楽観ロック (version) で別 admin の同時編集を検出 | repo テスト |
| F9 | 最終更新者記録 (created_by / updated_by) で操作者 email 記録 (※監査ログではない、DELETE で履歴消失) | migration + repo テスト |
| F10 | **(Codex H1 反映)** fiscal_year→暦年月範囲変換関数を共通化、`team_budget.py` の実績取得が FY 範囲で正しく動作 | `fiscal_calendar` テスト + 11/12 月境界の単体テスト |
| F11 | **(Codex H2 反映)** migration seed が冪等 (再実行で重複行が発生しない) | migration テスト (2 回実行 → COUNT 不変) |
| F12 | **(Codex M3 反映)** seed 再投入時に「変更セル数 / 現在合計 / seed 後合計」preview 表示後の二段階確認 | UI テスト |

### 2.2 非機能要件

| N# | 要件 | 根拠 |
|---|---|---|
| N1 | 既存 `team_budgets_quarterly` テーブルは破壊しない (役割: 四半期×統括隊×カテゴリ別予算保持) | Phase 3 質問 #5 で「そのまま残す」確定 |
| N2 | 既存 page (`team_budget.py`) の load_* 関数シグネチャ不変 (内部実装のみ切替) ※ただし year 引数の意味は暦年→fiscal_year に変更 | 既存呼び出し元への波及最小化 |
| N3 | PR #246 で確立した「team_budget_* 5 ファイル分業」パターンを踏襲 + **bulk 操作用結果モデル追加** (PR #246 は単一セル編集寄り、本設計は 72 セル bulk edit) | レビュアブル性、コードベース一貫性、Codex 指摘反映 |
| N4 | テストスイート増分 **+60 件想定** (952→約 1012 件)、全件 PASS 維持 (fiscal_calendar + 冪等性テスト追加分含む) | Definition of Done |
| N5 | Evaluator 分離プロトコル MUST 発動 (5 ファイル超変更、11 ファイル想定) | CLAUDE.md CRITICAL |

### 2.3 スコープ外

- **隊×月予算 (`team_budgets`)** の置換 — Phase 3 で「現状維持」確定、PR #246 実装をそのまま継続
- **soft delete (deleted_at/deleted_by)** — PR #246 follow-up と同じ判断、row DELETE で対応
- **過去 fiscal_year (2025 以前) の seed** — 実績データなし、scope 外
- **quarterly 更新→新テーブル自動同期** — Phase 4 で「C 完全同期」を却下、本田様が必要時に「再 seed」ボタン操作で同期判断

---

## 3. アーキテクチャ

### 3.1 ファイル変更一覧 (11 ファイル想定 ※Codex H1 反映で fiscal_calendar 追加)

```
infra/bigquery/migrations/
  2026-06-14_leader_team_monthly_budgets.sql        [新規]  テーブル作成 + 2026 seed MERGE (冪等)

dashboard/lib/
  fiscal_calendar.py       [新規]  fiscal_year↔calendar_month 変換 (Codex H1 対応)
  leader_budget_repo.py    [新規]  fetch / upsert / delete / seed_from_quarterly (楽観ロック)
                                   defensive: ROW_NUMBER で最新 1 件正規化
  leader_budget_cache.py   [新規]  @st.cache_data wrapper + invalidate 集約
                                   invalidate 対象は影響先ベースで列挙 (Codex M2 対応)
  bq_client.py             [修正]  load_leader_team_yearly_monthly_budgets 切替 (year→fiscal_year)
                                   load_leader_team_monthly_budgets 切替 (統括隊タブ用)
                                   load_leader_team_quarterly_budgets_for_seed [新規]
                                   load_team_budget_actuals: fiscal_calendar 経由で FY 範囲取得 (Codex H1)
                                   load_active_leader_teams: 同上
  constants.py             [修正]  LEADER_TEAM_MONTHLY_BUDGETS_TABLE 定数追加

dashboard/_pages/
  leader_budget_input.py   [新規]  admin 専用 6×12 grid 入力 UI + seed preview (Codex M3)
  team_budget.py           [修正]  fiscal_year selector 化 (Codex H1)、caption 文言修正

dashboard/app.py           [修正]  navigation 追加

dashboard/tests/
  test_lib_fiscal_calendar.py           [新規]  8 ケース想定 (Codex H1 対応)
  test_lib_leader_budget_repo.py        [新規]  17 ケース想定 (冪等性 + bulk 結果モデル含む)
  test_lib_leader_budget_cache.py       [新規]  10 ケース想定 (影響先ベース invalidate)
  test_lib_bq_client_leader.py          [新規]  10 ケース想定
  test_pages_leader_budget_input.py     [新規]  14 ケース想定 (seed preview + 11/12 月境界含む)
  test_lib_team_budget_view.py          [修正]  build_monthly_trend に 3 ケース追加
  test_lib_bq_client_team_budget.py     [修正]  SQL アサーション更新 + FY 範囲変換 8-10 件
  test_lib_team_budget_cache.py         [修正]  invalidate 関数追加 2 件
  test_pages_team_budget.py             [修正]  fiscal_year selector 化反映 2-3 件

scripts/tests/
  test_migration_leader_team_monthly_budgets.py  [新規 or 既存追記]  6 ケース想定 (冪等性検証含む)
```

### 3.2 依存方向

```
_pages/leader_budget_input.py
  ↓
leader_budget_cache.py  (UI cache wrapper)
  ↓
leader_budget_repo.py   (BQ DML、楽観ロック、ROW_NUMBER 正規化)
  ↓
bq_client.py            (BQ client + load_* 関数)
  ↓
fiscal_calendar.py      (fiscal_year↔calendar_month 変換、最下層)
  ↓
constants.py            (テーブル名定数)
```

循環依存なし。**fiscal_calendar.py は最下層**: bq_client / repo / page どこからでも参照可だが、自身は何も依存しない pure helper。

### 3.3 既存実装との関係

| 既存ファイル | 関係 |
|---|---|
| `team_budget_repo.py` | パターン踏襲 (新規 `leader_budget_repo.py` のテンプレート) |
| `team_budget_cache.py` | パターン踏襲 + invalidate 連携 (新 cache が古い cache を invalidate する必要あり) |
| `team_budget_hash.py` | **影響なし** (AI 評価 hash は team_budgets ベースで継続、新テーブルは hash 範囲外) |
| `team_budget_edit_logic.py` | **影響なし** (隊×月の超過判定で継続使用) |
| `_pages/team_budget.py` | load_* 関数の内部実装変更のみ、page 側は無修正 (caption 文言以外) |

---

## 4. データモデル

### 4.1 テーブル定義

```sql
CREATE TABLE IF NOT EXISTS `monthly-pay-tax.pay_reports.leader_team_monthly_budgets` (
  fiscal_year     INT64    NOT NULL,
  month           INT64    NOT NULL,          -- 1-12
  leader_team     STRING   NOT NULL,
  budget_amount   NUMERIC  NOT NULL,
  version         INT64    NOT NULL DEFAULT 1,
  created_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP(),
  created_by      STRING   NOT NULL,
  updated_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP(),
  updated_by      STRING   NOT NULL
)
CLUSTER BY fiscal_year, leader_team;
```

- **PK 相当**: `(fiscal_year, month, leader_team)` を MERGE 時に保証 (BQ は PK 制約なし、運用で担保)
- **partition**: 不要 (1 fiscal_year あたり 72 行のみ、最大数年で 300 行程度)
- **cluster**: `fiscal_year, leader_team` で fetch_yearly の filter 効率化

### 4.2 Seed MERGE (migration 内、fiscal_year=2026、※Codex H2 反映で冪等化)

```sql
MERGE `monthly-pay-tax.pay_reports.leader_team_monthly_budgets` T
USING (
  SELECT
    q.fiscal_year,
    m AS month,
    q.leader_team,
    SAFE_DIVIDE(SUM(q.budget_amount), 3) AS budget_amount
  FROM `monthly-pay-tax.pay_reports.team_budgets_quarterly` q
  CROSS JOIN UNNEST([
    CASE q.fiscal_quarter
      WHEN 1 THEN [11, 12, 1]
      WHEN 2 THEN [2, 3, 4]
      WHEN 3 THEN [5, 6, 7]
      WHEN 4 THEN [8, 9, 10]
    END
  ]) AS months
  CROSS JOIN UNNEST(months) AS m
  WHERE q.fiscal_year = 2026
  GROUP BY q.fiscal_year, q.leader_team, m
) S
ON T.fiscal_year = S.fiscal_year
   AND T.month = S.month
   AND T.leader_team = S.leader_team
WHEN NOT MATCHED THEN INSERT (
  fiscal_year, month, leader_team, budget_amount,
  version, created_by, updated_by
) VALUES (
  S.fiscal_year, S.month, S.leader_team, S.budget_amount,
  1, 'migration@2026-06-14', 'migration@2026-06-14'
);
-- 注: WHEN MATCHED は意図的に省略 (再実行で既存値を上書きしない、冪等)
```

**冪等性保証** (Codex H2 対応):
- 1 回目実行: 該当 row なし → INSERT → 72 行
- 2 回目実行: 全 row が MATCHED → 何もしない → 72 行のまま
- 手動編集後の再実行: 編集済み row は MATCHED → 上書きされない (保護)

**fiscal_quarter→month マッピング** (案 N11、`infra/bigquery/views.sql` `fiscal_quarter` UDF 準拠):
- Q1: 11, 12, 1 月
- Q2: 2, 3, 4 月
- Q3: 5, 6, 7 月
- Q4: 8, 9, 10 月

### 4.3 Python Row モデル (Codex L1 反映で int 採用)

```python
@dataclass(frozen=True)
class LeaderBudgetRow:
    fiscal_year: int
    month: int           # 1-12
    leader_team: str
    budget_amount: int   # NUMERIC → int (円整数運用、精度差問題回避)
    version: int
    created_at: datetime
    created_by: str
    updated_at: datetime
    updated_by: str
```

**型方針** (Codex L1 対応): `budget_amount` は **円整数** とし、BQ NUMERIC ↔ Python int の変換は repo 層で実施。float 化による精度差・Decimal の overhead 両方を回避。UI 入力も整数のみ受け付ける (小数入力は validate ではじく)。

### 4.4 Defensive Load (Codex H2 反映)

万一 PK 制約が運用上崩れた場合 (migration バグ / 並列 INSERT) でも UI が壊れないよう、`fetch_yearly` / `load_*` は ROW_NUMBER で最新 1 件を正規化:

```sql
SELECT * EXCEPT(rn) FROM (
  SELECT *,
    ROW_NUMBER() OVER(
      PARTITION BY fiscal_year, month, leader_team
      ORDER BY updated_at DESC, version DESC
    ) AS rn
  FROM `...leader_team_monthly_budgets`
  WHERE fiscal_year = @fiscal_year
) WHERE rn = 1
```

これにより重複 row 発生時も「最新 updated_at の row」が UI に表示される。重複検知のための監視クエリは Phase 9 (`/impl-plan`) で別途設計。

### 4.4 状態遷移

```
[未入力]
  ↓ upsert(expected_version=None) → INSERT (version=1)
[入力済(version=1)]
  ↓ upsert(expected_version=1)    → UPDATE (version=2)
[更新済(version=N)]
  ↓ delete(expected_version=N)    → DELETE
[未入力]
```

楽観ロック失敗時は `UpsertConflict` 例外、UI 側で該当セルだけ赤反転 + 他セルは保存継続。

---

## 5. インターフェース

### 5.1 `dashboard/lib/fiscal_calendar.py` (新規、Codex H1 対応)

会計年度 11 月始まりと暦年月の双方向変換を司る pure helper。`bq_client` / `repo` / `_pages/*` から参照可。

```python
# fiscal_quarter UDF と整合: Q1=11,12,1 / Q2=2,3,4 / Q3=5,6,7 / Q4=8,9,10

def fiscal_year_to_calendar_months(fiscal_year: int) -> list[tuple[int, int]]:
    """FY を構成する 12 ヶ月の (calendar_year, month) tuple を Q1 順で返す。
    FY2026 → [(2025,11),(2025,12),(2026,1),(2026,2),...,(2026,10)]"""

def calendar_to_fiscal(year: int, month: int) -> tuple[int, int]:
    """暦年月 → (fiscal_year, fiscal_quarter) を返す (BQ fiscal_quarter UDF と同等の Python 実装)。
    (2025, 11) → (2026, 1)、(2026, 5) → (2026, 3)"""

def fiscal_quarter_to_months(fiscal_quarter: int) -> list[int]:
    """fiscal_quarter (1-4) → 構成月リスト [Q順]。
    1 → [11, 12, 1]、3 → [5, 6, 7]"""

def fiscal_year_month_range(fiscal_year: int) -> tuple[int, int, int, int]:
    """load_team_budget_actuals(year_start, year_end, month_start, month_end) に渡せる範囲を返す。
    FY2026 → (2025, 2026, 11, 10)  # 11 月から翌年 10 月まで
    ※ ただし month_start > month_end のため、bq_client 側で「OR」分岐 SQL に組み立てる必要あり"""
```

**注意**: `fiscal_year_month_range` の戻り値は「年跨ぎ」を扱うため、呼び出し側で SQL 組み立てを工夫する必要あり。impl-plan で詳細化。

### 5.2 `dashboard/lib/leader_budget_repo.py` (新規)

```python
@dataclass(frozen=True)
class LeaderBudgetRow: ...

class UpsertConflict(Exception): ...

# bulk 操作用結果モデル (Codex 指摘: PR #246 は単一セル寄り、本設計は bulk)
@dataclass(frozen=True)
class BulkUpsertResult:
    saved_count: int
    conflicts: list[tuple[str, int]]  # [(leader_team, month), ...]
    deleted_count: int
    errors: list[tuple[str, int, str]]  # [(leader_team, month, error_msg), ...]

def fetch_yearly(fiscal_year: int) -> list[LeaderBudgetRow]:
    """ROW_NUMBER で defensive に最新 1 件正規化 (Codex H2 対応)。"""

def fetch_one(fiscal_year: int, month: int, leader_team: str) -> LeaderBudgetRow | None: ...

def upsert(
    fiscal_year, month, leader_team, budget_amount: int,
    expected_version, actor_email,
) -> LeaderBudgetRow:
    """expected_version=None で INSERT、int で UPDATE。version 不一致 → UpsertConflict raise."""

def delete(fiscal_year, month, leader_team, expected_version, actor_email) -> None: ...

def load_active_leader_teams_for_budget_input(fiscal_year: int) -> list[str]:
    """※ Codex L2 reflect: load_other_leader_teams から rename。
    予算入力 UI の行選択用に、対象 fiscal_year の active 統括隊一覧を返す。"""

def seed_from_quarterly(
    fiscal_year: int, actor_email: str, overwrite: bool,
) -> BulkUpsertResult:
    """overwrite=False で既存行ありなら ValueError raise。
    overwrite=True で既存 row を全て version+1 で上書き。"""

def preview_seed_from_quarterly(fiscal_year: int) -> dict:
    """※ Codex M3 reflect: 二段階確認の preview 用。
    実行前に「変更セル数 / 現在合計 / seed 後合計 / 差分大きい上位 N セル」を返す。
    Returns:
      {
        'changed_count': int,
        'current_total': int,
        'seed_total': int,
        'top_diffs': [(leader_team, month, current, seed, diff), ...],
      }"""
```

### 5.3 `dashboard/lib/leader_budget_cache.py` (新規、Codex M2 対応)

```python
@st.cache_data(ttl=600)
def cached_fetch_yearly(fiscal_year: int) -> list[LeaderBudgetRow]: ...

@st.cache_data(ttl=600)
def cached_load_quarterly_seed(fiscal_year: int) -> pd.DataFrame: ...

def invalidate_all(fiscal_year: int) -> None:
    """※ Codex M2 reflect: 4 関数固定ではなく、影響先ベースで列挙。
    leader_team_monthly_budgets が変わったことで再計算が必要になる cache 全て:
    - leader_budget_cache.cached_fetch_yearly.clear()
    - leader_budget_cache.cached_load_quarterly_seed.clear()
    - bq_client.load_leader_team_yearly_monthly_budgets.clear()  (全体タブ月次推移)
    - bq_client.load_leader_team_monthly_budgets.clear()          (統括隊タブ月予算)
    - bq_client.load_active_leader_teams.clear()                  (統括隊フィルタ用、新テーブル参照後)
    ※ load_team_budget_actuals は実績由来のため invalidate 不要
    ※ team_budget_cache の他の関数は team_budgets ベースで本テーブル変更影響なし
    """
```

### 5.4 `dashboard/lib/bq_client.py` (修正 + 1 追加、Codex H1 対応含む)

```python
# シグネチャ不変、内部実装を新テーブル参照に切替
@st.cache_data(ttl=600)
def load_leader_team_yearly_monthly_budgets(year: int) -> dict[int, int]:
    """year を fiscal_year として扱う (Issue #248 で意味変更)。
    returns: {month: SUM(budget_amount)} (12 月分、未投入月は 0)
    ※ 型を float → int (Codex L1)"""

@st.cache_data(ttl=600)
def load_leader_team_monthly_budgets(year: int, month: int) -> pd.DataFrame:
    """同上、year=fiscal_year。columns: leader_team, monthly_budget (int)"""

# 新規 (差分 tooltip 用)
@st.cache_data(ttl=600)
def load_leader_team_quarterly_budgets_for_seed(fiscal_year: int) -> pd.DataFrame:
    """差分 tooltip 用、columns: leader_team, month, quarterly_div3 (int)"""

# 修正: fiscal_year 範囲取得対応 (Codex H1)
@st.cache_data(ttl=300)
def load_team_budget_actuals(
    year_start, year_end, month_start, month_end, *, fiscal_year: int | None = None
) -> pd.DataFrame:
    """fiscal_year を指定した場合、内部で fiscal_calendar.fiscal_year_month_range を呼び、
    年跨ぎ (Q1=11,12,1) を正しく SELECT する。
    既存呼び出し (year_start=year_end=year, month_start=1, month_end=12) は後方互換維持。"""

@st.cache_data(ttl=600)
def load_active_leader_teams(year_start, year_end, month_start, month_end) -> list[str]:
    """※ Codex H1 reflect: fiscal_year 範囲を呼び出し側で fiscal_calendar 経由に。
    本関数自体のシグネチャは不変、team_budget.py 側で fiscal_calendar から範囲算出して渡す。"""
```

**意味論の重要変更** (Codex H1 反映済):
- `load_leader_team_yearly_monthly_budgets(year)` の `year` は **fiscal_year** に意味変更
- `team_budget.py` の年度セレクタを **fiscal_year selector** に切替
- 実績取得 (`load_team_budget_actuals` / `load_active_leader_teams`) は呼び出し側で `fiscal_calendar.fiscal_year_month_range(fy)` で範囲算出して渡す
- これにより FY2026 (2025/11-2026/10) の予算と実績が **同じ範囲** で取得され、11/12 月境界の年度ズレが発生しない

### 5.5 `dashboard/_pages/leader_budget_input.py` (新規、骨格、Codex M3 反映)

```python
def main() -> None:
    if not auth.require_role("admin"):
        return

    fiscal_year = _render_fiscal_year_selector()  # default: 現年度 (今日が 2026-06-14 → FY2026)
    current_rows = leader_budget_cache.cached_fetch_yearly(fiscal_year)
    seed_df = leader_budget_cache.cached_load_quarterly_seed(fiscal_year)

    if not current_rows:
        _render_seed_section(fiscal_year, seed_df)  # F5: 初期 seed ボタン
        return

    edited_df = st.data_editor(_build_grid(current_rows, seed_df), ...)
    if st.button("保存", type="primary"):
        result = _persist_diff(current_rows, edited_df, actor_email)  # BulkUpsertResult
        leader_budget_cache.invalidate_all(fiscal_year)
        _render_result(result)  # saved_count / conflicts / errors を表示
        st.rerun()

    with st.expander("⚠️ quarterly÷3 で全セル再 seed (上書き)"):
        if st.button("プレビュー"):
            preview = leader_budget_repo.preview_seed_from_quarterly(fiscal_year)
            _render_seed_preview(preview)  # 変更セル数 / 現在合計 / seed 後合計
        if st.checkbox("上記内容で上書きを承認"):
            if st.button("実行", type="secondary"):
                leader_budget_repo.seed_from_quarterly(fiscal_year, actor_email, overwrite=True)
                leader_budget_cache.invalidate_all(fiscal_year)
                st.success("再 seed 完了")
                st.rerun()
```

### 5.6 grid 仕様 (Codex M4 反映)

| 項目 | 仕様 |
|---|---|
| 行 | 6 統括隊 (leader_team、`team_hierarchy` 順) |
| 列 | 11, 12, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10 月 (fiscal_quarter 順 ※確定) |
| セル | budget_amount (int、円単位、整数入力) |
| 差分表示 | **第一候補**: 各列の help (列単位 tooltip) で「quarterly÷3 推定値」を提示。**フォールバック**: grid 下部に read-only DataFrame で差分一覧表示 (Codex M4: セル単位 tooltip は Streamlit data_editor で困難な可能性、impl-plan で実現可能性検証) |
| validation | `0 <= budget_amount < 1_000_000_000` (整数) |
| 空セル | 削除扱い (確認後 `repo.delete`) |

---

## 6. エラー処理

### 6.1 エラー分類 (Codex M1 反映で rollback 表現統一)

| カテゴリ | 発生例 | UI 挙動 | 復旧 |
|---|---|---|---|
| A. 楽観ロック競合 | 別 admin の同時編集 | conflict セル赤反転 + `st.error`、他セルは保存成功 | 「最新を再読込」ボタン |
| B. 入力値不正 | 負値 / 巨大値 / 非数値 / 小数 | 保存前 validate で `st.error`、BQ 書込前に弾く | 入力修正 |
| C. BQ 一時障害 | 5xx / timeout / quota | **該当セルのみ未反映、他セルは保存成功** + `st.error` で失敗セルリスト表示 | UI 「保存」再押下 (成功済みセルは再送不要) |
| D. 認可失敗 | non-admin URL アクセス | page 描画拒否 | admin に依頼 |
| E. seed 未投入 | fiscal_year=2027 で行なし | `st.info` + 「初期投入」ボタン提示 | admin 操作 |
| F. quarterly 未投入 | 初期投入元なし | `st.warning` + button disabled | scripts/upload_team_budgets_quarterly.py |

**重要** (Codex M1 反映): BQ DML は **トランザクション rollback 不可** (`MERGE` 単発で原子性は保証されるが、複数 row の連続 `MERGE` 間でのロールバックは不可)。よって C カテゴリでも「全保存ロールバック」表現は誤り、「該当セルのみ未反映、他セルは確定」が正しい挙動。本テーブル変更を全原子化したい場合は impl-plan で「一括 `MERGE` (USING (SELECT ... UNION ALL ...))」設計に変更する選択肢あり (現状は cell 単位 upsert で部分成功許容、本田様運用と整合)。

### 6.2 部分成功モデルの詳細 (PR #246 パターン + bulk 拡張)

```python
def _persist_diff(current_rows, edited_df, actor_email) -> BulkUpsertResult:
    """※ Codex 指摘反映: BulkUpsertResult で saved/conflicts/deleted/errors を構造化。"""
    saved_count, deleted_count = 0, 0
    conflicts, errors = [], []
    for (lt, m), edited in changes.items():
        try:
            if edited.is_delete:
                leader_budget_repo.delete(fy, m, lt, edited.version, actor_email)
                deleted_count += 1
            else:
                leader_budget_repo.upsert(
                    fiscal_year=fy, month=m, leader_team=lt,
                    budget_amount=edited.budget_amount,
                    expected_version=edited.version,
                    actor_email=actor_email,
                )
                saved_count += 1
        except UpsertConflict:
            conflicts.append((lt, m))
        except Exception as e:
            errors.append((lt, m, str(e)))  # BQ 一時障害等
    return BulkUpsertResult(saved_count, conflicts, deleted_count, errors)
```

**try が成功した分は確定**。conflict セルだけ警告、errors セルだけ再試行ガイド表示。

### 6.3 Seed 再投入の二段階確認 (Codex M3 反映で preview 必須化)

```python
# Step 1: プレビューボタン押下で preview 計算
preview = leader_budget_repo.preview_seed_from_quarterly(fiscal_year)
st.write(f"変更セル数: {preview['changed_count']} / 72")
st.write(f"現在合計: ¥{preview['current_total']:,}")
st.write(f"seed 後合計: ¥{preview['seed_total']:,}")
st.write(f"差額: ¥{preview['seed_total'] - preview['current_total']:+,}")
st.dataframe(preview['top_diffs'])  # 差分大きい上位 10 セル

# Step 2: 上書き承認 checkbox + 実行ボタンの二段階
if st.checkbox("上記内容で全 72 セルを上書きすることを承認"):
    if st.button("実行", type="secondary"):  # primary でなく secondary で危険度を視覚化
        leader_budget_repo.seed_from_quarterly(fiscal_year, actor_email, overwrite=True)
```

### 6.4 最終更新者記録 (Codex M5 反映、※「監査ログ」ではない)

- `created_by` / `updated_by` に email 記録 (最新状態の操作者のみ追跡可)
- DELETE すると履歴は消失するため、本格的な **監査ログとしては機能しない**
- 本田様 1 人運用のため最終更新者記録で十分。複数 admin 運用時は別途 audit table 設計 (OUT-5 参照)
- soft delete なし (PR #246 follow-up と同じ判断、scope 外)

### 6.5 障害通知連携

dashboard 直接 BQ DML のため `chat_notifier` 連携は **不要**。BQ 障害は Streamlit `st.error` で本田様に即時表示 → 本田様判断。

---

## 7. テスト戦略

### 7.1 Acceptance Criteria (14 件、Codex 反映で +4)

| # | 基準 | 検証 |
|---|---|---|
| AC1 | migration 適用後、fiscal_year=2026 の 72 行が quarterly÷3 値で seed | migration SQL を BQ mock で実行、COUNT=72 / SUM 一致 |
| AC2 | `load_leader_team_yearly_monthly_budgets(fiscal_year=2026)` が新テーブル参照、dict[int,int] 長さ 12 | mock BQ + SQL アサーション、int 型検証 |
| AC3 | `load_leader_team_monthly_budgets(fiscal_year=2026, month=5)` が新テーブル参照、leader_team 別 DataFrame | 同上 |
| AC4 | 全体タブ月次推移グラフが同四半期内 3 ヶ月別値で描画 | `build_monthly_trend` 単体テスト |
| AC5 | non-admin が `leader_budget_input.py` 描画拒否 | mock auth |
| AC6 | grid 編集 → 保存で `repo.upsert` が actor_email 付き呼出 | mock repo |
| AC7 | 楽観ロック競合時、conflict セルのみ error、他セル保存成功 (BulkUpsertResult 検証) | mock repo で 1 セル UpsertConflict |
| AC8 | 空セルへの編集で `delete` 呼出 (version 必須) | mock repo |
| AC9 | `invalidate_all(fiscal_year)` で **影響先 6 cache 関数** clear (cached_fetch_yearly / cached_load_quarterly_seed / cached_load_active_leader_teams_for_input / load_leader_team_yearly_monthly_budgets / load_leader_team_monthly_budgets / load_active_leader_teams) ※ Evaluator 指摘で初版 5 → 6 訂正 | clear 呼出検証 |
| AC10 | quarterly 未投入時、warning + 「初期投入」button disabled | mock empty quarterly |
| **AC11** (新) | **fiscal_calendar.fiscal_year_to_calendar_months(2026)** = [(2025,11),(2025,12),(2026,1),...,(2026,10)] 検証 | unit test、Q1-Q4 順、11/12 月境界 |
| **AC12** (新) | **migration seed の冪等性**: 1 回目実行で 72 行、2 回目実行でも 72 行 (重複なし)。手修正後の再実行で手修正値が保持される | migration SQL を 2 回実行、COUNT 不変 + 編集 row が MATCHED で上書きされないこと |
| **AC13** (新) | **11/12 月境界の年度ズレ無し**: FY2026 の実績取得が 2025/11-2026/10 範囲、予算と同じ範囲 | `team_budget.py` integration test (load_team_budget_actuals に fiscal_calendar 経由で範囲渡し検証) |
| **AC14** (新) | **seed_from_quarterly preview**: preview_seed_from_quarterly が `changed_count` / `current_total` / `seed_total` / `top_diffs` を返す | mock + 計算ロジック検証 |

### 7.2 テスト件数想定 (Codex 反映で +60 件)

| カテゴリ | 件数 |
|---|---|
| 新規 (dashboard、fiscal_calendar 含む) | 約 54 件 |
| 既存修正 (fiscal_year 化 + SQL アサーション) | 約 12 件 |
| 新規 (scripts、冪等性検証含む) | 約 6 件 |
| **合計増分** | **約 +60 件** (952 → 約 1012 件) |

### 7.3 TDD サイクル順序

`/impl-plan` で詳細化、想定順序 (Codex H1/H2 反映で fiscal_calendar 先行):
1. AC11 (fiscal_calendar) — pure helper、依存先なし、最初に Green 化
2. AC1 + AC12 (migration + 冪等性)
3. AC2 / AC3 / AC13 (load 関数 + 11/12 月境界)
4. AC6 / AC7 / AC8 / AC14 (repo + bulk + preview)
5. AC9 (cache)
6. AC5 / AC10 (page)
7. AC4 (build_monthly_trend 統合、最後)

### 7.4 Quality Gate

- `/safe-refactor` (3+ ファイル MUST)
- `/code-review high` (11 ファイル変更 = effort high)
- **Evaluator 分離 MUST** (5 ファイル超)、AC14 件全て独立評価
- `/codex review` (大規模 PR セカンドオピニオン、実装後再依頼)

---

## 8. スコープ外 / 将来課題

| # | 項目 | 理由 |
|---|---|---|
| OUT-1 | 隊×月予算 `team_budgets` の置換 | Phase 3 で現状維持確定 |
| OUT-2 | soft delete | PR #246 follow-up と同じ判断 |
| OUT-3 | 過去 fiscal_year (2025 以前) の seed | 実績データなし |
| OUT-4 | quarterly→新テーブル自動同期 | Phase 4 C 案却下 |
| **OUT-5** (新) | **本格的 audit table** (操作履歴 + DELETE 履歴保持) | Codex M5: 現状の `created_by/updated_by` は最終更新者記録のみ。複数 admin 運用時に検討 |
| **OUT-6** (新) | **重複 row 監視・通知** | Codex H2: ROW_NUMBER 防御で UI 表示は守れるが、重複発生検知の監視クエリ・Chat 通知は別途設計 |
| FUT-1 | 翌年度 (fiscal_year=2027) seed → UI 再 seed ボタンで対応 | F5 で実装済 |
| FUT-2 | カテゴリ別月予算 (現状: 四半期×カテゴリのみ) | quarterly の役割、新テーブルでは扱わない |
| FUT-3 | 一括 `MERGE` (USING UNION ALL) 全原子化 | Codex M1: 現状は部分成功許容、必要時に impl-plan で再設計 |

---

## 9. Open Questions (Codex review で OQ1/OQ2 確定済 → 削除)

| # | 項目 | 想定回答 | 確定タイミング |
|---|---|---|---|
| ~~OQ1~~ (確定) | fiscal_year セレクタの default 値 | **確定: 現年度 (今日が 2026-06-14 → FY2026)** | Codex 指摘で impl-plan 前確定 |
| ~~OQ2~~ (確定) | grid の列順 | **確定: 11, 12, 1, ..., 10 (fiscal_quarter 順)** | 同上 |
| OQ3 | grid 差分表示の最終形態 (列単位 tooltip / 差額列追加 / read-only DataFrame) | 想定: 列単位 tooltip 第一候補、Streamlit data_editor の仕様確認で実装中に決定 | impl-plan の実現性検証で確定 |
| OQ4 | 「初期投入」ボタンの文言・配置 | 想定: 「fiscal_year=YYYY を quarterly÷3 で初期投入」、page 上部 expander 内、admin のみ表示 | 実装中 |
| **OQ5** (新) | `created_by` の seed 元 email 文字列 | 想定: `'migration@2026-06-14'` (UI からの seed 時は actor_email) | 実装時確定 |

---

## 10. 参照

- [Issue #248](https://github.com/tadakayo/monthly-pay-tax/issues/248)
- [PR #246](https://github.com/tadakayo/monthly-pay-tax/pull/246) (要望 1b/2/3 隊×月予算入力 UI、本仕様の踏襲元 pattern)
- [PR #247](https://github.com/tadakayo/monthly-pay-tax/pull/247) (月次推移グラフ hotfix、本仕様が恒久対応として置換)
- [docs/specs/2026-06-13-team-monthly-budget-input.md](2026-06-13-team-monthly-budget-input.md) (隊×月予算設計、本仕様の姉妹仕様)
- `infra/bigquery/views.sql` `fiscal_quarter` UDF (会計年度 11 月始まり)
- `infra/bigquery/migrations/2026-06-11_quarterly_budgets.sql` (quarterly テーブル / `fiscal_quarter` UDF 定義)

---

## 11. 改訂履歴

| 日付 | 内容 | 担当 |
|---|---|---|
| 2026-06-14 | 初版 (brainstorm Phase 1-5 完了、本田様承認) | Claude Code |
| 2026-06-14 | 改訂版 (Codex review High 2 / Medium 5 / Low 3 反映、OQ1/OQ2 確定、fiscal_calendar.py 追加、ファイル数 10→11、テスト件数想定 +50→+60、AC 10→14) | Claude Code |
