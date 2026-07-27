"""Workspace API — browse server directories to pick a tool workspace folder."""
import os
from fastapi import APIRouter, Request, HTTPException, Query

from src.auth_helpers import get_current_user
from src.tool_security import owner_is_admin_or_single_user


def setup_workspace_routes():
    router = APIRouter(prefix="/api/workspace", tags=["workspace"])

    @router.get("/browse")
    def browse(request: Request, path: str = Query(default="")):
        """List subdirectories of `path` (default: home) so the UI can navigate
        the server filesystem and pick a workspace folder. Directories only.

        ADMIN-ONLY: this enumerates the server filesystem, so it is gated the
        same way the file/shell tools are (read_file/write_file/bash are in
        NON_ADMIN_BLOCKED_TOOLS). A non-admin who can't use those tools must not
        be able to map the host's directory tree either.
        """
        owner = get_current_user(request)
        if not owner_is_admin_or_single_user(owner):
            raise HTTPException(status_code=403, detail="Workspace browsing is admin-only")

        # Resolve symlinks so the reported path is canonical and the UI navigates
        # real directories (defends against symlink games in displayed paths).
        target = os.path.realpath(os.path.expanduser(path.strip() or "~"))
        if not os.path.isdir(target):
            target = os.path.realpath(os.path.expanduser("~"))

        dirs = []
        try:
            with os.scandir(target) as it:
                for entry in it:
                    try:
                        # Don't follow symlinks when classifying — a symlinked
                        # dir is skipped rather than letting the browser wander
                        # off via a link. Hidden entries are omitted.
                        if entry.is_dir(follow_symlinks=False) and not entry.name.startswith("."):
                            # Build the child path server-side with os.path.join
                            # so it's correct on Windows (backslashes) and Linux.
                            dirs.append({"name": entry.name, "path": os.path.join(target, entry.name)})
                    except OSError:
                        continue
        except (PermissionError, OSError):
            dirs = []

        parent = os.path.dirname(target)
        return {
            "path": target,
            "parent": parent if parent and parent != target else None,
            "dirs": sorted(dirs, key=lambda d: d["name"].lower()),
        }

    @router.post("/mkdir")
    async def mkdir(request: Request):
        """Create a new subfolder inside `path` (for picking a fresh project
        folder). Admin-only, same gating as /browse."""
        owner = get_current_user(request)
        if not owner_is_admin_or_single_user(owner):
            raise HTTPException(status_code=403, detail="Workspace browsing is admin-only")
        try:
            body = await request.json()
        except Exception:
            body = {}
        parent = os.path.realpath(os.path.expanduser((body.get("path") or "").strip() or "~"))
        name = (body.get("name") or "").strip()
        if not os.path.isdir(parent):
            raise HTTPException(status_code=400, detail="Parent folder not found")
        # name must be a single, plain folder name — no separators / traversal / hidden tricks
        if (not name or name in (".", "..") or "/" in name or "\\" in name
                or name.startswith(".") or len(name) > 80):
            raise HTTPException(status_code=400, detail="Invalid folder name")
        dest = os.path.join(parent, name)
        # defense: the new folder's parent must resolve back to `parent`
        if os.path.realpath(os.path.dirname(dest)) != parent:
            raise HTTPException(status_code=400, detail="Invalid path")
        try:
            os.makedirs(dest, exist_ok=True)
        except OSError as e:
            raise HTTPException(status_code=500, detail=f"Could not create folder: {e}")
        return {"ok": True, "path": dest, "name": name}

    @router.post("/exec")
    async def exec_cmd(request: Request):
        """Run a shell command in `path` (e.g. `mkdir my-project`, `ls`, `mv …`).
        Admin-only; runs through the same safe bash path as the coding tools
        (catastrophic-command denylist, real /bin/bash, confined cwd)."""
        owner = get_current_user(request)
        if not owner_is_admin_or_single_user(owner):
            raise HTTPException(status_code=403, detail="Admin only")
        try:
            body = await request.json()
        except Exception:
            body = {}
        path = os.path.realpath(os.path.expanduser((body.get("path") or "").strip() or "~"))
        command = (body.get("command") or "").strip()
        if not os.path.isdir(path):
            raise HTTPException(status_code=400, detail="Folder not found")
        if not command:
            raise HTTPException(status_code=400, detail="Command required")

        from src.tool_execution import execute_tool_block

        class _Block:
            def __init__(self, content):
                self.tool_type = "bash"
                self.content = content

        try:
            _desc, res = await execute_tool_block(_Block(command), owner=owner, workspace=path)
        except Exception as e:  # noqa: BLE001
            raise HTTPException(status_code=500, detail=f"exec failed: {e}")
        output = res.get("output") or res.get("error") or ""
        return {"ok": (res.get("exit_code", 1) == 0), "output": output, "exit_code": res.get("exit_code")}

    return router
