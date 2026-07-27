// static/js/activity.js — live "what's running + how much headroom" indicator.
// Polls /api/activity (services/activity). Updates a glanceable badge on the
// sidebar button, and opens a panel with RAM/GPU, loaded models, active agent
// sessions, downloads, concurrency budget, and a headroom hint.

let _open = false, _interval = null, _started = false, _badgeMisses = 0;

const _el = (id) => document.getElementById(id);
const _esc = (s) => (s || '').replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
const _api = (p, o) => fetch(p, Object.assign({ credentials: 'same-origin' }, o || {}));

function _ramColor(p) { return p >= 85 ? '#ff5758' : p >= 65 ? '#e0a000' : '#2ecc71'; }
function _ago(ts) { const s = Math.max(0, Math.floor(Date.now() / 1000) - (ts || 0)); return s < 60 ? s + 's' : Math.floor(s / 60) + 'm'; }

async function _fetch() { try { return await (await _api('/api/activity')).json(); } catch (e) { return null; } }

function _updateBadge(cap) {
  const badge = _el('activity-badge');
  if (!badge) return;
  // A single failed 5s poll shouldn't blink the badge off — hold the last
  // reading through transient hiccups, hide only after 3 misses in a row.
  if (!cap || !cap.ram) {
    if (++_badgeMisses >= 3) badge.style.display = 'none';
    return;
  }
  _badgeMisses = 0;
  const p = cap.ram.percent;
  badge.style.display = 'inline-flex';
  badge.style.alignItems = 'center';
  badge.style.gap = '3px';
  badge.innerHTML = `<span style="width:7px;height:7px;border-radius:50%;background:${_ramColor(p)};display:inline-block;"></span>`
    + (cap.active_count ? `<span style="font-size:9px;opacity:.75;">${cap.active_count}</span>` : '');
  badge.title = `RAM ${p}% · ${(cap.loaded_models || []).length} model(s) loaded · ${cap.active_count} agent session(s)`;
}

// runs for the whole app session so the sidebar badge stays live
function startMonitor() {
  if (_started) return; _started = true;
  const tick = async () => { const c = await _fetch(); _updateBadge(c); if (_open) _render(c); };
  tick();
  setInterval(tick, 5000);
}

function openPanel() {
  if (_open) return;
  _open = true;
  const modal = document.createElement('div');
  modal.className = 'modal';
  modal.id = 'activity-modal';
  modal.innerHTML = `
    <div class="modal-content" style="max-width:640px;width:94vw;max-height:88vh;display:flex;flex-direction:column;">
      <div style="display:flex;align-items:center;gap:10px;margin-bottom:6px;">
        <div style="font-weight:600;font-size:15px;flex:1;">Activity &amp; Capacity</div>
        <span style="font-size:11px;opacity:.55;">live · refreshes 5s</span>
        <button class="modal-close" id="activity-close" aria-label="Close">×</button>
      </div>
      <div style="font-size:12px;opacity:.7;margin-bottom:10px;">Everything runs on this Mac. Here's what's using it now and how much room is left.</div>
      <div id="activity-body" style="overflow:auto;display:flex;flex-direction:column;gap:14px;">
        <div style="opacity:.6;padding:20px;text-align:center;">Loading…</div>
      </div>
    </div>`;
  document.body.appendChild(modal);
  _el('activity-close').addEventListener('click', closePanel);
  modal.addEventListener('click', (e) => { if (e.target === modal) closePanel(); });
  document.addEventListener('keydown', _onEsc);
  _fetch().then(_render);
}

function _onEsc(e) { if (e.key === 'Escape' && _open) closePanel(); }

function _bar(usedGb, totalGb, gpuBudgetGb, pct) {
  const usedPct = Math.min(100, Math.round((usedGb / totalGb) * 100));
  const gpuPct = Math.min(100, Math.round((gpuBudgetGb / totalGb) * 100));
  return `<div style="position:relative;height:22px;border-radius:6px;background:var(--panel2,#262b34);border:1px solid var(--border,#333);overflow:hidden;">
      <div style="position:absolute;left:0;top:0;bottom:0;width:${usedPct}%;background:${_ramColor(pct)};opacity:.85;"></div>
      <div style="position:absolute;left:${gpuPct}%;top:0;bottom:0;width:2px;background:var(--fg);opacity:.5;" title="Metal GPU budget (~75%)"></div>
      <div style="position:absolute;inset:0;display:flex;align-items:center;justify-content:center;font-size:11px;font-weight:600;">${usedGb} / ${totalGb} GB used (${pct}%)</div>
    </div>
    <div style="font-size:10px;opacity:.5;margin-top:2px;">▏ marker = GPU budget for models (~${gpuBudgetGb} GB)</div>`;
}

function _section(title, inner) {
  return `<section style="border:1px solid var(--border,#333);border-radius:8px;padding:10px 12px;">
    <div style="font-size:12px;font-weight:600;margin-bottom:7px;">${title}</div>${inner}</section>`;
}

function _render(cap) {
  const body = _el('activity-body');
  if (!body) return;
  if (!cap || !cap.ram) { body.innerHTML = '<div style="opacity:.6;padding:20px;">Could not read capacity.</div>'; return; }

  const r = cap.ram;
  let html = _section('Memory', _bar(r.used_gb, r.total_gb, cap.gpu_budget_gb, r.percent)
    + `<div style="display:flex;gap:14px;font-size:12px;margin-top:8px;flex-wrap:wrap;">
        <span>🟢 Free: <b>${r.free_gb} GB</b></span>
        <span>📦 Models loaded: <b>${cap.loaded_gb} GB</b></span>
        <span>🧮 CPU: <b>${cap.cpu_percent}%</b></span>
        <span>🎮 For models: <b>${cap.available_for_models_gb} GB</b></span>
      </div>`);

  // headroom advice
  html += `<div class="call" style="border:1px solid #2ecc71;border-left:4px solid #2ecc71;border-radius:8px;padding:9px 12px;background:rgba(46,204,113,.07);font-size:13px;">
      <b style="color:#2ecc71;">Headroom</b> · ${_esc(cap.advice)}<br>
      <span style="font-size:11px;opacity:.7;">≈ ${cap.headroom.small_7b} more small (7B) · ${cap.headroom.mid_14b} more mid (14B) · big coder ${cap.headroom.fits_big_coder ? 'fits ✓' : 'too big now'}</span>
    </div>`;

  // loaded models
  const lm = cap.loaded_models || [];
  html += _section('Models loaded right now', lm.length
    ? lm.map(m => `<div style="display:flex;justify-content:space-between;font-size:12.5px;padding:3px 0;">
        <span>🧠 ${_esc(m.name)}</span><span style="opacity:.65;">${m.size_gb} GB${m.gpu_gb ? ' · ' + m.gpu_gb + ' GB GPU' : ''}</span></div>`).join('')
    : '<div style="font-size:12px;opacity:.55;">None loaded — models load on first use (~seconds), unload when idle.</div>');

  // active agent sessions — each with a Stop button (this panel is the universal
  // kill switch: it hits the op's real server-side cancel, so closing/✕ is not
  // needed and detached runs actually halt).
  const act = cap.active || [];
  const _stopBtn = (id) => `<button class="act-stop" data-stop="${id}" title="Stop this operation"
      style="margin-left:auto;font-size:10px;padding:1px 8px;border:1px solid var(--border);border-radius:6px;background:transparent;color:var(--red,#ff5758);cursor:pointer;flex-shrink:0;">Stop</button>`;
  html += _section(`Running now (${act.length})`, (act.length || (cap.downloads || []).length)
    ? (act.map(a => `<div style="font-size:12.5px;padding:3px 0;display:flex;align-items:center;gap:5px;">▶ <b>${_esc(a.kind)}</b> ${_esc(a.label || '')} <span style="opacity:.55;">· ${_esc(a.model || '')} · ${_ago(a.started_at)}</span>${a.stoppable ? _stopBtn(a.id) : ''}</div>`).join('')
       + (cap.downloads || []).map(d => `<div style="font-size:12.5px;padding:3px 0;">⬇ ${_esc(d.id.replace('ollama:', ''))} <span style="opacity:.55;">${d.pct != null ? d.pct + '%' : ''}</span></div>`).join(''))
    : '<div style="font-size:12px;opacity:.55;">Nothing running — start a Chat, Code, Crew, or download.</div>');

  // concurrency budget
  const c = cap.concurrency || {};
  html += _section('Parallel budget (Ollama)',
    `<div style="font-size:12.5px;line-height:1.7;">
       • Up to <b>${_esc(String(c.max_loaded_models))}</b> models loaded at once<br>
       • Up to <b>${_esc(String(c.num_parallel))}</b> parallel requests per model<br>
       • Extra requests queue (max ${_esc(String(c.max_queue))}) — they don't fail, just wait their turn.
     </div>
     <div style="font-size:11px;opacity:.6;margin-top:6px;">You can run several chats/Code/Crew sessions together; the single GPU time-slices, so each is a bit slower under heavy load.</div>`);

  body.innerHTML = html;

  // Wire each Stop button → unified /api/activity/stop, then refresh immediately
  // (the 5s poll would otherwise leave a stopped row lingering).
  body.querySelectorAll('.act-stop').forEach((btn) => {
    btn.addEventListener('click', async () => {
      const id = Number(btn.dataset.stop);
      btn.disabled = true; btn.textContent = 'Stopping…';
      try {
        await _api('/api/activity/stop', {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ id }),
        });
      } catch (e) {}
      try { _render(await _fetch()); } catch (e) {}
    });
  });
}

function closePanel() { if (!_open) return; _open = false; document.removeEventListener('keydown', _onEsc); const m = _el('activity-modal'); if (m) m.remove(); }
function togglePanel() { _open ? closePanel() : openPanel(); }
function isPanelOpen() { return _open; }

const activityModule = { openPanel, closePanel, togglePanel, isPanelOpen, startMonitor };
export default activityModule;
