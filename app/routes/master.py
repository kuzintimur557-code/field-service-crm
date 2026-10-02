"""Private master mode and first-launch onboarding routes."""

from datetime import datetime

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app.database import connect
from app.deps import get_role, get_user, get_user_company_id
from app.services.common import build_dashboard_links, get_company_settings
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
