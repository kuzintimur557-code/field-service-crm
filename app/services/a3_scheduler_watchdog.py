from datetime import datetime, timedelta

from app.database import connect
from app.services.a3_cycle_history import get_a3_cycle_reliability
from app.services.governance import get_governance_settings


A3_WATCHDOG_NEW_COMPANY_GRACE_HOURS = 24
A3_WATCHDOG_WARNING_HOURS = 24
A3_WATCHDOG_CRITICAL_HOURS = 48
A3_WATCHDOG_HISTORY_LIMIT = 50
A3_WATCHDOG_HISTORY_KEEP = 500
A3_WATCHDOG_HISTORY_RETENTION_DAYS = 180

A3_WATCHDOG_RUN_STATUS_LABELS = {
    "stable": "Стабильно",
    "warning": "Нужно внимание",
    "critical": "Критично",
    "paused": "Приостановлено",
}

A3_WATCHDOG_RUN_STATUS_TONES = {
    "stable": "success",
    "warning": "warning",
    "critical": "danger",
    "paused": "muted",
}


def _parse_datetime(value):
    try:
        return datetime.fromisoformat(str(value or "").replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None


def _comparable_now(value, now_value):
    if value.tzinfo:
        if now_value.tzinfo:
            return now_value.astimezone(value.tzinfo)
        return now_value.replace(tzinfo=value.tzinfo)

    if now_value.tzinfo:
        return now_value.replace(tzinfo=None)

    return now_value


def _company_is_in_grace_period(created_at, now_value):
    created_value = _parse_datetime(created_at)

    if not created_value:
        return False

    comparable_now = _comparable_now(created_value, now_value)
    return comparable_now - created_value < timedelta(
        hours=A3_WATCHDOG_NEW_COMPANY_GRACE_HOURS
    )


def _age_minutes(value, now_value):
    checked_at = _parse_datetime(value)

    if not checked_at:
        return None

    comparable_now = _comparable_now(checked_at, now_value)
    return max(0, int((comparable_now - checked_at).total_seconds() // 60))


def _age_label(age_minutes):
    if age_minutes is None:
        return "Время неизвестно"
    if age_minutes < 1:
        return "Только что"
    if age_minutes < 60:
        return f"{age_minutes} мин. назад"

    age_hours = age_minutes // 60
    if age_hours < 24:
        return f"{age_hours} ч. назад"

    return f"{age_hours // 24} дн. назад"


def _load_watchdog_companies():
    conn = connect()
    try:
        rows = conn.cursor().execute("""
            SELECT
                companies.id,
                companies.name,
                companies.owner_username,
                companies.created_at,
                company_features.enabled AS automation_enabled
            FROM companies
            LEFT JOIN company_features
              ON company_features.company_id=companies.id
             AND company_features.feature_key='automation'
            ORDER BY companies.id
        """).fetchall()
    finally:
        conn.close()

    return [dict(row) for row in rows]


def get_a3_scheduler_watchdog_report(now=None):
    now_value = now or datetime.now()
    report = {
        "companies_total": 0,
        "eligible_companies": 0,
        "skipped_companies": 0,
        "stable": 0,
        "warning": 0,
        "critical": 0,
        "waiting": 0,
        "errors": 0,
        "grace_hours": A3_WATCHDOG_NEW_COMPANY_GRACE_HOURS,
        "items": [],
        "generated_at": now_value.isoformat(timespec="seconds"),
    }

    for company in _load_watchdog_companies():
        report["companies_total"] += 1
        company_id = company["id"]
        item = {
            "company_id": company_id,
            "company_name": company.get("name") or f"Компания #{company_id}",
            "owner_username": company.get("owner_username") or "",
        }

        try:
            automation_enabled = company.get("automation_enabled")
            if automation_enabled is not None and not bool(automation_enabled):
                report["skipped_companies"] += 1
                item.update({
                    "status": "skipped",
                    "status_label": "Пропущено",
                    "reason": "feature_disabled",
                    "message": "Модуль автоматизации выключен для компании.",
                    "alertable": False,
                })
                report["items"].append(item)
                continue

            governance = get_governance_settings(company_id)
            if not bool(governance.get("autonomous_enabled", 1)):
                report["skipped_companies"] += 1
                item.update({
                    "status": "skipped",
                    "status_label": "Пропущено",
                    "reason": "autonomous_disabled",
                    "message": "Автономный режим A3 выключен владельцем.",
                    "alertable": False,
                })
                report["items"].append(item)
                continue

            reliability = get_a3_cycle_reliability(company_id, now=now_value)
            status = reliability.get("status") or "unknown"
            report["eligible_companies"] += 1

            if status == "unknown" and _company_is_in_grace_period(
                company.get("created_at"),
                now_value,
            ):
                report["waiting"] += 1
                item.update({
                    "status": "waiting",
                    "status_label": "Ожидается первый запуск",
                    "reason": "startup_grace_period",
                    "message": (
                        "Компания создана недавно; контроль ожидает первый "
                        "фоновый запуск A3."
                    ),
                    "alertable": False,
                    "reliability": reliability,
                })
            else:
                if status == "unknown":
                    status = "warning"
                    reliability = {
                        **reliability,
                        "status": "warning",
                        "status_label": "Нет фоновых запусков",
                        "status_tone": "warning",
                        "message": (
                            "Фоновые запуски A3 не зафиксированы после "
                            "периода настройки."
                        ),
                        "recommendation": (
                            "Проверьте внешнее расписание и секрет фонового запуска."
                        ),
                    }

                if status not in {"stable", "warning", "critical"}:
                    status = "warning"

                report[status] += 1
                item.update({
                    "status": status,
                    "status_label": reliability.get("status_label") or status,
                    "reason": "reliability_checked",
                    "message": reliability.get("message") or "",
                    "alertable": True,
                    "reliability": reliability,
                })
        except Exception:
            report["errors"] += 1
            item.update({
                "status": "error",
                "status_label": "Ошибка проверки",
                "reason": "watchdog_error",
                "message": "Не удалось проверить планировщик A3 компании.",
                "alertable": False,
            })

        report["items"].append(item)

    return report


def save_a3_scheduler_watchdog_status(report, checked_at=None):
    checked_value = checked_at or datetime.now()
    checked_text = checked_value.isoformat(timespec="seconds")
    items = list((report or {}).get("items") or [])
    conn = connect()
    saved = 0

    try:
        c = conn.cursor()
        for item in items:
            company_id = item.get("company_id")
            if not company_id:
                continue

            reliability = item.get("reliability") or {}
            notification = item.get("notification") or {}
            c.execute("""
                INSERT INTO a3_scheduler_watchdog_status (
                    company_id,
                    status,
                    status_label,
                    reason,
                    message,
                    latest_scheduler_run_at,
                    notification_created,
                    telegram_sent,
                    checked_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(company_id) DO UPDATE SET
                    status=excluded.status,
                    status_label=excluded.status_label,
                    reason=excluded.reason,
                    message=excluded.message,
                    latest_scheduler_run_at=excluded.latest_scheduler_run_at,
                    notification_created=excluded.notification_created,
                    telegram_sent=excluded.telegram_sent,
                    checked_at=excluded.checked_at
            """, (
                company_id,
                str(item.get("status") or "error")[:40],
                str(item.get("status_label") or "Ошибка проверки")[:120],
                str(item.get("reason") or "")[:120],
                str(item.get("message") or "")[:1000],
                reliability.get("latest_scheduler_run_at"),
                1 if notification.get("created") else 0,
                1 if notification.get("telegram_sent") else 0,
                checked_text,
            ))
            saved += 1

        conn.commit()
    finally:
        conn.close()

    return saved


def _watchdog_run_score(report):
    stable = max(0, int((report or {}).get("stable") or 0))
    warning = max(0, int((report or {}).get("warning") or 0))
    critical = max(0, int((report or {}).get("critical") or 0))
    waiting = max(0, int((report or {}).get("waiting") or 0))
    errors = max(0, int((report or {}).get("errors") or 0))
    checked = stable + warning + critical + waiting + errors

    if not checked:
        return 100

    points = stable * 100 + (warning + waiting) * 50
    return max(0, min(100, round(points / checked)))


def _watchdog_run_status(report):
    companies_total = int((report or {}).get("companies_total") or 0)
    skipped_companies = int((report or {}).get("skipped_companies") or 0)

    if (
        int((report or {}).get("critical") or 0)
        or int((report or {}).get("errors") or 0)
        or int((report or {}).get("notification_errors") or 0)
        or (report or {}).get("heartbeat_error")
    ):
        return "critical"
    if (
        int((report or {}).get("warning") or 0)
        or int((report or {}).get("waiting") or 0)
    ):
        return "warning"
    if companies_total and skipped_companies >= companies_total:
        return "paused"
    return "stable"


def record_a3_scheduler_watchdog_run(report, checked_at=None):
    report = report or {}
    recorded_at = checked_at or datetime.now()
    status = _watchdog_run_status(report)
    score = _watchdog_run_score(report)
    conn = connect()

    try:
        c = conn.cursor()
        c.execute("""
            INSERT INTO a3_scheduler_watchdog_runs (
                status,
                score,
                companies_total,
                eligible_companies,
                skipped_companies,
                stable_count,
                warning_count,
                critical_count,
                waiting_count,
                error_count,
                alerts_sent,
                recoveries_sent,
                telegram_sent,
                suppressed_count,
                notification_errors,
                heartbeats_saved,
                created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            status,
            score,
            max(0, int(report.get("companies_total") or 0)),
            max(0, int(report.get("eligible_companies") or 0)),
            max(0, int(report.get("skipped_companies") or 0)),
            max(0, int(report.get("stable") or 0)),
            max(0, int(report.get("warning") or 0)),
            max(0, int(report.get("critical") or 0)),
            max(0, int(report.get("waiting") or 0)),
            max(0, int(report.get("errors") or 0)),
            max(0, int(report.get("alerts_sent") or 0)),
            max(0, int(report.get("recoveries_sent") or 0)),
            max(0, int(report.get("telegram_sent") or 0)),
            max(0, int(report.get("suppressed") or 0)),
            max(0, int(report.get("notification_errors") or 0)),
            max(0, int(report.get("heartbeats_saved") or 0)),
            recorded_at.isoformat(timespec="seconds"),
        ))
        run_id = c.lastrowid
        cutoff = (
            recorded_at - timedelta(days=A3_WATCHDOG_HISTORY_RETENTION_DAYS)
        ).isoformat(timespec="seconds")
        c.execute(
            "DELETE FROM a3_scheduler_watchdog_runs WHERE created_at < ?",
            (cutoff,),
        )
        c.execute("""
            DELETE FROM a3_scheduler_watchdog_runs
            WHERE id NOT IN (
                SELECT id
                FROM a3_scheduler_watchdog_runs
                ORDER BY id DESC
                LIMIT ?
            )
        """, (A3_WATCHDOG_HISTORY_KEEP,))
        conn.commit()
        return run_id
    finally:
        conn.close()


def get_a3_scheduler_watchdog_history(limit=12):
    try:
        normalized_limit = max(
            1,
            min(A3_WATCHDOG_HISTORY_LIMIT, int(limit or 12)),
        )
    except (TypeError, ValueError):
        normalized_limit = 12

    conn = connect()
    try:
        rows = conn.cursor().execute("""
            SELECT *
            FROM a3_scheduler_watchdog_runs
            ORDER BY id DESC
            LIMIT ?
        """, (normalized_limit,)).fetchall()
    finally:
        conn.close()

    history = []
    for row in rows:
        item = dict(row)
        status = item.get("status") or "warning"
        created_at = _parse_datetime(item.get("created_at"))
        item["status_label"] = A3_WATCHDOG_RUN_STATUS_LABELS.get(
            status,
            "Нужно проверить",
        )
        item["status_tone"] = A3_WATCHDOG_RUN_STATUS_TONES.get(
            status,
            "warning",
        )
        item["problems_count"] = sum(
            int(item.get(key) or 0)
            for key in (
                "warning_count",
                "critical_count",
                "waiting_count",
                "error_count",
            )
        )
        item["notifications_count"] = (
            int(item.get("alerts_sent") or 0)
            + int(item.get("recoveries_sent") or 0)
        )
        item["created_label"] = (
            created_at.strftime("%d.%m.%Y %H:%M")
            if created_at
            else "Время неизвестно"
        )
        history.append(item)

    return history


def get_a3_scheduler_watchdog_trend(history=None, limit=12):
    recent = list(
        history
        if history is not None
        else get_a3_scheduler_watchdog_history(limit=limit)
    )
    latest = recent[0] if recent else None
    previous = recent[1] if len(recent) > 1 else None

    return {
        "has_history": bool(recent),
        "runs_count": len(recent),
        "latest_score": int((latest or {}).get("score") or 0),
        "latest_status": (latest or {}).get("status") or "waiting",
        "latest_status_label": (
            (latest or {}).get("status_label") or "Истории пока нет"
        ),
        "score_delta": (
            int(latest.get("score") or 0) - int(previous.get("score") or 0)
            if latest and previous
            else 0
        ),
        "critical_delta": (
            int(latest.get("critical_count") or 0)
            - int(previous.get("critical_count") or 0)
            if latest and previous
            else 0
        ),
        "items": list(reversed(recent)),
    }


def get_a3_scheduler_watchdog_status(company_id, now=None):
    if not company_id:
        raise ValueError("company_id is required")

    now_value = now or datetime.now()
    conn = connect()
    try:
        row = conn.cursor().execute("""
            SELECT *
            FROM a3_scheduler_watchdog_status
            WHERE company_id=?
        """, (company_id,)).fetchone()
    finally:
        conn.close()

    if not row:
        return {
            "company_id": company_id,
            "status": "unknown",
            "result_status": "unknown",
            "status_label": "Контроль ещё не запускался",
            "status_tone": "warning",
            "reason": "not_checked",
            "message": "Нет сохранённых контрольных проверок планировщика A3.",
            "recommendation": "Настройте отдельное расписание для контроля A3.",
            "checked_at": None,
            "checked_age_minutes": None,
            "checked_age_label": "Проверок пока нет",
            "latest_scheduler_run_at": None,
            "latest_scheduler_age_minutes": None,
            "latest_scheduler_age_label": "Основных запусков пока нет",
            "notification_created": False,
            "telegram_sent": False,
        }

    item = dict(row)
    age_minutes = _age_minutes(item.get("checked_at"), now_value)
    scheduler_age_minutes = _age_minutes(
        item.get("latest_scheduler_run_at"),
        now_value,
    )
    result_status = item.get("status") or "error"
    status = result_status
    status_label = item.get("status_label") or "Проверено"
    status_tone = {
        "stable": "success",
        "warning": "warning",
        "critical": "danger",
        "error": "danger",
        "waiting": "warning",
        "skipped": "muted",
    }.get(result_status, "warning")
    message = item.get("message") or "Контрольная проверка завершена."
    recommendation = "Следите за регулярностью контрольных проверок."

    if age_minutes is not None and age_minutes >= A3_WATCHDOG_CRITICAL_HOURS * 60:
        status = "critical"
        status_label = "Контроль остановлен"
        status_tone = "danger"
        message = "Контроль A3 не запускался больше 48 часов."
        recommendation = "Проверьте отдельное расписание контроля A3."
    elif age_minutes is not None and age_minutes >= A3_WATCHDOG_WARNING_HOURS * 60:
        status = "warning"
        status_label = "Контроль давно не запускался"
        status_tone = "warning"
        message = "Контроль A3 не запускался больше 24 часов."
        recommendation = "Убедитесь, что контрольное расписание работает."
    elif result_status == "critical":
        recommendation = "Проверьте основное расписание и журнал запусков A3."
    elif result_status in {"warning", "error"}:
        recommendation = "Проверьте причину предупреждения в журнале A3."
    elif result_status == "waiting":
        recommendation = "Дождитесь первого фонового запуска A3."
    elif result_status == "skipped":
        recommendation = "Контроль возобновится после включения автономного режима."

    return {
        **item,
        "status": status,
        "result_status": result_status,
        "status_label": status_label,
        "status_tone": status_tone,
        "message": message,
        "recommendation": recommendation,
        "checked_age_minutes": age_minutes,
        "checked_age_label": _age_label(age_minutes),
        "latest_scheduler_age_minutes": scheduler_age_minutes,
        "latest_scheduler_age_label": (
            _age_label(scheduler_age_minutes)
            if item.get("latest_scheduler_run_at")
            else "Основных запусков пока нет"
        ),
        "notification_created": bool(item.get("notification_created")),
        "telegram_sent": bool(item.get("telegram_sent")),
    }
