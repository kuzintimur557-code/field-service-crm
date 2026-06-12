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


def build_week_publication_summary(
    week_start,
    tasks,
    publications=None,
    acknowledgements=None,
    reminders=None,
    active_worker_names=None,
):
    publication_by_date = {
        str(_value(row, "plan_date") or "")[:10]: row
        for row in list(publications or [])
    }
    tasks_by_date = {}

    for task in tasks:
        task_date = str(_value(task, "task_date") or "")[:10]

        if task_date:
            tasks_by_date.setdefault(task_date, []).append(task)

    acknowledgements_by_plan = {}

    for row in list(acknowledgements or []):
        key = (
            str(_value(row, "plan_date") or "")[:10],
            int(_value(row, "revision", 0) or 0),
        )
        acknowledgements_by_plan.setdefault(key, []).append(row)

    reminders_by_plan = {}

    for row in list(reminders or []):
        key = (
            str(_value(row, "plan_date") or "")[:10],
            int(_value(row, "revision", 0) or 0),
        )
        reminders_by_plan.setdefault(key, []).append(row)

    day_names = (
        "Понедельник",
        "Вторник",
        "Среда",
        "Четверг",
        "Пятница",
        "Суббота",
        "Воскресенье",
    )
    days = []

    for offset, day_name in enumerate(day_names):
        day_value = week_start + timedelta(days=offset)
        plan_date = day_value.strftime("%Y-%m-%d")
        publication = publication_by_date.get(plan_date)
        revision = int(_value(publication, "revision", 0) or 0)
        state = build_day_publication_state(
            publication,
            tasks_by_date.get(plan_date, []),
            acknowledgements=acknowledgements_by_plan.get(
                (plan_date, revision),
                [],
            ),
            reminders=reminders_by_plan.get(
                (plan_date, revision),
                [],
            ),
            active_worker_names=active_worker_names,
        )

        if not state["task_count"] and not publication:
            display_state = "empty"
            status_label = "Нет заявок"
        elif state["state"] == "changed":
            display_state = "changed"
            status_label = "План изменён"
        elif state["state"] == "draft":
            display_state = "draft"
            status_label = "Черновик"
        elif state["worker_count"] and not state["pending_count"]:
            display_state = "accepted"
            status_label = "План принят"
        elif state["pending_count"]:
            display_state = "waiting"
            status_label = "Ожидает принятия"
        else:
            display_state = "published"
            status_label = "Опубликован"

        days.append({
            **state,
            "date": plan_date,
            "date_label": day_value.strftime("%d.%m"),
            "day_label": day_name,
            "display_state": display_state,
            "status_label": status_label,
            "url": f"/calendar/day?date={plan_date}",
        })

    active_days = [day for day in days if day["task_count"]]
    published_days = [
        day for day in active_days
        if day["state"] == "published"
    ]

    return {
        "days": days,
        "summary": {
            "active_days": len(active_days),
            "draft_days": sum(
                1 for day in active_days if day["state"] == "draft"
            ),
            "published_days": len(published_days),
            "changed_days": sum(
                1 for day in active_days if day["state"] == "changed"
            ),
            "accepted_days": sum(
                1
                for day in published_days
                if day["worker_count"] and not day["pending_count"]
            ),
            "pending_acknowledgements": sum(
                day["pending_count"] for day in published_days
            ),
            "remindable_workers": sum(
                day["remindable_count"] for day in published_days
            ),
        },
    }
