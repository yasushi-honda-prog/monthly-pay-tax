# 統括隊×月予算 UI 追加 設計仕様書

| 項目 | 内容 |
|---|---|
| 起票 Issue | [#248](https://github.com/tadakayo/monthly-pay-tax/issues/248) |
| 起票日 | 2026-06-13 |
| 設計確定日 | 2026-06-14 |
| 承認 Phase 4 案 | **B 案 (seed 自動 + 警告 + 差分 tooltip)** |
| 承認者 | 本田様 (brainstorm Phase 1-5 全セクション承認) |
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
| F9 | 監査ログ (created_by / updated_by) で操作者 email 記録 | migration + repo テスト |

### 2.2 非機能要件

| N# | 要件 | 根拠 |
|---|---|---|
| N1 | 既存 `team_budgets_quarterly` テーブルは破壊しない (役割: 四半期×統括隊×カテゴリ別予算保持) | Phase 3 質問 #5 で「そのまま残す」確定 |
| N2 | 既存 page (`team_budget.py`) の load_* 関数シグネチャ不変 (内部実装のみ切替) | 既存呼び出し元への波及最小化 |
| N3 | PR #246 で確立した「team_budget_* 5 ファイル分業」パターンを踏襲 | レビュアブル性、コードベース一貫性 |
| N4 | テストスイート増分 +50 件想定 (952→1002 件)、全件 PASS 維持 | Definition of Done |
| N5 | Evaluator 分離プロトコル MUST 発動 (5 ファイル超変更) | CLAUDE.md CRITICAL |

### 2.3 スコープ外

- **隊×月予算 (`team_budgets`)** の置換 — Phase 3 で「現状維持」確定、PR #246 実装をそのまま継続
- **soft delete (deleted_at/deleted_by)** — PR #246 follow-up と同じ判断、row DELETE で対応
- **過去 fiscal_year (2025 以前) の seed** — 実績データなし、scope 外
- **quarterly 更新→新テーブル自動同期** — Phase 4 で「C 完全同期」を却下、本田様が必要時に「再 seed」ボタン操作で同期判断

---

## 3. アーキテクチャ

### 3.1 ファイル変更一覧 (10 ファイル想定)

```
infra/bigquery/migrations/
  2026-06-14_leader_team_monthly_budgets.sql        [新規]  テーブル作成 + 2026 seed INSERT

dashboard/lib/
  leader_budget_repo.py    [新規]  fetch / upsert / delete / seed_from_quarterly (楽観ロック)
  leader_budget_cache.py   [新規]  @st.cache_data wrapper + invalidate 集約
  bq_client.py             [修正]  load_leader_team_yearly_monthly_budgets 切替
                                   load_leader_team_monthly_budgets 切替 (統括隊タブ用)
                                   load_leader_team_quarterly_budgets_for_seed [新規]
  constants.py             [修正]  LEADER_TEAM_MONTHLY_BUDGETS_TABLE 定数追加

dashboard/_pages/
  leader_budget_input.py   [新規]  admin 専用 6×12 grid 入力 UI
  team_budget.py           [修正]  caption 文言修正 (quarterly→新テーブル参照案内)

dashboard/app.py           [修正]  navigation 追加

dashboard/tests/
  test_lib_leader_budget_repo.py        [新規]  15 ケース想定
  test_lib_leader_budget_cache.py       [新規]  8 ケース想定
  test_lib_bq_client_leader.py          [新規]  10 ケース想定
  test_pages_leader_budget_input.py     [新規]  12 ケース想定
  test_lib_team_budget_view.py          [修正]  build_monthly_trend に 3 ケース追加
  test_lib_bq_client_team_budget.py     [修正]  SQL アサーション更新 5-8 件
  test_lib_team_budget_cache.py         [修正]  invalidate 関数追加 2 件
  test_pages_team_budget.py             [修正]  必要なら 0-2 件

scripts/tests/
  test_migration_leader_team_monthly_budgets.py  [新規 or 既存追記]  5 ケース想定
```

### 3.2 依存方向

```
_pages/leader_budget_input.py
  ↓
leader_budget_cache.py  (UI cache wrapper)
  ↓
leader_budget_repo.py   (BQ DML、楽観ロック)
  ↓
bq_client.py            (BQ client + load_* 関数)
  ↓
constants.py            (テーブル名定数)
```

循環依存なし。

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

### 4.2 Seed INSERT (migration 内、fiscal_year=2026 のみ)

```sql
INSERT INTO `monthly-pay-tax.pay_reports.leader_team_monthly_budgets`
  (fiscal_year, month, leader_team, budget_amount, version, created_by, updated_by)
SELECT
  q.fiscal_year,
  m AS month,
  q.leader_team,
  SAFE_DIVIDE(SUM(q.budget_amount), 3) AS budget_amount,
  1, 'migration@2026-06-14', 'migration@2026-06-14'
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
GROUP BY q.fiscal_year, q.leader_team, m;
```

**fiscal_quarter→month マッピング** (案 N11、`infra/bigquery/views.sql` `fiscal_quarter` UDF 準拠):
- Q1: 11, 12, 1 月
- Q2: 2, 3, 4 月
- Q3: 5, 6, 7 月
- Q4: 8, 9, 10 月

### 4.3 Python Row モデル

```python
@dataclass(frozen=True)
class LeaderBudgetRow:
    fiscal_year: int
    month: int           # 1-12
    leader_team: str
    budget_amount: float  # NUMERIC を float 化
    version: int
    created_at: datetime
    created_by: str
    updated_at: datetime
    updated_by: str
```

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

### 5.1 `dashboard/lib/leader_budget_repo.py` (新規)

```python
@dataclass(frozen=True)
class LeaderBudgetRow: ...

class UpsertConflict(Exception): ...

def fetch_yearly(fiscal_year: int) -> list[LeaderBudgetRow]: ...
def fetch_one(fiscal_year: int, month: int, leader_team: str) -> LeaderBudgetRow | None: ...
def upsert(fiscal_year, month, leader_team, budget_amount, expected_version, actor_email) -> LeaderBudgetRow: ...
def delete(fiscal_year, month, leader_team, expected_version, actor_email) -> None: ...
def load_other_leader_teams(fiscal_year: int) -> list[str]: ...
def seed_from_quarterly(fiscal_year: int, actor_email: str, overwrite: bool) -> int: ...
    # 返り値: 投入 row 数。overwrite=False で既存行ありなら ValueError raise
```

### 5.2 `dashboard/lib/leader_budget_cache.py` (新規)

```python
@st.cache_data(ttl=600)
def cached_fetch_yearly(fiscal_year: int) -> list[LeaderBudgetRow]: ...

@st.cache_data(ttl=600)
def cached_load_quarterly_seed(fiscal_year: int) -> pd.DataFrame: ...

def invalidate_all(fiscal_year: int) -> None:
    """関連 cache を一括クリア:
    - leader_budget_cache.cached_fetch_yearly.clear()
    - bq_client.load_leader_team_yearly_monthly_budgets.clear()
    - bq_client.load_leader_team_monthly_budgets.clear()
    - cached_load_quarterly_seed.clear()
    """
```

### 5.3 `dashboard/lib/bq_client.py` (修正 + 1 追加)

```python
# シグネチャ不変、内部実装を新テーブル参照に切替
@st.cache_data(ttl=600)
def load_leader_team_yearly_monthly_budgets(year: int) -> dict[int, float]:
    """year を fiscal_year として扱う (PR #248 で意味変更)。"""

@st.cache_data(ttl=600)
def load_leader_team_monthly_budgets(year: int, month: int) -> pd.DataFrame:
    """同上、year=fiscal_year。"""

# 新規
@st.cache_data(ttl=600)
def load_leader_team_quarterly_budgets_for_seed(fiscal_year: int) -> pd.DataFrame:
    """差分 tooltip 用、columns: leader_team, month, quarterly_div3"""
```

**意味論の重要変更**: 既存呼び出し `load_leader_team_yearly_monthly_budgets(year)` の `year` 引数は暦年から fiscal_year に意味が変わる。team_budget.py 側のセレクタも fiscal_year 表示に合わせる。

### 5.4 `dashboard/_pages/leader_budget_input.py` (新規、骨格)

```python
def main() -> None:
    if not auth.require_role("admin"):
        return

    fiscal_year = _render_fiscal_year_selector()  # default: 今日が 11 月以降なら来年度
    current_rows = leader_budget_cache.cached_fetch_yearly(fiscal_year)
    seed_df = leader_budget_cache.cached_load_quarterly_seed(fiscal_year)

    if not current_rows:
        _render_seed_section(fiscal_year, seed_df)  # F5: 再 seed ボタン
        return

    edited_df = st.data_editor(_build_grid(current_rows, seed_df), ...)
    if st.button("保存", type="primary"):
        saved_count, conflicts = _persist_diff(current_rows, edited_df, actor_email)
        leader_budget_cache.invalidate_all(fiscal_year)
        _render_result(saved_count, conflicts)
        st.rerun()
```

### 5.5 grid 仕様

| 項目 | 仕様 |
|---|---|
| 行 | 6 統括隊 (leader_team、`team_hierarchy` 順) |
| 列 | 11, 12, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10 月 (fiscal_quarter 順) |
| セル | budget_amount (NUMERIC、円単位、整数入力) |
| tooltip | `f"quarterly÷3 推定値: ¥{quarterly_div3:,.0f}"` |
| validation | `0 <= budget_amount < 1_000_000_000` |
| 空セル | 削除扱い (確認後 `repo.delete`) |

---

## 6. エラー処理

### 6.1 エラー分類

| カテゴリ | 発生例 | UI 挙動 | 復旧 |
|---|---|---|---|
| A. 楽観ロック競合 | 別 admin の同時編集 | conflict セル赤反転 + `st.error`、他セルは保存成功 | 「最新を再読込」ボタン |
| B. 入力値不正 | 負値 / 巨大値 / 非数値 | 保存前 validate で `st.error` | 入力修正 |
| C. BQ 一時障害 | 5xx / timeout | `st.error` + 全保存ロールバック | 「保存」再押下 |
| D. 認可失敗 | non-admin URL アクセス | page 描画拒否 | admin に依頼 |
| E. seed 未投入 | fiscal_year=2027 で行なし | `st.info` + 「初期投入」ボタン提示 | admin 操作 |
| F. quarterly 未投入 | 初期投入元なし | `st.warning` + button disabled | scripts/upload_team_budgets_quarterly.py |

### 6.2 楽観ロック競合の詳細 (PR #246 パターン継承)

```python
def _persist_diff(current_rows, edited_df, actor_email):
    conflicts, saved_count = [], 0
    for (lt, m), edited in changes.items():
        try:
            leader_budget_repo.upsert(
                fiscal_year=fy, month=m, leader_team=lt,
                budget_amount=edited.budget_amount,
                expected_version=edited.version,
                actor_email=actor_email,
            )
            saved_count += 1
        except UpsertConflict:
            conflicts.append((lt, m))
    return saved_count, conflicts
```

**try が成功した分は確定**。conflict セルだけ警告。

### 6.3 Seed 再投入の二段階確認

```python
if _yearly_has_data(fiscal_year):
    st.warning("既に手動投入済みデータがあります。上書きしますか?")
    if not st.checkbox("上書きを承認"):
        return
leader_budget_repo.seed_from_quarterly(fiscal_year, actor_email, overwrite=True)
```

### 6.4 監査ログ

- `created_by` / `updated_by` に email 記録
- soft delete なし (PR #246 follow-up と同じ判断、scope 外)

### 6.5 障害通知連携

dashboard 直接 BQ DML のため `chat_notifier` 連携は **不要**。BQ 障害は Streamlit `st.error` で本田様に即時表示 → 本田様判断。

---

## 7. テスト戦略

### 7.1 Acceptance Criteria (10 件)

| # | 基準 | 検証 |
|---|---|---|
| AC1 | migration 適用後、fiscal_year=2026 の 72 行が quarterly÷3 値で seed | migration SQL を BQ mock で実行、COUNT=72 / SUM 一致 |
| AC2 | `load_leader_team_yearly_monthly_budgets(fiscal_year=2026)` が新テーブル参照、dict[int,float] 長さ 12 | mock BQ + SQL アサーション |
| AC3 | `load_leader_team_monthly_budgets(fiscal_year=2026, month=5)` が新テーブル参照、leader_team 別 DataFrame | 同上 |
| AC4 | 全体タブ月次推移グラフが同四半期内 3 ヶ月別値で描画 | `build_monthly_trend` 単体テスト |
| AC5 | non-admin が `leader_budget_input.py` 描画拒否 | mock auth |
| AC6 | grid 編集 → 保存で `repo.upsert` が actor_email 付き呼出 | mock repo |
| AC7 | 楽観ロック競合時、conflict セルのみ error、他セル保存成功 | mock repo で 1 セル UpsertConflict |
| AC8 | 空セルへの編集で `delete` 呼出 (version 必須) | mock repo |
| AC9 | `invalidate_all(fiscal_year)` で 4 cache 関数 clear | clear 呼出検証 |
| AC10 | quarterly 未投入時、warning + 「初期投入」button disabled | mock empty quarterly |

### 7.2 テスト件数想定

| カテゴリ | 件数 |
|---|---|
| 新規 (dashboard) | 約 45 件 |
| 既存修正 | 約 8 件 |
| 新規 (scripts) | 約 5 件 |
| **合計増分** | **約 +50 件** (952 → 約 1002 件) |

### 7.3 TDD サイクル順序

`/impl-plan` で詳細化、想定順序:
1. AC1 (migration) → 2. AC2/AC3 (load 関数) → 3. AC6/AC7/AC8 (repo) → 4. AC9 (cache) → 5. AC5/AC10 (page) → 6. AC4 (build_monthly_trend 統合)

### 7.4 Quality Gate

- `/safe-refactor` (3+ ファイル MUST)
- `/code-review high` (10 ファイル変更 = effort high)
- **Evaluator 分離 MUST** (5 ファイル超)
- `/codex review` (大規模 PR セカンドオピニオン)

---

## 8. スコープ外 / 将来課題

| # | 項目 | 理由 |
|---|---|---|
| OUT-1 | 隊×月予算 `team_budgets` の置換 | Phase 3 で現状維持確定 |
| OUT-2 | soft delete | PR #246 follow-up と同じ判断 |
| OUT-3 | 過去 fiscal_year (2025 以前) の seed | 実績データなし |
| OUT-4 | quarterly→新テーブル自動同期 | Phase 4 C 案却下 |
| FUT-1 | 翌年度 (fiscal_year=2027) seed → UI 再 seed ボタンで対応 | F5 で実装済 |
| FUT-2 | カテゴリ別月予算 (現状: 四半期×カテゴリのみ) | quarterly の役割、新テーブルでは扱わない |

---

## 9. Open Questions

| # | 項目 | 想定回答 | 確定タイミング |
|---|---|---|---|
| OQ1 | fiscal_year セレクタの default 値ロジック (今日が 11 月以降→来年度) は本田様運用に合うか | 想定: 合致するが、UI 上で表示時に「今 (2026/06/14) → fiscal_year=2026 を default」で問題ない | 実装中に本田様確認、または impl-plan で再質問 |
| OQ2 | grid の列順は「11, 12, 1, 2, ..., 10 (fiscal_quarter 順)」か「1, 2, ..., 12 (暦年順)」か | 想定: fiscal_quarter 順 (Q1=11,12,1 など視覚的にまとまる) | 実装中に本田様確認 |
| OQ3 | 差分 tooltip ではなく「÷3 推定との差額」列追加が好ましいか | 想定: tooltip で十分 (列数 6×12=72 を倍 144 にすると目視負荷増) | 実装中に本田様確認 |
| OQ4 | 「初期投入」ボタンの文言・配置 | 想定: 「fiscal_year=YYYY を quarterly÷3 で初期投入」、page 上部、admin のみ表示 | 実装中 |

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
