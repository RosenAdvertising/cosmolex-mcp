#!/usr/bin/env python3
"""Small CI-friendly guard for the repository's MCP protocol target."""

from __future__ import annotations

import argparse

from mcp.types import LATEST_PROTOCOL_VERSION


EXPECTED_MCP_PROTOCOL_VERSION = "2026-07-28"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--mcp-only",
        action="store_true",
        help="Accepted for parity with fleet spec guards.",
    )
    parser.parse_args()

    if LATEST_PROTOCOL_VERSION != EXPECTED_MCP_PROTOCOL_VERSION:
        print(
            "Spec check: FAIL — expected MCP "
            f"{EXPECTED_MCP_PROTOCOL_VERSION}, got {LATEST_PROTOCOL_VERSION}"
        )
        return 1
    print(f"Spec check: PASS — MCP {EXPECTED_MCP_PROTOCOL_VERSION}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
