"""Agentic browser tool — Playwright Chromium driven by the agent loop.

Five small tools (navigate / read / click / fill / screenshot) that share one
headless Chromium page per process, so multi-step flows ("open the docs,
click Pricing, read the table") keep state between calls.

Threading model: Playwright's sync API must stay on the thread that started
it, while tool execution is async. All browser work is therefore funneled
through a single-worker ThreadPoolExecutor (`_run`), giving thread affinity
without blocking the event loop. The browser closes itself after
IDLE_CLOSE_SEC of inactivity to free RAM.

Security posture (local, single-admin Pi):
- http/https only — file:, javascript:, data: navigations are refused.
- The page runs in its own Chromium profile: no access to the user's real
  browser cookies or sessions.
- Page text returned to the model is DATA. The tool prompt (agent_loop
  TOOL_SECTIONS) instructs the model not to obey instructions found in pages.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlparse

logger = logging.getLogger("browser.tool")

IDLE_CLOSE_SEC = 300
NAV_TIMEOUT_MS = 25_000
ACTION_TIMEOUT_MS = 8_000
TEXT_BRIEF = 3_500
TEXT_FULL = 12_000
MAX_LINKS = 30
MAX_FIELDS = 15

_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="pi-browser")
_state_lock = threading.Lock()
_pw = None
_browser = None
_context = None
_page = None
_last_used = 0.0
_idle_timer: threading.Timer | None = None


# ---------------------------------------------------------------------------
# Lifecycle (all on the executor thread)
# ---------------------------------------------------------------------------

def _ensure_page():
    global _pw, _browser, _context, _page, _last_used
    _touch()
    if _page is not None:
        try:
            _ = _page.url  # liveness probe
            return _page
        except Exception:
            _teardown()
    from playwright.sync_api import sync_playwright
    _pw = sync_playwright().start()
    _browser = _pw.chromium.launch(headless=True)
    _context = _browser.new_context(
        viewport={"width": 1280, "height": 900},
        user_agent=(
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36 PiAOS-Agent"
        ),
        accept_downloads=False,
    )
    _context.set_default_timeout(ACTION_TIMEOUT_MS)
    _page = _context.new_page()
    logger.info("browser tool: chromium started")
    return _page


def _teardown():
    global _pw, _browser, _context, _page
    for closer in (
        lambda: _context.close() if _context else None,
        lambda: _browser.close() if _browser else None,
        lambda: _pw.stop() if _pw else None,
    ):
        try:
            closer()
        except Exception:
            pass
    _pw = _browser = _context = _page = None
    logger.info("browser tool: chromium closed")


def _touch():
    global _last_used, _idle_timer
    _last_used = time.time()
    if _idle_timer:
        _idle_timer.cancel()
    _idle_timer = threading.Timer(IDLE_CLOSE_SEC, _idle_close)
    _idle_timer.daemon = True
    _idle_timer.start()


def _idle_close():
    if time.time() - _last_used >= IDLE_CLOSE_SEC - 1:
        _executor.submit(_teardown)


async def _run(fn, *args):
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(_executor, fn, *args)


# ---------------------------------------------------------------------------
# Page-state summary the model can act on
# ---------------------------------------------------------------------------

def _clean(text: str, limit: int) -> str:
    text = re.sub(r"\n{3,}", "\n\n", (text or "").strip())
    if len(text) > limit:
        text = text[:limit] + f"\n… [truncated — {len(text)} chars total; use browser_read full=true for more]"
    return text


def _page_state(page, text_limit=TEXT_BRIEF) -> str:
    parts = [f"URL: {page.url}", f"Title: {page.title()}"]
    try:
        body = page.inner_text("body", timeout=3000)
    except Exception:
        body = ""
    parts.append("--- page text ---")
    parts.append(_clean(body, text_limit))
    try:
        links = page.eval_on_selector_all(
            "a[href]",
            """els => els
                .filter(e => e.offsetParent !== null && (e.innerText || '').trim())
                .slice(0, %d)
                .map(e => (e.innerText.trim().slice(0, 80) + ' -> ' + e.href))""" % MAX_LINKS,
        )
        if links:
            parts.append("--- links (text -> url) ---")
            parts.append("\n".join(links))
    except Exception:
        pass
    try:
        fields = page.eval_on_selector_all(
            "input, textarea, select, button[type=submit]",
            """els => els
                .filter(e => e.offsetParent !== null)
                .slice(0, %d)
                .map(e => {
                  const tag = e.tagName.toLowerCase();
                  const t = e.type || '';
                  const name = e.name || e.id || '';
                  const ph = e.placeholder || '';
                  const label = (e.labels && e.labels[0] && e.labels[0].innerText) || '';
                  return tag + (t ? ':' + t : '') + (name ? ' name=' + name : '') +
                         (ph ? ' placeholder=\"' + ph + '\"' : '') + (label ? ' label=\"' + label.trim() + '\"' : '');
                })""" % MAX_FIELDS,
        )
        if fields:
            parts.append("--- form fields ---")
            parts.append("\n".join(fields))
    except Exception:
        pass
    return "\n".join(parts)


def _check_url(url: str) -> str:
    url = (url or "").strip()
    if not url:
        raise ValueError("No URL given")
    if "://" not in url:
        url = "https://" + url
    scheme = urlparse(url).scheme.lower()
    if scheme not in ("http", "https"):
        raise ValueError(f"Only http/https URLs are allowed (got {scheme}:)")
    return url


# ---------------------------------------------------------------------------
# Public tool operations (sync bodies run on the executor thread)
# ---------------------------------------------------------------------------

async def navigate(url: str) -> dict:
    def _do():
        target = _check_url(url)
        page = _ensure_page()
        page.goto(target, timeout=NAV_TIMEOUT_MS, wait_until="domcontentloaded")
        try:
            page.wait_for_load_state("networkidle", timeout=4000)
        except Exception:
            pass
        return {"output": _page_state(page), "exit_code": 0}
    return await _guarded(_do)


async def read(selector: str = "", full: bool = False) -> dict:
    def _do():
        page = _ensure_page()
        if not page.url or page.url == "about:blank":
            return {"error": "No page open — call browser_navigate first.", "exit_code": 1}
        limit = TEXT_FULL if full else TEXT_BRIEF
        if selector:
            try:
                text = page.inner_text(selector, timeout=ACTION_TIMEOUT_MS)
            except Exception as e:
                return {"error": f"Selector {selector!r} not found: {e}", "exit_code": 1}
            return {"output": f"URL: {page.url}\n--- {selector} ---\n{_clean(text, limit)}", "exit_code": 0}
        return {"output": _page_state(page, text_limit=limit), "exit_code": 0}
    return await _guarded(_do)


async def click(target: str) -> dict:
    def _do():
        page = _ensure_page()
        if not target or not target.strip():
            return {"error": "Give the link/button text or a CSS selector to click.", "exit_code": 1}
        t = target.strip()
        attempts = []
        looks_selector = bool(re.match(r"^[#.\[]|^[a-z]+[#.\[:>]", t)) and " " not in t[:2]
        if looks_selector:
            attempts.append(lambda: page.click(t, timeout=ACTION_TIMEOUT_MS))
        attempts.extend([
            lambda: page.get_by_role("link", name=t).first.click(timeout=ACTION_TIMEOUT_MS),
            lambda: page.get_by_role("button", name=t).first.click(timeout=ACTION_TIMEOUT_MS),
            lambda: page.get_by_text(t, exact=False).first.click(timeout=ACTION_TIMEOUT_MS),
            lambda: page.click(t, timeout=ACTION_TIMEOUT_MS),
        ])
        last_err = None
        for attempt in attempts:
            try:
                attempt()
                last_err = None
                break
            except Exception as e:
                last_err = e
        if last_err is not None:
            return {"error": f"Could not click {t!r}: {last_err}", "exit_code": 1}
        try:
            page.wait_for_load_state("domcontentloaded", timeout=6000)
        except Exception:
            pass
        return {"output": f"Clicked {t!r}.\n\n" + _page_state(page), "exit_code": 0}
    return await _guarded(_do)


async def fill(selector: str, value: str, submit: bool = False) -> dict:
    def _do():
        page = _ensure_page()
        if not selector:
            return {"error": "Give a CSS selector, placeholder or label of the field to fill.", "exit_code": 1}
        s = selector.strip()
        target = None
        for finder in (
            lambda: page.locator(s).first,
            lambda: page.get_by_placeholder(s).first,
            lambda: page.get_by_label(s).first,
        ):
            try:
                loc = finder()
                loc.wait_for(state="visible", timeout=2500)
                target = loc
                break
            except Exception:
                continue
        if target is None:
            return {"error": f"No visible field matches {s!r} (selector / placeholder / label).", "exit_code": 1}
        target.fill(value or "")
        if submit:
            target.press("Enter")
            try:
                page.wait_for_load_state("domcontentloaded", timeout=6000)
            except Exception:
                pass
        return {"output": f"Filled {s!r}" + (" and pressed Enter" if submit else "") + ".\n\n" + _page_state(page), "exit_code": 0}
    return await _guarded(_do)


async def screenshot(workspace: str | None = None) -> dict:
    def _do():
        page = _ensure_page()
        if not page.url or page.url == "about:blank":
            return {"error": "No page open — call browser_navigate first.", "exit_code": 1}
        base = workspace if (workspace and os.path.isdir(workspace)) else os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "data", "browser_shots")
        os.makedirs(base, exist_ok=True)
        name = f"browser_{time.strftime('%Y%m%d_%H%M%S')}.png"
        path = os.path.join(base, name)
        page.screenshot(path=path, full_page=False)
        return {"output": f"Screenshot saved: {path}\nURL: {page.url}\nTitle: {page.title()}", "image_path": path, "exit_code": 0}
    return await _guarded(_do)


async def close() -> dict:
    def _do():
        _teardown()
        return {"output": "Browser closed.", "exit_code": 0}
    return await _guarded(_do)


async def _guarded(fn) -> dict:
    try:
        return await _run(fn)
    except ValueError as e:
        return {"error": str(e), "exit_code": 1}
    except Exception as e:
        msg = str(e).splitlines()[0][:300]
        logger.warning("browser tool error: %s", msg)
        return {"error": f"Browser error: {msg}", "exit_code": 1}
