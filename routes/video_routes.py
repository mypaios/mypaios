"""
routes/video_routes.py — text-to-video generation via a pluggable open-source
video-diffusion endpoint (mirrors the image-generation design).

An admin registers a ModelEndpoint with model_type="video" pointing at a local
open-source video server — e.g. ComfyUI (with an OpenAI-compatible shim) serving
**LTX-Video**, **CogVideoX**, **HunyuanVideo**, or **Wan2.1**. This route POSTs a
text prompt to `{base_url}/videos/generations` and stores the returned clip.

Like image generation, the heavy model is served separately (the "download the
model later" step); this is the durable integration layer that's ready for it.
"""
from __future__ import annotations

import os
import uuid
import base64
import logging
from pathlib import Path
from typing import Optional

import httpx
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel

from core.database import SessionLocal, ModelEndpoint
from src.auth_helpers import get_current_user

logger = logging.getLogger(__name__)

VIDEO_DIR = Path("data/generated_videos")


class VideoRequest(BaseModel):
    prompt: str
    model: Optional[str] = None
    seconds: Optional[int] = 5
    fps: Optional[int] = 24
    width: Optional[int] = None
    height: Optional[int] = None


def _video_endpoint():
    db = SessionLocal()
    try:
        return db.query(ModelEndpoint).filter(
            ModelEndpoint.model_type == "video",
            ModelEndpoint.is_enabled == True,  # noqa: E712
        ).first()
    finally:
        db.close()


def _safe_name(name: str) -> str:
    base = os.path.basename(name or "")
    return base if base and not base.startswith(".") else ""


def setup_video_routes() -> APIRouter:
    router = APIRouter(prefix="/api/video", tags=["video"])
    VIDEO_DIR.mkdir(parents=True, exist_ok=True)

    @router.get("/status")
    async def status(request: Request):
        get_current_user(request)
        ep = _video_endpoint()
        return {
            "configured": ep is not None,
            "endpoint": (ep.name if ep else None),
            "base_url": (ep.base_url if ep else None),
            "hint": None if ep else (
                "No video endpoint yet. Serve an open-source text-to-video model "
                "(LTX-Video / CogVideoX / HunyuanVideo / Wan2.1) and register it in "
                "Settings → Models as model_type 'video'."
            ),
        }

    @router.post("/generate")
    async def generate(request: Request, body: VideoRequest):
        get_current_user(request)
        if not (body.prompt or "").strip():
            raise HTTPException(400, "Prompt is required")
        ep = _video_endpoint()
        if not ep:
            raise HTTPException(400, "No video generation endpoint configured. "
                                     "Register a model_type='video' endpoint first.")

        base_url = ep.base_url.rstrip("/")
        if not base_url.endswith("/v1"):
            base_url += "/v1"
        headers = {"Content-Type": "application/json"}
        if ep.api_key:
            headers["Authorization"] = f"Bearer {ep.api_key}"

        payload = {
            "prompt": body.prompt,
            "model": body.model or "ltx-video",
            "seconds": body.seconds or 5,
            "fps": body.fps or 24,
            "response_format": "b64_json",
        }
        if body.width:
            payload["width"] = body.width
        if body.height:
            payload["height"] = body.height

        try:
            # Video generation is slow; allow a generous timeout.
            async with httpx.AsyncClient(timeout=900) as client:
                resp = await client.post(f"{base_url}/videos/generations", json=payload, headers=headers)
        except Exception as e:
            logger.error("video generation request failed: %s", e)
            raise HTTPException(502, f"Video endpoint unreachable: {e}")

        if resp.status_code != 200:
            raise HTTPException(502, f"Video endpoint error ({resp.status_code}): {resp.text[:200]}")

        # Accept either {data:[{b64_json}]}, {data:[{url}]}, or raw video bytes.
        video_bytes = None
        ct = resp.headers.get("content-type", "")
        if ct.startswith("application/json"):
            data = resp.json().get("data", [{}])
            item = data[0] if data else {}
            if item.get("b64_json"):
                video_bytes = base64.b64decode(item["b64_json"])
            elif item.get("url"):
                async with httpx.AsyncClient(timeout=300) as client:
                    dl = await client.get(item["url"])
                    dl.raise_for_status()
                    video_bytes = dl.content
        elif ct.startswith("video/") or ct == "application/octet-stream":
            video_bytes = resp.content

        if not video_bytes:
            raise HTTPException(502, "Video endpoint returned no video data")

        fname = f"{uuid.uuid4().hex}.mp4"
        (VIDEO_DIR / fname).write_bytes(video_bytes)
        logger.info("video generated: %s (%d bytes)", fname, len(video_bytes))
        return {"ok": True, "filename": fname, "url": f"/api/video/file/{fname}",
                "bytes": len(video_bytes)}

    @router.get("/library")
    async def library(request: Request):
        get_current_user(request)
        items = []
        for p in sorted(VIDEO_DIR.glob("*.mp4"), key=lambda x: x.stat().st_mtime, reverse=True):
            items.append({"filename": p.name, "url": f"/api/video/file/{p.name}",
                          "bytes": p.stat().st_size, "mtime": int(p.stat().st_mtime)})
        return {"videos": items}

    @router.get("/file/{filename}")
    async def get_file(request: Request, filename: str):
        get_current_user(request)
        name = _safe_name(filename)
        path = VIDEO_DIR / name
        if not name or not path.exists():
            raise HTTPException(404, "Not found")
        return FileResponse(str(path), media_type="video/mp4")

    return router
