import hashlib
import json
from datetime import datetime, timedelta

from app.services.daily_schedule import task_workers


REMINDER_COOLDOWN_MINUTES = 30


def _value(item, key, default=""):
    try:
        return item[key]
    except (KeyError, TypeError, IndexError):
        return default


def build_day_plan_snapshot(tasks):
    items = []
    worker_names = set()

    for task in tasks:
        workers = sorted(set(task_workers(task)))
        worker_names.update(workers)
        items.append({
            "task_id": int(_value(task, "id", 0) or 0),
            "task_date": str(_value(task, "task_date") or "")[:10],
            "workers": workers,
            "time_from": str(_value(task, "time_from") or "")[:5],
            "time_to": str(_value(task, "time_to") or "")[:5],
        })

    items.sort(key=lambda item: item["task_id"])
    payload = json.dumps(
        items,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    return {
        "hash": hashlib.sha256(payload.encode("utf-8")).hexdigest(),
        "task_count": len(items),
        "worker_count": len(worker_names),
        "workers": sorted(worker_names),
    }


def build_day_publication_state(
    publication,
    tasks,
    acknowledgements=None,
    reminders=None,
    active_worker_names=None,
    current_username="",
):
    snapshot = build_day_plan_snapshot(tasks)
    active_worker_names = set(
        snapshot["workers"]
        if active_worker_names is None
        else active_worker_names
    )
    acknowledgement_rows = list(acknowledgements or [])
    acknowledgement_by_worker = {
        str(_value(row, "username") or ""): str(
            _value(row, "acknowledged_at") or ""
        )
        for row in acknowledgement_rows
        if str(_value(row, "username") or "")
    }
    reminder_by_worker = {
        str(_value(row, "username") or ""): str(
            _value(row, "reminded_at") or ""
        )
        for row in list(reminders or [])
        if str(_value(row, "username") or "")
    }

    if not publication:
        return {
            **snapshot,
            "state": "draft",
            "tone": "draft",
            "title": "План не опубликован",
            "message": "Исполнители ещё не получили подтверждённый план.",
            "published_by": "",
            "published_at": "",
            "revision": 0,
            "acknowledged_count": 0,
            "pending_count": snapshot["worker_count"],
            "acknowledgements": [],
            "current_user_assigned": (
                current_username in snapshot["workers"]
            ),
            "current_user_acknowledged": False,
            "current_user_acknowledged_at": "",
            "remindable_count": 0,
            "reminder_cooldown_count": 0,
            "inactive_pending_count": 0,
            "last_reminded_at": "",
        }

    published_hash = str(_value(publication, "plan_hash") or "")
    is_current = published_hash == snapshot["hash"]

    if is_current:
        state = "published"
        tone = "published"
        title = "План опубликован"
        message = "Текущая версия подтверждена для исполнителей."
    else:
        state = "changed"
        tone = "changed"
        title = "После публикации есть изменения"
        message = "Обновите публикацию, чтобы команда увидела актуальный план."

    cooldown_threshold = datetime.now() - timedelta(
        minutes=REMINDER_COOLDOWN_MINUTES
    )
    acknowledgement_items = []

    for worker_name in snapshot["workers"]:
        worker_is_active = worker_name in active_worker_names
        acknowledged = (
            state == "published"
            and worker_name in acknowledgement_by_worker
        )
        reminded_at = reminder_by_worker.get(worker_name, "")
        reminder_on_cooldown = False

        if state == "published" and not acknowledged and reminded_at:
            try:
                reminder_on_cooldown = (
                    datetime.strptime(
                        reminded_at,
                        "%Y-%m-%d %H:%M",
                    )
                    > cooldown_threshold
                )
            except ValueError:
                reminder_on_cooldown = False

        acknowledgement_items.append({
            "username": worker_name,
            "acknowledged": acknowledged,
            "acknowledged_at": (
                acknowledgement_by_worker.get(worker_name, "")
                if state == "published"
                else ""
            ),
            "reminded_at": (
                reminded_at if state == "published" else ""
            ),
            "reminder_on_cooldown": reminder_on_cooldown,
            "active": worker_is_active,
            "remindable": (
                state == "published"
                and not acknowledged
                and worker_is_active
                and not reminder_on_cooldown
            ),
        })
    acknowledged_count = sum(
        1 for item in acknowledgement_items
        if item["acknowledged"]
    )
    current_user_acknowledged_at = (
        acknowledgement_by_worker.get(current_username, "")
        if state == "published"
        else ""
    )
    remindable_count = sum(
        1 for item in acknowledgement_items if item["remindable"]
    )
    reminder_cooldown_count = sum(
        1
        for item in acknowledgement_items
        if not item["acknowledged"] and item["reminder_on_cooldown"]
    )
    inactive_pending_count = sum(
        1
        for item in acknowledgement_items
        if not item["acknowledged"] and not item["active"]
    )
    last_reminded_at = max(
        (
            item["reminded_at"]
            for item in acknowledgement_items
            if item["reminded_at"]
        ),
        default="",
    )

    return {
        **snapshot,
        "state": state,
        "tone": tone,
        "title": title,
        "message": message,
        "published_by": str(
            _value(publication, "published_by") or ""
        ),
        "published_at": str(
            _value(publication, "published_at") or ""
        ),
        "revision": int(_value(publication, "revision", 1) or 1),
        "published_task_count": int(
            _value(publication, "task_count", 0) or 0
        ),
        "published_worker_count": int(
            _value(publication, "worker_count", 0) or 0
        ),
        "acknowledged_count": acknowledged_count,
        "pending_count": max(
            snapshot["worker_count"] - acknowledged_count,
            0,
        ),
        "acknowledgements": acknowledgement_items,
        "current_user_assigned": current_username in snapshot["workers"],
        "current_user_acknowledged": bool(
            current_user_acknowledged_at
        ),
        "current_user_acknowledged_at": (
            current_user_acknowledged_at
        ),
        "remindable_count": remindable_count,
        "reminder_cooldown_count": reminder_cooldown_count,
        "inactive_pending_count": inactive_pending_count,
        "last_reminded_at": last_reminded_at,
        "reminder_cooldown_minutes": REMINDER_COOLDOWN_MINUTES,
    }
