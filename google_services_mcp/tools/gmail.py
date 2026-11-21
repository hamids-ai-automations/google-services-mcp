"""Gmail tools (MCP surface). Draft-first; sending needs confirm=true plus policy."""

from __future__ import annotations

from ..permissions import Operation, ToolSpec
from ..services.gmail import GmailService
from .common import clean_query
from .registry import Runtime, ToolResult, tool

SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]


def _svc(runtime: Runtime) -> GmailService:
    return GmailService(runtime.client, runtime.settings)


SPEC_PROFILE = ToolSpec(
    name="gmail_get_profile",
    service="gmail",
    operation=Operation.READ,
    policy_key="read",
    description="Get the connected Gmail address and mailbox totals.",
    scopes=SCOPES,
)
SPEC_LABELS = ToolSpec(
    name="gmail_list_labels",
    service="gmail",
    operation=Operation.READ,
    policy_key="read",
    description="List Gmail labels (including system labels such as INBOX and UNREAD).",
    scopes=SCOPES,
)
SPEC_SEARCH = ToolSpec(
    name="gmail_search_messages",
    service="gmail",
    operation=Operation.READ,
    policy_key="read",
    description="Search Gmail with Gmail query syntax (e.g. 'from:boss@x.com is:unread newer_than:7d'). Returns message IDs.",
    scopes=SCOPES,
)
SPEC_GET = ToolSpec(
    name="gmail_get_message",
    service="gmail",
    operation=Operation.READ,
    policy_key="read",
    description="Fetch one message with headers and a truncated plain-text body.",
    scopes=SCOPES,
)
SPEC_THREADS = ToolSpec(
    name="gmail_list_threads",
    service="gmail",
    operation=Operation.READ,
    policy_key="read",
    description="List Gmail threads matching an optional query.",
    scopes=SCOPES,
)
SPEC_DRAFT = ToolSpec(
    name="gmail_create_draft",
    service="gmail",
    operation=Operation.WRITE,
    policy_key="draft",
    description="Create a Gmail draft. Preferred over sending: nothing leaves the mailbox.",
    scopes=SCOPES,
    idempotent=False,
)
SPEC_SEND = ToolSpec(
    name="gmail_send_email",
    service="gmail",
    operation=Operation.WRITE,
    policy_key="send",
    description="Send an email. Requires confirm=true and allow_email_send=true; returns a dry-run preview otherwise.",
    scopes=SCOPES,
    idempotent=False,
)
SPEC_MODIFY = ToolSpec(
    name="gmail_modify_labels",
    service="gmail",
    operation=Operation.WRITE,
    policy_key="modify",
    description="Add or remove labels on a message (e.g. mark read, archive).",
    scopes=SCOPES,
)
SPEC_TRASH = ToolSpec(
    name="gmail_trash_message",
    service="gmail",
    operation=Operation.DESTRUCTIVE,
    policy_key="trash",
    description="Move a message to Gmail trash (recoverable).",
    scopes=SCOPES,
    destructive=True,
)


@tool(SPEC_PROFILE)
def gmail_get_profile(runtime: Runtime) -> ToolResult:
    """Get the connected Gmail profile."""
    return runtime.run(SPEC_PROFILE, lambda: _svc(runtime).get_profile())


@tool(SPEC_LABELS)
def gmail_list_labels(runtime: Runtime) -> ToolResult:
    """List Gmail labels."""
    return runtime.run(SPEC_LABELS, lambda: _svc(runtime).list_labels())


@tool(SPEC_SEARCH)
def gmail_search_messages(
    runtime: Runtime,
    query: str,
    max_results: int = 10,
    label_ids: list[str] | None = None,
    include_spam_trash: bool = False,
) -> ToolResult:
    """Search messages with Gmail query syntax."""
    return runtime.run(
        SPEC_SEARCH,
        lambda: _svc(runtime).list_messages(
            query=clean_query(runtime.settings, query),
            max_results=max_results,
            label_ids=label_ids,
            include_spam_trash=include_spam_trash,
        ),
    )


@tool(SPEC_GET)
def gmail_get_message(runtime: Runtime, message_id: str, body_chars: int = 4000) -> ToolResult:
    """Fetch one message."""
    return runtime.run(SPEC_GET, lambda: _svc(runtime).get_message(message_id, body_chars=body_chars))


@tool(SPEC_THREADS)
def gmail_list_threads(runtime: Runtime, query: str | None = None, max_results: int = 10) -> ToolResult:
    """List threads."""
    return runtime.run(SPEC_THREADS, lambda: _svc(runtime).list_threads(query=query, max_results=max_results))


@tool(SPEC_DRAFT)
def gmail_create_draft(
    runtime: Runtime,
    to: list[str],
    subject: str,
    body: str,
    cc: list[str] | None = None,
    bcc: list[str] | None = None,
    html: bool = False,
    thread_id: str | None = None,
) -> ToolResult:
    """Create a draft email."""
    return runtime.run(
        SPEC_DRAFT,
        lambda: _svc(runtime).create_draft(
            to=to, subject=subject, body=body, cc=cc, bcc=bcc, html=html, thread_id=thread_id
        ),
    )


@tool(SPEC_SEND)
def gmail_send_email(
    runtime: Runtime,
    to: list[str],
    subject: str,
    body: str,
    cc: list[str] | None = None,
    bcc: list[str] | None = None,
    html: bool = False,
    confirm: bool = False,
    dry_run: bool = False,
) -> ToolResult:
    """Send an email after explicit confirmation."""
    return runtime.run(
        SPEC_SEND,
        lambda: _svc(runtime).send_email(
            to=to, subject=subject, body=body, cc=cc, bcc=bcc, html=html, confirm=confirm, dry_run=dry_run
        ),
    )


@tool(SPEC_MODIFY)
def gmail_modify_labels(
    runtime: Runtime,
    message_id: str,
    add: list[str] | None = None,
    remove: list[str] | None = None,
) -> ToolResult:
    """Add or remove labels on a message."""
    return runtime.run(SPEC_MODIFY, lambda: _svc(runtime).modify_labels(message_id, add=add, remove=remove))


@tool(SPEC_TRASH)
def gmail_trash_message(runtime: Runtime, message_id: str) -> ToolResult:
    """Move a message to trash."""
    return runtime.run(SPEC_TRASH, lambda: _svc(runtime).trash_message(message_id))
