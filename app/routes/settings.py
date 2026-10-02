"""Company settings routes."""

import csv
import io
from datetime import datetime
from urllib.parse import urlencode

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response

from app.database import connect
from app.deps import get_role, get_user, require_route_company_context
from app.services.common import (
    BUSINESS_PRESETS,
    CORE_FEATURES,
    FEATURE_DEFINITIONS,
    INDUSTRY_OPTIONS,
    build_dashboard_links,
    ensure_company_features,
    get_company_features,
    get_company_settings,
    get_company_mode,
    get_industry_label,
    get_role_title,
)
from app.services.plans import (
    get_company_user_limit_usage,
    get_plan_feature_flags,
    get_plan_label,
    get_plan_options,
    get_recommended_user_limit_plan,
    normalize_plan,
    plan_allows_active_users,
)
from app.templating import templates

router = APIRouter()


def run_automation_event(*args, **kwargs):
    from app.main import run_automation_event as _impl

    return _impl(*args, **kwargs)


def send_message(*args, **kwargs):
    from app.main import send_message as _impl

    return _impl(*args, **kwargs)


def apply_business_preset(*args, **kwargs):
    from app.main import apply_business_preset as _impl

    return _impl(*args, **kwargs)


def build_settings_links(*args, **kwargs):
    from app.main import build_settings_links as _impl

    return _impl(*args, **kwargs)


def record_company_settings_history(*args, **kwargs):
    from app.main import record_company_settings_history as _impl

    return _impl(*args, **kwargs)


def update_company_features(*args, **kwargs):
    from app.main import update_company_features as _impl

    return _impl(*args, **kwargs)

@router.get("/settings", response_class=HTMLResponse)
async def settings_page(request: Request):

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
    features = get_company_features(company_id)
    user_limit_usage = get_company_user_limit_usage(company_id, settings)
    recommended_plan = None

    if user_limit_usage["tone"] in ("warning", "danger"):
        recommended_plan = get_recommended_user_limit_plan(
            user_limit_usage["plan"],
            user_limit_usage["active_users_count"],
        )

    return templates.TemplateResponse(
        request,
        "settings.html",
        {
            "request": request,
            "username": username,
            "role": role,
            "settings": settings,
            "features": features,
            "feature_definitions": FEATURE_DEFINITIONS,
            "core_features": CORE_FEATURES,
            "user_limit_usage": user_limit_usage,
            "recommended_plan": recommended_plan,
            "plan_options": get_plan_options(),
            "industry_options": INDUSTRY_OPTIONS,
            "business_presets": BUSINESS_PRESETS,
            "links": build_settings_links(),
        }
    )


def normalize_settings_history_date(value):
    value = str(value or "").strip()

    if not value:
        return ""

    try:
        datetime.strptime(value, "%Y-%m-%d")
        return value
    except ValueError:
        return ""


def normalize_settings_history_filters(action="all", date_from="", date_to=""):
    selected_action = str(action or "all").strip()

    if not selected_action:
        selected_action = "all"

    return {
        "action": selected_action,
        "date_from": normalize_settings_history_date(date_from),
        "date_to": normalize_settings_history_date(date_to),
    }


def build_settings_history_export_url(filters):
    params = {}

    if filters["action"] != "all":
        params["action"] = filters["action"]

    if filters["date_from"]:
        params["date_from"] = filters["date_from"]

    if filters["date_to"]:
        params["date_to"] = filters["date_to"]

    if not params:
        return "/settings/history/export"

    return "/settings/history/export?" + urlencode(params)


def fetch_company_settings_history(c, company_id, filters, limit=None):
    where = ["company_id=?"]
    params = [company_id]

    if filters["action"] != "all":
        where.append("action=?")
        params.append(filters["action"])

    if filters["date_from"]:
        where.append("date(created_at) >= date(?)")
        params.append(filters["date_from"])

    if filters["date_to"]:
        where.append("date(created_at) <= date(?)")
        params.append(filters["date_to"])

    query = f"""
    SELECT *
    FROM company_settings_history
    WHERE {' AND '.join(where)}
    ORDER BY id DESC
    """

    if limit:
        query += "\nLIMIT ?"
        params.append(limit)

    return c.execute(query, params).fetchall()


def build_settings_history_summary(history):
    actors = {
        str(event["actor_username"] or "").strip()
        for event in history
        if str(event["actor_username"] or "").strip()
    }

    latest_event = history[0] if history else None

    return {
        "events_count": len(history),
        "actors_count": len(actors),
        "latest_at": latest_event["created_at"] if latest_event else "",
        "latest_action": latest_event["action"] if latest_event else "",
    }


@router.get("/settings/history", response_class=HTMLResponse)
async def settings_history_page(
    request: Request,
    action: str = "all",
    date_from: str = "",
    date_to: str = "",
):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role not in ("boss", "superadmin"):
        return RedirectResponse("/", status_code=302)

    company_id, missing_company_response = require_route_company_context(
        username,
        role,
    )

    if missing_company_response:
        return missing_company_response

    filters = normalize_settings_history_filters(action, date_from, date_to)

    conn = connect()
    c = conn.cursor()
    action_options = c.execute("""
    SELECT DISTINCT action
    FROM company_settings_history
    WHERE company_id=?
      AND action IS NOT NULL
      AND action != ''
    ORDER BY action
    """, (company_id,)).fetchall()
    history = fetch_company_settings_history(c, company_id, filters, limit=200)
    conn.close()
    summary = build_settings_history_summary(history)

    return templates.TemplateResponse(
        request,
        "settings_history.html",
        {
            "request": request,
            "username": username,
            "role": role,
            "history": history,
            "filters": filters,
            "action_options": [row["action"] for row in action_options],
            "export_url": build_settings_history_export_url(filters),
            "summary": summary,
        },
    )


@router.get("/settings/history/export")
async def settings_history_export(
    request: Request,
    action: str = "all",
    date_from: str = "",
    date_to: str = "",
):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role not in ("boss", "superadmin"):
        return RedirectResponse("/", status_code=302)

    company_id, missing_company_response = require_route_company_context(
        username,
        role,
    )

    if missing_company_response:
        return missing_company_response

    filters = normalize_settings_history_filters(action, date_from, date_to)

    conn = connect()
    c = conn.cursor()
    history = fetch_company_settings_history(c, company_id, filters)
    conn.close()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "Дата",
        "Действие",
        "Детали",
        "Было",
        "Стало",
        "Кто изменил",
    ])

    for event in history:
        writer.writerow([
            event["created_at"] or "",
            event["action"] or "",
            event["details"] or "",
            event["old_value"] or "",
            event["new_value"] or "",
            event["actor_username"] or "",
        ])

    return Response(
        content="\ufeff" + output.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": (
                "attachment; filename=company_settings_history.csv"
            )
        },
    )


@router.post("/settings")
async def update_settings(request: Request):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role not in ("boss", "superadmin"):
        return RedirectResponse("/", status_code=302)

    form = await request.form()

    company_name = (form.get("company_name") or "").strip()
    phone = (form.get("phone") or "").strip()
    email = (form.get("email") or "").strip()
    telegram_chat_id = (form.get("telegram_chat_id") or "").strip()
    address = (form.get("address") or "").strip()
    tax_number = (form.get("tax_number") or "").strip()
    bank_details = (form.get("bank_details") or "").strip()
    plan = (form.get("plan") or "basic").strip()
    industry = (form.get("industry") or "field_service").strip()
    task_label = (form.get("task_label") or "Заявка").strip()
    worker_label = (form.get("worker_label") or "Исполнитель").strip()
    client_label = (form.get("client_label") or "Клиент").strip()
    service_label = (form.get("service_label") or "Услуга").strip()
    mode = (form.get("mode") or "company").strip()

    if mode not in ("company", "master"):
        mode = "company"

    allowed_industries = [industry_key for industry_key, _ in INDUSTRY_OPTIONS]

    plan = normalize_plan(plan)
    if industry not in allowed_industries:
        industry = "field_service"

    plan_features = get_plan_feature_flags(plan)
    one_c_enabled = plan_features["one_c_enabled"]
    calls_enabled = plan_features["calls_enabled"]
    ai_calls_enabled = plan_features["ai_calls_enabled"]
    company_id, missing_company_response = require_route_company_context(username, role)

    if missing_company_response:
        return missing_company_response

    current_settings = get_company_settings(company_id)
    current_plan = normalize_plan(
        current_settings["plan"]
        if current_settings and "plan" in current_settings.keys()
        else "basic"
    )
    current_industry = str(
        current_settings["industry"] or "field_service"
    )
    user_limit_usage = get_company_user_limit_usage(
        company_id,
        current_settings,
    )

    if (
        plan != current_plan
        and not plan_allows_active_users(
            plan,
            user_limit_usage["active_users_count"],
        )
    ):
        return RedirectResponse(
            "/settings?error=plan_user_limit",
            status_code=302,
        )

    settings_history_changes = []

    if plan != current_plan:
        settings_history_changes.append(
            f"Тариф: {get_plan_label(current_plan)} → {get_plan_label(plan)}"
        )

    if industry != current_industry:
        settings_history_changes.append(
            (
                f"Сфера: {get_industry_label(current_industry)} → "
                f"{get_industry_label(industry)}"
            )
        )


    if form.get("apply_business_preset") == "1":
        apply_business_preset(company_id, industry)
    else:
        update_company_features(company_id, form)

    conn = connect()
    c = conn.cursor()

    c.execute("""
    INSERT OR IGNORE INTO company_settings (
        company_id, company_name, phone, email, address, tax_number, bank_details, plan,
        industry, task_label, worker_label, client_label, service_label,
        one_c_enabled, calls_enabled, ai_calls_enabled, updated_at
    )
    VALUES (?, '', '', '', '', '', '', 'basic', 'field_service',
            'Заявка', 'Исполнитель', 'Клиент', 'Услуга', 0, 0, 0, '')
    """, (company_id,))

    c.execute("""
    UPDATE company_settings
    SET company_name=?, phone=?, email=?, address=?, tax_number=?, bank_details=?,
        plan=?, industry=?, task_label=?, worker_label=?, client_label=?, service_label=?,
        one_c_enabled=?, calls_enabled=?, ai_calls_enabled=?, mode=?, updated_at=?
    WHERE company_id=?
    """, (
        company_name,
        phone,
        email,
        address,
        tax_number,
        bank_details,
        plan,
        industry,
        task_label,
        worker_label,
        client_label,
        service_label,
        one_c_enabled,
        calls_enabled,
        ai_calls_enabled,
        mode,
        datetime.now().strftime("%Y-%m-%d %H:%M"),
        company_id
    ))

    conn.commit()

    conn.close()

    if settings_history_changes:
        record_company_settings_history(
            company_id,
            username,
            "Настройки компании обновлены",
            "; ".join(settings_history_changes),
            get_plan_label(current_plan),
            get_plan_label(plan),
        )

    try:
        send_message(
            f"""
⚙️ Настройки компании обновлены

Компания: {company_name}
Изменил: {username} ({get_role_title(role)})
"""
        )
    except Exception:
        pass

    run_automation_event(
        company_id,
        "company_settings_updated",
        "company",
        company_id,
        f"Настройки компании обновлены: {company_name or 'Без названия'}",
        "/settings",
    )

    return RedirectResponse("/settings?updated=1", status_code=302)
