import os
import sqlite3
import sys
import tempfile
from pathlib import Path
from urllib.parse import urlencode
from unittest.mock import patch
from uuid import uuid4


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app import database  # noqa: E402
from app.postgresql_migration import (  # noqa: E402
    MIGRATION_LOCK_KEY,
    PostgreSQLDataMigrationError,
    migrate_sqlite_to_postgresql,
)


def _url_with_schema(database_url, schema):
    separator = "&" if "?" in database_url else "?"
    options = urlencode({"options": f"-csearch_path={schema}"})
    return f"{database_url}{separator}{options}"


def _create_schema(database_url, schema):
    import psycopg

    with psycopg.connect(database_url, autocommit=True) as connection:
        connection.execute(f'CREATE SCHEMA "{schema}"')


def _drop_schema(database_url, schema):
    import psycopg

    with psycopg.connect(database_url, autocommit=True) as connection:
        connection.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')


def _create_source(source_path):
    with patch.object(database, "DB_NAME", str(source_path)):
        with patch.dict(os.environ, {
            "DATABASE_BACKEND": "sqlite",
            "DATABASE_URL": "",
            "ENV": "test",
        }):
            database.init_db()

    connection = sqlite3.connect(source_path)
    try:
        connection.execute("""
            INSERT INTO companies (id, name, owner_username, created_at)
            VALUES (2, 'Migration Company', 'migration-owner', '2026-09-18')
        """)
        connection.execute("""
            INSERT INTO clients (
                id, name, phone, created_at, company_id
            )
            VALUES (2, 'Migration Client', '+70000000002', '2026-09-18', 2)
        """)
        connection.execute("""
            INSERT INTO tasks (
                id, client_id, client, description, task_date,
                status, price, company_id, created_at
            )
            VALUES (
                2, 2, 'Migration Client', 'Migration task', '2026-09-18',
                'Новая', '1500', 2, '2026-09-18 10:00:00'
            )
        """)
        connection.commit()
    finally:
        connection.close()


def main():
    if os.getenv("DATABASE_BACKEND") != "postgresql":
        raise RuntimeError("DATABASE_BACKEND=postgresql is required")
    database_url = os.getenv("DATABASE_URL", "")
    if not database_url:
        raise RuntimeError("DATABASE_URL is required")
    if os.getenv("POSTGRESQL_EXPERIMENTAL") != "1":
        raise RuntimeError("POSTGRESQL_EXPERIMENTAL=1 is required")

    schema = f"migration_smoke_{uuid4().hex}"
    invalid_schema = f"migration_invalid_{uuid4().hex}"
    unmanaged_schema = f"migration_unmanaged_{uuid4().hex}"
    _create_schema(database_url, schema)
    _create_schema(database_url, invalid_schema)
    _create_schema(database_url, unmanaged_schema)
    target_url = _url_with_schema(database_url, schema)
    invalid_target_url = _url_with_schema(database_url, invalid_schema)
    unmanaged_target_url = _url_with_schema(database_url, unmanaged_schema)

    try:
        with tempfile.TemporaryDirectory(
            prefix="field-service-migration-smoke-"
        ) as root:
            source_path = Path(root) / "source.db"
            _create_source(source_path)

            dry_run = migrate_sqlite_to_postgresql(
                source_path,
                target_url,
            )
            assert dry_run["executed"] is False
            assert dry_run["target_state"] == "empty"
            assert dry_run["can_execute"] is True
            assert dry_run["company_isolation"]["ok"] is True
            assert dry_run["table_count"] >= 50
            assert dry_run["total_rows"] > 0

            migrated = migrate_sqlite_to_postgresql(
                source_path,
                target_url,
                execute=True,
            )
            assert migrated["executed"] is True
            assert migrated["already_migrated"] is False
            assert migrated["target_state"] == "managed_complete"
            assert migrated["verification"]["ok"] is True
            assert migrated["verification"]["company_isolation"]["ok"]

            repeated = migrate_sqlite_to_postgresql(
                source_path,
                target_url,
                execute=True,
            )
            assert repeated["executed"] is False
            assert repeated["already_migrated"] is True
            assert repeated["verification"]["ok"] is True

            verified_dry_run = migrate_sqlite_to_postgresql(
                source_path,
                target_url,
            )
            assert verified_dry_run["already_migrated"] is True
            assert verified_dry_run["verification"]["ok"] is True

            import psycopg

            with psycopg.connect(target_url) as target_connection:
                target_connection.execute("DELETE FROM tasks")
                target_connection.execute("""
                    UPDATE postgresql_migration_runs
                    SET status='running', completed_at=NULL
                """)
            resumed = migrate_sqlite_to_postgresql(
                source_path,
                target_url,
                execute=True,
            )
            assert resumed["executed"] is True
            assert resumed["verification"]["ok"] is True

            with psycopg.connect(unmanaged_target_url) as target_connection:
                target_connection.execute(
                    "CREATE TABLE existing_data (id BIGINT PRIMARY KEY)"
                )
                target_connection.execute(
                    "INSERT INTO existing_data (id) VALUES (1)"
                )
            try:
                migrate_sqlite_to_postgresql(
                    source_path,
                    unmanaged_target_url,
                    execute=True,
                )
            except PostgreSQLDataMigrationError as exc:
                assert str(exc) == (
                    "postgresql_target_not_safe:nonempty_unmanaged"
                )
            else:
                raise AssertionError("Unmanaged target was not rejected")

            lock_connection = psycopg.connect(target_url)
            try:
                lock_connection.execute(
                    "SELECT pg_advisory_lock(%s)",
                    (MIGRATION_LOCK_KEY,),
                )
                lock_connection.commit()
                try:
                    migrate_sqlite_to_postgresql(
                        source_path,
                        invalid_target_url,
                        execute=True,
                    )
                except PostgreSQLDataMigrationError as exc:
                    assert str(exc) == (
                        "postgresql_migration_lock_unavailable"
                    )
                else:
                    raise AssertionError("Concurrent migration was not rejected")
            finally:
                lock_connection.execute(
                    "SELECT pg_advisory_unlock(%s)",
                    (MIGRATION_LOCK_KEY,),
                )
                lock_connection.commit()
                lock_connection.close()

            connection = sqlite3.connect(source_path)
            try:
                connection.execute("""
                    INSERT INTO clients (name, company_id, created_at)
                    VALUES ('Changed source', 1, '2026-09-18')
                """)
                connection.commit()
            finally:
                connection.close()

            try:
                migrate_sqlite_to_postgresql(
                    source_path,
                    target_url,
                    execute=True,
                )
            except PostgreSQLDataMigrationError as exc:
                assert str(exc) == (
                    "postgresql_target_not_safe:fingerprint_mismatch"
                )
            else:
                raise AssertionError("Changed source was not rejected")

            connection = sqlite3.connect(source_path)
            try:
                connection.execute("""
                    INSERT INTO tasks (
                        client_id, client, description, task_date, status,
                        price, company_id, created_at
                    )
                    VALUES (
                        2, 'Invalid tenant', 'Invalid tenant task',
                        '2026-09-18', 'Новая', '0', 1,
                        '2026-09-18 11:00:00'
                    )
                """)
                connection.commit()
            finally:
                connection.close()

            try:
                migrate_sqlite_to_postgresql(
                    source_path,
                    invalid_target_url,
                    execute=True,
                )
            except PostgreSQLDataMigrationError as exc:
                assert str(exc) == "sqlite_company_isolation_failed:tasks"
            else:
                raise AssertionError("Invalid tenant data was not rejected")

            print(
                "PostgreSQL data migration smoke passed: "
                f"{migrated['table_count']} tables, "
                f"{migrated['total_rows']} rows."
            )
    finally:
        _drop_schema(database_url, schema)
        _drop_schema(database_url, invalid_schema)
        _drop_schema(database_url, unmanaged_schema)


if __name__ == "__main__":
    main()
