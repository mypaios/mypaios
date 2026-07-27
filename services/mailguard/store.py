"""Mail Guard store — rules, decisions (audit trail), per-account state.

Standalone SQLite (data/mailguard.db, WAL) following the services/crew/store.py
pattern. Every triage verdict is recorded so the user can audit what the AI
did, restore wrongly-filed mail, and teach the rules from mistakes.
"""

from __future__ import annotations

import json
import os
import pathlib
import sqlite3
import threading
import time
from typing import Optional

_BASE_DIR = pathlib.Path(__file__).resolve().parent.parent.parent
_DB_FILE = str(_BASE_DIR / "data" / "mailguard.db")
_lock = threading.Lock()

VERDICTS = ("urgent", "important", "fyi", "marketing", "noise")
RULE_KINDS = ("include", "exclude")
RULE_FIELDS = ("sender", "domain", "subject")


def _connect() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(_DB_FILE), exist_ok=True)
    db = sqlite3.connect(_DB_FILE, timeout=30)
    db.execute("PRAGMA journal_mode=WAL")
    return db


def init_db():
    with _connect() as db:
        db.execute("""CREATE TABLE IF NOT EXISTS rules (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            owner TEXT DEFAULT '',
            kind TEXT NOT NULL,            -- include | exclude
            field TEXT NOT NULL,           -- sender | domain | subject
            pattern TEXT NOT NULL,         -- lowercase substring match
            note TEXT DEFAULT '',
            created REAL NOT NULL
        )""")
        db.execute("""CREATE TABLE IF NOT EXISTS decisions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            owner TEXT DEFAULT '',
            account_id TEXT NOT NULL,
            account_email TEXT DEFAULT '',
            message_id TEXT NOT NULL,
            uid TEXT DEFAULT '',
            folder TEXT DEFAULT 'INBOX',
            subject TEXT DEFAULT '',
            sender TEXT DEFAULT '',
            verdict TEXT NOT NULL,         -- urgent | important | fyi | marketing | noise
            stage TEXT DEFAULT '',         -- rule | heuristic | llm
            action TEXT DEFAULT 'kept',    -- kept | filed | trashed | restored
            reason TEXT DEFAULT '',
            draft TEXT DEFAULT '',
            ts REAL NOT NULL,
            UNIQUE(account_id, message_id)
        )""")
        db.execute("CREATE INDEX IF NOT EXISTS idx_decisions_ts ON decisions(ts DESC)")
        db.execute("CREATE INDEX IF NOT EXISTS idx_decisions_verdict ON decisions(verdict)")
        db.execute("""CREATE TABLE IF NOT EXISTS acct_state (
            account_id TEXT PRIMARY KEY,
            last_sweep REAL DEFAULT 0,
            last_error TEXT DEFAULT '',
            swept_total INTEGER DEFAULT 0
        )""")


# ── rules ──────────────────────────────────────────────────────────────────

def list_rules(owner: Optional[str] = None) -> list[dict]:
    init_db()
    with _connect() as db:
        q = "SELECT id, owner, kind, field, pattern, note, created FROM rules"
        params: tuple = ()
        if owner is not None:
            q += " WHERE owner=? OR owner='' OR owner IS NULL"
            params = (owner,)
        q += " ORDER BY kind, pattern"
        return [
            {"id": r[0], "owner": r[1], "kind": r[2], "field": r[3],
             "pattern": r[4], "note": r[5], "created": r[6]}
            for r in db.execute(q, params).fetchall()
        ]


def add_rule(kind: str, field: str, pattern: str, owner: str = "", note: str = "") -> dict:
    if kind not in RULE_KINDS:
        raise ValueError(f"kind must be one of {RULE_KINDS}")
    if field not in RULE_FIELDS:
        raise ValueError(f"field must be one of {RULE_FIELDS}")
    pattern = (pattern or "").strip().lower()
    if not pattern or len(pattern) > 200:
        raise ValueError("pattern must be 1-200 chars")
    init_db()
    with _lock, _connect() as db:
        # dedupe
        row = db.execute(
            "SELECT id FROM rules WHERE kind=? AND field=? AND pattern=?",
            (kind, field, pattern)).fetchone()
        if row:
            return {"id": row[0], "kind": kind, "field": field, "pattern": pattern, "deduped": True}
        cur = db.execute(
            "INSERT INTO rules(owner, kind, field, pattern, note, created) VALUES(?,?,?,?,?,?)",
            (owner or "", kind, field, pattern, note or "", time.time()))
        db.commit()
        return {"id": cur.lastrowid, "kind": kind, "field": field, "pattern": pattern}


def delete_rule(rule_id: int) -> bool:
    init_db()
    with _lock, _connect() as db:
        cur = db.execute("DELETE FROM rules WHERE id=?", (rule_id,))
        db.commit()
        return cur.rowcount > 0


# ── decisions ──────────────────────────────────────────────────────────────

def seen_message_ids(account_id: str, message_ids: list[str]) -> set[str]:
    """Which of these message-ids were already triaged for this account."""
    if not message_ids:
        return set()
    init_db()
    with _connect() as db:
        marks = ",".join("?" for _ in message_ids)
        rows = db.execute(
            f"SELECT message_id FROM decisions WHERE account_id=? AND message_id IN ({marks})",
            (account_id, *message_ids)).fetchall()
        return {r[0] for r in rows}


def record_decision(**kw) -> Optional[int]:
    init_db()
    with _lock, _connect() as db:
        try:
            cur = db.execute(
                """INSERT INTO decisions(owner, account_id, account_email, message_id, uid,
                       folder, subject, sender, verdict, stage, action, reason, draft, ts)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (kw.get("owner", ""), kw["account_id"], kw.get("account_email", ""),
                 kw["message_id"], str(kw.get("uid", "")), kw.get("folder", "INBOX"),
                 (kw.get("subject") or "")[:300], (kw.get("sender") or "")[:300],
                 kw["verdict"], kw.get("stage", ""), kw.get("action", "kept"),
                 (kw.get("reason") or "")[:400], kw.get("draft", ""), time.time()))
            db.commit()
            return cur.lastrowid
        except sqlite3.IntegrityError:
            return None  # duplicate (account_id, message_id) — already triaged


def list_decisions(limit: int = 50, verdict: Optional[str] = None,
                   since_hours: Optional[float] = None) -> list[dict]:
    init_db()
    q = ("SELECT id, account_id, account_email, message_id, uid, folder, subject, sender, "
         "verdict, stage, action, reason, draft, ts FROM decisions")
    conds, params = [], []
    if verdict:
        conds.append("verdict=?"); params.append(verdict)
    if since_hours:
        conds.append("ts>=?"); params.append(time.time() - since_hours * 3600)
    if conds:
        q += " WHERE " + " AND ".join(conds)
    q += " ORDER BY ts DESC LIMIT ?"
    params.append(max(1, min(int(limit), 500)))
    with _connect() as db:
        cols = ("id", "account_id", "account_email", "message_id", "uid", "folder",
                "subject", "sender", "verdict", "stage", "action", "reason", "draft", "ts")
        return [dict(zip(cols, r)) for r in db.execute(q, params).fetchall()]


def get_decision(decision_id: int) -> Optional[dict]:
    rows = [d for d in list_decisions(limit=500) if d["id"] == decision_id]
    return rows[0] if rows else None


def mark_restored(decision_id: int):
    init_db()
    with _lock, _connect() as db:
        db.execute("UPDATE decisions SET action='restored' WHERE id=?", (decision_id,))
        db.commit()


def stats(since_hours: float = 24.0) -> dict:
    init_db()
    cutoff = time.time() - since_hours * 3600
    with _connect() as db:
        rows = db.execute(
            "SELECT verdict, COUNT(*) FROM decisions WHERE ts>=? GROUP BY verdict",
            (cutoff,)).fetchall()
        by_verdict = {v: 0 for v in VERDICTS}
        by_verdict.update({r[0]: r[1] for r in rows})
        filed = db.execute(
            "SELECT COUNT(*) FROM decisions WHERE ts>=? AND action IN ('filed','trashed')",
            (cutoff,)).fetchone()[0]
        accounts = db.execute(
            "SELECT COUNT(DISTINCT account_id) FROM decisions WHERE ts>=?",
            (cutoff,)).fetchone()[0]
        total = db.execute("SELECT COUNT(*) FROM decisions").fetchone()[0]
        return {"window_hours": since_hours, "by_verdict": by_verdict,
                "filed": filed, "accounts_active": accounts, "all_time_total": total}


# ── per-account sweep state ────────────────────────────────────────────────

def touch_account(account_id: str, error: str = "", swept: int = 0):
    init_db()
    with _lock, _connect() as db:
        db.execute(
            """INSERT INTO acct_state(account_id, last_sweep, last_error, swept_total)
               VALUES(?,?,?,?)
               ON CONFLICT(account_id) DO UPDATE SET
                 last_sweep=excluded.last_sweep,
                 last_error=excluded.last_error,
                 swept_total=swept_total+?""",
            (account_id, time.time(), error[:300], swept, swept))
        db.commit()


def account_states() -> dict:
    init_db()
    with _connect() as db:
        rows = db.execute(
            "SELECT account_id, last_sweep, last_error, swept_total FROM acct_state").fetchall()
        return {r[0]: {"last_sweep": r[1], "last_error": r[2], "swept_total": r[3]} for r in rows}
