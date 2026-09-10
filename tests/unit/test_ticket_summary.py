from __future__ import annotations

import unittest
from unittest.mock import Mock, patch

import requests

from ispano.settings import TicketSummarySettings
from ispano.ticket_summary import TicketHistorySummarizer, TicketSummaryError


class TicketHistorySummarizerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.settings = TicketSummarySettings(
            "http://localhost:20128/v1", "local-model", "secret"
        )
        self.history = [{"author": "Оператор", "text": "Устройство отправлено к нам."}]

    @patch("ispano.ticket_summary.requests.post")
    def test_sends_openai_request_with_optional_bearer_token(self, post: Mock) -> None:
        response = Mock()
        response.json.return_value = {"choices": [{"message": {"content": "Устройство в пути."}}]}
        post.return_value = response

        result = TicketHistorySummarizer(self.settings).summarize(self.history)

        self.assertEqual(result, "Устройство в пути.")
        post.assert_called_once()
        url = post.call_args.args[0]
        kwargs = post.call_args.kwargs
        self.assertEqual(url, "http://localhost:20128/v1/chat/completions")
        self.assertEqual(kwargs["headers"]["Authorization"], "Bearer secret")
        self.assertEqual(kwargs["json"]["model"], "local-model")
        self.assertFalse(kwargs["json"]["stream"])
        self.assertIn("Устройство отправлено", kwargs["json"]["messages"][1]["content"])

    @patch("ispano.ticket_summary.requests.post")
    def test_omits_authorization_without_api_key(self, post: Mock) -> None:
        response = Mock()
        response.json.return_value = {"choices": [{"message": {"content": "Ведётся поиск решения."}}]}
        post.return_value = response

        result = TicketHistorySummarizer(
            TicketSummarySettings("http://ai.test/v1", "model", None)
        ).summarize([])

        self.assertEqual(result, "Ведётся поиск решения.")
        self.assertNotIn("Authorization", post.call_args.kwargs["headers"])

    @patch("ispano.ticket_summary.requests.post")
    def test_limits_result_to_1000_characters(self, post: Mock) -> None:
        response = Mock()
        response.json.return_value = {"choices": [{"message": {"content": "а" * 1200}}]}
        post.return_value = response

        self.assertEqual(len(TicketHistorySummarizer(self.settings).summarize([])), 1000)

    @patch("ispano.ticket_summary.time.sleep")
    @patch("ispano.ticket_summary.requests.post")
    def test_retries_three_times_then_fails(self, post: Mock, sleep: Mock) -> None:
        post.side_effect = requests.ConnectionError("offline")

        with self.assertRaisesRegex(TicketSummaryError, "3 попытки"):
            TicketHistorySummarizer(self.settings).summarize([])

        self.assertEqual(post.call_count, 3)
        self.assertEqual(sleep.call_count, 2)

    @patch("ispano.ticket_summary.requests.post")
    def test_rejects_empty_or_malformed_response(self, post: Mock) -> None:
        response = Mock()
        response.json.return_value = {"choices": []}
        post.return_value = response

        with patch("ispano.ticket_summary.time.sleep"):
            with self.assertRaises(TicketSummaryError):
                TicketHistorySummarizer(self.settings).summarize([])

    @patch("ispano.ticket_summary.requests.post")
    def test_accepts_openai_sse_response(self, post: Mock) -> None:
        response = Mock()
        response.json.side_effect = ValueError("not JSON")
        response.text = (
            'data: {"choices":[{"delta":{"content":"Устройство отправлено. "}}]}\n\n'
            'data: {"choices":[{"delta":{"content":"Ждём закрытия."}}]}\n\n'
            "data: [DONE]\n"
        )
        response.headers = {"Content-Type": "text/event-stream"}
        response.status_code = 200
        post.return_value = response

        self.assertEqual(
            TicketHistorySummarizer(self.settings).summarize([]),
            "Устройство отправлено. Ждём закрытия.",
        )
