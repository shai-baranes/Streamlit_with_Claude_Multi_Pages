let connected = false;
let confirmation = null;
let terminating = false;
let sessions = [];
let connectionVersion = 0;
let refreshing = false;
let idlePolicy = null;
let savingPolicy = false;
let policyVersion = 0;
const el = id => document.getElementById(id);
const mib = n => ((n || 0) / 1048576).toFixed(1);
async function request(path, body) {
  const response = await fetch(path, {method: body ? 'POST' : 'GET',
    headers: {'Content-Type':'application/json'},
    body: body ? JSON.stringify(body) : undefined});
  const data = await response.json();
  if (!response.ok) throw Error(data.error);
  return data;
}
async function refresh() {
  if (!connected || refreshing) return;
  refreshing = true;
  const version = connectionVersion;
  const policyAtRequest = policyVersion;
  try {
    const data = await request('/sessions');
    if (version !== connectionVersion) return;
    sessions = data.sessions;
    // A poll started before a settings change may return the previous policy.
    if (!savingPolicy && policyAtRequest === policyVersion) idlePolicy = data.idle_policy;
    const automatic = data.last_automatic_termination;
    const result = el('idle-auto-result');
    result.hidden = !automatic;
    if (automatic) {
      const at = new Date(automatic.at * 1000).toLocaleString();
      const threshold = automatic.minutes === 60 ? '1hr' : `${automatic.minutes}min`;
      result.textContent = `Last automatic run (${threshold}, ${at}): ${idleResult(automatic)}`;
    }
    setConnection(true);
    el('server').textContent = `Server RAM: ${mib(data.process_rss_bytes)} MiB | Process CPU: ${data.process_cpu_percent}% | Available RAM: ${mib(data.available_ram_bytes)} MiB`;
    el('sessions').replaceChildren();
    for (const s of sessions) {
      const row = document.createElement('tr');
      row.classList.add(`session-${s.state}`);
      const date = value => value ? new Date(value*1000).toLocaleString() : 'Unknown';
      for (const value of [s.id, `${s.address || 'Unknown'} (${s.location || 'unknown'})`, s.state,
        `${date(s.created_at)} / ${date(s.last_activity)}`, idleLabel(s), `${s.page || '—'} / ${s.dataset || '—'}`,
        `${s.rows} / ${s.columns}`, mib(s.frame_bytes), mib(s.upload_bytes), mib(s.export_bytes), mib(s.disk_bytes)]) {
        const cell = document.createElement('td'); cell.textContent = value; row.append(cell);
      }
      const cell = document.createElement('td'), button = document.createElement('button');
      button.textContent = 'Terminate'; button.disabled = s.state === 'terminating';
      button.onclick = () => showConfirmation({path: '/terminate', body: {id: s.id}},
        `Terminate session ${s.id} (${s.dataset || 'empty'})? Its dataset and settings will be lost.`);
      cell.append(button); row.append(cell); el('sessions').append(row);
    }
  } catch (error) {
    if (version === connectionVersion) {
      setConnection(false);
      el('message').textContent = error.message;
    }
  } finally {
    refreshing = false;
    if (version !== connectionVersion && connected) refresh();
  }
}
function setConnection(isConnected) {
  connected = isConnected;
  const panel = el('connection-panel');
  panel.className = `connection ${isConnected ? 'connected' : 'disconnected'}`;
  el('connection-state').textContent = isConnected ? 'Connected' : 'Disconnected';
  el('connection-detail').textContent = isConnected
    ? `Administration session active at ${window.location.origin}`
    : 'Select Connect to open the administration session through this server-local or SSH-tunneled address.';
  el('connect').disabled = isConnected;
  el('logout').disabled = !isConnected || savingPolicy;
  if (!isConnected) {
    sessions = [];
    el('sessions').replaceChildren();
    el('server').textContent = '';
    closeConfirmation();
  }
  updateIdleControls();
}
function idleLabel(session) {
  if (session.busy) return 'Busy';
  if (session.idle_seconds == null) return 'Unknown';
  const seconds = Math.floor(session.idle_seconds);
  return `${Math.floor(seconds / 60)}m ${seconds % 60}s`;
}
function idleMatches() {
  const cutoff = Number(el('idle-threshold').value) * 60;
  return sessions.filter(s => s.state !== 'terminating' && !s.busy && s.idle_seconds > cutoff).length;
}
function updateIdleControls() {
  const locked = !connected || !idlePolicy || terminating || savingPolicy || !!confirmation;
  if (idlePolicy && !confirmation && !savingPolicy) {
    el('auto-idle').checked = idlePolicy.enabled;
    el('idle-threshold').value = idlePolicy.minutes;
  }
  const count = idleMatches();
  el('idle-count').textContent = connected ? `${count} eligible` : '';
  el('terminate-idle').disabled = locked || count === 0;
  el('idle-threshold').disabled = locked;
  el('auto-idle').disabled = locked;
  el('logout').disabled = !connected || savingPolicy;
  const status = el('idle-policy-status');
  status.hidden = !savingPolicy && !idlePolicy?.enabled;
  status.textContent = savingPolicy ? 'Saving idle settings…'
    : 'Automatic termination stays active on the server after you disconnect or close this tab.';
}
function showConfirmation(action, message) {
  if (!connected || terminating || savingPolicy || confirmation) return;
  confirmation = action;
  el('confirmation-text').textContent = message;
  el('confirmation').hidden = false;
  el('confirm').focus();
  updateIdleControls();
}
function closeConfirmation() {
  confirmation = null;
  el('confirmation').hidden = true;
  updateIdleControls();
}
el('connect').onclick = () => {
  connectionVersion++;
  connected = true;
  el('message').textContent = 'Connecting…';
  refresh().then(() => {
    if (el('message').textContent === 'Connecting…') el('message').textContent = '';
  });
};
async function saveIdlePolicy() {
  const body = {enabled: el('auto-idle').checked, minutes: Number(el('idle-threshold').value)};
  savingPolicy = true;
  policyVersion++;
  updateIdleControls();
  el('message').textContent = '';
  try {
    idlePolicy = await request('/idle-policy', body);
  } catch (error) {
    el('message').textContent = `Could not save idle settings. ${error.message}`;
  } finally {
    savingPolicy = false;
    updateIdleControls();
  }
}
el('idle-threshold').onchange = saveIdlePolicy;
el('auto-idle').onchange = saveIdlePolicy;
function idleResult(result) {
  return `Terminated: ${result.terminated} | Still terminating: ${result.terminating} | Skipped: ${result.skipped} | Failed: ${result.failed}`;
}
el('terminate-idle').onclick = () => {
  const count = idleMatches();
  const threshold = el('idle-threshold');
  showConfirmation({path: '/terminate-idle', body: {minutes: Number(threshold.value)}},
    `Terminate sessions idle longer than ${threshold.selectedOptions[0].text}? ${count} currently eligible. The server will check again when you confirm. Their datasets and settings will be lost.`);
};
el('cancel').onclick = closeConfirmation;
el('confirm').onclick = async () => {
  if (!confirmation || terminating) return;
  const {path, body} = confirmation;
  const version = connectionVersion;
  terminating = true;
  closeConfirmation();
  try {
    const result = await request(path, body);
    if (version !== connectionVersion) return;
    el('message').textContent = path === '/terminate-idle'
      ? idleResult(result)
      : `${body.id}: ${result.state}`;
    await refresh();
  } catch (error) {
    if (version === connectionVersion) el('message').textContent = error.message;
  } finally {
    terminating = false;
    updateIdleControls();
  }
};
el('logout').onclick = () => {
  connectionVersion++;
  el('message').textContent = '';
  setConnection(false);
};
setInterval(refresh, 5000);
