"""team_budgets DML 関連の cache wrapper + invalidation 集約 (Step 2 / T6a)。

設計: docs/specs/2026-06-13-team-monthly-budget-input.md §5.4

Codex 指摘 k: repo 関数 (lib/team_budget_repo.py の load_team_budget 等) は
直接 @st.cache_data でラップしない (純粋関数として保ち、scripts/CSV 経路でも
そのまま使えるように)。UI 側で必要な cache wrapper を本ファイルに集約し、
invalidate_team_budget_caches は wrapper 関数だけを clear 対象にする。
"""

from __future__ import annotations

from typing import Optional

import streamlit as st

from lib.bq_client import (
    compute_current_hashes,
    get_bq_client,
    load_active_leader_teams,
    load_active_teams,
    load_leader_team_monthly_budgets,
    load_team_budget_actuals,
    load_team_monthly_eval,
)
from lib.team_budget_repo import (
    TeamBudgetRow,
    load_other_team_budgets_in_leader,
    load_team_budget,
)


@st.cache_data(ttl=60)
def load_team_budget_cached(
    year: int, month: int, team: str
) -> Optional[TeamBudgetRow]:
    """UI 表示用 cache (TTL 60s)。保存時は invalidate_team_budget_caches で clear。

    保存直前の超過判定では本 cache を信用せず、repo 直接呼びで fresh fetch する。
    """
    return load_team_budget(get_bq_client(), year, month, team)


@st.cache_data(ttl=60)
def load_other_team_budgets_cached(
    year: int, month: int, leader_team: str, exclude_team: str
) -> float:
    """超過判定の参考表示用 cache (TTL 60s)。Codex 指摘 f 対応。

    保存直前は cache を信用せず、repo 直接呼びで fresh fetch する責務は呼び出し側。
    """
    return load_other_team_budgets_in_leader(
        get_bq_client(),
        year=year, month=month,
        leader_team=leader_team, exclude_team=exclude_team,
    )


def invalidate_team_budget_caches() -> None:
    """team_budgets DML (upsert / delete) 後に呼ぶ集約 invalidator。

    Codex 指摘 j 対応の一箇所集約: clear 対象を本関数に集めることで、
    UI 側の保存ハンドラから漏れなく cache を払う。
    対象は cache_data でラップされた wrapper 関数のみ (raw repo 関数は clear 不要)。
    """
    targets = (
        load_team_budget_cached,
        load_other_team_budgets_cached,
        load_team_budget_actuals,
        load_active_teams,
        load_active_leader_teams,
        load_team_monthly_eval,
        compute_current_hashes,
        load_leader_team_monthly_budgets,
    )
    for fn in targets:
        try:
            fn.clear()
        except AttributeError:
            # cache_data で wrap されていない関数は no-op
            pass
