"""PostgreSQL backup creation, archive validation, and restore drills."""

import json
import os
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4


BACKUP_FORMAT = "field-service-postgresql-backup-v1"
DEFAULT_TIMEOUT_SECONDS = 300
POSTGRES_ENV_KEYS = {
    "dbname": "PGDATABASE",
    "host": "PGHOST",
    "port": "PGPORT",
    "user": "PGUSER",
    "password": "PGPASSWORD",
    "passfile": "PGPASSFILE",
    "service": "PGSERVICE",
    "servicefile": "PGSERVICEFILE",
    "sslmode": "PGSSLMODE",
    "sslcert": "PGSSLCERT",
    "sslkey": "PGSSLKEY",
    "sslrootcert": "PGSSLROOTCERT",
    "sslcrl": "PGSSLCRL",
    "sslcrldir": "PGSSLCRLDIR",
    "target_session_attrs": "PGTARGETSESSIONATTRS",
    "connect_timeout": "PGCONNECT_TIMEOUT",
    "channel_binding": "PGCHANNELBINDING",
    "gssencmode": "PGGSSENCMODE",
    "options": "PGOPTIONS",
    "application_name": "PGAPPNAME",
}


def _timeout_seconds():
    try:
        return max(10, int(os.getenv("POSTGRES_BACKUP_TIMEOUT_SECONDS", "300")))
    except ValueError:
        return DEFAULT_TIMEOUT_SECONDS


def _binary(env_name, default):
    configured = str(os.getenv(env_name) or "").strip()
    if configured:
        path = Path(configured).expanduser()
        return str(path) if path.is_file() else ""
    return shutil.which(default) or ""


def _connection_parameters(database_url):
    from psycopg.conninfo import conninfo_to_dict

    return conninfo_to_dict(database_url)


def _command_environment(database_url, database_name=None):
    parameters = _connection_parameters(database_url)
    environment = os.environ.copy()
    environment.pop("DATABASE_URL", None)
    for env_name in POSTGRES_ENV_KEYS.values():
        environment.pop(env_name, None)
    for key, env_name in POSTGRES_ENV_KEYS.items():
        value = parameters.get(key)
        if value not in (None, ""):
            environment[env_name] = str(value)
    if database_name:
        environment["PGDATABASE"] = database_name
    return environment


def _manifest_path(archive_path):
    return Path(f"{archive_path}.json")


def _read_manifest(archive_path):
    manifest_path = _manifest_path(archive_path)
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if manifest.get("format") != BACKUP_FORMAT:
        return None
    schema = manifest.get("schema")
    tables = manifest.get("tables")
    if not isinstance(schema, str) or not schema:
        return None
    if not isinstance(tables, dict):
        return None
    if not all(
        isinstance(name, str)
        and isinstance(count, int)
        and count >= 0
        for name, count in tables.items()
    ):
        return None
    return manifest


def _table_counts(connection, schema):
    from psycopg import sql

    rows = connection.execute(
        """
        SELECT table_name
        FROM information_schema.tables
        WHERE table_schema=%s
          AND table_type='BASE TABLE'
        ORDER BY table_name
        """,
        (schema,),
    ).fetchall()
    counts = {}
    for row in rows:
        table = row[0]
        query = sql.SQL("SELECT COUNT(*) FROM {}.{}").format(
            sql.Identifier(schema),
            sql.Identifier(table),
        )
        counts[table] = connection.execute(query).fetchone()[0]
    return counts


def inspect_postgresql_database(database_url):
    """Return safe connection and database-size metadata."""
    try:
        import psycopg

        with psycopg.connect(database_url) as connection:
            size = connection.execute(
                "SELECT pg_database_size(current_database())"
            ).fetchone()[0]
        return {"ok": True, "size": int(size), "error": ""}
    except Exception as error:
        return {
            "ok": False,
            "size": 0,
            "error": error.__class__.__name__,
        }


def create_postgresql_backup(database_url, backup_path, required_tables):
    """Create a consistent custom-format dump plus a row-count manifest."""
    pg_dump = _binary("PG_DUMP_BIN", "pg_dump")
    if not pg_dump:
        return None, "backup_tool_missing"

    import psycopg

    backup_path = Path(backup_path)
    backup_path.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    destination = backup_path / f"crm_backup_{timestamp}.dump"
    manifest_path = _manifest_path(destination)

    try:
        with psycopg.connect(database_url) as connection:
            connection.execute(
                "BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY"
            )
            schema = connection.execute("SELECT current_schema()").fetchone()[0]
            snapshot = connection.execute("SELECT pg_export_snapshot()").fetchone()[0]
            tables = _table_counts(connection, schema)
            missing = sorted(set(required_tables) - set(tables))
            if missing:
                connection.rollback()
                return None, "backup_schema_incomplete"
            command = [
                pg_dump,
                "--format=custom",
                f"--file={destination}",
                "--no-owner",
                "--no-privileges",
                f"--schema={schema}",
                f"--snapshot={snapshot}",
            ]
            completed = subprocess.run(
                command,
                env=_command_environment(database_url),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=_timeout_seconds(),
                check=False,
            )
            connection.rollback()
        if completed.returncode != 0 or not destination.is_file():
            raise RuntimeError("pg_dump_failed")
        manifest = {
            "format": BACKUP_FORMAT,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "schema": schema,
            "tables": tables,
        }
        manifest_path.write_text(
            json.dumps(manifest, ensure_ascii=False, sort_keys=True),
            encoding="utf-8",
        )
        return destination.name, ""
    except subprocess.TimeoutExpired:
        error_code = "backup_timeout"
    except Exception:
        error_code = "backup_failed"

    for path in (destination, manifest_path):
        try:
            path.unlink()
        except OSError:
            pass
    return None, error_code


def verify_postgresql_backup(archive_path, required_tables):
    """Validate the archive catalog and its sidecar manifest."""
    archive_path = Path(archive_path)
    result = {
        "status": "critical",
        "status_label": "Проблема",
        "message": "Копия не проверена.",
        "quick_check": "",
        "missing_tables": list(required_tables),
    }
    manifest = _read_manifest(archive_path)
    if manifest is None:
        result.update({
            "status_label": "Нет манифеста",
            "message": "Манифест PostgreSQL-копии отсутствует или повреждён.",
        })
        return result
    pg_restore = _binary("PG_RESTORE_BIN", "pg_restore")
    if not pg_restore:
        result.update({
            "status_label": "Нет pg_restore",
            "message": "Утилита pg_restore недоступна.",
        })
        return result
    try:
        completed = subprocess.run(
            [pg_restore, "--list", str(archive_path)],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=_timeout_seconds(),
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        completed = None
    tables = set(manifest["tables"])
    missing = sorted(set(required_tables) - tables)
    catalog = completed.stdout if completed and completed.returncode == 0 else ""
    catalog_missing = [
        table
        for table in required_tables
        if f" TABLE {manifest['schema']} {table} " not in catalog
    ]
    missing = sorted(set(missing) | set(catalog_missing))
    if not completed or completed.returncode != 0:
        result.update({
            "status_label": "Не читается",
            "message": "Архив не читается утилитой pg_restore.",
        })
    elif missing:
        result.update({
            "status": "warning",
            "status_label": "Неполная копия",
            "message": "В PostgreSQL-копии нет части ключевых таблиц.",
            "quick_check": "pg_restore --list",
            "missing_tables": missing,
        })
    else:
        result.update({
            "status": "ok",
            "status_label": "Проверена",
            "message": "Архив PostgreSQL читается, ключевые таблицы на месте.",
            "quick_check": "pg_restore --list",
            "missing_tables": [],
        })
    return result


def run_postgresql_restore_drill(database_url, archive_path, required_tables):
    """Restore a dump into a disposable database and compare every table."""
    archive_path = Path(archive_path)
    verification = verify_postgresql_backup(archive_path, required_tables)
    if verification["status"] != "ok":
        return {
            "status": "critical",
            "status_label": "Проверка провалена",
            "message": verification["message"],
            "file": archive_path.name,
            "verification": verification,
            "error": "restore_check_failed",
        }
    pg_restore = _binary("PG_RESTORE_BIN", "pg_restore")
    manifest = _read_manifest(archive_path)
    temp_database = f"field_service_restore_drill_{uuid4().hex[:12]}"
    maintenance = None
    restored = None
    try:
        import psycopg
        from psycopg import sql
        from psycopg.conninfo import conninfo_to_dict, make_conninfo

        parameters = conninfo_to_dict(database_url)
        parameters.pop("options", None)
        parameters["dbname"] = "postgres"
        maintenance = psycopg.connect(make_conninfo(**parameters), autocommit=True)
        maintenance.execute(
            sql.SQL("CREATE DATABASE {}").format(sql.Identifier(temp_database))
        )
        command_env = _command_environment(database_url, temp_database)
        command_env.pop("PGOPTIONS", None)
        completed = subprocess.run(
            [
                pg_restore,
                "--exit-on-error",
                "--clean",
                "--if-exists",
                "--no-owner",
                "--no-privileges",
                f"--dbname={temp_database}",
                str(archive_path),
            ],
            env=command_env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=_timeout_seconds(),
            check=False,
        )
        if completed.returncode != 0:
            raise RuntimeError("pg_restore_failed")
        parameters["dbname"] = temp_database
        restored = psycopg.connect(make_conninfo(**parameters))
        restored_counts = _table_counts(restored, manifest["schema"])
        if restored_counts != manifest["tables"]:
            raise RuntimeError("restored_data_mismatch")
        missing = sorted(set(required_tables) - set(restored_counts))
        if missing:
            raise RuntimeError("restored_schema_incomplete")
        return {
            "status": "ok",
            "status_label": "Восстановление проверено",
            "message": (
                "PostgreSQL-копия восстановлена во временную базу; "
                "структура и количество строк совпадают."
            ),
            "file": archive_path.name,
            "verification": verification,
            "error": "",
        }
    except subprocess.TimeoutExpired:
        message = "Проверка восстановления PostgreSQL превысила лимит времени."
    except Exception:
        message = "Не удалось восстановить или проверить PostgreSQL-копию."
    finally:
        if restored is not None:
            restored.close()
        if maintenance is not None:
            try:
                from psycopg import sql

                maintenance.execute(
                    sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(
                        sql.Identifier(temp_database)
                    )
                )
            except Exception:
                pass
            maintenance.close()

    return {
        "status": "critical",
        "status_label": "Проверка провалена",
        "message": message,
        "file": archive_path.name,
        "verification": verification,
        "error": "restore_check_failed",
    }
