"""Interactive first-run configuration for ISPaNo.

Run ``python setup.py`` from the project root to create or update ``.env``.
The script intentionally uses only the Python standard library so it can run
before Poetry dependencies are installed.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
import re


PROJECT_ROOT = Path(__file__).resolve().parent
ENV_FILENAME = ".env"
ENV_EXAMPLE_FILENAME = ".env.example"
SENSITIVE_KEYS = frozenset({"INTRASERVICE_PASSWORD", "TELEGRAM_BOT_TOKEN"})
COMMON_FIELDS = (
    ("INTRASERVICE_BASE_URL", "URL IntraService"),
    ("INTRASERVICE_LOGIN", "Логин IntraService"),
    ("INTRASERVICE_PASSWORD", "Пароль IntraService"),
)
TELEGRAM_FIELDS = (
    ("TELEGRAM_BOT_TOKEN", "Токен Telegram-бота"),
    ("ALLOWED_TELEGRAM_USER_IDS", "Разрешённые Telegram user ID через запятую"),
)
PLACEHOLDER_MARKERS = ("your_", "*****", "abc-your-token", "123456789,987654321")
ENV_LINE = re.compile(r"^(?P<prefix>\s*(?:export\s+)?(?P<key>[A-Za-z_][A-Za-z0-9_]*)\s*=\s*)(?P<value>.*?)(?P<ending>\r?\n)?$")


def _parse_env(lines: list[str]) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in lines:
        match = ENV_LINE.match(line)
        if match:
            values[match.group("key")] = match.group("value").strip()
    return values


def _is_placeholder(value: str) -> bool:
    lowered = value.casefold()
    return not value or any(marker in lowered for marker in PLACEHOLDER_MARKERS)


def _select_scenario(input_func: Callable[[str], str]) -> bool:
    print("Выберите, что будете запускать:")
    print("  1. JSON-экспорт и XLSX-отчёт")
    print("  2. Telegram-бот")
    print("  3. Оба варианта")
    while True:
        choice = input_func("Номер варианта [1]: ").strip() or "1"
        if choice == "1":
            return False
        if choice in {"2", "3"}:
            return True
        print("Введите 1, 2 или 3.")


def _is_valid(key: str, value: str) -> bool:
    if not value.strip():
        return False
    if key == "ALLOWED_TELEGRAM_USER_IDS":
        return all(
            item.strip().isascii()
            and item.strip().isdigit()
            and int(item.strip()) > 0
            for item in value.split(",")
        )
    return True


def _prompt_value(
    key: str,
    label: str,
    current: str,
    input_func: Callable[[str], str],
) -> str:
    usable_current = "" if _is_placeholder(current) else current
    if key in SENSITIVE_KEYS:
        hint = "уже задан" if usable_current else "не задан"
    elif usable_current:
        hint = f"текущее: {usable_current}"
    else:
        hint = "не задан"

    while True:
        value = input_func(f"{label} ({hint}): ").strip()
        if not value and usable_current:
            return usable_current
        if _is_valid(key, value):
            return value
        if key == "ALLOWED_TELEGRAM_USER_IDS":
            print("Укажите хотя бы один положительный числовой Telegram user ID через запятую.")
        else:
            print("Это обязательное значение. Введите непустое значение.")


def _update_env(lines: list[str], updates: dict[str, str]) -> list[str]:
    remaining = dict(updates)
    result: list[str] = []
    for line in lines:
        match = ENV_LINE.match(line)
        if match and match.group("key") in remaining:
            key = match.group("key")
            ending = match.group("ending") or "\n"
            result.append(f"{match.group('prefix')}{remaining.pop(key)}{ending}")
        else:
            result.append(line)
    if remaining:
        if result and not result[-1].endswith(("\n", "\r")):
            result[-1] += "\n"
        result.extend(f"{key}={value}\n" for key, value in remaining.items())
    return result


def _print_next_steps() -> None:
    print("\nНастройка завершена.")
    print("\nДальше:")
    print("  poetry install")
    print("  poetry run ispano export        # JSON-экспорт")
    print("  poetry run ispano tickets 4672  # XLSX-отчёт")
    print("  poetry run ispano bot           # Telegram-бот")
    print("  Подробнее: README.md")


def run_setup(project_root: Path = PROJECT_ROOT, input_func: Callable[[str], str] = input) -> None:
    """Create or interactively update a project's .env file."""
    env_path = project_root / ENV_FILENAME
    example_path = project_root / ENV_EXAMPLE_FILENAME
    if env_path.exists():
        lines = env_path.read_text(encoding="utf-8").splitlines(keepends=True)
        print("Найден существующий .env. Нажмите Enter, чтобы сохранить текущее значение.")
        is_new = False
    else:
        if not example_path.is_file():
            raise FileNotFoundError(f"Не найден шаблон конфигурации: {example_path}")
        lines = example_path.read_text(encoding="utf-8").splitlines(keepends=True)
        print(".env не найден — будет создан из .env.example.")
        is_new = True

    values = _parse_env(lines)
    include_telegram = _select_scenario(input_func)
    fields = COMMON_FIELDS + (TELEGRAM_FIELDS if include_telegram else ())
    updates = {
        key: _prompt_value(key, label, values.get(key, ""), input_func)
        for key, label in fields
    }
    if is_new and not include_telegram:
        updates.update({key: "" for key, _ in TELEGRAM_FIELDS})

    env_path.write_text("".join(_update_env(lines, updates)), encoding="utf-8")
    _print_next_steps()


def main() -> int:
    try:
        run_setup()
    except (EOFError, KeyboardInterrupt):
        print("\nНастройка отменена.")
        return 1
    except OSError as exc:
        print(f"Не удалось записать .env: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
