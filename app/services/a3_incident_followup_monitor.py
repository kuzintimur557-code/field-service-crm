import os
from datetime import datetime, timedelta

from app.database import connect


A3_FOLLOWUP_DUE_SOON_HOURS = 24
A3_FOLLOWUP_REMINDER_COOLDOWN_HOURS = 24


def _environment_hours(name, default, minimum=1, maximum=720):
    try:
        value = int(str(os.getenv(name, default)).strip())
    except (TypeError, ValueError):
        value = default
    return max(minimum, min(value, maximum))


def get_a3_followup_monitor_policy():
    due_soon_hours = _environment_hours(
        "A3_FOLLOWUP_DUE_SOON_HOURS",
        A3_FOLLOWUP_DUE_SOON_HOURS,
    )
    cooldown_hours = _environment_hours(
        "A3_FOLLOWUP_REMINDER_COOLDOWN_HOURS",
        A3_FOLLOWUP_REMINDER_COOLDOWN_HOURS,
    )
    return {
        "due_soon_hours": due_soon_hours,
        "cooldown_hours": cooldown_hours,
        "due_soon_label": f"{due_soon_hours} ч.",
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


def _timestamp(value=None):
    return (value or datetime.now()).strftime("%Y-%m-%d %H:%M:%S")


def _time_label(value):
    parsed = value if isinstance(value, datetime) else _parse_datetime(value)
    return parsed.strftime("%d.%m.%Y %H:%M") if parsed else "Не указано"


def _reminder_stage(due_at, now_value, due_soon_hours):
    if not due_at:
        return ""
    comparable_now = _align_datetime(now_value, due_at)
    if comparable_now > due_at:
        return "overdue"
    if due_at <= comparable_now + timedelta(hours=due_soon_hours):
        return "due_soon"
    return ""


def _can_remind(item, stage, now_value, cooldown_hours):
    if not stage:
        return False
    if stage != str(item.get("reminder_stage") or ""):
        return True
    last_reminded = _parse_datetime(item.get("last_reminded_at"))
    if not last_reminded:
        return True
    comparable_now = _align_datetime(now_value, last_reminded)
    return comparable_now - last_reminded >= timedelta(hours=cooldown_hours)


def _load_platform_admins(cursor):
    return [
        dict(row)
        for row in cursor.execute("""
            SELECT username, full_name, telegram_chat_id
            FROM users
            WHERE role='superadmin' AND COALESCE(is_active, 1)=1
            ORDER BY id
        """).fetchall()
    ]


def _notification_recipients(item, admins):
    owner = str(item.get("owner_username") or "").strip()
    if owner:
        assigned = [admin for admin in admins if admin["username"] == owner]
        if assigned:
            return assigned
    return admins


def _action_link(item):
    return (
        "/platform/a3-health/incidents/actions?status=all&incident_id="
        f"{item['incident_id']}#action-{item['id']}"
    )


def _stage_content(item, stage, due_at):
    company_name = item.get("company_name") or f"Компания #{item['company_id']}"
    if stage == "overdue":
        title = f"Просрочена контрольная мера A3: {company_name}"
        message = (
            f"Мера #{item['id']} «{item['title']}» по инциденту "
            f"#{item['incident_id']} просрочена. Срок: {_time_label(due_at)}."
        )
    else:
        title = f"Приближается срок меры A3: {company_name}"
        message = (
            f"Меру #{item['id']} «{item['title']}» по инциденту "
            f"#{item['incident_id']} нужно выполнить до {_time_label(due_at)}."
        )
    return title, message


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


def get_a3_followup_monitor_overview(now=None):
    now_value = now or datetime.now()
    policy = get_a3_followup_monitor_policy()
    conn = connect()
    try:
        rows = [
            dict(row)
            for row in conn.cursor().execute("""
                SELECT *
                FROM a3_incident_followups
                WHERE status IN ('open', 'in_progress')
                ORDER BY due_at, id
            """).fetchall()
        ]
    finally:
        conn.close()

    overview = {
        "active": len(rows),
        "due_soon": 0,
        "overdue": 0,
        "ready": 0,
        "reminders_sent": sum(int(row.get("reminder_count") or 0) for row in rows),
        "last_reminded_at": max(
            (str(row.get("last_reminded_at") or "") for row in rows),
            default="",
        ),
        "policy": policy,
    }
    for item in rows:
        due_at = _parse_datetime(item.get("due_at"))
        stage = _reminder_stage(
            due_at,
            now_value,
            policy["due_soon_hours"],
        )
        if stage == "overdue":
            overview["overdue"] += 1
        elif stage == "due_soon":
            overview["due_soon"] += 1
        if _can_remind(item, stage, now_value, policy["cooldown_hours"]):
            overview["ready"] += 1

    overview["last_reminded_label"] = (
        _time_label(overview["last_reminded_at"])
        if overview["last_reminded_at"] else "Напоминаний ещё не было"
    )
    overview["status"] = (
        "critical"
        if overview["overdue"] else "warning" if overview["due_soon"] else "stable"
    )
    overview["status_label"] = {
        "critical": "Есть просроченные меры",
        "warning": "Приближаются сроки",
        "stable": "Сроки под контролем",
    }[overview["status"]]
    return overview


def run_a3_incident_followup_monitor(now=None, telegram_sender=None):
    now_value = now or datetime.now()
    now_text = _timestamp(now_value)
    policy = get_a3_followup_monitor_policy()
    result = {
        "checked": 0,
        "due_soon": 0,
        "overdue": 0,
        "notified_actions": 0,
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
        cursor.execute("BEGIN IMMEDIATE")
        admins = _load_platform_admins(cursor)
        rows = cursor.execute("""
            SELECT
                followups.*,
                incidents.title AS incident_title,
                COALESCE(
                    companies.name,
                    'Компания #' || followups.company_id
                ) AS company_name
            FROM a3_incident_followups AS followups
            JOIN a3_platform_incidents AS incidents
              ON incidents.id=followups.incident_id
            LEFT JOIN companies ON companies.id=followups.company_id
            WHERE followups.status IN ('open', 'in_progress')
            ORDER BY followups.due_at, followups.id
        """).fetchall()

        for row in rows:
            result["checked"] += 1
            item = dict(row)
            due_at = _parse_datetime(item.get("due_at"))
            stage = _reminder_stage(
                due_at,
                now_value,
                policy["due_soon_hours"],
            )
            if stage == "overdue":
                result["overdue"] += 1
            elif stage == "due_soon":
                result["due_soon"] += 1
            if not stage:
                continue
            if not _can_remind(
                item,
                stage,
                now_value,
                policy["cooldown_hours"],
            ):
                result["suppressed"] += 1
                continue

            recipients = _notification_recipients(item, admins)
            if not recipients:
                result["without_recipients"] += 1
                continue
            title, message = _stage_content(item, stage, due_at)
            link = _action_link(item)
            for recipient in recipients:
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
                    item["company_id"],
                    recipient["username"],
                    title[:200],
                    message[:1000],
                    link,
                    now_text,
                ))
                result["notifications_created"] += 1
                telegram_messages.append((
                    recipient.get("telegram_chat_id"),
                    f"{title}\n{message}",
                ))
            cursor.execute("""
                UPDATE a3_incident_followups
                SET reminder_stage=?,
                    last_reminded_at=?,
                    reminder_count=COALESCE(reminder_count, 0) + 1,
                    updated_at=?
                WHERE id=? AND status IN ('open', 'in_progress')
            """, (stage, now_text, now_text, item["id"]))
            cursor.execute("""
                INSERT INTO a3_platform_incident_events (
                    incident_id,
                    company_id,
                    event_type,
                    actor_username,
                    message,
                    created_at
                ) VALUES (?, ?, 'followup_reminder', 'a3_monitor', ?, ?)
            """, (
                item["incident_id"],
                item["company_id"],
                message[:500],
                now_text,
            ))
            result["notified_actions"] += 1
            result["items"].append({
                "id": int(item["id"]),
                "incident_id": int(item["incident_id"]),
                "company_id": int(item["company_id"]),
                "stage": stage,
                "recipient_count": len(recipients),
                "link": link,
            })
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
