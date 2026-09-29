"""Setup and verification errors stay actionable without exposing secrets."""

import pytest
import requests

from cosmolex_mcp.client import AuthorizationRejected, MissingConfiguration
from cosmolex_mcp.setup import oauth_flow, verify


def test_verify_without_credentials_exits_cleanly(monkeypatch, capsys):
    monkeypatch.setattr(
        verify,
        "LCSClient",
        lambda: (_ for _ in ()).throw(
            MissingConfiguration(
                "No CosmoLex connection is configured. Run cosmolex-mcp-setup to connect, then restart the MCP server."
            )
        ),
    )
    with pytest.raises(SystemExit) as error:
        verify.main()
    assert error.value.code == 1
    assert capsys.readouterr().out == (
        "Verifying cosmolex-mcp credentials (LCS /v1 OAuth)...\n"
        "✗ Verification failed: No CosmoLex connection is configured. Run cosmolex-mcp-setup to connect, then restart the MCP server.\n"
        "If the refresh token was revoked, re-run: cosmolex-mcp-setup\n"
    )


def test_setup_empty_credentials_and_eof_exit_without_traceback(monkeypatch, capsys):
    monkeypatch.delenv("COSMOLEX_API_KEY", raising=False)
    monkeypatch.delenv("COSMOLEX_CLIENT_ID", raising=False)
    monkeypatch.delenv("COSMOLEX_CLIENT_SECRET", raising=False)
    monkeypatch.setattr("builtins.input", lambda _prompt: "")
    monkeypatch.setattr(oauth_flow.getpass, "getpass", lambda _prompt: "")
    with pytest.raises(SystemExit) as error:
        oauth_flow.main()
    assert error.value.code == 1
    output = capsys.readouterr().out
    assert "Error: API key, client ID, and client secret are all required." in output
    assert "Traceback" not in output


def test_setup_bad_credentials_are_sanitized_and_http_timeout_is_set(
    monkeypatch, capsys
):
    monkeypatch.setenv("COSMOLEX_API_KEY", "fake-api-secret")
    monkeypatch.setenv("COSMOLEX_CLIENT_ID", "fake-client-id")
    monkeypatch.setenv("COSMOLEX_CLIENT_SECRET", "fake-client-secret")
    monkeypatch.setenv("COSMOLEX_OAUTH_CODE", "fake-oauth-code")
    monkeypatch.setattr(oauth_flow.credentials, "set_secret", lambda *_: "keyring")
    monkeypatch.setattr(oauth_flow.credentials, "delete_secret", lambda *_: None)
    captured = {}
    response = requests.Response()
    response.status_code = 403
    response._content = b'{"detail":"private vendor response"}'
    monkeypatch.setattr(
        "cosmolex_mcp.client.requests.post",
        lambda *args, **kwargs: captured.update(kwargs) or response,
    )
    with pytest.raises(SystemExit) as error:
        oauth_flow.main()
    assert error.value.code == 1
    assert captured["timeout"] == 30
    output = capsys.readouterr().out
    assert (
        "CosmoLex access denied: the connected account lacks permission for this action"
        in output
    )
    assert "private vendor response" not in output
    assert "fake-client-secret" not in output
    assert "Traceback" not in output


def test_verify_bad_key_exits_with_permission_guidance(monkeypatch, capsys):
    class BadKeyClient:
        def list_users(self, **kwargs):
            raise AuthorizationRejected(
                "CosmoLex access denied: the connected account lacks permission for this action (or the authorization expired; re-run cosmolex-mcp-setup if so)."
            )

    monkeypatch.setattr(verify, "LCSClient", BadKeyClient)
    with pytest.raises(SystemExit) as error:
        verify.main()
    assert error.value.code == 1
    output = capsys.readouterr().out
    assert "CosmoLex access denied: the connected account lacks permission" in output
    assert "Traceback" not in output


def test_setup_prompt_eof_is_actionable(monkeypatch, capsys):
    monkeypatch.delenv("COSMOLEX_API_KEY", raising=False)
    monkeypatch.delenv("COSMOLEX_CLIENT_ID", raising=False)
    monkeypatch.delenv("COSMOLEX_CLIENT_SECRET", raising=False)
    monkeypatch.setattr(
        "builtins.input", lambda _prompt: (_ for _ in ()).throw(EOFError())
    )
    monkeypatch.setattr(
        oauth_flow.getpass, "getpass", lambda _prompt: (_ for _ in ()).throw(EOFError())
    )
    with pytest.raises(SystemExit) as error:
        oauth_flow.main()
    assert error.value.code == 1
    assert (
        "Error: API key, client ID, and client secret are all required."
        in capsys.readouterr().out
    )
