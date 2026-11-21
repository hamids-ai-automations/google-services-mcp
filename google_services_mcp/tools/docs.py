"""Google Docs tools (MCP surface)."""

from __future__ import annotations

from ..permissions import Operation, ToolSpec
from ..services.docs import DocsService
from .registry import Runtime, ToolResult, tool

SCOPES = ["https://www.googleapis.com/auth/documents.readonly"]


def _svc(runtime: Runtime) -> DocsService:
    return DocsService(runtime.client, runtime.settings)


SPEC_GET = ToolSpec(
    name="docs_get_document",
    service="docs",
    operation=Operation.READ,
    policy_key="read",
    description="Read a Google Doc: title, headings, table count and plain-text body (truncated).",
    scopes=SCOPES,
)
SPEC_CREATE = ToolSpec(
    name="docs_create_document",
    service="docs",
    operation=Operation.WRITE,
    policy_key="create",
    description="Create a Google Doc with optional initial text. Write operation.",
    scopes=SCOPES,
    idempotent=False,
)
SPEC_APPEND = ToolSpec(
    name="docs_append_text",
    service="docs",
    operation=Operation.WRITE,
    policy_key="update",
    description="Append text to the end of a document, optionally as a named heading style.",
    scopes=SCOPES,
    idempotent=False,
)
SPEC_INSERT = ToolSpec(
    name="docs_insert_text",
    service="docs",
    operation=Operation.WRITE,
    policy_key="update",
    description="Insert text at a specific document index.",
    scopes=SCOPES,
    idempotent=False,
)
SPEC_REPLACE = ToolSpec(
    name="docs_replace_text",
    service="docs",
    operation=Operation.WRITE,
    policy_key="update",
    description="Replace all occurrences of a string in a document; reports how many changed.",
    scopes=SCOPES,
)


@tool(SPEC_GET)
def docs_get_document(runtime: Runtime, document_id: str, max_chars: int = 20_000) -> ToolResult:
    """Read a document."""
    return runtime.run(SPEC_GET, lambda: _svc(runtime).get_document(document_id, max_chars=max_chars))


@tool(SPEC_CREATE)
def docs_create_document(runtime: Runtime, title: str, initial_text: str | None = None) -> ToolResult:
    """Create a document."""
    return runtime.run(SPEC_CREATE, lambda: _svc(runtime).create_document(title, initial_text=initial_text))


@tool(SPEC_APPEND)
def docs_append_text(
    runtime: Runtime,
    document_id: str,
    text: str,
    heading_style: str | None = None,
) -> ToolResult:
    """Append text to a document."""
    return runtime.run(SPEC_APPEND, lambda: _svc(runtime).append_text(document_id, text, heading_style=heading_style))


@tool(SPEC_INSERT)
def docs_insert_text(runtime: Runtime, document_id: str, text: str, index: int) -> ToolResult:
    """Insert text at an index."""
    return runtime.run(SPEC_INSERT, lambda: _svc(runtime).insert_text(document_id, text, index))


@tool(SPEC_REPLACE)
def docs_replace_text(
    runtime: Runtime,
    document_id: str,
    find: str,
    replace: str,
    match_case: bool = True,
) -> ToolResult:
    """Replace text in a document."""
    return runtime.run(
        SPEC_REPLACE,
        lambda: _svc(runtime).replace_text(document_id, find=find, replace=replace, match_case=match_case),
    )
