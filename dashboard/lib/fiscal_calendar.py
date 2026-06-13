"""会計年度 (11 月始まり) ↔ 暦年月 の双方向変換 pure helper (Issue #248 T1)。

設計: docs/specs/2026-06-14-leader-team-monthly-budget.md §5.1

BQ `fiscal_quarter` UDF (infra/bigquery/views.sql) と整合する Python 実装。
- Q1: 11, 12, 1 月
- Q2: 2, 3, 4 月
- Q3: 5, 6, 7 月
- Q4: 8, 9, 10 月

依存先なし (最下層 helper)。
"""

from __future__ import annotations

# fiscal_quarter (1-4) → 構成月リスト (Q順)。
_FQ_TO_MONTHS: dict[int, list[int]] = {
    1: [11, 12, 1],
    2: [2, 3, 4],
    3: [5, 6, 7],
    4: [8, 9, 10],
}


def fiscal_year_to_calendar_months(fiscal_year: int) -> list[tuple[int, int]]:
    """FY を構成する 12 ヶ月の (calendar_year, month) tuple を Q1 順で返す。

    例: FY2026 → [(2025,11),(2025,12),(2026,1),...,(2026,10)]
    """
    result: list[tuple[int, int]] = []
    for fq in [1, 2, 3, 4]:
        for month in _FQ_TO_MONTHS[fq]:
            # Q1 の 11, 12 月は前暦年、それ以外は当暦年
            cy = fiscal_year - 1 if month in (11, 12) else fiscal_year
            result.append((cy, month))
    return result


def calendar_to_fiscal(year: int, month: int) -> tuple[int, int]:
    """暦年月 → (fiscal_year, fiscal_quarter)。

    BQ `fiscal_quarter` UDF と等価:
      fiscal_year     = year + (1 if month >= 11 else 0)
      fiscal_quarter  = 1 + ((month - 11 + 12) % 12) DIV 3
    """
    fiscal_year = year + 1 if month >= 11 else year
    fiscal_quarter = 1 + ((month - 11 + 12) % 12) // 3
    return fiscal_year, fiscal_quarter


def fiscal_quarter_to_months(fiscal_quarter: int) -> list[int]:
    """fiscal_quarter (1-4) → 構成月リスト [Q順]。

    Raises:
        ValueError: fiscal_quarter が 1-4 の範囲外。
    """
    if fiscal_quarter not in _FQ_TO_MONTHS:
        raise ValueError(f"fiscal_quarter must be 1-4, got {fiscal_quarter}")
    return list(_FQ_TO_MONTHS[fiscal_quarter])


def fiscal_year_month_range(fiscal_year: int) -> tuple[int, int, int, int]:
    """`load_team_budget_actuals(year_start, year_end, month_start, month_end)` に渡せる範囲。

    FY2026 → (2025, 2026, 11, 10): year_start=2025 (Q1 11/12 月の年), year_end=2026,
    month_start=11 (Q1 開始月), month_end=10 (Q4 終了月).

    呼び出し側で `month_start > month_end` を検知して年跨ぎ SQL に組み立てる必要あり。
    """
    return (fiscal_year - 1, fiscal_year, 11, 10)
