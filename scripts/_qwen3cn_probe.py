"""Dump qwen3-coder-next's RAW tool-call format so we can see why PiAOS got tools=[]."""
import os, sys, asyncio, json
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(REPO); sys.path.insert(0, REPO)
from services.crew import router
from services.crew.registry import AGENTS
from src.agent_loop import stream_agent_loop

MODEL = "qwen3-coder-next:q4_K_M"


async def main():
    r = router.resolve(MODEL, "admin")
    print("resolved:", r[0], r[1])
    url, model, headers = r
    agent = AGENTS["coder"]
    messages = [
        {"role": "system", "content": agent.system_prompt},
        {"role": "user", "content": "Create a file named hello.txt containing the text 'hi from qwen3'. Use your tools."},
    ]
    evtypes = {}
    deltas, native_calls = [], []
    import tempfile
    ws = tempfile.mkdtemp(prefix="q3cn_")
    async for raw in stream_agent_loop(url, model, messages, headers=headers, temperature=0.2,
                                       max_rounds=3, disabled_tools=set(agent.disabled_tools),
                                       owner="admin", workspace=ws):
        if not isinstance(raw, str) or not raw.startswith("data:"):
            continue
        body = raw[5:].strip()
        if body == "[DONE]":
            break
        try:
            d = json.loads(body)
        except Exception:
            continue
        t = d.get("type", "delta" if "delta" in d else "?")
        evtypes[t] = evtypes.get(t, 0) + 1
        if "delta" in d and isinstance(d["delta"], str):
            deltas.append(d["delta"])
        if t in ("tool_calls", "tool_call_delta"):
            native_calls.append(d)
    print("event types:", evtypes)
    print("native tool-call events:", len(native_calls))
    if native_calls:
        print("first native call:", json.dumps(native_calls[0])[:300])
    full = "".join(deltas)
    print("=== RAW MODEL TEXT (first 1800 chars) ===")
    print(full[:1800])
    print("=== markers ===")
    for mark in ("```", "<tool_call>", "<function", "tool_call", "write_file", "bash", "{\"name\""):
        print(f"  {mark!r}: {full.count(mark)}")


asyncio.run(asyncio.wait_for(main(), timeout=300))
