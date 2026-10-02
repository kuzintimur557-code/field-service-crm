"""Notification center routes."""

import csv
import io
from datetime import datetime
from urllib.parse import urlencode

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response

from app.database import connect
from app.deps import get_role, get_user, get_user_company_id
from app.services.common import (
    build_dashboard_links,
    get_company_settings,
    require_feature,
)
from app.templating import templates

router = APIRouter()

def get_notifications_for_user(
    company_id: int,
    username: str,
    filter: str = "all",
    search: str = "",
    limit=100,
):
    selected_filter = filter if filter in ("all", "unread", "read") else "all"
    selected_search = str(search or "").strip()[:100]
    notifications_where = """
    WHERE company_id=?
      AND username=?
    """
    notification_params = [company_id, username]

    if selected_filter == "unread":
        notifications_where += "\n      AND is_read=0"
    elif selected_filter == "read":
        notifications_where += "\n      AND is_read=1"

    if selected_search:
        search_pattern = f"%{selected_search.lower()}%"
        notifications_where += """
      AND (
          LOWER(COALESCE(title, '')) LIKE ?
          OR LOWER(COALESCE(message, '')) LIKE ?
          OR LOWER(COALESCE(link, '')) LIKE ?
      )
        """
        notification_params.extend([search_pattern, search_pattern, search_pattern])

    conn = connect()
    c = conn.cursor()
    limit_clause = ""
    list_params = list(notification_params)

    if limit is not None:
        limit_clause = "LIMIT ?"
        list_params.append(limit)

    notifications = c.execute(f"""
    SELECT *
    FROM notifications
    {notifications_where}
    ORDER BY id DESC
    {limit_clause}
    """, list_params).fetchall()

    filtered_count = c.execute(f"""
    SELECT COUNT(*)
    FROM notifications
    {notifications_where}
    """, notification_params).fetchone()[0]

    unread_count = c.execute("""
    SELECT COUNT(*)
    FROM notifications
    WHERE company_id=?
      AND username=?
      AND is_read=0
    """, (company_id, username)).fetchone()[0]

    total_count = c.execute("""
    SELECT COUNT(*)
    FROM notifications
    WHERE company_id=?
      AND username=?
    """, (company_id, username)).fetchone()[0]
    read_count = max(total_count - unread_count, 0)

    conn.close()

    return {
        "notifications": notifications,
        "unread_count": unread_count,
        "total_count": total_count,
        "read_count": read_count,
        "filtered_count": filtered_count,
        "selected_filter": selected_filter,
        "selected_search": selected_search,
    }



@router.get("/notifications", response_class=HTMLResponse)
async def notifications_page(
    request: Request,
    filter: str = "all",
    search: str = ""
):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)
    company_id = get_user_company_id(username)
    disabled_response = require_feature(company_id, "notifications")

    if disabled_response:
        return disabled_response

    settings = get_company_settings(company_id)
    notification_data = get_notifications_for_user(
        company_id,
        username,
        filter=filter,
        search=search,
        limit=100,
    )

    return templates.TemplateResponse(
        request,
        "notifications.html",
        {
            "request": request,
            "username": username,
            "role": role,
            "notifications": notification_data["notifications"],
            "unread_count": notification_data["unread_count"],
            "total_count": notification_data["total_count"],
            "read_count": notification_data["read_count"],
            "filtered_count": notification_data["filtered_count"],
            "selected_filter": notification_data["selected_filter"],
            "selected_search": notification_data["selected_search"],
            "settings": settings
        }
    )


@router.get("/notifications/export")
async def notifications_export(
    request: Request,
    filter: str = "all",
    search: str = ""
):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    company_id = get_user_company_id(username)
    disabled_response = require_feature(company_id, "notifications")

    if disabled_response:
        return disabled_response

    notification_data = get_notifications_for_user(
        company_id,
        username,
        filter=filter,
        search=search,
        limit=None,
    )
    notifications = notification_data["notifications"]
    selected_filter = notification_data["selected_filter"]
    selected_search = notification_data["selected_search"]

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "Дата",
        "Статус",
        "Заголовок",
        "Сообщение",
        "Ссылка",
    ])

    for notification in notifications:
        writer.writerow([
            notification["created_at"] or "",
            "Прочитано" if notification["is_read"] else "Новое",
            notification["title"] or "",
            notification["message"] or "",
            notification["link"] or "",
        ])

    filename_parts = [
        selected_filter,
        "search" if selected_search else "all",
    ]
    filename = "notifications_" + "_".join(filename_parts) + ".csv"

    return Response(
        content="\ufeff" + output.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f"attachment; filename={filename}"
        }
    )


def build_notifications_redirect_url(filter_value="all", search_value=""):
    selected_filter = filter_value if filter_value in ("all", "unread", "read") else "all"
    selected_search = str(search_value or "").strip()[:100]
    redirect_params = {}

    if selected_filter != "all":
        redirect_params["filter"] = selected_filter

    if selected_search:
        redirect_params["search"] = selected_search

    redirect_url = "/notifications"

    if redirect_params:
        redirect_url += "?" + urlencode(redirect_params)

    return redirect_url


@router.post("/notifications/read-all")
async def mark_all_notifications_read(
    request: Request,
    filter: str = "all",
    search: str = ""
):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    company_id = get_user_company_id(username)
    disabled_response = require_feature(company_id, "notifications")
    selected_filter = filter if filter in ("all", "unread", "read") else "all"
    selected_search = str(search or "").strip()

    if disabled_response:
        return disabled_response

    conn = connect()
    c = conn.cursor()

    c.execute("""
    UPDATE notifications
    SET is_read=1
    WHERE company_id=?
      AND username=?
    """, (company_id, username))

    conn.commit()
    conn.close()

    return RedirectResponse(
        build_notifications_redirect_url(selected_filter, selected_search),
        status_code=302
    )


@router.post("/notifications/delete-read")
async def delete_read_notifications(
    request: Request,
    filter: str = "read",
    search: str = ""
):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    company_id = get_user_company_id(username)
    disabled_response = require_feature(company_id, "notifications")
    selected_filter = filter if filter in ("all", "unread", "read") else "read"
    selected_search = str(search or "").strip()

    if disabled_response:
        return disabled_response

    conn = connect()
    c = conn.cursor()

    c.execute("""
    DELETE FROM notifications
    WHERE company_id=?
      AND username=?
      AND is_read=1
    """, (company_id, username))

    conn.commit()
    conn.close()

    return RedirectResponse(
        build_notifications_redirect_url(selected_filter, selected_search),
        status_code=302
    )


@router.post("/notifications/{notification_id}/read")
async def mark_notification_read(
    request: Request,
    notification_id: int,
    filter: str = "all",
    search: str = ""
):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    company_id = get_user_company_id(username)
    disabled_response = require_feature(company_id, "notifications")

    if disabled_response:
        return disabled_response

    selected_filter = filter if filter in ("all", "unread", "read") else "all"
    selected_search = str(search or "").strip()

    conn = connect()
    c = conn.cursor()

    c.execute("""
    UPDATE notifications
    SET is_read=1
    WHERE id=?
      AND company_id=?
      AND username=?
    """, (notification_id, company_id, username))

    conn.commit()
    conn.close()

    return RedirectResponse(
        build_notifications_redirect_url(selected_filter, selected_search),
        status_code=302
    )


@router.get("/notifications/{notification_id}/open")
async def open_notification(request: Request, notification_id: int):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    company_id = get_user_company_id(username)
    disabled_response = require_feature(company_id, "notifications")

    if disabled_response:
        return disabled_response

    conn = connect()
    c = conn.cursor()

    notification = c.execute("""
    SELECT *
    FROM notifications
    WHERE id=?
      AND company_id=?
      AND username=?
    """, (notification_id, company_id, username)).fetchone()

    if not notification:
        conn.close()
        return RedirectResponse("/notifications", status_code=302)

    c.execute("""
    UPDATE notifications
    SET is_read=1
    WHERE id=?
      AND company_id=?
      AND username=?
    """, (notification_id, company_id, username))

    conn.commit()
    conn.close()

    link = (notification["link"] or "").strip()

    if not link or not link.startswith("/") or link.startswith("//"):
        link = "/notifications"

    return RedirectResponse(link, status_code=302)
