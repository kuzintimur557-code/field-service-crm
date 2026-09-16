# Field Service CRM / A3 Platform

Модульная CRM и операционная платформа для сервисных и локальных бизнесов:
заявки, клиенты, сотрудники, календарь, финансы, payroll, SLA, автоматизации,
A3 Ops Center и AI-ready аналитика.

## Стек

- FastAPI
- SQLite (текущий backend; идёт подготовка миграции на PostgreSQL)
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
- `DATABASE_BACKEND` - сейчас должен оставаться `sqlite`
- `DATABASE_URL` - будущая строка PostgreSQL; до завершения adapter не включать
- `BOT_TOKEN`
- `CHAT_ID`
- `CALENDAR_INCIDENT_RESPONSE_MINUTES` - по умолчанию `30`
- `CALENDAR_INCIDENT_ESCALATION_MINUTES` - по умолчанию `30`
- `CALENDAR_INCIDENT_RECOVERY_MINUTES` - по умолчанию `120`
- `CALENDAR_WATCHDOG_STALE_HOURS` - по умолчанию `6`
- `CALENDAR_SCHEDULER_STUCK_MINUTES` - по умолчанию `30`
- `A3_QUALITY_ALERT_RESPONSE_HOURS` - срок реакции на сигнал качества A3, `4` ч.
- `A3_QUALITY_ALERT_RESOLUTION_HOURS` - срок устранения, `24` ч.
- `A3_QUALITY_ALERT_ESCALATION_COOLDOWN_HOURS` - интервал повторной эскалации, `12` ч.

Сроки SLA отсчитываются от первого обнаружения и сохраняются для каждого
эпизода. Повторное открытие того же сигнала сохраняет сроки и историю
эскалаций; новый эпизод получает новые сроки. Для старых записей сроки
сохраняются при первой проверке или изменении состояния. Настройки принимают
целые значения от 1 до 720 часов; срок устранения не может быть короче реакции.

Проверку можно запустить в центре сигналов кнопкой «Проверить SLA» или через
`POST /api/platform/a3-health/incidents/actions/quality-alerts/sla/run`
(только superadmin). Сводка: `GET /api/platform/a3-health/incidents/actions/quality-alerts/sla`.
Cron `POST /automation/cron/a3-incident-actions` сначала обновляет сигналы
качества, затем проверяет SLA: автоматически закрытые сигналы не эскалируются.
Эскалация уведомляет активных superadmin в приложении и в Telegram, если у них
указан чат и настроен бот. Повторный запуск до истечения интервала не дублирует
уведомления; результат доступен в `quality_sla_summary`.

Railway metadata обычно задаётся автоматически:

- `RAILWAY_ENVIRONMENT`
- `RAILWAY_GIT_COMMIT_SHA`
- `RAILWAY_GIT_BRANCH`
- `RAILWAY_DEPLOYMENT_ID`
- `RAILWAY_SERVICE_NAME`

## Миграция на PostgreSQL

Переход выполняется по этапам, чтобы не потерять данные и не сломать текущую
SQLite-версию. Первый этап добавляет явную конфигурацию backend и блокирует
случайное использование `DATABASE_URL`, которое приложение ещё не обслуживает.
Текущий релиз продолжает работать с `DATABASE_BACKEND=sqlite`.

Если задать PostgreSQL раньше завершения adapter, приложение завершит запуск с
безопасной ошибкой конфигурации и не выведет строку подключения в лог. Текущий
статус миграции и следующий шаг видны на страницах `/system` и
`/platform/readiness`. Подробный порядок: `docs/postgresql_migration.md`.

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
python3 -m compileall -q app tests
python3 tests/smoke_app.py
python3 tests/smoke_security.py
```

## Production endpoints

Публичные:

- `GET /health` - приложение и база отвечают
- `GET /ready` - конфигурация backend, SQLite quick check, ключевые таблицы, uploads

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
- `POST /automation/cron/a3-autonomous` - выполняет автономный цикл A3
- `POST /automation/cron/a3-watchdog` - независимо контролирует запуски A3

Для A3 настройте два задания: основной цикл и watchdog. Watchdog должен
вызываться отдельным внешним расписанием, чтобы сообщить об остановке
основного задания.

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
