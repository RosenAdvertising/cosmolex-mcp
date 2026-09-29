"""Actionable, sanitized tool failures at the MCP dispatch boundary."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import pytest
import requests

from cosmolex_mcp import client as client_module
from cosmolex_mcp import server
from cosmolex_mcp.client import (
    AuthorizationRejected,
    InvalidToolArgument,
    MissingConfiguration,
    RateLimited,
    RecordNotFound,
    VendorHTTPFailure,
    LCSClient,
)
from tests.test_spec_2026_07_28 import _post_modern, _result


def _call(tool: str = "list_matters", arguments: dict[str, Any] | None = None):
    response = asyncio.run(
        _post_modern("tools/call", {"name": tool, "arguments": arguments or {}})
    )
    return _result(response)


@pytest.mark.parametrize(
    ("failure", "expected"),
    [
        (
            MissingConfiguration(
                "COSMOLEX_API_KEY is not set. Run cosmolex-mcp-setup."
            ),
            "Error executing tool list_matters: COSMOLEX_API_KEY is not set. Run cosmolex-mcp-setup.",
        ),
        (
            AuthorizationRejected(
                "CosmoLex rejected or expired authorization. Reauthorize with: cosmolex-mcp-setup."
            ),
            "Error executing tool list_matters: CosmoLex rejected or expired authorization. Reauthorize with: cosmolex-mcp-setup.",
        ),
        (
            VendorHTTPFailure(502, "internal_error"),
            "Error executing tool list_matters: CosmoLex returned HTTP 502: vendor service error.",
        ),
        (
            VendorHTTPFailure(418, "person@example.test?token=secret"),
            "Error executing tool list_matters: CosmoLex returned HTTP 418: request failed.",
        ),
        (
            RateLimited(17),
            "Error executing tool list_matters: CosmoLex rate limit reached. Retry after 17 seconds.",
        ),
        (
            InvalidToolArgument("page", "an integer greater than or equal to 1"),
            "Error executing tool list_matters: Invalid argument 'page': expected an integer greater than or equal to 1.",
        ),
        (
            RecordNotFound("matters record was not found."),
            "Error executing tool list_matters: matters record was not found.",
        ),
    ],
)
def test_typed_failures_are_exact_mcp_errors(monkeypatch, failure, expected):
    monkeypatch.setattr(server, "_c", lambda: _FailedClient(failure))
    result = _call()
    assert result["isError"] is True
    assert result["content"][0]["text"] == expected


class _FailedClient:
    def __init__(self, failure: Exception):
        self.failure = failure

    def list_matters(self, **kwargs):
        raise self.failure


def test_unsupported_capability_and_write_json_errors_are_actionable(monkeypatch):
    monkeypatch.setattr(server, "_c", lambda: object.__new__(LCSClient))
    unsupported = _call("list_banks")
    assert unsupported["isError"] is True
    assert unsupported["content"][0]["text"] == (
        "Error executing tool list_banks: list_banks (bank enumeration) is not available in the ProfitSolv LCS /v1 Integration API."
    )

    monkeypatch.setattr(
        server,
        "_c",
        lambda: type("Client", (), {"create_matter": lambda self, **fields: {}})(),
    )
    malformed = _call(
        "create_matter", {"fields_json": '{"email":"person@example.test"'}
    )
    assert malformed["isError"] is True
    assert malformed["content"][0]["text"] == (
        "Error executing tool create_matter: fields_json must be a JSON object"
    )
    assert "person@example.test" not in malformed["content"][0]["text"]


def test_schema_failure_names_field_and_expected_shape():
    result = _call("list_matters", {"page_size": 201})
    assert result["isError"] is True
    assert result["content"][0]["text"] == (
        "Error executing tool list_matters: Invalid arguments: page_size (expected an integer from 1 to 200)."
    )
    assert "201" not in result["content"][0]["text"]


def test_unknown_exception_is_masked_and_logs_only_fixed_reason(monkeypatch, caplog):
    secret = "person@example.test https://vendor.test/v1/matters?id=customer-42"

    class UnknownClient:
        def list_matters(self, **kwargs):
            raise RuntimeError(secret)

    monkeypatch.setattr(server, "_c", lambda: UnknownClient())
    with caplog.at_level(logging.INFO, logger="cosmolex_mcp.server"):
        result = _call()

    assert result["isError"] is True
    assert result["content"][0]["text"] == "Error executing tool list_matters"
    assert secret not in caplog.text
    assert "RuntimeError" not in caplog.text
    assert "tool_call_failed reason=unexpected_exception" in caplog.text


@pytest.mark.parametrize(
    "reason,expected",
    [
        ("invalid_request", "invalid request"),
        ("not_found", "resource was not found"),
        ("private-id-person@example.test", ""),
    ],
)
def test_vendor_reason_uses_allowlist(reason, expected):
    error = VendorHTTPFailure(400, reason)
    assert (expected in str(error)) if expected else (reason not in str(error))


def test_http_failure_sanitizes_vendor_reason_and_retry_after(monkeypatch):
    response = requests.Response()
    response.status_code = 429
    response.headers["Retry-After"] = "25"
    response._content = b'{"code":"private@example.test","detail":"customer secret"}'
    error = client_module.LCSClient._http_failure(response)
    assert str(error) == "CosmoLex rate limit reached. Retry after 25 seconds."


@pytest.mark.parametrize(
    ("status", "payload", "retry", "message"),
    [
        (
            401,
            {"detail": "Private Person person@example.invalid"},
            None,
            "CosmoLex rejected or expired authorization. Reauthorize with: cosmolex-mcp-setup.",
        ),
        (
            403,
            {"detail": "Private Person person@example.invalid"},
            None,
            "CosmoLex rejected or expired authorization. Reauthorize with: cosmolex-mcp-setup.",
        ),
        (
            404,
            {"detail": "Private Person person@example.invalid"},
            None,
            "CosmoLex resource was not found. Check the requested record.",
        ),
        (
            500,
            {
                "code": "internal_error",
                "detail": "Private Person person@example.invalid",
            },
            None,
            "CosmoLex returned HTTP 500: vendor service error.",
        ),
        (
            400,
            {"code": "Private Person person@example.invalid"},
            None,
            "CosmoLex returned HTTP 400: request failed.",
        ),
        (429, {}, "300", "CosmoLex rate limit reached. Retry after 300 seconds."),
        (
            429,
            {},
            "person@example.invalid",
            "CosmoLex rate limit reached. Retry after a short pause.",
        ),
    ],
)
def test_actual_http_failures_through_dispatch(
    monkeypatch, caplog, status, payload, retry, message
):
    from tests.test_canary_fixes import _client_with_response, _response

    client, _ = _client_with_response([])
    response = _response(payload)
    response.status_code = status
    if retry is not None:
        response.headers["Retry-After"] = retry
    monkeypatch.setattr(client, "_send", lambda *args, **kwargs: response)
    monkeypatch.setattr(server, "_c", lambda: client)
    with caplog.at_level(logging.INFO):
        result = _call()
    assert result["isError"] is True
    assert (
        result["content"][0]["text"] == f"Error executing tool list_matters: {message}"
    )
    assert "person@example.invalid" not in str(result) + caplog.text


def test_nullable_schema_argument_has_concrete_shape():
    result = _call(arguments={"client_id": {"person@example.invalid": "secret"}})
    assert result["isError"] is True
    assert (
        result["content"][0]["text"]
        == "Error executing tool list_matters: Invalid arguments: client_id (expected a string or null)."
    )


def test_unknown_failure_with_known_cause_stays_masked(monkeypatch, caplog):
    class Client:
        def list_matters(self, **kwargs):
            raise RuntimeError("person@example.invalid") from MissingConfiguration(
                "inner setup failure"
            )

    monkeypatch.setattr(server, "_c", lambda: Client())
    with caplog.at_level(logging.ERROR):
        result = _call()
    assert result["isError"] is True
    assert result["content"][0]["text"] == "Error executing tool list_matters"
    assert "person@example.invalid" not in caplog.text
    assert "inner setup failure" not in caplog.text
    assert "reason=unexpected_exception" in caplog.text


def test_oauth_refresh_rejection_is_safe_at_dispatch(monkeypatch):
    from tests.test_canary_fixes import _response

    client = object.__new__(LCSClient)
    client._tokens = {"refresh_token": "test-refresh-placeholder"}
    client._client_id = "test-client"
    client._client_secret = "test-secret"
    response = _response({"error": "invalid_grant", "detail": "person@example.invalid"})
    response.status_code = 400
    monkeypatch.setattr(
        client_module.requests, "post", lambda *args, **kwargs: response
    )
    monkeypatch.setattr(server, "_c", lambda: client)
    result = _call()
    assert result["isError"] is True
    assert (
        result["content"][0]["text"]
        == "Error executing tool list_matters: CosmoLex rejected or expired authorization. Reauthorize with: cosmolex-mcp-setup."
    )


def test_missing_record_and_known_404_record_quirk(monkeypatch):
    from tests.test_canary_fixes import _client_with_response, _response

    client, _ = _client_with_response([])
    response = _response({"error": "missing", "id": "private-record"})
    response.status_code = 404
    monkeypatch.setattr(client, "_send", lambda *args, **kwargs: response)
    monkeypatch.setattr(server, "_c", lambda: client)
    result = _call("get_matter", {"matter_id": "private-record"})
    assert result["isError"] is True
    assert (
        result["content"][0]["text"]
        == "Error executing tool get_matter: matters record was not found."
    )
    response._content = b'{"id":"valid-record","name":"Example"}'
    found = _call("get_matter", {"matter_id": "valid-record"})
    assert found["isError"] is False


def test_unreadable_vendor_response_has_safe_recovery(monkeypatch):
    from tests.test_canary_fixes import _client_with_response, _response

    client, _ = _client_with_response([])
    response = _response({})
    response._content = b"person@example.invalid"
    monkeypatch.setattr(client, "_send", lambda *args, **kwargs: response)
    monkeypatch.setattr(server, "_c", lambda: client)
    result = _call()
    assert result["isError"] is True
    assert (
        result["content"][0]["text"]
        == "Error executing tool list_matters: CosmoLex returned an unreadable response. Check the result in CosmoLex before retrying."
    )


def test_transport_failure_does_not_invite_blind_write_retry(monkeypatch, caplog):
    client = object.__new__(LCSClient)
    client.session = requests.Session()
    client._api_key = "test-placeholder"
    client._tokens = {"access_token": "test-placeholder"}
    monkeypatch.setattr(client, "_token_valid", lambda: True)

    def fail(*args, **kwargs):
        raise requests.Timeout(
            "person@example.invalid https://vendor.invalid/key/private"
        )

    monkeypatch.setattr(client.session, "request", fail)
    monkeypatch.setattr(server, "_c", lambda: client)
    with caplog.at_level(logging.INFO):
        result = _call("create_matter", {"fields_json": "{}"})
    assert result["isError"] is True
    assert (
        result["content"][0]["text"]
        == "Error executing tool create_matter: CosmoLex request did not complete. Check the result in CosmoLex before retrying."
    )
    assert "person@example.invalid" not in caplog.text
    assert "vendor.invalid" not in caplog.text
