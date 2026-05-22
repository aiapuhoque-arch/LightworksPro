"""
Grant admin consent for Lightworks Pro's Microsoft 365 permissions.

Run this script ONCE when People.Read (contact search) is not working.

What it does
------------
1. Reads your Azure App Client ID from %APPDATA%\\LightworksPro\\config.json.
2. Opens your browser to the Microsoft admin-consent page for your app.
3. Clears the stored sign-in token so Lightworks Pro re-authenticates on
   the next launch and picks up the newly approved permissions.

Who needs to run it
-------------------
- Personal / family Microsoft accounts  : You can consent yourself (step 2).
- Work / school accounts (Microsoft 365): Your IT admin must complete step 2.
  You can still run the script to prepare, then share the URL with your admin.

After consent is granted
------------------------
Restart Lightworks Pro — it will sign you in again automatically and contact
search should start working within a few minutes.
"""
import json
import os
import sys
import webbrowser
from pathlib import Path

APPDATA = Path(os.environ.get("APPDATA", "~")).expanduser()
CONFIG_FILE = APPDATA / "LightworksPro" / "config.json"
CACHE_GLOB  = "msal_cache_*.bin"


def _load_config() -> dict:
    if not CONFIG_FILE.exists():
        print(
            "ERROR: Config file not found.\n"
            f"Expected: {CONFIG_FILE}\n"
            "Launch Lightworks Pro once to create it, then re-run this script."
        )
        sys.exit(1)
    with open(CONFIG_FILE, encoding="utf-8") as f:
        return json.load(f)


def _clear_token_cache(config_dir: Path) -> None:
    cleared = 0
    for cache_file in config_dir.glob(CACHE_GLOB):
        try:
            cache_file.unlink()
            cleared += 1
        except Exception as e:
            print(f"  Warning: could not delete {cache_file.name}: {e}")
    if cleared:
        print(f"  Cleared {cleared} cached token file(s) — Lightworks Pro will sign in fresh.")
    else:
        print("  No cached token files found (that is fine).")


def main() -> None:
    config = _load_config()

    client_id = config.get("microsoft_client_id", "").strip()
    if not client_id:
        print(
            "ERROR: No Microsoft Client ID found in config.\n"
            "Run  scripts\\set_microsoft_client_id.py  first."
        )
        sys.exit(1)

    tenant_id = config.get("microsoft_tenant_id", "common").strip() or "common"

    # The redirect_uri MUST match a value registered on the app registration.
    # Using the well-known MSAL native-client URI avoids the
    # "This is not the right page" error after clicking Accept.
    # (That error means the consent succeeded but the redirect had nowhere valid
    # to land — the fix is this redirect_uri parameter.)
    redirect_uri = "https://login.microsoftonline.com/common/oauth2/nativeclient"
    consent_url = (
        f"https://login.microsoftonline.com/{tenant_id}"
        f"/adminconsent?client_id={client_id}"
        f"&redirect_uri={redirect_uri}"
    )

    print("=" * 60)
    print("Lightworks Pro — Grant Admin Consent")
    print("=" * 60)
    print()
    print("App Client ID :", client_id)
    print("Tenant        :", tenant_id)
    print()
    print("Opening your browser to the Microsoft consent page.")
    print("Sign in with an admin account and click 'Accept'.")
    print()
    print("NOTE: After clicking Accept you may see a blank white page or")
    print("a page that says 'This is not the right page'. That is normal")
    print("and means the consent WAS granted successfully. Close the tab")
    print("and press Enter below to continue.")
    print()
    print("If your browser does not open, visit this URL manually:")
    print()
    print(f"  {consent_url}")
    print()

    try:
        webbrowser.open(consent_url)
    except Exception as e:
        print(f"Could not open browser automatically: {e}")

    input("Press Enter after consent has been granted (or to skip and just clear the cache)...")

    print()
    print("Clearing stored sign-in token...")
    config_dir = CONFIG_FILE.parent
    _clear_token_cache(config_dir)

    print()
    print("Done. Restart Lightworks Pro — it will sign you in again.")
    print(
        "After sign-in, say a voice command like 'call John' to test contact search."
    )


if __name__ == "__main__":
    main()
