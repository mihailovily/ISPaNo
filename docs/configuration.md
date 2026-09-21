# Конфигурация ISPaNo

ISPaNo читает переменные из `.env` в корне проекта. Создайте файл из `.env.example` или запустите `python setup.py` до установки Poetry. Не добавляйте `.env` в Git и не передавайте его содержимое в тикетах, чатах или логах.

## IntraService и экспорт

Эти значения нужны командам `export`, `tickets`, `bot` и web-заданиям.

| Переменная | Обязательна | Значение по умолчанию | Назначение |
| --- | --- | --- | --- |
| `INTRASERVICE_BASE_URL` | нет | `https://sd.specint.ru` | Базовый URL IntraService без завершающего `/` |
| `INTRASERVICE_LOGIN` | да | — | Логин IntraService |
| `INTRASERVICE_PASSWORD` | да | — | Пароль IntraService |
| `REQUEST_DELAY` | нет | `0.4` | Пауза между запросами в секундах; положительное число |
| `REQUEST_CONNECT_TIMEOUT` | нет | `10` | Таймаут подключения в секундах; положительное число |
| `REQUEST_READ_TIMEOUT` | нет | `30` | Таймаут чтения ответа в секундах; положительное число |
| `MAX_PAGES_SAFETY` | нет | `20` | Предельное число страниц пагинации; положительное целое |
| `DEFAULT_LOOKBACK_HOURS` | нет | `24` | Глубина поиска для `export` без `--since`; положительное целое |
| `INTRASERVICE_TIMEZONE` | нет | `Europe/Moscow` | IANA-идентификатор временной зоны источника |
| `OUTPUT_DIR` | нет | `exports` | Каталог готовых JSON и XLSX; относительный путь считается от корня проекта |

В Docker Compose `OUTPUT_DIR=/app/exports` автоматически сопоставляется с каталогом `exports/` репозитория. На Windows не указывайте вручную контейнерный путь для локального запуска.

## Telegram

Требуется только для `poetry run ispano bot`.

| Переменная | Обязательна | Назначение |
| --- | --- | --- |
| `TELEGRAM_BOT_TOKEN` | да | Токен бота из BotFather |
| `ALLOWED_TELEGRAM_USER_IDS` | да | Один или несколько положительных числовых user ID через запятую |

Пустой, отрицательный или некорректный список запрещает запуск бота. Команда формирует JSON в памяти и не оставляет экспорт в `OUTPUT_DIR`.

## XLSX и локальные справочники

`tickets` использует файлы, которые намеренно не входят в репозиторий и Docker-образ:

| Переменная | Путь по умолчанию | Формат |
| --- | --- | --- |
| `PARTNER_ALIASES_PATH` | `.local/partner_aliases.json` | JSON-объект: исходное название организации → отображаемое имя партнёра |
| `CUSTOMER_NAMES_PATH` | `.local/customer_names.json` | JSON-массив допустимых имён заказчиков |

Пример `partner_aliases.json`:

```json
{
  "ООО Пример": "Партнёр Пример"
}
```

Пример `customer_names.json`:

```json
["Заказчик Пример", "Другой заказчик"]
```

Файлы `src/ispano/support_type_aliases.json` и `src/ispano/status_aliases.json` поставляются с приложением; для них отдельных переменных нет.

## AI-суммаризация для XLSX

Суммаризация предлагается интерактивно при запуске `tickets`, только если заданы и `TICKET_SUMMARY_API_BASE_URL`, и `TICKET_SUMMARY_MODEL`.

Для OpenAI-совместимого сервиса используйте значения по умолчанию:

```dotenv
TICKET_SUMMARY_PROVIDER=generic
TICKET_SUMMARY_API_BASE_URL=https://example.internal/v1
TICKET_SUMMARY_MODEL=your-model
TICKET_SUMMARY_API_KEY=
```

`TICKET_SUMMARY_API_KEY` необязателен; при наличии он отправляется как Bearer-токен.

Для GigaChat укажите authorization key из личного кабинета, а не временный OAuth access token:

```dotenv
TICKET_SUMMARY_PROVIDER=gigachat
TICKET_SUMMARY_API_BASE_URL=https://api.giga.chat/v1
TICKET_SUMMARY_MODEL=GigaChat
TICKET_SUMMARY_GIGACHAT_AUTHORIZATION_KEY=...
TICKET_SUMMARY_GIGACHAT_SCOPE=GIGACHAT_API_PERS
TICKET_SUMMARY_GIGACHAT_VERIFY_SSL=true
```

По умолчанию OAuth-запрос выполняется на `https://ngw.devices.sberbank.ru:9443/api/v2/oauth`. Для ИП и юридических лиц замените `TICKET_SUMMARY_GIGACHAT_SCOPE` на значение, выданное GigaChat. `TICKET_SUMMARY_GIGACHAT_VERIFY_SSL=false` отключает TLS-проверку только для OAuth и API-запросов GigaChat; используйте это лишь как временную меру, если доверенный сертификат невозможно установить в ОС или контейнере.

Проверить подключение и список моделей можно командой:

```bash
poetry run python scripts/test_ticket_summary.py --list-models
```

## Web-интерфейс

Эти переменные обязательны только для `poetry run ispano web`:

| Переменная | Назначение |
| --- | --- |
| `WEB_USERNAME` | Единственный логин администратора |
| `WEB_PASSWORD_HASH` | Корректный bcrypt-хеш пароля |
| `WEB_SESSION_SECRET` | Случайная строка длиной не менее 32 символов |
| `WEB_HOST` | Адрес прослушивания, по умолчанию `0.0.0.0` |
| `WEB_PORT` | Порт от 1 до 65535, по умолчанию `8000` |

Сгенерировать bcrypt-хеш можно так:

```bash
poetry run python -c "import bcrypt,getpass; print(bcrypt.hashpw(getpass.getpass().encode(), bcrypt.gensalt()).decode())"
```

Секрет сессии можно получить так:

```bash
poetry run python -c "import secrets; print(secrets.token_urlsafe(48))"
```

О требованиях к публикации web-интерфейса читайте в [эксплуатационном руководстве](operations.md).

