# PostgreSQL Migration

## Goal

Move production data from SQLite to PostgreSQL without changing local
development until the new backend passes the same application smoke checks.

## Current phase: PostgreSQL-native backup and restore

SQLite remains the default runtime. The PostgreSQL foundation now includes:

- `DATABASE_BACKEND=sqlite` keeps the current runtime;
- `DATABASE_URL` is treated as a cutover request;
- a psycopg adapter for placeholders, row access and generated identifiers;
- translation for the SQLite SQL forms used by schema initialization;
- idempotent schema creation and sequence synchronization on PostgreSQL;
- schema and complete application smoke checks on PostgreSQL 16 in CI;
- a dry-run-first SQLite-to-PostgreSQL migration command;
- consistent SQLite snapshots through the SQLite backup API;
- exact table counts, row counts, row checksums, ID bounds and company
  isolation checks before a migration is marked complete;
- resumable interrupted runs and verification-only repeated runs;
- transaction-scoped PostgreSQL advisory locks for A3 monitors, calendar
  incident operations and idempotent automation events;
- concurrent-session checks for partial unique indexes and duplicate-action
  protection;
- backend-aware `/health` and `/ready` database checks;
- `POSTGRESQL_EXPERIMENTAL=1` as an explicit non-production opt-in;
- unsupported, conflicting or incomplete PostgreSQL settings stop startup;
- diagnostics expose only the backend name and never the URL, host, user or
  password;
- production readiness remains blocked until the PostgreSQL-native backup and
  restore drill is complete.

## Known compatibility work

The application uses direct SQL and depends on SQLite behavior in several
places. This area remains before cutover:

1. Replace the SQLite backup fixture with PostgreSQL-native backup creation and
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

## Data migration command

Use a new, empty PostgreSQL database or schema. Set the target URL in the
environment so credentials do not appear in shell history:

```bash
export DATABASE_URL='postgresql://user:password@host:5432/field_service'
python3 scripts/migrate_sqlite_to_postgresql.py \
  --sqlite /path/to/verified/crm.db
```

Without `--execute`, the command is read-only. It creates a consistent
temporary SQLite snapshot, runs `PRAGMA integrity_check`, calculates a logical
fingerprint, checks every tenant table for missing or unknown `company_id`
values, checks core parent-child links for cross-company references, and
reports whether the PostgreSQL target is safe to use.

Run the copy only after the dry run reports `"can_execute": true`:

```bash
python3 scripts/migrate_sqlite_to_postgresql.py \
  --sqlite /path/to/verified/crm.db \
  --execute
```

The first execution refuses a PostgreSQL target that already contains tables.
It initializes the current application schema, removes only the bootstrap rows
created during that initialization, copies data in batches, synchronizes
sequences, and verifies row counts, row checksums and ID bounds. A migration is
recorded in `postgresql_migration_runs` only for that source fingerprint.

Repeating `--execute` with the same source performs verification without
writing the data again. An interrupted run with the same fingerprint resumes
from a clean target transaction. A changed source or an unmanaged non-empty
target is rejected. The command never prints `DATABASE_URL`.
Only one execution can hold the PostgreSQL migration lock at a time.

For the final cutover, stop application writes before taking the verified
SQLite backup used by this command. Rehearse the same commands on a production
copy first and record duration, row totals and the rollback deadline.

## Schema smoke

The smoke requires a disposable PostgreSQL database and refuses to run without
the explicit experimental flag:

```bash
export DATABASE_BACKEND=postgresql
export POSTGRESQL_EXPERIMENTAL=1
export DATABASE_URL=postgresql://user:password@127.0.0.1:5432/field_service_test
python3 tests/smoke_postgresql.py
python3 tests/smoke_postgresql_migration.py
python3 tests/smoke_postgresql_concurrency.py
```

It initializes the schema twice, verifies core tables and A3 quality SLA
columns, checks idempotent development seeds, verifies generated IDs and row
access, then checks PostgreSQL health and readiness responses. The migration
smoke uses isolated PostgreSQL schemas to verify dry run, copy, exact data
comparison, safe repetition, changed-source refusal and tenant-isolation
refusal. The concurrency smoke opens simultaneous PostgreSQL sessions and
verifies advisory-lock serialization, independent lock scopes, A3 incident
deduplication, automation action idempotency and partial-index predicates.
`/health` must
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
