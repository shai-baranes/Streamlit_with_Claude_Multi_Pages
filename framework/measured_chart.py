"""Render a 2D Plotly figure with a browser-side two-point readout."""

from typing import Literal

import plotly.graph_objects as go
import streamlit as st

from framework.plotly_assets import PLOTLY_SOURCE
from framework.state import current_html_export


_HTML = """
<div class="measured-chart-inline">
  <section class="measured-chart-panel">
    <div class="measured-chart-tools">
      <button type="button">Full screen</button>
    </div>
    <div class="measured-chart-plot"></div>
    <div class="measured-chart-readout" role="status" aria-live="polite">
      <div>Click two points to measure.</div>
      <div></div>
      <div></div>
    </div>
  </section>
</div>
<dialog class="measured-chart-dialog" aria-label="Full screen chart"></dialog>
"""

_CSS = """
.measured-chart-panel {
  display: flex;
  flex-direction: column;
  gap: 0.35rem;
  min-width: 0;
}
.measured-chart-tools { display: flex; justify-content: flex-end; }
.measured-chart-tools button {
  background: var(--st-background-color, white);
  color: var(--st-text-color, #1e293b);
  border: 1px solid var(--st-border-color, #cbd5e1);
  border-radius: 0.4rem;
  padding: 0.25rem 0.65rem;
  font: inherit;
  font-size: 0.875rem;
  cursor: pointer;
}
.measured-chart-plot { height: var(--measured-chart-height, 450px); min-width: 0; }
.measured-chart-readout {
  background: #eff6ff;
  color: #1e293b;
  border: 1px solid #bfdbfe;
  border-left: 4px solid #3b82f6;
  border-radius: 0.4rem;
  padding: 0.4rem 0.65rem;
  font: 0.8125rem/1.4 monospace;
  overflow-wrap: anywhere;
}
.measured-chart-readout > div { min-height: 1.4em; }
.measured-chart-dialog {
  box-sizing: border-box;
  width: 100%;
  height: 100%;
  max-width: none;
  max-height: none;
  margin: 0;
  border: 0;
  padding: 0.5rem;
  background: var(--st-background-color, white);
}
.measured-chart-dialog .measured-chart-panel { height: 100%; }
.measured-chart-dialog .measured-chart-plot { height: auto; flex: 1; min-height: 0; }
"""

_JS = r"""
const charts = new WeakMap()
const coordinates = new Intl.NumberFormat("en-US", {
  minimumFractionDigits: 4,
  maximumFractionDigits: 4,
})
const elapsed = new Intl.NumberFormat("en-US", {maximumFractionDigits: 6})

function periodStart(value) {
  const match = /^(\d{4})(?:-(0[1-9]|1[0-2])| Q([1-4]))?$/.exec(String(value))
  if (!match) return NaN

  const [, year, month, quarter] = match
  const monthIndex = quarter ? (Number(quarter) - 1) * 3 : Number(month || 1) - 1
  const date = new Date(0)
  date.setUTCFullYear(Number(year), monthIndex, 1)
  return date.getTime()
}

function measurement(first, second, xKind, unit) {
  let dx = second.x - first.x
  if (xKind === "period") {
    dx = (periodStart(second.x) - periodStart(first.x)) / (unit === "s" ? 1000 : 1)
  } else if (xKind === "seconds" && unit === "ms") {
    dx *= 1000
  }
  const x = !Number.isFinite(dx) ? "—" : xKind === "numeric"
    ? coordinates.format(dx) : `${elapsed.format(dx)} ${unit}`
  const dy = second.y - first.y
  return `Delta  Δx = ${x} | Δy = ${Number.isFinite(dy) ? coordinates.format(dy) : "—"}`
}

function describe(point, number) {
  const show = value => typeof value === "number" ? coordinates.format(value) : String(value)
  return `Point ${number}  x = ${show(point.x)} | y = ${show(point.y)} · ${point.label}`
}

function closestPoint(plot, {points, event}) {
  const candidates = (points || []).filter(point => point.x != null && point.y != null)
  if (candidates.length < 2 || !event) return candidates[0]

  // Unified hover returns several traces. Compare rendered positions so that a
  // click on a stacked segment resolves to that segment, even far from its tip.
  const bounds = plot.getBoundingClientRect()
  const mouseX = event.clientX - bounds.left
  const mouseY = event.clientY - bounds.top
  let best
  let bestDistance = Infinity
  for (const point of candidates) {
    const {curveNumber, pointNumber, xaxis, yaxis, fullData} = point
    if (!xaxis || !yaxis) continue
    const bar = fullData.type === "bar" && plot.calcdata?.[curveNumber]?.[pointNumber]
    let distance
    if (bar) {
      // Plotly's computed bar geometry contains the stack base and end.
      const horizontal = fullData.orientation === "h"
      const positionAxis = horizontal ? yaxis : xaxis
      const valueAxis = horizontal ? xaxis : yaxis
      const position = horizontal ? bar.y : bar.x
      const end = horizontal ? bar.x : bar.y
      const positionPixel = positionAxis._offset + positionAxis.c2p(position)
      const halfWidth = Math.abs(positionAxis.c2p(position + bar.w / 2)
        - positionAxis.c2p(position))
      const startPixel = valueAxis._offset + valueAxis.c2p(bar.b)
      const endPixel = valueAxis._offset + valueAxis.c2p(end)
      const cursorPosition = horizontal ? mouseY : mouseX
      const cursorValue = horizontal ? mouseX : mouseY
      distance = Math.hypot(
        Math.max(0, Math.abs(cursorPosition - positionPixel) - halfWidth),
        Math.max(0, Math.min(startPixel, endPixel) - cursorValue,
          cursorValue - Math.max(startPixel, endPixel)),
      )
    } else {
      const x = xaxis._offset + xaxis.d2p(point.x)
      const y = yaxis._offset + yaxis.d2p(point.y)
      distance = Math.hypot(mouseX - x, mouseY - y)
    }
    // At the same position pick the trace drawn on top.
    if (distance < bestDistance || (distance === bestDistance && curveNumber > best?.curveNumber)) {
      best = point
      bestDistance = distance
    }
  }
  return best || candidates[0]
}

function renderMeasuredChart({data, parentElement}) {
  const plotly = window.Plotly
  const inline = parentElement.querySelector(".measured-chart-inline")
  const dialog = parentElement.querySelector(".measured-chart-dialog")
  const panel = parentElement.querySelector(".measured-chart-panel")
  const plot = panel.querySelector(".measured-chart-plot")
  const button = panel.querySelector("button")
  const [firstLine, secondLine, deltaLine] = panel.querySelector(".measured-chart-readout").children

  let chart = charts.get(plot)
  if (!chart) {
    chart = {points: [], revision: null, pending: Promise.resolve()}
    charts.set(plot, chart)
  }
  // Streamlit can call the renderer again before running unmount cleanup.
  chart.dispose?.()
  const {data: traces, layout = {}} = JSON.parse(data.figure)
  const revision = JSON.stringify([traces, data.xKind])
  if (chart.revision !== revision) {
    chart.points = []
    chart.revision = revision
  }
  const hasSubplots = Boolean(layout.yaxis2 || layout.xaxis2)
  const height = layout.height || 450
  panel.style.setProperty("--measured-chart-height", `${height}px`)
  // Use the chart container's dimensions in both inline and expanded views.
  delete layout.height
  delete layout.width
  layout.autosize = true

  function renderReadout() {
    const [first, second] = chart.points
    firstLine.textContent = first ? describe(first, 1) : "Click two points to measure."
    secondLine.textContent = second ? describe(second, 2) : ""
    deltaLine.textContent = second ? measurement(first, second, data.xKind, data.unit) : ""
  }

  let clearing = false
  function click(event) {
    if (clearing) return
    const point = closestPoint(plot, event)
    if (!point) return
    const series = point.fullData.name || `Trace ${point.curveNumber + 1}`
    const axis = point.fullData.yaxis || "y"
    const label = hasSubplots ? `${series} (subplot ${axis})` : series
    if (chart.points.length === 2) chart.points = []
    chart.points.push({x: point.x, y: point.y, label})
    renderReadout()
  }

  function clear() {
    // Plotly also emits a point click for the second half of a double-click.
    clearing = true
    queueMicrotask(() => { clearing = false })
    chart.points = []
    renderReadout()
  }

  function resize() {
    if (plot._fullLayout && plot.clientWidth && plot.clientHeight) {
      plotly.Plots.resize(plot).catch(() => {}) // The plot can be hidden before resizing.
    }
  }

  function toggleFullscreen() {
    if (dialog.open) {
      restoreInline()
      return
    }
    dialog.showModal()
    dialog.append(panel)
    button.textContent = "Exit full screen"
    button.focus({preventScroll: true})
    resize()
  }

  function restoreInline(event) {
    event?.preventDefault()
    dialog.close()
    inline.append(panel)
    button.textContent = "Full screen"
    button.focus({preventScroll: true})
    resize()
  }

  renderReadout()
  button.addEventListener("click", toggleFullscreen)
  dialog.addEventListener("cancel", restoreInline)
  const observer = new ResizeObserver(resize)
  let active = true
  chart.pending = chart.pending.then(async () => {
    if (!active) return
    const render = plot._fullLayout ? plotly.react : plotly.newPlot
    await render(plot, traces, layout, {displaylogo: false})
    if (!active) return
    plot.on("plotly_click", click)
    plot.on("plotly_doubleclick", clear)
    observer.observe(plot)
    resize()
  }).catch(error => {
    if (active) firstLine.textContent = "Could not render the chart."
    console.error(error)
  })

  chart.dispose = () => {
    if (!active) return
    active = false
    observer.disconnect()
    button.removeEventListener("click", toggleFullscreen)
    dialog.removeEventListener("cancel", restoreInline)
    plot.removeListener?.("plotly_click", click)
    plot.removeListener?.("plotly_doubleclick", clear)
    // Updates may reuse the same plot. Purge only after Streamlit detaches it.
    chart.pending = chart.pending.then(() => {
      if (!plot.isConnected) plotly.purge(plot)
    })
  }
  return chart.dispose
}
"""

_COMPONENT = st.components.v2.component(
    "measured_plotly_chart",
    # Plotly inserts its toolbar styles into the document, outside Shadow DOM.
    isolate_styles=False,
    html=_HTML,
    css=_CSS,
    js=PLOTLY_SOURCE + "\n" + _JS + "\nexport default renderMeasuredChart",
)


def measured_plotly_chart(
    figure: go.Figure,
    *,
    key: str,
    x_kind: Literal["numeric", "period", "seconds"] = "numeric",
    delta_time_unit: Literal["ms", "s"] = "ms",
) -> None:
    """Display signed click deltas with the figure, including in full screen."""
    data = {"figure": figure.to_json(), "xKind": x_kind, "unit": delta_time_unit}
    report = current_html_export()
    if report is not None:
        # The downloaded file mounts the same browser renderer with the same data.
        report.component("renderMeasuredChart", data, html=_HTML, css=_CSS, js=_JS, dependencies=("plotly",))
    _COMPONENT(
        key=key,
        data=data,
        width="stretch",
    )
