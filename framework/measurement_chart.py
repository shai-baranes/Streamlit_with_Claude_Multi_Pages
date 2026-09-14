"""A Plotly chart and its browser-local two-point measurement readout."""
import hashlib

import streamlit as st
from framework.plotly_assets import PLOTLY_SOURCE

# Each root owns its chart/listeners; dataset values travel only in the data payload.
_JS = PLOTLY_SOURCE + r'''
const measurements = new WeakMap()
export default async function({data, parentElement}) {
  const plot = parentElement.querySelector('.measurement-plot')
  const box = parentElement.querySelector('.measurement-readout')
  let state = measurements.get(parentElement)
  if (!state || state.identity !== data.identity) {
    state = {identity: data.identity, points: []}
    measurements.set(parentElement, state)
  }
  if (!data.enabled) state.points = []
  plot.style.height = `${data.height}px`
  box.hidden = !data.enabled
  const figure = JSON.parse(data.figure)
  await Plotly.react(plot, figure.data, {...figure.layout, autosize: true},
                     {responsive: true, displaylogo: false})

  function fmt(value) {
    return typeof value === 'number' ? value.toFixed(4) : String(value ?? '--')
  }
  function delta(a, b, axis) {
    if (!a || !b || a[axis + 'Id'] !== b[axis + 'Id']) return '--'
    const type = b[axis + 'Type']
    // Categorical labels can look like numbers or dates; never coerce those axes.
    if (type === 'category' || type === 'multicategory') return '-- (categorical)'
    if (type === 'date') {
      const milliseconds = Date.parse(b[axis]) - Date.parse(a[axis])
      return Number.isFinite(milliseconds) ? `${fmt(milliseconds / 1000)} s elapsed` : '--'
    }
    const difference = Number(b[axis]) - Number(a[axis])
    return Number.isFinite(difference) ? fmt(difference) : '--'
  }
  function show() {
    const [a, b] = state.points
    box.textContent = !a ? '🖊 Click points on the chart to see both points and deltas.' :
      `Point 1: x1 = ${fmt(a.x)} | y1 = ${fmt(a.y)}\n` +
      `Point 2: x2 = ${fmt(b?.x)} | y2 = ${fmt(b?.y)}\n` +
      `Delta: dx = ${delta(a, b, 'x')} | dy = ${delta(a, b, 'y')}`
  }
  let ignoreClicksUntil = 0
  const clicked = event => {
    if (!data.enabled || !event.points?.length || performance.now() < ignoreClicksUntil) return
    const point = event.points[0]
    state.points.push({x: point.x, y: point.y,
      xType: point.xaxis?.type, yType: point.yaxis?.type,
      xId: point.xaxis?._id, yId: point.yaxis?._id})
    state.points = state.points.slice(-2)
    show()
  }
  const reset = () => {
    // Plotly may emit a queued click after the native double-click has cleared us.
    ignoreClicksUntil = performance.now() + 400
    state.points = []
    show()
  }
  plot.on('plotly_click', clicked)
  plot.on('plotly_doubleclick', reset)
  // Plotly can suppress its double-click event over individual markers.
  plot.addEventListener('dblclick', reset)
  const observer = new ResizeObserver(() => Plotly.Plots.resize(plot))
  observer.observe(plot)
  show()
  return () => {
    observer.disconnect()
    plot.removeListener('plotly_click', clicked)
    plot.removeListener('plotly_doubleclick', reset)
    plot.removeEventListener('dblclick', reset)
    Plotly.purge(plot)
  }
}
'''

_MEASUREMENT_CHART = st.components.v2.component(
    'plotly_measurement_chart',
    # Plotly injects document-level CSS and uses document pointer hit-testing.
    # Keep its DOM outside a shadow root; our classes and listeners remain scoped.
    isolate_styles=False,
    html='<div class="measurement-plot"></div><div class="measurement-readout" role="status"></div>',
    css='''
.measurement-plot { width: 100%; }
.measurement-readout { font: 13px/1.45 monospace; white-space: pre-line;
  padding: 8px 14px; margin-top: .5rem; min-height: 76px;
  border: 1px solid var(--st-border-color, #bfdbfe);
  border-left: 4px solid var(--st-primary-color, #3b82f6); border-radius: 6px;
  background: var(--st-secondary-background-color, #eff6ff); color: var(--st-text-color); }
.measurement-readout[hidden] { display: none; }
''', js=_JS,
)


def render_measurement_chart(figure, *, key, dataset_identity, measurement_enabled=True):
    """Render with a stable page key; changed data resets previously clicked points."""
    payload = figure.to_json()
    identity = f'{dataset_identity}:{hashlib.sha256(payload.encode()).hexdigest()}'
    height = figure.layout.height or 450
    _MEASUREMENT_CHART(key=key, data={'figure': payload, 'identity': identity,
                                    'enabled': measurement_enabled, 'height': height},
                       height=height + (120 if measurement_enabled else 0), width='stretch')
