# Security architecture

This document explains *how* the guarantees in `SECURITY.md` are enforced. Every control listed here lives in the
server; none of them depend on the model cooperating.

## 1. Layered enforcement

```
MCP call
   │
   ├─ tool registered?              registry.register_module  (unknown tool → MCP error)
   ├─ rate limit                     ratelimit.TokenBucket     → RateLimitedError
   ├─ permission policy              permissions.check         → ToolDisabledError
   ├─ argument validation           validation.*               → InvalidArgumentError
   ├─ OAuth scope check              oauth.scopes               → InsufficientScopesError
   ├─ destructive confirmation      safety.require_confirm     → ConfirmationRequiredError
   ├─ Google API call               services/*
   ├─ redact + truncate             security.redact/truncate
   └─ audit record                  audit.AuditLogger
```

Because the policy check precedes argument validation and the API call, a disabled tool never touches the network and
never validates attacker-controlled data.

## 2. Permission policy

`PermissionPolicy.check(spec)` returns `(allowed, reason)` and is evaluated for every call:

1. `mode: read_only` → only `Operation.READ` specs pass.
2. `mode: restricted` → only names in `permissions.allowed_tools` pass.
3. Service disabled → fail with the service name in the reason.
4. Service flag for `spec.policy_key` false → fail with the flag name.

`mode: custom` skips the mode-level gate and relies purely on flags — use it only when you intentionally want
fine-grained control without a global backstop.

`PermissionPolicy.summary()` feeds `google-services-mcp policy`, so the effective matrix is inspectable without reading
YAML.

## 3. Scope validation

Scopes are declared per tool (`ToolSpec.scopes`). Before the request, the token manager reports granted scopes;
missing ones raise `InsufficientScopesError` listing exactly what to grant. In practice this catches the most common
failure: a read-only token paired with a permissive policy.

Read-only scope set: `drive.readonly`, `spreadsheets.readonly`, `gmail.readonly`, `calendar.readonly`,
`documents.readonly`. Write scopes are requested only with `auth login --write`.

## 4. Destructive operations and dry runs

| Class | Requirement |
| --- | --- |
| `Operation.READ` | none |
| `Operation.CREATE` / `UPDATE` | `dry_run` defaults to `true`; pass `dry_run: false` to apply |
| `Operation.DELETE` | `confirm: true` **and** `dry_run: false` |

`gmail_send_email` is opt-in twice at the configuration level plus `confirm: true` per call — three independent keys.
`gmail_create_draft` is deliberately not gated this way: a draft is reviewable and reversible.

## 5. Untrusted content

Google content is attacker-influenced data. On the way out:

- `strip_control_chars()` removes control characters that can hide or reorder text.
- `wrap_untrusted()` fences content and labels it as data, reducing (not eliminating) injection risk.
- `truncate()` caps payloads at `limits.max_result_chars`, so a giant document cannot flood the context window.
- `redact()` scrubs `client_secret`, `refresh_token`, `access_token`, `Authorization` headers from anything logged.

## 6. Filesystem sandbox

`drive_upload_file` and `drive_download_file` resolve paths against `files.download_dir`:

- `ensure_within(root, candidate)` resolves symlinks and rejects `..` traversal outside the root.
- Absolute paths outside the root, UNC paths and drive-relative paths are rejected.
- `limits.max_download_bytes` bounds downloads before they hit disk.

## 7. Audit

`AuditLogger.record()` appends one JSON object per call:

```json
{"ts":"2026-11-21T09:31:02.114Z","tool":"drive_search_files","service":"drive","operation":"read",
 "outcome":"success","duration_ms":184,"correlation_id":"…","detail":{"policy_key":"read","result_count":12}}
```

- No payloads, no tokens, no file contents.
- Denials are recorded as `outcome: "denied"` — a blocked attempt is visible, not silent.
- Size-based rotation with retention (`audit.max_bytes`, `audit.retain_files`).

## 8. Network posture

- `stdio` is the default: the transport trusts the parent process, so the OS user boundary is the security boundary.
- `streamable-http` binds to `127.0.0.1` by default and logs a warning otherwise. It performs **no** user
  authentication. For remote use, terminate TLS and authentication at a reverse proxy and keep the server on a private
  interface.

## 9. Known limitations

- A single token represents one Google account; there is no multi-tenant credential broker.
- The policy is enforced per tool call, not per session, so a compromised *client* can still call any allowed tool as
  often as the rate limiter permits.
- Prompt injection is mitigated, not solved: an agent may still be tricked into an *allowed* action. That is why the
  default is read-only and why writes need explicit opt-in.
