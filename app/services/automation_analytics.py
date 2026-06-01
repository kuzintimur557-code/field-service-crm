from app.database import connect


def get_automation_analytics(company_id):
    conn = connect()
    c = conn.cursor()

    rows = c.execute("""
        SELECT status, COUNT(*) AS count
        FROM automation_events
        WHERE company_id=?
        GROUP BY status
    """, (company_id,)).fetchall()

    counts = {row["status"]: row["count"] for row in rows}

    done_total = counts.get("done", 0)
    skipped_total = counts.get("skipped", 0)
    failed_total = counts.get("failed", 0)
    pending_total = counts.get("pending", 0)

    events_total = done_total + skipped_total + failed_total + pending_total
    success_rate = round((done_total / events_total) * 100) if events_total else 100

    daily_rows = c.execute("""
        SELECT
            substr(created_at, 1, 10) AS day,
            status,
            COUNT(*) AS count
        FROM automation_events
        WHERE company_id=?
        GROUP BY day, status
        ORDER BY day ASC
        LIMIT 60
    """, (company_id,)).fetchall()

    daily_map = {}

    for row in daily_rows:
        day = row["day"] or "unknown"

        if day not in daily_map:
            daily_map[day] = {
                "day": day,
                "done": 0,
                "skipped": 0,
                "failed": 0,
                "pending": 0,
                "total": 0,
            }

        status = row["status"] or "pending"
        count = row["count"] or 0

        if status in daily_map[day]:
            daily_map[day][status] = count

        daily_map[day]["total"] += count

    conn.close()

    return {
        "events_total": events_total,
        "done_total": done_total,
        "skipped_total": skipped_total,
        "failed_total": failed_total,
        "pending_total": pending_total,
        "success_rate": success_rate,
        "daily": list(daily_map.values()),
    }


def get_unhealthy_rules(company_id):
    conn = connect()
    c = conn.cursor()

    rows = c.execute("""
        SELECT
            automation_rules.*,
            COUNT(automation_actions.id) AS action_count
        FROM automation_rules
        LEFT JOIN automation_actions
          ON automation_actions.rule_id=automation_rules.id
          AND automation_actions.company_id=automation_rules.company_id
        WHERE automation_rules.company_id=?
        GROUP BY automation_rules.id
        ORDER BY automation_rules.id DESC
    """, (company_id,)).fetchall()

    conn.close()

    items = []

    for row in rows:
        rule = dict(row)

        issues = []

        if not rule.get("active", 1):
            issues.append("Правило отключено")

        if not rule.get("action_count"):
            issues.append("Действия не настроены")

        if (rule.get("success_rate") or 100) < 60:
            issues.append("Низкая успешность")

        if (rule.get("skipped_runs") or 0) >= 5:
            issues.append("Много пропущенных запусков")

        if issues:
            items.append({
                "id": rule.get("id"),
                "name": rule.get("name"),
                "issues": issues,
            })

    return items[:20]
