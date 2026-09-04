import json

from app.database import connect
from app.services.autonomous_actions import enqueue_autonomous_action
from app.services.governance import get_governance_settings


def require_company_id(company_id):
    if not company_id:
        raise ValueError("company_id is required")


def get_decision_engine(company_id, queue_actions=False):
    require_company_id(company_id)

    governance = get_governance_settings(company_id)
    confidence_threshold = max(
        0,
        min(100, int(governance.get("confidence_threshold", 70))),
    )
    autonomous_enabled = bool(governance.get("autonomous_enabled", 1))
    max_actions_per_cycle = max(
        1,
        min(100, int(governance.get("max_actions_per_cycle", 20))),
    )

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

    pending_actions = {
        (row["action_type"], row["target_id"]): row["status"]
        for row in c.execute("""
            SELECT action_type, target_id, status
            FROM autonomous_action_queue
            WHERE company_id=?
              AND target_type='automation_rule'
              AND status IN ('pending', 'awaiting_approval', 'approved')
        """, (company_id,)).fetchall()
    }
    pending_action_count = len(pending_actions)
    queue_capacity_remaining = max(
        0,
        max_actions_per_cycle - pending_action_count,
    )

    conn.close()

    decisions = []
    queued_count = 0

    for row in rows:
        total = row["total_events"] or 0
        failed = row["failed_events"] or 0
        skipped = row["skipped_events"] or 0

        confidence = 100
        confidence -= min(40, failed * 5)
        confidence -= min(30, skipped * 3)
        confidence = max(5, confidence)

        recommendation = "stable"
        action_type = None
        request_reason = ""
        decision_confidence = 100

        if skipped >= 5:
            recommendation = "retry_recommended"
            action_type = "retry_events"
            decision_confidence = min(95, 45 + skipped * 5)
            request_reason = (
                f"Зафиксировано пропущенных событий: {skipped}; "
                f"всего событий: {total}"
            )

        if failed >= 5:
            recommendation = "investigate_rule"
            action_type = None
            decision_confidence = min(90, 45 + failed * 6)

        if failed >= 10:
            recommendation = "disable_rule"
            action_type = "disable_rule"
            decision_confidence = min(100, 50 + failed * 5)
            request_reason = (
                f"Зафиксировано ошибок: {failed}; "
                f"всего событий: {total}"
            )

        autonomous_status = "Действие не требуется"
        autonomous_ready = False
        autonomous_queued = False
        autonomous_pending = False

        if not row["active"]:
            recommendation = "inactive"
            action_type = None
            decision_confidence = None
            autonomous_status = "Правило уже выключено"
        elif action_type:
            pending_status = pending_actions.get((action_type, row["id"]))

            if pending_status:
                autonomous_pending = True
                pending_labels = {
                    "pending": "ожидает выполнения",
                    "awaiting_approval": "ожидает подтверждения",
                    "approved": "подтверждено и ожидает выполнения",
                }
                autonomous_status = (
                    "Похожее действие уже "
                    f"{pending_labels.get(pending_status, 'находится в очереди')}"
                )
            elif not autonomous_enabled:
                autonomous_status = "Автономный режим выключен"
            elif decision_confidence < confidence_threshold:
                autonomous_status = (
                    f"Недостаточная уверенность ИИ: {decision_confidence}% "
                    f"при пороге {confidence_threshold}%"
                )
            else:
                autonomous_ready = True

                if not queue_actions:
                    autonomous_status = (
                        "Готово к постановке в очередь при запуске ИИ"
                    )
                elif queued_count >= queue_capacity_remaining:
                    autonomous_ready = False
                    autonomous_status = (
                        "Очередь A3 заполнена: сначала завершите или подтвердите "
                        "текущие действия"
                        if queue_capacity_remaining == 0
                        else "Лимит новых действий для этого цикла исчерпан"
                    )
                else:
                    result = enqueue_autonomous_action(
                        company_id=company_id,
                        action_type=action_type,
                        target_type="automation_rule",
                        target_id=row["id"],
                        payload_json=json.dumps({
                            "requested_by": "system",
                            "reason": request_reason,
                        }, ensure_ascii=False),
                    )
                    autonomous_queued = result.get("queued", False)
                    queued_count += int(autonomous_queued)

                    if autonomous_queued:
                        autonomous_status = "Действие добавлено в очередь"
                    else:
                        autonomous_ready = False
                        queue_reason_labels = {
                            "protected_rule": "Действие запрещено: правило защищено",
                            "target_not_found": "Действие не создано: правило не найдено",
                            "duplicate_pending_action": "Похожее действие уже находится в очереди",
                            "cooldown_active": "Действие временно ограничено защитой от повторов",
                        }
                        autonomous_status = queue_reason_labels.get(
                            result.get("reason"),
                            "Действие не удалось добавить в очередь",
                        )

        decisions.append({
            "rule_id": row["id"],
            "rule_name": row["name"],
            "active": bool(row["active"]),
            "confidence_score": confidence,
            "decision_confidence": decision_confidence,
            "confidence_threshold": confidence_threshold,
            "max_actions_per_cycle": max_actions_per_cycle,
            "recommendation": recommendation,
            "autonomous_ready": autonomous_ready,
            "autonomous_queued": autonomous_queued,
            "autonomous_pending": autonomous_pending,
            "autonomous_status": autonomous_status,
            "failed_events": failed,
            "skipped_events": skipped,
            "total_events": total,
        })

    summary = {
        "stable": sum(
            1 for item in decisions
            if item["recommendation"] == "stable"
        ),
        "attention": sum(
            1 for item in decisions
            if item["recommendation"] in {
                "retry_recommended",
                "investigate_rule",
                "disable_rule",
            }
        ),
        "ready": sum(
            1 for item in decisions
            if item["autonomous_ready"]
        ),
        "inactive": sum(
            1 for item in decisions
            if item["recommendation"] == "inactive"
        ),
    }

    return {
        "count": len(decisions),
        "queued_count": queued_count,
        "max_actions_per_cycle": max_actions_per_cycle,
        "pending_action_count": pending_action_count,
        "queue_capacity_remaining": queue_capacity_remaining,
        "summary": summary,
        "items": decisions[:20],
    }
