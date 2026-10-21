"""Общие хелперы и базовый класс для тестов ``command_runner``."""

from unittest.mock import MagicMock

from django.test import SimpleTestCase, override_settings

LOCMEM_CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
    },
}


@override_settings(CACHES=LOCMEM_CACHES)
class CacheTestCase(SimpleTestCase):
    """``SimpleTestCase`` с изолированным in-memory кэшем.

    Перед каждым тестом кэш очищается, чтобы тесты не влияли друг на друга.
    """

    def setUp(self) -> None:
        """Очищает кэш перед каждым тестом."""
        super().setUp()
        from django.core.cache import cache
        cache.clear()


def make_staff_user() -> MagicMock:
    """Возвращает mock-пользователя с правами staff."""
    user = MagicMock()
    user.is_active = True
    user.is_staff = True
    user.is_authenticated = True
    return user
