"""actual_data_hash の Python 側 composite 合成 helper。

設計: docs/specs/2026-06-13-team-monthly-budget-input.md §5.3

既存の BQ SQL 内 hash 計算 (gyomu_reports 集計) は touch せず、Python 側で
budget_amount + prompt_version を追加して composite hash を作る。

cloud-run と dashboard の両方に同一実装を配置し、contract test fixture で
cross-side consistency を機械的検証する。

本ファイルと dashboard/lib/team_budget_hash.py は同一内容であるべき。
変更時は両方を同期更新すること。
"""

from __future__ import annotations

import hashlib
from decimal import Decimal
from typing import Optional, Union


def compose_actual_data_hash(
    bq_hash: str,
    budget_amount: Optional[Union[Decimal, float, int]],
    prompt_version: str,
) -> str:
    """既存 BQ hash と budget + prompt_version を合成して outdated 判定 hash を生成。

    Args:
        bq_hash: 既存 compute_actual_data_hash の SQL 戻り値 (空文字許容、
                 IFNULL(..., '') で "データなし" を表現)
        budget_amount: team_budgets.budget_amount。None は "null" 文字列に正規化、
                       Decimal/float/int は str(Decimal(str(value))) で正規化
                       (float の精度差異を吸収)
        prompt_version: vertex_evaluator.PROMPT_VERSION 等の文字列

    Returns:
        hex digest (64 文字)
    """
    if budget_amount is None:
        budget_norm = "null"
    else:
        # float 精度差・Decimal の trailing zero を吸収。
        # str(Decimal(str(1000.0))) は "1000.0"、str(Decimal("1000")) は "1000" になるため
        # format(f) + rstrip で末尾 0 と小数点を統一して正規化する。
        budget_dec = Decimal(str(budget_amount))
        as_fixed = format(budget_dec, "f")
        if "." in as_fixed:
            as_fixed = as_fixed.rstrip("0").rstrip(".")
        budget_norm = as_fixed
    composite = f"{bq_hash}|{budget_norm}|{prompt_version}"
    return hashlib.sha256(composite.encode("utf-8")).hexdigest()
