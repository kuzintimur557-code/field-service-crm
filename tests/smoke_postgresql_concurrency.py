import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from threading import Event
from time import monotonic
from urllib.parse import urlencode
from uuid import uuid4


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app import database  # noqa: E402


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


def _expect_unique_violation(connection, query, parameters):
    import psycopg

    connection.execute("SAVEPOINT expected_unique_violation")
    try:
        connection.execute(query, parameters)
    except psycopg.errors.UniqueViolation:
        connection.execute("ROLLBACK TO SAVEPOINT expected_unique_violation")
    else:
        raise AssertionError("Expected PostgreSQL unique violation")
    finally:
        connection.execute("RELEASE SAVEPOINT expected_unique_violation")


def _verify_lock_serialization():
    first = database.connect()
    first_cursor = first.cursor()
    database.begin_locked_transaction(
        first_cursor,
        "concurrency_smoke",
        1,
    )

    second_started = Event()

    def acquire_same_lock():
        connection = database.connect()
        try:
            second_started.set()
            started_at = monotonic()
            database.begin_locked_transaction(
                connection.cursor(),
                "concurrency_smoke",
                1,
            )
            waited = monotonic() - started_at
            connection.rollback()
            return waited
        finally:
            connection.close()

    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(acquire_same_lock)
        assert second_started.wait(timeout=2)

        different = database.connect()
        try:
            started_at = monotonic()
            database.begin_locked_transaction(
                different.cursor(),
                "concurrency_smoke",
                2,
            )
            different_wait = monotonic() - started_at
            different.rollback()
        finally:
            different.close()
        assert different_wait < 1
        assert future.done() is False

        release_at = monotonic()
        first.commit()
        same_wait = future.result(timeout=5)
        assert monotonic() - release_at < 5
        assert same_wait > 0

    first.close()


def _verify_partial_indexes_and_incident_sync():
    from app.services.a3_platform_incidents import sync_a3_platform_incidents

    connection = database.connect()
    try:
        index_rows = connection.execute("""
            SELECT indexname, indexdef
            FROM pg_indexes
            WHERE schemaname=CURRENT_SCHEMA()
              AND indexname IN (
                  'idx_automation_action_runs_source',
                  'idx_a3_platform_incident_active',
                  'idx_a3_followup_quality_alerts_open_key',
                  'idx_calendar_day_ack_automation_unique',
                  'idx_background_jobs_active_dedupe'
              )
        """).fetchall()
        definitions = {
            row["indexname"]: row["indexdef"].lower()
            for row in index_rows
        }
        assert len(definitions) == 5
        assert "unique index" in definitions[
            "idx_automation_action_runs_source"
        ]
        for index_name in (
            "idx_a3_platform_incident_active",
            "idx_a3_followup_quality_alerts_open_key",
            "idx_calendar_day_ack_automation_unique",
            "idx_background_jobs_active_dedupe",
        ):
            assert "unique index" in definitions[index_name]
            assert " where " in definitions[index_name]

        connection.execute("""
            INSERT INTO users (
                username, password, role, company_id, is_active
            ) VALUES ('concurrency-admin', '', 'superadmin', 1, 1)
        """)
        connection.commit()
    finally:
        connection.close()

    report = {
        "items": [{
            "company_id": 1,
            "company_name": "Concurrency Company",
            "status": "critical",
            "message": "Concurrent PostgreSQL incident",
        }],
    }
    now = datetime(2026, 9, 18, 12, 0, 0)

    def sync_incident():
        return sync_a3_platform_incidents(
            report,
            now=now,
            telegram_sender=lambda *_args: False,
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _item: sync_incident(), range(2)))
    assert sum(item["opened"] for item in results) == 1
    assert sum(item["repeated"] for item in results) == 1

    connection = database.connect()
    try:
        incident = connection.execute("""
            SELECT id, occurrence_count
            FROM a3_platform_incidents
            WHERE company_id=1
              AND incident_key='a3_scheduler_health'
              AND status='open'
        """).fetchall()
        assert len(incident) == 1
        assert incident[0]["occurrence_count"] == 2

        now_text = "2026-09-18 12:00:00"
        connection.execute("""
            INSERT INTO a3_platform_incidents (
                company_id, incident_key, severity, status, title,
                first_detected_at, last_detected_at, created_at, updated_at
            ) VALUES (
                1, 'a3_scheduler_health', 'critical', 'resolved',
                'Resolved duplicate', ?, ?, ?, ?
            )
        """, (now_text, now_text, now_text, now_text))
        _expect_unique_violation(connection, """
            INSERT INTO a3_platform_incidents (
                company_id, incident_key, severity, status, title,
                first_detected_at, last_detected_at, created_at, updated_at
            ) VALUES (
                1, 'a3_scheduler_health', 'critical', 'open',
                'Open duplicate', ?, ?, ?, ?
            )
        """, (now_text, now_text, now_text, now_text))

        quality_parameters = (
            "concurrency-quality",
            "repeat_return",
            "Concurrency quality",
            now_text,
            now_text,
            now_text,
            now_text,
        )
        for status in ("resolved", "resolved", "active"):
            connection.execute("""
                INSERT INTO a3_followup_quality_alerts (
                    alert_key, alert_type, company_id, title, status,
                    first_detected_at, last_detected_at, created_at, updated_at
                ) VALUES (?, ?, 1, ?, ?, ?, ?, ?, ?)
            """, (
                quality_parameters[0],
                quality_parameters[1],
                quality_parameters[2],
                status,
                *quality_parameters[3:],
            ))
        _expect_unique_violation(connection, """
            INSERT INTO a3_followup_quality_alerts (
                alert_key, alert_type, company_id, title, status,
                first_detected_at, last_detected_at, created_at, updated_at
            ) VALUES (?, ?, 1, ?, 'acknowledged', ?, ?, ?, ?)
        """, quality_parameters)

        reminder_parameters = (
            1,
            "2026-09-19",
            1,
            "worker",
            "boss",
            now_text,
        )
        for source in ("manual", "manual", "scheduler"):
            connection.execute("""
                INSERT INTO calendar_day_ack_reminders (
                    company_id, plan_date, revision, username,
                    reminded_by, reminded_at, source
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (*reminder_parameters, source))
        _expect_unique_violation(connection, """
            INSERT INTO calendar_day_ack_reminders (
                company_id, plan_date, revision, username,
                reminded_by, reminded_at, source
            ) VALUES (?, ?, ?, ?, ?, ?, 'manual_run')
        """, reminder_parameters)
        connection.commit()
    finally:
        connection.close()


def _verify_concurrent_automation_idempotency():
    from app.main import run_automation_event

    connection = database.connect()
    try:
        cursor = connection.cursor()
        cursor.execute("""
            INSERT INTO clients (name, company_id, created_at)
            VALUES ('Concurrency Client', 1, '2026-09-18')
        """)
        client_id = cursor.lastrowid
        cursor.execute("""
            INSERT INTO automation_rules (
                company_id, name, trigger_key, conditions_json,
                active, created_by, created_at, updated_at
            ) VALUES (
                1, 'Concurrency rule', 'concurrency_trigger', '{}',
                1, 'boss', '2026-09-18', '2026-09-18'
            )
        """)
        rule_id = cursor.lastrowid
        cursor.execute("""
            INSERT INTO automation_actions (
                company_id, rule_id, action_key, payload_json,
                sort_order, active, created_at
            ) VALUES (1, ?, 'create_task', ?, 1, 1, '2026-09-18')
        """, (rule_id, json.dumps({"message": "Concurrent task"})))
        connection.commit()
    finally:
        connection.close()

    def run_event():
        return run_automation_event(
            1,
            "concurrency_trigger",
            "client",
            client_id,
            "Concurrent event",
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _item: run_event(), range(2)))
    assert results == [1, 1]

    connection = database.connect()
    try:
        task_count = connection.execute("""
            SELECT COUNT(*) AS value
            FROM tasks
            WHERE company_id=1 AND description='Concurrent task'
        """).fetchone()["value"]
        run_count = connection.execute("""
            SELECT COUNT(*) AS value
            FROM automation_action_runs AS runs
            JOIN automation_actions AS actions ON actions.id=runs.action_id
            WHERE runs.company_id=1 AND actions.rule_id=?
        """, (rule_id,)).fetchone()["value"]
        assert task_count == 1
        assert run_count == 1
    finally:
        connection.close()


def _verify_background_job_concurrency():
    from app.services.background_jobs import (
        enqueue_background_job,
        process_background_jobs,
    )

    def enqueue_duplicate(_item):
        return enqueue_background_job(
            "test.concurrent",
            payload={},
            dedupe_key="postgresql-concurrent-dedupe",
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        dedupe_results = list(executor.map(enqueue_duplicate, range(2)))
    assert sum(1 for item in dedupe_results if item["created"]) == 1

    connection = database.connect()
    connection.execute("DELETE FROM background_jobs")
    connection.commit()
    connection.close()

    for item_id in (1, 2):
        enqueue_background_job(
            "test.concurrent",
            payload={"item_id": item_id},
            dedupe_key=f"postgresql-job-{item_id}",
        )

    processed_ids = []

    def handle_job(payload, _job):
        processed_ids.append(payload["item_id"])
        return {"item_id": payload["item_id"]}

    def run_worker(worker_number):
        return process_background_jobs(
            {"test.concurrent": handle_job},
            worker_id=f"postgresql-worker-{worker_number}",
            limit=1,
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        worker_results = list(executor.map(run_worker, range(2)))
    assert sum(item["succeeded"] for item in worker_results) == 2
    assert sorted(processed_ids) == [1, 2]

    connection = database.connect()
    try:
        statuses = connection.execute("""
            SELECT status, COUNT(*) AS value
            FROM background_jobs
            GROUP BY status
        """).fetchall()
        assert {row["status"]: row["value"] for row in statuses} == {
            "succeeded": 2,
        }
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

    schema = f"concurrency_smoke_{uuid4().hex}"
    _create_schema(database_url, schema)
    target_url = _url_with_schema(database_url, schema)
    previous_url = os.environ["DATABASE_URL"]
    os.environ["DATABASE_URL"] = target_url
    try:
        database.init_db()
        assert database.transaction_lock_key("scope", 1) == (
            database.transaction_lock_key("scope", 1)
        )
        assert database.transaction_lock_key("scope", 1) != (
            database.transaction_lock_key("scope", 2)
        )
        _verify_lock_serialization()
        _verify_partial_indexes_and_incident_sync()
        _verify_concurrent_automation_idempotency()
        _verify_background_job_concurrency()
        print(
            "PostgreSQL concurrency smoke passed: advisory locks, "
            "partial indexes, durable jobs and automation idempotency."
        )
    finally:
        os.environ["DATABASE_URL"] = previous_url
        _drop_schema(database_url, schema)


if __name__ == "__main__":
    main()
