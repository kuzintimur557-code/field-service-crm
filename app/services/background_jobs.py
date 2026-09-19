"""Durable database-backed jobs for production background work."""

import json
import os
import re
from datetime import datetime, timedelta

from app.database import begin_locked_transaction, connect


JOB_TYPE_PATTERN = re.compile(r"^[a-z][a-z0-9_.-]{1,79}$")
ERROR_CODE_PATTERN = re.compile(r"[^a-zA-Z0-9_.-]+")
class BackgroundJobExecutionError(RuntimeError):
    def __init__(self, code, retryable=True):
        super().__init__(str(code or "background_job_failed"))
        self.code = _safe_error_code(code)
        self.retryable = bool(retryable)


def _environment_int(name, default, minimum, maximum):
    try:
        value = int(str(os.getenv(name) or default).strip())
    except (TypeError, ValueError):
        value = default
    return max(minimum, min(maximum, value))


def get_background_job_policy():
    return {
        "batch_size": _environment_int(
            "BACKGROUND_JOB_BATCH_SIZE", 10, 1, 100
        ),
        "max_attempts": _environment_int(
            "BACKGROUND_JOB_MAX_ATTEMPTS", 3, 1, 10
        ),
        "stale_minutes": _environment_int(
            "BACKGROUND_JOB_STALE_MINUTES", 60, 5, 1440
        ),
        "warning_minutes": _environment_int(
            "BACKGROUND_JOB_WARNING_MINUTES", 5, 1, 1440
        ),
        "success_retention_days": _environment_int(
            "BACKGROUND_JOB_SUCCESS_RETENTION_DAYS", 14, 1, 365
        ),
        "failed_retention_days": _environment_int(
            "BACKGROUND_JOB_FAILED_RETENTION_DAYS", 30, 1, 730
        ),
    }


def _now_value(now=None):
    return now or datetime.now()


def _date_text(value):
    return value.strftime("%Y-%m-%d %H:%M:%S")


def _validate_job_type(job_type):
    value = str(job_type or "").strip().lower()
    if not JOB_TYPE_PATTERN.fullmatch(value):
        raise ValueError("Invalid background job type")
    return value


def _safe_error_code(value):
    code = ERROR_CODE_PATTERN.sub("_", str(value or "").strip())
    return (code.strip("_") or "background_job_failed")[:160]


def _json_text(value):
    return json.dumps(
        value if value is not None else {},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _json_value(value):
    try:
        decoded = json.loads(str(value or "{}"))
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}
    return decoded if isinstance(decoded, dict) else {}


def _status_label(status):
    return {
        "pending": "Ожидает",
        "running": "Выполняется",
        "succeeded": "Выполнено",
        "failed": "Ошибка",
    }.get(str(status or ""), "Неизвестно")


def _job_dict(row):
    if not row:
        return None
    job = dict(row)
    job["payload"] = _json_value(job.pop("payload_json", ""))
    job["result"] = _json_value(job.pop("result_json", ""))
    job["status_label"] = _status_label(job.get("status"))
    return job


def enqueue_background_job(
    job_type,
    payload=None,
    company_id=None,
    requested_by="",
    dedupe_key="",
    priority=100,
    max_attempts=None,
    available_at=None,
    now=None,
):
    job_type = _validate_job_type(job_type)
    if payload is not None and not isinstance(payload, dict):
        raise ValueError("Background job payload must be an object")
    policy = get_background_job_policy()
    max_attempts = max_attempts or policy["max_attempts"]
    max_attempts = max(1, min(10, int(max_attempts)))
    priority = max(0, min(1000, int(priority)))
    normalized_dedupe = str(dedupe_key or "").strip()[:160]
    requested_by = str(requested_by or "").strip()[:120]
    now_value = _now_value(now)
    available_value = available_at or now_value
    now_text = _date_text(now_value)
    available_text = _date_text(available_value)
    connection = connect()

    try:
        cursor = connection.cursor()
        begin_locked_transaction(
            cursor,
            "background_job_enqueue",
            normalized_dedupe or job_type,
        )
        if normalized_dedupe:
            existing = cursor.execute("""
                SELECT *
                FROM background_jobs
                WHERE dedupe_key=?
                  AND status IN ('pending', 'running')
                ORDER BY id DESC
                LIMIT 1
            """, (normalized_dedupe,)).fetchone()
            if existing:
                connection.commit()
                return {
                    "created": False,
                    "job": _job_dict(existing),
                }

        cursor.execute("""
            INSERT INTO background_jobs (
                company_id, job_type, status, priority,
                payload_json, result_json, dedupe_key, requested_by,
                attempts, max_attempts, available_at,
                created_at, updated_at
            ) VALUES (?, ?, 'pending', ?, ?, '{}', ?, ?, 0, ?, ?, ?, ?)
        """, (
            company_id,
            job_type,
            priority,
            _json_text(payload),
            normalized_dedupe,
            requested_by,
            max_attempts,
            available_text,
            now_text,
            now_text,
        ))
        job_id = cursor.lastrowid
        created = cursor.execute(
            "SELECT * FROM background_jobs WHERE id=?",
            (job_id,),
        ).fetchone()
        connection.commit()
        return {
            "created": True,
            "job": _job_dict(created),
        }
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def recover_stale_background_jobs(now=None):
    policy = get_background_job_policy()
    now_value = _now_value(now)
    now_text = _date_text(now_value)
    cutoff = _date_text(
        now_value - timedelta(minutes=policy["stale_minutes"])
    )
    connection = connect()
    recovered = 0
    failed = 0

    try:
        cursor = connection.cursor()
        begin_locked_transaction(cursor, "background_job_claim")
        rows = cursor.execute("""
            SELECT id, attempts, max_attempts
            FROM background_jobs
            WHERE status='running'
              AND locked_at IS NOT NULL
              AND locked_at<=?
            ORDER BY id
        """, (cutoff,)).fetchall()
        for row in rows:
            if int(row["attempts"] or 0) >= int(row["max_attempts"] or 1):
                cursor.execute("""
                    UPDATE background_jobs
                    SET status='failed', locked_at=NULL, locked_by=NULL,
                        finished_at=?, last_error='worker_lease_expired',
                        updated_at=?
                    WHERE id=? AND status='running'
                """, (now_text, now_text, row["id"]))
                failed += cursor.rowcount
            else:
                cursor.execute("""
                    UPDATE background_jobs
                    SET status='pending', available_at=?,
                        locked_at=NULL, locked_by=NULL,
                        last_error='worker_lease_expired', updated_at=?
                    WHERE id=? AND status='running'
                """, (now_text, now_text, row["id"]))
                recovered += cursor.rowcount
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()

    return {"recovered": recovered, "failed": failed}


def claim_next_background_job(worker_id, now=None):
    worker_id = str(worker_id or "").strip()[:160]
    if not worker_id:
        raise ValueError("Background worker id is required")
    now_text = _date_text(_now_value(now))
    connection = connect()

    try:
        cursor = connection.cursor()
        begin_locked_transaction(cursor, "background_job_claim")
        row = cursor.execute("""
            SELECT *
            FROM background_jobs
            WHERE status='pending'
              AND available_at<=?
            ORDER BY priority, id
            LIMIT 1
        """, (now_text,)).fetchone()
        if not row:
            connection.commit()
            return None
        cursor.execute("""
            UPDATE background_jobs
            SET status='running', attempts=attempts + 1,
                locked_at=?, locked_by=?,
                started_at=COALESCE(started_at, ?), updated_at=?
            WHERE id=? AND status='pending'
        """, (
            now_text,
            worker_id,
            now_text,
            now_text,
            row["id"],
        ))
        claimed = cursor.execute(
            "SELECT * FROM background_jobs WHERE id=?",
            (row["id"],),
        ).fetchone()
        connection.commit()
        return _job_dict(claimed)
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def complete_background_job(job_id, worker_id, result=None, now=None):
    now_text = _date_text(_now_value(now))
    connection = connect()
    try:
        cursor = connection.cursor()
        cursor.execute("""
            UPDATE background_jobs
            SET status='succeeded', result_json=?, finished_at=?,
                locked_at=NULL, locked_by=NULL, last_error='', updated_at=?
            WHERE id=? AND status='running' AND locked_by=?
        """, (
            _json_text(result),
            now_text,
            now_text,
            int(job_id),
            str(worker_id or "")[:160],
        ))
        updated = cursor.rowcount == 1
        connection.commit()
        return updated
    finally:
        connection.close()


def fail_background_job(
    job_id,
    worker_id,
    error_code,
    retryable=True,
    now=None,
):
    now_value = _now_value(now)
    now_text = _date_text(now_value)
    connection = connect()
    try:
        cursor = connection.cursor()
        begin_locked_transaction(cursor, "background_job_finish", int(job_id))
        row = cursor.execute("""
            SELECT attempts, max_attempts
            FROM background_jobs
            WHERE id=? AND status='running' AND locked_by=?
        """, (int(job_id), str(worker_id or "")[:160])).fetchone()
        if not row:
            connection.commit()
            return {"updated": False, "status": "ignored"}
        attempts = int(row["attempts"] or 0)
        max_attempts = int(row["max_attempts"] or 1)
        will_retry = bool(retryable) and attempts < max_attempts
        if will_retry:
            delay_minutes = min(60, 2 ** max(0, attempts - 1))
            available_at = _date_text(
                now_value + timedelta(minutes=delay_minutes)
            )
            cursor.execute("""
                UPDATE background_jobs
                SET status='pending', available_at=?,
                    locked_at=NULL, locked_by=NULL,
                    last_error=?, updated_at=?
                WHERE id=? AND status='running' AND locked_by=?
            """, (
                available_at,
                _safe_error_code(error_code),
                now_text,
                int(job_id),
                str(worker_id or "")[:160],
            ))
            status = "pending"
        else:
            cursor.execute("""
                UPDATE background_jobs
                SET status='failed', finished_at=?,
                    locked_at=NULL, locked_by=NULL,
                    last_error=?, updated_at=?
                WHERE id=? AND status='running' AND locked_by=?
            """, (
                now_text,
                _safe_error_code(error_code),
                now_text,
                int(job_id),
                str(worker_id or "")[:160],
            ))
            status = "failed"
        updated = cursor.rowcount == 1
        connection.commit()
        return {
            "updated": updated,
            "status": status if updated else "ignored",
            "retry_scheduled": will_retry if updated else False,
        }
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def cleanup_background_job_history(now=None):
    policy = get_background_job_policy()
    now_value = _now_value(now)
    succeeded_cutoff = _date_text(
        now_value - timedelta(days=policy["success_retention_days"])
    )
    failed_cutoff = _date_text(
        now_value - timedelta(days=policy["failed_retention_days"])
    )
    connection = connect()
    try:
        cursor = connection.cursor()
        cursor.execute("""
            DELETE FROM background_jobs
            WHERE (status='succeeded' AND finished_at<?)
               OR (status='failed' AND finished_at<?)
        """, (succeeded_cutoff, failed_cutoff))
        deleted = max(0, int(cursor.rowcount or 0))
        connection.commit()
        return deleted
    finally:
        connection.close()


def process_background_jobs(handlers, worker_id, limit=None, now=None):
    policy = get_background_job_policy()
    limit = policy["batch_size"] if limit is None else int(limit)
    limit = max(1, min(100, limit))
    recovery = recover_stale_background_jobs(now=now)
    summary = {
        "claimed": 0,
        "succeeded": 0,
        "retried": 0,
        "failed": 0,
        "recovered": recovery["recovered"],
        "stale_failed": recovery["failed"],
        "cleaned": 0,
        "items": [],
    }

    for _index in range(limit):
        job = claim_next_background_job(worker_id, now=now)
        if not job:
            break
        summary["claimed"] += 1
        handler = handlers.get(job["job_type"])
        try:
            if handler is None:
                raise BackgroundJobExecutionError(
                    "unsupported_job_type",
                    retryable=False,
                )
            result = handler(job["payload"], job) or {}
            if not isinstance(result, dict):
                raise BackgroundJobExecutionError(
                    "invalid_job_result",
                    retryable=False,
                )
            if not complete_background_job(
                job["id"], worker_id, result=result, now=now
            ):
                raise BackgroundJobExecutionError(
                    "job_lease_lost",
                    retryable=False,
                )
            summary["succeeded"] += 1
            summary["items"].append({
                "id": job["id"],
                "job_type": job["job_type"],
                "status": "succeeded",
                "result": result,
            })
        except BackgroundJobExecutionError as error:
            failure = fail_background_job(
                job["id"],
                worker_id,
                error.code,
                retryable=error.retryable,
                now=now,
            )
            key = "retried" if failure.get("retry_scheduled") else "failed"
            summary[key] += 1
            summary["items"].append({
                "id": job["id"],
                "job_type": job["job_type"],
                "status": failure.get("status"),
                "error": error.code,
            })
        except Exception as error:
            error_code = f"unexpected_{error.__class__.__name__}"
            failure = fail_background_job(
                job["id"],
                worker_id,
                error_code,
                retryable=True,
                now=now,
            )
            key = "retried" if failure.get("retry_scheduled") else "failed"
            summary[key] += 1
            summary["items"].append({
                "id": job["id"],
                "job_type": job["job_type"],
                "status": failure.get("status"),
                "error": _safe_error_code(error_code),
            })

    summary["cleaned"] = cleanup_background_job_history(now=now)
    return summary


def get_recent_background_jobs(job_type="", limit=20, include_payload=False):
    parameters = []
    query = "SELECT * FROM background_jobs"
    if job_type:
        query += " WHERE job_type=?"
        parameters.append(_validate_job_type(job_type))
    query += " ORDER BY id DESC LIMIT ?"
    parameters.append(max(1, min(100, int(limit))))
    connection = connect()
    try:
        rows = connection.execute(query, parameters).fetchall()
        jobs = [_job_dict(row) for row in rows]
        if not include_payload:
            for job in jobs:
                job.pop("payload", None)
        return jobs
    finally:
        connection.close()


def get_background_queue_status(now=None):
    policy = get_background_job_policy()
    now_value = _now_value(now)
    now_text = _date_text(now_value)
    stale_cutoff = _date_text(
        now_value - timedelta(minutes=policy["stale_minutes"])
    )
    failure_cutoff = _date_text(now_value - timedelta(hours=24))
    connection = connect()
    try:
        row = connection.execute("""
            SELECT
                SUM(CASE WHEN status='pending' THEN 1 ELSE 0 END) AS pending,
                SUM(CASE WHEN status='running' THEN 1 ELSE 0 END) AS running,
                SUM(CASE WHEN status='succeeded' THEN 1 ELSE 0 END) AS succeeded,
                SUM(CASE WHEN status='failed' THEN 1 ELSE 0 END) AS failed,
                SUM(CASE WHEN status='pending' AND available_at<=?
                         THEN 1 ELSE 0 END) AS due,
                SUM(CASE WHEN status='running' AND locked_at<=?
                         THEN 1 ELSE 0 END) AS stale_running,
                SUM(CASE WHEN status='failed' AND finished_at>=?
                         THEN 1 ELSE 0 END) AS failed_24h,
                SUM(CASE WHEN status='pending' AND last_error!=''
                         THEN 1 ELSE 0 END) AS retry_pending,
                MIN(CASE WHEN status='pending' AND available_at<=?
                         THEN created_at ELSE NULL END) AS oldest_due_at
            FROM background_jobs
        """, (
            now_text,
            stale_cutoff,
            failure_cutoff,
            now_text,
        )).fetchone()
    finally:
        connection.close()

    counts = {
        key: int(row[key] or 0)
        for key in (
            "pending",
            "running",
            "succeeded",
            "failed",
            "due",
            "stale_running",
            "failed_24h",
            "retry_pending",
        )
    }
    oldest_due_at = str(row["oldest_due_at"] or "")
    oldest_due_minutes = 0
    if oldest_due_at:
        try:
            oldest_due = datetime.strptime(
                oldest_due_at[:19],
                "%Y-%m-%d %H:%M:%S",
            )
            oldest_due_minutes = max(
                0,
                int((now_value - oldest_due).total_seconds() / 60),
            )
        except ValueError:
            oldest_due_minutes = 0

    if counts["stale_running"] or counts["failed_24h"]:
        status = "critical"
        status_label = "Требует внимания"
        message = (
            "Есть зависшие или окончательно завершившиеся ошибкой задания."
        )
    elif counts["retry_pending"]:
        status = "warning"
        status_label = "Ожидает повтора"
        message = "Часть заданий ожидает следующей попытки после ошибки."
    elif oldest_due_minutes >= policy["warning_minutes"]:
        status = "warning"
        status_label = "Есть задержка"
        message = "Ожидающее задание не забрано worker вовремя."
    else:
        status = "ok"
        status_label = "Работает"
        message = "Очередь выполняется без критичных задержек."

    return {
        **counts,
        "status": status,
        "status_label": status_label,
        "message": message,
        "oldest_due_at": oldest_due_at,
        "oldest_due_minutes": oldest_due_minutes,
        "policy": policy,
    }
