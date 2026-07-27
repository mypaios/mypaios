# Deploying MyPaiOS as a service

Templates for running MyPaiOS automatically at login/boot. Both bind to
`127.0.0.1:7860` on purpose — MyPaiOS is a personal, single-machine app.

| File | Platform | Install target |
| --- | --- | --- |
| `launchd.example.plist` | macOS | `~/Library/LaunchAgents/com.piaos.paios.plist` |
| `systemd.example.service` | Linux | `/etc/systemd/system/mypaios.service` |

(Naming note: identifiers like the launchd label `com.piaos.paios`, `PAIOS_*`
env vars, and `scripts/paios-*` keep their historical names — renaming
internals breaks running installs. See CONTRIBUTING.md.)

## macOS (launchd)

```bash
# One-time setup: creates ./venv, installs deps (including the full chromadb
# package that embedded vector-store mode needs), and verifies the app boots.
./start-macos.sh          # Ctrl-C once you see the UI come up

# Install the agent
sed "s|/path/to/mypaios|$PWD|g" deploy/launchd.example.plist \
  > ~/Library/LaunchAgents/com.piaos.paios.plist
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.piaos.paios.plist

# Logs / stop
tail -f logs/paios-launchd.log
launchctl bootout gui/$(id -u)/com.piaos.paios
```

## Linux (systemd)

```bash
# One-time setup
python3 -m venv venv
./venv/bin/pip install -r requirements.txt
# Pick a ChromaDB mode — see the ChromaDB section below. For embedded:
./venv/bin/pip uninstall -y chromadb-client && ./venv/bin/pip install chromadb

# Install the unit (edit YOURUSER first)
sed "s|/path/to/mypaios|$PWD|g" deploy/systemd.example.service \
  | sudo tee /etc/systemd/system/mypaios.service > /dev/null
sudo systemctl daemon-reload
sudo systemctl enable --now mypaios
journalctl -u mypaios -f
```

> An older 0.0.0.0-binding `paios-ui.service` template was removed in favour of this
> loopback-binding one — never bind MyPaiOS to 0.0.0.0 without a reverse proxy + auth in front.

## Reaching it from other devices (reverse proxy)

Keep the bind on `127.0.0.1` and put a TLS-terminating proxy in front rather
than exposing uvicorn directly — that gets you HTTPS (required for secure
cookies, mic/PWA features) and a single place for access control:

```
# nginx
location / {
    proxy_pass http://127.0.0.1:7860;
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_http_version 1.1;             # streaming (SSE) needs 1.1
    proxy_set_header Connection "";
    proxy_buffering off;                # don't buffer chat streams
    proxy_read_timeout 300s;
}
```

Caddy (`caddy reverse-proxy --from https://pi.example.com --to 127.0.0.1:7860`)
or `tailscale serve 7860` work the same way. Then in `.env`: set
`SECURE_COOKIES=true`, add your public origin to `ALLOWED_ORIGINS`, and leave
`LOCALHOST_BYPASS` unset/false — with a proxy on the same host, a loopback
auth bypass would hand the whole network an unauthenticated session.

## The ChromaDB story (vector store for RAG & semantic memory)

`src/chroma_client.py` supports two modes via `CHROMADB_MODE`:

- **`embedded` (the default)** — an in-process `chromadb.PersistentClient`
  storing data under `CHROMADB_PATH` (default `data/chroma`). Nothing extra
  to run or configure; this is what single-machine installs want.
- **`http`** — a thin client talking to a standalone ChromaDB service at
  `CHROMADB_HOST:CHROMADB_PORT` (defaults `localhost:8100`). Startup
  fast-fails with a clear error if the service is unreachable
  (`CHROMADB_CONNECT_TIMEOUT`, default 2s) instead of hanging, and a failed
  connection is never cached — the next call retries.

**The packaging catch:** `requirements.txt` installs `chromadb-client`, the
lightweight HTTP-only package. It cannot do embedded mode (no local storage
engine). The full `chromadb` package can do both, but the two conflict if
co-installed. So:

- **macOS via `start-macos.sh`** — handled for you: the script replaces
  `chromadb-client` with the full `chromadb` package, and embedded mode just
  works.
- **Linux native (systemd)** — do the same swap once, as shown above, and
  embedded mode just works. Alternatively keep `chromadb-client` and run a
  ChromaDB service (`docker run -d -p 8100:8000 -v chromadb-data:/chroma/chroma
  chromadb/chroma`), then set `CHROMADB_MODE=http` in `.env`.
- **Docker Compose** — the bundled `chromadb` service is the intended store,
  and the image ships the thin client (embedded mode is not available inside
  the container). The compose file already points `CHROMADB_HOST`/`PORT` at
  the service; make sure the app container also gets `CHROMADB_MODE=http` —
  if your compose version doesn't set it, add a `docker-compose.override.yml`:

  ```yaml
  services:
    paios:
      environment:
        - CHROMADB_MODE=http
  ```

If ChromaDB is missing or misconfigured the app still boots — RAG and
semantic memory degrade to keyword fallback — so a broken vector store shows
up as worse recall, not a crash. Check the startup log for
`ChromaDB ready (embedded)` / `ChromaDB connected (http)` to confirm which
mode you're actually in.
