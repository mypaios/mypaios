'use strict';
// Minimal, secure preload. contextIsolation is ON and nodeIntegration is OFF.
// Pi's UI is served by the local FastAPI server and needs no Node/Electron APIs,
// so we intentionally expose nothing here. Add a narrow contextBridge API later
// only if the UI needs native features (e.g. file dialogs, notifications).
