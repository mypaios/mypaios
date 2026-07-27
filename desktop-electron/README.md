# MyPaiOS — Desktop (Electron)

Native desktop shell for **Pi**. Bundles Chromium for pixel-identical rendering
on macOS + Windows, spawns the Python backend, and shows the UI in a real app
window (branded splash, app menu, single-instance, lifecycle management).

## Run (dev)
Prereqs: the repo `../venv` is set up and Ollama is running.

```bash
cd desktop-electron
npm install      # once
npm start        # launches Pi in a desktop window
```

The shell starts `../venv/bin/python -m uvicorn app:app` (or reuses a server
already on :7860), shows a loading splash, then loads the UI. Quitting stops the
backend it started. Override the port with `PAIOS_PORT`, or the repo path with
`PAIOS_REPO`.

## Build installers
```bash
npm run dist:mac    # → dist/  (.dmg)
npm run dist:win    # → dist/  (.exe, run on Windows)
```
Icons are in `assets/` — replace `assets/icon.png` / `assets/icon.icns` with the
official MyPaiOS mark (current files are placeholders from `docs/paios.jpg`).

## Production roadmap — a true "no-Python-required" distributable
The dev shell runs the repo venv. To ship to end users who have no Python:

1. **Bundle the backend.** Freeze the FastAPI app + dependencies into a sidecar
   with **PyInstaller**, ship it via electron-builder `extraResources`, and spawn
   the bundled binary instead of `../venv`.
   - Hardest part: `torch` / `onnxruntime` / `chromadb` / `docling` are large and
     finicky to freeze (expect a multi-GB payload). Mitigation: download heavy
     models (FastEmbed, Docling OCR) on **first run** rather than bundling them.
2. **Code-sign + notarize.** macOS (Developer ID + `notarytool`) and Windows
   (Authenticode) so installers run without security warnings.
3. **Auto-update.** Add `electron-updater` + a release feed (GitHub Releases / S3)
   for in-app updates.
4. **Ollama.** Detect/launch it, bundle it, or document it as a prerequisite.

## Why Electron (vs Tauri/pywebview)
Chosen for a durable, long-term product: bundled Chromium → identical rendering
everywhere (no per-OS webview quirks on a complex UI), the most mature tooling
(electron-builder, electron-updater, signing/notarization), and the proven stack
behind VS Code, Slack, Claude, ChatGPT, and LM Studio. A lightweight pywebview
launcher (`../desktop.py`) is also kept as a fallback.
