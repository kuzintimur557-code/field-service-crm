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


def _interval_is_available(
    assignments,
    target_date,
    worker_name,
    start,
    end,
    exclude_task_id=0,
):
    for assignment in assignments:
        if (
            exclude_task_id
            and int(assignment.get("task_id") or 0)
            == int(exclude_task_id)
        ):
            continue

        if str(assignment.get("date") or "")[:10] != target_date:
            continue

        if worker_name not in (assignment.get("workers") or []):
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
            return False

    return True


def build_day_assignment_suggestions(
    task,
    tasks,
    worker_names,
    worker_capacities=None,
    unavailable_worker_names=None,
    limit=8,
):
    worker_capacities = dict(worker_capacities or {})
    unavailable_worker_names = set(unavailable_worker_names or [])
    task_id = int(_value(task, "id", 0) or 0)
    target_date = str(_value(task, "task_date") or "")[:10]

    if not target_date or task_workers(task):
        return []

    assignments = [
        {
            "task_id": int(_value(item, "id", 0) or 0),
            "date": str(_value(item, "task_date") or "")[:10],
            "workers": task_workers(item),
            "time_from": str(_value(item, "time_from") or "")[:5],
            "time_to": str(_value(item, "time_to") or "")[:5],
        }
        for item in tasks
        if _task_blocks_time(item)
    ]
    duration_minutes = task_duration_minutes(task)
    current_start = parse_time_value(_value(task, "time_from"))
    current_end = parse_time_value(_value(task, "time_to"))
    suggestions = []

    for worker_name in dict.fromkeys(worker_names or []):
        if worker_name in unavailable_worker_names:
            continue

        daily_capacity = max(
            1,
            int(worker_capacities.get(worker_name) or 3),
        )
        active_count = sum(
            1
            for item in tasks
            if (
                _task_blocks_time(item)
                and worker_name in task_workers(item)
                and int(_value(item, "id", 0) or 0) != task_id
            )
        )

        if active_count >= daily_capacity:
            continue

        timeline = build_worker_timeline(tasks, worker_name)
        selected_slot = None
        keeps_current_time = bool(
            current_start is not None
            and current_end is not None
            and WORKDAY_START <= current_start < current_end <= WORKDAY_END
            and _interval_is_available(
                assignments,
                target_date,
                worker_name,
                current_start,
                current_end,
                exclude_task_id=task_id,
            )
        )

        if keeps_current_time:
            selected_slot = {
                "time_from": format_time_value(current_start),
                "time_to": format_time_value(current_end),
                "label": (
                    f"{format_time_value(current_start)}–"
                    f"{format_time_value(current_end)}"
                ),
            }
        else:
            available_slots = list_common_time_slots(
                assignments=assignments,
                target_date=target_date,
                target_workers=[worker_name],
                duration_minutes=duration_minutes,
                exclude_task_id=task_id,
            )

            if available_slots:
                selected_slot = available_slots[0]

        if not selected_slot:
            continue

        load_percent = round(active_count / daily_capacity * 100)
        utilization_percent = timeline["utilization_percent"]
        slot_start = parse_time_value(selected_slot["time_from"])
        start_penalty = max(
            ((slot_start or WORKDAY_START) - WORKDAY_START) // SLOT_STEP,
            0,
        )
        score = max(
            0,
            100
            - round(load_percent * 0.45)
            - round(utilization_percent * 0.25)
            - start_penalty,
        )

        if keeps_current_time:
            reason = "Текущее время свободно"
        elif active_count == 0:
            reason = "Исполнитель свободен"
        elif load_percent <= 50:
            reason = "Низкая загрузка"
        else:
            reason = "Есть свободное окно"

        suggestions.append({
            "worker": worker_name,
            "time_from": selected_slot["time_from"],
            "time_to": selected_slot["time_to"],
            "time_label": selected_slot["label"],
            "duration_minutes": duration_minutes,
            "active_count": active_count,
            "daily_capacity": daily_capacity,
            "load_percent": load_percent,
            "utilization_percent": utilization_percent,
            "score": score,
            "reason": reason,
            "keeps_current_time": keeps_current_time,
        })

    suggestions.sort(key=lambda item: (
        -item["score"],
        item["load_percent"],
        item["utilization_percent"],
        item["time_from"],
        item["worker"],
    ))
    return suggestions[:max(1, int(limit or 8))]


def _priority_rank(task):
    priority = str(_value(task, "priority") or "").strip().lower()

    if priority in ("срочно", "urgent", "emergency"):
        return 0

    if priority in ("высокий", "high"):
        return 1

    return 2


def build_daily_auto_plan(
    tasks,
    worker_names,
    worker_capacities=None,
    unavailable_worker_names=None,
    target_date="",
    limit=50,
):
    tasks = list(tasks)
    worker_names = list(dict.fromkeys(worker_names or []))
    worker_capacities = {
        worker_name: max(
            1,
            int((worker_capacities or {}).get(worker_name) or 3),
        )
        for worker_name in worker_names
    }
    unavailable_worker_names = set(unavailable_worker_names or [])
    active_tasks = [
        task for task in tasks if _task_blocks_time(task)
    ]
    target_date = str(target_date or "")[:10] or next(
        (
            str(_value(task, "task_date") or "")[:10]
            for task in active_tasks
            if str(_value(task, "task_date") or "")[:10]
        ),
        "",
    )
    assignments = [
        {
            "task_id": int(_value(task, "id", 0) or 0),
            "date": str(_value(task, "task_date") or "")[:10],
            "workers": task_workers(task),
            "time_from": str(_value(task, "time_from") or "")[:5],
            "time_to": str(_value(task, "time_to") or "")[:5],
        }
        for task in active_tasks
        if task_workers(task)
        and parse_time_value(_value(task, "time_from")) is not None
        and parse_time_value(_value(task, "time_to")) is not None
    ]
    worker_counts = {
        worker_name: sum(
            1
            for task in active_tasks
            if worker_name in task_workers(task)
        )
        for worker_name in worker_names
    }
    eligible_tasks = [
        task
        for task in active_tasks
        if (
            not task_workers(task)
            or parse_time_value(_value(task, "time_from")) is None
            or parse_time_value(_value(task, "time_to")) is None
        )
    ]
    eligible_tasks.sort(key=lambda task: (
        _priority_rank(task),
        0
        if (
            parse_time_value(_value(task, "time_from")) is not None
            and parse_time_value(_value(task, "time_to")) is not None
        )
        else 1,
        int(_value(task, "id", 0) or 0),
    ))
    plan_items = []
    unscheduled = []

    plan_limit = max(1, min(int(limit or 50), 50))

    for task in eligible_tasks[:plan_limit]:
        task_id = int(_value(task, "id", 0) or 0)
        current_workers = task_workers(task)
        current_time_from = str(_value(task, "time_from") or "")[:5]
        current_time_to = str(_value(task, "time_to") or "")[:5]
        current_start = parse_time_value(current_time_from)
        current_end = parse_time_value(current_time_to)
        duration_minutes = task_duration_minutes(task)
        target_workers = list(current_workers)
        target_slot = None
        reason = ""
        score = 0

        if current_workers:
            inactive_workers = [
                worker_name
                for worker_name in current_workers
                if worker_name not in worker_capacities
            ]

            if inactive_workers:
                unscheduled.append({
                    "task_id": task_id,
                    "client": str(_value(task, "client") or ""),
                    "reason": (
                        "Исполнитель отключён: "
                        + ", ".join(inactive_workers)
                    ),
                })
                continue

            unavailable_workers = [
                worker_name
                for worker_name in current_workers
                if worker_name in unavailable_worker_names
            ]

            if unavailable_workers:
                unscheduled.append({
                    "task_id": task_id,
                    "client": str(_value(task, "client") or ""),
                    "reason": (
                        "Исполнитель недоступен: "
                        + ", ".join(unavailable_workers)
                    ),
                })
                continue

            overloaded_workers = [
                worker_name
                for worker_name in current_workers
                if (
                    worker_counts.get(worker_name, 0) - 1
                    >= worker_capacities[worker_name]
                )
            ]

            if overloaded_workers:
                unscheduled.append({
                    "task_id": task_id,
                    "client": str(_value(task, "client") or ""),
                    "reason": (
                        "Дневной лимит заполнен: "
                        + ", ".join(overloaded_workers)
                    ),
                })
                continue

            available_slots = list_common_time_slots(
                assignments=assignments,
                target_date=target_date,
                target_workers=current_workers,
                duration_minutes=duration_minutes,
                exclude_task_id=task_id,
            )

            if available_slots:
                target_slot = available_slots[0]
                reason = "Найдено общее окно команды"
                score = 100 - min(
                    (
                        parse_time_value(target_slot["time_from"])
                        or WORKDAY_START
                    ) - WORKDAY_START,
                    600,
                ) // SLOT_STEP
        else:
            candidates = []

            for worker_name in worker_names:
                if worker_name in unavailable_worker_names:
                    continue

                daily_capacity = worker_capacities[worker_name]
                active_count = worker_counts.get(worker_name, 0)

                if active_count >= daily_capacity:
                    continue

                keeps_current_time = bool(
                    current_start is not None
                    and current_end is not None
                    and WORKDAY_START
                    <= current_start
                    < current_end
                    <= WORKDAY_END
                    and _interval_is_available(
                        assignments,
                        target_date,
                        worker_name,
                        current_start,
                        current_end,
                        exclude_task_id=task_id,
                    )
                )

                if keeps_current_time:
                    slot = {
                        "time_from": format_time_value(current_start),
                        "time_to": format_time_value(current_end),
                        "label": (
                            f"{format_time_value(current_start)}–"
                            f"{format_time_value(current_end)}"
                        ),
                    }
                else:
                    slots = list_common_time_slots(
                        assignments=assignments,
                        target_date=target_date,
                        target_workers=[worker_name],
                        duration_minutes=duration_minutes,
                        exclude_task_id=task_id,
                    )
                    slot = slots[0] if slots else None

                if not slot:
                    continue

                load_after = (active_count + 1) / daily_capacity
                slot_start = (
                    parse_time_value(slot["time_from"])
                    or WORKDAY_START
                )
                candidate_score = max(
                    0,
                    round(
                        100
                        - load_after * 55
                        - (
                            (slot_start - WORKDAY_START)
                            / SLOT_STEP
                        )
                        + (10 if keeps_current_time else 0)
                    ),
                )
                candidates.append({
                    "worker": worker_name,
                    "slot": slot,
                    "active_count": active_count,
                    "daily_capacity": daily_capacity,
                    "keeps_current_time": keeps_current_time,
                    "score": candidate_score,
                })

            candidates.sort(key=lambda item: (
                -item["score"],
                item["active_count"] / item["daily_capacity"],
                item["slot"]["time_from"],
                item["worker"],
            ))

            if candidates:
                best = candidates[0]
                target_workers = [best["worker"]]
                target_slot = best["slot"]
                score = best["score"]
                reason = (
                    "Сохранено текущее время"
                    if best["keeps_current_time"]
                    else "Минимальная загрузка и ближайшее окно"
                )

        if not target_workers or not target_slot:
            unscheduled.append({
                "task_id": task_id,
                "client": str(_value(task, "client") or ""),
                "reason": (
                    "Нет общего свободного окна."
                    if current_workers
                    else "Нет доступного исполнителя и свободного окна."
                ),
            })
            continue

        if not current_workers:
            for worker_name in target_workers:
                worker_counts[worker_name] = (
                    worker_counts.get(worker_name, 0) + 1
                )

        assignments.append({
            "task_id": task_id,
            "date": target_date,
            "workers": target_workers,
            "time_from": target_slot["time_from"],
            "time_to": target_slot["time_to"],
        })
        plan_items.append({
            "task_id": task_id,
            "client": str(_value(task, "client") or ""),
            "priority": str(
                _value(task, "priority") or "Обычный"
            ),
            "current_date": target_date,
            "expected_workers": ",".join(current_workers),
            "expected_time_from": current_time_from,
            "expected_time_to": current_time_to,
            "target_date": target_date,
            "target_workers": target_workers,
            "target_workers_csv": ",".join(target_workers),
            "target_time_from": target_slot["time_from"],
            "target_time_to": target_slot["time_to"],
            "target_time_label": (
                f"{target_slot['time_from']}–"
                f"{target_slot['time_to']}"
            ),
            "change_type": (
                "time" if current_workers else "worker_and_time"
            ),
            "change_label": (
                "Назначить время"
                if current_workers
                else "Назначить исполнителя и время"
            ),
            "reason": reason,
            "score": score,
        })

    return {
        "items": plan_items,
        "unscheduled": unscheduled,
        "summary": {
            "eligible": len(eligible_tasks),
            "planned": len(plan_items),
            "unscheduled": len(unscheduled),
            "limited": max(len(eligible_tasks) - plan_limit, 0),
        },
    }


def build_daily_conflict_repair_plan(
    tasks,
    worker_names,
    unavailable_worker_names=None,
    target_date="",
    limit=50,
):
    tasks = [
        task
        for task in tasks
        if (
            _task_blocks_time(task)
            and task_workers(task)
            and parse_time_value(_value(task, "time_from")) is not None
            and parse_time_value(_value(task, "time_to")) is not None
        )
    ]
    worker_names = set(worker_names or [])
    unavailable_worker_names = set(unavailable_worker_names or [])
    target_date = str(target_date or "")[:10]
    ordered_tasks = sorted(tasks, key=lambda task: (
        _priority_rank(task),
        parse_time_value(_value(task, "time_from")) or WORKDAY_END,
        int(_value(task, "id", 0) or 0),
    ))
    fixed_tasks = []
    moving_tasks = []
    conflict_ids_by_task = {}

    for task in ordered_tasks:
        task_id = int(_value(task, "id", 0) or 0)
        start = parse_time_value(_value(task, "time_from"))
        end = parse_time_value(_value(task, "time_to"))
        workers = set(task_workers(task))
        conflicts = []

        for fixed_task in fixed_tasks:
            fixed_workers = set(task_workers(fixed_task))

            if not workers.intersection(fixed_workers):
                continue

            fixed_start = parse_time_value(
                _value(fixed_task, "time_from")
            )
            fixed_end = parse_time_value(_value(fixed_task, "time_to"))

            if time_windows_overlap(
                start,
                end,
                fixed_start,
                fixed_end,
            ):
                conflicts.append(
                    int(_value(fixed_task, "id", 0) or 0)
                )

        if conflicts:
            moving_tasks.append(task)
            conflict_ids_by_task[task_id] = sorted(set(conflicts))
        else:
            fixed_tasks.append(task)

    if not moving_tasks:
        return {
            "items": [],
            "unscheduled": [],
            "summary": {
                "conflict_tasks": 0,
                "planned": 0,
                "unscheduled": 0,
                "limited": 0,
            },
        }

    assignments = [
        {
            "task_id": int(_value(task, "id", 0) or 0),
            "date": str(_value(task, "task_date") or "")[:10],
            "workers": task_workers(task),
            "time_from": str(_value(task, "time_from") or "")[:5],
            "time_to": str(_value(task, "time_to") or "")[:5],
        }
        for task in fixed_tasks
    ]
    plan_limit = max(1, min(int(limit or 50), 50))
    plan_items = []
    unscheduled = []

    for task in moving_tasks[:plan_limit]:
        task_id = int(_value(task, "id", 0) or 0)
        current_workers = task_workers(task)
        current_time_from = str(_value(task, "time_from") or "")[:5]
        current_time_to = str(_value(task, "time_to") or "")[:5]
        original_start = (
            parse_time_value(current_time_from) or WORKDAY_START
        )
        inactive_workers = [
            worker_name
            for worker_name in current_workers
            if worker_name not in worker_names
        ]

        if inactive_workers:
            unscheduled.append({
                "task_id": task_id,
                "client": str(_value(task, "client") or ""),
                "reason": (
                    "Исполнитель отключён: "
                    + ", ".join(inactive_workers)
                ),
            })
            continue

        blocked_workers = [
            worker_name
            for worker_name in current_workers
            if worker_name in unavailable_worker_names
        ]

        if blocked_workers:
            unscheduled.append({
                "task_id": task_id,
                "client": str(_value(task, "client") or ""),
                "reason": (
                    "Исполнитель недоступен: "
                    + ", ".join(blocked_workers)
                ),
            })
            continue

        available_slots = list_common_time_slots(
            assignments=assignments,
            target_date=target_date,
            target_workers=current_workers,
            duration_minutes=task_duration_minutes(task),
            exclude_task_id=task_id,
        )

        if not available_slots:
            unscheduled.append({
                "task_id": task_id,
                "client": str(_value(task, "client") or ""),
                "reason": "В рабочем дне нет общего свободного окна.",
            })
            continue

        available_slots.sort(key=lambda slot: (
            abs(
                (
                    parse_time_value(slot["time_from"])
                    or WORKDAY_START
                ) - original_start
            ),
            0
            if (
                parse_time_value(slot["time_from"])
                or WORKDAY_START
            ) >= original_start
            else 1,
            slot["time_from"],
        ))
        target_slot = available_slots[0]
        target_start = (
            parse_time_value(target_slot["time_from"])
            or WORKDAY_START
        )
        shift_minutes = abs(target_start - original_start)
        conflict_ids = conflict_ids_by_task.get(task_id, [])
        assignments.append({
            "task_id": task_id,
            "date": target_date,
            "workers": current_workers,
            "time_from": target_slot["time_from"],
            "time_to": target_slot["time_to"],
        })
        plan_items.append({
            "task_id": task_id,
            "client": str(_value(task, "client") or ""),
            "priority": str(
                _value(task, "priority") or "Обычный"
            ),
            "current_date": target_date,
            "expected_workers": ",".join(current_workers),
            "expected_time_from": current_time_from,
            "expected_time_to": current_time_to,
            "target_date": target_date,
            "target_workers": current_workers,
            "target_workers_csv": ",".join(current_workers),
            "target_time_from": target_slot["time_from"],
            "target_time_to": target_slot["time_to"],
            "target_time_label": (
                f"{target_slot['time_from']}–"
                f"{target_slot['time_to']}"
            ),
            "old_time_label": (
                f"{current_time_from}–{current_time_to}"
            ),
            "conflict_task_ids": conflict_ids,
            "conflict_label": ", ".join(
                f"#{conflict_id}" for conflict_id in conflict_ids
            ),
            "change_label": "Устранить пересечение",
            "reason": (
                f"Перенос на {shift_minutes} мин. от исходного времени"
            ),
            "score": max(0, 100 - shift_minutes // SLOT_STEP * 5),
        })

    return {
        "items": plan_items,
        "unscheduled": unscheduled,
        "summary": {
            "conflict_tasks": len(moving_tasks),
            "planned": len(plan_items),
            "unscheduled": len(unscheduled),
            "limited": max(len(moving_tasks) - plan_limit, 0),
        },
    }


def build_day_readiness(
    tasks,
    worker_names=None,
    worker_capacities=None,
    unavailable_worker_names=None,
):
    active_tasks = [
        task for task in tasks if _task_blocks_time(task)
    ]
    worker_names = set(worker_names or [])
    unavailable_worker_names = set(unavailable_worker_names or [])
    worker_capacities = {
        worker_name: max(
            1,
            int((worker_capacities or {}).get(worker_name) or 3),
        )
        for worker_name in worker_names
    }
    unassigned_ids = set()
    without_time_ids = set()
    conflict_ids = set()
    inactive_worker_task_ids = set()
    unavailable_worker_task_ids = set()
    worker_task_counts = {
        worker_name: 0 for worker_name in worker_names
    }

    for task in active_tasks:
        task_id = int(_value(task, "id", 0) or 0)
        workers = task_workers(task)
        start = parse_time_value(_value(task, "time_from"))
        end = parse_time_value(_value(task, "time_to"))

        if not workers:
            unassigned_ids.add(task_id)

        if start is None or end is None or start >= end:
            without_time_ids.add(task_id)

        if any(worker not in worker_names for worker in workers):
            inactive_worker_task_ids.add(task_id)

        if any(
            worker in unavailable_worker_names for worker in workers
        ):
            unavailable_worker_task_ids.add(task_id)

        for worker in set(workers).intersection(worker_names):
            worker_task_counts[worker] += 1

    for index, task in enumerate(active_tasks):
        task_id = int(_value(task, "id", 0) or 0)
        task_worker_names = set(task_workers(task))
        start = parse_time_value(_value(task, "time_from"))
        end = parse_time_value(_value(task, "time_to"))

        if not task_worker_names or start is None or end is None:
            continue

        for other in active_tasks[index + 1:]:
            other_workers = set(task_workers(other))

            if not task_worker_names.intersection(other_workers):
                continue

            other_start = parse_time_value(
                _value(other, "time_from")
            )
            other_end = parse_time_value(_value(other, "time_to"))

            if other_start is None or other_end is None:
                continue

            if time_windows_overlap(
                start,
                end,
                other_start,
                other_end,
            ):
                conflict_ids.add(task_id)
                conflict_ids.add(
                    int(_value(other, "id", 0) or 0)
                )

    overloaded_workers = sorted(
        worker_name
        for worker_name, task_count in worker_task_counts.items()
        if task_count > worker_capacities[worker_name]
    )
    issue_counts = {
        "conflicts": len(conflict_ids),
        "unassigned": len(unassigned_ids),
        "without_time": len(without_time_ids),
        "inactive_workers": len(inactive_worker_task_ids),
        "unavailable_workers": len(unavailable_worker_task_ids),
        "overloaded_workers": len(overloaded_workers),
    }
    score = max(
        0,
        100
        - min(issue_counts["conflicts"] * 20, 40)
        - min(issue_counts["unassigned"] * 15, 30)
        - min(issue_counts["without_time"] * 10, 20)
        - min(issue_counts["inactive_workers"] * 15, 30)
        - min(issue_counts["unavailable_workers"] * 15, 30)
        - min(issue_counts["overloaded_workers"] * 10, 20),
    )

    if not active_tasks:
        status = "День свободен"
        tone = "ready"
        headline = "Активных заявок нет."
    elif score >= 90:
        status = "Готово"
        tone = "ready"
        headline = "Расписание готово к работе."
    elif score >= 65:
        status = "Требует внимания"
        tone = "warning"
        headline = "Перед началом дня проверьте замечания."
    else:
        status = "Критично"
        tone = "critical"
        headline = "Расписание нужно исправить до начала работ."

    issues = []

    def add_issue(code, count, title, detail, target):
        if count:
            issues.append({
                "code": code,
                "count": count,
                "title": title,
                "detail": detail,
                "target": target,
            })

    add_issue(
        "conflicts",
        issue_counts["conflicts"],
        "Пересечения по времени",
        "Несколько заявок назначены одному исполнителю одновременно.",
        "#conflict-repair",
    )
    add_issue(
        "unassigned",
        issue_counts["unassigned"],
        "Нет исполнителя",
        "Заявки не попадут в рабочий маршрут команды.",
        "#auto-plan",
    )
    add_issue(
        "without_time",
        issue_counts["without_time"],
        "Не указано время",
        "Нельзя определить последовательность и загрузку.",
        "#auto-plan",
    )
    add_issue(
        "inactive_workers",
        issue_counts["inactive_workers"],
        "Назначен отключённый исполнитель",
        "Нужно заменить исполнителя в заявке.",
        "#day-routes",
    )
    add_issue(
        "unavailable_workers",
        issue_counts["unavailable_workers"],
        "Исполнитель недоступен",
        "У сотрудника отмечено отсутствие на выбранную дату.",
        "#day-routes",
    )
    add_issue(
        "overloaded_workers",
        issue_counts["overloaded_workers"],
        "Превышен дневной лимит",
        "Перегружены: " + ", ".join(overloaded_workers) + ".",
        "#day-routes",
    )

    checks = [
        {
            "label": "Исполнители назначены",
            "ok": not issue_counts["unassigned"],
            "count": issue_counts["unassigned"],
        },
        {
            "label": "Время указано",
            "ok": not issue_counts["without_time"],
            "count": issue_counts["without_time"],
        },
        {
            "label": "Нет пересечений",
            "ok": not issue_counts["conflicts"],
            "count": issue_counts["conflicts"],
        },
        {
            "label": "Команда доступна",
            "ok": not (
                issue_counts["inactive_workers"]
                or issue_counts["unavailable_workers"]
            ),
            "count": (
                issue_counts["inactive_workers"]
                + issue_counts["unavailable_workers"]
            ),
        },
        {
            "label": "Лимиты соблюдены",
            "ok": not issue_counts["overloaded_workers"],
            "count": issue_counts["overloaded_workers"],
        },
    ]

    return {
        "score": score,
        "status": status,
        "tone": tone,
        "headline": headline,
        "active_tasks": len(active_tasks),
        "issues": issues,
        "issue_counts": issue_counts,
        "checks": checks,
    }


def build_daily_schedule(
    tasks,
    worker_names=None,
    worker_capacities=None,
    unavailable_worker_names=None,
):
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
        item["assignment_suggestions"] = (
            build_day_assignment_suggestions(
                task=item["task"],
                tasks=tasks,
                worker_names=worker_names,
                worker_capacities=worker_capacities,
                unavailable_worker_names=unavailable_worker_names,
            )
            if _task_blocks_time(item["task"])
            else []
        )
        item["recommended_assignment"] = (
            item["assignment_suggestions"][0]
            if item["assignment_suggestions"]
            else None
        )
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
