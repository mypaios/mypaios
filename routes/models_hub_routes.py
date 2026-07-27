"""
routes/models_hub_routes.py — the "Local AI" hub: one-click download / activate /
delete of LOCAL models across every modality (STT, TTS, Image, OCR, LLM, Video).

Orchestrates the EXISTING install primitives (faster-whisper, scripts/download_kokoro,
scripts/flux_server launchd, Docling, ollama pull) behind a tiny status+job API the
Paraspeech-style panel (static/js/localAI.js) drives. Reads are user-visible; mutating
actions are admin-only (consistent with POST /api/auth/settings).
"""
from __future__ import annotations

import os
import time
import shutil
import logging
import threading
import subprocess

from fastapi import APIRouter, HTTPException, Query, Depends
from pydantic import BaseModel

from src.auth_helpers import require_user
from core.middleware import require_admin
from services.local_ai import catalog, status as status_svc, discover

logger = logging.getLogger(__name__)

# Background install jobs: {model_id: {"state": running|done|error, "msg": str, "pct": int|None}}
_JOBS: dict[str, dict] = {}
_JOBS_LOCK = threading.Lock()
_PATH_ENV = "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
FLUX_PLIST = os.path.expanduser("~/Library/LaunchAgents/com.piaos.flux.plist")


def _set_job(mid: str, **kw):
    with _JOBS_LOCK:
        _JOBS.setdefault(mid, {})
        _JOBS[mid].update(kw)


def _settings():
    from src.settings import load_settings
    return load_settings()


def _save(updates: dict):
    from src.settings import load_settings, save_settings
    s = load_settings()
    s.update(updates)
    save_settings(s)


def _repo_root() -> str:
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# ───────────────────────── install adapters (run in a thread) ────────────────
def _install_whisper(mid: str, entry: dict):
    model = entry.get("params", {}).get("stt_model", "base")
    _set_job(mid, state="running", msg=f"Downloading Whisper {model}…", pct=None)
    from faster_whisper import WhisperModel
    WhisperModel(model, device="cpu", compute_type="int8")  # downloads into HF cache
    _save({"stt_enabled": True, "stt_provider": "local", "stt_model": model})
    _set_job(mid, state="done", msg="Installed", pct=100)


def _install_kokoro(mid: str, entry: dict):
    _set_job(mid, state="running", msg="Downloading Kokoro voice model…", pct=None)
    repo = _repo_root()
    proc = subprocess.run(
        [os.path.join(repo, "venv", "bin", "python"), os.path.join(repo, "scripts", "download_kokoro.py")],
        cwd=repo, capture_output=True, text=True,
        env={**os.environ, "PATH": _PATH_ENV},
    )
    if proc.returncode != 0:
        raise RuntimeError((proc.stderr or proc.stdout or "download failed")[-300:])
    _save({"tts_enabled": True, "tts_provider": "local", "tts_voice": entry.get("params", {}).get("voice", "af_heart")})
    _set_job(mid, state="done", msg="Installed", pct=100)


def _write_flux_plist(params: dict):
    repo = _repo_root()
    py = os.path.join(repo, "venv", "bin", "python")
    server = os.path.join(repo, "scripts", "flux_server.py")
    log = os.path.join(repo, "logs", "flux-server.log")
    env = {"PATH": _PATH_ENV, "FLUX_PORT": "7801",
           "FLUX_FAMILY": params.get("FLUX_FAMILY", "z_image"),
           "FLUX_MODEL_ID": params.get("FLUX_MODEL_ID", "z-image-turbo"),
           "FLUX_QUANTIZE": params.get("FLUX_QUANTIZE", "4")}
    env_xml = "".join(f"    <key>{k}</key><string>{v}</string>\n" for k, v in env.items())
    plist = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>com.piaos.flux</string>
  <key>ProgramArguments</key><array><string>{py}</string><string>{server}</string><string>--port</string><string>7801</string></array>
  <key>WorkingDirectory</key><string>{repo}</string>
  <key>EnvironmentVariables</key><dict>
{env_xml}  </dict>
  <key>RunAtLoad</key><true/><key>KeepAlive</key><true/>
  <key>StandardOutPath</key><string>{log}</string>
  <key>StandardErrorPath</key><string>{log}</string>
</dict></plist>
"""
    os.makedirs(os.path.dirname(FLUX_PLIST), exist_ok=True)
    with open(FLUX_PLIST, "w") as f:
        f.write(plist)


def _upsert_image_endpoint(name: str):
    import uuid as _uuid, json as _json
    from core.database import SessionLocal, ModelEndpoint
    db = SessionLocal()
    try:
        ep = db.query(ModelEndpoint).filter(ModelEndpoint.base_url.like("%7801%")).first()
        mids = _json.dumps([name])
        if ep:
            ep.name, ep.model_type, ep.is_enabled = f"{name} (local MLX)", "image", True
            ep.cached_models = ep.pinned_models = mids
        else:
            db.add(ModelEndpoint(id=str(_uuid.uuid4()), name=f"{name} (local MLX)",
                                 base_url="http://localhost:7801", model_type="image",
                                 is_enabled=True, cached_models=mids, pinned_models=mids, owner=None))
        db.commit()
    finally:
        db.close()


def _install_flux(mid: str, entry: dict):
    params = entry.get("params", {})
    _set_job(mid, state="running", msg="Setting up local image server…", pct=None)
    _write_flux_plist(params)
    subprocess.run(["launchctl", "unload", FLUX_PLIST], capture_output=True)
    r = subprocess.run(["launchctl", "load", "-w", FLUX_PLIST], capture_output=True, text=True)
    if r.returncode != 0 and "already" not in (r.stderr or "").lower():
        logger.warning("flux launchctl load: %s", r.stderr)
    _upsert_image_endpoint(entry.get("params", {}).get("FLUX_MODEL_ID", entry["name"]))
    _save({"image_gen_enabled": True})
    _set_job(mid, state="done", msg="Ready — first image downloads the model (~9GB)", pct=100)


def _install_docling(mid: str, entry: dict):
    _set_job(mid, state="running", msg="Preparing document/OCR engine…", pct=None)
    try:
        from src.docling_runtime import _get_converter  # prefetch models
        _get_converter()
    except Exception as e:
        logger.warning("docling prefetch: %s", e)
    _save({"ocr_enabled": True, "ocr_provider": "docling"})
    _set_job(mid, state="done", msg="Installed", pct=100)


def _install_ollama(mid: str, entry: dict):
    name = entry.get("params", {}).get("ollama_name", "")
    _set_job(mid, state="running", msg=f"Pulling {name}…", pct=None)
    proc = subprocess.Popen(["ollama", "pull", name], stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            text=True, env={**os.environ, "PATH": _PATH_ENV})
    import re
    for line in iter(proc.stdout.readline, ""):
        m = re.search(r"(\d+)\s*%", line)
        if m:
            _set_job(mid, pct=int(m.group(1)), msg=f"Pulling {name}… {m.group(1)}%")
    proc.wait()
    if proc.returncode != 0:
        raise RuntimeError(f"ollama pull failed (is Ollama installed/running?)")
    _set_job(mid, state="done", msg="Installed", pct=100)


_INSTALLERS = {
    "whisper": _install_whisper, "kokoro": _install_kokoro, "flux_launchd": _install_flux,
    "docling": _install_docling, "ollama": _install_ollama,
}


def _run_install(mid: str, entry: dict):
    try:
        _INSTALLERS[entry["install_method"]](mid, entry)
    except Exception as e:
        logger.exception("install %s failed", mid)
        _set_job(mid, state="error", msg=str(e)[:300], pct=None)


# ───────────────────────────── activate / delete ─────────────────────────────
def _activate(entry: dict, on: bool):
    method, p = entry["install_method"], entry.get("params", {})
    if method == "whisper":
        _save({"stt_enabled": on, "stt_provider": "local" if on else "disabled", "stt_model": p.get("stt_model", "base")} if on
              else {"stt_enabled": False, "stt_provider": "disabled"})
    elif method == "kokoro":
        _save({"tts_enabled": on, "tts_provider": "local" if on else "disabled"})
    elif method == "flux_launchd":
        _save({"image_gen_enabled": on})
    elif method == "docling":
        _save({"ocr_enabled": on})
    elif method == "ollama":
        if on:
            _save({"default_model": p.get("ollama_name", "")})
    elif method == "endpoint":
        from core.database import SessionLocal, ModelEndpoint
        db = SessionLocal()
        try:
            for ep in db.query(ModelEndpoint).filter(ModelEndpoint.model_type == "video").all():
                ep.is_enabled = on
            db.commit()
        finally:
            db.close()


def _delete(entry: dict):
    method, p = entry["install_method"], entry.get("params", {})
    if method == "whisper":
        model = p.get("stt_model", "base")
        d = status_svc._hf_repo_dir(f"Systran/faster-whisper-{model}")
        shutil.rmtree(d, ignore_errors=True)
        # Only turn STT off if we deleted the model that was active (other sizes may remain).
        if _settings().get("stt_model") == model:
            _save({"stt_enabled": False, "stt_provider": "disabled"})
    elif method == "kokoro":
        from services.tts.tts_service import _KOKORO_DIR
        shutil.rmtree(_KOKORO_DIR, ignore_errors=True)
        _save({"tts_enabled": False, "tts_provider": "disabled"})
    elif method == "flux_launchd":
        subprocess.run(["launchctl", "unload", FLUX_PLIST], capture_output=True)
        try:
            os.remove(FLUX_PLIST)
        except OSError:
            pass
        from core.database import SessionLocal, ModelEndpoint
        db = SessionLocal()
        try:
            for ep in db.query(ModelEndpoint).filter(ModelEndpoint.base_url.like("%7801%")).all():
                ep.is_enabled = False
            db.commit()
        finally:
            db.close()
        _save({"image_gen_enabled": False})
    elif method == "ollama":
        subprocess.run(["ollama", "rm", p.get("ollama_name", "")], capture_output=True, env={**os.environ, "PATH": _PATH_ENV})
    elif method == "docling":
        _save({"ocr_enabled": False})


# ───────────────────────────────── routes ───────────────────────────────────
# Request models live at module scope: this file uses `from __future__ import
# annotations`, so FastAPI resolves handler body hints via get_type_hints()
# against module globals. A BaseModel nested in setup_models_hub_routes() is
# invisible there → FastAPI mis-reads `body` as a query param (422).
class IdBody(BaseModel):
    id: str


class TagBody(BaseModel):
    tag: str


class ModelBody(BaseModel):
    model: str


def setup_models_hub_routes() -> APIRouter:
    router = APIRouter(prefix="/api/local-ai", tags=["local-ai"])

    @router.get("/catalog")
    def get_catalog(owner: str = Depends(require_user)):
        data = status_svc.enrich_catalog()
        with _JOBS_LOCK:
            jobs = {k: dict(v) for k, v in _JOBS.items()}
        for m in data["models"]:
            if m["id"] in jobs:
                m["job"] = jobs[m["id"]]
        return data

    @router.get("/system")
    def get_system(owner: str = Depends(require_user)):
        return status_svc.detect_system()

    @router.get("/disk")
    def get_disk(owner: str = Depends(require_user)):
        return status_svc.disk_usage()

    @router.get("/status")
    def get_status(owner: str = Depends(require_user)):
        with _JOBS_LOCK:
            return {"jobs": {k: dict(v) for k, v in _JOBS.items()}}

    @router.post("/install")
    def install(body: IdBody, owner: str = Depends(require_user), _a: None = Depends(require_admin)):
        entry = catalog.by_id(body.id)
        if not entry:
            raise HTTPException(404, "Unknown model")
        if entry["install_method"] not in _INSTALLERS:
            raise HTTPException(400, entry.get("params", {}).get("hint", "This model is configured in Settings → Models."))
        with _JOBS_LOCK:
            if _JOBS.get(body.id, {}).get("state") == "running":
                return {"ok": True, "already_running": True}
        _set_job(body.id, state="running", msg="Starting…", pct=None)
        threading.Thread(target=_run_install, args=(body.id, entry), daemon=True).start()
        return {"ok": True, "id": body.id}

    @router.post("/activate")
    def activate(body: IdBody, owner: str = Depends(require_user), _a: None = Depends(require_admin)):
        entry = catalog.by_id(body.id)
        if not entry:
            raise HTTPException(404, "Unknown model")
        _activate(entry, True)
        return {"ok": True}

    @router.post("/deactivate")
    def deactivate(body: IdBody, owner: str = Depends(require_user), _a: None = Depends(require_admin)):
        entry = catalog.by_id(body.id)
        if not entry:
            raise HTTPException(404, "Unknown model")
        _activate(entry, False)
        return {"ok": True}

    @router.delete("/model")
    def delete_model(id: str = Query(...), owner: str = Depends(require_user), _a: None = Depends(require_admin)):
        entry = catalog.by_id(id)
        if not entry:
            raise HTTPException(404, "Unknown model")
        _delete(entry)
        with _JOBS_LOCK:
            _JOBS.pop(id, None)
        return {"ok": True}

    # ───────────── search / bring-your-own model (Ollama) ─────────────
    @router.get("/search")
    def search_models(q: str = Query(""), owner: str = Depends(require_user)):
        return {"results": discover.search(q)}

    @router.get("/resolve")
    def resolve_tag(tag: str = Query(...), owner: str = Depends(require_user)):
        """Size + hardware-fit for an arbitrary Ollama tag, WITHOUT downloading."""
        return discover.resolve(tag)

    @router.get("/installed")
    def installed_models(owner: str = Depends(require_user)):
        """Every model served by local Ollama, with size + fit + coding flag."""
        return {"models": discover.installed()}

    @router.post("/pull")
    def pull_tag(body: TagBody, owner: str = Depends(require_user), _a: None = Depends(require_admin)):
        """Pull an arbitrary Ollama tag — fit-gated (rejects > 500 GB / unresolvable)."""
        tag = (body.tag or "").strip()
        if not tag:
            raise HTTPException(400, "tag required")
        info = discover.resolve(tag)
        if not info.get("ok"):
            raise HTTPException(404, info.get("error", "not found"))
        if not info.get("can_pull"):
            raise HTTPException(400, info.get("fit_label", "too large to install"))
        mid = "ollama:" + info["tag"]
        with _JOBS_LOCK:
            if _JOBS.get(mid, {}).get("state") == "running":
                return {"ok": True, "already_running": True, "id": mid}
        entry = {"id": mid, "install_method": "ollama", "params": {"ollama_name": info["tag"]}}
        _set_job(mid, state="running", msg=f"Pulling {info['tag']}…", pct=None)
        threading.Thread(target=_run_install, args=(mid, entry), daemon=True).start()
        return {"ok": True, "id": mid, "size_gb": info.get("size_gb")}

    @router.post("/coding-default")
    def set_coding_default(body: ModelBody, owner: str = Depends(require_user), _a: None = Depends(require_admin)):
        """Use a model as the Crew/Cowork coding model (sets crew_coder_model)."""
        m = (body.model or "").strip()
        if not m:
            raise HTTPException(400, "model required")
        _save({"crew_coder_model": m})
        return {"ok": True, "crew_coder_model": m}

    @router.delete("/pulled")
    def delete_pulled(tag: str = Query(...), owner: str = Depends(require_user), _a: None = Depends(require_admin)):
        """Remove a model pulled via search/BYO (ollama rm)."""
        tag = (tag or "").strip()
        if not tag:
            raise HTTPException(400, "tag required")
        subprocess.run(["ollama", "rm", tag], capture_output=True, env={**os.environ, "PATH": _PATH_ENV})
        with _JOBS_LOCK:
            _JOBS.pop("ollama:" + tag, None)
        return {"ok": True}

    return router
