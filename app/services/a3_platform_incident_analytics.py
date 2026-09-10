from datetime import datetime, timedelta
from urllib.parse import urlencode

from app.database import connect
from app.services.a3_platform_incidents import (
    get_a3_platform_incident_policy,
)


A3_INCIDENT_ANALYTICS_PERIODS = {
    "7": "7 дней",
    "30": "30 дней",
    "90": "90 дней",
    "all": "Всё время",
}


def normalize_a3_incident_analytics_period(value):
    normalized = str(value or "30").strip().lower()
    return normalized if normalized in A3_INCIDENT_ANALYTICS_PERIODS else "30"


def normalize_a3_incident_analytics_company(value):
    normalized = str(value or "all").strip().lower()
    if normalized == "all":
        return "all"
    try:
        company_id = int(normalized)
    except (TypeError, ValueError):
        return "all"
    return company_id if company_id > 0 else "all"


def build_a3_incident_analytics_url(period="30", company_id="all"):
    selected_period = normalize_a3_incident_analytics_period(period)
    selected_company = normalize_a3_incident_analytics_company(company_id)
    params = {}
    if selected_period != "30":
        params["period"] = selected_period
    if selected_company != "all":
        params["company_id"] = selected_company
    query = urlencode(params)
    return "/platform/a3-health/incidents/analytics" + (
        f"?{query}" if query else ""
    )


def _parse_datetime(value):
    try:
        return datetime.fromisoformat(str(value or "").replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None


def _align_datetime(moment, reference):
    if not moment or not reference:
        return moment
    if moment.tzinfo and not reference.tzinfo:
        return moment.replace(tzinfo=None)
    if reference.tzinfo and not moment.tzinfo:
        return moment.replace(tzinfo=reference.tzinfo)
    return moment


def _minutes_between(started_at, finished_at):
    if not started_at or not finished_at:
        return None
    comparable_finish = _align_datetime(finished_at, started_at)
    return max(0, int((comparable_finish - started_at).total_seconds() // 60))


def _deadline_has_arrived(deadline, moment):
    if not deadline or not moment:
        return False
    return _align_datetime(moment, deadline) >= deadline


def _format_minutes(value):
    if value is None:
        return "Нет данных"
    minutes = max(0, int(round(value)))
    if minutes < 60:
        return f"{minutes} мин."
    hours, remainder = divmod(minutes, 60)
    if hours < 24:
        return f"{hours} ч. {remainder} мин." if remainder else f"{hours} ч."
    days, hours = divmod(hours, 24)
    return f"{days} дн. {hours} ч." if hours else f"{days} дн."


def _percent(numerator, denominator, empty=100):
    return round(numerator * 100 / denominator, 1) if denominator else empty


def _period_start(period, now_value):
    if period == "all":
        return None
    return now_value - timedelta(days=int(period) - 1)


def _month_start(value):
    return value.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def _next_month(value):
    if value.month == 12:
        return value.replace(year=value.year + 1, month=1)
    return value.replace(month=value.month + 1)


def _build_trend(items, period, period_start, now_value):
    use_days = period in {"7", "30"}
    trend_map = {}

    if use_days:
        cursor = (period_start or now_value).date()
        last_date = now_value.date()
        while cursor <= last_date:
            key = cursor.isoformat()
            trend_map[key] = {
                "key": key,
                "label": cursor.strftime("%d.%m"),
                "opened": 0,
                "resolved": 0,
                "late": 0,
                "escalated": 0,
            }
            cursor += timedelta(days=1)
    else:
        dated_items = [item["first_at"] for item in items if item["first_at"]]
        first_month = _month_start(
            period_start or (min(dated_items) if dated_items else now_value)
        )
        cursor = first_month
        last_month = _month_start(now_value)
        while cursor <= last_month:
            key = cursor.strftime("%Y-%m")
            trend_map[key] = {
                "key": key,
                "label": cursor.strftime("%m.%Y"),
                "opened": 0,
                "resolved": 0,
                "late": 0,
                "escalated": 0,
            }
            cursor = _next_month(cursor)

    def bucket(moment):
        return moment.strftime("%Y-%m-%d" if use_days else "%Y-%m")

    for item in items:
        first_at = item["first_at"]
        if first_at:
            key = bucket(first_at)
            if key in trend_map:
                trend_map[key]["opened"] += 1
                trend_map[key]["late"] += int(item["response_was_late"])
                trend_map[key]["escalated"] += int(item["is_escalated"])
        resolved_at = item["resolved_at"]
        if resolved_at:
            key = bucket(resolved_at)
            if key in trend_map:
                trend_map[key]["resolved"] += 1

    trend = list(trend_map.values())
    peak = max(
        (
            max(row["opened"], row["resolved"], row["late"], row["escalated"])
            for row in trend
        ),
        default=1,
    ) or 1
    for row in trend:
        row["opened_bar"] = round(row["opened"] * 100 / peak)
        row["resolved_bar"] = round(row["resolved"] * 100 / peak)
    return trend


def _company_row(item):
    return {
        "company_id": item["company_id"],
        "company_name": item["company_name"],
        "total": 0,
        "active": 0,
        "resolved": 0,
        "response_eligible": 0,
        "on_time": 0,
        "late": 0,
        "overdue": 0,
        "escalated": 0,
        "response_values": [],
    }


def _admin_row(item):
    return {
        "username": item["assigned_to"] or "",
        "display_name": item["assigned_to"] or "Не назначен",
        "total": 0,
        "active": 0,
        "resolved": 0,
        "acknowledged": 0,
        "late": 0,
        "escalated": 0,
        "response_values": [],
    }


def _build_recommendations(summary, companies, analytics_url):
    recommendations = []
    if summary["response_overdue"]:
        recommendations.append({
            "tone": "danger",
            "title": "Есть инциденты без своевременной реакции",
            "description": (
                f"Просрочено: {summary['response_overdue']}. "
                "Назначьте ответственных и зафиксируйте начало работы."
            ),
            "url": "/platform/a3-health/incidents?status=response_overdue",
            "action_label": "Открыть просроченные",
        })
    if summary["response_eligible"] and summary["response_sla_percent"] < 80:
        recommendations.append({
            "tone": "warning",
            "title": "Срок реакции соблюдается нестабильно",
            "description": (
                f"Текущий показатель: {summary['response_sla_percent']}%. "
                "Проверьте дежурства и правила назначения инцидентов."
            ),
            "url": analytics_url,
            "action_label": "Посмотреть аналитику",
        })
    if summary["escalation_rate"] >= 30 and summary["total"]:
        recommendations.append({
            "tone": "warning",
            "title": "Высокая доля эскалаций",
            "description": (
                f"Эскалировано {summary['escalation_rate']}% инцидентов. "
                "Разберите повторяющиеся причины у компаний с высоким риском."
            ),
            "url": analytics_url,
            "action_label": "Проверить компании",
        })
    if companies and companies[0]["risk_score"] >= 50:
        company = companies[0]
        recommendations.append({
            "tone": "danger" if company["risk_score"] >= 80 else "warning",
            "title": f"Требует внимания: {company['company_name']}",
            "description": (
                f"Оценка операционного риска {company['risk_score']}/100, "
                f"активных инцидентов: {company['active']}."
            ),
            "url": company["incidents_url"],
            "action_label": "Открыть инциденты",
        })
    if not recommendations:
        recommendations.append({
            "tone": "success",
            "title": "Работа с инцидентами стабильна",
            "description": (
                "Просроченных реакций и критической нагрузки за выбранный "
                "период не обнаружено."
            ),
            "url": "/platform/a3-health/incidents",
            "action_label": "Открыть центр",
        })
    return recommendations[:4]


def get_a3_platform_incident_analytics(
    period="30",
    company_id="all",
    now=None,
):
    now_value = now or datetime.now()
    selected_period = normalize_a3_incident_analytics_period(period)
    selected_company = normalize_a3_incident_analytics_company(company_id)
    period_start = _period_start(selected_period, now_value)
    policy = get_a3_platform_incident_policy()
    conditions = []
    params = []
    if period_start:
        conditions.append("incidents.first_detected_at>=?")
        params.append(period_start.strftime("%Y-%m-%d 00:00:00"))
    if selected_company != "all":
        conditions.append("incidents.company_id=?")
        params.append(selected_company)
    where_sql = "WHERE " + " AND ".join(conditions) if conditions else ""

    conn = connect()
    try:
        rows = conn.cursor().execute(f"""
            SELECT
                incidents.*,
                COALESCE(
                    companies.name,
                    'Компания #' || incidents.company_id
                ) AS company_name
            FROM a3_platform_incidents AS incidents
            LEFT JOIN companies ON companies.id=incidents.company_id
            {where_sql}
            ORDER BY incidents.first_detected_at DESC, incidents.id DESC
        """, params).fetchall()
        company_rows = conn.cursor().execute("""
            SELECT DISTINCT
                incidents.company_id,
                COALESCE(
                    companies.name,
                    'Компания #' || incidents.company_id
                ) AS company_name
            FROM a3_platform_incidents AS incidents
            LEFT JOIN companies ON companies.id=incidents.company_id
            ORDER BY company_name, incidents.company_id
        """).fetchall()
    finally:
        conn.close()

    items = []
    for raw_row in rows:
        row = dict(raw_row)
        first_at = _parse_datetime(row.get("first_detected_at"))
        response_due = _parse_datetime(row.get("response_due_at"))
        if not response_due and first_at:
            response_due = first_at + timedelta(minutes=policy["response_minutes"])
        acknowledged_at = _parse_datetime(row.get("acknowledged_at"))
        resolved_at = _parse_datetime(row.get("resolved_at"))
        response_minutes = _minutes_between(first_at, acknowledged_at)
        resolution_minutes = _minutes_between(first_at, resolved_at)
        response_was_late = bool(
            acknowledged_at
            and response_due
            and _align_datetime(acknowledged_at, response_due) > response_due
        )
        response_eligible = bool(
            acknowledged_at or _deadline_has_arrived(response_due, now_value)
        )
        is_active = row.get("status") == "open"
        response_overdue = bool(
            is_active
            and not acknowledged_at
            and _deadline_has_arrived(response_due, now_value)
        )
        is_escalated = bool(
            row.get("escalated_at") or int(row.get("escalation_count") or 0)
        )
        item = {
            **row,
            "first_at": first_at,
            "acknowledged_at_value": acknowledged_at,
            "resolved_at": resolved_at,
            "response_minutes": response_minutes,
            "resolution_minutes": resolution_minutes,
            "response_eligible": response_eligible,
            "response_on_time": bool(
                acknowledged_at and not response_was_late
            ),
            "response_was_late": response_was_late,
            "response_overdue": response_overdue,
            "is_active": is_active,
            "is_resolved": row.get("status") == "resolved",
            "is_escalated": is_escalated,
            "company_name": row.get("company_name")
            or f"Компания #{row['company_id']}",
        }
        items.append(item)

    total = len(items)
    active = sum(item["is_active"] for item in items)
    resolved = sum(item["is_resolved"] for item in items)
    acknowledged = sum(
        bool(item["acknowledged_at_value"]) for item in items
    )
    response_eligible = sum(item["response_eligible"] for item in items)
    on_time = sum(item["response_on_time"] for item in items)
    late = sum(item["response_was_late"] for item in items)
    response_overdue = sum(item["response_overdue"] for item in items)
    escalated = sum(item["is_escalated"] for item in items)
    response_values = [
        item["response_minutes"]
        for item in items
        if item["response_minutes"] is not None
    ]
    resolution_values = [
        item["resolution_minutes"]
        for item in items
        if item["resolution_minutes"] is not None
    ]
    average_response = (
        round(sum(response_values) / len(response_values))
        if response_values else None
    )
    average_resolution = (
        round(sum(resolution_values) / len(resolution_values))
        if resolution_values else None
    )
    summary = {
        "total": total,
        "active": active,
        "resolved": resolved,
        "acknowledged": acknowledged,
        "response_eligible": response_eligible,
        "on_time": on_time,
        "late": late,
        "response_overdue": response_overdue,
        "escalated": escalated,
        "response_sla_percent": _percent(on_time, response_eligible),
        "resolution_rate": _percent(resolved, total),
        "escalation_rate": _percent(escalated, total, empty=0),
        "average_response_minutes": average_response,
        "average_response_label": _format_minutes(average_response),
        "average_resolution_minutes": average_resolution,
        "average_resolution_label": _format_minutes(average_resolution),
    }

    companies_map = {}
    admins_map = {}
    for item in items:
        company = companies_map.setdefault(
            item["company_id"],
            _company_row(item),
        )
        company["total"] += 1
        company["active"] += int(item["is_active"])
        company["resolved"] += int(item["is_resolved"])
        company["response_eligible"] += int(item["response_eligible"])
        company["on_time"] += int(item["response_on_time"])
        company["late"] += int(item["response_was_late"])
        company["overdue"] += int(item["response_overdue"])
        company["escalated"] += int(item["is_escalated"])
        if item["response_minutes"] is not None:
            company["response_values"].append(item["response_minutes"])

        admin_key = item["assigned_to"] or "__unassigned__"
        admin = admins_map.setdefault(admin_key, _admin_row(item))
        admin["total"] += 1
        admin["active"] += int(item["is_active"])
        admin["resolved"] += int(item["is_resolved"])
        admin["acknowledged"] += int(bool(item["acknowledged_at_value"]))
        admin["late"] += int(item["response_was_late"])
        admin["escalated"] += int(item["is_escalated"])
        if item["response_minutes"] is not None:
            admin["response_values"].append(item["response_minutes"])

    companies = []
    for company in companies_map.values():
        values = company.pop("response_values")
        average = round(sum(values) / len(values)) if values else None
        company["response_sla_percent"] = _percent(
            company["on_time"],
            company["response_eligible"],
        )
        company["escalation_rate"] = _percent(
            company["escalated"],
            company["total"],
            empty=0,
        )
        company["average_response_minutes"] = average
        company["average_response_label"] = _format_minutes(average)
        company["risk_score"] = min(
            100,
            company["overdue"] * 35
            + company["active"] * 20
            + company["late"] * 15
            + company["escalated"] * 15,
        )
        company["risk_label"] = (
            "Высокий"
            if company["risk_score"] >= 80
            else "Средний" if company["risk_score"] >= 40 else "Низкий"
        )
        company["risk_tone"] = (
            "danger"
            if company["risk_score"] >= 80
            else "warning" if company["risk_score"] >= 40 else "success"
        )
        company["incidents_url"] = (
            "/platform/a3-health/incidents?status=all&search="
            + str(company["company_id"])
        )
        companies.append(company)
    companies.sort(
        key=lambda row: (
            -row["risk_score"],
            -row["active"],
            -row["total"],
            row["company_name"].lower(),
        )
    )

    admin_workload = []
    for admin in admins_map.values():
        values = admin.pop("response_values")
        average = round(sum(values) / len(values)) if values else None
        admin["average_response_minutes"] = average
        admin["average_response_label"] = _format_minutes(average)
        admin["load_score"] = min(
            100,
            admin["active"] * 25 + admin["late"] * 20 + admin["escalated"] * 15,
        )
        admin["load_label"] = (
            "Высокая"
            if admin["load_score"] >= 75
            else "Средняя" if admin["load_score"] >= 35 else "Низкая"
        )
        admin_workload.append(admin)
    admin_workload.sort(
        key=lambda row: (-row["active"], -row["total"], row["display_name"])
    )

    analytics_url = build_a3_incident_analytics_url(
        selected_period,
        selected_company,
    )
    export_params = {"period": selected_period}
    if selected_company != "all":
        export_params["company_id"] = selected_company
    records = []
    for item in items:
        records.append({
            "id": item["id"],
            "company_id": item["company_id"],
            "company_name": item["company_name"],
            "title": item.get("title") or "Инцидент A3",
            "status_label": "Открыт" if item["is_active"] else "Закрыт",
            "first_detected_at": item.get("first_detected_at") or "",
            "acknowledged_at": item.get("acknowledged_at") or "",
            "resolved_at": item.get("resolved_at") or "",
            "assigned_to": item.get("assigned_to") or "Не назначен",
            "response_label": _format_minutes(item["response_minutes"]),
            "resolution_label": _format_minutes(item["resolution_minutes"]),
            "response_status": (
                "Просрочена"
                if item["response_overdue"]
                else "С опозданием"
                if item["response_was_late"]
                else "В срок"
                if item["response_on_time"]
                else "Срок не наступил"
            ),
            "escalated_label": "Да" if item["is_escalated"] else "Нет",
        })

    return {
        "generated_at": now_value.strftime("%d.%m.%Y %H:%M"),
        "period": selected_period,
        "period_label": A3_INCIDENT_ANALYTICS_PERIODS[selected_period],
        "company_id": selected_company,
        "date_from": (
            period_start.strftime("%d.%m.%Y") if period_start else "Первый инцидент"
        ),
        "date_to": now_value.strftime("%d.%m.%Y"),
        "policy": policy,
        "summary": summary,
        "companies": companies,
        "admin_workload": admin_workload,
        "trend": _build_trend(items, selected_period, period_start, now_value),
        "recommendations": _build_recommendations(
            summary,
            companies,
            analytics_url,
        ),
        "records": records,
        "period_options": [
            {
                "key": key,
                "label": label,
                "url": build_a3_incident_analytics_url(key, selected_company),
            }
            for key, label in A3_INCIDENT_ANALYTICS_PERIODS.items()
        ],
        "company_options": [
            {
                "id": int(row["company_id"]),
                "name": row["company_name"],
            }
            for row in company_rows
        ],
        "base_url": "/platform/a3-health/incidents/analytics",
        "export_url": (
            "/platform/a3-health/incidents/analytics/export?"
            + urlencode(export_params)
        ),
    }
