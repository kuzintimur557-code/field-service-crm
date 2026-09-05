import time
from datetime import datetime, timedelta

from app.database import connect
from app.services.ops_timeline import create_ops_timeline_event


SELF_HEALING_STATUS_LABELS = {
    "done": "Выполнено",
    "warning": "Нужно внимание",
    "failed": "Ошибка",
}

SELF_HEALING_STATUS_TONES = {
    "done": "success",
    "warning": "warning",
    "failed": "danger",
}

SKIPPED_EVENT_RETRY_COOLDOWN_MINUTES = 30


def require_company_id(company_id):
    if not company_id:
        raise ValueError("company_id is required")


def run_self_healing_cycle(company_id, retry_events_handler=None):
    require_company_id(company_id)

    started_at = time.time()
    retry_cutoff = (
        datetime.now() - timedelta(
            minutes=SKIPPED_EVENT_RETRY_COOLDOWN_MINUTES,
        )
    ).isoformat(timespec="seconds")

    conn = connect()
    c = conn.cursor()

    retried_events = 0
    reenabled_rules = 0
    retry_not_ready_events = 0
    retry_failed_events = 0

    skipped_events = c.execute("""
        SELECT id, rule_id, trigger_key, entity_type, entity_id, message
        FROM automation_events
        WHERE company_id=?
          AND status='skipped'
          AND (
            last_retried_at IS NULL
            OR last_retried_at < ?
          )
        ORDER BY id DESC
        LIMIT 10
    """, (
        company_id,
        retry_cutoff,
    )).fetchall()

    retry_groups = {}

    for row in skipped_events:
        event = dict(row)
        rule_id = event.get("rule_id")

        if retry_events_handler and rule_id:
            retry_groups.setdefault(rule_id, []).append(event)
            continue

        c.execute("""
            UPDATE automation_events
            SET status='pending',
                last_retried_at=?,
                retry_count=COALESCE(retry_count, 0) + 1
            WHERE id=?
        """, (
            datetime.now().isoformat(timespec="seconds"),
            event["id"],
        ))
        retried_events += 1

    conn.commit()
    conn.close()

    if retry_events_handler:
        for rule_id, events in retry_groups.items():
            try:
                retry_result = retry_events_handler(
                    company_id=company_id,
                    rule_id=rule_id,
                    events=events,
                ) or {}
                retried_events += retry_result.get("replayed", 0)
                retry_not_ready_events += retry_result.get("not_ready", 0)
                retry_failed_events += retry_result.get("failed", 0)
            except Exception:
                retry_failed_events += len(events)

    duration_ms = int((time.time() - started_at) * 1000)
    run_status = (
        "warning"
        if retry_failed_events or retry_not_ready_events
        else "done"
    )

    conn = connect()
    c = conn.cursor()
    c.execute("""
        INSERT INTO self_healing_runs (
            company_id,
            retried_events,
            retry_not_ready_events,
            retry_failed_events,
            reenabled_rules,
            status,
            duration_ms,
            created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        company_id,
        retried_events,
        retry_not_ready_events,
        retry_failed_events,
        reenabled_rules,
        run_status,
        duration_ms,
        datetime.now().isoformat(timespec="seconds"),
    ))
    conn.commit()
    conn.close()

    try:
        create_ops_timeline_event(
            company_id=company_id,
            event_type="self_healing",
            severity=(
                "warning"
                if retry_failed_events or retry_not_ready_events
                else "info"
            ),
            title="Цикл самовосстановления завершён",
            message=(
                f"Повторно запущено событий: {retried_events}. "
                f"Условия ещё не готовы: {retry_not_ready_events}. "
                f"Ошибок запуска: {retry_failed_events}. "
                "Отключённые правила не включались автоматически."
            ),
            source="self_healing",
            target_type="automation_event",
            cooldown_minutes=15,
        )
    except Exception:
        pass

    return {
        "retried_events": retried_events,
        "reenabled_rules": reenabled_rules,
        "retry_not_ready_events": retry_not_ready_events,
        "retry_failed_events": retry_failed_events,
        "duration_ms": duration_ms,
        "status": run_status,
        "checked_events": len(skipped_events),
        "retry_cooldown_minutes": SKIPPED_EVENT_RETRY_COOLDOWN_MINUTES,
    }


def get_recovery_history(company_id, limit=20):
    require_company_id(company_id)

    conn = connect()
    c = conn.cursor()

    rows = c.execute("""
        SELECT
            retried_events,
            retry_not_ready_events,
            retry_failed_events,
            reenabled_rules,
            status,
            duration_ms,
            created_at
        FROM self_healing_runs
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
        item = dict(row)
        status = item.get("status") or "done"
        item["status_label"] = SELF_HEALING_STATUS_LABELS.get(
            status,
            status,
        )
        item["status_tone"] = SELF_HEALING_STATUS_TONES.get(
            status,
            "warning",
        )
        items.append(item)

    return items
