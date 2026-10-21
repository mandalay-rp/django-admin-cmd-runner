"""Тесты management-команд ``command_runner``."""

from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.test import SimpleTestCase

_DEMO_SLEEP = "command_runner.management.commands.demo_long_command.time.sleep"


class DemoLongCommandTests(SimpleTestCase):
    """Тесты :class:`demo_long_command.Command`."""

    @patch(_DEMO_SLEEP)
    def test_runs_steps(self, mock_sleep) -> None:
        """Команда выполняет указанное число шагов и пишет их в stdout."""
        out = StringIO()
        call_command("demo_long_command", "--steps=3", stdout=out)
        output = out.getvalue()

        self.assertIn("Шаг 1 из 3", output)
        self.assertIn("Шаг 2 из 3", output)
        self.assertIn("Шаг 3 из 3", output)
        self.assertIn("Готово", output)
        self.assertEqual(mock_sleep.call_count, 3)

    @patch(_DEMO_SLEEP)
    def test_default_steps(self, mock_sleep) -> None:
        """По умолчанию выполняется 20 шагов."""
        call_command("demo_long_command", stdout=StringIO())
        self.assertEqual(mock_sleep.call_count, 20)

    @patch(_DEMO_SLEEP)
    def test_min_steps(self, mock_sleep) -> None:
        """``--steps 0`` приводится к 1."""
        call_command("demo_long_command", "--steps=0", stdout=StringIO())
        self.assertEqual(mock_sleep.call_count, 1)
