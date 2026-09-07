"""Weekly ticket-report export independent from the CLI adapter."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from datetime import datetime
from importlib.resources import files
from pathlib import Path
from typing import Callable

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill

from .intraservice.client import IntraserviceClient
from .intraservice.parsing import TicketCard, parse_ticket_card
from .settings import IntraserviceSettings

REPORT_HEADERS = (
    "Заявка",
    "Статус Б24",
    "Статус SD",
    "Тип ТП",
    "Описание",
    "Партнер",
    "Заказчик",
    "Текущий статус/решение",
    "Последнее обновление",
    "Исполнитель",
)

ProgressReporter = Callable[[str], None]


def _normalize_organization(value: str) -> str:
    return " ".join(value.replace("«", '"').replace("»", '"').split()).casefold()


def load_partner_aliases() -> dict[str, str]:
    """Load the project-maintained creator organization to partner mapping."""
    source = files("ispano").joinpath("partner_aliases.json")
    payload = json.loads(source.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or not all(
        isinstance(key, str) and isinstance(value, str) for key, value in payload.items()
    ):
        raise ValueError("partner_aliases.json должен содержать JSON-объект строковых алиасов.")
    return {_normalize_organization(key): value.strip() for key, value in payload.items()}


@dataclass(frozen=True, slots=True)
class TicketReportRow:
    ticket_id: int
    status: str | None
    support_type: str | None
    partner: str | None
    last_updated_at: datetime | None

    @classmethod
    def from_card(cls, ticket_id: int, card: TicketCard, aliases: dict[str, str]) -> "TicketReportRow":
        partner = None
        if card.creator_organization:
            partner = aliases.get(_normalize_organization(card.creator_organization))
        return cls(ticket_id, card.status, card.support_type, partner, card.last_updated_at)

    def values(self) -> tuple[object, ...]:
        return (
            self.ticket_id,
            "",
            self.status or "",
            self.support_type or "",
            "",
            self.partner or "",
            "",
            "",
            self.last_updated_at,
            "",
        )


class TicketReportExporter:
    """Fetch report rows from IntraService ticket cards."""

    def __init__(self, settings: IntraserviceSettings, login: str, password: str) -> None:
        self.settings = settings
        self.login = login
        self.password = password

    def export(self, until_id: int, report: ProgressReporter = print) -> tuple[list[TicketReportRow], set[str]]:
        aliases = load_partner_aliases()
        unknown_organizations: set[str] = set()
        with IntraserviceClient(self.settings, self.login, self.password) as client:
            ticket_ids = client.list_ticket_ids_descending(until_id)
            report(f"Найдено тикетов для отчёта: {len(ticket_ids)}")
            rows: list[TicketReportRow] = []
            for index, ticket_id in enumerate(ticket_ids, 1):
                report(f"[{index}/{len(ticket_ids)}] Тикет {ticket_id}...")
                card = parse_ticket_card(client.get_ticket_page(ticket_id))
                row = TicketReportRow.from_card(ticket_id, card, aliases)
                rows.append(row)
                if card.creator_organization and row.partner is None:
                    unknown_organizations.add(card.creator_organization)
                time.sleep(self.settings.request_delay)
        return rows, unknown_organizations


def write_ticket_report(rows: list[TicketReportRow], output_dir: Path) -> Path:
    """Write a copy-ready single-sheet XLSX report."""
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"tickets_report_{datetime.now():%Y%m%d_%H%M%S}.xlsx"
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Тикеты"
    sheet.append(REPORT_HEADERS)
    for row in rows:
        sheet.append(row.values())

    header_fill = PatternFill("solid", fgColor="1F4E78")
    for cell in sheet[1]:
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    sheet.freeze_panes = "A2"
    sheet.auto_filter.ref = f"A1:J{max(len(rows) + 1, 1)}"
    for row in sheet.iter_rows(min_row=2):
        row[8].number_format = "dd.mm.yyyy"
        row[7].alignment = Alignment(vertical="top", wrap_text=True)
    for column, width in zip("ABCDEFGHIJ", (12, 18, 22, 30, 35, 20, 22, 45, 20, 20), strict=True):
        sheet.column_dimensions[column].width = width
    workbook.save(path)
    return path
