# Contributing to MyPaiOS

Thanks for helping. MyPaiOS is maintained by a single person (Vishal Pawar), so the best contributions are focused, easy to review, and easy to test.

## Branch model

The public repository at [github.com/mypaios/mypaios](https://github.com/mypaios/mypaios) uses a single default branch:

- **`main`** — the default branch. All PRs target `main`, and releases are tagged from it (e.g. `v1.13.51`).

Open your PR against `main`. Work in a feature branch in your fork (`fix/…`, `feat/…`) and keep it rebased on the latest `main`.

## Solo-maintainer expectations

This is a personal project with one maintainer. That means:

- **Response time is best-effort.** Reviews may take days, occasionally longer. A friendly ping after a week is fine.
- **Small PRs get merged; big PRs get discussed.** For anything beyond a focused fix, open an issue first and describe the approach before writing code.
- **Scope is curated.** The maintainer may decline features that add maintenance burden without clear benefit, even well-built ones. An issue-first conversation avoids wasted work.
- **Issues > PRs for agent output.** If you are running an LLM agent (Devin, Cursor, OpenHands, Claude Code, etc.) against this repo, please open an issue describing the problem first instead of opening a PR directly. Bulk agent-generated PRs that don't match the project's visual style or contribution format will be closed without review, even when the underlying fix is correct.

## Developer Certificate of Origin (DCO)

All commits must be signed off:

```bash
git commit -s -m "fix: describe the change"
```

The `-s` flag adds a `Signed-off-by: Your Name <you@example.com>` trailer, which certifies you agree to the [Developer Certificate of Origin](https://developercertificate.org/): that you wrote the change or otherwise have the right to submit it under the project's MIT license. No CLA, no paperwork — just the sign-off line. PRs with unsigned commits will be asked to rebase with `git rebase --signoff`.

**Why DCO?** MyPaiOS is an MIT fork of an upstream project that later changed license. A clean, auditable statement of origin on every commit protects both you and the project. Related rule: **never port code from upstream Odysseus committed after 2026-06-09** — it is AGPL-3.0 and cannot enter this MIT codebase.

## Before You Start

- Search existing issues and pull requests before opening a new one.
- Prefer one bug fix or feature per pull request.
- Avoid broad rewrites, formatting-only changes, or moving many files unless the issue is specifically about structure.
- If you want to work on a large feature, open an issue first and describe the approach.
- Do not rename internal identifiers (`paios-*` keys, `PAIOS_*` env vars, `X-PAIOS-*` headers, module names). They are historic and load-bearing; see the naming note in [AGENTS.md](AGENTS.md).

## Setup

Docker is the recommended path for normal testing:

```bash
git clone https://github.com/mypaios/mypaios && cd mypaios
cp .env.example .env
docker compose up -d --build
```

Manual development uses Python 3.11+:

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python setup.py
python -m uvicorn app:app --host 127.0.0.1 --port 7000
```

Windows is not actively tested. Docker on Linux or a Linux/macOS manual install is the safer path for now.

## Running Tests and Checks

The test suite is plain pytest:

```bash
# full suite
python -m pytest

# one file, or one test
python -m pytest tests/test_readme_ascii_fenced.py
python -m pytest tests/test_readme_ascii_fenced.py -k banner
```

Run the smallest relevant checks for your change:

```bash
python -m pytest
python -m py_compile app.py routes/*.py src/*.py
node --check static/js/<file-you-changed>.js
```

For Docker-related changes:

```bash
docker compose config
docker compose up -d --build
docker compose logs --tail=120 paios
```

Mention what you ran in the pull request description. If you could not run a check, say so.

## Pull Requests

Good pull requests usually include:

- A short explanation of the bug or feature.
- The files or areas changed.
- Manual test steps or automated test results from running the actual app, not just the test suite.
- Screenshots or short recordings for UI changes.
- Links to related issues, for example `Fixes #123`.
- DCO sign-off on every commit (`git commit -s`).

Please keep PRs small. Large PRs that mix unrelated cleanup, formatting, refactors, and behavior changes are much harder to review.

## Style and visual changes

MyPaiOS has an intentional visual style. PRs that ignore it will be closed without merge, no matter how correct the underlying code is.

Before submitting any change that affects what the app looks like — buttons, icons, fonts, colors, spacing, layout, CSS, HTML, SVG, or any `static/js/` module that draws to the DOM — please:

1. **Run the app locally** and view the change in a browser. Type-checks and unit tests are not enough.
2. **Attach a screenshot or short clip** of the change in the running app. Add a mobile screenshot too if the change affects mobile.
3. **Match the existing visual language.** Specifically:
   - Reuse existing CSS variables (`--red`, `--fg`, `--bg`, `--card`, `--border`, …). Do not introduce new color values, font sizes, or spacing units.
   - Reuse existing button, input, card, and border classes. Don't invent parallel styling for similar widgets.
   - **No Unicode emoji in UI or code.** Use inline SVG (matching the monochrome icon style already in `static/index.html`) or plain text.
   - Monospaced font (`Fira Code`) for primary UI text. Don't override.
   - Dark theme is the default; any light-mode work goes through the existing theme system, not hard-coded.
4. **Don't add parallel components.** If a similar widget already exists in the app, extend it instead of writing a new one.

If you are unsure whether a change is "visual," it is. Default to attaching a screenshot.

## Issue Reports

For bugs, include:

- Install method: Docker, manual Python, WSL, etc.
- OS, browser, and device if relevant.
- Exact steps to reproduce.
- Expected behavior and actual behavior.
- Logs, screenshots, or terminal output.

For model-serving issues, include:

- Backend: Ollama, vLLM, SGLang, llama.cpp, LM Studio, etc.
- Model name.
- GPU/CPU and operating system.
- Cookbook task logs or server logs.

Issues with only "help", "does not work", or a screenshot without context may be closed as not actionable.

## Security

Do not post secrets, API keys, private logs, personal documents, or public IPs in issues or pull requests.

For security reports, use GitHub Private Vulnerability Reporting — see [SECURITY.md](SECURITY.md).
