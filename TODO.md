# План полной реструктуризации ISPaNo

## 1. Целевая архитектура

Перевести проект на стандартный `src`-layout и разделить бизнес-логику, внешние интеграции и пользовательские интерфейсы:

```text
ISPaNo/
├── src/
│   └── ispano/
│       ├── __init__.py
│       ├── __main__.py
│       ├── cli.py
│       ├── settings.py
│       ├── models.py
│       ├── export.py
│       ├── serialization.py
│       ├── intraservice/
│       │   ├── __init__.py
│       │   ├── client.py
│       │   └── parsing.py
│       └── telegram/
│           ├── __init__.py
│           ├── app.py
│           ├── handlers.py
│           └── progress.py
├── tests/
│   ├── fixtures/
│   │   ├── task_page.json
│   │   └── ticket_history.html
│   ├── unit/
│   └── integration/
├── web/
│   └── index.html
├── bot.py
├── intraservice_parser.py
├── Dockerfile
├── docker-compose.yml
├── pyproject.toml
├── .env.example
└── README.md
```

Ответственность модулей:

- `settings.py` — чтение и валидация настроек без изменяемых глобальных переменных.
- `models.py` — типизированные внутренние модели тикета, комментария и документа экспорта.
- `intraservice/client.py` — HTTP-сессия, авторизация, пагинация и загрузка карточек.
- `intraservice/parsing.py` — чистые функции разбора дат, API-ответов и HTML.
- `export.py` — orchestration: получить тикеты, загрузить историю, сформировать результат и отправить прогресс.
- `serialization.py` — независимые сериализаторы `v2` и `legacy`.
- `telegram/` — только Telegram-specific код: handlers, проверка доступа и доставка прогресса.
- `cli.py` — единый интерфейс командной строки.
- Корневые `bot.py` и `intraservice_parser.py` — тонкие переходные обёртки без бизнес-логики.

Не создавать универсальные модули `utils.py` или `helpers.py`: каждая функция должна находиться рядом со своей предметной областью.

## 2. Основные изменения

### Конфигурация и зависимости

- Реализовать неизменяемые dataclass-настройки:
  - `IntraserviceSettings`;
  - `TelegramSettings`;
  - `ExportSettings`;
  - `AppSettings`.
- Добавить фабрики `from_env()`, которые не завершают процесс через `sys.exit`.
- Ошибки настроек представлять отдельным `ConfigurationError`; преобразование в exit code выполнять только в CLI или Telegram entry point.
- Валидировать настройки по команде:
  - `ispano export` не требует Telegram-токен и allowlist;
  - `ispano bot` требует токен, непустой allowlist и учётные данные Intraservice.
- Добавить `INTRASERVICE_TIMEZONE`, значение по умолчанию — `Europe/Moscow`.
- Сохранить существующие timeout, delay, output directory и safety limit.
- Исправить устаревшие комментарии, утверждающие, что пустой allowlist открывает доступ всем.

### Клиент Intraservice и парсинг

- Реализовать `IntraserviceClient` как context manager, владеющий `requests.Session`.
- Передавать клиенту base URL, timeout, задержку и предел страниц через конструктор.
- Все GET-параметры пагинации передавать через `params`, закрыв issue 6.
- Централизовать обработку:
  - connect/read timeout;
  - HTTP-ошибок;
  - невалидного JSON;
  - отсутствующей cookie после логина.
- Определить исключения `AuthenticationError`, `IntraserviceTimeoutError`, `IntraserviceResponseError`.
- Вынести HTML-разбор в чистую функцию `parse_ticket_history(html, created_at, upper_bound, now)`.
- Передавать `now` явно или через injectable clock, чтобы определение года комментария тестировалось детерминированно.
- Не импортировать настройки из клиента, парсера или экспортера: все зависимости передавать явно.

### Модели и JSON v2

Канонический формат — v2:

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
      "description": "Описание",
      "creator_id": 123,
      "creator_name": "Иванов И.",
      "created_at": "2026-08-26T11:34:13+03:00",
      "changed_at": "2026-08-28T08:58:32+03:00",
      "closed_at": null,
      "status_id": 35,
      "executor_ids": [1405, 1655],
      "chat": [],
      "raw": {}
    }
  ]
}
```

- Нормализовать основные поля в `snake_case`.
- Преобразовать даты в ISO 8601 с offset из `INTRASERVICE_TIMEZONE`.
- Преобразовать списки ID в массивы целых чисел.
- Хранить полный исходный API-объект в `raw`, чтобы неизвестные поля не терялись.
- Комментарии v2 должны содержать `id`, `occurred_at`, `date_raw`, `author`, `text`, `is_private`, `events`.
- Legacy-сериализатор должен воспроизводить текущий массив `[{ticket, chat}]` без изменения имён и структуры полей.
- Новый CLI и Telegram-бот используют v2 по умолчанию.
- CLI поддерживает `--format legacy`.
- Корневая обёртка `intraservice_parser.py` сохраняет legacy-формат и текущий интерактивный сценарий.

### CLI и экспорт файлов

Добавить entry point:

```toml
[project.scripts]
ispano = "ispano.cli:main"
```

Поддерживаемые команды:

```text
ispano export [--since DATETIME] [--format v2|legacy] [--output-dir PATH]
ispano bot
ispano --help
python -m ispano ...
```

Поведение `ispano export`:

- `--since` принимает `ДД.ММ.ГГГГ`, `ДД.ММ.ГГГГ ЧЧ:ММ` или ISO 8601.
- Без `--since` используется `DEFAULT_LOOKBACK_HOURS`.
- По умолчанию создаётся `exports/tickets_export_YYYYMMDD_HHMMSS.json`.
- После успешной записи атомарно обновляется `exports/latest.json`: временный файл и `Path.replace`.
- При неуспешном экспорте существующий `latest.json` остаётся нетронутым.
- Коды завершения: `0` — успех, `2` — ошибка аргументов/конфигурации, `3` — авторизация, `4` — сеть/API, `5` — запись файла.

Корневые обёртки:

- `bot.py` вызывает `ispano.cli.main(["bot"])`.
- `intraservice_parser.py` вызывает legacy CLI adapter с интерактивным вводом даты и credentials.
- Обёртки не должны содержать парсинг, HTTP-код или Telegram handlers.

### Telegram-слой

- Перенести создание `Application` в `telegram/app.py`, команды — в `handlers.py`, очередь прогресса — в `progress.py`.
- Представить callback прогресса протоколом `ProgressReporter`, чтобы exporter не зависел от Telegram.
- Сохранить очередь с `loop.call_soon_threadsafe`, агрегацию обновлений и ожидание progress-задачи перед финальным сообщением.
- Ограничить длину Telegram-статуса и частоту обновлений.
- Ошибки прогресса только логировать; они не должны отменять экспорт.
- Проверять allowlist до выполнения любой команды, включая `/start`.
- Формировать JSON через общий v2-сериализатор, чтобы CLI и бот выдавали одинаковый контракт.

### Web-viewer и оставшиеся issues

- Переместить viewer в `web/index.html`.
- Загружать `../exports/latest.json`.
- Проверять `schema_version === 2`; при несовпадении показывать понятную ошибку.
- Сохранить текущий внешний вид и поведение раскрывающихся карточек.
- Устранить issue 3:
  - не вставлять данные тикетов через `innerHTML`;
  - создавать элементы через DOM API;
  - пользовательские значения назначать только через `textContent`;
  - обработчики назначать через `addEventListener`;
  - статические сообщения также формировать DOM API.
- Запуск viewer документировать как `python -m http.server` из корня с переходом на `/web/`.
- Не копировать `exports/` и реальные выгрузки в Docker-образ.

### Packaging, Docker и документация

- Настроить Poetry на пакет из `src/ispano`.
- Добавить dev-зависимости `pytest`, `pytest-asyncio`, `ruff` и `mypy`.
- Настроить `ruff`, строгую проверку новых типов и pytest в `pyproject.toml`.
- В Docker сначала устанавливать зависимости для кеширования, затем копировать `src/` и устанавливать сам пакет.
- Заменить контейнерный CMD на `["ispano", "bot"]`.
- Оставить `Dockerfile` и `docker-compose.yml` в корне, сохранив стандартную команду `docker compose up`.
- Полностью актуализировать README:
  - реальная структура проекта;
  - все обязательные переменные;
  - новые и legacy-команды;
  - форматы v2/legacy;
  - расположение экспортов и viewer;
  - корректный systemd unit типа `oneshot` с `RemainAfterExit=yes`, без недопустимого `Restart=unless-stopped`.
- Удалить устаревшие `featuresToImplement.md` или перенести актуальные идеи в раздел roadmap README; не переносить старый черновик без ревизии.

## 3. Порядок внедрения

1. Зафиксировать текущее поведение characterization-тестами для дат, HTML, JSON legacy и пагинации.
2. Создать `src/ispano`, модели исключений и settings dataclasses.
3. Вынести чистые функции дат и HTML-парсинга без изменения результатов.
4. Реализовать `IntraserviceClient`, исправить query-параметры и централизовать сетевые ошибки.
5. Реализовать `TicketExporter` с внедряемым progress callback.
6. Добавить сериализаторы v2/legacy и атомарную запись `latest.json`.
7. Реализовать единый CLI и временные корневые обёртки.
8. Перенести Telegram-код и подключить общий exporter/serializer.
9. Перенести viewer, адаптировать к v2 и закрыть XSS.
10. Обновить Poetry, Docker, `.env.example`, ignore-файлы и README.
11. Запустить полный набор проверок и только после этого удалить дублированную реализацию из старых файлов.

Каждый этап должен оставлять импортируемый и тестируемый проект; перенос логики выполняется после появления тестов соответствующего компонента.

## 4. Тестовый план и критерии готовности

- Unit-тесты настроек: defaults, timezone, неверные числа, пустой token и некорректный allowlist.
- Тесты дат: оба пользовательских формата, ISO, leap year, неизвестный месяц, переход года и timezone offset.
- HTML fixtures: пустая история, обычные/приватные комментарии, события, даты с годом и без года, повреждённая разметка.
- HTTP-тесты с mock session:
  - login cookie;
  - GET-параметры находятся в query;
  - cutoff, пустая страница, повтор первой записи и safety limit;
  - timeout и HTTP error каждого endpoint.
- Тесты экспортера: порядок тикетов, progress events, пропуск допустимых ошибок и остановка при timeout.
- Snapshot-тесты legacy JSON и v2 JSON, включая сохранение всех полей в `raw`.
- Тесты записи: timestamp-файл, атомарный `latest.json`, отсутствие обновления latest при ошибке.
- Async-тесты Telegram progress queue, allowlist и обработки ошибок exporter.
- Проверка viewer на синтетическом JSON с HTML/`script` payload: содержимое отображается как текст и не выполняется.
- Команды приёмки:
  - `poetry check`;
  - `poetry run ruff check .`;
  - `poetry run mypy src`;
  - `poetry run pytest`;
  - `docker compose build`;
  - smoke test `ispano --help`, `ispano export`, `ispano bot`.
- Готовность означает отсутствие бизнес-логики в корневых обёртках, прохождение тестов и совпадение legacy snapshot с текущим экспортом.

## 5. Принятые допущения

- Python остаётся версии 3.12+, HTTP-клиент остаётся синхронным `requests`; Telegram запускает exporter вне event loop.
- V2 становится форматом по умолчанию; legacy сохраняется только как миграционный режим.
- Временная зона по умолчанию — `Europe/Moscow`, но переопределяется окружением.
- Реальные `tickets_export*.json` не используются как тестовые fixtures и не добавляются в репозиторий.
