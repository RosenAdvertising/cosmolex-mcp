#!/usr/bin/env python3
"""Cosmolex API client — ProfitSolv LCS ``/v1`` Integration API (scoped OAuth).

Auth: a scoped OAuth app (authorization-code grant once, then refresh-token
forever). There is **no password login**, so the MCP never trips CosmoLex's
single-session-per-user limit and never logs the user out of their browser.

  * One-time consent (browser, at setup): the user authorizes the integration and
    pastes back the ``code``; ``cosmolex-mcp-setup`` exchanges it for an
    ``access_token`` + ``refresh_token`` (see :func:`build_authorize_url` /
    :func:`exchange_code`).
  * Steady state: this client refreshes its own ``access_token`` with the
    ``refresh_token`` (a long-lived, static token, re-saved if the server ever
    rotates it) — headless, no browser, no password. On a ``401`` it refreshes once
    and retries. If the ``refresh_token`` is itself rejected, it raises asking the
    user to re-run setup (re-consent).

Data: ``{method} {API_BASE}/v1/{resource}[/{id}]`` with two headers —
``X-Api-Key: <app key>`` and ``X-User-Token: <access_token>``. List endpoints
return a paginated envelope ``{page,pageSize,totalCount,items,totalPages}``
(``documents`` returns a bare list); detail / create / update / delete use the
RESTful item route ``/v1/{resource}/{id}``.

Verified live 2026-06-28 against the CosmoLex sandbox firm 77 (OAuth host
``sandbox.cosmolex.com``; data host the ProfitSolv Azure app): the refresh-token
grant mints a fresh ``access_token`` (HTTP 200 — the no-logout property), ``users``
returns the real record (``totalCount`` 1), ``documents`` returns a real bare list
(6 rows), and ``matters``/``clients``/``contacts``/``time-entries``/``expense``/
``invoices``/``payments`` return HTTP 200 with an empty envelope (the sandbox firm
is otherwise blank). Coverage was confirmed identical to the verified Rocket Matter
``/v1`` rebuild (the SAME LCS API): ``transactions`` requires ``bankId``/``matterId``
("bankId is required when matterId is not provided."), ``codes`` requires
``matterId`` ("matterId is required."), ``text-shortcuts`` exists but this OAuth
app/user is not authorized (403), and ``banks``/``coa``/``firm``/``timekeepers``
are absent (404).

Server-side LIST filters are forwarded ONLY where /v1 honors them — clients
``name``/``displayName``, matters ``clientId``/``matterName``, time-entries
``matterId``, transactions/codes ``matterId`` (required); /v1 SILENTLY IGNORES
filters elsewhere, so those tools are pagination-only and never advertise a filter
that returns unfiltered data. This filter set and the create→read→update→delete
round-trips are INHERITED from the Rocket Matter live verification of this same /v1
API; the blank CosmoLex sandbox firm could not exercise filtered reads or write
round-trips directly (flagged UNVERIFIED-for-CosmoLex in the rebuild report).

COVERAGE: the LCS ``/v1`` API is narrower than the NextGen ``/api/v2`` set the
previous CosmoLex build used. Resources it does NOT expose (timekeepers, firm
summary, banks, chart of accounts, accounts-payable, lookups, document actions,
tasks, timers, calendar, tags, trust, rates, firm roles, tax/discount, phone
messages, internal chat, workflow, reports, recurring billing, matter templates,
court rules) are kept as **fail-loud stubs** via :meth:`_not_in_v1` — they raise a
clear "not in the LCS /v1 API" error instead of silently returning nothing, pending
Toby's keep/drop call. See the module ``COVERAGE_DELTA`` list and the wiki page
``Cosmolex MCP``.
"""

import json
import os
import time
from pathlib import Path
from urllib.parse import urlencode

import requests

from cosmolex_mcp import credentials

# Resolve credentials through the pluggable store (OS keyring -> env -> .env file).
# The LCS /v1 OAuth model needs the app's API key + the OAuth client_id/secret; the
# user/per-firm access is carried entirely by the cached OAuth tokens.
credentials.load_into_environ(
    [
        "COSMOLEX_API_KEY",
        "COSMOLEX_CLIENT_ID",
        "COSMOLEX_CLIENT_SECRET",
        "COSMOLEX_BASE_URL",
        "COSMOLEX_API_BASE_URL",
        "COSMOLEX_REDIRECT_URI",
    ]
)

# OAuth host — serves the consent (``/OAuth/authorize``) and token
# (``/api/ext/auth/token``) endpoints. CosmoLex sandbox = sandbox.cosmolex.com;
# production = law.cosmolex.com. Override with COSMOLEX_BASE_URL.
OAUTH_BASE = os.environ.get("COSMOLEX_BASE_URL", "https://sandbox.cosmolex.com")

# LCS Integration data host (the ProfitSolv Azure app). This is a DIFFERENT host
# from the OAuth host — the earlier "/v1 is dead on NextGen CosmoLex" misdiagnosis
# came from calling /v1 on the cosmolex.com product host (an empty-200 / 403
# catch-all), instead of this Azure data host. The default is the sandbox host; the
# production data host is provisioned per-firm and set via COSMOLEX_API_BASE_URL.
API_BASE = os.environ.get(
    "COSMOLEX_API_BASE_URL",
    "https://lcs-developer-api-profi-sandbox-gncndgfccdgxdtff.centralus-01.azurewebsites.net",
)

TOKEN_URL = f"{OAUTH_BASE}/api/ext/auth/token"
AUTHORIZE_URL = f"{OAUTH_BASE}/OAuth/authorize"

# Registered redirect URI for the OAuth app — a hard constant, NOT env-derived, so the
# setup wizard can detect a stored/overridden redirect that differs from what the app
# will actually accept (a mismatch breaks consent). The CosmoLex sandbox app registered
# ``https://localhost:8770/callback``; setup uses a manual copy-paste of the ``code``
# from the address bar (the browser lands on localhost:8770, which need not be served,
# and the ``code`` query param is copied back).
REGISTERED_REDIRECT_URI = "https://localhost:8770/callback"

# Effective redirect for building the consent URL: an explicit COSMOLEX_REDIRECT_URI
# override wins (for an app that registered a different redirect), else the registered
# constant above.
DEFAULT_REDIRECT_URI = (
    os.environ.get("COSMOLEX_REDIRECT_URI") or REGISTERED_REDIRECT_URI
)

CONFIG_DIR = Path.home() / ".cosmolex-mcp"
TOKEN_FILE = CONFIG_DIR / "tokens.json"

# Access tokens live ~30 min (expires_in 1799); refresh this many seconds early.
_EXPIRY_SKEW = 90

# Per-request timeout (seconds) for data calls — a stalled /v1 call must not hang
# the MCP tool indefinitely.
_HTTP_TIMEOUT = 30

# A JSON body carrying any of these keys (or ``success: false``) is an API
# error/problem envelope, not a record. Used on the 404 detail path to reject an
# error body that echoes an ``id``/``name`` so it is never mistaken for a real record
# (which :meth:`_update` would then merge + PUT). Deliberately broad there: a real
# record misjudged "not found" fails loudly, but an error envelope taken for a record
# corrupts data.
_ERROR_ENVELOPE_KEYS = (
    "error",
    "errors",
    "message",
    "detail",
    "title",
    "traceId",
    "exception",
)

# Tools whose capability the LCS /v1 API does not expose (kept as fail-loud stubs).
# Surfaced for Toby's keep/drop call — NOT silently dropped.
COVERAGE_DELTA = [
    "list_timekeepers (billable-time summary)",
    "get_firm_summary",
    "list_banks",
    "list_chart_of_accounts",
    "generate_invoice / list_billable_items / approve_invoice (the /api/v2 2-step billing flow)",
    "get_invoice_allocations",
    "document actions: get_document_default_app / get_document_download_url / "
    "get_document_upload_url / delete_document (/v1 documents is read-only list)",
    "Accounts Payable: list/get/create/update/delete bills, AP payments, vendors (12 tools)",
    "Lookups: all 17 (new-matter/contact/expense/invoice/time/transaction defaults, labels, suggestions)",
    "Codes: get_task_codes / get_activity_codes split (only the combined get_codes is in /v1)",
    "Text shortcuts (endpoint exists in /v1 but this OAuth app/user is not authorized -> 403)",
    "Not in /v1 at all: tasks, timers, calendar, tags, trust, rates, firm roles, "
    "tax/discount/surcharge/interest, phone messages, internal chat, workflow, "
    "reports, recurring billing, matter templates, court rules, global search",
]


def _load_tokens() -> dict:
    if TOKEN_FILE.exists():
        with open(TOKEN_FILE) as f:
            return json.load(f)
    return {}


def _save_tokens(tokens: dict) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    try:
        CONFIG_DIR.chmod(0o700)
    except OSError:
        pass
    with open(TOKEN_FILE, "w") as f:
        json.dump(tokens, f, indent=2)
    os.chmod(TOKEN_FILE, 0o600)


def _token_record(data: dict, prev: dict | None = None) -> dict:
    """Normalise a token-endpoint response into the cached token record.

    The ``refresh_token`` is long-lived and static (live-proven NOT to rotate), but
    this still re-saves whatever the token endpoint returns, so if the server ever
    starts rotating it the new value is captured; if a response omits it, the previous
    one is retained.
    """
    prev = prev or {}
    access = data.get("access_token")
    if not access:
        raise RuntimeError(f"Token response had no access_token: {str(data)[:200]}")
    return {
        "access_token": access,
        "refresh_token": data.get("refresh_token") or prev.get("refresh_token", ""),
        "expires_at": time.time() + int(data.get("expires_in", 1799)),
        "firm_id": data.get("firmId") or prev.get("firm_id"),
        "user_name": data.get("userName") or prev.get("user_name"),
    }


# ── OAuth setup helpers (used by cosmolex-mcp-setup) ─────────────────────────


def build_authorize_url(
    redirect_uri: str | None = None, client_id: str | None = None
) -> str:
    """Build the browser consent URL the user opens to authorize the integration."""
    client_id = client_id or os.environ.get("COSMOLEX_CLIENT_ID", "")
    redirect_uri = redirect_uri or DEFAULT_REDIRECT_URI
    query = urlencode(
        {
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
        }
    )
    return f"{AUTHORIZE_URL}?{query}"


def exchange_code(
    code: str,
    redirect_uri: str | None = None,
    client_id: str | None = None,
    client_secret: str | None = None,
    save: bool = True,
) -> dict:
    """Exchange an authorization ``code`` for tokens (one-time, at setup).

    POSTs ``grant_type=authorization_code`` to the token endpoint. The body matches
    the live-verified recipe (grant_type + client_id + client_secret + code) — the
    verified exchange did NOT send a ``redirect_uri``, so it is omitted here; the
    ``redirect_uri`` argument is kept only to build the consent URL. The long-lived
    ``refresh_token`` returned here is what the client then uses to refresh forever
    without a password login. Returns the cached token record.
    """
    client_id = client_id or os.environ.get("COSMOLEX_CLIENT_ID", "")
    client_secret = client_secret or os.environ.get("COSMOLEX_CLIENT_SECRET", "")
    if not (client_id and client_secret):
        raise RuntimeError(
            "COSMOLEX_CLIENT_ID and COSMOLEX_CLIENT_SECRET are required to "
            "exchange the authorization code. Run: cosmolex-mcp-setup"
        )
    resp = requests.post(
        TOKEN_URL,
        data={
            "grant_type": "authorization_code",
            "client_id": client_id,
            "client_secret": client_secret,
            "code": code,
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=30,
    )
    if not resp.ok:
        raise RuntimeError(
            f"Authorization-code exchange failed ({resp.status_code}): "
            f"{resp.text[:300]}"
        )
    tokens = _token_record(resp.json())
    if save:
        _save_tokens(tokens)
    return tokens


class LCSClient:
    """ProfitSolv LCS ``/v1`` Integration API client (scoped OAuth, no password).

    Construction loads the app key + OAuth client credentials and the cached tokens
    (from ``cosmolex-mcp-setup``). It does not hit the network — the first data
    call refreshes the access token if the cached one is stale.
    """

    def __init__(self):
        self.session = requests.Session()
        self.session.headers["Accept"] = "application/json"
        self._api_key = os.environ.get("COSMOLEX_API_KEY", "")
        self._client_id = os.environ.get("COSMOLEX_CLIENT_ID", "")
        self._client_secret = os.environ.get("COSMOLEX_CLIENT_SECRET", "")
        self._tokens = _load_tokens()
        if not self._tokens.get("access_token"):
            raise RuntimeError(
                "No CosmoLex OAuth tokens found. Run: cosmolex-mcp-setup"
            )
        if not self._api_key:
            raise RuntimeError(
                "COSMOLEX_API_KEY is not set. Run: cosmolex-mcp-setup"
            )

    # ── Auth ─────────────────────────────────────────────────────────────────

    def _token_valid(self) -> bool:
        return bool(self._tokens.get("access_token")) and (
            time.time() < self._tokens.get("expires_at", 0) - _EXPIRY_SKEW
        )

    def _refresh(self) -> None:
        """Get a fresh access token via the long-lived refresh token (no password)."""
        refresh_token = self._tokens.get("refresh_token")
        if not refresh_token:
            raise RuntimeError("No refresh_token cached. Run: cosmolex-mcp-setup")
        if not (self._client_id and self._client_secret):
            raise RuntimeError(
                "COSMOLEX_CLIENT_ID / COSMOLEX_CLIENT_SECRET not set. "
                "Run: cosmolex-mcp-setup"
            )
        resp = requests.post(
            TOKEN_URL,
            data={
                "grant_type": "refresh_token",
                "client_id": self._client_id,
                "client_secret": self._client_secret,
                "refresh_token": refresh_token,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=30,
        )
        if not resp.ok:
            raise RuntimeError(
                f"Token refresh failed ({resp.status_code}): {resp.text[:200]}. "
                "The refresh token may be revoked — re-run cosmolex-mcp-setup."
            )
        self._tokens = _token_record(resp.json(), self._tokens)
        _save_tokens(self._tokens)

    def _headers(self) -> dict:
        return {
            "X-Api-Key": self._api_key,
            "X-User-Token": self._tokens.get("access_token", ""),
        }

    # ── HTTP core ────────────────────────────────────────────────────────────

    def _url(self, path: str) -> str:
        return f"{API_BASE}/v1/{path.lstrip('/')}"

    def _send(
        self, method: str, path: str, params: dict | None = None, body=None
    ) -> requests.Response:
        """One ``/v1`` request with OAuth headers; refresh + retry once on 401.

        Refreshes the access token first if the cached one is stale; on a 401 from
        the server (token rejected early) it refreshes once and retries. Returns the
        raw ``Response`` so callers can treat 404 specially (see :meth:`_detail`).
        """
        if not self._token_valid():
            self._refresh()
        url = self._url(path)
        resp = self.session.request(
            method,
            url,
            params=params,
            json=body,
            headers=self._headers(),
            timeout=_HTTP_TIMEOUT,
        )
        if resp.status_code == 401:
            self._refresh()
            resp = self.session.request(
                method,
                url,
                params=params,
                json=body,
                headers=self._headers(),
                timeout=_HTTP_TIMEOUT,
            )
        return resp

    @staticmethod
    def _json_or_raise(resp: requests.Response):
        """Parse a JSON body, or raise a loud error on a non-2xx response."""
        if not resp.ok:
            raise RuntimeError(
                f"Cosmolex /v1 error {resp.status_code}: {resp.text[:400]}"
            )
        if not resp.content:
            return {}
        return resp.json()

    # ── Generic resource operations ──────────────────────────────────────────

    def _list(self, resource: str, page: int = 1, page_size: int = 25, **params):
        """GET a list endpoint -> the paginated envelope (or bare list for documents).

        ``page`` / ``pageSize`` are the live-confirmed pagination params; extra
        non-None query params (filters) pass through unchanged.
        """
        query: dict = {"page": page, "pageSize": page_size}
        query.update({k: v for k, v in params.items() if v is not None})
        return self._json_or_raise(self._send("GET", resource, params=query))

    @staticmethod
    def _is_error_envelope(data: dict) -> bool:
        """True if a JSON dict looks like an API error/problem envelope, not a record.

        Checks an explicit ``success: false`` plus the common error/problem-details
        keys (see ``_ERROR_ENVELOPE_KEYS``). Used to keep a 404 error body that echoes
        an ``id``/``name`` from being treated as a found record.
        """
        if data.get("success") is False:
            return True
        return any(data.get(k) for k in _ERROR_ENVELOPE_KEYS)

    def _detail(self, resource: str, record_id) -> dict | None:
        """GET a single record by id via the RESTful item route.

        Returns the record dict, or ``None`` if it does not exist. Tolerates a known
        server quirk where an existing record is occasionally returned with a 404
        status but a populated record body. The "found" path is strict: a 2xx with a
        dict body, or a 404 whose body is unmistakably the record — a truthy ``id``
        AND not an error envelope (see :meth:`_is_error_envelope`). A 404 / error
        envelope that merely echoes an ``id``/``name`` is treated as NOT found, and any
        OTHER non-2xx status (401/403/409/5xx) RAISES — so an error body is never
        mistaken for a record (which would otherwise let :meth:`_update` merge-and-PUT
        corrupt data). The bias is deliberate: a real record misjudged not-found fails
        loudly in :meth:`_update`; the inverse corrupts.
        """
        resp = self._send("GET", f"{resource}/{record_id}")
        data = None
        if resp.content:
            try:
                data = resp.json()
            except ValueError:
                data = None
        if resp.ok:
            return data if isinstance(data, dict) else None
        if resp.status_code == 404:
            # Known quirk: an existing record is occasionally returned WITH a 404
            # status but a full record body. Accept that ONLY when the body is a real
            # record — a truthy ``id`` and NOT an error envelope — so a 404 error body
            # that echoes an id/name is treated as not-found.
            if (
                isinstance(data, dict)
                and data.get("id")
                and not self._is_error_envelope(data)
            ):
                return data
            return None
        raise RuntimeError(
            f"Cosmolex /v1 error {resp.status_code}: {resp.text[:400]}"
        )

    def _create(self, resource: str, body: dict) -> dict:
        """POST to a collection -> the created record (201)."""
        return self._json_or_raise(self._send("POST", resource, body=body))

    def _update(
        self, resource: str, record_id, fields: dict, method: str = "PUT"
    ) -> dict:
        """Update via full-record merge: GET the record, overlay the caller's
        changed fields, and send the WHOLE record back.

        The /v1 update verbs reject a partial body (a partial client PUT returns
        ``400 "Name cannot be empty"``), so the current record must be merged in.
        ``method`` is ``PUT`` for most resources, ``PATCH`` for invoices.
        """
        current = self._detail(resource, record_id)
        if current is None:
            raise RuntimeError(f"{resource} {record_id} not found; cannot update.")
        merged = {**current, **fields}
        return self._json_or_raise(
            self._send(method, f"{resource}/{record_id}", body=merged)
        )

    def _delete(self, resource: str, record_id) -> dict:
        """DELETE a record by id.

        A 2xx with no body (the common 204) is an unambiguous success. Some /v1 delete
        routes instead return a 200 whose BODY reports the real outcome — a
        ``{"success": false, ...}`` (or an ``error``/``errors`` payload) there is a
        FAILURE despite the 2xx. The body is read so that is surfaced as an error
        (Rule 12 — never a false success) rather than reported as deleted; only a body
        that does not contradict success returns ``{"success": True}``.
        """
        resp = self._send("DELETE", f"{resource}/{record_id}")
        if not resp.ok:
            raise RuntimeError(
                f"Cosmolex /v1 error {resp.status_code}: {resp.text[:400]}"
            )
        if not resp.content:
            return {"success": True}
        try:
            data = resp.json()
        except ValueError:
            # A 2xx with a non-JSON body (e.g. empty string / plain text) = success.
            return {"success": True}
        if isinstance(data, dict) and (
            data.get("success") is False
            or (
                data.get("success") is None
                and (data.get("error") or data.get("errors"))
            )
        ):
            raise RuntimeError(
                f"Cosmolex /v1 delete reported failure despite HTTP "
                f"{resp.status_code}: {str(data)[:400]}"
            )
        return {"success": True}

    def _not_in_v1(self, capability: str) -> RuntimeError:
        """Standard fail-loud error for a capability the LCS /v1 API lacks.

        Never returns a false success — the tool raises so the gap is visible
        (Rule 12). Kept registered for Toby's keep/drop call; see ``COVERAGE_DELTA``.
        """
        return RuntimeError(
            f"'{capability}' is not available in the ProfitSolv LCS /v1 Integration "
            "API (the scoped-OAuth data API this MCP uses). It existed on the legacy "
            "/api/v2 session API, which trips CosmoLex's single-session limit "
            "and logs the user out — so it was intentionally dropped. This tool fails "
            "loudly instead of reporting a false success."
        )

    # ═════════════════════════════ Matters ══════════════════════════════════

    def list_matters(
        self,
        page: int = 1,
        page_size: int = 25,
        client_id: str | None = None,
        matter_name: str | None = None,
    ):
        """List matters (``GET /v1/matters``) -> paginated envelope.

        ``client_id`` and ``matter_name`` are the ONLY server-side filters /v1 honors
        for matters (verified live). Other narrowing (active/owner/free-text) is not
        applied by /v1, so it is not offered here — passing it would be silently
        ignored and return unfiltered results.
        """
        return self._list(
            "matters",
            page=page,
            page_size=page_size,
            clientId=client_id,
            matterName=matter_name,
        )

    def get_matter(self, matter_id: str) -> dict | None:
        return self._detail("matters", matter_id)

    def create_matter(self, **fields) -> dict:
        return self._create("matters", fields)

    def update_matter(self, matter_id: str, **fields) -> dict:
        return self._update("matters", matter_id, fields)

    def delete_matter(self, matter_id: str) -> dict:
        return self._delete("matters", matter_id)

    # ═════════════════════════════ Clients ══════════════════════════════════

    def list_clients(
        self,
        page: int = 1,
        page_size: int = 25,
        name: str | None = None,
        display_name: str | None = None,
    ):
        """List clients (``GET /v1/clients``) -> paginated envelope.

        ``name`` and ``display_name`` are the ONLY server-side filters /v1 honors for
        clients (verified live); other params (active, free-text search) are silently
        ignored by /v1 and so are not offered here.
        """
        return self._list(
            "clients",
            page=page,
            page_size=page_size,
            name=name,
            displayName=display_name,
        )

    def get_client(self, client_id: str) -> dict | None:
        return self._detail("clients", client_id)

    def create_client(self, **fields) -> dict:
        """Create a client (``POST /v1/clients``). Only ``name`` is required
        (verified live); other fields match the read shape."""
        return self._create("clients", fields)

    def update_client(self, client_id: str, **fields) -> dict:
        return self._update("clients", client_id, fields)

    def delete_client(self, client_id: str) -> dict:
        return self._delete("clients", client_id)

    # ═════════════════════════════ Contacts ═════════════════════════════════

    def list_contacts(self, page: int = 1, page_size: int = 25):
        """List contacts (``GET /v1/contacts``) -> paginated envelope."""
        return self._list("contacts", page=page, page_size=page_size)

    def get_contact(self, contact_id: str) -> dict | None:
        return self._detail("contacts", contact_id)

    def create_contact(self, **fields) -> dict:
        return self._create("contacts", fields)

    def update_contact(self, contact_id: str, **fields) -> dict:
        return self._update("contacts", contact_id, fields)

    def delete_contact(self, contact_id: str) -> dict:
        return self._delete("contacts", contact_id)

    # ════════════════════════════ Time Entries ══════════════════════════════

    def list_time_entries(
        self,
        matter_id: str | None = None,
        page: int = 1,
        page_size: int = 25,
    ):
        """List time entries (``GET /v1/time-entries``) -> paginated envelope.

        ``matter_id`` is the only server-side filter /v1 honors here (verified live).
        Other narrowing (rate type, billing status, card status) is NOT applied by
        /v1, so it is not offered — it would be silently ignored.
        """
        return self._list(
            "time-entries", page=page, page_size=page_size, matterId=matter_id
        )

    def get_time_entry(self, time_entry_id: str) -> dict | None:
        return self._detail("time-entries", time_entry_id)

    def create_time_entry(self, **fields) -> dict:
        return self._create("time-entries", fields)

    def update_time_entry(self, time_entry_id: str, **fields) -> dict:
        return self._update("time-entries", time_entry_id, fields)

    def delete_time_entry(self, time_entry_id: str) -> dict:
        return self._delete("time-entries", time_entry_id)

    # ═════════════════════════════ Expenses ═════════════════════════════════
    # Note the SINGULAR /v1 path: ``/v1/expense`` (plural ``/v1/expenses`` 404s).

    def list_expenses(self, page: int = 1, page_size: int = 25):
        """List expense cards (``GET /v1/expense``) -> paginated envelope.

        /v1 honors NO server-side filters on expense — even ``matterId`` is silently
        ignored (verified live: it returns the full firm-wide list), unlike
        time-entries. So no filter is offered; this is a firm-wide expense list.
        """
        return self._list("expense", page=page, page_size=page_size)

    def get_expense(self, expense_id: str) -> dict | None:
        return self._detail("expense", expense_id)

    def create_expense(self, **fields) -> dict:
        return self._create("expense", fields)

    def update_expense(self, expense_id: str, **fields) -> dict:
        return self._update("expense", expense_id, fields)

    def delete_expense(self, expense_id: str) -> dict:
        return self._delete("expense", expense_id)

    # ═════════════════════════════ Invoices ═════════════════════════════════
    # Update verb is PATCH (not PUT) for invoices, per the live OPTIONS probe.

    def list_invoices(self, page: int = 1, page_size: int = 25):
        """List invoices (``GET /v1/invoices``) -> paginated envelope."""
        return self._list("invoices", page=page, page_size=page_size)

    def get_invoice(self, invoice_id: str) -> dict | None:
        return self._detail("invoices", invoice_id)

    def create_invoice(self, **fields) -> dict:
        """Create an invoice (``POST /v1/invoices``). The required body has not been
        exercised live (the dev firm has no billable items); the caller supplies the
        fields and the API's 400 validation names any that are missing."""
        return self._create("invoices", fields)

    def update_invoice(self, invoice_id: str, **fields) -> dict:
        return self._update("invoices", invoice_id, fields, method="PATCH")

    def delete_invoice(self, invoice_id: str) -> dict:
        return self._delete("invoices", invoice_id)

    def generate_invoice(self, *args, **kwargs) -> dict:
        raise self._not_in_v1(
            "generate_invoice (the /api/v2 two-step billable-items + challenge-token "
            "flow). Use create_invoice with the /v1 invoice body instead."
        )

    def list_billable_items(self, *args, **kwargs) -> dict:
        raise self._not_in_v1(
            "list_billable_items (the /api/v2 challenge-token preview)"
        )

    def approve_invoice(self, *args, **kwargs) -> dict:
        raise self._not_in_v1("approve_invoice")

    # ═════════════════════════════ Payments ═════════════════════════════════
    # /v1/payments supports GET (list) + POST (create); no item detail route.

    def list_payments(self, page: int = 1, page_size: int = 25):
        """List payments (``GET /v1/payments``) -> paginated envelope."""
        return self._list("payments", page=page, page_size=page_size)

    def create_payment(self, **fields) -> dict:
        """Record a payment (``POST /v1/payments``). Body is caller-supplied; the
        API names any missing required fields via a 400 validation error."""
        return self._create("payments", fields)

    def get_invoice_allocations(self, *args, **kwargs) -> dict:
        raise self._not_in_v1("get_invoice_allocations")

    # ═══════════════════════════ Transactions ═══════════════════════════════

    def list_transactions(
        self,
        matter_id: str | None = None,
        bank_id: str | None = None,
        page: int = 1,
        page_size: int = 25,
    ):
        """List bank transactions (``GET /v1/transactions``).

        The /v1 transactions endpoint has NO firm-wide listing — it requires a
        ``matter_id`` or a ``bank_id`` (``bankId is required when matterId is not
        provided``). The /v1 API exposes no bank-enumeration endpoint, so a
        ``bank_id`` must come from the CosmoLex UI.
        """
        if not (matter_id or bank_id):
            raise RuntimeError(
                "list_transactions requires matter_id or bank_id — the LCS /v1 "
                "transactions endpoint has no firm-wide listing, and /v1 exposes no "
                "bank-enumeration endpoint (get a bankId from the CosmoLex UI)."
            )
        return self._list(
            "transactions",
            page=page,
            page_size=page_size,
            matterId=matter_id,
            bankId=bank_id,
        )

    def get_transaction(self, transaction_id: str) -> dict | None:
        return self._detail("transactions", transaction_id)

    def create_transaction(self, **fields) -> dict:
        """Create a bank transaction (``POST /v1/transactions``). Body caller-supplied
        (needs a ``bankId`` — see :meth:`list_transactions` on bank enumeration)."""
        return self._create("transactions", fields)

    def update_transaction(self, transaction_id: str, **fields) -> dict:
        return self._update("transactions", transaction_id, fields)

    def delete_transaction(self, transaction_id: str) -> dict:
        return self._delete("transactions", transaction_id)

    def list_banks(self, *args, **kwargs) -> dict:
        raise self._not_in_v1("list_banks (bank enumeration)")

    def list_chart_of_accounts(self, *args, **kwargs) -> dict:
        raise self._not_in_v1("list_chart_of_accounts")

    # ═════════════════════════════ Documents ════════════════════════════════
    # /v1/documents is read-only (GET list, bare array; no item route).

    def list_documents(self, page: int = 1, page_size: int = 25):
        """List documents (``GET /v1/documents``) -> a list (firm-wide).

        /v1 documents is read-only and exposes no confirmed server-side filter (the
        endpoint returned an unfiltered list in testing), so no ``matter_id`` filter
        is offered — it would be silently ignored.
        """
        return self._list("documents", page=page, page_size=page_size)

    def get_document_default_app(self, *a, **k) -> dict:
        raise self._not_in_v1("get_document_default_app")

    def get_document_download_url(self, *a, **k) -> dict:
        raise self._not_in_v1("get_document_download_url")

    def get_document_upload_url(self, *a, **k) -> dict:
        raise self._not_in_v1("get_document_upload_url")

    def delete_document(self, *a, **k) -> dict:
        raise self._not_in_v1("delete_document (/v1 documents is read-only)")

    # ═══════════════════════════ Users / Firm ═══════════════════════════════
    # /v1/users is read-only (GET list + GET detail). Users ARE the firm's
    # timekeepers (each carries a defaultRate + roles).

    def list_users(self, page: int = 1, page_size: int = 25):
        """List users / timekeepers (``GET /v1/users``) -> paginated envelope."""
        return self._list("users", page=page, page_size=page_size)

    def get_user(self, user_id: int) -> dict | None:
        return self._detail("users", user_id)

    def list_timekeepers(self, *args, **kwargs) -> dict:
        raise self._not_in_v1(
            "list_timekeepers (billable-time summary). The people list is in "
            "list_users; the per-timekeeper billable/non-billable totals are not in /v1."
        )

    def get_firm_summary(self, *args, **kwargs) -> dict:
        raise self._not_in_v1("get_firm_summary (firm financial summary)")

    # ═══════════════════════════ Codes (UTBMS) ══════════════════════════════

    def get_codes(self, matter_id: str) -> dict:
        """UTBMS codes for a matter (``GET /v1/codes?matterId=``). ``matter_id`` is
        required (the endpoint 400s without it)."""
        return self._json_or_raise(
            self._send("GET", "codes", params={"matterId": matter_id})
        )

    def get_task_codes(self, *args, **kwargs) -> dict:
        raise self._not_in_v1(
            "get_task_codes (task/activity split). /v1 exposes only the combined "
            "get_codes(matter_id)."
        )

    def get_activity_codes(self, *args, **kwargs) -> dict:
        raise self._not_in_v1(
            "get_activity_codes (task/activity split). /v1 exposes only the combined "
            "get_codes(matter_id)."
        )

    # ═══════════════════════════ Text Shortcuts ═════════════════════════════
    # The endpoint exists in /v1 but this OAuth app/user is not authorized (403).

    def list_text_shortcuts(self, page: int = 1, page_size: int = 25):
        """List text shortcuts (``GET /v1/text-shortcuts``).

        The endpoint exists in /v1 but the scoped OAuth app/user is currently not
        authorized for it (403). Kept live (not stubbed) so it works automatically
        if the scope is later granted; raises the API's 403 until then.
        """
        return self._list("text-shortcuts", page=page, page_size=page_size)

    def get_text_shortcut(self, shortcut_id: int) -> dict | None:
        return self._detail("text-shortcuts", shortcut_id)

    # ═══════════════════════════════ Lookups ════════════════════════════════
    # None of the legacy lookup endpoints exist in the LCS /v1 API (all 404).

    def get_new_matter_defaults(self, *a, **k) -> dict:
        raise self._not_in_v1("get_new_matter_defaults (lookups)")

    def get_new_matter_definition(self, *a, **k) -> dict:
        raise self._not_in_v1("get_new_matter_definition (lookups)")

    def get_ebilling_defaults(self, *a, **k) -> dict:
        raise self._not_in_v1("get_ebilling_defaults (lookups)")

    def get_matter_type_workflow(self, *a, **k) -> dict:
        raise self._not_in_v1("get_matter_type_workflow (lookups)")

    def get_client_labels(self, *a, **k) -> dict:
        raise self._not_in_v1("get_client_labels (lookups)")

    def get_matter_labels(self, *a, **k) -> dict:
        raise self._not_in_v1("get_matter_labels (lookups)")

    def get_client_suggestions(self, *a, **k) -> dict:
        raise self._not_in_v1("get_client_suggestions (lookups)")

    def get_new_contact_defaults(self, *a, **k) -> dict:
        raise self._not_in_v1("get_new_contact_defaults (lookups)")

    def get_expense_lookups(self, *a, **k) -> dict:
        raise self._not_in_v1("get_expense_lookups (lookups)")

    def get_new_expense_lookups(self, *a, **k) -> dict:
        raise self._not_in_v1("get_new_expense_lookups (lookups)")

    def get_invoice_lookups(self, *a, **k) -> dict:
        raise self._not_in_v1("get_invoice_lookups (lookups)")

    def get_new_invoice_lookups(self, *a, **k) -> dict:
        raise self._not_in_v1("get_new_invoice_lookups (lookups)")

    def get_invoice_payment_lookups(self, *a, **k) -> dict:
        raise self._not_in_v1("get_invoice_payment_lookups (lookups)")

    def get_time_entry_lookups(self, *a, **k) -> dict:
        raise self._not_in_v1("get_time_entry_lookups (lookups)")

    def get_time_grid_lookups(self, *a, **k) -> dict:
        raise self._not_in_v1("get_time_grid_lookups (lookups)")

    def get_transaction_lookups(self, *a, **k) -> dict:
        raise self._not_in_v1("get_transaction_lookups (lookups)")

    def get_hard_cost_expense_lookups(self, *a, **k) -> dict:
        raise self._not_in_v1("get_hard_cost_expense_lookups (lookups)")

    # ═══════════════════════════ Accounts Payable ═══════════════════════════
    # No AP endpoints exist in the LCS /v1 API (all 404).

    def list_ap_bills(self, *a, **k) -> dict:
        raise self._not_in_v1("list_ap_bills (Accounts Payable)")

    def get_ap_bill(self, *a, **k) -> dict:
        raise self._not_in_v1("get_ap_bill (Accounts Payable)")

    def create_ap_bill(self, *a, **k) -> dict:
        raise self._not_in_v1("create_ap_bill (Accounts Payable)")

    def update_ap_bill(self, *a, **k) -> dict:
        raise self._not_in_v1("update_ap_bill (Accounts Payable)")

    def delete_ap_bill(self, *a, **k) -> dict:
        raise self._not_in_v1("delete_ap_bill (Accounts Payable)")

    def list_ap_payments(self, *a, **k) -> dict:
        raise self._not_in_v1("list_ap_payments (Accounts Payable)")

    def create_ap_payment(self, *a, **k) -> dict:
        raise self._not_in_v1("create_ap_payment (Accounts Payable)")

    def get_ap_payment_status(self, *a, **k) -> dict:
        raise self._not_in_v1("get_ap_payment_status (Accounts Payable)")

    def list_ap_vendors(self, *a, **k) -> dict:
        raise self._not_in_v1("list_ap_vendors (Accounts Payable)")

    def get_ap_vendor(self, *a, **k) -> dict:
        raise self._not_in_v1("get_ap_vendor (Accounts Payable)")

    def create_ap_vendor(self, *a, **k) -> dict:
        raise self._not_in_v1("create_ap_vendor (Accounts Payable)")

    def update_ap_vendor(self, *a, **k) -> dict:
        raise self._not_in_v1("update_ap_vendor (Accounts Payable)")
