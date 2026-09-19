"""Safe aggregation and lifecycle management for application errors."""

import hashlib
import os
import re
from datetime import datetime, timedelta

from app.database import begin_locked_transaction, connect


_UUID_SEGMENT = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-"
    r"[89ab][0-9a-f]{3}-[0-9a-f]{12}$",
    re.IGNORECASE,
)
_HEX_SEGMENT = re.compile(r"^[0-9a-f]{16,}$", re.IGNORECASE)
_INTEGER_SEGMENT = re.compile(r"^\d+$")
_OPAQUE_SEGMENT = re.compile(r"^[A-Za-z0-9_-]{20,}$")


def _environment_int(name, default, minimum, maximum):
    try:
        value = int(str(os.getenv(name) or default).strip())
    except (TypeError, ValueError):
        value = default
    return max(minimum, min(maximum, value))


def get_error_monitoring_policy():
    return {
        "alert_threshold": _environment_int(
            "ERROR_MONITOR_ALERT_THRESHOLD", 3, 1, 1000,
        ),
        "alert_cooldown_minutes": _environment_int(
            "ERROR_MONITOR_ALERT_COOLDOWN_MINUTES", 60, 1, 10080,
        ),
        "recent_hours": _environment_int(
            "ERROR_MONITOR_RECENT_HOURS", 24, 1, 720,
        ),
    }


def normalize_error_path(path):
    """Remove identifiers from a URL path so equivalent failures are grouped."""
    raw_path = str(path or "/").split("?", 1)[0].strip()
    if not raw_path.startswith("/"):
        raw_path = "/" + raw_path
    normalized = []
    for segment in raw_path.split("/"):
        if _INTEGER_SEGMENT.fullmatch(segment):
            normalized.append(":id")
        elif _UUID_SEGMENT.fullmatch(segment):
            normalized.append(":uuid")
        elif _HEX_SEGMENT.fullmatch(segment):
            normalized.append(":token")
        elif "@" in segment or _OPAQUE_SEGMENT.fullmatch(segment):
            normalized.append(":value")
        else:
            normalized.append(segment[:80])
    value = "/".join(normalized)[:240]
    return value or "/"


def build_error_fingerprint(error_type, method, path, source="runtime"):
    payload = "\x1f".join((
        str(source or "runtime").strip().lower()[:80],
        str(error_type or "Exception").strip()[:120],
        str(method or "").strip().upper()[:12],
        normalize_error_path(path),
    ))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:32]


def _datetime_text(value):
    return value.strftime("%Y-%m-%d %H:%M:%S")


def _parse_datetime(value):
    text = str(value or "").strip()
    for pattern in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            return datetime.strptime(text, pattern)
        except ValueError:
            continue
    return None


def error_incident_status_label(status):
    return {
        "active": "Активен",
        "acknowledged": "Принят",
        "resolved": "Решён",
    }.get(str(status or ""), "Неизвестно")


def _incident_dict(row, policy=None):
    if not row:
        return None
    incident = dict(row)
    policy = policy or get_error_monitoring_policy()
    incident["status_label"] = error_incident_status_label(
        incident.get("status"),
    )
    incident["status_tone"] = {
        "active": "critical",
        "acknowledged": "warning",
        "resolved": "ok",
    }.get(incident.get("status"), "warning")
    incident["is_repeated"] = (
        int(incident.get("occurrence_count") or 0)
        >= policy["alert_threshold"]
    )
    return incident


def record_error_incident(
    error_type,
    method="",
    path="/",
    source="runtime",
    severity="critical",
    error_id="",
    request_id="",
    username="",
    now=None,
):
    """Create or increment an incident without persisting exception text."""
    now_value = now or datetime.now()
    now_text = _datetime_text(now_value)
    policy = get_error_monitoring_policy()
    normalized_path = normalize_error_path(path)
    normalized_type = str(error_type or "Exception").strip()[:120]
    normalized_method = str(method or "").strip().upper()[:12]
    normalized_source = str(source or "runtime").strip().lower()[:80]
    normalized_severity = (
        severity if severity in {"warning", "critical"} else "critical"
    )
    fingerprint = build_error_fingerprint(
        normalized_type,
        normalized_method,
        normalized_path,
        normalized_source,
    )
    connection = connect()

    try:
        cursor = connection.cursor()
        begin_locked_transaction(cursor, "application_error", fingerprint)
        row = cursor.execute("""
            SELECT *
            FROM application_error_incidents
            WHERE fingerprint=?
            LIMIT 1
        """, (fingerprint,)).fetchone()
        reopened = bool(row and row["status"] == "resolved")
        if row:
            cursor.execute("""
                UPDATE application_error_incidents
                SET error_type=?, source=?, method=?, path_pattern=?,
                    severity=?, status=?, last_seen_at=?,
                    occurrence_count=occurrence_count + 1,
                    reopen_count=reopen_count + ?,
                    last_error_id=?, last_request_id=?, last_username=?,
                    acknowledged_at=?, acknowledged_by=?,
                    resolved_at=?, resolved_by=?, resolution_note=?,
                    updated_at=?
                WHERE id=?
            """, (
                normalized_type,
                normalized_source,
                normalized_method,
                normalized_path,
                normalized_severity,
                "active" if reopened else row["status"],
                now_text,
                1 if reopened else 0,
                str(error_id or "")[:80],
                str(request_id or "")[:160],
                str(username or "")[:120],
                None if reopened else row["acknowledged_at"],
                None if reopened else row["acknowledged_by"],
                None if reopened else row["resolved_at"],
                None if reopened else row["resolved_by"],
                None if reopened else row["resolution_note"],
                now_text,
                row["id"],
            ))
            incident_id = row["id"]
            created = False
        else:
            cursor.execute("""
                INSERT INTO application_error_incidents (
                    fingerprint, error_type, source, method, path_pattern,
                    severity, status, first_seen_at, last_seen_at,
                    occurrence_count, reopen_count,
                    last_error_id, last_request_id, last_username,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, 'active', ?, ?, 1, 0,
                          ?, ?, ?, ?, ?)
            """, (
                fingerprint,
                normalized_type,
                normalized_source,
                normalized_method,
                normalized_path,
                normalized_severity,
                now_text,
                now_text,
                str(error_id or "")[:80],
                str(request_id or "")[:160],
                str(username or "")[:120],
                now_text,
                now_text,
            ))
            incident_id = cursor.lastrowid
            created = True

        incident_row = cursor.execute("""
            SELECT * FROM application_error_incidents WHERE id=?
        """, (incident_id,)).fetchone()
        last_notified_at = _parse_datetime(incident_row["last_notified_at"])
        cooldown_cutoff = now_value - timedelta(
            minutes=policy["alert_cooldown_minutes"],
        )
        notification_due = bool(
            int(incident_row["occurrence_count"] or 0)
            >= policy["alert_threshold"]
            and (
                last_notified_at is None
                or last_notified_at <= cooldown_cutoff
            )
        )
        if notification_due:
            cursor.execute("""
                UPDATE application_error_incidents
                SET first_notified_at=COALESCE(first_notified_at, ?),
                    last_notified_at=?,
                    notification_count=notification_count + 1,
                    updated_at=?
                WHERE id=?
            """, (now_text, now_text, now_text, incident_id))
            incident_row = cursor.execute("""
                SELECT * FROM application_error_incidents WHERE id=?
            """, (incident_id,)).fetchone()
        connection.commit()
        return {
            "created": created,
            "reopened": reopened,
            "notification_due": notification_due,
            "incident": _incident_dict(incident_row, policy),
            "policy": policy,
        }
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def get_error_incidents(status="all", limit=50):
    normalized_status = str(status or "all").strip().lower()
    if normalized_status not in {
        "all", "active", "acknowledged", "resolved",
    }:
        normalized_status = "all"
    limit = max(1, min(500, int(limit or 50)))
    connection = connect()
    if normalized_status == "all":
        rows = connection.execute("""
            SELECT * FROM application_error_incidents
            ORDER BY
                CASE status
                    WHEN 'active' THEN 0
                    WHEN 'acknowledged' THEN 1
                    ELSE 2
                END,
                last_seen_at DESC,
                id DESC
            LIMIT ?
        """, (limit,)).fetchall()
    else:
        rows = connection.execute("""
            SELECT * FROM application_error_incidents
            WHERE status=?
            ORDER BY last_seen_at DESC, id DESC
            LIMIT ?
        """, (normalized_status, limit)).fetchall()
    connection.close()
    policy = get_error_monitoring_policy()
    return [_incident_dict(row, policy) for row in rows]


def get_error_monitoring_overview(now=None, limit=30):
    now_value = now or datetime.now()
    policy = get_error_monitoring_policy()
    cutoff = _datetime_text(
        now_value - timedelta(hours=policy["recent_hours"]),
    )
    connection = connect()
    summary = connection.execute("""
        SELECT
            COUNT(*) AS total,
            SUM(CASE WHEN status='active' THEN 1 ELSE 0 END) AS active,
            SUM(CASE WHEN status='acknowledged' THEN 1 ELSE 0 END)
                AS acknowledged,
            SUM(CASE WHEN status='resolved' THEN 1 ELSE 0 END) AS resolved,
            SUM(
                CASE
                    WHEN status IN ('active', 'acknowledged')
                         AND occurrence_count>=?
                    THEN 1 ELSE 0
                END
            ) AS repeated,
            SUM(CASE WHEN last_seen_at>=? THEN 1 ELSE 0 END) AS recent
        FROM application_error_incidents
    """, (policy["alert_threshold"], cutoff)).fetchone()
    connection.close()
    values = {
        key: int(summary[key] or 0)
        for key in (
            "total", "active", "acknowledged", "resolved", "repeated", "recent",
        )
    }
    open_count = values["active"] + values["acknowledged"]
    if values["repeated"]:
        status = "critical"
        status_label = "Есть повторяющиеся ошибки"
    elif open_count:
        status = "warning"
        status_label = "Есть открытые ошибки"
    else:
        status = "ok"
        status_label = "Ошибок нет"
    return {
        "status": status,
        "status_label": status_label,
        "summary": {**values, "open": open_count},
        "policy": policy,
        "incidents": (
            get_error_incidents(limit=limit)
            if int(limit or 0) > 0
            else []
        ),
        "generated_at": _datetime_text(now_value),
    }


def _update_error_incident(incident_id, actor_username, target_status, note=""):
    if target_status not in {"acknowledged", "resolved"}:
        raise ValueError("Invalid error incident status")
    actor = str(actor_username or "").strip()[:120]
    if not actor:
        return {"ok": False, "error": "actor_required"}
    note = str(note or "").strip()[:500]
    now_text = _datetime_text(datetime.now())
    connection = connect()
    try:
        cursor = connection.cursor()
        begin_locked_transaction(cursor, "application_error", incident_id)
        row = cursor.execute("""
            SELECT * FROM application_error_incidents WHERE id=?
        """, (incident_id,)).fetchone()
        if not row:
            connection.commit()
            return {"ok": False, "error": "incident_not_found"}
        if target_status == "acknowledged":
            if row["status"] != "active":
                connection.commit()
                return {"ok": False, "error": "invalid_status"}
            cursor.execute("""
                UPDATE application_error_incidents
                SET status='acknowledged', acknowledged_at=?,
                    acknowledged_by=?, updated_at=?
                WHERE id=?
            """, (now_text, actor, now_text, incident_id))
        else:
            if row["status"] not in {"active", "acknowledged"}:
                connection.commit()
                return {"ok": False, "error": "invalid_status"}
            cursor.execute("""
                UPDATE application_error_incidents
                SET status='resolved', resolved_at=?, resolved_by=?,
                    resolution_note=?, updated_at=?
                WHERE id=?
            """, (now_text, actor, note, now_text, incident_id))
        updated = cursor.execute("""
            SELECT * FROM application_error_incidents WHERE id=?
        """, (incident_id,)).fetchone()
        connection.commit()
        return {"ok": True, "incident": _incident_dict(updated)}
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def acknowledge_error_incident(incident_id, actor_username):
    return _update_error_incident(
        incident_id,
        actor_username,
        "acknowledged",
    )


def resolve_error_incident(incident_id, actor_username, note=""):
    return _update_error_incident(
        incident_id,
        actor_username,
        "resolved",
        note,
    )
