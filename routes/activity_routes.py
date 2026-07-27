"""Activity routes — live capacity + what's running locally. GET /api/activity."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel

from src.auth_helpers import get_current_user
from core.middleware import require_admin
from services import activity, user_activity_log


class StopBody(BaseModel):
    id: int


class UserActivityLogBody(BaseModel):
    event_type: str
    details: dict


def setup_activity_routes() -> APIRouter:
    router = APIRouter(prefix="/api", tags=["activity"])

    @router.get("/activity")
    def get_activity(owner: str = Depends(get_current_user)):
        return activity.capacity()

    @router.post("/activity/stop")
    def stop_activity(body: StopBody, request: Request, _a: str = Depends(require_admin)):
        """Stop any registered live op (Code/chat/Crew/research/download) by its
        Activity-row id. The Activity tab is the universal kill switch."""
        return {"stopped": activity.stop(body.id)}

    @router.post("/user-activity/log")
    def log_user_activity(body: UserActivityLogBody, owner: str = Depends(get_current_user)):
        """Log a user activity event (click, text change, chat back-and-forth)."""
        user_activity_log.log(body.event_type, body.details)
        return {"status": "success"}

    @router.get("/user-activity/logs")
    def get_user_activity_logs(limit: int = 1000, owner: str = Depends(get_current_user)):
        """Retrieve logged user activities."""
        return user_activity_log.get_logs(limit=limit)

    @router.post("/user-activity/clear")
    def clear_user_activity_logs(owner: str = Depends(get_current_user)):
        """Clear the user activity log."""
        user_activity_log.clear_logs()
        return {"status": "success"}

    return router

