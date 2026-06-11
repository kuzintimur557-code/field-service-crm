import hashlib
import json

from app.services.daily_schedule import task_workers


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
    current_username="",
):
    snapshot = build_day_plan_snapshot(tasks)
    acknowledgement_rows = list(acknowledgements or [])
    acknowledgement_by_worker = {
        str(_value(row, "username") or ""): str(
            _value(row, "acknowledged_at") or ""
        )
        for row in acknowledgement_rows
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

    acknowledgement_items = [
        {
            "username": worker_name,
            "acknowledged": (
                state == "published"
                and worker_name in acknowledgement_by_worker
            ),
            "acknowledged_at": (
                acknowledgement_by_worker.get(worker_name, "")
                if state == "published"
                else ""
            ),
        }
        for worker_name in snapshot["workers"]
    ]
    acknowledged_count = sum(
        1 for item in acknowledgement_items
        if item["acknowledged"]
    )
    current_user_acknowledged_at = (
        acknowledgement_by_worker.get(current_username, "")
        if state == "published"
        else ""
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
    }
