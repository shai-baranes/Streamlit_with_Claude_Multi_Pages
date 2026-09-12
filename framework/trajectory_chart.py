"""A browser-side Plotly flight player with session-persisted controls and camera."""

from importlib.resources import files
import json

import pandas as pd
import plotly
import streamlit as st


DEFAULT_CAMERA = {"eye": {"x": 1.55, "y": -1.65, "z": 1.1}}
DEFAULT_FPS = 5
TRAJECTORY_COMPONENT_KEY = "trajectory_3d_component"

_PLOTLY_SOURCE = (
    files(plotly).joinpath("package_data", "plotly.min.js").read_text(encoding="utf-8")
)

_COMPONENT_JS = _PLOTLY_SOURCE + r"""

const trajectoryPlayers = new WeakMap()

export default async function(component) {
  const {data, parentElement, setStateValue} = component
  const plot = parentElement.querySelector("#trajectory-plot")
  if (!plot) return

  let player = trajectoryPlayers.get(parentElement)
  if (!player) {
    player = {
      state: {...data.initialState}, timer: null, cameraTimer: null,
      rendering: false, setStateValue,
    }
    trajectoryPlayers.set(parentElement, player)
  } else {
    // A remount receives the last state saved by this browser session.
    player.state = {...player.state, ...data.initialState}
    player.setStateValue = setStateValue
  }

  const rows = data.rows
  const lastIndex = Math.max(0, rows.length - 1)
  player.state.index = Math.min(Math.max(Number(player.state.index) || 0, 0), lastIndex)
  player.state.fps = Math.min(Math.max(Number(player.state.fps) || 5, 1), 10)
  player.state.camera = player.state.camera || data.defaultCamera

  const status = parentElement.querySelector("#trajectory-status")
  const elapsed = parentElement.querySelector("#trajectory-elapsed")
  const altitude = parentElement.querySelector("#trajectory-altitude")
  const position = parentElement.querySelector("#trajectory-position")
  const frame = parentElement.querySelector("#trajectory-frame")
  const progress = parentElement.querySelector("#trajectory-progress")
  const progressText = parentElement.querySelector("#trajectory-progress-text")
  const fps = parentElement.querySelector("#trajectory-fps")
  const fpsValue = parentElement.querySelector("#trajectory-fps-value")

  function saveState() {
    // Clone the object so Streamlit receives a new serializable state value.
    player.setStateValue("simulation", JSON.parse(JSON.stringify(player.state)))
  }

  function renderMetrics() {
    const current = rows[player.state.index]
    const ratio = rows.length ? (player.state.index + 1) / rows.length : 0
    status.textContent = player.state.status[0].toUpperCase() + player.state.status.slice(1)
    elapsed.textContent = `${current.Seconds.toFixed(1)} s`
    altitude.textContent = `${Math.round(current.Altitude).toLocaleString()} m`
    position.textContent = `${current.latitude.toFixed(4)}, ${current.longitude.toFixed(4)}`
    frame.textContent = `${(player.state.index + 1).toLocaleString()} / ${rows.length.toLocaleString()}`
    progress.value = ratio * 100
    progressText.textContent = `Trajectory progress: ${(ratio * 100).toFixed(1)}%`
    fps.value = String(player.state.fps)
    fpsValue.textContent = String(player.state.fps)
  }

  async function renderPlot() {
    const achieved = rows.slice(0, player.state.index + 1)
    const current = rows[player.state.index]
    const traces = [
      {
        type: "scatter3d", mode: "lines", name: "Complete route",
        x: rows.map(row => row.longitude), y: rows.map(row => row.latitude),
        z: rows.map(row => row.Altitude / 1000),
        line: {color: "rgba(120, 130, 145, 0.55)", width: 4}, hoverinfo: "skip",
      },
      {
        type: "scatter3d", mode: "lines", name: "Traveled route",
        x: achieved.map(row => row.longitude), y: achieved.map(row => row.latitude),
        z: achieved.map(row => row.Altitude / 1000),
        customdata: achieved.map(row => [row.Altitude]),
        line: {color: "#2563eb", width: 7},
        hovertemplate: "Longitude=%{x:.5f}<br>Latitude=%{y:.5f}<br>Altitude=%{customdata[0]:,.0f} m<extra></extra>",
      },
      {
        type: "scatter3d", mode: "markers", showlegend: false, hoverinfo: "skip",
        x: [current.longitude], y: [current.latitude], z: [current.Altitude / 1000],
        marker: {color: "rgba(220, 38, 38, 0.24)", size: 22},
      },
      {
        type: "scatter3d", mode: "markers+text", name: "Flight object",
        x: [current.longitude], y: [current.latitude], z: [current.Altitude / 1000],
        marker: {color: "#dc2626", size: 12, symbol: "diamond", line: {color: "#ffffff", width: 3}},
        text: ["✈"], textfont: {color: "#991b1b", size: 24}, textposition: "top center",
        customdata: [[current.Seconds, current.Altitude]],
        hovertemplate: "Seconds=%{customdata[0]:.1f}<br>Longitude=%{x:.5f}<br>Latitude=%{y:.5f}<br>Altitude=%{customdata[1]:,.0f} m<extra></extra>",
      },
    ]
    const layout = {
      height: 650, margin: {l: 0, r: 0, t: 20, b: 0},
      legend: {orientation: "h", y: 1.02, x: 0},
      scene: {
        xaxis: {title: {text: "Longitude (°)"}},
        yaxis: {title: {text: "Latitude (°)"}},
        zaxis: {title: {text: "Altitude (km)"}},
        aspectmode: "manual", aspectratio: {x: 1.25, y: 1.5, z: 0.9},
        camera: player.state.camera,
      },
    }
    player.rendering = true
    const config = {responsive: true, displaylogo: false}
    if (typeof plot.on === "function") {
      await window.Plotly.react(plot, traces, layout, config)
    } else {
      // The first render must initialize Plotly's event-emitting graph element.
      await window.Plotly.newPlot(plot, traces, layout, config)
    }
    player.rendering = false
  }

  function stopTimer() {
    if (player.timer !== null) clearInterval(player.timer)
    player.timer = null
  }

  function startTimer() {
    stopTimer()
    if (player.state.status !== "playing") return
    player.timer = setInterval(async () => {
      if (player.state.index >= lastIndex) {
        player.state.status = "stopped"
        stopTimer()
        saveState()
      } else {
        player.state.index += 1
      }
      renderMetrics()
      await renderPlot()
    }, 1000 / player.state.fps)
  }

  parentElement.querySelector("#trajectory-play").onclick = async () => {
    if (player.state.index >= lastIndex) player.state.index = 0
    player.state.status = "playing"
    saveState(); renderMetrics(); await renderPlot(); startTimer()
  }
  parentElement.querySelector("#trajectory-pause").onclick = () => {
    player.state.status = "paused"
    stopTimer(); saveState(); renderMetrics()
  }
  parentElement.querySelector("#trajectory-stop").onclick = () => {
    player.state.status = "stopped"
    stopTimer(); saveState(); renderMetrics()
  }
  parentElement.querySelector("#trajectory-reset").onclick = async () => {
    player.state = {index: 0, status: "stopped", fps: 5, camera: data.defaultCamera}
    stopTimer(); saveState(); renderMetrics(); await renderPlot()
  }
  fps.oninput = () => {
    player.state.fps = Number(fps.value)
    fpsValue.textContent = fps.value
    saveState(); startTimer()
  }

  renderMetrics()
  await renderPlot()
  if (!player.listening) {
    player.listening = true
    plot.on("plotly_relayout", event => {
      if (player.rendering || !event?.["scene.camera"]) return
      player.state.camera = event["scene.camera"]
      clearTimeout(player.cameraTimer)
      // Persist the final camera from every Plotly rotation mode after dragging ends.
      player.cameraTimer = setTimeout(saveState, 100)
    })
  }
  startTimer()
}
"""

_TRAJECTORY_COMPONENT = st.components.v2.component(
    "trajectory_flight_player",
    html="""
<div class="controls">
  <button id="trajectory-play" type="button">▶ Play</button>
  <button id="trajectory-pause" type="button">⏸ Pause</button>
  <button id="trajectory-stop" type="button">■ Stop</button>
  <button id="trajectory-reset" type="button">↻ Reset</button>
</div>
<label class="fps-label" for="trajectory-fps">Playback rate (frames per second): <strong id="trajectory-fps-value">5</strong></label>
<input id="trajectory-fps" type="range" min="1" max="10" step="1" value="5" />
<div class="metrics">
  <div><span>Status</span><strong id="trajectory-status"></strong></div>
  <div><span>Elapsed</span><strong id="trajectory-elapsed"></strong></div>
  <div><span>Altitude</span><strong id="trajectory-altitude"></strong></div>
  <div><span>Position</span><strong id="trajectory-position"></strong></div>
  <div><span>Frame</span><strong id="trajectory-frame"></strong></div>
</div>
<label id="trajectory-progress-text" for="trajectory-progress"></label>
<progress id="trajectory-progress" min="0" max="100"></progress>
<div id="trajectory-plot"></div>
""",
    css="""
.controls { display: flex; gap: .75rem; flex-wrap: wrap; margin-bottom: 1rem; }
button { border: 1px solid var(--st-border-color); border-radius: .55rem; padding: .55rem 1rem; background: var(--st-secondary-background-color); color: var(--st-text-color); cursor: pointer; font: inherit; }
#trajectory-play { background: var(--st-primary-color); color: white; }
.fps-label { display: block; margin-bottom: .35rem; color: var(--st-text-color); }
#trajectory-fps, #trajectory-progress { width: 100%; accent-color: var(--st-primary-color); }
.metrics { display: grid; grid-template-columns: repeat(5, minmax(0, 1fr)); gap: 1rem; margin: 1.25rem 0; color: var(--st-text-color); }
.metrics div { display: flex; flex-direction: column; gap: .25rem; min-width: 0; }
.metrics span { font-size: .9rem; }
.metrics strong { font-size: 1.55rem; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
#trajectory-progress-text { display: block; margin-bottom: .3rem; color: var(--st-text-color); }
#trajectory-plot { width: 100%; height: 650px; }
@media (max-width: 800px) { .metrics { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
""",
    js=_COMPONENT_JS,
)


def reset_trajectory_player(key: str = TRAJECTORY_COMPONENT_KEY) -> None:
    """Restore playback and camera defaults before mounting a replaced dataset."""

    st.session_state[key] = {
        "simulation": {
            "index": 0,
            "status": "stopped",
            "fps": DEFAULT_FPS,
            "camera": DEFAULT_CAMERA,
        }
    }


def render_trajectory_player(
    route: pd.DataFrame,
    *,
    key: str = TRAJECTORY_COMPONENT_KEY,
) -> None:
    """Mount one persistent browser player for the validated trajectory."""

    component_state = st.session_state.get(key, {})
    simulation = component_state.get("simulation") if hasattr(component_state, "get") else None
    if not simulation:
        simulation = {"index": 0, "status": "stopped", "fps": DEFAULT_FPS, "camera": DEFAULT_CAMERA}
    # JSON normalization converts pandas and NumPy scalar values for the frontend.
    rows = json.loads(route[["Seconds", "longitude", "latitude", "Altitude"]].to_json(orient="records"))
    _TRAJECTORY_COMPONENT(
        key=key,
        data={"rows": rows, "initialState": simulation, "defaultCamera": DEFAULT_CAMERA},
        width="stretch",
        height=900,
        on_simulation_change=lambda: None,
    )
