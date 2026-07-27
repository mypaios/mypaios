"""Mail Guard engine — cascading email triage, local-first and cheap.

Research-backed cascade (rules → header heuristics → local LLM), because
"send everything to an LLM" both costs more and scores WORSE on borderline
cases than heuristics-first pipelines. Stages per new message:

  1. USER RULES   — include patterns ⇒ never filtered (verdict ≥ important);
                    exclude patterns ⇒ marketing. Zero AI cost.
  2. HEURISTICS   — RFC marketing signals: List-Unsubscribe header,
                    Precedence: bulk/list, campaign headers, noreply senders.
                    Calendar invites ⇒ important. Zero AI cost.
  3. LLM          — only the ambiguous remainder goes to the local generalist
                    (hermes3 via the crew router), in ONE batched call per
                    sweep, strict JSON out: urgent / important / fyi / marketing.
  4. ACTIONS      — marketing/noise ⇒ MOVE to the "Pi Filtered" folder
                    (recoverable; hard-delete to Trash only if the user opts
                    in), urgent/important ⇒ kept + reply DRAFT saved into the
                    account's real Drafts folder (never sent).

Scales to ~40 accounts because stages 1-2 resolve the bulk of mail with no
model call, and stage 3 batches; per-sweep LLM work is capped.
"""

from __future__ import annotations

import email
import email.policy
import email.utils
import json
import logging
import re
import time
from email.message import EmailMessage
from typing import Optional

from services.mailguard import store

logger = logging.getLogger("mailguard")

HEADER_FETCH = "(BODY.PEEK[HEADER])"
BODY_SNIPPET_BYTES = 6000
SNIPPET_CHARS = 900
MAX_NEW_PER_ACCOUNT = 30          # per sweep — keeps a 40-account pass bounded
MAX_DRAFTS_PER_SWEEP = 5
LOOKBACK_DAYS = 3                  # only triage recent unseen mail

_NOREPLY_RE = re.compile(r"no[-_.]?reply|newsletter|marketing|promo(?:tions)?|offers|deals|noreply", re.I)
_CAMPAIGN_HEADERS = ("x-campaign", "x-mailchimp", "x-mc-user", "x-sg-eid", "x-ses-outgoing",
                     "x-mailgun", "x-postmark", "x-sendgrid", "x-hubspot", "x-marketo")


# ── small utils ────────────────────────────────────────────────────────────

def _addr(value: str) -> str:
    try:
        return (email.utils.parseaddr(value or "")[1] or "").lower()
    except Exception:
        return (value or "").lower()


def _domain(addr: str) -> str:
    return addr.rsplit("@", 1)[-1].lower() if "@" in (addr or "") else ""


def _dec_header(msg, name: str) -> str:
    try:
        raw = msg.get(name, "") or ""
        parts = email.header.decode_header(raw)
        out = ""
        for txt, enc in parts:
            out += txt.decode(enc or "utf-8", "replace") if isinstance(txt, bytes) else str(txt)
        return out.strip()
    except Exception:
        return str(msg.get(name, "") or "")


def _extract_json_array(text: str) -> Optional[list]:
    m = re.search(r"```(?:json)?\s*(\[.*?\])\s*```", text or "", re.S)
    cands = [m.group(1)] if m else []
    start = (text or "").find("[")
    if start != -1:
        depth = 0
        for i in range(start, len(text)):
            if text[i] == "[":
                depth += 1
            elif text[i] == "]":
                depth -= 1
                if depth == 0:
                    cands.append(text[start:i + 1])
                    break
    for c in cands:
        try:
            v = json.loads(c)
            if isinstance(v, list):
                return v
        except Exception:
            continue
    return None


# ── stage 1: user rules ────────────────────────────────────────────────────

def apply_rules(sender: str, subject: str, rules: list[dict]) -> Optional[tuple[str, str]]:
    """Return (verdict, reason) when a rule decides, else None.
    Include rules win over exclude rules (safety: never filter a VIP)."""
    s_addr = _addr(sender)
    s_dom = _domain(s_addr)
    subj = (subject or "").lower()

    def _match(rule) -> bool:
        p = rule["pattern"]
        if rule["field"] == "sender":
            return p in s_addr
        if rule["field"] == "domain":
            return p in s_dom
        return p in subj  # subject

    for r in rules:
        if r["kind"] == "include" and _match(r):
            return "important", f"include rule: {r['field']}~'{r['pattern']}'"
    for r in rules:
        if r["kind"] == "exclude" and _match(r):
            return "marketing", f"exclude rule: {r['field']}~'{r['pattern']}'"
    return None


# ── stage 2: header heuristics ─────────────────────────────────────────────

def apply_heuristics(msg, sender: str) -> Optional[tuple[str, str]]:
    """RFC-level marketing signals — the strongest non-AI classifier."""
    ctype = (msg.get_content_type() or "").lower() if hasattr(msg, "get_content_type") else ""
    if "text/calendar" in ctype or msg.get("X-Microsoft-CDO-Busystatus"):
        return "important", "calendar invite"
    if msg.get("List-Unsubscribe"):
        return "marketing", "List-Unsubscribe header (bulk sender)"
    precedence = str(msg.get("Precedence", "")).lower()
    if precedence in ("bulk", "list", "junk"):
        return "marketing", f"Precedence: {precedence}"
    if msg.get("List-Id") and not msg.get("In-Reply-To"):
        return "marketing", "mailing-list broadcast (List-Id)"
    for h in _CAMPAIGN_HEADERS:
        if msg.get(h):
            return "marketing", f"campaign header {h}"
    s_addr = _addr(sender)
    if _NOREPLY_RE.search(s_addr.split("@")[0] if "@" in s_addr else s_addr):
        return "marketing", "no-reply / promotional sender address"
    return None


# ── stage 3: LLM batch classification ──────────────────────────────────────

_CLASSIFY_SYSTEM = """You triage email for a busy professional. For EACH numbered email decide ONE category:
- "urgent": needs the user's action/response today (direct asks, deadlines, boss/client escalations, failures, money/security issues addressed to the user personally).
- "important": personally relevant, should read soon (real humans writing to the user, work threads, invoices/receipts they'd keep, meeting changes).
- "fyi": legitimate but passive (notifications, reports, confirmations, social updates).
- "marketing": promotional/newsletter/sales outreach the user did not ask a person for (cold outreach counts).
Reply with ONLY a JSON array: [{"i": <number>, "v": "<category>", "r": "<reason, max 8 words>"}]. One entry per email. No prose."""


async def classify_batch(items: list[dict], owner: str) -> dict[int, tuple[str, str]]:
    """items: [{i, sender, subject, snippet, account_email}] → {i: (verdict, reason)}.
    Falls back to 'fyi' (kept, never filtered) when no model is available."""
    if not items:
        return {}
    from services.crew import router as crew_router
    from src.llm_core import llm_call_async
    from src.settings import load_settings

    url, model, headers, _meta = crew_router.supervisor_route(owner, dict(load_settings()))
    if not url or not model:
        logger.warning("mailguard: no local model available — keeping %d emails unclassified", len(items))
        return {it["i"]: ("fyi", "no model available (kept)") for it in items}

    lines = []
    for it in items:
        lines.append(
            f"--- email {it['i']} (to: {it.get('account_email','me')}) ---\n"
            f"From: {it['sender']}\nSubject: {it['subject']}\n"
            f"Body (truncated): {it['snippet'][:SNIPPET_CHARS]}")
    out = await llm_call_async(
        url, model,
        [{"role": "system", "content": _CLASSIFY_SYSTEM},
         {"role": "user", "content": "\n".join(lines)}],
        headers=headers, temperature=0.1, max_tokens=1200, timeout=120)

    parsed = _extract_json_array(out or "") or []
    verdicts: dict[int, tuple[str, str]] = {}
    for entry in parsed:
        if not isinstance(entry, dict):
            continue
        try:
            i = int(entry.get("i"))
        except (TypeError, ValueError):
            continue
        v = str(entry.get("v", "")).strip().lower()
        if v == "noise":
            v = "marketing"
        if v not in ("urgent", "important", "fyi", "marketing"):
            continue
        verdicts[i] = (v, str(entry.get("r", ""))[:120] or "llm")
    # Anything the model skipped/garbled stays in the inbox — fail SAFE.
    for it in items:
        verdicts.setdefault(it["i"], ("fyi", "unclassified (kept)"))
    return verdicts


# ── drafts ─────────────────────────────────────────────────────────────────

_DRAFT_SYSTEM = """Draft a reply the user can send with minimal editing. Rules:
- Professional, warm, concise (under 130 words). Match the language of the original.
- Answer/acknowledge what was asked; if a decision is needed, propose the most reasonable option and leave a [confirm?] marker.
- No subject line, no signature block, no placeholders like [Name] except [confirm?].
Reply with ONLY the email body text."""


async def draft_reply(sender: str, subject: str, snippet: str, owner: str) -> str:
    from services.crew import router as crew_router
    from src.llm_core import llm_call_async
    from src.settings import load_settings
    url, model, headers, _meta = crew_router.supervisor_route(owner, dict(load_settings()))
    if not url or not model:
        return ""
    try:
        out = await llm_call_async(
            url, model,
            [{"role": "system", "content": _DRAFT_SYSTEM},
             {"role": "user", "content": f"From: {sender}\nSubject: {subject}\n\n{snippet[:1500]}"}],
            headers=headers, temperature=0.4, max_tokens=400, timeout=90)
        return (out or "").strip()[:4000]
    except Exception as e:  # noqa: BLE001
        logger.warning("mailguard draft failed: %s", e)
        return ""


def save_draft_to_imap(conn, cfg: dict, original_msg, draft_body: str) -> bool:
    """Append the reply draft to the account's real Drafts folder so it shows
    up threaded in any mail client. Never sends."""
    try:
        from routes.email_helpers import _detect_drafts_folder
        drafts = _detect_drafts_folder(conn) or "Drafts"
        m = EmailMessage()
        m["From"] = cfg.get("from_address") or cfg.get("imap_user") or ""
        m["To"] = _dec_header(original_msg, "Reply-To") or _dec_header(original_msg, "From")
        subj = _dec_header(original_msg, "Subject")
        m["Subject"] = subj if subj.lower().startswith("re:") else f"Re: {subj}"
        mid = original_msg.get("Message-ID")
        if mid:
            m["In-Reply-To"] = mid
            refs = (original_msg.get("References") or "").strip()
            m["References"] = f"{refs} {mid}".strip()
        m.set_content(draft_body + "\n\n— drafted by Pi Mail Guard (review before sending)")
        conn.append(f'"{drafts}"', "\\Draft", None, m.as_bytes())
        return True
    except Exception as e:  # noqa: BLE001
        logger.warning("mailguard: could not save IMAP draft: %s", e)
        return False


# ── folder ops ─────────────────────────────────────────────────────────────

def ensure_folder(conn, name: str) -> bool:
    try:
        typ, _ = conn.select(f'"{name}"', readonly=True)
        if typ == "OK":
            conn.select("INBOX")
            return True
    except Exception:
        pass
    try:
        conn.create(f'"{name}"')
        try:
            conn.subscribe(f'"{name}"')
        except Exception:
            pass
        conn.select("INBOX")
        return True
    except Exception as e:  # noqa: BLE001
        logger.warning("mailguard: cannot create folder %r: %s", name, e)
        return False


# ── per-account sweep ──────────────────────────────────────────────────────

def _fetch_new_messages(conn, account_id: str) -> list[dict]:
    """Unseen messages from the last LOOKBACK_DAYS not yet triaged."""
    import imaplib
    conn.select("INBOX")
    since = time.strftime("%d-%b-%Y", time.localtime(time.time() - LOOKBACK_DAYS * 86400))
    typ, data = conn.uid("SEARCH", None, f"(UNSEEN SINCE {since})")
    if typ != "OK" or not data or not data[0]:
        return []
    uids = data[0].split()[-MAX_NEW_PER_ACCOUNT:]
    out = []
    for uid in uids:
        try:
            typ, hdata = conn.uid("FETCH", uid, HEADER_FETCH)
            if typ != "OK" or not hdata or not isinstance(hdata[0], tuple):
                continue
            msg = email.message_from_bytes(hdata[0][1])
            mid = (msg.get("Message-ID") or f"<no-id-{account_id}-{uid.decode()}>").strip()
            out.append({"uid": uid.decode(), "message_id": mid, "msg": msg,
                        "sender": _dec_header(msg, "From"),
                        "subject": _dec_header(msg, "Subject")})
        except (imaplib.IMAP4.error, OSError) as e:
            logger.debug("mailguard fetch uid %s failed: %s", uid, e)
    # drop already-triaged
    seen = store.seen_message_ids(account_id, [m["message_id"] for m in out])
    return [m for m in out if m["message_id"] not in seen]


def _body_snippet(conn, uid: str) -> str:
    try:
        typ, data = conn.uid("FETCH", uid, f"(BODY.PEEK[]<0.{BODY_SNIPPET_BYTES}>)")
        if typ != "OK" or not data or not isinstance(data[0], tuple):
            return ""
        msg = email.message_from_bytes(data[0][1], policy=email.policy.default)
        text = ""
        if msg.is_multipart():
            for part in msg.walk():
                if part.get_content_type() == "text/plain":
                    text = part.get_content()
                    break
            if not text:
                for part in msg.walk():
                    if part.get_content_type() == "text/html":
                        text = re.sub(r"<[^>]+>", " ", part.get_content())
                        break
        else:
            text = msg.get_content() if msg.get_content_type() == "text/plain" \
                else re.sub(r"<[^>]+>", " ", str(msg.get_payload()))
        return re.sub(r"\s+", " ", str(text)).strip()[:SNIPPET_CHARS * 2]
    except Exception:
        return ""


async def sweep_account(cfg: dict, owner: str, rules: list[dict], settings: dict,
                        drafts_remaining: list[int]) -> dict:
    """Triage one account. Returns a summary dict. Failures isolate per-account."""
    from routes.email_helpers import _imap
    from routes.email_routes import _move_email_message

    account_id = cfg.get("account_id") or "legacy"
    account_email = cfg.get("from_address") or cfg.get("imap_user") or ""
    filtered_folder = settings.get("mailguard_filtered_folder") or "Pi Filtered"
    hard_delete = bool(settings.get("mailguard_hard_delete"))
    want_drafts = bool(settings.get("mailguard_draft_replies", True))

    summary = {"account": account_email, "new": 0, "filed": 0,
               "urgent": 0, "important": 0, "fyi": 0, "drafts": 0, "error": ""}
    try:
        with _imap(account_id=account_id, owner=owner) as conn:
            new_msgs = _fetch_new_messages(conn, account_id)
            summary["new"] = len(new_msgs)
            if not new_msgs:
                store.touch_account(account_id)
                return summary

            decided: list[dict] = []
            ambiguous: list[dict] = []
            for i, m in enumerate(new_msgs):
                hit = apply_rules(m["sender"], m["subject"], rules)
                stage = "rule"
                if not hit:
                    hit = apply_heuristics(m["msg"], m["sender"])
                    stage = "heuristic"
                if hit:
                    decided.append({**m, "verdict": hit[0], "reason": hit[1], "stage": stage})
                else:
                    snippet = _body_snippet(conn, m["uid"])
                    ambiguous.append({**m, "i": i, "snippet": snippet,
                                      "account_email": account_email})

            if ambiguous:
                verdicts = await classify_batch(
                    [{"i": a["i"], "sender": a["sender"], "subject": a["subject"],
                      "snippet": a["snippet"], "account_email": account_email}
                     for a in ambiguous], owner)
                for a in ambiguous:
                    v, r = verdicts.get(a["i"], ("fyi", "unclassified (kept)"))
                    decided.append({**a, "verdict": v, "reason": r, "stage": "llm"})

            # actions
            ensure_ok = None
            for d in decided:
                action = "kept"
                draft_text = ""
                if d["verdict"] in ("marketing", "noise"):
                    if hard_delete:
                        ok = _move_email_message(conn, d["uid"], "Trash", role="trash")
                        action = "trashed" if ok else "kept"
                    else:
                        if ensure_ok is None:
                            ensure_ok = ensure_folder(conn, filtered_folder)
                        ok = ensure_ok and _move_email_message(conn, d["uid"], filtered_folder)
                        action = "filed" if ok else "kept"
                    if action != "kept":
                        summary["filed"] += 1
                elif d["verdict"] in ("urgent", "important"):
                    summary[d["verdict"]] += 1
                    if want_drafts and drafts_remaining[0] > 0:
                        snippet = d.get("snippet") or _body_snippet(conn, d["uid"])
                        draft_text = await draft_reply(d["sender"], d["subject"], snippet, owner)
                        if draft_text:
                            drafts_remaining[0] -= 1
                            summary["drafts"] += 1
                            save_draft_to_imap(conn, cfg, d["msg"], draft_text)
                else:
                    summary["fyi"] += 1

                store.record_decision(
                    owner=owner, account_id=account_id, account_email=account_email,
                    message_id=d["message_id"], uid=d["uid"], folder="INBOX",
                    subject=d["subject"], sender=d["sender"], verdict=d["verdict"],
                    stage=d["stage"], action=action, reason=d["reason"], draft=draft_text)

            store.touch_account(account_id, swept=len(decided))
    except Exception as e:  # noqa: BLE001
        summary["error"] = str(e)[:200]
        store.touch_account(account_id, error=str(e)[:200])
        logger.warning("mailguard sweep failed for %s: %s", account_email, e)
    return summary


async def run_sweep() -> dict:
    """Sweep every enabled account. Returns combined summary."""
    from core.database import SessionLocal, EmailAccount
    from routes.email_helpers import _list_email_accounts

    # owner per account (configs don't carry it)
    owners: dict[str, str] = {}
    try:
        db = SessionLocal()
        try:
            for row in db.query(EmailAccount).filter(EmailAccount.enabled == True).all():  # noqa: E712
                owners[row.id] = row.owner or ""
        finally:
            db.close()
    except Exception:
        pass

    from src.settings import load_settings
    settings = dict(load_settings())
    configs = [c for c in _list_email_accounts() if c.get("imap_host")]
    if not configs:
        return {"accounts": 0, "summaries": [], "note": "no email accounts configured"}

    rules_all = store.list_rules()
    drafts_remaining = [MAX_DRAFTS_PER_SWEEP]
    summaries = []
    for cfg in configs:
        owner = owners.get(cfg.get("account_id") or "", "") or "admin"
        summaries.append(await sweep_account(cfg, owner, rules_all, settings, drafts_remaining))
    totals = {k: sum(s[k] for s in summaries) for k in ("new", "filed", "urgent", "important", "fyi", "drafts")}
    return {"accounts": len(configs), "totals": totals, "summaries": summaries}
