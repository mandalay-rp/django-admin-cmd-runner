# Changelog

Все значимые изменения проекта документируются в этом файле.
Формат основан на [Keep a Changelog](https://keepachangelog.com/ru/1.1.0/),
проект следует [Semantic Versioning](https://semver.org/lang/ru/).

## [Unreleased]

## [0.2.0] - 2026-10-21

### Added

- Первый публичный релиз.
- Запуск management-команд через staff-страницу `/admin-cmd-runner/`.
- Парсер аргументов в стиле shell (`shlex.split`) с автоматическим
  приведением типов kwargs по `add_argument(type=...)`.
- Real-time мониторинг: статус, прогресс-бар, лог (polling раз в секунду).
- Остановка выполнения: `job.cancel`/`revoke` для queued-задач,
  `send_stop_job_command` + `kill_horse` для started (RQ),
  `revoke(terminate=True)` для Celery.
- Поддержка бэкендов **RQ** и **Celery** (`ADMIN_CMD_RUNNER_QUEUE`).
- Базовый класс `ReporterCommand` для команд с прогрессом и stop.
- Демо-команда `demo_long_command`.
- Unit-тесты (покрытие ≥70%).

## [0.2.1] - 2026-10-21

### Fixed
- Поправлен путь к шаблону страницы запуска приложения (monitory.html).

## [0.3.0] - 2026-10-21

### Fixed
- Добавлено определение при чтении лога сообщения - из stdout оно (шаг пройден успешно) или из stderr(ошибки при выполнении шага).
- Добавлены тесты.
- Правки найденных багов.
