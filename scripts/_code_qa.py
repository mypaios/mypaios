"""Realistic 'ask about your project' test: map injected + READ-ONLY tools enabled."""
import os, sys, asyncio, tempfile, json
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(REPO); sys.path.insert(0, REPO)
from src.settings import load_settings
from services.code import repomap
from services.crew import router as crew_router
from services.crew.registry import AGENTS as CREW
from services.crew.policy import disabled_for
from src.agent_loop import stream_agent_loop


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
    d = tempfile.mkdtemp(prefix="code_qa_")
    os.makedirs(os.path.join(d, "calc"))
    open(os.path.join(d, "calc", "__init__.py"), "w").write("def add(a, b):\n    \"\"\"Return the sum.\"\"\"\n    return a + b\n")
    open(os.path.join(d, "utils.py"), "w").write("def slugify(text):\n    return text.lower().replace(' ', '-')\n")
    ctx = repomap.build_context(d)
    url, model, headers, _ = crew_router.route_for_agent(CREW["coder"], "admin", s)
    sysmsg = (CREW["coder"].system_prompt + "\n\nFull project context below — use it (and read_file/grep if needed).\n\n" + ctx["prompt_text"])
    q = "Which file defines the function `slugify`? And what does `add` return? Be brief."
    # read-only tools (retriever policy): allows read_file/grep/glob/ls, blocks write/exec
    ans = await asyncio.wait_for(collect(stream_agent_loop(
        url, model, [{"role": "system", "content": sysmsg}, {"role": "user", "content": q}],
        headers=headers, temperature=0.1, max_rounds=6,
        disabled_tools=set(disabled_for("retriever")), owner="admin", workspace=d)), timeout=300)
    print("[answer]\n" + ans[:600])
    ok = ("utils.py" in ans.lower()) and ("sum" in ans.lower() or "a + b" in ans.lower() or "a+b" in ans.lower())
    print("\n=== project_qa:", "PASS" if ok else "FAIL", "===")


asyncio.run(main())
