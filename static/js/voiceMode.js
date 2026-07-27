/**
 * voiceMode.js — hands-free voice conversation with Pi.
 *
 * Loop: listen (mic + simple energy VAD) → transcribe (/api/stt/transcribe,
 * local Whisper) → send through the normal chat pipeline (so Brain/tools/
 * model picker all apply) → wait for the reply to finish streaming → speak
 * it aloud (/api/tts/synthesize, local Kokoro) → listen again. Everything
 * runs on-device; nothing leaves the Mac.
 *
 * Exit: the Stop button, Esc, or clicking the composer voice button again.
 */

const SILENCE_MS = 1400;      // stop recording after this much quiet
const MIN_SPEECH_MS = 400;    // ignore blips shorter than this
const MAX_UTTERANCE_MS = 20000;
const RMS_THRESHOLD = 0.012;  // speech energy gate
const REPLY_TIMEOUT_MS = 5 * 60 * 1000;
const TTS_MAX_CHARS = 1400;

let _active = false;
let _status = 'idle';         // listening | thinking | speaking
let _muted = false;
let _overlay = null;
let _stream = null;
let _recorder = null;
let _audioCtx = null;
let _vadTimer = null;
let _audioEl = null;
let _abortLoop = false;

function _el(id) { return document.getElementById(id); }

function _setStatus(s, detail) {
  _status = s;
  if (!_overlay) return;
  const dot = _overlay.querySelector('.voice-dot');
  const label = _overlay.querySelector('.voice-status');
  const det = _overlay.querySelector('.voice-detail');
  dot.className = 'voice-dot ' + s;
  label.textContent = s === 'listening' ? 'Listening…'
    : s === 'thinking' ? 'Thinking…'
    : s === 'speaking' ? 'Speaking…' : '';
  if (detail !== undefined) det.textContent = detail || '';
}

function _ensureOverlay() {
  if (_overlay) return _overlay;
  const o = document.createElement('div');
  o.className = 'voice-overlay';
  o.id = 'voice-overlay';
  o.innerHTML = `
    <div class="voice-card">
      <span class="voice-dot listening"></span>
      <div class="voice-texts">
        <div class="voice-status">Listening…</div>
        <div class="voice-detail"></div>
      </div>
      <button class="voice-mute" id="voice-mute-btn" title="Mute spoken replies">🔊</button>
      <button class="voice-stop" id="voice-stop-btn" title="End voice conversation">✖</button>
    </div>`;
  document.body.appendChild(o);
  o.querySelector('#voice-stop-btn').addEventListener('click', stop);
  o.querySelector('#voice-mute-btn').addEventListener('click', (e) => {
    _muted = !_muted;
    e.currentTarget.textContent = _muted ? '🔇' : '🔊';
    if (_muted && _audioEl) { try { _audioEl.pause(); } catch (err) {} }
  });
  _overlay = o;
  return o;
}

async function _record() {
  // One utterance: resolves with a Blob (or null if aborted/empty).
  return new Promise((resolve) => {
    let chunks = [];
    let speechMs = 0;
    let silentMs = 0;
    let started = Date.now();
    let lastTick = Date.now();
    const mime = MediaRecorder.isTypeSupported('audio/webm') ? 'audio/webm' : '';
    _recorder = new MediaRecorder(_stream, mime ? { mimeType: mime } : undefined);
    _recorder.ondataavailable = (e) => { if (e.data && e.data.size) chunks.push(e.data); };
    _recorder.onstop = () => {
      const hadSpeech = speechMs >= MIN_SPEECH_MS;
      resolve(hadSpeech && chunks.length ? new Blob(chunks, { type: mime || 'audio/webm' }) : null);
    };
    _recorder.start(250);

    const src = _audioCtx.createMediaStreamSource(_stream);
    const analyser = _audioCtx.createAnalyser();
    analyser.fftSize = 1024;
    src.connect(analyser);
    const buf = new Float32Array(analyser.fftSize);

    const tick = () => {
      if (_abortLoop || !_recorder || _recorder.state !== 'recording') {
        try { src.disconnect(); } catch (e) {}
        return;
      }
      analyser.getFloatTimeDomainData(buf);
      let sum = 0;
      for (let i = 0; i < buf.length; i++) sum += buf[i] * buf[i];
      const rms = Math.sqrt(sum / buf.length);
      const now = Date.now();
      const dt = now - lastTick;
      lastTick = now;
      if (rms > RMS_THRESHOLD) { speechMs += dt; silentMs = 0; }
      else if (speechMs > 0) { silentMs += dt; }

      const tooLong = now - started > MAX_UTTERANCE_MS;
      const doneTalking = speechMs >= MIN_SPEECH_MS && silentMs >= SILENCE_MS;
      if (tooLong || doneTalking) {
        try { src.disconnect(); } catch (e) {}
        try { _recorder.stop(); } catch (e) { resolve(null); }
        return;
      }
      _vadTimer = setTimeout(tick, 80);
    };
    tick();
  });
}

async function _transcribe(blob) {
  const fd = new FormData();
  fd.append('file', blob, 'voice.webm');
  const res = await fetch('/api/stt/transcribe', { method: 'POST', credentials: 'same-origin', body: fd });
  if (!res.ok) {
    let msg = 'transcription failed';
    try { msg = (await res.json()).detail?.message || msg; } catch (e) {}
    throw new Error(msg);
  }
  const data = await res.json();
  return (data.text || '').trim();
}

function _sendToChat(text) {
  const ta = _el('message');
  if (!ta || !window.chatModule) throw new Error('chat not ready');
  ta.value = text;
  ta.dispatchEvent(new Event('input'));
  const ev = new Event('submit', { cancelable: true });
  window.chatModule.handleChatSubmit(ev);
}

async function _waitForReply() {
  const t0 = Date.now();
  // Give the stream a moment to register, then poll until it ends.
  await new Promise(r => setTimeout(r, 800));
  while (!_abortLoop) {
    let active = false;
    try { active = !!window.chatModule.hasActiveStream(window.sessionModule?.getCurrentSessionId?.()); } catch (e) {}
    if (!active) break;
    if (Date.now() - t0 > REPLY_TIMEOUT_MS) break;
    await new Promise(r => setTimeout(r, 400));
  }
  await new Promise(r => setTimeout(r, 300)); // let the DOM settle
  const msgs = document.querySelectorAll('#chat-history .msg-ai .body');
  if (!msgs.length) return '';
  const clone = msgs[msgs.length - 1].cloneNode(true);
  // Don't read code, tool threads or sources aloud.
  clone.querySelectorAll('pre, .agent-thread-node, .agent-tool-output, .sources-box, table').forEach(n => n.remove());
  return (clone.textContent || '').replace(/\s+/g, ' ').trim();
}

async function _speak(text) {
  if (_muted || !text) return;
  const trimmed = text.length > TTS_MAX_CHARS ? text.slice(0, TTS_MAX_CHARS) + '…' : text;
  let data;
  try {
    const res = await fetch('/api/tts/synthesize', {
      method: 'POST',
      credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text: trimmed, format: 'base64' }),
    });
    if (!res.ok) return; // TTS off — stay text-only, keep the loop going
    data = await res.json();
  } catch (e) { return; }
  if (!data || !data.audio) return;
  await new Promise((resolve) => {
    _audioEl = new Audio('data:audio/wav;base64,' + data.audio);
    _audioEl.onended = resolve;
    _audioEl.onerror = resolve;
    _audioEl.play().catch(resolve);
  });
  _audioEl = null;
}

async function _loop() {
  while (!_abortLoop) {
    _setStatus('listening', 'Speak — I stop listening when you pause.');
    let blob = null;
    try { blob = await _record(); } catch (e) { break; }
    if (_abortLoop) break;
    if (!blob) continue; // silence — keep listening

    _setStatus('thinking', 'Transcribing…');
    let text = '';
    try { text = await _transcribe(blob); } catch (e) {
      _setStatus('listening', 'Could not transcribe — try again.');
      continue;
    }
    if (!text) continue;
    _setStatus('thinking', '“' + text.slice(0, 80) + (text.length > 80 ? '…' : '') + '”');

    try { _sendToChat(text); } catch (e) { break; }
    const reply = await _waitForReply();
    if (_abortLoop) break;

    if (reply) {
      _setStatus('speaking', reply.slice(0, 90) + (reply.length > 90 ? '…' : ''));
      await _speak(reply);
    }
  }
  stop();
}

export async function start() {
  if (_active) { stop(); return; }
  if (!navigator.mediaDevices || !window.MediaRecorder) {
    if (window.uiModule && window.uiModule.showError) window.uiModule.showError('This browser cannot record audio.');
    return;
  }
  try {
    _stream = await navigator.mediaDevices.getUserMedia({ audio: true });
  } catch (e) {
    if (window.uiModule && window.uiModule.showError) window.uiModule.showError('Microphone permission denied.');
    return;
  }
  _active = true;
  _abortLoop = false;
  _audioCtx = new (window.AudioContext || window.webkitAudioContext)();
  _ensureOverlay();
  const btn = _el('voice-mode-btn');
  if (btn) btn.classList.add('voice-active');
  document.addEventListener('keydown', _escHandler);
  _loop();
}

function _escHandler(e) {
  if (e.key === 'Escape' && _active) stop();
}

export function stop() {
  if (!_active && !_overlay) return;
  _abortLoop = true;
  _active = false;
  document.removeEventListener('keydown', _escHandler);
  if (_vadTimer) { clearTimeout(_vadTimer); _vadTimer = null; }
  try { if (_recorder && _recorder.state === 'recording') _recorder.stop(); } catch (e) {}
  _recorder = null;
  if (_audioEl) { try { _audioEl.pause(); } catch (e) {} _audioEl = null; }
  if (_stream) { _stream.getTracks().forEach(t => t.stop()); _stream = null; }
  if (_audioCtx) { try { _audioCtx.close(); } catch (e) {} _audioCtx = null; }
  if (_overlay) { _overlay.remove(); _overlay = null; }
  const btn = _el('voice-mode-btn');
  if (btn) btn.classList.remove('voice-active');
}

export function isActive() { return _active; }

const voiceModeModule = { start, stop, isActive };
export default voiceModeModule;
window.voiceModeModule = voiceModeModule;
