#!/usr/bin/env python3
"""Setup for cosmolex-mcp — scoped OAuth (ProfitSolv LCS /v1 Integration API).

Stores the app's API key + OAuth client_id/client_secret, then runs the one-time
authorization-code consent so the MCP gets an access_token + a long-lived
refresh_token. After this, the client refreshes its own token forever — no password
login, so it never trips CosmoLex's single-session limit or logs you out.

The CosmoLex OAuth app registers a ``https://localhost:8770/callback`` redirect.
This wizard does NOT run a local catcher, so consent uses a MANUAL copy-paste flow:
it prints the authorize URL, you open it and click Allow, then copy the ``code``
value out of the redirected address bar (the browser lands on ``localhost:8770``,
which need not be served) and paste it back here.

Non-interactive use: set COSMOLEX_API_KEY / COSMOLEX_CLIENT_ID /
COSMOLEX_CLIENT_SECRET in the environment, and pass the code via ``--code`` or
COSMOLEX_OAUTH_CODE.
"""

import getpass
import os
import sys

from cosmolex_mcp import credentials
from cosmolex_mcp.client import (
    DEFAULT_REDIRECT_URI,
    OAUTH_BASE,
    REGISTERED_REDIRECT_URI,
    build_authorize_url,
    exchange_code,
)


def _capture(name: str, prompt: str, secret: bool = False) -> str:
    val = os.environ.get(name, "").strip()
    if val:
        return val
    val = (getpass.getpass(prompt) if secret else input(prompt)).strip()
    return val


def main():
    print("=== cosmolex-mcp Setup (scoped OAuth — LCS /v1 Integration API) ===\n")
    print(f"OAuth host: {OAUTH_BASE}")
    print("You'll need your integration's API key, client ID, and client secret")
    print("(from the ProfitSolv / CosmoLex developer app).\n")

    api_key = _capture("COSMOLEX_API_KEY", "API key (X-Api-Key): ", secret=True)
    client_id = _capture("COSMOLEX_CLIENT_ID", "OAuth client ID (ci-...): ")
    client_secret = _capture(
        "COSMOLEX_CLIENT_SECRET", "OAuth client secret: ", secret=True
    )
    redirect_uri = (
        os.environ.get("COSMOLEX_REDIRECT_URI", "").strip() or DEFAULT_REDIRECT_URI
    )

    # Guard against a stale/wrong stored redirect URI. The OAuth app only accepts its
    # REGISTERED redirect, so a stored/overridden value that differs from it breaks
    # first-time consent (a bad_request at the authorize step). Compare against the hard
    # REGISTERED_REDIRECT_URI constant — NOT DEFAULT_REDIRECT_URI, which is itself
    # env-derived and would equal a wrong override, making the check dead. Warn loud.
    if redirect_uri != REGISTERED_REDIRECT_URI:
        print(
            f"\n⚠  COSMOLEX_REDIRECT_URI is set to:\n     {redirect_uri}\n"
            f"   which differs from the app's registered redirect:\n     {REGISTERED_REDIRECT_URI}\n"
            "   Consent will FAIL unless that exact URI is registered on the OAuth app.\n"
            "   Unset COSMOLEX_REDIRECT_URI to use the registered default."
        )

    if not (api_key and client_id and client_secret):
        print("Error: API key, client ID, and client secret are all required.")
        sys.exit(1)

    # Persist the app credentials (keyring, 0600 .env fallback) AND make them visible
    # to exchange_code() in this same process.
    backend = credentials.set_secret("COSMOLEX_API_KEY", api_key)
    credentials.set_secret("COSMOLEX_CLIENT_ID", client_id)
    credentials.set_secret("COSMOLEX_CLIENT_SECRET", client_secret)
    if redirect_uri != DEFAULT_REDIRECT_URI:
        credentials.set_secret("COSMOLEX_REDIRECT_URI", redirect_uri)
    os.environ["COSMOLEX_CLIENT_ID"] = client_id
    os.environ["COSMOLEX_CLIENT_SECRET"] = client_secret
    # Remove any stale credentials from the previous NextGen username/password model
    # so the OAuth path is unambiguous.
    for stale in ("COSMOLEX_USERNAME", "COSMOLEX_PASSWORD"):
        credentials.delete_secret(stale)

    if backend == "keyring":
        print(
            f"\n✓ App credentials saved to the OS keyring ({credentials.storage_backend()})."
        )
    else:
        print(f"\n✓ App credentials saved to {credentials.ENV_FILE} (0600).")

    # ── One-time consent ─────────────────────────────────────────────────────
    auth_url = build_authorize_url(redirect_uri, client_id)
    print("\n--- One-time authorization ---")
    print("1. Open this URL in your browser (logged in to CosmoLex):\n")
    print(f"   {auth_url}\n")
    print("2. Click 'Allow'. Your browser will redirect to")
    print(f"   {redirect_uri}?code=...")
    print("   (localhost:8770 need not be served — just read the address bar.)")
    print("3. Copy the value of the 'code' query parameter from the address bar.\n")

    code = os.environ.get("COSMOLEX_OAUTH_CODE", "").strip()
    for arg in sys.argv[1:]:
        if arg.startswith("--code="):
            code = arg.split("=", 1)[1].strip()
    if not code:
        code = input("Paste the authorization code here: ").strip()
    if not code:
        print("Error: no authorization code provided.")
        sys.exit(1)

    try:
        tokens = exchange_code(code, redirect_uri, client_id, client_secret)
    except Exception as e:  # noqa: BLE001
        print(f"\n✗ Authorization failed: {e}")
        print(
            "Re-run cosmolex-mcp-setup and try a fresh code (codes are single-use)."
        )
        sys.exit(1)

    print("\n✓ Authorized — access + refresh tokens saved (chmod 600).")
    if tokens.get("firm_id"):
        print(f"  Firm: {tokens['firm_id']}   User: {tokens.get('user_name', '?')}")
    print("Run 'cosmolex-mcp-verify' to test the connection.")


if __name__ == "__main__":
    main()
