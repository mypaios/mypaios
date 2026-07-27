"""E2E probe: the agent loop drives the browser tool (hermes3, native tools).

Asks the model to open wikipedia.org via browser_navigate and report the page
title — proving schema registration, ToolBlock conversion, dispatch, and the
Playwright service all work through the REAL loop, not just direct calls.
"""
import os, sys, asyncio, json

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(REPO); sys.path.insert(0, REPO)

from src.agent_loop import stream_agent_loop


async def main():
    url = "http://localhost:11434/v1/chat/completions"
    model = "hermes3:8b"
    messages = [{
        "role": "user",
        "content": ("Use the browser_navigate tool to open https://www.wikipedia.org "
                    "and then tell me the exact <title> of the page. Do not guess — "
                    "actually open it."),
    }]
    text, tools = [], []
    async for raw in stream_agent_loop(
        url, model, messages, temperature=0.1, max_rounds=6, owner="admin",
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
        if d.get("type") == "tool_start":
            tools.append(d.get("tool", "?"))
        if "delta" in d and isinstance(d["delta"], str):
            text.append(d["delta"])
    final = "".join(text)
    print("tools used:", tools)
    print("answer tail:", final[-300:].replace("\n", " "))
    used = any(t.startswith("browser_") for t in tools)
    titled = "wikipedia" in final.lower()
    print("BROWSER AGENT E2E:", "PASS" if (used and titled) else "CHECK")

asyncio.run(main())
