"""Тесты модуля :mod:`command_runner.reporter`."""

import io
import sys
from unittest.mock import patch

from .base import CacheTestCase
from command_runner import store
from command_runner.reporter import (
    CommandStopRequested,
    NullReporter,
    Reporter,
    clear_current_run,
    get_current_run_id,
    get_reporter,
    set_current_run,
)


class ReporterTests(CacheTestCase):
    """Тесты :class:`Reporter`."""

    def test_write_appends_log(self) -> None:
        """``write`` пишет строку в лог запуска."""
        store.create_state("run-1", "demo", [])
        r = Reporter("run-1")
        r.write("hello")
        lines = store.get_log("run-1")
        self.assertEqual(len(lines), 1)
        self.assertEqual(lines[0]["msg"], "hello")

    def test_write_strips_ansi(self) -> None:
        """ANSI-последовательности из вывода удаляются."""
        store.create_state("run-1", "demo", [])
        r = Reporter("run-1")
        r.write("\x1b[31mred\x1b[0m")
        lines = store.get_log("run-1")
        self.assertEqual(lines[0]["msg"], "red")

    def test_write_skips_empty(self) -> None:
        """Пустые строки и переводы строк не попадают в лог."""
        store.create_state("run-1", "demo", [])
        r = Reporter("run-1")
        r.write("")
        r.write("\n")
        self.assertEqual(store.get_log("run-1"), [])

    def test_progress(self) -> None:
        """``progress`` обновляет прогресс состояния."""
        store.create_state("run-1", "demo", [])
        Reporter("run-1").progress(50, "half")
        state = store.get_state("run-1")
        self.assertEqual(state["progress"], {"percent": 50, "message": "half"})

    def test_check_stop_no_flag(self) -> None:
        """Без флага ``check_stop`` не поднимает исключение."""
        store.create_state("run-1", "demo", [])
        Reporter("run-1").check_stop()

    def test_check_stop_with_flag(self) -> None:
        """С флагом ``check_stop`` поднимает ``CommandStopRequested``."""
        store.create_state("run-1", "demo", [])
        store.request_stop("run-1")
        with self.assertRaises(CommandStopRequested):
            Reporter("run-1").check_stop()

    def test_isatty(self) -> None:
        """``isatty`` всегда ``False``."""
        self.assertFalse(Reporter("run-1").isatty)

    def test_flush(self) -> None:
        """``flush`` не падает."""
        Reporter("run-1").flush()


class NullReporterTests(CacheTestCase):
    """Тесты :class:`NullReporter`."""

    def test_write_to_stdout(self) -> None:
        """``write`` пишет в ``sys.stdout``."""
        buf = io.StringIO()
        with patch.object(sys, "stdout", buf):
            NullReporter().write("hello")
        self.assertEqual(buf.getvalue(), "hello\n")

    def test_progress_and_check_stop_noop(self) -> None:
        """``progress``/``check_stop`` — no-op."""
        r = NullReporter()
        r.progress(50, "x")
        r.check_stop()


class ThreadLocalTests(CacheTestCase):
    """Тесты thread-local для ``run_id``."""

    def tearDown(self) -> None:
        """Сбрасывает thread-local после теста."""
        clear_current_run()

    def test_set_get_clear(self) -> None:
        """``set_current_run``/``get_current_run_id``/``clear_current_run``."""
        self.assertIsNone(get_current_run_id())
        set_current_run("run-1")
        self.assertEqual(get_current_run_id(), "run-1")
        clear_current_run()
        self.assertIsNone(get_current_run_id())

    def test_get_reporter_null_outside_run(self) -> None:
        """Без ``run_id`` возвращается ``NullReporter``."""
        self.assertIsInstance(get_reporter(), NullReporter)

    def test_get_reporter_inside_run(self) -> None:
        """С ``run_id`` возвращается ``Reporter``."""
        set_current_run("run-1")
        r = get_reporter()
        self.assertIsInstance(r, Reporter)
        self.assertEqual(r.run_id, "run-1")
