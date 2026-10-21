"""Транспортно-независимое исполнение management-команды.

Функция :func:`execute_command` вызывается как celery-задача (через
обёртку в ``queue.celery_backend``) или как RQ-job (по import-path),
и отвечает за:

    * приведение типов kwargs по ``add_argument(type=...)`` команды;
    * установку двух ``Reporter`` (stdout и stderr) в ``call_command``;
    * фиксацию терминального статуса (``success``/``error``/``stopped``);
    * снятие глобального лока после завершения.
"""

import traceback
from collections.abc import Sequence
from typing import Any

from . import store
from .reporter import (
    CommandStopRequested,
    Reporter,
    clear_current_run,
    set_current_run,
)

_BOOL_TRUE: set[str] = {"1", "true", "yes", "on", "y", "t"}
_BOOL_FALSE: set[str] = {"0", "false", "no", "off", "n", "f"}


def _coerce_kwargs(
    command_name: str,
    kwargs: dict[str, Any],
) -> dict[str, Any]:
    """Приводит значения kwargs к типам, объявленным в ``add_argument``.

    ``call_command`` не применяет ``type`` из ``argparse`` к именованным
    аргументам, переданным через ``**kwargs`` — они попадают в
    ``options`` как есть. Эта функция разбирает ``parser`` команды и
    приводит значения к нужному типу (``int``, ``float``, кастомный
    callable, ``bool`` для ``store_true``/``store_false``).

    Если команда не найдена или парсер не удалось построить — kwargs
    возвращаются без изменений.
    """
    if not kwargs:
        return kwargs or {}

    from django.core.management import get_commands, load_command_class

    try:
        app_name: str = get_commands()[command_name]
    except KeyError:
        return kwargs

    try:
        command = load_command_class(app_name, command_name)
        parser = command.create_parser("", command_name)
    except Exception:
        return kwargs

    actions: dict[str, Any] = {}
    for action in parser._actions:
        if not action.option_strings:
            continue
        for opt in action.option_strings:
            key = opt.lstrip("-").replace("-", "_")
            actions[key] = action

    result: dict[str, Any] = {}
    for key, val in kwargs.items():
        action = actions.get(key)
        if action is None:
            result[key] = val
            continue

        if action.type is None and isinstance(val, str):
            low = val.strip().lower()
            if low in _BOOL_TRUE:
                result[key] = True
                continue
            if low in _BOOL_FALSE:
                result[key] = False
                continue

        if action.type is None:
            result[key] = val
            continue

        if isinstance(val, action.type):
            result[key] = val
            continue

        try:
            result[key] = action.type(val)
        except (TypeError, ValueError):
            result[key] = val

    return result


def execute_command(
    run_id: str,
    command_name: str,
    args: Sequence[str] | None = None,
    kwargs: dict[str, Any] | None = None,
) -> dict[str, str]:
    """Выполняет management-команду в контексте запуска ``run_id``.

    Создаёт два репортёра (для ``stdout`` и ``stderr``), чтобы фронт мог
    выделять сообщения разных потоков разным цветом. ``self.stdout`` и
    ``self.stderr`` внутри команды попадают в соответствующие репортёры.

    Возвращает словарь ``{"status": <итоговый статус>}``.
    """
    from django.core.management import call_command

    args = list(args or [])
    kwargs = _coerce_kwargs(command_name, kwargs or {})

    if store.get_state(run_id) is None:
        return {"status": "skipped", "reason": "state not found"}

    store.update_state(run_id, status="running", started_at=store.now_iso())
    set_current_run(run_id)

    out_reporter = Reporter(run_id, stream=store.STREAM_STDOUT)
    err_reporter = Reporter(run_id, stream=store.STREAM_STDERR)

    try:
        call_command(
            command_name,
            *args,
            stdout=out_reporter,
            stderr=err_reporter,
            **kwargs,
        )
        if store.is_stop_requested(run_id):
            store.update_state(run_id, status="stopped", finished_at=store.now_iso())
        else:
            store.update_state(run_id, status="success", finished_at=store.now_iso())
    except CommandStopRequested as exc:
        store.update_state(
            run_id,
            status="stopped",
            error=str(exc),
            finished_at=store.now_iso(),
        )
    except SystemExit:
        store.update_state(
            run_id,
            status="stopped",
            error="terminated",
            finished_at=store.now_iso(),
        )
    except Exception:
        store.update_state(
            run_id,
            status="error",
            error=traceback.format_exc(),
            finished_at=store.now_iso(),
        )
    finally:
        clear_current_run()
        store.release_lock(run_id)

    return {"status": (store.get_state(run_id) or {}).get("status", "unknown")}
