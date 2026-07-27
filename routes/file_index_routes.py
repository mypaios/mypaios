"""Routes for the global file/folder NAME index — powers the Agents tab
(Sync + Search). Admin-only, like the other connector/personal routes."""
import asyncio
import logging

from fastapi import APIRouter, HTTPException, Query, Depends
from pydantic import BaseModel

from src.auth_helpers import require_user
from core.middleware import require_admin
from src.file_index import get_file_index_manager

logger = logging.getLogger(__name__)


class RootBody(BaseModel):
    path: str


class OpenBody(BaseModel):
    path: str
    reveal: bool = False


def setup_file_index_routes():
    router = APIRouter(prefix="/api/file-index")
    mgr = get_file_index_manager()

    @router.get("")
    def status(owner: str = Depends(require_user), _a: None = Depends(require_admin)):
        return {
            "roots": mgr.get_roots(),
            "count": mgr.count,
            "last_sync": mgr.last_sync,
            "last_seconds": getattr(mgr, "last_duration", None),
            "skipped": list(getattr(mgr, "skipped_roots", [])),
            "last_error": getattr(mgr, "last_error", None),
        }

    @router.get("/search")
    def search(q: str = Query(""), owner: str = Depends(require_user), _a: None = Depends(require_admin)):
        return {"results": mgr.search(q)}

    @router.post("/sync")
    async def sync(owner: str = Depends(require_user), _a: None = Depends(require_admin)):
        res = await asyncio.to_thread(mgr.sync_all)
        return {"ok": True, "last_sync": mgr.last_sync, **res}

    @router.get("/roots")
    def list_roots(owner: str = Depends(require_user), _a: None = Depends(require_admin)):
        return {"roots": mgr.get_roots()}

    @router.post("/roots")
    def add_root(body: RootBody, owner: str = Depends(require_user), _a: None = Depends(require_admin)):
        try:
            p = mgr.add_root(body.path)
        except ValueError as e:
            raise HTTPException(400, str(e))
        return {"ok": True, "root": p, "roots": mgr.get_roots()}

    @router.delete("/roots")
    def remove_root(path: str = Query(...), owner: str = Depends(require_user), _a: None = Depends(require_admin)):
        return {"ok": True, "removed": mgr.remove_root(path), "roots": mgr.get_roots()}

    @router.post("/open")
    def open_path(body: OpenBody, owner: str = Depends(require_user), _a: None = Depends(require_admin)):
        try:
            return mgr.open_path(body.path, reveal=body.reveal)
        except PermissionError as e:
            raise HTTPException(403, str(e))
        except FileNotFoundError:
            raise HTTPException(404, "Path not found")
        except Exception as e:
            logger.warning("file_index open failed: %s", e)
            raise HTTPException(500, "Could not open path")

    return router
