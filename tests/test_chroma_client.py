"""Regression tests for the ChromaDB singleton client (issue #326).

Covers the fast-fail preflight (so an unreachable ChromaDB doesn't block
startup for the full OS connection timeout) and the rule that a failed
connection must not poison the cached singleton.
"""
import socket
import time

import pytest

import src.chroma_client as cc


def _free_port() -> int:
    """Bind to port 0, grab the assigned port, release it — nothing listens."""
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def test_port_open_false_for_closed_port_and_is_fast():
    port = _free_port()
    t0 = time.monotonic()
    assert cc._port_open("127.0.0.1", port, timeout=1.0) is False
    # The whole point: we fail fast, nowhere near the 30-60s OS timeout.
    assert time.monotonic() - t0 < 5.0


def test_port_open_true_for_listening_socket():
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.bind(("127.0.0.1", 0))
    srv.listen(1)
    host, port = srv.getsockname()
    try:
        assert cc._port_open(host, port, timeout=1.0) is True
    finally:
        srv.close()


@pytest.fixture
def clean_singleton():
    """Isolate each test from any client cached by other tests, and vice versa."""
    cc.reset_client()
    yield
    cc.reset_client()


def test_get_chroma_client_does_not_cache_when_unreachable(clean_singleton, monkeypatch):
    pytest.importorskip("chromadb")
    # The unreachable-service scenario only exists in http mode. The default is
    # CHROMADB_MODE=embedded (in-process, always "reachable"), so the mode must
    # be pinned or the host/port below are simply ignored and nothing raises.
    monkeypatch.setenv("CHROMADB_MODE", "http")
    monkeypatch.setenv("CHROMADB_HOST", "127.0.0.1")
    monkeypatch.setenv("CHROMADB_PORT", str(_free_port()))
    with pytest.raises(RuntimeError):
        cc.get_chroma_client()
    # A failed connection must leave the singleton unset so a later call
    # (once ChromaDB is up) can succeed.
    assert cc._client is None


def test_get_chroma_client_defaults_to_embedded_and_ignores_http_vars(
    clean_singleton, monkeypatch, tmp_path
):
    """Regression guard for the embedded-by-default contract (P4-3).

    With CHROMADB_MODE unset, get_chroma_client() must build an in-process
    PersistentClient and never consult CHROMADB_HOST/PORT — even when they
    point at a dead port.
    """
    chromadb = pytest.importorskip("chromadb")
    # requirements.txt installs `chromadb-client` (thin HTTP-only client, as
    # used on CI); PersistentClient only exists in the full `chromadb`
    # package. Embedded mode is exercised where the full package is installed
    # (dev machines, `pip install chromadb`).
    if getattr(chromadb, "is_thin_client", False):
        pytest.skip("chromadb thin client (chromadb-client) has no PersistentClient")
    monkeypatch.delenv("CHROMADB_MODE", raising=False)
    monkeypatch.setenv("CHROMADB_HOST", "127.0.0.1")
    monkeypatch.setenv("CHROMADB_PORT", str(_free_port()))
    monkeypatch.setenv("CHROMADB_PATH", str(tmp_path / "chroma"))
    client = cc.get_chroma_client()
    assert client is not None
    assert cc._client is client
    # Singleton: a second call returns the same object.
    assert cc.get_chroma_client() is client
