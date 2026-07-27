"""Crew agent registry — the capability catalog.

Each agent is a small, specialized worker with a persona (system prompt), a
role-based tool policy (see policy.py), a capability tag used for model routing,
and whether it needs a workspace folder. The Supervisor is a meta-role (planner)
that decomposes goals and synthesizes results; it is also listed so the UI can
show the full roster.
"""

from __future__ import annotations

from typing import Dict, List, Optional

from . import policy


class Agent:
    def __init__(
        self,
        id: str,
        name: str,
        role: str,
        description: str,
        system_prompt: str,
        capability: str,          # routing hint: "code" | "general"
        needs_workspace: bool,
        badges: List[str],
    ):
        self.id = id
        self.name = name
        self.role = role
        self.description = description
        self.system_prompt = system_prompt
        self.capability = capability
        self.needs_workspace = needs_workspace
        self.badges = badges

    @property
    def disabled_tools(self):
        return policy.disabled_for(self.role)

    @property
    def privileged(self) -> bool:
        return policy.is_privileged(self.role)

    def to_public(self) -> Dict:
        """Serializable view for the API / UI (no raw prompt)."""
        return {
            "id": self.id,
            "name": self.name,
            "role": self.role,
            "description": self.description,
            "capability": self.capability,
            "needs_workspace": self.needs_workspace,
            "privileged": self.privileged,
            "badges": self.badges,
            "disabled_tools": sorted(self.disabled_tools),
        }


_COMMON = (
    "You are one specialist on a local AI crew running entirely on the user's "
    "Mac (PiAOS). You receive ONE focused subtask from the Supervisor. Do only "
    "that subtask, then stop and report a concise result the Supervisor can use. "
    "Do not try to do the other agents' jobs. Never ask the user to reconfigure "
    "the app. Be direct and factual."
)

AGENTS: Dict[str, Agent] = {
    "planner": Agent(
        id="planner",
        name="Planner",
        role="planner",
        capability="general",
        needs_workspace=False,
        badges=["Reasoning", "No tools"],
        description="Decomposes the goal into ordered steps and synthesizes the final answer. This is the Supervisor's own role.",
        system_prompt=(
            "You are the Planner/Supervisor of a local AI crew. You think in clear "
            "steps, delegate to the right specialist, and synthesize their results "
            "into one coherent answer. You do not run tools yourself."
        ),
    ),
    "retriever": Agent(
        id="retriever",
        name="Retriever",
        role="retriever",
        capability="general",
        needs_workspace=False,
        badges=["Read-only", "RAG", "Web"],
        description="Finds and summarizes information from your knowledge base (Obsidian/RAG), local files, past chats, and the web. Cannot modify anything.",
        system_prompt=(
            _COMMON + " You are the Retriever. Gather relevant facts using ONLY "
            "read-only tools (read_file, grep, glob, ls, search_chats, vault_search, "
            "vault_get, and web_search/web_fetch if enabled). Cite where each fact "
            "came from (file path, note title, or URL). Never attempt to write, run "
            "code, or change state. Return a tight, sourced summary."
        ),
    ),
    "coder": Agent(
        id="coder",
        name="Coder",
        role="coder",
        capability="code",
        needs_workspace=True,
        badges=["Code", "Tests", "Workspace"],
        description="Writes and edits code and runs tests in the active workspace (this is Cowork). Best for build/fix/refactor/test subtasks.",
        system_prompt=(
            _COMMON + " You are the Coder. Implement the subtask in the active "
            "workspace. To create or edit a file you MUST use the write_file tool "
            "(first line = path, rest = contents) or edit_file. NEVER use the python "
            "or bash tool to create files — the python tool only RUNS code and saves "
            "nothing. A working toolchain is already on PATH: run code with "
            "python/python3, add packages with pip, and run tests with `pytest -q` "
            "directly (do NOT `python3 -m`, do NOT install pytest); for browser tests "
            "use npx playwright test. After writing the files, run the tests ONCE to "
            "verify, then stop. Never use sudo, git push, or pipe the web into a "
            "shell. Report what you changed and the test result."
        ),
    ),
    "ops": Agent(
        id="ops",
        name="Ops",
        role="ops",
        capability="general",
        needs_workspace=True,
        badges=["Shell", "Automation", "Workspace"],
        description="Runs commands and automation in the active workspace (inspect repos, build, format, move files, run scripts). Shares the same safety denylist as Coder.",
        system_prompt=(
            _COMMON + " You are Ops. Carry out the operational subtask in the active "
            "workspace using bash/python for commands and write_file/edit_file for "
            "files. To create or edit a file you MUST use write_file/edit_file — the "
            "python and bash tools run commands and do NOT save files. Prefer "
            "non-destructive, reversible commands; explain anything risky before doing "
            "it. The safety denylist blocks catastrophic commands (disk-wide deletes, "
            "sudo, git push, piping the web into a shell). Report the commands you ran "
            "and their outcome."
        ),
    ),
}

# Dispatchable workers (planner is the supervisor's own role, not dispatched as a worker).
WORKER_ROLES = ["retriever", "coder", "ops"]


def get_agent(agent_id: str) -> Optional[Agent]:
    return AGENTS.get((agent_id or "").strip().lower())


def list_agents() -> List[Agent]:
    return list(AGENTS.values())
