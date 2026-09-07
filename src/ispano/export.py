"""Export orchestration independent from Telegram and CLI."""

from __future__ import annotations

import time
from datetime import datetime
from typing import Callable

import requests

from .intraservice.client import (
    IntraserviceClient,
    IntraserviceResponseError,
    IntraserviceTimeoutError,
)
from .models import ExportItem
from .settings import IntraserviceSettings
from .intraservice.parsing import parse_api_datetime

ProgressReporter = Callable[[str], None]


class TicketExporter:
    """Fetch tickets and their histories while reporting progress."""

    def __init__(self, settings: IntraserviceSettings, login: str, password: str) -> None:
        self.settings = settings
        self.login = login
        self.password = password

    def export(self, cutoff: datetime, report: ProgressReporter = print) -> list[ExportItem]:
        with IntraserviceClient(self.settings, self.login, self.password) as client:
            report(f"Авторизация выполнена. Ищу тикеты после {cutoff}...")
            tickets = client.iter_changed_tasks(cutoff, report)
            report(f"Найдено тикетов: {len(tickets)}")
            result: list[ExportItem] = []
            for index, ticket in enumerate(tickets, 1):
                ticket_id = ticket.get("Id")
                report(f"[{index}/{len(tickets)}] Тикет {ticket_id}...")
                try:
                    created_at = parse_api_datetime(ticket.get("Created"))
                    upper_bound = (
                        parse_api_datetime(ticket.get("Closed"))
                        or parse_api_datetime(ticket.get("Changed"))
                        or datetime.now()
                    )
                    chat = client.get_ticket_chat(ticket_id, created_at, upper_bound)
                    time.sleep(self.settings.request_delay)
                except IntraserviceTimeoutError:
                    raise
                except (requests.RequestException, IntraserviceResponseError) as exc:
                    report(f"Ошибка запроса для тикета {ticket_id}: {exc}")
                    continue
                result.append(ExportItem(ticket=ticket, chat=chat))
            return sorted(result, key=lambda item: int(item.ticket.get("Id", 0)), reverse=True)
