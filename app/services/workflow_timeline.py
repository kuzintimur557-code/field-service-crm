from datetime import datetime

from app.database import connect


def require_company_id(company_id):
    if not company_id:
        raise ValueError("company_id is required")


def get_workflow_timeline(company_id, rule_id, limit=20):
    require_company_id(company_id)

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

    total_events_row = c.execute("""
        SELECT COUNT(*) AS total
        FROM automation_events
        WHERE company_id=?
          AND rule_id=?
    """, (
        company_id,
        rule_id,
    )).fetchone()
    total_events = total_events_row["total"] if total_events_row else 0

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
        "events_total": total_events,
        "limit": limit,
        "has_more": total_events > len(items),
        "summary": build_timeline_summary(items),
        "steps": build_timeline_steps(items),
        "sessions": build_timeline_sessions(items),
    }


def _session_key(event):
    created_at = event.get("created_at") or ""
    day = created_at[:10] or "unknown"

    return f"{event.get('rule_id')}:{day}"


def _session_date_label(event):
    created_at = event.get("created_at") or ""

    return created_at[:10] or "дата неизвестна"


def _parse_datetime(value):
    if not value:
        return None

    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            pass

    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _format_duration(seconds):
    if seconds is None:
        return "-"

    if seconds < 60:
        return f"{seconds} сек"

    minutes = seconds // 60

    if minutes < 60:
        return f"{minutes} мин"

    hours = minutes // 60
    remaining_minutes = minutes % 60

    if remaining_minutes:
        return f"{hours} ч {remaining_minutes} мин"

    return f"{hours} ч"


def _update_session_time(session, event):
    created_at = event.get("created_at")
    processed_at = event.get("processed_at") or created_at
    created_dt = _parse_datetime(created_at)
    processed_dt = _parse_datetime(processed_at)
    started_dt = _parse_datetime(session.get("started_at"))
    ended_dt = _parse_datetime(session.get("ended_at"))

    if created_dt and (not started_dt or created_dt < started_dt):
        session["started_at"] = created_at

    if processed_dt and (not ended_dt or processed_dt > ended_dt):
        session["ended_at"] = processed_at


def _session_duration(session):
    started_dt = _parse_datetime(session.get("started_at"))
    ended_dt = _parse_datetime(session.get("ended_at"))

    if not started_dt or not ended_dt:
        return None

    seconds = int((ended_dt - started_dt).total_seconds())

    if seconds < 0:
        return None

    return seconds


def _session_execution_state(session):
    if session["pending"]:
        return "active"

    if session["failed"]:
        return "problem"

    if session["skipped"]:
        return "warning"

    return "finished"


def build_timeline_summary(events):
    summary = {
        "total": len(events),
        "done": 0,
        "skipped": 0,
        "failed": 0,
        "pending": 0,
    }

    for event in events:
        status = event.get("status") or "pending"

        if status in ("done", "skipped", "failed", "pending"):
            summary[status] += 1
        else:
            summary["pending"] += 1

    return summary


def _event_status_label(status):
    labels = {
        "done": "Выполнено",
        "skipped": "Пропущено",
        "failed": "Ошибка",
        "pending": "Ожидает",
    }

    return labels.get(status or "pending", "Ожидает")


def _execution_state_label(state):
    labels = {
        "active": "В работе",
        "finished": "Завершено",
        "warning": "Нужно внимание",
        "problem": "Проблема",
    }

    return labels.get(state or "active", "В работе")


def build_timeline_sessions(events):
    sessions = []
    session_map = {}

    for event in events:
        key = _session_key(event)

        if key not in session_map:
            date_label = _session_date_label(event)
            session = {
                "id": key,
                "label": f"Сессия {len(sessions) + 1} · {date_label}",
                "date_label": date_label,
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
        _update_session_time(session, event)

        status = event.get("status") or "pending"
        session["total"] += 1

        if status in ("failed", "skipped", "done", "pending"):
            session[status] += 1
        else:
            session["pending"] += 1
    for session in sessions:
        session["steps"] = build_timeline_steps(session["events"])
        duration_seconds = _session_duration(session)
        session["duration_seconds"] = duration_seconds
        session["duration_label"] = _format_duration(duration_seconds)
        session["execution_state"] = _session_execution_state(session)
        session["execution_state_label"] = _execution_state_label(session["execution_state"])

        if session["failed"]:
            session["status"] = "failed"
        elif session["skipped"]:
            session["status"] = "skipped"
        elif session["pending"]:
            session["status"] = "pending"
        else:
            session["status"] = "done"

        session["status_label"] = _event_status_label(session["status"])

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
            "status_label": _event_status_label(status),
            "message": event.get("message") or "",
            "created_at": event.get("created_at"),
            "processed_at": event.get("processed_at"),
        })

    return steps
