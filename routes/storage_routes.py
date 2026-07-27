"""Storage routes — disks, model storage, and Pi's footprint. GET /api/storage."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from src.auth_helpers import get_current_user
from services import storage


def setup_storage_routes() -> APIRouter:
    router = APIRouter(prefix="/api", tags=["storage"])

    @router.get("/storage")
    def get_storage(rebuild: bool = Query(False), owner: str = Depends(get_current_user)):
        return storage.overview(rebuild=rebuild)

    return router
