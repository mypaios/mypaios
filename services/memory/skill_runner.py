# services/memory/skill_runner.py
"""Run a script bundled inside a skill directory (scripts/<file>).

This is the EXECUTION half of Claude-style Skills. A skill ships runnable code
under its own ``scripts/`` dir and the agent RUNS it — only the script's stdout
enters the model's context, not its source — instead of re-deriving every step
from prose each time. That's the determinism + token saving that make skills
powerful.

Security model (single-user, local-first):
  * Path is resolved with a realpath + commonpath guard, so a skill can only run
    files that live inside its OWN ``scripts/`` directory (no traversal, no
    running another skill's or the app's files).
  * Runs in a subprocess with ``shell=False`` (no shell injection), ``cwd`` set
    to the skill dir, and a hard timeout.
  * Imported (untrusted) skills are quarantined at the CALLER (do_manage_skills)
    until the owner sets ``trusted_exec`` — this module assumes the caller has
    already cleared the skill for execution.
"""
from __future__ import annotations

import os
import sys
import subprocess
from typing import Dict, List, Optional

MAX_OUTPUT = 20_000           # cap stdout/stderr returned into context
DEFAULT_TIMEOUT = 120         # seconds

# Interpreter per extension. shell=False, explicit argv — no shell expansion.
_RUNNERS = {
    ".py": lambda t: [sys.executable, t],
    ".sh": lambda t: ["bash", t],
    ".bash": lambda t: ["bash", t],
    ".js": lambda t: ["node", t],
    ".mjs": lambda t: ["node", t],
}


def run_skill_script(
    skill_dir: str,
    script_rel: str,
    args: Optional[List[str]] = None,
    timeout: int = DEFAULT_TIMEOUT,
) -> Dict:
    """Resolve and run ``<skill_dir>/scripts/<script_rel>``.

    Returns ``{stdout, stderr, exit_code}`` on a run, or ``{error, exit_code}``
    if the script can't be resolved/started.
    """
    args = [str(a) for a in (args or [])]
    base = os.path.realpath(os.path.join(skill_dir, "scripts"))
    target = os.path.realpath(os.path.join(skill_dir, "scripts", script_rel))

    # Confine strictly to <skill_dir>/scripts/ — refuse traversal.
    try:
        if os.path.commonpath([base, target]) != base:
            return {"error": "script path escapes the skill's scripts/ directory", "exit_code": 1}
    except ValueError:
        # commonpath raises if paths are on different drives (Windows) — refuse.
        return {"error": "invalid script path", "exit_code": 1}
    if not os.path.isfile(target):
        return {"error": f"script not found: scripts/{script_rel}", "exit_code": 1}

    ext = os.path.splitext(target)[1].lower()
    builder = _RUNNERS.get(ext)
    if not builder:
        return {"error": f"unsupported script type {ext!r} (allowed: .py .sh .js)", "exit_code": 1}
    cmd = builder(target) + args

    env = dict(os.environ)
    env["PI_SKILL_DIR"] = skill_dir          # scripts can locate their own bundled assets
    try:
        proc = subprocess.run(
            cmd, cwd=skill_dir, capture_output=True, text=True,
            timeout=timeout, env=env,
        )
    except subprocess.TimeoutExpired:
        return {"error": f"script timed out after {timeout}s", "exit_code": 124}
    except FileNotFoundError as e:
        return {"error": f"interpreter not available: {e}", "exit_code": 127}
    except Exception as e:                    # noqa: BLE001 — surface any spawn failure
        return {"error": f"failed to run script: {e}", "exit_code": 1}

    return {
        "stdout": (proc.stdout or "")[:MAX_OUTPUT],
        "stderr": (proc.stderr or "")[:MAX_OUTPUT],
        "exit_code": proc.returncode,
    }


def list_skill_scripts(skill_dir: str) -> List[str]:
    """Return the runnable script files (relative names) under <skill_dir>/scripts/."""
    base = os.path.join(skill_dir, "scripts")
    out: List[str] = []
    if not os.path.isdir(base):
        return out
    for root, _dirs, files in os.walk(base):
        for f in files:
            ext = os.path.splitext(f)[1].lower()
            if ext in _RUNNERS:
                rel = os.path.relpath(os.path.join(root, f), base)
                out.append(rel)
    return sorted(out)
