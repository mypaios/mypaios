"""Verify the Code tab's project-aware agent: (1) it ANSWERS project questions from
the injected repo map alone (tools off), (2) it can EDIT using that context (tools on)."""
import os, sys, asyncio, tempfile, subprocess, json

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(REPO); sys.path.insert(0, REPO)

from src.settings import load_settings
from services.code import repomap
from services.crew import router as crew_router
from services.crew.registry import AGENTS as CREW
from services.crew.policy import ALL_NAMED
from src.agent_loop import stream_agent_loop


def make_project():
    d = tempfile.mkdtemp(prefix="code_verify_")
    os.makedirs(os.path.join(d, "calc"))
    open(os.path.join(d, "calc", "__init__.py"), "w").write(
        "def add(a, b):\n    \"\"\"Return the sum.\"\"\"\n    return a + b\n")
    open(os.path.join(d, "utils.py"), "w").write(
        "def slugify(text):\n    \"\"\"Lowercase + hyphenate.\"\"\"\n    return text.lower().replace(' ', '-')\n")
    open(os.path.join(d, "README.md"), "w").write("# DemoCalc\nA tiny calculator demo.\n")
    return d


async def collect(stream):
    out = []
    async for raw in stream:
        if isinstance(raw, str) and raw.startswith("data:"):
            b = raw[5:].strip()
            if b == "[DONE]":
                break
            try:
                d = json.loads(b)
            except Exception:
                continue
            if "delta" in d and isinstance(d["delta"], str):
                out.append(d["delta"])
    return "".join(out)


async def main():
    s = dict(load_settings())
    ws = make_project()
    ctx = repomap.build_context(ws)
    print("map stats:", ctx["stats"], "| prompt_chars:", len(ctx["prompt_text"]))
    url, model, headers, meta = crew_router.route_for_agent(CREW["coder"], "admin", s)
    print("coder model:", model)

    # --- Test 1: project awareness from the MAP ALONE (tools disabled) ---
    sysmsg = ("You are a code assistant. Use ONLY the project map below to answer; do not ask for files.\n\n"
              + ctx["prompt_text"])
    q = "Which file defines the function `slugify`, and what does the `add` function do? Be brief."
    ans = await asyncio.wait_for(collect(stream_agent_loop(
        url, model, [{"role": "system", "content": sysmsg}, {"role": "user", "content": q}],
        headers=headers, temperature=0.1, max_rounds=1,
        disabled_tools=set(ALL_NAMED), relevant_tools=set(), owner="admin")), timeout=240)
    print("\n[map-only answer]\n" + ans[:500])
    aware = ("utils.py" in ans.lower()) and ("add" in ans.lower())
    print("map_awareness:", "PASS" if aware else "FAIL")

    # --- Test 2: EDIT using project context (tools on, workspace) ---
    coder = CREW["coder"]
    sys2 = (coder.system_prompt + "\n\nFull project context below — use it.\n\n" + ctx["prompt_text"])
    task = "Add a `mul(a, b)` function to calc/__init__.py in the same style as `add` (with a docstring). Then stop."
    await asyncio.wait_for(collect(stream_agent_loop(
        url, model, [{"role": "system", "content": sys2}, {"role": "user", "content": task}],
        headers=headers, temperature=0.2, max_rounds=12,
        disabled_tools=set(coder.disabled_tools), owner="admin", workspace=ws)), timeout=420)
    body = ""
    p = os.path.join(ws, "calc", "__init__.py")
    if os.path.exists(p):
        body = open(p).read()
    print("\n[calc/__init__.py after edit]\n" + body)
    edited = "def mul" in body and "def add" in body
    print("edit_with_context:", "PASS" if edited else "FAIL")

    print(f"\n=== CODE TAB: map_awareness={'PASS' if aware else 'FAIL'} | edit={'PASS' if edited else 'FAIL'} ===")


asyncio.run(main())
