"""Deny-by-default tool policy for Crew mini-agents.

The PiAOS agent loop accepts a `disabled_tools: Set[str]` that gates tools at
three layers (prompt assembly, schema filtering, execution). We express each
agent's privilege as an explicit DENY set built from capability groups, so a
weak local model can neither see nor invoke a tool outside its remit.

Two invariants hold for EVERY crew agent regardless of role:
  * It can never reconfigure PiAOS itself (endpoints, MCP, webhooks, tokens,
    settings, skills) — that would let an agent escalate its own privileges.
  * It can never serve/stop models or trigger research jobs.
This is the "least privilege by design / deny-by-default" posture.
"""

from __future__ import annotations

from typing import Set

# --- Capability groups (tool names as known to the agent loop) -------------

# App self-configuration & privilege-affecting tools — denied to ALL crew agents.
APP_CONTROL: Set[str] = {
    "manage_endpoints", "manage_mcp", "manage_webhooks", "manage_tokens",
    "manage_settings", "manage_skills", "manage_documents", "manage_calendar",
    "manage_contacts", "manage_research", "trigger_research",
    "download_model", "serve_model", "stop_served_model", "manage_endpoint",
}

# Anything that mutates state, runs code, or reaches the network.
WRITE_EXEC: Set[str] = {
    "bash", "python", "write_file", "edit_file",
    "create_document", "update_document", "suggest_document",
    "generate_image", "edit_image", "api_call",
    "manage_memory", "manage_tasks", "manage_notes",
}

# Read-only knowledge & inspection tools.
READ_ONLY: Set[str] = {
    "read_file", "grep", "glob", "ls",
    "search_chats", "vault_search", "vault_get",
    "web_search", "web_fetch",
}

# The full universe we know how to name (used to build a "block everything" set).
ALL_NAMED: Set[str] = APP_CONTROL | WRITE_EXEC | READ_ONLY


def disabled_for(role: str) -> Set[str]:
    """Return the set of tool names DISABLED for the given agent role.

    Unknown roles fall back to the most restrictive (no tools).
    """
    role = (role or "").strip().lower()

    if role == "coder":
        # Full coding in a workspace: shell, python, file read/write, search,
        # web docs lookups. Denied: app-control, image gen, arbitrary api_call,
        # doc-editor tools (use write_file instead), benign managers.
        return APP_CONTROL | {
            "generate_image", "edit_image", "api_call",
            "create_document", "update_document", "suggest_document",
            "manage_memory", "manage_tasks", "manage_notes",
        }

    if role == "ops":
        # Shell/automation in a workspace, read/write files, web. Denied:
        # app-control, image gen, arbitrary api_call, doc-editor tools.
        return APP_CONTROL | {
            "generate_image", "edit_image", "api_call",
            "create_document", "update_document", "suggest_document",
            "manage_memory", "manage_tasks", "manage_notes",
        }

    if role == "retriever":
        # Read-only knowledge retrieval (RAG / vault / files / web). No mutation.
        return APP_CONTROL | WRITE_EXEC

    if role == "planner":
        # Pure reasoning/synthesis — no tools at all.
        return set(ALL_NAMED)

    # Default: deny everything we know about.
    return set(ALL_NAMED)


def is_privileged(role: str) -> bool:
    """True if the role can run code or mutate the filesystem/network.

    Used by the approval gate: privileged steps are the ones a human should
    sign off on before they run.
    """
    role = (role or "").strip().lower()
    return role in {"coder", "ops"}
