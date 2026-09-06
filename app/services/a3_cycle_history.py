from datetime import datetime, timedelta

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

A3_CYCLE_HISTORY_LIMIT = 100
A3_CYCLE_HISTORY_EXPORT_LIMIT = 500
A3_CYCLE_HISTORY_KEEP = 500
A3_CYCLE_HISTORY_RETENTION_DAYS = 90
A3_SCHEDULER_HISTORY_WINDOW = 20
A3_SCHEDULER_WARNING_HOURS = 24
A3_SCHEDULER_CRITICAL_HOURS = 48


def require_company_id(company_id):
    if not company_id:
        raise ValueError("company_id is required")


def normalize_a3_cycle_status_filter(status_filter):
    normalized_status = str(status_filter or "all").strip().lower()

    if normalized_status not in {"all", *CYCLE_STATUS_LABELS.keys()}:
        return "all"

    return normalized_status


def a3_cycle_status_filter_label(status_filter):
    normalized_status = normalize_a3_cycle_status_filter(status_filter)

    if normalized_status == "all":
        return "Все результаты"

    return CYCLE_STATUS_LABELS[normalized_status]


def _build_cycle_history_where(company_id, status_filter):
    normalized_status = normalize_a3_cycle_status_filter(status_filter)
    where_sql = "WHERE company_id=?"
    params = [company_id]

    if normalized_status != "all":
        where_sql += " AND status=?"
        params.append(normalized_status)

    return where_sql, params, normalized_status


def _prune_a3_cycle_history(cursor, company_id, recorded_at):
    cutoff = (
        recorded_at - timedelta(days=A3_CYCLE_HISTORY_RETENTION_DAYS)
    ).isoformat(timespec="seconds")

    cursor.execute("""
        DELETE FROM a3_autonomous_cycle_runs
        WHERE company_id=?
          AND created_at < ?
    """, (company_id, cutoff))
    cursor.execute("""
        DELETE FROM a3_autonomous_cycle_runs
        WHERE company_id=?
          AND id NOT IN (
              SELECT id
              FROM a3_autonomous_cycle_runs
              WHERE company_id=?
              ORDER BY id DESC
              LIMIT ?
          )
    """, (
        company_id,
        company_id,
        A3_CYCLE_HISTORY_KEEP,
    ))


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

    recorded_at = datetime.now()
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
            recorded_at.isoformat(timespec="seconds"),
        ))
        run_id = c.lastrowid
        _prune_a3_cycle_history(c, company_id, recorded_at)
        conn.commit()
        return run_id
    finally:
        conn.close()


def get_a3_cycle_history(company_id, limit=20, status_filter="all"):
    require_company_id(company_id)

    try:
        normalized_limit = max(
            1,
            min(A3_CYCLE_HISTORY_EXPORT_LIMIT, int(limit or 20)),
        )
    except (TypeError, ValueError):
        normalized_limit = 20

    where_sql, params, _ = _build_cycle_history_where(
        company_id,
        status_filter,
    )
    params.append(normalized_limit)

    conn = connect()
    try:
        rows = conn.cursor().execute("""
            SELECT *
            FROM a3_autonomous_cycle_runs
            {where_sql}
            ORDER BY id DESC
            LIMIT ?
        """.format(where_sql=where_sql), params).fetchall()
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


def get_a3_cycle_summary(company_id, status_filter="all"):
    require_company_id(company_id)
    where_sql, params, normalized_status = _build_cycle_history_where(
        company_id,
        status_filter,
    )

    conn = connect()
    try:
        row = conn.cursor().execute("""
            SELECT
                COUNT(*) AS total_runs,
                SUM(CASE WHEN status='completed' THEN 1 ELSE 0 END)
                    AS completed_runs,
                SUM(CASE WHEN status='warning' THEN 1 ELSE 0 END)
                    AS warning_runs,
                SUM(CASE WHEN status='error' THEN 1 ELSE 0 END)
                    AS error_runs,
                COALESCE(SUM(processed_actions), 0) AS processed_actions,
                COALESCE(SUM(failed_actions), 0) AS failed_actions,
                COALESCE(AVG(duration_ms), 0) AS avg_duration_ms,
                AVG(health_score) AS avg_health_score
            FROM a3_autonomous_cycle_runs
            {where_sql}
        """.format(where_sql=where_sql), params).fetchone()
    finally:
        conn.close()

    item = dict(row or {})
    total_runs = int(item.get("total_runs") or 0)
    completed_runs = int(item.get("completed_runs") or 0)
    avg_health_score = item.get("avg_health_score")

    return {
        "status_filter": normalized_status,
        "status_filter_label": a3_cycle_status_filter_label(normalized_status),
        "total_runs": total_runs,
        "completed_runs": completed_runs,
        "warning_runs": int(item.get("warning_runs") or 0),
        "error_runs": int(item.get("error_runs") or 0),
        "processed_actions": int(item.get("processed_actions") or 0),
        "failed_actions": int(item.get("failed_actions") or 0),
        "avg_duration_ms": int(round(float(item.get("avg_duration_ms") or 0))),
        "avg_health_score": (
            None
            if avg_health_score is None
            else int(round(float(avg_health_score)))
        ),
        "success_rate": (
            round(completed_runs * 100 / total_runs, 1)
            if total_runs
            else 0
        ),
    }


def _parse_cycle_datetime(value):
    try:
        return datetime.fromisoformat(str(value or ""))
    except (TypeError, ValueError):
        return None


def _cycle_age_label(age_minutes):
    if age_minutes is None:
        return "Время неизвестно"

    if age_minutes < 1:
        return "Только что"

    if age_minutes < 60:
        return f"{age_minutes} мин. назад"

    age_hours = age_minutes // 60
    if age_hours < 24:
        return f"{age_hours} ч. назад"

    return f"{age_hours // 24} дн. назад"


def get_a3_cycle_reliability(company_id, now=None):
    require_company_id(company_id)
    now_value = now or datetime.now()

    conn = connect()
    try:
        rows = conn.cursor().execute("""
            SELECT status, created_at, duration_ms
            FROM a3_autonomous_cycle_runs
            WHERE company_id=?
              AND triggered_by='scheduler'
            ORDER BY id DESC
            LIMIT ?
        """, (
            company_id,
            A3_SCHEDULER_HISTORY_WINDOW,
        )).fetchall()
    finally:
        conn.close()

    items = [dict(row) for row in rows]
    completed_runs = sum(item.get("status") == "completed" for item in items)
    warning_runs = sum(item.get("status") == "warning" for item in items)
    error_runs = sum(item.get("status") == "error" for item in items)
    consecutive_errors = 0
    consecutive_attention = 0

    for item in items:
        if item.get("status") == "error":
            consecutive_errors += 1
        else:
            break

    for item in items:
        if item.get("status") != "completed":
            consecutive_attention += 1
        else:
            break

    latest_item = items[0] if items else {}
    latest_created_at = latest_item.get("created_at")
    latest_datetime = _parse_cycle_datetime(latest_created_at)
    age_minutes = None

    if latest_datetime:
        age_minutes = max(
            0,
            int((now_value - latest_datetime).total_seconds() // 60),
        )

    age_hours = age_minutes / 60 if age_minutes is not None else None
    total_runs = len(items)
    reliability_rate = (
        round(completed_runs * 100 / total_runs, 1)
        if total_runs
        else None
    )
    status = "stable"
    status_label = "Стабильно"
    status_tone = "success"
    message = "Фоновые циклы A3 выполняются без ошибок."
    recommendation = "Продолжайте контролировать журнал автономных запусков."

    if not items:
        status = "unknown"
        status_label = "Нет фоновых запусков"
        status_tone = "warning"
        message = "Планировщик A3 ещё не записал ни одного фонового цикла."
        recommendation = "Настройте регулярный вызов фонового маршрута A3."
    elif consecutive_errors >= 2:
        status = "critical"
        status_label = "Критично"
        status_tone = "danger"
        message = f"Подряд завершились ошибкой циклы: {consecutive_errors}."
        recommendation = "Проверьте журнал, настройки A3 и доступность базы данных."
    elif age_hours is not None and age_hours >= A3_SCHEDULER_CRITICAL_HOURS:
        status = "critical"
        status_label = "Планировщик остановлен"
        status_tone = "danger"
        message = "Фоновый цикл A3 не запускался больше 48 часов."
        recommendation = "Проверьте cron, секрет запуска и доступность приложения."
    elif latest_item.get("status") == "error":
        status = "warning"
        status_label = "Последний запуск с ошибкой"
        status_tone = "warning"
        message = "Последний фоновый цикл A3 завершился ошибкой."
        recommendation = "Проверьте причину ошибки до следующего запуска."
    elif age_hours is not None and age_hours >= A3_SCHEDULER_WARNING_HOURS:
        status = "warning"
        status_label = "Давно не запускался"
        status_tone = "warning"
        message = "Фоновый цикл A3 не запускался больше 24 часов."
        recommendation = "Убедитесь, что внешний планировщик продолжает работу."
    elif latest_item.get("status") == "warning":
        status = "warning"
        status_label = "Есть замечания"
        status_tone = "warning"
        message = "Последний фоновый цикл завершился с замечаниями."
        recommendation = "Проверьте очередь подтверждений и ошибки повторов."
    elif total_runs >= 3 and reliability_rate < 70:
        status = "warning"
        status_label = "Низкая надёжность"
        status_tone = "warning"
        message = "Меньше 70% последних фоновых циклов завершились без замечаний."
        recommendation = "Проверьте повторяющиеся причины нестабильных запусков."

    return {
        "status": status,
        "status_label": status_label,
        "status_tone": status_tone,
        "message": message,
        "recommendation": recommendation,
        "history_window": A3_SCHEDULER_HISTORY_WINDOW,
        "scheduler_runs": total_runs,
        "completed_runs": completed_runs,
        "warning_runs": warning_runs,
        "error_runs": error_runs,
        "reliability_rate": reliability_rate,
        "consecutive_errors": consecutive_errors,
        "consecutive_attention": consecutive_attention,
        "latest_status": latest_item.get("status"),
        "latest_status_label": CYCLE_STATUS_LABELS.get(
            latest_item.get("status"),
            "Нет данных",
        ),
        "latest_scheduler_run_at": latest_created_at,
        "latest_scheduler_age_minutes": age_minutes,
        "latest_scheduler_age_label": _cycle_age_label(age_minutes),
        "latest_duration_ms": int(latest_item.get("duration_ms") or 0),
    }
