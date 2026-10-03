"""Calendar, dispatch, day plan and conflict routes."""

from datetime import datetime, timedelta

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response

from app.database import connect
from app.deps import (
    get_role,
    get_user,
    get_user_company_id,
    update_last_seen,
)
from app.services.common import (
    build_dashboard_links,
    create_notification,
    format_task_workers,
    get_company_features,
    get_company_settings,
    get_task_worker_chat_ids,
    get_task_worker_names,
    require_feature,
    role_label,
    task_has_worker,
    worker_task_condition,
    worker_task_params,
)
from app.templating import templates

router = APIRouter()


import json
from urllib.parse import urlencode

from app.database import begin_locked_transaction
from app.deps import SESSION_COOKIE_NAME, sign_session_value
from app.services.common import can_access_task, has_feature
from app.services.day_plan_publication import (
    REMINDER_COOLDOWN_MINUTES,
    build_day_plan_snapshot,
    build_day_publication_state,
    build_week_publication_summary,
)
from app.services.dispatch_board import build_dispatch_board
from app.services.schedule_conflicts import detect_schedule_conflicts
from app.services.smart_scheduling import (
    add_time_slots_to_recommendations,
    build_scheduling_recommendations,
)
from app.services.daily_schedule import (
    SLOT_STEP,
    WORKDAY_END,
    WORKDAY_START,
    build_daily_auto_plan,
    build_daily_conflict_repair_plan,
    build_daily_schedule,
    build_day_readiness,
    find_time_conflicts,
    format_time_value,
    list_common_time_slots,
    normalize_time_window,
    parse_time_value,
    task_duration_minutes,
)


def _main_attr(name):
    from app import main

    return getattr(main, name)


def get_company_schedule_conflicts(*args, **kwargs):
    return _main_attr("get_company_schedule_conflicts")(*args, **kwargs)


def _build_company_dispatch_plan(*args, **kwargs):
    return _main_attr("_build_company_dispatch_plan")(*args, **kwargs)


def _get_dispatch_date_suggestions(*args, **kwargs):
    return _main_attr("_get_dispatch_date_suggestions")(*args, **kwargs)


def get_calendar_incident_policy(*args, **kwargs):
    return _main_attr("get_calendar_incident_policy")(*args, **kwargs)


def parse_calendar_incident_datetime(*args, **kwargs):
    return _main_attr("parse_calendar_incident_datetime")(*args, **kwargs)


def format_calendar_incident_age(*args, **kwargs):
    return _main_attr("format_calendar_incident_age")(*args, **kwargs)


def get_worker_unavailability(*args, **kwargs):
    return _main_attr("get_worker_unavailability")(*args, **kwargs)


def run_automation_event(*args, **kwargs):
    from app.main import run_automation_event as _impl

    return _impl(*args, **kwargs)


def send_message(*args, **kwargs):
    from app.main import send_message as _impl

    return _impl(*args, **kwargs)


def send_message_to_chat(*args, **kwargs):
    from app.main import send_message_to_chat as _impl

    return _impl(*args, **kwargs)

@router.get("/calendar/dispatch", response_class=HTMLResponse)
async def calendar_dispatch_page(
    request: Request,
    week_start: str = "",
    worker: str = "",
    status: str = "",
):
    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role not in ("boss", "manager"):
        return RedirectResponse("/", status_code=302)

    company_id = get_user_company_id(username)
    disabled_response = require_feature(company_id, "calendar")

    if disabled_response:
        return disabled_response

    calendar_settings = get_company_settings(company_id)
    try:
        week_anchor = datetime.strptime(
            str(week_start or datetime.now().strftime("%Y-%m-%d")),
            "%Y-%m-%d",
        ).date()
    except Exception:
        week_anchor = datetime.now().date()

    board_week_start = week_anchor - timedelta(days=week_anchor.weekday())
    board_week_end = board_week_start + timedelta(days=6)
    selected_week_start = board_week_start.strftime("%Y-%m-%d")
    selected_week_end = board_week_end.strftime("%Y-%m-%d")
    selected_status = (
        status if status in ("Новая", "В работе") else ""
    )
    conn = connect()
    c = conn.cursor()
    worker_rows = c.execute("""
    SELECT username, daily_capacity
    FROM users
    WHERE company_id=?
      AND role='worker'
      AND COALESCE(is_active, 1)=1
    ORDER BY username
    """, (company_id,)).fetchall()
    worker_names = [row["username"] for row in worker_rows]
    selected_worker = worker if worker in worker_names else ""
    worker_capacities = {
        row["username"]: max(1, int(row["daily_capacity"] or 3))
        for row in worker_rows
    }
    all_tasks = c.execute("""
    SELECT *
    FROM tasks
    WHERE company_id=?
      AND archived=0
      AND status NOT IN ('Завершено', 'Отменено')
      AND (
          task_date IS NULL
          OR task_date=''
          OR substr(task_date, 1, 10) BETWEEN ? AND ?
      )
    ORDER BY
      CASE WHEN task_date IS NULL OR task_date='' THEN 0 ELSE 1 END,
      task_date,
      id
    """, (
        company_id,
        selected_week_start,
        selected_week_end,
    )).fetchall()
    unavailable_dates, unavailable_reasons = get_worker_unavailability(
        c,
        company_id,
        worker_names,
        selected_week_start,
        selected_week_end,
    )
    conflicts = detect_schedule_conflicts(
        tasks=all_tasks,
        worker_capacities=worker_capacities,
        unavailable_dates=unavailable_dates,
        unavailable_reasons=unavailable_reasons,
    )
    conflict_task_ids = {
        conflict["task_id"]
        for conflict in conflicts
    }
    display_tasks = []

    for task in all_tasks:
        task_workers = get_task_worker_names(task)

        if selected_worker and selected_worker not in task_workers:
            continue

        if selected_status and task["status"] != selected_status:
            continue

        display_tasks.append(task)

    day_capacity = {}

    for day_offset in range(7):
        day_date = (
            board_week_start + timedelta(days=day_offset)
        ).strftime("%Y-%m-%d")
        available_capacity = sum(
            capacity
            for worker_name, capacity in worker_capacities.items()
            if day_date not in unavailable_dates.get(worker_name, set())
        )
        assignment_count = sum(
            len(get_task_worker_names(task))
            for task in all_tasks
            if str(task["task_date"] or "")[:10] == day_date
        )
        day_capacity[day_date] = {
            "assignments": assignment_count,
            "capacity": available_capacity,
            "available_slots": max(
                available_capacity - assignment_count,
                0,
            ),
        }

    planning_queue_count = c.execute("""
    SELECT COUNT(*)
    FROM tasks
    WHERE company_id=?
      AND archived=0
      AND status NOT IN ('Завершено', 'Отменено')
      AND (
          task_date IS NULL
          OR task_date=''
          OR (
              TRIM(COALESCE(worker, ''))=''
              AND TRIM(COALESCE(workers, ''))=''
          )
      )
    """, (company_id,)).fetchone()[0]
    week_publication_tasks = c.execute("""
    SELECT *
    FROM tasks
    WHERE company_id=?
      AND archived=0
      AND status!='Отменено'
      AND substr(task_date, 1, 10) BETWEEN ? AND ?
    ORDER BY task_date, id
    """, (
        company_id,
        selected_week_start,
        selected_week_end,
    )).fetchall()
    publication_rows = c.execute("""
    SELECT *
    FROM calendar_day_publications
    WHERE company_id=?
      AND plan_date BETWEEN ? AND ?
    ORDER BY plan_date
    """, (
        company_id,
        selected_week_start,
        selected_week_end,
    )).fetchall()
    acknowledgement_rows = c.execute("""
    SELECT
        acknowledgement.plan_date,
        acknowledgement.revision,
        acknowledgement.username,
        acknowledgement.acknowledged_at
    FROM calendar_day_acknowledgements AS acknowledgement
    JOIN calendar_day_publications AS publication
      ON publication.company_id=acknowledgement.company_id
     AND publication.plan_date=acknowledgement.plan_date
     AND publication.revision=acknowledgement.revision
    WHERE acknowledgement.company_id=?
      AND acknowledgement.plan_date BETWEEN ? AND ?
    ORDER BY acknowledgement.plan_date, acknowledgement.username
    """, (
        company_id,
        selected_week_start,
        selected_week_end,
    )).fetchall()
    reminder_rows = c.execute("""
    SELECT
        reminder.plan_date,
        reminder.revision,
        reminder.username,
        MAX(reminder.reminded_at) AS reminded_at
    FROM calendar_day_ack_reminders AS reminder
    JOIN calendar_day_publications AS publication
      ON publication.company_id=reminder.company_id
     AND publication.plan_date=reminder.plan_date
     AND publication.revision=reminder.revision
    WHERE reminder.company_id=?
      AND reminder.plan_date BETWEEN ? AND ?
    GROUP BY
        reminder.plan_date,
        reminder.revision,
        reminder.username
    ORDER BY reminder.plan_date, reminder.username
    """, (
        company_id,
        selected_week_start,
        selected_week_end,
    )).fetchall()
    week_plan_run_rows = c.execute("""
    SELECT *
    FROM calendar_plan_operation_runs
    WHERE company_id=?
      AND week_start=?
    ORDER BY id DESC
    LIMIT 8
    """, (
        company_id,
        selected_week_start,
    )).fetchall()
    scheduler_status_row = c.execute("""
    SELECT *
    FROM calendar_plan_scheduler_status
    WHERE company_id=?
    """, (company_id,)).fetchone()
    scheduler_run_rows = c.execute("""
    SELECT *
    FROM calendar_plan_scheduler_runs
    WHERE company_id=?
    ORDER BY id DESC
    LIMIT 8
    """, (company_id,)).fetchall()
    scheduler_run_summary_row = c.execute("""
    SELECT
        COUNT(*) AS total_runs,
        SUM(CASE WHEN status='done' THEN 1 ELSE 0 END) AS done_runs,
        SUM(CASE WHEN status='skipped' THEN 1 ELSE 0 END) AS skipped_runs,
        SUM(
            CASE WHEN status IN ('error', 'locked')
                 THEN 1 ELSE 0 END
        ) AS problem_runs,
        SUM(changed_days) AS changed_days,
        SUM(notifications_sent) AS notifications_sent
    FROM (
        SELECT *
        FROM calendar_plan_scheduler_runs
        WHERE company_id=?
        ORDER BY id DESC
        LIMIT 30
    )
    """, (company_id,)).fetchone()
    scheduler_incident_rows = c.execute("""
    SELECT *
    FROM calendar_scheduler_incident_events
    WHERE company_id=?
    ORDER BY id DESC
    LIMIT 8
    """, (company_id,)).fetchall()
    conn.close()
    week_plan_runs = []
    calendar_scheduler_runs = []
    calendar_scheduler_incident_events = []

    for row in week_plan_run_rows:
        item = dict(row)
        item["action_label"] = (
            "Публикация готовых планов"
            if item["action"] == "publish_ready"
            else "Напоминания команде"
        )
        item["source_label"] = (
            "По расписанию"
            if item["source"] == "scheduler"
            else (
                "Запуск владельцем"
                if item["source"] == "manual_run"
                else "Вручную"
            )
        )
        week_plan_runs.append(item)

    scheduler_status_labels = {
        "done": ("Выполнено", "done"),
        "skipped": ("Пропущено", "skipped"),
        "locked": ("Занято", "locked"),
        "error": ("Ошибка", "error"),
        "running": ("Выполняется", "running"),
    }

    for row in scheduler_run_rows:
        item = dict(row)
        item["source_label"] = (
            "Вручную"
            if item["source"] == "manual_run"
            else "По расписанию"
        )
        (
            item["status_label"],
            item["status_tone"],
        ) = scheduler_status_labels.get(
            item["status"],
            ("Неизвестно", "skipped"),
        )
        calendar_scheduler_runs.append(item)

    calendar_scheduler_run_summary = {
        key: int(scheduler_run_summary_row[key] or 0)
        for key in (
            "total_runs",
            "done_runs",
            "skipped_runs",
            "problem_runs",
            "changed_days",
            "notifications_sent",
        )
    }
    incident_type_labels = {
        "error": "Ошибка запуска",
        "stuck": "Зависший запуск",
        "stale": "Cron не запускался",
    }
    incident_event_labels = {
        "opened": "Открыт",
        "acknowledged": "Принят в работу",
        "escalated": "Передан платформе",
        "recovery_overdue": "Восстановление просрочено",
        "recovery_started": "Запущено восстановление",
        "recovery_failed": "Восстановление не выполнено",
        "note": "Рабочая заметка",
        "reassigned": "Ответственный изменён",
        "recovered": "Восстановлен",
    }

    for row in scheduler_incident_rows:
        item = dict(row)
        item["incident_type_label"] = incident_type_labels.get(
            item["incident_type"],
            "Инцидент",
        )
        item["event_type_label"] = incident_event_labels.get(
            item["event_type"],
            "Событие",
        )
        calendar_scheduler_incident_events.append(item)

    automation_enabled = bool(
        calendar_settings["calendar_auto_publish"]
        or calendar_settings["calendar_auto_remind"]
    )
    calendar_incident_policy = get_calendar_incident_policy()

    calendar_scheduler_incident = {
        "active": False,
        "type": "",
        "type_label": "",
        "message": "",
        "started_at": "",
        "alerted_at": "",
        "acknowledged_at": "",
        "acknowledged_by": "",
        "assigned_at": "",
        "assigned_to": "",
        "assigned_by": "",
    }

    if not automation_enabled:
        calendar_scheduler_status = {
            "tone": "disabled",
            "title": "Автоматизация выключена",
            "message": "Включите нужные действия и сохраните настройки.",
            "last_completed_at": "",
        }
    elif not scheduler_status_row:
        calendar_scheduler_status = {
            "tone": "waiting",
            "title": "Ожидает первого запуска",
            "message": "Cron ещё не запускал автоматизацию календаря.",
            "last_completed_at": "",
        }
    else:
        last_completed_at = str(
            scheduler_status_row["last_completed_at"] or ""
        )
        last_status = str(
            scheduler_status_row["last_status"] or "waiting"
        )
        last_source = str(
            scheduler_status_row["last_source"] or "scheduler"
        )
        source_label = (
            "вручную"
            if last_source == "manual_run"
            else "по расписанию"
        )
        triggered_by = str(
            scheduler_status_row["last_triggered_by"] or ""
        )
        trigger_details = source_label

        if triggered_by:
            trigger_details += f", {triggered_by}"

        if last_status == "error":
            calendar_scheduler_status = {
                "tone": "error",
                "title": "Ошибка автоматизации",
                "message": str(
                    scheduler_status_row["last_error"]
                    or "Последний запуск завершился с ошибкой."
                ),
                "last_completed_at": last_completed_at,
            }
        elif last_status == "waiting":
            calendar_scheduler_status = {
                "tone": "waiting",
                "title": "Ожидает рабочего окна",
                "message": (
                    "Последняя проверка выполнена вне настроенного "
                    "времени автоматизации."
                ),
                "last_completed_at": last_completed_at,
            }
        elif last_status == "running":
            last_started_at = str(
                scheduler_status_row["last_started_at"] or ""
            )

            try:
                started_at = datetime.strptime(
                    last_started_at,
                    "%Y-%m-%d %H:%M",
                )
                is_stuck = (
                    datetime.now() - started_at
                    > timedelta(
                        minutes=calendar_incident_policy[
                            "stuck_minutes"
                        ],
                    )
                )
            except ValueError:
                is_stuck = True

            calendar_scheduler_status = {
                "tone": "error" if is_stuck else "waiting",
                "title": (
                    "Запуск не завершён"
                    if is_stuck
                    else "Автоматизация выполняется"
                ),
                "message": (
                    "Проверьте cron и журнал приложения: "
                    "последний запуск не завершился."
                    if is_stuck
                    else (
                        f"Запуск начат: {last_started_at} "
                        f"({trigger_details})."
                    )
                ),
                "last_completed_at": last_started_at,
            }
        else:
            try:
                completed_at = datetime.strptime(
                    last_completed_at,
                    "%Y-%m-%d %H:%M",
                )
                is_stale = (
                    datetime.now() - completed_at
                    > timedelta(
                        hours=calendar_incident_policy[
                            "stale_hours"
                        ],
                    )
                )
            except ValueError:
                is_stale = True

            calendar_scheduler_status = {
                "tone": "stale" if is_stale else "healthy",
                "title": (
                    "Давно не запускалась"
                    if is_stale
                    else "Автоматизация работает"
                ),
                "message": (
                    "Проверьте расписание cron и секрет запуска."
                    if is_stale
                    else (
                        "Последний запуск: "
                        f"{last_completed_at}. "
                        "Изменено дней: "
                        f"{scheduler_status_row['last_changed_days']}. "
                        "Уведомлений: "
                        f"{scheduler_status_row['last_notifications_sent']}. "
                        f"Источник: {trigger_details}."
                    )
                ),
                "last_completed_at": last_completed_at,
            }

        active_incident = str(
            scheduler_status_row["active_incident"] or ""
        )

        if active_incident:
            calendar_scheduler_incident = {
                "active": True,
                "type": active_incident,
                "type_label": incident_type_labels.get(
                    active_incident,
                    "Инцидент",
                ),
                "message": str(
                    scheduler_status_row["incident_message"] or ""
                ),
                "started_at": str(
                    scheduler_status_row["incident_started_at"] or ""
                ),
                "alerted_at": str(
                    scheduler_status_row["last_alerted_at"] or ""
                ),
                "acknowledged_at": str(
                    scheduler_status_row[
                        "incident_acknowledged_at"
                    ] or ""
                ),
                "acknowledged_by": str(
                    scheduler_status_row[
                        "incident_acknowledged_by"
                    ] or ""
                ),
                "assigned_at": str(
                    scheduler_status_row[
                        "incident_assigned_at"
                    ]
                    or scheduler_status_row[
                        "incident_acknowledged_at"
                    ]
                    or ""
                ),
                "assigned_to": str(
                    scheduler_status_row[
                        "incident_assigned_to"
                    ]
                    or scheduler_status_row[
                        "incident_acknowledged_by"
                    ]
                    or ""
                ),
                "assigned_by": str(
                    scheduler_status_row[
                        "incident_assigned_by"
                    ]
                    or scheduler_status_row[
                        "incident_acknowledged_by"
                    ]
                    or ""
                ),
            }
            calendar_scheduler_status = {
                "tone": "error",
                "title": calendar_scheduler_incident["type_label"],
                "message": calendar_scheduler_incident["message"],
                "last_completed_at": (
                    calendar_scheduler_incident["started_at"]
                ),
            }
    week_publication = build_week_publication_summary(
        week_start=board_week_start,
        tasks=week_publication_tasks,
        publications=publication_rows,
        acknowledgements=acknowledgement_rows,
        reminders=reminder_rows,
        active_worker_names=worker_names,
    )
    week_tasks_by_date = {}

    for task in week_publication_tasks:
        task_date = str(task["task_date"] or "")[:10]
        week_tasks_by_date.setdefault(task_date, []).append(task)

    for day in week_publication["days"]:
        day_readiness = build_day_readiness(
            tasks=week_tasks_by_date.get(day["date"], []),
            worker_names=worker_names,
            worker_capacities=worker_capacities,
            unavailable_worker_names={
                worker_name
                for worker_name in worker_names
                if day["date"]
                in unavailable_dates.get(worker_name, set())
            },
        )
        day["readiness_score"] = day_readiness["score"]
        day["readiness_status"] = day_readiness["status"]
        day["can_publish"] = bool(
            day["date"] >= datetime.now().strftime("%Y-%m-%d")
            and day["task_count"]
            and day_readiness["score"] == 100
            and day["state"] != "published"
        )
        day["can_remind"] = bool(
            day["date"] >= datetime.now().strftime("%Y-%m-%d")
            and day["state"] == "published"
            and day["remindable_count"]
        )

    week_publication["summary"]["publishable_days"] = sum(
        1 for day in week_publication["days"] if day["can_publish"]
    )
    week_publication["summary"]["remindable_days"] = sum(
        1 for day in week_publication["days"] if day["can_remind"]
    )
    board_columns = build_dispatch_board(
        tasks=display_tasks,
        week_start=board_week_start,
        conflict_task_ids=conflict_task_ids,
        day_capacity=day_capacity,
    )
    today_value = datetime.now().strftime("%Y-%m-%d")

    for column in board_columns:
        column["is_today"] = column["date"] == today_value
        column["is_past"] = bool(
            column["date"] and column["date"] < today_value
        )

    query_params = {}

    if selected_worker:
        query_params["worker"] = selected_worker

    if selected_status:
        query_params["status"] = selected_status

    def dispatch_week_url(start_date):
        params = {
            "week_start": start_date.strftime("%Y-%m-%d"),
            **query_params,
        }
        return "/calendar/dispatch?" + urlencode(params)

    summary = {
        "tasks": len(display_tasks),
        "backlog": sum(
            1
            for task in display_tasks
            if not str(task["task_date"] or "").strip()
        ),
        "new": sum(
            1 for task in display_tasks
            if task["status"] == "Новая"
        ),
        "in_progress": sum(
            1 for task in display_tasks
            if task["status"] == "В работе"
        ),
        "conflicts": sum(
            1
            for task in display_tasks
            if task["id"] in conflict_task_ids
        ),
    }

    return templates.TemplateResponse(
        request=request,
        name="calendar_dispatch.html",
        context={
            "request": request,
            "username": username,
            "role": role,
            "settings": calendar_settings,
            "workers": worker_rows,
            "board_columns": board_columns,
            "summary": summary,
            "selected_worker": selected_worker,
            "selected_status": selected_status,
            "selected_week_start": selected_week_start,
            "selected_week_end": selected_week_end,
            "planning_queue_count": planning_queue_count,
            "week_publication": week_publication,
            "week_plan_runs": week_plan_runs,
            "calendar_scheduler_runs": calendar_scheduler_runs,
            "calendar_scheduler_run_summary": (
                calendar_scheduler_run_summary
            ),
            "calendar_scheduler_incident": (
                calendar_scheduler_incident
            ),
            "calendar_scheduler_incident_events": (
                calendar_scheduler_incident_events
            ),
            "calendar_auto_publish": bool(
                calendar_settings["calendar_auto_publish"]
            ),
            "calendar_auto_remind": bool(
                calendar_settings["calendar_auto_remind"]
            ),
            "calendar_auto_days_ahead": max(
                0,
                min(
                    14,
                    int(
                        calendar_settings[
                            "calendar_auto_days_ahead"
                        ]
                        if calendar_settings[
                            "calendar_auto_days_ahead"
                        ] is not None
                        else 7
                    ),
                ),
            ),
            "calendar_auto_window_start": str(
                calendar_settings["calendar_auto_window_start"]
                or "00:00"
            ),
            "calendar_auto_window_end": str(
                calendar_settings["calendar_auto_window_end"]
                or "23:59"
            ),
            "calendar_scheduler_status": calendar_scheduler_status,
            "calendar_incident_policy": calendar_incident_policy,
            "previous_week_url": dispatch_week_url(
                board_week_start - timedelta(days=7)
            ),
            "current_week_url": dispatch_week_url(
                datetime.now().date()
                - timedelta(days=datetime.now().date().weekday())
            ),
            "next_week_url": dispatch_week_url(
                board_week_start + timedelta(days=7)
            ),
        },
    )


@router.post("/api/calendar/dispatch/week-plans")
async def api_calendar_dispatch_week_plans(request: Request):
    username = get_user(request)

    if not username:
        return JSONResponse(
            {
                "ok": False,
                "error": "unauthorized",
                "message": "Требуется авторизация.",
            },
            status_code=401,
        )

    if get_role(username) not in ("boss", "manager"):
        return JSONResponse(
            {
                "ok": False,
                "error": "forbidden",
                "message": "Недостаточно прав.",
            },
            status_code=403,
        )

    company_id = get_user_company_id(username)

    if not has_feature(company_id, "calendar"):
        return JSONResponse(
            {
                "ok": False,
                "error": "feature_disabled",
                "message": "Модуль календаря отключён.",
            },
            status_code=403,
        )

    try:
        payload = await request.json()
    except Exception:
        return JSONResponse(
            {
                "ok": False,
                "error": "invalid_json",
                "message": "Не удалось прочитать запрос.",
            },
            status_code=400,
        )

    action = str(payload.get("action") or "").strip()

    if action not in ("publish_ready", "remind_pending"):
        return JSONResponse(
            {
                "ok": False,
                "error": "invalid_action",
                "message": "Неизвестное действие.",
            },
            status_code=400,
        )

    try:
        week_anchor = datetime.strptime(
            str(payload.get("week_start") or "")[:10],
            "%Y-%m-%d",
        ).date()
    except ValueError:
        return JSONResponse(
            {
                "ok": False,
                "error": "invalid_date",
                "message": "Указана некорректная дата недели.",
            },
            status_code=400,
        )

    week_start = week_anchor - timedelta(days=week_anchor.weekday())
    week_end = week_start + timedelta(days=6)
    week_start_value = week_start.strftime("%Y-%m-%d")
    week_end_value = week_end.strftime("%Y-%m-%d")
    today_value = datetime.now().strftime("%Y-%m-%d")
    conn = connect()
    c = conn.cursor()
    worker_rows = c.execute("""
    SELECT username, daily_capacity, telegram_chat_id
    FROM users
    WHERE company_id=?
      AND role='worker'
      AND COALESCE(is_active, 1)=1
    ORDER BY username
    """, (company_id,)).fetchall()
    worker_names = [row["username"] for row in worker_rows]
    worker_capacities = {
        row["username"]: max(1, int(row["daily_capacity"] or 3))
        for row in worker_rows
    }
    active_workers = {
        row["username"]: row for row in worker_rows
    }
    task_rows = c.execute("""
    SELECT *
    FROM tasks
    WHERE company_id=?
      AND archived=0
      AND status!='Отменено'
      AND substr(task_date, 1, 10) BETWEEN ? AND ?
    ORDER BY task_date, id
    """, (
        company_id,
        week_start_value,
        week_end_value,
    )).fetchall()
    tasks_by_date = {}

    for task in task_rows:
        task_date = str(task["task_date"] or "")[:10]
        tasks_by_date.setdefault(task_date, []).append(task)

    publication_rows = c.execute("""
    SELECT *
    FROM calendar_day_publications
    WHERE company_id=?
      AND plan_date BETWEEN ? AND ?
    ORDER BY plan_date
    """, (
        company_id,
        week_start_value,
        week_end_value,
    )).fetchall()
    publication_by_date = {
        row["plan_date"]: row for row in publication_rows
    }
    unavailable_dates, _ = get_worker_unavailability(
        c,
        company_id,
        worker_names,
        week_start_value,
        week_end_value,
    )
    now = datetime.now()
    now_value = now.strftime("%Y-%m-%d %H:%M")
    source = str(
        request.scope.get("state", {}).get(
            "calendar_plan_source",
            "manual",
        )
    )
    if source not in ("scheduler", "manual_run"):
        source = "manual"
    is_automatic_source = source in ("scheduler", "manual_run")
    automatic_date_from = ""
    automatic_date_to = ""

    if is_automatic_source:
        automatic_date_from = str(
            payload.get("date_from") or ""
        )[:10]
        automatic_date_to = str(
            payload.get("date_to") or ""
        )[:10]

        try:
            datetime.strptime(automatic_date_from, "%Y-%m-%d")
            datetime.strptime(automatic_date_to, "%Y-%m-%d")
        except ValueError:
            automatic_date_from = week_start_value
            automatic_date_to = week_end_value

    telegram_messages = []
    items = []

    if action == "publish_ready":
        published_days = 0
        updated_days = 0
        notified_workers = 0

        for offset in range(7):
            selected_date = (
                week_start + timedelta(days=offset)
            ).strftime("%Y-%m-%d")
            tasks = tasks_by_date.get(selected_date, [])
            publication = publication_by_date.get(selected_date)

            if (
                is_automatic_source
                and not (
                    automatic_date_from
                    <= selected_date
                    <= automatic_date_to
                )
            ):
                items.append({
                    "date": selected_date,
                    "status": "skipped",
                    "reason": "Вне горизонта автоматизации",
                })
                continue

            if selected_date < today_value:
                items.append({
                    "date": selected_date,
                    "status": "skipped",
                    "reason": "Прошедший день",
                })
                continue

            if not tasks:
                items.append({
                    "date": selected_date,
                    "status": "skipped",
                    "reason": "Нет заявок",
                })
                continue

            snapshot = build_day_plan_snapshot(tasks)

            if (
                publication
                and str(publication["plan_hash"] or "")
                == snapshot["hash"]
            ):
                items.append({
                    "date": selected_date,
                    "status": "skipped",
                    "reason": "Актуальный план уже опубликован",
                })
                continue

            readiness = build_day_readiness(
                tasks=tasks,
                worker_names=worker_names,
                worker_capacities=worker_capacities,
                unavailable_worker_names={
                    worker_name
                    for worker_name in worker_names
                    if selected_date
                    in unavailable_dates.get(worker_name, set())
                },
            )

            if readiness["score"] != 100:
                items.append({
                    "date": selected_date,
                    "status": "skipped",
                    "reason": "Расписание требует исправления",
                    "readiness_score": readiness["score"],
                })
                continue

            c.execute("""
            INSERT INTO calendar_day_publications (
                company_id, plan_date, plan_hash, task_count,
                worker_count, published_by, published_at, revision
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, 1)
            ON CONFLICT(company_id, plan_date) DO UPDATE SET
                plan_hash=excluded.plan_hash,
                task_count=excluded.task_count,
                worker_count=excluded.worker_count,
                published_by=excluded.published_by,
                published_at=excluded.published_at,
                revision=calendar_day_publications.revision + 1
            """, (
                company_id,
                selected_date,
                snapshot["hash"],
                snapshot["task_count"],
                snapshot["worker_count"],
                username,
                now_value,
            ))
            is_update = publication is not None
            event_title = (
                "План дня обновлён"
                if is_update
                else "План дня опубликован"
            )
            event_message = (
                f"Дата: {selected_date}. "
                f"Заявок: {snapshot['task_count']}. "
                "Откройте маршрут дня перед началом работы."
            )
            day_notified_workers = 0

            for worker_name in snapshot["workers"]:
                worker_row = active_workers.get(worker_name)

                if not worker_row:
                    continue

                c.execute("""
                INSERT INTO notifications (
                    company_id, username, title, message,
                    link, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """, (
                    company_id,
                    worker_name,
                    event_title,
                    event_message,
                    f"/calendar/day?date={selected_date}",
                    now_value,
                ))
                day_notified_workers += 1
                chat_id = str(
                    worker_row["telegram_chat_id"] or ""
                ).strip()

                if chat_id:
                    telegram_messages.append((
                        chat_id,
                        f"{event_title}\n{event_message}",
                    ))

            if is_update:
                updated_days += 1
            else:
                published_days += 1

            notified_workers += day_notified_workers
            items.append({
                "date": selected_date,
                "status": "updated" if is_update else "published",
                "reason": event_title,
                "notified_workers": day_notified_workers,
            })

        summary = {
            "published_days": published_days,
            "updated_days": updated_days,
            "notified_workers": notified_workers,
            "skipped_days": sum(
                1 for item in items if item["status"] == "skipped"
            ),
        }
        changed_days = published_days + updated_days
        message = (
            f"Готовые планы опубликованы: {changed_days}. "
            f"Исполнителей уведомлено: {notified_workers}."
        )
    else:
        acknowledgement_rows = c.execute("""
        SELECT plan_date, revision, username
        FROM calendar_day_acknowledgements
        WHERE company_id=?
          AND plan_date BETWEEN ? AND ?
        """, (
            company_id,
            week_start_value,
            week_end_value,
        )).fetchall()
        acknowledged_by_plan = {}

        for row in acknowledgement_rows:
            key = (row["plan_date"], int(row["revision"] or 0))
            acknowledged_by_plan.setdefault(key, set()).add(
                row["username"]
            )

        reminder_rows = c.execute("""
        SELECT plan_date, revision, username, MAX(reminded_at) AS reminded_at
        FROM calendar_day_ack_reminders
        WHERE company_id=?
          AND plan_date BETWEEN ? AND ?
        GROUP BY plan_date, revision, username
        """, (
            company_id,
            week_start_value,
            week_end_value,
        )).fetchall()
        reminder_by_plan_worker = {
            (
                row["plan_date"],
                int(row["revision"] or 0),
                row["username"],
            ): row["reminded_at"]
            for row in reminder_rows
        }
        scheduler_reminded_workers = {
            (
                row["plan_date"],
                int(row["revision"] or 0),
                row["username"],
            )
            for row in c.execute("""
            SELECT DISTINCT plan_date, revision, username
            FROM calendar_day_ack_reminders
            WHERE company_id=?
              AND plan_date BETWEEN ? AND ?
              AND source IN ('scheduler', 'manual_run')
            """, (
                company_id,
                week_start_value,
                week_end_value,
            )).fetchall()
        }
        cooldown_threshold = now - timedelta(
            minutes=REMINDER_COOLDOWN_MINUTES
        )
        affected_days = 0
        sent_reminders = 0
        cooldown_workers = 0
        inactive_workers = 0
        automatic_skips = 0

        for offset in range(7):
            selected_date = (
                week_start + timedelta(days=offset)
            ).strftime("%Y-%m-%d")
            publication = publication_by_date.get(selected_date)

            if (
                is_automatic_source
                and not (
                    automatic_date_from
                    <= selected_date
                    <= automatic_date_to
                )
            ):
                items.append({
                    "date": selected_date,
                    "status": "skipped",
                    "reason": "Вне горизонта автоматизации",
                })
                continue

            if selected_date < today_value:
                items.append({
                    "date": selected_date,
                    "status": "skipped",
                    "reason": "Прошедший день",
                })
                continue

            if not publication:
                items.append({
                    "date": selected_date,
                    "status": "skipped",
                    "reason": "План не опубликован",
                })
                continue

            tasks = tasks_by_date.get(selected_date, [])
            snapshot = build_day_plan_snapshot(tasks)

            if (
                snapshot["hash"]
                != str(publication["plan_hash"] or "")
            ):
                items.append({
                    "date": selected_date,
                    "status": "skipped",
                    "reason": "План изменён после публикации",
                })
                continue

            revision = int(publication["revision"] or 1)
            acknowledged_workers = acknowledged_by_plan.get(
                (selected_date, revision),
                set(),
            )
            pending_workers = [
                worker_name
                for worker_name in snapshot["workers"]
                if worker_name not in acknowledged_workers
            ]

            if not pending_workers:
                items.append({
                    "date": selected_date,
                    "status": "skipped",
                    "reason": "Все исполнители приняли план",
                })
                continue

            day_sent = 0
            day_cooldown = 0
            day_inactive = 0
            day_automatic_skips = 0

            for worker_name in pending_workers:
                worker_row = active_workers.get(worker_name)

                if not worker_row:
                    day_inactive += 1
                    continue

                reminder_key = (
                    selected_date,
                    revision,
                    worker_name,
                )

                if (
                    is_automatic_source
                    and reminder_key in scheduler_reminded_workers
                ):
                    day_automatic_skips += 1
                    continue

                reminded_at_value = reminder_by_plan_worker.get((
                    selected_date,
                    revision,
                    worker_name,
                ))
                reminded_at = None

                if reminded_at_value:
                    try:
                        reminded_at = datetime.strptime(
                            reminded_at_value,
                            "%Y-%m-%d %H:%M",
                        )
                    except ValueError:
                        reminded_at = None

                if reminded_at and reminded_at > cooldown_threshold:
                    day_cooldown += 1
                    continue

                c.execute("""
                INSERT OR IGNORE INTO calendar_day_ack_reminders (
                    company_id, plan_date, revision, username,
                    reminded_by, reminded_at, source
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (
                    company_id,
                    selected_date,
                    revision,
                    worker_name,
                    username,
                    now_value,
                    source,
                ))

                if is_automatic_source and c.rowcount == 0:
                    day_automatic_skips += 1
                    continue

                notification_title = "Подтвердите план дня"
                notification_message = (
                    f"План на {selected_date}, версия {revision}. "
                    "Откройте маршрут и нажмите «Принять план»."
                )
                c.execute("""
                INSERT INTO notifications (
                    company_id, username, title, message,
                    link, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """, (
                    company_id,
                    worker_name,
                    notification_title,
                    notification_message,
                    f"/calendar/day?date={selected_date}",
                    now_value,
                ))
                day_sent += 1
                chat_id = str(
                    worker_row["telegram_chat_id"] or ""
                ).strip()

                if chat_id:
                    telegram_messages.append((
                        chat_id,
                        (
                            f"{notification_title}\n"
                            f"Дата: {selected_date}\n"
                            f"Версия плана: {revision}\n"
                            "Откройте маршрут дня и подтвердите получение."
                        ),
                    ))

            if day_sent:
                affected_days += 1

            sent_reminders += day_sent
            cooldown_workers += day_cooldown
            inactive_workers += day_inactive
            automatic_skips += day_automatic_skips
            items.append({
                "date": selected_date,
                "status": "reminded" if day_sent else "skipped",
                "reason": (
                    f"Отправлено напоминаний: {day_sent}"
                    if day_sent
                    else "Нет доступных получателей"
                ),
                "sent": day_sent,
                "cooldown": day_cooldown,
                "inactive": day_inactive,
                "automatic_skips": day_automatic_skips,
            })

        summary = {
            "affected_days": affected_days,
            "sent_reminders": sent_reminders,
            "cooldown_workers": cooldown_workers,
            "inactive_workers": inactive_workers,
            "automatic_skips": automatic_skips,
            "skipped_days": sum(
                1 for item in items if item["status"] == "skipped"
            ),
        }
        message = (
            f"Напоминания отправлены: {sent_reminders}. "
            f"Дней затронуто: {affected_days}."
        )

    changed_days = (
        summary["published_days"] + summary["updated_days"]
        if action == "publish_ready"
        else summary["affected_days"]
    )
    notifications_sent = (
        summary["notified_workers"]
        if action == "publish_ready"
        else summary["sent_reminders"]
    )
    operation_run_id = 0

    if source == "manual" or changed_days or notifications_sent:
        c.execute("""
        INSERT INTO calendar_plan_operation_runs (
            company_id, week_start, week_end, action, source,
            actor_username, changed_days, notifications_sent,
            skipped_days, result_json, created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            company_id,
            week_start_value,
            week_end_value,
            action,
            source,
            username,
            changed_days,
            notifications_sent,
            summary["skipped_days"],
            json.dumps(
                {
                    "summary": summary,
                    "items": items,
                    "message": message,
                },
                ensure_ascii=False,
            ),
            now_value,
        ))
        operation_run_id = c.lastrowid
    conn.commit()
    conn.close()

    for chat_id, message_text in telegram_messages:
        try:
            send_message_to_chat(chat_id, message_text)
        except Exception:
            pass

    return {
        "ok": True,
        "action": action,
        "week_start": week_start_value,
        "week_end": week_end_value,
        "summary": summary,
        "items": items,
        "message": message,
        "source": source,
        "operation_run_id": operation_run_id,
    }


@router.post("/api/calendar/dispatch/automation-settings")
async def api_calendar_dispatch_automation_settings(request: Request):
    username = get_user(request)

    if not username:
        return JSONResponse(
            {
                "ok": False,
                "error": "unauthorized",
                "message": "Требуется авторизация.",
            },
            status_code=401,
        )

    if get_role(username) != "boss":
        return JSONResponse(
            {
                "ok": False,
                "error": "forbidden",
                "message": "Настройки автоматизации доступны владельцу.",
            },
            status_code=403,
        )

    company_id = get_user_company_id(username)

    if not has_feature(company_id, "calendar"):
        return JSONResponse(
            {
                "ok": False,
                "error": "feature_disabled",
                "message": "Модуль календаря отключён.",
            },
            status_code=403,
        )

    try:
        payload = await request.json()
    except Exception:
        return JSONResponse(
            {
                "ok": False,
                "error": "invalid_json",
                "message": "Не удалось прочитать запрос.",
            },
            status_code=400,
        )

    auto_publish = 1 if payload.get("auto_publish") else 0
    auto_remind = 1 if payload.get("auto_remind") else 0

    try:
        auto_days_ahead = int(
            payload.get("days_ahead", 7)
        )
    except (TypeError, ValueError):
        auto_days_ahead = -1

    if auto_days_ahead < 0 or auto_days_ahead > 14:
        return JSONResponse(
            {
                "ok": False,
                "error": "invalid_days_ahead",
                "message": (
                    "Горизонт автоматизации должен быть "
                    "от 0 до 14 дней."
                ),
            },
            status_code=400,
        )

    auto_window_start = str(
        payload.get("window_start") or "00:00"
    ).strip()
    auto_window_end = str(
        payload.get("window_end") or "23:59"
    ).strip()

    for value in (auto_window_start, auto_window_end):
        try:
            datetime.strptime(value, "%H:%M")
        except ValueError:
            return JSONResponse(
                {
                    "ok": False,
                    "error": "invalid_time_window",
                    "message": (
                        "Время автоматизации должно быть "
                        "в формате ЧЧ:ММ."
                    ),
                },
                status_code=400,
            )

    get_company_settings(company_id)
    conn = connect()
    c = conn.cursor()
    c.execute("""
    UPDATE company_settings
    SET calendar_auto_publish=?,
        calendar_auto_remind=?,
        calendar_auto_days_ahead=?,
        calendar_auto_window_start=?,
        calendar_auto_window_end=?,
        updated_at=?
    WHERE company_id=?
    """, (
        auto_publish,
        auto_remind,
        auto_days_ahead,
        auto_window_start,
        auto_window_end,
        datetime.now().strftime("%Y-%m-%d %H:%M"),
        company_id,
    ))
    conn.commit()
    conn.close()

    return {
        "ok": True,
        "auto_publish": bool(auto_publish),
        "auto_remind": bool(auto_remind),
        "days_ahead": auto_days_ahead,
        "window_start": auto_window_start,
        "window_end": auto_window_end,
        "message": "Настройки автоматизации сохранены.",
    }


def calendar_automation_time_allowed(
    current_time,
    window_start,
    window_end,
):
    current_value = current_time.strftime("%H:%M")

    if window_start <= window_end:
        return window_start <= current_value <= window_end

    return (
        current_value >= window_start
        or current_value <= window_end
    )


async def run_calendar_plan_scheduler(*args, **kwargs):
    return await _main_attr("run_calendar_plan_scheduler")(*args, **kwargs)


@router.post("/api/calendar/dispatch/automation-run")
async def api_calendar_dispatch_automation_run(request: Request):
    username = get_user(request)

    if not username:
        return JSONResponse(
            {
                "ok": False,
                "error": "unauthorized",
                "message": "Требуется авторизация.",
            },
            status_code=401,
        )

    if get_role(username) != "boss":
        return JSONResponse(
            {
                "ok": False,
                "error": "forbidden",
                "message": "Ручной запуск доступен владельцу.",
            },
            status_code=403,
        )

    company_id = get_user_company_id(username)

    if not has_feature(company_id, "calendar"):
        return JSONResponse(
            {
                "ok": False,
                "error": "feature_disabled",
                "message": "Модуль календаря отключён.",
            },
            status_code=403,
        )

    result = await run_calendar_plan_scheduler(
        company_id,
        actor_username=username,
        source="manual_run",
    )

    if result["error"]:
        error_messages = {
            "automation_disabled": (
                "Сначала включите автопубликацию "
                "или автонапоминания."
            ),
            "actor_not_found": "Не найден активный владелец компании.",
            "scheduler_already_running": (
                "Автоматизация уже выполняется. "
                "Дождитесь завершения текущего запуска."
            ),
        }
        return JSONResponse(
            {
                "ok": False,
                "error": result["error"],
                "message": error_messages.get(
                    result["error"],
                    "Автоматизация завершилась с ошибкой.",
                ),
                "result": result,
            },
            status_code=409,
        )

    changed_days = int(result["changed_days"] or 0)
    notifications_sent = int(result["notifications_sent"] or 0)
    message = (
        "Автоматизация выполнена. "
        f"Изменено дней: {changed_days}. "
        f"Уведомлений: {notifications_sent}."
        if changed_days or notifications_sent
        else "Проверка завершена: новых действий нет."
    )

    return {
        "ok": True,
        "message": message,
        "result": result,
    }


def log_calendar_scheduler_incident_event(*args, **kwargs):
    return _main_attr("log_calendar_scheduler_incident_event")(*args, **kwargs)


def trim_calendar_scheduler_runs(*args, **kwargs):
    return _main_attr("trim_calendar_scheduler_runs")(*args, **kwargs)


def acknowledge_calendar_scheduler_incident(*args, **kwargs):
    return _main_attr("acknowledge_calendar_scheduler_incident")(*args, **kwargs)


@router.post("/api/calendar/dispatch/incident/acknowledge")
async def api_calendar_dispatch_incident_acknowledge(request: Request):
    username = get_user(request)

    if not username:
        return JSONResponse(
            {
                "ok": False,
                "error": "unauthorized",
                "message": "Требуется авторизация.",
            },
            status_code=401,
        )

    if get_role(username) != "boss":
        return JSONResponse(
            {
                "ok": False,
                "error": "forbidden",
                "message": "Подтвердить инцидент может владелец.",
            },
            status_code=403,
        )

    company_id = get_user_company_id(username)

    if not has_feature(company_id, "calendar"):
        return JSONResponse(
            {
                "ok": False,
                "error": "feature_disabled",
                "message": "Модуль календаря отключён.",
            },
            status_code=403,
        )

    result = acknowledge_calendar_scheduler_incident(
        company_id,
        username,
    )

    if not result["ok"]:
        return JSONResponse(result, status_code=409)

    conn = connect()
    c = conn.cursor()
    c.execute("""
    UPDATE notifications
    SET is_read=1
    WHERE company_id=?
      AND username=?
      AND link='/calendar/dispatch'
      AND is_read=0
    """, (
        company_id,
        username,
    ))
    conn.commit()
    conn.close()

    return result


@router.get("/calendar/day", response_class=HTMLResponse)
async def calendar_day_route_page(
    request: Request,
    date: str = "",
    worker: str = "",
):
    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role not in ("boss", "manager", "worker"):
        return RedirectResponse("/", status_code=302)

    company_id = get_user_company_id(username)
    disabled_response = require_feature(company_id, "calendar")

    if disabled_response:
        return disabled_response

    settings = get_company_settings(company_id)

    try:
        selected_day = datetime.strptime(
            str(date or datetime.now().strftime("%Y-%m-%d")),
            "%Y-%m-%d",
        ).date()
    except ValueError:
        selected_day = datetime.now().date()

    selected_date = selected_day.strftime("%Y-%m-%d")
    conn = connect()
    c = conn.cursor()
    worker_rows = c.execute("""
    SELECT username, full_name, daily_capacity
    FROM users
    WHERE company_id=?
      AND role='worker'
      AND COALESCE(is_active, 1)=1
    ORDER BY COALESCE(NULLIF(full_name, ''), username), username
    """, (company_id,)).fetchall()
    worker_names = [row["username"] for row in worker_rows]
    worker_capacities = {
        row["username"]: max(1, int(row["daily_capacity"] or 3))
        for row in worker_rows
    }

    if role == "worker":
        selected_worker = username
        visible_worker_names = [username]
    else:
        selected_worker = worker if worker in worker_names else ""
        visible_worker_names = (
            [selected_worker] if selected_worker else worker_names
        )

    query = """
    SELECT *
    FROM tasks
    WHERE company_id=?
      AND archived=0
      AND status!='Отменено'
      AND task_date LIKE ?
    """
    params = [company_id, f"{selected_date}%"]
    publication_tasks = c.execute(query + " ORDER BY id", params).fetchall()
    publication = c.execute("""
    SELECT *
    FROM calendar_day_publications
    WHERE company_id=? AND plan_date=?
    """, (company_id, selected_date)).fetchone()
    publication_revision = (
        int(publication["revision"] or 0) if publication else 0
    )
    acknowledgement_rows = c.execute("""
    SELECT username, acknowledged_at
    FROM calendar_day_acknowledgements
    WHERE company_id=? AND plan_date=? AND revision=?
    ORDER BY username
    """, (
        company_id,
        selected_date,
        publication_revision,
    )).fetchall() if publication_revision else []
    reminder_rows = c.execute("""
    SELECT username, MAX(reminded_at) AS reminded_at
    FROM calendar_day_ack_reminders
    WHERE company_id=? AND plan_date=? AND revision=?
    GROUP BY username
    ORDER BY username
    """, (
        company_id,
        selected_date,
        publication_revision,
    )).fetchall() if publication_revision else []

    if selected_worker:
        query += f" AND {worker_task_condition()}"
        params.extend(worker_task_params(selected_worker))

    query += """
    ORDER BY
      CASE WHEN time_from IS NULL OR time_from='' THEN 1 ELSE 0 END,
      time_from,
      id
    """
    tasks = c.execute(query, params).fetchall()
    unavailable_dates, _ = get_worker_unavailability(
        c,
        company_id,
        worker_names,
        selected_date,
        selected_date,
    )
    conn.close()
    schedule = build_daily_schedule(
        tasks,
        visible_worker_names,
        worker_capacities=worker_capacities,
        unavailable_worker_names={
            worker_name
            for worker_name in visible_worker_names
            if selected_date
            in unavailable_dates.get(worker_name, set())
        },
    )
    day_auto_plan = {
        "items": [],
        "unscheduled": [],
        "summary": {
            "eligible": 0,
            "planned": 0,
            "reassignments": 0,
            "unscheduled": 0,
            "limited": 0,
        },
    }
    day_conflict_repair = {
        "items": [],
        "unscheduled": [],
        "summary": {
            "conflict_tasks": 0,
            "planned": 0,
            "unscheduled": 0,
            "limited": 0,
        },
    }

    can_auto_manage_day = (
        role in ("boss", "manager")
        and not selected_worker
        and selected_day >= datetime.now().date()
    )

    if can_auto_manage_day:
        day_auto_plan = build_daily_auto_plan(
            tasks=tasks,
            worker_names=worker_names,
            worker_capacities=worker_capacities,
            unavailable_worker_names={
                worker_name
                for worker_name in worker_names
                if selected_date
                in unavailable_dates.get(worker_name, set())
            },
            target_date=selected_date,
        )
        day_conflict_repair = build_daily_conflict_repair_plan(
            tasks=tasks,
            worker_names=worker_names,
            unavailable_worker_names={
                worker_name
                for worker_name in worker_names
                if selected_date
                in unavailable_dates.get(worker_name, set())
            },
            target_date=selected_date,
        )
    day_readiness = build_day_readiness(
        tasks=tasks,
        worker_names=worker_names,
        worker_capacities=worker_capacities,
        unavailable_worker_names={
            worker_name
            for worker_name in worker_names
            if selected_date
            in unavailable_dates.get(worker_name, set())
        },
    )
    day_publication = build_day_publication_state(
        publication,
        publication_tasks,
        acknowledgements=acknowledgement_rows,
        reminders=reminder_rows,
        active_worker_names=worker_names,
        current_username=username,
    )

    if not can_auto_manage_day:
        for issue in day_readiness["issues"]:
            if issue["target"] in ("#auto-plan", "#conflict-repair"):
                issue["target"] = "#day-routes"

    def day_url(day_value):
        params = {"date": day_value.strftime("%Y-%m-%d")}

        if selected_worker and role != "worker":
            params["worker"] = selected_worker

        return "/calendar/day?" + urlencode(params)

    return templates.TemplateResponse(
        request=request,
        name="calendar_day_route.html",
        context={
            "request": request,
            "username": username,
            "role": role,
            "workers": worker_rows,
            "selected_worker": selected_worker,
            "selected_date": selected_date,
            "schedule": schedule,
            "day_readiness": day_readiness,
            "day_publication": day_publication,
            "can_publish_day": can_auto_manage_day,
            "day_auto_plan": day_auto_plan,
            "day_conflict_repair": day_conflict_repair,
            "settings": settings,
            "previous_day_url": day_url(
                selected_day - timedelta(days=1)
            ),
            "today_day_url": day_url(datetime.now().date()),
            "next_day_url": day_url(
                selected_day + timedelta(days=1)
            ),
        },
    )


@router.post("/api/calendar/day/publication")
async def api_calendar_day_publication(request: Request):
    username = get_user(request)

    if not username:
        return JSONResponse(
            {
                "ok": False,
                "error": "unauthorized",
                "message": "Требуется авторизация.",
            },
            status_code=401,
        )

    role = get_role(username)

    if role not in ("boss", "manager"):
        return JSONResponse(
            {
                "ok": False,
                "error": "forbidden",
                "message": "Недостаточно прав.",
            },
            status_code=403,
        )

    company_id = get_user_company_id(username)

    if not has_feature(company_id, "calendar"):
        return JSONResponse(
            {
                "ok": False,
                "error": "feature_disabled",
                "message": "Модуль календаря отключён.",
            },
            status_code=403,
        )

    try:
        payload = await request.json()
    except Exception:
        return JSONResponse(
            {
                "ok": False,
                "error": "invalid_json",
                "message": "Не удалось прочитать запрос.",
            },
            status_code=400,
        )

    selected_date = str(payload.get("date") or "").strip()[:10]
    action = str(payload.get("action") or "publish").strip()

    try:
        selected_day = datetime.strptime(
            selected_date,
            "%Y-%m-%d",
        ).date()
    except ValueError:
        return JSONResponse(
            {
                "ok": False,
                "error": "invalid_date",
                "message": "Указана некорректная дата.",
            },
            status_code=400,
        )

    if selected_day < datetime.now().date():
        return JSONResponse(
            {
                "ok": False,
                "error": "past_date",
                "message": "Нельзя изменять публикацию прошедшего дня.",
            },
            status_code=400,
        )

    if action not in ("publish", "unpublish"):
        return JSONResponse(
            {
                "ok": False,
                "error": "invalid_action",
                "message": "Неизвестное действие.",
            },
            status_code=400,
        )

    conn = connect()
    c = conn.cursor()
    tasks = c.execute("""
    SELECT *
    FROM tasks
    WHERE company_id=?
      AND archived=0
      AND status!='Отменено'
      AND task_date LIKE ?
    ORDER BY id
    """, (company_id, f"{selected_date}%")).fetchall()
    publication = c.execute("""
    SELECT *
    FROM calendar_day_publications
    WHERE company_id=? AND plan_date=?
    """, (company_id, selected_date)).fetchone()

    if action == "unpublish":
        if not publication:
            conn.close()
            return JSONResponse(
                {
                    "ok": False,
                    "error": "not_published",
                    "message": "План дня ещё не опубликован.",
                },
                status_code=404,
            )

        c.execute("""
        DELETE FROM calendar_day_publications
        WHERE company_id=? AND plan_date=?
        """, (company_id, selected_date))
        c.execute("""
        DELETE FROM calendar_day_acknowledgements
        WHERE company_id=? AND plan_date=?
        """, (company_id, selected_date))
        c.execute("""
        DELETE FROM calendar_day_ack_reminders
        WHERE company_id=? AND plan_date=?
        """, (company_id, selected_date))
        event_title = "План дня снят с публикации"
        event_message = (
            f"План на {selected_date} будет опубликован повторно "
            "после уточнения."
        )
        response_message = "Публикация плана снята."
        response_state = "draft"
    else:
        if not tasks:
            conn.close()
            return JSONResponse(
                {
                    "ok": False,
                    "error": "empty_day",
                    "message": "На выбранный день нет заявок.",
                },
                status_code=400,
            )

        worker_rows = c.execute("""
        SELECT username, daily_capacity, telegram_chat_id
        FROM users
        WHERE company_id=?
          AND role='worker'
          AND COALESCE(is_active, 1)=1
        ORDER BY username
        """, (company_id,)).fetchall()
        worker_names = [row["username"] for row in worker_rows]
        worker_capacities = {
            row["username"]: max(1, int(row["daily_capacity"] or 3))
            for row in worker_rows
        }
        unavailable_dates, _ = get_worker_unavailability(
            c,
            company_id,
            worker_names,
            selected_date,
            selected_date,
        )
        readiness = build_day_readiness(
            tasks=tasks,
            worker_names=worker_names,
            worker_capacities=worker_capacities,
            unavailable_worker_names={
                worker_name
                for worker_name in worker_names
                if selected_date
                in unavailable_dates.get(worker_name, set())
            },
        )

        if readiness["score"] != 100:
            conn.close()
            return JSONResponse(
                {
                    "ok": False,
                    "error": "day_not_ready",
                    "message": (
                        "Сначала устраните проблемы в расписании."
                    ),
                    "score": readiness["score"],
                    "issues": readiness["issues"],
                },
                status_code=409,
            )

        snapshot = build_day_plan_snapshot(tasks)
        now_value = datetime.now().strftime("%Y-%m-%d %H:%M")
        c.execute("""
        INSERT INTO calendar_day_publications (
            company_id, plan_date, plan_hash, task_count,
            worker_count, published_by, published_at, revision
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, 1)
        ON CONFLICT(company_id, plan_date) DO UPDATE SET
            plan_hash=excluded.plan_hash,
            task_count=excluded.task_count,
            worker_count=excluded.worker_count,
            published_by=excluded.published_by,
            published_at=excluded.published_at,
            revision=calendar_day_publications.revision + 1
        """, (
            company_id,
            selected_date,
            snapshot["hash"],
            snapshot["task_count"],
            snapshot["worker_count"],
            username,
            now_value,
        ))
        is_update = publication is not None
        event_title = (
            "План дня обновлён"
            if is_update
            else "План дня опубликован"
        )
        event_message = (
            f"Дата: {selected_date}. "
            f"Заявок: {snapshot['task_count']}. "
            "Откройте маршрут дня перед началом работы."
        )
        response_message = event_title + "."
        response_state = "published"

    assigned_workers = sorted({
        worker_name
        for task in tasks
        for worker_name in get_task_worker_names(task)
    })
    active_worker_rows = c.execute("""
    SELECT username, telegram_chat_id
    FROM users
    WHERE company_id=?
      AND role='worker'
      AND COALESCE(is_active, 1)=1
    """, (company_id,)).fetchall()
    active_workers = {
        row["username"]: row
        for row in active_worker_rows
    }
    now_value = datetime.now().strftime("%Y-%m-%d %H:%M")
    telegram_messages = []

    for worker_name in assigned_workers:
        worker_row = active_workers.get(worker_name)

        if not worker_row:
            continue

        c.execute("""
        INSERT INTO notifications (
            company_id, username, title, message, link, created_at
        )
        VALUES (?, ?, ?, ?, ?, ?)
        """, (
            company_id,
            worker_name,
            event_title,
            event_message,
            f"/calendar/day?date={selected_date}",
            now_value,
        ))
        chat_id = str(worker_row["telegram_chat_id"] or "").strip()

        if chat_id:
            telegram_messages.append((
                chat_id,
                f"{event_title}\n{event_message}",
            ))

    conn.commit()
    conn.close()

    for chat_id, message in telegram_messages:
        try:
            send_message_to_chat(chat_id, message)
        except Exception:
            pass

    return {
        "ok": True,
        "state": response_state,
        "date": selected_date,
        "message": response_message,
        "notified_workers": len([
            worker_name
            for worker_name in assigned_workers
            if worker_name in active_workers
        ]),
    }


@router.post("/api/calendar/day/acknowledge")
async def api_calendar_day_acknowledge(request: Request):
    username = get_user(request)

    if not username:
        return JSONResponse(
            {
                "ok": False,
                "error": "unauthorized",
                "message": "Требуется авторизация.",
            },
            status_code=401,
        )

    role = get_role(username)

    if role != "worker":
        return JSONResponse(
            {
                "ok": False,
                "error": "forbidden",
                "message": "Подтверждение доступно исполнителям.",
            },
            status_code=403,
        )

    company_id = get_user_company_id(username)

    if not has_feature(company_id, "calendar"):
        return JSONResponse(
            {
                "ok": False,
                "error": "feature_disabled",
                "message": "Модуль календаря отключён.",
            },
            status_code=403,
        )

    try:
        payload = await request.json()
    except Exception:
        return JSONResponse(
            {
                "ok": False,
                "error": "invalid_json",
                "message": "Не удалось прочитать запрос.",
            },
            status_code=400,
        )

    selected_date = str(payload.get("date") or "").strip()[:10]

    try:
        selected_day = datetime.strptime(
            selected_date,
            "%Y-%m-%d",
        ).date()
    except ValueError:
        return JSONResponse(
            {
                "ok": False,
                "error": "invalid_date",
                "message": "Указана некорректная дата.",
            },
            status_code=400,
        )

    if selected_day < datetime.now().date():
        return JSONResponse(
            {
                "ok": False,
                "error": "past_date",
                "message": "Нельзя подтверждать прошедший план.",
            },
            status_code=400,
        )

    conn = connect()
    c = conn.cursor()
    publication = c.execute("""
    SELECT *
    FROM calendar_day_publications
    WHERE company_id=? AND plan_date=?
    """, (company_id, selected_date)).fetchone()

    if not publication:
        conn.close()
        return JSONResponse(
            {
                "ok": False,
                "error": "not_published",
                "message": "План дня ещё не опубликован.",
            },
            status_code=404,
        )

    tasks = c.execute("""
    SELECT *
    FROM tasks
    WHERE company_id=?
      AND archived=0
      AND status!='Отменено'
      AND task_date LIKE ?
    ORDER BY id
    """, (company_id, f"{selected_date}%")).fetchall()
    snapshot = build_day_plan_snapshot(tasks)

    if snapshot["hash"] != str(publication["plan_hash"] or ""):
        conn.close()
        return JSONResponse(
            {
                "ok": False,
                "error": "plan_changed",
                "message": (
                    "План изменён. Дождитесь новой публикации."
                ),
            },
            status_code=409,
        )

    if username not in snapshot["workers"]:
        conn.close()
        return JSONResponse(
            {
                "ok": False,
                "error": "not_assigned",
                "message": "На этот день у вас нет назначенных заявок.",
            },
            status_code=403,
        )

    active_worker = c.execute("""
    SELECT id
    FROM users
    WHERE company_id=?
      AND username=?
      AND role='worker'
      AND COALESCE(is_active, 1)=1
    """, (company_id, username)).fetchone()

    if not active_worker:
        conn.close()
        return JSONResponse(
            {
                "ok": False,
                "error": "inactive_worker",
                "message": "Учётная запись исполнителя отключена.",
            },
            status_code=403,
        )

    revision = int(publication["revision"] or 1)
    acknowledged_at = datetime.now().strftime("%Y-%m-%d %H:%M")
    c.execute("""
    INSERT INTO calendar_day_acknowledgements (
        company_id, plan_date, revision, username, acknowledged_at
    )
    VALUES (?, ?, ?, ?, ?)
    ON CONFLICT(company_id, plan_date, revision, username)
    DO UPDATE SET acknowledged_at=excluded.acknowledged_at
    """, (
        company_id,
        selected_date,
        revision,
        username,
        acknowledged_at,
    ))
    c.execute("""
    UPDATE notifications
    SET is_read=1
    WHERE company_id=?
      AND username=?
      AND link=?
      AND title IN (
          'План дня опубликован',
          'План дня обновлён',
          'Подтвердите план дня'
      )
    """, (
        company_id,
        username,
        f"/calendar/day?date={selected_date}",
    ))
    conn.commit()
    conn.close()

    return {
        "ok": True,
        "date": selected_date,
        "revision": revision,
        "acknowledged_at": acknowledged_at,
        "message": "План дня принят.",
    }


@router.post("/api/calendar/day/acknowledgements/remind")
async def api_calendar_day_acknowledgements_remind(request: Request):
    username = get_user(request)

    if not username:
        return JSONResponse(
            {
                "ok": False,
                "error": "unauthorized",
                "message": "Требуется авторизация.",
            },
            status_code=401,
        )

    role = get_role(username)

    if role not in ("boss", "manager"):
        return JSONResponse(
            {
                "ok": False,
                "error": "forbidden",
                "message": "Недостаточно прав.",
            },
            status_code=403,
        )

    company_id = get_user_company_id(username)

    if not has_feature(company_id, "calendar"):
        return JSONResponse(
            {
                "ok": False,
                "error": "feature_disabled",
                "message": "Модуль календаря отключён.",
            },
            status_code=403,
        )

    try:
        payload = await request.json()
    except Exception:
        return JSONResponse(
            {
                "ok": False,
                "error": "invalid_json",
                "message": "Не удалось прочитать запрос.",
            },
            status_code=400,
        )

    selected_date = str(payload.get("date") or "").strip()[:10]

    try:
        selected_day = datetime.strptime(
            selected_date,
            "%Y-%m-%d",
        ).date()
    except ValueError:
        return JSONResponse(
            {
                "ok": False,
                "error": "invalid_date",
                "message": "Указана некорректная дата.",
            },
            status_code=400,
        )

    if selected_day < datetime.now().date():
        return JSONResponse(
            {
                "ok": False,
                "error": "past_date",
                "message": "Нельзя напоминать по прошедшему плану.",
            },
            status_code=400,
        )

    conn = connect()
    c = conn.cursor()
    publication = c.execute("""
    SELECT *
    FROM calendar_day_publications
    WHERE company_id=? AND plan_date=?
    """, (company_id, selected_date)).fetchone()

    if not publication:
        conn.close()
        return JSONResponse(
            {
                "ok": False,
                "error": "not_published",
                "message": "План дня ещё не опубликован.",
            },
            status_code=404,
        )

    tasks = c.execute("""
    SELECT *
    FROM tasks
    WHERE company_id=?
      AND archived=0
      AND status!='Отменено'
      AND task_date LIKE ?
    ORDER BY id
    """, (company_id, f"{selected_date}%")).fetchall()
    snapshot = build_day_plan_snapshot(tasks)

    if snapshot["hash"] != str(publication["plan_hash"] or ""):
        conn.close()
        return JSONResponse(
            {
                "ok": False,
                "error": "plan_changed",
                "message": (
                    "План изменён. Сначала обновите публикацию."
                ),
            },
            status_code=409,
        )

    revision = int(publication["revision"] or 1)
    acknowledged_workers = {
        row["username"]
        for row in c.execute("""
        SELECT username
        FROM calendar_day_acknowledgements
        WHERE company_id=? AND plan_date=? AND revision=?
        """, (
            company_id,
            selected_date,
            revision,
        )).fetchall()
    }
    pending_workers = [
        worker_name
        for worker_name in snapshot["workers"]
        if worker_name not in acknowledged_workers
    ]

    if not pending_workers:
        conn.close()
        return {
            "ok": True,
            "date": selected_date,
            "revision": revision,
            "sent": [],
            "cooldown": [],
            "inactive": [],
            "message": "Все исполнители уже подтвердили план.",
        }

    placeholders = ",".join("?" for _ in pending_workers)
    active_worker_rows = c.execute(f"""
    SELECT username, telegram_chat_id
    FROM users
    WHERE company_id=?
      AND role='worker'
      AND COALESCE(is_active, 1)=1
      AND username IN ({placeholders})
    """, [company_id, *pending_workers]).fetchall()
    active_workers = {
        row["username"]: row for row in active_worker_rows
    }
    now = datetime.now()
    now_value = now.strftime("%Y-%m-%d %H:%M")
    cooldown_threshold = now - timedelta(
        minutes=REMINDER_COOLDOWN_MINUTES
    )
    sent_workers = []
    cooldown_workers = []
    inactive_workers = []
    telegram_messages = []

    for worker_name in pending_workers:
        worker_row = active_workers.get(worker_name)

        if not worker_row:
            inactive_workers.append(worker_name)
            continue

        last_reminder = c.execute("""
        SELECT reminded_at
        FROM calendar_day_ack_reminders
        WHERE company_id=?
          AND plan_date=?
          AND revision=?
          AND username=?
        ORDER BY id DESC
        LIMIT 1
        """, (
            company_id,
            selected_date,
            revision,
            worker_name,
        )).fetchone()

        if last_reminder and last_reminder["reminded_at"]:
            try:
                reminded_at = datetime.strptime(
                    last_reminder["reminded_at"],
                    "%Y-%m-%d %H:%M",
                )
            except ValueError:
                reminded_at = None

            if reminded_at and reminded_at > cooldown_threshold:
                cooldown_workers.append(worker_name)
                continue

        c.execute("""
        INSERT INTO calendar_day_ack_reminders (
            company_id, plan_date, revision, username,
            reminded_by, reminded_at, source
        )
        VALUES (?, ?, ?, ?, ?, ?, 'manual')
        """, (
            company_id,
            selected_date,
            revision,
            worker_name,
            username,
            now_value,
        ))
        notification_title = "Подтвердите план дня"
        notification_message = (
            f"План на {selected_date}, версия {revision}. "
            "Откройте маршрут и нажмите «Принять план»."
        )
        c.execute("""
        INSERT INTO notifications (
            company_id, username, title, message, link, created_at
        )
        VALUES (?, ?, ?, ?, ?, ?)
        """, (
            company_id,
            worker_name,
            notification_title,
            notification_message,
            f"/calendar/day?date={selected_date}",
            now_value,
        ))
        sent_workers.append(worker_name)
        chat_id = str(worker_row["telegram_chat_id"] or "").strip()

        if chat_id:
            telegram_messages.append((
                chat_id,
                (
                    f"{notification_title}\n"
                    f"Дата: {selected_date}\n"
                    f"Версия плана: {revision}\n"
                    "Откройте маршрут дня и подтвердите получение."
                ),
            ))

    conn.commit()
    conn.close()

    for chat_id, message in telegram_messages:
        try:
            send_message_to_chat(chat_id, message)
        except Exception:
            pass

    if sent_workers:
        message = f"Напоминания отправлены: {len(sent_workers)}."
    elif cooldown_workers:
        message = (
            "Напоминания уже отправлялись недавно. "
            f"Повтор доступен через {REMINDER_COOLDOWN_MINUTES} минут."
        )
    else:
        message = "Нет активных исполнителей для напоминания."

    return {
        "ok": True,
        "date": selected_date,
        "revision": revision,
        "sent": sent_workers,
        "cooldown": cooldown_workers,
        "inactive": inactive_workers,
        "message": message,
        "cooldown_minutes": REMINDER_COOLDOWN_MINUTES,
    }


@router.post("/api/calendar/day/move-time")
async def api_calendar_day_move_time(request: Request):
    username = get_user(request)

    if not username:
        return JSONResponse(
            {"ok": False, "error": "unauthorized"},
            status_code=401,
        )

    role = get_role(username)

    if role not in ("boss", "manager"):
        return JSONResponse(
            {"ok": False, "error": "forbidden"},
            status_code=403,
        )

    company_id = get_user_company_id(username)

    if not has_feature(company_id, "calendar"):
        return JSONResponse(
            {"ok": False, "error": "feature_disabled"},
            status_code=403,
        )

    try:
        payload = await request.json()
    except Exception:
        return JSONResponse(
            {"ok": False, "error": "invalid_json"},
            status_code=400,
        )

    try:
        task_id = int(payload.get("task_id") or 0)
    except Exception:
        task_id = 0

    target_date = str(payload.get("target_date") or "").strip()[:10]
    target_time_from = str(
        payload.get("target_time_from") or ""
    ).strip()[:5]
    expected_date = str(
        payload.get("expected_date") or ""
    ).strip()[:10]
    expected_time_from = str(
        payload.get("expected_time_from") or ""
    ).strip()[:5]
    expected_time_to = str(
        payload.get("expected_time_to") or ""
    ).strip()[:5]

    try:
        parsed_target_date = datetime.strptime(
            target_date,
            "%Y-%m-%d",
        ).date()
    except Exception:
        return JSONResponse(
            {"ok": False, "error": "invalid_date"},
            status_code=400,
        )

    if parsed_target_date < datetime.now().date():
        return JSONResponse(
            {"ok": False, "error": "past_date"},
            status_code=400,
        )

    target_start = parse_time_value(target_time_from)

    if target_start is None or target_start % SLOT_STEP:
        return JSONResponse(
            {"ok": False, "error": "invalid_time"},
            status_code=400,
        )

    conn = connect()
    c = conn.cursor()
    task = c.execute("""
    SELECT *
    FROM tasks
    WHERE id=? AND company_id=?
    """, (task_id, company_id)).fetchone()

    if not task:
        conn.close()
        return JSONResponse(
            {"ok": False, "error": "not_found"},
            status_code=404,
        )

    if (
        int(task["archived"] or 0) == 1
        or task["status"] in ("Завершено", "Отменено")
    ):
        conn.close()
        return JSONResponse(
            {"ok": False, "error": "task_closed"},
            status_code=409,
        )

    current_date = str(task["task_date"] or "")[:10]
    current_time_from = str(task["time_from"] or "")[:5]
    current_time_to = str(task["time_to"] or "")[:5]

    if (
        current_date != expected_date
        or current_time_from != expected_time_from
        or current_time_to != expected_time_to
    ):
        conn.close()
        return JSONResponse(
            {
                "ok": False,
                "error": "stale",
                "current_date": current_date,
                "current_time_from": current_time_from,
                "current_time_to": current_time_to,
            },
            status_code=409,
        )

    duration_minutes = task_duration_minutes(task)
    target_end = target_start + duration_minutes

    if target_start < WORKDAY_START or target_end > WORKDAY_END:
        conn.close()
        return JSONResponse(
            {
                "ok": False,
                "error": "outside_workday",
                "workday_from": format_time_value(WORKDAY_START),
                "workday_to": format_time_value(WORKDAY_END),
            },
            status_code=400,
        )

    target_time_from = format_time_value(target_start)
    target_time_to = format_time_value(target_end)

    if (
        current_date == target_date
        and current_time_from == target_time_from
        and current_time_to == target_time_to
    ):
        conn.close()
        return {
            "ok": True,
            "changed": False,
            "task_id": task_id,
            "target_date": target_date,
            "target_time_from": target_time_from,
            "target_time_to": target_time_to,
        }

    task_workers = get_task_worker_names(task)

    if not task_workers:
        conn.close()
        return JSONResponse(
            {"ok": False, "error": "unassigned"},
            status_code=409,
        )

    placeholders = ",".join("?" for _ in task_workers)
    worker_rows = c.execute(f"""
    SELECT username, daily_capacity, telegram_chat_id
    FROM users
    WHERE company_id=?
      AND role='worker'
      AND COALESCE(is_active, 1)=1
      AND username IN ({placeholders})
    """, [company_id, *task_workers]).fetchall()
    workers_by_name = {
        row["username"]: row
        for row in worker_rows
    }

    inactive_worker = next(
        (
            worker_name
            for worker_name in task_workers
            if worker_name not in workers_by_name
        ),
        "",
    )

    if inactive_worker:
        conn.close()
        return JSONResponse(
            {
                "ok": False,
                "error": "inactive_worker",
                "worker": inactive_worker,
            },
            status_code=409,
        )

    unavailable_dates, unavailable_reasons = get_worker_unavailability(
        c,
        company_id,
        task_workers,
        target_date,
        target_date,
    )
    unavailable_worker = next(
        (
            worker_name
            for worker_name in task_workers
            if target_date in unavailable_dates.get(worker_name, set())
        ),
        "",
    )

    if unavailable_worker:
        reason = unavailable_reasons.get(
            (unavailable_worker, target_date),
            "",
        )
        conn.close()
        return JSONResponse(
            {
                "ok": False,
                "error": "worker_unavailable",
                "worker": unavailable_worker,
                "reason": reason,
            },
            status_code=409,
        )

    if target_date != current_date:
        for worker_name in task_workers:
            active_count = c.execute(f"""
            SELECT COUNT(*)
            FROM tasks
            WHERE company_id=?
              AND id!=?
              AND archived=0
              AND status NOT IN ('Завершено', 'Отменено')
              AND task_date LIKE ?
              AND {worker_task_condition()}
            """, [
                company_id,
                task_id,
                f"{target_date}%",
                *worker_task_params(worker_name),
            ]).fetchone()[0]
            daily_capacity = max(
                1,
                int(workers_by_name[worker_name]["daily_capacity"] or 3),
            )

            if active_count >= daily_capacity:
                conn.close()
                return JSONResponse(
                    {
                        "ok": False,
                        "error": "capacity_reached",
                        "worker": worker_name,
                        "active_count": active_count,
                        "daily_capacity": daily_capacity,
                    },
                    status_code=409,
                )

    day_tasks = c.execute("""
    SELECT *
    FROM tasks
    WHERE company_id=?
      AND id!=?
      AND archived=0
      AND status NOT IN ('Завершено', 'Отменено')
      AND task_date LIKE ?
    ORDER BY time_from, id
    """, (
        company_id,
        task_id,
        f"{target_date}%",
    )).fetchall()
    conflicts = find_time_conflicts(
        day_tasks,
        task_workers,
        target_time_from,
        target_time_to,
    )
    assignments = [
        {
            "task_id": row["id"],
            "date": str(row["task_date"] or "")[:10],
            "workers": get_task_worker_names(row),
            "time_from": str(row["time_from"] or "")[:5],
            "time_to": str(row["time_to"] or "")[:5],
        }
        for row in day_tasks
    ]
    suggestions = list_common_time_slots(
        assignments=assignments,
        target_date=target_date,
        target_workers=task_workers,
        duration_minutes=duration_minutes,
    )[:8]

    if conflicts:
        conn.close()
        return JSONResponse(
            {
                "ok": False,
                "error": "time_conflict",
                "conflicts": conflicts,
                "suggestions": suggestions,
            },
            status_code=409,
        )

    c.execute("""
    UPDATE tasks
    SET task_date=?, time_from=?, time_to=?
    WHERE id=? AND company_id=?
    """, (
        target_date,
        target_time_from,
        target_time_to,
        task_id,
        company_id,
    ))
    details = (
        f"Было: {current_date or 'Без даты'}, "
        f"{current_time_from + '–' + current_time_to if current_time_from else 'Без времени'}. "
        f"Стало: {target_date}, {target_time_from}–{target_time_to}"
    )
    created_at = datetime.now().strftime("%Y-%m-%d %H:%M")
    c.execute("""
    INSERT INTO task_activity (
        task_id, username, role, action, details, created_at
    )
    VALUES (?, ?, ?, ?, ?, ?)
    """, (
        task_id,
        username,
        role,
        "Время изменено на маршруте дня",
        details,
        created_at,
    ))

    for worker_name in task_workers:
        c.execute("""
        INSERT INTO notifications (
            company_id, username, title, message, link, created_at
        )
        VALUES (?, ?, ?, ?, ?, ?)
        """, (
            company_id,
            worker_name,
            f"Изменено расписание заявки #{task_id}",
            f"{target_date}, {target_time_from}–{target_time_to}",
            f"/task/{task_id}",
            created_at,
        ))

    conn.commit()
    chat_ids = [
        str(row["telegram_chat_id"] or "").strip()
        for row in worker_rows
        if str(row["telegram_chat_id"] or "").strip()
    ]
    conn.close()

    for chat_id in chat_ids:
        try:
            send_message_to_chat(
                chat_id,
                (
                    f"Изменено расписание заявки #{task_id}\n"
                    f"Клиент: {task['client']}\n"
                    f"Дата: {target_date}\n"
                    f"Время: {target_time_from}–{target_time_to}"
                ),
            )
        except Exception:
            pass

    return {
        "ok": True,
        "changed": True,
        "task_id": task_id,
        "old_date": current_date,
        "old_time_from": current_time_from,
        "old_time_to": current_time_to,
        "target_date": target_date,
        "target_time_from": target_time_from,
        "target_time_to": target_time_to,
        "suggestions": suggestions,
    }


@router.get("/api/calendar/dispatch/plan")
def api_calendar_dispatch_plan(
    request: Request,
    start: str = "",
    days: int = 14,
    limit: int = 25,
):
    username = get_user(request)

    if not username:
        return JSONResponse(
            {
                "ok": False,
                "error": "unauthorized",
                "message": "Требуется авторизация.",
            },
            status_code=401,
        )

    role = get_role(username)

    if role not in ("boss", "manager"):
        return JSONResponse(
            {
                "ok": False,
                "error": "forbidden",
                "message": "Недостаточно прав.",
            },
            status_code=403,
        )

    company_id = get_user_company_id(username)

    if not has_feature(company_id, "calendar"):
        return JSONResponse(
            {
                "ok": False,
                "error": "feature_disabled",
                "message": "Модуль календаря отключён.",
            },
            status_code=403,
        )

    try:
        start_date = datetime.strptime(
            str(start or datetime.now().strftime("%Y-%m-%d")),
            "%Y-%m-%d",
        ).date()
    except Exception:
        return JSONResponse(
            {
                "ok": False,
                "error": "invalid_start_date",
                "message": "Указана некорректная начальная дата.",
            },
            status_code=400,
        )

    if start_date < datetime.now().date():
        start_date = datetime.now().date()

    search_days = days if days in (7, 14, 30) else 14
    plan_limit = min(max(int(limit or 25), 1), 50)
    conn = connect()
    plan = _build_company_dispatch_plan(
        conn.cursor(),
        company_id,
        start_date,
        search_days,
        plan_limit,
    )
    conn.close()
    return {
        "ok": True,
        "company_id": company_id,
        **plan,
    }


@router.post("/api/calendar/dispatch/plan/apply")
async def api_calendar_dispatch_plan_apply(request: Request):
    username = get_user(request)

    if not username:
        return JSONResponse(
            {
                "ok": False,
                "error": "unauthorized",
                "message": "Требуется авторизация.",
            },
            status_code=401,
        )

    role = get_role(username)

    if role not in ("boss", "manager"):
        return JSONResponse(
            {
                "ok": False,
                "error": "forbidden",
                "message": "Недостаточно прав.",
            },
            status_code=403,
        )

    company_id = get_user_company_id(username)

    if not has_feature(company_id, "calendar"):
        return JSONResponse(
            {
                "ok": False,
                "error": "feature_disabled",
                "message": "Модуль календаря отключён.",
            },
            status_code=403,
        )

    try:
        payload = await request.json()
    except Exception:
        return JSONResponse(
            {
                "ok": False,
                "error": "invalid_json",
                "message": "Не удалось прочитать план.",
            },
            status_code=400,
        )

    plan_items = payload.get("items")

    if not isinstance(plan_items, list) or not plan_items:
        return JSONResponse(
            {
                "ok": False,
                "error": "empty_plan",
                "message": "Не выбраны заявки для планирования.",
            },
            status_code=400,
        )

    if len(plan_items) > 50:
        return JSONResponse(
            {
                "ok": False,
                "error": "plan_too_large",
                "message": "За один раз можно применить не более 50 строк.",
            },
            status_code=400,
        )

    conn = connect()
    c = conn.cursor()
    worker_rows = c.execute("""
    SELECT username, daily_capacity, telegram_chat_id
    FROM users
    WHERE company_id=?
      AND role='worker'
      AND COALESCE(is_active, 1)=1
    ORDER BY username
    """, (company_id,)).fetchall()
    workers_by_name = {
        row["username"]: row
        for row in worker_rows
    }
    applied = []
    skipped = []
    telegram_messages = []
    processed_task_ids = set()
    now_value = datetime.now().strftime("%Y-%m-%d %H:%M")
    today = datetime.now().date()

    for raw_item in plan_items:
        try:
            task_id = int(raw_item.get("task_id") or 0)
        except (TypeError, ValueError, AttributeError):
            task_id = 0

        if not task_id or task_id in processed_task_ids:
            skipped.append({
                "task_id": task_id,
                "reason": "Некорректная или повторяющаяся заявка.",
            })
            continue

        processed_task_ids.add(task_id)
        target_date = str(
            raw_item.get("target_date") or ""
        ).strip()[:10]
        expected_date = str(
            raw_item.get("current_date") or ""
        ).strip()[:10]
        checks_expected_time = (
            "expected_time_from" in raw_item
            or "expected_time_to" in raw_item
        )
        expected_time_from = str(
            raw_item.get("expected_time_from") or ""
        ).strip()[:5]
        expected_time_to = str(
            raw_item.get("expected_time_to") or ""
        ).strip()[:5]
        expected_workers_value = raw_item.get("expected_workers")

        if isinstance(expected_workers_value, list):
            expected_workers = ",".join(
                str(value).strip()
                for value in expected_workers_value
                if str(value).strip()
            )
        else:
            expected_workers = ",".join(
                value.strip()
                for value in str(
                    expected_workers_value or ""
                ).split(",")
                if value.strip()
            )

        raw_target_workers = raw_item.get("target_workers")

        if isinstance(raw_target_workers, list):
            target_workers = [
                str(value).strip()
                for value in raw_target_workers
                if str(value).strip()
            ]
        else:
            target_workers = [
                value.strip()
                for value in str(
                    raw_item.get("target_workers_csv") or ""
                ).split(",")
                if value.strip()
            ]

        target_workers = list(dict.fromkeys(target_workers))
        target_time_from, target_time_to, time_error = (
            normalize_time_window(
                raw_item.get("target_time_from"),
                raw_item.get("target_time_to"),
            )
        )

        try:
            parsed_target_date = datetime.strptime(
                target_date,
                "%Y-%m-%d",
            ).date()
        except ValueError:
            skipped.append({
                "task_id": task_id,
                "reason": "Некорректная дата назначения.",
            })
            continue

        if parsed_target_date < today:
            skipped.append({
                "task_id": task_id,
                "reason": "Нельзя назначить заявку на прошедшую дату.",
            })
            continue

        if not target_workers or len(target_workers) > 5:
            skipped.append({
                "task_id": task_id,
                "reason": "Не выбрана допустимая команда.",
            })
            continue

        if time_error:
            skipped.append({
                "task_id": task_id,
                "reason": time_error,
            })
            continue

        if not target_time_from or not target_time_to:
            skipped.append({
                "task_id": task_id,
                "reason": "Не выбрано временное окно.",
            })
            continue

        task = c.execute("""
        SELECT *
        FROM tasks
        WHERE id=? AND company_id=?
        """, (task_id, company_id)).fetchone()

        if not task:
            skipped.append({
                "task_id": task_id,
                "reason": "Заявка не найдена.",
            })
            continue

        if (
            int(task["archived"] or 0) == 1
            or task["status"] in ("Завершено", "Отменено")
        ):
            skipped.append({
                "task_id": task_id,
                "reason": "Заявка уже закрыта или находится в архиве.",
            })
            continue

        current_date = str(task["task_date"] or "")[:10]
        current_time_from = str(task["time_from"] or "")[:5]
        current_time_to = str(task["time_to"] or "")[:5]
        current_workers = get_task_worker_names(task)
        current_workers_csv = ",".join(current_workers)

        if (
            current_date != expected_date
            or current_workers_csv != expected_workers
            or (
                checks_expected_time
                and (
                    current_time_from != expected_time_from
                    or current_time_to != expected_time_to
                )
            )
        ):
            skipped.append({
                "task_id": task_id,
                "reason": "Заявка изменилась после расчёта плана.",
            })
            continue

        invalid_workers = [
            worker_name
            for worker_name in target_workers
            if worker_name not in workers_by_name
        ]

        if invalid_workers:
            skipped.append({
                "task_id": task_id,
                "reason": (
                    "Исполнитель отключён: "
                    + ", ".join(invalid_workers)
                ),
            })
            continue

        unavailable_dates, unavailable_reasons = (
            get_worker_unavailability(
                c,
                company_id,
                target_workers,
                target_date,
                target_date,
            )
        )
        unavailable_worker = next(
            (
                worker_name
                for worker_name in target_workers
                if target_date
                in unavailable_dates.get(worker_name, set())
            ),
            "",
        )

        if unavailable_worker:
            reason = unavailable_reasons.get(
                (unavailable_worker, target_date),
                "Сотрудник недоступен.",
            )
            skipped.append({
                "task_id": task_id,
                "reason": f"{unavailable_worker}: {reason}",
            })
            continue

        day_tasks = c.execute("""
        SELECT *
        FROM tasks
        WHERE company_id=?
          AND id!=?
          AND archived=0
          AND status NOT IN ('Завершено', 'Отменено')
          AND task_date LIKE ?
        """, (
            company_id,
            task_id,
            f"{target_date}%",
        )).fetchall()
        time_conflicts = find_time_conflicts(
            day_tasks,
            target_workers,
            target_time_from,
            target_time_to,
        )

        if time_conflicts:
            conflict = time_conflicts[0]
            skipped.append({
                "task_id": task_id,
                "reason": (
                    f"Пересечение с заявкой #{conflict['task_id']} "
                    f"({conflict['time_from']}–{conflict['time_to']})."
                ),
            })
            continue

        capacity_error = None

        for worker_name in target_workers:
            active_count = c.execute(f"""
            SELECT COUNT(*)
            FROM tasks
            WHERE company_id=?
              AND id!=?
              AND archived=0
              AND status NOT IN ('Завершено', 'Отменено')
              AND task_date LIKE ?
              AND {worker_task_condition()}
            """, [
                company_id,
                task_id,
                f"{target_date}%",
                *worker_task_params(worker_name),
            ]).fetchone()[0]
            daily_capacity = max(
                1,
                int(
                    workers_by_name[worker_name]["daily_capacity"]
                    or 3
                ),
            )

            if active_count >= daily_capacity:
                capacity_error = (
                    f"{worker_name}: дневной лимит "
                    f"{daily_capacity} уже заполнен."
                )
                break

        if capacity_error:
            skipped.append({
                "task_id": task_id,
                "reason": capacity_error,
            })
            continue

        target_workers_csv = ",".join(target_workers)
        c.execute("""
        UPDATE tasks
        SET task_date=?, worker=?, workers=?, time_from=?, time_to=?
        WHERE id=? AND company_id=?
        """, (
            target_date,
            target_workers[0],
            target_workers_csv,
            target_time_from,
            target_time_to,
            task_id,
            company_id,
        ))
        details = (
            f"Дата: {current_date or 'не назначена'} → {target_date}. "
            f"Время: {target_time_from}–{target_time_to}. "
            f"Исполнители: "
            f"{', '.join(current_workers) or 'не назначены'} → "
            f"{', '.join(target_workers)}"
        )
        c.execute("""
        INSERT INTO task_activity (
            task_id, username, role, action, details, created_at
        )
        VALUES (?, ?, ?, ?, ?, ?)
        """, (
            task_id,
            username,
            role,
            "Применён автоматический план",
            details,
            now_value,
        ))

        for worker_name in target_workers:
            c.execute("""
            INSERT INTO notifications (
                company_id, username, title, message, link, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """, (
                company_id,
                worker_name,
                f"Запланирована заявка #{task_id}",
                (
                    f"Дата: {target_date}. "
                    f"Время: {target_time_from}–{target_time_to}. "
                    "Автоматическое планирование."
                ),
                f"/task/{task_id}",
                now_value,
            ))
            chat_id = str(
                workers_by_name[worker_name]["telegram_chat_id"] or ""
            ).strip()

            if chat_id:
                telegram_messages.append((
                    chat_id,
                    (
                        f"Запланирована заявка #{task_id}\n"
                        f"Клиент: {task['client']}\n"
                        f"Дата: {target_date}\n"
                        f"Время: {target_time_from}–{target_time_to}"
                    ),
                ))

        for worker_name in current_workers:
            if worker_name in target_workers:
                continue

            c.execute("""
            INSERT INTO notifications (
                company_id, username, title, message, link, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """, (
                company_id,
                worker_name,
                f"Снято назначение с заявки #{task_id}",
                "Команда изменена автоматическим планировщиком.",
                "/my-tasks",
                now_value,
            ))

        applied.append({
            "task_id": task_id,
            "target_date": target_date,
            "target_workers": target_workers,
            "target_time_from": target_time_from,
            "target_time_to": target_time_to,
        })

    conn.commit()
    conn.close()

    for chat_id, message in telegram_messages:
        try:
            send_message_to_chat(chat_id, message)
        except Exception:
            pass

    return {
        "ok": True,
        "applied": applied,
        "skipped": skipped,
        "summary": {
            "requested": len(plan_items),
            "applied": len(applied),
            "skipped": len(skipped),
        },
        "message": (
            f"Применено: {len(applied)}. "
            f"Пропущено: {len(skipped)}."
        ),
    }


@router.post("/api/calendar/dispatch/move")
async def api_calendar_dispatch_move(request: Request):
    username = get_user(request)

    if not username:
        return JSONResponse(
            {"ok": False, "error": "unauthorized"},
            status_code=401,
        )

    role = get_role(username)

    if role not in ("boss", "manager"):
        return JSONResponse(
            {"ok": False, "error": "forbidden"},
            status_code=403,
        )

    company_id = get_user_company_id(username)

    if not has_feature(company_id, "calendar"):
        return JSONResponse(
            {"ok": False, "error": "feature_disabled"},
            status_code=403,
        )

    try:
        payload = await request.json()
    except Exception:
        return JSONResponse(
            {"ok": False, "error": "invalid_json"},
            status_code=400,
        )

    try:
        task_id = int(payload.get("task_id") or 0)
    except Exception:
        task_id = 0

    target_date = str(payload.get("target_date") or "").strip()[:10]
    expected_date = str(payload.get("expected_date") or "").strip()[:10]

    if target_date:
        try:
            parsed_target_date = datetime.strptime(
                target_date,
                "%Y-%m-%d",
            ).date()
        except Exception:
            return JSONResponse(
                {"ok": False, "error": "invalid_date"},
                status_code=400,
            )

        if parsed_target_date < datetime.now().date():
            return JSONResponse(
                {"ok": False, "error": "past_date"},
                status_code=400,
            )

    conn = connect()
    c = conn.cursor()
    task = c.execute("""
    SELECT *
    FROM tasks
    WHERE id=? AND company_id=?
    """, (task_id, company_id)).fetchone()

    if not task:
        conn.close()
        return JSONResponse(
            {"ok": False, "error": "not_found"},
            status_code=404,
        )

    if (
        int(task["archived"] or 0) == 1
        or task["status"] in ("Завершено", "Отменено")
    ):
        conn.close()
        return JSONResponse(
            {"ok": False, "error": "task_closed"},
            status_code=409,
        )

    current_date = str(task["task_date"] or "")[:10]

    if current_date != expected_date:
        conn.close()
        return JSONResponse(
            {
                "ok": False,
                "error": "stale",
                "current_date": current_date,
            },
            status_code=409,
        )

    if current_date == target_date:
        conn.close()
        return {
            "ok": True,
            "task_id": task_id,
            "old_date": current_date,
            "new_date": target_date,
            "changed": False,
        }

    task_workers = get_task_worker_names(task)
    worker_rows = []

    if task_workers:
        placeholders = ",".join("?" for _ in task_workers)
        worker_rows = c.execute(f"""
        SELECT username, daily_capacity, telegram_chat_id
        FROM users
        WHERE company_id=?
          AND role='worker'
          AND COALESCE(is_active, 1)=1
          AND username IN ({placeholders})
        """, [company_id, *task_workers]).fetchall()

    if target_date and task_workers:
        workers_by_name = {
            row["username"]: row
            for row in worker_rows
        }

        if any(
            worker_name not in workers_by_name
            for worker_name in task_workers
        ):
            conn.close()
            return JSONResponse(
                {"ok": False, "error": "inactive_worker"},
                status_code=409,
            )

        unavailable_dates, unavailable_reasons = (
            get_worker_unavailability(
                c,
                company_id,
                task_workers,
                target_date,
                target_date,
            )
        )
        unavailable_worker = next(
            (
                worker_name
                for worker_name in task_workers
                if target_date
                in unavailable_dates.get(worker_name, set())
            ),
            "",
        )

        if unavailable_worker:
            reason = unavailable_reasons.get(
                (unavailable_worker, target_date),
                "",
            )
            suggestions = _get_dispatch_date_suggestions(
                c,
                company_id,
                task_id,
                task_workers,
                target_date,
                workers_by_name,
            )
            conn.close()
            return JSONResponse(
                {
                    "ok": False,
                    "error": "worker_unavailable",
                    "worker": unavailable_worker,
                    "reason": reason,
                    "suggestions": suggestions,
                },
                status_code=409,
            )

        for worker_name in task_workers:
            active_count = c.execute(f"""
            SELECT COUNT(*)
            FROM tasks
            WHERE company_id=?
              AND id!=?
              AND archived=0
              AND status NOT IN ('Завершено', 'Отменено')
              AND task_date LIKE ?
              AND {worker_task_condition()}
            """, [
                company_id,
                task_id,
                f"{target_date}%",
                *worker_task_params(worker_name),
            ]).fetchone()[0]
            daily_capacity = max(
                1,
                int(workers_by_name[worker_name]["daily_capacity"] or 3),
            )

            if active_count >= daily_capacity:
                suggestions = _get_dispatch_date_suggestions(
                    c,
                    company_id,
                    task_id,
                    task_workers,
                    target_date,
                    workers_by_name,
                )
                conn.close()
                return JSONResponse(
                    {
                        "ok": False,
                        "error": "capacity_reached",
                        "worker": worker_name,
                        "active_count": active_count,
                        "daily_capacity": daily_capacity,
                        "suggestions": suggestions,
                    },
                    status_code=409,
                )

    c.execute("""
    UPDATE tasks
    SET task_date=?
    WHERE id=? AND company_id=?
    """, (target_date, task_id, company_id))
    details = (
        f"Было: {current_date or 'Без даты'}. "
        f"Стало: {target_date or 'Без даты'}"
    )
    c.execute("""
    INSERT INTO task_activity (
        task_id, username, role, action, details, created_at
    )
    VALUES (?, ?, ?, ?, ?, ?)
    """, (
        task_id,
        username,
        role,
        "Перенесено на диспетчерской доске",
        details,
        datetime.now().strftime("%Y-%m-%d %H:%M"),
    ))
    created_at = datetime.now().strftime("%Y-%m-%d %H:%M")

    for worker_name in task_workers:
        c.execute("""
        INSERT INTO notifications (
            company_id, username, title, message, link, created_at
        )
        VALUES (?, ?, ?, ?, ?, ?)
        """, (
            company_id,
            worker_name,
            f"Изменена дата заявки #{task_id}",
            f"Новая дата: {target_date or 'не назначена'}",
            f"/task/{task_id}",
            created_at,
        ))

    conn.commit()
    chat_ids = [
        str(row["telegram_chat_id"] or "").strip()
        for row in worker_rows
        if str(row["telegram_chat_id"] or "").strip()
    ]
    conn.close()

    for chat_id in chat_ids:
        try:
            send_message_to_chat(
                chat_id,
                (
                    f"Изменена дата заявки #{task_id}\n"
                    f"Клиент: {task['client']}\n"
                    f"Новая дата: {target_date or 'не назначена'}"
                ),
            )
        except Exception:
            pass

    return {
        "ok": True,
        "task_id": task_id,
        "old_date": current_date,
        "new_date": target_date,
        "changed": True,
    }


@router.get("/calendar/conflicts", response_class=HTMLResponse)
async def calendar_conflicts_page(
    request: Request,
    days: int = 30,
    severity: str = "",
    conflict_type: str = "",
):
    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role not in ("boss", "manager"):
        return RedirectResponse("/", status_code=302)

    company_id = get_user_company_id(username)
    disabled_response = require_feature(company_id, "calendar")

    if disabled_response:
        return disabled_response

    settings = get_company_settings(company_id)

    selected_days = days if days in (7, 14, 30, 60) else 30
    date_from = datetime.now().strftime("%Y-%m-%d")
    date_to = (
        datetime.now().date() + timedelta(days=selected_days - 1)
    ).strftime("%Y-%m-%d")
    conflicts, summary = get_company_schedule_conflicts(
        company_id,
        date_from,
        date_to,
    )
    selected_severity = (
        severity if severity in ("critical", "warning") else ""
    )
    selected_type = (
        conflict_type
        if conflict_type in (
            "unavailable",
            "overload",
            "time_overlap",
            "unassigned",
            "inactive_worker",
        )
        else ""
    )

    if selected_severity:
        conflicts = [
            conflict
            for conflict in conflicts
            if conflict["severity"] == selected_severity
        ]

    if selected_type:
        conflicts = [
            conflict
            for conflict in conflicts
            if any(
                issue["type"] == selected_type
                for issue in conflict["issues"]
            )
        ]

    return templates.TemplateResponse(
        request=request,
        name="calendar_conflicts.html",
        context={
            "request": request,
            "username": username,
            "role": role,
            "conflicts": conflicts,
            "summary": summary,
            "selected_days": selected_days,
            "selected_severity": selected_severity,
            "selected_type": selected_type,
            "date_from": date_from,
            "date_to": date_to,
            "settings": settings,
        },
    )


@router.get("/api/calendar/conflicts")
def api_calendar_conflicts(
    request: Request,
    days: int = 30,
):
    username = get_user(request)

    if not username:
        return JSONResponse(
            {"ok": False, "error": "unauthorized"},
            status_code=401,
        )

    role = get_role(username)

    if role not in ("boss", "manager"):
        return JSONResponse(
            {"ok": False, "error": "forbidden"},
            status_code=403,
        )

    company_id = get_user_company_id(username)

    if not has_feature(company_id, "calendar"):
        return JSONResponse(
            {"ok": False, "error": "feature_disabled"},
            status_code=403,
        )

    selected_days = days if days in (7, 14, 30, 60) else 30
    date_from = datetime.now().strftime("%Y-%m-%d")
    date_to = (
        datetime.now().date() + timedelta(days=selected_days - 1)
    ).strftime("%Y-%m-%d")
    conflicts, summary = get_company_schedule_conflicts(
        company_id,
        date_from,
        date_to,
    )

    return {
        "ok": True,
        "company_id": company_id,
        "date_from": date_from,
        "date_to": date_to,
        "summary": summary,
        "items": [
            {
                "task_id": conflict["task_id"],
                "client": conflict["task"]["client"] or "",
                "description": conflict["task"]["description"] or "",
                "task_date": conflict["task_date"],
                "workers": conflict["workers"],
                "severity": conflict["severity"],
                "issues": conflict["issues"],
                "recommendations": [
                    {
                        "mode": item["mode"],
                        "date": item["date"],
                        "workers": item["worker_names"],
                        "score": item["score"],
                        "reason": item["reason"],
                    }
                    for item in conflict["recommendations"]
                ],
            }
            for conflict in conflicts
        ],
    }


@router.post("/calendar/conflicts/{task_id}/resolve")
async def resolve_calendar_conflict(request: Request, task_id: int):
    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role not in ("boss", "manager"):
        return RedirectResponse("/", status_code=302)

    company_id = get_user_company_id(username)

    if not has_feature(company_id, "calendar"):
        return require_feature(company_id, "calendar")

    form = await request.form()
    new_date = str(form.get("new_date") or "").strip()[:10]
    expected_date = str(form.get("expected_date") or "").strip()[:10]
    expected_workers = str(
        form.get("expected_workers") or ""
    ).strip()
    requested_workers = [
        worker_name
        for worker_name in dict.fromkeys(
            part.strip()
            for part in str(form.get("workers_csv") or "").split(",")
            if part.strip()
        )
    ]
    return_days = str(form.get("return_days") or "30").strip()

    if return_days not in ("7", "14", "30", "60"):
        return_days = "30"

    redirect_base = f"/calendar/conflicts?days={return_days}"

    try:
        target_date = datetime.strptime(new_date, "%Y-%m-%d").date()
    except Exception:
        return RedirectResponse(
            redirect_base + "&error=invalid_date",
            status_code=302,
        )

    if target_date < datetime.now().date():
        return RedirectResponse(
            redirect_base + "&error=past_date",
            status_code=302,
        )

    if not requested_workers:
        return RedirectResponse(
            redirect_base + "&error=no_workers",
            status_code=302,
        )

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

    current_date = str(task["task_date"] or "")[:10]
    current_workers = get_task_worker_names(task)

    if (
        current_date != expected_date
        or ",".join(current_workers) != expected_workers
    ):
        conn.close()
        return RedirectResponse(
            redirect_base + "&error=stale",
            status_code=302,
        )

    placeholders = ",".join("?" for _ in requested_workers)
    worker_rows = c.execute(f"""
    SELECT username, daily_capacity, telegram_chat_id
    FROM users
    WHERE company_id=?
      AND role='worker'
      AND COALESCE(is_active, 1)=1
      AND username IN ({placeholders})
    """, [company_id, *requested_workers]).fetchall()
    workers_by_name = {
        row["username"]: row
        for row in worker_rows
    }

    if any(
        worker_name not in workers_by_name
        for worker_name in requested_workers
    ):
        conn.close()
        return RedirectResponse(
            redirect_base + "&error=invalid_workers",
            status_code=302,
        )

    unavailable_dates, _ = get_worker_unavailability(
        c,
        company_id,
        requested_workers,
        new_date,
        new_date,
    )

    if any(
        new_date in unavailable_dates.get(worker_name, set())
        for worker_name in requested_workers
    ):
        conn.close()
        return RedirectResponse(
            redirect_base + "&error=worker_unavailable",
            status_code=302,
        )

    for worker_name in requested_workers:
        active_count = c.execute(f"""
        SELECT COUNT(*)
        FROM tasks
        WHERE company_id=?
          AND id!=?
          AND archived=0
          AND status NOT IN ('Завершено', 'Отменено')
          AND task_date LIKE ?
          AND {worker_task_condition()}
        """, [
            company_id,
            task_id,
            f"{new_date}%",
            *worker_task_params(worker_name),
        ]).fetchone()[0]
        daily_capacity = max(
            1,
            int(workers_by_name[worker_name]["daily_capacity"] or 3),
        )

        if active_count >= daily_capacity:
            conn.close()
            return RedirectResponse(
                redirect_base + "&error=capacity_changed",
                status_code=302,
            )

    new_workers_csv = ",".join(requested_workers)
    c.execute("""
    UPDATE tasks
    SET task_date=?, worker=?, workers=?
    WHERE id=? AND company_id=?
    """, (
        new_date,
        requested_workers[0],
        new_workers_csv,
        task_id,
        company_id,
    ))
    details = (
        f"Дата: {current_date} → {new_date}. "
        f"Исполнители: {', '.join(current_workers) or 'не назначены'}"
        f" → {', '.join(requested_workers)}"
    )
    c.execute("""
    INSERT INTO task_activity (
        task_id, username, role, action, details, created_at
    )
    VALUES (?, ?, ?, ?, ?, ?)
    """, (
        task_id,
        username,
        role,
        "Конфликт расписания устранён",
        details,
        datetime.now().strftime("%Y-%m-%d %H:%M"),
    ))
    added_workers = [
        worker_name
        for worker_name in requested_workers
        if worker_name not in current_workers
    ]
    removed_workers = [
        worker_name
        for worker_name in current_workers
        if worker_name not in requested_workers
    ]
    notification_created_at = datetime.now().strftime("%Y-%m-%d %H:%M")

    for worker_name in added_workers:
        c.execute("""
        INSERT INTO notifications (
            company_id, username, title, message, link, created_at
        )
        VALUES (?, ?, ?, ?, ?, ?)
        """, (
            company_id,
            worker_name,
            f"Назначена заявка #{task_id}",
            f"Дата: {new_date}. Конфликт расписания устранён.",
            f"/task/{task_id}",
            notification_created_at,
        ))

    for worker_name in removed_workers:
        c.execute("""
        INSERT INTO notifications (
            company_id, username, title, message, link, created_at
        )
        VALUES (?, ?, ?, ?, ?, ?)
        """, (
            company_id,
            worker_name,
            f"Снято назначение с заявки #{task_id}",
            "Заявка перераспределена из центра конфликтов.",
            "/my-tasks",
            notification_created_at,
        ))

    conn.commit()
    conn.close()

    for worker_name in added_workers:
        chat_id = str(
            workers_by_name[worker_name]["telegram_chat_id"] or ""
        ).strip()

        if not chat_id:
            continue

        try:
            send_message_to_chat(
                chat_id,
                (
                    f"Вам назначена заявка #{task_id}\n"
                    f"Клиент: {task['client']}\n"
                    f"Дата: {new_date}"
                ),
            )
        except Exception:
            pass

    return RedirectResponse(
        redirect_base + f"&resolved=1&task_id={task_id}",
        status_code=302,
    )


@router.get("/calendar", response_class=HTMLResponse)
async def calendar_page(
    request: Request,
    worker: str = "",
    month: str = "",
    status: str = "",
    date: str = "",
    availability: str = "",
    week_start: str = "",
    schedule_start: str = "",
    schedule_days: int = 14,
    schedule_workers: int = 1,
    schedule_duration: int = 60,
):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    update_last_seen(username)
    role = get_role(username)

    if role == "superadmin":
        return RedirectResponse("/platform", status_code=302)

    company_id = get_user_company_id(username)
    disabled_response = require_feature(company_id, "calendar")

    if disabled_response:
        return disabled_response

    settings = get_company_settings(company_id)

    conn = connect()
    c = conn.cursor()

    workers = []
    worker_loads = []
    worker_availability = []
    weekly_capacity_rows = []
    weekly_capacity_days = []
    weekly_capacity_summary = {
        "assignments": 0,
        "capacity": 0,
        "available_slots": 0,
        "full_cells": 0,
        "unavailable_cells": 0,
        "conflict_assignments": 0,
        "utilization_percent": 0,
    }
    smart_schedule_items = []
    smart_schedule_summary = {
        "search_days": 14,
        "required_workers": 1,
        "days_with_capacity": 0,
        "total_open_slots": 0,
        "found": 0,
        "time_slots_found": 0,
    }
    availability_summary = {
        "total": 0,
        "free": 0,
        "busy": 0,
        "unavailable": 0,
    }
    selected_availability = (
        availability
        if availability in ("free", "busy", "unavailable")
        else ""
    )
    selected_date = str(date or "").strip()

    try:
        if selected_date:
            datetime.strptime(selected_date, "%Y-%m-%d")
    except Exception:
        selected_date = ""

    availability_date = selected_date or datetime.now().strftime("%Y-%m-%d")
    selected_schedule_start = str(schedule_start or "").strip()

    try:
        schedule_start_date = datetime.strptime(
            selected_schedule_start or availability_date,
            "%Y-%m-%d",
        ).date()
    except Exception:
        schedule_start_date = datetime.now().date()

    if schedule_start_date < datetime.now().date():
        schedule_start_date = datetime.now().date()

    selected_schedule_start = schedule_start_date.strftime("%Y-%m-%d")
    selected_schedule_days = (
        schedule_days if schedule_days in (7, 14, 30) else 14
    )
    selected_schedule_workers = min(max(int(schedule_workers or 1), 1), 5)
    selected_schedule_duration = (
        schedule_duration
        if schedule_duration in (30, 60, 90, 120)
        else 60
    )
    selected_week_start = str(week_start or "").strip()

    try:
        week_anchor = datetime.strptime(
            selected_week_start or availability_date,
            "%Y-%m-%d",
        ).date()
    except Exception:
        week_anchor = datetime.now().date()

    calendar_week_start = week_anchor - timedelta(days=week_anchor.weekday())
    calendar_week_end = calendar_week_start + timedelta(days=6)
    selected_week_start = calendar_week_start.strftime("%Y-%m-%d")
    selected_week_end = calendar_week_end.strftime("%Y-%m-%d")
    weekday_labels = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]

    for day_offset in range(7):
        week_day = calendar_week_start + timedelta(days=day_offset)
        weekly_capacity_days.append({
            "date": week_day.strftime("%Y-%m-%d"),
            "day_label": weekday_labels[day_offset],
            "date_label": week_day.strftime("%d.%m"),
            "is_today": week_day == datetime.now().date(),
        })

    query = """
    SELECT *
    FROM tasks
    WHERE archived=0 AND company_id=?
    """
    params = [company_id]

    if month:
        query += " AND task_date LIKE ?"
        params.append(f"{month}%")

    if selected_date:
        query += " AND task_date LIKE ?"
        params.append(f"{selected_date}%")

    if role in ("boss", "manager"):
        workers = c.execute("""
        SELECT username, daily_capacity
        FROM users
        WHERE role='worker'
          AND company_id=?
          AND COALESCE(is_active, 1)=1
        ORDER BY username
        """, (company_id,)).fetchall()
        worker_names = [w["username"] for w in workers]
        worker_capacity_map = {
            worker_row["username"]: max(
                1,
                int(worker_row["daily_capacity"] or 3),
            )
            for worker_row in workers
        }
        availability_day = datetime.strptime(
            availability_date,
            "%Y-%m-%d",
        ).date()
        schedule_end_date = (
            schedule_start_date
            + timedelta(days=selected_schedule_days - 1)
        )
        unavailable_dates, unavailable_reasons = get_worker_unavailability(
            c,
            company_id,
            worker_names,
            min(
                availability_day,
                calendar_week_start,
                schedule_start_date,
            ).strftime("%Y-%m-%d"),
            max(
                availability_day,
                calendar_week_end,
                schedule_end_date,
            ).strftime("%Y-%m-%d"),
        )

        if worker and worker in worker_names:
            query += f" AND {worker_task_condition()}"
            params += worker_task_params(worker)
            planner_worker_names = [worker]
        elif worker:
            query += " AND 1=0"
            planner_worker_names = []
        else:
            planner_worker_names = worker_names

        for worker_row in workers:
            worker_name = worker_row["username"]
            worker_condition = worker_task_condition()
            worker_params = worker_task_params(worker_name)
            load_params = [company_id] + worker_params
            date_filter = ""

            if month:
                date_filter = " AND task_date LIKE ?"
                load_params.append(f"{month}%")

            total = c.execute(f"""
            SELECT COUNT(*) FROM tasks
            WHERE archived=0 AND company_id=? AND {worker_condition}{date_filter}
            """, load_params).fetchone()[0]

            new = c.execute(f"""
            SELECT COUNT(*) FROM tasks
            WHERE archived=0 AND company_id=? AND {worker_condition}
              AND status='Новая'{date_filter}
            """, load_params).fetchone()[0]

            active = c.execute(f"""
            SELECT COUNT(*) FROM tasks
            WHERE archived=0 AND company_id=? AND {worker_condition}
              AND status='В работе'{date_filter}
            """, load_params).fetchone()[0]

            completed = c.execute(f"""
            SELECT COUNT(*) FROM tasks
            WHERE archived=0 AND company_id=? AND {worker_condition}
              AND status='Завершено'{date_filter}
            """, load_params).fetchone()[0]

            worker_loads.append({
                "username": worker_name,
                "total": total,
                "new": new,
                "active": active,
                "completed": completed
            })

        worker_name_set = set(worker_names)
        busy_counts = {worker_name: 0 for worker_name in worker_names}
        availability_rows = c.execute("""
        SELECT worker, workers
        FROM tasks
        WHERE archived=0
          AND company_id=?
          AND task_date LIKE ?
          AND status NOT IN ('Завершено', 'Отменено')
        """, (company_id, f"{availability_date}%")).fetchall()

        for availability_task in availability_rows:
            for worker_name in get_task_worker_names(availability_task):
                if worker_name in worker_name_set:
                    busy_counts[worker_name] += 1

        for worker_name in worker_names:
            active_count = busy_counts.get(worker_name, 0)
            daily_capacity = worker_capacity_map[worker_name]
            available_slots = max(daily_capacity - active_count, 0)
            is_unavailable = (
                availability_date
                in unavailable_dates.get(worker_name, set())
            )

            if is_unavailable:
                available_slots = 0

            worker_availability.append({
                "username": worker_name,
                "active_count": active_count,
                "daily_capacity": daily_capacity,
                "available_slots": available_slots,
                "load_percent": min(
                    round(active_count / daily_capacity * 100),
                    100,
                ),
                "is_free": available_slots > 0 and not is_unavailable,
                "is_at_capacity": (
                    available_slots == 0 and not is_unavailable
                ),
                "is_unavailable": is_unavailable,
                "unavailable_reason": unavailable_reasons.get(
                    (worker_name, availability_date),
                    "",
                ),
                "is_recommended": False
            })

        recommended_load = min(
            [
                item["active_count"] / item["daily_capacity"]
                for item in worker_availability
                if item["available_slots"] > 0
                and not item["is_unavailable"]
            ],
            default=None
        )

        for item in worker_availability:
            item["is_recommended"] = (
                recommended_load is not None
                and item["available_slots"] > 0
                and not item["is_unavailable"]
                and item["active_count"] / item["daily_capacity"]
                == recommended_load
            )

        availability_summary = {
            "total": len(worker_availability),
            "free": sum(1 for item in worker_availability if item["is_free"]),
            "busy": sum(
                1
                for item in worker_availability
                if item["is_at_capacity"]
            ),
            "unavailable": sum(
                1
                for item in worker_availability
                if item["is_unavailable"]
            ),
        }

        if selected_availability == "free":
            worker_availability = [item for item in worker_availability if item["is_free"]]
        elif selected_availability == "busy":
            worker_availability = [
                item
                for item in worker_availability
                if item["is_at_capacity"]
            ]
        elif selected_availability == "unavailable":
            worker_availability = [
                item
                for item in worker_availability
                if item["is_unavailable"]
            ]

        weekly_counts = {
            worker_name: {
                day["date"]: 0
                for day in weekly_capacity_days
            }
            for worker_name in planner_worker_names
        }
        weekly_rows = c.execute("""
        SELECT worker, workers, substr(task_date, 1, 10) AS work_date
        FROM tasks
        WHERE archived=0
          AND company_id=?
          AND status NOT IN ('Завершено', 'Отменено')
          AND task_date IS NOT NULL
          AND task_date != ''
          AND substr(task_date, 1, 10) BETWEEN ? AND ?
        """, (
            company_id,
            selected_week_start,
            selected_week_end,
        )).fetchall()

        for weekly_task in weekly_rows:
            work_date = weekly_task["work_date"]

            for worker_name in get_task_worker_names(weekly_task):
                if worker_name in weekly_counts:
                    weekly_counts[worker_name][work_date] += 1

        recommended_workers_by_day = {}

        for day in weekly_capacity_days:
            day_date = day["date"]
            available_workers = [
                worker_name
                for worker_name in planner_worker_names
                if day_date not in unavailable_dates.get(worker_name, set())
                if weekly_counts[worker_name][day_date]
                < worker_capacity_map[worker_name]
            ]

            if available_workers:
                recommended_workers_by_day[day_date] = min(
                    available_workers,
                    key=lambda worker_name: (
                        weekly_counts[worker_name][day_date]
                        / worker_capacity_map[worker_name],
                        weekly_counts[worker_name][day_date],
                        worker_name,
                    ),
                )

        for worker_name in planner_worker_names:
            daily_capacity = worker_capacity_map[worker_name]
            cells = []

            for day in weekly_capacity_days:
                day_date = day["date"]
                task_count = weekly_counts[worker_name][day_date]
                is_unavailable = (
                    day_date
                    in unavailable_dates.get(worker_name, set())
                )
                available_slots = (
                    0
                    if is_unavailable
                    else max(daily_capacity - task_count, 0)
                )
                is_at_capacity = available_slots == 0
                is_overloaded = task_count > daily_capacity
                cell_status = "free"

                if is_unavailable:
                    cell_status = "unavailable"
                elif is_overloaded:
                    cell_status = "overloaded"
                elif is_at_capacity:
                    cell_status = "full"
                elif task_count:
                    cell_status = "partial"

                cells.append({
                    "date": day_date,
                    "task_count": task_count,
                    "available_slots": available_slots,
                    "load_percent": min(
                        round(task_count / daily_capacity * 100),
                        100,
                    ),
                    "status": cell_status,
                    "is_unavailable": is_unavailable,
                    "has_conflict": is_unavailable and task_count > 0,
                    "unavailable_reason": unavailable_reasons.get(
                        (worker_name, day_date),
                        "",
                    ),
                    "is_recommended": (
                        recommended_workers_by_day.get(day_date)
                        == worker_name
                    ),
                    "calendar_url": "/calendar?" + urlencode({
                        "date": day_date,
                        "worker": worker_name,
                        "week_start": selected_week_start,
                    }),
                    "create_url": "/create-task?" + urlencode({
                        "task_date": day_date,
                        "worker": worker_name,
                        "return_to": "calendar",
                    }),
                })

            total_assignments = sum(
                cell["task_count"] for cell in cells
            )
            available_day_count = sum(
                1
                for cell in cells
                if not cell["is_unavailable"]
            )
            total_capacity = daily_capacity * available_day_count
            total_available_slots = sum(
                cell["available_slots"] for cell in cells
            )
            weekly_capacity_rows.append({
                "username": worker_name,
                "daily_capacity": daily_capacity,
                "cells": cells,
                "total_assignments": total_assignments,
                "total_capacity": total_capacity,
                "available_slots": total_available_slots,
                "unavailable_days": 7 - available_day_count,
                "utilization_percent": round(
                    total_assignments / total_capacity * 100
                ) if total_capacity else 0,
            })

        weekly_capacity_summary = {
            "assignments": sum(
                row["total_assignments"]
                for row in weekly_capacity_rows
            ),
            "capacity": sum(
                row["total_capacity"]
                for row in weekly_capacity_rows
            ),
            "available_slots": sum(
                row["available_slots"]
                for row in weekly_capacity_rows
            ),
            "full_cells": sum(
                1
                for row in weekly_capacity_rows
                for cell in row["cells"]
                if cell["status"] in ("full", "overloaded")
            ),
            "unavailable_cells": sum(
                1
                for row in weekly_capacity_rows
                for cell in row["cells"]
                if cell["status"] == "unavailable"
            ),
            "conflict_assignments": sum(
                cell["task_count"]
                for row in weekly_capacity_rows
                for cell in row["cells"]
                if cell["is_unavailable"]
            ),
            "utilization_percent": 0,
        }

        if weekly_capacity_summary["capacity"]:
            weekly_capacity_summary["utilization_percent"] = round(
                weekly_capacity_summary["assignments"]
                / weekly_capacity_summary["capacity"]
                * 100
            )

        schedule_rows = c.execute("""
        SELECT id, worker, workers,
               substr(task_date, 1, 10) AS work_date,
               time_from, time_to
        FROM tasks
        WHERE archived=0
          AND company_id=?
          AND status NOT IN ('Завершено', 'Отменено')
          AND task_date IS NOT NULL
          AND task_date != ''
          AND substr(task_date, 1, 10) BETWEEN ? AND ?
        """, (
            company_id,
            selected_schedule_start,
            schedule_end_date.strftime("%Y-%m-%d"),
        )).fetchall()
        schedule_assignments = [
            {
                "task_id": row["id"],
                "date": row["work_date"],
                "workers": get_task_worker_names(row),
                "time_from": row["time_from"],
                "time_to": row["time_to"],
            }
            for row in schedule_rows
        ]
        scheduling_result = build_scheduling_recommendations(
            worker_capacities=worker_capacity_map,
            assignments=schedule_assignments,
            start_date=schedule_start_date,
            search_days=selected_schedule_days,
            required_workers=selected_schedule_workers,
            preferred_worker=worker if worker in worker_names else "",
            unavailable_dates=unavailable_dates,
            limit=selected_schedule_days,
        )
        actionable_schedule_items = add_time_slots_to_recommendations(
            scheduling_result["items"],
            schedule_assignments,
            duration_minutes=selected_schedule_duration,
        )
        smart_schedule_items = actionable_schedule_items[:12]
        smart_schedule_summary = dict(scheduling_result["summary"])
        smart_schedule_summary["found"] = len(actionable_schedule_items)
        smart_schedule_summary["time_slots_found"] = sum(
            item["available_time_slot_count"]
            for item in actionable_schedule_items
        )

        for item in smart_schedule_items:
            primary_time_slot = item["primary_time_slot"]
            item["create_url"] = "/create-task?" + urlencode({
                "task_date": item["date"],
                "time_from": primary_time_slot["time_from"],
                "time_to": primary_time_slot["time_to"],
                "worker": item["worker_names"][0],
                "workers_csv": ",".join(item["worker_names"]),
                "return_to": "calendar",
            })
            item["calendar_url"] = "/calendar?" + urlencode({
                "date": item["date"],
                "week_start": (
                    schedule_start_date
                    - timedelta(days=schedule_start_date.weekday())
                ).strftime("%Y-%m-%d"),
            })
    else:
        worker = ""
        query += f" AND {worker_task_condition()}"
        params += worker_task_params(username)

    if status in ("Новая", "В работе", "Завершено", "Отменено"):
        query += " AND status=?"
        params.append(status)

    current_calendar_day = datetime.strptime(availability_date, "%Y-%m-%d").date()

    def calendar_day_url(day):
        day_params = {"date": day.strftime("%Y-%m-%d")}

        if worker:
            day_params["worker"] = worker

        if status in ("Новая", "В работе", "Завершено", "Отменено"):
            day_params["status"] = status

        if selected_availability:
            day_params["availability"] = selected_availability

        return f"/calendar?{urlencode(day_params)}"

    previous_day_url = calendar_day_url(current_calendar_day - timedelta(days=1))
    today_day_url = calendar_day_url(datetime.now().date())
    next_day_url = calendar_day_url(current_calendar_day + timedelta(days=1))

    def calendar_week_url(start_date):
        week_params = {"week_start": start_date.strftime("%Y-%m-%d")}

        if worker:
            week_params["worker"] = worker

        if status in ("Новая", "В работе", "Завершено", "Отменено"):
            week_params["status"] = status

        return f"/calendar?{urlencode(week_params)}"

    previous_week_url = calendar_week_url(
        calendar_week_start - timedelta(days=7)
    )
    current_week_url = calendar_week_url(
        datetime.now().date()
        - timedelta(days=datetime.now().date().weekday())
    )
    next_week_url = calendar_week_url(
        calendar_week_start + timedelta(days=7)
    )

    query += " ORDER BY task_date ASC, id DESC"

    tasks = c.execute(query, params).fetchall()

    conn.close()

    calendar_days = []

    for task in tasks:
        task_date = str(task["task_date"] or "").strip()
        day_label = task_date[:10] if task_date else "Без даты"

        if not calendar_days or calendar_days[-1]["date"] != day_label:
            calendar_days.append({
                "date": day_label,
                "status_counts": {
                    "Новая": 0,
                    "В работе": 0,
                    "Завершено": 0,
                    "Отменено": 0
                },
                "tasks": []
            })

        task_status = task["status"] or ""

        if task_status in calendar_days[-1]["status_counts"]:
            calendar_days[-1]["status_counts"][task_status] += 1

        calendar_days[-1]["tasks"].append({
            "task": task,
            "workers": format_task_workers(task)
        })

    return templates.TemplateResponse(
        request=request,
        name="calendar.html",
        context={
            "tasks": tasks,
            "calendar_days": calendar_days,
            "workers": workers,
            "worker_loads": worker_loads,
            "worker_availability": worker_availability,
            "weekly_capacity_rows": weekly_capacity_rows,
            "weekly_capacity_days": weekly_capacity_days,
            "weekly_capacity_summary": weekly_capacity_summary,
            "smart_schedule_items": smart_schedule_items,
            "smart_schedule_summary": smart_schedule_summary,
            "availability_summary": availability_summary,
            "selected_worker": worker,
            "selected_month": month,
            "selected_status": status,
            "selected_availability": selected_availability,
            "selected_date": selected_date,
            "availability_date": availability_date,
            "selected_week_start": selected_week_start,
            "selected_week_end": selected_week_end,
            "selected_schedule_start": selected_schedule_start,
            "selected_schedule_days": selected_schedule_days,
            "selected_schedule_workers": selected_schedule_workers,
            "selected_schedule_duration": selected_schedule_duration,
            "previous_day_url": previous_day_url,
            "today_day_url": today_day_url,
            "next_day_url": next_day_url,
            "previous_week_url": previous_week_url,
            "current_week_url": current_week_url,
            "next_week_url": next_week_url,
            "username": username,
            "role": role,
            "settings": settings
        }
    )


@router.get("/api/calendar/smart-schedule")
def api_calendar_smart_schedule(
    request: Request,
    start: str = "",
    days: int = 14,
    workers: int = 1,
    worker: str = "",
    duration: int = 60,
):
    username = get_user(request)

    if not username:
        return JSONResponse(
            {"ok": False, "error": "unauthorized"},
            status_code=401,
        )

    role = get_role(username)

    if role not in ("boss", "manager"):
        return JSONResponse(
            {"ok": False, "error": "forbidden"},
            status_code=403,
        )

    company_id = get_user_company_id(username)

    if not has_feature(company_id, "calendar"):
        return JSONResponse(
            {"ok": False, "error": "feature_disabled"},
            status_code=403,
        )

    try:
        start_date = datetime.strptime(
            str(start or datetime.now().strftime("%Y-%m-%d")),
            "%Y-%m-%d",
        ).date()
    except Exception:
        return JSONResponse(
            {"ok": False, "error": "invalid_start_date"},
            status_code=400,
        )

    if start_date < datetime.now().date():
        start_date = datetime.now().date()

    search_days = days if days in (7, 14, 30) else 14
    required_workers = min(max(int(workers or 1), 1), 5)
    selected_duration = duration if duration in (30, 60, 90, 120) else 60
    preferred_worker = str(worker or "").strip()
    conn = connect()
    c = conn.cursor()
    worker_rows = c.execute("""
    SELECT username, daily_capacity
    FROM users
    WHERE company_id=?
      AND role='worker'
      AND COALESCE(is_active, 1)=1
    ORDER BY username
    """, (company_id,)).fetchall()
    worker_capacities = {
        row["username"]: max(1, int(row["daily_capacity"] or 3))
        for row in worker_rows
    }

    if preferred_worker and preferred_worker not in worker_capacities:
        conn.close()
        return JSONResponse(
            {"ok": False, "error": "invalid_worker"},
            status_code=400,
        )

    end_date = start_date + timedelta(days=search_days - 1)
    assignment_rows = c.execute("""
    SELECT id, worker, workers,
           substr(task_date, 1, 10) AS work_date,
           time_from, time_to
    FROM tasks
    WHERE archived=0
      AND company_id=?
      AND status NOT IN ('Завершено', 'Отменено')
      AND task_date IS NOT NULL
      AND task_date != ''
      AND substr(task_date, 1, 10) BETWEEN ? AND ?
    """, (
        company_id,
        start_date.strftime("%Y-%m-%d"),
        end_date.strftime("%Y-%m-%d"),
    )).fetchall()
    unavailable_dates, _ = get_worker_unavailability(
        c,
        company_id,
        worker_capacities.keys(),
        start_date.strftime("%Y-%m-%d"),
        end_date.strftime("%Y-%m-%d"),
    )
    conn.close()
    schedule_assignments = [
        {
            "task_id": row["id"],
            "date": row["work_date"],
            "workers": get_task_worker_names(row),
            "time_from": row["time_from"],
            "time_to": row["time_to"],
        }
        for row in assignment_rows
    ]
    result = build_scheduling_recommendations(
        worker_capacities=worker_capacities,
        assignments=schedule_assignments,
        start_date=start_date,
        search_days=search_days,
        required_workers=required_workers,
        preferred_worker=preferred_worker,
        unavailable_dates=unavailable_dates,
        limit=search_days,
    )
    actionable_items = add_time_slots_to_recommendations(
        result["items"],
        schedule_assignments,
        duration_minutes=selected_duration,
    )
    result["items"] = actionable_items[:12]
    result["summary"]["found"] = len(actionable_items)
    result["summary"]["time_slots_found"] = sum(
        item["available_time_slot_count"]
        for item in actionable_items
    )

    for item in result["items"]:
        primary_time_slot = item["primary_time_slot"]
        item["create_url"] = "/create-task?" + urlencode({
            "task_date": item["date"],
            "time_from": primary_time_slot["time_from"],
            "time_to": primary_time_slot["time_to"],
            "worker": item["worker_names"][0],
            "workers_csv": ",".join(item["worker_names"]),
            "return_to": "calendar",
        })

    return {
        "ok": True,
        "company_id": company_id,
        "start": start_date.strftime("%Y-%m-%d"),
        "end": end_date.strftime("%Y-%m-%d"),
        "preferred_worker": preferred_worker,
        "duration_minutes": selected_duration,
        "summary": result["summary"],
        "items": result["items"],
    }
