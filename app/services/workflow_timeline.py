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
        "sessions": build_timeline_sessions(items),
    }


def _session_key(event):
    created_at = event.get("created_at") or ""
    day = created_at[:10] or "unknown"

    return f"{event.get('rule_id')}:{day}"


def build_timeline_sessions(events):
    sessions = []
    session_map = {}

    for event in events:
        key = _session_key(event)

        if key not in session_map:
            session = {
                "id": key,
                "label": f"Сессия {len(sessions) + 1}",
                "started_at": event.get("created_at"),
                "ended_at": event.get("processed_at") or event.get("created_at"),
                "events": [],
                "steps": [],
                "status": "pending",
                "total": 0,
                "failed": 0,
                "skipped": 0,
                "done": 0,
                "pending": 0,
            }
            session_map[key] = session
            sessions.append(session)

        session = session_map[key]
        session["events"].append(event)

        status = event.get("status") or "pending"
        session["total"] += 1

        if status in ("failed", "skipped", "done", "pending"):
            session[status] += 1
        else:
            session["pending"] += 1

        if event.get("processed_at"):
            session["ended_at"] = event.get("processed_at")

    for session in sessions:
        session["steps"] = build_timeline_steps(session["events"])

        if session["failed"]:
            session["status"] = "failed"
        elif session["skipped"]:
            session["status"] = "skipped"
        elif session["pending"]:
            session["status"] = "pending"
        else:
            session["status"] = "done"

    return sessions


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
