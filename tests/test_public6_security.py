"""Offline reproductions of PUBLIC6 findings through real MCP/setup boundaries."""

from cosmolex_mcp import credentials, private_storage
from cosmolex_mcp.endpoint_validation import vendor_endpoint, LCS_HOSTS
from cosmolex_mcp import oauth_callback
from cosmolex_mcp.setup import oauth_flow as setup_flow
import asyncio
import os
from pathlib import Path
from unittest.mock import Mock

import pytest
from mcp import ClientSession
from mcp.client._memory import InMemoryTransport
from cosmolex_mcp import client as client_module, server


@pytest.fixture
def boundary(monkeypatch):
    client = object.__new__(client_module.LCSClient)
    calls = Mock(return_value={"id": "123"})
    for name in ("get", "put", "patch", "post", "_detail", "_send", "_request"):
        monkeypatch.setattr(client, name, calls, raising=False)
    monkeypatch.setattr(server, "LCSClient", lambda: client)
    for name in ("_c", "_client", "get_client"):
        if hasattr(server, name):
            monkeypatch.setattr(server, name, lambda: client)

    async def invoke(name, arguments):
        async with InMemoryTransport(server.mcp) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                return await session.call_tool(name, arguments)

    return lambda name, arguments: asyncio.run(invoke(name, arguments)), calls


@pytest.mark.parametrize(
    "name,arguments",
    [
        ("update_matter", {"matter_id": "123", "fields_json": "{}"}),
        ("update_client", {"client_id": "123", "fields_json": "{}"}),
        ("update_contact", {"contact_id": "123", "fields_json": "{}"}),
        ("update_time_entry", {"time_entry_id": "123", "fields_json": "{}"}),
        ("update_expense", {"expense_id": "123", "fields_json": "{}"}),
        ("update_invoice", {"invoice_id": "123", "fields_json": "{}"}),
        ("update_transaction", {"transaction_id": "123", "fields_json": "{}"}),
    ],
)
def test_empty_write_rejected_at_mcp_boundary(boundary, name, arguments):
    call, requests = boundary
    result = call(name, arguments)
    assert result.is_error, result
    assert any(
        "field" in item.text or "non-empty" in item.text for item in result.content
    )
    requests.assert_not_called()


@pytest.mark.parametrize("failure", ["directory_chmod", "fchmod", "replace", None])
@pytest.mark.parametrize("existing", [False, True])
def test_fallback_private_from_creation_and_fail_closed(
    monkeypatch, tmp_path, failure, existing
):
    target = tmp_path / "config" / ".env"
    if existing:
        target.parent.mkdir()
        target.write_text("old value")
    if "cosmolex" == "lawmatics":
        monkeypatch.setattr(credentials, "env_file", lambda: target)
    else:
        monkeypatch.setattr(credentials, "ENV_FILE", target)
        monkeypatch.setattr(credentials, "CONFIG_DIR", target.parent)
    observed = []
    real_open = os.open

    def opened(path, flags, mode=0o777):
        fd = real_open(path, flags, mode)
        observed.append((mode, os.fstat(fd).st_mode & 0o777))
        return fd

    monkeypatch.setattr(private_storage.os, "open", opened)

    def denied(*args, **kwargs):
        raise OSError("simulated permissions failure")

    if failure == "directory_chmod":
        monkeypatch.setattr(Path, "chmod", denied)
    elif failure:
        monkeypatch.setattr(private_storage.os, failure, denied)
    old_umask = os.umask(0o022)
    try:
        if failure:
            with pytest.raises(OSError):
                credentials._write_env_file({"TEST_VALUE": "dummy"})
            assert (
                target.read_text() == "old value" if existing else not target.exists()
            )
        else:
            credentials._write_env_file({"TEST_VALUE": "dummy"})
            assert target.stat().st_mode & 0o777 == 0o600
            assert target.parent.stat().st_mode & 0o777 == 0o700
    finally:
        os.umask(old_umask)
    assert all(mode == actual == 0o600 for mode, actual in observed)
    assert not list(target.parent.glob("..env.*")) if target.parent.exists() else True


@pytest.mark.parametrize(
    "url",
    [
        "http://2130706433",
        "http://0x7f000001",
        "https://attacker.example",
        "https://127.1",
        "https://0177.0.0.1",
        "https://[::ffff:127.0.0.1]",
        "https://app.rocketmatter.net.attacker.example",
        "https://law.cosmolex.com@attacker.example",
        "https://law.cosmolex.com?secret=x",
        "https://law.cosmolex.com#x",
        "https://law.cosmolex.com:8443",
        "https://unrelated.azurewebsites.net",
    ],
)
@pytest.mark.parametrize("variable", ["COSMOLEX_BASE_URL", "COSMOLEX_API_BASE_URL"])
def test_configured_endpoint_rejected_on_import(monkeypatch, url, variable):
    import subprocess
    import sys

    monkeypatch.setenv(variable, url)
    proc = subprocess.run(
        [sys.executable, "-c", "import cosmolex_mcp.client"],
        text=True,
        capture_output=True,
    )
    assert proc.returncode != 0
    assert "Invalid endpoint" in proc.stderr


def test_exact_documented_hosts_are_accepted():
    for host in LCS_HOSTS:
        assert vendor_endpoint("https://" + host, LCS_HOSTS) == "https://" + host


@pytest.mark.parametrize("failure", ["directory_chmod", "fchmod", None])
def test_token_file_private_before_write(monkeypatch, tmp_path, failure):
    target = tmp_path / "private" / "tokens.json"
    monkeypatch.setattr(client_module, "TOKEN_FILE", target)
    monkeypatch.setattr(client_module, "CONFIG_DIR", target.parent)

    def denied(*args, **kwargs):
        raise OSError("simulated permissions failure")

    if failure == "directory_chmod":
        monkeypatch.setattr(Path, "chmod", denied)
    elif failure:
        monkeypatch.setattr(private_storage.os, failure, denied)
    old_umask = os.umask(0o022)
    try:
        if failure:
            with pytest.raises(OSError):
                client_module._save_tokens({"access_token": "dummy"})
            assert not target.exists()
        else:
            client_module._save_tokens({"access_token": "dummy"})
            assert target.stat().st_mode & 0o777 == 0o600
    finally:
        os.umask(old_umask)


@pytest.mark.parametrize(
    "suffix",
    [
        "?code=dummy",
        "?code=dummy&state=wrong",
        "?code=dummy&state=expected&state=expected",
        "?code=dummy&code=other&state=expected",
        "?state=expected",
        "?code=dummy&state=expected&error=denied",
        "?code=dummy&state=expected#fragment",
    ],
)
def test_missing_wrong_duplicate_state_or_code_rejected(suffix):
    with pytest.raises(ValueError):
        oauth_callback.redirect_code(
            "http://127.0.0.1:8124/callback" + suffix,
            "http://127.0.0.1:8124/callback",
            "expected",
        )


def test_state_randomness_and_valid_redirect():
    states = {oauth_callback.new_state() for _ in range(100)}
    assert len(states) == 100
    assert all(len(x) >= 43 for x in states)
    assert (
        oauth_callback.redirect_code(
            "http://127.0.0.1:8124/callback?code=dummy&state=expected",
            "http://127.0.0.1:8124/callback",
            "expected",
        )
        == "dummy"
    )
    with pytest.raises(ValueError):
        oauth_callback.redirect_code(
            "https://attacker.example/callback?code=dummy&state=expected",
            "http://127.0.0.1:8124/callback",
            "expected",
        )


@pytest.mark.parametrize("returned_state", [None, "wrong", "expected"])
def test_real_setup_checks_state_before_exchange(monkeypatch, returned_state, capsys):
    from urllib.parse import parse_qs, urlsplit

    monkeypatch.setattr(setup_flow, "new_state", lambda: "expected")
    monkeypatch.setattr(setup_flow.sys, "argv", ["setup"])
    events = []
    exchange = Mock(return_value={"access_token": "dummy"})
    code_query = "?code=dummy" + ("&state=" + returned_state if returned_state else "")

    class FakeHTTPServer:
        def __init__(self, address, handler):
            events.append(("bound", address))
            self.handler = handler

        def handle_request(self):
            import io

            handler = object.__new__(self.handler)
            handler.path = "/callback" + code_query
            handler.send_response = Mock()
            handler.send_header = Mock()
            handler.end_headers = Mock()
            handler.wfile = io.BytesIO()
            handler.do_GET()
            if returned_state != "expected":
                raise ValueError("invalid callback")

        def server_close(self):
            events.append(("closed",))

    monkeypatch.setattr(oauth_callback, "HTTPServer", FakeHTTPServer)
    for key in (
        "COSMOLEX_API_KEY",
        "COSMOLEX_CLIENT_ID",
        "COSMOLEX_CLIENT_SECRET",
    ):
        monkeypatch.setenv(key, "dummy")
    monkeypatch.setattr(setup_flow.credentials, "set_secret", lambda *a: "keyring")
    monkeypatch.setattr(setup_flow.credentials, "delete_secret", lambda *a: None)
    monkeypatch.setattr(setup_flow, "exchange_code", exchange)
    original_build = setup_flow.build_authorize_url

    def authorize(*args):
        assert events[0][0] == "bound"
        return original_build(*args)

    monkeypatch.setattr(setup_flow, "build_authorize_url", authorize)
    assert setup_flow.DEFAULT_REDIRECT_URI == "http://127.0.0.1:8770/callback"
    if returned_state == "expected":
        setup_flow.main()
        exchange.assert_called_once()
    else:
        with pytest.raises(SystemExit) as exc:
            setup_flow.main()
        assert exc.value.code == 1
        exchange.assert_not_called()
    output = capsys.readouterr().out
    authorization = next(
        line.strip() for line in output.splitlines() if "response_type=code" in line
    )
    assert parse_qs(urlsplit(authorization).query)["state"] == ["expected"]
    assert events[0][0] == "bound"
    assert events[-1] == ("closed",)


@pytest.mark.parametrize("args", [["--code=dummy"], ["--code", "dummy"]])
def test_setup_rejects_code_in_argv(monkeypatch, args):
    monkeypatch.setattr(setup_flow.sys, "argv", ["setup", *args])
    exchange = Mock()
    monkeypatch.setattr(setup_flow, "exchange_code", exchange)
    with pytest.raises(SystemExit) as exc:
        setup_flow.main()
    assert exc.value.code == 1
    exchange.assert_not_called()


@pytest.mark.parametrize("operation", ["exchange", "refresh", "api"])
def test_credentials_never_follow_http_redirects(monkeypatch, operation):
    import requests

    response = requests.Response()
    response.status_code = 302
    response.headers["Location"] = "https://attacker.example/"
    response._content = b"{}"
    transport = Mock(return_value=response)
    monkeypatch.setattr(client_module.requests, "post", transport)
    client = object.__new__(client_module.LCSClient)
    client.session = Mock(request=transport)
    client._api_key = "dummy"
    client._client_id = "dummy"
    client._client_secret = "dummy"
    client._tokens = {
        "access_token": "dummy",
        "refresh_token": "dummy",
        "expires_at": 9999999999,
    }
    try:
        if operation == "exchange":
            client_module.exchange_code(
                "dummy", client_id="dummy", client_secret="dummy"
            )
        elif operation == "refresh":
            client._refresh()
        else:
            client._send("GET", "matters")
    except Exception:
        pass  # 302 is not a token response; the credential-bearing call is what matters.
    transport.assert_called_once()
    assert transport.call_args.kwargs["allow_redirects"] is False
