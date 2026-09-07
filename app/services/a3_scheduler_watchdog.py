from datetime import datetime, timedelta

from app.database import connect
from app.services.a3_cycle_history import get_a3_cycle_reliability
from app.services.governance import get_governance_settings


A3_WATCHDOG_NEW_COMPANY_GRACE_HOURS = 24


def _parse_datetime(value):
    try:
        return datetime.fromisoformat(str(value or "").replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None


def _company_is_in_grace_period(created_at, now_value):
    created_value = _parse_datetime(created_at)

    if not created_value:
        return False

    comparable_now = (
        datetime.now(created_value.tzinfo)
        if created_value.tzinfo
        else now_value
    )
    return comparable_now - created_value < timedelta(
        hours=A3_WATCHDOG_NEW_COMPANY_GRACE_HOURS
    )


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
                        "Компания создана недавно; watchdog ожидает первый "
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
                            "Проверьте внешний cron и секрет фонового запуска."
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
