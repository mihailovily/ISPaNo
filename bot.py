#!/usr/bin/env python3
"""
Telegram-бот-обёртка над intraservice_parser.py.

Команды:
  /start           - краткая справка.
  /export          - выгрузить тикеты, изменённые за последние
                      DEFAULT_LOOKBACK_HOURS часов (см. .env).
  /export ДД.ММ.ГГГГ [ЧЧ:ММ]
                    - выгрузить тикеты, изменённые после указанной даты.

Бот сам логинится в Intraservice логином/паролем из .env (никакого
input() тут быть не может - процесс работает без консоли, обычно
внутри Docker), забирает тикеты + чат и присылает результат обратно
как JSON-файл прямо в чат.

Доступ ограничен списком ALLOWED_TELEGRAM_USER_IDS из .env (если
список пуст - бот отвечает всем, см. предупреждение при старте).
"""

import asyncio
import io
import json
import logging
from datetime import datetime

from telegram import Update, InputFile
from telegram.constants import ChatAction
from telegram.ext import Application, CommandHandler, ContextTypes

import config
import intraservice_parser as isp

logging.basicConfig(
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger("intraservice-bot")


def is_allowed(user_id: int) -> bool:
    return user_id in config.ALLOWED_TELEGRAM_USER_IDS


async def _update_progress(status_msg, progress_queue: asyncio.Queue[str | None]) -> None:
    """Forward parser progress to Telegram without crossing thread boundaries."""
    latest_line = None
    while True:
        line = await progress_queue.get()
        if line is None:
            if latest_line is not None:
                try:
                    await status_msg.edit_text(f"Обновление прогресса:\n{latest_line}")
                except Exception:  # noqa: BLE001 - progress must not break export
                    logger.exception("Failed to update export progress")
            return

        latest_line = line
        try:
            while True:
                line = await asyncio.wait_for(progress_queue.get(), timeout=2.0)
                if line is None:
                    try:
                        await status_msg.edit_text(f"Обновление прогресса:\n{latest_line}")
                    except Exception:  # noqa: BLE001 - progress must not break export
                        logger.exception("Failed to update export progress")
                    return
                latest_line = line
        except asyncio.TimeoutError:
            pass

        try:
            await status_msg.edit_text(f"Обновление прогресса:\n{latest_line}")
        except Exception:  # noqa: BLE001 - progress must not break export
            logger.exception("Failed to update export progress")
        latest_line = None


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "Привет! Я выгружаю тикеты из Intraservice и присылаю JSON.\n\n"
        "Команды:\n"
        "/export - тикеты за последние "
        f"{config.DEFAULT_LOOKBACK_HOURS} ч.\n"
        "/export 20.08.2026 - тикеты, изменённые после этой даты\n"
        "/export 20.08.2026 14:30 - с точным временем"
    )


async def export_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if not is_allowed(user.id):
        logger.warning("Отказано в доступе user_id=%s (@%s)", user.id, user.username)
        await update.message.reply_text("Доступ к этому боту для тебя не открыт.")
        return

    if not config.INTRASERVICE_LOGIN or not config.INTRASERVICE_PASSWORD:
        await update.message.reply_text(
            "На сервере не заданы INTRASERVICE_LOGIN / INTRASERVICE_PASSWORD "
            "(проверь .env)."
        )
        return

    # Разбираем дату из аргументов команды, если она есть.
    args = context.args or []
    if args:
        raw = " ".join(args)
        cutoff = isp.parse_dot_datetime(raw) or isp.parse_dot_datetime(raw + " 00:00")
        if cutoff is None:
            await update.message.reply_text(
                "Не понял дату. Формат: ДД.ММ.ГГГГ или ДД.ММ.ГГГГ ЧЧ:ММ, "
                "например: /export 20.08.2026 14:30"
            )
            return
    else:
        cutoff = isp.default_cutoff()

    status_msg = await update.message.reply_text(
        f"Начинаю выгрузку тикетов, изменённых после {cutoff:%d.%m.%Y %H:%M}...\n"
        f"Это может занять какое-то время в зависимости от количества тикетов."
    )
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)

    # Передаём прогресс из рабочего потока в event loop через thread-safe очередь.
    loop = asyncio.get_running_loop()
    progress_queue: asyncio.Queue[str | None] = asyncio.Queue()
    progress_task = asyncio.create_task(_update_progress(status_msg, progress_queue))

    def log(line: str) -> None:
        logger.info(line)
        loop.call_soon_threadsafe(progress_queue.put_nowait, line)

    result: list[dict] | None = None
    error_message: str | None = None
    try:
        # requests/BeautifulSoup синхронные - гоняем их в отдельном потоке,
        # чтобы не блокировать event loop бота (и чтобы бот отвечал другим
        # пользователям, пока идёт долгая выгрузка).
        result = await loop.run_in_executor(
            None,
            isp.export_tickets,
            config.INTRASERVICE_LOGIN,
            config.INTRASERVICE_PASSWORD,
            cutoff,
            log,
        )
    except isp.LoginError as e:
        error_message = f"Не удалось авторизоваться в Intraservice: {e}"
    except Exception as e:  # noqa: BLE001 - хотим сообщить пользователю о любой ошибке
        logger.exception("Ошибка при экспорте тикетов")
        error_message = f"Произошла ошибка при выгрузке: {e}"

    finally:
        loop.call_soon_threadsafe(progress_queue.put_nowait, None)
        await progress_task

    if error_message is not None:
        await status_msg.edit_text(error_message)
        return

    if not result:
        await status_msg.edit_text(
            f"Готово, но тикетов, изменённых после {cutoff:%d.%m.%Y %H:%M}, не найдено."
        )
        return

    payload = json.dumps(result, ensure_ascii=False, indent=2).encode("utf-8")
    filename = f"tickets_export_{datetime.now():%Y%m%d_%H%M%S}.json"

    await status_msg.edit_text(f"Готово, тикетов: {len(result)}. Отправляю файл...")
    await update.message.reply_document(
        document=InputFile(io.BytesIO(payload), filename=filename),
        caption=f"Тикеты, изменённые после {cutoff:%d.%m.%Y %H:%M} - всего {len(result)} шт.",
    )


def build_application() -> Application:
    app = Application.builder().token(config.require_telegram_bot_token()).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("export", export_command))
    return app


def main() -> None:
    config.require_allowed_telegram_user_ids()
    if not config.ALLOWED_TELEGRAM_USER_IDS:
        logger.warning(
            "ALLOWED_TELEGRAM_USER_IDS не задан - бот будет отвечать ЛЮБОМУ "
            "пользователю Telegram. Рекомендуется ограничить доступ в .env."
        )
    app = build_application()
    logger.info("Бот запущен, жду команды...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
