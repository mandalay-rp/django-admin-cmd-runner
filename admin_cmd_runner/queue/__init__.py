"""Фабрика бэкендов очередей (Celery / RQ).

Выбор бэкенда — через ``settings.COMMAND_RUNNER_QUEUE`` (``"celery"``
или ``"rq"``). Импорт конкретного бэкенда ленивый, чтобы отсутствие
celery или rq в окружении не ломало работу другого бэкенда.
"""

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

from .base import BaseQueueBackend


def get_backend() -> BaseQueueBackend:
    """Возвращает экземпляр бэкенда очереди согласно настройкам."""
    kind: str = getattr(settings, "COMMAND_RUNNER_QUEUE", "celery")
    if kind == "celery":
        from .celery_backend import CeleryBackend

        return CeleryBackend()
    if kind == "rq":
        from .rq_backend import RqBackend

        return RqBackend()
    raise ImproperlyConfigured(f"Unknown COMMAND_RUNNER_QUEUE: {kind!r}")
