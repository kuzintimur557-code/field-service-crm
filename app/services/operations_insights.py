from datetime import datetime, timedelta

from app.database import connect
from app.services.governance import (
    APPROVAL_ATTENTION_MINUTES,
    APPROVAL_OVERDUE_MINUTES,
)


def require_company_id(company_id):
    if not company_id:
        raise ValueError("company_id is required")


def get_operations_insights(company_id):
    require_company_id(company_id)

    conn = connect()
    c = conn.cursor()

    rows = c.execute("""
        SELECT status, COUNT(*) AS count
        FROM automation_events
        WHERE company_id=?
        GROUP BY status
    """, (company_id,)).fetchall()

    now = datetime.now()
    attention_cutoff = (
        now - timedelta(minutes=APPROVAL_ATTENTION_MINUTES)
    ).isoformat(timespec="seconds")
    overdue_cutoff = (
        now - timedelta(minutes=APPROVAL_OVERDUE_MINUTES)
    ).isoformat(timespec="seconds")

    approval_counts = c.execute("""
        SELECT
            COUNT(*) AS total,
            SUM(CASE WHEN created_at <= ? THEN 1 ELSE 0 END) AS attention,
            SUM(CASE WHEN created_at <= ? THEN 1 ELSE 0 END) AS overdue
        FROM autonomous_action_queue
        WHERE company_id=?
          AND status='awaiting_approval'
    """, (
        attention_cutoff,
        overdue_cutoff,
        company_id,
    )).fetchone()

    conn.close()

    counts = {row["status"]: row["count"] for row in rows}

    done_total = counts.get("done", 0)
    skipped_total = counts.get("skipped", 0)
    failed_total = counts.get("failed", 0)
    pending_total = counts.get("pending", 0)
    approval_total = approval_counts["total"] or 0
    approval_attention = approval_counts["attention"] or 0
    approval_overdue = approval_counts["overdue"] or 0

    total = done_total + skipped_total + failed_total + pending_total

    insights = []

    if total >= 100:
        insights.append({
            "level": "info",
            "title": "Высокая активность автоматизации",
            "message": "Движок автоматизации обрабатывает большой объём событий.",
        })

    if skipped_total >= 10:
        insights.append({
            "level": "warning",
            "title": "Рост пропущенных выполнений",
            "message": "За последнее время накопилось много пропущенных событий автоматизации.",
        })

    if failed_total >= 5:
        insights.append({
            "level": "critical",
            "title": "Обнаружена нестабильность выполнения",
            "message": "Несколько запусков автоматизации завершились ошибкой.",
        })

    if pending_total >= 15:
        insights.append({
            "level": "warning",
            "title": "Очередь автоматизации растёт",
            "message": "В очереди накопилось много ожидающих событий.",
        })

    if approval_overdue:
        insights.append({
            "level": "critical",
            "title": "Просрочены подтверждения ИИ",
            "message": (
                "Есть действия ИИ, которые ожидают решения владельца "
                "больше суток."
            ),
        })
    elif approval_attention:
        insights.append({
            "level": "warning",
            "title": "Задерживаются подтверждения ИИ",
            "message": (
                "Есть действия ИИ, которые ожидают решения владельца "
                "больше 6 часов."
            ),
        })

    success_rate = round((done_total / total) * 100) if total else 100

    if success_rate < 70:
        insights.append({
            "level": "critical",
            "title": "Низкая надёжность автоматизации",
            "message": "Успешность автоматизации ниже нормального уровня.",
        })

    if not insights:
        insights.append({
            "level": "healthy",
            "title": "Операции стабильны",
            "message": "Платформа автоматизации работает нормально.",
        })

    return {
        "count": len(insights),
        "items": insights,
        "awaiting_approval_count": approval_total,
        "approval_attention_count": approval_attention,
        "approval_overdue_count": approval_overdue,
    }
