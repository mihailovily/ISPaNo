"""Telegram application factory."""

from __future__ import annotations

from telegram.ext import Application, CommandHandler

from ..settings import AppSettings
from .handlers import export_command, start


def build_application(settings: AppSettings) -> Application:
    telegram = settings.require_telegram()
    application = Application.builder().token(telegram.bot_token).build()
    application.bot_data["settings"] = settings
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("export", export_command))
    return application
