"""Standalone Crew verification: planning + multi-agent run end-to-end.

Proves: (1) the Supervisor decomposes a goal into structured worker steps;
(2) run() dispatches to a worker via the real agent loop, the worker uses tools
in the workspace, and synthesis yields a final answer; (3) the worker's output
is independently correct (pytest green).
"""
import os, sys, asyncio, tempfile, subprocess

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(REPO); sys.path.insert(0, REPO)

from src.settings import load_settings
from services.crew import supervisor, router


async def main():
    s = dict(load_settings())
    s.update({"crew_max_steps": 2, "crew_max_rounds_per_agent": 14, "crew_enabled": True})

    print("local models:", router.available_local_models())

    # --- Test 1: planning produces structured steps ---
    plan = await supervisor.plan(
        "Find the TODO comments in this project and fix the simplest one, with a test.",
        owner="admin", settings=s)
    print("PLAN routed:", plan.get("routed"), "supervisor_model:", plan.get("supervisor_model"))
    for st in plan.get("steps", []):
        print("  -", st.get("agent"), "::", (st.get("task") or "")[:60])
    plan_ok = bool(plan.get("steps"))

    # --- Test 2: run a small coding goal through the mesh, in a temp workspace ---
    ws = tempfile.mkdtemp(prefix="crew_verify_")
    goal = ("Create calc.py with a function add(a, b) that returns a + b, and "
            "tests/test_calc.py with a pytest asserting add(2, 3) == 5. Then run "
            "pytest -q and make sure it passes.")
    events, final, steps = [], "", []
    async for ev in supervisor.run(goal, None, "admin", ws, s):
        t = ev.get("type"); events.append(t)
        if t == "step_start":
            print(f"  step {ev['index']} -> {ev['agent']} (model={ev.get('model')}, cloud={ev.get('is_cloud')})")
        elif t == "tool":
            print(f"    tool {ev.get('status')}: {ev.get('tool')}")
        elif t == "warning":
            print(f"    ⚠ {ev.get('message')}")
        elif t == "done":
            final = ev.get("final", ""); steps = ev.get("steps", [])

    print("EVENT TYPES:", sorted(set(events)))
    files = subprocess.run(["find", ws, "-type", "f", "-not", "-path", "*/.*",
                            "-not", "-path", "*/__pycache__/*"], capture_output=True, text=True).stdout
    print("FILES:\n" + files)
    for rel in ("calc.py", "tests/test_calc.py"):
        p = os.path.join(ws, rel)
        if os.path.exists(p):
            print(f"--- {rel} ---\n" + (open(p).read() or "(EMPTY)"))
    env = {**os.environ, "PYTHONPATH": ws + os.pathsep + os.environ.get("PYTHONPATH", "")}
    pt = subprocess.run([os.path.join(REPO, "venv", "bin", "pytest"), "-q"],
                        cwd=ws, capture_output=True, text=True, env=env)
    print("PYTEST rc=", pt.returncode, "\nSTDOUT+ERR:\n" + (pt.stdout + "\n" + pt.stderr)[-600:])
    print("FINAL (first 400):\n" + (final or "")[:400])

    run_ok = ("done" in events) and ("step_start" in events) and bool(final.strip())
    code_ok = (pt.returncode == 0)
    print(f"\n=== CREW RESULT: plan={'PASS' if plan_ok else 'FAIL'} | "
          f"run_orchestration={'PASS' if run_ok else 'FAIL'} | "
          f"worker_code_green={'PASS' if code_ok else 'FAIL'} ===")


asyncio.run(asyncio.wait_for(main(), timeout=600))
