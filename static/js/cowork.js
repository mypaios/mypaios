// static/js/cowork.js — "Cowork": a local Claude-style coding session launcher.
// Reuses MyPaiOS's existing agent loop (workspace-scoped bash/python/read_file/
// write_file/edit_file) + the workspace picker. This panel ties it together:
// pick a project folder, install/choose a local coding model, then start an
// agent-mode coding session in that folder (edits files, runs shell/pytest/
// Playwright, iterates). See routes/chat_routes.py + src/agent_loop.py.

import { openWorkspaceBrowser, getWorkspace } from './workspace.js';

let _open = false;
let _poll = null;

const _el = (id) => document.getElementById(id);
const _esc = (s) => (s || '').replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
const _api = (p, o) => fetch(p, Object.assign({ credentials: 'same-origin' }, o || {}));
const _basename = (p) => (p || '').replace(/[\\/]+$/, '').split(/[\\/]/).pop() || '';

function openPanel() {
  if (_open) return;
  _open = true;
  const modal = document.createElement('div');
  modal.className = 'modal';
  modal.id = 'cowork-modal';
  modal.innerHTML = `
    <div class="modal-content" style="max-width:640px;width:92vw;max-height:86vh;display:flex;flex-direction:column;">
      <div class="modal-header" style="display:flex;align-items:center;gap:8px;">
        <h4 style="margin:0;flex:1;">Cowork — local coding agent</h4>
        <button class="close-btn" id="cowork-close">✖</button>
      </div>
      <div class="modal-body" style="overflow:auto;padding:6px 4px;display:flex;flex-direction:column;gap:14px;">
        <section style="border:1px solid var(--border);border-radius:8px;padding:12px;">
          <strong style="display:block;margin-bottom:6px;">1 · Project folder</strong>
          <div style="display:flex;align-items:center;gap:8px;">
            <span id="cowork-ws" style="flex:1;font-size:13px;opacity:0.85;word-break:break-all;"></span>
            <button class="admin-btn-sm" id="cowork-pick">Choose folder…</button>
          </div>
          <div style="font-size:11px;opacity:0.55;margin-top:6px;">The agent's file edits and commands are confined to this folder.</div>
        </section>
        <section style="border:1px solid var(--border);border-radius:8px;padding:12px;">
          <strong style="display:block;margin-bottom:8px;">2 · Coding model (local, open-source)</strong>
          <div id="cowork-models" style="display:flex;flex-direction:column;gap:6px;"><div style="opacity:0.6;font-size:12px;">Loading…</div></div>
          <div style="font-size:11px;opacity:0.55;margin-top:6px;">After install, pick it in the model menu (bottom-right of chat). Works with your current model too.</div>
        </section>
        <section style="border:1px solid var(--border);border-radius:8px;padding:12px;font-size:12px;opacity:0.8;line-height:1.5;">
          <strong style="display:block;margin-bottom:4px;">What Cowork can do</strong>
          Read &amp; edit files · run shell &amp; <code>pytest</code> · run <b>Playwright</b> E2E tests · iterate write→test→fix — all inside your folder.<br>
          <span style="opacity:0.7;">🔒 Destructive commands (disk-wide deletes, <code>sudo</code>, <code>git push</code>, piping the web into a shell) are blocked.</span>
        </section>
      </div>
      <div class="modal-footer" style="display:flex;justify-content:flex-end;gap:8px;padding-top:10px;border-top:1px solid var(--border);">
        <button class="confirm-btn confirm-btn-secondary" id="cowork-cancel">Close</button>
        <button class="confirm-btn confirm-btn-primary" id="cowork-start">Start coding session →</button>
      </div>
    </div>`;
  document.body.appendChild(modal);
  _el('cowork-close').addEventListener('click', closePanel);
  _el('cowork-cancel').addEventListener('click', closePanel);
  modal.addEventListener('mousedown', (e) => { if (e.target === modal) closePanel(); });
  _el('cowork-pick').addEventListener('click', () => { openWorkspaceBrowser(); });
  _el('cowork-start').addEventListener('click', _start);
  document.addEventListener('keydown', _onEsc);
  _syncWs();
  _loadModels();
}

function _onEsc(e) { if (e.key === 'Escape' && _open) closePanel(); }

// Picking a folder fires this from workspace.js setWorkspace — updates the
// pill + Start button instantly (the old focus/setTimeout hacks never fired
// because the picker lives in the same window).
document.addEventListener('workspace-changed', () => { if (_open) _syncWs(); });

function _syncWs() {
  const ws = getWorkspace();
  const el = _el('cowork-ws');
  if (el) el.innerHTML = ws ? `📂 ${_esc(ws)}` : '<span style="opacity:0.5;">No folder chosen yet</span>';
  const start = _el('cowork-start');
  if (start) start.disabled = !ws;
}

async function _loadModels() {
  let data;
  try { data = await (await _api('/api/local-ai/catalog')).json(); }
  catch (e) { _el('cowork-models').innerHTML = '<div style="opacity:0.6;font-size:12px;">Could not load models.</div>'; return; }
  const coders = (data.models || []).filter((m) => m.code);
  const box = _el('cowork-models');
  box.innerHTML = '';
  let anyRunning = false;
  coders.forEach((m) => {
    if (m.job && m.job.state === 'running') anyRunning = true;
    const row = document.createElement('div');
    row.style.cssText = 'display:flex;align-items:center;gap:8px;padding:6px 8px;border:1px solid var(--border);border-radius:6px;';
    const sizeTxt = m.size_gb >= 1 ? m.size_gb + ' GB' : '';
    const badges = (m.badges || []).map((b) => `<span style="font-size:10px;padding:1px 6px;border-radius:10px;background:color-mix(in srgb,var(--fg) 9%,transparent);">${_esc(b)}</span>`).join(' ');
    let btn;
    if (m.job && m.job.state === 'running') btn = `<button class="admin-btn-sm" disabled>${m.job.pct != null ? m.job.pct + '%' : 'Installing…'}</button>`;
    else if (m.job && (m.job.state === 'failed' || m.job.state === 'error')) btn = `<button class="admin-btn-sm" data-install="${m.id}" title="${_esc(m.job.error || 'download failed')}" style="color:#ff5758;">✗ retry</button>`;
    else if (m.installed) btn = `<span style="font-size:11px;color:#2ecc71;">✓ Installed</span>`;
    else btn = `<button class="admin-btn-sm" data-install="${m.id}">Install</button>`;
    row.innerHTML = `<span style="width:7px;height:7px;border-radius:50%;background:${m.installed ? '#2ecc71' : 'color-mix(in srgb,var(--fg) 30%,transparent)'};flex-shrink:0;"></span>
      <div style="flex:1;min-width:0;"><div style="font-weight:600;font-size:13px;">${_esc(m.name)}${m.code_default ? ' <span style="font-size:10px;opacity:0.6;">· recommended</span>' : ''}</div>
      <div style="display:flex;gap:5px;flex-wrap:wrap;margin-top:2px;">${sizeTxt ? `<span style="font-size:11px;opacity:0.6;">${sizeTxt}</span>` : ''}${badges}</div></div>
      <div style="flex-shrink:0;">${btn}</div>`;
    box.appendChild(row);
  });
  box.querySelectorAll('[data-install]').forEach((b) =>
    b.addEventListener('click', () => _install(b.getAttribute('data-install'))));
  if (anyRunning && !_poll) _poll = setInterval(_loadModels, 1800);
  if (!anyRunning && _poll) { clearInterval(_poll); _poll = null; }
}

async function _install(id) {
  try {
    const r = await _api('/api/local-ai/install', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ id }) });
    if (!r.ok) { const d = await r.json().catch(() => ({})); alert('Install failed: ' + (d.detail || 'admin required?')); }
  } catch (e) { alert('Install failed — is the server up?'); }
  _loadModels();
}

function _start() {
  const ws = getWorkspace();
  if (!ws) { alert('Choose a project folder first.'); return; }
  // Switch the composer to Agent mode (the agent loop + coding tools).
  const ab = _el('mode-agent-btn');
  if (ab && !ab.classList.contains('active')) ab.click();
  closePanel();
  // Focus the chat composer + give a starting hint.
  const inp = document.querySelector('#chat-input, #message-input, textarea.styled-prompt-input, [contenteditable][role="textbox"], .prompt-input textarea');
  if (inp) { try { inp.focus(); } catch (_) {} }
  try { window.dispatchEvent(new CustomEvent('cowork-started', { detail: { workspace: ws } })); } catch (_) {}
}

function closePanel() { _open = false; if (_poll) { clearInterval(_poll); _poll = null; } document.removeEventListener('keydown', _onEsc); const m = _el('cowork-modal'); if (m) m.remove(); }
function togglePanel() { _open ? closePanel() : openPanel(); }
function isPanelOpen() { return _open; }

const coworkModule = { openPanel, closePanel, togglePanel, isPanelOpen };
export default coworkModule;
