from datetime import datetime

from app.database import connect


CYCLE_STATUS_LABELS = {
    "completed": "Завершено",
    "warning": "Завершено с замечаниями",
    "error": "Ошибка",
}

CYCLE_STATUS_TONES = {
    "completed": "success",
    "warning": "warning",
    "error": "danger",
}

CYCLE_SOURCE_LABELS = {
    "scheduler": "Планировщик",
    "system": "Система",
}


def require_company_id(company_id):
    if not company_id:
        raise ValueError("company_id is required")


def record_a3_cycle_run(
    company_id,
    triggered_by,
    status,
    decision_count=0,
    queued_actions=0,
    processed_actions=0,
    awaiting_approval=0,
    failed_actions=0,
    retried_events=0,
    retry_not_ready_events=0,
    retry_failed_events=0,
    health_score=None,
    health_status="",
    duration_ms=0,
    message="",
):
    require_company_id(company_id)

    normalized_status = str(status or "completed").strip()
    if normalized_status not in CYCLE_STATUS_LABELS:
        normalized_status = "error"

    source = str(triggered_by or "system").strip()[:120] or "system"
    normalized_health_score = None
    if health_score is not None:
        try:
            normalized_health_score = max(0, min(100, int(health_score)))
        except (TypeError, ValueError):
            normalized_health_score = None

    conn = connect()
    try:
        c = conn.cursor()
        c.execute("""
            INSERT INTO a3_autonomous_cycle_runs (
                company_id,
                triggered_by,
                status,
                decision_count,
                queued_actions,
                processed_actions,
                awaiting_approval,
                failed_actions,
                retried_events,
                retry_not_ready_events,
                retry_failed_events,
                health_score,
                health_status,
                duration_ms,
                message,
                created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            company_id,
            source,
            normalized_status,
            max(0, int(decision_count or 0)),
            max(0, int(queued_actions or 0)),
            max(0, int(processed_actions or 0)),
            max(0, int(awaiting_approval or 0)),
            max(0, int(failed_actions or 0)),
            max(0, int(retried_events or 0)),
            max(0, int(retry_not_ready_events or 0)),
            max(0, int(retry_failed_events or 0)),
            normalized_health_score,
            str(health_status or "").strip()[:40],
            max(0, int(duration_ms or 0)),
            str(message or "").strip()[:1000],
            datetime.now().isoformat(timespec="seconds"),
        ))
        run_id = c.lastrowid
        conn.commit()
        return run_id
    finally:
        conn.close()


def get_a3_cycle_history(company_id, limit=20):
    require_company_id(company_id)

    try:
        normalized_limit = max(1, min(100, int(limit or 20)))
    except (TypeError, ValueError):
        normalized_limit = 20

    conn = connect()
    try:
        rows = conn.cursor().execute("""
            SELECT *
            FROM a3_autonomous_cycle_runs
            WHERE company_id=?
            ORDER BY id DESC
            LIMIT ?
        """, (
            company_id,
            normalized_limit,
        )).fetchall()
    finally:
        conn.close()

    items = []
    for row in rows:
        item = dict(row)
        status = item.get("status") or "completed"
        source = item.get("triggered_by") or "system"
        item["status_label"] = CYCLE_STATUS_LABELS.get(status, status)
        item["status_tone"] = CYCLE_STATUS_TONES.get(status, "warning")
        item["source_label"] = CYCLE_SOURCE_LABELS.get(
            source,
            f"Вручную: {source}",
        )
        items.append(item)

    return items
