"""
chroma_client.py

Singleton ChromaDB HTTP client.
Connects to a ChromaDB instance running as a standalone service.
"""

import os
import socket
import logging

logger = logging.getLogger(__name__)

_client = None

# A short connect probe so an unreachable ChromaDB fails fast instead of
# blocking on the OS connection timeout (~30-60s, WinError 10060 on Windows),
# which otherwise stalls app startup. Tunable via CHROMADB_CONNECT_TIMEOUT.
_CONNECT_TIMEOUT = float(os.getenv("CHROMADB_CONNECT_TIMEOUT", "2.0"))


def _port_open(host: str, port: int, timeout: float = None) -> bool:
    """Return True if a TCP connection to host:port succeeds within timeout."""
    try:
        with socket.create_connection((host, port), timeout=timeout or _CONNECT_TIMEOUT):
            return True
    except OSError:
        return False


def get_chroma_client():
    """Get or create the singleton ChromaDB client.

    Defaults to an EMBEDDED in-process PersistentClient (no separate server),
    so RAG + semantic memory work out of the box on a single machine and data
    persists under data/chroma. Set CHROMADB_MODE=http to connect to a
    standalone ChromaDB service instead.

    Raises RuntimeError with a clear install hint if `chromadb` is missing.
    """
    global _client
    if _client is not None:
        return _client

    try:
        import chromadb
    except ImportError as e:
        raise RuntimeError(
            "ChromaDB integration is not installed. Install it with: "
            "pip install chromadb"
        ) from e

    mode = os.getenv("CHROMADB_MODE", "embedded").strip().lower()

    if mode == "http":
        host = os.getenv("CHROMADB_HOST", "localhost")
        port = int(os.getenv("CHROMADB_PORT", "8100"))
        if not _port_open(host, port):
            raise RuntimeError(
                f"ChromaDB is not reachable at {host}:{port}. Start the service, "
                f"or use CHROMADB_MODE=embedded (default) for an in-process store."
            )
        client = chromadb.HttpClient(host=host, port=port)
        # Health check before caching — don't poison the singleton with a client
        # whose service is up on the port but not yet healthy.
        client.heartbeat()
        _client = client
        logger.info(f"ChromaDB connected (http): {host}:{port}")
        return _client

    # Embedded (default): in-process persistent store, no server to run.
    from core.constants import DATA_DIR
    path = os.getenv("CHROMADB_PATH", os.path.join(DATA_DIR, "chroma"))
    os.makedirs(path, exist_ok=True)
    client = chromadb.PersistentClient(path=path)
    client.heartbeat()
    _client = client
    logger.info(f"ChromaDB ready (embedded): {path}")
    return _client


def reset_client():
    """Reset the singleton (e.g. after config change)."""
    global _client
    _client = None
