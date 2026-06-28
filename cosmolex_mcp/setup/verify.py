#!/usr/bin/env python3
"""Verify cosmolex-mcp credentials (scoped OAuth — LCS /v1 Integration API)."""

import json
import sys

from cosmolex_mcp.client import LCSClient


def main():
    print("Verifying cosmolex-mcp credentials (LCS /v1 OAuth)...")
    try:
        client = LCSClient()
        # A lightweight authenticated /v1 read confirms the OAuth token works (and
        # refreshes it first if the cached access token has expired).
        users = client.list_users(page=1, page_size=1)
        total = users.get("totalCount") if isinstance(users, dict) else "?"
        print("✓ Authenticated — ProfitSolv LCS /v1 Integration API reachable")
        print(f"  (firm users: {total})")
        print()
        print(json.dumps(users, indent=2))
    except Exception as e:  # noqa: BLE001
        print(f"✗ Verification failed: {e}")
        print("If the refresh token was revoked, re-run: cosmolex-mcp-setup")
        sys.exit(1)


if __name__ == "__main__":
    main()
