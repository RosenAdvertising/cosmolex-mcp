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
    LCSClient,
    MissingConfiguration,
    RateLimited,
    RecordNotFound,
    VendorHTTPFailure,
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
                "CosmoLex authorization expired or was rejected. Re-run cosmolex-mcp-setup to reconnect."
            ),
            "Error executing tool list_matters: CosmoLex authorization expired or was rejected. Re-run cosmolex-mcp-setup to reconnect.",
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


def test_public_call_tool_preserves_safe_errors_without_transport(monkeypatch):
    monkeypatch.setattr(server, "_c", lambda: _FailedClient(RateLimited(120)))
    result = asyncio.run(server.mcp.call_tool("list_matters", {}))
    assert result.is_error is True
    assert result.content[0].text == (
        "Error executing tool list_matters: CosmoLex rate limit reached. Retry after 120 seconds."
    )


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
            "CosmoLex authorization expired or was rejected. Re-run cosmolex-mcp-setup to reconnect.",
        ),
        (
            403,
            {"detail": "Private Person person@example.invalid"},
            None,
            "CosmoLex access denied: the connected account lacks permission for this action (or the authorization expired; re-run cosmolex-mcp-setup if so).",
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
    post_calls = []
    monkeypatch.setattr(
        client_module.requests,
        "post",
        lambda *args, **kwargs: post_calls.append(kwargs) or response,
    )
    monkeypatch.setattr(server, "_c", lambda: client)
    result = _call()
    assert result["isError"] is True
    assert post_calls[0]["timeout"] == 30
    assert (
        result["content"][0]["text"]
        == "Error executing tool list_matters: CosmoLex authorization expired or was rejected. Re-run cosmolex-mcp-setup to reconnect."
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
        == "Error executing tool create_matter: CosmoLex request outcome is unknown. Check whether the operation completed in CosmoLex before retrying."
    )
    assert "person@example.invalid" not in caplog.text
    assert "vendor.invalid" not in caplog.text


@pytest.mark.parametrize(
    ("tool", "error_type", "expected"),
    [
        (
            "list_matters",
            requests.Timeout,
            "CosmoLex request did not complete. Check connectivity and retry.",
        ),
        (
            "list_matters",
            requests.ConnectionError,
            "CosmoLex request did not complete. Check connectivity and retry.",
        ),
        (
            "create_matter",
            requests.Timeout,
            "CosmoLex request outcome is unknown. Check whether the operation completed in CosmoLex before retrying.",
        ),
        (
            "create_matter",
            requests.ConnectionError,
            "CosmoLex request outcome is unknown. Check whether the operation completed in CosmoLex before retrying.",
        ),
    ],
)
def test_timeout_and_connection_errors_are_safe_by_operation_kind(
    monkeypatch, tool, error_type, expected
):
    client = object.__new__(LCSClient)
    client.session = requests.Session()
    client._api_key = "test-placeholder"
    client._tokens = {"access_token": "test-placeholder"}
    monkeypatch.setattr(client, "_token_valid", lambda: True)

    def fail(*args, **kwargs):
        raise error_type("private host https://private.invalid/key")

    monkeypatch.setattr(client.session, "request", fail)
    monkeypatch.setattr(server, "_c", lambda: client)
    args = {"fields_json": "{}"} if tool == "create_matter" else {}
    result = _call(tool, args)
    assert result["isError"] is True
    assert result["content"][0]["text"] == f"Error executing tool {tool}: {expected}"
    assert "private.invalid" not in str(result)


def test_403_has_permission_guidance_and_401_has_reconnect_guidance(monkeypatch):
    from tests.test_canary_fixes import _client_with_response, _response

    client, _ = _client_with_response([])
    for code, detail in (
        (401, "authorization expired or was rejected"),
        (403, "access denied: the connected account lacks permission"),
    ):
        response = _response({"detail": "private user secret"})
        response.status_code = code
        monkeypatch.setattr(
            client, "_send", lambda *args, _resp=response, **kwargs: _resp
        )
        monkeypatch.setattr(server, "_c", lambda: client)
        result = _call()
        assert result["isError"] is True
        text = result["content"][0]["text"]
        assert detail in text
        assert "private user secret" not in text


def test_id_path_segment_is_validated_before_requests_prepares_url(monkeypatch):
    client = object.__new__(LCSClient)
    client.session = requests.Session()
    client._api_key = "test-placeholder"
    client._tokens = {"access_token": "test-placeholder"}
    monkeypatch.setattr(client, "_token_valid", lambda: True)
    captured = {}

    def request(method, url, **kwargs):
        request_kwargs = {
            key: value for key, value in kwargs.items() if key != "timeout"
        }
        captured["url"] = requests.Request(method, url, **request_kwargs).prepare().url
        response = requests.Response()
        response.status_code = 200
        response._content = b'{"id":"sentinel"}'
        return response

    monkeypatch.setattr(client.session, "request", request)
    client._detail("matters", "normal-id")
    assert captured["url"].endswith("/matters/normal-id")


def test_http_call_timeout_and_no_retry_after_sleep(monkeypatch):
    client = object.__new__(LCSClient)
    client.session = requests.Session()
    client._api_key = "test-placeholder"
    client._tokens = {"access_token": "test-placeholder"}
    monkeypatch.setattr(client, "_token_valid", lambda: True)
    calls = []
    response = requests.Response()
    response.status_code = 429
    response.headers["Retry-After"] = "120"
    response._content = b"{}"
    monkeypatch.setattr(
        client_module.time, "sleep", lambda _: pytest.fail("unexpected sleep")
    )
    monkeypatch.setattr(
        client.session,
        "request",
        lambda *args, **kwargs: calls.append(kwargs) or response,
    )
    monkeypatch.setattr(server, "_c", lambda: client)
    result = _call()
    assert result["isError"] is True
    assert "Retry after 120 seconds." in result["content"][0]["text"]
    assert len(calls) == 1
    assert calls[0]["timeout"] == client_module._HTTP_TIMEOUT


def test_http_200_error_envelope_is_not_reported_as_success(monkeypatch):
    from tests.test_canary_fixes import _client_with_response, _response

    client, _ = _client_with_response([])
    response = _response({"success": False, "detail": "private vendor text"})
    monkeypatch.setattr(client, "_send", lambda *args, **kwargs: response)
    monkeypatch.setattr(server, "_c", lambda: client)
    result = _call("create_matter", {"fields_json": "{}"})
    assert result["isError"] is True
    assert result["content"][0]["text"] == (
        "Error executing tool create_matter: CosmoLex returned HTTP 200: vendor service error."
    )
    assert "private vendor text" not in str(result)


def test_resource_failure_boundary_keeps_client_text_and_logs_safe(monkeypatch, caplog):
    class ResourceClient:
        def list_users(self, **kwargs):
            raise MissingConfiguration(
                "No CosmoLex connection is configured. Run setup safely."
            )

    monkeypatch.setattr(server, "_c", lambda: ResourceClient())
    with caplog.at_level(logging.INFO):
        response = asyncio.run(
            _post_modern("resources/read", {"uri": "cosmolex://users"})
        )
    text = response.text
    assert "Run setup safely." in text
    assert "unexpected_exception" not in caplog.text
    assert "MissingConfiguration" not in caplog.text


@pytest.mark.parametrize("error_type", [requests.Timeout, requests.ConnectionError])
def test_oauth_post_transport_failure_has_unknown_outcome_at_dispatch(
    monkeypatch, error_type
):
    client = object.__new__(LCSClient)
    client._tokens = {"refresh_token": "fake"}
    client._client_id = "fake"
    client._client_secret = "fake"
    calls = []

    def fail(*args, **kwargs):
        calls.append(kwargs)
        raise error_type("PRIVATE_SENTINEL")

    monkeypatch.setattr(client_module.requests, "post", fail)
    monkeypatch.setattr(server, "_c", lambda: client)
    result = _call()
    assert result["isError"] is True
    assert (
        result["content"][0]["text"]
        == "Error executing tool list_matters: CosmoLex authorization request outcome is unknown. Check whether authorization completed before retrying."
    )
    assert len(calls) == 1 and calls[0]["timeout"] == 30


def test_authorization_code_transport_failure_is_safe(monkeypatch):
    from cosmolex_mcp.client import TransportFailure

    def fail(*args, **kwargs):
        assert kwargs["timeout"] == 30
        raise requests.Timeout("PRIVATE_SENTINEL")

    monkeypatch.setattr(client_module.requests, "post", fail)
    with pytest.raises(TransportFailure) as caught:
        client_module.exchange_code(
            "fake", client_id="fake", client_secret="fake", save=False
        )
    assert (
        str(caught.value)
        == "CosmoLex authorization request outcome is unknown. Check whether authorization completed before retrying."
    )


@pytest.mark.parametrize("operation", ["list", "detail"])
def test_successful_records_may_contain_title_and_message(monkeypatch, operation):
    from tests.test_canary_fixes import _response

    record = {"id": "record", "title": "Case title", "message": "Record note"}
    response = _response(record)
    client = object.__new__(LCSClient)
    monkeypatch.setattr(client, "_send", lambda *a, **k: response)
    result = (
        client._detail("matters", "record")
        if operation == "detail"
        else client._json_or_raise(response)
    )
    assert result == record


@pytest.mark.parametrize("tool", ["get_matter", "delete_matter"])
def test_explicit_false_response_is_an_error_for_detail_and_delete(monkeypatch, tool):
    from tests.test_canary_fixes import _response

    response = _response({"success": False, "detail": "PRIVATE_SENTINEL"})
    client = object.__new__(LCSClient)
    monkeypatch.setattr(client, "_send", lambda *a, **k: response)
    monkeypatch.setattr(server, "_c", lambda: client)
    result = _call(tool, {"matter_id": "normal-id"})
    assert result["isError"] is True
    assert (
        result["content"][0]["text"]
        == f"Error executing tool {tool}: CosmoLex returned HTTP 200: vendor service error."
    )
