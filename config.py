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

TELEGRAM_BOT_TOKEN = _get_required("TELEGRAM_BOT_TOKEN")

# Кому разрешено пользоваться ботом. В .env через запятую:
#   ALLOWED_TELEGRAM_USER_IDS=123456789,987654321
# Если оставить пустым - бот будет отвечать любому пользователю
# Telegram, который его найдёт (не рекомендуется для продакшена,
# т.к. в боте лежит доступ к учётке в Intraservice).
_allowed_raw = _get_optional("ALLOWED_TELEGRAM_USER_IDS", "")
ALLOWED_TELEGRAM_USER_IDS = {
    int(x) for x in _allowed_raw.split(",") if x.strip().isdigit()
}

# --------------------------- Параметры парсера ---------------------------

REQUEST_DELAY = float(_get_optional("REQUEST_DELAY", "0.4"))
MAX_PAGES_SAFETY = int(_get_optional("MAX_PAGES_SAFETY", "20"))

# Если в команде /export не указана дата - берём тикеты, изменённые
# за последние N часов.
DEFAULT_LOOKBACK_HOURS = int(_get_optional("DEFAULT_LOOKBACK_HOURS", "24"))

# Куда класть JSON-файлы экспорта (и локально, и это же будет volume
# в docker-compose.yml, чтобы файлы не терялись при пересоздании контейнера).
OUTPUT_DIR = _get_optional("OUTPUT_DIR", "exports")
