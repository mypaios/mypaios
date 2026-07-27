# Security Policy

MyPaiOS is a self-hosted AI workspace with privileged local capabilities (shell, file access, email, model serving). Treat a running instance like an admin console, and please do not run it as a public, unauthenticated service.

## Supported Versions

| Version | Supported |
|---|---|
| Latest release (currently `v1.13.51` / app version `1.13.51.108`) | ✅ |
| Anything older | ❌ — upgrade to the latest release |

Security fixes land on `main` and ship in the next tagged release. There are no long-term-support branches.

## Reporting a Vulnerability

**Use GitHub Private Vulnerability Reporting — it is the only supported channel.**

1. Go to the repository's **Security** tab: [github.com/mypaios/mypaios/security](https://github.com/mypaios/mypaios/security)
2. Click **"Report a vulnerability"** and fill in the private advisory form.

Please do **not** open a public issue for security problems, and do not include exploit details in public discussions. There is no security email address; the private advisory flow reaches the maintainer directly and keeps the report confidential until a fix is out.

You can expect an acknowledgment on a best-effort basis (this is a solo-maintained project). Credit is given in the advisory and changelog unless you prefer otherwise.

## Threat Model (summary)

The full model is in [THREAT_MODEL.md](THREAT_MODEL.md). The short version:

- **Single-user, local-first by design.** MyPaiOS assumes one trusted owner/admin on a private machine or network. A logged-in admin can run shell commands, read/write files, and send email — that is intentional and in-scope for the product, not a vulnerability.
- **Never expose it to the internet without authentication.** Keep `AUTH_ENABLED=true` for any network-accessible deployment, put the app behind HTTPS via a trusted reverse proxy or private access layer (Tailscale, VPN, Cloudflare Access), and keep internal services (ChromaDB, SearXNG, ntfy, Ollama, vLLM, llama.cpp, databases, raw model APIs) unreachable from outside the host.
- **`LOCALHOST_BYPASS` is dev-only and dangerous.** When `true`, direct loopback requests are auto-authenticated as admin with no login. It exists purely for local development on a single-user machine. Keep it `false` on anything network-exposed, shared, or proxied — a misconfigured proxy that forwards as loopback would hand out admin.
- **What we defend against:** unauthenticated access, non-admins reaching admin capabilities, prompt injection from untrusted content (web results, emails, fetched pages) steering the agent, and internal services leaking beyond the host.

## Deployment Guidance

- Keep `AUTH_ENABLED=true` for any network-accessible deployment.
- Keep `LOCALHOST_BYPASS=false` outside local development.
- Set `SECURE_COOKIES=true` when the app is served through HTTPS by a trusted reverse proxy or private access gateway.
- Use HTTPS when exposing the app beyond localhost.
- Put the authenticated web/API entrypoint behind a trusted reverse proxy or private access layer such as Cloudflare Access, Tailscale, or a VPN.
- Keep ChromaDB, SearXNG, ntfy, Ollama, vLLM, llama.cpp, databases, and raw model/provider APIs internal-only.
- Protect `.env`, `data/`, `logs/`, uploads, generated media, backups, auth/session files, database files, API keys, and model/provider tokens.
- Disable open signup unless you intentionally want new accounts.
- Keep demo/test users non-admin, and remove them entirely on serious deployments.
- Give admin accounts strong passwords and enable 2FA where possible.
- Leave high-risk agent tools restricted to admins: shell, Python, file read/write, email send/read, MCP, app API, task/skill/memory management, settings, tokens, and model serving.
- Rotate API keys, webhook secrets, and app API tokens if they appear in logs, screenshots, demos, or shared chats.
- Treat shell, model-serving, MCP, email, calendar, and vault features as privileged admin functionality.
- Common internal-only ports are the app `7000`, SearXNG `8080`, ntfy `8091`, ChromaDB `8100`, Ollama `11434`, and local model/provider APIs such as `8000-8020`.

## Publishing A Fork

Before pushing a public fork, run:

```bash
git status --short
git check-ignore -v .env data/auth.json data/app.db logs/compound.log paios.db
git grep -n -I -E "(sk-[A-Za-z0-9_-]{20,}|xox[baprs]-|AIza[0-9A-Za-z_-]{20,}|Bearer [A-Za-z0-9._~+/-]{20,})" -- . ':!static/lib/**' ':!package-lock.json'
```

Only `.env.example`, docs, source, tests, and static assets should be committed. Never commit live `.env` values, `data/` contents, local databases, uploaded files, generated media, logs, backups, auth/session files, API keys, model/provider tokens, password hashes, or personal documents.
