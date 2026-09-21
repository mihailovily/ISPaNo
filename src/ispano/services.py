"""Application services shared by CLI, Telegram, and web adapters."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from .export import ProgressReporter, TicketExporter
from .models import ExportItem
from .serialization import serialize_v2, write_json_export
from .settings import AppSettings, ConfigurationError
from .ticket_report import TicketReportExporter, write_ticket_report
from .ticket_summary import TicketHistorySummarizer


def fetch_export_items(
    settings: AppSettings, cutoff: datetime, report: ProgressReporter = print
) -> list[ExportItem]:
    """Fetch changed tickets and their histories without choosing a delivery format."""
    login, password = settings.intraservice.require_credentials()
    return TicketExporter(settings.intraservice, login, password).export(cutoff, report)


def create_json_export(
    settings: AppSettings, cutoff: datetime, report: ProgressReporter = print
) -> tuple[dict[str, Any], Path]:
    """Create the canonical v2 export and persist it in the configured output directory."""
    items = fetch_export_items(settings, cutoff, report)
    payload = serialize_v2(items, cutoff, settings.export.timezone)
    return payload, write_json_export(payload, settings.export.output_dir)


def create_ticket_report(
    settings: AppSettings,
    until_id: int,
    *,
    use_ai: bool = False,
    report: ProgressReporter = print,
) -> tuple[Path, set[str]]:
    """Create the XLSX report and return its path plus unknown organizations."""
    if until_id <= 0:
        raise ConfigurationError("Номер тикета должен быть положительным целым числом.")
    login, password = settings.intraservice.require_credentials()
    summarizer = (
        TicketHistorySummarizer(settings.ticket_summary)
        if use_ai and settings.ticket_summary.enabled
        else None
    )
    rows, unknown_organizations = TicketReportExporter(
        settings.intraservice, login, password, summarizer
    ).export(until_id, report)
    return write_ticket_report(rows, settings.export.output_dir), unknown_organizations
