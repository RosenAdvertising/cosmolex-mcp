"""Session-bound OAuth redirect validation and owned loopback callback."""

import secrets
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlsplit


def new_state() -> str:
    return secrets.token_urlsafe(32)


def redirect_code(response: str, redirect_uri: str, expected_state: str) -> str:
    """Require the exact redirect destination and one matching state/code."""
    message = "Invalid OAuth redirect or state. Restart setup and authorize again."
    try:
        if any(ord(c) <= 32 for c in response) or "\\" in response:
            raise ValueError
        received = urlsplit(response)
        registered = urlsplit(redirect_uri)
        if (received.scheme, received.netloc, received.path) != (
            registered.scheme,
            registered.netloc,
            registered.path,
        ) or received.fragment:
            raise ValueError
        params = parse_qs(received.query, keep_blank_values=True)
        state = params.get("state", [])
        code = params.get("code", [])
        if (
            not expected_state
            or len(state) != 1
            or not secrets.compare_digest(state[0].encode(), expected_state.encode())
            or len(code) != 1
            or not code[0]
            or "error" in params
        ):
            raise ValueError
        return code[0]
    except (ValueError, TypeError):
        raise ValueError(message) from None


def _callback_path(path: str) -> str:
    """Require an unchanged, single-slash origin-form callback path."""
    if (
        not path.startswith("/")
        or path.startswith("//")
        or "?" in path
        or "#" in path
        or "\\" in path
        or any(ord(c) <= 32 for c in path)
    ):
        raise ValueError
    return path


def validate_redirect(redirect_uri: str) -> None:
    try:
        url = urlsplit(redirect_uri)
        _callback_path(url.path)
        if (
            url.username is not None
            or url.password is not None
            or "?" in redirect_uri
            or "#" in redirect_uri
            or any(ord(c) <= 32 for c in redirect_uri)
            or "\\" in redirect_uri
        ):
            raise ValueError
        if url.scheme != "http" or url.hostname != "127.0.0.1" or not url.port:
            raise ValueError
    except (ValueError, TypeError):
        raise ValueError(
            "Register an HTTP loopback redirect with the vendor using 127.0.0.1, an explicit port and callback path before running setup. localhost and external callbacks are not supported."
        ) from None


class LoopbackCallback:
    """Bind before displaying authorization; suppress request/code logging."""

    def __init__(self, redirect_uri: str, state: str):
        validate_redirect(redirect_uri)
        self.redirect_uri = redirect_uri
        self.state = state
        self.code = None
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_GET(self):
                try:
                    # Only an origin-form request for the registered callback is valid.
                    _callback_path(self.path.partition("?")[0])
                    parsed = urlsplit(owner.redirect_uri)
                    code = redirect_code(
                        f"{parsed.scheme}://{parsed.netloc}{self.path}",
                        owner.redirect_uri,
                        owner.state,
                    )
                except ValueError:
                    self.send_response(400)
                    self.end_headers()
                    self.wfile.write(b"Invalid OAuth response. Return to setup.")
                    return
                owner.code = code
                self.send_response(200)
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(b"Authorization received. You may close this window.")

        self.server = HTTPServer(("127.0.0.1", urlsplit(redirect_uri).port), Handler)
        self.server.timeout = 1

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.server.server_close()

    def receive(self, timeout: float = 180) -> str:
        deadline = time.monotonic() + timeout
        while self.code is None and time.monotonic() < deadline:
            self.server.handle_request()
        if self.code is None:
            raise ValueError("OAuth callback timed out. Restart setup.")
        return self.code
