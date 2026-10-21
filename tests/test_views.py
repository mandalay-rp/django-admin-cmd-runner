"""Тесты модуля :mod:`command_runner.views`."""

import json
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

from django.test import RequestFactory

from .base import CacheTestCase, make_staff_user
from command_runner import store, views


class MonitorPageTests(CacheTestCase):
    """Тесты :func:`views.monitor_page`."""

    def setUp(self) -> None:
        """Готовит фабрику запросов."""
        super().setUp()
        self.factory = RequestFactory()

    def test_root_no_run_id(self) -> None:
        """Без ``run_id`` контекст содержит ``current_run_id=None``."""
        request = self.factory.get("/command-runner/")
        request.user = make_staff_user()

        with patch("command_runner.views.render") as mock_render:
            mock_render.return_value = MagicMock(status_code=200)
            views.monitor_page(request)

        ctx = mock_render.call_args[0][2]
        self.assertIsNone(ctx["current_run_id"])
        self.assertIn("commands", ctx)
        self.assertIn("urls", ctx)

    def test_with_run_id(self) -> None:
        """С ``run_id`` контекст содержит его в ``current_run_id``."""
        request = self.factory.get("/command-runner/run-1/")
        request.user = make_staff_user()

        with patch("command_runner.views.render") as mock_render:
            mock_render.return_value = MagicMock(status_code=200)
            views.monitor_page(request, run_id="run-1")

        ctx = mock_render.call_args[0][2]
        self.assertEqual(ctx["current_run_id"], "run-1")


class StartRunTests(CacheTestCase):
    """Тесты :func:`views.start_run`."""

    def setUp(self) -> None:
        """Готовит фабрику запросов."""
        super().setUp()
        self.factory = RequestFactory()

    def test_invalid_form(self) -> None:
        """Невалидная форма → HTTP 400."""
        request = self.factory.post("/start/", {"command": "nope"})
        request.user = make_staff_user()

        with patch(
            "command_runner.views.get_available_commands",
            return_value=[],
        ):
            response = views.start_run(request)

        self.assertEqual(response.status_code, 400)
        self.assertEqual(json.loads(response.content)["error"], "invalid")

    def test_lock_held(self) -> None:
        """Активный запуск → HTTP 409 и ``run_id`` существующего запуска."""
        existing = "existing-run"
        store.acquire_lock(existing)
        store.create_state(existing, "demo", [])
        store.update_state(existing, status="running")

        request = self.factory.post(
            "/start/",
            {"command": "demo_long_command", "args": ""},
        )
        request.user = make_staff_user()

        with patch(
            "command_runner.views.get_available_commands",
            return_value=[{"name": "demo_long_command"}],
        ):
            response = views.start_run(request)

        self.assertEqual(response.status_code, 409)
        data = json.loads(response.content)
        self.assertEqual(data["run_id"], existing)

    def test_success(self) -> None:
        """Успешный запуск сохраняет state, task_id и возвращает ``run_id``."""
        request = self.factory.post(
            "/start/",
            {"command": "demo_long_command", "args": "--steps 3"},
        )
        request.user = make_staff_user()

        with patch(
            "command_runner.views.get_available_commands",
            return_value=[{"name": "demo_long_command"}],
        ), patch(
            "command_runner.views.get_backend",
        ) as mock_get_backend:
            mock_backend = MagicMock()
            mock_backend.enqueue.return_value = "task-123"
            mock_get_backend.return_value = mock_backend

            response = views.start_run(request)

        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertTrue(data["ok"])
        run_id = data["run_id"]

        self.assertEqual(store.get_lock(), run_id)
        self.assertEqual(store.get_task_id(run_id), "task-123")

        state = store.get_state(run_id)
        self.assertEqual(state["command"], "demo_long_command")
        self.assertEqual(state["status"], "queued")
        mock_backend.enqueue.assert_called_once()


class StopRunTests(CacheTestCase):
    """Тесты :func:`views.stop_run`."""

    def setUp(self) -> None:
        """Готовит фабрику запросов."""
        super().setUp()
        self.factory = RequestFactory()

    def _request(self, run_id: str):
        """Создаёт POST-запрос от staff-пользователя."""
        request = self.factory.post(f"/stop/{run_id}/")
        request.user = make_staff_user()
        return request

    def test_not_found(self) -> None:
        """Отсутствующий ``run_id`` → HTTP 404."""
        response = views.stop_run(self._request("nope"), run_id="nope")
        self.assertEqual(response.status_code, 404)

    def test_already_terminal(self) -> None:
        """Терминальный статус → ``already`` без вызова бэкенда."""
        run_id = "run-1"
        store.create_state(run_id, "demo", [])
        store.update_state(run_id, status="success")

        with patch("command_runner.views.get_backend") as mock_gb:
            response = views.stop_run(self._request(run_id), run_id=run_id)

        mock_gb.assert_not_called()
        data = json.loads(response.content)
        self.assertTrue(data["ok"])
        self.assertEqual(data["already"], "success")

    def test_no_task_id(self) -> None:
        """Без ``task_id`` статус сразу становится ``stopped``."""
        run_id = "run-1"
        store.create_state(run_id, "demo", [])
        store.update_state(run_id, status="queued")

        response = views.stop_run(self._request(run_id), run_id=run_id)

        data = json.loads(response.content)
        self.assertEqual(data["result"], "no_task")
        self.assertEqual(store.get_state(run_id)["status"], "stopped")

    def test_revoke_cancelled(self) -> None:
        """``revoke`` вернул ``"cancelled"`` → статус ``stopped``."""
        run_id = "run-1"
        store.create_state(run_id, "demo", [])
        store.set_task_id(run_id, "task-1")
        store.update_state(run_id, status="queued")

        with patch("command_runner.views.get_backend") as mock_gb:
            mock_backend = MagicMock()
            mock_backend.revoke.return_value = "cancelled"
            mock_gb.return_value = mock_backend

            response = views.stop_run(self._request(run_id), run_id=run_id)

        data = json.loads(response.content)
        self.assertEqual(data["result"], "cancelled")
        self.assertEqual(store.get_state(run_id)["status"], "stopped")

    def test_revoke_stopping(self) -> None:
        """``revoke`` вернул ``"stopping"`` → статус ``stopping``."""
        run_id = "run-1"
        store.create_state(run_id, "demo", [])
        store.set_task_id(run_id, "task-1")
        store.update_state(run_id, status="running")

        with patch("command_runner.views.get_backend") as mock_gb:
            mock_backend = MagicMock()
            mock_backend.revoke.return_value = "stopping"
            mock_gb.return_value = mock_backend

            response = views.stop_run(self._request(run_id), run_id=run_id)

        data = json.loads(response.content)
        self.assertEqual(data["result"], "stopping")
        state = store.get_state(run_id)
        self.assertEqual(state["status"], "stopping")
        self.assertIsNotNone(state["stopping_at"])


class StatusApiTests(CacheTestCase):
    """Тесты :func:`views.status_api`."""

    def setUp(self) -> None:
        """Готовит фабрику запросов."""
        super().setUp()
        self.factory = RequestFactory()

    def _request(self, run_id: str, since: int = 0):
        """Создаёт GET-запрос от staff-пользователя."""
        request = self.factory.get(f"/status/{run_id}/", {"since": since})
        request.user = make_staff_user()
        return request

    def test_not_found(self) -> None:
        """Отсутствующий ``run_id`` → HTTP 404."""
        response = views.status_api(self._request("nope"), run_id="nope")
        self.assertEqual(response.status_code, 404)

    def test_returns_state_and_log(self) -> None:
        """Возвращает состояние и новые строки лога."""
        run_id = "run-1"
        store.create_state(run_id, "demo", [])
        store.update_state(run_id, status="running")
        store.append_log(run_id, "l1")
        store.append_log(run_id, "l2")

        response = views.status_api(self._request(run_id, since=1), run_id=run_id)
        data = json.loads(response.content)

        self.assertTrue(data["ok"])
        self.assertEqual(data["state"]["status"], "running")
        self.assertEqual(len(data["log"]), 1)
        self.assertEqual(data["log"][0]["msg"], "l2")
        self.assertEqual(data["since"], 2)


class FinalizeIfNeededTests(CacheTestCase):
    """Тесты :func:`views._finalize_if_needed`."""

    def test_terminal_noop(self) -> None:
        """Терминальный статус не меняется."""
        run_id = "run-1"
        store.create_state(run_id, "demo", [])
        store.update_state(run_id, status="success")

        result = views._finalize_if_needed(run_id, store.get_state(run_id))
        self.assertEqual(result["status"], "success")

    def test_not_stopping_noop(self) -> None:
        """Не-``stopping`` статус не меняется."""
        run_id = "run-1"
        store.create_state(run_id, "demo", [])
        store.update_state(run_id, status="running")

        result = views._finalize_if_needed(run_id, store.get_state(run_id))
        self.assertEqual(result["status"], "running")

    def test_stopping_with_backend_stopped(self) -> None:
        """Бэкенд сообщил ``"stopped"`` → статус становится ``stopped``."""
        run_id = "run-1"
        store.create_state(run_id, "demo", [])
        store.set_task_id(run_id, "task-1")
        store.update_state(
            run_id,
            status="stopping",
            stopping_at=store.now_iso(),
        )

        with patch("command_runner.views.get_backend") as mock_gb:
            mock_backend = MagicMock()
            mock_backend.get_status.return_value = "stopped"
            mock_gb.return_value = mock_backend

            result = views._finalize_if_needed(run_id, store.get_state(run_id))

        self.assertEqual(result["status"], "stopped")
        self.assertIsNotNone(result["finished_at"])

    def test_stopping_with_backend_error_maps_to_stopped(self) -> None:
        """``"error"`` при ``stopping`` считается ``stopped`` (RQ-кейс)."""
        run_id = "run-1"
        store.create_state(run_id, "demo", [])
        store.set_task_id(run_id, "task-1")
        store.update_state(
            run_id,
            status="stopping",
            stopping_at=store.now_iso(),
        )

        with patch("command_runner.views.get_backend") as mock_gb:
            mock_backend = MagicMock()
            mock_backend.get_status.return_value = "error"
            mock_gb.return_value = mock_backend

            result = views._finalize_if_needed(run_id, store.get_state(run_id))

        self.assertEqual(result["status"], "stopped")

    def test_stopping_timeout_fallback(self) -> None:
        """По истечении ``STOP_GRACE_SECONDS`` статус принудительно ``stopped``."""
        run_id = "run-1"
        store.create_state(run_id, "demo", [])
        past = (
            datetime.now(timezone.utc) - timedelta(seconds=views.STOP_GRACE_SECONDS + 5)
        ).isoformat()
        store.update_state(run_id, status="stopping", stopping_at=past)

        result = views._finalize_if_needed(run_id, store.get_state(run_id))
        self.assertEqual(result["status"], "stopped")
