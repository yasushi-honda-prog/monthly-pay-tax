# 予実管理機能 PR-E 設計仕様書 (四半期 × 統括隊 × カテゴリ予算)

**作成日**: 2026-06-11
**前提**: PR #209 (spec) / #210-#213 (PR-A〜PR-D) の延長線上。本 doc は **Phase 2** の BQ 基盤 + 投入 script のみを定義。dashboard UI 統合・AI 評価エンジンの統括隊レベル対応は Phase 3 以降の別 PR。
**ステータス**: Phase 1 実装範囲のみ確定 (本 PR で完結)

---

## 1. 背景

PR-A〜D で実装した予実管理機能は **隊 (`activity_category`) × 月** 粒度の月別予算。一方、運用上は以下の管理ニーズがある:

1. **四半期予算サイクル**: 月次よりも四半期で予算編成・実績振り返りを行う
2. **統括隊レイヤー**: 複数の隊を束ねる統括隊 (6 つ) で集約管理
3. **支出カテゴリ別管理**: 業務委託費だけでなく旅費・消耗品・通信・広告・自由枠・共通費の 7 カテゴリで予算編成

本 PR (PR-E) は上記 3 軸を満たす BQ 基盤を構築する。**実額紐付けは Phase 1 では "タダメン業務委託費" のみ**で、他 6 カテゴリは予算のみ表示。

---

## 2. 確定済み設計判断 (2026-06-10 セッション)

| 論点 | 採択案 | 根拠 |
|---|---|---|
| 取り込み粒度 | **案 A**: 四半期×統括隊×カテゴリをそのまま保持 (新規テーブル `team_budgets_quarterly`) | シートと 1:1、既存 `team_budgets` (月別) と並存 |
| 統括隊↔隊マッピング | **案 X**: 新規テーブル `team_hierarchy` | activity_category と leader_team の階層を CSV で投入 |
| 自由に使える10万円 / 共通費 | **案 P**: 6 カテゴリと同じレベルでテーブル格納 | Phase 1 は予算のみ表示、実額紐付けは Phase 2 |
| 会計年度 | **案 N11**: 11 月始まり (Q1=11-1月 / Q2=2-4月 / Q3=5-7月 / Q4=8-10月) | 画像「第3Q (5-7月)」と一致 |
| 階層の時系列 | **案 T-NOW**: 現在値のみ保持 | 最小実装、組織再編は schema migration で対応 |

---

## 3. BQ スキーマ

### 3.1 fiscal_quarter UDF (案 N11)

```sql
CREATE OR REPLACE FUNCTION fiscal_quarter(year INT64, month INT64)
AS (
  STRUCT(
    IF(month >= 11, year + 1, year) AS fiscal_year,
    1 + DIV(MOD(month - 11 + 12, 12), 3) AS fiscal_quarter
  )
);
```

**fiscal_year の整列規則**: 終了月 (10月) の暦年に揃える。
- 暦 2025-11 〜 2026-10 → FY2026
- 暦 2026-11 〜 2027-10 → FY2027

### 3.2 expense_categories テーブル (7 行 seed)

| sort | expense_category | actual_source | is_phase1_supported |
|---|---|---|---|
| 1 | タダメン業務委託費 | `gyomu` | TRUE |
| 2 | 旅費交通費 | `reimbursement` | FALSE |
| 3 | 消耗品費 | `reimbursement` | FALSE |
| 4 | 通信運搬費 | `reimbursement` | FALSE |
| 5 | 広告宣伝費 | `reimbursement` | FALSE |
| 6 | 自由に使える10万円 | `none` | FALSE |
| 7 | 共通費 | `none` | FALSE |

Codex Medium-6 反映: typo 防止のため `team_budgets_quarterly.expense_category` は本テーブルと JOIN 検証 (script 内で実装)。

### 3.3 team_hierarchy テーブル

- PK: `activity_category` (gyomu_reports.activity_category と同一値)
- `leader_team`: 統括隊名 (例: シロロ+ゆずるん統括隊)
- `leader_team_type`: 'operating' (通常統括隊) / 'common' (共通枠の virtual)
- `version`: optimistic lock

Codex High-2 反映: 案 T-NOW で「現在値のみ」前提なので PK 単独で許容。組織再編時は手動 schema migration。

### 3.4 team_budgets_quarterly テーブル

- PK: `(fiscal_year, fiscal_quarter, leader_team, expense_category)`
- `budget_amount`: NUMERIC
- `version`: optimistic lock
- Partition: DATE(updated_at) / Cluster: (fiscal_year, fiscal_quarter, leader_team)

Codex Medium-4 反映: 既存 `team_budgets` (隊×月) と粒度差を schema コメントで明示。

### 3.5 v_team_budget_actuals_quarterly VIEW

予実集計の中核 VIEW。`actual_mapping_status` で 4 状態を区別:

| status | 意味 |
|---|---|
| `mapped` | Phase 1 対応カテゴリ + 予算あり + 実額あり |
| `no_actual_rows` | Phase 1 対応カテゴリ + 予算あり + 実額 0 件 |
| `not_supported_in_phase1` | Phase 2 以降対応カテゴリ (予算のみ表示) |
| `budget_missing` | 実額あり + 予算未設定 |

Codex High-3 反映: NULL と Phase1 未対応を明示的に区別。

### 3.6 v_team_hierarchy_coverage VIEW

`gyomu_reports.activity_category` の出現と `team_hierarchy` 定義の差分:

| status | 意味 | 対応 |
|---|---|---|
| `MAPPED` | 両方あり | OK |
| `UNMAPPED` | gyomu 出現するが hierarchy 未定義 | hierarchy CSV を更新 |
| `UNUSED` | hierarchy 定義あるが gyomu 出現なし | 組織変更の名残、放置可 |

Codex Medium-5 反映: hierarchy 再アップロード時に隊が漏れたら本 VIEW で検知。

---

## 4. 投入 script

### 4.1 scripts/upload_team_hierarchy.py

- CSV (`activity_category,leader_team,leader_team_type,note`) を `team_hierarchy` に MERGE
- `--check-coverage` で UNMAPPED 隊を warn
- optimistic lock, `--force`, `--dry-run`, `--yes` は PR-A の upload_budgets.py 踏襲

### 4.2 scripts/upload_team_budgets_quarterly.py

- **2 形式自動判別** (Codex Medium-7 反映):
  - **long** 形式: `fiscal_year,fiscal_quarter,leader_team,expense_category,budget_amount,memo`
  - **matrix** 形式: 1 列目 = leader_team, 2 列目以降 = expense_category (画像通り)
- matrix 形式は `--fiscal-year` / `--fiscal-quarter` 必須
- `--expected-total` で投入合計の検算 (画像 23,457,444 と照合、不一致は warn のみ)
- `expense_categories` マスタと JOIN で typo 検知 (`--no-validate-categories` で skip 可)
- '計' / '合計' / 'total' / 'sum' 行は自動スキップ (検算用と判断)
- カンマ区切り数値 (例: `"5,289,363"`) の自動変換

---

## 5. テスト

| ファイル | カバー範囲 | テスト数 |
|---|---|---|
| `scripts/tests/test_upload_team_hierarchy.py` | parse_csv + validation + preview + merge + coverage + actor | 24 |
| `scripts/tests/test_upload_team_budgets_quarterly.py` | format detect + long/matrix parse + 全 validation + dispatch + preview + merge | 34 |

BQ client は MagicMock で差し替え (踏襲元: `test_upload_budgets.py`)。

---

## 6. Definition of Done

- [x] BQ migration SQL (UDF + 3 テーブル + 2 VIEW + seed) 作成
- [x] schema.sql / views.sql / cloud-run/config.py に反映 (snapshot 対象拡張)
- [x] 2 script + テスト 58 件追加
- [x] CSV テンプレート 2 つ + 投入手順 doc
- [x] CLAUDE.md 反映
- [ ] 本田さんが画像の数値を CSV に書いて `python3 scripts/upload_team_budgets_quarterly.py budgets_q3_2026.csv --fiscal-year 2026 --fiscal-quarter 3` で BQ に投入できる (本番投入は別タイミング)
- [ ] Evaluator/Codex/Agent 3 並列セカンドオピニオン → 必須修正反映

---

## 7. Phase 2 以降に送る項目 (本 PR ではやらない)

1. **立替金 → expense_category マッピング**: reimbursement_items.category を expense_category へマッピング (旅費/消耗品/通信/広告)
2. **自由10万・共通費の実額紐付け仕様**: 利用追跡方法・本部費按分ロジックの仕様確認
3. **dashboard UI 拡張**: 四半期×統括隊×カテゴリの可視化 (既存予実管理ページとの統合方針)
4. **AI 評価エンジンの統括隊レベル対応**: Gemini プロンプトを統括隊レベルで生成、Q ごとに評価コメント

---

## 8. 関連リソース

- 設計母体: `docs/specs/2026-06-10-team-budget-eval-design.md` (Phase 1)
- 投入手順: `docs/operations/20260611_四半期予算投入手順.md`
- CSV テンプレ:
  - `docs/operations/team-hierarchy-template.csv`
  - `docs/operations/team-budgets-quarterly-template-matrix.csv`
  - `docs/operations/team-budgets-quarterly-template-long.csv`
- migration: `infra/bigquery/migrations/2026-06-11_quarterly_budgets.sql`
