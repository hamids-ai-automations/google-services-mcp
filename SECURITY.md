# Security policy

## Reporting a vulnerability

Email **security@hamids-ai.dev** with a description, reproduction steps and the affected version. Please do not open a
public issue for security problems. Expect an acknowledgement within 72 hours.

## Threat model

The server sits between an AI agent and a user's Google account. The agent is assumed to be *untrusted*: it may be
prompt-injected by third-party content (a Gmail body, a shared document, a file name). The operator is trusted.

Consequently the server never relies on the model to behave:

| Risk | Control |
| --- | --- |
| Agent attempts a write the operator never approved | `PermissionPolicy.check()` inside the tool wrapper, before any HTTP call |
| Agent sends email without approval | Two independent keys (`permissions.allow_email_send` + `gmail.send`) plus `confirm=true` per call |
| Agent deletes data | Destructive tools require `confirm=true`; always audited |
| Prompt injection from Google content | Returned text is wrapped as untrusted, control characters stripped, truncated |
| Token / secret leakage | Tokens never returned by tools; `redact()` scrubs keys, bearer tokens, refresh tokens from logs |
| Filesystem escape via Drive upload/download | All local paths must resolve inside `files.download_dir` (`ensure_within`) |
| Runaway agent loops | Token-bucket rate limiter (`limits.requests_per_minute`) returns `RATE_LIMITED` with retry hint |
| Silent tampering | Append-only JSONL audit log with rotation and retention |

## Operational guidance

- Keep `permissions.mode: read_only` until a workflow demonstrably needs more.
- Grant the narrowest OAuth scopes that satisfy the workflow; re-run `auth login` when widening.
- Keep `streamable-http` on loopback. It has no per-user authentication; front it with an authenticating proxy.
- `secrets/` and `logs/` are git-ignored — verify before publishing a fork.
- Rotate the OAuth client secret and revoke the token (`auth logout`) if a machine is lost.

## Supported versions

Security fixes target the latest minor release on `main`.
