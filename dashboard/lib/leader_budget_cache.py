"""leader_team_monthly_budgets DML 関連の cache wrapper + invalidation 集約 (Issue #248 T6)。

設計: docs/specs/2026-06-14-leader-team-monthly-budget.md §5.3

team_budget_cache パターン踏襲。新テーブル変更で再計算が必要な cache を
影響先ベースで列挙し、invalidate_all で一括 clear する (Codex M2 反映)。
"""

from __future__ import annotations

import streamlit as st

from lib.bq_client import (
    get_bq_client,
    load_active_leader_teams,
    load_leader_team_monthly_budgets,
    load_leader_team_quarterly_budgets_for_seed,
    load_leader_team_yearly_monthly_budgets,
)
from lib.leader_budget_repo import (
    LeaderBudgetRow,
    fetch_yearly,
    load_active_leader_teams_for_budget_input,
)


@st.cache_data(ttl=600)
def cached_fetch_yearly(fiscal_year: int) -> list[LeaderBudgetRow]:
    """UI 入力 grid 表示用 cache (TTL 10 分)。保存時に invalidate_all で clear。"""
    return fetch_yearly(get_bq_client(), fiscal_year)


@st.cache_data(ttl=600)
def cached_load_quarterly_seed(fiscal_year: int):
    """差分 tooltip 用の quarterly÷3 推定値 cache (TTL 10 分)。"""
    return load_leader_team_quarterly_budgets_for_seed(fiscal_year)


@st.cache_data(ttl=600)
def cached_load_active_leader_teams_for_input(fiscal_year: int) -> list[str]:
    """予算入力 UI の grid 行選択用 cache (TTL 10 分)。"""
    return load_active_leader_teams_for_budget_input(get_bq_client(), fiscal_year)


def invalidate_all(fiscal_year: int) -> None:
    """leader_team_monthly_budgets DML 後に呼ぶ集約 invalidator (Codex M2 反映)。

    新テーブル変更で再計算が必要になる cache を影響先ベースで列挙:
    - cached_fetch_yearly: UI 入力 grid の最新行
    - cached_load_quarterly_seed: 差分 tooltip の seed 推定
    - cached_load_active_leader_teams_for_input: 入力 grid 行リスト
    - bq_client.load_leader_team_yearly_monthly_budgets: 全体タブ月次推移
    - bq_client.load_leader_team_monthly_budgets: 統括隊タブ月予算
    - bq_client.load_active_leader_teams: 統括隊フィルタ selectbox

    Note:
        fiscal_year 引数は将来の部分 clear 用のためのシグネチャ予約。
        現実装の `st.cache_data.clear()` は関数単位の全 clear で全年度キャッシュが消える
        (Codex R10 反映、実害小)。

    対象外:
    - load_team_budget_actuals: 実績由来のため本テーブル変更影響なし
    - team_budget_cache の他関数: team_budgets ベース、本テーブル変更影響なし
    """
    _ = fiscal_year  # 将来の部分 clear 用引数。現状は全 clear。
    targets = (
        cached_fetch_yearly,
        cached_load_quarterly_seed,
        cached_load_active_leader_teams_for_input,
        load_leader_team_yearly_monthly_budgets,
        load_leader_team_monthly_budgets,
        load_active_leader_teams,
    )
    for fn in targets:
        try:
            fn.clear()
        except AttributeError:
            pass
