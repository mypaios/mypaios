"""Repo map — a concise, token-budgeted map of a whole project for the coding agent.

Inspired by Aider's repo map: give the model the project's structure plus the key
symbols (functions / classes + signatures) from every code file, so it understands
the codebase without reading every file. Plus the project "constitution"
(AGENTS.md / CLAUDE.md / README). Pure-stdlib (ast for Python, regex for the rest)
— no tree-sitter dependency.
"""

from __future__ import annotations

import ast
import os
import re
import time
from typing import Dict, List, Optional, Tuple

# Directories never worth mapping.
_IGNORE_DIRS = {
    ".git", ".hg", ".svn", "node_modules", "venv", ".venv", "env", "__pycache__",
    ".mypy_cache", ".pytest_cache", ".ruff_cache", "dist", "build", ".next",
    ".nuxt", "target", "out", ".idea", ".vscode", ".gradle", "vendor", "Pods",
    ".terraform", "coverage", ".cache", "site-packages", ".tox", "bin", "obj",
}
_IGNORE_SUFFIX = (".min.js", ".min.css", ".lock", ".map", ".pyc", ".so", ".dylib",
                  ".o", ".a", ".class", ".jar", ".png", ".jpg", ".jpeg", ".gif",
                  ".pdf", ".zip", ".tar", ".gz", ".mp4", ".mov", ".woff", ".woff2",
                  ".ttf", ".ico", ".bin", ".onnx", ".gguf", ".safetensors")

_CODE_EXT = {
    ".py": "python", ".js": "js", ".jsx": "js", ".mjs": "js", ".cjs": "js",
    ".ts": "ts", ".tsx": "ts", ".go": "go", ".rs": "rust", ".java": "java",
    ".kt": "kotlin", ".c": "c", ".h": "c", ".cpp": "cpp", ".cc": "cpp",
    ".hpp": "cpp", ".cs": "csharp", ".rb": "ruby", ".php": "php", ".swift": "swift",
    ".scala": "scala", ".sh": "shell", ".lua": "lua",
}

_MAX_FILES = 4000
_MAX_FILE_BYTES = 400_000
_DEFAULT_BUDGET = 14000   # chars of symbol section (the map text the model sees)

_AGENTS_NAMES = ["PI.md", "pi.md", "AGENTS.md", "CLAUDE.md", ".cursorrules", ".github/copilot-instructions.md"]
_README_NAMES = ["README.md", "README.rst", "README.txt", "README"]

# small in-memory cache: root -> (built_at, context)
_CACHE: Dict[str, Tuple[float, dict]] = {}
_CACHE_TTL = 120.0


# ───────────────────────── symbol extraction ─────────────────────────
def _py_symbols(src: str) -> List[str]:
    out: List[str] = []
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return out

    def sig(fn) -> str:
        a = [ar.arg for ar in fn.args.args]
        if fn.args.vararg:
            a.append("*" + fn.args.vararg.arg)
        if fn.args.kwarg:
            a.append("**" + fn.args.kwarg.arg)
        kind = "async def" if isinstance(fn, ast.AsyncFunctionDef) else "def"
        return f"{kind} {fn.name}({', '.join(a)})"

    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            out.append(sig(node))
        elif isinstance(node, ast.ClassDef):
            bases = ", ".join(b.id for b in node.bases if isinstance(b, ast.Name))
            out.append(f"class {node.name}" + (f"({bases})" if bases else ""))
            methods = [m for m in node.body if isinstance(m, (ast.FunctionDef, ast.AsyncFunctionDef))]
            for m in methods[:12]:
                out.append("    " + sig(m))
    return out


_JS_PATTERNS = [
    re.compile(r"^\s*export\s+(?:default\s+)?(?:async\s+)?function\s+(\w+)\s*\(([^)]*)\)", re.M),
    re.compile(r"^\s*(?:export\s+)?(?:async\s+)?function\s+(\w+)\s*\(([^)]*)\)", re.M),
    re.compile(r"^\s*export\s+(?:default\s+)?class\s+(\w+)", re.M),
    re.compile(r"^\s*class\s+(\w+)", re.M),
    re.compile(r"^\s*export\s+const\s+(\w+)\s*=\s*(?:async\s*)?\(([^)]*)\)\s*=>", re.M),
    re.compile(r"^\s*export\s+(?:const|let|var)\s+(\w+)", re.M),
]
_GENERIC_PATTERNS = {
    "go": [re.compile(r"^\s*func\s+(?:\([^)]*\)\s*)?(\w+)\s*\(([^)]*)\)", re.M),
           re.compile(r"^\s*type\s+(\w+)\s+(?:struct|interface)", re.M)],
    "rust": [re.compile(r"^\s*(?:pub\s+)?fn\s+(\w+)\s*\(([^)]*)\)", re.M),
             re.compile(r"^\s*(?:pub\s+)?(?:struct|enum|trait)\s+(\w+)", re.M)],
    "java": [re.compile(r"^\s*(?:public|private|protected).*?\b(\w+)\s*\(([^)]*)\)\s*\{", re.M),
             re.compile(r"^\s*(?:public\s+)?(?:class|interface|enum)\s+(\w+)", re.M)],
    "ruby": [re.compile(r"^\s*def\s+(\w+)", re.M), re.compile(r"^\s*class\s+(\w+)", re.M)],
    "php": [re.compile(r"^\s*(?:public|private|protected|static|\s)*function\s+(\w+)\s*\(([^)]*)\)", re.M),
            re.compile(r"^\s*class\s+(\w+)", re.M)],
    "c": [re.compile(r"^[A-Za-z_][\w\s\*]*\b(\w+)\s*\(([^)]*)\)\s*\{", re.M)],
    "cpp": [re.compile(r"^[A-Za-z_][\w\s\*:<>]*\b(\w+)\s*\(([^)]*)\)\s*\{", re.M),
            re.compile(r"^\s*(?:class|struct)\s+(\w+)", re.M)],
    "csharp": [re.compile(r"^\s*(?:public|private|protected|internal).*?\b(\w+)\s*\(([^)]*)\)", re.M),
               re.compile(r"^\s*(?:public\s+)?(?:class|interface|struct|enum)\s+(\w+)", re.M)],
    "swift": [re.compile(r"^\s*func\s+(\w+)\s*\(([^)]*)\)", re.M),
              re.compile(r"^\s*(?:class|struct|enum|protocol)\s+(\w+)", re.M)],
    "shell": [re.compile(r"^\s*(?:function\s+)?(\w+)\s*\(\)\s*\{", re.M)],
}


def _regex_symbols(src: str, lang: str) -> List[str]:
    out: List[str] = []
    pats = _JS_PATTERNS if lang in ("js", "ts") else _GENERIC_PATTERNS.get(lang, [])
    seen = set()
    for pat in pats:
        for m in pat.finditer(src):
            name = m.group(1)
            if not name or name in seen:
                continue
            seen.add(name)
            args = m.group(2) if m.re.groups >= 2 and m.lastindex and m.lastindex >= 2 else None
            out.append(f"{name}({args.strip()})" if args is not None else name)
            if len(out) >= 40:
                return out
    return out


def _symbols(path: str, lang: str) -> List[str]:
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            src = f.read(_MAX_FILE_BYTES)
    except OSError:
        return []
    if lang == "python":
        return _py_symbols(src)
    return _regex_symbols(src, lang)


# ───────────────────────── walk + tree ─────────────────────────
def _walk(root: str):
    """Yield (relpath, lang) for code files; collect tree lines too."""
    code_files: List[Tuple[str, str]] = []
    tree_lines: List[str] = []
    n = 0
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d not in _IGNORE_DIRS and not d.startswith("."))[:80]
        rel = os.path.relpath(dirpath, root)
        depth = 0 if rel == "." else rel.count(os.sep) + 1
        if depth > 6:
            dirnames[:] = []
            continue
        if rel != ".":
            tree_lines.append("  " * (depth - 1) + os.path.basename(dirpath) + "/")
        for fn in sorted(filenames)[:200]:
            if fn.startswith(".") or fn.endswith(_IGNORE_SUFFIX):
                continue
            ext = os.path.splitext(fn)[1].lower()
            relf = os.path.normpath(os.path.join(rel, fn)) if rel != "." else fn
            if ext in _CODE_EXT:
                code_files.append((relf, _CODE_EXT[ext]))
                tree_lines.append("  " * depth + fn)
                n += 1
            elif fn.lower() in ("readme.md", "package.json", "pyproject.toml", "requirements.txt",
                                "go.mod", "cargo.toml", "dockerfile", "makefile", "agents.md", "claude.md"):
                tree_lines.append("  " * depth + fn)
            if n >= _MAX_FILES:
                return code_files, tree_lines
    return code_files, tree_lines


def _read_first(root: str, names: List[str], limit: int) -> Optional[Tuple[str, str]]:
    for name in names:
        p = os.path.join(root, name)
        if os.path.isfile(p):
            try:
                with open(p, "r", encoding="utf-8", errors="ignore") as f:
                    return name, f.read(limit)
            except OSError:
                continue
    return None


def load_project_pi(root: str, limit: int = 8000):
    """Per-project constitution file (PI.md > AGENTS.md > CLAUDE.md > …).
    First-found wins. Returns (filename, text) or None. Used by chat/research
    to honor a project's PI.md the same way the Code tab does."""
    try:
        root = os.path.abspath(os.path.expanduser(root or ""))
    except Exception:
        return None
    if not root or not os.path.isdir(root):
        return None
    return _read_first(root, _AGENTS_NAMES, limit)


def load_global_pi(limit: int = 4000) -> str:
    """Global, user-wide instructions from <DATA_DIR>/PI.md (like ~/.claude/CLAUDE.md).
    Always-on, lowest precedence (a project PI.md can override it in prose)."""
    try:
        from src.constants import PI_MD
        if os.path.isfile(PI_MD):
            with open(PI_MD, "r", encoding="utf-8", errors="ignore") as f:
                return f.read(limit).strip()
    except Exception:
        pass
    return ""


def _importance(relf: str) -> int:
    """Higher = include earlier in the budget. Entry points & shallow files first."""
    base = os.path.basename(relf).lower()
    score = 0
    if base in ("__init__.py", "main.py", "app.py", "index.js", "index.ts", "main.go",
                "main.rs", "server.py", "cli.py", "mod.rs", "lib.rs"):
        score += 50
    score -= relf.count(os.sep) * 5     # prefer shallow
    if any(t in relf.lower() for t in ("test", "spec", "__tests__", "migrations")):
        score -= 20
    return score


# ───────────────────────── public API ─────────────────────────
def build_context(root: str, budget_chars: int = _DEFAULT_BUDGET, rebuild: bool = False) -> dict:
    """Return a project map + constitution for `root`.

    Keys: ok, root, tree, map_text, agents (name+content), readme, stats, prompt_text.
    `prompt_text` is the ready-to-inject block for the agent's system message.
    """
    root = os.path.abspath(os.path.expanduser(root or ""))
    if not os.path.isdir(root):
        return {"ok": False, "error": f"not a folder: {root}"}

    if not rebuild:
        c = _CACHE.get(root)
        if c and (time.time() - c[0]) < _CACHE_TTL:
            return c[1]

    code_files, tree_lines = _walk(root)
    # symbol section, budget-bounded, important files first
    code_files.sort(key=lambda cf: _importance(cf[0]), reverse=True)
    sym_lines: List[str] = []
    used = 0
    mapped = 0
    for relf, lang in code_files:
        syms = _symbols(os.path.join(root, relf), lang)
        if not syms:
            continue
        block = relf + "\n" + "\n".join("  " + s for s in syms[:25]) + "\n"
        if used + len(block) > budget_chars:
            if used == 0:
                sym_lines.append(block[:budget_chars])
            sym_lines.append(f"\n… (+{len(code_files) - mapped} more files not shown — ask or use grep/read_file)")
            break
        sym_lines.append(block)
        used += len(block)
        mapped += 1

    tree_txt = "\n".join(tree_lines[:400])
    agents = _read_first(root, _AGENTS_NAMES, 8000)
    readme = _read_first(root, _README_NAMES, 3000)

    langs: Dict[str, int] = {}
    for _, lang in code_files:
        langs[lang] = langs.get(lang, 0) + 1
    stats = {"code_files": len(code_files), "mapped": mapped,
             "languages": dict(sorted(langs.items(), key=lambda x: -x[1]))}

    # assemble the injectable block
    parts = [f"# PROJECT: {os.path.basename(root)}  ({root})",
             f"Languages: {', '.join(f'{k}×{v}' for k, v in stats['languages'].items()) or 'mixed'} · {len(code_files)} code files"]
    if agents:
        parts.append(f"\n## Project instructions ({agents[0]})\n{agents[1].strip()}")
    elif readme:
        parts.append(f"\n## README ({readme[0]})\n{readme[1].strip()}")
    parts.append("\n## File tree\n" + tree_txt)
    parts.append("\n## Key symbols (functions/classes by file)\n" + "".join(sym_lines).strip())
    prompt_text = "\n".join(parts)

    ctx = {"ok": True, "root": root, "tree": tree_txt, "map_text": "".join(sym_lines).strip(),
           "agents": ({"name": agents[0], "content": agents[1]} if agents else None),
           "readme": ({"name": readme[0], "content": readme[1]} if readme else None),
           "stats": stats, "prompt_text": prompt_text}
    _CACHE[root] = (time.time(), ctx)
    return ctx
