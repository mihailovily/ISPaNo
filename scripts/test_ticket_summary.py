"""Diagnose the OpenAI-compatible AI endpoint used by ``ispano tickets``.

Run from the project root:
    poetry run python scripts/test_ticket_summary.py
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

import requests

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from ispano.settings import TicketSummarySettings  # noqa: E402
from ispano.ticket_summary import TicketHistorySummarizer, TicketSummaryError  # noqa: E402


def _headers(settings: TicketSummarySettings) -> dict[str, str]:
    headers = {"Accept": "application/json"}
    if settings.api_key:
        headers["Authorization"] = f"Bearer {settings.api_key}"
    return headers


def _show_available_models(settings: TicketSummarySettings, *, list_all: bool) -> bool | None:
    """List models when the endpoint implements OpenAI's optional `/models` API."""
    try:
        response = requests.get(
            f"{settings.api_base_url}/models",
            headers=_headers(settings),
            timeout=(10, 30),
        )
        response.raise_for_status()
        payload: Any = response.json()
        models = payload.get("data", []) if isinstance(payload, dict) else []
        model_ids = [item.get("id") for item in models if isinstance(item, dict) and item.get("id")]
        if model_ids:
            print(f"Endpoint вернул моделей: {len(model_ids)}")
            suggested = [
                model_id
                for model_id in ("auto/best-chat", "auto/chat", "auto/fast", "main")
                if model_id in model_ids
            ]
            if suggested:
                print("Подходящие варианты для суммаризации: " + ", ".join(suggested))
            if list_all:
                print("Все доступные модели:")
            for model_id in (model_ids if list_all else []):
                marker = "  <- выбрана" if model_id == settings.model else ""
                print(f"- {model_id}{marker}")
            if settings.model not in model_ids:
                print(
                    "Ошибка конфигурации: указанная TICKET_SUMMARY_MODEL отсутствует "
                    "в списке. Выберите одну из доступных моделей."
                )
                return False
            return True
        else:
            print("`/models` ответил, но не вернул список моделей.")
            return None
    except (requests.RequestException, ValueError) as exc:
        print(f"Не удалось проверить `/models` (это не мешает основному тесту): {exc}")
        return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Проверить AI-суммаризацию тикетов")
    parser.add_argument(
        "--list-models",
        action="store_true",
        help="напечатать все модели, возвращённые endpoint",
    )
    args = parser.parse_args(argv)
    settings = TicketSummarySettings.from_env()
    if not settings.enabled:
        print(
            "ИИ не настроен. Укажите TICKET_SUMMARY_API_BASE_URL и "
            "TICKET_SUMMARY_MODEL в .env."
        )
        return 2

    print(f"Endpoint: {settings.api_base_url}")
    print(f"Модель: {settings.model}")
    print(f"API-ключ: {'задан' if settings.api_key else 'не задан'}")
    if _show_available_models(settings, list_all=args.list_models) is False:
        return 2

    history = [
        {
            "date": "2026-09-10T10:00:00",
            "author": "Инженер",
            "text": "Команда BW реализована на HSM SPB.",
            "events": None,
            "is_private": False,
        },
        {
            "date": "2026-09-10T11:00:00",
            "author": "Инженер",
            "text": "Ждём закрытия. Описание работы команды есть в руководстве программиста, пункт 4.4.15.",
            "events": None,
            "is_private": False,
        },
    ]
    print("Отправляю тестовую историю в `/chat/completions`...")
    try:
        result = TicketHistorySummarizer(settings).summarize(history)
    except TicketSummaryError as exc:
        print(f"Тест не пройден: {exc}")
        return 1

    print("Тест пройден. Ответ модели:")
    print(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
