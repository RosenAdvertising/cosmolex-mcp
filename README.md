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
rather than silently returning nothing.

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
- Python MCP SDK >=2.3,<3 (separate from the MCP protocol revision)
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

Before setup, register **`http://127.0.0.1:8770/callback`** as an OAuth redirect
with CosmoLex / ProfitSolv. The old HTTPS localhost registration must be changed
to this HTTP loopback redirect.

The wizard:

1. Stores your integration's **API key**, **OAuth client ID**, and **client secret**
   in your OS keyring (see Credential storage below).
2. Binds the local callback, then prints an authorization URL. Open it in your
   browser (logged in to CosmoLex) and click **Allow**. If the port is occupied,
   setup stops before printing the URL.
3. Your browser redirects to `http://127.0.0.1:8770/callback`. The listener checks
   the callback path and session's random `state` before accepting the code.
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

## HTTP mode

Stdio, above, stays the default. Set `COSMOLEX_MCP_TRANSPORT=streamable-http` to serve the same server over stateless Streamable HTTP (MCP 2026-07-28). The endpoint is `POST /mcp`. Vendor credentials come from the same environment variables as stdio, never from the request.

| Variable | Default | Purpose |
| --- | --- | --- |
| `COSMOLEX_MCP_TRANSPORT` | `stdio` | `stdio` or `streamable-http` |
| `COSMOLEX_MCP_HOST` | `127.0.0.1` | Bind address. Loopback keeps the SDK's own Host and Origin checks. |
| `PORT` | `8080` | Bind port. A non-integer stops the process. |
| `COSMOLEX_MCP_ALLOWED_HOSTS` | unset | Comma-separated Host allowlist. Required when the bind address is not loopback. |
| `COSMOLEX_MCP_ALLOWED_ORIGINS` | unset | Optional comma-separated Origin allowlist, used with the Host allowlist off loopback. |
| `COSMOLEX_API_KEY` |  | Vendor API key |
| `COSMOLEX_CLIENT_ID` |  | OAuth client id |
| `COSMOLEX_CLIENT_SECRET` |  | OAuth client secret |
| `COSMOLEX_BASE_URL` | `https://sandbox.cosmolex.com` | OAuth host |
| `COSMOLEX_API_BASE_URL` | sandbox LCS host | `/v1` data host |
| `COSMOLEX_REDIRECT_URI` | `http://127.0.0.1:8770/callback` | Setup redirect only |

```bash
COSMOLEX_MCP_TRANSPORT=streamable-http PORT=8080 cosmolex-mcp
```

Clients then POST to `http://127.0.0.1:8080/mcp`.

## Credential storage

By default credentials are stored in your operating system's native secret store via
the cross-platform [`keyring`](https://github.com/jaraco/keyring) library:

| OS      | Backend                                  |
| ------- | ---------------------------------------- |
| macOS   | Keychain                                 |
| Windows | Credential Manager                       |
| Linux   | Secret Service (GNOME Keyring / KWallet) |

Secrets are saved under the service name `cosmolex-mcp` when a keyring backend is
available. The file fallback below stores credentials on disk with restricted
permissions.

**File fallback.** On a host with no keyring backend (e.g. a headless Linux box
without Secret Service), or if you set `COSMOLEX_MCP_USE_KEYRING=0`, credentials fall
back to a `~/.cosmolex-mcp/.env` file with `0600` permissions.

On Windows, the file is stored in the user's profile and protected by Windows'
default per-user access rules. On POSIX, files are created with `0600` permissions
and writes fail closed if private permissions cannot be established.

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

## Setup security

Register the exact `COSMOLEX_REDIRECT_URI` with the vendor (default:
`http://127.0.0.1:8770/callback`). Overrides must use HTTP and exactly `127.0.0.1`,
with an explicit port and callback path. `localhost`, IPv6 and external callbacks
are rejected. Setup binds that address before displaying authorization and receives
the callback automatically; manual redirect pastes, bare codes, `--code` arguments
and `COSMOLEX_OAUTH_CODE` are not supported.
Fallback credentials and tokens are atomically written with `0600` permissions
established before any secret bytes are written; permission failures stop the write.

OAuth endpoints accept only `https://sandbox.cosmolex.com` and
`https://law.cosmolex.com`. Data endpoints accept only the exact two ProfitSolv LCS
hosts in `cosmolex_mcp/endpoint_validation.py`. Endpoints reject userinfo, paths,
query strings, fragments and non-default ports. No Azure suffix wildcard is used.
The [CosmoLex host documentation](https://support.cosmolex.com/knowledge-base/access-cosmolex-app/)
identifies the production product host; the
[public LCS sandbox Swagger document](https://lcs-developer-api-profi-sandbox-gncndgfccdgxdtff.centralus-01.azurewebsites.net/swagger/v1/swagger.json)
identifies the LCS gateway. Additional provisioned hosts require verification and
an explicit allowlist update.
