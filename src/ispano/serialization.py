"""Versioned JSON serializers and atomic export-file writing."""

from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable
from zoneinfo import ZoneInfo

from .intraservice.parsing import parse_api_datetime
from .models import ExportItem


def _iso(value: str | None, timezone_name: str) -> str | None:
    if not value:
        return None
    parsed = parse_api_datetime(value)
    if parsed is None:
        return value
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=ZoneInfo(timezone_name))
    return parsed.isoformat()


def _int_list(value: Any) -> list[int]:
    values = value if isinstance(value, list) else str(value or "").replace(";", ",").split(",")
    result: list[int] = []
    for item in values:
        try:
            number = int(str(item).strip())
        except (TypeError, ValueError):
            continue
        if number not in result:
            result.append(number)
    return result


def _comment_v2(comment: dict[str, Any], timezone_name: str) -> dict[str, Any]:
    return {
        "id": comment.get("id"),
        "occurred_at": _iso(comment.get("date"), timezone_name),
        "date_raw": comment.get("date_raw"),
        "author": comment.get("author"),
        "text": comment.get("text"),
        "is_private": bool(comment.get("is_private", False)),
        "events": comment.get("events"),
    }


def serialize_legacy(items: Iterable[ExportItem]) -> list[dict[str, Any]]:
    """Keep the pre-v2 ``[{ticket, chat}]`` contract unchanged."""
    return [{"ticket": item.ticket, "chat": item.chat} for item in items]


def serialize_v2(
    items: Iterable[ExportItem],
    cutoff: datetime,
    timezone_name: str,
    *,
    exported_at: datetime | None = None,
) -> dict[str, Any]:
    timezone = ZoneInfo(timezone_name)
    exported_at = exported_at or datetime.now(timezone)
    if exported_at.tzinfo is None:
        exported_at = exported_at.replace(tzinfo=timezone)
    cutoff_value = cutoff.replace(tzinfo=timezone) if cutoff.tzinfo is None else cutoff

    tickets: list[dict[str, Any]] = []
    for item in items:
        raw = item.ticket
        tickets.append(
            {
                "id": raw.get("Id"),
                "name": raw.get("Name"),
                "description": raw.get("Description"),
                "creator_id": raw.get("CreatorId"),
                "creator_name": raw.get("Creator"),
                "created_at": _iso(raw.get("Created"), timezone_name),
                "changed_at": _iso(raw.get("Changed"), timezone_name),
                "closed_at": _iso(raw.get("Closed"), timezone_name),
                "status_id": raw.get("StatusId"),
                "executor_ids": _int_list(raw.get("ExecutorIds")),
                "chat": [_comment_v2(comment, timezone_name) for comment in item.chat],
                "raw": raw,
            }
        )
    return {
        "schema_version": 2,
        "exported_at": exported_at.isoformat(),
        "cutoff": cutoff_value.isoformat(),
        "source_timezone": timezone_name,
        "tickets": tickets,
    }


def write_json_export(payload: Any, output_dir: Path, *, update_latest: bool = True) -> Path:
    """Write a timestamped JSON file and optionally update canonical ``latest.json``."""
    output_dir.mkdir(parents=True, exist_ok=True)
    target = output_dir / f"tickets_export_{datetime.now():%Y%m%d_%H%M%S}.json"
    _atomic_dump(payload, target)
    if update_latest:
        _atomic_dump(payload, output_dir / "latest.json")
    return target


def _atomic_dump(payload: Any, target: Path) -> None:
    fd, temp_name = tempfile.mkstemp(prefix=f".{target.name}.", suffix=".tmp", dir=target.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(payload, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        Path(temp_name).replace(target)
    except Exception:
        Path(temp_name).unlink(missing_ok=True)
        raise
