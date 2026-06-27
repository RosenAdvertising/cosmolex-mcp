# cosmolex-mcp — tests

Two layers:

- **`config.py`** — `mcp_test_kit` toolkit config (structure / resilience tiers). Its
  live "smoke" tier is skipped because it needs real CosmoLex credentials.
- **`read_smoke.py` / `write_test.py`** — live integration harnesses that exercise the
  real NextGen `/api/v2` surface against a CosmoLex **sandbox** account.

## Live harnesses

Both read credentials from the environment only — nothing is inlined. Set them to a
CosmoLex **sandbox** login and point at the sandbox host:

```bash
export COSMOLEX_USERNAME="your-sandbox-username"
export COSMOLEX_PASSWORD="your-sandbox-password"
export COSMOLEX_BASE_URL="https://sandbox.cosmolex.com"

python tests/read_smoke.py     # reads only — every list_/get_/lookup_ tool once
python tests/write_test.py     # full CRUD round-trips on ZZTEST data, auto-torn-down
```

- `read_smoke.py` classifies each read as PASS / EXPECTED-STUB (the tools with no
  NextGen `/api/v2` equivalent — Lookups, Codes, Text Shortcuts, a few write-only flows)
  / FAIL; the exit code is non-zero on any FAIL.
- `write_test.py` creates only `ZZTEST`-prefixed records, verifies create/get/list/
  update/delete per resource (plus the transaction and 2-step invoice flows), then tears
  everything down in reverse dependency order and sweeps for leftovers. It **hard-refuses
  to run against any non-sandbox host** and skips cleanly when credentials are unset.

Both harnesses are import-safe (no login at import) and require credentials at run time,
so a bare `pytest` / CI collection is a no-op rather than a live call.

Last live verification — 2026-06-27: read 23 PASS / 28 expected-stub / 0 FAIL;
write 30 PASS / 0 FAIL / 1 WARN (cosmetic), 0 leftovers.
