# Production Launch Checklist

## 1. Environment

Set these variables before production deploy:

- `ENV=production`
- `SECRET_KEY` with a long random value
- `COOKIE_SECURE=1`
- `AUTOMATION_CRON_SECRET` with a long random value
- `BOT_TOKEN` and `CHAT_ID` if Telegram alerts are enabled
- `DATA_DIR` if the server uses a mounted persistent volume
- `DATABASE_BACKEND=sqlite` while the PostgreSQL migration is unfinished

Do not attach `DATABASE_URL` or enable `POSTGRESQL_EXPERIMENTAL` on the
application service until the full PostgreSQL application smoke, data migration
and restore drill are complete. The current guardrail deliberately stops
startup instead of silently falling back to SQLite when PostgreSQL is requested.

Before a PostgreSQL cutover:

- rehearse `scripts/migrate_sqlite_to_postgresql.py` on a verified production
  copy and a new empty PostgreSQL database;
- record the source fingerprint, table count, row count and duration;
- stop application writes before creating the final SQLite backup;
- run the migration dry run, then repeat it with `--execute`;
- run the same `--execute` command again and require
  `"already_migrated": true` with clean verification;
- keep the SQLite backup until the PostgreSQL-native restore drill succeeds.

Railway normally sets deployment metadata automatically:

- `RAILWAY_ENVIRONMENT`
- `RAILWAY_ENVIRONMENT_NAME`
- `RAILWAY_GIT_COMMIT_SHA`
- `RAILWAY_GIT_BRANCH`
- `RAILWAY_DEPLOYMENT_ID`
- `RAILWAY_SERVICE_NAME`

## 2. Local Checks Before Push

Run:

```bash
./quick_check.sh
python3 tests/smoke_security.py
```

With a disposable PostgreSQL test database configured, also run:

```bash
python3 tests/smoke_postgresql_migration.py
python3 tests/smoke_postgresql_concurrency.py
```

Optional HTTP check against a running server:

```bash
BASE=http://127.0.0.1:8000 ./quick_check.sh
```

## 3. Deploy Checks

After deploy, check:

- `GET /health`
- `GET /ready`
- `/system` as admin
- `/platform/readiness` as superadmin
- `/backup` as superadmin

Expected:

- `/health` returns `200`
- `/ready` returns `200`
- `/system` shows no critical production blockers
- `/system` shows the expected database backend and no configuration conflict
- backups are visible and restore check is available

## 4. Automation Cron

Protected cron endpoints require the `x-automation-secret` header:

- `POST /automation/cron/ai-digest`
- `POST /automation/cron/calendar-plans`
- `POST /automation/cron/calendar-plans/watchdog`

Example:

```bash
curl -X POST \
  -H "x-automation-secret: $AUTOMATION_CRON_SECRET" \
  https://your-domain.example/automation/cron/ai-digest
```

## 5. Rollback Signals

Pause rollout if any of these happen:

- `/ready` returns `503`
- `/system` shows critical runtime errors
- database quick check fails
- database backend configuration is invalid or PostgreSQL cutover is incomplete
- uploads are not writable
- login or session checks fail
- company isolation smoke tests fail

## 6. Safe Release Rule

Do not launch a production update unless:

- CI is green
- local smoke checks pass
- `SECRET_KEY` is not default
- backups are available
- restore check is clean
- `/health` and `/ready` are green after deploy
