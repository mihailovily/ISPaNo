"""HTTP integration with IntraService."""

from __future__ import annotations

import time
from datetime import datetime
from typing import Any, Callable

import requests

from ..settings import IntraserviceSettings
from .parsing import parse_api_datetime, parse_json_or_die, parse_ticket_history


class AuthenticationError(RuntimeError):
    """IntraService did not establish an authenticated session."""


class IntraserviceTimeoutError(requests.Timeout):
    """An IntraService request exceeded its configured timeout."""


class IntraserviceResponseError(RuntimeError):
    """IntraService returned an unexpected HTTP or payload response."""


class IntraserviceClient:
    """Session-owning client for the IntraService endpoints used by exports."""

    def __init__(self, settings: IntraserviceSettings, login: str, password: str) -> None:
        self.settings = settings
        self.login_name = login
        self.password = password
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": "Mozilla/5.0 (compatible; ISPaNo/0.2)",
                "Accept-Language": "ru-RU,ru;q=0.9",
            }
        )

    def __enter__(self) -> "IntraserviceClient":
        try:
            self.login()
        except Exception:
            self.session.close()
            raise
        return self

    def __exit__(self, *_: object) -> None:
        self.session.close()

    def login(self) -> None:
        try:
            response = self.session.post(
                f"{self.settings.base_url}/",
                data={"login": self.login_name, "password": self.password},
                headers={
                    "Referer": f"{self.settings.base_url}/",
                    "Content-Type": "application/x-www-form-urlencoded",
                },
                allow_redirects=True,
                timeout=self.settings.request_timeout,
            )
            response.raise_for_status()
        except requests.Timeout as exc:
            raise IntraserviceTimeoutError("Тайм-аут авторизации в IntraService.") from exc
        except requests.RequestException as exc:
            raise AuthenticationError(f"Ошибка авторизации в IntraService: {exc}") from exc

        if not self.session.cookies.get(".INTRASERVICE"):
            raise AuthenticationError(
                "Авторизация не прошла: cookie .INTRASERVICE не появилась. "
                "Проверь логин и пароль."
            )

    def fetch_tasks_page(self, page: int) -> dict[str, Any]:
        try:
            response = self.session.get(
                f"{self.settings.base_url}/api/Task",
                params={"tb_orderby": "Changed desc", "nolayout": "true", "page": page},
                timeout=self.settings.request_timeout,
            )
            response.raise_for_status()
            return parse_json_or_die(response, f"/api/Task (страница {page})")
        except requests.Timeout as exc:
            raise IntraserviceTimeoutError(f"Тайм-аут загрузки страницы {page}.") from exc
        except (requests.RequestException, ValueError) as exc:
            raise IntraserviceResponseError(f"Ошибка загрузки страницы {page}: {exc}") from exc

    def iter_changed_tasks(
        self, cutoff: datetime, report: Callable[[str], None] = print
    ) -> list[dict[str, Any]]:
        comparison_cutoff = cutoff.replace(tzinfo=None) if cutoff.tzinfo else cutoff
        tickets: list[dict[str, Any]] = []
        page = 1
        previous_first_id: Any = None

        while True:
            tasks = self.fetch_tasks_page(page).get("Tasks") or []
            if not tasks:
                report(f"Страница {page} пустая - тикеты закончились.")
                break

            first_id = tasks[0].get("Id")
            if page > 1 and first_id is not None and first_id == previous_first_id:
                report(f"Пагинация не изменилась на странице {page}; экспорт остановлен.")
                break
            previous_first_id = first_id

            reached_cutoff = False
            for task in tasks:
                changed_at = parse_api_datetime(task.get("Changed"))
                if changed_at is None or changed_at <= comparison_cutoff:
                    reached_cutoff = True
                    break
                tickets.append(task)
            if reached_cutoff:
                report(f"Дошли до тикетов старше {cutoff}; страница {page} завершена.")
                break
            if page >= self.settings.max_pages:
                report("Достигнут MAX_PAGES_SAFETY; экспорт остановлен.")
                break
            page += 1
            time.sleep(self.settings.request_delay)
        return tickets

    def get_ticket_chat(
        self,
        ticket_id: Any,
        created_at: datetime | None,
        upper_bound: datetime | None,
    ) -> list[dict[str, Any]]:
        try:
            response = self.session.get(
                f"{self.settings.base_url}/Task/View/{ticket_id}",
                timeout=self.settings.request_timeout,
            )
            response.raise_for_status()
        except requests.Timeout as exc:
            raise IntraserviceTimeoutError(f"Тайм-аут загрузки тикета {ticket_id}.") from exc
        except requests.RequestException as exc:
            raise IntraserviceResponseError(f"Ошибка загрузки тикета {ticket_id}: {exc}") from exc
        return parse_ticket_history(response.text, created_at, upper_bound)
