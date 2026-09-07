from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock, patch

from openpyxl import load_workbook

from ispano.intraservice.client import IntraserviceClient, IntraserviceResponseError
from ispano.intraservice.parsing import TicketCard, parse_task_list_ids, parse_ticket_card
from ispano.settings import IntraserviceSettings
from ispano.ticket_report import REPORT_HEADERS, TicketReportRow, load_partner_aliases, write_ticket_report


CARD_HTML = """
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

    def test_extracts_distinct_ticket_ids_in_response_order(self) -> None:
        html = '<a href="Task/view/20">20</a><a href="/Task/View/19">19</a><a href="Task/view/20">20</a>'
        self.assertEqual(parse_task_list_ids(html), [20, 19])


class TicketReportTests(unittest.TestCase):
    def test_alias_normalization_and_unknown_organization(self) -> None:
        with patch("ispano.ticket_report.files") as mocked_files:
            mocked_files.return_value.joinpath.return_value.read_text.return_value = '{"ООО \\\"Тест\\\"": "Тест"}'
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

    def test_project_partner_aliases_are_loaded(self) -> None:
        aliases = load_partner_aliases()
        self.assertEqual(aliases["ооо \"специальная интеграция\""], "СпецИнт")
        self.assertEqual(aliases["ооо система защиты данных"], "СЗД")

    def test_writes_copy_ready_workbook(self) -> None:
        row = TicketReportRow(20, "В работе", "Стандартная", "Партнер", datetime(2026, 9, 7, 11, 2))
        with TemporaryDirectory() as directory:
            path = write_ticket_report([row], Path(directory))
            workbook = load_workbook(path)
            sheet = workbook["Тикеты"]
            self.assertEqual(tuple(cell.value for cell in sheet[1]), REPORT_HEADERS)
            self.assertEqual(sheet["A2"].value, 20)
            self.assertIsNone(sheet["B2"].value)
            self.assertEqual(sheet["I2"].value, datetime(2026, 9, 7, 11, 2))


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
