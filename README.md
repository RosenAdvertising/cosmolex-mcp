# cosmolex-mcp

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

MCP server for [CosmoLex](https://www.cosmolex.com) — legal practice management
from Claude Desktop in natural language, over the official **ProfitSolv LCS `/v1`
Integration API** with a **scoped OAuth** integration.

No password login: the server authorizes once in the browser, then refreshes its own
token forever. It never trips CosmoLex's single-session-per-user limit, so it won't
log you out of your CosmoLex browser session while it runs.

The server exposes **86 MCP tools**. The resources the LCS `/v1` API does not expose
are kept as **fail-loud stubs** — they return a clear "not in the LCS /v1 API" error
rather than silently returning nothing, pending a keep/drop decision.

## What you can do

The LCS `/v1` Integration API covers the core practice-management entities:

- **Matters** — list, get, create, update, delete
- **Clients & Contacts** — full CRUD
- **Time entries & Expenses** — full CRUD (log and edit billable time and costs)
- **Invoices** — list, get, create, update, delete
- **Payments** — list and record
- **Transactions** — list (by matter or bank), get, create, update, delete
- **Documents** — list (read-only)
- **Users / timekeepers** — list, get
- **UTBMS codes** — per matter

### Not covered by the `/v1` API

The `/v1` Integration API is narrower than CosmoLex's internal UI (and than the
NextGen `/api/v2` surface a previous build used). These are **not available** and
their tools fail loudly (rather than returning nothing): firm financial summary,
timekeeper time summaries, bank/chart-of-accounts enumeration, the two-step
invoice-generation flow, accounts payable, lookup/defaults endpoints, and tasks,
timers, calendar, tags, trust, rates, firm roles, tax/discount, phone messages,
internal chat, workflow, reports, recurring billing, matter templates, and court
rules.

## Requirements

- Python 3.10+
- Claude Desktop (or any MCP-compatible client)
- A CosmoLex account **and** a registered OAuth integration (API key + OAuth client
  ID/secret) for the ProfitSolv LCS Integration API

## Installation

```bash
pip install cosmolex-mcp
```

Or from source:

```bash
uv pip install -e .
# or
pip install -e .
```

## Setup

```bash
cosmolex-mcp-setup
```

The wizard:

1. Stores your integration's **API key**, **OAuth client ID**, and **client secret**
   in your OS keyring (see Credential storage below).
2. Prints an authorization URL. Open it in your browser (logged in to CosmoLex) and
   click **Allow**.
3. Your browser redirects to the app's registered redirect URI
   (`https://localhost:8770/callback`) with a `?code=...` parameter. The browser may
   show a connection error — that's fine; just copy the `code` value from the address
   bar and paste it back into the wizard.
4. The wizard exchanges the code for an access token + refresh token, cached at
   `~/.cosmolex-mcp/tokens.json` (chmod 600).

After that, the client refreshes its own access token with the long-lived refresh
token — no browser, no password — so you won't be prompted again unless the refresh
token is revoked.

Verify:

```bash
cosmolex-mcp-verify
```

## Claude Desktop Configuration

```json
{
  "mcpServers": {
    "cosmolex": {
      "command": "cosmolex-mcp"
    }
  }
}
```

## Credential storage

By default credentials are stored in your operating system's native secret store via
the cross-platform [`keyring`](https://github.com/jaraco/keyring) library:

| OS      | Backend                                  |
| ------- | ---------------------------------------- |
| macOS   | Keychain                                 |
| Windows | Credential Manager                       |
| Linux   | Secret Service (GNOME Keyring / KWallet) |

Secrets are saved under the service name `cosmolex-mcp`. Nothing is written to disk in
clear text.

**File fallback.** On a host with no keyring backend (e.g. a headless Linux box
without Secret Service), or if you set `COSMOLEX_MCP_USE_KEYRING=0`, credentials fall
back to a `~/.cosmolex-mcp/.env` file with `0600` permissions.

**Read order.** Credentials resolve in the order OS keyring → process environment →
`.env` file.

## Authentication notes

The server uses the **ProfitSolv LCS `/v1` Integration API** with a scoped OAuth
integration:

- **Consent once** (`/OAuth/authorize` → `Allow`) to obtain an authorization code.
- **Exchange** the code at `{base}/api/ext/auth/token` (`grant_type=authorization_code`)
  for an `access_token` (~30 min) + a long-lived `refresh_token`.
- **Data calls** go to the LCS `/v1` host with two headers: `X-Api-Key: <app key>` and
  `X-User-Token: <access token>`.
- **Refresh** (`grant_type=refresh_token`) renews the access token without a password
  login, so the user's CosmoLex browser session is never bumped.

Hosts are overridable via `COSMOLEX_BASE_URL` (OAuth host — sandbox
`sandbox.cosmolex.com`, production `law.cosmolex.com`) and `COSMOLEX_API_BASE_URL`
(the LCS `/v1` data host — the ProfitSolv Azure app; the production data host is
provisioned per-firm).

## Example usage in Claude

> "List my matters"
>
> "Create a client named Acme Holdings"
>
> "Log a time entry on matter <id>"
>
> "Show open invoices and recent payments"
>
> "List the firm's users"

## License

MIT — see [LICENSE](LICENSE).
