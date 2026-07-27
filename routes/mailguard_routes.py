"""Mail Guard routes — status, rules CRUD, decisions audit trail, restore,
manual sweep, digest. Config flags live in DEFAULT_SETTINGS and persist via
the standard POST /api/auth/settings path."""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from core.middleware import require_admin
from routes.email_helpers import require_user

logger = logging.getLogger("mailguard.routes")


def setup_mailguard_routes() -> APIRouter:
    router = APIRouter(prefix="/api/mailguard", tags=["email"])

    @router.get("/status")
    async def get_status(request: Request, owner: str = Depends(require_user)):
        from services.mailguard import store
        from services.mailguard.runner import status
        from routes.email_helpers import _list_email_accounts
        st = status()
        st["stats_24h"] = store.stats(24)
        st["account_states"] = store.account_states()
        st["accounts"] = [
            {"id": c.get("account_id"), "email": c.get("from_address") or c.get("imap_user"),
             "name": c.get("account_name")}
            for c in _list_email_accounts() if c.get("imap_host")
        ]
        return st

    @router.post("/sweep")
    async def sweep(request: Request, _a: None = Depends(require_admin)):
        from services.mailguard.runner import sweep_now
        return await sweep_now()

    # ── rules ──
    @router.get("/rules")
    async def rules_list(request: Request, owner: str = Depends(require_user)):
        from services.mailguard import store
        return {"rules": store.list_rules()}

    @router.post("/rules")
    async def rules_add(request: Request, _a: None = Depends(require_admin)):
        from services.mailguard import store
        body = await request.json()
        try:
            rule = store.add_rule(
                kind=str(body.get("kind", "")).strip(),
                field=str(body.get("field", "sender")).strip(),
                pattern=str(body.get("pattern", "")),
                owner=require_user(request),
                note=str(body.get("note", ""))[:200],
            )
        except ValueError as e:
            raise HTTPException(400, str(e))
        return {"ok": True, "rule": rule}

    @router.delete("/rules/{rule_id}")
    async def rules_delete(rule_id: int, request: Request, _a: None = Depends(require_admin)):
        from services.mailguard import store
        return {"ok": store.delete_rule(rule_id)}

    # ── decisions / audit trail ──
    @router.get("/decisions")
    async def decisions(request: Request,
                        limit: int = Query(50, le=500),
                        verdict: Optional[str] = Query(None),
                        hours: Optional[float] = Query(None),
                        owner: str = Depends(require_user)):
        from services.mailguard import store
        return {"decisions": store.list_decisions(limit=limit, verdict=verdict, since_hours=hours)}

    @router.post("/decisions/{decision_id}/restore")
    async def restore(decision_id: int, request: Request, _a: None = Depends(require_admin)):
        """Move a wrongly-filed message back to INBOX and learn from it:
        the sender is auto-added as an include rule so it never happens again."""
        from services.mailguard import store
        from services.mailguard.engine import _addr
        from routes.email_helpers import _imap
        from routes.email_routes import _move_email_message
        from src.settings import load_settings

        d = store.get_decision(decision_id)
        if not d:
            raise HTTPException(404, "decision not found")
        if d["action"] not in ("filed", "trashed"):
            raise HTTPException(400, f"nothing to restore (action={d['action']})")
        folder = (load_settings().get("mailguard_filtered_folder") or "Pi Filtered") \
            if d["action"] == "filed" else "Trash"
        owner = require_user(request)
        moved = False
        try:
            with _imap(account_id=d["account_id"], owner=owner) as conn:
                conn.select(f'"{folder}"')
                # the UID changed when the message moved — find it by Message-ID
                typ, data = conn.uid("SEARCH", None, f'(HEADER Message-ID "{d["message_id"]}")')
                if typ == "OK" and data and data[0]:
                    uid = data[0].split()[-1].decode()
                    moved = _move_email_message(conn, uid, "INBOX")
        except Exception as e:  # noqa: BLE001
            raise HTTPException(502, f"restore failed: {e}")
        if not moved:
            raise HTTPException(404, "message not found in the filtered folder (already moved?)")
        store.mark_restored(decision_id)
        sender_addr = _addr(d["sender"])
        learned = None
        if sender_addr:
            learned = store.add_rule("include", "sender", sender_addr,
                                     owner=owner, note="learned from restore")
        return {"ok": True, "restored": True, "learned_rule": learned}

    # ── digest ──
    @router.get("/digest")
    async def digest(request: Request, hours: float = Query(24, le=168),
                     owner: str = Depends(require_user)):
        from services.mailguard import store
        st = store.stats(hours)
        urgent = store.list_decisions(limit=20, verdict="urgent", since_hours=hours)
        important = store.list_decisions(limit=30, verdict="important", since_hours=hours)
        return {"stats": st, "urgent": urgent, "important": important}

    return router
