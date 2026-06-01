from app.database import connect
from app.services.autonomous_actions import enqueue_autonomous_action


def get_decision_engine(company_id):
    conn = connect()
    c = conn.cursor()

    rows = c.execute("""
        SELECT
            automation_rules.id,
            automation_rules.name,
            automation_rules.active,
            COUNT(automation_events.id) AS total_events,
            SUM(CASE WHEN automation_events.status='failed' THEN 1 ELSE 0 END) AS failed_events,
            SUM(CASE WHEN automation_events.status='skipped' THEN 1 ELSE 0 END) AS skipped_events
        FROM automation_rules
        LEFT JOIN automation_events
          ON automation_events.rule_id=automation_rules.id
          AND automation_events.company_id=automation_rules.company_id
        WHERE automation_rules.company_id=?
        GROUP BY automation_rules.id
        ORDER BY automation_rules.id DESC
    """, (company_id,)).fetchall()

    conn.close()

    decisions = []

    for row in rows:
        total = row["total_events"] or 0
        failed = row["failed_events"] or 0
        skipped = row["skipped_events"] or 0

        confidence = 100
        confidence -= min(40, failed * 5)
        confidence -= min(30, skipped * 3)
        confidence = max(5, confidence)

        recommendation = "stable"

        if skipped >= 5:
            recommendation = "retry_recommended"

        if failed >= 5:
            recommendation = "investigate_rule"

        if failed >= 10:
            recommendation = "disable_rule"

            enqueue_autonomous_action(
                company_id=company_id,
                action_type="disable_rule",
                target_type="automation_rule",
                target_id=row["id"],
            )

        elif skipped >= 5:
            enqueue_autonomous_action(
                company_id=company_id,
                action_type="retry_events",
                target_type="automation_rule",
                target_id=row["id"],
            )

        decisions.append({
            "rule_id": row["id"],
            "rule_name": row["name"],
            "active": bool(row["active"]),
            "confidence_score": confidence,
            "recommendation": recommendation,
            "failed_events": failed,
            "skipped_events": skipped,
            "total_events": total,
        })

    return {
        "count": len(decisions),
        "items": decisions[:20],
    }
