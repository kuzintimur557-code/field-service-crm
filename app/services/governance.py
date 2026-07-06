from datetime import datetime
import json

from app.database import connect


def require_company_id(company_id):
    if not company_id:
        raise ValueError("company_id is required")


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
        item["approval_safety"] = "safe" if safe else "unsafe"
        item["approval_safety_reason"] = reason
        item["approval_safety_label"] = label
        item["can_bulk_approve"] = safe
        item["can_bulk_reject"] = not safe

        items.append(item)

    return items


def get_approval_history(company_id, decision_filter="all"):
    require_company_id(company_id)

    if decision_filter not in {"all", "approved", "rejected"}:
        decision_filter = "all"

    conn = connect()
    c = conn.cursor()

    where_sql = "WHERE autonomous_action_approvals.company_id=?"
    params = [company_id]

    if decision_filter != "all":
        where_sql += " AND autonomous_action_approvals.decision=?"
        params.append(decision_filter)

    rows = c.execute("""
        SELECT
            autonomous_action_approvals.*,
            autonomous_action_approvals.action_queue_id AS action_id,
            autonomous_action_queue.action_type,
            autonomous_action_queue.target_type,
            autonomous_action_queue.target_id,
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
        LIMIT 100
    """.format(where_sql=where_sql), params).fetchall()

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
        item["decided_by_label"] = (
            "Система" if decided_by == "system" else decided_by
        )

        items.append(item)

    return items
