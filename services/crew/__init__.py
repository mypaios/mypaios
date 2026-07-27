"""Crew — PiAOS-native multi-agent mesh (OpenClaw-style, local-first).

A Supervisor decomposes a goal into steps and dispatches each to a specialized
mini-agent (Planner / Coder / Retriever / Ops). Every worker reuses the existing
PiAOS agent loop (`src.agent_loop.stream_agent_loop`) with a per-agent persona and
a deny-by-default tool allowlist. Models are routed local-first (Ollama) with
policy-gated cloud fallback (off by default). Runs are audited to data/crew.db.

This package is single-operator / local-first by design — it intentionally does
NOT implement the multi-tenant gateway/mesh hardening (K8s/Vault/SPIRE/gRPC/NATS)
that only matters for hostile multi-tenancy.
"""

from .registry import AGENTS, get_agent, list_agents  # noqa: F401
