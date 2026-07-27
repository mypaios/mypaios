"""Crew routes — the OpenClaw-style local agent mesh API.

Endpoints (all under /api/crew):
  GET  /agents      → roster + per-agent tool policy + routing snapshot
  GET  /status      → feature flags + available local models
  POST /plan        → decompose a goal into worker steps (for human approval)
  POST /run         → execute a (optionally pre-approved) plan, streaming SSE
  GET  /runs        → recent run audit list
  GET  /run/{id}    → full audit detail for one run

Mutations (plan/run) are admin-gated, matching the rest of PiAOS. The
plan→approve→run split is the human-in-the-loop gate: the UI shows the plan and
the user clicks Run before any worker (incl. code/shell steps) executes.
"""

from __future__ import annotations

import json
import logging
import os
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse

from core.middleware import require_admin
from src.auth_helpers import effective_user, get_current_user
from src.settings import load_settings
from services.crew import router as crew_router
from services.crew import store, supervisor
from services.crew.registry import list_agents

logger = logging.getLogger("crew.routes")


def _sse(obj: dict) -> str:
    return "data: " + json.dumps(obj, ensure_ascii=False) + "\n\n"


def setup_crew_routes() -> APIRouter:
    router = APIRouter(prefix="/api/crew", tags=["crew"])

    @router.get("/status")
    def crew_status(request: Request):
        get_current_user(request)  # populated by auth middleware; presence not required in single-user mode
        s = load_settings()
        return {
            "enabled": bool(s.get("crew_enabled", True)),
            "allow_cloud": bool(s.get("crew_allow_cloud", False)),
            "approval_mode": s.get("crew_approval_mode", "plan"),
            "max_steps": int(s.get("crew_max_steps", 5) or 5),
            "max_rounds_per_agent": int(s.get("crew_max_rounds_per_agent", 12) or 12),
            "supervisor_model": s.get("crew_supervisor_model", ""),
            "local_models": crew_router.available_local_models(),
        }

    @router.get("/agents")
    def crew_agents(request: Request):
        s = load_settings()
        owner = get_current_user(request)
        roster = []
        for a in list_agents():
            pub = a.to_public()
            url, model, _h, meta = crew_router.route_for_agent(a, owner, s)
            pub["routed_model"] = model
            pub["routed_source"] = meta.get("source")
            roster.append(pub)
        return {"agents": roster, "local_models": crew_router.available_local_models()}

    @router.post("/plan")
    async def crew_plan(request: Request, _admin: str = Depends(require_admin)):
        body = await request.json()
        goal = (body.get("goal") or "").strip()
        if not goal:
            raise HTTPException(400, "goal required")
        s = load_settings()
        if not s.get("crew_enabled", True):
            raise HTTPException(403, "Crew is disabled in settings")
        owner = effective_user(request)
        try:
            plan = await supervisor.plan(goal, owner, s)
        except Exception as e:  # noqa: BLE001
            logger.exception("crew plan failed")
            raise HTTPException(500, f"planning failed: {e}")
        return plan

    @router.post("/run")
    async def crew_run(request: Request, _admin: str = Depends(require_admin)):
        body = await request.json()
        goal = (body.get("goal") or "").strip()
        if not goal:
            raise HTTPException(400, "goal required")
        s = load_settings()
        if not s.get("crew_enabled", True):
            raise HTTPException(403, "Crew is disabled in settings")
        plan_obj = body.get("plan") if isinstance(body.get("plan"), dict) else None
        workspace = (body.get("workspace") or "").strip() or None
        if workspace and not os.path.isdir(os.path.expanduser(workspace)):
            raise HTTPException(400, f"workspace not found: {workspace}")
        if workspace:
            workspace = os.path.expanduser(workspace)
        owner = effective_user(request)
        run_id = uuid.uuid4().hex
        store.create_run(run_id, owner, goal, plan_obj)

        async def gen():
            from services import activity
            _cancel = {"stop": False}  # flipped by the Activity Stop button
            sid = activity.register("crew", None, goal[:60], ref=run_id,
                                    cancel=lambda: _cancel.__setitem__("stop", True))
            steps, final, used_cloud, status = [], "", False, "done"
            try:
                yield _sse({"type": "run_id", "run_id": run_id})
                async for ev in supervisor.run(goal, plan_obj, owner, workspace, s):
                    if _cancel["stop"]:
                        status = "stopped"
                        yield _sse({"type": "error", "message": "[stopped by user]"})
                        break
                    if ev.get("type") == "done":
                        final = ev.get("final", "")
                        used_cloud = bool(ev.get("used_cloud"))
                        steps = ev.get("steps", [])
                    yield _sse(ev)
            except Exception as e:  # noqa: BLE001
                logger.exception("crew run %s failed", run_id)
                status = "error"
                yield _sse({"type": "error", "message": str(e)})
            finally:
                activity.unregister(sid)
                try:
                    store.finish_run(run_id, status, steps, final, used_cloud)
                except Exception:  # noqa: BLE001
                    logger.exception("crew run %s: audit write failed", run_id)
                yield "data: [DONE]\n\n"

        return StreamingResponse(
            gen(), media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    @router.get("/runs")
    def crew_runs(request: Request):
        owner = get_current_user(request)
        return {"runs": store.list_runs(owner, limit=50)}

    @router.get("/run/{run_id}")
    def crew_run_detail(run_id: str, request: Request):
        owner = get_current_user(request)
        run = store.get_run(run_id, owner)
        if not run:
            raise HTTPException(404, "run not found")
        return run

    return router
