# Changelog

All notable changes to this project are documented here. Format follows [Keep a Changelog](https://keepachangelog.com)
and the project adheres to [Semantic Versioning](https://semver.org).

## [Unreleased]

### Fixed

- `Retry-After` sent as an HTTP-date (RFC 9110 form) was silently ignored, so a rate-limited call fell back to
  exponential back-off and re-hit the API too early. Both `delay-seconds` and `HTTP-date` are now parsed, and
  past dates resolve to zero wait.
- An unbounded honoured `Retry-After` could stall an MCP tool call for minutes. Delays are now clamped to
  `RETRY_AFTER_CEILING` (120 s) and the clamp is logged as `retry_after_clamped`.

### Added

- `tests/test_retry.py` (15 cases): retryable vs non-retryable statuses, idempotency guard, back-off bounds and
  jitter, both `Retry-After` forms, ceiling clamping, malformed headers, attempt budget, and pass-through of our
  own error types. Five of these cases fail against the previous implementation.
- README "Retry and rate-limit behaviour" section documenting what is retried and why.

## [0.1.0] - 2026-11-21

### Added

- MCP server (`google-services-mcp serve`) over `stdio` and `streamable-http` transports, built on the MCP Python SDK
  (`mcp>=2.3`).
- 44 tools across Drive, Sheets, Gmail, Calendar and Docs, each with a `ToolSpec` describing operation, policy key,
  required scopes and MCP annotations.
- Server-side permission policy: global modes (`read_only`, `read_write`, `restricted`, `custom`) plus per-service,
  per-action flags enforced inside the tool wrapper.
- Two-key outbound email guard (`permissions.allow_email_send` **and** `gmail.send`) with mandatory `confirm=true`.
- Dry-run-by-default writes and `confirm=true` for destructive operations (delete/trash/sheet removal).
- OAuth 2.0 installed-app flow: browser login, console/headless login, remote auth-code exchange, token status and
  revocation. Per-service scope validation with `INSUFFICIENT_SCOPES` failures.
- Typed service adapters for Drive, Sheets, Gmail (including safe MIME construction), Calendar and Docs.
- Security helpers: secret redaction, result truncation, control-character stripping, untrusted-content wrapping and a
  local download/upload sandbox that rejects path traversal.
- JSONL audit log with size-based rotation, retention and an in-memory tail for diagnostics.
- Token-bucket rate limiting, exponential back-off with idempotency awareness, and opaque upstream error mapping.
- CLI: `serve`, `auth login|status|logout`, `policy`, `doctor`.
- Pytest suite covering configuration parsing, permission gating, the execution wrapper and security helpers.

### Fixed

- Tool result schema: the registered wrapper returns a plain `dict[str, Any]` instead of a `ToolResult` model, so
  `build_server()` no longer fails with `PydanticUserError: Output type not fully defined` for tools such as
  `drive_copy_file`.
- `truncate()` bounds the *total* size of a nested payload instead of each string independently, so
  `limits.max_result_chars` actually caps what reaches the model.
- `ensure_within()` raises `InvalidArgumentError` (visible to tools) instead of a bare `ValueError` when a path escapes
  the sandbox.
- Flat service flags (`create: true` next to `enabled:`) now take precedence over the nested `flags:` block, as the
  documentation always implied.
- Default configuration enables all five services read-only, so a fresh install is usable (`policy` no longer reports
  an empty matrix) while every write stays denied.
- Removed a dead nested-`if` branch in `TokenManager.get_credentials()` that could never be reached.

### Tooling

- `tests/test_server.py` builds the real server and asserts all 44 tools expose input/output schemas plus correct
  annotations, locking in the output-schema regression.
- `scripts/gen_tools_doc.py` regenerates `docs/tools.md` from the live `ToolSpec` registry, so the tool reference cannot
  drift from the code; CI fails when it does.
- CI workflow (`.github/workflows/ci.yml`) runs ruff, pytest and the `doctor`/`policy` smoke tests on Ubuntu and Windows
  for Python 3.11 and 3.12, plus the docs freshness check.

---
