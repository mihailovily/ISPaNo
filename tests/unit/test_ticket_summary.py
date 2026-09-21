from __future__ import annotations

import time
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
        prompt = kwargs["json"]["messages"][0]["content"]
        self.assertIn("Заявки на ТП 3-й линии", prompt)
        self.assertIn("последовательность обновлений", prompt)
        self.assertIn("последнее подтверждённое событие", prompt)
        self.assertIn("отправка изделия от ГК СПБ", prompt)

    @patch("ispano.ticket_summary.requests.post")
    def test_summarizes_short_description_with_normalized_response(self, post: Mock) -> None:
        response = Mock()
        response.json.return_value = {
            "choices": [
                {
                    "message": {
                        "content": "  - При обновлении возникает ошибка.\nНужны логи.  "
                    }
                }
            ]
        }
        post.return_value = response

        result = TicketHistorySummarizer(self.settings).summarize_description(
            "4581. Ошибка обновления", "После загрузки файла возникает ошибка."
        )

        self.assertEqual(result, "При обновлении возникает ошибка.")
        messages = post.call_args.kwargs["json"]["messages"]
        self.assertIn("Верни от двух до шести слов", messages[0]["content"])
        self.assertIn("4581. Ошибка обновления", messages[1]["content"])
        self.assertIn("После загрузки файла", messages[1]["content"])

    @patch("ispano.ticket_summary.requests.post")
    def test_description_without_source_does_not_call_endpoint(self, post: Mock) -> None:
        with self.assertRaisesRegex(TicketSummaryError, "нет заголовка"):
            TicketHistorySummarizer(self.settings).summarize_description(None, "  ")

        post.assert_not_called()

    @patch("ispano.ticket_summary.requests.post")
    def test_limits_description_to_400_characters(self, post: Mock) -> None:
        response = Mock()
        response.json.return_value = {
            "choices": [{"message": {"content": "а" * 500}}]
        }
        post.return_value = response

        result = TicketHistorySummarizer(self.settings).summarize_description(
            "Ошибка", "Подробности"
        )

        self.assertEqual(len(result), 400)

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
    def test_limits_result_to_600_characters(self, post: Mock) -> None:
        response = Mock()
        response.json.return_value = {"choices": [{"message": {"content": "а" * 800}}]}
        post.return_value = response

        self.assertEqual(len(TicketHistorySummarizer(self.settings).summarize([])), 600)

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

    @patch("ispano.ticket_summary.uuid.uuid4", return_value="request-uuid")
    @patch("ispano.ticket_summary.requests.post")
    def test_gigachat_fetches_and_caches_oauth_token(self, post: Mock, _uuid: Mock) -> None:
        oauth_response = Mock()
        oauth_response.json.return_value = {
            "access_token": "oauth-token",
            "expires_at": time.time() + 3600,
        }
        completion_response = Mock()
        completion_response.json.return_value = {
            "choices": [{"message": {"content": "Ожидаются данные."}}]
        }
        post.side_effect = [oauth_response, completion_response, completion_response]
        settings = TicketSummarySettings(
            "https://api.giga.chat/v1",
            "GigaChat",
            None,
            provider="gigachat",
            gigachat_authorization_key="authorization-key",
        )

        summarizer = TicketHistorySummarizer(settings)
        self.assertEqual(summarizer.summarize([]), "Ожидаются данные.")
        self.assertEqual(summarizer.summarize([]), "Ожидаются данные.")

        self.assertEqual(post.call_count, 3)
        oauth_kwargs = post.call_args_list[0].kwargs
        self.assertEqual(post.call_args_list[0].args[0], settings.gigachat_oauth_url)
        self.assertEqual(oauth_kwargs["headers"]["Authorization"], "Basic authorization-key")
        self.assertEqual(oauth_kwargs["headers"]["RqUID"], "request-uuid")
        self.assertEqual(oauth_kwargs["data"], {"scope": "GIGACHAT_API_PERS"})
        self.assertTrue(oauth_kwargs["verify"])
        completion_kwargs = post.call_args_list[1].kwargs
        self.assertEqual(completion_kwargs["headers"]["Authorization"], "Bearer oauth-token")
        self.assertTrue(completion_kwargs["verify"])

    @patch("ispano.ticket_summary.requests.post")
    def test_gigachat_refreshes_expired_oauth_token(self, post: Mock) -> None:
        expired = Mock()
        expired.json.return_value = {"access_token": "old", "expires_at": time.time() - 1}
        fresh = Mock()
        fresh.json.return_value = {"access_token": "new", "expires_at": time.time() + 3600}
        completion = Mock()
        completion.json.return_value = {"choices": [{"message": {"content": "Готово."}}]}
        post.side_effect = [expired, completion, fresh, completion]
        settings = TicketSummarySettings(
            "https://api.giga.chat/v1", "GigaChat", None, provider="gigachat",
            gigachat_authorization_key="key",
        )

        summarizer = TicketHistorySummarizer(settings)
        summarizer.summarize([])
        summarizer.summarize([])

        self.assertEqual(post.call_count, 4)
        self.assertEqual(post.call_args_list[3].kwargs["headers"]["Authorization"], "Bearer new")

    @patch("ispano.ticket_summary.requests.post")
    def test_gigachat_oauth_failure_has_clear_error(self, post: Mock) -> None:
        post.side_effect = requests.ConnectionError("certificate verify failed")
        settings = TicketSummarySettings(
            "https://api.giga.chat/v1", "GigaChat", None, provider="gigachat",
            gigachat_authorization_key="key",
        )

        with patch("ispano.ticket_summary.time.sleep"):
            with self.assertRaisesRegex(TicketSummaryError, "OAuth-токен GigaChat"):
                TicketHistorySummarizer(settings).summarize([])

    @patch("ispano.ticket_summary.requests.post")
    def test_gigachat_verify_ssl_false_applies_to_oauth_and_completion(self, post: Mock) -> None:
        oauth = Mock()
        oauth.json.return_value = {"access_token": "token", "expires_at": time.time() + 3600}
        completion = Mock()
        completion.json.return_value = {"choices": [{"message": {"content": "Готово."}}]}
        post.side_effect = [oauth, completion]
        settings = TicketSummarySettings(
            "https://api.giga.chat/v1", "GigaChat", None, provider="gigachat",
            gigachat_authorization_key="key", gigachat_verify_ssl=False,
        )

        TicketHistorySummarizer(settings).summarize([])

        self.assertFalse(post.call_args_list[0].kwargs["verify"])
        self.assertFalse(post.call_args_list[1].kwargs["verify"])

    @patch("ispano.ticket_summary.requests.post")
    def test_generic_endpoint_does_not_receive_gigachat_tls_option(self, post: Mock) -> None:
        response = Mock()
        response.json.return_value = {"choices": [{"message": {"content": "Готово."}}]}
        post.return_value = response

        TicketHistorySummarizer(self.settings).summarize([])

        self.assertNotIn("verify", post.call_args.kwargs)
