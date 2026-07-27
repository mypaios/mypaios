// static/js/agents.js — Agents tab: file Sync agent + smart file Search agent.
// Talks to /api/file-index/* (see routes/file_index_routes.py + src/file_index.py).
// Search results are clickable: a file opens in its default app, a folder opens
// in Finder; the "Finder" button reveals the item in Finder.

let _open = false;
let _searchTimer = null;

const _el = (id) => document.getElementById(id);
const _esc = (s) => (s || '').replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
const _api = (path, opts) => fetch(path, Object.assign({ credentials: 'same-origin' }, opts || {}));
const _fmtTime = (ts) => { if (!ts) return 'never'; try { return new Date(ts * 1000).toLocaleString(); } catch (e) { return '—'; } };

function openPanel() {
  if (_open) return;
  _open = true;
  const modal = document.createElement('div');
  modal.className = 'modal';
  modal.id = 'agents-modal';
  modal.innerHTML = `
    <div class="modal-content" style="max-width:680px;width:92vw;max-height:84vh;display:flex;flex-direction:column;">
      <div class="modal-header" style="display:flex;align-items:center;gap:8px;">
        <h4 style="margin:0;flex:1;">Files — drive sync &amp; search</h4>
        <button class="close-btn" id="agents-close">✖</button>
      </div>
      <div class="modal-body" style="overflow:auto;padding:4px 2px;display:flex;flex-direction:column;gap:14px;">
        <section style="border:1px solid var(--border);border-radius:8px;padding:12px;">
          <div style="display:flex;align-items:center;gap:8px;margin-bottom:8px;">
            <strong style="flex:1;">🔄 Sync agent — connected drives</strong>
            <button class="admin-btn-sm" id="agents-sync-now">Sync now</button>
          </div>
          <div id="agents-status" style="font-size:12px;opacity:0.75;margin-bottom:8px;">Loading…</div>
          <div id="agents-roots" style="display:flex;flex-direction:column;gap:4px;margin-bottom:8px;"></div>
          <div style="display:flex;gap:6px;">
            <input id="agents-root-input" class="settings-input" placeholder="Add a drive/folder path (e.g. /Volumes/MyDrive)" style="flex:1;">
            <button class="admin-btn-sm" id="agents-root-add">Add</button>
          </div>
        </section>
        <section style="border:1px solid var(--border);border-radius:8px;padding:12px;">
          <strong style="display:block;margin-bottom:8px;">🔎 Search agent — files &amp; folders by name</strong>
          <input id="agents-search" class="settings-input" placeholder="Search file/folder names…" autocomplete="off" style="width:100%;">
          <div id="agents-results" style="margin-top:10px;display:flex;flex-direction:column;gap:2px;max-height:42vh;overflow:auto;"></div>
        </section>
      </div>
    </div>`;
  document.body.appendChild(modal);

  _el('agents-close').addEventListener('click', closePanel);
  modal.addEventListener('mousedown', (e) => { if (e.target === modal) closePanel(); });
  _el('agents-sync-now').addEventListener('click', _syncNow);
  _el('agents-root-add').addEventListener('click', _addRoot);
  _el('agents-root-input').addEventListener('keydown', (e) => { if (e.key === 'Enter') _addRoot(); });
  const sb = _el('agents-search');
  sb.addEventListener('input', () => { clearTimeout(_searchTimer); _searchTimer = setTimeout(_doSearch, 180); });
  sb.focus();
  _loadStatus();
}

async function _loadStatus() {
  try {
    const d = await (await _api('/api/file-index')).json();
    const skipped = d.skipped || [];
    const head = `${(d.count || 0).toLocaleString()} items indexed · last sync: ${_fmtTime(d.last_sync)}`;
    _el('agents-status').innerHTML = _esc(head) + (skipped.length
      ? `<div style="margin-top:6px;color:#e0a000;font-size:11px;line-height:1.45;">` +
        `⚠︎ macOS is blocking ${skipped.length} folder${skipped.length > 1 ? 's' : ''} (no Full Disk Access). ` +
        `Grant Pi's backend Full Disk Access in System Settings → Privacy &amp; Security → Full Disk Access, ` +
        `then click <b>Sync now</b>.</div>`
      : '');
    const wrap = _el('agents-roots');
    wrap.innerHTML = '';
    (d.roots || []).forEach((p) => {
      const blocked = skipped.includes(p);
      const row = document.createElement('div');
      row.style.cssText = 'display:flex;align-items:center;gap:6px;font-size:12px;';
      row.innerHTML =
        `<span style="flex:1;opacity:0.85;word-break:break-all;">` +
          `${blocked ? '🔒 ' : ''}${_esc(p)}` +
          `${blocked ? ' <span style="color:#e0a000;">(blocked by macOS)</span>' : ''}</span>` +
        `<button class="admin-btn-sm" data-rm="${_esc(p)}" style="opacity:0.7;">Remove</button>`;
      wrap.appendChild(row);
    });
    wrap.querySelectorAll('[data-rm]').forEach((b) =>
      b.addEventListener('click', () => _removeRoot(b.getAttribute('data-rm'))));
  } catch (e) {
    _el('agents-status').textContent = 'Could not load status.';
  }
}

async function _syncNow() {
  const btn = _el('agents-sync-now');
  const old = btn.textContent;
  btn.textContent = 'Syncing…'; btn.disabled = true;
  try {
    const d = await (await _api('/api/file-index/sync', { method: 'POST' })).json();
    if (d.busy) {
      _el('agents-status').textContent = 'A sync is already running… try again in a moment.';
    } else {
      await _loadStatus();  // refresh count + any "blocked by macOS" warning
    }
    if (_el('agents-search').value.trim()) _doSearch();
  } catch (e) {
    _el('agents-status').textContent = 'Sync failed.';
  }
  btn.textContent = old; btn.disabled = false;
}

async function _addRoot() {
  const inp = _el('agents-root-input');
  const path = inp.value.trim();
  if (!path) return;
  try {
    const r = await _api('/api/file-index/roots', {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ path }),
    });
    if (!r.ok) { const e = await r.json().catch(() => ({})); alert(e.detail || 'Could not add that path'); return; }
    inp.value = '';
    _loadStatus();
  } catch (e) { alert('Could not add drive'); }
}

async function _removeRoot(path) {
  try { await _api('/api/file-index/roots?path=' + encodeURIComponent(path), { method: 'DELETE' }); _loadStatus(); } catch (e) {}
}

async function _doSearch() {
  const q = _el('agents-search').value.trim();
  const box = _el('agents-results');
  if (!q) { box.innerHTML = ''; return; }
  try {
    const d = await (await _api('/api/file-index/search?q=' + encodeURIComponent(q))).json();
    const results = d.results || [];
    if (!results.length) { box.innerHTML = '<div style="opacity:0.5;font-size:12px;padding:6px;">No matches.</div>'; return; }
    box.innerHTML = '';
    results.forEach((r) => {
      const row = document.createElement('div');
      row.style.cssText = 'display:flex;align-items:center;gap:8px;padding:6px 8px;border-radius:6px;cursor:pointer;';
      row.onmouseenter = () => { row.style.background = 'var(--panel)'; };
      row.onmouseleave = () => { row.style.background = ''; };
      const icon = r.is_dir ? '📁' : '📄';
      const dir = r.path.replace(/\/[^/]*$/, '');
      row.innerHTML = `<span>${icon}</span>` +
        `<span style="flex:1;min-width:0;"><span style="font-weight:600;font-size:13px;">${_esc(r.name)}</span>` +
        `<br><span style="opacity:0.5;font-size:11px;word-break:break-all;">${_esc(dir)}</span></span>` +
        `<button class="admin-btn-sm reveal" title="Reveal in Finder" style="opacity:0.6;flex-shrink:0;">Finder</button>`;
      row.addEventListener('click', (e) => { if (e.target.classList.contains('reveal')) return; _openPath(r.path, false); });
      row.querySelector('.reveal').addEventListener('click', (e) => { e.stopPropagation(); _openPath(r.path, true); });
      box.appendChild(row);
    });
  } catch (e) {
    box.innerHTML = '<div style="opacity:0.5;font-size:12px;padding:6px;">Search error.</div>';
  }
}

async function _openPath(path, reveal) {
  try {
    const r = await _api('/api/file-index/open', {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ path, reveal: !!reveal }),
    });
    if (!r.ok) alert('Could not open that path');
  } catch (e) { alert('Could not open'); }
}

function closePanel() { _open = false; const m = _el('agents-modal'); if (m) m.remove(); }
function togglePanel() { _open ? closePanel() : openPanel(); }
function isPanelOpen() { return _open; }

const agentsModule = { openPanel, closePanel, togglePanel, isPanelOpen };
export default agentsModule;
