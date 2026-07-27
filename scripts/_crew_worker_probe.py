"""Probe ONE coder worker in isolation, through the Crew dispatch path.

Isolates 'does the coder worker produce correct files under the Crew persona +
task-wrapper framing' from planning/synthesis. Dumps the worker's full text,
tool events, the files it wrote, and the independent pytest result.
"""
import os, sys, asyncio, tempfile, subprocess, json

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(REPO); sys.path.insert(0, REPO)

from services.crew import router
from services.crew.registry import AGENTS
from src.agent_loop import stream_agent_loop


async def main():
    s = {"crew_enabled": True}
    agent = AGENTS["coder"]
    url, model, headers, meta = router.route_for_agent(agent, "admin", s)
    print("coder routed model:", model, "url:", url)

    ws = tempfile.mkdtemp(prefix="crew_probe_")
    goal = ("Create calc.py with a function add(a, b) that returns a + b, and "
            "tests/test_calc.py with a pytest asserting add(2, 3) == 5. Then run "
            "pytest -q and make sure it passes.")
    user_msg = f"OVERALL GOAL:\n{goal}\n\nYOUR SUBTASK:\n{goal}"
    messages = [
        {"role": "system", "content": agent.system_prompt},
        {"role": "user", "content": user_msg},
    ]
    tools, text = [], []
    async for raw in stream_agent_loop(
        url, model, messages, headers=headers, temperature=0.2, max_rounds=14,
        disabled_tools=set(agent.disabled_tools), owner="admin", workspace=ws,
    ):
        if not isinstance(raw, str) or not raw.startswith("data:"):
            continue
        body = raw[5:].strip()
        if body == "[DONE]":
            break
        try:
            d = json.loads(body)
        except Exception:
            continue
        if "delta" in d and isinstance(d["delta"], str):
            text.append(d["delta"])
        elif d.get("type") == "tool_start":
            tools.append(("start", d.get("tool"), (d.get("command") or "")[:60]))
        elif d.get("type") == "tool_output":
            tools.append(("out", d.get("tool"), "rc=" + str(d.get("exit_code"))))

    print("\n=== TOOL EVENTS ===")
    for t in tools:
        print(" ", t)
    print("\n=== WORKER TEXT (first 600) ===\n" + ("".join(text))[:600])
    print("\n=== FILES ===")
    print(subprocess.run(["find", ws, "-type", "f", "-not", "-path", "*/.*",
                          "-not", "-path", "*/__pycache__/*"], capture_output=True, text=True).stdout)
    for rel in ("calc.py", "tests/test_calc.py"):
        p = os.path.join(ws, rel)
        if os.path.exists(p):
            print(f"--- {rel} ---\n" + (open(p).read() or "(EMPTY)"))
    env = {**os.environ, "PYTHONPATH": ws + os.pathsep + os.environ.get("PYTHONPATH", "")}
    pt = subprocess.run([os.path.join(REPO, "venv", "bin", "pytest"), "-q"],
                        cwd=ws, capture_output=True, text=True, env=env)
    print("PYTEST rc=", pt.returncode, "\n" + (pt.stdout + pt.stderr)[-400:])
    print("=== WORKER PROBE:", "GREEN" if pt.returncode == 0 else "NOT GREEN", "===")


asyncio.run(asyncio.wait_for(main(), timeout=400))
