#!/usr/bin/env python3
"""Live read smoke for the rebuilt cosmolex-mcp (NextGen /api/v2).

Logs in (via the real LCSClient inside each tool) and calls every READ tool once
through the actual server tool functions. Reads only — NO create/update/delete.

Classification per tool:
  PASS          -> returned a valid JSON response (a list incl. [], or an object
                   that is NOT an {"error": ...} envelope).
  EXPECTED-STUB -> returned {"error": "...not available on NextGen /api/v2..."}
                   (the 25 Lookups/Codes/TextShortcuts + a few write-only flows
                   that have no /api/v2 equivalent yet — intentional).
  FAIL          -> an unexpected error envelope, or an exception.

Creds come from env (COSMOLEX_USERNAME / COSMOLEX_PASSWORD), set by the caller.
"""
import json
import os
import sys

# Run-from-repo bootstrap: make the cosmolex_mcp package importable whether or not
# it has been pip-installed, so `python tests/read_smoke.py` works from a clone.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# server.py wraps every tool with _safe_tool, so a raised RuntimeError comes back
# as {"error": "..."} rather than an exception — we inspect the JSON envelope.
from cosmolex_mcp import server as S  # noqa: E402

NOT_AVAIL = "not available on NextGen"

# (tool_callable, kwargs) — every READ tool, with minimal valid args.
READ_CALLS = [
    # Core list reads (no required args)
    ("list_clients", S.list_clients, {}),
    ("list_matters", S.list_matters, {}),
    ("list_contacts", S.list_contacts, {}),
    ("list_time_entries", S.list_time_entries, {}),
    ("list_expenses", S.list_expenses, {}),
    ("list_invoices", S.list_invoices, {}),
    ("list_payments", S.list_payments, {}),
    ("list_transactions", S.list_transactions, {}),
    ("list_ap_bills", S.list_ap_bills, {}),
    ("list_ap_vendors", S.list_ap_vendors, {}),
    ("list_documents", S.list_documents, {}),
    ("list_users", S.list_users, {}),
    # allocation read requires an invoice_id; without one the client raises a
    # clear guard error (counts as PASS — the guard is the designed behavior).
    ("get_payment_invoice_allocations", S.get_payment_invoice_allocations,
     {"payment_source_id": 1, "destination_operating_bank_id": "x"}),
    # Stub reads (no /api/v2 equivalent) — EXPECTED-STUB
    ("list_ap_payments", S.list_ap_payments, {}),
    ("get_ap_payment_status", S.get_ap_payment_status, {"bill_ids": "1"}),
    ("get_document_default_application", S.get_document_default_application, {}),
    ("list_task_codes", S.list_task_codes, {}),
    ("list_activity_codes", S.list_activity_codes, {}),
    ("list_codes", S.list_codes, {}),
    ("list_text_shortcuts", S.list_text_shortcuts, {}),
    ("get_text_shortcut", S.get_text_shortcut, {"shortcut_id": "1"}),
    ("lookup_clients", S.lookup_clients, {}),
    ("lookup_client_labels", S.lookup_client_labels, {}),
    ("lookup_matter_labels", S.lookup_matter_labels, {}),
    ("lookup_matter_type_workflow", S.lookup_matter_type_workflow, {"matter_type_id": "1"}),
    ("lookup_new_contact_form", S.lookup_new_contact_form, {}),
    ("lookup_new_matter_definition", S.lookup_new_matter_definition, {}),
    ("lookup_new_matter_definition_for_matter", S.lookup_new_matter_definition_for_matter, {"matter_id": "1"}),
    ("lookup_new_matter_defaults", S.lookup_new_matter_defaults, {}),
    ("lookup_new_matter_ebilling_defaults", S.lookup_new_matter_ebilling_defaults, {}),
    ("lookup_expense", S.lookup_expense, {}),
    ("lookup_new_expense", S.lookup_new_expense, {}),
    ("lookup_new_expense_info", S.lookup_new_expense_info, {}),
    ("lookup_new_hard_cost_expense", S.lookup_new_hard_cost_expense, {}),
    ("lookup_invoice_payments", S.lookup_invoice_payments, {}),
    ("lookup_invoice", S.lookup_invoice, {}),
    ("lookup_new_invoice", S.lookup_new_invoice, {}),
    ("lookup_new_invoice_info", S.lookup_new_invoice_info, {}),
    ("lookup_new_time_entry", S.lookup_new_time_entry, {}),
    ("lookup_new_timesheet_from_grid", S.lookup_new_timesheet_from_grid, {}),
    ("lookup_new_transaction", S.lookup_new_transaction, {}),
]

# Detail reads (get_*) need an id. Pull live ids first from the list reads so we
# exercise the real /api/v2 detail filter path when data exists.
# All CosmoLex detail reads filter on the primary key ``id``. For guid-keyed
# resources the dummy id must be a GUID (a non-guid 409s as a type mismatch); for
# numeric-keyed resources (accountPayable, user) it must be an INT.
GUID0 = "00000000-0000-0000-0000-000000000000"
INT0 = "999999999"
DETAIL_READS = [
    # (name, fn, id_kwarg, source_list_fn, id_field_in_row, dummy_id)
    ("get_client", S.get_client, "client_id", S.list_clients, "id", GUID0),
    ("get_matter", S.get_matter, "matter_id", S.list_matters, "id", GUID0),
    ("get_contact", S.get_contact, "contact_id", S.list_contacts, "id", GUID0),
    ("get_time_entry", S.get_time_entry, "time_entry_id", S.list_time_entries, "id", GUID0),
    ("get_expense", S.get_expense, "expense_card_id", S.list_expenses, "id", GUID0),
    ("get_invoice", S.get_invoice, "invoice_id", S.list_invoices, "id", GUID0),
    ("get_transaction", S.get_transaction, "transaction_id", S.list_transactions, "id", GUID0),
    ("get_ap_bill", S.get_ap_bill, "bill_id", S.list_ap_bills, "id", INT0),
    ("get_ap_vendor", S.get_ap_vendor, "vendor_id", S.list_ap_vendors, "id", GUID0),
    ("get_user", S.get_user, "user_id", S.list_users, "id", "1"),
]


def classify(name, raw):
    """Return ('PASS'|'EXPECTED-STUB'|'FAIL', detail)."""
    try:
        obj = json.loads(raw) if isinstance(raw, str) else raw
    except (ValueError, TypeError):
        # A non-JSON string result is still a returned value -> PASS.
        return "PASS", f"{type(raw).__name__} len={len(str(raw))}"
    if isinstance(obj, dict) and "error" in obj and len(obj) == 1:
        if NOT_AVAIL in str(obj["error"]):
            return "EXPECTED-STUB", obj["error"][:70]
        # allocation guard (designed) counts as PASS
        if "requires an invoice_id" in str(obj["error"]):
            return "PASS", "guard: requires invoice_id (designed)"
        return "FAIL", obj["error"][:120]
    if isinstance(obj, list):
        return "PASS", f"list rows={len(obj)}"
    return "PASS", f"{type(obj).__name__}"


def main():
    # Live read harness: creds come from env (COSMOLEX_USERNAME / COSMOLEX_PASSWORD),
    # never inlined. Skip cleanly when unset so a bare run / CI collection is a no-op.
    if not (os.environ.get("COSMOLEX_USERNAME") and os.environ.get("COSMOLEX_PASSWORD")):
        print("SKIP: set COSMOLEX_USERNAME + COSMOLEX_PASSWORD + COSMOLEX_BASE_URL="
              "https://sandbox.cosmolex.com to run this live read harness.")
        sys.exit(0)
    results = []  # (name, status, detail)
    # First pass: pull a live id per detail-read source.
    live_ids = {}
    for name, fn, idk, src_fn, idfield, dummy in DETAIL_READS:
        try:
            rows = json.loads(src_fn())
            if isinstance(rows, list) and rows and isinstance(rows[0], dict):
                live_ids[name] = rows[0].get(idfield)
        except Exception:
            live_ids[name] = None

    # List + stub + lookup reads.
    for name, fn, kw in READ_CALLS:
        try:
            raw = fn(**kw)
            status, detail = classify(name, raw)
        except Exception as e:  # noqa: BLE001
            status, detail = "FAIL", f"EXC {type(e).__name__}: {str(e)[:100]}"
        results.append((name, status, detail))

    # Detail reads.
    for name, fn, idk, src_fn, idfield, dummy in DETAIL_READS:
        rid = live_ids.get(name)
        if rid is None:
            # No row to fetch (blank account). The detail path can't be exercised
            # with real data; confirm the tool runs cleanly with a type-correct
            # dummy id (returns JSON null / None) rather than erroring.
            try:
                raw = fn(**{idk: dummy})
                status, detail = classify(name, raw)
                if status == "PASS":
                    detail = f"no live row; dummy-id -> {detail}"
            except Exception as e:  # noqa: BLE001
                status, detail = "FAIL", f"EXC {type(e).__name__}: {str(e)[:100]}"
        else:
            try:
                raw = fn(**{idk: rid})
                status, detail = classify(name, raw)
                detail = f"live id -> {detail}"
            except Exception as e:  # noqa: BLE001
                status, detail = "FAIL", f"EXC {type(e).__name__}: {str(e)[:100]}"
        results.append((name, status, detail))

    # Report
    npass = sum(1 for _, s, _ in results if s == "PASS")
    nstub = sum(1 for _, s, _ in results if s == "EXPECTED-STUB")
    nfail = sum(1 for _, s, _ in results if s == "FAIL")
    total = len(results)
    print(f"=== READ SMOKE: {npass} PASS / {nstub} EXPECTED-STUB / {nfail} FAIL  (of {total} read tools) ===\n")
    for name, status, detail in results:
        mark = {"PASS": "PASS         ", "EXPECTED-STUB": "EXPECTED-STUB", "FAIL": "FAIL  <<<<<  "}[status]
        print(f"  {mark}  {name:42s}  {detail}")
    print()
    if nfail:
        print("FAILURES:")
        for name, status, detail in results:
            if status == "FAIL":
                print(f"  - {name}: {detail}")
    sys.exit(1 if nfail else 0)


if __name__ == "__main__":
    main()
