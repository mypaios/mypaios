"""Audit store for Crew runs — standalone SQLite at data/crew.db.

Mirrors the durability pattern of src/file_index.py (WAL + a write lock +
parameterized queries). Every run records who asked, the goal, the plan, each
step's agent/model/result, whether any cloud model was used, and the final
synthesized answer — the auditability the design calls for.
"""

from __future__ import annotations

import json
import os
import pathlib
import sqlite3
import threading
import time
from typing import Dict, List, Optional

_BASE_DIR = pathlib.Path(__file__).resolve().parent.parent.parent
_DB_FILE = str(_BASE_DIR / "data" / "crew.db")

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
            CREATE TABLE IF NOT EXISTS crew_runs (
                id TEXT PRIMARY KEY,
                owner TEXT,
                goal TEXT NOT NULL,
                status TEXT NOT NULL,
                used_cloud INTEGER NOT NULL DEFAULT 0,
                plan_json TEXT,
                steps_json TEXT,
                final TEXT,
                meta_json TEXT,
                created_at INTEGER NOT NULL,
                finished_at INTEGER
            )
            """
        )
        db.execute("CREATE INDEX IF NOT EXISTS ix_crew_runs_owner ON crew_runs(owner)")
        db.execute("CREATE INDEX IF NOT EXISTS ix_crew_runs_created ON crew_runs(created_at)")


def create_run(run_id: str, owner: Optional[str], goal: str, plan: Optional[dict]) -> None:
    init_db()
    with _lock, _connect() as db:
        db.execute(
            "INSERT OR REPLACE INTO crew_runs(id,owner,goal,status,used_cloud,plan_json,steps_json,final,meta_json,created_at,finished_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (run_id, owner, goal, "running", 0,
             json.dumps(plan or {}), json.dumps([]), None, json.dumps({}),
             int(time.time()), None),
        )
        db.commit()


def finish_run(
    run_id: str, status: str, steps: List[dict], final: Optional[str],
    used_cloud: bool, meta: Optional[dict] = None,
) -> None:
    with _lock, _connect() as db:
        db.execute(
            "UPDATE crew_runs SET status=?, used_cloud=?, steps_json=?, final=?, meta_json=?, finished_at=? WHERE id=?",
            (status, 1 if used_cloud else 0, json.dumps(steps),
             final, json.dumps(meta or {}), int(time.time()), run_id),
        )
        db.commit()


def list_runs(owner: Optional[str], limit: int = 50) -> List[Dict]:
    init_db()
    with _connect() as db:
        if owner is None:
            cur = db.execute(
                "SELECT id,owner,goal,status,used_cloud,created_at,finished_at FROM crew_runs "
                "ORDER BY created_at DESC LIMIT ?", (limit,))
        else:
            cur = db.execute(
                "SELECT id,owner,goal,status,used_cloud,created_at,finished_at FROM crew_runs "
                "WHERE owner=? OR owner IS NULL ORDER BY created_at DESC LIMIT ?", (owner, limit))
        return [
            {"id": r[0], "owner": r[1], "goal": r[2], "status": r[3],
             "used_cloud": bool(r[4]), "created_at": r[5], "finished_at": r[6]}
            for r in cur.fetchall()
        ]


def get_run(run_id: str, owner: Optional[str]) -> Optional[Dict]:
    init_db()
    with _connect() as db:
        cur = db.execute(
            "SELECT id,owner,goal,status,used_cloud,plan_json,steps_json,final,meta_json,created_at,finished_at "
            "FROM crew_runs WHERE id=?", (run_id,))
        r = cur.fetchone()
    if not r:
        return None
    # Owner scoping: 404-style hiding is enforced by the route; here we just return.
    if owner is not None and r[1] is not None and r[1] != owner:
        return None
    return {
        "id": r[0], "owner": r[1], "goal": r[2], "status": r[3],
        "used_cloud": bool(r[4]),
        "plan": json.loads(r[5] or "{}"),
        "steps": json.loads(r[6] or "[]"),
        "final": r[7],
        "meta": json.loads(r[8] or "{}"),
        "created_at": r[9], "finished_at": r[10],
    }
