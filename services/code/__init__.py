"""Code — project-aware coding workspace (Pi's 'Code' tab).

Brings agentic-coding best practices to Pi's local coder:
  * a repo MAP (Aider-style) so the agent knows the whole project
  * AGENTS.md / CLAUDE.md / README as a project "constitution" (Codex/Claude Code)
  * plan-first + diffs + test artifacts (Antigravity/Claude Code)
Reuses the proven Cowork agent engine (src.agent_loop + the coding model).
"""

from .repomap import build_context  # noqa: F401
