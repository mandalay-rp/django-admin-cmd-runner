"""Специальная регистрация в админке не требуется.

Страница мониторинга доступна staff-пользователям по URL
``/command-runner/`` (см. ``views.monitor_page``). Чтобы добавить
пункт меню в админку, переопределите ``admin/base_site.html``:

    {% extends "admin/base.html" %}
    {% block userlinks %}
        <a href="{% url 'command_runner:monitor_root' %}">Command Runner</a> /
        {{ block.super }}
    {% endblock %}
"""
