from datetime import datetime, timedelta
from urllib.parse import urlencode

from app.database import connect
from app.services.a3_platform_incidents import (
    get_a3_platform_incident_policy,
)


A3_INCIDENT_REVIEW_STATUS_LABELS = {
    "pending": "Ожидают разбора",
    "in_progress": "В работе",
    "overdue": "Просрочены",
    "completed": "Завершены",
    "all": "Все",
}
A3_INCIDENT_REVIEW_EDITABLE_STATUSES = {
    "pending",
    "in_progress",
    "completed",
}


def normalize_a3_incident_review_status(value):
    normalized = str(value or "pending").strip().lower()
    return (
        normalized
        if normalized in A3_INCIDENT_REVIEW_STATUS_LABELS
        else "pending"
    )


def normalize_a3_incident_review_company(value):
    normalized = str(value or "all").strip().lower()
    if normalized == "all":
        return "all"
    try:
        company_id = int(normalized)
    except (TypeError, ValueError):
        return "all"
    return company_id if company_id > 0 else "all"


def build_a3_incident_reviews_url(
    status="pending",
    company_id="all",
    search="",
):
    selected_status = normalize_a3_incident_review_status(status)
    selected_company = normalize_a3_incident_review_company(company_id)
    selected_search = str(search or "").strip()[:100]
    params = {}
    if selected_status != "pending":
        params["status"] = selected_status
    if selected_company != "all":
        params["company_id"] = selected_company
    if selected_search:
        params["search"] = selected_search
    query = urlencode(params)
    return "/platform/a3-health/incidents/reviews" + (
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


def _timestamp(value=None):
    return (value or datetime.now()).strftime("%Y-%m-%d %H:%M:%S")


def _time_label(value):
    parsed = value if isinstance(value, datetime) else _parse_datetime(value)
    return parsed.strftime("%d.%m.%Y %H:%M") if parsed else "Не указано"


def _review_due_at(incident, review_hours):
    stored = _parse_datetime(incident.get("review_due_at"))
    if stored:
        return stored
    resolved_at = _parse_datetime(incident.get("resolved_at"))
    return resolved_at + timedelta(hours=review_hours) if resolved_at else None


def _is_overdue(deadline, now_value):
    return bool(
        deadline
        and _align_datetime(now_value, deadline) > deadline
    )


def _due_progress_label(deadline, now_value, completed=False):
    if completed:
        return "Разбор завершён"
    if not deadline:
        return "Срок не определён"
    comparable_now = _align_datetime(now_value, deadline)
    minutes = int((deadline - comparable_now).total_seconds() // 60)
    if minutes < 0:
        overdue = abs(minutes)
        if overdue < 60:
            return f"Просрочено на {overdue} мин."
        if overdue < 1440:
            return f"Просрочено на {overdue // 60} ч."
        return f"Просрочено на {overdue // 1440} дн."
    if minutes < 60:
        return f"Осталось {max(0, minutes)} мин."
    if minutes < 1440:
        return f"Осталось {minutes // 60} ч."
    return f"Осталось {minutes // 1440} дн."


def _editable_status(value):
    normalized = str(value or "in_progress").strip().lower()
    return (
        normalized
        if normalized in A3_INCIDENT_REVIEW_EDITABLE_STATUSES
        else "in_progress"
    )


def _review_status_label(status, overdue=False):
    if overdue:
        return "Разбор просрочен"
    return {
        "pending": "Ожидает разбора",
        "in_progress": "Разбор в работе",
        "completed": "Разбор завершён",
    }.get(status, "Ожидает разбора")


def _load_platform_admins(cursor):
    return [
        {
            **dict(row),
            "display_name": row["full_name"] or row["username"],
        }
        for row in cursor.execute("""
            SELECT username, full_name
            FROM users
            WHERE role='superadmin' AND COALESCE(is_active, 1)=1
            ORDER BY COALESCE(full_name, username), username
        """).fetchall()
    ]


def _platform_admin_exists(cursor, username):
    return bool(cursor.execute("""
        SELECT 1
        FROM users
        WHERE username=?
          AND role='superadmin'
          AND COALESCE(is_active, 1)=1
    """, (username,)).fetchone())


def _matches_search(item, search):
    if not search:
        return True
    haystack = " ".join(str(value or "") for value in (
        item.get("id"),
        item.get("company_id"),
        item.get("company_name"),
        item.get("title"),
        item.get("review_owner"),
        item.get("root_cause"),
    )).lower()
    return search.lower() in haystack


def _enrich_review(raw_item, now_value, policy):
    item = dict(raw_item)
    review_status = str(item.get("review_status") or "pending").lower()
    if review_status not in A3_INCIDENT_REVIEW_EDITABLE_STATUSES:
        review_status = "pending"
    due_at = _review_due_at(item, policy["review_hours"])
    completed = review_status == "completed"
    overdue = not completed and _is_overdue(due_at, now_value)
    completed_fields = sum(bool(str(item.get(key) or "").strip()) for key in (
        "root_cause",
        "corrective_actions",
        "prevention_actions",
    ))
    item.update({
        "company_name": item.get("company_name")
        or f"Компания #{item['company_id']}",
        "review_status": review_status,
        "review_status_label": _review_status_label(review_status, overdue),
        "review_status_tone": (
            "danger"
            if overdue
            else "success" if completed
            else "warning" if review_status == "in_progress" else "neutral"
        ),
        "review_due_value": due_at,
        "review_due_sort": _timestamp(due_at) if due_at else "9999",
        "review_due_label": _time_label(due_at),
        "review_progress_label": _due_progress_label(
            due_at,
            now_value,
            completed=completed,
        ),
        "review_owner_label": item.get("review_owner") or "Не назначен",
        "resolved_label": _time_label(item.get("resolved_at")),
        "completed_label": _time_label(item.get("review_completed_at")),
        "is_overdue": overdue,
        "is_completed": completed,
        "completeness_percent": round(completed_fields * 100 / 3),
        "incident_url": (
            "/platform/a3-health/incidents?status=resolved&search="
            + str(item["id"])
            + f"#incident-{item['id']}"
        ),
        "company_url": f"/platform/companies/{item['company_id']}",
    })
    return item


def get_a3_platform_incident_reviews(
    status_filter="pending",
    company_id="all",
    search="",
    limit=100,
    now=None,
):
    now_value = now or datetime.now()
    selected_status = normalize_a3_incident_review_status(status_filter)
    selected_company = normalize_a3_incident_review_company(company_id)
    selected_search = str(search or "").strip()[:100]
    safe_limit = max(1, min(int(limit or 100), 300))
    policy = get_a3_platform_incident_policy()
    conditions = ["incidents.status='resolved'"]
    params = []
    if selected_company != "all":
        conditions.append("incidents.company_id=?")
        params.append(selected_company)

    conn = connect()
    try:
        cursor = conn.cursor()
        rows = cursor.execute(f"""
            SELECT
                incidents.*,
                COALESCE(
                    companies.name,
                    'Компания #' || incidents.company_id
                ) AS company_name
            FROM a3_platform_incidents AS incidents
            LEFT JOIN companies ON companies.id=incidents.company_id
            WHERE {' AND '.join(conditions)}
            ORDER BY incidents.resolved_at DESC, incidents.id DESC
        """, params).fetchall()
        admins = _load_platform_admins(cursor)
        company_rows = cursor.execute("""
            SELECT DISTINCT
                incidents.company_id,
                COALESCE(
                    companies.name,
                    'Компания #' || incidents.company_id
                ) AS company_name
            FROM a3_platform_incidents AS incidents
            LEFT JOIN companies ON companies.id=incidents.company_id
            WHERE incidents.status='resolved'
            ORDER BY company_name, incidents.company_id
        """).fetchall()
    finally:
        conn.close()

    all_items = [
        _enrich_review(row, now_value, policy)
        for row in rows
    ]
    all_items = [
        item for item in all_items if _matches_search(item, selected_search)
    ]
    summary = {
        "total": len(all_items),
        "pending": sum(
            item["review_status"] == "pending" for item in all_items
        ),
        "in_progress": sum(
            item["review_status"] == "in_progress" for item in all_items
        ),
        "overdue": sum(item["is_overdue"] for item in all_items),
        "completed": sum(item["is_completed"] for item in all_items),
    }
    summary["completion_percent"] = (
        round(summary["completed"] * 100 / summary["total"], 1)
        if summary["total"] else 100
    )

    if selected_status == "pending":
        items = [
            item
            for item in all_items
            if item["review_status"] == "pending"
        ]
    elif selected_status == "in_progress":
        items = [
            item
            for item in all_items
            if item["review_status"] == "in_progress"
        ]
    elif selected_status == "overdue":
        items = [item for item in all_items if item["is_overdue"]]
    elif selected_status == "completed":
        items = [item for item in all_items if item["is_completed"]]
    else:
        items = list(all_items)

    items.sort(key=lambda item: (
        not item["is_overdue"],
        item["is_completed"],
        item["review_due_sort"],
        -int(item["id"]),
    ))
    items = items[:safe_limit]
    status_options = []
    for key, label in A3_INCIDENT_REVIEW_STATUS_LABELS.items():
        status_options.append({
            "key": key,
            "label": label,
            "count": summary["total" if key == "all" else key],
            "url": build_a3_incident_reviews_url(
                key,
                selected_company,
                selected_search,
            ),
        })

    return {
        "generated_at": now_value.strftime("%d.%m.%Y %H:%M"),
        "status_filter": selected_status,
        "company_id": selected_company,
        "search": selected_search,
        "summary": summary,
        "items": items,
        "visible": len(items),
        "status_options": status_options,
        "company_options": [
            {"id": int(row["company_id"]), "name": row["company_name"]}
            for row in company_rows
        ],
        "admins": admins,
        "policy": policy,
        "base_url": "/platform/a3-health/incidents/reviews",
    }


def save_a3_platform_incident_review(
    incident_id,
    actor_username,
    review_status,
    review_owner,
    root_cause,
    corrective_actions,
    prevention_actions,
    now=None,
):
    selected_status = _editable_status(review_status)
    selected_owner = str(review_owner or actor_username or "").strip()[:120]
    root_cause_text = str(root_cause or "").strip()[:2000]
    corrective_text = str(corrective_actions or "").strip()[:3000]
    prevention_text = str(prevention_actions or "").strip()[:3000]
    if selected_status == "completed" and not all((
        root_cause_text,
        corrective_text,
        prevention_text,
    )):
        return {
            "ok": False,
            "error": "incomplete_review",
            "message": (
                "Для завершения заполните причину, выполненные действия "
                "и профилактику повторения."
            ),
        }

    now_value = now or datetime.now()
    now_text = _timestamp(now_value)
    policy = get_a3_platform_incident_policy()
    conn = connect()
    try:
        cursor = conn.cursor()
        cursor.execute("BEGIN IMMEDIATE")
        if not _platform_admin_exists(cursor, actor_username):
            conn.rollback()
            return {
                "ok": False,
                "error": "forbidden",
                "message": "Недостаточно прав для разбора инцидента.",
            }
        if not selected_owner or not _platform_admin_exists(cursor, selected_owner):
            conn.rollback()
            return {
                "ok": False,
                "error": "invalid_owner",
                "message": "Выберите активного администратора платформы.",
            }

        incident_row = cursor.execute("""
            SELECT *
            FROM a3_platform_incidents
            WHERE id=? AND status='resolved'
        """, (incident_id,)).fetchone()
        if not incident_row:
            conn.rollback()
            return {
                "ok": False,
                "error": "incident_not_found",
                "message": "Закрытый инцидент не найден.",
            }
        incident = dict(incident_row)
        review_due = _review_due_at(incident, policy["review_hours"])
        if not review_due:
            review_due = now_value + timedelta(hours=policy["review_hours"])
        started_at = incident.get("review_started_at")
        if selected_status in {"in_progress", "completed"} and not started_at:
            started_at = now_text
        completed_at = (
            incident.get("review_completed_at") or now_text
            if selected_status == "completed"
            else None
        )
        completed_by = (
            incident.get("review_completed_by") or actor_username
            if selected_status == "completed"
            else None
        )
        cursor.execute("""
            UPDATE a3_platform_incidents
            SET review_status=?,
                review_due_at=?,
                review_owner=?,
                root_cause=?,
                corrective_actions=?,
                prevention_actions=?,
                review_started_at=?,
                review_completed_at=?,
                review_completed_by=?,
                review_updated_at=?,
                updated_at=?
            WHERE id=? AND status='resolved'
        """, (
            selected_status,
            _timestamp(review_due),
            selected_owner,
            root_cause_text,
            corrective_text,
            prevention_text,
            started_at,
            completed_at,
            completed_by,
            now_text,
            now_text,
            incident_id,
        ))
        event_type = (
            "review_completed"
            if selected_status == "completed"
            else "review_updated"
        )
        event_message = (
            f"Разбор завершил {actor_username}. Причина и меры зафиксированы."
            if selected_status == "completed"
            else f"Разбор обновил {actor_username}: {_review_status_label(selected_status)}."
        )
        cursor.execute("""
            INSERT INTO a3_platform_incident_events (
                incident_id,
                company_id,
                event_type,
                actor_username,
                message,
                created_at
            ) VALUES (?, ?, ?, ?, ?, ?)
        """, (
            incident_id,
            incident["company_id"],
            event_type,
            actor_username,
            event_message,
            now_text,
        ))
        conn.commit()
        return {
            "ok": True,
            "incident_id": incident_id,
            "review_status": selected_status,
            "review_owner": selected_owner,
            "message": (
                "Разбор завершён."
                if selected_status == "completed"
                else "Разбор сохранён."
            ),
        }
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
