"""Billing pages, invoices and subscription cron routes."""

import csv
import hmac
import io
import os
from datetime import datetime

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response

from app.database import connect
from app.deps import (
    get_role,
    get_user,
    get_user_company_id,
    require_route_company_context,
)
from app.services.billing import (
    BILLING_INVOICE_STATUSES,
    build_billing_invoice_rows,
    build_billing_invoice_summary,
    build_billing_invoices_export_url,
    build_billing_next_payment_summary,
    build_platform_billing_invoice_activity_summary,
    build_platform_billing_invoice_links,
    build_platform_billing_monthly_summary,
    build_platform_billing_risk_summary,
    fetch_billing_invoice,
    fetch_billing_invoices,
    fetch_billing_plan_history,
    fetch_platform_billing_invoice_activity,
    generate_company_billing_invoice,
    get_billing_invoice_status_meta,
    get_billing_invoice_status_options,
    get_platform_billing_invoice_summary,
    normalize_billing_invoice_filter,
    normalize_billing_invoice_status,
    normalize_billing_period,
    record_platform_billing_activity,
)
from app.services.common import (
    build_dashboard_links,
    get_company_settings,
)
from app.services.plans import (
    PLAN_DEFINITIONS,
    get_company_user_limit_usage,
    get_plan_feature_flags,
    get_plan_label,
    get_plan_price_label,
    get_plan_user_limit,
    get_recommended_user_limit_plan,
    normalize_plan,
)
from app.services.subscriptions import (
    get_company_subscription,
    run_subscription_reminders,
)
from app.templating import templates

router = APIRouter()

@router.get("/billing", response_class=HTMLResponse)
async def billing_page(request: Request):

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
    plan = normalize_plan(
        settings["plan"] if settings and "plan" in settings.keys() else "basic"
    )
    plan_features = get_plan_feature_flags(plan)
    user_limit = get_plan_user_limit(plan)
    user_limit_usage = get_company_user_limit_usage(company_id, settings)
    recommended_plan = None

    if user_limit_usage["tone"] in ("warning", "danger"):
        recommended_plan = get_recommended_user_limit_plan(
            plan,
            user_limit_usage["active_users_count"],
        )

    conn = connect()
    c = conn.cursor()
    plan_history = fetch_billing_plan_history(c, company_id)
    billing_invoices = fetch_billing_invoices(c, company_id)
    conn.close()
    billing_invoice_summary = build_billing_invoice_summary(billing_invoices)
    billing_risk_summary = build_platform_billing_risk_summary(billing_invoices)
    next_payment_summary = build_billing_next_payment_summary(billing_invoices)
    recent_billing_invoices = billing_invoices[:3]

    plan_names = {
        plan_key: definition["label"]
        for plan_key, definition in PLAN_DEFINITIONS.items()
    }
    plan_prices = {
        plan_key: get_plan_price_label(plan_key)
        for plan_key in PLAN_DEFINITIONS
    }
    subscription = get_company_subscription(company_id)

    return templates.TemplateResponse(
        request,
        "billing.html",
        {
            "request": request,
            "username": username,
            "role": role,
            "settings": settings,
            "plan": plan,
            "plan_features": plan_features,
            "user_limit": user_limit,
            "user_limit_usage": user_limit_usage,
            "recommended_plan": recommended_plan,
            "plan_names": plan_names,
            "plan_prices": plan_prices,
            "subscription": subscription,
            "plan_history": plan_history,
            "billing_invoice_summary": billing_invoice_summary,
            "billing_risk_summary": billing_risk_summary,
            "next_payment_summary": next_payment_summary,
            "recent_billing_invoices": recent_billing_invoices,
        }
    )


@router.get("/api/billing")
async def api_billing(request: Request):

    username = get_user(request)

    if not username:
        return JSONResponse({"error": "auth_required"}, status_code=401)

    role = get_role(username)

    if role not in ("boss", "superadmin"):
        return JSONResponse({"error": "forbidden"}, status_code=403)

    company_id = get_user_company_id(username)

    if not company_id:
        return JSONResponse({"error": "company_required"}, status_code=400)

    settings = get_company_settings(company_id)
    plan = normalize_plan(
        settings["plan"] if settings and "plan" in settings.keys() else "basic"
    )
    plan_features = get_plan_feature_flags(plan)
    user_limit_usage = get_company_user_limit_usage(company_id, settings)
    recommended_plan = None

    if user_limit_usage["tone"] in ("warning", "danger"):
        recommended_plan = get_recommended_user_limit_plan(
            plan,
            user_limit_usage["active_users_count"],
        )

    conn = connect()
    c = conn.cursor()
    invoices = fetch_billing_invoices(c, company_id)
    conn.close()

    return {
        "ok": True,
        "company_id": company_id,
        "plan": {
            "code": plan,
            "label": get_plan_label(plan),
            "price_label": get_plan_price_label(plan),
            "user_limit": get_plan_user_limit(plan),
            "user_limit_label": user_limit_usage["user_limit_label"],
            "features": plan_features,
        },
        "user_limit_usage": user_limit_usage,
        "recommended_plan": recommended_plan,
        "invoice_summary": build_billing_invoice_summary(invoices),
        "invoice_risk_summary": build_platform_billing_risk_summary(invoices),
        "next_payment": build_billing_next_payment_summary(invoices),
        "recent_invoices": invoices[:3],
        "links": {
            "page": "/billing",
            "export": "/billing/export",
            "invoices": "/billing/invoices",
            "invoices_api": "/api/billing/invoices",
        },
    }


@router.get("/billing/export")
async def billing_export(request: Request):

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
    plan = normalize_plan(
        settings["plan"] if settings and "plan" in settings.keys() else "basic"
    )
    user_limit_usage = get_company_user_limit_usage(company_id, settings)

    conn = connect()
    c = conn.cursor()
    plan_history = fetch_billing_plan_history(c, company_id, limit=None)
    billing_invoices = fetch_billing_invoices(c, company_id)
    conn.close()
    billing_invoice_summary = build_billing_invoice_summary(billing_invoices)
    billing_risk_summary = build_platform_billing_risk_summary(billing_invoices)
    next_payment_summary = build_billing_next_payment_summary(billing_invoices)

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Тарифы компании"])
    writer.writerow(["Текущий тариф", get_plan_label(plan)])
    writer.writerow(["Активные пользователи", user_limit_usage["active_users_count"]])
    writer.writerow(["Лимит пользователей", user_limit_usage["user_limit_label"]])
    writer.writerow(["Статус лимита", user_limit_usage["status"]])
    writer.writerow([])
    writer.writerow([
        "Тариф",
        "Лимит пользователей",
        "Стоимость",
        "Звонки",
        "1С",
        "ИИ-звонки",
        "Текущий",
    ])

    for plan_key, definition in PLAN_DEFINITIONS.items():
        user_limit_label = (
            str(definition["user_limit"])
            if definition["user_limit"] is not None
            else "Без лимита"
        )
        writer.writerow([
            definition["label"],
            user_limit_label,
            get_plan_price_label(plan_key),
            "Да" if definition["calls_enabled"] else "Нет",
            "Да" if definition["one_c_enabled"] else "Нет",
            "Да" if definition["ai_calls_enabled"] else "Нет",
            "Да" if plan_key == plan else "Нет",
        ])

    writer.writerow([])
    writer.writerow(["Состояние счетов"])
    writer.writerow(["Показатель", "Значение"])
    writer.writerow(["Всего счетов", billing_invoice_summary["count"]])
    writer.writerow(["Начислено", billing_invoice_summary["total_amount_label"]])
    writer.writerow(["Оплачено", billing_invoice_summary["paid_amount_label"]])
    writer.writerow(["К оплате", billing_invoice_summary["unpaid_amount_label"]])
    writer.writerow([
        "Просрочено по дате",
        billing_risk_summary["overdue_by_date_count"],
    ])
    writer.writerow([
        "Сумма просрочки",
        billing_risk_summary["overdue_by_date_amount_label"],
    ])
    writer.writerow([
        "Скоро к оплате",
        billing_risk_summary["due_soon_count"],
    ])
    writer.writerow([
        "Сумма скоро к оплате",
        billing_risk_summary["due_soon_amount_label"],
    ])
    writer.writerow(["Черновики", billing_risk_summary["draft_count"]])
    writer.writerow(["Выставленные", billing_risk_summary["issued_count"]])
    if next_payment_summary["has_invoice"]:
        next_invoice = next_payment_summary["invoice"]
        writer.writerow([])
        writer.writerow(["Ближайший платёж"])
        writer.writerow(["Счёт", next_invoice["invoice_number"] or next_invoice["id"]])
        writer.writerow(["Срок", next_invoice["due_date"] or "Не указан"])
        writer.writerow(["Сумма", next_invoice["amount_label"]])
        writer.writerow(["Статус", next_payment_summary["label"]])

    writer.writerow([])
    writer.writerow(["История тарифа"])
    writer.writerow(["Дата", "Действие", "Детали", "Было", "Стало", "Кто изменил"])
    for event in plan_history:
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
            "Content-Disposition": "attachment; filename=billing_plans.csv"
        },
    )


@router.get("/billing/invoices", response_class=HTMLResponse)
async def billing_invoices_page(request: Request, status: str = "all"):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role not in ("boss", "superadmin"):
        return RedirectResponse("/", status_code=302)

    company_id, missing_company_response = require_route_company_context(username, role)

    if missing_company_response:
        return missing_company_response

    status_filter = normalize_billing_invoice_filter(status)

    conn = connect()
    c = conn.cursor()
    invoices = fetch_billing_invoices(c, company_id, status_filter=status_filter)
    conn.close()
    summary = build_billing_invoice_summary(invoices)
    monthly_summary = build_platform_billing_monthly_summary(invoices)
    return templates.TemplateResponse(
        request,
        "billing_invoices.html",
        {
            "request": request,
            "username": username,
            "role": role,
            "invoices": invoices,
            "summary": summary,
            "monthly_summary": monthly_summary,
            "status_filter": status_filter,
            "status_options": get_billing_invoice_status_options(),
            "export_url": build_billing_invoices_export_url(status_filter),
        },
    )


@router.get("/api/billing/invoices")
async def api_billing_invoices(request: Request, status: str = "all"):

    username = get_user(request)

    if not username:
        return JSONResponse({"error": "auth_required"}, status_code=401)

    role = get_role(username)

    if role not in ("boss", "superadmin"):
        return JSONResponse({"error": "forbidden"}, status_code=403)

    company_id = get_user_company_id(username)

    if not company_id:
        return JSONResponse({"error": "company_required"}, status_code=400)

    status_filter = normalize_billing_invoice_filter(status)

    conn = connect()
    c = conn.cursor()
    invoices = fetch_billing_invoices(
        c,
        company_id,
        status_filter=status_filter,
    )
    conn.close()
    summary = build_billing_invoice_summary(invoices)
    monthly_summary = build_platform_billing_monthly_summary(invoices)

    return {
        "ok": True,
        "filters": {
            "status": status_filter,
            "company_id": company_id,
        },
        "summary": summary,
        "monthly_summary": monthly_summary,
        "export_url": build_billing_invoices_export_url(status_filter),
        "invoices": invoices,
    }


@router.post("/billing/invoices/generate")
async def generate_billing_invoice(request: Request):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role not in ("boss", "superadmin"):
        return RedirectResponse("/", status_code=302)

    company_id, missing_company_response = require_route_company_context(username, role)

    if missing_company_response:
        return missing_company_response

    form = await request.form()
    period = normalize_billing_period(form.get("period") or "")
    result = generate_company_billing_invoice(company_id, period, username)
    invoice = result["invoice"]
    flag = "created" if result["created"] else "exists"

    return RedirectResponse(
        f"/billing/invoices/{invoice['id']}?{flag}=1",
        status_code=302,
    )


@router.get("/billing/invoices/export")
async def billing_invoices_export(request: Request, status: str = "all"):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role not in ("boss", "superadmin"):
        return RedirectResponse("/", status_code=302)

    company_id, missing_company_response = require_route_company_context(username, role)

    if missing_company_response:
        return missing_company_response

    status_filter = normalize_billing_invoice_filter(status)

    conn = connect()
    c = conn.cursor()
    invoices = fetch_billing_invoices(c, company_id, status_filter=status_filter)
    conn.close()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "Номер",
        "Период",
        "Тариф",
        "Сумма",
        "Валюта",
        "Статус",
        "Оплатить до",
        "Оплачен",
        "Примечание",
        "Создан",
    ])

    for invoice in invoices:
        writer.writerow([
            invoice["invoice_number"] or "",
            invoice["period"] or "",
            invoice["plan_label"],
            invoice["amount"] or 0,
            invoice["currency"] or "RUB",
            invoice["status_label"],
            invoice["due_date"] or "",
            invoice["paid_at"] or "",
            invoice["notes"] or "",
            invoice["created_at"] or "",
        ])

    filename = "billing_invoices.csv"

    if status_filter != "all":
        filename = f"billing_invoices_{status_filter}.csv"

    return Response(
        content="\ufeff" + output.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f"attachment; filename={filename}"
        },
    )


@router.get("/billing/invoices/{invoice_id}/export")
async def billing_invoice_detail_export(request: Request, invoice_id: int):

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

    conn = connect()
    c = conn.cursor()
    invoice = fetch_billing_invoice(c, company_id, invoice_id)
    invoice_activity = (
        fetch_platform_billing_invoice_activity(c, invoice)
        if invoice
        else []
    )
    conn.close()

    if not invoice:
        return RedirectResponse(
            "/billing/invoices?error=invoice_not_found",
            status_code=302,
        )

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Счёт платформы"])
    writer.writerow(["ID счёта", invoice["id"]])
    writer.writerow(["Номер", invoice["invoice_number"] or ""])
    writer.writerow(["Период", invoice["period"] or ""])
    writer.writerow(["Тариф", invoice["plan_label"]])
    writer.writerow(["Сумма", invoice["amount"] or 0])
    writer.writerow(["Валюта", invoice["currency"] or "RUB"])
    writer.writerow(["Статус", invoice["status_label"]])
    writer.writerow(["Оплатить до", invoice["due_date"] or ""])
    writer.writerow(["Оплачен", invoice["paid_at"] or ""])
    writer.writerow(["Создан", invoice["created_at"] or ""])
    writer.writerow(["Примечание", invoice["notes"] or ""])
    writer.writerow([])
    writer.writerow(["История счёта"])
    writer.writerow(["Действие", "Подробности", "Выполнил", "Дата"])

    for event in invoice_activity:
        writer.writerow([
            event["action"] or "",
            event["details"] or "",
            event["actor_username"] or "",
            event["created_at"] or "",
        ])

    return Response(
        content="\ufeff" + output.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": (
                f"attachment; filename=billing_invoice_{invoice_id}.csv"
            )
        },
    )


@router.get("/api/billing/invoices/{invoice_id}")
async def api_billing_invoice_detail(request: Request, invoice_id: int):

    username = get_user(request)

    if not username:
        return JSONResponse({"error": "auth_required"}, status_code=401)

    role = get_role(username)

    if role not in ("boss", "superadmin"):
        return JSONResponse({"error": "forbidden"}, status_code=403)

    company_id = get_user_company_id(username)

    if not company_id:
        return JSONResponse({"error": "company_required"}, status_code=400)

    conn = connect()
    c = conn.cursor()
    invoice = fetch_billing_invoice(c, company_id, invoice_id)
    invoice_activity = (
        fetch_platform_billing_invoice_activity(c, invoice)
        if invoice
        else []
    )
    conn.close()

    if not invoice:
        return JSONResponse(
            {"error": "invoice_not_found"},
            status_code=404,
        )

    return {
        "ok": True,
        "invoice": invoice,
        "activity": invoice_activity,
        "activity_summary": (
            build_platform_billing_invoice_activity_summary(invoice_activity)
        ),
        "export_url": f"/billing/invoices/{invoice_id}/export",
    }


@router.get("/billing/invoices/{invoice_id}", response_class=HTMLResponse)
async def billing_invoice_detail_page(request: Request, invoice_id: int):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role not in ("boss", "superadmin"):
        return RedirectResponse("/", status_code=302)

    company_id, missing_company_response = require_route_company_context(username, role)

    if missing_company_response:
        return missing_company_response

    conn = connect()
    c = conn.cursor()
    invoice = fetch_billing_invoice(c, company_id, invoice_id)
    invoice_activity = (
        fetch_platform_billing_invoice_activity(c, invoice)
        if invoice
        else []
    )
    conn.close()

    if not invoice:
        return RedirectResponse(
            "/billing/invoices?error=invoice_not_found",
            status_code=302,
        )

    return templates.TemplateResponse(
        request,
        "billing_invoice_detail.html",
        {
            "request": request,
            "username": username,
            "role": role,
            "invoice": invoice,
            "invoice_activity": invoice_activity,
            "activity_summary": (
                build_platform_billing_invoice_activity_summary(
                    invoice_activity,
                )
            ),
        },
    )



@router.post("/automation/cron/subscription-reminders")
async def run_subscription_reminders_cron(request: Request):
    cron_secret = (os.getenv("AUTOMATION_CRON_SECRET") or "").strip()

    if not cron_secret:
        return JSONResponse(
            {"ok": False, "error": "AUTOMATION_CRON_SECRET is not configured"},
            status_code=503,
        )
    token = (request.headers.get("x-automation-secret") or "").strip()
    if not token or not hmac.compare_digest(token, cron_secret):
        return JSONResponse(
            {"ok": False, "error": "forbidden"},
            status_code=403,
        )

    summary = run_subscription_reminders()
    return {"ok": True, "summary": summary}
