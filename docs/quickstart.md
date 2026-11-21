# Quickstart

Ten minutes from clone to a read-only agent that can list your Drive and read a Doc.

## 1. Create the OAuth client

1. Open [Google Cloud Console](https://console.cloud.google.com/) → create (or pick) a project.
2. **APIs & Services → Library**: enable *Google Drive API*, *Google Sheets API*, *Gmail API*, *Google Calendar API*,
   *Google Docs API*.
3. **APIs & Services → OAuth consent screen**: choose *External* (or *Internal* for Workspace), add your account as a
   test user while the app is in testing.
4. **Credentials → Create credentials → OAuth client ID → Desktop app**. Download the JSON.

```bash
mkdir -p secrets
mv ~/Downloads/client_secret_*.json secrets/client_secrets.json
```

> Desktop-app clients are required: the server uses a loopback redirect. Do not create a "Web application" client.

## 2. Install

```bash
python -m venv .venv
.\.venv\Scripts\activate
pip install -e .
```

## 3. Configure (read-only start)

```bash
cp config/config.example.yaml config/config.yaml
```

The shipped example is already conservative: `mode: read_only`, Drive read only, Gmail read + draft, everything else
read-only. Keep it that way for the first run.

## 4. Authorise

```bash
google-services-mcp auth login
```

A browser opens; consent to the read scopes. The refresh token lands in `secrets/token.json` (mode 600 on POSIX).

```bash
google-services-mcp auth status
```

You should see `token_present: true`. `google-services-mcp doctor` prints the resolved config, credential paths and the
current tool allow-list.

## 5. Connect a client

Claude Desktop / Cursor / Marvis (stdio):

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

Ask the agent: *"List my 5 most recent Google Docs."* → `drive_search_files` runs, audit log records it.

## 6. Widen deliberately

To let the agent create a Sheet:

```yaml
permissions:
  mode: read_write
  services:
    sheets:
      create: true
```

Restart the server and call `sheets_create_spreadsheet`. Writes are dry-run unless the caller passes `dry_run: false`,
so a preview comes back before anything hits Google.

To send mail you need all three: `permissions.allow_email_send: true`, `gmail.send: true`, and `confirm: true` on the
`gmail_send_email` call. Prefer `gmail_create_draft` — it leaves the mailbox untouched and lets a human press send.

## Troubleshooting

| Symptom | Cause | Fix |
| --- | --- | --- |
| `INSUFFICIENT_SCOPES` | Token lacks the scope a tool needs | `auth login --write`, consent again |
| `TOOL_DISABLED` / `denied` | Policy flag off or mode too strict | `google-services-mcp policy`, widen the flag |
| `AuthenticationError: client secrets not found` | Path wrong | `GSMCP_OAUTH_CLIENT_SECRETS_FILE`, or edit `config.yaml` |
| `403 accessNotConfigured` | API not enabled in the project | Enable it in API Library |
| `RATE_LIMITED` | Local token bucket drained | Raise `limits.requests_per_minute` or slow the agent |
| Browser flow hangs on a headless box | No loopback browser | `auth login --console` or `auth login --no-browser` + `--code` |
