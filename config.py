"""
Конфигурация сервиса.

Все "магические" константы и секреты, которые раньше были прямо в коде
парсера, теперь читаются из переменных окружения. Если рядом со скриптом
лежит файл .env и установлен python-dotenv - он подхватится автоматически
(это удобно локально). В Docker-контейнере переменные обычно приходят
через env_file / environment в docker-compose.yml - тогда .env читать
не обязательно, но не мешает.
"""

import os
import sys

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    # python-dotenv не установлен - просто работаем с тем, что уже есть
    # в окружении (так и должно быть внутри Docker-контейнера).
    pass


def _get_optional(name: str, default: str) -> str:
    return os.environ.get(name, default)


def _get_required(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        sys.exit(
            f"Не задана обязательная переменная окружения {name}.\n"
            f"Скопируй .env.example в .env и заполни его, "
            f"либо задай {name} в окружении контейнера."
        )
    return value


# --------------------------- Intraservice ---------------------------

BASE_URL = _get_optional("INTRASERVICE_BASE_URL", "https://sd.specint.ru")

# Логин/пароль для CLI-режима можно не задавать заранее - скрипт спросит
# их в консоли. Для бота (не-интерактивный режим) они обязательны -
# это проверяется в intraservice_parser.get_credential().
INTRASERVICE_LOGIN = os.environ.get("INTRASERVICE_LOGIN")
INTRASERVICE_PASSWORD = os.environ.get("INTRASERVICE_PASSWORD")

# --------------------------- Telegram-бот ---------------------------

# Токен проверяется только при запуске bot.py. Это позволяет использовать
# CLI-парсер без настройки Telegram.
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")


def require_telegram_bot_token() -> str:
    """Вернуть токен Telegram или завершить запуск с понятной ошибкой."""
    return _get_required("TELEGRAM_BOT_TOKEN")

# Кому разрешено пользоваться ботом. В .env через запятую:
#   ALLOWED_TELEGRAM_USER_IDS=123456789,987654321
# Если оставить пустым - бот будет отвечать любому пользователю
# Telegram, который его найдёт (не рекомендуется для продакшена,
# т.к. в боте лежит доступ к учётке в Intraservice).
_allowed_raw = _get_optional("ALLOWED_TELEGRAM_USER_IDS", "")
ALLOWED_TELEGRAM_USER_IDS: frozenset[int] = frozenset()


def require_allowed_telegram_user_ids() -> frozenset[int]:
    """Validate and return a non-empty Telegram user allowlist."""
    raw = _allowed_raw.strip()
    if not raw:
        sys.exit(
            "ALLOWED_TELEGRAM_USER_IDS is not set. Startup aborted: "
            "provide at least one positive Telegram user ID."
        )

    invalid_ids = []
    allowed_ids = set()
    for raw_id in raw.split(","):
        user_id = raw_id.strip()
        if not user_id or not user_id.isascii() or not user_id.isdigit() or int(user_id) <= 0:
            invalid_ids.append(user_id or "<empty value>")
            continue
        allowed_ids.add(int(user_id))

    if invalid_ids or not allowed_ids:
        invalid = ", ".join(repr(value) for value in invalid_ids)
        sys.exit(
            "Invalid ALLOWED_TELEGRAM_USER_IDS. "
            f"All values must be positive integer IDs; invalid values: {invalid}."
        )

    global ALLOWED_TELEGRAM_USER_IDS
    ALLOWED_TELEGRAM_USER_IDS = frozenset(allowed_ids)
    return ALLOWED_TELEGRAM_USER_IDS

# --------------------------- Параметры парсера ---------------------------

REQUEST_DELAY = float(_get_optional("REQUEST_DELAY", "0.4"))
REQUEST_CONNECT_TIMEOUT = float(_get_optional("REQUEST_CONNECT_TIMEOUT", "10"))
REQUEST_READ_TIMEOUT = float(_get_optional("REQUEST_READ_TIMEOUT", "30"))
REQUEST_TIMEOUT: tuple[float, float] = (REQUEST_CONNECT_TIMEOUT, REQUEST_READ_TIMEOUT)
MAX_PAGES_SAFETY = int(_get_optional("MAX_PAGES_SAFETY", "20"))

# Если в команде /export не указана дата - берём тикеты, изменённые
# за последние N часов.
DEFAULT_LOOKBACK_HOURS = int(_get_optional("DEFAULT_LOOKBACK_HOURS", "24"))

# Куда класть JSON-файлы экспорта (и локально, и это же будет volume
# в docker-compose.yml, чтобы файлы не терялись при пересоздании контейнера).
OUTPUT_DIR = _get_optional("OUTPUT_DIR", "exports")
