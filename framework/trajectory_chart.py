"""A browser-side Plotly flight player with session-persisted controls and camera."""

import json

import pandas as pd
import streamlit as st

from framework.trajectory import trajectory_separation_meters


DEFAULT_CAMERA = {"eye": {"x": 1.55, "y": -1.65, "z": 1.1}}
DEFAULT_FPS = 5
DEFAULT_MAX_DISTANCE_METERS = 2000
TRAJECTORY_COMPONENT_KEY = "trajectory_3d_component"

# Share the installed bundle with the other app-owned v2 chart.
from framework.plotly_assets import PLOTLY_SOURCE as _PLOTLY_SOURCE

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
  const hasSecondary = data.hasSecondary
  const lastIndex = Math.max(0, rows.length - 1)
  player.state.index = Math.min(Math.max(Number(player.state.index) || 0, 0), lastIndex)
  player.state.fps = Math.min(Math.max(Number(player.state.fps) || 5, 1), 10)
  player.state.maxDistance = Math.max(Number(player.state.maxDistance) || 2000, 100)
  player.state.showRoute1 = player.state.showRoute1 !== false
  player.state.showRoute2 = player.state.showRoute2 !== false
  player.state.camera = player.state.camera || data.defaultCamera

  const status = parentElement.querySelector("#trajectory-status")
  const elapsed = parentElement.querySelector("#trajectory-elapsed")
  const altitude = parentElement.querySelector("#trajectory-altitude")
  const position = parentElement.querySelector("#trajectory-position")
  const frame = parentElement.querySelector("#trajectory-frame")
  const progress = parentElement.querySelector("#trajectory-progress")
  const progressText = parentElement.querySelector("#trajectory-progress-text")
  const fps = parentElement.querySelector("#trajectory-fps")
  const distanceControl = parentElement.querySelector("#trajectory-distance-control")
  const maxDistance = parentElement.querySelector("#trajectory-max-distance")
  const maxDistanceValue = parentElement.querySelector("#trajectory-max-distance-value")
  const distanceWarning = parentElement.querySelector("#trajectory-distance-warning")
  const route1Toggle = parentElement.querySelector("#trajectory-route-1")
  const route2Toggle = parentElement.querySelector("#trajectory-route-2")
  const route2Label = parentElement.querySelector("#trajectory-route-2-label")
  const playButton = parentElement.querySelector("#trajectory-play")
  const pauseButton = parentElement.querySelector("#trajectory-pause")
  const resetButton = parentElement.querySelector("#trajectory-reset")

  function saveState() {
    // Clone the object so Streamlit receives a new serializable state value.
    player.setStateValue("simulation", JSON.parse(JSON.stringify(player.state)))
  }

  function scheduleStateSave(delay = 100) {
    // Let local controls paint first; immediate component synchronization can race fast clicks.
    clearTimeout(player.stateTimer)
    player.stateTimer = setTimeout(saveState, delay)
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
    progressText.textContent = `Trajectory progress: ${(ratio * 100).toFixed(1)}% (${current.Seconds.toFixed(1)} Seconds)`
    fps.value = String(player.state.fps)
    distanceControl.hidden = !hasSecondary
    if (hasSecondary) {
      const observedMaximum = Math.max(...rows.map(row => row.distance_m || 0))
      const sliderMaximum = Math.max(5000, Math.ceil(observedMaximum / 500) * 500)
      player.state.maxDistance = Math.min(player.state.maxDistance, sliderMaximum)
      maxDistance.max = String(sliderMaximum)
      maxDistance.value = String(player.state.maxDistance)
      maxDistanceValue.textContent = `${Math.round(player.state.maxDistance).toLocaleString()} m`
      const exceeded = player.state.showRoute1 && player.state.showRoute2 && current.distance_m > player.state.maxDistance
      distanceWarning.hidden = !exceeded
      distanceWarning.textContent = exceeded
        ? `Distance warning active: ${Math.round(current.distance_m).toLocaleString()} m`
        : ""
    }
    const playing = player.state.status === "playing"
    const paused = player.state.status === "paused"
    route1Toggle.checked = player.state.showRoute1
    route2Toggle.checked = player.state.showRoute2
    route2Label.hidden = !hasSecondary
    // Separate controls keep both actions immediately available during Plotly updates.
    playButton.classList.toggle("is-active", playing)
    pauseButton.classList.toggle("is-active", paused)
    playButton.setAttribute("aria-pressed", String(playing))
    pauseButton.setAttribute("aria-pressed", String(paused))
  }

  async function renderPlot() {
    const achieved = rows.slice(0, player.state.index + 1)
    const current = rows[player.state.index]
    const traces = []
    if (player.state.showRoute1) {
      traces.push({
        type: "scatter3d", mode: "lines", name: "Complete route 1",
        x: rows.map(row => row.longitude), y: rows.map(row => row.latitude),
        z: rows.map(row => row.Altitude / 1000),
        line: {color: "rgba(120, 130, 145, 0.55)", width: 4}, hoverinfo: "skip",
      }, {
        type: "scatter3d", mode: "lines", name: "Traveled route 1",
        x: achieved.map(row => row.longitude), y: achieved.map(row => row.latitude),
        z: achieved.map(row => row.Altitude / 1000),
        customdata: achieved.map(row => [row.Altitude]),
        line: {color: "#2563eb", width: 7},
        hovertemplate: "Longitude=%{x:.5f}<br>Latitude=%{y:.5f}<br>Altitude=%{customdata[0]:,.0f} m<extra></extra>",
      }, {
        type: "scatter3d", mode: "markers", showlegend: false, hoverinfo: "skip",
        x: [current.longitude], y: [current.latitude], z: [current.Altitude / 1000],
        marker: {color: "rgba(220, 38, 38, 0.20)", size: 14},
      }, {
        type: "scatter3d", mode: "markers+text", name: "Flight object 1",
        x: [current.longitude], y: [current.latitude], z: [current.Altitude / 1000],
        marker: {color: "#dc2626", size: 8, symbol: "diamond", line: {color: "#ffffff", width: 2}},
        text: ["✈"], textfont: {color: "#991b1b", size: 16}, textposition: "top center",
        customdata: [[current.Seconds, current.Altitude]],
        hovertemplate: "Seconds=%{customdata[0]:.1f}<br>Longitude=%{x:.5f}<br>Latitude=%{y:.5f}<br>Altitude=%{customdata[1]:,.0f} m<extra></extra>",
      })
    }
    if (hasSecondary && player.state.showRoute2) {
      // The second aircraft uses the same frame index and Seconds value as route 1.
      traces.push(
        {
          type: "scatter3d", mode: "lines", name: "Complete route 2",
          x: rows.map(row => row.longitude_2), y: rows.map(row => row.latitude_2),
          z: rows.map(row => row.altitude_2 / 1000),
          line: {color: "rgba(168, 85, 247, 0.38)", width: 4}, hoverinfo: "skip",
        },
        {
          type: "scatter3d", mode: "lines", name: "Traveled route 2",
          x: achieved.map(row => row.longitude_2), y: achieved.map(row => row.latitude_2),
          z: achieved.map(row => row.altitude_2 / 1000),
          customdata: achieved.map(row => [row.altitude_2]),
          line: {color: "#7c3aed", width: 7},
          hovertemplate: "Longitude=%{x:.5f}<br>Latitude=%{y:.5f}<br>Altitude=%{customdata[0]:,.0f} m<extra></extra>",
        },
        {
          type: "scatter3d", mode: "markers", showlegend: false, hoverinfo: "skip",
          x: [current.longitude_2], y: [current.latitude_2], z: [current.altitude_2 / 1000],
          marker: {color: "rgba(245, 158, 11, 0.20)", size: 14},
        },
        {
          type: "scatter3d", mode: "markers+text", name: "Flight object 2",
          x: [current.longitude_2], y: [current.latitude_2], z: [current.altitude_2 / 1000],
          marker: {color: "#f59e0b", size: 8, symbol: "diamond", line: {color: "#ffffff", width: 2}},
          text: ["✈"], textfont: {color: "#b45309", size: 16}, textposition: "top center",
          customdata: [[current.Seconds, current.altitude_2]],
          hovertemplate: "Seconds=%{customdata[0]:.1f}<br>Longitude=%{x:.5f}<br>Latitude=%{y:.5f}<br>Altitude=%{customdata[1]:,.0f} m<extra></extra>",
        },
      )
      if (player.state.showRoute1 && current.distance_m > player.state.maxDistance) {
        // A local metre projection keeps the warning sleeve cylindrical despite degree axes.
        const latitudeRadians = current.latitude * Math.PI / 180
        const p1 = [0, 0, current.Altitude]
        const p2 = [
          (current.longitude_2 - current.longitude) * 111320 * Math.cos(latitudeRadians),
          (current.latitude_2 - current.latitude) * 111320,
          current.altitude_2,
        ]
        const axis = p2.map((value, index) => value - p1[index])
        const axisLength = Math.hypot(...axis) || 1
        const unit = axis.map(value => value / axisLength)
        const reference = Math.abs(unit[2]) < 0.9 ? [0, 0, 1] : [0, 1, 0]
        const cross = (a, b) => [
          a[1] * b[2] - a[2] * b[1],
          a[2] * b[0] - a[0] * b[2],
          a[0] * b[1] - a[1] * b[0],
        ]
        const rawU = cross(unit, reference)
        const rawULength = Math.hypot(...rawU) || 1
        const basisU = rawU.map(value => value / rawULength)
        const basisV = cross(unit, basisU)
        const radiusMeters = 120
        const segmentCount = 20
        const angles = Array.from({length: segmentCount}, (_, index) => index * 2 * Math.PI / segmentCount)
        const rings = [p1, p2].map(center => angles.map(angle => {
          const point = center.map((value, index) => value + radiusMeters * (
            Math.cos(angle) * basisU[index] + Math.sin(angle) * basisV[index]
          ))
          return {
            longitude: current.longitude + point[0] / (111320 * Math.cos(latitudeRadians)),
            latitude: current.latitude + point[1] / 111320,
            altitude: point[2] / 1000,
          }
        }))
        const vertices = rings.flat()
        const faceI = [], faceJ = [], faceK = []
        for (let index = 0; index < segmentCount; index += 1) {
          const next = (index + 1) % segmentCount
          // Two triangles per segment form a reliable open cylindrical sleeve.
          faceI.push(index, index)
          faceJ.push(next, segmentCount + next)
          faceK.push(segmentCount + next, segmentCount + index)
        }
        traces.push({
          type: "mesh3d", name: "Distance limit exceeded", showlegend: true,
          x: vertices.map(point => point.longitude),
          y: vertices.map(point => point.latitude),
          z: vertices.map(point => point.altitude),
          i: faceI, j: faceJ, k: faceK,
          color: "#f472b6", opacity: 0.42, flatshading: true, hoverinfo: "skip",
        })
      }
    }
    const layout = {
      height: 650, margin: {l: 96, r: 0, t: 20, b: 0},
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
        position: "absolute", display: "flex", flexFlow: "column nowrap",
        left: "calc(4px + 1.5rem)", right: "auto", top: "auto", bottom: "9.1rem",
        transform: "none", width: "auto",
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
    // The current frame is already drawn, so start immediately without waiting on Plotly.
    renderMetrics(); startTimer(); scheduleStateSave()
  }
  pauseButton.onclick = () => {
    player.state.status = "paused"
    stopTimer(); renderMetrics(); scheduleStateSave()
  }
  resetButton.onclick = async () => {
    resetButton.classList.remove("reset-feedback")
    void resetButton.offsetWidth
    resetButton.classList.add("reset-feedback")
    player.state = {index: 0, status: "stopped", fps: 5, maxDistance: 2000, showRoute1: true, showRoute2: true, camera: data.defaultCamera}
    stopTimer(); renderMetrics(); await renderPlot()
    clearTimeout(player.resetTimer)
    // Delay the rerun-producing state save until the temporary gray feedback is visible.
    player.resetTimer = setTimeout(() => {
      resetButton.classList.remove("reset-feedback")
      saveState()
    }, 200)
  }
  fps.onchange = () => {
    player.state.fps = Number(fps.value)
    // Restart locally so the selected rate takes effect without a Streamlit rerun.
    startTimer()
    saveState()
  }
  maxDistance.oninput = async () => {
    player.state.maxDistance = Number(maxDistance.value)
    renderMetrics()
    await renderPlot()
  }
  maxDistance.onchange = () => {
    // Persist once after dragging so the warning threshold survives page reruns.
    saveState()
  }
  route1Toggle.onchange = async () => {
    if (!route1Toggle.checked && !route2Toggle.checked) {
      route1Toggle.checked = true
      return
    }
    player.state.showRoute1 = route1Toggle.checked
    renderMetrics(); await renderPlot(); saveState()
  }
  route2Toggle.onchange = async () => {
    if (!route2Toggle.checked && !route1Toggle.checked) {
      route2Toggle.checked = true
      return
    }
    player.state.showRoute2 = route2Toggle.checked
    renderMetrics(); await renderPlot(); saveState()
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
    # Plotly's document stylesheet and pointer handling require light DOM.
    # Prefix local classes so player styling cannot affect surrounding pages.
    isolate_styles=False,
    html="""
<div class="trajectory-metrics">
  <div><span>Status</span><strong id="trajectory-status"></strong></div>
  <div><span>Elapsed</span><strong id="trajectory-elapsed"></strong></div>
  <div><span>Altitude</span><strong id="trajectory-altitude"></strong></div>
  <div><span>Position</span><strong id="trajectory-position"></strong></div>
  <div><span>Frame</span><strong id="trajectory-frame"></strong></div>
</div>
<div class="trajectory-graph-stage">
  <div id="trajectory-plot"></div>
  <div class="trajectory-route-toggles" aria-label="Displayed flight curves">
    <label><input id="trajectory-route-1" type="checkbox" checked /><span class="route-color route-one"></span>Flight object 1 curve</label>
    <label id="trajectory-route-2-label"><input id="trajectory-route-2" type="checkbox" checked /><span class="route-color route-two"></span>Flight object 2 curve</label>
  </div>
  <div class="trajectory-fps-control">
    <label for="trajectory-fps">Playback rate (frames per second)</label>
    <select id="trajectory-fps">
      <option value="1">1 fps</option><option value="2">2 fps</option><option value="3">3 fps</option>
      <option value="4">4 fps</option><option value="5" selected>5 fps</option><option value="6">6 fps</option>
      <option value="7">7 fps</option><option value="8">8 fps</option><option value="9">9 fps</option>
      <option value="10">10 fps</option>
    </select>
  </div>
  <div class="trajectory-controls">
    <button id="trajectory-play" type="button">▶ Play</button>
    <button id="trajectory-pause" type="button">⏸ Pause</button>
    <button id="trajectory-reset" type="button">↻ Reset</button>
  </div>
</div>
<div class="trajectory-slider-control">
  <label id="trajectory-progress-text" for="trajectory-progress"></label>
  <input id="trajectory-progress" type="range" min="0" max="0" step="1" value="0" />
</div>
<div id="trajectory-distance-control" class="trajectory-slider-control" hidden>
  <label for="trajectory-max-distance">Maximum allowed distance: <strong id="trajectory-max-distance-value">2,000 m</strong></label>
  <input id="trajectory-max-distance" type="range" min="100" max="5000" step="100" value="2000" />
  <strong id="trajectory-distance-warning" class="trajectory-distance-warning" hidden></strong>
</div>
""",
    css="""
.trajectory-graph-stage { position: relative; min-width: 0; }
.trajectory-controls { position: absolute; left: 4px; bottom: 8px; z-index: 100; display: flex; flex-direction: column; gap: .45rem; margin: 0; width: 5.4rem; }
.trajectory-fps-control { position: absolute; left: calc(4px + 1.5rem); bottom: 27.4rem; z-index: 101; display: grid; gap: .3rem; width: 9.5rem; padding: .5rem; border: 1px solid var(--st-border-color); border-radius: .5rem; background: var(--st-background-color, #fff); color: var(--st-text-color); font-size: .72rem; }
.trajectory-route-toggles { position: absolute; top: 3.4rem; right: .5rem; z-index: 101; display: grid; gap: .35rem; padding: .5rem .65rem; border: 1px solid var(--st-border-color); border-radius: .5rem; background: var(--st-background-color, #fff); color: var(--st-text-color); font-size: .74rem; }
.trajectory-route-toggles label { display: flex; align-items: center; gap: .35rem; cursor: pointer; }
.trajectory-route-toggles input { margin: 0; accent-color: var(--st-primary-color); }
.route-color { width: .65rem; height: .65rem; border-radius: 50%; }.route-one { background: #2563eb; }.route-two { background: #7c3aed; }
.trajectory-fps-control select { width: 100%; padding: .3rem; border: 1px solid var(--st-border-color); border-radius: .35rem; background: var(--st-secondary-background-color); color: var(--st-text-color); cursor: pointer; }
.trajectory-controls button { width: 5.4rem; min-width: 5.4rem; max-width: 5.4rem; height: 2.4rem; min-height: 2.4rem; padding: .25rem .2rem; border: 1px solid var(--st-border-color); border-radius: .5rem; background: var(--st-secondary-background-color); color: var(--st-text-color); cursor: pointer; font: inherit; font-size: .78rem; line-height: 1.1; white-space: nowrap; transition: background-color .15s ease, border-color .15s ease, box-shadow .15s ease, color .15s ease; }
#trajectory-play.is-active { border-color: #15803d; background: #16a34a; color: white; box-shadow: 0 0 0 3px rgba(22, 163, 74, .24); }
#trajectory-pause.is-active { border-color: #b45309; background: #f59e0b; color: #111827; box-shadow: 0 0 0 3px rgba(245, 158, 11, .28); }
#trajectory-reset.reset-feedback { border-color: #6b7280; background: #6b7280; color: white; box-shadow: 0 0 0 3px rgba(107, 114, 128, .22); }
#trajectory-progress, #trajectory-max-distance { width: 100%; accent-color: var(--st-primary-color); }
.trajectory-metrics { display: grid; grid-template-columns: repeat(5, minmax(0, 1fr)); gap: 1rem; margin: 1rem 0 0; color: var(--st-text-color); }
.trajectory-metrics div { display: flex; flex-direction: column; gap: .25rem; min-width: 0; }
.trajectory-metrics span { font-size: .78rem; }
.trajectory-metrics strong { font-size: 1.12rem; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
#trajectory-progress-text { display: block; color: var(--st-text-color); }
#trajectory-plot { min-width: 0; width: 100%; height: 650px; }
.trajectory-slider-control { position: relative; z-index: 20; display: grid; gap: .35rem; margin-top: 1rem; padding: .2rem 0; background: var(--st-background-color, #fff); pointer-events: auto; }
.trajectory-slider-control input[type="range"] { position: relative; z-index: 21; cursor: pointer; pointer-events: auto; touch-action: none; }
.trajectory-distance-warning { width: fit-content; color: #9d174d; background: rgba(249, 168, 212, .35); border: 1px solid rgba(236, 72, 153, .55); border-radius: .4rem; padding: .3rem .55rem; }
/* Plotly anchors this container at the right edge unless both levels are moved. */
#trajectory-plot .modebar-container { left: 0 !important; right: auto !important; width: 100% !important; pointer-events: none; }
#trajectory-plot .modebar { position: absolute !important; display: flex !important; flex-flow: column nowrap !important; gap: .2rem; left: calc(4px + 1.5rem) !important; right: auto !important; top: auto !important; bottom: 9.1rem !important; width: auto !important; transform: none !important; pointer-events: auto; }
#trajectory-plot .modebar-group { display: flex !important; flex-flow: column nowrap !important; gap: .2rem; float: none !important; width: auto !important; padding: 0 !important; }
#trajectory-plot .modebar-btn { display: flex !important; align-items: center; justify-content: center; float: none !important; width: 2.4rem !important; height: 2.4rem !important; padding: .45rem !important; border: 1px solid var(--st-border-color) !important; border-radius: .45rem !important; background: var(--st-secondary-background-color) !important; opacity: .82 !important; box-sizing: border-box !important; }
#trajectory-plot .modebar-btn:hover { border-color: var(--st-primary-color) !important; opacity: 1 !important; }
@media (max-width: 800px) {
  .trajectory-metrics { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .trajectory-controls, .trajectory-controls button { width: 4.9rem; min-width: 4.9rem; max-width: 4.9rem; }
  .trajectory-controls button { font-size: .72rem; }
  .trajectory-fps-control { left: calc(4px + 1.25rem); width: 8.5rem; }
  #trajectory-plot .modebar { left: calc(4px + 1.25rem) !important; }
}
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
            "maxDistance": DEFAULT_MAX_DISTANCE_METERS,
            "showRoute1": True,
            "showRoute2": True,
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
            "maxDistance": DEFAULT_MAX_DISTANCE_METERS,
            "showRoute1": True,
            "showRoute2": True,
            "camera": DEFAULT_CAMERA,
        }
    # JSON normalization converts pandas and NumPy scalar values for the frontend.
    secondary_columns = ["longitude_2", "latitude_2", "altitude_2"]
    has_secondary = all(column in route.columns for column in secondary_columns)
    selected_columns = ["Seconds", "longitude", "latitude", "Altitude"]
    if has_secondary:
        route = route.copy()
        route["distance_m"] = trajectory_separation_meters(route)
        selected_columns.extend(secondary_columns)
        selected_columns.append("distance_m")
    rows = json.loads(route[selected_columns].to_json(orient="records"))
    _TRAJECTORY_COMPONENT(
        key=key,
        data={
            "rows": rows,
            "hasSecondary": has_secondary,
            "initialState": simulation,
            "defaultCamera": DEFAULT_CAMERA,
        },
        width="stretch",
        # Responsive metrics use three rows on narrow screens, so reserve enough
        # component height to keep both sliders inside the interactive host boundary.
        height=1200,
        on_simulation_change=lambda: None,
    )
