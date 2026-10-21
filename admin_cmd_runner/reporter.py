"""Репортёр прогресса/лога, передаваемый в ``call_command`` как stdout.

Совмещает роли:
    * file-like объекта (``write``/``flush``/``isatty``) — для stdout/stderr;
    * API для управления прогрессом и проверки флага остановки.

Текущий ``run_id`` хранится в thread-local, чтобы management-команда
могла обратиться к репортёру через ``get_reporter()`` без проброса
дополнительных параметров.
"""

import re
import sys
import threading
from typing import Any

from . import store

_thread_local: threading.local = threading.local()

_ANSI_RE: re.Pattern[str] = re.compile(r"\x1b\[[0-9;]*m")


class CommandStopRequested(Exception):
    """Сигнализирует о том, что пользователь запросил остановку команды.

    Может подниматься из ``Reporter.check_stop()`` внутри management-команды;
    ``jobs.execute_command`` перехватывает это исключение и фиксирует
    терминальный статус ``stopped``.
    """


def set_current_run(run_id: str) -> None:
    """Устанавливает ``run_id`` активного запуска в текущем потоке."""
    _thread_local.run_id = run_id


def clear_current_run() -> None:
    """Сбрасывает ``run_id`` в текущем потоке."""
    _thread_local.run_id = None


def get_current_run_id() -> str | None:
    """Возвращает ``run_id`` текущего потока или ``None``."""
    return getattr(_thread_local, "run_id", None)


class Reporter:
    """Репортёр прогресса и логов, привязанный к конкретному ``run_id``.

    Используется как ``stdout``/``stderr`` в ``call_command`` и как объект
    с методами ``progress``/``check_stop`` для использования внутри команд.
    """

    def __init__(self, run_id: str) -> None:
        """Создаёт репортёр для запуска ``run_id``."""
        self.run_id: str = run_id

    def write(self, msg: Any = "") -> None:
        """Записывает строку в лог запуска (ANSI-коды удаляются)."""
        text = _ANSI_RE.sub("", str(msg)).rstrip("\n")
        if not text:
            return
        store.append_log(self.run_id, text)

    def flush(self) -> None:
        """Заглушка для совместимости с file-like интерфейсом."""

    @property
    def isatty(self) -> bool:
        """Всегда ``False`` — значит, вывод можно писать без TTY-контроля."""
        return False

    def log(self, msg: Any) -> None:
        """Псевдоним ``write`` для использования внутри команд."""
        self.write(msg)

    def progress(self, percent: int, message: str = "") -> None:
        """Обновляет прогресс запуска: процент и текстовое сообщение."""
        store.set_progress(self.run_id, percent, message)

    def check_stop(self) -> None:
        """Поднимает ``CommandStopRequested``, если запрошена остановка."""
        if store.is_stop_requested(self.run_id):
            raise CommandStopRequested("Stop requested by user")


class NullReporter:
    """Репортёр-заглушка для запуска команд вне очереди (например, из shell).

    Пишет в стандартный stdout процесса и игнорирует обновления прогресса.
    """

    def write(self, msg: Any = "") -> None:
        """Пишет строку в ``sys.stdout`` процесса."""
        sys.stdout.write(str(msg).rstrip("\n") + "\n")

    def flush(self) -> None:
        """Сбрасывает буфер ``sys.stdout``."""
        sys.stdout.flush()

    @property
    def isatty(self) -> bool:
        """Всегда ``False``."""
        return False

    def log(self, msg: Any) -> None:
        """Псевдоним ``write``."""
        self.write(msg)

    def progress(self, percent: int, message: str = "") -> None:
        """Ничего не делает: прогресс вне очереди не отслеживается."""

    def check_stop(self) -> None:
        """Ничего не делает: останавливать нечего."""


def get_reporter() -> Reporter | NullReporter:
    """Возвращает репортёр для текущего потока.

    Если ``run_id`` в потоке не установлен (команда запускается вне воркера) —
    возвращает :class:`NullReporter`.
    """
    run_id = get_current_run_id()
    return Reporter(run_id) if run_id else NullReporter()
