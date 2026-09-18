from __future__ import annotations

import argparse
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from ispano import cli
from ispano.settings import TicketSummarySettings


class TicketCommandAiPromptTests(unittest.TestCase):
    def _settings(self, summary: TicketSummarySettings) -> Mock:
        settings = Mock()
        settings.intraservice.require_credentials.return_value = ("login", "password")
        settings.ticket_summary = summary
        return settings

    @patch("ispano.cli.create_ticket_report", return_value=(Path("report.xlsx"), set()))
    @patch("ispano.cli.AppSettings.from_env")
    @patch("builtins.input", return_value="Y")
    def test_y_enables_ai_summarizer(
        self, input_func: Mock, settings_loader: Mock, report_creator: Mock
    ) -> None:
        settings_loader.return_value = self._settings(
            TicketSummarySettings("http://ai.test/v1", "model", None)
        )
        result = cli.run_tickets(argparse.Namespace(ticket_id=20))

        self.assertEqual(result, 0)
        input_func.assert_called_once_with(
            "Использовать ИИ для заполнения статусов и описаний? [y/N] "
        )
        self.assertTrue(report_creator.call_args.kwargs["use_ai"])

    @patch("ispano.cli.create_ticket_report", return_value=(Path("report.xlsx"), set()))
    @patch("ispano.cli.AppSettings.from_env")
    @patch("builtins.input", return_value="")
    def test_empty_answer_disables_ai_summarizer(
        self, _: Mock, settings_loader: Mock, report_creator: Mock
    ) -> None:
        settings_loader.return_value = self._settings(
            TicketSummarySettings("http://ai.test/v1", "model", None)
        )
        cli.run_tickets(argparse.Namespace(ticket_id=20))

        self.assertFalse(report_creator.call_args.kwargs["use_ai"])

    @patch("ispano.cli.create_ticket_report", return_value=(Path("report.xlsx"), set()))
    @patch("ispano.cli.AppSettings.from_env")
    @patch("builtins.input")
    def test_does_not_prompt_when_ai_is_not_configured(
        self, input_func: Mock, settings_loader: Mock, report_creator: Mock
    ) -> None:
        settings_loader.return_value = self._settings(TicketSummarySettings(None, None, None))
        cli.run_tickets(argparse.Namespace(ticket_id=20))

        input_func.assert_not_called()
        self.assertFalse(report_creator.call_args.kwargs["use_ai"])
