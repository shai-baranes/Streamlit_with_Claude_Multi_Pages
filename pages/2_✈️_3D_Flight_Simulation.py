"""Interactive 3D playback for the active session's trajectory fields."""

from framework.state import ui
from framework.trajectory import (
    SECONDARY_TRAJECTORY_COLUMNS,
    missing_trajectory_columns,
    prepare_trajectory,
    trajectory_identity,
)
from framework.trajectory_chart import render_trajectory_player, reset_trajectory_player
from utils import require_data


st = ui(__file__)
MAX_ANIMATION_FRAMES = 300

st.set_page_config(page_title="3D flight simulation", layout="wide")
st.title("3D flight simulation")
# st.caption(
#     "Gray = complete route · Blue = traveled route · Red aircraft = current position"
# )

df_full = require_data()
missing = missing_trajectory_columns(df_full)
if missing:
    st.warning(
        "This simulation requires these loaded fields: " + ", ".join(missing) + "."
    )
    st.info(
        "Return to Load CSV and include the missing fields, or load the bundled sample data."
    )
    st.stop()

prepared = prepare_trajectory(df_full, MAX_ANIMATION_FRAMES)
trajectory = prepared.frame
secondary_present = [
    column for column in SECONDARY_TRAJECTORY_COLUMNS if column in df_full.columns
]
if secondary_present and len(secondary_present) != len(SECONDARY_TRAJECTORY_COLUMNS):
    # Partial optional coordinates cannot describe a second 3D aircraft safely.
    st.info(
        "The secondary route needs all three optional fields: "
        + ", ".join(SECONDARY_TRAJECTORY_COLUMNS)
        + ". Showing the primary route only."
    )
if prepared.invalid_rows:
    st.warning(
        f"Ignored {prepared.invalid_rows:,} rows with missing, nonnumeric, or out-of-range coordinates."
    )
if len(trajectory) < 2:
    st.info("At least two valid trajectory records are required for simulation.")
    st.stop()
if prepared.reduced:
    st.caption(
        f"Playback uses {len(trajectory):,} evenly distributed frames from "
        f"{prepared.source_rows:,} source rows to keep browser animation responsive."
    )
    # st.info(
    #     f"Playback uses {len(trajectory):,} evenly distributed frames from "
    #     f"{prepared.source_rows:,} source rows to keep browser animation responsive."
    # )

dataset = st.session_state.get("dataset")
identity = trajectory_identity(df_full, getattr(dataset, "version", None))
if st.session_state.get("trajectory_identity") != identity:
    # Dataset replacement resets only this browser session's player and camera.
    st.session_state["trajectory_identity"] = identity
    reset_trajectory_player()

# Playback and Plotly interaction share one browser component, so frame updates cannot
# remount the chart or replace a camera chosen with any of Plotly's manipulation modes.
render_trajectory_player(trajectory)
