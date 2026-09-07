"""Progress delivery from worker threads to the Telegram event loop."""

from __future__ import annotations

import asyncio
import logging

logger = logging.getLogger(__name__)


async def update_status(status_message: object, queue: asyncio.Queue[str | None]) -> None:
    """Coalesce progress lines and keep progress failures non-fatal."""
    latest: str | None = None
    while True:
        line = await queue.get()
        if line is None:
            if latest:
                await _edit(status_message, latest)
            return
        latest = line
        try:
            while True:
                line = await asyncio.wait_for(queue.get(), timeout=2.0)
                if line is None:
                    await _edit(status_message, latest)
                    return
                latest = line
        except asyncio.TimeoutError:
            pass
        await _edit(status_message, latest)
        latest = None


async def _edit(status_message: object, text: str) -> None:
    try:
        await status_message.edit_text(f"Обновление прогресса:\n{text}")
    except Exception:  # noqa: BLE001 - status must not cancel an export
        logger.exception("Не удалось обновить прогресс экспорта")
