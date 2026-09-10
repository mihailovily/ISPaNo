"""Application configuration loaded from environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from dotenv import load_dotenv

load_dotenv()

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONTAINER_OUTPUT_DIR = "/app/exports"


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


def resolve_output_dir(value: str | os.PathLike[str] | None) -> Path:
    """Resolve export paths relative to the project and normalize Docker's path.

    ``/app/exports`` is the container path used by Docker Compose. When the
    same .env file is used on Windows, pathlib would otherwise turn it into
    ``C:\\app\\exports`` outside the repository.
    """
    raw_value = str(value or "exports").strip() or "exports"
    normalized = raw_value.replace("\\", "/").rstrip("/")
    if normalized == CONTAINER_OUTPUT_DIR:
        return PROJECT_ROOT / "exports"

    output_dir = Path(raw_value)
    return output_dir if output_dir.is_absolute() else PROJECT_ROOT / output_dir


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
            output_dir=resolve_output_dir(_env("OUTPUT_DIR", "exports")),
            default_lookback_hours=_positive_int("DEFAULT_LOOKBACK_HOURS", 24),
            timezone=timezone,
        )


@dataclass(frozen=True, slots=True)
class TicketSummarySettings:
    """Optional OpenAI-compatible settings for XLSX ticket summaries."""

    api_base_url: str | None
    model: str | None
    api_key: str | None

    @property
    def enabled(self) -> bool:
        """Whether enough configuration is present to offer AI summarization."""
        return self.api_base_url is not None and self.model is not None

    @classmethod
    def from_env(cls) -> "TicketSummarySettings":
        api_base_url = (_env("TICKET_SUMMARY_API_BASE_URL", "") or "").strip().rstrip("/")
        model = (_env("TICKET_SUMMARY_MODEL", "") or "").strip()
        api_key = (_env("TICKET_SUMMARY_API_KEY", "") or "").strip()
        return cls(
            api_base_url=api_base_url or None,
            model=model or None,
            api_key=api_key or None,
        )


@dataclass(frozen=True, slots=True)
class AppSettings:
    """All settings. Telegram configuration is loaded only when requested."""

    intraservice: IntraserviceSettings
    export: ExportSettings
    ticket_summary: TicketSummarySettings
    telegram: TelegramSettings | None = None

    @classmethod
    def from_env(cls, *, include_telegram: bool = False) -> "AppSettings":
        return cls(
            intraservice=IntraserviceSettings.from_env(),
            export=ExportSettings.from_env(),
            ticket_summary=TicketSummarySettings.from_env(),
            telegram=TelegramSettings.from_env() if include_telegram else None,
        )

    def require_telegram(self) -> TelegramSettings:
        return self.telegram or TelegramSettings.from_env()
