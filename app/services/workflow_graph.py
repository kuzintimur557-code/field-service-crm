import json

from app.database import connect


def _safe_payload(payload_json):
    if not payload_json:
        return {}

    try:
        return json.loads(payload_json)
    except Exception:
        return {}


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
