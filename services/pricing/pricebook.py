# services/pricing/pricebook.py
"""Layered PriceBook — the single source of truth for what a generation costs.

Layers (highest wins):
  L0  reported   — provider told us the exact cost (OpenRouter usage.cost).
                   Handled by the caller; this module never overrides it.
  L1  dynamic    — per-model pricing captured from provider catalogs at
                   model-refresh time (OpenRouter /models → ModelEndpoint.model_meta).
  L2  static     — bundled, filtered snapshot of litellm's community price DB
                   (services/pricing/litellm_snapshot.json, USD per 1M tokens;
                   litellm by BerriAI, MIT License — full text in
                   licenses/litellm-MIT-LICENSE.txt).
  L3  overrides  — user-maintained data/pricing_overrides.json.
  local          — local endpoints are free (badge shows "local", not $0).

All prices are normalized to **USD per 1M tokens** at ingest. The two classic
unit bugs this guards against: OpenRouter reports strings in USD per SINGLE
token (×1e6), xAI reports cents per 100M tokens (÷10,000).

Cost math is provider-aware because cache billing semantics differ:
  * OpenAI-style (openai/openrouter/deepseek/groq/xai/…): `cached_tokens` is a
    SUBSET of input_tokens → bill (input−cached) at the input rate + cached at
    the cache-read rate. A naive formula double-bills.
  * Anthropic: input_tokens EXCLUDES cache reads/writes → bill all three
    buckets separately.
Reasoning tokens are already inside completion_tokens for OpenAI-style
providers — display them, never re-bill.
"""
from __future__ import annotations

import json
import logging
import os
import threading
import time
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

_HERE = os.path.dirname(os.path.abspath(__file__))
_SNAPSHOT_PATH = os.path.join(_HERE, "litellm_snapshot.json")

_lock = threading.Lock()
_snapshot: Optional[Dict[str, Any]] = None
_overrides: Optional[Dict[str, Any]] = None
_overrides_mtime: float = 0.0


def _load_snapshot() -> Dict[str, Any]:
    global _snapshot
    with _lock:
        if _snapshot is None:
            try:
                with open(_SNAPSHOT_PATH, encoding="utf-8") as f:
                    _snapshot = json.load(f)
            except Exception as e:
                logger.warning("pricebook: snapshot unavailable: %s", e)
                _snapshot = {"_meta": {}, "models": {}}
        return _snapshot


def _load_overrides() -> Dict[str, Any]:
    """data/pricing_overrides.json — {model_id: {in_per_m, out_per_m, ...}}."""
    global _overrides, _overrides_mtime
    try:
        from src.constants import DATA_DIR
        p = os.path.join(DATA_DIR, "pricing_overrides.json")
        m = os.path.getmtime(p) if os.path.exists(p) else 0
        with _lock:
            if _overrides is None or m != _overrides_mtime:
                _overrides_mtime = m
                if m:
                    with open(p, encoding="utf-8") as f:
                        _overrides = json.load(f)
                else:
                    _overrides = {}
        return _overrides or {}
    except Exception:
        return {}


def normalize_openrouter_pricing(p: Dict[str, Any]) -> Dict[str, float]:
    """OpenRouter /models pricing: STRING fields in USD per SINGLE token
    ("0" = free). Normalize to USD per 1M tokens. `request` stays per-request USD."""
    def f(key: str) -> float:
        try:
            return float(p.get(key) or 0)
        except (TypeError, ValueError):
            return 0.0
    row: Dict[str, float] = {}
    if f("prompt"):            row["in_per_m"] = round(f("prompt") * 1e6, 6)
    if f("completion"):        row["out_per_m"] = round(f("completion") * 1e6, 6)
    if f("input_cache_read"):  row["cache_read_per_m"] = round(f("input_cache_read") * 1e6, 6)
    if f("input_cache_write"): row["cache_write_per_m"] = round(f("input_cache_write") * 1e6, 6)
    if f("request"):           row["request_usd"] = f("request")
    return row


def _prefix_match(model: str, table: Dict[str, Any]) -> Optional[str]:
    """Longest-prefix / suffix-aware match so 'anthropic/claude-sonnet-4' and
    'gpt-5-2026-05-01' resolve. Exact match is checked by the caller first."""
    m = model.lower()
    bare = m.split("/", 1)[-1]          # drop 'vendor/' prefix
    best, best_len = None, 0
    for key in table.keys():
        k = key.lower()
        kb = k.split("/", 1)[-1]
        for a, b in ((m, k), (bare, kb), (bare, k), (m, kb)):
            if (a.startswith(b) or b.startswith(a)) and len(b) > best_len and len(b) >= 6:
                best, best_len = key, len(b)
    return best


def get_price(model: str,
              model_meta: Optional[Dict[str, Any]] = None,
              is_local: bool = False) -> Optional[Dict[str, Any]]:
    """Resolve the price row for a model.

    model_meta: the per-model dict captured from the endpoint's catalog
    (ModelEndpoint.model_meta[model]) — already normalized at ingest.
    Returns {in_per_m, out_per_m, [cache_*], [request_usd], source, [fetched_at]}
    or None (= unknown; caller must show 'unknown', never guess).
    """
    if not model:
        return None
    if is_local:
        return {"in_per_m": 0.0, "out_per_m": 0.0, "source": "local"}

    ov = _load_overrides()
    row = ov.get(model) or (ov.get(_prefix_match(model, ov)) if ov else None)
    if row:
        return {**row, "source": "override"}

    if model_meta and isinstance(model_meta.get("pricing"), dict) and model_meta["pricing"]:
        return {**model_meta["pricing"], "source": "catalog",
                "fetched_at": model_meta.get("fetched_at")}

    models = _load_snapshot().get("models", {})
    row = models.get(model)
    if row is None:
        key = _prefix_match(model, models)
        row = models.get(key) if key else None
    if row:
        out = {k: v for k, v in row.items() if k != "provider"}
        out["source"] = "litellm"
        out["fetched_at"] = _load_snapshot().get("_meta", {}).get("fetched_at")
        return out
    return None


def compute_cost(usage: Dict[str, Any], price: Optional[Dict[str, Any]],
                 provider: str = "openai") -> Optional[float]:
    """Provider-correct cost in USD from a normalized usage dict, or None when
    the price is unknown. Free/local rows return 0.0."""
    if not price:
        return None
    if price.get("source") == "local":
        return 0.0
    inp = int(usage.get("input_tokens") or 0)
    out = int(usage.get("output_tokens") or 0)
    cached = int(usage.get("cached_tokens") or 0)
    cache_write = int(usage.get("cache_write_tokens") or 0)
    in_rate = float(price.get("in_per_m") or 0) / 1e6
    out_rate = float(price.get("out_per_m") or 0) / 1e6
    cr_rate = float(price.get("cache_read_per_m") or 0) / 1e6
    cw_rate = float(price.get("cache_write_per_m") or 0) / 1e6

    if provider == "anthropic":
        # input EXCLUDES cache traffic — bill all buckets separately.
        cost = inp * in_rate + cached * (cr_rate or in_rate * 0.1) + cache_write * (cw_rate or in_rate * 1.25) + out * out_rate
    else:
        # cached is a SUBSET of input — never double-bill.
        cached = min(cached, inp)
        cost = (inp - cached) * in_rate + cached * (cr_rate or 0.0) + out * out_rate
    cost += float(price.get("request_usd") or 0)
    return round(cost, 8)


def is_local_url(url: Optional[str]) -> bool:
    """Loopback / private-LAN / tailnet endpoints are free local inference."""
    if not url:
        return True
    try:
        from urllib.parse import urlparse
        host = (urlparse(url).hostname or "").lower()
    except Exception:
        return False
    if host in ("localhost", "127.0.0.1", "0.0.0.0", "::1", "host.docker.internal"):
        return True
    if host.startswith(("192.168.", "10.")):
        return True
    if host.startswith("172."):
        try:
            second = int(host.split(".")[1])
            return 16 <= second <= 31
        except (ValueError, IndexError):
            return False
    if host.startswith("100."):  # Tailscale CGNAT
        try:
            second = int(host.split(".")[1])
            return 64 <= second <= 127
        except (ValueError, IndexError):
            return False
    return False


def book_status() -> Dict[str, Any]:
    snap = _load_snapshot()
    return {
        "snapshot_models": len(snap.get("models", {})),
        "snapshot_fetched_at": snap.get("_meta", {}).get("fetched_at"),
        "overrides": len(_load_overrides()),
    }
