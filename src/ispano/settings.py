"""Application configuration loaded from environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from dotenv import load_dotenv

load_dotenv()


class ConfigurationError(ValueError):
    """Raised when environment configuration is missing or invalid."""


def _env(name: str, default: str | None = None) -> str | None:
    value = os.getenv(name)
    return default if value is None else value


def _required(name: str) -> str:
    value = _env(name, "")
    if not value or not value.strip():
        raise ConfigurationError(f"Не задана обязательная переменная окружения {name}.")
    return value.strip()


def _positive_float(name: str, default: float) -> float:
    raw = _env(name, str(default))
    try:
        value = float(raw or "")
    except ValueError as exc:
        raise ConfigurationError(f"{name} должно быть положительным числом.") from exc
    if value <= 0:
        raise ConfigurationError(f"{name} должно быть положительным числом.")
    return value


def _positive_int(name: str, default: int) -> int:
    raw = _env(name, str(default))
    try:
        value = int(raw or "")
    except ValueError as exc:
        raise ConfigurationError(f"{name} должно быть положительным целым числом.") from exc
    if value <= 0:
        raise ConfigurationError(f"{name} должно быть положительным целым числом.")
    return value


def _allowlist() -> frozenset[int]:
    raw = (_env("ALLOWED_TELEGRAM_USER_IDS", "") or "").strip()
    if not raw:
        raise ConfigurationError(
            "ALLOWED_TELEGRAM_USER_IDS не задан. "
            "Для запуска бота укажи хотя бы один положительный Telegram user ID."
        )

    values: set[int] = set()
    invalid: list[str] = []
    for item in raw.split(","):
        item = item.strip()
        if not item.isascii() or not item.isdigit() or int(item) <= 0:
            invalid.append(item or "<пустое значение>")
        else:
            values.add(int(item))
    if invalid or not values:
        raise ConfigurationError(
            "Некорректный ALLOWED_TELEGRAM_USER_IDS: " + ", ".join(repr(x) for x in invalid)
        )
    return frozenset(values)


@dataclass(frozen=True, slots=True)
class IntraserviceSettings:
    """Settings required to access IntraService."""

    base_url: str
    login: str | None
    password: str | None
    request_delay: float
    request_timeout: tuple[float, float]
    max_pages: int

    @classmethod
    def from_env(cls) -> "IntraserviceSettings":
        base_url = (_env("INTRASERVICE_BASE_URL", "https://sd.specint.ru") or "").rstrip("/")
        if not base_url:
            raise ConfigurationError("INTRASERVICE_BASE_URL не может быть пустым.")
        return cls(
            base_url=base_url,
            login=_env("INTRASERVICE_LOGIN") or None,
            password=_env("INTRASERVICE_PASSWORD") or None,
            request_delay=_positive_float("REQUEST_DELAY", 0.4),
            request_timeout=(
                _positive_float("REQUEST_CONNECT_TIMEOUT", 10),
                _positive_float("REQUEST_READ_TIMEOUT", 30),
            ),
            max_pages=_positive_int("MAX_PAGES_SAFETY", 20),
        )

    def require_credentials(self) -> tuple[str, str]:
        if not self.login or not self.password:
            raise ConfigurationError(
                "Для экспорта нужны INTRASERVICE_LOGIN и INTRASERVICE_PASSWORD."
            )
        return self.login, self.password


@dataclass(frozen=True, slots=True)
class TelegramSettings:
    """Settings required by the Telegram adapter."""

    bot_token: str
    allowed_user_ids: frozenset[int]

    @classmethod
    def from_env(cls) -> "TelegramSettings":
        return cls(bot_token=_required("TELEGRAM_BOT_TOKEN"), allowed_user_ids=_allowlist())


@dataclass(frozen=True, slots=True)
class ExportSettings:
    """Export defaults shared by CLI, bot and the viewer."""

    output_dir: Path
    default_lookback_hours: int
    timezone: str

    @classmethod
    def from_env(cls) -> "ExportSettings":
        timezone = _env("INTRASERVICE_TIMEZONE", "Europe/Moscow") or "Europe/Moscow"
        try:
            ZoneInfo(timezone)
        except ZoneInfoNotFoundError as exc:
            raise ConfigurationError(f"Неизвестная временная зона INTRASERVICE_TIMEZONE: {timezone}") from exc
        return cls(
            output_dir=Path(_env("OUTPUT_DIR", "exports") or "exports"),
            default_lookback_hours=_positive_int("DEFAULT_LOOKBACK_HOURS", 24),
            timezone=timezone,
        )


@dataclass(frozen=True, slots=True)
class AppSettings:
    """All settings. Telegram configuration is loaded only when requested."""

    intraservice: IntraserviceSettings
    export: ExportSettings
    telegram: TelegramSettings | None = None

    @classmethod
    def from_env(cls, *, include_telegram: bool = False) -> "AppSettings":
        return cls(
            intraservice=IntraserviceSettings.from_env(),
            export=ExportSettings.from_env(),
            telegram=TelegramSettings.from_env() if include_telegram else None,
        )

    def require_telegram(self) -> TelegramSettings:
        return self.telegram or TelegramSettings.from_env()
