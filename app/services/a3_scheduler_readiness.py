from datetime import datetime

from app.database import connect
from app.services.a3_cycle_history import get_a3_cycle_reliability


READINESS_STATUS_LABELS = {
    "ok": "Готово",
    "warning": "Нужна настройка",
    "critical": "Критично",
}

READINESS_STATUS_TONES = {
    "ok": "success",
    "warning": "warning",
    "critical": "danger",
}


def require_company_id(company_id):
    if not company_id:
        raise ValueError("company_id is required")


def _readiness_check(
    key,
    label,
    status,
    message,
    recommendation,
    weight,
    required=True,
):
    return {
        "key": key,
        "label": label,
        "status": status,
        "status_label": READINESS_STATUS_LABELS.get(status, status),
        "status_tone": READINESS_STATUS_TONES.get(status, "warning"),
        "message": message,
        "recommendation": recommendation,
        "weight": weight,
        "required": required,
    }


def _company_delivery_state(company_id):
    conn = connect()
    try:
        row = conn.cursor().execute("""
            SELECT
                companies.owner_username,
                users.telegram_chat_id
            FROM companies
            LEFT JOIN users
              ON users.company_id=companies.id
             AND users.username=companies.owner_username
            WHERE companies.id=?
        """, (company_id,)).fetchone()
    finally:
        conn.close()

    return {
        "owner_username": str(
            row["owner_username"] if row else ""
        ).strip(),
        "telegram_configured": bool(
            str(row["telegram_chat_id"] if row else "").strip()
        ),
    }


def get_a3_scheduler_readiness(
    company_id,
    cron_configured,
    automation_enabled,
    autonomous_enabled,
):
    require_company_id(company_id)
    delivery = _company_delivery_state(company_id)
    reliability = get_a3_cycle_reliability(company_id)
    scheduler_seen = bool(reliability.get("latest_scheduler_run_at"))
    reliability_status = reliability.get("status") or "unknown"

    if reliability_status == "stable":
        runtime_status = "ok"
        runtime_message = "Последние фоновые циклы выполняются стабильно."
    elif reliability_status == "critical":
        runtime_status = "critical"
        runtime_message = reliability.get("message") or "Планировщик нестабилен."
    else:
        runtime_status = "warning"
        runtime_message = reliability.get("message") or "Нужно проверить планировщик."

    checks = [
        _readiness_check(
            "automation_module",
            "Модуль автоматизации",
            "ok" if automation_enabled else "critical",
            (
                "Модуль автоматизации включён."
                if automation_enabled
                else "Модуль автоматизации выключен для компании."
            ),
            "Включите модуль автоматизации в настройках компании.",
            20,
        ),
        _readiness_check(
            "autonomous_mode",
            "Автономный режим",
            "ok" if autonomous_enabled else "warning",
            (
                "Автономное выполнение разрешено."
                if autonomous_enabled
                else "Автономное выполнение выключено владельцем."
            ),
            "Включите автономный режим в настройках управления A3.",
            20,
        ),
        _readiness_check(
            "cron_secret",
            "Секрет фонового запуска",
            "ok" if cron_configured else "critical",
            (
                "AUTOMATION_CRON_SECRET настроен."
                if cron_configured
                else "AUTOMATION_CRON_SECRET не настроен."
            ),
            "Добавьте AUTOMATION_CRON_SECRET в переменные окружения.",
            25,
        ),
        _readiness_check(
            "scheduler_runtime",
            "Работа планировщика",
            runtime_status if scheduler_seen else "warning",
            (
                runtime_message
                if scheduler_seen
                else "Фоновые запуски A3 ещё не зафиксированы."
            ),
            (
                reliability.get("recommendation")
                or "Настройте регулярный POST-запрос фонового запуска A3."
            ),
            25,
        ),
        _readiness_check(
            "owner_telegram",
            "Telegram владельца",
            "ok" if delivery["telegram_configured"] else "warning",
            (
                "Telegram владельца готов принимать оповещения."
                if delivery["telegram_configured"]
                else "У владельца не указан telegram_chat_id."
            ),
            "Добавьте telegram_chat_id владельцу компании.",
            10,
            required=False,
        ),
    ]

    status_scores = {
        "ok": 1,
        "warning": 0.5,
        "critical": 0,
    }
    score = round(sum(
        item["weight"] * status_scores.get(item["status"], 0)
        for item in checks
    ))
    required_ready = all(
        item["status"] == "ok"
        for item in checks
        if item["required"]
    )

    if any(item["status"] == "critical" for item in checks):
        status = "critical"
    elif required_ready:
        status = "ok"
    else:
        status = "warning"

    next_actions = [
        item["recommendation"]
        for item in checks
        if item["status"] != "ok"
    ]

    return {
        "ready": required_ready,
        "score": score,
        "status": status,
        "status_label": READINESS_STATUS_LABELS[status],
        "status_tone": READINESS_STATUS_TONES[status],
        "cron_configured": bool(cron_configured),
        "automation_enabled": bool(automation_enabled),
        "autonomous_enabled": bool(autonomous_enabled),
        "telegram_configured": delivery["telegram_configured"],
        "owner_username": delivery["owner_username"],
        "cron_method": "POST",
        "cron_path": "/automation/cron/a3-autonomous",
        "cron_header": "x-automation-secret",
        "watchdog_method": "POST",
        "watchdog_path": "/automation/cron/a3-watchdog",
        "checks": checks,
        "next_actions": next_actions,
        "reliability": reliability,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
    }
