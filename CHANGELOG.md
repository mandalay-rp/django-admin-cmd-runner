# Changelog

Все значимые изменения проекта документируются в этом файле.
Формат основан на [Keep a Changelog](https://keepachangelog.com/ru/1.1.0/),
проект следует [Semantic Versioning](https://semver.org/lang/ru/).

## [Unreleased]

## [0.1.0] - 2026-10-21

### Added

- Первый публичный релиз.
- Запуск management-команд через staff-страницу `/command-runner/`.
- Парсер аргументов в стиле shell (`shlex.split`) с автоматическим
  приведением типов kwargs по `add_argument(type=...)`.
- Real-time мониторинг: статус, прогресс-бар, лог (polling раз в секунду).
- Остановка выполнения: `job.cancel`/`revoke` для queued-задач,
  `send_stop_job_command` + `kill_horse` для started (RQ),
  `revoke(terminate=True)` для Celery.
- Поддержка бэкендов **RQ** и **Celery** (`COMMAND_RUNNER_QUEUE`).
- Базовый класс `ReporterCommand` для команд с прогрессом и stop.
- Демо-команда `demo_long_command`.
- Unit-тесты (покрытие ≥70%).
