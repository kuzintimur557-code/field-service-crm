from datetime import datetime

from app.database import connect


TIMELINE_STATUS_FILTERS = {"all", "done", "skipped", "failed", "pending"}
MIN_TIMELINE_LIMIT = 5
MAX_TIMELINE_LIMIT = 100


def require_company_id(company_id):
    if not company_id:
        raise ValueError("company_id is required")


def normalize_timeline_status_filter(status_filter):
    value = (status_filter or "all").strip().lower()

    if value in TIMELINE_STATUS_FILTERS:
        return value

    return "all"


def timeline_status_filter_label(status_filter):
    labels = {
        "all": "Все",
        "done": "Выполненные",
        "skipped": "Пропущенные",
        "failed": "Ошибки",
        "pending": "Ожидающие",
    }

    return labels.get(status_filter or "all", "Все")


def normalize_timeline_limit(limit):
    try:
        value = int(limit)
    except (TypeError, ValueError):
        return 20

    if value < MIN_TIMELINE_LIMIT:
        return MIN_TIMELINE_LIMIT

    if value > MAX_TIMELINE_LIMIT:
        return MAX_TIMELINE_LIMIT

    return value


def timeline_range(items):
    if not items:
        return {
            "range_start": None,
            "range_end": None,
            "range_label": "История: событий нет",
        }

    newest = items[0].get("created_at") or "-"
    oldest = items[-1].get("created_at") or "-"

    return {
        "range_start": oldest,
        "range_end": newest,
        "range_label": f"История: с {oldest} по {newest}",
    }


def get_workflow_timeline(company_id, rule_id, limit=20, status_filter="all"):
    require_company_id(company_id)
    limit = normalize_timeline_limit(limit)
    status_filter = normalize_timeline_status_filter(status_filter)

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

    where_parts = [
        "company_id=?",
        "rule_id=?",
    ]
    params = [
        company_id,
        rule_id,
    ]

    if status_filter != "all":
        where_parts.append("status=?")
        params.append(status_filter)

    where_sql = " AND ".join(where_parts)

    total_events_row = c.execute(f"""
        SELECT COUNT(*) AS total
        FROM automation_events
        WHERE {where_sql}
    """, tuple(params)).fetchone()
    total_events = total_events_row["total"] if total_events_row else 0

    rows = c.execute(f"""
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
        WHERE {where_sql}
        ORDER BY id DESC
        LIMIT ?
    """, tuple(params + [limit])).fetchall()

    conn.close()

    items = [dict(row) for row in rows]
    loaded_count = len(items)
    remaining_count = max(total_events - loaded_count, 0)
    has_more = total_events > loaded_count
    loaded_label = (
        f"Показано: {loaded_count} · Осталось: {remaining_count}"
        if has_more
        else f"Показано: {loaded_count}"
    )
    load_state_label = "Есть ещё события" if has_more else "Загружены все события"
    status_filter_label = timeline_status_filter_label(status_filter)
    status_filter_count_label = f"Фильтр: {status_filter_label} · Найдено событий: {total_events}"
    range_info = timeline_range(items)

    return {
        "rule_id": rule_id,
        "status_filter": status_filter,
        "status_filter_label": status_filter_label,
        "status_filter_count_label": status_filter_count_label,
        "items": items,
        "events_total": total_events,
        "loaded_count": loaded_count,
        "remaining_count": remaining_count,
        "loaded_label": loaded_label,
        "load_state_label": load_state_label,
        "range_start": range_info["range_start"],
        "range_end": range_info["range_end"],
        "range_label": range_info["range_label"],
        "limit": limit,
        "has_more": has_more,
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


def _session_time_range_label(session):
    started_at = session.get("started_at") or "-"
    ended_at = session.get("ended_at") or "-"

    return f"Период: {started_at} → {ended_at}"


def _session_execution_state(session):
    if session["pending"]:
        return "active"

    if session["failed"]:
        return "problem"

    if session["skipped"]:
        return "warning"

    return "finished"


def _session_summary_label(session):
    parts = [
        f"Выполнено: {session['done']}",
        f"Пропущено: {session['skipped']}",
        f"Ошибки: {session['failed']}",
        f"Ожидает: {session['pending']}",
    ]

    return " · ".join(parts)


def _session_problem_label(session):
    problem_count = session["failed"] + session["skipped"]
    return problem_count, f"Проблем: {problem_count}"


def build_timeline_summary(events):
    summary = {
        "total": len(events),
        "done": 0,
        "skipped": 0,
        "failed": 0,
        "pending": 0,
        "state": "empty",
        "state_label": "История пустая",
        "latest_event_at": None,
        "latest_event_label": "Последнее событие: нет",
        "problem_count": 0,
        "problem_label": "Проблемных событий: 0",
    }

    if events:
        summary["latest_event_at"] = events[0].get("created_at")
        summary["latest_event_label"] = (
            f"Последнее событие: {summary['latest_event_at'] or 'дата неизвестна'}"
        )

    for event in events:
        status = event.get("status") or "pending"

        if status in ("done", "skipped", "failed", "pending"):
            summary[status] += 1
        else:
            summary["pending"] += 1

    summary["problem_count"] = summary["failed"] + summary["skipped"]
    summary["problem_label"] = f"Проблемных событий: {summary['problem_count']}"

    if summary["failed"]:
        summary["state"] = "problem"
        summary["state_label"] = "Есть ошибки"
    elif summary["skipped"]:
        summary["state"] = "warning"
        summary["state_label"] = "Есть пропуски"
    elif summary["pending"]:
        summary["state"] = "active"
        summary["state_label"] = "Есть ожидающие"
    elif summary["total"]:
        summary["state"] = "finished"
        summary["state_label"] = "Все события выполнены"

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
        session["time_range_label"] = _session_time_range_label(session)
        session["execution_state"] = _session_execution_state(session)
        session["execution_state_label"] = _execution_state_label(session["execution_state"])
        session["summary_label"] = _session_summary_label(session)
        problem_count, problem_label = _session_problem_label(session)
        session["problem_count"] = problem_count
        session["problem_label"] = problem_label

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
            "event_label": f"Событие #{event.get('id') or '-'} · {_event_status_label(status)}",
            "message": event.get("message") or "",
            "created_at": event.get("created_at"),
            "processed_at": event.get("processed_at"),
        })

    return steps
