"""Detached Code-tab agent jobs — work that finishes even if you close the panel.

The problem: a Code chat turn used to run *inside* the HTTP streaming request,
so if the client went away (panel ✕, app reload, network blip) the request was
cancelled and the agent loop died mid-task — the file never got written.

The fix: each turn runs as a server-side asyncio task that is NOT tied to any
request. It drains stream_agent_loop into a per-session buffer and, on
completion, persists the assistant message to the session store. The HTTP
endpoint just *tails* that buffer. Disconnecting stops the tailing, never the
work. Reopening the window re-attaches to the same buffer (replays what already
happened, then continues live) — so the operation always runs to its goal and
you can always see where it's at.

One running job per session id. Finished buffers linger briefly so a
reconnecting client can replay the result, then are swept.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Callable, Optional

from services.code import sessions as sess_store

logger = logging.getLogger("code.jobs")

_JOBS: dict = {}            # sid -> _Job
_KEEP_DONE_SECONDS = 600    # keep a finished job's buffer this long for replay
_MAX_BUFFER = 6000          # hard cap on buffered SSE lines (runaway backstop)


class _Job:
    __slots__ = ("sid", "buffer", "status", "started", "ended",
                 "assistant", "task", "history", "user_msg")

    def __init__(self, sid: str):
        self.sid = sid
        self.buffer: list = []        # SSE strings, each ending in "\n\n"
        self.status = "running"       # running | done | error
        self.started = time.time()
        self.ended: Optional[float] = None
        self.assistant = ""           # accumulated assistant text (for persistence)
        self.task = None
        self.history: list = []       # history snapshot captured at start
        self.user_msg = ""


def is_running(sid: str) -> bool:
    j = _JOBS.get(sid)
    return bool(j and j.status == "running")


def status(sid: str) -> dict:
    j = _JOBS.get(sid)
    if not j:
        return {"running": False, "cursor": 0, "status": "idle"}
    return {"running": j.status == "running", "cursor": len(j.buffer), "status": j.status}


def cancel(sid: str) -> bool:
    """Actually stop a detached run (the Stop button). Cancels the task; the
    job's finally-block still persists whatever was produced before the stop."""
    j = _JOBS.get(sid)
    if j and j.task and not j.task.done():
        j.buffer.append("data: " + json.dumps({"type": "delta", "delta": "\n[stopped]"}) + "\n\n")
        j.task.cancel()
        return True
    return False


def _sweep():
    """Drop finished jobs whose buffers have aged out."""
    now = time.time()
    for sid in list(_JOBS.keys()):
        j = _JOBS[sid]
        if j.status != "running" and j.ended and (now - j.ended) > _KEEP_DONE_SECONDS:
            _JOBS.pop(sid, None)


def start(sid: str, loop_factory: Callable, user_msg: str, history: Optional[list] = None):
    """Start (or return the already-running) detached job for `sid`.

    loop_factory() must return an async generator yielding SSE strings — the
    same lines stream_agent_loop produces. Returns the _Job.
    """
    _sweep()
    existing = _JOBS.get(sid)
    if existing and existing.status == "running":
        return existing  # never double-run a session; caller attaches instead

    job = _Job(sid)
    job.user_msg = user_msg or ""
    job.history = list(history or [])
    _JOBS[sid] = job

    async def _run():
        try:
            async for ev in loop_factory():
                if not isinstance(ev, str):
                    continue
                line = ev if ev.endswith("\n\n") else ev + "\n\n"
                if len(job.buffer) < _MAX_BUFFER:
                    job.buffer.append(line)
                _accumulate(job, line)
        except asyncio.CancelledError:
            # The job task itself was cancelled (server shutdown) — mark and re-raise.
            job.status = "error"
            job.ended = time.time()
            raise
        except Exception as e:  # noqa: BLE001
            logger.exception("code job %s failed", sid)
            job.buffer.append("data: " + json.dumps({"type": "error", "message": str(e)[:300]}) + "\n\n")
            job.status = "error"
        finally:
            if job.status == "running":
                job.status = "done"
            job.ended = time.time()
            job.buffer.append("data: [DONE]\n\n")
            _persist(job)

    job.task = asyncio.create_task(_run())
    return job


def _accumulate(job: _Job, line: str):
    """Pull assistant text out of delta events so we can persist the reply."""
    if not line.startswith("data: "):
        return
    payload = line[6:].strip()
    if not payload or payload == "[DONE]":
        return
    try:
        d = json.loads(payload)
    except Exception:
        return
    if isinstance(d, dict) and isinstance(d.get("delta"), str):
        job.assistant += d["delta"]


def _persist(job: _Job):
    """On completion, append user + assistant to the session's stored history,
    so the result survives even if no client was watching when it finished."""
    try:
        text = (job.assistant or "").strip()
        if not text:
            return
        hist = list(job.history)
        hist.append({"role": "user", "content": job.user_msg})
        hist.append({"role": "assistant", "content": text})
        sess_store.update_session(job.sid, history=hist)
        logger.info("code job %s persisted (%d chars) to session history", job.sid, len(text))
    except Exception:
        logger.exception("code job %s persist failed", job.sid)


async def stream(sid: str, from_cursor: int = 0):
    """Tail a job's buffer from `from_cursor`, then live until it finishes.

    Safe to call repeatedly / from multiple reconnects. Closing the consumer
    (client disconnect) does NOT stop the underlying job.
    """
    job = _JOBS.get(sid)
    if not job:
        yield "data: " + json.dumps({"type": "error", "message": "no active job for this window"}) + "\n\n"
        yield "data: [DONE]\n\n"
        return
    i = max(0, int(from_cursor or 0))
    while True:
        while i < len(job.buffer):
            yield job.buffer[i]
            i += 1
        if job.status != "running" and i >= len(job.buffer):
            return
        await asyncio.sleep(0.15)
