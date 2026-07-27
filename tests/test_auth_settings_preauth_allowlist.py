"""GET /api/auth/settings must never leak secrets to the login page.

The endpoint is auth-exempt (login-page prefetch + expired-session app pages
call it), so the unauthenticated tier is an explicit ALLOWLIST — not a
denylist scrub. The load-bearing property: a NEW settings key whose name does
not look secret-shaped (so the denylist in src/settings_scrub.py would wave it
through) must still be invisible to an unauthenticated caller.

Tiers pinned here:
  admin                  -> full settings
  authenticated non-admin -> denylist-scrubbed copy (keybinds/TTS keep working)
  unauthenticated        -> _PREAUTH_SETTINGS_ALLOWLIST projection only
"""
import asyncio
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest


SETTINGS = {
    # Allowlisted, pre-auth UI reads these:
    "keybinds": {"send": "Enter"},
    "tts_enabled": True,
    "tts_provider": "kokoro",
    "tts_voice": "alloy",
    "tts_speed": "1",
    "search_provider": "searxng",
    # Secret-shaped (denylist would catch these):
    "brave_api_key": "brv-secret",
    "smtp_password": "hunter2",
    # Made-up secret whose name does NOT match any denylist pattern — the
    # exact class of leak the allowlist exists to stop:
    "wormhole_flux_capacitor": "TOP-SECRET-VALUE",
    # Ordinary non-secret config that still should not be broadcast pre-auth:
    "app_public_url": "https://chat.example.com",
}


def _endpoint(auth_manager, monkeypatch, settings=SETTINGS):
    import routes.auth_routes as ar

    # No disk / integrations side effects during router construction.
    monkeypatch.setattr(ar, "migrate_from_settings", lambda: None)
    monkeypatch.setattr(ar, "_load_settings", lambda: dict(settings))
    router = ar.setup_auth_routes(auth_manager)
    for r in router.routes:
        if getattr(getattr(r, "endpoint", None), "__name__", "") == "get_settings":
            return r.endpoint
    raise AssertionError("get_settings route not found")


def _auth_manager(username=None, is_admin=False):
    am = MagicMock()
    am.get_username_for_token.return_value = username
    am.is_admin.return_value = is_admin
    return am


def _request():
    return SimpleNamespace(cookies={"paios_session": "tok"})


def test_unauthenticated_gets_only_allowlist(monkeypatch):
    ep = _endpoint(_auth_manager(username=None), monkeypatch)
    out = asyncio.run(ep(_request()))
    # Presence itself is the leak — non-allowlisted keys must be absent.
    assert "wormhole_flux_capacitor" not in out
    assert "brave_api_key" not in out
    assert "smtp_password" not in out
    assert "app_public_url" not in out
    # The pre-auth UI still gets what it needs.
    assert out["keybinds"] == {"send": "Enter"}
    assert out["tts_enabled"] is True
    assert out["tts_provider"] == "kokoro"
    assert out["search_provider"] == "searxng"
    # And the made-up secret VALUE never appears anywhere in the response.
    assert "TOP-SECRET-VALUE" not in repr(out)


def test_unauthenticated_response_is_subset_of_declared_allowlist(monkeypatch):
    """Every returned key must be in the allowlist — new settings keys are
    private-by-default until deliberately added."""
    # A future key nobody thought to classify:
    settings = dict(SETTINGS, some_future_admin_only_thing="internal")
    ep = _endpoint(_auth_manager(username=None), monkeypatch, settings)
    out = asyncio.run(ep(_request()))
    allow = {"keybinds", "tts_enabled", "tts_provider", "tts_voice",
             "tts_speed", "search_provider"}
    assert set(out) <= allow
    assert "some_future_admin_only_thing" not in out


def test_unauthenticated_nested_secret_under_allowlisted_key_is_scrubbed(monkeypatch):
    """Defense-in-depth: even inside an allowlisted key, secret-shaped nested
    values are blanked by the deep scrub."""
    settings = dict(SETTINGS)
    settings["keybinds"] = {"send": "Enter", "smuggled_api_key": "oops"}
    ep = _endpoint(_auth_manager(username=None), monkeypatch, settings)
    out = asyncio.run(ep(_request()))
    assert out["keybinds"]["smuggled_api_key"] == ""
    assert out["keybinds"]["send"] == "Enter"


def test_authenticated_non_admin_still_gets_scrubbed_full_settings(monkeypatch):
    """Regression guard: logged-in non-admins keep the denylist-scrubbed copy
    (keybinds + TTS + the rest), unchanged behavior."""
    ep = _endpoint(_auth_manager(username="bob", is_admin=False), monkeypatch)
    out = asyncio.run(ep(_request()))
    assert out["keybinds"] == {"send": "Enter"}
    assert out["app_public_url"] == "https://chat.example.com"  # non-secret survives
    assert out["brave_api_key"] == ""   # secret-shaped values blanked
    assert out["smtp_password"] == ""


def test_admin_gets_full_settings(monkeypatch):
    ep = _endpoint(_auth_manager(username="root", is_admin=True), monkeypatch)
    out = asyncio.run(ep(_request()))
    assert out["brave_api_key"] == "brv-secret"
    assert out["wormhole_flux_capacitor"] == "TOP-SECRET-VALUE"
