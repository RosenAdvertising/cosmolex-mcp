"""In-process Streamable HTTP checks for MCP 2026-07-28."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from importlib.metadata import version as distribution_version
from typing import Any

import httpx2 as httpx
import pytest
import requests

from cosmolex_mcp import server
from cosmolex_mcp.client import LCSClient


PROTOCOL_VERSION = "2026-07-28"
PROTOCOL_VERSION_META_KEY = "io.modelcontextprotocol/protocolVersion"
CLIENT_CAPABILITIES_META_KEY = "io.modelcontextprotocol/clientCapabilities"
CLIENT_INFO_META_KEY = "io.modelcontextprotocol/clientInfo"
SERVER_INFO_META_KEY = "io.modelcontextprotocol/serverInfo"


def _headers(method: str, params: dict[str, Any] | None = None) -> dict[str, str]:
    headers = {
        "accept": "application/json, text/event-stream",
        "content-type": "application/json",
        "mcp-protocol-version": PROTOCOL_VERSION,
        "mcp-method": method,
    }
    if method == "tools/call" and params is not None:
        headers["mcp-name"] = str(params["name"])
    return headers


def _body(
    method: str,
    params: dict[str, Any] | None = None,
    *,
    request_id: int = 1,
) -> dict[str, Any]:
    request_params = dict(params or {})
    request_params["_meta"] = {
        PROTOCOL_VERSION_META_KEY: PROTOCOL_VERSION,
        CLIENT_CAPABILITIES_META_KEY: {},
        CLIENT_INFO_META_KEY: {"name": "cosmolex-http-test", "version": "0"},
    }
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "method": method,
        "params": request_params,
    }


def _payload(response: httpx.Response) -> dict[str, Any]:
    content_type = response.headers.get("content-type", "")
    if "text/event-stream" in content_type:
        data_lines = [
            line[5:].strip()
            for line in response.text.splitlines()
            if line.startswith("data:")
        ]
        assert data_lines, response.text
        return json.loads(data_lines[-1])
    return response.json()


def _result(response: httpx.Response) -> dict[str, Any]:
    assert response.status_code == 200, response.text
    payload = _payload(response)
    assert payload["jsonrpc"] == "2.0"
    return payload["result"]


@asynccontextmanager
async def _client(
    app,
    base_url: str = "http://127.0.0.1:8080",
) -> AsyncIterator[httpx.AsyncClient]:
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url=base_url) as client:
            yield client


async def _post(
    app,
    method: str,
    params: dict[str, Any] | None = None,
    *,
    header_overrides: dict[str, str] | None = None,
    base_url: str = "http://127.0.0.1:8080",
) -> httpx.Response:
    headers = _headers(method, params)
    if header_overrides:
        headers.update(header_overrides)
    async with _client(app, base_url) as client:
        return await client.post("/mcp", headers=headers, json=_body(method, params))


def test_tools_list_matches_the_stdio_server() -> None:
    async def listed() -> tuple[dict[str, Any], dict[str, Any]]:
        stdio_tools = await server.mcp.list_tools()
        response = await _post(server.create_serve_app(), "tools/list")
        return {tool.name: tool for tool in stdio_tools}, _result(response)

    stdio_tools, http_result = asyncio.run(listed())
    http_tools = http_result["tools"]
    assert [tool["name"] for tool in http_tools] == list(stdio_tools)
    for http_tool in http_tools:
        stdio_tool = stdio_tools[http_tool["name"]]
        dumped = stdio_tool.model_dump(by_alias=True, mode="json", exclude_none=True)
        assert http_tool["inputSchema"] == dumped["inputSchema"]


def test_read_tool_runs_against_the_vendor_send_mock(monkeypatch) -> None:
    vendor_payload = {
        "items": [{"id": "matter-1", "matterName": "Alpha"}],
        "totalCount": 1,
    }
    vendor = object.__new__(LCSClient)

    def send(method: str, path: str, params=None, body=None):
        assert method == "GET"
        assert path == "matters"
        response = requests.Response()
        response.status_code = 200
        response._content = json.dumps(vendor_payload).encode()
        response.headers["Content-Type"] = "application/json"
        return response

    vendor._send = send  # type: ignore[method-assign]
    monkeypatch.setattr(server, "_c", lambda: vendor)

    response = asyncio.run(
        _post(
            server.create_serve_app(),
            "tools/call",
            {"name": "list_matters", "arguments": {}},
        )
    )
    result = _result(response)
    assert result["isError"] is False
    assert json.loads(result["content"][0]["text"]) == vendor_payload


def test_requests_are_stateless_and_omit_session_id() -> None:
    app = server.create_serve_app()
    observed: list[Any] = []

    async def observe(ctx, call_next):
        connection = ctx.session._connection
        if not observed:
            connection.state["written_by_request_1"] = "only-request-1"
        observed.append(connection.state.get("written_by_request_1"))
        return await call_next(ctx)

    server.mcp.middleware.append(observe)
    try:

        async def both() -> tuple[httpx.Response, httpx.Response]:
            async with _client(app) as client:
                first = await client.post(
                    "/mcp",
                    headers=_headers("tools/list"),
                    json=_body("tools/list", request_id=1),
                )
                second = await client.post(
                    "/mcp",
                    headers={
                        **_headers("tools/list"),
                        "mcp-session-id": "not-a-session",
                    },
                    json=_body("tools/list", request_id=2),
                )
                return first, second

        first, second = asyncio.run(both())
    finally:
        server.mcp.middleware.remove(observe)

    assert observed == ["only-request-1", None]
    assert _result(first)["tools"]
    assert [tool["name"] for tool in _result(second)["tools"]] == [
        tool["name"] for tool in _result(first)["tools"]
    ]
    assert "mcp-session-id" not in first.headers
    assert "mcp-session-id" not in second.headers


def test_transport_default_is_stdio_and_bogus_exits(monkeypatch) -> None:
    monkeypatch.delenv("COSMOLEX_MCP_TRANSPORT", raising=False)
    assert server._requested_transport() == "stdio"
    monkeypatch.setenv("COSMOLEX_MCP_TRANSPORT", "  STDIO  ")
    assert server._requested_transport() == "stdio"
    ran: dict[str, bool] = {}
    monkeypatch.setattr(
        server.mcp, "run", lambda *args, **kwargs: ran.setdefault("yes", True)
    )
    monkeypatch.delenv("COSMOLEX_MCP_TRANSPORT", raising=False)
    server.main()
    assert ran["yes"] is True

    monkeypatch.setenv("COSMOLEX_MCP_TRANSPORT", "bogus")
    with pytest.raises(SystemExit) as caught:
        server.main()
    message = str(caught.value)
    assert "bogus" in message
    assert "stdio" in message
    assert "streamable-http" in message


def test_non_integer_port_exits(monkeypatch) -> None:
    monkeypatch.setenv("PORT", "nope")
    with pytest.raises(SystemExit) as caught:
        server._port()
    assert "PORT" in str(caught.value)
    assert "nope" in str(caught.value)


def test_allowed_hosts_refuse_foreign_host_and_bad_origin(monkeypatch) -> None:
    monkeypatch.setenv("COSMOLEX_MCP_HOST", "0.0.0.0")
    monkeypatch.setenv("COSMOLEX_MCP_ALLOWED_HOSTS", "allowed.example")
    monkeypatch.setenv("COSMOLEX_MCP_ALLOWED_ORIGINS", "https://allowed.example")
    app = server.create_serve_app()

    async def rejected() -> tuple[httpx.Response, httpx.Response]:
        async with _client(app, "http://allowed.example") as client:
            foreign_host = await client.post(
                "/mcp",
                headers={**_headers("tools/list"), "host": "other.example"},
                json=_body("tools/list"),
            )
            bad_origin = await client.post(
                "/mcp",
                headers={
                    **_headers("tools/list"),
                    "host": "allowed.example",
                    "origin": "https://evil.example",
                },
                json=_body("tools/list"),
            )
            return foreign_host, bad_origin

    foreign_host, bad_origin = asyncio.run(rejected())
    assert foreign_host.status_code == 421
    assert bad_origin.status_code == 403


def test_non_loopback_host_without_allowed_hosts_exits(monkeypatch) -> None:
    monkeypatch.setenv("COSMOLEX_MCP_HOST", "0.0.0.0")
    monkeypatch.delenv("COSMOLEX_MCP_ALLOWED_HOSTS", raising=False)
    with pytest.raises(SystemExit) as caught:
        server.create_serve_app()
    assert "COSMOLEX_MCP_ALLOWED_HOSTS" in str(caught.value)


def test_get_and_delete_are_rejected_and_discover_advertises_version() -> None:
    app = server.create_serve_app()

    async def responses() -> tuple[httpx.Response, httpx.Response, httpx.Response]:
        async with _client(app) as client:
            route = {"mcp-protocol-version": PROTOCOL_VERSION}
            get_response = await client.get("/mcp", headers=route)
            delete_response = await client.delete("/mcp", headers=route)
            discover = await client.post(
                "/mcp",
                headers=_headers("server/discover"),
                json=_body("server/discover"),
            )
            return get_response, delete_response, discover

    get_response, delete_response, discover = asyncio.run(responses())
    assert get_response.status_code == 405
    assert delete_response.status_code == 405
    result = _result(discover)
    assert PROTOCOL_VERSION in result["supportedVersions"]
    server_info = result["_meta"][SERVER_INFO_META_KEY]
    assert server_info["version"] == distribution_version("cosmolex-mcp")
    assert server_info["version"]
    assert server.mcp.name == "cosmolex"
    assert server.mcp.title == "CosmoLex"
    assert server.mcp.version == server_info["version"]


def test_stateless_lifespan_runs_once_for_the_app_not_per_request(monkeypatch) -> None:
    entries: list[str] = []
    original = server.mcp._lowlevel_server.lifespan

    @asynccontextmanager
    async def counting(lowlevel_app):
        entries.append("enter")
        async with original(lowlevel_app) as state:
            yield state

    monkeypatch.setattr(server.mcp._lowlevel_server, "lifespan", counting)
    app = server.create_serve_app()

    async def two_requests() -> None:
        async with _client(app) as client:
            first = await client.post(
                "/mcp",
                headers=_headers("tools/list"),
                json=_body("tools/list", request_id=1),
            )
            second = await client.post(
                "/mcp",
                headers=_headers("tools/list"),
                json=_body("tools/list", request_id=2),
            )
            assert first.status_code == 200
            assert second.status_code == 200

    asyncio.run(two_requests())
    assert entries == ["enter"]
