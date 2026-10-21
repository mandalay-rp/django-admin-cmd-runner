"""Реестр management-команд, доступных для запуска из UI.

Источник данных — ``settings.COMMAND_RUNNER_COMMANDS``: список строк
(имён команд) или словарей ``{"name": ..., "label": ..., "args_help": ...}``.
"""

from typing import Any, Union

from django.conf import settings

CommandSpec = dict[str, str]
CommandEntry = Union[str, dict[str, Any]]


def get_available_commands() -> list[CommandSpec]:
    """Возвращает список доступных команд в нормализованном виде.

    Каждый элемент — словарь с ключами ``name``, ``label``, ``args_help``.
    Порядок соответствует ``settings.COMMAND_RUNNER_COMMANDS``.
    """
    raw: list[CommandEntry] = getattr(settings, "COMMAND_RUNNER_COMMANDS", [])
    result: list[CommandSpec] = []
    for item in raw:
        if isinstance(item, str):
            result.append({"name": item, "label": item, "args_help": ""})
        else:
            result.append(
                {
                    "name": item["name"],
                    "label": item.get("label", item.get("name")) or "",
                    "args_help": item.get("args_help", ""),
                }
            )
    return result
