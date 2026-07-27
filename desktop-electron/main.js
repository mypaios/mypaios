'use strict';
/*
 * MyPaiOS — Electron desktop shell.
 *
 * Wraps the local FastAPI server (Pi) in a native desktop window with bundled
 * Chromium (identical rendering on macOS + Windows). This shell:
 *   - spawns the Python backend (repo venv uvicorn) — or reuses one already up,
 *   - shows a branded loading splash while the server (and first-run model) boot,
 *   - loads the Pi UI once ready,
 *   - stops the backend it started when the app quits,
 *   - enforces single-instance, routes external links to the OS browser,
 *   - installs a standard app menu.
 *
 * NOTE: this dev build spawns the repo's existing venv. For a distributable
 * (no Python required by the user) the backend is bundled as a PyInstaller
 * sidecar via electron-builder extraResources — see task #20 / README.
 */
const { app, BrowserWindow, Menu, shell, dialog } = require('electron');
const { spawn } = require('child_process');
const path = require('path');
const net = require('net');

// In dev the repo is the parent of desktop-electron/. When packaged (.app),
// __dirname is inside the bundle, so fall back to the known repo path. The
// persistent launchd backend means the packaged app normally just reuses :7860
// (it only needs REPO/venv if it has to start the server itself).
const REPO = process.env.PAIOS_REPO || path.resolve(__dirname, '..');
const HOST = '127.0.0.1';
const PORT = parseInt(process.env.PAIOS_PORT || process.env.APP_PORT || '7860', 10);
const APP_URL = `http://${HOST}:${PORT}`;

let mainWindow = null;
let backend = null;
let startedBackend = false;

// ── Error logging ──────────────────────────────────────────────────────────
// Everything the shell does (and every crash it can catch) is appended to
// logs/piaos-electron.log so failures are diagnosable instead of a silent
// "quit unexpectedly". Read it with:  tail -f "<repo>/logs/piaos-electron.log"
const fs = require('fs');
const LOG_FILE = path.join(REPO, 'logs', 'piaos-electron.log');
function logMain(...args) {
  const fmt = (a) => (a && a.stack) ? a.stack
    : (a && typeof a === 'object' ? (() => { try { return JSON.stringify(a); } catch (_) { return String(a); } })()
    : String(a));
  const line = `[${new Date().toISOString()}] ${args.map(fmt).join(' ')}\n`;
  try { fs.mkdirSync(path.dirname(LOG_FILE), { recursive: true }); fs.appendFileSync(LOG_FILE, line); } catch (_) {}
  try { process.stdout.write(line); } catch (_) {}
}
process.on('uncaughtException', (err) => logMain('FATAL uncaughtException:', err));
process.on('unhandledRejection', (reason) => logMain('unhandledRejection:', reason));
app.on('child-process-gone', (_e, details) => logMain('child-process-gone:', details));
app.on('render-process-gone', (_e, _wc, details) => logMain('render-process-gone(app):', details));
logMain('=== MyPaiOS shell starting ===',
  '| pid', process.pid, '| packaged', app.isPackaged,
  '| electron', process.versions.electron, '| REPO', REPO, '| URL', APP_URL);

function venvPython() {
  return process.platform === 'win32'
    ? path.join(REPO, 'venv', 'Scripts', 'python.exe')
    : path.join(REPO, 'venv', 'bin', 'python');
}

function portOpen(timeout = 1000) {
  return new Promise((resolve) => {
    const sock = new net.Socket();
    let settled = false;
    const done = (v) => { if (!settled) { settled = true; sock.destroy(); resolve(v); } };
    sock.setTimeout(timeout);
    sock.once('connect', () => done(true));
    sock.once('timeout', () => done(false));
    sock.once('error', () => done(false));
    sock.connect(PORT, HOST);
  });
}

async function waitForServer(maxSec = 180) {
  for (let i = 0; i < maxSec; i++) {
    if (await portOpen()) return true;
    if (startedBackend && backend === null) return false; // backend died early
    await new Promise((r) => setTimeout(r, 1000));
  }
  return false;
}

function startBackend() {
  const py = venvPython();
  logMain('startBackend: spawning', py, '-m uvicorn on', `${HOST}:${PORT}`, '| cwd', REPO);
  backend = spawn(
    py,
    ['-m', 'uvicorn', 'app:app', '--host', HOST, '--port', String(PORT)],
    {
      cwd: REPO,
      env: Object.assign({}, process.env, { CHROMADB_MODE: process.env.CHROMADB_MODE || 'embedded' }),
      stdio: ['ignore', 'pipe', 'pipe'],
    }
  );
  startedBackend = true;
  if (backend.stdout) backend.stdout.on('data', (d) => logMain('[backend]', String(d).trimEnd()));
  if (backend.stderr) backend.stderr.on('data', (d) => logMain('[backend:err]', String(d).trimEnd()));
  backend.on('error', (e) => logMain('startBackend: spawn error:', e));
  backend.on('exit', (code, sig) => { logMain('backend exited — code', code, 'signal', sig); backend = null; });
}

function stopBackend() {
  if (backend && !backend.killed) {
    try { backend.kill(); } catch (e) { /* ignore */ }
  }
  backend = null;
}

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1280,
    height: 860,
    minWidth: 900,
    minHeight: 600,
    title: 'MyPaiOS',
    backgroundColor: '#2E333D',
    show: false,
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });
  mainWindow.loadFile(path.join(__dirname, 'loading.html'));
  mainWindow.once('ready-to-show', () => mainWindow.show());
  mainWindow.webContents.on('did-fail-load', (_e, code, desc, url) =>
    logMain('did-fail-load:', code, desc, url));
  mainWindow.webContents.on('render-process-gone', (_e, details) =>
    logMain('render-process-gone:', details));
  mainWindow.webContents.on('unresponsive', () => logMain('window unresponsive'));
  // Open target=_blank / external links in the OS browser, not a new app window.
  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    shell.openExternal(url);
    return { action: 'deny' };
  });
  mainWindow.on('closed', () => { mainWindow = null; });
}

async function boot() {
  try {
    logMain('boot: start');
    if (!mainWindow) createWindow();
    const up = await portOpen();
    logMain('boot: port', PORT, 'already open?', up);
    if (!up) startBackend();
    const ok = await waitForServer();
    logMain('boot: server ready?', ok);
    if (!mainWindow) return;
    if (ok) {
      mainWindow.webContents.session.clearStorageData({
        storages: ['serviceworkers', 'cachestorage']
      }).then(() => {
        mainWindow.loadURL(APP_URL);
        logMain('boot: loaded', APP_URL);
      }).catch((err) => {
        logMain('boot: error clearing storage', err);
        mainWindow.loadURL(APP_URL);
      });
    } else {
      logMain('boot: server did NOT start in time');
      dialog.showErrorBox(
        'MyPaiOS',
        'The Pi server did not start in time.\n\nMake sure the Python env is set up:\n' +
        '  cd "' + REPO + '"\n  ./venv/bin/python -m uvicorn app:app\n\nSee README for setup.'
      );
    }
  } catch (e) {
    logMain('boot: ERROR', e);
  }
}

function buildMenu() {
  const isMac = process.platform === 'darwin';
  const template = [
    ...(isMac ? [{ role: 'appMenu' }] : []),
    { label: 'File', submenu: [isMac ? { role: 'close' } : { role: 'quit' }] },
    { role: 'editMenu' },
    {
      label: 'View',
      submenu: [
        { label: 'Home', accelerator: 'CmdOrCtrl+Shift+H', click: () => mainWindow && mainWindow.loadURL(APP_URL) },
        { role: 'reload' },
        { role: 'forceReload' },
        { type: 'separator' },
        { role: 'resetZoom' },
        { role: 'zoomIn' },
        { role: 'zoomOut' },
        { type: 'separator' },
        { role: 'togglefullscreen' },
        { role: 'toggleDevTools' },
      ],
    },
    { role: 'windowMenu' },
    {
      role: 'help',
      submenu: [
        { label: 'MyPaiOS Help Guide', click: () => shell.openExternal('http://127.0.0.1:7860/help') },
      ],
    },
  ];
  return Menu.buildFromTemplate(template);
}

if (!app.requestSingleInstanceLock()) {
  app.quit();
} else {
  app.on('second-instance', () => {
    if (mainWindow) {
      if (mainWindow.isMinimized()) mainWindow.restore();
      mainWindow.focus();
    }
  });
  app.whenReady().then(() => {
    // Show the MyPaiOS icon in the macOS Dock (dev runs show the generic
    // Electron icon otherwise). A packaged .app embeds this via electron-builder.
    if (process.platform === 'darwin' && app.dock) {
      try { app.dock.setIcon(path.join(__dirname, 'assets', 'icon.png')); } catch (e) { /* ignore */ }
    }
    Menu.setApplicationMenu(buildMenu());
    boot();
    app.on('activate', () => { if (mainWindow === null) boot(); });
  });
  app.on('window-all-closed', () => {
    stopBackend();
    if (process.platform !== 'darwin') app.quit();
  });
  app.on('before-quit', () => stopBackend());
}
