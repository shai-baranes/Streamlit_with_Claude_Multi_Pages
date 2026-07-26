import streamlit as st
import pandas as pd

from utils import inject_css, require_data, sidebar_filters
from st_aggrid import AgGrid, GridOptionsBuilder, DataReturnMode, JsCode


st.set_page_config(page_title="Stacked Values", page_icon="📈", layout="wide")
inject_css()

st.title("📈 Stacked Values")

TIME_COLUMN_CANDIDATES = ["Date", "time", "Time"]
SECONDS_COLUMN_CANDIDATES = ["Seconds", "seconds"]
DELTA_SECONDS_COLUMN = "Dt [s]"
VIEW_MODES = ["Full", "Stacked by Left", "Stacked by All"]


def get_time_column(df: pd.DataFrame) -> str:
    for col in TIME_COLUMN_CANDIDATES:
        if col in df.columns:
            return col
    raise KeyError("Could not find a time-like column in the dataframe.")


def get_seconds_column(df: pd.DataFrame) -> str | None:
    for col in SECONDS_COLUMN_CANDIDATES:
        if col in df.columns:
            return col
    return None


def init_state() -> None:
    defaults = {
        "selected_columns_ordered": [],
        "view_mode": "Stacked by Left",
        "selected_source_row": None,
        "aggrid_mount_id": 0,
        "pending_restore_scroll": False,
        "stacked_exclusion_cols": [],
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def mark_grid_for_remount_and_restore() -> None:
    st.session_state["aggrid_mount_id"] += 1
    st.session_state["pending_restore_scroll"] = (
        st.session_state.get("selected_source_row") is not None
    )


def on_selected_columns_change(widget_key: str, state_key: str) -> None:
    current_widget_selection = st.session_state.get(widget_key, [])
    previous_ordered_selection = st.session_state.get(state_key, [])

    previous_still_selected = [
        c for c in previous_ordered_selection if c in current_widget_selection
    ]
    newly_added = [
        c for c in current_widget_selection if c not in previous_ordered_selection
    ]

    st.session_state[state_key] = previous_still_selected + newly_added

    valid_exclusions = [
        c for c in st.session_state.get("stacked_exclusion_cols", [])
        if c in st.session_state[state_key]
    ]
    st.session_state["stacked_exclusion_cols"] = valid_exclusions
    st.session_state["stacked_exclusion_cols_widget"] = valid_exclusions

    mark_grid_for_remount_and_restore()


def on_view_mode_change() -> None:
    if st.session_state.get("view_mode") != "Stacked by All":
        st.session_state["stacked_exclusion_cols"] = []
        st.session_state["stacked_exclusion_cols_widget"] = []
    mark_grid_for_remount_and_restore()


def on_exclusion_change() -> None:
    selected_columns = st.session_state.get("selected_columns_ordered", [])
    current_excluded = [
        c
        for c in st.session_state.get("stacked_exclusion_cols_widget", [])
        if c in selected_columns
    ]

    if selected_columns and len(current_excluded) >= len(selected_columns):
        current_excluded = current_excluded[: len(selected_columns) - 1]
        st.session_state["stacked_exclusion_cols_widget"] = current_excluded

    st.session_state["stacked_exclusion_cols"] = current_excluded
    mark_grid_for_remount_and_restore()


@st.cache_data(show_spinner=False)
def build_view_cached(
    df: pd.DataFrame,
    selected_columns: tuple[str, ...],
    view_mode: str,
    exclusion_cols: tuple[str, ...],
) -> pd.DataFrame:
    if not selected_columns:
        return pd.DataFrame()

    time_col = get_time_column(df)
    seconds_col = get_seconds_column(df)

    anchor_col = selected_columns[0]
    data_cols = [c for c in selected_columns if c != time_col]
    compare_cols = [c for c in data_cols if c not in exclusion_cols]

    if not compare_cols and data_cols:
        compare_cols = [data_cols[0]]

    extra_cols = [c for c in selected_columns[1:] if c not in {time_col, anchor_col}]
    result_cols = [time_col, anchor_col] + extra_cols

    if seconds_col and seconds_col not in result_cols:
        result_cols_with_seconds = result_cols + [seconds_col]
    else:
        result_cols_with_seconds = result_cols

    if view_mode == "Full":
        out = df.loc[:, result_cols_with_seconds].copy()

    elif view_mode == "Stacked by Left":
        mask = df[anchor_col].ne(df[anchor_col].shift())
        out = df.loc[mask, result_cols_with_seconds].copy()

    elif view_mode == "Stacked by All":
        if not data_cols:
            out = df.loc[:, result_cols_with_seconds].copy()
        else:
            changed_mask = df[compare_cols].ne(df[compare_cols].shift()).any(axis=1)
            out = df.loc[changed_mask, result_cols_with_seconds].copy()

    else:
        raise ValueError(f"Unsupported view mode: {view_mode}")

    out.insert(0, "_source_row", out.index.astype(str))

    if seconds_col is not None and seconds_col in out.columns:
        out[DELTA_SECONDS_COLUMN] = pd.to_numeric(out[seconds_col], errors="coerce").diff()
        out[DELTA_SECONDS_COLUMN] = out[DELTA_SECONDS_COLUMN].round(3)
        out[DELTA_SECONDS_COLUMN] = out[DELTA_SECONDS_COLUMN].astype(object)
        if not out.empty:
            out.iloc[0, out.columns.get_loc(DELTA_SECONDS_COLUMN)] = "-"

        out.insert(2, DELTA_SECONDS_COLUMN, out.pop(DELTA_SECONDS_COLUMN))

        if seconds_col not in selected_columns:
            out = out.drop(columns=[seconds_col])

    return out.reset_index(drop=True)


@st.cache_data(show_spinner=False)
def build_selected_row_preview_cached(
    df_filtered: pd.DataFrame,
    selected_source_row: str | None,
    time_col: str,
    anchor_col: str,
) -> pd.DataFrame | None:
    if selected_source_row is None:
        return None

    source_idx = int(selected_source_row)
    if source_idx not in df_filtered.index:
        return None

    preferred_cols = [col for col in [time_col, anchor_col] if col in df_filtered.columns]
    remaining_cols = [c for c in df_filtered.columns if c not in preferred_cols]
    preview_cols = preferred_cols + remaining_cols

    return df_filtered.loc[[source_idx], preview_cols].copy()


def extract_selected_row(grid_response: dict) -> dict | None:
    selected_rows = grid_response.get("selected_rows")

    if selected_rows is None:
        return None

    if isinstance(selected_rows, pd.DataFrame):
        if selected_rows.empty:
            return None
        return selected_rows.iloc[0].to_dict()

    if isinstance(selected_rows, list):
        return selected_rows[0] if selected_rows else None

    return None


def build_restore_and_scroll_js(selected_source_row: str | None) -> JsCode | None:
    if selected_source_row is None:
        return None

    return JsCode(
        f"""
        function(params) {{
            const targetSourceRow = "{selected_source_row}";

            function restoreSelectionAndScroll() {{
                let matchedNode = null;

                params.api.forEachNode(function(node) {{
                    if (
                        node &&
                        node.data &&
                        String(node.data._source_row) === String(targetSourceRow)
                    ) {{
                        matchedNode = node;
                    }}
                }});

                if (matchedNode) {{
                    matchedNode.setSelected(true, true);
                    params.api.ensureIndexVisible(matchedNode.rowIndex, "top");
                }}
            }}

            setTimeout(restoreSelectionAndScroll, 120);
            setTimeout(restoreSelectionAndScroll, 300);
        }}
        """
    )


def configure_grid(
    view_df: pd.DataFrame,
    time_col: str,
    selected_columns: list[str],
    restore_scroll_js: JsCode | None,
) -> dict:
    gb = GridOptionsBuilder.from_dataframe(view_df)

    gb.configure_default_column(
        min_column_width=60,
        maxWidth=140,
        resizable=True,
        sortable=True,
        filterable=False,
        editable=False,
    )

    gb.configure_column("_source_row", hide=True)
    gb.configure_column(time_col, width=95, minWidth=85, maxWidth=140, pinned="left")

    if DELTA_SECONDS_COLUMN in view_df.columns:
        gb.configure_column(
            DELTA_SECONDS_COLUMN,
            width=90,
            minWidth=80,
            maxWidth=110,
            pinned="left",
        )

    for col in selected_columns:
        if col != time_col and col in view_df.columns:
            gb.configure_column(col, width=85, minWidth=60, maxWidth=120)

    gb.configure_selection(
        selection_mode="single",
        use_checkbox=True,
    )

    grid_options = {
        "suppressRowClickSelection": False,
        "rowDeselection": True,
        "ensureDomOrder": True,
        "getRowId": JsCode("function(params) { return params.data._source_row; }"),
    }

    if restore_scroll_js is not None:
        grid_options["onFirstDataRendered"] = restore_scroll_js

    gb.configure_grid_options(**grid_options)
    return gb.build()


init_state()

df_full = require_data()
df_filtered = sidebar_filters(df_full)
time_col = get_time_column(df_filtered)
seconds_col = get_seconds_column(df_filtered)

selectable_columns = [
    c for c in df_filtered.columns
    if c != time_col and c != seconds_col
]


@st.fragment
def render_stacked_table() -> None:
    st.subheader("Stacked event table")

    st.multiselect(
        "Select columns to display",
        options=selectable_columns,
        default=st.session_state["selected_columns_ordered"],
        key="selected_columns_widget",
        on_change=on_selected_columns_change,
        args=("selected_columns_widget", "selected_columns_ordered"),
        help="The first selected column is the anchor column. Date and Dt [s] are always shown on the left when available.",
    )

    mode_col, _ = st.columns([1, 5])

    with mode_col:
        st.selectbox(
            "View mode",
            options=VIEW_MODES,
            key="view_mode",
            on_change=on_view_mode_change,
        )

    selected_columns = st.session_state["selected_columns_ordered"]

    if (
        st.session_state["view_mode"] == "Stacked by All"
        and selected_columns
    ):
        allowed_max = max(0, len(selected_columns) - 1)
        current_excluded = [
            c for c in st.session_state.get("stacked_exclusion_cols", [])
            if c in selected_columns
        ]

        if len(current_excluded) > allowed_max:
            current_excluded = current_excluded[:allowed_max]
            st.session_state["stacked_exclusion_cols"] = current_excluded
            st.session_state["stacked_exclusion_cols_widget"] = current_excluded

        st.multiselect(
            "Exclusion rule",
            options=selected_columns,
            default=current_excluded,
            key="stacked_exclusion_cols_widget",
            on_change=on_exclusion_change,
            help="Excluded columns do not participate in change detection for 'Stacked by All'. At least one selected column must still participate.",
        )

    if not selected_columns:
        st.info("No column selected. Table is intentionally empty.")
        return

    anchor_col = selected_columns[0]
    view_mode = st.session_state["view_mode"]
    exclusion_cols = tuple(
        c for c in st.session_state.get("stacked_exclusion_cols", [])
        if c in selected_columns
    )

    view_df = build_view_cached(
        df=df_filtered,
        selected_columns=tuple(selected_columns),
        view_mode=view_mode,
        exclusion_cols=exclusion_cols,
    )

    if (
        st.session_state["selected_source_row"] is not None
        and "_source_row" in view_df.columns
        and st.session_state["selected_source_row"] not in set(view_df["_source_row"])
    ):
        st.session_state["selected_source_row"] = None
        st.session_state["pending_restore_scroll"] = False

    caption_parts = [
        f"Anchor column: {anchor_col}",
        f"Mode: {view_mode}",
        f"Visible rows: {len(view_df)} / {len(df_filtered)}",
    ]
    if view_mode == "Stacked by All" and exclusion_cols:
        caption_parts.append(f"Excluded from change detection: {', '.join(exclusion_cols)}")

    st.caption(" | ".join(caption_parts))

    restore_scroll_js = None
    if st.session_state["pending_restore_scroll"]:
        restore_scroll_js = build_restore_and_scroll_js(
            st.session_state["selected_source_row"]
        )

    grid_options = configure_grid(
        view_df=view_df,
        time_col=time_col,
        selected_columns=selected_columns,
        restore_scroll_js=restore_scroll_js,
    )

    aggrid_key = f"event_table_aggrid_{st.session_state['aggrid_mount_id']}"

    grid_response = AgGrid(
        view_df,
        gridOptions=grid_options,
        data_return_mode=DataReturnMode.FILTERED_AND_SORTED,
        update_on=["selectionChanged"],
        fit_columns_on_grid_load=False,
        allow_unsafe_jscode=True,
        theme="streamlit",
        height=450,
        key=aggrid_key,
        reload_data=False,
    )

    st.session_state["pending_restore_scroll"] = False

    selected_row = extract_selected_row(grid_response)
    if selected_row is not None and "_source_row" in selected_row:
        st.session_state["selected_source_row"] = str(selected_row["_source_row"])

    selected_full_row = build_selected_row_preview_cached(
        df_filtered=df_filtered,
        selected_source_row=st.session_state["selected_source_row"],
        time_col=time_col,
        anchor_col=anchor_col,
    )

    if selected_full_row is not None:
        st.markdown("**Selected source row**")
        st.dataframe(selected_full_row, use_container_width=True)


render_stacked_table()