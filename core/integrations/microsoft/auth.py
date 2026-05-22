"""
Microsoft OAuth 2.0 via MSAL — device-code flow suitable for headless/VUI apps.
Tokens are stored in a DPAPI-encrypted file in %APPDATA%\\LightworksPro\\.
No passwords are ever stored.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Optional

import msal

log = logging.getLogger(__name__)

SCOPES = [
    "Calendars.Read",
    "Mail.Read",
    "Mail.Send",
    "MailboxSettings.Read",
    "Presence.ReadWrite",
    "Chat.Read",               # Teams chat messages
    "Notes.ReadWrite",         # OneNote dictation
    "People.Read",             # contact lookup via /me/people
    "Contacts.Read",           # personal Outlook contacts book
    "User.ReadBasic.All",      # org directory search via /users (fallback when People.Read not consented)
    "Tasks.ReadWrite",         # Microsoft To Do
    "Sites.Read.All",          # SharePoint staff directory (staff_directory.xlsx)
]


class MicrosoftAuth:
    def __init__(self, client_id: str, tenant_id: str = "common") -> None:
        self._client_id = client_id
        self._tenant_id = tenant_id
        self._cache = msal.SerializableTokenCache()
        self._load_cache()
        self._app = msal.PublicClientApplication(
            client_id=client_id,
            authority=f"https://login.microsoftonline.com/{tenant_id}",
            token_cache=self._cache,
            validate_authority=False,  # skip tenant-discovery HTTP round-trip (well-known authority)
        )

    def needs_sign_in(self) -> bool:
        """True if there is no valid cached token and interactive sign-in is required."""
        accounts = self._app.get_accounts()
        if not accounts:
            return True
        result = self._app.acquire_token_silent(SCOPES, account=accounts[0])
        return not (result and "access_token" in result)

    def get_admin_consent_url(self) -> str:
        """
        Return the Azure admin-consent URL for this app registration.
        An IT admin must visit this URL (or a tenant admin can grant it in the Azure portal)
        to allow delegated permissions like People.Read for all users in the org.

        The redirect_uri must match a value registered on the app.
        We use the well-known MSAL native-client URI so the post-consent
        redirect lands on a blank Microsoft page rather than showing
        "This is not the right page".
        """
        redirect = "https://login.microsoftonline.com/common/oauth2/nativeclient"
        return (
            f"https://login.microsoftonline.com/{self._tenant_id}"
            f"/adminconsent?client_id={self._client_id}"
            f"&redirect_uri={redirect}"
        )

    def clear_cache(self) -> None:
        """
        Wipe the in-memory and on-disk token cache.
        Call this after admin consent is granted so the next get_token() triggers
        a fresh device-code sign-in that picks up the newly approved scopes.
        """
        try:
            self._cache.deserialize("{}")
        except Exception:
            pass
        try:
            self._cache_path().unlink(missing_ok=True)
        except Exception as e:
            log.warning("Could not delete token cache file: %s", e)

    def begin_device_flow(self) -> tuple[str, dict]:
        """
        Start a device-code flow.
        Returns (spoken_instructions, flow_state).
        Pass flow_state to complete_device_flow() after the user authenticates.
        """
        flow = self._app.initiate_device_flow(SCOPES)
        if "user_code" not in flow:
            raise RuntimeError(f"Device flow failed: {flow.get('error_description')}")
        code = " ".join(list(flow["user_code"]))
        spoken = (
            "Microsoft 365 sign-in required. "
            f"Enter the code: {code}. "
            "I will wait up to 15 minutes for you to sign in."
        )
        log.info("DEVICE FLOW: %s", flow["message"])
        return spoken, flow

    def complete_device_flow(self, flow: dict) -> None:
        """Block (call from a thread-pool executor) until sign-in completes."""
        result = self._app.acquire_token_by_device_flow(flow)
        if "access_token" not in result:
            raise RuntimeError(f"Auth failed: {result.get('error_description', result)}")
        try:
            self._save_cache()
        except Exception:
            log.warning("Token obtained but cache save failed — will re-sign-in next launch")
        log.info("Microsoft 365 sign-in complete")

    def get_token(self) -> str:
        """Return a valid access token, refreshing silently. Raises if not signed in."""
        accounts = self._app.get_accounts()
        if accounts:
            result = self._app.acquire_token_silent(SCOPES, account=accounts[0])
            if result and "access_token" in result:
                self._save_cache()
                return result["access_token"]
        raise RuntimeError(
            "No cached token. Call begin_device_flow / complete_device_flow first."
        )

    # ------------------------------------------------------------------
    # Token cache persistence — DPAPI-encrypted file on Windows
    # ------------------------------------------------------------------

    def _cache_path(self) -> Path:
        # Store alongside config in %APPDATA%\LightworksPro\
        base = Path(os.environ.get("APPDATA", "~")) / "LightworksPro"
        base.mkdir(parents=True, exist_ok=True)
        # One cache file per client_id (first 8 chars avoids overly long names)
        return base / f"msal_cache_{self._client_id[:8]}.bin"

    def _load_cache(self) -> None:
        path = self._cache_path()
        if not path.exists():
            return
        try:
            import win32crypt
            encrypted = path.read_bytes()
            _, plaintext = win32crypt.CryptUnprotectData(encrypted, None, None, None, 0)
            self._cache.deserialize(plaintext.decode("utf-8"))
        except Exception as e:
            log.warning("Could not load token cache (%s) — will re-authenticate", e)

    def _save_cache(self) -> None:
        path = self._cache_path()
        try:
            import win32crypt
            plaintext = self._cache.serialize().encode("utf-8")
            encrypted = win32crypt.CryptProtectData(plaintext, None, None, None, None, 0)
            path.write_bytes(bytes(encrypted))
        except Exception as e:
            log.warning("Could not save token cache (%s)", e)
