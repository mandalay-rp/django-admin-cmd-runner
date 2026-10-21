"""Бэкенд очереди на Celery."""

from collections.abc import Sequence
from typing import Any

from celery import current_app as celery_app
from celery import shared_task
from celery.result import AsyncResult

from ..jobs import execute_command
from .base import BaseQueueBackend


@shared_task(name="command_runner.execute_command")
def celery_execute_command(
    run_id: str,
    command_name: str,
    args: Sequence[str] | None = None,
    kwargs: dict[str, Any] | None = None,
) -> dict[str, str]:
    """Celery-обёртка над :func:`command_runner.jobs.execute_command`."""
    return execute_command(run_id, command_name, args, kwargs)


_CELERY_STATE_MAP: dict[str, str] = {
    "PENDING": "queued",
    "STARTED": "running",
    "RETRY": "running",
    "SUCCESS": "success",
    "FAILURE": "error",
    "REVOKED": "stopped",
}


class CeleryBackend(BaseQueueBackend):
    """Реализация бэкенда очереди на Celery."""

    def enqueue(
        self,
        run_id: str,
        command_name: str,
        args: Sequence[str] | None = None,
        kwargs: dict[str, Any] | None = None,
    ) -> str:
        """Ставит задачу в Celery и возвращает её ``task_id``."""
        res = celery_execute_command.apply_async(
            args=[run_id, command_name, list(args or []), kwargs or {}],
        )
        return res.id

    def revoke(self, task_id: str) -> str:
        """Отзывает задачу в Celery (terminate + SIGTERM)."""
        try:
            celery_app.control.revoke(task_id, terminate=True, signal="SIGTERM")
            return "stopping"
        except Exception:
            return "not_found"

    def get_status(self, task_id: str) -> str | None:
        """Возвращает унифицированный статус Celery-задачи."""
        try:
            state: str = AsyncResult(task_id).state
        except Exception:
            return None
        return _CELERY_STATE_MAP.get(state)
