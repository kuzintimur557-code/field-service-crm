"""Task routes: creation, details, items, expenses, status, photos, documents."""

import mimetypes
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import urlencode

from fastapi import APIRouter, File, Request, UploadFile
from fastapi.responses import (
    FileResponse,
    HTMLResponse,
    RedirectResponse,
    Response,
)
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

from app.database import connect
from app.deps import (
    get_role,
    get_user,
    get_user_company_id,
    get_user_session_version,
    update_last_seen,
)
from app.object_storage import ObjectStorageError
from app.services.common import (
    build_dashboard_links,
    can_access_task,
    create_notification,
    format_task_workers,
    get_company_features,
    get_company_settings,
    get_role_title,
    get_task_company_id,
    get_task_worker_chat_ids,
    get_task_worker_names,
    has_feature,
    log_task_activity,
    require_feature,
    role_label,
    task_has_worker,
    worker_task_condition,
    worker_task_params,
)
from app.services.daily_schedule import (
    find_time_conflicts,
    normalize_time_window,
)
from app.services.smart_scheduling import build_scheduling_recommendations
from app.templating import templates
from app.uploads import (
    ALLOWED_IMAGE_EXTENSIONS,
    DOCS_DIR,
    IMAGE_UPLOAD_MAX_BYTES,
    UPLOAD_DIR,
    UploadValidationError,
    save_upload_file,
    storage_file_response,
    validate_upload_file,
)

router = APIRouter()


def send_message(*args, **kwargs):
    from app.main import send_message as _impl

    return _impl(*args, **kwargs)


def send_message_to_chat(*args, **kwargs):
    from app.main import send_message_to_chat as _impl

    return _impl(*args, **kwargs)


def send_photo(*args, **kwargs):
    from app.main import send_photo as _impl

    return _impl(*args, **kwargs)


def run_automation_event(*args, **kwargs):
    from app.main import run_automation_event as _impl

    return _impl(*args, **kwargs)


def register_pdf_font():
    from app.main import register_pdf_font as _impl

    return _impl()


def draw_text(*args, **kwargs):
    from app.main import draw_text as _impl

    return _impl(*args, **kwargs)


def draw_pdf_image(*args, **kwargs):
    from app.main import draw_pdf_image as _impl

    return _impl(*args, **kwargs)


def get_worker_unavailability(*args, **kwargs):
    from app.main import get_worker_unavailability as _impl

    return _impl(*args, **kwargs)


def get_worker_unavailable_reasons(*args, **kwargs):
    from app.main import get_worker_unavailable_reasons as _impl

    return _impl(*args, **kwargs)
    from app.main import run_automation_event as _impl

    return _impl(*args, **kwargs)


def get_worker_unavailability(*args, **kwargs):
    from app.main import get_worker_unavailability as _impl

    return _impl(*args, **kwargs)


def get_worker_unavailable_reasons(*args, **kwargs):
    from app.main import get_worker_unavailable_reasons as _impl

    return _impl(*args, **kwargs)
    from app.main import run_automation_event as _impl

    return _impl(*args, **kwargs)


def _worker_capacity_helpers():
    from app.main import (
        get_worker_unavailability,
        get_worker_unavailable_reasons,
    )

    return get_worker_unavailability, get_worker_unavailable_reasons

@router.get("/create-task", response_class=HTMLResponse)
async def create_task_page(
    request: Request,
    task_date: str = "",
    time_from: str = "",
    time_to: str = "",
    worker: str = "",
    workers_csv: str = "",
    return_to: str = "",
    client_id: int = 0,
    note_id: int = 0,
    source_task_id: int = 0,
    ai_note_id: int = 0,
    call_id: int = 0
):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    update_last_seen(username)
    role = get_role(username)

    if role == "superadmin":
        return RedirectResponse("/platform", status_code=302)

    if role not in ("boss", "manager"):
        return RedirectResponse("/", status_code=302)

    company_id = get_user_company_id(username)
    selected_task_date = str(task_date or "").strip()

    try:
        if selected_task_date:
            datetime.strptime(selected_task_date, "%Y-%m-%d")
    except Exception:
        selected_task_date = ""

    selected_time_from, selected_time_to, _ = normalize_time_window(
        time_from,
        time_to,
    )
    conn = connect()
    c = conn.cursor()

    workers = c.execute("""
    SELECT username, daily_capacity FROM users
    WHERE role='worker'
      AND company_id=?
      AND COALESCE(is_active, 1)=1
    ORDER BY username
    """, (company_id,)).fetchall()
    worker_names = [row["username"] for row in workers]
    worker_capacity_map = {
        row["username"]: max(1, int(row["daily_capacity"] or 3))
        for row in workers
    }
    daily_counts = {worker_name: 0 for worker_name in worker_names}
    unavailable_dates = {}
    unavailable_reasons = {}

    if selected_task_date:
        daily_rows = c.execute("""
        SELECT worker, workers
        FROM tasks
        WHERE archived=0
          AND company_id=?
          AND task_date LIKE ?
          AND status NOT IN ('Завершено', 'Отменено')
        """, (company_id, f"{selected_task_date}%")).fetchall()

        for daily_task in daily_rows:
            for worker_name in get_task_worker_names(daily_task):
                if worker_name in daily_counts:
                    daily_counts[worker_name] += 1

        unavailable_dates, unavailable_reasons = get_worker_unavailability(
            c,
            company_id,
            worker_names,
            selected_task_date,
            selected_task_date,
        )

    worker_options = []

    for worker_name in worker_names:
        daily_capacity = worker_capacity_map[worker_name]
        active_count = daily_counts[worker_name]
        available_slots = max(daily_capacity - active_count, 0)
        is_unavailable = (
            selected_task_date
            and selected_task_date
            in unavailable_dates.get(worker_name, set())
        )

        if is_unavailable:
            available_slots = 0

        worker_options.append({
            "username": worker_name,
            "active_count": active_count,
            "daily_capacity": daily_capacity,
            "available_slots": available_slots,
            "is_at_capacity": available_slots == 0 and not is_unavailable,
            "is_unavailable": is_unavailable,
            "unavailable_reason": unavailable_reasons.get(
                (worker_name, selected_task_date),
                "",
            ),
        })

    selected_workers = [
        worker_name
        for worker_name in dict.fromkeys(
            part.strip()
            for part in str(workers_csv or "").split(",")
            if part.strip()
        )
        if worker_name in worker_names
    ]
    selected_worker = str(worker or "").strip()
    selected_return_to = return_to if return_to in ("calendar", "client") else ""
    selected_worker_active_count = 0
    selected_worker_active_tasks = []
    selected_worker_daily_capacity = 0
    selected_worker_available_slots = 0
    selected_worker_at_capacity = False
    selected_worker_unavailable = False
    selected_worker_unavailable_reason = ""
    recommended_worker = None
    selected_client = None
    selected_address = ""
    selected_description = ""
    selected_note_id = 0
    selected_source_task_id = 0
    selected_ai_note_id = 0
    selected_call_id = 0

    if selected_worker in worker_names:
        if selected_worker not in selected_workers:
            selected_workers.insert(0, selected_worker)
        selected_worker_daily_capacity = worker_capacity_map[selected_worker]

        if selected_task_date:
            selected_worker_active_tasks = c.execute(f"""
            SELECT id, client, status, task_date
            FROM tasks
            WHERE archived=0
              AND company_id=?
              AND task_date LIKE ?
              AND status NOT IN ('Завершено', 'Отменено')
              AND {worker_task_condition()}
            ORDER BY task_date ASC, id DESC
            """, [company_id, f"{selected_task_date}%", *worker_task_params(selected_worker)]).fetchall()
            selected_worker_active_count = daily_counts[selected_worker]
            selected_worker_available_slots = max(
                selected_worker_daily_capacity
                - selected_worker_active_count,
                0,
            )
            selected_worker_at_capacity = (
                selected_worker_active_count
                >= selected_worker_daily_capacity
            )
            selected_worker_unavailable = (
                selected_task_date
                in unavailable_dates.get(selected_worker, set())
            )
            selected_worker_unavailable_reason = unavailable_reasons.get(
                (selected_worker, selected_task_date),
                "",
            )

            if selected_worker_unavailable:
                selected_worker_available_slots = 0

            if selected_worker_active_count > 0 or selected_worker_unavailable:
                alternatives = []

                for worker_name, active_count in daily_counts.items():
                    if worker_name == selected_worker:
                        continue

                    if (
                        selected_task_date
                        in unavailable_dates.get(worker_name, set())
                    ):
                        continue

                    worker_capacity = worker_capacity_map[worker_name]
                    available_slots = max(
                        worker_capacity - active_count,
                        0,
                    )

                    if available_slots <= 0:
                        continue

                    alternatives.append({
                        "username": worker_name,
                        "active_count": active_count,
                        "daily_capacity": worker_capacity,
                        "available_slots": available_slots,
                    })

                alternatives.sort(key=lambda item: (
                    item["active_count"] / item["daily_capacity"],
                    item["active_count"],
                    item["username"],
                ))
                recommended_worker = (
                    alternatives[0] if alternatives else None
                )

                if recommended_worker:
                    switch_params = {
                        "task_date": selected_task_date,
                        "worker": recommended_worker["username"],
                    }

                    if selected_time_from and selected_time_to:
                        switch_params["time_from"] = selected_time_from
                        switch_params["time_to"] = selected_time_to

                    if selected_return_to:
                        switch_params["return_to"] = selected_return_to

                    if client_id:
                        switch_params["client_id"] = client_id

                    if source_task_id:
                        switch_params["source_task_id"] = source_task_id

                    if ai_note_id:
                        switch_params["ai_note_id"] = ai_note_id

                    if call_id:
                        switch_params["call_id"] = call_id

                    recommended_worker["switch_url"] = f"/create-task?{urlencode(switch_params)}"

    clients = c.execute("""
    SELECT *
    FROM clients
    WHERE company_id=?
    ORDER BY name
    """, (company_id,)).fetchall()

    if client_id:
        selected_client = c.execute("""
        SELECT *
        FROM clients
        WHERE id=? AND company_id=?
        """, (client_id, company_id)).fetchone()

        if selected_client:
            selected_address = selected_client["address"] or ""

        if selected_client and source_task_id:
            source_task = c.execute("""
            SELECT *
            FROM tasks
            WHERE id=?
              AND client_id=?
              AND company_id=?
            """, (source_task_id, client_id, company_id)).fetchone()

            if source_task:
                selected_address = source_task["address"] or selected_address
                selected_description = source_task["description"] or ""
                selected_source_task_id = source_task_id

                if not selected_workers:
                    selected_workers = [
                        worker_name for worker_name in get_task_worker_names(source_task)
                        if worker_name in worker_names
                    ]

        if selected_client and note_id:
            selected_note = c.execute("""
            SELECT note
            FROM client_notes
            WHERE id=?
              AND client_id=?
              AND company_id=?
            """, (note_id, client_id, company_id)).fetchone()

            if selected_note:
                selected_description = selected_note["note"] or ""
                selected_note_id = note_id

        if selected_client and call_id:
            selected_call = c.execute("""
            SELECT *
            FROM call_records
            WHERE id=?
              AND client_id=?
              AND company_id=?
            """, (call_id, client_id, company_id)).fetchone()

            if selected_call:
                call_parts = []

                if selected_call["summary"]:
                    call_parts.append(selected_call["summary"])

                if selected_call["ai_summary"]:
                    call_parts.append(f"ИИ-резюме: {selected_call['ai_summary']}")

                if selected_call["transcript"] and not call_parts:
                    call_parts.append(selected_call["transcript"])

                selected_description = "\n\n".join(call_parts) or selected_description
                selected_call_id = call_id

    if ai_note_id:
        selected_ai_note = c.execute("""
        SELECT *
        FROM ai_assistant_notes
        WHERE id=?
          AND company_id=?
          AND COALESCE(is_done, 0)=0
        """, (ai_note_id, company_id)).fetchone()

        if selected_ai_note:
            selected_description = selected_ai_note["note"] or selected_description
            selected_ai_note_id = ai_note_id

    settings = get_company_settings(company_id)

    custom_fields = c.execute("""
    SELECT *
    FROM custom_fields
    WHERE company_id=?
      AND entity_type='task'
      AND active=1
    ORDER BY sort_order, id
    """, (company_id,)).fetchall()

    conn.close()

    return templates.TemplateResponse(
        request=request,
        name="create_task.html",
        context={
            "username": username,
            "workers": workers,
            "worker_options": worker_options,
            "clients": clients,
            "custom_fields": custom_fields,
            "selected_client": selected_client,
            "selected_address": selected_address,
            "selected_description": selected_description,
            "selected_note_id": selected_note_id,
            "selected_source_task_id": selected_source_task_id,
            "selected_ai_note_id": selected_ai_note_id,
            "selected_call_id": selected_call_id,
            "selected_task_date": selected_task_date,
            "selected_time_from": selected_time_from,
            "selected_time_to": selected_time_to,
            "selected_workers": selected_workers,
            "selected_return_to": selected_return_to,
            "selected_worker_active_count": selected_worker_active_count,
            "selected_worker_active_tasks": selected_worker_active_tasks,
            "selected_worker_daily_capacity": selected_worker_daily_capacity,
            "selected_worker_available_slots": selected_worker_available_slots,
            "selected_worker_at_capacity": selected_worker_at_capacity,
            "selected_worker_unavailable": selected_worker_unavailable,
            "selected_worker_unavailable_reason": (
                selected_worker_unavailable_reason
            ),
            "recommended_worker": recommended_worker,
            "settings": settings
        }
    )



@router.post("/create-task")
async def create_task(
    request: Request,
    photo: UploadFile = File(None)
):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role not in ("boss", "manager"):
        return RedirectResponse("/", status_code=302)

    form = await request.form()

    client_id = form.get("client_id") or None
    client = form.get("client")
    phone = form.get("phone")
    address = form.get("address")
    description = form.get("description")
    task_date = form.get("task_date")
    time_from, time_to, time_error = normalize_time_window(
        form.get("time_from"),
        form.get("time_to"),
    )
    deadline_at = (form.get("deadline_at") or "").strip()
    selected_workers = form.getlist("workers")
    return_to = (form.get("return_to") or "").strip()
    note_id = (form.get("note_id") or "").strip()
    source_task_id = (form.get("source_task_id") or "").strip()
    ai_note_id = (form.get("ai_note_id") or "").strip()
    call_id = (form.get("call_id") or "").strip()
    allow_capacity_override = (
        form.get("allow_capacity_override") or ""
    ).strip() == "1"
    priority = form.get("priority")
    price = form.get("price")
    company_id = get_user_company_id(username)

    if time_error:
        error_params = {"error": "invalid_time"}

        if str(task_date or "")[:10]:
            error_params["task_date"] = str(task_date or "")[:10]

        return RedirectResponse(
            f"/create-task?{urlencode(error_params)}",
            status_code=302,
        )

    conn = connect()
    c = conn.cursor()

    custom_fields = c.execute("""
    SELECT *
    FROM custom_fields
    WHERE company_id=?
      AND entity_type='task'
      AND active=1
    ORDER BY sort_order, id
    """, (company_id,)).fetchall()

    for custom_field in custom_fields:
        field_name = f"custom_field_{custom_field['id']}"
        custom_value = (form.get(field_name) or "").strip()

        if custom_field["is_required"] and not custom_value:
            error_params = {"error": "custom_required"}
            selected_task_date = str(task_date or "")[:10]

            try:
                if selected_task_date:
                    datetime.strptime(selected_task_date, "%Y-%m-%d")
                    error_params["task_date"] = selected_task_date
            except Exception:
                pass

            if time_from:
                error_params["time_from"] = time_from

            if time_to:
                error_params["time_to"] = time_to

            selected_worker = next(
                (worker_name.strip() for worker_name in selected_workers if worker_name.strip()),
                ""
            )

            if selected_worker:
                error_params["worker"] = selected_worker

            if return_to == "calendar":
                error_params["return_to"] = "calendar"
            elif return_to == "client" and client_id:
                error_params["return_to"] = "client"
                error_params["client_id"] = client_id

                if note_id.isdigit():
                    note = c.execute("""
                    SELECT id
                    FROM client_notes
                    WHERE id=?
                      AND client_id=?
                      AND company_id=?
                    """, (int(note_id), client_id, company_id)).fetchone()

                    if note:
                        error_params["note_id"] = note_id

                if source_task_id.isdigit():
                    source_task = c.execute("""
                    SELECT id
                    FROM tasks
                    WHERE id=?
                      AND client_id=?
                      AND company_id=?
                    """, (int(source_task_id), client_id, company_id)).fetchone()

                    if source_task:
                        error_params["source_task_id"] = source_task_id

                if call_id.isdigit():
                    call = c.execute("""
                    SELECT id
                    FROM call_records
                    WHERE id=?
                      AND client_id=?
                      AND company_id=?
                    """, (int(call_id), client_id, company_id)).fetchone()

                    if call:
                        error_params["call_id"] = call_id

            if ai_note_id.isdigit():
                ai_note = c.execute("""
                SELECT id
                FROM ai_assistant_notes
                WHERE id=?
                  AND company_id=?
                  AND COALESCE(is_done, 0)=0
                """, (int(ai_note_id), company_id)).fetchone()

                if ai_note:
                    error_params["ai_note_id"] = ai_note_id

            conn.close()
            return RedirectResponse(f"/create-task?{urlencode(error_params)}", status_code=302)

    if client_id:
        submitted_address = (address or "").strip()
        existing_client = c.execute("""
        SELECT *
        FROM clients
        WHERE id=? AND company_id=?
        """, (client_id, company_id)).fetchone()

        if existing_client:
            client = existing_client["name"]
            phone = existing_client["phone"]
            address = submitted_address or existing_client["address"]

    source_call = None

    if call_id.isdigit() and client_id:
        source_call = c.execute("""
        SELECT id, summary
        FROM call_records
        WHERE id=?
          AND client_id=?
          AND company_id=?
        """, (int(call_id), client_id, company_id)).fetchone()

    valid_workers = []
    worker_chat_ids = []
    worker_capacity_map = {}

    for selected_worker in selected_workers:
        selected_worker = (selected_worker or "").strip()

        if not selected_worker:
            continue

        worker_user = c.execute("""
        SELECT username, telegram_chat_id, daily_capacity
        FROM users
        WHERE username=?
          AND role='worker'
          AND company_id=?
          AND COALESCE(is_active, 1)=1
        """, (selected_worker, company_id)).fetchone()

        if worker_user and worker_user["username"] not in valid_workers:
            valid_workers.append(worker_user["username"])
            worker_capacity_map[worker_user["username"]] = max(
                1,
                int(worker_user["daily_capacity"] or 3),
            )

            if worker_user["telegram_chat_id"]:
                worker_chat_ids.append(worker_user["telegram_chat_id"])

    worker = valid_workers[0] if valid_workers else ""
    workers_text = ",".join(valid_workers)
    over_capacity_workers = []
    unavailable_workers = []
    selected_task_date = str(task_date or "")[:10]

    try:
        if selected_task_date:
            datetime.strptime(selected_task_date, "%Y-%m-%d")
    except Exception:
        selected_task_date = ""

    if selected_task_date:
        unavailable_dates, unavailable_reasons = get_worker_unavailability(
            c,
            company_id,
            valid_workers,
            selected_task_date,
            selected_task_date,
        )

        for worker_name in valid_workers:
            if (
                selected_task_date
                in unavailable_dates.get(worker_name, set())
            ):
                unavailable_workers.append({
                    "username": worker_name,
                    "reason": unavailable_reasons.get(
                        (worker_name, selected_task_date),
                        "",
                    ),
                })
                continue

            active_count = c.execute(f"""
            SELECT COUNT(*)
            FROM tasks
            WHERE archived=0
              AND company_id=?
              AND task_date LIKE ?
              AND status NOT IN ('Завершено', 'Отменено')
              AND {worker_task_condition()}
            """, [
                company_id,
                f"{selected_task_date}%",
                *worker_task_params(worker_name),
            ]).fetchone()[0]
            daily_capacity = worker_capacity_map[worker_name]

            if active_count >= daily_capacity:
                over_capacity_workers.append({
                    "username": worker_name,
                    "active_count": active_count,
                    "daily_capacity": daily_capacity,
                })

    if unavailable_workers:
        error_params = {
            "error": "worker_unavailable",
            "task_date": selected_task_date,
            "worker": unavailable_workers[0]["username"],
            "workers_csv": ",".join(valid_workers),
        }

        if time_from and time_to:
            error_params["time_from"] = time_from
            error_params["time_to"] = time_to

        if return_to == "calendar":
            error_params["return_to"] = "calendar"
        elif return_to == "client" and client_id:
            error_params["return_to"] = "client"
            error_params["client_id"] = client_id

        conn.close()
        return RedirectResponse(
            f"/create-task?{urlencode(error_params)}",
            status_code=302,
        )

    if over_capacity_workers and not allow_capacity_override:
        error_params = {"error": "capacity_confirmation"}

        if selected_task_date:
            error_params["task_date"] = selected_task_date

        error_params["worker"] = over_capacity_workers[0]["username"]
        error_params["workers_csv"] = ",".join(valid_workers)

        if time_from and time_to:
            error_params["time_from"] = time_from
            error_params["time_to"] = time_to

        if return_to == "calendar":
            error_params["return_to"] = "calendar"
        elif return_to == "client" and client_id:
            error_params["return_to"] = "client"
            error_params["client_id"] = client_id

        conn.close()
        return RedirectResponse(
            f"/create-task?{urlencode(error_params)}",
            status_code=302,
        )

    if selected_task_date and valid_workers and time_from and time_to:
        day_tasks = c.execute("""
        SELECT *
        FROM tasks
        WHERE company_id=?
          AND archived=0
          AND status NOT IN ('Завершено', 'Отменено')
          AND task_date LIKE ?
        """, (company_id, f"{selected_task_date}%")).fetchall()
        time_conflicts = find_time_conflicts(
            day_tasks,
            valid_workers,
            time_from,
            time_to,
        )

        if time_conflicts:
            conflict = time_conflicts[0]
            error_params = {
                "error": "time_conflict",
                "task_date": selected_task_date,
                "worker": valid_workers[0],
                "workers_csv": ",".join(valid_workers),
                "time_from": time_from,
                "time_to": time_to,
                "conflict_task_id": conflict["task_id"],
            }
            conn.close()
            return RedirectResponse(
                f"/create-task?{urlencode(error_params)}",
                status_code=302,
            )

    c.execute("""
    INSERT INTO tasks (
        company_id,
        client_id,
        client,
        phone,
        address,
        description,
        task_date,
        time_from,
        time_to,
        worker,
        workers,
        priority,
        price,
        photo,
        status,
        report,
        after_photo,
        created_at,
        source_call_id
    )
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        company_id,
        client_id,
        client,
        phone,
        address,
        description,
        task_date,
        time_from,
        time_to,
        worker,
        workers_text,
        priority,
        price,
        "",
        "Новая",
        "",
        "",
        datetime.now().strftime("%Y-%m-%d %H:%M"),
        source_call["id"] if source_call else None
    ))

    task_id = c.lastrowid
    notification_created_at = datetime.now().strftime("%Y-%m-%d %H:%M")
    notification_message = (
        f"Клиент: {client}. "
        f"Дата: {task_date or 'не указана'}. "
        f"Время: {time_from or 'не указано'}"
        f"{'–' + time_to if time_to else ''}. "
        f"Приоритет: {priority or 'не указан'}"
    )

    for worker_name in valid_workers:
        c.execute("""
        INSERT INTO notifications (
            company_id,
            username,
            title,
            message,
            link,
            created_at
        )
        VALUES (?, ?, ?, ?, ?, ?)
        """, (
            company_id,
            worker_name,
            f"Назначена новая заявка #{task_id}",
            notification_message,
            f"/task/{task_id}",
            notification_created_at,
        ))

    conn.commit()

    try:
        filename = save_upload_file(photo, task_id, "before")
    except UploadValidationError as error:
        conn.close()
        return RedirectResponse(
            f"/task/{task_id}?file_error={error.code}",
            status_code=302,
        )
    except ObjectStorageError:
        conn.close()
        return RedirectResponse(
            f"/task/{task_id}?file_error=storage",
            status_code=302,
        )

    if filename:
        c.execute("""
        UPDATE tasks SET photo=? WHERE id=?
        """, (filename, task_id))
        conn.commit()

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
            "task",
            task_id,
            custom_value,
            datetime.now().strftime("%Y-%m-%d %H:%M")
        ))

    if custom_fields:
        conn.commit()

    if ai_note_id.isdigit():
        c.execute("""
        UPDATE ai_assistant_notes
        SET is_done=1,
            done_by=?,
            done_at=?,
            created_task_id=?
        WHERE id=?
          AND company_id=?
          AND COALESCE(is_done, 0)=0
        """, (
            username,
            datetime.now().strftime("%Y-%m-%d %H:%M"),
            task_id,
            int(ai_note_id),
            company_id
        ))
        conn.commit()

    conn.close()

    log_task_activity(
        task_id,
        username,
        role,
        "Создана заявка",
        (
            f"Клиент: {client}. "
            f"Исполнители: {format_task_workers({'worker': worker, 'workers': workers_text})}. "
            f"Дата: {task_date}. "
            f"Время: {time_from or 'не указано'}"
            f"{'–' + time_to if time_to else ''}"
        )
    )

    if source_call:
        log_task_activity(
            task_id,
            username,
            role,
            "Создано из звонка",
            f"Источник: звонок #{source_call['id']}. {source_call['summary'] or ''}".strip()
        )

    if over_capacity_workers:
        capacity_details = "; ".join(
            f"{item['username']}: "
            f"{item['active_count']} из {item['daily_capacity']}"
            for item in over_capacity_workers
        )
        log_task_activity(
            task_id,
            username,
            role,
            "Превышен дневной лимит",
            f"Подтверждено при создании. {capacity_details}",
        )

    run_automation_event(
        company_id,
        "new_task",
        "task",
        task_id,
        f"Создана новая заявка #{task_id}",
        f"/task/{task_id}",
    )

    text = f"""
🚀 Новая заявка #{task_id}

👤 Клиент: {client}
📞 Телефон: {phone}
📍 Адрес: {address}
	📅 Дата: {task_date}
	⏰ Время: {time_from or 'не указано'}{'–' + time_to if time_to else ''}
👷 Исполнители: {format_task_workers({'worker': worker, 'workers': workers_text})}
🔥 Приоритет: {priority}
💰 Цена: {price}
"""

    try:
        send_message(text)

        for worker_chat_id in worker_chat_ids:
            send_message_to_chat(
                worker_chat_id,
                f"""
📋 Вам назначена новая заявка #{task_id}

👤 Клиент: {client}
📞 Телефон: {phone}
📍 Адрес: {address}
	📅 Дата: {task_date}
	⏰ Время: {time_from or 'не указано'}{'–' + time_to if time_to else ''}
🔥 Приоритет: {priority}
"""
            )

        if filename:
            send_photo(
                f"uploads/{filename}",
                f"Фото до работы к заявке #{task_id}"
            )
    except Exception as e:
        print("Telegram notification error:", e)

    if return_to == "calendar":
        calendar_date = str(task_date or "")[:10]

        try:
            datetime.strptime(calendar_date, "%Y-%m-%d")
        except Exception:
            calendar_date = datetime.now().strftime("%Y-%m-%d")

        calendar_url = f"/calendar?date={calendar_date}"

        if worker:
            calendar_url += f"&worker={worker}"

        return RedirectResponse(calendar_url, status_code=302)

    if return_to == "client" and client_id:
        return RedirectResponse(f"/clients/{client_id}", status_code=302)

    return RedirectResponse("/", status_code=302)


@router.get("/task/{task_id}", response_class=HTMLResponse)
async def task_detail(request: Request, task_id: int):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    conn = connect()
    c = conn.cursor()

    task = c.execute("""
    SELECT * FROM tasks WHERE id=?
    """, (task_id,)).fetchone()

    if not task:
        conn.close()
        return RedirectResponse("/", status_code=302)

    if not can_access_task(username, role, task):
        conn.close()
        return RedirectResponse("/", status_code=302)

    company_id = get_task_company_id(task)
    linked_client = None

    if "client_id" in task.keys() and task["client_id"]:
        linked_client = c.execute("""
        SELECT *
        FROM clients
        WHERE id=? AND company_id=?
        """, (task["client_id"], company_id)).fetchone()

    source_call = None

    if "source_call_id" in task.keys() and task["source_call_id"]:
        source_call = c.execute("""
        SELECT
            call_records.*,
            clients.name AS client_name
        FROM call_records
        LEFT JOIN clients
          ON clients.id=call_records.client_id
         AND clients.company_id=call_records.company_id
        WHERE call_records.id=?
          AND call_records.company_id=?
        """, (task["source_call_id"], company_id)).fetchone()

    comments = c.execute("""
    SELECT *
    FROM task_comments
    WHERE task_id=?
    ORDER BY id ASC
    """, (task_id,)).fetchall()

    activity = c.execute("""
    SELECT *
    FROM task_activity
    WHERE task_id=?
    ORDER BY id DESC
    """, (task_id,)).fetchall()

    task_items = c.execute("""
    SELECT *
    FROM task_items
    WHERE task_id=?
    ORDER BY id DESC
    """, (task_id,)).fetchall()

    task_expenses = c.execute("""
    SELECT *
    FROM task_expenses
    WHERE task_id=?
    ORDER BY id DESC
    """, (task_id,)).fetchall()

    catalog_items = c.execute("""
    SELECT *
    FROM catalog_items
    WHERE active=1 AND company_id=?
    ORDER BY item_type, name
    """, (company_id,)).fetchall()

    estimate_total = sum(item["total"] for item in task_items)
    estimate_profit = sum(item["profit"] for item in task_items)
    expenses_total = sum(expense["amount"] for expense in task_expenses)
    discount_amount = float(task["discount_amount"] or 0) if "discount_amount" in task.keys() else 0

    if discount_amount < 0:
        discount_amount = 0

    estimate_final_total = max(estimate_total - discount_amount, 0)
    estimate_final_profit = estimate_profit - discount_amount - expenses_total
    estimate_margin = round((estimate_final_profit / estimate_final_total) * 100, 1) if estimate_final_total else 0

    sla_status = "none"

    if task["deadline_at"]:
        now_value = datetime.now().strftime("%Y-%m-%dT%H:%M")

        if task["status"] != "Завершено" and task["deadline_at"] < now_value:
            sla_status = "overdue"
        elif task["status"] != "Завершено":
            sla_status = "active"
        else:
            sla_status = "done"
    task_workers = get_task_worker_names(task)
    available_workers = c.execute("""
    SELECT username, full_name
    FROM users
    WHERE company_id=?
      AND role='worker'
      AND COALESCE(is_active, 1)=1
    ORDER BY COALESCE(NULLIF(full_name, ''), username), username
    """, (company_id,)).fetchall()
    smart_reschedule_items = []
    smart_reschedule_summary = {
        "search_days": 14,
        "required_workers": len(task_workers),
        "days_with_capacity": 0,
        "total_open_slots": 0,
        "found": 0,
    }

    if (
        role in ("boss", "manager")
        and task_workers
        and task["status"] not in ("Завершено", "Отменено")
    ):
        worker_placeholders = ",".join("?" for _ in task_workers)
        reschedule_workers = c.execute(f"""
        SELECT username, daily_capacity
        FROM users
        WHERE company_id=?
          AND role='worker'
          AND COALESCE(is_active, 1)=1
          AND username IN ({worker_placeholders})
        ORDER BY username
        """, [company_id, *task_workers]).fetchall()
        reschedule_capacities = {
            row["username"]: max(
                1,
                int(row["daily_capacity"] or 3),
            )
            for row in reschedule_workers
        }

        if len(reschedule_capacities) == len(task_workers):
            reschedule_start = datetime.now().date()

            try:
                current_task_date = datetime.strptime(
                    str(task["task_date"] or "")[:10],
                    "%Y-%m-%d",
                ).date()

                if current_task_date > reschedule_start:
                    reschedule_start = current_task_date
            except Exception:
                pass

            reschedule_end = reschedule_start + timedelta(days=13)
            reschedule_rows = c.execute("""
            SELECT worker, workers, substr(task_date, 1, 10) AS work_date
            FROM tasks
            WHERE archived=0
              AND company_id=?
              AND id!=?
              AND status NOT IN ('Завершено', 'Отменено')
              AND task_date IS NOT NULL
              AND task_date != ''
              AND substr(task_date, 1, 10) BETWEEN ? AND ?
            """, (
                company_id,
                task_id,
                reschedule_start.strftime("%Y-%m-%d"),
                reschedule_end.strftime("%Y-%m-%d"),
            )).fetchall()
            reschedule_unavailable_dates, _ = get_worker_unavailability(
                c,
                company_id,
                task_workers,
                reschedule_start.strftime("%Y-%m-%d"),
                reschedule_end.strftime("%Y-%m-%d"),
            )
            reschedule_result = build_scheduling_recommendations(
                worker_capacities=reschedule_capacities,
                assignments=[
                    {
                        "date": row["work_date"],
                        "workers": get_task_worker_names(row),
                    }
                    for row in reschedule_rows
                ],
                start_date=reschedule_start,
                search_days=14,
                fixed_workers=task_workers,
                unavailable_dates=reschedule_unavailable_dates,
                limit=5,
            )
            smart_reschedule_items = reschedule_result["items"]
            smart_reschedule_summary = reschedule_result["summary"]

    task_custom_fields = c.execute("""
    SELECT custom_fields.id, custom_fields.label, custom_fields.group_name, custom_fields.field_type, custom_field_values.value
    FROM custom_fields
    LEFT JOIN custom_field_values
      ON custom_field_values.field_id=custom_fields.id
      AND custom_field_values.company_id=custom_fields.company_id
      AND custom_field_values.entity_type='task'
      AND custom_field_values.entity_id=?
    WHERE custom_fields.company_id=?
      AND custom_fields.entity_type='task'
      AND custom_fields.active=1
    ORDER BY custom_fields.sort_order, custom_fields.id
    """, (task_id, company_id)).fetchall()

    settings = get_company_settings(company_id)

    conn.close()

    return templates.TemplateResponse(
        request,
        "task_detail.html",
        {
            "request": request,
            "task": task,
            "username": username,
            "role": role,
            "comments": comments,
            "activity": activity,
            "activities": activity,
            "linked_client": linked_client,
            "source_call": source_call,
            "task_items": task_items,
            "task_expenses": task_expenses,
            "catalog_items": catalog_items,
            "estimate_total": estimate_total,
            "estimate_profit": estimate_profit,
            "expenses_total": expenses_total,
            "discount_amount": discount_amount,
            "estimate_final_total": estimate_final_total,
            "estimate_final_profit": estimate_final_profit,
            "estimate_margin": estimate_margin,
            "task_workers": task_workers,
            "available_workers": available_workers,
            "smart_reschedule_items": smart_reschedule_items,
            "smart_reschedule_summary": smart_reschedule_summary,
            "task_custom_fields": task_custom_fields,
            "sla_status": sla_status,
            "settings": settings
        }
    )


@router.post("/task/{task_id}/items")
async def add_task_item(request: Request, task_id: int):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role not in ("boss", "manager"):
        return RedirectResponse("/", status_code=302)

    form = await request.form()

    catalog_item_id = form.get("catalog_item_id")
    qty = form.get("qty") or "1"

    try:
        qty = float(str(qty).replace(",", "."))
    except Exception:
        qty = 1

    if qty <= 0:
        qty = 1

    conn = connect()
    c = conn.cursor()

    task = c.execute("""
    SELECT *
    FROM tasks
    WHERE id=?
    """, (task_id,)).fetchone()

    if not task:
        conn.close()
        return RedirectResponse("/", status_code=302)

    if not can_access_task(username, role, task):
        conn.close()
        return RedirectResponse("/", status_code=302)

    company_id = get_task_company_id(task)

    item = c.execute("""
    SELECT *
    FROM catalog_items
    WHERE id=? AND company_id=? AND active=1
    """, (catalog_item_id, company_id)).fetchone()

    if not item:
        conn.close()
        return RedirectResponse(f"/task/{task_id}", status_code=302)

    total = float(item["price"]) * qty
    profit = (float(item["price"]) - float(item["cost"])) * qty

    c.execute("""
    INSERT INTO task_items (
        company_id,
        task_id,
        catalog_item_id,
        item_name,
        item_type,
        unit,
        qty,
        price,
        cost,
        total,
        profit,
        created_at
    )
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        company_id,
        task_id,
        item["id"],
        item["name"],
        item["item_type"],
        item["unit"],
        qty,
        item["price"],
        item["cost"],
        total,
        profit,
        datetime.now().strftime("%Y-%m-%d %H:%M")
    ))

    conn.commit()
    conn.close()

    try:
        log_task_activity(
            task_id,
            username,
            role,
            "Добавлена позиция в смету",
            f"{item['name']} × {qty}"
        )
    except Exception:
        pass

    run_automation_event(
        company_id,
        "task_finance_changed",
        "task",
        task_id,
        f"Добавлена позиция в смету заявки #{task_id}: {item['name']}",
        f"/task/{task_id}",
    )

    return RedirectResponse(f"/task/{task_id}", status_code=302)


@router.post("/task/{task_id}/items/manual")
async def add_manual_task_item(request: Request, task_id: int):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role not in ("boss", "manager"):
        return RedirectResponse("/", status_code=302)

    form = await request.form()
    item_name = (form.get("item_name") or "").strip()
    item_type = form.get("item_type") if form.get("item_type") in ("service", "material") else "service"
    unit = (form.get("unit") or "шт").strip()
    qty = form.get("qty") or "1"
    price = form.get("price") or "0"
    cost = form.get("cost") or "0"

    try:
        qty = float(str(qty).replace(",", "."))
    except Exception:
        qty = 1

    try:
        price = float(str(price).replace(",", "."))
    except Exception:
        price = 0

    try:
        cost = float(str(cost).replace(",", "."))
    except Exception:
        cost = 0

    if not item_name:
        return RedirectResponse(f"/task/{task_id}?error=manual_item_empty", status_code=302)

    if qty <= 0:
        qty = 1

    if price < 0:
        price = 0

    if cost < 0:
        cost = 0

    conn = connect()
    c = conn.cursor()

    task = c.execute("""
    SELECT *
    FROM tasks
    WHERE id=?
    """, (task_id,)).fetchone()

    if not task:
        conn.close()
        return RedirectResponse("/", status_code=302)

    if not can_access_task(username, role, task):
        conn.close()
        return RedirectResponse("/", status_code=302)

    company_id = get_task_company_id(task)
    total = price * qty
    profit = (price - cost) * qty

    c.execute("""
    INSERT INTO task_items (
        company_id,
        task_id,
        catalog_item_id,
        item_name,
        item_type,
        unit,
        qty,
        price,
        cost,
        total,
        profit,
        created_at
    )
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        company_id,
        task_id,
        None,
        item_name,
        item_type,
        unit,
        qty,
        price,
        cost,
        total,
        profit,
        datetime.now().strftime("%Y-%m-%d %H:%M")
    ))

    conn.commit()
    conn.close()

    log_task_activity(
        task_id,
        username,
        role,
        "Добавлена ручная позиция в смету",
        f"{item_name} × {qty}"
    )

    run_automation_event(
        company_id,
        "task_finance_changed",
        "task",
        task_id,
        f"Добавлена ручная позиция в смету заявки #{task_id}: {item_name}",
        f"/task/{task_id}",
    )

    return RedirectResponse(f"/task/{task_id}", status_code=302)


@router.post("/task/{task_id}/items/{item_id}/delete")
async def delete_task_item(request: Request, task_id: int, item_id: int):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role not in ("boss", "manager"):
        return RedirectResponse("/", status_code=302)

    conn = connect()
    c = conn.cursor()

    task = c.execute("""
    SELECT *
    FROM tasks
    WHERE id=?
    """, (task_id,)).fetchone()

    if not task:
        conn.close()
        return RedirectResponse("/", status_code=302)

    if not can_access_task(username, role, task):
        conn.close()
        return RedirectResponse("/", status_code=302)

    company_id = get_task_company_id(task)

    item = c.execute("""
    SELECT *
    FROM task_items
    WHERE id=? AND task_id=? AND company_id=?
    """, (item_id, task_id, company_id)).fetchone()

    if not item:
        conn.close()
        return RedirectResponse(f"/task/{task_id}", status_code=302)

    c.execute("""
    DELETE FROM task_items
    WHERE id=? AND task_id=? AND company_id=?
    """, (item_id, task_id, company_id))

    conn.commit()
    conn.close()

    try:
        log_task_activity(
            task_id,
            username,
            role,
            "Удалена позиция из сметы",
            f"{item['item_name']} × {item['qty']}"
        )
    except Exception:
        pass

    run_automation_event(
        company_id,
        "task_finance_changed",
        "task",
        task_id,
        f"Удалена позиция из сметы заявки #{task_id}: {item['item_name']}",
        f"/task/{task_id}",
    )

    return RedirectResponse(f"/task/{task_id}", status_code=302)


@router.post("/task/{task_id}/estimate/apply")
async def apply_task_estimate_total(request: Request, task_id: int):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role not in ("boss", "manager"):
        return RedirectResponse("/", status_code=302)

    conn = connect()
    c = conn.cursor()

    task = c.execute("""
    SELECT *
    FROM tasks
    WHERE id=?
    """, (task_id,)).fetchone()

    if not task:
        conn.close()
        return RedirectResponse("/", status_code=302)

    if not can_access_task(username, role, task):
        conn.close()
        return RedirectResponse("/", status_code=302)

    company_id = get_task_company_id(task)
    estimate_total = c.execute("""
    SELECT SUM(total)
    FROM task_items
    WHERE task_id=? AND company_id=?
    """, (task_id, company_id)).fetchone()[0] or 0
    discount_amount = float(task["discount_amount"] or 0) if "discount_amount" in task.keys() else 0

    if discount_amount < 0:
        discount_amount = 0

    final_total = max(estimate_total - discount_amount, 0)

    c.execute("""
    UPDATE tasks
    SET price=?
    WHERE id=? AND company_id=?
    """, (str(final_total), task_id, company_id))

    conn.commit()
    conn.close()

    log_task_activity(
        task_id,
        username,
        role,
        "Цена обновлена по смете",
        f"Новая цена: {final_total}"
    )

    run_automation_event(
        company_id,
        "task_finance_changed",
        "task",
        task_id,
        f"Цена заявки #{task_id} обновлена по смете: {final_total}",
        f"/task/{task_id}",
    )

    return RedirectResponse(f"/task/{task_id}", status_code=302)


@router.post("/task/{task_id}/expenses")
async def add_task_expense(request: Request, task_id: int):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role not in ("boss", "manager"):
        return RedirectResponse("/", status_code=302)

    form = await request.form()
    title = (form.get("title") or "").strip()
    amount = form.get("amount") or "0"

    try:
        amount = float(str(amount).replace(",", "."))
    except Exception:
        amount = 0

    if not title:
        return RedirectResponse(f"/task/{task_id}?error=expense_empty", status_code=302)

    if amount < 0:
        amount = 0

    conn = connect()
    c = conn.cursor()

    task = c.execute("""
    SELECT *
    FROM tasks
    WHERE id=?
    """, (task_id,)).fetchone()

    if not task:
        conn.close()
        return RedirectResponse("/", status_code=302)

    if not can_access_task(username, role, task):
        conn.close()
        return RedirectResponse("/", status_code=302)

    company_id = get_task_company_id(task)

    c.execute("""
    INSERT INTO task_expenses (
        company_id,
        task_id,
        title,
        amount,
        created_at
    )
    VALUES (?, ?, ?, ?, ?)
    """, (
        company_id,
        task_id,
        title,
        amount,
        datetime.now().strftime("%Y-%m-%d %H:%M")
    ))

    conn.commit()
    conn.close()

    log_task_activity(
        task_id,
        username,
        role,
        "Добавлен расход",
        f"{title}: {amount}"
    )

    run_automation_event(
        company_id,
        "task_finance_changed",
        "task",
        task_id,
        f"Добавлен расход заявки #{task_id}: {title} — {amount}",
        f"/task/{task_id}",
    )

    return RedirectResponse(f"/task/{task_id}", status_code=302)


@router.post("/task/{task_id}/expenses/{expense_id}/delete")
async def delete_task_expense(request: Request, task_id: int, expense_id: int):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role not in ("boss", "manager"):
        return RedirectResponse("/", status_code=302)

    conn = connect()
    c = conn.cursor()

    task = c.execute("""
    SELECT *
    FROM tasks
    WHERE id=?
    """, (task_id,)).fetchone()

    if not task:
        conn.close()
        return RedirectResponse("/", status_code=302)

    if not can_access_task(username, role, task):
        conn.close()
        return RedirectResponse("/", status_code=302)

    company_id = get_task_company_id(task)
    expense = c.execute("""
    SELECT *
    FROM task_expenses
    WHERE id=? AND task_id=? AND company_id=?
    """, (expense_id, task_id, company_id)).fetchone()

    if not expense:
        conn.close()
        return RedirectResponse(f"/task/{task_id}", status_code=302)

    c.execute("""
    DELETE FROM task_expenses
    WHERE id=? AND task_id=? AND company_id=?
    """, (expense_id, task_id, company_id))

    conn.commit()
    conn.close()

    log_task_activity(
        task_id,
        username,
        role,
        "Удалён расход",
        f"{expense['title']}: {expense['amount']}"
    )

    run_automation_event(
        company_id,
        "task_finance_changed",
        "task",
        task_id,
        (
            f"Удалён расход заявки #{task_id}: "
            f"{expense['title']} — {expense['amount']}"
        ),
        f"/task/{task_id}",
    )

    return RedirectResponse(f"/task/{task_id}", status_code=302)


@router.post("/task/{task_id}/discount")
async def update_task_discount(request: Request, task_id: int):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role not in ("boss", "manager"):
        return RedirectResponse("/", status_code=302)

    form = await request.form()
    discount_amount = form.get("discount_amount") or "0"

    try:
        discount_amount = float(str(discount_amount).replace(",", "."))
    except Exception:
        discount_amount = 0

    if discount_amount < 0:
        discount_amount = 0

    conn = connect()
    c = conn.cursor()

    task = c.execute("""
    SELECT *
    FROM tasks
    WHERE id=?
    """, (task_id,)).fetchone()

    if not task:
        conn.close()
        return RedirectResponse("/", status_code=302)

    if not can_access_task(username, role, task):
        conn.close()
        return RedirectResponse("/", status_code=302)

    company_id = get_task_company_id(task)
    old_discount = task["discount_amount"] if "discount_amount" in task.keys() else 0

    c.execute("""
    UPDATE tasks
    SET discount_amount=?
    WHERE id=? AND company_id=?
    """, (discount_amount, task_id, company_id))

    conn.commit()
    conn.close()

    log_task_activity(
        task_id,
        username,
        role,
        "Изменена скидка",
        f"{old_discount} → {discount_amount}"
    )

    run_automation_event(
        company_id,
        "task_finance_changed",
        "task",
        task_id,
        f"Скидка заявки #{task_id}: {old_discount} → {discount_amount}",
        f"/task/{task_id}",
    )

    return RedirectResponse(f"/task/{task_id}", status_code=302)


@router.post("/task/{task_id}/comment")
async def add_task_comment(request: Request, task_id: int):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    form = await request.form()
    message = (form.get("message") or "").strip()

    conn = connect()
    c = conn.cursor()

    task = c.execute("""
    SELECT * FROM tasks WHERE id=?
    """, (task_id,)).fetchone()

    if not task:
        conn.close()
        return RedirectResponse("/", status_code=302)

    if not can_access_task(username, role, task):
        conn.close()
        return RedirectResponse("/", status_code=302)

    if message:
        c.execute("""
        INSERT INTO task_comments (
            task_id,
            username,
            role,
            message,
            created_at
        )
        VALUES (?, ?, ?, ?, ?)
        """, (
            task_id,
            username,
            role,
            message,
            datetime.now().strftime("%Y-%m-%d %H:%M")
        ))

        conn.commit()

        log_task_activity(
            task_id,
            username,
            role,
            "Добавлен комментарий",
            message
        )

        try:
            comment_text = f"""
💬 Новый комментарий в заявке #{task_id}

Клиент: {task['client']}
Адрес: {task['address']}
Автор: {username} ({get_role_title(role)})

Комментарий:
{message}
"""

            send_message(comment_text)

            for worker_chat_id in get_task_worker_chat_ids(c, task):
                send_message_to_chat(worker_chat_id, comment_text)

        except Exception as e:
            print("Telegram comment notification error:", e)

    conn.close()

    if message:
        run_automation_event(
            get_task_company_id(task),
            "task_comment_added",
            "task",
            task_id,
            f"Добавлен комментарий к заявке #{task_id}",
            f"/task/{task_id}",
        )

    return RedirectResponse(f"/task/{task_id}", status_code=302)


@router.post("/task/{task_id}/payment")
async def update_payment_status(request: Request, task_id: int):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role not in ("boss", "manager"):
        return RedirectResponse("/", status_code=302)

    form = await request.form()
    new_status = form.get("payment_status") or "Не оплачено"

    allowed = [
        "Не оплачено",
        "Частично оплачено",
        "Оплачено"
    ]

    if new_status not in allowed:
        new_status = "Не оплачено"

    conn = connect()
    c = conn.cursor()

    task = c.execute("""
    SELECT *
    FROM tasks
    WHERE id=?
    """, (task_id,)).fetchone()

    if not task:
        conn.close()
        return RedirectResponse("/", status_code=302)

    if not can_access_task(username, role, task):
        conn.close()
        return RedirectResponse("/", status_code=302)

    company_id = get_task_company_id(task)
    old_status = task["payment_status"] if "payment_status" in task.keys() else "Не оплачено"

    c.execute("""
    UPDATE tasks
    SET payment_status=?
    WHERE id=?
    """, (new_status, task_id))

    conn.commit()
    conn.close()

    try:
        log_task_activity(
            task_id,
            username,
            role,
            "Изменён статус оплаты",
            f"{old_status} → {new_status}"
        )
    except Exception:
        pass

    if old_status != new_status:
        run_automation_event(
            company_id,
            "payment_status_changed",
            "task",
            task_id,
            f"Статус оплаты заявки #{task_id}: {old_status} → {new_status}",
            f"/task/{task_id}",
        )

    try:
        send_message(
            f"""
💳 Изменён статус оплаты

Заявка: #{task_id}
Клиент: {task['client']}

Было: {old_status}
Стало: {new_status}

Изменил: {username} ({get_role_title(role)})
"""
        )
    except Exception:
        pass

    return RedirectResponse(f"/task/{task_id}", status_code=302)




@router.post("/task/{task_id}/complete")
async def complete_task(request: Request, task_id: int):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role != "worker":
        return RedirectResponse("/", status_code=302)

    form = await request.form()
    report = (form.get("report") or "").strip()
    after_photo = form.get("after_photo")

    if not report:
        return RedirectResponse("/my-tasks?error=report_required", status_code=302)

    company_id = get_user_company_id(username)

    conn = connect()
    c = conn.cursor()

    task = c.execute("""
    SELECT *
    FROM tasks
    WHERE id=? AND company_id=?
    """, (task_id, company_id)).fetchone()

    if not task or not task_has_worker(username, task):
        conn.close()
        return RedirectResponse("/my-tasks", status_code=302)

    try:
        filename = save_upload_file(after_photo, task_id, "after")
    except UploadValidationError as error:
        conn.close()
        return RedirectResponse(
            f"/my-tasks?error=file_{error.code}",
            status_code=302,
        )
    except ObjectStorageError:
        conn.close()
        return RedirectResponse(
            "/my-tasks?error=storage",
            status_code=302,
        )

    c.execute("""
    UPDATE tasks
    SET status='Завершено',
        report=?,
        after_photo=?
    WHERE id=?
    """, (
        report,
        filename or task["after_photo"],
        task_id
    ))

    c.execute("""
    INSERT INTO task_activity (
        task_id,
        username,
        role,
        action,
        details,
        created_at
    )
    VALUES (?, ?, ?, ?, ?, ?)
    """, (
        task_id,
        username,
        role,
        "Завершил заявку",
        report,
        datetime.now().strftime("%Y-%m-%d %H:%M")
    ))

    owners = c.execute("""
    SELECT username
    FROM users
    WHERE company_id=? AND role IN ('boss', 'manager')
    """, (company_id,)).fetchall()

    for owner in owners:
        c.execute("""
        INSERT INTO notifications (
            company_id,
            username,
            title,
            message,
            link,
            created_at
        )
        VALUES (?, ?, ?, ?, ?, ?)
        """, (
            company_id,
            owner["username"],
            "✅ Заявка завершена",
            f"Исполнитель {username} завершил заявку #{task_id}",
            f"/task/{task_id}",
            datetime.now().strftime("%Y-%m-%d %H:%M")
        ))

    conn.commit()
    conn.close()

    if task["status"] != "Завершено":
        run_automation_event(
            company_id,
            "task_status_changed",
            "task",
            task_id,
            f"Статус заявки #{task_id}: {task['status']} → Завершено",
            f"/task/{task_id}",
        )

    try:
        send_message(
            f"""
✅ Заявка завершена исполнителем

Заявка: #{task_id}
Клиент: {task["client"]}
Адрес: {task["address"]}
Исполнитель: {username}

Отчёт:
{report}
"""
        )
    except Exception:
        pass

    return RedirectResponse("/my-tasks", status_code=302)


@router.post("/task/{task_id}/start")
async def start_task(request: Request, task_id: int):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role != "worker":
        return RedirectResponse("/", status_code=302)

    company_id = get_user_company_id(username)

    conn = connect()
    c = conn.cursor()

    task = c.execute("""
    SELECT *
    FROM tasks
    WHERE id=? AND company_id=?
    """, (task_id, company_id)).fetchone()

    if not task or not task_has_worker(username, task):
        conn.close()
        return RedirectResponse("/my-tasks", status_code=302)

    c.execute("""
    UPDATE tasks
    SET status='В работе'
    WHERE id=?
    """, (task_id,))

    c.execute("""
    INSERT INTO task_activity (
        task_id,
        username,
        role,
        action,
        details,
        created_at
    )
    VALUES (?, ?, ?, ?, ?, ?)
    """, (
        task_id,
        username,
        role,
        "Взял в работу",
        "Исполнитель начал выполнение заявки",
        datetime.now().strftime("%Y-%m-%d %H:%M")
    ))

    conn.commit()
    conn.close()

    if task["status"] != "В работе":
        run_automation_event(
            company_id,
            "task_status_changed",
            "task",
            task_id,
            f"Статус заявки #{task_id}: {task['status']} → В работе",
            f"/task/{task_id}",
        )

    return RedirectResponse("/my-tasks", status_code=302)



@router.post("/task/{task_id}/edit")
async def edit_task_field(request: Request, task_id: int):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role not in ("boss", "manager"):
        return RedirectResponse("/", status_code=302)

    form = await request.form()
    field = (form.get("field") or "").strip()
    value = (form.get("value") or "").strip()

    allowed_fields = {
        "client": "client",
        "phone": "phone",
        "address": "address",
        "description": "description",
        "priority": "priority",
        "price": "price",
        "status": "status"
    }

    if field not in allowed_fields:
        return RedirectResponse(f"/task/{task_id}", status_code=302)

    conn = connect()
    c = conn.cursor()

    task = c.execute("""
    SELECT *
    FROM tasks
    WHERE id=?
    """, (task_id,)).fetchone()

    if not task:
        conn.close()
        return RedirectResponse("/", status_code=302)

    if not can_access_task(username, role, task):
        conn.close()
        return RedirectResponse("/", status_code=302)

    column = allowed_fields[field]
    company_id = get_task_company_id(task)
    previous_value = "" if task[column] is None else str(task[column])

    c.execute(f"""
    UPDATE tasks
    SET {column}=?
    WHERE id=?
    """, (value, task_id))

    c.execute("""
    INSERT INTO task_activity (
        task_id,
        username,
        role,
        action,
        details,
        created_at
    )
    VALUES (?, ?, ?, ?, ?, ?)
    """, (
        task_id,
        username,
        role,
        "Изменено поле",
        f"{field}: {value}",
        datetime.now().strftime("%Y-%m-%d %H:%M")
    ))

    conn.commit()
    conn.close()

    if previous_value != value:
        field_labels = {
            "client": "Клиент",
            "phone": "Телефон",
            "address": "Адрес",
            "description": "Описание",
            "priority": "Приоритет",
            "price": "Цена",
            "status": "Статус",
        }
        field_label = field_labels.get(field, field)

        if field == "status":
            run_automation_event(
                company_id,
                "task_status_changed",
                "task",
                task_id,
                f"Статус заявки #{task_id}: {previous_value} → {value}",
                f"/task/{task_id}",
            )
        elif field == "price":
            run_automation_event(
                company_id,
                "task_finance_changed",
                "task",
                task_id,
                f"Цена заявки #{task_id}: {previous_value or '0'} → {value or '0'}",
                f"/task/{task_id}",
            )
        else:
            run_automation_event(
                company_id,
                "task_details_changed",
                "task",
                task_id,
                (
                    f"{field_label} заявки #{task_id}: "
                    f"{previous_value or 'пусто'} → {value or 'пусто'}"
                ),
                f"/task/{task_id}",
            )

    return RedirectResponse(f"/task/{task_id}", status_code=302)


@router.post("/task/{task_id}/workers")
async def update_task_workers(request: Request, task_id: int):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role not in ("boss", "manager"):
        return RedirectResponse("/", status_code=302)

    company_id = get_user_company_id(username)
    form = await request.form()
    selected_workers = form.getlist("workers")

    conn = connect()
    c = conn.cursor()

    task = c.execute("""
    SELECT *
    FROM tasks
    WHERE id=? AND company_id=?
    """, (task_id, company_id)).fetchone()

    if not task or not can_access_task(username, role, task):
        conn.close()
        return RedirectResponse("/", status_code=302)

    previous_workers = get_task_worker_names(task)
    valid_workers = []
    worker_chat_ids = {}

    for worker_name in selected_workers:
        worker_name = str(worker_name or "").strip()

        if not worker_name or worker_name in valid_workers:
            continue

        worker = c.execute("""
        SELECT username, telegram_chat_id
        FROM users
        WHERE company_id=?
          AND username=?
          AND role='worker'
          AND COALESCE(is_active, 1)=1
        """, (company_id, worker_name)).fetchone()

        if worker:
            valid_workers.append(worker["username"])
            worker_chat_ids[worker["username"]] = str(
                worker["telegram_chat_id"] or ""
            ).strip()

    worker_value = valid_workers[0] if valid_workers else ""
    workers_value = ",".join(valid_workers)
    added_workers = [
        worker_name
        for worker_name in valid_workers
        if worker_name not in previous_workers
    ]
    removed_workers = [
        worker_name
        for worker_name in previous_workers
        if worker_name not in valid_workers
    ]

    if valid_workers == previous_workers:
        conn.close()
        return RedirectResponse(f"/task/{task_id}", status_code=302)

    removed_worker_chat_ids = {}

    for worker_name in removed_workers:
        worker = c.execute("""
        SELECT username, telegram_chat_id
        FROM users
        WHERE company_id=?
          AND username=?
          AND role='worker'
          AND COALESCE(is_active, 1)=1
        """, (company_id, worker_name)).fetchone()

        if worker:
            removed_worker_chat_ids[worker_name] = str(
                worker["telegram_chat_id"] or ""
            ).strip()

    c.execute("""
    UPDATE tasks
    SET worker=?, workers=?
    WHERE id=? AND company_id=?
    """, (worker_value, workers_value, task_id, company_id))

    c.execute("""
    INSERT INTO task_activity (
        task_id,
        username,
        role,
        action,
        details,
        created_at
    )
    VALUES (?, ?, ?, ?, ?, ?)
    """, (
        task_id,
        username,
        role,
        "Изменены исполнители",
        ", ".join(valid_workers) if valid_workers else "Исполнители сняты",
        datetime.now().strftime("%Y-%m-%d %H:%M"),
    ))

    notification_title = f"Назначена заявка #{task_id}"
    notification_message = (
        f"Клиент: {task['client']}. "
        f"Дата: {task['task_date'] or 'не указана'}"
    )
    notification_created_at = datetime.now().strftime("%Y-%m-%d %H:%M")

    for worker_name in added_workers:
        c.execute("""
        INSERT INTO notifications (
            company_id,
            username,
            title,
            message,
            link,
            created_at
        )
        VALUES (?, ?, ?, ?, ?, ?)
        """, (
            company_id,
            worker_name,
            notification_title,
            notification_message,
            f"/task/{task_id}",
            notification_created_at,
        ))

    for worker_name in removed_worker_chat_ids:
        c.execute("""
        INSERT INTO notifications (
            company_id,
            username,
            title,
            message,
            link,
            created_at
        )
        VALUES (?, ?, ?, ?, ?, ?)
        """, (
            company_id,
            worker_name,
            f"Снято назначение с заявки #{task_id}",
            notification_message,
            "/my-tasks",
            notification_created_at,
        ))

    conn.commit()
    conn.close()

    previous_workers_text = ", ".join(previous_workers) or "не назначены"
    current_workers_text = ", ".join(valid_workers) or "не назначены"

    run_automation_event(
        company_id,
        "task_workers_changed",
        "task",
        task_id,
        (
            f"Исполнители заявки #{task_id}: "
            f"{previous_workers_text} → {current_workers_text}"
        ),
        f"/task/{task_id}",
    )

    telegram_text = (
        f"Вам назначена заявка #{task_id}\n"
        f"Клиент: {task['client']}\n"
        f"Дата: {task['task_date'] or 'не указана'}\n"
        f"Описание: {task['description'] or 'не указано'}"
    )

    for worker_name in added_workers:
        chat_id = worker_chat_ids.get(worker_name)

        if not chat_id:
            continue

        try:
            send_message_to_chat(chat_id, telegram_text)
        except Exception as error:
            print("Telegram reassignment notification error:", error)

    removal_telegram_text = (
        f"С вас снята заявка #{task_id}\n"
        f"Клиент: {task['client']}\n"
        f"Дата: {task['task_date'] or 'не указана'}"
    )

    for worker_name, chat_id in removed_worker_chat_ids.items():
        if not chat_id:
            continue

        try:
            send_message_to_chat(chat_id, removal_telegram_text)
        except Exception as error:
            print("Telegram unassignment notification error:", error)

    return RedirectResponse(f"/task/{task_id}", status_code=302)


@router.post("/task/{task_id}/custom-field")
async def update_task_custom_field(request: Request, task_id: int):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role not in ("boss", "manager"):
        return RedirectResponse("/", status_code=302)

    form = await request.form()
    field_id_raw = (form.get("field_id") or "").strip()
    value = (form.get("value") or "").strip()

    try:
        field_id = int(field_id_raw)
    except ValueError:
        return RedirectResponse(f"/task/{task_id}", status_code=302)

    conn = connect()
    c = conn.cursor()

    task = c.execute("""
    SELECT *
    FROM tasks
    WHERE id=?
    """, (task_id,)).fetchone()

    if not task:
        conn.close()
        return RedirectResponse("/", status_code=302)

    if not can_access_task(username, role, task):
        conn.close()
        return RedirectResponse("/", status_code=302)

    company_id = get_task_company_id(task)

    disabled_response = require_feature(company_id, "custom_fields")

    if disabled_response:
        conn.close()
        return disabled_response

    custom_field = c.execute("""
    SELECT *
    FROM custom_fields
    WHERE id=?
      AND company_id=?
      AND entity_type='task'
      AND active=1
    """, (field_id, company_id)).fetchone()

    if not custom_field:
        conn.close()
        return RedirectResponse(f"/task/{task_id}", status_code=302)

    if custom_field["is_required"] and not value:
        conn.close()
        return RedirectResponse(f"/task/{task_id}?error=custom_required", status_code=302)

    existing_value = c.execute("""
    SELECT *
    FROM custom_field_values
    WHERE company_id=?
      AND field_id=?
      AND entity_type='task'
      AND entity_id=?
    """, (company_id, field_id, task_id)).fetchone()

    if value:
        if existing_value:
            c.execute("""
            UPDATE custom_field_values
            SET value=?
            WHERE id=?
            """, (value, existing_value["id"]))
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
                field_id,
                "task",
                task_id,
                value,
                datetime.now().strftime("%Y-%m-%d %H:%M")
            ))
    elif existing_value and not custom_field["is_required"]:
        c.execute("""
        DELETE FROM custom_field_values
        WHERE id=?
        """, (existing_value["id"],))

    c.execute("""
    INSERT INTO task_activity (
        task_id,
        username,
        role,
        action,
        details,
        created_at
    )
    VALUES (?, ?, ?, ?, ?, ?)
    """, (
        task_id,
        username,
        role,
        "Изменено доп. поле",
        f"{custom_field['label']}: {value}",
        datetime.now().strftime("%Y-%m-%d %H:%M")
    ))

    conn.commit()
    conn.close()

    run_automation_event(
        company_id,
        "task_custom_field_updated",
        "task",
        task_id,
        (
            f"Поле заявки изменено: {custom_field['label']} — "
            f"{value or 'очищено'}"
        ),
        f"/task/{task_id}",
    )

    return RedirectResponse(f"/task/{task_id}", status_code=302)


@router.post("/task/{task_id}/deadline")
async def update_task_deadline(request: Request, task_id: int):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role not in ("boss", "manager"):
        return RedirectResponse("/", status_code=302)

    company_id = get_user_company_id(username)

    form = await request.form()
    deadline_at = (form.get("deadline_at") or "").strip()

    conn = connect()
    c = conn.cursor()

    task = c.execute("""
    SELECT *
    FROM tasks
    WHERE id=? AND company_id=?
    """, (task_id, company_id)).fetchone()

    if not task:
        conn.close()
        return RedirectResponse("/", status_code=302)

    previous_deadline = (task["deadline_at"] or "").strip()

    c.execute("""
    UPDATE tasks
    SET deadline_at=?
    WHERE id=? AND company_id=?
    """, (deadline_at, task_id, company_id))

    c.execute("""
    INSERT INTO task_activity (
        task_id,
        username,
        role,
        action,
        details,
        created_at
    )
    VALUES (?, ?, ?, ?, ?, ?)
    """, (
        task_id,
        username,
        role,
        "Изменён срок",
        deadline_at or "Срок очищен",
        datetime.now().strftime("%Y-%m-%d %H:%M")
    ))

    owners = c.execute("""
    SELECT username
    FROM users
    WHERE company_id=?
      AND role IN ('boss', 'manager')
    """, (company_id,)).fetchall()

    for owner in owners:
        if owner["username"] != username:
            c.execute("""
            INSERT INTO notifications (
                company_id,
                username,
                title,
                message,
                link,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """, (
                company_id,
                owner["username"],
                "⏰ Изменён срок",
                f"{username} изменил срок заявки #{task_id}",
                f"/task/{task_id}",
                datetime.now().strftime("%Y-%m-%d %H:%M")
            ))

    conn.commit()
    conn.close()

    if previous_deadline != deadline_at:
        run_automation_event(
            company_id,
            "sla_deadline_changed",
            "task",
            task_id,
            (
                f"SLA заявки #{task_id}: "
                f"{previous_deadline or 'не задан'} → {deadline_at or 'очищен'}"
            ),
            f"/task/{task_id}",
        )

    return RedirectResponse(f"/task/{task_id}", status_code=302)


@router.post("/task/{task_id}/date")
async def update_task_date(request: Request, task_id: int):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role not in ("boss", "manager"):
        return RedirectResponse("/", status_code=302)

    form = await request.form()
    new_date = (form.get("task_date") or "").strip()
    return_to = (form.get("return_to") or "").strip()
    has_time_fields = (
        form.get("time_from") is not None
        or form.get("time_to") is not None
    )

    conn = connect()
    c = conn.cursor()

    task = c.execute("""
    SELECT *
    FROM tasks
    WHERE id=?
    """, (task_id,)).fetchone()

    if not task:
        conn.close()
        return RedirectResponse("/", status_code=302)

    if not can_access_task(username, role, task):
        conn.close()
        return RedirectResponse("/", status_code=302)

    selected_date = str(new_date or "")[:10]

    try:
        if selected_date:
            datetime.strptime(selected_date, "%Y-%m-%d")
    except Exception:
        conn.close()
        return RedirectResponse(
            f"/task/{task_id}?date_error=invalid",
            status_code=302,
        )

    task_workers = get_task_worker_names(task)
    new_time_from = str(task["time_from"] or "")[:5]
    new_time_to = str(task["time_to"] or "")[:5]

    if has_time_fields:
        new_time_from, new_time_to, time_error = normalize_time_window(
            form.get("time_from"),
            form.get("time_to"),
        )

        if time_error:
            conn.close()
            return RedirectResponse(
                f"/task/{task_id}?date_error=invalid_time",
                status_code=302,
            )

    if selected_date and task_workers:
        unavailable_dates, _ = get_worker_unavailability(
            c,
            task["company_id"],
            task_workers,
            selected_date,
            selected_date,
        )
        unavailable_worker = next(
            (
                worker_name
                for worker_name in task_workers
                if selected_date
                in unavailable_dates.get(worker_name, set())
            ),
            "",
        )

        if unavailable_worker:
            conn.close()
            return RedirectResponse(
                (
                    f"/task/{task_id}?date_error=worker_unavailable"
                    f"&worker={unavailable_worker}"
                ),
                status_code=302,
            )

    if (
        selected_date
        and task_workers
        and new_time_from
        and new_time_to
    ):
        day_tasks = c.execute("""
        SELECT *
        FROM tasks
        WHERE company_id=?
          AND id!=?
          AND archived=0
          AND status NOT IN ('Завершено', 'Отменено')
          AND task_date LIKE ?
        """, (
            task["company_id"],
            task_id,
            f"{selected_date}%",
        )).fetchall()
        time_conflicts = find_time_conflicts(
            day_tasks,
            task_workers,
            new_time_from,
            new_time_to,
        )

        if time_conflicts:
            conflict = time_conflicts[0]
            conn.close()
            return RedirectResponse(
                (
                    f"/task/{task_id}?date_error=time_conflict"
                    f"&conflict_task_id={conflict['task_id']}"
                ),
                status_code=302,
            )

    old_date = task["task_date"]
    old_time_from = str(task["time_from"] or "")[:5]
    old_time_to = str(task["time_to"] or "")[:5]
    old_time = (
        f"{old_time_from}–{old_time_to}"
        if old_time_from and old_time_to
        else "Без времени"
    )
    schedule_changed = (
        str(old_date or "")[:10] != selected_date
        or old_time_from != new_time_from
        or old_time_to != new_time_to
    )
    worker_chat_ids = get_task_worker_chat_ids(c, task)

    c.execute("""
    UPDATE tasks
    SET task_date=?, time_from=?, time_to=?
    WHERE id=?
    """, (
        selected_date,
        new_time_from,
        new_time_to,
        task_id,
    ))

    conn.commit()
    conn.close()

    log_task_activity(
        task_id,
        username,
        role,
        "Расписание заявки изменено",
        (
            f"Было: {old_date or 'Без даты'}, {old_time}. "
            f"Стало: {selected_date or 'Без даты'}, "
            f"{new_time_from + '–' + new_time_to if new_time_from else 'Без времени'}"
        ),
    )

    if schedule_changed:
        run_automation_event(
            get_task_company_id(task),
            "task_schedule_changed",
            "task",
            task_id,
            (
                f"Расписание заявки #{task_id}: "
                f"{old_date or 'Без даты'} → {selected_date or 'Без даты'}"
            ),
            f"/task/{task_id}",
        )

    try:
        date_text = f"""
	📅 Расписание заявки изменено

Заявка: #{task_id}
Клиент: {task['client']}
Адрес: {task['address']}
Старая дата: {old_date or 'Без даты'}
	Новая дата: {selected_date}
	Новое время: {new_time_from + '–' + new_time_to if new_time_from else 'Без времени'}

Изменил: {username} ({get_role_title(role)})
"""

        send_message(date_text)

        for worker_chat_id in worker_chat_ids:
            send_message_to_chat(worker_chat_id, date_text)
    except Exception:
        pass

    if return_to.startswith("/calendar"):
        return RedirectResponse(return_to, status_code=302)

    return RedirectResponse(f"/task/{task_id}", status_code=302)


@router.post("/task/{task_id}/status")
async def update_task_status(request: Request, task_id: int):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    form = await request.form()
    new_status = (form.get("status") or "").strip()
    return_to = (form.get("return_to") or "").strip()

    allowed_statuses = ("Новая", "В работе", "Завершено", "Отменено")

    if new_status not in allowed_statuses:
        if return_to.startswith("/calendar"):
            return RedirectResponse(return_to, status_code=302)

        return RedirectResponse(f"/task/{task_id}", status_code=302)

    conn = connect()
    c = conn.cursor()

    task = c.execute("""
    SELECT * FROM tasks WHERE id=?
    """, (task_id,)).fetchone()

    if not task:
        conn.close()
        return RedirectResponse("/", status_code=302)

    if not can_access_task(username, role, task):
        conn.close()
        return RedirectResponse("/", status_code=302)

    company_id = get_task_company_id(task)
    old_status = task["status"]

    c.execute("""
    UPDATE tasks
    SET status=?
    WHERE id=?
    """, (new_status, task_id))

    conn.commit()
    conn.close()

    if old_status != new_status:
        log_task_activity(
            task_id,
            username,
            role,
            "Изменён статус",
            f"{old_status} → {new_status}"
        )

        run_automation_event(
            company_id,
            "task_status_changed",
            "task",
            task_id,
            f"Статус заявки #{task_id}: {old_status} → {new_status}",
            f"/task/{task_id}",
        )

        role_title = get_role_title(role)

        status_icons = {
            "Новая": "🆕",
            "В работе": "🚧",
            "Завершено": "✅",
            "Отменено": "❌"
        }

        icon = status_icons.get(new_status, "🔄")

        try:
            send_message(
                f"""
{icon} Статус заявки #{task_id} изменён

Клиент: {task['client']}
Адрес: {task['address']}
Исполнитель: {task['worker']}

Было: {old_status}
Стало: {new_status}

Изменил: {username} ({role_title})
"""
            )
        except Exception:
            pass

    if return_to.startswith("/calendar"):
        return RedirectResponse(return_to, status_code=302)

    return RedirectResponse(f"/task/{task_id}", status_code=302)


@router.post("/task/{task_id}/before-photo")
async def update_before_photo(
    request: Request,
    task_id: int,
    before_photo: UploadFile = File(None)
):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    conn = connect()
    c = conn.cursor()

    task = c.execute("""
    SELECT * FROM tasks WHERE id=?
    """, (task_id,)).fetchone()

    if not task:
        conn.close()
        return RedirectResponse("/", status_code=302)

    if not can_access_task(username, role, task):
        conn.close()
        return RedirectResponse("/", status_code=302)

    try:
        filename = save_upload_file(before_photo, task_id, "before")
    except UploadValidationError as error:
        conn.close()
        return RedirectResponse(
            f"/task/{task_id}?file_error={error.code}",
            status_code=302,
        )
    except ObjectStorageError:
        conn.close()
        return RedirectResponse(
            f"/task/{task_id}?file_error=storage",
            status_code=302,
        )

    if filename:
        c.execute("""
        UPDATE tasks SET photo=? WHERE id=?
        """, (filename, task_id))
        conn.commit()

    conn.close()

    if filename:
        log_task_activity(
            task_id,
            username,
            role,
            "Загружено фото до",
            filename
        )

        run_automation_event(
            get_task_company_id(task),
            "task_photo_uploaded",
            "task",
            task_id,
            f"Загружено фото до заявки #{task_id}",
            f"/task/{task_id}",
        )

    try:
        if filename:
            send_photo(
                f"uploads/{filename}",
                f"Фото до работы по заявке #{task_id}"
            )
    except Exception:
        pass

    return RedirectResponse(f"/task/{task_id}", status_code=302)


@router.post("/task/{task_id}/report")
async def update_report(
    request: Request,
    task_id: int,
    after_photo: UploadFile = File(None)
):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    form = await request.form()
    report = form.get("report")

    conn = connect()
    c = conn.cursor()

    task = c.execute("""
    SELECT * FROM tasks WHERE id=?
    """, (task_id,)).fetchone()

    if not task:
        conn.close()
        return RedirectResponse("/", status_code=302)

    if not can_access_task(username, role, task):
        conn.close()
        return RedirectResponse("/", status_code=302)

    previous_report = str(task["report"] or "")
    after_filename = task["after_photo"] if "after_photo" in task.keys() else ""
    try:
        new_after_filename = save_upload_file(
            after_photo,
            task_id,
            "after",
        )
    except UploadValidationError as error:
        conn.close()
        return RedirectResponse(
            f"/task/{task_id}?file_error={error.code}",
            status_code=302,
        )
    except ObjectStorageError:
        conn.close()
        return RedirectResponse(
            f"/task/{task_id}?file_error=storage",
            status_code=302,
        )

    if new_after_filename:
        after_filename = new_after_filename

    c.execute("""
    UPDATE tasks
    SET report=?, after_photo=?
    WHERE id=?
    """, (
        report,
        after_filename,
        task_id
    ))

    conn.commit()
    conn.close()

    log_task_activity(
        task_id,
        username,
        role,
        "Обновлён отчёт исполнителя",
        report or ""
    )

    if previous_report != str(report or ""):
        run_automation_event(
            get_task_company_id(task),
            "task_report_updated",
            "task",
            task_id,
            f"Отчёт по заявке #{task_id} обновлён",
            f"/task/{task_id}",
        )

    if new_after_filename:
        log_task_activity(
            task_id,
            username,
            role,
            "Загружено фото после",
            new_after_filename
        )

        run_automation_event(
            get_task_company_id(task),
            "task_photo_uploaded",
            "task",
            task_id,
            f"Загружено фото после заявки #{task_id}",
            f"/task/{task_id}",
        )

    try:
        send_message(
            f"""
📝 Отчёт по заявке #{task_id}

Клиент: {task['client']}
Исполнитель: {task['worker']}

Отчёт:
{report}
"""
        )

        if new_after_filename:
            send_photo(
                f"uploads/{new_after_filename}",
                f"Фото после работы по заявке #{task_id}"
            )
    except Exception:
        pass

    return RedirectResponse(
        f"/task/{task_id}",
        status_code=302
    )



@router.post("/task/{task_id}/archive")
async def archive_task(request: Request, task_id: int):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role not in ("boss", "manager"):
        return RedirectResponse("/", status_code=302)

    conn = connect()
    c = conn.cursor()

    task = c.execute("""
    SELECT * FROM tasks WHERE id=?
    """, (task_id,)).fetchone()

    if not task:
        conn.close()
        return RedirectResponse("/", status_code=302)

    if not can_access_task(username, role, task):
        conn.close()
        return RedirectResponse("/", status_code=302)

    c.execute("""
    UPDATE tasks
    SET archived=1
    WHERE id=?
    """, (task_id,))

    conn.commit()
    conn.close()

    try:
        log_task_activity(
            task_id,
            username,
            role,
            "Заявка отправлена в архив",
            f"Клиент: {task['client']}"
        )
    except Exception:
        pass

    run_automation_event(
        get_task_company_id(task),
        "task_archived",
        "task",
        task_id,
        f"Заявка #{task_id} отправлена в архив",
        f"/task/{task_id}",
    )

    return RedirectResponse("/", status_code=302)


@router.post("/task/{task_id}/unarchive")
async def unarchive_task(request: Request, task_id: int):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role not in ("boss", "manager"):
        return RedirectResponse("/", status_code=302)

    conn = connect()
    c = conn.cursor()

    task = c.execute("""
    SELECT * FROM tasks WHERE id=?
    """, (task_id,)).fetchone()

    if not task:
        conn.close()
        return RedirectResponse("/", status_code=302)

    if not can_access_task(username, role, task):
        conn.close()
        return RedirectResponse("/", status_code=302)

    c.execute("""
    UPDATE tasks
    SET archived=0
    WHERE id=?
    """, (task_id,))

    conn.commit()
    conn.close()

    try:
        log_task_activity(
            task_id,
            username,
            role,
            "Заявка возвращена из архива",
            f"Клиент: {task['client']}"
        )
    except Exception:
        pass

    run_automation_event(
        get_task_company_id(task),
        "task_restored",
        "task",
        task_id,
        f"Заявка #{task_id} восстановлена из архива",
        f"/task/{task_id}",
    )

    return RedirectResponse(f"/task/{task_id}", status_code=302)


@router.post("/task/{task_id}/delete")
async def delete_task(request: Request, task_id: int):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role not in ("boss", "manager"):
        return RedirectResponse("/", status_code=302)

    company_id = get_user_company_id(username)

    conn = connect()
    c = conn.cursor()

    task = c.execute("""
    SELECT *
    FROM tasks
    WHERE id=? AND company_id=?
    """, (task_id, company_id)).fetchone()

    if not task:
        conn.close()
        return RedirectResponse("/", status_code=302)

    c.execute("""
    UPDATE tasks
    SET archived=1
    WHERE id=? AND company_id=?
    """, (task_id, company_id))

    c.execute("""
    INSERT INTO task_activity (
        task_id,
        username,
        role,
        action,
        details,
        created_at
    )
    VALUES (?, ?, ?, ?, ?, ?)
    """, (
        task_id,
        username,
        role,
        "Заявка отправлена в архив",
        "Заявка скрыта с активного списка",
        datetime.now().strftime("%Y-%m-%d %H:%M")
    ))

    conn.commit()
    conn.close()

    run_automation_event(
        company_id,
        "task_archived",
        "task",
        task_id,
        f"Заявка #{task_id} отправлена в архив",
        f"/task/{task_id}",
    )

    return RedirectResponse("/?archived=1", status_code=302)


@router.get("/task/{task_id}/invoice")
async def task_invoice_pdf(request: Request, task_id: int):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    conn = connect()
    c = conn.cursor()

    task = c.execute("""
    SELECT * FROM tasks WHERE id=?
    """, (task_id,)).fetchone()

    if not task:
        conn.close()
        return HTMLResponse("Task not found", status_code=404)

    if not can_access_task(username, role, task):
        conn.close()
        return RedirectResponse("/", status_code=302)

    task_items = c.execute("""
    SELECT *
    FROM task_items
    WHERE task_id=?
    ORDER BY id ASC
    """, (task_id,)).fetchall()

    conn.close()

    estimate_total = sum(item["total"] for item in task_items)
    payment_status = task["payment_status"] if "payment_status" in task.keys() else "Не оплачено"
    task_company_id = get_task_company_id(task)
    settings = get_company_settings(task_company_id)

    pdf_path = DOCS_DIR / f"task_{task_id}_invoice.pdf"
    font_name = register_pdf_font()

    pdf = canvas.Canvas(str(pdf_path), pagesize=A4)
    page_width, page_height = A4

    pdf.setFont(font_name, 22)
    pdf.drawString(40, page_height - 50, f"Счёт по заявке №{task['id']}")

    pdf.setFont(font_name, 10)
    pdf.drawString(40, page_height - 72, f"Дата формирования: {datetime.now().strftime('%Y-%m-%d %H:%M')}")

    y = page_height - 100

    if settings and settings["company_name"]:
        pdf.setFont(font_name, 11)
        pdf.drawString(40, y, "Исполнитель / компания:")
        y -= 16
        y = draw_text(pdf, settings["company_name"], 40, y, font_name, size=10)
        if settings["phone"]:
            y = draw_text(pdf, f"Телефон: {settings['phone']}", 40, y, font_name, size=10)
        if settings["email"]:
            y = draw_text(pdf, f"Электронная почта: {settings['email']}", 40, y, font_name, size=10)
        if settings["address"]:
            y = draw_text(pdf, f"Адрес: {settings['address']}", 40, y, font_name, size=10)
        if settings["tax_number"]:
            y = draw_text(pdf, f"Налоговый номер: {settings['tax_number']}", 40, y, font_name, size=10)
        y -= 12
    else:
        y = page_height - 115

    fields = [
        ("Клиент", task["client"]),
        ("Телефон", task["phone"]),
        ("Адрес", task["address"]),
        ("Дата заявки", task["task_date"]),
        ("Исполнитель", task["worker"]),
        ("Статус оплаты", payment_status),
    ]

    for label, value in fields:
        pdf.setFont(font_name, 10)
        pdf.drawString(40, y, f"{label}:")
        y = draw_text(pdf, value, 150, y, font_name, size=10, max_chars=58, line_height=15)
        y -= 4

    y -= 16
    pdf.setFont(font_name, 13)
    pdf.drawString(40, y, "Позиции счёта")
    y -= 24

    if task_items:
        pdf.setFont(font_name, 9)
        pdf.drawString(40, y, "Наименование")
        pdf.drawString(275, y, "Кол-во")
        pdf.drawString(350, y, "Цена")
        pdf.drawString(430, y, "Сумма")
        y -= 14

        for item in task_items:
            if y < 90:
                pdf.showPage()
                y = page_height - 60
                pdf.setFont(font_name, 9)

            item_name = str(item["item_name"] or "")
            if len(item_name) > 42:
                item_name = item_name[:39] + "..."

            pdf.drawString(40, y, item_name)
            pdf.drawString(275, y, f"{item['qty']} {item['unit']}")
            pdf.drawString(350, y, f"{item['price']} RUB")
            pdf.drawString(430, y, f"{item['total']} RUB")
            y -= 16

        y -= 12
        pdf.setFont(font_name, 13)
        pdf.drawString(350, y, "Итого:")
        pdf.drawString(430, y, f"{estimate_total} RUB")
    else:
        y = draw_text(pdf, "Позиции счёта пока не добавлены", 40, y, font_name, size=10)

    y -= 35

    if settings and settings["bank_details"]:
        pdf.setFont(font_name, 12)
        pdf.drawString(40, y, "Банковские реквизиты")
        y -= 18
        y = draw_text(pdf, settings["bank_details"], 40, y, font_name, size=10)
        y -= 12

    pdf.setFont(font_name, 10)
    pdf.drawString(40, y, "Спасибо за обращение!")

    pdf.save()

    try:
        log_task_activity(
            task_id,
            username,
            role,
            "Сформирован PDF счёт",
            f"task_{task_id}_invoice.pdf"
        )
    except Exception:
        pass

    return FileResponse(
        str(pdf_path),
        media_type="application/pdf",
        filename=f"task_{task_id}_invoice.pdf"
    )


@router.get("/task/{task_id}/pdf")
async def task_pdf(request: Request, task_id: int):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    conn = connect()
    c = conn.cursor()

    task = c.execute("""
    SELECT * FROM tasks WHERE id=?
    """, (task_id,)).fetchone()

    if not task:
        conn.close()
        return HTMLResponse("Task not found", status_code=404)

    if not can_access_task(username, role, task):
        conn.close()
        return RedirectResponse("/", status_code=302)

    task_items = c.execute("""
    SELECT *
    FROM task_items
    WHERE task_id=?
    ORDER BY id ASC
    """, (task_id,)).fetchall()

    conn.close()

    estimate_total = sum(item["total"] for item in task_items)
    task_company_id = get_task_company_id(task)
    settings = get_company_settings(task_company_id)

    pdf_path = DOCS_DIR / f"task_{task_id}.pdf"
    font_name = register_pdf_font()

    pdf = canvas.Canvas(str(pdf_path), pagesize=A4)
    page_width, page_height = A4

    pdf.setFont(font_name, 20)
    pdf.drawString(40, page_height - 50, f"Акт выполненных работ №{task['id']}")

    pdf.setFont(font_name, 10)
    pdf.drawString(40, page_height - 72, f"Дата формирования: {datetime.now().strftime('%Y-%m-%d %H:%M')}")

    y = page_height - 100

    if settings and settings["company_name"]:
        pdf.setFont(font_name, 11)
        pdf.drawString(40, y, "Исполнитель / компания:")
        y -= 16
        y = draw_text(pdf, settings["company_name"], 40, y, font_name, size=10)
        if settings["phone"]:
            y = draw_text(pdf, f"Телефон: {settings['phone']}", 40, y, font_name, size=10)
        if settings["email"]:
            y = draw_text(pdf, f"Электронная почта: {settings['email']}", 40, y, font_name, size=10)
        if settings["address"]:
            y = draw_text(pdf, f"Адрес: {settings['address']}", 40, y, font_name, size=10)
        if settings["tax_number"]:
            y = draw_text(pdf, f"Налоговый номер: {settings['tax_number']}", 40, y, font_name, size=10)
        y -= 12
    else:
        y = page_height - 110

    fields = [
        ("Клиент", task["client"]),
        ("Телефон", task["phone"]),
        ("Адрес", task["address"]),
        ("Дата заявки", task["task_date"]),
        ("Исполнитель", task["worker"]),
        ("Приоритет", task["priority"]),
        ("Стоимость", f"{task['price']} RUB"),
        ("Статус", task["status"]),
        ("Статус оплаты", task["payment_status"] if "payment_status" in task.keys() else "Не оплачено"),
    ]

    for label, value in fields:
        pdf.setFont(font_name, 10)
        pdf.drawString(40, y, f"{label}:")
        y = draw_text(pdf, value, 145, y, font_name, size=10, max_chars=58, line_height=15)
        y -= 4

    y -= 8
    pdf.setFont(font_name, 12)
    pdf.drawString(40, y, "Описание работ")
    y -= 20
    y = draw_text(pdf, task["description"], 40, y, font_name, size=10)

    y -= 14
    pdf.setFont(font_name, 12)
    pdf.drawString(40, y, "Отчёт исполнителя")
    y -= 20
    y = draw_text(pdf, task["report"] if "report" in task.keys() else "", 40, y, font_name, size=10)

    y -= 18
    pdf.setFont(font_name, 12)
    pdf.drawString(40, y, "Смета / выполненные работы")
    y -= 22

    if task_items:
        pdf.setFont(font_name, 9)
        pdf.drawString(40, y, "Наименование")
        pdf.drawString(275, y, "Кол-во")
        pdf.drawString(350, y, "Цена")
        pdf.drawString(430, y, "Сумма")
        y -= 14

        for item in task_items:
            if y < 90:
                pdf.showPage()
                y = page_height - 60
                pdf.setFont(font_name, 9)

            pdf.setFont(font_name, 9)

            item_name = str(item["item_name"] or "")
            if len(item_name) > 42:
                item_name = item_name[:39] + "..."

            pdf.drawString(40, y, item_name)
            pdf.drawString(275, y, f"{item['qty']} {item['unit']}")
            pdf.drawString(350, y, f"{item['price']} RUB")
            pdf.drawString(430, y, f"{item['total']} RUB")
            y -= 16

        y -= 8
        pdf.setFont(font_name, 11)
        pdf.drawString(350, y, "Итого:")
        pdf.drawString(430, y, f"{estimate_total} RUB")
        y -= 18
    else:
        y = draw_text(pdf, "Смета пока не заполнена", 40, y, font_name, size=10)
        y -= 10

    y -= 18
    y = draw_pdf_image(pdf, task["photo"], "Фото до работы", 40, y, font_name)
    y = draw_pdf_image(pdf, task["after_photo"] if "after_photo" in task.keys() else "", "Фото после работы", 40, y, font_name)

    if y < 120:
        pdf.showPage()
        y = page_height - 60

    pdf.setFont(font_name, 11)
    pdf.drawString(40, y, "Подпись клиента: ______________________________")
    y -= 35
    pdf.drawString(40, y, "Подпись исполнителя: ___________________________")

    pdf.save()

    log_task_activity(
        task_id,
        username,
        role,
        "Сформирован PDF акт",
        f"task_{task_id}_act.pdf"
    )

    return FileResponse(
        str(pdf_path),
        media_type="application/pdf",
        filename=f"task_{task_id}_act.pdf"
    )
