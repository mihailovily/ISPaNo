import os
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock, patch

from openpyxl import load_workbook

from ispano.intraservice.client import IntraserviceClient, IntraserviceResponseError
from ispano.intraservice.parsing import TicketCard, parse_task_list_ids, parse_ticket_card
from ispano.settings import IntraserviceSettings
from ispano.ticket_report import (
    REPORT_HEADERS,
    TicketReportExporter,
    TicketReportRow,
    load_partner_aliases,
    load_customer_names,
    load_support_type_aliases,
    load_status_aliases,
    write_ticket_report,
)
from ispano.ticket_summary import TicketSummaryError


CARD_HTML = """
<span id="taskname">4581. Запрос обновления 6036 [ТестКлиент]</span>
<a href="/Task/index?tb_serviceid=27" title="Заявки на ТП 3-й линии в СПБ">Заявки на ТП 3-й линии в СПБ</a>
<span id="tasktypespan">Стандартный HSM</span>
<select id="statusid"><option>В работе</option><option selected>Требует уточнения</option></select>
<div id="creator">Создана: 4 сентября 2026 19:00 <a title='ООО «Тест»'>ООО «Тест»</a></div>
<div id="lifetimeshort"><div class="itemcomments"><span class="darkgrey">7 сентября, 11:02</span></div></div>
"""


class TicketCardParsingTests(unittest.TestCase):
    def test_parses_report_fields_from_ticket_page(self) -> None:
        card = parse_ticket_card(CARD_HTML, now=datetime(2026, 9, 7, 12))
        self.assertEqual(card.status, "Требует уточнения")
        self.assertEqual(card.support_type, "Заявки на ТП 3-й линии в СПБ")
        self.assertEqual(card.creator_organization, "ООО «Тест»")
        self.assertEqual(card.last_updated_at, datetime(2026, 9, 7, 11, 2))
        self.assertEqual(card.title, "4581. Запрос обновления 6036 [ТестКлиент]")

    def test_extracts_distinct_ticket_ids_in_response_order(self) -> None:
        html = '<a href="Task/view/20">20</a><a href="/Task/View/19">19</a><a href="Task/view/20">20</a>'
        self.assertEqual(parse_task_list_ids(html), [20, 19])


class TicketReportTests(unittest.TestCase):
    def test_alias_normalization_and_unknown_organization(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "partner_aliases.json"
            path.write_text('{"ООО \\\"Тест\\\"": "Тест"}', encoding="utf-8")
            with patch.dict(os.environ, {"PARTNER_ALIASES_PATH": str(path)}, clear=False):
                aliases = load_partner_aliases()
        card = parse_ticket_card(CARD_HTML, now=datetime(2026, 9, 7, 12))
        row = TicketReportRow.from_card(20, card, aliases)
        self.assertEqual(row.partner, "Тест")
        unknown = TicketReportRow.from_card(
            19,
            TicketCard("В работе", "Стандартная", "ООО Неизвестная", None),
            aliases,
        )
        self.assertEqual(unknown.partner, "ООО Неизвестная")

    def test_partner_aliases_are_loaded_from_private_file(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "partner_aliases.json"
            path.write_text('{"ООО Пример": "Пример"}', encoding="utf-8")
            with patch.dict(os.environ, {"PARTNER_ALIASES_PATH": str(path)}, clear=False):
                aliases = load_partner_aliases()

        self.assertEqual(aliases["ооо пример"], "Пример")

    def test_support_type_alias_is_applied(self) -> None:
        aliases = load_support_type_aliases()
        row = TicketReportRow.from_card(
            20,
            TicketCard("В работе", "ТП HSM Стандартная", None, None),
            {},
            aliases,
        )
        self.assertEqual(row.support_type, "Стандартная")

    def test_status_alias_is_applied(self) -> None:
        aliases = load_status_aliases()
        row = TicketReportRow.from_card(
            20,
            TicketCard("Требуется уточнение", "Стандартная", None, None),
            {},
            status_aliases=aliases,
        )
        self.assertEqual(row.status, "Требует уточнения")

    def test_title_fields_extract_description_and_customer_case_insensitively(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "customer_names.json"
            path.write_text('["Отличный Банк", "Другой Банк"]', encoding="utf-8")
            with patch.dict(os.environ, {"CUSTOMER_NAMES_PATH": str(path)}, clear=False):
                customer_names = load_customer_names()
        row = TicketReportRow.from_card(
            4581,
            TicketCard(
                "В работе",
                "Стандартная",
                None,
                None,
                "4581. Запрос обновления 6036 [OТЛИЧНЫЙ БАНК]",
            ),
            {},
            customer_names=customer_names,
        )
        self.assertEqual(row.description, "Запрос обновления 6036")
        self.assertEqual(row.customer, "Отличный Банк")

        uppercase_customer = TicketReportRow.from_card(
            4582,
            TicketCard("В работе", "Стандартная", None, None, "4582. Ошибка [ДРУГОЙ БАНК]"),
            {},
            customer_names=customer_names,
        )
        self.assertEqual(uppercase_customer.customer, "Другой Банк")

        abbreviated_customer = TicketReportRow.from_card(
            4583,
            TicketCard("В работе", "Стандартная", None, None, "4583. Ошибка [ДРУГОЙ]"),
            {},
            customer_names=customer_names,
        )
        self.assertEqual(abbreviated_customer.customer, "Другой Банк")

    def test_writes_copy_ready_workbook(self) -> None:
        row = TicketReportRow(
            20,
            "В работе",
            "Стандартная",
            "Партнер",
            datetime(2026, 9, 7, 11, 2),
            "Запрос обновления 6036",
            "ТестКлиент",
        )
        with TemporaryDirectory() as directory:
            path = write_ticket_report([row], Path(directory))
            workbook = load_workbook(path)
            sheet = workbook["Тикеты"]
            self.assertEqual(tuple(cell.value for cell in sheet[1]), REPORT_HEADERS)
            self.assertEqual(sheet["A2"].value, 20)
            self.assertIsNone(sheet["B2"].value)
            self.assertEqual(sheet["E2"].value, "Запрос обновления 6036")
            self.assertEqual(sheet["G2"].value, "ТестКлиент")
            self.assertEqual(sheet["I2"].value, datetime(2026, 9, 7, 11, 2))

    def test_writes_current_ai_status_to_eighth_column(self) -> None:
        row = TicketReportRow(20, None, None, None, None, current_status="Ведётся поиск решения.")
        self.assertEqual(row.values()[7], "Ведётся поиск решения.")


class TicketReportAiTests(unittest.TestCase):
    @patch("ispano.ticket_report.load_customer_names", return_value={})
    @patch("ispano.ticket_report.load_status_aliases", return_value={})
    @patch("ispano.ticket_report.load_support_type_aliases", return_value={})
    @patch("ispano.ticket_report.load_partner_aliases", return_value={})
    @patch("ispano.ticket_report.IntraserviceClient")
    def test_passes_parsed_history_to_ai_and_records_its_status(
        self, client_cls: Mock, *_: Mock
    ) -> None:
        client = client_cls.return_value.__enter__.return_value
        client.list_ticket_ids_descending.return_value = [20]
        client.get_ticket_page.return_value = CARD_HTML
        summarizer = Mock()
        summarizer.summarize.return_value = "Устройство отправлено в сервис."
        settings = IntraserviceSettings("https://sd.example.test", "login", "password", 0, (1, 1), 1)

        rows, _ = TicketReportExporter(settings, "login", "password", summarizer).export(20)

        self.assertEqual(rows[0].current_status, "Устройство отправлено в сервис.")
        self.assertEqual(summarizer.summarize.call_count, 1)

    @patch("ispano.ticket_report.load_customer_names", return_value={})
    @patch("ispano.ticket_report.load_status_aliases", return_value={})
    @patch("ispano.ticket_report.load_support_type_aliases", return_value={})
    @patch("ispano.ticket_report.load_partner_aliases", return_value={})
    @patch("ispano.ticket_report.IntraserviceClient")
    def test_continues_with_empty_status_when_ai_fails(
        self, client_cls: Mock, *_: Mock
    ) -> None:
        client = client_cls.return_value.__enter__.return_value
        client.list_ticket_ids_descending.return_value = [20]
        client.get_ticket_page.return_value = CARD_HTML
        summarizer = Mock()
        summarizer.summarize.side_effect = TicketSummaryError("offline")
        messages: list[str] = []
        settings = IntraserviceSettings("https://sd.example.test", "login", "password", 0, (1, 1), 1)

        rows, _ = TicketReportExporter(settings, "login", "password", summarizer).export(20, messages.append)

        self.assertEqual(rows[0].current_status, None)
        self.assertTrue(any("тикет 20" in message for message in messages))


class TicketListClientTests(unittest.TestCase):
    def setUp(self) -> None:
        self.settings = IntraserviceSettings(
            base_url="https://sd.example.test",
            login="login",
            password="password",
            request_delay=0.01,
            request_timeout=(1, 1),
            max_pages=1,
        )

    def test_stops_at_inclusive_boundary_in_descending_list(self) -> None:
        client = IntraserviceClient(self.settings, "login", "password")
        response = Mock()
        response.text = '<a href="/Task/View/22">22</a><a href="/Task/View/21">21</a><a href="/Task/View/20">20</a>'
        client.session.post = Mock(return_value=response)

        self.assertEqual(client.list_ticket_ids_descending(21), [22, 21])
        client.session.post.assert_called_once_with(
            "https://sd.example.test/task/list",
            data={"tb_orderby": "Id desc", "nolayout": "true", "totalcount": "false", "count": "0"},
            headers={"Referer": "https://sd.example.test/Task", "X-Requested-With": "XMLHttpRequest"},
            timeout=(1, 1),
        )

    def test_fails_without_creating_an_incomplete_range(self) -> None:
        client = IntraserviceClient(self.settings, "login", "password")
        response = Mock()
        response.text = '<a href="/Task/View/22">22</a><a href="/Task/View/21">21</a>'
        client.session.post = Mock(return_value=response)

        with self.assertRaisesRegex(IntraserviceResponseError, "20 не найден"):
            client.list_ticket_ids_descending(20)
