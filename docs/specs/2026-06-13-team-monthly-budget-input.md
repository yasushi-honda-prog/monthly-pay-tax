# 隊×月予算入力 UI 設計仕様書 (要望 1b/2/3 クラスタ対応)

**作成日**: 2026-06-13
**前提**:
- PR-A〜D の `team_budgets` (隊×月、`docs/specs/2026-06-10-team-budget-eval-design.md`)
- PR-E の `team_budgets_quarterly` (統括隊×四半期×カテゴリ、`docs/specs/2026-06-11-team-budget-quarterly.md`)
- PR-A 2026-06-12 統括隊ベース再構成 (`docs/specs/2026-06-12-team-budget-leader-team-restructure.md`)
- handoff `docs/handoff/LATEST.md` 2026-06-13 PM「条件待ち #2」より本田様明示指示で着手
- 関連 Issue: #244 (本 PR scope) / #245 (要望 4、postponed)
- Codex セカンドオピニオン: 2026-06-13 セッション中に取得、a〜l 12 論点を本 spec に反映済

**ステータス**: 本田様承認待ち (brainstorm Phase 5 全セクション ok 済 → Phase 6 文書出力)

---

## 1. 背景・動機

### 1.1 本田様報告 (handoff 2026-06-13 PM)

| # | 症状 / 要望 | 真因 |
|---|---|---|
| **1b** | 月次推移グラフの予算が ¥0 フラットライン (PR-Q2M 月予算が KPI のみ反映、グラフ未反映) | 隊×月予算データソース未整備 |
| **2** | 隊マトリクスタブが空表示「意味が分からない」 | `team_budgets` 空で達成率算出不可 |
| **3** | 隊ドリルダウンに各隊月予算入力 UI 追加 (統括隊予算との整合性チェック付き) | 入力導線そのものが未実装 |

### 1.2 1b/2/3 を 1 つの設計問題として扱う理由

3 件はいずれも `team_budgets` テーブル空が共通根本原因。入力 UI (3) を提供すれば本田様が手打ちでデータ投入でき、その結果として 1b/2 の表示が既存ロジックで自動解消する。**3 つを独立 PR にすると、1b/2 単体ではデータが入らず検証不能**となるため一体設計が必須。

### 1.3 1b/2 を「グラフ・マトリクス側ロジックを統括隊予算ベースに変更」ではなく「team_budgets 入力で解消」する判断

本田様の要望 3 原文「**隊ドリルダウンに各隊月予算入力 UI 追加 (統括隊予算との整合性チェック付き)**」を文字通り達成するには手打ち入力できる UI が必須。よって team_budgets を主データ層とし、1b/2 は派生的に解消する形に確定 (brainstorm Phase 3 質問 #1 再選択)。

---

## 2. 確定済み設計判断 (2026-06-13 brainstorm セッション)

| 論点 | 採択案 | 根拠 |
|---|---|---|
| データ層 | `team_budgets` を主データ、隊×月予算を本田様が手打ち入力 | 要望 3 原文 (Codex 指摘なし) |
| 入力 UI 位置 | 隊ドリルダウンタブの「集計」セクション直下にインライン編集 | 要望 3 原文「隊ドリルダウンに」、実額との横並び |
| 編集 scope | (year, month, team) 1 単位 | ドリルダウンが (year, month, team) スコープと整合 |
| 認可 | admin ロール専用 (編集は admin のみ、user/checker は閲覧のみ) | 既存 admin 系ページパターン踏襲 (team_hierarchy_settings.py / user_management.py) |
| WRITE 経路 | dashboard 直接 BQ MERGE (cloud-run 中継なし) | 既存 admin 系ページ全て直 MERGE。Codex 指摘 a (前提明文化要) を反映 |
| 楽観ロック | `lib/team_budget_repo.py` 新規作成、UPDATE-only + INSERT 分離 | Codex 指摘 c。upload_budgets.py 流用は新規 INSERT 競合で上書き発生のため不採用 |
| 削除 semantics | Phase 1 は row DELETE (NUMERIC NOT NULL 制約のため) | Codex 指摘 b。soft delete (deleted_at/deleted_by 列追加) は follow-up |
| 超過防止 | ソフトブロック (超過時のみ確認ダイアログ + 続行可、UI 常時残額表示) | 本田様「超過させないように」指示 + brainstorm Phase 5 再選択 |
| 統括隊予算 None 時 | 保存禁止 + 「先に統括隊四半期予算を投入」誘導 | Codex 指摘 g |
| プリフィル | しない (未入力は空欄 / NULL) | brainstorm Phase 3 質問 #3、表示と保存状態の混同を防ぐ |
| AI 評価への反映 | `actual_data_hash` に budget_amount と prompt_version を含める形に migration | Codex 指摘 e、「追加実装ゼロ」では予算変更が再生成 trigger にならないため |
| 1b/2 のロジック改修 | なし。team_budgets 入力で自動解消 | データフローは v_team_budget_actuals → load_team_budget_actuals → build_monthly_trend / build_matrix_df、既存パスで成立 |
| team selectbox の範囲 | 既存 `load_active_teams` 流用 (VIEW INNER JOIN で operating 配下に限定済) | Codex 指摘 i、新規対応不要 |
| 整合性監査 | Phase 1 では `team_budget_audit_log` 等の専用 audit 不要 | Codex 指摘 k。`updated_by` で当面しのぐ。削除時は `"delete:" + actor` の pseudo-tag |
| 他隊合計 cache | TTL 60s、保存直前は再取得必須 | Codex 指摘 f、cache 信用しないことで race を最小化 |

---

## 3. アーキテクチャ

### 3.1 依存方向

```
dashboard/_pages/team_budget.py (UI、admin 判定)
  └─> dashboard/lib/team_budget_repo.py (新規、MERGE 書き込み + 楽観ロック)
        └─> google.cloud.bigquery (既存共有 client)

cloud-run/vertex_evaluator.py (compute_actual_data_hash 修正)
cloud-run/team_eval_service.py (hash 計算経路に budget_amount 渡す)
dashboard/lib/bq_client.py (compute_current_hashes 同等修正)

scripts/upload_budgets.py (既存 CSV upload)
  └─> 本 PR では touch しない (DRY 共有化は follow-up PR)
```

Phase 1 では `team_budget_repo.py` を新規作成し dashboard だけが使用。`upload_budgets.py` の同等ロジック共有化は follow-up (CRITICAL「変更を要求された範囲のみ」に従い scope creep 回避)。

### 3.2 データフロー (write 経路)

```
本田様 (admin) が隊ドリルダウンで予算入力
  → dashboard/_pages/team_budget.py の編集セクション
    → 保存直前に load_other_team_budgets_in_leader で他隊合計再取得
    → 超過判定 → 必要なら confirm ダイアログ
    → upsert_team_budget (UPDATE or INSERT)
      → BigQuery team_budgets テーブル更新
    → invalidate_team_budget_caches で cache 一括 clear
    → st.rerun() で再描画
```

### 3.3 データフロー (AI 評価への反映)

```
本田様が隊ドリルダウンで「AI 評価更新」ボタンを押下
  → cloud-run/team_eval_service.py
    → load_team_aggregate (v_team_budget_actuals から budget_amount 含む取得)
    → compute_actual_data_hash(actual, top, samples, budget, prompt_version)
      → 既存 team_monthly_eval.actual_data_hash と比較
        → 不一致 (予算変わったため hash 異なる) → 再生成 trigger
        → Gemini プロンプトに新 budget が乗る
```

---

## 4. データモデル

### 4.1 team_budgets (既存スキーマそのまま使用)

```sql
CREATE TABLE `monthly-pay-tax.pay_reports.team_budgets` (
  year INT64 NOT NULL,
  month INT64 NOT NULL,
  team STRING NOT NULL,
  budget_amount NUMERIC NOT NULL,    -- 0 は許容、削除は row DELETE
  memo STRING,
  version INT64 NOT NULL,             -- 楽観ロック、UPDATE で +1
  created_at TIMESTAMP NOT NULL,
  created_by STRING NOT NULL,         -- email or "script:upload_budgets:<email>"
  updated_at TIMESTAMP NOT NULL,
  updated_by STRING NOT NULL          -- email、削除時は "delete:<email>" (pseudo-tag)
)
PARTITION BY DATE(updated_at)
CLUSTER BY year, month, team;
```

**変更なし** (本 PR ではスキーマ変更しない)。soft delete (`deleted_at`, `deleted_by` 列追加) は follow-up PR。

### 4.2 actual_data_hash 変更 (cloud-run + dashboard)

**実装上の前提（Step 0 grep で判明、当初案を訂正）**: 既存の `compute_actual_data_hash` / `compute_current_hashes` は **BQ SQL 内で hash 計算が完結**しており、Python 側は SQL を発行して結果を受け取るだけ。当初案の「Python で `json.dumps({...budget...})`」アプローチは実装と乖離するため不採用。

**修正後の方針**: 既存 SQL は touch せず、**Python 側で composite hash を合成**する形に変更。

| 場所 | 変更内容 |
|---|---|
| `cloud-run/vertex_evaluator.py:compute_actual_data_hash()` | シグネチャ不変 `(bq_client, year, month, team) -> str`。内部で既存 BQ hash を取得後、team_budgets から budget を SELECT、共通 helper `compose_actual_data_hash(bq_hash, budget, prompt_version)` で合成して返す |
| `cloud-run/team_eval_service.py` | hash 計算経路は既存呼び出しのまま、戻り値 hash の意味が「actual + budget + prompt_version」に変わる |
| `dashboard/lib/bq_client.py:compute_current_hashes()` | シグネチャ不変 `(year, month, teams) -> dict`。内部で既存 BQ hash dict 取得後、各 team の budget を別 SELECT、共通 helper で合成 |
| `lib/team_budget_hash.py` (新規) | 共通 helper `compose_actual_data_hash(bq_hash, budget_amount, prompt_version) -> str`。cloud-run と dashboard 両方で同一実装、contract test 共有で同期検証 |

**Decimal/NUMERIC 正規化** (Codex 指摘 j): budget_amount は `str(Decimal(value))` で正規化、`None` は文字列 `"null"` に統一。合成方式: `SHA256(f"{bq_hash}|{budget_norm}|{prompt_version}")` を hex 化。

**利点**:
- 既存 SQL を touch しないため `test_vertex_evaluator` の 5 件と `test_lib_bq_client_team_budget` の hash 値 assert 6 件が破壊されない
- Python composite が pure function なため unit test しやすい
- 両側 (cloud-run / dashboard) で同じ helper を物理的に共有はできないが、contract test fixture (`tests/fixtures/hash_contract.py`) を両側で import して同入力同出力を検証

**マイグレーション戦略**: 既存 team_monthly_eval の actual_data_hash は変更しない。新ロジックで計算した hash が既存 hash と一致しなくなるため、既存隊は全て「outdated」バッジが付く。本田様が順次「更新」ボタンを押して再生成する運用 (β / α 案を兼ねる)。

### 4.3 セル状態の解釈

| 状態 | budget_amount | 表示 | 操作可能 |
|---|---|---|---|
| 未設定 | row 不在 | 「予算未設定」 | 保存 (新規 INSERT) |
| 設定済み | row 存在、`>= 0` | 「¥X」+ memo + version | 保存 (UPDATE) / 削除 |
| 削除中 | UI 上 confirm 表示中 | 「削除しますか？」 | 「削除する」 / 「キャンセル」 |

---

## 5. インターフェース

### 5.1 lib/team_budget_repo.py 公開 API

```python
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

@dataclass(frozen=True)
class TeamBudgetRow:
    year: int
    month: int
    team: str
    budget_amount: float
    memo: Optional[str]
    version: int
    updated_at: datetime
    updated_by: str

class UpsertConflict(Exception):
    """楽観ロック競合 (UPDATE/DELETE で affected_rows=0、または INSERT 競合)"""

def load_team_budget(client, year: int, month: int, team: str) -> Optional[TeamBudgetRow]:
    """1 row 取得。存在しなければ None"""

def upsert_team_budget(
    client, *, year: int, month: int, team: str,
    budget_amount: float, memo: Optional[str],
    expected_version: Optional[int], actor: str,
) -> TeamBudgetRow:
    """expected_version=None → 新規 INSERT (既存行があれば conflict)
    expected_version=N → UPDATE WHERE version=N (不一致なら conflict)
    成功時は新 version 付き TeamBudgetRow"""

def delete_team_budget(
    client, *, year: int, month: int, team: str,
    expected_version: int, actor: str,
) -> None:
    """DELETE WHERE version=expected_version。conflict 時 UpsertConflict"""

def load_other_team_budgets_in_leader(
    client, *, year: int, month: int, leader_team: str, exclude_team: str,
) -> float:
    """超過判定用、operating 配下の同月予算合計 (exclude_team を除く)"""
```

### 5.2 dashboard UI (隊ドリルダウンタブ拡張)

挿入位置: 「集計」と「AI 評価コメント」の間。

```python
if is_admin:
    st.markdown("### 月予算編集")

    current_row = load_team_budget_cached(year, month, team)
    leader = _infer_leader_team(actuals_month, team)
    leader_monthly_budget = leader_team_monthly_budgets.get(leader)
    other_total = load_other_team_budgets_cached(year, month, leader, team)
    remaining = (
        leader_monthly_budget - other_total
        if leader_monthly_budget is not None else None
    )

    _render_budget_reference(leader, leader_monthly_budget, other_total, remaining)

    if leader_monthly_budget is None:
        st.warning(
            "⚠ 統括隊「{leader}」の四半期予算が未投入です。"
            "先に統括隊四半期予算を投入してください。"
        )
        # 保存ボタン disabled
    else:
        new_amount = st.number_input(
            "予算金額", min_value=0, step=10000,
            value=int(current_row.budget_amount) if current_row else 0,
            key=f"tb_edit_amount_{year}_{month}_{team}",
        )
        new_memo = st.text_input("メモ (任意)", max_chars=255, ...)
        col_save, col_del = st.columns(2)
        col_save.button("保存", on_click=_on_save_click, ...)
        if current_row:
            col_del.button("予算削除", on_click=_on_delete_click, ...)

    # confirm 系 (超過 / 削除) の表示
    _render_overflow_dialog_if_pending(...)
    _render_delete_dialog_if_pending(...)
```

### 5.3 共通 hash 合成 helper (新規、cloud-run + dashboard 双方に配置)

```python
# 配置候補: cloud-run/team_budget_hash.py + dashboard/lib/team_budget_hash.py
# (両側に同一実装を置き、contract test fixture を tests/fixtures/hash_contract.py で共有)

import hashlib
from decimal import Decimal
from typing import Optional, Union

def compose_actual_data_hash(
    bq_hash: str,
    budget_amount: Optional[Union[Decimal, float, int]],
    prompt_version: str,
) -> str:
    """既存 BQ hash と budget + prompt_version を合成して outdated 判定 hash を生成。

    BQ SQL 側の hash 計算 (gyomu_reports 集計) は touch せず、Python 側で
    budget と prompt_version を追加して composite hash を作る。

    Args:
        bq_hash: 既存 compute_actual_data_hash の SQL 戻り値 (空文字許容、
                 IFNULL(..., '') で "データなし" を表現)
        budget_amount: team_budgets.budget_amount。None は "null" 文字列に正規化、
                       Decimal/float/int は str(Decimal(value)) で正規化
        prompt_version: vertex_evaluator.PROMPT_VERSION 等

    Returns:
        hex digest (64 文字)
    """
    if budget_amount is None:
        budget_norm = "null"
    else:
        budget_norm = str(Decimal(str(budget_amount)))
    composite = f"{bq_hash}|{budget_norm}|{prompt_version}"
    return hashlib.sha256(composite.encode("utf-8")).hexdigest()
```

Contract test fixture (両側で import):

```python
# tests/fixtures/hash_contract.py
HASH_CONTRACT_CASES = [
    # (bq_hash, budget_amount, prompt_version, expected_hex)
    ("", None, "v1", "..."),                    # データなし + 予算なし
    ("abc123", None, "v1", "..."),              # 実額あり + 予算なし
    ("abc123", Decimal("1000"), "v1", "..."),   # 実額あり + 予算 (Decimal)
    ("abc123", 1000.0, "v1", "..."),            # float 入力でも同 hash
    ("abc123", 1000, "v1", "..."),              # int 入力でも同 hash
    ("abc123", Decimal("1000"), "v2", "..."),   # prompt_version 違いで異 hash
]
```

両側の compose_actual_data_hash がこの fixture を通すことで cross-side consistency を保証する (Codex 指摘 a / g 反映)。

### 5.4 cache invalidation 集約関数

```python
def invalidate_team_budget_caches():
    """team_budgets DML 後に呼ぶ。Codex 指摘 j 対応の一箇所集約"""
    for fn in (
        load_team_budget,
        load_team_budget_actuals,
        load_active_teams,
        load_active_leader_teams,
        load_team_monthly_eval,
        compute_current_hashes,
        load_other_team_budgets_in_leader,
        load_leader_team_monthly_budgets,
    ):
        try:
            fn.clear()
        except AttributeError:
            pass
```

---

## 6. エラー処理

### 6.1 入力 validation

| 項目 | ルール | 違反時 |
|---|---|---|
| budget_amount 型 | 数値 | UI で型保証 |
| budget_amount 範囲 | `>= 0` | `st.number_input(min_value=0)` |
| budget_amount 上限 | なし | チェックなし |
| memo 長さ | 255 文字以下 | `max_chars=255` |
| year, month, team | session_state 固定値 | UI で違反不可 |

### 6.2 統括隊予算 None 時

保存ボタン disabled + warning 表示 (本田様が先に四半期予算を投入する運用に誘導)。

### 6.3 超過時のソフトブロック (session_state 2 段押下)

```
1. 保存ボタン押下 → load_other_team_budgets_in_leader 再取得
2. is_overflow = (other_total + new_amount > leader_monthly_budget)
3. is_overflow かつ未確認 → session_state["tb_overflow_pending"] = {...} → rerun
4. confirm ダイアログ表示「¥X 超過します。続行?」
5. 「続行」→ session_state["tb_overflow_confirmed"] = True → 再保存実行
6. 「キャンセル」→ session_state pending クリア
```

### 6.4 楽観ロック競合 (UpsertConflict)

```
upsert_team_budget / delete_team_budget で affected_rows=0
  → UpsertConflict raise
  → UI: st.error("他の管理者が同時編集中の可能性があります。画面を更新してください")
  → 「画面を更新」ボタン → invalidate caches + st.rerun()
```

### 6.5 BQ write error (network / permission 等)

```
except Exception as exc:
    logger.exception("team_budget save failed")
    st.error(f"保存失敗: {exc}")
```

### 6.6 削除確認 (session_state 2 段押下)

confirm ダイアログ「予算 ¥X を削除しますか?」→「削除する」/「キャンセル」。

### 6.7 AI 評価コメント再生成の促進

予算変更 detect 時:
```python
if previous_budget != new_amount:
    st.info("💡 予算が変更されたため、AI 評価コメントの再生成を推奨します")
```

---

## 7. テスト戦略

### 7.1 カバー対象

| ファイル | カバー | 件数想定 |
|---|---|---|
| `dashboard/tests/test_lib_team_budget_repo.py` (新規) | load / upsert insert / upsert update / delete / load_other / UpsertConflict / actor 記録 | ~24 |
| `dashboard/tests/test_pages_team_budget.py` (拡張) | admin 編集 UI / user 非表示 / 統括隊予算 None / 超過判定 / 2 段押下 / 削除 / cache invalidate | ~16 |
| `cloud-run/tests/test_vertex_evaluator.py` (拡張) | compute_actual_data_hash の budget_amount 反映 / 同一入力同一 hash / budget 違いで差分 | ~5 |
| `cloud-run/tests/test_team_eval_service.py` (拡張) | budget_amount を hash に渡す経路 / hash 不一致時の再生成 | ~3 |
| `dashboard/tests/test_lib_bq_client.py` (拡張) | compute_current_hashes の同等修正 | ~2 |

### 7.2 方針

- BQ は MagicMock、`@st.cache_data` は `clear()` でリセット
- `st.session_state` テストは既存 `test_pages_team_budget.py` 手法流用
- 楽観ロック競合は `affected_rows=0` mock で再現
- 統括隊予算 None ケースは `load_leader_team_monthly_budgets` empty DataFrame mock
- 超過判定の boundary: 残額 ¥0 ちょうど / +¥1 を fixture で網羅

### 7.3 Acceptance Criteria

| AC | 基準 | 検証方法 |
|---|---|---|
| AC1 | admin role で隊ドリルダウンに「月予算編集」セクション表示 | unit test (`is_admin=True`) |
| AC2 | user/checker role では「月予算編集」非表示 | unit test (`is_admin=False`) |
| AC3 | 統括隊月予算 None 時、保存ボタン disabled + warning | unit test (空 fixture) |
| AC4 | 入力値 + 他隊合計 ≤ 統括隊月予算 → 直接保存 | unit test (boundary fixture) |
| AC5 | 超過時 → confirm 表示 →「続行」で保存、「キャンセル」で cancel | unit test (overflow + confirm flow) |
| AC6 | save 成功時、team_budgets に正しい row が MERGE される (全列) | unit test (mock client calls 検証) |
| AC7 | 楽観ロック競合時、error + 「画面を更新」ボタン表示 | unit test (mock affected_rows=0) |
| AC8 | save 成功時、関連 cache が clear される | unit test (mock `.clear()` 呼び出し) |
| AC9 | 削除ボタンで row DELETE、確認ダイアログ経由 | unit test (delete flow + confirm) |
| AC10 | compute_actual_data_hash が budget_amount を入力に含む | unit test (異 budget で hash 差) |
| AC11 | team_eval_service が hash 計算時に budget_amount を渡す | unit test (mock chain 検証) |
| AC12 | 予算変更後、AI 評価「更新」で再生成される (skip されない) | integration test (mock vertex 経由) |
| AC13 | 1b: team_budgets 入力後、月次推移グラフの予算ライン ≠ ¥0 | integration smoke test (fixture 投入 → DataFrame 検証) |
| AC14 | 2: team_budgets 入力後、隊マトリクスで達成率が計算される | integration smoke test (fixture 投入 → matrix 検証) |
| AC15 | 連続操作 (cache miss なし) でも正しい状態 | unit test (TTL 経過なし連続操作) |
| AC16 | 既存 458 テストの非破壊 (CI green) | CI 自動 |

---

## 8. スコープ外 (本 PR ではやらない)

1. **scripts/upload_budgets.py の team_budget_repo 共有化**: refactor 抑制 (本 PR scope creep 回避)、follow-up PR
2. **team_budget_audit_log (Codex 指摘 k)**: 専用 audit テーブル新設は不要、`updated_by` で当面しのぐ
3. **soft delete (deleted_at / deleted_by 列追加)**: row DELETE で十分、必要になったら follow-up
4. **一括編集 UI (隊×月マトリクス UI)**: brainstorm Phase 3 質問 #1 (再) で「隊ドリルダウンインライン編集のみ」確定
5. **要望 4 (隊ドリルダウン業務報告詳細強化)**: Issue #245 postponed、別セッション
6. **ハード超過防止 (BigQuery multi-statement transaction)**: ソフトブロックで十分 (Codex 指摘 l)
7. **既存 team_monthly_eval 行の actual_data_hash 一括 NULL 化 migration**: 既存 hash と新 hash が不一致なら自動 outdated 判定、明示 NULL 化は不要

---

## 9. Open Questions (未解決事項)

なし。brainstorm Phase 1〜5 で全主要論点を確定済み (Codex セカンドオピニオン a〜l も反映済)。

---

## 10. 段階的実装 (single PR 想定、3-5 commit に分割)

| commit | 内容 |
|---|---|
| 1 | 設計文書 (本 PR の本ファイル) ※本 commit でこの spec が入る |
| 2 | lib/team_budget_repo.py 新規 + test_lib_team_budget_repo.py (~24 件) |
| 3 | cloud-run/vertex_evaluator.py + team_eval_service.py の actual_data_hash 修正 + 関連 test (~8 件) |
| 4 | dashboard/lib/bq_client.py compute_current_hashes 修正 + test (~2 件) |
| 5 | dashboard/_pages/team_budget.py 隊ドリルダウン編集 UI + test_pages_team_budget.py (~16 件) |

CLAUDE.md CRITICAL: 5 ファイル以上 + 新機能 + アーキテクチャ影響に該当するため `rules/quality-gate.md` Evaluator 分離プロトコル必須。

---

## 11. デプロイ手順

CI/CD (ADR-0006) で自動デプロイ。手動デプロイは不要。

**注意**: `cloud-run/vertex_evaluator.py` と `dashboard/lib/bq_client.py` を同一 PR で同時にデプロイすること。片方のみデプロイ → hash 不一致が生じ、本田様 UI から見て全隊 outdated 表示が一時的に固定化する。

---

## 12. ロールバック手順

1. **dashboard rollback**: `gcloud run services update-traffic pay-dashboard --to-revisions=<previous>=100`
2. **cloud-run rollback**: 同様に pay-collector を直前 revision に
3. **BQ team_budgets テーブル**: Step 0 snapshot バックアップ (pay_reports_backup) から復元可

---

## 13. 関連 PR / Issue

- Issue #244 (本 PR scope、1b/2/3 クラスタ)
- Issue #245 (要望 4、postponed、follow-up セッション)
- PR #209-#213 (PR-A〜D)
- PR #214-#218 (PR-E/F)
- PR #222-#227 (2026-06-11/12 バグ修正)
- PR #229-#231 (統括隊ベース再構成 PR-A/B)
- 本 PR (隊×月予算入力 UI + AI 評価 hash 拡張)
