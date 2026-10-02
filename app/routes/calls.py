"""Call history and AI call analysis routes."""

import csv
import io
import mimetypes
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, File, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse, Response

from app.database import connect
from app.deps import get_role, get_user, get_user_company_id
from app.object_storage import ObjectStorageError, save_storage_fileobj
from app.services.call_analysis import analyze_call_text
from app.services.common import (
    build_dashboard_links,
    create_call_follow_up_notification,
    create_notification,
    get_company_settings,
    require_feature,
)
from app.uploads import (
    ALLOWED_CALL_AUDIO_EXTENSIONS,
    CALL_AUDIO_UPLOAD_MAX_BYTES,
    UPLOAD_DIR,
    UploadValidationError,
    safe_call_audio_filename,
    storage_file_response,
    validate_upload_file,
)
from app.services.email_inbox import (
    extract_email_fields,
    get_company_service_names,
)
from app.templating import templates

router = APIRouter()

def get_call_history_for_company(
    company_id: int,
    status: str = "",
    client_id: str = "",
    search: str = "",
    content: str = "",
    limit=50,
):
    selected_call_status = status if status in ("completed", "missed", "follow_up") else ""
    selected_call_content = content if content in ("audio", "analysis") else ""
    selected_call_search = str(search or "").strip()[:100]
    selected_call_client_id = None

    try:
        selected_call_client_id = int(str(client_id or "").strip()) if str(client_id or "").strip() else None
    except ValueError:
        selected_call_client_id = None

    call_filters = ["call_records.company_id=?"]
    call_params = [company_id]

    if selected_call_status:
        call_filters.append("call_records.status=?")
        call_params.append(selected_call_status)

    if selected_call_client_id:
        call_filters.append("call_records.client_id=?")
        call_params.append(selected_call_client_id)

    if selected_call_content == "audio":
        call_filters.append("COALESCE(call_records.audio_filename, '')!=''")

    if selected_call_content == "analysis":
        call_filters.append("""
        (
            COALESCE(call_records.transcript, '')!=''
            OR COALESCE(call_records.ai_summary, '')!=''
        )
        """)

    if selected_call_search:
        search_pattern = f"%{selected_call_search.lower()}%"
        call_filters.append("""
        (
            LOWER(COALESCE(call_records.summary, '')) LIKE ?
            OR LOWER(COALESCE(call_records.transcript, '')) LIKE ?
            OR LOWER(COALESCE(call_records.ai_summary, '')) LIKE ?
            OR LOWER(COALESCE(call_records.phone, '')) LIKE ?
            OR LOWER(COALESCE(clients.name, '')) LIKE ?
        )
        """)
        call_params.extend([
            search_pattern,
            search_pattern,
            search_pattern,
            search_pattern,
            search_pattern,
        ])

    call_where_sql = " AND ".join(call_filters)
    limit_clause = ""
    list_params = list(call_params)

    if limit is not None:
        limit_clause = "LIMIT ?"
        list_params.append(limit)

    conn = connect()
    c = conn.cursor()

    call_records = c.execute(f"""
    SELECT
        call_records.*,
        clients.name AS client_name
    FROM call_records
    LEFT JOIN clients
      ON clients.id=call_records.client_id
     AND clients.company_id=call_records.company_id
    WHERE {call_where_sql}
    ORDER BY COALESCE(call_records.call_at, call_records.created_at) DESC,
             call_records.id DESC
    {limit_clause}
    """, list_params).fetchall()

    call_stats_row = c.execute(f"""
    SELECT
        COUNT(*) AS total,
        SUM(CASE WHEN call_records.status='missed' THEN 1 ELSE 0 END) AS missed,
        SUM(CASE WHEN call_records.status='follow_up' THEN 1 ELSE 0 END) AS follow_up,
        SUM(CASE WHEN COALESCE(call_records.audio_filename, '')!='' THEN 1 ELSE 0 END) AS with_audio,
        SUM(
            CASE
            WHEN COALESCE(call_records.transcript, '')!=''
              OR COALESCE(call_records.ai_summary, '')!=''
            THEN 1 ELSE 0 END
        ) AS with_analysis
    FROM call_records
    LEFT JOIN clients
      ON clients.id=call_records.client_id
     AND clients.company_id=call_records.company_id
    WHERE {call_where_sql}
    """, call_params).fetchone()

    call_stats = {
        "total": call_stats_row["total"] or 0,
        "missed": call_stats_row["missed"] or 0,
        "follow_up": call_stats_row["follow_up"] or 0,
        "with_audio": call_stats_row["with_audio"] or 0,
        "with_analysis": call_stats_row["with_analysis"] or 0,
    }

    conn.close()

    return {
        "call_records": call_records,
        "call_stats": call_stats,
        "selected_call_status": selected_call_status,
        "selected_call_content": selected_call_content,
        "selected_call_client_id": selected_call_client_id,
        "selected_call_search": selected_call_search,
    }


@router.get("/calls", response_class=HTMLResponse)
async def calls_page(
    request: Request,
    status: str = "",
    client_id: str = "",
    search: str = "",
    content: str = ""
):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role not in ("boss", "manager"):
        return RedirectResponse("/", status_code=302)

    company_id = get_user_company_id(username)
    disabled_response = require_feature(company_id, "calls")

    if disabled_response:
        return disabled_response

    settings = get_company_settings(company_id)
    call_data = get_call_history_for_company(
        company_id,
        status=status,
        client_id=client_id,
        search=search,
        content=content,
        limit=50,
    )

    conn = connect()
    c = conn.cursor()

    clients = c.execute("""
    SELECT id, name, phone
    FROM clients
    WHERE company_id=?
    ORDER BY name, id
    """, (company_id,)).fetchall()

    conn.close()

    return templates.TemplateResponse(
        request,
        "calls.html",
        {
            "request": request,
            "username": username,
            "role": role,
            "settings": settings,
            "clients": clients,
            "call_records": call_data["call_records"],
            "call_stats": call_data["call_stats"],
            "selected_call_status": call_data["selected_call_status"],
            "selected_call_content": call_data["selected_call_content"],
            "selected_call_client_id": call_data["selected_call_client_id"],
            "selected_call_search": call_data["selected_call_search"]
        }
    )


@router.get("/calls/export")
async def calls_export(
    request: Request,
    status: str = "",
    client_id: str = "",
    search: str = "",
    content: str = ""
):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role not in ("boss", "manager"):
        return RedirectResponse("/", status_code=302)

    company_id = get_user_company_id(username)
    disabled_response = require_feature(company_id, "calls")

    if disabled_response:
        return disabled_response

    settings = get_company_settings(company_id)

    if not settings or not settings["calls_enabled"]:
        return RedirectResponse("/calls", status_code=302)

    call_data = get_call_history_for_company(
        company_id,
        status=status,
        client_id=client_id,
        search=search,
        content=content,
        limit=None,
    )
    call_records = call_data["call_records"]
    selected_call_status = call_data["selected_call_status"]
    selected_call_content = call_data["selected_call_content"]
    selected_call_search = call_data["selected_call_search"]
    selected_call_client_id = call_data["selected_call_client_id"]

    direction_labels = {
        "incoming": "Входящий",
        "outgoing": "Исходящий",
    }
    status_labels = {
        "completed": "Состоялся",
        "missed": "Пропущен",
        "follow_up": "Нужен контакт",
    }

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "Дата",
        "Клиент",
        "Телефон",
        "Тип",
        "Результат",
        "Длительность, минут",
        "Заметка",
        "Расшифровка",
        "ИИ-резюме",
        "Автор"
    ])

    for call in call_records:
        writer.writerow([
            call["call_at"] or call["created_at"],
            call["client_name"] or "Без привязки",
            call["phone"] or "",
            direction_labels.get(call["direction"], call["direction"] or ""),
            status_labels.get(call["status"], call["status"] or ""),
            call["duration_minutes"] or 0,
            call["summary"] or "",
            call["transcript"] or "",
            call["ai_summary"] or "",
            call["username"] or ""
        ])

    filename_parts = [
        selected_call_status or "all",
        str(selected_call_client_id or "all"),
        "search" if selected_call_search else "all",
        selected_call_content or "all",
    ]
    filename = "calls_" + "_".join(filename_parts) + ".csv"

    return Response(
        content="\ufeff" + output.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f"attachment; filename={filename}"
        }
    )


@router.get("/calls/{call_id}", response_class=HTMLResponse)
async def call_detail(request: Request, call_id: int):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role not in ("boss", "manager"):
        return RedirectResponse("/", status_code=302)

    company_id = get_user_company_id(username)
    disabled_response = require_feature(company_id, "calls")

    if disabled_response:
        return disabled_response

    settings = get_company_settings(company_id)

    if not settings or not settings["calls_enabled"]:
        return RedirectResponse("/calls", status_code=302)

    conn = connect()
    c = conn.cursor()

    call = c.execute("""
    SELECT
        call_records.*,
        clients.name AS client_name,
        clients.phone AS client_phone
    FROM call_records
    LEFT JOIN clients
      ON clients.id=call_records.client_id
     AND clients.company_id=call_records.company_id
    WHERE call_records.id=?
      AND call_records.company_id=?
    """, (call_id, company_id)).fetchone()

    if not call:
        conn.close()
        return RedirectResponse("/calls", status_code=302)

    linked_tasks = c.execute("""
    SELECT id, status, task_date, description
    FROM tasks
    WHERE company_id=?
      AND source_call_id=?
      AND COALESCE(archived, 0)=0
    ORDER BY id DESC
    """, (company_id, call_id)).fetchall()

    conn.close()

    call_text_parts = [
        call["summary"],
        call["transcript"],
        call["ai_summary"],
    ]
    call_text = "\n".join(
        str(part or "") for part in call_text_parts if str(part or "").strip()
    )
    call_extracted = {}
    if call_text:
        call_extracted = extract_email_fields(
            call_text,
            "",
            "",
            get_company_service_names(company_id),
        )

    return templates.TemplateResponse(
        request,
        "call_detail.html",
        {
            "request": request,
            "username": username,
            "role": role,
            "settings": settings,
            "call": call,
            "linked_tasks": linked_tasks,
            "call_extracted": call_extracted,
        }
    )


@router.post("/calls/{call_id}/analysis")
async def update_call_analysis(request: Request, call_id: int):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role not in ("boss", "manager"):
        return RedirectResponse("/", status_code=302)

    company_id = get_user_company_id(username)
    disabled_response = require_feature(company_id, "calls")

    if disabled_response:
        return disabled_response

    settings = get_company_settings(company_id)

    if not settings or not settings["calls_enabled"]:
        return RedirectResponse("/calls", status_code=302)

    form = await request.form()
    transcript = str(form.get("transcript") or "").strip()[:10000]
    requested_ai_summary = str(form.get("ai_summary") or "").strip()[:5000]

    conn = connect()
    c = conn.cursor()

    call = c.execute("""
    SELECT id, ai_summary, summary, status,
           ai_sentiment, ai_sale_detected, ai_follow_up_detected
    FROM call_records
    WHERE id=? AND company_id=?
    """, (call_id, company_id)).fetchone()

    if not call:
        conn.close()
        return RedirectResponse("/calls", status_code=302)

    ai_calls_enabled = bool(settings["ai_calls_enabled"])
    ai_summary = requested_ai_summary if ai_calls_enabled else (call["ai_summary"] or "")

    analysis_sentiment = call["ai_sentiment"] or ""
    analysis_sale = int(call["ai_sale_detected"] or 0)
    analysis_follow_up = int(call["ai_follow_up_detected"] or 0)
    new_status = call["status"]

    if ai_calls_enabled:
        analysis = analyze_call_text(
            call["summary"],
            transcript,
            ai_summary,
        )
        analysis_sentiment = analysis["sentiment"]
        analysis_sale = int(analysis["sale_detected"])
        analysis_follow_up = int(analysis["follow_up_detected"])

        if analysis_follow_up and call["status"] == "completed":
            new_status = "follow_up"

    c.execute("""
    UPDATE call_records
    SET transcript=?,
        ai_summary=?,
        ai_sentiment=?,
        ai_sale_detected=?,
        ai_follow_up_detected=?,
        status=?
    WHERE id=? AND company_id=?
    """, (
        transcript,
        ai_summary,
        analysis_sentiment,
        analysis_sale,
        analysis_follow_up,
        new_status,
        call_id,
        company_id
    ))

    conn.commit()
    conn.close()

    return RedirectResponse(f"/calls/{call_id}?updated=1", status_code=302)


@router.post("/calls/{call_id}/complete")
async def complete_call_follow_up(request: Request, call_id: int):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role not in ("boss", "manager"):
        return RedirectResponse("/", status_code=302)

    company_id = get_user_company_id(username)
    disabled_response = require_feature(company_id, "calls")

    if disabled_response:
        return disabled_response

    settings = get_company_settings(company_id)

    if not settings or not settings["calls_enabled"]:
        return RedirectResponse("/calls", status_code=302)

    conn = connect()
    c = conn.cursor()

    call = c.execute("""
    SELECT id, status
    FROM call_records
    WHERE id=? AND company_id=?
    """, (call_id, company_id)).fetchone()

    if not call:
        conn.close()
        return RedirectResponse("/calls", status_code=302)

    if call["status"] != "follow_up":
        conn.close()
        return RedirectResponse(f"/calls/{call_id}", status_code=302)

    c.execute("""
    UPDATE call_records
    SET status='completed'
    WHERE id=? AND company_id=?
    """, (call_id, company_id))

    c.execute("""
    UPDATE notifications
    SET is_read=1
    WHERE company_id=?
      AND username=?
      AND title='Нужен контакт по звонку'
      AND link=?
    """, (
        company_id,
        username,
        f"/calls/{call_id}",
    ))

    conn.commit()
    conn.close()

    from app.main import run_automation_event

    run_automation_event(
        company_id,
        "call_follow_up_completed",
        "call",
        call_id,
        f"Контакт по звонку #{call_id} закрыт",
        f"/calls/{call_id}",
    )

    return RedirectResponse(f"/calls/{call_id}?completed=1", status_code=302)


@router.post("/calls/{call_id}/audio")
async def upload_call_audio(
    request: Request,
    call_id: int,
    audio: UploadFile = File(None)
):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role not in ("boss", "manager"):
        return RedirectResponse("/", status_code=302)

    company_id = get_user_company_id(username)
    disabled_response = require_feature(company_id, "calls")

    if disabled_response:
        return disabled_response

    settings = get_company_settings(company_id)

    if not settings or not settings["calls_enabled"]:
        return RedirectResponse("/calls", status_code=302)

    conn = connect()
    c = conn.cursor()

    call = c.execute("""
    SELECT id, audio_filename
    FROM call_records
    WHERE id=? AND company_id=?
    """, (call_id, company_id)).fetchone()

    if not call:
        conn.close()
        return RedirectResponse("/calls", status_code=302)

    if not audio or not audio.filename:
        conn.close()
        return RedirectResponse(f"/calls/{call_id}?audio_error=empty", status_code=302)

    try:
        validate_upload_file(
            audio,
            ALLOWED_CALL_AUDIO_EXTENSIONS,
            CALL_AUDIO_UPLOAD_MAX_BYTES,
        )
    except UploadValidationError as error:
        conn.close()
        return RedirectResponse(
            f"/calls/{call_id}?audio_error={error.code}",
            status_code=302,
        )

    stored_filename = safe_call_audio_filename(call_id, audio.filename)
    safe_content_type = (
        mimetypes.guess_type(stored_filename)[0]
        or "application/octet-stream"
    )
    try:
        save_storage_fileobj(
            audio.file,
            f"call_audio/{stored_filename}",
            UPLOAD_DIR,
            safe_content_type,
        )
    except ObjectStorageError:
        conn.close()
        return RedirectResponse(
            f"/calls/{call_id}?audio_error=storage",
            status_code=302,
        )

    old_filename = Path(call["audio_filename"] or "").name

    c.execute("""
    UPDATE call_records
    SET audio_filename=?
    WHERE id=? AND company_id=?
    """, (
        stored_filename,
        call_id,
        company_id
    ))

    conn.commit()
    conn.close()

    if old_filename and old_filename != stored_filename:
        try:
            delete_storage_object(
                f"call_audio/{old_filename}",
                UPLOAD_DIR,
            )
        except (ObjectStorageError, ValueError):
            pass

    return RedirectResponse(f"/calls/{call_id}?audio_uploaded=1", status_code=302)


@router.get("/calls/{call_id}/audio")
async def download_call_audio(request: Request, call_id: int):

    username = get_user(request)

    if not username:
        return Response(status_code=404)

    role = get_role(username)

    if role not in ("boss", "manager"):
        return Response(status_code=404)

    company_id = get_user_company_id(username)

    conn = connect()
    c = conn.cursor()

    call = c.execute("""
    SELECT audio_filename
    FROM call_records
    WHERE id=? AND company_id=?
    """, (call_id, company_id)).fetchone()

    conn.close()

    if not call:
        return Response(status_code=404)

    audio_filename = Path(call["audio_filename"] or "").name

    if not audio_filename or audio_filename != (call["audio_filename"] or ""):
        return Response(status_code=404)

    return storage_file_response(
        f"call_audio/{audio_filename}",
        UPLOAD_DIR,
        download_name=audio_filename,
        request=request,
    )


@router.post("/calls")
async def create_call_record(request: Request):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role not in ("boss", "manager"):
        return RedirectResponse("/", status_code=302)

    company_id = get_user_company_id(username)
    disabled_response = require_feature(company_id, "calls")

    if disabled_response:
        return disabled_response

    settings = get_company_settings(company_id)

    if not settings or not settings["calls_enabled"]:
        return RedirectResponse("/calls?error=disabled", status_code=302)

    form = await request.form()
    client_id_raw = str(form.get("client_id") or "").strip()
    phone = str(form.get("phone") or "").strip()[:80]
    summary = str(form.get("summary") or "").strip()[:1000]
    direction = str(form.get("direction") or "incoming").strip()
    status = str(form.get("status") or "completed").strip()
    call_at = str(form.get("call_at") or "").strip().replace("T", " ")

    if direction not in ("incoming", "outgoing"):
        direction = "incoming"

    if status not in ("completed", "missed", "follow_up"):
        status = "completed"

    try:
        duration_minutes = int(str(form.get("duration_minutes") or "0"))
    except ValueError:
        duration_minutes = 0

    duration_minutes = max(0, min(duration_minutes, 1440))

    conn = connect()
    c = conn.cursor()

    client_id = None
    client = None

    if client_id_raw:
        try:
            client_id = int(client_id_raw)
        except ValueError:
            client_id = None

        if client_id:
            client = c.execute("""
            SELECT id, name, phone
            FROM clients
            WHERE id=?
              AND company_id=?
            """, (client_id, company_id)).fetchone()

        if not client:
            conn.close()
            return RedirectResponse("/calls?error=client", status_code=302)

        if not phone:
            phone = str(client["phone"] or "").strip()[:80]

    if not call_at:
        call_at = datetime.now().strftime("%Y-%m-%d %H:%M")

    if not client_id and not phone and not summary:
        conn.close()
        return RedirectResponse("/calls?error=empty", status_code=302)

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
            client["name"] if client else "",
            client_id,
            summary,
            phone,
            call_id,
        )

        from app.main import run_automation_event

        run_automation_event(
            company_id,
            "call_follow_up_created",
            "call",
            call_id,
            f"Нужен контакт по звонку #{call_id}: {summary or phone}",
            f"/calls/{call_id}",
        )

    return RedirectResponse("/calls?created=1", status_code=302)
