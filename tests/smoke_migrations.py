import os
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]


def run_alembic(temp_dir, *args):
    env = dict(os.environ)
    env["DATA_DIR"] = temp_dir
    env["DATABASE_BACKEND"] = "sqlite"
    env["DATABASE_URL"] = ""

    return subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )


def main():
    with tempfile.TemporaryDirectory() as temp_dir, patch.dict(
        os.environ,
        {"DATABASE_BACKEND": "sqlite", "DATABASE_URL": ""},
        clear=False,
    ):
        # fresh database: bootstrap schema, then stamp baseline
        sys.path.insert(0, str(ROOT))
        from app import database

        database.DATA_DIR = Path(temp_dir)
        database.DB_NAME = str(Path(temp_dir) / "crm.db")
        database.init_db()

        result = run_alembic(temp_dir, "stamp", "0001")
        assert result.returncode == 0, result.stderr

        db_path = Path(temp_dir) / "crm.db"
        conn = sqlite3.connect(str(db_path))
        version = conn.execute(
            "SELECT version_num FROM alembic_version"
        ).fetchone()
        conn.close()
        assert version and version[0] == "0001"

        # upgrade head is idempotent and records the baseline
        result = run_alembic(temp_dir, "upgrade", "head")
        assert result.returncode == 0, result.stderr

        result = run_alembic(temp_dir, "upgrade", "head")
        assert result.returncode == 0, result.stderr

        conn = sqlite3.connect(str(db_path))
        version = conn.execute(
            "SELECT version_num FROM alembic_version"
        ).fetchone()
        conn.close()
        assert version and version[0] == "0001"

        # current revision resolves
        result = run_alembic(temp_dir, "current")
        assert result.returncode == 0, result.stderr
        assert "0001" in result.stdout

    print("Migrations smoke passed.")


if __name__ == "__main__":
    main()
