from django.urls import path

from . import views

app_name = "command_runner"

urlpatterns = [
    path("", views.monitor_page, name="monitor_root"),
    path("start/", views.start_run, name="start"),
    path("<str:run_id>/", views.monitor_page, name="monitor"),
    path("<str:run_id>/stop/", views.stop_run, name="stop"),
    path("<str:run_id>/status/", views.status_api, name="status"),
]
