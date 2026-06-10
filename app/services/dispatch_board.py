from datetime import timedelta


def build_dispatch_board(
    tasks,
    week_start,
    conflict_task_ids=None,
    day_capacity=None,
):
    conflict_task_ids = set(conflict_task_ids or [])
    day_capacity = day_capacity or {}
    columns = [{
        "date": "",
        "date_label": "Без даты",
        "day_label": "Очередь",
        "is_backlog": True,
        "is_today": False,
        "tasks": [],
        "assignment_count": 0,
        "capacity": 0,
        "available_slots": 0,
    }]
    columns.extend(
        {
            "date": (week_start + timedelta(days=offset)).strftime(
                "%Y-%m-%d"
            ),
            "date_label": (week_start + timedelta(days=offset)).strftime(
                "%d.%m"
            ),
            "day_label": [
                "Понедельник",
                "Вторник",
                "Среда",
                "Четверг",
                "Пятница",
                "Суббота",
                "Воскресенье",
            ][offset],
            "is_backlog": False,
            "is_today": False,
            "tasks": [],
            "assignment_count": day_capacity.get(
                (week_start + timedelta(days=offset)).strftime(
                    "%Y-%m-%d"
                ),
                {},
            ).get("assignments", 0),
            "capacity": day_capacity.get(
                (week_start + timedelta(days=offset)).strftime(
                    "%Y-%m-%d"
                ),
                {},
            ).get("capacity", 0),
            "available_slots": day_capacity.get(
                (week_start + timedelta(days=offset)).strftime(
                    "%Y-%m-%d"
                ),
                {},
            ).get("available_slots", 0),
        }
        for offset in range(7)
    )
    column_map = {
        column["date"]: column
        for column in columns
    }

    for task in tasks:
        task_date = str(task["task_date"] or "")[:10]
        target_column = column_map.get(task_date, column_map[""])
        worker_names = []

        for field in ("worker", "workers"):
            for worker_name in str(task[field] or "").split(","):
                worker_name = worker_name.strip()

                if worker_name and worker_name not in worker_names:
                    worker_names.append(worker_name)

        target_column["tasks"].append({
            "task": task,
            "workers": worker_names,
            "workers_label": ", ".join(worker_names) or "Не назначены",
            "has_conflict": task["id"] in conflict_task_ids,
        })

    for column in columns:
        column["tasks"].sort(key=lambda item: (
            0 if item["has_conflict"] else 1,
            0 if item["task"]["priority"] == "Срочно" else 1,
            item["task"]["id"],
        ))

    return columns
