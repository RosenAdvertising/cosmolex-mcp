#!/usr/bin/env python3
"""Allow ``python -m cosmolex_mcp.setup`` to run the OAuth setup wizard."""

from cosmolex_mcp.setup.oauth_flow import main

if __name__ == "__main__":
    main()
