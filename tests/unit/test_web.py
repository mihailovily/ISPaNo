from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from time import sleep
import unittest
from unittest.mock import patch
import os

import bcrypt
from fastapi.testclient import TestClient

from ispano.settings import (
    AppSettings,
    ExportSettings,
    IntraserviceSettings,
    TicketSummarySettings,
    WebSettings,
)
from ispano.web.app import create_app
from ispano.web.jobs import JobManager


class JobManagerTests(unittest.TestCase):
    def test_runs_jobs_in_submission_order(self) -> None:
        manager = JobManager()
        order: list[str] = []
        with TemporaryDirectory() as directory:
            first_path = Path(directory) / "one.json"
            second_path = Path(directory) / "two.json"

            def first(report):
                order.append("first")
                report("first progress")
                first_path.write_text("{}", encoding="utf-8")
                return first_path

            def second(report):
                order.append("second")
                second_path.write_text("{}", encoding="utf-8")
                return second_path

            first_job = manager.submit("json", first)
            second_job = manager.submit("report", second)
            for _ in range(50):
                if manager.get(second_job.id).status == "succeeded":
                    break
                sleep(0.01)

        self.assertEqual(order, ["first", "second"])
        self.assertEqual(manager.get(first_job.id).progress, ["first progress"])
        self.assertEqual(manager.get(second_job.id).status, "succeeded")


class WebSettingsTests(unittest.TestCase):
    def test_rejects_non_bcrypt_hash_and_short_session_secret(self) -> None:
        with patch.dict(
            os.environ,
            {
                "WEB_USERNAME": "admin",
                "WEB_PASSWORD_HASH": "plaintext",
                "WEB_SESSION_SECRET": "short",
            },
            clear=False,
        ):
            with self.assertRaisesRegex(ValueError, "bcrypt"):
                WebSettings.from_env()


class WebApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = TemporaryDirectory()
        password_hash = bcrypt.hashpw(b"secret", bcrypt.gensalt()).decode()
        self.settings = AppSettings(
            intraservice=IntraserviceSettings("https://sd.example", "login", "password", 0.1, (1, 1), 1),
            export=ExportSettings(Path(self.directory.name), 24, "Europe/Moscow"),
            ticket_summary=TicketSummarySettings(None, None, None),
            web=WebSettings("admin", password_hash, "x" * 32, "127.0.0.1", 8000),
        )
        self.client = TestClient(create_app(self.settings))

    def tearDown(self) -> None:
        self.directory.cleanup()

    def _login(self) -> str:
        response = self.client.post("/api/login", json={"username": "admin", "password": "secret"})
        self.assertEqual(response.status_code, 200)
        return self.client.get("/api/session").json()["csrf"]

    def test_pages_and_api_require_login(self) -> None:
        self.assertEqual(self.client.get("/").status_code, 401)
        self.assertEqual(self.client.post("/api/jobs/json", json={}).status_code, 401)
        self._login()
        self.assertEqual(self.client.get("/").status_code, 200)

    def test_json_job_validates_csrf_and_returns_download(self) -> None:
        csrf = self._login()
        self.assertEqual(
            self.client.post("/api/jobs/json", json={"since": "03.09.2026"}).status_code,
            403,
        )
        output = Path(self.directory.name) / "result.json"
        output.write_text('{"schema_version":2,"tickets":[]}', encoding="utf-8")
        with patch("ispano.web.app.create_json_export", return_value=({}, output)):
            response = self.client.post(
                "/api/jobs/json",
                headers={"X-CSRF-Token": csrf},
                json={"since": "03.09.2026"},
            )
            self.assertEqual(response.status_code, 200)
            job_id = response.json()["id"]
            for _ in range(50):
                status = self.client.get(f"/api/jobs/{job_id}").json()
                if status["status"] == "succeeded":
                    break
                sleep(0.01)

        self.assertEqual(status["status"], "succeeded")
        self.assertEqual(self.client.get(status["download_url"]).status_code, 200)

    def test_report_rejects_invalid_input_and_unconfigured_ai(self) -> None:
        csrf = self._login()
        headers = {"X-CSRF-Token": csrf}
        self.assertEqual(
            self.client.post("/api/jobs/report", headers=headers, json={"ticket_id": 0}).status_code,
            422,
        )
        self.assertEqual(
            self.client.post(
                "/api/jobs/report", headers=headers, json={"ticket_id": 20, "use_ai": True}
            ).status_code,
            422,
        )
