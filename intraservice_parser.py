#!/usr/bin/env python3
"""Парсер тикетов из Intraservice и экспорт в JSON."""

import json
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path

import requests
from bs4 import BeautifulSoup

import config

MONTHS_RU = {
    "января": 1, "февраля": 2, "марта": 3, "апреля": 4,
    "мая": 5, "июня": 6, "июля": 7, "августа": 8,
    "сентября": 9, "октября": 10, "ноября": 11, "декабря": 12,
}

# Комментарий текущего/недавнего года: "27 августа, 16:25" (без года).
COMMENT_DATE_RE_NO_YEAR = re.compile(r"(\d{1,2})\s+(\S+),\s+(\d{1,2}):(\d{2})")
# Комментарий тикета старше года: "05.05.2023, 12:56" (год указан явно).
COMMENT_DATE_RE_WITH_YEAR = re.compile(r"(\d{1,2})\.(\d{1,2})\.(\d{4}),\s+(\d{1,2}):(\d{2})")


class LoginError(RuntimeError):
    """Не удалось залогиниться в Intraservice (неверный логин/пароль и т.п.)."""


def login(session: requests.Session, login_name: str, password: str) -> None:
    """Авторизация в Intraservice."""
    resp = session.post(
        config.BASE_URL + "/",
        data={"login": login_name, "password": password},
        headers={
            "Referer": config.BASE_URL + "/",
            "Content-Type": "application/x-www-form-urlencoded",
        },
        allow_redirects=True,
    )
    resp.raise_for_status()

    # Успешный логин отдаёт 302 -> /Task и ставит cookie .INTRASERVICE.
    if not session.cookies.get(".INTRASERVICE"):
        raise LoginError(
            "Авторизация не прошла - cookie .INTRASERVICE не появилась. "
            "Проверь INTRASERVICE_LOGIN / INTRASERVICE_PASSWORD."
        )


def make_session(login_name: str, password: str) -> requests.Session:
    s = requests.Session()
    s.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36",
        "Accept-Language": "ru-RU,ru;q=0.9",
    })
    login(s, login_name, password)
    return s


def parse_dot_datetime(s: str):
    """Формат 'ДД.ММ.ГГГГ ЧЧ:ММ[:СС]' -> datetime или None."""
    if not s:
        return None
    s = s.strip()
    for fmt in ("%d.%m.%Y %H:%M:%S", "%d.%m.%Y %H:%M"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    return None


def parse_api_datetime(s):
    """Формат из JSON API: '2026-08-28T08:58:32.207' -> datetime, либо None."""
    if not s:
        return None
    try:
        return datetime.fromisoformat(s)
    except ValueError:
        return None


def infer_comment_datetime(day: int, month: int, hour: int, minute: int,
                            created_dt, upper_dt):
    """
    В HTML комментария год не указан ('27 августа, 16:25').
    Подбираем год так, чтобы дата попадала в диапазон [created_dt, upper_dt].
    """
    candidates = []
    lo_year = created_dt.year if created_dt else (upper_dt.year - 1 if upper_dt else datetime.now().year - 1)
    hi_year = upper_dt.year if upper_dt else datetime.now().year
    for year in range(lo_year, hi_year + 1):
        try:
            candidate = datetime(year, month, day, hour, minute)
        except ValueError:
            continue
        candidates.append(candidate)

    if not candidates:
        return None

    in_range = [c for c in candidates
                if (created_dt is None or c >= created_dt.replace(hour=0, minute=0, second=0))
                and (upper_dt is None or c <= upper_dt)]
    if in_range:
        return max(in_range)
    return min(candidates, key=lambda c: abs((c - (upper_dt or c)).total_seconds()))


def parse_json_or_die(resp: requests.Response, context: str) -> dict:
    """Разбор JSON ответа или поднятие понятной ошибки."""
    try:
        return resp.json()
    except ValueError:
        raise RuntimeError(
            f"Не удалось разобрать JSON в ответе на {context}. "
            f"HTTP статус: {resp.status_code}, "
            f"Content-Type: {resp.headers.get('Content-Type')}. "
            f"Похоже, сессия протухла и сервер вернул страницу логина - "
            f"попробуй запустить экспорт ещё раз."
        )


def fetch_tasks_page(session: requests.Session, page: int) -> dict:
    url = f"{config.BASE_URL}/api/Task"
    data = {
        "tb_orderby": "Changed desc",
        "nolayout": "true",
        "page": page,
    }
    resp = session.request("GET", url, data=data)
    resp.raise_for_status()
    return parse_json_or_die(resp, context=f"/api/Task (страница {page})")


def get_tickets_changed_after(session: requests.Session, cutoff: datetime,
                               log=print) -> list[dict]:
    """
    Идём по страницам /api/Task (сортировка Changed desc), собираем полные
    словари тикетов, у которых Changed > cutoff. log() - функция для вывода
    прогресса (по умолчанию print, бот подставляет свою).
    """
    import time

    tickets = []
    page = 1
    reached_cutoff = False
    prev_first_id = None

    while True:
        root = fetch_tasks_page(session, page)
        tasks = root.get("Tasks") or []

        if not tasks:
            log(f"Страница {page} пустая - тикеты закончились.")
            break

        first_id_on_page = tasks[0].get("Id")
        if page > 1 and first_id_on_page is not None and first_id_on_page == prev_first_id:
            log(f"ВНИМАНИЕ: страница {page} вернула тот же первый тикет ({first_id_on_page}) - "
                f"параметр пагинации не действует, останавливаюсь.")
            break
        prev_first_id = first_id_on_page

        for task in tasks:
            changed_dt = parse_api_datetime(task.get("Changed"))
            if changed_dt is None or changed_dt <= cutoff:
                reached_cutoff = True
                break
            tickets.append(task)

        if reached_cutoff:
            log(f"Дошли до тикетов старше {cutoff}, останавливаемся (страница {page}).")
            break
        if page >= config.MAX_PAGES_SAFETY:
            log("Достигнут предохранитель по числу страниц (MAX_PAGES_SAFETY), останавливаюсь.")
            break

        page += 1
        time.sleep(config.REQUEST_DELAY)

    return tickets


def get_ticket_chat(session: requests.Session, ticket_id, created_dt, upper_dt) -> list[dict]:
    url = f"{config.BASE_URL}/Task/View/{ticket_id}"
    resp = session.get(url)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    lifetime_block = soup.find(id="lifetimeshort")
    if lifetime_block is None:
        return []

    comments = []
    for item in lifetime_block.find_all("div", class_="itemcomments"):
        date_span = item.find("span", class_="darkgrey")
        author_span = item.find("span", class_="lifetime-user")
        comment_div = item.find("div", class_="comment")
        details_ps = item.find_all("p", class_="lifetimedetails")

        text = None
        is_private = False
        if comment_div is not None:
            pre = comment_div.find("pre")
            if pre is not None:
                text = pre.get_text(separator="\n", strip=True)
            classes = comment_div.get("class", [])
            is_private = "private" in classes

        comment_id = None
        link_span = item.find("span", id=re.compile(r"^link\d+$"))
        if link_span is not None:
            m = re.search(r"\d+", link_span["id"])
            if m:
                comment_id = int(m.group())

        date_iso = None
        date_raw = date_span.get_text(strip=True) if date_span else None
        if date_raw:
            m_year = COMMENT_DATE_RE_WITH_YEAR.search(date_raw)
            m_noyear = COMMENT_DATE_RE_NO_YEAR.search(date_raw) if not m_year else None

            if m_year:
                day, month, year, hour, minute = m_year.groups()
                try:
                    date_iso = datetime(int(year), int(month), int(day),
                                         int(hour), int(minute)).isoformat()
                except ValueError:
                    date_iso = None
            elif m_noyear:
                day, month_name, hour, minute = m_noyear.groups()
                month = MONTHS_RU.get(month_name.lower())
                if month:
                    dt = infer_comment_datetime(
                        int(day), month, int(hour), int(minute),
                        created_dt, upper_dt,
                    )
                    if dt:
                        date_iso = dt.isoformat()

        comments.append({
            "id": comment_id,
            "date_raw": date_raw,
            "date": date_iso,
            "author": author_span.get_text(strip=True) if author_span else None,
            "text": text,
            "is_private": is_private,
            "events": [p.get_text(strip=True) for p in details_ps] or None,
        })

    comments.reverse()
    return comments


def export_tickets(login_name: str, password: str, cutoff: datetime,
                    log=print) -> list[dict]:
    """Получение тикетов и чата после даты cutoff."""
    import time

    session = make_session(login_name, password)
    log(f"Авторизация выполнена. Ищу тикеты, изменённые после {cutoff}...")

    tickets = get_tickets_changed_after(session, cutoff, log=log)
    log(f"Найдено тикетов: {len(tickets)}")

    result = []
    for i, ticket in enumerate(tickets, 1):
        ticket_id = ticket.get("Id")
        log(f"[{i}/{len(tickets)}] Тикет {ticket_id}...")
        try:
            created_dt = parse_api_datetime(ticket.get("Created"))
            closed_dt = parse_api_datetime(ticket.get("Closed"))
            changed_dt = parse_api_datetime(ticket.get("Changed"))
            upper_dt = closed_dt or changed_dt or datetime.now()

            chat = get_ticket_chat(session, ticket_id, created_dt, upper_dt)
            time.sleep(config.REQUEST_DELAY)
        except requests.RequestException as e:
            log(f"Ошибка запроса для тикета {ticket_id}: {e}")
            continue

        result.append({"ticket": ticket, "chat": chat})

    result.sort(key=lambda item: int(item["ticket"].get("Id", 0)), reverse=True)
    return result


def default_cutoff() -> datetime:
    """Если дата не задана явно - берём последние DEFAULT_LOOKBACK_HOURS часов."""
    return datetime.now() - timedelta(hours=config.DEFAULT_LOOKBACK_HOURS)


def _read_cutoff_date_interactive() -> datetime:
    while True:
        raw = input("С какой даты брать тикеты (изменённые ПОСЛЕ неё)? "
                     "Формат ДД.ММ.ГГГГ или ДД.ММ.ГГГГ ЧЧ:ММ:\n> ").strip()
        if not raw:
            continue
        dt = parse_dot_datetime(raw)
        if dt is None:
            dt = parse_dot_datetime(raw + " 00:00")
        if dt is None:
            print("  Не понял дату, попробуй ещё раз в формате ДД.ММ.ГГГГ.")
            continue
        return dt


def _get_credential_interactive(env_value: str | None, prompt_label: str, env_name: str) -> str:
    if env_value:
        return env_value
    value = input(f"{prompt_label}: ").strip()
    if not value:
        sys.exit(f"{env_name} не задан ни в переменных окружения/.env, ни введён вручную.")
    return value


def main():
    """CLI-режим ручного запуска и сохранения JSON в файл."""
    login_name = _get_credential_interactive(config.INTRASERVICE_LOGIN, "Логин Intraservice", "INTRASERVICE_LOGIN")
    password = _get_credential_interactive(config.INTRASERVICE_PASSWORD, "Пароль Intraservice", "INTRASERVICE_PASSWORD")
    cutoff = _read_cutoff_date_interactive()

    try:
        result = export_tickets(login_name, password, cutoff)
    except LoginError as e:
        sys.exit(str(e))

    out_dir = Path(config.OUTPUT_DIR)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"tickets_export_{datetime.now():%Y%m%d_%H%M%S}.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"\nГотово. Сохранено {len(result)} тикетов в {out_path}")


if __name__ == "__main__":
    main()
