"""隊×月予算 (team_budgets) の DML repository。

設計: docs/specs/2026-06-13-team-monthly-budget-input.md

dashboard から admin 限定で team_budgets を編集する UI 用のリポジトリ層。
既存 scripts/upload_budgets.py の MERGE ロジックとは別系統 (Codex 指摘 c:
upload_budgets.py 流用は新規 INSERT 競合で上書き発生のため不採用)。

team_hierarchy_repo.py パターンを踏襲し UPDATE-only + INSERT 分離。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass(frozen=True)
class TeamBudgetRow:
    """team_budgets テーブルの 1 row。

    UI ロード時 / upsert 成功時の戻り値として利用する。
    """

    year: int
    month: int
    team: str
    budget_amount: float
    memo: Optional[str]
    version: int
    updated_at: datetime
    updated_by: str


class UpsertConflict(Exception):
    """楽観ロック競合または INSERT 競合。

    - UPDATE WHERE version=expected_version で affected_rows=0
    - DELETE WHERE version=expected_version で affected_rows=0
    - INSERT 試行時に既存 row が同 PK で存在 (NOT EXISTS 句で 0 件挿入)

    UI 側は本例外をキャッチして「他の管理者が同時編集中の可能性があります」
    エラーを表示し、再読込ボタンで st.rerun() する。
    """
