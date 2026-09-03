# IntraService Parse & Notify

Проект предназначен для автоматического экспорта тикетов и истории комментариев из системы Intraservice в JSON, который затем можно передать в AI-агента или использовать в другом обработчике данных.

Скрипт собирает:
- список тикетов из API сервиса;
- карточки тикетов и их изменения;
- комментарии/чат по каждому тикету;
- результат в удобном JSON-формате, готовом к дальнейшей обработке.

## Что делает проект

- логинится в Intraservice автоматически;
- получает тикеты по дате изменения;
- фильтрует заявки после указанной даты отсечки;
- извлекает историю комментариев из HTML-страницы карточки тикета;
- сохраняет результат в файл `tickets_export.json`;
- сортирует итоговый список по идентификатору тикета в порядке убывания;
- поддерживает локальный просмотр через простую HTML-страницу.

## Структура проекта

```text
.
├── parser.py             # основной парсер
├── index.html            # простая визуализация данных
├── tickets_export.json   # результат выгрузки
├── pyproject.toml        # зависимости и конфигурация проекта
├── README.md             # документация
├── task.md               # техническое задание
├── add.md                # дополнения/заметки
├── test.py               # тестовые/экспериментальные скрипты
└── .env                  # локальные учетные данные (не обязательно хранить в git)
```

## Требования

### Для запуска с Docker (рекомендуется)
- Docker и Docker Compose

### Для локальной разработки (без Docker)
- Python 3.12+
- Poetry (для управления зависимостями)

## Установка и конфигурация

### 1. Склонируйте проект

```bash
git clone <repo-url>
cd ISPaNo
```

### 2. Создайте файл конфигурации `.env`

```dotenv
INTRASERVICE_LOGIN=your_login
INTRASERVICE_PASSWORD=your_password
```


## Запуск с Docker (рекомендуется)

### Быстрый старт

```bash
docker compose up -d
```

Это запустит бота в фоновом режиме. Проверьте статус:

```bash
docker compose ps
```

Просмотрите логи:

```bash
docker compose logs -f intraservice-bot
```

### Остановка контейнера

```bash
docker compose down
```

### Пересборка образа (после изменения кода)

```bash
docker compose build --no-cache
docker compose up -d
```

### Экспортированные файлы

Файлы экспорта сохраняются в локальную папку `./exports/` (настроено в `docker-compose.yml`):

```bash
ls -la ./exports/
```

## Локальный запуск (без Docker)

### Для разработки

Установите Poetry и зависимости:

```bash
pip install --upgrade pip poetry
poetry install
```

## Запуск бота

### С Docker Compose

Убедитесь, что в файле `.env` указаны учетные данные:

```bash
docker compose up -d
```

Бот будет автоматически перезапускаться при сбое благодаря политике `restart: unless-stopped`.

### Локально (без Docker)

Активируйте виртуальное окружение и запустите:

```bash
poetry run python bot.py
```

Или если вы работаете в режиме разработки с Poetry:

```bash
poetry install
poetry run python bot.py
```

## Формат выходных данных

Результат представляет собой массив объектов следующего вида:

```json
[
  {
    "ticket": {
      "Id": 4658,
      "Name": "Активности для каманд",
      "Description": "...",
      "Created": "26.08.2026 11:34:13",
      "Changed": "28.08.2026 8:58:32",
      "StatusId": 35,
      "ExecutorIds": "1405, 1655"
    },
    "chat": [
      {
        "author": "Иванов И.",
        "date_raw": "27 августа, 16:25",
        "text": "Текст сообщения"
      }
    ]
  }
]
```

## Просмотр выгрузки в браузере

Для локального просмотра можно открыть `index.html` напрямую в браузере, но удобнее запускать локальный сервер:

```bash
python -m http.server 8000
```

Затем откройте:

```text
http://localhost:8000/
```

Если все корректно, страница загрузит `tickets_export.json` и покажет список тикетов и переписку по ним.

## Развертывание на сервер

### Docker Compose на Ubuntu/Linux (рекомендуется)

Это самый надежный способ для production.

1. **Установите Docker и Docker Compose** (если еще не установлены):

```bash
# Ubuntu/Debian
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh

# Добавьте пользователя в группу docker
sudo usermod -aG docker $USER
newgrp docker

# Установите Docker Compose
sudo curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
sudo chmod +x /usr/local/bin/docker-compose
```

2. **Клонируйте проект на сервер:**

```bash
git clone <repo-url> /opt/intraservice-bot
cd /opt/intraservice-bot
```

3. **Создайте файл конфигурации:**

```bash
cat > .env << EOF
INTRASERVICE_LOGIN=your_login
INTRASERVICE_PASSWORD=your_password
EOF

chmod 600 .env
```

4. **Запустите сервис:**

```bash
docker compose up -d
```

5. **Проверьте статус:**

```bash
docker compose ps
docker compose logs -f intraservice-bot
```

### Запуск бота как systemd сервиса

Для автоматического запуска при перезагрузке сервера создайте файл `/etc/systemd/system/intraservice-bot.service`:

```ini
[Unit]
Description=Intraservice Bot
After=docker.service
Requires=docker.service

[Service]
Type=simple
WorkingDirectory=/opt/intraservice-bot
ExecStart=/usr/local/bin/docker-compose up
ExecStop=/usr/local/bin/docker-compose down
Restart=unless-stopped
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Включите и запустите сервис:

```bash
sudo systemctl daemon-reload
sudo systemctl enable intraservice-bot
sudo systemctl start intraservice-bot
sudo systemctl status intraservice-bot
```

### Мониторинг и логирование

**Просмотр логов:**

```bash
# Последние 100 строк
docker compose logs -f --tail=100

# Логи конкретного сервиса
docker compose logs intraservice-bot
```

**Состояние контейнера:**

```bash
docker compose ps
docker inspect intraservice-bot
```

**Проверка healthcheck:**

```bash
docker compose ps
# Статус должен быть "healthy"
```

### Обновление кода

```bash
cd /opt/intraservice-bot
git pull origin main
docker compose build --no-cache
docker compose up -d
```

## Безопасность

- не храните логин и пароль в git;
- добавьте `.env` в `.gitignore`;
- используйте минимально необходимые права доступа к данным.

## Возможные улучшения

- добавить cron/scheduler для автоматической выгрузки;
- хранить история экспортов по датам;
- сделать REST API для подачи данных в сторонние сервисы;
- добавить логирование и уведомления об ошибках;
- расширить HTML-отчёт красивыми фильтрами и сортировкой.

## Полезные команды

### Docker Compose

```bash
# Запуск в фоновом режиме
docker compose up -d

# Остановка контейнера
docker compose down

# Просмотр логов
docker compose logs -f
docker compose logs --tail=50

# Пересборка образа
docker compose build --no-cache

# Проверка статуса
docker compose ps

# Перезапуск сервиса
docker compose restart
```

### Локальный запуск

```bash
# Запуск бота
poetry run python bot.py

# Проверка версии Python
python --version

# Проверка установленных зависимостей
poetry show
```

### Система

```bash
# Проверка прав доступа к .env
ls -la .env

# Просмотр свежих логов Docker
docker compose logs -f --tail=100

# Очистка неиспользуемых образов Docker
docker image prune -a
```

## Контакты / поддержка

Для работы с проектом лучше хранить секреты в `.env`, а саму выгрузку выполнять в отдельной рабочей среде. При необходимости можно быстро адаптировать парсер под другой API, другой формат фильтрации или другой вывод JSON.

---

Если нужно, я могу сразу сделать ещё одну версию README в более "продакшн"-стиле: краткую, корпоративную, либо с подробным разделом "Deploy to Ubuntu/Nginx" и примерами команд для реального сервера.
