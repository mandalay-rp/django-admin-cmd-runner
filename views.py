"""HTTP-вьюхи: страница монитора, запуск, остановка, статус.

Все эндпоинты закрыты ``@staff_member_required``. Состояние запуска
хранится в общем кэше (см. :mod:`command_runner.store`), а исполнение
делегируется бэкенду очереди (:mod:`command_runner.queue`).
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from django.contrib.admin.views.decorators import staff_member_required
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import render
from django.urls import reverse
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_GET, require_POST

from . import store
from .forms import StartCommandForm
from .queue import get_backend
from .registry import get_available_commands

logger = logging.getLogger(__name__)

STOP_GRACE_SECONDS: int = 10


@staff_member_required
@ensure_csrf_cookie
def monitor_page(
    request: HttpRequest,
    run_id: str | None = None,
) -> HttpResponse:
    """Страница монитора запусков.

    На корневом URL (``run_id is None``) показывает форму и не запускает
    поллинг; при ``/command-runner/<run_id>/`` — восстанавливает состояние
    конкретного запуска и включает поллинг на клиенте.
    """
    ctx: dict[str, Any] = {
        "commands": get_available_commands(),
        "current_run_id": run_id or None,
        "urls": {
            "start": reverse("command_runner:start"),
            "stop": reverse("command_runner:stop", args=["__RUNID__"]),
            "status": reverse("command_runner:status", args=["__RUNID__"]),
            "monitor": reverse("command_runner:monitor", args=["__RUNID__"]),
        },
    }
    return render(request, "command_runner/monitor.html", ctx)


@staff_member_required
@require_POST
def start_run(request: HttpRequest) -> JsonResponse:
    """Принимает POST на запуск команды.

    Валидирует форму, захватывает глобальный лок, создаёт состояние,
    ставит задачу в бэкенд и сохраняет ``task_id``. Возвращает ``run_id``
    для последующего поллинга.
    """
    form = StartCommandForm(request.POST)
    if not form.is_valid():
        return JsonResponse(
            {"ok": False, "error": "invalid", "errors": form.errors},
            status=400,
        )

    command_name: str = form.cleaned_data["command"]
    positional, kwargs = form.split_args_kwargs()

    current_lock = store.get_lock()
    if current_lock:
        cur = store.get_state(current_lock)
        if cur is None or cur.get("status") in ("success", "error", "stopped"):
            store.release_lock(current_lock)

    run_id = store.new_run_id()
    if not store.acquire_lock(run_id):
        return JsonResponse(
            {"ok": False, "error": "already_running", "run_id": store.get_lock()},
            status=409,
        )

    store.create_state(run_id, command_name, positional)
    backend = get_backend()
    task_id: str = backend.enqueue(
        run_id,
        command_name,
        args=positional,
        kwargs=kwargs,
    )
    store.set_task_id(run_id, task_id)

    return JsonResponse({"ok": True, "run_id": run_id})


@staff_member_required
@require_POST
def stop_run(request: HttpRequest, run_id: str) -> JsonResponse:
    """Запрашивает остановку запуска ``run_id``.

    Делегирует остановку бэкенду (``revoke``) и фиксирует статус:
    терминальный сразу для ``queued``-задач, ``stopping`` — для
    выполняющихся (финализируется в ``status_api``).
    """
    state = store.get_state(run_id)
    if not state:
        return JsonResponse({"ok": False, "error": "not_found"}, status=404)

    if state.get("status") in ("success", "error", "stopped"):
        return JsonResponse({"ok": True, "already": state["status"]})

    store.request_stop(run_id)

    task_id = store.get_task_id(run_id)
    if not task_id:
        store.update_state(run_id, status="stopped", finished_at=store.now_iso())
        store.release_lock(run_id)
        return JsonResponse({"ok": True, "result": "no_task"})

    try:
        result: str = get_backend().revoke(task_id)
    except Exception:
        logger.exception("STOP: revoke failed for task_id=%r", task_id)
        result = "stopping"

    logger.warning("STOP: revoke result=%r for task_id=%r", result, task_id)

    if result in ("cancelled", "terminal", "not_found"):
        store.update_state(run_id, status="stopped", finished_at=store.now_iso())
        store.release_lock(run_id)
    else:
        store.update_state(run_id, status="stopping", stopping_at=store.now_iso())

    return JsonResponse({"ok": True, "result": result})


@staff_member_required
@require_GET
def status_api(request: HttpRequest, run_id: str) -> JsonResponse:
    """Возвращает JSON с текущим состоянием и новыми строками лога.

    Query-параметр ``since`` — индекс, с которого вернуть новые строки
    лога. Перед отдачей состояния вызывает финализатор, чтобы
    зафиксировать терминальный статус после жёсткого kill'а.
    """
    state = store.get_state(run_id)
    if not state:
        return JsonResponse({"ok": False, "error": "not_found"}, status=404)

    state = _finalize_if_needed(run_id, state)

    try:
        since: int = max(0, int(request.GET.get("since", 0)))
    except ValueError:
        since = 0

    lines = store.get_log(run_id, since=since)
    return JsonResponse(
        {
            "ok": True,
            "state": state,
            "log": lines,
            "since": since + len(lines),
        }
    )


def _finalize_if_needed(
    run_id: str,
    state: dict[str, Any],
) -> dict[str, Any]:
    """Финализирует статус ``stopping`` по данным бэкенда или по таймауту.

    Жёсткая остановка (``kill_horse``) не даёт выполниться ``finally``
    в ``execute_command``, поэтому фактический терминальный статус
    берётся из бэкенда очереди. Если бэкенд недоступен — по истечении
    ``STOP_GRACE_SECONDS`` статус принудительно ставится в ``stopped``.
    """
    status: str | None = state.get("status")

    if status in ("success", "error", "stopped"):
        if store.get_lock() == run_id:
            store.release_lock(run_id)
        return state

    if status != "stopping":
        return state

    task_id = store.get_task_id(run_id)
    if task_id:
        try:
            backend_status = get_backend().get_status(task_id)
        except Exception:
            logger.exception("_finalize_if_needed: get_status failed for %r", task_id)
            backend_status = None

        if backend_status in ("stopped", "error", "success", "not_found"):
            if backend_status == "error" and status == "stopping":
                # RQ помечает job, убитый по stop, как FAILED.
                # Раз мы сами просили остановку — это stopped, а не error.
                final = "stopped"
            elif backend_status == "not_found":
                final = "stopped"
            else:
                final = backend_status
            state = (
                store.update_state(
                    run_id,
                    status=final,
                    finished_at=store.now_iso(),
                )
                or state
            )
            store.release_lock(run_id)
            return state

    stopping_at = state.get("stopping_at")
    if stopping_at:
        try:
            t: datetime = datetime.fromisoformat(stopping_at)
        except ValueError:
            return state
        if datetime.now(timezone.utc) - t > timedelta(seconds=STOP_GRACE_SECONDS):
            state = (
                store.update_state(
                    run_id,
                    status="stopped",
                    finished_at=store.now_iso(),
                )
                or state
            )
            store.release_lock(run_id)
    return state
