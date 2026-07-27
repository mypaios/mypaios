// static/js/mailGuard.js — Mail Guard panel: local AI email triage across all
// accounts. Shield button in the Email sidebar header opens this. Backed by
// /api/mailguard/* (routes/mailguard_routes.py + services/mailguard).

let _open = false;
let _poll = null;

const _el = (id) => document.getElementById(id);
const _esc = (s) => (s || '').replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
const _api = (p, o) => fetch(p, Object.assign({ credentials: 'same-origin' }, o || {}));

const VERDICT_ICON = { urgent: '🔴', important: '🟡', fyi: '⚪', marketing: '🛍️', noise: '🗑️' };

function openPanel() {
  if (_open) return;
  _open = true;
  const modal = document.createElement('div');
  modal.className = 'modal';
  modal.id = 'mailguard-modal';
  modal.innerHTML = `
    <div class="modal-content" style="max-width:820px;width:95vw;max-height:90vh;display:flex;flex-direction:column;">
      <div class="modal-header" style="display:flex;align-items:center;gap:10px;">
        <h4 style="margin:0;flex:1;display:flex;align-items:center;gap:8px;">🛡️ Mail Guard
          <span id="mg-state" style="font-size:11px;font-weight:400;opacity:.6;"></span></h4>
        <label style="font-size:12px;display:flex;align-items:center;gap:5px;cursor:pointer;">
          <input type="checkbox" id="mg-enabled"> on</label>
        <button class="admin-btn-sm" id="mg-sweep" style="font-weight:600;">Sweep now ▶</button>
        <button class="close-btn" id="mg-close">✖</button>
      </div>
      <div style="font-size:12px;opacity:.7;padding:2px 0 8px;">Watches every connected inbox: keeps what matters, files marketing into a recoverable folder, drafts replies for urgent mail — all on your local models. Nothing is ever sent or permanently deleted by the AI.</div>

      <div id="mg-scroll" style="overflow:auto;display:flex;flex-direction:column;gap:12px;padding-right:2px;">

        <section style="border:1px solid var(--border);border-radius:9px;padding:10px 12px;">
          <div style="font-size:12px;font-weight:600;margin-bottom:6px;">Behavior</div>
          <div style="display:flex;flex-wrap:wrap;gap:10px;align-items:center;font-size:12px;">
            <label>Sweep every <input id="mg-interval" type="number" min="2" max="720" style="width:54px;background:var(--bg2,#1b1f27);color:var(--fg);border:1px solid var(--border);border-radius:6px;padding:3px 6px;"> min</label>
            <label>Filtered folder <input id="mg-folder" type="text" style="width:110px;background:var(--bg2,#1b1f27);color:var(--fg);border:1px solid var(--border);border-radius:6px;padding:3px 6px;"></label>
            <label style="display:flex;align-items:center;gap:4px;cursor:pointer;"><input type="checkbox" id="mg-drafts"> draft replies (urgent/important)</label>
            <label style="display:flex;align-items:center;gap:4px;cursor:pointer;" title="Off = marketing is FILED (recoverable). On = straight to Trash."><input type="checkbox" id="mg-harddelete"> hard-delete marketing</label>
            <button class="admin-btn-sm" id="mg-save" style="font-weight:600;">Save</button>
            <span id="mg-msg" style="font-size:11px;opacity:.7;"></span>
          </div>
        </section>

        <section style="border:1px solid var(--border);border-radius:9px;padding:10px 12px;">
          <div style="display:flex;align-items:center;gap:8px;margin-bottom:6px;">
            <div style="font-size:12px;font-weight:600;">Last 24 hours</div>
            <span id="mg-accounts" style="font-size:11px;opacity:.55;"></span>
          </div>
          <div id="mg-stats" style="display:flex;flex-wrap:wrap;gap:8px;font-size:12px;">Loading…</div>
        </section>

        <section style="border:1px solid var(--border);border-radius:9px;padding:10px 12px;">
          <div style="font-size:12px;font-weight:600;margin-bottom:6px;">Rules — you teach it</div>
          <div style="font-size:11px;opacity:.65;margin-bottom:8px;"><b>Keep (VIP)</b> senders are never filtered and rank as important. <b>Filter</b> patterns go straight to the filtered folder. Restoring a wrongly-filed email auto-adds its sender to Keep.</div>
          <div style="display:flex;gap:6px;flex-wrap:wrap;align-items:center;margin-bottom:8px;">
            <select id="mg-rule-kind" style="background:var(--bg2,#1b1f27);color:var(--fg);border:1px solid var(--border);border-radius:6px;padding:4px 6px;font-size:12px;">
              <option value="include">Keep (VIP)</option>
              <option value="exclude">Filter</option>
            </select>
            <select id="mg-rule-field" style="background:var(--bg2,#1b1f27);color:var(--fg);border:1px solid var(--border);border-radius:6px;padding:4px 6px;font-size:12px;">
              <option value="sender">sender contains</option>
              <option value="domain">domain contains</option>
              <option value="subject">subject contains</option>
            </select>
            <input id="mg-rule-pattern" type="text" placeholder="boss@company.com · newsletters.example · 'invoice'"
              style="flex:1;min-width:160px;background:var(--bg2,#1b1f27);color:var(--fg);border:1px solid var(--border);border-radius:6px;padding:4px 8px;font-size:12px;">
            <button class="admin-btn-sm" id="mg-rule-add" style="font-weight:600;">+ Add</button>
          </div>
          <div id="mg-rules" style="display:flex;flex-direction:column;gap:6px;font-size:12px;">Loading…</div>
        </section>

        <section style="border:1px solid var(--border);border-radius:9px;padding:10px 12px;">
          <div style="display:flex;align-items:center;gap:8px;margin-bottom:6px;">
            <div style="font-size:12px;font-weight:600;">Recent decisions — full audit trail</div>
            <span style="flex:1;"></span>
            <button class="admin-btn-sm" id="mg-refresh" title="Refresh">↻</button>
          </div>
          <div id="mg-decisions" style="display:flex;flex-direction:column;gap:6px;font-size:12px;max-height:34vh;overflow:auto;">Loading…</div>
        </section>
      </div>
      <div style="font-size:11px;opacity:.55;border-top:1px solid var(--border);padding-top:7px;margin-top:8px;">Cascade: your rules → bulk-mail headers (no AI cost) → local AI only for the rest. Filtered mail sits in “<span id="mg-folder-foot">Pi Filtered</span>” in each mailbox — nothing is gone until <i>you</i> empty it.</div>
    </div>`;
  document.body.appendChild(modal);
  _el('mg-close').addEventListener('click', closePanel);
  modal.addEventListener('mousedown', (e) => { if (e.target === modal) closePanel(); });
  _el('mg-save').addEventListener('click', _saveConfig);
  _el('mg-enabled').addEventListener('change', _saveConfig);
  _el('mg-sweep').addEventListener('click', _sweepNow);
  _el('mg-rule-add').addEventListener('click', _addRule);
  _el('mg-rule-pattern').addEventListener('keydown', (e) => { if (e.key === 'Enter') _addRule(); });
  _el('mg-refresh').addEventListener('click', () => { _loadStatus(); _loadDecisions(); });
  document.addEventListener('keydown', _onEsc);
  _loadStatus();
  _loadRules();
  _loadDecisions();
}

function _onEsc(e) { if (e.key === 'Escape' && _open) closePanel(); }

async function _loadStatus() {
  let st;
  try { st = await (await _api('/api/mailguard/status')).json(); }
  catch (e) { const b = _el('mg-stats'); if (b) b.innerHTML = '<span style="opacity:.55;">Couldn&#39;t load — hit ↻ to retry.</span>'; return; }
  if (!_el('mg-enabled')) return;
  _el('mg-enabled').checked = !!st.enabled;
  _el('mg-interval').value = st.interval_min || 15;
  _el('mg-folder').value = st.filtered_folder || 'Pi Filtered';
  _el('mg-drafts').checked = !!st.draft_replies;
  _el('mg-harddelete').checked = !!st.hard_delete;
  const foot = _el('mg-folder-foot'); if (foot) foot.textContent = st.filtered_folder || 'Pi Filtered';
  const state = _el('mg-state');
  if (state) {
    state.textContent = st.running ? '· sweeping…'
      : st.enabled ? `· on, every ${st.interval_min}m` : '· off';
  }
  const accts = _el('mg-accounts');
  if (accts) accts.textContent = st.accounts && st.accounts.length
    ? `${st.accounts.length} account${st.accounts.length > 1 ? 's' : ''}: ${st.accounts.map(a => a.email).join(', ')}`
    : 'no email accounts connected yet — add one in Settings → Connectors → Email';
  const s = st.stats_24h || {};
  const bv = s.by_verdict || {};
  const box = _el('mg-stats');
  if (box) {
    box.innerHTML = `
      <span class="admin-btn-sm" style="cursor:default;">🔴 urgent ${bv.urgent || 0}</span>
      <span class="admin-btn-sm" style="cursor:default;">🟡 important ${bv.important || 0}</span>
      <span class="admin-btn-sm" style="cursor:default;">⚪ fyi ${bv.fyi || 0}</span>
      <span class="admin-btn-sm" style="cursor:default;">🛍️ marketing ${(bv.marketing || 0) + (bv.noise || 0)}</span>
      <span class="admin-btn-sm" style="cursor:default;">📁 filed ${s.filed || 0}</span>
      <span style="opacity:.5;align-self:center;">all-time triaged: ${s.all_time_total || 0}${st.last_sweep_ts ? ' · last sweep ' + new Date(st.last_sweep_ts * 1000).toLocaleTimeString() : ''}</span>`;
  }
  if (st.running && !_poll) {
    _poll = setInterval(() => { if (_open) _loadStatus(); else _stopPoll(); }, 4000);
  } else if (!st.running) { _stopPoll(); }
}

function _stopPoll() { if (_poll) { clearInterval(_poll); _poll = null; } }

async function _saveConfig() {
  const body = {
    mailguard_enabled: _el('mg-enabled').checked,
    mailguard_interval_min: parseInt(_el('mg-interval').value, 10) || 15,
    mailguard_filtered_folder: (_el('mg-folder').value || 'Pi Filtered').trim(),
    mailguard_draft_replies: _el('mg-drafts').checked,
    mailguard_hard_delete: _el('mg-harddelete').checked,
  };
  const msg = _el('mg-msg');
  try {
    const r = await _api('/api/auth/settings', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    if (msg) msg.textContent = r.ok ? '✅ saved' : '✗ save failed (admin?)';
  } catch (e) { if (msg) msg.textContent = '✗ save failed'; }
  setTimeout(_loadStatus, 600);
}

async function _sweepNow() {
  const btn = _el('mg-sweep');
  if (btn) { btn.disabled = true; btn.textContent = 'Sweeping…'; }
  try {
    const r = await _api('/api/mailguard/sweep', { method: 'POST' });
    const d = await r.json().catch(() => ({}));
    const msg = _el('mg-msg');
    if (msg) {
      if (d.busy) msg.textContent = 'already sweeping…';
      else if (d.note) msg.textContent = d.note;
      else if (d.error) msg.textContent = '✗ ' + d.error;
      else if (d.totals) msg.textContent = `✅ ${d.totals.new} new · ${d.totals.filed} filed · ${d.totals.urgent} urgent · ${d.totals.drafts} drafts`;
    }
  } catch (e) { const m = _el('mg-msg'); if (m) m.textContent = '✗ sweep failed — is the server up?'; }
  if (btn) { btn.disabled = false; btn.textContent = 'Sweep now ▶'; }
  _loadStatus();
  _loadDecisions();
}

async function _loadRules() {
  let d;
  try { d = await (await _api('/api/mailguard/rules')).json(); }
  catch (e) { const b = _el('mg-rules'); if (b) b.innerHTML = '<span style="opacity:.55;">Couldn&#39;t load rules — hit ↻ to retry.</span>'; return; }
  const box = _el('mg-rules');
  if (!box) return;
  const rules = d.rules || [];
  if (!rules.length) { box.innerHTML = '<div style="opacity:.55;">No rules yet — add a VIP sender or a filter pattern above.</div>'; return; }
  box.innerHTML = '';
  rules.forEach((r) => {
    const row = document.createElement('div');
    row.style.cssText = 'display:flex;align-items:center;gap:8px;';
    row.innerHTML = `
      <span style="font-size:11px;border:1px solid var(--border);border-radius:5px;padding:1px 7px;${r.kind === 'include' ? 'color:#42E2B8;' : 'opacity:.7;'}">${r.kind === 'include' ? '✓ keep' : '⛔ filter'}</span>
      <span style="opacity:.6;">${_esc(r.field)} ~</span>
      <span style="font-weight:600;flex:1;overflow:hidden;text-overflow:ellipsis;">${_esc(r.pattern)}</span>
      ${r.note ? `<span style="font-size:10px;opacity:.45;">${_esc(r.note)}</span>` : ''}
      <button class="admin-btn-sm" data-id="${r.id}" style="opacity:.55;">✕</button>`;
    row.querySelector('button').addEventListener('click', async (e) => {
      const msg = _el('mg-msg');
      try {
        const dr = await _api('/api/mailguard/rules/' + e.currentTarget.dataset.id, { method: 'DELETE' });
        if (!dr.ok && msg) msg.textContent = '✗ could not delete rule (admin?)';
      } catch (err) { if (msg) msg.textContent = '✗ could not delete rule — connection error'; }
      _loadRules();
    });
    box.appendChild(row);
  });
}

async function _addRule() {
  const pattern = (_el('mg-rule-pattern').value || '').trim();
  if (!pattern) return;
  const msg = _el('mg-msg');
  try {
    const r = await _api('/api/mailguard/rules', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ kind: _el('mg-rule-kind').value, field: _el('mg-rule-field').value, pattern }),
    });
    if (r.ok) { _el('mg-rule-pattern').value = ''; if (msg) msg.textContent = ''; }
    else {
      const d = await r.json().catch(() => ({}));
      if (msg) msg.textContent = '✗ rule not added: ' + (d.detail || 'admin required?');
    }
  } catch (e) { if (msg) msg.textContent = '✗ rule not added — connection error'; }
  _loadRules();
}

async function _loadDecisions() {
  let d;
  try { d = await (await _api('/api/mailguard/decisions?limit=60')).json(); }
  catch (e) { const b = _el('mg-decisions'); if (b) b.innerHTML = '<span style="opacity:.55;">Couldn&#39;t load — hit ↻ to retry.</span>'; return; }
  const box = _el('mg-decisions');
  if (!box) return;
  const list = d.decisions || [];
  if (!list.length) { box.innerHTML = '<div style="opacity:.55;">Nothing triaged yet — connect an email account and hit Sweep now ▶.</div>'; return; }
  box.innerHTML = '';
  list.forEach((dec) => {
    const row = document.createElement('div');
    row.style.cssText = 'border:1px solid var(--border);border-radius:8px;padding:6px 9px;';
    const restorable = dec.action === 'filed' || dec.action === 'trashed';
    row.innerHTML = `
      <div style="display:flex;align-items:center;gap:7px;">
        <span title="${_esc(dec.verdict)}">${VERDICT_ICON[dec.verdict] || '·'}</span>
        <span style="font-weight:600;flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">${_esc(dec.subject || '(no subject)')}</span>
        <span style="font-size:10px;opacity:.5;">${_esc((dec.account_email || '').split('@')[0])}</span>
        ${restorable ? `<button class="admin-btn-sm" data-act="restore" style="font-size:10.5px;">↩ restore</button>` : ''}
        ${dec.draft ? `<button class="admin-btn-sm" data-act="draft" style="font-size:10.5px;">✍ draft</button>` : ''}
      </div>
      <div style="font-size:10.5px;opacity:.6;margin-top:2px;">${_esc(dec.sender)} · ${_esc(dec.stage)}: ${_esc(dec.reason)} · ${_esc(dec.action)}</div>
      <div class="mg-draft" style="display:none;white-space:pre-wrap;font-size:11.5px;border-top:1px dashed var(--border);margin-top:5px;padding-top:5px;"></div>`;
    const rbtn = row.querySelector('[data-act="restore"]');
    if (rbtn) rbtn.addEventListener('click', async () => {
      rbtn.disabled = true; rbtn.textContent = '…';
      try {
        const r = await _api(`/api/mailguard/decisions/${dec.id}/restore`, { method: 'POST' });
        rbtn.textContent = r.ok ? '✓ back in inbox' : '✗ failed';
        if (r.ok) _loadRules(); // sender was learned as VIP
      } catch (err) { rbtn.disabled = false; rbtn.textContent = '↩ retry'; }
    });
    const dbtn = row.querySelector('[data-act="draft"]');
    if (dbtn) dbtn.addEventListener('click', () => {
      const dv = row.querySelector('.mg-draft');
      dv.textContent = dec.draft;
      dv.style.display = dv.style.display === 'none' ? 'block' : 'none';
    });
    box.appendChild(row);
  });
}

function closePanel() {
  if (!_open) return;
  _open = false;
  _stopPoll();
  document.removeEventListener('keydown', _onEsc);
  const m = _el('mailguard-modal');
  if (m) m.remove();
}

function togglePanel() { _open ? closePanel() : openPanel(); }
function isPanelOpen() { return _open; }

const mailGuardModule = { openPanel, closePanel, togglePanel, isPanelOpen };
export default mailGuardModule;
window.mailGuardModule = mailGuardModule;
