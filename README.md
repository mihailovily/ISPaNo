# ISPaNo

ISPaNo выгружает тикеты и историю IntraService. Проект поддерживает три сценария:

- JSON-экспорт через CLI;
- XLSX-выгрузку для недельного отчёта;
- Telegram-бота, который отправляет JSON-файл пользователю.

В состав проекта также входит локальный viewer. Он отображает только канонический
JSON формата v2, созданный CLI-экспортом.

## Структура

```text
ISPaNo/
├── src/ispano/
│   ├── cli.py                 # команды export, tickets и bot
│   ├── settings.py            # конфигурация и валидация
│   ├── export.py              # оркестрация JSON-экспорта
│   ├── serialization.py       # форматы v2/legacy и атомарная запись
│   ├── ticket_report.py       # XLSX для недельного отчёта
│   ├── intraservice/          # HTTP-клиент и парсеры
│   └── telegram/              # приложение, обработчики и прогресс
├── tests/unit/                # unit-тесты
├── web/index.html             # viewer формата v2
├── exports/                   # локальные результаты, исключённые из Git
├── bot.py                     # совместимый запуск команды bot
├── config.py                  # совместимая переходная обёртка
└── intraservice_parser.py     # совместимый интерактивный legacy-запуск
```

Новая бизнес-логика размещается в `src/ispano`. Корневые `bot.py`, `config.py`
и `intraservice_parser.py` сохранены для совместимости; их не следует расширять.

## Требования и быстрый старт

- Python 3.12+
- Poetry 2.4+
- Docker и Docker Compose — только для контейнерного запуска

Для локальной работы необходимо создать `.env` на основе `.env.example` и
заполнить актуальными значениями:

```bash
python setup.py
poetry install
poetry run ispano --help
```

Мастер настройки спрашивает только значения для выбранного сценария и при
повторном запуске позволяет оставить или изменить текущие. Если предпочтительна
ручная настройка, скопируйте `.env.example` в `.env` и отредактируйте файл.

Для JSON-экспорта и XLSX-отчёта необходимы `INTRASERVICE_LOGIN` и
`INTRASERVICE_PASSWORD`. Для Telegram-бота дополнительно требуются
`TELEGRAM_BOT_TOKEN` и непустой `ALLOWED_TELEGRAM_USER_IDS`. Пустой или
некорректный allowlist запрещает запуск бота.

Основные параметры: `INTRASERVICE_BASE_URL`, `REQUEST_DELAY`,
`REQUEST_CONNECT_TIMEOUT`, `REQUEST_READ_TIMEOUT`, `MAX_PAGES_SAFETY`,
`DEFAULT_LOOKBACK_HOURS`, `INTRASERVICE_TIMEZONE` и `OUTPUT_DIR`. Полный
список и значения по умолчанию приведены в `.env.example`.

## CLI

```bash
poetry run ispano export
poetry run ispano export --since "03.09.2026 14:30"
poetry run ispano export --format legacy
poetry run ispano export --output-dir custom-exports
poetry run ispano tickets 4672
poetry run ispano bot
```

Команда `export` по умолчанию выгружает тикеты, изменённые за
`DEFAULT_LOOKBACK_HOURS`. Параметр `--since` принимает дату в формате
`ДД.ММ.ГГГГ`, дату и время в формате `ДД.ММ.ГГГГ ЧЧ:ММ` либо дату в ISO 8601.
Параметр `--output-dir` задаёт каталог JSON-файлов только для текущего запуска
`export`.

По умолчанию JSON-экспорт сохраняется в `<корень проекта>/exports` под именем
`tickets_export_YYYYMMDD_HHMMSS.json`. После успешной выгрузки v2 также
атомарно обновляется `exports/latest.json`; при ошибке экспорта этот файл не
изменяется. Относительный `OUTPUT_DIR` разрешается относительно корня проекта.
Значение `/app/exports`, используемое Docker, при локальном запуске
сопоставляется с `<корень проекта>/exports`.

Совместимые команды остаются доступными:

```bash
poetry run python intraservice_parser.py
poetry run python bot.py
```

`intraservice_parser.py` запускает интерактивный legacy-режим с запросом даты.
Новый CLI использует v2 по умолчанию.

## Форматы JSON

Формат v2 является каноническим:

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

Параметр `--format legacy` сохраняет прежнюю структуру массива
`[{"ticket": ..., "chat": ...}]`. Legacy-файл не заменяет
`exports/latest.json`, поскольку viewer ожидает канонический v2.

## Недельный отчёт по тикетам

Команда `poetry run ispano tickets 4672` создаёт
`exports/tickets_report_YYYYMMDD_HHMMSS.xlsx` с одним листом `Тикеты`, готовым
для переноса в недельный отчёт. В выгрузку входят тикеты от самого свежего до
`4672` включительно.

Команда получает из карточки тикета статус SD, тип ТП, партнёра и последнее
обновление. Для заголовков вида `Запрос обновления <версия> [Заказчик]`
автоматически заполняются «Описание» и «Заказчик». XLSX-выгрузка не изменяет
JSON-экспорт и `exports/latest.json`.

Соответствия полной организации заявителя и значения в колонке «Партнер»
хранятся локально в `.local/partner_aliases.json`. Этот файл не входит в Git и
Docker-образ; путь можно изменить через `PARTNER_ALIASES_PATH`:

```json
{
  "ООО Пример": "Пример"
}
```

При отсутствии организации в алиасах в XLSX записывается исходное значение, а
после выгрузки оно выводится как кандидат на добавление алиаса.

Алиасы типов техподдержки находятся в
`src/ispano/support_type_aliases.json`. Например, запись
`"ТП HSM Стандартная": "Стандартная"` преобразует исходное название типа в
каноническое значение для отчёта.

Алиасы статусов SD находятся в `src/ispano/status_aliases.json`. Они приводят
статусы к допустимым для отчёта значениям: «Приостановлен», «Закрыт», «В
работе», «Ожидается обновление», «Требует уточнения», «Выполняется» и
«Отложен». Неизвестный статус сохраняется в исходном виде.

Список распознаваемых заказчиков хранится локально в
`.local/customer_names.json`; путь можно изменить через `CUSTOMER_NAMES_PATH`.
Сравнение выполняется без учёта регистра, а в XLSX сохраняется написание из
локального списка.

### ИИ-статус в XLSX

Для `ispano tickets` можно настроить OpenAI-совместимый endpoint:

```dotenv
TICKET_SUMMARY_API_BASE_URL=http://localhost:20128/v1
TICKET_SUMMARY_MODEL=имя-модели
TICKET_SUMMARY_API_KEY=  # необязательно для локального endpoint
```

Если заданы URL и модель, перед каждой XLSX-выгрузкой команда спрашивает
`Использовать ИИ для заполнения статусов? [y/N]`. Только `y` отправляет историю
каждого тикета в ИИ и записывает содержательный результат (не более 1000
символов) в «Текущий статус/решение». При трёх неудачных попытках для отдельного тикета
выгрузка продолжается, а его ячейка остаётся пустой.

Для проверки endpoint и имени модели до выгрузки запустите:

```powershell
poetry run python scripts/test_ticket_summary.py
```

Скрипт не печатает API-ключ, проверяет `/models` (если endpoint поддерживает
этот OpenAI-совместимый метод) и затем выполняет тестовый запрос в
`/chat/completions`. Для полного списка моделей добавьте `--list-models`.

## Telegram-бот

Команда `poetry run ispano bot` запускает бота с командами `/start` и
`/export`. Обработка доступна только идентификаторам из
`ALLOWED_TELEGRAM_USER_IDS`. Бот формирует JSON формата v2 в памяти и отправляет
его в Telegram; файлы в `OUTPUT_DIR` и `exports/latest.json` при этом не
создаются.

## Docker

```bash
docker compose up -d --build
docker compose logs -f intraservice-bot
docker compose down
```

Compose запускает Telegram-бота как основной процесс контейнера командой
`poetry run python -m ispano bot`. Секреты передаются из `.env` и не копируются
в образ. `exports/` подключается как доступный для записи volume, а `.local/`
подключается только для чтения.

## Viewer

Для viewer требуется HTTP-сервер, запущенный из корня проекта:

```bash
poetry run python -m http.server 8000
```

После запуска viewer доступен по адресу
[http://localhost:8000/web/](http://localhost:8000/web/). Он загружает
`exports/latest.json`, проверяет `schema_version === 2` и добавляет данные через
DOM API, поэтому содержимое тикетов не интерпретируется как HTML.

## Проверки

```bash
poetry check
poetry run python -m unittest discover -s tests
```

Эти проверки следует выполнять в среде разработки или CI перед публикацией
изменений.

## Безопасность

- Не следует коммитить `.env`, `exports/` и реальные выгрузки.
- Рекомендуется ограничивать `ALLOWED_TELEGRAM_USER_IDS` минимально необходимым
  набором Telegram user ID.
- Viewer следует открывать через HTTP-сервер, а не через `file://`.
- Не следует добавлять реальные выгрузки тикетов в fixtures или Docker-контекст.
