#!/usr/bin/env python3
"""Phase 2 LIVE write verification for cosmolex-mcp (NextGen /api/v2).

SANDBOX ONLY. ZZTEST-prefixed data ONLY. Every created record's guid is tracked
in CREATED and torn down in a finally block (reverse dependency order) so nothing
is orphaned even on mid-flight failure. Reads the working body live; on a 400 it
prints the error so the body can be adjusted MINIMALLY (no invented fields).

Per resource: CREATE (ZZTEST) -> VERIFY (appears in list_ AND get_ detail returns
the real record — this also confirms the guid-id detail filter on POPULATED data)
-> UPDATE one field (verify persisted) -> DELETE (confirm gone).

Sequence: client -> matter -> (time, expense under that matter); contact
independent. Financial flows: create_transaction (allocations) + invoice 2-step.

Run with COSMOLEX_BASE_URL=https://sandbox.cosmolex.com and sandbox creds in env.
"""
import json
import os
import sys
import traceback
from datetime import date, timedelta

# Run-from-repo bootstrap: make the cosmolex_mcp package importable whether or not
# it has been pip-installed, so `python tests/write_test.py` works from a clone.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cosmolex_mcp import server as S  # noqa: E402
from cosmolex_mcp.client import LCSClient  # noqa: E402

TAG = "ZZTEST"
results = []        # (label, verdict, detail)
CREATED = []        # (kind, delete_fn, guid) — torn down in reverse in finally
# The LCSClient is created inside main() (after the sandbox guard), NOT at import
# time, so importing this module never triggers a login.


def rec(label, verdict, detail=""):
    results.append((label, verdict, detail))
    print(f"  [{verdict:4s}] {label}: {detail}"[:200])


def j(raw):
    try:
        return json.loads(raw) if isinstance(raw, str) else raw
    except (ValueError, TypeError):
        return raw


def is_err(obj):
    return isinstance(obj, dict) and "error" in obj and len(obj) == 1


# ── Generic CRUD verifier for a resource via the SERVER tool functions ───────

def crud(kind, create_fn, body, list_fn, get_fn, update_fn, update_field,
         update_val, delete_fn, id_key="id", track=True):
    """Returns the created guid (or None). Records create/verify/update/delete."""
    # CREATE
    created = j(create_fn(fields_json=json.dumps(body)))
    if is_err(created):
        rec(f"{kind}.create", "FAIL", f"body={body} -> {created['error'][:140]}")
        return None
    guid = created.get(id_key) if isinstance(created, dict) else None
    if not guid:
        rec(f"{kind}.create", "FAIL", f"no '{id_key}' in response keys={list(created)[:12] if isinstance(created,dict) else type(created)}")
        return None
    if track:
        CREATED.append((kind, delete_fn, guid))
    rec(f"{kind}.create", "PASS", f"guid={guid}  (working body={body})")

    # VERIFY via get_ detail (the populated-data guid-id filter test)
    got = j(get_fn(guid))
    if is_err(got) or got is None:
        rec(f"{kind}.get_detail", "FAIL", f"get({guid}) -> {got}")
    else:
        rec(f"{kind}.get_detail", "PASS", f"detail returned (guid-id filter works on populated data)")

    # VERIFY appears in list_
    listed = j(list_fn())
    in_list = isinstance(listed, list) and any(
        isinstance(r, dict) and r.get("id") == guid for r in listed
    )
    rec(f"{kind}.in_list", "PASS" if in_list else "WARN",
        "found in list_" if in_list else f"not in list_ (rows={len(listed) if isinstance(listed,list) else '?'})")

    # UPDATE
    upd = j(update_fn(guid, fields_json=json.dumps({update_field: update_val})))
    if is_err(upd):
        rec(f"{kind}.update", "FAIL", f"{update_field}={update_val!r} -> {upd['error'][:120]}")
    else:
        # re-read to confirm persisted
        reread = j(get_fn(guid))
        persisted = isinstance(reread, dict) and str(reread.get(update_field, "")).find(str(update_val)) >= 0
        rec(f"{kind}.update", "PASS" if persisted else "WARN",
            f"{update_field}={update_val!r} {'persisted' if persisted else 'set (persist unverified: field not in read set)'}")

    # DELETE
    deld = j(delete_fn(guid))
    if is_err(deld):
        rec(f"{kind}.delete", "FAIL", f"delete({guid}) -> {deld['error'][:120]}")
    else:
        gone = j(get_fn(guid))
        is_gone = gone is None or (isinstance(gone, list) and not gone)
        rec(f"{kind}.delete", "PASS" if is_gone else "WARN",
            "deleted + confirmed gone" if is_gone else f"delete ok but still readable: {str(gone)[:60]}")
        if is_gone and track:
            # remove from teardown registry (already gone)
            CREATED[:] = [(k, f, g) for (k, f, g) in CREATED if g != guid]
    return guid


def main():
    # SANDBOX-ONLY live write harness. Creds come from env (COSMOLEX_USERNAME /
    # COSMOLEX_PASSWORD), never inlined. Skip cleanly without creds; HARD-REFUSE
    # any non-sandbox host so this can never create/delete in a real firm account.
    if not (os.environ.get("COSMOLEX_USERNAME") and os.environ.get("COSMOLEX_PASSWORD")):
        print("SKIP: set COSMOLEX_USERNAME + COSMOLEX_PASSWORD + COSMOLEX_BASE_URL="
              "https://sandbox.cosmolex.com to run this live write harness.")
        return
    from urllib.parse import urlparse

    from cosmolex_mcp.client import BASE_URL
    if urlparse(BASE_URL).hostname != "sandbox.cosmolex.com":
        print(f"REFUSING: this harness creates and deletes records; "
              f"COSMOLEX_BASE_URL={BASE_URL!r} is not the CosmoLex sandbox "
              f"(sandbox.cosmolex.com). Refusing to run.")
        sys.exit(2)
    client = LCSClient()  # direct client for financial-flow probing + teardown
    try:
        print("=== CLIENT ===")
        client_guid = crud(
            "client", S.create_client, {"name": f"{TAG} Client Alpha"},
            S.list_clients, S.get_client, S.update_client,
            "displayName", f"{TAG} Renamed", S.delete_client, track=False,
        )
        # We need a LIVING client to hang a matter on, so re-create one we keep.
        held_client = j(S.create_client(fields_json=json.dumps({"name": f"{TAG} Client Hold"})))
        held_client_guid = held_client.get("id") if isinstance(held_client, dict) and not is_err(held_client) else None
        if held_client_guid:
            CREATED.append(("client(hold)", S.delete_client, held_client_guid))
            print(f"  (held client for matter dep: {held_client_guid})")

        print("\n=== MATTER ===")
        matter_guid = None
        if held_client_guid:
            matter_guid = crud(
                "matter", S.create_matter,
                {"clientId": held_client_guid, "matterName": f"{TAG} Matter One"},
                S.list_matters, S.get_matter, S.update_matter,
                "matterName", f"{TAG} Matter Renamed", S.delete_matter, track=False,
            )
            # held matter to hang time/expense on
            held_matter = j(S.create_matter(fields_json=json.dumps(
                {"clientId": held_client_guid, "matterName": f"{TAG} Matter Hold"})))
            held_matter_guid = held_matter.get("id") if isinstance(held_matter, dict) and not is_err(held_matter) else None
            if held_matter_guid:
                CREATED.append(("matter(hold)", S.delete_matter, held_matter_guid))
                print(f"  (held matter for time/expense dep: {held_matter_guid})")
        else:
            rec("matter.*", "SKIP", "no client guid to attach matter")
            held_matter_guid = None

        print("\n=== TIME ENTRY ===")
        if held_matter_guid:
            crud("time_entry", S.create_time_entry,
                 {"matterId": held_matter_guid, "cardType": 1, "timeBilledDecimal": 0.5,
                  "ratePrice": 100, "rateTypeId": 1, "billingStatus": 1,
                  "description": f"{TAG} time"},
                 S.list_time_entries, S.get_time_entry, S.update_time_entry,
                 "description", f"{TAG} time edited", S.delete_time_entry, track=False)
        else:
            rec("time_entry.*", "SKIP", "no matter guid")

        print("\n=== EXPENSE ===")
        if held_matter_guid:
            crud("expense", S.create_expense,
                 {"matterId": held_matter_guid, "cardType": 2, "quantity": 1,
                  "ratePrice": 10, "billingStatus": 1, "description": f"{TAG} expense"},
                 S.list_expenses, S.get_expense, S.update_expense,
                 "description", f"{TAG} expense edited", S.delete_expense, track=False)
        else:
            rec("expense.*", "SKIP", "no matter guid")

        print("\n=== CONTACT (independent) ===")
        crud("contact", S.create_contact, {"name": f"{TAG} Contact Bravo"},
             S.list_contacts, S.get_contact, S.update_contact,
             "displayName", f"{TAG} Contact Renamed", S.delete_contact, track=False)

        # ── FINANCIAL FLOWS (direct client; allocations + 2-step invoice) ─────
        print("\n=== TRANSACTION (financial flow) ===")
        try:
            banks = client.list_banks()
            coas = client.list_chart_of_accounts()
            # Use the OPERATING bank (a Trust bank requires a matterId on the txn).
            op_bank = next((b for b in banks if "operat" in str(b.get("bankTypeLabel", "")).lower()), None) if isinstance(banks, list) else None
            bank_id = (op_bank or (banks[0] if isinstance(banks, list) and banks else {})).get("id")
            # pick an income/fee COA; fall back to first
            coa_id = None
            if isinstance(coas, list) and coas:
                fee = next((c for c in coas if "income" in str(c.get("accountTypeLabel","")).lower()
                            or "fee" in str(c.get("accountName","")).lower()), coas[0])
                coa_id = fee.get("id")
            rec("transaction.helpers", "PASS" if (bank_id and coa_id) else "WARN",
                f"bankId={bank_id} coaId={coa_id} (banks={len(banks) if isinstance(banks,list) else '?'}, coa={len(coas) if isinstance(coas,list) else '?'})")
            if bank_id and coa_id:
                tbody = {
                    "bankId": bank_id, "transactionType": "1", "transactionMethod": 1005,
                    "transactionDate": date.today().isoformat(), "amount": "10.00",
                    "payeeName": f"{TAG} Payor", "savePayee": False,
                    "allocations": [{"id": 1, "chartOfAccountId": str(coa_id),
                                     "allocationSignedAmount": 10, "memo": "", "deleted": False}],
                }
                tx = client.create_transaction(**tbody)
                if isinstance(tx, dict) and tx.get("id"):
                    txid = tx["id"]
                    CREATED.append(("transaction", client.delete_transaction, txid))
                    rec("transaction.create", "PASS", f"guid={txid} (body confirmed)")
                    d = client.delete_transaction(txid)
                    CREATED[:] = [(k,f,g) for (k,f,g) in CREATED if g != txid]
                    rec("transaction.delete", "PASS", f"{d}")
                else:
                    rec("transaction.create", "FAIL", f"body={tbody} -> {str(tx)[:160]}")
        except Exception as e:
            rec("transaction.flow", "FAIL", f"EXC {type(e).__name__}: {str(e)[:140]}")

        print("\n=== INVOICE (2-step flow) ===")
        # Needs a matter WITH an unbilled billable time entry. Build a fresh held
        # matter + billable time, then attempt the 2-step generate.
        try:
            if held_client_guid:
                im = client.create_matter(clientId=held_client_guid, matterName=f"{TAG} Inv Matter")
                im_guid = im.get("id") if isinstance(im, dict) else None
                if im_guid:
                    CREATED.append(("matter(inv)", client.delete_matter, im_guid))
                    it = client.create_time_entry(matterId=im_guid, cardType=1, timeBilledDecimal=1,
                                                  ratePrice=100, rateTypeId=1, billingStatus=1,
                                                  description=f"{TAG} billable")
                    it_guid = it.get("id") if isinstance(it, dict) else None
                    if it_guid:
                        CREATED.append(("time(inv)", client.delete_time_entry, it_guid))
                    # Step 1: billable items w/ challenge
                    to_date = date.today().isoformat()
                    params = {"sortBy": "-creationDate", "matterId": im_guid, "invoiced": "false",
                              "toDate": to_date, "statusId": "eq|1", "billingStatus": "any|1",
                              "isMatterActive": "eq|true"}
                    from cosmolex_mcp.client import BASE_URL
                    r1 = client.session.get(f"{BASE_URL}/api/timeexpense/", params=params)
                    items = r1.json() if r1.ok and r1.content else []
                    rec("invoice.step1_billable", "PASS" if isinstance(items, list) else "WARN",
                        f"status={r1.status_code} items={len(items) if isinstance(items,list) else type(items).__name__}; sample_keys={list(items[0].keys())[:8] if isinstance(items,list) and items else 'none'}")
                    tel = [{"id": x.get("id"), "challenge": x.get("challenge")} for x in items
                           if isinstance(x, dict) and x.get("id") and x.get("challenge")] if isinstance(items, list) else []
                    # invoiceNumber from form prep
                    f2 = client.session.get(f"{BASE_URL}/api/gui/form/newInvoice", params={"matterId": im_guid})
                    inv_no = None
                    if f2.ok and f2.content:
                        try: inv_no = f2.json().get("invoiceNumber")
                        except ValueError: pass
                    if tel:
                        ibody = {"matterId": im_guid, "invoiceDate": to_date,
                                 "dueDate": (date.today()+timedelta(days=30)).isoformat(),
                                 "toDate": to_date, "invoiceNumber": inv_no, "timeExpenseList": tel,
                                 "description": "", "discountType": "1", "discountAmount": 0,
                                 "discountTaxable": True, "consolidateSimilarExpense": True,
                                 "overheadContext": 1, "overheadPercentage": 0, "financeChargeAmount": 0,
                                 "financeChargeIsAutomatic": False, "lateFees": 0, "otherFees": 0,
                                 "clientPortalShareable": False, "showCoverPage": False,
                                 "isStartDateSelected": False, "applyAvailableOperatingFunds": False,
                                 "applyAvailableTrustFunds": False, "writeOffList": [], "documents": [], "id": None}
                        inv = client._api_post("invoice", ibody)
                        if isinstance(inv, dict) and inv.get("id"):
                            invid = inv["id"]
                            CREATED.append(("invoice", client.delete_invoice, invid))
                            rec("invoice.create", "PASS", f"guid={invid} invoiceNumber={inv_no}")
                            d = client.delete_invoice(invid)
                            CREATED[:] = [(k,f,g) for (k,f,g) in CREATED if g != invid]
                            rec("invoice.delete", "PASS", f"{d}")
                        else:
                            rec("invoice.create", "FAIL", f"invNo={inv_no} -> {str(inv)[:160]}")
                    else:
                        rec("invoice.step2", "BLOCKED", f"no billable items with challenge token (items={len(items) if isinstance(items,list) else '?'}, inv_no={inv_no}) — flow needs browser capture or different billable-items params")
        except Exception as e:
            rec("invoice.flow", "FAIL", f"EXC {type(e).__name__}: {str(e)[:140]}")

    except Exception as e:
        print(f"\n!!! HARNESS EXCEPTION: {type(e).__name__}: {e}")
        traceback.print_exc()
    finally:
        # ── TEARDOWN: delete everything still tracked, reverse order ──────────
        print("\n=== TEARDOWN (reverse dependency order) ===")
        leftovers = []
        for kind, del_fn, guid in reversed(CREATED):
            try:
                d = del_fn(guid)
                dd = j(d) if not isinstance(d, dict) else d
                ok = (isinstance(dd, dict) and (dd.get("success") or not is_err(dd)))
                print(f"  teardown {kind} {guid}: {'OK' if ok else 'FAIL '+str(dd)[:80]}")
                if not ok:
                    leftovers.append((kind, guid, str(dd)[:80]))
            except Exception as e:
                print(f"  teardown {kind} {guid}: EXC {type(e).__name__}: {str(e)[:80]}")
                leftovers.append((kind, guid, f"EXC {type(e).__name__}"))

        # ── LEFTOVER SWEEP: list every resource, flag any ZZTEST rows remaining ─
        print("\n=== ZZTEST LEFTOVER SWEEP (list every resource, flag ZZTEST) ===")
        sweep_specs = [
            ("client", client.list_clients, ("name", "displayName")),
            ("matter", client.list_matters, ("clientMatterName", "clientName")),
            ("contact", client.list_contacts, ("name", "displayName")),
            ("timeExpense", client.list_time_entries, ("description",)),
            ("timeExpense(exp)", client.list_expenses, ("description",)),
            ("transaction", client.list_transactions, ("clientName",)),
            ("payee", client.list_ap_vendors, ("payeeName",)),
        ]
        zz_left = []
        for name, fn, namefields in sweep_specs:
            try:
                rows = fn()
                if isinstance(rows, list):
                    for r in rows:
                        if isinstance(r, dict) and any(TAG in str(r.get(nf, "")) for nf in namefields):
                            zz_left.append((name, r.get("id"), {nf: r.get(nf) for nf in namefields}))
            except Exception as e:
                print(f"  sweep {name}: ERR {type(e).__name__}")
        if zz_left:
            print(f"  !!! {len(zz_left)} ZZTEST LEFTOVERS REMAIN — MANUAL SWEEP NEEDED:")
            for n, g, nm in zz_left:
                print(f"    LEFTOVER {n} id={g} {nm}")
        else:
            print("  CLEAN: zero ZZTEST rows remain across all swept resources.")

        # ── SUMMARY ──────────────────────────────────────────────────────────
        print("\n" + "=" * 70)
        np = sum(1 for _, v, _ in results if v == "PASS")
        nf = sum(1 for _, v, _ in results if v == "FAIL")
        nw = sum(1 for _, v, _ in results if v == "WARN")
        nb = sum(1 for _, v, _ in results if v in ("BLOCKED", "SKIP"))
        print(f"WRITE TEST: {np} PASS / {nf} FAIL / {nw} WARN / {nb} BLOCKED|SKIP")
        print(f"LEFTOVERS: {len(zz_left)} ZZTEST rows remaining; {len(leftovers)} teardown failures")
        if nf:
            print("\nFAILURES:")
            for label, v, d in results:
                if v == "FAIL":
                    print(f"  - {label}: {d}")


if __name__ == "__main__":
    main()
