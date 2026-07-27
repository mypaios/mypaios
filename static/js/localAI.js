// static/js/localAI.js — "Local AI" hub: one-click download / activate / delete of
// local models for every task (Voice→Text, Text→Voice, Image, Doc/OCR, LLM, Video).
// Talks to /api/local-ai/* (routes/models_hub_routes.py). Mirrors the Agents panel.

let _open = false;
let _poll = null;

const _el = (id) => document.getElementById(id);
const _esc = (s) => (s || '').replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
const _api = (path, opts) => fetch(path, Object.assign({ credentials: 'same-origin' }, opts || {}));
const _gb = (b) => b >= 1e9 ? (b / 1e9).toFixed(1) + ' GB' : b >= 1e6 ? Math.round(b / 1e6) + ' MB' : (b ? Math.round(b / 1e3) + ' KB' : '');

const _FIT = { good: ['#2ecc71', 'Fits your Mac'], slow: ['#e0a000', 'May be slow'], too_big: ['#ff5758', 'Too big'] };
const _ICON = {
  mic: 'M12 2a3 3 0 0 1 3 3v6a3 3 0 0 1-6 0V5a3 3 0 0 1 3-3z M19 10a7 7 0 0 1-14 0 M12 17v4',
  speaker: 'M11 5 6 9H2v6h4l5 4z M19 5a10 10 0 0 1 0 14 M15.5 8.5a5 5 0 0 1 0 7',
  image: 'M3 3h18v18H3z M8.5 8.5 0 0 1 0 0 M21 15l-5-5L5 21',
  doc: 'M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z M14 2v6h6',
  chip: 'M9 3v2 M15 3v2 M9 19v2 M15 19v2 M3 9h2 M3 15h2 M19 9h2 M19 15h2 M5 5h14v14H5z M9 9h6v6H9z',
  video: 'M23 7l-7 5 7 5V7z M1 5h15v14H1z',
};

function openPanel() {
  if (_open) return;
  _open = true;
  const modal = document.createElement('div');
  modal.className = 'modal';
  modal.id = 'localai-modal';
  modal.innerHTML = `
    <div class="modal-content" style="max-width:760px;width:94vw;max-height:88vh;display:flex;flex-direction:column;">
      <div class="modal-header" style="display:flex;align-items:center;gap:8px;">
        <h4 style="margin:0;flex:1;">Local AI</h4>
        <button class="close-btn" id="localai-close" title="Close (Esc)">✖</button>
      </div>
      <div id="localai-banner" style="font-size:12px;opacity:0.8;padding:2px 4px 6px;"></div>
      <div style="display:flex;gap:6px;padding:0 4px 8px;">
        <input id="localai-search" type="text" autocomplete="off" spellcheck="false"
          placeholder="Search models, or paste any Ollama tag (e.g. deepseek-r1:14b)…"
          style="flex:1;background:var(--bg2,#1b1f27);color:var(--fg);border:1px solid var(--border);border-radius:8px;padding:8px 10px;font-size:13px;outline:none;">
        <button class="admin-btn-sm" id="localai-search-clear" title="Clear" style="opacity:.55;">✕</button>
      </div>
      <div id="localai-pulling" style="display:none;font-size:12px;padding:7px 10px;margin:0 4px 8px;border:1px solid var(--border);border-radius:8px;"></div>
      <div id="localai-scroll" style="overflow:auto;padding:0 2px 4px;display:flex;flex-direction:column;gap:14px;">
        <div id="localai-search-results"></div>
        <div id="localai-body" style="display:flex;flex-direction:column;gap:16px;">
          <div style="opacity:0.6;padding:20px;text-align:center;">Loading…</div>
        </div>
        <div id="localai-installed"></div>
      </div>
      <div id="localai-disk" style="font-size:11px;opacity:0.6;border-top:1px solid var(--border);padding-top:8px;margin-top:4px;"></div>
    </div>`;
  document.body.appendChild(modal);
  _el('localai-close').addEventListener('click', closePanel);
  document.addEventListener('keydown', _onEsc);
  modal.addEventListener('mousedown', (e) => { if (e.target === modal) closePanel(); });
  const si = _el('localai-search');
  si.addEventListener('input', _onSearch);
  _el('localai-search-clear').addEventListener('click', () => { si.value = ''; _search(''); si.focus(); });
  _load();
}

async function _load() {
  let data;
  try { data = await (await _api('/api/local-ai/catalog')).json(); }
  catch (e) { _el('localai-body').innerHTML = '<div style="opacity:0.6;padding:20px;">Could not load models.</div>'; return; }
  _render(data);
  _loadInstalled();
  _pollCustom(); // resume progress display for any pull still running server-side
  _api('/api/local-ai/disk').then(r => r.json()).then(d => {
    const el = _el('localai-disk');
    if (el) el.textContent = `🔒 Runs locally · ${d.items?.length || 0} model${(d.items?.length || 0) === 1 ? '' : 's'} on disk · ${_gb(d.total_bytes || 0) || '0 MB'} used`;
  }).catch(() => {});
}

// ───────────── search / bring-your-own model ─────────────
let _searchT = null;
let _customPoll = null;
const _FITC = { green: '#2ecc71', amber: '#e0a000', red: '#ff5758', too_big: '#ff5758', unknown: 'var(--fg)' };

function _onSearch() {
  const q = (_el('localai-search').value || '').trim();
  clearTimeout(_searchT);
  _searchT = setTimeout(() => _search(q), 350);
}

async function _search(q) {
  const box = _el('localai-search-results');
  if (!box) return;
  if (!q) { box.innerHTML = ''; box.style.display = 'none'; return; }
  box.style.display = 'block';
  box.innerHTML = '<div style="opacity:0.6;padding:8px;font-size:12px;">Searching…</div>';
  let results = [], searchFailed = false;
  try { results = (await (await _api('/api/local-ai/search?q=' + encodeURIComponent(q))).json()).results || []; } catch (e) { searchFailed = true; }
  let html = '<section style="border:1px solid var(--border);border-radius:8px;padding:10px 12px;">'
    + '<div style="margin-bottom:8px;"><strong>Search results</strong> <span style="font-size:11px;opacity:0.55;">pick a size and Pull — fit is checked first</span></div>';
  html += searchFailed ? '<div style="opacity:0.6;font-size:12px;padding:4px;">Search failed — is the server reachable?</div>'
    : results.length ? results.map(_searchRow).join('')
    : '<div style="opacity:0.6;font-size:12px;padding:4px;">No curated match — try the exact-tag option below.</div>';
  html += `<div style="display:flex;align-items:center;gap:10px;padding:8px;margin-top:6px;border:1px dashed var(--border);border-radius:6px;">
      <div style="flex:1;min-width:0;font-size:12px;">Bring your own — pull the exact tag <code>${_esc(q)}</code></div>
      <button class="admin-btn-sm" data-pulltag="${_esc(q)}">Resolve &amp; pull</button></div>`;
  html += '</section>';
  box.innerHTML = html;
  box.querySelectorAll('[data-pulltag]').forEach((b) => b.addEventListener('click', () => _pull(b.getAttribute('data-pulltag'))));
  box.querySelectorAll('.localai-pullsel').forEach((b) => b.addEventListener('click', () => {
    const sel = b.previousElementSibling; if (sel && sel.value) _pull(sel.value);
  }));
}

function _searchRow(m) {
  const tags = (m.tags && m.tags.length) ? m.tags : ['latest'];
  const opts = tags.map((t) => `<option value="${_esc(m.name + ':' + t)}">${_esc(t)}</option>`).join('');
  const codeBadge = m.coding ? '<span style="font-size:10px;color:#5BA8FF;border:1px solid #5BA8FF;border-radius:10px;padding:1px 6px;">coding</span>' : '';
  return `<div style="display:flex;align-items:center;gap:10px;padding:8px;border:1px solid var(--border);border-radius:6px;">
    <div style="flex:1;min-width:0;">
      <div style="font-weight:600;font-size:13px;">${_esc(m.name)} ${codeBadge}</div>
      <div style="font-size:11px;opacity:0.65;margin-top:2px;">${_esc(m.blurb || '')}</div>
    </div>
    <div style="display:flex;gap:5px;align-items:center;flex-shrink:0;">
      <select class="localai-tagsel" style="font-size:11px;background:var(--bg2,#1b1f27);color:var(--fg);border:1px solid var(--border);border-radius:5px;padding:3px 5px;">${opts}</select>
      <button class="admin-btn-sm localai-pullsel">Pull</button>
    </div>
  </div>`;
}

async function _pull(tag) {
  if (!tag) return;
  let info;
  try { info = await (await _api('/api/local-ai/resolve?tag=' + encodeURIComponent(tag))).json(); }
  catch (e) { alert('Could not resolve ' + tag); return; }
  if (!info.ok) { alert('Not found: ' + (info.error || tag)); return; }
  if (!info.can_pull) { alert(`${info.fit_label}\n${info.tag} is ${info.size_gb} GB — too large to install.`); return; }
  if (!confirm(`Download ${info.tag}\nSize: ${info.size_gb} GB · ${info.fit_label}\n\nThis can take a while (downloads in the background).`)) return;
  try {
    const r = await _api('/api/local-ai/pull', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ tag: info.tag }) });
    if (!r.ok) { alert('Pull failed (admin required?)'); return; }
  } catch (e) { alert('Pull failed (admin required?)'); return; }
  if (!_customPoll) _customPoll = setInterval(_pollCustom, 2500);
  _pollCustom();
}

async function _pollCustom() {
  let jobs = {};
  try { jobs = (await (await _api('/api/local-ai/status')).json()).jobs || {}; } catch (e) {}
  const entries = Object.entries(jobs).filter(([k]) => k.indexOf('ollama:') === 0);
  const running = entries.filter(([, v]) => v.state === 'running');
  const errs = entries.filter(([, v]) => v.state === 'error');
  const box = _el('localai-pulling');
  if (box) {
    if (running.length) {
      box.style.display = 'block';
      box.innerHTML = running.map(([k, v]) => `⬇ <b>${_esc(k.slice(7))}</b> — ${v.pct != null ? v.pct + '%' : 'downloading…'}`).join('<br>');
    } else if (errs.length) {
      box.style.display = 'block';
      box.innerHTML = errs.map(([k, v]) => `<span style="color:#ff5758;">✗ ${_esc(k.slice(7))}: ${_esc(v.msg || 'failed')}</span>`).join('<br>');
    } else { box.style.display = 'none'; }
  }
  _loadInstalled();
  if (!running.length && _customPoll) { clearInterval(_customPoll); _customPoll = null; }
}

// ───────────── installed (your) models ─────────────
async function _loadInstalled() {
  const box = _el('localai-installed');
  if (!box) return;
  let models = [];
  try { models = (await (await _api('/api/local-ai/installed')).json()).models || []; } catch (e) { return; }
  if (!models.length) { box.innerHTML = ''; return; }
  box.innerHTML = '<section style="border:1px solid var(--border);border-radius:8px;padding:10px 12px;">'
    + '<div style="display:flex;align-items:center;gap:8px;margin-bottom:8px;"><strong>Your installed models</strong>'
    + '<span style="font-size:11px;opacity:0.55;">everything on local Ollama · ⭐ = use for coding</span></div>'
    + '<div style="display:flex;flex-direction:column;gap:6px;">' + models.map(_installedRow).join('') + '</div></section>';
  box.querySelectorAll('[data-coding]').forEach((b) => b.addEventListener('click', () => _setCoding(b.getAttribute('data-coding'))));
  box.querySelectorAll('[data-rm]').forEach((b) => b.addEventListener('click', () => _deletePulled(b.getAttribute('data-rm'))));
}

function _installedRow(m) {
  const c = _FITC[m.fit] || 'var(--fg)';
  const codeBadge = m.coding ? '<span style="font-size:10px;color:#5BA8FF;border:1px solid #5BA8FF;border-radius:10px;padding:1px 6px;">coding</span>' : '';
  const catBadge = m.in_catalog ? '<span style="font-size:10px;opacity:0.5;">· in catalog</span>' : '';
  return `<div style="display:flex;align-items:center;gap:10px;padding:8px;border:1px solid var(--border);border-radius:6px;">
    <div style="flex:1;min-width:0;">
      <div style="font-weight:600;font-size:13px;overflow:hidden;text-overflow:ellipsis;">${_esc(m.name)} ${codeBadge} ${catBadge}</div>
      <div style="margin-top:3px;font-size:11px;"><span style="opacity:0.6;">${m.size_gb} GB</span>
        <span style="color:${c};border:1px solid ${c};border-radius:10px;padding:1px 6px;margin-left:4px;">${_esc(m.fit_label || '')}</span></div>
    </div>
    <div style="display:flex;gap:4px;align-items:center;flex-shrink:0;">
      <button class="admin-btn-sm" data-coding="${_esc(m.name)}" title="Use as the Crew/Cowork coding model">⭐ Coding</button>
      <button class="admin-btn-sm" data-rm="${_esc(m.name)}" title="Delete from disk" style="opacity:0.55;">🗑</button>
    </div>
  </div>`;
}

async function _setCoding(model) {
  try {
    const r = await _api('/api/local-ai/coding-default', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ model }) });
    if (!r.ok) { alert('Failed (admin required?)'); return; }
    alert(`✅ "${model}" is now the coding model.\nCrew's Coder uses it automatically; in Cowork/chat, pick it from the model dropdown.`);
    _loadInstalled();   // move the blue 'coding' badge to the new model now
  } catch (e) { alert('Failed (admin required?)'); }
}

async function _deletePulled(tag) {
  if (!confirm(`Delete ${tag} from disk?`)) return;
  try {
    const r = await _api('/api/local-ai/pulled?tag=' + encodeURIComponent(tag), { method: 'DELETE' });
    if (!r.ok) { const d = await r.json().catch(() => ({})); alert('Delete failed: ' + (d.detail || 'admin required / model in use?')); return; }
  } catch (e) { alert('Delete failed — is the server up?'); return; }
  _loadInstalled();
}

function _render(data) {
  const sys = data.system || {};
  const ram = sys.total_ram_gb ? `${Math.round(sys.total_ram_gb)} GB` : '';
  _el('localai-banner').innerHTML = `🔒 Everything below runs <b>locally on this Mac</b> — nothing leaves your device.` +
    (sys.cpu_name ? ` <span style="opacity:0.6">· ${_esc(sys.cpu_name)}${ram ? ' · ' + ram : ''}</span>` : '');

  const models = data.models || [];
  const body = _el('localai-body');
  body.innerHTML = '';
  let anyRunning = false;

  (data.modalities || []).forEach((mod) => {
    const rows = models.filter((m) => m.modality === mod.key);
    if (!rows.length) return;
    const sec = document.createElement('section');
    sec.style.cssText = 'border:1px solid var(--border);border-radius:8px;padding:10px 12px;';
    const path = _ICON[mod.icon] || '';
    sec.innerHTML = `<div style="display:flex;align-items:center;gap:8px;margin-bottom:8px;">
        <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="opacity:0.7;flex-shrink:0;"><path d="${path}"/></svg>
        <strong>${_esc(mod.title)}</strong>
        <span style="font-size:11px;opacity:0.55;">${_esc(mod.blurb || '')}</span>
      </div>`;
    const list = document.createElement('div');
    list.style.cssText = 'display:flex;flex-direction:column;gap:6px;';
    rows.forEach((m) => { if (m.job && m.job.state === 'running') anyRunning = true; list.appendChild(_card(m)); });
    sec.appendChild(list);
    body.appendChild(sec);
  });

  if (anyRunning && !_poll) _poll = setInterval(_load, 1600);
  if (!anyRunning && _poll) { clearInterval(_poll); _poll = null; }
}

function _card(m) {
  const row = document.createElement('div');
  row.style.cssText = 'display:flex;align-items:center;gap:10px;padding:8px;border:1px solid var(--border);border-radius:6px;';
  const fit = _FIT[m.fit];
  const badges = (m.badges || []).map((b) =>
    `<span style="font-size:10px;padding:1px 6px;border-radius:10px;background:color-mix(in srgb, var(--fg) 9%, transparent);">${_esc(b)}</span>`).join(' ');
  const fitPill = fit ? `<span style="font-size:10px;padding:1px 6px;border-radius:10px;color:${fit[0]};border:1px solid ${fit[0]};">${fit[1]}</span>` : '';
  const sizeTxt = m.size_gb ? (m.size_gb >= 1 ? m.size_gb + ' GB' : Math.round(m.size_gb * 1000) + ' MB') : '';
  const dot = m.active ? '#2ecc71' : (m.installed ? 'var(--fg)' : 'color-mix(in srgb, var(--fg) 30%, transparent)');

  let action = '';
  const job = m.job;
  if (job && job.state === 'running') {
    action = `<button class="admin-btn-sm" disabled style="opacity:0.7;">${job.pct != null ? job.pct + '%' : 'Installing…'}</button>`;
  } else if (m.install_method === 'endpoint') {
    action = `<span style="font-size:11px;opacity:0.6;max-width:230px;">${_esc((m.params && m.params.hint) || 'Configure in Settings → Models')}</span>`;
  } else if (!m.installed) {
    action = `<button class="admin-btn-sm" data-act="install" data-id="${m.id}">Download</button>`;
  } else if (!m.active) {
    action = `<button class="admin-btn-sm" data-act="activate" data-id="${m.id}">Enable</button>
              <button class="admin-btn-sm" data-act="delete" data-id="${m.id}" title="Delete" style="opacity:0.55;">🗑</button>`;
  } else {
    action = `<button class="admin-btn-sm" data-act="deactivate" data-id="${m.id}" style="color:#2ecc71;border-color:#2ecc71;">✓ Active</button>
              <button class="admin-btn-sm" data-act="delete" data-id="${m.id}" title="Delete" style="opacity:0.55;">🗑</button>`;
  }
  const errMsg = (job && job.state === 'error') ? `<div style="font-size:11px;color:#ff5758;margin-top:3px;">${_esc(job.msg)}</div>` : '';

  row.innerHTML = `
    <span style="width:8px;height:8px;border-radius:50%;background:${dot};flex-shrink:0;"></span>
    <div style="flex:1;min-width:0;">
      <div style="font-weight:600;font-size:13px;">${_esc(m.name)} ${m.default ? '<span style="font-size:10px;opacity:0.6;">· recommended</span>' : ''}</div>
      <div style="display:flex;align-items:center;gap:5px;flex-wrap:wrap;margin-top:3px;">
        ${sizeTxt ? `<span style="font-size:11px;opacity:0.6;">${sizeTxt}</span>` : ''}${badges}${fitPill}
      </div>${errMsg}
    </div>
    <div style="display:flex;gap:4px;align-items:center;flex-shrink:0;">${action}</div>`;

  row.querySelectorAll('[data-act]').forEach((b) =>
    b.addEventListener('click', () => _doAction(b.getAttribute('data-act'), b.getAttribute('data-id'))));
  return row;
}

async function _doAction(act, id) {
  let r = null;
  try {
    if (act === 'install') {
      r = await _api('/api/local-ai/install', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ id }) });
    } else if (act === 'activate' || act === 'deactivate') {
      r = await _api('/api/local-ai/' + act, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ id }) });
    } else if (act === 'delete') {
      if (!confirm('Delete this model from disk?')) return;
      r = await _api('/api/local-ai/model?id=' + encodeURIComponent(id), { method: 'DELETE' });
    }
    // HTTP errors (403 non-admin, 500) don't throw — without this check the
    // click silently no-ops and the list just repaints unchanged.
    if (r && !r.ok) {
      const d = await r.json().catch(() => ({}));
      alert(act + ' failed: ' + (d.detail || r.status));
    }
  } catch (e) { alert('Action failed (admin required?)'); }
  _load();
}

function _onEsc(e) { if (e.key === 'Escape' && _open) closePanel(); }
function closePanel() { _open = false; if (_poll) { clearInterval(_poll); _poll = null; } document.removeEventListener('keydown', _onEsc); const m = _el('localai-modal'); if (m) m.remove(); }
function togglePanel() { _open ? closePanel() : openPanel(); }
function isPanelOpen() { return _open; }

const localAIModule = { openPanel, closePanel, togglePanel, isPanelOpen };
export default localAIModule;
