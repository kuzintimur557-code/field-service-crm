from datetime import datetime

from app.database import connect


def get_governance_settings(company_id):
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


def save_governance_settings(
    company_id,
    autonomous_enabled,
    max_actions_per_cycle,
    require_critical_approval,
    confidence_threshold,
    protected_rules_json="[]",
):
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

    conn.close()

    return [dict(row) for row in rows]


def get_approval_history(company_id):
    conn = connect()
    c = conn.cursor()

    rows = c.execute("""
        SELECT
            autonomous_action_approvals.*,
            autonomous_action_queue.action_type,
            autonomous_action_queue.target_type,
            autonomous_action_queue.target_id
        FROM autonomous_action_approvals
        LEFT JOIN autonomous_action_queue
          ON autonomous_action_queue.id =
             autonomous_action_approvals.action_queue_id
        WHERE autonomous_action_approvals.company_id=?
        ORDER BY autonomous_action_approvals.id DESC
        LIMIT 100
    """, (company_id,)).fetchall()

    conn.close()

    return [dict(row) for row in rows]
