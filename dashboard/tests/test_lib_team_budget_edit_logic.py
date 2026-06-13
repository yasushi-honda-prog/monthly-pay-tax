"""team_budget_edit_logic の pure helper テスト (Step 3)。"""

from __future__ import annotations

import pytest

from lib.team_budget_edit_logic import (
    DeleteConfirmState,
    OverflowConfirmState,
    compute_remaining_budget,
    is_overflow,
    overflow_amount,
    transition_on_confirm_cancel,
    transition_on_confirm_continue,
    transition_on_delete_click,
    transition_on_delete_confirm_cancel,
    transition_on_save_click,
)


class TestComputeRemainingBudget:
    def test_returns_difference(self):
        assert compute_remaining_budget(1000000.0, 600000.0) == 400000.0

    def test_returns_none_when_leader_budget_none(self):
        assert compute_remaining_budget(None, 600000.0) is None

    def test_can_be_zero(self):
        assert compute_remaining_budget(1000000.0, 1000000.0) == 0.0

    def test_can_be_negative_when_other_exceeds(self):
        """予算編成途中で配下他隊合計が統括隊予算を超えている (warn 状態)"""
        assert compute_remaining_budget(1000000.0, 1500000.0) == -500000.0


class TestIsOverflow:
    def test_below_budget_not_overflow(self):
        assert is_overflow(300000.0, 600000.0, 1000000.0) is False

    def test_exactly_budget_not_overflow(self):
        """boundary: 残額 0 ちょうど (= 等号一致は超過しない)"""
        assert is_overflow(400000.0, 600000.0, 1000000.0) is False

    def test_just_over_budget(self):
        """boundary: +¥1 で超過"""
        assert is_overflow(400001.0, 600000.0, 1000000.0) is True

    def test_returns_false_when_leader_budget_none(self):
        """統括隊予算未投入 (判定不能) は False (呼び出し側で別ガード)"""
        assert is_overflow(500000.0, 600000.0, None) is False


class TestOverflowAmount:
    def test_returns_diff_when_overflow(self):
        assert overflow_amount(500000.0, 600000.0, 1000000.0) == 100000.0

    def test_returns_zero_when_not_overflow(self):
        assert overflow_amount(300000.0, 600000.0, 1000000.0) == 0.0

    def test_returns_zero_when_leader_none(self):
        assert overflow_amount(500000.0, 600000.0, None) == 0.0


class TestTransitionOnSaveClick:
    def test_no_overflow_save_immediately(self):
        current = OverflowConfirmState()
        new_state, save_now = transition_on_save_click(
            current=current,
            new_amount=300000.0,
            new_memo="ok",
            other_total=600000.0,
            leader_monthly_budget=1000000.0,
        )
        assert save_now is True
        assert new_state.pending is False
        assert new_state.confirmed is False

    def test_overflow_unconfirmed_pends(self):
        current = OverflowConfirmState()
        new_state, save_now = transition_on_save_click(
            current=current,
            new_amount=500000.0,
            new_memo="over",
            other_total=600000.0,
            leader_monthly_budget=1000000.0,
        )
        assert save_now is False
        assert new_state.pending is True
        assert new_state.confirmed is False
        assert new_state.pending_amount == 500000.0
        assert new_state.pending_memo == "over"
        assert new_state.pending_overflow_by == 100000.0

    def test_overflow_confirmed_saves(self):
        """confirm ダイアログで「続行」押下後 → 再 save → save 実行"""
        current = OverflowConfirmState(
            pending=False, confirmed=True,
            pending_amount=500000.0, pending_memo="over",
            pending_overflow_by=100000.0,
        )
        new_state, save_now = transition_on_save_click(
            current=current,
            new_amount=500000.0,
            new_memo="over",
            other_total=600000.0,
            leader_monthly_budget=1000000.0,
        )
        assert save_now is True
        # state は reset される (confirmed を持ち越さない)
        assert new_state.confirmed is False
        assert new_state.pending is False


class TestTransitionOnConfirmContinue:
    def test_marks_confirmed(self):
        current = OverflowConfirmState(
            pending=True, confirmed=False,
            pending_amount=500000.0, pending_memo="m",
            pending_overflow_by=100000.0,
        )
        new_state = transition_on_confirm_continue(current)
        assert new_state.confirmed is True
        assert new_state.pending is False
        assert new_state.pending_amount == 500000.0


class TestTransitionOnConfirmCancel:
    def test_resets_state(self):
        new_state = transition_on_confirm_cancel()
        assert new_state == OverflowConfirmState()
        assert new_state.pending is False
        assert new_state.confirmed is False


class TestDeleteConfirmTransitions:
    def test_click_sets_pending(self):
        assert transition_on_delete_click() == DeleteConfirmState(pending=True)

    def test_cancel_resets(self):
        assert transition_on_delete_confirm_cancel() == DeleteConfirmState(pending=False)
