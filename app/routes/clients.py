"""Client base, client cards, notes, files and calls routes."""

import csv
import io
import mimetypes
from datetime import datetime, timedelta
from pathlib import Path

from fastapi import APIRouter, File, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse, Response

from app.database import connect
from app.deps import (
    get_role,
    get_user,
    get_user_company_id,
    require_route_company_context,
)
from app.object_storage import (
    ObjectStorageError,
    delete_storage_object,
    save_storage_fileobj,
)
from app.services.common import (
    build_dashboard_links,
    create_call_follow_up_notification,
    create_notification,
    format_task_workers,
    get_company_settings,
    get_task_worker_names,
    has_feature,
    log_task_activity,
    require_feature,
    role_label,
    ui_text,
)
from app.templating import templates
from app.uploads import (
    ALLOWED_CLIENT_FILE_EXTENSIONS,
    CLIENT_FILE_UPLOAD_MAX_BYTES,
    CLIENT_FILES_DIR,
    UPLOAD_DIR,
    validate_upload_file,
    safe_client_file_filename,
    storage_file_response,
)

router = APIRouter()

def get_clients_with_metrics(
    company_id: int,
    search: str = "",
    client_filter: str = "",
    client_sort: str = "",
):
    today = datetime.now().strftime("%Y-%m-%d")
    selected_search = str(search or "").strip()[:100]
    selected_client_filter = (
        client_filter if client_filter in ("active", "overdue", "empty") else ""
    )
    selected_client_sort = (
        client_sort if client_sort in ("name", "tasks", "active", "overdue")
        else "newest"
    )
    search_value = f"%{selected_search.lower()}%"

    search_condition = ""
    params = [today, company_id]

    if selected_search:
        search_condition = """
          AND (
            lower(clients.name) LIKE ?
            OR lower(clients.phone) LIKE ?
            OR lower(clients.email) LIKE ?
            OR lower(clients.address) LIKE ?
            OR lower(clients.notes) LIKE ?
          )
        """
        params.extend([
            search_value,
            search_value,
            search_value,
            search_value,
            search_value,
        ])

    conn = connect()
    c = conn.cursor()

    clients = c.execute(f"""
    SELECT
        clients.*,
        COUNT(tasks.id) AS task_count,
        MAX(tasks.task_date) AS last_task_date,
        SUM(CASE
            WHEN tasks.status='Завершено'
            THEN CAST(REPLACE(COALESCE(tasks.price, '0'), ',', '.') AS REAL)
            ELSE 0
        END) AS completed_revenue,
        SUM(CASE
            WHEN tasks.archived=0
             AND tasks.status IN ('Новая', 'В работе')
            THEN 1 ELSE 0
        END) AS active_task_count,
        SUM(CASE
            WHEN tasks.archived=0
             AND tasks.task_date IS NOT NULL
             AND substr(tasks.task_date, 1, 10) < ?
             AND tasks.status NOT IN ('Завершено', 'Отменено')
            THEN 1 ELSE 0
        END) AS overdue_task_count
    FROM clients
    LEFT JOIN tasks
      ON tasks.client_id=clients.id
      AND tasks.company_id=clients.company_id
    WHERE clients.company_id=?
    {search_condition}
    GROUP BY clients.id
    ORDER BY clients.id DESC
    """, params).fetchall()

    conn.close()

    if selected_client_filter == "active":
        clients = [client for client in clients if client["active_task_count"]]
    elif selected_client_filter == "overdue":
        clients = [client for client in clients if client["overdue_task_count"]]
    elif selected_client_filter == "empty":
        clients = [client for client in clients if not client["task_count"]]

    if selected_client_sort == "name":
        clients = sorted(clients, key=lambda client: str(client["name"] or "").lower())
    elif selected_client_sort == "tasks":
        clients = sorted(clients, key=lambda client: client["task_count"] or 0, reverse=True)
    elif selected_client_sort == "active":
        clients = sorted(clients, key=lambda client: client["active_task_count"] or 0, reverse=True)
    elif selected_client_sort == "overdue":
        clients = sorted(clients, key=lambda client: client["overdue_task_count"] or 0, reverse=True)

    clients = clients[:1000]

    return {
        "clients": clients,
        "selected_search": selected_search,
        "selected_client_filter": selected_client_filter,
        "selected_client_sort": selected_client_sort,
    }




def run_automation_event(*args, **kwargs):
    from app.main import run_automation_event as _impl

    return _impl(*args, **kwargs)

@router.get("/clients", response_class=HTMLResponse)
async def clients_page(
    request: Request,
    search: str = "",
    client_filter: str = "",
    client_sort: str = ""
):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role == "superadmin":
        return RedirectResponse("/platform", status_code=302)

    if role not in ("boss", "manager"):
        return RedirectResponse("/", status_code=302)

    company_id = get_user_company_id(username)
    disabled_response = require_feature(company_id, "clients")

    if disabled_response:
        return disabled_response

    settings = get_company_settings(company_id)
    client_data = get_clients_with_metrics(
        company_id,
        search=search,
        client_filter=client_filter,
        client_sort=client_sort,
    )
    conn = connect()
    c = conn.cursor()

    custom_fields = c.execute("""
    SELECT *
    FROM custom_fields
    WHERE company_id=?
      AND entity_type='client'
      AND active=1
    ORDER BY sort_order, id
    """, (company_id,)).fetchall()

    conn.close()

    return templates.TemplateResponse(
        request,
        "clients.html",
        {
            "request": request,
            "username": username,
            "role": role,
            "clients": client_data["clients"],
            "selected_search": client_data["selected_search"],
            "selected_client_filter": client_data["selected_client_filter"],
            "selected_client_sort": client_data["selected_client_sort"],
            "custom_fields": custom_fields,
            "settings": settings,
        }
    )


@router.get("/clients/export")
async def clients_export(
    request: Request,
    search: str = "",
    client_filter: str = "",
    client_sort: str = ""
):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role == "superadmin":
        return RedirectResponse("/platform", status_code=302)

    if role not in ("boss", "manager"):
        return RedirectResponse("/", status_code=302)

    company_id = get_user_company_id(username)
    disabled_response = require_feature(company_id, "clients")

    if disabled_response:
        return disabled_response

    settings = get_company_settings(company_id)
    client_data = get_clients_with_metrics(
        company_id,
        search=search,
        client_filter=client_filter,
        client_sort=client_sort,
    )
    clients = client_data["clients"]
    selected_search = client_data["selected_search"]
    selected_client_filter = client_data["selected_client_filter"]
    selected_client_sort = client_data["selected_client_sort"]

    client_label = (
        settings["client_label"]
        if settings and settings["client_label"]
        else "Клиент"
    )
    task_label = (
        settings["task_label"]
        if settings and settings["task_label"]
        else "Заявка"
    )

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        client_label,
        "Телефон",
        "Электронная почта",
        "Адрес",
        "Заметки",
        f"{task_label}: всего",
        "Активных",
        "Просрочено",
        "Последняя запись",
        "Выручка",
        "Создан",
    ])

    for client in clients:
        writer.writerow([
            client["name"] or "",
            client["phone"] or "",
            client["email"] or "",
            client["address"] or "",
            client["notes"] or "",
            client["task_count"] or 0,
            client["active_task_count"] or 0,
            client["overdue_task_count"] or 0,
            client["last_task_date"] or "",
            client["completed_revenue"] or 0,
            client["created_at"] or "",
        ])

    filename_parts = [
        selected_client_filter or "all",
        selected_client_sort,
        "search" if selected_search else "all",
    ]
    filename = "clients_" + "_".join(filename_parts) + ".csv"

    return Response(
        content="\ufeff" + output.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f"attachment; filename={filename}"
        }
    )


@router.get("/clients/{client_id}", response_class=HTMLResponse)
async def client_detail(
    request: Request,
    client_id: int,
    task_filter: str = "",
    task_search: str = "",
    task_sort: str = "",
    activity_filter: str = "",
    note_search: str = "",
    file_search: str = "",
    call_filter: str = "",
    call_content: str = ""
):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role not in ("boss", "manager"):
        return RedirectResponse("/", status_code=302)

    company_id, missing_company_response = require_route_company_context(username, role)

    if missing_company_response:
        return missing_company_response

    settings = get_company_settings(company_id)
    task_label = settings["task_label"] or "Заявка"
    disabled_response = require_feature(company_id, "clients")

    if disabled_response:
        return disabled_response

    conn = connect()
    c = conn.cursor()

    client = c.execute("""
    SELECT *
    FROM clients
    WHERE id=? AND company_id=?
    """, (client_id, company_id)).fetchone()

    if not client:
        conn.close()
        return RedirectResponse("/clients", status_code=302)

    tasks = c.execute("""
    SELECT *
    FROM tasks
    WHERE client_id=? AND company_id=?
    ORDER BY id DESC
    """, (client_id, company_id)).fetchall()
    selected_task_filter = task_filter if task_filter in (
        "active",
        "completed",
        "overdue",
        "sla_overdue",
        "sla_soon",
        "unassigned",
    ) else ""
    selected_task_search = str(task_search or "").strip()[:100]
    selected_task_sort = task_sort if task_sort in ("oldest", "date_asc", "date_desc") else "newest"
    selected_activity_filter = activity_filter if activity_filter in ("status", "date", "comment") else ""
    selected_note_search = str(note_search or "").strip()[:100]
    selected_file_search = str(file_search or "").strip()[:100]
    selected_call_filter = call_filter if call_filter in ("follow_up", "missed", "completed") else ""
    search_value = selected_task_search.lower()
    note_search_value = selected_note_search.lower()
    file_search_value = selected_file_search.lower()
    latest_task = tasks[0] if tasks else None
    client_task_workers = {task["id"]: format_task_workers(task) for task in tasks}

    now_dt = datetime.now()
    today = now_dt.strftime("%Y-%m-%d")
    client_now_value = now_dt.strftime("%Y-%m-%dT%H:%M")
    client_sla_soon_value = (now_dt + timedelta(hours=24)).strftime("%Y-%m-%dT%H:%M")
    client_total_tasks = len(tasks)
    client_active_tasks = 0
    client_completed_tasks = 0
    client_overdue_tasks = 0
    client_sla_overdue_tasks = 0
    client_sla_due_soon_tasks = 0
    client_unassigned_tasks = 0
    client_revenue = 0
    upcoming_tasks = []

    for task in tasks:
        task_status = task["status"] or ""
        is_archived = "archived" in task.keys() and task["archived"] == 1
        task_date = str(task["task_date"] or "")[:10]
        is_open_task = (
            not is_archived
            and task_status not in ("Завершено", "Отменено")
        )

        if not is_archived and task_status in ("Новая", "В работе"):
            client_active_tasks += 1

        if (
            is_open_task
            and task_date
            and task_date >= today
        ):
            upcoming_tasks.append(task)

        if task_status == "Завершено":
            client_completed_tasks += 1

            try:
                client_revenue += float(str(task["price"] or 0).replace(",", "."))
            except Exception:
                pass

        if (
            is_open_task
            and task_date
            and task_date < today
        ):
            client_overdue_tasks += 1

        if is_open_task:
            deadline_at = str(task["deadline_at"] or "") if "deadline_at" in task.keys() else ""

            if deadline_at:
                if deadline_at < client_now_value:
                    client_sla_overdue_tasks += 1
                elif deadline_at <= client_sla_soon_value:
                    client_sla_due_soon_tasks += 1

            if client_task_workers.get(task["id"], "Не назначены") == "Не назначены":
                client_unassigned_tasks += 1

    upcoming_task = None

    if upcoming_tasks:
        upcoming_task = sorted(
            upcoming_tasks,
            key=lambda item: (str(item["task_date"] or ""), item["id"] or 0)
        )[0]

    client_next_action = {
        "title": "Активных работ нет",
        "text": f"Можно создать запись в разделе «{task_label}» или добавить заметку.",
        "link": f"/create-task?client_id={client_id}&return_to=client",
        "link_text": f"Создать: {task_label}"
    }

    if client_overdue_tasks:
        client_next_action = {
            "title": f"Просрочено: {task_label}",
            "text": "Проверьте просрочки, перенесите дату или закройте работу.",
            "link": f"/clients/{client_id}?task_filter=overdue",
            "link_text": "Открыть просрочки"
        }
    elif upcoming_task:
        client_next_action = {
            "title": f"{task_label} #{upcoming_task['id']}: ближайшее",
            "text": f"{upcoming_task['task_date'] or 'Без даты'} / {upcoming_task['status']}",
            "link": f"/task/{upcoming_task['id']}",
            "link_text": f"Открыть: {task_label}"
        }
    elif client_active_tasks:
        client_next_action = {
            "title": f"Активно: {task_label}",
            "text": "Есть работы без будущей даты. Проверьте активный список.",
            "link": f"/clients/{client_id}?task_filter=active",
            "link_text": "Показать активные"
        }

    filtered_tasks = []

    for task in tasks:
        task_status = task["status"] or ""
        is_archived = "archived" in task.keys() and task["archived"] == 1
        task_date = str(task["task_date"] or "")[:10]
        deadline_at = str(task["deadline_at"] or "") if "deadline_at" in task.keys() else ""
        task_workers = client_task_workers.get(task["id"], "Не назначены")
        is_open_task = (
            not is_archived
            and task_status not in ("Завершено", "Отменено")
        )
        is_overdue = (
            is_open_task
            and task_date
            and task_date < today
        )
        is_sla_overdue = (
            is_open_task
            and deadline_at
            and deadline_at < client_now_value
        )
        is_sla_due_soon = (
            is_open_task
            and deadline_at
            and client_now_value <= deadline_at <= client_sla_soon_value
        )
        is_unassigned = is_open_task and task_workers == "Не назначены"

        if selected_task_filter == "active" and (is_archived or task_status not in ("Новая", "В работе")):
            continue

        if selected_task_filter == "completed" and task_status != "Завершено":
            continue

        if selected_task_filter == "overdue" and not is_overdue:
            continue

        if selected_task_filter == "sla_overdue" and not is_sla_overdue:
            continue

        if selected_task_filter == "sla_soon" and not is_sla_due_soon:
            continue

        if selected_task_filter == "unassigned" and not is_unassigned:
            continue

        if search_value:
            search_text = " ".join([
                str(task["id"] or ""),
                str(task["description"] or ""),
                str(task["address"] or ""),
                str(task["worker"] or ""),
                str(task["workers"] or ""),
                str(task_status or "")
            ]).lower()

            if search_value not in search_text:
                continue

        filtered_tasks.append(task)

    if selected_task_sort == "oldest":
        filtered_tasks.sort(key=lambda item: item["id"] or 0)
    elif selected_task_sort == "date_asc":
        filtered_tasks.sort(key=lambda item: (str(item["task_date"] or ""), item["id"] or 0))
    elif selected_task_sort == "date_desc":
        filtered_tasks.sort(key=lambda item: (str(item["task_date"] or ""), item["id"] or 0), reverse=True)

    client_notes = c.execute("""
    SELECT *
    FROM client_notes
    WHERE client_id=? AND company_id=?
    ORDER BY id DESC
    """, (client_id, company_id)).fetchall()
    latest_client_note = client_notes[0] if client_notes else None
    client_note_count = len(client_notes)

    if note_search_value:
        client_notes = [
            note for note in client_notes
            if note_search_value in str(note["note"] or "").lower()
        ]

    client_timeline = c.execute("""
    SELECT
        task_activity.*,
        tasks.id AS task_id,
        tasks.status AS task_status
    FROM task_activity
    JOIN tasks ON tasks.id=task_activity.task_id
    WHERE tasks.client_id=?
      AND tasks.company_id=?
    ORDER BY task_activity.id DESC
    LIMIT 20
    """, (client_id, company_id)).fetchall()
    latest_activity = client_timeline[0] if client_timeline else None

    selected_call_content = call_content if call_content in ("audio", "analysis") else ""
    call_filter_parts = []
    call_params = [client_id, company_id]

    if selected_call_filter:
        call_filter_parts.append("status=?")
        call_params.append(selected_call_filter)

    if selected_call_content == "audio":
        call_filter_parts.append("COALESCE(audio_filename, '')!=''")

    if selected_call_content == "analysis":
        call_filter_parts.append("""
        (
            COALESCE(transcript, '')!=''
            OR COALESCE(ai_summary, '')!=''
        )
        """)

    call_filter_sql = ""

    if call_filter_parts:
        call_filter_sql = "AND " + " AND ".join(call_filter_parts)

    client_calls = c.execute(f"""
    SELECT *
    FROM call_records
    WHERE client_id=? AND company_id=?
      {call_filter_sql}
    ORDER BY COALESCE(call_at, created_at) DESC, id DESC
    LIMIT 10
    """, call_params).fetchall()
    latest_client_call = c.execute("""
    SELECT *
    FROM call_records
    WHERE client_id=? AND company_id=?
    ORDER BY COALESCE(call_at, created_at) DESC, id DESC
    LIMIT 1
    """, (client_id, company_id)).fetchone()
    client_call_count = c.execute("""
    SELECT COUNT(*)
    FROM call_records
    WHERE client_id=? AND company_id=?
    """, (client_id, company_id)).fetchone()[0]
    client_call_stats_row = c.execute("""
    SELECT
        COUNT(*) AS total,
        SUM(CASE WHEN status='follow_up' THEN 1 ELSE 0 END) AS follow_up,
        SUM(CASE WHEN status='missed' THEN 1 ELSE 0 END) AS missed,
        SUM(CASE WHEN COALESCE(audio_filename, '')!='' THEN 1 ELSE 0 END) AS with_audio,
        SUM(
            CASE
            WHEN COALESCE(transcript, '')!=''
              OR COALESCE(ai_summary, '')!=''
            THEN 1 ELSE 0 END
        ) AS with_analysis
    FROM call_records
    WHERE client_id=? AND company_id=?
    """, (client_id, company_id)).fetchone()
    client_call_stats = {
        "total": client_call_stats_row["total"] or 0,
        "follow_up": client_call_stats_row["follow_up"] or 0,
        "missed": client_call_stats_row["missed"] or 0,
        "with_audio": client_call_stats_row["with_audio"] or 0,
        "with_analysis": client_call_stats_row["with_analysis"] or 0,
    }

    def parse_client_health_datetime(value):
        raw_value = str(value or "").strip()

        if not raw_value:
            return None

        normalized_value = raw_value.replace("T", " ")
        formats = (
            ("%Y-%m-%d %H:%M:%S", normalized_value[:19]),
            ("%Y-%m-%d %H:%M", normalized_value[:16]),
            ("%Y-%m-%d", normalized_value[:10]),
        )

        for date_format, candidate in formats:
            try:
                return datetime.strptime(candidate, date_format)
            except Exception:
                pass

        return None

    last_contact = None

    if latest_client_note:
        last_contact = {
            "type": "Заметка",
            "date": latest_client_note["created_at"],
            "text": latest_client_note["note"]
        }

    if latest_activity and (
        not last_contact
        or str(latest_activity["created_at"] or "") > str(last_contact["date"] or "")
    ):
        last_contact = {
            "type": latest_activity["action"],
            "date": latest_activity["created_at"],
            "text": latest_activity["details"]
        }

    if latest_client_call:
        latest_call_date = latest_client_call["call_at"] or latest_client_call["created_at"]

        if (
            not last_contact
            or str(latest_call_date or "") > str(last_contact["date"] or "")
        ):
            last_contact = {
                "type": "Звонок",
                "date": latest_call_date,
                "text": latest_client_call["summary"] or latest_client_call["phone"] or ""
            }

    last_contact_age_days = None

    if last_contact:
        last_contact_dt = parse_client_health_datetime(last_contact["date"])

        if last_contact_dt:
            last_contact_age_days = max(0, (now_dt - last_contact_dt).days)

    client_health_reasons = []
    client_health_score = 100

    if client_overdue_tasks:
        client_health_score -= min(35, client_overdue_tasks * 15)
        client_health_reasons.append({
            "label": f"Просроченных работ: {client_overdue_tasks}",
            "link": f"/clients/{client_id}?task_filter=overdue",
        })

    if client_sla_overdue_tasks:
        client_health_score -= min(35, client_sla_overdue_tasks * 20)
        client_health_reasons.append({
            "label": f"SLA просрочен: {client_sla_overdue_tasks}",
            "link": f"/clients/{client_id}?task_filter=sla_overdue&task_sort=date_asc",
        })

    if client_sla_due_soon_tasks:
        client_health_score -= min(15, client_sla_due_soon_tasks * 7)
        client_health_reasons.append({
            "label": f"SLA в ближайшие 24 часа: {client_sla_due_soon_tasks}",
            "link": f"/clients/{client_id}?task_filter=sla_soon&task_sort=date_asc",
        })

    if client_call_stats["follow_up"]:
        client_health_score -= min(20, client_call_stats["follow_up"] * 10)
        client_health_reasons.append({
            "label": f"Нужен контакт по звонкам: {client_call_stats['follow_up']}",
            "link": f"/clients/{client_id}?call_filter=follow_up#calls",
        })

    if client_call_stats["missed"]:
        client_health_score -= min(15, client_call_stats["missed"] * 7)
        client_health_reasons.append({
            "label": f"Пропущенных звонков: {client_call_stats['missed']}",
            "link": f"/clients/{client_id}?call_filter=missed#calls",
        })

    if client_unassigned_tasks:
        client_health_score -= min(15, client_unassigned_tasks * 5)
        client_health_reasons.append({
            "label": f"Без исполнителя: {client_unassigned_tasks}",
            "link": f"/clients/{client_id}?task_filter=unassigned",
        })

    if last_contact_age_days is None:
        client_health_score -= 10
        client_health_reasons.append({
            "label": "Контактов ещё не было",
            "link": f"/clients/{client_id}#calls",
        })
    elif last_contact_age_days >= 30:
        client_health_score -= 10
        client_health_reasons.append({
            "label": f"Последний контакт {last_contact_age_days} дн. назад",
            "link": f"/clients/{client_id}#calls",
        })

    client_health_score = max(0, min(100, client_health_score))

    if client_overdue_tasks or client_sla_overdue_tasks:
        client_health_status_key = "risk"
        client_health_status_label = "Риск"
        client_health_summary = "Есть просрочки или нарушенный SLA. Начните с проблемных работ."
    elif client_health_reasons:
        client_health_status_key = "attention"
        client_health_status_label = "Нужна реакция"
        client_health_summary = "Есть сигналы, которые лучше обработать до следующего визита."
    else:
        client_health_status_key = "stable"
        client_health_status_label = "Стабильно"
        client_health_summary = "Критичных сигналов по клиенту нет."

    client_health = {
        "score": client_health_score,
        "status_key": client_health_status_key,
        "status_label": client_health_status_label,
        "summary": client_health_summary,
        "reasons": client_health_reasons,
        "last_contact_age_days": last_contact_age_days,
        "sla_overdue_tasks": client_sla_overdue_tasks,
        "sla_due_soon_tasks": client_sla_due_soon_tasks,
        "unassigned_tasks": client_unassigned_tasks,
    }

    if selected_activity_filter:
        filtered_timeline = []

        for item in client_timeline:
            action = str(item["action"] or "").lower()

            if selected_activity_filter == "status" and "статус" not in action:
                continue

            if selected_activity_filter == "date" and "дат" not in action and "срок" not in action:
                continue

            if selected_activity_filter == "comment" and "коммент" not in action:
                continue

            filtered_timeline.append(item)

        client_timeline = filtered_timeline

    client_files = c.execute("""
    SELECT *
    FROM client_files
    WHERE client_id=? AND company_id=?
    ORDER BY id DESC
    """, (client_id, company_id)).fetchall()
    client_file_count = len(client_files)

    if file_search_value:
        client_files = [
            client_file for client_file in client_files
            if file_search_value in " ".join([
                str(client_file["original_filename"] or ""),
                str(client_file["username"] or ""),
                str(client_file["content_type"] or "")
            ]).lower()
        ]

    client_custom_fields = c.execute("""
    SELECT custom_fields.id, custom_fields.label, custom_fields.field_type, custom_fields.options, custom_field_values.value
    FROM custom_fields
    LEFT JOIN custom_field_values
      ON custom_field_values.field_id=custom_fields.id
      AND custom_field_values.company_id=custom_fields.company_id
      AND custom_field_values.entity_type='client'
      AND custom_field_values.entity_id=?
    WHERE custom_fields.company_id=?
      AND custom_fields.entity_type='client'
      AND custom_fields.active=1
    ORDER BY custom_fields.sort_order, custom_fields.id
    """, (client_id, company_id)).fetchall()

    conn.close()

    return templates.TemplateResponse(
        request,
        "client_detail.html",
        {
            "request": request,
            "username": username,
            "role": role,
            "client": client,
            "tasks": filtered_tasks,
            "latest_task": latest_task,
            "upcoming_task": upcoming_task,
            "client_task_workers": client_task_workers,
            "shown_task_count": len(filtered_tasks),
            "selected_task_filter": selected_task_filter,
            "selected_task_search": selected_task_search,
            "selected_task_sort": selected_task_sort,
            "selected_activity_filter": selected_activity_filter,
            "selected_note_search": selected_note_search,
            "selected_file_search": selected_file_search,
            "selected_call_filter": selected_call_filter,
            "selected_call_content": selected_call_content,
            "client_notes": client_notes,
            "client_files": client_files,
            "latest_client_note": latest_client_note,
            "client_calls": client_calls,
            "latest_client_call": latest_client_call,
            "last_contact": last_contact,
            "client_next_action": client_next_action,
            "shown_note_count": len(client_notes),
            "client_note_count": client_note_count,
            "client_call_count": client_call_count,
            "client_call_stats": client_call_stats,
            "client_calls_enabled": bool(settings and settings["calls_enabled"]),
            "shown_file_count": len(client_files),
            "client_file_count": client_file_count,
            "shown_activity_count": len(client_timeline),
            "client_total_tasks": client_total_tasks,
            "client_now_value": client_now_value,
            "client_active_tasks": client_active_tasks,
            "client_completed_tasks": client_completed_tasks,
            "client_overdue_tasks": client_overdue_tasks,
            "client_health": client_health,
            "client_revenue": client_revenue,
            "client_timeline": client_timeline,
            "client_custom_fields": client_custom_fields,
            "settings": settings
        }
    )


@router.get("/clients/{client_id}/export")
async def client_detail_export(request: Request, client_id: int):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role not in ("boss", "manager"):
        return RedirectResponse("/", status_code=302)

    company_id, missing_company_response = require_route_company_context(username, role)

    if missing_company_response:
        return missing_company_response

    disabled_response = require_feature(company_id, "clients")

    if disabled_response:
        return disabled_response

    settings = get_company_settings(company_id)
    task_label = settings["task_label"] or "Заявка"
    worker_label = settings["worker_label"] or "Исполнитель"
    client_label = settings["client_label"] or "Клиент"

    conn = connect()
    c = conn.cursor()

    client = c.execute("""
    SELECT *
    FROM clients
    WHERE id=? AND company_id=?
    """, (client_id, company_id)).fetchone()

    if not client:
        conn.close()
        return RedirectResponse("/clients", status_code=302)

    tasks = c.execute("""
    SELECT *
    FROM tasks
    WHERE client_id=? AND company_id=?
    ORDER BY id DESC
    """, (client_id, company_id)).fetchall()

    client_notes = c.execute("""
    SELECT *
    FROM client_notes
    WHERE client_id=? AND company_id=?
    ORDER BY id DESC
    """, (client_id, company_id)).fetchall()

    client_files = c.execute("""
    SELECT *
    FROM client_files
    WHERE client_id=? AND company_id=?
    ORDER BY id DESC
    """, (client_id, company_id)).fetchall()

    client_calls = c.execute("""
    SELECT *
    FROM call_records
    WHERE client_id=? AND company_id=?
    ORDER BY COALESCE(call_at, created_at) DESC, id DESC
    """, (client_id, company_id)).fetchall()

    client_timeline = c.execute("""
    SELECT
        task_activity.*,
        tasks.id AS task_id,
        tasks.status AS task_status
    FROM task_activity
    JOIN tasks ON tasks.id=task_activity.task_id
    WHERE tasks.client_id=?
      AND tasks.company_id=?
    ORDER BY task_activity.id DESC
    """, (client_id, company_id)).fetchall()

    client_custom_fields = c.execute("""
    SELECT custom_fields.label, custom_field_values.value
    FROM custom_fields
    LEFT JOIN custom_field_values
      ON custom_field_values.field_id=custom_fields.id
      AND custom_field_values.company_id=custom_fields.company_id
      AND custom_field_values.entity_type='client'
      AND custom_field_values.entity_id=?
    WHERE custom_fields.company_id=?
      AND custom_fields.entity_type='client'
      AND custom_fields.active=1
    ORDER BY custom_fields.sort_order, custom_fields.id
    """, (client_id, company_id)).fetchall()

    conn.close()

    output = io.StringIO()
    writer = csv.writer(output)

    writer.writerow([f"Карточка: {client_label}"])
    writer.writerow(["ID", client["id"]])
    writer.writerow([client_label, client["name"] or ""])
    writer.writerow(["Телефон", client["phone"] or ""])
    writer.writerow(["Электронная почта", client["email"] or ""])
    writer.writerow(["Адрес", client["address"] or ""])
    writer.writerow(["Заметки", client["notes"] or ""])
    writer.writerow(["Создан", client["created_at"] or ""])
    writer.writerow(["Экспортировано", datetime.now().strftime("%Y-%m-%d %H:%M")])

    if client_custom_fields:
        writer.writerow([])
        writer.writerow(["Дополнительные поля"])
        writer.writerow(["Поле", "Значение"])

        for field in client_custom_fields:
            writer.writerow([
                field["label"] or "",
                field["value"] or "",
            ])

    writer.writerow([])
    writer.writerow([f"{task_label}: история"])
    writer.writerow([
        "ID",
        "Дата",
        "Статус",
        worker_label,
        "Приоритет",
        "Стоимость",
        "SLA",
        "Описание",
        "Адрес",
    ])

    for task in tasks:
        writer.writerow([
            task["id"],
            task["task_date"] or "",
            task["status"] or "",
            format_task_workers(task),
            task["priority"] or "",
            task["price"] or "",
            task["deadline_at"] or "",
            task["description"] or "",
            task["address"] or "",
        ])

    writer.writerow([])
    writer.writerow(["Заметки"])
    writer.writerow(["Дата", "Автор", "Роль", "Текст"])

    for note in client_notes:
        writer.writerow([
            note["created_at"] or "",
            note["username"] or "",
            role_label(note["role"]),
            note["note"] or "",
        ])

    writer.writerow([])
    writer.writerow(["Звонки"])
    writer.writerow([
        "Дата",
        "Направление",
        "Статус",
        "Телефон",
        "Длительность, минут",
        "Заметка",
        "Расшифровка",
        "ИИ-резюме",
        "Автор",
    ])

    call_direction_labels = {
        "incoming": "Входящий",
        "outgoing": "Исходящий",
    }
    call_status_labels = {
        "completed": "Состоялся",
        "missed": "Пропущен",
        "follow_up": "Нужен контакт",
    }

    for call in client_calls:
        writer.writerow([
            call["call_at"] or call["created_at"] or "",
            call_direction_labels.get(call["direction"], call["direction"] or ""),
            call_status_labels.get(call["status"], call["status"] or ""),
            call["phone"] or "",
            call["duration_minutes"] or 0,
            call["summary"] or "",
            call["transcript"] or "",
            call["ai_summary"] or "",
            call["username"] or "",
        ])

    writer.writerow([])
    writer.writerow(["Файлы"])
    writer.writerow(["Дата", "Файл", "Тип", "Автор"])

    for client_file in client_files:
        writer.writerow([
            client_file["created_at"] or "",
            client_file["original_filename"] or "",
            client_file["content_type"] or "",
            client_file["username"] or "",
        ])

    writer.writerow([])
    writer.writerow(["Лента активности"])
    writer.writerow(["Дата", task_label, "Действие", "Детали"])

    for item in client_timeline:
        writer.writerow([
            item["created_at"] or "",
            item["task_id"] or "",
            ui_text(item["action"] or ""),
            ui_text(item["details"] or ""),
        ])

    return Response(
        content="\ufeff" + output.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f"attachment; filename=client_{client_id}_card.csv"
        }
    )


@router.post("/clients/{client_id}/calls")
async def add_client_call(request: Request, client_id: int):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role not in ("boss", "manager"):
        return RedirectResponse("/", status_code=302)

    company_id, missing_company_response = require_route_company_context(username, role)

    if missing_company_response:
        return missing_company_response

    disabled_response = require_feature(company_id, "calls")

    if disabled_response:
        return disabled_response

    settings = get_company_settings(company_id)

    if not settings or not settings["calls_enabled"]:
        return RedirectResponse(f"/clients/{client_id}?call_error=disabled", status_code=302)

    form = await request.form()
    phone = str(form.get("phone") or "").strip()[:80]
    summary = str(form.get("summary") or "").strip()[:1000]
    direction = str(form.get("direction") or "outgoing").strip()
    status = str(form.get("status") or "completed").strip()
    call_at = str(form.get("call_at") or "").strip().replace("T", " ")

    if direction not in ("incoming", "outgoing"):
        direction = "outgoing"

    if status not in ("completed", "missed", "follow_up"):
        status = "completed"

    try:
        duration_minutes = int(str(form.get("duration_minutes") or "0"))
    except ValueError:
        duration_minutes = 0

    duration_minutes = max(0, min(duration_minutes, 1440))

    conn = connect()
    c = conn.cursor()

    client = c.execute("""
    SELECT id, name, phone
    FROM clients
    WHERE id=? AND company_id=?
    """, (client_id, company_id)).fetchone()

    if not client:
        conn.close()
        return RedirectResponse("/clients", status_code=302)

    if not phone:
        phone = str(client["phone"] or "").strip()[:80]

    if not call_at:
        call_at = datetime.now().strftime("%Y-%m-%d %H:%M")

    if not phone and not summary:
        conn.close()
        return RedirectResponse(f"/clients/{client_id}?call_error=empty", status_code=302)

    c.execute("""
    INSERT INTO call_records (
        company_id,
        client_id,
        username,
        direction,
        status,
        phone,
        summary,
        call_at,
        duration_minutes,
        created_at
    )
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        company_id,
        client_id,
        username,
        direction,
        status,
        phone,
        summary,
        call_at,
        duration_minutes,
        datetime.now().strftime("%Y-%m-%d %H:%M")
    ))
    call_id = c.lastrowid

    conn.commit()
    conn.close()

    if status == "follow_up":
        create_call_follow_up_notification(
            company_id,
            username,
            client["name"],
            client_id,
            summary,
            phone,
            call_id,
        )
        run_automation_event(
            company_id,
            "call_follow_up_created",
            "call",
            call_id,
            f"Нужен контакт по звонку #{call_id}: {summary or phone}",
            f"/calls/{call_id}",
        )

    return RedirectResponse(f"/clients/{client_id}?call_created=1", status_code=302)


@router.post("/clients/{client_id}/notes")
async def add_client_note(request: Request, client_id: int):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role not in ("boss", "manager"):
        return RedirectResponse("/", status_code=302)

    company_id = get_user_company_id(username)

    form = await request.form()
    note = (form.get("note") or "").strip()

    if not note:
        return RedirectResponse(f"/clients/{client_id}?note_error=empty", status_code=302)

    conn = connect()
    c = conn.cursor()

    client = c.execute("""
    SELECT *
    FROM clients
    WHERE id=? AND company_id=?
    """, (client_id, company_id)).fetchone()

    if not client:
        conn.close()
        return RedirectResponse("/clients", status_code=302)

    c.execute("""
    INSERT INTO client_notes (
        company_id,
        client_id,
        username,
        role,
        note,
        created_at
    )
    VALUES (?, ?, ?, ?, ?, ?)
    """, (
        company_id,
        client_id,
        username,
        role,
        note,
        datetime.now().strftime("%Y-%m-%d %H:%M")
    ))

    conn.commit()
    conn.close()

    try:
        send_message(
            f"""
📝 Новая заметка по клиенту

Клиент: {client['name']}
Автор: {username} ({get_role_title(role)})

Заметка:
{note}
"""
        )
    except Exception:
        pass

    run_automation_event(
        company_id,
        "client_note_added",
        "client",
        client_id,
        f"Добавлена заметка по клиенту: {client['name']}",
        f"/clients/{client_id}",
    )

    return RedirectResponse(f"/clients/{client_id}?note_created=1", status_code=302)


@router.post("/clients/{client_id}/files")
async def upload_client_file(
    request: Request,
    client_id: int,
    upload: UploadFile = File(None)
):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role not in ("boss", "manager"):
        return RedirectResponse("/", status_code=302)

    company_id = get_user_company_id(username)

    conn = connect()
    c = conn.cursor()

    client = c.execute("""
    SELECT id
    FROM clients
    WHERE id=? AND company_id=?
    """, (client_id, company_id)).fetchone()

    if not client:
        conn.close()
        return RedirectResponse("/clients", status_code=302)

    if not upload or not upload.filename:
        conn.close()
        return RedirectResponse(f"/clients/{client_id}?file_error=empty", status_code=302)

    try:
        validate_upload_file(
            upload,
            ALLOWED_CLIENT_FILE_EXTENSIONS,
            CLIENT_FILE_UPLOAD_MAX_BYTES,
        )
    except UploadValidationError as error:
        conn.close()
        return RedirectResponse(
            f"/clients/{client_id}?file_error={error.code}",
            status_code=302,
        )

    original_filename = Path(upload.filename).name
    stored_filename = safe_client_file_filename(client_id, original_filename)
    safe_content_type = (
        mimetypes.guess_type(stored_filename)[0]
        or "application/octet-stream"
    )
    try:
        save_storage_fileobj(
            upload.file,
            f"client_files/{stored_filename}",
            UPLOAD_DIR,
            safe_content_type,
        )
    except ObjectStorageError:
        conn.close()
        return RedirectResponse(
            f"/clients/{client_id}?file_error=storage",
            status_code=302,
        )

    c.execute("""
    INSERT INTO client_files (
        company_id,
        client_id,
        username,
        original_filename,
        stored_filename,
        content_type,
        created_at
    )
    VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        company_id,
        client_id,
        username,
        original_filename,
        stored_filename,
        safe_content_type,
        datetime.now().strftime("%Y-%m-%d %H:%M")
    ))

    conn.commit()
    conn.close()

    run_automation_event(
        company_id,
        "client_file_uploaded",
        "client",
        client_id,
        f"Загружен файл клиента: {original_filename}",
        f"/clients/{client_id}",
    )

    return RedirectResponse(f"/clients/{client_id}?file_uploaded=1", status_code=302)


@router.get("/clients/{client_id}/files/{file_id}")
async def download_client_file(request: Request, client_id: int, file_id: int):

    username = get_user(request)

    if not username:
        return Response(status_code=404)

    role = get_role(username)

    if role not in ("boss", "manager"):
        return Response(status_code=404)

    company_id = get_user_company_id(username)

    conn = connect()
    c = conn.cursor()

    client_file = c.execute("""
    SELECT *
    FROM client_files
    WHERE id=?
      AND client_id=?
      AND company_id=?
    """, (file_id, client_id, company_id)).fetchone()

    conn.close()

    if not client_file:
        return Response(status_code=404)

    stored_filename = Path(client_file["stored_filename"] or "").name
    if not stored_filename:
        return Response(status_code=404)

    return storage_file_response(
        f"client_files/{stored_filename}",
        UPLOAD_DIR,
        download_name=client_file["original_filename"] or stored_filename,
        media_type=client_file["content_type"] or "",
        request=request,
    )


@router.post("/clients/{client_id}/files/{file_id}/delete")
async def delete_client_file(request: Request, client_id: int, file_id: int):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role not in ("boss", "manager"):
        return RedirectResponse("/", status_code=302)

    company_id = get_user_company_id(username)

    conn = connect()
    c = conn.cursor()

    client_file = c.execute("""
    SELECT *
    FROM client_files
    WHERE id=?
      AND client_id=?
      AND company_id=?
    """, (file_id, client_id, company_id)).fetchone()

    if not client_file:
        conn.close()
        return RedirectResponse(f"/clients/{client_id}", status_code=302)

    stored_filename = Path(client_file["stored_filename"] or "").name

    c.execute("""
    DELETE FROM client_files
    WHERE id=? AND client_id=? AND company_id=?
    """, (file_id, client_id, company_id))
    conn.commit()
    conn.close()

    if stored_filename:
        try:
            delete_storage_object(
                f"client_files/{stored_filename}",
                UPLOAD_DIR,
            )
        except (ObjectStorageError, ValueError):
            pass

    run_automation_event(
        company_id,
        "client_file_deleted",
        "client",
        client_id,
        (
            "Удалён файл клиента: "
            f"{client_file['original_filename'] or stored_filename}"
        ),
        f"/clients/{client_id}",
    )

    return RedirectResponse(f"/clients/{client_id}?file_deleted=1", status_code=302)


@router.post("/clients/{client_id}/edit")
async def edit_client(request: Request, client_id: int):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role not in ("boss", "manager"):
        return RedirectResponse("/", status_code=302)

    company_id = get_user_company_id(username)

    form = await request.form()

    name = (form.get("name") or "").strip()
    phone = (form.get("phone") or "").strip()
    email = (form.get("email") or "").strip()
    telegram_chat_id = (form.get("telegram_chat_id") or "").strip()
    address = (form.get("address") or "").strip()
    notes = (form.get("notes") or "").strip()

    if not name:
        return RedirectResponse(f"/clients/{client_id}?error=empty", status_code=302)

    conn = connect()
    c = conn.cursor()

    client = c.execute("""
    SELECT *
    FROM clients
    WHERE id=? AND company_id=?
    """, (client_id, company_id)).fetchone()

    if not client:
        conn.close()
        return RedirectResponse("/clients", status_code=302)

    custom_fields = c.execute("""
    SELECT *
    FROM custom_fields
    WHERE company_id=?
      AND entity_type='client'
      AND active=1
    ORDER BY sort_order, id
    """, (company_id,)).fetchall()

    for custom_field in custom_fields:
        field_name = f"custom_field_{custom_field['id']}"
        custom_value = (form.get(field_name) or "").strip()

        if custom_field["is_required"] and not custom_value:
            conn.close()
            return RedirectResponse(f"/clients/{client_id}?error=custom_required", status_code=302)

    c.execute("""
    UPDATE clients
    SET name=?, phone=?, email=?, address=?, notes=?
    WHERE id=? AND company_id=?
    """, (
        name,
        phone,
        email,
        address,
        notes,
        client_id,
        company_id
    ))

    changed_custom_fields = []

    for custom_field in custom_fields:
        field_name = f"custom_field_{custom_field['id']}"
        custom_value = (form.get(field_name) or "").strip()
        existing_value = c.execute("""
        SELECT *
        FROM custom_field_values
        WHERE company_id=?
          AND field_id=?
          AND entity_type='client'
          AND entity_id=?
        """, (company_id, custom_field["id"], client_id)).fetchone()

        previous_value = (existing_value["value"] if existing_value else "").strip()

        if custom_value != previous_value:
            changed_custom_fields.append((custom_field["label"], custom_value))

        if custom_value:
            if existing_value:
                c.execute("""
                UPDATE custom_field_values
                SET value=?
                WHERE id=?
                """, (custom_value, existing_value["id"]))
            else:
                c.execute("""
                INSERT INTO custom_field_values (
                    company_id,
                    field_id,
                    entity_type,
                    entity_id,
                    value,
                    created_at
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """, (
                    company_id,
                    custom_field["id"],
                    "client",
                    client_id,
                    custom_value,
                    datetime.now().strftime("%Y-%m-%d %H:%M")
                ))
        elif existing_value and not custom_field["is_required"]:
            c.execute("""
            DELETE FROM custom_field_values
            WHERE id=?
            """, (existing_value["id"],))

    linked_tasks = c.execute("""
    SELECT id
    FROM tasks
    WHERE client_id=? AND company_id=?
    """, (client_id, company_id)).fetchall()

    conn.commit()
    conn.close()

    for task in linked_tasks:
        try:
            log_task_activity(
                task["id"],
                username,
                role,
                "Обновлена карточка клиента",
                name
            )
        except Exception:
            pass

    try:
        send_message(
            f"""
👤 Карточка клиента обновлена

Клиент: {name}
Телефон: {phone}
Электронная почта: {email}
Адрес: {address}

Изменил: {username} ({get_role_title(role)})
"""
        )
    except Exception:
        pass

    run_automation_event(
        company_id,
        "client_updated",
        "client",
        client_id,
        f"Обновлена карточка клиента: {name}",
        f"/clients/{client_id}",
    )

    if changed_custom_fields:
        changed_fields_preview = ", ".join(
            f"{label}: {value or 'очищено'}"
            for label, value in changed_custom_fields
        )

        run_automation_event(
            company_id,
            "client_custom_field_updated",
            "client",
            client_id,
            f"Поля клиента изменены: {changed_fields_preview}",
            f"/clients/{client_id}",
        )

    return RedirectResponse(f"/clients/{client_id}?updated=1", status_code=302)


@router.post("/clients")
async def create_client(request: Request):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role not in ("boss", "manager"):
        return RedirectResponse("/", status_code=302)

    form = await request.form()

    name = (form.get("name") or "").strip()
    phone = (form.get("phone") or "").strip()
    email = (form.get("email") or "").strip()
    telegram_chat_id = (form.get("telegram_chat_id") or "").strip()
    address = (form.get("address") or "").strip()
    notes = (form.get("notes") or "").strip()

    if not name:
        return RedirectResponse("/clients?error=empty", status_code=302)

    company_id = get_user_company_id(username)

    conn = connect()
    c = conn.cursor()

    custom_fields = c.execute("""
    SELECT *
    FROM custom_fields
    WHERE company_id=?
      AND entity_type='client'
      AND active=1
    ORDER BY sort_order, id
    """, (company_id,)).fetchall()

    for custom_field in custom_fields:
        field_name = f"custom_field_{custom_field['id']}"
        custom_value = (form.get(field_name) or "").strip()

        if custom_field["is_required"] and not custom_value:
            conn.close()
            return RedirectResponse("/clients?error=custom_required", status_code=302)

    c.execute("""
    INSERT INTO clients (
        company_id,
        name,
        phone,
        email,
        address,
        notes,
        created_at
    )
    VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        company_id,
        name,
        phone,
        email,
        address,
        notes,
        datetime.now().strftime("%Y-%m-%d %H:%M")
    ))

    conn.commit()
    client_id = c.lastrowid

    for custom_field in custom_fields:
        field_name = f"custom_field_{custom_field['id']}"
        custom_value = (form.get(field_name) or "").strip()

        if not custom_value:
            continue

        c.execute("""
        INSERT INTO custom_field_values (
            company_id,
            field_id,
            entity_type,
            entity_id,
            value,
            created_at
        )
        VALUES (?, ?, ?, ?, ?, ?)
        """, (
            company_id,
            custom_field["id"],
            "client",
            client_id,
            custom_value,
            datetime.now().strftime("%Y-%m-%d %H:%M")
        ))

    if custom_fields:
        conn.commit()

    conn.close()

    try:
        send_message(
            f"""
👤 Новый клиент

Имя: {name}
Телефон: {phone}
Адрес: {address}

Создал: {username} ({get_role_title(role)})
"""
        )
    except Exception:
        pass

    run_automation_event(
        company_id,
        "new_client",
        "client",
        client_id,
        f"Создан новый клиент: {name}",
        f"/clients/{client_id}",
    )

    return RedirectResponse("/clients?created=1", status_code=302)
