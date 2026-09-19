# Field Service CRM / A3 Platform

Модульная CRM и операционная платформа для сервисных и локальных бизнесов:
заявки, клиенты, сотрудники, календарь, финансы, payroll, SLA, автоматизации,
A3 Ops Center и AI-ready аналитика.

## Стек

- FastAPI
- SQLite для локальной разработки, PostgreSQL для production
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
- `DATABASE_BACKEND` - `sqlite` или `postgresql`
- `DATABASE_URL` - строка подключения PostgreSQL
- `POSTGRESQL_EXPERIMENTAL=1` - явное подтверждение PostgreSQL cutover
- `PG_DUMP_BIN`, `PG_RESTORE_BIN` - пути к PostgreSQL client tools при необходимости
- `POSTGRES_BACKUP_TIMEOUT_SECONDS` - лимит backup/restore, по умолчанию `300`
- `OBJECT_STORAGE_BACKEND` - `local` или `s3`
- `S3_BUCKET`, `S3_REGION`, `S3_ENDPOINT_URL`, `S3_PREFIX` - S3-хранилище
- `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY` - ключи, если нет IAM role
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
SQLite-версию. Добавлены psycopg adapter, перенос общей схемы и полный
PostgreSQL application smoke в CI. Также добавлен защищённый перенос данных:
dry-run, согласованный SQLite snapshot, точная сверка строк и проверка
изоляции компаний. Конкурентные A3, календарные и automation-транзакции
защищены PostgreSQL advisory locks; partial indexes проверяются двумя
параллельными сессиями. PostgreSQL backup создаётся через `pg_dump` из
согласованного snapshot, а restore drill разворачивает его в одноразовую базу
и сверяет структуру и количество строк. SQLite остаётся локальным backend по
умолчанию.

PostgreSQL требует явного `POSTGRESQL_EXPERIMENTAL=1`. Боевой переход выполняют
после репетиции миграции на production-копии и успешного restore drill. Ошибки
конфигурации не выводят строку подключения в лог. Текущий статус и следующий
шаг видны на страницах `/system` и `/platform/readiness`. Подробный порядок:
`docs/postgresql_migration.md`.

Проверка миграции без записи в PostgreSQL:

```bash
export DATABASE_URL='postgresql://user:password@host:5432/field_service'
python3 scripts/migrate_sqlite_to_postgresql.py --sqlite /path/to/crm.db
```

Запись разрешается только явным флагом `--execute` и только в пустую целевую
базу или схему. Повтор команды с тем же источником проверяет результат без
повторного копирования.

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
- `GET /ready` - конфигурация backend, проверка базы, ключевые таблицы, uploads

В PostgreSQL-режиме `/health` проверяет подключение, а `/ready` также проверяет
конфигурацию, ключевые таблицы и доступность файлового хранилища.

## S3-хранилище

При `OBJECT_STORAGE_BACKEND=s3` фото заявок, файлы клиентов и аудио звонков
сохраняются в S3-совместимом bucket. Новые резервные копии автоматически
зеркалируются в `backups/`; PostgreSQL manifest хранится рядом с dump.
Существующие локальные файлы переносятся dry-run-first командой
`scripts/sync_files_to_s3.py`. Подробности: `docs/object_storage.md`.

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
- `tests/smoke_object_storage.py`
- `tests/smoke_postgresql.py`, `tests/smoke_postgresql_migration.py`,
  `tests/smoke_postgresql_concurrency.py`,
  `tests/smoke_postgresql_backup.py` и полный `tests/smoke_app.py` на PostgreSQL 16

## Документы

- [Production Launch Checklist](docs/production_launch_checklist.md)
- [Object Storage](docs/object_storage.md)
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
