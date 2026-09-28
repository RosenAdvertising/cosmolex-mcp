# MCP 2026-07-28 migration report

## Result

`cosmolex-mcp` now targets MCP `2026-07-28`, up from `2025-11-25`.
The direct Python SDK dependency changed from `mcp>=1.27.2,<2` (locked to
1.28.1) to the exact migration release `mcp==2.0.0`. The refreshed lock
includes the v2 dependency split, including `mcp-types==2.0.0`.

This was a migration, not a no-op. The pre-migration server constructed v1
`FastMCP`, had no protocol guard, and tracked no tests. The authoritative
change classification and official citations are in
[`SPEC-DELTA-2026-07-28.md`](SPEC-DELTA-2026-07-28.md).

No deployment, live firm, live account, credential store, or browser page was
touched. The server's production entry point remains stdio.

## Implementation

- Replaced the v1 `FastMCP` surface with SDK v2 `MCPServer`; tool, resource,
  prompt, and entry-point behavior remains otherwise unchanged.
- Preserved the downstream CosmoLex OAuth credential/token model. No MCP
  session state, MCP authorization layer, or new cache was introduced.
- Kept SDK v2's conservative private, zero-TTL cache hints and dual-era
  compatibility.
- Added an exact list-input contract: page numbers are at least one and page
  sizes are schema-enforced from 1 through 200 on all 15 paginated tools.
- Defensively caps both bare-list and envelope `items` responses to the requested
  `page_size`; each call still performs exactly one vendor request.
- Added PII-free reason logs to custom input, credential, upstream response,
  detail/update/delete, unavailable-capability, and transaction-scope rejection
  paths.
- Removed a token-response error interpolation that could have copied token or
  user fields into an exception surface.
- Added an explicit core Ruff policy for the declared Python 3.10 floor.

## AFFECTS-US mapping

| AFFECTS-US item | Handling | Commit |
| --- | --- | --- |
| Modern stateless requests and no session header | SDK v2 dispatcher; raw HTTP discovery asserts no `Mcp-Session-Id` | `a5482bf`; `d148833` |
| Per-request metadata and `server/discover` | Modern raw request helper and exact version/identity/capability assertions | `d148833` |
| Required `resultType` | Discovery, every list/read category, and a tool validation error assert `complete` | `d148833` |
| Modern HTTP routing headers | Raw requests send `MCP-Protocol-Version`, `Mcp-Method`, and named-operation `Mcp-Name`; missing/mismatched method/name regressions assert `-32020` | `d148833` |
| Subscription/listen-era capabilities | SDK-managed list-change/resource-subscription declarations preserved; no publisher or custom bus added | `a5482bf`; `d148833` |
| Capability extensions | Discovery proves no unused extension is advertised | `d148833` |
| Required cache hints | Tools, prompts, resources, templates, and resource reads assert `ttlMs: 0` and `cacheScope: private` | `d148833` |
| Deterministic `tools/list` | Two independent listings assert identical order and all 86 names | `d148833` |
| JSON Schema 2020-12 behavior | All tool schemas remain object schemas; paginated schemas also assert numeric bounds | `a5482bf`; `d148833` |
| Resource-not-found `-32602` | Unknown `cosmolex://` URI regression | `d148833` |
| Reserved error allocation | Header mismatch `-32020`, unsupported version `-32022`, and unknown method `-32601` asserted | `d148833` |

## Test inventory

Before migration:

- `uv run --locked --with pytest pytest -q`: **0/0 tests**; pytest exited 5
  because the repository tracked no tests.

After migration, using the locked environment:

- `uv run --locked pytest -q`: **14/14 passed**.
- `uv run --locked python tests/spec_check.py --mcp-only`: **PASS**, exact
  protocol `2026-07-28`.
- `uvx ruff check .`: **all checks passed**.
- `python -m compileall -q cosmolex_mcp tests`: **passed**.

The tests are fully offline. They cover raw modern discovery; modern and legacy
negotiation; routing headers; list/read cache metadata; deterministic tools;
resource and method errors; bounded tool schemas; vendor response caps; and
PII-free rejection logging.

## Sibling canary checks

### A. List-tool limit and order — fixed

All 15 paginated list tools previously exposed unconstrained `page` and
`page_size` integers. The client made one request (no auto-pagination), but the
bare-list documents endpoint had no defensive cap if the vendor ignored
`pageSize`. Schemas now enforce `page >= 1` and `1 <= page_size <= 200`; both
bare lists and envelope items are capped, with regression tests proving one
request and no over-return.

No `order` or `sort` parameter was added. The repository's live-verified LCS
`/v1` contract documents only pagination and the narrow filters already present;
it identifies no honored ordering parameter. Ordering is therefore
method-verified-only rather than live-retested in this credential-free migration.

### B. Silent rejections — fixed

Custom guard and validation failures now emit a PII-free reason event before
raising. Regression coverage checks list-bound, JSON-object, transaction-scope,
and token-response rejection logs without including submitted values.

### C. Origin/CSP ceremony — N/A

The production process is an stdio MCP server and serves no browser pages. The
Streamable HTTP app is constructed only by offline protocol tests, so the Clio
browser-ceremony patterns do not apply.

### D. PII in logs — fixed

No application log call emits subject, email, user name, client name, or matter
name. New reason logs contain only static reason keys, numeric HTTP status, and
static resource/capability identifiers. The token-response guard no longer
interpolates its response dict, closing the adjacent error-surface exposure.

## Judgment calls and remaining limitations

- Cache policy stays private with zero TTL; positive or shared caching would be
  a new retention/behavior choice.
- SDK-managed list-change/resource-subscription declarations remain enabled for
  dual-era fidelity. No application event publisher was invented.
- Missing-client-capability error `-32021` is not manufactured because no server
  operation requires a new optional client capability.
- No live CosmoLex call was made. Vendor ordering support and downstream API
  behavior are method-verified from the repository's existing live notes only.
- The sandbox denied writes to the repository's `.git`. Commits were created in
  the authorized alternate Git database. The verified bundle at
  `/private/tmp/claude-501/-Users-tobyrosen-Cowork-RA-Projects/7c2bbcf3-be6b-4bd4-bbc9-3870b657affb/scratchpad/fanout/cosmolex-spec-2026-07-28.bundle`
  **must be imported** into the repository; nothing was pushed.

## Branch log before this report commit

```text
d148833 test: prove MCP 2026-07-28 conformance
a5482bf feat: migrate server to MCP 2026-07-28
29fcf1b docs: document MCP 2026-07-28 delta
```

This document is committed separately as
`docs: report MCP 2026-07-28 migration`; its own hash cannot be embedded in its
contents without changing that hash. The finalized external fan-out report lists
the complete post-commit log and bundle verification result.
