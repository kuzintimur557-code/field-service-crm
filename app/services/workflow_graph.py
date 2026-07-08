import json

from app.database import connect


MIN_WORKFLOW_GRAPH_LIMIT = 1
MAX_WORKFLOW_GRAPH_LIMIT = 100


def require_company_id(company_id):
    if not company_id:
        raise ValueError("company_id is required")


def normalize_workflow_graph_limit(limit):
    try:
        value = int(limit)
    except (TypeError, ValueError):
        return 50

    if value < MIN_WORKFLOW_GRAPH_LIMIT:
        return MIN_WORKFLOW_GRAPH_LIMIT

    if value > MAX_WORKFLOW_GRAPH_LIMIT:
        return MAX_WORKFLOW_GRAPH_LIMIT

    return value


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
        "task_text_contains": "Текст заявки содержит",
        "status_new": "Только новые заявки",
        "status_in_progress": "Только заявки в работе",
        "status_done": "Только завершённые заявки",
        "status_cancelled": "Только отменённые заявки",
        "payment_unpaid": "Только неоплаченные заявки",
        "payment_partial": "Только частично оплаченные заявки",
        "payment_paid": "Только оплаченные заявки",
        "worker_assigned": "Только задачи с исполнителем",
        "worker_unassigned": "Только задачи без исполнителя",
        "worker_specific": "Только выбранный исполнитель",
        "date_today": "Только задачи на сегодня",
        "date_overdue": "Только просроченные задачи",
        "date_future": "Только будущие задачи",
        "price_high": "Только дорогие заявки",
        "price_missing": "Только заявки без цены",
        "catalog_specific": "Только выбранная позиция каталога",
        "sla_today": "Только дедлайн сегодня",
        "sla_overdue": "Только просроченный SLA",
        "sla_due_24h": "Только дедлайн в ближайшие 24 часа",
        "client_specific": "Только выбранный клиент",
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

    if conditions.get("conditions"):
        items = conditions.get("conditions") or []
        operator = str(conditions.get("operator") or "and").lower()
        operator_label = "ИЛИ" if operator == "or" else "И"

        item_labels = []

        for item in items:
            item_mode = item.get("mode") or "none"
            item_labels.append(item.get("label") or labels.get(item_mode, item_mode))

        if operator == "or":
            label = "Любое условие: " + " или ".join(item_labels)
            mode = "combined_or"
        else:
            label = "Все условия: " + " + ".join(item_labels)
            mode = "combined_and"

        return {
            "mode": mode,
            "label": label,
            "operator": operator,
            "operator_label": operator_label,
            "count": len(item_labels),
            "count_label": f"Условий: {len(item_labels)}",
            "items": item_labels,
            "raw": conditions,
        }

    mode = conditions.get("mode") or "none"

    if mode not in labels:
        mode = "none"

    return {
        "mode": mode,
        "label": conditions.get("label") or labels[mode],
        "operator": "and",
        "operator_label": "И",
        "count": 0 if mode == "none" else 1,
        "count_label": f"Условий: {0 if mode == 'none' else 1}",
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


def _action_key_label(action_key):
    labels = {
        "notification": "Уведомление",
        "telegram_alert": "Telegram-уведомление",
        "email": "Email",
        "create_task": "Создать задачу",
        "ai_digest": "ИИ-сводка",
    }

    return labels.get(action_key or "", action_key or "Действие")


def _trigger_key_label(trigger_key):
    labels = {
        "overdue_task": "Просрочена задача",
        "sla_overdue": "Просрочен SLA",
        "unpaid_task": "Нет оплаты",
        "worker_overload": "Перегрузка сотрудника",
        "new_client": "Новый клиент",
        "daily_digest": "Ежедневная ИИ-сводка",
        "weekly_digest": "Еженедельная ИИ-сводка",
    }

    return labels.get(trigger_key or "", trigger_key or "Триггер")


def _workflow_status_label(status):
    labels = {
        "active": "Активно",
        "disabled": "Выключено",
        "has_events": "Есть события",
        "empty": "Нет событий",
        "done": "Выполнено",
        "skipped": "Пропущено",
        "pending": "Ожидает",
        "failed": "Ошибка",
    }

    return labels.get(status or "", status or "-")


def _ai_debug_recommendations(rule, actions, latest_problem_event):
    recommendations = []

    if not rule["active"]:
        recommendations.append(
            "Цепочка выключена. Если это рабочий процесс, включите правило и выполните тестовый запуск."
        )

    if not actions:
        recommendations.append(
            "У правила нет действий. Добавьте уведомление, Telegram-сообщение или ИИ-сводку, иначе цепочка ничего не выполнит."
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

    risk = _risk_level(priority)
    diagnosis = _debug_diagnosis(rule, actions, latest_problem_event)
    summary_label = (
        f"Диагностика: {issues[0]} · "
        f"Риск: {risk['label']} · "
        f"Следующий шаг: {diagnosis['next_step']}"
    )

    return {
        "status": "needs_attention" if issues[0] != "Критических проблем не найдено" else "ok",
        "severity": severity,
        "priority": priority,
        "risk": risk,
        "reason": issues[0],
        "summary_label": summary_label,
        "issues": issues,
        "diagnosis": diagnosis,
        "ai_recommendations": _ai_debug_recommendations(rule, actions, latest_problem_event),
        "latest_problem_event": dict(latest_problem_event) if latest_problem_event else None,
        "quick_actions": quick_actions,
        "safe_fixes": _workflow_safe_fixes(rule, actions, latest_problem_event),
        "dangerous_fixes": _workflow_dangerous_fixes(rule, actions, latest_problem_event),
    }


def _workflow_stats_summary(total_events, done_count, skipped_count, pending_count, failed_count, success_rate):
    return (
        f"Событий: {total_events} · "
        f"Выполнено: {done_count} · "
        f"Пропущено: {skipped_count} · "
        f"Ожидает: {pending_count} · "
        f"Ошибки: {failed_count} · "
        f"Успешность: {success_rate}%"
    )


def _company_workflow_summary(items):
    total = len(items)
    active = sum(1 for item in items if (item.get("rule") or {}).get("active"))
    disabled = total - active
    empty = sum(1 for item in items if not item.get("actions"))
    needs_attention = sum(
        1
        for item in items
        if (item.get("debug") or {}).get("status") == "needs_attention"
    )
    problem_events = sum(
        (item.get("stats") or {}).get("problem_count", 0)
        for item in items
    )

    return {
        "total": total,
        "active": active,
        "disabled": disabled,
        "empty": empty,
        "needs_attention": needs_attention,
        "problem_events": problem_events,
        "label": (
            f"Цепочек: {total} · "
            f"Активных: {active} · "
            f"Выключенных: {disabled} · "
            f"Без действий: {empty} · "
            f"Требуют внимания: {needs_attention} · "
            f"Проблемных событий: {problem_events}"
        ),
    }


def get_rule_workflow_graph(company_id, rule_id):
    require_company_id(company_id)

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
    problem_count = skipped_count + failed_count
    success_rate = round(done_count / max(done_count + skipped_count + failed_count, 1) * 100, 1)
    conditions = _condition_summary(rule["conditions_json"])
    trigger_label = _trigger_key_label(rule["trigger_key"])
    rule_status = "active" if rule["active"] else "disabled"
    event_status = "has_events" if total_events else "empty"

    nodes = [
        {
            "id": f"trigger:{rule_id}",
            "type": "trigger",
            "label": trigger_label,
            "status": rule_status,
            "status_label": _workflow_status_label(rule_status),
        },
        {
            "id": f"rule:{rule_id}",
            "type": "rule",
            "label": rule["name"],
            "status": rule_status,
            "status_label": _workflow_status_label(rule_status),
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
        action_label = _action_key_label(action["action_key"])
        action_status = "active" if action["active"] else "disabled"

        nodes.append({
            "id": node_id,
            "type": "action",
            "label": action_label,
            "status": action_status,
            "status_label": _workflow_status_label(action_status),
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
            "label": action_label,
            "active": bool(action["active"]),
            "status": action_status,
            "status_label": _workflow_status_label(action_status),
            "sort_order": action["sort_order"],
            "payload": payload,
        })

    event_node_id = f"events:{rule_id}"

    nodes.append({
        "id": event_node_id,
        "type": "events",
        "label": "События",
        "status": event_status,
        "status_label": _workflow_status_label(event_status),
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
            "trigger_label": trigger_label,
            "active": bool(rule["active"]),
            "status": rule_status,
            "status_label": _workflow_status_label(rule_status),
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
            "problem_count": problem_count,
            "problem_label": f"Проблемных событий: {problem_count}",
            "success_rate": success_rate,
            "summary_label": _workflow_stats_summary(
                total_events,
                done_count,
                skipped_count,
                pending_count,
                failed_count,
                success_rate,
            ),
        },
    }


def get_company_workflow_graphs(company_id, limit=50):
    require_company_id(company_id)
    limit = normalize_workflow_graph_limit(limit)

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
        "limit": limit,
        "count": len(items),
        "summary": _company_workflow_summary(items),
        "items": items,
    }


def get_rule_workflow_debug(company_id, rule_id):
    require_company_id(company_id)

    graph = get_rule_workflow_graph(company_id, rule_id)

    if not graph:
        return None

    return {
        "ok": True,
        "rule": graph["rule"],
        "debug": graph["debug"],
        "stats": graph["stats"],
    }
