# AGENTS.md — MyPaiOS

Shared instructions for **any** AI coding agent working in this repo (Claude Code, Google Antigravity, Gemini CLI, Cursor, …). This is the single source of truth; `CLAUDE.md` is a symlink to this file. Keep it current.

## What this is
**MyPaiOS** (My Personal AI OS; pronounced "my-pie-OS" — the assistant persona is **Pi**) — a **local-first**, single-user AI workspace, forked from the MIT snapshot of Odysseus. One owner/admin. Everything runs on the local machine (Ollama models, FastAPI backend, vanilla-JS SPA). No cloud dependency for core function.

## Naming convention (do NOT "fix" this)
- **User-visible text** says **MyPaiOS** (product) and **Pi** (assistant persona).
- **Internals keep the historic `paios`/`PAIOS` identifiers** — element ids/classes, `paios-*` localStorage keys, the `CACHE_NAME` in `static/sw.js`, `X-PAIOS-*` headers, `PAIOS_*` env vars, the launchd label `com.piaos.paios`, python module names, and script paths like `scripts/paios-*`. Renaming them breaks running installs. Never rename internals as part of a branding pass.

## Licensing guardrail
- This fork is MIT, taken from the Odysseus MIT snapshot (commit `8354948`, 2026-06-05). Upstream relicensed to **AGPL-3.0 on 2026-06-09**. **Never merge, cherry-pick, or adapt upstream Odysseus code from after 2026-06-09** — doing so would contaminate the MIT fork with AGPL code.

## Run / dev
- Python: **always** use the venv → `./venv/bin/python` (never bare `python`).
- Server: uvicorn on **127.0.0.1:7860**, managed by launchd: `~/Library/LaunchAgents/com.piaos.paios.plist`. Logs: `logs/paios-launchd.log`.
- **WORKFLOW RULE (backend edits):** `launchctl unload <plist>` → edit `.py` → `launchctl load -w <plist>`. Python is not hot-reloaded; you must restart for backend changes to take effect.
- **Frontend** is vanilla JS in `static/` (no build step). After editing any `static/**/*.js` or `.css`, **bump `CACHE_NAME` in `static/sw.js`** (e.g. `paios-vNNN` → `vNNN+1`) and tell the user to hard-reload (⌘⇧R) — the service worker caches aggressively.
- Local auth: `LOCALHOST_BYPASS=true` in `.env` auto-authenticates **direct loopback** requests as admin (no login). Tunnel/proxy requests are excluded (`_is_trusted_loopback`). **Keep it `false` for any network-exposed deployment.**
- Tests: `./venv/bin/python -m pytest` (see CONTRIBUTING.md for the smallest relevant checks).

## Layout
- `src/` — engine: LLM calls (`llm_core.py`), agent loop (`agent_loop.py`), tool schemas/impls (`tool_schemas.py`, `tool_implementations.py`), chat processor, deep research, model context.
- `routes/` — FastAPI endpoints (`*_routes.py`).
- `services/` — feature modules: `memory/` (skills), `crew/` (multi-agent), `code/` (detached jobs), mail guard, hwfit, browser.
- `static/` — SPA (`app.js`, `js/*.js`, `index.html`, `style.css`, `sw.js`).
- `core/` — DB, middleware, auth, constants. `data/` — runtime (skills, settings.json, sqlite, uploads) — **gitignored**.

## Guardrails (do NOT violate)
- **Mail Guard NEVER auto-sends** — drafts only (IMAP Drafts append, zero SMTP for triage).
- **Admin-gate all mutations**; respect owner-scoping (skills/notes/etc. are per-owner).
- **Never** enter/commit API keys, tokens, or passwords; never hardcode secrets. `.env` is gitignored.
- **Do not remove existing capabilities** when refactoring.
- **Imported skills are quarantined** (`source=imported`, `trusted_exec=false`) — their `scripts/` won't run until the owner trusts them. See `services/memory/skill_runner.py`.

## Gotchas (learned the hard way)
- **FastAPI 422:** Pydantic request-body models MUST be module-scope (with `from __future__ import annotations`), never defined inside a route function, or the body is mis-read as a query param.
- **Local LLMs:** single GPU → inference **serializes** (concurrent agents queue). Ollama is reached via the `/v1` OpenAI-compat path; on Ollama 0.30.x `/v1` defaults to the model's full context (NOT 2048 — that lore is outdated). Known weak spots: temp 1.0 sent to all, no `keep_alive`, no per-family sampling, tool-trained models forced onto the fenced-tool prompt. (Pending tuning.)
- **Screenshots:** machine-specific paths do not belong in this file. If your workflow needs a screenshot directory (e.g. "look at the latest screenshot"), set `$PAIOS_SCREENSHOT_DIR` in a local `AGENTS.local.md` (gitignored) and read it from there.
- **Skills** are SKILL.md folders under `data/skills/<category>/<name>/` with 3-level progressive disclosure; the `manage_skills` tool drives them. Don't rebuild — extend `services/memory/skills.py` + `skill_format.py`.

## Multi-agent handoff (Claude Code ↔ Antigravity/Gemini)
Multiple agents edit this repo. Per-tool memory does NOT sync — **git + this file + `HANDOFF.md` + the baton are the shared context.**
- **Who's working now — the baton (`scripts/baton`):** `ACTIVE_AGENT.md` (root) names the agent currently driving. Commands: `scripts/baton status` (who + recent log) · `scripts/baton on <claude|gemini> "task"` (claim) · `scripts/baton off` (release) · `scripts/baton handover <to> "task"` (hand over). **Before editing, check `status`; if the other agent holds it, hand over or coordinate. Claim it while you work; release/hand over when done — keep it honest.**
- **Before starting:** read this file, run `scripts/baton status`, skim `HANDOFF.md`, and `git log --oneline -20` + `git status` to see what the other agent changed.
- **At end of a working session:** `scripts/baton off` (or hand over), commit your work with a **conventional-commit** message (`feat:`/`fix:`/`refactor:`/`chore:`/`docs:`) so the next agent can diff it, and append a short entry to `HANDOFF.md`.
- Antigravity leaves `*.bak.ai` backups when it edits (gitignored) — a quick "what did the other tool touch" signal.
- `data/PI.md` is for the **running app's** Pi agents (chat/code/crew), NOT for IDE coding agents — keep the two distinct.
