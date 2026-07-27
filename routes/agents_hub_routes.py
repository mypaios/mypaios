"""Agents hub — chat-based agent management, end to end.

The user types what they want in plain words ("every morning at 8 summarize the
top AI news"); a local LLM parses it into a command and the hub executes it
against Pi's EXISTING TaskScheduler engine — create / list / run / pause /
resume / delete — via loopback calls to /api/tasks (internal token +
X-PAIOS-Owner), so validation, scheduling, delivery and run history all reuse
the proven path. Agents == scheduler tasks; they also appear under Tasks.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request

from core.middleware import INTERNAL_TOOL_HEADER, INTERNAL_TOOL_TOKEN, require_admin
from src.auth_helpers import get_current_user

logger = logging.getLogger("agents.hub")

_BASE = "http://127.0.0.1:7860"

_PARSER_SYSTEM = """You are Pi's Agent Manager. The user manages automated agents in plain words.
Parse their message into ONE command and respond with ONLY a JSON object — no prose.

Schema:
{"action": "create" | "list" | "run" | "pause" | "resume" | "delete" | "help",
 "target": "<agent name the user referred to, for run/pause/resume/delete>",
 "task": {                      // only for create
   "name": "<short name>",
   "prompt": "<full instructions the agent will execute each run, written as a directive>",
   "task_type": "llm",          // "research" only if the user wants deep web research
   "trigger_type": "schedule",  // "webhook" if the user wants on-demand / manual only
   "schedule": "daily",         // once|daily|weekly|monthly|cron — omit if trigger_type=webhook
   "scheduled_time": "08:00",   // HH:MM 24h
   "scheduled_day": null,        // weekly: 0=Mon..6=Sun · monthly: 1-31
   "cron_expression": null,
   "output_target": "session"
 },
 "reply": "<one friendly sentence confirming what you did/understood>"}

Rules:
- If the user gives no schedule for a new agent, use trigger_type "webhook" (runs on demand) and say so in reply.
- "every morning"=daily, time defaults 08:00 if unsaid; "every monday"=weekly scheduled_day 0.
- For anything that's a question about agents or unclear → action "help" with a helpful reply.
"""


def _internal_headers(owner: Optional[str]) -> dict:
    h = {INTERNAL_TOOL_HEADER: INTERNAL_TOOL_TOKEN}
    if owner:
        h["X-PAIOS-Owner"] = owner
    return h


async def _proxy(method: str, path: str, owner: Optional[str], body: Optional[dict] = None):
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.request(method, _BASE + path, json=body, headers=_internal_headers(owner))
        try:
            data = r.json()
        except Exception:  # noqa: BLE001
            data = {"raw": r.text[:300]}
        return r.status_code, data


def _extract_json(text: str) -> Optional[dict]:
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text or "", re.S)
    cands = [m.group(1)] if m else []
    start = (text or "").find("{")
    if start != -1:
        depth = 0
        for i in range(start, len(text)):
            if text[i] == "{":
                depth += 1
            elif text[i] == "}":
                depth -= 1
                if depth == 0:
                    cands.append(text[start:i + 1])
                    break
    for c in cands:
        try:
            return json.loads(c)
        except Exception:  # noqa: BLE001
            continue
    return None


async def _parse_command(text: str, owner: Optional[str]) -> dict:
    """LLM-parse the user's message into a command dict."""
    from services.crew import router as crew_router
    from src.llm_core import llm_call_async
    from src.settings import load_settings
    url, model, headers, _meta = crew_router.supervisor_route(owner, dict(load_settings()))
    if not url:
        raise HTTPException(503, "No local model available to parse commands — install one in Local AI.")
    out = await llm_call_async(url, model,
                               [{"role": "system", "content": _PARSER_SYSTEM},
                                {"role": "user", "content": text}],
                               headers=headers, temperature=0.1, max_tokens=900)
    cmd = _extract_json(out or "")
    if not isinstance(cmd, dict) or not cmd.get("action"):
        raise HTTPException(422, "Could not understand that — try e.g. “every morning at 8 summarize the top AI news”.")
    return cmd


def _match_task(tasks: list, target: str) -> Optional[dict]:
    t = (target or "").strip().lower()
    if not t:
        return None
    exact = [x for x in tasks if (x.get("name") or "").lower() == t]
    if exact:
        return exact[0]
    sub = [x for x in tasks if t in (x.get("name") or "").lower()]
    return sub[0] if sub else None


async def _pinned_model(owner: Optional[str], heavy: bool = False) -> tuple[Optional[str], Optional[str]]:
    """(model, endpoint_url) to pin on a template install — both must be set
    for the scheduler to honor them (see the NOTE in the create path below).

    heavy=True routes to the crew CODER (qwen3-coder-next) instead of the
    generalist: verified 2026-06-10 that hermes3:8b in scheduler runs will
    sometimes acknowledge-instead-of-act or even HALLUCINATE tool output on
    tool-heavy prompts (file listings), while the coder model drives tools
    reliably. Tool-heavy template categories pay the bigger model's load
    time in exchange for runs that actually execute.
    """
    try:
        from services.crew import router as crew_router
        from services.crew.registry import AGENTS as CREW_AGENTS
        from src.settings import load_settings
        settings = dict(load_settings())
        if heavy:
            gurl, gmodel, _h, _m = crew_router.route_for_agent(CREW_AGENTS["coder"], owner, settings)
        else:
            gurl, gmodel, _h, _m = crew_router.supervisor_route(owner, settings)
        return (gmodel, gurl) if gurl and gmodel else (None, None)
    except Exception:  # noqa: BLE001
        return None, None


# Template categories whose prompts are tool-execution-heavy (bash/find/git/
# pytest) — these get the coder-grade model at install time.
_HEAVY_CATEGORIES = {"Files", "Code", "System"}


def _template_task_payload(tpl: dict, model: Optional[str], endpoint_url: Optional[str]) -> dict:
    """Map a prebuilt template onto the TaskCreate shape the hub already uses."""
    task = {
        "name": f"{tpl['emoji']} {tpl['name']}",
        "prompt": tpl["prompt"],
        "task_type": "llm",
        "output_target": "session",
    }
    sched = tpl.get("schedule")
    if sched:
        task["trigger_type"] = "schedule"
        task["schedule"] = sched.get("schedule", "daily")
        task["scheduled_time"] = sched.get("time", "09:00")
        if sched.get("day") is not None:
            task["scheduled_day"] = sched["day"]
    else:
        task["trigger_type"] = "webhook"  # on-demand: runs only via ▶
    if model and endpoint_url:
        task["model"] = model
        task["endpoint_url"] = endpoint_url
    return task


def setup_agents_hub_routes() -> APIRouter:
    router = APIRouter(prefix="/api/agents", tags=["agents"])

    @router.get("")
    async def list_agents(request: Request, owner: str = Depends(get_current_user)):
        code, data = await _proxy("GET", "/api/tasks", owner)
        if code != 200:
            raise HTTPException(code, str(data)[:200])
        return data

    @router.get("/templates")
    async def list_templates(request: Request, owner: str = Depends(get_current_user)):
        """Prebuilt gallery — every template plus whether it's already installed
        (matched by the exact task name the install path creates)."""
        from services.agent_templates import get_templates
        code, data = await _proxy("GET", "/api/tasks", owner)
        tasks = (data.get("tasks") if isinstance(data, dict) else data) or []
        existing = {(t.get("name") or "") for t in tasks}
        out = []
        for tpl in get_templates():
            out.append({
                "id": tpl["id"],
                "emoji": tpl["emoji"],
                "name": tpl["name"],
                "category": tpl["category"],
                "desc": tpl["desc"],
                "on_demand": tpl.get("schedule") is None,
                "schedule": tpl.get("schedule"),
                "needs": tpl.get("needs") or [],
                "installed": f"{tpl['emoji']} {tpl['name']}" in existing,
            })
        return {"templates": out}

    @router.post("/templates/install")
    async def install_template(request: Request, _a: None = Depends(require_admin)):
        """Install one template ({id}) or several ({ids:[...]}).

        Every install creates the task then immediately PAUSES it (user's
        chosen default) — on-demand ▶ runs still work on paused tasks, and
        scheduled ones only fire after the user resumes them.
        """
        from services.agent_templates import get_template
        body = await request.json()
        ids = body.get("ids") if isinstance(body.get("ids"), list) else None
        if ids is None:
            one = (body.get("id") or "").strip()
            if not one:
                raise HTTPException(400, "id or ids required")
            ids = [one]
        owner = get_current_user(request)
        model, endpoint_url = await _pinned_model(owner)
        heavy_model, heavy_url = await _pinned_model(owner, heavy=True)

        # Skip already-installed (same exact name) instead of duplicating.
        code, data = await _proxy("GET", "/api/tasks", owner)
        existing = {(t.get("name") or "") for t in ((data.get("tasks") if isinstance(data, dict) else data) or [])}

        installed, skipped, errors = [], [], []
        for tid in ids[:60]:
            tpl = get_template(tid)
            if not tpl:
                errors.append({"id": tid, "error": "unknown template"})
                continue
            display = f"{tpl['emoji']} {tpl['name']}"
            if display in existing:
                skipped.append(tid)
                continue
            if tpl.get("category") in _HEAVY_CATEGORIES and heavy_model and heavy_url:
                payload = _template_task_payload(tpl, heavy_model, heavy_url)
            else:
                payload = _template_task_payload(tpl, model, endpoint_url)
            code, data = await _proxy("POST", "/api/tasks", owner, payload)
            if code not in (200, 201):
                errors.append({"id": tid, "error": str(data.get("detail") if isinstance(data, dict) else data)[:160]})
                continue
            new_id = (data.get("task") or {}).get("id") if isinstance(data, dict) else None
            new_id = new_id or (data.get("id") if isinstance(data, dict) else None)
            if new_id:
                await _proxy("POST", f"/api/tasks/{new_id}/pause", owner)
            installed.append({"id": tid, "task_id": new_id, "name": display})
            existing.add(display)
        return {"ok": not errors, "installed": installed, "skipped": skipped, "errors": errors}

    @router.get("/{task_id}/last-run")
    async def last_run(task_id: str, request: Request, owner: str = Depends(get_current_user)):
        code, data = await _proxy("GET", f"/api/tasks/{task_id}/runs", owner)
        if code != 200:
            raise HTTPException(code, str(data)[:200])
        runs = data.get("runs") if isinstance(data, dict) else data
        return {"run": (runs or [None])[0]}

    @router.post("/command")
    async def command(request: Request, _a: None = Depends(require_admin)):
        body = await request.json()
        text = (body.get("text") or "").strip()
        if not text:
            raise HTTPException(400, "text required")
        owner = get_current_user(request)
        cmd = await _parse_command(text, owner)
        action = (cmd.get("action") or "help").lower()
        reply = cmd.get("reply") or ""
        ok = True

        if action == "create":
            task = cmd.get("task") or {}
            if not task.get("prompt"):
                raise HTTPException(422, "I understood you want a new agent but not what it should do — say what it should do each run.")
            task.setdefault("task_type", "llm")
            task.setdefault("output_target", "session")
            # Pin hub-created agents to the verified local generalist (hermes3)
            # rather than whatever the global default model happens to be.
            # NOTE the scheduler ignores task.model unless endpoint_url is ALSO
            # set (_execute_llm_task falls back to defaults if either is missing)
            # — so pin both.
            if not task.get("model") or not task.get("endpoint_url"):
                try:
                    from services.crew import router as crew_router
                    from src.settings import load_settings
                    gurl, gmodel, _h, _m = crew_router.supervisor_route(owner, dict(load_settings()))
                    if gurl and gmodel:
                        task.setdefault("model", gmodel)
                        task.setdefault("endpoint_url", gurl)
                except Exception:  # noqa: BLE001
                    pass
            if task.get("trigger_type") == "webhook":
                task.pop("schedule", None)
                task.pop("cron_expression", None)
            else:
                task.setdefault("trigger_type", "schedule")
                task.setdefault("schedule", "daily")
                task.setdefault("scheduled_time", "08:00")
            code, data = await _proxy("POST", "/api/tasks", owner, task)
            if code not in (200, 201):
                ok = False
                reply = f"Couldn't create the agent: {str(data.get('detail') if isinstance(data, dict) else data)[:160]}"
        elif action in ("run", "pause", "resume", "delete"):
            code, data = await _proxy("GET", "/api/tasks", owner)
            tasks = data.get("tasks") if isinstance(data, dict) else data
            tasks = tasks or []
            hit = _match_task(tasks, cmd.get("target") or "")
            if not hit:
                ok = False
                reply = f"I couldn't find an agent matching “{cmd.get('target') or '?'}”."
            else:
                tid = hit.get("id")
                if action == "delete":
                    code, data = await _proxy("DELETE", f"/api/tasks/{tid}", owner)
                elif action == "run":
                    code, data = await _proxy("POST", f"/api/tasks/{tid}/run", owner)
                else:
                    code, data = await _proxy("POST", f"/api/tasks/{tid}/{action}", owner)
                if code != 200:
                    ok = False
                    reply = f"{action} failed: {str(data.get('detail') if isinstance(data, dict) else data)[:160]}"
                elif not reply:
                    reply = f"Done — {action} “{hit.get('name')}”."
        elif action == "list":
            reply = reply or "Here are your agents."
        else:
            reply = reply or ("I manage your agents. Try: “every morning at 8 summarize the top AI news”, "
                              "“run the news agent now”, “pause the news agent”, or “delete the news agent”.")

        code, data = await _proxy("GET", "/api/tasks", owner)
        agents = (data.get("tasks") if isinstance(data, dict) else data) or []
        return {"ok": ok, "action": action, "reply": reply, "agents": agents}

    return router
