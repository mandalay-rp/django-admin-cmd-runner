"""Тесты модуля :mod:`command_runner.store`."""

from .base import CacheTestCase
from command_runner import store


class LockTests(CacheTestCase):
    """Тесты глобального лока."""

    def test_acquire_and_get(self) -> None:
        """Лок захватывается один раз и возвращает тот же ``run_id``."""
        self.assertTrue(store.acquire_lock("run-1"))
        self.assertEqual(store.get_lock(), "run-1")

    def test_double_acquire_fails(self) -> None:
        """Второй захват лока под другой ``run_id`` возвращает ``False``."""
        store.acquire_lock("run-1")
        self.assertFalse(store.acquire_lock("run-2"))
        self.assertEqual(store.get_lock(), "run-1")

    def test_release_by_owner(self) -> None:
        """Владелец лока может его освободить."""
        store.acquire_lock("run-1")
        store.release_lock("run-1")
        self.assertIsNone(store.get_lock())

    def test_release_by_non_owner_is_noop(self) -> None:
        """Освобождение чужим ``run_id`` не снимает лок."""
        store.acquire_lock("run-1")
        store.release_lock("run-2")
        self.assertEqual(store.get_lock(), "run-1")


class StateTests(CacheTestCase):
    """Тесты хранения состояния запуска."""

    def test_create_state(self) -> None:
        """Создаёт состояние со статусом ``queued`` и пустым прогрессом."""
        state = store.create_state("run-1", "demo", ["--steps", "3"])
        self.assertEqual(state["run_id"], "run-1")
        self.assertEqual(state["command"], "demo")
        self.assertEqual(state["args"], ["--steps", "3"])
        self.assertEqual(state["status"], "queued")
        self.assertEqual(state["progress"], {"percent": 0, "message": ""})
        self.assertIsNone(state["error"])
        self.assertIsNotNone(state["created_at"])

    def test_get_state(self) -> None:
        """Возвращает созданное состояние."""
        store.create_state("run-1", "demo", [])
        state = store.get_state("run-1")
        self.assertIsNotNone(state)
        self.assertEqual(state["run_id"], "run-1")

    def test_get_state_missing(self) -> None:
        """Для отсутствующего ``run_id`` возвращает ``None``."""
        self.assertIsNone(store.get_state("nope"))

    def test_update_state(self) -> None:
        """Частично обновляет поля состояния."""
        store.create_state("run-1", "demo", [])
        updated = store.update_state("run-1", status="running", started_at="ts")
        self.assertEqual(updated["status"], "running")
        self.assertEqual(updated["started_at"], "ts")

    def test_update_state_missing(self) -> None:
        """Обновление несуществующего запуска возвращает ``None``."""
        self.assertIsNone(store.update_state("nope", status="running"))

    def test_set_progress(self) -> None:
        """``set_progress`` пишет процент и сообщение."""
        store.create_state("run-1", "demo", [])
        store.set_progress("run-1", 42, "почти всё")
        state = store.get_state("run-1")
        self.assertEqual(state["progress"], {"percent": 42, "message": "почти всё"})


class LogTests(CacheTestCase):
    """Тесты хранения лога."""

    def test_append_and_get(self) -> None:
        """Строки лога сохраняются с таймстампом и возвращаются по порядку."""
        store.create_state("run-1", "demo", [])
        store.append_log("run-1", "line 1")
        store.append_log("run-1", "line 2")

        lines = store.get_log("run-1")
        self.assertEqual(len(lines), 2)
        self.assertEqual(lines[0]["msg"], "line 1")
        self.assertEqual(lines[1]["msg"], "line 2")
        self.assertIn("t", lines[0])

    def test_get_log_since(self) -> None:
        """``since`` сдвигает окно выдачи строк."""
        store.create_state("run-1", "demo", [])
        store.append_log("run-1", "a")
        store.append_log("run-1", "b")
        store.append_log("run-1", "c")

        lines = store.get_log("run-1", since=1)
        self.assertEqual([i["msg"] for i in lines], ["b", "c"])

    def test_log_trimming(self) -> None:
        """При превышении лимита старые строки обрезаются."""
        store.create_state("run-1", "demo", [])
        for i in range(store.MAX_LOG_LINES + 10):
            store.append_log("run-1", f"l{i}")

        lines = store.get_log("run-1")
        self.assertEqual(len(lines), store.MAX_LOG_LINES)
        self.assertEqual(lines[-1]["msg"], f"l{store.MAX_LOG_LINES + 9}")
        self.assertNotEqual(lines[0]["msg"], "l0")


class StopFlagTests(CacheTestCase):
    """Тесты флага остановки."""

    def test_request_stop(self) -> None:
        """После запроса флаг возвращает ``True``."""
        self.assertFalse(store.is_stop_requested("run-1"))
        store.request_stop("run-1")
        self.assertTrue(store.is_stop_requested("run-1"))


class TaskIdTests(CacheTestCase):
    """Тесты хранения ``task_id``."""

    def test_set_and_get(self) -> None:
        """``set_task_id``/``get_task_id`` работают как KV-хранилище."""
        store.set_task_id("run-1", "task-123")
        self.assertEqual(store.get_task_id("run-1"), "task-123")

    def test_get_missing(self) -> None:
        """Для отсутствующего ключа возвращается ``None``."""
        self.assertIsNone(store.get_task_id("nope"))


class HelpersTests(CacheTestCase):
    """Тесты вспомогательных функций."""

    def test_new_run_id_unique(self) -> None:
        """``new_run_id`` генерирует разные идентификаторы."""
        a = store.new_run_id()
        b = store.new_run_id()
        self.assertNotEqual(a, b)
        self.assertEqual(len(a), 32)

    def test_now_iso_returns_str(self) -> None:
        """``now_iso`` возвращает ISO-строку."""
        ts = store.now_iso()
        self.assertIsInstance(ts, str)
        self.assertIn("T", ts)
