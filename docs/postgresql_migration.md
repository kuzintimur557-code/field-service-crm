# PostgreSQL Migration

## Goal

Move production data from SQLite to PostgreSQL without changing local
development until the new backend passes the same application smoke checks.

## Current phase: configuration guardrail

This release still uses SQLite. It now has one explicit source of truth:

- `DATABASE_BACKEND=sqlite` keeps the current runtime;
- `DATABASE_URL` is treated as a cutover request;
- unsupported, conflicting or premature PostgreSQL settings stop startup;
- diagnostics expose only the backend name and never the URL, host, user or
  password;
- production readiness remains blocked until PostgreSQL support is complete.

## Known compatibility work

The application uses direct SQL and depends on SQLite behavior in several
places. The adapter must handle these areas before cutover:

1. Parameter placeholders and row access by both column name and index.
2. Generated identifiers currently read through `lastrowid`.
3. Schema creation with `AUTOINCREMENT` and incremental column migrations with
   `PRAGMA table_info`.
4. SQLite forms such as `INSERT OR IGNORE`, `GROUP_CONCAT` and date functions.
5. Partial indexes and transaction locking used by automation monitors.
6. Health checks, backup creation and restore drills that currently operate on
   a local database file.

## Safe sequence

1. Add the PostgreSQL connection adapter and schema migrations.
2. Run the complete smoke suite against disposable SQLite and PostgreSQL
   databases in CI.
3. Add an idempotent SQLite-to-PostgreSQL data migration with row-count and
   company-isolation verification.
4. Add PostgreSQL-native backup and restore checks.
5. Rehearse migration on a production copy and record timings and rollback
   criteria.
6. Set `DATABASE_BACKEND=postgresql` and `DATABASE_URL` only during the approved
   cutover window.
7. Keep the verified SQLite backup until the PostgreSQL restore drill passes.

## Exit criteria

- all smoke and security checks pass on both backends;
- `/health` and `/ready` report PostgreSQL without exposing connection data;
- table and row counts match the source database;
- tenant-isolation checks pass after migration;
- create, update, archive, automation and cron flows work on PostgreSQL;
- a PostgreSQL backup can be restored into a clean database;
- rollback steps and the allowed data-loss window are documented.
