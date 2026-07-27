// static/js/agentsHub.js — Agents: chat-based agent management, end to end.
// Type what you want ("every morning at 8 summarize the top AI news") — a local
// LLM parses it and drives Pi's scheduler engine: create / list / run / pause /
// resume / delete. Agent cards show schedule, status, last run. Backed by
// /api/agents/* (routes/agents_hub_routes.py) over the existing /api/tasks.

let _open = false, _busy = false;

const _el = (id) => document.getElementById(id);
const _esc = (s) => (s || '').replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
const _api = (p, o) => fetch(p, Object.assign({ credentials: 'same-origin' }, o || {}));

const _CHIPS = [
  'Every morning at 8 summarize the top AI news',
  'Every Monday at 9:00 list my open TODOs from my notes',
  'Create an on-demand agent that checks if my Pi services are healthy',
  'List my agents',
];

function openPanel() {
  if (_open) return;
  _open = true;
  const modal = document.createElement('div');
  modal.className = 'modal';
  modal.id = 'agentshub-modal';
  modal.innerHTML = `
    <div class="modal-content" style="max-width:760px;width:95vw;max-height:90vh;display:flex;flex-direction:column;">
      <div style="display:flex;align-items:center;gap:10px;margin-bottom:4px;">
        <div style="font-weight:600;font-size:15px;flex:1;">Agents</div>
        <span style="font-size:11px;opacity:.55;">chat-managed · runs on your local models</span>
        <button class="modal-close" id="agentshub-close" aria-label="Close">×</button>
      </div>
      <div style="font-size:12px;opacity:.7;margin-bottom:8px;">Tell me what to automate — I'll create, schedule, run, pause, or delete agents for you. They execute with Pi's tools and show up under Tasks too.</div>
      <div id="agentshub-chips" style="display:flex;flex-wrap:wrap;gap:6px;margin-bottom:8px;"></div>
      <div id="agentshub-chat" style="display:flex;flex-direction:column;gap:8px;max-height:24vh;overflow:auto;margin-bottom:8px;"></div>
      <div style="display:flex;gap:8px;margin-bottom:10px;">
        <input id="agentshub-input" type="text" autocomplete="off" spellcheck="false"
          placeholder="e.g. every morning at 8 summarize the top AI news…"
          style="flex:1;background:var(--bg2,#1b1f27);color:var(--fg);border:1px solid var(--border,#333);border-radius:9px;padding:9px 11px;font-size:13px;outline:none;">
        <button class="admin-btn-sm" id="agentshub-send" style="font-weight:600;">Send ▶</button>
      </div>
      <div style="display:flex;align-items:center;gap:8px;margin-bottom:6px;">
        <div style="font-size:12px;font-weight:600;">Your agents</div>
        <span id="agentshub-count" style="font-size:11px;opacity:.5;"></span>
        <span style="flex:1;"></span>
        <button class="admin-btn-sm" id="agentshub-refresh" title="Refresh">↻</button>
      </div>
      <div id="agentshub-list" style="overflow:auto;display:flex;flex-direction:column;gap:8px;flex:1;">
        <div style="opacity:.6;padding:14px;text-align:center;">Loading…</div>
      </div>
      <details id="agentshub-templates" style="margin:10px 0 0;background:transparent;border:none;">
        <summary style="cursor:pointer;font-size:12.5px;font-weight:600;color:var(--fg);background:var(--panel2,#262b34);border:1px solid var(--border,#333);border-radius:8px;padding:8px 11px;">✨ Prebuilt agents <span id="tpl-state" style="font-weight:400;opacity:.6;">· 40 ready-made</span></summary>
        <div style="font-size:11.5px;opacity:.7;margin:6px 0;">One-click agents for the most common automations. Everything installs <b>paused</b> — run any with ▶, or resume its schedule when you're ready. Topic-driven ones read their input from a note called “&lt;Agent name&gt; — Input”.</div>
        <div id="tpl-cats" style="display:flex;flex-wrap:wrap;gap:5px;margin-bottom:8px;"></div>
        <div id="tpl-grid" style="display:grid;grid-template-columns:repeat(auto-fill,minmax(215px,1fr));gap:8px;max-height:34vh;overflow:auto;">
          <div style="opacity:.6;padding:10px;">Loading templates…</div>
        </div>
        <div style="display:flex;align-items:center;gap:8px;margin-top:8px;">
          <span id="tpl-msg" style="font-size:11px;opacity:.7;flex:1;"></span>
          <button class="admin-btn-sm" id="tpl-install-all" title="Install every template (all paused)">Install all</button>
        </div>
      </details>
      <details id="agentshub-remote" style="margin:8px 0 0;background:transparent;border:none;">
        <summary style="cursor:pointer;font-size:12.5px;font-weight:600;color:var(--fg);background:var(--panel2,#262b34);border:1px solid var(--border,#333);border-radius:8px;padding:8px 11px;">📱 Remote — talk to Pi from anywhere (Telegram) <span id="tg-state" style="font-weight:400;opacity:.6;"></span></summary>
        <div style="font-size:11.5px;opacity:.7;margin:6px 0;">Create a bot with <b>@BotFather</b> in Telegram, paste its token here, then message your bot — it replies with your chat id; add that id and you're live. Read-only tools; off by default.</div>
        <div style="display:flex;gap:6px;flex-wrap:wrap;align-items:center;">
          <input id="tg-token" type="password" placeholder="bot token (paste from @BotFather)" autocomplete="off"
            style="flex:1;min-width:180px;background:var(--bg2,#1b1f27);color:var(--fg);border:1px solid var(--border,#333);border-radius:7px;padding:6px 9px;font-size:12px;">
          <button class="admin-btn-sm" id="tg-test">Test</button>
          <input id="tg-allow" type="text" placeholder="allowed chat ids (comma)" autocomplete="off"
            style="width:170px;background:var(--bg2,#1b1f27);color:var(--fg);border:1px solid var(--border,#333);border-radius:7px;padding:6px 9px;font-size:12px;">
          <label style="font-size:12px;display:flex;align-items:center;gap:4px;cursor:pointer;"><input type="checkbox" id="tg-enabled"> on</label>
          <button class="admin-btn-sm" id="tg-save" style="font-weight:600;">Save</button>
        </div>
        <div id="tg-msg" style="font-size:11px;opacity:.7;margin-top:5px;"></div>
      </details>
    </div>`;
  document.body.appendChild(modal);
  _el('agentshub-close').addEventListener('click', closePanel);
  modal.addEventListener('click', (e) => { if (e.target === modal) closePanel(); });
  _el('agentshub-send').addEventListener('click', _send);
  _el('agentshub-refresh').addEventListener('click', _loadAgents);
  _el('agentshub-input').addEventListener('keydown', (e) => { if (e.key === 'Enter') { e.preventDefault(); _send(); } });
  const chips = _el('agentshub-chips');
  _CHIPS.forEach((c) => {
    const b = document.createElement('button');
    b.className = 'admin-btn-sm';
    b.style.cssText = 'font-size:11px;opacity:.85;';
    b.textContent = c;
    b.addEventListener('click', () => { _el('agentshub-input').value = c; _send(); });
    chips.appendChild(b);
  });
  _say('hi', "What should I automate for you? Describe it in plain words — schedule optional (no schedule = on-demand).");
  document.addEventListener('keydown', _onEsc);
  _loadAgents();
  _tplInit();
  _tgInit();
}

function _onEsc(e) { if (e.key === 'Escape' && _open) closePanel(); }

// ── Prebuilt templates gallery ──
let _tplAll = [], _tplCat = 'All';

async function _tplInit() {
  try {
    const d = await (await _api('/api/agents/templates')).json();
    _tplAll = d.templates || [];
  } catch (e) { _tplAll = []; }
  const cats = ['All'].concat([...new Set(_tplAll.map(t => t.category))]);
  const catBox = _el('tpl-cats');
  if (catBox) {
    catBox.innerHTML = '';
    cats.forEach((c) => {
      const b = document.createElement('button');
      b.className = 'admin-btn-sm';
      b.style.cssText = 'font-size:11px;' + (c === _tplCat ? 'font-weight:700;border-color:var(--accent,var(--red,#FF5758));' : 'opacity:.75;');
      b.textContent = c;
      b.addEventListener('click', () => { _tplCat = c; _tplInit(); });
      catBox.appendChild(b);
    });
  }
  const state = _el('tpl-state');
  if (state) {
    const inst = _tplAll.filter(t => t.installed).length;
    state.textContent = `· ${_tplAll.length} ready-made${inst ? ` · ${inst} installed` : ''}`;
  }
  _tplRender();
  const all = _el('tpl-install-all');
  if (all && !all.dataset.bound) {
    all.dataset.bound = '1';
    all.addEventListener('click', () => {
      const missing = _tplAll.filter(t => !t.installed).map(t => t.id);
      if (!missing.length) { _el('tpl-msg').textContent = 'Everything is already installed.'; return; }
      if (!confirm(`Install ${missing.length} prebuilt agents? All arrive paused — nothing runs until you say so.`)) return;
      _tplInstall(missing);
    });
  }
}

function _tplSched(t) {
  if (t.on_demand) return 'on demand ▶';
  const s = t.schedule || {};
  const day = ['Mon','Tue','Wed','Thu','Fri','Sat','Sun'][s.day] || '';
  if (s.schedule === 'daily') return 'daily ' + (s.time || '');
  if (s.schedule === 'weekly') return 'weekly ' + day + ' ' + (s.time || '');
  if (s.schedule === 'monthly') return 'monthly ' + (s.time || '');
  return 'scheduled';
}

function _tplRender() {
  const grid = _el('tpl-grid');
  if (!grid) return;
  const items = _tplAll.filter(t => _tplCat === 'All' || t.category === _tplCat);
  if (!items.length) { grid.innerHTML = '<div style="opacity:.6;padding:10px;">No templates.</div>'; return; }
  grid.innerHTML = '';
  items.forEach((t) => {
    const card = document.createElement('div');
    card.style.cssText = 'border:1px solid var(--border,#333);border-radius:9px;padding:8px 10px;display:flex;flex-direction:column;gap:4px;';
    const needs = (t.needs || []).includes('email') ? '<span style="font-size:9.5px;border:1px solid var(--border,#333);border-radius:5px;padding:1px 5px;opacity:.6;">needs email</span>' : '';
    card.innerHTML = `
      <div style="display:flex;align-items:center;gap:6px;">
        <span style="font-size:14px;">${t.emoji}</span>
        <span style="font-weight:600;font-size:12px;flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">${_esc(t.name)}</span>
      </div>
      <div style="font-size:11px;opacity:.7;line-height:1.4;min-height:28px;">${_esc(t.desc)}</div>
      <div style="display:flex;align-items:center;gap:6px;">
        <span style="font-size:10px;opacity:.55;flex:1;">${_esc(_tplSched(t))}</span>${needs}
        <button class="admin-btn-sm tpl-install" style="font-size:11px;${t.installed ? 'opacity:.5;' : 'font-weight:600;'}" ${t.installed ? 'disabled' : ''}>${t.installed ? '✓ Installed' : '+ Install'}</button>
      </div>`;
    const btn = card.querySelector('.tpl-install');
    if (btn && !t.installed) btn.addEventListener('click', () => _tplInstall([t.id], btn));
    grid.appendChild(card);
  });
}

async function _tplInstall(ids, btn) {
  const msg = _el('tpl-msg');
  if (btn) { btn.disabled = true; btn.textContent = '…'; }
  if (msg) msg.textContent = `Installing ${ids.length}…`;
  try {
    const r = await _api('/api/agents/templates/install', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(ids.length === 1 ? { id: ids[0] } : { ids }),
    });
    const d = await r.json().catch(() => ({}));
    if (!r.ok) { if (msg) msg.textContent = '✗ ' + (d.detail || 'install failed (admin required?)'); }
    else {
      const n = (d.installed || []).length, sk = (d.skipped || []).length, er = (d.errors || []).length;
      if (msg) msg.textContent = `✅ installed ${n}${sk ? `, ${sk} already there` : ''}${er ? `, ${er} failed` : ''} — all paused; press ▶ on a card to try one.`;
    }
  } catch (e) { if (msg) msg.textContent = '✗ connection error'; }
  _tplInit();
  _loadAgents();
}

// ── Remote (Telegram) config ──
async function _tgInit() {
  const msg = _el('tg-msg'), state = _el('tg-state');
  try {
    const st = await (await _api('/api/gateway/telegram/status')).json();
    if (state) state.textContent = st.running ? '· live as @' + (st.bot || '?') : (st.enabled ? '· starting…' : '· off');
    const en = _el('tg-enabled'); if (en) en.checked = !!st.enabled;
    const al = _el('tg-allow'); if (al) al.value = (st.allowed_chat_ids || []).join(',');
    if (st.token_set && _el('tg-token')) _el('tg-token').placeholder = 'token saved — paste to replace';
    if (st.last_error && msg) msg.textContent = '⚠ ' + st.last_error;
  } catch (e) {}
  const t = _el('tg-test');
  if (t && !t.dataset.bound) { t.dataset.bound = '1'; t.addEventListener('click', async () => {
    msg.textContent = 'testing…';
    try {
      const r = await _api('/api/gateway/telegram/test', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ token: _el('tg-token').value.trim() }) });
      const d = await r.json().catch(() => ({}));
      msg.textContent = r.ok ? '✅ token valid — bot @' + d.bot : '✗ ' + (d.detail || 'invalid token');
    } catch (e) { msg.textContent = '✗ test failed'; }
  }); }
  const s = _el('tg-save');
  if (s && !s.dataset.bound) { s.dataset.bound = '1'; s.addEventListener('click', async () => {
    const body = { enabled: _el('tg-enabled').checked,
                   allowed_chat_ids: _el('tg-allow').value.split(',').map(x => x.trim()).filter(Boolean) };
    const tok = _el('tg-token').value.trim();
    if (tok) body.token = tok;
    try {
      const r = await _api('/api/gateway/telegram/config', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
      msg.textContent = r.ok ? '✅ saved — message your bot from your phone' : '✗ save failed';
      if (r.ok) { _el('tg-token').value = ''; setTimeout(_tgInit, 1500); }
    } catch (e) { msg.textContent = '✗ save failed'; }
  }); }
}

function _say(who, text) {
  const chat = _el('agentshub-chat');
  if (!chat) return;
  const d = document.createElement('div');
  d.style.cssText = 'font-size:12.5px;line-height:1.5;' + (who === 'you'
    ? 'background:var(--panel2,#262b34);border:1px solid var(--border,#333);border-radius:8px;padding:6px 10px;align-self:flex-end;max-width:88%;'
    : 'opacity:.9;align-self:flex-start;max-width:92%;');
  d.textContent = (who === 'you' ? '' : '🤖 ') + text;
  chat.appendChild(d);
  chat.scrollTop = chat.scrollHeight;
}

async function _send() {
  if (_busy) return;
  const inp = _el('agentshub-input');
  const text = (inp.value || '').trim();
  if (!text) return;
  inp.value = '';
  _say('you', text);
  _busy = true;
  const btn = _el('agentshub-send');
  if (btn) { btn.disabled = true; btn.textContent = '…'; }
  try {
    const r = await _api('/api/agents/command', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text }),
    });
    const d = await r.json().catch(() => ({}));
    if (!r.ok) { _say('pi', d.detail || 'That failed — try rephrasing.'); }
    else { _say('pi', d.reply || 'Done.'); _renderAgents(d.agents || []); }
  } catch (e) { _say('pi', 'Connection error.'); }
  _busy = false;
  if (btn) { btn.disabled = false; btn.textContent = 'Send ▶'; }
}

async function _loadAgents() {
  let d;
  try { d = await (await _api('/api/agents')).json(); }
  catch (e) { const l = _el('agentshub-list'); if (l) l.innerHTML = '<div style="opacity:.55;font-size:12.5px;padding:12px;">Couldn&#39;t load agents — hit ↻ to retry.</div>'; return; }
  _renderAgents((d && (d.tasks || d.agents)) || (Array.isArray(d) ? d : []));
}

function _schedLine(t) {
  if (t.trigger_type === 'webhook') return 'on demand';
  if (t.trigger_type === 'event') return 'on event: ' + (t.trigger_event || '?');
  const s = t.schedule || '';
  if (s === 'cron') return 'cron ' + (t.cron_expression || '');
  if (s === 'daily') return 'daily at ' + (t.scheduled_time || '?');
  if (s === 'weekly') return 'weekly (' + ['Mon','Tue','Wed','Thu','Fri','Sat','Sun'][t.scheduled_day || 0] + ') at ' + (t.scheduled_time || '?');
  if (s === 'monthly') return 'monthly (day ' + (t.scheduled_day || 1) + ') at ' + (t.scheduled_time || '?');
  if (s === 'once') return 'once';
  return s || '—';
}

// Relative time, e.g. "in 3h" / "2h ago" / "just now" — computed against the
// browser clock so the schedule reads at a glance.
function _relTime(iso) {
  if (!iso) return '';
  const t = Date.parse(iso);
  if (isNaN(t)) return '';
  const future = (t - Date.now()) > 0;
  const diff = Math.abs(t - Date.now());
  const m = Math.round(diff / 60000), h = Math.round(diff / 3600000), d = Math.round(diff / 86400000);
  let s;
  if (m < 1) return 'just now';
  else if (m < 60) s = m + 'm';
  else if (h < 24) s = h + 'h';
  else s = d + 'd';
  return future ? 'in ' + s : s + ' ago';
}

// Absolute timestamp like "Jun 18, 08:00".
function _fmtTs(iso) {
  const t = new Date(iso);
  if (isNaN(t.getTime())) return String(iso || '').slice(0, 16).replace('T', ' ');
  try { return t.toLocaleString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' }); }
  catch (e) { return String(iso).slice(0, 16).replace('T', ' '); }
}

function _chip(inner) {
  return `<span style="font-size:10.5px;padding:2px 7px;border-radius:6px;background:var(--panel2,#262b34);border:1px solid var(--border,#333);white-space:nowrap;">${inner}</span>`;
}

// The full "everything you'd want to see" schedule strip: cadence, next run
// (absolute + relative), last run, total runs, the model it uses, and whether
// it notifies. Always visible on the card.
function _schedChips(t, paused) {
  const chips = [];
  chips.push(_chip((paused ? '⏸ ' : (t.trigger_type === 'schedule' ? '📅 ' : '⚡ ')) + _esc(_schedLine(t))));
  if (t.next_run && !paused && t.trigger_type === 'schedule') {
    chips.push(_chip('⏱ next ' + _esc(_fmtTs(t.next_run)) + ' <span style="opacity:.6;">· ' + _esc(_relTime(t.next_run)) + '</span>'));
  }
  chips.push(t.last_run
    ? _chip('✓ last ' + _esc(_relTime(t.last_run)) + ' <span style="opacity:.6;">· ' + _esc(_fmtTs(t.last_run)) + '</span>')
    : _chip('<span style="opacity:.7;">never run yet</span>'));
  if (typeof t.run_count === 'number') chips.push(_chip('🔁 ' + t.run_count + (t.run_count === 1 ? ' run' : ' runs')));
  if (t.model) chips.push(_chip('🧠 ' + _esc(t.model)));
  if (t.notifications_enabled === false) chips.push(_chip('🔕 silent'));
  return `<div style="margin-top:7px;display:flex;flex-wrap:wrap;gap:5px;">${chips.join('')}</div>`;
}

// Agents are ScheduledTasks with only name + prompt — no description field. The
// prompt is the raw execution directive (full of "You are the X agent. Do the
// following NOW: run the bash tool with EXACTLY this command…" boilerplate), so
// derive a clean one-line summary for the card and keep the full prompt behind a
// disclosure.
function _agentSummary(t) {
  let s = (t.prompt || t.action || '').replace(/\s+/g, ' ').trim();
  if (!s) return '';
  // Strip the engineered preambles/boilerplate so the line reads like intent.
  s = s
    .replace(/^you are (the |a |an )?[^.]*?\bagent\b[.,:\s-]*/i, '')
    .replace(/\bdo the following now[:.\s-]*/i, '')
    .replace(/\brun the (bash|shell|python) tool with exactly this command[^:]*:\s*/i, '')
    .replace(/\binput:\s*first use [a-z_]+ to read the note titled[^.]*\.\s*/i, '')
    .replace(/\b(report-only|never delete|never send|do not delete|do not send)[^.]*\.\s*$/i, '')
    .trim();
  // First sentence, else clamp.
  const dot = s.indexOf('. ');
  if (dot > 25 && dot < 110) s = s.slice(0, dot + 1);
  if (s.length > 110) s = s.slice(0, 108).replace(/\s\S*$/, '') + '…';
  return s;
}

// The cake/tofu glyph is OS font-fallback for an uncommon emoji baked into the
// agent NAME by templates (name = "{emoji} {name}"). Strip a leading emoji so
// the title is clean; we render our own consistent glyph + state dot instead.
function _cleanName(t) {
  const n = (t.name || '(unnamed)').trim();
  try { return n.replace(/^(?:[\p{Extended_Pictographic}←-➿️‍]+\s*)+/u, '').trim() || n; }
  catch (e) { return n.replace(/^[^\w(]+\s*/, '').trim() || n; }
}

function _isPaused(t) {
  return t.enabled === false || t.status === 'paused' || t.status === 'inactive' || t.paused === true;
}

function _renderAgents(tasks) {
  const list = _el('agentshub-list');
  const count = _el('agentshub-count');
  if (!list) return;
  if (count) count.textContent = tasks.length ? `${tasks.length}` : '';
  if (!tasks.length) {
    list.innerHTML = '<div style="opacity:.55;font-size:12.5px;padding:12px;">No agents yet — describe one above to create it.</div>';
    return;
  }
  list.innerHTML = '';
  tasks.forEach((t) => {
    const paused = _isPaused(t);
    const onDemand = t.trigger_type === 'webhook' || t.schedule === 'once' || !t.schedule;
    // State dot: muted=paused, blue=on-demand (no schedule), green=scheduled & active.
    const dotColor = paused ? 'color-mix(in srgb,var(--fg) 30%,transparent)'
      : (onDemand ? 'var(--blue,#5BA8FF)' : '#2ecc71');
    const dotTitle = paused ? 'paused' : (onDemand ? 'on demand' : 'scheduled');
    const summary = _agentSummary(t);
    const card = document.createElement('div');
    card.style.cssText = 'border:1px solid var(--border,#333);border-radius:10px;padding:10px 12px;';
    card.innerHTML = `
      <div style="display:flex;align-items:center;gap:7px;">
        <span title="${dotTitle}" style="width:8px;height:8px;border-radius:50%;background:${dotColor};flex-shrink:0;"></span>
        <span style="opacity:.5;flex-shrink:0;">🤖</span>
        <span style="font-weight:600;font-size:13px;flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">${_esc(_cleanName(t))}</span>
        <button class="admin-btn-sm" data-act="run" title="Run now">▶</button>
        <button class="admin-btn-sm" data-act="${paused ? 'resume' : 'pause'}" title="${paused ? 'Resume' : 'Pause'}">${paused ? '▶︎' : '⏸'}</button>
        <button class="admin-btn-sm" data-act="delete" title="Delete" style="opacity:.55;">🗑</button>
      </div>
      ${summary ? `<div style="font-size:12px;opacity:.8;margin-top:5px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">${_esc(summary)}</div>` : ''}
      ${_schedChips(t, paused)}
      <div style="display:flex;gap:12px;margin-top:6px;">
        <a href="#" data-act="lastrun" style="font-size:10.5px;opacity:.55;">last result ▾</a>
        <a href="#" data-act="prompt" style="font-size:10.5px;opacity:.55;">view prompt ▾</a>
      </div>
      <div class="agentshub-lastrun" style="display:none;font-size:11.5px;white-space:pre-wrap;border-top:1px dashed var(--border,#333);margin-top:6px;padding-top:6px;max-height:160px;overflow:auto;"></div>
      <div class="agentshub-prompt" style="display:none;font-size:11px;white-space:pre-wrap;border-top:1px dashed var(--border,#333);margin-top:6px;padding-top:6px;max-height:200px;overflow:auto;opacity:.85;">${_esc(t.prompt || t.action || '(no prompt)')}</div>`;
    card.querySelectorAll('[data-act]').forEach((b) =>
      b.addEventListener('click', (e) => { e.preventDefault(); _cardAction(b.getAttribute('data-act'), t, card); }));
    list.appendChild(card);
  });
}

async function _cardAction(act, t, card) {
  if (act === 'prompt') {
    const box = card.querySelector('.agentshub-prompt');
    if (box) box.style.display = box.style.display === 'none' ? 'block' : 'none';
    return;
  }
  if (act === 'lastrun') {
    const box = card.querySelector('.agentshub-lastrun');
    if (box.style.display !== 'none') { box.style.display = 'none'; return; }
    box.style.display = 'block';
    box.textContent = 'Loading…';
    try {
      const d = await (await _api('/api/agents/' + t.id + '/last-run')).json();
      const run = d.run;
      box.textContent = run ? `[${run.status || '?'} · ${String(run.started_at || '').slice(0, 16)}]\n` + String(run.result || run.error || '(no output)').slice(0, 1500)
                            : 'No runs yet — hit ▶ to run it now.';
    } catch (e) { box.textContent = 'Could not load the last run.'; }
    return;
  }
  if (act === 'delete' && !confirm(`Delete agent “${t.name}”?`)) return;
  try {
    const path = act === 'delete' ? `/api/tasks/${t.id}` : `/api/tasks/${t.id}/${act}`;
    const r = await _api(path, { method: act === 'delete' ? 'DELETE' : 'POST' });
    if (!r.ok) { alert('Action failed (admin required?)'); return; }
    if (act === 'run') {
      _say('pi', `Running “${t.name}” — check “last result” in a moment.`);
      // The run is async — refresh again shortly so 'last: …' reflects THIS
      // run instead of the previous one.
      setTimeout(_loadAgents, 4000);
    }
  } catch (e) { alert('Action failed.'); }
  _loadAgents();
}

function closePanel() { if (!_open) return; _open = false; document.removeEventListener('keydown', _onEsc); const m = _el('agentshub-modal'); if (m) m.remove(); }
function togglePanel() { _open ? closePanel() : openPanel(); }
function isPanelOpen() { return _open; }

const agentsHubModule = { openPanel, closePanel, togglePanel, isPanelOpen };
export default agentsHubModule;
