import json

from app.database import connect


def _safe_payload(payload_json):
    if not payload_json:
        return {}

    try:
        return json.loads(payload_json)
    except Exception:
        return {}


def _debug_action(label, action_type, target=None):
    return {
        "label": label,
        "action_type": action_type,
        "target": target or "",
    }


def _ai_debug_recommendations(rule, actions, latest_problem_event):
    recommendations = []

    if not rule["active"]:
        recommendations.append(
            "Цепочка выключена. Если это рабочий процесс, включите правило и выполните тестовый запуск."
        )

    if not actions:
        recommendations.append(
            "У правила нет действий. Добавьте уведомление, Telegram-сообщение или AI-сводку, иначе цепочка ничего не выполнит."
        )

    if latest_problem_event:
        status = latest_problem_event["status"]
        message = latest_problem_event["message"] or ""

        if status == "failed":
            recommendations.append(
                "Последний запуск завершился ошибкой. Откройте событие, проверьте сообщение ошибки и повторите цепочку после исправления."
            )
        elif status == "skipped":
            recommendations.append(
                "Последний запуск был пропущен. Проверьте условия правила и запустите повтор пропущенных событий."
            )

        if message:
            recommendations.append(f"Контекст последней проблемы: {message}")

    if not recommendations:
        recommendations.append(
            "Критических проблем не найдено. Для контроля можно выполнить ручной тестовый запуск цепочки."
        )

    return recommendations[:4]


def _workflow_debug(rule, actions, latest_problem_event):
    issues = []
    severity = "ok"
    priority = 0
    quick_actions = [
        _debug_action("Запустить цепочку", "run_rule", rule["id"]),
        _debug_action("Открыть правило", "open_rule", rule["id"]),
    ]

    if not rule["active"]:
        issues.append("Правило выключено")
        severity = "warning"
        priority = max(priority, 40)
        quick_actions.append(_debug_action("Включить правило", "enable_rule", rule["id"]))

    if not actions:
        issues.append("В цепочке нет действий")
        severity = "critical"
        priority = max(priority, 80)
        quick_actions.append(_debug_action("Добавить действие", "open_rule_actions", rule["id"]))

    if latest_problem_event:
        issues.append(f"Последнее проблемное событие: {latest_problem_event['status']}")
        severity = "critical" if latest_problem_event["status"] == "failed" else "warning"
        priority = max(priority, 90 if latest_problem_event["status"] == "failed" else 60)
        quick_actions.append(_debug_action("Открыть событие", "open_event", latest_problem_event["id"]))
        quick_actions.append(_debug_action("Повторить пропущенные", "retry_skipped", rule["id"]))

    if not issues:
        issues.append("Критических проблем не найдено")

    return {
        "status": "needs_attention" if issues[0] != "Критических проблем не найдено" else "ok",
        "severity": severity,
        "priority": priority,
        "reason": issues[0],
        "issues": issues,
        "ai_recommendations": _ai_debug_recommendations(rule, actions, latest_problem_event),
        "latest_problem_event": dict(latest_problem_event) if latest_problem_event else None,
        "quick_actions": quick_actions,
    }


def get_rule_workflow_graph(company_id, rule_id):
    conn = connect()
    c = conn.cursor()

    rule = c.execute("""
        SELECT *
        FROM automation_rules
        WHERE company_id=?
          AND id=?
    """, (
        company_id,
        rule_id,
    )).fetchone()

    if not rule:
        conn.close()
        return None

    actions = c.execute("""
        SELECT *
        FROM automation_actions
        WHERE company_id=?
          AND rule_id=?
        ORDER BY sort_order, id
    """, (
        company_id,
        rule_id,
    )).fetchall()

    event_counts = {
        row["status"]: row["count"]
        for row in c.execute("""
            SELECT status, COUNT(*) AS count
            FROM automation_events
            WHERE company_id=?
              AND rule_id=?
            GROUP BY status
        """, (
            company_id,
            rule_id,
        )).fetchall()
    }

    latest_problem_event = c.execute("""
        SELECT
            id,
            status,
            message,
            created_at,
            processed_at
        FROM automation_events
        WHERE company_id=?
          AND rule_id=?
          AND status IN ('failed', 'skipped')
        ORDER BY id DESC
        LIMIT 1
    """, (
        company_id,
        rule_id,
    )).fetchone()

    conn.close()

    done_count = event_counts.get("done", 0)
    skipped_count = event_counts.get("skipped", 0)
    pending_count = event_counts.get("pending", 0)
    failed_count = event_counts.get("failed", 0)
    total_events = done_count + skipped_count + pending_count + failed_count
    success_rate = round(done_count / max(done_count + skipped_count + failed_count, 1) * 100, 1)

    nodes = [
        {
            "id": f"trigger:{rule_id}",
            "type": "trigger",
            "label": rule["trigger_key"],
            "status": "active" if rule["active"] else "disabled",
        },
        {
            "id": f"rule:{rule_id}",
            "type": "rule",
            "label": rule["name"],
            "status": "active" if rule["active"] else "disabled",
        },
    ]

    edges = [
        {
            "from": f"trigger:{rule_id}",
            "to": f"rule:{rule_id}",
            "label": "запускает",
        }
    ]

    action_items = []

    for action in actions:
        node_id = f"action:{action['id']}"
        payload = _safe_payload(action["payload_json"])

        nodes.append({
            "id": node_id,
            "type": "action",
            "label": action["action_key"],
            "status": "active" if action["active"] else "disabled",
            "sort_order": action["sort_order"],
            "target_username": payload.get("target_username", ""),
        })

        edges.append({
            "from": f"rule:{rule_id}",
            "to": node_id,
            "label": "выполняет",
        })

        action_items.append({
            "id": action["id"],
            "action_key": action["action_key"],
            "active": bool(action["active"]),
            "sort_order": action["sort_order"],
            "payload": payload,
        })

    event_node_id = f"events:{rule_id}"

    nodes.append({
        "id": event_node_id,
        "type": "events",
        "label": "События",
        "status": "has_events" if total_events else "empty",
        "total": total_events,
    })

    edges.append({
        "from": f"rule:{rule_id}",
        "to": event_node_id,
        "label": "создаёт события",
    })

    return {
        "ok": True,
        "rule": {
            "id": rule["id"],
            "name": rule["name"],
            "trigger_key": rule["trigger_key"],
            "active": bool(rule["active"]),
        },
        "nodes": nodes,
        "edges": edges,
        "actions": action_items,
        "debug": _workflow_debug(rule, action_items, latest_problem_event),
        "stats": {
            "actions_total": len(action_items),
            "events_total": total_events,
            "done": done_count,
            "skipped": skipped_count,
            "pending": pending_count,
            "failed": failed_count,
            "success_rate": success_rate,
        },
    }


def get_company_workflow_graphs(company_id, limit=50):
    conn = connect()
    c = conn.cursor()

    rows = c.execute("""
        SELECT id
        FROM automation_rules
        WHERE company_id=?
        ORDER BY id DESC
        LIMIT ?
    """, (
        company_id,
        limit,
    )).fetchall()

    conn.close()

    items = []

    for row in rows:
        graph = get_rule_workflow_graph(company_id, row["id"])

        if graph:
            items.append(graph)

    return {
        "ok": True,
        "count": len(items),
        "items": items,
    }


def get_rule_workflow_debug(company_id, rule_id):
    graph = get_rule_workflow_graph(company_id, rule_id)

    if not graph:
        return None

    return {
        "ok": True,
        "rule": graph["rule"],
        "debug": graph["debug"],
        "stats": graph["stats"],
    }
