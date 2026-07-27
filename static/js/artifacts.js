/**
 * artifacts.js — Claude-style live preview of generated HTML / SVG / React.
 *
 * Watches rendered markdown anywhere in the app (chat, Code board, Cowork,
 * Crew) for previewable code blocks (```html / ```svg / ```jsx / ```tsx,
 * or a fence whose body starts with <!DOCTYPE html> / <html / <svg). Each
 * gets a floating "Preview" chip; clicking POSTs the code to /api/artifacts
 * and opens the result in a sandboxed iframe panel. While the assistant is
 * still streaming into the same block, the panel live-refreshes (debounced),
 * so the page builds itself in front of you.
 *
 * Safety: the iframe uses sandbox WITHOUT allow-same-origin — the artifact
 * gets an opaque origin and cannot touch Pi's cookies/DOM/storage.
 */

const PREVIEW_LANGS = new Set(['html', 'htm', 'svg', 'jsx', 'tsx', 'react']);
const AUTO_OPEN_MIN_CHARS = 160;
const LIVE_REFRESH_MS = 1300;

let _panel = null;
let _iframe = null;
let _titleEl = null;
let _boundCode = null;     // the <code> element the panel is following
let _boundLang = 'html';
let _refreshTimer = null;
let _scanTimer = null;
let _observer = null;
const _seen = new WeakSet(); // code elements already given a chip
let _mobileWidth = false;

function _langOf(codeEl) {
  const m = (codeEl.className || '').match(/language-([a-z0-9]+)/i);
  if (m && PREVIEW_LANGS.has(m[1].toLowerCase())) return m[1].toLowerCase();
  const head = (codeEl.textContent || '').slice(0, 200).trimStart().toLowerCase();
  if (head.startsWith('<!doctype html') || head.startsWith('<html')) return 'html';
  if (head.startsWith('<svg')) return 'svg';
  return null;
}

function _titleFor(lang) {
  return lang === 'svg' ? 'SVG preview'
    : (lang === 'jsx' || lang === 'tsx' || lang === 'react') ? 'React preview'
    : 'Page preview';
}

async function _post(code, lang) {
  const res = await fetch('/api/artifacts', {
    method: 'POST',
    credentials: 'same-origin',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ code, lang, title: _titleFor(lang) }),
  });
  if (!res.ok) throw new Error('artifact create failed: ' + res.status);
  return res.json();
}

function _ensurePanel() {
  if (_panel) return _panel;
  const modal = document.createElement('div');
  modal.className = 'modal';
  modal.id = 'artifact-modal';
  modal.innerHTML = `
    <div class="modal-content artifact-panel">
      <div class="modal-header" style="display:flex;align-items:center;gap:8px;">
        <h4 id="artifact-title" style="margin:0;flex:1;display:flex;align-items:center;gap:8px;">Preview</h4>
        <button class="admin-btn-sm" id="artifact-device" title="Toggle phone width">📱</button>
        <button class="admin-btn-sm" id="artifact-refresh" title="Re-render from the code block">⟳</button>
        <button class="admin-btn-sm" id="artifact-open" title="Open in a new tab">↗</button>
        <button class="close-btn" id="artifact-close">✖</button>
      </div>
      <div class="artifact-frame-wrap">
        <iframe id="artifact-iframe" class="artifact-iframe"
          sandbox="allow-scripts allow-forms allow-modals allow-popups allow-downloads"
          referrerpolicy="no-referrer" title="Artifact preview"></iframe>
      </div>
      <div class="artifact-foot">Runs sandboxed — the preview can't see your Pi data. Live-updates while the model is still writing.</div>
    </div>`;
  document.body.appendChild(modal);
  _panel = modal;
  _iframe = modal.querySelector('#artifact-iframe');
  _titleEl = modal.querySelector('#artifact-title');
  modal.querySelector('#artifact-close').addEventListener('click', closePanel);
  modal.addEventListener('mousedown', (e) => { if (e.target === modal) closePanel(); });
  modal.querySelector('#artifact-refresh').addEventListener('click', () => _renderBound(true));
  modal.querySelector('#artifact-open').addEventListener('click', () => {
    if (_iframe && _iframe.dataset.url) window.open(_iframe.dataset.url, '_blank', 'noopener');
  });
  modal.querySelector('#artifact-device').addEventListener('click', () => {
    _mobileWidth = !_mobileWidth;
    _iframe.style.width = _mobileWidth ? '390px' : '100%';
    _iframe.style.margin = _mobileWidth ? '0 auto' : '0';
  });
  return modal;
}

function closePanel() {
  if (_refreshTimer) { clearTimeout(_refreshTimer); _refreshTimer = null; }
  _boundCode = null;
  if (_panel) _panel.remove();
  _panel = null; _iframe = null; _titleEl = null;
}

async function _renderBound(force) {
  if (!_boundCode || !_iframe) return;
  const code = _boundCode.textContent || '';
  if (!code.trim()) return;
  if (!force && _iframe.dataset.codeLen === String(code.length)) return; // unchanged
  try {
    const { url } = await _post(code, _boundLang);
    _iframe.dataset.url = url;
    _iframe.dataset.codeLen = String(code.length);
    _iframe.src = url;
  } catch (e) {
    console.warn('[artifacts] render failed', e);
    // Don't leave a blank iframe — tell the user it failed, with retry via ⟳.
    try {
      _iframe.removeAttribute('src');
      _iframe.srcdoc = '<body style="font:14px -apple-system,sans-serif;color:#b3261e;padding:18px;">'
        + 'Could not render this preview (the server may be busy). Use ⟳ to retry.</body>';
    } catch (_) {}
  }
}

function openArtifact(codeEl, lang) {
  _boundCode = codeEl;
  _boundLang = lang;
  _ensurePanel();
  _titleEl.innerHTML = `${_titleFor(lang)} <span class="artifact-lang-badge">${lang}</span>`;
  _iframe.dataset.codeLen = '';
  _renderBound(true);
}

function _scheduleLiveRefresh() {
  if (!_panel || !_boundCode || !_boundCode.isConnected) return;
  if (_refreshTimer) clearTimeout(_refreshTimer);
  _refreshTimer = setTimeout(() => { _refreshTimer = null; _renderBound(false); }, LIVE_REFRESH_MS);
}

function _addChip(pre, codeEl, lang) {
  if (pre.querySelector('.artifact-chip')) return;
  const btn = document.createElement('button');
  btn.type = 'button';
  btn.className = 'artifact-chip';
  btn.textContent = '▶ Preview';
  btn.title = 'Render this code live in a sandboxed window';
  btn.addEventListener('click', (e) => {
    e.preventDefault();
    e.stopPropagation();
    openArtifact(codeEl, _langOf(codeEl) || lang);
  });
  pre.classList.add('artifact-host');
  pre.appendChild(btn);
}

function _scan() {
  _scanTimer = null;
  const pres = document.querySelectorAll('pre > code');
  for (const codeEl of pres) {
    const lang = _langOf(codeEl);
    if (!lang) continue;
    const pre = codeEl.parentElement;
    _addChip(pre, codeEl, lang);
    if (!_seen.has(codeEl)) {
      _seen.add(codeEl);
      // Auto-open Claude-style: only for fresh assistant chat output of real size.
      const inAssistantMsg = !!codeEl.closest('.msg-ai');
      const isLastMsg = inAssistantMsg && !codeEl.closest('.msg-ai').nextElementSibling;
      if (inAssistantMsg && isLastMsg && (codeEl.textContent || '').length >= AUTO_OPEN_MIN_CHARS) {
        openArtifact(codeEl, lang);
      }
    }
  }
  // The bound block may still be streaming — keep the panel fresh.
  if (_panel && _boundCode && _boundCode.isConnected) _scheduleLiveRefresh();
}

function _queueScan() {
  if (_scanTimer) return;
  _scanTimer = setTimeout(_scan, 600);
}

function init() {
  if (_observer) return;
  _observer = new MutationObserver((muts) => {
    for (const m of muts) {
      if (m.type === 'childList' && (m.addedNodes.length || m.removedNodes.length)) { _queueScan(); return; }
      if (m.type === 'characterData') { _queueScan(); return; }
    }
  });
  _observer.observe(document.body, { childList: true, subtree: true, characterData: true });
  _queueScan();
}

const artifactsModule = { init, openArtifact, closePanel };
export default artifactsModule;
window.artifactsModule = artifactsModule;
