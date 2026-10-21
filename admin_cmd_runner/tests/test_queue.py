"""Тесты бэкендов очередей :mod:`admin_cmd_runner.queue`."""

import unittest
from unittest.mock import MagicMock, patch

from django.core.exceptions import ImproperlyConfigured
from django.test import SimpleTestCase, override_settings

try:
    from admin_cmd_runner.queue.celery_backend import (
        CeleryBackend,
        celery_execute_command,
    )
    HAS_CELERY = True
except ImportError:
    HAS_CELERY = False
    CeleryBackend = None
    celery_execute_command = None

try:
    from rq.job import Job, JobStatus

    from admin_cmd_runner.queue.rq_backend import RqBackend
    HAS_RQ = True
except ImportError:
    HAS_RQ = False
    RqBackend = None
    Job = None
    JobStatus = None


class GetBackendTests(SimpleTestCase):
    """Тесты фабрики :func:`admin_cmd_runner.queue.get_backend`."""

    @unittest.skipUnless(HAS_CELERY, "celery not installed")
    @override_settings(ADMIN_CMD_RUNNER_QUEUE="celery")
    def test_celery(self) -> None:
        """Настройка ``celery`` → ``CeleryBackend``."""
        from admin_cmd_runner.queue import get_backend
        self.assertIsInstance(get_backend(), CeleryBackend)

    @unittest.skipUnless(HAS_RQ, "rq not installed")
    @override_settings(ADMIN_CMD_RUNNER_QUEUE="rq")
    def test_rq(self) -> None:
        """Настройка ``rq`` → ``RqBackend``."""
        from admin_cmd_runner.queue import get_backend
        self.assertIsInstance(get_backend(), RqBackend)

    @override_settings(ADMIN_CMD_RUNNER_QUEUE="unknown")
    def test_unknown(self) -> None:
        """Неизвестный бэкенд → ``ImproperlyConfigured``."""
        from admin_cmd_runner.queue import get_backend
        with self.assertRaises(ImproperlyConfigured):
            get_backend()


@unittest.skipUnless(HAS_CELERY, "celery not installed")
class CeleryBackendTests(SimpleTestCase):
    """Тесты :class:`CeleryBackend`."""

    def test_enqueue(self) -> None:
        """``enqueue`` возвращает ``task_id`` из ``apply_async``."""
        backend = CeleryBackend()
        with patch.object(celery_execute_command, "apply_async") as mock_apply:
            mock_apply.return_value.id = "task-1"
            task_id = backend.enqueue("run-1", "demo", args=[], kwargs={})
        self.assertEqual(task_id, "task-1")
        mock_apply.assert_called_once()

    def test_revoke(self) -> None:
        """``revoke`` вызывает ``control.revoke`` и возвращает ``"stopping"``."""
        backend = CeleryBackend()
        with patch(
            "admin_cmd_runner.queue.celery_backend.celery_app",
        ) as mock_app:
            result = backend.revoke("task-1")
        self.assertEqual(result, "stopping")
        mock_app.control.revoke.assert_called_once_with(
            "task-1", terminate=True, signal="SIGTERM",
        )

    def test_revoke_error(self) -> None:
        """Исключение в ``control.revoke`` → ``"not_found"``."""
        backend = CeleryBackend()
        with patch(
            "admin_cmd_runner.queue.celery_backend.celery_app",
        ) as mock_app:
            mock_app.control.revoke.side_effect = RuntimeError("boom")
            result = backend.revoke("task-1")
        self.assertEqual(result, "not_found")

    def test_get_status_known(self) -> None:
        """Известный celery-state мапится в унифицированный."""
        backend = CeleryBackend()
        with patch(
            "admin_cmd_runner.queue.celery_backend.AsyncResult",
        ) as mock_ar:
            mock_ar.return_value.state = "STARTED"
            self.assertEqual(backend.get_status("t"), "running")

            mock_ar.return_value.state = "SUCCESS"
            self.assertEqual(backend.get_status("t"), "success")

    def test_get_status_exception(self) -> None:
        """Исключение при получении статуса → ``None``."""
        backend = CeleryBackend()
        with patch(
            "admin_cmd_runner.queue.celery_backend.AsyncResult",
            side_effect=RuntimeError("boom"),
        ):
            self.assertIsNone(backend.get_status("t"))


@unittest.skipUnless(HAS_RQ, "rq not installed")
class RqBackendTests(SimpleTestCase):
    """Тесты :class:`RqBackend`."""

    def _mock_job(self, status: "JobStatus") -> MagicMock:
        """Создаёт mock ``Job`` с указанным статусом."""
        job = MagicMock()
        job.id = "job-1"
        job.get_status.return_value = status
        return job

    def test_revoke_queued(self) -> None:
        """``queued``-задача снимается через ``job.cancel()``."""
        backend = RqBackend()
        job = self._mock_job(JobStatus.QUEUED)
        with patch(
            "admin_cmd_runner.queue.rq_backend.Job.fetch", return_value=job,
        ):
            result = backend.revoke("job-1")
        self.assertEqual(result, "cancelled")
        job.cancel.assert_called_once()

    def test_revoke_started(self) -> None:
        """``started``-задача → ``send_stop_job_command`` и результат ``"stopping"``."""
        backend = RqBackend()
        job = self._mock_job(JobStatus.STARTED)
        with patch(
            "admin_cmd_runner.queue.rq_backend.Job.fetch", return_value=job,
        ), patch(
            "admin_cmd_runner.queue.rq_backend.send_stop_job_command",
        ) as mock_stop:
            result = backend.revoke("job-1")
        self.assertEqual(result, "stopping")
        mock_stop.assert_called_once()

    def test_revoke_started_fallback_kill_horse(self) -> None:
        """Если ``send_stop_job_command`` упал — вызывается ``kill_horse``."""
        backend = RqBackend()
        job = self._mock_job(JobStatus.STARTED)
        worker = MagicMock()
        worker.name = "worker-1"

        with patch(
            "admin_cmd_runner.queue.rq_backend.Job.fetch", return_value=job,
        ), patch(
            "admin_cmd_runner.queue.rq_backend.send_stop_job_command",
            side_effect=RuntimeError("boom"),
        ), patch(
            "admin_cmd_runner.queue.rq_backend._find_worker_for_job",
            return_value=worker,
        ), patch(
            "admin_cmd_runner.queue.rq_backend.send_kill_horse_command",
        ) as mock_kill:
            result = backend.revoke("job-1")

        self.assertEqual(result, "stopping")
        mock_kill.assert_called_once()

    def test_revoke_terminal(self) -> None:
        """Терминальный статус → ``"terminal"`` без действий."""
        backend = RqBackend()
        job = self._mock_job(JobStatus.FINISHED)
        with patch(
            "admin_cmd_runner.queue.rq_backend.Job.fetch", return_value=job,
        ):
            result = backend.revoke("job-1")
        self.assertEqual(result, "terminal")
        job.cancel.assert_not_called()

    def test_revoke_not_found(self) -> None:
        """Отсутствующий job → ``"not_found"``."""
        from rq.exceptions import NoSuchJobError

        backend = RqBackend()
        with patch(
            "admin_cmd_runner.queue.rq_backend.Job.fetch",
            side_effect=NoSuchJobError,
        ):
            result = backend.revoke("job-1")
        self.assertEqual(result, "not_found")

    def test_get_status_mapping(self) -> None:
        """Известные RQ-статусы мапятся в унифицированные."""
        backend = RqBackend()

        cases = {
            JobStatus.QUEUED: "queued",
            JobStatus.STARTED: "running",
            JobStatus.FINISHED: "success",
            JobStatus.FAILED: "error",
            JobStatus.STOPPED: "stopped",
            JobStatus.CANCELED: "stopped",
        }
        for rq_status, expected in cases.items():
            job = self._mock_job(rq_status)
            with patch(
                "admin_cmd_runner.queue.rq_backend.Job.fetch", return_value=job,
            ):
                self.assertEqual(backend.get_status("job-1"), expected)

    def test_get_status_not_found(self) -> None:
        """Отсутствующий job → ``"not_found"``."""
        from rq.exceptions import NoSuchJobError

        backend = RqBackend()
        with patch(
            "admin_cmd_runner.queue.rq_backend.Job.fetch",
            side_effect=NoSuchJobError,
        ):
            self.assertEqual(backend.get_status("job-1"), "not_found")
