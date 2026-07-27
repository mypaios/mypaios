"""Model discovery for the Local AI hub — search + bring-your-own (Ollama).

Lets the user search a curated list of popular Ollama models AND pull ANY tag
they paste, with a hardware-fit guardrail BEFORE downloading:
  * size is read from the Ollama registry manifest (no download needed)
  * a hard 500 GB ceiling, and a green/amber/red fit vs the Mac's RAM
"""

from __future__ import annotations

import json
import logging
import pathlib
from typing import Dict, List, Optional

import httpx

logger = logging.getLogger("local_ai.discover")

_DIR = pathlib.Path(__file__).resolve().parent
_POPULAR = _DIR / "popular.json"
_REGISTRY = "https://registry.ollama.ai/v2"
_HARD_CAP_GB = 500.0
_CODE_HINTS = ("coder", "code", "devstral", "deepseek-coder", "starcoder", "codellama", "codegemma", "codestral")


def _is_code(name: str) -> bool:
    nl = (name or "").lower()
    return any(h in nl for h in _CODE_HINTS)


def _load_popular() -> List[dict]:
    try:
        return json.loads(_POPULAR.read_text(encoding="utf-8"))
    except Exception as e:  # noqa: BLE001
        logger.warning("popular.json load failed: %s", e)
        return []


def search(q: str) -> List[dict]:
    q = (q or "").strip().lower()
    pop = _load_popular()
    if not q:
        return pop[:40]
    out = [m for m in pop
           if q in m.get("name", "").lower()
           or q in m.get("blurb", "").lower()
           or any(q in str(t).lower() for t in m.get("tags", []))]
    # exact-name matches first
    out.sort(key=lambda m: (q not in m.get("name", "").lower(), not m.get("coding"), m.get("name", "")))
    return out[:40]


def _parse_tag(tag: str):
    """Return (repo, tag, registry_path). 'qwen3:8b' -> ('qwen3','8b','library/qwen3')."""
    tag = (tag or "").strip().lstrip("/")
    last = tag.split("/")[-1]
    if ":" in last:
        repo, t = tag.rsplit(":", 1)
    else:
        repo, t = tag, "latest"
    path = repo if "/" in repo else "library/" + repo
    return repo, t, path


def fit(size_gb: float, system: Optional[dict] = None) -> Dict:
    if system is None:
        try:
            from services.local_ai.status import detect_system
            system = detect_system()
        except Exception:  # noqa: BLE001
            system = {}
    ram = float(system.get("total_ram_gb") or 0)
    if size_gb > _HARD_CAP_GB:
        return {"fit": "too_big", "fit_label": f"Over the {int(_HARD_CAP_GB)} GB limit", "can_pull": False}
    if ram <= 0:
        return {"fit": "unknown", "fit_label": "size unknown", "can_pull": True}
    if size_gb <= ram * 0.55:
        return {"fit": "green", "fit_label": "Fits comfortably", "can_pull": True}
    if size_gb <= ram * 0.80:
        return {"fit": "amber", "fit_label": "Fits (tight)", "can_pull": True}
    if size_gb <= ram * 1.05:
        return {"fit": "red", "fit_label": f"Risky — near your {int(ram)} GB RAM", "can_pull": True}
    return {"fit": "red", "fit_label": f"May not fit ({int(size_gb)} GB > {int(ram)} GB RAM)", "can_pull": True}


def resolve(tag: str, system: Optional[dict] = None) -> Dict:
    """Look up an Ollama tag's size + fit from the registry, WITHOUT downloading."""
    repo, t, path = _parse_tag(tag)
    if not repo:
        return {"tag": tag, "ok": False, "error": "empty tag"}
    url = f"{_REGISTRY}/{path}/manifests/{t}"
    try:
        r = httpx.get(url, timeout=15, headers={"User-Agent": "PiAOS-LocalAI"})
        if r.status_code == 404:
            return {"tag": f"{repo}:{t}", "ok": False, "error": "not found in the Ollama registry"}
        r.raise_for_status()
        layers = r.json().get("layers", [])
        size_gb = round(sum(int(l.get("size", 0)) for l in layers) / 1e9, 2)
        return {"tag": f"{repo}:{t}", "ok": True, "size_gb": size_gb,
                "coding": _is_code(repo), **fit(size_gb, system)}
    except httpx.HTTPError as e:
        return {"tag": f"{repo}:{t}", "ok": False, "error": f"registry error: {str(e)[:100]}"}


def installed() -> List[dict]:
    """All models served by local Ollama, enriched with size + fit + coding flag."""
    try:
        r = httpx.get("http://localhost:11434/api/tags", timeout=5)
        r.raise_for_status()
        models = r.json().get("models", [])
    except Exception as e:  # noqa: BLE001
        logger.info("installed(): ollama tags unavailable: %s", e)
        return []
    try:
        from services.local_ai import catalog as _cat
        catalog_names = {(m.get("params", {}) or {}).get("ollama_name", "") for m in _cat.models()}
    except Exception:  # noqa: BLE001
        catalog_names = set()
    try:
        from services.local_ai.status import detect_system
        system = detect_system()
    except Exception:  # noqa: BLE001
        system = {}
    out = []
    for m in models:
        name = m.get("name", "")
        gb = round(int(m.get("size", 0)) / 1e9, 2)
        out.append({"name": name, "size_gb": gb, "coding": _is_code(name),
                    "in_catalog": name in catalog_names, **fit(gb, system)})
    out.sort(key=lambda x: (not x["coding"], -x["size_gb"]))
    return out
