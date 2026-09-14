import os
from datetime import datetime, timedelta

from app.database import connect
from app.services.a3_followup_analytics import get_a3_followup_analytics


A3_FOLLOWUP_REPEAT_RETURN_THRESHOLD = 2
A3_FOLLOWUP_LOW_QUALITY_SCORE = 70
A3_FOLLOWUP_QUALITY_MIN_REVIEWS = 2
A3_FOLLOWUP_QUALITY_COOLDOWN_HOURS = 24
A3_FOLLOWUP_QUALITY_LOOKBACK_DAYS = 30


def _environment_int(name, default, minimum, maximum):
    try:
        value = int(str(os.getenv(name, default)).strip())
    except (TypeError, ValueError):
        value = default
    return max(minimum, min(value, maximum))


def get_a3_followup_quality_policy():
    requested_lookback = _environment_int(
        "A3_FOLLOWUP_QUALITY_LOOKBACK_DAYS",
        A3_FOLLOWUP_QUALITY_LOOKBACK_DAYS,
        7,
        90,
    )
    lookback_days = min(
        (7, 30, 90),
        key=lambda value: (abs(value - requested_lookback), value),
    )
    return {
        "repeat_return_threshold": _environment_int(
            "A3_FOLLOWUP_REPEAT_RETURN_THRESHOLD",
            A3_FOLLOWUP_REPEAT_RETURN_THRESHOLD,
            2,
            20,
        ),
        "low_quality_score": _environment_int(
            "A3_FOLLOWUP_LOW_QUALITY_SCORE",
            A3_FOLLOWUP_LOW_QUALITY_SCORE,
            1,
            99,
        ),
        "minimum_reviews": _environment_int(
            "A3_FOLLOWUP_QUALITY_MIN_REVIEWS",
            A3_FOLLOWUP_QUALITY_MIN_REVIEWS,
            1,
            100,
        ),
        "cooldown_hours": _environment_int(
            "A3_FOLLOWUP_QUALITY_COOLDOWN_HOURS",
            A3_FOLLOWUP_QUALITY_COOLDOWN_HOURS,
            1,
            720,
        ),
        "lookback_days": lookback_days,
    }


def _load_admins(cursor):
    return [dict(row) for row in cursor.execute("""
        SELECT username, full_name, telegram_chat_id
        FROM users
        WHERE role='superadmin' AND COALESCE(is_active, 1)=1
        ORDER BY id
    """).fetchall()]


def _recipients(signal, admins):
    owner = str(signal.get("owner_username") or "").strip()
    assigned = [admin for admin in admins if admin["username"] == owner]
    return assigned or admins


def _quality_signals(report, policy):
    signals = []
    for item in report["repeat_returns"]:
        if item["rework_count"] < policy["repeat_return_threshold"]:
            continue
        signals.append({
            "key": f"repeat_return:{item['id']}",
            "type": "repeat_return",
            "type_label": "Повторный возврат",
            "severity": "critical" if item["rework_count"] >= 3 else "warning",
            "company_id": item["company_id"],
            "incident_id": item["incident_id"],
            "owner_username": item["owner_username"],
            "title": f"Повторные возвраты меры A3 #{item['id']}",
            "message": (
                f"Мера «{item['title']}» возвращалась на доработку "
                f"{item['rework_count']} раз. Проверок: "
                f"{item['verification_attempts']}."
            ),
            "metric": item["rework_count"],
            "metric_label": f"{item['rework_count']} возврата",
            "link": item["url"],
        })
    for item in report["owner_quality"]:
        score = item["quality_score"]
        if (
            score is None
            or item["reviewed_actions"] < policy["minimum_reviews"]
            or score >= policy["low_quality_score"]
        ):
            continue
        signals.append({
            "key": f"low_quality:{item['key']}",
            "type": "low_quality",
            "type_label": "Низкое качество",
            "severity": "critical" if score < 50 else "warning",
            "company_id": 1,
            "owner_username": item["key"],
            "title": f"Снизилось качество мер A3: {item['label']}",
            "message": (
                f"Оценка качества за {report['date_from']} — "
                f"{report['date_to']}: {score} из 100. Возвратов: "
                f"{item['returns_total']}, просрочено: {item['overdue']}."
            ),
            "metric": score,
            "metric_label": f"{score} из 100",
            "link": "/platform/a3-health/incidents/analytics#followup-quality",
        })
    return sorted(signals, key=lambda item: (
        item["severity"] != "critical", item["type"], item["key"],
    ))


def _recently_notified(cursor, signal, username, cutoff):
    return bool(cursor.execute("""
        SELECT 1
        FROM notifications
        WHERE username=? AND title=? AND link=? AND created_at>=?
        LIMIT 1
    """, (
        username,
        signal["title"],
        signal["link"],
        cutoff,
    )).fetchone())


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


def get_a3_followup_quality_monitor_overview(now=None):
    now_value = now or datetime.now()
    policy = get_a3_followup_quality_policy()
    report = get_a3_followup_analytics(
        period=str(policy["lookback_days"]),
        now=now_value,
    )
    signals = _quality_signals(report, policy)
    cutoff = (now_value - timedelta(hours=policy["cooldown_hours"])).strftime(
        "%Y-%m-%d %H:%M:%S"
    )
    conn = connect()
    try:
        cursor = conn.cursor()
        admins = _load_admins(cursor)
        for signal in signals:
            recipients = _recipients(signal, admins)
            signal["ready"] = any(
                not _recently_notified(cursor, signal, recipient["username"], cutoff)
                for recipient in recipients
            )
    finally:
        conn.close()
    summary = {
        "total": len(signals),
        "critical": sum(item["severity"] == "critical" for item in signals),
        "repeat_returns": sum(item["type"] == "repeat_return" for item in signals),
        "low_quality": sum(item["type"] == "low_quality" for item in signals),
        "ready": sum(item["ready"] for item in signals),
    }
    status = "critical" if summary["critical"] else "warning" if signals else "stable"
    return {
        "generated_at": now_value.strftime("%d.%m.%Y %H:%M"),
        "status": status,
        "status_label": {
            "critical": "Есть критические сигналы качества",
            "warning": "Качество требует внимания",
            "stable": "Качество под контролем",
        }[status],
        "summary": summary,
        "signals": signals,
        "policy": policy,
    }


def run_a3_followup_quality_monitor(now=None, telegram_sender=None):
    now_value = now or datetime.now()
    now_text = now_value.strftime("%Y-%m-%d %H:%M:%S")
    overview = get_a3_followup_quality_monitor_overview(now=now_value)
    cutoff = (now_value - timedelta(
        hours=overview["policy"]["cooldown_hours"]
    )).strftime("%Y-%m-%d %H:%M:%S")
    result = {
        "checked": len(overview["signals"]),
        "repeat_returns": overview["summary"]["repeat_returns"],
        "low_quality": overview["summary"]["low_quality"],
        "notified_signals": 0,
        "notifications_created": 0,
        "telegram_sent": 0,
        "suppressed": 0,
        "without_recipients": 0,
        "items": [],
        "policy": overview["policy"],
    }
    telegram_messages = []
    conn = connect()
    try:
        cursor = conn.cursor()
        cursor.execute("BEGIN IMMEDIATE")
        admins = _load_admins(cursor)
        for signal in overview["signals"]:
            recipients = _recipients(signal, admins)
            if not recipients:
                result["without_recipients"] += 1
                continue
            notified = 0
            for recipient in recipients:
                if _recently_notified(
                    cursor, signal, recipient["username"], cutoff,
                ):
                    result["suppressed"] += 1
                    continue
                cursor.execute("""
                    INSERT INTO notifications (
                        company_id, username, title, message, link,
                        is_read, created_at
                    ) VALUES (?, ?, ?, ?, ?, 0, ?)
                """, (
                    signal["company_id"],
                    recipient["username"],
                    signal["title"][:200],
                    signal["message"][:1000],
                    signal["link"],
                    now_text,
                ))
                notified += 1
                result["notifications_created"] += 1
                telegram_messages.append((
                    recipient.get("telegram_chat_id"),
                    f"{signal['title']}\n{signal['message']}",
                ))
            if notified:
                result["notified_signals"] += 1
                if signal["type"] == "repeat_return":
                    cursor.execute("""
                        INSERT INTO a3_platform_incident_events (
                            incident_id, company_id, event_type,
                            actor_username, message, created_at
                        ) VALUES (?, ?, 'followup_quality_alert',
                                  'a3_quality_monitor', ?, ?)
                    """, (
                        signal["incident_id"],
                        signal["company_id"],
                        signal["message"][:500],
                        now_text,
                    ))
                result["items"].append({
                    "key": signal["key"],
                    "type": signal["type"],
                    "severity": signal["severity"],
                    "recipient_count": notified,
                    "link": signal["link"],
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
