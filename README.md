# ISPaNo

ISPaNo получает тикеты и историю IntraService. Поддерживаются три интерфейса с общей прикладной логикой:

- JSON v2-экспорт через CLI или защищённый web-интерфейс;
- XLSX для недельного отчёта;
- Telegram-бот, отправляющий JSON v2.

## Установка

Требуются Python 3.12+ и Poetry 2.4+. Скопируйте `.env.example` в `.env`, заполните учётные данные IntraService и установите зависимости:

```bash
poetry install
poetry run ispano --help
```

Для JSON/XLSX нужны `INTRASERVICE_LOGIN` и `INTRASERVICE_PASSWORD`. Для Telegram также укажите `TELEGRAM_BOT_TOKEN` и непустой `ALLOWED_TELEGRAM_USER_IDS`.

## CLI и Telegram

```bash
poetry run ispano export
poetry run ispano export --since "03.09.2026 14:30"
poetry run ispano tickets 4672
poetry run ispano bot
```

`export` записывает только канонический JSON v2 в `exports/` и атомарно обновляет `exports/latest.json`. `tickets` создаёт XLSX от самого свежего номера заявки до указанного включительно. Если настроены `TICKET_SUMMARY_API_BASE_URL` и `TICKET_SUMMARY_MODEL`, CLI предложит включить ИИ-суммаризацию.

## ИИ-суммаризация и GigaChat

По умолчанию `TICKET_SUMMARY_PROVIDER=generic`: приложение вызывает OpenAI-совместимый endpoint и при необходимости передаёт `TICKET_SUMMARY_API_KEY` как Bearer-токен.

Для GigaChat настройте в `.env` authorization key из личного кабинета (не OAuth access token):

```dotenv
TICKET_SUMMARY_PROVIDER=gigachat
TICKET_SUMMARY_API_BASE_URL=https://api.giga.chat/v1
TICKET_SUMMARY_MODEL=GigaChat
TICKET_SUMMARY_GIGACHAT_AUTHORIZATION_KEY=ваш_authorization_key
TICKET_SUMMARY_GIGACHAT_SCOPE=GIGACHAT_API_PERS
TICKET_SUMMARY_GIGACHAT_VERIFY_SSL=true
```

Приложение само получает и обновляет OAuth-токен, срок действия которого ограничен. Для ИП и юридических лиц замените scope на выданное GigaChat значение. Если в системе или Docker-контейнере не установлен сертификат Минцифры, можно временно установить `TICKET_SUMMARY_GIGACHAT_VERIFY_SSL=false`. Это снижает защищённость TLS-соединения и действует только на OAuth и API-запросы GigaChat; предпочтительно установить доверенный сертификат в ОС или контейнере.

Проверить конфигурацию и доступные модели можно командой:

```bash
poetry run python scripts/test_ticket_summary.py --list-models
```

Telegram-бот доступен только ID из allowlist. Он формирует JSON в памяти и не пишет экспорт на диск.

## Веб-интерфейс

В `.env` для web-режима задайте одного администратора:

```dotenv
WEB_USERNAME=admin
WEB_PASSWORD_HASH=$2b$...
WEB_SESSION_SECRET=не_менее_32_случайных_символов
WEB_HOST=0.0.0.0
WEB_PORT=8000
```

Сгенерировать хеш можно так:

```bash
poetry run python -c "import bcrypt,getpass; print(bcrypt.hashpw(getpass.getpass().encode(), bcrypt.gensalt()).decode())"
```

Запуск `poetry run ispano web` открывает защищённый интерфейс. Он ставит JSON-экспорт и XLSX-отчёт в последовательную очередь, показывает прогресс, позволяет скачать готовый файл и просмотреть диалоги. В viewer можно выбрать локальный JSON v2: файл остаётся в браузере и не отправляется на сервер.

Готовые web-артефакты остаются в `exports/` до ручной очистки. Состояния заданий намеренно хранятся только в памяти процесса: после перезапуска незавершённые задания отменяются.

## Docker

Один образ содержит оба режима. Compose profiles выбирают сервисы:

```bash
docker compose --profile bot up -d --build
docker compose --profile web up -d --build
docker compose --profile bot --profile web up -d --build
```

Web-профиль публикует `${WEB_PORT:-8000}`, bot портов не открывает. Оба используют `.env`, читают `.local/` и сохраняют результаты в примонтированный `exports/`.

## Разработка

```bash
poetry check
poetry run python -m unittest discover -s tests
```

Не коммитьте `.env`, `.local/`, `exports/` и реальные выгрузки. JSON v2 — единственный поддерживаемый формат; старые launcher-скрипты и legacy JSON удалены.
