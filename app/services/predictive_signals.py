from datetime import datetime, timedelta

from app.database import connect
from app.services.governance import APPROVAL_OVERDUE_MINUTES


def require_company_id(company_id):
    if not company_id:
        raise ValueError("company_id is required")


def get_predictive_signals(company_id):
    require_company_id(company_id)

    conn = connect()
    c = conn.cursor()

    rows = c.execute("""
        SELECT status, created_at
        FROM automation_events
        WHERE company_id=?
        ORDER BY id DESC
        LIMIT 200
    """, (company_id,)).fetchall()

    approval_overdue_cutoff = (
        datetime.now() - timedelta(minutes=APPROVAL_OVERDUE_MINUTES)
    ).isoformat(timespec="seconds")
    approval_overdue_count = c.execute("""
        SELECT COUNT(*) AS total
        FROM autonomous_action_queue
        WHERE company_id=?
          AND status='awaiting_approval'
          AND created_at <= ?
    """, (
        company_id,
        approval_overdue_cutoff,
    )).fetchone()["total"]

    conn.close()

    total = len(rows)

    skipped = 0
    failed = 0
    pending = 0
    done = 0

    for row in rows:
        status = row["status"] or "pending"

        if status == "skipped":
            skipped += 1
        elif status == "failed":
            failed += 1
        elif status == "done":
            done += 1
        else:
            pending += 1

    success_rate = round((done / total) * 100) if total else 100

    signals = []

    if skipped >= 20:
        signals.append({
            "severity": "warning",
            "title": "Растёт тренд пропусков",
            "prediction": "Количество пропущенных событий автоматизации может продолжить расти.",
        })

    if failed >= 10:
        signals.append({
            "severity": "critical",
            "title": "Обнаружен всплеск ошибок",
            "prediction": "Риск нестабильного выполнения растёт.",
        })

    if success_rate < 75:
        signals.append({
            "severity": "degraded",
            "title": "Успешность снижается",
            "prediction": "Надёжность платформы может продолжить снижаться.",
        })

    if pending >= 25:
        signals.append({
            "severity": "warning",
            "title": "Прогноз перегрузки автоматизации",
            "prediction": "Давление очереди ожидающих событий растёт.",
        })

    if skipped + failed >= 30:
        signals.append({
            "severity": "critical",
            "title": "Растёт нагрузка на восстановление",
            "prediction": "Потребность в самовосстановлении, вероятно, увеличится.",
        })

    if approval_overdue_count:
        signals.append({
            "severity": "critical",
            "title": "Подтверждения задерживают автоматизацию",
            "prediction": (
                "Неподтверждённые действия ИИ могут задержать "
                "восстановление и важные изменения правил."
            ),
        })

    if not signals:
        signals.append({
            "severity": "healthy",
            "title": "Операции стабильны",
            "prediction": "Прогнозных операционных рисков не обнаружено.",
        })

    return {
        "count": len(signals),
        "items": signals,
        "success_rate": success_rate,
        "total_events": total,
        "approval_overdue_count": approval_overdue_count,
    }
