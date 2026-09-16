import os
import sys
import asyncio
import json
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app import database  # noqa: E402


REQUIRED_TABLES = {
    "users",
    "companies",
    "tasks",
    "system_events",
    "a3_followup_quality_alerts",
}

REQUIRED_QUALITY_SLA_COLUMNS = {
    "response_due_at",
    "resolution_due_at",
    "escalated_at",
    "last_escalated_at",
    "escalation_count",
}


def main():
    if os.getenv("DATABASE_BACKEND") != "postgresql":
        raise RuntimeError("DATABASE_BACKEND=postgresql is required")
    if not os.getenv("DATABASE_URL"):
        raise RuntimeError("DATABASE_URL is required")
    if os.getenv("POSTGRESQL_EXPERIMENTAL") != "1":
        raise RuntimeError("POSTGRESQL_EXPERIMENTAL=1 is required")

    runtime = database.get_database_runtime_config()
    assert runtime["configuration_valid"] is True
    assert runtime["active_backend"] == "postgresql"

    database.init_db()
    database.init_db()

    connection = database.connect()
    company_id = None
    try:
        table_rows = connection.execute("""
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema=CURRENT_SCHEMA()
            ORDER BY table_name
        """).fetchall()
        table_names = {row["table_name"] for row in table_rows}
        assert REQUIRED_TABLES <= table_names, REQUIRED_TABLES - table_names

        column_rows = connection.execute("""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema=CURRENT_SCHEMA()
              AND table_name='a3_followup_quality_alerts'
        """).fetchall()
        column_names = {row["column_name"] for row in column_rows}
        assert REQUIRED_QUALITY_SLA_COLUMNS <= column_names, (
            REQUIRED_QUALITY_SLA_COLUMNS - column_names
        )

        seeded_users = connection.execute("""
            SELECT username, COUNT(*) AS duplicate_count
            FROM users
            WHERE username IN ('boss', 'manager', 'worker')
            GROUP BY username
            ORDER BY username
        """).fetchall()
        assert len(seeded_users) == 3
        assert all(row["duplicate_count"] == 1 for row in seeded_users)

        marker = f"PostgreSQL smoke {uuid4().hex}"
        cursor = connection.cursor()
        cursor.execute(
            """
            INSERT INTO companies (name, owner_username, created_at)
            VALUES (?, ?, ?)
            """,
            (marker, "owner", "2026-09-16T00:00:00"),
        )
        company_id = cursor.lastrowid
        connection.commit()

        company = connection.execute(
            "SELECT id, name FROM companies WHERE id=?",
            (company_id,),
        ).fetchone()
        assert company[0] == company["id"] == company_id
        assert company["name"] == marker

        from app import main as crm

        health = crm.get_public_health_status()
        assert health["ok"] is True
        assert health["database"]["backend"] == "postgresql"
        assert health["database"]["error"] == ""

        readiness = crm.get_public_readiness_status()
        readiness_checks = {
            item["key"]: item for item in readiness["checks"]
        }
        assert readiness["ok"] is False
        assert readiness_checks["database"]["ok"] is True
        assert readiness_checks["postgresql_connection_check"]["ok"] is True
        assert readiness_checks["required_tables"]["ok"] is True
        assert readiness_checks["database_release_support"]["ok"] is False
        response = asyncio.run(crm.public_ready())
        assert response.status_code == 503
        payload = json.loads(response.body)
        serialized = json.dumps(payload)
        assert payload["checks"] == readiness["checks"]
        assert os.environ["DATABASE_URL"] not in serialized

        import psycopg

        with patch.object(
            crm,
            "connect",
            side_effect=psycopg.OperationalError("private connection detail"),
        ):
            unavailable = crm.get_public_health_status()
        assert unavailable["ok"] is False
        assert unavailable["database"]["error"] == "OperationalError"
        assert "private connection detail" not in json.dumps(unavailable)

        print(
            "PostgreSQL schema smoke passed: "
            f"{len(table_names)} tables, generated id {company_id}."
        )
    finally:
        if company_id is not None:
            connection.execute(
                "DELETE FROM companies WHERE id=?",
                (company_id,),
            )
            connection.commit()
        connection.close()


if __name__ == "__main__":
    main()
