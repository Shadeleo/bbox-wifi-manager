'use strict';

/* ── State ──────────────────────────────────────────────────────────────── */
let liveDevices   = [];
let aclRules      = [];
let historyDevices = [];
let historyLoaded = false;

/* ── Bootstrap ──────────────────────────────────────────────────────────── */
document.addEventListener('DOMContentLoaded', () => {
  loadDevices();

  document.getElementById('history-tab-btn').addEventListener('shown.bs.tab', () => {
    if (!historyLoaded) loadHistory();
  });
});

/* ── API ────────────────────────────────────────────────────────────────── */

async function loadDevices() {
  setLiveState('loading');
  try {
    const data = await apiFetch('/api/devices');
    liveDevices = data.devices  ?? [];
    aclRules    = data.acl      ?? [];

    renderLiveTable();
    updateStats(data);
    updateRefreshTime();
    setBboxStatus(true);
  } catch (e) {
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
    setHistoryState('table'); // affiche table vide
    console.error('Historique :', e.message);
  }
}

async function blockDevice(mac, hostname) {
  if (!confirm(`Bloquer "${hostname}" (${mac}) ?\n\nL'appareil sera expulsé du réseau WiFi.`)) return;
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

async function unblockDevice(mac, ruleId) {
  if (!confirm(`Débloquer ${mac} ?\n\nL'appareil pourra se reconnecter au WiFi.`)) return;
  try {
    await apiFetch(`/api/block/${ruleId}?mac=${encodeURIComponent(mac)}`, { method: 'DELETE' });
    await reloadAll();
  } catch (e) {
    alert(`Impossible de débloquer l'appareil :\n${e.message}`);
  }
}

async function reloadAll() {
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

/* ── Rendering ──────────────────────────────────────────────────────────── */

function renderLiveTable() {
  const tbody = document.getElementById('live-tbody');

  if (liveDevices.length === 0) {
    tbody.innerHTML = `
      <tr>
        <td colspan="8">
          <div class="empty-state">
            <i class="bi bi-wifi-off"></i>
            Aucun appareil WiFi connecté en ce moment
          </div>
        </td>
      </tr>`;
  } else {
    tbody.innerHTML = liveDevices.map(deviceRow).join('');
  }
  setLiveState('table');
}

function deviceRow(d) {
  const rule = aclRules.find(r => r.mac === d.mac);

  const statusBadge = d.is_blocked
    ? `<span class="badge bg-danger-subtle text-danger">Bloqué</span>`
    : `<span class="badge bg-success-subtle text-success">Connecté</span>`;

  const actionBtn = d.is_blocked
    ? `<button class="btn-unblock" onclick="unblockDevice('${esc(d.mac)}', ${rule?.rule_id ?? 0})">
         <i class="bi bi-check-circle me-1"></i>Débloquer
       </button>`
    : `<button class="btn-block" onclick="blockDevice('${esc(d.mac)}', '${esc(d.hostname)}')">
         <i class="bi bi-slash-circle me-1"></i>Bloquer
       </button>`;

  return `
    <tr>
      <td>
        <div class="d-flex align-items-center gap-2">
          <div class="device-icon">
            <i class="bi ${deviceIcon(d.hostname)} text-muted"></i>
          </div>
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
      <td>${rssiBadge(d.rssi)}</td>
      <td>${statusBadge}</td>
      <td>${actionBtn}</td>
    </tr>`;
}

function renderHistoryTable(devices) {
  const tbody = document.getElementById('history-tbody');
  const onlineMacs = new Set(liveDevices.map(h => h.mac));

  if (devices.length === 0) {
    tbody.innerHTML = `
      <tr>
        <td colspan="6">
          <div class="empty-state">
            <i class="bi bi-clock-history"></i>
            Aucun historique disponible
          </div>
        </td>
      </tr>`;
    return;
  }

  tbody.innerHTML = devices.map(d => {
    const online  = onlineMacs.has(d.mac);
    const status  = d.is_blocked
      ? `<span class="badge bg-danger-subtle text-danger">Bloqué</span>`
      : online
        ? `<span class="badge bg-success-subtle text-success">En ligne</span>`
        : `<span class="badge bg-secondary-subtle text-secondary">Hors ligne</span>`;

    return `
      <tr>
        <td>
          <div class="d-flex align-items-center gap-2">
            <div class="device-icon">
              <i class="bi ${deviceIcon(d.hostname)} text-muted"></i>
            </div>
            <div class="device-name">${escHtml(d.hostname || 'Inconnu')}</div>
          </div>
        </td>
        <td><code>${d.ip || '—'}</code></td>
        <td><code>${d.mac || '—'}</code></td>
        <td class="text-muted small">${fmtDate(d.first_seen)}</td>
        <td class="text-muted small">${fmtDate(d.last_seen)}</td>
        <td>${status}</td>
      </tr>`;
  }).join('');
}

function filterHistory() {
  const q = document.getElementById('history-search').value.toLowerCase();
  const filtered = q
    ? historyDevices.filter(d =>
        (d.hostname || '').toLowerCase().includes(q) ||
        (d.mac      || '').toLowerCase().includes(q) ||
        (d.ip       || '').toLowerCase().includes(q)
      )
    : historyDevices;
  renderHistoryTable(filtered);
}

/* ── UI state helpers ───────────────────────────────────────────────────── */

function setLiveState(state, msg = '') {
  document.getElementById('live-loading').classList.toggle('d-none', state !== 'loading');
  document.getElementById('live-error').classList.toggle('d-none', state !== 'error');
  document.getElementById('live-table-wrap').classList.toggle('d-none', state !== 'table');
  if (state === 'error') document.getElementById('live-error-msg').textContent =
    `Impossible de contacter la Bbox : ${msg}`;
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

function deviceIcon(name = '') {
  const n = name.toLowerCase();
  if (n.includes('iphone') || n.includes('android') || n.includes('phone') || n.includes('samsung') || n.includes('pixel'))
    return 'bi-phone';
  if (n.includes('ipad') || n.includes('tablet'))
    return 'bi-tablet';
  if (n.includes('mac') || n.includes('macbook') || n.includes('laptop') || n.includes('pc'))
    return 'bi-laptop';
  if (n.includes('tv') || n.includes('chromecast') || n.includes('firestick') || n.includes('shield'))
    return 'bi-tv';
  if (n.includes('xbox') || n.includes('ps') || n.includes('playstation') || n.includes('nintendo'))
    return 'bi-controller';
  if (n.includes('print'))
    return 'bi-printer';
  return 'bi-device-hdd';
}

/* ── Utils ──────────────────────────────────────────────────────────────── */

async function apiFetch(url, opts = {}) {
  const res = await fetch(url, opts);
  const data = await res.json();
  if (!res.ok || data.error) throw new Error(data.error || `HTTP ${res.status}`);
  return data;
}

function escHtml(s) {
  return String(s)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;')
    .replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}

function esc(s) { return String(s).replace(/'/g, "\\'"); }
