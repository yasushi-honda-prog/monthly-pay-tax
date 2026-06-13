"""隊×月予算編集 UI の pure helper (Step 3 / T6b)。

UI 層から状態遷移・数値計算ロジックを分離してテスタブルにする。
Streamlit 依存を持たない pure 関数のみ。

設計: docs/specs/2026-06-13-team-monthly-budget-input.md §6.3 / §6.6
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


def compute_remaining_budget(
    leader_monthly_budget: Optional[float],
    other_total: float,
) -> Optional[float]:
    """統括隊月予算の残額。

    Args:
        leader_monthly_budget: 統括隊の月予算 (四半期÷3)。None なら未投入
        other_total: 配下他隊の同月予算合計 (load_other_team_budgets_in_leader)

    Returns:
        残額 (= leader - other_total)、leader None なら None
    """
    if leader_monthly_budget is None:
        return None
    return leader_monthly_budget - other_total


def is_overflow(
    new_amount: float,
    other_total: float,
    leader_monthly_budget: Optional[float],
) -> bool:
    """入力値 + 他隊合計が統括隊月予算を超過するか。

    leader_monthly_budget が None (未投入) の場合は判定不能で False を返す。
    呼び出し側は事前に「統括隊予算 None なら保存禁止」のガードを通すこと
    (本関数は超過判定ロジックのみに責務を絞る)。
    """
    if leader_monthly_budget is None:
        return False
    return (other_total + new_amount) > leader_monthly_budget


def overflow_amount(
    new_amount: float,
    other_total: float,
    leader_monthly_budget: Optional[float],
) -> float:
    """超過額。is_overflow=False なら 0。"""
    if leader_monthly_budget is None:
        return 0.0
    diff = (other_total + new_amount) - leader_monthly_budget
    return max(diff, 0.0)


# --------- session_state 状態遷移 (pure な state representation) ---------


@dataclass(frozen=True)
class OverflowConfirmState:
    """超過確認ダイアログの状態 (Streamlit 非依存の抽象表現)。

    pending = True: 「¥X 超過します。続行?」を表示中
    confirmed = True: 「続行」が押された (次の save 実行で消費される)
    両方 False: 通常状態
    """

    pending: bool = False
    confirmed: bool = False
    pending_amount: Optional[float] = None
    pending_memo: Optional[str] = None
    pending_overflow_by: float = 0.0


def transition_on_save_click(
    *,
    current: OverflowConfirmState,
    new_amount: float,
    new_memo: Optional[str],
    other_total: float,
    leader_monthly_budget: Optional[float],
) -> tuple[OverflowConfirmState, bool]:
    """保存ボタン押下時の状態遷移を計算。

    Returns:
        (新 state, save_now)
        save_now=True: そのまま save 実行可
        save_now=False: confirm 待ち (state.pending=True)
    """
    overflow = is_overflow(new_amount, other_total, leader_monthly_budget)
    if not overflow:
        # 超過なし → そのまま save、state は reset
        return OverflowConfirmState(), True
    if current.confirmed:
        # 既に confirm 済み → save 実行 + reset
        return OverflowConfirmState(), True
    # 超過 + 未確認 → pending を立てて rerun (save しない)
    return (
        OverflowConfirmState(
            pending=True,
            confirmed=False,
            pending_amount=new_amount,
            pending_memo=new_memo,
            pending_overflow_by=overflow_amount(
                new_amount, other_total, leader_monthly_budget
            ),
        ),
        False,
    )


def transition_on_confirm_continue(
    current: OverflowConfirmState,
) -> OverflowConfirmState:
    """confirm ダイアログ「続行」押下時。confirmed=True で次 save を許可。"""
    return OverflowConfirmState(
        pending=False,
        confirmed=True,
        pending_amount=current.pending_amount,
        pending_memo=current.pending_memo,
        pending_overflow_by=current.pending_overflow_by,
    )


def transition_on_confirm_cancel() -> OverflowConfirmState:
    """confirm ダイアログ「キャンセル」押下時。state をリセット。"""
    return OverflowConfirmState()


# --------- 削除確認の状態遷移 ---------


@dataclass(frozen=True)
class DeleteConfirmState:
    """削除確認ダイアログの状態。"""

    pending: bool = False


def transition_on_delete_click() -> DeleteConfirmState:
    return DeleteConfirmState(pending=True)


def transition_on_delete_confirm_cancel() -> DeleteConfirmState:
    return DeleteConfirmState(pending=False)
