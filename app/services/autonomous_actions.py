from datetime import datetime, timedelta
import json

from app.database import connect
from app.services.governance import get_governance_settings
from app.services.ops_timeline import create_ops_timeline_event


SUPPORTED_AUTONOMOUS_ACTIONS = {
    ("disable_rule", "automation_rule"),
    ("retry_events", "automation_rule"),
}

AUTONOMOUS_ACTION_COOLDOWN_MINUTES = 10
AUTONOMOUS_ACTION_COOLDOWN_LIMIT = 3


def require_company_id(company_id):
    if not company_id:
        raise ValueError("company_id is required")


def _is_supported_action(action_type, target_type):
    return (action_type, target_type) in SUPPORTED_AUTONOMOUS_ACTIONS


def _protected_rule_ids(governance):
    try:
        return {
            int(rule_id)
            for rule_id in json.loads(
                governance.get("protected_rules_json") or "[]"
            )
        }
    except Exception:
        return set()


def _automation_rule_exists(cursor, company_id, rule_id):
    if not rule_id:
        return False

    return cursor.execute("""
        SELECT id
        FROM automation_rules
        WHERE company_id=?
          AND id=?
    """, (
        company_id,
        rule_id,
    )).fetchone() is not None


def _approval_reason(reason, default):
    value = str(reason or default).strip()
    return (value or default)[:500]


def enqueue_autonomous_action(
    company_id,
    action_type,
    target_type,
    target_id=None,
    payload_json=None,
):
    require_company_id(company_id)

    if not _is_supported_action(action_type, target_type):
        return {
            "queued": False,
            "reason": "unsupported_action",
        }

    if target_type == "automation_rule":
        try:
            target_id = int(target_id)
        except Exception:
            return {
                "queued": False,
                "reason": "invalid_target_id",
            }

        if target_id <= 0:
            return {
                "queued": False,
                "reason": "invalid_target_id",
            }

    now_value = datetime.now()
    cooldown_cutoff = (
        now_value - timedelta(minutes=AUTONOMOUS_ACTION_COOLDOWN_MINUTES)
    ).isoformat(timespec="seconds")

    conn = connect()
    c = conn.cursor()

    if (
        target_type == "automation_rule"
        and not _automation_rule_exists(c, company_id, target_id)
    ):
        conn.close()

        return {
            "queued": False,
            "reason": "target_not_found",
        }

    if (
        action_type == "disable_rule"
        and target_id in _protected_rule_ids(get_governance_settings(company_id))
    ):
        conn.close()

        return {
            "queued": False,
            "reason": "protected_rule",
        }

    existing = c.execute("""
        SELECT id
        FROM autonomous_action_queue
        WHERE company_id=?
          AND action_type=?
          AND target_type=?
          AND COALESCE(target_id, 0)=COALESCE(?, 0)
          AND status IN ('pending', 'awaiting_approval', 'approved')
        ORDER BY id DESC
        LIMIT 1
    """, (
        company_id,
        action_type,
        target_type,
        target_id,
    )).fetchone()

    if existing:
        conn.close()

        return {
            "queued": False,
            "reason": "duplicate_pending_action",
        }

    cooldown_count = c.execute("""
        SELECT COUNT(*) AS total
        FROM autonomous_action_queue
        WHERE company_id=?
          AND action_type=?
          AND target_type=?
          AND COALESCE(target_id, 0)=COALESCE(?, 0)
          AND created_at >= ?
    """, (
        company_id,
        action_type,
        target_type,
        target_id,
        cooldown_cutoff,
    )).fetchone()["total"]

    if cooldown_count >= AUTONOMOUS_ACTION_COOLDOWN_LIMIT:
        conn.close()

        return {
            "queued": False,
            "reason": "cooldown_active",
        }

    c.execute("""
        INSERT INTO autonomous_action_queue (
            company_id,
            action_type,
            target_type,
            target_id,
            payload_json,
            created_at
        ) VALUES (?, ?, ?, ?, ?, ?)
    """, (
        company_id,
        action_type,
        target_type,
        target_id,
        payload_json,
        now_value.isoformat(timespec="seconds"),
    ))

    conn.commit()
    conn.close()

    return {
        "queued": True,
    }


def get_autonomous_actions(company_id, limit=50):
    require_company_id(company_id)

    conn = connect()
    c = conn.cursor()

    rows = c.execute("""
        SELECT
            id,
            action_type,
            target_type,
            target_id,
            status,
            payload_json,
            created_at,
            processed_at
        FROM autonomous_action_queue
        WHERE company_id=?
        ORDER BY id DESC
        LIMIT ?
    """, (
        company_id,
        limit,
    )).fetchall()

    conn.close()

    return [dict(row) for row in rows]


def process_autonomous_actions(company_id):
    require_company_id(company_id)

    governance = get_governance_settings(company_id)

    if not governance.get("autonomous_enabled", 1):
        return {
            "processed": 0,
            "blocked": True,
            "reason": "autonomous_disabled",
        }

    conn = connect()
    c = conn.cursor()

    protected_rules = _protected_rule_ids(governance)

    rows = c.execute("""
        SELECT *
        FROM autonomous_action_queue
        WHERE company_id=?
          AND status IN ('pending', 'approved')
        ORDER BY id ASC
        LIMIT ?
    """, (
        company_id,
        governance.get("max_actions_per_cycle", 20),
    )).fetchall()

    processed = 0
    awaiting_approval = 0
    failed = 0

    for row in rows:
        action_type = row["action_type"]
        target_type = row["target_type"]
        target_id = row["target_id"]
        status = row["status"]

        if (
            action_type == "disable_rule"
            and target_type == "automation_rule"
            and target_id in protected_rules
        ):
            c.execute("""
                UPDATE autonomous_action_queue
                SET status='failed',
                    processed_at=?
                WHERE id=?
            """, (
                datetime.now().isoformat(timespec="seconds"),
                row["id"],
            ))
            failed += 1
            continue

        if (
            governance.get("require_critical_approval", 1)
            and action_type == "disable_rule"
            and status != "approved"
        ):
            c.execute("""
                UPDATE autonomous_action_queue
                SET status='awaiting_approval'
                WHERE id=?
            """, (row["id"],))

            awaiting_approval += 1
            continue

        if action_type == "retry_events":
            if target_type == "automation_rule":
                if not _automation_rule_exists(c, company_id, target_id):
                    c.execute("""
                        UPDATE autonomous_action_queue
                        SET status='failed',
                            processed_at=?
                        WHERE id=?
                    """, (
                        datetime.now().isoformat(timespec="seconds"),
                        row["id"],
                    ))
                    failed += 1
                    continue

            c.execute("""
                UPDATE automation_events
                SET status='pending',
                    processed_at=NULL
                WHERE company_id=?
                  AND status='skipped'
                  AND (
                    ?!='automation_rule'
                    OR rule_id=?
                  )
            """, (
                company_id,
                target_type,
                target_id,
            ))
        elif action_type == "disable_rule" and target_type == "automation_rule":
            if not _automation_rule_exists(c, company_id, target_id):
                c.execute("""
                    UPDATE autonomous_action_queue
                    SET status='failed',
                        processed_at=?
                    WHERE id=?
                """, (
                    datetime.now().isoformat(timespec="seconds"),
                    row["id"],
                ))
                failed += 1
                continue

            c.execute("""
                UPDATE automation_rules
                SET active=0
                WHERE company_id=?
                  AND id=?
            """, (
                company_id,
                target_id,
            ))
        else:
            c.execute("""
                UPDATE autonomous_action_queue
                SET status='failed',
                    processed_at=?
                WHERE id=?
            """, (
                datetime.now().isoformat(timespec="seconds"),
                row["id"],
            ))
            failed += 1
            continue

        c.execute("""
            UPDATE autonomous_action_queue
            SET status='completed',
                processed_at=?
            WHERE id=?
        """, (
            datetime.now().isoformat(timespec="seconds"),
            row["id"],
        ))

        processed += 1

    conn.commit()
    conn.close()

    return {
        "processed": processed,
        "awaiting_approval": awaiting_approval,
        "failed": failed,
    }


def approve_autonomous_action(
    company_id,
    action_id,
    decided_by="system",
    reason=None,
):
    require_company_id(company_id)

    conn = connect()
    c = conn.cursor()

    row = c.execute("""
        SELECT *
        FROM autonomous_action_queue
        WHERE id=?
          AND company_id=?
          AND status='awaiting_approval'
    """, (
        action_id,
        company_id,
    )).fetchone()

    if not row:
        conn.close()

        return {
            "ok": False,
            "error": "not_found",
        }

    if (
        row["action_type"] != "disable_rule"
        or row["target_type"] != "automation_rule"
    ):
        c.execute("""
            UPDATE autonomous_action_queue
            SET status='failed',
                processed_at=?
            WHERE id=?
              AND company_id=?
        """, (
            datetime.now().isoformat(timespec="seconds"),
            action_id,
            company_id,
        ))

        conn.commit()
        conn.close()

        return {
            "ok": False,
            "error": "unsupported_action",
        }

    if (
        row["target_type"] == "automation_rule"
        and not _automation_rule_exists(c, company_id, row["target_id"])
    ):
        c.execute("""
            UPDATE autonomous_action_queue
            SET status='failed',
                processed_at=?
            WHERE id=?
              AND company_id=?
        """, (
            datetime.now().isoformat(timespec="seconds"),
            action_id,
            company_id,
        ))

        conn.commit()
        conn.close()

        return {
            "ok": False,
            "error": "target_not_found",
        }

    if row["target_id"] in _protected_rule_ids(get_governance_settings(company_id)):
        c.execute("""
            UPDATE autonomous_action_queue
            SET status='failed',
                processed_at=?
            WHERE id=?
              AND company_id=?
        """, (
            datetime.now().isoformat(timespec="seconds"),
            action_id,
            company_id,
        ))

        conn.commit()
        conn.close()

        return {
            "ok": False,
            "error": "protected_rule",
        }

    c.execute("""
        INSERT INTO autonomous_action_approvals (
            company_id,
            action_queue_id,
            decision,
            decided_by,
            reason,
            created_at
        ) VALUES (?, ?, ?, ?, ?, ?)
    """, (
        company_id,
        action_id,
        "approved",
        decided_by,
        _approval_reason(reason, "Одобрено вручную"),
        datetime.now().isoformat(timespec="seconds"),
    ))

    c.execute("""
        UPDATE autonomous_action_queue
        SET status='approved',
            processed_at=NULL
        WHERE id=?
          AND company_id=?
    """, (
        action_id,
        company_id,
    ))

    conn.commit()
    conn.close()

    create_ops_timeline_event(
        company_id=company_id,
        event_type="approval",
        severity="info",
        title="ИИ-действие подтверждено",
        message=f"Подтверждено действие #{action_id}",
        target_type="autonomous_action",
        target_id=action_id,
    )

    return {
        "ok": True,
        "action_id": action_id,
    }


def approve_safe_autonomous_actions(company_id, decided_by="system", limit=50):
    require_company_id(company_id)

    rows, protected_rules, existing_rule_ids = _build_approval_queue_context(
        company_id,
        limit,
    )

    result = {
        "ok": True,
        "total": len(rows),
        "approved": 0,
        "skipped": 0,
        "failed": 0,
        "protected": 0,
        "missing_target": 0,
        "unsupported": 0,
    }

    for row in rows:
        if (
            row["action_type"] != "disable_rule"
            or row["target_type"] != "automation_rule"
        ):
            result["skipped"] += 1
            result["unsupported"] += 1
            continue

        if row["target_id"] in protected_rules:
            result["skipped"] += 1
            result["protected"] += 1
            continue

        if row["target_id"] not in existing_rule_ids:
            result["skipped"] += 1
            result["missing_target"] += 1
            continue

        approval = approve_autonomous_action(
            company_id=company_id,
            action_id=row["id"],
            decided_by=decided_by,
            reason="Массово одобрено: безопасное действие",
        )

        if approval.get("ok"):
            result["approved"] += 1
        else:
            result["failed"] += 1

    if result["approved"]:
        create_ops_timeline_event(
            company_id=company_id,
            event_type="approval",
            severity="info",
            title="ИИ-действия подтверждены",
            message=f"Массово подтверждено действий: {result['approved']}",
            target_type="autonomous_action",
            target_id=None,
        )

    return result


def _build_approval_queue_context(company_id, limit):
    governance = get_governance_settings(company_id)
    protected_rules = _protected_rule_ids(governance)

    conn = connect()
    c = conn.cursor()

    rows = c.execute("""
        SELECT *
        FROM autonomous_action_queue
        WHERE company_id=?
          AND status='awaiting_approval'
        ORDER BY id ASC
        LIMIT ?
    """, (
        company_id,
        limit,
    )).fetchall()

    rule_ids = [
        row["target_id"]
        for row in rows
        if row["target_type"] == "automation_rule" and row["target_id"]
    ]

    existing_rule_ids = set()

    if rule_ids:
        placeholders = ",".join("?" for _ in rule_ids)
        existing_rule_ids = {
            row["id"]
            for row in c.execute(f"""
                SELECT id
                FROM automation_rules
                WHERE company_id=?
                  AND id IN ({placeholders})
            """, (
                company_id,
                *rule_ids,
            )).fetchall()
        }

    conn.close()

    return rows, protected_rules, existing_rule_ids


def reject_unsafe_autonomous_actions(company_id, decided_by="system", limit=50):
    require_company_id(company_id)

    rows, protected_rules, existing_rule_ids = _build_approval_queue_context(
        company_id,
        limit,
    )

    result = {
        "ok": True,
        "total": len(rows),
        "rejected": 0,
        "skipped": 0,
        "protected": 0,
        "missing_target": 0,
        "unsupported": 0,
    }

    for row in rows:
        unsafe = False
        rejection_reason = ""

        if (
            row["action_type"] != "disable_rule"
            or row["target_type"] != "automation_rule"
        ):
            unsafe = True
            rejection_reason = "Массово отклонено: неподдерживаемое действие"
            result["unsupported"] += 1
        elif row["target_id"] in protected_rules:
            unsafe = True
            rejection_reason = "Массово отклонено: защищённое правило"
            result["protected"] += 1
        elif row["target_id"] not in existing_rule_ids:
            unsafe = True
            rejection_reason = "Массово отклонено: цель не найдена"
            result["missing_target"] += 1

        if not unsafe:
            result["skipped"] += 1
            continue

        rejection = reject_autonomous_action(
            company_id=company_id,
            action_id=row["id"],
            decided_by=decided_by,
            reason=rejection_reason,
        )

        if rejection.get("ok"):
            result["rejected"] += 1

    if result["rejected"]:
        create_ops_timeline_event(
            company_id=company_id,
            event_type="approval",
            severity="warning",
            title="ИИ-действия отклонены",
            message=f"Массово отклонено небезопасных действий: {result['rejected']}",
            target_type="autonomous_action",
            target_id=None,
        )

    return result


def reject_autonomous_action(
    company_id,
    action_id,
    decided_by="system",
    reason=None,
):
    require_company_id(company_id)

    conn = connect()
    c = conn.cursor()

    row = c.execute("""
        SELECT *
        FROM autonomous_action_queue
        WHERE id=?
          AND company_id=?
          AND status='awaiting_approval'
    """, (
        action_id,
        company_id,
    )).fetchone()

    if not row:
        conn.close()

        return {
            "ok": False,
            "error": "not_found",
        }

    c.execute("""
        INSERT INTO autonomous_action_approvals (
            company_id,
            action_queue_id,
            decision,
            decided_by,
            reason,
            created_at
        ) VALUES (?, ?, ?, ?, ?, ?)
    """, (
        company_id,
        action_id,
        "rejected",
        decided_by,
        _approval_reason(reason, "Отклонено вручную"),
        datetime.now().isoformat(timespec="seconds"),
    ))

    c.execute("""
        UPDATE autonomous_action_queue
        SET status='rejected',
            processed_at=?
        WHERE id=?
          AND company_id=?
    """, (
        datetime.now().isoformat(timespec="seconds"),
        action_id,
        company_id,
    ))

    conn.commit()
    conn.close()

    create_ops_timeline_event(
        company_id=company_id,
        event_type="approval",
        severity="warning",
        title="ИИ-действие отклонено",
        message=f"Отклонено действие #{action_id}",
        target_type="autonomous_action",
        target_id=action_id,
    )

    return {
        "ok": True,
        "action_id": action_id,
    }
