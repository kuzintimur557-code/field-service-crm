# Field Service CRM / A3 Platform

Модульная CRM и операционная платформа для сервисных и локальных бизнесов:
заявки, клиенты, сотрудники, календарь, финансы, payroll, SLA, автоматизации,
A3 Ops Center и AI-ready аналитика.

## Стек

- FastAPI
- SQLite
- Jinja2
- Railway
- GitHub Actions

## Основные возможности

- multi-company архитектура
- роли `superadmin`, `boss`, `manager`, `worker`
- signed session auth
- bcrypt пароли
- company isolation
- заявки, клиенты, сотрудники
- worker panel
- календарь и диспетчеризация
- recurring jobs
- SLA и SLA analytics
- финансы, payroll, finance summary
- custom fields
- уведомления
- Telegram integration
- A3 automation engine
- workflow runtime, timeline, replay
- system diagnostics, backups, readiness checks

## Локальный запуск

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Локальный адрес:

```text
http://127.0.0.1:8000
```

Если нужен другой порт:

```bash
uvicorn app.main:app --reload --port 8011
```

## Переменные окружения

Пример лежит в:

```text
.env.example
```

Для production обязательно задать:

- `ENV=production`
- `SECRET_KEY`
- `COOKIE_SECURE=1`
- `AUTOMATION_CRON_SECRET`

Опционально:

- `DATA_DIR`
- `BOT_TOKEN`
- `CHAT_ID`

Railway metadata обычно задаётся автоматически:

- `RAILWAY_ENVIRONMENT`
- `RAILWAY_GIT_COMMIT_SHA`
- `RAILWAY_GIT_BRANCH`
- `RAILWAY_DEPLOYMENT_ID`
- `RAILWAY_SERVICE_NAME`

## Проверки перед коммитом

Быстрая проверка:

```bash
./quick_check.sh
```

Проверка безопасности:

```bash
python3 tests/smoke_security.py
```

Проверка поднятого локального сервера:

```bash
BASE=http://127.0.0.1:8000 ./quick_check.sh
```

Полный локальный smoke:

```bash
python3 -m py_compile app/main.py app/database.py tests/smoke_app.py tests/smoke_security.py
python3 tests/smoke_app.py
python3 tests/smoke_security.py
```

## Production endpoints

Публичные:

- `GET /health` - приложение и база отвечают
- `GET /ready` - SQLite quick check, ключевые таблицы, uploads

Админские:

- `/system` - диагностика системы
- `/system/export` - CSV отчёт системы
- `/backup` - резервные копии
- `/platform/readiness` - готовность релиза

## Cron endpoints

Защищены заголовком `x-automation-secret`.

- `POST /automation/cron/ai-digest`
- `POST /automation/cron/calendar-plans`
- `POST /automation/cron/calendar-plans/watchdog`

Пример:

```bash
curl -X POST \
  -H "x-automation-secret: $AUTOMATION_CRON_SECRET" \
  https://your-domain.example/automation/cron/ai-digest
```

## CI

GitHub Actions workflow:

```text
.github/workflows/ci.yml
```

CI запускает:

- установку зависимостей
- Python compile check
- `tests/smoke_app.py`
- `tests/smoke_security.py`

## Документы

- [Production Launch Checklist](docs/production_launch_checklist.md)
- [UI Russian Language Guide](docs/ui_language_ru.md)
- [Changelog](CHANGELOG.md)

## Правило разработки

Работаем маленькими safe diff:

1. backend/helper
2. template/UI
3. smoke tests
4. `python3 -m py_compile ...`
5. `git diff --check`
6. smoke checks
7. отдельный commit
