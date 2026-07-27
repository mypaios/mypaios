"""Mail Guard background runner — telegram-gateway pattern.

Idles until `mailguard_enabled` is on (re-reads settings every cycle, so
toggling needs no restart), then sweeps all enabled email accounts every
`mailguard_interval_min` minutes. Sweep work itself lives in engine.py.
"""

from __future__ import annotations

import asyncio
import logging
import time

logger = logging.getLogger("mailguard")

_state = {
    "running": False,
    "last_sweep_ts": 0.0,
    "last_summary": None,
    "last_error": "",
    "sweeps": 0,
}


def status() -> dict:
    from src.settings import load_settings
    s = load_settings()
    return {
        "enabled": bool(s.get("mailguard_enabled")),
        "running": _state["running"],
        "interval_min": int(s.get("mailguard_interval_min") or 15),
        "filtered_folder": s.get("mailguard_filtered_folder") or "Pi Filtered",
        "hard_delete": bool(s.get("mailguard_hard_delete")),
        "draft_replies": bool(s.get("mailguard_draft_replies", True)),
        "last_sweep_ts": _state["last_sweep_ts"],
        "last_summary": _state["last_summary"],
        "last_error": _state["last_error"],
        "sweeps": _state["sweeps"],
    }


async def sweep_now() -> dict:
    """Manual sweep (also used by the ▶ button). Serialized via flag."""
    from services.mailguard.engine import run_sweep
    if _state["running"]:
        return {"busy": True, "note": "a sweep is already running"}
    _state["running"] = True
    try:
        summary = await run_sweep()
        _state["last_summary"] = summary
        _state["last_sweep_ts"] = time.time()
        _state["sweeps"] += 1
        _state["last_error"] = ""
        return summary
    except Exception as e:  # noqa: BLE001
        _state["last_error"] = str(e)[:300]
        logger.warning("mailguard sweep error: %s", e)
        return {"error": str(e)[:300]}
    finally:
        _state["running"] = False


async def run_loop():
    from src.settings import load_settings
    logger.info("mailguard runner started (idle until enabled)")
    while True:
        try:
            s = load_settings()
            if not s.get("mailguard_enabled"):
                await asyncio.sleep(5)
                continue
            interval = max(2, int(s.get("mailguard_interval_min") or 15)) * 60
            due = (time.time() - _state["last_sweep_ts"]) >= interval
            if due and not _state["running"]:
                await sweep_now()
            await asyncio.sleep(30)
        except asyncio.CancelledError:
            raise
        except Exception as e:  # noqa: BLE001
            _state["last_error"] = str(e)[:300]
            logger.warning("mailguard loop error: %s", e)
            await asyncio.sleep(10)
