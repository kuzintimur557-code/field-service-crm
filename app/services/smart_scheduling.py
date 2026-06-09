from datetime import timedelta


def build_scheduling_recommendations(
    worker_capacities,
    assignments,
    start_date,
    search_days=14,
    required_workers=1,
    preferred_worker="",
    fixed_workers=None,
    unavailable_dates=None,
    limit=12,
):
    worker_names = sorted(worker_capacities)
    required_workers = max(1, int(required_workers or 1))
    search_days = max(1, int(search_days or 14))
    preferred_worker = str(preferred_worker or "").strip()
    fixed_workers = [
        worker_name
        for worker_name in dict.fromkeys(fixed_workers or [])
        if worker_name in worker_capacities
    ]
    unavailable_dates = {
        worker_name: set(date_values or [])
        for worker_name, date_values in (unavailable_dates or {}).items()
    }

    if fixed_workers:
        required_workers = len(fixed_workers)
    daily_counts = {
        worker_name: {}
        for worker_name in worker_names
    }

    for assignment in assignments:
        work_date = str(assignment.get("date") or "")[:10]

        if not work_date:
            continue

        for worker_name in assignment.get("workers") or []:
            if worker_name not in daily_counts:
                continue

            daily_counts[worker_name][work_date] = (
                daily_counts[worker_name].get(work_date, 0) + 1
            )

    recommendations = []
    days_with_capacity = 0
    total_open_slots = 0

    for day_offset in range(search_days):
        schedule_date = start_date + timedelta(days=day_offset)
        date_value = schedule_date.strftime("%Y-%m-%d")
        candidates = []

        for worker_name in worker_names:
            if date_value in unavailable_dates.get(worker_name, set()):
                continue

            capacity = max(1, int(worker_capacities[worker_name] or 1))
            task_count = daily_counts[worker_name].get(date_value, 0)
            available_slots = max(capacity - task_count, 0)

            if available_slots <= 0:
                continue

            candidates.append({
                "username": worker_name,
                "task_count": task_count,
                "daily_capacity": capacity,
                "available_slots": available_slots,
                "load_ratio": task_count / capacity,
            })
            total_open_slots += available_slots

        candidate_names = {
            item["username"] for item in candidates
        }
        fixed_team_available = (
            not fixed_workers
            or all(
                worker_name in candidate_names
                for worker_name in fixed_workers
            )
        )

        if len(candidates) >= required_workers and fixed_team_available:
            days_with_capacity += 1

        if fixed_workers:
            selected = [
                next(
                    item for item in candidates
                    if item["username"] == worker_name
                )
                for worker_name in fixed_workers
                if worker_name in candidate_names
            ]

            if len(selected) != len(fixed_workers):
                continue

            remaining_candidates = []
        elif preferred_worker:
            preferred = next(
                (
                    item for item in candidates
                    if item["username"] == preferred_worker
                ),
                None,
            )

            if not preferred:
                continue

            selected = [preferred]
            remaining_candidates = [
                item for item in candidates
                if item["username"] != preferred_worker
            ]
        else:
            selected = []
            remaining_candidates = candidates

        remaining_candidates.sort(key=lambda item: (
            item["load_ratio"],
            item["task_count"],
            -item["available_slots"],
            item["username"],
        ))
        selected.extend(
            remaining_candidates[:required_workers - len(selected)]
        )

        if len(selected) < required_workers:
            continue

        load_after = [
            (item["task_count"] + 1) / item["daily_capacity"]
            for item in selected
        ]
        average_load_after = sum(load_after) / len(load_after)
        max_load_after = max(load_after)
        available_after = sum(
            max(
                item["daily_capacity"] - item["task_count"] - 1,
                0,
            )
            for item in selected
        )
        score = max(
            0,
            round(
                100
                - day_offset * 2
                - average_load_after * 45
                - max_load_after * 20
            ),
        )
        reason = "Ближайшее свободное окно"

        if all(item["task_count"] == 0 for item in selected):
            reason = "Все исполнители свободны"
        elif average_load_after <= 0.5:
            reason = "Низкая загрузка команды"
        elif available_after:
            reason = "После назначения останется резерв"

        recommendations.append({
            "date": date_value,
            "date_label": schedule_date.strftime("%d.%m.%Y"),
            "day_offset": day_offset,
            "workers": selected,
            "worker_names": [item["username"] for item in selected],
            "available_after": available_after,
            "average_load_percent": round(average_load_after * 100),
            "max_load_percent": round(max_load_after * 100),
            "score": score,
            "reason": reason,
        })

    recommendations.sort(key=lambda item: (
        -item["score"],
        item["day_offset"],
        item["average_load_percent"],
        ",".join(item["worker_names"]),
    ))

    return {
        "items": recommendations[:max(1, int(limit or 12))],
        "summary": {
            "search_days": search_days,
            "required_workers": required_workers,
            "days_with_capacity": days_with_capacity,
            "total_open_slots": total_open_slots,
            "found": len(recommendations),
        },
    }
