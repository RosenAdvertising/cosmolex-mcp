#!/usr/bin/env python3
"""Setup wizard for cosmolex-mcp — NextGen session-login credentials.

NextGen CosmoLex accounts authenticate with a browser-style session login:
a username + password password-grant against ``/api/ext/auth/token`` (using the
shared public login client), whose token is sent as the ``a_t`` cookie on the
``/api/v2`` data calls. There is NO API key or OAuth app to register for the
working data path — just the CosmoLex login you use in the web app.

This wizard captures the username + password (and an optional host override) and
stores them via the OS keyring (chmod-0600 ``.env`` file fallback). Run
``cosmolex-mcp-verify`` afterwards to test the connection.
"""

import getpass
import os
import sys

from cosmolex_mcp import credentials


def main() -> None:
    print("=== cosmolex-mcp Setup (NextGen session login) ===\n")

    # 1. Username (CosmoLex login email) ------------------------------------
    username = os.environ.get("COSMOLEX_USERNAME", "").strip()
    if not username:
        username = input("CosmoLex login username (email): ").strip()
    if not username:
        print("Error: a username is required.")
        sys.exit(1)

    # 2. Password -----------------------------------------------------------
    password = os.environ.get("COSMOLEX_PASSWORD", "").strip()
    if not password:
        # getpass keeps the password off the terminal echo and shell history.
        password = getpass.getpass("CosmoLex login password: ").strip()
    if not password:
        print("Error: a password is required.")
        sys.exit(1)

    # 3. Base URL (optional; defaults to the production host) ---------------
    print(
        "\nHost override (optional). Leave blank for the default production host\n"
        "https://app.cosmolex.com. Use https://sandbox.cosmolex.com for the\n"
        "sandbox/trial account.\n"
    )
    base_url = os.environ.get("COSMOLEX_BASE_URL", "").strip()
    if not base_url:
        base_url = input("CosmoLex base URL [https://app.cosmolex.com]: ").strip()

    # 4. Persist via the pluggable store ------------------------------------
    backend = credentials.set_secret("COSMOLEX_USERNAME", username)
    credentials.set_secret("COSMOLEX_PASSWORD", password)
    if base_url:
        credentials.set_secret("COSMOLEX_BASE_URL", base_url)
    # Remove any stale credentials from the dead ApiKey/OAuth/token model so the
    # session-login path is unambiguous.
    for stale in ("COSMOLEX_API_KEY", "COSMOLEX_USER_TOKEN"):
        credentials.delete_secret(stale)

    if backend == "keyring":
        print(
            f"\n✓ Credentials saved to the OS keyring ({credentials.storage_backend()})."
        )
    else:
        print(f"\n✓ Credentials saved to {credentials.ENV_FILE} (0600).")
    print("Run 'cosmolex-mcp-verify' to test the connection.")


if __name__ == "__main__":
    main()
