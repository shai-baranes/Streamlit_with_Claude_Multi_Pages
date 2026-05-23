"""
pages/2_📈_Charts.py  — Dynamic Charts page.
"""

import streamlit as st
# import numpy as np
# import plotly.express as px
# import plotly.graph_objects as go
# from plotly.subplots import make_subplots
import pandas as pd
from utils import inject_css, require_data, sidebar_filters
# import streamlit.components.v1 as _cv1

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


def init_selected_columns_state(state_key: str = "selected_columns_ordered"):
    if state_key not in st.session_state:
        st.session_state[state_key] = []


def sync_selected_columns(options, widget_key="selected_columns_widget", state_key="selected_columns_ordered"):
    """
    Preserve selection order based on user history, not widget display order.
    """
    current_widget_selection = st.session_state.get(widget_key, [])
    previous_ordered_selection = st.session_state.get(state_key, [])

    previous_still_selected = [c for c in previous_ordered_selection if c in current_widget_selection]
    newly_added = [c for c in current_widget_selection if c not in previous_ordered_selection]

    new_ordered_selection = previous_still_selected + newly_added
    st.session_state[state_key] = [c for c in new_ordered_selection if c in options]


def build_stacked_view(df: pd.DataFrame, selected_columns: list[str]) -> pd.DataFrame:
    if not selected_columns:
        return pd.DataFrame()

    time_col = get_time_column(df)
    anchor_col = selected_columns[0]
    extra_cols = [c for c in selected_columns[1:] if c != time_col]

    # rows are filtered by the 'mask'
    # shift() and ne() are often used together to compare each row with the row before it. shift() moves values up or down by a number of rows, while ne() means “not equal” and returns True wherever two values differ.
    mask = df[anchor_col].ne(df[anchor_col].shift()) # .shift() default is "1"

    result_cols = [time_col, anchor_col] + [c for c in extra_cols if c != anchor_col]
    result_df = df.loc[mask, result_cols].copy()

    return result_df.reset_index(drop=True)


# ---- UI ----

st.subheader("Stacked event table")

if "df_full" not in st.session_state:
    st.warning("Please load the CSV first.")
else:
    df_full = st.session_state["df_full"]
    time_col = get_time_column(df_full)

    selectable_columns = [c for c in df_full.columns if c != time_col]

    init_selected_columns_state()

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
            "Rows are shown only where the anchor value changes from the previous row. "
            "Time is always added on the left."
        ),
    )

    selected_columns = st.session_state["selected_columns_ordered"]

    if not selected_columns:
        st.info("No column selected. Table is intentionally empty.")
        st.dataframe(pd.DataFrame())
    else:
        anchor_col = selected_columns[0]
        stacked_df = build_stacked_view(df_full, selected_columns)

        st.caption(
            f"Anchor column: {anchor_col} | "
            f"Visible rows: {len(stacked_df)} / {len(df_full)}"
        )

        st.dataframe(stacked_df, use_container_width=True)


