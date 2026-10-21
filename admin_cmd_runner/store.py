"""Хранилище состояния и логов запусков команд в общем кэше.

Ключи:
    admin_cmd_runner:lock            — идентификатор активного запуска (один на проект);
    admin_cmd_runner:state:<run_id>  — словарь состояния (status, progress, error, ...);
    admin_cmd_runner:log:<run_id>    — список строк лога;
    admin_cmd_runner:stop:<run_id>   — флаг запроса остановки;
    admin_cmd_runner:task:<run_id>   — task_id/job_id в бэкенде очереди.

Все ключи имеют TTL (``STATE_TTL``), чтобы не засорять Redis.
Кэш обязан быть общим для всех процессов (Redis/Memcached) —
иначе web и worker не увидят состояние друг друга.
"""

import uuid
from collections.abc import Sequence
from datetime import datetime, timezone
from typing import Any

from django.core.cache import cache

LOCK_KEY: str = "admin_cmd_runner:lock"
STATE_KEY: str = "admin_cmd_runner:state:{run_id}"
LOG_KEY: str = "admin_cmd_runner:log:{run_id}"
STOP_KEY: str = "admin_cmd_runner:stop:{run_id}"
TASK_KEY: str = "admin_cmd_runner:task:{run_id}"

LOCK_TTL: int = 60 * 60 * 24
STATE_TTL: int = 60 * 60 * 24
STOP_TTL: int = 60 * 60 * 6
MAX_LOG_LINES: int = 2000

STREAM_STDOUT: str = "stdout"
STREAM_STDERR: str = "stderr"


def now_iso() -> str:
    """Возвращает текущий момент в UTC в формате ISO-8601."""
    return datetime.now(timezone.utc).isoformat()


def _state_key(run_id: str) -> str:
    """Ключ кэша для состояния запуска."""
    return STATE_KEY.format(run_id=run_id)


def _log_key(run_id: str) -> str:
    """Ключ кэша для лога запуска."""
    return LOG_KEY.format(run_id=run_id)


def _stop_key(run_id: str) -> str:
    """Ключ кэша для флага остановки."""
    return STOP_KEY.format(run_id=run_id)


def _task_key(run_id: str) -> str:
    """Ключ кэша для task_id бэкенда."""
    return TASK_KEY.format(run_id=run_id)


# ----- lock (глобальный, один запуск на проект) -----

def acquire_lock(run_id: str) -> bool:
    """Атомарно захватывает глобальный лок под указанный ``run_id``.

    Возвращает ``True``, если лок захвачен, ``False`` — если уже занят.
    """
    return bool(cache.add(LOCK_KEY, run_id, timeout=LOCK_TTL))


def get_lock() -> str | None:
    """Возвращает ``run_id`` активного запуска или ``None``."""
    return cache.get(LOCK_KEY)


def release_lock(run_id: str) -> None:
    """Снимает лок, если он принадлежит ``run_id`` (иначе no-op)."""
    if cache.get(LOCK_KEY) == run_id:
        cache.delete(LOCK_KEY)


# ----- state -----

def create_state(
    run_id: str,
    command: str,
    args: Sequence[str] | None,
) -> dict[str, Any]:
    """Создаёт начальное состояние запуска и пустой лог.

    Возвращает созданный словарь состояния.
    """
    state: dict[str, Any] = {
        "run_id": run_id,
        "command": command,
        "args": list(args or []),
        "status": "queued",
        "started_at": None,
        "finished_at": None,
        "stopping_at": None,
        "progress": {"percent": 0, "message": ""},
        "result": None,
        "error": None,
        "created_at": now_iso(),
    }
    cache.set(_state_key(run_id), state, timeout=STATE_TTL)
    cache.set(_log_key(run_id), [], timeout=STATE_TTL)
    return state


def get_state(run_id: str) -> dict[str, Any] | None:
    """Возвращает текущее состояние запуска или ``None``."""
    return cache.get(_state_key(run_id))


def update_state(run_id: str, **fields: Any) -> dict[str, Any] | None:
    """Частично обновляет состояние запуска.

    Возвращает обновлённый словарь состояния или ``None``, если
    состояния нет (например, истёк TTL).
    """
    state = cache.get(_state_key(run_id))
    if state is None:
        return None
    state.update(fields)
    cache.set(_state_key(run_id), state, timeout=STATE_TTL)
    return state


def set_progress(run_id: str, percent: int, message: str = "") -> None:
    """Обновляет прогресс выполнения: процент и текстовое сообщение."""
    update_state(run_id, progress={"percent": int(percent), "message": message})


# ----- log -----

def append_log(
    run_id: str,
    line: str,
    stream: str = STREAM_STDOUT,
) -> None:
    """Добавляет строку в лог запуска с указанием потока.

    ``stream`` — ``"stdout"`` или ``"stderr"``; используется фронтом для
    цветового выделения строк. Если лог превышает ``MAX_LOG_LINES``,
    самые старые строки обрезаются.
    """
    key = _log_key(run_id)
    lines: list[dict[str, Any]] = cache.get(key) or []
    lines.append({"t": now_iso(), "msg": line, "stream": stream})
    if len(lines) > MAX_LOG_LINES:
        lines = lines[-MAX_LOG_LINES:]
    cache.set(key, lines, timeout=STATE_TTL)


def get_log(run_id: str, since: int = 0) -> list[dict[str, Any]]:
    """Возвращает строки лога начиная с индекса ``since`` (включительно).

    Каждая строка — словарь ``{"t": ..., "msg": ..., "stream": ...}``.
    Для строк, записанных до появления поля ``stream``, ключ может
    отсутствовать — фронт трактует это как ``"stdout"``.
    """
    lines: list[dict[str, Any]] = cache.get(_log_key(run_id)) or []
    return lines[since:]


# ----- stop -----

def request_stop(run_id: str) -> None:
    """Выставляет флаг запроса остановки для запуска."""
    cache.set(_stop_key(run_id), True, timeout=STOP_TTL)


def is_stop_requested(run_id: str) -> bool:
    """``True``, если для запуска запрошена остановка."""
    return bool(cache.get(_stop_key(run_id)))


# ----- helpers -----

def new_run_id() -> str:
    """Генерирует новый уникальный ``run_id`` (hex, 32 символа)."""
    return uuid.uuid4().hex


# ----- task_id -----

def set_task_id(run_id: str, task_id: str) -> None:
    """Сохраняет ``task_id``/``job_id`` бэкенда для запуска."""
    cache.set(_task_key(run_id), task_id, timeout=STATE_TTL)


def get_task_id(run_id: str) -> str | None:
    """Возвращает ``task_id``/``job_id`` бэкенда или ``None``."""
    return cache.get(_task_key(run_id))
