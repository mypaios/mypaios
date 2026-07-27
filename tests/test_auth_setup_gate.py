"""First-run /api/auth/setup must hard-refuse once ANY account exists.

The classic first-comer-wins takeover: an exposed instance whose owner
completed setup must never let a remote caller mint another admin through
/setup. Two layers are pinned here against the REAL AuthManager:

  1. route layer  — first_run_setup raises 400 "Already configured"
  2. manager layer — AuthManager.setup() re-checks under _setup_lock, so even
     a race straight to the manager cannot create a second admin
"""
import asyncio
import threading
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from core.auth import AuthManager


def _manager(tmp_path):
    return AuthManager(auth_path=str(tmp_path / "auth.json"))


def _setup_endpoint(auth_manager, monkeypatch):
    import routes.auth_routes as ar
    monkeypatch.setattr(ar, "migrate_from_settings", lambda: None)
    router = ar.setup_auth_routes(auth_manager)
    for r in router.routes:
        if getattr(getattr(r, "endpoint", None), "__name__", "") == "first_run_setup":
            return r.endpoint
    raise AssertionError("first_run_setup route not found")


def _request(host="203.0.113.7"):
    return SimpleNamespace(client=SimpleNamespace(host=host))


def _body(username, password="correct-horse-battery"):
    return SimpleNamespace(username=username, password=password)


def test_setup_refuses_once_any_account_exists(tmp_path, monkeypatch):
    am = _manager(tmp_path)
    ep = _setup_endpoint(am, monkeypatch)

    # First run: creates the admin.
    res = asyncio.run(ep(_body("owner"), _request()))
    assert res["ok"] is True
    assert am.users["owner"]["is_admin"] is True

    # Second caller (attacker) is hard-refused with 400 — even from a
    # different IP, so the rate limiter is not what's doing the work.
    with pytest.raises(HTTPException) as ei:
        asyncio.run(ep(_body("attacker"), _request(host="198.51.100.9")))
    assert ei.value.status_code == 400
    assert "attacker" not in am.users


def test_setup_refuses_even_when_only_a_non_admin_exists(tmp_path, monkeypatch):
    """is_configured counts ANY user — a lone non-admin still closes the gate
    (stricter than 'once an admin exists')."""
    am = _manager(tmp_path)
    am.create_user("plainuser", "correct-horse-battery", is_admin=False)
    ep = _setup_endpoint(am, monkeypatch)
    with pytest.raises(HTTPException) as ei:
        asyncio.run(ep(_body("attacker"), _request()))
    assert ei.value.status_code == 400
    assert "attacker" not in am.users


def test_manager_setup_is_race_safe(tmp_path):
    """Concurrent AuthManager.setup calls: exactly one wins (the _setup_lock
    check-and-write), so parallel requests racing an empty auth.json cannot
    both create admin accounts."""
    am = _manager(tmp_path)
    results = []
    barrier = threading.Barrier(2)

    def attempt(name):
        barrier.wait()
        results.append((name, am.setup(name, "correct-horse-battery")))

    threads = [threading.Thread(target=attempt, args=(n,)) for n in ("alpha", "beta")]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert sorted(ok for _, ok in results) == [False, True]
    assert len(am.users) == 1


def test_manager_setup_refuses_when_configured(tmp_path):
    am = _manager(tmp_path)
    assert am.setup("owner", "correct-horse-battery") is True
    assert am.setup("attacker", "correct-horse-battery") is False
    assert list(am.users) == ["owner"]
