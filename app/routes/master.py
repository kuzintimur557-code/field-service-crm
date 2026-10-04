"""Private master mode and first-launch onboarding routes."""

from datetime import datetime

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app.database import connect
from app.deps import get_role, get_user, get_user_company_id
from app.services.common import (
    build_dashboard_links,
    create_task_from_draft,
    get_company_settings,
)
from app.services.email_inbox import (
    extract_email_fields,
    get_company_service_names,
    suggest_inbox_slots,
)
from app.services.subscriptions import get_company_subscription
from app.templating import templates

router = APIRouter()

@router.get("/onboarding", response_class=HTMLResponse)
async def onboarding_page(request: Request):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role not in ("boss", "manager"):
        return RedirectResponse("/", status_code=302)

    company_id = get_user_company_id(username)
    settings = get_company_settings(company_id)
    subscription = get_company_subscription(company_id)

    conn = connect()
    c = conn.cursor()

    clients_count = c.execute(
        "SELECT COUNT(*) FROM clients WHERE company_id=?",
        (company_id,),
    ).fetchone()[0]
    tasks_count = c.execute(
        "SELECT COUNT(*) FROM tasks WHERE company_id=?",
        (company_id,),
    ).fetchone()[0]
    workers_count = c.execute("""
    SELECT COUNT(*)
    FROM users
    WHERE company_id=? AND role='worker' AND COALESCE(is_active, 1)=1
    """, (company_id,)).fetchone()[0]

    conn.close()

    profile_done = bool(
        (settings["company_name"] or "").strip()
        or (settings["phone"] or "").strip()
    )

    steps = [
        {
            "title": "Заполнить профиль компании",
            "done": profile_done,
            "link": "/settings",
        },
        {
            "title": "Добавить первого клиента",
            "done": clients_count > 0,
            "link": "/clients",
        },
        {
            "title": f"Создать первую {(settings['task_label'] or 'заявку').lower()}",
            "done": tasks_count > 0,
            "link": "/create-task",
        },
        {
            "title": f"Пригласить {(settings['worker_label'] or 'исполнителя').lower()}",
            "done": workers_count > 0,
            "link": "/workers",
        },
        {
            "title": "Выбрать тариф и активировать подписку",
            "done": subscription["status"] == "active",
            "link": "/billing",
        },
    ]

    done_count = sum(1 for step in steps if step["done"])

    return templates.TemplateResponse(
        request,
        "onboarding.html",
        {
            "request": request,
            "username": username,
            "role": role,
            "settings": settings,
            "links": build_dashboard_links(),
            "steps": steps,
            "done_count": done_count,
            "total_count": len(steps),
        }
    )


@router.get("/master", response_class=HTMLResponse)
async def master_today_page(request: Request):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role not in ("boss", "manager"):
        return RedirectResponse("/", status_code=302)

    company_id = get_user_company_id(username)
    settings = get_company_settings(company_id)

    today = datetime.now().strftime("%Y-%m-%d")
    month = today[:7]

    conn = connect()
    c = conn.cursor()

    tasks_today = c.execute("""
    SELECT *
    FROM tasks
    WHERE company_id=?
      AND COALESCE(archived, 0)=0
      AND task_date LIKE ?
    ORDER BY COALESCE(time_from, ''), id
    """, (company_id, f"{today}%")).fetchall()

    revenue_today = c.execute("""
    SELECT COALESCE(SUM(
        CAST(REPLACE(COALESCE(price, '0'), ',', '.') AS REAL)
    ), 0)
    FROM tasks
    WHERE company_id=?
      AND COALESCE(archived, 0)=0
      AND status='Завершено'
      AND task_date LIKE ?
    """, (company_id, f"{today}%")).fetchone()[0]

    revenue_month = c.execute("""
    SELECT COALESCE(SUM(
        CAST(REPLACE(COALESCE(price, '0'), ',', '.') AS REAL)
    ), 0)
    FROM tasks
    WHERE company_id=?
      AND COALESCE(archived, 0)=0
      AND status='Завершено'
      AND substr(task_date, 1, 7)=?
    """, (company_id, month)).fetchone()[0]

    conn.close()

    return templates.TemplateResponse(
        request,
        "master.html",
        {
            "request": request,
            "username": username,
            "role": role,
            "settings": settings,
            "links": build_dashboard_links(),
            "tasks_today": tasks_today,
            "revenue_today": revenue_today,
            "revenue_month": revenue_month,
            "today": today,
        }
    )


@router.get("/master/voice", response_class=HTMLResponse)
async def master_voice_page(request: Request):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role not in ("boss", "manager"):
        return RedirectResponse("/", status_code=302)

    company_id = get_user_company_id(username)
    settings = get_company_settings(company_id)

    return templates.TemplateResponse(
        request,
        "master_voice.html",
        {
            "request": request,
            "username": username,
            "role": role,
            "settings": settings,
            "links": build_dashboard_links(),
        }
    )


@router.post("/master/voice/preview")
async def master_voice_preview(request: Request):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role not in ("boss", "manager"):
        return RedirectResponse("/", status_code=302)

    company_id = get_user_company_id(username)
    settings = get_company_settings(company_id)

    form = await request.form()
    text = str(form.get("note") or "").strip()[:5000]

    if not text:
        return RedirectResponse("/master/voice?error=empty", status_code=302)

    parsed = extract_email_fields(
        text,
        "",
        "",
        get_company_service_names(company_id),
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

    slot_suggestions = suggest_inbox_slots(
        company_id,
        start_date=parsed.get("date", ""),
    )
    recommended_worker = (
        slot_suggestions[0]["worker"] if slot_suggestions else ""
    )

    return templates.TemplateResponse(
        request,
        "master_voice_preview.html",
        {
            "request": request,
            "username": username,
            "role": role,
            "settings": settings,
            "links": build_dashboard_links(),
            "text": text,
            "parsed": parsed,
            "workers": workers,
            "recommended_worker": recommended_worker,
            "slot_suggestions": slot_suggestions,
            "error": "",
        }
    )


@router.post("/master/voice/confirm")
async def master_voice_confirm(request: Request):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role not in ("boss", "manager"):
        return RedirectResponse("/", status_code=302)

    company_id = get_user_company_id(username)
    settings = get_company_settings(company_id)

    form = await request.form()

    client_name = (form.get("client_name") or "").strip()[:200]
    phone = (form.get("phone") or "").strip()[:60]
    address = (form.get("address") or "").strip()[:300]
    task_date = (form.get("task_date") or "").strip()[:10]
    description = (form.get("description") or "").strip()[:5000]
    price = (form.get("price") or "").strip()[:40]
    selected_worker = (form.get("worker") or "").strip()[:120]
    source_text = (form.get("source_text") or "").strip()[:5000]

    if not client_name:
        return RedirectResponse(
            "/master/voice?error=client_required",
            status_code=302,
        )

    if task_date:
        try:
            datetime.strptime(task_date, "%Y-%m-%d")
        except ValueError:
            return RedirectResponse(
                "/master/voice?error=invalid_date",
                status_code=302,
            )

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

    task_id, client_id = create_task_from_draft(
        company_id,
        username,
        role,
        client_name,
        phone=phone,
        address=address,
        task_date=task_date,
        description=description,
        price=price,
        worker=selected_worker,
        source_kind="voice",
        details=source_text,
    )

    return RedirectResponse(f"/task/{task_id}", status_code=302)
