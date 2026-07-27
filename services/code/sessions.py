"""Code Board sessions — persistent, resumable coding sessions (tmux-style).

Up to MAX_SESSIONS coding "windows", each pinned to a project folder with its
own chat history, stored in standalone SQLite (data/code_sessions.db — WAL +
write lock, same durability pattern as crew/file-index stores). The frontend
board lists them as tiles; multiple sessions can stream concurrently (the
backend is async and Ollama serves parallel requests).
"""

from __future__ import annotations

import json
import os
import pathlib
import sqlite3
import threading
import time
import uuid
from typing import Dict, List, Optional

_BASE_DIR = pathlib.Path(__file__).resolve().parent.parent.parent
_DB_FILE = str(_BASE_DIR / "data" / "code_sessions.db")

MAX_SESSIONS = 16

_lock = threading.Lock()


def _connect() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(_DB_FILE), exist_ok=True)
    db = sqlite3.connect(_DB_FILE, timeout=30)
    db.execute("PRAGMA journal_mode=WAL")
    return db


def init_db() -> None:
    with _connect() as db:
        db.execute(
            """
            CREATE TABLE IF NOT EXISTS code_sessions (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                root TEXT NOT NULL,
                history_json TEXT NOT NULL DEFAULT '[]',
                created_at INTEGER NOT NULL,
                updated_at INTEGER NOT NULL
            )
            """
        )
        db.execute("CREATE INDEX IF NOT EXISTS ix_code_sessions_updated ON code_sessions(updated_at)")


def _row_meta(r) -> Dict:
    history = json.loads(r[3] or "[]")
    last = ""
    for m in reversed(history):
        if isinstance(m, dict) and m.get("content"):
            last = str(m["content"])[:120]
            break
    return {"id": r[0], "name": r[1], "root": r[2], "turns": len(history),
            "last": last, "created_at": r[4], "updated_at": r[5]}


def list_sessions() -> List[Dict]:
    init_db()
    with _connect() as db:
        cur = db.execute(
            "SELECT id,name,root,history_json,created_at,updated_at FROM code_sessions "
            "ORDER BY updated_at DESC")
        return [_row_meta(r) for r in cur.fetchall()]


def get_session(sid: str) -> Optional[Dict]:
    init_db()
    with _connect() as db:
        cur = db.execute(
            "SELECT id,name,root,history_json,created_at,updated_at FROM code_sessions WHERE id=?",
            (sid,))
        r = cur.fetchone()
    if not r:
        return None
    meta = _row_meta(r)
    meta["history"] = json.loads(r[3] or "[]")
    return meta


def create_session(root: str, name: Optional[str] = None) -> Dict:
    init_db()
    root = os.path.realpath(os.path.expanduser(root or ""))
    if not os.path.isdir(root):
        raise ValueError(f"not a folder: {root}")
    with _lock, _connect() as db:
        n = db.execute("SELECT COUNT(*) FROM code_sessions").fetchone()[0]
        if n >= MAX_SESSIONS:
            raise RuntimeError(f"Board is full ({MAX_SESSIONS} sessions) — close one first.")
        sid = uuid.uuid4().hex[:12]
        now = int(time.time())
        nm = (name or os.path.basename(root) or "session")[:60]
        db.execute(
            "INSERT INTO code_sessions(id,name,root,history_json,created_at,updated_at) VALUES (?,?,?,?,?,?)",
            (sid, nm, root, "[]", now, now))
        db.commit()
    return {"id": sid, "name": nm, "root": root, "turns": 0, "last": "",
            "created_at": now, "updated_at": now}


def update_session(sid: str, history: Optional[list] = None,
                   name: Optional[str] = None, root: Optional[str] = None) -> bool:
    init_db()
    sets, vals = [], []
    if history is not None:
        # keep history bounded — last 60 turns is plenty for a coding session
        clean = [m for m in history if isinstance(m, dict)
                 and m.get("role") in ("user", "assistant") and m.get("content")][-60:]
        sets.append("history_json=?"); vals.append(json.dumps(clean))
    if name:
        sets.append("name=?"); vals.append(str(name)[:60])
    if root:
        rp = os.path.realpath(os.path.expanduser(root))
        if not os.path.isdir(rp):
            raise ValueError(f"not a folder: {root}")
        sets.append("root=?"); vals.append(rp)
    if not sets:
        return False
    sets.append("updated_at=?"); vals.append(int(time.time()))
    vals.append(sid)
    with _lock, _connect() as db:
        cur = db.execute(f"UPDATE code_sessions SET {', '.join(sets)} WHERE id=?", vals)
        db.commit()
        return cur.rowcount > 0


def delete_session(sid: str) -> bool:
    init_db()
    with _lock, _connect() as db:
        cur = db.execute("DELETE FROM code_sessions WHERE id=?", (sid,))
        db.commit()
        return cur.rowcount > 0
