from __future__ import annotations

import importlib.util
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from ispano import cli


SETUP_PATH = Path(__file__).resolve().parents[2] / "setup.py"
SPEC = importlib.util.spec_from_file_location("ispano_setup", SETUP_PATH)
assert SPEC and SPEC.loader
setup = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(setup)


ENV_TEMPLATE = """# Конфигурация\nINTRASERVICE_BASE_URL=https://sd.example.test\nINTRASERVICE_LOGIN=your_login\nINTRASERVICE_PASSWORD=your_password\nTELEGRAM_BOT_TOKEN=123456:ABC-your-token\nALLOWED_TELEGRAM_USER_IDS=123456789,987654321\nREQUEST_DELAY=0.4\nCUSTOM_VALUE=keep\n"""


class SetupTests(unittest.TestCase):
    def _inputs(self, *values: str):
        iterator = iter(values)
        return lambda _prompt: next(iterator)

    def test_creates_env_and_clears_unused_telegram_secrets(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / ".env.example").write_text(ENV_TEMPLATE, encoding="utf-8")
            output = StringIO()
            with patch("sys.stdout", output):
                setup.run_setup(root, self._inputs("1", "https://sd.local", "alice", "secret"))

            env = (root / ".env").read_text(encoding="utf-8")

        self.assertIn("INTRASERVICE_BASE_URL=https://sd.local", env)
        self.assertIn("INTRASERVICE_LOGIN=alice", env)
        self.assertIn("INTRASERVICE_PASSWORD=secret", env)
        self.assertIn("TELEGRAM_BOT_TOKEN=", env)
        self.assertIn("ALLOWED_TELEGRAM_USER_IDS=", env)
        self.assertIn("REQUEST_DELAY=0.4", env)
        self.assertIn("poetry run ispano export", output.getvalue())

    def test_updates_existing_env_without_exposing_secret_values(self) -> None:
        existing = "# Keep this comment\nINTRASERVICE_BASE_URL=https://old.example\nINTRASERVICE_LOGIN=old-user\nINTRASERVICE_PASSWORD=old-secret\nEXTRA_SETTING=preserve\n"
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / ".env").write_text(existing, encoding="utf-8")
            prompts: list[str] = []
            responses = iter(("1", "", "new-user", ""))
            with patch("sys.stdout", StringIO()):
                setup.run_setup(root, lambda prompt: (prompts.append(prompt), next(responses))[1])
            env = (root / ".env").read_text(encoding="utf-8")

        self.assertIn("# Keep this comment", env)
        self.assertIn("INTRASERVICE_BASE_URL=https://old.example", env)
        self.assertIn("INTRASERVICE_LOGIN=new-user", env)
        self.assertIn("INTRASERVICE_PASSWORD=old-secret", env)
        self.assertIn("EXTRA_SETTING=preserve", env)
        self.assertNotIn("old-secret", "\n".join(prompts))


class FirstRunHintTests(unittest.TestCase):
    def test_command_without_env_prints_setup_hint(self) -> None:
        with TemporaryDirectory() as directory:
            stderr = StringIO()
            with patch.object(cli, "PROJECT_ROOT", Path(directory)), patch("sys.stderr", stderr):
                exit_code = cli.main(["export"])

        self.assertEqual(exit_code, 2)
        self.assertIn("python setup.py", stderr.getvalue())

    def test_help_is_available_without_env(self) -> None:
        with TemporaryDirectory() as directory:
            with (
                patch.object(cli, "PROJECT_ROOT", Path(directory)),
                patch("sys.stdout", StringIO()),
                self.assertRaises(SystemExit) as raised,
            ):
                cli.main(["--help"])

        self.assertEqual(raised.exception.code, 0)
