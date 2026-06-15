'use strict';

/* ── State ──────────────────────────────────────────────────────────────── */
let liveDevices    = [];
let historyDevices = [];
let historyLoaded  = false;
let graph3D        = null;

/* ── Bootstrap ──────────────────────────────────────────────────────────── */
document.addEventListener('DOMContentLoaded', () => {
  loadDevices();

  document.getElementById('history-tab-btn').addEventListener('shown.bs.tab', () => {
    if (!historyLoaded) loadHistory();
  });

  document.getElementById('tab-3d-btn').addEventListener('shown.bs.tab', () => {
    if (liveDevices.length) initGraph3D();
  });
});

/* ── API calls ──────────────────────────────────────────────────────────── */

async function loadDevices() {
  setLiveState('loading');
  try {
    const data = await apiFetch('/api/devices');
    liveDevices = data.devices ?? [];
    renderLiveTable();
    updateStats(data);
    updateRefreshTime();
    setBboxStatus(true);
    if (graph3D) initGraph3D();
  } catch (e) {
    console.error('[loadDevices]', e);
    setLiveState('error', e.message);
    setBboxStatus(false);
  }
}

async function loadHistory() {
  setHistoryState('loading');
  try {
    const data = await apiFetch('/api/history');
    historyDevices = data.devices ?? [];
    historyLoaded  = true;
    renderHistoryTable(historyDevices);
    document.getElementById('stat-total').textContent = historyDevices.length;
    document.getElementById('badge-history').textContent = historyDevices.length || '';
    setHistoryState('table');
  } catch (e) {
    setHistoryState('table');
    console.error('Historique :', e.message);
  }
}

async function disconnectDevice(mac, hostname) {
  if (!confirm(`Déconnecter "${hostname}" (${mac}) ?\n\nL'appareil sera expulsé temporairement — il pourra se reconnecter.`)) return;
  try {
    await apiFetch('/api/disconnect', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ mac, hostname }),
    });
    await reloadAll();
  } catch (e) {
    alert(`Impossible de déconnecter l'appareil :\n${e.message}`);
  }
}

async function blockDevice(mac, hostname) {
  if (!confirm(`Bloquer définitivement "${hostname}" (${mac}) ?\n\nL'appareil ne pourra plus accéder à Internet.`)) return;
  try {
    await apiFetch('/api/block', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ mac, hostname }),
    });
    await reloadAll();
  } catch (e) {
    alert(`Impossible de bloquer l'appareil :\n${e.message}`);
  }
}

async function unblockDevice(mac) {
  if (!confirm(`Débloquer ${mac} ?\n\nL'appareil pourra se reconnecter au réseau.`)) return;
  try {
    await apiFetch(`/api/block?mac=${encodeURIComponent(mac)}`, { method: 'DELETE' });
    await reloadAll();
  } catch (e) {
    alert(`Impossible de débloquer l'appareil :\n${e.message}`);
  }
}

async function kickAndBlock(mac, hostname) {
  if (!confirm(`Expulser ET bloquer "${hostname}" (${mac}) ?\n\nL'appareil sera immédiatement déconnecté et ne pourra plus accéder à Internet.`)) return;
  try {
    await apiFetch('/api/kick-and-block', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ mac, hostname }),
    });
    await reloadAll();
  } catch (e) {
    alert(`Impossible d'expulser/bloquer l'appareil :\n${e.message}`);
  }
}

async function reloadAll() {
  closePanel();
  await loadDevices();
  if (historyLoaded) {
    historyLoaded = false;
    await loadHistory();
  }
}

function refreshAll() {
  historyLoaded = false;
  loadDevices();
  const histActive = document.querySelector('#tab-history.active');
  if (histActive) loadHistory();
}

/* ── 3D Graph ───────────────────────────────────────────────────────────── */

function initGraph3D() {
  const container = document.getElementById('graph-3d');
  if (!container) return;

  const h = Math.max(520, window.innerHeight - 210);
  container.style.height = h + 'px';

  const nodes = [{ id: '__bbox__', label: 'Bbox', group: 'router' }];
  const links = [];

  for (const d of liveDevices) {
    nodes.push({
      id:         d.mac,
      label:      d.hostname,
      group:      d.is_blocked ? 'blocked' : d.active ? 'active' : 'inactive',
      ...d,
    });
    links.push({ source: '__bbox__', target: d.mac, alive: !!d.active });
  }

  const gData = { nodes, links };

  if (graph3D) {
    graph3D.graphData(gData);
    return;
  }

  graph3D = ForceGraph3D()(container)
    .width(container.offsetWidth)
    .height(h)
    .backgroundColor('#0f172a')
    .graphData(gData)
    .nodeLabel(n => `<span style="background:rgba(15,23,42,.9);color:#f1f5f9;padding:5px 10px;border-radius:8px;font-size:12px;font-family:system-ui">${escHtml(n.label || n.hostname || '')}</span>`)
    .nodeColor(n => {
      if (n.group === 'router')   return '#3b82f6';
      if (n.group === 'blocked')  return '#ef4444';
      if (n.group === 'active')   return '#22c55e';
      return '#475569';
    })
    .nodeVal(n => n.group === 'router' ? 24 : 6)
    .nodeOpacity(0.92)
    .linkColor(l => l.alive ? 'rgba(34,197,94,0.5)' : 'rgba(148,163,184,0.2)')
    .linkWidth(l => l.alive ? 1.5 : 0.8)
    .linkDirectionalParticles(l => l.alive ? 4 : 0)
    .linkDirectionalParticleSpeed(0.005)
    .linkDirectionalParticleWidth(1.5)
    .linkDirectionalParticleColor(() => '#4ade80')
    .onNodeClick(node => {
      if (node.group === 'router') return;
      showDevicePanel(node);
    })
    .onBackgroundClick(closePanel);

  window.addEventListener('resize', () => {
    if (graph3D) graph3D.width(container.offsetWidth);
  });
}

function showDevicePanel(node) {
  document.getElementById('panel-icon').className = `bi ${deviceIcon(node.hostname || '', node.is_wifi)}`;
  document.getElementById('panel-name').textContent = node.hostname || 'Inconnu';
  document.getElementById('panel-ip').textContent   = node.ip  || '—';
  document.getElementById('panel-mac').textContent  = node.mac || '—';
  document.getElementById('panel-link').textContent = node.link || '—';
  document.getElementById('panel-rssi').innerHTML   = node.is_wifi ? rssiBadge(node.rssi) : '<span class="text-muted">—</span>';

  const statusEl = document.getElementById('panel-status');
  if (node.is_blocked) {
    statusEl.innerHTML = '<span class="badge bg-danger-subtle text-danger">Bloqué</span>';
  } else if (node.active) {
    statusEl.innerHTML = '<span class="badge bg-success-subtle text-success">Connecté</span>';
  } else {
    statusEl.innerHTML = '<span class="badge bg-secondary-subtle text-secondary">Hors ligne</span>';
  }

  let actions = '';
  if (node.is_blocked) {
    actions = `<button class="btn-unblock w-100" onclick="unblockDevice('${esc(node.mac)}')">
      <i class="bi bi-check-circle me-1"></i>Débloquer</button>`;
  } else {
    if (node.is_wifi && node.active) {
      actions += `<button class="btn-disconnect w-100 mb-2" onclick="disconnectDevice('${esc(node.mac)}','${esc(node.hostname)}')">
        <i class="bi bi-wifi-off me-1"></i>Déconnecter</button>`;
      actions += `<button class="btn-kick-block w-100 mb-2" onclick="kickAndBlock('${esc(node.mac)}','${esc(node.hostname)}')">
        <i class="bi bi-x-octagon me-1"></i>Kick & Bloquer</button>`;
    }
    actions += `<button class="btn-block w-100" onclick="blockDevice('${esc(node.mac)}','${esc(node.hostname)}')">
      <i class="bi bi-slash-circle me-1"></i>Bloquer</button>`;
  }
  document.getElementById('panel-actions').innerHTML = actions;

  document.getElementById('device-panel').classList.add('panel-open');
}

function closePanel() {
  document.getElementById('device-panel').classList.remove('panel-open');
}

/* ── Table rendering ────────────────────────────────────────────────────── */

function renderLiveTable() {
  const tbody = document.getElementById('live-tbody');

  if (liveDevices.length === 0) {
    tbody.innerHTML = `<tr><td colspan="9"><div class="empty-state">
      <i class="bi bi-wifi-off"></i>Aucun appareil connecté en ce moment</div></td></tr>`;
  } else {
    const rows = [];
    for (const d of liveDevices) {
      try { rows.push(deviceRow(d)); }
      catch (err) {
        rows.push(`<tr><td colspan="9" class="text-danger small">Erreur sur ${escHtml(String(d?.hostname ?? d?.mac ?? '?'))}</td></tr>`);
      }
    }
    tbody.innerHTML = rows.join('');
  }
  setLiveState('table');
}

function deviceRow(d) {
  let statusBadge;
  if (d.is_blocked) {
    statusBadge = `<span class="badge bg-danger-subtle text-danger">Bloqué</span>`;
  } else if (d.active) {
    statusBadge = `<span class="badge bg-success-subtle text-success">Connecté</span>`;
  } else {
    statusBadge = `<span class="badge bg-secondary-subtle text-secondary">Hors ligne</span>`;
  }

  let actionBtn = '';
  if (d.is_blocked) {
    actionBtn = `<button class="btn-unblock" onclick="unblockDevice('${esc(d.mac)}')">
      <i class="bi bi-check-circle me-1"></i>Débloquer</button>`;
  } else {
    const kickBtn = (d.is_wifi && d.active)
      ? `<button class="btn-disconnect" onclick="disconnectDevice('${esc(d.mac)}','${esc(d.hostname)}')">
           <i class="bi bi-wifi-off me-1"></i>Déconnecter</button>` : '';
    const kickBlockBtn = (d.is_wifi && d.active)
      ? `<button class="btn-kick-block" onclick="kickAndBlock('${esc(d.mac)}','${esc(d.hostname)}')">
           <i class="bi bi-x-octagon me-1"></i>Kick & Bloquer</button>` : '';
    actionBtn = `<div class="d-flex gap-1 flex-wrap">
      ${kickBtn}${kickBlockBtn}
      <button class="btn-block" onclick="blockDevice('${esc(d.mac)}','${esc(d.hostname)}')">
        <i class="bi bi-slash-circle me-1"></i>Bloquer</button>
    </div>`;
  }

  const linkBadge = d.is_wifi
    ? `<span class="link-badge link-wifi"><i class="bi bi-wifi me-1"></i>${escHtml(d.link)}</span>`
    : `<span class="link-badge link-eth"><i class="bi bi-ethernet me-1"></i>${escHtml(d.link || 'Ethernet')}</span>`;

  return `
    <tr class="${d.active ? '' : 'row-inactive'}">
      <td>
        <div class="d-flex align-items-center gap-2">
          <div class="device-icon"><i class="bi ${deviceIcon(d.hostname, d.is_wifi)} text-muted"></i></div>
          <div>
            <div class="device-name">${escHtml(d.hostname)}</div>
            ${d.band ? `<div class="device-band">${d.band}</div>` : ''}
          </div>
        </div>
      </td>
      <td><code>${d.ip || '—'}</code></td>
      <td><code>${d.mac || '—'}</code></td>
      <td class="text-muted small">${fmtDate(d.first_seen)}</td>
      <td class="text-muted small">${fmtDate(d.last_seen)}</td>
      <td>${linkBadge}</td>
      <td>${d.is_wifi ? rssiBadge(d.rssi) : '<span class="text-muted">—</span>'}</td>
      <td>${statusBadge}</td>
      <td>${actionBtn}</td>
    </tr>`;
}

function renderHistoryTable(devices) {
  const tbody     = document.getElementById('history-tbody');
  const onlineMacs = new Set(liveDevices.map(h => h.mac));

  if (devices.length === 0) {
    tbody.innerHTML = `<tr><td colspan="7"><div class="empty-state">
      <i class="bi bi-clock-history"></i>Aucun historique disponible</div></td></tr>`;
    return;
  }

  tbody.innerHTML = devices.map(d => {
    const online = onlineMacs.has(d.mac);
    const status = d.is_blocked
      ? `<span class="badge bg-danger-subtle text-danger">Bloqué</span>`
      : online
        ? `<span class="badge bg-success-subtle text-success">En ligne</span>`
        : `<span class="badge bg-secondary-subtle text-secondary">Hors ligne</span>`;

    const actionBtn = d.is_blocked
      ? `<button class="btn-unblock" onclick="unblockDevice('${esc(d.mac)}')">
           <i class="bi bi-check-circle me-1"></i>Débloquer</button>`
      : `<button class="btn-block" onclick="blockDevice('${esc(d.mac)}','${esc(d.hostname || d.mac)}')">
           <i class="bi bi-slash-circle me-1"></i>Bloquer</button>`;

    return `
      <tr>
        <td>
          <div class="d-flex align-items-center gap-2">
            <div class="device-icon"><i class="bi ${deviceIcon(d.hostname)} text-muted"></i></div>
            <div class="device-name">${escHtml(d.hostname || 'Inconnu')}</div>
          </div>
        </td>
        <td><code>${d.ip || '—'}</code></td>
        <td><code>${d.mac || '—'}</code></td>
        <td class="text-muted small">${fmtDate(d.first_seen)}</td>
        <td class="text-muted small">${fmtDate(d.last_seen)}</td>
        <td>${status}</td>
        <td>${actionBtn}</td>
      </tr>`;
  }).join('');
}

function filterHistory() {
  const q = document.getElementById('history-search').value.toLowerCase();
  const filtered = q
    ? historyDevices.filter(d =>
        String(d.hostname || '').toLowerCase().includes(q) ||
        String(d.mac      || '').toLowerCase().includes(q) ||
        String(d.ip       || '').toLowerCase().includes(q))
    : historyDevices;
  renderHistoryTable(filtered);
}

/* ── UI state helpers ───────────────────────────────────────────────────── */

function setLiveState(state, msg = '') {
  document.getElementById('live-loading').classList.toggle('d-none', state !== 'loading');
  document.getElementById('live-error').classList.toggle('d-none', state !== 'error');
  document.getElementById('live-table-wrap').classList.toggle('d-none', state !== 'table');
  if (state === 'error')
    document.getElementById('live-error-msg').textContent = `Impossible de contacter la Bbox : ${msg}`;
}

function setHistoryState(state) {
  document.getElementById('history-loading').classList.toggle('d-none', state !== 'loading');
  document.getElementById('history-table-wrap').classList.toggle('d-none', state !== 'table');
}

function updateStats(data) {
  if (data.devices      != null) {
    document.getElementById('stat-connected').textContent = data.devices.length;
    document.getElementById('badge-live').textContent = data.devices.length || '';
  }
  if (data.blocked_count != null)
    document.getElementById('stat-blocked').textContent = data.blocked_count;
}

function setBboxStatus(online) {
  const el = document.getElementById('stat-status');
  el.className = online ? 'stat-value text-success' : 'stat-value text-danger';
  el.innerHTML = online
    ? `<i class="bi bi-circle-fill" style="font-size:.6rem;vertical-align:middle"></i> <span style="font-size:1rem">En ligne</span>`
    : `<i class="bi bi-circle-fill" style="font-size:.6rem;vertical-align:middle"></i> <span style="font-size:1rem">Hors ligne</span>`;
}

function updateRefreshTime() {
  document.getElementById('last-refresh').textContent =
    'Actualisé à ' + new Date().toLocaleTimeString('fr-FR', { hour: '2-digit', minute: '2-digit' });
}

/* ── Formatters ─────────────────────────────────────────────────────────── */

function fmtDate(iso) {
  if (!iso) return '<span class="text-muted">—</span>';
  const d = new Date(iso);
  return d.toLocaleDateString('fr-FR', {
    day: '2-digit', month: '2-digit', year: 'numeric',
    hour: '2-digit', minute: '2-digit',
  });
}

function rssiBadge(rssi) {
  if (rssi == null) return `<span class="rssi-badge rssi-unknown"><i class="bi bi-question-circle"></i> —</span>`;
  const cls  = rssi >= -50 ? 'rssi-excellent' : rssi >= -70 ? 'rssi-good' : rssi >= -85 ? 'rssi-fair' : 'rssi-poor';
  const icon = rssi >= -50 ? 'bi-reception-4'  : rssi >= -70 ? 'bi-reception-3' : rssi >= -85 ? 'bi-reception-2' : 'bi-reception-1';
  return `<span class="rssi-badge ${cls}"><i class="bi ${icon}"></i> ${rssi} dBm</span>`;
}

function deviceIcon(name = '', isWifi = false) {
  const n = String(name ?? '').toLowerCase();
  if (n.includes('iphone') || n.includes('android') || n.includes('phone') || n.includes('samsung') || n.includes('pixel') || n.includes('redmi') || n.includes('xiaomi') || n.includes('huawei') || n.includes('oppo'))
    return 'bi-phone';
  if (n.includes('ipad') || n.includes('tablet'))  return 'bi-tablet';
  if (n.includes('macbook') || n.includes('laptop') || n.includes('notebook')) return 'bi-laptop';
  if (n.includes('mac') && !n.includes('mac address')) return 'bi-display';
  if (n.includes('desktop') || n.includes('pc') || n.includes('workstation')) return 'bi-pc-display';
  if (n.includes('tv') || n.includes('chromecast') || n.includes('firestick') || n.includes('shield') || n.includes('bbox-tv')) return 'bi-tv';
  if (n.includes('xbox') || n.includes('playstation') || n.includes('nintendo') || n.includes('ps4') || n.includes('ps5')) return 'bi-controller';
  if (n.includes('print'))  return 'bi-printer';
  if (n.includes('nas') || n.includes('synology') || n.includes('qnap')) return 'bi-hdd-network';
  if (n.includes('bbox'))   return 'bi-router';
  return isWifi ? 'bi-wifi' : 'bi-hdd-rack';
}

/* ── Utils ──────────────────────────────────────────────────────────────── */

async function apiFetch(url, opts = {}) {
  const res = await fetch(url, opts);
  let data;
  try { data = await res.json(); } catch { throw new Error(`HTTP ${res.status} (réponse non-JSON)`); }
  if (res.status === 401) { window.location.href = '/login'; throw new Error('Session expirée'); }
  if (!res.ok || data.error) throw new Error(data.error || `HTTP ${res.status}`);
  return data;
}

function escHtml(s) {
  return String(s ?? '')
    .replace(/&/g, '&amp;').replace(/</g, '&lt;')
    .replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}

function esc(s) { return String(s ?? '').replace(/'/g, "\\'"); }
