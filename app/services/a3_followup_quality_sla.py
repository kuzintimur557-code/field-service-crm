import os
from datetime import datetime, timedelta

from app.database import begin_locked_transaction, connect


A3_QUALITY_ALERT_RESPONSE_HOURS = 4
A3_QUALITY_ALERT_RESOLUTION_HOURS = 24
A3_QUALITY_ALERT_ESCALATION_COOLDOWN_HOURS = 12


def _environment_hours(name, default, minimum=1, maximum=720):
    try:
        value = int(str(os.getenv(name, default)).strip())
    except (TypeError, ValueError):
        value = default
    return max(minimum, min(value, maximum))


def get_a3_followup_quality_sla_policy():
    response_hours = _environment_hours(
        "A3_QUALITY_ALERT_RESPONSE_HOURS",
        A3_QUALITY_ALERT_RESPONSE_HOURS,
    )
    resolution_hours = max(
        response_hours,
        _environment_hours(
            "A3_QUALITY_ALERT_RESOLUTION_HOURS",
            A3_QUALITY_ALERT_RESOLUTION_HOURS,
        ),
    )
    cooldown_hours = _environment_hours(
        "A3_QUALITY_ALERT_ESCALATION_COOLDOWN_HOURS",
        A3_QUALITY_ALERT_ESCALATION_COOLDOWN_HOURS,
    )
    return {
        "response_hours": response_hours,
        "resolution_hours": resolution_hours,
        "cooldown_hours": cooldown_hours,
        "response_label": f"{response_hours} ч.",
        "resolution_label": f"{resolution_hours} ч.",
        "cooldown_label": f"{cooldown_hours} ч.",
    }


def _parse_datetime(value):
    try:
        return datetime.fromisoformat(str(value or "").replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None


def _align_datetime(moment, reference):
    if not moment or not reference:
        return moment
    if moment.tzinfo and not reference.tzinfo:
        return moment.replace(tzinfo=None)
    if reference.tzinfo and not moment.tzinfo:
        return moment.replace(tzinfo=reference.tzinfo)
    return moment


def _timestamp(value):
    return value.isoformat(sep=" ", timespec="seconds") if value else None


def _time_label(value):
    moment = value if isinstance(value, datetime) else _parse_datetime(value)
    return moment.strftime("%d.%m.%Y %H:%M") if moment else "Не указано"


def _duration_label(seconds):
    minutes = max(0, int(abs(seconds) // 60))
    hours, remainder = divmod(minutes, 60)
    if hours and remainder:
        return f"{hours} ч. {remainder} мин."
    if hours:
        return f"{hours} ч."
    return f"{remainder} мин."


def _deadline_progress(deadline, now_value):
    if not deadline:
        return "Срок не рассчитан"
    clock = _align_datetime(now_value, deadline)
    seconds = (deadline - clock).total_seconds()
    if seconds <= 0:
        return f"Просрочено на {_duration_label(seconds)}"
    return f"Осталось {_duration_label(seconds)}"


def _alert_deadlines(item, policy):
    first_detected = _parse_datetime(item.get("first_detected_at"))
    response_due = _parse_datetime(item.get("response_due_at")) or (
        first_detected + timedelta(hours=policy["response_hours"])
        if first_detected else None
    )
    resolution_due = _parse_datetime(item.get("resolution_due_at")) or (
        first_detected + timedelta(hours=policy["resolution_hours"])
        if first_detected else None
    )
    return response_due, resolution_due


def persist_a3_followup_quality_alert_deadlines(cursor, items, policy=None):
    """Freeze deadlines once; existing episodes keep their original SLA."""
    selected_policy = policy or get_a3_followup_quality_sla_policy()
    for item in items:
        response_due, resolution_due = _alert_deadlines(item, selected_policy)
        deadlines = (_timestamp(response_due), _timestamp(resolution_due))
        if deadlines == (item.get("response_due_at"), item.get("resolution_due_at")):
            continue
        cursor.execute("""
            UPDATE a3_followup_quality_alerts
            SET response_due_at=?, resolution_due_at=? WHERE id=?
        """, (*deadlines, item["id"]))
        item["response_due_at"], item["resolution_due_at"] = deadlines


def _can_escalate(item, now_value, cooldown_hours):
    if not item.get("sla_stage"):
        return False
    last_escalated = _parse_datetime(item.get("last_escalated_at"))
    if not last_escalated:
        return True
    clock = _align_datetime(now_value, last_escalated)
    return clock - last_escalated >= timedelta(hours=cooldown_hours)


def enrich_a3_followup_quality_alert_sla(items, now=None, policy=None):
    now_value = now or datetime.now()
    selected_policy = policy or get_a3_followup_quality_sla_policy()
    for item in items:
        response_due, resolution_due = _alert_deadlines(item, selected_policy)
        status = str(item.get("status") or "")
        is_open = status in {"active", "acknowledged"}
        response_at = _parse_datetime(
            item.get("acknowledged_at") or item.get("resolved_at")
        )
        resolved_at = _parse_datetime(item.get("resolved_at"))
        comparable_now = _align_datetime(now_value, response_due)
        response_breached = bool(
            response_due
            and (
                (response_at and _align_datetime(response_at, response_due) > response_due)
                or (status == "active" and comparable_now >= response_due)
            )
        )
        comparable_resolution_now = _align_datetime(now_value, resolution_due)
        resolution_breached = bool(
            resolution_due
            and (
                (resolved_at and _align_datetime(resolved_at, resolution_due) > resolution_due)
                or (is_open and comparable_resolution_now >= resolution_due)
            )
        )
        response_overdue = bool(status == "active" and response_breached)
        resolution_overdue = bool(is_open and resolution_breached)
        stage = (
            "resolution_overdue" if resolution_overdue
            else "response_overdue" if response_overdue else ""
        )
        if response_at:
            response_status_label = (
                "Реакция с опозданием" if response_breached else "Реакция в срок"
            )
        elif status == "resolved":
            response_status_label = "Закрыт без отдельного принятия"
        else:
            response_status_label = _deadline_progress(response_due, now_value)
        if resolved_at:
            resolution_status_label = (
                "Закрыт с опозданием"
                if resolution_breached else "Устранён в срок"
            )
        else:
            resolution_status_label = _deadline_progress(
                resolution_due, now_value,
            )
        item.update({
            "response_due_at_calculated": _timestamp(response_due),
            "response_due_label": _time_label(response_due),
            "resolution_due_at_calculated": _timestamp(resolution_due),
            "resolution_due_label": _time_label(resolution_due),
            "response_status_label": response_status_label,
            "resolution_status_label": resolution_status_label,
            "is_response_overdue": response_overdue,
            "is_resolution_overdue": resolution_overdue,
            "response_sla_breached": response_breached,
            "resolution_sla_breached": resolution_breached,
            "sla_stage": stage,
            "sla_stage_label": (
                "Закрыт с нарушением SLA"
                if status == "resolved" and (response_breached or resolution_breached)
                else "SLA завершён" if status == "resolved" else {
                "response_overdue": "Просрочена реакция",
                "resolution_overdue": "Просрочено устранение",
                "": "В срок",
                }[stage]
            ),
            "is_escalated": bool(item.get("escalated_at")),
            "escalated_label": _time_label(item.get("escalated_at")),
            "last_escalated_label": _time_label(item.get("last_escalated_at")),
        })
        item["sla_ready"] = _can_escalate(
            item, now_value, selected_policy["cooldown_hours"],
        )
    return items


def get_a3_followup_quality_sla_overview(now=None):
    now_value = now or datetime.now()
    policy = get_a3_followup_quality_sla_policy()
    conn = connect()
    try:
        items = [dict(row) for row in conn.execute("""
            SELECT * FROM a3_followup_quality_alerts
            WHERE status IN ('active', 'acknowledged')
            ORDER BY first_detected_at, id
        """).fetchall()]
    finally:
        conn.close()
    enrich_a3_followup_quality_alert_sla(items, now_value, policy)
    summary = {
        "total": len(items),
        "unacknowledged": sum(item["status"] == "active" for item in items),
        "acknowledged": sum(item["status"] == "acknowledged" for item in items),
        "response_overdue": sum(item["is_response_overdue"] for item in items),
        "resolution_overdue": sum(
            item["is_resolution_overdue"] for item in items
        ),
        "escalated": sum(item["is_escalated"] for item in items),
        "escalation_count": sum(item.get("escalation_count") or 0 for item in items),
        "overdue": sum(bool(item["sla_stage"]) for item in items),
        "ready": sum(item["sla_ready"] for item in items),
    }
    status = (
        "critical" if summary["resolution_overdue"]
        else "warning" if summary["response_overdue"] else "stable"
    )
    return {
        "generated_at": now_value.strftime("%d.%m.%Y %H:%M"),
        "status": status,
        "status_label": {
            "critical": "Просрочено устранение сигналов",
            "warning": "Просрочена реакция на сигналы",
            "stable": "SLA сигналов соблюдается",
        }[status],
        "summary": summary,
        "policy": policy,
        "items": items,
    }


def _load_admins(cursor):
    return [dict(row) for row in cursor.execute("""
        SELECT username, full_name, telegram_chat_id
        FROM users
        WHERE role='superadmin' AND COALESCE(is_active, 1)=1
        ORDER BY id
    """).fetchall()]


def _send_telegram(messages, telegram_sender=None):
    if telegram_sender is None:
        from app.telegram_utils import send_message_to_chat

        telegram_sender = send_message_to_chat
    sent = 0
    for chat_id, message in messages:
        if not str(chat_id or "").strip():
            continue
        try:
            if telegram_sender(chat_id, message):
                sent += 1
        except Exception:
            continue
    return sent


def run_a3_followup_quality_sla_monitor(now=None, telegram_sender=None):
    now_value = now or datetime.now()
    now_text = _timestamp(now_value)
    policy = get_a3_followup_quality_sla_policy()
    result = {
        "checked": 0,
        "response_overdue": 0,
        "resolution_overdue": 0,
        "escalated_alerts": 0,
        "notifications_created": 0,
        "telegram_sent": 0,
        "suppressed": 0,
        "without_recipients": 0,
        "items": [],
        "policy": policy,
    }
    telegram_messages = []
    conn = connect()
    try:
        cursor = conn.cursor()
        begin_locked_transaction(cursor, "a3_platform_operations")
        admins = _load_admins(cursor)
        alerts = [dict(row) for row in cursor.execute("""
            SELECT alerts.*, COALESCE(
                companies.name, 'Компания #' || alerts.company_id
            ) AS company_name
            FROM a3_followup_quality_alerts AS alerts
            LEFT JOIN companies ON companies.id=alerts.company_id
            WHERE alerts.status IN ('active', 'acknowledged')
            ORDER BY alerts.first_detected_at, alerts.id
        """).fetchall()]
        persist_a3_followup_quality_alert_deadlines(cursor, alerts, policy)
        enrich_a3_followup_quality_alert_sla(alerts, now_value, policy)
        for item in alerts:
            result["checked"] += 1
            result["response_overdue"] += int(item["is_response_overdue"])
            result["resolution_overdue"] += int(item["is_resolution_overdue"])
            stage = item["sla_stage"]
            if not stage:
                continue
            if not item["sla_ready"]:
                result["suppressed"] += 1
                continue
            if not admins:
                result["without_recipients"] += 1
                continue
            if stage == "resolution_overdue":
                title = "Просрочено устранение сигнала качества A3"
                message = (
                    f"Сигнал #{item['id']} «{item['title']}» не закрыт в срок. "
                    f"Срок устранения: {item['resolution_due_label']}."
                )
            else:
                title = "Просрочена реакция на сигнал качества A3"
                message = (
                    f"Сигнал #{item['id']} «{item['title']}» не принят в "
                    f"работу. Срок реакции: {item['response_due_label']}."
                )
            link = (
                "/platform/a3-health/incidents/actions/quality-alerts"
                f"?status=all#alert-{item['id']}"
            )
            for recipient in admins:
                cursor.execute("""
                    INSERT INTO notifications (
                        company_id, username, title, message, link,
                        is_read, created_at
                    ) VALUES (?, ?, ?, ?, ?, 0, ?)
                """, (
                    item["company_id"], recipient["username"], title,
                    message[:1000], link, now_text,
                ))
                result["notifications_created"] += 1
                telegram_messages.append((
                    recipient.get("telegram_chat_id"), f"{title}\n{message}",
                ))
            cursor.execute("""
                UPDATE a3_followup_quality_alerts
                SET escalated_at=COALESCE(escalated_at, ?),
                    last_escalated_at=?,
                    escalation_count=COALESCE(escalation_count, 0) + 1,
                    updated_at=?
                WHERE id=?
            """, (now_text, now_text, now_text, item["id"]))
            if item.get("incident_id"):
                cursor.execute("""
                    INSERT INTO a3_platform_incident_events (
                        incident_id, company_id, event_type,
                        actor_username, message, created_at
                    ) VALUES (?, ?, 'followup_quality_escalated',
                              'a3_quality_sla_monitor', ?, ?)
                """, (
                    item["incident_id"], item["company_id"],
                    message[:500], now_text,
                ))
            result["escalated_alerts"] += 1
            result["items"].append({
                "id": item["id"],
                "stage": stage,
                "recipient_count": len(admins),
                "link": link,
            })
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    result["telegram_sent"] = _send_telegram(
        telegram_messages, telegram_sender=telegram_sender,
    )
    return result
