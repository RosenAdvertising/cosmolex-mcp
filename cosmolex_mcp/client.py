#!/usr/bin/env python3
"""CosmoLex API client (NextGen).

Auth: NextGen session login (username + password). NextGen CosmoLex accounts do
NOT serve the legacy ProfitSolv LCS ``/v1/`` gateway (it empty-200s / 403s and
returns no real data) — real data comes from the ``/api/v2/`` REST API, reached
with a browser-style session login rather than an ApiKey/OAuth integration token.

Login flow (``POST {BASE_URL}/api/ext/auth/token``, grant_type=password):
  * Prime cookies with ``GET /login``.
  * POST the password grant with browser headers (User-Agent, X-Requested-With,
    Referer) — without them CosmoLex falsely returns 401.
  * The returned ``access_token`` is sent as the ``a_t`` COOKIE (not a Bearer
    header) on all subsequent ``/api/v2/{resource}`` data calls.
  * On a 401 (or a 400 wrapping ``{"httpErrorType":401}`` / ``{"login":false}``)
    the client re-runs the login. Tokens are cached at
    ``~/.cosmolex-mcp/tokens.json`` (chmod 0600).

The PUBLIC login client_id ``4bfde53b970545e6b6a2d7f7ab55a957`` is SHARED across
ProfitSolv NextGen (same constant Rocket Matter uses) — it is not a secret and
not the portal ``ci-`` integration key (that key mints a token but ``/api/v2``
rejects it with ``"login":false``).

Data query syntax for ``GET /api/v2/{resource}``:
  ``?fields=a,b,c`` (required) and optional ``&active=eq|true`` ``&top=N``
  ``&skip=N`` ``&sortInfo=field:desc``. To discover valid fields per resource,
  GET ``/api/v2/resourcedef/{resource}``. An empty list ``[]`` is valid data
  (the sandbox is a blank account), not a failure. Note ``active`` is a FILTER on
  CosmoLex (``active=eq|true``), NOT a readable field — do not request it in
  ``fields``.

READ COVERAGE (all on ``/api/v2``, verified live 2026-06-21): the list reads
(``list_clients``/``list_matters``/``list_contacts``/``list_time_entries``/
``list_expenses``/``list_invoices``/``list_payments``/``list_transactions``/
``list_users``/``list_documents``/``list_ap_bills``/``list_ap_vendors``) plus the
detail reads (``get_*`` via the FILTER form — NextGen has no path-style
``/api/v2/{res}/{id}`` route), plus ``get_firm_summary``, ``list_timekeepers``,
``list_banks``, ``list_chart_of_accounts``, ``get_payment_invoice_allocations``.

WRITE COVERAGE (re-pointed to the NextGen ``/api/{resource}`` write API): the
create/update/delete methods for ``client``, ``matter``, ``contact``,
``timeExpense`` (time entries + expenses), ``invoice``, and ``transaction``,
plus AP-bill create/update (``accountPayable``) and AP-vendor create/update
(``payee``), now POST/PUT/PATCH/DELETE ``/api/{resource}`` via
``_api_post``/``_api_put``/``_api_patch``/``_api_delete``. The ENDPOINT + VERB
mirror the verified Rocket Matter rebuild, and the request BODY shape was
CONFIRMED LIVE against the CosmoLex sandbox (2026-06-27, full create/update/delete
round-trips per resource) — the ``**fields`` passthrough is kept and NO body
fields are invented.

NOT AVAILABLE ON NEXTGEN ``/api/v2`` (raise a clear ``RuntimeError`` so the tool
surface still imports and the count holds): the LCS Lookups (``/v1/lookups/...``),
the UTBMS Codes (``/v1/codes/...``), the Text Shortcuts (``/v1/text-shortcuts``),
the document write/action methods (``/v1/documents/...`` upload/download/delete),
``create_payment`` / ``approve_invoice``, and the AP delete + AP payment methods.
These were the dead ``/v1`` LCS surface; their NextGen equivalents (where they
exist) need separate supervised live discovery.
"""

from __future__ import annotations

import json
import os
import time
from datetime import date, timedelta
from pathlib import Path
from urllib.parse import urlencode, urlparse

import requests

from cosmolex_mcp import credentials

# Resolve credentials through the pluggable store (OS keyring -> env -> .env file).
# NextGen auth = username + password (the ApiKey/OAuth keys are not used).
credentials.load_into_environ(
    [
        "COSMOLEX_USERNAME",
        "COSMOLEX_PASSWORD",
        "COSMOLEX_BASE_URL",
    ]
)

BASE_URL = (
    os.environ.get("COSMOLEX_BASE_URL", "").strip().rstrip("/")
    or "https://sandbox.cosmolex.com"
)

# PUBLIC login-page client_id — SHARED across ProfitSolv NextGen (same value
# Rocket Matter uses). Constant, not a secret; used for the password grant.
LOGIN_CLIENT_ID = "4bfde53b970545e6b6a2d7f7ab55a957"

# Browser User-Agent — CosmoLex rejects the session login + data calls without
# browser-style headers (returns a misleading 401).
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36"
)

# Token endpoint (form-urlencoded password grant).
TOKEN_URL = f"{BASE_URL}/api/ext/auth/token"

CONFIG_DIR = Path.home() / ".cosmolex-mcp"
TOKEN_FILE = CONFIG_DIR / "tokens.json"


def _load_tokens() -> dict:
    if TOKEN_FILE.exists():
        try:
            with open(TOKEN_FILE) as f:
                return json.load(f)
        except (OSError, ValueError):
            return {}
    return {}


def _save_tokens(tokens: dict) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with open(TOKEN_FILE, "w") as f:
        json.dump(tokens, f, indent=2)
    os.chmod(TOKEN_FILE, 0o600)


class LCSClient:
    """NextGen CosmoLex client. Session login (username + password) ->
    ``a_t`` cookie -> ``/api/v2`` REST data calls.
    """

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": USER_AGENT,
                "X-Requested-With": "XMLHttpRequest",
                "Referer": f"{BASE_URL}/nxg/",
                "Accept": "application/json",
            }
        )
        self._tokens = _load_tokens()
        # Log in if there's no cached, unexpired token; otherwise reuse it.
        if not self._token_valid():
            self._login()
        else:
            self._apply_session_token()

    # ── Auth ─────────────────────────────────────────────────────────────────

    def _token_valid(self) -> bool:
        return bool(self._tokens.get("access_token")) and (
            time.time() < self._tokens.get("expires_at", 0) - 60
        )

    def _apply_session_token(self) -> None:
        """Set the session ``a_t`` cookie from the cached access token.

        Domain is derived from ``BASE_URL`` (not hardcoded) so a
        ``COSMOLEX_BASE_URL`` override still attaches the cookie — otherwise
        requests silently drops it and every call 401s.
        """
        self.session.cookies.set(
            "a_t", self._tokens["access_token"], domain=urlparse(BASE_URL).hostname
        )

    def _login(self) -> None:
        """Run the NextGen password-grant session login and persist tokens.

        Browser headers (User-Agent on the session + X-Requested-With + Referer)
        are REQUIRED — without them the grant falsely returns 401.
        """
        username = os.environ.get("COSMOLEX_USERNAME", "")
        password = os.environ.get("COSMOLEX_PASSWORD", "")
        if not username or not password:
            raise RuntimeError(
                "COSMOLEX_USERNAME and COSMOLEX_PASSWORD must be set. "
                "Run: cosmolex-mcp-setup"
            )

        # Prime cookies.
        self.session.get(f"{BASE_URL}/login")

        resp = self.session.post(
            TOKEN_URL,
            data={
                "username": username,
                "password": password,
                "grant_type": "password",
                "client_id": LOGIN_CLIENT_ID,
            },
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "X-Requested-With": "XMLHttpRequest",
                "Referer": f"{BASE_URL}/login",
            },
        )
        if resp.status_code != 200:
            raise RuntimeError(
                f"Login failed ({resp.status_code}): {resp.text[:200]}"
            )
        data = resp.json()
        token = data.get("access_token", "")
        if not token:
            raise RuntimeError("No access_token in login response")

        self._tokens = {
            "access_token": token,
            "refresh_token": data.get("refresh_token", ""),
            "expires_at": time.time() + data.get("expires_in", 17999),
        }
        _save_tokens(self._tokens)
        self._apply_session_token()

    # ── /api/v2 REST (NextGen) ───────────────────────────────────────────────

    @staticmethod
    def _is_unauthorized(resp: requests.Response) -> bool:
        """True if the response signals an expired/invalid session.

        NextGen does NOT always use HTTP 401: an expired session token returns
        HTTP 400 with a JSON body ``{"httpErrorType": 401, "login": false, ...}``.
        Treat both a real 401 and that 400-wrapped-401 as "re-login needed".
        """
        if resp.status_code == 401:
            return True
        if resp.status_code == 400 and resp.content:
            try:
                body = resp.json()
            except ValueError:
                return False
            if isinstance(body, dict) and (
                body.get("httpErrorType") == 401 or body.get("login") is False
            ):
                return True
        return False

    def _v2_get(self, resource: str, **params) -> list | dict:
        """GET ``{BASE}/api/v2/{resource}`` with query params; return parsed JSON.

        ``fields`` may be passed as a list or a comma string; it is joined to the
        ``fields=a,b,c`` form. Other filters (``active``, ``top``, ``skip``,
        ``sortInfo``, etc.) pass through unchanged. On a 401 the client re-logs in
        once and retries. An empty list ``[]`` is valid data.
        """
        query: dict[str, object] = {}
        for key, val in params.items():
            if val is None:
                continue
            if key == "fields" and isinstance(val, (list, tuple)):
                query["fields"] = ",".join(str(f) for f in val)
            else:
                query[key] = val
        url = f"{BASE_URL}/api/v2/{resource}"
        if query:
            # Keep the pipe in active=eq|true and the colon in sortInfo intact.
            url = f"{url}?{urlencode(query, safe='|:,')}"

        resp = self.session.get(url)
        if self._is_unauthorized(resp):
            self._login()
            resp = self.session.get(url)
        if not resp.ok:
            raise RuntimeError(f"API error {resp.status_code}: {resp.text[:400]}")
        if not resp.content:
            return []
        return resp.json()

    def _v2_detail(self, resource: str, id_field: str, record_id, fields) -> dict | None:
        """Single record from a ``/api/v2`` list endpoint by id filter.

        NextGen has no path-style detail route (``/api/v2/{res}/{id}`` 404s for
        every resource); a detail read is a filtered list. On CosmoLex the
        filterable primary key is ``id`` for EVERY resource we expose a detail read
        on — the guid-keyed business resources (client/matter/contact/timeExpense/
        invoice/transaction/payee) filter by their guid ``id``, and the
        numeric-keyed resources (user/accountPayable) filter by their numeric
        ``id``. (Verified live 2026-06-21: ``id=eq|{guid}`` is accepted and returns
        the row; ``identifier=eq|{guid}`` is REJECTED with 409 — ``identifier`` is
        a human-facing sequence NUMBER, not the primary key. This is the OPPOSITE
        of Rocket Matter, where ``identifier`` is the detail filter.) Returns the
        record dict, or ``None`` if not found.
        """
        result = self._v2_get(resource, fields=fields, **{id_field: f"eq|{record_id}"})
        if isinstance(result, list):
            return result[0] if result else None
        return result

    # ── Field sets (from /api/v2/resourcedef, verified live 2026-06-21) ───────
    # ``active`` is a FILTER on CosmoLex, NOT a readable field — never in fields.

    _CLIENT_FIELDS = [
        "name", "displayName", "email", "cellPhoneNumber", "workPhoneNumber",
        "homePhoneNumber", "code", "identifier", "label", "activeLabel",
        "city", "country", "clientAsEntity", "entityName", "notes",
    ]
    _MATTER_FIELDS = [
        "clientMatterName", "clientName", "clientDisplayName", "clientIdentifier",
        "clientCode", "billingMethodName", "billingMethod", "dateOpened",
        "areaOfLawDesc", "className", "active", "clientPortalShareable",
    ]
    _CONTACT_FIELDS = [
        "name", "displayName", "email", "cellPhoneNumber", "homePhoneNumber",
        "code", "identifier", "contactTypeLabel", "activeLabel", "city",
        "country", "clientAsEntity", "entityName",
    ]
    _TIME_ENTRY_FIELDS = [
        "identifier", "description", "clientMatterName", "clientName",
        "billableAmount", "billableTime", "billedHours", "billedMinutes",
        "billingStatusLabel", "cardStatusLabel", "cardTypeLabel", "invoiced",
        "invoiceNumber", "invoiceDate", "creationDate", "expenseCode", "hold",
    ]
    _EXPENSE_FIELDS = [
        "identifier", "description", "clientMatterName", "clientName",
        "billableAmount", "billingStatusLabel", "cardTypeLabel", "expenseCode",
        "invoiced", "invoiceNumber", "invoiceDate", "creationDate", "hold",
    ]
    _INVOICE_FIELDS = [
        "clientMatterName", "clientName", "clientCode", "clientEmailAddress",
        "description", "dueDate", "discountAmount", "discountTypeLabel",
        "financeChargeAmount", "advancedClientCost", "clientPortalShareable",
        "ebillingEnabled", "extendedClientMatterName",
    ]
    _PAYMENT_FIELDS = ["amount", "notes", "paymentDate", "paymentReference", "payorName"]
    _TRANSACTION_FIELDS = [
        "identifier", "clientMatterName", "clientName", "clientCode",
        "clientDisplayName", "bankName", "bankAccountName", "bankAccountNumber",
        "bankTypeLabel", "clearDate", "cleared", "depositSlipDate",
        "depositSlipNumber", "isCreditMemo", "isOperatingRetainer",
    ]
    _ALLOCATION_FIELDS = [
        "accountName", "accountNumber", "accountLabel", "allocationTypeLabel",
        "creditAmount", "debitAmount", "signedAmount", "balance", "entryDate",
        "entryType", "memo", "payee", "referenceNumber", "journalEntryId",
        "isHardCost", "isTaxAllocation",
    ]
    _DOCUMENT_FIELDS = [
        "name", "itemType", "size", "modified", "clientPortalShareable",
        "hasComments",
    ]
    _USER_FIELDS = [
        "userFullName", "emailAddress", "userName", "roleName", "cellNumber",
        "lastLoginDateTime",
    ]
    _FIRM_FIELDS = [
        "unpaidBalance", "unbilledBalance", "paidAmount", "billedAmount",
        "overdueInvoices", "overdueInvoicesTotal", "unpaidInvoices",
        "trustRetainer", "operatingRetainer", "unbilledTimeExpenseCards",
    ]
    _TIMEKEEPER_FIELDS = [
        "name", "emailAddress", "initials", "title", "active", "billableTime",
        "nonBillableTime", "noChargeTime", "targetHours", "defaultRate",
        "className", "timeKeeperCode",
    ]
    _BANK_FIELDS = [
        "bankName", "accountName", "accountNumber", "accountLabel", "balance",
        "bankTypeLabel", "chartOfAccountNumber", "label", "operatingRetainerAmount",
        "trustRetainerAmount",
    ]
    _COA_FIELDS = [
        "accountNumber", "accountName", "accountLabel", "accountTypeLabel",
        "accountBalance", "balanceAmount", "description", "statusLabel",
        "isSubAccount", "systemDefined",
    ]
    _AP_BILL_FIELDS = [
        "date", "dueDate", "amount", "balance", "discount", "financeCharge",
        "billCreditLabel", "category", "clientName", "clientMatter",
        "matterName", "matterFileNumber", "memo1", "memo2", "notes",
        "isCredit", "paid", "hold", "agingDays", "overDueDays",
    ]
    _PAYEE_FIELDS = [
        "payeeName", "identifier", "printAs", "active", "email", "phone", "fax",
        "address1", "city", "stateShortName", "countryShortName", "taxId",
        "eligibleFor1099", "contactName", "notes",
    ]

    # ── Clients ──────────────────────────────────────────────────────────────

    def list_clients(
        self,
        page: int = 1,
        page_size: int = 25,
        active_only: bool | None = None,
        display_name: str | None = None,
        name: str | None = None,
        email: str | None = None,
    ) -> list | dict:
        """List clients via ``/api/v2/client``. ``page_size`` maps to ``top``;
        ``active_only`` to ``active=eq|true``. (``display_name``/``name``/``email``
        accepted for API compatibility; the ``/api/v2`` text-search filters differ
        from the legacy params and are not applied here.)"""
        params: dict[str, object] = {
            "fields": self._CLIENT_FIELDS,
            "top": page_size,
            "skip": (page - 1) * page_size,
        }
        if active_only:
            params["active"] = "eq|true"
        return self._v2_get("client", **params)

    def get_client(self, client_id: str) -> dict | None:
        return self._v2_detail("client", "id", client_id, self._CLIENT_FIELDS)

    def create_client(self, **fields) -> dict:
        return self._api_post("client", fields)

    def update_client(self, client_id: str, **fields) -> dict:
        return self._api_put("client", client_id, fields)

    def delete_client(self, client_id: str) -> dict:
        return self._api_delete("client", client_id)

    # ── Matters ──────────────────────────────────────────────────────────────

    def list_matters(
        self,
        page: int = 1,
        page_size: int = 25,
        active_only: bool | None = None,
        search_text: str | None = None,
        client_id: str | None = None,
        matter_owner_id: int | None = None,
        matter_type_id: int | None = None,
    ) -> list | dict:
        """List matters via ``/api/v2/matter``. ``page_size`` maps to ``top``;
        ``active_only`` to ``active=eq|true``. (``search_text``/``client_id``/
        ``matter_owner_id``/``matter_type_id`` accepted for API compatibility;
        ``/api/v2`` server-side filters differ and are not applied here.)"""
        params: dict[str, object] = {
            "fields": self._MATTER_FIELDS,
            "top": page_size,
            "skip": (page - 1) * page_size,
        }
        if active_only:
            params["active"] = "eq|true"
        return self._v2_get("matter", **params)

    def get_matter(self, matter_id: str) -> dict | None:
        return self._v2_detail("matter", "id", matter_id, self._MATTER_FIELDS)

    def create_matter(self, **fields) -> dict:
        return self._api_post("matter", fields)

    def update_matter(self, matter_id: str, **fields) -> dict:
        return self._api_put("matter", matter_id, fields)

    def delete_matter(self, matter_id: str) -> dict:
        return self._api_delete("matter", matter_id)

    # ── Contacts ─────────────────────────────────────────────────────────────

    def list_contacts(
        self, page: int = 1, page_size: int = 25, active_only: bool | None = None
    ) -> list | dict:
        params: dict[str, object] = {
            "fields": self._CONTACT_FIELDS,
            "top": page_size,
            "skip": (page - 1) * page_size,
        }
        if active_only:
            params["active"] = "eq|true"
        return self._v2_get("contact", **params)

    def get_contact(self, contact_id: str) -> dict | None:
        return self._v2_detail("contact", "id", contact_id, self._CONTACT_FIELDS)

    def create_contact(self, **fields) -> dict:
        return self._api_post("contact", fields)

    def update_contact(self, contact_id: str, **fields) -> dict:
        return self._api_put("contact", contact_id, fields)

    def delete_contact(self, contact_id: str) -> dict:
        return self._api_delete("contact", contact_id)

    # ── Time Entries (timeExpense filtered to Time rows) ─────────────────────

    def list_time_entries(
        self,
        matter_id: str | None = None,
        rate_type: str | None = None,
        billing_status: str | None = None,
        card_status: str | None = None,
        timekeeper_id: int | None = None,
        page: int = 1,
        page_size: int = 25,
    ) -> list | dict:
        params: dict[str, object] = {
            "fields": self._TIME_ENTRY_FIELDS,
            "top": page_size,
            "skip": (page - 1) * page_size,
            "sortInfo": "creationDate:desc",
            "cardTypeLabel": "eq|Time",
        }
        return self._v2_get("timeExpense", **params)

    def get_time_entry(self, time_entry_id: str) -> dict | None:
        return self._v2_detail(
            "timeExpense", "id", time_entry_id, self._TIME_ENTRY_FIELDS
        )

    def create_time_entry(self, **fields) -> dict:
        return self._api_post("timeExpense", fields)

    def update_time_entry(self, time_entry_id: str, **fields) -> dict:
        return self._api_put("timeExpense", time_entry_id, fields)

    def delete_time_entry(self, time_entry_id: str) -> dict:
        return self._api_delete("timeExpense", time_entry_id)

    # ── Expenses (timeExpense filtered to Expense rows) ──────────────────────

    def list_expenses(
        self,
        billing_type_id: int | None = None,
        billing_status_id: int | None = None,
        is_matter_active: bool | None = None,
        page: int = 1,
        page_size: int = 25,
    ) -> list | dict:
        return self._v2_get(
            "timeExpense",
            fields=self._EXPENSE_FIELDS,
            top=page_size,
            skip=(page - 1) * page_size,
            sortInfo="creationDate:desc",
            cardTypeLabel="eq|Expense",
        )

    def get_expense(self, expense_card_id: str) -> dict | None:
        return self._v2_detail(
            "timeExpense", "id", expense_card_id, self._EXPENSE_FIELDS
        )

    def create_expense(self, **fields) -> dict:
        return self._api_post("timeExpense", fields)

    def update_expense(self, expense_card_id: str, **fields) -> dict:
        return self._api_put("timeExpense", expense_card_id, fields)

    def delete_expense(self, expense_card_id: str) -> dict:
        return self._api_delete("timeExpense", expense_card_id)

    # ── Invoices ─────────────────────────────────────────────────────────────

    def list_invoices(
        self,
        page: int = 1,
        page_size: int = 25,
        status: str | None = None,
        matter_id: str | None = None,
        client_id: str | None = None,
        invoice_number: str | None = None,
        is_draft: bool | None = None,
    ) -> list | dict:
        return self._v2_get(
            "invoice",
            fields=self._INVOICE_FIELDS,
            top=page_size,
            skip=(page - 1) * page_size,
        )

    def get_invoice(self, invoice_id: str) -> dict | None:
        return self._v2_detail("invoice", "id", invoice_id, self._INVOICE_FIELDS)

    def create_invoice(self, **fields) -> dict:
        return self._api_post("invoice", fields)

    def update_invoice(self, invoice_id: str, **fields) -> dict:
        return self._api_patch("invoice", invoice_id, fields)

    def delete_invoice(self, invoice_id: str) -> dict:
        return self._api_delete("invoice", invoice_id)

    def approve_invoice(self, invoice_id: str, **fields) -> dict:
        """Approve an invoice. NOT available on NextGen ``/api/v2`` — the legacy
        ``/v1/invoices/{id}/approve`` LCS path is dead on NextGen accounts and the
        NextGen approval flow has not been captured live."""
        raise RuntimeError(
            "approve_invoice is not available on NextGen /api/v2 (legacy /v1 "
            "approve path is dead); the NextGen approval flow needs live capture."
        )

    # ── Payments (genericPayment read; create not on /api/v2) ────────────────

    def list_payments(
        self,
        page: int = 1,
        page_size: int = 25,
        matter_id: str | None = None,
        invoice_id: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> list | dict:
        # /api/v2 payments resource is genericPayment (NOT payment).
        return self._v2_get(
            "genericPayment",
            fields=self._PAYMENT_FIELDS,
            top=page_size,
            skip=(page - 1) * page_size,
            sortInfo="paymentDate:desc",
        )

    def create_payment(self, **fields) -> dict:
        """Record a payment. NOT available on NextGen ``/api/v2`` — the legacy
        ``/v1/payments`` LCS path is dead on NextGen and the NextGen payment-create
        flow (a multi-step allocation form) needs separate live capture."""
        raise RuntimeError(
            "create_payment is not available on NextGen /api/v2 (legacy /v1 path "
            "is dead); the NextGen payment-create flow needs live capture."
        )

    def get_payment_invoice_allocations(self, **params) -> list | dict:
        """Invoice allocations via ``/api/v2/allocation``. Requires an
        ``invoice_id`` / ``invoiceId`` (or ``journal_entry_id``) filter — an
        unfiltered allocation read 409s ("Something went wrong.")."""
        invoice_id = params.get("invoice_id") or params.get("invoiceId")
        journal_entry_id = params.get("journal_entry_id") or params.get("journalEntryId")
        if not (invoice_id or journal_entry_id):
            raise RuntimeError(
                "get_payment_invoice_allocations requires an invoice_id (or "
                "journal_entry_id) filter; an unfiltered /api/v2/allocation read "
                "is rejected (409) by NextGen."
            )
        q: dict[str, object] = {
            "fields": self._ALLOCATION_FIELDS,
            "sortInfo": "entryDate:desc",
        }
        if invoice_id:
            q["invoiceId"] = f"eq|{invoice_id}"
        if journal_entry_id:
            q["journalEntryId"] = f"eq|{journal_entry_id}"
        if params.get("top") is not None:
            q["top"] = params["top"]
        if params.get("skip") is not None:
            q["skip"] = params["skip"]
        return self._v2_get("allocation", **q)

    # ── Transactions ─────────────────────────────────────────────────────────

    def list_transactions(
        self,
        page: int = 1,
        page_size: int = 25,
        bank_id: str | None = None,
        bank_type: int | None = None,
        matter_id: str | None = None,
        transaction_type: str | None = None,
        transaction_status: str | None = None,
    ) -> list | dict:
        params: dict[str, object] = {
            "fields": self._TRANSACTION_FIELDS,
            "top": page_size,
            "skip": (page - 1) * page_size,
        }
        if bank_id:
            params["bankId"] = f"eq|{bank_id}"
        if matter_id:
            params["matterId"] = f"eq|{matter_id}"
        return self._v2_get("transaction", **params)

    def get_transaction(self, transaction_id: str) -> dict | None:
        return self._v2_detail(
            "transaction", "id", transaction_id, self._TRANSACTION_FIELDS
        )

    @staticmethod
    def _shape_allocation(alloc: dict, row_id: int) -> dict:
        """Coerce one transaction allocation row into the shape NextGen requires.

        Verified live 2026-06-21 (mirrors Rocket Matter): the per-row amount key is
        ``allocationSignedAmount`` (NOT ``signedAmount``/``amount``), each row needs
        a client-side sequential ``id`` + ``deleted: false``, and
        ``chartOfAccountId`` is sent as a STRING. ``amount`` is accepted as a
        friendly alias for ``allocationSignedAmount``.
        """
        a = dict(alloc)
        a.setdefault("id", row_id)
        a.setdefault("deleted", False)
        a.setdefault("memo", "")
        alias = a.pop("amount", None)
        if "allocationSignedAmount" not in a and alias is not None:
            a["allocationSignedAmount"] = alias
        if a.get("chartOfAccountId") is not None:
            a["chartOfAccountId"] = str(a["chartOfAccountId"])
        return a

    def create_transaction(self, **fields) -> dict:
        """Create a bank transaction (deposit/withdrawal) — verified live 2026-06-21.

        Required body: ``bankId`` (guid from :meth:`list_banks`), ``transactionType``
        ("1"=Deposit / "9"=Withdrawal), ``transactionMethod`` (numeric, 1001+ range;
        e.g. 1005=Cash — 1-3 are rejected), ``transactionDate``, ``amount`` (string),
        ``payeeName``, and a non-empty ``allocations`` list whose
        ``allocationSignedAmount`` values sum to ``amount`` (each needs a
        ``chartOfAccountId`` from :meth:`list_chart_of_accounts`). Allocation rows are
        normalised here (see :meth:`_shape_allocation`). NOTE: an Operating-bank
        deposit needs no matter; a TRUST-bank transaction requires ``matterId``
        ("Matter is required for trust transaction").
        """
        body = dict(fields)
        body.setdefault("savePayee", False)
        allocations = body.get("allocations")
        if isinstance(allocations, list):
            body["allocations"] = [
                self._shape_allocation(a, i) for i, a in enumerate(allocations, 1)
            ]
        return self._api_post("transaction", body)

    def update_transaction(self, transaction_id: str, **fields) -> dict:
        return self._api_put("transaction", transaction_id, fields)

    def delete_transaction(self, transaction_id: str) -> dict:
        return self._api_delete("transaction", transaction_id)

    def list_billable_items(self, matter_id: str, to_date: str | None = None) -> list:
        """Unbilled, billable time/expense for a matter (``GET /api/timeexpense/``).

        Each row carries the per-item ``challenge`` token an invoice create must echo
        back in ``timeExpenseList`` (verified live 2026-06-21). Note the lowercase
        ``timeexpense`` path — distinct from the ``/api/v2/timeExpense`` read grid,
        which does not expose ``challenge``.
        """
        params = {
            "sortBy": "-creationDate",
            "matterId": matter_id,
            "invoiced": "false",
            "toDate": to_date or date.today().isoformat(),
            "statusId": "eq|1",
            "billingStatus": "any|1",
            "isMatterActive": "eq|true",
        }
        resp = self.session.get(f"{BASE_URL}/api/timeexpense/", params=params)
        if self._is_unauthorized(resp):
            self._login()
            resp = self.session.get(f"{BASE_URL}/api/timeexpense/", params=params)
        if not resp.ok:
            raise RuntimeError(f"API error {resp.status_code}: {resp.text[:400]}")
        data = resp.json() if resp.content else []
        if not isinstance(data, list):
            raise RuntimeError(
                f"Unexpected billable-items response: {type(data).__name__}: {str(data)[:200]}"
            )
        return data

    def generate_invoice(
        self,
        matter_id: str,
        invoice_date: str | None = None,
        due_date: str | None = None,
        to_date: str | None = None,
        **extra,
    ) -> dict:
        """Generate an invoice for a matter from its unbilled billable items.

        Two-step flow (verified live 2026-06-21): fetch the matter's billable items
        to collect each item's ``challenge`` token, then POST the invoice echoing
        ``timeExpenseList=[{id, challenge}, ...]``. Raises if the matter has no
        unbilled billable items. ``**extra`` overrides any default body field.
        """
        items = self.list_billable_items(matter_id, to_date)
        time_expense_list = [
            {"id": it["id"], "challenge": it["challenge"]}
            for it in items
            if it.get("id") and it.get("challenge")
        ]
        if not time_expense_list:
            raise RuntimeError(
                f"No unbilled billable items for matter {matter_id}; nothing to invoice."
            )
        # The next invoice number comes from the matter-scoped form prep; the create
        # rejects a null invoiceNumber, so fetch it rather than omit it.
        form = self.session.get(
            f"{BASE_URL}/api/gui/form/newInvoice", params={"matterId": matter_id}
        )
        if self._is_unauthorized(form):
            self._login()
            form = self.session.get(
                f"{BASE_URL}/api/gui/form/newInvoice", params={"matterId": matter_id}
            )
        invoice_number = None
        if form.ok and form.content:
            try:
                invoice_number = form.json().get("invoiceNumber")
            except ValueError:
                pass
        inv_date = invoice_date or date.today().isoformat()
        if due_date is None:
            due_date = (date.fromisoformat(inv_date) + timedelta(days=30)).isoformat()
        body = {
            "matterId": matter_id,
            "invoiceNumber": invoice_number,
            "invoiceDate": inv_date,
            "dueDate": due_date,
            "toDate": to_date or inv_date,
            "timeExpenseList": time_expense_list,
            "description": "",
            "discountType": "1",
            "discountAmount": 0,
            "discountTaxable": True,
            "consolidateSimilarExpense": True,
            "overheadContext": 1,
            "overheadPercentage": 0,
            "financeChargeAmount": 0,
            "financeChargeIsAutomatic": False,
            "lateFees": 0,
            "otherFees": 0,
            "clientPortalShareable": False,
            "showCoverPage": False,
            "isStartDateSelected": False,
            "applyAvailableOperatingFunds": False,
            "applyAvailableTrustFunds": False,
            "writeOffList": [],
            "documents": [],
            "id": None,
        }
        body.update(extra)
        return self._api_post("invoice", body)

    # ── Documents (read on /api/v2; writes not available) ────────────────────

    def list_documents(
        self,
        matter_id: str | None = None,
        path: str | None = None,
        doc_id: str | None = None,
        file_name: str | None = None,
    ) -> list | dict:
        params: dict[str, object] = {"fields": self._DOCUMENT_FIELDS, "top": 25}
        if matter_id:
            params["matterId"] = f"eq|{matter_id}"
        if doc_id:
            params["identifier"] = f"eq|{doc_id}"
        if file_name:
            params["name"] = f"eq|{file_name}"
        return self._v2_get("document", **params)

    def get_document_default_application(self) -> dict:
        raise RuntimeError(
            "get_document_default_application is not available on NextGen /api/v2 "
            "(legacy /v1/documents path is dead); needs live capture."
        )

    def get_document_download_url(self, **fields) -> dict:
        raise RuntimeError(
            "get_document_download_url is not available on NextGen /api/v2 "
            "(legacy /v1/documents path is dead); needs live capture."
        )

    def get_document_upload_url(self, **fields) -> dict:
        raise RuntimeError(
            "get_document_upload_url is not available on NextGen /api/v2 "
            "(legacy /v1/documents path is dead); needs live capture."
        )

    def delete_document(self, **fields) -> dict:
        raise RuntimeError(
            "delete_document is not available on NextGen /api/v2 "
            "(legacy /v1/documents path is dead); needs live capture."
        )

    # ── Users / Timekeepers ──────────────────────────────────────────────────

    def list_users(
        self, page: int = 1, page_size: int = 25, active_only: bool | None = None
    ) -> list | dict:
        """List users via ``/api/v2/user``."""
        return self._v2_get(
            "user", fields=self._USER_FIELDS, top=page_size, skip=(page - 1) * page_size
        )

    def get_user(self, user_id: str) -> dict | None:
        return self._v2_detail("user", "id", user_id, self._USER_FIELDS)

    def list_timekeepers(
        self, page: int = 1, page_size: int = 25, active_only: bool | None = None
    ) -> list | dict:
        """List timekeepers (billable-time summary) via ``/api/v2/timekeeper``."""
        params: dict[str, object] = {
            "fields": self._TIMEKEEPER_FIELDS,
            "top": page_size,
        }
        if active_only:
            params["active"] = "eq|true"
        return self._v2_get("timekeeper", **params)

    def get_firm_summary(self) -> list | dict:
        """Firm financial summary via ``/api/v2/firm``."""
        return self._v2_get("firm", fields=self._FIRM_FIELDS)

    def list_banks(self) -> list | dict:
        """Bank accounts via ``/api/v2/bank``. The ``id`` is the ``bankId`` a
        transaction create needs."""
        return self._v2_get("bank", fields=self._BANK_FIELDS, top=50)

    def list_chart_of_accounts(self) -> list | dict:
        """Chart of accounts via ``/api/v2/coa``. The ``id`` is the
        ``chartOfAccountId`` used in transaction allocations."""
        return self._v2_get("coa", fields=self._COA_FIELDS, top=300)

    # ── Accounts Payable — Bills (accountPayable grid) ───────────────────────

    def list_ap_bills(
        self,
        page: int = 1,
        page_size: int = 25,
        status: str | None = None,
        paid: bool | None = None,
        is_credit: bool | None = None,
        payee_name: str | None = None,
    ) -> list | dict:
        return self._v2_get(
            "accountPayable",
            fields=self._AP_BILL_FIELDS,
            top=page_size,
            skip=(page - 1) * page_size,
        )

    def get_ap_bill(self, bill_id: str) -> dict | None:
        # accountPayable's primary key is the numeric ``id`` (no ``identifier``).
        return self._v2_detail("accountPayable", "id", bill_id, self._AP_BILL_FIELDS)

    def create_ap_bill(self, **fields) -> dict:
        return self._api_post("accountPayable", fields)

    def update_ap_bill(self, bill_id: str, **fields) -> dict:
        return self._api_patch("accountPayable", bill_id, fields)

    def delete_ap_bill(self, bill_id: str) -> dict:
        raise RuntimeError(
            "delete_ap_bill is not available on NextGen /api/v2 (legacy "
            "/v1/accounts-payable path is dead); the NextGen delete verb needs "
            "live capture."
        )

    # ── Accounts Payable — Vendors (payee grid) ──────────────────────────────

    def list_ap_vendors(
        self,
        page: int = 1,
        page_size: int = 25,
        search: str | None = None,
        email: str | None = None,
        active_only: bool | None = None,
    ) -> list | dict:
        params: dict[str, object] = {
            "fields": self._PAYEE_FIELDS,
            "top": page_size,
            "skip": (page - 1) * page_size,
        }
        if active_only:
            params["active"] = "eq|true"
        return self._v2_get("payee", **params)

    def get_ap_vendor(self, vendor_id: str) -> dict | None:
        return self._v2_detail("payee", "id", vendor_id, self._PAYEE_FIELDS)

    def create_ap_vendor(self, **fields) -> dict:
        return self._api_post("payee", fields)

    def update_ap_vendor(self, vendor_id: str, **fields) -> dict:
        return self._api_put("payee", vendor_id, fields)

    # ── Accounts Payable — Payments (not on /api/v2) ─────────────────────────

    def list_ap_payments(self, page: int = 1, page_size: int = 25, **kw) -> dict:
        raise RuntimeError(
            "list_ap_payments is not available on NextGen /api/v2 (legacy "
            "/v1/accounts-payable/payments path is dead); needs live capture."
        )

    def get_ap_payment_status(self, **params) -> dict:
        raise RuntimeError(
            "get_ap_payment_status is not available on NextGen /api/v2 (legacy "
            "/v1/accounts-payable/payments path is dead); needs live capture."
        )

    def create_ap_payment(self, **fields) -> dict:
        raise RuntimeError(
            "create_ap_payment is not available on NextGen /api/v2 (legacy "
            "/v1/accounts-payable/payments path is dead); needs live capture."
        )

    # ── Codes (UTBMS) — not on /api/v2 ───────────────────────────────────────

    def get_codes(self, matter_id: str | None = None) -> dict:
        raise RuntimeError(
            "get_codes is not available on NextGen /api/v2 (legacy /v1/codes LCS "
            "path is dead); the NextGen UTBMS-codes source needs live discovery."
        )

    def get_task_codes(self, matter_id: str | None = None) -> dict:
        raise RuntimeError(
            "get_task_codes is not available on NextGen /api/v2 (legacy /v1/codes "
            "LCS path is dead); the NextGen UTBMS-codes source needs live discovery."
        )

    def get_activity_codes(self, matter_id: str | None = None) -> dict:
        raise RuntimeError(
            "get_activity_codes is not available on NextGen /api/v2 (legacy "
            "/v1/codes LCS path is dead); the NextGen UTBMS-codes source needs "
            "live discovery."
        )

    # ── Text Shortcuts — not on /api/v2 ──────────────────────────────────────

    def list_text_shortcuts(self, page: int = 1, page_size: int = 25) -> dict:
        raise RuntimeError(
            "list_text_shortcuts is not available on NextGen /api/v2 (legacy "
            "/v1/text-shortcuts LCS path is dead); needs live discovery."
        )

    def get_text_shortcut(self, shortcut_id: str) -> dict:
        raise RuntimeError(
            "get_text_shortcut is not available on NextGen /api/v2 (legacy "
            "/v1/text-shortcuts LCS path is dead); needs live discovery."
        )

    # ── Lookups — not on /api/v2 ─────────────────────────────────────────────
    # The LCS /v1/lookups/* surface is dead on NextGen. NextGen surfaces this data
    # via /api/gui/form/* and /api/v2/resourcedef/* instead, which need separate
    # supervised live discovery before re-implementing. Until then these raise.

    def _lookup_unavailable(self, name: str):
        raise RuntimeError(
            f"{name} is not available on NextGen /api/v2 (legacy /v1/lookups LCS "
            "path is dead); NextGen form-defaults come from /api/gui/form/* and "
            "/api/v2/resourcedef/*, which need live discovery."
        )

    def lookup_clients(self, query: str | None = None) -> dict:
        self._lookup_unavailable("lookup_clients")

    def lookup_client_labels(self, query: str | None = None) -> dict:
        self._lookup_unavailable("lookup_client_labels")

    def lookup_matter_labels(self, query: str | None = None) -> dict:
        self._lookup_unavailable("lookup_matter_labels")

    def lookup_matter_type_workflow(self, matter_type_id: str) -> dict:
        self._lookup_unavailable("lookup_matter_type_workflow")

    def lookup_new_contact_form(self) -> dict:
        self._lookup_unavailable("lookup_new_contact_form")

    def lookup_new_matter_definition(self) -> dict:
        self._lookup_unavailable("lookup_new_matter_definition")

    def lookup_new_matter_definition_for_matter(self, matter_id: str) -> dict:
        self._lookup_unavailable("lookup_new_matter_definition_for_matter")

    def lookup_new_matter_defaults(self) -> dict:
        self._lookup_unavailable("lookup_new_matter_defaults")

    def lookup_new_matter_ebilling_defaults(self) -> dict:
        self._lookup_unavailable("lookup_new_matter_ebilling_defaults")

    def lookup_expense(self, matter_id: str | None = None) -> dict:
        self._lookup_unavailable("lookup_expense")

    def lookup_new_expense(self) -> dict:
        self._lookup_unavailable("lookup_new_expense")

    def lookup_new_expense_info(self, matter_id: str | None = None) -> dict:
        self._lookup_unavailable("lookup_new_expense_info")

    def lookup_new_hard_cost_expense(self, matter_id: str | None = None) -> dict:
        self._lookup_unavailable("lookup_new_hard_cost_expense")

    def lookup_invoice_payments(self) -> dict:
        self._lookup_unavailable("lookup_invoice_payments")

    def lookup_invoice(self, matter_id: str | None = None) -> dict:
        self._lookup_unavailable("lookup_invoice")

    def lookup_new_invoice(self) -> dict:
        self._lookup_unavailable("lookup_new_invoice")

    def lookup_new_invoice_info(self, matter_id: str | None = None) -> dict:
        self._lookup_unavailable("lookup_new_invoice_info")

    def lookup_new_time_entry(self, matter_id: str | None = None) -> dict:
        self._lookup_unavailable("lookup_new_time_entry")

    def lookup_new_timesheet_from_grid(self) -> dict:
        self._lookup_unavailable("lookup_new_timesheet_from_grid")

    def lookup_new_transaction(
        self,
        transaction_type: str | None = None,
        context: str | None = None,
        context_id: str | None = None,
    ) -> dict:
        self._lookup_unavailable("lookup_new_transaction")

    # ── /api writes (NextGen) — POST collection / PUT|PATCH|DELETE item ───────

    def _api_post(self, resource: str, body: dict | None = None) -> dict:
        return self._api_write("POST", f"/api/{resource}", body)

    def _api_put(self, resource: str, record_id, body: dict | None = None) -> dict:
        """Update via full-record replace (mirrors the verified RM pattern).

        NextGen PUT expects the COMPLETE record, not a partial patch (a partial
        body returns ``409``). So fetch the current record, merge the caller's
        changed fields over it, and PUT the whole thing back. BODY shape is
        CONFIRMED LIVE against the CosmoLex sandbox (2026-06-27).
        """
        current = self.session.get(f"{BASE_URL}/api/{resource}/{record_id}")
        if self._is_unauthorized(current):
            self._login()
            current = self.session.get(f"{BASE_URL}/api/{resource}/{record_id}")
        merged: dict = {}
        if current.ok and current.content:
            try:
                existing = current.json()
                if isinstance(existing, dict):
                    merged = existing
            except ValueError:
                pass
        merged.update(body or {})
        return self._api_write("PUT", f"/api/{resource}/{record_id}", merged)

    def _api_patch(self, resource: str, record_id, body: dict | None = None) -> dict:
        return self._api_write("PATCH", f"/api/{resource}/{record_id}", body)

    def _api_delete(self, resource: str, record_id) -> dict:
        return self._api_write("DELETE", f"/api/{resource}/{record_id}", None)

    def _api_write(self, method: str, path: str, body: dict | None) -> dict:
        """Mutating call on the NextGen /api write API (a_t cookie session).

        Endpoint + verb mirror the verified RM rebuild; the BODY shape is
        CONFIRMED LIVE against the CosmoLex sandbox (2026-06-27). Re-logs in once
        on a 401/400-wrapped-401, same as the reads.
        """
        url = f"{BASE_URL}{path}"
        json_body = None if method == "DELETE" else (body or {})
        resp = self.session.request(method, url, json=json_body)
        if self._is_unauthorized(resp):
            self._login()
            resp = self.session.request(method, url, json=json_body)
        if not resp.ok:
            raise RuntimeError(f"API error {resp.status_code}: {resp.text[:400]}")
        if not resp.content:
            return {"success": True}
        return resp.json()
