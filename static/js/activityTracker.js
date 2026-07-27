// static/js/activityTracker.js — client-side user interaction logging for QA/testing.
// Tracks clicks, text input, navigation, and chat messages, writing them to the backend log.

let _enabled = localStorage.getItem('user_activity_tracking_enabled') === 'true';

const API_BASE = window.location.origin;

function isEnabled() {
  return _enabled;
}

function setEnabled(val) {
  _enabled = !!val;
  localStorage.setItem('user_activity_tracking_enabled', _enabled ? 'true' : 'false');
  log('tracking_state_changed', { enabled: _enabled });
  updateFloatingIndicator();
  
  // Sync the checkbox UI if it exists
  const checkbox = document.getElementById('set-user-activity-tracking');
  if (checkbox) checkbox.checked = _enabled;
}

async function log(eventType, details) {
  if (!_enabled && eventType !== 'tracking_state_changed') return;
  
  try {
    await fetch(`${API_BASE}/api/user-activity/log`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        event_type: eventType,
        details: details || {}
      })
    });
  } catch (e) {
    console.error('Failed to log user activity:', e);
  }
}

// Visual indicator of active logging (pulsing dot + text)
function updateFloatingIndicator() {
  let indicator = document.getElementById('activity-tracking-indicator');
  if (_enabled) {
    if (!indicator) {
      indicator = document.createElement('div');
      indicator.id = 'activity-tracking-indicator';
      indicator.innerHTML = `
        <span class="pulse-dot"></span>
        <span style="font-size: 11px; font-weight: 500;">Activity Logging Active</span>
      `;
      indicator.style.cssText = `
        position: fixed;
        bottom: 20px;
        right: 20px;
        background: rgba(20, 24, 33, 0.85);
        backdrop-filter: blur(8px);
        -webkit-backdrop-filter: blur(8px);
        border: 1px solid rgba(46, 204, 113, 0.4);
        color: #2ecc71;
        padding: 8px 14px;
        border-radius: 999px;
        display: flex;
        align-items: center;
        gap: 8px;
        z-index: 10000;
        box-shadow: 0 4px 20px rgba(0,0,0,0.3);
        pointer-events: none;
        transition: opacity 0.3s ease;
      `;
      
      if (!document.getElementById('pulse-dot-style')) {
        const style = document.createElement('style');
        style.id = 'pulse-dot-style';
        style.textContent = `
          .pulse-dot {
            width: 8px;
            height: 8px;
            background: #2ecc71;
            border-radius: 50%;
            animation: pulse 1.8s infinite;
          }
          @keyframes pulse {
            0% { transform: scale(0.95); box-shadow: 0 0 0 0 rgba(46, 204, 113, 0.7); }
            70% { transform: scale(1); box-shadow: 0 0 0 6px rgba(46, 204, 113, 0); }
            100% { transform: scale(0.95); box-shadow: 0 0 0 0 rgba(46, 204, 113, 0); }
          }
        `;
        document.head.appendChild(style);
      }
      document.body.appendChild(indicator);
    }
  } else {
    if (indicator) {
      indicator.remove();
    }
  }
}

// Clear backend logs
async function clearLogs() {
  try {
    const res = await fetch(`${API_BASE}/api/user-activity/clear`, { method: 'POST' });
    return res.ok;
  } catch (e) {
    console.error('Failed to clear logs:', e);
    return false;
  }
}

function init() {
  updateFloatingIndicator();
  
  // Track clicks
  document.addEventListener('click', (e) => {
    if (!_enabled) return;
    
    // Ignore clicks on indicator itself
    if (e.target.closest('#activity-tracking-indicator')) return;
    
    const interactive = e.target.closest('button, a, input, select, textarea, [role="button"], .tab, .btn, .vis-row');
    if (!interactive) return;
    
    const tag = interactive.tagName.toLowerCase();
    const id = interactive.id ? `#${interactive.id}` : '';
    const classes = interactive.className && typeof interactive.className === 'string'
      ? '.' + interactive.className.trim().replace(/\s+/g, '.')
      : '';
    const text = interactive.innerText ? interactive.innerText.trim().slice(0, 100) : '';
    const name = interactive.getAttribute('name') || '';
    const placeholder = interactive.getAttribute('placeholder') || '';
    const type = interactive.getAttribute('type') || '';
    
    log('click', {
      element: `${tag}${id}${classes}`,
      text: text,
      name: name,
      placeholder: placeholder,
      type: type,
      url: window.location.origin + window.location.pathname
    });
  }, true);
  
  // Track text changes (1s debounce)
  let inputTimeout;
  document.addEventListener('input', (e) => {
    if (!_enabled) return;
    
    const target = e.target;
    if (target.tagName !== 'INPUT' && target.tagName !== 'TEXTAREA') return;
    if (target.type === 'password') return;
    
    clearTimeout(inputTimeout);
    inputTimeout = setTimeout(() => {
      const id = target.id ? `#${target.id}` : '';
      const name = target.getAttribute('name') || '';
      const type = target.getAttribute('type') || 'text';
      const val = target.value || '';
      
      log('input_change', {
        element: `${target.tagName.toLowerCase()}${id}`,
        name: name,
        type: type,
        value_length: val.length,
        value: val.length > 300 ? val.slice(0, 300) + '...' : val
      });
    }, 1000);
  }, true);
  
  // Track URL history changes
  window.addEventListener('popstate', () => {
    if (!_enabled) return;
    log('navigation', { url: window.location.origin + window.location.pathname });
  });

  // Track frontend errors
  window.addEventListener('error', (e) => {
    if (!_enabled) return;
    log('frontend_error', {
      message: e.message || 'Unknown error',
      source: e.filename ? e.filename.split('/').pop() : 'unknown',
      line: e.lineno || 0,
      col: e.colno || 0,
      stack: e.error && e.error.stack ? e.error.stack.slice(0, 300) : ''
    });
  });

  // Track promise rejections
  window.addEventListener('unhandledrejection', (e) => {
    if (!_enabled) return;
    const reason = e.reason;
    log('frontend_error', {
      message: reason && reason.message ? reason.message : String(reason || 'Unhandled promise rejection'),
      source: 'promise_rejection',
      stack: reason && reason.stack ? reason.stack.slice(0, 300) : ''
    });
  });
}

// Run init
init();

export default {
  isEnabled,
  setEnabled,
  log,
  clearLogs,
  init
};
