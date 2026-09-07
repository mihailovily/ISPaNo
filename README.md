# ISPaNo

Сервис для выгрузки тикетов и истории IntraService в JSON. Проект предоставляет CLI, Telegram-бота и локальный безопасный viewer.

## Структура

```text
ISPaNo/
├── src/ispano/
│   ├── cli.py                 # команды export, tickets и bot
│   ├── settings.py            # конфигурация и валидация
│   ├── models.py              # доменные модели
│   ├── export.py              # orchestration выгрузки
│   ├── serialization.py       # форматы v2/legacy и атомарная запись
│   ├── intraservice/          # HTTP-клиент и чистые парсеры
│   └── telegram/              # handlers, приложение и прогресс
├── tests/unit/                # тесты дат, HTML и сериализации
├── web/index.html             # viewer формата v2
├── exports/                   # локальные результаты, не попадают в git
├── bot.py                     # совместимый запуск старой команды
└── intraservice_parser.py     # совместимый интерактивный legacy-запуск
```

Корневые Python-файлы оставлены только как переходные точки. Новую логику следует добавлять в `src/ispano`.

## Требования и конфигурация

- Python 3.12+
- Poetry 2.4+
- Docker и Docker Compose — для контейнерного запуска

Создай конфигурацию:

```bash
cp .env.example .env
```

Для бота обязательны `INTRASERVICE_LOGIN`, `INTRASERVICE_PASSWORD`, `TELEGRAM_BOT_TOKEN` и непустой `ALLOWED_TELEGRAM_USER_IDS`. Пустой или ошибочный allowlist запрещает запуск.

Основные параметры: `INTRASERVICE_BASE_URL`, `REQUEST_DELAY`, `REQUEST_CONNECT_TIMEOUT`, `REQUEST_READ_TIMEOUT`, `MAX_PAGES_SAFETY`, `DEFAULT_LOOKBACK_HOURS`, `INTRASERVICE_TIMEZONE` и `OUTPUT_DIR`. Полный список находится в `.env.example`.

## Локальный запуск

```bash
poetry install
poetry run ispano --help
poetry run ispano export
poetry run ispano export --since "03.09.2026 14:30"
poetry run ispano export --format legacy
poetry run ispano tickets 4672
poetry run ispano bot
```

По умолчанию экспорт записывается в папку `exports` внутри корня проекта:
`exports/tickets_export_YYYYMMDD_HHMMSS.json`, а после успешной записи — в
`exports/latest.json`. Относительный `OUTPUT_DIR` также разрешается от корня
проекта. Значение `/app/exports` используется Docker и при локальном запуске
автоматически сопоставляется с `<корень проекта>/exports`.
`latest.json` обновляется атомарно и не изменяется при ошибке экспорта.

Старые команды остаются рабочими:

```bash
poetry run python intraservice_parser.py
poetry run python bot.py
```

Первый запуск — интерактивный legacy-режим с запросом даты; новый CLI использует формат v2 по умолчанию.

## Docker

```bash
docker compose up -d --build
docker compose logs -f intraservice-bot
docker compose down
```

Контейнер запускает `python -m ispano bot`. Каталог `exports/` подключён как volume; секреты передаются через `.env` и не копируются в образ.

## Форматы JSON

Формат v2 — канонический:

```json
{
  "schema_version": 2,
  "exported_at": "2026-09-03T15:30:00+03:00",
  "cutoff": "2026-09-02T15:30:00+03:00",
  "source_timezone": "Europe/Moscow",
  "tickets": [
    {
      "id": 4658,
      "name": "Название",
      "created_at": "2026-08-26T11:34:13+03:00",
      "changed_at": "2026-08-28T08:58:32+03:00",
      "executor_ids": [1405, 1655],
      "chat": [],
      "raw": {}
    }
  ]
}
```

`--format legacy` сохраняет прежнюю структуру массива `[{"ticket": ..., "chat": ...}]`.
Legacy-файл не заменяет `exports/latest.json`, потому что viewer ожидает канонический v2.

## Недельный отчёт по тикетам

Команда ниже создаёт `exports/tickets_report_YYYYMMDD_HHMMSS.xlsx` с одним листом
`Тикеты`, который можно копировать в недельный отчёт:

```bash
poetry run ispano tickets 4672
```

В выгрузку входят тикеты от самого свежего до `4672` включительно. Команда получает
статус SD, тип ТП, партнёра и последнее обновление из карточки тикета. Для заголовков
вида `Запрос обновления <версия> [Заказчик]` автоматически заполняются «Описание» и
«Заказчик». JSON-экспорт и `exports/latest.json` команда не изменяет.

Соответствия полной организации заявителя и значения в колонке «Партнер» хранятся
локально в `.local/partner_aliases.json`. Файл не входит в Git и Docker-образ.
Путь можно изменить через `PARTNER_ALIASES_PATH`. Формат пар:

```json
{
  "ООО Пример": "Пример"
}
```

Если организация не найдена в алиасах, она записывается в XLSX в исходном виде и
печатается после выгрузки как кандидат на добавление алиаса.

Алиасы типов техподдержки находятся в `src/ispano/support_type_aliases.json`.
Например, запись `"ТП HSM Стандартная": "Стандартная"` преобразует исходное
название типа в каноническое значение для отчёта.

Список распознаваемых заказчиков хранится локально в `.local/customer_names.json`.
Путь можно изменить через `CUSTOMER_NAMES_PATH`. Сравнение выполняется без учёта
регистра; в XLSX записывается написание из локального списка.

## Viewer

Запусти HTTP-сервер из корня проекта:

```bash
poetry run python -m http.server 8000
```

Открой [http://localhost:8000/web/](http://localhost:8000/web/). Viewer загружает `exports/latest.json`, проверяет `schema_version === 2` и вставляет данные через DOM API, поэтому содержимое тикетов не интерпретируется как HTML.

## Проверки

```bash
poetry check
poetry run python -m unittest discover -s tests
```

Эти команды должны выполняться в среде разработки или CI перед публикацией изменений.

## Безопасность

- не коммить `.env`, `exports/` и реальные выгрузки;
- используй минимальный allowlist Telegram user ID;
- не открывай viewer через `file://`: используй HTTP-сервер;
- не добавляй реальные ticket exports в fixtures или Docker-контекст.
