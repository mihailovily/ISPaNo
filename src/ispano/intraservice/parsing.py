"""Pure parsers for IntraService dates, JSON and ticket history HTML."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from urllib.parse import parse_qs, urlparse

import requests
from bs4 import BeautifulSoup

MONTHS_RU = {
    "января": 1,
    "февраля": 2,
    "марта": 3,
    "апреля": 4,
    "мая": 5,
    "июня": 6,
    "июля": 7,
    "августа": 8,
    "сентября": 9,
    "октября": 10,
    "ноября": 11,
    "декабря": 12,
}
COMMENT_DATE_RE_NO_YEAR = re.compile(r"(\d{1,2})\s+(\S+),\s+(\d{1,2}):(\d{2})")
COMMENT_DATE_RE_WITH_YEAR = re.compile(r"(\d{1,2})\.(\d{1,2})\.(\d{4}),\s+(\d{1,2}):(\d{2})")
CREATED_AT_RE = re.compile(
    r"Создана:\s*(\d{1,2})\s+(\S+)\s+(\d{4})\s+(\d{1,2}):(\d{2})", re.IGNORECASE
)
# IntraService emits relative links (``Task/view/4671``) in the list, while
# other installations/fixtures may use absolute-path links (``/Task/View/4671``).
TASK_VIEW_ID_RE = re.compile(r"/?Task/View/(\d+)", re.IGNORECASE)


@dataclass(frozen=True, slots=True)
class TicketCard:
    """Fields from a ticket page needed for the weekly report."""

    status: str | None
    support_type: str | None
    creator_organization: str | None
    last_updated_at: datetime | None


def parse_dot_datetime(value: str | None) -> datetime | None:
    """Parse ``ДД.ММ.ГГГГ ЧЧ:ММ[:СС]``."""
    if not value:
        return None
    value = value.strip()
    for fmt in ("%d.%m.%Y %H:%M:%S", "%d.%m.%Y %H:%M"):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    return None


def parse_api_datetime(value: str | None) -> datetime | None:
    """Parse the ISO-like timestamp returned by the API."""
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def infer_comment_datetime(
    day: int,
    month: int,
    hour: int,
    minute: int,
    created_at: datetime | None,
    upper_bound: datetime | None,
    now: datetime | None = None,
) -> datetime | None:
    """Infer the year for a history date that omits it."""
    now = now or datetime.now()
    created_bound = created_at.replace(tzinfo=None) if created_at else None
    upper_bound_naive = upper_bound.replace(tzinfo=None) if upper_bound else None
    now_naive = now.replace(tzinfo=None)
    if created_bound:
        low_year = created_bound.year
    elif upper_bound_naive:
        low_year = upper_bound_naive.year - 1
    else:
        low_year = now_naive.year - 1
    high_year = upper_bound_naive.year if upper_bound_naive else now_naive.year
    candidates: list[datetime] = []
    for year in range(low_year, high_year + 1):
        try:
            candidates.append(datetime(year, month, day, hour, minute))
        except ValueError:
            continue
    if not candidates:
        return None
    in_range = [
        candidate
        for candidate in candidates
        if (
            created_bound is None
            or candidate >= created_bound.replace(hour=0, minute=0, second=0, microsecond=0)
        )
        and (upper_bound_naive is None or candidate <= upper_bound_naive)
    ]
    if in_range:
        return max(in_range)
    return min(
        candidates,
        key=lambda candidate: abs((candidate - (upper_bound_naive or candidate)).total_seconds()),
    )


def parse_json_or_die(response: requests.Response, context: str) -> dict[str, Any]:
    """Decode an API response and include useful context on malformed data."""
    try:
        payload = response.json()
    except ValueError as exc:
        raise ValueError(
            f"Не удалось разобрать JSON в ответе на {context}. "
            f"HTTP статус: {response.status_code}, "
            f"Content-Type: {response.headers.get('Content-Type')}."
        ) from exc
    if not isinstance(payload, dict):
        raise ValueError(f"Ответ на {context} должен быть JSON-объектом.")
    return payload


def parse_task_list_ids(html: str) -> list[int]:
    """Extract distinct ticket IDs from a ``/task/list`` HTML response."""
    soup = BeautifulSoup(html, "html.parser")
    result: list[int] = []
    for link in soup.find_all("a", href=True):
        match = TASK_VIEW_ID_RE.search(str(link["href"]))
        if match:
            ticket_id = int(match.group(1))
            if ticket_id not in result:
                result.append(ticket_id)
    return result


def _parse_created_at(soup: BeautifulSoup) -> datetime | None:
    creator = soup.find(id="creator")
    if creator is None:
        return None


def _parse_support_type(soup: BeautifulSoup) -> str | None:
    """Extract the support service name from the ticket's service link.

    ``#tasktypespan`` contains the technical subtype (for example,
    ``Стандартный``), not the support service used in the report. The report
    value is the text of the link to ``/Task/index?tb_serviceid=...``.
    """
    for link in soup.find_all("a", href=True):
        parsed_url = urlparse(str(link["href"]))
        path = parsed_url.path.rstrip("/").lstrip("/").casefold()
        if path != "task/index" or "tb_serviceid" not in parse_qs(parsed_url.query):
            continue
        value = link.get_text(" ", strip=True)
        if not value:
            value = str(link.get("title", "")).strip()
        if value:
            return value
    return None
    match = CREATED_AT_RE.search(creator.get_text(" ", strip=True))
    if not match:
        return None
    day, month_name, year, hour, minute = match.groups()
    month = MONTHS_RU.get(month_name.lower())
    if month is None:
        return None
    try:
        return datetime(int(year), month, int(day), int(hour), int(minute))
    except ValueError:
        return None


def parse_ticket_card(html: str, *, now: datetime | None = None) -> TicketCard:
    """Parse current ticket metadata and the latest lifecycle timestamp."""
    soup = BeautifulSoup(html, "html.parser")

    status = None
    status_select = soup.find("select", id="statusid")
    if status_select is not None:
        selected = status_select.find("option", selected=True)
        if selected is not None:
            status = selected.get_text(" ", strip=True) or None

    support_type = _parse_support_type(soup)

    creator_organization = None
    creator = soup.find(id="creator")
    if creator is not None:
        organization_link = creator.find("a", title=True)
        if organization_link is not None:
            creator_organization = str(organization_link["title"]).strip() or None

    reference_time = now or datetime.now()
    history = parse_ticket_history(
        html,
        _parse_created_at(soup),
        reference_time,
        now=reference_time,
    )
    dates = [parse_api_datetime(comment.get("date")) for comment in history]
    last_updated_at = max((value for value in dates if value is not None), default=None)
    return TicketCard(status, support_type, creator_organization, last_updated_at)


def parse_ticket_history(
    html: str,
    created_at: datetime | None,
    upper_bound: datetime | None,
    *,
    now: datetime | None = None,
) -> list[dict[str, Any]]:
    """Parse ticket history without performing I/O."""
    soup = BeautifulSoup(html, "html.parser")
    lifetime_block = soup.find(id="lifetimeshort")
    if lifetime_block is None:
        return []

    comments: list[dict[str, Any]] = []
    for item in lifetime_block.find_all("div", class_="itemcomments"):
        date_span = item.find("span", class_="darkgrey")
        author_span = item.find("span", class_="lifetime-user")
        comment_div = item.find("div", class_="comment")
        detail_nodes = item.find_all("p", class_="lifetimedetails")

        text = None
        is_private = False
        if comment_div is not None:
            pre = comment_div.find("pre")
            if pre is not None:
                text = pre.get_text(separator="\n", strip=True)
            is_private = "private" in comment_div.get("class", [])

        comment_id = None
        link_span = item.find("span", id=re.compile(r"^link\d+$"))
        if link_span is not None:
            match = re.search(r"\d+", link_span.get("id", ""))
            if match:
                comment_id = int(match.group())

        date_raw = date_span.get_text(strip=True) if date_span else None
        occurred_at = None
        if date_raw:
            with_year = COMMENT_DATE_RE_WITH_YEAR.search(date_raw)
            without_year = COMMENT_DATE_RE_NO_YEAR.search(date_raw) if not with_year else None
            if with_year:
                day, month, year, hour, minute = map(int, with_year.groups())
                try:
                    occurred_at = datetime(year, month, day, hour, minute).isoformat()
                except ValueError:
                    occurred_at = None
            elif without_year:
                day, month_name, hour, minute = without_year.groups()
                month = MONTHS_RU.get(month_name.lower())
                if month:
                    inferred = infer_comment_datetime(
                        int(day), month, int(hour), int(minute), created_at, upper_bound, now
                    )
                    occurred_at = inferred.isoformat() if inferred else None

        comments.append(
            {
                "id": comment_id,
                "date_raw": date_raw,
                "date": occurred_at,
                "author": author_span.get_text(strip=True) if author_span else None,
                "text": text,
                "is_private": is_private,
                "events": [node.get_text(strip=True) for node in detail_nodes] or None,
            }
        )
    comments.reverse()
    return comments
