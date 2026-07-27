"""Activity & capacity — what's running locally + how much headroom is left.

Pi runs everything on one Mac, so "how much more can I run in parallel" is a
real question. This exposes:
  * live RAM / CPU (psutil)
  * which models Ollama currently has LOADED (the things using the GPU now)
  * active Pi agent sessions (Code / Crew, via a tiny registry) + downloads
  * Ollama's concurrency budget (max loaded models + parallel requests)
  * a headroom estimate ("you can add ~N more")
"""

from __future__ import annotations

import itertools
import logging
import os
import threading
import time
from typing import Dict, List, Optional

logger = logging.getLogger("activity")

_sessions: Dict[int, dict] = {}
_lock = threading.Lock()
_counter = itertools.count(1)

# Metal lets the GPU use ~75% of unified RAM for models by default.
_METAL_FRACTION = 0.75
# rough loaded footprints (GB) for the headroom hint
_SMALL_GB = 6.0     # ~7-8B quant
_MED_GB = 10.0      # ~14B quant
_BIG_GB = 55.0      # qwen3-coder-next etc.


# ───────────── session registry (active agent streams) ─────────────
# Every live operation in PiAOS should register here so the Activity panel can
# (a) SHOW it in real time and (b) STOP it. Each entry optionally carries a
# `cancel` callable (the subsystem's own stop primitive — jobs.cancel,
# agent_runs.stop, research cancel, etc.) so one Stop button covers everything.
def register(kind: str, model: Optional[str] = None, label: Optional[str] = None,
             ref: Optional[str] = None, cancel=None) -> int:
    with _lock:
        sid = next(_counter)
        _sessions[sid] = {"id": sid, "kind": kind, "model": model,
                          "label": (label or "")[:60], "started_at": int(time.time()),
                          "ref": ref, "_cancel": cancel}
        return sid


def unregister(sid: Optional[int]) -> None:
    if sid is None:
        return
    with _lock:
        _sessions.pop(sid, None)


def stop(entry_id: int) -> bool:
    """Stop a registered live op by its registry id. Calls the entry's own
    cancel primitive (set at register time). Returns True if a cancel ran."""
    with _lock:
        entry = _sessions.get(int(entry_id)) if str(entry_id).lstrip("-").isdigit() else None
        cancel = entry.get("_cancel") if entry else None
    if not cancel:
        return False
    try:
        cancel()
        return True
    except Exception as e:  # noqa: BLE001
        logger.warning("activity.stop(%s) cancel failed: %s", entry_id, e)
        return False


def _active() -> List[dict]:
    # Strip the non-serializable cancel callable; expose a `stoppable` flag + ref
    # so the frontend can render a Stop button and send the id back.
    with _lock:
        out = []
        for v in _sessions.values():
            out.append({"id": v["id"], "kind": v["kind"], "model": v.get("model"),
                        "label": v.get("label"), "started_at": v.get("started_at"),
                        "ref": v.get("ref"), "stoppable": v.get("_cancel") is not None})
        return out


# ───────────── ollama loaded models ─────────────
def _ollama_loaded() -> List[dict]:
    try:
        import httpx
        r = httpx.get("http://localhost:11434/api/ps", timeout=3)
        r.raise_for_status()
        out = []
        for m in r.json().get("models", []):
            sz = int(m.get("size", 0))
            vram = int(m.get("size_vram", 0))
            out.append({"name": m.get("name", ""), "size_gb": round(sz / 1e9, 1),
                        "gpu_gb": round(vram / 1e9, 1), "expires_at": m.get("expires_at")})
        return out
    except Exception as e:  # noqa: BLE001
        logger.debug("ollama /api/ps failed: %s", e)
        return []


def _downloads() -> List[dict]:
    """Active Local-AI installs / model pulls (best-effort)."""
    try:
        from routes.models_hub_routes import _JOBS, _JOBS_LOCK
        with _JOBS_LOCK:
            return [{"id": k, "msg": v.get("msg"), "pct": v.get("pct")}
                    for k, v in _JOBS.items() if v.get("state") == "running"]
    except Exception:  # noqa: BLE001
        return []


def _concurrency() -> dict:
    return {
        "max_loaded_models": os.environ.get("OLLAMA_MAX_LOADED_MODELS", "3 (default)"),
        "num_parallel": os.environ.get("OLLAMA_NUM_PARALLEL", "auto (1–4)"),
        "max_queue": os.environ.get("OLLAMA_MAX_QUEUE", "512 (default)"),
    }


def capacity() -> dict:
    import psutil
    vm = psutil.virtual_memory()
    total = vm.total / 1e9
    free = vm.available / 1e9
    used = vm.used / 1e9
    cpu = psutil.cpu_percent(interval=0.0)

    loaded = _ollama_loaded()
    loaded_gb = round(sum(m["size_gb"] for m in loaded), 1)
    gpu_budget = round(total * _METAL_FRACTION, 1)
    avail = max(0.0, min(free, gpu_budget - loaded_gb))

    active = _active()
    downloads = _downloads()

    # human advice
    if avail >= _BIG_GB:
        advice = f"~{avail:.0f} GB free for models — room for a big coder, or several smaller ones in parallel."
    elif avail >= _MED_GB:
        advice = f"~{avail:.0f} GB free — you can add ~{int(avail // _MED_GB)} more mid-size model(s) (≈14B)."
    elif avail >= _SMALL_GB:
        advice = f"~{avail:.0f} GB free — room for a small model (≈7B). Big models would queue/evict."
    else:
        advice = "Memory is tight — new model loads will queue or evict an idle model."

    return {
        "ram": {"total_gb": round(total, 1), "used_gb": round(used, 1),
                "free_gb": round(free, 1), "percent": round(vm.percent)},
        "cpu_percent": round(cpu),
        "gpu_budget_gb": gpu_budget,
        "loaded_models": loaded,
        "loaded_gb": loaded_gb,
        "available_for_models_gb": round(avail, 1),
        "headroom": {
            "small_7b": int(avail // _SMALL_GB),
            "mid_14b": int(avail // _MED_GB),
            "fits_big_coder": avail >= _BIG_GB,
        },
        "concurrency": _concurrency(),
        "active": active,
        "active_count": len(active),
        "downloads": downloads,
        "advice": advice,
    }
