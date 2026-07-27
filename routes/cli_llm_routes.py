# routes/cli_llm_routes.py
"""CLI models — use locally-installed AI CLIs (claude, codex, gemini) as chat
backends through an OpenAI-compatible shim, so subscriptions the user already
pays for (Claude Code Max, ChatGPT/Codex) appear in the model picker with NO
API key.

Exposes:
    GET  /cli/v1/models            — which CLI backends are installed
    POST /cli/v1/chat/completions  — OpenAI-compat (stream + non-stream)

Register an endpoint with base_url http://localhost:7860/cli/v1 and the
normal chat path treats it like any OpenAI-compatible server. The CLI runs as
the logged-in user, entirely locally; PAIOS never sees or stores credentials —
auth lives with each CLI's own login.
"""
import asyncio
import json
import logging
import shutil
import time
import uuid

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, StreamingResponse

logger = logging.getLogger(__name__)

# CLI registry: model-id → how to invoke it. Prompt is passed on stdin to
# avoid argv length limits and shell quoting issues (argv list, shell=False).
_CLIS = {
    "claude-cli": {
        "binary": "claude",
        "label": "Claude (Claude Code subscription)",
        "args": ["-p", "--output-format", "text"],
        "stdin_prompt": True,
    },
    "codex-cli": {
        "binary": "codex",
        "label": "Codex (ChatGPT subscription)",
        "args": ["exec", "--skip-git-repo-check", "-"],
        "stdin_prompt": True,
    },
    "gemini-cli": {
        "binary": "gemini",
        "label": "Gemini (Google subscription)",
        "args": ["-p"],
        "stdin_prompt": True,
    },
}

_TIMEOUT_SEC = 600


def _resolve_binary(name: str):
    """Find a CLI binary even under launchd's minimal PATH."""
    import os
    hit = shutil.which(name)
    if hit:
        return hit
    home = os.path.expanduser("~")
    for d in ("/opt/homebrew/bin", "/usr/local/bin", f"{home}/.local/bin",
              f"{home}/bin", f"{home}/.npm-global/bin"):
        p = os.path.join(d, name)
        if os.path.isfile(p) and os.access(p, os.X_OK):
            return p
    return None


def _available():
    out = {}
    for mid, cfg in _CLIS.items():
        path = _resolve_binary(cfg["binary"])
        if path:
            out[mid] = {**cfg, "binary": path}
    return out


def _flatten_messages(messages) -> str:
    """Render an OpenAI messages array into one prompt for a one-shot CLI call.
    System messages become a preamble; the conversation is replayed inline."""
    parts = []
    for m in messages or []:
        role = m.get("role", "user")
        content = m.get("content", "")
        if isinstance(content, list):  # multimodal — keep text parts only
            content = " ".join(c.get("text", "") for c in content if isinstance(c, dict) and c.get("type") == "text")
        if not content:
            continue
        if role == "system":
            parts.append(f"[Instructions]\n{content}\n")
        elif role == "assistant":
            parts.append(f"[Your previous reply]\n{content}\n")
        else:
            parts.append(f"[User]\n{content}\n")
    parts.append("Reply to the last user message. Output only your reply.")
    return "\n".join(parts)


async def _run_cli(cfg: dict, prompt: str) -> tuple:
    """Run the CLI once; return (text, error)."""
    try:
        proc = await asyncio.create_subprocess_exec(
            cfg["binary"], *cfg["args"],
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        out, err = await asyncio.wait_for(
            proc.communicate(input=prompt.encode("utf-8")), timeout=_TIMEOUT_SEC)
        text = (out or b"").decode("utf-8", "replace").strip()
        if proc.returncode != 0 and not text:
            return None, (err or b"").decode("utf-8", "replace")[:400] or f"{cfg['binary']} exited {proc.returncode}"
        return text, None
    except asyncio.TimeoutError:
        try:
            proc.kill()
        except Exception:
            pass
        return None, f"{cfg['binary']} timed out after {_TIMEOUT_SEC}s"
    except Exception as e:  # noqa: BLE001
        return None, str(e)[:400]


def setup_cli_llm_routes() -> APIRouter:
    router = APIRouter(prefix="/cli/v1", tags=["cli-llm"])

    @router.get("/models")
    async def list_models():
        return {"object": "list", "data": [
            {"id": mid, "object": "model", "owned_by": cfg["label"]}
            for mid, cfg in _available().items()
        ]}

    @router.post("/chat/completions")
    async def chat_completions(request: Request):
        body = await request.json()
        model = (body.get("model") or "").strip()
        cfg = _available().get(model)
        if not cfg:
            return JSONResponse(status_code=404, content={"error": {
                "message": f"CLI model {model!r} not installed. Available: {list(_available())}"}})
        prompt = _flatten_messages(body.get("messages"))
        stream = bool(body.get("stream"))
        rid = f"cli-{uuid.uuid4().hex[:12]}"
        created = int(time.time())

        text, err = await _run_cli(cfg, prompt)
        if err and text is None:
            return JSONResponse(status_code=502, content={"error": {"message": f"CLI error: {err}"}})

        usage = {  # CLIs don't report tokens — estimate; PriceBook treats CLI as free
            "prompt_tokens": max(1, len(prompt) // 4),
            "completion_tokens": max(1, len(text) // 4),
            "total_tokens": max(2, (len(prompt) + len(text)) // 4),
        }
        if not stream:
            return {"id": rid, "object": "chat.completion", "created": created, "model": model,
                    "choices": [{"index": 0, "finish_reason": "stop",
                                 "message": {"role": "assistant", "content": text}}],
                    "usage": usage}

        async def _sse():
            # Chunk the finished text so the UI renders progressively.
            head = {"id": rid, "object": "chat.completion.chunk", "created": created, "model": model}
            step = 400
            for i in range(0, len(text), step):
                yield "data: " + json.dumps({**head, "choices": [
                    {"index": 0, "delta": {"content": text[i:i + step]}, "finish_reason": None}]}) + "\n\n"
                await asyncio.sleep(0)
            yield "data: " + json.dumps({**head, "usage": usage, "choices": [
                {"index": 0, "delta": {}, "finish_reason": "stop"}]}) + "\n\n"
            yield "data: [DONE]\n\n"

        return StreamingResponse(_sse(), media_type="text/event-stream")

    return router
