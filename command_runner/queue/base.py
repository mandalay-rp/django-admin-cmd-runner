"""Абстрактный интерфейс бэкенда очереди."""

from abc import ABC, abstractmethod
from collections.abc import Sequence
from typing import Any


class BaseQueueBackend(ABC):
    """Общий интерфейс для Celery и RQ бэкендов."""

    @abstractmethod
    def enqueue(
        self,
        run_id: str,
        command_name: str,
        args: Sequence[str] | None = None,
        kwargs: dict[str, Any] | None = None,
    ) -> str:
        """Ставит задачу в очередь и возвращает ``task_id``/``job_id``."""

    @abstractmethod
    def revoke(self, task_id: str) -> str:
        """Пытается остановить задачу.

        Возвращает одно из:
            ``"cancelled"``  — задача была в очереди и снята (не выполнялась);
            ``"stopping"``   — задача выполнялась, отправлена команда остановки;
            ``"terminal"``   — задача уже завершена/упала/отменена;
            ``"not_found"``  — задача не найдена.
        """

    @abstractmethod
    def get_status(self, task_id: str) -> str | None:
        """Возвращает унифицированный статус задачи.

        Возможные значения:
            ``"queued"`` | ``"running"`` | ``"stopped"`` | ``"success"``
            | ``"error"`` | ``"not_found"``
            | ``None`` — если состояние не определяется (нет данных или
              бэкенд недоступен).
        """
