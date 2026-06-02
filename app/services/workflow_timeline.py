from app.database import connect


def get_workflow_timeline(company_id, rule_id, limit=20):
    conn = connect()
    c = conn.cursor()

    rule = c.execute("""
        SELECT id
        FROM automation_rules
        WHERE company_id=?
          AND id=?
    """, (
        company_id,
        rule_id,
    )).fetchone()

    if not rule:
        conn.close()
        return None

    rows = c.execute("""
        SELECT
            id,
            rule_id,
            trigger_key,
            entity_type,
            entity_id,
            status,
            message,
            created_at,
            processed_at
        FROM automation_events
        WHERE company_id=?
          AND rule_id=?
        ORDER BY id DESC
        LIMIT ?
    """, (
        company_id,
        rule_id,
        limit,
    )).fetchall()

    conn.close()

    items = [dict(row) for row in rows]

    return {
        "rule_id": rule_id,
        "items": items,
        "steps": build_timeline_steps(items),
    }


def build_timeline_steps(events):
    steps = []

    for event in events:
        status = event.get("status") or "pending"

        label = "Ожидает"
        level = "pending"

        if status == "done":
            label = "Выполнено"
            level = "success"

        elif status == "skipped":
            label = "Пропущено"
            level = "warning"

        elif status == "failed":
            label = "Ошибка"
            level = "critical"

        steps.append({
            "event_id": event.get("id"),
            "label": label,
            "level": level,
            "status": status,
            "message": event.get("message") or "",
            "created_at": event.get("created_at"),
            "processed_at": event.get("processed_at"),
        })

    return steps
