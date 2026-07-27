"""User Activity Log Service — records user clicks, inputs, navigation, and chat back-and-forth for testing/QA."""

import json
import os
import time
import threading

try:
    from core.constants import BASE_DIR
    _LOG_PATH = os.path.join(BASE_DIR, "logs", "user-activity.jsonl")
except Exception:
    _LOG_PATH = os.path.join("logs", "user-activity.jsonl")

_lock = threading.Lock()
_MAX_BYTES = 10_000_000  # 10 MB limit
_KEEP_LINES = 10000

def log(event_type: str, details: dict) -> None:
    """Log an activity event to logs/user-activity.jsonl."""
    try:
        rec = {
            "t": round(time.time(), 3),
            "type": event_type,
            "details": details
        }
        line = json.dumps(rec, ensure_ascii=False) + "\n"
        with _lock:
            os.makedirs(os.path.dirname(_LOG_PATH), exist_ok=True)
            with open(_LOG_PATH, "a", encoding="utf-8") as f:
                f.write(line)
            
            # Trim check
            if os.path.getsize(_LOG_PATH) > _MAX_BYTES:
                _trim_logs()
    except Exception:
        pass

def _trim_logs() -> None:
    """Trim the log file to stay within limits."""
    try:
        if not os.path.exists(_LOG_PATH):
            return
        with open(_LOG_PATH, "r", encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()
        if len(lines) > _KEEP_LINES:
            with open(_LOG_PATH, "w", encoding="utf-8") as f:
                f.writelines(lines[-_KEEP_LINES:])
    except Exception:
        pass

def get_logs(limit: int = 1000) -> list:
    """Read the last `limit` logs from the log file (newest first)."""
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
            out.append(json.loads(ln))
        except Exception:
            continue
        if len(out) >= limit:
            break
    return out

def clear_logs() -> None:
    """Clear all logged user activities."""
    try:
        with _lock:
            if os.path.exists(_LOG_PATH):
                os.remove(_LOG_PATH)
    except Exception:
        pass
