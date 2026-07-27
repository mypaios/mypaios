#!/usr/bin/env python3
"""PiAOS — native desktop launcher (cross-platform).

Runs the local FastAPI server (as a subprocess) and shows the UI in a NATIVE
OS webview window via pywebview — no browser, no address bar, feels like a real
app, and lightweight (uses the OS's own webview, not a bundled Chromium):

  - macOS   -> WKWebView (Cocoa)
  - Windows -> WebView2 (Edge Chromium runtime; preinstalled on Windows 11)
  - Linux   -> WebKitGTK / Qt

If a server is already running on the port, it just attaches a window to it and
will NOT stop it on close. Otherwise it starts one and stops it when the window
closes.

Run:
  macOS/Linux:  ./venv/bin/python desktop.py
  Windows:      venv\\Scripts\\python.exe desktop.py
"""
import os
import sys
import time
import socket
import subprocess
import atexit

REPO = os.path.dirname(os.path.abspath(__file__))
HOST = os.environ.get("APP_BIND", "127.0.0.1")
PORT = int(os.environ.get("PAIOS_PORT", os.environ.get("APP_PORT", "7860")))
URL = f"http://{HOST}:{PORT}"

# Load .env so the server inherits CHROMADB_MODE / PAIOS_DOC_ROOTS / vault config.
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(REPO, ".env"))
except Exception:
    pass
os.environ.setdefault("CHROMADB_MODE", "embedded")


def _port_open(host: str, port: int, timeout: float = 1.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout):
            return True
    except OSError:
        return False


def _venv_python() -> str:
    if os.name == "nt":
        return os.path.join(REPO, "venv", "Scripts", "python.exe")
    return os.path.join(REPO, "venv", "bin", "python")


_server = None
if not _port_open(HOST, PORT):
    py = _venv_python() if os.path.exists(_venv_python()) else sys.executable
    print(f"[desktop] starting Pi server: {py} -m uvicorn app:app :{PORT}")
    _server = subprocess.Popen(
        [py, "-m", "uvicorn", "app:app", "--host", HOST, "--port", str(PORT)],
        cwd=REPO,
    )
    # First run may download an embedding model — allow up to ~3 min.
    for _ in range(180):
        if _port_open(HOST, PORT):
            break
        if _server.poll() is not None:
            sys.stderr.write("[desktop] Pi server exited during startup.\n")
            sys.exit(1)
        time.sleep(1)
else:
    print(f"[desktop] reusing server already running at {URL}")


def _shutdown():
    # Only stop the server WE started (never kill a pre-existing one).
    if _server is not None and _server.poll() is None:
        _server.terminate()
        try:
            _server.wait(timeout=6)
        except Exception:
            _server.kill()


atexit.register(_shutdown)

import webview  # imported after the server boots to keep startup snappy

webview.create_window(
    "PiAOS",
    URL,
    width=1280,
    height=860,
    min_size=(900, 600),
)
webview.start()  # blocks on the main thread until the window is closed
_shutdown()
