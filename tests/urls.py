"""URL-конфиг для тестов: подключает маршруты command_runner."""

from django.urls import include, path

urlpatterns = [
    path("admin/", __import__("django.contrib.admin", fromlist=["site"]).site.urls),
    path("command-runner/", include("command_runner.urls")),
]
