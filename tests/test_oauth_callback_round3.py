"""Exercise the real setup entry point with an owned HTTP callback; no vendor calls."""

import builtins
from concurrent.futures import ThreadPoolExecutor
from http.client import HTTPConnection
import socket
from unittest.mock import Mock
from urllib.parse import parse_qs, urlencode, urlsplit

import pytest

from cosmolex_mcp import oauth_callback
from cosmolex_mcp.setup import oauth_flow as setup_flow


@pytest.fixture
def configure(monkeypatch):
    monkeypatch.setattr(setup_flow.sys, "argv", ["setup"])

    def configure(redirect):
        for key in ("API_KEY", "CLIENT_ID", "CLIENT_SECRET"):
            monkeypatch.setenv("COSMOLEX_" + key, "dummy")
        monkeypatch.setenv("COSMOLEX_REDIRECT_URI", redirect)
        monkeypatch.setattr(setup_flow.credentials, "set_secret", lambda *a: "keyring")
        monkeypatch.setattr(setup_flow.credentials, "delete_secret", lambda *a: None)
        exchange = Mock(return_value={"access_token": "dummy"})
        monkeypatch.setattr(setup_flow, "exchange_code", exchange)
        return exchange

    return configure


@pytest.mark.parametrize(
    "redirect",
    [
        "https://attacker.example/callback",
        "http://localhost:8124/callback",
        "http://[::1]:8124/callback",
        "https://127.0.0.1:8124/callback",
        "http://127.0.0.1:8124/callback?query=1",
    ],
)
def test_real_setup_refuses_unowned_or_unsupported_callback(
    configure, redirect, capsys, monkeypatch
):
    exchange = configure(redirect)
    bind = Mock(side_effect=AssertionError("must reject before binding"))
    monkeypatch.setattr(oauth_callback, "HTTPServer", bind)
    with pytest.raises(SystemExit) as error:
        setup_flow.main()
    assert error.value.code == 1
    exchange.assert_not_called()
    bind.assert_not_called()
    captured = capsys.readouterr()
    output = captured.out + captured.err
    assert (
        "Register an HTTP loopback redirect with the vendor using 127.0.0.1" in output
    )
    assert "response_type=code" not in output
    assert "attacker.example" not in output


def test_real_setup_bind_failure_does_not_advertise_authorization(configure, capsys):
    with socket.socket() as occupied:
        occupied.bind(("127.0.0.1", 0))
        occupied.listen()
        redirect = f"http://127.0.0.1:{occupied.getsockname()[1]}/callback"
        exchange = configure(redirect)
        with pytest.raises(SystemExit) as error:
            setup_flow.main()
        assert error.value.code == 1
    exchange.assert_not_called()
    captured = capsys.readouterr()
    assert "response_type=code" not in captured.out
    assert "could not receive a valid OAuth callback" in captured.out + captured.err


@pytest.mark.parametrize("returned_state", ["matching", "wrong", "missing"])
def test_real_setup_http_callback_end_to_end(configure, monkeypatch, returned_state):
    # Allocate an unused local port, then let the real setup listener bind it.
    with socket.socket() as available:
        available.bind(("127.0.0.1", 0))
        port = available.getsockname()[1]
    redirect = f"http://127.0.0.1:{port}/callback"
    exchange = configure(redirect)
    original_receive = oauth_callback.LoopbackCallback.receive
    listeners = []

    def bounded_receive(self):
        listeners.append(self)
        self.server.timeout = 0.05
        return original_receive(self, timeout=2)

    monkeypatch.setattr(oauth_callback.LoopbackCallback, "receive", bounded_receive)
    original_print = builtins.print
    browser_futures = []

    def browser(params):
        query = {"code": "dummy-code"}
        if returned_state != "missing":
            query["state"] = (
                params["state"][0] if returned_state == "matching" else "wrong"
            )
        connection = HTTPConnection("127.0.0.1", port, timeout=3)
        try:
            connection.request("GET", "/callback?" + urlencode(query))
            response = connection.getresponse()
            response.read()
            assert response.status == (200 if returned_state == "matching" else 400)
        finally:
            connection.close()

    with ThreadPoolExecutor(max_workers=1) as pool:

        def observe_print(*args, **kwargs):
            if (
                len(args) == 1
                and isinstance(args[0], str)
                and "response_type=code" in args[0]
            ):
                params = parse_qs(urlsplit(args[0]).query)
                assert params["redirect_uri"] == [redirect]
                assert len(params["state"][0]) >= 43
                # At the instant the URL is printed, setup already owns this port.
                with socket.socket() as contender:
                    with pytest.raises(OSError):
                        contender.bind(("127.0.0.1", port))
                browser_futures.append(pool.submit(browser, params))
            original_print(*args, **kwargs)

        monkeypatch.setattr(builtins, "print", observe_print)
        if returned_state == "matching":
            setup_flow.main()
            exchange.assert_called_once()
            assert exchange.call_args.args == ("dummy-code", redirect, "dummy", "dummy")
        else:
            with pytest.raises(SystemExit) as error:
                setup_flow.main()
            assert error.value.code == 1
            exchange.assert_not_called()
        assert len(browser_futures) == 1
        browser_futures[0].result(timeout=4)
    assert len(listeners) == 1
    assert listeners[0].server.fileno() == -1
    assert listeners[0].code == ("dummy-code" if returned_state == "matching" else None)
