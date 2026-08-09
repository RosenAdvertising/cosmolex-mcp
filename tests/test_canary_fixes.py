"""Fleet-canary regressions for list safety and rejection logging."""

from __future__ import annotations

import json
import logging
from typing import Any

import pytest
import requests

from cosmolex_mcp import client as client_module
from cosmolex_mcp import server
from cosmolex_mcp.client import LCSClient


def _response(payload: Any) -> requests.Response:
    response = requests.Response()
    response.status_code = 200
    response._content = json.dumps(payload).encode()
    response.headers["Content-Type"] = "application/json"
    return response


def _client_with_response(
    payload: Any,
) -> tuple[LCSClient, list[dict[str, Any]]]:
    client = object.__new__(LCSClient)
    calls: list[dict[str, Any]] = []

    def send(
        method: str,
        path: str,
        params: dict[str, Any] | None = None,
        body: Any = None,
    ) -> requests.Response:
        calls.append({"method": method, "path": path, "params": params, "body": body})
        return _response(payload)

    client._send = send  # type: ignore[method-assign]
    return client, calls


def test_bare_list_is_single_request_and_never_exceeds_page_size() -> None:
    client, calls = _client_with_response([{"id": n} for n in range(8)])

    result = client._list("documents", page=2, page_size=3)

    assert result == [{"id": 0}, {"id": 1}, {"id": 2}]
    assert len(calls) == 1
    assert calls[0]["params"] == {"page": 2, "pageSize": 3}


def test_envelope_items_are_defensively_capped_and_filters_are_preserved() -> None:
    payload = {
        "page": 1,
        "pageSize": 99,
        "totalCount": 8,
        "items": [{"id": n} for n in range(8)],
    }
    client, calls = _client_with_response(payload)

    result = client._list("matters", page_size=2, clientId="client-id")

    assert len(result["items"]) == 2
    assert result["totalCount"] == 8
    assert len(calls) == 1
    assert calls[0]["params"] == {
        "page": 1,
        "pageSize": 2,
        "clientId": "client-id",
    }


@pytest.mark.parametrize("page,page_size", [(0, 25), (1, 0), (1, 201)])
def test_direct_list_bounds_reject_with_pii_free_reason_log(
    caplog: pytest.LogCaptureFixture,
    page: int,
    page_size: int,
) -> None:
    client, calls = _client_with_response([])

    with caplog.at_level(logging.WARNING), pytest.raises(ValueError):
        client._list("documents", page=page, page_size=page_size)

    assert calls == []
    assert "list_request_rejected reason=" in caplog.text
    assert "email" not in caplog.text.lower()
    assert "name=" not in caplog.text.lower()


def test_sensitive_token_response_is_not_copied_to_error_or_log(
    caplog: pytest.LogCaptureFixture,
) -> None:
    sensitive = "sensitive-refresh-value"
    person = "person@example.test"

    with caplog.at_level(logging.WARNING), pytest.raises(
        RuntimeError,
        match="^Token response had no access_token$",
    ) as exc_info:
        client_module._token_record(
            {"refresh_token": sensitive, "userName": person}
        )

    combined = caplog.text + str(exc_info.value)
    assert "oauth_token_response_rejected reason=missing_access_token" in combined
    assert sensitive not in combined
    assert person not in combined


def test_fields_validation_and_transaction_guard_emit_pii_free_reason_logs(
    caplog: pytest.LogCaptureFixture,
) -> None:
    person = "person@example.test"
    with caplog.at_level(logging.WARNING):
        with pytest.raises(ValueError, match="must be a JSON object"):
            server._fields(json.dumps([person]))
        with pytest.raises(RuntimeError, match="requires matter_id or bank_id"):
            object.__new__(LCSClient).list_transactions()

    assert "tool_input_rejected reason=fields_json_not_object" in caplog.text
    assert "list_request_rejected reason=missing_transaction_scope" in caplog.text
    assert person not in caplog.text
