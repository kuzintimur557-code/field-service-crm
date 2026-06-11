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


def task_duration_minutes(task, default=DEFAULT_DURATION):
    start = parse_time_value(_value(task, "time_from"))
    end = parse_time_value(_value(task, "time_to"))

    if start is None or end is None or start >= end:
        return int(default or DEFAULT_DURATION)

    return end - start


def _task_blocks_time(task):
    return str(_value(task, "status") or "") not in (
        "Завершено",
        "Отменено",
    )


def _merge_intervals(intervals):
    merged = []

    for start, end in sorted(intervals):
        if not merged or start > merged[-1][1]:
            merged.append([start, end])
            continue

        merged[-1][1] = max(merged[-1][1], end)

    return merged


def list_common_time_slots(
    assignments,
    target_date,
    target_workers,
    duration_minutes=DEFAULT_DURATION,
    workday_start=WORKDAY_START,
    workday_end=WORKDAY_END,
    step_minutes=SLOT_STEP,
    exclude_task_id=0,
):
    target_workers = list(dict.fromkeys(target_workers or []))

    if not target_workers:
        return []

    duration_minutes = max(
        step_minutes,
        int(duration_minutes or DEFAULT_DURATION),
    )
    target_date = str(target_date or "")[:10]
    available_slots = []

    for start in range(
        workday_start,
        workday_end - duration_minutes + 1,
        step_minutes,
    ):
        end = start + duration_minutes
        has_conflict = False

        for assignment in assignments:
            assignment_task_id = int(
                assignment.get("task_id") or 0
            )

            if (
                exclude_task_id
                and assignment_task_id == int(exclude_task_id)
            ):
                continue

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
            available_slots.append({
                "time_from": format_time_value(start),
                "time_to": format_time_value(end),
                "label": (
                    f"{format_time_value(start)}–"
                    f"{format_time_value(end)}"
                ),
                "duration_minutes": duration_minutes,
            })

    return available_slots


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
    slots = list_common_time_slots(
        assignments=assignments,
        target_date=target_date,
        target_workers=target_workers,
        duration_minutes=duration_minutes,
        workday_start=workday_start,
        workday_end=workday_end,
        step_minutes=step_minutes,
    )
    if not slots:
        return None

    return {
        "time_from": slots[0]["time_from"],
        "time_to": slots[0]["time_to"],
        "duration_minutes": slots[0]["duration_minutes"],
    }


def build_worker_timeline(
    tasks,
    worker_name,
    workday_start=WORKDAY_START,
    workday_end=WORKDAY_END,
    step_minutes=SLOT_STEP,
):
    busy_intervals = []
    timed_tasks = []

    for task in tasks:
        if worker_name not in task_workers(task):
            continue

        if not _task_blocks_time(task):
            continue

        start = parse_time_value(_value(task, "time_from"))
        end = parse_time_value(_value(task, "time_to"))

        if start is None or end is None:
            continue

        clipped_start = max(start, workday_start)
        clipped_end = min(end, workday_end)

        if clipped_start >= clipped_end:
            continue

        busy_intervals.append((clipped_start, clipped_end))
        timed_tasks.append({
            "task_id": int(_value(task, "id", 0) or 0),
            "start": clipped_start,
            "end": clipped_end,
        })

    merged_busy = _merge_intervals(busy_intervals)
    free_intervals = []
    cursor = workday_start

    for start, end in merged_busy:
        if cursor < start:
            free_intervals.append((cursor, start))

        cursor = max(cursor, end)

    if cursor < workday_end:
        free_intervals.append((cursor, workday_end))

    timeline_slots = []

    for start in range(workday_start, workday_end, step_minutes):
        end = min(start + step_minutes, workday_end)
        task_ids = sorted({
            item["task_id"]
            for item in timed_tasks
            if time_windows_overlap(
                start,
                end,
                item["start"],
                item["end"],
            )
        })
        status = (
            "conflict"
            if len(task_ids) > 1
            else "busy"
            if task_ids
            else "free"
        )
        timeline_slots.append({
            "time_from": format_time_value(start),
            "time_to": format_time_value(end),
            "label": format_time_value(start),
            "hour_label": (
                format_time_value(start)
                if start % 60 == 0
                else ""
            ),
            "status": status,
            "task_ids": task_ids,
            "task_count": len(task_ids),
        })

    busy_minutes = sum(end - start for start, end in merged_busy)
    workday_minutes = max(workday_end - workday_start, 1)

    return {
        "slots": timeline_slots,
        "free_windows": [
            {
                "time_from": format_time_value(start),
                "time_to": format_time_value(end),
                "label": (
                    f"{format_time_value(start)}–"
                    f"{format_time_value(end)}"
                ),
                "duration_minutes": end - start,
            }
            for start, end in free_intervals
        ],
        "busy_minutes": busy_minutes,
        "free_minutes": workday_minutes - busy_minutes,
        "utilization_percent": min(
            round(busy_minutes / workday_minutes * 100),
            100,
        ),
    }


def build_daily_schedule(tasks, worker_names=None):
    tasks = list(tasks)
    worker_names = list(dict.fromkeys(worker_names or []))
    assignments = [
        {
            "task_id": int(_value(task, "id", 0) or 0),
            "date": str(_value(task, "task_date") or "")[:10],
            "workers": task_workers(task),
            "time_from": str(_value(task, "time_from") or "")[:5],
            "time_to": str(_value(task, "time_to") or "")[:5],
        }
        for task in tasks
        if _task_blocks_time(task)
    ]
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
        duration_minutes = task_duration_minutes(task)
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
            "duration_minutes": duration_minutes,
            "has_time": bool(
                parse_time_value(_value(task, "time_from")) is not None
                and parse_time_value(_value(task, "time_to")) is not None
            ),
            "conflicts": [],
            "available_slots": list_common_time_slots(
                assignments=assignments,
                target_date=str(
                    _value(task, "task_date") or ""
                )[:10],
                target_workers=workers,
                duration_minutes=duration_minutes,
                exclude_task_id=int(_value(task, "id", 0) or 0),
            ) if workers and _task_blocks_time(task) else [],
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
        worker_schedule["timeline"] = build_worker_timeline(
            tasks,
            worker_schedule["username"],
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
