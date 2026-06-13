"""統括隊月予算入力ページ (admin only、Issue #248)

設計: docs/specs/2026-06-14-leader-team-monthly-budget.md §5.5

機能:
1. fiscal_year selector (default: 現在年度)
2. 6×12 grid 入力 (列単位 help で quarterly÷3 推定値 tooltip 表示、Codex M4)
3. 保存ボタン: 楽観ロックで diff 保存、BulkUpsertResult を表示
4. 初期 seed セクション: quarterly÷3 で 72 セル一括投入 (preview → 二段階承認、Codex M3)
5. 既存データありの再 seed (上書き) も同 expander で対応

非機能:
- admin 以外は require_admin で page 描画拒否
- 保存後は invalidate_all で関連 cache クリア
"""

from __future__ import annotations

from datetime import datetime

import pandas as pd
import streamlit as st

from lib.auth import require_admin
from lib.bq_client import get_bq_client
from lib.doc_styles import apply_doc_styles, render_hero
from lib.fiscal_calendar import calendar_to_fiscal, fiscal_quarter_to_months
from lib.leader_budget_cache import (
    cached_fetch_yearly,
    cached_load_quarterly_seed,
    invalidate_all,
)
from lib.leader_budget_repo import (
    BulkUpsertResult,
    UpsertConflict,
    LeaderBudgetRow,
    delete as repo_delete,
    preview_seed_from_quarterly,
    seed_from_quarterly,
    upsert,
)

# --- 認証チェック (admin only) ---
email = st.session_state.get("user_email", "")
role = st.session_state.get("user_role", "")
require_admin(email, role)

apply_doc_styles()

render_hero(
    "💰 統括隊月予算入力",
    "全体タブ・統括隊タブの月次推移グラフ予算ラインを月毎に手調整します。<br>"
    "新規 BQ table <code>leader_team_monthly_budgets</code> を直接編集します "
    "(Issue #248、PR #247 hotfix の恒久対応)。",
    color="green",
)

# FY 列順 (Q1→Q4): 11, 12, 1, 2, ..., 10
_FY_MONTHS_ORDER: list[int] = []
for fq in [1, 2, 3, 4]:
    _FY_MONTHS_ORDER.extend(fiscal_quarter_to_months(fq))


def _current_fiscal_year() -> int:
    """現年度の fiscal_year を返す (default selector 用)。

    OQ1 確定: 今日が 2026-06-14 → calendar_to_fiscal(2026, 6) = (2026, 3)、
    fiscal_year=2026 を default にする。
    """
    today = datetime.now()
    fy, _ = calendar_to_fiscal(today.year, today.month)
    return fy


# --- サイドバー: fiscal_year 選択 ---
_default_fy = _current_fiscal_year()
fiscal_year = st.sidebar.selectbox(
    "fiscal_year (会計年度、11 月始まり)",
    options=[_default_fy + 1, _default_fy, _default_fy - 1],
    index=1,  # default は中央 (現年度)
    key="lbi_fiscal_year",
    help=(
        f"FY{_default_fy} は {_default_fy - 1}/11 〜 {_default_fy}/10 (12 ヶ月)。"
        " 列順は Q1=11,12,1 / Q2=2,3,4 / Q3=5,6,7 / Q4=8,9,10。"
    ),
)

st.caption(
    f"FY{fiscal_year} の編集中 ({fiscal_year - 1}/11 〜 {fiscal_year}/10)。"
    " admin のみ閲覧・編集可能。"
)

# --- データ取得 ---
current_rows = cached_fetch_yearly(fiscal_year)
seed_df = cached_load_quarterly_seed(fiscal_year)


def _build_grid_df(
    rows: list[LeaderBudgetRow], seed: pd.DataFrame
) -> pd.DataFrame:
    """grid 表示用 DataFrame を構築。

    rows と seed_df をマージして leader_team × month_order の matrix を返す。
    """
    # 行 = leader_team の一覧 (rows + seed の和集合)
    leader_teams = set(r.leader_team for r in rows)
    if not seed.empty and "leader_team" in seed.columns:
        leader_teams |= set(seed["leader_team"].dropna().unique())
    leader_teams_sorted = sorted(leader_teams)

    if not leader_teams_sorted:
        return pd.DataFrame()

    # row.budget_amount を (leader_team, month) → int に変換
    cell_map = {
        (r.leader_team, r.month): r.budget_amount for r in rows
    }
    # grid 作成: index=leader_team, columns=_FY_MONTHS_ORDER (列順)
    data = {}
    for m in _FY_MONTHS_ORDER:
        col_label = f"{m}月"
        data[col_label] = [
            cell_map.get((lt, m), 0) for lt in leader_teams_sorted
        ]
    df = pd.DataFrame(data, index=leader_teams_sorted)
    df.index.name = "leader_team"
    return df


def _detect_changes(
    original_rows: list[LeaderBudgetRow],
    edited_df: pd.DataFrame,
) -> list[dict]:
    """編集前後を比較して変更セルを抽出。

    Returns:
        [{leader_team, month, new_amount, expected_version, is_new}, ...]
    """
    original_map = {(r.leader_team, r.month): r for r in original_rows}
    changes: list[dict] = []
    for lt in edited_df.index:
        for m in _FY_MONTHS_ORDER:
            col_label = f"{m}月"
            if col_label not in edited_df.columns:
                continue
            new_val = edited_df.at[lt, col_label]
            try:
                new_val_int = int(new_val) if pd.notna(new_val) else 0
            except (ValueError, TypeError):
                continue  # invalid 値は skip (UI で validate 済の前提)
            existing = original_map.get((lt, m))
            if existing is None:
                if new_val_int > 0:
                    changes.append({
                        "leader_team": lt, "month": m,
                        "new_amount": new_val_int,
                        "expected_version": None,
                        "is_new": True, "is_delete": False,
                    })
            else:
                if new_val_int == 0:
                    # 既存→空セルは削除扱い
                    changes.append({
                        "leader_team": lt, "month": m,
                        "new_amount": 0,
                        "expected_version": existing.version,
                        "is_new": False, "is_delete": True,
                    })
                elif new_val_int != existing.budget_amount:
                    changes.append({
                        "leader_team": lt, "month": m,
                        "new_amount": new_val_int,
                        "expected_version": existing.version,
                        "is_new": False, "is_delete": False,
                    })
    return changes


def _persist_diff(
    client,
    fiscal_year: int,
    changes: list[dict],
    actor_email: str,
) -> BulkUpsertResult:
    """変更を 1 セルずつ upsert/delete (Codex M1: 部分成功許容)。"""
    saved_count, deleted_count = 0, 0
    conflicts, errors = [], []
    for ch in changes:
        lt, m = ch["leader_team"], ch["month"]
        try:
            if ch["is_delete"]:
                repo_delete(
                    client,
                    fiscal_year=fiscal_year, month=m, leader_team=lt,
                    expected_version=ch["expected_version"],
                    actor_email=actor_email,
                )
                deleted_count += 1
            else:
                upsert(
                    client,
                    fiscal_year=fiscal_year, month=m, leader_team=lt,
                    budget_amount=ch["new_amount"],
                    expected_version=ch["expected_version"],
                    actor_email=actor_email,
                )
                saved_count += 1
        except UpsertConflict:
            conflicts.append((lt, m))
        except Exception as e:
            errors.append((lt, m, str(e)))
    return BulkUpsertResult(
        saved_count=saved_count,
        deleted_count=deleted_count,
        conflicts=conflicts,
        errors=errors,
    )


def _render_result(result: BulkUpsertResult) -> None:
    if result.saved_count > 0 or result.deleted_count > 0:
        st.success(
            f"保存成功: {result.saved_count} 件 / 削除: {result.deleted_count} 件"
        )
    if result.conflicts:
        st.error(
            f"楽観ロック競合 ({len(result.conflicts)} 件、別 admin の同時編集の可能性)。"
            " ページを再読込してから編集をやり直してください: "
            + ", ".join(f"{lt}/{m}月" for lt, m in result.conflicts)
        )
    if result.errors:
        st.error(
            f"BQ エラー ({len(result.errors)} 件):\n"
            + "\n".join(f"- {lt}/{m}月: {msg}" for lt, m, msg in result.errors)
        )
    if (
        result.saved_count == 0
        and result.deleted_count == 0
        and not result.conflicts
        and not result.errors
    ):
        st.info("変更はありませんでした。")


# --- メイン UI ---

if not current_rows and (seed_df is None or seed_df.empty):
    st.warning(
        f"FY{fiscal_year} は予算未投入、かつ seed 元 (team_budgets_quarterly) も空です。"
        " 先に scripts/upload_team_budgets_quarterly.py で四半期予算を投入してください。"
    )
    st.stop()

# --- grid 入力 ---
st.subheader(f"📝 FY{fiscal_year} 統括隊月予算 grid")

if not current_rows:
    st.info(
        f"FY{fiscal_year} はまだ投入されていません。下の「初期投入」セクションで "
        "quarterly÷3 から seed してください。"
    )
else:
    grid_df = _build_grid_df(current_rows, seed_df)
    if grid_df.empty:
        st.info("表示する統括隊データがありません。")
    else:
        st.caption(
            f"行: 統括隊 ({len(grid_df.index)}件) × 列: 月 (11→10、FY 順)。"
            " 各列ヘッダーの help に quarterly÷3 推定値が表示されます。"
            " セルを編集して「保存」ボタンで反映。"
        )
        # column_config で列ごとに help (Codex M4: tooltip フォールバック方針、列単位)
        column_config = {}
        if seed_df is not None and not seed_df.empty:
            # code-review high CONFIRMED 反映: int() は truncate のため round() を経由
            # (Codex R9 統一: 'int(round())' で四捨五入)
            seed_map = {
                (row["leader_team"], int(row["month"])): int(round(row["quarterly_div3"]))
                for _, row in seed_df.iterrows()
            }
        else:
            seed_map = {}
        for m in _FY_MONTHS_ORDER:
            col_label = f"{m}月"
            # 列の help: 該当月の seed 値の平均 or 代表値
            seed_values_for_month = [
                seed_map.get((lt, m), 0) for lt in grid_df.index
            ]
            seed_avg = (
                sum(seed_values_for_month) // len(seed_values_for_month)
                if seed_values_for_month else 0
            )
            column_config[col_label] = st.column_config.NumberColumn(
                col_label,
                min_value=0,
                max_value=1_000_000_000,
                step=10000,
                format="¥%d",
                help=f"quarterly÷3 推定値 (統括隊平均): ¥{seed_avg:,}",
            )

        edited_df = st.data_editor(
            grid_df,
            column_config=column_config,
            use_container_width=True,
            key="lbi_grid",
            num_rows="fixed",
        )

        if st.button("💾 保存", type="primary", key="lbi_save"):
            changes = _detect_changes(current_rows, edited_df)
            if not changes:
                st.info("変更はありませんでした。")
            else:
                result = _persist_diff(
                    get_bq_client(), fiscal_year, changes, email
                )
                invalidate_all(fiscal_year)
                _render_result(result)
                if result.saved_count > 0 or result.deleted_count > 0:
                    st.rerun()

st.divider()

# --- 初期投入 / 再 seed セクション ---
with st.expander("⚠️ quarterly÷3 で 72 セル一括 seed (初期投入 / 再投入)"):
    st.caption(
        f"FY{fiscal_year} の 72 セルを team_budgets_quarterly÷3 で一括投入します。"
        " 既に手入力データがある場合は「上書き」になります。"
    )
    if st.button("🔍 プレビュー", key="lbi_seed_preview"):
        preview = preview_seed_from_quarterly(get_bq_client(), fiscal_year)
        # Codex review C-M1 反映: fiscal_year と preview を紐付けて保存。
        # sidebar で年度切替後に古い preview で実行できないよう保護。
        st.session_state["_lbi_preview"] = {
            "fiscal_year": fiscal_year,
            "preview": preview,
        }

    _preview_state = st.session_state.get("_lbi_preview")
    # 年度切替後に古い preview を破棄 (C-M1 反映)
    if _preview_state and _preview_state.get("fiscal_year") != fiscal_year:
        st.session_state.pop("_lbi_preview", None)
        _preview_state = None
    preview = _preview_state["preview"] if _preview_state else None
    if preview:
        col1, col2, col3 = st.columns(3)
        col1.metric("変更セル数", f"{preview['changed_count']} / 72")
        col2.metric("現在合計", f"¥{preview['current_total']:,}")
        col3.metric(
            "seed 後合計",
            f"¥{preview['seed_total']:,}",
            delta=f"¥{preview['seed_total'] - preview['current_total']:+,}",
        )
        if preview["top_diffs"]:
            st.caption("差額大きい上位 10 件:")
            st.dataframe(
                pd.DataFrame(preview["top_diffs"]),
                use_container_width=True,
                hide_index=True,
            )

        # 既存データの有無で確認文言を変える
        existing_count = len(current_rows)
        if existing_count > 0:
            confirm_label = (
                f"⚠️ 既存 {existing_count} 件を上書きすることを承認します"
            )
        else:
            confirm_label = "上記内容で新規投入することを承認します"
        confirmed = st.checkbox(confirm_label, key="lbi_seed_confirm")
        if confirmed:
            if st.button(
                "🚀 実行", type="secondary", key="lbi_seed_execute"
            ):
                try:
                    result = seed_from_quarterly(
                        get_bq_client(),
                        fiscal_year=fiscal_year,
                        actor_email=email,
                        overwrite=True,
                    )
                    invalidate_all(fiscal_year)
                    st.session_state.pop("_lbi_preview", None)
                    _render_result(result)
                    if result.saved_count > 0:
                        st.rerun()
                except ValueError as e:
                    st.error(f"seed 失敗: {e}")
