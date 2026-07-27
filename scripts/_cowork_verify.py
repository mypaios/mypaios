"""Standalone Cowork verification: (1) bash tool echo -e sanity, (2) full agentic green run."""
import os, sys, asyncio, json, tempfile, subprocess

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(REPO); sys.path.insert(0, REPO)
PYTEST = os.path.join(REPO, "venv", "bin", "pytest")


class _Block:
    def __init__(self, tool_type, content):
        self.tool_type = tool_type
        self.content = content


async def test_playwright_green():
    """Deterministic proof that Cowork can run a real Playwright BROWSER test
    green (uses the globally-cached chromium). Drives the real bash + write_file
    tools end-to-end — the E2E testing Vishal asked Cowork to support."""
    from src.tool_execution import execute_tool_block
    ws = tempfile.mkdtemp(prefix="cowork_pw_")
    setup = ("npm init -y >/dev/null 2>&1 && npm i -D @playwright/test >/dev/null 2>&1 "
             "&& npx playwright install chromium >/dev/null 2>&1 && echo SETUP_DONE")
    _, r1 = await execute_tool_block(_Block("bash", setup), workspace=ws, owner="admin")
    setup_ok = "SETUP_DONE" in (r1.get("output") or "")
    cfg = "module.exports = { testDir: './tests', use: { browserName: 'chromium' } };\n"
    spec = ("const { test, expect } = require('@playwright/test');\n"
            "test('renders heading', async ({ page }) => {\n"
            "  await page.setContent('<h1>PiAOS Cowork</h1>');\n"
            "  await expect(page.locator('h1')).toHaveText('PiAOS Cowork');\n"
            "});\n")
    for path, body in (("playwright.config.js", cfg), ("tests/example.spec.js", spec)):
        await execute_tool_block(_Block("write_file", path + "\n" + body), workspace=ws, owner="admin")
    _, r2 = await execute_tool_block(_Block("bash", "npx playwright test --reporter=line"),
                                     workspace=ws, owner="admin")
    out = (r2.get("output") or "") + (r2.get("stderr") or "") + (r2.get("error") or "")
    green = ("1 passed" in out) and r2.get("exit_code", 1) == 0
    print(f"[playwright green] setup={'ok' if setup_ok else 'FAIL'} | run -> "
          f"{'PASS' if green else 'FAIL'}\n  output: {out.strip()[-300:]}")
    return green


async def test_bash_echo():
    """Verify the bash tool runs under real /bin/bash so echo -e behaves."""
    from src.tool_execution import execute_tool_block
    ws = tempfile.mkdtemp(prefix="cowork_bash_")
    blk = _Block("bash", 'echo -e "line1\\nline2" > f.txt; cat f.txt')
    await execute_tool_block(blk, workspace=ws, owner="admin")
    content = open(os.path.join(ws, "f.txt")).read()
    ok = content.strip() == "line1\nline2" and "-e" not in content
    print(f"[bash echo -e] {'PASS' if ok else 'FAIL'} -> {content!r}")
    return ok


async def run_agent(model, max_rounds=20):
    from src.ai_interaction import _resolve_model
    from src.agent_loop import stream_agent_loop
    url, mdl, headers = _resolve_model(model, owner="admin")
    ws = tempfile.mkdtemp(prefix="cowork_verify_")
    task = (
        "In the current working directory create a Python package using the write_file tool "
        "(do NOT use shell echo or heredocs):\n"
        "1. calc/__init__.py defining add(a,b) returning a+b and mul(a,b) returning a*b.\n"
        "2. tests/test_calc.py with pytest tests asserting add(2,3)==5 and mul(2,3)==6.\n"
        "Then run the tests with the bash tool using exactly: pytest -q\n"
        "Ensure they pass (green). Stop as soon as the tests pass."
    )
    tools = []
    try:
        async for ev in stream_agent_loop(url, mdl, [{"role": "user", "content": task}],
                                          headers=headers, workspace=ws, owner="admin",
                                          max_rounds=max_rounds, temperature=0.2):
            if not ev.startswith("data:"):
                continue
            b = ev[5:].strip()
            if b == "[DONE]":
                break
            try:
                d = json.loads(b)
            except Exception:
                continue
            if d.get("type") == "tool_start":
                tools.append(d.get("tool"))
    except Exception as e:
        print("loop error:", type(e).__name__, str(e)[:160])
    # Independent verification (don't trust the agent's own claim). Mirror the
    # Cowork subprocess env: workspace root on PYTHONPATH (same as tool_execution).
    _env = {**os.environ, "PYTHONPATH": ws + os.pathsep + os.environ.get("PYTHONPATH", "")}
    pt = subprocess.run([PYTEST, "-q"], cwd=ws, capture_output=True, text=True, env=_env)
    files = subprocess.run(["find", ws, "-type", "f", "-not", "-path", "*/.*",
                            "-not", "-path", "*/__pycache__/*"], capture_output=True, text=True).stdout
    print(f"[{model}] tools={tools}")
    print("files:\n" + files)
    for rel in ("calc/__init__.py", "tests/test_calc.py"):
        p = os.path.join(ws, rel)
        if os.path.exists(p):
            print(f"--- {rel} ---\n" + (open(p).read() or "(EMPTY)"))
    print(f"PYTEST rc={pt.returncode}\n" + (pt.stdout or pt.stderr)[-400:])
    return pt.returncode == 0


CALC_SRC = "def add(a, b):\n    return a + b\n\n\ndef mul(a, b):\n    return a * b\n"
TEST_SRC = ("from calc import add, mul\n\n\n"
            "def test_add():\n    assert add(2, 3) == 5\n\n\n"
            "def test_mul():\n    assert mul(2, 3) == 6\n")


async def test_infra_green():
    """Deterministic, model-free proof that the Cowork TOOLCHAIN runs a correct
    suite green: drive the real write_file + bash tools end-to-end."""
    from src.tool_execution import execute_tool_block
    ws = tempfile.mkdtemp(prefix="cowork_infra_")
    # write_file must auto-create parent dirs (calc/, tests/)
    for path, body in (("calc/__init__.py", CALC_SRC), ("tests/test_calc.py", TEST_SRC)):
        blk = _Block("write_file", path + "\n" + body)  # format: first line = path, rest = body
        await execute_tool_block(blk, workspace=ws, owner="admin")
    made = all(os.path.exists(os.path.join(ws, p)) for p in ("calc/__init__.py", "tests/test_calc.py"))
    # run tests via the real bash tool (PATH→venv pytest, PYTHONPATH→workspace)
    desc, res = await execute_tool_block(_Block("bash", "pytest -q"), workspace=ws, owner="admin")
    out = (res.get("output") or "") + (res.get("stderr") or "") + (res.get("error") or "")
    green = ("2 passed" in out) and res.get("exit_code", 1) == 0
    print(f"[infra green] write_file_made_dirs={made} | bash pytest -> "
          f"{'PASS' if green else 'FAIL'}\n  output: {out.strip()[:200]}")
    return made and green


async def main():
    infra_ok = await test_infra_green()
    bash_ok = await test_bash_echo()
    if "--infra" in sys.argv:
        print(f"\n=== RESULT: infra_green={'PASS' if infra_ok else 'FAIL'} | "
              f"bash_echo={'PASS' if bash_ok else 'FAIL'} ===")
        return
    if "--playwright" in sys.argv:
        pw_ok = await test_playwright_green()
        print(f"\n=== RESULT: infra_green={'PASS' if infra_ok else 'FAIL'} | "
              f"playwright_green={'PASS' if pw_ok else 'FAIL'} ===")
        return
    if "--bakeoff" in sys.argv:
        models = ["qwen2.5-coder:14b", "qwen2.5-coder:7b", "gpt-oss:20b"]
        attempts = 3
        results = {}
        for m in models:
            wins = 0
            for i in range(attempts):
                print(f"\n>>> BAKEOFF {m} attempt {i+1}/{attempts}")
                try:
                    g = await asyncio.wait_for(run_agent(m, max_rounds=18), timeout=420)
                except Exception as e:
                    print("  attempt error:", type(e).__name__, str(e)[:120]); g = False
                wins += 1 if g else 0
                if g:
                    print(f"  -> GREEN (stopping early for {m})"); break
            results[m] = wins
        print("\n=== BAKEOFF RESULTS (green attempts before early-stop) ===")
        for m in models:
            print(f"  {m}: {'GREEN' if results[m] else 'no green'}")
        best = next((m for m in models if results[m]), None)
        print(f"=== RECOMMENDED Cowork default: {best or 'none reached green'} ===")
        return
    model = next((a for a in sys.argv[1:] if not a.startswith("-")), "qwen2.5-coder:14b")
    green = await asyncio.wait_for(run_agent(model), timeout=600)
    print(f"\n=== RESULT: infra_green={'PASS' if infra_ok else 'FAIL'} | "
          f"bash_echo={'PASS' if bash_ok else 'FAIL'} | "
          f"agentic_green={'PASS' if green else 'FAIL'} ===")


asyncio.run(main())
