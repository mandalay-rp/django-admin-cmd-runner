"""Тесты модуля :mod:`command_runner.registry`."""

from django.test import SimpleTestCase, override_settings

from command_runner.registry import get_available_commands


class GetAvailableCommandsTests(SimpleTestCase):
    """Тесты нормализации ``COMMAND_RUNNER_COMMANDS``."""

    @override_settings(COMMAND_RUNNER_COMMANDS=[])
    def test_empty(self) -> None:
        """Пустой список команд → пустой результат."""
        self.assertEqual(get_available_commands(), [])

    @override_settings(COMMAND_RUNNER_COMMANDS=["cmd_a", "cmd_b"])
    def test_strings(self) -> None:
        """Строки нормализуются в словари с пустым ``args_help``."""
        result = get_available_commands()
        self.assertEqual(
            result,
            [
                {"name": "cmd_a", "label": "cmd_a", "args_help": ""},
                {"name": "cmd_b", "label": "cmd_b", "args_help": ""},
            ],
        )

    @override_settings(
        COMMAND_RUNNER_COMMANDS=[
            {"name": "cmd_a"},
            {"name": "cmd_b", "label": "B", "args_help": "--x"},
        ]
    )
    def test_dicts(self) -> None:
        """Словари дополняются дефолтными ``label`` и ``args_help``."""
        result = get_available_commands()
        self.assertEqual(
            result,
            [
                {"name": "cmd_a", "label": "cmd_a", "args_help": ""},
                {"name": "cmd_b", "label": "B", "args_help": "--x"},
            ],
        )
