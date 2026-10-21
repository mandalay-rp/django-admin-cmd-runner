"""Тесты модуля :mod:`command_runner.forms`."""

from django.test import SimpleTestCase, override_settings

from command_runner.forms import StartCommandForm


class CleanCommandTests(SimpleTestCase):
    """Тесты валидации имени команды."""

    @override_settings(COMMAND_RUNNER_COMMANDS=[{"name": "demo_long_command"}])
    def test_allowed(self) -> None:
        """Разрешённая команда проходит валидацию."""
        form = StartCommandForm({"command": "demo_long_command", "args": ""})
        self.assertTrue(form.is_valid(), form.errors)

    @override_settings(COMMAND_RUNNER_COMMANDS=[{"name": "demo_long_command"}])
    def test_not_allowed(self) -> None:
        """Неразрешённая команда отклоняется."""
        form = StartCommandForm({"command": "rm_rf", "args": ""})
        self.assertFalse(form.is_valid())
        self.assertIn("command", form.errors)


class CleanArgsTests(SimpleTestCase):
    """Тесты разбора строки аргументов."""

    @override_settings(COMMAND_RUNNER_COMMANDS=[{"name": "cmd"}])
    def test_bad_quotes(self) -> None:
        """Некорректные кавычки дают ошибку валидации."""
        form = StartCommandForm({"command": "cmd", "args": '"unclosed'})
        self.assertFalse(form.is_valid())
        self.assertIn("args", form.errors)


class SplitArgsKwargsTests(SimpleTestCase):
    """Тесты :meth:`StartCommandForm.split_args_kwargs`."""

    def _form(self, args: str) -> StartCommandForm:
        """Возвращает валидную форму с указанными аргументами."""
        form = StartCommandForm({"command": "cmd", "args": args})
        form.is_valid()
        return form

    @override_settings(COMMAND_RUNNER_COMMANDS=[{"name": "cmd"}])
    def test_empty(self) -> None:
        """Пустая строка → пустые позиционные и kwargs."""
        self.assertEqual(self._form("").split_args_kwargs(), ([], {}))

    @override_settings(COMMAND_RUNNER_COMMANDS=[{"name": "cmd"}])
    def test_positional(self) -> None:
        """Только позиционные аргументы."""
        self.assertEqual(
            self._form("a b c").split_args_kwargs(),
            (["a", "b", "c"], {}),
        )

    @override_settings(COMMAND_RUNNER_COMMANDS=[{"name": "cmd"}])
    def test_kwargs_with_space(self) -> None:
        """``--key value`` → kwarg."""
        self.assertEqual(
            self._form("--steps 5").split_args_kwargs(),
            ([], {"steps": "5"}),
        )

    @override_settings(COMMAND_RUNNER_COMMANDS=[{"name": "cmd"}])
    def test_kwargs_with_equals(self) -> None:
        """``--key=value`` → kwarg."""
        self.assertEqual(
            self._form("--steps=5").split_args_kwargs(),
            ([], {"steps": "5"}),
        )

    @override_settings(COMMAND_RUNNER_COMMANDS=[{"name": "cmd"}])
    def test_flag(self) -> None:
        """``--flag`` без значения → ``True``."""
        self.assertEqual(
            self._form("--verbose").split_args_kwargs(),
            ([], {"verbose": True}),
        )

    @override_settings(COMMAND_RUNNER_COMMANDS=[{"name": "cmd"}])
    def test_quoted_value(self) -> None:
        """Значения с пробелами можно брать в кавычки."""
        self.assertEqual(
            self._form('--name "Hello World"').split_args_kwargs(),
            ([], {"name": "Hello World"}),
        )

    @override_settings(COMMAND_RUNNER_COMMANDS=[{"name": "cmd"}])
    def test_double_dash(self) -> None:
        """Всё после ``--`` считается позиционным."""
        self.assertEqual(
            self._form("-- --literal").split_args_kwargs(),
            (["--literal"], {}),
        )

    @override_settings(COMMAND_RUNNER_COMMANDS=[{"name": "cmd"}])
    def test_mixed(self) -> None:
        """Комбинация позиционных и именованных аргументов."""
        self.assertEqual(
            self._form("pos1 --steps 5 pos2 --flag").split_args_kwargs(),
            (["pos1", "pos2"], {"steps": "5", "flag": True}),
        )
