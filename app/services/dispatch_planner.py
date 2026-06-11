from datetime import datetime

from app.services.daily_schedule import find_common_time_slot
from app.services.smart_scheduling import build_scheduling_recommendations


def _value(item, key, default=""):
    try:
        return item[key]
    except (KeyError, TypeError, IndexError):
        return default


def _task_workers(task):
    worker_names = []

    for field in ("worker", "workers"):
        for worker_name in str(_value(task, field) or "").split(","):
            worker_name = worker_name.strip()

            if worker_name and worker_name not in worker_names:
                worker_names.append(worker_name)

    return worker_names


def _priority_rank(task):
    priority = str(_value(task, "priority") or "").strip().lower()

    if priority in ("срочно", "emergency", "urgent"):
        return 0

    if priority in ("высокий", "high"):
        return 1

    return 2


def _priority_label(task):
    priority = str(_value(task, "priority") or "").strip()
    normalized = priority.lower()

    if normalized in ("срочно", "emergency", "urgent"):
        return "Срочно"

    if normalized in ("высокий", "high"):
        return "Высокий"

    if normalized in ("", "normal", "обычный"):
        return "Обычный"

    return priority


def build_dispatch_plan(
    tasks,
    worker_capacities,
    assignments,
    unavailable_dates,
    start_date,
    search_days=14,
    limit=25,
):
    search_days = max(1, min(int(search_days or 14), 30))
    limit = max(1, min(int(limit or 25), 50))
    simulated_assignments = [
        {
            "date": str(item.get("date") or "")[:10],
            "workers": list(item.get("workers") or []),
            "time_from": str(item.get("time_from") or "")[:5],
            "time_to": str(item.get("time_to") or "")[:5],
        }
        for item in assignments
    ]
    eligible_tasks = []

    for task in tasks:
        task_date = str(_value(task, "task_date") or "")[:10]
        worker_names = _task_workers(task)

        if task_date and worker_names:
            continue

        eligible_tasks.append(task)

    eligible_tasks.sort(key=lambda task: (
        _priority_rank(task),
        0 if str(_value(task, "task_date") or "")[:10] else 1,
        str(_value(task, "created_at") or ""),
        int(_value(task, "id", 0) or 0),
    ))
    plan_items = []
    unscheduled_items = []

    for task in eligible_tasks[:limit]:
        task_id = int(_value(task, "id", 0) or 0)
        current_date = str(_value(task, "task_date") or "")[:10]
        current_workers = _task_workers(task)
        valid_current_workers = [
            worker_name
            for worker_name in current_workers
            if worker_name in worker_capacities
        ]
        inactive_workers = [
            worker_name
            for worker_name in current_workers
            if worker_name not in worker_capacities
        ]
        required_workers = max(len(current_workers), 1)
        fixed_workers = (
            valid_current_workers
            if current_workers and not inactive_workers
            else None
        )
        task_start_date = start_date
        task_search_days = search_days

        if current_date:
            try:
                task_start_date = datetime.strptime(
                    current_date,
                    "%Y-%m-%d",
                ).date()
            except ValueError:
                task_start_date = start_date

            if task_start_date < start_date:
                unscheduled_items.append({
                    "task_id": task_id,
                    "client": str(_value(task, "client") or ""),
                    "priority": _priority_label(task),
                    "current_date": current_date,
                    "current_workers": current_workers,
                    "reason": "Дата заявки уже прошла.",
                })
                continue

            task_search_days = 1

        recommendation = build_scheduling_recommendations(
            worker_capacities=worker_capacities,
            assignments=simulated_assignments,
            start_date=task_start_date,
            search_days=task_search_days,
            required_workers=required_workers,
            fixed_workers=fixed_workers,
            unavailable_dates=unavailable_dates,
            limit=1,
        )

        if not recommendation["items"]:
            reason = "В выбранном периоде нет свободного окна."

            if current_date:
                reason = "На дату заявки нет свободной команды."
            elif fixed_workers:
                reason = "У назначенной команды нет общего свободного дня."

            unscheduled_items.append({
                "task_id": task_id,
                "client": str(_value(task, "client") or ""),
                "priority": _priority_label(task),
                "current_date": current_date,
                "current_workers": current_workers,
                "reason": reason,
            })
            continue

        best = recommendation["items"][0]
        target_workers = best["worker_names"]
        time_slot = find_common_time_slot(
            assignments=simulated_assignments,
            target_date=best["date"],
            target_workers=target_workers,
        )

        if not time_slot:
            unscheduled_items.append({
                "task_id": task_id,
                "client": str(_value(task, "client") or ""),
                "priority": _priority_label(task),
                "current_date": current_date,
                "current_workers": current_workers,
                "reason": "В рабочем дне нет общего часового окна.",
            })
            continue

        if not current_date and not current_workers:
            change_type = "full"
            change_label = "Дата и команда"
        elif not current_date:
            change_type = "date"
            change_label = "Назначить дату"
        else:
            change_type = "team"
            change_label = (
                "Заменить команду"
                if inactive_workers
                else "Назначить команду"
            )

        plan_items.append({
            "task_id": task_id,
            "client": str(_value(task, "client") or ""),
            "description": str(_value(task, "description") or ""),
            "priority": _priority_label(task),
            "current_date": current_date,
            "current_workers": current_workers,
            "expected_workers": ",".join(current_workers),
            "target_date": best["date"],
            "target_date_label": best["date_label"],
            "target_workers": target_workers,
            "target_workers_csv": ",".join(target_workers),
            "target_time_from": time_slot["time_from"],
            "target_time_to": time_slot["time_to"],
            "target_time_label": (
                f"{time_slot['time_from']}–{time_slot['time_to']}"
            ),
            "change_type": change_type,
            "change_label": change_label,
            "score": best["score"],
            "reason": best["reason"],
            "average_load_percent": best["average_load_percent"],
            "available_after": best["available_after"],
        })
        simulated_assignments.append({
            "date": best["date"],
            "workers": target_workers,
            "time_from": time_slot["time_from"],
            "time_to": time_slot["time_to"],
        })

    return {
        "items": plan_items,
        "unscheduled": unscheduled_items,
        "summary": {
            "eligible": len(eligible_tasks),
            "planned": len(plan_items),
            "unscheduled": len(unscheduled_items),
            "limited": max(len(eligible_tasks) - limit, 0),
            "search_days": search_days,
        },
    }
