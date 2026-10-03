"""List pages: my tasks, today, overdue, SLA, workload, owner dashboard, reports, archive."""

import csv
import io
from datetime import datetime, timedelta

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response

from app.database import connect
from app.deps import (
    get_role,
    get_user,
    get_user_company_id,
    require_route_company_context,
    update_last_seen,
)
from app.services.common import (
    build_dashboard_links,
    can_access_task,
    create_notification,
    format_task_workers,
    get_company_features,
    get_company_settings,
    get_overdue_days,
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
from app.templating import templates

router = APIRouter()


def _main_attr(name):
    from app import main

    return getattr(main, name)


def run_automation_event(*args, **kwargs):
    return _main_attr("run_automation_event")(*args, **kwargs)


def send_message(*args, **kwargs):
    return _main_attr("send_message")(*args, **kwargs)


def send_message_to_chat(*args, **kwargs):
    return _main_attr("send_message_to_chat")(*args, **kwargs)

@router.get("/workload", response_class=HTMLResponse)
async def workload_page(request: Request):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role not in ("boss", "manager"):
        return RedirectResponse("/", status_code=302)

    company_id = get_user_company_id(username)
    disabled_response = require_feature(company_id, "workload")

    if disabled_response:
        return disabled_response

    settings = get_company_settings(company_id)

    conn = connect()
    c = conn.cursor()

    workers = c.execute("""
    SELECT username, full_name, position, last_seen
    FROM users
    WHERE role='worker'
      AND company_id=?
      AND COALESCE(is_active, 1)=1
    ORDER BY username
    """, (company_id,)).fetchall()

    stats = []

    for worker in workers:
        name = worker["username"]

        total = c.execute(f"""
        SELECT COUNT(*)
        FROM tasks
        WHERE archived=0
          AND company_id=?
          AND ({worker_task_condition()})
        """, [company_id] + worker_task_params(name)).fetchone()[0]

        active = c.execute(f"""
        SELECT COUNT(*)
        FROM tasks
        WHERE archived=0
          AND company_id=?
          AND status='В работе'
          AND ({worker_task_condition()})
        """, [company_id] + worker_task_params(name)).fetchone()[0]

        new = c.execute(f"""
        SELECT COUNT(*)
        FROM tasks
        WHERE archived=0
          AND company_id=?
          AND status='Новая'
          AND ({worker_task_condition()})
        """, [company_id] + worker_task_params(name)).fetchone()[0]

        done = c.execute(f"""
        SELECT COUNT(*)
        FROM tasks
        WHERE archived=0
          AND company_id=?
          AND status='Завершено'
          AND ({worker_task_condition()})
        """, [company_id] + worker_task_params(name)).fetchone()[0]

        if active >= 3:
            load_status = "Перегружен"
        elif active == 0 and new == 0:
            load_status = "Свободен"
        else:
            load_status = "В норме"

        stats.append({
            "worker": worker,
            "total": total,
            "active": active,
            "new": new,
            "done": done,
            "load_status": load_status
        })

    conn.close()

    return templates.TemplateResponse(
        request,
        "workload.html",
        {
            "request": request,
            "username": username,
            "role": role,
            "stats": stats,
            "settings": settings
        }
    )


@router.post("/sla/reminders")
async def create_sla_reminders(request: Request):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role not in ("boss", "manager"):
        return RedirectResponse("/", status_code=302)

    company_id = get_user_company_id(username)
    disabled_response = require_feature(company_id, "sla")

    if disabled_response:
        return disabled_response

    now_value = datetime.now().strftime("%Y-%m-%dT%H:%M")
    soon_value = (datetime.now() + timedelta(hours=24)).strftime("%Y-%m-%dT%H:%M")

    conn = connect()
    c = conn.cursor()

    tasks = c.execute("""
    SELECT *
    FROM tasks
    WHERE archived=0
      AND company_id=?
      AND status!='Завершено'
      AND deadline_at IS NOT NULL
      AND deadline_at!=''
      AND deadline_at < ?
    ORDER BY deadline_at ASC
    """, (company_id, now_value)).fetchall()

    users = c.execute("""
    SELECT username
    FROM users
    WHERE company_id=?
      AND role IN ('boss', 'manager')
    """, (company_id,)).fetchall()

    created_count = 0
    automation_tasks = []

    for task in tasks:
        task_created_count = 0

        for user in users:
            existing_notification = c.execute("""
            SELECT id
            FROM notifications
            WHERE company_id=?
              AND username=?
              AND title=?
              AND link=?
              AND is_read=0
            """, (
                company_id,
                user["username"],
                "🔴 Просрочен SLA",
                f"/task/{task['id']}"
            )).fetchone()

            if existing_notification:
                continue

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
                user["username"],
                "🔴 Просрочен SLA",
                f"Заявка #{task['id']} просрочила срок SLA",
                f"/task/{task['id']}",
                datetime.now().strftime("%Y-%m-%d %H:%M")
            ))
            created_count += 1
            task_created_count += 1

        if task_created_count:
            automation_tasks.append(task)

    conn.commit()
    conn.close()

    for task in automation_tasks:
        run_automation_event(
            company_id,
            "sla_overdue",
            "task",
            task["id"],
            f"Заявка #{task['id']} просрочила срок SLA",
            f"/task/{task['id']}"
        )

    return RedirectResponse(f"/sla?reminders=1&created={created_count}&filter=overdue", status_code=302)


@router.post("/sla/escalations")
async def create_sla_escalations(request: Request):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role not in ("boss", "manager"):
        return RedirectResponse("/", status_code=302)

    company_id = get_user_company_id(username)

    disabled_response = require_feature(company_id, "sla")

    if disabled_response:
        return disabled_response


    escalation_cutoff = (datetime.now() - timedelta(hours=24)).strftime("%Y-%m-%dT%H:%M")

    conn = connect()
    c = conn.cursor()

    tasks = c.execute("""
    SELECT *
    FROM tasks
    WHERE archived=0
      AND company_id=?
      AND status!='Завершено'
      AND deadline_at IS NOT NULL
      AND deadline_at!=''
      AND deadline_at < ?
    ORDER BY deadline_at ASC
    """, (company_id, escalation_cutoff)).fetchall()

    bosses = c.execute("""
    SELECT username
    FROM users
    WHERE company_id=?
      AND role='boss'
    """, (company_id,)).fetchall()

    created_count = 0

    for task in tasks:
        for boss in bosses:
            existing_notification = c.execute("""
            SELECT id
            FROM notifications
            WHERE company_id=?
              AND username=?
              AND title=?
              AND link=?
              AND is_read=0
            """, (
                company_id,
                boss["username"],
                "🚨 SLA эскалация",
                f"/task/{task['id']}"
            )).fetchone()

            if existing_notification:
                continue

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
                boss["username"],
                "🚨 SLA эскалация",
                f"Заявка #{task['id']} просрочила SLA больше чем на 24 часа",
                f"/task/{task['id']}",
                datetime.now().strftime("%Y-%m-%d %H:%M")
            ))
            created_count += 1

    conn.commit()
    conn.close()

    return RedirectResponse(f"/sla?escalations=1&created={created_count}&filter=overdue", status_code=302)


@router.get("/sla", response_class=HTMLResponse)
async def sla_page(request: Request, filter: str = "", worker: str = ""):

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
    disabled_response = require_feature(company_id, "sla")

    if disabled_response:
        return disabled_response

    now_value = datetime.now().strftime("%Y-%m-%dT%H:%M")
    soon_value = (datetime.now() + timedelta(hours=24)).strftime("%Y-%m-%dT%H:%M")

    conn = connect()
    c = conn.cursor()

    tasks = c.execute("""
    SELECT *
    FROM tasks
    WHERE archived=0
      AND company_id=?
      AND deadline_at IS NOT NULL
      AND deadline_at!=''
    ORDER BY deadline_at ASC
    """, (company_id,)).fetchall()

    workers = c.execute("""
    SELECT username
    FROM users
    WHERE role='worker'
      AND company_id=?
    ORDER BY username
    """, (company_id,)).fetchall()
    worker_names = [w["username"] for w in workers]

    all_sla_tasks = list(tasks)
    sla_overdue_count = len([
        t for t in all_sla_tasks
        if t["status"] != "Завершено"
        and t["deadline_at"] < now_value
    ])
    sla_due_soon_count = len([
        t for t in all_sla_tasks
        if t["status"] != "Завершено"
        and now_value <= t["deadline_at"] <= soon_value
    ])
    sla_done_count = len([
        t for t in all_sla_tasks
        if t["status"] == "Завершено"
    ])
    sla_active_count = len([
        t for t in all_sla_tasks
        if t["status"] != "Завершено"
        and t["deadline_at"] >= now_value
    ])
    sla_stats = {
        "total": len(all_sla_tasks),
        "overdue": sla_overdue_count,
        "soon": sla_due_soon_count,
        "active": sla_active_count,
        "done": sla_done_count
    }
    worker_sla_stats = []

    for worker_row in workers:
        worker_name = worker_row["username"]
        worker_tasks = [
            t for t in all_sla_tasks
            if can_access_task(worker_name, "worker", t)
        ]
        worker_sla_stats.append({
            "username": worker_name,
            "total": len(worker_tasks),
            "overdue": len([
                t for t in worker_tasks
                if t["status"] != "Завершено"
                and t["deadline_at"] < now_value
            ]),
            "soon": len([
                t for t in worker_tasks
                if t["status"] != "Завершено"
                and now_value <= t["deadline_at"] <= soon_value
            ]),
            "done": len([
                t for t in worker_tasks
                if t["status"] == "Завершено"
            ])
        })

    if filter == "overdue":
        tasks = [
            t for t in tasks
            if t["status"] != "Завершено"
            and t["deadline_at"] < now_value
        ]

    elif filter == "active":
        tasks = [
            t for t in tasks
            if t["status"] != "Завершено"
            and t["deadline_at"] >= now_value
        ]

    elif filter == "soon":
        tasks = [
            t for t in tasks
            if t["status"] != "Завершено"
            and now_value <= t["deadline_at"] <= soon_value
        ]

    elif filter == "done":
        tasks = [
            t for t in tasks
            if t["status"] == "Завершено"
        ]

    if worker and worker in worker_names:
        tasks = [
            t for t in tasks
            if can_access_task(worker, "worker", t)
        ]
    elif worker:
        tasks = []

    conn.close()

    return templates.TemplateResponse(
        request,
        "sla.html",
        {
            "request": request,
            "username": username,
            "role": role,
            "tasks": tasks,
            "sla_stats": sla_stats,
            "worker_sla_stats": worker_sla_stats,
            "workers": workers,
            "now_value": now_value,
            "soon_value": soon_value,
            "selected_filter": filter,
            "selected_worker": worker,
            "settings": settings
        }
    )

@router.get("/today", response_class=HTMLResponse)
async def today_page(request: Request):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role not in ("boss", "manager"):
        return RedirectResponse("/", status_code=302)

    company_id = get_user_company_id(username)
    settings = get_company_settings(company_id)
    today = datetime.now().strftime("%Y-%m-%d")

    conn = connect()
    c = conn.cursor()

    tasks = c.execute("""
    SELECT *
    FROM tasks
    WHERE archived=0
      AND company_id=?
      AND task_date LIKE ?
    ORDER BY task_date ASC
    """, (company_id, f"{today}%")).fetchall()

    conn.close()

    return templates.TemplateResponse(
        request,
        "today.html",
        {
            "request": request,
            "username": username,
            "role": role,
            "tasks": tasks,
            "today": today,
            "settings": settings
        }
    )


@router.get("/overdue", response_class=HTMLResponse)
async def overdue_page(request: Request):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role not in ("boss", "manager"):
        return RedirectResponse("/", status_code=302)

    company_id = get_user_company_id(username)
    settings = get_company_settings(company_id)
    today_date = datetime.now().date()
    today = today_date.strftime("%Y-%m-%d")

    conn = connect()
    c = conn.cursor()

    tasks = c.execute("""
    SELECT *
    FROM tasks
    WHERE archived=0
      AND company_id=?
      AND status NOT IN ('Завершено', 'Отменено')
      AND task_date IS NOT NULL
      AND task_date!=''
      AND task_date < ?
    ORDER BY task_date ASC
    """, (company_id, today)).fetchall()

    entries = []

    for task in tasks:
        overdue_days = get_overdue_days(task["task_date"], today_date)
        entries.append({
            "task": task,
            "overdue_days": overdue_days,
            "sla_status": "Нарушен SLA" if overdue_days > 1 else "Просрочено"
        })

    conn.close()

    return templates.TemplateResponse(
        request,
        "overdue.html",
        {
            "request": request,
            "username": username,
            "role": role,
            "tasks": tasks,
            "entries": entries,
            "settings": settings
        }
    )


@router.post("/overdue/reminders")
async def create_overdue_reminders(request: Request):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role not in ("boss", "manager"):
        return RedirectResponse("/", status_code=302)

    company_id = get_user_company_id(username)
    today = datetime.now().strftime("%Y-%m-%d")

    conn = connect()
    c = conn.cursor()

    tasks = c.execute("""
    SELECT *
    FROM tasks
    WHERE archived=0
      AND company_id=?
      AND status NOT IN ('Завершено', 'Отменено')
      AND task_date IS NOT NULL
      AND task_date!=''
      AND task_date < ?
    ORDER BY task_date ASC
    """, (company_id, today)).fetchall()

    users = c.execute("""
    SELECT username
    FROM users
    WHERE company_id=?
      AND role IN ('boss', 'manager')
    """, (company_id,)).fetchall()

    created_count = 0
    automation_tasks = []

    for task in tasks:
        task_created_count = 0

        for user in users:
            existing_notification = c.execute("""
            SELECT id
            FROM notifications
            WHERE company_id=?
              AND username=?
              AND title=?
              AND link=?
              AND is_read=0
            """, (
                company_id,
                user["username"],
                "🟠 Просрочена задача",
                f"/task/{task['id']}"
            )).fetchone()

            if existing_notification:
                continue

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
                user["username"],
                "🟠 Просрочена задача",
                f"Задача #{task['id']} просрочена по дате",
                f"/task/{task['id']}",
                datetime.now().strftime("%Y-%m-%d %H:%M")
            ))
            created_count += 1
            task_created_count += 1

        if task_created_count:
            automation_tasks.append(task)

    conn.commit()
    conn.close()

    for task in automation_tasks:
        run_automation_event(
            company_id,
            "overdue_task",
            "task",
            task["id"],
            f"Задача #{task['id']} просрочена по дате",
            f"/task/{task['id']}"
        )

    return RedirectResponse(f"/overdue?reminders=1&created={created_count}", status_code=302)

@router.get("/sla/analytics/export")
async def sla_analytics_export(request: Request):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role not in ("boss", "manager"):
        return RedirectResponse("/", status_code=302)

    company_id = get_user_company_id(username)
    disabled_response = require_feature(company_id, "sla")

    if disabled_response:
        return disabled_response

    conn = connect()
    c = conn.cursor()

    rows = c.execute("""
    SELECT
        id,
        client,
        workers,
        task_date,
        status
    FROM tasks
    WHERE company_id=?
    ORDER BY task_date DESC
    """, (company_id,)).fetchall()

    conn.close()

    today = datetime.now().date()

    output = io.StringIO()
    writer = csv.writer(output)

    writer.writerow([
        "Номер заявки",
        "Клиент",
        "Исполнители",
        "Дата заявки",
        "Статус",
        "Просрочено",
        "Дней просрочки"
    ])

    for row in rows:
        is_overdue = False
        age_days = 0

        try:
            task_date_value = datetime.strptime(row["task_date"], "%Y-%m-%d").date()
            age_days = (today - task_date_value).days
            is_overdue = row["status"] != "done" and task_date_value < today
        except Exception:
            pass

        writer.writerow([
            row["id"],
            row["client"] or "Без клиента",
            row["workers"] or "",
            row["task_date"] or "",
            row["status"] or "",
            "да" if is_overdue else "нет",
            age_days
        ])

    content = output.getvalue()
    output.close()

    return Response(
        content,
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": "attachment; filename=sla_analytics.csv"
        }
    )



@router.get("/sla/analytics", response_class=HTMLResponse)
async def sla_analytics_page(request: Request):

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
    disabled_response = require_feature(company_id, "sla")

    if disabled_response:
        return disabled_response

    conn = connect()
    c = conn.cursor()

    total_tasks = c.execute("""
    SELECT COUNT(*)
    FROM tasks
    WHERE company_id=?
    """, (company_id,)).fetchone()[0]

    completed_tasks = c.execute("""
    SELECT COUNT(*)
    FROM tasks
    WHERE company_id=?
      AND status='done'
    """, (company_id,)).fetchone()[0]

    open_tasks = c.execute("""
    SELECT COUNT(*)
    FROM tasks
    WHERE company_id=?
      AND status!='done'
    """, (company_id,)).fetchone()[0]

    overdue_tasks = c.execute("""
    SELECT COUNT(*)
    FROM tasks
    WHERE company_id=?
      AND status!='done'
      AND task_date < date('now')
    """, (company_id,)).fetchone()[0]

    clients = c.execute("""
    SELECT DISTINCT client
    FROM tasks
    WHERE company_id=?
      AND client IS NOT NULL
      AND client!=''
    ORDER BY client
    """, (company_id,)).fetchall()

    client_rows = []

    for client in clients:
        client_name = client["client"]

        total_client_tasks = c.execute("""
        SELECT COUNT(*)
        FROM tasks
        WHERE company_id=?
          AND client=?
        """, (company_id, client_name)).fetchone()[0]

        completed_client_tasks = c.execute("""
        SELECT COUNT(*)
        FROM tasks
        WHERE company_id=?
          AND client=?
          AND status='done'
        """, (company_id, client_name)).fetchone()[0]

        open_client_tasks = c.execute("""
        SELECT COUNT(*)
        FROM tasks
        WHERE company_id=?
          AND client=?
          AND status!='done'
        """, (company_id, client_name)).fetchone()[0]

        overdue_client_tasks = c.execute("""
        SELECT COUNT(*)
        FROM tasks
        WHERE company_id=?
          AND client=?
          AND status!='done'
          AND task_date < date('now')
        """, (company_id, client_name)).fetchone()[0]

        client_overdue_rate = round(
            (overdue_client_tasks / total_client_tasks * 100),
            1
        ) if total_client_tasks else 0

        client_rows.append({
            "client": client_name,
            "total_tasks": total_client_tasks,
            "completed_tasks": completed_client_tasks,
            "open_tasks": open_client_tasks,
            "overdue_tasks": overdue_client_tasks,
            "overdue_rate": client_overdue_rate,
            "sla_score": round(100 - client_overdue_rate, 1)
        })

    sla_client_rows = sorted(
        client_rows,
        key=lambda row: row["overdue_tasks"],
        reverse=True
    )[:20]

    overdue_task_rows = c.execute("""
    SELECT
        id,
        client,
        workers,
        task_date,
        status
    FROM tasks
    WHERE company_id=?
      AND status!='done'
      AND task_date < date('now')
    ORDER BY task_date ASC
    LIMIT 30
    """, (company_id,)).fetchall()

    today = datetime.now().date()
    sla_overdue_tasks = []

    for row in overdue_task_rows:
        try:
            task_date_value = datetime.strptime(row["task_date"], "%Y-%m-%d").date()
            age_days = (today - task_date_value).days
        except Exception:
            age_days = 0

        sla_overdue_tasks.append({
            "id": row["id"],
            "client": row["client"] or "Не указан",
            "workers": row["workers"] or "",
            "task_date": row["task_date"],
            "status": row["status"],
            "age_days": age_days
        })


    workers = c.execute("""
    SELECT id, username
    FROM users
    WHERE company_id=?
      AND role='worker'
    ORDER BY username
    """, (company_id,)).fetchall()

    worker_rows = []

    for worker in workers:
        username_value = worker["username"]

        total_worker_tasks = c.execute("""
        SELECT COUNT(*)
        FROM tasks
        WHERE company_id=?
          AND workers LIKE ?
        """, (company_id, f"%{username_value}%")).fetchone()[0]

        completed_worker_tasks = c.execute("""
        SELECT COUNT(*)
        FROM tasks
        WHERE company_id=?
          AND workers LIKE ?
          AND status='done'
        """, (company_id, f"%{username_value}%")).fetchone()[0]

        open_worker_tasks = c.execute("""
        SELECT COUNT(*)
        FROM tasks
        WHERE company_id=?
          AND workers LIKE ?
          AND status!='done'
        """, (company_id, f"%{username_value}%")).fetchone()[0]

        overdue_worker_tasks = c.execute("""
        SELECT COUNT(*)
        FROM tasks
        WHERE company_id=?
          AND workers LIKE ?
          AND status!='done'
          AND task_date < date('now')
        """, (company_id, f"%{username_value}%")).fetchone()[0]

        worker_overdue_rate = round(
            (overdue_worker_tasks / total_worker_tasks * 100),
            1
        ) if total_worker_tasks else 0

        worker_rows.append({
            "worker": username_value,
            "total_tasks": total_worker_tasks,
            "completed_tasks": completed_worker_tasks,
            "open_tasks": open_worker_tasks,
            "overdue_tasks": overdue_worker_tasks,
            "overdue_rate": worker_overdue_rate,
            "sla_score": round(100 - worker_overdue_rate, 1)
        })

    sla_worker_rows = sorted(
        worker_rows,
        key=lambda row: row["overdue_tasks"],
        reverse=True
    )

    monthly_task_rows = c.execute("""
    SELECT
        substr(task_date, 1, 7) as month,
        COUNT(*) as total_tasks,
        SUM(CASE WHEN status='done' THEN 1 ELSE 0 END) as completed_tasks,
        SUM(CASE WHEN status!='done' AND task_date < date('now') THEN 1 ELSE 0 END) as overdue_tasks
    FROM tasks
    WHERE company_id=?
      AND task_date IS NOT NULL
      AND task_date!=''
    GROUP BY substr(task_date, 1, 7)
    ORDER BY month DESC
    LIMIT 12
    """, (company_id,)).fetchall()

    sla_monthly_rows = []

    for row in monthly_task_rows:
        monthly_total = int(row["total_tasks"] or 0)
        monthly_overdue = int(row["overdue_tasks"] or 0)

        monthly_overdue_rate = round(
            (monthly_overdue / monthly_total * 100),
            1
        ) if monthly_total else 0

        sla_monthly_rows.append({
            "month": row["month"],
            "total_tasks": monthly_total,
            "completed_tasks": int(row["completed_tasks"] or 0),
            "overdue_tasks": monthly_overdue,
            "overdue_rate": monthly_overdue_rate,
            "sla_score": round(100 - monthly_overdue_rate, 1)
        })

    completed_rows = c.execute("""
    SELECT
        created_at,
        task_date
    FROM tasks
    WHERE company_id=?
      AND status='done'
      AND created_at IS NOT NULL
      AND task_date IS NOT NULL
      AND task_date!=''
    """, (company_id,)).fetchall()

    completion_days = []

    for row in completed_rows:
        try:
            created_date = datetime.strptime(
                row["created_at"][:10],
                "%Y-%m-%d"
            ).date()

            completed_date = datetime.strptime(
                row["task_date"][:10],
                "%Y-%m-%d"
            ).date()

            days = (completed_date - created_date).days

            if days >= 0:
                completion_days.append(days)

        except Exception:
            pass

    average_completion_days = round(
        sum(completion_days) / len(completion_days),
        1
    ) if completion_days else 0

    fastest_completion_days = min(completion_days) if completion_days else 0
    slowest_completion_days = max(completion_days) if completion_days else 0

    conn.close()

    overdue_rate = round(
        (overdue_tasks / total_tasks * 100),
        1
    ) if total_tasks else 0

    overall_sla_score = round(100 - overdue_rate, 1)

    return templates.TemplateResponse(
        request,
        "sla_analytics.html",
        {
            "request": request,
            "username": username,
            "role": role,
            "total_tasks": total_tasks,
            "completed_tasks": completed_tasks,
            "open_tasks": open_tasks,
            "overdue_tasks": overdue_tasks,
            "overdue_rate": overdue_rate,
            "overall_sla_score": overall_sla_score,
            "average_completion_days": average_completion_days,
            "fastest_completion_days": fastest_completion_days,
            "slowest_completion_days": slowest_completion_days,
            "sla_worker_rows": sla_worker_rows,
            "sla_client_rows": sla_client_rows,
            "sla_overdue_tasks": sla_overdue_tasks,
            "sla_monthly_rows": sla_monthly_rows,
            "settings": settings
        }
    )


@router.get("/owner/dashboard/export")
async def owner_dashboard_export(request: Request):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role != "boss":
        return RedirectResponse("/", status_code=302)

    company_id = get_user_company_id(username)

    disabled_response = require_feature(company_id, "analytics")

    if disabled_response:
        return disabled_response



    conn = connect()
    c = conn.cursor()

    rows = c.execute("""
    SELECT
        month,
        SUM(price) as revenue,
        SUM(payroll_total) as payroll,
        SUM(profit) as profit,
        COUNT(task_id) as jobs_count,
        AVG(price) as average_job_value
    FROM finance_summary
    WHERE company_id=?
    GROUP BY month
    ORDER BY month DESC
    """, (company_id,)).fetchall()

    conn.close()

    output = io.StringIO()
    writer = csv.writer(output)

    writer.writerow([
        "Месяц",
        "Выручка",
        "Зарплаты",
        "Прибыль",
        "Чистая прибыль",
        "Количество заявок",
        "Средний чек"
    ])

    for row in rows:
        revenue = float(row["revenue"] or 0)
        payroll = float(row["payroll"] or 0)
        profit = float(row["profit"] or 0)

        writer.writerow([
            row["month"],
            round(revenue, 2),
            round(payroll, 2),
            round(profit, 2),
            round(profit - payroll, 2),
            int(row["jobs_count"] or 0),
            round(float(row["average_job_value"] or 0), 2)
        ])

    content = output.getvalue()
    output.close()

    return Response(
        content,
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": "attachment; filename=owner_dashboard.csv"
        }
    )



@router.get("/owner/dashboard", response_class=HTMLResponse)
async def owner_dashboard_page(request: Request, month: str = ""):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role != "boss":
        return RedirectResponse("/", status_code=302)

    company_id = get_user_company_id(username)
    disabled_response = require_feature(company_id, "analytics")

    if disabled_response:
        return disabled_response

    settings = get_company_settings(company_id)

    if not month:
        month = datetime.now().strftime("%Y-%m")

    try:
        owner_selected_month_date = datetime.strptime(month + "-01", "%Y-%m-%d")
    except ValueError:
        month = datetime.now().strftime("%Y-%m")
        owner_selected_month_date = datetime.strptime(month + "-01", "%Y-%m-%d")

    conn = connect()
    c = conn.cursor()

    total_clients = c.execute("""
    SELECT COUNT(*)
    FROM clients
    WHERE company_id=?
    """, (company_id,)).fetchone()[0]

    total_workers = c.execute("""
    SELECT COUNT(*)
    FROM users
    WHERE company_id=?
      AND role='worker'
    """, (company_id,)).fetchone()[0]

    total_tasks = c.execute("""
    SELECT COUNT(*)
    FROM tasks
    WHERE company_id=?
    """, (company_id,)).fetchone()[0]

    total_completed_tasks = c.execute("""
    SELECT COUNT(*)
    FROM tasks
    WHERE company_id=?
      AND status='done'
    """, (company_id,)).fetchone()[0]

    total_revenue = c.execute("""
    SELECT COALESCE(SUM(price), 0)
    FROM finance_summary
    WHERE company_id=?
    """, (company_id,)).fetchone()[0]

    total_profit = c.execute("""
    SELECT COALESCE(SUM(profit), 0)
    FROM finance_summary
    WHERE company_id=?
    """, (company_id,)).fetchone()[0]

    total_payroll = c.execute("""
    SELECT COALESCE(SUM(payroll_total), 0)
    FROM finance_summary
    WHERE company_id=?
    """, (company_id,)).fetchone()[0]

    unpaid_total = c.execute("""
    SELECT COALESCE(SUM(price), 0)
    FROM tasks
    WHERE company_id=?
      AND payment_status!='paid'
    """, (company_id,)).fetchone()[0]

    average_job_value = c.execute("""
    SELECT COALESCE(AVG(price), 0)
    FROM tasks
    WHERE company_id=?
    """, (company_id,)).fetchone()[0]

    unpaid_tasks = c.execute("""
    SELECT
        id,
        client,
        task_date,
        price
    FROM tasks
    WHERE company_id=?
      AND payment_status!='paid'
      AND CAST(REPLACE(COALESCE(price, '0'), ',', '.') AS REAL) > 0
    ORDER BY task_date ASC
    LIMIT 20
    """, (company_id,)).fetchall()

    unpaid_aging_summary = {
        "0_7": 0,
        "8_30": 0,
        "31_plus": 0
    }

    unpaid_risk_tasks = []

    today = datetime.now().date()

    for row in unpaid_tasks:
        unpaid_amount = float(row["price"] or 0)

        try:
            task_date = datetime.strptime(row["task_date"], "%Y-%m-%d").date()
            age_days = (today - task_date).days
        except Exception:
            age_days = 0

        if age_days <= 7:
            unpaid_aging_summary["0_7"] += unpaid_amount
        elif age_days <= 30:
            unpaid_aging_summary["8_30"] += unpaid_amount
        else:
            unpaid_aging_summary["31_plus"] += unpaid_amount

        unpaid_risk_tasks.append({
            "id": row["id"],
            "client_name": row["client"] or "Не указан",
            "task_date": row["task_date"],
            "unpaid_amount": round(unpaid_amount, 1),
            "age_days": age_days
        })

    unpaid_aging_summary = {
        "0_7": round(unpaid_aging_summary["0_7"], 1),
        "8_30": round(unpaid_aging_summary["8_30"], 1),
        "31_plus": round(unpaid_aging_summary["31_plus"], 1)
    }

    repeat_clients_summary = c.execute("""
    SELECT
        COUNT(*) as repeat_clients_count,
        COALESCE(SUM(revenue), 0) as repeat_clients_revenue
    FROM (
        SELECT
            client_name,
            COUNT(task_id) as jobs_count,
            SUM(price) as revenue
        FROM finance_summary
        WHERE company_id=?
        GROUP BY client_name
        HAVING COUNT(task_id) > 1
    )
    """, (company_id,)).fetchone()

    top_repeat_clients = c.execute("""
    SELECT
        client_name,
        COUNT(task_id) as jobs_count,
        SUM(price) as revenue,
        SUM(profit) as profit,
        SUM(payroll_total) as payroll
    FROM finance_summary
    WHERE company_id=?
    GROUP BY client_name
    HAVING COUNT(task_id) > 1
    ORDER BY revenue DESC
    LIMIT 10
    """, (company_id,)).fetchall()

    top_owner_clients = c.execute("""
    SELECT
        client_name,
        SUM(price) as revenue,
        SUM(profit) as profit,
        SUM(payroll_total) as payroll,
        COUNT(task_id) as jobs_count
    FROM finance_summary
    WHERE company_id=?
    GROUP BY client_name
    ORDER BY profit DESC
    LIMIT 10
    """, (company_id,)).fetchall()

    top_owner_workers = c.execute("""
    SELECT
        users.username as worker_name,
        SUM(payroll_payouts.amount) as total_paid,
        COUNT(payroll_payouts.id) as payouts_count
    FROM payroll_payouts
    JOIN users ON users.id = payroll_payouts.worker_id
    WHERE payroll_payouts.company_id=?
      AND payroll_payouts.status='paid'
    GROUP BY payroll_payouts.worker_id, users.username
    ORDER BY total_paid DESC
    LIMIT 10
    """, (company_id,)).fetchall()

    low_margin_clients = c.execute("""
    SELECT
        client_name,
        SUM(price) as revenue,
        SUM(profit) as profit,
        SUM(payroll_total) as payroll,
        COUNT(task_id) as jobs_count
    FROM finance_summary
    WHERE company_id=?
    GROUP BY client_name
    HAVING SUM(price) > 0
       AND ((SUM(profit) - SUM(payroll_total)) / SUM(price) * 100) < 15
    ORDER BY ((SUM(profit) - SUM(payroll_total)) / SUM(price) * 100) ASC
    LIMIT 10
    """, (company_id,)).fetchall()

    negative_months = c.execute("""
    SELECT
        month,
        SUM(price) as revenue,
        SUM(profit) as profit,
        SUM(payroll_total) as payroll
    FROM finance_summary
    WHERE company_id=?
    GROUP BY month
    HAVING (SUM(profit) - SUM(payroll_total)) < 0
    ORDER BY month DESC
    LIMIT 10
    """, (company_id,)).fetchall()

    owner_monthly_metrics = c.execute("""
    SELECT
        month,
        SUM(price) as revenue,
        SUM(payroll_total) as payroll,
        SUM(profit) as profit,
        COUNT(task_id) as jobs_count,
        AVG(price) as average_job_value
    FROM finance_summary
    WHERE company_id=?
    GROUP BY month
    ORDER BY month DESC
    LIMIT 12
    """, (company_id,)).fetchall()

    total_revenue = round(float(total_revenue or 0), 1)
    total_profit = round(float(total_profit or 0), 1)
    total_payroll = round(float(total_payroll or 0), 1)
    unpaid_total = round(float(unpaid_total or 0), 1)
    average_job_value = round(float(average_job_value or 0), 1)

    net_profit = round(total_profit - total_payroll, 1)

    payroll_ratio = round((total_payroll / total_revenue * 100), 1) if total_revenue else 0
    profit_margin = round((net_profit / total_revenue * 100), 1) if total_revenue else 0
    completion_rate = round((total_completed_tasks / total_tasks * 100), 1) if total_tasks else 0
    unpaid_ratio = round((unpaid_total / total_revenue * 100), 1) if total_revenue else 0

    repeat_clients_count = int(repeat_clients_summary["repeat_clients_count"] or 0)
    repeat_clients_revenue = round(float(repeat_clients_summary["repeat_clients_revenue"] or 0), 1)

    top_repeat_clients = [
        {
            "client_name": row["client_name"] or "Не указан",
            "jobs_count": int(row["jobs_count"] or 0),
            "revenue": round(float(row["revenue"] or 0), 1),
            "profit": round(float(row["profit"] or 0), 1),
            "payroll": round(float(row["payroll"] or 0), 1),
            "net_profit": round(float(row["profit"] or 0) - float(row["payroll"] or 0), 1)
        }
        for row in top_repeat_clients
    ]

    top_owner_clients = [
        {
            "client_name": row["client_name"] or "Не указан",
            "revenue": round(float(row["revenue"] or 0), 1),
            "profit": round(float(row["profit"] or 0), 1),
            "payroll": round(float(row["payroll"] or 0), 1),
            "net_profit": round(float(row["profit"] or 0) - float(row["payroll"] or 0), 1),
            "jobs_count": int(row["jobs_count"] or 0)
        }
        for row in top_owner_clients
    ]

    top_owner_workers = [
        {
            "worker_name": row["worker_name"],
            "total_paid": round(float(row["total_paid"] or 0), 1),
            "payouts_count": int(row["payouts_count"] or 0)
        }
        for row in top_owner_workers
    ]

    low_margin_clients = [
        {
            "client_name": row["client_name"] or "Не указан",
            "revenue": round(float(row["revenue"] or 0), 1),
            "profit": round(float(row["profit"] or 0), 1),
            "payroll": round(float(row["payroll"] or 0), 1),
            "net_profit": round(float(row["profit"] or 0) - float(row["payroll"] or 0), 1),
            "margin": round(((float(row["profit"] or 0) - float(row["payroll"] or 0)) / float(row["revenue"] or 1) * 100), 1),
            "jobs_count": int(row["jobs_count"] or 0)
        }
        for row in low_margin_clients
    ]

    negative_months = [
        {
            "month": row["month"],
            "revenue": round(float(row["revenue"] or 0), 1),
            "profit": round(float(row["profit"] or 0), 1),
            "payroll": round(float(row["payroll"] or 0), 1),
            "net_profit": round(float(row["profit"] or 0) - float(row["payroll"] or 0), 1)
        }
        for row in negative_months
    ]

    owner_monthly_metrics = [
        {
            "month": row["month"],
            "revenue": round(float(row["revenue"] or 0), 1),
            "payroll": round(float(row["payroll"] or 0), 1),
            "profit": round(float(row["profit"] or 0), 1),
            "net_profit": round(float(row["profit"] or 0) - float(row["payroll"] or 0), 1),
            "jobs_count": int(row["jobs_count"] or 0),
            "average_job_value": round(float(row["average_job_value"] or 0), 1)
        }
        for row in owner_monthly_metrics
    ]

    selected_month_metrics = c.execute("""
    SELECT
        COALESCE(SUM(price), 0) as revenue,
        COALESCE(SUM(payroll_total), 0) as payroll,
        COALESCE(SUM(profit), 0) as profit
    FROM finance_summary
    WHERE company_id=?
      AND month=?
    """, (company_id, month)).fetchone()

    previous_month = (owner_selected_month_date.replace(day=1) - timedelta(days=1)).strftime("%Y-%m")

    previous_month_metrics = c.execute("""
    SELECT
        COALESCE(SUM(price), 0) as revenue,
        COALESCE(SUM(payroll_total), 0) as payroll,
        COALESCE(SUM(profit), 0) as profit
    FROM finance_summary
    WHERE company_id=?
      AND month=?
    """, (company_id, previous_month)).fetchone()

    selected_revenue = float(selected_month_metrics["revenue"] or 0)
    selected_payroll = float(selected_month_metrics["payroll"] or 0)
    selected_profit = float(selected_month_metrics["profit"] or 0)
    selected_net_profit = selected_profit - selected_payroll

    previous_revenue = float(previous_month_metrics["revenue"] or 0)
    previous_payroll = float(previous_month_metrics["payroll"] or 0)
    previous_profit = float(previous_month_metrics["profit"] or 0)
    previous_net_profit = previous_profit - previous_payroll

    owner_month_comparison = {
        "selected_month": month,
        "previous_month": previous_month,
        "revenue_growth": round(((selected_revenue - previous_revenue) / previous_revenue * 100), 1) if previous_revenue else 0,
        "payroll_growth": round(((selected_payroll - previous_payroll) / previous_payroll * 100), 1) if previous_payroll else 0,
        "net_profit_growth": round(((selected_net_profit - previous_net_profit) / previous_net_profit * 100), 1) if previous_net_profit else 0,
        "selected_revenue": round(selected_revenue, 1),
        "selected_payroll": round(selected_payroll, 1),
        "selected_net_profit": round(selected_net_profit, 1),
        "previous_revenue": round(previous_revenue, 1),
        "previous_payroll": round(previous_payroll, 1),
        "previous_net_profit": round(previous_net_profit, 1)
    }

    owner_chart_data = list(reversed(owner_monthly_metrics))

    conn.close()

    return templates.TemplateResponse(
        request,
        "owner_dashboard.html",
        {
            "request": request,
            "username": username,
            "role": role,
            "month": month,
            "total_clients": total_clients,
            "total_workers": total_workers,
            "total_tasks": total_tasks,
            "total_completed_tasks": total_completed_tasks,
            "total_revenue": total_revenue,
            "total_profit": total_profit,
            "total_payroll": total_payroll,
            "net_profit": net_profit,
            "unpaid_total": unpaid_total,
            "average_job_value": average_job_value,
            "payroll_ratio": payroll_ratio,
            "profit_margin": profit_margin,
            "completion_rate": completion_rate,
            "unpaid_ratio": unpaid_ratio,
            "unpaid_aging_summary": unpaid_aging_summary,
            "unpaid_risk_tasks": unpaid_risk_tasks,
            "repeat_clients_count": repeat_clients_count,
            "repeat_clients_revenue": repeat_clients_revenue,
            "top_repeat_clients": top_repeat_clients,
            "top_owner_clients": top_owner_clients,
            "top_owner_workers": top_owner_workers,
            "low_margin_clients": low_margin_clients,
            "negative_months": negative_months,
            "owner_monthly_metrics": owner_monthly_metrics,
            "owner_chart_data": owner_chart_data,
            "owner_month_comparison": owner_month_comparison,
            "settings": settings,
        }
    )

@router.get("/reports", response_class=HTMLResponse)
async def reports_page(request: Request, month: str = ""):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    update_last_seen(username)
    role = get_role(username)

    if role not in ("boss", "manager"):
        return RedirectResponse("/", status_code=302)

    company_id = get_user_company_id(username)
    disabled_response = require_feature(company_id, "analytics")

    if disabled_response:
        return disabled_response

    settings = get_company_settings(company_id)

    if not month:
        month = datetime.now().strftime("%Y-%m")

    conn = connect()
    c = conn.cursor()

    workers = c.execute("""
    SELECT username FROM users
    WHERE role='worker' AND company_id=?
    ORDER BY username
    """, (company_id,)).fetchall()

    report_rows = []

    total_completed = 0
    total_active = 0
    total_new = 0
    total_cancelled = 0
    total_revenue = 0

    for w in workers:
        worker_name = w[0]
        worker_condition = worker_task_condition()
        worker_params = worker_task_params(worker_name)

        completed = c.execute(f"""
        SELECT COUNT(*) FROM tasks
        WHERE archived=0 AND company_id=? AND {worker_condition}
          AND status='Завершено' AND task_date LIKE ?
        """, [company_id] + worker_params + [f"{month}%"]).fetchone()[0]

        active = c.execute(f"""
        SELECT COUNT(*) FROM tasks
        WHERE archived=0 AND company_id=? AND {worker_condition}
          AND status='В работе' AND task_date LIKE ?
        """, [company_id] + worker_params + [f"{month}%"]).fetchone()[0]

        new = c.execute(f"""
        SELECT COUNT(*) FROM tasks
        WHERE archived=0 AND company_id=? AND {worker_condition}
          AND status='Новая' AND task_date LIKE ?
        """, [company_id] + worker_params + [f"{month}%"]).fetchone()[0]

        cancelled = c.execute(f"""
        SELECT COUNT(*) FROM tasks
        WHERE archived=0 AND company_id=? AND {worker_condition}
          AND status='Отменено' AND task_date LIKE ?
        """, [company_id] + worker_params + [f"{month}%"]).fetchone()[0]

        revenue = c.execute(f"""
        SELECT SUM(price) FROM tasks
        WHERE archived=0 AND company_id=? AND {worker_condition}
          AND status='Завершено' AND task_date LIKE ?
        """, [company_id] + worker_params + [f"{month}%"]).fetchone()[0]

        if revenue is None:
            revenue = 0

        total_worker_tasks = completed + active + new + cancelled

        report_rows.append({
            "worker": worker_name,
            "completed": completed,
            "active": active,
            "new": new,
            "cancelled": cancelled,
            "revenue": revenue,
            "total": total_worker_tasks
        })

        total_completed += completed
        total_active += active
        total_new += new
        total_cancelled += cancelled
        total_revenue += revenue

    tasks = c.execute("""
    SELECT * FROM tasks
    WHERE company_id=? AND task_date LIKE ?
    ORDER BY task_date ASC, id DESC
    """, (company_id, f"{month}%")).fetchall()

    conn.close()

    return templates.TemplateResponse(
        request=request,
        name="reports.html",
        context={
            "username": username,
            "month": month,
            "report_rows": report_rows,
            "tasks": tasks,
            "total_completed": total_completed,
            "total_active": total_active,
            "total_new": total_new,
            "total_cancelled": total_cancelled,
            "total_revenue": total_revenue,
            "role": role,
            "settings": settings
        }
    )

@router.get("/archive", response_class=HTMLResponse)
async def archive_page(request: Request):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role not in ("boss", "manager"):
        return RedirectResponse("/", status_code=302)

    company_id = get_user_company_id(username)
    disabled_response = require_feature(company_id, "archive")

    if disabled_response:
        return disabled_response

    settings = get_company_settings(company_id)

    conn = connect()
    c = conn.cursor()

    tasks = c.execute("""
    SELECT *
    FROM tasks
    WHERE archived=1 AND company_id=?
    ORDER BY id DESC
    """, (company_id,)).fetchall()

    conn.close()

    return templates.TemplateResponse(
        request,
        "archive.html",
        {
            "request": request,
            "username": username,
            "role": role,
            "tasks": tasks,
            "settings": settings
        }
    )

@router.get("/my-tasks", response_class=HTMLResponse)
async def my_tasks_page(request: Request, status: str = ""):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role != "worker":
        return RedirectResponse("/", status_code=302)

    company_id = get_user_company_id(username)
    settings = get_company_settings(company_id)

    conn = connect()
    c = conn.cursor()

    query = """
    SELECT *
    FROM tasks
    WHERE archived=0
      AND company_id=?
    """

    query += f" AND {worker_task_condition()}"
    params = [company_id] + worker_task_params(username)

    if status:
        query += " AND status=?"
        params.append(status)
        query += " ORDER BY task_date DESC, id DESC"
    else:
        query += " AND status!='Завершено'"
        query += """
        ORDER BY
            CASE status
                WHEN 'В работе' THEN 0
                WHEN 'Новая' THEN 1
                ELSE 2
            END,
            CASE WHEN task_date IS NULL OR task_date='' THEN 1 ELSE 0 END,
            task_date ASC,
            id DESC
        """

    tasks = c.execute(query, params).fetchall()

    conn.close()

    return templates.TemplateResponse(
        request,
        "my_tasks.html",
        {
            "request": request,
            "username": username,
            "role": role,
            "tasks": tasks,
            "selected_status": status,
            "settings": settings
        }
    )
