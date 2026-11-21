# Tool reference

Every tool is gated by `PermissionPolicy` before the Google call and audited afterwards. `Policy` is the key that must
be enabled under `permissions.services.<service>.`; `Destructive` means `confirm: true` is required; `Idempotent` is
used for retry/back-off decisions. `Available now` reflects the default configuration shipped in
`config/config.example.yaml` (read-only mode).

Regenerate with `python scripts/gen_tools_doc.py`.

Registered tools: **44**.

## Calendar

| Tool | Policy | Operation | Destructive | Idempotent | Available now | Description |
| --- | --- | --- | --- | --- | --- | --- |
| `calendar_check_availability` | `read` | read | — | yes | yes | Query free/busy blocks for one or more calendars in a time window. |
| `calendar_create_event` | `create` | write | — | no | no | Create an event. Supports dry_run=true to preview the payload without writing. |
| `calendar_delete_event` | `delete` | destructive | yes | yes | no | Delete a calendar event. Requires confirm=true. |
| `calendar_get_event` | `read` | read | — | yes | yes | Fetch a single calendar event by ID. |
| `calendar_list_calendars` | `read` | read | — | yes | yes | List calendars visible to the connected account with access roles. |
| `calendar_list_events` | `read` | read | — | yes | yes | List events in a time window (RFC3339), optionally filtered by free-text query. |
| `calendar_update_event` | `update` | write | — | yes | no | Patch fields on an existing event (summary, times, location, attendees). |

## Docs

| Tool | Policy | Operation | Destructive | Idempotent | Available now | Description |
| --- | --- | --- | --- | --- | --- | --- |
| `docs_append_text` | `update` | write | — | no | no | Append text to the end of a document, optionally as a named heading style. |
| `docs_create_document` | `create` | write | — | no | no | Create a Google Doc with optional initial text. Write operation. |
| `docs_get_document` | `read` | read | — | yes | yes | Read a Google Doc: title, headings, table count and plain-text body (truncated). |
| `docs_insert_text` | `update` | write | — | no | no | Insert text at a specific document index. |
| `docs_replace_text` | `update` | write | — | yes | no | Replace all occurrences of a string in a document; reports how many changed. |

## Drive

| Tool | Policy | Operation | Destructive | Idempotent | Available now | Description |
| --- | --- | --- | --- | --- | --- | --- |
| `drive_copy_file` | `create` | write | — | no | no | Copy a Drive file, optionally into another folder. Write operation. |
| `drive_create_folder` | `create` | write | — | no | no | Create a Drive folder. Write operation; audited. |
| `drive_delete_file` | `delete` | destructive | yes | yes | no | Permanently delete a Drive file. Requires confirm=true; irreversible. |
| `drive_download_file` | `read` | read | — | yes | yes | Download a Drive file into the server's download directory (path-traversal guarded). |
| `drive_get_file` | `read` | read | — | yes | yes | Fetch metadata for a single Drive file, including owners, size and web link. |
| `drive_list_files` | `read` | read | — | yes | yes | List Drive files with an optional raw Drive query (e.g. "mimeType='application/pdf'"). Read-only. |
| `drive_list_permissions` | `read` | read | — | yes | yes | List the permissions currently set on a Drive file. |
| `drive_move_file` | `update` | write | — | no | no | Move a Drive file to a new parent folder. Metadata-only change. |
| `drive_read_file` | `read` | read | — | yes | yes | Read a Drive file's text content. Google-native files are exported to text; size-capped. |
| `drive_rename_file` | `update` | write | — | yes | no | Rename a Drive file. |
| `drive_search_files` | `read` | read | — | yes | yes | Search Drive by file name or full text. Read-only; returns metadata only. |
| `drive_share_file` | `share` | write | — | no | no | Grant a user or domain access to a Drive file. Access-control change; audited. |
| `drive_trash_file` | `delete` | destructive | yes | yes | no | Move a Drive file to trash (recoverable for 30 days). Destructive. |
| `drive_upload_file` | `upload` | write | — | no | no | Upload a local file from the server's download directory into Drive. Write operation. |

## Gmail

| Tool | Policy | Operation | Destructive | Idempotent | Available now | Description |
| --- | --- | --- | --- | --- | --- | --- |
| `gmail_create_draft` | `draft` | write | — | no | no | Create a Gmail draft. Preferred over sending: nothing leaves the mailbox. |
| `gmail_get_message` | `read` | read | — | yes | yes | Fetch one message with headers and a truncated plain-text body. |
| `gmail_get_profile` | `read` | read | — | yes | yes | Get the connected Gmail address and mailbox totals. |
| `gmail_list_labels` | `read` | read | — | yes | yes | List Gmail labels (including system labels such as INBOX and UNREAD). |
| `gmail_list_threads` | `read` | read | — | yes | yes | List Gmail threads matching an optional query. |
| `gmail_modify_labels` | `modify` | write | — | yes | no | Add or remove labels on a message (e.g. mark read, archive). |
| `gmail_search_messages` | `read` | read | — | yes | yes | Search Gmail with Gmail query syntax (e.g. 'from:boss@x.com is:unread newer_than:7d'). Returns message IDs. |
| `gmail_send_email` | `send` | write | — | no | no | Send an email. Requires confirm=true and allow_email_send=true; returns a dry-run preview otherwise. |
| `gmail_trash_message` | `trash` | destructive | yes | yes | no | Move a message to Gmail trash (recoverable). |

## Sheets

| Tool | Policy | Operation | Destructive | Idempotent | Available now | Description |
| --- | --- | --- | --- | --- | --- | --- |
| `sheets_add_sheet` | `create` | write | — | no | no | Add a new tab to an existing spreadsheet. |
| `sheets_append_rows` | `write` | write | — | no | no | Append rows after the last row of a table. Write operation. |
| `sheets_batch_read` | `read` | read | — | yes | yes | Read several A1 ranges from one spreadsheet in a single API call. |
| `sheets_clear_range` | `write` | destructive | yes | yes | no | Clear values in an A1 range, keeping formatting. Destructive to cell data. |
| `sheets_create_spreadsheet` | `create` | write | — | no | no | Create a new spreadsheet with an optional initial tab. Write operation. |
| `sheets_delete_sheet` | `delete` | destructive | yes | yes | no | Delete a tab (by numeric sheetId) from a spreadsheet. Requires confirm=true. |
| `sheets_get_spreadsheet` | `read` | read | — | yes | yes | Get spreadsheet metadata: title, locale, time zone and the list of tabs. |
| `sheets_read_range` | `read` | read | — | yes | yes | Read an A1 range (e.g. 'Sheet1!A1:D20') from a spreadsheet. Read-only. |
| `sheets_update_range` | `write` | write | — | yes | no | Overwrite an A1 range with a 2-D values array. Write operation; audited. |

## OAuth scopes referenced

- `https://www.googleapis.com/auth/calendar.readonly`
- `https://www.googleapis.com/auth/documents.readonly`
- `https://www.googleapis.com/auth/drive.readonly`
- `https://www.googleapis.com/auth/gmail.readonly`
- `https://www.googleapis.com/auth/spreadsheets.readonly`
