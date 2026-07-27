"""
src/ms_graph.py — Microsoft 365 / Outlook connector via Microsoft Graph + OAuth2.

Modern, durable replacement for IMAP/SMTP basic auth (which Microsoft has
disabled for most work tenants). Uses the OAuth2 **Authorization Code flow with
PKCE** as a *public client* — so NO client secret is needed (ideal for a local
self-hosted app). Tokens are stored encrypted; access tokens auto-refresh.

Azure app registration (one-time, done by the user/admin):
  - Platform: "Mobile and desktop applications" (public client)
  - Redirect URI: http://localhost:7860/api/email/oauth/ms/callback
  - Delegated API permissions (Microsoft Graph):
      offline_access, User.Read, Mail.ReadWrite, Mail.Send
  - Copy the Application (client) ID  →  paste into Pi (Connectors → Outlook).

Only standard-library + requests are used here; no Azure SDK dependency.
"""
from __future__ import annotations

import base64
import hashlib
import logging
import secrets
import time
from typing import Any, Callable, Optional

import requests

logger = logging.getLogger(__name__)

GRAPH = "https://graph.microsoft.com/v1.0"
# Delegated scopes. offline_access => refresh token; the rest => read/send mail.
SCOPES = ["offline_access", "openid", "profile", "User.Read", "Mail.ReadWrite", "Mail.Send"]
DEFAULT_TENANT = "common"  # or "organizations", or a specific tenant GUID/domain
REDIRECT_PATH = "/api/email/oauth/ms/callback"


# ───────────────────────── OAuth2 (Auth Code + PKCE) ─────────────────────────

def _authority(tenant: str) -> str:
    return f"https://login.microsoftonline.com/{tenant or DEFAULT_TENANT}/oauth2/v2.0"


def make_pkce() -> tuple[str, str]:
    """Return (code_verifier, code_challenge) for a PKCE exchange (S256)."""
    verifier = base64.urlsafe_b64encode(secrets.token_bytes(48)).rstrip(b"=").decode("ascii")
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return verifier, challenge


def build_authorize_url(client_id: str, redirect_uri: str, state: str,
                        code_challenge: str, tenant: str = DEFAULT_TENANT,
                        login_hint: str = "") -> str:
    from urllib.parse import urlencode
    params = {
        "client_id": client_id,
        "response_type": "code",
        "redirect_uri": redirect_uri,
        "response_mode": "query",
        "scope": " ".join(SCOPES),
        "state": state,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
        "prompt": "select_account",
    }
    if login_hint:
        params["login_hint"] = login_hint
    return f"{_authority(tenant)}/authorize?{urlencode(params)}"


def exchange_code(client_id: str, redirect_uri: str, code: str, code_verifier: str,
                  tenant: str = DEFAULT_TENANT, timeout: int = 30) -> dict:
    """Exchange an authorization code for tokens. Returns the token dict
    (access_token, refresh_token, expires_in, …) or raises."""
    data = {
        "client_id": client_id,
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": redirect_uri,
        "code_verifier": code_verifier,
        "scope": " ".join(SCOPES),
    }
    r = requests.post(f"{_authority(tenant)}/token", data=data, timeout=timeout)
    if r.status_code != 200:
        raise RuntimeError(f"Token exchange failed ({r.status_code}): {r.text[:300]}")
    return _stamp_expiry(r.json())


def refresh_tokens(client_id: str, refresh_token: str, tenant: str = DEFAULT_TENANT,
                   timeout: int = 30) -> dict:
    """Use a refresh token to get a fresh access token. Returns a token dict.
    Microsoft rotates refresh tokens, so persist the new refresh_token too."""
    data = {
        "client_id": client_id,
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        "scope": " ".join(SCOPES),
    }
    r = requests.post(f"{_authority(tenant)}/token", data=data, timeout=timeout)
    if r.status_code != 200:
        raise RuntimeError(f"Token refresh failed ({r.status_code}): {r.text[:300]}")
    return _stamp_expiry(r.json())


def _stamp_expiry(tok: dict) -> dict:
    # absolute expiry timestamp (60s safety margin) so callers can check cheaply
    tok["expires_at"] = int(time.time()) + int(tok.get("expires_in", 3600)) - 60
    return tok


# ───────────────────────────── Graph mail client ─────────────────────────────

class GraphMailClient:
    """Thin Microsoft Graph mail client with automatic token refresh.

    `token_provider()` must return a valid access token string (refreshing if
    needed). For one-off use, pass a static token.
    """

    def __init__(self, token_provider: Callable[[], str] | str, timeout: int = 30):
        if isinstance(token_provider, str):
            tok = token_provider
            token_provider = lambda: tok  # noqa: E731
        self._token = token_provider
        self.timeout = timeout

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self._token()}", "Content-Type": "application/json"}

    def _get(self, path: str, params: Optional[dict] = None) -> dict:
        r = requests.get(f"{GRAPH}{path}", headers=self._headers(), params=params, timeout=self.timeout)
        r.raise_for_status()
        return r.json()

    def _post(self, path: str, json: Optional[dict] = None) -> Any:
        r = requests.post(f"{GRAPH}{path}", headers=self._headers(), json=json, timeout=self.timeout)
        if r.status_code not in (200, 201, 202, 204):
            raise RuntimeError(f"Graph POST {path} failed ({r.status_code}): {r.text[:300]}")
        return r.json() if r.content and r.headers.get("content-type", "").startswith("application/json") else {}

    # --- identity ---
    def me(self) -> dict:
        return self._get("/me", params={"$select": "displayName,mail,userPrincipalName"})

    # --- read ---
    def list_messages(self, folder: str = "inbox", top: int = 25, unread_only: bool = False,
                      select: str = "id,subject,from,receivedDateTime,bodyPreview,isRead,conversationId,internetMessageId") -> list[dict]:
        params = {"$top": str(top), "$orderby": "receivedDateTime desc", "$select": select}
        if unread_only:
            params["$filter"] = "isRead eq false"
        return self._get(f"/me/mailFolders/{folder}/messages", params=params).get("value", [])

    def get_message(self, message_id: str) -> dict:
        return self._get(f"/me/messages/{message_id}",
                         params={"$select": "id,subject,from,toRecipients,ccRecipients,"
                                            "receivedDateTime,body,bodyPreview,isRead,"
                                            "conversationId,internetMessageId"})

    def mark_read(self, message_id: str, read: bool = True) -> None:
        r = requests.patch(f"{GRAPH}/me/messages/{message_id}", headers=self._headers(),
                           json={"isRead": read}, timeout=self.timeout)
        r.raise_for_status()

    # --- send / reply / draft (Graph creates the draft; we never auto-send unless told) ---
    @staticmethod
    def _to_recips(addresses: list[str]) -> list[dict]:
        return [{"emailAddress": {"address": a.strip()}} for a in addresses if a and a.strip()]

    def send_mail(self, to: list[str], subject: str, body_text: str,
                  cc: Optional[list[str]] = None, save_to_sent: bool = True) -> None:
        msg = {
            "message": {
                "subject": subject,
                "body": {"contentType": "Text", "content": body_text},
                "toRecipients": self._to_recips(to),
                "ccRecipients": self._to_recips(cc or []),
            },
            "saveToSentItems": save_to_sent,
        }
        self._post("/me/sendMail", json=msg)

    def reply(self, message_id: str, comment: str, reply_all: bool = False) -> None:
        """Send a reply to an existing message (keeps threading)."""
        path = f"/me/messages/{message_id}/{'replyAll' if reply_all else 'reply'}"
        self._post(path, json={"comment": comment})

    def create_reply_draft(self, message_id: str, comment: str = "", reply_all: bool = False) -> dict:
        """Create (but do NOT send) a reply draft — for human-in-the-loop review."""
        path = f"/me/messages/{message_id}/{'createReplyAll' if reply_all else 'createReply'}"
        draft = self._post(path, json=({"comment": comment} if comment else {}))
        return draft


__all__ = [
    "GRAPH", "SCOPES", "DEFAULT_TENANT", "REDIRECT_PATH",
    "make_pkce", "build_authorize_url", "exchange_code", "refresh_tokens",
    "GraphMailClient",
]
