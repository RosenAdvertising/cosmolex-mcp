# MCP specification delta: 2025-11-25 to 2026-07-28

Research date: 2026-08-09. Sources are limited to the official MCP
specification and official MCP Python SDK documentation.

## Current target and migration release

This repository currently targets MCP `2025-11-25`:

- `pyproject.toml` declares `mcp>=1.27.2,<2`, and `uv.lock` resolves MCP Python
  SDK 1.28.1. The v1 SDK line defaults to protocol `2025-11-25`.
- `cosmolex_mcp/server.py` constructs v1 `FastMCP` and calls `mcp.run()` with
  its default stdio transport. It does not override protocol negotiation.
- The repository has no tracked test suite or protocol-version guard.

The official changelog says `2026-07-28` follows `2025-11-25`
([spec changelog](https://modelcontextprotocol.io/specification/2026-07-28/changelog)).
The implementation release is MCP Python SDK `2.0.0`, which supports
`2026-07-28` and earlier revisions from one server
([SDK v2.0.0 release notes](https://github.com/modelcontextprotocol/python-sdk/releases/tag/v2.0.0)).
Required Python API changes follow the
[official v1-to-v2 migration guide](https://py.sdk.modelcontextprotocol.io/migration/).

Verdicts below mean:

- **AFFECTS-US**: this server exposes or relies on the changed surface. The SDK
  may implement the wire behavior, but the migration must pin, configure, or
  test it.
- **NOT-APPLICABLE**: the feature or direction is not implemented here and will
  not be added merely because the revision permits it.

## Protocol negotiation and lifecycle

| Normative change | Verdict | Repository-specific reason |
| --- | --- | --- |
| Protocol-level sessions and `Mcp-Session-Id` are removed. [Source](https://modelcontextprotocol.io/specification/2026-07-28/changelog#major-changes) | **AFFECTS-US** | Although the production entry point is stdio, SDK v2's modern dispatcher and test-only Streamable HTTP app must accept independent requests without session state. Application state already lives in the downstream credential/token store, not an MCP session. |
| Modern requests remove `initialize` and carry protocol version, client capabilities, and recommended identity in `_meta`; version mismatch uses `UnsupportedProtocolVersionError`. [Source](https://modelcontextprotocol.io/specification/2026-07-28/changelog#major-changes) | **AFFECTS-US** | The stdio server must serve modern self-describing requests while SDK v2 retains legacy negotiation. |
| Servers MUST implement `server/discover`. [Source](https://modelcontextprotocol.io/specification/2026-07-28/changelog#major-changes) | **AFFECTS-US** | Every modern server needs discovery of versions, identity, and capabilities. |
| All results require `resultType`, ordinarily `"complete"`. [Source](https://modelcontextprotocol.io/specification/2026-07-28/changelog#major-changes) | **AFFECTS-US** | This server returns tool, resource, prompt, discovery, and list results. |
| Server-initiated requests are replaced by Multi Round-Trip Requests (MRTR). [Source](https://modelcontextprotocol.io/specification/2026-07-28/changelog#major-changes) | **NOT-APPLICABLE** | No tool, resource, or prompt uses sampling, roots, elicitation, or another server-to-client request. |
| `ping`, `logging/setLevel`, and `notifications/roots/list_changed` are removed; protocol logging becomes request-scoped. [Source](https://modelcontextprotocol.io/specification/2026-07-28/changelog#major-changes) | **NOT-APPLICABLE** | The server implements none of these methods and emits no MCP logging notifications. |

## Transports and notifications

| Normative change | Verdict | Repository-specific reason |
| --- | --- | --- |
| Streamable HTTP POST requests require `Mcp-Method`, plus `Mcp-Name` for named operations; `x-mcp-header` maps selected tool arguments to custom headers. [Source](https://modelcontextprotocol.io/specification/2026-07-28/changelog#minor-changes) | **AFFECTS-US** | The runtime remains stdio, but the same `MCPServer` owns the constructible Streamable HTTP surface. Raw-wire tests must prove the SDK validates routing headers. No tool opts into `x-mcp-header`. |
| HTTP GET and resource subscribe/unsubscribe are replaced by `subscriptions/listen`. [Source](https://modelcontextprotocol.io/specification/2026-07-28/changelog#major-changes) | **AFFECTS-US** | SDK v2 maps the high-level server's existing tool/prompt/resource list-change and resource-subscription declarations to modern discovery. No publisher, event store, or custom subscription bus will be added. |
| SSE resumability and redelivery are removed. [Source](https://modelcontextprotocol.io/specification/2026-07-28/changelog#major-changes) | **NOT-APPLICABLE** | There is no event store or resumption dependency. |
| Legacy HTTP+SSE is formally deprecated. [Source](https://modelcontextprotocol.io/specification/2026-07-28/changelog#deprecated) | **NOT-APPLICABLE** | The production server exposes stdio only and has no HTTP+SSE transport. |

## Capabilities and extensions

| Normative change | Verdict | Repository-specific reason |
| --- | --- | --- |
| Client and server capabilities gain an `extensions` field. [Source](https://modelcontextprotocol.io/specification/2026-07-28/changelog#minor-changes) | **AFFECTS-US** | `server/discover` exposes this shape; the server must not advertise an unused extension. |
| Core experimental tasks move to `io.modelcontextprotocol/tasks`. [Source](https://modelcontextprotocol.io/specification/2026-07-28/changelog#major-changes) | **NOT-APPLICABLE** | The apparent task-related tools are fail-loud CosmoLex vendor stubs, not MCP Tasks protocol handlers. |
| Roots, Sampling, and Logging are deprecated. [Source](https://modelcontextprotocol.io/specification/2026-07-28/changelog#deprecated) | **NOT-APPLICABLE** | None is declared or used. |
| Sampling `includeContext` values `"thisServer"` and `"allServers"` are deprecated. [Source](https://modelcontextprotocol.io/specification/2026-07-28/changelog#deprecated) | **NOT-APPLICABLE** | Sampling is not used. |

## Tools, resources, prompts, and cache semantics

| Normative change | Verdict | Repository-specific reason |
| --- | --- | --- |
| Tool, prompt, resource, resource-template list results and resource reads require `ttlMs` and `cacheScope`. [Source](https://modelcontextprotocol.io/specification/2026-07-28/changelog#minor-changes) | **AFFECTS-US** | The server exposes tools, prompts, and static resources. SDK v2's conservative private, zero-TTL defaults preserve the existing no-cache posture. |
| `tools/list` SHOULD be deterministic. [Source](https://modelcontextprotocol.io/specification/2026-07-28/changelog#minor-changes) | **AFFECTS-US** | The existing decorator registration order is stable and must be tested across repeated listings. |
| Tool schemas accept all JSON Schema 2020-12 keywords and structured content may be any JSON value. [Source](https://modelcontextprotocol.io/specification/2026-07-28/changelog#minor-changes) | **AFFECTS-US** | Decorators generate all tool schemas. SDK v2 owns revised validation; existing string results require no payload redesign. |
| Resource-not-found changes from `-32002` to `-32602`. [Source](https://modelcontextprotocol.io/specification/2026-07-28/changelog#minor-changes) | **AFFECTS-US** | Unknown `cosmolex://` resource URIs must now return Invalid Params. |
| URL-mode elicitation drops its completion notification and `elicitationId`. [Source](https://modelcontextprotocol.io/specification/2026-07-28/changelog#minor-changes) | **NOT-APPLICABLE** | The server performs no elicitation. |
| The generated schema models minimum, maximum, and default as numbers rather than only integers. [Source](https://modelcontextprotocol.io/specification/2026-07-28/changelog#other-schema-changes) | **NOT-APPLICABLE** | The repository neither vendors the MCP schema nor directly validates that numeric meta-schema; SDK v2 absorbs the correction. |

## Authorization and security

| Normative change | Verdict | Repository-specific reason |
| --- | --- | --- |
| Authorization servers SHOULD return RFC 9207 `iss`, which MCP clients validate. [Source](https://modelcontextprotocol.io/specification/2026-07-28/changelog#minor-changes) | **NOT-APPLICABLE** | This server has no MCP authorization layer. Its credential flow is a downstream CosmoLex API integration, not MCP client authorization. |
| MCP clients performing Dynamic Client Registration send `application_type`. [Source](https://modelcontextprotocol.io/specification/2026-07-28/changelog#minor-changes) | **NOT-APPLICABLE** | The process is not dynamically registered as an MCP client. |
| Persisted MCP client credentials are bound to their authorization-server issuer. [Source](https://modelcontextprotocol.io/specification/2026-07-28/changelog#minor-changes) | **NOT-APPLICABLE** | The server stores downstream CosmoLex application/user tokens, not MCP client registrations. |
| Dynamic Client Registration is deprecated in favor of Client ID Metadata Documents. [Source](https://modelcontextprotocol.io/specification/2026-07-28/changelog#deprecated) | **NOT-APPLICABLE** | The server neither hosts DCR nor acts as a dynamically registered MCP client. |

## Errors, metadata, and observability

| Normative change | Verdict | Repository-specific reason |
| --- | --- | --- |
| MCP reserves `-32020..-32099`; header mismatch, missing capability, and unsupported version use `-32020`, `-32021`, and `-32022`; unknown methods use `-32601`. [Source](https://modelcontextprotocol.io/specification/2026-07-28/changelog#minor-changes) | **AFFECTS-US** | The dispatcher can receive malformed routing, unsupported versions, and unknown methods. Tests cover reachable codes without inventing an optional capability. |
| `_meta` formally carries W3C `traceparent`, `tracestate`, and `baggage`. [Source](https://modelcontextprotocol.io/specification/2026-07-28/changelog#minor-changes) | **NOT-APPLICABLE** | The server has no MCP `_meta` tracing integration. |

The changelog's governance and SEP workflow updates impose no runtime or wire
requirements and are intentionally omitted. This migration will not adopt any
deprecated feature merely to demonstrate SDK support.
