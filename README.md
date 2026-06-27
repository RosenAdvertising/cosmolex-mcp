# cosmolex-mcp

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

MCP server for [CosmoLex](https://www.cosmolex.com) — legal practice management
for NextGen CosmoLex accounts. Use CosmoLex from Claude Desktop (or any MCP
client) with natural language: matters, clients, contacts, time entries,
expenses, invoices, payments, transactions, accounts payable, and documents.

This server exposes **83 tools** across 16 resource groups, built against the
NextGen `/api/v2` REST API (the live data API on current CosmoLex accounts),
reached with a username/password session login.

## What you can do

- **Matters & Clients** — list, get, create, update, delete matters and clients.
- **Contacts** — full CRUD on matter/client contacts.
- **Time & Expense** — list, get, create, update, delete time entries and expense cards.
- **Invoices & Payments** — list/get/create/update/delete invoices, approve invoices,
  record payments, and inspect invoice payment allocations.
- **Transactions** — list/get/create/update/delete bank/trust transactions.
- **Accounts Payable** — manage AP bills, vendors, and payments.
- **Documents** — list documents, fetch download/upload URLs, delete documents.
- **Timekeepers (users)** — list and get firm users.
- **Lookups & Codes** — form/definition lookups and task/activity/code lookups
  used to build valid create payloads. **Note:** these (and a few write flows —
  invoice approve, payment create, AP payment/delete, document write) are part of
  the legacy LCS surface and are **not yet available on NextGen `/api/v2`**; their
  tools remain in the surface and return an explanatory error until the NextGen
  equivalents are mapped.

Read tools are prefixed `list_*` / `get_*` / `lookup_*`; write tools are
`create_*` / `update_*` / `delete_*` / `approve_*`. Every write tool's description
states its side effect explicitly (it permanently changes live firm data).

## Requirements

- Python 3.10+
- A CosmoLex **login** (the username + password you use in the CosmoLex web app)
- Optionally, a host override (defaults to `https://app.cosmolex.com`; use
  `https://sandbox.cosmolex.com` for a sandbox/trial account)

## Installation

```bash
uv pip install -e .
# or
pip install -e .
```

## Authentication

NextGen CosmoLex accounts authenticate with a **browser-style session login** —
just the CosmoLex username + password you use in the web app. There is no API key
or OAuth app to register for the working data path.

### How it works

The server runs a password-grant session login (`POST /api/ext/auth/token` with a
public, shared login client) and sends the returned token as the `a_t` **cookie**
on every `/api/v2/{resource}` data call. The session token is cached for you (at
`~/.cosmolex-mcp/tokens.json`, mode 0600) and re-acquired automatically on expiry
or a 401. No Bearer header, no per-request token minting.

### Environment variables

| Variable             | Required | Purpose                                                                 |
| -------------------- | -------- | ----------------------------------------------------------------------- |
| `COSMOLEX_USERNAME`  | yes      | Your CosmoLex login username (email).                                   |
| `COSMOLEX_PASSWORD`  | yes      | Your CosmoLex login password.                                           |
| `COSMOLEX_BASE_URL`  | no       | Host root. Defaults to `https://app.cosmolex.com`; use `https://sandbox.cosmolex.com` for a sandbox/trial account. |

See [`.env.example`](.env.example) for a template.

## Setup

```bash
cosmolex-mcp-setup
```

This prompts for your CosmoLex username, password, and an optional host override,
and stores them in your OS keyring (see Credential storage below).

Verify your configuration and credential backend:

```bash
cosmolex-mcp-verify
```

## Credential storage

Secrets are stored in your operating system's native secret store via the
cross-platform [`keyring`](https://github.com/jaraco/keyring) library:

- macOS → Keychain
- Windows → Credential Manager
- Linux → Secret Service (GNOME Keyring / KWallet)

Resolution order (read): **OS keyring → process environment →
`~/.cosmolex-mcp/.env`**. On headless hosts with no Secret Service backend, the
server falls back to a `chmod 0600` `.env` file in `~/.cosmolex-mcp/`. Opt out of
keyring with `COSMOLEX_MCP_USE_KEYRING=0`.

## Claude Desktop configuration

Add to your `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "cosmolex": {
      "command": "cosmolex-mcp",
      "env": {
        "COSMOLEX_USERNAME": "you@example.com",
        "COSMOLEX_PASSWORD": "your-password"
      }
    }
  }
}
```

(If you store credentials via `cosmolex-mcp-setup`, you can omit the `env` block.)

## Running

```bash
cosmolex-mcp
```

The server speaks MCP over stdio.

## License

MIT — see [LICENSE](LICENSE).
