"""Platform (superadmin) routes: companies, modules, presets, billing, readiness, health."""

import csv
import io
from datetime import datetime, timedelta
from urllib.parse import urlencode

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response

from app.database import connect
from app.deps import get_role, get_user, get_user_company_id, is_superadmin
from app.templating import templates

router = APIRouter()


def _main_attr(name):
    from app import main

    return getattr(main, name)


import json
from uuid import uuid4

from app.database import get_database_error_types
from app.services.background_jobs import (
    get_background_queue_status,
    get_recent_background_jobs,
)
from app.services.a3_cycle_history import get_a3_cycle_reliability
from app.services.a3_followup_analytics import (
    a3_followup_analytics_csv_rows,
    get_a3_followup_analytics,
)
from app.services.a3_followup_quality_monitor import (
    a3_followup_quality_alert_csv_rows,
    acknowledge_a3_followup_quality_alert,
    build_a3_followup_quality_alerts_url,
    get_a3_followup_quality_alerts,
    get_a3_followup_quality_monitor_overview,
    reopen_a3_followup_quality_alert,
    resolve_a3_followup_quality_alert,
    run_a3_followup_quality_monitor,
)
from app.services.a3_followup_quality_sla import (
    get_a3_followup_quality_sla_overview,
    run_a3_followup_quality_sla_monitor,
)
from app.services.a3_incident_followup_monitor import (
    get_a3_followup_monitor_overview,
    run_a3_incident_followup_monitor,
)
from app.services.a3_incident_followups import (
    build_a3_followups_url,
    create_a3_incident_followup,
    get_a3_incident_followups,
    review_a3_incident_followup,
    update_a3_incident_followup,
)
from app.services.a3_platform_health import get_a3_platform_health
from app.services.a3_platform_incident_analytics import (
    get_a3_platform_incident_analytics,
)
from app.services.a3_platform_incident_reviews import (
    build_a3_incident_reviews_url,
    get_a3_platform_incident_reviews,
    save_a3_platform_incident_review,
)
from app.services.a3_platform_incidents import (
    acknowledge_a3_platform_incident,
    add_a3_platform_incident_note,
    assign_a3_platform_incident,
    build_a3_platform_incidents_url,
    get_a3_platform_incident_admins,
    get_a3_platform_incidents,
)
from app.services.a3_scheduler_watchdog import (
    get_a3_scheduler_watchdog_history,
    get_a3_scheduler_watchdog_trend,
)
from app.services.billing import (
    BILLING_INVOICE_STATUSES,
    build_billing_invoice_summary,
    build_platform_billing_invoice_activity_summary,
    build_platform_billing_links,
    build_platform_billing_monthly_summary,
    build_platform_billing_risk_summary,
    build_platform_billing_url,
    create_platform_billing_reminders,
    fetch_platform_billing_invoice,
    fetch_platform_billing_invoice_activity,
    fetch_platform_billing_invoices,
    generate_company_billing_invoice,
    get_billing_invoice_status_meta,
    get_billing_invoice_status_options,
    get_platform_billing_company_options,
    normalize_billing_invoice_filter,
    normalize_billing_period,
    normalize_platform_billing_company_id,
    notify_platform_billing_status_change,
    record_platform_billing_activity,
    sync_platform_billing_overdue_invoices,
)
from app.services.plans import (
    get_company_user_limit_usage,
    get_plan_feature_flags,
    get_plan_label,
    get_plan_options,
    normalize_plan,
    plan_allows_active_users,
)


import json as _json_module
import uuid
from uuid import uuid4

from app.database import connect as _connect_unused  # noqa: F401
from app.database import get_database_error_types
from app.services.common import (
    FEATURE_DEFINITIONS,
    HTTP_OBSERVABILITY_IGNORED_PATH_PREFIXES,
    HTTP_SLOW_REQUEST_THRESHOLD_MS,
    SYSTEM_EVENT_ALERT_HOURS,
    SYSTEM_EVENT_RETENTION_DAYS,
    SYSTEM_EVENT_RETENTION_KEEP,
    INDUSTRY_OPTIONS,
    create_notification,
    normalize_system_event_severity,
    get_company_settings,
    get_industry_label,
    has_feature,
    role_label,
)
from app.services.plans import (
    get_company_user_limit_usage,
    get_plan_feature_flags,
    get_plan_label,
    get_plan_options,
    normalize_plan,
    plan_allows_active_users,
)
from app.services.billing import (
    BILLING_INVOICE_STATUSES,
    build_billing_invoice_summary,
    build_platform_billing_invoice_activity_summary,
    build_platform_billing_links,
    build_platform_billing_monthly_summary,
    build_platform_billing_risk_summary,
    build_platform_billing_url,
    create_platform_billing_reminders,
    fetch_platform_billing_invoice,
    fetch_platform_billing_invoice_activity,
    fetch_platform_billing_invoices,
    generate_company_billing_invoice,
    get_billing_invoice_status_meta,
    get_billing_invoice_status_options,
    get_platform_billing_company_options,
    normalize_billing_invoice_filter,
    normalize_billing_period,
    normalize_platform_billing_company_id,
    notify_platform_billing_status_change,
    record_platform_billing_activity,
    sync_platform_billing_overdue_invoices,
)
from app.services.background_jobs import (
    get_background_queue_status,
    get_recent_background_jobs,
)
from app.services.a3_cycle_history import get_a3_cycle_reliability
from app.services.a3_followup_analytics import (
    a3_followup_analytics_csv_rows,
    get_a3_followup_analytics,
)
from app.services.a3_followup_quality_monitor import (
    a3_followup_quality_alert_csv_rows,
    acknowledge_a3_followup_quality_alert,
    build_a3_followup_quality_alerts_url,
    get_a3_followup_quality_alerts,
    get_a3_followup_quality_monitor_overview,
    reopen_a3_followup_quality_alert,
    resolve_a3_followup_quality_alert,
    run_a3_followup_quality_monitor,
)
from app.services.a3_followup_quality_sla import (
    get_a3_followup_quality_sla_overview,
    run_a3_followup_quality_sla_monitor,
)
from app.services.a3_incident_followup_monitor import (
    get_a3_followup_monitor_overview,
    run_a3_incident_followup_monitor,
)
from app.services.a3_incident_followups import (
    build_a3_followups_url,
    create_a3_incident_followup,
    get_a3_incident_followups,
    review_a3_incident_followup,
    update_a3_incident_followup,
)
from app.services.a3_platform_health import get_a3_platform_health
from app.services.a3_platform_incident_analytics import (
    get_a3_platform_incident_analytics,
)
from app.services.a3_platform_incident_reviews import (
    build_a3_incident_reviews_url,
    get_a3_platform_incident_reviews,
    save_a3_platform_incident_review,
)
from app.services.a3_platform_incidents import (
    acknowledge_a3_platform_incident,
    add_a3_platform_incident_note,
    assign_a3_platform_incident,
    build_a3_platform_incidents_url,
    get_a3_platform_incident_admins,
    get_a3_platform_incidents,
)
from app.services.a3_scheduler_watchdog import (
    get_a3_scheduler_watchdog_history,
    get_a3_scheduler_watchdog_trend,
)


def send_message_to_chat(*args, **kwargs):
    return _main_attr("send_message_to_chat")(*args, **kwargs)


def HTTP_OBSERVABILITY_IGNORED_PATH_PREFIXES(*args, **kwargs):
    return _main_attr("HTTP_OBSERVABILITY_IGNORED_PATH_PREFIXES")(*args, **kwargs)



def a3_api_error(*args, **kwargs):
    return _main_attr("a3_api_error")(*args, **kwargs)

def acknowledge_calendar_scheduler_incident(*args, **kwargs):
    return _main_attr("acknowledge_calendar_scheduler_incident")(*args, **kwargs)

def add_calendar_scheduler_incident_note(*args, **kwargs):
    return _main_attr("add_calendar_scheduler_incident_note")(*args, **kwargs)

def apply_business_preset(*args, **kwargs):
    return _main_attr("apply_business_preset")(*args, **kwargs)

def build_platform_calendar_health_filter_url(*args, **kwargs):
    return _main_attr("build_platform_calendar_health_filter_url")(*args, **kwargs)

def build_platform_calendar_health_links(*args, **kwargs):
    return _main_attr("build_platform_calendar_health_links")(*args, **kwargs)

def build_platform_calendar_health_queue_url(*args, **kwargs):
    return _main_attr("build_platform_calendar_health_queue_url")(*args, **kwargs)

def build_platform_calendar_incident_analytics_links(*args, **kwargs):
    return _main_attr("build_platform_calendar_incident_analytics_links")(*args, **kwargs)

def build_platform_companies_url(*args, **kwargs):
    return _main_attr("build_platform_companies_url")(*args, **kwargs)

def build_platform_readiness_links(*args, **kwargs):
    return _main_attr("build_platform_readiness_links")(*args, **kwargs)

def claim_visible_calendar_scheduler_incidents(*args, **kwargs):
    return _main_attr("claim_visible_calendar_scheduler_incidents")(*args, **kwargs)

def close_calendar_scheduler_incident(*args, **kwargs):
    return _main_attr("close_calendar_scheduler_incident")(*args, **kwargs)

def compare_platform_release_readiness_snapshots(*args, **kwargs):
    return _main_attr("compare_platform_release_readiness_snapshots")(*args, **kwargs)

def compare_platform_release_readiness_to_snapshot(*args, **kwargs):
    return _main_attr("compare_platform_release_readiness_to_snapshot")(*args, **kwargs)

def create_platform_release_readiness_snapshot(*args, **kwargs):
    return _main_attr("create_platform_release_readiness_snapshot")(*args, **kwargs)

def create_platform_release_signoff(*args, **kwargs):
    return _main_attr("create_platform_release_signoff")(*args, **kwargs)

def get_a3_company_id(*args, **kwargs):
    return _main_attr("get_a3_company_id")(*args, **kwargs)

def get_a3_owner_company_id(*args, **kwargs):
    return _main_attr("get_a3_owner_company_id")(*args, **kwargs)

def get_backup_status(*args, **kwargs):
    return _main_attr("get_backup_status")(*args, **kwargs)

def get_platform_calendar_company_detail(*args, **kwargs):
    return _main_attr("get_platform_calendar_company_detail")(*args, **kwargs)

def get_platform_calendar_health(*args, **kwargs):
    return _main_attr("get_platform_calendar_health")(*args, **kwargs)

def get_platform_calendar_incident_analytics(*args, **kwargs):
    return _main_attr("get_platform_calendar_incident_analytics")(*args, **kwargs)

def get_platform_company_items(*args, **kwargs):
    return _main_attr("get_platform_company_items")(*args, **kwargs)

def get_platform_company_profile(*args, **kwargs):
    return _main_attr("get_platform_company_profile")(*args, **kwargs)

def get_platform_dashboard_data(*args, **kwargs):
    return _main_attr("get_platform_dashboard_data")(*args, **kwargs)

def get_platform_dashboard_links(*args, **kwargs):
    return _main_attr("get_platform_dashboard_links")(*args, **kwargs)

def get_platform_generated_at(*args, **kwargs):
    return _main_attr("get_platform_generated_at")(*args, **kwargs)

def get_platform_module_usage(*args, **kwargs):
    return _main_attr("get_platform_module_usage")(*args, **kwargs)

def get_platform_preset_profile(*args, **kwargs):
    return _main_attr("get_platform_preset_profile")(*args, **kwargs)

def get_platform_preset_usage(*args, **kwargs):
    return _main_attr("get_platform_preset_usage")(*args, **kwargs)

def get_platform_release_control_center(*args, **kwargs):
    return _main_attr("get_platform_release_control_center")(*args, **kwargs)

def get_platform_release_dashboard_summary(*args, **kwargs):
    return _main_attr("get_platform_release_dashboard_summary")(*args, **kwargs)

def get_platform_release_launch_plan(*args, **kwargs):
    return _main_attr("get_platform_release_launch_plan")(*args, **kwargs)

def get_platform_release_post_launch_review(*args, **kwargs):
    return _main_attr("get_platform_release_post_launch_review")(*args, **kwargs)

def get_platform_release_readiness(*args, **kwargs):
    return _main_attr("get_platform_release_readiness")(*args, **kwargs)

def get_platform_release_readiness_history(*args, **kwargs):
    return _main_attr("get_platform_release_readiness_history")(*args, **kwargs)

def get_platform_release_readiness_snapshot(*args, **kwargs):
    return _main_attr("get_platform_release_readiness_snapshot")(*args, **kwargs)

def get_platform_release_readiness_trend(*args, **kwargs):
    return _main_attr("get_platform_release_readiness_trend")(*args, **kwargs)

def get_platform_release_runbook(*args, **kwargs):
    return _main_attr("get_platform_release_runbook")(*args, **kwargs)

def get_platform_release_signoff_history(*args, **kwargs):
    return _main_attr("get_platform_release_signoff_history")(*args, **kwargs)

def get_platform_release_timeline(*args, **kwargs):
    return _main_attr("get_platform_release_timeline")(*args, **kwargs)

def hash_password(*args, **kwargs):
    return _main_attr("hash_password")(*args, **kwargs)

def is_password_strong(*args, **kwargs):
    return _main_attr("is_password_strong")(*args, **kwargs)

def log_calendar_scheduler_recovery_attempt(*args, **kwargs):
    return _main_attr("log_calendar_scheduler_recovery_attempt")(*args, **kwargs)

def normalize_platform_company_filters(*args, **kwargs):
    return _main_attr("normalize_platform_company_filters")(*args, **kwargs)

def reassign_calendar_scheduler_incident(*args, **kwargs):
    return _main_attr("reassign_calendar_scheduler_incident")(*args, **kwargs)

def reassign_visible_calendar_scheduler_incidents(*args, **kwargs):
    return _main_attr("reassign_visible_calendar_scheduler_incidents")(*args, **kwargs)

def record_company_settings_history(*args, **kwargs):
    return _main_attr("record_company_settings_history")(*args, **kwargs)

def run_automation_event(*args, **kwargs):
    return _main_attr("run_automation_event")(*args, **kwargs)

def run_background_job_batch(*args, **kwargs):
    return _main_attr("run_background_job_batch")(*args, **kwargs)

def system_event_severity_label(*args, **kwargs):
    return _main_attr("system_event_severity_label")(*args, **kwargs)


def get_system_event_cleanup_candidates(*args, **kwargs):
    return _main_attr("get_system_event_cleanup_candidates")(*args, **kwargs)


def run_calendar_plan_scheduler(*args, **kwargs):
    return _main_attr("run_calendar_plan_scheduler")(*args, **kwargs)

def send_message_to_chat(*args, **kwargs):
    return _main_attr("send_message_to_chat")(*args, **kwargs)

@router.post("/platform/companies")
async def create_platform_company(request: Request):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role != "superadmin":
        return RedirectResponse("/", status_code=302)

    form = await request.form()

    company_name = (form.get("company_name") or "").strip()
    owner_username = (form.get("owner_username") or "").strip()
    owner_password = (form.get("owner_password") or "").strip()
    industry = (form.get("industry") or "field_service").strip()

    if not company_name or not owner_username or not owner_password:
        return RedirectResponse("/platform/companies?error=empty", status_code=302)

    if not is_password_strong(owner_password):
        return RedirectResponse("/platform/companies?error=weak_password", status_code=302)

    allowed_industries = {industry_key for industry_key, _ in INDUSTRY_OPTIONS}

    if industry not in allowed_industries:
        industry = "field_service"

    conn = connect()
    c = conn.cursor()

    existing_user = c.execute("""
    SELECT id
    FROM users
    WHERE username=?
    """, (owner_username,)).fetchone()

    if existing_user:
        conn.close()
        return RedirectResponse("/platform/companies?error=user_exists", status_code=302)

    c.execute("""
    INSERT INTO companies (
        name,
        owner_username,
        created_at
    )
    VALUES (?, ?, ?)
    """, (
        company_name,
        owner_username,
        datetime.now().strftime("%Y-%m-%d %H:%M")
    ))

    company_id = c.lastrowid

    c.execute("""
    INSERT INTO users (
        username,
        password,
        role,
        company_id,
        last_seen
    )
    VALUES (?, ?, ?, ?, ?)
    """, (
        owner_username,
        hash_password(owner_password),
        "boss",
        company_id,
        datetime.now().strftime("%Y-%m-%d %H:%M")
    ))

    c.execute("""
    INSERT OR IGNORE INTO company_settings (
        company_id,
        company_name,
        phone,
        email,
        address,
        tax_number,
        bank_details,
        plan,
        one_c_enabled,
        calls_enabled,
        ai_calls_enabled,
        updated_at
    )
    VALUES (?, ?, '', '', '', '', '', 'basic', 0, 0, 0, ?)
    """, (
        company_id,
        company_name,
        datetime.now().strftime("%Y-%m-%d %H:%M")
    ))

    conn.commit()
    conn.close()
    apply_business_preset(company_id, industry)

    return RedirectResponse("/platform/companies?created=1", status_code=302)


@router.post("/platform/companies/{company_id}/settings")
async def update_platform_company_settings(request: Request, company_id: int):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role != "superadmin":
        return RedirectResponse("/", status_code=302)

    form = await request.form()
    plan = normalize_plan(form.get("plan") or "basic")
    industry = (form.get("industry") or "field_service").strip()
    return_to = (form.get("return_to") or "").strip()
    allowed_industries = {industry_key for industry_key, _ in INDUSTRY_OPTIONS}

    if industry not in allowed_industries:
        industry = "field_service"

    (
        return_search,
        return_industry,
        return_plan,
        return_limit,
        return_feature,
        return_billing,
    ) = normalize_platform_company_filters(
        form.get("return_search") or "",
        form.get("return_industry") or "all",
        form.get("return_plan") or "all",
        form.get("return_limit") or "all",
        form.get("return_feature") or "all",
        form.get("return_billing") or "all",
    )
    visible_return_industry = return_industry
    visible_return_plan = return_plan

    if visible_return_industry != "all" and visible_return_industry != industry:
        visible_return_industry = industry

    if visible_return_plan != "all" and visible_return_plan != plan:
        visible_return_plan = plan

    if return_to == "detail":
        return_url = f"/platform/companies/{company_id}"
    else:
        return_url = build_platform_companies_url(
            return_search,
            visible_return_industry,
            visible_return_plan,
            limit=return_limit,
            feature=return_feature,
            billing=return_billing,
        )

    conn = connect()
    c = conn.cursor()
    company = c.execute("""
    SELECT id, name, owner_username
    FROM companies
    WHERE id=?
    """, (company_id,)).fetchone()

    if not company:
        conn.close()
        return RedirectResponse(
            build_platform_companies_url(
                return_search,
                return_industry,
                return_plan,
                {"error": "company_not_found"},
                limit=return_limit,
                feature=return_feature,
                billing=return_billing,
            ),
            status_code=302,
        )

    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    c.execute("""
    INSERT OR IGNORE INTO company_settings (
        company_id, company_name, phone, email, address, tax_number,
        bank_details, plan, industry, task_label, worker_label,
        client_label, service_label, one_c_enabled, calls_enabled,
        ai_calls_enabled, updated_at
    )
    VALUES (?, ?, '', '', '', '', '', 'basic', 'field_service',
            'Заявка', 'Исполнитель', 'Клиент', 'Услуга', 0, 0, 0, ?)
    """, (
        company_id,
        company["name"] or "",
        now,
    ))

    conn.commit()
    conn.close()

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
        separator = "&" if "?" in return_url else "?"
        return RedirectResponse(
            f"{return_url}{separator}error=plan_user_limit",
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

    apply_business_preset(company_id, industry)
    plan_features = get_plan_feature_flags(plan)

    conn = connect()
    c = conn.cursor()
    c.execute("""
    UPDATE company_settings
    SET plan=?,
        one_c_enabled=?,
        calls_enabled=?,
        ai_calls_enabled=?,
        updated_at=?
    WHERE company_id=?
    """, (
        plan,
        plan_features["one_c_enabled"],
        plan_features["calls_enabled"],
        plan_features["ai_calls_enabled"],
        datetime.now().strftime("%Y-%m-%d %H:%M"),
        company_id,
    ))
    conn.commit()
    conn.close()

    if settings_history_changes:
        record_company_settings_history(
            company_id,
            username,
            "Платформа обновила настройки",
            "; ".join(settings_history_changes),
            get_plan_label(current_plan),
            get_plan_label(plan),
        )

    industry_label = get_industry_label(industry)
    owner_username = str(company["owner_username"] or "").strip()

    if owner_username:
        create_notification(
            company_id,
            owner_username,
            "Настройки компании обновлены",
            (
                f"Платформа изменила тариф: {get_plan_label(plan)}, "
                f"сфера: {industry_label}"
            ),
            "/settings",
        )

    run_automation_event(
        company_id,
        "company_settings_updated",
        "company",
        company_id,
        (
            f"Платформа обновила настройки компании: "
            f"{get_plan_label(plan)} / {industry_label}"
        ),
        "/settings",
    )

    separator = "&" if "?" in return_url else "?"

    return RedirectResponse(
        f"{return_url}{separator}updated=1",
        status_code=302,
    )


@router.post("/platform/companies/{company_id}/apply-preset")
async def apply_platform_company_preset(request: Request, company_id: int):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role != "superadmin":
        return RedirectResponse("/", status_code=302)

    profile = get_platform_company_profile(company_id)

    if not profile:
        return RedirectResponse(
            "/platform/companies?error=company_not_found",
            status_code=302,
        )

    company = profile["company"]
    settings = profile["settings"]
    industry = str(settings["industry"] or "field_service")
    industry_label = dict(INDUSTRY_OPTIONS).get(
        industry,
        "Сфера не указана",
    )

    apply_business_preset(company_id, industry)

    record_company_settings_history(
        company_id,
        username,
        "Платформа применила пресет",
        (
            f"Пресет: {industry_label}; "
            "модули и подписи компании приведены к настройкам сферы"
        ),
        "",
        industry_label,
    )

    owner_username = str(company["owner_username"] or "").strip()

    if owner_username:
        create_notification(
            company_id,
            owner_username,
            "Пресет компании применён",
            f"Платформа повторно применила пресет: {industry_label}",
            "/settings",
        )

    run_automation_event(
        company_id,
        "company_settings_updated",
        "company",
        company_id,
        f"Платформа повторно применила пресет: {industry_label}",
        "/settings",
    )

    return RedirectResponse(
        f"/platform/companies/{company_id}?updated=1",
        status_code=302,
    )


@router.get("/platform/companies/export")
async def platform_companies_export(
    request: Request,
    search: str = "",
    industry: str = "all",
    plan: str = "all",
    limit: str = "all",
    feature: str = "all",
    billing: str = "all",
):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role != "superadmin":
        return RedirectResponse("/", status_code=302)

    company_data = get_platform_company_items(
        search,
        industry,
        plan,
        limit,
        feature,
        billing,
    )

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "ID",
        "Компания",
        "Владелец",
        "Сфера",
        "Тариф",
        "Лимит пользователей",
        "Статус лимита",
        "Рекомендуемый тариф",
        "Активные пользователи",
        "Пользователи всего",
        "Активные заявки",
        "Архивные заявки",
        "Статус счетов",
        "К оплате",
        "Просрочено счетов",
        "Скоро к оплате",
        "Создана",
    ])

    for company in company_data["companies"]:
        writer.writerow([
            company["id"],
            company["name"],
            company["owner_username"],
            company["industry_label"],
            company["plan_label"],
            company["user_limit_label"],
            company["user_limit_status"],
            (
                company["recommended_plan"]["label"]
                if company["recommended_plan"]
                else ""
            ),
            company["active_users_count"],
            company["users_count"],
            company["active_tasks_count"],
            company["archived_tasks_count"],
            company["billing_status_label"],
            company["billing_invoice_summary"]["unpaid_amount_label"],
            company["billing_risk_summary"]["overdue_by_date_count"],
            company["billing_risk_summary"]["due_soon_count"],
            company["created_at"],
        ])

    filename_parts = [
        "platform_companies",
        company_data["selected_industry"],
        company_data["selected_plan"],
        company_data["selected_limit"],
    ]

    if company_data["selected_feature"] != "all":
        filename_parts.append(company_data["selected_feature"])

    if company_data["selected_billing"] != "all":
        filename_parts.append(f"billing_{company_data['selected_billing']}")

    filename = "_".join(filename_parts) + ".csv"

    return Response(
        "\ufeff" + output.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f"attachment; filename={filename}"
        },
    )


@router.get("/platform/companies/{company_id}/export")
async def platform_company_export(request: Request, company_id: int):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role != "superadmin":
        return RedirectResponse("/", status_code=302)

    profile = get_platform_company_profile(company_id)

    if not profile:
        return RedirectResponse(
            "/platform/companies?error=company_not_found",
            status_code=302,
        )

    company = profile["company"]
    settings = profile["settings"]
    usage = profile["usage"]

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Карточка компании"])
    writer.writerow(["ID", company["id"]])
    writer.writerow(["Компания", company["name"]])
    writer.writerow(["Владелец", company["owner_username"]])
    writer.writerow(["Сфера", profile["industry_label"]])
    writer.writerow(["Тариф", usage["plan_label"]])
    writer.writerow(["Лимит пользователей", usage["user_limit_label"]])
    writer.writerow(["Статус лимита", usage["status"]])
    writer.writerow([
        "Рекомендуемый тариф",
        (
            profile["recommended_plan"]["label"]
            if profile["recommended_plan"]
            else ""
        ),
    ])
    writer.writerow(["Активные пользователи", usage["active_users_count"]])
    writer.writerow(["Пользователи всего", usage["users_count"]])
    writer.writerow(["Модулей включено", profile["enabled_features_count"]])
    writer.writerow(["Модулей выключено", profile["disabled_features_count"]])
    writer.writerow(["Отклонений от пресета", profile["preset_drift"]["count"]])
    writer.writerow(["Заявки всего", profile["task_stats"]["total"]])
    writer.writerow(["Активные заявки", profile["task_stats"]["active"]])
    writer.writerow(["Архивные заявки", profile["task_stats"]["archived"]])
    writer.writerow(["Новые заявки", profile["task_stats"]["new_tasks"]])
    writer.writerow(["Заявки в работе", profile["task_stats"]["in_progress"]])
    writer.writerow(["Завершённые заявки", profile["task_stats"]["completed"]])
    writer.writerow(["Создана", company["created_at"]])
    writer.writerow([])

    writer.writerow(["Настройки"])
    writer.writerow(["Заявка", settings["task_label"]])
    writer.writerow(["Исполнитель", settings["worker_label"]])
    writer.writerow(["Клиент", settings["client_label"]])
    writer.writerow(["Услуга", settings["service_label"]])
    writer.writerow([])

    writer.writerow(["История настроек"])
    writer.writerow([
        "Дата",
        "Действие",
        "Детали",
        "Было",
        "Стало",
        "Кто изменил",
    ])
    for event in profile["settings_history"]:
        writer.writerow([
            event["created_at"] or "",
            event["action"] or "",
            event["details"] or "",
            event["old_value"] or "",
            event["new_value"] or "",
            event["actor_username"] or "",
        ])
    writer.writerow([])

    writer.writerow(["Счета платформы"])
    writer.writerow(["Всего счетов", profile["billing_invoice_summary"]["count"]])
    writer.writerow([
        "Начислено",
        profile["billing_invoice_summary"]["total_amount_label"],
    ])
    writer.writerow([
        "К оплате",
        profile["billing_invoice_summary"]["unpaid_amount_label"],
    ])
    writer.writerow([
        "Просрочено по дате",
        profile["billing_risk_summary"]["overdue_by_date_count"],
    ])
    writer.writerow([
        "Сумма просрочки",
        profile["billing_risk_summary"]["overdue_by_date_amount_label"],
    ])
    writer.writerow([
        "Скоро к оплате",
        profile["billing_risk_summary"]["due_soon_count"],
    ])
    writer.writerow(["Черновики", profile["billing_risk_summary"]["draft_count"]])
    if profile["next_payment_summary"]["has_invoice"]:
        next_invoice = profile["next_payment_summary"]["invoice"]
        writer.writerow([
            "Ближайший платёж",
            next_invoice["invoice_number"] or f"#{next_invoice['id']}",
        ])
        writer.writerow(["Срок ближайшего платежа", next_invoice["due_date"] or ""])
        writer.writerow([
            "Статус ближайшего платежа",
            profile["next_payment_summary"]["label"],
        ])
    writer.writerow(["Номер", "Период", "Тариф", "Сумма", "Статус", "Оплатить до"])
    for invoice in profile["billing_invoices"]:
        writer.writerow([
            invoice["invoice_number"] or f"#{invoice['id']}",
            invoice["period"] or "",
            invoice["plan_label"],
            invoice["amount"] or 0,
            invoice["status_label"],
            invoice["due_date"] or "",
        ])
    writer.writerow([])

    writer.writerow(["Пользователи"])
    writer.writerow(["ID", "Имя", "Логин", "Роль", "Статус", "Последний вход"])
    for user in profile["users"]:
        writer.writerow([
            user["id"],
            user["full_name"] or user["username"],
            user["username"],
            role_label(user["role"]),
            "Активен" if user["is_active"] is None or user["is_active"] else "Отключён",
            user["last_seen"] or "",
        ])
    writer.writerow([])

    writer.writerow(["Модули"])
    writer.writerow(["Ключ", "Название", "Статус"])
    for feature in profile["features"]:
        writer.writerow([
            feature["key"],
            feature["title"],
            "Включено" if feature["enabled"] else "Выключено",
        ])
    writer.writerow([])

    writer.writerow(["Отклонения от пресета"])
    writer.writerow(["Ключ", "Название", "Ожидается", "Сейчас"])
    for drift in profile["preset_drift"]["items"]:
        writer.writerow([
            drift["key"],
            drift["title"],
            drift["expected_label"],
            drift["current_label"],
        ])
    writer.writerow([])

    writer.writerow(["Последние заявки"])
    writer.writerow(["ID", "Клиент", "Статус", "Дата", "Архив"])
    for task in profile["recent_tasks"]:
        writer.writerow([
            task["id"],
            task["client"] or "",
            task["status"] or "",
            task["task_date"] or "",
            "Да" if task["archived"] else "Нет",
        ])

    return Response(
        "\ufeff" + output.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": (
                f"attachment; filename=platform_company_{company_id}.csv"
            )
        },
    )


@router.post("/platform/companies/{company_id}/billing/generate")
async def generate_platform_company_billing_invoice(
    request: Request,
    company_id: int,
):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role != "superadmin":
        return RedirectResponse("/", status_code=302)

    profile = get_platform_company_profile(company_id)

    if not profile:
        return RedirectResponse(
            "/platform/companies?error=company_not_found",
            status_code=302,
        )

    form = await request.form()
    period = normalize_billing_period(form.get("period") or "")
    result = generate_company_billing_invoice(company_id, period, username)
    flag = "invoice_created" if result["created"] else "invoice_exists"

    return RedirectResponse(
        f"/platform/companies/{company_id}?{flag}=1",
        status_code=302,
    )


@router.get("/platform/companies/{company_id}", response_class=HTMLResponse)
async def platform_company_detail_page(request: Request, company_id: int):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role != "superadmin":
        return RedirectResponse("/", status_code=302)

    profile = get_platform_company_profile(company_id)

    if not profile:
        return RedirectResponse(
            "/platform/companies?error=company_not_found",
            status_code=302,
        )

    return templates.TemplateResponse(
        request,
        "platform_company_detail.html",
        {
            "request": request,
            "username": username,
            "role": role,
            "generated_at": get_platform_generated_at(),
            "industry_options": INDUSTRY_OPTIONS,
            "plan_options": get_plan_options(),
            **profile,
        },
    )


@router.get("/api/platform/companies/{company_id}")
async def api_platform_company_detail(request: Request, company_id: int):

    username = get_user(request)

    if not username:
        return JSONResponse({"error": "auth_required"}, status_code=401)

    role = get_role(username)

    if role != "superadmin":
        return JSONResponse({"error": "forbidden"}, status_code=403)

    profile = get_platform_company_profile(company_id)

    if not profile:
        return JSONResponse({"error": "company_not_found"}, status_code=404)

    settings = profile["settings"]
    company = profile["company"]

    return {
        "ok": True,
        "generated_at": get_platform_generated_at(),
        "company": company,
        "settings": {
            "industry": settings["industry"],
            "task_label": settings["task_label"],
            "worker_label": settings["worker_label"],
            "client_label": settings["client_label"],
            "service_label": settings["service_label"],
        },
        "usage": profile["usage"],
        "recommended_plan": profile["recommended_plan"],
        "industry_label": profile["industry_label"],
        "feature_summary": {
            "enabled": profile["enabled_features_count"],
            "disabled": profile["disabled_features_count"],
        },
        "preset_drift": {
            "count": profile["preset_drift"]["count"],
            "status_label": profile["preset_drift"]["status_label"],
            "items": profile["preset_drift"]["items"],
        },
        "task_stats": profile["task_stats"],
        "billing": {
            "summary": profile["billing_invoice_summary"],
            "risk_summary": profile["billing_risk_summary"],
            "next_payment": profile["next_payment_summary"],
            "recent_invoices": profile["billing_invoices"],
        },
        "links": profile["links"],
    }


@router.get("/api/platform/companies")
async def api_platform_companies(
    request: Request,
    search: str = "",
    industry: str = "all",
    plan: str = "all",
    limit: str = "all",
    feature: str = "all",
    billing: str = "all",
):

    username = get_user(request)

    if not username:
        return JSONResponse({"error": "auth_required"}, status_code=401)

    role = get_role(username)

    if role != "superadmin":
        return JSONResponse({"error": "forbidden"}, status_code=403)

    company_data = get_platform_company_items(
        search,
        industry,
        plan,
        limit,
        feature,
        billing,
    )

    return {
        "ok": True,
        "generated_at": get_platform_generated_at(),
        "filters": {
            "search": company_data["search"],
            "industry": company_data["selected_industry"],
            "plan": company_data["selected_plan"],
            "limit": company_data["selected_limit"],
            "feature": company_data["selected_feature"],
            "billing": company_data["selected_billing"],
        },
        "summary": company_data["summary"],
        "companies": company_data["companies"],
        "links": company_data["links"],
    }


@router.get("/platform/companies", response_class=HTMLResponse)
async def platform_companies_page(
    request: Request,
    search: str = "",
    industry: str = "all",
    plan: str = "all",
    limit: str = "all",
    feature: str = "all",
    billing: str = "all",
):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role != "superadmin":
        return RedirectResponse("/", status_code=302)

    company_data = get_platform_company_items(
        search,
        industry,
        plan,
        limit,
        feature,
        billing,
    )

    return templates.TemplateResponse(
        request,
        "platform_companies.html",
        {
            "request": request,
            "username": username,
            "role": role,
            "generated_at": get_platform_generated_at(),
            "companies": company_data["companies"],
            "summary": company_data["summary"],
            "links": company_data["links"],
            "industry_options": INDUSTRY_OPTIONS,
            "plan_options": get_plan_options(),
            "feature_options": FEATURE_DEFINITIONS,
            "search": company_data["search"],
            "selected_industry": company_data["selected_industry"],
            "selected_plan": company_data["selected_plan"],
            "selected_limit": company_data["selected_limit"],
            "selected_feature": company_data["selected_feature"],
            "selected_billing": company_data["selected_billing"],
        }
    )


@router.get("/platform/modules", response_class=HTMLResponse)
async def platform_modules_page(request: Request):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role != "superadmin":
        return RedirectResponse("/", status_code=302)

    module_usage = get_platform_module_usage()

    return templates.TemplateResponse(
        request,
        "platform_modules.html",
        {
            "request": request,
            "username": username,
            "role": role,
            "generated_at": get_platform_generated_at(),
            "summary": module_usage["summary"],
            "modules": module_usage["modules"],
            "links": module_usage["links"],
        },
    )


@router.get("/api/platform/modules")
async def api_platform_modules(request: Request):

    username = get_user(request)

    if not username:
        return JSONResponse({"error": "auth_required"}, status_code=401)

    role = get_role(username)

    if role != "superadmin":
        return JSONResponse({"error": "forbidden"}, status_code=403)

    module_usage = get_platform_module_usage()

    return {
        "ok": True,
        "generated_at": get_platform_generated_at(),
        "summary": module_usage["summary"],
        "modules": module_usage["modules"],
        "links": module_usage["links"],
    }


@router.get("/api/platform/modules/{feature_key}")
async def api_platform_module_detail(request: Request, feature_key: str):

    username = get_user(request)

    if not username:
        return JSONResponse({"error": "auth_required"}, status_code=401)

    role = get_role(username)

    if role != "superadmin":
        return JSONResponse({"error": "forbidden"}, status_code=403)

    module_usage = get_platform_module_usage()
    feature_key = str(feature_key or "").strip()
    module = next(
        (
            item
            for item in module_usage["modules"]
            if item["key"] == feature_key
        ),
        None,
    )

    if not module:
        return JSONResponse({"error": "module_not_found"}, status_code=404)

    links = {
        "platform": module_usage["links"]["platform"],
        "modules": module_usage["links"]["page"],
        **module["links"],
    }

    return {
        "ok": True,
        "generated_at": get_platform_generated_at(),
        "summary": module_usage["summary"],
        "module": module,
        "links": links,
    }


@router.get("/platform/modules/export")
async def platform_modules_export(request: Request):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role != "superadmin":
        return RedirectResponse("/", status_code=302)

    module_usage = get_platform_module_usage()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Сформировано", get_platform_generated_at()])
    writer.writerow([])
    writer.writerow([
        "Модуль",
        "Ключ",
        "Описание",
        "Включено компаний",
        "Выключено компаний",
        "Покрытие",
        "Примеры компаний",
    ])

    for module in module_usage["modules"]:
        writer.writerow([
            module["title"],
            module["key"],
            module["description"],
            module["enabled_count"],
            module["disabled_count"],
            f"{module['coverage_percent']}%",
            "; ".join(company["name"] for company in module["companies"]),
        ])

    return Response(
        "\ufeff" + output.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": (
                "attachment; filename=platform_modules.csv"
            )
        },
    )


@router.get("/platform/modules/{feature_key}", response_class=HTMLResponse)
async def platform_module_detail_page(request: Request, feature_key: str):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role != "superadmin":
        return RedirectResponse("/", status_code=302)

    module_usage = get_platform_module_usage()
    feature_key = str(feature_key or "").strip()
    module = next(
        (
            item
            for item in module_usage["modules"]
            if item["key"] == feature_key
        ),
        None,
    )

    if not module:
        return RedirectResponse(
            "/platform/modules?error=module_not_found",
            status_code=302,
        )

    links = {
        "platform": module_usage["links"]["platform"],
        "modules": module_usage["links"]["page"],
        **module["links"],
    }

    return templates.TemplateResponse(
        request,
        "platform_module_detail.html",
        {
            "request": request,
            "username": username,
            "role": role,
            "generated_at": get_platform_generated_at(),
            "summary": module_usage["summary"],
            "module": module,
            "links": links,
        },
    )


@router.get("/platform/presets", response_class=HTMLResponse)
async def platform_presets_page(request: Request):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role != "superadmin":
        return RedirectResponse("/", status_code=302)

    preset_usage = get_platform_preset_usage()

    return templates.TemplateResponse(
        request,
        "platform_presets.html",
        {
            "request": request,
            "username": username,
            "role": role,
            "generated_at": get_platform_generated_at(),
            "summary": preset_usage["summary"],
            "presets": preset_usage["presets"],
            "links": preset_usage["links"],
        },
    )


@router.get("/api/platform/presets")
async def api_platform_presets(request: Request):

    username = get_user(request)

    if not username:
        return JSONResponse({"error": "auth_required"}, status_code=401)

    role = get_role(username)

    if role != "superadmin":
        return JSONResponse({"error": "forbidden"}, status_code=403)

    preset_usage = get_platform_preset_usage()

    return {
        "ok": True,
        "generated_at": get_platform_generated_at(),
        "summary": preset_usage["summary"],
        "presets": preset_usage["presets"],
        "links": preset_usage["links"],
    }


@router.get("/api/platform/presets/{industry_key}")
async def api_platform_preset_detail(request: Request, industry_key: str):

    username = get_user(request)

    if not username:
        return JSONResponse({"error": "auth_required"}, status_code=401)

    role = get_role(username)

    if role != "superadmin":
        return JSONResponse({"error": "forbidden"}, status_code=403)

    profile = get_platform_preset_profile(industry_key)

    if not profile:
        return JSONResponse({"error": "preset_not_found"}, status_code=404)

    return {
        "ok": True,
        "generated_at": get_platform_generated_at(),
        **profile,
    }


@router.get("/platform/presets/export")
async def platform_presets_export(request: Request):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role != "superadmin":
        return RedirectResponse("/", status_code=302)

    preset_usage = get_platform_preset_usage()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Сформировано", get_platform_generated_at()])
    writer.writerow([])
    writer.writerow([
        "Сфера",
        "Ключ",
        "Компаний",
        "Отклонений",
        "Модулей в пресете",
        "Заявка",
        "Исполнитель",
        "Клиент",
        "Услуга",
        "Модули",
    ])

    for preset in preset_usage["presets"]:
        writer.writerow([
            preset["title"],
            preset["key"],
            preset["companies_count"],
            preset["drift_count"],
            preset["modules_count"],
            preset["labels"]["task_label"],
            preset["labels"]["worker_label"],
            preset["labels"]["client_label"],
            preset["labels"]["service_label"],
            "; ".join(feature["title"] for feature in preset["features"]),
        ])

    return Response(
        "\ufeff" + output.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": (
                "attachment; filename=platform_presets.csv"
            )
        },
    )


@router.get("/platform/presets/{industry_key}", response_class=HTMLResponse)
async def platform_preset_detail_page(request: Request, industry_key: str):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role != "superadmin":
        return RedirectResponse("/", status_code=302)

    profile = get_platform_preset_profile(industry_key)

    if not profile:
        return RedirectResponse(
            "/platform/presets?error=preset_not_found",
            status_code=302,
        )

    return templates.TemplateResponse(
        request,
        "platform_preset_detail.html",
        {
            "request": request,
            "username": username,
            "role": role,
            "generated_at": get_platform_generated_at(),
            **profile,
        },
    )


def get_system_event_history(limit=20):
    conn = connect()
    rows = conn.execute("""
    SELECT *
    FROM system_events
    ORDER BY id DESC
    LIMIT ?
    """, (limit,)).fetchall()
    conn.close()
    events = []

    for row in rows:
        event = dict(row)
        event["severity"] = normalize_system_event_severity(
            event.get("severity"),
        )
        event["severity_label"] = system_event_severity_label(
            event["severity"],
        )
        events.append(event)

    return events


def get_system_event_retention_status():
    conn = connect()
    summary = conn.execute("""
    SELECT
        COUNT(*) AS count,
        MIN(created_at) AS oldest_created_at,
        MAX(created_at) AS latest_created_at
    FROM system_events
    """).fetchone()
    conn.close()
    candidates = get_system_event_cleanup_candidates()

    return {
        "count": summary["count"] or 0,
        "oldest_created_at": summary["oldest_created_at"] or "",
        "latest_created_at": summary["latest_created_at"] or "",
        "retention_days": SYSTEM_EVENT_RETENTION_DAYS,
        "retention_keep": SYSTEM_EVENT_RETENTION_KEEP,
        "cleanup_count": len(candidates),
        "cleanup_url": "/system/events/cleanup",
    }


def get_http_error_meta(status_code):
    labels = {
        404: {
            "code": "not_found",
            "title": "Страница не найдена",
            "message": (
                "Такой страницы нет или адрес был изменён. "
                "Проверьте ссылку или вернитесь на главную."
            ),
        },
        405: {
            "code": "method_not_allowed",
            "title": "Метод не поддерживается",
            "message": (
                "Этот адрес не принимает такой способ запроса. "
                "Вернитесь назад и повторите действие через интерфейс."
            ),
        },
    }

    return labels.get(status_code, {
        "code": "http_error",
        "title": "Запрос не выполнен",
        "message": "Сервер не смог выполнить этот запрос.",
    })


@router.get("/api/platform")
async def api_platform_dashboard(request: Request):

    username = get_user(request)

    if not username:
        return JSONResponse({"error": "auth_required"}, status_code=401)

    role = get_role(username)

    if role != "superadmin":
        return JSONResponse({"error": "forbidden"}, status_code=403)

    dashboard_data = get_platform_dashboard_data()

    return {
        "ok": True,
        "generated_at": dashboard_data["generated_at"],
        "counts": dashboard_data["counts"],
        "company_usage_summary": dashboard_data["company_usage_summary"],
        "limit_alert_companies": dashboard_data["limit_alert_companies"],
        "billing_alert_companies": dashboard_data["billing_alert_companies"],
        "platform_billing_summary": dashboard_data["platform_billing_summary"],
        "module_usage_summary": dashboard_data["module_usage_summary"],
        "preset_usage_summary": dashboard_data["preset_usage_summary"],
        "links": dashboard_data["links"],
    }


@router.get("/platform/export")
async def platform_dashboard_export(request: Request):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role != "superadmin":
        return RedirectResponse("/", status_code=302)

    dashboard_data = get_platform_dashboard_data()
    counts = dashboard_data["counts"]
    platform_alerts = dashboard_data["platform_alerts"]
    company_summary = dashboard_data["company_usage_summary"]
    platform_billing_summary = dashboard_data["platform_billing_summary"]
    module_summary = dashboard_data["module_usage_summary"]
    preset_summary = dashboard_data["preset_usage_summary"]

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Панель платформы"])
    writer.writerow(["Сформировано", dashboard_data["generated_at"]])
    writer.writerow(["Компании", counts["companies"]])
    writer.writerow(["Пользователи", counts["users"]])
    writer.writerow(["Заявки", counts["tasks"]])
    writer.writerow(["Клиенты", counts["clients"]])
    writer.writerow([])
    writer.writerow(["Тарифы и лимиты"])
    writer.writerow(["Компаний", company_summary["companies"]])
    writer.writerow(["Превышен лимит", company_summary["limit_danger"]])
    writer.writerow(["Лимит заполнен", company_summary["limit_warning"]])
    writer.writerow(["В норме", company_summary["limit_ok"]])
    writer.writerow(["Компаний с долгом", company_summary["billing_risk_companies"]])
    writer.writerow(["К оплате", company_summary["billing_unpaid_amount_label"]])
    writer.writerow([])
    writer.writerow(["Компании с риском лимита"])
    writer.writerow(["ID", "Компания", "Тариф", "Пользователи", "Статус"])

    for company in platform_alerts["limit_alert_companies"]:
        writer.writerow([
            company["id"],
            company["name"],
            company["plan_label"],
            (
                f"{company['active_users_count']} / "
                f"{company['user_limit_label']}"
            ),
            company["user_limit_status"],
        ])

    if not platform_alerts["limit_alert_companies"]:
        writer.writerow(["", "Нет компаний с риском лимита", "", "", ""])

    writer.writerow([])
    writer.writerow(["Компании с риском оплаты"])
    writer.writerow(["ID", "Компания", "Тариф", "К оплате", "Статус"])

    for company in platform_alerts["billing_alert_companies"]:
        writer.writerow([
            company["id"],
            company["name"],
            company["plan_label"],
            company["billing_invoice_summary"]["unpaid_amount_label"],
            company["billing_status_label"],
        ])

    if not platform_alerts["billing_alert_companies"]:
        writer.writerow(["", "Нет компаний с риском оплаты", "", "", ""])

    writer.writerow([])
    writer.writerow(["Счета и подписки"])
    writer.writerow(["Счетов", platform_billing_summary["count"]])
    writer.writerow([
        "Компаний со счетами",
        platform_billing_summary["companies_with_invoices"],
    ])
    writer.writerow(["Начислено", platform_billing_summary["total_amount_label"]])
    writer.writerow(["К оплате", platform_billing_summary["unpaid_amount_label"]])
    writer.writerow([
        "Просрочено по сроку",
        platform_billing_summary["risk_summary"]["overdue_by_date_count"],
    ])
    writer.writerow([
        "Оплата в 7 дней",
        platform_billing_summary["risk_summary"]["due_soon_count"],
    ])
    writer.writerow([])
    writer.writerow(["Модульность SaaS"])
    writer.writerow(["Модулей", module_summary["modules_count"]])
    writer.writerow(["Покрытие модулей", f"{module_summary['coverage_percent']}%"])
    writer.writerow(["Пресетов", preset_summary["presets_count"]])
    writer.writerow(["Активных сфер", preset_summary["active_presets_count"]])
    writer.writerow(["Отклонений", preset_summary["drift_count"]])

    return Response(
        content="\ufeff" + output.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": "attachment; filename=platform_dashboard.csv"
        },
    )


@router.get("/platform", response_class=HTMLResponse)
async def platform_dashboard(request: Request):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role != "superadmin":
        return RedirectResponse("/", status_code=302)

    dashboard_data = get_platform_dashboard_data()
    counts = dashboard_data["counts"]
    companies_count = counts["companies"]
    users_count = counts["users"]
    tasks_count = counts["tasks"]
    clients_count = counts["clients"]

    conn = connect()
    c = conn.cursor()
    companies = c.execute("""
    SELECT *
    FROM companies
    ORDER BY id DESC
    """).fetchall()

    conn.close()
    calendar_health = get_platform_calendar_health(
        current_username=username,
    )
    calendar_health_incidents = [
        item for item in calendar_health["items"] if item["active_incident"]
    ][:5]
    calendar_admin_workload = calendar_health["admin_workload"][:4]
    calendar_incident_analytics = get_platform_calendar_incident_analytics(
        days=30,
    )
    calendar_recommendations = calendar_incident_analytics[
        "recommendations"
    ][:3]
    release_readiness = get_platform_release_readiness(
        counts={
            "companies": companies_count,
            "users": users_count,
            "tasks": tasks_count,
            "clients": clients_count,
        },
        calendar_health_summary=calendar_health["summary"],
    )
    release_dashboard = get_platform_release_dashboard_summary(
        release_readiness,
        calendar_health_summary=calendar_health["summary"],
    )
    return templates.TemplateResponse(
        request,
        "platform.html",
        {
            "request": request,
            "username": username,
            "role": role,
            "generated_at": dashboard_data["generated_at"],
            "companies_count": companies_count,
            "users_count": users_count,
            "tasks_count": tasks_count,
            "clients_count": clients_count,
            "companies": companies,
            "calendar_health_summary": calendar_health["summary"],
            "calendar_health_incidents": calendar_health_incidents,
            "calendar_admin_workload": calendar_admin_workload,
            "calendar_incident_analytics_summary": (
                calendar_incident_analytics["summary"]
            ),
            "calendar_recommendations": calendar_recommendations,
            "release_readiness": release_readiness,
            "release_dashboard": release_dashboard,
            "company_usage_summary": dashboard_data["company_usage_summary"],
            "limit_alert_companies": dashboard_data["limit_alert_companies"],
            "billing_alert_companies": dashboard_data["billing_alert_companies"],
            "platform_billing_summary": (
                dashboard_data["platform_billing_summary"]
            ),
            "module_usage_summary": dashboard_data["module_usage_summary"],
            "preset_usage_summary": dashboard_data["preset_usage_summary"],
            "links": dashboard_data["links"],
        }
    )


@router.get("/platform/billing", response_class=HTMLResponse)
async def platform_billing_page(
    request: Request,
    status: str = "all",
    company_id: str = "all",
):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role != "superadmin":
        return RedirectResponse("/", status_code=302)

    status_filter = normalize_billing_invoice_filter(status)
    selected_company_id = normalize_platform_billing_company_id(company_id)

    conn = connect()
    c = conn.cursor()
    invoices = fetch_platform_billing_invoices(
        c,
        status_filter=status_filter,
        company_id=selected_company_id,
    )
    company_options = get_platform_billing_company_options(c)
    conn.close()
    summary = build_billing_invoice_summary(invoices)
    risk_summary = build_platform_billing_risk_summary(invoices)
    monthly_summary = build_platform_billing_monthly_summary(invoices)
    links = build_platform_billing_links(status_filter, selected_company_id)
    status_filter_options = [
        {
            **option,
            "url": build_platform_billing_url(
                option["key"],
                selected_company_id,
            ),
        }
        for option in get_billing_invoice_status_options()
    ]

    return templates.TemplateResponse(
        request,
        "platform_billing.html",
        {
            "request": request,
            "username": username,
            "role": role,
            "generated_at": get_platform_generated_at(),
            "invoices": invoices,
            "summary": summary,
            "risk_summary": risk_summary,
            "monthly_summary": monthly_summary,
            "links": links,
            "status_filter": status_filter,
            "status_options": get_billing_invoice_status_options(),
            "status_filter_options": status_filter_options,
            "company_options": company_options,
            "selected_company_id": selected_company_id,
            "export_url": links["export"],
        },
    )


@router.post("/platform/billing/generate")
async def generate_platform_billing_invoice(request: Request):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role != "superadmin":
        return RedirectResponse("/", status_code=302)

    form = await request.form()

    try:
        company_id = int(form.get("company_id") or 0)
    except (TypeError, ValueError):
        company_id = 0

    if company_id <= 0:
        return RedirectResponse(
            "/platform/billing?error=company_required",
            status_code=302,
        )

    profile = get_platform_company_profile(company_id)

    if not profile:
        return RedirectResponse(
            "/platform/billing?error=company_not_found",
            status_code=302,
        )

    period = normalize_billing_period(form.get("period") or "")
    result = generate_company_billing_invoice(company_id, period, username)
    flag = "invoice_created" if result["created"] else "invoice_exists"

    if result["created"]:
        invoice = result["invoice"]
        record_platform_billing_activity(
            company_id,
            username,
            "Счёт платформы создан",
            (
                f"{invoice['invoice_number']} · "
                f"{invoice['period']} · {invoice['amount_label']}"
            ),
            profile["company"]["owner_username"] or "",
        )

    return RedirectResponse(
        f"/platform/billing?{flag}=1",
        status_code=302,
    )


@router.post("/platform/billing/reminders/send")
async def send_platform_billing_reminders(request: Request):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role != "superadmin":
        return RedirectResponse("/", status_code=302)

    form = await request.form()
    selected_company_id = normalize_platform_billing_company_id(
        form.get("company_id") or "all"
    )
    status_filter = normalize_billing_invoice_filter(
        form.get("status") or "all"
    )
    result = create_platform_billing_reminders(selected_company_id)
    redirect_url = build_platform_billing_url(status_filter, selected_company_id)
    separator = "&" if "?" in redirect_url else "?"

    return RedirectResponse(
        (
            f"{redirect_url}{separator}billing_reminders=1"
            f"&created={result['created']}"
        ),
        status_code=302,
    )


@router.post("/platform/billing/overdue/sync")
async def sync_platform_billing_overdue(request: Request):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role != "superadmin":
        return RedirectResponse("/", status_code=302)

    form = await request.form()
    selected_company_id = normalize_platform_billing_company_id(
        form.get("company_id") or "all"
    )
    status_filter = normalize_billing_invoice_filter(
        form.get("status") or "all"
    )
    result = sync_platform_billing_overdue_invoices(selected_company_id)
    redirect_url = build_platform_billing_url(status_filter, selected_company_id)
    separator = "&" if "?" in redirect_url else "?"

    return RedirectResponse(
        (
            f"{redirect_url}{separator}overdue_synced=1"
            f"&updated={result['updated']}"
        ),
        status_code=302,
    )


@router.get("/api/platform/billing")
async def api_platform_billing(
    request: Request,
    status: str = "all",
    company_id: str = "all",
):
    username = get_user(request)

    if not username:
        return JSONResponse({"error": "auth_required"}, status_code=401)

    role = get_role(username)

    if role != "superadmin":
        return JSONResponse({"error": "forbidden"}, status_code=403)

    status_filter = normalize_billing_invoice_filter(status)
    selected_company_id = normalize_platform_billing_company_id(company_id)

    conn = connect()
    c = conn.cursor()
    invoices = fetch_platform_billing_invoices(
        c,
        status_filter=status_filter,
        company_id=selected_company_id,
    )
    company_options = get_platform_billing_company_options(c)
    conn.close()

    summary = build_billing_invoice_summary(invoices)
    risk_summary = build_platform_billing_risk_summary(invoices)
    monthly_summary = build_platform_billing_monthly_summary(invoices)
    links = build_platform_billing_links(status_filter, selected_company_id)

    return {
        "ok": True,
        "generated_at": get_platform_generated_at(),
        "filters": {
            "status": status_filter,
            "company_id": selected_company_id,
        },
        "summary": summary,
        "risk_summary": risk_summary,
        "monthly_summary": monthly_summary,
        "company_options": company_options,
        "export_url": links["export"],
        "links": links,
        "invoices": invoices,
    }


@router.get("/api/platform/billing/invoices/{invoice_id}")
async def api_platform_billing_invoice(
    request: Request,
    invoice_id: int,
):
    username = get_user(request)

    if not username:
        return JSONResponse({"error": "auth_required"}, status_code=401)

    role = get_role(username)

    if role != "superadmin":
        return JSONResponse({"error": "forbidden"}, status_code=403)

    conn = connect()
    c = conn.cursor()
    invoice = fetch_platform_billing_invoice(c, invoice_id)
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
        "generated_at": get_platform_generated_at(),
        "invoice": invoice,
        "activity": invoice_activity,
        "activity_summary": (
            build_platform_billing_invoice_activity_summary(invoice_activity)
        ),
        "export_url": invoice["links"]["export"],
        "company_url": invoice["links"]["company"],
        "links": invoice["links"],
    }


@router.post("/platform/billing/invoices/{invoice_id}/status")
async def update_platform_billing_invoice_status(
    request: Request,
    invoice_id: int,
):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role != "superadmin":
        return RedirectResponse("/", status_code=302)

    form = await request.form()
    status = str(form.get("status") or "").strip().lower()
    return_to = str(form.get("return_to") or "").strip().lower()

    if status not in BILLING_INVOICE_STATUSES:
        if return_to == "detail":
            return RedirectResponse(
                f"/platform/billing/invoices/{invoice_id}?error=status_invalid",
                status_code=302,
            )

        return RedirectResponse(
            "/platform/billing?error=status_invalid",
            status_code=302,
        )

    paid_at = datetime.now().strftime("%Y-%m-%d %H:%M") if status == "paid" else ""

    conn = connect()
    c = conn.cursor()
    invoice = fetch_platform_billing_invoice(c, invoice_id)

    if not invoice:
        conn.close()
        return RedirectResponse(
            "/platform/billing?error=invoice_not_found",
            status_code=302,
        )

    if invoice["status_code"] == status:
        conn.close()

        if return_to == "detail":
            return RedirectResponse(
                f"/platform/billing/invoices/{invoice_id}?invoice_updated=1",
                status_code=302,
            )

        return RedirectResponse(
            "/platform/billing?invoice_updated=1",
            status_code=302,
        )

    c.execute("""
    UPDATE billing_invoices
    SET status=?,
        paid_at=?
    WHERE id=?
    """, (status, paid_at, invoice_id))
    conn.commit()
    conn.close()

    new_status_label = get_billing_invoice_status_meta(status)["label"]
    record_platform_billing_activity(
        invoice["company_id"],
        username,
        "Статус счёта платформы",
        (
            f"{invoice['invoice_number'] or ('#' + str(invoice_id))}: "
            f"{invoice['status_label']} → {new_status_label}"
        ),
        invoice["owner_username"] or "",
    )
    notify_platform_billing_status_change(invoice, status)

    if return_to == "detail":
        return RedirectResponse(
            f"/platform/billing/invoices/{invoice_id}?invoice_updated=1",
            status_code=302,
        )

    return RedirectResponse(
        "/platform/billing?invoice_updated=1",
        status_code=302,
    )


@router.get("/platform/billing/invoices/{invoice_id}/export")
async def platform_billing_invoice_export(
    request: Request,
    invoice_id: int,
):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role != "superadmin":
        return RedirectResponse("/", status_code=302)

    conn = connect()
    c = conn.cursor()
    invoice = fetch_platform_billing_invoice(c, invoice_id)
    invoice_activity = (
        fetch_platform_billing_invoice_activity(c, invoice)
        if invoice
        else []
    )
    conn.close()

    if not invoice:
        return RedirectResponse(
            "/platform/billing?error=invoice_not_found",
            status_code=302,
        )

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Счёт платформы"])
    writer.writerow(["ID счёта", invoice["id"]])
    writer.writerow(["Номер", invoice["invoice_number"] or ""])
    writer.writerow(["Компания", invoice["company_name"]])
    writer.writerow(["ID компании", invoice["company_id"]])
    writer.writerow(["Владелец", invoice["owner_username"]])
    writer.writerow(["Период", invoice["period"] or ""])
    writer.writerow(["Тариф", invoice["plan_label"]])
    writer.writerow(["Сумма", invoice["amount"] or 0])
    writer.writerow(["Валюта", invoice["currency"] or "RUB"])
    writer.writerow(["Статус", invoice["status_label"]])
    writer.writerow(["Оплатить до", invoice["due_date"] or ""])
    writer.writerow(["Оплачен", invoice["paid_at"] or ""])
    writer.writerow(["Создан", invoice["created_at"] or ""])
    writer.writerow(["Примечание", invoice["notes"] or ""])

    return Response(
        content="\ufeff" + output.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": (
                f"attachment; filename=platform_invoice_{invoice_id}.csv"
            )
        },
    )


@router.get("/platform/billing/invoices/{invoice_id}", response_class=HTMLResponse)
async def platform_billing_invoice_detail_page(
    request: Request,
    invoice_id: int,
):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role != "superadmin":
        return RedirectResponse("/", status_code=302)

    conn = connect()
    c = conn.cursor()
    invoice = fetch_platform_billing_invoice(c, invoice_id)
    invoice_activity = (
        fetch_platform_billing_invoice_activity(c, invoice)
        if invoice
        else []
    )
    conn.close()

    if not invoice:
        return RedirectResponse(
            "/platform/billing?error=invoice_not_found",
            status_code=302,
        )

    return templates.TemplateResponse(
        request,
        "platform_billing_invoice_detail.html",
        {
            "request": request,
            "username": username,
            "role": role,
            "generated_at": get_platform_generated_at(),
            "invoice": invoice,
            "invoice_activity": invoice_activity,
            "activity_summary": (
                build_platform_billing_invoice_activity_summary(
                    invoice_activity,
                )
            ),
            "status_options": get_billing_invoice_status_options(),
        },
    )


@router.get("/platform/billing/export")
async def platform_billing_export(
    request: Request,
    status: str = "all",
    company_id: str = "all",
):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role != "superadmin":
        return RedirectResponse("/", status_code=302)

    status_filter = normalize_billing_invoice_filter(status)
    selected_company_id = normalize_platform_billing_company_id(company_id)

    conn = connect()
    c = conn.cursor()
    invoices = fetch_platform_billing_invoices(
        c,
        status_filter=status_filter,
        company_id=selected_company_id,
    )
    conn.close()
    monthly_summary = build_platform_billing_monthly_summary(invoices)

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Динамика по месяцам"])
    writer.writerow([
        "Период",
        "Счётов",
        "Начислено",
        "Оплачено",
        "К оплате",
        "Просрочено счетов",
        "Просрочено сумма",
    ])

    for month in monthly_summary:
        writer.writerow([
            month["period"],
            month["count"],
            month["total_amount"],
            month["paid_amount"],
            month["unpaid_amount"],
            month["overdue_count"],
            month["overdue_amount"],
        ])

    writer.writerow([])
    writer.writerow(["Счета"])
    writer.writerow([
        "ID компании",
        "Компания",
        "Владелец",
        "Номер",
        "Период",
        "Тариф",
        "Сумма",
        "Валюта",
        "Статус",
        "Оплатить до",
        "Оплачен",
        "Создан",
    ])

    for invoice in invoices:
        writer.writerow([
            invoice["company_id"] or "",
            invoice["company_name"],
            invoice["owner_username"],
            invoice["invoice_number"] or "",
            invoice["period"] or "",
            invoice["plan_label"],
            invoice["amount"] or 0,
            invoice["currency"] or "RUB",
            invoice["status_label"],
            invoice["due_date"] or "",
            invoice["paid_at"] or "",
            invoice["created_at"] or "",
        ])

    filename_parts = ["platform_billing"]

    if status_filter != "all":
        filename_parts.append(status_filter)

    if selected_company_id != "all":
        filename_parts.append(f"company_{selected_company_id}")

    filename = "_".join(filename_parts) + ".csv"

    if status_filter != "all" and selected_company_id == "all":
        filename = f"platform_billing_{status_filter}.csv"

    return Response(
        content="\ufeff" + output.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f"attachment; filename={filename}"
        },
    )


@router.get("/platform/readiness", response_class=HTMLResponse)
async def platform_readiness_page(
    request: Request,
    notice: str = "",
    error: str = "",
):
    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role != "superadmin":
        return RedirectResponse("/", status_code=302)

    readiness = get_platform_release_readiness()
    history = get_platform_release_readiness_history()
    comparison = compare_platform_release_readiness_to_snapshot(
        readiness,
    )
    trend = get_platform_release_readiness_trend(history)
    launch_plan = get_platform_release_launch_plan(readiness)
    signoffs = get_platform_release_signoff_history()
    timeline = get_platform_release_timeline(history, signoffs)
    runbook = get_platform_release_runbook(
        readiness,
        launch_plan,
        timeline,
    )
    control_center = get_platform_release_control_center(
        readiness,
        launch_plan,
        timeline,
        runbook,
    )
    post_launch_review = get_platform_release_post_launch_review(
        readiness,
        comparison,
        trend,
        launch_plan,
        timeline,
        control_center,
        history,
        signoffs,
    )

    return templates.TemplateResponse(
        request,
        "platform_readiness.html",
        {
            "request": request,
            "username": username,
            "role": role,
            "readiness": readiness,
            "history": history,
            "comparison": comparison,
            "trend": trend,
            "launch_plan": launch_plan,
            "signoffs": signoffs,
            "timeline": timeline,
            "runbook": runbook,
            "control_center": control_center,
            "post_launch_review": post_launch_review,
            "links": build_platform_readiness_links(),
            "notice": notice,
            "error": error,
        },
    )


@router.post("/platform/readiness/snapshot")
async def platform_readiness_snapshot(request: Request):
    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role != "superadmin":
        return RedirectResponse("/", status_code=302)

    create_platform_release_readiness_snapshot(username)
    return RedirectResponse(
        "/platform/readiness?notice=snapshot_saved",
        status_code=302,
    )


@router.post("/platform/readiness/signoff")
async def platform_readiness_signoff(request: Request):
    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role != "superadmin":
        return RedirectResponse("/", status_code=302)

    form = await request.form()
    decision = str(form.get("decision") or "blocked").strip()
    comment = str(form.get("comment") or "").strip()
    signoff_id, error = create_platform_release_signoff(
        username,
        decision,
        comment,
    )

    if error == "launch_blocked":
        return RedirectResponse(
            "/platform/readiness?error=launch_blocked",
            status_code=302,
        )

    return RedirectResponse(
        f"/platform/readiness?notice=signoff_saved&signoff={signoff_id}",
        status_code=302,
    )


@router.get("/platform/readiness/export")
async def platform_readiness_export(request: Request):
    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role != "superadmin":
        return RedirectResponse("/", status_code=302)

    readiness = get_platform_release_readiness()
    history = get_platform_release_readiness_history()
    comparison = compare_platform_release_readiness_to_snapshot(
        readiness,
    )
    trend = get_platform_release_readiness_trend(history)
    launch_plan = get_platform_release_launch_plan(readiness)
    signoffs = get_platform_release_signoff_history()
    timeline = get_platform_release_timeline(history, signoffs)
    runbook = get_platform_release_runbook(
        readiness,
        launch_plan,
        timeline,
    )
    control_center = get_platform_release_control_center(
        readiness,
        launch_plan,
        timeline,
        runbook,
    )
    post_launch_review = get_platform_release_post_launch_review(
        readiness,
        comparison,
        trend,
        launch_plan,
        timeline,
        control_center,
        history,
        signoffs,
    )
    output = io.StringIO()
    writer = csv.writer(output)

    writer.writerow(["Готовность релиза"])
    writer.writerow(["Сгенерировано", readiness["generated_at"]])
    writer.writerow(["Окружение", readiness["environment"]])
    writer.writerow(["Статус", readiness["status_label"]])
    writer.writerow(["Оценка", readiness["score"]])
    writer.writerow(["Готово", readiness["ok_count"]])
    writer.writerow(["Внимание", readiness["warning_count"]])
    writer.writerow(["Критично", readiness["critical_count"]])
    writer.writerow(["Резюме", readiness["headline"]])
    writer.writerow([])

    backup_status = readiness["backup_status"]
    writer.writerow(["Резервные копии"])
    writer.writerow(["Статус", backup_status["status_label"]])
    writer.writerow(["Резюме", backup_status["summary"]])
    writer.writerow(["Действие", backup_status["action"]])
    writer.writerow(["Копий", backup_status["count"]])
    writer.writerow(["Последняя копия", backup_status["latest_name"]])
    writer.writerow(["Возраст последней", backup_status["latest_age_label"]])
    writer.writerow(["Общий размер", backup_status["total_size_label"]])
    writer.writerow([])

    writer.writerow(["Сравнение с последним снимком"])
    writer.writerow(["Есть снимок", "да" if comparison["has_snapshot"] else "нет"])
    writer.writerow(["Состояние", comparison["label"]])
    writer.writerow(["Резюме", comparison["summary"]])
    writer.writerow(["Дата снимка", comparison["snapshot_created_at"]])
    writer.writerow(["Динамика оценки", comparison["score_delta"]])
    writer.writerow(["Динамика критичных", comparison["critical_delta"]])
    writer.writerow(["Динамика предупреждений", comparison["warning_delta"]])
    writer.writerow([])

    writer.writerow(["Новые блокеры"])
    writer.writerow(["Категория", "Проверка", "Действие"])
    for check in comparison["new_blockers"]:
        writer.writerow([
            check["category_label"],
            check["title"],
            check["action"],
        ])
    writer.writerow([])

    writer.writerow(["Закрытые блокеры"])
    writer.writerow(["Категория", "Проверка", "Действие"])
    for check in comparison["resolved_blockers"]:
        writer.writerow([
            check["category_label"],
            check["title"],
            check["action"],
        ])
    writer.writerow([])

    writer.writerow(["Тренд снимков"])
    writer.writerow(["Есть история", "да" if trend["has_history"] else "нет"])
    writer.writerow(["Состояние", trend["label"]])
    writer.writerow(["Резюме", trend["summary"]])
    writer.writerow(["Снимков", trend["total_snapshots"]])
    writer.writerow(["Последняя оценка", trend["latest_score"]])
    writer.writerow(["Динамика оценки", trend["score_change"]])
    writer.writerow(["Динамика критичных", trend["critical_change"]])
    writer.writerow(["Динамика предупреждений", trend["warning_change"]])
    writer.writerow(["Лучший снимок", trend["best_score"], trend["best_date"]])
    writer.writerow(["Худший снимок", trend["worst_score"], trend["worst_date"]])
    writer.writerow([])

    writer.writerow(["План запуска"])
    writer.writerow(["Решение", launch_plan["label"]])
    writer.writerow(["Режим", launch_plan["recommended_mode"]])
    writer.writerow(["Резюме", launch_plan["summary"]])
    writer.writerow(["Оценка", launch_plan["score"]])
    writer.writerow(["Критично", launch_plan["critical_count"]])
    writer.writerow(["Внимание", launch_plan["warning_count"]])
    writer.writerow([])

    writer.writerow(["Этапы запуска"])
    writer.writerow(["Этап", "Статус", "Действие", "Описание", "Ссылка"])
    for phase in launch_plan["phases"]:
        for item in phase["items"]:
            writer.writerow([
                phase["title"],
                item["status_label"],
                item["title"],
                item["description"],
                item["url"],
            ])
    writer.writerow([])

    writer.writerow(["Подтверждения запуска"])
    writer.writerow([
        "Дата",
        "Автор",
        "Решение",
        "Режим",
        "Оценка",
        "Критично",
        "Внимание",
        "Комментарий",
        "Снимок",
    ])
    for signoff in signoffs:
        writer.writerow([
            signoff["signed_at"],
            signoff["signed_by"],
            signoff["decision_label"],
            signoff["recommended_mode"],
            signoff["score"],
            signoff["critical_count"],
            signoff["warning_count"],
            signoff["comment"],
            signoff["snapshot_url"],
        ])
    writer.writerow([])

    writer.writerow(["Журнал релиза"])
    writer.writerow([
        "Дата",
        "Тип",
        "Событие",
        "Автор",
        "Статус",
        "Оценка",
        "Описание",
        "Ссылка",
    ])
    for event in timeline["events"]:
        writer.writerow([
            event["at"],
            event["type_label"],
            event["title"],
            event["actor"],
            event["badge"],
            event["score"],
            event["description"],
            event["url"],
        ])
    writer.writerow([])

    writer.writerow(["Регламент релиза"])
    writer.writerow(["Состояние", runbook["label"]])
    writer.writerow(["Режим", runbook["mode"]])
    writer.writerow(["Резюме", runbook["summary"]])
    writer.writerow(["Шагов", runbook["steps_count"]])
    writer.writerow(["Критичных шагов", runbook["critical_steps_count"]])
    writer.writerow(["Есть подтверждение", "да" if runbook["has_signoff"] else "нет"])
    writer.writerow([])

    writer.writerow(["Шаги регламента"])
    writer.writerow(["Раздел", "Статус", "Владелец", "Шаг", "Описание", "Ссылка"])
    for section in runbook["sections"]:
        for step in section["steps"]:
            writer.writerow([
                section["title"],
                step["status_label"],
                step["owner"],
                step["title"],
                step["description"],
                step["url"],
            ])
    writer.writerow([])

    writer.writerow(["Триггеры отката"])
    for trigger in runbook["rollback_triggers"]:
        writer.writerow([trigger])
    writer.writerow([])

    writer.writerow(["Центр контроля запуска"])
    writer.writerow(["Состояние", control_center["label"]])
    writer.writerow(["Риск", control_center["risk_level"]])
    writer.writerow(["Режим", control_center["mode"]])
    writer.writerow(["Резюме", control_center["summary"]])
    writer.writerow([
        "Следующая точка",
        control_center["next_checkpoint"]["title"],
    ])
    writer.writerow([])

    writer.writerow(["Метрики контроля"])
    writer.writerow(["Метрика", "Значение", "Статус", "Описание", "Ссылка"])
    for metric in control_center["metrics"]:
        writer.writerow([
            metric["title"],
            metric["value"],
            metric["status_label"],
            metric["description"],
            metric["url"],
        ])
    writer.writerow([])

    writer.writerow(["Контрольные точки"])
    writer.writerow(["Точка", "Когда", "Статус", "Описание", "Ссылка"])
    for checkpoint in control_center["checkpoints"]:
        writer.writerow([
            checkpoint["title"],
            checkpoint["value"],
            checkpoint["status_label"],
            checkpoint["description"],
            checkpoint["url"],
        ])
    writer.writerow([])

    writer.writerow(["Фокус мониторинга"])
    writer.writerow(["Область", "Значение", "Статус", "Действие", "Ссылка"])
    for item in control_center["watch_focus"]:
        writer.writerow([
            item["title"],
            item["value"],
            item["status_label"],
            item["description"],
            item["url"],
        ])
    writer.writerow([])

    writer.writerow(["Условия остановки"])
    for condition in control_center["stop_conditions"]:
        writer.writerow([condition])
    writer.writerow([])

    writer.writerow(["Пострелизный разбор"])
    writer.writerow(["Состояние", post_launch_review["label"]])
    writer.writerow(["Итог", post_launch_review["outcome"]])
    writer.writerow(["Резюме", post_launch_review["summary"]])
    writer.writerow(["Оценка", post_launch_review["score"]])
    writer.writerow(["Динамика оценки", post_launch_review["score_delta"]])
    writer.writerow([
        "Динамика критичных",
        post_launch_review["critical_delta"],
    ])
    writer.writerow([
        "Последнее решение",
        post_launch_review["latest_decision"],
        post_launch_review["latest_decision_at"],
    ])
    writer.writerow([])

    writer.writerow(["Метрики разбора"])
    writer.writerow(["Метрика", "Значение", "Статус", "Описание", "Ссылка"])
    for metric in post_launch_review["metrics"]:
        writer.writerow([
            metric["title"],
            metric["value"],
            metric["status_label"],
            metric["description"],
            metric["url"],
        ])
    writer.writerow([])

    writer.writerow(["Что сработало"])
    writer.writerow(["Пункт", "Значение", "Описание", "Ссылка"])
    for item in post_launch_review["positives"]:
        writer.writerow([
            item["title"],
            item["value"],
            item["description"],
            item["url"],
        ])
    writer.writerow([])

    writer.writerow(["Что проверить"])
    writer.writerow(["Пункт", "Значение", "Статус", "Действие", "Ссылка"])
    for item in post_launch_review["issues"]:
        writer.writerow([
            item["title"],
            item["value"],
            item["status_label"],
            item["description"],
            item["url"],
        ])
    writer.writerow([])

    writer.writerow(["Решения после запуска"])
    writer.writerow(["Решение", "Значение", "Статус", "Описание", "Ссылка"])
    for item in post_launch_review["decisions"]:
        writer.writerow([
            item["title"],
            item["value"],
            item["status_label"],
            item["description"],
            item["url"],
        ])
    writer.writerow([])

    writer.writerow(["Категории"])
    writer.writerow([
        "Категория",
        "Статус",
        "Оценка",
        "Проверок",
        "Готово",
        "Внимание",
        "Критично",
    ])
    for category in readiness["categories"]:
        writer.writerow([
            category["label"],
            category["status_label"],
            category["score"],
            category["checks"],
            category["ok"],
            category["warning"],
            category["critical"],
        ])
    writer.writerow([])

    writer.writerow(["Следующие действия"])
    writer.writerow([
        "Категория",
        "Проверка",
        "Статус",
        "Описание",
        "Действие",
        "Ссылка",
    ])
    for check in readiness["next_actions"]:
        writer.writerow([
            check["category_label"],
            check["title"],
            check["status_label"],
            check["description"],
            check["action"],
            check["url"],
        ])
    writer.writerow([])

    writer.writerow(["Все проверки"])
    writer.writerow([
        "Категория",
        "Ключ",
        "Проверка",
        "Статус",
        "Вес",
        "Баллы",
        "Описание",
        "Действие",
        "Ссылка",
    ])
    for check in readiness["checks"]:
        writer.writerow([
            check["category_label"],
            check["key"],
            check["title"],
            check["status_label"],
            check["weight"],
            check["points"],
            check["description"],
            check["action"],
            check["url"],
        ])
    writer.writerow([])

    writer.writerow(["История снимков"])
    writer.writerow([
        "Дата",
        "Автор",
        "Статус",
        "Оценка",
        "Динамика",
        "Критично",
        "Внимание",
        "Готово",
        "Резюме",
    ])
    for snapshot in history:
        writer.writerow([
            snapshot["created_at"],
            snapshot["created_by"],
            snapshot["status_label"],
            snapshot["score"],
            snapshot["delta_label"],
            snapshot["critical_count"],
            snapshot["warning_count"],
            snapshot["ok_count"],
            snapshot["headline"],
        ])

    return Response(
        "\ufeff" + output.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": (
                "attachment; filename=platform_release_readiness.csv"
            ),
        },
    )


@router.get(
    "/platform/readiness/snapshots/{snapshot_id}",
    response_class=HTMLResponse,
)
async def platform_readiness_snapshot_page(
    request: Request,
    snapshot_id: int,
):
    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role != "superadmin":
        return RedirectResponse("/", status_code=302)

    snapshot = get_platform_release_readiness_snapshot(snapshot_id)

    if not snapshot:
        return RedirectResponse(
            "/platform/readiness?error=snapshot_not_found",
            status_code=302,
        )

    snapshot_comparison = compare_platform_release_readiness_snapshots(
        snapshot,
    )
    snapshot_signoffs = get_platform_release_signoff_history(
        snapshot_id=snapshot_id,
    )

    return templates.TemplateResponse(
        request,
        "platform_readiness_snapshot.html",
        {
            "request": request,
            "username": username,
            "role": role,
            "snapshot": snapshot,
            "snapshot_comparison": snapshot_comparison,
            "launch_plan": snapshot["launch_plan"],
            "snapshot_signoffs": snapshot_signoffs,
            "links": build_platform_readiness_links(snapshot_id),
        },
    )


@router.get("/platform/readiness/snapshots/{snapshot_id}/export")
async def platform_readiness_snapshot_export(
    request: Request,
    snapshot_id: int,
):
    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role != "superadmin":
        return RedirectResponse("/", status_code=302)

    snapshot = get_platform_release_readiness_snapshot(snapshot_id)

    if not snapshot:
        return RedirectResponse(
            "/platform/readiness?error=snapshot_not_found",
            status_code=302,
        )

    snapshot_comparison = compare_platform_release_readiness_snapshots(
        snapshot,
    )
    launch_plan = snapshot["launch_plan"]
    snapshot_signoffs = get_platform_release_signoff_history(
        snapshot_id=snapshot_id,
    )

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Снимок готовности релиза"])
    writer.writerow(["Номер", snapshot["id"]])
    writer.writerow(["Дата", snapshot["created_at"]])
    writer.writerow(["Автор", snapshot["created_by"]])
    writer.writerow(["Статус", snapshot["status_label"]])
    writer.writerow(["Оценка", snapshot["score"]])
    writer.writerow(["Динамика", snapshot["delta_label"]])
    writer.writerow(["Критично", snapshot["critical_count"]])
    writer.writerow(["Внимание", snapshot["warning_count"]])
    writer.writerow(["Готово", snapshot["ok_count"]])
    writer.writerow(["Резюме", snapshot["headline"]])
    writer.writerow(["Окружение", snapshot["environment"]])
    writer.writerow([])

    writer.writerow(["Сравнение с предыдущим снимком"])
    writer.writerow([
        "Есть предыдущий снимок",
        "да" if snapshot_comparison["has_previous"] else "нет",
    ])
    writer.writerow(["Состояние", snapshot_comparison["label"]])
    writer.writerow(["Резюме", snapshot_comparison["summary"]])
    writer.writerow([
        "Дата предыдущего снимка",
        snapshot_comparison["previous_created_at"],
    ])
    writer.writerow(["Динамика оценки", snapshot_comparison["score_delta"]])
    writer.writerow([
        "Динамика критичных",
        snapshot_comparison["critical_delta"],
    ])
    writer.writerow([
        "Динамика предупреждений",
        snapshot_comparison["warning_delta"],
    ])
    writer.writerow([])

    writer.writerow(["Новые блокеры"])
    writer.writerow(["Категория", "Проверка", "Действие"])
    for check in snapshot_comparison["new_blockers"]:
        writer.writerow([
            check["category_label"],
            check["title"],
            check["action"],
        ])
    writer.writerow([])

    writer.writerow(["Закрытые блокеры"])
    writer.writerow(["Категория", "Проверка", "Действие"])
    for check in snapshot_comparison["resolved_blockers"]:
        writer.writerow([
            check["category_label"],
            check["title"],
            check["action"],
        ])
    writer.writerow([])

    writer.writerow(["Изменения проверок"])
    writer.writerow(["Категория", "Проверка", "Было", "Стало", "Действие"])
    for check in snapshot_comparison["changed_checks"]:
        writer.writerow([
            check["category_label"],
            check["title"],
            check["from_status"],
            check["to_status"],
            check["action"],
        ])
    writer.writerow([])

    writer.writerow(["План запуска снимка"])
    writer.writerow(["Решение", launch_plan["label"]])
    writer.writerow(["Режим", launch_plan["recommended_mode"]])
    writer.writerow(["Резюме", launch_plan["summary"]])
    writer.writerow(["Оценка", launch_plan["score"]])
    writer.writerow(["Критично", launch_plan["critical_count"]])
    writer.writerow(["Внимание", launch_plan["warning_count"]])
    writer.writerow([])

    writer.writerow(["Этапы запуска"])
    writer.writerow(["Этап", "Статус", "Действие", "Описание", "Ссылка"])
    for phase in launch_plan["phases"]:
        for item in phase["items"]:
            writer.writerow([
                phase["title"],
                item["status_label"],
                item["title"],
                item["description"],
                item["url"],
            ])
    writer.writerow([])

    writer.writerow(["Подтверждения по снимку"])
    writer.writerow([
        "Дата",
        "Автор",
        "Решение",
        "Режим",
        "Оценка",
        "Критично",
        "Внимание",
        "Комментарий",
    ])
    for signoff in snapshot_signoffs:
        writer.writerow([
            signoff["signed_at"],
            signoff["signed_by"],
            signoff["decision_label"],
            signoff["recommended_mode"],
            signoff["score"],
            signoff["critical_count"],
            signoff["warning_count"],
            signoff["comment"],
        ])
    writer.writerow([])

    writer.writerow(["Категории"])
    writer.writerow([
        "Категория",
        "Статус",
        "Оценка",
        "Проверок",
        "Готово",
        "Внимание",
        "Критично",
    ])
    for category in snapshot["categories"]:
        writer.writerow([
            category["label"],
            category["status_label"],
            category["score"],
            category["checks"],
            category["ok"],
            category["warning"],
            category["critical"],
        ])
    writer.writerow([])

    writer.writerow(["Следующие действия"])
    writer.writerow([
        "Категория",
        "Проверка",
        "Статус",
        "Описание",
        "Действие",
        "Ссылка",
    ])
    for check in snapshot["next_actions"]:
        writer.writerow([
            check["category_label"],
            check["title"],
            check["status_label"],
            check["description"],
            check["action"],
            check["url"],
        ])
    writer.writerow([])

    writer.writerow(["Все проверки"])
    writer.writerow([
        "Категория",
        "Ключ",
        "Проверка",
        "Статус",
        "Вес",
        "Баллы",
        "Описание",
        "Действие",
        "Ссылка",
    ])
    for check in snapshot["checks"]:
        writer.writerow([
            check["category_label"],
            check["key"],
            check["title"],
            check["status_label"],
            check["weight"],
            check["points"],
            check["description"],
            check["action"],
            check["url"],
        ])

    return Response(
        "\ufeff" + output.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": (
                "attachment; filename="
                f"platform_release_readiness_snapshot_{snapshot_id}.csv"
            ),
        },
    )


@router.get("/api/platform/readiness")
async def api_platform_readiness(request: Request):
    username = get_user(request)

    if not username:
        return JSONResponse({"error": "auth_required"}, status_code=401)

    role = get_role(username)

    if role != "superadmin":
        return JSONResponse({"error": "forbidden"}, status_code=403)

    readiness = get_platform_release_readiness()
    readiness["comparison"] = (
        compare_platform_release_readiness_to_snapshot(readiness)
    )
    readiness["trend"] = get_platform_release_readiness_trend()
    readiness["launch_plan"] = get_platform_release_launch_plan(readiness)
    signoffs = get_platform_release_signoff_history()
    readiness["signoffs"] = signoffs
    timeline = get_platform_release_timeline(
        signoffs=signoffs,
    )
    readiness["timeline"] = timeline
    readiness["runbook"] = get_platform_release_runbook(
        readiness,
        readiness["launch_plan"],
        timeline,
    )
    readiness["control_center"] = get_platform_release_control_center(
        readiness,
        readiness["launch_plan"],
        timeline,
        readiness["runbook"],
    )
    readiness["post_launch_review"] = (
        get_platform_release_post_launch_review(
            readiness,
            readiness["comparison"],
            readiness["trend"],
            readiness["launch_plan"],
            timeline,
            readiness["control_center"],
            None,
            signoffs,
        )
    )
    return readiness


@router.get("/api/platform/readiness/post-launch-review")
async def api_platform_readiness_post_launch_review(request: Request):
    username = get_user(request)

    if not username:
        return JSONResponse({"error": "auth_required"}, status_code=401)

    role = get_role(username)

    if role != "superadmin":
        return JSONResponse({"error": "forbidden"}, status_code=403)

    readiness = get_platform_release_readiness()
    history = get_platform_release_readiness_history()
    comparison = compare_platform_release_readiness_to_snapshot(readiness)
    trend = get_platform_release_readiness_trend(history)
    launch_plan = get_platform_release_launch_plan(readiness)
    signoffs = get_platform_release_signoff_history()
    timeline = get_platform_release_timeline(history, signoffs)
    control_center = get_platform_release_control_center(
        readiness,
        launch_plan,
        timeline,
    )
    return get_platform_release_post_launch_review(
        readiness,
        comparison,
        trend,
        launch_plan,
        timeline,
        control_center,
        history,
        signoffs,
    )


@router.get("/api/platform/readiness/control-center")
async def api_platform_readiness_control_center(request: Request):
    username = get_user(request)

    if not username:
        return JSONResponse({"error": "auth_required"}, status_code=401)

    role = get_role(username)

    if role != "superadmin":
        return JSONResponse({"error": "forbidden"}, status_code=403)

    readiness = get_platform_release_readiness()
    launch_plan = get_platform_release_launch_plan(readiness)
    timeline = get_platform_release_timeline()
    runbook = get_platform_release_runbook(
        readiness,
        launch_plan,
        timeline,
    )
    return get_platform_release_control_center(
        readiness,
        launch_plan,
        timeline,
        runbook,
    )


@router.get("/api/platform/readiness/runbook")
async def api_platform_readiness_runbook(request: Request):
    username = get_user(request)

    if not username:
        return JSONResponse({"error": "auth_required"}, status_code=401)

    role = get_role(username)

    if role != "superadmin":
        return JSONResponse({"error": "forbidden"}, status_code=403)

    readiness = get_platform_release_readiness()
    launch_plan = get_platform_release_launch_plan(readiness)
    timeline = get_platform_release_timeline()
    return get_platform_release_runbook(readiness, launch_plan, timeline)


@router.get("/api/platform/readiness/timeline")
async def api_platform_readiness_timeline(request: Request):
    username = get_user(request)

    if not username:
        return JSONResponse({"error": "auth_required"}, status_code=401)

    role = get_role(username)

    if role != "superadmin":
        return JSONResponse({"error": "forbidden"}, status_code=403)

    return get_platform_release_timeline()


@router.get("/api/platform/readiness/signoffs")
async def api_platform_readiness_signoffs(request: Request):
    username = get_user(request)

    if not username:
        return JSONResponse({"error": "auth_required"}, status_code=401)

    role = get_role(username)

    if role != "superadmin":
        return JSONResponse({"error": "forbidden"}, status_code=403)

    return {
        "signoffs": get_platform_release_signoff_history(),
    }


@router.get("/api/platform/readiness/launch-plan")
async def api_platform_readiness_launch_plan(request: Request):
    username = get_user(request)

    if not username:
        return JSONResponse({"error": "auth_required"}, status_code=401)

    role = get_role(username)

    if role != "superadmin":
        return JSONResponse({"error": "forbidden"}, status_code=403)

    readiness = get_platform_release_readiness()
    return get_platform_release_launch_plan(readiness)


@router.get("/platform/a3-health", response_class=HTMLResponse)
async def platform_a3_health_page(
    request: Request,
    status: str = "all",
    search: str = "",
):
    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    if get_role(username) != "superadmin":
        return RedirectResponse("/", status_code=302)

    health = get_a3_platform_health(
        status_filter=status,
        search=search,
    )
    history = get_a3_scheduler_watchdog_history(limit=12)
    trend = get_a3_scheduler_watchdog_trend(history=history)
    links = get_platform_dashboard_links()
    links.update({
        "platform": links["page"],
        "base": "/platform/a3-health",
        "export": health["export_url"],
    })

    return templates.TemplateResponse(
        request,
        "platform_a3_health.html",
        {
            "request": request,
            "username": username,
            "health": health,
            "summary": health["summary"],
            "companies": health["items"],
            "history": history,
            "trend": trend,
            "links": links,
        },
    )


@router.get("/api/platform/a3-health/history")
async def api_platform_a3_health_history(request: Request, limit: int = 12):
    username = get_user(request)

    if not username:
        return JSONResponse({"error": "auth_required"}, status_code=401)

    if get_role(username) != "superadmin":
        return JSONResponse({"error": "forbidden"}, status_code=403)

    history = get_a3_scheduler_watchdog_history(limit=limit)
    return {
        "ok": True,
        "history": history,
        "trend": get_a3_scheduler_watchdog_trend(history=history),
    }


def _a3_platform_incident_redirect(
    incident_id,
    result,
    status="active",
    assignee="all",
    search="",
    success_notice="updated",
):
    target = build_a3_platform_incidents_url(status, assignee, search)
    separator = "&" if "?" in target else "?"
    flag = (
        {"notice": success_notice}
        if result.get("ok")
        else {"error": result.get("error") or "action_failed"}
    )
    return RedirectResponse(
        f"{target}{separator}{urlencode(flag)}#incident-{incident_id}",
        status_code=302,
    )


@router.get("/platform/a3-health/incidents", response_class=HTMLResponse)
async def platform_a3_incidents_page(
    request: Request,
    status: str = "active",
    assignee: str = "all",
    search: str = "",
    notice: str = "",
    error: str = "",
):
    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    if get_role(username) != "superadmin":
        return RedirectResponse("/", status_code=302)

    center = get_a3_platform_incidents(
        status_filter=status,
        assignee_filter=assignee,
        search=search,
        current_username=username,
    )
    links = get_platform_dashboard_links()
    links.update({
        "platform": links["page"],
        "base": center["base_url"],
    })

    return templates.TemplateResponse(
        request,
        "platform_a3_incidents.html",
        {
            "request": request,
            "username": username,
            "center": center,
            "summary": center["summary"],
            "incidents": center["items"],
            "admins": get_a3_platform_incident_admins(),
            "notice": notice,
            "error": error,
            "links": links,
        },
    )


@router.get("/api/platform/a3-health/incidents")
async def api_platform_a3_incidents(
    request: Request,
    status: str = "active",
    assignee: str = "all",
    search: str = "",
    limit: int = 100,
):
    username = get_user(request)

    if not username:
        return JSONResponse({"error": "auth_required"}, status_code=401)

    if get_role(username) != "superadmin":
        return JSONResponse({"error": "forbidden"}, status_code=403)

    return {
        "ok": True,
        **get_a3_platform_incidents(
            status_filter=status,
            assignee_filter=assignee,
            search=search,
            current_username=username,
            limit=limit,
        ),
    }


@router.get(
    "/platform/a3-health/incidents/analytics",
    response_class=HTMLResponse,
)
async def platform_a3_incident_analytics_page(
    request: Request,
    period: str = "30",
    company_id: str = "all",
):
    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    if get_role(username) != "superadmin":
        return RedirectResponse("/", status_code=302)

    analytics = get_a3_platform_incident_analytics(
        period=period,
        company_id=company_id,
    )
    followup_analytics = get_a3_followup_analytics(
        period=period,
        company_id=company_id,
    )
    links = get_platform_dashboard_links()
    links["platform"] = links["page"]

    return templates.TemplateResponse(
        request,
        "platform_a3_incident_analytics.html",
        {
            "request": request,
            "username": username,
            "analytics": analytics,
            "summary": analytics["summary"],
            "companies": analytics["companies"],
            "admin_workload": analytics["admin_workload"],
            "trend": analytics["trend"],
            "recommendations": analytics["recommendations"],
            "followup_analytics": followup_analytics,
            "links": links,
        },
    )


@router.get("/api/platform/a3-health/incidents/analytics")
async def api_platform_a3_incident_analytics(
    request: Request,
    period: str = "30",
    company_id: str = "all",
):
    username = get_user(request)

    if not username:
        return JSONResponse({"error": "auth_required"}, status_code=401)

    if get_role(username) != "superadmin":
        return JSONResponse({"error": "forbidden"}, status_code=403)

    analytics = get_a3_platform_incident_analytics(
        period=period,
        company_id=company_id,
    )
    return {
        "ok": True,
        **analytics,
        "followup_analytics": get_a3_followup_analytics(
            period=period,
            company_id=company_id,
        ),
    }


@router.get("/platform/a3-health/incidents/analytics/export")
async def platform_a3_incident_analytics_export(
    request: Request,
    period: str = "30",
    company_id: str = "all",
):
    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    if get_role(username) != "superadmin":
        return RedirectResponse("/", status_code=302)

    analytics = get_a3_platform_incident_analytics(
        period=period,
        company_id=company_id,
    )
    summary = analytics["summary"]
    output = io.StringIO()
    writer = csv.writer(output)

    writer.writerow(["Сводка по инцидентам A3"])
    writer.writerow(["Период", analytics["period_label"]])
    writer.writerow(["Начало периода", analytics["date_from"]])
    writer.writerow(["Конец периода", analytics["date_to"]])
    writer.writerow(["Инцидентов", summary["total"]])
    writer.writerow(["Активных", summary["active"]])
    writer.writerow(["Закрытых", summary["resolved"]])
    writer.writerow(["SLA реакции, %", summary["response_sla_percent"]])
    writer.writerow(["Реакций в срок", summary["on_time"]])
    writer.writerow(["Реакций с опозданием", summary["late"]])
    writer.writerow(["Реакция просрочена", summary["response_overdue"]])
    writer.writerow(["Эскалировано", summary["escalated"]])
    writer.writerow(["Доля эскалаций, %", summary["escalation_rate"]])
    writer.writerow(["Разборов ожидают", summary["review_pending"]])
    writer.writerow(["Разборов просрочено", summary["review_overdue"]])
    writer.writerow(["Разборов завершено", summary["review_completed"]])
    writer.writerow([
        "Разборы завершены, %",
        summary["review_completion_percent"],
    ])
    writer.writerow(["Среднее время реакции", summary["average_response_label"]])
    writer.writerow([
        "Среднее время восстановления",
        summary["average_resolution_label"],
    ])
    writer.writerow([])

    writer.writerow(["Компании"])
    writer.writerow([
        "ID компании",
        "Компания",
        "Инцидентов",
        "Активных",
        "Закрытых",
        "SLA реакции, %",
        "Реакций с опозданием",
        "Реакция просрочена",
        "Эскалировано",
        "Среднее время реакции",
        "Риск",
        "Оценка риска",
    ])
    for company in analytics["companies"]:
        writer.writerow([
            company["company_id"],
            company["company_name"],
            company["total"],
            company["active"],
            company["resolved"],
            company["response_sla_percent"],
            company["late"],
            company["overdue"],
            company["escalated"],
            company["average_response_label"],
            company["risk_label"],
            company["risk_score"],
        ])
    writer.writerow([])

    writer.writerow(["Нагрузка администраторов"])
    writer.writerow([
        "Ответственный",
        "Инцидентов",
        "Активных",
        "Закрытых",
        "Принято в работу",
        "С опозданием",
        "Эскалировано",
        "Среднее время реакции",
        "Нагрузка",
    ])
    for admin in analytics["admin_workload"]:
        writer.writerow([
            admin["display_name"],
            admin["total"],
            admin["active"],
            admin["resolved"],
            admin["acknowledged"],
            admin["late"],
            admin["escalated"],
            admin["average_response_label"],
            admin["load_label"],
        ])
    writer.writerow([])

    writer.writerow(["Динамика"])
    writer.writerow([
        "Период",
        "Открыто",
        "Закрыто",
        "Реакция с опозданием",
        "Эскалировано",
    ])
    for row in analytics["trend"]:
        writer.writerow([
            row["label"],
            row["opened"],
            row["resolved"],
            row["late"],
            row["escalated"],
        ])
    writer.writerow([])

    writer.writerow(["Инциденты"])
    writer.writerow([
        "ID",
        "ID компании",
        "Компания",
        "Инцидент",
        "Состояние",
        "Обнаружен",
        "Принят в работу",
        "Закрыт",
        "Ответственный",
        "Время реакции",
        "Время восстановления",
        "Соблюдение реакции",
        "Эскалирован",
        "Разбор причин",
    ])
    for record in analytics["records"]:
        writer.writerow([
            record["id"],
            record["company_id"],
            record["company_name"],
            record["title"],
            record["status_label"],
            record["first_detected_at"],
            record["acknowledged_at"],
            record["resolved_at"],
            record["assigned_to"],
            record["response_label"],
            record["resolution_label"],
            record["response_status"],
            record["escalated_label"],
            record["review_status_label"],
        ])

    followup_analytics = get_a3_followup_analytics(
        period=period,
        company_id=company_id,
    )
    writer.writerows(a3_followup_analytics_csv_rows(followup_analytics))

    return Response(
        "\ufeff" + output.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": (
                "attachment; filename="
                f"a3_incident_analytics_{analytics['period']}.csv"
            ),
        },
    )


def _a3_platform_incident_review_redirect(
    incident_id,
    result,
    status="pending",
    company_id="all",
    search="",
):
    target = build_a3_incident_reviews_url(status, company_id, search)
    separator = "&" if "?" in target else "?"
    flag = (
        {"notice": "review_saved"}
        if result.get("ok")
        else {"error": result.get("error") or "action_failed"}
    )
    return RedirectResponse(
        f"{target}{separator}{urlencode(flag)}#review-{incident_id}",
        status_code=302,
    )


@router.get(
    "/platform/a3-health/incidents/reviews",
    response_class=HTMLResponse,
)
async def platform_a3_incident_reviews_page(
    request: Request,
    status: str = "pending",
    company_id: str = "all",
    search: str = "",
    notice: str = "",
    error: str = "",
):
    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    if get_role(username) != "superadmin":
        return RedirectResponse("/", status_code=302)

    center = get_a3_platform_incident_reviews(
        status_filter=status,
        company_id=company_id,
        search=search,
    )
    links = get_platform_dashboard_links()
    links["platform"] = links["page"]
    export_params = {
        "status": center["status_filter"],
        "company_id": center["company_id"],
    }
    if center["search"]:
        export_params["search"] = center["search"]
    links["a3_incident_reviews_export"] = (
        "/platform/a3-health/incidents/reviews/export?"
        + urlencode(export_params)
    )

    return templates.TemplateResponse(
        request,
        "platform_a3_incident_reviews.html",
        {
            "request": request,
            "username": username,
            "center": center,
            "summary": center["summary"],
            "reviews": center["items"],
            "admins": center["admins"],
            "notice": notice,
            "error": error,
            "links": links,
        },
    )


@router.get("/api/platform/a3-health/incidents/reviews")
async def api_platform_a3_incident_reviews(
    request: Request,
    status: str = "pending",
    company_id: str = "all",
    search: str = "",
    limit: int = 100,
):
    username = get_user(request)

    if not username:
        return JSONResponse({"error": "auth_required"}, status_code=401)

    if get_role(username) != "superadmin":
        return JSONResponse({"error": "forbidden"}, status_code=403)

    return {
        "ok": True,
        **get_a3_platform_incident_reviews(
            status_filter=status,
            company_id=company_id,
            search=search,
            limit=limit,
        ),
    }


@router.post("/platform/a3-health/incidents/{incident_id}/review")
async def update_platform_a3_incident_review(
    request: Request,
    incident_id: int,
):
    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    if get_role(username) != "superadmin":
        return RedirectResponse("/", status_code=302)

    form = await request.form()
    result = save_a3_platform_incident_review(
        incident_id=incident_id,
        actor_username=username,
        review_status=form.get("review_status") or "in_progress",
        review_owner=form.get("review_owner") or username,
        root_cause=form.get("root_cause") or "",
        corrective_actions=form.get("corrective_actions") or "",
        prevention_actions=form.get("prevention_actions") or "",
    )
    return _a3_platform_incident_review_redirect(
        incident_id,
        result,
        form.get("return_status") or "pending",
        form.get("company_id") or "all",
        form.get("search") or "",
    )


@router.get("/platform/a3-health/incidents/reviews/export")
async def platform_a3_incident_reviews_export(
    request: Request,
    status: str = "all",
    company_id: str = "all",
    search: str = "",
):
    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    if get_role(username) != "superadmin":
        return RedirectResponse("/", status_code=302)

    center = get_a3_platform_incident_reviews(
        status_filter=status,
        company_id=company_id,
        search=search,
        limit=300,
    )
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "ID инцидента",
        "ID компании",
        "Компания",
        "Инцидент",
        "Закрыт",
        "Состояние разбора",
        "Срок разбора",
        "Ответственный",
        "Причина",
        "Выполненные действия",
        "Профилактика повторения",
        "Разбор завершён",
        "Завершил",
    ])
    for review in center["items"]:
        writer.writerow([
            review["id"],
            review["company_id"],
            review["company_name"],
            review["title"],
            review["resolved_at"] or "",
            review["review_status_label"],
            review["review_due_at"] or review["review_due_label"],
            review["review_owner_label"],
            review["root_cause"] or "",
            review["corrective_actions"] or "",
            review["prevention_actions"] or "",
            review["review_completed_at"] or "",
            review["review_completed_by"] or "",
        ])

    return Response(
        "\ufeff" + output.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": (
                "attachment; filename=a3_incident_reviews.csv"
            ),
        },
    )


def _a3_incident_followup_redirect(
    result,
    status="active",
    company_id="all",
    incident_id="all",
    owner="all",
    search="",
):
    target = build_a3_followups_url(
        status,
        company_id,
        incident_id,
        owner,
        search,
    )
    separator = "&" if "?" in target else "?"
    flag = (
        {"notice": result.get("notice") or "action_saved"}
        if result.get("ok")
        else {"error": result.get("error") or "action_failed"}
    )
    anchor = (
        f"#action-{result['followup_id']}"
        if result.get("followup_id") else "#create-action"
    )
    return RedirectResponse(
        f"{target}{separator}{urlencode(flag)}{anchor}",
        status_code=302,
    )


@router.get(
    "/platform/a3-health/incidents/actions",
    response_class=HTMLResponse,
)
async def platform_a3_incident_actions_page(
    request: Request,
    status: str = "active",
    company_id: str = "all",
    incident_id: str = "all",
    owner: str = "all",
    search: str = "",
    notice: str = "",
    error: str = "",
    monitor_checked: int = 0,
    monitor_notified: int = 0,
    monitor_due_soon: int = 0,
    monitor_overdue: int = 0,
    monitor_verification: int = 0,
):
    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    if get_role(username) != "superadmin":
        return RedirectResponse("/", status_code=302)

    center = get_a3_incident_followups(
        status_filter=status,
        company_id=company_id,
        incident_id=incident_id,
        owner_filter=owner,
        search=search,
        current_username=username,
    )
    monitor = get_a3_followup_monitor_overview()
    quality_monitor = get_a3_followup_quality_monitor_overview()
    monitor["last_run"] = {
        "checked": max(0, int(monitor_checked or 0)),
        "notified": max(0, int(monitor_notified or 0)),
        "due_soon": max(0, int(monitor_due_soon or 0)),
        "overdue": max(0, int(monitor_overdue or 0)),
        "verification": max(0, int(monitor_verification or 0)),
    }
    links = get_platform_dashboard_links()
    links["platform"] = links["page"]
    export_params = {
        "status": center["status_filter"],
        "company_id": center["company_id"],
        "incident_id": center["incident_id"],
        "owner": center["owner_filter"],
    }
    if center["search"]:
        export_params["search"] = center["search"]
    links["a3_incident_actions_export"] = (
        "/platform/a3-health/incidents/actions/export?"
        + urlencode(export_params)
    )

    return templates.TemplateResponse(
        request,
        "platform_a3_incident_actions.html",
        {
            "request": request,
            "username": username,
            "center": center,
            "summary": center["summary"],
            "actions": center["items"],
            "admins": center["admins"],
            "monitor": monitor,
            "quality_monitor": quality_monitor,
            "notice": notice,
            "error": error,
            "links": links,
        },
    )


@router.get("/api/platform/a3-health/incidents/actions")
async def api_platform_a3_incident_actions(
    request: Request,
    status: str = "active",
    company_id: str = "all",
    incident_id: str = "all",
    owner: str = "all",
    search: str = "",
    limit: int = 150,
):
    username = get_user(request)

    if not username:
        return JSONResponse({"error": "auth_required"}, status_code=401)

    if get_role(username) != "superadmin":
        return JSONResponse({"error": "forbidden"}, status_code=403)

    return {
        "ok": True,
        **get_a3_incident_followups(
            status_filter=status,
            company_id=company_id,
            incident_id=incident_id,
            owner_filter=owner,
            search=search,
            current_username=username,
            limit=limit,
        ),
    }


@router.get("/api/platform/a3-health/incidents/actions/monitor")
async def api_platform_a3_incident_action_monitor(request: Request):
    username = get_user(request)

    if not username:
        return JSONResponse({"error": "auth_required"}, status_code=401)

    if get_role(username) != "superadmin":
        return JSONResponse({"error": "forbidden"}, status_code=403)

    return {"ok": True, **get_a3_followup_monitor_overview()}


@router.get("/api/platform/a3-health/incidents/actions/quality-monitor")
async def api_platform_a3_incident_action_quality_monitor(request: Request):
    username = get_user(request)

    if not username:
        return JSONResponse({"error": "auth_required"}, status_code=401)

    if get_role(username) != "superadmin":
        return JSONResponse({"error": "forbidden"}, status_code=403)

    return {"ok": True, **get_a3_followup_quality_monitor_overview()}


@router.get(
    "/platform/a3-health/incidents/actions/quality-alerts",
    response_class=HTMLResponse,
)
async def platform_a3_followup_quality_alerts_page(
    request: Request,
    status: str = "active",
    search: str = "",
    notice: str = "",
    error: str = "",
    sla_checked: int = 0,
    sla_escalated: int = 0,
):
    username = get_user(request)
    if not username:
        return RedirectResponse("/login", status_code=302)
    if get_role(username) != "superadmin":
        return RedirectResponse("/", status_code=302)
    center = get_a3_followup_quality_alerts(status, search)
    quality_sla = get_a3_followup_quality_sla_overview()
    return templates.TemplateResponse(
        request,
        "platform_a3_followup_quality_alerts.html",
        {
            "request": request,
            "username": username,
            "center": center,
            "alerts": center["items"],
            "quality_sla": quality_sla,
            "sla_checked": max(0, sla_checked),
            "sla_escalated": max(0, sla_escalated),
            "notice": notice,
            "error": error,
            "links": get_platform_dashboard_links(),
        },
    )


@router.get("/api/platform/a3-health/incidents/actions/quality-alerts")
async def api_platform_a3_followup_quality_alerts(
    request: Request,
    status: str = "active",
    search: str = "",
    limit: int = 200,
):
    username = get_user(request)
    if not username:
        return JSONResponse({"error": "auth_required"}, status_code=401)
    if get_role(username) != "superadmin":
        return JSONResponse({"error": "forbidden"}, status_code=403)
    return {
        "ok": True,
        **get_a3_followup_quality_alerts(status, search, limit),
    }


@router.get("/api/platform/a3-health/incidents/actions/quality-alerts/sla")
async def api_platform_a3_followup_quality_alert_sla(request: Request):
    username = get_user(request)
    if not username:
        return JSONResponse({"error": "auth_required"}, status_code=401)
    if get_role(username) != "superadmin":
        return JSONResponse({"error": "forbidden"}, status_code=403)
    return {"ok": True, **get_a3_followup_quality_sla_overview()}


@router.post(
    "/platform/a3-health/incidents/actions/quality-alerts/sla/run"
)
async def run_platform_a3_followup_quality_alert_sla(request: Request):
    username = get_user(request)
    if not username:
        return RedirectResponse("/login", status_code=302)
    if get_role(username) != "superadmin":
        return RedirectResponse("/", status_code=302)
    form = await request.form()
    result = run_a3_followup_quality_sla_monitor()
    target = build_a3_followup_quality_alerts_url(
        form.get("return_status") or "active",
        form.get("search") or "",
    )
    separator = "&" if "?" in target else "?"
    params = urlencode({
        "notice": "quality_sla_complete",
        "sla_checked": result["checked"],
        "sla_escalated": result["escalated_alerts"],
    })
    return RedirectResponse(
        f"{target}{separator}{params}#sla-monitor",
        status_code=302,
    )


@router.post(
    "/api/platform/a3-health/incidents/actions/quality-alerts/sla/run"
)
async def api_run_platform_a3_followup_quality_alert_sla(request: Request):
    username = get_user(request)
    if not username:
        return JSONResponse({"error": "auth_required"}, status_code=401)
    if get_role(username) != "superadmin":
        return JSONResponse({"error": "forbidden"}, status_code=403)
    return {"ok": True, **run_a3_followup_quality_sla_monitor()}


def _change_a3_followup_quality_alert(alert_id, username, action, note=""):
    action_name = str(action or "").strip().lower()
    handlers = {
        "acknowledge": acknowledge_a3_followup_quality_alert,
        "resolve": resolve_a3_followup_quality_alert,
        "reopen": reopen_a3_followup_quality_alert,
    }
    handler = handlers.get(action_name)
    if not handler:
        return {"ok": False, "error": "invalid_action"}
    if action_name == "reopen":
        return handler(alert_id, username)
    return handler(alert_id, username, note)


@router.post(
    "/platform/a3-health/incidents/actions/quality-alerts/{alert_id}/{action}"
)
async def change_platform_a3_followup_quality_alert(
    request: Request,
    alert_id: int,
    action: str,
):
    username = get_user(request)
    if not username:
        return RedirectResponse("/login", status_code=302)
    if get_role(username) != "superadmin":
        return RedirectResponse("/", status_code=302)
    form = await request.form()
    result = _change_a3_followup_quality_alert(
        alert_id,
        username,
        action,
        form.get("note") or "",
    )
    target = build_a3_followup_quality_alerts_url(
        form.get("return_status") or "active",
        form.get("search") or "",
    )
    separator = "&" if "?" in target else "?"
    flag = (
        {"notice": result.get("notice") or "quality_alert_saved"}
        if result.get("ok")
        else {"error": result.get("error") or "action_failed"}
    )
    return RedirectResponse(
        f"{target}{separator}{urlencode(flag)}#alert-{alert_id}",
        status_code=302,
    )


@router.post(
    "/api/platform/a3-health/incidents/actions/quality-alerts/{alert_id}/{action}"
)
async def api_change_platform_a3_followup_quality_alert(
    request: Request,
    alert_id: int,
    action: str,
):
    username = get_user(request)
    if not username:
        return JSONResponse({"error": "auth_required"}, status_code=401)
    if get_role(username) != "superadmin":
        return JSONResponse({"error": "forbidden"}, status_code=403)
    try:
        payload = await request.json()
    except Exception:
        payload = {}
    if not isinstance(payload, dict):
        payload = {}
    result = _change_a3_followup_quality_alert(
        alert_id, username, action, payload.get("note") or "",
    )
    if not result.get("ok"):
        code = 404 if result.get("error") == "alert_not_found" else 400
        return JSONResponse(result, status_code=code)
    return result


@router.get("/platform/a3-health/incidents/actions/quality-alerts/export")
async def platform_a3_followup_quality_alerts_export(
    request: Request,
    status: str = "all",
    search: str = "",
):
    username = get_user(request)
    if not username:
        return RedirectResponse("/login", status_code=302)
    if get_role(username) != "superadmin":
        return RedirectResponse("/", status_code=302)
    center = get_a3_followup_quality_alerts(status, search, 500)
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerows(a3_followup_quality_alert_csv_rows(center))
    return Response(
        "\ufeff" + output.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": "attachment; filename=a3_quality_alerts.csv",
        },
    )


@router.post("/platform/a3-health/incidents/actions/create")
async def create_platform_a3_incident_action(request: Request):
    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    if get_role(username) != "superadmin":
        return RedirectResponse("/", status_code=302)

    form = await request.form()
    result = create_a3_incident_followup(
        incident_id=form.get("incident_id") or 0,
        actor_username=username,
        title=form.get("title") or "",
        description=form.get("description") or "",
        action_type=form.get("action_type") or "prevention",
        priority=form.get("priority") or "normal",
        owner_username=form.get("owner_username") or "",
        due_at=form.get("due_at") or "",
    )
    return _a3_incident_followup_redirect(
        result,
        form.get("return_status") or "active",
        form.get("company_id") or "all",
        form.get("return_incident_id") or "all",
        form.get("owner") or "all",
        form.get("search") or "",
    )


@router.post("/platform/a3-health/incidents/actions/{followup_id}/update")
async def update_platform_a3_incident_action(
    request: Request,
    followup_id: int,
):
    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    if get_role(username) != "superadmin":
        return RedirectResponse("/", status_code=302)

    form = await request.form()
    result = update_a3_incident_followup(
        followup_id=followup_id,
        actor_username=username,
        title=form.get("title") or "",
        description=form.get("description") or "",
        status=form.get("action_status") or "open",
        priority=form.get("priority") or "normal",
        owner_username=form.get("owner_username") or "",
        due_at=form.get("due_at") or "",
    )
    return _a3_incident_followup_redirect(
        result,
        form.get("return_status") or "active",
        form.get("company_id") or "all",
        form.get("incident_id") or "all",
        form.get("owner") or "all",
        form.get("search") or "",
    )


@router.post("/platform/a3-health/incidents/actions/{followup_id}/verify")
async def verify_platform_a3_incident_action(
    request: Request,
    followup_id: int,
):
    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    if get_role(username) != "superadmin":
        return RedirectResponse("/", status_code=302)

    form = await request.form()
    result = review_a3_incident_followup(
        followup_id=followup_id,
        actor_username=username,
        decision=form.get("decision") or "",
        note=form.get("verification_note") or "",
        rework_due_at=form.get("rework_due_at") or "",
    )
    return _a3_incident_followup_redirect(
        result,
        form.get("return_status") or "all",
        form.get("company_id") or "all",
        form.get("incident_id") or "all",
        form.get("owner") or "all",
        form.get("search") or "",
    )


@router.post(
    "/api/platform/a3-health/incidents/actions/{followup_id}/verify"
)
async def api_verify_platform_a3_incident_action(
    request: Request,
    followup_id: int,
):
    username = get_user(request)

    if not username:
        return JSONResponse({"error": "auth_required"}, status_code=401)

    if get_role(username) != "superadmin":
        return JSONResponse({"error": "forbidden"}, status_code=403)

    try:
        payload = await request.json()
    except Exception:
        payload = {}
    result = review_a3_incident_followup(
        followup_id=followup_id,
        actor_username=username,
        decision=payload.get("decision") or "",
        note=payload.get("verification_note") or "",
        rework_due_at=payload.get("rework_due_at") or "",
    )
    if not result.get("ok"):
        status_code = (
            404 if result.get("error") == "followup_not_found" else 400
        )
        return JSONResponse(result, status_code=status_code)
    return result


@router.post("/platform/a3-health/incidents/actions/monitor/run")
async def run_platform_a3_incident_action_monitor(request: Request):
    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    if get_role(username) != "superadmin":
        return RedirectResponse("/", status_code=302)

    form = await request.form()
    result = run_a3_incident_followup_monitor()
    target = build_a3_followups_url(
        form.get("return_status") or "active",
        form.get("company_id") or "all",
        form.get("incident_id") or "all",
        form.get("owner") or "all",
        form.get("search") or "",
    )
    separator = "&" if "?" in target else "?"
    params = {
        "notice": "monitor_complete",
        "monitor_checked": result["checked"],
        "monitor_notified": result["notified_actions"],
        "monitor_due_soon": result["due_soon"],
        "monitor_overdue": result["overdue"],
        "monitor_verification": result["verification_pending"],
    }
    return RedirectResponse(
        f"{target}{separator}{urlencode(params)}#deadline-monitor",
        status_code=302,
    )


@router.post("/platform/a3-health/incidents/actions/quality-monitor/run")
async def run_platform_a3_incident_action_quality_monitor(request: Request):
    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    if get_role(username) != "superadmin":
        return RedirectResponse("/", status_code=302)

    form = await request.form()
    run_a3_followup_quality_monitor()
    target = build_a3_followups_url(
        form.get("return_status") or "active",
        form.get("company_id") or "all",
        form.get("incident_id") or "all",
        form.get("owner") or "all",
        form.get("search") or "",
    )
    separator = "&" if "?" in target else "?"
    return RedirectResponse(
        f"{target}{separator}notice=quality_monitor_complete#quality-monitor",
        status_code=302,
    )


@router.post("/api/platform/a3-health/incidents/actions/quality-monitor/run")
async def api_run_platform_a3_incident_action_quality_monitor(request: Request):
    username = get_user(request)

    if not username:
        return JSONResponse({"error": "auth_required"}, status_code=401)

    if get_role(username) != "superadmin":
        return JSONResponse({"error": "forbidden"}, status_code=403)

    return {"ok": True, **run_a3_followup_quality_monitor()}


@router.get("/platform/a3-health/incidents/actions/export")
async def platform_a3_incident_actions_export(
    request: Request,
    status: str = "all",
    company_id: str = "all",
    incident_id: str = "all",
    owner: str = "all",
    search: str = "",
):
    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    if get_role(username) != "superadmin":
        return RedirectResponse("/", status_code=302)

    center = get_a3_incident_followups(
        status_filter=status,
        company_id=company_id,
        incident_id=incident_id,
        owner_filter=owner,
        search=search,
        current_username=username,
        limit=500,
    )
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "ID меры",
        "ID инцидента",
        "ID компании",
        "Компания",
        "Инцидент",
        "Тип меры",
        "Название",
        "Описание",
        "Состояние",
        "Приоритет",
        "Ответственный",
        "Срок",
        "Просрочена",
        "Выполнена",
        "Выполнил",
        "Проверка результата",
        "Комментарий проверки",
        "Проверил",
        "Дата проверки",
        "Попыток проверки",
        "Возвратов на доработку",
        "Создал",
    ])
    for action in center["items"]:
        writer.writerow([
            action["id"],
            action["incident_id"],
            action["company_id"],
            action["company_name"],
            action["incident_title"],
            action["action_type_label"],
            action["title"],
            action["description"] or "",
            action["status_label"],
            action["priority_label"],
            action["owner_label"],
            action["due_at"],
            "Да" if action["is_overdue"] else "Нет",
            action["completed_at"] or "",
            action["completed_by"] or "",
            action["verification_label"],
            action["verification_note"] or "",
            action["verified_by"] or "",
            action["verified_at"] or "",
            action["verification_attempts"],
            action["rework_count"],
            action["created_by"],
        ])

    return Response(
        "\ufeff" + output.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": (
                "attachment; filename=a3_incident_actions.csv"
            ),
        },
    )


@router.post("/platform/a3-health/incidents/{incident_id}/acknowledge")
async def acknowledge_platform_a3_incident(
    request: Request,
    incident_id: int,
):
    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    if get_role(username) != "superadmin":
        return RedirectResponse("/", status_code=302)

    form = await request.form()
    result = acknowledge_a3_platform_incident(incident_id, username)
    return _a3_platform_incident_redirect(
        incident_id,
        result,
        form.get("status") or "active",
        form.get("assignee") or "all",
        form.get("search") or "",
        success_notice="acknowledged",
    )


@router.post("/platform/a3-health/incidents/{incident_id}/assign")
async def assign_platform_a3_incident(
    request: Request,
    incident_id: int,
):
    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    if get_role(username) != "superadmin":
        return RedirectResponse("/", status_code=302)

    form = await request.form()
    result = assign_a3_platform_incident(
        incident_id,
        username,
        form.get("assigned_to") or "",
    )
    return _a3_platform_incident_redirect(
        incident_id,
        result,
        form.get("status") or "active",
        form.get("assignee") or "all",
        form.get("search") or "",
        success_notice="assigned",
    )


@router.post("/platform/a3-health/incidents/{incident_id}/note")
async def note_platform_a3_incident(
    request: Request,
    incident_id: int,
):
    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    if get_role(username) != "superadmin":
        return RedirectResponse("/", status_code=302)

    form = await request.form()
    result = add_a3_platform_incident_note(
        incident_id,
        username,
        form.get("note") or "",
    )
    return _a3_platform_incident_redirect(
        incident_id,
        result,
        form.get("status") or "active",
        form.get("assignee") or "all",
        form.get("search") or "",
        success_notice="note_added",
    )


@router.get("/platform/a3-health/export")
async def platform_a3_health_export(
    request: Request,
    status: str = "all",
    search: str = "",
):
    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    if get_role(username) != "superadmin":
        return RedirectResponse("/", status_code=302)

    health = get_a3_platform_health(
        status_filter=status,
        search=search,
    )
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "ID компании",
        "Компания",
        "Владелец",
        "Общее состояние",
        "Основной запуск",
        "Последний основной запуск",
        "Контрольная проверка",
        "Последняя контрольная проверка",
        "Уведомление создано",
        "Telegram отправлен",
        "Рекомендация",
    ])

    for item in health["items"]:
        writer.writerow([
            item["company_id"],
            item["company_name"],
            item["owner_username"],
            item["status_label"],
            item["main_status_label"],
            item["latest_scheduler_age_label"],
            item["watchdog_status_label"],
            item["watchdog_checked_age_label"],
            "Да" if item["notification_created"] else "Нет",
            "Да" if item["telegram_sent"] else "Нет",
            item["recommendation"],
        ])

    filename = f"a3_platform_health_{health['status_filter']}.csv"
    return Response(
        content="\ufeff" + output.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f"attachment; filename={filename}",
        },
    )


@router.get("/platform/calendar-health", response_class=HTMLResponse)
async def platform_calendar_health_page(
    request: Request,
    status: str = "all",
    assignee: str = "all",
    notice: str = "",
    error: str = "",
    claimed: int = 0,
    skipped: int = 0,
    reassigned: int = 0,
):
    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role != "superadmin":
        return RedirectResponse("/", status_code=302)

    health = get_platform_calendar_health(
        status_filter=status,
        assignee_filter=assignee,
        current_username=username,
    )
    page_messages = {
        "acknowledged": (
            "Инцидент принят в работу и назначен вам.",
            "success",
        ),
        "incident_not_found": (
            "Активный инцидент уже закрыт или не найден.",
            "error",
        ),
        "already_acknowledged": (
            "Инцидент уже принял другой администратор.",
            "error",
        ),
        "company_not_found": (
            "Компания не найдена.",
            "error",
        ),
        "bulk_empty": (
            "Видимых непринятых инцидентов нет.",
            "success",
        ),
        "bulk_conflict": (
            "Инциденты уже изменились. Обновите очередь.",
            "error",
        ),
        "bulk_reassign_empty": (
            "Видимых принятых инцидентов для передачи нет.",
            "success",
        ),
        "bulk_reassign_conflict": (
            "Инциденты уже изменились или ответственный недоступен.",
            "error",
        ),
    }
    page_message = page_messages.get(notice or error)

    if notice == "bulk_acknowledged":
        page_message = (
            (
                f"Принято инцидентов: {max(0, int(claimed or 0))}."
                + (
                    f" Пропущено: {max(0, int(skipped or 0))}."
                    if skipped
                    else ""
                )
            ),
            "success",
        )
    elif notice == "bulk_reassigned":
        page_message = (
            (
                f"Передано инцидентов: {max(0, int(reassigned or 0))}."
                + (
                    f" Пропущено: {max(0, int(skipped or 0))}."
                    if skipped
                    else ""
                )
            ),
            "success",
        )
    visible_claimable_count = sum(
        1 for item in health["items"] if item["requires_response"]
    )
    visible_reassignable_count = sum(
        1
        for item in health["items"]
        if item["active_incident"] and item["is_acknowledged"]
    )
    reassign_admins = [
        admin_username
        for admin_username in health["platform_admins"]
        if admin_username != username
    ]
    links = build_platform_calendar_health_links(
        health["status_filter"],
        health["assignee_filter"],
    )
    status_filter_options = [
        {
            "key": "all",
            "label": "Все",
            "url": build_platform_calendar_health_filter_url(
                "all",
                health["assignee_filter"],
            ),
        },
        {
            "key": "critical",
            "label": f"Критические · {health['summary']['critical']}",
            "url": build_platform_calendar_health_filter_url(
                "critical",
                health["assignee_filter"],
            ),
        },
        {
            "key": "unacknowledged",
            "label": f"Не приняты · {health['summary']['unacknowledged']}",
            "url": build_platform_calendar_health_filter_url(
                "unacknowledged",
                health["assignee_filter"],
            ),
        },
        {
            "key": "response_overdue",
            "label": f"Реакция · {health['summary']['response_overdue']}",
            "url": build_platform_calendar_health_filter_url(
                "response_overdue",
                health["assignee_filter"],
            ),
        },
        {
            "key": "recovery_overdue",
            "label": (
                f"Восстановление · "
                f"{health['summary']['recovery_overdue']}"
            ),
            "url": build_platform_calendar_health_filter_url(
                "recovery_overdue",
                health["assignee_filter"],
            ),
        },
        {
            "key": "problem",
            "label": f"Проблемы · {health['summary']['problems']}",
            "url": build_platform_calendar_health_filter_url(
                "problem",
                health["assignee_filter"],
            ),
        },
        {
            "key": "healthy",
            "label": f"Работают · {health['summary']['healthy']}",
            "url": build_platform_calendar_health_filter_url(
                "healthy",
                health["assignee_filter"],
            ),
        },
        {
            "key": "waiting",
            "label": f"Ожидают · {health['summary']['waiting']}",
            "url": build_platform_calendar_health_filter_url(
                "waiting",
                health["assignee_filter"],
            ),
        },
        {
            "key": "disabled",
            "label": f"Выключены · {health['summary']['disabled']}",
            "url": build_platform_calendar_health_filter_url(
                "disabled",
                health["assignee_filter"],
            ),
        },
    ]

    return templates.TemplateResponse(
        request,
        "platform_calendar_health.html",
        {
            "request": request,
            "username": username,
            "role": role,
            "health": health,
            "summary": health["summary"],
            "companies": health["items"],
            "selected_status": health["status_filter"],
            "selected_assignee": health["assignee_filter"],
            "platform_admins": health["platform_admins"],
            "admin_workload": health["admin_workload"],
            "visible_claimable_count": visible_claimable_count,
            "visible_reassignable_count": visible_reassignable_count,
            "reassign_admins": reassign_admins,
            "bulk_claim_limit": 25,
            "links": links,
            "status_filter_options": status_filter_options,
            "page_message": (
                page_message[0] if page_message else ""
            ),
            "page_message_tone": (
                page_message[1] if page_message else ""
            ),
        },
    )


@router.post("/platform/calendar-health/claim-visible")
async def platform_calendar_claim_visible_incidents(
    request: Request,
    status: str = "unacknowledged",
    assignee: str = "unassigned",
):
    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    if get_role(username) != "superadmin":
        return RedirectResponse("/", status_code=302)

    result = claim_visible_calendar_scheduler_incidents(
        username,
        status_filter=status,
        assignee_filter=assignee,
    )

    if result["claimed_count"]:
        return RedirectResponse(
            build_platform_calendar_health_queue_url(
                status=result["status_filter"],
                assignee=result["assignee_filter"],
                notice="bulk_acknowledged",
                claimed=result["claimed_count"],
                skipped=result["skipped_count"],
            ),
            status_code=302,
        )

    error_code = (
        "bulk_conflict"
        if result["visible_count"]
        else "bulk_empty"
    )
    return RedirectResponse(
        build_platform_calendar_health_queue_url(
            status=result.get("status_filter") or status,
            assignee=result.get("assignee_filter") or assignee,
            error=error_code if error_code == "bulk_conflict" else "",
            notice=error_code if error_code == "bulk_empty" else "",
        ),
        status_code=302,
    )


@router.post("/platform/calendar-health/reassign-visible")
async def platform_calendar_reassign_visible_incidents(
    request: Request,
    status: str = "all",
    assignee: str = "all",
):
    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    if get_role(username) != "superadmin":
        return RedirectResponse("/", status_code=302)

    form = await request.form()
    result = reassign_visible_calendar_scheduler_incidents(
        username,
        form.get("assignee_username"),
        status_filter=status,
        assignee_filter=assignee,
    )

    if result["reassigned_count"]:
        return RedirectResponse(
            build_platform_calendar_health_queue_url(
                status=result["status_filter"],
                assignee=result["assignee_filter"],
                notice="bulk_reassigned",
                reassigned=result["reassigned_count"],
                skipped=result["skipped_count"],
            ),
            status_code=302,
        )

    error_code = (
        "bulk_reassign_conflict"
        if result["visible_count"]
        else "bulk_reassign_empty"
    )
    return RedirectResponse(
        build_platform_calendar_health_queue_url(
            status=result.get("status_filter") or status,
            assignee=result.get("assignee_filter") or assignee,
            error=(
                error_code
                if error_code == "bulk_reassign_conflict"
                else ""
            ),
            notice=(
                error_code
                if error_code == "bulk_reassign_empty"
                else ""
            ),
        ),
        status_code=302,
    )


@router.get("/platform/calendar-health/export")
async def platform_calendar_health_export(
    request: Request,
    status: str = "all",
    assignee: str = "all",
):
    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    if get_role(username) != "superadmin":
        return RedirectResponse("/", status_code=302)

    health = get_platform_calendar_health(
        status_filter=status,
        assignee_filter=assignee,
        current_username=username,
    )
    output = io.StringIO()
    writer = csv.writer(output)
    summary = health["summary"]
    status_filter_labels = {
        "all": "Все",
        "problem": "Проблемные",
        "critical": "Критические",
        "unacknowledged": "Не приняты",
        "response_overdue": "Реакция просрочена",
        "recovery_overdue": "Восстановление просрочено",
        "healthy": "Работают",
    }
    assignee_filter_labels = {
        "all": "Все",
        "me": "Назначено мне",
    }
    writer.writerow(["Сводка"])
    writer.writerow([
        "Фильтр состояния",
        status_filter_labels.get(health["status_filter"], health["status_filter"]),
    ])
    writer.writerow([
        "Фильтр ответственного",
        assignee_filter_labels.get(
            health["assignee_filter"],
            health["assignee_filter"],
        ),
    ])
    writer.writerow(["Общий статус", summary["overall_status_label"]])
    writer.writerow([
        "Старейший активный инцидент",
        summary["oldest_active_incident_label"],
    ])
    writer.writerow(["Компаний", summary["total_companies"]])
    writer.writerow(["Критические", summary["critical"]])
    writer.writerow(["Не приняты", summary["unacknowledged"]])
    writer.writerow(["Просрочена реакция", summary["response_overdue"]])
    writer.writerow(["Активные инциденты", summary["active_incidents"]])
    writer.writerow(["Просрочено восстановление", summary["recovery_overdue"]])
    writer.writerow([])
    writer.writerow(["Компании"])
    writer.writerow([
        "Номер компании",
        "Компания",
        "Владелец",
        "Приоритет",
        "Состояние",
        "Автоматизация включена",
        "Автопубликация",
        "Автонаповещения",
        "Последняя активность",
        "Последний результат",
        "Причина последнего результата",
        "Тип инцидента",
        "Сообщение инцидента",
        "Возраст инцидента",
        "Реакция просрочена",
        "Восстановление просрочено",
        "Передано платформе",
        "Принят в работу",
        "Ответственный",
        "В работе",
        "SLA срок",
        "Следующее действие",
        "Подсказка действия",
        "Ссылка",
    ])

    for item in health["items"]:
        writer.writerow([
            item["company_id"],
            item["company_name"],
            item["owner_username"],
            item["priority_label"],
            item["status_label"],
            "да" if item["automation_enabled"] else "нет",
            "да" if item["calendar_auto_publish"] else "нет",
            "да" if item["calendar_auto_remind"] else "нет",
            item["last_activity_at"] or "",
            item["last_scheduler_run_status_label"] or "",
            item["last_scheduler_run_reason"] or "",
            item["incident_label"] if item["active_incident"] else "",
            item["incident_message"] or "",
            item["incident_age_label"] or "",
            "да" if item["response_overdue"] else "нет",
            "да" if item["recovery_overdue"] else "нет",
            "да" if item["is_escalated"] else "нет",
            "да" if item["is_acknowledged"] else "нет",
            item["assignee_username"] or "",
            item["recovery_age_label"] or "",
            item["sla_deadline_label"] or "",
            item["next_action_label"],
            item["next_action_hint"],
            item["detail_url"],
        ])

    filename = (
        "platform_calendar_health_"
        f"{health['status_filter']}_{health['assignee_filter']}.csv"
    )
    return Response(
        "\ufeff" + output.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": (
                f"attachment; filename={filename}"
            ),
        },
    )


@router.get(
    "/platform/calendar-health/analytics",
    response_class=HTMLResponse,
)
async def platform_calendar_incident_analytics_page(
    request: Request,
    days: int = 30,
):
    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    if get_role(username) != "superadmin":
        return RedirectResponse("/", status_code=302)

    analytics = get_platform_calendar_incident_analytics(
        days=days,
    )
    links = build_platform_calendar_incident_analytics_links(
        analytics["days"],
    )
    period_filter_options = [
        {
            "days": option_days,
            "label": f"{option_days} дней",
            "url": (
                "/platform/calendar-health/analytics?"
                + urlencode({"days": option_days})
            ),
        }
        for option_days in (7, 30, 90)
    ]

    return templates.TemplateResponse(
        request,
        "platform_calendar_incident_analytics.html",
        {
            "request": request,
            "username": username,
            "role": "superadmin",
            "analytics": analytics,
            "summary": analytics["summary"],
            "companies": analytics["companies"],
            "types": analytics["types"],
            "daily": analytics["daily"],
            "recent_sessions": analytics["recent_sessions"],
            "recommendations": analytics["recommendations"],
            "selected_days": analytics["days"],
            "links": links,
            "period_filter_options": period_filter_options,
        },
    )


@router.get("/platform/calendar-health/analytics/export")
async def platform_calendar_incident_analytics_export(
    request: Request,
    days: int = 30,
):
    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    if get_role(username) != "superadmin":
        return RedirectResponse("/", status_code=302)

    analytics = get_platform_calendar_incident_analytics(days=days)
    output = io.StringIO()
    writer = csv.writer(output)
    summary = analytics["summary"]

    writer.writerow(["Сводка"])
    writer.writerow(["Период", analytics["date_from"], analytics["date_to"]])
    writer.writerow(["Инцидентов", summary["incidents"]])
    writer.writerow(["Восстановлено", summary["recovered"]])
    writer.writerow(["Активных", summary["active"]])
    writer.writerow(["Компаний высокого риска", summary["high_risk_companies"]])
    writer.writerow(["Компаний среднего риска", summary["medium_risk_companies"]])
    writer.writerow(["Топ риск компания", summary["top_risk_company_name"]])
    writer.writerow(["Топ риск оценка", summary["top_risk_company_score"]])
    writer.writerow(["Дней высокого риска", summary["high_risk_days"]])
    writer.writerow(["Дней среднего риска", summary["medium_risk_days"]])
    writer.writerow(["Топ риск день", summary["top_risk_day"]])
    writer.writerow(["Топ риск день оценка", summary["top_risk_day_score"]])
    writer.writerow(["Закрыто %", summary["recovery_rate"]])
    writer.writerow(["SLA реакции %", summary["response_sla_percent"]])
    writer.writerow([
        "SLA восстановления %",
        summary["recovery_sla_percent"],
    ])
    writer.writerow([
        "Средняя реакция",
        summary["average_response_label"],
    ])
    writer.writerow([
        "Среднее восстановление",
        summary["average_recovery_label"],
    ])
    writer.writerow(["Попыток восстановления", summary["recovery_attempts"]])
    writer.writerow(["Ошибок восстановления", summary["recovery_failures"]])
    writer.writerow(["Просрочена реакция", summary["response_overdue"]])
    writer.writerow([
        "Просрочено восстановление",
        summary["recovery_overdue"],
    ])
    writer.writerow(["Эскалаций", summary["escalations"]])
    writer.writerow([])

    writer.writerow(["Рекомендации"])
    writer.writerow(["Заголовок", "Описание", "Ссылка"])
    for recommendation in analytics["recommendations"]:
        writer.writerow([
            recommendation["title"],
            recommendation["description"],
            recommendation["url"],
        ])
    writer.writerow([])

    writer.writerow(["Компании"])
    writer.writerow([
        "Номер компании",
        "Компания",
        "Риск",
        "Оценка риска",
        "Главный фактор",
        "Динамика риска",
        "Инциденты",
        "Восстановлено",
        "Активные",
        "Эскалации",
        "Просрочена реакция",
        "Реакция %",
        "Просрочено восстановление",
        "Средняя реакция",
        "Среднее восстановление",
        "Ссылка",
    ])
    for company in analytics["companies"]:
        writer.writerow([
            company["company_id"],
            company["company_name"],
            company["risk_label"],
            company["risk_score"],
            company["risk_main_factor"],
            company["risk_trend_label"],
            company["incidents"],
            company["recovered"],
            company["active"],
            company["escalations"],
            company["response_overdue"],
            company["response_overdue_percent"],
            company["recovery_overdue"],
            company["average_response_label"],
            company["average_recovery_label"],
            company["detail_url"],
        ])
    writer.writerow([])

    writer.writerow(["Причины"])
    writer.writerow([
        "Тип",
        "Инциденты",
        "Восстановлено",
        "Активные",
        "Просрочена реакция",
    ])
    for incident_type in analytics["types"]:
        writer.writerow([
            incident_type["label"],
            incident_type["incidents"],
            incident_type["recovered"],
            incident_type["active"],
            incident_type["response_overdue"],
        ])
    writer.writerow([])

    writer.writerow(["Динамика"])
    writer.writerow([
        "Дата",
        "Инциденты",
        "Восстановлено",
        "Активные",
        "Просрочена реакция",
        "Оценка риска",
    ])
    for day in analytics["daily"]:
        writer.writerow([
            day["date"],
            day["incidents"],
            day["recovered"],
            day["active"],
            day["response_overdue"],
            day["risk_score"],
        ])
    writer.writerow([])

    writer.writerow(["Последние инциденты"])
    writer.writerow([
        "Компания",
        "Тип",
        "Открыт",
        "Реакция",
        "Восстановление",
        "Состояние",
        "Реакция просрочена",
        "Эскалации",
    ])
    for incident in analytics["recent_sessions"]:
        writer.writerow([
            incident["company_name"],
            incident["incident_type_label"],
            incident["opened_at_value"],
            incident["response_label"],
            (
                incident["recovery_work_label"]
                if incident["is_active"] and incident["acknowledged_at"]
                else incident["recovery_label"]
            ),
            incident["status_label"],
            "да" if incident["response_overdue"] else "нет",
            incident["escalations"],
        ])

    return Response(
        "\ufeff" + output.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": (
                "attachment; filename="
                f"platform_calendar_incidents_{analytics['days']}d.csv"
            ),
        },
    )


@router.get("/platform/calendar-health/{company_id}/export")
async def platform_calendar_company_health_export(
    request: Request,
    company_id: int,
):
    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    if get_role(username) != "superadmin":
        return RedirectResponse("/", status_code=302)

    detail = get_platform_calendar_company_detail(company_id)

    if not detail:
        return RedirectResponse(
            "/platform/calendar-health?error=company_not_found",
            status_code=302,
        )

    company = detail["company"]
    output = io.StringIO()
    writer = csv.writer(output)

    writer.writerow(["Сводка"])
    writer.writerow(["Номер компании", company["company_id"]])
    writer.writerow(["Компания", company["company_name"]])
    writer.writerow(["Владелец", company["owner_username"]])
    writer.writerow(["Состояние", company["status_label"]])
    writer.writerow(["Приоритет", company["priority_label"]])
    writer.writerow(["Риск 30 дней", company["risk_label"]])
    writer.writerow(["Оценка риска", company["risk_score"]])
    writer.writerow(["Следующее действие риска", company["risk_next_action"]])
    writer.writerow(["Главный фактор риска", company["risk_main_factor"]])
    writer.writerow(["Динамика риска", company["risk_trend_label"]])
    writer.writerow(["Краткое резюме риска", company["risk_summary"]])
    writer.writerow([
        "Инцидентов за 30 дней",
        company["risk_incidents"],
    ])
    writer.writerow([
        "Просрочена реакция за 30 дней",
        company["risk_response_overdue"],
    ])
    writer.writerow([
        "Реакция просрочена %",
        company["risk_response_overdue_percent"],
    ])
    writer.writerow([
        "Автоматизация включена",
        "да" if company["automation_enabled"] else "нет",
    ])
    writer.writerow([
        "Автопубликация",
        "да" if company["calendar_auto_publish"] else "нет",
    ])
    writer.writerow([
        "Автонаповещения",
        "да" if company["calendar_auto_remind"] else "нет",
    ])
    writer.writerow(["Активный инцидент", company["incident_label"]])
    writer.writerow(["Сообщение инцидента", company["incident_message"] or ""])
    writer.writerow(["Возраст инцидента", company["incident_age_label"] or ""])
    writer.writerow([
        "Принят в работу",
        "да" if company["is_acknowledged"] else "нет",
    ])
    writer.writerow(["Ответственный", company["assignee_username"] or ""])
    writer.writerow([
        "Реакция просрочена",
        "да" if company["response_overdue"] else "нет",
    ])
    writer.writerow([
        "Восстановление просрочено",
        "да" if company["recovery_overdue"] else "нет",
    ])
    writer.writerow(["SLA срок", company["sla_deadline_label"] or ""])
    writer.writerow(["Следующее действие", company["next_action_label"]])
    writer.writerow(["Подсказка действия", company["next_action_hint"]])
    writer.writerow([])

    writer.writerow(["Последние запуски"])
    writer.writerow([
        "Состояние",
        "Источник",
        "Начало",
        "Завершение",
        "Период с",
        "Период по",
        "Изменено дней",
        "Уведомлений",
        "Причина",
    ])
    for run in detail["runs"]:
        writer.writerow([
            run["status_label"],
            run["source_label"],
            run["started_at"] or "",
            run["completed_at"] or "",
            run["range_start"] or "",
            run["range_end"] or "",
            run["changed_days"] or 0,
            run["notifications_sent"] or 0,
            run["reason"] or "",
        ])
    writer.writerow([])

    writer.writerow(["История инцидентов"])
    writer.writerow(["Событие", "Тип", "Дата", "Участник", "Описание"])
    for incident in detail["incidents"]:
        writer.writerow([
            incident["event_type_label"],
            incident["incident_type_label"],
            incident["created_at"] or "",
            incident["actor_username"] or "система",
            incident["message"] or "",
        ])
    writer.writerow([])

    writer.writerow(["Операции с планами"])
    writer.writerow([
        "Операция",
        "Источник",
        "Период с",
        "Период по",
        "Исполнитель",
        "Изменено дней",
        "Уведомлений",
        "Пропущено дней",
    ])
    for operation in detail["operations"]:
        writer.writerow([
            operation["action_label"],
            operation["source_label"],
            operation["week_start"] or "",
            operation["week_end"] or "",
            operation["actor_username"] or "система",
            operation["changed_days"] or 0,
            operation["notifications_sent"] or 0,
            operation["skipped_days"] or 0,
        ])

    return Response(
        "\ufeff" + output.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": (
                "attachment; filename="
                f"platform_calendar_company_{company_id}.csv"
            ),
        },
    )


@router.get(
    "/platform/calendar-health/{company_id}",
    response_class=HTMLResponse,
)
async def platform_calendar_company_health_page(
    request: Request,
    company_id: int,
    notice: str = "",
    error: str = "",
):
    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role != "superadmin":
        return RedirectResponse("/", status_code=302)

    detail = get_platform_calendar_company_detail(company_id)

    if not detail:
        return RedirectResponse(
            "/platform/calendar-health?error=company_not_found",
            status_code=302,
        )

    page_messages = {
        "acknowledged": (
            "Инцидент принят в работу от имени платформы.",
            "success",
        ),
        "note_added": (
            "Рабочая заметка добавлена в журнал инцидента.",
            "success",
        ),
        "assigned": (
            "Ответственный за инцидент изменён.",
            "success",
        ),
        "recovered": (
            "Проверка выполнена успешно. Инцидент закрыт.",
            "success",
        ),
        "incident_not_found": (
            "Активный инцидент уже закрыт или не найден.",
            "error",
        ),
        "already_acknowledged": (
            "Инцидент уже принят в работу.",
            "error",
        ),
        "empty_note": (
            "Введите текст рабочей заметки.",
            "error",
        ),
        "note_too_long": (
            "Заметка не должна превышать 500 символов.",
            "error",
        ),
        "assignee_not_found": (
            "Ответственный не найден или отключён.",
            "error",
        ),
        "incident_not_acknowledged": (
            "Сначала примите инцидент в работу.",
            "error",
        ),
        "already_assigned": (
            "Этот администратор уже отвечает за инцидент.",
            "error",
        ),
        "incident_not_assignee": (
            "Запустить восстановление может только текущий ответственный.",
            "error",
        ),
        "recovery_note_required": (
            "Опишите результат диагностики перед восстановлением.",
            "error",
        ),
        "recovery_note_too_long": (
            "Комментарий к восстановлению не должен превышать 500 символов.",
            "error",
        ),
        "automation_disabled": (
            "Автоматизация календаря выключена у компании.",
            "error",
        ),
        "calendar_disabled": (
            "Модуль календаря выключен у компании.",
            "error",
        ),
        "scheduler_already_running": (
            "Планировщик уже выполняется. Повторите позже.",
            "error",
        ),
        "actor_not_found": (
            "У компании нет активного владельца или менеджера.",
            "error",
        ),
        "recovery_failed": (
            "Восстановление завершилось с ошибкой. Проверьте журнал.",
            "error",
        ),
    }
    message_key = notice or error
    page_message = page_messages.get(message_key)

    return templates.TemplateResponse(
        request,
        "platform_calendar_company_health.html",
        {
            "request": request,
            "username": username,
            "role": role,
            "detail": detail,
            "company": detail["company"],
            "summary": detail["summary"],
            "runs": detail["runs"],
            "incidents": detail["incidents"],
            "operations": detail["operations"],
            "platform_admins": detail["platform_admins"],
            "page_message": (
                page_message[0] if page_message else ""
            ),
            "page_message_tone": (
                page_message[1] if page_message else ""
            ),
        },
    )


@router.post(
    "/platform/calendar-health/{company_id}/acknowledge",
)
async def platform_calendar_incident_acknowledge(
    request: Request,
    company_id: int,
    return_to: str = "",
    status: str = "all",
    assignee: str = "all",
):
    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    if get_role(username) != "superadmin":
        return RedirectResponse("/", status_code=302)

    result = acknowledge_calendar_scheduler_incident(
        company_id,
        username,
    )
    query_key = "notice" if result["ok"] else "error"
    query_value = (
        "acknowledged" if result["ok"] else result["error"]
    )

    if return_to == "queue":
        return RedirectResponse(
            build_platform_calendar_health_queue_url(
                status=status,
                assignee=assignee,
                **{query_key: query_value},
            ),
            status_code=302,
        )

    return RedirectResponse(
        (
            f"/platform/calendar-health/{company_id}"
            f"?{query_key}={query_value}"
        ),
        status_code=302,
    )


@router.post(
    "/platform/calendar-health/{company_id}/note",
)
async def platform_calendar_incident_note(
    request: Request,
    company_id: int,
):
    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    if get_role(username) != "superadmin":
        return RedirectResponse("/", status_code=302)

    form = await request.form()
    result = add_calendar_scheduler_incident_note(
        company_id,
        username,
        form.get("message"),
    )
    query_key = "notice" if result["ok"] else "error"
    query_value = (
        "note_added" if result["ok"] else result["error"]
    )
    return RedirectResponse(
        (
            f"/platform/calendar-health/{company_id}"
            f"?{query_key}={query_value}"
        ),
        status_code=302,
    )


@router.post(
    "/platform/calendar-health/{company_id}/assign",
)
async def platform_calendar_incident_assign(
    request: Request,
    company_id: int,
):
    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    if get_role(username) != "superadmin":
        return RedirectResponse("/", status_code=302)

    form = await request.form()
    result = reassign_calendar_scheduler_incident(
        company_id,
        username,
        form.get("assignee_username"),
    )
    query_key = "notice" if result["ok"] else "error"
    query_value = "assigned" if result["ok"] else result["error"]
    return RedirectResponse(
        (
            f"/platform/calendar-health/{company_id}"
            f"?{query_key}={query_value}"
        ),
        status_code=302,
    )


@router.post(
    "/platform/calendar-health/{company_id}/recover",
)
async def platform_calendar_incident_recover(
    request: Request,
    company_id: int,
):
    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    if get_role(username) != "superadmin":
        return RedirectResponse("/", status_code=302)

    form = await request.form()
    recovery_note = str(
        form.get("recovery_note") or ""
    ).strip()
    conn = connect()
    c = conn.cursor()
    company = c.execute("""
    SELECT
        companies.id,
        scheduler.active_incident,
        scheduler.incident_acknowledged_at,
        scheduler.incident_acknowledged_by,
        scheduler.incident_assigned_to
    FROM companies
    LEFT JOIN calendar_plan_scheduler_status AS scheduler
      ON scheduler.company_id=companies.id
    WHERE companies.id=?
    """, (company_id,)).fetchone()
    conn.close()

    if not company or not str(company["active_incident"] or ""):
        return RedirectResponse(
            (
                f"/platform/calendar-health/{company_id}"
                "?error=incident_not_found"
            ),
            status_code=302,
        )

    if not company["incident_acknowledged_at"]:
        return RedirectResponse(
            (
                f"/platform/calendar-health/{company_id}"
                "?error=incident_not_acknowledged"
            ),
            status_code=302,
        )

    assigned_to = str(
        company["incident_assigned_to"]
        or company["incident_acknowledged_by"]
        or ""
    )

    if assigned_to != username:
        return RedirectResponse(
            (
                f"/platform/calendar-health/{company_id}"
                "?error=incident_not_assignee"
            ),
            status_code=302,
        )

    if not recovery_note:
        return RedirectResponse(
            (
                f"/platform/calendar-health/{company_id}"
                "?error=recovery_note_required"
            ),
            status_code=302,
        )

    if len(recovery_note) > 500:
        return RedirectResponse(
            (
                f"/platform/calendar-health/{company_id}"
                "?error=recovery_note_too_long"
            ),
            status_code=302,
        )

    log_calendar_scheduler_recovery_attempt(
        company_id,
        "recovery_started",
        username,
        (
            "Платформа запустила внеплановую проверку автоматизации. "
            f"Комментарий ответственного: {recovery_note}"
        ),
    )
    result = await run_calendar_plan_scheduler(
        company_id,
        source="manual_run",
    )

    if result["error"]:
        error_code = (
            result["error"]
            if result["error"] in {
                "automation_disabled",
                "calendar_disabled",
                "scheduler_already_running",
                "actor_not_found",
            }
            else "recovery_failed"
        )
        log_calendar_scheduler_recovery_attempt(
            company_id,
            "recovery_failed",
            username,
            (
                "Внеплановая проверка завершилась с ошибкой: "
                f"{result['error']}. "
                f"Комментарий ответственного: {recovery_note}"
            ),
        )
        return RedirectResponse(
            (
                f"/platform/calendar-health/{company_id}"
                f"?error={error_code}"
            ),
            status_code=302,
        )

    close_calendar_scheduler_incident(
        company_id,
        actor_username=username,
        recovery_message=(
            "Платформа выполнила внеплановую проверку. "
            "Автоматизация календаря работает штатно. "
            f"Итог диагностики: {recovery_note}"
        ),
    )
    return RedirectResponse(
        (
            f"/platform/calendar-health/{company_id}"
            "?notice=recovered"
        ),
        status_code=302,
    )


@router.get("/api/platform/backup-status")
async def api_platform_backup_status(request: Request):
    username = get_user(request)

    if not username:
        return JSONResponse({"error": "auth_required"}, status_code=401)

    role = get_role(username)

    if role != "superadmin":
        return JSONResponse({"error": "forbidden"}, status_code=403)

    return get_backup_status()


@router.get("/api/platform/background-jobs")
async def api_platform_background_jobs(request: Request):
    username = get_user(request)

    if not username:
        return JSONResponse({"error": "auth_required"}, status_code=401)
    if get_role(username) != "superadmin":
        return JSONResponse({"error": "forbidden"}, status_code=403)

    return {
        "summary": get_background_queue_status(),
        "items": get_recent_background_jobs(limit=50),
    }


@router.post("/api/platform/background-jobs/run")
async def api_platform_run_background_jobs(request: Request):
    username = get_user(request)

    if not username:
        return JSONResponse({"error": "auth_required"}, status_code=401)
    if get_role(username) != "superadmin":
        return JSONResponse({"error": "forbidden"}, status_code=403)

    summary = run_background_job_batch(
        worker_id=f"manual-{username}-{uuid4().hex[:10]}",
    )
    return {
        "ok": not summary["failed"] and not summary["stale_failed"],
        "summary": summary,
    }
