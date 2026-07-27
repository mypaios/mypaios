// static/js/videoHub.js — Video tab: upload videos, watch local analysis
// (keyframes + transcript → digest), review the timestamped digest, and ask
// about them in chat. Backend: services/video/analyzer.py via
// GET /api/upload/videos · POST /api/upload/{id}/analyze-video ·
// GET /api/upload/{id}/video-digest. 100% local.

let _open = false;
let _poll = null;

const _el = (id) => document.getElementById(id);
const _esc = (s) => (s || '').replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
const _api = (p, o) => fetch(p, Object.assign({ credentials: 'same-origin' }, o || {}));
const _mb = (b) => b >= 1e9 ? (b / 1e9).toFixed(1) + ' GB' : Math.max(1, Math.round((b || 0) / 1e6)) + ' MB';
const _mmss = (t) => { t = Math.round(t || 0); const h = Math.floor(t / 3600), m = Math.floor((t % 3600) / 60), s = t % 60; return (h ? h + ':' + String(m).padStart(2, '0') : m) + ':' + String(s).padStart(2, '0'); };

function openPanel() {
  if (_open) return;
  _open = true;
  const modal = document.createElement('div');
  modal.className = 'modal';
  modal.id = 'video-modal';
  modal.innerHTML = `
    <div class="modal-content" style="max-width:760px;width:94vw;max-height:88vh;display:flex;flex-direction:column;">
      <div style="display:flex;align-items:center;gap:10px;margin-bottom:6px;">
        <div style="font-weight:600;font-size:15px;flex:1;">🎬 Video</div>
        <button class="admin-btn-sm" id="video-upload-btn" title="Upload a video (mp4/mov/webm, up to 512MB) — analysis starts automatically">⬆ Upload</button>
        <input type="file" id="video-upload-file" accept="video/*,.mp4,.mov,.webm,.mkv,.m4v" style="display:none" />
        <button class="admin-btn-sm" id="video-refresh" title="Refresh">↻</button>
        <button class="modal-close" id="video-close" aria-label="Close">×</button>
      </div>
      <div style="font-size:12px;opacity:.7;margin-bottom:10px;">Every video is analyzed locally — keyframes + speech transcript merge into a timestamped digest you can review here or ask about in chat (attach the video to a message).</div>
      <div id="video-body" style="overflow:auto;display:flex;flex-direction:column;gap:8px;">
        <div style="opacity:.6;padding:20px;text-align:center;">Loading…</div>
      </div>
    </div>`;
  document.body.appendChild(modal);
  _el('video-close').addEventListener('click', closePanel);
  _el('video-refresh').addEventListener('click', () => _load());
  _el('video-upload-btn').addEventListener('click', () => _el('video-upload-file').click());
  _el('video-upload-file').addEventListener('change', _upload);
  modal.addEventListener('click', (e) => { if (e.target === modal) closePanel(); });
  document.addEventListener('keydown', _onEsc);
  _load();
}

function _onEsc(e) { if (e.key === 'Escape' && _open) closePanel(); }

function closePanel() {
  _open = false;
  if (_poll) { clearInterval(_poll); _poll = null; }
  document.removeEventListener('keydown', _onEsc);
  const m = _el('video-modal');
  if (m) m.remove();
}

async function _upload(e) {
  const f = e.target.files && e.target.files[0];
  e.target.value = '';
  if (!f) return;
  const body = _el('video-body');
  if (body) body.insertAdjacentHTML('afterbegin',
    `<div style="opacity:.7;padding:8px;">Uploading “${_esc(f.name)}” (${_mb(f.size)})…</div>`);
  const fd = new FormData();
  fd.append('files', f);
  try {
    const r = await _api('/api/upload', { method: 'POST', body: fd });
    const d = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error((d.detail && JSON.stringify(d.detail)) || `HTTP ${r.status}`);
    // Analysis auto-kicks server-side on upload.
  } catch (err) {
    alert('Upload failed: ' + err.message);
  }
  _load();
}

async function _load() {
  const body = _el('video-body');
  if (!body) return;
  let d;
  try { d = await (await _api('/api/upload/videos')).json(); }
  catch (e) { body.innerHTML = '<div style="opacity:.6;padding:16px;">Could not load videos — hit ↻ to retry.</div>'; return; }
  const vids = d.videos || [];
  if (!vids.length) {
    body.innerHTML = '<div style="opacity:.6;padding:24px;text-align:center;">No videos yet — hit ⬆ Upload, or drop a video into chat.<br><span style="font-size:11px;">Analysis runs locally in the background; a 1h meeting takes ~20–30 min, short clips a minute or two.</span></div>';
    return;
  }
  body.innerHTML = '';
  let anyRunning = false;
  vids.forEach((v) => {
    const job = v.job || {};
    const running = job.status === 'queued' || job.status === 'running';
    if (running) anyRunning = true;
    const pct = Math.round(100 * (job.progress || 0));
    let chip;
    if (v.analyzed) chip = `<span style="color:#2ecc71;font-size:11px;">✓ analyzed · ${v.scenes} scenes · ${v.segments} speech segments${v.duration ? ' · ' + _mmss(v.duration) : ''}</span>`;
    else if (running) chip = `<span style="color:#e0a000;font-size:11px;">⚙ ${_esc(job.stage || 'working')} · ${pct}%</span>`;
    else if (job.status === 'error') chip = `<span style="color:var(--red,#ff5758);font-size:11px;" title="${_esc(job.error || '')}">✗ failed — hit Analyze to retry</span>`;
    else chip = '<span style="opacity:.6;font-size:11px;">not analyzed</span>';

    const row = document.createElement('div');
    row.style.cssText = 'border:1px solid var(--border,#333);border-radius:10px;padding:9px 12px;';
    row.innerHTML = `
      <div style="display:flex;align-items:center;gap:8px;">
        <span style="flex-shrink:0;">🎬</span>
        <div style="flex:1;min-width:0;">
          <div style="font-weight:600;font-size:12.5px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">${_esc(v.name)}</div>
          <div style="margin-top:2px;">${chip} <span style="opacity:.45;font-size:10.5px;">· ${_mb(v.size)}</span></div>
        </div>
        <button class="admin-btn-sm" data-act="analyze" title="${v.analyzed ? 'Re-analyze from scratch' : 'Analyze now'}">${v.analyzed ? '↻ Re-analyze' : '▶ Analyze'}</button>
        <button class="admin-btn-sm" data-act="digest" ${v.analyzed ? '' : 'disabled style="opacity:.4;"'} title="View the timestamped digest">📄 Digest</button>
      </div>
      <div class="video-digest-box" style="display:none;font-size:11.5px;white-space:pre-wrap;border-top:1px dashed var(--border,#333);margin-top:8px;padding-top:8px;max-height:300px;overflow:auto;"></div>`;
    row.querySelector('[data-act="analyze"]').addEventListener('click', async () => {
      await _api(`/api/upload/${encodeURIComponent(v.id)}/analyze-video?force=${v.analyzed ? 1 : 0}`, { method: 'POST' });
      _load();
    });
    row.querySelector('[data-act="digest"]').addEventListener('click', async () => {
      const box = row.querySelector('.video-digest-box');
      if (box.style.display !== 'none') { box.style.display = 'none'; return; }
      box.style.display = 'block';
      box.textContent = 'Loading digest…';
      try {
        const dd = await (await _api(`/api/upload/${encodeURIComponent(v.id)}/video-digest`)).json();
        const dig = dd.digest || {};
        const lines = [];
        (dig.scenes || []).forEach(s => lines.push(`[${_mmss(s.t)}] 👁 ${s.caption}`));
        if (dig.scenes && dig.scenes.length && dig.transcript && dig.transcript.length) lines.push('');
        (dig.transcript || []).forEach(s => lines.push(`[${_mmss(s.start)}] 🗣 ${s.text}`));
        box.textContent = lines.join('\n') || '(empty digest)';
      } catch (e) { box.textContent = 'Could not load the digest.'; }
    });
    body.appendChild(row);
  });
  // Auto-refresh while anything is processing.
  if (anyRunning && !_poll) _poll = setInterval(() => { if (_open) _load(); }, 5000);
  if (!anyRunning && _poll) { clearInterval(_poll); _poll = null; }
}

function togglePanel() { _open ? closePanel() : openPanel(); }
function isPanelOpen() { return _open; }

const videoHubModule = { openPanel, closePanel, togglePanel, isPanelOpen };
export default videoHubModule;
