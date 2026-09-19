# PostgreSQL Migration

## Goal

Move production data from SQLite to PostgreSQL without changing local
development until the new backend passes the same application smoke checks.

## Current phase: production rehearsal and cutover preparation

SQLite remains the default runtime. The PostgreSQL foundation now includes:

- `DATABASE_BACKEND=sqlite` keeps the current runtime;
- `DATABASE_URL` is treated as a cutover request;
- a psycopg adapter for placeholders, row access and generated identifiers;
- translation for the SQLite SQL forms used by schema initialization;
- idempotent schema creation and sequence synchronization on PostgreSQL;
- schema and complete application smoke checks on PostgreSQL 16 in CI;
- a dry-run-first SQLite-to-PostgreSQL migration command;
- consistent SQLite snapshots through the SQLite backup API;
- consistent PostgreSQL custom-format dumps from exported snapshots;
- archive catalog and manifest validation without exposing connection data;
- restore drills in disposable PostgreSQL databases with exact table row-count
  comparison and automatic cleanup;
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
- `/ready` supports PostgreSQL after schema, migration, concurrency, backup and
  restore smoke checks pass.

## Remaining operational work

The PostgreSQL application compatibility work is complete. Before cutover:

1. Rehearse migration and restore with a recent production copy.
2. Record duration, row totals, backup size, rollback deadline and responsible
   operator.
3. Confirm the production PostgreSQL role can create and drop the disposable
   restore-drill database, or provide a dedicated maintenance role with those
   permissions.

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
python3 tests/smoke_postgresql_backup.py
```

It initializes the schema twice, verifies core tables and A3 quality SLA
columns, checks idempotent development seeds, verifies generated IDs and row
access, then checks PostgreSQL health and readiness responses. The migration
smoke uses isolated PostgreSQL schemas to verify dry run, copy, exact data
comparison, safe repetition, changed-source refusal and tenant-isolation
refusal. The concurrency smoke opens simultaneous PostgreSQL sessions and
verifies advisory-lock serialization, independent lock scopes, A3 incident
deduplication, automation action idempotency and partial-index predicates.
The backup smoke creates a custom-format archive, validates its sidecar
manifest, restores it into a disposable database and compares every table's row
count. `/health` and `/ready` must both pass. CI then runs the complete
application smoke, including the native backup lifecycle, against the same
disposable PostgreSQL service.

## PostgreSQL backup operations

The `/backup` page uses `pg_dump` and `pg_restore` from `PATH`. Override their
paths with `PG_DUMP_BIN` and `PG_RESTORE_BIN` when the client tools are installed
elsewhere. `POSTGRES_BACKUP_TIMEOUT_SECONDS` defaults to 300 seconds.

The database role used by the application must have permission to read all
application tables. A restore drill also needs permission to create and drop a
temporary database. The dump command receives credentials through libpq
environment variables; URLs and passwords are not placed in command arguments,
manifests, status APIs or logs. Keep each `.dump` file together with its
`.dump.json` manifest; both are downloadable from `/backup`.

## Exit criteria

- all smoke and security checks pass on both backends;
- `/health` and `/ready` report PostgreSQL without exposing connection data;
- table and row counts match the source database;
- tenant-isolation checks pass after migration;
- create, update, archive, automation and cron flows work on PostgreSQL;
- a PostgreSQL backup can be restored into a clean database;
- rollback steps and the allowed data-loss window are documented.
