"""Telegram gateway — chat with Pi from your phone, anywhere.

Long-polls the official Bot API (https://core.telegram.org/bots/api) when
enabled. Messages from allowlisted chats run through Pi's agent loop on the
local generalist model with a SAFE tool policy (read/search/web — no shell,
no file writes) and the reply is sent back, chunked to Telegram's 4096 limit.

Security posture:
  * disabled by default; token pasted by the user (their own bot)
  * unknown chats are never executed — they get their chat_id so the user can
    allowlist themselves in Settings, nothing else
  * remote messages run with the read-only tool policy regardless of sender
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import List, Optional

import httpx

logger = logging.getLogger("gateway.telegram")

_API = "https://api.telegram.org/bot{token}/{method}"
_state = {"running": False, "last_error": "", "last_update_at": 0, "handled": 0, "bot": ""}


def status() -> dict:
    from src.settings import load_settings
    s = load_settings()
    return {
        "enabled": bool(s.get("telegram_enabled")),
        "token_set": bool((s.get("telegram_bot_token") or "").strip()),
        "allowed_chat_ids": s.get("telegram_allowed_chat_ids") or [],
        **_state,
    }


async def _tg(token: str, method: str, **params):
    async with httpx.AsyncClient(timeout=70) as client:
        r = await client.post(_API.format(token=token, method=method), json=params)
        data = r.json()
        if not data.get("ok"):
            raise RuntimeError(f"telegram {method}: {data.get('description', r.status_code)}")
        return data.get("result")


async def test_token(token: str) -> dict:
    """getMe — validates a token without starting the loop."""
    me = await _tg(token, "getMe")
    return {"ok": True, "bot": me.get("username", "?")}


def _safe_disabled_tools() -> set:
    """Remote messages get the read-only policy (same as the Crew retriever)."""
    from services.crew.policy import disabled_for
    return set(disabled_for("retriever"))


async def _answer(text: str, owner: str) -> str:
    """Run one remote message through the agent loop, collect the reply."""
    from services.crew import router as crew_router
    from src.agent_loop import stream_agent_loop
    from src.settings import load_settings
    s = dict(load_settings())
    url, model, headers, _m = crew_router.supervisor_route(owner, s)
    if not url:
        return "No local model is available right now."
    sysmsg = ("You are Pi, the user's personal AI, replying via Telegram. Be concise "
              "(a few short paragraphs max — it's a phone). You may use read-only "
              "tools (knowledge search, files read, web) to answer. Never run "
              "commands or modify anything from this channel.")
    out: List[str] = []
    try:
        async for ev in stream_agent_loop(
            url, model, [{"role": "system", "content": sysmsg},
                         {"role": "user", "content": text}],
            headers=headers, temperature=0.4, max_rounds=6,
            disabled_tools=_safe_disabled_tools(), owner=owner,
        ):
            if isinstance(ev, str) and ev.startswith("data:"):
                b = ev[5:].strip()
                if b == "[DONE]":
                    break
                try:
                    d = json.loads(b)
                except Exception:  # noqa: BLE001
                    continue
                if "delta" in d and isinstance(d["delta"], str):
                    out.append(d["delta"])
    except Exception as e:  # noqa: BLE001
        logger.warning("telegram answer failed: %s", e)
        return f"Something went wrong answering that ({str(e)[:80]})."
    return ("".join(out)).strip() or "(no reply)"


async def _send_chunked(token: str, chat_id, text: str):
    text = text or "(empty)"
    for i in range(0, len(text), 4000):
        await _tg(token, "sendMessage", chat_id=chat_id, text=text[i:i + 4000])


async def run_loop():
    """Forever loop — re-reads settings each cycle so toggling needs no restart."""
    from src.settings import load_settings
    offset = 0
    logger.info("telegram gateway loop started (idle until enabled)")
    while True:
        try:
            s = load_settings()
            token = (s.get("telegram_bot_token") or "").strip()
            enabled = bool(s.get("telegram_enabled")) and token
            if not enabled:
                _state["running"] = False
                await asyncio.sleep(5)
                continue
            if not _state["running"]:
                try:
                    me = await _tg(token, "getMe")
                    _state["bot"] = me.get("username", "")
                    _state["running"] = True
                    _state["last_error"] = ""
                    logger.info("telegram gateway live as @%s", _state["bot"])
                except Exception as e:  # noqa: BLE001
                    _state["last_error"] = str(e)[:200]
                    await asyncio.sleep(15)
                    continue

            updates = await _tg(token, "getUpdates", offset=offset, timeout=50,
                                allowed_updates=["message"])
            for u in updates or []:
                offset = max(offset, int(u.get("update_id", 0)) + 1)
                msg = u.get("message") or {}
                chat_id = (msg.get("chat") or {}).get("id")
                text = (msg.get("text") or "").strip()
                if chat_id is None or not text:
                    continue
                allowed = [str(x) for x in (s.get("telegram_allowed_chat_ids") or [])]
                if str(chat_id) not in allowed:
                    # Identify, never execute.
                    await _send_chunked(token, chat_id,
                                        f"This is a private Pi instance. Your chat id is {chat_id} — "
                                        "add it in Pi → Agents → Remote to enable access.")
                    continue
                _state["last_update_at"] = int(time.time())
                _state["handled"] += 1
                try:
                    await _tg(token, "sendChatAction", chat_id=chat_id, action="typing")
                except Exception:  # noqa: BLE001
                    pass
                reply = await _answer(text, owner="admin")
                await _send_chunked(token, chat_id, reply)
        except asyncio.CancelledError:
            raise
        except Exception as e:  # noqa: BLE001
            _state["last_error"] = str(e)[:200]
            _state["running"] = False
            logger.warning("telegram gateway error: %s", e)
            await asyncio.sleep(10)
