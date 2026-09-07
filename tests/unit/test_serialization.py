from datetime import datetime
import unittest

from ispano.models import ExportItem
from ispano.serialization import serialize_legacy, serialize_v2


class SerializationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.item = ExportItem(
            ticket={
                "Id": 7,
                "Name": "Тест",
                "Created": "2026-09-03T10:00:00",
                "Changed": "2026-09-03T11:00:00",
                "ExecutorIds": "10, 11",
            },
            chat=[
                {
                    "id": 1,
                    "date": "2026-09-03T10:30:00",
                    "date_raw": "03.09.2026, 10:30",
                    "author": "Автор",
                    "text": "Текст",
                    "is_private": False,
                    "events": None,
                }
            ],
        )

    def test_legacy_shape_is_unchanged(self) -> None:
        self.assertEqual(
            serialize_legacy([self.item]),
            [{"ticket": self.item.ticket, "chat": self.item.chat}],
        )

    def test_v2_normalizes_dates_and_ids(self) -> None:
        payload = serialize_v2([self.item], datetime(2026, 9, 3, 9), "Europe/Moscow")
        self.assertEqual(payload["schema_version"], 2)
        self.assertEqual(payload["tickets"][0]["executor_ids"], [10, 11])
        self.assertEqual(payload["tickets"][0]["created_at"], "2026-09-03T10:00:00+03:00")
