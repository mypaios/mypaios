"""Supervisor — decomposes a goal, dispatches to mini-agents, synthesizes.

Flow (human-in-the-loop friendly):
  1. plan(goal)         → one Planner LLM call returns an ordered list of steps,
                          each assigned to a worker (retriever/coder/ops). The UI
                          shows this for approval before anything runs.
  2. run(goal, plan)    → async generator. For each step it routes a model
                          (local-first), runs the worker via the existing agent
                          loop with that worker's tool policy + persona, forwards
                          progress, and collects the result. Finally it makes one
                          Planner synthesis call combining all step results.

Every worker reuses src.agent_loop.stream_agent_loop, so coding steps ARE Cowork,
retrieval steps use the same RAG/vault/web tools, etc. — no duplicated machinery.
"""

from __future__ import annotations

import json
import logging
import re
from typing import AsyncGenerator, Dict, List, Optional

from . import router
from .policy import ALL_NAMED
from .registry import AGENTS, WORKER_ROLES, get_agent

logger = logging.getLogger("crew.supervisor")

_CONTEXT_CHARS = 4000      # how much prior-step context to feed the next worker
_RESULT_CHARS = 6000       # cap a single worker's collected result


class CrewError(Exception):
    pass


def _extract_json(text: str) -> Optional[dict]:
    """Pull the first balanced {...} JSON object out of a model response."""
    if not text:
        return None
    # fenced ```json block first
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.S)
    candidates = []
    if m:
        candidates.append(m.group(1))
    # first brace-balanced object
    start = text.find("{")
    if start != -1:
        depth = 0
        for i in range(start, len(text)):
            if text[i] == "{":
                depth += 1
            elif text[i] == "}":
                depth -= 1
                if depth == 0:
                    candidates.append(text[start:i + 1])
                    break
    for c in candidates:
        try:
            return json.loads(c)
        except Exception:  # noqa: BLE001
            continue
    return None


def _heuristic_step(goal: str) -> Dict:
    g = (goal or "").lower()
    if any(k in g for k in ("code", "implement", "build", "fix", "refactor", "test", "function", "bug", "script ")):
        agent = "coder"
    elif any(k in g for k in ("run ", "install", "format", "convert", "move ", "rename", "execute", "command", "automation")):
        agent = "ops"
    else:
        agent = "retriever"
    return {"agent": agent, "task": goal, "why": "single-step heuristic fallback"}


async def _consume(stream) -> AsyncGenerator[dict, None]:
    """Parse the agent loop's SSE strings into event dicts."""
    async for raw in stream:
        if not isinstance(raw, str) or not raw.startswith("data:"):
            continue
        body = raw[5:].strip()
        if body == "[DONE]":
            return
        try:
            yield json.loads(body)
        except Exception:  # noqa: BLE001
            continue


async def _complete(messages: List[dict], url: str, model: str, headers: dict,
                    owner: Optional[str], max_rounds: int = 1) -> str:
    """Run a pure-reasoning (no tools) completion and return the text."""
    from src.agent_loop import stream_agent_loop
    out: List[str] = []
    stream = stream_agent_loop(
        url, model, messages, headers=headers, temperature=0.2,
        max_rounds=max_rounds, disabled_tools=set(ALL_NAMED),
        relevant_tools=set(), owner=owner,
    )
    async for d in _consume(stream):
        if "delta" in d and isinstance(d["delta"], str):
            out.append(d["delta"])
    return "".join(out).strip()


async def plan(goal: str, owner: Optional[str], settings: Dict) -> Dict:
    """Produce an ordered plan of worker steps for a goal."""
    max_steps = int(settings.get("crew_max_steps", 5) or 5)
    url, model, headers, meta = router.supervisor_route(owner, settings)
    if not url:
        # No model available — return a heuristic single-step plan so the UI still works.
        return {"steps": [_heuristic_step(goal)], "synthesis": "Summarize the result for the user.",
                "routed": False, "note": "No local model resolved; using heuristic plan."}

    sys = (
        AGENTS["planner"].system_prompt +
        "\n\nDecompose the user's goal into 1-" + str(max_steps) + " ordered steps. "
        "Assign each step to exactly one worker:\n"
        "- retriever: find/look up/summarize info from files, the knowledge base, past chats, or the web (READ ONLY).\n"
        "- coder: write/edit code and run tests in the active workspace.\n"
        "- ops: run shell commands / automation in the active workspace.\n\n"
        "Respond with ONLY a JSON object, no prose:\n"
        '{"steps":[{"agent":"retriever|coder|ops","task":"<imperative subtask>","why":"<1 line>"}],'
        '"synthesis":"<how to combine the results into the final answer>"}'
    )
    messages = [{"role": "system", "content": sys}, {"role": "user", "content": goal}]
    try:
        raw = await _complete(messages, url, model, headers, owner, max_rounds=1)
    except Exception as e:  # noqa: BLE001
        logger.warning("crew.plan: completion failed: %s", e)
        raw = ""

    parsed = _extract_json(raw) or {}
    steps = parsed.get("steps") if isinstance(parsed.get("steps"), list) else None
    clean: List[Dict] = []
    for s in (steps or []):
        if not isinstance(s, dict):
            continue
        agent = str(s.get("agent", "")).strip().lower()
        if agent not in WORKER_ROLES:
            agent = "retriever"
        task = str(s.get("task", "")).strip()
        if not task:
            continue
        clean.append({"agent": agent, "task": task, "why": str(s.get("why", "")).strip()})
        if len(clean) >= max_steps:
            break
    if not clean:
        clean = [_heuristic_step(goal)]
    return {
        "steps": clean,
        "synthesis": str(parsed.get("synthesis", "")).strip() or "Combine the step results into one clear answer for the user.",
        "routed": True,
        "supervisor_model": meta.get("model"),
    }


async def run(
    goal: str,
    plan_obj: Optional[Dict],
    owner: Optional[str],
    workspace: Optional[str],
    settings: Dict,
) -> AsyncGenerator[dict, None]:
    """Execute a plan step-by-step, streaming progress event dicts.

    Yields dicts with a "type" field (run_start, step_start, delta, tool,
    step_done, warning, synthesis_start, delta_final, done, error). The caller
    serializes them as SSE.
    """
    from src.agent_loop import stream_agent_loop

    max_rounds = int(settings.get("crew_max_rounds_per_agent", 12) or 12)
    if plan_obj is None:
        plan_obj = await plan(goal, owner, settings)
    steps = plan_obj.get("steps") or [_heuristic_step(goal)]

    yield {"type": "run_start", "goal": goal, "plan": plan_obj}

    step_records: List[Dict] = []
    used_cloud = False
    context_parts: List[str] = []

    for idx, step in enumerate(steps):
        agent = get_agent(step.get("agent", "retriever")) or AGENTS["retriever"]
        url, model, headers, rmeta = router.route_for_agent(agent, owner, settings)
        if rmeta.get("is_cloud"):
            used_cloud = True

        if not url:
            msg = f"No model available for {agent.name} (local-first; cloud fallback {'on' if settings.get('crew_allow_cloud') else 'off'})."
            yield {"type": "warning", "index": idx, "message": msg}
            step_records.append({"index": idx, "agent": agent.id, "task": step.get("task"),
                                 "model": None, "result": f"[skipped] {msg}", "ok": False})
            continue

        step_ws = workspace if agent.needs_workspace else None
        if agent.needs_workspace and not step_ws:
            yield {"type": "warning", "index": idx,
                   "message": f"{agent.name} works best with a workspace folder; none set, running in the confined sandbox."}

        yield {"type": "step_start", "index": idx, "agent": agent.id, "agent_name": agent.name,
               "task": step.get("task"), "model": model, "is_cloud": rmeta.get("is_cloud", False),
               "needs_workspace": agent.needs_workspace, "workspace": step_ws}

        prior = ("\n\n".join(context_parts))[-_CONTEXT_CHARS:]
        user_msg = (
            f"OVERALL GOAL:\n{goal}\n\n"
            + (f"RESULTS SO FAR (from earlier crew steps):\n{prior}\n\n" if prior else "")
            + f"YOUR SUBTASK:\n{step.get('task')}"
        )
        messages = [
            {"role": "system", "content": agent.system_prompt},
            {"role": "user", "content": user_msg},
        ]

        collected: List[str] = []
        try:
            stream = stream_agent_loop(
                url, model, messages, headers=headers, temperature=0.2,
                max_rounds=max_rounds,
                disabled_tools=set(agent.disabled_tools),   # COPY: loop mutates this set
                owner=owner, workspace=step_ws,
            )
            async for d in _consume(stream):
                t = d.get("type")
                if "delta" in d and isinstance(d["delta"], str):
                    collected.append(d["delta"])
                    yield {"type": "delta", "index": idx, "text": d["delta"]}
                elif t == "tool_start":
                    yield {"type": "tool", "index": idx, "status": "start",
                           "tool": d.get("tool"), "detail": d.get("command", "")}
                elif t == "tool_output":
                    yield {"type": "tool", "index": idx, "status": "output",
                           "tool": d.get("tool"),
                           "detail": str(d.get("output", ""))[:400],
                           "exit_code": d.get("exit_code")}
                elif t == "error":
                    yield {"type": "warning", "index": idx, "message": str(d.get("error", "error"))}
        except Exception as e:  # noqa: BLE001
            logger.exception("crew step %d (%s) failed", idx, agent.id)
            yield {"type": "warning", "index": idx, "message": f"{agent.name} error: {e}"}

        result = "".join(collected).strip()[:_RESULT_CHARS] or "(no output)"
        step_records.append({"index": idx, "agent": agent.id, "task": step.get("task"),
                             "model": model, "is_cloud": rmeta.get("is_cloud", False),
                             "result": result, "ok": True})
        context_parts.append(f"[{agent.name}] {result}")
        yield {"type": "step_done", "index": idx, "agent": agent.id, "result": result}

    # --- Synthesis ---------------------------------------------------------
    final = ""
    yield {"type": "synthesis_start"}
    surl, smodel, sheaders, smeta = router.supervisor_route(owner, settings)
    if smeta.get("is_cloud"):
        used_cloud = True
    if surl and step_records:
        joined = "\n\n".join(f"### {r['agent']} (step {r['index']+1})\n{r['result']}" for r in step_records)
        syn_sys = (
            AGENTS["planner"].system_prompt +
            "\nWrite the FINAL answer for the user by combining the crew's step "
            "results below. Be direct and complete. Do not mention the crew's "
            "internal mechanics unless useful."
        )
        syn_user = (f"GOAL:\n{goal}\n\nSYNTHESIS GUIDANCE:\n{plan_obj.get('synthesis','')}\n\n"
                    f"STEP RESULTS:\n{joined}")
        try:
            async for d in _consume(stream_agent_loop(
                surl, smodel, [{"role": "system", "content": syn_sys},
                               {"role": "user", "content": syn_user}],
                headers=sheaders, temperature=0.3, max_rounds=1,
                disabled_tools=set(__import__('services.crew.policy', fromlist=['ALL_NAMED']).ALL_NAMED),
                relevant_tools=set(), owner=owner,
            )):
                if "delta" in d and isinstance(d["delta"], str):
                    final += d["delta"]
                    yield {"type": "delta_final", "text": d["delta"]}
        except Exception as e:  # noqa: BLE001
            logger.warning("crew synthesis failed: %s", e)

    if not final.strip():
        # Fallback: concatenate step results.
        final = "\n\n".join(f"**{r['agent'].title()}** — {r['result']}" for r in step_records) or "(no result)"
        yield {"type": "delta_final", "text": final}

    yield {"type": "done", "final": final.strip(), "used_cloud": used_cloud, "steps": step_records}
