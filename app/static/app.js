'use strict';

/* ── State ──────────────────────────────────────────────────────────────── */
let liveDevices    = [];
let historyDevices = [];
let historyLoaded  = false;
let graph2D        = null;
let liveSortKey    = null;
let liveSortDir    = 1;
let historySortKey = null;
let historySortDir = 1;
let bandwidthChart = null;
let activityChart  = null;
let liveChart       = null;
let liveHistory     = [];
let livePollTimer   = null;

/* ── Bootstrap ──────────────────────────────────────────────────────────── */
document.addEventListener('DOMContentLoaded', () => {
  loadDevices();
  loadHistory();

  document.getElementById('history-tab-btn').addEventListener('shown.bs.tab', () => {
    if (!historyLoaded) loadHistory();
  });

  document.getElementById('tab-3d-btn').addEventListener('shown.bs.tab', () => {
    if (liveDevices.length) initGraph2D();
  });

  document.getElementById('tab-conso-btn').addEventListener('shown.bs.tab', () => {
    loadNetworkStats();
    startLivePolling();
  });

  document.getElementById('tab-conso-btn').addEventListener('hidden.bs.tab', () => {
    stopLivePolling();
  });

  document.getElementById('mainTabs').addEventListener('shown.bs.tab', (e) => {
    document.getElementById('live-search-wrap').classList.toggle('d-none', e.target.id !== 'tab-live-btn');
    document.getElementById('history-search-wrap').classList.toggle('d-none', e.target.id !== 'history-tab-btn');
    document.getElementById('graph-search-wrap').classList.toggle('d-none', e.target.id !== 'tab-3d-btn');
    document.getElementById('unit-toggle-btn').classList.toggle('d-none', e.target.id !== 'tab-conso-btn');
  });
});

/* ── API calls ──────────────────────────────────────────────────────────── */

async function loadDevices() {
  setLiveState('loading');
  try {
    const data = await apiFetch('/api/devices');
    liveDevices = data.devices ?? [];
    filterLive();
    updateStats(data);
    updateRefreshTime();
    setBboxStatus(true);
    if (graph2D) initGraph2D();
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
    filterHistory();
    document.getElementById('stat-total').textContent = historyDevices.length;
    document.getElementById('badge-history').textContent = historyDevices.length || '';
    setHistoryState('table');
  } catch (e) {
    setHistoryState('table');
    console.error('Historique :', e.message);
  }
}

/* ── Consommation réseau ───────────────────────────────────────────────── */

let bandwidthUnit  = 'mbps'; // 'mbps' | 'mops'
let lastPeakMbps   = null;
let lastLiveRxMbps = 0;
let lastLiveTxMbps = 0;
let lastBandwidthPoints = [];

function unitLabel() { return bandwidthUnit === 'mbps' ? 'Mb/s' : 'Mo/s'; }
function toDisplayUnit(mbps) { return bandwidthUnit === 'mbps' ? mbps : mbps / 8; }

function toggleBandwidthUnit() {
  bandwidthUnit = bandwidthUnit === 'mbps' ? 'mops' : 'mbps';
  document.getElementById('unit-toggle-label').textContent = bandwidthUnit === 'mbps' ? 'Mo/s' : 'Mb/s';
  refreshConsoDisplay();
}

function refreshConsoDisplay() {
  document.getElementById('conso-peak').textContent =
    lastPeakMbps ? `${toDisplayUnit(lastPeakMbps).toFixed(1)} ${unitLabel()}` : '—';
  document.getElementById('conso-live').textContent =
    `↓ ${toDisplayUnit(lastLiveRxMbps).toFixed(1)} / ↑ ${toDisplayUnit(lastLiveTxMbps).toFixed(1)} ${unitLabel()}`;
  renderBandwidthChart(lastBandwidthPoints);
  renderLiveChart();
}

function chartTextColor() {
  return document.documentElement.getAttribute('data-bs-theme') === 'dark' ? '#e5e9f0' : '#0f172a';
}
function chartGridColor() {
  return document.documentElement.getAttribute('data-bs-theme') === 'dark' ? 'rgba(255,255,255,0.08)' : 'rgba(0,0,0,0.06)';
}

async function loadNetworkStats() {
  try {
    const data = await apiFetch('/api/network-stats');

    document.getElementById('conso-total').textContent =
      data.total_gb != null ? `${data.total_gb.toFixed(1)} Go` : '—';
    lastPeakMbps = data.peak_mbps ?? null;
    lastBandwidthPoints = data.points ?? [];
    document.getElementById('conso-peak').textContent =
      lastPeakMbps ? `${toDisplayUnit(lastPeakMbps).toFixed(1)} ${unitLabel()}` : '—';

    renderBandwidthChart(lastBandwidthPoints);
    renderActivityChart(data.activity ?? []);
    renderTopLists(data.activity ?? []);
  } catch (e) {
    console.error('[loadNetworkStats]', e);
  }
}

function renderTopLists(activity) {
  const topUpload   = [...activity].sort((a, b) => b.tx_usage - a.tx_usage).slice(0, 3);
  const topDownload = [...activity].sort((a, b) => b.rx_usage - a.rx_usage).slice(0, 3);
  renderTopList('top-upload-list', topUpload, 'tx_usage');
  renderTopList('top-download-list', topDownload, 'rx_usage');
}

const TOP_MEDALS = ['#fbbf24', '#cbd5e1', '#d97706'];

function renderTopList(containerId, items, key) {
  const container = document.getElementById(containerId);
  if (items.length === 0 || items.every(d => d[key] === 0)) {
    container.innerHTML = `<p class="text-muted small mb-0 text-center py-2">Aucune activité</p>`;
    return;
  }
  container.innerHTML = items.map((d, i) => {
    const level    = d[key] || 0;
    const pct      = Math.round((level / 8) * 100);
    const barColor = level >= 6 ? '#ef4444' : level >= 3 ? '#f59e0b' : '#22c55e';
    return `
    <div class="top-rank-row">
      <div class="top-rank-medal" style="background:${TOP_MEDALS[i] || 'var(--border)'}">${i + 1}</div>
      <div class="top-rank-icon"><i class="bi ${deviceIcon(d.hostname, true)}"></i></div>
      <div class="top-rank-info">
        <div class="top-rank-name">${escHtml(d.hostname)}</div>
        <div class="top-rank-bar-wrap"><div class="top-rank-bar" style="width:${pct}%; background:${barColor}"></div></div>
      </div>
      <div class="top-rank-value">${level}/8</div>
    </div>`;
  }).join('');
}

function renderBandwidthChart(points) {
  const canvas = document.getElementById('chart-bandwidth');
  const labels = points.map(p => new Date(p.ts.replace(' ', 'T'))
    .toLocaleTimeString('fr-FR', { hour: '2-digit', minute: '2-digit' }));
  const rx = points.map(p => toDisplayUnit(p.rx_kbps / 1000));
  const tx = points.map(p => toDisplayUnit(p.tx_kbps / 1000));
  const unit = unitLabel();

  if (bandwidthChart) bandwidthChart.destroy();
  bandwidthChart = new Chart(canvas, {
    type: 'line',
    data: {
      labels,
      datasets: [
        { label: `Téléchargement (${unit})`, data: rx, borderColor: '#3b82f6',
          backgroundColor: 'rgba(59,130,246,0.15)', fill: true, tension: 0.3, pointRadius: 0 },
        { label: `Envoi (${unit})`, data: tx, borderColor: '#f59e0b',
          backgroundColor: 'rgba(245,158,11,0.15)', fill: true, tension: 0.3, pointRadius: 0 },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      scales: {
        x: { ticks: { color: chartTextColor(), maxTicksLimit: 8 }, grid: { color: chartGridColor() } },
        y: { ticks: { color: chartTextColor() }, grid: { color: chartGridColor() }, beginAtZero: true },
      },
      plugins: { legend: { labels: { color: chartTextColor() } } },
    },
  });
}

function renderActivityChart(activity) {
  const canvas = document.getElementById('chart-activity');
  const sorted = [...activity].sort((a, b) => b.usage - a.usage).slice(0, 8);

  if (activityChart) { activityChart.destroy(); activityChart = null; }
  if (sorted.length === 0) return;

  const palette = ['#3b82f6', '#f59e0b', '#10b981', '#ef4444', '#8b5cf6', '#ec4899', '#14b8a6', '#f97316'];
  activityChart = new Chart(canvas, {
    type: 'doughnut',
    data: {
      labels: sorted.map(a => a.hostname),
      datasets: [{ data: sorted.map(a => a.usage), backgroundColor: palette }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: { legend: { position: 'bottom', labels: { color: chartTextColor(), boxWidth: 12, font: { size: 11 } } } },
    },
  });
}

/* ── Débit en temps réel ──────────────────────────────────────────────── */

const LIVE_POLL_MS = 2000;
const LIVE_WINDOW   = 30; // 30 points × 2s = fenêtre glissante de 60s

function startLivePolling() {
  stopLivePolling();
  liveHistory = [];
  pollLiveStats();
  livePollTimer = setInterval(pollLiveStats, LIVE_POLL_MS);
}

function stopLivePolling() {
  if (livePollTimer) { clearInterval(livePollTimer); livePollTimer = null; }
}

async function pollLiveStats() {
  try {
    const data = await apiFetch('/api/network-stats/live');
    lastLiveRxMbps = (data.rx_kbps || 0) / 1000;
    lastLiveTxMbps = (data.tx_kbps || 0) / 1000;
    liveHistory.push({ time: new Date(), rx: lastLiveRxMbps, tx: lastLiveTxMbps });
    if (liveHistory.length > LIVE_WINDOW) liveHistory.shift();

    document.getElementById('conso-live').textContent =
      `↓ ${toDisplayUnit(lastLiveRxMbps).toFixed(1)} / ↑ ${toDisplayUnit(lastLiveTxMbps).toFixed(1)} ${unitLabel()}`;

    renderLiveChart();
    if (data.activity) renderTopLists(data.activity);
  } catch (e) {
    console.error('[pollLiveStats]', e);
  }
}

function renderLiveChart() {
  const canvas = document.getElementById('chart-live');
  const labels = liveHistory.map(p =>
    p.time.toLocaleTimeString('fr-FR', { hour: '2-digit', minute: '2-digit', second: '2-digit' }));
  const rx = liveHistory.map(p => toDisplayUnit(p.rx));
  const tx = liveHistory.map(p => toDisplayUnit(p.tx));
  const unit = unitLabel();

  if (liveChart) {
    liveChart.data.labels = labels;
    liveChart.data.datasets[0].data = rx;
    liveChart.data.datasets[0].label = `Téléchargement (${unit})`;
    liveChart.data.datasets[1].data = tx;
    liveChart.data.datasets[1].label = `Envoi (${unit})`;
    liveChart.update('none');
    return;
  }

  liveChart = new Chart(canvas, {
    type: 'line',
    data: {
      labels,
      datasets: [
        { label: `Téléchargement (${unit})`, data: rx, borderColor: '#3b82f6',
          backgroundColor: 'rgba(59,130,246,0.15)', fill: true, tension: 0.3, pointRadius: 0 },
        { label: `Envoi (${unit})`, data: tx, borderColor: '#f59e0b',
          backgroundColor: 'rgba(245,158,11,0.15)', fill: true, tension: 0.3, pointRadius: 0 },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      animation: false,
      scales: {
        x: { ticks: { color: chartTextColor(), maxTicksLimit: 6 }, grid: { color: chartGridColor() } },
        y: { ticks: { color: chartTextColor() }, grid: { color: chartGridColor() }, beginAtZero: true },
      },
      plugins: { legend: { labels: { color: chartTextColor() } } },
    },
  });
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
  const consoActive = document.querySelector('#tab-conso.active');
  if (consoActive) loadNetworkStats();
}

/* ── Network Graph — pure canvas 2D, zero external dependency ────────────── */

const NODE_COLOR   = { router: '#60a5fa', active: '#4ade80', blocked: '#f87171', inactive: '#475569' };
const DEVICE_EMOJI = {
  router: '📡', phone: '📱', tablet: '📱', laptop: '💻',
  display: '🖥', tv: '📺', controller: '🎮', printer: '🖨',
  'hdd-network': '💾', wifi: '📶',
};

function getNodeIconName(node) {
  if (node.group === 'router') return 'router';
  const n = String(node.hostname || '').toLowerCase();
  if (/iphone|android|phone|samsung|pixel|redmi|xiaomi|huawei|oppo/.test(n)) return 'phone';
  if (/ipad|tablet/.test(n))     return 'tablet';
  if (/macbook|laptop|notebook/.test(n)) return 'laptop';
  if (/mac|desktop|pc|workstation/.test(n)) return 'display';
  if (/\btv\b|chromecast|firestick|shield|appletv/.test(n)) return 'tv';
  if (/xbox|playstation|nintendo|ps4|ps5/.test(n)) return 'controller';
  if (/print/.test(n)) return 'printer';
  if (/nas|synology|qnap/.test(n)) return 'hdd-network';
  return 'wifi';
}

function hexToRgb(hex) {
  return [parseInt(hex.slice(1,3),16), parseInt(hex.slice(3,5),16), parseInt(hex.slice(5,7),16)];
}
function lighten(hex, amt) {
  const [r,g,b] = hexToRgb(hex);
  return `rgb(${Math.min(255,r+amt)},${Math.min(255,g+amt)},${Math.min(255,b+amt)})`;
}

/* ── Graph state ── */
let gCanvas    = null;   // HTMLCanvasElement
let gCtx       = null;   // CanvasRenderingContext2D
let gNodes     = [];
let gLinks     = [];
let gParticles = [];
let gStars     = [];
let gHover     = null;
let gAnimId    = null;
let gTooltip   = null;
let gSearchTerm = '';

function nodeR(node) { return node.group === 'router' ? 30 : 20; }

/* ── Layout: router in centre, devices in a circle ── */
function buildLayout() {
  const W = gCanvas.width, H = gCanvas.height;
  const cx = W / 2, cy = H / 2;
  const count = liveDevices.length || 1;
  const radius = Math.min(W, H) * 0.34;

  gNodes = [{ id: '__bbox__', hostname: 'Bbox', group: 'router', x: cx, y: cy }];
  gLinks = [];

  liveDevices.forEach((d, i) => {
    const angle = (i / count) * Math.PI * 2 - Math.PI / 2;
    gNodes.push({
      ...d,
      id:    d.mac,
      group: d.is_blocked ? 'blocked' : d.active ? 'active' : 'inactive',
      x: cx + Math.cos(angle) * radius,
      y: cy + Math.sin(angle) * radius,
    });
    gLinks.push({ src: '__bbox__', tgt: d.mac, alive: !!d.active });
  });

  // Animate particles along active links
  gParticles = [];
  gLinks.filter(l => l.alive).forEach(l => {
    for (let i = 0; i < 4; i++) {
      gParticles.push({ l, t: Math.random() });
    }
  });
}

function nodeById(id) { return gNodes.find(n => n.id === id); }

function nodeMatchesSearch(node) {
  if (!gSearchTerm || node.group === 'router') return true;
  const hay = `${node.hostname || ''} ${node.ip || ''} ${node.mac || ''}`.toLowerCase();
  return hay.includes(gSearchTerm);
}

function filterGraph() {
  gSearchTerm = document.getElementById('graph-search').value.trim().toLowerCase();
}

/* ── Drawing ── */
function drawFrame() {
  const ctx = gCtx, W = gCanvas.width, H = gCanvas.height;

  // Background
  ctx.fillStyle = '#060d1a';
  ctx.fillRect(0, 0, W, H);

  // Stars
  gStars.forEach(s => {
    ctx.beginPath(); ctx.arc(s.x, s.y, s.r, 0, Math.PI * 2);
    ctx.fillStyle = `rgba(255,255,255,${s.a})`; ctx.fill();
  });

  // Links
  gLinks.forEach(l => {
    const s = nodeById(l.src), t = nodeById(l.tgt);
    if (!s || !t) return;
    ctx.beginPath(); ctx.moveTo(s.x, s.y); ctx.lineTo(t.x, t.y);
    ctx.strokeStyle = l.alive ? 'rgba(74,222,128,0.35)' : 'rgba(148,163,184,0.1)';
    ctx.lineWidth   = l.alive ? 1.5 : 0.8;
    ctx.stroke();
  });

  // Particles along active links
  gParticles.forEach(p => {
    p.t = (p.t + 0.005) % 1;
    const s = nodeById(p.l.src), t = nodeById(p.l.tgt);
    if (!s || !t) return;
    const x = s.x + (t.x - s.x) * p.t;
    const y = s.y + (t.y - s.y) * p.t;
    // Glow
    const g = ctx.createRadialGradient(x, y, 0, x, y, 8);
    g.addColorStop(0, 'rgba(74,222,128,0.9)');
    g.addColorStop(1, 'rgba(74,222,128,0)');
    ctx.fillStyle = g;
    ctx.beginPath(); ctx.arc(x, y, 8, 0, Math.PI * 2); ctx.fill();
    // Core dot
    ctx.fillStyle = '#4ade80';
    ctx.beginPath(); ctx.arc(x, y, 3, 0, Math.PI * 2); ctx.fill();
  });

  // Nodes
  gNodes.forEach(node => drawNode(ctx, node, node === gHover));

  gAnimId = requestAnimationFrame(drawFrame);
}

function drawNode(ctx, node, hover) {
  const R        = nodeR(node);
  const isRouter = node.group === 'router';
  const color    = NODE_COLOR[node.group] || NODE_COLOR.inactive;
  const [cr,cg,cb] = hexToRgb(color);
  const {x, y}   = node;
  const matched  = nodeMatchesSearch(node);

  ctx.save();
  if (!matched) ctx.globalAlpha = 0.18;

  // Glow (always on router, on hover for others)
  if (isRouter || hover) {
    const g = ctx.createRadialGradient(x, y, R * 0.4, x, y, R * 2.8);
    g.addColorStop(0, `rgba(${cr},${cg},${cb},${isRouter ? 0.6 : 0.45})`);
    g.addColorStop(1, `rgba(${cr},${cg},${cb},0)`);
    ctx.beginPath(); ctx.arc(x, y, R * 2.8, 0, Math.PI * 2);
    ctx.fillStyle = g; ctx.fill();
  }

  // Core — radial gradient for 3-D shading
  const grad = ctx.createRadialGradient(x - R * 0.35, y - R * 0.35, 2, x, y, R);
  grad.addColorStop(0, lighten(color, 90));
  grad.addColorStop(1, color);
  ctx.beginPath(); ctx.arc(x, y, R, 0, Math.PI * 2);
  ctx.fillStyle = grad; ctx.fill();

  // White border
  ctx.strokeStyle = `rgba(255,255,255,${isRouter ? 0.8 : 0.45})`;
  ctx.lineWidth   = isRouter ? 2.5 : 1.5;
  ctx.stroke();

  // Router dashed outer ring
  if (isRouter) {
    ctx.beginPath(); ctx.arc(x, y, R + 8, 0, Math.PI * 2);
    ctx.strokeStyle = `rgba(${cr},${cg},${cb},0.55)`;
    ctx.lineWidth   = 2;
    ctx.setLineDash([5, 5]); ctx.stroke(); ctx.setLineDash([]);
  }

  // Search match ring
  if (matched && gSearchTerm && !isRouter) {
    ctx.beginPath(); ctx.arc(x, y, R + 6, 0, Math.PI * 2);
    ctx.strokeStyle = 'rgba(250,204,21,0.95)';
    ctx.lineWidth   = 2.5;
    ctx.stroke();
  }

  // Emoji
  const emoji = DEVICE_EMOJI[getNodeIconName(node)] || '📶';
  ctx.font         = `${Math.round(R * (isRouter ? 1.05 : 0.95))}px serif`;
  ctx.textAlign    = 'center';
  ctx.textBaseline = 'middle';
  ctx.fillText(emoji, x, y);

  // Label below node
  const label = (node.hostname || '').length > 15
    ? node.hostname.slice(0, 15) + '…' : (node.hostname || '');
  if (label) {
    ctx.font         = 'bold 12px "Segoe UI", system-ui, sans-serif';
    ctx.textBaseline = 'top';
    ctx.fillStyle    = '#e2e8f0';
    ctx.shadowColor  = '#060d1a'; ctx.shadowBlur = 6;
    ctx.fillText(label, x, y + R + 6);
    ctx.shadowBlur   = 0;
  }

  ctx.restore();
}

/* ── Hit-test ── */
function nodeAt(px, py) {
  // Reverse order so top nodes get priority
  for (let i = gNodes.length - 1; i >= 0; i--) {
    const n = gNodes[i];
    const R = nodeR(n), dx = n.x - px, dy = n.y - py;
    if (dx * dx + dy * dy <= R * R) return n;
  }
  return null;
}

/* ── Tooltip ── */
function showTooltip(node, canvasX, canvasY) {
  if (!gTooltip) {
    gTooltip = document.createElement('div');
    gTooltip.style.cssText = [
      'position:absolute', 'pointer-events:none', 'z-index:99',
      'background:rgba(6,13,26,.92)', 'color:#f1f5f9',
      'padding:7px 13px', 'border-radius:9px',
      'font:13px/1.4 system-ui,sans-serif',
      'border:1px solid rgba(255,255,255,.1)',
      'white-space:nowrap',
    ].join(';');
    document.getElementById('graph-3d').parentElement.appendChild(gTooltip);
  }
  gTooltip.innerHTML = `<b>${escHtml(node.hostname || '')}</b><br>
    <span style="color:#94a3b8;font-size:11px">${escHtml(node.ip || node.mac || '')}</span>`;
  gTooltip.style.left    = (canvasX + 14) + 'px';
  gTooltip.style.top     = (canvasY - 10) + 'px';
  gTooltip.style.display = 'block';
}
function hideTooltip() {
  if (gTooltip) gTooltip.style.display = 'none';
}

/* ── Events ── */
function handleGraphClick(e) {
  const r    = gCanvas.getBoundingClientRect();
  const node = nodeAt(e.clientX - r.left, e.clientY - r.top);
  if (node && node.group !== 'router') showDevicePanel(node);
  else closePanel();
}
function handleGraphMove(e) {
  const r    = gCanvas.getBoundingClientRect();
  const node = nodeAt(e.clientX - r.left, e.clientY - r.top);
  gHover     = node || null;
  gCanvas.style.cursor = (node && node.group !== 'router') ? 'pointer' : 'default';
  if (node && node.group !== 'router') showTooltip(node, e.clientX - r.left, e.clientY - r.top);
  else hideTooltip();
}

/* ── Init / refresh ── */
function initGraph2D() {
  const container = document.getElementById('graph-3d');
  if (!container) return;

  const W = Math.max(400, container.offsetWidth
            || container.closest('.tab-pane')?.offsetWidth
            || document.querySelector('.panel-card')?.offsetWidth
            || 900);
  const H = Math.max(540, window.innerHeight - 210);

  if (gAnimId) { cancelAnimationFrame(gAnimId); gAnimId = null; }

  // Create canvas fresh every time data changes
  container.innerHTML = '';
  gCanvas = document.createElement('canvas');
  gCanvas.width  = W;
  gCanvas.height = H;
  gCanvas.style.cssText = 'display:block;width:100%;height:100%';
  container.style.height = H + 'px';
  container.appendChild(gCanvas);
  gCtx = gCanvas.getContext('2d');

  // Stars (random but stable for this session)
  gStars = Array.from({ length: 220 }, () => ({
    x: Math.random() * W,
    y: Math.random() * H,
    r: Math.random() * 1.3 + 0.2,
    a: Math.random() * 0.55 + 0.1,
  }));

  buildLayout();

  gCanvas.addEventListener('click',     handleGraphClick);
  gCanvas.addEventListener('mousemove', handleGraphMove);
  gCanvas.addEventListener('mouseleave', () => { gHover = null; hideTooltip(); });

  drawFrame();

  window.addEventListener('resize', () => {
    if (!gCanvas) return;
    const nw = container.offsetWidth || W;
    gCanvas.width = nw;
    buildLayout();
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
    actions = `<button class="btn-unblock w-100" onclick="unblockDevice('${escAttrJs(node.mac)}')">
      <i class="bi bi-check-circle me-1"></i>Débloquer</button>`;
  } else {
    if (node.is_wifi && node.active) {
      actions += `<button class="btn-disconnect w-100 mb-2" onclick="disconnectDevice('${escAttrJs(node.mac)}','${escAttrJs(node.hostname)}')">
        <i class="bi bi-wifi-off me-1"></i>Déconnecter</button>`;
      actions += `<button class="btn-kick-block w-100 mb-2" onclick="kickAndBlock('${escAttrJs(node.mac)}','${escAttrJs(node.hostname)}')">
        <i class="bi bi-x-octagon me-1"></i>Kick & Bloquer</button>`;
    }
    actions += `<button class="btn-block w-100" onclick="blockDevice('${escAttrJs(node.mac)}','${escAttrJs(node.hostname)}')">
      <i class="bi bi-slash-circle me-1"></i>Bloquer</button>`;
  }
  document.getElementById('panel-actions').innerHTML = actions;
  document.getElementById('device-panel').classList.add('panel-open');
}

function closePanel() {
  document.getElementById('device-panel').classList.remove('panel-open');
}

/* ── Table rendering ────────────────────────────────────────────────────── */

function renderLiveTable(devices = liveDevices) {
  const tbody = document.getElementById('live-tbody');
  const activeDevices = devices.filter(d => d.active);

  if (activeDevices.length === 0) {
    tbody.innerHTML = `<tr><td colspan="9"><div class="empty-state">
      <i class="bi bi-wifi-off"></i>Aucun appareil connecté en ce moment</div></td></tr>`;
  } else {
    const rows = [];
    for (const d of activeDevices) {
      try { rows.push(deviceRow(d)); }
      catch (err) {
        rows.push(`<tr><td colspan="9" class="text-danger small">Erreur sur ${escHtml(String(d?.hostname ?? d?.mac ?? '?'))}</td></tr>`);
      }
    }
    tbody.innerHTML = rows.join('');
  }
  setLiveState('table');
}

function filterLive() {
  const q = document.getElementById('live-search').value.toLowerCase();
  let filtered = q
    ? liveDevices.filter(d =>
        String(d.hostname || '').toLowerCase().includes(q) ||
        String(d.mac      || '').toLowerCase().includes(q) ||
        String(d.ip       || '').toLowerCase().includes(q))
    : liveDevices;
  if (liveSortKey) {
    filtered = [...filtered].sort((a, b) => liveSortDir * compareValues(a, b, liveSortKey));
  }
  renderLiveTable(filtered);
}

/* ── Sorting ─────────────────────────────────────────────────────────────── */

function compareValues(a, b, key) {
  if (key === 'ip') {
    const toNum = (ip) => (ip || '0.0.0.0').split('.')
      .map(n => parseInt(n, 10) || 0)
      .reduce((acc, n) => acc * 256 + n, 0);
    return toNum(a.ip) - toNum(b.ip);
  }
  if (key === 'rssi') {
    const va = a.rssi == null ? -Infinity : a.rssi;
    const vb = b.rssi == null ? -Infinity : b.rssi;
    return va - vb;
  }
  if (key === 'status') {
    const rank = (d) => d.is_blocked ? 0 : d.active ? 1 : 2;
    return rank(a) - rank(b);
  }
  if (key === 'status_history') {
    return (a.is_blocked ? 0 : 1) - (b.is_blocked ? 0 : 1);
  }
  const va = String(a[key] ?? '').toLowerCase();
  const vb = String(b[key] ?? '').toLowerCase();
  if (va < vb) return -1;
  if (va > vb) return 1;
  return 0;
}

function updateSortIcons(scopeId, key, dir) {
  document.querySelectorAll(`#${scopeId} .sort-btn`).forEach(btn => {
    const icon = btn.querySelector('i');
    if (btn.dataset.key === key) {
      icon.className = dir === 1 ? 'bi bi-sort-down' : 'bi bi-sort-up';
      btn.classList.add('active');
    } else {
      icon.className = 'bi bi-arrow-down-up';
      btn.classList.remove('active');
    }
  });
}

function sortLiveTable(key) {
  if (liveSortKey === key) liveSortDir *= -1;
  else { liveSortKey = key; liveSortDir = 1; }
  updateSortIcons('tab-live', liveSortKey, liveSortDir);
  filterLive();
}

function sortHistoryTable(key) {
  if (historySortKey === key) historySortDir *= -1;
  else { historySortKey = key; historySortDir = 1; }
  updateSortIcons('tab-history', historySortKey, historySortDir);
  filterHistory();
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
    actionBtn = `<button class="tbl-action-btn tbl-unblock" onclick="unblockDevice('${escAttrJs(d.mac)}')" title="Débloquer">
      <i class="bi bi-check-circle"></i></button>`;
  } else {
    const kickBtn = (d.is_wifi && d.active)
      ? `<button class="tbl-action-btn tbl-disconnect" onclick="disconnectDevice('${escAttrJs(d.mac)}','${escAttrJs(d.hostname)}')" title="Déconnecter">
           <i class="bi bi-wifi-off"></i></button>` : '';
    const kickBlockBtn = (d.is_wifi && d.active)
      ? `<button class="tbl-action-btn tbl-kick-block" onclick="kickAndBlock('${escAttrJs(d.mac)}','${escAttrJs(d.hostname)}')" title="Kick &amp; Bloquer">
           <i class="bi bi-x-octagon"></i></button>` : '';
    actionBtn = `<div class="d-flex gap-1">
      ${kickBtn}${kickBlockBtn}
      <button class="tbl-action-btn tbl-block" onclick="blockDevice('${escAttrJs(d.mac)}','${escAttrJs(d.hostname)}')" title="Bloquer">
        <i class="bi bi-slash-circle"></i></button>
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
      <td class="d-none d-md-table-cell"><code>${d.mac || '—'}</code></td>
      <td class="d-none d-xl-table-cell text-muted small">${fmtDate(d.first_seen)}</td>
      <td class="d-none d-lg-table-cell text-muted small">${fmtDate(d.last_seen)}</td>
      <td class="d-none d-sm-table-cell col-narrow">${linkBadge}</td>
      <td class="d-none d-sm-table-cell col-narrow">${d.is_wifi ? rssiBadge(d.rssi) : '<span class="text-muted">—</span>'}</td>
      <td class="col-narrow">${statusBadge}</td>
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
      ? `<button class="tbl-action-btn tbl-unblock" onclick="unblockDevice('${escAttrJs(d.mac)}')" title="Débloquer">
           <i class="bi bi-check-circle"></i></button>`
      : `<button class="tbl-action-btn tbl-block" onclick="blockDevice('${escAttrJs(d.mac)}','${escAttrJs(d.hostname || d.mac)}')" title="Bloquer">
           <i class="bi bi-slash-circle"></i></button>`;

    return `
      <tr>
        <td>
          <div class="d-flex align-items-center gap-2">
            <div class="device-icon"><i class="bi ${deviceIcon(d.hostname)} text-muted"></i></div>
            <div class="device-name">${escHtml(d.hostname || 'Inconnu')}</div>
          </div>
        </td>
        <td><code>${d.ip || '—'}</code></td>
        <td class="d-none d-md-table-cell"><code>${d.mac || '—'}</code></td>
        <td class="d-none d-lg-table-cell text-muted small">${fmtDate(d.first_seen)}</td>
        <td class="d-none d-sm-table-cell text-muted small">${fmtDate(d.last_seen)}</td>
        <td class="col-narrow">${status}</td>
        <td>${actionBtn}</td>
      </tr>`;
  }).join('');
}

function filterHistory() {
  const q = document.getElementById('history-search').value.toLowerCase();
  let filtered = q
    ? historyDevices.filter(d =>
        String(d.hostname || '').toLowerCase().includes(q) ||
        String(d.mac      || '').toLowerCase().includes(q) ||
        String(d.ip       || '').toLowerCase().includes(q))
    : historyDevices;
  if (historySortKey) {
    filtered = [...filtered].sort((a, b) => historySortDir * compareValues(a, b, historySortKey));
  }
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
    const activeCount = data.devices.filter(d => d.active).length;
    document.getElementById('stat-connected').textContent = activeCount;
    document.getElementById('stat-known').textContent     = data.devices.length;
    document.getElementById('badge-live').textContent = activeCount || '';
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

/* Echappe une valeur destinee a un litteral de chaine JS place DANS un
   attribut HTML, par exemple onclick="fn('${escAttrJs(v)}')".
   Le parseur HTML decode les entites AVANT que JS ne lise la chaine : une
   apostrophe encodee en &#39; y redeviendrait une vraie apostrophe et
   refermerait le litteral. On echappe donc la quote a la mode JS (\'),
   et seulement le reste a la mode HTML.
   Pour du texte affiche, utiliser escHtml. */
function escAttrJs(s) {
  return String(s ?? '')
    .replace(/\\/g, '\\\\')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, "\\'")
    .replace(/\r/g, '\\r')
    .replace(/\n/g, '\\n');
}
