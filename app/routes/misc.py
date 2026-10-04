"""Misc routes: file serving, integrations, more menu, debug page, favicon."""

from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse, Response

from app.database import connect
from app.deps import (
    get_role,
    get_user,
    get_user_company_id,
    require_route_company_context,
)
from app.services.common import (
    build_dashboard_links,
    get_company_features,
    get_company_settings,
    role_label,
)
from app.services.plans import PLAN_DEFINITIONS
from app.templating import templates
from app.uploads import UPLOAD_DIR, storage_file_response

router = APIRouter()


def _main_attr(name):
    from app import main

    return getattr(main, name)


def get_company_context_diagnostics(*args, **kwargs):
    return _main_attr("get_company_context_diagnostics")(*args, **kwargs)


def can_access_task(*args, **kwargs):
    return _main_attr("can_access_task")(*args, **kwargs)


def build_admin_links(*args, **kwargs):
    return _main_attr("build_admin_links")(*args, **kwargs)

@router.get("/uploads/{filename:path}")
async def uploaded_file(request: Request, filename: str):
    username = get_user(request)

    if not username:
        return Response(status_code=404)

    safe_filename = Path(filename or "").name

    if not safe_filename or safe_filename != filename:
        return Response(status_code=404)

    role = get_role(username)

    conn = connect()
    c = conn.cursor()

    task = c.execute("""
    SELECT *
    FROM tasks
    WHERE photo=? OR after_photo=?
    """, (safe_filename, safe_filename)).fetchone()

    conn.close()

    if not task or not can_access_task(username, role, task):
        return Response(status_code=404)

    return storage_file_response(safe_filename, UPLOAD_DIR, request=request)



def build_debug_links():
    return {
        "clear_login_attempts": "/debug/login-attempts/clear",
    }


@router.get("/favicon.ico")
async def favicon():
    return FileResponse("app/static/favicon.svg", media_type="image/svg+xml")



@router.get("/debug", response_class=HTMLResponse)
async def debug_page(request: Request):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role != "superadmin":
        return RedirectResponse("/", status_code=302)

    conn = connect()
    c = conn.cursor()

    users_count = c.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    tasks_count = c.execute("SELECT COUNT(*) FROM tasks").fetchone()[0]
    active_tasks_count = c.execute("SELECT COUNT(*) FROM tasks WHERE archived=0").fetchone()[0]
    archived_tasks_count = c.execute("SELECT COUNT(*) FROM tasks WHERE archived=1").fetchone()[0]
    clients_count = c.execute("SELECT COUNT(*) FROM clients").fetchone()[0]
    catalog_count = c.execute("SELECT COUNT(*) FROM catalog_items").fetchone()[0]
    company_context_diagnostics = get_company_context_diagnostics(c)

    company_id, missing_company_response = require_route_company_context(username, role)

    if missing_company_response:
        conn.close()
        return missing_company_response

    settings = get_company_settings(company_id)
    plan_names = {
        plan_key: definition["label"]
        for plan_key, definition in PLAN_DEFINITIONS.items()
    }

    recent_users = c.execute("""
    SELECT username, role, last_seen
    FROM users
    ORDER BY last_seen DESC
    """).fetchall()

    login_events = c.execute("""
    SELECT *
    FROM login_events
    ORDER BY id DESC
    LIMIT 20
    """).fetchall()

    login_attempts = c.execute("""
    SELECT *
    FROM login_attempts
    ORDER BY id DESC
    LIMIT 20
    """).fetchall()

    conn.close()

    return templates.TemplateResponse(
        request,
        "debug.html",
        {
            "request": request,
            "username": username,
            "role": role,
            "users_count": users_count,
            "tasks_count": tasks_count,
            "active_tasks_count": active_tasks_count,
            "archived_tasks_count": archived_tasks_count,
            "clients_count": clients_count,
            "catalog_count": catalog_count,
            "company_context_diagnostics": company_context_diagnostics,
            "settings": settings,
            "plan_names": plan_names,
            "recent_users": recent_users,
            "login_events": login_events,
            "login_attempts": login_attempts,
            "links": build_debug_links(),
        }
    )




@router.get("/integrations/1c", response_class=HTMLResponse)
async def integration_1c_page(request: Request):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role not in ("boss", "superadmin"):
        return RedirectResponse("/", status_code=302)

    company_id, missing_company_response = require_route_company_context(username, role)

    if missing_company_response:
        return missing_company_response

    settings = get_company_settings(company_id)

    return templates.TemplateResponse(
        request,
        "integration_1c.html",
        {
            "request": request,
            "username": username,
            "role": role,
            "settings": settings
        }
    )


@router.get("/more", response_class=HTMLResponse)
async def more_page(request: Request):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)
    company_id = get_user_company_id(username)
    features = get_company_features(company_id)
    settings = get_company_settings(company_id)
    unread_notification_count = 0

    if company_id:
        conn = connect()
        c = conn.cursor()
        unread_notification_count = c.execute("""
        SELECT COUNT(*)
        FROM notifications
        WHERE company_id=?
          AND username=?
          AND is_read=0
        """, (company_id, username)).fetchone()[0]
        conn.close()

    return templates.TemplateResponse(
        request,
        "more.html",
        {
            "request": request,
            "username": username,
            "role": role,
            "features": features,
            "settings": settings,
            "unread_notification_count": unread_notification_count,
            "links": build_dashboard_links(),
        }
    )


@router.post("/debug/login-attempts/clear")
async def clear_login_attempts_admin(request: Request):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role != "superadmin":
        return RedirectResponse("/", status_code=302)

    conn = connect()
    c = conn.cursor()

    c.execute("DELETE FROM login_attempts")

    conn.commit()
    conn.close()

    return RedirectResponse("/debug?login_attempts_cleared=1", status_code=302)


@router.get("/admin/notes", response_class=HTMLResponse)
async def admin_notes_page(request: Request):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role != "superadmin":
        return RedirectResponse("/", status_code=302)

    return templates.TemplateResponse(
        request,
        "admin_notes.html",
        {
            "request": request,
            "username": username,
            "role": role,
            "links": build_admin_links(),
        }
    )

