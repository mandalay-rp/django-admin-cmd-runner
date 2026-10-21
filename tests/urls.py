"""URL-конфиг для тестов: подключает маршруты admin_cmd_runner."""

from django.urls import include, path

urlpatterns = [
    path("admin/", __import__("django.contrib.admin", fromlist=["site"]).site.urls),
    path("admin-cmd-runner/", include("admin_cmd_runner.urls")),
]
