"""Telegram command handlers."""

from __future__ import annotations

import asyncio
import io
import json
import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from telegram import InputFile, Update
from telegram.constants import ChatAction
from telegram.ext import ContextTypes

from ..intraservice.parsing import parse_dot_datetime
from ..serialization import serialize_v2
from ..settings import AppSettings
from .progress import update_status

logger = logging.getLogger(__name__)


def is_allowed(user_id: int | None, settings: AppSettings) -> bool:
    return user_id is not None and user_id in settings.require_telegram().allowed_user_ids


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    settings: AppSettings = context.application.bot_data["settings"]
    message = update.effective_message
    if not is_allowed(update.effective_user.id if update.effective_user else None, settings):
        await message.reply_text("Доступ к этому боту не открыт.")
        return
    await message.reply_text(
        "Привет! Я выгружаю тикеты из IntraService и присылаю JSON.\n\n"
        "/export - тикеты за последние "
        f"{settings.export.default_lookback_hours} ч.\n"
        "/export ДД.ММ.ГГГГ [ЧЧ:ММ] - выгрузка после указанной даты"
    )


async def export_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    settings: AppSettings = context.application.bot_data["settings"]
    message = update.effective_message
    user_id = update.effective_user.id if update.effective_user else None
    if not is_allowed(user_id, settings):
        await message.reply_text("Доступ к этому боту не открыт.")
        return

    raw = " ".join(context.args or [])
    cutoff = (parse_dot_datetime(raw) or parse_dot_datetime(f"{raw} 00:00")) if raw else None
    if raw and cutoff is None:
        await message.reply_text("Формат даты: ДД.ММ.ГГГГ или ДД.ММ.ГГГГ ЧЧ:ММ")
        return
    cutoff = cutoff or (
        datetime.now(ZoneInfo(settings.export.timezone)).replace(tzinfo=None)
        - timedelta(hours=settings.export.default_lookback_hours)
    )

    status = await message.reply_text(f"Начинаю выгрузку после {cutoff:%d.%m.%Y %H:%M}...")
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)
    loop = asyncio.get_running_loop()
    queue: asyncio.Queue[str | None] = asyncio.Queue()
    progress_task = asyncio.create_task(update_status(status, queue))

    def report(line: str) -> None:
        logger.info(line)
        loop.call_soon_threadsafe(queue.put_nowait, line)

    exporter = context.application.bot_data["exporter"]
    try:
        items = await loop.run_in_executor(None, exporter.export, cutoff, report)
        payload = serialize_v2(items, cutoff, settings.export.timezone)
    except Exception as exc:  # noqa: BLE001 - user receives a useful failure message
        logger.exception("Ошибка экспорта")
        await status.edit_text(f"Произошла ошибка при выгрузке: {exc}")
        return
    finally:
        loop.call_soon_threadsafe(queue.put_nowait, None)
        await progress_task

    encoded = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
    await status.edit_text(f"Готово, тикетов: {len(items)}. Отправляю файл...")
    await message.reply_document(
        document=InputFile(
            io.BytesIO(encoded),
            filename=f"tickets_export_{datetime.now():%Y%m%d_%H%M%S}.json",
        ),
        caption=f"Выгружено тикетов: {len(items)}",
    )
