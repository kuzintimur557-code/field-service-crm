from datetime import datetime


WORKDAY_START = 8 * 60
WORKDAY_END = 20 * 60
DEFAULT_DURATION = 60
SLOT_STEP = 30


def _value(item, key, default=""):
    try:
        return item[key]
    except (KeyError, TypeError, IndexError):
        return default


def task_workers(task):
    worker_names = []

    for field in ("worker", "workers"):
        for worker_name in str(_value(task, field) or "").split(","):
            worker_name = worker_name.strip()

            if worker_name and worker_name not in worker_names:
                worker_names.append(worker_name)

    return worker_names


def parse_time_value(value):
    value = str(value or "").strip()[:5]

    if not value:
        return None

    try:
        parsed = datetime.strptime(value, "%H:%M")
    except ValueError:
        return None

    return parsed.hour * 60 + parsed.minute


def format_time_value(minutes):
    minutes = max(0, min(int(minutes), 23 * 60 + 59))
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def normalize_time_window(time_from, time_to):
    start = parse_time_value(time_from)
    end = parse_time_value(time_to)

    if start is None and end is None:
        return "", "", None

    if start is None or end is None:
        return "", "", "Укажите время начала и окончания."

    if start >= end:
        return "", "", "Время окончания должно быть позже начала."

    return format_time_value(start), format_time_value(end), None


def time_windows_overlap(start_a, end_a, start_b, end_b):
    return start_a < end_b and start_b < end_a


def find_time_conflicts(
    tasks,
    target_workers,
    time_from,
    time_to,
    exclude_task_id=0,
):
    start = parse_time_value(time_from)
    end = parse_time_value(time_to)

    if start is None or end is None:
        return []

    target_worker_set = set(target_workers or [])
    conflicts = []

    for task in tasks:
        task_id = int(_value(task, "id", 0) or 0)

        if exclude_task_id and task_id == int(exclude_task_id):
            continue

        shared_workers = sorted(
            target_worker_set.intersection(task_workers(task))
        )

        if not shared_workers:
            continue

        task_start = parse_time_value(_value(task, "time_from"))
        task_end = parse_time_value(_value(task, "time_to"))

        if task_start is None or task_end is None:
            continue

        if not time_windows_overlap(start, end, task_start, task_end):
            continue

        conflicts.append({
            "task_id": task_id,
            "client": str(_value(task, "client") or ""),
            "time_from": format_time_value(task_start),
            "time_to": format_time_value(task_end),
            "workers": shared_workers,
        })

    return conflicts


def find_common_time_slot(
    assignments,
    target_date,
    target_workers,
    duration_minutes=DEFAULT_DURATION,
    workday_start=WORKDAY_START,
    workday_end=WORKDAY_END,
    step_minutes=SLOT_STEP,
):
    target_workers = list(dict.fromkeys(target_workers or []))

    if not target_workers:
        return None

    duration_minutes = max(
        step_minutes,
        int(duration_minutes or DEFAULT_DURATION),
    )
    target_date = str(target_date or "")[:10]

    for start in range(
        workday_start,
        workday_end - duration_minutes + 1,
        step_minutes,
    ):
        end = start + duration_minutes
        has_conflict = False

        for assignment in assignments:
            if str(assignment.get("date") or "")[:10] != target_date:
                continue

            if not set(target_workers).intersection(
                assignment.get("workers") or []
            ):
                continue

            assignment_start = parse_time_value(
                assignment.get("time_from")
            )
            assignment_end = parse_time_value(
                assignment.get("time_to")
            )

            if assignment_start is None or assignment_end is None:
                continue

            if time_windows_overlap(
                start,
                end,
                assignment_start,
                assignment_end,
            ):
                has_conflict = True
                break

        if not has_conflict:
            return {
                "time_from": format_time_value(start),
                "time_to": format_time_value(end),
                "duration_minutes": duration_minutes,
            }

    return None


def build_daily_schedule(tasks, worker_names=None):
    worker_names = list(dict.fromkeys(worker_names or []))
    schedule_workers = {
        worker_name: {
            "username": worker_name,
            "items": [],
            "conflict_count": 0,
            "scheduled_count": 0,
            "unscheduled_count": 0,
        }
        for worker_name in worker_names
    }
    unassigned = []

    for task in tasks:
        workers = task_workers(task)
        item = {
            "task": task,
            "task_id": int(_value(task, "id", 0) or 0),
            "client": str(_value(task, "client") or ""),
            "address": str(_value(task, "address") or ""),
            "status": str(_value(task, "status") or ""),
            "priority": str(_value(task, "priority") or "Обычный"),
            "time_from": str(_value(task, "time_from") or "")[:5],
            "time_to": str(_value(task, "time_to") or "")[:5],
            "workers": workers,
            "has_time": bool(
                parse_time_value(_value(task, "time_from")) is not None
                and parse_time_value(_value(task, "time_to")) is not None
            ),
            "conflicts": [],
        }

        if not workers:
            unassigned.append(item)
            continue

        for worker_name in workers:
            schedule_workers.setdefault(worker_name, {
                "username": worker_name,
                "items": [],
                "conflict_count": 0,
                "scheduled_count": 0,
                "unscheduled_count": 0,
            })
            schedule_workers[worker_name]["items"].append({
                **item,
                "conflicts": [],
            })

    for worker_schedule in schedule_workers.values():
        items = worker_schedule["items"]

        for index, item in enumerate(items):
            if not item["has_time"]:
                continue

            start = parse_time_value(item["time_from"])
            end = parse_time_value(item["time_to"])

            for other in items[index + 1:]:
                if not other["has_time"]:
                    continue

                other_start = parse_time_value(other["time_from"])
                other_end = parse_time_value(other["time_to"])

                if not time_windows_overlap(
                    start,
                    end,
                    other_start,
                    other_end,
                ):
                    continue

                item["conflicts"].append(other["task_id"])
                other["conflicts"].append(item["task_id"])

        items.sort(key=lambda item: (
            0 if item["has_time"] else 1,
            parse_time_value(item["time_from"]) or WORKDAY_END + 1,
            0 if str(item["priority"]).lower() in ("срочно", "urgent") else 1,
            item["task_id"],
        ))
        worker_schedule["scheduled_count"] = sum(
            1 for item in items if item["has_time"]
        )
        worker_schedule["unscheduled_count"] = sum(
            1 for item in items if not item["has_time"]
        )
        worker_schedule["conflict_count"] = sum(
            1 for item in items if item["conflicts"]
        )

        for route_order, item in enumerate(items, start=1):
            item["route_order"] = route_order

    ordered_workers = sorted(
        schedule_workers.values(),
        key=lambda item: (
            -len(item["items"]),
            item["username"],
        ),
    )
    unique_items = {}

    for worker_schedule in ordered_workers:
        for item in worker_schedule["items"]:
            existing = unique_items.setdefault(item["task_id"], {
                **item,
                "conflicts": [],
            })
            existing["conflicts"] = sorted(set(
                existing["conflicts"] + item["conflicts"]
            ))

    for item in unassigned:
        unique_items.setdefault(item["task_id"], item)

    return {
        "workers": ordered_workers,
        "unassigned": unassigned,
        "summary": {
            "workers": len([
                item for item in ordered_workers if item["items"]
            ]),
            "tasks": len(unique_items),
            "scheduled": sum(
                1 for item in unique_items.values() if item["has_time"]
            ),
            "without_time": sum(
                1 for item in unique_items.values() if not item["has_time"]
            ),
            "conflicts": sum(
                1 for item in unique_items.values() if item["conflicts"]
            ),
            "unassigned": len(unassigned),
        },
    }
