"""OpenAI-compatible ticket-history summarization."""

from __future__ import annotations

import json
import time
from typing import Any

import requests

from .settings import TicketSummarySettings


class TicketSummaryError(RuntimeError):
    """The configured AI service could not produce a usable ticket status."""


class TicketHistorySummarizer:
    """Request a compact current ticket status from an OpenAI-compatible API."""

    max_attempts = 3
    max_status_length = 1000

    def __init__(self, settings: TicketSummarySettings) -> None:
        if not settings.enabled:
            raise ValueError("ИИ-суммаризация не настроена.")
        self.settings = settings

    def summarize(self, history: list[dict[str, Any]]) -> str:
        """Return a non-empty status, retrying transient transport/API failures."""
        last_error: Exception | None = None
        for attempt in range(1, self.max_attempts + 1):
            try:
                return self._request(history)
            except (requests.RequestException, ValueError, TicketSummaryError) as exc:
                last_error = exc
                if attempt < self.max_attempts:
                    time.sleep(attempt)
        raise TicketSummaryError(
            f"ИИ не вернул корректный статус за {self.max_attempts} попытки: {last_error}"
        ) from last_error

    def _request(self, history: list[dict[str, Any]]) -> str:
        headers = {"Content-Type": "application/json"}
        if self.settings.api_key:
            headers["Authorization"] = f"Bearer {self.settings.api_key}"
        payload = {
            "model": self.settings.model,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "Ты анализируешь историю заявки службы поддержки. Составь понятное "
                        "текущее состояние тикета на русском языке. Укажи, что уже сделано, "
                        "что происходит сейчас, чего ожидают или какой следующий шаг нужен. "
                        "Добавь существенный технический контекст из истории: названия "
                        "команд, систем, устройств, версий, документов или пунктов "
                        "руководства, если они помогают понять состояние. Не выдумывай факты "
                        "и не повторяй всю переписку. Верни только готовый текст без "
                        "заголовков и Markdown: обычно 2–6 связанных предложений, не более "
                        "1000 символов."
                    ),
                },
                {
                    "role": "user",
                    "content": "История тикета:\n" + json.dumps(history, ensure_ascii=False),
                },
            ],
            "temperature": 0.1,
            "stream": False,
        }
        response = requests.post(
            f"{self.settings.api_base_url}/chat/completions",
            headers=headers,
            json=payload,
            timeout=(10, 60),
        )
        response.raise_for_status()
        content = self._extract_content(response)
        if not isinstance(content, str) or not (status := content.strip()):
            raise TicketSummaryError("ИИ вернул пустой или некорректный статус.")
        return status[: self.max_status_length]

    def _extract_content(self, response: requests.Response) -> str:
        """Read regular JSON responses and OpenAI-compatible SSE streams."""
        try:
            data = response.json()
        except ValueError:
            return self._extract_sse_content(response)
        try:
            content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise TicketSummaryError("Ответ ИИ не содержит choices[0].message.content.") from exc
        return content

    @staticmethod
    def _extract_sse_content(response: requests.Response) -> str:
        chunks: list[str] = []
        for line in response.text.splitlines():
            if not line.startswith("data:"):
                continue
            raw_chunk = line.removeprefix("data:").strip()
            if not raw_chunk or raw_chunk == "[DONE]":
                continue
            try:
                payload = json.loads(raw_chunk)
                choice = payload["choices"][0]
                content = choice.get("delta", {}).get("content") or choice.get("message", {}).get("content")
            except (json.JSONDecodeError, KeyError, IndexError, TypeError):
                continue
            if isinstance(content, str):
                chunks.append(content)
        if chunks:
            return "".join(chunks)

        content_type = response.headers.get("Content-Type", "не указан")
        preview = " ".join(response.text.split())[:500]
        suffix = f" Тело ответа: {preview}" if preview else ""
        raise TicketSummaryError(
            f"Endpoint вернул не-JSON и не SSE (HTTP {response.status_code}, "
            f"Content-Type: {content_type}).{suffix}"
        )
