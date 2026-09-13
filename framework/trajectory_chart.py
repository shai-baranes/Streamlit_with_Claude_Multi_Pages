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

_COMPONENT_JS = (
    _PLOTLY_SOURCE
    + r"""

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
  const playButton = parentElement.querySelector("#trajectory-play")
  const pauseButton = parentElement.querySelector("#trajectory-pause")
  const resetButton = parentElement.querySelector("#trajectory-reset")

  function saveState() {
    // Clone the object so Streamlit receives a new serializable state value.
    player.setStateValue("simulation", JSON.parse(JSON.stringify(player.state)))
  }

  function renderMetrics() {
    const current = rows[player.state.index]
    const ratio = lastIndex ? player.state.index / lastIndex : 0
    status.textContent = player.state.status[0].toUpperCase() + player.state.status.slice(1)
    elapsed.textContent = `${current.Seconds.toFixed(1)} s`
    altitude.textContent = `${Math.round(current.Altitude).toLocaleString()} m`
    position.textContent = `${current.latitude.toFixed(4)}, ${current.longitude.toFixed(4)}`
    frame.textContent = `${(player.state.index + 1).toLocaleString()} / ${rows.length.toLocaleString()}`
    progress.max = String(lastIndex)
    progress.value = String(player.state.index)
    progressText.textContent = `Trajectory progress: ${(ratio * 100).toFixed(1)}%`
    fps.value = String(player.state.fps)
    fpsValue.textContent = String(player.state.fps)
    const playing = player.state.status === "playing"
    const paused = player.state.status === "paused"
    // Persistent colors and pressed semantics make the active action unmistakable.
    playButton.classList.toggle("is-active", playing)
    pauseButton.classList.toggle("is-active", paused)
    playButton.setAttribute("aria-pressed", String(playing))
    pauseButton.setAttribute("aria-pressed", String(paused))
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
      height: 650, margin: {l: 58, r: 0, t: 20, b: 0},
      legend: {orientation: "h", y: 1.02, x: 0},
      // Reserve the plot's left margin for one vertical manipulation toolbar.
      modebar: {orientation: "v"},
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
    const modebar = plot.querySelector(".modebar")
    if (modebar) {
      // Plotly injects toolbar styles after component CSS, so enforce the left strip here.
      Object.assign(modebar.style, {
        position: "absolute", display: "flex", flexFlow: "column nowrap", left: "4px", right: "auto",
        top: "auto", bottom: "8px", transform: "none", width: "auto",
      })
      modebar.querySelectorAll(".modebar-group").forEach(group => {
        Object.assign(group.style, {
          display: "flex", flexFlow: "column nowrap", float: "none", width: "auto",
        })
      })
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

  playButton.onclick = async () => {
    if (player.state.index >= lastIndex) player.state.index = 0
    player.state.status = "playing"
    saveState(); renderMetrics(); await renderPlot(); startTimer()
  }
  pauseButton.onclick = () => {
    player.state.status = "paused"
    stopTimer(); saveState(); renderMetrics()
  }
  resetButton.onclick = async () => {
    resetButton.classList.remove("reset-feedback")
    void resetButton.offsetWidth
    resetButton.classList.add("reset-feedback")
    player.state = {index: 0, status: "stopped", fps: 5, camera: data.defaultCamera}
    stopTimer(); renderMetrics(); await renderPlot()
    clearTimeout(player.resetTimer)
    // Delay the rerun-producing state save until the temporary gray feedback is visible.
    player.resetTimer = setTimeout(() => {
      resetButton.classList.remove("reset-feedback")
      saveState()
    }, 200)
  }
  fps.oninput = () => {
    player.state.fps = Number(fps.value)
    fpsValue.textContent = fps.value
    // Restart locally so the new rate takes effect without a Streamlit rerun.
    startTimer()
  }
  fps.onchange = () => {
    // Persist only the committed value so dragging remains responsive during playback.
    saveState()
  }
  progress.onpointerdown = () => {
    // Freeze automatic advancement while the user scrubs to a precise frame.
    stopTimer()
  }
  progress.oninput = async () => {
    player.state.index = Number(progress.value)
    renderMetrics()
    await renderPlot()
  }
  progress.onchange = () => {
    // Save the chosen frame once per completed seek, then resume if Play is active.
    saveState()
    startTimer()
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
)

_TRAJECTORY_COMPONENT = st.components.v2.component(
    "trajectory_flight_player",
    html="""
<div class="controls">
  <button id="trajectory-play" type="button">▶ Play</button>
  <button id="trajectory-pause" type="button">⏸ Pause</button>
  <button id="trajectory-reset" type="button">↻ Reset</button>
</div>
<div class="metrics">
  <div><span>Status</span><strong id="trajectory-status"></strong></div>
  <div><span>Elapsed</span><strong id="trajectory-elapsed"></strong></div>
  <div><span>Altitude</span><strong id="trajectory-altitude"></strong></div>
  <div><span>Position</span><strong id="trajectory-position"></strong></div>
  <div><span>Frame</span><strong id="trajectory-frame"></strong></div>
</div>
<div id="trajectory-plot"></div>
<div class="slider-control">
  <label id="trajectory-progress-text" for="trajectory-progress"></label>
  <input id="trajectory-progress" type="range" min="0" max="0" step="1" value="0" />
</div>
<div class="slider-control">
  <label class="fps-label" for="trajectory-fps">Playback rate (frames per second): <strong id="trajectory-fps-value">5</strong></label>
  <input id="trajectory-fps" type="range" min="1" max="10" step="1" value="5" />
</div>
""",
    css="""
.controls { position: sticky; top: 0; z-index: 100; display: flex; gap: .5rem; flex-wrap: nowrap; margin-bottom: .75rem; padding: .2rem 0; width: min(100%, 30rem); background: var(--st-background-color, #fff); }
.controls button { flex: 1 1 0; border: 1px solid var(--st-border-color); border-radius: .5rem; padding: .38rem .7rem; min-height: 2.25rem; background: var(--st-secondary-background-color); color: var(--st-text-color); cursor: pointer; font: inherit; font-size: .9rem; white-space: nowrap; transition: background-color .15s ease, border-color .15s ease, box-shadow .15s ease, color .15s ease; }
#trajectory-play.is-active { border-color: #15803d; background: #16a34a; color: white; box-shadow: 0 0 0 3px rgba(22, 163, 74, .24); }
#trajectory-pause.is-active { border-color: #b45309; background: #f59e0b; color: #111827; box-shadow: 0 0 0 3px rgba(245, 158, 11, .28); }
#trajectory-reset.reset-feedback { border-color: #6b7280; background: #6b7280; color: white; box-shadow: 0 0 0 3px rgba(107, 114, 128, .22); }
.fps-label { display: block; color: var(--st-text-color); }
#trajectory-fps, #trajectory-progress { width: 100%; accent-color: var(--st-primary-color); }
.metrics { display: grid; grid-template-columns: repeat(5, minmax(0, 1fr)); gap: 1rem; margin: 1rem 0 0; color: var(--st-text-color); }
.metrics div { display: flex; flex-direction: column; gap: .25rem; min-width: 0; }
.metrics span { font-size: .78rem; }
.metrics strong { font-size: 1.12rem; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
#trajectory-progress-text { display: block; color: var(--st-text-color); }
#trajectory-plot { width: 100%; height: 650px; }
.slider-control { position: relative; z-index: 20; display: grid; gap: .35rem; margin-top: 1rem; padding: .2rem 0; background: var(--st-background-color, #fff); pointer-events: auto; }
.slider-control input[type="range"] { position: relative; z-index: 21; cursor: pointer; pointer-events: auto; touch-action: none; }
#trajectory-plot .modebar { position: absolute !important; display: flex !important; flex-flow: column nowrap !important; gap: .2rem; left: 4px !important; right: auto !important; top: auto !important; bottom: 8px !important; width: auto !important; transform: none !important; }
#trajectory-plot .modebar-group { display: flex !important; flex-flow: column nowrap !important; gap: .2rem; float: none !important; width: auto !important; padding: 0 !important; }
#trajectory-plot .modebar-btn { display: flex !important; align-items: center; justify-content: center; float: none !important; width: 2.4rem !important; height: 2.4rem !important; padding: .45rem !important; border: 1px solid var(--st-border-color) !important; border-radius: .45rem !important; background: var(--st-secondary-background-color) !important; opacity: .82 !important; box-sizing: border-box !important; }
#trajectory-plot .modebar-btn:hover { border-color: var(--st-primary-color) !important; opacity: 1 !important; }
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
    simulation = (
        component_state.get("simulation") if hasattr(component_state, "get") else None
    )
    if not simulation:
        simulation = {
            "index": 0,
            "status": "stopped",
            "fps": DEFAULT_FPS,
            "camera": DEFAULT_CAMERA,
        }
    # JSON normalization converts pandas and NumPy scalar values for the frontend.
    rows = json.loads(
        route[["Seconds", "longitude", "latitude", "Altitude"]].to_json(
            orient="records"
        )
    )
    _TRAJECTORY_COMPONENT(
        key=key,
        data={
            "rows": rows,
            "initialState": simulation,
            "defaultCamera": DEFAULT_CAMERA,
        },
        width="stretch",
        # Responsive metrics use three rows on narrow screens, so reserve enough
        # component height to keep both sliders inside the interactive host boundary.
        height=1120,
        on_simulation_change=lambda: None,
    )
