from datetime import datetime, timedelta

from app.database import connect
from app.services.a3_incident_followups import (
    build_a3_followups_url,
    normalize_a3_followup_company,
)
from app.services.a3_platform_incident_analytics import (
    normalize_a3_incident_analytics_period,
)


def _moment(value, now):
    try:
        moment = datetime.fromisoformat(str(value or "").replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    if moment.tzinfo is not None:
        # Database timestamps without an offset use the application's local time.
        moment = moment.astimezone(now.tzinfo).replace(tzinfo=None)
    return moment


def _ratio(count, total):
    return round(count * 100 / total, 1) if total else None


def _summary(items):
    completed = [item for item in items if item["status"] == "completed"]
    timed = [item for item in completed if item["completed"] and item["due"]]
    durations = [
        (item["verified"] - item["completed"]).total_seconds() / 3600
        for item in items
        if item["approved"] and item["verified"] and item["completed"]
        and item["verified"] >= item["completed"]
    ]
    verified = sum(item["approved"] for item in items)
    verification_attempts = sum(item["verification_attempts"] for item in items)
    returns_total = sum(item["rework_count"] for item in items)
    reviewed_actions = sum(item["verification_attempts"] > 0 for item in items)
    returned_actions = sum(item["rework_count"] > 0 for item in items)
    first_pass_verified = sum(
        item["approved"] and item["rework_count"] == 0 for item in items
    )
    on_time = sum(item["completed"] <= item["due"] for item in timed)
    return {
        "total": len(items),
        "active": sum(item["active"] for item in items),
        "completed": len(completed),
        "verified": verified,
        "pending": sum(item["pending"] for item in items),
        "rework": sum(item["rework"] for item in items),
        "cancelled": sum(item["status"] == "cancelled" for item in items),
        "overdue": sum(item["overdue"] for item in items),
        "unassigned": sum(item["active"] and not item["owner_username"] for item in items),
        "verified_percent": _ratio(verified, len(completed)),
        "verification_attempts": verification_attempts,
        "reviewed_actions": reviewed_actions,
        "returns_total": returns_total,
        "returned_actions": returned_actions,
        "rework_rate": _ratio(returned_actions, reviewed_actions),
        "first_pass_verified": first_pass_verified,
        "first_pass_percent": _ratio(first_pass_verified, verified),
        "on_time": on_time,
        "timed_completions": len(timed),
        "on_time_percent": _ratio(on_time, len(timed)),
        "verification_samples": len(durations),
        "average_verification_hours": (
            round(sum(durations) / len(durations), 1) if durations else None
        ),
    }


def _quality_rating(summary):
    components = [
        (summary["first_pass_percent"], 0.5),
        (summary["on_time_percent"], 0.3),
        (summary["verified_percent"], 0.2),
    ]
    available = [(value, weight) for value, weight in components if value is not None]
    if not available:
        return {
            "quality_score": None,
            "quality_label": "Недостаточно данных",
            "quality_tone": "neutral",
        }
    weight_total = sum(weight for _, weight in available)
    score = round(sum(value * weight for value, weight in available) / weight_total, 1)
    if score >= 85:
        label, tone = "Отлично", "success"
    elif score >= 70:
        label, tone = "Стабильно", "info"
    elif score >= 50:
        label, tone = "Внимание", "warning"
    else:
        label, tone = "Требует улучшения", "danger"
    return {
        "quality_score": score,
        "quality_label": label,
        "quality_tone": tone,
    }


def get_a3_followup_analytics(period="30", company_id="all", now=None):
    selected_period = normalize_a3_incident_analytics_period(period)
    selected_company = normalize_a3_followup_company(company_id)
    clock = now or datetime.now()
    now_value = clock.replace(tzinfo=None)
    start = (
        (now_value - timedelta(days=int(selected_period) - 1)).replace(
            hour=0, minute=0, second=0, microsecond=0,
        ) if selected_period != "all" else None
    )
    conn = connect()
    try:
        company_filter = "" if selected_company == "all" else "WHERE f.company_id=?"
        company_params = () if selected_company == "all" else (selected_company,)
        rows = conn.execute(f"""
            SELECT f.*, COALESCE(c.name, 'Компания #' || f.company_id) AS company_name
            FROM a3_incident_followups AS f
            JOIN a3_platform_incidents AS i
              ON i.id=f.incident_id AND i.company_id=f.company_id
            LEFT JOIN companies AS c ON c.id=f.company_id
            {company_filter}
            ORDER BY f.id
        """, company_params).fetchall()
    finally:
        conn.close()

    all_items = []
    for row in rows:
        item = dict(row)
        item["owner_username"] = str(item.get("owner_username") or "").strip()
        item["verification_attempts"] = max(
            0, int(item.get("verification_attempts") or 0),
        )
        item["rework_count"] = max(0, int(item.get("rework_count") or 0))
        for name, column in (
            ("created", "created_at"), ("completed", "completed_at"),
            ("verified", "verified_at"), ("due", "due_at"),
        ):
            item[name] = _moment(item.get(column), clock)
        if item["created"] and item["created"] > now_value:
            continue
        item["active"] = item["status"] in {"open", "in_progress"}
        item["approved"] = (
            item["status"] == "completed" and item["verification_status"] == "approved"
        )
        item["pending"] = item["status"] == "completed" and not item["approved"]
        item["rework"] = item["active"] and item["verification_status"] == "rejected"
        item["overdue"] = bool(item["active"] and item["due"] and item["due"] < now_value)
        all_items.append(item)

    cohort = [
        item for item in all_items
        if start is None or (item["created"] and item["created"] >= start)
    ]
    backlog = [item for item in all_items if item["active"] or item["pending"]]

    def grouped(field, label):
        groups = {}
        for item in cohort:
            groups.setdefault(item[field], []).append(item)
        result = [
            {"key": key, "label": label(items[0]), **_summary(items)}
            for key, items in groups.items()
        ]
        return sorted(result, key=lambda item: (
            -item["overdue"], -item["pending"], -item["active"], str(item["key"]),
        ))

    companies = grouped("company_id", lambda item: item["company_name"])
    owners = grouped(
        "owner_username", lambda item: item["owner_username"] or "Не назначен",
    )
    owner_quality = [
        {**owner, **_quality_rating(owner)}
        for owner in owners
        if owner["key"]
    ]
    owner_quality.sort(key=lambda item: (
        item["quality_score"] is None,
        -(item["quality_score"] or 0),
        item["returns_total"],
        item["overdue"],
        item["label"].lower(),
    ))

    months = {}
    for item in cohort:
        key = item["created"].strftime("%Y-%m") if item["created"] else "Без даты"
        months.setdefault(key, []).append(item)
    problems = sorted([
        item for item in backlog
        if item["overdue"] or item["pending"] or item["rework"]
        or (item["active"] and not item["owner_username"])
    ], key=lambda item: (
        not item["overdue"], not item["pending"], not item["rework"],
        item["due"] if item["overdue"] else item["completed"] or item["created"] or now_value,
        item["id"],
    ))
    problem_rows = []
    for item in problems[:20]:
        since = item["due"] if item["overdue"] else item["completed"] if item["pending"] else None
        problem_rows.append({
            "id": item["id"], "title": item["title"],
            "company_name": item["company_name"],
            "owner": item["owner_username"] or "Не назначен",
            "reason": (
                "Просрочена" if item["overdue"] else "Ждёт проверки"
                if item["pending"] else "На доработке" if item["rework"]
                else "Не назначен ответственный" if not item["owner_username"]
                else "В работе"
            ),
            "tone": "danger" if item["overdue"] else "warning",
            "waiting_hours": round(max(0, (now_value - since).total_seconds() / 3600), 1) if since else None,
            "url": build_a3_followups_url(
                "all", item["company_id"], item["incident_id"],
            ) + f"#action-{item['id']}",
        })
    repeat_returns = []
    for item in sorted(
        (item for item in cohort if item["rework_count"] >= 2),
        key=lambda item: (-item["rework_count"], -item["verification_attempts"], item["id"]),
    )[:20]:
        repeat_returns.append({
            "id": item["id"],
            "incident_id": item["incident_id"],
            "company_id": item["company_id"],
            "title": item["title"],
            "company_name": item["company_name"],
            "owner_username": item["owner_username"],
            "owner": item["owner_username"] or "Не назначен",
            "verification_attempts": item["verification_attempts"],
            "rework_count": item["rework_count"],
            "status_label": (
                "Просрочена" if item["overdue"] else "На доработке"
                if item["rework"] else "Ждёт проверки" if item["pending"]
                else "Подтверждена" if item["approved"] else "Активна"
            ),
            "tone": "danger" if item["rework_count"] >= 3 else "warning",
            "url": build_a3_followups_url(
                "all", item["company_id"], item["incident_id"],
            ) + f"#action-{item['id']}",
        })
    return {
        "period": selected_period, "company_id": selected_company,
        "date_from": start.strftime("%d.%m.%Y") if start else "Всё время",
        "date_to": now_value.strftime("%d.%m.%Y"),
        "summary": _summary(cohort), "backlog": _summary(backlog),
        "companies": companies,
        "owners": owners,
        "owner_quality": owner_quality,
        "repeat_returns": repeat_returns,
        "months": [{
            "month": (
                datetime.strptime(key, "%Y-%m").strftime("%m.%Y")
                if key != "Без даты" else key
            ),
            **_summary(items),
        } for key, items in sorted(months.items())],
        "problems": problem_rows,
        "unshown_backlog": max(0, len(problems) - len(problem_rows)),
        "actions_url": build_a3_followups_url("all", selected_company),
    }


def a3_followup_analytics_csv_rows(report):
    summary = report["summary"]
    rows = [
        [], ["Контрольные меры A3: по дате создания"],
        ["Начало периода", report["date_from"]], ["Конец периода", report["date_to"]],
        ["Всего мер", summary["total"]], ["Выполнено", summary["completed"]],
        ["Подтверждено", summary["verified"]], ["Ждут проверки", summary["pending"]],
        ["Выполнено в срок, %", summary["on_time_percent"]],
        ["Средняя проверка результата, ч.", summary["average_verification_hours"]],
        ["Попыток проверки", summary["verification_attempts"]],
        ["Возвратов на доработку", summary["returns_total"]],
        ["Принято с первого раза, %", summary["first_pass_percent"]],
        ["Доля мер с возвратом, %", summary["rework_rate"]],
        ["Текущий остаток за всё время", report["backlog"]["total"]],
        ["Просрочено за всё время", report["backlog"]["overdue"]],
        ["Ждут проверки за всё время", report["backlog"]["pending"]],
    ]
    for key, title, label in (
        ("companies", "Меры по компаниям", "label"),
        ("owners", "Меры по ответственным", "label"),
        ("months", "Меры по месяцу создания", "month"),
    ):
        rows.extend([[], [title], [
            "Группа", "Всего", "Активные", "Просрочены", "Выполнены",
            "Подтверждены", "Ждут проверки", "На доработке", "Отменены",
            "Попытки проверки", "Возвраты", "Принято с первого раза, %",
            "Доля мер с возвратом, %", "Выполнено в срок, %",
            "Средняя проверка, ч.",
        ]])
        for item in report[key]:
            rows.append([item[label]] + [item[name] for name in (
                "total", "active", "overdue", "completed", "verified", "pending",
                "rework", "cancelled", "verification_attempts", "returns_total",
                "first_pass_percent", "rework_rate", "on_time_percent",
                "average_verification_hours",
            )])
    rows.extend([[], ["Рейтинг качества ответственных"], [
        "Ответственный", "Оценка качества", "Уровень", "Всего мер",
        "Проверено мер", "Принято с первого раза, %", "Возвраты",
        "Выполнено в срок, %", "Просрочено",
    ]])
    for item in report["owner_quality"]:
        rows.append([
            item["label"], item["quality_score"], item["quality_label"],
            item["total"], item["reviewed_actions"], item["first_pass_percent"],
            item["returns_total"], item["on_time_percent"], item["overdue"],
        ])
    rows.extend([[], ["Меры с повторными возвратами"], [
        "ID меры", "Мера", "Компания", "Ответственный", "Состояние",
        "Попытки проверки", "Возвраты",
    ]])
    for item in report["repeat_returns"]:
        rows.append([
            item["id"], item["title"], item["company_name"], item["owner"],
            item["status_label"], item["verification_attempts"],
            item["rework_count"],
        ])
    # Spreadsheet applications must treat user-controlled names as text.
    return [[
        "'" + value if isinstance(value, str) and value.lstrip().startswith(("=", "+", "-", "@"))
        else value for value in row
    ] for row in rows]
