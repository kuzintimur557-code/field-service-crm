"""Email inbox routes (AI Inbox / Email Dispatcher)."""

import hmac
import os
from datetime import datetime

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from app.database import connect
from app.deps import (
    get_role,
    get_user,
    get_user_company_id,
)
from app.services.common import (
    build_dashboard_links,
    create_notification,
    get_company_settings,
    has_feature,
    log_task_activity,
    require_feature,
)
from app.services.email_inbox import (
    EMAIL_STATUSES,
    MAX_RAW_LENGTH,
    find_or_create_inbox_client,
    get_email_message,
    get_email_messages,
    normalize_inbox_payload,
    parse_extracted_fields,
    parse_raw_email,
    save_email_message,
    set_email_message_status,
    suggest_inbox_slots,
)
from app.telegram_utils import send_message_to_chat
from app.templating import templates

router = APIRouter()

@router.get("/inbox", response_class=HTMLResponse)
async def inbox_page(request: Request, status: str = ""):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role not in ("boss", "manager"):
        return RedirectResponse("/", status_code=302)

    company_id = get_user_company_id(username)
    disabled_response = require_feature(company_id, "inbox")

    if disabled_response:
        return disabled_response

    settings = get_company_settings(company_id)

    if status not in EMAIL_STATUSES:
        status = ""

    messages = get_email_messages(company_id, status=status, limit=100)

    for message in messages:
        message["extracted"] = parse_extracted_fields(message.get("extracted_json"))

    return templates.TemplateResponse(
        request,
        "inbox.html",
        {
            "request": request,
            "username": username,
            "role": role,
            "settings": settings,
            "links": build_dashboard_links(),
            "messages": messages,
            "selected_status": status,
        }
    )


@router.get("/inbox/{message_id}", response_class=HTMLResponse)
async def inbox_detail_page(request: Request, message_id: int):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role not in ("boss", "manager"):
        return RedirectResponse("/", status_code=302)

    company_id = get_user_company_id(username)
    disabled_response = require_feature(company_id, "inbox")

    if disabled_response:
        return disabled_response

    message = get_email_message(company_id, message_id)

    if not message:
        return RedirectResponse("/inbox", status_code=302)

    message["extracted"] = parse_extracted_fields(message.get("extracted_json"))
    settings = get_company_settings(company_id)

    slot_suggestions = []
    workers = []
    recommended_worker = ""

    if message["status"] == "new":
        slot_suggestions = suggest_inbox_slots(
            company_id,
            start_date=message["extracted"].get("date", ""),
        )

        conn = connect()
        c = conn.cursor()
        workers = c.execute("""
        SELECT username
        FROM users
        WHERE company_id=? AND role='worker' AND COALESCE(is_active, 1)=1
        ORDER BY username
        """, (company_id,)).fetchall()
        conn.close()

        if slot_suggestions:
            recommended_worker = slot_suggestions[0]["worker"]

    return templates.TemplateResponse(
        request,
        "inbox_detail.html",
        {
            "request": request,
            "username": username,
            "role": role,
            "settings": settings,
            "links": build_dashboard_links(),
            "message": message,
            "slot_suggestions": slot_suggestions,
            "workers": workers,
            "recommended_worker": recommended_worker,
            "error": request.query_params.get("error", ""),
        }
    )


@router.post("/inbox/{message_id}/confirm")
async def inbox_confirm(request: Request, message_id: int):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role not in ("boss", "manager"):
        return RedirectResponse("/", status_code=302)

    company_id = get_user_company_id(username)
    disabled_response = require_feature(company_id, "inbox")

    if disabled_response:
        return disabled_response

    message = get_email_message(company_id, message_id)

    if not message:
        return RedirectResponse("/inbox", status_code=302)

    if message["status"] != "new":
        return RedirectResponse("/inbox", status_code=302)

    form = await request.form()

    client_name = (form.get("client_name") or "").strip()[:200]
    phone = (form.get("phone") or "").strip()[:60]
    email = (form.get("email") or "").strip()[:200]
    address = (form.get("address") or "").strip()[:300]
    task_date = (form.get("task_date") or "").strip()[:10]
    description = (form.get("description") or "").strip()[:5000]
    price = (form.get("price") or "").strip()[:40]
    selected_worker = (form.get("worker") or "").strip()[:120]

    if selected_worker:
        conn = connect()
        c = conn.cursor()
        worker_user = c.execute("""
        SELECT username
        FROM users
        WHERE company_id=? AND role='worker'
          AND COALESCE(is_active, 1)=1 AND username=?
        """, (company_id, selected_worker)).fetchone()
        conn.close()

        if not worker_user:
            selected_worker = ""

    if not client_name:
        return RedirectResponse(
            f"/inbox/{message_id}?error=client_required",
            status_code=302,
        )

    if task_date:
        try:
            datetime.strptime(task_date, "%Y-%m-%d")
        except ValueError:
            return RedirectResponse(
                f"/inbox/{message_id}?error=invalid_date",
                status_code=302,
            )

    client_id = find_or_create_inbox_client(
        company_id, client_name, phone, email, address
    )

    conn = connect()
    c = conn.cursor()

    try:
        c.execute("""
        INSERT INTO tasks (
            company_id,
            client_id,
            client,
            phone,
            address,
            description,
            task_date,
            worker,
            workers,
            priority,
            price,
            status,
            created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            company_id,
            client_id,
            client_name,
            phone,
            address,
            description,
            task_date,
            selected_worker,
            selected_worker,
            "Обычный",
            price,
            "Новая",
            datetime.now().strftime("%Y-%m-%d %H:%M"),
        ))

        task_id = c.lastrowid
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    if selected_worker:
        create_notification(
            company_id,
            selected_worker,
            f"Назначена новая заявка #{task_id}",
            (
                f"Клиент: {client_name}. "
                f"Дата: {task_date or 'не указана'}."
            ),
            f"/task/{task_id}",
        )

    set_email_message_status(
        company_id,
        message_id,
        "confirmed",
        task_id=task_id,
        client_id=client_id,
    )

    log_task_activity(
        task_id,
        username,
        role,
        "Создано из письма",
        f"Письмо №{message_id}: {message['subject'] or '(без темы)'}"[:200],
    )

    return RedirectResponse(f"/task/{task_id}", status_code=302)


@router.post("/inbox/{message_id}/reject")
async def inbox_reject(request: Request, message_id: int):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role not in ("boss", "manager"):
        return RedirectResponse("/", status_code=302)

    company_id = get_user_company_id(username)
    disabled_response = require_feature(company_id, "inbox")

    if disabled_response:
        return disabled_response

    message = get_email_message(company_id, message_id)

    if message and message["status"] == "new":
        set_email_message_status(company_id, message_id, "rejected")

    return RedirectResponse("/inbox", status_code=302)


@router.post("/api/inbox/email")
async def receive_inbox_email(request: Request):
    inbox_secret = (os.getenv("INBOX_WEBHOOK_SECRET") or "").strip()

    if not inbox_secret:
        return JSONResponse(
            {"ok": False, "error": "INBOX_WEBHOOK_SECRET is not configured"},
            status_code=503,
        )
    token = (request.headers.get("x-inbox-secret") or "").strip()
    if not token or not hmac.compare_digest(token, inbox_secret):
        return JSONResponse(
            {"ok": False, "error": "forbidden"},
            status_code=403,
        )

    content_type = (
        (request.headers.get("content-type") or "")
        .split(";")[0]
        .strip()
        .lower()
    )

    if content_type == "application/json":
        try:
            data = await request.json()
        except Exception:
            return JSONResponse(
                {"ok": False, "error": "invalid_json"},
                status_code=400,
            )
    else:
        raw_body = await request.body()

        if len(raw_body) > MAX_RAW_LENGTH:
            return JSONResponse(
                {"ok": False, "error": "message_too_large"},
                status_code=413,
            )

        try:
            data = parse_raw_email(raw_body)
        except ValueError as e:
            return JSONResponse(
                {"ok": False, "error": str(e)},
                status_code=400,
            )

        try:
            data["company_id"] = int(
                request.query_params.get("company_id") or 0
            )
        except (TypeError, ValueError):
            data["company_id"] = 0

    try:
        payload = normalize_inbox_payload(data)
    except ValueError as e:
        return JSONResponse(
            {"ok": False, "error": str(e)},
            status_code=400,
        )

    company_id = payload["company_id"]

    conn = connect()
    c = conn.cursor()
    company = c.execute(
        "SELECT id FROM companies WHERE id=?",
        (company_id,),
    ).fetchone()

    if not company:
        conn.close()
        return JSONResponse(
            {"ok": False, "error": "company_not_found"},
            status_code=404,
        )
    conn.close()

    if not has_feature(company_id, "inbox"):
        return JSONResponse(
            {"ok": False, "error": "feature_disabled"},
            status_code=403,
        )

    result = save_email_message(payload)

    if result["created"]:
        conn = connect()
        c = conn.cursor()
        recipients = c.execute("""
        SELECT username, telegram_chat_id
        FROM users
        WHERE company_id=? AND role IN ('boss', 'manager')
        """, (company_id,)).fetchall()
        conn.close()

        subject = payload["subject"] or "(без темы)"
        for recipient in recipients:
            create_notification(
                company_id,
                recipient["username"],
                "Новое письмо в почте",
                subject[:200],
                "/inbox",
            )

            recipient_chat_id = (recipient["telegram_chat_id"] or "").strip()
            if recipient_chat_id:
                send_message_to_chat(
                    recipient_chat_id,
                    f"📩 Новое письмо: {subject[:300]}",
                )

    message = result["message"]
    return {
        "ok": True,
        "created": result["created"],
        "duplicate": not result["created"],
        "id": message["id"],
    }
