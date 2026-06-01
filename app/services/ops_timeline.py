from datetime import datetime

from app.database import connect


def create_ops_timeline_event(
    company_id,
    event_type,
    severity,
    title,
    message,
    source="a3",
    target_type=None,
    target_id=None,
    cooldown_minutes=10,
):
    conn = connect()
    c = conn.cursor()

    try:
        c.execute("""
            ALTER TABLE ops_timeline_events
            ADD COLUMN source TEXT
        """)
    except Exception:
        pass

    try:
        c.execute("""
            ALTER TABLE ops_timeline_events
            ADD COLUMN target_type TEXT
        """)
    except Exception:
        pass

    try:
        c.execute("""
            ALTER TABLE ops_timeline_events
            ADD COLUMN target_id INTEGER
        """)
    except Exception:
        pass

    existing = c.execute("""
        SELECT id
        FROM ops_timeline_events
        WHERE company_id=?
          AND event_type=?
          AND title=?
          AND message=?
          AND COALESCE(target_type, '') =
              COALESCE(?, '')
          AND COALESCE(target_id, 0) =
              COALESCE(?, 0)
          AND created_at >= datetime(
                'now',
                '-' || ? || ' minutes'
          )
        ORDER BY id DESC
        LIMIT 1
    """, (
        company_id,
        event_type,
        title,
        message,
        target_type,
        target_id,
        cooldown_minutes,
    )).fetchone()

    if existing:
        event_id = existing["id"]
        conn.close()

        return event_id

    c.execute("""
        INSERT INTO ops_timeline_events (
            company_id,
            event_type,
            severity,
            title,
            message,
            source,
            target_type,
            target_id,
            created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        company_id,
        event_type,
        severity,
        title,
        message,
        source,
        target_type,
        target_id,
        datetime.now().isoformat(timespec="seconds"),
    ))

    conn.commit()
    event_id = c.lastrowid
    conn.close()

    return event_id


def get_ops_timeline(company_id, limit=100):
    conn = connect()
    c = conn.cursor()

    rows = c.execute("""
        SELECT *
        FROM ops_timeline_events
        WHERE company_id=?
        ORDER BY id DESC
        LIMIT ?
    """, (
        company_id,
        limit,
    )).fetchall()

    conn.close()

    return [dict(row) for row in rows]
