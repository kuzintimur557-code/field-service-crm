"""Team management routes."""

import csv
import io
from datetime import datetime, timedelta
from urllib.parse import urlencode

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
    TEAM_ACTIVITY_FILTERS,
    build_dashboard_links,
    get_company_settings,
    get_task_worker_names,
    get_workers_for_company,
    log_task_activity,
    worker_task_condition,
    worker_task_params,
)
from app.services.plans import (
    get_company_user_limit_usage,
    get_recommended_user_limit_plan,
)
from app.templating import templates

router = APIRouter()


def run_automation_event(*args, **kwargs):
    from app.main import run_automation_event as _impl

    return _impl(*args, **kwargs)


def get_worker_unavailability(*args, **kwargs):
    from app.main import get_worker_unavailability as _impl

    return _impl(*args, **kwargs)


def hash_password(*args, **kwargs):
    from app.main import hash_password as _impl

    return _impl(*args, **kwargs)


def is_password_strong(*args, **kwargs):
    from app.main import is_password_strong as _impl

    return _impl(*args, **kwargs)


def record_user_limit_warning(*args, **kwargs):
    from app.main import record_user_limit_warning as _impl

    return _impl(*args, **kwargs)

@router.get("/workers", response_class=HTMLResponse)
async def workers_page(
    request: Request,
    status: str = "active",
    search: str = ""
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
    settings = get_company_settings(company_id)
    user_limit_usage = get_company_user_limit_usage(company_id, settings)
    recommended_plan = None

    if user_limit_usage["tone"] in ("warning", "danger"):
        recommended_plan = get_recommended_user_limit_plan(
            user_limit_usage["plan"],
            user_limit_usage["active_users_count"],
        )

    worker_data = get_workers_for_company(
        company_id,
        status=status,
        search=search,
    )

    conn = connect()
    c = conn.cursor()

    team_counts = c.execute("""
    SELECT
        COUNT(*) AS total_count,
        SUM(CASE WHEN COALESCE(is_active, 1)=1 THEN 1 ELSE 0 END) AS active_count,
        SUM(CASE WHEN is_active=0 THEN 1 ELSE 0 END) AS inactive_count
    FROM users
    WHERE role IN ('manager', 'worker') AND company_id=?
    """, (company_id,)).fetchone()

    conn.close()

    return templates.TemplateResponse(
        request=request,
        name="workers.html",
        context={
            "workers": worker_data["workers"],
            "username": username,
            "role": role,
            "status": worker_data["status"],
            "search": worker_data["search"],
            "team_counts": team_counts,
            "user_limit_usage": user_limit_usage,
            "recommended_plan": recommended_plan,
            "settings": settings
        }
    )


@router.get("/workers/export")
async def workers_export(
    request: Request,
    status: str = "active",
    search: str = ""
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
    settings = get_company_settings(company_id)
    user_limit_usage = get_company_user_limit_usage(company_id, settings)
    recommended_plan = None

    if user_limit_usage["tone"] in ("warning", "danger"):
        recommended_plan = get_recommended_user_limit_plan(
            user_limit_usage["plan"],
            user_limit_usage["active_users_count"],
        )

    worker_data = get_workers_for_company(
        company_id,
        status=status,
        search=search,
    )
    workers = worker_data["workers"]
    status = worker_data["status"]
    selected_search = worker_data["search"]

    worker_label = (
        settings["worker_label"]
        if settings and settings["worker_label"]
        else "Исполнитель"
    )
    role_labels = {
        "manager": "Менеджер",
        "worker": worker_label,
    }

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "Логин",
        "ФИО",
        "Роль",
        "Статус",
        "Должность",
        "Телефон",
        "Электронная почта",
        "Номер чата Telegram",
        "Процент с прибыли",
        "Был онлайн",
    ])

    for worker in workers:
        writer.writerow([
            worker["username"] or "",
            worker["full_name"] or "",
            role_labels.get(worker["role"], worker["role"] or ""),
            "Активен" if worker["is_active"] is None or worker["is_active"] else "Отключён",
            worker["position"] or "",
            worker["phone"] or "",
            worker["email"] or "",
            worker["telegram_chat_id"] or "",
            worker["commission_percent"] or 0,
            worker["last_seen"] or "",
        ])

    writer.writerow([])
    writer.writerow(["Тариф", user_limit_usage["plan_label"]])
    writer.writerow([
        "Лимит пользователей",
        (
            f"{user_limit_usage['active_users_count']} / "
            f"{user_limit_usage['user_limit_label']}"
        ),
    ])
    writer.writerow(["Статус лимита", user_limit_usage["status"]])
    writer.writerow([
        "Рекомендуемый тариф",
        recommended_plan["label"] if recommended_plan else "",
    ])

    filename_parts = [
        status,
        "search" if selected_search else "all",
    ]
    filename = "workers_" + "_".join(filename_parts) + ".csv"

    return Response(
        content="\ufeff" + output.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f"attachment; filename={filename}"
        }
    )


@router.get("/workers/activity", response_class=HTMLResponse)
async def team_activity_page(
    request: Request,
    action: str = "all",
    search: str = "",
    date_from: str = "",
    date_to: str = "",
):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role not in ("boss", "manager"):
        return RedirectResponse("/", status_code=302)

    company_id = get_user_company_id(username)
    if action not in TEAM_ACTIVITY_FILTERS:
        action = "all"

    search = str(search or "").strip()[:100]
    date_from = str(date_from or "").strip()[:10]
    date_to = str(date_to or "").strip()[:10]
    conn = connect()
    c = conn.cursor()
    selected_actions = TEAM_ACTIVITY_FILTERS[action]
    query = """
    SELECT team_activity.*, users.id AS current_user_id
    FROM team_activity
    LEFT JOIN users
      ON users.id=team_activity.user_id
     AND users.company_id=team_activity.company_id
    WHERE team_activity.company_id=?
    """
    params = [company_id]

    if selected_actions:
        placeholders = ",".join("?" for _ in selected_actions)
        query += f" AND team_activity.action IN ({placeholders})"
        params.extend(selected_actions)

    if search:
        query += """
        AND (
            lower(team_activity.target_username) LIKE ?
            OR lower(team_activity.actor_username) LIKE ?
        )
        """
        search_value = f"%{search.lower()}%"
        params.extend([search_value, search_value])

    if date_from:
        query += " AND team_activity.created_at >= ?"
        params.append(date_from)

    if date_to:
        query += " AND team_activity.created_at <= ?"
        params.append(date_to + " 23:59")

    query += " ORDER BY team_activity.id DESC LIMIT 200"
    events = c.execute(query, params).fetchall()

    activity_counts = c.execute("""
    SELECT
        COUNT(*) AS total_count,
        SUM(CASE WHEN action IN (
            'Пользователь создан', 'Пользователь удалён'
        ) THEN 1 ELSE 0 END) AS membership_count,
        SUM(CASE WHEN action IN (
            'Пользователь отключён', 'Пользователь включён'
        ) THEN 1 ELSE 0 END) AS access_count,
        SUM(CASE WHEN action='Пароль обновлён' THEN 1 ELSE 0 END) AS password_count,
        SUM(CASE WHEN action='Процент обновлён' THEN 1 ELSE 0 END) AS commission_count,
        SUM(CASE WHEN action='Лимит тарифа' THEN 1 ELSE 0 END) AS limit_count,
        SUM(CASE WHEN action IN (
            'Счёт платформы создан', 'Статус счёта платформы'
        ) THEN 1 ELSE 0 END) AS billing_count
    FROM team_activity
    WHERE company_id=?
    """, (company_id,)).fetchone()

    conn.close()
    common_filter_params = {}

    if search:
        common_filter_params["search"] = search
    if date_from:
        common_filter_params["date_from"] = date_from
    if date_to:
        common_filter_params["date_to"] = date_to

    activity_filter_links = {}
    for action_key in TEAM_ACTIVITY_FILTERS:
        link_params = {"action": action_key, **common_filter_params}
        activity_filter_links[action_key] = (
            "/workers/activity?" + urlencode(link_params)
        )

    export_params = {"action": action, **common_filter_params}

    return templates.TemplateResponse(
        request=request,
        name="team_activity.html",
        context={
            "request": request,
            "username": username,
            "role": role,
            "events": events,
            "action": action,
            "search": search,
            "date_from": date_from,
            "date_to": date_to,
            "activity_counts": activity_counts,
            "activity_filter_links": activity_filter_links,
            "export_url": (
                "/workers/activity/export?" + urlencode(export_params)
            ),
        },
    )


@router.get("/workers/activity/export")
async def team_activity_export(
    request: Request,
    action: str = "all",
    search: str = "",
    date_from: str = "",
    date_to: str = "",
):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role not in ("boss", "manager"):
        return RedirectResponse("/", status_code=302)

    if action not in TEAM_ACTIVITY_FILTERS:
        action = "all"

    search = str(search or "").strip()[:100]
    date_from = str(date_from or "").strip()[:10]
    date_to = str(date_to or "").strip()[:10]
    company_id = get_user_company_id(username)
    selected_actions = TEAM_ACTIVITY_FILTERS[action]
    conn = connect()
    c = conn.cursor()
    query = """
    SELECT target_username, actor_username, action, details, created_at
    FROM team_activity
    WHERE company_id=?
    """
    params = [company_id]

    if selected_actions:
        placeholders = ",".join("?" for _ in selected_actions)
        query += f" AND action IN ({placeholders})"
        params.extend(selected_actions)

    if search:
        query += """
        AND (
            lower(target_username) LIKE ?
            OR lower(actor_username) LIKE ?
        )
        """
        search_value = f"%{search.lower()}%"
        params.extend([search_value, search_value])

    if date_from:
        query += " AND created_at >= ?"
        params.append(date_from)

    if date_to:
        query += " AND created_at <= ?"
        params.append(date_to + " 23:59")

    query += " ORDER BY id DESC"
    events = c.execute(query, params).fetchall()
    conn.close()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "Сотрудник",
        "Действие",
        "Подробности",
        "Выполнил",
        "Дата",
    ])

    for event in events:
        writer.writerow([
            event["target_username"] or "",
            event["action"] or "",
            event["details"] or "",
            event["actor_username"] or "",
            event["created_at"] or "",
        ])

    content = "\ufeff" + output.getvalue()

    return Response(
        content,
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": (
                f"attachment; filename=team_activity_{action}.csv"
            )
        },
    )



@router.get("/workers/{worker_id}", response_class=HTMLResponse)
async def worker_detail(request: Request, worker_id: int, month: str = ""):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role not in ("boss", "manager"):
        return RedirectResponse("/", status_code=302)

    company_id = get_user_company_id(username)

    if not month:
        month = datetime.now().strftime("%Y-%m")

    conn = connect()
    c = conn.cursor()

    worker = c.execute("""
    SELECT *
    FROM users
    WHERE id=? AND company_id=?
    """, (worker_id, company_id)).fetchone()

    if not worker:
        conn.close()
        return RedirectResponse("/workers", status_code=302)

    worker_condition = worker_task_condition()
    worker_params = worker_task_params(worker["username"])
    settings = get_company_settings(company_id)
    task_label = settings["task_label"] or "Заявка"
    client_label = settings["client_label"] or "Клиент"
    worker_label = settings["worker_label"] or "Сотрудник"
    today = datetime.now().strftime("%Y-%m-%d")

    total_tasks = c.execute(f"""
    SELECT COUNT(*)
    FROM tasks
    WHERE company_id=? AND {worker_condition}
    """, [company_id] + worker_params).fetchone()[0]

    done_tasks = c.execute(f"""
    SELECT COUNT(*)
    FROM tasks
    WHERE company_id=? AND {worker_condition} AND status='Завершено'
    """, [company_id] + worker_params).fetchone()[0]

    active_tasks_count = c.execute(f"""
    SELECT COUNT(*)
    FROM tasks
    WHERE company_id=?
      AND archived=0
      AND status NOT IN ('Завершено', 'Отменено')
      AND {worker_condition}
    """, [company_id] + worker_params).fetchone()[0]

    overdue_tasks_count = c.execute(f"""
    SELECT COUNT(*)
    FROM tasks
    WHERE company_id=?
      AND archived=0
      AND status NOT IN ('Завершено', 'Отменено')
      AND task_date IS NOT NULL
      AND task_date != ''
      AND substr(task_date, 1, 10) < ?
      AND {worker_condition}
    """, [company_id, today] + worker_params).fetchone()[0]

    today_tasks_count = c.execute(f"""
    SELECT COUNT(*)
    FROM tasks
    WHERE company_id=?
      AND archived=0
      AND status NOT IN ('Завершено', 'Отменено')
      AND task_date LIKE ?
      AND {worker_condition}
    """, [company_id, f"{today}%"] + worker_params).fetchone()[0]

    future_tasks_count = c.execute(f"""
    SELECT COUNT(*)
    FROM tasks
    WHERE company_id=?
      AND archived=0
      AND status NOT IN ('Завершено', 'Отменено')
      AND task_date IS NOT NULL
      AND task_date != ''
      AND substr(task_date, 1, 10) > ?
      AND {worker_condition}
    """, [company_id, today] + worker_params).fetchone()[0]

    active_tasks = c.execute(f"""
    SELECT *
    FROM tasks
    WHERE company_id=?
      AND archived=0
      AND status NOT IN ('Завершено', 'Отменено')
      AND {worker_condition}
    ORDER BY
      CASE WHEN task_date IS NULL OR task_date='' THEN 1 ELSE 0 END,
      task_date,
      id
    LIMIT 10
    """, [company_id] + worker_params).fetchall()

    income = c.execute(f"""
    SELECT SUM(price)
    FROM tasks
    WHERE company_id=? AND {worker_condition} AND status='Завершено'
    """, [company_id] + worker_params).fetchone()[0] or 0

    month_tasks = c.execute(f"""
    SELECT *
    FROM tasks
    WHERE archived=0
      AND company_id=?
      AND {worker_condition}
      AND task_date LIKE ?
    """, [company_id] + worker_params + [f"{month}%"]).fetchall()

    finance_total = 0
    finance_profit = 0
    finance_expenses = 0

    for task in month_tasks:
        items = c.execute("""
        SELECT *
        FROM task_items
        WHERE task_id=?
        """, (task["id"],)).fetchall()
        expenses = c.execute("""
        SELECT *
        FROM task_expenses
        WHERE task_id=?
        """, (task["id"],)).fetchall()

        task_total = sum(item["total"] for item in items)
        task_profit = sum(item["profit"] for item in items)
        discount_amount = float(task["discount_amount"] or 0) if "discount_amount" in task.keys() else 0
        task_expenses_total = sum(expense["amount"] for expense in expenses)

        if not items:
            try:
                task_total = float(task["price"] or 0)
            except Exception:
                task_total = 0
            task_profit = 0

        if discount_amount < 0:
            discount_amount = 0

        task_total = max(task_total - discount_amount, 0)
        task_profit = task_profit - discount_amount - task_expenses_total

        task_worker_count = len(get_task_worker_names(task)) or 1
        finance_total += task_total / task_worker_count
        finance_profit += task_profit / task_worker_count
        finance_expenses += task_expenses_total / task_worker_count

    commission_percent = float(worker["commission_percent"] or 0) if "commission_percent" in worker.keys() else 0
    finance_total = round(finance_total, 1)
    finance_profit = round(finance_profit, 1)
    finance_expenses = round(finance_expenses, 1)
    finance_payout = round(finance_profit * commission_percent / 100, 1)
    finance_margin = round((finance_profit / finance_total) * 100, 1) if finance_total else 0

    payroll_payout = c.execute("""
    SELECT *
    FROM payroll_payouts
    WHERE company_id=? AND worker_id=? AND month=? AND status='paid'
    """, (company_id, worker_id, month)).fetchone()
    payroll_paid_amount = round(float(payroll_payout["amount"] or 0), 1) if payroll_payout else 0
    payroll_due_amount = round(max(finance_payout - payroll_paid_amount, 0), 1)
    payroll_status = "Не выплачено"

    if payroll_payout:
        payroll_status = "Выплачено" if payroll_paid_amount >= finance_payout else "Частично"

    team_activity = c.execute("""
    SELECT *
    FROM team_activity
    WHERE company_id=? AND user_id=?
    ORDER BY id DESC
    LIMIT 20
    """, (company_id, worker_id)).fetchall()

    unavailability_periods = []

    if worker["role"] == "worker":
        unavailability_periods = c.execute("""
        SELECT *
        FROM worker_unavailability
        WHERE company_id=? AND worker_id=?
        ORDER BY
            CASE WHEN date_to >= ? THEN 0 ELSE 1 END,
            date_from,
            id DESC
        LIMIT 30
        """, (company_id, worker_id, today)).fetchall()

    weekly_schedule = []
    nearest_free_date = ""
    daily_capacity = max(1, int(worker["daily_capacity"] or 3))
    worker_is_active = (
        worker["is_active"] is None or int(worker["is_active"]) == 1
    )

    if worker["role"] == "worker" and worker_is_active:
        schedule_end = (
            datetime.now() + timedelta(days=6)
        ).strftime("%Y-%m-%d")
        schedule_rows = c.execute(f"""
        SELECT substr(task_date, 1, 10) AS work_date, COUNT(*) AS task_count
        FROM tasks
        WHERE company_id=?
          AND archived=0
          AND status NOT IN ('Завершено', 'Отменено')
          AND task_date IS NOT NULL
          AND task_date != ''
          AND substr(task_date, 1, 10) BETWEEN ? AND ?
          AND {worker_condition}
        GROUP BY substr(task_date, 1, 10)
        """, [company_id, today, schedule_end] + worker_params).fetchall()
        schedule_counts = {
            row["work_date"]: row["task_count"]
            for row in schedule_rows
        }
        unavailable_dates, unavailable_reasons = get_worker_unavailability(
            c,
            company_id,
            [worker["username"]],
            today,
            schedule_end,
        )
        weekday_labels = [
            "Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"
        ]

        for day_offset in range(7):
            schedule_date = datetime.now() + timedelta(days=day_offset)
            date_value = schedule_date.strftime("%Y-%m-%d")
            task_count = int(schedule_counts.get(date_value, 0))
            load_status = "Свободен"
            available_slots = max(daily_capacity - task_count, 0)
            is_unavailable = (
                date_value
                in unavailable_dates.get(worker["username"], set())
            )
            unavailable_reason = unavailable_reasons.get(
                (worker["username"], date_value),
                "",
            )

            if is_unavailable:
                load_status = "Недоступен"
                available_slots = 0
            elif task_count >= daily_capacity:
                load_status = "Нет мест"
            elif task_count:
                load_status = "Есть места"

            if (
                not nearest_free_date
                and not is_unavailable
                and available_slots > 0
            ):
                nearest_free_date = date_value

            weekly_schedule.append({
                "date": date_value,
                "day_label": weekday_labels[schedule_date.weekday()],
                "date_label": schedule_date.strftime("%d.%m"),
                "task_count": task_count,
                "available_slots": available_slots,
                "load_status": load_status,
                "is_unavailable": is_unavailable,
                "unavailable_reason": unavailable_reason,
                "calendar_url": "/calendar?" + urlencode({
                    "date": date_value,
                    "worker": worker["username"],
                }),
                "create_url": "/create-task?" + urlencode({
                    "task_date": date_value,
                    "worker": worker["username"],
                    "return_to": "calendar",
                }),
            })

    conn.close()
    create_task_url = ""
    worker_calendar_url = ""

    if worker["role"] == "worker" and worker_is_active:
        create_task_url = "/create-task?" + urlencode({
            "task_date": today,
            "worker": worker["username"],
            "return_to": "calendar",
        })
        worker_calendar_url = "/calendar?" + urlencode({
            "worker": worker["username"],
            "month": today[:7],
        })

    return templates.TemplateResponse(
        request=request,
        name="worker_detail.html",
        context={
            "request": request,
            "username": username,
            "role": role,
            "worker": worker,
            "month": month,
            "total_tasks": total_tasks,
            "done_tasks": done_tasks,
            "active_tasks_count": active_tasks_count,
            "overdue_tasks_count": overdue_tasks_count,
            "today_tasks_count": today_tasks_count,
            "future_tasks_count": future_tasks_count,
            "active_tasks": active_tasks,
            "today": today,
            "task_label": task_label,
            "client_label": client_label,
            "worker_label": worker_label,
            "create_task_url": create_task_url,
            "worker_calendar_url": worker_calendar_url,
            "weekly_schedule": weekly_schedule,
            "unavailability_periods": unavailability_periods,
            "nearest_free_date": nearest_free_date,
            "daily_capacity": daily_capacity,
            "income": income,
            "finance_total": finance_total,
            "finance_profit": finance_profit,
            "finance_expenses": finance_expenses,
            "finance_payout": finance_payout,
            "finance_margin": finance_margin,
            "payroll_status": payroll_status,
            "payroll_paid_amount": payroll_paid_amount,
            "payroll_due_amount": payroll_due_amount,
            "payroll_note": payroll_payout["note"] if payroll_payout else "",
            "team_activity": team_activity,
        }
    )



@router.post("/workers/{user_id}/unavailability")
async def create_worker_unavailability(request: Request, user_id: int):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    if get_role(username) not in ("boss", "manager"):
        return RedirectResponse("/", status_code=302)

    company_id = get_user_company_id(username)
    form = await request.form()
    date_from = str(form.get("date_from") or "").strip()
    date_to = str(form.get("date_to") or "").strip()
    reason = str(form.get("reason") or "").strip()[:300]

    try:
        period_start = datetime.strptime(date_from, "%Y-%m-%d").date()
        period_end = datetime.strptime(date_to, "%Y-%m-%d").date()
    except Exception:
        return RedirectResponse(
            f"/workers/{user_id}?unavailability_error=invalid_date",
            status_code=302,
        )

    if period_end < period_start:
        return RedirectResponse(
            f"/workers/{user_id}?unavailability_error=invalid_period",
            status_code=302,
        )

    if (period_end - period_start).days > 365:
        return RedirectResponse(
            f"/workers/{user_id}?unavailability_error=period_too_long",
            status_code=302,
        )

    conn = connect()
    c = conn.cursor()
    worker = c.execute("""
    SELECT id, username, role
    FROM users
    WHERE id=? AND company_id=?
    """, (user_id, company_id)).fetchone()

    if not worker or worker["role"] != "worker":
        conn.close()
        return RedirectResponse("/workers", status_code=302)

    overlapping_period = c.execute("""
    SELECT id
    FROM worker_unavailability
    WHERE company_id=?
      AND worker_id=?
      AND date_from <= ?
      AND date_to >= ?
    LIMIT 1
    """, (
        company_id,
        user_id,
        date_to,
        date_from,
    )).fetchone()

    if overlapping_period:
        conn.close()
        return RedirectResponse(
            f"/workers/{user_id}?unavailability_error=overlap",
            status_code=302,
        )

    created_at = datetime.now().strftime("%Y-%m-%d %H:%M")
    c.execute("""
    INSERT INTO worker_unavailability (
        company_id, worker_id, date_from, date_to,
        reason, created_by, created_at
    )
    VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        company_id,
        user_id,
        date_from,
        date_to,
        reason,
        username,
        created_at,
    ))
    activity_details = f"{date_from} — {date_to}"

    if reason:
        activity_details += f" · {reason}"

    c.execute("""
    INSERT INTO team_activity (
        company_id, user_id, target_username, actor_username,
        action, details, created_at
    )
    VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        company_id,
        user_id,
        worker["username"],
        username,
        "Добавлен период недоступности",
        activity_details,
        created_at,
    ))
    conn.commit()
    conn.close()

    run_automation_event(
        company_id,
        "worker_unavailability_changed",
        "worker",
        user_id,
        (
            f"Недоступность сотрудника {worker['username']} добавлена: "
            f"{activity_details}"
        ),
        f"/workers/{user_id}",
    )

    return RedirectResponse(
        f"/workers/{user_id}?unavailability_created=1",
        status_code=302,
    )


@router.post("/workers/{user_id}/unavailability/{period_id}/delete")
async def delete_worker_unavailability(
    request: Request,
    user_id: int,
    period_id: int,
):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    if get_role(username) not in ("boss", "manager"):
        return RedirectResponse("/", status_code=302)

    company_id = get_user_company_id(username)
    conn = connect()
    c = conn.cursor()
    period = c.execute("""
    SELECT
        worker_unavailability.*,
        users.username AS worker_username
    FROM worker_unavailability
    JOIN users ON users.id=worker_unavailability.worker_id
    WHERE worker_unavailability.id=?
      AND worker_unavailability.worker_id=?
      AND worker_unavailability.company_id=?
      AND users.company_id=worker_unavailability.company_id
    """, (period_id, user_id, company_id)).fetchone()

    if not period:
        conn.close()
        return RedirectResponse(f"/workers/{user_id}", status_code=302)

    c.execute("""
    DELETE FROM worker_unavailability
    WHERE id=? AND worker_id=? AND company_id=?
    """, (period_id, user_id, company_id))
    activity_details = f"{period['date_from']} — {period['date_to']}"

    if period["reason"]:
        activity_details += f" · {period['reason']}"

    c.execute("""
    INSERT INTO team_activity (
        company_id, user_id, target_username, actor_username,
        action, details, created_at
    )
    VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        company_id,
        user_id,
        period["worker_username"],
        username,
        "Удалён период недоступности",
        activity_details,
        datetime.now().strftime("%Y-%m-%d %H:%M"),
    ))
    conn.commit()
    conn.close()

    run_automation_event(
        company_id,
        "worker_unavailability_changed",
        "worker",
        user_id,
        (
            f"Недоступность сотрудника {period['worker_username']} удалена: "
            f"{activity_details}"
        ),
        f"/workers/{user_id}",
    )

    return RedirectResponse(
        f"/workers/{user_id}?unavailability_deleted=1",
        status_code=302,
    )


@router.post("/workers")
async def create_worker(request: Request):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role != "boss":
        return RedirectResponse("/", status_code=302)

    company_id = get_user_company_id(username)

    form = await request.form()

    worker_username = (form.get("username") or "").strip()
    worker_password = (form.get("password") or "").strip()
    worker_role = (form.get("role") or "worker").strip()

    if not worker_username or not worker_password:
        return RedirectResponse(
            "/workers?error=empty_credentials",
            status_code=302,
        )

    if worker_role not in ("manager", "worker"):
        return RedirectResponse("/workers?error=invalid_role", status_code=302)

    if not is_password_strong(worker_password):
        return RedirectResponse("/workers?error=weak_password", status_code=302)

    full_name = (form.get("full_name") or "").strip()
    position = (form.get("position") or "").strip()
    phone = (form.get("phone") or "").strip()
    email = (form.get("email") or "").strip()
    telegram_chat_id = (form.get("telegram_chat_id") or "").strip()
    commission_percent = form.get("commission_percent") or "0"

    try:
        commission_percent = float(str(commission_percent).replace(",", "."))
    except Exception:
        commission_percent = 0

    if commission_percent < 0:
        commission_percent = 0

    conn = connect()
    c = conn.cursor()

    existing = c.execute("""
    SELECT *
    FROM users
    WHERE username=?
    """, (worker_username,)).fetchone()

    if existing:
        conn.close()
        return RedirectResponse("/workers?error=exists", status_code=302)

    c.execute("""
    INSERT INTO users (
        username,
        password,
        role,
        company_id,
        full_name,
        position,
        phone,
        email,
        telegram_chat_id,
        commission_percent,
        last_seen
    )
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        worker_username,
        hash_password(worker_password),
        worker_role,
        company_id,
        full_name,
        position,
        phone,
        email,
        telegram_chat_id,
        commission_percent,
        datetime.now().strftime("%Y-%m-%d %H:%M")
    ))
    created_user_id = c.lastrowid
    c.execute("""
    INSERT INTO team_activity (
        company_id, user_id, target_username, actor_username,
        action, details, created_at
    )
    VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        company_id,
        created_user_id,
        worker_username,
        username,
        "Пользователь создан",
        "Роль: " + (
            "Менеджер" if worker_role == "manager" else "Исполнитель"
        ),
        datetime.now().strftime("%Y-%m-%d %H:%M"),
    ))

    conn.commit()
    conn.close()

    limit_warning = record_user_limit_warning(
        company_id,
        username,
        created_user_id,
        worker_username,
    )

    run_automation_event(
        company_id,
        "worker_created",
        "worker",
        created_user_id,
        f"Сотрудник создан: {worker_username}",
        f"/workers/{created_user_id}",
    )

    if limit_warning:
        run_automation_event(
            company_id,
            "company_user_limit_warning",
            "worker",
            created_user_id,
            (
                f"Создан пользователь {worker_username}, "
                f"но {limit_warning['usage']['status'].lower()}"
            ),
            "/billing",
        )
        return RedirectResponse(
            "/workers?created=1&limit_warning=1",
            status_code=302,
        )

    return RedirectResponse("/workers?created=1", status_code=302)


@router.post("/workers/{user_id}/profile")
async def update_team_user_profile(request: Request, user_id: int):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    if get_role(username) != "boss":
        return RedirectResponse("/workers?error=only_boss", status_code=302)

    company_id = get_user_company_id(username)
    form = await request.form()
    profile_fields = {
        "full_name": str(form.get("full_name") or "").strip()[:150],
        "position": str(form.get("position") or "").strip()[:150],
        "phone": str(form.get("phone") or "").strip()[:100],
        "email": str(form.get("email") or "").strip()[:200],
        "telegram_chat_id": str(
            form.get("telegram_chat_id") or ""
        ).strip()[:200],
    }
    raw_daily_capacity = form.get("daily_capacity")
    field_labels = {
        "full_name": "ФИО",
        "position": "Должность",
        "phone": "Телефон",
        "email": "Электронная почта",
        "telegram_chat_id": "Номер чата Telegram",
        "daily_capacity": "Дневной лимит заявок",
    }

    conn = connect()
    c = conn.cursor()
    user = c.execute("""
    SELECT *
    FROM users
    WHERE id=? AND company_id=?
    """, (user_id, company_id)).fetchone()

    if not user:
        conn.close()
        return RedirectResponse("/workers", status_code=302)

    if user["role"] == "boss":
        conn.close()
        return RedirectResponse(
            "/workers?error=cannot_change_boss",
            status_code=302,
        )

    try:
        daily_capacity = int(
            raw_daily_capacity
            if raw_daily_capacity not in (None, "")
            else (user["daily_capacity"] or 3)
        )
    except Exception:
        daily_capacity = int(user["daily_capacity"] or 3)

    daily_capacity = min(max(daily_capacity, 1), 20)
    profile_fields["daily_capacity"] = daily_capacity
    changed_fields = [
        field_labels[field]
        for field, value in profile_fields.items()
        if (
            int(user[field] or 3) != value
            if field == "daily_capacity"
            else str(user[field] or "") != value
        )
    ]

    c.execute("""
    UPDATE users
    SET full_name=?, position=?, phone=?, email=?, telegram_chat_id=?,
        daily_capacity=?
    WHERE id=? AND company_id=?
    """, (
        profile_fields["full_name"],
        profile_fields["position"],
        profile_fields["phone"],
        profile_fields["email"],
        profile_fields["telegram_chat_id"],
        profile_fields["daily_capacity"],
        user_id,
        company_id,
    ))

    if changed_fields:
        c.execute("""
        INSERT INTO team_activity (
            company_id, user_id, target_username, actor_username,
            action, details, created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            company_id,
            user_id,
            user["username"],
            username,
            "Карточка обновлена",
            "Изменены поля: " + ", ".join(changed_fields),
            datetime.now().strftime("%Y-%m-%d %H:%M"),
        ))

    conn.commit()
    conn.close()

    if changed_fields:
        run_automation_event(
            company_id,
            "worker_profile_updated",
            "worker",
            user_id,
            (
                f"Карточка сотрудника {user['username']} обновлена: "
                f"{', '.join(changed_fields)}"
            ),
            f"/workers/{user_id}",
        )

    return RedirectResponse(
        f"/workers/{user_id}?profile_updated=1",
        status_code=302,
    )


@router.post("/workers/{user_id}/password")
async def change_team_user_password(request: Request, user_id: int):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role != "boss":
        return RedirectResponse("/workers?error=only_boss", status_code=302)

    company_id = get_user_company_id(username)
    form = await request.form()
    new_password = (form.get("password") or "").strip()

    if not new_password:
        return RedirectResponse("/workers?error=empty_password", status_code=302)

    if not is_password_strong(new_password):
        return RedirectResponse("/workers?error=weak_password", status_code=302)

    conn = connect()
    c = conn.cursor()

    user = c.execute("""
    SELECT *
    FROM users
    WHERE id=? AND company_id=?
    """, (user_id, company_id)).fetchone()

    if not user:
        conn.close()
        return RedirectResponse("/workers", status_code=302)

    if user["username"] == username or user["role"] == "boss":
        conn.close()
        return RedirectResponse(
            "/workers?error=cannot_change_boss",
            status_code=302,
        )

    c.execute("""
    UPDATE users
    SET password=?, session_version=COALESCE(session_version, 1) + 1
    WHERE id=? AND company_id=?
    """, (hash_password(new_password), user_id, company_id))
    c.execute("""
    INSERT INTO team_activity (
        company_id, user_id, target_username, actor_username,
        action, details, created_at
    )
    VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        company_id,
        user_id,
        user["username"],
        username,
        "Пароль обновлён",
        "Пароль изменён владельцем компании",
        datetime.now().strftime("%Y-%m-%d %H:%M"),
    ))

    conn.commit()
    conn.close()

    run_automation_event(
        company_id,
        "worker_password_changed",
        "worker",
        user_id,
        f"Пароль сотрудника {user['username']} изменён",
        f"/workers/{user_id}",
    )

    return RedirectResponse("/workers?password_changed=1", status_code=302)


@router.post("/workers/{user_id}/commission")
async def update_worker_commission(request: Request, user_id: int):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role != "boss":
        return RedirectResponse("/workers?error=only_boss", status_code=302)

    company_id = get_user_company_id(username)
    form = await request.form()
    commission_percent = form.get("commission_percent") or "0"

    try:
        commission_percent = float(str(commission_percent).replace(",", "."))
    except Exception:
        commission_percent = 0

    if commission_percent < 0:
        commission_percent = 0

    conn = connect()
    c = conn.cursor()

    user = c.execute("""
    SELECT *
    FROM users
    WHERE id=? AND company_id=?
    """, (user_id, company_id)).fetchone()

    if not user:
        conn.close()
        return RedirectResponse("/workers", status_code=302)

    if user["role"] == "boss":
        conn.close()
        return RedirectResponse("/workers?error=cannot_change_boss", status_code=302)

    previous_commission = float(user["commission_percent"] or 0)
    c.execute("""
    UPDATE users
    SET commission_percent=?
    WHERE id=? AND company_id=?
    """, (commission_percent, user_id, company_id))
    c.execute("""
    INSERT INTO team_activity (
        company_id, user_id, target_username, actor_username,
        action, details, created_at
    )
    VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        company_id,
        user_id,
        user["username"],
        username,
        "Процент обновлён",
        f"{previous_commission:g}% → {commission_percent:g}%",
        datetime.now().strftime("%Y-%m-%d %H:%M"),
    ))

    conn.commit()
    conn.close()

    if previous_commission != commission_percent:
        run_automation_event(
            company_id,
            "worker_commission_updated",
            "worker",
            user_id,
            (
                f"Процент сотрудника {user['username']}: "
                f"{previous_commission:g}% → {commission_percent:g}%"
            ),
            f"/workers/{user_id}",
        )

    return RedirectResponse("/workers?commission_updated=1", status_code=302)


@router.post("/workers/{user_id}/toggle-active")
async def toggle_team_user_active(request: Request, user_id: int):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    if get_role(username) != "boss":
        return RedirectResponse("/workers?error=only_boss", status_code=302)

    company_id = get_user_company_id(username)
    form = await request.form()
    disabled_reason = str(form.get("disabled_reason") or "").strip()[:500]
    conn = connect()
    c = conn.cursor()

    user = c.execute("""
    SELECT id, username, role, is_active
    FROM users
    WHERE id=? AND company_id=?
    """, (user_id, company_id)).fetchone()

    if not user:
        conn.close()
        return RedirectResponse("/workers", status_code=302)

    if user["username"] == username or user["role"] == "boss":
        conn.close()
        return RedirectResponse(
            "/workers?error=cannot_disable_boss",
            status_code=302,
        )

    current_active = 1 if user["is_active"] is None else int(user["is_active"])

    if current_active and user["role"] == "worker":
        active_task_count = c.execute(f"""
        SELECT COUNT(*)
        FROM tasks
        WHERE company_id=?
          AND archived=0
          AND status NOT IN ('Завершено', 'Отменено')
          AND {worker_task_condition()}
        """, [
            company_id,
            *worker_task_params(user["username"]),
        ]).fetchone()[0]

        if active_task_count:
            conn.close()
            return RedirectResponse(
                (
                    "/workers?error=active_tasks"
                    f"&count={active_task_count}"
                ),
                status_code=302,
            )

    if current_active:
        new_active = 0
        changed_at = datetime.now().strftime("%Y-%m-%d %H:%M")
        c.execute("""
        UPDATE users
        SET is_active=0, disabled_at=?, disabled_reason=?
        WHERE id=? AND company_id=?
        """, (
            changed_at,
            disabled_reason,
            user_id,
            company_id,
        ))
        c.execute("""
        INSERT INTO team_activity (
            company_id, user_id, target_username, actor_username,
            action, details, created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            company_id,
            user_id,
            user["username"],
            username,
            "Пользователь отключён",
            disabled_reason,
            changed_at,
        ))
    else:
        new_active = 1
        changed_at = datetime.now().strftime("%Y-%m-%d %H:%M")
        c.execute("""
        UPDATE users
        SET is_active=1, disabled_at=NULL, disabled_reason=NULL
        WHERE id=? AND company_id=?
        """, (user_id, company_id))
        c.execute("""
        INSERT INTO team_activity (
            company_id, user_id, target_username, actor_username,
            action, details, created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            company_id,
            user_id,
            user["username"],
            username,
            "Пользователь включён",
            "Доступ восстановлен",
            changed_at,
        ))

    conn.commit()
    conn.close()

    run_automation_event(
        company_id,
        "worker_status_changed",
        "worker",
        user_id,
        (
            f"Сотрудник {user['username']} "
            f"{'включён' if new_active else 'отключён'}"
        ),
        f"/workers/{user_id}",
    )

    if new_active:
        limit_warning = record_user_limit_warning(
            company_id,
            username,
            user_id,
            user["username"],
        )

        if limit_warning:
            run_automation_event(
                company_id,
                "company_user_limit_warning",
                "worker",
                user_id,
                (
                    f"Включён пользователь {user['username']}, "
                    f"но {limit_warning['usage']['status'].lower()}"
                ),
                "/billing",
            )
            return RedirectResponse(
                "/workers?status_updated=1&limit_warning=1",
                status_code=302,
            )

    return RedirectResponse("/workers?status_updated=1", status_code=302)


@router.post("/workers/{user_id}/delete")
async def delete_team_user(request: Request, user_id: int):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role != "boss":
        return RedirectResponse("/workers?error=only_boss", status_code=302)

    current_company_id = get_user_company_id(username)
    conn = connect()
    c = conn.cursor()

    user = c.execute("""
    SELECT *
    FROM users
    WHERE id=? AND company_id=?
    """, (user_id, current_company_id)).fetchone()

    if not user:
        conn.close()
        return RedirectResponse("/workers", status_code=302)

    if user["username"] == username or user["role"] == "boss":
        conn.close()
        return RedirectResponse("/workers?error=cannot_delete_boss", status_code=302)

    current_active = 1 if user["is_active"] is None else int(user["is_active"])

    if user["role"] == "worker":
        worker_params = worker_task_params(user["username"])
        active_task_count = c.execute(f"""
        SELECT COUNT(*)
        FROM tasks
        WHERE company_id=?
          AND archived=0
          AND status NOT IN ('Завершено', 'Отменено')
          AND {worker_task_condition()}
        """, [current_company_id, *worker_params]).fetchone()[0]

        if active_task_count:
            conn.close()
            return RedirectResponse(
                (
                    "/workers?error=active_tasks"
                    f"&count={active_task_count}"
                ),
                status_code=302,
            )

    if current_active:
        conn.close()
        return RedirectResponse(
            "/workers?error=disable_before_delete",
            status_code=302,
        )

    if user["role"] == "worker":
        task_history_count = c.execute(f"""
        SELECT COUNT(*)
        FROM tasks
        WHERE company_id=?
          AND {worker_task_condition()}
        """, [current_company_id, *worker_params]).fetchone()[0]
        recurring_count = c.execute(f"""
        SELECT COUNT(*)
        FROM recurring_jobs
        WHERE company_id=?
          AND {worker_task_condition()}
        """, [current_company_id, *worker_params]).fetchone()[0]
        payout_count = c.execute("""
        SELECT COUNT(*)
        FROM payroll_payouts
        WHERE company_id=? AND worker_id=?
        """, (current_company_id, user_id)).fetchone()[0]
        history_count = (
            task_history_count
            + recurring_count
            + payout_count
        )

        if history_count:
            conn.close()
            return RedirectResponse(
                (
                    "/workers?error=user_has_history"
                    f"&count={history_count}"
                ),
                status_code=302,
            )

    c.execute("""
    INSERT INTO team_activity (
        company_id, user_id, target_username, actor_username,
        action, details, created_at
    )
    VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        current_company_id,
        user_id,
        user["username"],
        username,
        "Пользователь удалён",
        "Роль: " + (
            "Менеджер" if user["role"] == "manager" else "Исполнитель"
        ),
        datetime.now().strftime("%Y-%m-%d %H:%M"),
    ))

    c.execute("""
    DELETE FROM worker_unavailability
    WHERE worker_id=? AND company_id=?
    """, (user_id, current_company_id))

    c.execute("""
    DELETE FROM users
    WHERE id=? AND company_id=?
    """, (user_id, current_company_id))

    conn.commit()
    conn.close()

    run_automation_event(
        current_company_id,
        "worker_deleted",
        "worker",
        user_id,
        f"Сотрудник удалён: {user['username']}",
        "/workers",
    )

    return RedirectResponse("/workers?deleted=1", status_code=302)
