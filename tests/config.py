from pathlib import Path

from mcp_test_kit.config import ResilienceConfig, SpecCheckConfig, ToolkitConfig

from cosmolex_mcp.server import mcp

_TESTS_DIR = Path(__file__).parent

TOOLKIT = ToolkitConfig(
    mcp_server=mcp,
    spec_check=SpecCheckConfig(
        endpoints_path=_TESTS_DIR.parent / "endpoints.yaml",
        openapi_path=_TESTS_DIR.parent
        / "endpoints.yaml",  # dummy — contract tier skipped
    ),
    source_path=_TESTS_DIR.parent / "cosmolex_mcp",
    module_path="cosmolex_mcp",
    server_path=_TESTS_DIR.parent / "cosmolex_mcp" / "server.py",
    resilience=ResilienceConfig(tools_to_timeout_test=["list_clients"]),
    skip_tiers={
        "contract": "endpoints.yaml is a tool inventory, not an OpenAPI doc — contract tier needs OpenAPI 3.x",
        "smoke": "requires live OAuth credentials (run cosmolex-mcp-setup: API key + client_id/secret + one-time consent)",
    },
)
