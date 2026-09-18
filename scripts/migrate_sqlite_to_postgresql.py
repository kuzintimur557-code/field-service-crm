#!/usr/bin/env python3
import argparse
import json
import os
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.postgresql_migration import (  # noqa: E402
    PostgreSQLDataMigrationError,
    migrate_sqlite_to_postgresql,
)


def parse_args():
    parser = argparse.ArgumentParser(
        description="Safely migrate a SQLite snapshot to PostgreSQL.",
    )
    parser.add_argument(
        "--sqlite",
        required=True,
        help="Path to the source SQLite database.",
    )
    parser.add_argument(
        "--database-url",
        default=os.getenv("DATABASE_URL", ""),
        help="Target PostgreSQL URL; defaults to DATABASE_URL.",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Perform the copy. Without this flag the command is read-only.",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    try:
        result = migrate_sqlite_to_postgresql(
            args.sqlite,
            args.database_url,
            execute=args.execute,
        )
    except PostgreSQLDataMigrationError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}))
        return 2
    except Exception as exc:
        print(json.dumps({
            "ok": False,
            "error": "unexpected_migration_error",
            "error_type": type(exc).__name__,
        }))
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
