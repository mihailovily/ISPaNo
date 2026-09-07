"""Small domain models used by serializers and integrations."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class ExportItem:
    """A raw IntraService ticket with its parsed history."""

    ticket: dict[str, Any]
    chat: list[dict[str, Any]]


@dataclass(frozen=True, slots=True)
class ExportDocument:
    """Canonical v2 export document."""

    schema_version: int
    exported_at: str
    cutoff: str
    source_timezone: str
    tickets: list[dict[str, Any]]
