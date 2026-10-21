"""Демонстрационная долгая команда: показывает прогресс и реакцию на stop.

Пример запуска из UI с аргументом: ``--steps 2``.
"""

import argparse
import time
from typing import Any

from ._base import ReporterCommand


class Command(ReporterCommand):
    """Демонстрационная команда, выполняющая ``--steps`` итераций по 0.5 сек."""

    help: str = "Демонстрационная долгая команда, показывающая прогресс и stop."

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        """Добавляет опцию ``--steps`` (число итераций, по умолчанию 20)."""
        parser.add_argument("--steps", type=int, default=20)

    def handle(self, *args: Any, **options: Any) -> None:
        """Выполняет цикл итераций, обновляя прогресс и проверяя stop."""
        steps: int = max(1, options["steps"])
        for i in range(steps):
            self.reporter.check_stop()
            self.stdout.write(f"Шаг {i + 1} из {steps}")
            self.reporter.progress(int((i + 1) / steps * 100), f"Шаг {i + 1}/{steps}")
            time.sleep(0.5)
        self.stdout.write("Готово")
