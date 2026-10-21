"""Бэкенд очереди на RQ.

Особенности RQ, учтённые здесь:
    * в ``StartedJobRegistry`` job_id может храниться с суффиксом
      ``:execution_id`` — его нужно очищать перед ``send_stop_job_command``;
    * job, убитый по stop через ``kill_horse``, помечается как ``FAILED``
      (мапится в ``"error"``), финализатор в ``views`` поправит это на
      ``"stopped"``;
    * ``send_stop_job_command`` работает, только если воркер найден в той
      же очереди — иначе используется ``send_kill_horse_command``.
"""

import logging
from collections.abc import Sequence
from typing import Any

import redis
from django.conf import settings
from redis import Redis
from rq import Queue
from rq.command import send_kill_horse_command, send_stop_job_command
from rq.exceptions import InvalidJobOperation, NoSuchJobError
from rq.job import Job, JobStatus
from rq.worker import Worker

from ..jobs import execute_command
from .base import BaseQueueBackend

logger = logging.getLogger(__name__)


def _conn() -> Redis:
    """Создаёт Redis-соединение по ``COMMAND_RUNNER_RQ_REDIS_URL``."""
    return redis.from_url(settings.COMMAND_RUNNER_RQ_REDIS_URL)


def _queue(conn: Redis | None = None) -> tuple[Queue, Redis]:
    """Возвращает ``(Queue, redis_conn)`` для очереди command_runner."""
    conn = conn or _conn()
    name: str = getattr(settings, "COMMAND_RUNNER_RQ_QUEUE", "default")
    return Queue(name, connection=conn), conn


def _clean_job_id(job_id: str) -> str:
    """Отрезает от ``job_id`` суффикс ``:execution_id``, если он есть."""
    return job_id.split(":", 1)[0]


def _find_worker_for_job(
    conn: Redis,
    queue_name: str,
    job_id: str,
) -> Worker | None:
    """Ищет воркер, который прямо сейчас исполняет ``job_id``.

    Сравнение идёт по очищенному ``job_id`` — RQ хранит в воркере
    чистый UUID, а в реестре — возможно с суффиксом.
    """
    clean = _clean_job_id(job_id)
    for worker in Worker.all(queue=Queue(queue_name, connection=conn)):
        try:
            current = worker.get_current_job_id()
        except Exception:
            current = None
        if current and _clean_job_id(current) == clean:
            return worker
    return None


_RQ_STATUS_MAP: dict[JobStatus, str] = {
    JobStatus.QUEUED: "queued",
    JobStatus.DEFERRED: "queued",
    JobStatus.SCHEDULED: "queued",
    JobStatus.STARTED: "running",
    JobStatus.FINISHED: "success",
    JobStatus.FAILED: "error",
    JobStatus.STOPPED: "stopped",
    JobStatus.CANCELED: "stopped",
}


class RqBackend(BaseQueueBackend):
    """Реализация бэкенда очереди на RQ."""

    def enqueue(
        self,
        run_id: str,
        command_name: str,
        args: Sequence[str] | None = None,
        kwargs: dict[str, Any] | None = None,
    ) -> str:
        """Ставит задачу в RQ и возвращает её ``job_id``."""
        q, _ = _queue()
        job: Job = q.enqueue(
            execute_command,
            run_id,
            command_name,
            list(args or []),
            kwargs or {},
            job_timeout=-1,
        )
        return job.id

    def revoke(self, task_id: str) -> str:
        """Останавливает RQ-задачу.

        Для ``queued``-задачи — ``job.cancel()``; для ``started`` —
        ``send_stop_job_command`` с fallback'ом на ``send_kill_horse_command``.
        """
        conn = _conn()
        queue_name: str = getattr(settings, "COMMAND_RUNNER_RQ_QUEUE", "default")

        try:
            job: Job = Job.fetch(task_id, connection=conn)
        except NoSuchJobError:
            logger.warning("revoke: job %r not found", task_id)
            return "not_found"

        status: JobStatus = job.get_status()
        logger.warning("revoke: job %r status=%r", task_id, status)

        if status in (JobStatus.QUEUED, JobStatus.DEFERRED, JobStatus.SCHEDULED):
            try:
                job.cancel()
                logger.warning("revoke: job %r cancelled (was %s)", task_id, status)
                return "cancelled"
            except InvalidJobOperation as exc:
                logger.warning("revoke: cancel failed for %r: %s", task_id, exc)

        if status == JobStatus.STARTED:
            clean_id = _clean_job_id(job.id)
            try:
                send_stop_job_command(conn, clean_id)
                logger.warning("revoke: send_stop_job_command sent for %r", clean_id)
                return "stopping"
            except Exception as exc:
                logger.warning("revoke: send_stop_job_command failed: %s", exc)

            worker = _find_worker_for_job(conn, queue_name, job.id)
            if worker is not None:
                try:
                    send_kill_horse_command(conn, worker.name)
                    logger.warning("revoke: kill horse sent to worker %r", worker.name)
                except Exception:
                    logger.exception(
                        "revoke: kill horse failed for worker %r", worker.name
                    )
            return "stopping"

        logger.warning("revoke: job %r in terminal state %r", task_id, status)
        return "terminal"

    def get_status(self, task_id: str) -> str | None:
        """Возвращает унифицированный статус RQ-задачи."""
        try:
            job: Job = Job.fetch(task_id, connection=_conn())
        except NoSuchJobError:
            return "not_found"
        except Exception:
            return None
        return _RQ_STATUS_MAP.get(job.get_status())
