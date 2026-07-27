"""Code tab routes — project-aware coding agent.

The 'Code' tab opens a folder, builds a repo MAP (services/code/repomap) so the
agent knows the WHOLE project, then runs the proven Cowork coding engine
(src.agent_loop + the coding model + coder tool policy) with that map + the
project's AGENTS.md/README injected as context. Best practices applied:
Aider repo map · Codex/Claude AGENTS.md · plan-first · workspace sandbox + denylist.
"""

from __future__ import annotations

import json
import logging
import os
import time

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from core.middleware import require_admin
from src.auth_helpers import effective_user, get_current_user
from src.settings import load_settings
from services.code import repomap
from services.crew import router as crew_router
from services.crew.registry import AGENTS as CREW_AGENTS

logger = logging.getLogger("code.routes")

_AGENTS_TEMPLATE = """# AGENTS.md

> Project instructions for AI coding agents (Codex / Claude Code / Pi). Keep this
> short — a "constitution": point to where the real detail lives.

## What this project is
{desc}

## How to run / test
- Install:
- Run:
- Test:

## Conventions
- Language / style:
- Don't touch:

## Notes for the agent
- Prefer small, reviewable changes. Run tests before declaring done.
"""

_PI_TEMPLATE = """# PI.md

> Instructions for PiAOS agents (Code / Chat / Crew / Research) working in THIS
> project. Read on every turn, takes precedence over AGENTS.md. Keep it short.

## What this project is
{desc}

## How to run / test
- Install:
- Run:
- Test:

## Conventions
- Language / style:
- Don't touch:

## Notes for the agent
- Prefer small, reviewable changes. Run tests before declaring done.
"""


def _coder_route(owner, settings):
    url, model, headers, meta = crew_router.route_for_agent(CREW_AGENTS["coder"], owner, settings)
    return url, model, headers, meta


# NOTE: request models MUST live at module scope. This file uses
# `from __future__ import annotations`, so FastAPI resolves a handler's
# `body: ChatBody` hint via get_type_hints() against the MODULE globals. A
# BaseModel defined inside setup_code_routes() isn't in those globals, so
# FastAPI can't see it's a Pydantic model and mis-treats `body` as a query
# param → 422 {"loc":["query","body"],"msg":"Field required"}.
class ChatBody(BaseModel):
    path: str
    message: str
    history: list | None = None
    plan: bool | None = False
    sid: str | None = None   # Code Board window id — enables detached/resumable runs
    mode: str | None = "code"  # code | plan | act | review | research (Claude-style modes)


# ── Code tab = a direct, Claude-Code-style coding agent ──────────────────────
# The Code tab talks to the coder DIRECTLY (no Crew supervisor), so it gets its
# own prompt + a focused toolset instead of the crew's "one subtask then stop"
# framing (services/crew/registry._COMMON), which makes the model quit early.

# Claude-Code-shaped allowlist: file ops + execution + web research + browser.
# Everything else (email, contacts, model-serving, sessions, image-gen,
# app-config) is disabled so a local model sees a small, unambiguous toolset.
_CODE_TAB_TOOLS = {
    "read_file", "write_file", "edit_file", "ls", "glob", "grep",
    "bash", "python",
    "web_search", "web_fetch", "trigger_research",
    "browser_navigate", "browser_read", "browser_click",
    "browser_fill", "browser_screenshot",
}

# Tools that MUTATE the project or run code — denied in read-only modes (Plan,
# Review). Read-only enforcement must be real (server-side tool gating), not
# just prompt wording, or a local model will still emit write_file.
_WRITE_EXEC_TOOLS = {"write_file", "edit_file", "bash", "python"}


def _code_tab_disabled_tools(extra: set | None = None) -> set:
    """Disable every known tool not in the focused coding allowlist, plus any
    `extra` denials (used to enforce read-only Plan/Review modes)."""
    try:
        from src.agent_tools import TOOL_TAGS
        universe = set(TOOL_TAGS)
    except Exception:  # noqa: BLE001 — fall back to the crew denylist
        base = set(CREW_AGENTS["coder"].disabled_tools)
        return base | (extra or set())
    disabled = (universe - _CODE_TAB_TOOLS) | set(CREW_AGENTS["coder"].disabled_tools)
    return disabled | (extra or set())


# Per-mode system-prompt preambles. The mode also drives the tool policy
# (read-only modes add _WRITE_EXEC_TOOLS to the disabled set).
_MODE_PREAMBLES = {
    "plan": (
        "\n\n=== PLAN MODE (READ-ONLY) ===\n"
        "You may ONLY read and inspect: read_file, ls, glob, grep, web_search, "
        "web_fetch. Writing, editing, and running code are DISABLED this turn. "
        "Produce or REFINE a concrete, numbered implementation plan: which files "
        "you'll touch, the exact changes, risks, and how you'll verify. Then STOP "
        "and wait. Do NOT start implementing. If the user gives more feedback, "
        "keep refining the plan — stay in planning until they explicitly switch to "
        "Act. End with: 'Ready when you are — press Act to build this.'"
    ),
    "act": (
        "\n\n=== ACT MODE ===\n"
        "The plan in the conversation above is APPROVED. Execute it now, end to "
        "end, using write_file/edit_file/bash/python. Make every edit the plan "
        "calls for, verify your work (run it / open it), then give a short summary "
        "of files changed and how you verified. Do NOT re-plan or ask permission."
    ),
    "review": (
        "\n\n=== REVIEW MODE (READ-ONLY) ===\n"
        "You are doing a code review. Read the relevant files (writing and running "
        "code are DISABLED this turn). Output findings as a prioritized list — "
        "Critical / Major / Minor / Nit — each with a file:line reference, the "
        "problem, and a concrete suggested fix. Do NOT modify any files."
    ),
    "research": (
        "\n\n=== DEEP RESEARCH MODE ===\n"
        "Answer with current, sourced information. Use web_search to find sources "
        "and web_fetch to read the best ones; for a broad question call "
        "trigger_research to launch a full multi-source report (it streams in the "
        "Deep Research sidebar). CITE every URL you used. Prefer reading over "
        "editing — don't change project files unless the user explicitly asks."
    ),
}


_CODE_TAB_SYSTEM = (
    "You are Pi's coding agent, working DIRECTLY for the user inside their "
    "project on their Mac — like Claude Code, but fully local. There is no "
    "supervisor; you own the task end to end.\n\n"
    "HOW YOU WORK:\n"
    "1. Understand first. Read the project map below; use grep/glob/read_file "
    "to open any file you'll touch before changing it. Never guess a file's "
    "contents.\n"
    "2. Then act. Keep going until the task is genuinely COMPLETE — don't stop "
    "after one step to ask permission for obvious next steps. Make all the edits "
    "the task needs.\n"
    "   CRITICAL: never end a reply with \"Let me create the file\" / \"I'll build "
    "it now\" and then stop. If you say you'll write or edit something, the "
    "write_file/edit_file call MUST be in that SAME reply. Announcing an action "
    "without emitting the tool call is the #1 thing that wastes the user's time — "
    "do the call, don't describe it.\n"
    "3. Files: to create or edit a file you MUST use write_file (first line = "
    "the path, the rest = the full file contents) or edit_file. NEVER use the "
    "python or bash tool to write files — python only RUNS code and saves "
    "nothing.\n"
    "4. Verify before you claim done. A toolchain is on PATH: run code with "
    "python/python3, add packages with pip, run tests with `pytest -q` directly "
    "(don't `python3 -m`, don't install pytest). For a web page or HTML you "
    "built, open it with browser_navigate (file:///full/path) and "
    "browser_screenshot to confirm it renders, or browser_read to check the "
    "DOM.\n"
    "5. Research when you need current facts: web_search to find sources, then "
    "web_fetch to read the best ones. Cite the URLs you used.\n\n"
    "STYLE: Be concise in prose — do the work in tools, not in long "
    "explanations. After finishing, give a short summary of what you changed "
    "(files touched) and how you verified it.\n\n"
    "SAFETY: Stay inside the workspace. Never use sudo, never `git push`, never "
    "pipe the web into a shell, never delete broadly. These are blocked anyway."
)


def setup_code_routes() -> APIRouter:
    router = APIRouter(prefix="/api/code", tags=["code"])

    @router.get("/context")
    def context(path: str = Query(...), rebuild: bool = Query(False),
                request: Request = None, owner: str = Depends(get_current_user)):
        if not path or not os.path.isdir(os.path.expanduser(path)):
            raise HTTPException(400, f"not a folder: {path}")
        ctx = repomap.build_context(path, rebuild=rebuild)
        if not ctx.get("ok"):
            raise HTTPException(400, ctx.get("error", "could not read project"))
        # Don't ship the giant prompt_text to the client — just what the panel needs.
        s = load_settings()
        _, model, _h, _m = _coder_route(owner, s)
        return {
            "ok": True, "root": ctx["root"], "stats": ctx["stats"],
            "tree": ctx["tree"], "map_text": ctx["map_text"],
            "agents": ctx["agents"], "readme": ctx["readme"],
            "prompt_chars": len(ctx["prompt_text"]), "coder_model": model,
        }

    @router.post("/chat")
    async def chat(body: ChatBody, request: Request, _a: str = Depends(require_admin)):
        from src.agent_loop import stream_agent_loop
        path = os.path.expanduser((body.path or "").strip())
        msg = (body.message or "").strip()
        if not path or not os.path.isdir(path):
            raise HTTPException(400, f"not a folder: {body.path}")
        if not msg:
            raise HTTPException(400, "message required")
        owner = effective_user(request)
        s = load_settings()
        ctx = repomap.build_context(path)
        url, model, headers, meta = _coder_route(owner, s)
        if not url:
            raise HTTPException(503, "No local coding model available — install one in Local AI.")

        # Mode selects BOTH the prompt preamble and the tool policy. Plan/Review
        # are read-only (write/exec tools disabled server-side, the only real
        # guarantee). `plan: true` from an older client maps to 'plan'.
        mode = (body.mode or ("plan" if body.plan else "code")).strip().lower()
        if mode not in ("code", "plan", "act", "review", "research"):
            mode = "code"
        _extra_disabled = _WRITE_EXEC_TOOLS if mode in ("plan", "review") else set()
        disabled = _code_tab_disabled_tools(_extra_disabled)

        system = (
            _CODE_TAB_SYSTEM
            + _MODE_PREAMBLES.get(mode, "")
            + "\n\n=== PROJECT MAP (file tree + key symbols + project notes) ===\n"
            + ctx["prompt_text"]
        )
        messages = [{"role": "system", "content": system}]
        for h in (body.history or [])[-12:]:
            if isinstance(h, dict) and h.get("role") in ("user", "assistant") and h.get("content"):
                messages.append({"role": h["role"], "content": str(h["content"])[:8000]})
        messages.append({"role": "user", "content": msg})

        max_rounds = int(s.get("crew_max_rounds_per_agent", 14) or 14)

        # Detached execution: the agent loop runs as a server-side job that
        # finishes even if THIS request is cancelled (panel closed, app reloaded,
        # network blip). We just tail its buffer. The job persists the result to
        # the session store on completion, so the work always reaches its goal.
        # `sid` (Code Board window id) keys the job; without it we fall back to a
        # synthetic per-request id (still detached, just not resumable).
        from services.code import jobs as code_jobs
        job_sid = (body.sid or "").strip() or f"adhoc:{int(time.time()*1000)}"

        def _loop_factory():
            async def _g():
                from services import activity
                act_id = activity.register("code", model, os.path.basename(path),
                                           ref=job_sid, cancel=lambda: code_jobs.cancel(job_sid))
                try:
                    yield "data: " + json.dumps({"type": "start", "model": model, "root": ctx["root"]}) + "\n\n"
                    async for ev in stream_agent_loop(
                        url, model, messages, headers=headers, temperature=0.2,
                        max_rounds=max_rounds, disabled_tools=disabled,
                        owner=owner, workspace=path,
                    ):
                        if isinstance(ev, str):
                            yield ev
                finally:
                    activity.unregister(act_id)
            return _g()

        # history snapshot for server-side persistence on completion
        _hist = [h for h in (body.history or [])
                 if isinstance(h, dict) and h.get("role") in ("user", "assistant")]
        code_jobs.start(job_sid, _loop_factory, user_msg=msg, history=_hist)

        return StreamingResponse(code_jobs.stream(job_sid, 0), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    @router.get("/chat/attach")
    async def chat_attach(sid: str = Query(...), cursor: int = Query(0),
                          request: Request = None, _a: str = Depends(require_admin)):
        """Re-attach to a still-running (or just-finished) detached job and resume
        streaming from `cursor`. This is what makes a run survive ✕ / reload:
        reopen the window and you pick the live stream back up where it is."""
        from services.code import jobs as code_jobs
        return StreamingResponse(code_jobs.stream(sid, cursor), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    @router.get("/job")
    def chat_job_status(sid: str = Query(...), request: Request = None,
                        owner: str = Depends(get_current_user)):
        """Is there a detached run going for this window? Lets the UI show 'still
        working' and decide whether to re-attach on reopen."""
        from services.code import jobs as code_jobs
        return code_jobs.status(sid)

    @router.post("/job/stop")
    def chat_job_stop(sid: str = Query(...), request: Request = None,
                      _a: str = Depends(require_admin)):
        """Actually stop a detached run (Stop button) — since the work no longer
        lives in the request, aborting the client stream alone wouldn't halt it."""
        from services.code import jobs as code_jobs
        return {"stopped": code_jobs.cancel(sid)}

    # ───────────── Code Board sessions (tmux-style, ≤16 windows) ─────────────
    from services.code import sessions as sess_store

    @router.get("/sessions")
    def list_code_sessions(request: Request, owner: str = Depends(get_current_user)):
        from services.code import jobs as code_jobs
        sessions = sess_store.list_sessions()
        for s in sessions:
            s["running"] = code_jobs.is_running(s.get("id"))  # server truth, survives reload
        return {"sessions": sessions, "max": sess_store.MAX_SESSIONS}

    @router.get("/sessions/{sid}")
    def get_code_session(sid: str, request: Request, owner: str = Depends(get_current_user)):
        s = sess_store.get_session(sid)
        if not s:
            raise HTTPException(404, "session not found")
        from services.code import jobs as code_jobs
        st = code_jobs.status(sid)
        s["running"] = st["running"]
        s["job_cursor"] = st["cursor"]
        return s

    @router.post("/sessions")
    async def create_code_session(request: Request, _a: str = Depends(require_admin)):
        body = await request.json()
        try:
            return sess_store.create_session(body.get("root") or "", body.get("name"))
        except ValueError as e:
            raise HTTPException(400, str(e))
        except RuntimeError as e:
            raise HTTPException(409, str(e))

    @router.patch("/sessions/{sid}")
    async def update_code_session(sid: str, request: Request, _a: str = Depends(require_admin)):
        body = await request.json()
        try:
            ok = sess_store.update_session(sid, history=body.get("history"),
                                           name=body.get("name"), root=body.get("root"))
        except ValueError as e:
            raise HTTPException(400, str(e))
        if not ok:
            raise HTTPException(404, "session not found")
        return {"ok": True}

    @router.delete("/sessions/{sid}")
    def delete_code_session(sid: str, request: Request, _a: str = Depends(require_admin)):
        if not sess_store.delete_session(sid):
            raise HTTPException(404, "session not found")
        return {"ok": True}

    @router.post("/agents-md")
    def make_agents_md(body: dict, request: Request, _a: str = Depends(require_admin)):
        path = os.path.expanduser((body.get("path") or "").strip())
        if not path or not os.path.isdir(path):
            raise HTTPException(400, "not a folder")
        dest = os.path.join(path, "AGENTS.md")
        if os.path.exists(dest):
            return {"ok": True, "existed": True, "path": dest}
        ctx = repomap.build_context(path)
        desc = ""
        if ctx.get("readme"):
            desc = (ctx["readme"]["content"] or "").strip().split("\n\n")[0][:400]
        try:
            with open(dest, "w", encoding="utf-8") as f:
                f.write(_AGENTS_TEMPLATE.format(desc=desc or "(describe the project)"))
        except OSError as e:
            raise HTTPException(500, f"could not write AGENTS.md: {e}")
        repomap.build_context(path, rebuild=True)
        return {"ok": True, "existed": False, "path": dest}

    @router.post("/pi-md")
    def make_pi_md(body: dict, request: Request, _a: str = Depends(require_admin)):
        """Scaffold a per-project PI.md (Pi's CLAUDE.md). Read by the Code tab +
        workspace-scoped chat; takes precedence over AGENTS.md."""
        path = os.path.expanduser((body.get("path") or "").strip())
        if not path or not os.path.isdir(path):
            raise HTTPException(400, "not a folder")
        dest = os.path.join(path, "PI.md")
        if os.path.exists(dest):
            return {"ok": True, "existed": True, "path": dest}
        ctx = repomap.build_context(path)
        desc = ""
        if ctx.get("readme"):
            desc = (ctx["readme"]["content"] or "").strip().split("\n\n")[0][:400]
        try:
            with open(dest, "w", encoding="utf-8") as f:
                f.write(_PI_TEMPLATE.format(desc=desc or "(describe the project)"))
        except OSError as e:
            raise HTTPException(500, f"could not write PI.md: {e}")
        repomap.build_context(path, rebuild=True)
        return {"ok": True, "existed": False, "path": dest}

    return router
