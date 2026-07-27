"""Storage overview — Mac disks, AI-model storage, and Pi's own footprint.

One place that answers "where is my disk going?":
  * Mac level — every real volume's total/used/free
  * Models — Ollama models (itemized), the Hugging Face cache (whisper /
    Z-Image / docling live there), and Pi-managed model files (Kokoro etc.)
  * Pi as software — the installed app, the repo (venv / git / electron /
    code), and the data folder (chats DB, knowledge index, generated images…)

du runs are batched and the whole overview is cached for 2 minutes.
"""

from __future__ import annotations

import logging
import os
import pathlib
import subprocess
import threading
import time
from typing import Dict, List, Optional

logger = logging.getLogger("storage")

_REPO = str(pathlib.Path(__file__).resolve().parent.parent)
_HOME = os.path.expanduser("~")
_OLLAMA_DIR = os.environ.get("OLLAMA_MODELS", os.path.join(_HOME, ".ollama", "models"))
_HF_CACHE = os.path.join(_HOME, ".cache", "huggingface")
# Packaged desktop app. New builds install as MyPaiOS.app; older installs
# used PiAOS.app — measure both so legacy installs still show up.
_APP_BUNDLES = ["/Applications/MyPaiOS.app", "/Applications/PiAOS.app"]

_CACHE_TTL = 120.0
_cache: Optional[tuple] = None
_lock = threading.Lock()


def _du_many(paths: List[str]) -> Dict[str, float]:
    """GB for each existing path via one batched `du -sk` call."""
    existing = [p for p in paths if p and os.path.exists(p)]
    out: Dict[str, float] = {p: 0.0 for p in paths if p}
    if not existing:
        return out
    try:
        r = subprocess.run(["du", "-sk", *existing], capture_output=True, text=True, timeout=120)
        for line in r.stdout.splitlines():
            try:
                kb, path = line.split("\t", 1)
                out[path.strip()] = round(int(kb) / 1048576, 2)   # KiB → GiB
            except ValueError:
                continue
    except Exception as e:  # noqa: BLE001
        logger.warning("du failed: %s", e)
    return out


def _disks() -> List[dict]:
    import psutil
    seen = set()
    disks = []
    for part in psutil.disk_partitions(all=False):
        mp = part.mountpoint
        # Real, user-meaningful volumes only: the boot data volume + /Volumes/*.
        if mp != "/" and not mp.startswith("/Volumes/"):
            continue
        if mp in seen:
            continue
        seen.add(mp)
        try:
            # On macOS, "/" is the sealed system snapshot (~12 GB) — the user's
            # real usage lives on the APFS Data volume, which shares the
            # container's free space. Measure there for the boot disk.
            probe = "/System/Volumes/Data" if mp == "/" and os.path.isdir("/System/Volumes/Data") else mp
            u = psutil.disk_usage(probe)
        except OSError:
            continue
        disks.append({
            "mount": mp,
            "name": "Macintosh HD" if mp == "/" else os.path.basename(mp),
            "total_gb": round(u.total / 1e9, 1),
            "used_gb": round(u.used / 1e9, 1),
            "free_gb": round(u.free / 1e9, 1),
            "percent": round(u.percent),
        })
    disks.sort(key=lambda d: (d["mount"] != "/", d["mount"]))
    return disks


def _ollama_items() -> List[dict]:
    try:
        import httpx
        r = httpx.get("http://localhost:11434/api/tags", timeout=4)
        r.raise_for_status()
        items = [{"name": m.get("name", ""), "gb": round(int(m.get("size", 0)) / 1e9, 1)}
                 for m in r.json().get("models", [])]
        items.sort(key=lambda x: -x["gb"])
        return items
    except Exception:  # noqa: BLE001
        return []


def overview(rebuild: bool = False) -> dict:
    global _cache
    with _lock:
        if _cache and not rebuild and (time.time() - _cache[0]) < _CACHE_TTL:
            return _cache[1]

    data_dir = os.path.join(_REPO, "data")
    repo_parts = {
        "venv": os.path.join(_REPO, "venv"),
        "git": os.path.join(_REPO, ".git"),
        "electron": os.path.join(_REPO, "desktop-electron"),
        "data": data_dir,
    }
    du1 = _du_many([_REPO, _OLLAMA_DIR, _HF_CACHE, *_APP_BUNDLES, *repo_parts.values()])

    # data/ breakdown — its children, largest first
    data_children: List[str] = []
    try:
        with os.scandir(data_dir) as it:
            data_children = [e.path for e in it if not e.name.startswith(".")]
    except OSError:
        pass
    du2 = _du_many(data_children)
    data_items = sorted(
        ({"name": os.path.basename(p), "gb": g, "is_dir": os.path.isdir(p)} for p, g in du2.items()),
        key=lambda x: -x["gb"])[:14]

    repo_total = du1.get(_REPO, 0.0)
    venv_gb = du1.get(repo_parts["venv"], 0.0)
    git_gb = du1.get(repo_parts["git"], 0.0)
    electron_gb = du1.get(repo_parts["electron"], 0.0)
    data_gb = du1.get(data_dir, 0.0)
    code_gb = round(max(0.0, repo_total - venv_gb - git_gb - electron_gb - data_gb), 2)

    ollama_items = _ollama_items()
    ollama_gb = du1.get(_OLLAMA_DIR, 0.0) or round(sum(i["gb"] for i in ollama_items), 1)
    hf_gb = du1.get(_HF_CACHE, 0.0)

    # Pi-managed model files inside data/ (kokoro etc.) are part of data_gb;
    # call them out so the models story adds up.
    pi_model_files_gb = next((i["gb"] for i in data_items if i["name"] == "models"), 0.0)

    models_total = round(ollama_gb + hf_gb + pi_model_files_gb, 1)
    app_gb = round(sum(du1.get(b, 0.0) for b in _APP_BUNDLES), 2)
    software_total = round(app_gb + venv_gb + git_gb + electron_gb + code_gb, 2)
    pi_total = round(models_total + software_total + data_gb - pi_model_files_gb, 1)

    result = {
        "disks": _disks(),
        "models": {
            "total_gb": models_total,
            "ollama": {"dir": _OLLAMA_DIR, "total_gb": ollama_gb, "items": ollama_items},
            "hf_cache": {"dir": _HF_CACHE, "total_gb": hf_gb,
                         "note": "Whisper, Z-Image/FLUX, Docling and other Hugging Face downloads"},
            "pi_model_files_gb": pi_model_files_gb,
        },
        "pi": {
            "software_total_gb": software_total,
            "app_gb": app_gb,
            "repo": {"path": _REPO, "total_gb": repo_total, "venv_gb": venv_gb,
                     "git_gb": git_gb, "electron_gb": electron_gb, "code_gb": code_gb},
            "data_gb": data_gb,
            "data_items": data_items,
        },
        "totals": {
            "pi_related_gb": pi_total,
            "note": "models + software + your Pi data, combined",
        },
        "generated_at": int(time.time()),
    }
    with _lock:
        _cache = (time.time(), result)
    return result
