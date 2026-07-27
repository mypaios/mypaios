"""
src/file_index.py — global file/folder NAME index + fuzzy search + open-in-Finder.

Indexes file & folder NAMES (not content) under user-configured "drive" roots
into a standalone SQLite DB (data/file_index.db) for fast name search. Results
are clickable: open a file in its default app, or reveal/open a folder in Finder.

Self-contained (raw sqlite3, no app-DB coupling) so the index can be rebuilt
freely. Used by the Agents tab (Sync + Search) via routes/file_index_routes.py.
"""
from __future__ import annotations

import os
import sys
import json
import time
import sqlite3
import logging
import threading
import subprocess

logger = logging.getLogger(__name__)

_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_DATA_DIR = os.path.join(_BASE_DIR, "data")
ROOTS_FILE = os.path.join(_DATA_DIR, "file_index_roots.json")
DB_FILE = os.path.join(_DATA_DIR, "file_index.db")

# Directory names never worth indexing (noise / huge / build / vcs).
SKIP_DIR_NAMES = {
    "node_modules", ".git", ".hg", ".svn", "__pycache__", ".venv", "venv",
    ".cache", ".npm", ".gradle", ".m2", ".cocoapods", ".Trash", "dist", "build",
    ".next", ".turbo", "site-packages", "DerivedData", ".terraform", ".tox",
    # Huge/mounted volumes inside ~ that would blow up a home scan. Add them as
    # an explicit root instead if you really want to index one.
    "4TBHDD", "Applications",
    # Heavy build/dependency/cache dirs (incl. Unity project "Library"/"Temp").
    "Library", "Temp", "Pods", "target", "vendor", "Caches", "out", "obj",
}
# Bundle/package dir suffixes treated as opaque (don't recurse into their guts).
SKIP_DIR_SUFFIXES = (".app", ".photoslibrary", ".framework", ".bundle", ".xcodeproj", ".lproj")
# Cloud-sync folders whose entries are often online-only placeholders. Opening
# such a directory can trigger a network materialization that wedges open()
# UNINTERRUPTIBLY in the kernel. Skip by name prefix (account suffix varies,
# e.g. "OneDrive-Acme"). The per-root watchdog below is the real safety net.
SKIP_DIR_PREFIXES = ("OneDrive", "Dropbox", "Google Drive", "GoogleDrive", "pCloud",
                     "Creative Cloud Files", "iCloud~", "Box Sync")
# Per-root walk watchdog (seconds). A single offline drive or online-only cloud
# folder can hang scandir's open() forever — and NO Python-level timeout can
# interrupt a syscall already stuck in the kernel. So each root is walked in a
# daemon thread and abandoned past this deadline (the thread leaks harmlessly
# instead of holding the lock and breaking every future sync).
PER_ROOT_TIMEOUT = int(os.getenv("PAIOS_FILE_INDEX_ROOT_TIMEOUT", "15"))
# Absolute path prefixes to skip entirely (massive / system).
def _default_skip_prefixes():
    home = os.path.expanduser("~")
    return [os.path.join(home, "Library"), "/System", "/private", "/usr", "/Library"]

SKIP_PREFIXES = _default_skip_prefixes()
MAX_ENTRIES = int(os.getenv("PAIOS_FILE_INDEX_MAX", "400000"))  # safety cap


def _default_roots():
    # Default to the user's working folders (fast). Full home is huge here
    # (Unity projects, a 4TB drive, etc.), so add Home / external drives
    # explicitly in the Agents → Sync panel if you want them.
    home = os.path.expanduser("~")
    cands = [os.path.join(home, d) for d in ("Documents", "Desktop", "Downloads")]
    roots = [p for p in cands if os.path.isdir(p)]
    return roots or [home]


class FileIndexManager:
    def __init__(self):
        os.makedirs(_DATA_DIR, exist_ok=True)
        self._sync_guard = threading.Lock()  # only one sync at a time (non-blocking)
        self._db_lock = threading.Lock()     # serialize sqlite writes
        self.roots = self._load_roots()
        self.last_sync = None
        self.last_duration = None
        self.last_error = None
        self.skipped_roots = []              # roots abandoned last cycle (hung/offline)
        self.count = 0
        self._init_db()
        self._refresh_count()

    # ---------- roots config ----------
    def _load_roots(self):
        try:
            with open(ROOTS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, list) and data:
                return [os.path.realpath(os.path.expanduser(p)) for p in data]
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            pass
        roots = _default_roots()
        self._save_roots(roots)
        return roots

    def _save_roots(self, roots=None):
        roots = self.roots if roots is None else roots
        try:
            with open(ROOTS_FILE, "w", encoding="utf-8") as f:
                json.dump(roots, f, indent=2)
        except OSError as e:
            logger.warning("file_index: could not save roots: %s", e)

    def get_roots(self):
        return list(self.roots)

    def add_root(self, path):
        p = os.path.realpath(os.path.expanduser((path or "").strip()))
        if not p or not os.path.isdir(p):
            raise ValueError(f"Not a directory: {path}")
        if p not in self.roots:
            self.roots.append(p)
            self._save_roots()
        return p

    def remove_root(self, path):
        p = os.path.realpath(os.path.expanduser((path or "").strip()))
        if p in self.roots:
            self.roots.remove(p)
            self._save_roots()
            db = self._connect()
            try:
                with self._db_lock:
                    db.execute("DELETE FROM files WHERE root = ?", (p,))
                    db.commit()
            finally:
                db.close()
            self._refresh_count()
        return p

    # ---------- db ----------
    def _connect(self):
        db = sqlite3.connect(DB_FILE, timeout=30)
        db.execute("PRAGMA journal_mode=WAL")
        return db

    def _init_db(self):
        with self._connect() as db:
            db.execute(
                """
                CREATE TABLE IF NOT EXISTS files (
                    path TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    name_lower TEXT NOT NULL,
                    is_dir INTEGER NOT NULL,
                    ext TEXT,
                    root TEXT NOT NULL,
                    mtime INTEGER
                )
                """
            )
            db.execute("CREATE INDEX IF NOT EXISTS ix_files_name_lower ON files(name_lower)")
            db.execute("CREATE INDEX IF NOT EXISTS ix_files_root ON files(root)")

    def _refresh_count(self):
        try:
            with self._connect() as db:
                self.count = db.execute("SELECT COUNT(*) FROM files").fetchone()[0]
        except sqlite3.Error:
            self.count = 0

    # ---------- scan / sync ----------
    def _skip_dir(self, dirpath, dname):
        if dname in SKIP_DIR_NAMES or dname.startswith("."):
            return True
        if dname.endswith(SKIP_DIR_SUFFIXES):
            return True
        if dname.startswith(SKIP_DIR_PREFIXES):
            return True
        full = os.path.join(dirpath, dname)
        for pre in SKIP_PREFIXES:
            if full == pre or full.startswith(pre + os.sep):
                return True
        return False

    def _walk_root(self, root, result):
        """Walk ONE root into result['rows']. Runs in a daemon thread so a hung
        scandir/open() on an offline mount or online-only cloud placeholder can be
        abandoned without wedging the manager. (A syscall already stuck in the
        kernel can't be interrupted — the thread just leaks until it returns.)"""
        rows = []
        capped = False
        try:
            for dirpath, dirnames, filenames in os.walk(root):
                dirnames[:] = [d for d in dirnames if not self._skip_dir(dirpath, d)]
                for dname in dirnames:
                    rows.append((os.path.join(dirpath, dname), dname, dname.lower(), 1, None, root, None))
                for fname in filenames:
                    if fname.startswith("."):
                        continue
                    rows.append((
                        os.path.join(dirpath, fname), fname, fname.lower(),
                        0, os.path.splitext(fname)[1].lower(), root, None,
                    ))
                if len(rows) >= MAX_ENTRIES:
                    capped = True
                    break
        except OSError as e:
            logger.warning("file_index: walk error in %s: %s", root, e)
        result["rows"] = rows
        result["capped"] = capped

    def sync_all(self):
        """Rebuild the index across all roots. BLOCKING — call via asyncio.to_thread.

        Each root is walked in a watchdog thread (PER_ROOT_TIMEOUT). A root that
        hangs (offline drive, online-only cloud folder) is abandoned for this cycle
        and surfaced in `skipped_roots`, so one bad mount can never wedge the index
        or block 'Sync now'. Returns {'busy': True} immediately if a sync is
        already in flight (never blocks the caller)."""
        if not self._sync_guard.acquire(blocking=False):
            return {"busy": True, "count": self.count, "last_sync": self.last_sync,
                    "skipped": list(self.skipped_roots)}
        try:
            t0 = time.time()
            rows = []
            capped = False
            skipped = []
            for root in self.roots:
                if not os.path.isdir(root):
                    continue
                result = {}
                th = threading.Thread(target=self._walk_root, args=(root, result),
                                      name="file_index_walk", daemon=True)
                th.start()
                th.join(PER_ROOT_TIMEOUT)
                if th.is_alive():
                    skipped.append(root)
                    logger.warning(
                        "file_index: walk of %s exceeded %ss (offline drive or "
                        "online-only cloud folder?) — skipping it this cycle",
                        root, PER_ROOT_TIMEOUT)
                    continue
                rows.extend(result.get("rows", []))
                if result.get("capped"):
                    capped = True
                    break
            db = self._connect()
            try:
                with self._db_lock:
                    db.execute("DELETE FROM files")
                    db.executemany(
                        "INSERT OR REPLACE INTO files(path,name,name_lower,is_dir,ext,root,mtime) "
                        "VALUES (?,?,?,?,?,?,?)",
                        rows,
                    )
                    db.commit()
            finally:
                db.close()
            self.count = len(rows)
            self.last_sync = int(time.time())
            self.skipped_roots = skipped
            self.last_duration = round(time.time() - t0, 1)
            self.last_error = None
            logger.info("file_index: synced %d entries in %ss (capped=%s, skipped=%s)",
                        self.count, self.last_duration, capped, skipped or "none")
            return {"count": self.count, "seconds": self.last_duration,
                    "roots": len(self.roots), "capped": capped, "skipped": skipped}
        except Exception as e:
            self.last_error = str(e)
            logger.warning("file_index: sync failed: %s", e, exc_info=True)
            return {"error": str(e), "count": self.count, "last_sync": self.last_sync}
        finally:
            self._sync_guard.release()

    # ---------- search ----------
    def search(self, query, limit=60):
        q = (query or "").strip().lower()
        if not q:
            return []
        like = f"%{q}%"
        try:
            with self._connect() as db:
                cur = db.execute(
                    """
                    SELECT path, name, is_dir, ext FROM files
                    WHERE name_lower LIKE ?
                    ORDER BY
                      CASE WHEN name_lower = ? THEN 0
                           WHEN name_lower LIKE ? THEN 1
                           ELSE 2 END,
                      is_dir DESC,
                      LENGTH(name) ASC
                    LIMIT ?
                    """,
                    (like, q, q + "%", limit),
                )
                return [
                    {"path": r[0], "name": r[1], "is_dir": bool(r[2]), "ext": r[3] or ""}
                    for r in cur.fetchall()
                ]
        except sqlite3.Error as e:
            logger.warning("file_index: search error: %s", e)
            return []

    # ---------- open ----------
    def open_path(self, path, reveal=False):
        """Open a file (default app) / folder (Finder), or reveal in Finder.
        Restricted to configured roots for safety."""
        p = os.path.realpath(os.path.expanduser(path or ""))
        if not any(p == r or p.startswith(r + os.sep) for r in self.roots):
            raise PermissionError("Path is not under a connected drive")
        if not os.path.exists(p):
            raise FileNotFoundError(p)
        if sys.platform == "darwin":
            cmd = ["open", "-R", p] if reveal else ["open", p]
            subprocess.run(cmd, check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        elif sys.platform == "win32":
            if reveal:
                subprocess.run(["explorer", "/select,", p], check=False)
            else:
                os.startfile(p)  # type: ignore[attr-defined]
        else:
            target = os.path.dirname(p) if reveal else p
            subprocess.run(["xdg-open", target], check=False,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return {"ok": True, "path": p}


_manager = None


def get_file_index_manager():
    global _manager
    if _manager is None:
        _manager = FileIndexManager()
    return _manager
