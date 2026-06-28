#!/usr/bin/env python3
"""Cosmolex MCP server — LCS Integration API tools."""

import json
from functools import wraps
from mcp.server.fastmcp import FastMCP
from cosmolex_mcp.client import LCSClient

mcp = FastMCP(
    "cosmolex",
    instructions=(
        "Cosmolex legal practice management via the ProfitSolv LCS /v1 Integration "
        "API (scoped OAuth — no password login, so it never logs you out of "
        "CosmoLex). Covered: matters, clients, contacts, time entries, expenses, "
        "invoices, payments, transactions (by matter/bank), documents (read), users, "
        "and UTBMS codes. Matters are the core entity — most resources link to a matter "
        "ID. Some legacy tools (firm summary, banks, chart of accounts, accounts "
        "payable, lookups, timekeeper summaries, tasks/calendar/trust/etc.) are NOT in "
        "the /v1 API and fail loudly with a clear message rather than returning nothing."
    ),
)

_raw_tool = mcp.tool


def _safe_tool(*args, **kwargs):
    def decorator(fn):
        @wraps(fn)
        def wrapped(*fn_args, **fn_kwargs):
            try:
                return fn(*fn_args, **fn_kwargs)
            except Exception as e:
                return json.dumps({"error": str(e)})

        return _raw_tool(*args, **kwargs)(wrapped)

    return decorator


mcp.tool = _safe_tool


def _c():
    return LCSClient()


def _fields(fields_json: str | None) -> dict:
    if not fields_json:
        return {}
    try:
        fields = json.loads(fields_json)
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid fields_json: {e}") from e
    if not isinstance(fields, dict):
        raise ValueError("fields_json must be a JSON object")
    return fields


# ── Matters ────────────────────────────────────────────────────────────────────


@mcp.tool()
def list_matters(
    page: int = 1,
    page_size: int = 25,
    client_id: str | None = None,
    matter_name: str | None = None,
) -> str:
    """List matters, paginated. Optional server-side filters: client_id (GUID) and
    matter_name — these are the only filters the /v1 API honors for matters."""
    return json.dumps(
        _c().list_matters(
            page=page,
            page_size=page_size,
            client_id=client_id,
            matter_name=matter_name,
        ),
        indent=2,
    )


@mcp.tool()
def get_matter(matter_id: str) -> str:
    """Get a matter by ID (GUID)."""
    return json.dumps(_c().get_matter(matter_id), indent=2)


@mcp.tool()
def create_matter(fields_json: str) -> str:
    """Create a matter. fields_json: JSON object with matter fields.
    Required: clientId. Optional: billingMethod, dateOpened, matterOwnerId,
    areaOfLawId, matterName, matterFileNumber, notes, matterTypeId."""
    return json.dumps(_c().create_matter(**_fields(fields_json)), indent=2)


@mcp.tool()
def update_matter(matter_id: str, fields_json: str) -> str:
    """Update a matter by ID (GUID). fields_json: JSON object with fields to update."""
    return json.dumps(_c().update_matter(matter_id, **_fields(fields_json)), indent=2)


@mcp.tool()
def delete_matter(matter_id: str) -> str:
    """Delete a matter by ID (GUID)."""
    return json.dumps(_c().delete_matter(matter_id), indent=2)


# ── Clients ────────────────────────────────────────────────────────────────────


@mcp.tool()
def list_clients(
    page: int = 1,
    page_size: int = 25,
    name: str | None = None,
    display_name: str | None = None,
) -> str:
    """List clients, paginated. Optional server-side filters: name and display_name —
    these are the only filters the /v1 API honors for clients."""
    return json.dumps(
        _c().list_clients(
            page=page,
            page_size=page_size,
            name=name,
            display_name=display_name,
        ),
        indent=2,
    )


@mcp.tool()
def get_client(client_id: str) -> str:
    """Get a client by ID (GUID)."""
    return json.dumps(_c().get_client(client_id), indent=2)


@mcp.tool()
def create_client(fields_json: str) -> str:
    """Create a client. fields_json: JSON object. Required: name.
    Optional: displayName, contactSalutation, contactTitle, entityName,
    address1, clientAsEntity, email, secondaryEmail, cellPhoneNumber."""
    return json.dumps(_c().create_client(**_fields(fields_json)), indent=2)


@mcp.tool()
def update_client(client_id: str, fields_json: str) -> str:
    """Update a client by ID (GUID). fields_json: JSON object with fields to update."""
    return json.dumps(_c().update_client(client_id, **_fields(fields_json)), indent=2)


@mcp.tool()
def delete_client(client_id: str) -> str:
    """Delete a client by ID (GUID)."""
    return json.dumps(_c().delete_client(client_id), indent=2)


# ── Contacts ───────────────────────────────────────────────────────────────────


@mcp.tool()
def list_contacts(page: int = 1, page_size: int = 25) -> str:
    """List contacts with pagination."""
    return json.dumps(_c().list_contacts(page=page, page_size=page_size), indent=2)


@mcp.tool()
def get_contact(contact_id: str) -> str:
    """Get a contact by ID (GUID)."""
    return json.dumps(_c().get_contact(contact_id), indent=2)


@mcp.tool()
def create_contact(fields_json: str) -> str:
    """Create a contact. fields_json: JSON object with contact fields."""
    return json.dumps(_c().create_contact(**_fields(fields_json)), indent=2)


@mcp.tool()
def update_contact(contact_id: str, fields_json: str) -> str:
    """Update a contact by ID (GUID)."""
    return json.dumps(_c().update_contact(contact_id, **_fields(fields_json)), indent=2)


@mcp.tool()
def delete_contact(contact_id: str) -> str:
    """Delete a contact by ID (GUID)."""
    return json.dumps(_c().delete_contact(contact_id), indent=2)


# ── Time Entries ───────────────────────────────────────────────────────────────


@mcp.tool()
def list_time_entries(
    matter_id: str | None = None,
    page: int = 1,
    page_size: int = 25,
) -> str:
    """List time entries, paginated. Optional matter_id (GUID) filter — the only
    server-side filter the /v1 API honors for time entries."""
    return json.dumps(
        _c().list_time_entries(
            matter_id=matter_id,
            page=page,
            page_size=page_size,
        ),
        indent=2,
    )


@mcp.tool()
def get_time_entry(time_entry_id: str) -> str:
    """Get a time entry by ID (GUID)."""
    return json.dumps(_c().get_time_entry(time_entry_id), indent=2)


@mcp.tool()
def create_time_entry(fields_json: str) -> str:
    """Create a time entry. fields_json: JSON object. Required: matterId."""
    return json.dumps(_c().create_time_entry(**_fields(fields_json)), indent=2)


@mcp.tool()
def update_time_entry(time_entry_id: str, fields_json: str) -> str:
    """Update a time entry by ID (GUID)."""
    return json.dumps(
        _c().update_time_entry(time_entry_id, **_fields(fields_json)), indent=2
    )


@mcp.tool()
def delete_time_entry(time_entry_id: str) -> str:
    """Delete a time entry by ID (GUID)."""
    return json.dumps(_c().delete_time_entry(time_entry_id), indent=2)


# ── Expenses ───────────────────────────────────────────────────────────────────


@mcp.tool()
def list_expenses(page: int = 1, page_size: int = 25) -> str:
    """List expense cards, paginated (firm-wide). The /v1 API honors no server-side
    filter on expenses — not even matter_id — so none is offered."""
    return json.dumps(
        _c().list_expenses(page=page, page_size=page_size),
        indent=2,
    )


@mcp.tool()
def get_expense(expense_id: str) -> str:
    """Get an expense card by ID (GUID)."""
    return json.dumps(_c().get_expense(expense_id), indent=2)


@mcp.tool()
def create_expense(fields_json: str) -> str:
    """Create an expense card. fields_json: JSON object. Required: matterId."""
    return json.dumps(_c().create_expense(**_fields(fields_json)), indent=2)


@mcp.tool()
def update_expense(expense_id: str, fields_json: str) -> str:
    """Update an expense card by ID (GUID)."""
    return json.dumps(_c().update_expense(expense_id, **_fields(fields_json)), indent=2)


@mcp.tool()
def delete_expense(expense_id: str) -> str:
    """Delete an expense card by ID (GUID)."""
    return json.dumps(_c().delete_expense(expense_id), indent=2)


# ── Invoices ───────────────────────────────────────────────────────────────────


@mcp.tool()
def list_invoices(page: int = 1, page_size: int = 25) -> str:
    """List invoices with pagination."""
    return json.dumps(_c().list_invoices(page=page, page_size=page_size), indent=2)


@mcp.tool()
def get_invoice(invoice_id: str) -> str:
    """Get an invoice by ID (GUID)."""
    return json.dumps(_c().get_invoice(invoice_id), indent=2)


@mcp.tool()
def generate_invoice(
    matter_id: str,
    invoice_date: str = "",
    due_date: str = "",
    to_date: str = "",
) -> str:
    """[Not in LCS /v1] Generate an invoice via the legacy two-step billable-items +
    challenge-token flow. That flow was /api/v2-only and fails loudly here. Use
    create_invoice with the /v1 invoice body instead."""
    return json.dumps(
        _c().generate_invoice(
            matter_id,
            invoice_date=invoice_date or None,
            due_date=due_date or None,
            to_date=to_date or None,
        ),
        indent=2,
    )


@mcp.tool()
def list_billable_items(matter_id: str, to_date: str = "") -> str:
    """[Not in LCS /v1] Preview a matter's unbilled billable items with challenge
    tokens (the /api/v2 billing flow). Fails loudly."""
    return json.dumps(_c().list_billable_items(matter_id, to_date or None), indent=2)


@mcp.tool()
def create_invoice(fields_json: str) -> str:
    """Create an invoice via POST /v1/invoices. fields_json: JSON object with the
    invoice body. The API's 400 validation names any missing required fields."""
    return json.dumps(_c().create_invoice(**_fields(fields_json)), indent=2)


@mcp.tool()
def update_invoice(invoice_id: str, fields_json: str) -> str:
    """Update an invoice by ID (GUID)."""
    return json.dumps(_c().update_invoice(invoice_id, **_fields(fields_json)), indent=2)


@mcp.tool()
def delete_invoice(invoice_id: str) -> str:
    """Delete an invoice by ID (GUID)."""
    return json.dumps(_c().delete_invoice(invoice_id), indent=2)


@mcp.tool()
def approve_invoice(invoice_id: str, invoice_number: str) -> str:
    """[Not in LCS /v1] Approve a draft invoice for posting. Not exposed by /v1;
    fails loudly."""
    return json.dumps(_c().approve_invoice(invoice_id, invoice_number), indent=2)


# ── Payments ───────────────────────────────────────────────────────────────────


@mcp.tool()
def list_payments(page: int = 1, page_size: int = 25) -> str:
    """List invoice payments with pagination."""
    return json.dumps(_c().list_payments(page=page, page_size=page_size), indent=2)


@mcp.tool()
def create_payment(fields_json: str) -> str:
    """Create an invoice payment and allocate to invoices/trust."""
    return json.dumps(_c().create_payment(**_fields(fields_json)), indent=2)


@mcp.tool()
def get_invoice_allocations(fields_json: str | None = None) -> str:
    """[Not in LCS /v1] Get invoice allocation suggestions for a payment. Not exposed
    by /v1; fails loudly."""
    return json.dumps(_c().get_invoice_allocations(**_fields(fields_json)), indent=2)


# ── Transactions ───────────────────────────────────────────────────────────────


@mcp.tool()
def list_transactions(
    matter_id: str | None = None,
    bank_id: str | None = None,
    page: int = 1,
    page_size: int = 25,
) -> str:
    """List bank transactions for a matter or bank.

    The LCS /v1 transactions endpoint has no firm-wide listing — pass either a
    matter_id (GUID) or a bank_id. /v1 exposes no bank enumeration, so a bank_id must
    come from the CosmoLex UI."""
    return json.dumps(
        _c().list_transactions(
            matter_id=matter_id, bank_id=bank_id, page=page, page_size=page_size
        ),
        indent=2,
    )


@mcp.tool()
def get_transaction(transaction_id: str) -> str:
    """Get a transaction by ID (GUID)."""
    return json.dumps(_c().get_transaction(transaction_id), indent=2)


@mcp.tool()
def list_banks() -> str:
    """[Not in LCS /v1] List bank accounts. Bank enumeration is not exposed by the
    /v1 Integration API; this tool fails loudly. Get a bankId from the CosmoLex
    UI for create_transaction / list_transactions."""
    return json.dumps(_c().list_banks(), indent=2)


@mcp.tool()
def list_chart_of_accounts() -> str:
    """[Not in LCS /v1] List the chart of accounts. Not exposed by the /v1
    Integration API; this tool fails loudly."""
    return json.dumps(_c().list_chart_of_accounts(), indent=2)


@mcp.tool()
def create_transaction(fields_json: str) -> str:
    """Create a bank transaction (deposit/withdrawal) via POST /v1/transactions.

    fields_json: JSON object with the transaction body (needs a bankId — see
    list_transactions on bank enumeration). The API's 400 validation names any
    missing required fields."""
    return json.dumps(_c().create_transaction(**_fields(fields_json)), indent=2)


@mcp.tool()
def update_transaction(transaction_id: str, fields_json: str) -> str:
    """Update a transaction by ID (GUID)."""
    return json.dumps(
        _c().update_transaction(transaction_id, **_fields(fields_json)), indent=2
    )


@mcp.tool()
def delete_transaction(transaction_id: str) -> str:
    """Delete a transaction by ID (GUID)."""
    return json.dumps(_c().delete_transaction(transaction_id), indent=2)


# ── Documents ──────────────────────────────────────────────────────────────────


@mcp.tool()
def list_documents(page: int = 1, page_size: int = 25) -> str:
    """List documents, paginated (firm-wide, read-only). The /v1 API exposes no
    confirmed server-side filter for documents, so none is offered."""
    return json.dumps(_c().list_documents(page=page, page_size=page_size), indent=2)


@mcp.tool()
def get_document_default_app() -> str:
    """[Not in LCS /v1] /v1 documents is read-only (list only); document actions are
    not exposed. Fails loudly."""
    return json.dumps(_c().get_document_default_app(), indent=2)


@mcp.tool()
def get_document_download_url(fields_json: str) -> str:
    """[Not in LCS /v1] Signed download URLs are not exposed by /v1 (read-only
    documents). Fails loudly."""
    return json.dumps(_c().get_document_download_url(**_fields(fields_json)), indent=2)


@mcp.tool()
def get_document_upload_url(fields_json: str) -> str:
    """[Not in LCS /v1] Signed upload URLs are not exposed by /v1 (read-only
    documents). Fails loudly."""
    return json.dumps(_c().get_document_upload_url(**_fields(fields_json)), indent=2)


@mcp.tool()
def delete_document(path: str, doc_id: str) -> str:
    """[Not in LCS /v1] /v1 documents is read-only; delete is not exposed. Fails
    loudly."""
    return json.dumps(_c().delete_document(path=path, doc_id=doc_id), indent=2)


# ── Users / Timekeepers ────────────────────────────────────────────────────────


@mcp.tool()
def list_users(page: int = 1, page_size: int = 25) -> str:
    """List firm users (a.k.a. timekeepers) with pagination. Each carries email,
    roles, default rate, and status."""
    return json.dumps(_c().list_users(page=page, page_size=page_size), indent=2)


@mcp.tool()
def get_user(user_id: int) -> str:
    """Get a firm user by numeric ID."""
    return json.dumps(_c().get_user(user_id), indent=2)


@mcp.tool()
def list_timekeepers(
    page: int = 1, page_size: int = 25, active_only: bool | None = None
) -> str:
    """[Not in LCS /v1] Per-timekeeper billable/non-billable time summary is not in
    /v1; fails loudly. Use list_users for the firm's people list."""
    return json.dumps(
        _c().list_timekeepers(page=page, page_size=page_size, active_only=active_only),
        indent=2,
    )


# ── Firm ───────────────────────────────────────────────────────────────────────


@mcp.tool()
def get_firm_summary() -> str:
    """[Not in LCS /v1] Firm financial summary (balances, overdue, retainers) is not
    exposed by /v1; fails loudly."""
    return json.dumps(_c().get_firm_summary(), indent=2)


# ── Text Shortcuts ─────────────────────────────────────────────────────────────


@mcp.tool()
def list_text_shortcuts(page: int = 1, page_size: int = 25) -> str:
    """List text shortcuts/shorthands. The /v1 endpoint exists but the current OAuth
    app/user may not be authorized (returns a 403 until the scope is granted)."""
    return json.dumps(
        _c().list_text_shortcuts(page=page, page_size=page_size), indent=2
    )


@mcp.tool()
def get_text_shortcut(shortcut_id: int) -> str:
    """Get a text shortcut by ID (subject to the same /v1 authorization as
    list_text_shortcuts)."""
    return json.dumps(_c().get_text_shortcut(shortcut_id), indent=2)


# ── Codes ──────────────────────────────────────────────────────────────────────


@mcp.tool()
def get_codes(matter_id: str) -> str:
    """Get UTBMS codes for a matter (GUID) via GET /v1/codes?matterId=. matter_id is
    required."""
    return json.dumps(_c().get_codes(matter_id), indent=2)


@mcp.tool()
def get_task_codes(matter_id: str) -> str:
    """[Not in LCS /v1] Task/activity split is not exposed; /v1 has only the combined
    get_codes(matter_id). Fails loudly."""
    return json.dumps(_c().get_task_codes(matter_id), indent=2)


@mcp.tool()
def get_activity_codes(matter_id: str) -> str:
    """[Not in LCS /v1] Task/activity split is not exposed; /v1 has only the combined
    get_codes(matter_id). Fails loudly."""
    return json.dumps(_c().get_activity_codes(matter_id), indent=2)


# ── Lookups [Not in LCS /v1] ─────────────────────────────────────────────────────
# None of the legacy lookup endpoints exist in the LCS /v1 API; every tool below
# fails loudly. Kept registered for Toby's keep/drop call (see COVERAGE_DELTA).


@mcp.tool()
def get_new_matter_defaults() -> str:
    """[Not in LCS /v1] New-matter defaults lookup. Fails loudly."""
    return json.dumps(_c().get_new_matter_defaults(), indent=2)


@mcp.tool()
def get_new_matter_definition(matter_id: str | None = None) -> str:
    """[Not in LCS /v1] New-matter definition lookup. Fails loudly."""
    return json.dumps(_c().get_new_matter_definition(matter_id=matter_id), indent=2)


@mcp.tool()
def get_ebilling_defaults() -> str:
    """[Not in LCS /v1] eBilling defaults lookup. Fails loudly."""
    return json.dumps(_c().get_ebilling_defaults(), indent=2)


@mcp.tool()
def get_matter_type_workflow(matter_type_id: int) -> str:
    """[Not in LCS /v1] Matter-type workflow lookup. Fails loudly."""
    return json.dumps(_c().get_matter_type_workflow(matter_type_id), indent=2)


@mcp.tool()
def get_client_labels() -> str:
    """[Not in LCS /v1] Client labels lookup. Fails loudly."""
    return json.dumps(_c().get_client_labels(), indent=2)


@mcp.tool()
def get_matter_labels() -> str:
    """[Not in LCS /v1] Matter labels lookup. Fails loudly."""
    return json.dumps(_c().get_matter_labels(), indent=2)


@mcp.tool()
def get_client_suggestions(search: str | None = None) -> str:
    """[Not in LCS /v1] Client suggestions lookup. Fails loudly. Use list_clients."""
    return json.dumps(_c().get_client_suggestions(search=search), indent=2)


@mcp.tool()
def get_new_contact_defaults() -> str:
    """[Not in LCS /v1] New-contact defaults lookup. Fails loudly."""
    return json.dumps(_c().get_new_contact_defaults(), indent=2)


@mcp.tool()
def get_expense_lookups() -> str:
    """[Not in LCS /v1] Expense lookups. Fails loudly."""
    return json.dumps(_c().get_expense_lookups(), indent=2)


@mcp.tool()
def get_new_expense_lookups(matter_id: str | None = None) -> str:
    """[Not in LCS /v1] New-expense lookups. Fails loudly."""
    return json.dumps(_c().get_new_expense_lookups(matter_id=matter_id), indent=2)


@mcp.tool()
def get_invoice_lookups() -> str:
    """[Not in LCS /v1] Invoice lookups. Fails loudly."""
    return json.dumps(_c().get_invoice_lookups(), indent=2)


@mcp.tool()
def get_new_invoice_lookups(matter_id: str | None = None) -> str:
    """[Not in LCS /v1] New-invoice lookups. Fails loudly."""
    return json.dumps(_c().get_new_invoice_lookups(matter_id=matter_id), indent=2)


@mcp.tool()
def get_invoice_payment_lookups() -> str:
    """[Not in LCS /v1] Invoice-payment lookups. Fails loudly."""
    return json.dumps(_c().get_invoice_payment_lookups(), indent=2)


@mcp.tool()
def get_time_entry_lookups(matter_id: str | None = None) -> str:
    """[Not in LCS /v1] Time-entry lookups. Fails loudly."""
    return json.dumps(_c().get_time_entry_lookups(matter_id=matter_id), indent=2)


@mcp.tool()
def get_time_grid_lookups() -> str:
    """[Not in LCS /v1] Time-grid lookups. Fails loudly."""
    return json.dumps(_c().get_time_grid_lookups(), indent=2)


@mcp.tool()
def get_transaction_lookups() -> str:
    """[Not in LCS /v1] Transaction lookups. Fails loudly."""
    return json.dumps(_c().get_transaction_lookups(), indent=2)


@mcp.tool()
def get_hard_cost_expense_lookups(matter_id: str | None = None) -> str:
    """[Not in LCS /v1] Hard-cost-expense lookups. Fails loudly."""
    return json.dumps(_c().get_hard_cost_expense_lookups(matter_id=matter_id), indent=2)


# ── Accounts Payable [Not in LCS /v1] ────────────────────────────────────────────
# No AP endpoints exist in the LCS /v1 API; every tool below fails loudly. Kept
# registered for Toby's keep/drop call (see COVERAGE_DELTA).


@mcp.tool()
def list_ap_bills(page: int = 1, page_size: int = 25) -> str:
    """[Not in LCS /v1] List AP bills. Fails loudly."""
    return json.dumps(_c().list_ap_bills(page=page, page_size=page_size), indent=2)


@mcp.tool()
def get_ap_bill(bill_id: str) -> str:
    """[Not in LCS /v1] Get an AP bill. Fails loudly."""
    return json.dumps(_c().get_ap_bill(bill_id), indent=2)


@mcp.tool()
def create_ap_bill(fields_json: str) -> str:
    """[Not in LCS /v1] Create an AP bill. Fails loudly."""
    return json.dumps(_c().create_ap_bill(**_fields(fields_json)), indent=2)


@mcp.tool()
def update_ap_bill(bill_id: str, fields_json: str) -> str:
    """[Not in LCS /v1] Update an AP bill. Fails loudly."""
    return json.dumps(_c().update_ap_bill(bill_id, **_fields(fields_json)), indent=2)


@mcp.tool()
def delete_ap_bill(bill_id: str) -> str:
    """[Not in LCS /v1] Delete an AP bill. Fails loudly."""
    return json.dumps(_c().delete_ap_bill(bill_id), indent=2)


@mcp.tool()
def list_ap_payments(page: int = 1, page_size: int = 25) -> str:
    """[Not in LCS /v1] List AP payments. Fails loudly."""
    return json.dumps(_c().list_ap_payments(page=page, page_size=page_size), indent=2)


@mcp.tool()
def create_ap_payment(fields_json: str) -> str:
    """[Not in LCS /v1] Trigger an AP payment. Fails loudly."""
    return json.dumps(_c().create_ap_payment(**_fields(fields_json)), indent=2)


@mcp.tool()
def get_ap_payment_status(fields_json: str | None = None) -> str:
    """[Not in LCS /v1] AP payment status. Fails loudly."""
    return json.dumps(_c().get_ap_payment_status(**_fields(fields_json)), indent=2)


@mcp.tool()
def list_ap_vendors(page: int = 1, page_size: int = 25) -> str:
    """[Not in LCS /v1] List AP vendors. Fails loudly."""
    return json.dumps(_c().list_ap_vendors(page=page, page_size=page_size), indent=2)


@mcp.tool()
def get_ap_vendor(vendor_id: str) -> str:
    """[Not in LCS /v1] Get an AP vendor. Fails loudly."""
    return json.dumps(_c().get_ap_vendor(vendor_id), indent=2)


@mcp.tool()
def create_ap_vendor(fields_json: str) -> str:
    """[Not in LCS /v1] Create an AP vendor. Fails loudly."""
    return json.dumps(_c().create_ap_vendor(**_fields(fields_json)), indent=2)


@mcp.tool()
def update_ap_vendor(vendor_id: str, fields_json: str) -> str:
    """[Not in LCS /v1] Update an AP vendor. Fails loudly."""
    return json.dumps(
        _c().update_ap_vendor(vendor_id, **_fields(fields_json)), indent=2
    )


# ── Resources ─────────────────────────────────────────────────────────────────


@mcp.resource("cosmolex://users", mime_type="application/json")
def users_resource() -> str:
    """All firm users / timekeepers (email, roles, default rate, status)."""
    return json.dumps(_c().list_users(page=1, page_size=100), indent=2)


@mcp.resource("cosmolex://clients", mime_type="application/json")
def clients_resource() -> str:
    """The firm's clients (first page) — names, balances, and contact details."""
    return json.dumps(_c().list_clients(page=1, page_size=100), indent=2)


@mcp.resource("cosmolex://security-notes", mime_type="text/markdown")
def security_notes_resource() -> str:
    """Security posture for cosmolex-mcp.

    ## Credentials
    - **Scoped OAuth (ProfitSolv LCS /v1 Integration API).** Set up once via
      `cosmolex-mcp-setup`: it stores the integration's API key + OAuth
      client_id/client_secret and runs a one-time browser consent. There is NO
      password login, so the MCP never trips CosmoLex's single-session limit
      and never logs you out of your browser.
    - **COSMOLEX_API_KEY / COSMOLEX_CLIENT_ID / COSMOLEX_CLIENT_SECRET**:
      resolved via the OS keyring (file fallback `~/.cosmolex-mcp/.env`, chmod
      0600). The OAuth access + refresh tokens are cached in
      `~/.cosmolex-mcp/tokens.json` (chmod 0600). Data calls send
      `X-Api-Key` + `X-User-Token` headers; the client refreshes the access token
      with the (rotating) refresh token on expiry or a 401 — no browser, no password.
      Re-run setup only if the refresh token is revoked.

    ## Tool classification
    - **Read-only (safe):** list_matters, get_matter, list_clients, get_client,
      list_contacts, get_contact, list_time_entries, get_time_entry, list_expenses,
      get_expense, list_invoices, get_invoice, list_payments, list_transactions,
      get_transaction, list_documents, list_users, get_user, get_codes,
      list_text_shortcuts, get_text_shortcut.
    - **Write / side-effect:** create_matter, update_matter, delete_matter,
      create_client, update_client, delete_client, create_contact, update_contact,
      delete_contact, create_time_entry, update_time_entry, delete_time_entry,
      create_expense, update_expense, delete_expense, create_invoice, update_invoice,
      delete_invoice, create_payment, create_transaction, update_transaction,
      delete_transaction.
    - **Not in LCS /v1 (fail loud — kept for keep/drop review):** get_firm_summary,
      list_timekeepers, list_banks, list_chart_of_accounts, generate_invoice,
      list_billable_items, approve_invoice, get_invoice_allocations, the document
      actions, get_task_codes/get_activity_codes, all 17 lookups, all Accounts
      Payable tools.

    ## Data sensitivity
    Matters, time entries, invoices, transactions, and client records contain billable
    legal and financial data. Treat all matter-linked data as attorney-client
    privileged.
    """
    return security_notes_resource.__doc__ or ""


# ── Prompts ───────────────────────────────────────────────────────────────────


@mcp.prompt()
def matter_billing_review(matter_id: str) -> str:
    """Review unbilled time and outstanding invoices for a specific matter."""
    return f"""Review billing status for matter {matter_id}:

1. Call get_matter({matter_id}) — confirm matter name, billing method, and owner.
2. Call list_time_entries with matter_id={matter_id} — total hours and estimated value
   of unbilled entries.
3. Call list_invoices (firm-wide — there is no per-matter invoice filter; select the
   rows whose matter is {matter_id}); identify draft, sent, and overdue.
4. Output:
   - Matter: name | billing method | owner
   - Unbilled time: X entries | Y hours | $Z estimated
   - Invoices: draft | sent (unpaid) | paid this cycle
   - Recommended action: bill the matter / follow up on overdue / no action"""


@mcp.prompt()
def new_matter_intake(client_id: str) -> str:
    """Create a new matter for an existing client."""
    return f"""Open a new matter for client {client_id}:

1. Call get_client({client_id}) — confirm client name and status.
2. Decide the matter name and billing method from the client context.
3. Call create_matter with fields_json containing at least clientId={client_id} and a
   descriptive matter name. The API's 400 validation will name any other required
   fields; add them and retry.
4. Confirm matter created: return the new matter ID and name.
5. Call get_matter(<new_id>) — verify the saved record."""


@mcp.prompt()
def accounts_receivable_review() -> str:
    """Review outstanding invoices and recent payments for firm AR status."""
    return """Generate an accounts receivable summary for the firm:

1. Call list_invoices — group by status; flag any sent invoices with age > 30 days.
2. Call list_payments — identify recent payments applied in the last 30 days.
3. Output:
   - AR summary: Total outstanding | 0-30 days | 31-60 days | 60+ days
   - Payments: total applied this cycle
   - Recommended: which invoices to follow up on immediately (highest and oldest first)
   (Note: Accounts Payable and firm-summary tools are not available in the LCS /v1 API.)"""


def main():
    mcp.run()


if __name__ == "__main__":
    main()
