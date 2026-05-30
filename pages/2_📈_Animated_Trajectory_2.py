import streamlit as st
import numpy as np
import pandas as pd
import plotly.graph_objects as go

st.set_page_config(page_title="Trajectory Animation", layout="wide")

st.title("Animated trajectory")
st.caption("Gray = full route, Blue = achieved route, Dark blue = current position")

# ── Synthetic geo dataset ─────────────────────────────────────────────────────
np.random.seed(42)
_n = 40
_t_vals = np.linspace(0, 39, _n)
_lat_base = np.linspace(32.05, 33.20, _n)
_lon_base = np.linspace(34.75, 34.55, _n)

_lat_vals = (
    _lat_base
    + 0.04 * np.sin(_t_vals * 0.7)
    + np.random.normal(0, 0.008, _n)
).round(5)

_lon_vals = (
    _lon_base
    + 0.03 * np.cos(_t_vals * 0.5)
    + np.random.normal(0, 0.006, _n)
).round(5)

geo_df = pd.DataFrame(
    {
        "Time": _t_vals.round(1),
        "Latitude": _lat_vals,
        "Longitude": _lon_vals,
    }
).sort_values("Time").reset_index(drop=True)

st.caption(
    f"Route · {len(geo_df)} steps · "
    f"lat {geo_df['Latitude'].min():.3f}–{geo_df['Latitude'].max():.3f} · "
    f"lon {geo_df['Longitude'].min():.3f}–{geo_df['Longitude'].max():.3f}"
)

# ── UI controls ───────────────────────────────────────────────────────────────
c1, c2, c3 = st.columns([1, 1, 1])
with c1:
    zoom = st.slider("Zoom", min_value=6, max_value=15, value=9)
with c2:
    marker_size = st.slider("Current marker size", min_value=8, max_value=24, value=16)
with c3:
    frame_duration = st.slider("Frame duration (ms)", min_value=100, max_value=1200, value=350, step=50)

show_points = st.toggle("Show all route points", value=False)

# ── Derived values ────────────────────────────────────────────────────────────
center_lat = geo_df["Latitude"].mean()
center_lon = geo_df["Longitude"].mean()

# Base traces shown before animation starts
full_route_trace = go.Scattermap(
    lat=geo_df["Latitude"],
    lon=geo_df["Longitude"],
    mode="lines",
    name="Full trajectory",
    line=dict(color="rgba(140,140,140,0.85)", width=4),
    hoverinfo="skip",
)

achieved_trace = go.Scattermap(
    lat=[geo_df.loc[0, "Latitude"]],
    lon=[geo_df.loc[0, "Longitude"]],
    mode="lines",
    name="Achieved trajectory",
    line=dict(color="#1976D2", width=5),
    hoverinfo="skip",
)

current_trace = go.Scattermap(
    lat=[geo_df.loc[0, "Latitude"]],
    lon=[geo_df.loc[0, "Longitude"]],
    mode="markers+text",
    name="Current position",
    marker=dict(size=marker_size, color="#0D47A1"),
    text=[f"T={geo_df.loc[0, 'Time']}"],
    textposition="top right",
    hovertemplate=(
        "Time=%{text}<br>"
        "Lat=%{lat:.5f}<br>"
        "Lon=%{lon:.5f}<extra></extra>"
    ),
)

traces = [full_route_trace, achieved_trace, current_trace]

if show_points:
    traces.append(
        go.Scattermap(
            lat=geo_df["Latitude"],
            lon=geo_df["Longitude"],
            mode="markers",
            name="All samples",
            marker=dict(size=6, color="rgba(24,95,165,0.45)"),
            hovertemplate=(
                "Lat=%{lat:.5f}<br>"
                "Lon=%{lon:.5f}<extra></extra>"
            ),
        )
    )

# Frames
frames = []
for i in range(len(geo_df)):
    frame_traces = [
        go.Scattermap(
            lat=geo_df["Latitude"],
            lon=geo_df["Longitude"],
            mode="lines",
            line=dict(color="rgba(140,140,140,0.85)", width=4),
            hoverinfo="skip",
        ),
        go.Scattermap(
            lat=geo_df.loc[:i, "Latitude"],
            lon=geo_df.loc[:i, "Longitude"],
            mode="lines",
            line=dict(color="#1976D2", width=5),
            hoverinfo="skip",
        ),
        go.Scattermap(
            lat=[geo_df.loc[i, "Latitude"]],
            lon=[geo_df.loc[i, "Longitude"]],
            mode="markers+text",
            marker=dict(size=marker_size, color="#0D47A1"),
            text=[f"{geo_df.loc[i, 'Time']}"],
            textposition="top right",
            hovertemplate=(
                "Time=%{text}<br>"
                "Lat=%{lat:.5f}<br>"
                "Lon=%{lon:.5f}<extra></extra>"
            ),
        ),
    ]

    if show_points:
        frame_traces.append(
            go.Scattermap(
                lat=geo_df["Latitude"],
                lon=geo_df["Longitude"],
                mode="markers",
                marker=dict(size=6, color="rgba(24,95,165,0.45)"),
                hovertemplate=(
                    "Lat=%{lat:.5f}<br>"
                    "Lon=%{lon:.5f}<extra></extra>"
                ),
            )
        )

    frames.append(go.Frame(name=str(i), data=frame_traces))

fig = go.Figure(data=traces, frames=frames)

fig.update_layout(
    height=650,
    margin=dict(l=10, r=10, t=60, b=10),
    paper_bgcolor="#f5f7fa",
    plot_bgcolor="#f5f7fa",
    title="Position over time",
    map=dict(
        style="open-street-map",
        zoom=zoom,
        center=dict(lat=center_lat, lon=center_lon),
    ),
    updatemenus=[
        dict(
            type="buttons",
            direction="left",
            x=0.0,
            y=1.02,
            showactive=False,
            buttons=[
                dict(
                    label="▶ Play",
                    method="animate",
                    args=[
                        None,
                        dict(
                            frame=dict(duration=frame_duration, redraw=True),
                            transition=dict(duration=0),
                            fromcurrent=True,
                        ),
                    ],
                ),
                dict(
                    label="⏸ Pause",
                    method="animate",
                    args=[
                        [None],
                        dict(
                            frame=dict(duration=0, redraw=False),
                            transition=dict(duration=0),
                            mode="immediate",
                        ),
                    ],
                ),
            ],
        )
    ],
    sliders=[
        dict(
            active=0,
            x=0.12,
            y=0.02,
            len=0.82,
            currentvalue=dict(prefix="Step: "),
            pad=dict(t=30),
            steps=[
                dict(
                    label=str(geo_df.loc[i, "Time"]),
                    method="animate",
                    args=[
                        [str(i)],
                        dict(
                            frame=dict(duration=0, redraw=True),
                            transition=dict(duration=0),
                            mode="immediate",
                        ),
                    ],
                )
                for i in range(len(geo_df))
            ],
        )
    ],
    legend=dict(
        orientation="h",
        yanchor="bottom",
        y=0.98,
        xanchor="right",
        x=1.0,
    ),
)

st.plotly_chart(fig, theme=None)