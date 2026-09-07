from datetime import datetime
import unittest

from ispano.intraservice.parsing import (
    infer_comment_datetime,
    parse_dot_datetime,
    parse_ticket_history,
)


class ParsingTests(unittest.TestCase):
    def test_parse_dot_datetime_accepts_optional_seconds(self) -> None:
        self.assertEqual(parse_dot_datetime("03.09.2026 14:15"), datetime(2026, 9, 3, 14, 15))
        self.assertEqual(
            parse_dot_datetime("03.09.2026 14:15:16"), datetime(2026, 9, 3, 14, 15, 16)
        )

    def test_infer_comment_year_is_deterministic(self) -> None:
        result = infer_comment_datetime(
            31, 12, 23, 30, datetime(2025, 1, 1), datetime(2026, 1, 2), datetime(2026, 1, 2)
        )
        self.assertEqual(result, datetime(2025, 12, 31, 23, 30))

    def test_html_parser_uses_text_values_and_preserves_private_flag(self) -> None:
        html = """
        <div id="lifetimeshort">
          <div class="itemcomments">
            <span id="link42"></span>
            <span class="darkgrey">05.05.2023, 12:56</span>
            <span class="lifetime-user">Иван</span>
            <div class="comment private"><pre>&lt;script&gt;alert(1)&lt;/script&gt;</pre></div>
            <p class="lifetimedetails">Событие</p>
          </div>
        </div>
        """
        result = parse_ticket_history(html, None, None)
        self.assertEqual(result[0]["id"], 42)
        self.assertEqual(result[0]["text"], "<script>alert(1)</script>")
        self.assertTrue(result[0]["is_private"])
