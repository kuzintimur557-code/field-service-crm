# PostgreSQL Migration

## Goal

Move production data from SQLite to PostgreSQL without changing local
development until the new backend passes the same application smoke checks.

## Current phase: connection and schema foundation

SQLite remains the default runtime. The PostgreSQL foundation now includes:

- `DATABASE_BACKEND=sqlite` keeps the current runtime;
- `DATABASE_URL` is treated as a cutover request;
- a psycopg adapter for placeholders, row access and generated identifiers;
- translation for the SQLite SQL forms used by schema initialization;
- idempotent schema creation and sequence synchronization on PostgreSQL;
- schema and complete application smoke checks on PostgreSQL 16 in CI;
- backend-aware `/health` and `/ready` database checks;
- `POSTGRESQL_EXPERIMENTAL=1` as an explicit non-production opt-in;
- unsupported, conflicting or incomplete PostgreSQL settings stop startup;
- diagnostics expose only the backend name and never the URL, host, user or
  password;
- production readiness remains blocked until application and migration smoke
  checks are complete.

## Known compatibility work

The application uses direct SQL and depends on SQLite behavior in several
places. The adapter must handle these areas before cutover:

1. Add an idempotent SQLite-to-PostgreSQL data migration with row-count and
   company-isolation verification.
2. Validate partial indexes and transaction locking used by automation
   monitors under concurrent PostgreSQL sessions.
3. Replace the SQLite backup fixture with PostgreSQL-native backup creation and
   restore drills. The application smoke currently isolates the legacy backup
   lifecycle in a temporary SQLite database.

## Safe sequence

1. Keep the connection adapter and application smoke green on both backends.
2. Add an idempotent SQLite-to-PostgreSQL data migration with row-count and
   company-isolation verification.
3. Add PostgreSQL-native backup and restore checks.
4. Rehearse migration on a production copy and record timings and rollback
   criteria.
5. Set `DATABASE_BACKEND=postgresql` and `DATABASE_URL` only during the approved
   cutover window.
6. Keep the verified SQLite backup until the PostgreSQL restore drill passes.

## Schema smoke

The smoke requires a disposable PostgreSQL database and refuses to run without
the explicit experimental flag:

```bash
DATABASE_BACKEND=postgresql \
POSTGRESQL_EXPERIMENTAL=1 \
DATABASE_URL=postgresql://user:password@127.0.0.1:5432/field_service_test \
python3 tests/smoke_postgresql.py
```

It initializes the schema twice, verifies core tables and A3 quality SLA
columns, checks idempotent development seeds, verifies generated IDs and row
access, then checks PostgreSQL health and readiness responses. `/health` must
pass, while `/ready` remains blocked by `database_release_support` until the
data migration and PostgreSQL-native backup drill are complete. CI then runs
the complete application smoke against the same disposable PostgreSQL service;
only the legacy file-backup lifecycle uses a temporary SQLite fixture.

## Exit criteria

- all smoke and security checks pass on both backends;
- `/health` and `/ready` report PostgreSQL without exposing connection data;
- table and row counts match the source database;
- tenant-isolation checks pass after migration;
- create, update, archive, automation and cron flows work on PostgreSQL;
- a PostgreSQL backup can be restored into a clean database;
- rollback steps and the allowed data-loss window are documented.
