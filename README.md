# Google Services MCP

A permission-controlled [Model Context Protocol](https://modelcontextprotocol.io) gateway that gives AI agents scoped,
auditable access to **Google Drive, Sheets, Gmail, Calendar and Docs** — with OAuth scopes, a server-side permission
policy, mandatory confirmation for destructive actions, rate limiting and a JSONL audit trail.

The design goal is blunt: an agent should be able to *read* your workspace by default, and only *change* it when a human
operator deliberately widened the policy. The policy lives in the server, not in the prompt, so no amount of prompting
can talk its way past it.

```
agent ──MCP──▶ tool wrapper ──▶ 1. rate limit ──▶ 2. permission policy ──▶ 3. Google API
                                    │                                         │
                                    └── 4. redact + truncate ◀────────────────┘
                                                     │
                                                     └──▶ audit.jsonl
```

## Highlights

- **Default read-only.** `read_only` mode blocks every write/destructive tool before a network call is made.
- **Per-service, per-action flags.** `drive.share`, `gmail.send`, `calendar.delete`, … each have their own switch.
- **Two-key outbound email.** Sending requires `permissions.allow_email_send: true` *and* `gmail.send: true` *and*
  `confirm: true` on the call itself.
- **Dry-run by default.** Writes preview their effect unless the caller passes `dry_run: false`; deletions need
  `confirm: true` as well.
- **44 tools** across five services, each with an MCP `ToolSpec` (operation, policy key, scopes, annotations).
- **Untrusted content handling.** Gmail/Drive/Docs text is wrapped and control characters stripped before it reaches the
  model, so a malicious document cannot smuggle instructions.
- **Local file sandbox.** Drive upload/download are confined to `files.download_dir`; path traversal is rejected.
- **Audit without payloads.** `logs/audit.jsonl` records tool, service, outcome, duration, correlation id — never
  message bodies or tokens.

## Install

```bash
git clone https://github.com/hamids-ai-automations/google-services-mcp.git
cd google-services-mcp
python -m venv .venv
.\.venv\Scripts\activate            # Windows
# source .venv/bin/activate         # macOS / Linux
pip install -e ".[dev]"
```

Requirements: Python 3.11+, an OAuth client (Desktop app) from Google Cloud Console with the Drive, Sheets, Gmail,
Calendar and Docs APIs enabled.

## Configure

```bash
cp config/config.example.yaml config/config.yaml
cp .env.example .env
```

Every flag in `permissions.services` maps to a policy key used by the tools. Widening one widens what the agent can do:

| Service | Policy keys | Notes |
| --- | --- | --- |
| `drive` | `read`, `create`, `update`, `upload`, `share`, `delete` | `delete` also needs `confirm=true` per call |
| `sheets` | `read`, `write`, `create`, `delete` | `delete` removes a whole sheet (irreversible) |
| `gmail` | `read`, `draft`, `send`, `modify`, `trash` | `send` needs `allow_email_send` + `confirm=true` |
| `calendar` | `read`, `create`, `update`, `delete` | deleting an event also needs `confirm=true` |
| `docs` | `read`, `create`, `update` | updates are append/insert/replace-text only |

`permissions.mode` adds a global gate on top: `read_only` (reads only), `read_write` (flag-driven), `restricted`
(only names in `allowed_tools`), `custom` (flags only, no mode-level short-circuit).

## Authorise

```bash
google-services-mcp auth login               # opens a browser, stores the refresh token
google-services-mcp auth login --console     # headless: paste the code
google-services-mcp auth login --write       # request write scopes too
google-services-mcp auth status              # token presence, expiry, granted scopes
google-services-mcp auth logout              # revoke at Google and delete locally
```

Tick the scopes you actually intend to use. A token that was granted read-only scopes cannot perform writes even if the
policy allows them — the server fails fast with `INSUFFICIENT_SCOPES` instead of a confusing 403.

## Run

```bash
google-services-mcp serve                        # stdio (Claude Desktop, Cursor, Marvis, …)
GSMCP_TRANSPORT=streamable-http google-services-mcp serve
```

Register with an MCP client (stdio):

```json
{
  "mcpServers": {
    "google-services": {
      "command": "D:\\GitHub Profile\\google-services-mcp\\.venv\\Scripts\\python.exe",
      "args": ["-m", "google_services_mcp", "serve", "--config", "D:\\GitHub Profile\\google-services-mcp\\config\\config.yaml"]
    }
  }
}
```

`streamable-http` binds to loopback by default. Do **not** expose it directly: it has no built-in user authentication —
put an authenticating reverse proxy in front of it, or keep the transport on `stdio`.

## CLI

| Command | Purpose |
| --- | --- |
| `serve` | Run the MCP server over the configured transport. |
| `auth login / status / logout` | Manage the OAuth credential (never prints tokens). |
| `policy` | Print the effective permission matrix. |
| `doctor` | Config, credential, path and tool-allow-list diagnostics as JSON. |

## Tools

44 tools, all prefixed by service. See [docs/tools.md](docs/tools.md) for the full reference with policy keys and
arguments.

- **Drive** — `drive_search_files`, `drive_list_files`, `drive_get_file`, `drive_read_file`, `drive_download_file`,
  `drive_upload_file`, `drive_create_folder`, `drive_copy_file`, `drive_move_file`, `drive_rename_file`,
  `drive_share_file`, `drive_trash_file`, `drive_delete_file`, `drive_list_permissions`
- **Sheets** — `sheets_get_spreadsheet`, `sheets_read_range`, `sheets_batch_read`, `sheets_update_range`,
  `sheets_append_rows`, `sheets_clear_range`, `sheets_create_spreadsheet`, `sheets_add_sheet`, `sheets_delete_sheet`
- **Gmail** — `gmail_get_profile`, `gmail_list_labels`, `gmail_search_messages`, `gmail_get_message`,
  `gmail_list_threads`, `gmail_create_draft`, `gmail_send_email`, `gmail_modify_labels`, `gmail_trash_message`
- **Calendar** — `calendar_list_calendars`, `calendar_list_events`, `calendar_get_event`,
  `calendar_check_availability`, `calendar_create_event`, `calendar_update_event`, `calendar_delete_event`
- **Docs** — `docs_get_document`, `docs_create_document`, `docs_append_text`, `docs_insert_text`, `docs_replace_text`

## Security model

Read [docs/security.md](docs/security.md) and [SECURITY.md](SECURITY.md). Short version:

1. Tools are only reachable if registered, and each registration carries an explicit `ToolSpec`.
2. `PermissionPolicy.check()` runs inside the wrapper before any HTTP call; denial is audited as `denied`.
3. Scopes are validated per service; missing scopes raise `INSUFFICIENT_SCOPES` with the missing list.
4. Destructive tools require `confirm: true`; writes default to `dry_run: true`.
5. Returned Google content is treated as data: wrapped, control-stripped, truncated, never executed.

## Retry and rate-limit behaviour

Every Google API call goes through `google_services_mcp.retry.execute_with_retry`:

- **What is retried.** Only `429`, `500`, `502`, `503`, `504` (and transport errors with no HTTP status) are retried,
  and only for idempotent operations. Non-idempotent calls (`gmail_send_message`, event creation without a stable id)
  fail fast — a duplicate side effect is worse than a visible error.
- **How long we wait.** When Google sends `Retry-After`, it is honoured in **both** RFC 9110 forms: `delay-seconds`
  (`Retry-After: 7`) and `HTTP-date` (`Retry-After: Sat, 21 Nov 2026 12:00:30 GMT`). Anything above
  `RETRY_AFTER_CEILING` (120 s) is clamped and logged as `retry_after_clamped`, because a single MCP tool call must not
  block for minutes. Without a hint, back-off is exponential from `backoff_base_seconds` with ±25 % jitter, capped at
  `backoff_max_seconds`.
- **How many attempts.** `max_retries` (default 3) plus the initial attempt; the last failure surfaces as a typed
  `GoogleServicesMCPError` whose `retryable` flag tells the client whether a retry is worth trying.

```bash
.\.venv\Scripts\python.exe -m pytest tests\test_retry.py -q   # 15 cases, no network, no real sleeping
```

## Development

```bash
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m ruff format --check .
.\.venv\Scripts\python.exe -m google_services_mcp --config config\config.example.yaml policy
.\.venv\Scripts\python.exe scripts\gen_tools_doc.py   # regenerate docs/tools.md from ToolSpec metadata
```

CI (`.github/workflows/ci.yml`) runs the same commands on Ubuntu and Windows for Python 3.11 and 3.12, and fails if
`docs/tools.md` is out of date.

When adding a tool: declare a `ToolSpec`, register it in the service module, add a permission flag in `config.py` if it
introduces a new operation, then rerun `scripts/gen_tools_doc.py`.

Layout:

```
google_services_mcp/
  config.py        settings models + YAML/env loading
  permissions.py   policy + ToolSpec
  tools/           one module per service + registry/wrapper
  services/        typed Google API adapters
  oauth/           token manager, scopes, authorisation flows
  audit.py         JSONL audit log with rotation
  security.py      redaction, truncation, sandboxing, untrusted wrapping
```

## License

MIT — see [LICENSE](LICENSE).
