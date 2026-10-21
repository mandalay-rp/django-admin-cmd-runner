"""Тесты модуля :mod:`admin_cmd_runner.jobs`."""

from unittest.mock import patch

from admin_cmd_runner import store
from admin_cmd_runner.jobs import _coerce_kwargs, execute_command
from admin_cmd_runner.management.commands.demo_long_command import (
    Command as DemoCommand,
)

from .base import CacheTestCase

# Путь до time.sleep в демо-команде — чтобы не ждать в тестах.
_DEMO_SLEEP = "admin_cmd_runner.management.commands.demo_long_command.time.sleep"


class CoerceKwargsTests(CacheTestCase):
    """Тесты :func:`_coerce_kwargs`."""

    def test_empty(self) -> None:
        """Пустой ``kwargs`` → пустой dict."""
        self.assertEqual(_coerce_kwargs("demo_long_command", {}), {})

    def test_int_coercion(self) -> None:
        """Строка приводится к ``int`` по ``type=int``."""
        result = _coerce_kwargs("demo_long_command", {"steps": "5"})
        self.assertEqual(result, {"steps": 5})
        self.assertIsInstance(result["steps"], int)

    def test_already_int(self) -> None:
        """Значение нужного типа не переприводится."""
        result = _coerce_kwargs("demo_long_command", {"steps": 5})
        self.assertEqual(result, {"steps": 5})

    def test_bad_int_falls_back(self) -> None:
        """Некорректное значение остаётся как есть."""
        result = _coerce_kwargs("demo_long_command", {"steps": "abc"})
        self.assertEqual(result, {"steps": "abc"})

    def test_unknown_key(self) -> None:
        """Неизвестный ключ передаётся без изменений."""
        result = _coerce_kwargs("demo_long_command", {"unknown": "value"})
        self.assertEqual(result, {"unknown": "value"})

    def test_unknown_command(self) -> None:
        """Неизвестная команда → kwargs без изменений."""
        result = _coerce_kwargs("nonexistent_xyz", {"steps": "5"})
        self.assertEqual(result, {"steps": "5"})


class ExecuteCommandTests(CacheTestCase):
    """Тесты :func:`execute_command`."""

    def test_skipped_without_state(self) -> None:
        """Без созданного состояния команда не выполняется."""
        result = execute_command("missing", "demo_long_command")
        self.assertEqual(result["status"], "skipped")

    def test_success(self) -> None:
        """Успешное выполнение переводит состояние в ``success`` и пишет лог."""
        run_id = "run-1"
        store.create_state(run_id, "demo_long_command", [])

        with patch(_DEMO_SLEEP):
            result = execute_command(
                run_id,
                "demo_long_command",
                args=[],
                kwargs={"steps": "2"},
            )

        self.assertEqual(result["status"], "success")
        state = store.get_state(run_id)
        self.assertEqual(state["status"], "success")
        self.assertIsNotNone(state["finished_at"])

        messages = [i["msg"] for i in store.get_log(run_id)]
        self.assertTrue(any("Шаг 1" in m for m in messages))
        self.assertTrue(any("Готово" in m for m in messages))

    def test_stdout_lines_marked_as_stdout(self) -> None:
        """Строки, записанные в ``self.stdout``, попадают в лог как ``stdout``."""
        run_id = "run-1"
        store.create_state(run_id, "demo_long_command", [])

        with patch(_DEMO_SLEEP):
            execute_command(
                run_id,
                "demo_long_command",
                args=[],
                kwargs={"steps": "2"},
            )

        lines = store.get_log(run_id)
        for line in lines:
            self.assertEqual(line["stream"], store.STREAM_STDOUT)

    def test_stderr_separated_from_stdout(self) -> None:
        """Строки ``self.stderr`` помечаются как ``stderr``, не смешиваясь.

        Патчим ``handle`` конкретного класса ``demo_long_command.Command``:
        ``call_command`` инстанцирует именно его, и его ``handle`` важнее
        ``BaseCommand.handle`` в MRO.
        """
        run_id = "run-1"
        store.create_state(run_id, "demo_long_command", [])

        def mixed_handle(self, *a, **kw):
            self.stdout.write("out-1")
            self.stderr.write("err-1")
            self.stdout.write("out-2")

        with patch.object(DemoCommand, "handle", mixed_handle):
            execute_command(run_id, "demo_long_command")

        lines = store.get_log(run_id)
        self.assertEqual(
            [(i["msg"], i["stream"]) for i in lines],
            [
                ("out-1", store.STREAM_STDOUT),
                ("err-1", store.STREAM_STDERR),
                ("out-2", store.STREAM_STDOUT),
            ],
        )

    def test_error(self) -> None:
        """Ошибка внутри команды переводит состояние в ``error`` с traceback."""
        run_id = "run-1"
        store.create_state(run_id, "demo_long_command", [])

        with patch(_DEMO_SLEEP):
            result = execute_command(
                run_id,
                "demo_long_command",
                args=[],
                kwargs={"steps": "abc"},
            )

        self.assertEqual(result["status"], "error")
        state = store.get_state(run_id)
        self.assertEqual(state["status"], "error")
        self.assertIn("TypeError", state["error"])

    def test_stopped(self) -> None:
        """Флаг остановки до запуска → статус ``stopped``."""
        run_id = "run-1"
        store.create_state(run_id, "demo_long_command", [])
        store.request_stop(run_id)

        with patch(_DEMO_SLEEP):
            result = execute_command(
                run_id,
                "demo_long_command",
                args=[],
                kwargs={"steps": "3"},
            )

        self.assertEqual(result["status"], "stopped")
        state = store.get_state(run_id)
        self.assertEqual(state["status"], "stopped")

    def test_lock_released(self) -> None:
        """После выполнения лок снимается."""
        run_id = "run-1"
        store.acquire_lock(run_id)
        store.create_state(run_id, "demo_long_command", [])

        with patch(_DEMO_SLEEP):
            execute_command(run_id, "demo_long_command", kwargs={"steps": "1"})

        self.assertIsNone(store.get_lock())
