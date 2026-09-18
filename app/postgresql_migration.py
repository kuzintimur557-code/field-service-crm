import base64
import hashlib
import json
import math
import os
import sqlite3
import tempfile
from contextlib import contextmanager
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path

from app import database
from app.postgres_adapter import connect_postgres, validate_identifier


MIGRATION_TABLE = "postgresql_migration_runs"
MIGRATION_LOCK_KEY = 734_202_609
COPY_BATCH_SIZE = 500
REQUIRED_SOURCE_TABLES = {"companies", "users"}
TENANT_RELATIONSHIPS = (
    ("tasks", "client_id", "clients", "id"),
    ("task_items", "task_id", "tasks", "id"),
    ("task_items", "catalog_item_id", "catalog_items", "id"),
    ("task_expenses", "task_id", "tasks", "id"),
    ("finance_summary", "task_id", "tasks", "id"),
    ("client_notes", "client_id", "clients", "id"),
    ("client_files", "client_id", "clients", "id"),
    ("call_records", "client_id", "clients", "id"),
    ("recurring_jobs", "client_id", "clients", "id"),
    ("custom_field_values", "field_id", "custom_fields", "id"),
    ("team_activity", "user_id", "users", "id"),
    ("payroll_payouts", "worker_id", "users", "id"),
    ("worker_unavailability", "worker_id", "users", "id"),
    ("automation_actions", "rule_id", "automation_rules", "id"),
    ("automation_events", "rule_id", "automation_rules", "id"),
    ("automation_action_runs", "action_id", "automation_actions", "id"),
    (
        "autonomous_action_approvals",
        "action_queue_id",
        "autonomous_action_queue",
        "id",
    ),
    (
        "a3_platform_incident_events",
        "incident_id",
        "a3_platform_incidents",
        "id",
    ),
    (
        "a3_incident_followups",
        "incident_id",
        "a3_platform_incidents",
        "id",
    ),
    (
        "a3_followup_quality_alerts",
        "incident_id",
        "a3_platform_incidents",
        "id",
    ),
)


class PostgreSQLDataMigrationError(RuntimeError):
    """Safe, stable migration error that never contains connection details."""


def _quoted(identifier):
    return f'"{validate_identifier(identifier)}"'


def _utc_now():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


@contextmanager
def _temporary_environment(values):
    previous = {key: os.environ.get(key) for key in values}
    try:
        for key, value in values.items():
            os.environ[key] = value
        yield
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def _validate_inputs(sqlite_path, database_url):
    source_path = Path(sqlite_path).expanduser().resolve()
    if not source_path.is_file():
        raise PostgreSQLDataMigrationError("sqlite_source_not_found")
    if database._database_url_backend(database_url) != "postgresql":
        raise PostgreSQLDataMigrationError("postgresql_database_url_required")
    return source_path


@contextmanager
def _sqlite_snapshot(source_path):
    with tempfile.TemporaryDirectory(prefix="field-service-sqlite-snapshot-") as root:
        snapshot_path = Path(root) / "snapshot.db"
        source = sqlite3.connect(f"{source_path.as_uri()}?mode=ro", uri=True)
        target = sqlite3.connect(snapshot_path)
        try:
            source.backup(target)
        except sqlite3.Error as exc:
            raise PostgreSQLDataMigrationError(
                "sqlite_snapshot_failed"
            ) from exc
        finally:
            target.close()
            source.close()

        snapshot = sqlite3.connect(snapshot_path)
        snapshot.row_factory = sqlite3.Row
        try:
            integrity = snapshot.execute("PRAGMA integrity_check").fetchone()
            if not integrity or integrity[0] != "ok":
                raise PostgreSQLDataMigrationError(
                    "sqlite_integrity_check_failed"
                )
            yield snapshot
        finally:
            snapshot.close()


def _sqlite_tables(connection):
    rows = connection.execute("""
        SELECT name
        FROM sqlite_master
        WHERE type='table'
          AND name NOT LIKE 'sqlite_%'
        ORDER BY name
    """).fetchall()
    tables = [validate_identifier(row["name"]) for row in rows]
    missing = sorted(REQUIRED_SOURCE_TABLES - set(tables))
    if missing:
        raise PostgreSQLDataMigrationError(
            "sqlite_required_tables_missing:" + ",".join(missing)
        )
    return tables


def _sqlite_columns(connection, table):
    rows = connection.execute(
        f"PRAGMA table_info({_quoted(table)})"
    ).fetchall()
    columns = [validate_identifier(row["name"]) for row in rows]
    primary_key = [
        column
        for _, column in sorted(
            (row["pk"], validate_identifier(row["name"]))
            for row in rows
            if row["pk"]
        )
    ]
    if not columns:
        raise PostgreSQLDataMigrationError(
            f"sqlite_table_has_no_columns:{table}"
        )
    return columns, primary_key


def _canonical_number(value):
    if isinstance(value, float) and not math.isfinite(value):
        return repr(value)
    try:
        number = Decimal(str(value))
    except InvalidOperation:
        return repr(value)
    if number == 0:
        return "0"
    return format(number.normalize(), "f")


def _canonical_value(value):
    if value is None:
        return ["null", None]
    if isinstance(value, (bool, int, float, Decimal)):
        return ["number", _canonical_number(value)]
    if isinstance(value, bytes):
        return ["bytes", base64.b64encode(value).decode("ascii")]
    return ["text", str(value)]


def _table_checksum(connection, table, columns):
    selected = ", ".join(_quoted(column) for column in columns)
    row_hashes = []
    for row in connection.execute(
        f"SELECT {selected} FROM {_quoted(table)}"
    ):
        payload = [_canonical_value(row[column]) for column in columns]
        encoded = json.dumps(
            payload,
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
        row_hashes.append(hashlib.sha256(encoded).hexdigest())
    checksum = hashlib.sha256()
    for row_hash in sorted(row_hashes):
        checksum.update(row_hash.encode("ascii"))
        checksum.update(b"\n")
    return checksum.hexdigest(), len(row_hashes)


def _key_bounds(connection, table, columns):
    if "id" not in columns:
        return None
    row = connection.execute(
        f"SELECT MIN(id) AS minimum, MAX(id) AS maximum "
        f"FROM {_quoted(table)}"
    ).fetchone()
    return [row["minimum"], row["maximum"]]


def _build_manifest(connection, tables, column_reader):
    table_manifest = {}
    total_rows = 0
    logical_hash = hashlib.sha256()
    for table in sorted(tables):
        columns, primary_key = column_reader(connection, table)
        checksum, row_count = _table_checksum(connection, table, columns)
        key_bounds = _key_bounds(connection, table, columns)
        item = {
            "columns": columns,
            "primary_key": primary_key,
            "row_count": row_count,
            "checksum": checksum,
            "id_bounds": key_bounds,
        }
        table_manifest[table] = item
        total_rows += row_count
        logical_hash.update(table.encode("utf-8"))
        logical_hash.update(b"\0")
        logical_hash.update(",".join(columns).encode("utf-8"))
        logical_hash.update(b"\0")
        logical_hash.update(str(row_count).encode("ascii"))
        logical_hash.update(b"\0")
        logical_hash.update(checksum.encode("ascii"))
        logical_hash.update(b"\n")
    return {
        "version": 1,
        "source_fingerprint": logical_hash.hexdigest(),
        "table_count": len(table_manifest),
        "total_rows": total_rows,
        "tables": table_manifest,
    }


def _postgresql_tables(connection):
    rows = connection.execute("""
        SELECT table_name
        FROM information_schema.tables
        WHERE table_schema=CURRENT_SCHEMA()
          AND table_type='BASE TABLE'
        ORDER BY table_name
    """).fetchall()
    return [validate_identifier(row["table_name"]) for row in rows]


def _postgresql_columns(connection, table):
    rows = connection.execute("""
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema=CURRENT_SCHEMA()
          AND table_name=?
        ORDER BY ordinal_position
    """, (table,)).fetchall()
    columns = [validate_identifier(row["column_name"]) for row in rows]
    primary_rows = connection.execute("""
        SELECT attribute.attname AS column_name
        FROM pg_index AS index_definition
        JOIN pg_class AS table_definition
          ON table_definition.oid=index_definition.indrelid
        JOIN pg_namespace AS namespace_definition
          ON namespace_definition.oid=table_definition.relnamespace
        JOIN unnest(index_definition.indkey) WITH ORDINALITY
          AS indexed_column(attribute_number, position) ON TRUE
        JOIN pg_attribute AS attribute
          ON attribute.attrelid=table_definition.oid
         AND attribute.attnum=indexed_column.attribute_number
        WHERE namespace_definition.nspname=CURRENT_SCHEMA()
          AND table_definition.relname=?
          AND index_definition.indisprimary
        ORDER BY indexed_column.position
    """, (table,)).fetchall()
    primary_key = [
        validate_identifier(row["column_name"]) for row in primary_rows
    ]
    return columns, primary_key


def _company_isolation_report(connection, manifest):
    company_tables = []
    issues = []
    for table, item in sorted(manifest["tables"].items()):
        if "company_id" not in item["columns"]:
            continue
        company_tables.append(table)
        missing_filter = "company_id IS NULL"
        if table == "users" and "role" in item["columns"]:
            missing_filter += " AND COALESCE(role, '')!='superadmin'"
        missing = connection.execute(
            f"SELECT COUNT(*) AS value FROM {_quoted(table)} "
            f"WHERE {missing_filter}"
        ).fetchone()["value"]
        orphaned = connection.execute(
            f"SELECT COUNT(*) AS value FROM {_quoted(table)} AS tenant_row "
            "LEFT JOIN companies "
            "ON companies.id=tenant_row.company_id "
            "WHERE tenant_row.company_id IS NOT NULL "
            "AND companies.id IS NULL"
        ).fetchone()["value"]
        if missing or orphaned:
            issues.append({
                "table": table,
                "missing_company_id": int(missing),
                "orphaned_company_id": int(orphaned),
            })
    relationship_issues = []
    checked_relationships = 0
    for child, foreign_key, parent, parent_key in TENANT_RELATIONSHIPS:
        child_item = manifest["tables"].get(child)
        parent_item = manifest["tables"].get(parent)
        if not child_item or not parent_item:
            continue
        if not {foreign_key, "company_id"} <= set(child_item["columns"]):
            continue
        if not {parent_key, "company_id"} <= set(parent_item["columns"]):
            continue
        checked_relationships += 1
        row = connection.execute(
            f"SELECT "
            f"SUM(CASE WHEN parent.{_quoted(parent_key)} IS NULL "
            "THEN 1 ELSE 0 END) AS missing_parent, "
            "SUM(CASE WHEN "
            f"parent.{_quoted(parent_key)} IS NOT NULL "
            "AND child.company_id!=parent.company_id "
            "THEN 1 ELSE 0 END) AS cross_company "
            f"FROM {_quoted(child)} AS child "
            f"LEFT JOIN {_quoted(parent)} AS parent "
            f"ON parent.{_quoted(parent_key)}=child.{_quoted(foreign_key)} "
            f"WHERE child.{_quoted(foreign_key)} IS NOT NULL"
        ).fetchone()
        missing_parent = int(row["missing_parent"] or 0)
        cross_company = int(row["cross_company"] or 0)
        if missing_parent or cross_company:
            relationship_issues.append({
                "table": child,
                "column": foreign_key,
                "parent_table": parent,
                "missing_parent": missing_parent,
                "cross_company": cross_company,
            })
    return {
        "ok": not issues and not relationship_issues,
        "checked_tables": len(company_tables),
        "checked_relationships": checked_relationships,
        "issues": issues,
        "relationship_issues": relationship_issues,
    }


def _assert_company_isolation(connection, manifest, prefix):
    report = _company_isolation_report(connection, manifest)
    if not report["ok"]:
        tables = sorted({
            item["table"]
            for item in report["issues"] + report["relationship_issues"]
        })
        raise PostgreSQLDataMigrationError(
            f"{prefix}_company_isolation_failed:" + ",".join(tables)
        )
    return report


def _target_state(connection, fingerprint):
    tables = _postgresql_tables(connection)
    if not tables:
        return {
            "name": "empty",
            "tables": tables,
            "run": None,
        }
    if MIGRATION_TABLE not in tables:
        return {
            "name": "nonempty_unmanaged",
            "tables": tables,
            "run": None,
        }
    runs = connection.execute(f"""
        SELECT source_fingerprint, status, manifest_json
        FROM {_quoted(MIGRATION_TABLE)}
        ORDER BY id
    """).fetchall()
    if len(runs) != 1 or runs[0]["source_fingerprint"] != fingerprint:
        return {
            "name": "fingerprint_mismatch",
            "tables": tables,
            "run": None,
        }
    return {
        "name": f"managed_{runs[0]['status']}",
        "tables": tables,
        "run": runs[0],
    }


def _initialize_target(database_url, source_name, fingerprint):
    with _temporary_environment({
        "DATABASE_BACKEND": "postgresql",
        "DATABASE_URL": database_url,
        "POSTGRESQL_EXPERIMENTAL": "1",
        "ENV": "production",
    }):
        database.init_db()
    connection = connect_postgres(database_url)
    try:
        connection.execute(f"""
            CREATE TABLE IF NOT EXISTS {_quoted(MIGRATION_TABLE)} (
                id BIGSERIAL PRIMARY KEY,
                source_fingerprint TEXT UNIQUE NOT NULL,
                source_name TEXT NOT NULL,
                status TEXT NOT NULL,
                manifest_json TEXT NOT NULL DEFAULT '{{}}',
                started_at TEXT NOT NULL,
                completed_at TEXT
            )
        """)
        connection.execute(f"""
            INSERT INTO {_quoted(MIGRATION_TABLE)} (
                source_fingerprint,
                source_name,
                status,
                manifest_json,
                started_at
            )
            VALUES (?, ?, 'running', '{{}}', ?)
        """, (fingerprint, source_name, _utc_now()))
        connection.commit()
    finally:
        connection.close()


def _validate_target_schema(connection, manifest):
    target_tables = set(_postgresql_tables(connection))
    missing_tables = sorted(set(manifest["tables"]) - target_tables)
    if missing_tables:
        raise PostgreSQLDataMigrationError(
            "postgresql_tables_missing:" + ",".join(missing_tables)
        )
    for table, item in manifest["tables"].items():
        target_columns, _ = _postgresql_columns(connection, table)
        missing_columns = sorted(set(item["columns"]) - set(target_columns))
        if missing_columns:
            raise PostgreSQLDataMigrationError(
                f"postgresql_columns_missing:{table}:" +
                ",".join(missing_columns)
            )


def _truncate_application_tables(connection):
    tables = [
        table for table in _postgresql_tables(connection)
        if table != MIGRATION_TABLE
    ]
    if not tables:
        raise PostgreSQLDataMigrationError("postgresql_schema_is_empty")
    table_list = ", ".join(_quoted(table) for table in tables)
    connection.execute(f"TRUNCATE TABLE {table_list} RESTART IDENTITY")


def _copy_source(connection, source, manifest):
    for table, item in manifest["tables"].items():
        columns = item["columns"]
        selected = ", ".join(_quoted(column) for column in columns)
        placeholders = ", ".join("?" for _ in columns)
        insert_sql = (
            f"INSERT INTO {_quoted(table)} ({selected}) "
            f"VALUES ({placeholders})"
        )
        source_cursor = source.execute(
            f"SELECT {selected} FROM {_quoted(table)}"
        )
        while True:
            rows = source_cursor.fetchmany(COPY_BATCH_SIZE)
            if not rows:
                break
            connection.executemany(
                insert_sql,
                [tuple(row[column] for column in columns) for row in rows],
            )


def _verify_target(connection, source_manifest):
    target_manifest = _build_manifest(
        connection,
        list(source_manifest["tables"]),
        lambda _connection, table: (
            source_manifest["tables"][table]["columns"],
            source_manifest["tables"][table]["primary_key"],
        ),
    )
    differences = []
    for table, source_item in source_manifest["tables"].items():
        target_item = target_manifest["tables"][table]
        for field in ("row_count", "checksum", "id_bounds"):
            if source_item[field] != target_item[field]:
                differences.append(f"{table}.{field}")
    if differences:
        raise PostgreSQLDataMigrationError(
            "postgresql_verification_failed:" + ",".join(differences)
        )
    isolation = _assert_company_isolation(
        connection,
        source_manifest,
        "postgresql",
    )
    return {
        "ok": True,
        "table_count": source_manifest["table_count"],
        "total_rows": source_manifest["total_rows"],
        "company_isolation": isolation,
    }


def _mark_complete(connection, fingerprint, manifest):
    cursor = connection.execute(f"""
        UPDATE {_quoted(MIGRATION_TABLE)}
        SET status='complete',
            manifest_json=?,
            completed_at=?
        WHERE source_fingerprint=?
          AND status='running'
    """, (
        json.dumps(manifest, ensure_ascii=False, separators=(",", ":")),
        _utc_now(),
        fingerprint,
    ))
    if cursor.rowcount != 1:
        raise PostgreSQLDataMigrationError(
            "postgresql_migration_state_update_failed"
        )


def migrate_sqlite_to_postgresql(sqlite_path, database_url, execute=False):
    """Copy a consistent SQLite snapshot into a guarded PostgreSQL target."""
    source_path = _validate_inputs(sqlite_path, database_url)
    with _sqlite_snapshot(source_path) as source:
        tables = _sqlite_tables(source)
        source_manifest = _build_manifest(source, tables, _sqlite_columns)
        source_isolation = _assert_company_isolation(
            source,
            source_manifest,
            "sqlite",
        )
        fingerprint = source_manifest["source_fingerprint"]

        target = connect_postgres(database_url)
        lock_held = False
        try:
            if execute:
                lock_row = target.execute(
                    "SELECT pg_try_advisory_lock(?) AS locked",
                    (MIGRATION_LOCK_KEY,),
                ).fetchone()
                target.commit()
                if not lock_row or not lock_row["locked"]:
                    raise PostgreSQLDataMigrationError(
                        "postgresql_migration_lock_unavailable"
                    )
                lock_held = True

            state = _target_state(target, fingerprint)
            target.commit()
            can_execute = state["name"] in {
                "empty",
                "managed_running",
                "managed_complete",
            }
            summary = {
                "ok": True,
                "executed": False,
                "already_migrated": state["name"] == "managed_complete",
                "source_name": source_path.name,
                "source_fingerprint": fingerprint,
                "table_count": source_manifest["table_count"],
                "total_rows": source_manifest["total_rows"],
                "target_state": state["name"],
                "can_execute": can_execute,
                "company_isolation": source_isolation,
            }
            if not execute:
                if state["name"] == "managed_complete":
                    _validate_target_schema(target, source_manifest)
                    summary["verification"] = _verify_target(
                        target,
                        source_manifest,
                    )
                    target.commit()
                return summary
            if not can_execute:
                raise PostgreSQLDataMigrationError(
                    "postgresql_target_not_safe:" + state["name"]
                )

            if state["name"] == "empty":
                _initialize_target(
                    database_url,
                    source_path.name,
                    fingerprint,
                )
                state = _target_state(target, fingerprint)
                if state["name"] != "managed_running":
                    raise PostgreSQLDataMigrationError(
                        "postgresql_target_initialization_failed"
                    )

            _validate_target_schema(target, source_manifest)
            if state["name"] == "managed_complete":
                verification = _verify_target(target, source_manifest)
                target.commit()
                summary.update({
                    "already_migrated": True,
                    "target_state": "managed_complete",
                    "verification": verification,
                })
                return summary

            try:
                _truncate_application_tables(target)
                _copy_source(target, source, source_manifest)
                database.sync_postgres_sequences(target.cursor())
                verification = _verify_target(target, source_manifest)
                _mark_complete(target, fingerprint, source_manifest)
                target.commit()
            except Exception:
                target.rollback()
                raise
            summary.update({
                "executed": True,
                "already_migrated": False,
                "target_state": "managed_complete",
                "verification": verification,
            })
            return summary
        finally:
            if target is not None:
                if lock_held:
                    try:
                        target.rollback()
                        target.execute(
                            "SELECT pg_advisory_unlock(?)",
                            (MIGRATION_LOCK_KEY,),
                        )
                        target.commit()
                    except Exception:
                        target.rollback()
                target.close()
