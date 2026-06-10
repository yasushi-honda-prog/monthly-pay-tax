"""予実管理ビュー共通レンダラ + 純粋計算ヘルパ (spec §6)

純関数 (計算ロジック) と Streamlit レンダリングを混在させているが、
計算系はテスト容易性のため Streamlit 非依存にしている。
"""

from __future__ import annotations

from typing import Optional

import pandas as pd


# ----- 純関数: 計算ヘルパ -----


def classify_achievement(rate: Optional[float]) -> str:
    """達成率レンジを分類する (色 mapping と判定の単一情報源)。

    Returns:
        "ok" (80-120%) / "warning" (60-80% or 120-150%) / "danger" (<60% or >150%) /
        "no_data" (None/NaN)
    """
    if rate is None or (isinstance(rate, float) and pd.isna(rate)):
        return "no_data"
    if 80 <= rate <= 120:
        return "ok"
    if (60 <= rate < 80) or (120 < rate <= 150):
        return "warning"
    return "danger"


def achievement_color(rate: Optional[float]) -> str:
    """達成率 → HEX color (ヒートマップ / matrix セル背景用)"""
    bucket = classify_achievement(rate)
    return {
        "ok": "#d4edda",       # 緑
        "warning": "#fff3cd",  # 黄
        "danger": "#f8d7da",   # 赤
        "no_data": "#e9ecef",  # 灰
    }[bucket]


def format_yen(value: Optional[float]) -> str:
    """¥ 整数表記 (¥1,234,567)。None / NaN は '—'"""
    if value is None:
        return "—"
    try:
        if pd.isna(value):
            return "—"
    except (TypeError, ValueError):
        pass
    try:
        return f"¥{int(value):,}"
    except (TypeError, ValueError):
        return "—"


def format_rate(rate: Optional[float]) -> str:
    """達成率 → '96.0%' or '—'"""
    if rate is None:
        return "—"
    try:
        if pd.isna(rate):
            return "—"
    except (TypeError, ValueError):
        pass
    try:
        return f"{float(rate):.1f}%"
    except (TypeError, ValueError):
        return "—"


def format_diff(diff: Optional[float]) -> str:
    """差額 → '+1,234' / '-5,678' / '—'"""
    if diff is None:
        return "—"
    try:
        if pd.isna(diff):
            return "—"
    except (TypeError, ValueError):
        pass
    try:
        return f"{int(diff):+,}"
    except (TypeError, ValueError):
        return "—"


def is_outdated(stored_hash: Optional[str], current_hash: Optional[str]) -> bool:
    """評価レコードの hash と現在の hash を比較し outdated か判定する。

    判定ルール (Evaluator MEDIUM 修正):
    - 両方非空 → 不一致なら outdated
    - stored が空で current が非空 → outdated (評価レコードが古い形式 or
      claim 進行中で hash が未確定。安全側に振って再生成を促す)
    - current が空 (実データがない) → False (表示する outdated 判定材料がない)
    """
    if not current_hash:
        return False
    if not stored_hash:
        return True
    return stored_hash != current_hash


def summarize_actuals(df: pd.DataFrame) -> dict:
    """予実 DataFrame から全体集計を返す。

    Returns:
        {
          "total_budget": float, "total_actual": float,
          "overall_rate": float|None, "overall_diff": float
        }
    """
    if df.empty:
        return {
            "total_budget": 0.0, "total_actual": 0.0,
            "overall_rate": None, "overall_diff": 0.0,
        }
    total_budget = float(df["budget_amount"].fillna(0).sum())
    total_actual = float(df["actual_amount"].fillna(0).sum())
    overall_rate = (total_actual / total_budget * 100) if total_budget > 0 else None
    return {
        "total_budget": total_budget,
        "total_actual": total_actual,
        "overall_rate": overall_rate,
        "overall_diff": total_actual - total_budget,
    }


def build_matrix_df(actuals: pd.DataFrame, value: str = "achievement_rate") -> pd.DataFrame:
    """v_team_budget_actuals → 隊×月 ピボット DataFrame。

    Args:
        value: "achievement_rate" / "actual_amount" / "diff_amount" 等
    """
    if actuals.empty:
        return pd.DataFrame()
    pivot = actuals.pivot_table(
        index="team", columns="month", values=value, aggfunc="first"
    )
    pivot = pivot.sort_index()
    return pivot


# ----- Streamlit レンダラ (副作用あり) -----


def render_kpi_row(summary: dict) -> None:
    """全体予算 / 実額 / 達成率 + 差額 の 3 列 KPI (spec §6.2)"""
    import streamlit as st

    col_b, col_a, col_r = st.columns(3)
    col_b.metric("全体予算", format_yen(summary["total_budget"]))
    col_a.metric("全体実額", format_yen(summary["total_actual"]))
    col_r.metric(
        "全体達成率",
        format_rate(summary["overall_rate"]),
        delta=format_diff(summary["overall_diff"]),
    )


def render_ai_comment_card(
    eval_row: Optional[dict],
    *,
    outdated: bool,
    is_admin: bool,
    on_update,
    on_force_update,
    key_suffix: str = "default",
) -> None:
    """AI 評価コメントカード (spec §6.4)。

    Args:
        eval_row: team_monthly_eval の 1 行 (dict) または None
        outdated: hash 不一致なら True
        is_admin: 強制再生成ボタン表示判定
        on_update: 「評価を更新」ボタン押下時に呼ぶ callable (force=False)
        on_force_update: 「強制再生成」ボタン押下時に呼ぶ callable (force=True)
        key_suffix: button key の suffix (deterministic に year/month/team 等を渡す)
    """
    import streamlit as st

    with st.container(border=True):
        if eval_row is None or not eval_row.get("ai_comment"):
            st.info(
                "まだ評価コメントがありません。「評価を更新」ボタンで生成できます。"
            )
        else:
            if outdated:
                st.warning("⚠ 元データが更新されています (outdated)。再生成を推奨します。")
            st.markdown(eval_row["ai_comment"])
            generated_at = eval_row.get("generated_at")
            if generated_at:
                st.caption(f"生成日時: {generated_at}")

        # admin のみ 2 列、非 admin は単独列 (Evaluator LOW: zero-width 回避)
        if is_admin:
            col1, col2 = st.columns(2)
            if col1.button("評価を更新", key=f"update_eval_{key_suffix}"):
                on_update()
            if col2.button("強制再生成 (admin)", key=f"force_eval_{key_suffix}"):
                on_force_update()
        else:
            if st.button("評価を更新", key=f"update_eval_{key_suffix}"):
                on_update()
