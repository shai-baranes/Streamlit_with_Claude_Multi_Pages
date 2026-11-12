// One reporter per dashboard document, with no Streamlit state updates.
const reporters = new WeakMap();
const schedules = new WeakMap();
export default function ({data, parentElement}) {
  reporters.get(parentElement)?.();
  const doc = parentElement.ownerDocument;
  const interval = 15000;
  const controller = new AbortController();
  const frames = new Map();
  const plots = new Set();
  let schedule = schedules.get(doc);
  if (schedule?.token !== data.token) {
    schedule = {token: data.token, sentAt: -Infinity, queued: false};
    schedules.set(doc, schedule);
  }
  let pending, scanTimer;

  function report() {
    clearTimeout(pending);
    pending = undefined;
    schedule.sentAt = performance.now();
    schedule.queued = false;
    fetch('/api/session-activity', {
      method: 'POST', headers: {'X-Dashboard-Activity': data.token}, keepalive: true,
    }).catch(() => {}); // Reporting must not interfere with dashboard use.
  }
  function activity() {
    schedule.queued = true;
    const delay = interval - (performance.now() - schedule.sentAt);
    if (delay <= 0) report();
    else if (pending === undefined) pending = setTimeout(report, delay);
  }
  function interaction(event) {
    if (event.isTrusted && (event.type !== 'pointermove' || event.buttons)) activity();
  }
  function listen(target, signal) {
    for (const type of ['pointerdown', 'click', 'keydown', 'wheel', 'scroll', 'pointermove']) {
      target.addEventListener(type, interaction, {signal, capture: true, passive: true});
    }
  }
  function bindFrame(frame) {
    frames.get(frame)?.abort();
    frames.delete(frame);
    if (!frame.contentDocument) return; // Cross-origin frames are inaccessible.
    const scope = new AbortController();
    frames.set(frame, scope);
    listen(frame.contentDocument, scope.signal);
  }
  function scan() {
    scanTimer = undefined;
    for (const [frame, scope] of frames) {
      if (!frame.isConnected) {scope.abort(); frames.delete(frame);}
    }
    for (const frame of doc.querySelectorAll('iframe')) {
      if (!frames.has(frame)) bindFrame(frame);
    }
    for (const plot of plots) {
      if (!plot.isConnected) {
        plot.removeListener?.('plotly_animatingframe', activity);
        plots.delete(plot);
      }
    }
    for (const plot of doc.querySelectorAll('.js-plotly-plot')) {
      if (plot.on && !plots.has(plot)) {
        plot.on('plotly_animatingframe', activity);
        plots.add(plot);
      }
    }
  }
  listen(doc, controller.signal);
  doc.addEventListener('dashboard-playback-frame', activity, {signal: controller.signal});
  doc.addEventListener('load', event => {
    if (event.target.tagName === 'IFRAME') bindFrame(event.target);
  }, {capture: true, signal: controller.signal});
  const observer = new MutationObserver(changes => {
    if (scanTimer === undefined && changes.some(change => {
      if (change.type === 'attributes') {
        return change.target.matches('.js-plotly-plot') && !plots.has(change.target);
      }
      return [...change.addedNodes, ...change.removedNodes].some(node =>
        node.nodeType === 1 && (node.matches('iframe, .js-plotly-plot') ||
          node.querySelector('iframe, .js-plotly-plot')));
    })) {
      scanTimer = setTimeout(scan, 100);
    }
  });
  observer.observe(doc.body, {childList: true, subtree: true, attributeFilter: ['class']});
  scan();
  if (schedule.queued) activity();

  function cleanup() {
    if (reporters.get(parentElement) !== cleanup) return;
    clearTimeout(pending);
    clearTimeout(scanTimer);
    controller.abort();
    observer.disconnect();
    for (const scope of frames.values()) scope.abort();
    for (const plot of plots) plot.removeListener?.('plotly_animatingframe', activity);
    reporters.delete(parentElement);
  }
  reporters.set(parentElement, cleanup);
  return cleanup;
}
