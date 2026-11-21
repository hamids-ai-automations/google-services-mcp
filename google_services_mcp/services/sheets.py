"""Google Sheets adapter (v4)."""

from __future__ import annotations

from typing import Any

from ..client import GoogleApiClient
from ..config import Settings
from ..retry import execute_with_retry
from .common import compact, normalize_spreadsheet_sheets, validate_values_matrix


class SheetsService:
    def __init__(self, client: GoogleApiClient, settings: Settings) -> None:
        self.client = client
        self.settings = settings

    def _api(self) -> Any:
        return self.client.sheets(["https://www.googleapis.com/auth/spreadsheets.readonly"])

    def _execute(self, request: Any, *, idempotent: bool = True) -> Any:
        return execute_with_retry(
            request,
            max_retries=self.settings.google.max_retries,
            base_delay=self.settings.google.backoff_base_seconds,
            max_delay=self.settings.google.backoff_max_seconds,
            idempotent=idempotent,
        )

    # -- read ---------------------------------------------------------------
    def get_spreadsheet(self, spreadsheet_id: str) -> dict[str, Any]:
        api = self._api()
        data = self._execute(
            api.spreadsheets().get(
                spreadsheetId=spreadsheet_id,
                includeGridData=False,
                fields=(
                    "spreadsheetId,properties(title,locale,timeZone),spreadsheetUrl,"
                    "sheets(properties(sheetId,title,index,gridProperties(rowCount,columnCount),hidden))"
                ),
            )
        )
        return {
            "spreadsheet_id": data.get("spreadsheetId"),
            "title": data.get("properties", {}).get("title"),
            "locale": data.get("properties", {}).get("locale"),
            "time_zone": data.get("properties", {}).get("timeZone"),
            "url": data.get("spreadsheetUrl"),
            "sheets": normalize_spreadsheet_sheets(data.get("sheets")),
        }

    def read_range(
        self, spreadsheet_id: str, range_a1: str, *, value_render: str = "FORMATTED_VALUE"
    ) -> dict[str, Any]:
        api = self._api()
        data = self._execute(
            api.spreadsheets()
            .values()
            .get(spreadsheetId=spreadsheet_id, range=range_a1, valueRenderOption=value_render)
        )
        values = data.get("values", [])
        return {
            "range": data.get("range", range_a1),
            "rows": len(values),
            "columns": max((len(row) for row in values), default=0),
            "values": values,
        }

    def batch_read(
        self, spreadsheet_id: str, ranges: list[str], *, value_render: str = "FORMATTED_VALUE"
    ) -> dict[str, Any]:
        api = self._api()
        data = self._execute(
            api.spreadsheets()
            .values()
            .batchGet(spreadsheetId=spreadsheet_id, ranges=ranges, valueRenderOption=value_render)
        )
        return {
            "ranges": [
                {
                    "range": item.get("range"),
                    "rows": len(item.get("values", [])),
                    "values": item.get("values", []),
                }
                for item in data.get("valueRanges", [])
            ]
        }

    # -- write --------------------------------------------------------------
    def create_spreadsheet(self, title: str, *, sheet_title: str | None = None) -> dict[str, Any]:
        api = self._api()
        body: dict[str, Any] = {"properties": {"title": title}}
        if sheet_title:
            body["sheets"] = [{"properties": {"title": sheet_title}}]
        data = self._execute(
            api.spreadsheets().create(body=body, fields="spreadsheetId,properties(title),spreadsheetUrl"),
            idempotent=False,
        )
        return {
            "spreadsheet_id": data.get("spreadsheetId"),
            "title": data.get("properties", {}).get("title"),
            "url": data.get("spreadsheetUrl"),
        }

    def update_range(
        self,
        spreadsheet_id: str,
        range_a1: str,
        values: list[list[Any]],
        *,
        value_input: str = "USER_ENTERED",
    ) -> dict[str, Any]:
        api = self._api()
        matrix = validate_values_matrix(values)
        data = self._execute(
            api.spreadsheets()
            .values()
            .update(
                spreadsheetId=spreadsheet_id,
                range=range_a1,
                valueInputOption=value_input,
                body={"values": matrix},
            )
        )
        return {
            "updated_range": data.get("updatedRange"),
            "updated_rows": data.get("updatedRows"),
            "updated_columns": data.get("updatedColumns"),
            "updated_cells": data.get("updatedCells"),
        }

    def append_rows(
        self,
        spreadsheet_id: str,
        range_a1: str,
        values: list[list[Any]],
        *,
        value_input: str = "USER_ENTERED",
    ) -> dict[str, Any]:
        api = self._api()
        matrix = validate_values_matrix(values)
        data = self._execute(
            api.spreadsheets()
            .values()
            .append(
                spreadsheetId=spreadsheet_id,
                range=range_a1,
                valueInputOption=value_input,
                insertDataOption="INSERT_ROWS",
                body={"values": matrix},
            ),
            idempotent=False,
        )
        updates = data.get("updates", {})
        return {
            "updated_range": updates.get("updatedRange"),
            "appended_rows": updates.get("updatedRows"),
            "appended_cells": updates.get("updatedCells"),
        }

    def clear_range(self, spreadsheet_id: str, range_a1: str) -> dict[str, Any]:
        api = self._api()
        data = self._execute(
            api.spreadsheets().values().clear(spreadsheetId=spreadsheet_id, range=range_a1), idempotent=True
        )
        return {"cleared_range": data.get("clearedRange")}

    def add_sheet(self, spreadsheet_id: str, sheet_title: str) -> dict[str, Any]:
        api = self._api()
        data = self._execute(
            api.spreadsheets().batchUpdate(
                spreadsheetId=spreadsheet_id,
                body={"requests": [{"addSheet": {"properties": {"title": sheet_title}}}]},
            ),
            idempotent=False,
        )
        replies = data.get("replies", [{}])
        props = replies[0].get("addSheet", {}).get("properties", {}) if replies else {}
        return {"sheet": compact({"sheet_id": props.get("sheetId"), "title": props.get("title")})}

    def delete_sheet(self, spreadsheet_id: str, sheet_id: int) -> dict[str, Any]:
        api = self._api()
        data = self._execute(
            api.spreadsheets().batchUpdate(
                spreadsheetId=spreadsheet_id,
                body={"requests": [{"deleteSheet": {"sheetId": sheet_id}}]},
            ),
            idempotent=True,
        )
        return {"deleted_sheet_id": sheet_id, "replies": len(data.get("replies", []))}
