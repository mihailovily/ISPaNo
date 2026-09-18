"""Command-line entry points for exports and the Telegram bot."""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timedelta
from typing import Sequence
from zoneinfo import ZoneInfo

from .intraservice.client import (
    AuthenticationError,
    IntraserviceResponseError,
    IntraserviceTimeoutError,
)
from .intraservice.parsing import parse_dot_datetime
from .settings import AppSettings, ConfigurationError, PROJECT_ROOT
from .services import create_json_export, create_ticket_report


def _parse_since(raw: str) -> datetime:
    value = parse_dot_datetime(raw) or parse_dot_datetime(f"{raw} 00:00")
    if value:
        return value
    try:
        return datetime.fromisoformat(raw)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            "ожидался ДД.ММ.ГГГГ, ДД.ММ.ГГГГ ЧЧ:ММ или ISO 8601"
        ) from exc


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ispano", description="Экспорт тикетов IntraService")
    subparsers = parser.add_subparsers(dest="command", required=True)
    export = subparsers.add_parser("export", help="выгрузить тикеты в JSON")
    export.add_argument("--since", type=_parse_since, help="дата отсечения")
    tickets = subparsers.add_parser("tickets", help="выгрузить таблицу для недельного отчёта")
    tickets.add_argument("ticket_id", type=int, help="последний номер тикета в выгрузке")
    subparsers.add_parser("bot", help="запустить Telegram-бота")
    subparsers.add_parser("web", help="запустить защищённый веб-интерфейс")
    return parser


def _require_env_file() -> bool:
    """Give a first-run hint before commands need environment configuration."""
    if (PROJECT_ROOT / ".env").is_file():
        return True
    print(
        "Ошибка конфигурации: не найден .env. "
        "Запустите `python setup.py` для первичной настройки.",
        file=sys.stderr,
    )
    return False


def run_export(args: argparse.Namespace) -> int:
    settings = AppSettings.from_env()
    cutoff = args.since or (
        datetime.now(ZoneInfo(settings.export.timezone)).replace(tzinfo=None)
        - timedelta(hours=settings.export.default_lookback_hours)
    )
    if cutoff.tzinfo is not None:
        cutoff = cutoff.astimezone(ZoneInfo(settings.export.timezone)).replace(tzinfo=None)
    payload, path = create_json_export(settings, cutoff)
    print(f"Готово. Сохранено {len(payload['tickets'])} тикетов в {path}")
    return 0


def run_bot() -> int:
    from .telegram.app import build_application

    settings = AppSettings.from_env(include_telegram=True)
    build_application(settings).run_polling()
    return 0


def run_tickets(args: argparse.Namespace) -> int:
    settings = AppSettings.from_env()
    use_ai = False
    if settings.ticket_summary.enabled:
        answer = input(
            "Использовать ИИ для заполнения статусов и описаний? [y/N] "
        ).strip().casefold()
        if answer == "y":
            use_ai = True
    path, unknown_organizations = create_ticket_report(settings, args.ticket_id, use_ai=use_ai)
    print(f"Готово. Сохранено отчёт в {path}")
    if unknown_organizations:
        print("Неизвестные организации (добавьте алиасы в partner_aliases.json):")
        for organization in sorted(unknown_organizations):
            print(f"- {organization}")
    return 0


def run_web() -> int:
    from .web.app import create_app
    import uvicorn

    settings = AppSettings.from_env(include_web=True)
    web = settings.require_web()
    uvicorn.run(create_app(settings), host=web.host, port=web.port)
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    if not _require_env_file():
        return 2
    try:
        if args.command == "export":
            return run_export(args)
        if args.command == "tickets":
            return run_tickets(args)
        if args.command == "bot":
            return run_bot()
        if args.command == "web":
            return run_web()
    except ConfigurationError as exc:
        print(f"Ошибка конфигурации: {exc}", file=sys.stderr)
        return 2
    except AuthenticationError as exc:
        print(f"Ошибка авторизации: {exc}", file=sys.stderr)
        return 3
    except IntraserviceTimeoutError as exc:
        print(f"Сетевая ошибка: {exc}", file=sys.stderr)
        return 4
    except IntraserviceResponseError as exc:
        print(f"Ошибка ответа IntraService: {exc}", file=sys.stderr)
        return 4
    except OSError as exc:
        print(f"Ошибка записи файла: {exc}", file=sys.stderr)
        return 5
    return 2
