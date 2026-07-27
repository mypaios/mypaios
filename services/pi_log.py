"""Ultra-light, append-only event log of what Pi actually DOES — for fast triage.

One compact JSON line per significant event in logs/pi-events.jsonl, e.g.:
  {"t":1718412345,"k":"tool","tool":"write_file","ok":1,"cmd":"index.html","ws":"my-project"}
  {"t":...,"k":"nudge","phrase":"let me create the file"}
  {"t":...,"k":"http","status":422,"path":"/api/code/chat"}
  {"t":...,"k":"turn","ev":"start","model":"qwen3-coder-next:q4_K_M","ws":"my-project"}

This is deliberately NOT the verbose uvicorn/python log — it's the high-signal
"what happened" stream you can grep in seconds:
    tail -n 50 logs/pi-events.jsonl
    grep '"ok":0' logs/pi-events.jsonl          # every tool failure
    grep '"k":"http"' logs/pi-events.jsonl      # every 4xx/5xx

Self-trimming so it never grows unbounded (caps at ~1 MB, keeps the last 3000
lines). Best-effort: every call is wrapped so logging can NEVER break a request.
"""

from __future__ import annotations

import json
import os
import threading
import time

try:
    from core.constants import BASE_DIR
    _LOG_PATH = os.path.join(BASE_DIR, "logs", "pi-events.jsonl")
except Exception:  # pragma: no cover — fall back to cwd
    _LOG_PATH = os.path.join("logs", "pi-events.jsonl")

_MAX_BYTES = 1_000_000   # trim when the file grows past ~1 MB
_KEEP_LINES = 3000       # ...down to the most recent this many lines
_TRIM_EVERY = 64         # only stat()/trim once per this many writes

_lock = threading.Lock()
_writes = 0


def log(kind: str, **fields) -> None:
    """Append one event. Never raises. Keep `fields` small + JSON-serializable."""
    global _writes
    try:
        rec = {"t": int(time.time()), "k": kind}
        for k, v in fields.items():
            if v is None:
                continue
            # keep strings short so the log stays light
            rec[k] = v[:200] if isinstance(v, str) else v
        line = json.dumps(rec, separators=(",", ":"), ensure_ascii=False) + "\n"
        with _lock:
            os.makedirs(os.path.dirname(_LOG_PATH), exist_ok=True)
            with open(_LOG_PATH, "a", encoding="utf-8") as f:
                f.write(line)
            _writes += 1
            if _writes % _TRIM_EVERY == 0:
                _maybe_trim()
    except Exception:
        pass  # logging must never break the caller


def _maybe_trim() -> None:
    try:
        if os.path.getsize(_LOG_PATH) <= _MAX_BYTES:
            return
        with open(_LOG_PATH, "r", encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()
        if len(lines) > _KEEP_LINES:
            with open(_LOG_PATH, "w", encoding="utf-8") as f:
                f.writelines(lines[-_KEEP_LINES:])
    except Exception:
        pass


def tail(n: int = 200, kind: str = "") -> list:
    """Return the last `n` events (newest last), optionally filtered by kind."""
    try:
        with open(_LOG_PATH, "r", encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()
    except FileNotFoundError:
        return []
    except Exception:
        return []
    out = []
    for ln in reversed(lines):
        ln = ln.strip()
        if not ln:
            continue
        try:
            rec = json.loads(ln)
        except Exception:
            continue
        if kind and rec.get("k") != kind:
            continue
        out.append(rec)
        if len(out) >= n:
            break
    out.reverse()
    return out
