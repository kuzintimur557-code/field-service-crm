from datetime import datetime, timedelta
from urllib.parse import urlencode

from app.database import connect


A3_FOLLOWUP_FILTER_LABELS = {
    "active": "Активные",
    "overdue": "Просроченные",
    "due_soon": "Срок сегодня",
    "verification_pending": "Ждут проверки",
    "verified": "Подтверждённые",
    "rejected": "На доработке",
    "completed": "Выполненные",
    "cancelled": "Отменённые",
    "all": "Все",
}
A3_FOLLOWUP_STATUS_LABELS = {
    "open": "Новая",
    "in_progress": "В работе",
    "completed": "Выполнена",
    "cancelled": "Отменена",
}
A3_FOLLOWUP_TYPE_LABELS = {
    "corrective": "Исправляющая мера",
    "prevention": "Профилактическая мера",
}
A3_FOLLOWUP_PRIORITY_LABELS = {
    "low": "Низкий",
    "normal": "Обычный",
    "high": "Высокий",
    "critical": "Критический",
}
A3_FOLLOWUP_VERIFICATION_LABELS = {
    "not_ready": "Проверка не требуется",
    "pending": "Ожидает проверки",
    "approved": "Результат подтверждён",
    "rejected": "Возвращена на доработку",
}


def normalize_a3_followup_filter(value):
    normalized = str(value or "active").strip().lower()
    return normalized if normalized in A3_FOLLOWUP_FILTER_LABELS else "active"


def normalize_a3_followup_company(value):
    normalized = str(value or "all").strip().lower()
    if normalized == "all":
        return "all"
    try:
        company_id = int(normalized)
    except (TypeError, ValueError):
        return "all"
    return company_id if company_id > 0 else "all"


def normalize_a3_followup_incident(value):
    normalized = str(value or "all").strip().lower()
    if normalized == "all":
        return "all"
    try:
        incident_id = int(normalized)
    except (TypeError, ValueError):
        return "all"
    return incident_id if incident_id > 0 else "all"


def normalize_a3_followup_owner(value):
    normalized = str(value or "all").strip().lower()
    return normalized if normalized in {"all", "unassigned", "me"} else "all"


def build_a3_followups_url(
    status="active",
    company_id="all",
    incident_id="all",
    owner="all",
    search="",
):
    selected_status = normalize_a3_followup_filter(status)
    selected_company = normalize_a3_followup_company(company_id)
    selected_incident = normalize_a3_followup_incident(incident_id)
    selected_owner = normalize_a3_followup_owner(owner)
    selected_search = str(search or "").strip()[:100]
    params = {}
    if selected_status != "active":
        params["status"] = selected_status
    if selected_company != "all":
        params["company_id"] = selected_company
    if selected_incident != "all":
        params["incident_id"] = selected_incident
    if selected_owner != "all":
        params["owner"] = selected_owner
    if selected_search:
        params["search"] = selected_search
    query = urlencode(params)
    return "/platform/a3-health/incidents/actions" + (
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


def _due_progress_label(due_at, now_value, is_finished=False):
    if is_finished:
        return "Контроль завершён"
    if not due_at:
        return "Срок не указан"
    comparable_now = _align_datetime(now_value, due_at)
    minutes = int((due_at - comparable_now).total_seconds() // 60)
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
    normalized = str(value or "open").strip().lower()
    return normalized if normalized in A3_FOLLOWUP_STATUS_LABELS else "open"


def _action_type(value):
    normalized = str(value or "prevention").strip().lower()
    return normalized if normalized in A3_FOLLOWUP_TYPE_LABELS else "prevention"


def _priority(value):
    normalized = str(value or "normal").strip().lower()
    return normalized if normalized in A3_FOLLOWUP_PRIORITY_LABELS else "normal"


def _verification_status(task_status, value):
    normalized = str(value or "not_ready").strip().lower()
    if task_status == "completed":
        return normalized if normalized in {"pending", "approved"} else "pending"
    if normalized == "rejected":
        return "rejected"
    return "not_ready"


def _platform_admin_exists(cursor, username):
    return bool(cursor.execute("""
        SELECT 1
        FROM users
        WHERE username=?
          AND role='superadmin'
          AND COALESCE(is_active, 1)=1
    """, (username,)).fetchone())


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


def _log_incident_event(
    cursor,
    incident_id,
    company_id,
    event_type,
    actor_username,
    message,
    created_at,
):
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
        company_id,
        event_type,
        actor_username,
        message,
        created_at,
    ))


def _enrich_followup(raw_item, now_value):
    item = dict(raw_item)
    status = _editable_status(item.get("status"))
    due_at = _parse_datetime(item.get("due_at"))
    is_active = status in {"open", "in_progress"}
    comparable_now = _align_datetime(now_value, due_at) if due_at else now_value
    is_overdue = bool(is_active and due_at and comparable_now > due_at)
    due_soon = bool(
        is_active
        and due_at
        and comparable_now <= due_at <= comparable_now + timedelta(hours=24)
    )
    priority = _priority(item.get("priority"))
    action_type = _action_type(item.get("action_type"))
    verification_status = _verification_status(
        status,
        item.get("verification_status"),
    )
    item.update({
        "status": status,
        "status_label": (
            "Просрочена"
            if is_overdue else A3_FOLLOWUP_STATUS_LABELS[status]
        ),
        "status_tone": (
            "danger"
            if is_overdue
            else "success" if status == "completed"
            else "neutral" if status == "cancelled"
            else "warning" if status == "in_progress" else "info"
        ),
        "priority": priority,
        "priority_label": A3_FOLLOWUP_PRIORITY_LABELS[priority],
        "priority_tone": (
            "danger"
            if priority == "critical"
            else "warning" if priority == "high" else "neutral"
        ),
        "action_type": action_type,
        "action_type_label": A3_FOLLOWUP_TYPE_LABELS[action_type],
        "verification_status": verification_status,
        "verification_label": A3_FOLLOWUP_VERIFICATION_LABELS[
            verification_status
        ],
        "verification_tone": (
            "success"
            if verification_status == "approved"
            else "danger" if verification_status == "rejected"
            else "warning" if verification_status == "pending"
            else "neutral"
        ),
        "verification_pending": verification_status == "pending",
        "is_verified": verification_status == "approved",
        "is_rejected": verification_status == "rejected",
        "verified_label": _time_label(item.get("verified_at")),
        "company_name": item.get("company_name")
        or f"Компания #{item['company_id']}",
        "incident_title": item.get("incident_title") or "Инцидент A3",
        "owner_label": item.get("owner_username") or "Не назначен",
        "due_value": due_at,
        "due_label": _time_label(due_at),
        "due_input": due_at.strftime("%Y-%m-%dT%H:%M") if due_at else "",
        "due_progress_label": _due_progress_label(
            due_at,
            now_value,
            is_finished=status in {"completed", "cancelled"},
        ),
        "completed_label": _time_label(item.get("completed_at")),
        "is_active": is_active,
        "is_overdue": is_overdue,
        "due_soon": due_soon,
        "incident_url": (
            "/platform/a3-health/incidents?status=resolved&search="
            + str(item["incident_id"])
            + f"#incident-{item['incident_id']}"
        ),
        "review_url": (
            "/platform/a3-health/incidents/reviews?status=all&search="
            + str(item["incident_id"])
            + f"#review-{item['incident_id']}"
        ),
    })
    return item


def get_a3_incident_followups(
    status_filter="active",
    company_id="all",
    incident_id="all",
    owner_filter="all",
    search="",
    current_username="",
    limit=150,
    now=None,
):
    now_value = now or datetime.now()
    selected_status = normalize_a3_followup_filter(status_filter)
    selected_company = normalize_a3_followup_company(company_id)
    selected_incident = normalize_a3_followup_incident(incident_id)
    selected_owner = normalize_a3_followup_owner(owner_filter)
    selected_search = str(search or "").strip()[:100]
    safe_limit = max(1, min(int(limit or 150), 500))
    conditions = []
    params = []
    if selected_company != "all":
        conditions.append("followups.company_id=?")
        params.append(selected_company)
    if selected_incident != "all":
        conditions.append("followups.incident_id=?")
        params.append(selected_incident)
    if selected_owner == "unassigned":
        conditions.append("followups.owner_username IS NULL")
    elif selected_owner == "me":
        conditions.append("followups.owner_username=?")
        params.append(str(current_username or ""))
    if selected_search:
        search_value = f"%{selected_search.lower()}%"
        conditions.append("""
            (
                LOWER(followups.title) LIKE ?
                OR LOWER(COALESCE(followups.description, '')) LIKE ?
                OR LOWER(COALESCE(followups.owner_username, '')) LIKE ?
                OR LOWER(COALESCE(companies.name, '')) LIKE ?
                OR LOWER(COALESCE(incidents.title, '')) LIKE ?
            )
        """)
        params.extend([search_value] * 5)
    where_sql = "WHERE " + " AND ".join(conditions) if conditions else ""

    conn = connect()
    try:
        cursor = conn.cursor()
        rows = cursor.execute(f"""
            SELECT
                followups.*,
                incidents.title AS incident_title,
                incidents.resolved_at AS incident_resolved_at,
                COALESCE(
                    companies.name,
                    'Компания #' || followups.company_id
                ) AS company_name
            FROM a3_incident_followups AS followups
            JOIN a3_platform_incidents AS incidents
              ON incidents.id=followups.incident_id
            LEFT JOIN companies ON companies.id=followups.company_id
            {where_sql}
            ORDER BY followups.due_at, followups.id
        """, params).fetchall()
        admins = _load_platform_admins(cursor)
        company_rows = cursor.execute("""
            SELECT DISTINCT
                followups.company_id,
                COALESCE(
                    companies.name,
                    'Компания #' || followups.company_id
                ) AS company_name
            FROM a3_incident_followups AS followups
            LEFT JOIN companies ON companies.id=followups.company_id
            ORDER BY company_name, followups.company_id
        """).fetchall()
        incident_conditions = ["incidents.status='resolved'"]
        incident_params = []
        if selected_company != "all":
            incident_conditions.append("incidents.company_id=?")
            incident_params.append(selected_company)
        incident_rows = cursor.execute(f"""
            SELECT
                incidents.id,
                incidents.company_id,
                incidents.title,
                incidents.resolved_at,
                COALESCE(
                    companies.name,
                    'Компания #' || incidents.company_id
                ) AS company_name
            FROM a3_platform_incidents AS incidents
            LEFT JOIN companies ON companies.id=incidents.company_id
            WHERE {' AND '.join(incident_conditions)}
            ORDER BY incidents.resolved_at DESC, incidents.id DESC
            LIMIT 200
        """, incident_params).fetchall()
    finally:
        conn.close()

    all_items = [_enrich_followup(row, now_value) for row in rows]
    summary = {
        "total": len(all_items),
        "active": sum(item["is_active"] for item in all_items),
        "overdue": sum(item["is_overdue"] for item in all_items),
        "due_soon": sum(item["due_soon"] for item in all_items),
        "completed": sum(
            item["status"] == "completed" for item in all_items
        ),
        "cancelled": sum(
            item["status"] == "cancelled" for item in all_items
        ),
        "unassigned": sum(
            item["is_active"] and not item.get("owner_username")
            for item in all_items
        ),
        "critical": sum(
            item["is_active"] and item["priority"] == "critical"
            for item in all_items
        ),
        "verification_pending": sum(
            item["verification_pending"] for item in all_items
        ),
        "verified": sum(item["is_verified"] for item in all_items),
        "rejected": sum(item["is_rejected"] for item in all_items),
    }
    finished = summary["completed"] + summary["cancelled"]
    summary["completion_percent"] = (
        round(summary["completed"] * 100 / (summary["active"] + finished), 1)
        if summary["active"] + finished else 100
    )

    if selected_status == "active":
        items = [item for item in all_items if item["is_active"]]
    elif selected_status == "overdue":
        items = [item for item in all_items if item["is_overdue"]]
    elif selected_status == "due_soon":
        items = [item for item in all_items if item["due_soon"]]
    elif selected_status == "verification_pending":
        items = [item for item in all_items if item["verification_pending"]]
    elif selected_status == "verified":
        items = [item for item in all_items if item["is_verified"]]
    elif selected_status == "rejected":
        items = [item for item in all_items if item["is_rejected"]]
    elif selected_status == "completed":
        items = [item for item in all_items if item["status"] == "completed"]
    elif selected_status == "cancelled":
        items = [item for item in all_items if item["status"] == "cancelled"]
    else:
        items = list(all_items)

    priority_order = {"critical": 0, "high": 1, "normal": 2, "low": 3}
    items.sort(key=lambda item: (
        not item["is_overdue"],
        not item["due_soon"],
        not item["verification_pending"],
        priority_order[item["priority"]],
        item.get("due_at") or "9999",
        int(item["id"]),
    ))
    items = items[:safe_limit]
    status_options = []
    for key, label in A3_FOLLOWUP_FILTER_LABELS.items():
        status_options.append({
            "key": key,
            "label": label,
            "count": summary["total" if key == "all" else key],
            "url": build_a3_followups_url(
                key,
                selected_company,
                selected_incident,
                selected_owner,
                selected_search,
            ),
        })

    return {
        "generated_at": now_value.strftime("%d.%m.%Y %H:%M"),
        "status_filter": selected_status,
        "company_id": selected_company,
        "incident_id": selected_incident,
        "owner_filter": selected_owner,
        "search": selected_search,
        "summary": summary,
        "items": items,
        "visible": len(items),
        "status_options": status_options,
        "company_options": [
            {"id": int(row["company_id"]), "name": row["company_name"]}
            for row in company_rows
        ],
        "incident_options": [
            {
                "id": int(row["id"]),
                "company_id": int(row["company_id"]),
                "label": (
                    f"#{row['id']} · {row['company_name']} · {row['title']}"
                ),
            }
            for row in incident_rows
        ],
        "admins": admins,
        "base_url": "/platform/a3-health/incidents/actions",
        "create_defaults": {
            "due_at": (
                now_value + timedelta(days=1)
            ).strftime("%Y-%m-%dT%H:%M"),
        },
    }


def create_a3_incident_followup(
    incident_id,
    actor_username,
    title,
    description,
    action_type,
    priority,
    owner_username,
    due_at,
    now=None,
):
    title_text = str(title or "").strip()[:180]
    description_text = str(description or "").strip()[:2000]
    selected_type = _action_type(action_type)
    selected_priority = _priority(priority)
    selected_owner = str(owner_username or "").strip()[:120]
    due_value = _parse_datetime(due_at)
    if not title_text:
        return {"ok": False, "error": "empty_title", "message": "Введите название меры."}
    if not due_value:
        return {"ok": False, "error": "invalid_due_at", "message": "Укажите корректный срок."}

    now_value = now or datetime.now()
    now_text = _timestamp(now_value)
    conn = connect()
    try:
        cursor = conn.cursor()
        cursor.execute("BEGIN IMMEDIATE")
        if not _platform_admin_exists(cursor, actor_username):
            conn.rollback()
            return {"ok": False, "error": "forbidden", "message": "Недостаточно прав."}
        if selected_owner and not _platform_admin_exists(cursor, selected_owner):
            conn.rollback()
            return {
                "ok": False,
                "error": "invalid_owner",
                "message": "Выберите активного администратора платформы.",
            }
        incident = cursor.execute("""
            SELECT id, company_id, title
            FROM a3_platform_incidents
            WHERE id=? AND status='resolved'
        """, (incident_id,)).fetchone()
        if not incident:
            conn.rollback()
            return {
                "ok": False,
                "error": "incident_not_found",
                "message": "Закрытый инцидент не найден.",
            }
        cursor.execute("""
            INSERT INTO a3_incident_followups (
                incident_id,
                company_id,
                action_type,
                title,
                description,
                status,
                priority,
                owner_username,
                due_at,
                created_by,
                created_at,
                updated_at
            ) VALUES (?, ?, ?, ?, ?, 'open', ?, ?, ?, ?, ?, ?)
        """, (
            incident_id,
            incident["company_id"],
            selected_type,
            title_text,
            description_text,
            selected_priority,
            selected_owner or None,
            _timestamp(due_value),
            actor_username,
            now_text,
            now_text,
        ))
        followup_id = cursor.lastrowid
        _log_incident_event(
            cursor,
            incident_id,
            incident["company_id"],
            "followup_created",
            actor_username,
            (
                f"Создана контрольная мера #{followup_id}: {title_text}. "
                f"Срок: {_time_label(due_value)}."
            ),
            now_text,
        )
        conn.commit()
        return {
            "ok": True,
            "followup_id": followup_id,
            "incident_id": incident_id,
            "message": "Контрольная мера создана.",
        }
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def update_a3_incident_followup(
    followup_id,
    actor_username,
    title,
    description,
    status,
    priority,
    owner_username,
    due_at,
    now=None,
):
    title_text = str(title or "").strip()[:180]
    description_text = str(description or "").strip()[:2000]
    selected_status = _editable_status(status)
    selected_priority = _priority(priority)
    selected_owner = str(owner_username or "").strip()[:120]
    due_value = _parse_datetime(due_at)
    if not title_text:
        return {"ok": False, "error": "empty_title", "message": "Введите название меры."}
    if not due_value:
        return {"ok": False, "error": "invalid_due_at", "message": "Укажите корректный срок."}

    now_value = now or datetime.now()
    now_text = _timestamp(now_value)
    conn = connect()
    try:
        cursor = conn.cursor()
        cursor.execute("BEGIN IMMEDIATE")
        if not _platform_admin_exists(cursor, actor_username):
            conn.rollback()
            return {"ok": False, "error": "forbidden", "message": "Недостаточно прав."}
        if selected_owner and not _platform_admin_exists(cursor, selected_owner):
            conn.rollback()
            return {
                "ok": False,
                "error": "invalid_owner",
                "message": "Выберите активного администратора платформы.",
            }
        row = cursor.execute("""
            SELECT * FROM a3_incident_followups WHERE id=?
        """, (followup_id,)).fetchone()
        if not row:
            conn.rollback()
            return {
                "ok": False,
                "error": "followup_not_found",
                "message": "Контрольная мера не найдена.",
            }
        followup = dict(row)
        completed_at = None
        completed_by = None
        if selected_status == "completed":
            completed_at = followup.get("completed_at") or now_text
            completed_by = followup.get("completed_by") or actor_username
        previous_status = str(followup.get("status") or "open")
        previous_verification = str(
            followup.get("verification_status") or "not_ready"
        )
        result_changed = (
            selected_status == "completed"
            and previous_status == "completed"
            and (
                title_text != str(followup.get("title") or "")
                or description_text != str(followup.get("description") or "")
            )
        )
        if result_changed:
            completed_at = now_text
            completed_by = actor_username
        if selected_status == "completed":
            if previous_status != "completed" or result_changed:
                verification_status = "pending"
                verification_note = None
                verified_at = None
                verified_by = None
            else:
                verification_status = _verification_status(
                    selected_status,
                    previous_verification,
                )
                verification_note = followup.get("verification_note")
                verified_at = followup.get("verified_at")
                verified_by = followup.get("verified_by")
        elif (
            selected_status == "in_progress"
            and previous_status == "in_progress"
            and previous_verification == "rejected"
        ):
            verification_status = "rejected"
            verification_note = followup.get("verification_note")
            verified_at = followup.get("verified_at")
            verified_by = followup.get("verified_by")
        else:
            verification_status = "not_ready"
            verification_note = None
            verified_at = None
            verified_by = None
        due_text = _timestamp(due_value)
        reminder_changed = (
            result_changed
            or selected_status != followup.get("status")
            or selected_owner != str(followup.get("owner_username") or "")
            or due_text != str(followup.get("due_at") or "")
        )
        reminder_stage = (
            None if reminder_changed else followup.get("reminder_stage")
        )
        last_reminded_at = (
            None if reminder_changed else followup.get("last_reminded_at")
        )
        cursor.execute("""
            UPDATE a3_incident_followups
            SET title=?,
                description=?,
                status=?,
                priority=?,
                owner_username=?,
                due_at=?,
                completed_at=?,
                completed_by=?,
                reminder_stage=?,
                last_reminded_at=?,
                verification_status=?,
                verification_note=?,
                verified_at=?,
                verified_by=?,
                updated_at=?
            WHERE id=?
        """, (
            title_text,
            description_text,
            selected_status,
            selected_priority,
            selected_owner or None,
            due_text,
            completed_at,
            completed_by,
            reminder_stage,
            last_reminded_at,
            verification_status,
            verification_note,
            verified_at,
            verified_by,
            now_text,
            followup_id,
        ))
        event_type = (
            "followup_verification_reset"
            if result_changed
            else "followup_completed"
            if selected_status == "completed"
            and followup.get("status") != "completed"
            else "followup_updated"
        )
        _log_incident_event(
            cursor,
            followup["incident_id"],
            followup["company_id"],
            event_type,
            actor_username,
            (
                f"Контрольная мера #{followup_id}: "
                f"{A3_FOLLOWUP_STATUS_LABELS[selected_status].lower()}."
                + (
                    " Результат изменён и отправлен на повторную проверку."
                    if result_changed else ""
                )
            ),
            now_text,
        )
        conn.commit()
        return {
            "ok": True,
            "followup_id": followup_id,
            "incident_id": followup["incident_id"],
            "status": selected_status,
            "message": "Контрольная мера обновлена.",
        }
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def review_a3_incident_followup(
    followup_id,
    actor_username,
    decision,
    note="",
    rework_due_at="",
    now=None,
):
    selected_decision = str(decision or "").strip().lower()
    note_text = str(note or "").strip()[:2000]
    if selected_decision not in {"approved", "rejected"}:
        return {
            "ok": False,
            "error": "invalid_verification_decision",
            "message": "Выберите результат проверки.",
        }
    if selected_decision == "rejected" and not note_text:
        return {
            "ok": False,
            "error": "empty_verification_note",
            "message": "Укажите причину возврата на доработку.",
        }

    now_value = now or datetime.now()
    now_text = _timestamp(now_value)
    rework_due = _parse_datetime(rework_due_at)
    if selected_decision == "rejected":
        if not rework_due:
            return {
                "ok": False,
                "error": "invalid_rework_due_at",
                "message": "Укажите новый срок доработки.",
            }
        comparable_now = _align_datetime(now_value, rework_due)
        if rework_due <= comparable_now:
            return {
                "ok": False,
                "error": "invalid_rework_due_at",
                "message": "Новый срок должен быть позже текущего времени.",
            }

    conn = connect()
    try:
        cursor = conn.cursor()
        cursor.execute("BEGIN IMMEDIATE")
        if not _platform_admin_exists(cursor, actor_username):
            conn.rollback()
            return {
                "ok": False,
                "error": "forbidden",
                "message": "Недостаточно прав для проверки результата.",
            }
        row = cursor.execute("""
            SELECT * FROM a3_incident_followups WHERE id=?
        """, (followup_id,)).fetchone()
        if not row:
            conn.rollback()
            return {
                "ok": False,
                "error": "followup_not_found",
                "message": "Контрольная мера не найдена.",
            }
        followup = dict(row)
        if followup.get("status") != "completed":
            conn.rollback()
            return {
                "ok": False,
                "error": "followup_not_completed",
                "message": "Сначала отметьте меру выполненной.",
            }

        if selected_decision == "approved":
            cursor.execute("""
                UPDATE a3_incident_followups
                SET verification_status='approved',
                    verification_note=?,
                    verified_at=?,
                    verified_by=?,
                    updated_at=?
                WHERE id=? AND status='completed'
            """, (
                note_text,
                now_text,
                actor_username,
                now_text,
                followup_id,
            ))
            event_type = "followup_verified"
            event_message = (
                f"Результат контрольной меры #{followup_id} подтверждён "
                f"администратором {actor_username}."
            )
        else:
            cursor.execute("""
                UPDATE a3_incident_followups
                SET status='in_progress',
                    due_at=?,
                    completed_at=NULL,
                    completed_by=NULL,
                    verification_status='rejected',
                    verification_note=?,
                    verified_at=?,
                    verified_by=?,
                    reminder_stage=NULL,
                    last_reminded_at=NULL,
                    updated_at=?
                WHERE id=? AND status='completed'
            """, (
                _timestamp(rework_due),
                note_text,
                now_text,
                actor_username,
                now_text,
                followup_id,
            ))
            event_type = "followup_rejected"
            event_message = (
                f"Контрольная мера #{followup_id} возвращена на доработку "
                f"до {_time_label(rework_due)}. Причина: {note_text}"
            )

        _log_incident_event(
            cursor,
            followup["incident_id"],
            followup["company_id"],
            event_type,
            actor_username,
            event_message,
            now_text,
        )
        notification_created = 0
        owner = str(followup.get("owner_username") or "").strip()
        if owner and owner != actor_username and _platform_admin_exists(cursor, owner):
            notification_title = (
                "Результат меры A3 подтверждён"
                if selected_decision == "approved"
                else "Мера A3 возвращена на доработку"
            )
            cursor.execute("""
                INSERT INTO notifications (
                    company_id,
                    username,
                    title,
                    message,
                    link,
                    is_read,
                    created_at
                ) VALUES (?, ?, ?, ?, ?, 0, ?)
            """, (
                followup["company_id"],
                owner,
                notification_title,
                event_message[:1000],
                (
                    "/platform/a3-health/incidents/actions?status=all&"
                    f"incident_id={followup['incident_id']}#action-{followup_id}"
                ),
                now_text,
            ))
            notification_created = 1
        conn.commit()
        return {
            "ok": True,
            "followup_id": followup_id,
            "incident_id": followup["incident_id"],
            "decision": selected_decision,
            "notice": (
                "verification_approved"
                if selected_decision == "approved"
                else "verification_rejected"
            ),
            "notification_created": notification_created,
            "message": (
                "Результат меры подтверждён."
                if selected_decision == "approved"
                else "Мера возвращена на доработку."
            ),
        }
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
