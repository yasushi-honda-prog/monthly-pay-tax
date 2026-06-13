"""業務報告一覧ビュー関連のヘルパー + render 関数 (Issue #254/#245)。

filter_wam_only は Streamlit 非依存の純関数。
render_gyomu_list_view は Streamlit に依存するが、loader 呼出は呼び出し元責務
(注入型 API、Codex セカンドオピニオン High #1/#2 反映)。
"""

from __future__ import annotations

import unicodedata

import pandas as pd


# 検索対象ラベル → 実カラム名のマッピング (module level、テスト容易化)
_SEARCH_TARGET_MAP: dict[str, str] = {
    "メンバー": "nickname",
    "内容": "description",
    "スポンサー": "sponsor",
    "業務分類": "work_category",
    "隊（活動）分類": "activity_category",
}


def _normalized_starts_with_wam(val: object) -> bool:
    if val is None:
        return False
    try:
        if pd.isna(val):
            return False
    except (TypeError, ValueError):
        pass
    if not isinstance(val, str):
        val = str(val)
    # NFKC: 全角ＷＡＭ → WAM、全角（）→ ()、全角空白 → 半角空白
    # lstrip: 入力者のタイポによる先頭空白を許容
    return unicodedata.normalize("NFKC", val).lstrip().startswith("(WAM)")


def filter_wam_only(df: pd.DataFrame) -> pd.DataFrame:
    """業務分類が「（WAM）」または「(WAM)」で始まる行のみを抽出する。

    判定は NFKC 正規化 + 先頭空白除去後に半角「(WAM)」プレフィックスで行う。
    これにより全角/半角括弧、全角/半角アルファベット、先頭空白の混在を吸収する。
    元の DataFrame の値は変更しない (新しい DataFrame を返す)。
    """
    if df.empty or "work_category" not in df.columns:
        return df.iloc[0:0].copy()
    mask = df["work_category"].map(_normalized_starts_with_wam)
    return df[mask].copy()


def _filter_by_period(
    df: pd.DataFrame,
    selected_year: int,
    selected_month: str,
    range_start_year: int | None,
    range_start_month: int | None,
    range_end_year: int | None,
    range_end_month: int | None,
) -> pd.DataFrame | None:
    """期間フィルタを適用する純関数。

    Returns:
        フィルタ後 DataFrame、または None (期間指定の終了 < 開始の場合、
        呼び出し元に warning 表示を委ねるシグナル)
    """
    if selected_month != "期間指定":
        result_base = df[df["year"] == selected_year]
        month_val = int(selected_month.replace("月", ""))
        return result_base[result_base["month"] == month_val]
    # 期間指定: 年またぎ範囲対応 (tab1 と同じ year*100+month ベース)
    _start_ym = range_start_year * 100 + range_start_month
    _end_ym = range_end_year * 100 + range_end_month
    if _end_ym < _start_ym:
        return None
    # month は NaN 含む可能性があるため to_numeric で安全変換 (NaN は比較で False)
    _ym_num = (
        df["year"].astype(int) * 100
        + pd.to_numeric(df["month"], errors="coerce")
    )
    return df[(_ym_num >= _start_ym) & (_ym_num <= _end_ym)]


def render_gyomu_list_view(
    *,
    # データ (呼び出し元から注入、Codex High #1)
    df_gyomu_all: pd.DataFrame,
    name_map: dict[str, str],
    all_members: list[str],
    # 選択状態
    selected_members: list[str],
    selected_year: int,
    selected_month: str,
    range_start_year: int | None = None,
    range_start_month: int | None = None,
    range_end_year: int | None = None,
    range_end_month: int | None = None,
    # 識別 / 表示制御
    key_prefix: str,
    wam_only: bool = False,
    empty_message: str = "データがありません",
    # Issue #254/#245 (隊ドリルダウン拡張)
    fixed_activity_category: str | None = None,
    compact: bool = False,
) -> None:
    """業務報告一覧のテーブルビューを描画する (注入型 API)。

    呼び出し元責務 (loader 呼出 + 正規化):
      - load_gyomu_with_members() → df_gyomu_all (raw)
      - fill_empty_nickname / valid_years / display_name 列の構築
      - load_all_members / load_member_name_map

    fixed_activity_category 指定時 (Issue #254):
      - 内部 filter: activity_category == fixed_activity_category
      - 隊（活動）分類 selectbox を非表示 (2 列レイアウトに圧縮)
      - 検索対象 options から「隊（活動）分類」を除外 (Codex Medium)
      - 値変更時に reset_counter advance (前隊の条件残留防止、Codex Medium)

    compact=True (Issue #254 右カラム用、Codex High #3):
      - dataframe height を 600 → 360 に圧縮
      - 表示列から URL / activity_category を除外
    """
    # 遅延 import: lib の純関数部分 (filter_wam_only) を Streamlit 抜きで
    # テストするため、render 関数のみ Streamlit を import する
    import streamlit as st  # noqa: PLC0415

    # 呼び出し元責務だった処理 (loader / 正規化) は除外。df_gyomu_all は呼び出し元で
    # fill_empty_nickname + valid_years + display_name 列追加済の前提
    if df_gyomu_all.empty:
        st.info(empty_message)
        return

    # 期間フィルタ
    result_base = _filter_by_period(
        df_gyomu_all,
        selected_year=selected_year,
        selected_month=selected_month,
        range_start_year=range_start_year,
        range_start_month=range_start_month,
        range_end_year=range_end_year,
        range_end_month=range_end_month,
    )
    if result_base is None:
        st.warning("終了年月が開始年月より前になっています")
        return

    if selected_members:
        result_base = result_base[result_base["nickname"].isin(selected_members)]

    if wam_only:
        result_base = filter_wam_only(result_base)

    # Issue #254: 隊 fix モード
    if fixed_activity_category is not None:
        result_base = result_base[
            result_base["activity_category"] == fixed_activity_category
        ]

    total_base = len(result_base)
    if total_base == 0:
        st.info(empty_message)
        return

    # reset counter (Streamlit widget value のリセット用、公式パターン)
    counter_key = f"{key_prefix}_reset_counter"
    if counter_key not in st.session_state:
        st.session_state[counter_key] = 0

    # Issue #254 (Codex Medium): fixed_activity_category 変更時に reset_counter
    # を advance して前隊のフィルタ条件残留を防ぐ
    fixed_state_key = f"{key_prefix}_fixed_activity_category"
    prev_fixed = st.session_state.get(fixed_state_key)
    if fixed_activity_category is not None and prev_fixed != fixed_activity_category:
        if prev_fixed is not None:
            # 初回ではなく値変更のときのみ advance
            st.session_state[counter_key] += 1
        st.session_state[fixed_state_key] = fixed_activity_category

    _rc = st.session_state[counter_key]

    # --- フィルタ行 1: 隊（活動）分類 → 業務分類(依存) → スポンサー ---
    # Issue #254: fixed mode では 隊分類 selectbox を非表示、2 列レイアウト
    if fixed_activity_category is None:
        fcol1, fcol2, fcol3 = st.columns(3)
        with fcol1:
            categories = ["隊（活動）分類"] + sorted(
                result_base["activity_category"].dropna().unique().tolist()
            )
            sel_cat = st.selectbox(
                "隊（活動）分類", categories,
                key=f"{key_prefix}_cat_{_rc}", label_visibility="collapsed",
            )
        result_after_cat = (
            result_base if sel_cat == "隊（活動）分類"
            else result_base[result_base["activity_category"] == sel_cat]
        )
    else:
        # 隊 fix モード: 隊分類 UI 隠す、業務分類 + スポンサーの 2 列
        fcol2, fcol3 = st.columns(2)
        result_after_cat = result_base

    with fcol2:
        work_categories = sorted(
            result_after_cat["work_category"].dropna().unique().tolist()
        )
        sel_wcat = st.multiselect(
            "業務分類", work_categories, key=f"{key_prefix}_wcat_{_rc}",
            placeholder="全業務分類", label_visibility="collapsed",
        )

    with fcol3:
        sponsor_series = result_after_cat["sponsor"].dropna().astype(str).str.strip()
        sponsors = sorted(sponsor_series[sponsor_series != ""].unique().tolist())
        sel_sponsor = st.multiselect(
            "スポンサー", sponsors, key=f"{key_prefix}_sponsor_{_rc}",
            placeholder="全スポンサー", label_visibility="collapsed",
        )

    # --- フィルタ行 2: キーワード検索 + 検索対象選択 + リセット ---
    # Issue #254 (Codex Medium): fixed mode では検索対象から「隊（活動）分類」除外
    if fixed_activity_category is None:
        search_target_labels = list(_SEARCH_TARGET_MAP.keys())
    else:
        search_target_labels = [
            k for k in _SEARCH_TARGET_MAP.keys() if k != "隊（活動）分類"
        ]

    scol1, scol2, scol3 = st.columns([3, 2, 1])
    with scol1:
        keyword = st.text_input(
            "検索", key=f"{key_prefix}_keyword_{_rc}",
            placeholder="🔍 キーワード入力 (部分一致)",
            label_visibility="collapsed",
        )
    with scol2:
        sel_targets = st.multiselect(
            "検索対象", search_target_labels,
            key=f"{key_prefix}_search_targets_{_rc}",
            placeholder="検索対象 (空=全カラム横断)",
            label_visibility="collapsed",
            help="検索対象カラムを限定したい場合は選択 (複数選択可)。空の場合は全カラム横断検索。",
        )
    with scol3:
        def _reset_filters() -> None:
            st.session_state[counter_key] += 1
        st.button(
            "リセット", key=f"{key_prefix}_reset", use_container_width=True,
            help="業務分類・スポンサー・検索キーワード・検索対象をクリア",
            on_click=_reset_filters,
        )

    # --- フィルタ適用 ---
    result = result_after_cat
    if sel_wcat:
        result = result[result["work_category"].isin(sel_wcat)]
    if sel_sponsor:
        result = result[result["sponsor"].astype(str).str.strip().isin(sel_sponsor)]
    if keyword:
        kw = keyword.strip().lower()
        _target_cols = (
            [_SEARCH_TARGET_MAP[t] for t in sel_targets]
            if sel_targets else [_SEARCH_TARGET_MAP[t] for t in search_target_labels]
        )

        def _col_match(col: str) -> "pd.Series":
            return result[col].fillna("").astype(str).str.lower().str.contains(
                kw, regex=False, na=False,
            )

        mask = _col_match(_target_cols[0])
        for _c in _target_cols[1:]:
            mask = mask | _col_match(_c)
        result = result[mask]

    # 遅延 import (UI 描画用ヘルパ、循環依存防止のため関数内)
    from lib.ui_helpers import (  # noqa: PLC0415
        add_gyomu_date_dt,
        clean_numeric_series,
        render_kpi,
    )

    result = add_gyomu_date_dt(result)
    result["amount_num"] = clean_numeric_series(result["amount"])

    k1, k2, k3 = st.columns(3)
    with k1:
        render_kpi("総額", f"¥{result['amount_num'].sum():,.0f}")
    with k2:
        render_kpi("件数", f"{len(result):,}")
    with k3:
        # 分母は: 絞り込みなし → 全メンバー、絞り込みあり → 選択メンバー数
        _reporter_total = len(selected_members) if selected_members else len(all_members)
        render_kpi("報告者数", f"{result['nickname'].nunique()} / {_reporter_total} 名")

    if len(result) < total_base:
        st.markdown(
            f'<div class="count-badge">{len(result):,} 件 / 全 {total_base:,} 件中</div>',
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            f'<div class="count-badge">{len(result):,} 件</div>',
            unsafe_allow_html=True,
        )

    # 「内容」列の Python 側 pre-format 改行 (st.dataframe の wrap 制約への workaround)
    def _wrap_jp(s: object, width: int = 22) -> str:
        if s is None or (isinstance(s, float) and pd.isna(s)):
            return ""
        text = str(s)
        if len(text) <= width:
            return text
        return "\n".join(text[i:i + width] for i in range(0, len(text), width))

    # Issue #254 (Codex High #3): compact mode で URL / activity_category 列を除外
    if compact:
        view_columns = [
            "display_name", "date_dt", "day_of_week",
            "work_category", "sponsor", "description",
            "unit_price", "work_hours", "travel_distance_km", "amount",
        ]
        view_height = 360
    else:
        view_columns = [
            "display_name", "source_url", "date_dt", "day_of_week",
            "activity_category", "work_category",
            "sponsor", "description",
            "unit_price", "work_hours", "travel_distance_km", "amount",
        ]
        view_height = 600

    view = result[view_columns].copy()
    view["description"] = view["description"].apply(_wrap_jp)

    rename_map = {
        "display_name": "メンバー",
        "source_url": "URL",
        "date_dt": "日付",
        "day_of_week": "曜日",
        "activity_category": "隊（活動）分類",
        "work_category": "業務分類",
        "sponsor": "スポンサー",
        "description": "内容",
        "unit_price": "単価",
        "work_hours": "時間",
        "travel_distance_km": "移動距離(km)",
        "amount": "金額",
    }
    column_config = {
        "日付": st.column_config.DateColumn(format="M/D"),
        "内容": st.column_config.TextColumn("内容", width="large"),
        "業務分類": st.column_config.TextColumn("業務分類", width="medium"),
        "スポンサー": st.column_config.TextColumn("スポンサー", width="medium"),
    }
    if not compact:
        column_config["URL"] = st.column_config.LinkColumn(display_text="開く")
        column_config["隊（活動）分類"] = st.column_config.TextColumn(
            "隊（活動）分類", width="medium",
        )

    st.dataframe(
        view.rename(columns=rename_map),
        column_config=column_config,
        use_container_width=True,
        hide_index=True,
        height=view_height,
        row_height=66,
    )
