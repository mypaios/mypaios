"""Local-first model router for the Crew.

Policy (matches the agreed design):
  * LOCAL FIRST — always prefer a model served by local Ollama.
  * Capability-aware — a "code" subtask routes to a coding model (qwen2.5-coder
    etc.) when one is installed; "general" subtasks route to a general chat model.
  * Cloud fallback is OFF by default — only used when `crew_allow_cloud` is true
    AND no suitable local model resolves. Every cloud use is surfaced/audited by
    the supervisor.

The router returns a `(endpoint_url, model_id, headers)` triple ready to hand to
`src.agent_loop.stream_agent_loop`.
"""

from __future__ import annotations

import logging
from typing import Dict, List, Optional, Tuple

import httpx

logger = logging.getLogger("crew.router")

_OLLAMA_BASE = "http://localhost:11434"
_OLLAMA_CHAT_URL = _OLLAMA_BASE + "/v1/chat/completions"

# substrings that mark a model as coding-specialized
_CODE_HINTS = ("coder", "code", "devstral", "deepseek-coder", "starcoder")
# general-purpose families we prefer for reasoning/synthesis. hermes leads —
# Nous Hermes is a tool-calling generalist (verified native tool_calls 2026-06-07),
# the best fit for planner/retriever/ops roles.
_GENERAL_HINTS = ("hermes", "qwen3", "qwen2.5", "llama", "gemma", "mistral", "phi", "gpt-oss")
# Models MEASURED to mis-drive PiAOS's tool-call protocol (they emit non-PiAOS
# tool names / ramble instead of using write_file). The crew avoids them for
# ALL steps (tool use + planning/synthesis), falling back to them only if no
# other local model exists. (gpt-oss:20b went 0/3 in the Cowork bake-off.)
_WEAK_AT_TOOLS = ("gpt-oss",)


def available_local_models() -> List[str]:
    """Names of models currently served by local Ollama (best-effort)."""
    try:
        r = httpx.get(_OLLAMA_BASE + "/api/tags", timeout=3.0)
        r.raise_for_status()
        data = r.json() or {}
        return [m.get("name", "") for m in data.get("models", []) if m.get("name")]
    except Exception as e:  # noqa: BLE001 — Ollama may be down; degrade gracefully
        logger.info("crew.router: ollama tags unavailable: %s", e)
        return []


def _best_local(capability: str, settings: Dict, models: List[str]) -> Optional[str]:
    """Choose the best local model name for a capability, or None."""
    if not models:
        return None
    cap = (capability or "general").lower()

    # Explicit CREW overrides win — but do NOT inherit the global `default_model`
    # (often a chat model like gpt-oss that mis-drives tools). Only an explicit
    # crew_* setting forces a model; otherwise fall through to capability + the
    # weak-at-tools exclusion below.
    if cap == "code":
        pref = (settings.get("crew_coder_model") or "").strip()
    else:
        pref = (settings.get("crew_supervisor_model") or "").strip()
    if pref and any(pref == m or pref in m for m in models):
        return next(m for m in models if pref == m or pref in m)

    # Drop models known to mis-drive PiAOS tools — unless that empties the list,
    # in which case we have no better option and keep them.
    candidates = [m for m in models if not any(w in m.lower() for w in _WEAK_AT_TOOLS)] or models
    lower = [(m, m.lower()) for m in candidates]
    coders = [m for m, lo in lower if any(h in lo for h in _CODE_HINTS)]
    if cap == "code" and coders:
        coders.sort(key=_size_rank, reverse=True)
        return coders[0]
    # general: prefer a non-coder general instruct model, else a coder, else any
    generals = [m for m, lo in lower
                if any(h in lo for h in _GENERAL_HINTS) and not any(h in lo for h in _CODE_HINTS)]
    if generals:
        generals.sort(key=_size_rank, reverse=True)
        return generals[0]
    if coders:
        coders.sort(key=_size_rank, reverse=True)
        return coders[0]
    return candidates[0]


def _size_rank(name: str) -> float:
    """Rough size from a model name like 'qwen2.5-coder:14b' → 14.0 (for sorting)."""
    import re
    m = re.search(r"(\d+(?:\.\d+)?)\s*b", name.lower())
    return float(m.group(1)) if m else 0.0


def resolve(model_name: str, owner: Optional[str]) -> Optional[Tuple[str, str, Dict]]:
    """Resolve a model name to (url, model, headers).

    Tries PiAOS's endpoint resolver first (honors registered endpoints, owner
    scoping, headers). Falls back to a direct local-Ollama OpenAI-compatible URL
    so the crew still works even if no Ollama endpoint row is registered.
    """
    try:
        from src.ai_interaction import _resolve_model
        return _resolve_model(model_name, owner=owner)
    except Exception as e:  # noqa: BLE001
        logger.info("crew.router: _resolve_model('%s') failed (%s); trying direct Ollama", model_name, e)
    # Direct Ollama fallback only if the model is actually served locally.
    if model_name in available_local_models():
        return (_OLLAMA_CHAT_URL, model_name, {})
    return None


def route_for_agent(
    agent, owner: Optional[str], settings: Dict
) -> Tuple[Optional[str], Optional[str], Optional[Dict], Dict]:
    """Pick and resolve a model for an agent.

    Returns (url, model, headers, meta) where meta describes the routing decision
    for the audit trail. (url/model/headers are None if nothing resolved.)
    """
    capability = getattr(agent, "capability", "general")
    models = available_local_models()
    chosen = _best_local(capability, settings, models)
    meta = {"capability": capability, "local_models": len(models), "is_cloud": False}

    if chosen:
        resolved = resolve(chosen, owner)
        if resolved:
            meta["model"] = chosen
            meta["source"] = "local"
            return resolved[0], resolved[1], resolved[2], meta

    # No local model resolved → policy-gated cloud fallback.
    if settings.get("crew_allow_cloud"):
        cloud_pref = (settings.get("crew_cloud_model") or settings.get("default_model") or "").strip()
        if cloud_pref:
            resolved = resolve(cloud_pref, owner)
            if resolved:
                meta["model"] = cloud_pref
                meta["source"] = "cloud"
                meta["is_cloud"] = True
                return resolved[0], resolved[1], resolved[2], meta

    meta["source"] = "none"
    return None, None, None, meta


def supervisor_route(owner: Optional[str], settings: Dict) -> Tuple[Optional[str], Optional[str], Optional[Dict], Dict]:
    """Route for the Supervisor's own planning/synthesis calls (general capability)."""
    from .registry import AGENTS
    return route_for_agent(AGENTS["planner"], owner, settings)
