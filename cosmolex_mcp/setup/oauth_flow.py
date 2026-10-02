#!/usr/bin/env python3
"""One-time OAuth setup with state-bound redirect validation.

Read credentials from prompts/environment; authorization responses never use argv.
"""

import getpass
import os
import sys

from cosmolex_mcp import credentials
from cosmolex_mcp.oauth_callback import LoopbackCallback, new_state, validate_redirect
from cosmolex_mcp.client import (
    DEFAULT_REDIRECT_URI,
    OAUTH_BASE,
    SafeToolFailure,
    build_authorize_url,
    exchange_code,
)


def _capture(name: str, prompt: str, secret: bool = False) -> str:
    val = os.environ.get(name, "").strip()
    if val:
        return val
    try:
        val = (getpass.getpass(prompt) if secret else input(prompt)).strip()
    except EOFError:
        return ""
    return val


def main():
    if any(arg == "--code" or arg.startswith("--code=") for arg in sys.argv[1:]):
        print("Error: authorization codes are not accepted in command-line arguments.")
        sys.exit(1)
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

    try:
        validate_redirect(redirect_uri)
    except ValueError as exc:
        print(f"Error: {exc}")
        sys.exit(1)

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

    state = new_state()
    try:
        with LoopbackCallback(redirect_uri, state) as callback:
            auth_url = build_authorize_url(redirect_uri, client_id, state)
            print("Register this exact redirect URI with the vendor:", redirect_uri)
            print("Open this URL in your browser and approve the app:")
            print(auth_url)
            code = callback.receive()
    except (OSError, ValueError):
        print(
            "Error: could not receive a valid OAuth callback. Check the registered redirect and restart setup."
        )
        sys.exit(1)

    try:
        tokens = exchange_code(code, redirect_uri, client_id, client_secret)
    except SafeToolFailure as e:
        print(f"\n✗ Authorization failed: {e}")
        print("Re-run cosmolex-mcp-setup and try a fresh code (codes are single-use).")
        sys.exit(1)
    except Exception:  # noqa: BLE001
        print("\n✗ Authorization failed due to an unexpected local error.")
        print("Check the setup configuration and try again.")
        sys.exit(1)

    print("\n✓ Authorized — access + refresh tokens saved (chmod 600).")
    if tokens.get("firm_id"):
        print(f"  Firm: {tokens['firm_id']}   User: {tokens.get('user_name', '?')}")
    print(
        "Restart the MCP server, then run 'cosmolex-mcp-verify' to test the connection."
    )


if __name__ == "__main__":
    main()
