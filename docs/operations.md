# Запуск и эксплуатация ISPaNo

## Локальный запуск

После настройки `.env` и установки зависимостей используйте одну из команд:

```bash
poetry run ispano export
poetry run ispano export --since "03.09.2026 14:30"
poetry run ispano tickets 4672
poetry run ispano bot
poetry run ispano web
```

`--since` принимает `ДД.ММ.ГГГГ`, `ДД.ММ.ГГГГ ЧЧ:ММ` или ISO 8601. Если опция не указана, экспорт берёт `DEFAULT_LOOKBACK_HOURS` в зоне `INTRASERVICE_TIMEZONE`.

Команда `tickets` формирует один XLSX-лист от самого свежего найденного номера заявки до указанного номера включительно. При настроенной AI-суммаризации она задаёт вопрос перед отправкой данных выбранному провайдеру.

## Web-интерфейс

Откройте `http://<WEB_HOST>:<WEB_PORT>/` после запуска `poetry run ispano web`. Вход требует `WEB_USERNAME` и пароль, соответствующий `WEB_PASSWORD_HASH`.

Web-приложение выполняет задания строго по одному. Оно показывает состояние `queued`, `running`, `succeeded` или `failed`, последние 100 строк прогресса и ссылку на скачивание готового файла. Задания и их статусы хранятся только в памяти процесса: после перезапуска незавершённые задания и история очереди исчезают. Готовые файлы остаются в `OUTPUT_DIR` до ручной очистки.

Страница viewer открывает готовый JSON web-задания или выбранный пользователем локальный JSON v2. Локальный файл обрабатывается браузером и не загружается на сервер.

Не публикуйте web-интерфейс в открытом интернете напрямую. Размещайте его за HTTPS reverse proxy, ограничьте сетевой доступ и храните `.env` с правами, доступными только оператору. Встроенная сессия настроена для HTTP-совместимого локального запуска; TLS завершается на reverse proxy.

## Docker Compose

Compose profiles позволяют запускать каждый режим отдельно или вместе:

```bash
docker compose --profile bot up -d --build
docker compose --profile web up -d --build
docker compose --profile bot --profile web up -d --build
```

Для просмотра журналов:

```bash
docker compose logs -f intraservice-bot
docker compose logs -f intraservice-web
```

`intraservice-web` публикует `${WEB_PORT:-8000}`. Оба контейнера получают `.env`, монтируют `.local/` только для чтения и `exports/` для записи. Перед запуском убедитесь, что `WEB_PORT`, `WEB_HOST` и web-секреты заданы для web-профиля, а Telegram-переменные — для bot-профиля.

## Диагностика

| Симптом | Что проверить |
| --- | --- |
| Нет `.env` | Запустите `python setup.py` или скопируйте `.env.example` в `.env` и заполните обязательные поля. |
| Ошибка конфигурации | Сверьте имена переменных и ограничения в [конфигурации](configuration.md). |
| Ошибка авторизации IntraService | URL, логин и пароль; не выводите пароль в логи. |
| Сетевая ошибка или таймаут | Доступность IntraService, прокси и значения `REQUEST_*_TIMEOUT`. |
| Бот не запускается | Токен и список `ALLOWED_TELEGRAM_USER_IDS`; список не может быть пустым. |
| Web не запускается | Bcrypt-хеш, секрет не менее 32 символов и допустимый `WEB_PORT`. |
| Неизвестная организация в XLSX | Добавьте отображаемое имя в `.local/partner_aliases.json`. |
| AI-суммаризация недоступна | Задайте URL и модель; для GigaChat также authorization key. |

Для проверки GigaChat или другого AI-провайдера используйте `scripts/test_ticket_summary.py --list-models`. Не отключайте TLS-проверку GigaChat без необходимости.

## Проверка после изменений

```bash
poetry check
poetry run python -m unittest discover -s tests
node --check web/app.js
node --check web/viewer.js
```

JSON-файлы и отчёты в `exports/` содержат рабочие данные. Не используйте их как тестовые фикстуры и не добавляйте в Git.

