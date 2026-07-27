// static/js/workspace.js
//
// Workspace picker: browse server directories in a draggable modal, choose a
// folder, and show it as a removable pill in the chat input bar. While set, the
// chat request sends `workspace` so the agent's file/shell tools are confined
// to that folder (see routes/chat_routes.py + src/tool_execution.py).

import Storage, { KEYS } from './storage.js';
import uiModule from './ui.js';
import { makeWindowDraggable } from './windowDrag.js';

const API_BASE = window.location.origin;
// Same folder glyph as the overflow menu item + pill (not an emoji).
const _FOLDER_SVG = '<svg class="workspace-row-icon" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/></svg>';
let _modal = null;
let _curPath = '';

export function getWorkspace() {
  return Storage.get(KEYS.WORKSPACE, '') || '';
}

function _basename(p) {
  if (!p) return '';
  // Handle both POSIX (/) and Windows (\) separators.
  const parts = p.replace(/[\\/]+$/, '').split(/[\\/]/);
  return parts[parts.length - 1] || p;
}

export function syncWorkspaceIndicator(path) {
  const pill = document.getElementById('workspace-indicator-btn');
  const name = document.getElementById('workspace-indicator-name');
  const overflow = document.getElementById('overflow-workspace-btn');
  if (pill) {
    pill.style.display = path ? '' : 'none';
    pill.classList.toggle('active', !!path);
    if (path) pill.title = `Workspace: ${path} — click to clear`;
  }
  if (name) name.textContent = path ? _basename(path) : '';
  if (overflow) overflow.classList.toggle('active', !!path);
  // Recompute the "+" overflow dot (app.js owns updatePlusDot via this event).
  try { document.dispatchEvent(new CustomEvent('overflow-state-change')); } catch (_) {}
}

export function setWorkspace(path) {
  if (path) Storage.set(KEYS.WORKSPACE, path);
  else Storage.remove(KEYS.WORKSPACE);
  syncWorkspaceIndicator(path || '');
  // Notify open panels (Code/Crew/Cowork) — openWorkspaceBrowser() resolves when
  // the dialog OPENS, not when the user picks, so this event is how they learn
  // a folder was actually selected.
  try { document.dispatchEvent(new CustomEvent('workspace-changed', { detail: { path: path || '' } })); } catch (e) {}
}

export function clearWorkspace() {
  setWorkspace('');
  if (uiModule && uiModule.showToast) uiModule.showToast('Workspace cleared');
}

async function _load(path) {
  const url = `${API_BASE}/api/workspace/browse${path ? `?path=${encodeURIComponent(path)}` : ''}`;
  const res = await fetch(url, { credentials: 'same-origin' });
  if (!res.ok) throw new Error(`browse failed: ${res.status}`);
  return res.json();
}

function _render(data) {
  _curPath = data.path;
  const body = _modal.querySelector('#workspace-body');
  const pathEl = _modal.querySelector('#workspace-cur-path');
  if (pathEl) {
    // Reflect the resolved (realpath) location back into the editable field.
    pathEl.value = data.path;
    pathEl.title = data.path;
  }
  let rows = '';
  if (data.parent) {
    rows += `<div class="workspace-row workspace-up" data-path="${encodeURIComponent(data.parent)}">↑ ..</div>`;
  }
  for (const d of data.dirs) {
    // Backend supplies the full child path (os.path.join → cross-platform).
    rows += `<div class="workspace-row" data-path="${encodeURIComponent(d.path)}">${_FOLDER_SVG}<span>${uiModule.esc(d.name)}</span></div>`;
  }
  if (!data.dirs.length && !data.parent) rows = '<div class="workspace-empty">No subfolders</div>';
  body.innerHTML = rows || '<div class="workspace-empty">No subfolders</div>';
  body.querySelectorAll('.workspace-row').forEach((row) => {
    row.addEventListener('click', () => _navigate(decodeURIComponent(row.dataset.path)));
  });
}

async function _navigate(path) {
  try {
    _render(await _load(path));
  } catch (e) {
    if (uiModule && uiModule.showError) uiModule.showError('Could not open folder');
  }
}

async function _runCommand() {
  if (!_modal) return;
  const inp = _modal.querySelector('#workspace-cmd');
  const out = _modal.querySelector('#workspace-cmd-out');
  const runBtn = _modal.querySelector('#workspace-run');
  const cmd = (inp.value || '').trim();
  if (!cmd) return;
  if (runBtn && runBtn.disabled) return;  // already running — ignore double-fire
  if (runBtn) runBtn.disabled = true;
  inp.disabled = true;
  out.style.display = 'block';
  out.textContent = '$ ' + cmd + '\nrunning…';
  try {
    const res = await fetch(`${API_BASE}/api/workspace/exec`, {
      method: 'POST', credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ path: _curPath, command: cmd }),
    });
    const d = await res.json().catch(() => ({}));
    if (!res.ok) { out.textContent = '$ ' + cmd + '\n' + (d.detail || ('error ' + res.status)); return; }
    out.textContent = '$ ' + cmd + '\n' + (d.output || '(no output)') + (d.exit_code ? `\n[exit ${d.exit_code}]` : '');
    inp.value = '';
    try { _render(await _load(_curPath)); } catch (e) {}  // refresh — new folder shows up
  } catch (e) {
    out.textContent = '$ ' + cmd + '\nerror running command';
  } finally {
    if (runBtn) runBtn.disabled = false;
    inp.disabled = false;
  }
}

function _getModal() {
  if (_modal) return _modal;
  _modal = document.createElement('div');
  _modal.id = 'workspace-modal';
  _modal.className = 'modal';
  _modal.style.display = 'none';
  _modal.innerHTML = `
    <div class="modal-content">
      <div class="modal-header">
        <h4><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="vertical-align:-2px;margin-right:6px"><path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/></svg>Select workspace</h4>
        <button class="close-btn" id="workspace-close" aria-label="Close">✖</button>
      </div>
      <input type="text" class="styled-prompt-input workspace-cur" id="workspace-cur-path"
             spellcheck="false" autocomplete="off" autocapitalize="off" autocorrect="off"
             placeholder="Type or paste a folder path, then press Enter" />
      <div class="modal-body workspace-body" id="workspace-body"></div>
      <div class="workspace-cmd-row" style="display:flex;gap:6px;margin-top:8px;">
        <input type="text" id="workspace-cmd" class="styled-prompt-input" spellcheck="false" autocomplete="off"
               autocapitalize="off" autocorrect="off" style="flex:1;font-family:var(--mono,monospace);font-size:12px;"
               placeholder="Run a command in this folder — e.g.  mkdir my-project   ·   ls   ·   git status" />
        <button type="button" class="confirm-btn confirm-btn-secondary" id="workspace-run">Run</button>
      </div>
      <pre id="workspace-cmd-out" style="display:none;max-height:120px;overflow:auto;background:var(--panel2,#262b34);border:1px solid var(--border,#333);border-radius:6px;padding:6px 9px;font-size:11px;margin:6px 0 0;white-space:pre-wrap;"></pre>
      <div class="modal-footer workspace-footer">
        <button type="button" class="confirm-btn confirm-btn-secondary" id="workspace-newfolder">+ New folder</button>
        <button type="button" class="confirm-btn confirm-btn-secondary" id="workspace-reveal" style="margin-right:auto;" title="Show this folder in Finder">Finder ↗</button>
        <button type="button" class="confirm-btn confirm-btn-secondary" id="workspace-cancel">Cancel</button>
        <button type="button" class="confirm-btn confirm-btn-primary" id="workspace-use">Use this folder</button>
      </div>
    </div>`;
  document.body.appendChild(_modal);
  _modal.querySelector('#workspace-close').addEventListener('click', closeWorkspaceBrowser);
  _modal.querySelector('#workspace-cancel').addEventListener('click', closeWorkspaceBrowser);
  // Editable path bar: Enter navigates to a typed/pasted folder.
  _modal.querySelector('#workspace-cur-path').addEventListener('keydown', (e) => {
    if (e.key === 'Enter') {
      e.preventDefault();
      const v = e.target.value.trim();
      if (v) _navigate(v);
    }
  });
  _modal.querySelector('#workspace-use').addEventListener('click', () => {
    // Honor a path the user typed/pasted but didn't press Enter on — the old
    // behavior silently selected the PREVIOUS folder and even toasted it.
    const typedEl = _modal.querySelector('#workspace-cur-path');
    const typed = typedEl ? (typedEl.value || '').trim() : '';
    const chosen = (typed && typed !== _curPath) ? typed : _curPath;
    setWorkspace(chosen);
    if (uiModule && uiModule.showToast) uiModule.showToast(`Workspace set: ${_basename(chosen)}`);
    closeWorkspaceBrowser();
  });
  // "New folder" = a shortcut that prefills the command box (window.prompt is
  // disabled in the Electron app, so we use the inline command box instead).
  _modal.querySelector('#workspace-newfolder').addEventListener('click', () => {
    const inp = _modal.querySelector('#workspace-cmd');
    inp.value = 'mkdir ';
    inp.focus();
    inp.setSelectionRange(inp.value.length, inp.value.length);
  });
  // Command box: run a shell command in the current folder, show output, refresh.
  _modal.querySelector('#workspace-run').addEventListener('click', _runCommand);
  _modal.querySelector('#workspace-cmd').addEventListener('keydown', (e) => {
    if (e.key === 'Enter') { e.preventDefault(); _runCommand(); }
  });
  // Reveal the current folder in Finder (reuses the file-index open endpoint).
  _modal.querySelector('#workspace-reveal').addEventListener('click', async () => {
    try {
      const rv = await fetch(`${API_BASE}/api/file-index/open`, {
        method: 'POST', credentials: 'same-origin',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ path: _curPath, reveal: true }),
      });
      if (!rv.ok && uiModule && uiModule.showError) uiModule.showError('Could not open Finder');
    } catch (e) {
      if (uiModule && uiModule.showError) uiModule.showError('Could not open Finder');
    }
  });
  const content = _modal.querySelector('.modal-content');
  const header = _modal.querySelector('.modal-header');
  if (content && header) makeWindowDraggable(_modal, { content, header });
  return _modal;
}

export async function openWorkspaceBrowser() {
  const modal = _getModal();
  modal.style.display = 'flex';
  try {
    _render(await _load(getWorkspace() || ''));
  } catch (e) {
    const body = modal.querySelector('#workspace-body');
    if (body) body.innerHTML = '<div style="opacity:.6;padding:18px;font-size:13px;">Could not load folders — check the server. You can still type a path above and Use it.</div>';
    if (uiModule && uiModule.showError) uiModule.showError('Could not browse folders');
  }
  document.addEventListener('keydown', _onWsEsc);
}

function _onWsEsc(e) { if (e.key === 'Escape' && _modal && _modal.style.display !== 'none') closeWorkspaceBrowser(); }

export function closeWorkspaceBrowser() {
  if (_modal) _modal.style.display = 'none';
  document.removeEventListener('keydown', _onWsEsc);
}

export function initWorkspace() {
  // Restore persisted workspace into the pill on load.
  syncWorkspaceIndicator(getWorkspace());
  const overflow = document.getElementById('overflow-workspace-btn');
  if (overflow) overflow.addEventListener('click', openWorkspaceBrowser);
  const pill = document.getElementById('workspace-indicator-btn');
  if (pill) pill.addEventListener('click', clearWorkspace);
}

export default { initWorkspace, openWorkspaceBrowser, getWorkspace, setWorkspace, clearWorkspace, syncWorkspaceIndicator };
