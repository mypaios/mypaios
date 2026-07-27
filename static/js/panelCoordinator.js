// static/js/panelCoordinator.js
// ──────────────────────────────────────────────────────────────────────────
// Single-active panel coordinator (Pattern A — "one screen at a time").
//
// PROBLEM it fixes: every tool in MyPaiOS opens as a floating `.modal` over the
// permanent chat. Opening a second tool used to STACK on the first and — due to
// three competing z-index writers (ui.js _zCounter @1000 no-important, ui.js
// click-to-front @250, modalManager _modalTopZ @300 !important) — could even
// render UNDERNEATH it. The user's words:
//   "when i open tab it goes under previous tab ... popups all the time".
//
// WHAT it does, universally, with ZERO per-panel edits — by keying off the
// `.modal` convention every tool already shares:
//   1. SINGLE-ACTIVE: when a known TOOL panel becomes visible, every OTHER open
//      tool panel is closed via its own close affordance (so each module's
//      internal open flag stays in sync). Only one tool occupies the chat area.
//   2. SCREEN FRAME: the active tool gets a `panel-screen` class; style.css then
//      sizes it to fill the chat-area region with an opaque background, so it
//      reads as a dedicated SCREEN instead of a floating popup over chat.
//   3. AUTHORITATIVE Z: a single counter (tool band) makes the active tool the
//      top tool, so "goes under" can never happen again. A second counter keeps
//      transient dialogs (rename / confirm / audit) above tools as before.
//
// Chat stays the permanent home: closing/Esc-ing the active tool, clicking its
// rail button again, or Cmd/Ctrl+1 returns straight to chat.
//
// DELIBERATE EXCEPTIONS (left entirely alone):
//   • The email family (email-lib-modal + email-reader-*) — a genuine
//     multi-window surface with its own coexistence logic.
//   • styled-confirm-overlay / styled-prompt-overlay — pinned to z 99999 in
//     CSS; we must not lower them with an inline !important.
//   • Anything carrying `.panel-exempt`.
// Transient dialogs (rename-session-modal, custom-preset-modal, the skills
// audit confirm, etc.) are NOT tools, so they layer ON TOP of a tool without
// closing it.
// ──────────────────────────────────────────────────────────────────────────

import * as Modals from './modalManager.js';

// Top-level TOOL panels that participate in single-active + screen framing.
const TOOL_IDS = new Set([
  'agentshub-modal', 'localai-modal', 'agents-modal', 'crew-modal', 'cowork-modal',
  'code-modal', 'activity-modal', 'storage-modal', 'mailguard-modal',
  'settings-modal', 'memory-modal', 'gallery-modal', 'tasks-modal', 'calendar-modal',
  'cookbook-modal', 'doclib-modal', 'research-overlay', 'library-modal',
  'help-modal', 'video-modal',
]);
// Note: theme-modal (quick color picker) and artifact-modal (live preview, meant
// to sit over chat) are intentionally NOT tools — they stay lightweight floating
// utilities, but still get the dialog z-band so they never render under a tool.

// `.modal` dialogs that own a high CSS z-index — never re-promote (an inline
// !important would override and LOWER their stylesheet !important value).
const DIALOG_SKIP = new Set(['styled-confirm-overlay', 'styled-prompt-overlay']);

const MODE_KEY = 'paios-single-panel';

const singleMode = () => document.body.classList.contains('single-panel-mode');
const isModal = (m) => !!m && m.nodeType === 1 && m.classList && m.classList.contains('modal');
const isVisible = (m) =>
  !m.classList.contains('hidden') &&
  !m.classList.contains('modal-minimized') &&
  getComputedStyle(m).display !== 'none';
const isEmailFamily = (m) => m.id === 'email-lib-modal' || (m.id || '').startsWith('email-reader-');
const isParticipant = (m) =>
  isModal(m) && !m.classList.contains('panel-exempt') &&
  (TOOL_IDS.has(m.id) || m.classList.contains('panel-tool'));

let _topZ = 900;       // tool band — above static modal z's (260/300), below dialogs
let _dialogZ = 9500;   // dialog band — above any tool, below toasts(9999)/menus

function bringToFront(m) {
  const cur = parseInt(m.style.zIndex, 10) || 0;
  if (cur === _topZ) return;                 // already top → no-op (loop guard)
  m.style.setProperty('z-index', String(++_topZ), 'important');
}

function promoteDialog(m) {
  const cur = parseInt(m.style.zIndex, 10) || 0;
  if (cur === _dialogZ) return;
  m.style.setProperty('z-index', String(++_dialogZ), 'important');
}

// Close a peer tool the same way the user would, so its module resets state.
function closePanel(m) {
  const id = m.id || '';
  const btn = m.querySelector('.modal-close, .close-btn, [data-close], [aria-label="Close"]');
  if (btn) { try { btn.click(); return; } catch (_) {} }
  try { if (id && Modals.isRegistered && Modals.isRegistered(id)) { Modals.close(id); return; } } catch (_) {}
  m.classList.add('hidden');
  m.style.display = '';
  try { window.dispatchEvent(new CustomEvent('modal-dismissed', { detail: { id } })); } catch (_) {}
}

function activate(m) {
  if (!isParticipant(m) || !isVisible(m)) return;
  const cur = parseInt(m.style.zIndex, 10) || 0;
  const others = [...document.querySelectorAll('.modal')]
    .filter(o => o !== m && isParticipant(o) && isVisible(o));
  // Idempotent: if already framed, top of the tool band, and the sole open
  // tool, there's nothing to do — this stops our own class/style mutations
  // from re-triggering the observer into a loop.
  const settled = m.classList.contains('panel-screen') && cur === _topZ
    && (!singleMode() || others.length === 0);
  if (settled) return;
  m.classList.add('panel-screen');
  bringToFront(m);
  if (singleMode()) others.forEach(closePanel);
  try { window.dispatchEvent(new CustomEvent('paios:panel-activated', { detail: { id: m.id } })); } catch (_) {}
}

function handle(m) {
  if (!isModal(m) || !isVisible(m)) return;
  if (isParticipant(m)) { activate(m); return; }
  if (isEmailFamily(m) || DIALOG_SKIP.has(m.id)) return;
  promoteDialog(m);                           // generic dialog → keep above tools
}

function activeTool() {
  return [...document.querySelectorAll('.modal')].find(m => isParticipant(m) && isVisible(m)) || null;
}

export function closeActive() {
  const m = activeTool();
  if (m) closePanel(m);
}

function scan() { document.querySelectorAll('.modal').forEach(handle); }

function init() {
  let on = true;
  try { on = localStorage.getItem(MODE_KEY) !== '0'; } catch (_) {}
  document.body.classList.toggle('single-panel-mode', on);

  new MutationObserver((muts) => {
    for (const mu of muts) {
      if (mu.type === 'childList') {
        mu.addedNodes.forEach(n => { if (isModal(n)) handle(n); });
      } else if (mu.type === 'attributes' && isModal(mu.target)) {
        handle(mu.target);
      }
    }
  }).observe(document.body, { childList: true, subtree: true, attributes: true, attributeFilter: ['class', 'style'] });
  scan();

  // Cmd/Ctrl+1 → jump home (close the active tool, revealing chat).
  document.addEventListener('keydown', (e) => {
    if ((e.metaKey || e.ctrlKey) && e.key === '1') {
      const m = activeTool();
      if (m) { e.preventDefault(); closePanel(m); }
    }
  });

  // Click a background window to raise it (replaces ui.js's old click-to-front).
  document.addEventListener('mousedown', (e) => {
    const content = e.target.closest && e.target.closest('.modal-content');
    if (!content) return;
    const modal = content.closest('.modal');
    if (!modal || !isVisible(modal)) return;
    if (isParticipant(modal)) bringToFront(modal);
    else if (isModal(modal) && !isEmailFamily(modal) && !DIALOG_SKIP.has(modal.id)) promoteDialog(modal);
  });
}

export function setSinglePanelMode(on) {
  try { localStorage.setItem(MODE_KEY, on ? '1' : '0'); } catch (_) {}
  document.body.classList.toggle('single-panel-mode', !!on);
  scan();
}

if (typeof window !== 'undefined') {
  window.PanelMode = { closeActive, set: setSinglePanelMode, activeTool };
  if (document.body) init();
  else document.addEventListener('DOMContentLoaded', () => init(), { once: true });
}

export default { closeActive, setSinglePanelMode };
