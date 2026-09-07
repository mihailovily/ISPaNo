"""Compatibility adapter for the original interactive parser command."""

from __future__ import annotations

import sys
from datetime import datetime

from .export import TicketExporter
from .intraservice.parsing import parse_dot_datetime
from .serialization import serialize_legacy, write_json_export
from .settings import AppSettings, ConfigurationError


def _read_date() -> datetime:
    while True:
        raw = input(
            "С какой даты брать тикеты (изменённые ПОСЛЕ неё)? "
            "Формат ДД.ММ.ГГГГ или ДД.ММ.ГГГГ ЧЧ:ММ:\n> "
        ).strip()
        value = parse_dot_datetime(raw) or parse_dot_datetime(f"{raw} 00:00")
        if value:
            return value
        print("Не понял дату, попробуй ещё раз.")


def main() -> int:
    try:
        settings = AppSettings.from_env()
        login, password = settings.intraservice.require_credentials()
        items = TicketExporter(settings.intraservice, login, password).export(_read_date())
        path = write_json_export(
            serialize_legacy(items), settings.export.output_dir, update_latest=False
        )
        print(f"\nГотово. Сохранено {len(items)} тикетов в {path}")
        return 0
    except ConfigurationError as exc:
        print(f"Ошибка конфигурации: {exc}", file=sys.stderr)
        return 2
