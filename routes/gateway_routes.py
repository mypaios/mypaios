"""Gateway routes — Telegram remote-access config/status. /api/gateway/*"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request

from core.middleware import require_admin
from src.auth_helpers import get_current_user
from src.settings import load_settings, save_settings
from services.gateway import telegram_gateway


def setup_gateway_routes() -> APIRouter:
    router = APIRouter(prefix="/api/gateway", tags=["gateway"])

    @router.get("/telegram/status")
    def tg_status(request: Request, owner: str = Depends(get_current_user)):
        # status() exposes flags only — the token itself is never echoed
        return telegram_gateway.status()

    @router.post("/telegram/config")
    async def tg_config(request: Request, _a: None = Depends(require_admin)):
        body = await request.json()
        s = load_settings()
        if "enabled" in body:
            s["telegram_enabled"] = bool(body["enabled"])
        if "token" in body:
            s["telegram_bot_token"] = (body.get("token") or "").strip()
        if "allowed_chat_ids" in body and isinstance(body["allowed_chat_ids"], list):
            s["telegram_allowed_chat_ids"] = [str(x).strip() for x in body["allowed_chat_ids"] if str(x).strip()][:10]
        save_settings(s)
        return {"ok": True, **telegram_gateway.status()}

    @router.post("/telegram/test")
    async def tg_test(request: Request, _a: None = Depends(require_admin)):
        body = await request.json()
        token = (body.get("token") or "").strip() or (load_settings().get("telegram_bot_token") or "").strip()
        if not token:
            raise HTTPException(400, "No token to test")
        try:
            return await telegram_gateway.test_token(token)
        except Exception as e:  # noqa: BLE001
            raise HTTPException(400, f"Token check failed: {str(e)[:160]}")

    return router
