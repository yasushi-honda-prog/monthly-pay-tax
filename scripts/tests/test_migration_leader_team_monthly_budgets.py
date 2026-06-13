"""migration 2026-06-14_leader_team_monthly_budgets.sql の構造検証テスト (Issue #248 T2)。

BQ emulator なしで SQL 自体の構造的妥当性を機械検証する:
- CREATE TABLE IF NOT EXISTS で leader_team_monthly_budgets を作成
- MERGE で WHEN NOT MATCHED THEN INSERT のみ (WHEN MATCHED なし = 冪等性)
- fiscal_quarter→month マッピング Q1=[11,12,1] Q2=[2,3,4] Q3=[5,6,7] Q4=[8,9,10]
- fiscal_year=2026 で seed
- CAST AS NUMERIC + SAFE_DIVIDE で端数対応

冪等性の本番実機検証は migration apply 時に手動 2 回実行で確認 (Codex R3 緩和策)。

設計: docs/specs/2026-06-14-leader-team-monthly-budget.md §4.2 / AC1 / AC12
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

_MIGRATION_PATH = (
    Path(__file__).resolve().parents[2]
    / "infra"
    / "bigquery"
    / "migrations"
    / "2026-06-14_leader_team_monthly_budgets.sql"
)


@pytest.fixture(scope="module")
def sql_text() -> str:
    """migration SQL の全文を読み込む。"""
    return _MIGRATION_PATH.read_text(encoding="utf-8")


class TestMigrationFileExists:
    def test_file_exists(self):
        assert _MIGRATION_PATH.exists(), f"Migration file not found: {_MIGRATION_PATH}"


class TestCreateTable:
    """CREATE TABLE 句の構造検証。"""

    def test_create_table_if_not_exists(self, sql_text: str):
        """idempotent な CREATE TABLE IF NOT EXISTS で作成すること。"""
        assert "CREATE TABLE IF NOT EXISTS" in sql_text

    def test_table_name(self, sql_text: str):
        """テーブル名 leader_team_monthly_budgets。"""
        assert "leader_team_monthly_budgets" in sql_text

    def test_has_required_columns(self, sql_text: str):
        """必須列 (fiscal_year, month, leader_team, budget_amount, version, audit cols)。"""
        required = [
            "fiscal_year",
            "month",
            "leader_team",
            "budget_amount",
            "version",
            "created_at",
            "created_by",
            "updated_at",
            "updated_by",
        ]
        for col in required:
            assert col in sql_text, f"Missing column: {col}"

    def test_cluster_by_fiscal_year_leader_team(self, sql_text: str):
        """CLUSTER BY fiscal_year, leader_team で fetch_yearly 効率化。"""
        assert re.search(r"CLUSTER BY\s+fiscal_year\s*,\s*leader_team", sql_text)

    def test_no_partition_by(self, sql_text: str):
        """1 fiscal_year あたり 72 行のみのため partition なし (設計判断)。"""
        assert "PARTITION BY" not in sql_text

    def test_budget_amount_is_numeric(self, sql_text: str):
        """budget_amount は NUMERIC (既存 team_budgets と統一)。"""
        assert re.search(r"budget_amount\s+NUMERIC", sql_text)


class TestSeedMerge:
    """seed MERGE の冪等性検証 (Codex H2 反映)。"""

    def test_uses_merge_not_unconditional_insert(self, sql_text: str):
        """MERGE で seed (UNCONDITIONAL INSERT は使わない)。"""
        assert "MERGE" in sql_text

    def test_has_when_not_matched_insert(self, sql_text: str):
        """WHEN NOT MATCHED THEN INSERT で新規 row のみ挿入。"""
        assert re.search(r"WHEN NOT MATCHED\s+THEN INSERT", sql_text)

    def test_no_when_matched_clause(self, sql_text: str):
        """WHEN MATCHED は意図的に省略 (再実行で既存値を上書きしない、冪等)。"""
        # 「WHEN MATCHED」が無いことを厳密にチェック
        # コメント行除外のため、SQL の executable 部分のみ抽出
        executable_lines = [
            line
            for line in sql_text.splitlines()
            if not line.strip().startswith("--")
        ]
        executable_sql = "\n".join(executable_lines)
        assert "WHEN MATCHED" not in executable_sql, (
            "WHEN MATCHED clause found, but seed must be idempotent (insert-only)"
        )

    def test_merge_on_pk_columns(self, sql_text: str):
        """ON 句で (fiscal_year, month, leader_team) の 3 列マッチ。"""
        assert re.search(r"T\.fiscal_year\s*=\s*S\.fiscal_year", sql_text)
        assert re.search(r"T\.month\s*=\s*S\.month", sql_text)
        assert re.search(r"T\.leader_team\s*=\s*S\.leader_team", sql_text)


class TestFiscalQuarterMapping:
    """fiscal_quarter→month マッピングが BQ fiscal_quarter UDF と整合。"""

    def test_q1_months(self, sql_text: str):
        """Q1: 11, 12, 1 月。"""
        assert re.search(r"WHEN 1 THEN \[\s*11\s*,\s*12\s*,\s*1\s*\]", sql_text)

    def test_q2_months(self, sql_text: str):
        """Q2: 2, 3, 4 月。"""
        assert re.search(r"WHEN 2 THEN \[\s*2\s*,\s*3\s*,\s*4\s*\]", sql_text)

    def test_q3_months(self, sql_text: str):
        """Q3: 5, 6, 7 月。"""
        assert re.search(r"WHEN 3 THEN \[\s*5\s*,\s*6\s*,\s*7\s*\]", sql_text)

    def test_q4_months(self, sql_text: str):
        """Q4: 8, 9, 10 月。"""
        assert re.search(r"WHEN 4 THEN \[\s*8\s*,\s*9\s*,\s*10\s*\]", sql_text)


class TestSeedSource:
    """seed 元データの参照と fiscal_year=2026 限定。"""

    def test_references_team_budgets_quarterly(self, sql_text: str):
        """seed 元は team_budgets_quarterly。"""
        assert "team_budgets_quarterly" in sql_text

    def test_filter_fiscal_year_2026(self, sql_text: str):
        """seed 対象は fiscal_year=2026 のみ。"""
        assert re.search(r"WHERE\s+q\.fiscal_year\s*=\s*2026", sql_text)

    def test_safe_divide_by_3(self, sql_text: str):
        """budget_amount は SAFE_DIVIDE(SUM(...), 3) で四半期÷3。"""
        assert re.search(r"SAFE_DIVIDE\(\s*SUM\(q\.budget_amount\)\s*,\s*3\s*\)", sql_text)

    def test_cast_to_numeric(self, sql_text: str):
        """CAST AS NUMERIC で型統一 (Codex R9 端数対応)。"""
        assert re.search(r"CAST\(SAFE_DIVIDE.*AS NUMERIC\)", sql_text)


class TestAuditMetadata:
    """seed row の audit 列が migration 識別子で記録される。"""

    def test_seed_created_by_migration_tag(self, sql_text: str):
        """created_by に migration タグ。"""
        assert "'migration@2026-06-14'" in sql_text

    def test_seed_version_initial(self, sql_text: str):
        """seed row の version は 1 から開始。"""
        # INSERT 句の VALUES に 1 が含まれる
        assert re.search(r"VALUES\s*\(.*,\s*1\s*,", sql_text, flags=re.DOTALL)
