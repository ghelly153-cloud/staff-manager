"""Authentication & authorisation.

* People sign in with Microsoft (OAuth 2.0 authorization-code flow with PKCE via MSAL, confidential client on the
  SERVER - secrets never reach the browser). Sign-in asks for NO file permissions.
* Access is by allow-list + role (ROLE_ADMINS / ROLE_EDITORS / ROLE_VIEWERS). Anyone else is refused.
* The workbook connection is a separate, explicit step done once by an admin ("Connect workbook"), which asks for the
  file permission. Its refresh token is stored ENCRYPTED on the server disk (Fernet) - never in the browser or git.
"""
import json
import os
import threading

import msal
from cryptography.fernet import Fernet, InvalidToken

from .adapters.base import WorkbookError

RANK = {"viewer": 1, "editor": 2, "admin": 3}


def role_for(settings, email):
    e = (email or "").strip().lower()
    if not e:
        return None
    if e in settings.admins:
        return "admin"
    if e in settings.editors:
        return "editor"
    if e in settings.viewers:
        return "viewer"
    return None


def authority(settings):
    return f"https://login.microsoftonline.com/{settings.tenant_id}"


def file_scopes():
    # Least privilege: Files.ReadWrite covers the signed-in user's own OneDrive.
    # Use "Files.ReadWrite.All" (set GRAPH_FILE_SCOPE) only if the workbook lives in SharePoint / is shared with the account.
    return [f"https://graph.microsoft.com/{os.getenv('GRAPH_FILE_SCOPE', 'Files.ReadWrite')}"]


class EncryptedFileCache:
    """MSAL token cache persisted encrypted at rest."""

    def __init__(self, path, key):
        self.path, self.f = path, Fernet(key.encode())
        self.cache = msal.SerializableTokenCache()
        self._lock = threading.Lock()
        if os.path.exists(path):
            try:
                self.cache.deserialize(self.f.decrypt(open(path, "rb").read()).decode())
            except (InvalidToken, ValueError):
                pass        # unreadable cache => treated as "not connected"

    def save(self):
        with self._lock:
            if self.cache.has_state_changed:
                os.makedirs(os.path.dirname(self.path), exist_ok=True)
                tmp = self.path + ".tmp"
                with open(tmp, "wb") as fh:
                    fh.write(self.f.encrypt(self.cache.serialize().encode()))
                os.chmod(tmp, 0o600)
                os.replace(tmp, self.path)


class MsalTokenProvider:
    """Supplies delegated Graph access tokens to the sync service using the stored refresh token."""

    def __init__(self, settings):
        self.s = settings
        self.store = EncryptedFileCache(os.path.join(settings.data_dir, "graph_token_cache.bin"), settings.token_encryption_key)
        self.app = msal.ConfidentialClientApplication(settings.client_id, client_credential=settings.client_secret,
                                                      authority=authority(settings), token_cache=self.store.cache)
        self._invalid = False

    def connected_account(self):
        accts = self.app.get_accounts()
        return accts[0] if accts else None

    def get_token(self):
        acct = self.connected_account()
        if not acct:
            raise WorkbookError("auth", "The workbook is not connected yet. An admin must use “Connect workbook”.")
        res = self.app.acquire_token_silent(file_scopes(), account=acct, force_refresh=self._invalid)
        self._invalid = False
        self.store.save()
        if not res or "access_token" not in res:
            raise WorkbookError("auth", "Microsoft sign-in for the workbook has expired. An admin must reconnect.")
        return res["access_token"]

    def invalidate(self):
        self._invalid = True

    def privacy_safe_account(self):
        a = self.connected_account()
        if not a:
            return None
        u = a.get("username", "")
        name, _, dom = u.partition("@")
        return f"{name[:2]}***@{dom}" if dom else "connected"


class LoginFlows:
    """Server-side initiation/completion of the auth-code (+PKCE) flow."""

    def __init__(self, settings):
        self.s = settings
        self.app = msal.ConfidentialClientApplication(settings.client_id, client_credential=settings.client_secret,
                                                      authority=authority(settings))

    def start(self, purpose, redirect_uri):
        # purpose "signin": identity only. purpose "connect": file permission, token cached for the sync service.
        scopes = file_scopes() if purpose == "connect" else []
        flow = self.app.initiate_auth_code_flow(scopes, redirect_uri=redirect_uri, prompt="select_account" if purpose == "signin" else "consent")
        flow["_purpose"] = purpose
        return flow

    def finish(self, flow, params, provider=None):
        purpose = flow.get("_purpose", "signin")
        app = self.app
        if purpose == "connect" and provider is not None:
            app = provider.app              # use the cache-backed client so the refresh token is retained
        res = app.acquire_token_by_auth_code_flow(flow, params)
        if purpose == "connect" and provider is not None:
            provider.store.save()
        return res
