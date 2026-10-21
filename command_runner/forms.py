"""Форма запуска management-команды с парсингом аргументов.

Аргументы передаются в виде одной строки в стиле shell: значения с
пробелами можно оборачивать в кавычки, именованные аргументы начинаются
с ``--``. Пример: ``--steps 5 --name "Hello World"``.

Правило разбора positional/kwargs повторяет ``argparse``:
    * всё до ``--`` — позиционные;
    * ``--key value`` и ``--key=value`` — именованные;
    * ``--flag`` без значения — ``True`` (для ``action="store_true"``);
    * всё после ``--`` — позиционные.
"""

import shlex
from typing import Any

from django import forms

from .registry import get_available_commands


class StartCommandForm(forms.Form):
    """Форма для POST ``/command-runner/start/``."""

    command = forms.CharField(
        max_length=200,
        help_text="Имя management-команды из белого списка.",
    )
    args = forms.CharField(
        required=False,
        help_text=(
            "Позиционные и --именованные аргументы через пробел. "
            "Значения с пробелами — в кавычках: '--name \"Hello World\"'."
        ),
    )

    def clean_command(self) -> str:
        """Проверяет, что команда входит в белый список."""
        name: str = self.cleaned_data["command"]
        allowed = {c["name"] for c in get_available_commands()}
        if name not in allowed:
            raise forms.ValidationError("Команда не разрешена.")
        return name

    def clean_args(self) -> list[str]:
        """Разбирает строку аргументов на токены через :func:`shlex.split`."""
        raw: str = self.cleaned_data.get("args", "") or ""
        try:
            tokens: list[str] = shlex.split(raw)
        except ValueError as exc:
            raise forms.ValidationError("Не удалось разобрать аргументы") from exc
        return tokens

    def split_args_kwargs(self) -> tuple[list[str], dict[str, Any]]:
        """Разделяет токены на позиционные аргументы и именованные kwargs.

        Возвращает кортеж ``(positional, kwargs)``. Именованные аргументы
        извлекаются в соответствии с правилами ``argparse`` (см. докстринг
        модуля).
        """
        tokens: list[str] = self.cleaned_data["args"]
        positional: list[str] = []
        kwargs: dict[str, Any] = {}
        i = 0
        while i < len(tokens):
            tok = tokens[i]
            if tok == "--":
                positional.extend(tokens[i + 1 :])
                break
            if tok.startswith("--"):
                if "=" in tok:
                    key, val = tok[2:].split("=", 1)
                    kwargs[key] = val
                    i += 1
                elif i + 1 < len(tokens) and not tokens[i + 1].startswith("--"):
                    kwargs[tok[2:]] = tokens[i + 1]
                    i += 2
                else:
                    kwargs[tok[2:]] = True
                    i += 1
            else:
                positional.append(tok)
                i += 1
        return positional, kwargs
