# Changelog

All notable changes to MyPaiOS are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and version numbers follow the project's own display-version scheme (the app
shows `1.13.51.108`; git tags use the short form, e.g. `v1.13.51`).

Entries before the initial public release summarize the project's internal
build history (previously numbered `0.x`), condensed from the in-app "What's
New" changelog.

## [Unreleased] - since 2026-07-20

### Added
- **Full feature reference** — a standalone page cataloguing all 13 feature
  areas, 51 named capabilities, and 108 individual details, each cited
  against the exact source file and line that implements it
  ([`feature-reference.html`](feature-reference.html)), linked from the
  homepage's "Built in public" numbers section.
- A short note on why the version number **1.13.51.108** carries resonance in
  Hindu tradition (the Rig Veda's "Ekam," Trayodashi, the Shakti Peethas, and
  the many traditional uses of 108) — framed as a discovered resonance in an
  ordinary incrementing build number, not a deliberate original design.

### Changed
- **Sidebar navigation flattened** — the 8 sidebar sections (Chats, Models,
  Tools, Code, Knowledge, Automate, System, App) are now static, always-
  expanded groups instead of a click-to-open accordion. Nothing is hidden
  behind a click anymore; removed the collapse chevron and the two separate
  mechanisms that were forcing sections (particularly Chats) shut on load.

### Removed
- All direct dollar-figure comparisons against ChatGPT/Claude/Gemini pricing
  (the $20/mo table, the "$3,600 over five years" math, the live cost
  ticker) from the homepage and README. Non-pricing comparisons — offline
  support, model choice, rate limits, open source — stay.
- The full ChatGPT/Claude/Gemini side-by-side comparison table, on both the
  homepage and README.

### Security
- Resolved all 106 open Dependabot alerts. Bumped `mcp` (pinned to `1.28.1`
  specifically — the earliest release with the WebSocket Host/Origin
  validation fix, GHSA-vj7q-gjh5-988w, that doesn't drop the
  `Server.list_tools()` API `mcp_servers/*.py` depends on; `2.0.0`+ removes
  it), `pypdf`, `cryptography`, `aiohttp`, `setuptools`, `pillow`
  (+`torchvision` to match), `pydantic-settings`, and `starlette`. Bumped the
  Electron desktop shell (`electron` 33→43.4.0, `electron-builder`
  25→26.15.7), which transitively resolved every `tar`/`js-yaml`/
  `ip-address`/`brace-expansion`/`form-data` alert too (`npm audit`: 0
  vulnerabilities). One critical `chromadb` alert dismissed as not
  applicable: it's a transitive dependency of `chromadb-client` that this
  app never runs as a server (only the embedded, in-process client), and no
  patched release exists upstream yet.

## [1.13.51.108] - 2026-07-20

### Initial public release

MyPaiOS — My Personal AI OS — published at
[github.com/mypaios/mypaios](https://github.com/mypaios/mypaios).

Highlights of what ships in this first public version:

- **Chat & agents** against any local or API model (Ollama, vLLM, llama.cpp,
  OpenRouter, OpenAI, GitHub Copilot), with tools, MCP servers, skills, and
  persistent memory. The assistant persona is **Pi**.
- **Cookbook** — hardware-aware model recommendations with one-click download
  and serving (built on llmfit).
- **Deep Research** — multi-step research runs with cited visual reports
  (adapted from Tongyi DeepResearch).
- **Compare** — side-by-side and blind multi-model testing.
- **Documents** — a multi-tab editor where AI assists rather than writes.
- **Email** — IMAP/SMTP with local AI triage (Mail Guard drafts only, never
  auto-sends), **Notes & Tasks**, and a CalDAV-aware **Calendar**.
- **Voice & video** — local speech-to-text (faster-whisper), TTS (Kokoro), and
  video analysis that turns clips into a timestamped, chat-able digest.
- **Crew** multi-agent orchestration and a **Code** tab with Plan / Act /
  Review / Research modes, detached server-side runs, and a universal Stop.
- **Local-first security posture** — auth on by default, admin-gated
  privileged tools, prompt-injection hardening for untrusted content, PWA
  mobile support, 2FA.

### Changed
- Product renamed to **MyPaiOS** (tagline: "My Personal AI OS") for the public
  release; the assistant persona remains **Pi**. Internal identifiers
  intentionally keep their historic `paios` names (see AGENTS.md).
- Documentation set rewritten for the public repository: README, CONTRIBUTING
  (DCO, `main`-based flow), SECURITY (GitHub Private Vulnerability Reporting),
  THREAT_MODEL, CODE_OF_CONDUCT, and issue/PR templates.

---

## Pre-public history (internal builds)

### 0.9.12 - 2026-07-20 — Two-layer brand + reorganized help
- Product/persona split introduced: the product name and the **Pi** assistant
  persona became distinct (~140 strings across app, login, desktop app, docs).
- Help guide reorganized to mirror the app sidebar; reads as pure app help.
- Chat polish: consistent hover action row, content-hugging bubbles,
  jump-to-latest arrow, old chats open at the newest message.

### 0.9.11 - 2026-07-19 — Complete help guide + PDF export
- In-app guide downloadable as a locally rendered PDF (`/help.pdf`).
- 6 new help sections (slash commands, personas & group chat, standing
  instructions, email, deep research, agent tool catalog); 23 sections
  deepened; 13 stale spots fixed after a feature-vs-docs audit.
- Uniform message actions (Copy/Edit/Regenerate), tidier menus.

### 0.9.10 - 2026-07-18 — Video analysis, CLI subscriptions & cost tracking
- Local video analysis: keyframes + speech transcript merge into a timestamped
  digest you can chat with; answers cite `[mm:ss]`; uploads up to 512 MB.
- CLI models: use Claude Code / Codex subscriptions as chat models, no API key.
- Cloud provider groundwork: 11 API presets and real per-message/per-chat cost
  tracking; local models stay free.
- New vision (qwen3-vl) and research model families; stability and UI fixes.

### 0.9.9 - 2026-06-16 — Agents panel simplified
- Cleaner agent cards with one-line summaries, state dots, and tighter
  schedule lines; duplicate-agent guard.

### 0.9.8 / 0.9.7 / 0.9.6 - 2026-06-15 — Deep Research reliability
- Visual Report opens in-app (fixed "Not authenticated" in new tabs).
- Per-step model routing: a fast model reads pages, the reasoner synthesizes —
  research completes in minutes instead of timing out.
- Robust web search client; research modes now change strategy, not just
  output; global and per-project standing-instruction files (`PI.md`).

### 0.9.5 / 0.9.4 / 0.9.3 - 2026-06-14..15 — Control, modes & accessibility
- Display size zoom (90-160%) and reduce-motion accessibility toggles.
- Activity tab became the universal Stop for anything running.
- Code tab modes: Plan (read-only) / Act / Review / Deep Research / Code.
- Code runs finish server-side even if the client disconnects; light activity
  log for fast triage; in-app help modal + live version badge.

### 0.9.2 / 0.9.1 - 2026-06-13..14 — Code agent + UX backlog burn
- Code tab upgraded to a Claude-Code-style agent: reads before editing,
  surgical edits, iterates until done, verifies its work; fixed the 422 error
  that broke Code chats.
- 52 micro-UX fixes (Esc closes modals, error toasts, per-account unread dots,
  bulk archive, and more).

### 0.9.0 - 2026-06-12 — Six major capabilities
- Mail Guard (local AI email triage for up to 40 accounts), Artifacts (live
  inline HTML/SVG/React preview), Voice mode, browser-use tool (Playwright),
  40 prebuilt agent templates, regrouped sidebar.

### 0.8.x - 2026-06-09..11 — Power features
- Crew multi-agent orchestration, Code Board (16 concurrent sessions),
  Activity & capacity monitor, Storage panel, vision chat, deep-think toggle,
  Telegram gateway.

### 0.7.x - 2026-06-05..08 — Automation & local stack
- Agents Hub scheduler, Local AI Hub (six modalities), drive-wide file search,
  Cookbook & Compare, interactive help guide, OCR for scanned PDFs, local
  image generation, Whisper STT + Kokoro TTS.

### 0.1 - 0.6 — Foundation (fork point: Odysseus MIT snapshot, 2026-06-05)
- Chat, sessions, RAG memory (ChromaDB), notes, tasks, calendar, multi-account
  email, connectors hub, Ollama local LLM pipeline.

[1.13.51.108]: https://github.com/mypaios/mypaios/releases/tag/v1.13.51
