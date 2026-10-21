"""Базовый класс для management-команд, поддерживающих прогресс и stop.

Наследники получают свойство ``self.reporter``: внутри воркера это
:class:`admin_cmd_runner.reporter.Reporter` (пишет в лог запуска и
позволяет обновлять прогресс/проверять stop), а вне воркера —
:class:`admin_cmd_runner.reporter.NullReporter` (пишет в stdout процесса).
"""

from django.core.management.base import BaseCommand

from admin_cmd_runner.reporter import NullReporter, Reporter, get_reporter


class ReporterCommand(BaseCommand):
    """BaseCommand с доступом к репортёру прогресса/остановки."""

    @property
    def reporter(self) -> Reporter | NullReporter:
        """Возвращает репортёр текущего запуска (или заглушку вне воркера)."""
        return get_reporter()
