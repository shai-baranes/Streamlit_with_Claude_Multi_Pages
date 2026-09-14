let token = '';
let selectedSession = null;
const el = id => document.getElementById(id);
const mib = n => ((n || 0) / 1048576).toFixed(1);
async function request(path, body) {
  const response = await fetch(path, {method: body ? 'POST' : 'GET',
    headers: {Authorization: `Bearer ${token}`, 'Content-Type':'application/json'},
    body: body ? JSON.stringify(body) : undefined});
  const data = await response.json();
  if (!response.ok) throw Error(data.error);
  return data;
}
async function refresh() {
  if (!token) return;
  try {
    const data = await request('/sessions');
    el('server').textContent = `Server RAM: ${mib(data.process_rss_bytes)} MiB | Process CPU: ${data.process_cpu_percent}% | Available RAM: ${mib(data.available_ram_bytes)} MiB`;
    el('sessions').replaceChildren();
    for (const s of data.sessions) {
      const row = document.createElement('tr');
      const date = value => value ? new Date(value*1000).toLocaleString() : 'Unknown';
      for (const value of [s.id, `${s.address || 'Unknown'} (${s.location || 'unknown'})`, s.state,
        `${date(s.created_at)} / ${date(s.last_activity)}`, `${s.page || '—'} / ${s.dataset || '—'}`,
        `${s.rows} / ${s.columns}`, mib(s.frame_bytes), mib(s.upload_bytes), mib(s.export_bytes), mib(s.disk_bytes)]) {
        const cell = document.createElement('td'); cell.textContent = value; row.append(cell);
      }
      const cell = document.createElement('td'), button = document.createElement('button');
      button.textContent = 'Terminate'; button.disabled = s.state === 'terminating';
      button.onclick = () => {
        selectedSession = s.id;
        el('confirmation-text').textContent = `Terminate session ${s.id} (${s.dataset || 'empty'})? Its dataset and settings will be lost.`;
        el('confirmation').hidden = false;
        el('confirm').focus();
      };
      cell.append(button); row.append(cell); el('sessions').append(row);
    }
  } catch(error) {el('message').textContent = error.message;}
}
el('connect').onclick = () => {token = el('token').value; el('token').value = ''; el('message').textContent = ''; refresh();};
el('cancel').onclick = () => {selectedSession = null; el('confirmation').hidden = true;};
el('confirm').onclick = async () => {
  const id = selectedSession;
  if (!id) return;
  selectedSession = null; el('confirmation').hidden = true;
  try {const result = await request('/terminate', {id}); el('message').textContent = `${id}: ${result.state}`; await refresh();}
  catch(error) {el('message').textContent = error.message;}
};
el('logout').onclick = () => {token = ''; selectedSession = null; el('confirmation').hidden = true; el('sessions').replaceChildren(); el('server').textContent = '';};
setInterval(refresh, 5000);
