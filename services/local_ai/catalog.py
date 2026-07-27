"""Loader for the curated Local AI model catalog (services/local_ai/catalog.json)."""
from __future__ import annotations

import os
import json
import functools

_DIR = os.path.dirname(os.path.abspath(__file__))
_CATALOG_PATH = os.path.join(_DIR, "catalog.json")


@functools.lru_cache(maxsize=1)
def _load() -> dict:
    with open(_CATALOG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def modalities() -> list[dict]:
    return list(_load().get("modalities", []))


def models() -> list[dict]:
    return list(_load().get("models", []))


def by_id(model_id: str) -> dict | None:
    for m in models():
        if m.get("id") == model_id:
            return m
    return None


def by_modality(modality: str) -> list[dict]:
    return [m for m in models() if m.get("modality") == modality]
