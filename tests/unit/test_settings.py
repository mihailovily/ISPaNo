import os
from pathlib import Path
import unittest
from unittest.mock import patch

from ispano.settings import PROJECT_ROOT, ExportSettings, TicketSummarySettings


class OutputDirectoryTests(unittest.TestCase):
    def test_container_path_is_mapped_to_project_exports(self) -> None:
        with patch.dict(os.environ, {"OUTPUT_DIR": "/app/exports"}, clear=False):
            settings = ExportSettings.from_env()

        self.assertEqual(settings.output_dir, PROJECT_ROOT / "exports")

    def test_relative_path_is_resolved_from_project_root(self) -> None:
        with patch.dict(os.environ, {"OUTPUT_DIR": "custom-exports"}, clear=False):
            settings = ExportSettings.from_env()

        self.assertEqual(settings.output_dir, PROJECT_ROOT / "custom-exports")

    def test_explicit_absolute_path_is_preserved(self) -> None:
        absolute_path = str((Path(os.environ.get("TEMP", ".")) / "ispano-exports").resolve())
        with patch.dict(os.environ, {"OUTPUT_DIR": absolute_path}, clear=False):
            settings = ExportSettings.from_env()

        self.assertEqual(settings.output_dir, Path(absolute_path))


class TicketSummarySettingsTests(unittest.TestCase):
    def test_is_disabled_when_endpoint_or_model_is_missing(self) -> None:
        with patch.dict(
            os.environ,
            {"TICKET_SUMMARY_API_BASE_URL": "http://ai.test/v1", "TICKET_SUMMARY_MODEL": ""},
            clear=False,
        ):
            self.assertFalse(TicketSummarySettings.from_env().enabled)

    def test_loads_endpoint_model_and_optional_key(self) -> None:
        with patch.dict(
            os.environ,
            {
                "TICKET_SUMMARY_API_BASE_URL": "http://ai.test/v1/",
                "TICKET_SUMMARY_MODEL": "test-model",
                "TICKET_SUMMARY_API_KEY": "key",
            },
            clear=False,
        ):
            settings = TicketSummarySettings.from_env()

        self.assertTrue(settings.enabled)
        self.assertEqual(settings.api_base_url, "http://ai.test/v1")
        self.assertEqual(settings.model, "test-model")
        self.assertEqual(settings.api_key, "key")

    def test_loads_gigachat_defaults(self) -> None:
        with patch.dict(
            os.environ,
            {
                "TICKET_SUMMARY_PROVIDER": "gigachat",
                "TICKET_SUMMARY_MODEL": "GigaChat",
                "TICKET_SUMMARY_GIGACHAT_AUTHORIZATION_KEY": "authorization-key",
            },
            clear=True,
        ):
            settings = TicketSummarySettings.from_env()

        self.assertTrue(settings.enabled)
        self.assertEqual(settings.provider, "gigachat")
        self.assertEqual(settings.api_base_url, "https://api.giga.chat/v1")
        self.assertEqual(settings.gigachat_scope, "GIGACHAT_API_PERS")
        self.assertTrue(settings.gigachat_verify_ssl)

    def test_gigachat_requires_authorization_key(self) -> None:
        with patch.dict(
            os.environ,
            {"TICKET_SUMMARY_PROVIDER": "gigachat", "TICKET_SUMMARY_MODEL": "GigaChat"},
            clear=True,
        ):
            with self.assertRaisesRegex(ValueError, "AUTHORIZATION_KEY"):
                TicketSummarySettings.from_env()

    def test_rejects_invalid_gigachat_verify_ssl_value(self) -> None:
        with patch.dict(
            os.environ,
            {"TICKET_SUMMARY_GIGACHAT_VERIFY_SSL": "sometimes"},
            clear=True,
        ):
            with self.assertRaisesRegex(ValueError, "VERIFY_SSL"):
                TicketSummarySettings.from_env()
