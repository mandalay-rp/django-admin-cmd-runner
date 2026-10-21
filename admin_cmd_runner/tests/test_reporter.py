"""Тесты модуля :mod:`admin_cmd_runner.reporter`."""

import io
import sys
from unittest.mock import patch

from admin_cmd_runner import store
from admin_cmd_runner.reporter import (
    CommandStopRequested,
    NullReporter,
    Reporter,
    clear_current_run,
    get_current_run_id,
    get_reporter,
    set_current_run,
)

from .base import CacheTestCase


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

    def test_write_default_stream_stdout(self) -> None:
        """По умолчанию ``Reporter`` пишет в ``stdout``."""
        store.create_state("run-1", "demo", [])
        Reporter("run-1").write("hello")
        lines = store.get_log("run-1")
        self.assertEqual(lines[0]["stream"], store.STREAM_STDOUT)

    def test_write_stream_stderr(self) -> None:
        """``Reporter(stream="stderr")`` помечает строки как ``stderr``."""
        store.create_state("run-1", "demo", [])
        Reporter("run-1", stream=store.STREAM_STDERR).write("oops")
        lines = store.get_log("run-1")
        self.assertEqual(lines[0]["stream"], store.STREAM_STDERR)
        self.assertEqual(lines[0]["msg"], "oops")

    def test_two_reporters_isolated_streams(self) -> None:
        """Два репортёра на один ``run_id`` пишут в разные потоки."""
        store.create_state("run-1", "demo", [])
        out = Reporter("run-1", stream=store.STREAM_STDOUT)
        err = Reporter("run-1", stream=store.STREAM_STDERR)
        out.write("out")
        err.write("err")

        lines = store.get_log("run-1")
        self.assertEqual(
            [(i["msg"], i["stream"]) for i in lines],
            [("out", store.STREAM_STDOUT), ("err", store.STREAM_STDERR)],
        )

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

    def test_stream_attribute(self) -> None:
        """Атрибут ``stream`` сохраняется из конструктора."""
        self.assertEqual(
            Reporter("run-1", stream=store.STREAM_STDERR).stream,
            store.STREAM_STDERR,
        )


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

    def test_stream_attribute(self) -> None:
        """Атрибут ``stream`` есть для совместимости с ``Reporter``."""
        self.assertEqual(NullReporter().stream, store.STREAM_STDOUT)
        self.assertEqual(
            NullReporter(stream=store.STREAM_STDERR).stream,
            store.STREAM_STDERR,
        )


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
        """С ``run_id`` возвращается ``Reporter`` со ``stream="stdout"``."""
        set_current_run("run-1")
        r = get_reporter()
        self.assertIsInstance(r, Reporter)
        self.assertEqual(r.run_id, "run-1")
        self.assertEqual(r.stream, store.STREAM_STDOUT)
