"""Per-modality install/active/size detection + hardware-fit + disk usage for the
Local AI hub. Read-only — knows WHERE each modality stores its model so the UI can
show Installed / Active / size without a central registry."""
from __future__ import annotations

import os
import shutil
import logging
import functools

logger = logging.getLogger(__name__)

_HF_HUB = os.path.expanduser(os.environ.get("HF_HOME", "~/.cache/huggingface")).rstrip("/")
if not _HF_HUB.endswith("hub"):
    _HF_HUB = os.path.join(_HF_HUB, "hub")


# ── helpers ──────────────────────────────────────────────────────────────────
def _settings() -> dict:
    try:
        from src.settings import load_settings
        return load_settings()
    except Exception:
        return {}


def _dir_size(path: str) -> int:
    total = 0
    try:
        for root, _dirs, files in os.walk(path):
            for f in files:
                try:
                    total += os.path.getsize(os.path.join(root, f))
                except OSError:
                    pass
    except OSError:
        pass
    return total


def _hf_repo_dir(repo: str) -> str:
    return os.path.join(_HF_HUB, "models--" + repo.replace("/", "--"))


@functools.lru_cache(maxsize=1)
def detect_system() -> dict:
    try:
        from services.hwfit.hardware import detect_system as _ds
        return _ds() or {}
    except Exception:
        return {}


# ── per-modality status ──────────────────────────────────────────────────────
def _status_whisper(entry: dict, s: dict) -> dict:
    model = entry.get("params", {}).get("stt_model", "base")
    d = _hf_repo_dir(f"Systran/faster-whisper-{model}")
    installed = os.path.isdir(d) and _dir_size(d) > 1_000_000
    active = installed and s.get("stt_enabled") and s.get("stt_provider") == "local" and s.get("stt_model") == model
    return {"installed": installed, "active": bool(active), "size_on_disk_bytes": _dir_size(d) if installed else 0}


def _status_kokoro(entry: dict, s: dict) -> dict:
    try:
        from services.tts.tts_service import _KOKORO_DIR, _KOKORO_MODEL_FILE, _KOKORO_VOICES_FILE
    except Exception:
        return {"installed": False, "active": False, "size_on_disk_bytes": 0}
    mp = os.path.join(_KOKORO_DIR, _KOKORO_MODEL_FILE)
    vp = os.path.join(_KOKORO_DIR, _KOKORO_VOICES_FILE)
    installed = os.path.exists(mp) and os.path.exists(vp)
    size = (os.path.getsize(mp) + os.path.getsize(vp)) if installed else 0
    active = installed and s.get("tts_enabled") and s.get("tts_provider") == "local"
    return {"installed": installed, "active": bool(active), "size_on_disk_bytes": size}


def _image_endpoint_enabled() -> bool:
    try:
        from core.database import SessionLocal, ModelEndpoint
        db = SessionLocal()
        try:
            ep = db.query(ModelEndpoint).filter(
                ModelEndpoint.model_type == "image", ModelEndpoint.is_enabled == True  # noqa: E712
            ).first()
            return ep is not None
        finally:
            db.close()
    except Exception:
        return False


def _flux_health() -> tuple[bool, str]:
    """(server_running, model_id_being_served). The flux server reports the
    active model via /health.model, so we can tell z-image from flux."""
    try:
        import httpx
        r = httpx.get("http://127.0.0.1:7801/health", timeout=1.5)
        if r.status_code == 200:
            return True, str(r.json().get("model", ""))
    except Exception:
        pass
    return False, ""


def _status_flux(entry: dict, s: dict) -> dict:
    p = entry.get("params", {})
    mid = p.get("FLUX_MODEL_ID", "")
    repo = "Tongyi-MAI/Z-Image-Turbo" if p.get("FLUX_FAMILY") == "z_image" else "black-forest-labs/FLUX.1-schnell"
    d = _hf_repo_dir(repo)
    weights = os.path.isdir(d) and _dir_size(d) > 100_000_000  # >100MB = real
    running, run_model = _flux_health()
    is_this = running and run_model == mid          # this exact image model is the one being served
    endpoint = _image_endpoint_enabled()
    installed = weights or is_this
    active = bool(is_this and endpoint and s.get("image_gen_enabled", True))
    return {"installed": installed, "active": active,
            "size_on_disk_bytes": _dir_size(d) if weights else 0, "loaded": is_this}


def _status_docling(entry: dict, s: dict) -> dict:
    try:
        import docling  # noqa: F401
        importable = True
    except Exception:
        importable = False
    active = bool(importable and s.get("ocr_enabled", True))
    return {"installed": importable, "active": active, "size_on_disk_bytes": 0}


def _ollama_tags() -> set[str]:
    try:
        import httpx
        base = "http://localhost:11434"
        try:
            from core.database import SessionLocal, ModelEndpoint
            db = SessionLocal()
            try:
                ep = db.query(ModelEndpoint).filter(ModelEndpoint.model_type == "llm").first()
                if ep and "11434" in (ep.base_url or ""):
                    base = ep.base_url.split("/v1")[0].rstrip("/")
            finally:
                db.close()
        except Exception:
            pass
        r = httpx.get(base + "/api/tags", timeout=2.0)
        if r.status_code == 200:
            return {m.get("name", "") for m in (r.json().get("models") or [])}
    except Exception:
        pass
    return set()


def _status_ollama(entry: dict, s: dict, tags: set[str]) -> dict:
    name = entry.get("params", {}).get("ollama_name", "")
    installed = name in tags or any(t.split(":")[0] == name.split(":")[0] for t in tags)
    active = bool(installed and s.get("default_model") == name)
    return {"installed": installed, "active": active, "size_on_disk_bytes": 0}


def _status_video(entry: dict, s: dict) -> dict:
    try:
        from core.database import SessionLocal, ModelEndpoint
        db = SessionLocal()
        try:
            ep = db.query(ModelEndpoint).filter(
                ModelEndpoint.model_type == "video", ModelEndpoint.is_enabled == True  # noqa: E712
            ).first()
            configured = ep is not None
        finally:
            db.close()
    except Exception:
        configured = False
    return {"installed": configured, "active": configured, "size_on_disk_bytes": 0}


def model_status(entry: dict, s: dict | None = None, ollama_tags: set | None = None) -> dict:
    s = s if s is not None else _settings()
    method = entry.get("install_method")
    if method == "whisper":
        return _status_whisper(entry, s)
    if method == "kokoro":
        return _status_kokoro(entry, s)
    if method == "flux_launchd":
        return _status_flux(entry, s)
    if method == "docling":
        return _status_docling(entry, s)
    if method == "ollama":
        return _status_ollama(entry, s, ollama_tags if ollama_tags is not None else _ollama_tags())
    if method == "endpoint":
        return _status_video(entry, s)
    return {"installed": False, "active": False, "size_on_disk_bytes": 0}


def model_fit(entry: dict, system: dict | None = None) -> dict:
    system = system if system is not None else detect_system()
    need = float(entry.get("requires_ram_gb") or 0)
    total = float(system.get("total_ram_gb") or 0)
    if need <= 0 or total <= 0:
        return {"fit": "unknown", "fit_label": ""}
    if need <= total * 0.7:
        return {"fit": "good", "fit_label": "Fits your Mac"}
    if need <= total:
        return {"fit": "slow", "fit_label": "May be slow"}
    return {"fit": "too_big", "fit_label": "Too big for your Mac"}


def enrich_catalog() -> dict:
    from services.local_ai import catalog
    s = _settings()
    system = detect_system()
    tags = _ollama_tags()
    out = {"system": system, "modalities": catalog.modalities(), "models": []}
    for m in catalog.models():
        st = model_status(m, s, tags)
        fit = model_fit(m, system)
        out["models"].append({**m, **st, **fit})
    return out


def disk_usage() -> dict:
    from services.local_ai import catalog
    s = _settings()
    tags = _ollama_tags()
    items, total = [], 0
    for m in catalog.models():
        st = model_status(m, s, tags)
        b = st.get("size_on_disk_bytes", 0)
        if st.get("installed") and b > 0:
            total += b
            items.append({"id": m["id"], "name": m["name"], "bytes": b})
    items.sort(key=lambda x: x["bytes"], reverse=True)
    return {"total_bytes": total, "items": items}
