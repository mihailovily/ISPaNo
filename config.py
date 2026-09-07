"""Compatibility facade for code that used the old root-level config module."""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent / "src"))

from ispano.settings import AppSettings  # noqa: E402

_settings = AppSettings.from_env()
BASE_URL = _settings.intraservice.base_url
INTRASERVICE_LOGIN = _settings.intraservice.login
INTRASERVICE_PASSWORD = _settings.intraservice.password
REQUEST_DELAY = _settings.intraservice.request_delay
REQUEST_TIMEOUT = _settings.intraservice.request_timeout
MAX_PAGES_SAFETY = _settings.intraservice.max_pages
DEFAULT_LOOKBACK_HOURS = _settings.export.default_lookback_hours
OUTPUT_DIR = str(_settings.export.output_dir)


def require_telegram_bot_token() -> str:
    return AppSettings.from_env(include_telegram=True).require_telegram().bot_token


def require_allowed_telegram_user_ids() -> frozenset[int]:
    return AppSettings.from_env(include_telegram=True).require_telegram().allowed_user_ids
