#!/usr/bin/env python3
"""Verify cosmolex-mcp credentials against the live NextGen /api/v2 API.

Constructs an ``LCSClient`` (which runs the username/password session login and
attaches the ``a_t`` cookie) and issues one lightweight authenticated read to
confirm the credentials work end to end.
"""

import json
import sys

from cosmolex_mcp.client import LCSClient


def main() -> None:
    print("Verifying cosmolex-mcp credentials...")
    try:
        client = LCSClient()
        # A lightweight authenticated read confirms the session login + a_t
        # cookie resolved correctly. /api/v2/user is always populated (the
        # logged-in user), so it is a reliable non-empty smoke read.
        user = client.list_users(page=1, page_size=1)
        print("✓ Authenticated — CosmoLex NextGen /api/v2 API reachable")
        print()
        print(json.dumps(user, indent=2))
    except Exception as e:  # noqa: BLE001 - surface any failure to the user
        print(f"✗ Verification failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
