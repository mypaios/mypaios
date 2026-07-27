"""Artifacts — live preview of agent-generated HTML / SVG / React, Claude-style.

The chat (or Code board) detects a previewable code block, POSTs it here, and
embeds GET /artifact/{id} in a sandboxed iframe. Design notes:

- The preview page is a REAL navigation (not iframe srcdoc), so it can carry
  its own permissive CSP without loosening the app shell's, and "Open in new
  tab" is free.
- The iframe embeds it with sandbox="allow-scripts ..." and NO
  allow-same-origin → the artifact runs with an opaque origin and cannot read
  Pi's cookies, storage, or DOM even though it is served from the same host.
- GET is deliberately session-free: the 128-bit random id IS the capability
  (the sandboxed iframe may not send cookies reliably). Artifacts live only
  in process memory (LRU, capped) and die with the server.
- React/JSX runs via vendored Babel + React UMD (static/libs/artifacts/*) so
  it works fully offline — no CDN required.
"""

from __future__ import annotations

import logging
import re
import secrets
import time
from collections import OrderedDict
from threading import Lock

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from src.auth_helpers import get_current_user

logger = logging.getLogger("artifacts")

_MAX_ARTIFACTS = 80
_MAX_CODE_CHARS = 600_000
_store: "OrderedDict[str, dict]" = OrderedDict()
_lock = Lock()

# Sandboxed-iframe-friendly CSP for the artifact document itself. Inline +
# eval are required (Babel transforms in-page); https: lets generated pages
# pull CDN assets (Tailwind, Chart.js, fonts) when online. The opaque-origin
# sandbox in the parent iframe is what isolates this from Pi proper.
_ARTIFACT_CSP = (
    "default-src 'self' https: data: blob:; "
    "script-src 'self' 'unsafe-inline' 'unsafe-eval' https: blob:; "
    "style-src 'self' 'unsafe-inline' https:; "
    "img-src * data: blob:; font-src * data:; connect-src *; media-src * data: blob:; "
    "frame-ancestors 'self'"
)

_REACT_LANGS = {"jsx", "tsx", "react"}
_HTML_LANGS = {"html", "htm", "xhtml"}
_SVG_LANGS = {"svg"}


class ArtifactIn(BaseModel):
    code: str
    lang: str = "html"
    title: str = ""


def _looks_full_document(code: str) -> bool:
    head = code.lstrip()[:200].lower()
    return head.startswith("<!doctype") or head.startswith("<html")


def _wrap_html_fragment(code: str, title: str) -> str:
    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title or 'Artifact'}</title>
<style>body{{margin:16px;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;background:#fff;color:#1d2128}}</style>
</head><body>
{code}
</body></html>"""


def _wrap_svg(code: str, title: str) -> str:
    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>{title or 'SVG artifact'}</title>
<style>html,body{{margin:0;height:100%}}body{{display:flex;align-items:center;justify-content:center;background:#fff}}svg{{max-width:96vw;max-height:96vh}}</style>
</head><body>
{code}
</body></html>"""


def _wrap_react(code: str, title: str) -> str:
    # The user code is embedded as a non-executing template script and
    # transformed in-page by the vendored Babel (modules → CJS, JSX → JS).
    # A tiny CJS shim provides require()/exports so `import React ...` and
    # `export default App` both work as Claude-style artifacts expect.
    safe = code.replace("</script", "<\\/script")
    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title or 'React artifact'}</title>
<style>body{{margin:0;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;background:#fff;color:#1d2128}}#root{{min-height:100vh}}
#artifact-err{{display:none;white-space:pre-wrap;font:12px/1.5 ui-monospace,Menlo,monospace;color:#b3261e;background:#fdecea;border:1px solid #f5c6c0;border-radius:8px;margin:14px;padding:12px}}</style>
<script src="/static/libs/artifacts/react.production.min.js"></script>
<script src="/static/libs/artifacts/react-dom.production.min.js"></script>
<script src="/static/libs/artifacts/babel.min.js"></script>
</head><body>
<div id="root"></div>
<pre id="artifact-err"></pre>
<script type="text/artifact-source">{safe}</script>
<script>
(function () {{
  var errBox = document.getElementById('artifact-err');
  function fail(msg) {{ errBox.style.display = 'block'; errBox.textContent = String(msg); }}
  try {{
    var src = document.querySelector('script[type="text/artifact-source"]').textContent;
    var out = Babel.transform(src, {{
      filename: 'artifact.tsx',
      presets: [['env', {{ modules: 'commonjs' }}], 'react', 'typescript'],
    }}).code;
    var exportsObj = {{}};
    var moduleObj = {{ exports: exportsObj }};
    var shim = {{
      'react': React,
      'react-dom': ReactDOM,
      'react-dom/client': ReactDOM,
    }};
    var requireShim = function (name) {{
      if (shim[name]) return shim[name];
      throw new Error("Module '" + name + "' is not available in the local preview. Only react / react-dom are bundled.");
    }};
    var fn = new Function('require', 'module', 'exports', 'React', 'ReactDOM', out);
    fn(requireShim, moduleObj, moduleObj.exports, React, ReactDOM);
    var Comp = moduleObj.exports && (moduleObj.exports.default || moduleObj.exports);
    if (Comp && typeof Comp === 'object' && !Comp.$$typeof) {{
      for (var k in Comp) {{
        if (typeof Comp[k] === 'function') {{ Comp = Comp[k]; break; }}
      }}
    }}
    if (typeof Comp !== 'function' && !(Comp && Comp.$$typeof)) {{
      var names = Object.keys(moduleObj.exports || {{}});
      throw new Error('No renderable component export found' + (names.length ? ' (exports: ' + names.join(', ') + ')' : '') + '. Use `export default function App() {{...}}`.');
    }}
    ReactDOM.createRoot(document.getElementById('root')).render(React.createElement(Comp));
  }} catch (e) {{
    fail(e && (e.stack || e.message) || e);
  }}
}})();
</script>
</body></html>"""


def build_artifact_html(code: str, lang: str, title: str) -> str:
    lang = (lang or "").strip().lower()
    if lang in _REACT_LANGS:
        return _wrap_react(code, title)
    if lang in _SVG_LANGS or (lang == "" and code.lstrip()[:4].lower() == "<svg"):
        return _wrap_svg(code, title)
    # html / unknown: full documents pass through, fragments get a shell
    if _looks_full_document(code):
        return code
    return _wrap_html_fragment(code, title)


def setup_artifact_routes() -> APIRouter:
    router = APIRouter(tags=["artifacts"])

    @router.post("/api/artifacts")
    def create_artifact(body: ArtifactIn, user=Depends(get_current_user)):
        code = body.code or ""
        if not code.strip():
            raise HTTPException(status_code=400, detail="Empty artifact code")
        if len(code) > _MAX_CODE_CHARS:
            raise HTTPException(status_code=413, detail="Artifact too large")
        title = re.sub(r"[\r\n<>]", " ", body.title or "")[:120]
        art_id = secrets.token_urlsafe(16)
        html = build_artifact_html(code, body.lang, title)
        with _lock:
            _store[art_id] = {
                "html": html,
                "title": title or "Artifact",
                "lang": (body.lang or "html").lower(),
                "ts": time.time(),
            }
            while len(_store) > _MAX_ARTIFACTS:
                _store.popitem(last=False)
        return {"id": art_id, "url": f"/artifact/{art_id}"}

    @router.get("/artifact/{art_id}")
    def get_artifact(art_id: str):
        with _lock:
            entry = _store.get(art_id)
            if entry:
                _store.move_to_end(art_id)
        if not entry:
            return HTMLResponse(
                "<!DOCTYPE html><html><body style='font-family:sans-serif;color:#666;"
                "display:flex;align-items:center;justify-content:center;height:96vh'>"
                "<div>This preview has expired — re-open it from the chat (artifacts "
                "live in memory and reset when Pi restarts).</div></body></html>",
                status_code=404,
            )
        return HTMLResponse(
            entry["html"],
            headers={
                "Content-Security-Policy": _ARTIFACT_CSP,
                "Cache-Control": "no-store",
                "X-Content-Type-Options": "nosniff",
            },
        )

    return router
