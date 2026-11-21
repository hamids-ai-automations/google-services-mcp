"""Google Drive adapter (v3)."""

from __future__ import annotations

import io
from pathlib import Path
from typing import Any

from googleapiclient.http import MediaFileUpload, MediaIoBaseDownload

from ..client import GoogleApiClient
from ..config import Settings
from ..exceptions import InvalidArgumentError, SizeLimitExceededError
from ..retry import execute_with_retry
from ..security import ensure_within
from .common import compact, ensure_size, normalize_file

FILE_FIELDS = (
    "id,name,mimeType,modifiedTime,createdTime,size,owners(emailAddress),parents,"
    "webViewLink,trashed,shared,description,iconLink"
)

EXPORT_TARGETS = {
    "text/plain": "text/plain",
    "text/markdown": "text/plain",
    "application/pdf": "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    ),
    "text/csv": "text/csv",
}


class DriveService:
    def __init__(self, client: GoogleApiClient, settings: Settings) -> None:
        self.client = client
        self.settings = settings

    # -- helpers ------------------------------------------------------------
    def _api(self) -> Any:
        return self.client.drive(["https://www.googleapis.com/auth/drive.readonly"])

    def _execute(self, request: Any, *, idempotent: bool = True) -> Any:
        return execute_with_retry(
            request,
            max_retries=self.settings.google.max_retries,
            base_delay=self.settings.google.backoff_base_seconds,
            max_delay=self.settings.google.backoff_max_seconds,
            idempotent=idempotent,
        )

    def download_root(self) -> Path:
        root = self.settings.download_dir()
        root.mkdir(parents=True, exist_ok=True)
        return root

    # -- read operations ----------------------------------------------------
    def list_files(
        self,
        *,
        query: str | None = None,
        page_size: int = 25,
        page_token: str | None = None,
        order_by: str = "modifiedTime desc",
        include_trashed: bool = False,
    ) -> dict[str, Any]:
        api = self._api()
        clauses: list[str] = []
        if query:
            clauses.append(f"({query})")
        if not include_trashed:
            clauses.append("trashed = false")
        payload = {
            "pageSize": min(page_size, self.settings.limits.max_page_size),
            "fields": f"nextPageToken,files({FILE_FIELDS})",
            "orderBy": order_by,
            "q": " and ".join(clauses) if clauses else None,
        }
        if page_token:
            payload["pageToken"] = page_token
        response = self._execute(api.files().list(**compact(payload)))
        files = [normalize_file(item) for item in response.get("files", [])]
        return {
            "files": files,
            "result_count": len(files),
            "next_page_token": response.get("nextPageToken"),
        }

    def search_files(self, *, query: str, page_size: int = 25) -> dict[str, Any]:
        # Restrict free-text search to name/full-text to avoid Drive query injection
        # through operator characters supplied by the model.
        sanitized = query.replace("'", " ")
        drive_query = f"name contains '{sanitized}' or fullText contains '{sanitized}'"
        return self.list_files(query=drive_query, page_size=page_size)

    def get_file(self, file_id: str) -> dict[str, Any]:
        api = self._api()
        item = self._execute(api.files().get(fileId=file_id, fields=FILE_FIELDS, supportsAllDrives=True))
        return {"file": normalize_file(item)}

    def download_text(self, file_id: str, *, max_bytes: int | None = None) -> dict[str, Any]:
        """Download a file into memory, bounded by ``max_download_bytes``."""
        api = self._api()
        limit = max_bytes or self.settings.limits.max_download_bytes
        meta = self._execute(api.files().get(fileId=file_id, fields="id,name,mimeType,size"))
        mime_type = meta.get("mimeType", "")
        declared = int(meta["size"]) if str(meta.get("size", "")).isdigit() else None
        if declared and declared > limit:
            raise SizeLimitExceededError(
                f"File `{meta.get('name')}` is {declared} bytes, above the {limit} byte download limit.",
                details={"file_id": file_id, "size_bytes": declared, "limit_bytes": limit},
            )

        if mime_type.startswith("application/vnd.google-apps."):
            export_mime = _export_mime_for(mime_type)
            data = self._execute(api.files().export_media(fileId=file_id, mimeType=export_mime))
        else:
            buffer = io.BytesIO()
            downloader = MediaIoBaseDownload(buffer, api.files().get_media(fileId=file_id), chunksize=1024 * 1024)
            done = False
            while not done:
                _, done = downloader.next_chunk()
                if buffer.tell() > limit:
                    raise SizeLimitExceededError(
                        f"Download aborted: file exceeds the {limit} byte limit.",
                        details={"file_id": file_id, "limit_bytes": limit},
                    )
            data = buffer.getvalue()
        ensure_size(data, limit, what=f"File `{meta.get('name')}`")
        return {
            "file_id": file_id,
            "name": meta.get("name"),
            "mime_type": mime_type,
            "size_bytes": len(data),
            "content": _decode(data),
        }

    def download_to_disk(self, file_id: str, destination: str) -> dict[str, Any]:
        """Save a file under the configured download directory (no traversal)."""
        root = self.download_root()
        target = ensure_within(root, root / destination)
        target.parent.mkdir(parents=True, exist_ok=True)
        api = self._api()
        meta = self._execute(api.files().get(fileId=file_id, fields="id,name,size,mimeType"))
        declared = int(meta["size"]) if str(meta.get("size", "")).isdigit() else None
        if declared and declared > self.settings.limits.max_download_bytes:
            raise SizeLimitExceededError(
                f"File is {declared} bytes, above the configured download limit.",
                details={"limit_bytes": self.settings.limits.max_download_bytes},
            )
        buffer = io.BytesIO()
        downloader = MediaIoBaseDownload(buffer, api.files().get_media(fileId=file_id), chunksize=1024 * 1024)
        done = False
        while not done:
            _, done = downloader.next_chunk()
            ensure_size(buffer.getvalue(), self.settings.limits.max_download_bytes, what="Download")
        target.write_bytes(buffer.getvalue())
        return {"saved_to": str(target), "size_bytes": target.stat().st_size, "name": meta.get("name")}

    # -- write operations ---------------------------------------------------
    def create_folder(self, name: str, parent_id: str | None = None) -> dict[str, Any]:
        api = self._api()
        body: dict[str, Any] = {"name": name, "mimeType": "application/vnd.google-apps.folder"}
        if parent_id:
            body["parents"] = [parent_id]
        item = self._execute(api.files().create(body=body, fields=FILE_FIELDS, supportsAllDrives=True))
        return {"file": normalize_file(item)}

    def upload_file(
        self,
        *,
        local_path: str,
        name: str | None = None,
        parent_id: str | None = None,
        mime_type: str | None = None,
    ) -> dict[str, Any]:
        root = self.download_root()
        path = ensure_within(root, root / local_path)
        if not path.exists() or not path.is_file():
            raise InvalidArgumentError(f"Local file not found under the upload directory: {local_path}")
        size = path.stat().st_size
        if size > self.settings.limits.max_upload_bytes:
            raise SizeLimitExceededError(
                f"File is {size} bytes, above the {self.settings.limits.max_upload_bytes} byte upload limit."
            )
        api = self._api()
        body: dict[str, Any] = {"name": name or path.name}
        if parent_id:
            body["parents"] = [parent_id]
        media = MediaFileUpload(str(path), mimetype=mime_type or "application/octet-stream", resumable=False)
        item = self._execute(
            api.files().create(body=body, media_body=media, fields=FILE_FIELDS, supportsAllDrives=True),
            idempotent=False,
        )
        return {"file": normalize_file(item)}

    def copy_file(self, file_id: str, *, name: str | None = None, parent_id: str | None = None) -> dict[str, Any]:
        api = self._api()
        body: dict[str, Any] = {}
        if name:
            body["name"] = name
        if parent_id:
            body["parents"] = [parent_id]
        item = self._execute(
            api.files().copy(fileId=file_id, body=body, fields=FILE_FIELDS, supportsAllDrives=True),
            idempotent=False,
        )
        return {"file": normalize_file(item)}

    def move_file(self, file_id: str, *, add_parent: str, remove_parent: str | None = None) -> dict[str, Any]:
        api = self._api()
        current = self._execute(api.files().get(fileId=file_id, fields="id,parents,name"))
        remove_parents = remove_parent or ",".join(current.get("parents") or [])
        item = self._execute(
            api.files().update(
                fileId=file_id,
                addParents=add_parent,
                removeParents=remove_parents,
                fields=FILE_FIELDS,
                supportsAllDrives=True,
            ),
            idempotent=False,
        )
        return {"file": normalize_file(item)}

    def rename_file(self, file_id: str, new_name: str) -> dict[str, Any]:
        api = self._api()
        item = self._execute(
            api.files().update(fileId=file_id, body={"name": new_name}, fields=FILE_FIELDS),
            idempotent=False,
        )
        return {"file": normalize_file(item)}

    def trash_file(self, file_id: str) -> dict[str, Any]:
        api = self._api()
        item = self._execute(
            api.files().update(fileId=file_id, body={"trashed": True}, fields=FILE_FIELDS),
            idempotent=True,
        )
        return {"file": normalize_file(item), "trashed": True}

    def delete_file(self, file_id: str) -> dict[str, Any]:
        api = self._api()
        self._execute(api.files().delete(fileId=file_id, supportsAllDrives=True), idempotent=True)
        return {"deleted": True, "file_id": file_id}

    def share_file(
        self,
        file_id: str,
        *,
        role: str,
        email: str | None = None,
        domain: str | None = None,
        send_notification: bool = False,
    ) -> dict[str, Any]:
        api = self._api()
        body: dict[str, Any] = {"role": role, "type": "user" if email else "domain"}
        if email:
            body["emailAddress"] = email
        if domain:
            body["domain"] = domain
        permission = self._execute(
            api.permissions().create(
                fileId=file_id,
                body=body,
                sendNotificationEmail=send_notification,
                fields="id,role,type,emailAddress,domain",
            ),
            idempotent=False,
        )
        return {"permission": compact(permission)}

    def list_permissions(self, file_id: str) -> dict[str, Any]:
        api = self._api()
        response = self._execute(
            api.permissions().list(fileId=file_id, fields="permissions(id,role,type,emailAddress,domain)")
        )
        return {"permissions": [compact(item) for item in response.get("permissions", [])]}


def _export_mime_for(mime_type: str) -> str:
    mapping = {
        "application/vnd.google-apps.document": "text/plain",
        "application/vnd.google-apps.spreadsheet": "text/csv",
        "application/vnd.google-apps.presentation": "text/plain",
        "application/vnd.google-apps.drawing": "image/png",
    }
    return mapping.get(mime_type, "application/pdf")


def _decode(data: bytes) -> str:
    for encoding in ("utf-8", "utf-16", "latin-1"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return ""
