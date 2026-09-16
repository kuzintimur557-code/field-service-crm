import os
from datetime import datetime, timedelta
from urllib.parse import urlencode

from app.database import connect


A3_PLATFORM_INCIDENT_KEY = "a3_scheduler_health"
A3_PLATFORM_INCIDENT_EVENT_LIMIT = 200
A3_PLATFORM_INCIDENT_RESPONSE_MINUTES = 30
A3_PLATFORM_INCIDENT_ESCALATION_MINUTES = 60
A3_PLATFORM_INCIDENT_REVIEW_HOURS = 24

A3_PLATFORM_INCIDENT_STATUS_LABELS = {
    "active": "Активные",
    "unacknowledged": "Не приняты в работу",
    "acknowledged": "Приняты в работу",
    "response_overdue": "Просрочена реакция",
    "escalated": "Эскалированные",
    "resolved": "Закрытые",
    "all": "Все",
}

A3_PLATFORM_INCIDENT_EVENT_LABELS = {
    "opened": "Инцидент открыт",
    "updated": "Проблема повторилась",
    "acknowledged": "Принят в работу",
    "assigned": "Назначен ответственный",
    "escalated": "Инцидент эскалирован",
    "note": "Добавлен комментарий",
    "resolved": "Работа восстановлена",
    "review_updated": "Разбор инцидента обновлён",
    "review_completed": "Разбор инцидента завершён",
    "followup_created": "Контрольная мера создана",
    "followup_updated": "Контрольная мера обновлена",
    "followup_completed": "Контрольная мера выполнена",
    "followup_reminder": "Напоминание о контрольной мере",
    "followup_verification_reminder": "Напоминание о проверке меры",
    "followup_verified": "Результат меры подтверждён",
    "followup_verification_reset": "Результат меры отправлен на повторную проверку",
    "followup_rejected": "Мера возвращена на доработку",
    "followup_quality_alert": "Сигнал качества создан",
    "followup_quality_acknowledged": "Сигнал качества принят в работу",
    "followup_quality_resolved": "Сигнал качества закрыт",
    "followup_quality_reopened": "Сигнал качества открыт повторно",
    "followup_quality_escalated": "Нарушение SLA сигнала качества",
}


def _environment_minutes(name, default, minimum=5, maximum=10080):
    try:
        value = int(str(os.getenv(name, default)).strip())
    except (TypeError, ValueError):
        value = default
    return max(minimum, min(value, maximum))


def get_a3_platform_incident_policy():
    response_minutes = _environment_minutes(
        "A3_INCIDENT_RESPONSE_MINUTES",
        A3_PLATFORM_INCIDENT_RESPONSE_MINUTES,
    )
    escalation_minutes = max(
        response_minutes,
        _environment_minutes(
            "A3_INCIDENT_ESCALATION_MINUTES",
            A3_PLATFORM_INCIDENT_ESCALATION_MINUTES,
        ),
    )
    review_hours = _environment_minutes(
        "A3_INCIDENT_REVIEW_HOURS",
        A3_PLATFORM_INCIDENT_REVIEW_HOURS,
        minimum=1,
        maximum=720,
    )
    return {
        "response_minutes": response_minutes,
        "escalation_minutes": escalation_minutes,
        "response_label": f"{response_minutes} мин.",
        "escalation_label": f"{escalation_minutes} мин.",
        "review_hours": review_hours,
        "review_label": f"{review_hours} ч.",
    }


def _timestamp(value=None):
    return (value or datetime.now()).strftime("%Y-%m-%d %H:%M:%S")


def _parse_datetime(value):
    try:
        return datetime.fromisoformat(str(value or "").replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None


def _time_label(value):
    parsed = _parse_datetime(value)
    return parsed.strftime("%d.%m.%Y %H:%M") if parsed else "Время неизвестно"


def _age_label(value, now_value=None):
    parsed = _parse_datetime(value)
    if not parsed:
        return "Время неизвестно"

    current = now_value or datetime.now()
    if parsed.tzinfo and not current.tzinfo:
        current = current.replace(tzinfo=parsed.tzinfo)
    elif current.tzinfo and not parsed.tzinfo:
        current = current.replace(tzinfo=None)

    minutes = max(0, int((current - parsed).total_seconds() // 60))
    if minutes < 1:
        return "Только что"
    if minutes < 60:
        return f"{minutes} мин. назад"
    if minutes < 1440:
        return f"{minutes // 60} ч. назад"
    return f"{minutes // 1440} дн. назад"


def _incident_deadline(incident, field_name, minutes):
    stored = _parse_datetime(incident.get(field_name))
    if stored:
        return stored
    started = _parse_datetime(incident.get("first_detected_at"))
    return started + timedelta(minutes=minutes) if started else None


def _deadline_label(deadline, now_value):
    if not deadline:
        return "Срок не определён"

    comparable_now = now_value
    if deadline.tzinfo and not comparable_now.tzinfo:
        comparable_now = comparable_now.replace(tzinfo=deadline.tzinfo)
    elif comparable_now.tzinfo and not deadline.tzinfo:
        comparable_now = comparable_now.replace(tzinfo=None)

    minutes = int((deadline - comparable_now).total_seconds() // 60)
    if minutes < 0:
        overdue = abs(minutes)
        if overdue < 60:
            return f"Просрочено на {overdue} мин."
        if overdue < 1440:
            return f"Просрочено на {overdue // 60} ч."
        return f"Просрочено на {overdue // 1440} дн."
    if minutes < 1:
        return "Срок наступает сейчас"
    if minutes < 60:
        return f"Осталось {minutes} мин."
    if minutes < 1440:
        return f"Осталось {minutes // 60} ч."
    return f"Осталось {minutes // 1440} дн."


def _deadline_is_overdue(deadline, moment):
    if not deadline or not moment:
        return False
    comparable_moment = moment
    if deadline.tzinfo and not comparable_moment.tzinfo:
        comparable_moment = comparable_moment.replace(tzinfo=deadline.tzinfo)
    elif comparable_moment.tzinfo and not deadline.tzinfo:
        comparable_moment = comparable_moment.replace(tzinfo=None)
    return comparable_moment > deadline


def _deadline_has_arrived(deadline, moment):
    if not deadline or not moment:
        return False
    comparable_moment = moment
    if deadline.tzinfo and not comparable_moment.tzinfo:
        comparable_moment = comparable_moment.replace(tzinfo=deadline.tzinfo)
    elif comparable_moment.tzinfo and not deadline.tzinfo:
        comparable_moment = comparable_moment.replace(tzinfo=None)
    return comparable_moment >= deadline


def _late_response_label(deadline, responded_at):
    deadline_state = _deadline_label(deadline, responded_at)
    if deadline_state.startswith("Просрочено на "):
        return "С опозданием на " + deadline_state.removeprefix("Просрочено на ")
    return "Без опоздания"


def _normalize_status_filter(value):
    normalized = str(value or "active").strip().lower()
    return (
        normalized
        if normalized in A3_PLATFORM_INCIDENT_STATUS_LABELS
        else "active"
    )


def _normalize_assignee_filter(value):
    normalized = str(value or "all").strip().lower()
    return normalized if normalized in {"all", "unassigned", "me"} else "all"


def build_a3_platform_incidents_url(
    status="active",
    assignee="all",
    search="",
):
    params = {}
    selected_status = _normalize_status_filter(status)
    selected_assignee = _normalize_assignee_filter(assignee)
    selected_search = str(search or "").strip()[:100]

    if selected_status != "active":
        params["status"] = selected_status
    if selected_assignee != "all":
        params["assignee"] = selected_assignee
    if selected_search:
        params["search"] = selected_search

    query = urlencode(params)
    return "/platform/a3-health/incidents" + (f"?{query}" if query else "")


def _incident_url(incident_id, company_id):
    return (
        build_a3_platform_incidents_url(search=str(company_id))
        + f"#incident-{incident_id}"
    )


def _load_platform_admins(cursor):
    return [
        dict(row)
        for row in cursor.execute("""
            SELECT username, full_name, telegram_chat_id
            FROM users
            WHERE role='superadmin'
              AND COALESCE(is_active, 1)=1
            ORDER BY id
        """).fetchall()
    ]


def _platform_admin_exists(cursor, username):
    return bool(cursor.execute("""
        SELECT 1
        FROM users
        WHERE username=?
          AND role='superadmin'
          AND COALESCE(is_active, 1)=1
    """, (username,)).fetchone())


def _log_event(
    cursor,
    incident_id,
    company_id,
    event_type,
    message,
    actor_username="",
    created_at="",
):
    cursor.execute("""
        INSERT INTO a3_platform_incident_events (
            incident_id,
            company_id,
            event_type,
            actor_username,
            message,
            created_at
        ) VALUES (?, ?, ?, ?, ?, ?)
    """, (
        incident_id,
        company_id,
        event_type,
        str(actor_username or "")[:120],
        str(message or "")[:500],
        created_at or _timestamp(),
    ))
    cursor.execute("""
        DELETE FROM a3_platform_incident_events
        WHERE incident_id=?
          AND id NOT IN (
              SELECT id
              FROM a3_platform_incident_events
              WHERE incident_id=?
              ORDER BY id DESC
              LIMIT ?
          )
    """, (
        incident_id,
        incident_id,
        A3_PLATFORM_INCIDENT_EVENT_LIMIT,
    ))


def _create_notifications(
    cursor,
    recipients,
    company_id,
    title,
    message,
    link,
    created_at,
):
    created = 0
    for recipient in recipients:
        username = str(recipient.get("username") or "").strip()
        if not username:
            continue
        cursor.execute("""
            INSERT INTO notifications (
                company_id,
                username,
                title,
                message,
                link,
                is_read,
                created_at
            ) VALUES (?, ?, ?, ?, ?, 0, ?)
        """, (
            company_id,
            username,
            str(title or "")[:200],
            str(message or "")[:1000],
            str(link or "")[:500],
            created_at,
        ))
        created += 1
    return created


def _send_telegram(messages, telegram_sender=None):
    if telegram_sender is None:
        from app.telegram_utils import send_message_to_chat

        telegram_sender = send_message_to_chat

    sent = 0
    for chat_id, text in messages:
        if not str(chat_id or "").strip():
            continue
        try:
            if telegram_sender(chat_id, text):
                sent += 1
        except Exception:
            continue
    return sent


def escalate_overdue_a3_platform_incidents(now=None, telegram_sender=None):
    now_value = now or datetime.now()
    now_text = _timestamp(now_value)
    policy = get_a3_platform_incident_policy()
    result = {
        "checked": 0,
        "escalated": 0,
        "notifications_created": 0,
        "telegram_sent": 0,
    }
    telegram_messages = []
    conn = connect()

    try:
        cursor = conn.cursor()
        cursor.execute("BEGIN IMMEDIATE")
        admins = _load_platform_admins(cursor)
        rows = cursor.execute("""
            SELECT
                incidents.*,
                companies.name AS company_name
            FROM a3_platform_incidents AS incidents
            LEFT JOIN companies ON companies.id=incidents.company_id
            WHERE incidents.status='open'
              AND incidents.acknowledged_at IS NULL
              AND incidents.escalated_at IS NULL
            ORDER BY incidents.first_detected_at, incidents.id
        """).fetchall()

        for row in rows:
            result["checked"] += 1
            incident = dict(row)
            deadline = _incident_deadline(
                incident,
                "escalation_due_at",
                policy["escalation_minutes"],
            )
            if not deadline:
                continue

            if not _deadline_has_arrived(deadline, now_value):
                continue

            cursor.execute("""
                UPDATE a3_platform_incidents
                SET escalated_at=?,
                    escalation_count=COALESCE(escalation_count, 0) + 1,
                    last_notified_at=?,
                    updated_at=?
                WHERE id=?
                  AND status='open'
                  AND acknowledged_at IS NULL
                  AND escalated_at IS NULL
            """, (
                now_text,
                now_text,
                now_text,
                incident["id"],
            ))
            if not cursor.rowcount:
                continue

            company_name = (
                incident.get("company_name")
                or f"Компания #{incident['company_id']}"
            )
            title = f"Эскалация инцидента A3: {company_name}"
            message = (
                f"Инцидент #{incident['id']} не принят в работу за "
                f"{policy['escalation_label']}. Требуется немедленная реакция."
            )
            _log_event(
                cursor,
                incident["id"],
                incident["company_id"],
                "escalated",
                message,
                created_at=now_text,
            )
            result["notifications_created"] += _create_notifications(
                cursor,
                admins,
                incident["company_id"],
                title,
                message,
                _incident_url(incident["id"], incident["company_id"]),
                now_text,
            )
            telegram_text = f"{title}\n{message}"
            telegram_messages.extend(
                (admin.get("telegram_chat_id"), telegram_text)
                for admin in admins
            )
            result["escalated"] += 1

        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    result["telegram_sent"] = _send_telegram(
        telegram_messages,
        telegram_sender=telegram_sender,
    )
    return result


def sync_a3_platform_incidents(report, now=None, telegram_sender=None):
    now_value = now or datetime.now()
    now_text = _timestamp(now_value)
    result = {
        "opened": 0,
        "repeated": 0,
        "resolved": 0,
        "notifications_created": 0,
        "telegram_sent": 0,
        "items_checked": 0,
    }
    telegram_messages = []
    policy = get_a3_platform_incident_policy()
    conn = connect()

    try:
        cursor = conn.cursor()
        cursor.execute("BEGIN IMMEDIATE")
        admins = _load_platform_admins(cursor)

        for item in list((report or {}).get("items") or []):
            company_id = item.get("company_id")
            if not company_id:
                continue

            result["items_checked"] += 1
            status = str(item.get("status") or "error").strip().lower()
            company_name = str(
                item.get("company_name") or f"Компания #{company_id}"
            )[:200]
            message = str(
                item.get("message") or "Контроль A3 обнаружил ошибку."
            )[:1000]
            active = cursor.execute("""
                SELECT *
                FROM a3_platform_incidents
                WHERE company_id=?
                  AND incident_key=?
                  AND status='open'
                LIMIT 1
            """, (
                company_id,
                A3_PLATFORM_INCIDENT_KEY,
            )).fetchone()

            if status in {"critical", "error"}:
                title = f"Критический сбой A3: {company_name}"

                if active:
                    active_data = dict(active)
                    response_due = _incident_deadline(
                        active_data,
                        "response_due_at",
                        policy["response_minutes"],
                    )
                    escalation_due = _incident_deadline(
                        active_data,
                        "escalation_due_at",
                        policy["escalation_minutes"],
                    )
                    message_changed = str(active["message"] or "") != message
                    cursor.execute("""
                        UPDATE a3_platform_incidents
                        SET severity='critical',
                            title=?,
                            message=?,
                            last_detected_at=?,
                            occurrence_count=occurrence_count + 1,
                            response_due_at=COALESCE(response_due_at, ?),
                            escalation_due_at=COALESCE(escalation_due_at, ?),
                            updated_at=?
                        WHERE id=?
                    """, (
                        title,
                        message,
                        now_text,
                        _timestamp(response_due) if response_due else None,
                        _timestamp(escalation_due) if escalation_due else None,
                        now_text,
                        active["id"],
                    ))
                    if message_changed:
                        _log_event(
                            cursor,
                            active["id"],
                            company_id,
                            "updated",
                            message,
                            created_at=now_text,
                        )
                    result["repeated"] += 1
                    continue

                cursor.execute("""
                    INSERT INTO a3_platform_incidents (
                        company_id,
                        incident_key,
                        severity,
                        status,
                        title,
                        message,
                        first_detected_at,
                        last_detected_at,
                        occurrence_count,
                        response_due_at,
                        escalation_due_at,
                        last_notified_at,
                        created_at,
                        updated_at
                    ) VALUES (
                        ?, ?, 'critical', 'open', ?, ?, ?, ?, 1, ?, ?, ?, ?, ?
                    )
                """, (
                    company_id,
                    A3_PLATFORM_INCIDENT_KEY,
                    title,
                    message,
                    now_text,
                    now_text,
                    _timestamp(
                        now_value + timedelta(minutes=policy["response_minutes"])
                    ),
                    _timestamp(
                        now_value + timedelta(minutes=policy["escalation_minutes"])
                    ),
                    now_text,
                    now_text,
                    now_text,
                ))
                incident_id = cursor.lastrowid
                link = _incident_url(incident_id, company_id)
                _log_event(
                    cursor,
                    incident_id,
                    company_id,
                    "opened",
                    message,
                    created_at=now_text,
                )
                result["notifications_created"] += _create_notifications(
                    cursor,
                    admins,
                    company_id,
                    title,
                    message,
                    link,
                    now_text,
                )
                telegram_text = f"{title}\n{message}\nИнцидент #{incident_id}"
                telegram_messages.extend(
                    (admin.get("telegram_chat_id"), telegram_text)
                    for admin in admins
                )
                result["opened"] += 1
                continue

            if status not in {"stable", "skipped"} or not active:
                continue

            resolution_message = (
                "Контроль A3 снова работает штатно."
                if status == "stable"
                else "Контроль A3 приостановлен настройками компании."
            )
            cursor.execute("""
                UPDATE a3_platform_incidents
                SET status='resolved',
                    resolved_at=?,
                    resolution_message=?,
                    review_status='pending',
                    review_due_at=COALESCE(review_due_at, ?),
                    last_notified_at=?,
                    updated_at=?
                WHERE id=? AND status='open'
            """, (
                now_text,
                resolution_message,
                _timestamp(
                    now_value + timedelta(hours=policy["review_hours"])
                ),
                now_text,
                now_text,
                active["id"],
            ))
            _log_event(
                cursor,
                active["id"],
                company_id,
                "resolved",
                resolution_message,
                created_at=now_text,
            )
            title = f"Работа A3 восстановлена: {company_name}"
            link = _incident_url(active["id"], company_id)
            result["notifications_created"] += _create_notifications(
                cursor,
                admins,
                company_id,
                title,
                resolution_message,
                link,
                now_text,
            )
            telegram_text = (
                f"{title}\n{resolution_message}\nИнцидент #{active['id']}"
            )
            telegram_messages.extend(
                (admin.get("telegram_chat_id"), telegram_text)
                for admin in admins
            )
            result["resolved"] += 1

        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    result["telegram_sent"] = _send_telegram(
        telegram_messages,
        telegram_sender=telegram_sender,
    )
    try:
        escalation = escalate_overdue_a3_platform_incidents(
            now=now_value,
            telegram_sender=telegram_sender,
        )
        result["escalated"] = escalation["escalated"]
        result["notifications_created"] += escalation[
            "notifications_created"
        ]
        result["telegram_sent"] += escalation["telegram_sent"]
        result["escalation_error"] = ""
    except Exception:
        result["escalated"] = 0
        result["escalation_error"] = (
            "Не удалось проверить сроки эскалации инцидентов A3."
        )
    return result


def get_a3_platform_incident_summary(now=None):
    now_value = now or datetime.now()
    policy = get_a3_platform_incident_policy()
    conn = connect()
    try:
        cursor = conn.cursor()
        row = cursor.execute("""
            SELECT
                COUNT(*) AS total,
                SUM(CASE WHEN status='open' THEN 1 ELSE 0 END) AS active,
                SUM(
                    CASE WHEN status='open' AND severity='critical'
                    THEN 1 ELSE 0 END
                ) AS critical,
                SUM(
                    CASE WHEN status='open' AND acknowledged_at IS NOT NULL
                    THEN 1 ELSE 0 END
                ) AS acknowledged,
                SUM(
                    CASE WHEN status='open' AND acknowledged_at IS NULL
                    THEN 1 ELSE 0 END
                ) AS unacknowledged,
                SUM(
                    CASE WHEN status='open' AND assigned_to IS NULL
                    THEN 1 ELSE 0 END
                ) AS unassigned,
                SUM(
                    CASE WHEN status='open' AND escalated_at IS NOT NULL
                    THEN 1 ELSE 0 END
                ) AS escalated,
                SUM(CASE WHEN status='resolved' THEN 1 ELSE 0 END) AS resolved
            FROM a3_platform_incidents
        """).fetchone()
        active_rows = [
            dict(item)
            for item in cursor.execute("""
                SELECT first_detected_at, response_due_at, acknowledged_at
                FROM a3_platform_incidents
                WHERE status='open'
                  AND acknowledged_at IS NULL
            """).fetchall()
        ]
    finally:
        conn.close()

    summary = {
        key: int(row[key] or 0)
        for key in (
            "total",
            "active",
            "critical",
            "acknowledged",
            "unacknowledged",
            "unassigned",
            "escalated",
            "resolved",
        )
    }
    summary["response_overdue"] = 0
    for incident in active_rows:
        deadline = _incident_deadline(
            incident,
            "response_due_at",
            policy["response_minutes"],
        )
        if not deadline:
            continue
        if _deadline_is_overdue(deadline, now_value):
            summary["response_overdue"] += 1
    return summary


def get_a3_platform_incident_admins():
    conn = connect()
    try:
        admins = _load_platform_admins(conn.cursor())
    finally:
        conn.close()

    return [
        {
            **admin,
            "display_name": admin.get("full_name") or admin.get("username"),
        }
        for admin in admins
    ]


def get_a3_platform_incidents(
    status_filter="active",
    assignee_filter="all",
    search="",
    current_username="",
    limit=100,
    now=None,
):
    now_value = now or datetime.now()
    now_text = _timestamp(now_value)
    policy = get_a3_platform_incident_policy()
    selected_status = _normalize_status_filter(status_filter)
    selected_assignee = _normalize_assignee_filter(assignee_filter)
    selected_search = str(search or "").strip()[:100]
    safe_limit = max(1, min(int(limit or 100), 300))
    conditions = []
    params = []

    if selected_status == "active":
        conditions.append("incidents.status='open'")
    elif selected_status == "resolved":
        conditions.append("incidents.status='resolved'")
    elif selected_status == "acknowledged":
        conditions.extend([
            "incidents.status='open'",
            "incidents.acknowledged_at IS NOT NULL",
        ])
    elif selected_status == "unacknowledged":
        conditions.extend([
            "incidents.status='open'",
            "incidents.acknowledged_at IS NULL",
        ])
    elif selected_status == "response_overdue":
        conditions.extend([
            "incidents.status='open'",
            "incidents.acknowledged_at IS NULL",
            """
                COALESCE(
                    incidents.response_due_at,
                    datetime(
                        incidents.first_detected_at,
                        '+' || ? || ' minutes'
                    )
                ) < ?
            """,
        ])
        params.extend([policy["response_minutes"], now_text])
    elif selected_status == "escalated":
        conditions.extend([
            "incidents.status='open'",
            "incidents.escalated_at IS NOT NULL",
        ])

    if selected_assignee == "unassigned":
        conditions.append("incidents.assigned_to IS NULL")
    elif selected_assignee == "me":
        conditions.append("incidents.assigned_to=?")
        params.append(str(current_username or ""))

    if selected_search:
        search_value = f"%{selected_search.lower()}%"
        conditions.append("""
            (
                LOWER(COALESCE(companies.name, '')) LIKE ?
                OR LOWER(COALESCE(companies.owner_username, '')) LIKE ?
                OR LOWER(COALESCE(incidents.title, '')) LIKE ?
                OR LOWER(COALESCE(incidents.message, '')) LIKE ?
                OR LOWER(COALESCE(incidents.assigned_to, '')) LIKE ?
                OR CAST(incidents.id AS TEXT)=?
                OR CAST(incidents.company_id AS TEXT)=?
            )
        """)
        params.extend([
            search_value,
            search_value,
            search_value,
            search_value,
            search_value,
            selected_search,
            selected_search,
        ])

    where_sql = "WHERE " + " AND ".join(conditions) if conditions else ""
    conn = connect()
    try:
        rows = conn.cursor().execute(f"""
            SELECT
                incidents.*,
                companies.name AS company_name,
                companies.owner_username
            FROM a3_platform_incidents AS incidents
            LEFT JOIN companies ON companies.id=incidents.company_id
            {where_sql}
            ORDER BY
                CASE incidents.status WHEN 'open' THEN 0 ELSE 1 END,
                CASE incidents.severity WHEN 'critical' THEN 0 ELSE 1 END,
                incidents.updated_at DESC,
                incidents.id DESC
            LIMIT ?
        """, (*params, safe_limit)).fetchall()
        incidents = [dict(row) for row in rows]
        incident_ids = [item["id"] for item in incidents]
        events_by_incident = {incident_id: [] for incident_id in incident_ids}

        if incident_ids:
            placeholders = ",".join("?" for _ in incident_ids)
            event_rows = conn.cursor().execute(f"""
                SELECT *
                FROM a3_platform_incident_events
                WHERE incident_id IN ({placeholders})
                ORDER BY created_at DESC, id DESC
            """, incident_ids).fetchall()
            for row in event_rows:
                event = dict(row)
                incident_events = events_by_incident[event["incident_id"]]
                if len(incident_events) >= 20:
                    continue
                event["event_label"] = A3_PLATFORM_INCIDENT_EVENT_LABELS.get(
                    event.get("event_type"),
                    "Событие инцидента",
                )
                event["created_label"] = _time_label(event.get("created_at"))
                incident_events.append(event)
    finally:
        conn.close()

    for incident in incidents:
        is_open = incident.get("status") == "open"
        response_due = _incident_deadline(
            incident,
            "response_due_at",
            policy["response_minutes"],
        )
        escalation_due = _incident_deadline(
            incident,
            "escalation_due_at",
            policy["escalation_minutes"],
        )
        response_overdue = bool(
            is_open
            and not incident.get("acknowledged_at")
            and _deadline_is_overdue(response_due, now_value)
        )
        acknowledged_at = _parse_datetime(incident.get("acknowledged_at"))
        response_was_late = _deadline_is_overdue(
            response_due,
            acknowledged_at,
        )
        incident.update({
            "company_name": (
                incident.get("company_name")
                or f"Компания #{incident['company_id']}"
            ),
            "status_label": "Открыт" if is_open else "Закрыт",
            "status_tone": "danger" if is_open else "success",
            "work_status_label": (
                "Принят в работу"
                if is_open and incident.get("acknowledged_at")
                else "Ожидает реакции" if is_open else "Работа восстановлена"
            ),
            "work_status_tone": (
                "warning"
                if is_open and incident.get("acknowledged_at")
                else "danger" if is_open else "success"
            ),
            "assignee_label": incident.get("assigned_to") or "Не назначен",
            "response_status_label": (
                "Реакция с опозданием"
                if response_was_late
                else "Реакция зафиксирована"
                if acknowledged_at
                else "Реакция просрочена"
                if response_overdue
                else "Ожидается реакция" if is_open else "Закрыт"
            ),
            "response_status_tone": (
                "danger"
                if response_was_late or response_overdue
                else "success"
                if acknowledged_at or not is_open
                else "warning"
            ),
            "response_due_label": _time_label(response_due),
            "response_remaining_label": _deadline_label(
                response_due,
                now_value,
            ),
            "response_progress_label": (
                (
                    f"{_late_response_label(response_due, acknowledged_at)} · "
                    f"{_time_label(incident.get('acknowledged_at'))}"
                )
                if acknowledged_at
                else "Инцидент закрыт"
                if not is_open
                else _deadline_label(response_due, now_value)
            ),
            "escalation_due_label": _time_label(escalation_due),
            "escalation_remaining_label": _deadline_label(
                escalation_due,
                now_value,
            ),
            "is_escalated": bool(incident.get("escalated_at")),
            "response_was_late": response_was_late,
            "escalated_label": _time_label(incident.get("escalated_at")),
            "escalation_progress_label": (
                f"Выполнена: {_time_label(incident.get('escalated_at'))}"
                if incident.get("escalated_at")
                else "Не требуется после реакции"
                if incident.get("acknowledged_at")
                else "Инцидент закрыт"
                if not is_open
                else _deadline_label(escalation_due, now_value)
            ),
            "first_detected_label": _time_label(
                incident.get("first_detected_at")
            ),
            "last_detected_label": _time_label(
                incident.get("last_detected_at")
            ),
            "updated_label": _time_label(incident.get("updated_at")),
            "updated_age_label": _age_label(
                incident.get("updated_at"),
                now_value=now_value,
            ),
            "resolved_label": _time_label(incident.get("resolved_at")),
            "events": events_by_incident.get(incident["id"], []),
            "company_url": f"/platform/companies/{incident['company_id']}",
            "review_url": (
                "/platform/a3-health/incidents/reviews?status=all&search="
                + str(incident["id"])
                + f"#review-{incident['id']}"
            ),
        })

    summary = get_a3_platform_incident_summary(now=now_value)
    status_options = []
    for key, label in A3_PLATFORM_INCIDENT_STATUS_LABELS.items():
        count = {
            "active": summary["active"],
            "unacknowledged": summary["unacknowledged"],
            "acknowledged": summary["acknowledged"],
            "response_overdue": summary["response_overdue"],
            "escalated": summary["escalated"],
            "resolved": summary["resolved"],
            "all": summary["total"],
        }[key]
        status_options.append({
            "key": key,
            "label": label,
            "count": count,
            "url": build_a3_platform_incidents_url(
                key,
                selected_assignee,
                selected_search,
            ),
        })

    return {
        "generated_at": now_value.strftime("%d.%m.%Y %H:%M"),
        "status_filter": selected_status,
        "assignee_filter": selected_assignee,
        "search": selected_search,
        "summary": summary,
        "items": incidents,
        "status_options": status_options,
        "base_url": "/platform/a3-health/incidents",
        "visible": len(incidents),
        "policy": policy,
    }


def acknowledge_a3_platform_incident(
    incident_id,
    actor_username,
    now=None,
):
    now_value = now or datetime.now()
    now_text = _timestamp(now_value)
    conn = connect()
    try:
        cursor = conn.cursor()
        cursor.execute("BEGIN IMMEDIATE")
        if not _platform_admin_exists(cursor, actor_username):
            conn.rollback()
            return {
                "ok": False,
                "error": "forbidden",
                "message": "Недостаточно прав для работы с инцидентом.",
            }

        incident = cursor.execute("""
            SELECT * FROM a3_platform_incidents
            WHERE id=? AND status='open'
        """, (incident_id,)).fetchone()
        if not incident:
            conn.rollback()
            return {
                "ok": False,
                "error": "incident_not_found",
                "message": "Активный инцидент не найден.",
            }
        if incident["acknowledged_at"]:
            conn.rollback()
            return {
                "ok": False,
                "error": "already_acknowledged",
                "message": "Инцидент уже принят в работу.",
            }

        incident_data = dict(incident)
        response_due = _incident_deadline(
            incident_data,
            "response_due_at",
            get_a3_platform_incident_policy()["response_minutes"],
        )
        response_was_late = _deadline_is_overdue(response_due, now_value)
        assigned_to = incident["assigned_to"] or actor_username
        cursor.execute("""
            UPDATE a3_platform_incidents
            SET acknowledged_at=?,
                acknowledged_by=?,
                assigned_at=COALESCE(assigned_at, ?),
                assigned_to=COALESCE(assigned_to, ?),
                assigned_by=COALESCE(assigned_by, ?),
                updated_at=?
            WHERE id=? AND status='open' AND acknowledged_at IS NULL
        """, (
            now_text,
            actor_username,
            now_text,
            actor_username,
            actor_username,
            now_text,
            incident_id,
        ))
        response_message = f"Инцидент принял в работу {actor_username}."
        if response_was_late:
            response_message += " " + _late_response_label(
                response_due,
                now_value,
            ) + "."
        _log_event(
            cursor,
            incident_id,
            incident["company_id"],
            "acknowledged",
            response_message,
            actor_username=actor_username,
            created_at=now_text,
        )
        conn.commit()
        return {
            "ok": True,
            "incident_id": incident_id,
            "assigned_to": assigned_to,
            "response_was_late": response_was_late,
            "message": "Инцидент принят в работу.",
        }
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def assign_a3_platform_incident(
    incident_id,
    actor_username,
    assignee_username,
    now=None,
    telegram_sender=None,
):
    assignee = str(assignee_username or "").strip()[:120]
    now_text = _timestamp(now)
    telegram_messages = []
    conn = connect()
    try:
        cursor = conn.cursor()
        cursor.execute("BEGIN IMMEDIATE")
        if not _platform_admin_exists(cursor, actor_username):
            conn.rollback()
            return {
                "ok": False,
                "error": "forbidden",
                "message": "Недостаточно прав для назначения ответственного.",
            }
        if not assignee or not _platform_admin_exists(cursor, assignee):
            conn.rollback()
            return {
                "ok": False,
                "error": "invalid_assignee",
                "message": "Выберите активного администратора платформы.",
            }

        incident = cursor.execute("""
            SELECT incidents.*, companies.name AS company_name
            FROM a3_platform_incidents AS incidents
            LEFT JOIN companies ON companies.id=incidents.company_id
            WHERE incidents.id=? AND incidents.status='open'
        """, (incident_id,)).fetchone()
        if not incident:
            conn.rollback()
            return {
                "ok": False,
                "error": "incident_not_found",
                "message": "Активный инцидент не найден.",
            }
        if str(incident["assigned_to"] or "") == assignee:
            conn.rollback()
            return {
                "ok": True,
                "incident_id": incident_id,
                "assigned_to": assignee,
                "notifications_created": 0,
                "telegram_sent": 0,
                "message": "Ответственный уже назначен.",
            }

        cursor.execute("""
            UPDATE a3_platform_incidents
            SET assigned_at=?, assigned_to=?, assigned_by=?,
                last_notified_at=?, updated_at=?
            WHERE id=? AND status='open'
        """, (
            now_text,
            assignee,
            actor_username,
            now_text,
            now_text,
            incident_id,
        ))
        event_message = f"Ответственным назначен {assignee}."
        _log_event(
            cursor,
            incident_id,
            incident["company_id"],
            "assigned",
            event_message,
            actor_username=actor_username,
            created_at=now_text,
        )
        assignee_row = cursor.execute("""
            SELECT username, telegram_chat_id
            FROM users
            WHERE username=?
        """, (assignee,)).fetchone()
        title = f"Вам назначен инцидент A3 #{incident_id}"
        message = (
            f"Компания: {incident['company_name'] or incident['company_id']}. "
            f"{incident['message'] or 'Требуется проверка A3.'}"
        )
        result = {
            "ok": True,
            "incident_id": incident_id,
            "assigned_to": assignee,
            "notifications_created": _create_notifications(
                cursor,
                [dict(assignee_row)],
                incident["company_id"],
                title,
                message,
                _incident_url(incident_id, incident["company_id"]),
                now_text,
            ),
            "message": "Ответственный назначен.",
        }
        telegram_messages.append((assignee_row["telegram_chat_id"], f"{title}\n{message}"))
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    result["telegram_sent"] = _send_telegram(
        telegram_messages,
        telegram_sender=telegram_sender,
    )
    return result


def add_a3_platform_incident_note(
    incident_id,
    actor_username,
    note,
    now=None,
):
    note_text = str(note or "").strip()[:500]
    if not note_text:
        return {
            "ok": False,
            "error": "empty_note",
            "message": "Введите текст комментария.",
        }

    now_text = _timestamp(now)
    conn = connect()
    try:
        cursor = conn.cursor()
        cursor.execute("BEGIN IMMEDIATE")
        if not _platform_admin_exists(cursor, actor_username):
            conn.rollback()
            return {
                "ok": False,
                "error": "forbidden",
                "message": "Недостаточно прав для комментария.",
            }
        incident = cursor.execute("""
            SELECT id, company_id
            FROM a3_platform_incidents
            WHERE id=? AND status='open'
        """, (incident_id,)).fetchone()
        if not incident:
            conn.rollback()
            return {
                "ok": False,
                "error": "incident_not_found",
                "message": "Активный инцидент не найден.",
            }

        _log_event(
            cursor,
            incident_id,
            incident["company_id"],
            "note",
            note_text,
            actor_username=actor_username,
            created_at=now_text,
        )
        cursor.execute("""
            UPDATE a3_platform_incidents
            SET updated_at=?
            WHERE id=?
        """, (now_text, incident_id))
        conn.commit()
        return {
            "ok": True,
            "incident_id": incident_id,
            "message": "Комментарий добавлен.",
        }
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
