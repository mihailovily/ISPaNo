# ISPaNo

ISPaNo выгружает заявки и историю переписки из IntraService. Приложение поддерживает JSON v2, XLSX-отчёт для недельной работы, Telegram-бота и защищённый web-интерфейс. Все режимы используют общую прикладную логику и одинаковую конфигурацию.

## Быстрый старт

Требуются Python 3.12+ и Poetry 2.4+.

```bash
python setup.py
poetry install
poetry run ispano export
```

`setup.py` создаёт или обновляет `.env` с реквизитами IntraService и, при необходимости, Telegram. Настройку web-интерфейса и AI-суммаризации добавляют вручную в `.env` по [руководству по конфигурации](docs/configuration.md).

## Режимы работы

| Режим | Команда | Результат |
| --- | --- | --- |
| JSON-экспорт | `poetry run ispano export` | Файл JSON v2 в `exports/` и обновлённый `exports/latest.json` |
| JSON с даты | `poetry run ispano export --since "03.09.2026 14:30"` | Экспорт заявок, изменённых после указанной даты |
| XLSX-отчёт | `poetry run ispano tickets 4672` | Таблица `tickets_report_*.xlsx` до номера заявки включительно |
| Telegram | `poetry run ispano bot` | JSON v2 отправляется авторизованному пользователю Telegram |
| Web | `poetry run ispano web` | Защищённая страница для постановки JSON- и XLSX-заданий |

Полные инструкции по запуску, Docker, безопасности и диагностике собраны в [эксплуатационном руководстве](docs/operations.md). Описание обязательных переменных, локальных справочников и AI-провайдеров — в [конфигурации](docs/configuration.md).

## Формат экспорта

JSON v2 — единственный поддерживаемый формат обмена. Его поля, даты и правила обновления `latest.json` описаны в [спецификации JSON v2](docs/json-v2.md). Web viewer умеет открывать локальный JSON v2 прямо в браузере: выбранный файл на сервер не отправляется.

## Docker

Один образ обслуживает bot и web. Выберите нужные Compose profiles:

```bash
docker compose --profile bot up -d --build
docker compose --profile web up -d --build
docker compose --profile bot --profile web up -d --build
```

Web-профиль публикует `${WEB_PORT:-8000}`; bot не открывает портов. Оба сервиса используют `.env`, читают `.local/` и сохраняют артефакты в примонтированный `exports/`.

## Разработка

```bash
poetry check
poetry run python -m unittest discover -s tests
```

Не коммитьте `.env`, `.local/`, `exports/` и реальные выгрузки.

## Документация

- [Конфигурация](docs/configuration.md)
- [Запуск и эксплуатация](docs/operations.md)
- [Формат JSON v2](docs/json-v2.md)
- [Архивный Word-отчёт](docs/archive/README.md)
