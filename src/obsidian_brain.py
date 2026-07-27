"""
Obsidian "brain" write-back.

Persists every chat turn into the user's OWN Obsidian vault so knowledge
accumulates and PiAOS can retrieve it later (the same vault is indexed
into RAG, closing the read/write loop). For each turn we save three things:

  1. Transcript  — the full You / PAIOS exchange, appended to a per-session note.
  2. Outputs     — fenced code blocks extracted to standalone files for reuse.
  3. Summary     — a short synopsis in the note's YAML front-matter.

Per-user and isolated: each owner maps to their own vault via
data/obsidian_vaults.json (owner -> absolute path), with a single-user
PAIOS_OBSIDIAN_VAULT env fallback. If an owner has no vault configured, every
function here is a safe no-op — nothing is shared across users.
"""

from __future__ import annotations

import os
import re
import json
import glob
import logging
from datetime import datetime

# Resolve the data dir from this file's location rather than importing
# core.constants — importing the `core` package triggers heavy side effects
# (DB init), and write-back must stay a light, self-contained best-effort path.
_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(_BASE_DIR, "data")

logger = logging.getLogger(__name__)

VAULTS_MAP_FILE = os.path.join(DATA_DIR, "obsidian_vaults.json")

# Folder created inside each vault for PAIOS-generated notes.
BRAIN_SUBDIR = "PiAOS"
CHATS_SUBDIR = "Chats"
OUTPUTS_SUBDIR = "Outputs"

_CODE_BLOCK_RE = re.compile(r"```([\w+.-]*)\n(.*?)```", re.DOTALL)
_EXT_BY_LANG = {
    "python": "py", "py": "py", "javascript": "js", "js": "js",
    "typescript": "ts", "ts": "ts", "tsx": "tsx", "jsx": "jsx",
    "bash": "sh", "sh": "sh", "shell": "sh", "zsh": "sh",
    "json": "json", "yaml": "yml", "yml": "yml", "toml": "toml",
    "html": "html", "css": "css", "sql": "sql", "go": "go", "rust": "rs",
    "java": "java", "c": "c", "cpp": "cpp", "c++": "cpp", "csharp": "cs",
    "ruby": "rb", "php": "php", "swift": "swift", "kotlin": "kt", "r": "r",
    "markdown": "md", "md": "md", "dockerfile": "Dockerfile", "ini": "ini",
}


def _slug(text: str, n: int = 60) -> str:
    text = (text or "").strip().replace("\n", " ")
    text = re.sub(r"[^\w \-]", "", text, flags=re.UNICODE)
    text = re.sub(r"\s+", " ", text).strip()
    return (text[:n].strip() or "chat")


def _load_vault_map() -> dict:
    try:
        with open(VAULTS_MAP_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, dict) else {}
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}


def resolve_vault(owner: str | None, uprefs: dict | None = None) -> str | None:
    """Return the absolute vault path for `owner`, or None if not configured.

    Resolution order: per-user pref -> data/obsidian_vaults.json[owner] ->
    PAIOS_OBSIDIAN_VAULT env (single-user fallback). The path must exist and be
    a directory; otherwise we warn once and no-op.
    """
    candidate = None
    if uprefs and uprefs.get("obsidian_vault"):
        candidate = uprefs.get("obsidian_vault")
    if not candidate and owner:
        candidate = _load_vault_map().get(owner)
    if not candidate:
        candidate = os.getenv("PAIOS_OBSIDIAN_VAULT") or None
    if not candidate:
        return None
    path = os.path.realpath(os.path.expanduser(candidate))
    if not os.path.isdir(path):
        logger.warning("[obsidian-brain] vault for owner=%s not found: %s", owner, path)
        return None
    return path


def _session_note_path(chats_dir: str, sess) -> tuple[str, bool]:
    """Locate this session's note (stable across renames), or build a new path.

    Returns (path, is_new). Existing notes are matched by the session-id suffix
    so an auto-rename of the chat title doesn't orphan the file.
    """
    sid8 = (getattr(sess, "id", "") or "")[:8] or "session"
    existing = glob.glob(os.path.join(chats_dir, f"*{sid8}.md"))
    if existing:
        return existing[0], False
    date = datetime.now().strftime("%Y-%m-%d")
    name = _slug(getattr(sess, "name", None) or "Chat")
    return os.path.join(chats_dir, f"{date} - {name} - {sid8}.md"), True


def _yaml_escape(s: str) -> str:
    return (s or "").replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ").strip()


def _save_outputs(outputs_dir: str, sid8: str, reply: str) -> list[str]:
    """Extract fenced code blocks to standalone files; return relative links."""
    links: list[str] = []
    blocks = _CODE_BLOCK_RE.findall(reply or "")
    if not blocks:
        return links
    os.makedirs(outputs_dir, exist_ok=True)
    stamp = datetime.now().strftime("%H%M%S")
    for i, (lang, code) in enumerate(blocks, 1):
        code = code.strip("\n")
        if len(code) < 12:  # skip trivial inline snippets
            continue
        ext = _EXT_BY_LANG.get((lang or "").strip().lower(), "txt")
        fname = f"{sid8}-{stamp}-{i}.{ext}"
        try:
            with open(os.path.join(outputs_dir, fname), "w", encoding="utf-8") as f:
                f.write(code + "\n")
            links.append(f"{OUTPUTS_SUBDIR}/{fname}")
        except OSError as e:
            logger.warning("[obsidian-brain] could not save output %s: %s", fname, e)
    return links


def record_turn(
    owner: str | None,
    sess,
    user_message: str,
    assistant_reply: str,
    uprefs: dict | None = None,
    sources: list | None = None,
) -> str | None:
    """Append one chat turn to the owner's vault note. Safe no-op if unconfigured.

    Returns the note path on success, else None. Never raises — callers treat
    this as best-effort.
    """
    try:
        if not (user_message or assistant_reply):
            return None
        vault = resolve_vault(owner, uprefs)
        if not vault:
            return None

        chats_dir = os.path.join(vault, BRAIN_SUBDIR, CHATS_SUBDIR)
        outputs_dir = os.path.join(vault, BRAIN_SUBDIR, OUTPUTS_SUBDIR)
        os.makedirs(chats_dir, exist_ok=True)

        note_path, is_new = _session_note_path(chats_dir, sess)
        sid8 = (getattr(sess, "id", "") or "")[:8] or "session"
        now = datetime.now()
        model = getattr(sess, "model", "") or "?"

        parts: list[str] = []
        if is_new:
            title = getattr(sess, "name", None) or "PiAOS chat"
            summary = _yaml_escape((user_message or "").strip())[:200]
            parts.append(
                "---\n"
                f'title: "{_yaml_escape(title)}"\n'
                f"created: {now.isoformat(timespec='seconds')}\n"
                "source: PiAOS\n"
                f'model: "{_yaml_escape(model)}"\n'
                f"session_id: {getattr(sess, 'id', '')}\n"
                f'owner: "{_yaml_escape(owner or "")}"\n'
                "tags: [paios, chat, brain]\n"
                f'summary: "{summary}"\n'
                "---\n\n"
                f"# {title}\n\n"
                "> Auto-saved by PiAOS. Every turn is appended here so "
                "your knowledge accumulates and PAIOS can recall it later.\n\n"
            )

        ts = now.strftime("%Y-%m-%d %H:%M")
        if user_message:
            parts.append(f"## 🧑 You — {ts}\n\n{user_message.strip()}\n\n")
        if assistant_reply:
            parts.append(f"## 🤖 PiAOS ({model})\n\n{assistant_reply.strip()}\n\n")

        output_links = _save_outputs(outputs_dir, sid8, assistant_reply or "")
        if output_links:
            parts.append("**Saved outputs:** " + ", ".join(f"[[{l}]]" for l in output_links) + "\n\n")

        if sources:
            srcs = []
            for s in sources:
                if isinstance(s, dict):
                    srcs.append(str(s.get("filename") or s.get("title") or s.get("url") or s))
                else:
                    srcs.append(str(s))
            if srcs:
                parts.append("> Sources: " + "; ".join(srcs[:8]) + "\n\n")

        parts.append("---\n\n")

        with open(note_path, "a", encoding="utf-8") as f:
            f.write("".join(parts))

        logger.info("[obsidian-brain] saved turn -> %s", note_path)
        return note_path
    except Exception as e:  # best-effort; never break the chat
        logger.warning("[obsidian-brain] record_turn failed: %s", e)
        return None
