"""AI insights and AI assistant routes."""

import csv
import io
from datetime import datetime, timedelta

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response

from app.database import connect
from app.deps import get_role, get_user, get_user_company_id
from app.services.common import (
    build_dashboard_links,
    build_settings_links,
    get_company_features,
    get_company_settings,
    require_feature,
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


def log_ai_assistant_event(*args, **kwargs):
    return _main_attr("log_ai_assistant_event")(*args, **kwargs)


def create_ai_follow_up_notifications(*args, **kwargs):
    return _main_attr("create_ai_follow_up_notifications")(*args, **kwargs)


def create_ai_follow_up_notifications_for_company(*args, **kwargs):
    return _main_attr("create_ai_follow_up_notifications_for_company")(*args, **kwargs)


def build_owner_ai_assistant_context(*args, **kwargs):
    return _main_attr("build_owner_ai_assistant_context")(*args, **kwargs)


def ensure_ai_digest_automation_rules(*args, **kwargs):
    return _main_attr("ensure_ai_digest_automation_rules")(*args, **kwargs)

@router.get("/ai/insights", response_class=HTMLResponse)
async def ai_insights_page(request: Request):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role not in ("boss", "manager"):
        return RedirectResponse("/", status_code=302)

    company_id = get_user_company_id(username)
    disabled_response = require_feature(company_id, "ai_insights")

    if disabled_response:
        return disabled_response

    settings = get_company_settings(company_id)

    conn = connect()
    c = conn.cursor()

    overdue_tasks = c.execute("""
    SELECT COUNT(*)
    FROM tasks
    WHERE company_id=?
      AND archived=0
      AND status!='Завершено'
      AND task_date < date('now')
    """, (company_id,)).fetchone()[0]

    unpaid_total = c.execute("""
    SELECT COALESCE(SUM(price), 0)
    FROM tasks
    WHERE company_id=?
      AND archived=0
      AND payment_status!='Оплачено'
    """, (company_id,)).fetchone()[0]

    low_margin_clients = c.execute("""
    SELECT
        client,
        COUNT(*) as tasks_count,
        COALESCE(SUM(price), 0) as revenue
    FROM tasks
    WHERE company_id=?
      AND archived=0
    GROUP BY client
    HAVING COALESCE(SUM(price), 0) > 0
    ORDER BY revenue ASC
    LIMIT 5
    """, (company_id,)).fetchall()

    worker_rows = c.execute("""
    SELECT username
    FROM users
    WHERE company_id=?
      AND role='worker'
    ORDER BY username
    """, (company_id,)).fetchall()

    weak_workers = []

    for worker_row in worker_rows:
        worker_name = worker_row["username"]
        worker_condition = worker_task_condition()
        worker_params = worker_task_params(worker_name)

        completed_count = c.execute(f"""
        SELECT COUNT(*)
        FROM tasks
        WHERE company_id=?
          AND archived=0
          AND status='Завершено'
          AND {worker_condition}
        """, [company_id] + worker_params).fetchone()[0]

        active_count = c.execute(f"""
        SELECT COUNT(*)
        FROM tasks
        WHERE company_id=?
          AND archived=0
          AND status!='Завершено'
          AND {worker_condition}
        """, [company_id] + worker_params).fetchone()[0]

        weak_workers.append({
            "username": worker_name,
            "completed_count": completed_count,
            "active_count": active_count
        })

    weak_workers.sort(key=lambda row: (row["completed_count"], -row["active_count"]))

    insights = []

    if overdue_tasks:
        insights.append({
            "level": "danger",
            "title": "Есть риск по просрочкам",
            "message": f"Просрочено {overdue_tasks} {settings['task_label'] or 'задач'}. Рекомендуется проверить ответственных и сроки."
        })

    if unpaid_total:
        insights.append({
            "level": "warning",
            "title": "Есть риск неоплаты",
            "message": f"Неоплаченная сумма: ₽{round(float(unpaid_total or 0), 1)}. Рекомендуется запустить напоминания клиентам."
        })

    if weak_workers:
        weakest_worker = weak_workers[0]
        insights.append({
            "level": "info",
            "title": "Сотрудник требует внимания",
            "message": f"{settings['worker_label'] or 'Сотрудник'} {weakest_worker['username']} имеет мало завершённых задач: {weakest_worker['completed_count']}."
        })

    if low_margin_clients:
        client = low_margin_clients[0]
        insights.append({
            "level": "info",
            "title": "Клиент с низкой выручкой",
            "message": f"{settings['client_label'] or 'Клиент'} {client['client'] or 'Не указан'} принёс ₽{round(float(client['revenue'] or 0), 1)}."
        })

    if not insights:
        insights.append({
            "level": "success",
            "title": "Критичных рисков не найдено",
            "message": "Сейчас система не видит явных проблем по просрочкам, оплатам и сотрудникам."
        })

    risk_score = 0

    risk_score += overdue_tasks * 10

    if unpaid_total:
        risk_score += min(int(float(unpaid_total) / 1000), 40)

    if weak_workers:
        weakest_worker = weak_workers[0]
        if weakest_worker["completed_count"] == 0:
            risk_score += 20

    if risk_score > 100:
        risk_score = 100

    if risk_score >= 70:
        risk_level = "danger"
        risk_title = "Высокий риск"
    elif risk_score >= 40:
        risk_level = "warning"
        risk_title = "Средний риск"
    else:
        risk_level = "success"
        risk_title = "Низкий риск"

    weekly_summary = []

    weekly_summary.append(f"За неделю система видит {overdue_tasks} просроченных {settings['task_label'] or 'задач'}.")

    if unpaid_total:
        weekly_summary.append(f"Неоплаченная сумма составляет ₽{round(float(unpaid_total or 0), 1)}.")

    if weak_workers:
        weekly_summary.append(f"Требует внимания {settings['worker_label'] or 'сотрудник'}: {weak_workers[0]['username']}.")

    weekly_summary.append(f"Общий уровень риска: {risk_title} ({risk_score}/100).")

    conn.close()

    return templates.TemplateResponse(
        request,
        "ai_insights.html",
        {
            "request": request,
            "username": username,
            "role": role,
            "settings": settings,
            "insights": insights,
            "overdue_tasks": overdue_tasks,
            "unpaid_total": unpaid_total,
            "weak_workers": weak_workers[:5],
            "low_margin_clients": low_margin_clients,
            "risk_score": risk_score,
            "risk_level": risk_level,
            "risk_title": risk_title,
            "weekly_summary": weekly_summary
        }
    )

@router.get("/ai/assistant", response_class=HTMLResponse)
async def ai_assistant_page(
    request: Request,
    note_filter: str = "",
    note_search: str = "",
    event_filter: str = ""
):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role not in ("boss", "manager"):
        return RedirectResponse("/", status_code=302)

    company_id = get_user_company_id(username)
    disabled_response = require_feature(company_id, "ai_insights")

    if disabled_response:
        return disabled_response

    assistant = build_owner_ai_assistant_context(
        company_id,
        note_filter,
        note_search,
        event_filter
    )

    return templates.TemplateResponse(
        request,
        "ai_assistant.html",
        {
            "request": request,
            "username": username,
            "role": role,
            "settings": assistant["settings"],
            "metrics": assistant["metrics"],
            "priorities": assistant["priorities"],
            "next_steps": assistant["next_steps"],
            "overdue_rows": assistant["overdue_rows"],
            "action_history": assistant["action_history"],
            "assistant_notes": assistant["assistant_notes"],
            "ai_events": assistant["ai_events"],
            "selected_note_filter": assistant["selected_note_filter"],
            "selected_note_search": assistant["selected_note_search"],
            "selected_event_filter": assistant["selected_event_filter"],
            "completed_notes": assistant["completed_notes"],
            "features": get_company_features(company_id)
        }
    )


@router.get("/ai/assistant/events/export")
async def ai_assistant_events_export(request: Request, event_filter: str = ""):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role not in ("boss", "manager"):
        return RedirectResponse("/", status_code=302)

    company_id = get_user_company_id(username)
    disabled_response = require_feature(company_id, "ai_insights")

    if disabled_response:
        return disabled_response

    selected_event_filter = event_filter if event_filter in (
        "created",
        "notification_sent",
        "postponed",
        "done"
    ) else ""
    event_filter_sql = ""
    event_params = [company_id]

    if selected_event_filter:
        event_filter_sql = "AND action=?"
        event_params.append(selected_event_filter)

    conn = connect()
    c = conn.cursor()

    events = c.execute(f"""
    SELECT *
    FROM ai_assistant_events
    WHERE company_id=?
      {event_filter_sql}
    ORDER BY id DESC
    LIMIT 500
    """, event_params).fetchall()

    conn.close()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Дата", "Автор", "Действие", "Номер заметки", "Детали"])

    for event in events:
        writer.writerow([
            event["created_at"],
            event["username"],
            event["action"],
            event["note_id"],
            event["details"],
        ])

    content = output.getvalue()
    output.close()

    return Response(
        content,
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f"attachment; filename=ai_assistant_events_{selected_event_filter or 'all'}.csv"
        }
    )


@router.post("/ai/assistant/notes")
async def add_ai_assistant_note(request: Request):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role not in ("boss", "manager"):
        return RedirectResponse("/", status_code=302)

    company_id = get_user_company_id(username)
    disabled_response = require_feature(company_id, "ai_insights")

    if disabled_response:
        return disabled_response

    form = await request.form()
    note = str(form.get("note") or "").strip()
    priority = str(form.get("priority") or "normal").strip()
    follow_up_date = str(form.get("follow_up_date") or "").strip()

    if priority not in ("urgent", "normal", "later"):
        priority = "normal"

    if follow_up_date:
        try:
            datetime.strptime(follow_up_date, "%Y-%m-%d")
        except Exception:
            follow_up_date = ""

    if not note:
        return RedirectResponse("/ai/assistant?note_error=empty", status_code=302)

    conn = connect()
    c = conn.cursor()

    c.execute("""
    INSERT INTO ai_assistant_notes (
        company_id, username, note, priority, follow_up_date, created_at
    )
    VALUES (?, ?, ?, ?, ?, ?)
    """, (
        company_id,
        username,
        note,
        priority,
        follow_up_date,
        datetime.now().strftime("%Y-%m-%d %H:%M")
    ))

    conn.commit()
    note_id = c.lastrowid
    conn.close()

    log_ai_assistant_event(
        company_id,
        note_id,
        username,
        "created",
        note
    )

    run_automation_event(
        company_id,
        "ai_note_created",
        "ai_note",
        note_id,
        f"ИИ-заметка создана: {note[:120]}",
        "/ai/assistant",
    )

    return RedirectResponse("/ai/assistant?note_created=1", status_code=302)


@router.post("/ai/assistant/notes/{note_id}/done")
async def complete_ai_assistant_note(request: Request, note_id: int):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role not in ("boss", "manager"):
        return RedirectResponse("/", status_code=302)

    company_id = get_user_company_id(username)
    disabled_response = require_feature(company_id, "ai_insights")

    if disabled_response:
        return disabled_response

    conn = connect()
    c = conn.cursor()

    c.execute("""
    UPDATE ai_assistant_notes
    SET is_done=1,
        done_by=?,
        done_at=?
    WHERE id=?
      AND company_id=?
    """, (
        username,
        datetime.now().strftime("%Y-%m-%d %H:%M"),
        note_id,
        company_id
    ))

    conn.commit()
    conn.close()

    log_ai_assistant_event(
        company_id,
        note_id,
        username,
        "done",
        "ИИ-заметка выполнена"
    )

    run_automation_event(
        company_id,
        "ai_note_done",
        "ai_note",
        note_id,
        f"ИИ-заметка выполнена #{note_id}",
        "/ai/assistant",
    )

    return RedirectResponse("/ai/assistant?note_done=1", status_code=302)


@router.post("/ai/assistant/notes/{note_id}/postpone")
async def postpone_ai_assistant_note(request: Request, note_id: int):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role not in ("boss", "manager"):
        return RedirectResponse("/", status_code=302)

    company_id = get_user_company_id(username)
    disabled_response = require_feature(company_id, "ai_insights")

    if disabled_response:
        return disabled_response

    form = await request.form()
    days = str(form.get("days") or "1").strip()

    if days not in ("1", "7"):
        days = "1"

    next_date = (datetime.now() + timedelta(days=int(days))).strftime("%Y-%m-%d")

    conn = connect()
    c = conn.cursor()

    c.execute("""
    UPDATE ai_assistant_notes
    SET follow_up_date=?
    WHERE id=?
      AND company_id=?
      AND COALESCE(is_done, 0)=0
    """, (
        next_date,
        note_id,
        company_id
    ))

    conn.commit()
    conn.close()

    log_ai_assistant_event(
        company_id,
        note_id,
        username,
        "postponed",
        f"Контроль перенесён на {next_date}"
    )

    run_automation_event(
        company_id,
        "ai_note_postponed",
        "ai_note",
        note_id,
        f"ИИ-заметка перенесена на {next_date}",
        "/ai/assistant",
    )

    return RedirectResponse("/ai/assistant?note_postponed=1", status_code=302)


@router.post("/ai/assistant/follow-ups/notify")
async def notify_ai_assistant_follow_ups(request: Request):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role not in ("boss", "manager"):
        return RedirectResponse("/", status_code=302)

    company_id = get_user_company_id(username)
    disabled_response = require_feature(company_id, "ai_insights")

    if disabled_response:
        return disabled_response

    disabled_response = require_feature(company_id, "notifications")

    if disabled_response:
        return disabled_response

    created_count = create_ai_follow_up_notifications(company_id, username)

    if created_count:
        run_automation_event(
            company_id,
            "ai_follow_up_notifications_sent",
            "company",
            company_id,
            f"ИИ-контроль отправил уведомления: {created_count}",
            "/ai/assistant",
        )

    return RedirectResponse(
        f"/ai/assistant?follow_up_notifications={created_count}",
        status_code=302
    )


@router.post("/ai/assistant/setup-digests")
async def setup_ai_assistant_digest_rules(request: Request):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role not in ("boss", "manager"):
        return RedirectResponse("/", status_code=302)

    company_id = get_user_company_id(username)
    disabled_response = require_feature(company_id, "ai_insights")

    if disabled_response:
        return disabled_response

    disabled_response = require_feature(company_id, "automation")

    if disabled_response:
        return disabled_response

    created_count = ensure_ai_digest_automation_rules(company_id, username)

    if created_count:
        run_automation_event(
            company_id,
            "ai_digest_rules_created",
            "company",
            company_id,
            f"Правила ИИ-сводок настроены: {created_count}",
            "/ai/assistant",
        )

    return RedirectResponse(f"/ai/assistant?digest_rules={created_count}", status_code=302)


@router.post("/ai/insights/digest")
async def create_ai_insights_digest(request: Request):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role not in ("boss", "manager"):
        return RedirectResponse("/", status_code=302)

    company_id = get_user_company_id(username)
    disabled_response = require_feature(company_id, "ai_insights")

    if disabled_response:
        return disabled_response

    settings = get_company_settings(company_id)

    conn = connect()
    c = conn.cursor()

    overdue_tasks = c.execute("""
    SELECT COUNT(*)
    FROM tasks
    WHERE company_id=?
      AND archived=0
      AND status!='Завершено'
      AND task_date < date('now')
    """, (company_id,)).fetchone()[0]

    unpaid_total = c.execute("""
    SELECT COALESCE(SUM(price), 0)
    FROM tasks
    WHERE company_id=?
      AND archived=0
      AND payment_status!='Оплачено'
    """, (company_id,)).fetchone()[0]

    message_lines = [
        "ИИ-сводка по бизнесу",
        f"Просроченные {settings['task_label'] or 'задачи'}: {overdue_tasks}",
        f"Неоплаченная сумма: ₽{round(float(unpaid_total or 0), 1)}"
    ]

    if overdue_tasks:
        message_lines.append("Рекомендация: проверьте ответственных и сроки.")

    if unpaid_total:
        message_lines.append("Рекомендация: запустите напоминания по оплатам.")

    digest_message = "\\n".join(message_lines)

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
        username,
        "🤖 ИИ-сводка",
        digest_message,
        "/ai/insights",
        datetime.now().strftime("%Y-%m-%d %H:%M")
    ))

    conn.commit()
    conn.close()

    run_automation_event(
        company_id,
        "ai_insights_digest_created",
        "company",
        company_id,
        "Ручная ИИ-сводка создана",
        "/ai/insights",
    )

    return RedirectResponse("/ai/insights?digest=1", status_code=302)

