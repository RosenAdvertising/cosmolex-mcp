# CosmoLex MCP server

[![CI](https://github.com/RosenAdvertising/cosmolex-mcp/actions/workflows/ci.yml/badge.svg)](https://github.com/RosenAdvertising/cosmolex-mcp/actions/workflows/ci.yml)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![MCP 2026-07-28](https://img.shields.io/badge/MCP-2026--07--28-7C3AED.svg)](https://modelcontextprotocol.io)
[![PyPI version](https://img.shields.io/pypi/v/cosmolex-mcp.svg)](https://pypi.org/project/cosmolex-mcp/)

Connect Claude and other MCP clients to CosmoLex to manage matters, clients, time entries, invoices and payments.

CosmoLex MCP server is a [Model Context Protocol](https://modelcontextprotocol.io) server for [CosmoLex](https://www.cosmolex.com), the legal practice management platform. It registers 86 tools that read and write CosmoLex data through the ProfitSolv LCS `/v1` Integration API; 43 of them cover capabilities that API does not expose and return an error saying so (see [Tools](#tools)). It runs over stdio by default, for desktop clients such as Claude Desktop, and offers an opt-in stateless Streamable HTTP mode that implements MCP specification 2026-07-28. CosmoLex credentials stay on the machine that runs the server: they come from the setup command and your operating system's keyring, never from the client. The server signs in with scoped OAuth rather than a password, so it never trips CosmoLex's single-session-per-user limit and does not log you out of your CosmoLex browser session while it runs.

## Features

- **Matters**: list, get, create, update and delete matters.
- **Clients and contacts**: create, read, update and delete clients and contacts.
- **Time entries and expenses**: log, edit and delete billable time and costs.
- **Invoices**: list, get, create, update and delete invoices.
- **Payments**: list payments and record new ones.
- **Transactions**: list by matter or bank, get, create, update and delete.
- **Documents**: list documents (read-only).
- **Users**: list and get firm users.
- **UTBMS codes**: get the codes for a matter.

## Tools

The server registers 86 tools. 43 of them work against the LCS `/v1` Integration API. The other 43 cover capabilities that API does not expose; they stay registered and return an error that names the capability and says it "is not available in the ProfitSolv LCS /v1 Integration API." instead of an empty result (see [Limits of the LCS /v1 API](#limits-of-the-lcs-v1-api)).

<details>
<summary>All 86 tools</summary>

Working tools (43):

- `create_client`
- `create_contact`
- `create_expense`
- `create_invoice`
- `create_matter`
- `create_payment`
- `create_time_entry`
- `create_transaction`
- `delete_client`
- `delete_contact`
- `delete_expense`
- `delete_invoice`
- `delete_matter`
- `delete_time_entry`
- `delete_transaction`
- `get_client`
- `get_codes`
- `get_contact`
- `get_expense`
- `get_invoice`
- `get_matter`
- `get_text_shortcut`
- `get_time_entry`
- `get_transaction`
- `get_user`
- `list_clients`
- `list_contacts`
- `list_documents`
- `list_expenses`
- `list_invoices`
- `list_matters`
- `list_payments`
- `list_text_shortcuts`
- `list_time_entries`
- `list_transactions`
- `list_users`
- `update_client`
- `update_contact`
- `update_expense`
- `update_invoice`
- `update_matter`
- `update_time_entry`
- `update_transaction`

Registered but not available in the `/v1` API (43):

- `approve_invoice`
- `create_ap_bill`
- `create_ap_payment`
- `create_ap_vendor`
- `delete_ap_bill`
- `delete_document`
- `generate_invoice`
- `get_activity_codes`
- `get_ap_bill`
- `get_ap_payment_status`
- `get_ap_vendor`
- `get_client_labels`
- `get_client_suggestions`
- `get_document_default_app`
- `get_document_download_url`
- `get_document_upload_url`
- `get_ebilling_defaults`
- `get_expense_lookups`
- `get_firm_summary`
- `get_hard_cost_expense_lookups`
- `get_invoice_allocations`
- `get_invoice_lookups`
- `get_invoice_payment_lookups`
- `get_matter_labels`
- `get_matter_type_workflow`
- `get_new_contact_defaults`
- `get_new_expense_lookups`
- `get_new_invoice_lookups`
- `get_new_matter_defaults`
- `get_new_matter_definition`
- `get_task_codes`
- `get_time_entry_lookups`
- `get_time_grid_lookups`
- `get_transaction_lookups`
- `list_ap_bills`
- `list_ap_payments`
- `list_ap_vendors`
- `list_banks`
- `list_billable_items`
- `list_chart_of_accounts`
- `list_timekeepers`
- `update_ap_bill`
- `update_ap_vendor`

</details>

### Prompts and resources

The server also registers three prompts and three resources.

| Prompt | What it does |
| --- | --- |
| `accounts_receivable_review` | Reviews outstanding invoices and recent payments for the firm's receivables. |
| `matter_billing_review` | Reviews unbilled time and outstanding invoices for one matter. Takes `matter_id`. |
| `new_matter_intake` | Walks through creating a new matter for an existing client. Takes `client_id`. |

| Resource | What it provides |
| --- | --- |
| `cosmolex://clients` | The firm's clients (first page): names, balances and contact details. |
| `cosmolex://users` | All firm users and timekeepers with email, roles, default rate and status. |
| `cosmolex://security-notes` | Security notes for the server. |

## Requirements

- Python 3.10 or later.
- A CosmoLex account and a registered OAuth integration for the ProfitSolv LCS Integration API: an API key, an OAuth client ID and a client secret.
- An MCP client such as Claude Desktop.

## Installation

Install [uv](https://docs.astral.sh/uv/), then clone the repository and install its locked dependencies:

```bash
git clone https://github.com/RosenAdvertising/cosmolex-mcp.git
cd cosmolex-mcp
uv sync --locked
```

Releases are also published to PyPI: `pip install cosmolex-mcp` installs version 0.3.0, which predates the HTTP mode described below. Install from source to use HTTP mode.

## Configuration

Before setup, register `http://127.0.0.1:8770/callback` as an OAuth redirect with CosmoLex / ProfitSolv, then run the setup command:

```bash
uv run cosmolex-mcp-setup
```

The wizard:

1. Stores your integration's API key, OAuth client ID and client secret in your operating system's keyring (see [Credential storage](#credential-storage)).
2. Binds the local callback, then prints an authorization URL. Open it in your browser (logged in to CosmoLex) and click Allow. If the port is occupied, setup stops before printing the URL.
3. Receives the redirect at `http://127.0.0.1:8770/callback`, checking the callback path and the session's random `state` before accepting the code.
4. Exchanges the code for an access token and a refresh token, cached at `~/.cosmolex-mcp/tokens.json` with `0600` permissions.

After that, the server refreshes its own access token with the long-lived refresh token, with no browser and no password, so you are not prompted again unless the refresh token is revoked.

Check the connection:

```bash
uv run cosmolex-mcp-verify
```

Server messages that say to run `cosmolex-mcp-setup` mean `uv run cosmolex-mcp-setup` from your clone.

The server reads these variables, which you can also set in its environment:

| Variable | Required | Default | Purpose |
| --- | --- | --- | --- |
| `COSMOLEX_API_KEY` | Yes (saved by setup) | Credential store | Integration API key, sent as the `X-Api-Key` header. |
| `COSMOLEX_CLIENT_ID` | Yes (saved by setup) | Credential store | OAuth client ID. |
| `COSMOLEX_CLIENT_SECRET` | Yes (saved by setup) | Credential store | OAuth client secret. |
| `COSMOLEX_BASE_URL` | No | `https://sandbox.cosmolex.com` | OAuth host. Use `https://law.cosmolex.com` for a production firm. |
| `COSMOLEX_API_BASE_URL` | No | The ProfitSolv LCS sandbox host | The LCS `/v1` data host. See [Setup security](#setup-security) for the hosts the server accepts. |
| `COSMOLEX_REDIRECT_URI` | No | `http://127.0.0.1:8770/callback` | OAuth redirect URI used by setup; must match the redirect registered with the vendor. |
| `COSMOLEX_MCP_USE_KEYRING` | No | `1` | Set to `0` to skip the operating system keyring and use the environment and the `.env` file fallback. |

## Usage with Claude Desktop

Add the server to Claude Desktop's configuration file (`~/Library/Application Support/Claude/claude_desktop_config.json` on macOS, `%APPDATA%\Claude\claude_desktop_config.json` on Windows):

```json
{
  "mcpServers": {
    "cosmolex": {
      "command": "uv",
      "args": ["run", "--locked", "--directory", "/absolute/path/to/cosmolex-mcp", "cosmolex-mcp"]
    }
  }
}
```

Replace `/absolute/path/to/cosmolex-mcp` with the path of your clone, then restart Claude Desktop. Any other stdio MCP client uses the same command and arguments.

## HTTP mode

Stdio is the default. Set `COSMOLEX_MCP_TRANSPORT=streamable-http` to serve the stateless Streamable HTTP transport from MCP specification 2026-07-28 at `/mcp`. Each request stands alone: no initialization handshake and no `Mcp-Session-Id`. Clients on earlier protocol versions are served on the same endpoint.

> **Security: this endpoint has no authentication and no TLS.** Anyone who can reach the port can run every tool, including write and delete tools, with this server's vendor credentials. Keep the default loopback bind (`127.0.0.1`), or put the server behind an authenticating TLS proxy on a private network. `COSMOLEX_MCP_ALLOWED_HOSTS` and `COSMOLEX_MCP_ALLOWED_ORIGINS` protect against browser DNS rebinding, not against direct callers. A proxy in front of it needs connection and idle timeouts: a legacy-style `GET /mcp` with `Accept: text/event-stream` holds a stream open until the client disconnects.

| Variable | Default | Purpose |
| --- | --- | --- |
| `COSMOLEX_MCP_TRANSPORT` | `stdio` | `stdio` or `streamable-http`. |
| `COSMOLEX_MCP_HOST` | `127.0.0.1` | Bind address. `127.0.0.1`, `localhost` and `::1` use the SDK's built-in Host and Origin checks; any other value requires `COSMOLEX_MCP_ALLOWED_HOSTS`. |
| `PORT` | `8080` | Port; must be an integer. An empty value uses `8080`. |
| `COSMOLEX_MCP_ALLOWED_HOSTS` | unset | Comma-separated `Host` header values accepted on a non-loopback bind, such as `mcp.example.com:8080` or `mcp.example.com:*`. |
| `COSMOLEX_MCP_ALLOWED_ORIGINS` | unset | Comma-separated `Origin` values accepted on a non-loopback bind, such as `https://client.example.com`. Requests without an `Origin` header are accepted. |

CosmoLex credentials come from the same configuration as stdio (see [Configuration](#configuration)), never from the request.

```bash
COSMOLEX_MCP_TRANSPORT=streamable-http PORT=8080 uv run --locked cosmolex-mcp
```

Point the MCP client at `http://127.0.0.1:8080/mcp`.

## Error handling

A failed tool call returns an MCP error result (`isError`) whose text starts with `Error executing tool` and the tool name, followed by a fixed message. The server never passes a CosmoLex response body, a request URL or a credential back to the client.

| Situation | What the tool returns |
| --- | --- |
| Setup missing or incomplete | "No CosmoLex connection is configured. Run cosmolex-mcp-setup to connect, then restart the MCP server.", or a message naming the missing `COSMOLEX_API_KEY`, `COSMOLEX_CLIENT_ID` or `COSMOLEX_CLIENT_SECRET`. |
| HTTP 401 (after one automatic token refresh) | "CosmoLex authorization expired or was rejected. Re-run cosmolex-mcp-setup to reconnect." |
| HTTP 403 | "CosmoLex access denied: the connected account lacks permission for this action (or the authorization expired; re-run cosmolex-mcp-setup if so)." |
| HTTP 404 | "CosmoLex resource was not found. Check the requested record." |
| HTTP 429 | "CosmoLex rate limit reached. Retry after N seconds." where N comes from the `Retry-After` header, or "Retry after a short pause." when the header is missing. |
| Any other error status | "CosmoLex returned HTTP 500: vendor service error." (the status varies). The reason comes from a fixed list: invalid request, authorization was rejected, permission was denied, resource was not found, request validation failed, vendor service error, or request failed. |
| Timeout or connection failure on a read | "CosmoLex request did not complete. Check connectivity and retry." |
| Timeout or connection failure on a write | "CosmoLex request outcome is unknown. Check whether the operation completed in CosmoLex before retrying." |
| Response that is not valid JSON | "CosmoLex returned an unreadable response. Check the result in CosmoLex before retrying." |
| A tool the `/v1` API does not support | "list_banks (bank enumeration) is not available in the ProfitSolv LCS /v1 Integration API." (the capability varies). |
| Invalid arguments | A message such as "Invalid arguments: page (expected an integer greater than or equal to 1)." or "fields_json must be a JSON object". |
| Anything else | "Error executing tool list_matters" (the tool name) with no detail. |

Every CosmoLex request has a 30-second timeout. The server does not retry failed requests, does not retry rate-limited requests and does not follow redirects. On HTTP 401 it refreshes the OAuth access token once and repeats the request. A failed resource read returns a fixed message, "CosmoLex resource could not be read." for an unexpected failure.

At startup the server exits with a message on stderr and a non-zero status when `COSMOLEX_MCP_TRANSPORT` is neither `stdio` nor `streamable-http`, when `PORT` is not an integer, or when a non-loopback `COSMOLEX_MCP_HOST` is set without `COSMOLEX_MCP_ALLOWED_HOSTS`.

## Limits of the LCS /v1 API

The ProfitSolv LCS `/v1` Integration API is narrower than CosmoLex's own application. The 43 tools listed as unavailable under [Tools](#tools) cover firm financial summaries, timekeeper billable-time summaries, bank and chart-of-accounts listings, the two-step invoice generation flow, invoice allocations, document upload, download and delete actions, accounts payable, lookup and default-value endpoints, and the separate task and activity code lists (only the combined `get_codes` is available). CosmoLex features the API does not expose at all, such as tasks, timers, calendar, tags, trust, rates, firm roles, tax and discount settings, phone messages, internal chat, workflow, reports, recurring billing, matter templates and court rules, have no tools.

Transaction listing needs a matter or bank scope, and the code lookup needs a matter ID. The text shortcut tools return an access denied error unless your integration is authorized for that endpoint.

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

**Read order.** A credential already set in the process environment wins. Otherwise the server reads the OS keyring, then the `.env` file fallback.

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
> "Log a time entry on matter `<id>`"
>
> "Show open invoices and recent payments"
>
> "List the firm's users"

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

## Testing

The test suite runs offline and needs no CosmoLex account: every CosmoLex API call is replaced by an in-process test double. It covers path-identifier validation, error handling, OAuth redirect and callback validation, setup errors, credential file handling, endpoint allowlists, the stdio server, and the Streamable HTTP transport including the 2026-07-28 wire format, Host and Origin checks and stateless requests.

```bash
uv sync --locked
uv run --locked pytest -q
```

CI runs the suite on every push and pull request to `main`.

## License

MIT. See [LICENSE](LICENSE).
