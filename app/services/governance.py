from datetime import datetime
import json

from app.database import connect


APPROVAL_HISTORY_LIMIT = 100
APPROVAL_ATTENTION_MINUTES = 6 * 60
APPROVAL_OVERDUE_MINUTES = 24 * 60

ACTION_LABELS = {
    "retry_events": "Повторить события",
    "disable_rule": "Отключить правило",
    "recovery_cycle": "Запустить восстановление",
}

TARGET_LABELS = {
    "automation_rule": "Правило автоматизации",
    "automation_event": "Событие автоматизации",
    "autonomous_action": "ИИ-действие",
}


def require_company_id(company_id):
    if not company_id:
        raise ValueError("company_id is required")


def action_label(action_type):
    return ACTION_LABELS.get(action_type, action_type or "-")


def target_label(target_type):
    return TARGET_LABELS.get(target_type, target_type or "-")


def approval_request_context(payload_json):
    try:
        payload = json.loads(payload_json or "{}")
    except (TypeError, ValueError):
        payload = {}

    reason = str(payload.get("reason") or "").strip()
    requested_by = str(payload.get("requested_by") or "").strip()

    return {
        "request_reason": reason[:500],
        "requested_by": requested_by[:120],
        "requested_by_label": "Система" if requested_by == "system" else requested_by,
    }


def approval_age_context(created_at):
    try:
        created = datetime.fromisoformat(
            str(created_at or "").replace("Z", "+00:00")
        )
    except (TypeError, ValueError):
        return {
            "approval_age_minutes": None,
            "approval_age_label": "Время не указано",
            "approval_urgency": "unknown",
            "approval_urgency_label": "Нужно проверить время",
        }

    now = datetime.now(created.tzinfo) if created.tzinfo else datetime.now()
    age_minutes = max(0, int((now - created).total_seconds() // 60))

    if age_minutes >= APPROVAL_OVERDUE_MINUTES:
        urgency = "overdue"
        urgency_label = "Ожидает больше суток"
    elif age_minutes >= APPROVAL_ATTENTION_MINUTES:
        urgency = "attention"
        urgency_label = "Ожидает больше 6 часов"
    else:
        urgency = "normal"
        urgency_label = "Новый запрос"

    if age_minutes < 1:
        age_label = "Меньше минуты назад"
    elif age_minutes < 60:
        age_label = f"{age_minutes} мин. назад"
    elif age_minutes < 24 * 60:
        age_label = f"{age_minutes // 60} ч. назад"
    else:
        age_label = f"{age_minutes // (24 * 60)} дн. назад"

    return {
        "approval_age_minutes": age_minutes,
        "approval_age_label": age_label,
        "approval_urgency": urgency,
        "approval_urgency_label": urgency_label,
    }


def get_governance_settings(company_id):
    require_company_id(company_id)

    conn = connect()
    c = conn.cursor()

    row = c.execute("""
        SELECT *
        FROM autonomous_governance_settings
        WHERE company_id=?
        ORDER BY id DESC
        LIMIT 1
    """, (company_id,)).fetchone()

    conn.close()

    if not row:
        return {
            "autonomous_enabled": 1,
            "max_actions_per_cycle": 20,
            "require_critical_approval": 1,
            "confidence_threshold": 70,
            "protected_rules_json": "[]",
        }

    return dict(row)


def ensure_governance_settings(company_id):
    settings = get_governance_settings(company_id)

    if settings.get("id"):
        return settings

    save_governance_settings(
        company_id=company_id,
        autonomous_enabled=settings["autonomous_enabled"],
        max_actions_per_cycle=settings["max_actions_per_cycle"],
        require_critical_approval=settings["require_critical_approval"],
        confidence_threshold=settings["confidence_threshold"],
        protected_rules_json=settings["protected_rules_json"],
    )

    return get_governance_settings(company_id)


def save_governance_settings(
    company_id,
    autonomous_enabled,
    max_actions_per_cycle,
    require_critical_approval,
    confidence_threshold,
    protected_rules_json="[]",
):
    require_company_id(company_id)

    conn = connect()
    c = conn.cursor()

    c.execute("""
        INSERT INTO autonomous_governance_settings (
            company_id,
            autonomous_enabled,
            max_actions_per_cycle,
            require_critical_approval,
            confidence_threshold,
            protected_rules_json,
            created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        company_id,
        autonomous_enabled,
        max_actions_per_cycle,
        require_critical_approval,
        confidence_threshold,
        protected_rules_json,
        datetime.now().isoformat(timespec="seconds"),
    ))

    conn.commit()
    conn.close()

    return {
        "ok": True,
    }


def get_approval_queue(company_id):
    require_company_id(company_id)

    governance = get_governance_settings(company_id)

    try:
        protected_rules = {
            int(rule_id)
            for rule_id in json.loads(
                governance.get("protected_rules_json") or "[]"
            )
        }
    except Exception:
        protected_rules = set()

    conn = connect()
    c = conn.cursor()

    rows = c.execute("""
        SELECT *
        FROM autonomous_action_queue
        WHERE company_id=?
          AND status='awaiting_approval'
        ORDER BY id DESC
        LIMIT 100
    """, (company_id,)).fetchall()

    rule_ids = [
        row["target_id"]
        for row in rows
        if row["target_type"] == "automation_rule" and row["target_id"]
    ]

    rules_by_id = {}

    if rule_ids:
        placeholders = ",".join("?" for _ in rule_ids)
        rules_by_id = {
            row["id"]: dict(row)
            for row in c.execute(f"""
                SELECT id, name, active
                FROM automation_rules
                WHERE company_id=?
                  AND id IN ({placeholders})
            """, (
                company_id,
                *rule_ids,
            )).fetchall()
        }

    conn.close()

    items = []

    for row in rows:
        item = dict(row)
        reason = "ready"
        label = "Можно подтвердить"
        safe = True

        if (
            item["action_type"] != "disable_rule"
            or item["target_type"] != "automation_rule"
        ):
            reason = "unsupported_action"
            label = "Неподдерживаемое действие"
            safe = False
        elif item["target_id"] in protected_rules:
            reason = "protected_rule"
            label = "Защищённое правило"
            safe = False
        elif item["target_id"] not in rules_by_id:
            reason = "missing_target"
            label = "Цель не найдена"
            safe = False

        target_rule = rules_by_id.get(item["target_id"]) or {}

        item["target_name"] = target_rule.get("name") or ""
        item["target_active"] = target_rule.get("active")
        item["action_label"] = action_label(item.get("action_type"))
        item["target_label"] = target_label(item.get("target_type"))
        item["approval_safety"] = "safe" if safe else "unsafe"
        item["approval_safety_reason"] = reason
        item["approval_safety_label"] = label
        item["can_bulk_approve"] = safe
        item["can_bulk_reject"] = not safe
        item.update(approval_request_context(item.get("payload_json")))
        item.update(approval_age_context(item.get("created_at")))

        items.append(item)

    return items


def get_approval_history(
    company_id,
    decision_filter="all",
    date_from=None,
    date_to=None,
    action_type_filter="all",
    target_type_filter="all",
    decided_by_filter=None,
    target_id_filter=None,
):
    require_company_id(company_id)

    if decision_filter not in {"all", "approved", "rejected"}:
        decision_filter = "all"

    if action_type_filter not in {"all", *ACTION_LABELS.keys()}:
        action_type_filter = "all"

    if target_type_filter not in {"all", *TARGET_LABELS.keys()}:
        target_type_filter = "all"

    conn = connect()
    c = conn.cursor()

    where_sql = "WHERE autonomous_action_approvals.company_id=?"
    params = [company_id]

    if decision_filter != "all":
        where_sql += " AND autonomous_action_approvals.decision=?"
        params.append(decision_filter)

    if date_from:
        where_sql += " AND autonomous_action_approvals.created_at >= ?"
        params.append(f"{date_from}T00:00:00")

    if date_to:
        where_sql += " AND autonomous_action_approvals.created_at <= ?"
        params.append(f"{date_to}T23:59:59")

    if action_type_filter != "all":
        where_sql += " AND autonomous_action_queue.action_type=?"
        params.append(action_type_filter)

    if target_type_filter != "all":
        where_sql += " AND autonomous_action_queue.target_type=?"
        params.append(target_type_filter)

    if decided_by_filter:
        where_sql += " AND autonomous_action_approvals.decided_by=?"
        params.append(decided_by_filter)

    if target_id_filter:
        where_sql += " AND autonomous_action_queue.target_id=?"
        params.append(target_id_filter)

    params_with_limit = [*params, APPROVAL_HISTORY_LIMIT]

    rows = c.execute("""
        SELECT
            autonomous_action_approvals.*,
            autonomous_action_approvals.action_queue_id AS action_id,
            autonomous_action_queue.action_type,
            autonomous_action_queue.target_type,
            autonomous_action_queue.target_id,
            autonomous_action_queue.payload_json,
            automation_rules.name AS target_name,
            automation_rules.active AS target_active
        FROM autonomous_action_approvals
        LEFT JOIN autonomous_action_queue
          ON autonomous_action_queue.id =
             autonomous_action_approvals.action_queue_id
        LEFT JOIN automation_rules
          ON automation_rules.company_id =
             autonomous_action_approvals.company_id
         AND automation_rules.id = autonomous_action_queue.target_id
         AND autonomous_action_queue.target_type='automation_rule'
        {where_sql}
        ORDER BY autonomous_action_approvals.id DESC
        LIMIT ?
    """.format(where_sql=where_sql), params_with_limit).fetchall()

    conn.close()

    items = []

    for row in rows:
        item = dict(row)
        decision = item.get("decision")
        decided_by = item.get("decided_by") or "system"

        item["decision_label"] = {
            "approved": "Одобрено",
            "rejected": "Отклонено",
        }.get(decision, decision or "Решение не указано")
        item["action_label"] = action_label(item.get("action_type"))
        item["target_label"] = target_label(item.get("target_type"))
        item["decided_by_label"] = (
            "Система" if decided_by == "system" else decided_by
        )
        item.update(approval_request_context(item.get("payload_json")))

        items.append(item)

    return items
