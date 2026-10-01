# Production Launch Checklist

## 1. Environment

Set these variables before production deploy:

- `ENV=production`
- `SECRET_KEY` with a random value of at least 32 characters
- `COOKIE_SECURE=1`
- `TRUSTED_HOSTS` with the production domain or `APP_BASE_URL` with its HTTPS URL
- `CSRF_TRUSTED_ORIGINS` if browser requests legitimately use another origin
- `TRUST_PROXY_HEADERS=1` only when direct traffic is blocked by a trusted proxy
- `AUTOMATION_CRON_SECRET` with a long random value
- `INBOX_WEBHOOK_SECRET` with a long random value if email intake is enabled
- `BOT_TOKEN` and `CHAT_ID` if Telegram alerts are enabled
- `DATA_DIR` if the server uses a mounted persistent volume
- `DATABASE_BACKEND=postgresql` after the rehearsed cutover
- `DATABASE_URL` for the production PostgreSQL database
- `POSTGRESQL_EXPERIMENTAL=1` as the explicit cutover guard
- `OBJECT_STORAGE_BACKEND=s3`
- `S3_BUCKET`, region or custom endpoint, and provider credentials or IAM role
- background queue policy variables when the defaults do not fit the workload
- request and upload limits when the defaults do not fit the workload

Keep `DATABASE_BACKEND=sqlite` until the full PostgreSQL application smoke,
data-migration rehearsal and restore drill are complete. The guardrail stops
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

Before switching file storage to S3:

- run `scripts/sync_files_to_s3.py` without `--execute`;
- run it again with `--execute` and require `"ok": true`;
- create and download a task photo, client file, and call audio;
- create a database backup and require the external-copy status to be green;
- keep the local files until `/ready` and `/system` confirm S3 access.

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
python3 tests/smoke_production_security.py
python3 tests/smoke_release.py
```

With a disposable PostgreSQL test database configured, also run:

```bash
python3 tests/smoke_postgresql_migration.py
python3 tests/smoke_postgresql_concurrency.py
python3 tests/smoke_postgresql_backup.py
python3 tests/smoke_object_storage.py
python3 tests/smoke_background_jobs.py
python3 tests/smoke_error_monitoring.py
```

Optional HTTP check against a running server:

```bash
BASE=http://127.0.0.1:8000 ./quick_check.sh
```

## 3. Deploy Checks

Before the first production deploy, enable Railway **Wait for CI**, set the
healthcheck path to `/health`, set the timeout to `300` seconds and make
`Production release gate` a required GitHub check. See `docs/ci_cd.md`.

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
- `/docs`, `/redoc` and `/openapi.json` are unavailable in production
- a POST with an unrelated `Origin` returns `403`
- a request above `MAX_REQUEST_BYTES` returns `413`
- backups are visible and restore check is available
- the configured file-storage backend is available
- the latest backup has a valid external copy when S3 is enabled
- the background queue has no stale workers or failed jobs

## 4. Automation Cron

Protected cron endpoints require the `x-automation-secret` header:

- `POST /automation/cron/ai-digest`
- `POST /automation/cron/calendar-plans`
- `POST /automation/cron/calendar-plans/watchdog`
- `POST /automation/cron/background-jobs` every minute
- `POST /automation/cron/database-backup` daily
- `POST /automation/cron/subscription-reminders` daily

Example:

```bash
curl -X POST \
  -H "x-automation-secret: $AUTOMATION_CRON_SECRET" \
  https://your-domain.example/automation/cron/ai-digest
```

Use either the one-minute cron endpoint or a dedicated worker process:

```bash
python3 scripts/run_background_worker.py --watch
```

Do not run both unless concurrent workers are intentional. Atomic claims make
that safe, but one processing mode is simpler to operate.

## 5. Rollback Signals

Pause rollout if any of these happen:

- `/ready` returns `503`
- `/system` shows critical runtime errors
- database connection or integrity check fails
- database backend configuration is invalid or PostgreSQL cutover is incomplete
- uploads are not writable
- S3 bucket access or the off-site backup mirror fails
- the background queue reports stale or failed jobs
- login or session checks fail
- company isolation smoke tests fail

## 6. Safe Release Rule

Do not launch a production update unless:

- CI is green
- `Production release gate` is green
- local smoke checks pass
- `SECRET_KEY` is not default
- backups are available
- restore check is clean
- `/health` and `/ready` are green after deploy
