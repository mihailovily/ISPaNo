FROM python:3.12-slim

# Логи Python сразу летят в stdout, без буферизации - удобно смотреть
# через `docker compose logs -f`.
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app/src \
    POETRY_VIRTUALENVS_CREATE=false \
    POETRY_NO_INTERACTION=1 \
    POETRY_VERSION=2.4.1

WORKDIR /app

# Устанавливаем Poetry и только затем зависимости из pyproject.toml/poetry.lock.
RUN pip install --no-cache-dir "poetry==$POETRY_VERSION"

COPY pyproject.toml poetry.lock* ./
RUN poetry install --only main --no-root --no-interaction --no-ansi

COPY . .

# Директория для экспортов (используется CLI-режимом; бот шлёт файл
# прямо в Telegram, на диск ничего не пишет). Совпадает с OUTPUT_DIR
# по умолчанию в src/ispano/settings.py и с volume в docker-compose.yml.
RUN mkdir -p /app/exports

CMD ["poetry", "run", "python", "-m", "ispano", "bot"]
