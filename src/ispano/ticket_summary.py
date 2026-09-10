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
    max_status_length = 600

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
                        "Ты анализируешь историю заявки службы поддержки.  В системе видны заявки, получаемые первой, второй и третьей линией техподдержки. Для первой и второй линии мы являемся разработчиком, производителем и тд. В разговоре с клиентом они ссылаются именно на нас."
                        "Заявки, имеющие в себе тип Заявки на ТП 3-й линии в СПБ адресованы непосредственно нам.  "
                        "Составь понятное текущее состояние тикета на русском языке с учетом перечисленных особенностей: проблему или результат, текущее "
                        "действие и действительный следующий шаг. Ты составляешь отчет для тьетьей линии техподдержки, поэтому читывай это при обработке. В случае с выполнением задач, более корректно писать «запросили», "
                        "«предоставили», «зафиксировали»; если что-то отправлено производителю, то это отправлено нам, как правило "
                        "Строго соблюдай хронологию по полям date: последнее подтверждённое "
                        "событие важнее прежних планов и вопросов. Не меняй направление действий: "
                        "«передать/отправить на диагностику производителю, нам или на завод» — "
                        "это передача изделия нам; «отправлено обратно заказчику/клиенту» — "
                        "это отправка изделия от ГК СПБ (от нас) заказчику. "
                        "Приоритет — итог для тикета: обновление запрошено или предоставлено, "
                        "функция не поддерживается, решение найдено либо ожидаются данные. Если идет речь об общении со сторонним вендором (например, T8, то указывай его, т.к это важно для понимания контекста)."
                        "Не описывай последовательность обновлений, совместимость версий, "
                        "инструкции и прочие исторические детали, если они не являются текущим "
                        "блокером. Не называй специалистов, авторов сообщений, роли, номера "
                        "обращений и формальные статусы SD, если без них не теряется смысл. "
                        "Не пересказывай диалог, не добавляй несущественные подробности и не "
                        "выдумывай факты. Верни только готовый текст без заголовков и Markdown: "
                        "обычно 1–3 связанных предложения, не более 400 символов, если можешь более кратко, то это приветствуется.\n\n"
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
