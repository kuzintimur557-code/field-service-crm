import json

from app.database import connect


def _safe_payload(payload_json):
    if not payload_json:
        return {}

    try:
        return json.loads(payload_json)
    except Exception:
        return {}


def _condition_summary(conditions_json):
    labels = {
        "none": "Без условий",
        "priority_high": "Только высокий приоритет",
        "emergency": "Только срочные заявки",
        "status_new": "Только новые заявки",
        "status_in_progress": "Только заявки в работе",
        "status_done": "Только завершённые заявки",
        "payment_unpaid": "Только неоплаченные заявки",
        "payment_partial": "Только частично оплаченные заявки",
        "payment_paid": "Только оплаченные заявки",
        "worker_assigned": "Только задачи с исполнителем",
        "date_today": "Только задачи на сегодня",
        "date_overdue": "Только просроченные задачи",
        "date_future": "Только будущие задачи",
        "price_high": "Только дорогие заявки",
        "price_missing": "Только заявки без цены",
        "sla_today": "Только дедлайн сегодня",
        "sla_overdue": "Только просроченный SLA",
        "sla_due_24h": "Только дедлайн в ближайшие 24 часа",
        "client_new": "Только новые клиенты",
        "client_repeat": "Только постоянные клиенты",
        "client_vip": "Только VIP клиенты",
        "client_has_debt": "Только клиенты с долгом",
        "client_many_tasks": "Только клиенты с большим количеством заявок",
    }

    try:
        conditions = json.loads(conditions_json or "{}")
    except Exception:
        conditions = {}

    mode = conditions.get("mode") or "none"

    if mode not in labels:
        mode = "none"

    return {
        "mode": mode,
        "label": labels[mode],
        "raw": conditions,
    }


def _debug_action(label, action_type, target=None):
    return {
        "label": label,
        "action_type": action_type,
        "target": target or "",
    }


def _safe_fix(label, action_type, target=None, description=""):
    return {
        "label": label,
        "action_type": action_type,
        "target": target or "",
        "description": description,
        "safe": True,
    }


def _dangerous_fix(label, action_type, target_type, target_id=None, description=""):
    return {
        "label": label,
        "action_type": action_type,
        "target_type": target_type,
        "target_id": target_id,
        "description": description,
        "requires_approval": True,
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


def _debug_diagnosis(rule, actions, latest_problem_event):
    if not actions:
        return {
            "title": "Цепочка не выполняет полезных действий",
            "details": "У правила нет активных шагов выполнения. Даже если триггер сработает, бизнес-результата не будет.",
            "next_step": "Откройте правило и добавьте хотя бы одно действие.",
        }

    inactive_actions = [action for action in actions if not action["active"]]

    if len(inactive_actions) == len(actions):
        return {
            "title": "Все действия цепочки выключены",
            "details": "Правило может создавать события, но ни одно действие не будет выполнено.",
            "next_step": "Включите нужные действия или замените их рабочими шагами.",
        }

    if not rule["active"]:
        return {
            "title": "Правило выключено",
            "details": "Цепочка не будет запускаться автоматически, пока правило выключено.",
            "next_step": "Включите правило и выполните тестовый запуск.",
        }

    if latest_problem_event:
        message = latest_problem_event["message"] or "Без подробного сообщения"

        if latest_problem_event["status"] == "failed":
            return {
                "title": "Последний запуск завершился ошибкой",
                "details": message,
                "next_step": "Откройте проблемное событие, исправьте причину и повторите запуск цепочки.",
            }

        if latest_problem_event["status"] == "skipped":
            return {
                "title": "Последний запуск был пропущен",
                "details": message,
                "next_step": "Проверьте условия правила и повторите пропущенные события.",
            }

    return {
        "title": "Критических проблем не найдено",
        "details": "Цепочка выглядит рабочей по текущим данным.",
        "next_step": "Для контроля выполните ручной тестовый запуск.",
    }


def _risk_level(priority):
    if priority >= 90:
        return {
            "key": "critical",
            "label": "Критический",
            "description": "Нужно проверить в первую очередь.",
        }

    if priority >= 60:
        return {
            "key": "high",
            "label": "Высокий",
            "description": "Есть риск сбоя автоматизации.",
        }

    if priority >= 40:
        return {
            "key": "medium",
            "label": "Средний",
            "description": "Есть настройка, которая требует внимания.",
        }

    return {
        "key": "low",
        "label": "Низкий",
        "description": "Критических проблем не найдено.",
    }


def _workflow_safe_fixes(rule, actions, latest_problem_event):
    fixes = []

    if not rule["active"]:
        fixes.append(_safe_fix(
            "Включить правило",
            "enable_rule",
            rule["id"],
            "Безопасно включает правило без переключения туда-сюда.",
        ))

    if latest_problem_event and latest_problem_event["status"] == "skipped":
        fixes.append(_safe_fix(
            "Повторить пропущенные",
            "retry_skipped",
            rule["id"],
            "Повторяет только пропущенные события этой цепочки.",
        ))

    if actions and rule["active"]:
        fixes.append(_safe_fix(
            "Тестовый запуск",
            "run_rule",
            rule["id"],
            "Создаёт ручное событие для проверки цепочки.",
        ))

    return fixes[:3]


def _workflow_dangerous_fixes(rule, actions, latest_problem_event):
    fixes = []

    if rule["active"] and latest_problem_event and latest_problem_event["status"] == "failed":
        fixes.append(_dangerous_fix(
            "Запросить отключение правила",
            "disable_rule",
            "automation_rule",
            rule["id"],
            "Отключение правила требует подтверждения владельца.",
        ))

    return fixes[:2]


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
        "risk": _risk_level(priority),
        "reason": issues[0],
        "issues": issues,
        "diagnosis": _debug_diagnosis(rule, actions, latest_problem_event),
        "ai_recommendations": _ai_debug_recommendations(rule, actions, latest_problem_event),
        "latest_problem_event": dict(latest_problem_event) if latest_problem_event else None,
        "quick_actions": quick_actions,
        "safe_fixes": _workflow_safe_fixes(rule, actions, latest_problem_event),
        "dangerous_fixes": _workflow_dangerous_fixes(rule, actions, latest_problem_event),
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
    conditions = _condition_summary(rule["conditions_json"])

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
            "conditions": conditions,
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
