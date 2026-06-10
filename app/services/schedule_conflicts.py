from datetime import datetime

from app.services.smart_scheduling import build_scheduling_recommendations


def _task_workers(task):
    names = []

    for field in ("worker", "workers"):
        value = task.get(field, "") if isinstance(task, dict) else task[field]

        for name in str(value or "").split(","):
            name = name.strip()

            if name and name not in names:
                names.append(name)

    return names


def detect_schedule_conflicts(
    tasks,
    worker_capacities,
    unavailable_dates=None,
    unavailable_reasons=None,
):
    unavailable_dates = {
        worker_name: set(date_values or [])
        for worker_name, date_values in (unavailable_dates or {}).items()
    }
    unavailable_reasons = unavailable_reasons or {}
    assignments_by_worker_date = {}

    for task in tasks:
        task_date = str(task["task_date"] or "")[:10]

        for worker_name in _task_workers(task):
            key = (worker_name, task_date)
            assignments_by_worker_date.setdefault(key, []).append(task["id"])

    overloaded_task_ids = {}

    for key, task_ids in assignments_by_worker_date.items():
        worker_name = key[0]

        if worker_name not in worker_capacities:
            continue

        capacity = max(
            1,
            int(worker_capacities.get(worker_name, 1) or 1),
        )

        for task_id in task_ids[capacity:]:
            overloaded_task_ids.setdefault(task_id, []).append({
                "worker": worker_name,
                "assigned": len(task_ids),
                "capacity": capacity,
            })

    conflicts = []

    for task in tasks:
        task_date = str(task["task_date"] or "")[:10]
        workers = _task_workers(task)
        issues = []

        if not workers:
            issues.append({
                "type": "unassigned",
                "label": "Не назначен исполнитель",
                "details": "Заявка есть в графике, но команда не выбрана.",
                "severity": "critical",
            })

        inactive_workers = [
            worker_name
            for worker_name in workers
            if worker_name not in worker_capacities
        ]

        for worker_name in inactive_workers:
            issues.append({
                "type": "inactive_worker",
                "label": f"{worker_name} отключён",
                "details": "Исполнитель больше не доступен для назначения.",
                "severity": "critical",
                "worker": worker_name,
            })

        unavailable_workers = [
            worker_name
            for worker_name in workers
            if worker_name in worker_capacities
            if task_date in unavailable_dates.get(worker_name, set())
        ]

        for worker_name in unavailable_workers:
            reason = unavailable_reasons.get(
                (worker_name, task_date),
                "Сотрудник недоступен",
            )
            issues.append({
                "type": "unavailable",
                "label": f"{worker_name} недоступен",
                "details": reason,
                "severity": "critical",
                "worker": worker_name,
            })

        overloaded_workers = []

        for overload in overloaded_task_ids.get(task["id"], []):
            worker_name = overload["worker"]
            overloaded_workers.append(worker_name)
            issues.append({
                "type": "overload",
                "label": f"Перегруз: {worker_name}",
                "details": (
                    f"Назначено {overload['assigned']}, "
                    f"дневной лимит {overload['capacity']}."
                ),
                "severity": "warning",
                **overload,
            })

        if not issues:
            continue

        severity = (
            "critical"
            if any(issue["severity"] == "critical" for issue in issues)
            else "warning"
        )
        conflicts.append({
            "task": task,
            "task_id": task["id"],
            "task_date": task_date,
            "workers": workers,
            "workers_csv": ",".join(workers),
            "issues": issues,
            "severity": severity,
            "unavailable_workers": unavailable_workers,
            "inactive_workers": inactive_workers,
            "overloaded_workers": overloaded_workers,
        })

    conflicts.sort(key=lambda item: (
        0 if item["severity"] == "critical" else 1,
        item["task_date"],
        item["task_id"],
    ))
    return conflicts


def build_conflict_recommendations(
    conflict,
    worker_capacities,
    assignments,
    unavailable_dates,
    search_days=14,
):
    task_date = datetime.strptime(
        conflict["task_date"],
        "%Y-%m-%d",
    ).date()
    current_workers = conflict["workers"]
    required_workers = max(len(current_workers), 1)
    recommendations = []

    if (
        current_workers
        and all(
            worker_name in worker_capacities
            for worker_name in current_workers
        )
    ):
        move_result = build_scheduling_recommendations(
            worker_capacities=worker_capacities,
            assignments=assignments,
            start_date=task_date,
            search_days=search_days,
            fixed_workers=current_workers,
            unavailable_dates=unavailable_dates,
            limit=3,
        )

        for item in move_result["items"]:
            if item["date"] == conflict["task_date"]:
                continue

            recommendations.append({
                **item,
                "mode": "move_date",
                "mode_label": "Сохранить команду",
                "action_label": "Перенести",
                "description": "Перенести заявку на свободный день.",
            })
            break

    same_day_result = build_scheduling_recommendations(
        worker_capacities=worker_capacities,
        assignments=assignments,
        start_date=task_date,
        search_days=1,
        required_workers=required_workers,
        unavailable_dates=unavailable_dates,
        limit=3,
    )

    for item in same_day_result["items"]:
        if (
            item["date"] == conflict["task_date"]
            and item["worker_names"] == current_workers
        ):
            continue

        recommendations.append({
            **item,
            "mode": "change_team",
            "mode_label": "Сохранить дату",
            "action_label": "Сменить команду",
            "description": "Назначить свободных исполнителей на эту дату.",
        })
        break

    balanced_result = build_scheduling_recommendations(
        worker_capacities=worker_capacities,
        assignments=assignments,
        start_date=task_date,
        search_days=search_days,
        required_workers=required_workers,
        unavailable_dates=unavailable_dates,
        limit=5,
    )

    for item in balanced_result["items"]:
        duplicate = any(
            recommendation["date"] == item["date"]
            and recommendation["worker_names"] == item["worker_names"]
            for recommendation in recommendations
        )

        if duplicate:
            continue

        recommendations.append({
            **item,
            "mode": "rebalance",
            "mode_label": "Лучший вариант",
            "action_label": "Применить",
            "description": "Перенести и сбалансировать команду.",
        })
        break

    return recommendations[:3]
