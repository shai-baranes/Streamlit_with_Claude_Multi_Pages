import streamlit as st
import pandas as pd

from utils import inject_css, require_data, sidebar_filters

from st_aggrid import (
    AgGrid,
    GridOptionsBuilder,
    GridUpdateMode,
    DataReturnMode,
    JsCode,
)


st.set_page_config(page_title="Stacked Vlues", page_icon="📈", layout="wide")
inject_css()

df_full = require_data()
df      = sidebar_filters(df_full)

st.title("📈 Stacked Values")

TIME_COLUMN_CANDIDATES = ["time", "Time", "Date"]


def get_time_column(df: pd.DataFrame) -> str:
    for col in TIME_COLUMN_CANDIDATES:
        if col in df.columns:
            return col
    raise KeyError("Could not find a 'time' column in the dataframe.")


def init_state():
    if "selected_columns_ordered" not in st.session_state:
        st.session_state["selected_columns_ordered"] = []

    if "stacked_mode" not in st.session_state:
        st.session_state["stacked_mode"] = True

    if "prev_stacked_mode" not in st.session_state:
        st.session_state["prev_stacked_mode"] = True

    if "selected_source_row" not in st.session_state:
        st.session_state["selected_source_row"] = None

    if "aggrid_key_counter" not in st.session_state:
        st.session_state["aggrid_key_counter"] = 0


def sync_selected_columns(
    options,
    widget_key="selected_columns_widget",
    state_key="selected_columns_ordered",
):
    current_widget_selection = st.session_state.get(widget_key, [])
    previous_ordered_selection = st.session_state.get(state_key, [])

    previous_still_selected = [
        c for c in previous_ordered_selection if c in current_widget_selection
    ]
    newly_added = [
        c for c in current_widget_selection if c not in previous_ordered_selection
    ]

    st.session_state[state_key] = [
        c for c in (previous_still_selected + newly_added) if c in options
    ]


def build_view(df: pd.DataFrame, selected_columns: list, stacked_mode: bool) -> pd.DataFrame:
    if not selected_columns:
        return pd.DataFrame()

    time_col = get_time_column(df)
    anchor_col = selected_columns[0]
    extra_cols = [c for c in selected_columns[1:] if c != time_col]

    result_cols = [time_col, anchor_col] + [c for c in extra_cols if c != anchor_col]

    if stacked_mode:
        mask = df[anchor_col].ne(df[anchor_col].shift())
        out = df.loc[mask, result_cols].copy()
    else:
        out = df.loc[:, result_cols].copy()

    out.insert(0, "_source_row", out.index.astype(str))
    return out.reset_index(drop=True)


def extract_selected_row(grid_response):
    selected_rows = grid_response.get("selected_rows", None)

    if selected_rows is None:
        return None

    if isinstance(selected_rows, pd.DataFrame):
        if selected_rows.empty:
            return None
        return selected_rows.iloc[0].to_dict()

    if isinstance(selected_rows, list):
        if len(selected_rows) == 0:
            return None
        return selected_rows[0]

    return None


def build_restore_and_scroll_js(selected_source_row: str | None):
    if selected_source_row is None:
        return None

    return JsCode(f"""
    function(params) {{
        var targetSourceRow = "{selected_source_row}";

        function restoreSelectionAndScroll() {{
            var matchedNode = null;

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
                params.api.ensureIndexVisible(matchedNode.rowIndex, 'top');
            }}
        }}

        setTimeout(restoreSelectionAndScroll, 120);
        setTimeout(restoreSelectionAndScroll, 300);
    }}
    """)


st.subheader("Stacked event table")

if "df_full" not in st.session_state:
    st.warning("Please load the CSV first.")
else:
    init_state()

    df_full = st.session_state["df_full"]
    time_col = get_time_column(df_full)
    selectable_columns = [c for c in df_full.columns if c != time_col]

    st.multiselect(
        "Select columns to display",
        options=selectable_columns,
        default=st.session_state["selected_columns_ordered"],
        key="selected_columns_widget",
        on_change=sync_selected_columns,
        kwargs={
            "options": selectable_columns,
            "widget_key": "selected_columns_widget",
            "state_key": "selected_columns_ordered",
        },
        help=(
            "The first selected column is the anchor column. "
            "Time is always shown on the left."
        ),
    )

    st.checkbox(
        "Stacked mode (show only rows where anchor value changes)",
        key="stacked_mode",
    )

    selected_columns = st.session_state["selected_columns_ordered"]

    if not selected_columns:
        st.info("No column selected. Table is intentionally empty.")
    else:
        anchor_col = selected_columns[0]

        mode_changed = (
            st.session_state["prev_stacked_mode"] != st.session_state["stacked_mode"]
        )

        if mode_changed:
            st.session_state["aggrid_key_counter"] += 1

        view_df = build_view(
            df_full,
            selected_columns,
            st.session_state["stacked_mode"],
        )

        st.caption(
            f"Anchor column: {anchor_col} | "
            f"Mode: {'stacked' if st.session_state['stacked_mode'] else 'full'} | "
            f"Visible rows: {len(view_df)} / {len(df_full)}"
        )

        restore_scroll_js = None
        if mode_changed and st.session_state["selected_source_row"] is not None:
            restore_scroll_js = build_restore_and_scroll_js(
                st.session_state["selected_source_row"]
            )

        gb = GridOptionsBuilder.from_dataframe(view_df)

        gb.configure_default_column( # default value for columns width (to be narrower!)
            min_column_width=60,
            resizable=True,
            filterable=False,
            sortable=True,
            editable=False,
            maxWidth=140,
        )

        # # to configure specific columns other  then the default width value:
        # gb.configure_column("_source_row", hide=True)

        # gb.configure_column(time_col, width=90, minWidth=80, maxWidth=120)

        # for col in selected_columns:
        #     gb.configure_column(col, width=85, minWidth=60, maxWidth=110)

        gb.configure_column("_source_row", hide=True)

        gb.configure_selection(
            selection_mode="single",
            use_checkbox=True,
        )

        grid_options_extra = {
            "suppressRowClickSelection": False,
            "rowDeselection": True,
            "ensureDomOrder": True,
            "getRowId": JsCode("function(params) { return params.data._source_row; }"),
        }

        if restore_scroll_js is not None:
            grid_options_extra["onFirstDataRendered"] = restore_scroll_js

        gb.configure_grid_options(**grid_options_extra)

        aggrid_key = f"event_table_aggrid_{st.session_state['aggrid_key_counter']}"

        grid_response = AgGrid(
            view_df,
            gridOptions=gb.build(),
            data_return_mode=DataReturnMode.FILTERED_AND_SORTED,
            update_mode=GridUpdateMode.SELECTION_CHANGED,
            fit_columns_on_grid_load=True,
            allow_unsafe_jscode=True,
            theme="streamlit",
            height=450,
            key=aggrid_key,
            reload_data=False,
        )

        selected_row = extract_selected_row(grid_response)

        if selected_row is not None and "_source_row" in selected_row:
            st.session_state["selected_source_row"] = str(selected_row["_source_row"])

        if st.session_state["selected_source_row"] is not None:
            selected_full_row = df_full.loc[[int(st.session_state["selected_source_row"])]].copy() # TBD add here your recommended columns to be dispalyed (along with the anchor I guess)

            st.markdown("**Selected source row**")
            st.dataframe(selected_full_row, use_container_width=True)

    st.session_state["prev_stacked_mode"] = st.session_state["stacked_mode"]