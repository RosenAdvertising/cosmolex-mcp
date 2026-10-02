# MCP 2026-07-28 migration notes

This server targets MCP protocol `2026-07-28` through the Python SDK requirement
`mcp>=2.2,<3`. `uv.lock` resolves both `mcp` and `mcp-types` to `2.2.0`.
The production entry point uses stdio; the tests also exercise the SDK's
Streamable HTTP app in process. The [spec delta](SPEC-DELTA-2026-07-28.md)
maps the protocol changes to this server.

## Implementation

- `MCPServer` supplies modern discovery, request routing, protocol negotiation,
  and result metadata while retaining legacy client compatibility.
- Tool, resource, and prompt listings use the SDK's private, zero TTL cache hints.
  Tool registration order is deterministic.
- Paginated tools require `page >= 1` and `1 <= page_size <= 200`. List responses
  are capped to the requested size, including bare lists and envelope `items`.
  Each list call still makes one vendor request.
- Validation and upstream rejection paths log static reason keys without submitted
  values. The token response guard does not interpolate the response body.
- CosmoLex OAuth credentials and tokens remain downstream API state; the server
  adds no MCP session store or MCP authorization layer.

## Protocol coverage

The in-process tests cover `server/discover`, per-request protocol metadata,
`MCP-Protocol-Version` and `Mcp-Method` routing headers, `Mcp-Name` for named
operations, `resultType`, cache hints, repeated `tools/list` ordering, schema
bounds, resource errors, and supported error codes. The SDK handles modern
stateless requests and older negotiation. The server does not implement optional
sampling, elicitation, tracing, or a custom subscription publisher.

## Reproduce local checks

Create a test-only `PYTHONPATH` module that replaces
`cosmolex_mcp.credentials.load_into_environ` before importing product modules,
so local credential stores are not accessed. From the repository root, run:

```bash
TEST_SAFETY_DIR="$(mktemp -d)"
cat > "$TEST_SAFETY_DIR/sitecustomize.py" <<'PY'
import sys
import types
credentials = types.ModuleType("cosmolex_mcp.credentials")
credentials.load_into_environ = lambda _names: None
sys.modules["cosmolex_mcp.credentials"] = credentials
PY
export PYTHONPATH="$TEST_SAFETY_DIR"
uv run --offline --locked --group dev pytest -q
uv run --offline --locked --group dev python tests/spec_check.py --mcp-only
uv run --offline --locked --with ruff ruff check cosmolex_mcp/client.py cosmolex_mcp/server.py tests/spec_check.py tests/test_canary_fixes.py tests/test_spec_2026_07_28.py
uv lock --offline --check
```

These checks use fake credentials, mocked vendor responses, and an in-process
transport. They do not establish live CosmoLex API behavior, credential loading,
or deployed runtime behavior. Vendor ordering support remains unverified for
CosmoLex beyond the existing method-level API notes; no sort parameter was added.

## Error handling

Known credential, authorization, vendor-response, and transport failures are raised
as typed `ToolError` instances with sanitized client messages. Unexpected failures
remain masked by the MCP boundary. Resource reads use the SDK's resource error
handling boundary; messages and logs must not include credentials, submitted
values, vendor response text, or exception details.
