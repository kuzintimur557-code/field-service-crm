import json
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app import database  # noqa: E402
from app.postgresql_backup import (  # noqa: E402
    _command_environment,
    create_postgresql_backup,
    inspect_postgresql_database,
    run_postgresql_restore_drill,
    verify_postgresql_backup,
)


REQUIRED_TABLES = ("users", "tasks", "clients")


def main():
    if os.getenv("DATABASE_BACKEND") != "postgresql":
        raise RuntimeError("DATABASE_BACKEND=postgresql is required")
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL is required")

    database.init_db()
    private_url = (
        "postgresql://private_user:private_password@db.internal:5432/crm"
        "?sslmode=require"
    )
    command_environment = _command_environment(private_url)
    assert "DATABASE_URL" not in command_environment
    assert command_environment["PGUSER"] == "private_user"
    assert command_environment["PGPASSWORD"] == "private_password"
    assert command_environment["PGHOST"] == "db.internal"
    state = inspect_postgresql_database(database_url)
    assert state["ok"] is True
    assert state["size"] > 0

    with tempfile.TemporaryDirectory() as temp_dir:
        backup_dir = Path(temp_dir)
        filename, error = create_postgresql_backup(
            database_url,
            backup_dir,
            REQUIRED_TABLES,
        )
        assert error == "", error
        assert filename and filename.endswith(".dump")
        archive = backup_dir / filename
        manifest_path = Path(f"{archive}.json")
        assert archive.is_file() and archive.stat().st_size > 0
        assert manifest_path.is_file()

        manifest_text = manifest_path.read_text(encoding="utf-8")
        manifest = json.loads(manifest_text)
        assert set(REQUIRED_TABLES) <= set(manifest["tables"])
        assert database_url not in manifest_text

        verification = verify_postgresql_backup(archive, REQUIRED_TABLES)
        assert verification["status"] == "ok", verification
        assert verification["missing_tables"] == []

        drill = run_postgresql_restore_drill(
            database_url,
            archive,
            REQUIRED_TABLES,
        )
        assert drill["status"] == "ok", drill
        assert drill["error"] == ""

        broken = backup_dir / "broken.dump"
        broken.write_bytes(b"not-a-postgresql-archive")
        broken_verification = verify_postgresql_backup(
            broken,
            REQUIRED_TABLES,
        )
        assert broken_verification["status"] == "critical"

        with patch.dict(
            os.environ,
            {"PG_DUMP_BIN": str(backup_dir / "missing-pg-dump")},
        ):
            missing_name, missing_error = create_postgresql_backup(
                database_url,
                backup_dir,
                REQUIRED_TABLES,
            )
        assert missing_name is None
        assert missing_error == "backup_tool_missing"

    print("PostgreSQL backup and restore smoke passed.")


if __name__ == "__main__":
    main()
