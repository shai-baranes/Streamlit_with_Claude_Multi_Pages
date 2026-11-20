import streamlit as st
# Namespace widget persistence so legacy pages retain independent selections.
from framework.state import current_html_export, ui
st = ui(__file__)
import pandas as pd
from framework.analysis import chronological_order
from framework.stacked_presets import MAX_NAME_LENGTH, VIEW_MODES, PresetError, PresetStore

from utils import inject_css, require_data, sidebar_filters
from st_aggrid import AgGrid, GridOptionsBuilder, DataReturnMode, JsCode
# Bound grid transport while retaining the selected source-row preview.
from framework.grid import AgGrid


st.set_page_config(page_title="Stacked Values", page_icon="📈", layout="wide")
inject_css()

st = st.exportable_page(
    title="Stacked Values",
    help="Includes every loaded column and every row matching the current sidebar filters.",
)
st.title("📈 Stacked Values")

TIME_COLUMN_CANDIDATES = ["Seconds"]
DELTA_SECONDS_COLUMN = "Dt [seconds]"


def get_time_column(df: pd.DataFrame) -> str:
    for col in TIME_COLUMN_CANDIDATES:
        if col in df.columns:
            return col
    st.info("Select the Seconds field on the upload page to use this table.")
    st.stop()
    raise KeyError("Could not find the Seconds column in the dataframe.")


def init_state() -> None:
    defaults = {
        "selected_columns_ordered": [],
        "view_mode": "Stacked by Left",
        "selected_source_row": None,
        "aggrid_mount_id": 0,
        "pending_restore_scroll": False,
        "stacked_exclusion_cols": [],
        "stacked_exclusion_cols_widget": [],
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

    ordered = previous_still_selected + newly_added
    st.session_state[state_key] = ordered
    if ordered != previous_ordered_selection:
        clear_preset_name()

    set_exclusions(st.session_state["stacked_exclusion_cols"])
    mark_grid_for_remount_and_restore()


def on_view_mode_change() -> None:
    # Keep the last valid exclusion selection while the control is hidden in
    # other modes so returning to Stacked by All reapplies it immediately.
    clear_preset_name()
    mark_grid_for_remount_and_restore()


def set_exclusions(exclusions) -> None:
    columns = st.session_state["selected_columns_ordered"]
    valid = [c for c in exclusions if c in columns][:max(0, len(columns) - 1)]
    st.session_state["stacked_exclusion_cols"] = valid
    st.set_widget_value("stacked_exclusion_cols_widget", valid)


def on_exclusion_change() -> None:
    previous = st.session_state["stacked_exclusion_cols"]
    set_exclusions(st.session_state["stacked_exclusion_cols_widget"])
    if st.session_state["stacked_exclusion_cols"] != previous:
        clear_preset_name()
    mark_grid_for_remount_and_restore()


def clear_preset_name() -> None:
    st.session_state.pop("active_preset_id", None)
    st.set_widget_value("preset_name", "")


def add_dt_seconds_column(out: pd.DataFrame, time_col: str) -> pd.DataFrame:
    out = out.copy()
    # The duplicated page treats Seconds as elapsed numeric time and preserves
    # fractional differences such as the sample dataset's 0.5-second cadence.
    elapsed_seconds = pd.to_numeric(out[time_col], errors="coerce")
    out[DELTA_SECONDS_COLUMN] = elapsed_seconds.diff().round(3)
    out[DELTA_SECONDS_COLUMN] = out[DELTA_SECONDS_COLUMN].astype(object)

    if not out.empty:
        out.iloc[0, out.columns.get_loc(DELTA_SECONDS_COLUMN)] = "-"

    out.insert(2, DELTA_SECONDS_COLUMN, out.pop(DELTA_SECONDS_COLUMN))
    return out


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
    # Numeric ordering prevents negative elapsed values when upstream sales
    # normalization has grouped rows by repeated dates.
    df = chronological_order(df, time_col, numeric=True)
    anchor_col = selected_columns[0]
    data_cols = [c for c in selected_columns if c != time_col]
    compare_cols = [c for c in data_cols if c not in exclusion_cols]

    if not compare_cols and data_cols:
        compare_cols = [data_cols[0]]

    extra_cols = [c for c in selected_columns[1:] if c not in {time_col, anchor_col}]
    result_cols = [time_col, anchor_col] + extra_cols

    if view_mode == "Full":
        out = df.loc[:, result_cols].copy()

    elif view_mode == "Stacked by Left":
        mask = df[anchor_col].ne(df[anchor_col].shift())
        out = df.loc[mask, result_cols].copy()

    elif view_mode == "Stacked by All":
        if not data_cols:
            out = df.loc[:, result_cols].copy()
        else:
            changed_mask = df[compare_cols].ne(df[compare_cols].shift()).any(axis=1)
            out = df.loc[changed_mask, result_cols].copy()

    else:
        raise ValueError(f"Unsupported view mode: {view_mode}")

    out.insert(0, "_source_row", out.index.astype(str))

    if time_col in out.columns:
        out = add_dt_seconds_column(out, time_col)

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
    gb.configure_column(
        time_col, width=130, minWidth=100, maxWidth=180, pinned="left", sort="asc"
    )

    if DELTA_SECONDS_COLUMN in view_df.columns:
        # Pin the derived delta beside Seconds so AgGrid draws its pinned-column
        # separator after Dt [seconds], keeping the two time fields together.
        gb.configure_column(
            DELTA_SECONDS_COLUMN,
            width=105,
            minWidth=95,
            maxWidth=130,
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

selectable_columns = [c for c in df_filtered.columns if c != time_col]


def select_preset(presets) -> None:
    selected = presets.get(st.session_state.get("preset_choice"))
    # Keep the revision the user saw when they chose the preset.
    st.session_state["preset_edit_target"] = selected
    st.session_state.pop("preset_delete_target", None)
    st.session_state.pop("last_preset_apply", None)


def preset_apply_state(preset) -> tuple:
    return (
        preset.id,
        preset.revision,
        tuple(st.session_state["selected_columns_ordered"]),
        tuple(st.session_state["stacked_exclusion_cols"]),
        st.session_state["view_mode"],
        st.session_state.get("preset_name", ""),
    )


def apply_preset(preset) -> None:
    available = set(selectable_columns)
    columns = [c for c in preset.columns if c in available]
    if not columns:
        st.warning("None of this preset’s display columns are loaded. Apply the needed columns on the CSV loader page first.")
        return
    st.session_state["selected_columns_ordered"] = columns
    st.set_widget_value("selected_columns_widget", columns)
    set_exclusions(preset.exclusions)
    if preset.view_mode is not None:
        st.set_widget_value("view_mode", preset.view_mode)
    mark_grid_for_remount_and_restore()
    st.session_state["active_preset_id"] = preset.id
    # Retain the applied revision even after editing settings clears the name.
    st.session_state["preset_update_target"] = preset
    st.set_widget_value("preset_name", preset.name)
    st.session_state["last_preset_apply"] = preset_apply_state(preset)

    missing = [c for c in preset.columns if c not in available]
    omitted = [c for c in preset.exclusions if c not in st.session_state["stacked_exclusion_cols"]]
    if missing:
        st.text("Unavailable display columns: " + ", ".join(missing))
    if omitted:
        st.text("Exclusions omitted to match the loaded columns and keep at least one column in change detection: "
                + ", ".join(omitted))


def render_presets() -> None:
    store = PresetStore()
    with st.expander("Presets"):
        # Tint the label text area while leaving the native controls untouched.
        st.html("""
            <style>
            .st-key-seconds-saved-presets [data-testid="stWidgetLabel"] p,
            .st-key-seconds-active-preset [data-testid="stWidgetLabel"] p {
                width: fit-content;
                padding: 0.125rem 0.375rem;
                border-radius: 0.25rem;
            }
            .st-key-seconds-saved-presets [data-testid="stWidgetLabel"] p {
                background-color: rgb(59 130 246 / 16%);
            }
            .st-key-seconds-active-preset [data-testid="stWidgetLabel"] p {
                background-color: rgb(34 197 94 / 16%);
            }
            </style>
        """)
        # Save and delete run after the name widget has already rendered.
        saved_name = st.session_state.pop("preset_name_after_action", None)
        if saved_name is not None:
            st.set_widget_value("preset_name", saved_name)
        st.caption("Presets are shared with everyone on this server. Exclusions affect Stacked by All.")
        notice = st.session_state.pop("preset_notice", None)
        if notice:
            st.success(notice)
        try:
            presets = {preset.id: preset for preset in store.list()}
        except PresetError as exc:
            st.error(str(exc))
            return

        updated_id = st.session_state.pop("preset_choice_after_update", None)
        if updated_id in presets:
            st.set_widget_value("preset_choice", updated_id)
        with st.container(key="seconds-saved-presets"):
            selected_id = st.selectbox(
                "Saved presets",
                options=list(presets),
                index=None,
                placeholder="Choose a preset",
                format_func=lambda key: presets[key].name,
                key="preset_choice",
                on_change=select_preset,
                args=(presets,),
            )
        selected = presets.get(selected_id)
        # Process the click against the latest saved revision before rendering the button.
        apply_button = st.container()
        if st.session_state.pop("preset_apply_requested", False) and selected is not None:
            select_preset(presets)
            apply_preset(selected)
        apply_button.button(
            "Apply preset",
            disabled=selected is None or preset_apply_state(selected) == st.session_state.get("last_preset_apply"),
            on_click=st.session_state.__setitem__,
            args=("preset_apply_requested", True),
        )

        with st.container(key="seconds-active-preset"):
            name = st.text_input("Active preset", key="preset_name", max_chars=MAX_NAME_LENGTH)
        applied = st.session_state.get("preset_update_target")
        can_update = applied is not None and applied.id in presets
        target = st.session_state.get("preset_edit_target")
        can_edit = selected is not None and target is not None and target.id == selected.id
        if target is not None and (not can_edit or target.revision != selected.revision):
            st.warning("Apply the latest version of this preset before editing."
                       if can_edit else "The selected preset was deleted. Choose another preset.")
        pending = st.session_state.get("preset_delete_target")
        with st.container(horizontal=True):
            save_new = st.button(
                "Save new",
                disabled=pending is not None,
                help="Enter the new preset’s name in the Active preset field before saving.",
            )
            update = st.button(
                "Update selected",
                disabled=not can_update or pending is not None,
                help=f"Update the last applied preset: {applied.name}" if can_update
                else "Apply a preset before updating it.",
            )
            if st.button("Delete selected", disabled=not can_edit or pending is not None):
                pending = st.session_state["preset_delete_target"] = target

        confirm = False
        if pending is not None:
            st.warning("Deleting this preset removes it for everyone on this server.")
            st.text(pending.name)
            with st.container(horizontal=True):
                confirm = st.button("Confirm delete")
                if st.button("Cancel deletion"):
                    st.session_state.pop("preset_delete_target", None)
                    st.rerun()

        try:
            if confirm:
                st.session_state.pop("preset_delete_target", None)
                store.delete(pending)
                st.session_state.pop("preset_edit_target", None)
                if st.session_state.get("active_preset_id") == pending.id:
                    st.session_state.pop("active_preset_id")
                    st.session_state["preset_name_after_action"] = ""
                if applied is not None and applied.id == pending.id:
                    st.session_state.pop("preset_update_target")
                st.session_state["preset_notice"] = "Preset deleted."
                st.rerun()
            if save_new or update:
                saved = store.save(
                    (name.strip() or applied.name) if update else name,
                    st.session_state["selected_columns_ordered"],
                    st.session_state["stacked_exclusion_cols"],
                    view_mode=st.session_state["view_mode"],
                    previous=applied if update else None,
                )
                if update:
                    st.session_state["preset_edit_target"] = saved
                    st.session_state["preset_update_target"] = saved
                    st.session_state["preset_choice_after_update"] = saved.id
                st.session_state["active_preset_id"] = saved.id
                st.session_state["preset_name_after_action"] = saved.name
                st.session_state["preset_notice"] = "Preset updated." if update else "Preset saved."
                st.rerun()
        except PresetError as exc:
            st.error(str(exc))


@st.fragment
def render_stacked_table() -> None:
    st.subheader("Stacked event table")
    render_presets()

    st.multiselect(
        "Select columns to display",
        options=selectable_columns,
        key="selected_columns_widget",
        on_change=on_selected_columns_change,
        args=("selected_columns_widget", "selected_columns_ordered"),
        help="The first selected column is the anchor column. Seconds and Dt [seconds] are always shown on the left.",
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

    if st.session_state["view_mode"] == "Stacked by All" and selected_columns:
        # The widget may have been removed during a run in another view mode.
        set_exclusions(st.session_state["stacked_exclusion_cols"])
        st.multiselect(
            "Exclusion rule",
            options=selected_columns,
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
        selected_source_row=st.session_state.get("selected_source_row"),
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

    visible_df = pd.DataFrame(grid_response["data"])


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
    

    # ── Download ──────────────────────────────────────────────────────────────────
    # Generate the full export only after an explicit request.
    if st.button("Prepare CSV export"):
        st.download_button(
            label="⬇️ Download filtered data as CSV",
            data=visible_df.to_csv(index=False).encode("utf-8"),
            file_name="filtered_sales_data.csv",
            mime="text/csv",
        )

    st.markdown("---")
    st.caption(f"Showing {len(visible_df):,} of {len(df_full):,} records")


report = current_html_export()
if report is None:
    render_stacked_table()
else:
    # The offline controls replace the fragment in the report, while it stays live here.
    st.begin_export_exclusion()
    try:
        render_stacked_table()
    finally:
        st.end_export_exclusion()
    from framework.stacked_export import export_stacked_table
    export_stacked_table(report, df_filtered, st.session_state)
st.finish_html_export() # end section of HTML export (started as: 'st = st.exportable_page(title="Stacked Values")' - usually end of file)