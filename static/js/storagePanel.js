// static/js/storagePanel.js — Storage tab: Mac disks, AI-model storage, and
// Pi's own footprint, in one panel. Data from /api/storage (services/storage.py).
// (Named storagePanel.js — storage.js is the localStorage helper.)

let _open = false;

const _el = (id) => document.getElementById(id);
const _esc = (s) => (s || '').replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
const _api = (p, o) => fetch(p, Object.assign({ credentials: 'same-origin' }, o || {}));
const _gb = (n) => (n >= 1000 ? (n / 1000).toFixed(2) + ' TB' : (n >= 10 ? Math.round(n) : n) + ' GB');
const _pctColor = (p) => p >= 90 ? '#ff5758' : p >= 75 ? '#e0a000' : '#2ecc71';

function openPanel() {
  if (_open) return;
  _open = true;
  const modal = document.createElement('div');
  modal.className = 'modal';
  modal.id = 'storage-modal';
  modal.innerHTML = `
    <div class="modal-content" style="max-width:680px;width:94vw;max-height:88vh;display:flex;flex-direction:column;">
      <div style="display:flex;align-items:center;gap:10px;margin-bottom:6px;">
        <div style="font-weight:600;font-size:15px;flex:1;">Storage</div>
        <button class="admin-btn-sm" id="storage-refresh" title="Re-measure (sizes are cached ~2 min)">↻</button>
        <button class="modal-close" id="storage-close" aria-label="Close">×</button>
      </div>
      <div style="font-size:12px;opacity:.7;margin-bottom:10px;">Your Mac's disks, every AI model on disk, and how much space Pi itself takes.</div>
      <div id="storage-body" style="overflow:auto;display:flex;flex-direction:column;gap:14px;">
        <div style="opacity:.6;padding:20px;text-align:center;">Measuring…</div>
      </div>
    </div>`;
  document.body.appendChild(modal);
  _el('storage-close').addEventListener('click', closePanel);
  _el('storage-refresh').addEventListener('click', () => _load(true));
  modal.addEventListener('click', (e) => { if (e.target === modal) closePanel(); });
  document.addEventListener('keydown', _onEsc);
  _load(false);
}

function _onEsc(e) { if (e.key === 'Escape' && _open) closePanel(); }

async function _load(rebuild) {
  const body = _el('storage-body');
  if (!body) return;
  if (rebuild) body.innerHTML = '<div style="opacity:.6;padding:20px;text-align:center;">Re-measuring…</div>';
  // Disable ↻ during the (expensive) du-scan so impatient double-clicks
  // don't fire several rebuilds at the server.
  const rb = _el('storage-refresh');
  if (rb) { rb.disabled = true; rb.style.opacity = '0.5'; }
  let o;
  try { o = await (await _api('/api/storage' + (rebuild ? '?rebuild=true' : ''))).json(); }
  catch (e) { body.innerHTML = '<div style="opacity:.6;padding:20px;">Could not read storage.</div>'; }
  finally { if (rb) { rb.disabled = false; rb.style.opacity = ''; } }
  if (!o || !o.disks) { body.innerHTML = '<div style="opacity:.6;padding:20px;">Could not read storage.</div>'; return; }
  _render(o);
}

function _bar(pct, label) {
  return `<div style="position:relative;height:22px;border-radius:6px;background:var(--panel2,#262b34);border:1px solid var(--border,#333);overflow:hidden;">
      <div style="position:absolute;left:0;top:0;bottom:0;width:${Math.min(100, pct)}%;background:${_pctColor(pct)};opacity:.85;"></div>
      <div style="position:absolute;inset:0;display:flex;align-items:center;justify-content:center;font-size:11px;font-weight:600;">${_esc(label)}</div>
    </div>`;
}

function _section(title, sub, inner) {
  return `<section style="border:1px solid var(--border,#333);border-radius:8px;padding:10px 12px;">
    <div style="display:flex;align-items:baseline;gap:8px;margin-bottom:7px;">
      <div style="font-size:12px;font-weight:600;">${title}</div>
      ${sub ? `<div style="font-size:11px;opacity:.55;">${sub}</div>` : ''}
    </div>${inner}</section>`;
}

function _row(icon, name, gb, note) {
  return `<div style="display:flex;align-items:center;gap:8px;font-size:12.5px;padding:3px 0;">
      <span style="width:18px;text-align:center;">${icon}</span>
      <span style="flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">${_esc(name)}</span>
      ${note ? `<span style="font-size:10.5px;opacity:.45;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;max-width:40%;">${_esc(note)}</span>` : ''}
      <b style="flex-shrink:0;">${_gb(gb)}</b>
    </div>`;
}

function _render(o) {
  const body = _el('storage-body');
  if (!body) return;
  let html = '';

  // ── Mac disks ──
  html += _section('💽 Mac disks', '',
    o.disks.map((d) =>
      `<div style="margin:6px 0;">
         <div style="display:flex;justify-content:space-between;font-size:12px;margin-bottom:3px;">
           <b>${_esc(d.name)}</b><span style="opacity:.6;">${_gb(d.free_gb)} free</span>
         </div>
         ${_bar(d.percent, `${_gb(d.used_gb)} of ${_gb(d.total_gb)} used (${d.percent}%)`)}
       </div>`).join(''));

  // ── Pi-related total ──
  const t = o.totals || {};
  html += `<div style="border:1px solid var(--red,#FF5758);border-left-width:4px;border-radius:8px;padding:9px 12px;font-size:13px;">
      <b style="color:var(--red,#FF5758);">Pi-related storage: ${_gb(t.pi_related_gb || 0)}</b>
      <span style="font-size:11px;opacity:.6;"> — ${_esc(t.note || '')}</span>
    </div>`;

  // ── Models ──
  const m = o.models || {};
  const ol = m.ollama || {};
  let modelsInner = '';
  (ol.items || []).forEach((i) => { modelsInner += _row('🧠', i.name, i.gb); });
  modelsInner += `<div style="border-top:1px dashed var(--border,#333);margin-top:5px;padding-top:5px;">`
    + _row('📦', 'Ollama models total', ol.total_gb || 0, ol.dir)
    + _row('🤗', 'Hugging Face cache', (m.hf_cache || {}).total_gb || 0, 'Whisper · Z-Image · Docling')
    + _row('🎙️', 'Pi model files (Kokoro…)', m.pi_model_files_gb || 0, 'data/models')
    + `</div>`
    + `<div style="font-size:12px;margin-top:6px;"><b>All models: ${_gb(m.total_gb || 0)}</b>
       <span style="font-size:11px;opacity:.55;"> · manage/delete in Local AI</span></div>`;
  html += _section('🧠 AI models on disk', '', modelsInner);

  // ── Pi software ──
  const p = o.pi || {};
  const r = p.repo || {};
  let piInner = ''
    + _row('🖥️', 'MyPaiOS.app (desktop app)', p.app_gb || 0, '/Applications (incl. legacy PiAOS.app)')
    + _row('🐍', 'Python environment (venv)', r.venv_gb || 0)
    + _row('⚛️', 'Desktop shell (electron)', r.electron_gb || 0)
    + _row('🌿', 'Git history', r.git_gb || 0)
    + _row('📄', 'Pi source code', r.code_gb || 0)
    + `<div style="font-size:12px;margin-top:6px;"><b>Pi as software: ${_gb(p.software_total_gb || 0)}</b>
       <span style="font-size:11px;opacity:.55;"> · ${_esc(r.path || '')}</span></div>`;
  html += _section('π Pi software footprint', '', piInner);

  // ── Pi data ──
  let dataInner = '';
  (p.data_items || []).forEach((i) => {
    const icons = { models: '🎙️', chroma: '🧩', generated_images: '🎨', generated_videos: '🎬', fastembed_cache: '🔡' };
    dataInner += _row(icons[i.name] || (i.is_dir ? '📁' : '📄'), i.name, i.gb);
  });
  dataInner += `<div style="font-size:12px;margin-top:6px;"><b>Your Pi data: ${_gb(p.data_gb || 0)}</b>
     <span style="font-size:11px;opacity:.55;"> · chats, knowledge index, images, session boards</span></div>`;
  html += _section('🗂️ Pi data (yours)', 'data/ — knowledge, chats, generated media', dataInner);

  body.innerHTML = html;
}

function closePanel() { if (!_open) return; _open = false; document.removeEventListener('keydown', _onEsc); const m = _el('storage-modal'); if (m) m.remove(); }
function togglePanel() { _open ? closePanel() : openPanel(); }
function isPanelOpen() { return _open; }

const storagePanelModule = { openPanel, closePanel, togglePanel, isPanelOpen };
export default storagePanelModule;
