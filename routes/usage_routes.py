# routes/usage_routes.py
"""Spend/usage API — powers the Usage dashboard, cost badges history, and the
CLI `paios usage` command. Reads the usage_ledger (counts + costs only)."""
import logging
from datetime import datetime, timedelta

from fastapi import APIRouter, Request
from sqlalchemy import func

from core.database import SessionLocal, UsageLedger
from src.auth_helpers import get_current_user

logger = logging.getLogger(__name__)


def setup_usage_routes() -> APIRouter:
    router = APIRouter(prefix="/api/usage", tags=["usage"])

    @router.get("/summary")
    async def usage_summary(request: Request, days: int = 30):
        """Spend rollups: today / this month / by-day / by-model / by-provider."""
        user = get_current_user(request)
        days = max(1, min(int(days or 30), 365))
        since = datetime.utcnow() - timedelta(days=days)
        db = SessionLocal()
        try:
            q = db.query(UsageLedger).filter(UsageLedger.ts >= since)
            if user:
                q = q.filter((UsageLedger.owner == user) | (UsageLedger.owner.is_(None)))
            rows = q.all()

            def _day(r):
                return r.ts.strftime("%Y-%m-%d") if r.ts else "?"

            by_day, by_model, by_provider = {}, {}, {}
            total_cost = 0.0
            total_in = total_out = 0
            unknown_cost_rows = 0
            for r in rows:
                c = r.cost_usd or 0.0
                if r.cost_usd is None and (r.provider not in (None, "ollama")):
                    unknown_cost_rows += 1
                total_cost += c
                total_in += r.input_tokens or 0
                total_out += r.output_tokens or 0
                d = _day(r)
                by_day[d] = round(by_day.get(d, 0.0) + c, 6)
                mk = r.model or "?"
                m = by_model.setdefault(mk, {"cost": 0.0, "in": 0, "out": 0, "calls": 0, "provider": r.provider})
                m["cost"] = round(m["cost"] + c, 6)
                m["in"] += r.input_tokens or 0
                m["out"] += r.output_tokens or 0
                m["calls"] += 1
                pk = r.provider or "?"
                by_provider[pk] = round(by_provider.get(pk, 0.0) + c, 6)

            today = datetime.utcnow().strftime("%Y-%m-%d")
            month_prefix = datetime.utcnow().strftime("%Y-%m")
            return {
                "days": days,
                "total_cost_usd": round(total_cost, 6),
                "today_cost_usd": by_day.get(today, 0.0),
                "month_cost_usd": round(sum(v for k, v in by_day.items() if k.startswith(month_prefix)), 6),
                "total_input_tokens": total_in,
                "total_output_tokens": total_out,
                "generations": len(rows),
                "unknown_cost_rows": unknown_cost_rows,
                "by_day": dict(sorted(by_day.items())),
                "by_model": dict(sorted(by_model.items(), key=lambda kv: -kv[1]["cost"])),
                "by_provider": dict(sorted(by_provider.items(), key=lambda kv: -kv[1])),
            }
        finally:
            db.close()

    @router.get("/sessions/top")
    async def top_sessions(request: Request, days: int = 30, limit: int = 10):
        """Most expensive sessions in the window."""
        user = get_current_user(request)
        since = datetime.utcnow() - timedelta(days=max(1, min(int(days or 30), 365)))
        db = SessionLocal()
        try:
            q = (db.query(UsageLedger.session_id,
                          func.sum(UsageLedger.cost_usd).label("cost"),
                          func.count(UsageLedger.id).label("calls"))
                 .filter(UsageLedger.ts >= since, UsageLedger.session_id.isnot(None)))
            if user:
                q = q.filter((UsageLedger.owner == user) | (UsageLedger.owner.is_(None)))
            rows = (q.group_by(UsageLedger.session_id)
                     .order_by(func.sum(UsageLedger.cost_usd).desc())
                     .limit(max(1, min(int(limit or 10), 50))).all())
            return {"sessions": [
                {"session_id": r[0], "cost_usd": round(r[1] or 0.0, 6), "calls": r[2]}
                for r in rows
            ]}
        finally:
            db.close()

    @router.get("/balance")
    async def openrouter_balance(request: Request):
        """Remaining OpenRouter credits/limits via GET /api/v1/key (works with a
        normal inference key; /credits is management-key-gated). Uses the first
        enabled OpenRouter endpoint's stored key — the key never leaves the
        server except to OpenRouter itself."""
        get_current_user(request)
        import httpx
        from core.database import ModelEndpoint
        db = SessionLocal()
        try:
            eps = db.query(ModelEndpoint).filter(ModelEndpoint.is_enabled.is_(True)).all()
            key = None
            for ep in eps:
                if "openrouter.ai" in (ep.base_url or "") and ep.api_key:
                    key = ep.api_key
                    break
        finally:
            db.close()
        if not key:
            return {"configured": False}
        try:
            r = httpx.get("https://openrouter.ai/api/v1/key",
                          headers={"Authorization": f"Bearer {key}"}, timeout=15)
            r.raise_for_status()
            d = (r.json() or {}).get("data", {})
            return {
                "configured": True,
                "label": d.get("label"),
                "usage": d.get("usage"),
                "limit": d.get("limit"),
                "limit_remaining": d.get("limit_remaining"),
                "is_free_tier": d.get("is_free_tier"),
            }
        except Exception as e:
            logger.warning(f"openrouter balance check failed: {type(e).__name__}")
            return {"configured": True, "error": "balance check failed"}

    return router
