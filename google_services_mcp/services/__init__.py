"""Google service adapters (thin, testable wrappers over google-api-python-client)."""

from .calendar import CalendarService
from .docs import DocsService
from .drive import DriveService
from .gmail import GmailService
from .sheets import SheetsService

__all__ = ["CalendarService", "DocsService", "DriveService", "GmailService", "SheetsService"]
