import os
from datetime import datetime, timedelta
from urllib.parse import urlencode

from app.database import begin_locked_transaction, connect
from app.services.a3_followup_analytics import get_a3_followup_analytics
from app.services.a3_followup_quality_sla import (
    enrich_a3_followup_quality_alert_sla,
    get_a3_followup_quality_sla_policy,
    persist_a3_followup_quality_alert_deadlines,
)


A3_FOLLOWUP_REPEAT_RETURN_THRESHOLD = 2
A3_FOLLOWUP_LOW_QUALITY_SCORE = 70
A3_FOLLOWUP_QUALITY_MIN_REVIEWS = 2
A3_FOLLOWUP_QUALITY_COOLDOWN_HOURS = 24
A3_FOLLOWUP_QUALITY_LOOKBACK_DAYS = 30

A3_QUALITY_ALERT_STATUS_LABELS = {
    "active": "Активен",
    "acknowledged": "Принят в работу",
    "resolved": "Закрыт",
}
A3_QUALITY_ALERT_FILTER_LABELS = {
    "active": "Активные",
    "acknowledged": "В работе",
    "resolved": "Закрытые",
    "all": "Все",
}


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


def build_a3_followup_quality_alerts_url(status="active", search=""):
    selected_status = str(status or "active").strip().lower()
    if selected_status not in A3_QUALITY_ALERT_FILTER_LABELS:
        selected_status = "active"
    parts = []
    if selected_status != "active":
        parts.append(f"status={selected_status}")
    search_text = str(search or "").strip()[:100]
    if search_text:
        parts.append(urlencode({"search": search_text}))
    return "/platform/a3-health/incidents/actions/quality-alerts" + (
        "?" + "&".join(parts) if parts else ""
    )


def _parse_datetime(value):
    try:
        return datetime.fromisoformat(str(value or "").replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None


def _time_label(value):
    parsed = value if isinstance(value, datetime) else _parse_datetime(value)
    return parsed.strftime("%d.%m.%Y %H:%M") if parsed else "Не указано"


def _elapsed_hours(now_value, value):
    parsed = _parse_datetime(value)
    if not parsed:
        return 0.0
    clock = now_value
    if (clock.tzinfo is None) != (parsed.tzinfo is None):
        if clock.tzinfo is not None:
            clock = clock.replace(tzinfo=None)
        if parsed.tzinfo is not None:
            parsed = parsed.replace(tzinfo=None)
    return round(max(0, (clock - parsed).total_seconds() / 3600), 1)


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


def _signal_worsened(signal, alert):
    previous = float(alert.get("metric_value") or 0)
    current = float(signal.get("metric") or 0)
    if signal["type"] == "low_quality":
        return current < previous
    return current > previous


def _latest_alerts(cursor):
    rows = cursor.execute("""
        SELECT alerts.*
        FROM a3_followup_quality_alerts AS alerts
        JOIN (
            SELECT alert_key, MAX(id) AS latest_id
            FROM a3_followup_quality_alerts
            GROUP BY alert_key
        ) AS latest ON latest.latest_id=alerts.id
    """).fetchall()
    return {row["alert_key"]: dict(row) for row in rows}


def _sync_quality_alerts(cursor, signals, now_text):
    latest = _latest_alerts(cursor)
    sla_policy = get_a3_followup_quality_sla_policy()
    persist_a3_followup_quality_alert_deadlines(cursor, latest.values(), sla_policy)
    detected_keys = {signal["key"] for signal in signals}
    active = {}
    reopened = 0
    created = 0
    auto_resolved = 0
    for signal in signals:
        alert = latest.get(signal["key"])
        if alert and alert["status"] in {"active", "acknowledged"}:
            cursor.execute("""
                UPDATE a3_followup_quality_alerts
                SET severity=?, title=?, message=?, link=?, metric_value=?,
                    last_detected_at=?, updated_at=?
                WHERE id=?
            """, (
                signal["severity"], signal["title"], signal["message"],
                signal["link"], signal["metric"], now_text, now_text,
                alert["id"],
            ))
            active[signal["key"]] = {
                **alert,
                **signal,
                "id": alert["id"],
                "last_notified_at": alert.get("last_notified_at"),
            }
            continue
        if (
            alert
            and alert["status"] == "resolved"
            and alert.get("resolution_kind") == "manual"
            and not _signal_worsened(signal, alert)
        ):
            continue
        cursor.execute("""
            INSERT INTO a3_followup_quality_alerts (
                alert_key, alert_type, severity, company_id, incident_id,
                owner_username, title, message, link, metric_value, status,
                first_detected_at, last_detected_at, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'active', ?, ?, ?, ?)
        """, (
            signal["key"], signal["type"], signal["severity"],
            signal["company_id"], signal.get("incident_id"),
            signal.get("owner_username"), signal["title"], signal["message"],
            signal["link"], signal["metric"], now_text, now_text,
            now_text, now_text,
        ))
        alert_id = cursor.lastrowid
        persist_a3_followup_quality_alert_deadlines(cursor, [{
            "id": alert_id, "first_detected_at": now_text,
        }], sla_policy)
        active[signal["key"]] = {
            **signal,
            "id": alert_id,
            "last_notified_at": None,
        }
        if alert:
            reopened += 1
        else:
            created += 1
    for key, alert in latest.items():
        if alert["status"] not in {"active", "acknowledged"} or key in detected_keys:
            continue
        cursor.execute("""
            UPDATE a3_followup_quality_alerts
            SET status='resolved', resolved_at=?, resolved_by='a3_quality_monitor',
                resolution_note='Показатель вернулся в допустимый диапазон.',
                resolution_kind='automatic', updated_at=?
            WHERE id=?
        """, (now_text, now_text, alert["id"]))
        if alert.get("incident_id"):
            cursor.execute("""
                INSERT INTO a3_platform_incident_events (
                    incident_id, company_id, event_type,
                    actor_username, message, created_at
                ) VALUES (?, ?, 'followup_quality_resolved',
                          'a3_quality_monitor', ?, ?)
            """, (
                alert["incident_id"], alert["company_id"],
                "Сигнал качества закрыт автоматически: показатель "
                "вернулся в допустимый диапазон.",
                now_text,
            ))
        auto_resolved += 1
    return {
        "active": active,
        "created": created,
        "reopened": reopened,
        "auto_resolved": auto_resolved,
    }


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
    cutoff = now_value - timedelta(hours=policy["cooldown_hours"])
    conn = connect()
    try:
        cursor = conn.cursor()
        admins = _load_admins(cursor)
        latest = _latest_alerts(cursor)
        for signal in signals:
            recipients = _recipients(signal, admins)
            alert = latest.get(signal["key"])
            manually_resolved = bool(
                alert
                and alert["status"] == "resolved"
                and alert.get("resolution_kind") == "manual"
                and not _signal_worsened(signal, alert)
            )
            last_notified = _parse_datetime(
                alert.get("last_notified_at") if alert else None
            )
            signal["alert_id"] = alert["id"] if alert else None
            signal["managed_status"] = alert["status"] if alert else "new"
            signal["actionable"] = bool(recipients) and not manually_resolved
            signal["ready"] = bool(
                signal["actionable"]
                and (not last_notified or last_notified <= cutoff)
            )
    finally:
        conn.close()
    summary = {
        "total": sum(item["actionable"] for item in signals),
        "critical": sum(
            item["actionable"] and item["severity"] == "critical"
            for item in signals
        ),
        "repeat_returns": sum(
            item["actionable"] and item["type"] == "repeat_return"
            for item in signals
        ),
        "low_quality": sum(
            item["actionable"] and item["type"] == "low_quality"
            for item in signals
        ),
        "ready": sum(item["ready"] for item in signals),
    }
    status = (
        "critical" if summary["critical"]
        else "warning" if summary["total"] else "stable"
    )
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
    cutoff = now_value - timedelta(
        hours=overview["policy"]["cooldown_hours"]
    )
    result = {
        "checked": len(overview["signals"]),
        "repeat_returns": overview["summary"]["repeat_returns"],
        "low_quality": overview["summary"]["low_quality"],
        "notified_signals": 0,
        "notifications_created": 0,
        "telegram_sent": 0,
        "suppressed": 0,
        "without_recipients": 0,
        "alerts_created": 0,
        "alerts_reopened": 0,
        "alerts_auto_resolved": 0,
        "items": [],
        "policy": overview["policy"],
    }
    telegram_messages = []
    conn = connect()
    try:
        cursor = conn.cursor()
        begin_locked_transaction(cursor, "a3_platform_operations")
        admins = _load_admins(cursor)
        synced = _sync_quality_alerts(cursor, overview["signals"], now_text)
        result["alerts_created"] = synced["created"]
        result["alerts_reopened"] = synced["reopened"]
        result["alerts_auto_resolved"] = synced["auto_resolved"]
        for signal in overview["signals"]:
            alert = synced["active"].get(signal["key"])
            if not alert:
                result["suppressed"] += 1
                continue
            recipients = _recipients(signal, admins)
            if not recipients:
                result["without_recipients"] += 1
                continue
            last_notified = _parse_datetime(alert.get("last_notified_at"))
            if last_notified and last_notified > cutoff:
                result["suppressed"] += 1
                continue
            notified = 0
            for recipient in recipients:
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
                cursor.execute("""
                    UPDATE a3_followup_quality_alerts
                    SET last_notified_at=?,
                        notification_count=notification_count + 1,
                        updated_at=?
                    WHERE id=?
                """, (now_text, now_text, alert["id"]))
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
                    "alert_id": alert["id"],
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


def get_a3_followup_quality_alerts(
    status_filter="active",
    search="",
    limit=200,
    now=None,
):
    selected_status = str(status_filter or "active").strip().lower()
    if selected_status not in A3_QUALITY_ALERT_FILTER_LABELS:
        selected_status = "active"
    search_text = str(search or "").strip()[:100]
    safe_limit = max(1, min(int(limit or 200), 500))
    conditions = []
    params = []
    if selected_status == "active":
        conditions.append("status IN ('active', 'acknowledged')")
    elif selected_status != "all":
        conditions.append("status=?")
        params.append(selected_status)
    where_sql = "WHERE " + " AND ".join(conditions) if conditions else ""
    scan_limit = 5000 if search_text else safe_limit
    conn = connect()
    try:
        all_rows = [dict(row) for row in conn.execute("""
            SELECT * FROM a3_followup_quality_alerts
        """).fetchall()]
        rows = [dict(row) for row in conn.execute(f"""
            SELECT * FROM a3_followup_quality_alerts
            {where_sql}
            ORDER BY
                CASE status WHEN 'active' THEN 0 WHEN 'acknowledged' THEN 1 ELSE 2 END,
                CASE severity WHEN 'critical' THEN 0 ELSE 1 END,
                updated_at DESC,
                id DESC
            LIMIT ?
        """, (*params, scan_limit)).fetchall()]
    finally:
        conn.close()
    now_value = now or datetime.now()
    sla_policy = get_a3_followup_quality_sla_policy()
    enrich_a3_followup_quality_alert_sla(all_rows, now_value, sla_policy)
    enrich_a3_followup_quality_alert_sla(rows, now_value, sla_policy)
    if search_text:
        needle = search_text.casefold()
        rows = [
            item for item in rows
            if needle in " ".join((
                str(item.get("id") or ""),
                str(item.get("title") or ""),
                str(item.get("message") or ""),
                str(item.get("owner_username") or ""),
            )).casefold()
        ][:safe_limit]
    for item in rows:
        item.update({
            "status_label": A3_QUALITY_ALERT_STATUS_LABELS.get(
                item["status"], "Неизвестно",
            ),
            "status_tone": (
                "success" if item["status"] == "resolved"
                else "warning" if item["status"] == "acknowledged"
                else "danger" if item["severity"] == "critical" else "warning"
            ),
            "severity_label": (
                "Критический" if item["severity"] == "critical" else "Внимание"
            ),
            "type_label": (
                "Повторный возврат"
                if item["alert_type"] == "repeat_return" else "Низкое качество"
            ),
            "owner_label": item.get("owner_username") or "Не назначен",
            "first_detected_label": _time_label(item.get("first_detected_at")),
            "last_detected_label": _time_label(item.get("last_detected_at")),
            "last_notified_label": _time_label(item.get("last_notified_at")),
            "acknowledged_label": _time_label(item.get("acknowledged_at")),
            "resolved_label": _time_label(item.get("resolved_at")),
            "age_hours": _elapsed_hours(
                now_value, item.get("first_detected_at"),
            ),
        })
    counts = {
        "total": len(all_rows),
        "active": sum(row["status"] in {"active", "acknowledged"} for row in all_rows),
        "acknowledged": sum(row["status"] == "acknowledged" for row in all_rows),
        "resolved": sum(row["status"] == "resolved" for row in all_rows),
        "critical": sum(
            row["status"] in {"active", "acknowledged"}
            and row["severity"] == "critical"
            for row in all_rows
        ),
    }
    sla_summary = {
        "response_overdue": sum(
            item["is_response_overdue"] for item in all_rows
        ),
        "resolution_overdue": sum(
            item["is_resolution_overdue"] for item in all_rows
        ),
        "escalated": sum(
            item["is_escalated"]
            and item["status"] in {"active", "acknowledged"}
            for item in all_rows
        ),
        "ready": sum(item["sla_ready"] for item in all_rows),
    }
    status_options = []
    for key, label in A3_QUALITY_ALERT_FILTER_LABELS.items():
        count_key = "total" if key == "all" else key
        status_options.append({
            "key": key,
            "label": label,
            "count": counts[count_key],
            "url": build_a3_followup_quality_alerts_url(key, search_text),
        })
    export_query = urlencode({
        "status": selected_status,
        **({"search": search_text} if search_text else {}),
    })
    return {
        "generated_at": now_value.strftime("%d.%m.%Y %H:%M"),
        "status_filter": selected_status,
        "search": search_text,
        "summary": counts,
        "sla_summary": sla_summary,
        "sla_policy": sla_policy,
        "items": rows,
        "visible": len(rows),
        "status_options": status_options,
        "base_url": "/platform/a3-health/incidents/actions/quality-alerts",
        "export_url": (
            "/platform/a3-health/incidents/actions/quality-alerts/export?"
            + export_query
        ),
    }


def a3_followup_quality_alert_csv_rows(center):
    rows = [[
        "ID", "Тип", "Важность", "Состояние", "Заголовок", "Описание",
        "Компания", "Инцидент", "Ответственный", "Значение",
        "Обнаружен", "Последнее обнаружение", "Уведомлений",
        "Принял в работу", "Дата принятия", "Комментарий",
        "Закрыл", "Дата закрытия", "Результат закрытия", "Вид закрытия",
        "Срок реакции", "Состояние реакции", "Срок устранения",
        "Состояние устранения", "Эскалации", "Последняя эскалация",
    ]]
    for item in center["items"]:
        rows.append([
            item["id"], item["type_label"], item["severity_label"],
            item["status_label"], item["title"], item["message"],
            item["company_id"], item["incident_id"] or "",
            item["owner_label"], item["metric_value"],
            item["first_detected_at"], item["last_detected_at"],
            item["notification_count"], item["acknowledged_by"] or "",
            item["acknowledged_at"] or "", item["acknowledged_note"] or "",
            item["resolved_by"] or "", item["resolved_at"] or "",
            item["resolution_note"] or "", item["resolution_kind"] or "",
            item["response_due_at_calculated"], item["response_status_label"],
            item["resolution_due_at_calculated"],
            item["resolution_status_label"], item["escalation_count"],
            item["last_escalated_at"] or "",
        ])
    return [[
        "'" + value
        if isinstance(value, str)
        and value.lstrip().startswith(("=", "+", "-", "@"))
        else value
        for value in row
    ] for row in rows]


def _change_quality_alert(alert_id, actor_username, action, note="", now=None):
    action_name = str(action or "").strip().lower()
    if action_name not in {"acknowledge", "resolve", "reopen"}:
        return {"ok": False, "error": "invalid_action"}
    note_text = str(note or "").strip()[:1000]
    if action_name == "resolve" and not note_text:
        return {
            "ok": False,
            "error": "empty_resolution_note",
            "message": "Укажите, как устранена причина сигнала.",
        }
    now_text = (now or datetime.now()).strftime("%Y-%m-%d %H:%M:%S")
    conn = connect()
    try:
        cursor = conn.cursor()
        begin_locked_transaction(cursor, "a3_platform_operations")
        admin = cursor.execute("""
            SELECT 1 FROM users
            WHERE username=? AND role='superadmin' AND COALESCE(is_active, 1)=1
        """, (actor_username,)).fetchone()
        if not admin:
            conn.rollback()
            return {"ok": False, "error": "forbidden"}
        row = cursor.execute("""
            SELECT * FROM a3_followup_quality_alerts WHERE id=?
        """, (alert_id,)).fetchone()
        if not row:
            conn.rollback()
            return {"ok": False, "error": "alert_not_found"}
        alert = dict(row)
        persist_a3_followup_quality_alert_deadlines(cursor, [alert])
        if action_name == "acknowledge":
            if alert["status"] != "active":
                conn.rollback()
                return {"ok": False, "error": "invalid_alert_status"}
            cursor.execute("""
                UPDATE a3_followup_quality_alerts
                SET status='acknowledged', acknowledged_at=?, acknowledged_by=?,
                    acknowledged_note=?, updated_at=? WHERE id=?
            """, (now_text, actor_username, note_text, now_text, alert_id))
            notice = "quality_alert_acknowledged"
        elif action_name == "resolve":
            if alert["status"] not in {"active", "acknowledged"}:
                conn.rollback()
                return {"ok": False, "error": "invalid_alert_status"}
            cursor.execute("""
                UPDATE a3_followup_quality_alerts
                SET status='resolved', resolved_at=?, resolved_by=?,
                    resolution_note=?, resolution_kind='manual', updated_at=?
                WHERE id=?
            """, (now_text, actor_username, note_text, now_text, alert_id))
            notice = "quality_alert_resolved"
        else:
            if alert["status"] != "resolved":
                conn.rollback()
                return {"ok": False, "error": "invalid_alert_status"}
            cursor.execute("""
                UPDATE a3_followup_quality_alerts
                SET status='active', acknowledged_at=NULL, acknowledged_by=NULL,
                    acknowledged_note=NULL, resolved_at=NULL, resolved_by=NULL,
                    resolution_note=NULL, resolution_kind=NULL,
                    last_notified_at=NULL, updated_at=? WHERE id=?
            """, (now_text, alert_id))
            notice = "quality_alert_reopened"
        if alert.get("incident_id"):
            event_type = {
                "acknowledge": "followup_quality_acknowledged",
                "resolve": "followup_quality_resolved",
                "reopen": "followup_quality_reopened",
            }[action_name]
            event_message = {
                "acknowledge": "Сигнал качества принят в работу.",
                "resolve": "Сигнал качества закрыт.",
                "reopen": "Сигнал качества открыт повторно.",
            }[action_name]
            if note_text:
                event_message += f" Комментарий: {note_text}"
            cursor.execute("""
                INSERT INTO a3_platform_incident_events (
                    incident_id, company_id, event_type,
                    actor_username, message, created_at
                ) VALUES (?, ?, ?, ?, ?, ?)
            """, (
                alert["incident_id"], alert["company_id"], event_type,
                actor_username, event_message[:500], now_text,
            ))
        conn.commit()
        return {
            "ok": True,
            "alert_id": alert_id,
            "action": action_name,
            "notice": notice,
        }
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def acknowledge_a3_followup_quality_alert(
    alert_id, actor_username, note="", now=None,
):
    return _change_quality_alert(
        alert_id, actor_username, "acknowledge", note, now,
    )


def resolve_a3_followup_quality_alert(
    alert_id, actor_username, note="", now=None,
):
    return _change_quality_alert(alert_id, actor_username, "resolve", note, now)


def reopen_a3_followup_quality_alert(alert_id, actor_username, now=None):
    return _change_quality_alert(alert_id, actor_username, "reopen", now=now)
