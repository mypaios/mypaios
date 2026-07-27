#!/usr/bin/env python3
"""
Local FLUX.1-schnell image server — Apple MLX via mflux, OpenAI-compatible.

Exposes `POST /v1/images/generations` returning {"data":[{"b64_json": ...}]}
(and GET /v1/models) so PiAOS's image tool (src/ai_interaction.do_generate_image)
can call it like any OpenAI image endpoint. Runs FLUX.1-schnell natively on
Apple Silicon (MLX, 4-bit quantized → ~8-12 GB unified memory).

Run:  venv/bin/python scripts/flux_server.py --port 7801
First generation downloads the schnell weights (~24 GB, one-time, cached in
~/.cache/huggingface) then quantizes in-memory; subsequent loads are ~1 min.

Model id reported: "flux.1-schnell".  Env: FLUX_PORT, FLUX_QUANTIZE (default 4).
"""
import os
import glob
import time
import shutil
import base64
import logging
import argparse
import tempfile
import threading
from typing import Optional

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from pydantic import BaseModel

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("flux_server")

MODEL_ID = os.getenv("FLUX_MODEL_ID", "z-image-turbo")
FAMILY = os.getenv("FLUX_FAMILY", "z_image").lower()  # "z_image" | "flux"
QUANTIZE = int(os.getenv("FLUX_QUANTIZE", "4"))

app = FastAPI(title="PiAOS FLUX server")
_flux = None
_load_lock = threading.Lock()
_gen_lock = threading.Lock()   # serialize generations (avoid memory spikes)


def _get_flux():
    global _flux
    if _flux is None:
        with _load_lock:
            if _flux is None:
                from mflux.models.common.config import ModelConfig
                model_path = os.getenv("FLUX_MODEL_PATH", "").strip() or None
                t = time.time()
                if FAMILY == "z_image":
                    # Z-Image-Turbo — ungated, native to mflux, quantized fresh (no
                    # format-mismatch). Official weights download on first run.
                    from mflux.models.z_image.variants.z_image import ZImage
                    log.info("Loading Z-Image-Turbo (quantize=%s) — first run downloads weights…", QUANTIZE)
                    _flux = ZImage(model_config=ModelConfig.z_image_turbo(), quantize=QUANTIZE, model_path=model_path)
                else:
                    from mflux.models.flux.variants.txt2img.flux import Flux1
                    base = os.getenv("FLUX_BASE_MODEL", "schnell")
                    if model_path:
                        log.info("Loading FLUX.1-%s from mirror %s…", base, model_path)
                        _flux = Flux1(model_config=ModelConfig.from_name(model_name=base), model_path=model_path)
                    else:
                        log.info("Loading FLUX.1-%s (quantize=%s) official repo — requires HF access…", base, QUANTIZE)
                        _flux = Flux1.from_name(model_name=base, quantize=QUANTIZE)
                log.info("Model loaded in %.0fs", time.time() - t)
    return _flux


class ImageReq(BaseModel):
    prompt: str
    n: Optional[int] = 1
    size: Optional[str] = "1024x1024"
    model: Optional[str] = None
    quality: Optional[str] = None
    steps: Optional[int] = None
    seed: Optional[int] = None
    response_format: Optional[str] = "b64_json"


def _models_payload():
    return {"object": "list", "data": [{"id": MODEL_ID, "object": "model", "owned_by": "black-forest-labs"}]}


@app.get("/health")
def health():
    return {"ok": True, "model": MODEL_ID, "loaded": _flux is not None}


@app.get("/v1/models")
@app.get("/models")
def models():
    return _models_payload()


def _parse_size(size: str):
    try:
        w, h = (size or "1024x1024").lower().split("x")
        w, h = int(w), int(h)
    except Exception:
        w = h = 1024

    def fix(v):
        v = max(256, min(1536, v))
        return v - (v % 16)
    return fix(w), fix(h)


def _to_png_bytes(gi) -> bytes:
    """Get PNG bytes from a mflux result (GeneratedImage or PIL.Image).

    mflux's GeneratedImage.save() will NOT overwrite an existing file — it
    appends _1/_2/… — so we save into an EMPTY temp dir and read whatever PNG
    actually lands there (covers both the GeneratedImage `save(path=)` API and a
    plain PIL `save(fp)`)."""
    d = tempfile.mkdtemp(prefix="piaos_img_")
    target = os.path.join(d, "img.png")
    try:
        saved = False
        for call in (lambda: gi.save(path=target), lambda: gi.save(target)):
            try:
                call()
                saved = True
                break
            except TypeError:
                continue
        if not saved:
            pil = getattr(gi, "image", None) or getattr(gi, "_image", None)
            if pil is not None:
                pil.save(target)
                saved = True
        pngs = sorted(glob.glob(os.path.join(d, "*.png")))
        if pngs:
            with open(pngs[0], "rb") as f:
                data = f.read()
            if data:
                return data
        raise RuntimeError("mflux produced no image bytes")
    finally:
        shutil.rmtree(d, ignore_errors=True)


def _generate(body: ImageReq):
    model = _get_flux()
    w, h = _parse_size(body.size or "1024x1024")
    if FAMILY == "z_image":
        steps = body.steps or 8       # Z-Image-Turbo: ~8 steps
        guidance = 1.0
    else:
        steps = body.steps or 4       # FLUX schnell: 4 steps, guidance-distilled
        guidance = 0.0
    seed = body.seed if body.seed is not None else int.from_bytes(os.urandom(4), "big")
    with _gen_lock:
        t = time.time()
        result = model.generate_image(
            seed=seed, prompt=body.prompt,
            num_inference_steps=steps, height=h, width=w, guidance=guidance,
        )
        data = _to_png_bytes(result)  # handles both GeneratedImage (FLUX) and PIL.Image (Z-Image)
        log.info("generated %dx%d steps=%d seed=%d in %.1fs (%d bytes)",
                 w, h, steps, seed, time.time() - t, len(data))
    return {"created": int(time.time()),
            "data": [{"b64_json": base64.b64encode(data).decode()}]}


@app.post("/v1/images/generations")
@app.post("/images/generations")
def images(body: ImageReq):
    try:
        return _generate(body)
    except Exception as e:
        log.exception("generation failed")
        return JSONResponse(status_code=500, content={"error": {"message": str(e)}})


# Minimal chat stub so any model-resolution probe doesn't error.
@app.post("/v1/chat/completions")
@app.post("/chat/completions")
def chat_stub(body: dict):
    return {"id": "flux-stub", "object": "chat.completion",
            "choices": [{"index": 0, "message": {"role": "assistant", "content": ""},
                         "finish_reason": "stop"}]}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=int(os.getenv("FLUX_PORT", "7801")))
    args = ap.parse_args()
    import uvicorn
    log.info("PiAOS FLUX server on http://%s:%d  (model=%s, quantize=%d)", args.host, args.port, MODEL_ID, QUANTIZE)
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")
