// static/js/code.js — "Code" Board: tmux-style grid of up to 16 persistent
// coding sessions ("windows"), each pinned to a project folder with its own
// chat history (server-side: /api/code/sessions). Multiple sessions can stream
// CONCURRENTLY — switching windows or closing the panel does NOT stop a run;
// only the Stop button does. Each session injects the repo map + AGENTS.md
// (project-aware coding) via /api/code/chat.

import { openWorkspaceBrowser } from './workspace.js';

let _open = false;
let _view = 'board';        // 'board' | 'session'
let _currentId = null;      // session displayed in 'session' view
let _pickFor = null;        // 'new' | sessionId — what the folder picker is for
// Claude-style modes. Plan = read-only, iterate until you press Act; Act =
// execute the plan; Review = read-only critique; Research = web + cite; Code =
// normal build. Persisted so it sticks across opens.
const _MODES = [
  { id: 'code', label: 'Code', hint: 'Build / fix — full tools' },
  { id: 'plan', label: 'Plan', hint: 'Read-only — keeps planning until you press Act' },
  { id: 'act', label: 'Act', hint: 'Execute the approved plan above' },
  { id: 'review', label: 'Review', hint: 'Read-only code review' },
  { id: 'research', label: 'Research', hint: 'Deep research the web + cite' },
];
let _mode = (() => { try { return localStorage.getItem('ody-code-mode') || 'code'; } catch (e) { return 'code'; } })();
let _max = 16;

// Runtime per-session state. Survives view switches and panel close, so runs
// keep streaming in the background. id → {meta, history, busy, ctrl, live,
// liveBodyEl, liveToolsEl, ctxLine}
const _S = new Map();

const _el = (id) => document.getElementById(id);
const _esc = (s) => (s || '').replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
const _api = (p, o) => fetch(p, Object.assign({ credentials: 'same-origin' }, o || {}));
const _base = (p) => (p || '').replace(/[\\/]+$/, '').split(/[\\/]/).pop() || '';
const _ago = (ts) => { const s = Math.max(0, Math.floor(Date.now() / 1000) - (ts || 0)); return s < 60 ? 'now' : s < 3600 ? Math.floor(s / 60) + 'm' : s < 86400 ? Math.floor(s / 3600) + 'h' : Math.floor(s / 86400) + 'd'; };

// Folder picked in the workspace browser → create a session or repoint one.
document.addEventListener('workspace-changed', async (e) => {
  if (!_open || !_pickFor) return;
  const path = e.detail && e.detail.path;
  const why = _pickFor; _pickFor = null;
  if (!path) return;
  if (why === 'new') {
    try {
      const r = await _api('/api/code/sessions', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ root: path }) });
      const d = await r.json().catch(() => ({}));
      if (!r.ok) { alert(d.detail || 'Could not create session'); _renderBoard(); return; }
      _S.set(d.id, { meta: d, history: [], busy: false, ctrl: null, live: '', liveBodyEl: null, liveToolsEl: null, ctxLine: '' });
      _openSession(d.id);
    } catch (err) { _renderBoard(); }
  } else if (_S.has(why)) {
    try {
      const pr = await _api('/api/code/sessions/' + why, { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ root: path, name: _base(path) }) });
      if (!pr.ok) { alert('Could not repoint this window.'); return; }
      const s = _S.get(why);
      s.meta.root = path; s.meta.name = _base(path);
      if (_view === 'session' && _currentId === why) _renderSession();
    } catch (err) { alert('Could not repoint this window — is the server up?'); }
  }
});

function openPanel() {
  if (_open) { return; }
  _open = true;
  let modal = _el('code-modal');
  if (!modal) {
    modal = document.createElement('div');
    modal.className = 'modal';
    modal.id = 'code-modal';
    modal.innerHTML = `
      <div class="modal-content" style="max-width:900px;width:96vw;height:90vh;display:flex;flex-direction:column;">
        <div id="code-view" style="display:flex;flex-direction:column;flex:1;min-height:0;"></div>
      </div>`;
    document.body.appendChild(modal);
    modal.addEventListener('click', (e) => { if (e.target === modal) closePanel(); });
  }
  document.addEventListener('keydown', _onEsc);
  modal.style.display = 'flex';
  _view = 'board';
  _renderBoard();
}

// ─────────────────────────── BOARD VIEW ───────────────────────────

async function _renderBoard() {
  _view = 'board';
  _stopJobPoll();   // board view isn't tied to one session's run
  const v = _el('code-view');
  if (!v) return;
  v.innerHTML = `
    <div style="display:flex;align-items:center;gap:10px;margin-bottom:4px;">
      <div style="font-weight:600;font-size:15px;flex:1;">Code Board <span style="font-size:11px;opacity:.55;font-weight:400;">· up to ${_max} coding windows — they keep running while you switch</span></div>
      <button class="modal-close" id="code-close" aria-label="Close">×</button>
    </div>
    <div style="font-size:12px;opacity:.65;margin-bottom:10px;">Click a window to continue where you left off. ▶ = running now (closing this panel does not stop it).</div>
    <div id="code-grid" style="display:grid;grid-template-columns:repeat(auto-fill,minmax(190px,1fr));gap:10px;overflow:auto;padding:2px;flex:1;align-content:start;"></div>`;
  _el('code-close').addEventListener('click', closePanel);

  let data = { sessions: [], max: 16 };
  let loadFailed = false;
  try { data = await (await _api('/api/code/sessions')).json(); } catch (e) { loadFailed = true; }
  _max = data.max || 16;
  const grid = _el('code-grid');
  if (!grid) return;
  grid.innerHTML = '';
  if (loadFailed) {
    const err = document.createElement('div');
    err.style.cssText = 'grid-column:1/-1;opacity:.7;font-size:13px;padding:10px;';
    err.innerHTML = 'Could not load your windows (is the server up?). <a href="#" id="code-retry" style="color:var(--red,#FF5758);">Retry</a>';
    grid.appendChild(err);
    const rt = _el('code-retry');
    if (rt) rt.addEventListener('click', (e) => { e.preventDefault(); _renderBoard(); });
    return;
  }

  (data.sessions || []).forEach((meta) => {
    if (!_S.has(meta.id)) _S.set(meta.id, { meta, history: null, busy: false, ctrl: null, live: '', liveBodyEl: null, liveToolsEl: null, ctxLine: '' });
    else _S.get(meta.id).meta = Object.assign(_S.get(meta.id).meta, meta);
    grid.appendChild(_tile(_S.get(meta.id)));
  });

  // "New window" tile
  if ((data.sessions || []).length < _max) {
    const add = document.createElement('div');
    add.style.cssText = 'border:1px dashed var(--border,#333);border-radius:10px;min-height:110px;display:flex;flex-direction:column;align-items:center;justify-content:center;cursor:pointer;opacity:.7;gap:6px;';
    add.innerHTML = '<div style="font-size:22px;">+</div><div style="font-size:12px;">New window</div>';
    add.addEventListener('click', () => { _pickFor = 'new'; openWorkspaceBrowser(); });
    grid.appendChild(add);
  }
  if (!(data.sessions || []).length) {
    const hint = document.createElement('div');
    hint.style.cssText = 'grid-column:1/-1;opacity:.55;font-size:13px;padding:8px;';
    hint.textContent = 'No coding windows yet — click “New window”, pick a project folder, and start. Open as many as ' + _max + '; they all keep their history.';
    grid.appendChild(hint);
  }
}

function _tile(s) {
  const m = s.meta;
  const t = document.createElement('div');
  t.style.cssText = 'border:1px solid var(--border,#333);border-radius:10px;padding:10px;min-height:110px;display:flex;flex-direction:column;gap:5px;cursor:pointer;position:relative;transition:.12s;';
  t.addEventListener('mouseenter', () => { t.style.borderColor = 'var(--red,#FF5758)'; });
  t.addEventListener('mouseleave', () => { t.style.borderColor = 'var(--border,#333)'; });
  const _isRunning = s.busy || (s.meta && s.meta.running);  // server truth survives reload
  const running = _isRunning ? '<span style="color:#2ecc71;font-size:10px;font-weight:700;">▶ running</span>' : '';
  const snippet = s.busy && s.live ? s.live.slice(-110) : (m.last || '');
  t.innerHTML = `
    <div style="display:flex;align-items:center;gap:6px;">
      <span style="font-weight:600;font-size:13px;flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">⌨ ${_esc(m.name)}</span>
      ${running}
      <button data-del style="background:none;border:none;color:var(--fg);opacity:.4;cursor:pointer;font-size:13px;padding:0 2px;" title="Close window (deletes its history)">✕</button>
    </div>
    <div style="font-size:10.5px;opacity:.5;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;" title="${_esc(m.root)}">${_esc(m.root)}</div>
    <div style="font-size:11.5px;opacity:.75;flex:1;overflow:hidden;line-height:1.4;max-height:46px;">${_esc(snippet)}</div>
    <div style="font-size:10px;opacity:.45;">${m.turns || 0} turns · ${_ago(m.updated_at)}</div>`;
  t.addEventListener('click', (e) => {
    if (e.target.closest('[data-del]')) return;
    _openSession(m.id);
  });
  t.querySelector('[data-del]').addEventListener('click', async (e) => {
    e.stopPropagation();
    if (s.busy || (s.meta && s.meta.running)) { alert('This window is running — stop it first.'); return; }
    if (!confirm(`Close “${m.name}”? Its chat history is deleted.`)) return;
    try {
      const dr = await _api('/api/code/sessions/' + m.id, { method: 'DELETE' });
      if (!dr.ok) { alert('Could not close window — it may reappear on reload.'); return; }
    } catch (err) { alert('Could not close window — is the server up?'); return; }
    _S.delete(m.id);
    _renderBoard();
  });
  return t;
}

// ─────────────────────────── SESSION VIEW ───────────────────────────

async function _openSession(id) {
  let s = _S.get(id);
  if (!s) { _renderBoard(); return; }
  if (s.history === null) {
    try {
      const full = await (await _api('/api/code/sessions/' + id)).json();
      s.history = full.history || [];
      s.meta = Object.assign(s.meta, full);
    } catch (e) { s.history = []; }
  }
  _currentId = id;
  _view = 'session';
  _renderSession();
  // A detached run may still be going for this window (panel was closed, or the
  // app was reloaded and lost the in-page stream). Re-attach so you SEE it
  // finishing — the work never stopped server-side.
  if (!s.busy && s.meta && s.meta.running) _attachLive(s);
}

function _renderSession() {
  const s = _S.get(_currentId);
  const v = _el('code-view');
  if (!s || !v) return;
  v.innerHTML = `
    <div style="display:flex;align-items:center;gap:8px;margin-bottom:6px;">
      <button class="admin-btn-sm" id="code-back" title="Back to the board">⊞ Board</button>
      <div style="font-weight:600;font-size:14px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">⌨ ${_esc(s.meta.name)}</div>
      <span id="code-model" style="font-size:11px;opacity:.6;"></span>
      <span style="flex:1;"></span>
      <button class="admin-btn-sm" id="code-repoint" title="Point this window at a different folder">📂</button>
      <button class="admin-btn-sm" id="code-map-toggle">▸ Map</button>
      <button class="modal-close" id="code-close" aria-label="Close">×</button>
    </div>
    <div style="font-size:10.5px;opacity:.5;margin-bottom:6px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;" title="${_esc(s.meta.root)}">${_esc(s.meta.root)}</div>
    <div id="code-map" style="display:none;font-size:12px;border:1px solid var(--border,#333);border-radius:8px;padding:8px;margin-bottom:8px;max-height:28vh;overflow:auto;white-space:pre-wrap;font-family:var(--mono,monospace);"></div>
    <div id="code-thread" style="flex:1;overflow:auto;padding:6px 2px;display:flex;flex-direction:column;gap:10px;min-height:0;"></div>
    <div style="border-top:1px solid var(--border,#333);padding-top:8px;">
      <div style="display:flex;align-items:center;gap:8px;margin-bottom:6px;">
        <div id="code-modes" style="display:flex;gap:3px;flex-wrap:wrap;">
          ${_MODES.map(m => `<button class="code-mode-btn" data-mode="${m.id}" title="${m.hint}"
            style="font-size:11px;padding:2px 9px;border-radius:7px;cursor:pointer;border:1px solid var(--border);
            background:${_mode === m.id ? 'var(--red,#FF5758)' : 'transparent'};
            color:${_mode === m.id ? '#fff' : 'var(--fg)'};">${m.label}</button>`).join('')}
        </div>
        <span id="code-running" style="font-size:12px;font-weight:600;color:var(--red,#FF5758);display:none;align-items:center;gap:6px;"></span>
        <span style="flex:1;"></span>
        <span id="code-status" style="font-size:11px;opacity:.6;"></span>
      </div>
      <div id="code-mode-hint" style="font-size:10.5px;opacity:.55;margin-bottom:6px;">${_esc((_MODES.find(m => m.id === _mode) || _MODES[0]).hint)}</div>
      <div style="display:flex;gap:8px;">
        <textarea id="code-input" rows="2" placeholder="Ask about the project, or tell the agent what to build/fix…  (⌘↵ to send)"
          style="flex:1;box-sizing:border-box;resize:vertical;padding:8px;border-radius:8px;"></textarea>
        <button class="admin-btn-sm" id="code-send" style="font-weight:600;">${s.busy ? 'Stop ■' : 'Send ▶'}</button>
      </div>
    </div>`;

  _el('code-back').addEventListener('click', () => { _detachLive(s); _renderBoard(); });
  _el('code-close').addEventListener('click', closePanel);
  _el('code-repoint').addEventListener('click', () => { _pickFor = _currentId; openWorkspaceBrowser(); });
  _el('code-map-toggle').addEventListener('click', () => {
    const m = _el('code-map'); if (m) m.style.display = m.style.display === 'none' ? 'block' : 'none';
  });
  (_el('code-modes') ? _el('code-modes').querySelectorAll('.code-mode-btn') : []).forEach((btn) => {
    btn.addEventListener('click', () => {
      _mode = btn.dataset.mode;
      try { localStorage.setItem('ody-code-mode', _mode); } catch (e) {}
      _el('code-modes').querySelectorAll('.code-mode-btn').forEach((b) => {
        const on = b.dataset.mode === _mode;
        b.style.background = on ? 'var(--red,#FF5758)' : 'transparent';
        b.style.color = on ? '#fff' : 'var(--fg)';
      });
      const h = _el('code-mode-hint'); const m = _MODES.find((x) => x.id === _mode);
      if (h && m) h.textContent = m.hint;
      const inp = _el('code-input');
      if (inp) inp.placeholder = _mode === 'plan' ? 'Describe what to plan — I’ll plan, not build, until you press Act…'
        : _mode === 'act' ? 'Press Send to execute the plan above (or add a note)…'
        : _mode === 'review' ? 'What should I review? (read-only — no changes)'
        : _mode === 'research' ? 'What should I research on the web?'
        : 'Ask about the project, or tell the agent what to build/fix…  (⌘↵ to send)';
    });
  });
  _el('code-send').addEventListener('click', () => {
    const cur = _S.get(_currentId);
    if (cur && cur.busy) {
      // Work is detached server-side now, so aborting the local stream isn't
      // enough — tell the server to actually stop the job.
      try { cur.ctrl && cur.ctrl.abort(); } catch (e) {}
      _api('/api/code/job/stop?sid=' + encodeURIComponent(cur.meta.id), { method: 'POST' }).catch(() => {});
      return;
    }
    _send();
  });
  _el('code-input').addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) { e.preventDefault(); _send(); }
  });

  // rebuild the thread from history (+ live bubble if this session is running)
  (s.history || []).forEach((m) => {
    const b = _bubble(m.role === 'user' ? 'user' : 'coder');
    const c = (m.content || '').trim();
    // A cancelled turn ("[stopped]" / empty) is NOT a failed build — make that
    // unmistakable so a stopped run isn't mistaken for broken output.
    if (m.role !== 'user' && (c === '' || c === '[stopped]' || c === '[stopped by user]')) {
      b.body.innerHTML = '<span style="opacity:.6;font-style:italic;">⏹ Stopped — nothing was written this turn. Send again to continue.</span>';
    } else {
      b.body.textContent = m.content;
    }
  });
  if (s.busy) {
    const b = _bubble('coder');
    b.body.textContent = s.live || '…';
    s.liveBodyEl = b.body; s.liveToolsEl = b.tools;
  }
  _scroll();
  const ci = _el('code-input'); if (ci && !s.busy) ci.focus();
  _ensureRunStyle();
  _setRunUI(s.busy);     // reflect current state immediately
  _startJobPoll();       // then keep it synced to server truth
  _loadContext(s);
}

function _detachLive(s) {
  if (s) { s.liveBodyEl = null; s.liveToolsEl = null; }
}

// ── Running indicator + server-truth poll ───────────────────────────────────
// The work is detached server-side, so the client's local `busy` flag can drift
// (stream dropped, panel reopened) while the job keeps going. We poll the job
// status so the open panel ALWAYS shows the true running state — and re-attach
// to a still-running job so you can watch it finish.
function _ensureRunStyle() {
  if (document.getElementById('code-run-style')) return;
  const st = document.createElement('style');
  st.id = 'code-run-style';
  st.textContent = '@keyframes codeRunPulse{0%,100%{opacity:1;transform:scale(1)}50%{opacity:.3;transform:scale(.6)}}'
    + '.code-run-dot{width:9px;height:9px;border-radius:50%;background:var(--red,#FF5758);display:inline-block;animation:codeRunPulse 1s ease-in-out infinite;}';
  document.head.appendChild(st);
}

function _setRunUI(running) {
  const sb = _el('code-send'); if (sb) sb.textContent = running ? 'Stop ■' : 'Send ▶';
  const r = _el('code-running');
  if (r) {
    r.style.display = running ? 'inline-flex' : 'none';
    r.innerHTML = running ? '<span class="code-run-dot"></span> Working…' : '';
  }
}

let _jobPollTimer = null;
function _startJobPoll() {
  _stopJobPoll();
  _jobPollTimer = setInterval(async () => {
    if (!_open || _view !== 'session') { _stopJobPoll(); return; }
    const s = _S.get(_currentId);
    if (!s) return;
    if (s.busy) { _setRunUI(true); return; }   // our own live stream owns the UI
    let st = null;
    try { st = await (await _api('/api/code/job?sid=' + encodeURIComponent(s.meta.id))).json(); } catch (e) { return; }
    if (st && st.running) {
      _setRunUI(true);
      _attachLive(s);   // detached job still going, but we're not watching → re-attach
    } else {
      _setRunUI(false);
    }
  }, 2500);
}
function _stopJobPoll() { if (_jobPollTimer) { clearInterval(_jobPollTimer); _jobPollTimer = null; } }

async function _loadContext(s) {
  if (!s || !s.meta.root) return;
  const st = _el('code-status');
  if (s.ctxLine) { if (st) st.textContent = s.ctxLine; }
  else if (st) st.textContent = 'reading project…';
  let ctx;
  try { ctx = await (await _api('/api/code/context?path=' + encodeURIComponent(s.meta.root))).json(); }
  catch (e) { if (st) st.textContent = 'could not read project'; return; }
  if (!ctx.ok) { if (st) st.textContent = ctx.detail || 'error'; return; }
  const mEl = _el('code-model');
  if (mEl) mEl.textContent = ctx.coder_model ? '· ' + ctx.coder_model : '';
  const langs = Object.entries(ctx.stats.languages || {}).map(([k, v]) => `${k}×${v}`).join(' · ');
  s.ctxLine = `${ctx.stats.code_files} files · ${langs}`;
  if (_currentId === s.meta.id) {
    const st2 = _el('code-status');
    if (st2) st2.textContent = s.ctxLine;
    const agentsLine = ctx.agents
      ? `📜 ${_esc(ctx.agents.name)} found (project instructions)`
      : `<span style="opacity:.7;">No AGENTS.md — </span><a href="#" id="code-mkagents">create one</a>`;
    const map = _el('code-map');
    if (map) {
      map.innerHTML = `<div style="font-family:var(--font,sans-serif);margin-bottom:6px;">${agentsLine}</div>`
        + '<b>File tree</b>\n' + _esc(ctx.tree) + '\n\n<b>Key symbols</b>\n' + _esc(ctx.map_text);
      const mk = _el('code-mkagents');
      if (mk) mk.addEventListener('click', async (e) => {
        e.preventDefault();
        try {
          await _api('/api/code/agents-md', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ path: s.meta.root }) });
          _loadContext(s);
        } catch (err) {}
      });
    }
  }
}

function _bubble(role) {
  const wrap = document.createElement('div');
  wrap.className = 'code-msg';
  wrap.style.cssText = 'display:flex;flex-direction:column;gap:3px;';
  const who = document.createElement('div');
  who.style.cssText = 'font-size:10px;opacity:.5;text-transform:uppercase;letter-spacing:.5px;';
  who.textContent = role === 'user' ? 'you' : 'coder';
  const tools = document.createElement('div');
  tools.style.cssText = 'font-size:11px;opacity:.8;display:flex;flex-direction:column;gap:2px;';
  const body = document.createElement('div');
  body.style.cssText = 'font-size:13.5px;white-space:pre-wrap;line-height:1.5;'
    + (role === 'user' ? 'background:var(--panel2,#262b34);border:1px solid var(--border,#333);border-radius:8px;padding:7px 10px;align-self:flex-start;max-width:90%;' : '');
  wrap.appendChild(who); wrap.appendChild(tools); wrap.appendChild(body);
  const t = _el('code-thread');
  if (t) t.appendChild(wrap);
  return { wrap, tools, body };
}

function _scroll() { const t = _el('code-thread'); if (t) t.scrollTop = t.scrollHeight; }

async function _send() {
  const s = _S.get(_currentId);
  if (!s || s.busy) return;
  const ta = _el('code-input');
  const msg = (ta && ta.value || '').trim();
  if (!msg) return;
  ta.value = '';
  s.history.push({ role: 'user', content: msg });
  const ub = _bubble('user'); ub.body.textContent = msg;
  const lb = _bubble('coder');
  s.busy = true; s.live = ''; s.liveBodyEl = lb.body; s.liveToolsEl = lb.tools;
  s.ctrl = new AbortController();
  _setRunUI(true);
  _scroll();
  _streamTurn(s, msg);   // intentionally NOT awaited from UI flow — runs in background
}

async function _streamTurn(s, msg) {
  // Start a DETACHED server-side run (keyed by the window id) and tail it. If
  // this tab goes away mid-run, the job keeps going and persists its result —
  // reopening re-attaches via _attachLive(). The work always reaches its goal.
  const id = s.meta.id;
  let resp = null;
  try {
    resp = await _api('/api/code/chat', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ sid: id, path: s.meta.root, message: msg, history: s.history.slice(0, -1), mode: _mode }),
      signal: s.ctrl.signal,
    });
  } catch (e) {
    if (e && e.name === 'AbortError') s.live += '\n[stopped]';
    else s.live += '\n[connection error]';
    if (s.liveBodyEl) s.liveBodyEl.textContent = s.live;
  }
  await _consumeSSE(s, id, resp, false);
}

// Re-attach to a run still going server-side (reopen, or after an app reload
// that lost the in-page stream). Replays what happened so far, then live.
async function _attachLive(s) {
  const id = s.meta.id;
  s.busy = true; s.live = ''; s.ctrl = new AbortController();
  if (_open && _view === 'session' && _currentId === id) {
    const lb = _bubble('coder'); s.liveBodyEl = lb.body; s.liveToolsEl = lb.tools;
    _setRunUI(true);
  }
  let resp = null;
  try {
    resp = await _api('/api/code/chat/attach?sid=' + encodeURIComponent(id) + '&cursor=0', { signal: s.ctrl.signal });
  } catch (e) {}
  await _consumeSSE(s, id, resp, true);
}

async function _consumeSSE(s, id, resp, isAttach) {
  try {
    if (!resp || !resp.ok || !resp.body) {
      const t = resp ? await resp.text().catch(() => '') : '';
      s.live += '\n[error] ' + (t || 'could not connect').slice(0, 200);
      if (s.liveBodyEl) s.liveBodyEl.textContent = s.live;
    } else {
      const reader = resp.body.getReader(); const dec = new TextDecoder(); let buf = '';
      while (true) {
        const { value, done } = await reader.read(); if (done) break;
        buf += dec.decode(value, { stream: true });
        let i;
        while ((i = buf.indexOf('\n\n')) >= 0) {
          const chunk = buf.slice(0, i); buf = buf.slice(i + 2);
          if (!chunk.startsWith('data:')) continue;
          const bd = chunk.slice(5).trim();
          if (bd === '[DONE]') continue;
          let d; try { d = JSON.parse(bd); } catch (e) { continue; }
          _handleEvent(s, d);
        }
      }
    }
  } catch (e) {
    if (e && e.name === 'AbortError') { s.live += '\n[stopped]'; }
    else { s.live += '\n[connection error]'; }
    if (s.liveBodyEl) s.liveBodyEl.textContent = s.live;
  }
  await _finalizeTurn(s, id, isAttach);
}

async function _finalizeTurn(s, id, isAttach) {
  const live = s.live;
  s.busy = false; s.ctrl = null; s.live = '';
  s.liveBodyEl = null; s.liveToolsEl = null;
  s.meta.updated_at = Math.floor(Date.now() / 1000);
  if (isAttach) {
    // The detached job persisted user+assistant server-side; we never saw the
    // user message here, so reload the authoritative history rather than guess.
    try {
      const full = await (await _api('/api/code/sessions/' + id)).json();
      s.history = full.history || s.history;
      if (s.meta) s.meta.running = !!full.running;
    } catch (e) {}
    if (_open && _view === 'session' && _currentId === id) { _renderSession(); return; }
  } else {
    if (live.trim()) s.history.push({ role: 'assistant', content: live.trim() });
    // Server also persists on job completion (same full history → idempotent),
    // so this PATCH is just the fast path when the client stayed connected.
    try {
      await _api('/api/code/sessions/' + id, { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ history: s.history }) });
    } catch (e) {}
  }
  if (_open && _view === 'session' && _currentId === id) {
    _setRunUI(false);   // the poll re-detects if a job is somehow still going
    if (!isAttach) _loadContext(s);   // repo map may have changed
  } else if (_open && _view === 'board') {
    _renderBoard();    // refresh tile badges
  }
}

function _handleEvent(s, d) {
  const displayed = _open && _view === 'session' && _currentId === s.meta.id;
  if (d.delta && typeof d.delta === 'string') {
    s.live += d.delta;
    if (displayed && s.liveBodyEl) { s.liveBodyEl.textContent = s.live; _scroll(); }
  } else if (d.type === 'tool_start') {
    if (displayed && s.liveToolsEl) {
      const c = document.createElement('div');
      c.textContent = '🔧 ' + (d.tool || '') + (d.command ? ' · ' + String(d.command).slice(0, 80) : '');
      s.liveToolsEl.appendChild(c); _scroll();
    }
  } else if (d.type === 'tool_output') {
    if (displayed && s.liveToolsEl) {
      const ok = (d.exit_code === 0 || d.exit_code == null);
      const c = document.createElement('div');
      c.innerHTML = (ok ? '✓ ' : '✗ ') + '<b>' + _esc(d.tool || '') + '</b> ' + _esc(String(d.output || '').slice(0, 140));
      if (!ok) c.style.color = '#ff5758';
      s.liveToolsEl.appendChild(c); _scroll();
    }
  } else if (d.type === 'error') {
    s.live += '\n[error] ' + (d.message || '');
    if (displayed && s.liveBodyEl) s.liveBodyEl.textContent = s.live;
  }
}

// ─────────────────────────── panel control ───────────────────────────

function _onEsc(e) { if (e.key === 'Escape' && _open) closePanel(); }

function closePanel() {
  if (!_open) return;
  _open = false;
  document.removeEventListener('keydown', _onEsc);
  // Clear any pending folder-pick intent so a later workspace pick elsewhere
  // can't silently create/repoint a code window.
  _pickFor = null;
  // Do NOT abort running sessions — the board's whole point is that windows
  // keep working in the background (see them in Activity).
  _stopJobPoll();
  _S.forEach((s) => _detachLive(s));
  const m = _el('code-modal');
  if (m) m.style.display = 'none';
}

function togglePanel() { _open ? closePanel() : openPanel(); }
function isPanelOpen() { return _open; }

const codeModule = { openPanel, closePanel, togglePanel, isPanelOpen };
export default codeModule;
