from app.database import connect


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
    }
