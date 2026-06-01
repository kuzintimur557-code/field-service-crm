import time
from datetime import datetime

from app.database import connect
from app.services.ops_timeline import create_ops_timeline_event


def run_self_healing_cycle(company_id=1):
    started_at = time.time()

    conn = connect()
    c = conn.cursor()

    retried_events = 0
    reenabled_rules = 0

    skipped_events = c.execute("""
        SELECT id
        FROM automation_events
        WHERE company_id=?
          AND status='skipped'
        ORDER BY id DESC
        LIMIT 10
    """, (company_id,)).fetchall()

    for row in skipped_events:
        c.execute("""
            UPDATE automation_events
            SET status='pending'
            WHERE id=?
        """, (row["id"],))
        retried_events += 1

    disabled_rules = c.execute("""
        SELECT id
        FROM automation_rules
        WHERE company_id=?
          AND active=0
        ORDER BY id DESC
        LIMIT 5
    """, (company_id,)).fetchall()

    for row in disabled_rules:
        c.execute("""
            UPDATE automation_rules
            SET active=1
            WHERE id=?
        """, (row["id"],))
        reenabled_rules += 1

    duration_ms = int((time.time() - started_at) * 1000)

    c.execute("""
        INSERT INTO self_healing_runs (
            company_id,
            retried_events,
            reenabled_rules,
            status,
            duration_ms,
            created_at
        ) VALUES (?, ?, ?, ?, ?, ?)
    """, (
        company_id,
        retried_events,
        reenabled_rules,
        "done",
        duration_ms,
        datetime.now().isoformat(timespec="seconds"),
    ))

    conn.commit()
    conn.close()

    create_ops_timeline_event(
        company_id=company_id,
        event_type="self_healing",
        severity="info",
        title="Цикл самовосстановления завершён",
        message=f"Повторно запущено событий: {retried_events}. Повторно включено правил: {reenabled_rules}.",
    )

    return {
        "retried_events": retried_events,
        "reenabled_rules": reenabled_rules,
        "duration_ms": duration_ms,
    }


def get_recovery_history(company_id, limit=20):
    conn = connect()
    c = conn.cursor()

    rows = c.execute("""
        SELECT
            retried_events,
            reenabled_rules,
            status,
            duration_ms,
            created_at
        FROM self_healing_runs
        WHERE company_id=?
        ORDER BY id DESC
        LIMIT ?
    """, (
        company_id,
        limit,
    )).fetchall()

    conn.close()

    return [dict(row) for row in rows]
