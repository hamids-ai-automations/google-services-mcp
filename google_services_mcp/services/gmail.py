"""Gmail adapter (v1) with safe MIME construction and draft-first sending."""

from __future__ import annotations

import base64
import re
from email.message import EmailMessage
from email.utils import formataddr, parseaddr
from typing import Any

from ..client import GoogleApiClient
from ..config import Settings
from ..exceptions import InvalidArgumentError
from ..retry import execute_with_retry
from .common import compact

# Headers that must never be injected from model-supplied strings.
FORBIDDEN_HEADERS = ("bcc", "cc", "to", "from")  # handled structurally


class GmailService:
    def __init__(self, client: GoogleApiClient, settings: Settings) -> None:
        self.client = client
        self.settings = settings

    def _api(self) -> Any:
        return self.client.gmail(["https://www.googleapis.com/auth/gmail.readonly"])

    def _execute(self, request: Any, *, idempotent: bool = True) -> Any:
        return execute_with_retry(
            request,
            max_retries=self.settings.google.max_retries,
            base_delay=self.settings.google.backoff_base_seconds,
            max_delay=self.settings.google.backoff_max_seconds,
            idempotent=idempotent,
        )

    # -- read ---------------------------------------------------------------
    def get_profile(self) -> dict[str, Any]:
        api = self._api()
        data = self._execute(api.users().getProfile(userId="me"))
        return compact(
            {
                "email_address": data.get("emailAddress"),
                "messages_total": data.get("messagesTotal"),
                "threads_total": data.get("threadsTotal"),
            }
        )

    def list_labels(self) -> dict[str, Any]:
        api = self._api()
        data = self._execute(api.users().labels().list(userId="me"))
        return {
            "labels": [
                compact({"id": item.get("id"), "name": item.get("name"), "type": item.get("type")})
                for item in data.get("labels", [])
            ]
        }

    def list_messages(
        self,
        *,
        query: str | None = None,
        max_results: int = 10,
        label_ids: list[str] | None = None,
        include_spam_trash: bool = False,
    ) -> dict[str, Any]:
        api = self._api()
        payload: dict[str, Any] = {
            "userId": "me",
            "maxResults": min(max_results, self.settings.limits.max_page_size),
            "includeSpamTrash": include_spam_trash,
        }
        if query:
            payload["q"] = query
        if label_ids:
            payload["labelIds"] = label_ids
        data = self._execute(api.users().messages().list(**payload))
        ids = [item.get("id") for item in data.get("messages", [])]
        return {"message_ids": ids, "result_count": len(ids), "estimated_total": data.get("resultSizeEstimate")}

    def get_message(self, message_id: str, *, body_chars: int = 4000) -> dict[str, Any]:
        api = self._api()
        data = self._execute(api.users().messages().get(userId="me", id=message_id, format="full"))
        headers = {
            item.get("name", "").lower(): item.get("value") for item in data.get("payload", {}).get("headers", [])
        }
        body = _extract_body(data.get("payload", {}))[: max(0, body_chars)]
        return {
            "id": data.get("id"),
            "thread_id": data.get("threadId"),
            "label_ids": data.get("labelIds", []),
            "snippet": data.get("snippet"),
            "internal_date": data.get("internalDate"),
            "from": headers.get("from"),
            "to": headers.get("to"),
            "cc": headers.get("cc"),
            "subject": headers.get("subject"),
            "date": headers.get("date"),
            "message_id_header": headers.get("message-id"),
            "body": body,
            "attachment_count": _count_attachments(data.get("payload", {})),
        }

    def list_threads(self, *, query: str | None = None, max_results: int = 10) -> dict[str, Any]:
        api = self._api()
        payload: dict[str, Any] = {"userId": "me", "maxResults": min(max_results, self.settings.limits.max_page_size)}
        if query:
            payload["q"] = query
        data = self._execute(api.users().threads().list(**payload))
        return {"threads": data.get("threads", []), "result_count": len(data.get("threads", []))}

    # -- write --------------------------------------------------------------
    def create_draft(
        self,
        *,
        to: list[str],
        subject: str,
        body: str,
        cc: list[str] | None = None,
        bcc: list[str] | None = None,
        html: bool = False,
        thread_id: str | None = None,
    ) -> dict[str, Any]:
        raw = _build_raw_message(to=to, subject=subject, body=body, cc=cc, bcc=bcc, html=html)
        api = self._api()
        message: dict[str, Any] = {"raw": raw}
        if thread_id:
            message["threadId"] = thread_id
        data = self._execute(api.users().drafts().create(userId="me", body={"message": message}), idempotent=False)
        return compact(
            {
                "draft_id": data.get("id"),
                "message_id": data.get("message", {}).get("id"),
                "thread_id": data.get("message", {}).get("threadId"),
            }
        )

    def send_email(
        self,
        *,
        to: list[str],
        subject: str,
        body: str,
        cc: list[str] | None = None,
        bcc: list[str] | None = None,
        html: bool = False,
        confirm: bool = False,
        dry_run: bool = False,
    ) -> dict[str, Any]:
        """Send mail. Requires both ``confirm=true`` and the ``allow_email_send`` policy flag."""
        _validate_recipients(to, "to")
        if cc:
            _validate_recipients(cc, "cc")
        if bcc:
            _validate_recipients(bcc, "bcc")
        preview = {
            "to": to,
            "cc": cc or [],
            "bcc_count": len(bcc or []),
            "subject": subject,
            "body_chars": len(body),
        }
        if dry_run or not confirm:
            return {
                "sent": False,
                "dry_run": True,
                "preview": preview,
                "reason": "confirm=false" if not confirm else "dry_run=true",
            }
        if not self.settings.permissions.allow_email_send:
            raise InvalidArgumentError("Outbound email is disabled by server policy (allow_email_send=false).")
        raw = _build_raw_message(to=to, subject=subject, body=body, cc=cc, bcc=bcc, html=html)
        api = self._api()
        data = self._execute(api.users().messages().send(userId="me", body={"raw": raw}), idempotent=False)
        return compact(
            {
                "sent": True,
                "message_id": data.get("id"),
                "thread_id": data.get("threadId"),
                "label_ids": data.get("labelIds"),
            }
        )

    def modify_labels(
        self, message_id: str, *, add: list[str] | None = None, remove: list[str] | None = None
    ) -> dict[str, Any]:
        if not add and not remove:
            raise InvalidArgumentError("Provide at least one label to add or remove.")
        api = self._api()
        data = self._execute(
            api.users()
            .messages()
            .modify(userId="me", id=message_id, body={"addLabelIds": add or [], "removeLabelIds": remove or []})
        )
        return compact({"message_id": data.get("id"), "label_ids": data.get("labelIds")})

    def trash_message(self, message_id: str) -> dict[str, Any]:
        api = self._api()
        data = self._execute(api.users().messages().trash(userId="me", id=message_id))
        return {"trashed": True, "message_id": data.get("id"), "label_ids": data.get("labelIds", [])}


# -- helpers ---------------------------------------------------------------
def _validate_recipients(addresses: list[str], field: str) -> None:
    if not addresses:
        raise InvalidArgumentError(f"`{field}` must contain at least one address.")
    for address in addresses:
        _, parsed = parseaddr(address)
        if "@" not in parsed or parsed != address.strip() or "\n" in address or "\r" in address:
            raise InvalidArgumentError(f"Invalid email address in `{field}`: {address!r}")


def _build_raw_message(
    *,
    to: list[str],
    subject: str,
    body: str,
    cc: list[str] | None = None,
    bcc: list[str] | None = None,
    html: bool = False,
) -> str:
    _validate_recipients(to, "to")
    if "\n" in subject or "\r" in subject:
        raise InvalidArgumentError("Subject must not contain line breaks.")
    message = EmailMessage()
    message["To"] = ", ".join(formataddr(parseaddr(address)) for address in to)
    if cc:
        _validate_recipients(cc, "cc")
        message["Cc"] = ", ".join(formataddr(parseaddr(address)) for address in cc)
    if bcc:
        _validate_recipients(bcc, "bcc")
        message["Bcc"] = ", ".join(formataddr(parseaddr(address)) for address in bcc)
    message["Subject"] = subject
    if html:
        message.set_content("This message contains HTML content.")
        message.add_alternative(body, subtype="html")
    else:
        message.set_content(body)
    return base64.urlsafe_b64encode(message.as_bytes()).decode("ascii")


def _walk_parts(part: dict[str, Any]) -> list[dict[str, Any]]:
    parts = [part]
    for child in part.get("parts", []) or []:
        parts.extend(_walk_parts(child))
    return parts


def _extract_body(payload: dict[str, Any]) -> str:
    plain: str | None = None
    html: str | None = None
    for part in _walk_parts(payload):
        mime = part.get("mimeType", "")
        data = part.get("body", {}).get("data")
        if not data:
            continue
        decoded = base64.urlsafe_b64decode(data + "===").decode("utf-8", errors="replace")
        if mime == "text/plain" and plain is None:
            plain = decoded
        elif mime == "text/html" and html is None:
            html = decoded
    if plain:
        return plain
    if html:
        return html_to_text(html)
    return ""


_TAG_RE = re.compile(r"<[^>]+>")
_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)
_BLOCK_RE = re.compile(r"</(p|div|tr|li|h[1-6])>", re.IGNORECASE)
_SCRIPT_RE = re.compile(r"<(script|style)\b.*?</\1>", re.IGNORECASE | re.DOTALL)
_ENTITY_MAP = {"&nbsp;": " ", "&amp;": "&", "&lt;": "<", "&gt;": ">", "&quot;": '"', "&#39;": "'"}


def html_to_text(html: str) -> str:
    """Deterministic HTML-to-text conversion (no network, no exotics)."""
    text = _COMMENT_RE.sub("", html)
    text = _SCRIPT_RE.sub("", text)
    text = _BLOCK_RE.sub("\n", text)
    text = _TAG_RE.sub("", text)
    for entity, replacement in _ENTITY_MAP.items():
        text = text.replace(entity, replacement)
    lines = [line.strip() for line in text.splitlines()]
    return "\n".join(line for line in lines if line)


def _count_attachments(payload: dict[str, Any]) -> int:
    return sum(1 for part in _walk_parts(payload) if part.get("filename") and part.get("body", {}).get("attachmentId"))
