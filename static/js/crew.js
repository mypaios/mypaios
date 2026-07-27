// Crew — local multi-agent mesh panel.
// Supervisor decomposes a goal into steps and dispatches to mini-agents
// (Planner/Coder/Retriever/Ops). Local-first routing; plan→approve→run is the
// human-in-the-loop gate. Streams progress over SSE (fetch + ReadableStream).

import { getWorkspace, openWorkspaceBrowser } from './workspace.js';

let _open = false;
let _plan = null;          // last plan from /api/crew/plan (editable, approved on Run)
let _planGoal = null;      // goal the plan was made for — stale plans aren't sent
let _running = false;
let _ctrl = null;

// Folder selection arrives via this event (openWorkspaceBrowser resolves on
// open, not on pick).
document.addEventListener('workspace-changed', () => { if (_open) _syncWs(); });

const _el = (id) => document.getElementById(id);
const _esc = (s) => (s || '').replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
const _api = (p, o) => fetch(p, Object.assign({ credentials: 'same-origin' }, o || {}));
const _basename = (p) => (p || '').replace(/[\\/]+$/, '').split(/[\\/]/).pop() || '';

const ROLE_ICON = { planner: '🧭', retriever: '🔎', coder: '💻', ops: '⚙️' };

function openPanel() {
  if (_open) return;
  _open = true;
  const modal = document.createElement('div');
  modal.className = 'modal';
  modal.id = 'crew-modal';
  modal.innerHTML = `
    <div class="modal-content" style="max-width:780px;max-height:88vh;overflow:auto;">
      <div style="display:flex;align-items:center;gap:10px;margin-bottom:6px;">
        <div style="font-weight:600;font-size:15px;flex:1;">Crew — local agent mesh</div>
        <span id="crew-cloud-pill" style="font-size:11px;opacity:.7;"></span>
        <button class="modal-close" id="crew-close" aria-label="Close">×</button>
      </div>
      <div style="font-size:12px;opacity:.7;margin-bottom:10px;">
        🔒 Runs locally. A Supervisor splits your goal into steps and routes each to a specialist
        (local Ollama models, cloud off by default). Review the plan, then Run.
      </div>

      <div id="crew-roster" style="display:flex;flex-wrap:wrap;gap:6px;margin-bottom:10px;"></div>

      <textarea id="crew-goal" rows="3" placeholder="Describe a goal — e.g. &quot;Find the open TODOs in this project, then fix the simplest one and add a test.&quot;"
        style="width:100%;box-sizing:border-box;resize:vertical;padding:8px;border-radius:8px;"></textarea>

      <div style="display:flex;align-items:center;gap:8px;margin:8px 0;flex-wrap:wrap;">
        <span style="font-size:12px;opacity:.7;">Workspace (for Coder/Ops):</span>
        <span id="crew-ws" style="font-size:12px;font-weight:600;">none</span>
        <button class="admin-btn-sm" id="crew-pick-ws">Pick folder</button>
        <span style="flex:1;"></span>
        <button class="admin-btn-sm" id="crew-plan-btn">Plan</button>
        <button class="admin-btn-sm" id="crew-run-btn" style="font-weight:600;">Run ▶</button>
      </div>

      <div id="crew-plan" style="margin:6px 0;"></div>
      <div id="crew-stream" style="margin:6px 0;"></div>
      <div id="crew-final" style="margin:8px 0;"></div>

      <div style="margin-top:14px;border-top:1px solid var(--border,#333);padding-top:8px;">
        <div style="font-size:12px;opacity:.7;margin-bottom:6px;">Recent runs</div>
        <div id="crew-history" style="font-size:12px;"></div>
      </div>
    </div>`;
  document.body.appendChild(modal);

  _el('crew-close').addEventListener('click', closePanel);
  modal.addEventListener('click', (e) => { if (e.target === modal && !_running) closePanel(); });
  document.addEventListener('keydown', _onEsc);
  _el('crew-pick-ws').addEventListener('click', () => openWorkspaceBrowser());
  _el('crew-plan-btn').addEventListener('click', _doPlan);
  _el('crew-goal').addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) {
      e.preventDefault();
      const g = (_el('crew-goal').value || '').trim();
      if (_plan && _planGoal === g && !_running) _doRun(); else _doPlan();
    }
  });
  _el('crew-run-btn').addEventListener('click', () => {
    if (_running) { try { _ctrl && _ctrl.abort(); } catch (e) {} return; }  // acts as Stop while running
    _doRun();
  });

  _syncWs();
  _loadStatus();
  _loadRoster();
  _loadHistory();
}

function _syncWs() {
  const ws = getWorkspace();
  const span = _el('crew-ws');
  if (span) { span.textContent = ws ? _basename(ws) : 'none'; span.title = ws || ''; }
}

async function _loadStatus() {
  try {
    const r = await _api('/api/crew/status');
    if (!r.ok) return;
    const s = await r.json();
    const pill = _el('crew-cloud-pill');
    if (pill) pill.textContent = (s.local_models && s.local_models.length)
      ? `${s.local_models.length} local model${s.local_models.length > 1 ? 's' : ''}${s.allow_cloud ? ' · cloud on' : ''}`
      : 'no local models — install via Local AI';
  } catch (_) {}
}

async function _loadRoster() {
  const box = _el('crew-roster');
  if (!box) return;
  try {
    const r = await _api('/api/crew/agents');
    const d = await r.json();
    box.innerHTML = (d.agents || []).map(a => {
      const m = a.routed_model ? _esc(a.routed_model) : '—';
      const ic = ROLE_ICON[a.role] || '🤖';
      const priv = a.privileged ? ' title="privileged: runs code/shell"' : '';
      return `<span class="admin-card" style="padding:6px 9px;border-radius:8px;font-size:11px;"${priv}>
        <b>${ic} ${_esc(a.name)}</b><br><span style="opacity:.65;">${_esc((a.badges || []).join(' · '))}</span>
        <br><span style="opacity:.5;">→ ${m}</span></span>`;
    }).join('');
  } catch (_) { box.innerHTML = '<span style="opacity:.5;">Could not load the roster.</span>'; }
}

async function _doPlan() {
  const goal = (_el('crew-goal').value || '').trim();
  if (!goal) { _el('crew-plan').innerHTML = '<span style="color:var(--red,#e06);font-size:12px;">Enter a goal first.</span>'; return; }
  _el('crew-plan').innerHTML = '<span style="font-size:12px;opacity:.7;">Planning…</span>';
  try {
    const r = await _api('/api/crew/plan', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ goal }) });
    if (!r.ok) { const t = await r.text(); _el('crew-plan').innerHTML = `<span style="color:var(--red,#e06);font-size:12px;">Plan failed: ${_esc(t)}</span>`; return; }
    _plan = await r.json();
    _planGoal = goal;
    _renderPlan();
  } catch (e) { _el('crew-plan').innerHTML = `<span style="color:var(--red,#e06);font-size:12px;">${_esc(String(e))}</span>`; }
}

function _renderPlan() {
  const box = _el('crew-plan');
  if (!_plan || !_plan.steps) { box.innerHTML = ''; return; }
  const rows = _plan.steps.map((s, i) => {
    const ic = ROLE_ICON[s.agent] || '🤖';
    return `<div style="display:flex;gap:8px;padding:5px 0;border-bottom:1px solid var(--border,#2a2a2a);">
      <div style="font-size:12px;width:90px;opacity:.85;">${i + 1}. ${ic} <b>${_esc(s.agent)}</b></div>
      <div style="font-size:12px;flex:1;">${_esc(s.task)}${s.why ? `<br><span style="opacity:.5;">${_esc(s.why)}</span>` : ''}</div>
    </div>`;
  }).join('');
  box.innerHTML = `<div style="border:1px solid var(--border,#333);border-radius:8px;padding:8px;">
    <div style="font-size:12px;font-weight:600;margin-bottom:4px;">Proposed plan${_plan.routed === false ? ' (heuristic — no model)' : ''} — review, then Run ▶</div>
    ${rows}</div>`;
}

async function _doRun() {
  if (_running) return;
  const goal = (_el('crew-goal').value || '').trim();
  if (!goal) { _el('crew-plan').innerHTML = '<span style="color:var(--red,#e06);font-size:12px;">Enter a goal first.</span>'; return; }
  _running = true;
  const runBtn = _el('crew-run-btn');
  if (runBtn) runBtn.textContent = 'Stop ■';
  _el('crew-stream').innerHTML = '';
  _el('crew-final').innerHTML = '';
  const stream = _el('crew-stream');
  const finalBox = _el('crew-final');
  const stepEls = {};
  const ws = getWorkspace() || null;

  const ensureStep = (idx) => {
    if (stepEls[idx]) return stepEls[idx];
    const d = document.createElement('div');
    d.style = 'border:1px solid var(--border,#333);border-radius:8px;padding:8px;margin:6px 0;';
    d.innerHTML = `<div class="crew-step-head" style="font-size:12px;font-weight:600;"></div>
      <div class="crew-step-tools" style="font-size:11px;opacity:.7;margin:3px 0;"></div>
      <div class="crew-step-out" style="font-size:12px;white-space:pre-wrap;opacity:.9;"></div>`;
    stream.appendChild(d);
    stepEls[idx] = d;
    return d;
  };

  _ctrl = new AbortController();
  try {
    // only send the plan if it was made for THIS goal (else the supervisor re-plans)
    const planToUse = (_plan && _planGoal === goal) ? _plan : null;
    if (_plan && _planGoal !== goal) {
      const pn = _el('crew-plan');
      if (pn) pn.innerHTML = '<span style="opacity:.7;font-size:12px;">Goal changed since you planned — the previous plan was discarded; re-planning live.</span>';
    }
    const resp = await _api('/api/crew/run', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ goal, plan: planToUse, workspace: ws }),
      signal: _ctrl.signal,
    });
    if (!resp.ok || !resp.body) { const t = await resp.text(); finalBox.innerHTML = `<span style="color:var(--red,#e06);font-size:12px;">Run failed: ${_esc(t)}</span>`; return; }
    const reader = resp.body.getReader();
    const dec = new TextDecoder();
    let buf = '';
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buf += dec.decode(value, { stream: true });
      let i;
      while ((i = buf.indexOf('\n\n')) >= 0) {
        const chunk = buf.slice(0, i); buf = buf.slice(i + 2);
        if (!chunk.startsWith('data:')) continue;
        const body = chunk.slice(5).trim();
        if (body === '[DONE]') continue;
        let ev; try { ev = JSON.parse(body); } catch (_) { continue; }
        _handleEvent(ev, { stream, finalBox, ensureStep });
      }
    }
  } catch (e) {
    if (finalBox) {
      finalBox.innerHTML = (e && e.name === 'AbortError')
        ? '<span style="font-size:12px;opacity:.7;">■ Stopped.</span>'
        : `<span style="color:var(--red,#e06);font-size:12px;">${_esc(String(e))}</span>`;
    }
  } finally {
    _running = false; _ctrl = null;
    const runBtn = _el('crew-run-btn');
    if (runBtn) { runBtn.textContent = 'Run ▶'; runBtn.disabled = false; }
    _loadHistory();
  }
}

function _handleEvent(ev, ctx) {
  const t = ev.type;
  if (t === 'run_start') {
    _plan = ev.plan || _plan; _renderPlan();
  } else if (t === 'step_start') {
    const d = ctx.ensureStep(ev.index);
    const ic = ROLE_ICON[ev.agent] || '🤖';
    const cloud = ev.is_cloud ? ' <span style="color:#e6a700;">☁ cloud</span>' : '';
    d.querySelector('.crew-step-head').innerHTML = `${ic} <b>${_esc(ev.agent_name || ev.agent)}</b> — ${_esc(ev.task || '')} <span style="opacity:.5;">(${_esc(ev.model || '?')})</span>${cloud}`;
  } else if (t === 'delta') {
    const d = ctx.ensureStep(ev.index);
    d.querySelector('.crew-step-out').textContent += ev.text || '';
  } else if (t === 'tool') {
    const d = ctx.ensureStep(ev.index);
    const tools = d.querySelector('.crew-step-tools');
    const mark = ev.status === 'start' ? '🔧' : (ev.exit_code === 0 || ev.exit_code == null ? '✓' : '✗');
    tools.innerHTML += `<div>${mark} <b>${_esc(ev.tool || '')}</b> ${_esc((ev.detail || '').slice(0, 120))}</div>`;
  } else if (t === 'step_done') {
    const d = ctx.ensureStep(ev.index);
    const head = d.querySelector('.crew-step-head');
    if (head && !/✓/.test(head.innerHTML)) head.innerHTML = '✓ ' + head.innerHTML;
  } else if (t === 'warning') {
    const d = ctx.ensureStep(ev.index != null ? ev.index : 0);
    d.querySelector('.crew-step-tools').innerHTML += `<div style="color:#e6a700;">⚠ ${_esc(ev.message || '')}</div>`;
  } else if (t === 'synthesis_start') {
    ctx.finalBox.innerHTML = '<div style="font-size:12px;font-weight:600;margin-bottom:4px;">Final answer</div><div class="crew-final-out" style="font-size:13px;white-space:pre-wrap;"></div>';
  } else if (t === 'delta_final') {
    let out = ctx.finalBox.querySelector('.crew-final-out');
    if (!out) { ctx.finalBox.innerHTML = '<div class="crew-final-out" style="font-size:13px;white-space:pre-wrap;"></div>'; out = ctx.finalBox.querySelector('.crew-final-out'); }
    out.textContent += ev.text || '';
  } else if (t === 'done') {
    if (ev.used_cloud) {
      const pill = _el('crew-cloud-pill'); if (pill) pill.innerHTML += ' <span style="color:#e6a700;">· used cloud</span>';
    }
  } else if (t === 'error') {
    ctx.finalBox.innerHTML += `<div style="color:var(--red,#e06);font-size:12px;">Error: ${_esc(ev.message || '')}</div>`;
  }
}

async function _loadHistory() {
  const box = _el('crew-history');
  if (!box) return;
  try {
    const r = await _api('/api/crew/runs');
    const d = await r.json();
    if (!d.runs || !d.runs.length) { box.innerHTML = '<span style="opacity:.5;">No runs yet.</span>'; return; }
    box.innerHTML = d.runs.slice(0, 12).map(run => {
      const cloud = run.used_cloud ? ' ☁' : '';
      const st = run.status === 'done' ? '✓' : (run.status === 'error' ? '✗' : '…');
      return `<div class="crew-run-row" data-run="${_esc(run.id)}" style="padding:3px 0;opacity:.85;cursor:pointer;" title="Click for details">${st} ${_esc((run.goal || '').slice(0, 70))}${cloud}</div>
        <div class="crew-run-detail" id="crew-run-${_esc(run.id)}" style="display:none;"></div>`;
    }).join('');
    box.querySelectorAll('.crew-run-row').forEach((row) =>
      row.addEventListener('click', () => _toggleRunDetail(row.getAttribute('data-run'))));
  } catch (_) { box.innerHTML = '<span style="opacity:.5;">Could not load run history.</span>'; }
}

async function _toggleRunDetail(runId) {
  const box = _el('crew-run-' + runId);
  if (!box) return;
  if (box.style.display !== 'none') { box.style.display = 'none'; return; }
  box.style.display = 'block';
  box.innerHTML = '<div style="opacity:.5;padding:4px 0 4px 16px;">Loading…</div>';
  try {
    const run = await (await _api('/api/crew/run/' + encodeURIComponent(runId))).json();
    const steps = (run.steps || []).map((s) => {
      const ic = ROLE_ICON[s.agent] || '🤖';
      const cloud = s.is_cloud ? ' <span style="color:#e6a700;">☁</span>' : '';
      return `<div style="margin:5px 0;">
          <div style="font-weight:600;">${ic} ${_esc(s.agent)} <span style="opacity:.5;font-weight:400;">· ${_esc(s.model || '')}${cloud}</span></div>
          <div style="opacity:.7;">${_esc((s.task || '').slice(0, 110))}</div>
          <div style="white-space:pre-wrap;opacity:.85;margin-top:2px;">${_esc((s.result || '').slice(0, 400))}${(s.result || '').length > 400 ? '…' : ''}</div>
        </div>`;
    }).join('');
    box.innerHTML = `<div style="border:1px solid var(--border,#333);border-radius:8px;padding:8px 10px;margin:4px 0 8px 14px;font-size:12px;">
        ${steps || '<div style="opacity:.5;">No step records.</div>'}
        ${run.final ? `<div style="border-top:1px solid var(--border,#333);margin-top:6px;padding-top:6px;"><b>Final</b><div style="white-space:pre-wrap;">${_esc(run.final.slice(0, 600))}${run.final.length > 600 ? '…' : ''}</div></div>` : ''}
      </div>`;
  } catch (e) { box.innerHTML = '<div style="opacity:.5;padding:4px 0 4px 16px;">Could not load run.</div>'; }
}

function _onEsc(e) { if (e.key === 'Escape' && _open) closePanel(); }

function closePanel() {
  if (!_open) return;
  if (_running && !confirm('A crew run is in progress — close and STOP it?')) return;
  _open = false;
  document.removeEventListener('keydown', _onEsc);
  try { _ctrl && _ctrl.abort(); } catch (e) {}  // stop any in-flight run
  const m = _el('crew-modal');
  if (m) m.remove();
}

function togglePanel() { _open ? closePanel() : openPanel(); }
function isPanelOpen() { return _open; }

const crewModule = { openPanel, closePanel, togglePanel, isPanelOpen };
export default crewModule;
