"""Google Drive tools (MCP surface)."""

from __future__ import annotations

from ..permissions import Operation, ToolSpec
from ..services.drive import DriveService
from .common import clean_query, confirm_guard
from .registry import Runtime, ToolResult, tool

SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]


def _svc(runtime: Runtime) -> DriveService:
    return DriveService(runtime.client, runtime.settings)


SPEC_SEARCH = ToolSpec(
    name="drive_search_files",
    service="drive",
    operation=Operation.READ,
    policy_key="read",
    description="Search Drive by file name or full text. Read-only; returns metadata only.",
    scopes=SCOPES,
)
SPEC_LIST = ToolSpec(
    name="drive_list_files",
    service="drive",
    operation=Operation.READ,
    policy_key="read",
    description="List Drive files with an optional raw Drive query (e.g. \"mimeType='application/pdf'\"). Read-only.",
    scopes=SCOPES,
)
SPEC_GET = ToolSpec(
    name="drive_get_file",
    service="drive",
    operation=Operation.READ,
    policy_key="read",
    description="Fetch metadata for a single Drive file, including owners, size and web link.",
    scopes=SCOPES,
)
SPEC_READ = ToolSpec(
    name="drive_read_file",
    service="drive",
    operation=Operation.READ,
    policy_key="read",
    description="Read a Drive file's text content. Google-native files are exported to text; size-capped.",
    scopes=SCOPES,
)
SPEC_DOWNLOAD = ToolSpec(
    name="drive_download_file",
    service="drive",
    operation=Operation.READ,
    policy_key="read",
    description="Download a Drive file into the server's download directory (path-traversal guarded).",
    scopes=SCOPES,
)
SPEC_CREATE_FOLDER = ToolSpec(
    name="drive_create_folder",
    service="drive",
    operation=Operation.WRITE,
    policy_key="create",
    description="Create a Drive folder. Write operation; audited.",
    scopes=SCOPES,
    idempotent=False,
)
SPEC_UPLOAD = ToolSpec(
    name="drive_upload_file",
    service="drive",
    operation=Operation.WRITE,
    policy_key="upload",
    description="Upload a local file from the server's download directory into Drive. Write operation.",
    scopes=SCOPES,
    idempotent=False,
)
SPEC_COPY = ToolSpec(
    name="drive_copy_file",
    service="drive",
    operation=Operation.WRITE,
    policy_key="create",
    description="Copy a Drive file, optionally into another folder. Write operation.",
    scopes=SCOPES,
    idempotent=False,
)
SPEC_MOVE = ToolSpec(
    name="drive_move_file",
    service="drive",
    operation=Operation.WRITE,
    policy_key="update",
    description="Move a Drive file to a new parent folder. Metadata-only change.",
    scopes=SCOPES,
    idempotent=False,
)
SPEC_RENAME = ToolSpec(
    name="drive_rename_file",
    service="drive",
    operation=Operation.WRITE,
    policy_key="update",
    description="Rename a Drive file.",
    scopes=SCOPES,
)
SPEC_TRASH = ToolSpec(
    name="drive_trash_file",
    service="drive",
    operation=Operation.DESTRUCTIVE,
    policy_key="delete",
    description="Move a Drive file to trash (recoverable for 30 days). Destructive.",
    scopes=SCOPES,
    destructive=True,
)
SPEC_DELETE = ToolSpec(
    name="drive_delete_file",
    service="drive",
    operation=Operation.DESTRUCTIVE,
    policy_key="delete",
    description="Permanently delete a Drive file. Requires confirm=true; irreversible.",
    scopes=SCOPES,
    destructive=True,
)
SPEC_SHARE = ToolSpec(
    name="drive_share_file",
    service="drive",
    operation=Operation.WRITE,
    policy_key="share",
    description="Grant a user or domain access to a Drive file. Access-control change; audited.",
    scopes=SCOPES,
    idempotent=False,
)
SPEC_PERMISSIONS = ToolSpec(
    name="drive_list_permissions",
    service="drive",
    operation=Operation.READ,
    policy_key="read",
    description="List the permissions currently set on a Drive file.",
    scopes=SCOPES,
)


@tool(SPEC_SEARCH)
def drive_search_files(
    runtime: Runtime,
    query: str,
    page_size: int = 25,
) -> ToolResult:
    """Search Drive files by name or full text."""
    return runtime.run(
        SPEC_SEARCH,
        lambda: _svc(runtime).search_files(query=clean_query(runtime.settings, query), page_size=page_size),
    )


@tool(SPEC_LIST)
def drive_list_files(
    runtime: Runtime,
    query: str | None = None,
    page_size: int = 25,
    page_token: str | None = None,
    order_by: str = "modifiedTime desc",
    include_trashed: bool = False,
) -> ToolResult:
    """List Drive files, optionally filtered by a Drive query string."""
    return runtime.run(
        SPEC_LIST,
        lambda: _svc(runtime).list_files(
            query=query,
            page_size=page_size,
            page_token=page_token,
            order_by=order_by,
            include_trashed=include_trashed,
        ),
    )


@tool(SPEC_GET)
def drive_get_file(runtime: Runtime, file_id: str) -> ToolResult:
    """Get metadata for one Drive file."""
    return runtime.run(SPEC_GET, lambda: _svc(runtime).get_file(file_id))


@tool(SPEC_READ)
def drive_read_file(runtime: Runtime, file_id: str, max_bytes: int | None = None) -> ToolResult:
    """Read a Drive file's text content."""
    return runtime.run(SPEC_READ, lambda: _svc(runtime).download_text(file_id, max_bytes=max_bytes))


@tool(SPEC_DOWNLOAD)
def drive_download_file(runtime: Runtime, file_id: str, destination: str) -> ToolResult:
    """Download a Drive file to the server's download directory."""
    return runtime.run(SPEC_DOWNLOAD, lambda: _svc(runtime).download_to_disk(file_id, destination))


@tool(SPEC_CREATE_FOLDER)
def drive_create_folder(runtime: Runtime, name: str, parent_id: str | None = None) -> ToolResult:
    """Create a Drive folder."""
    return runtime.run(SPEC_CREATE_FOLDER, lambda: _svc(runtime).create_folder(name, parent_id))


@tool(SPEC_UPLOAD)
def drive_upload_file(
    runtime: Runtime,
    local_path: str,
    name: str | None = None,
    parent_id: str | None = None,
    mime_type: str | None = None,
) -> ToolResult:
    """Upload a local file (inside the download directory) to Drive."""
    return runtime.run(
        SPEC_UPLOAD,
        lambda: _svc(runtime).upload_file(local_path=local_path, name=name, parent_id=parent_id, mime_type=mime_type),
    )


@tool(SPEC_COPY)
def drive_copy_file(
    runtime: Runtime,
    file_id: str,
    name: str | None = None,
    parent_id: str | None = None,
) -> ToolResult:
    """Copy a Drive file."""
    return runtime.run(SPEC_COPY, lambda: _svc(runtime).copy_file(file_id, name=name, parent_id=parent_id))


@tool(SPEC_MOVE)
def drive_move_file(
    runtime: Runtime,
    file_id: str,
    add_parent: str,
    remove_parent: str | None = None,
) -> ToolResult:
    """Move a Drive file to another folder."""
    return runtime.run(
        SPEC_MOVE,
        lambda: _svc(runtime).move_file(file_id, add_parent=add_parent, remove_parent=remove_parent),
    )


@tool(SPEC_RENAME)
def drive_rename_file(runtime: Runtime, file_id: str, new_name: str) -> ToolResult:
    """Rename a Drive file."""
    return runtime.run(SPEC_RENAME, lambda: _svc(runtime).rename_file(file_id, new_name))


@tool(SPEC_TRASH)
def drive_trash_file(runtime: Runtime, file_id: str) -> ToolResult:
    """Move a Drive file to trash."""
    return runtime.run(SPEC_TRASH, lambda: _svc(runtime).trash_file(file_id))


@tool(SPEC_DELETE)
def drive_delete_file(runtime: Runtime, file_id: str, confirm: bool = False) -> ToolResult:
    """Permanently delete a Drive file (requires confirm=true)."""

    def action() -> dict:
        confirm_guard(runtime.settings, confirm, "drive_delete_file")
        return _svc(runtime).delete_file(file_id)

    return runtime.run(SPEC_DELETE, action)


@tool(SPEC_SHARE)
def drive_share_file(
    runtime: Runtime,
    file_id: str,
    role: str = "reader",
    email: str | None = None,
    domain: str | None = None,
    send_notification: bool = False,
) -> ToolResult:
    """Share a Drive file with a user or domain."""
    return runtime.run(
        SPEC_SHARE,
        lambda: _svc(runtime).share_file(
            file_id, role=role, email=email, domain=domain, send_notification=send_notification
        ),
    )


@tool(SPEC_PERMISSIONS)
def drive_list_permissions(runtime: Runtime, file_id: str) -> ToolResult:
    """List permissions on a Drive file."""
    return runtime.run(SPEC_PERMISSIONS, lambda: _svc(runtime).list_permissions(file_id))
