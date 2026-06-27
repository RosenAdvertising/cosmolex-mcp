#!/usr/bin/env python3
"""CosmoLex MCP server — NextGen ``/api/v2`` session-login tools.

The tool SURFACE (names, signatures, the ``_safe_tool``/``_fields``/``_params``
helpers, and the ``fields_json`` string args) is unchanged from the original LCS
build. Each tool now calls a NAMED client method (``LCSClient.list_clients`` etc.)
that hits the verified NextGen ``/api/v2`` REST API instead of the dead ``/v1``
LCS gateway. Tools whose resource has no ``/api/v2`` equivalent (the Lookups,
UTBMS Codes, Text Shortcuts groups, plus document writes, payment/AP-payment
creates, invoice approve, and AP delete) call client methods that raise a clear
"not available on NextGen /api/v2" ``RuntimeError`` — ``_safe_tool`` turns that
into a ``{"error": ...}`` JSON result, so the server still imports cleanly and the
tool count holds.
"""

import json
from functools import wraps

from mcp.server.fastmcp import FastMCP

from cosmolex_mcp.client import LCSClient

mcp = FastMCP(
    "cosmolex",
    instructions=(
        "CosmoLex legal practice management via the NextGen /api/v2 REST API "
        "(username/password session login). Manage matters, clients, contacts, "
        "time entries, expenses, invoices, payments, transactions, accounts "
        "payable (bills, vendors), and documents. Matters are the core entity — "
        "most billable resources link to a matter. Read tools (list_*/get_*) are "
        "safe; create_*/update_*/delete_* tools permanently modify live firm data. "
        "Some legacy lookup/code/text-shortcut tools and a few write flows are not "
        "available on NextGen /api/v2 and will return an explanatory error."
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


def _params(mapping: dict) -> dict:
    """Drop None values so the API receives a clean query string."""
    return {k: v for k, v in mapping.items() if v is not None}


# ── Clients ──────────────────────────────────────────────────────────────────


@mcp.tool()
def list_clients(
    page: int = 1,
    page_size: int = 25,
    active_only: bool | None = None,
    display_name: str | None = None,
    name: str | None = None,
    email: str | None = None,
) -> str:
    """List clients. Supports pagination and search by display_name, name, or email."""
    return json.dumps(
        _c().list_clients(
            page=page,
            page_size=page_size,
            active_only=active_only,
            display_name=display_name,
            name=name,
            email=email,
        ),
        indent=2,
    )


@mcp.tool()
def get_client(client_id: str) -> str:
    """Get a single client by ID."""
    return json.dumps(_c().get_client(client_id), indent=2)


@mcp.tool()
def create_client(fields_json: str) -> str:
    """Creates a new client in CosmoLex. WRITE: this permanently adds a record to
    live firm data.

    fields_json: JSON object. Required: name. Optional: displayName,
    contactSalutation, contactTitle, entityName, address1, clientAsEntity, email,
    secondaryEmail, cellPhoneNumber, workPhoneNumber, homePhoneNumber, notes."""
    return json.dumps(_c().create_client(**_fields(fields_json)), indent=2)


@mcp.tool()
def update_client(client_id: str, fields_json: str) -> str:
    """Updates an existing client by ID. WRITE: this permanently modifies live firm data.

    fields_json: JSON object with fields to update (displayName, name,
    contactSalutation, contactTitle, entityName, address1, clientAsEntity, email,
    secondaryEmail, cellPhoneNumber, workPhoneNumber, homePhoneNumber, notes)."""
    return json.dumps(_c().update_client(client_id, **_fields(fields_json)), indent=2)


@mcp.tool()
def delete_client(client_id: str) -> str:
    """Deletes a client by ID. WRITE: this permanently removes a record from live
    firm data and cannot be undone."""
    return json.dumps(_c().delete_client(client_id), indent=2)


# ── Matters ──────────────────────────────────────────────────────────────────


@mcp.tool()
def list_matters(
    page: int = 1,
    page_size: int = 25,
    active_only: bool | None = None,
    search_text: str | None = None,
    client_id: str | None = None,
    matter_owner_id: int | None = None,
    matter_type_id: int | None = None,
) -> str:
    """List matters. Supports pagination, search_text, and filters by client_id,
    matter_owner_id, matter_type_id, and active_only."""
    return json.dumps(
        _c().list_matters(
            page=page,
            page_size=page_size,
            active_only=active_only,
            search_text=search_text,
            client_id=client_id,
            matter_owner_id=matter_owner_id,
            matter_type_id=matter_type_id,
        ),
        indent=2,
    )


@mcp.tool()
def get_matter(matter_id: str) -> str:
    """Get a single matter by ID."""
    return json.dumps(_c().get_matter(matter_id), indent=2)


@mcp.tool()
def create_matter(fields_json: str) -> str:
    """Creates a new matter in CosmoLex. WRITE: this permanently adds a record to
    live firm data.

    fields_json: JSON object. Common fields: clientId, billingMethod, dateOpened,
    matterOwnerId, areaOfLawId, matterName, matterFileNumber, notes, matterTypeId."""
    return json.dumps(_c().create_matter(**_fields(fields_json)), indent=2)


@mcp.tool()
def update_matter(matter_id: str, fields_json: str) -> str:
    """Updates an existing matter by ID. WRITE: this permanently modifies live firm data.

    fields_json: JSON object with fields to update (billingMethod, dateOpened,
    matterOwnerId, clientId, areaOfLawId, matterName, matterFileNumber, notes,
    matterTypeId)."""
    return json.dumps(_c().update_matter(matter_id, **_fields(fields_json)), indent=2)


@mcp.tool()
def delete_matter(matter_id: str) -> str:
    """Deletes a matter by ID. WRITE: this permanently removes a record from live
    firm data and cannot be undone."""
    return json.dumps(_c().delete_matter(matter_id), indent=2)


# ── Contacts ─────────────────────────────────────────────────────────────────


@mcp.tool()
def list_contacts(
    page: int = 1, page_size: int = 25, active_only: bool | None = None
) -> str:
    """List contacts. Supports pagination and active_only filter."""
    return json.dumps(
        _c().list_contacts(page=page, page_size=page_size, active_only=active_only),
        indent=2,
    )


@mcp.tool()
def get_contact(contact_id: str) -> str:
    """Get a single contact by ID."""
    return json.dumps(_c().get_contact(contact_id), indent=2)


@mcp.tool()
def create_contact(fields_json: str) -> str:
    """Creates a new contact in CosmoLex. WRITE: this permanently adds a record to
    live firm data.

    fields_json: JSON object. Fields: active, contactType, contactTypeLabel,
    contact (nested contact details object)."""
    return json.dumps(_c().create_contact(**_fields(fields_json)), indent=2)


@mcp.tool()
def update_contact(contact_id: str, fields_json: str) -> str:
    """Updates an existing contact by ID. WRITE: this permanently modifies live firm data.

    fields_json: JSON object with fields to update (active, contactType,
    contactTypeLabel, contact)."""
    return json.dumps(_c().update_contact(contact_id, **_fields(fields_json)), indent=2)


@mcp.tool()
def delete_contact(contact_id: str) -> str:
    """Deletes a contact by ID. WRITE: this permanently removes a record from live
    firm data and cannot be undone."""
    return json.dumps(_c().delete_contact(contact_id), indent=2)


# ── Time Entries ─────────────────────────────────────────────────────────────


@mcp.tool()
def list_time_entries(
    page: int = 1,
    page_size: int = 25,
    matter_id: str | None = None,
    rate_type: str | None = None,
    billing_status: str | None = None,
    card_status: str | None = None,
    timekeeper_id: int | None = None,
) -> str:
    """List time entries. Filter by matter_id, rate_type, billing_status,
    card_status, and timekeeper_id."""
    return json.dumps(
        _c().list_time_entries(
            page=page,
            page_size=page_size,
            matter_id=matter_id,
            rate_type=rate_type,
            billing_status=billing_status,
            card_status=card_status,
            timekeeper_id=timekeeper_id,
        ),
        indent=2,
    )


@mcp.tool()
def get_time_entry(time_entry_id: str) -> str:
    """Get a single time entry by ID."""
    return json.dumps(_c().get_time_entry(time_entry_id), indent=2)


@mcp.tool()
def create_time_entry(fields_json: str) -> str:
    """Creates a new time entry in CosmoLex. WRITE: this permanently adds a record to
    live firm data.

    fields_json: JSON object. Required: matterId. Common fields: date, description,
    task, hours, rate, timeKeeperId, billingStatus, utbmsCodeActivity, value."""
    return json.dumps(_c().create_time_entry(**_fields(fields_json)), indent=2)


@mcp.tool()
def update_time_entry(time_entry_id: str, fields_json: str) -> str:
    """Updates an existing time entry by ID. WRITE: this permanently modifies live
    firm data.

    fields_json: JSON object with fields to update (matterId, billingStatus, date,
    description, task, hold, hours, rate, timeBilled, timeKeeperId, rateTypeId,
    utbmsCodeActivityId, taxable)."""
    return json.dumps(
        _c().update_time_entry(time_entry_id, **_fields(fields_json)), indent=2
    )


@mcp.tool()
def delete_time_entry(time_entry_id: str) -> str:
    """Deletes a time entry by ID. WRITE: this permanently removes a record from live
    firm data and cannot be undone."""
    return json.dumps(_c().delete_time_entry(time_entry_id), indent=2)


# ── Expense ──────────────────────────────────────────────────────────────────


@mcp.tool()
def list_expenses(
    page: int = 1,
    page_size: int = 25,
    billing_type_id: int | None = None,
    billing_status_id: int | None = None,
    is_matter_active: bool | None = None,
) -> str:
    """List expense cards. Filter by billing_type_id, billing_status_id, and
    is_matter_active."""
    return json.dumps(
        _c().list_expenses(
            page=page,
            page_size=page_size,
            billing_type_id=billing_type_id,
            billing_status_id=billing_status_id,
            is_matter_active=is_matter_active,
        ),
        indent=2,
    )


@mcp.tool()
def get_expense(expense_card_id: str) -> str:
    """Get a single expense card by ID."""
    return json.dumps(_c().get_expense(expense_card_id), indent=2)


@mcp.tool()
def create_expense(fields_json: str) -> str:
    """Creates a new expense card in CosmoLex. WRITE: this permanently adds a record
    to live firm data.

    fields_json: JSON object. Required: matterId. Common fields: billingType,
    creationDate, code, description, notes, expenseName, ratePrice, rateTypeId,
    quantity, value, timeKeeperId, labels, taxable."""
    return json.dumps(_c().create_expense(**_fields(fields_json)), indent=2)


@mcp.tool()
def update_expense(expense_card_id: str, fields_json: str) -> str:
    """Updates an existing expense card by ID. WRITE: this permanently modifies live
    firm data.

    fields_json: JSON object with fields to update (matterId, expenseName,
    description, timekeeperId, rate, quantity, billingStatusId, billingTypeId,
    expenseCode, labels)."""
    return json.dumps(
        _c().update_expense(expense_card_id, **_fields(fields_json)), indent=2
    )


@mcp.tool()
def delete_expense(expense_card_id: str) -> str:
    """Deletes an expense card by ID. WRITE: this permanently removes a record from
    live firm data and cannot be undone."""
    return json.dumps(_c().delete_expense(expense_card_id), indent=2)


# ── Invoices ─────────────────────────────────────────────────────────────────


@mcp.tool()
def list_invoices(
    page: int = 1,
    page_size: int = 25,
    status: str | None = None,
    matter_id: str | None = None,
    client_id: str | None = None,
    invoice_number: str | None = None,
    is_draft: bool | None = None,
) -> str:
    """List invoices. Filter by status, matter_id, client_id, invoice_number, and
    is_draft."""
    return json.dumps(
        _c().list_invoices(
            page=page,
            page_size=page_size,
            status=status,
            matter_id=matter_id,
            client_id=client_id,
            invoice_number=invoice_number,
            is_draft=is_draft,
        ),
        indent=2,
    )


@mcp.tool()
def get_invoice(invoice_id: str) -> str:
    """Get a single invoice by ID."""
    return json.dumps(_c().get_invoice(invoice_id), indent=2)


@mcp.tool()
def create_invoice(fields_json: str) -> str:
    """Creates a new invoice in CosmoLex. WRITE: this permanently adds a record to
    live firm data.

    fields_json: JSON object. Required: matterId, invoiceDate, dueDate,
    includeTimecardsToDate. Optional: invoiceNumber, invoiceAmount, description,
    discountAmount, discountType, financeChargeAmount, lateFees, otherFees,
    timeList, expenseList, sharedViaClientPortal, showCoverPage."""
    return json.dumps(_c().create_invoice(**_fields(fields_json)), indent=2)


@mcp.tool()
def update_invoice(invoice_id: str, fields_json: str) -> str:
    """Updates an existing invoice by ID. WRITE: this permanently modifies live firm data.

    fields_json: JSON object with fields to update (matterId, description,
    invoiceNumber, invoiceDate, dueDate, invoiceAmount, discountAmount, discountType,
    financeChargeAmount, lateFees, otherFees, timeList, expenseList,
    sharedViaClientPortal, showCoverPage)."""
    return json.dumps(_c().update_invoice(invoice_id, **_fields(fields_json)), indent=2)


@mcp.tool()
def delete_invoice(invoice_id: str) -> str:
    """Deletes an invoice by ID. WRITE: this permanently removes a record from live
    firm data and cannot be undone."""
    return json.dumps(_c().delete_invoice(invoice_id), indent=2)


@mcp.tool()
def approve_invoice(invoice_id: str, fields_json: str = "{}") -> str:
    """Approves an invoice by ID. WRITE: finalizes the invoice for posting against
    live firm data and may trigger client billing.

    fields_json: JSON object. Required: invoiceNumber (the number to assign on
    approval). NOTE: not available on NextGen /api/v2 — returns an error until the
    NextGen approval flow is captured live."""
    return json.dumps(_c().approve_invoice(invoice_id, **_fields(fields_json)), indent=2)


# ── Payments ─────────────────────────────────────────────────────────────────


@mcp.tool()
def list_payments(
    page: int = 1,
    page_size: int = 25,
    matter_id: str | None = None,
    invoice_id: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
) -> str:
    """List payments. Filter by matter_id, invoice_id, and a start_date/end_date
    range (ISO YYYY-MM-DD)."""
    return json.dumps(
        _c().list_payments(
            page=page,
            page_size=page_size,
            matter_id=matter_id,
            invoice_id=invoice_id,
            start_date=start_date,
            end_date=end_date,
        ),
        indent=2,
    )


@mcp.tool()
def create_payment(fields_json: str) -> str:
    """Creates a new payment in CosmoLex and allocates it to invoices/trust. WRITE:
    this permanently records a financial transaction in live firm data.

    fields_json: JSON object. Required: paymentMethodId, paymentSource, receivedFrom,
    destinationOperatingBankId, applyOverpaymentToMatterId, memo, matters. Optional:
    matterId, clientId, invoiceId, amount, overpaymentAmount, referenceNumber,
    paymentDate, sourceTrustBankId, sourceOperatingBankId, writeOffRemainingBalance.
    NOTE: not available on NextGen /api/v2 — returns an error until the NextGen
    payment-create flow is captured live."""
    return json.dumps(_c().create_payment(**_fields(fields_json)), indent=2)


@mcp.tool()
def get_payment_invoice_allocations(
    payment_source_id: int,
    destination_operating_bank_id: str,
    amount: float | None = None,
    matter_id: str | None = None,
    invoice_id: str | None = None,
    client_id: str | None = None,
    payment_filter_option_id: int | None = None,
    source_trust_bank_id: str | None = None,
    source_operating_bank_id: str | None = None,
) -> str:
    """Get invoice allocations via /api/v2/allocation. Requires invoice_id (an
    unfiltered allocation read is rejected by NextGen). The legacy payment-source
    params are accepted for API compatibility."""
    return json.dumps(
        _c().get_payment_invoice_allocations(
            invoice_id=invoice_id,
            matter_id=matter_id,
            client_id=client_id,
        ),
        indent=2,
    )


# ── Transactions ─────────────────────────────────────────────────────────────


@mcp.tool()
def list_transactions(
    page: int = 1,
    page_size: int = 25,
    bank_id: str | None = None,
    bank_type: int | None = None,
    matter_id: str | None = None,
    transaction_type: str | None = None,
    transaction_status: str | None = None,
) -> str:
    """List bank transactions. Filter by bank_id, bank_type, matter_id,
    transaction_type, and transaction_status."""
    return json.dumps(
        _c().list_transactions(
            page=page,
            page_size=page_size,
            bank_id=bank_id,
            bank_type=bank_type,
            matter_id=matter_id,
            transaction_type=transaction_type,
            transaction_status=transaction_status,
        ),
        indent=2,
    )


@mcp.tool()
def get_transaction(transaction_id: str) -> str:
    """Get a single transaction by ID."""
    return json.dumps(_c().get_transaction(transaction_id), indent=2)


@mcp.tool()
def create_transaction(fields_json: str) -> str:
    """Creates a new bank transaction in CosmoLex. WRITE: this permanently records a
    financial transaction in live firm data.

    fields_json: JSON object. Required: amount, bankId, matterId, transactionDate,
    transactionType. Optional: description, memo1, payeeName, transactionMethod,
    transactionStatus, allocations, preTaxAmount, paidTax1Amount, paidTax2Amount,
    referenceNumber, payorName."""
    return json.dumps(_c().create_transaction(**_fields(fields_json)), indent=2)


@mcp.tool()
def update_transaction(transaction_id: str, fields_json: str) -> str:
    """Updates an existing transaction by ID. WRITE: this permanently modifies live
    firm data.

    fields_json: JSON object with fields to update (matterId, transactionType,
    transactionDate, amount, description, bankId, challenge, memo1, payeeName,
    transactionMethod, transactionStatus, allocations, referenceNumber, payorName)."""
    return json.dumps(
        _c().update_transaction(transaction_id, **_fields(fields_json)), indent=2
    )


@mcp.tool()
def delete_transaction(transaction_id: str) -> str:
    """Deletes a transaction by ID. WRITE: this permanently removes a record from
    live firm data and cannot be undone."""
    return json.dumps(_c().delete_transaction(transaction_id), indent=2)


# ── Accounts Payable — Bills ─────────────────────────────────────────────────


@mcp.tool()
def list_ap_bills(
    page: int = 1,
    page_size: int = 25,
    status: str | None = None,
    paid: bool | None = None,
    is_credit: bool | None = None,
    payee_name: str | None = None,
) -> str:
    """List accounts payable bills. Filter by status, paid, is_credit, and
    payee_name."""
    return json.dumps(
        _c().list_ap_bills(
            page=page,
            page_size=page_size,
            status=status,
            paid=paid,
            is_credit=is_credit,
            payee_name=payee_name,
        ),
        indent=2,
    )


@mcp.tool()
def get_ap_bill(bill_id: str) -> str:
    """Get a single accounts payable bill by ID."""
    return json.dumps(_c().get_ap_bill(bill_id), indent=2)


@mcp.tool()
def create_ap_bill(fields_json: str) -> str:
    """Creates a new accounts payable bill in CosmoLex. WRITE: this permanently adds
    a record to live firm data.

    fields_json: JSON object. Required: allocations, amount, date, isRecurring,
    payeeName. Optional: dueDate, discount, financeCharge, recurringPeriod, memo1,
    memo2, referenceNumber, notes, isCredit, expenses, address1, city, stateId, zip."""
    return json.dumps(_c().create_ap_bill(**_fields(fields_json)), indent=2)


@mcp.tool()
def update_ap_bill(bill_id: str, fields_json: str) -> str:
    """Updates an existing accounts payable bill by ID. WRITE: this permanently
    modifies live firm data.

    fields_json: JSON object with fields to update. Required: isRecurring. Optional:
    date, dueDate, discount, financeCharge, recurringPeriod, payeeName, amount,
    memo1, memo2, referenceNumber, notes, isCredit, allocations, expenses."""
    return json.dumps(_c().update_ap_bill(bill_id, **_fields(fields_json)), indent=2)


@mcp.tool()
def delete_ap_bill(bill_id: str) -> str:
    """Deletes an accounts payable bill by ID. WRITE: this permanently removes a
    record from live firm data and cannot be undone. NOTE: not available on NextGen
    /api/v2 — returns an error until the NextGen delete verb is captured live."""
    return json.dumps(_c().delete_ap_bill(bill_id), indent=2)


# ── Accounts Payable — Vendors ───────────────────────────────────────────────


@mcp.tool()
def list_ap_vendors(
    page: int = 1,
    page_size: int = 25,
    search: str | None = None,
    email: str | None = None,
    active_only: bool | None = None,
) -> str:
    """List accounts payable vendors. Filter by search, email, and active_only."""
    return json.dumps(
        _c().list_ap_vendors(
            page=page,
            page_size=page_size,
            search=search,
            email=email,
            active_only=active_only,
        ),
        indent=2,
    )


@mcp.tool()
def get_ap_vendor(vendor_id: str) -> str:
    """Get a single accounts payable vendor by ID."""
    return json.dumps(_c().get_ap_vendor(vendor_id), indent=2)


@mcp.tool()
def create_ap_vendor(fields_json: str) -> str:
    """Creates a new accounts payable vendor in CosmoLex. WRITE: this permanently
    adds a record to live firm data.

    fields_json: JSON object. Required: payeeName, printAs. Optional: active,
    displayName, name, entityName, email, phoneNumber, fax, cellPhoneNumber,
    address1, city, stateId, zip, countryId, taxID, eligibleFor1099, contactName,
    notes."""
    return json.dumps(_c().create_ap_vendor(**_fields(fields_json)), indent=2)


@mcp.tool()
def update_ap_vendor(vendor_id: str, fields_json: str) -> str:
    """Updates an existing accounts payable vendor by ID. WRITE: this permanently
    modifies live firm data.

    fields_json: JSON object with fields to update (active, displayName, payeeName,
    name, entityName, email, phoneNumber, fax, cellPhoneNumber, address1, city,
    stateId, zip, countryId, printAs, taxID, eligibleFor1099, contactName, notes)."""
    return json.dumps(_c().update_ap_vendor(vendor_id, **_fields(fields_json)), indent=2)


# ── Accounts Payable — Payments ──────────────────────────────────────────────


@mcp.tool()
def list_ap_payments(
    page: int = 1,
    page_size: int = 25,
    status: str | None = None,
    vendor: str | None = None,
    bill_id: str | None = None,
) -> str:
    """List accounts payable payments. Filter by status, vendor, and bill_id. NOTE:
    not available on NextGen /api/v2 — returns an error until captured live."""
    return json.dumps(
        _c().list_ap_payments(
            page=page,
            page_size=page_size,
            status=status,
            vendor=vendor,
            bill_id=bill_id,
        ),
        indent=2,
    )


@mcp.tool()
def get_ap_payment_status(bill_ids: str) -> str:
    """Get payment status for one or more accounts payable bills. bill_ids: a
    comma-separated list of bill IDs (maps to the spec BillIds query param). NOTE:
    not available on NextGen /api/v2 — returns an error until captured live."""
    return json.dumps(_c().get_ap_payment_status(BillIds=bill_ids), indent=2)


@mcp.tool()
def create_ap_payment(fields_json: str) -> str:
    """Creates a new accounts payable payment in CosmoLex. WRITE: this permanently
    records a financial disbursement against live firm data.

    fields_json: JSON object. Required: amount, bankId, bills, date, memo1, payee,
    transactionMethod, transactionType. Optional: memo2, PrintAs, referenceNro,
    address1, city, stateId, countryId, zip. NOTE: not available on NextGen
    /api/v2 — returns an error until captured live."""
    return json.dumps(_c().create_ap_payment(**_fields(fields_json)), indent=2)


# ── Documents ────────────────────────────────────────────────────────────────


@mcp.tool()
def list_documents(
    matter_id: str | None = None,
    path: str | None = None,
    doc_id: str | None = None,
    file_name: str | None = None,
) -> str:
    """List documents and folders. Filter by matter_id, path, doc_id, or file_name."""
    return json.dumps(
        _c().list_documents(
            matter_id=matter_id, path=path, doc_id=doc_id, file_name=file_name
        ),
        indent=2,
    )


@mcp.tool()
def get_document_default_application() -> str:
    """Get the default document gateway application configured for the firm. NOTE:
    not available on NextGen /api/v2 — returns an error until captured live."""
    return json.dumps(_c().get_document_default_application(), indent=2)


@mcp.tool()
def get_document_download_url(fields_json: str) -> str:
    """Generate a signed download URL for a document.

    fields_json: JSON object. Required: fileId, fileName, filePath. NOTE: not
    available on NextGen /api/v2 — returns an error until captured live."""
    return json.dumps(_c().get_document_download_url(**_fields(fields_json)), indent=2)


@mcp.tool()
def get_document_upload_url(fields_json: str) -> str:
    """Generate a signed upload URL for a document. WRITE: this provisions an upload
    slot that adds a document to live firm data once the upload completes.

    fields_json: JSON object. Required: fileContentType, fileId, fileName, filePath,
    parentFolderId. NOTE: not available on NextGen /api/v2 — returns an error until
    captured live."""
    return json.dumps(_c().get_document_upload_url(**_fields(fields_json)), indent=2)


@mcp.tool()
def delete_document(fields_json: str) -> str:
    """Deletes a document or folder. WRITE: this permanently removes a record from
    live firm data and cannot be undone.

    fields_json: JSON object. Required: id, itemType, path. NOTE: not available on
    NextGen /api/v2 — returns an error until captured live."""
    return json.dumps(_c().delete_document(**_fields(fields_json)), indent=2)


# ── Timekeepers (Users) ──────────────────────────────────────────────────────


@mcp.tool()
def list_users(
    page: int = 1, page_size: int = 25, active_only: bool | None = None
) -> str:
    """List users/timekeepers. Supports pagination and active_only filter."""
    return json.dumps(
        _c().list_users(page=page, page_size=page_size, active_only=active_only),
        indent=2,
    )


@mcp.tool()
def get_user(user_id: str) -> str:
    """Get a single user/timekeeper by ID."""
    return json.dumps(_c().get_user(user_id), indent=2)


# ── Code Lookups ─────────────────────────────────────────────────────────────


@mcp.tool()
def list_task_codes(matter_id: str | None = None) -> str:
    """List UTBMS task codes, optionally scoped to a matter_id. NOTE: not available
    on NextGen /api/v2 — returns an error until the NextGen source is discovered."""
    return json.dumps(_c().get_task_codes(matter_id), indent=2)


@mcp.tool()
def list_activity_codes(matter_id: str | None = None) -> str:
    """List UTBMS activity codes, optionally scoped to a matter_id. NOTE: not
    available on NextGen /api/v2 — returns an error until discovered."""
    return json.dumps(_c().get_activity_codes(matter_id), indent=2)


@mcp.tool()
def list_codes(matter_id: str | None = None) -> str:
    """List all UTBMS task and activity codes in one call, optionally scoped to a
    matter_id. NOTE: not available on NextGen /api/v2 — returns an error until
    discovered."""
    return json.dumps(_c().get_codes(matter_id), indent=2)


# ── Text Shortcuts ───────────────────────────────────────────────────────────


@mcp.tool()
def list_text_shortcuts(page: int = 1, page_size: int = 25) -> str:
    """List text shortcuts/shorthands with pagination. NOTE: not available on
    NextGen /api/v2 — returns an error until discovered."""
    return json.dumps(_c().list_text_shortcuts(page=page, page_size=page_size), indent=2)


@mcp.tool()
def get_text_shortcut(shortcut_id: str) -> str:
    """Get a single text shortcut by ID. NOTE: not available on NextGen /api/v2 —
    returns an error until discovered."""
    return json.dumps(_c().get_text_shortcut(shortcut_id), indent=2)


# ── Lookups ──────────────────────────────────────────────────────────────────
# The LCS /v1/lookups/* surface is dead on NextGen; these tools call client
# methods that raise an explanatory error (NextGen form-defaults live under
# /api/gui/form/* and /api/v2/resourcedef/*, pending live discovery).


@mcp.tool()
def lookup_clients(query: str | None = None) -> str:
    """Look up clients for the matter client selector. Optional query: search text.
    NOTE: not available on NextGen /api/v2 — returns an error until discovered."""
    return json.dumps(_c().lookup_clients(query), indent=2)


@mcp.tool()
def lookup_client_labels(query: str | None = None) -> str:
    """Look up active client labels. Optional query: search text. NOTE: not
    available on NextGen /api/v2 — returns an error until discovered."""
    return json.dumps(_c().lookup_client_labels(query), indent=2)


@mcp.tool()
def lookup_matter_labels(query: str | None = None) -> str:
    """Look up active matter labels. Optional query: search text. NOTE: not
    available on NextGen /api/v2 — returns an error until discovered."""
    return json.dumps(_c().lookup_matter_labels(query), indent=2)


@mcp.tool()
def lookup_matter_type_workflow(matter_type_id: str) -> str:
    """Get the workflow statuses for a given matter type ID. NOTE: not available on
    NextGen /api/v2 — returns an error until discovered."""
    return json.dumps(_c().lookup_matter_type_workflow(matter_type_id), indent=2)


@mcp.tool()
def lookup_new_contact_form() -> str:
    """Get defaults and lookup lists for the new-contact form. NOTE: not available
    on NextGen /api/v2 — returns an error until discovered."""
    return json.dumps(_c().lookup_new_contact_form(), indent=2)


@mcp.tool()
def lookup_new_matter_definition() -> str:
    """Get the NextGen form definition and defaults for creating a new matter. NOTE:
    not available on NextGen /api/v2 — returns an error until discovered."""
    return json.dumps(_c().lookup_new_matter_definition(), indent=2)


@mcp.tool()
def lookup_new_matter_definition_for_matter(matter_id: str) -> str:
    """Get the NextGen form definition and defaults for an existing matter by ID.
    NOTE: not available on NextGen /api/v2 — returns an error until discovered."""
    return json.dumps(_c().lookup_new_matter_definition_for_matter(matter_id), indent=2)


@mcp.tool()
def lookup_new_matter_defaults() -> str:
    """Get the global defaults (billing methods, owners, types) for a new matter.
    NOTE: not available on NextGen /api/v2 — returns an error until discovered."""
    return json.dumps(_c().lookup_new_matter_defaults(), indent=2)


@mcp.tool()
def lookup_new_matter_ebilling_defaults() -> str:
    """Get the eBilling defaults for enabling electronic billing on a new matter.
    NOTE: not available on NextGen /api/v2 — returns an error until discovered."""
    return json.dumps(_c().lookup_new_matter_ebilling_defaults(), indent=2)


@mcp.tool()
def lookup_expense(matter_id: str | None = None) -> str:
    """Get all lookup data required to create expense cards, optionally scoped to a
    matter_id. NOTE: not available on NextGen /api/v2 — returns an error until
    discovered."""
    return json.dumps(_c().lookup_expense(matter_id), indent=2)


@mcp.tool()
def lookup_new_expense() -> str:
    """Get lookup values for creating a new soft-cost expense card. NOTE: not
    available on NextGen /api/v2 — returns an error until discovered."""
    return json.dumps(_c().lookup_new_expense(), indent=2)


@mcp.tool()
def lookup_new_expense_info(matter_id: str | None = None) -> str:
    """Get matter-specific lookup info for a new expense card (matter_id). NOTE: not
    available on NextGen /api/v2 — returns an error until discovered."""
    return json.dumps(_c().lookup_new_expense_info(matter_id), indent=2)


@mcp.tool()
def lookup_new_hard_cost_expense(matter_id: str | None = None) -> str:
    """Get matter-specific lookup values for a new hard-cost expense (matter_id).
    NOTE: not available on NextGen /api/v2 — returns an error until discovered."""
    return json.dumps(_c().lookup_new_hard_cost_expense(matter_id), indent=2)


@mcp.tool()
def lookup_invoice_payments() -> str:
    """Get the lookup lists for invoice payment dropdowns. NOTE: not available on
    NextGen /api/v2 — returns an error until discovered."""
    return json.dumps(_c().lookup_invoice_payments(), indent=2)


@mcp.tool()
def lookup_invoice(matter_id: str | None = None) -> str:
    """Get all lookup data required to create invoices, optionally scoped to a
    matter_id. NOTE: not available on NextGen /api/v2 — returns an error until
    discovered."""
    return json.dumps(_c().lookup_invoice(matter_id), indent=2)


@mcp.tool()
def lookup_new_invoice() -> str:
    """Get lookup values for creating a new invoice. NOTE: not available on NextGen
    /api/v2 — returns an error until discovered."""
    return json.dumps(_c().lookup_new_invoice(), indent=2)


@mcp.tool()
def lookup_new_invoice_info(matter_id: str | None = None) -> str:
    """Get matter-specific lookup info for a new invoice (matter_id). NOTE: not
    available on NextGen /api/v2 — returns an error until discovered."""
    return json.dumps(_c().lookup_new_invoice_info(matter_id), indent=2)


@mcp.tool()
def lookup_new_time_entry(matter_id: str | None = None) -> str:
    """Get lookup values for creating a new time entry (matter_id). NOTE: not
    available on NextGen /api/v2 — returns an error until discovered."""
    return json.dumps(_c().lookup_new_time_entry(matter_id), indent=2)


@mcp.tool()
def lookup_new_timesheet_from_grid() -> str:
    """Get lookup values for creating time entries from the time grid. NOTE: not
    available on NextGen /api/v2 — returns an error until discovered."""
    return json.dumps(_c().lookup_new_timesheet_from_grid(), indent=2)


@mcp.tool()
def lookup_new_transaction(
    transaction_type: str | None = None,
    context: str | None = None,
    context_id: str | None = None,
) -> str:
    """Get lookup values for creating a new transaction. Optional filters:
    transaction_type, context, context_id. NOTE: not available on NextGen /api/v2 —
    returns an error until discovered."""
    return json.dumps(
        _c().lookup_new_transaction(
            transaction_type=transaction_type, context=context, context_id=context_id
        ),
        indent=2,
    )


# ── Prompts ──────────────────────────────────────────────────────────────────


@mcp.prompt()
def new_matter_intake(client_id: str) -> str:
    """Open a new matter for an existing client with correct defaults."""
    return f"""Open a new matter for client {client_id}:

1. Call get_client({client_id}) — confirm client name and status.
2. Call lookup_new_matter_defaults — retrieve available billing methods, owners, and types.
3. Call lookup_matter_labels — identify appropriate labels for this matter type.
4. Determine the matter type and billing method from the client context.
5. Call create_matter with fields_json containing:
   clientId={client_id}, billingMethod (from defaults), matterOwnerId (from defaults),
   matterName (descriptive), dateOpened (today), and areaOfLawId if applicable.
6. Confirm matter created: return matter ID, name, and billing method.
7. Call lookup_new_matter_definition_for_matter(matter_id=<new_id>) for required fields."""


@mcp.prompt()
def ar_ap_review() -> str:
    """Review outstanding invoices and accounts payable bills for firm AR/AP status."""
    return """Generate an accounts receivable and payable summary for the firm:

1. Call list_invoices — group by status; flag any sent invoices aged > 30 days.
2. Call list_payments — identify payments applied in the last 30 days.
3. Call list_ap_bills — list outstanding AP bills, filtering paid=false.
4. Call list_ap_vendors — cross-reference vendor names for the AP list.
5. Call lookup_invoice_payments — confirm available payment methods on file.
6. Output:
   - AR summary: Total outstanding | 0–30 days | 31–60 days | 60+ days
   - AP summary: Total owed | Number of open bills | Top 3 vendors by amount
   - Recommended: which invoices to follow up on first (highest and oldest)."""


def main():
    mcp.run()


if __name__ == "__main__":
    main()
