"""Google Docs adapter (v1)."""

from __future__ import annotations

from typing import Any

from ..client import GoogleApiClient
from ..config import Settings
from ..exceptions import InvalidArgumentError
from ..retry import execute_with_retry
from .common import compact


class DocsService:
    def __init__(self, client: GoogleApiClient, settings: Settings) -> None:
        self.client = client
        self.settings = settings

    def _api(self) -> Any:
        return self.client.docs(["https://www.googleapis.com/auth/documents.readonly"])

    def _execute(self, request: Any, *, idempotent: bool = True) -> Any:
        return execute_with_retry(
            request,
            max_retries=self.settings.google.max_retries,
            base_delay=self.settings.google.backoff_base_seconds,
            max_delay=self.settings.google.backoff_max_seconds,
            idempotent=idempotent,
        )

    # -- read ---------------------------------------------------------------
    def get_document(self, document_id: str, *, max_chars: int = 20_000) -> dict[str, Any]:
        api = self._api()
        data = self._execute(api.documents().get(documentId=document_id))
        body = data.get("body", {}).get("content", [])
        text = _extract_text(body)
        headings = _extract_headings(data)
        return {
            "document_id": data.get("documentId"),
            "title": data.get("title"),
            "revision_id": data.get("revisionId"),
            "character_count": len(text),
            "table_count": _count_tables(body),
            "headings": headings,
            "text": text[: max(0, max_chars)],
            "truncated": len(text) > max_chars,
        }

    def get_document_text(self, document_id: str, *, max_chars: int = 20_000) -> dict[str, Any]:
        result = self.get_document(document_id, max_chars=max_chars)
        return compact(
            {
                "document_id": result["document_id"],
                "title": result["title"],
                "character_count": result["character_count"],
                "text": result["text"],
                "truncated": result["truncated"],
            }
        )

    # -- write --------------------------------------------------------------
    def create_document(self, title: str, *, initial_text: str | None = None) -> dict[str, Any]:
        api = self._api()
        data = self._execute(api.documents().create(body={"title": title}), idempotent=False)
        document_id = data.get("documentId")
        if initial_text:
            self.append_text(document_id, initial_text)
        return compact(
            {
                "document_id": document_id,
                "title": data.get("title"),
                "url": f"https://docs.google.com/document/d/{document_id}/edit",
            }
        )

    def append_text(self, document_id: str, text: str, *, heading_style: str | None = None) -> dict[str, Any]:
        api = self._api()
        doc = self._execute(api.documents().get(documentId=document_id, fields="body(content(endIndex))"))
        content = doc.get("body", {}).get("content", [])
        end_index = max((item.get("endIndex", 1) for item in content), default=1) - 1
        requests: list[dict[str, Any]] = [{"insertText": {"location": {"index": end_index}, "text": text}}]
        if heading_style:
            requests.append(
                {
                    "updateParagraphStyle": {
                        "range": {"startIndex": end_index, "endIndex": end_index + len(text)},
                        "paragraphStyle": {"namedStyleType": heading_style},
                        "fields": "namedStyleType",
                    }
                }
            )
        result = self._execute(
            api.documents().batchUpdate(documentId=document_id, body={"requests": requests}),
            idempotent=False,
        )
        return compact(
            {"document_id": document_id, "applied_requests": len(requests), "replies": len(result.get("replies", []))}
        )

    def insert_text(self, document_id: str, text: str, index: int) -> dict[str, Any]:
        if index < 1:
            raise InvalidArgumentError("`index` must be >= 1 (Docs body starts at index 1).")
        api = self._api()
        result = self._execute(
            api.documents().batchUpdate(
                documentId=document_id,
                body={"requests": [{"insertText": {"location": {"index": index}, "text": text}}]},
            ),
            idempotent=False,
        )
        return {"document_id": document_id, "replies": len(result.get("replies", []))}

    def replace_text(self, document_id: str, *, find: str, replace: str, match_case: bool = True) -> dict[str, Any]:
        if not find:
            raise InvalidArgumentError("`find` must not be empty.")
        api = self._api()
        result = self._execute(
            api.documents().batchUpdate(
                documentId=document_id,
                body={
                    "requests": [
                        {
                            "replaceAllText": {
                                "containsText": {"text": find, "matchCase": match_case},
                                "replaceText": replace,
                            }
                        }
                    ]
                },
            ),
            idempotent=True,
        )
        occurrences = 0
        for reply in result.get("replies", []):
            occurrences += reply.get("replaceAllText", {}).get("occurrencesChanged", 0)
        return {"document_id": document_id, "occurrences_changed": occurrences}


def _extract_text(content: list[dict[str, Any]]) -> str:
    chunks: list[str] = []
    for element in content:
        paragraph = element.get("paragraph")
        if paragraph:
            for run in paragraph.get("elements", []):
                text_run = run.get("textRun")
                if text_run:
                    chunks.append(text_run.get("content", ""))
        table = element.get("table")
        if table:
            for row in table.get("tableRows", []):
                cells = []
                for cell in row.get("tableCells", []):
                    cells.append(_extract_text(cell.get("content", [])).strip())
                chunks.append(" | ".join(cells) + "\n")
    return "".join(chunks)


def _extract_headings(document: dict[str, Any]) -> list[dict[str, Any]]:
    headings: list[dict[str, Any]] = []
    for element in document.get("body", {}).get("content", []):
        paragraph = element.get("paragraph")
        if not paragraph:
            continue
        style = paragraph.get("paragraphStyle", {}).get("namedStyleType", "")
        if not style.startswith("HEADING"):
            continue
        text = "".join(run.get("textRun", {}).get("content", "") for run in paragraph.get("elements", [])).strip()
        if text:
            headings.append({"level": style.replace("HEADING_", "H"), "text": text})
    return headings


def _count_tables(content: list[dict[str, Any]]) -> int:
    return sum(1 for element in content if element.get("table"))
