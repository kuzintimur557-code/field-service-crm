from datetime import datetime

from app.database import connect
from app.services.governance import get_governance_settings


def enqueue_autonomous_action(
    company_id,
    action_type,
    target_type,
    target_id=None,
    payload_json=None,
):
    conn = connect()
    c = conn.cursor()

    existing = c.execute("""
        SELECT id
        FROM autonomous_action_queue
        WHERE company_id=?
          AND action_type=?
          AND target_type=?
          AND COALESCE(target_id, 0)=COALESCE(?, 0)
          AND status IN ('pending', 'awaiting_approval')
        ORDER BY id DESC
        LIMIT 1
    """, (
        company_id,
        action_type,
        target_type,
        target_id,
    )).fetchone()

    if existing:
        conn.close()

        return {
            "queued": False,
            "reason": "duplicate_pending_action",
        }

    cooldown_count = c.execute("""
        SELECT COUNT(*) AS total
        FROM autonomous_action_queue
        WHERE company_id=?
          AND action_type=?
          AND target_type=?
          AND COALESCE(target_id, 0)=COALESCE(?, 0)
          AND created_at >= datetime('now', '-10 minutes')
    """, (
        company_id,
        action_type,
        target_type,
        target_id,
    )).fetchone()["total"]

    if cooldown_count >= 3:
        conn.close()

        return {
            "queued": False,
            "reason": "cooldown_active",
        }

    c.execute("""
        INSERT INTO autonomous_action_queue (
            company_id,
            action_type,
            target_type,
            target_id,
            payload_json,
            created_at
        ) VALUES (?, ?, ?, ?, ?, ?)
    """, (
        company_id,
        action_type,
        target_type,
        target_id,
        payload_json,
        datetime.now().isoformat(timespec="seconds"),
    ))

    conn.commit()
    conn.close()

    return {
        "queued": True,
    }


def get_autonomous_actions(company_id):
    conn = connect()
    c = conn.cursor()

    rows = c.execute("""
        SELECT *
        FROM autonomous_action_queue
        WHERE company_id=?
        ORDER BY id DESC
        LIMIT 100
    """, (company_id,)).fetchall()

    conn.close()

    return [dict(row) for row in rows]


def process_autonomous_actions(company_id=1):
    governance = get_governance_settings(company_id)

    if not governance.get("autonomous_enabled", 1):
        return {
            "processed": 0,
            "blocked": True,
            "reason": "autonomous_disabled",
        }

    conn = connect()
    c = conn.cursor()

    rows = c.execute("""
        SELECT *
        FROM autonomous_action_queue
        WHERE company_id=?
          AND status='pending'
        ORDER BY id ASC
        LIMIT ?
    """, (
        company_id,
        governance.get("max_actions_per_cycle", 20),
    )).fetchall()

    processed = 0

    for row in rows:
        action_type = row["action_type"]

        if (
            governance.get("require_critical_approval", 1)
            and action_type == "disable_rule"
        ):
            c.execute("""
                UPDATE autonomous_action_queue
                SET status='awaiting_approval'
                WHERE id=?
            """, (row["id"],))

            continue

        c.execute("""
            UPDATE autonomous_action_queue
            SET status='completed',
                processed_at=?
            WHERE id=?
        """, (
            datetime.now().isoformat(timespec="seconds"),
            row["id"],
        ))

        processed += 1

    conn.commit()
    conn.close()

    return {
        "processed": processed,
    }
