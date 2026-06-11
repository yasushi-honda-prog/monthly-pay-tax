"""予実階層設定ページ (admin only)

PR-E で構築した team_hierarchy テーブルを dashboard から編集する管理画面。
本田様の方針: dashboard 編集対象は team_hierarchy のみ。team_budgets_quarterly /
expense_categories は CSV + CLI 経由 (CSV 番号で本田様作業、MERGE は冪等)。

UI 構成:
    1. 未マッピング隊の補完 (UNMAPPED 32 件を 1-click で team_hierarchy に追加)
    2. 統括隊名のリネーム (leader_team 一括書き換え)
    3. 階層一覧の編集 (activity_category 単位で leader_team / leader_team_type / note 更新)
    4. 階層一覧の削除 (1 行単位)
    5. coverage サマリー (MAPPED / UNMAPPED / UNUSED 件数)
"""

from __future__ import annotations

import time

import pandas as pd
import streamlit as st

# 二重 submit ロック設定 (race condition による重複 INSERT 防止)
# 本田様 2026-06-11 のインシデント: 連続クリック等で 2 秒差の MERGE が同時実行され
# team_hierarchy に重複行が混入。本ロックでセッション内の race を防ぐ。
ADD_LOCK_KEY = "th_add_lock_ts"
ADD_LOCK_DURATION_SEC = 5

from lib.auth import require_admin
from lib.constants import LEADER_TEAM_TYPES
from lib.doc_styles import (
    apply_doc_styles,
    render_hero,
    render_section_header,
)
from lib.team_hierarchy_repo import (
    delete_hierarchy_row,
    fetch_distinct_leader_teams,
    fetch_hierarchy,
    fetch_unmapped_activity_categories,
    insert_hierarchy_row,
    rename_leader_team,
    update_hierarchy_row,
)

# --- 認証チェック ---
email = st.session_state.get("user_email", "")
role = st.session_state.get("user_role", "")
require_admin(email, role)

# --- 共通トンマナ CSS ---
apply_doc_styles()

# --- ヒーロー ---
render_hero(
    "🏷️ 予実階層設定",
    "予実管理機能 (PR-E) で使う「隊 ↔ 統括隊」のマッピングを編集します。<br>"
    "活動分類 (gyomu_reports.activity_category) を統括隊に紐付けることで、"
    "<code>v_team_budget_actuals_quarterly</code> に実額が集計されるようになります。",
    color="purple",
)

st.caption(
    "※ 統括隊レベルの予算金額 (team_budgets_quarterly) と支出カテゴリマスタ "
    "(expense_categories) は CSV + CLI で投入します (本ページの編集対象外)。"
    "投入手順は `docs/operations/20260611_四半期予算投入手順.md` 参照。"
)
st.divider()


# --- データ取得 (ページ全体で使い回し) ---
@st.cache_data(ttl=60)
def _load_hierarchy() -> pd.DataFrame:
    return fetch_hierarchy()


@st.cache_data(ttl=60)
def _load_unmapped() -> pd.DataFrame:
    return fetch_unmapped_activity_categories()


@st.cache_data(ttl=60)
def _load_leader_teams() -> list[str]:
    return fetch_distinct_leader_teams()


def _invalidate_caches() -> None:
    """編集後に全 cache をクリア (個別 cache.clear で他ユーザーへの波及を最小化)。"""
    _load_hierarchy.clear()
    _load_unmapped.clear()
    _load_leader_teams.clear()


# CR-H1 反映: dialog はモジュールトップで定義 (条件分岐内にあると df_hierarchy 空時に未定義)
@st.dialog("階層エントリ削除の確認")
def _confirm_delete_dialog(target_activity: str, target_leader: str):
    st.warning("以下の team_hierarchy 行を削除します。元に戻せません。")
    st.markdown(f"- 活動分類: **{target_activity}**")
    st.markdown(f"- 統括隊: **{target_leader}**")
    st.caption(
        "削除しても gyomu_reports / team_budgets_quarterly には影響しません。"
        "v_team_hierarchy_coverage で UNMAPPED として再検出されます。"
    )
    col_ok, col_cancel = st.columns(2)
    with col_ok:
        if st.button("削除を実行", type="primary", use_container_width=True,
                     key="dialog_th_delete_ok"):
            try:
                delete_hierarchy_row(target_activity)
                st.success(f"{target_activity} を削除しました。")
                _invalidate_caches()
                st.rerun()
            except Exception as e:
                st.error(f"削除に失敗しました: {e}")
    with col_cancel:
        if st.button("キャンセル", use_container_width=True,
                     key="dialog_th_delete_cancel"):
            st.rerun()


try:
    df_hierarchy = _load_hierarchy()
    df_unmapped = _load_unmapped()
    # データ重複防御: BQ で同一 activity_category の duplicate row が混入した場合に
    # Streamlit の widget key duplicate を防ぐ。最新 updated_at を採用。
    # 重複が検出されたら本田様判断で BQ 上の余分な row を削除する想定
    _original_hierarchy_count = len(df_hierarchy)
    df_hierarchy = df_hierarchy.sort_values("updated_at", ascending=False) \
                               .drop_duplicates(subset=["activity_category"], keep="first") \
                               .reset_index(drop=True)
    _hierarchy_duplicates = _original_hierarchy_count - len(df_hierarchy)
    leader_team_options = _load_leader_teams()
except Exception as e:
    st.error(f"BQ 取得に失敗しました: {e}")
    st.stop()


# --- サマリー ---
render_section_header("カバレッジサマリー", icon="📊", color="amber")
col_a, col_b, col_c = st.columns(3)
with col_a:
    st.metric("登録済み隊数", len(df_hierarchy))
with col_b:
    st.metric("未マッピング隊数 (UNMAPPED)", len(df_unmapped))
with col_c:
    st.metric("統括隊数 (distinct)", len(leader_team_options))

if len(df_unmapped) > 0:
    st.warning(
        f"⚠ gyomu_reports に出現するが team_hierarchy 未定義の隊が {len(df_unmapped)} 件あります。"
        "下記「未マッピング隊の補完」で割当を進めてください。"
    )
else:
    st.success("✓ すべての隊がマッピング済みです。")

if _hierarchy_duplicates > 0:
    st.error(
        f"⚠ team_hierarchy に同一 activity_category の重複行が {_hierarchy_duplicates} 件検出されました "
        f"(表示は最新 updated_at の行を採用、UI は復旧済)。"
        " BQ で `SELECT activity_category, COUNT(*) FROM team_hierarchy GROUP BY activity_category HAVING COUNT(*)>1` "
        "で確認し、余分な行を削除してください。"
    )
st.divider()


# --- 1. 未マッピング隊の補完 ---
render_section_header(
    "未マッピング隊の補完 (UNMAPPED → 統括隊割当)", icon="➕", color="blue"
)
st.caption(
    "gyomu_reports に出現する活動分類のうち、まだ team_hierarchy に登録されていないものを"
    "選んで統括隊に紐付けます。1 件ずつ追加します。"
    " 本リストは「隊」サフィックスの活動分類のみ表示します"
    " (主要分類「その他」「移動」「電話対応」等は team_hierarchy 管理対象外。"
    " 必要時は `scripts/upload_team_hierarchy.py` で個別投入)。"
)

# 本田様判断: UNMAPPED 全件から「〜隊」サフィックスのみを selectbox に出す
unmapped_team_options = [
    cat for cat in df_unmapped["activity_category"].tolist()
    if cat.endswith("隊")
]

if not unmapped_team_options:
    if df_unmapped.empty:
        st.info("未マッピング隊はありません。")
    else:
        st.info(
            f"「隊」サフィックスの未マッピング隊はありません "
            f"(主要分類が {len(df_unmapped)} 件残っていますが、本リストの対象外です)。"
        )
else:
    with st.form("add_unmapped_form"):
        col1, col2, col3, col4 = st.columns([3, 3, 1, 2])
        with col1:
            target_unmapped = st.selectbox(
                f"未マッピング隊 ({len(unmapped_team_options)} 件)",
                unmapped_team_options,
                key="add_target_unmapped",
            )
        with col2:
            # 既存の統括隊名から選ぶ + 新規入力も許容
            leader_choice = st.selectbox(
                "統括隊 (既存)",
                ["(新規入力)"] + leader_team_options,
                key="add_leader_choice",
            )
        with col3:
            new_type = st.selectbox(
                "type",
                LEADER_TEAM_TYPES,
                key="add_type",
            )
        with col4:
            new_note = st.text_input("note (任意)", key="add_note")

        new_leader_text = st.text_input(
            "統括隊 (新規入力)",
            placeholder="ヤスス+ヒデデン統括隊 など",
            disabled=(leader_choice != "(新規入力)"),
            key="add_new_leader_text",
        )

        submitted = st.form_submit_button("追加", use_container_width=True)
        if submitted:
            # 二重 submit ロック: 直近 ADD_LOCK_DURATION_SEC 秒以内なら skip
            # (Streamlit form の rerun 中に次の submit が積まれた場合の race 防御)
            now_ts = time.time()
            last_submit_ts = st.session_state.get(ADD_LOCK_KEY, 0.0)
            if now_ts - last_submit_ts < ADD_LOCK_DURATION_SEC:
                st.warning(
                    f"直前の追加処理から {ADD_LOCK_DURATION_SEC} 秒以内のため処理を"
                    "スキップしました (重複追加防止)。少し待ってから再度操作してください。"
                )
            else:
                st.session_state[ADD_LOCK_KEY] = now_ts
                actual_leader = (
                    new_leader_text.strip() if leader_choice == "(新規入力)"
                    else leader_choice
                )
                if not actual_leader:
                    st.error("統括隊名を選択または入力してください")
                else:
                    try:
                        affected = insert_hierarchy_row(
                            activity_category=target_unmapped,
                            leader_team=actual_leader,
                            leader_team_type=new_type,
                            note=(new_note.strip() or None),
                            actor=email,
                        )
                        if affected == 0:
                            st.error(
                                "追加が反映されませんでした。画面を再読み込みしてから再度実行してください。"
                            )
                        else:
                            st.success(
                                f"{target_unmapped} を {actual_leader} ({new_type}) として追加しました。"
                            )
                            _invalidate_caches()
                            st.rerun()
                    except Exception as e:
                        st.error(f"追加に失敗しました: {e}")

st.divider()


# --- 2. 統括隊名のリネーム ---
render_section_header("統括隊名のリネーム", icon="✏️", color="green")
st.caption(
    "leader_team を一括 UPDATE で書き換えます。対象の隊すべての leader_team が同時に変更されます。"
    "なお、team_budgets_quarterly 側の leader_team は連動しません — 必要に応じて"
    "本田様にて CSV 再投入で揃えてください。"
)

if not leader_team_options:
    st.info("リネーム可能な統括隊がありません (team_hierarchy が空)。")
else:
    with st.form("rename_form"):
        col1, col2, col3 = st.columns([3, 3, 1])
        with col1:
            rename_target = st.selectbox(
                "対象の統括隊", leader_team_options, key="rename_target"
            )
        with col2:
            new_leader_name = st.text_input(
                "新しい名前",
                placeholder="新しい統括隊名",
                key="rename_new_name",
            )
        with col3:
            rename_submitted = st.form_submit_button("リネーム", use_container_width=True)
        if rename_submitted:
            new_name = new_leader_name.strip()
            if not new_name:
                st.error("新しい名前を入力してください")
            elif new_name == rename_target:
                st.info("変更がありません")
            else:
                try:
                    affected = rename_leader_team(rename_target, new_name, actor=email)
                    st.success(
                        f"{rename_target} → {new_name} に {affected} 件の隊を一括リネームしました。"
                    )
                    # Codex H2 / Evaluator 指摘: team_budgets_quarterly は自動連動しない
                    st.warning(
                        "⚠ team_budgets_quarterly の leader_team は連動しません。"
                        "予実比較を正しく出すには、新名で予算 CSV を作成し "
                        "`scripts/upload_team_budgets_quarterly.py` で再投入してください。"
                    )
                    _invalidate_caches()
                    st.rerun()
                except Exception as e:
                    st.error(f"リネームに失敗しました: {e}")

st.divider()


# --- 3. 階層一覧の編集・削除 ---
render_section_header("階層一覧 (編集・削除)", icon="📋", color="purple")
st.caption(
    "登録済み隊を一覧表示。各行で leader_team / leader_team_type / note を編集できます。"
    "削除は行右端の「削除」ボタンから (gyomu_reports / team_budgets_quarterly には影響なし)。"
)

if df_hierarchy.empty:
    st.info("登録済み隊がありません。「未マッピング隊の補完」から追加してください。")
else:
    # CR-H1 反映: dialog はモジュールトップで定義済み (空 DataFrame でも再定義されないため)
    _delete_target = st.session_state.pop("th_delete_target", None)
    if _delete_target is not None:
        _confirm_delete_dialog(_delete_target[0], _delete_target[1])

    # フィルタ
    filter_leader = st.selectbox(
        "統括隊で絞り込み",
        ["全て"] + leader_team_options,
        key="filter_th_leader",
    )
    df_view = df_hierarchy
    if filter_leader != "全て":
        df_view = df_view[df_view["leader_team"] == filter_leader]

    st.caption(f"表示件数: {len(df_view)} / 全 {len(df_hierarchy)} 件")

    # 行表示
    # enumerate で idx を key に含めることで、万一データ重複が drop_duplicates を
    # すり抜けても (例えば pandas での重複判定が浮動小数等で揺れた場合) Streamlit の
    # widget key duplicate を防ぐ二重防御
    for idx, (_, row) in enumerate(df_view.iterrows()):
        key_suffix = f"{idx}_{row['activity_category']}"
        with st.container(border=True):
            c1, c2, c3, c4, c5 = st.columns([3, 3, 1, 2, 1])
            with c1:
                st.markdown(f"**{row['activity_category']}**")
                if row.get("updated_at") is not None and not pd.isna(row["updated_at"]):
                    st.caption(
                        f"v{int(row['version'])} / "
                        f"{row['updated_at'].strftime('%Y-%m-%d %H:%M')} by {row['updated_by']}"
                    )
            with c2:
                new_leader = st.text_input(
                    "統括隊",
                    value=row["leader_team"],
                    key=f"edit_leader_{key_suffix}",
                    label_visibility="collapsed",
                )
            with c3:
                current_type_idx = (
                    list(LEADER_TEAM_TYPES).index(row["leader_team_type"])
                    if row["leader_team_type"] in LEADER_TEAM_TYPES else 0
                )
                new_type = st.selectbox(
                    "type",
                    LEADER_TEAM_TYPES,
                    index=current_type_idx,
                    key=f"edit_type_{key_suffix}",
                    label_visibility="collapsed",
                )
            with c4:
                new_note = st.text_input(
                    "note",
                    value=row["note"] or "",
                    key=f"edit_note_{key_suffix}",
                    label_visibility="collapsed",
                )
            with c5:
                changed = (
                    new_leader.strip() != row["leader_team"]
                    or new_type != row["leader_team_type"]
                    or (new_note.strip() or None) != row["note"]
                )
                save_disabled = not changed or not new_leader.strip()
                if st.button(
                    "保存",
                    key=f"save_{key_suffix}",
                    disabled=save_disabled,
                    use_container_width=True,
                ):
                    try:
                        affected = update_hierarchy_row(
                            activity_category=row["activity_category"],
                            leader_team=new_leader.strip(),
                            leader_team_type=new_type,
                            note=(new_note.strip() or None),
                            actor=email,
                            expected_version=int(row["version"]),
                        )
                        if affected == 0:
                            # Codex M2 反映: lock 競合 or 削除済みは error に
                            st.error(
                                "保存できませんでした。他のユーザーが更新または削除した可能性があります。"
                                "ブラウザを再読み込みしてからやり直してください。"
                            )
                        else:
                            st.success(f"{row['activity_category']} を更新しました。")
                            _invalidate_caches()
                            st.rerun()
                    except Exception as e:
                        st.error(f"更新に失敗しました: {e}")

                if st.button(
                    "削除",
                    key=f"del_{key_suffix}",
                    use_container_width=True,
                ):
                    st.session_state["th_delete_target"] = (
                        row["activity_category"],
                        row["leader_team"],
                    )
                    st.rerun()
