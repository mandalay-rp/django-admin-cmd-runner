# Command Runner

Читать на [English](README.md)

Django-приложение для запуска management-команд из админки с мониторингом
выполнения в реальном времени и возможностью принудительной остановки.

## Возможности

- Запуск любой management-команды Django из белого списка через веб-интерфейс.
- Передача позиционных и именованных аргументов в формате shell
  (`--steps 5 --name "Hello World"`).
- Мониторинг выполнения в реальном времени: статус, прогресс-бар, лог.
- Перехват stdout/stderr команды в лог запуска.
- Остановка выполнения: задачи в очереди снимаются мгновенно
  (`job.cancel` для RQ, `revoke` для Celery); выполняющиеся задачи
  убиваются (`send_stop_job_command` / `kill_horse` для RQ,
  `revoke(terminate=True)` для Celery).
- Поддержка двух бэкендов очередей: **Celery** и **RQ** (выбор в настройках).
- Хранение состояния и логов в общем кэше (Redis).
- Доступ только для staff-пользователей.
- Ограничение: одновременно выполняется только одна команда
  (глобальный лок в Redis).

## Требования

- Python 3.10+
- Django 3.2+
- Redis (для кэша и очереди)
- Один из бэкендов очереди: `celery` + настроенный брокер (Redis/RabbitMQ)
  или `rq` (использует Redis)

## Установка

### 1. Установите зависимости

```bash
pip install django django-redis redis
# для RQ:
pip install rq
# для Celery:
pip install celery
```

### 2. Скопируйте приложение

Скопируйте пакет `admin_cmd_runner/` в ваш проект (например, в
`your_project_name/apps/admin_cmd_runner/`) и добавьте его в `INSTALLED_APPS`:

```python
INSTALLED_APPS = [
    # ...
    "admin_cmd_runner",
]
```

### 3. Настройте `settings.py`

```python
# Выбор бэкенда: "celery" или "rq"
ADMIN_CMD_RUNNER_QUEUE = "rq"

# Redis для RQ-очереди
ADMIN_CMD_RUNNER_RQ_REDIS_URL = "redis://redis:6379/2"
ADMIN_CMD_RUNNER_RQ_QUEUE = "default"

# Для django-rq worker: без этого блока воркер подключается к localhost:6379/0
RQ_QUEUES = {
    "default": {"URL": ADMIN_CMD_RUNNER_RQ_REDIS_URL},
    "high":    {"URL": ADMIN_CMD_RUNNER_RQ_REDIS_URL},
}

# Общий кэш для состояния (обязательно Redis или Memcached)
CACHES = {
    "default": {
        "BACKEND": "django_redis.cache.RedisCache",
        "LOCATION": "redis://redis:6379/1",
        "OPTIONS": {
            "CLIENT_CLASS": "django_redis.client.DefaultClient",
        },
    },
}

# Белый список команд
ADMIN_CMD_RUNNER_COMMANDS = [
    {
        "name": "demo_long_command",
        "label": "Демонстрационная долгая команда",
        "args_help": "--steps N",
    },
    # ...
]
```

### 4. Подключите URL-маршруты

В `urls.py` проекта:

```python
from django.urls import include, path

urlpatterns += [
    path("admin-cmd-runner/", include("admin_cmd_runner.urls")),
]
```

### 5. Запустите воркер

Для RQ:

```bash
# голый RQ:
rq worker default

# или через django-rq:
python manage.py rqworker default
```

Для Celery:

```bash
celery -A proj worker -l info
```

### 6. Запустите веб-сервер

```bash
python manage.py runserver
```

## Использование

1. Откройте `/admin-cmd-runner/` под staff-пользователем.
2. Выберите команду из выпадающего списка.
3. Введите аргументы (необязательно): позиционные `arg1 arg2`; именованные
   `--steps 5 --name "Hello World"`; флаги `--verbose` (без значения → `True`);
   всё после `--` считается позиционным.
4. Нажмите «Запустить». Откроется страница запуска с прогресс-баром
   и логом, обновляющимся раз в секунду.
5. Нажмите «Остановить» для принудительной остановки. Для задач в
   очереди остановка происходит мгновенно; для выполняющихся —
   через 1–3 секунды (зависит от бэкенда).

## Тестирование

Тесты не требуют Redis, БД или установленных `rq`/`celery`: кэш
подменяется на `LocMemCache` через `override_settings`, а тесты бэкендов
пропускаются (`skipUnless`), если соответствующая библиотека не установлена.

### Запуск в проекте

Если `admin_cmd_runner` подключён в `INSTALLED_APPS` вашего Django-проекта:

```bash
# все тесты приложения (по app label)
python manage.py test admin_cmd_runner

# только пакет тестов
python manage.py test admin_cmd_runner.tests

# конкретный модуль
python manage.py test admin_cmd_runner.tests.test_store

# конкретный тест-класс
python manage.py test admin_cmd_runner.tests.test_store.LockTests

# конкретный метод
python manage.py test admin_cmd_runner.tests.test_store.LockTests.test_acquire_and_get
```

Если приложение подключено по полному пути (`your_project_name.apps.admin_cmd_runner`),
используйте label или полный путь к пакету тестов:

```bash
python manage.py test apps_admin_cmd_runner
# или
python manage.py test your_project_name.apps.admin_cmd_runner.tests
```

### Запуск при разработке пакета (uv)

Из корня репозитория (там, где `pyproject.toml`):

```bash
# установить uv (один раз)
curl -LsSf https://astral.sh/uv/install.sh | sh

# создать виртуальное окружение и установить пакет
# в editable-режиме со всеми dev-зависимостями
uv sync --extra dev

# тесты с покрытием (конфиг pytest — в pyproject.toml)
uv run pytest admin_cmd_runner/tests

# только линтер
uv run ruff check admin_cmd_runner tests

# только проверка типов
uv run mypy admin_cmd_runner

# всё сразу (lint + typecheck + test)
uv run ruff check admin_cmd_runner tests \
  && uv run mypy admin_cmd_runner \
  && uv run pytest admin_cmd_runner/tests
```

Управление зависимостями:

```bash
# добавить dev-зависимость
uv add --dev pytest-xdist

# обновить lock-файл без установки
uv lock

# синхронизировать окружение с lock-файлом
uv sync --extra dev

# конкретная версия Python
uv python install 3.12
uv venv --python 3.12
```

### Покрытие

Порог покрытия задан в `pyproject.toml` (`--cov-fail-under=70`). HTML-отчёт:

```bash
uv run pytest admin_cmd_runner/tests --cov-report=html
open htmlcov/index.html
```

### Запуск в Docker

```bash
docker compose exec django python manage.py test admin_cmd_runner
```

## Архитектура

```
admin_cmd_runner/
├── __init__.py             — описание приложения
├── apps.py                 — AppConfig
├── admin.py                — без моделей, только подсказка по меню
├── urls.py                 — URL-маршруты
├── views.py                — монитор, запуск, остановка, статус
├── forms.py                — форма и парсер аргументов
├── registry.py             — реестр доступных команд из settings
├── store.py                — состояние и логи в общем кэше
├── reporter.py             — Reporter для прогресса и остановки
├── jobs.py                 — транспортно-независимое исполнение команды
├── queue/
│   ├── __init__.py         — фабрика бэкендов
│   ├── base.py             — абстрактный интерфейс
│   ├── celery_backend.py   — реализация на Celery
│   └── rq_backend.py       — реализация на RQ
├── management/
│   └── commands/
│       ├── _base.py        — ReporterCommand с доступом к reporter
│       └── demo_long_command.py — демо-команда с прогрессом и stop
└── templates/
    └── admin_cmd_runner/
        └── monitor.html    — UI с polling
```

### Поток выполнения

1. **Запуск.** `start_run` валидирует форму, захватывает глобальный лок
   (`cache.add`), создаёт состояние (`status=queued`), ставит задачу в
   бэкенд очереди и сохраняет `task_id`.
2. **Исполнение.** Воркер вызывает `execute_command`, которая приводит
   типы `kwargs` по `add_argument(type=...)`, ставит `status=running`,
   устанавливает `Reporter` в качестве stdout, выполняет команду через
   `call_command` и в `finally` фиксирует терминальный статус и снимает лок.
3. **Мониторинг.** Фронт раз в секунду запрашивает `status_api`, который
   возвращает состояние и новые строки лога (`since=N`).
4. **Остановка.** `stop_run` выставляет флаг `stop`, вызывает
   `backend.revoke(task_id)`: для `queued` — задача снимается, статус
   сразу `stopped`; для `started` — отправляется команда остановки,
   статус `stopping`, а финализация в `stopped` происходит в `status_api`
   по факту смерти процесса в бэкенде (или по таймауту `STOP_GRACE_SECONDS`).

### Хранилище (Redis)

| Ключ                    | Назначение                                  | TTL    |
|-------------------------|---------------------------------------------|--------|
| `admin_cmd_runner:lock`           | id активного запуска (один на проект)       | 24 ч   |
| `admin_cmd_runner:state:<run_id>` | состояние запуска (status, progress, error) | 24 ч   |
| `admin_cmd_runner:log:<run_id>`   | лог (список строк, ограничен 2000 записей)  | 24 ч   |
| `admin_cmd_runner:stop:<run_id>`  | флаг запроса остановки                      | 6 ч    |
| `admin_cmd_runner:task:<run_id>`  | task_id/job_id в бэкенде                    | 24 ч   |

**Важно:** кэш должен быть общим для всех процессов (web и worker),
поэтому `LocMemCache` не подходит — нужен Redis или Memcached.

## Написание собственных команд

Наследуйтесь от `ReporterCommand`, чтобы получить доступ к
`self.reporter` (прогресс, лог, проверка остановки):

```python
from admin_cmd_runner.management.commands._base import ReporterCommand


class Command(ReporterCommand):
    help = "Что делает команда"

    def add_arguments(self, parser):
        parser.add_argument("--count", type=int, default=10)

    def handle(self, *args, **options):
        count = options["count"]
        for i in range(count):
            self.reporter.check_stop()  # поднимет CommandStopRequested при stop
            self.stdout.write(f"Шаг {i + 1}/{count}")  # попадёт в лог
            self.reporter.progress(
                int((i + 1) / count * 100),
                f"Шаг {i + 1}/{count}",
            )
            # ... полезная работа ...
```

Если команда не наследует `ReporterCommand`, она всё равно попадёт
в лог (stdout перехватывается), но не сможет обновлять прогресс и
кооперативно проверять флаг остановки (останется только жёсткий kill).

## Docker Compose

Пример для запуска вместе с Redis и воркером RQ:

```yaml
services:
  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"

  django:
    build: .
    command: python manage.py runserver 0.0.0.0:8000
    volumes:
      - .:/code
    depends_on:
      - redis

  rq:
    build: .
    command: python manage.py rqworker default
    environment:
      - DJANGO_SETTINGS_MODULE=your_project_name.settings.dev
      - PYTHONUNBUFFERED=1
    volumes:
      - .:/code
    depends_on:
      - redis
      - django
    restart: "always"
    # ВАЖНО: не добавляйте stdin_open: true — иначе rqworker
    # получит EOF на stdin и будет завершаться каждые ~30 секунд.
```

## Известные ограничения

- Одновременно выполняется только одна команда (глобальный лок).
- Стандартный `int`/`float`-парсинг kwargs работает через
  `add_argument(type=...)` команды; для кастомных типов (например
  `datetime`) используйте callable-`type`, он будет вызван.
- Лог ограничен 2000 строками на запуск (старые обрезаются).
- `kill_horse` в RQ не даёт выполниться `finally` — финализация
  статуса происходит на стороне web-процесса через `status_api`.
- 1–2 лишних запроса `/status/` после нажатия «Остановить» —
  неизбежны: они попадают в окно между кликом и фактической
  смертью процесса воркера.
