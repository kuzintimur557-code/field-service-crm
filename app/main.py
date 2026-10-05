from app.services.workflow_timeline import get_workflow_timeline
from app.services.automation_analytics import (
    get_automation_analytics,
    get_unhealthy_rules,
)
from app.services.autonomous_actions import (
    SKIPPED_EVENT_RETRY_COOLDOWN_MINUTES,
    approve_autonomous_action,
    approve_safe_autonomous_actions,
    enqueue_autonomous_action,
    get_autonomous_actions,
    get_autonomous_action_summary,
    process_autonomous_actions,
    reject_autonomous_action,
    reject_unsafe_autonomous_actions,
)
from app.services.a3_runner import run_a3_autonomous_cycle
from app.services.a3_cycle_history import (
    A3_CYCLE_HISTORY_EXPORT_LIMIT,
    A3_CYCLE_HISTORY_LIMIT,
    a3_cycle_status_filter_label,
    get_a3_cycle_history,
    get_a3_cycle_reliability,
    get_a3_cycle_summary,
    normalize_a3_cycle_status_filter,
    record_a3_cycle_run,
)
from app.services.a3_scheduler_readiness import get_a3_scheduler_readiness
from app.services.a3_scheduler_watchdog import (
    get_a3_scheduler_watchdog_report,
    get_a3_scheduler_watchdog_history,
    get_a3_scheduler_watchdog_status,
    get_a3_scheduler_watchdog_trend,
    record_a3_scheduler_watchdog_run,
    save_a3_scheduler_watchdog_status,
)
from app.services.a3_platform_health import (
    build_a3_platform_health_url,
    get_a3_platform_health,
)
from app.services.a3_platform_incidents import (
    acknowledge_a3_platform_incident,
    add_a3_platform_incident_note,
    assign_a3_platform_incident,
    build_a3_platform_incidents_url,
    escalate_overdue_a3_platform_incidents,
    get_a3_platform_incident_admins,
    get_a3_platform_incidents,
    sync_a3_platform_incidents,
)
from app.services.a3_platform_incident_analytics import (
    build_a3_incident_analytics_url,
    get_a3_platform_incident_analytics,
    normalize_a3_incident_analytics_company,
    normalize_a3_incident_analytics_period,
)
from app.services.a3_platform_incident_reviews import (
    build_a3_incident_reviews_url,
    get_a3_platform_incident_reviews,
    normalize_a3_incident_review_company,
    normalize_a3_incident_review_status,
    save_a3_platform_incident_review,
)
from app.services.a3_incident_followups import (
    build_a3_followups_url,
    create_a3_incident_followup,
    get_a3_incident_followups,
    normalize_a3_followup_company,
    normalize_a3_followup_filter,
    normalize_a3_followup_incident,
    normalize_a3_followup_owner,
    review_a3_incident_followup,
    update_a3_incident_followup,
)
from app.services.a3_incident_followup_monitor import (
    get_a3_followup_monitor_policy,
    get_a3_followup_monitor_overview,
    run_a3_incident_followup_monitor,
)
from app.services.a3_followup_analytics import (
    a3_followup_analytics_csv_rows,
    get_a3_followup_analytics,
)
from app.services.a3_followup_quality_monitor import (
    a3_followup_quality_alert_csv_rows,
    acknowledge_a3_followup_quality_alert,
    build_a3_followup_quality_alerts_url,
    get_a3_followup_quality_policy,
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
from app.services.decision_engine import get_decision_engine

from app.services.governance import (
    APPROVAL_HISTORY_LIMIT,
    action_label,
    ensure_governance_settings,
    get_governance_settings,
    save_governance_settings,
    get_approval_queue,
    get_approval_history,
    target_label,
)
from app.services.ops_timeline import (
    create_ops_timeline_event,
    get_ops_timeline,
)
from app.services.operations_insights import get_operations_insights
from app.services.predictive_signals import get_predictive_signals
from app.services.self_healing import (
    get_recovery_history,
    run_self_healing_cycle,
)
from app.services.system_health import (
    calculate_system_health,
    get_system_health_history,
)
from app.services.smart_scheduling import (
    add_time_slots_to_recommendations,
    build_scheduling_recommendations,
)
from app.services.schedule_conflicts import (
    build_conflict_recommendations,
    detect_schedule_conflicts,
)
from app.services.dispatch_board import build_dispatch_board
from app.services.dispatch_planner import build_dispatch_plan
from app.services.day_plan_publication import (
    REMINDER_COOLDOWN_MINUTES,
    build_day_plan_snapshot,
    build_day_publication_state,
    build_week_publication_summary,
)
from app.services.daily_schedule import (
    SLOT_STEP,
    WORKDAY_END,
    WORKDAY_START,
    build_day_readiness,
    build_daily_auto_plan,
    build_daily_conflict_repair_plan,
    build_daily_schedule,
    format_time_value,
    find_time_conflicts,
    list_common_time_slots,
    normalize_time_window,
    parse_time_value,
    task_duration_minutes,
)
from app.services.workflow_graph import (
    get_company_workflow_graphs,
    get_rule_workflow_debug,
    get_rule_workflow_graph,
)
from fastapi import FastAPI, Request, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse, FileResponse, Response, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app.database import (
    begin_locked_transaction,
    connect,
    get_database_error_types,
    get_database_runtime_config,
    init_db,
)
from app.deps import (
    COOKIE_SECURE,
    SESSION_CLOCK_SKEW_SECONDS,
    SESSION_COOKIE_MAX_AGE_SECONDS,
    SESSION_COOKIE_NAME,
    SECRET_KEY,
    clear_failed_logins,
    get_request_ip,
    get_role,
    get_user,
    get_user_company_id,
    get_user_session_version,
    is_login_blocked,
    is_superadmin,
    log_login_event,
    missing_company_context_response,
    register_failed_login,
    require_route_company_context,
    sign_session_value,
    update_last_seen,
    verify_session_value,
)
from app.uploads import (
    ALLOWED_CALL_AUDIO_EXTENSIONS,
    PDF_IMAGE_EXTENSIONS,
    ALLOWED_CLIENT_FILE_EXTENSIONS,
    ALLOWED_IMAGE_EXTENSIONS,
    CALL_AUDIO_UPLOAD_MAX_BYTES,
    CLIENT_FILE_UPLOAD_MAX_BYTES,
    CLIENT_FILES_DIR,
    DOCS_DIR,
    IMAGE_CONTENT_TYPES,
    IMAGE_UPLOAD_MAX_BYTES,
    UPLOAD_DIR,
    UploadValidationError,
    get_upload_size,
    safe_call_audio_filename,
    safe_client_file_filename,
    safe_upload_filename,
    save_upload_file,
    storage_file_response,
    validate_upload_file,
)
from app.services.common import (
    BUSINESS_PRESETS,
    HTTP_OBSERVABILITY_IGNORED_PATH_PREFIXES,
    HTTP_SLOW_REQUEST_THRESHOLD_MS,
    SYSTEM_EVENT_ALERT_HOURS,
    SYSTEM_EVENT_RETENTION_DAYS,
    SYSTEM_EVENT_RETENTION_KEEP,
    build_error_links,
    cleanup_system_events,
    format_backup_age,
    format_file_size,
    get_recent_system_event_summary,
    log_http_request_event,
    log_system_event,
    request_prefers_json,
    should_log_http_request,
    normalize_system_event_severity,
    system_event_severity_label,
    get_system_event_cleanup_candidates,
    CORE_FEATURES,
    FEATURE_DEFINITIONS,
    INDUSTRY_OPTIONS,
    TEAM_ACTIVITY_FILTERS,
    build_dashboard_links,
    can_access_task,
    create_call_follow_up_notification,
    create_notification,
    ensure_company_features,
    format_task_workers,
    get_company_features,
    get_company_settings,
    get_industry_label,
    get_next_recurring_date,
    get_workers_for_company,
    get_overdue_days,
    get_role_title,
    get_task_company_id,
    get_task_worker_chat_ids,
    get_task_worker_names,
    has_feature,
    log_task_activity,
    require_company_id_value,
    require_feature,
    role_label,
    task_has_worker,
    ui_text,
    worker_task_condition,
    worker_task_params,
)
from app.services.plans import (
    PLAN_DEFINITIONS,
    format_rub_amount,
    get_company_user_limit_usage,
    get_plan_feature_flags,
    get_plan_label,
    get_plan_monthly_price,
    get_plan_options,
    get_plan_price_label,
    get_plan_user_limit,
    get_recommended_user_limit_plan,
    get_user_limit_status,
    normalize_plan,
    plan_allows_active_users,
)
from app.services.billing import (
    BILLING_INVOICE_STATUSES,
    build_billing_invoice_number,
    build_billing_invoice_rows,
    build_billing_invoice_summary,
    build_billing_invoices_export_url,
    build_platform_billing_invoice_activity_summary,
    build_platform_billing_invoice_links,
    build_platform_billing_links,
    build_platform_billing_monthly_summary,
    build_platform_billing_risk_summary,
    build_platform_billing_url,
    build_billing_next_payment_summary,
    create_platform_billing_reminders,
    fetch_billing_invoice,
    fetch_billing_invoices,
    fetch_billing_plan_history,
    fetch_platform_billing_invoice,
    fetch_platform_billing_invoice_activity,
    fetch_platform_billing_invoices,
    generate_company_billing_invoice,
    get_billing_invoice_status_meta,
    get_billing_invoice_status_options,
    get_billing_period_due_date,
    get_platform_billing_company_options,
    get_platform_billing_invoice_summary,
    get_platform_billing_reminder_payload,
    normalize_billing_invoice_filter,
    normalize_billing_invoice_status,
    normalize_billing_period,
    normalize_platform_billing_company_id,
    notify_platform_billing_status_change,
    parse_billing_due_date,
    record_platform_billing_activity,
    sync_platform_billing_overdue_invoices,
)
from app.routes.inbox import (
    router as inbox_router,
    inbox_page,
    inbox_detail_page,
    inbox_confirm,
    inbox_reject,
    receive_inbox_email,
)
from app.routes.master import (
    router as master_router,
    master_today_page,
    master_voice_page,
    master_voice_preview,
    master_voice_confirm,
    master_voice_search,
    master_voice_remind,
    master_voice_command,
    onboarding_page,
)
from app.routes.calls import (
    router as calls_router,
    calls_page,
    calls_export,
    call_detail,
    upload_call_audio,
    download_call_audio,
    update_call_analysis,
    complete_call_follow_up,
    create_call_record,
)
from app.routes.billing import (
    router as billing_router,
    billing_page,
    api_billing,
    billing_export,
    billing_invoices_page,
    api_billing_invoices,
    generate_billing_invoice,
    billing_invoices_export,
    billing_invoice_detail_export,
    api_billing_invoice_detail,
    billing_invoice_detail_page,
    run_subscription_reminders_cron,
)
from app.routes.cron import (
    router as cron_router,
    run_platform_billing_reminders_cron,
    run_ai_digest_scheduler_cron,
    run_calendar_plan_scheduler_cron,
    run_calendar_plan_scheduler_watchdog,
    run_background_jobs_cron,
    run_database_backup_cron,
    run_a3_autonomous_cron,
    run_a3_scheduler_watchdog_cron,
    run_a3_incident_action_monitor_cron,
)
from app.routes.notifications import (
    router as notifications_router,
    notifications_page,
    notifications_export,
    mark_all_notifications_read,
    delete_read_notifications,
    mark_notification_read,
    open_notification,
    build_notifications_redirect_url,
)
from app.routes.profile import (
    router as profile_router,
    profile_page,
    change_my_password,
)
from app.routes.auth import (
    router as auth_router,
    login_page,
    login,
    logout,
)
from app.routes.clients import (
    router as clients_router,
    clients_page,
    clients_export,
    client_detail,
    client_detail_export,
    add_client_call,
    add_client_note,
    upload_client_file,
    download_client_file,
    delete_client_file,
    edit_client,
    create_client,
)
from app.routes.tasks import (
    router as tasks_router,
    create_task_page,
    create_task,
    task_detail,
    add_task_item,
    add_manual_task_item,
    delete_task_item,
    apply_task_estimate_total,
    add_task_expense,
    delete_task_expense,
    update_task_discount,
    add_task_comment,
    update_payment_status,
    complete_task,
    start_task,
    edit_task_field,
    update_task_workers,
    update_task_custom_field,
    update_task_deadline,
    update_task_date,
    update_task_status,
    update_before_photo,
    update_report,
    archive_task,
    unarchive_task,
    delete_task,
    task_invoice_pdf,
    task_pdf,
)
from app.routes.platform import (
    router as platform_router,
    create_platform_company,
    update_platform_company_settings,
    apply_platform_company_preset,
    platform_companies_export,
    platform_company_export,
    generate_platform_company_billing_invoice,
    platform_company_detail_page,
    api_platform_company_detail,
    api_platform_companies,
    platform_companies_page,
    platform_modules_page,
    api_platform_modules,
    api_platform_module_detail,
    platform_modules_export,
    platform_module_detail_page,
    platform_presets_page,
    api_platform_presets,
    api_platform_preset_detail,
    platform_presets_export,
    platform_preset_detail_page,
    get_system_event_history,
    get_system_event_retention_status,
    get_http_error_meta,
    api_platform_dashboard,
    platform_dashboard_export,
    platform_dashboard,
    platform_billing_page,
    generate_platform_billing_invoice,
    send_platform_billing_reminders,
    sync_platform_billing_overdue,
    api_platform_billing,
    api_platform_billing_invoice,
    update_platform_billing_invoice_status,
    platform_billing_invoice_export,
    platform_billing_invoice_detail_page,
    platform_billing_export,
    platform_readiness_page,
    platform_readiness_snapshot,
    platform_readiness_signoff,
    platform_readiness_export,
    platform_readiness_snapshot_page,
    platform_readiness_snapshot_export,
    api_platform_readiness,
    api_platform_readiness_post_launch_review,
    api_platform_readiness_control_center,
    api_platform_readiness_runbook,
    api_platform_readiness_timeline,
    api_platform_readiness_signoffs,
    api_platform_readiness_launch_plan,
    platform_a3_health_page,
    api_platform_a3_health_history,
    platform_a3_incidents_page,
    api_platform_a3_incidents,
    platform_a3_incident_analytics_page,
    api_platform_a3_incident_analytics,
    platform_a3_incident_analytics_export,
    platform_a3_incident_reviews_page,
    api_platform_a3_incident_reviews,
    update_platform_a3_incident_review,
    platform_a3_incident_reviews_export,
    platform_a3_incident_actions_page,
    api_platform_a3_incident_actions,
    api_platform_a3_incident_action_monitor,
    api_platform_a3_incident_action_quality_monitor,
    platform_a3_followup_quality_alerts_page,
    api_platform_a3_followup_quality_alerts,
    api_change_platform_a3_followup_quality_alert,
    platform_a3_followup_quality_alerts_export,
    create_platform_a3_incident_action,
    update_platform_a3_incident_action,
    verify_platform_a3_incident_action,
    api_verify_platform_a3_incident_action,
    run_platform_a3_incident_action_monitor,
    run_platform_a3_incident_action_quality_monitor,
    api_run_platform_a3_incident_action_quality_monitor,
    platform_a3_incident_actions_export,
    platform_a3_health_export,
    platform_calendar_health_page,
    platform_calendar_claim_visible_incidents,
    platform_calendar_reassign_visible_incidents,
    platform_calendar_health_export,
    platform_calendar_incident_analytics_page,
    platform_calendar_incident_analytics_export,
    platform_calendar_company_health_export,
    platform_calendar_company_health_page,
    platform_calendar_incident_acknowledge,
    platform_calendar_incident_note,
    platform_calendar_incident_assign,
    platform_calendar_incident_recover,
    api_platform_backup_status,
    api_platform_background_jobs,
    api_platform_run_background_jobs,
)
from app.routes.misc import (
    router as misc_router,
    uploaded_file,
    debug_page,
    favicon,
    integration_1c_page,
    more_page,
    clear_login_attempts_admin,
    admin_notes_page,
    build_debug_links,
)
from app.routes.ai import (
    router as ai_router,
    ai_insights_page,
    ai_assistant_page,
    ai_assistant_events_export,
    add_ai_assistant_note,
    complete_ai_assistant_note,
    postpone_ai_assistant_note,
    notify_ai_assistant_follow_ups,
    setup_ai_assistant_digest_rules,
    create_ai_insights_digest,
)
from app.routes.catalog import (
    router as catalog_router,
    recurring_jobs_page,
    create_recurring_job,
    generate_recurring_task,
    toggle_recurring_job,
    update_recurring_job_date,
    custom_fields_page,
    create_custom_field,
    update_custom_field_order,
    toggle_custom_field,
    catalog_page,
    create_catalog_item,
    toggle_catalog_item,
)
from app.routes.lists import (
    router as lists_router,
    my_tasks_page,
    today_page,
    overdue_page,
    create_overdue_reminders,
    sla_page,
    create_sla_reminders,
    create_sla_escalations,
    sla_analytics_page,
    sla_analytics_export,
    workload_page,
    owner_dashboard_page,
    owner_dashboard_export,
    reports_page,
    archive_page,
)
from app.routes.calendar import (
    router as calendar_router,
    calendar_page,
    calendar_dispatch_page,
    calendar_day_route_page,
    calendar_conflicts_page,
    resolve_calendar_conflict,
    calendar_automation_time_allowed,
    api_calendar_smart_schedule,
    api_calendar_conflicts,
    api_calendar_dispatch_week_plans,
    api_calendar_dispatch_automation_settings,
    api_calendar_dispatch_automation_run,
    api_calendar_dispatch_incident_acknowledge,
    api_calendar_day_publication,
    api_calendar_day_acknowledge,
    api_calendar_day_acknowledgements_remind,
    api_calendar_day_move_time,
    api_calendar_dispatch_plan,
    api_calendar_dispatch_plan_apply,
    api_calendar_dispatch_move,
    run_calendar_plan_scheduler,
)
from app.routes.finance import (
    router as finance_router,
    finance_export,
    finance_summary_export,
    finance_summary_page,
    finance_page,
    payroll_page,
    payroll_history_page,
    payroll_history_export,
    payroll_export,
    mark_payroll_paid,
    update_payroll_payout_note,
    mark_payroll_unpaid,
)
from app.routes.settings import (
    router as settings_router,
    settings_page,
    settings_history_page,
    settings_history_export,
    update_settings,
    normalize_settings_history_date,
    normalize_settings_history_filters,
    build_settings_history_export_url,
    fetch_company_settings_history,
    build_settings_history_summary,
)
from app.routes.workers import (
    router as workers_router,
    workers_page,
    workers_export,
    team_activity_page,
    team_activity_export,
    worker_detail,
    create_worker_unavailability,
    delete_worker_unavailability,
    create_worker,
    update_team_user_profile,
    change_team_user_password,
    update_worker_commission,
    toggle_team_user_active,
    delete_team_user,
)
from app.postgresql_backup import (
    create_postgresql_backup,
    inspect_postgresql_database,
    run_postgresql_restore_drill,
    verify_postgresql_backup,
)
from app.object_storage import (
    ObjectStorageError,
    delete_storage_object,
    get_object_storage_runtime_config,
    get_object_storage_status,
    get_storage_object,
    read_storage_bytes,
    save_storage_fileobj,
    save_storage_path,
    s3_object_exists,
)
from app.services.background_jobs import (
    BackgroundJobExecutionError,
    enqueue_background_job,
    get_background_queue_status,
    get_recent_background_jobs,
    process_background_jobs,
)
from app.services.call_analysis import analyze_call_text
from app.services.subscriptions import (
    activate_company_subscription,
    get_company_subscription,
    get_company_subscription_fast,
    run_subscription_reminders,
)
from app.services.email_inbox import (
    EMAIL_STATUSES,
    MAX_RAW_LENGTH,
    extract_email_fields,
    find_or_create_inbox_client,
    get_company_service_names,
    get_email_message,
    get_email_messages,
    normalize_inbox_payload,
    parse_extracted_fields,
    parse_raw_email,
    save_email_message,
    set_email_message_status,
    suggest_inbox_slots,
)
from app.services.error_monitoring import (
    acknowledge_error_incident,
    get_error_incidents,
    get_error_monitoring_overview,
    normalize_error_path,
    record_error_incident,
    resolve_error_incident,
)
from app.security import (
    get_cross_site_request_error,
    get_request_size_error,
    get_security_runtime_config,
    require_valid_production_security,
)
from app.telegram_utils import send_message, send_photo, send_message_to_chat

from datetime import datetime, timedelta
from pathlib import Path
from time import monotonic
from uuid import uuid4
from urllib.parse import quote, urlencode
from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

import shutil
import os
import hmac
import hashlib
import bcrypt
import sqlite3
import base64
import secrets
import csv
import io
import calendar
import json
import tempfile
import mimetypes
import ipaddress


APP_VERSION = "0.3.0"
BACKUP_RETENTION_DAYS = 30
BACKUP_RETENTION_KEEP = 3
BACKUP_REQUIRED_TABLES = ("users", "tasks", "clients")
REQUEST_ID_HEADER = "X-Request-ID"
RESPONSE_TIME_HEADER = "X-Response-Time-ms"
SECURITY_RUNTIME = require_valid_production_security(
    get_security_runtime_config(),
)

app = FastAPI(
    docs_url="/docs" if SECURITY_RUNTIME["docs_enabled"] else None,
    redoc_url="/redoc" if SECURITY_RUNTIME["docs_enabled"] else None,
    openapi_url=(
        "/openapi.json" if SECURITY_RUNTIME["docs_enabled"] else None
    ),
)
app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=SECURITY_RUNTIME["trusted_hosts"] or ["*"],
)

app.include_router(inbox_router)
app.include_router(master_router)
app.include_router(calls_router)
app.include_router(billing_router)
app.include_router(cron_router)
app.include_router(notifications_router)
app.include_router(profile_router)
app.include_router(auth_router)
app.include_router(clients_router)
app.include_router(tasks_router)
app.include_router(settings_router)
app.include_router(workers_router)
app.include_router(finance_router)
app.include_router(calendar_router)
app.include_router(lists_router)
app.include_router(catalog_router)
app.include_router(ai_router)
app.include_router(misc_router)
app.include_router(platform_router)

init_db()

os.makedirs("uploads/docs", exist_ok=True)

app.mount("/static", StaticFiles(directory="app/static"), name="static")

from app.templating import templates


def normalize_request_id(value=""):
    request_id = str(value or "").strip()
    allowed_extra_chars = {"-", "_", "."}

    if (
        8 <= len(request_id) <= 64
        and all(
            char.isalnum() or char in allowed_extra_chars
            for char in request_id
        )
    ):
        return request_id

    return uuid4().hex


def get_request_id(request=None):
    existing = ""

    try:
        existing = getattr(request.state, "request_id", "")
    except Exception:
        existing = ""

    if existing:
        return existing

    header_value = ""

    try:
        header_value = request.headers.get(REQUEST_ID_HEADER, "")
    except Exception:
        header_value = ""

    request_id = normalize_request_id(header_value)

    try:
        request.state.request_id = request_id
    except Exception:
        pass

    return request_id


def apply_request_id_header(response, request_id):
    if request_id:
        response.headers.setdefault(REQUEST_ID_HEADER, request_id)

    return response


def apply_response_time_header(response, duration_ms):
    response.headers.setdefault(RESPONSE_TIME_HEADER, str(max(0, duration_ms)))
    return response


def apply_security_headers(response):
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault(
        "Referrer-Policy",
        "strict-origin-when-cross-origin",
    )
    response.headers.setdefault(
        "Permissions-Policy",
        "camera=(), microphone=(), geolocation=()",
    )
    response.headers.setdefault(
        "Content-Security-Policy",
        "default-src 'self'; base-uri 'self'; object-src 'none'; "
        "frame-ancestors 'none'; form-action 'self'; "
        "script-src 'self' 'unsafe-inline'; "
        "style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data: blob:; media-src 'self' blob:; "
        "font-src 'self' data:; connect-src 'self'",
    )
    response.headers.setdefault("Cross-Origin-Opener-Policy", "same-origin")
    response.headers.setdefault("Cross-Origin-Resource-Policy", "same-origin")
    response.headers.setdefault("X-Permitted-Cross-Domain-Policies", "none")

    if COOKIE_SECURE:
        response.headers.setdefault(
            "Strict-Transport-Security",
            "max-age=31536000; includeSubDomains",
        )

    return response


def finalize_response_headers(response, request_id="", duration_ms=None):
    apply_security_headers(response)

    if duration_ms is not None:
        apply_response_time_header(response, duration_ms)

    apply_request_id_header(response, request_id)
    return response


@app.middleware("http")
async def security_headers_middleware(request: Request, call_next):
    request_id = get_request_id(request)
    started_at = monotonic()
    request_size_error = get_request_size_error(
        request.headers,
        SECURITY_RUNTIME["max_request_bytes"],
    )
    cross_site_error = get_cross_site_request_error(
        request.method,
        request.headers,
        SECURITY_RUNTIME["csrf_trusted_origins"],
    )
    if request_size_error or cross_site_error:
        error = request_size_error or cross_site_error
        status_code = (
            413
            if error == "request_too_large"
            else 400
            if error == "invalid_content_length"
            else 403
        )
        response = JSONResponse(
            {
                "ok": False,
                "error": error,
                "request_id": request_id,
            },
            status_code=status_code,
        )
        duration_ms = int((monotonic() - started_at) * 1000)
        finalize_response_headers(response, request_id, duration_ms)
        log_http_request_event(request, response, request_id, duration_ms)
        return response
    response = await call_next(request)
    duration_ms = int((monotonic() - started_at) * 1000)
    finalize_response_headers(response, request_id, duration_ms)
    if not request.url.path.startswith("/static/"):
        response.headers.setdefault("Cache-Control", "no-store")
    log_http_request_event(request, response, request_id, duration_ms)
    return response


SUBSCRIPTION_EXEMPT_PREFIXES = (
    "/login",
    "/logout",
    "/billing",
    "/static/",
    "/health",
    "/ready",
    "/api/inbox/",
    "/api/billing",
    "/automation/cron/",
)


@app.middleware("http")
async def subscription_access_middleware(request: Request, call_next):
    if request.method in ("GET", "HEAD", "OPTIONS"):
        return await call_next(request)

    path = request.url.path

    if any(path.startswith(prefix) for prefix in SUBSCRIPTION_EXEMPT_PREFIXES):
        return await call_next(request)

    username = get_user(request)

    if not username:
        return await call_next(request)

    role = get_role(username)

    if role == "superadmin":
        return await call_next(request)

    company_id = get_user_company_id(username)
    subscription = get_company_subscription_fast(company_id)

    if subscription["is_open"]:
        return await call_next(request)

    if path.startswith("/api/"):
        return JSONResponse(
            {"ok": False, "error": "subscription_closed"},
            status_code=403,
        )

    return RedirectResponse("/billing?subscription_closed=1", status_code=302)


templates.env.globals["role_label"] = role_label
templates.env.globals["ui_text"] = ui_text



def get_current_company_id(request=None):
    if request and hasattr(request, "session"):
        company_id = request.session.get("company_id")

        if company_id:
            try:
                return int(company_id)
            except (TypeError, ValueError):
                return None

    if request:
        username = get_user(request)

        if username:
            return get_user_company_id(username)

    return None

DATA_DIR = Path(os.getenv("DATA_DIR", "."))
AUTOMATION_TRIGGERS = [
    ("new_task", "Новая заявка"),
    ("task_status_changed", "Статус заявки изменён"),
    ("task_schedule_changed", "Расписание заявки изменено"),
    ("task_workers_changed", "Исполнители заявки изменены"),
    ("task_archived", "Заявка отправлена в архив"),
    ("task_restored", "Заявка восстановлена из архива"),
    ("task_details_changed", "Данные заявки изменены"),
    ("task_finance_changed", "Финансы заявки изменены"),
    ("task_photo_uploaded", "Фото заявки загружено"),
    ("task_report_updated", "Отчёт по заявке обновлён"),
    ("payroll_payout_paid", "Выплата сотруднику отмечена"),
    ("payroll_payout_unpaid", "Выплата сотруднику отменена"),
    ("payroll_payout_note_updated", "Комментарий выплаты обновлён"),
    ("recurring_task_generated", "Создана регулярная заявка"),
    ("recurring_job_created", "Шаблон регулярной работы создан"),
    ("recurring_job_toggled", "Статус шаблона регулярной работы изменён"),
    ("recurring_job_date_changed", "Дата шаблона регулярной работы изменена"),
    ("payment_status_changed", "Статус оплаты изменён"),
    ("task_comment_added", "Комментарий к заявке добавлен"),
    ("overdue_task", "Просрочена задача"),
    ("sla_overdue", "Просрочен SLA"),
    ("sla_deadline_changed", "Срок SLA изменён"),
    ("unpaid_task", "Нет оплаты"),
    ("worker_overload", "Перегрузка сотрудника"),
    ("new_client", "Новый клиент"),
    ("client_updated", "Клиент обновлён"),
    ("client_note_added", "Заметка клиента добавлена"),
    ("client_file_uploaded", "Файл клиента загружен"),
    ("client_file_deleted", "Файл клиента удалён"),
    ("client_custom_field_updated", "Значение поля клиента изменено"),
    ("call_follow_up_created", "Нужен контакт по звонку"),
    ("call_follow_up_completed", "Контакт по звонку закрыт"),
    ("catalog_item_created", "Позиция каталога создана"),
    ("catalog_item_toggled", "Позиция каталога включена или выключена"),
    ("custom_field_created", "Поле компании создано"),
    ("custom_field_ordered", "Порядок поля компании изменён"),
    ("custom_field_toggled", "Поле компании включено или выключено"),
    ("task_custom_field_updated", "Значение поля заявки изменено"),
    ("worker_created", "Сотрудник создан"),
    ("worker_status_changed", "Статус сотрудника изменён"),
    ("worker_unavailability_changed", "Недоступность сотрудника изменена"),
    ("worker_profile_updated", "Карточка сотрудника обновлена"),
    ("worker_commission_updated", "Процент сотрудника изменён"),
    ("worker_deleted", "Сотрудник удалён"),
    ("worker_password_changed", "Пароль сотрудника изменён"),
    ("profile_password_changed", "Пользователь сменил свой пароль"),
    ("company_settings_updated", "Настройки компании обновлены"),
    ("ai_note_created", "ИИ-заметка создана"),
    ("ai_note_postponed", "ИИ-заметка перенесена"),
    ("ai_note_done", "ИИ-заметка выполнена"),
    ("ai_follow_up_notifications_sent", "ИИ-контроль отправил уведомления"),
    ("ai_insights_digest_created", "ИИ-сводка создана вручную"),
    ("ai_digest_rules_created", "Правила ИИ-сводок настроены"),
    ("daily_digest", "Ежедневная ИИ-сводка"),
    ("weekly_digest", "Еженедельная ИИ-сводка")
]

AUTOMATION_TRIGGER_GROUPS = [
    ("Заявки", (
        "new_task",
        "task_status_changed",
        "task_schedule_changed",
        "task_workers_changed",
        "task_archived",
        "task_restored",
        "task_details_changed",
        "task_photo_uploaded",
        "task_report_updated",
        "task_comment_added",
        "recurring_task_generated",
        "recurring_job_created",
        "recurring_job_toggled",
        "recurring_job_date_changed",
        "overdue_task",
    )),
    ("Финансы", (
        "task_finance_changed",
        "payment_status_changed",
        "unpaid_task",
        "payroll_payout_paid",
        "payroll_payout_unpaid",
        "payroll_payout_note_updated",
    )),
    ("Клиенты", (
        "new_client",
        "client_updated",
        "client_note_added",
        "client_file_uploaded",
        "client_file_deleted",
        "client_custom_field_updated",
    )),
    ("Звонки", (
        "call_follow_up_created",
        "call_follow_up_completed",
    )),
    ("Каталог", (
        "catalog_item_created",
        "catalog_item_toggled",
    )),
    ("Поля компании", (
        "custom_field_created",
        "custom_field_ordered",
        "custom_field_toggled",
        "task_custom_field_updated",
    )),
    ("Команда", (
        "worker_created",
        "worker_status_changed",
        "worker_unavailability_changed",
        "worker_profile_updated",
        "worker_commission_updated",
        "worker_deleted",
        "worker_password_changed",
        "profile_password_changed",
    )),
    ("Компания", (
        "company_settings_updated",
    )),
    ("SLA и загрузка", (
        "sla_overdue",
        "sla_deadline_changed",
        "worker_overload",
    )),
    ("ИИ-помощник", (
        "ai_note_created",
        "ai_note_postponed",
        "ai_note_done",
        "ai_follow_up_notifications_sent",
    )),
    ("ИИ-сводки", (
        "ai_insights_digest_created",
        "ai_digest_rules_created",
        "daily_digest",
        "weekly_digest",
    )),
]


def get_automation_trigger_groups():
    trigger_labels = dict(AUTOMATION_TRIGGERS)
    grouped_keys = set()
    groups = []

    for group_label, group_keys in AUTOMATION_TRIGGER_GROUPS:
        group_items = [
            (key, trigger_labels[key])
            for key in group_keys
            if key in trigger_labels
        ]

        if group_items:
            grouped_keys.update(key for key, _ in group_items)
            groups.append((group_label, group_items))

    other_items = [
        (key, label)
        for key, label in AUTOMATION_TRIGGERS
        if key not in grouped_keys
    ]

    if other_items:
        groups.append(("Другое", other_items))

    return groups


AUTOMATION_ACTIONS = [
    ("notification", "Создать уведомление"),
    ("telegram_alert", "Telegram-уведомление"),
    ("ai_digest", "ИИ-сводка"),
    ("email", "Электронная почта"),
    ("create_task", "Создать задачу")
]

AUTOMATION_STATUS_LABELS = {
    "pending": "Ожидает",
    "done": "Выполнено",
    "skipped": "Пропущено",
    "failed": "Ошибка"
}




INDUSTRY_LABEL_PRESETS = {
    "field_service": {
        "task_label": "Заявка",
        "worker_label": "Исполнитель",
        "client_label": "Клиент",
        "service_label": "Услуга"
    },
    "beauty": {
        "task_label": "Запись",
        "worker_label": "Мастер",
        "client_label": "Клиент",
        "service_label": "Услуга"
    },
    "cleaning": {
        "task_label": "Заказ",
        "worker_label": "Клинер",
        "client_label": "Клиент",
        "service_label": "Уборка"
    },
    "repair": {
        "task_label": "Заказ",
        "worker_label": "Мастер",
        "client_label": "Клиент",
        "service_label": "Работа"
    },
    "auto_service": {
        "task_label": "Заказ-наряд",
        "worker_label": "Мастер",
        "client_label": "Клиент",
        "service_label": "Работа"
    },
    "logistics": {
        "task_label": "Рейс",
        "worker_label": "Водитель",
        "client_label": "Клиент",
        "service_label": "Перевозка"
    },
    "agency": {
        "task_label": "Проект",
        "worker_label": "Специалист",
        "client_label": "Клиент",
        "service_label": "Услуга"
    },
    "medical": {
        "task_label": "Приём",
        "worker_label": "Специалист",
        "client_label": "Пациент",
        "service_label": "Услуга"
    },
    "education": {
        "task_label": "Занятие",
        "worker_label": "Преподаватель",
        "client_label": "Ученик",
        "service_label": "Курс"
    },
    "restaurant": {
        "task_label": "Заказ",
        "worker_label": "Сотрудник",
        "client_label": "Гость",
        "service_label": "Блюдо"
    },
    "ecommerce": {
        "task_label": "Заказ",
        "worker_label": "Сотрудник",
        "client_label": "Покупатель",
        "service_label": "Товар"
    },
    "other": {
        "task_label": "Задача",
        "worker_label": "Сотрудник",
        "client_label": "Клиент",
        "service_label": "Услуга"
    },
    "custom": {
        "task_label": "Задача",
        "worker_label": "Сотрудник",
        "client_label": "Клиент",
        "service_label": "Услуга"
    }
}


def get_worker_unavailability(
    cursor,
    company_id,
    worker_names,
    date_from,
    date_to,
):
    worker_names = list(dict.fromkeys(
        str(name or "").strip()
        for name in worker_names
        if str(name or "").strip()
    ))

    if not worker_names:
        return {}, []

    placeholders = ",".join("?" for _ in worker_names)
    rows = cursor.execute(f"""
    SELECT
        worker_unavailability.*,
        users.username
    FROM worker_unavailability
    JOIN users ON users.id=worker_unavailability.worker_id
    WHERE worker_unavailability.company_id=?
      AND users.company_id=worker_unavailability.company_id
      AND users.username IN ({placeholders})
      AND worker_unavailability.date_from <= ?
      AND worker_unavailability.date_to >= ?
    ORDER BY
        worker_unavailability.date_from,
        worker_unavailability.id
    """, [
        company_id,
        *worker_names,
        str(date_to)[:10],
        str(date_from)[:10],
    ]).fetchall()
    dates_by_worker = {
        worker_name: set()
        for worker_name in worker_names
    }
    reasons_by_worker_date = {}

    try:
        requested_start = datetime.strptime(
            str(date_from)[:10],
            "%Y-%m-%d",
        ).date()
        requested_end = datetime.strptime(
            str(date_to)[:10],
            "%Y-%m-%d",
        ).date()
    except Exception:
        return dates_by_worker, reasons_by_worker_date

    for row in rows:
        try:
            period_start = datetime.strptime(
                row["date_from"],
                "%Y-%m-%d",
            ).date()
            period_end = datetime.strptime(
                row["date_to"],
                "%Y-%m-%d",
            ).date()
        except Exception:
            continue

        current_date = max(period_start, requested_start)
        period_end = min(period_end, requested_end)

        while current_date <= period_end:
            date_value = current_date.strftime("%Y-%m-%d")
            dates_by_worker.setdefault(row["username"], set()).add(date_value)
            reasons_by_worker_date[
                (row["username"], date_value)
            ] = row["reason"] or "Сотрудник недоступен"
            current_date += timedelta(days=1)

    return dates_by_worker, reasons_by_worker_date


def get_company_schedule_conflicts(
    company_id,
    date_from,
    date_to,
    recommendation_days=14,
):
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
    recommendation_end = (
        datetime.strptime(date_to, "%Y-%m-%d").date()
        + timedelta(days=recommendation_days)
    ).strftime("%Y-%m-%d")
    task_rows = c.execute("""
    SELECT *
    FROM tasks
    WHERE company_id=?
      AND archived=0
      AND status NOT IN ('Завершено', 'Отменено')
      AND task_date IS NOT NULL
      AND task_date != ''
      AND substr(task_date, 1, 10) BETWEEN ? AND ?
    ORDER BY task_date, id
    """, (company_id, date_from, date_to)).fetchall()
    assignment_rows = c.execute("""
    SELECT id, worker, workers, substr(task_date, 1, 10) AS work_date
    FROM tasks
    WHERE company_id=?
      AND archived=0
      AND status NOT IN ('Завершено', 'Отменено')
      AND task_date IS NOT NULL
      AND task_date != ''
      AND substr(task_date, 1, 10) BETWEEN ? AND ?
    ORDER BY task_date, id
    """, (company_id, date_from, recommendation_end)).fetchall()
    unavailable_dates, unavailable_reasons = get_worker_unavailability(
        c,
        company_id,
        worker_capacities.keys(),
        date_from,
        recommendation_end,
    )
    conflicts = detect_schedule_conflicts(
        tasks=task_rows,
        worker_capacities=worker_capacities,
        unavailable_dates=unavailable_dates,
        unavailable_reasons=unavailable_reasons,
    )

    for conflict in conflicts:
        assignments = [
            {
                "date": row["work_date"],
                "workers": get_task_worker_names(row),
            }
            for row in assignment_rows
            if row["id"] != conflict["task_id"]
        ]
        conflict["recommendations"] = build_conflict_recommendations(
            conflict=conflict,
            worker_capacities=worker_capacities,
            assignments=assignments,
            unavailable_dates=unavailable_dates,
            search_days=recommendation_days,
        )

    conn.close()
    summary = {
        "total": len(conflicts),
        "critical": sum(
            1 for conflict in conflicts
            if conflict["severity"] == "critical"
        ),
        "warning": sum(
            1 for conflict in conflicts
            if conflict["severity"] == "warning"
        ),
        "unavailable": sum(
            1
            for conflict in conflicts
            if any(
                issue["type"] == "unavailable"
                for issue in conflict["issues"]
            )
        ),
        "overload": sum(
            1
            for conflict in conflicts
            if any(
                issue["type"] == "overload"
                for issue in conflict["issues"]
            )
        ),
        "time_overlap": sum(
            1
            for conflict in conflicts
            if any(
                issue["type"] == "time_overlap"
                for issue in conflict["issues"]
            )
        ),
        "unassigned": sum(
            1
            for conflict in conflicts
            if any(
                issue["type"] == "unassigned"
                for issue in conflict["issues"]
            )
        ),
    }
    return conflicts, summary


def _get_dispatch_date_suggestions(
    cursor,
    company_id,
    task_id,
    task_workers,
    start_date,
    workers_by_name,
):
    try:
        search_start = datetime.strptime(start_date, "%Y-%m-%d").date()
    except Exception:
        search_start = datetime.now().date()

    if search_start < datetime.now().date():
        search_start = datetime.now().date()

    search_end = search_start + timedelta(days=13)
    assignment_rows = cursor.execute("""
    SELECT worker, workers, time_from, time_to,
           substr(task_date, 1, 10) AS work_date
    FROM tasks
    WHERE company_id=?
      AND id!=?
      AND archived=0
      AND status NOT IN ('Завершено', 'Отменено')
      AND task_date IS NOT NULL
      AND task_date != ''
      AND substr(task_date, 1, 10) BETWEEN ? AND ?
    """, (
        company_id,
        task_id,
        search_start.strftime("%Y-%m-%d"),
        search_end.strftime("%Y-%m-%d"),
    )).fetchall()
    unavailable_dates, _ = get_worker_unavailability(
        cursor,
        company_id,
        task_workers,
        search_start.strftime("%Y-%m-%d"),
        search_end.strftime("%Y-%m-%d"),
    )
    result = build_scheduling_recommendations(
        worker_capacities={
            worker_name: max(
                1,
                int(workers_by_name[worker_name]["daily_capacity"] or 3),
            )
            for worker_name in task_workers
            if worker_name in workers_by_name
        },
        assignments=[
            {
                "date": row["work_date"],
                "workers": get_task_worker_names(row),
                "time_from": row["time_from"],
                "time_to": row["time_to"],
            }
            for row in assignment_rows
        ],
        start_date=search_start,
        search_days=14,
        fixed_workers=task_workers,
        unavailable_dates=unavailable_dates,
        limit=3,
    )
    return [
        {
            "date": item["date"],
            "date_label": item["date_label"],
            "score": item["score"],
        }
        for item in result["items"]
    ]


def _build_company_dispatch_plan(
    cursor,
    company_id,
    start_date,
    search_days,
    limit=25,
):
    worker_rows = cursor.execute("""
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
    end_date = start_date + timedelta(days=search_days - 1)
    task_rows = cursor.execute("""
    SELECT *
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
    ORDER BY id
    """, (company_id,)).fetchall()
    assignment_rows = cursor.execute("""
    SELECT worker, workers, time_from, time_to,
           substr(task_date, 1, 10) AS work_date
    FROM tasks
    WHERE company_id=?
      AND archived=0
      AND status NOT IN ('Завершено', 'Отменено')
      AND task_date IS NOT NULL
      AND task_date!=''
      AND substr(task_date, 1, 10) BETWEEN ? AND ?
    """, (
        company_id,
        start_date.strftime("%Y-%m-%d"),
        end_date.strftime("%Y-%m-%d"),
    )).fetchall()
    unavailable_dates, _ = get_worker_unavailability(
        cursor,
        company_id,
        worker_capacities.keys(),
        start_date.strftime("%Y-%m-%d"),
        end_date.strftime("%Y-%m-%d"),
    )
    plan = build_dispatch_plan(
        tasks=task_rows,
        worker_capacities=worker_capacities,
        assignments=[
            {
                "date": row["work_date"],
                "workers": get_task_worker_names(row),
                "time_from": row["time_from"],
                "time_to": row["time_to"],
            }
            for row in assignment_rows
        ],
        unavailable_dates=unavailable_dates,
        start_date=start_date,
        search_days=search_days,
        limit=limit,
    )
    plan["workers_count"] = len(worker_capacities)
    plan["start"] = start_date.strftime("%Y-%m-%d")
    plan["end"] = end_date.strftime("%Y-%m-%d")
    return plan


def hash_password(password):
    hashed = bcrypt.hashpw(
        password.encode("utf-8"),
        bcrypt.gensalt()
    )
    return "bcrypt$" + hashed.decode("utf-8")


def verify_password(password, stored_password):
    password = str(password or "")
    if (
        not stored_password
        or not password
        or len(password.encode("utf-8")) > 72
    ):
        return False

    stored_password = str(stored_password)

    if stored_password.startswith("bcrypt$"):
        bcrypt_hash = stored_password.replace("bcrypt$", "", 1)
        try:
            return bcrypt.checkpw(
                password.encode("utf-8"),
                bcrypt_hash.encode("utf-8")
            )
        except ValueError:
            return False

    if stored_password.startswith("sha256$"):
        try:
            _, salt, digest = stored_password.split("$", 2)
            check = hashlib.sha256((salt + password).encode("utf-8")).hexdigest()
            return secrets.compare_digest(check, digest)
        except Exception:
            return False

    return secrets.compare_digest(password, stored_password)


def password_needs_upgrade(stored_password):
    return not str(stored_password or "").startswith("bcrypt$")


def is_password_strong(password):
    value = str(password or "")
    return bool(
        len(value) >= 8
        and len(value.encode("utf-8")) <= 72
        and any(character.isalpha() for character in value)
        and any(character.isdigit() for character in value)
    )


COMPANY_CONTEXT_DIAGNOSTIC_TABLES = [
    ("users", "Пользователи", "role!='superadmin'"),
    ("tasks", "Заявки", "1=1"),
    ("clients", "Клиенты", "1=1"),
    ("catalog_items", "Каталог", "1=1"),
    ("task_items", "Позиции смет", "1=1"),
    ("client_notes", "Заметки клиентов", "1=1"),
    ("client_files", "Файлы клиентов", "1=1"),
    ("call_records", "История звонков", "1=1"),
    ("recurring_jobs", "Повторяющиеся работы", "1=1"),
    ("custom_fields", "Настраиваемые поля", "1=1"),
    ("custom_field_values", "Значения настраиваемых полей", "1=1"),
    ("company_settings", "Настройки компаний", "1=1"),
    ("company_features", "Функции компаний", "1=1"),
]


def get_company_context_diagnostics(cursor):
    items = []

    for table_name, label, base_where in COMPANY_CONTEXT_DIAGNOSTIC_TABLES:
        missing_company = cursor.execute(f"""
        SELECT COUNT(*)
        FROM {table_name}
        WHERE ({base_where})
          AND company_id IS NULL
        """).fetchone()[0]

        invalid_company = cursor.execute(f"""
        SELECT COUNT(*)
        FROM {table_name}
        WHERE ({base_where})
          AND company_id IS NOT NULL
          AND company_id NOT IN (
              SELECT id
              FROM companies
          )
        """).fetchone()[0]

        items.append({
            "table": table_name,
            "label": label,
            "missing_company": missing_company,
            "invalid_company": invalid_company,
            "ok": missing_company == 0 and invalid_company == 0,
        })

    total_issues = sum(
        item["missing_company"] + item["invalid_company"]
        for item in items
    )

    return {
        "items": items,
        "total_issues": total_issues,
        "ok": total_issues == 0,
    }


def update_company_features(company_id, form):
    company_id = require_company_id_value(company_id)
    ensure_company_features(company_id)

    conn = connect()
    c = conn.cursor()
    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    for feature_key, _, _ in FEATURE_DEFINITIONS:
        enabled = 1 if feature_key in CORE_FEATURES else int(form.get(f"feature_{feature_key}") == "1")

        c.execute("""
        UPDATE company_features
        SET enabled=?, updated_at=?
        WHERE company_id=? AND feature_key=?
        """, (
            enabled,
            now,
            company_id,
            feature_key
        ))

    conn.commit()
    conn.close()


def get_industry_labels(industry):
    return INDUSTRY_LABEL_PRESETS.get(
        industry,
        INDUSTRY_LABEL_PRESETS["other"]
    )



def apply_business_preset(company_id, industry):
    company_id = require_company_id_value(company_id)
    ensure_company_features(company_id)

    enabled_features = set(BUSINESS_PRESETS.get(industry) or BUSINESS_PRESETS["other"])
    enabled_features.update(CORE_FEATURES)
    labels = get_industry_labels(industry)

    conn = connect()
    c = conn.cursor()
    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    for feature_key, _, _ in FEATURE_DEFINITIONS:
        enabled = 1 if feature_key in enabled_features else 0

        c.execute("""
        UPDATE company_features
        SET enabled=?, updated_at=?
        WHERE company_id=? AND feature_key=?
        """, (
            enabled,
            now,
            company_id,
            feature_key
        ))

    c.execute("""
    UPDATE company_settings
    SET
        industry=?,
        task_label=?,
        worker_label=?,
        client_label=?,
        service_label=?,
        updated_at=?
    WHERE company_id=?
    """, (
        industry,
        labels["task_label"],
        labels["worker_label"],
        labels["client_label"],
        labels["service_label"],
        now,
        company_id
    ))

    conn.commit()
    conn.close()


def record_user_limit_warning(
    company_id,
    actor_username,
    target_user_id,
    target_username,
):
    limit_usage = get_company_user_limit_usage(company_id)

    if limit_usage["tone"] not in ("warning", "danger"):
        return None

    recommended_plan = get_recommended_user_limit_plan(
        limit_usage["plan"],
        limit_usage["active_users_count"],
    )
    limit_details = (
        f"{limit_usage['status']}. "
        f"Тариф: {limit_usage['plan_label']}. "
        "Активных пользователей: "
        f"{limit_usage['active_users_count']} / "
        f"{limit_usage['user_limit_label']}."
    )

    if recommended_plan:
        limit_details += f" Рекомендуемый тариф: {recommended_plan['label']}."

    conn = connect()
    c = conn.cursor()
    c.execute("""
    INSERT INTO team_activity (
        company_id, user_id, target_username, actor_username,
        action, details, created_at
    )
    VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        company_id,
        target_user_id,
        target_username,
        actor_username,
        "Лимит тарифа",
        limit_details,
        datetime.now().strftime("%Y-%m-%d %H:%M"),
    ))
    conn.commit()
    conn.close()

    create_notification(
        company_id,
        actor_username,
        "Лимит тарифа команды",
        limit_details,
        "/billing",
    )

    return {
        "usage": limit_usage,
        "recommended_plan": recommended_plan,
        "details": limit_details,
    }


def record_company_settings_history(
    company_id,
    actor_username,
    action,
    details="",
    old_value="",
    new_value="",
):
    conn = connect()
    c = conn.cursor()
    c.execute("""
    INSERT INTO company_settings_history (
        company_id,
        actor_username,
        action,
        details,
        old_value,
        new_value,
        created_at
    )
    VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        company_id,
        actor_username,
        action,
        details,
        old_value,
        new_value,
        datetime.now().strftime("%Y-%m-%d %H:%M"),
    ))
    conn.commit()
    conn.close()


def log_ai_assistant_event(company_id, note_id, username, action, details=""):
    conn = connect()
    c = conn.cursor()

    c.execute("""
    INSERT INTO ai_assistant_events (
        company_id, note_id, username, action, details, created_at
    )
    VALUES (?, ?, ?, ?, ?, ?)
    """, (
        company_id,
        note_id,
        username,
        action,
        details,
        datetime.now().strftime("%Y-%m-%d %H:%M")
    ))

    conn.commit()
    conn.close()


def create_ai_follow_up_notifications(company_id, username, now_dt=None):
    now_dt = now_dt or datetime.now()
    today_key = now_dt.strftime("%Y-%m-%d")
    now = now_dt.strftime("%Y-%m-%d %H:%M")
    created_count = 0

    conn = connect()
    c = conn.cursor()

    due_notes = c.execute("""
    SELECT *
    FROM ai_assistant_notes
    WHERE company_id=?
      AND COALESCE(is_done, 0)=0
      AND follow_up_date IS NOT NULL
      AND follow_up_date!=''
      AND follow_up_date <= ?
    ORDER BY
      CASE COALESCE(priority, 'normal')
        WHEN 'urgent' THEN 0
        WHEN 'normal' THEN 1
        ELSE 2
      END,
      follow_up_date ASC,
      id DESC
    """, (company_id, today_key)).fetchall()

    for note in due_notes:
        title = f"ИИ-контроль: заметка #{note['id']}"
        message = note["note"]
        duplicate_count = c.execute("""
        SELECT COUNT(*)
        FROM notifications
        WHERE company_id=?
          AND username=?
          AND title=?
          AND created_at LIKE ?
        """, (
            company_id,
            username,
            title,
            f"{today_key}%"
        )).fetchone()[0]

        if duplicate_count:
            continue

        c.execute("""
        INSERT INTO notifications (
            company_id, username, title, message, link, created_at
        )
        VALUES (?, ?, ?, ?, ?, ?)
        """, (
            company_id,
            username,
            title,
            message,
            "/ai/assistant",
            now
        ))
        created_count += 1

        c.execute("""
        UPDATE ai_assistant_notes
        SET last_notified_at=?,
            notification_count=COALESCE(notification_count, 0) + 1
        WHERE id=?
          AND company_id=?
        """, (
            now,
            note["id"],
            company_id
        ))

        c.execute("""
        INSERT INTO ai_assistant_events (
            company_id, note_id, username, action, details, created_at
        )
        VALUES (?, ?, ?, ?, ?, ?)
        """, (
            company_id,
            note["id"],
            username,
            "notification_sent",
            title,
            now
        ))

        user_row = c.execute("""
        SELECT telegram_chat_id
        FROM users
        WHERE company_id=?
          AND username=?
        """, (company_id, username)).fetchone()

        if user_row and user_row["telegram_chat_id"]:
            try:
                send_message_to_chat(
                    user_row["telegram_chat_id"],
                    f"{title}\n{message}"
                )
            except Exception:
                pass

    conn.commit()
    conn.close()

    return created_count


def create_ai_follow_up_notifications_for_company(company_id, now_dt=None):
    if not has_feature(company_id, "notifications"):
        return 0

    conn = connect()
    c = conn.cursor()

    recipients = c.execute("""
    SELECT username
    FROM users
    WHERE company_id=?
      AND role IN ('boss', 'manager')
    ORDER BY role, username
    """, (company_id,)).fetchall()

    conn.close()

    created_count = 0

    for recipient in recipients:
        created_count += create_ai_follow_up_notifications(
            company_id,
            recipient["username"],
            now_dt
        )

    return created_count




def build_ai_digest_message(company_id, cursor=None):
    conn = None
    c = cursor

    if c is None:
        conn = connect()
        c = conn.cursor()

    c.execute("""
    INSERT OR IGNORE INTO company_settings (
        company_id, company_name, phone, email, address, tax_number, bank_details,
        plan, industry, task_label, worker_label, client_label, service_label,
        one_c_enabled, calls_enabled, ai_calls_enabled, updated_at
    )
    VALUES (?, '', '', '', '', '', '', 'basic', 'field_service',
            'Заявка', 'Исполнитель', 'Клиент', 'Услуга', 0, 0, 0, '')
    """, (company_id,))

    settings = c.execute("""
    SELECT *
    FROM company_settings
    WHERE company_id=?
    """, (company_id,)).fetchone()

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

    active_notes = c.execute("""
    SELECT note, priority, follow_up_date
    FROM ai_assistant_notes
    WHERE company_id=?
      AND COALESCE(is_done, 0)=0
    ORDER BY
      CASE
        WHEN follow_up_date IS NOT NULL
         AND follow_up_date!=''
         AND follow_up_date <= date('now') THEN 0
        ELSE 1
      END,
      CASE COALESCE(priority, 'normal')
        WHEN 'urgent' THEN 0
        WHEN 'normal' THEN 1
        ELSE 2
      END,
      id DESC
    LIMIT 3
    """, (company_id,)).fetchall()

    if conn:
        conn.commit()
        conn.close()

    message_lines = [
        "ИИ-сводка по бизнесу",
        f"Просроченные {settings['task_label'] or 'задачи'}: {overdue_tasks}",
        f"Неоплаченная сумма: ₽{round(float(unpaid_total or 0), 1)}"
    ]

    if overdue_tasks:
        message_lines.append("Рекомендация: проверьте ответственных и сроки.")

    if unpaid_total:
        message_lines.append("Рекомендация: запустите напоминания по оплатам.")

    if active_notes:
        message_lines.append("Активные заметки владельца:")

        for note in active_notes:
            priority_prefix = "Срочно: " if note["priority"] == "urgent" else ""
            follow_up_suffix = f" (контроль: {note['follow_up_date']})" if note["follow_up_date"] else ""
            message_lines.append(f"- {priority_prefix}{note['note']}{follow_up_suffix}")

    return "\n".join(message_lines)


def build_owner_ai_assistant_context(company_id, note_filter="", note_search="", event_filter=""):
    settings = get_company_settings(company_id)
    task_label = settings["task_label"] or "задачи"
    worker_label = settings["worker_label"] or "сотрудник"
    trigger_labels = dict(AUTOMATION_TRIGGERS)
    selected_note_filter = note_filter if note_filter in ("due", "urgent") else ""
    selected_note_search = (note_search or "").strip()[:80]
    selected_event_filter = event_filter if event_filter in (
        "created",
        "notification_sent",
        "postponed",
        "done"
    ) else ""
    note_filter_sql = ""
    note_params = [company_id]
    completed_note_params = [company_id]
    event_filter_sql = ""
    event_params = [company_id]

    if selected_note_filter == "due":
        note_filter_sql = """
          AND follow_up_date IS NOT NULL
          AND follow_up_date!=''
          AND follow_up_date <= date('now')
        """
    elif selected_note_filter == "urgent":
        note_filter_sql = """
          AND COALESCE(priority, 'normal')='urgent'
        """

    note_search_sql = ""

    if selected_note_search:
        note_search_sql = "AND note LIKE ?"
        note_params.append(f"%{selected_note_search}%")
        completed_note_params.append(f"%{selected_note_search}%")

    if selected_event_filter:
        event_filter_sql = "AND action=?"
        event_params.append(selected_event_filter)

    conn = connect()
    c = conn.cursor()

    overdue_tasks = c.execute("""
    SELECT COUNT(*)
    FROM tasks
    WHERE company_id=?
      AND archived=0
      AND status NOT IN ('Завершено', 'Отменено')
      AND task_date < date('now')
    """, (company_id,)).fetchone()[0]

    active_tasks = c.execute("""
    SELECT COUNT(*)
    FROM tasks
    WHERE company_id=?
      AND archived=0
      AND status IN ('Новая', 'В работе')
    """, (company_id,)).fetchone()[0]

    unpaid_total = c.execute("""
    SELECT COALESCE(SUM(CAST(REPLACE(COALESCE(price, '0'), ',', '.') AS REAL)), 0)
    FROM tasks
    WHERE company_id=?
      AND archived=0
      AND payment_status!='Оплачено'
    """, (company_id,)).fetchone()[0]

    worker_count = c.execute("""
    SELECT COUNT(*)
    FROM users
    WHERE company_id=?
      AND role='worker'
    """, (company_id,)).fetchone()[0]

    assistant_note_stats = c.execute("""
    SELECT
        COUNT(*) AS active_count,
        SUM(CASE WHEN COALESCE(priority, 'normal')='urgent' THEN 1 ELSE 0 END) AS urgent_count,
        SUM(
            CASE
                WHEN follow_up_date IS NOT NULL
                 AND follow_up_date!=''
                 AND follow_up_date <= date('now')
                THEN 1
                ELSE 0
            END
        ) AS due_count
    FROM ai_assistant_notes
    WHERE company_id=?
      AND COALESCE(is_done, 0)=0
    """, (company_id,)).fetchone()

    overdue_rows = c.execute("""
    SELECT id, client, task_date, workers, worker, status
    FROM tasks
    WHERE company_id=?
      AND archived=0
      AND status NOT IN ('Завершено', 'Отменено')
      AND task_date < date('now')
    ORDER BY task_date ASC
    LIMIT 5
    """, (company_id,)).fetchall()

    action_history = c.execute("""
    SELECT
        automation_events.*,
        automation_rules.name AS rule_name
    FROM automation_events
    LEFT JOIN automation_rules
      ON automation_rules.id=automation_events.rule_id
      AND automation_rules.company_id=automation_events.company_id
    WHERE automation_events.company_id=?
      AND automation_events.trigger_key IN (
          'overdue_task',
          'sla_overdue',
          'daily_digest',
          'weekly_digest'
      )
    ORDER BY automation_events.id DESC
    LIMIT 8
    """, (company_id,)).fetchall()

    assistant_notes = c.execute(f"""
    SELECT *
    FROM ai_assistant_notes
    WHERE company_id=?
      AND COALESCE(is_done, 0)=0
      {note_filter_sql}
      {note_search_sql}
    ORDER BY
      CASE
        WHEN follow_up_date IS NOT NULL
         AND follow_up_date!=''
         AND follow_up_date <= date('now') THEN 0
        ELSE 1
      END,
      CASE COALESCE(priority, 'normal')
        WHEN 'urgent' THEN 0
        WHEN 'normal' THEN 1
        ELSE 2
      END,
      id DESC
    LIMIT 8
    """, note_params).fetchall()

    ai_events = c.execute(f"""
    SELECT *
    FROM ai_assistant_events
    WHERE company_id=?
      {event_filter_sql}
    ORDER BY id DESC
    LIMIT 10
    """, event_params).fetchall()

    completed_notes = c.execute(f"""
    SELECT
        ai_assistant_notes.*,
        tasks.client AS created_task_client,
        tasks.status AS created_task_status
    FROM ai_assistant_notes
    LEFT JOIN tasks
      ON tasks.id=ai_assistant_notes.created_task_id
      AND tasks.company_id=ai_assistant_notes.company_id
    WHERE ai_assistant_notes.company_id=?
      AND COALESCE(ai_assistant_notes.is_done, 0)=1
      {note_search_sql}
    ORDER BY ai_assistant_notes.id DESC
    LIMIT 8
    """, completed_note_params).fetchall()

    conn.close()

    action_history_rows = []

    for event in action_history:
        event_row = dict(event)
        event_row["trigger_label"] = trigger_labels.get(event["trigger_key"], event["trigger_key"])
        event_row["status_label"] = AUTOMATION_STATUS_LABELS.get(event["status"], event["status"])
        action_history_rows.append(event_row)

    priorities = []

    if overdue_tasks:
        priorities.append({
            "level": "danger",
            "title": "Сначала разберите просрочки",
            "reason": f"Просрочено: {overdue_tasks} ({task_label}).",
            "action": "Открыть просрочки",
            "link": "/overdue"
        })

    if unpaid_total:
        priorities.append({
            "level": "warning",
            "title": "Проверьте неоплаченные работы",
            "reason": f"Неоплаченная сумма: ₽{round(float(unpaid_total or 0), 1)}.",
            "action": "Открыть финансы",
            "link": "/finance"
        })

    if worker_count and active_tasks > worker_count * 3:
        priorities.append({
            "level": "warning",
            "title": "Проверьте загрузку команды",
            "reason": f"Активных {task_label}: {active_tasks}, {worker_label}: {worker_count}.",
            "action": "Открыть загрузку",
            "link": "/workload"
        })

    if not priorities:
        priorities.append({
            "level": "success",
            "title": "Критичных действий сейчас нет",
            "reason": "ИИ-помощник не видит срочных просрочек, перегруза или кассового риска.",
            "action": "Смотреть ИИ-инсайты",
            "link": "/ai/insights"
        })

    next_steps = [
        "Проверьте самый старый риск первым.",
        "Назначьте ответственного и дату следующего действия.",
        "После исправления запустите ИИ-сводку повторно."
    ]

    return {
        "settings": settings,
        "metrics": {
            "overdue_tasks": overdue_tasks,
            "active_tasks": active_tasks,
            "unpaid_total": round(float(unpaid_total or 0), 1),
            "worker_count": worker_count,
            "ai_notes_active": assistant_note_stats["active_count"] or 0,
            "ai_notes_urgent": assistant_note_stats["urgent_count"] or 0,
            "ai_notes_due": assistant_note_stats["due_count"] or 0
        },
        "priorities": priorities,
        "next_steps": next_steps,
        "overdue_rows": overdue_rows,
        "action_history": action_history_rows,
        "assistant_notes": assistant_notes,
        "ai_events": ai_events,
        "selected_note_filter": selected_note_filter,
        "selected_note_search": selected_note_search,
        "selected_event_filter": selected_event_filter,
        "completed_notes": completed_notes
    }


def automation_single_condition_matches(c, company_id, rule, entity_type, entity_id, condition):
    rule_data = dict(rule)
    rule_data["conditions_json"] = json.dumps(condition or {}, ensure_ascii=False)
    return automation_condition_matches(
        c,
        company_id,
        rule_data,
        entity_type,
        entity_id,
    )


def automation_combined_conditions_match(c, company_id, rule, entity_type, entity_id, conditions):
    items = conditions.get("conditions") or []
    operator = str(conditions.get("operator") or "and").lower()

    if not items:
        return True, ""

    results = [
        automation_single_condition_matches(
            c,
            company_id,
            rule,
            entity_type,
            entity_id,
            item,
        )
        for item in items
    ]

    if operator == "or":
        if any(result[0] for result in results):
            return True, ""

        message = "; ".join([result[1] for result in results if result[1]])
        return False, message or "Ни одно условие не выполнено"

    if all(result[0] for result in results):
        return True, ""

    message = "; ".join([result[1] for result in results if result[1]])
    return False, message or "Не все условия выполнены"


def automation_condition_diagnostics(c, company_id, rule, entity_type, entity_id):
    try:
        conditions = json.loads(rule["conditions_json"] or "{}")
    except Exception:
        conditions = {}

    items = conditions.get("conditions") or [conditions]
    operator = str(conditions.get("operator") or "and").lower()

    if operator not in ("and", "or"):
        operator = "and"

    details = []

    for condition in items:
        mode = str(condition.get("mode") or "none")
        matched, message = automation_single_condition_matches(
            c,
            company_id,
            rule,
            entity_type,
            entity_id,
            condition,
        )
        details.append({
            "label": str(condition.get("label") or (
                "Без условий" if mode == "none" else mode
            )),
            "matched": bool(matched),
            "message": (
                "Условие выполнено"
                if matched
                else str(message or "Условие не выполнено")
            )[:180],
        })

    results = [item["matched"] for item in details]
    overall = any(results) if operator == "or" else all(results)

    return {
        "matched": overall,
        "operator": operator,
        "operator_label": "ИЛИ" if operator == "or" else "И",
        "details": details,
    }


def automation_condition_batch_summary(c, company_id, rule, task_ids):
    matched_task_ids = []
    rejected_tasks = []
    condition_stats = []
    operator = "and"

    for task_id in task_ids:
        diagnostics = automation_condition_diagnostics(
            c,
            company_id,
            rule,
            "task",
            task_id,
        )
        operator = diagnostics["operator"]

        if not condition_stats:
            condition_stats = [
                {
                    "label": detail["label"],
                    "matched": 0,
                }
                for detail in diagnostics["details"]
            ]

        for index, detail in enumerate(diagnostics["details"]):
            if detail["matched"]:
                condition_stats[index]["matched"] += 1

        if diagnostics["matched"]:
            matched_task_ids.append(task_id)
        elif len(rejected_tasks) < 10:
            rejected_tasks.append({
                "id": task_id,
                "failed_conditions": [
                    detail["label"]
                    for detail in diagnostics["details"]
                    if not detail["matched"]
                ],
            })

    total = len(task_ids)
    matched_count = len(matched_task_ids)

    for item in condition_stats:
        item["match_rate"] = round(
            (item["matched"] / total) * 100
        ) if total else 0

    return {
        "total": total,
        "matched": matched_count,
        "match_rate": round((matched_count / total) * 100) if total else 0,
        "matched_task_ids": matched_task_ids[:10],
        "rejected_tasks": rejected_tasks,
        "condition_stats": condition_stats,
        "operator": operator,
    }


def automation_condition_coverage_assessment(total, matched):
    total = max(int(total or 0), 0)
    matched = max(min(int(matched or 0), total), 0)

    if total == 0:
        return {
            "status": "no_data",
            "tone": "off",
            "title": "Недостаточно данных",
            "message": "Добавьте заявки или увеличьте период проверки.",
        }

    match_rate = round((matched / total) * 100)

    if match_rate == 0:
        return {
            "status": "too_narrow",
            "tone": "warn",
            "title": "Правило слишком узкое",
            "message": "Ни одна заявка не подходит. Проверьте значения и сочетание условий.",
        }

    if match_rate <= 15:
        return {
            "status": "narrow",
            "tone": "warn",
            "title": "Правило узкое",
            "message": "Срабатываний мало. Убедитесь, что нужные заявки не отсеиваются.",
        }

    if match_rate <= 80:
        return {
            "status": "balanced",
            "tone": "ok",
            "title": "Правило сбалансировано",
            "message": "Условия выделяют заметную часть заявок и не охватывают все подряд.",
        }

    if match_rate < 100:
        return {
            "status": "broad",
            "tone": "warn",
            "title": "Правило широкое",
            "message": "Проверьте, не будет ли автоматизация срабатывать слишком часто.",
        }

    return {
        "status": "all",
        "tone": "warn",
        "title": "Правило подходит всем заявкам",
        "message": "Добавьте ограничивающее условие, если автоматизация не должна запускаться всегда.",
    }


def automation_condition_focus_assessment(condition_stats, operator="and"):
    valid_stats = [
        item
        for item in (condition_stats or [])
        if isinstance(item, dict) and item.get("label")
    ]

    if not valid_stats:
        return {}

    operator = "or" if operator == "or" else "and"

    if operator == "or":
        focus = max(
            valid_stats,
            key=lambda item: int(item.get("match_rate") or 0),
        )
        return {
            "title": "Главная ветка условия ИЛИ",
            "label": str(focus["label"]),
            "match_rate": int(focus.get("match_rate") or 0),
            "message": "Эта ветка даёт больше всего совпадений.",
        }

    focus = min(
        valid_stats,
        key=lambda item: int(item.get("match_rate") or 0),
    )
    return {
        "title": "Главное ограничение правила",
        "label": str(focus["label"]),
        "match_rate": int(focus.get("match_rate") or 0),
        "message": "Это условие сильнее остальных сокращает количество подходящих заявок.",
    }


def automation_action_dry_run_preview(action):
    action_data = dict(action)

    try:
        payload = json.loads(action_data.get("payload_json") or "{}")
    except Exception:
        payload = {}

    action_key = str(action_data.get("action_key") or "")
    target = str(payload.get("target_username") or "").strip()
    message = str(payload.get("message") or "").strip()
    subject = str(payload.get("subject") or "").strip()
    task_delay_days, task_priority, task_deadline_hours = (
        automation_create_task_settings(payload)
    )
    task_max_daily_load = automation_task_max_daily_load(payload)
    task_capacity_fallback_days = (
        automation_task_capacity_fallback_days(payload)
    )
    task_business_days_only = automation_task_business_days_only(payload)
    supported = action_key in {
        "notification",
        "telegram_alert",
        "ai_digest",
        "create_task",
    }

    if action_key == "notification":
        detail = f"Получатель: {target or 'создатель правила'}"
    elif action_key == "telegram_alert":
        detail = f"Telegram: {target or 'создатель правила'}"
    elif action_key == "ai_digest":
        detail = f"ИИ-сводка для: {target or 'создатель правила'}"
    elif action_key == "email":
        detail = f"Почта: {target or 'получатель не указан'}"
    elif action_key == "create_task":
        target_label = (
            "авто: наименее загруженный"
            if target == "__least_loaded__"
            else target or "без исполнителя"
        )
        schedule_label = (
            "сегодня"
            if task_delay_days == 0
            else f"через {task_delay_days} дн."
        )
        deadline_label = (
            "без SLA"
            if task_deadline_hours == 0
            else f"SLA: {task_deadline_hours} ч."
        )
        load_limit_detail = ""

        if target == "__least_loaded__":
            load_limit_label = (
                "без лимита загрузки"
                if task_max_daily_load == 0
                else f"лимит: {task_max_daily_load} в день"
            )
            load_limit_detail = f" · {load_limit_label}"
            load_limit_detail += " · справедливое распределение"

            if task_capacity_fallback_days:
                load_limit_detail += (
                    f" · поиск окна: {task_capacity_fallback_days} дн."
                )

            if task_business_days_only:
                load_limit_detail += " · только рабочие дни"

        detail = (
            f"Новая задача для: {target_label}"
            f" · {schedule_label}"
            f" · приоритет: {task_priority}"
            f" · {deadline_label}"
            f"{load_limit_detail}"
            " · данные клиента из исходной заявки"
        )
    else:
        detail = "Неизвестное действие"

    if subject:
        detail = f"{detail} · Тема: {subject}"

    if message:
        detail = f"{detail} · {message[:140]}"

    action_data["dry_run_supported"] = supported
    action_data["dry_run_detail"] = detail
    return action_data


def automation_create_task_settings(payload):
    try:
        task_delay_days = int(payload.get("task_delay_days") or 0)
    except (TypeError, ValueError):
        task_delay_days = 0

    if task_delay_days not in (0, 1, 3, 7):
        task_delay_days = 0

    task_priority = str(payload.get("task_priority") or "Обычный").strip()

    if task_priority not in ("Обычный", "Срочно"):
        task_priority = "Обычный"

    try:
        task_deadline_hours = int(payload.get("task_deadline_hours") or 0)
    except (TypeError, ValueError):
        task_deadline_hours = 0

    if task_deadline_hours not in (0, 4, 8, 24, 72):
        task_deadline_hours = 0

    return task_delay_days, task_priority, task_deadline_hours


def automation_task_max_daily_load(payload):
    try:
        max_daily_load = int(payload.get("task_max_daily_load") or 0)
    except (TypeError, ValueError):
        max_daily_load = 0

    if max_daily_load not in (0, 1, 2, 3, 5):
        max_daily_load = 0

    return max_daily_load


def automation_task_capacity_fallback_days(payload):
    try:
        fallback_days = int(
            payload.get("task_capacity_fallback_days") or 0
        )
    except (TypeError, ValueError):
        fallback_days = 0

    if fallback_days not in (0, 1, 3, 7):
        fallback_days = 0

    return fallback_days


def automation_task_business_days_only(payload):
    return str(
        payload.get("task_business_days_only") or ""
    ).strip().lower() in ("1", "true", "yes", "on")


def automation_least_loaded_worker(
    c,
    company_id,
    task_date,
    max_daily_load=0,
):
    workers = c.execute("""
    SELECT username, telegram_chat_id
    FROM users
    WHERE company_id=?
      AND role='worker'
      AND COALESCE(is_active, 1)=1
    ORDER BY username
    """, (company_id,)).fetchall()

    if not workers:
        return None

    worker_load = {
        worker["username"]: 0
        for worker in workers
    }
    last_auto_assignment = {
        worker["username"]: 0
        for worker in workers
    }
    tasks = c.execute("""
    SELECT worker, workers
    FROM tasks
    WHERE company_id=?
      AND archived=0
      AND task_date LIKE ?
      AND status NOT IN ('Завершено', 'Отменено')
    """, (company_id, f"{task_date}%")).fetchall()

    for task in tasks:
        for worker_name in get_task_worker_names(task):
            if worker_name in worker_load:
                worker_load[worker_name] += 1

    assignment_rows = c.execute("""
    SELECT
        automation_action_runs.id AS run_id,
        tasks.worker,
        tasks.workers
    FROM automation_action_runs
    JOIN tasks
      ON tasks.id=automation_action_runs.created_entity_id
      AND tasks.company_id=automation_action_runs.company_id
    WHERE automation_action_runs.company_id=?
      AND automation_action_runs.created_entity_type='task'
    ORDER BY automation_action_runs.id DESC
    """, (company_id,))

    for assignment in assignment_rows:
        for worker_name in get_task_worker_names(assignment):
            if (
                worker_name in last_auto_assignment
                and not last_auto_assignment[worker_name]
            ):
                last_auto_assignment[worker_name] = assignment["run_id"]

        if all(last_auto_assignment.values()):
            break

    available_workers = [
        worker
        for worker in workers
        if (
            not max_daily_load
            or worker_load[worker["username"]] < max_daily_load
        )
    ]

    if not available_workers:
        return None

    selected_worker = min(
        available_workers,
        key=lambda worker: (
            worker_load[worker["username"]],
            last_auto_assignment[worker["username"]],
            worker["username"],
        ),
    )

    return {
        "username": selected_worker["username"],
        "telegram_chat_id": selected_worker["telegram_chat_id"],
        "active_count": worker_load[selected_worker["username"]],
        "last_auto_assignment": last_auto_assignment[
            selected_worker["username"]
        ],
    }


def automation_find_available_worker_slot(
    c,
    company_id,
    scheduled_at,
    max_daily_load=0,
    fallback_days=0,
    business_days_only=False,
):
    for offset_days in range(0, fallback_days + 1):
        candidate_at = scheduled_at + timedelta(days=offset_days)

        if business_days_only and candidate_at.weekday() >= 5:
            continue

        selected_worker = automation_least_loaded_worker(
            c,
            company_id,
            candidate_at.strftime("%Y-%m-%d"),
            max_daily_load,
        )

        if selected_worker:
            return selected_worker, candidate_at

    return None, scheduled_at


def automation_action_target_is_valid(c, company_id, action_key, target_username):
    target_username = str(target_username or "").strip()

    if action_key == "create_task":
        if not target_username:
            return True

        if target_username == "__least_loaded__":
            return bool(c.execute("""
            SELECT id
            FROM users
            WHERE company_id=?
              AND role='worker'
              AND COALESCE(is_active, 1)=1
            LIMIT 1
            """, (company_id,)).fetchone())

        return bool(c.execute("""
        SELECT id
        FROM users
        WHERE company_id=?
          AND username=?
          AND role='worker'
          AND COALESCE(is_active, 1)=1
        """, (company_id, target_username)).fetchone())

    if not target_username:
        return action_key not in ("notification", "telegram_alert", "email")

    return bool(c.execute("""
    SELECT id
    FROM users
    WHERE company_id=?
      AND username=?
      AND COALESCE(is_active, 1)=1
    """, (company_id, target_username)).fetchone())


def execute_automation_create_task_action(
    c,
    company_id,
    rule,
    action,
    payload,
    entity_type,
    entity_id,
    now,
    failure_details=None,
    success_details=None,
):
    if entity_type not in ("task", "client") or not entity_id:
        return None

    previous_run = c.execute("""
    SELECT created_entity_id
    FROM automation_action_runs
    WHERE company_id=?
      AND action_id=?
      AND entity_type=?
      AND entity_id=?
    """, (
        company_id,
        action["id"],
        entity_type,
        entity_id,
    )).fetchone()

    if previous_run:
        return previous_run["created_entity_id"]

    if entity_type == "task":
        source_row = c.execute("""
        SELECT
            client_id,
            client,
            phone,
            address
        FROM tasks
        WHERE company_id=?
          AND id=?
          AND archived=0
        """, (company_id, entity_id)).fetchone()
        source_label = f"Исходная заявка: #{entity_id}"
    else:
        source_row = c.execute("""
        SELECT
            id AS client_id,
            name AS client,
            phone,
            address
        FROM clients
        WHERE company_id=?
          AND id=?
        """, (company_id, entity_id)).fetchone()
        source_label = f"Исходный клиент: #{entity_id}"

    if not source_row:
        return None

    description = str(payload.get("message") or "").strip()
    task_delay_days, task_priority, task_deadline_hours = (
        automation_create_task_settings(payload)
    )
    task_max_daily_load = automation_task_max_daily_load(payload)
    task_capacity_fallback_days = (
        automation_task_capacity_fallback_days(payload)
    )
    task_business_days_only = automation_task_business_days_only(payload)
    scheduled_at = datetime.now() + timedelta(days=task_delay_days)
    task_date = scheduled_at.strftime("%Y-%m-%d")
    requested_task_date = task_date
    deadline_at = ""

    if task_deadline_hours:
        deadline_at = (
            scheduled_at + timedelta(hours=task_deadline_hours)
        ).strftime("%Y-%m-%dT%H:%M")

    target_username = str(payload.get("target_username") or "").strip()
    target_worker = ""
    target_chat_id = ""

    if target_username == "__least_loaded__":
        selected_worker, selected_at = automation_find_available_worker_slot(
            c,
            company_id,
            scheduled_at,
            task_max_daily_load,
            task_capacity_fallback_days,
            task_business_days_only,
        )

        if selected_worker:
            scheduled_at = selected_at
            task_date = scheduled_at.strftime("%Y-%m-%d")

            if task_deadline_hours:
                deadline_at = (
                    scheduled_at
                    + timedelta(hours=task_deadline_hours)
                ).strftime("%Y-%m-%dT%H:%M")

            target_worker = selected_worker["username"]
            target_chat_id = str(
                selected_worker["telegram_chat_id"] or ""
            ).strip()
        else:
            if failure_details is not None:
                failure_details.append(
                    (
                        "Нет исполнителя с доступной загрузкой "
                        f"на {task_date}"
                        + (
                            (
                                " и в течение "
                                f"{task_capacity_fallback_days} дн. после неё"
                            )
                            if task_capacity_fallback_days
                            else ""
                        )
                        + ". "
                        f"Лимит на исполнителя: {task_max_daily_load} в день."
                        + (
                            " Учитываются только рабочие дни."
                            if task_business_days_only
                            else ""
                        )
                    )
                )
            return None
    elif target_username:
        worker_row = c.execute("""
        SELECT username, telegram_chat_id
        FROM users
        WHERE company_id=?
          AND username=?
          AND role='worker'
          AND COALESCE(is_active, 1)=1
        """, (company_id, target_username)).fetchone()

        if worker_row:
            target_worker = worker_row["username"]
            target_chat_id = str(worker_row["telegram_chat_id"] or "").strip()

    if not description:
        description = f"Автоматическая задача: {rule['name']}"

    was_rescheduled = task_date != requested_task_date
    schedule_activity = ""

    if was_rescheduled:
        schedule_activity = (
            f". Автоперенос: {requested_task_date} → {task_date}"
        )

    c.execute("""
    INSERT INTO tasks (
        company_id, client_id, client, phone, address,
        description, task_date, worker, workers,
        priority, price, photo, status, report,
        after_photo, created_at, deadline_at
    )
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        company_id,
        source_row["client_id"],
        source_row["client"],
        source_row["phone"],
        source_row["address"],
        description,
        task_date,
        target_worker,
        target_worker,
        task_priority,
        "0",
        "",
        "Новая",
        "",
        "",
        now,
        deadline_at,
    ))
    created_task_id = c.lastrowid

    c.execute("""
    INSERT INTO task_activity (
        task_id, username, role, action, details, created_at
    )
    VALUES (?, ?, 'system', 'Создана автоматизацией', ?, ?)
    """, (
        created_task_id,
        rule["created_by"] or "automation",
        (
            f"Правило: {rule['name']}. "
            f"{source_label}. "
            f"Исполнитель: {target_worker or 'не назначен'}. "
            f"Дата: {task_date}. Приоритет: {task_priority}. "
            f"SLA: {deadline_at or 'не задан'}"
            f"{schedule_activity}"
        ),
        now,
    ))

    if target_worker:
        c.execute("""
        INSERT INTO notifications (
            company_id, username, title, message,
            link, created_at
        )
        VALUES (?, ?, ?, ?, ?, ?)
        """, (
            company_id,
            target_worker,
            f"Новая автоматическая заявка #{created_task_id}",
            description,
            f"/task/{created_task_id}",
            now,
        ))

    if was_rescheduled:
        reschedule_message = (
            f"Заявка #{created_task_id} перенесена "
            f"с {requested_task_date} на {task_date}. "
            f"Исполнитель: {target_worker or 'не назначен'}."
        )

        if success_details is not None:
            success_details.append(reschedule_message)

        owner_username = str(rule["created_by"] or "").strip()

        if owner_username:
            c.execute("""
            INSERT INTO notifications (
                company_id, username, title, message,
                link, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """, (
                company_id,
                owner_username,
                f"A3 перенёс заявку #{created_task_id}",
                reschedule_message,
                f"/task/{created_task_id}",
                now,
            ))

    c.execute("""
    INSERT INTO automation_action_runs (
        company_id, action_id, entity_type, entity_id,
        created_entity_type, created_entity_id, created_at
    )
    VALUES (?, ?, ?, ?, 'task', ?, ?)
    """, (
        company_id,
        action["id"],
        entity_type,
        entity_id,
        created_task_id,
        now,
    ))

    if target_chat_id:
        try:
            send_message_to_chat(
                target_chat_id,
                (
                    f"Вам назначена автоматическая заявка #{created_task_id}\n"
                    f"Клиент: {source_row['client'] or 'Без клиента'}\n"
                    f"Дата: {task_date}\n"
                    f"SLA: {deadline_at or 'не задан'}\n"
                    f"Описание: {description}"
                ),
            )
        except Exception:
            pass

    return created_task_id


def automation_dry_run_readiness(rule_active, condition_matched, actions):
    active_actions = [
        automation_action_dry_run_preview(action)
        for action in (actions or [])
        if action["active"]
    ]
    inactive_actions = [
        automation_action_dry_run_preview(action)
        for action in (actions or [])
        if not action["active"]
    ]
    executable_actions = [
        action
        for action in active_actions
        if action["dry_run_supported"]
    ]
    unsupported_actions = [
        action
        for action in active_actions
        if not action["dry_run_supported"]
    ]

    if not rule_active:
        status = {
            "status": "rule_disabled",
            "tone": "off",
            "title": "Запуск заблокирован",
            "message": "Правило выключено. Включите его перед реальным запуском.",
        }
    elif not condition_matched:
        status = {
            "status": "condition_failed",
            "tone": "warn",
            "title": "Запуск заблокирован",
            "message": "Условия не выполнены для выбранной заявки.",
        }
    elif not active_actions:
        status = {
            "status": "no_actions",
            "tone": "warn",
            "title": "Нет активных действий",
            "message": "Добавьте или включите хотя бы одно действие цепочки.",
        }
    elif not executable_actions:
        status = {
            "status": "unsupported_actions",
            "tone": "warn",
            "title": "Действия ещё не поддерживаются",
            "message": "Настроенные действия пока не исполняются текущим движком выполнения.",
        }
    else:
        status = {
            "status": "ready",
            "tone": "ok",
            "title": "Готово к запуску",
            "message": f"Будет выполнено действий: {len(executable_actions)}.",
        }

    status["active_actions"] = active_actions
    status["executable_actions"] = executable_actions
    status["unsupported_actions"] = unsupported_actions
    status["inactive_actions"] = inactive_actions
    return status


def automation_condition_number(conditions, default, minimum=0):
    try:
        value = float(str(conditions.get("value", default)).replace(",", "."))
    except (TypeError, ValueError):
        value = float(default)

    return max(value, minimum)


CLIENT_AUTOMATION_CONDITION_MODES = {
    "client_specific",
    "client_new",
    "client_repeat",
    "client_vip",
    "client_has_debt",
    "client_many_tasks",
}


def automation_client_condition_matches(c, company_id, conditions, client_id):
    mode = conditions.get("mode") or "none"

    try:
        client_id = int(client_id or 0)
    except (TypeError, ValueError):
        client_id = 0

    if not client_id:
        return False, f"Условие не выполнено: {conditions.get('label') or mode}"

    client = c.execute("""
    SELECT id, name, phone, notes, created_at
    FROM clients
    WHERE id=?
      AND company_id=?
    """, (client_id, company_id)).fetchone()

    if not client:
        return False, f"Условие не выполнено: клиент #{client_id} не найден"

    client_task_count = c.execute("""
    SELECT COUNT(*)
    FROM tasks
    WHERE company_id=?
      AND client_id=?
    """, (
        company_id,
        client_id,
    )).fetchone()[0]

    client_unpaid_count = c.execute("""
    SELECT COUNT(*)
    FROM tasks
    WHERE company_id=?
      AND client_id=?
      AND payment_status IN ('Не оплачено', 'unpaid', 'not_paid')
    """, (
        company_id,
        client_id,
    )).fetchone()[0]

    client_task_threshold = int(automation_condition_number(conditions, 5, 1))

    if mode == "client_specific":
        try:
            selected_client_id = int(conditions.get("value"))
        except (TypeError, ValueError):
            selected_client_id = 0

        if selected_client_id and client_id == selected_client_id:
            return True, ""

    elif mode == "client_new":
        if client_task_count <= 1:
            return True, ""

    elif mode == "client_repeat":
        if client_task_count >= 2:
            return True, ""

    elif mode == "client_vip":
        client_notes = str(client["notes"] or "").lower()
        if "vip" in client_notes or "вип" in client_notes:
            return True, ""

    elif mode == "client_has_debt":
        if client_unpaid_count > 0:
            return True, ""

    elif mode == "client_many_tasks":
        if client_task_count >= client_task_threshold:
            return True, ""

    return False, f"Условие не выполнено: {conditions.get('label') or mode}"



def automation_condition_matches(c, company_id, rule, entity_type, entity_id):
    try:
        conditions = json.loads(rule["conditions_json"] or "{}")
    except Exception:
        conditions = {}

    if conditions.get("conditions"):
        return automation_combined_conditions_match(
            c,
            company_id,
            rule,
            entity_type,
            entity_id,
            conditions,
        )

    mode = conditions.get("mode") or "none"

    if mode == "none":
        return True, ""

    if entity_type == "client" and mode in CLIENT_AUTOMATION_CONDITION_MODES:
        return automation_client_condition_matches(
            c,
            company_id,
            conditions,
            entity_id,
        )

    if entity_type != "task" or not entity_id:
        return False, f"Условие не выполнено: {conditions.get('label') or mode}"

    task = c.execute("""
    SELECT
        id,
        client_id,
        client,
        phone,
        address,
        description,
        priority,
        status,
        payment_status,
        worker,
        workers,
        task_date,
        price,
        deadline_at
    FROM tasks
    WHERE company_id=?
      AND id=?
    """, (
        company_id,
        entity_id,
    )).fetchone()

    if not task:
        return False, f"Условие не выполнено: задача #{entity_id} не найдена"

    priority = str(task["priority"] or "").strip().lower()
    status = str(task["status"] or "").strip().lower()
    payment_status = str(task["payment_status"] or "").strip().lower()
    task_search_text = " ".join([
        str(task["client"] or ""),
        str(task["phone"] or ""),
        str(task["address"] or ""),
        str(task["description"] or ""),
    ]).lower()
    task_date = str(task["task_date"] or "")[:10]
    deadline_at = str(task["deadline_at"] or "")
    deadline_date = deadline_at[:10]

    try:
        task_price = float(
            str(task["price"] or "0")
            .replace(" ", "")
            .replace(",", ".")
        )
    except Exception:
        task_price = 0

    today_dt = datetime.now()
    today = today_dt.strftime("%Y-%m-%d")
    tomorrow = (today_dt + timedelta(days=1)).strftime("%Y-%m-%d")
    next_7_days_date = (today_dt + timedelta(days=7)).strftime("%Y-%m-%d")
    next_24h = today_dt + timedelta(hours=24)
    price_threshold = automation_condition_number(conditions, 10000)
    client_task_threshold = int(automation_condition_number(conditions, 5, 1))

    client_id = task["client_id"]
    client = None

    if client_id:
        client = c.execute("""
        SELECT id, name, phone, notes, created_at
        FROM clients
        WHERE id=?
          AND company_id=?
        """, (client_id, company_id)).fetchone()

    client_task_count = 0
    client_unpaid_count = 0

    if client_id:
        client_task_count = c.execute("""
        SELECT COUNT(*)
        FROM tasks
        WHERE company_id=?
          AND client_id=?
        """, (
            company_id,
            client_id,
        )).fetchone()[0]

        client_unpaid_count = c.execute("""
        SELECT COUNT(*)
        FROM tasks
        WHERE company_id=?
          AND client_id=?
          AND payment_status IN ('Не оплачено', 'unpaid', 'not_paid')
        """, (
            company_id,
            client_id,
        )).fetchone()[0]

    if mode == "priority_high":
        if priority in ("срочно", "высокий", "urgent", "high"):
            return True, ""

    elif mode == "emergency":
        if priority in ("срочно", "urgent", "emergency"):
            return True, ""

    elif mode == "task_text_contains":
        keyword = str(conditions.get("value") or "").strip().lower()
        if keyword and keyword in task_search_text:
            return True, ""

    elif mode == "status_new":
        if status in ("новая", "new"):
            return True, ""

    elif mode == "status_in_progress":
        if status in ("в работе", "in_progress", "working"):
            return True, ""

    elif mode == "status_done":
        if status in ("завершено", "done", "completed"):
            return True, ""

    elif mode == "status_cancelled":
        if status in ("отменено", "cancelled", "canceled"):
            return True, ""

    elif mode == "payment_unpaid":
        if payment_status in ("не оплачено", "unpaid", "not_paid"):
            return True, ""

    elif mode == "payment_partial":
        if payment_status in ("частично оплачено", "partial", "partially_paid"):
            return True, ""

    elif mode == "payment_paid":
        if payment_status in ("оплачено", "paid"):
            return True, ""

    elif mode == "worker_assigned":
        if get_task_worker_names(task):
            return True, ""

    elif mode == "worker_unassigned":
        if not get_task_worker_names(task):
            return True, ""

    elif mode == "worker_specific":
        selected_worker = str(conditions.get("value") or "").strip()
        if selected_worker and task_has_worker(selected_worker, task):
            return True, ""

    elif mode == "date_today":
        if task_date == today:
            return True, ""

    elif mode == "date_tomorrow":
        if task_date == tomorrow:
            return True, ""

    elif mode == "date_next_7_days":
        if task_date and today <= task_date <= next_7_days_date:
            return True, ""

    elif mode == "date_overdue":
        if task_date and task_date < today and status not in ("завершено", "done", "completed", "отменено", "cancelled"):
            return True, ""

    elif mode == "date_future":
        if task_date and task_date > today:
            return True, ""

    elif mode == "price_high":
        if task_price >= price_threshold:
            return True, ""

    elif mode == "price_missing":
        if task_price <= 0:
            return True, ""

    elif mode == "catalog_specific":
        try:
            selected_catalog_item_id = int(conditions.get("value"))
        except (TypeError, ValueError):
            selected_catalog_item_id = 0

        if selected_catalog_item_id:
            task_item = c.execute("""
            SELECT 1
            FROM task_items
            WHERE company_id=?
              AND task_id=?
              AND catalog_item_id=?
            LIMIT 1
            """, (
                company_id,
                entity_id,
                selected_catalog_item_id,
            )).fetchone()

            if task_item:
                return True, ""

    elif mode == "sla_today":
        if deadline_date == today:
            return True, ""

    elif mode == "sla_overdue":
        if deadline_at and deadline_at < today_dt.isoformat(timespec="minutes") and status not in ("завершено", "done", "completed", "отменено", "cancelled"):
            return True, ""

    elif mode == "sla_due_24h":
        if deadline_at and status not in ("завершено", "done", "completed", "отменено", "cancelled"):
            try:
                deadline_dt = datetime.fromisoformat(deadline_at.replace("Z", "+00:00").replace("+00:00", ""))
                if today_dt <= deadline_dt <= next_24h:
                    return True, ""
            except Exception:
                pass

    elif mode == "client_specific":
        try:
            selected_client_id = int(conditions.get("value"))
        except (TypeError, ValueError):
            selected_client_id = 0

        if client and selected_client_id and client_id == selected_client_id:
            return True, ""

    elif mode == "client_new":
        if client_task_count <= 1:
            return True, ""

    elif mode == "client_repeat":
        if client_task_count >= 2:
            return True, ""

    elif mode == "client_vip":
        client_notes = str(client["notes"] or "").lower() if client else ""
        if "vip" in client_notes or "вип" in client_notes:
            return True, ""

    elif mode == "client_has_debt":
        if client_unpaid_count > 0:
            return True, ""

    elif mode == "client_many_tasks":
        if client_task_count >= client_task_threshold:
            return True, ""

    else:
        return False, f"Условие не поддерживается: {mode}"

    return False, f"Условие не выполнено: {conditions.get('label') or mode}"


def run_automation_event(
    company_id,
    trigger_key,
    entity_type="",
    entity_id=None,
    message="",
    link="",
    only_rule_id=None,
    return_details=False,
):
    company_id = require_company_id_value(company_id)

    if not has_feature(company_id, "automation"):
        if return_details:
            return {
                "created_events": 0,
                "events": [],
            }
        return 0

    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    created_events = 0
    event_results = []

    conn = connect()
    c = conn.cursor()
    begin_locked_transaction(
        c,
        "automation_event",
        company_id,
        trigger_key,
        entity_type,
        entity_id,
    )

    rules_query = """
    SELECT *
    FROM automation_rules
    WHERE company_id=?
      AND trigger_key=?
      AND active=1
    """
    rules_params = [company_id, trigger_key]

    if only_rule_id is not None:
        rules_query += " AND id=?"
        rules_params.append(only_rule_id)

    rules_query += " ORDER BY id"
    rules = c.execute(rules_query, rules_params).fetchall()

    for rule in rules:
        condition_ok, condition_message = automation_condition_matches(
            c,
            company_id,
            rule,
            entity_type,
            entity_id,
        )

        if not condition_ok:
            skipped_message = condition_message

            if message:
                skipped_message = f"{condition_message}. Событие: {message}"

            c.execute("""
            INSERT INTO automation_events (
                company_id, rule_id, trigger_key, entity_type,
                entity_id, status, message, created_at, processed_at
            )
            VALUES (?, ?, ?, ?, ?, 'skipped', ?, ?, ?)
            """, (
                company_id,
                rule["id"],
                trigger_key,
                entity_type,
                entity_id,
                skipped_message,
                now,
                now,
            ))
            event_results.append({
                "id": c.lastrowid,
                "status": "skipped",
                "message": skipped_message,
            })
            continue

        c.execute("""
        INSERT INTO automation_events (
            company_id, rule_id, trigger_key, entity_type,
            entity_id, status, message, created_at
        )
        VALUES (?, ?, ?, ?, ?, 'pending', ?, ?)
        """, (
            company_id,
            rule["id"],
            trigger_key,
            entity_type,
            entity_id,
            message,
            now
        ))

        event_id = c.lastrowid
        handled_actions = 0
        action_failures = []
        action_successes = []

        actions = c.execute("""
        SELECT *
        FROM automation_actions
        WHERE company_id=?
          AND rule_id=?
          AND active=1
        ORDER BY sort_order, id
        """, (company_id, rule["id"])).fetchall()

        for action in actions:
            try:
                payload = json.loads(action["payload_json"] or "{}")
            except Exception:
                payload = {}

            if action["action_key"] == "notification":
                target_username = (payload.get("target_username") or rule["created_by"] or "").strip()
                notification_message = (payload.get("message") or message or "").strip()

                if target_username:
                    c.execute("""
                    INSERT INTO notifications (
                        company_id, username, title, message, link, created_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?)
                    """, (
                        company_id,
                        target_username,
                        rule["name"],
                        notification_message,
                        link,
                        now
                    ))
                    handled_actions += 1

            if action["action_key"] == "telegram_alert":
                target_username = (payload.get("target_username") or rule["created_by"] or "").strip()
                telegram_message = (payload.get("message") or message or "").strip()

                if target_username and telegram_message:
                    user_row = c.execute("""
                    SELECT telegram_chat_id
                    FROM users
                    WHERE company_id=?
                      AND username=?
                    """, (company_id, target_username)).fetchone()

                    if user_row and user_row["telegram_chat_id"]:
                        try:
                            send_message_to_chat(
                                user_row["telegram_chat_id"],
                                telegram_message
                            )
                            handled_actions += 1
                        except Exception:
                            pass

            if action["action_key"] == "ai_digest":
                target_username = (payload.get("target_username") or rule["created_by"] or "").strip()

                if target_username:
                    digest_message = build_ai_digest_message(company_id, c)

                    c.execute("""
                    INSERT INTO notifications (
                        company_id, username, title, message, link, created_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?)
                    """, (
                        company_id,
                        target_username,
                        "🤖 ИИ-сводка",
                        digest_message,
                        "/ai/insights",
                        now
                    ))

                    handled_actions += 1

                    user_row = c.execute("""
                    SELECT telegram_chat_id
                    FROM users
                    WHERE company_id=?
                      AND username=?
                    """, (company_id, target_username)).fetchone()

                    if user_row and user_row["telegram_chat_id"]:
                        try:
                            send_message_to_chat(
                                user_row["telegram_chat_id"],
                                digest_message
                            )
                        except Exception:
                            pass

            if action["action_key"] == "create_task":
                created_task_id = execute_automation_create_task_action(
                    c,
                    company_id,
                    rule,
                    action,
                    payload,
                    entity_type,
                    entity_id,
                    now,
                    action_failures,
                    action_successes,
                )

                if created_task_id:
                    handled_actions += 1

        status = "done" if handled_actions else "skipped"
        event_message = message

        if action_successes:
            success_message = " ".join(dict.fromkeys(action_successes))
            event_message = (
                f"{message}. Результат: {success_message}"
                if message
                else success_message
            )

        if action_failures:
            failure_message = " ".join(dict.fromkeys(action_failures))
            event_message = (
                f"{message}. Причина: {failure_message}"
                if message
                else failure_message
            )
            alert_username = str(rule["created_by"] or "").strip()
            alert_title = f"A3: требуется распределение — {rule['name']}"
            alert_link = f"/automation/events/{event_id}"

            if alert_username:
                existing_alert = c.execute("""
                SELECT id
                FROM notifications
                WHERE company_id=?
                  AND username=?
                  AND title=?
                  AND is_read=0
                LIMIT 1
                """, (
                    company_id,
                    alert_username,
                    alert_title,
                )).fetchone()

                if not existing_alert:
                    c.execute("""
                    INSERT INTO notifications (
                        company_id, username, title, message,
                        link, created_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?)
                    """, (
                        company_id,
                        alert_username,
                        alert_title,
                        failure_message,
                        alert_link,
                        now,
                    ))

        c.execute("""
        UPDATE automation_events
        SET status=?, message=?, processed_at=?
        WHERE id=?
          AND company_id=?
        """, (
            status,
            event_message,
            now,
            event_id,
            company_id
        ))

        created_events += 1
        event_results.append({
            "id": event_id,
            "status": status,
            "message": event_message,
        })

    conn.commit()
    conn.close()

    if return_details:
        return {
            "created_events": created_events,
            "events": event_results,
        }

    return created_events


def build_a3_event_retry_state(event, now_dt=None):
    event = dict(event or {})
    status = str(event.get("status") or "").strip()
    rule_id = event.get("rule_id")
    retry_count = max(0, int(event.get("retry_count") or 0))
    last_retried_at = str(event.get("last_retried_at") or "").strip()
    retryable_status = status in {"pending", "skipped"}
    available_at = ""
    remaining_minutes = 0

    if last_retried_at:
        try:
            retry_at = datetime.fromisoformat(last_retried_at)
            available_dt = retry_at + timedelta(
                minutes=SKIPPED_EVENT_RETRY_COOLDOWN_MINUTES,
            )
            remaining_seconds = max(
                0,
                int((available_dt - (now_dt or datetime.now())).total_seconds()),
            )
            remaining_minutes = (remaining_seconds + 59) // 60
            available_at = available_dt.isoformat(timespec="minutes")
        except (TypeError, ValueError):
            last_retried_at = ""

    available = bool(
        retryable_status
        and rule_id
        and remaining_minutes == 0
    )

    if not retryable_status:
        label = "Повтор не требуется"
    elif not rule_id:
        label = "Правило события не найдено"
    elif remaining_minutes:
        label = f"Повтор через {remaining_minutes} мин."
    else:
        label = "Можно повторить"

    return {
        "available": available,
        "label": label,
        "retry_count": retry_count,
        "last_retried_at": last_retried_at,
        "available_at": available_at,
        "remaining_minutes": remaining_minutes,
        "cooldown_minutes": SKIPPED_EVENT_RETRY_COOLDOWN_MINUTES,
    }


def replay_a3_skipped_automation_events(company_id, rule_id, events):
    result = {
        "replayed": 0,
        "not_ready": 0,
        "failed": 0,
    }

    for event in events:
        retried_at = datetime.now().isoformat(timespec="seconds")
        processed_at = datetime.now().strftime("%Y-%m-%d %H:%M")

        try:
            execution = run_automation_event(
                company_id=company_id,
                trigger_key=event.get("trigger_key") or "",
                entity_type=event.get("entity_type") or "",
                entity_id=event.get("entity_id"),
                message=event.get("message") or "Повторная проверка A3",
                link="/automation",
                only_rule_id=rule_id,
                return_details=True,
            )
        except Exception:
            try:
                conn = connect()
                c = conn.cursor()
                c.execute("""
                    UPDATE automation_events
                    SET last_retried_at=?,
                        retry_count=COALESCE(retry_count, 0) + 1
                    WHERE company_id=?
                      AND id=?
                      AND status IN ('pending', 'skipped')
                """, (
                    retried_at,
                    company_id,
                    event.get("id"),
                ))
                conn.commit()
                conn.close()
            except Exception:
                pass

            result["failed"] += 1
            continue

        execution_events = execution.get("events", [])
        successful_events = [
            item for item in execution_events
            if item.get("status") == "done"
        ]

        if not successful_events:
            conn = connect()
            c = conn.cursor()
            latest_message = next(
                (
                    item.get("message")
                    for item in reversed(execution_events)
                    if item.get("message")
                ),
                event.get("message") or "Повторная проверка A3",
            )
            c.execute("""
                UPDATE automation_events
                SET status='skipped',
                    message=?,
                    processed_at=?,
                    last_retried_at=?,
                    retry_count=COALESCE(retry_count, 0) + 1
                WHERE company_id=?
                  AND id=?
                  AND status IN ('pending', 'skipped')
            """, (
                latest_message,
                processed_at,
                retried_at,
                company_id,
                event.get("id"),
            ))

            generated_skipped_ids = [
                item.get("id")
                for item in execution_events
                if item.get("status") == "skipped" and item.get("id")
            ]
            if generated_skipped_ids:
                placeholders = ",".join("?" for _ in generated_skipped_ids)
                c.execute(
                    f"""
                    DELETE FROM automation_events
                    WHERE company_id=?
                      AND id IN ({placeholders})
                    """,
                    [company_id, *generated_skipped_ids],
                )
            conn.commit()
            conn.close()

            result["not_ready"] += 1
            continue

        conn = connect()
        c = conn.cursor()
        c.execute("""
            UPDATE automation_events
            SET status='done',
                message=message || ' | Повторно проверено A3',
                processed_at=?,
                last_retried_at=?,
                retry_count=COALESCE(retry_count, 0) + 1
            WHERE company_id=?
              AND id=?
              AND status IN ('pending', 'skipped')
        """, (
            processed_at,
            retried_at,
            company_id,
            event.get("id"),
        ))
        conn.commit()
        conn.close()
        result["replayed"] += 1

    return result


def run_ai_digest_scheduler(company_id, now_dt=None):
    company_id = require_company_id_value(company_id)

    result = {
        "daily": 0,
        "weekly": 0,
        "follow_ups": 0,
        "skipped": 0
    }

    if not has_feature(company_id, "automation") or not has_feature(company_id, "ai_insights"):
        return result

    now_dt = now_dt or datetime.now()
    today_key = now_dt.strftime("%Y-%m-%d")
    iso_year, iso_week, _ = now_dt.isocalendar()
    week_key = f"{iso_year}-W{iso_week:02d}"
    daily_message = f"Ежедневная ИИ-сводка {today_key}"

    conn = connect()
    c = conn.cursor()

    daily_rules = c.execute("""
    SELECT COUNT(*)
    FROM automation_rules
    WHERE company_id=?
      AND trigger_key='daily_digest'
      AND active=1
    """, (company_id,)).fetchone()[0]

    weekly_rules = c.execute("""
    SELECT COUNT(*)
    FROM automation_rules
    WHERE company_id=?
      AND trigger_key='weekly_digest'
      AND active=1
    """, (company_id,)).fetchone()[0]

    daily_already_sent = c.execute("""
    SELECT COUNT(*)
    FROM automation_events
    WHERE company_id=?
      AND trigger_key='daily_digest'
      AND message=?
    """, (company_id, daily_message)).fetchone()[0]

    weekly_message = f"Еженедельная ИИ-сводка {week_key}"
    weekly_already_sent = c.execute("""
    SELECT COUNT(*)
    FROM automation_events
    WHERE company_id=?
      AND trigger_key='weekly_digest'
      AND message=?
    """, (company_id, weekly_message)).fetchone()[0]

    conn.close()

    result["follow_ups"] = create_ai_follow_up_notifications_for_company(
        company_id,
        now_dt
    )

    if daily_rules and not daily_already_sent:
        result["daily"] = run_automation_event(
            company_id,
            "daily_digest",
            "company",
            company_id,
            daily_message,
            "/ai/insights"
        )
    elif daily_rules:
        result["skipped"] += 1

    if weekly_rules and not weekly_already_sent:
        result["weekly"] = run_automation_event(
            company_id,
            "weekly_digest",
            "company",
            company_id,
            weekly_message,
            "/ai/insights"
        )
    elif weekly_rules:
        result["skipped"] += 1

    return result


def run_ai_digest_scheduler_for_all_companies(now_dt=None):
    summary = {
        "companies": 0,
        "daily": 0,
        "weekly": 0,
        "follow_ups": 0,
        "skipped": 0
    }

    conn = connect()
    c = conn.cursor()

    companies = c.execute("""
    SELECT id
    FROM companies
    ORDER BY id
    """).fetchall()

    conn.close()

    for company in companies:
        result = run_ai_digest_scheduler(company["id"], now_dt)
        summary["companies"] += 1
        summary["daily"] += result["daily"]
        summary["weekly"] += result["weekly"]
        summary["follow_ups"] += result["follow_ups"]
        summary["skipped"] += result["skipped"]

    return summary


def ensure_ai_digest_automation_rules(company_id, username):
    company_id = require_company_id_value(company_id)
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    created_count = 0
    defaults = [
        ("daily_digest", "Ежедневная ИИ-сводка"),
        ("weekly_digest", "Еженедельная ИИ-сводка")
    ]

    conn = connect()
    c = conn.cursor()

    for trigger_key, name in defaults:
        existing = c.execute("""
        SELECT automation_rules.id
        FROM automation_rules
        JOIN automation_actions
          ON automation_actions.rule_id=automation_rules.id
          AND automation_actions.company_id=automation_rules.company_id
        WHERE automation_rules.company_id=?
          AND automation_rules.trigger_key=?
          AND automation_actions.action_key='ai_digest'
        LIMIT 1
        """, (company_id, trigger_key)).fetchone()

        if existing:
            continue

        c.execute("""
        INSERT INTO automation_rules (
            company_id, name, trigger_key, conditions_json,
            active, created_by, created_at, updated_at
        )
        VALUES (?, ?, ?, ?, 1, ?, ?, ?)
        """, (
            company_id,
            name,
            trigger_key,
            json.dumps({}, ensure_ascii=False),
            username,
            now,
            now
        ))

        rule_id = c.lastrowid
        payload = {
            "target_username": username,
            "message": ""
        }

        c.execute("""
        INSERT INTO automation_actions (
            company_id, rule_id, action_key, payload_json,
            sort_order, active, created_at
        )
        VALUES (?, ?, 'ai_digest', ?, 1, 1, ?)
        """, (
            company_id,
            rule_id,
            json.dumps(payload, ensure_ascii=False),
            now
        ))

        created_count += 1

    conn.commit()
    conn.close()

    return created_count


def register_pdf_font():
    font_paths = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
        "/Library/Fonts/Arial Unicode.ttf",
    ]

    for font_path in font_paths:
        if os.path.exists(font_path):
            try:
                pdfmetrics.registerFont(TTFont("CRMFont", font_path))
                return "CRMFont"
            except Exception:
                pass

    return "Helvetica"


def draw_text(pdf, text, x, y, font_name, size=10, max_chars=88, line_height=16):
    pdf.setFont(font_name, size)
    text = str(text or "")
    lines = []

    for paragraph in text.split("\n"):
        words = paragraph.split()

        if not words:
            lines.append("")
            continue

        line = ""

        for word in words:
            candidate = f"{line} {word}".strip()

            if len(candidate) <= max_chars:
                line = candidate
            else:
                lines.append(line)
                line = word

        if line:
            lines.append(line)

    for line in lines:
        if y < 70:
            pdf.showPage()
            y = 800
            pdf.setFont(font_name, size)

        pdf.drawString(x, y, line)
        y -= line_height

    return y


def draw_pdf_image(pdf, filename, title, x, y, font_name):
    if not filename:
        return y

    try:
        image_bytes = read_storage_bytes(filename, UPLOAD_DIR)
    except (ObjectStorageError, ValueError):
        image_bytes = None

    if image_bytes is None:
        return y

    if Path(filename).suffix.lower() not in PDF_IMAGE_EXTENSIONS:
        pdf.setFont(font_name, 10)
        pdf.drawString(x, y, f"{title}: файл сохранён, но формат не вставляется в PDF")
        return y - 24

    if y < 270:
        pdf.showPage()
        y = 800

    try:
        pdf.setFont(font_name, 11)
        pdf.drawString(x, y, title)
        y -= 16
        image = ImageReader(io.BytesIO(image_bytes))
        pdf.drawImage(
            image,
            x,
            y - 170,
            width=240,
            height=170,
            preserveAspectRatio=True,
            mask="auto"
        )
        y -= 200
    except Exception:
        pdf.setFont(font_name, 10)
        pdf.drawString(x, y, f"{title}: не удалось вставить изображение")
        y -= 24

    return y










def format_calendar_incident_age(age_minutes):
    if age_minutes is None:
        return "неизвестно"

    age_minutes = max(0, int(age_minutes))

    if age_minutes < 60:
        return f"{age_minutes} мин"

    hours, minutes = divmod(age_minutes, 60)

    if hours < 24:
        return (
            f"{hours} ч {minutes} мин"
            if minutes
            else f"{hours} ч"
        )

    days, remaining_hours = divmod(hours, 24)
    return (
        f"{days} д {remaining_hours} ч"
        if remaining_hours
        else f"{days} д"
    )


def build_calendar_incident_sla_deadline(
    active_incident,
    is_acknowledged,
    incident_age_minutes,
    recovery_age_minutes,
    response_target_minutes,
    recovery_target_minutes,
):
    if not active_incident:
        return {
            "label": "",
            "tone": "",
        }

    if is_acknowledged:
        if recovery_age_minutes is None:
            return {
                "label": "Срок восстановления неизвестен",
                "tone": "waiting",
            }

        remaining_minutes = (
            int(recovery_target_minutes) - int(recovery_age_minutes)
        )
        if remaining_minutes >= 0:
            return {
                "label": (
                    "Восстановление через "
                    f"{format_calendar_incident_age(remaining_minutes)}"
                ),
                "tone": "waiting",
            }

        return {
            "label": (
                "Восстановление просрочено на "
                f"{format_calendar_incident_age(abs(remaining_minutes))}"
            ),
            "tone": "error",
        }

    if incident_age_minutes is None:
        return {
            "label": "Срок реакции неизвестен",
            "tone": "waiting",
        }

    remaining_minutes = (
        int(response_target_minutes) - int(incident_age_minutes)
    )
    if remaining_minutes >= 0:
        return {
            "label": (
                "Реакция через "
                f"{format_calendar_incident_age(remaining_minutes)}"
            ),
            "tone": "waiting",
        }

    return {
        "label": (
            "Реакция просрочена на "
            f"{format_calendar_incident_age(abs(remaining_minutes))}"
        ),
        "tone": "error",
    }


def get_bounded_environment_int(
    name,
    default,
    minimum,
    maximum,
):
    raw_value = str(os.getenv(name) or "").strip()

    try:
        value = int(raw_value) if raw_value else int(default)
    except ValueError:
        value = int(default)

    return max(minimum, min(value, maximum))


def make_production_config_item(
    key,
    title,
    status,
    value,
    description,
    action,
):
    labels = {
        "ok": "Готово",
        "warning": "Внимание",
        "critical": "Критично",
    }
    normalized_status = status if status in labels else "warning"

    return {
        "key": key,
        "title": title,
        "status": normalized_status,
        "status_label": labels[normalized_status],
        "value": value,
        "description": description,
        "action": action,
    }


def get_production_config_status():
    env_name = (os.getenv("ENV") or "development").strip()
    railway_environment = bool((os.getenv("RAILWAY_ENVIRONMENT") or "").strip())
    production_mode = env_name == "production" or railway_environment
    bot_token_configured = bool((os.getenv("BOT_TOKEN") or "").strip())
    chat_id_configured = bool((os.getenv("CHAT_ID") or "").strip())
    telegram_configured = bot_token_configured and chat_id_configured
    cron_secret_configured = bool(
        (os.getenv("AUTOMATION_CRON_SECRET") or "").strip()
    )
    security_config = get_security_runtime_config()
    secret_is_default = SECRET_KEY == "dev-secret-change-me"
    secret_is_weak = secret_is_default or len(SECRET_KEY) < 32
    data_dir_exists = DATA_DIR.exists()
    uploads_exists = UPLOAD_DIR.exists()
    data_dir_writable = data_dir_exists and os.access(DATA_DIR, os.W_OK)
    uploads_writable = uploads_exists and os.access(UPLOAD_DIR, os.W_OK)
    object_storage_status = get_object_storage_status(UPLOAD_DIR)
    object_storage_config = object_storage_status["configuration"]
    storage_ready = data_dir_writable and object_storage_status["ok"]
    storage_config_status = (
        "critical"
        if not storage_ready
        else (
            "warning"
            if production_mode
            and object_storage_status["backend"] == "local"
            else "ok"
        )
    )
    database_runtime = get_database_runtime_config()
    database_production_ready = (
        database_runtime["active_backend"] == "postgresql"
        and database_runtime["postgresql_ready"]
    )
    database_config_status = (
        "critical"
        if not database_runtime["configuration_valid"]
        or (production_mode and not database_production_ready)
        else "ok" if database_production_ready else "warning"
    )

    items = [
        make_production_config_item(
            "environment",
            "Режим приложения",
            "ok" if production_mode else "warning",
            "боевой" if production_mode else env_name,
            (
                "Приложение запущено в боевом окружении."
                if production_mode
                else "Сейчас приложение работает не в боевом режиме."
            ),
            "Для релиза используйте ENV=production или Railway окружение.",
        ),
        make_production_config_item(
            "database_backend",
            "База данных production",
            database_config_status,
            database_runtime["configured_backend_label"],
            (
                "Конфигурация базы содержит несовместимые параметры."
                if not database_runtime["configuration_valid"]
                else (
                    "PostgreSQL готов к production."
                    if database_production_ready
                    else (
                        "SQLite остаётся активной базой на этапе миграции. "
                        "Для локальной разработки это допустимо."
                    )
                )
            ),
            (
                "Устраните конфликт DATABASE_BACKEND и DATABASE_URL."
                if not database_runtime["configuration_valid"]
                else (
                    "Проверьте миграцию и restore drill на отдельной "
                    "PostgreSQL базе перед production cutover."
                )
            ),
        ),
        make_production_config_item(
            "secret_key",
            "Секрет приложения",
            "critical" if secret_is_weak else "ok",
            "слабый" if secret_is_weak else "задан",
            (
                "SECRET_KEY отсутствует или короче 32 символов."
                if secret_is_weak
                else "Секрет приложения задан через окружение."
            ),
            "Перед боевым запуском задайте SECRET_KEY длиной от 32 символов.",
        ),
        make_production_config_item(
            "trusted_hosts",
            "Разрешённые домены",
            (
                "ok"
                if security_config["trusted_hosts_configured"]
                else "critical" if production_mode else "warning"
            ),
            (
                ", ".join(security_config["trusted_hosts"])
                if security_config["trusted_hosts"]
                else "не заданы"
            ),
            (
                "Host-заголовок ограничен списком production-доменов."
                if security_config["trusted_hosts_configured"]
                else "В development разрешены все Host-заголовки."
            ),
            "Задайте TRUSTED_HOSTS или APP_BASE_URL перед релизом.",
        ),
        make_production_config_item(
            "request_security",
            "Защита HTTP-запросов",
            "ok",
            "включена",
            (
                "Межсайтовые изменения, слишком большие запросы и "
                "небезопасные browser origins блокируются middleware."
            ),
            "Проверяйте security smoke после изменения proxy или домена.",
        ),
        make_production_config_item(
            "secure_cookie",
            "Защита cookie",
            "ok" if COOKIE_SECURE else "warning",
            "включена" if COOKIE_SECURE else "выключена",
            (
                "Cookie сессии защищены для HTTPS."
                if COOKIE_SECURE
                else "Cookie сессии не ограничены HTTPS."
            ),
            "Для боевого режима включите COOKIE_SECURE или Railway окружение.",
        ),
        make_production_config_item(
            "telegram",
            "Telegram уведомления",
            "ok" if telegram_configured else "warning",
            "настроены" if telegram_configured else "не настроены",
            (
                "BOT_TOKEN и CHAT_ID заданы."
                if telegram_configured
                else "BOT_TOKEN или CHAT_ID не заданы."
            ),
            "Добавьте Telegram переменные окружения.",
        ),
        make_production_config_item(
            "automation_cron_secret",
            "Фоновые запуски",
            "ok" if cron_secret_configured else "warning",
            "секрет задан" if cron_secret_configured else "секрет не задан",
            (
                "Фоновые автоматизации защищены отдельным секретом."
                if cron_secret_configured
                else "Фоновые автоматизации нельзя безопасно запускать извне."
            ),
            "Укажите AUTOMATION_CRON_SECRET для расписаний и дайджестов.",
        ),
        make_production_config_item(
            "storage",
            "Файловое хранилище",
            storage_config_status,
            object_storage_status["backend_label"],
            (
                "S3-совместимое хранилище доступно."
                if object_storage_status["backend"] == "s3"
                and storage_ready
                else (
                    "Локальное хранилище доступно; для production нужен "
                    "постоянный диск или S3."
                    if storage_ready
                    else object_storage_status["message"]
                )
            ),
            (
                "Настройте OBJECT_STORAGE_BACKEND=s3 и S3_BUCKET."
                if object_storage_status["backend"] == "local"
                else "Проверьте S3 bucket, endpoint и права приложения."
            ),
        ),
    ]
    critical_count = sum(1 for item in items if item["status"] == "critical")
    warning_count = sum(1 for item in items if item["status"] == "warning")

    if critical_count:
        status = "critical"
        status_label = "Есть критичные настройки"
        summary = "Перед релизом нужно закрыть критичные настройки окружения."
    elif warning_count:
        status = "warning"
        status_label = "Нужна настройка"
        summary = "Критичных проблем нет, но часть настроек стоит добить."
    else:
        status = "ok"
        status_label = "Готово"
        summary = "Ключевые настройки окружения готовы к работе."

    return {
        "environment": env_name,
        "railway_environment": railway_environment,
        "production_mode": production_mode,
        "cookie_secure": COOKIE_SECURE,
        "secret_is_default": secret_is_default,
        "secret_is_weak": secret_is_weak,
        "security_config": security_config,
        "bot_token_configured": bot_token_configured,
        "chat_id_configured": chat_id_configured,
        "telegram_configured": telegram_configured,
        "automation_cron_secret_configured": cron_secret_configured,
        "data_dir_writable": data_dir_writable,
        "uploads_writable": uploads_writable,
        "storage_ready": storage_ready,
        "object_storage_status": object_storage_status,
        "object_storage_config": object_storage_config,
        "database_runtime": database_runtime,
        "database_production_ready": database_production_ready,
        "items": items,
        "status": status,
        "status_label": status_label,
        "summary": summary,
        "critical_count": critical_count,
        "warning_count": warning_count,
    }


def get_calendar_incident_policy(
    response_minutes=None,
    escalation_minutes=None,
    recovery_minutes=None,
    stale_hours=None,
    stuck_minutes=None,
):
    response_minutes = (
        get_bounded_environment_int(
            "CALENDAR_INCIDENT_RESPONSE_MINUTES",
            30,
            5,
            240,
        )
        if response_minutes is None
        else max(5, min(int(response_minutes), 240))
    )
    escalation_minutes = (
        get_bounded_environment_int(
            "CALENDAR_INCIDENT_ESCALATION_MINUTES",
            30,
            5,
            1440,
        )
        if escalation_minutes is None
        else max(5, min(int(escalation_minutes), 1440))
    )
    recovery_minutes = (
        get_bounded_environment_int(
            "CALENDAR_INCIDENT_RECOVERY_MINUTES",
            120,
            15,
            2880,
        )
        if recovery_minutes is None
        else max(15, min(int(recovery_minutes), 2880))
    )

    return {
        "response_minutes": response_minutes,
        "escalation_minutes": max(
            response_minutes,
            escalation_minutes,
        ),
        "recovery_minutes": max(
            response_minutes,
            recovery_minutes,
        ),
        "stale_hours": (
            get_bounded_environment_int(
                "CALENDAR_WATCHDOG_STALE_HOURS",
                6,
                1,
                72,
            )
            if stale_hours is None
            else max(1, min(int(stale_hours), 72))
        ),
        "stuck_minutes": (
            get_bounded_environment_int(
                "CALENDAR_SCHEDULER_STUCK_MINUTES",
                30,
                5,
                240,
            )
            if stuck_minutes is None
            else max(5, min(int(stuck_minutes), 240))
        ),
    }


def get_calendar_incident_priority(
    status_code,
    active_incident,
    is_acknowledged,
    incident_age_minutes,
    response_target_minutes=None,
    recovery_overdue=False,
):
    if response_target_minutes is None:
        response_target_minutes = get_calendar_incident_policy()[
            "response_minutes"
        ]

    has_incident = bool(active_incident)
    response_overdue = bool(
        has_incident
        and not is_acknowledged
        and incident_age_minutes is not None
        and incident_age_minutes >= response_target_minutes
    )

    if has_incident and is_acknowledged and recovery_overdue:
        return {
            "code": "critical",
            "label": "Критический",
            "rank": 0,
            "response_overdue": False,
            "recovery_overdue": True,
        }

    if (
        has_incident
        and not is_acknowledged
        and (
            status_code in {"error", "stuck"}
            or response_overdue
        )
    ):
        return {
            "code": "critical",
            "label": "Критический",
            "rank": 0,
            "response_overdue": response_overdue,
            "recovery_overdue": False,
        }

    if has_incident and not is_acknowledged:
        return {
            "code": "high",
            "label": "Высокий",
            "rank": 1,
            "response_overdue": response_overdue,
            "recovery_overdue": False,
        }

    if has_incident and is_acknowledged:
        return {
            "code": "medium",
            "label": "В работе",
            "rank": 2,
            "response_overdue": False,
            "recovery_overdue": False,
        }

    if status_code in {"error", "stuck"}:
        return {
            "code": "high",
            "label": "Высокий",
            "rank": 1,
            "response_overdue": False,
            "recovery_overdue": False,
        }

    if status_code == "stale":
        return {
            "code": "medium",
            "label": "Проверить",
            "rank": 2,
            "response_overdue": False,
            "recovery_overdue": False,
        }

    return {
        "code": "normal",
        "label": "Штатный",
        "rank": 3,
        "response_overdue": False,
        "recovery_overdue": False,
    }


def parse_calendar_incident_datetime(value):
    try:
        return datetime.strptime(
            str(value or ""),
            "%Y-%m-%d %H:%M",
        )
    except ValueError:
        return None


def build_calendar_incident_sessions(
    events,
    now_dt=None,
    response_target_minutes=None,
    recovery_target_minutes=None,
):
    now_dt = now_dt or datetime.now()
    policy = get_calendar_incident_policy(
        response_minutes=response_target_minutes,
        recovery_minutes=recovery_target_minutes,
    )
    response_target_minutes = policy["response_minutes"]
    recovery_target_minutes = policy["recovery_minutes"]
    sessions = []
    active_by_company = {}

    for raw_event in sorted(
        (dict(event) for event in events),
        key=lambda event: (
            str(event.get("created_at") or ""),
            int(event.get("id") or 0),
        ),
    ):
        company_id = int(raw_event.get("company_id") or 0)
        event_type = str(raw_event.get("event_type") or "")
        event_at = parse_calendar_incident_datetime(
            raw_event.get("created_at"),
        )

        if event_type == "opened":
            session = {
                "company_id": company_id,
                "company_name": str(
                    raw_event.get("company_name")
                    or f"Компания #{company_id}"
                ),
                "incident_type": str(
                    raw_event.get("incident_type") or "error"
                ),
                "message": str(raw_event.get("message") or ""),
                "opened_at": event_at,
                "opened_at_value": str(
                    raw_event.get("created_at") or ""
                ),
                "acknowledged_at": None,
                "acknowledged_at_value": "",
                "acknowledged_by": "",
                "recovered_at": None,
                "recovered_at_value": "",
                "recovered_by": "",
                "recovery_attempts": 0,
                "recovery_failures": 0,
                "recovery_overdue_events": 0,
                "escalations": 0,
                "escalated_at": None,
                "escalated_at_value": "",
            }
            sessions.append(session)
            active_by_company[company_id] = session
            continue

        session = active_by_company.get(company_id)

        if not session:
            continue

        if (
            event_type == "acknowledged"
            and not session["acknowledged_at"]
        ):
            session["acknowledged_at"] = event_at
            session["acknowledged_at_value"] = str(
                raw_event.get("created_at") or ""
            )
            session["acknowledged_by"] = str(
                raw_event.get("actor_username") or ""
            )
        elif event_type == "recovery_started":
            session["recovery_attempts"] += 1
        elif event_type == "recovery_failed":
            session["recovery_failures"] += 1
        elif event_type == "recovery_overdue":
            session["recovery_overdue_events"] += 1
        elif event_type == "escalated":
            session["escalations"] += 1
            session["escalated_at"] = event_at
            session["escalated_at_value"] = str(
                raw_event.get("created_at") or ""
            )
        elif event_type == "recovered":
            session["recovered_at"] = event_at
            session["recovered_at_value"] = str(
                raw_event.get("created_at") or ""
            )
            session["recovered_by"] = str(
                raw_event.get("actor_username") or ""
            )
            active_by_company.pop(company_id, None)

    incident_type_labels = {
        "error": "Ошибка запуска",
        "stuck": "Зависший запуск",
        "stale": "Планировщик не запускался",
    }

    for session in sessions:
        opened_at = session["opened_at"]
        acknowledged_at = session["acknowledged_at"]
        recovered_at = session["recovered_at"]
        response_minutes = None
        recovery_minutes = None
        recovery_work_minutes = None

        if opened_at and acknowledged_at:
            response_minutes = max(
                0,
                int(
                    (acknowledged_at - opened_at).total_seconds()
                    // 60
                ),
            )

        if acknowledged_at and recovered_at:
            recovery_minutes = max(
                0,
                int(
                    (recovered_at - acknowledged_at).total_seconds()
                    // 60
                ),
            )
        elif acknowledged_at:
            recovery_work_minutes = max(
                0,
                int(
                    (now_dt - acknowledged_at).total_seconds()
                    // 60
                ),
            )

        if recovery_minutes is not None:
            recovery_work_minutes = recovery_minutes

        session["response_minutes"] = response_minutes
        session["response_label"] = (
            format_calendar_incident_age(response_minutes)
            if response_minutes is not None
            else "Не принят"
        )
        session["recovery_minutes"] = recovery_minutes
        session["recovery_label"] = (
            format_calendar_incident_age(recovery_minutes)
            if recovery_minutes is not None
            else "Не восстановлен"
        )
        session["recovery_work_minutes"] = recovery_work_minutes
        session["recovery_work_label"] = (
            format_calendar_incident_age(recovery_work_minutes)
            if recovery_work_minutes is not None
            else "Не принят"
        )
        session["age_minutes"] = (
            max(
                0,
                int((now_dt - opened_at).total_seconds() // 60),
            )
            if opened_at
            else None
        )
        session["age_label"] = format_calendar_incident_age(
            session["age_minutes"],
        )
        session["is_recovered"] = bool(recovered_at)
        session["is_active"] = not session["is_recovered"]
        session["response_sla_met"] = bool(
            response_minutes is not None
            and response_minutes <= response_target_minutes
        )
        session["response_overdue"] = bool(
            (
                response_minutes is not None
                and response_minutes > response_target_minutes
            )
            or (
                not acknowledged_at
                and session["age_minutes"] is not None
                and session["age_minutes"] >= response_target_minutes
            )
        )
        session["recovery_sla_met"] = bool(
            recovery_minutes is not None
            and recovery_minutes <= recovery_target_minutes
        )
        session["recovery_overdue"] = bool(
            acknowledged_at
            and not recovered_at
            and recovery_work_minutes is not None
            and recovery_work_minutes >= recovery_target_minutes
        )
        session["incident_type_label"] = (
            incident_type_labels.get(
                session["incident_type"],
                "Инцидент",
            )
        )
        session["status_label"] = (
            "Восстановлен"
            if session["is_recovered"]
            else (
                "Восстановление просрочено"
                if session["recovery_overdue"]
                else (
                    "Принят в работу"
                    if acknowledged_at
                    else (
                        "Передан платформе"
                        if session["escalations"]
                        else "Ожидает реакции"
                    )
                )
            )
        )
        session["status_tone"] = (
            "healthy"
            if session["is_recovered"]
            else (
                "error"
                if session["recovery_overdue"]
                else ("waiting" if acknowledged_at else "error")
            )
        )

    return sessions


def get_calendar_company_risk_main_factor(company):
    factors = [
        (
            int(company.get("response_overdue_percent") or 0),
            (
                "Просроченная реакция: "
                f"{company.get('response_overdue_percent') or 0}%"
            ),
        ),
        (
            int(company.get("recovery_overdue") or 0) * 25,
            (
                "Просроченное восстановление: "
                f"{company.get('recovery_overdue') or 0}"
            ),
        ),
        (
            int(company.get("active") or 0) * 20,
            f"Активные инциденты: {company.get('active') or 0}",
        ),
        (
            int(company.get("escalations") or 0) * 15,
            f"Эскалации: {company.get('escalations') or 0}",
        ),
    ]
    active_factors = [
        item for item in factors if item[0] > 0
    ]

    if not active_factors:
        return "Серьёзных факторов риска не найдено."

    return max(active_factors, key=lambda item: item[0])[1]


def get_calendar_company_risk_trend(company):
    recent_pressure = (
        int(company.get("recent_incidents") or 0)
        + int(company.get("recent_response_overdue") or 0) * 2
    )
    previous_pressure = (
        int(company.get("previous_incidents") or 0)
        + int(company.get("previous_response_overdue") or 0) * 2
    )
    total_compared = recent_pressure + previous_pressure

    if total_compared <= 1:
        return {
            "label": "Мало данных",
            "tone": "waiting",
            "delta": recent_pressure - previous_pressure,
        }

    delta = recent_pressure - previous_pressure

    if delta >= 2:
        return {
            "label": "Риск растёт",
            "tone": "error",
            "delta": delta,
        }

    if delta <= -2:
        return {
            "label": "Риск снижается",
            "tone": "healthy",
            "delta": delta,
        }

    return {
        "label": "Стабильно",
        "tone": "waiting",
        "delta": delta,
    }


def build_calendar_company_risk_summary(company):
    return (
        f"Риск: {company.get('risk_label', 'Низкий')} "
        f"({company.get('risk_score', 0)}/100). "
        f"Динамика: {company.get('risk_trend_label', 'Мало данных')}. "
        f"Причина: {company.get('risk_main_factor', 'нет данных')}. "
        f"Следующий шаг: {company.get('risk_next_action', 'наблюдать')}."
    )


def get_platform_calendar_incident_analytics(
    days=30,
    now_dt=None,
    response_target_minutes=None,
    recovery_target_minutes=None,
):
    now_dt = now_dt or datetime.now()
    policy = get_calendar_incident_policy(
        response_minutes=response_target_minutes,
        recovery_minutes=recovery_target_minutes,
    )
    response_target_minutes = policy["response_minutes"]
    recovery_target_minutes = policy["recovery_minutes"]
    selected_days = days if days in {7, 30, 90} else 30
    date_from = (
        now_dt.date() - timedelta(days=selected_days - 1)
    ).strftime("%Y-%m-%d")
    trend_cutoff = now_dt.date() - timedelta(
        days=max(1, selected_days // 2) - 1,
    )
    conn = connect()
    c = conn.cursor()
    event_rows = c.execute("""
    SELECT
        events.*,
        COALESCE(
            companies.name,
            settings.company_name,
            'Компания #' || events.company_id
        ) AS company_name
    FROM calendar_scheduler_incident_events AS events
    LEFT JOIN companies
      ON companies.id=events.company_id
    LEFT JOIN company_settings AS settings
      ON settings.company_id=events.company_id
    WHERE events.created_at>=?
    ORDER BY events.created_at, events.id
    """, (f"{date_from} 00:00",)).fetchall()
    conn.close()
    sessions = build_calendar_incident_sessions(
        event_rows,
        now_dt=now_dt,
        response_target_minutes=response_target_minutes,
        recovery_target_minutes=recovery_target_minutes,
    )
    recovered = [
        item for item in sessions if item["is_recovered"]
    ]
    active = [
        item for item in sessions if item["is_active"]
    ]
    responded = [
        item
        for item in sessions
        if item["response_minutes"] is not None
    ]
    response_eligible = [
        item
        for item in sessions
        if (
            item["response_minutes"] is not None
            or item["is_recovered"]
            or int(item["age_minutes"] or 0)
            >= response_target_minutes
        )
    ]
    response_sla_met = sum(
        1 for item in response_eligible if item["response_sla_met"]
    )
    response_sla_percent = round(
        response_sla_met * 100 / len(response_eligible),
    ) if response_eligible else 100
    recovery_eligible = [
        item
        for item in sessions
        if (
            item["acknowledged_at"]
            and (
                item["is_recovered"]
                or int(item["recovery_work_minutes"] or 0)
                >= recovery_target_minutes
            )
        )
    ]
    recovery_sla_met = sum(
        1 for item in recovery_eligible if item["recovery_sla_met"]
    )
    recovery_sla_percent = round(
        recovery_sla_met * 100 / len(recovery_eligible),
    ) if recovery_eligible else 100
    recovery_rate = round(
        len(recovered) * 100 / len(sessions),
    ) if sessions else 100
    average_response_minutes = round(
        sum(item["response_minutes"] for item in responded)
        / len(responded),
    ) if responded else 0
    average_recovery_minutes = round(
        sum(item["recovery_minutes"] for item in recovered)
        / len(recovered),
    ) if recovered else 0
    company_map = {}
    type_map = {
        incident_type: {
            "type": incident_type,
            "label": label,
            "incidents": 0,
            "recovered": 0,
            "active": 0,
            "response_overdue": 0,
        }
        for incident_type, label in (
            ("error", "Ошибки запуска"),
            ("stuck", "Зависшие запуски"),
            ("stale", "Пропуски расписания"),
        )
    }
    daily_map = {}

    for session in sessions:
        company = company_map.setdefault(
            session["company_id"],
            {
                "company_id": session["company_id"],
                "company_name": session["company_name"],
                "incidents": 0,
                "recovered": 0,
                "active": 0,
                "response_minutes": [],
                "recovery_minutes": [],
                "escalations": 0,
                "response_overdue": 0,
                "recovery_overdue": 0,
                "recent_incidents": 0,
                "previous_incidents": 0,
                "recent_response_overdue": 0,
                "previous_response_overdue": 0,
            },
        )
        company["incidents"] += 1
        company["recovered"] += int(session["is_recovered"])
        company["active"] += int(session["is_active"])
        company["escalations"] += int(session["escalations"] or 0)
        company["response_overdue"] += int(
            session["response_overdue"]
        )
        company["recovery_overdue"] += int(
            session["recovery_overdue"]
        )

        if session["response_minutes"] is not None:
            company["response_minutes"].append(
                session["response_minutes"],
            )

        if session["recovery_minutes"] is not None:
            company["recovery_minutes"].append(
                session["recovery_minutes"],
            )

        incident_type = type_map.setdefault(
            session["incident_type"],
            {
                "type": session["incident_type"],
                "label": session["incident_type_label"],
                "incidents": 0,
                "recovered": 0,
                "active": 0,
                "response_overdue": 0,
            },
        )
        incident_type["incidents"] += 1
        incident_type["recovered"] += int(session["is_recovered"])
        incident_type["active"] += int(session["is_active"])
        incident_type["response_overdue"] += int(
            session["response_overdue"]
        )
        opened_date = (
            session["opened_at"].strftime("%Y-%m-%d")
            if session["opened_at"]
            else ""
        )
        opened_day = session["opened_at"].date() if session["opened_at"] else None

        if opened_day and opened_day >= trend_cutoff:
            company["recent_incidents"] += 1
            company["recent_response_overdue"] += int(
                session["response_overdue"]
            )
        else:
            company["previous_incidents"] += 1
            company["previous_response_overdue"] += int(
                session["response_overdue"]
            )

        if opened_date:
            day = daily_map.setdefault(
                opened_date,
                {
                    "date": opened_date,
                    "incidents": 0,
                    "recovered": 0,
                    "active": 0,
                    "response_overdue": 0,
                },
            )
            day["incidents"] += 1
            day["recovered"] += int(session["is_recovered"])
            day["active"] += int(session["is_active"])
            day["response_overdue"] += int(session["response_overdue"])

    companies = []

    for company in company_map.values():
        response_values = company.pop("response_minutes")
        recovery_values = company.pop("recovery_minutes")
        company["average_response_minutes"] = (
            round(sum(response_values) / len(response_values))
            if response_values
            else 0
        )
        company["average_response_label"] = (
            format_calendar_incident_age(
                company["average_response_minutes"],
            )
            if response_values
            else "Нет данных"
        )
        company["average_recovery_minutes"] = (
            round(sum(recovery_values) / len(recovery_values))
            if recovery_values
            else 0
        )
        company["average_recovery_label"] = (
            format_calendar_incident_age(
                company["average_recovery_minutes"],
            )
            if recovery_values
            else "Нет данных"
        )
        company["response_overdue_percent"] = (
            round(company["response_overdue"] * 100 / company["incidents"])
            if company["incidents"]
            else 0
        )
        company["risk_score"] = min(
            100,
            company["response_overdue_percent"]
            + company["active"] * 20
            + company["escalations"] * 15
            + company["recovery_overdue"] * 25,
        )
        if company["risk_score"] >= 80:
            company["risk_label"] = "Высокий"
            company["risk_tone"] = "error"
        elif company["risk_score"] >= 40:
            company["risk_label"] = "Средний"
            company["risk_tone"] = "waiting"
        else:
            company["risk_label"] = "Низкий"
            company["risk_tone"] = "healthy"
        company["risk_main_factor"] = (
            get_calendar_company_risk_main_factor(company)
        )
        risk_trend = get_calendar_company_risk_trend(company)
        company["risk_trend_label"] = risk_trend["label"]
        company["risk_trend_tone"] = risk_trend["tone"]
        company["risk_trend_delta"] = risk_trend["delta"]
        company["detail_url"] = (
            f"/platform/calendar-health/{company['company_id']}"
        )
        companies.append(company)

    companies.sort(
        key=lambda item: (
            -item["risk_score"],
            -item["response_overdue"],
            -item["active"],
            -item["incidents"],
            item["company_name"].lower(),
        )
    )
    type_rows = [
        item
        for item in type_map.values()
        if item["incidents"]
    ]
    type_rows.sort(
        key=lambda item: (-item["incidents"], item["label"])
    )
    daily = sorted(
        daily_map.values(),
        key=lambda item: item["date"],
        reverse=True,
    )
    max_daily_incidents = max(
        (item["incidents"] for item in daily),
        default=1,
    )

    for day in daily:
        day["bar_percent"] = max(
            8,
            round(day["incidents"] * 100 / max_daily_incidents),
        )
        day["risk_score"] = min(
            100,
            day["response_overdue"] * 35
            + day["active"] * 20
            + day["incidents"] * 5,
        )
        if day["risk_score"] >= 80:
            day["risk_label"] = "Высокий"
        elif day["risk_score"] >= 40:
            day["risk_label"] = "Средний"
        else:
            day["risk_label"] = "Низкий"

    sessions.sort(
        key=lambda item: item["opened_at_value"],
        reverse=True,
    )
    high_risk_companies = [
        company for company in companies if company["risk_score"] >= 80
    ]
    medium_risk_companies = [
        company
        for company in companies
        if 40 <= company["risk_score"] < 80
    ]
    top_risk_company = companies[0] if companies else None
    high_risk_days = [
        day for day in daily if day["risk_score"] >= 80
    ]
    medium_risk_days = [
        day for day in daily if 40 <= day["risk_score"] < 80
    ]
    top_risk_day = max(
        daily,
        key=lambda day: day["risk_score"],
        default=None,
    )
    summary = {
        "incidents": len(sessions),
        "recovered": len(recovered),
        "active": len(active),
        "recovery_rate": recovery_rate,
        "response_sla_percent": response_sla_percent,
        "recovery_sla_percent": recovery_sla_percent,
        "average_response_minutes": average_response_minutes,
        "average_response_label": (
            format_calendar_incident_age(average_response_minutes)
            if responded
            else "Нет данных"
        ),
        "average_recovery_minutes": average_recovery_minutes,
        "average_recovery_label": (
            format_calendar_incident_age(average_recovery_minutes)
            if recovered
            else "Нет данных"
        ),
        "recovery_attempts": sum(
            item["recovery_attempts"] for item in sessions
        ),
        "recovery_failures": sum(
            item["recovery_failures"] for item in sessions
        ),
        "response_overdue": sum(
            1 for item in sessions if item["response_overdue"]
        ),
        "recovery_overdue": sum(
            1 for item in sessions if item["recovery_overdue"]
        ),
        "recovery_overdue_events": sum(
            item["recovery_overdue_events"] for item in sessions
        ),
        "escalations": sum(
            item["escalations"] for item in sessions
        ),
        "high_risk_companies": len(high_risk_companies),
        "medium_risk_companies": len(medium_risk_companies),
        "top_risk_company_name": (
            top_risk_company["company_name"]
            if top_risk_company
            else ""
        ),
        "top_risk_company_score": (
            top_risk_company["risk_score"]
            if top_risk_company
            else 0
        ),
        "top_risk_company_url": (
            top_risk_company["detail_url"]
            if top_risk_company
            else ""
        ),
        "high_risk_days": len(high_risk_days),
        "medium_risk_days": len(medium_risk_days),
        "top_risk_day": (
            top_risk_day["date"]
            if top_risk_day
            else ""
        ),
        "top_risk_day_score": (
            top_risk_day["risk_score"]
            if top_risk_day
            else 0
        ),
    }
    recommendations = []

    if summary["high_risk_companies"]:
        recommendations.append({
            "tone": "error",
            "title": "Разберите компании высокого риска",
            "description": (
                f"Компаний высокого риска: "
                f"{summary['high_risk_companies']}. "
                f"Начните с {summary['top_risk_company_name']}."
            ),
            "url": (
                top_risk_company["detail_url"]
                if top_risk_company
                else "/platform/calendar-health/analytics"
            ),
        })

    if summary["active"]:
        recommendations.append({
            "tone": "error",
            "title": "Разберите активные инциденты",
            "description": (
                f"Сейчас открыто {summary['active']} инцидентов. "
                "Начните с компаний в верхней части списка."
            ),
            "url": "/platform/calendar-health?status=problem",
        })

    if summary["recovery_overdue"]:
        recommendations.append({
            "tone": "error",
            "title": "Ускорьте восстановление",
            "description": (
                "Есть инциденты, где срок восстановления уже превышен. "
                "Передайте их ответственным администраторам."
            ),
            "url": "/platform/calendar-health?status=recovery_overdue",
        })

    if summary["response_overdue"]:
        recommendations.append({
            "tone": "warning",
            "title": "Ускорьте реакцию",
            "description": (
                f"За период нарушений реакции: "
                f"{summary['response_overdue']}. Проверьте очередь "
                "непринятых инцидентов и ответственных."
            ),
            "url": "/platform/calendar-health?status=response_overdue",
        })

    if summary["response_sla_percent"] < 90:
        recommendations.append({
            "tone": "warning",
            "title": "Проверьте скорость реакции",
            "description": (
                "SLA реакции ниже 90%. Непринятые инциденты нужно "
                "быстрее брать в работу."
            ),
            "url": (
                "/platform/calendar-health?"
                "status=unacknowledged&assignee=unassigned"
            ),
        })

    if summary["recovery_failures"]:
        recommendations.append({
            "tone": "warning",
            "title": "Разберите ошибки восстановления",
            "description": (
                f"За период было ошибок восстановления: "
                f"{summary['recovery_failures']}. Проверьте журналы "
                "компаний с повторными сбоями."
            ),
            "url": "/platform/calendar-health/analytics",
        })

    if summary["escalations"]:
        recommendations.append({
            "tone": "warning",
            "title": "Снизьте количество эскалаций",
            "description": (
                f"Эскалаций за период: {summary['escalations']}. "
                "Это сигнал, что часть инцидентов слишком долго "
                "остаётся без реакции."
            ),
            "url": "/platform/calendar-health?status=critical",
        })

    if not recommendations:
        recommendations.append({
            "tone": "healthy",
            "title": "Календарные автоматизации стабильны",
            "description": (
                "Критичных сигналов за выбранный период нет. "
                "Продолжайте следить за динамикой."
            ),
            "url": "/platform/calendar-health",
        })

    return {
        "days": selected_days,
        "date_from": date_from,
        "date_to": now_dt.strftime("%Y-%m-%d"),
        "generated_at": now_dt.strftime("%Y-%m-%d %H:%M"),
        "summary": summary,
        "companies": companies,
        "types": type_rows,
        "daily": daily,
        "recent_sessions": sessions[:20],
        "recommendations": recommendations[:5],
        "policy": policy,
    }


def get_platform_calendar_health(
    now_dt=None,
    status_filter="all",
    assignee_filter="all",
    current_username="",
    stale_after_hours=None,
    response_target_minutes=None,
    recovery_target_minutes=None,
    stuck_after_minutes=None,
):
    now_dt = now_dt or datetime.now()
    policy = get_calendar_incident_policy(
        response_minutes=response_target_minutes,
        recovery_minutes=recovery_target_minutes,
        stale_hours=stale_after_hours,
        stuck_minutes=stuck_after_minutes,
    )
    stale_after_hours = policy["stale_hours"]
    response_target_minutes = policy["response_minutes"]
    recovery_target_minutes = policy["recovery_minutes"]
    stuck_after_minutes = policy["stuck_minutes"]
    status_filter = (
        status_filter
        if status_filter in {
            "all",
            "problem",
            "healthy",
            "waiting",
            "disabled",
            "unacknowledged",
            "response_overdue",
            "recovery_overdue",
            "critical",
        }
        else "all"
    )
    conn = connect()
    c = conn.cursor()
    rows = c.execute("""
    SELECT
        settings.company_id,
        settings.company_name,
        settings.calendar_auto_publish,
        settings.calendar_auto_remind,
        settings.calendar_auto_days_ahead,
        settings.calendar_auto_window_start,
        settings.calendar_auto_window_end,
        settings.updated_at AS settings_updated_at,
        companies.name AS registered_name,
        companies.owner_username AS registered_owner,
        (
            SELECT users.username
            FROM users
            WHERE users.company_id=settings.company_id
              AND users.role='boss'
              AND COALESCE(users.is_active, 1)=1
            ORDER BY users.id
            LIMIT 1
        ) AS active_owner,
        scheduler.last_started_at,
        scheduler.last_completed_at,
        scheduler.last_status,
        scheduler.last_error,
        scheduler.last_changed_days,
        scheduler.last_notifications_sent,
        scheduler.active_incident,
        scheduler.incident_started_at,
        scheduler.incident_message,
        scheduler.incident_acknowledged_at,
        scheduler.incident_acknowledged_by,
        scheduler.incident_assigned_at,
        scheduler.incident_assigned_to,
        scheduler.incident_assigned_by,
        EXISTS(
            SELECT 1
            FROM calendar_scheduler_incident_events AS escalation
            WHERE escalation.company_id=settings.company_id
              AND escalation.event_type='escalated'
              AND escalation.created_at>=COALESCE(
                  scheduler.incident_started_at,
                  ''
              )
        ) AS incident_escalated,
        EXISTS(
            SELECT 1
            FROM calendar_scheduler_incident_events AS recovery_breach
            WHERE recovery_breach.company_id=settings.company_id
              AND recovery_breach.event_type='recovery_overdue'
              AND recovery_breach.created_at>=COALESCE(
                  scheduler.incident_started_at,
                  ''
              )
        ) AS recovery_overdue_notified,
        latest_run.started_at AS last_scheduler_run_at,
        latest_run.completed_at AS last_scheduler_completed_at,
        latest_run.status AS last_scheduler_run_status,
        latest_run.reason AS last_scheduler_run_reason
    FROM company_settings AS settings
    LEFT JOIN companies
      ON companies.id=settings.company_id
    LEFT JOIN calendar_plan_scheduler_status AS scheduler
      ON scheduler.company_id=settings.company_id
    LEFT JOIN calendar_plan_scheduler_runs AS latest_run
      ON latest_run.id=(
          SELECT run.id
          FROM calendar_plan_scheduler_runs AS run
          WHERE run.company_id=settings.company_id
            AND run.source='scheduler'
          ORDER BY run.id DESC
          LIMIT 1
      )
    ORDER BY settings.company_id
    """).fetchall()
    platform_admin_rows = c.execute("""
    SELECT username
    FROM users
    WHERE role='superadmin'
      AND COALESCE(is_active, 1)=1
    ORDER BY username
    """).fetchall()
    conn.close()
    platform_admins = [
        str(row["username"] or "")
        for row in platform_admin_rows
        if str(row["username"] or "")
    ]
    current_username = str(current_username or "").strip()
    assignee_filter = str(assignee_filter or "all").strip()

    if assignee_filter == "me":
        assignee_target = current_username
    elif assignee_filter in platform_admins:
        assignee_target = assignee_filter
    elif assignee_filter == "unassigned":
        assignee_target = ""
    else:
        assignee_filter = "all"
        assignee_target = ""

    if assignee_filter == "me" and not assignee_target:
        assignee_filter = "all"

    items = []
    incident_labels = {
        "error": "Ошибка запуска",
        "stuck": "Зависший запуск",
        "stale": "Планировщик не запускался",
    }
    status_labels = {
        "disabled": "Выключена",
        "waiting": "Ожидает запуска",
        "healthy": "Работает",
        "running": "Выполняется",
        "stale": "Давно не запускалась",
        "stuck": "Запуск завис",
        "error": "Ошибка",
    }
    run_status_labels = {
        "done": "Выполнено",
        "skipped": "Пропущено",
        "locked": "Занято другим запуском",
        "error": "Ошибка",
        "running": "Выполняется",
    }

    for row in rows:
        item = dict(row)
        item["company_name"] = str(
            item["registered_name"]
            or item["company_name"]
            or f"Компания #{item['company_id']}"
        )
        item["owner_username"] = str(
            item["registered_owner"]
            or item["active_owner"]
            or "не назначен"
        )
        item["automation_enabled"] = bool(
            item["calendar_auto_publish"]
            or item["calendar_auto_remind"]
        )
        active_incident = str(item["active_incident"] or "")
        latest_value = str(
            item["last_scheduler_run_at"]
            or item["settings_updated_at"]
            or ""
        )

        try:
            latest_at = datetime.strptime(
                latest_value,
                "%Y-%m-%d %H:%M",
            )
        except ValueError:
            latest_at = None

        if not item["automation_enabled"]:
            status_code = "disabled"
        elif active_incident:
            status_code = active_incident
        elif not item["last_scheduler_run_at"]:
            status_code = (
                "stale"
                if latest_at
                and now_dt - latest_at
                > timedelta(hours=stale_after_hours)
                else "waiting"
            )
        elif item["last_scheduler_run_status"] == "error":
            status_code = "error"
        elif item["last_scheduler_run_status"] == "running":
            status_code = (
                "stuck"
                if latest_at
                and now_dt - latest_at
                > timedelta(minutes=stuck_after_minutes)
                else "running"
            )
        elif (
            latest_at
            and now_dt - latest_at
            > timedelta(hours=stale_after_hours)
        ):
            status_code = "stale"
        else:
            status_code = "healthy"

        item["status_code"] = status_code
        item["status_label"] = status_labels[status_code]
        item["last_scheduler_run_status_label"] = (
            run_status_labels.get(
                str(item["last_scheduler_run_status"] or ""),
                "Неизвестно",
            )
            if item["last_scheduler_run_status"]
            else ""
        )
        item["incident_label"] = incident_labels.get(
            active_incident,
            "",
        )
        item["last_activity_at"] = str(
            item["last_scheduler_completed_at"]
            or item["last_scheduler_run_at"]
            or ""
        )
        item["is_problem"] = status_code in {
            "error",
            "stuck",
            "stale",
        }
        item["is_acknowledged"] = bool(
            item["incident_acknowledged_at"]
        )
        item["assignee_username"] = str(
            item["incident_assigned_to"]
            or item["incident_acknowledged_by"]
            or ""
        )
        item["assigned_at"] = str(
            item["incident_assigned_at"]
            or item["incident_acknowledged_at"]
            or ""
        )
        item["assigned_by"] = str(
            item["incident_assigned_by"]
            or item["incident_acknowledged_by"]
            or ""
        )
        item["is_mine"] = bool(
            active_incident
            and current_username
            and item["assignee_username"] == current_username
        )
        incident_started_value = str(
            item["incident_started_at"] or ""
        )

        try:
            incident_started_at = datetime.strptime(
                incident_started_value,
                "%Y-%m-%d %H:%M",
            )
            incident_age_minutes = max(
                0,
                int(
                    (now_dt - incident_started_at).total_seconds()
                    // 60
                ),
            )
        except ValueError:
            incident_age_minutes = None
        acknowledged_value = str(
            item["incident_acknowledged_at"] or ""
        )

        try:
            acknowledged_at = datetime.strptime(
                acknowledged_value,
                "%Y-%m-%d %H:%M",
            )
            recovery_age_minutes = max(
                0,
                int(
                    (now_dt - acknowledged_at).total_seconds()
                    // 60
                ),
            )
        except ValueError:
            recovery_age_minutes = None

        recovery_overdue = bool(
            active_incident
            and item["is_acknowledged"]
            and recovery_age_minutes is not None
            and recovery_age_minutes >= recovery_target_minutes
        )

        priority = get_calendar_incident_priority(
            status_code,
            active_incident,
            item["is_acknowledged"],
            incident_age_minutes,
            response_target_minutes=response_target_minutes,
            recovery_overdue=recovery_overdue,
        )
        item["incident_age_minutes"] = incident_age_minutes
        item["incident_age_label"] = (
            format_calendar_incident_age(incident_age_minutes)
            if active_incident
            else ""
        )
        item["priority_code"] = priority["code"]
        item["priority_label"] = priority["label"]
        item["priority_rank"] = priority["rank"]
        item["response_overdue"] = priority["response_overdue"]
        item["recovery_overdue"] = priority["recovery_overdue"]
        item["recovery_age_minutes"] = recovery_age_minutes
        item["recovery_age_label"] = (
            format_calendar_incident_age(recovery_age_minutes)
            if item["is_acknowledged"]
            else ""
        )
        item["recovery_overdue_notified"] = bool(
            active_incident and item["recovery_overdue_notified"]
        )
        sla_deadline = build_calendar_incident_sla_deadline(
            active_incident,
            item["is_acknowledged"],
            incident_age_minutes,
            recovery_age_minutes,
            response_target_minutes,
            recovery_target_minutes,
        )
        item["sla_deadline_label"] = sla_deadline["label"]
        item["sla_deadline_tone"] = sla_deadline["tone"]
        item["requires_response"] = bool(
            active_incident and not item["is_acknowledged"]
        )
        item["is_escalated"] = bool(
            active_incident and item["incident_escalated"]
        )
        item["detail_url"] = (
            f"/platform/calendar-health/{item['company_id']}"
        )
        item["links"] = {
            "detail": item["detail_url"],
            "acknowledge_queue": (
                f"/platform/calendar-health/{item['company_id']}/acknowledge?"
                + urlencode({
                    "return_to": "queue",
                    "status": status_filter,
                    "assignee": assignee_filter,
                })
            ),
        }
        if item["requires_response"]:
            item["next_action_label"] = "Принять в работу"
            item["next_action_hint"] = (
                "Инцидент ещё не закреплён за администратором."
            )
            item["next_action_tone"] = "error"
        elif active_incident and item["is_mine"]:
            item["next_action_label"] = "Запустить восстановление"
            item["next_action_hint"] = (
                "Вы ответственный. Проверьте диагностику и запустите "
                "восстановление из карточки компании."
            )
            item["next_action_tone"] = (
                "error" if item["recovery_overdue"] else "warning"
            )
        elif active_incident and item["is_acknowledged"]:
            item["next_action_label"] = "Контроль ответственного"
            item["next_action_hint"] = (
                f"Ответственный: {item['assignee_username'] or 'не назначен'}."
            )
            item["next_action_tone"] = (
                "error" if item["recovery_overdue"] else "waiting"
            )
        elif item["is_problem"]:
            item["next_action_label"] = "Проверить настройки"
            item["next_action_hint"] = (
                "Активного инцидента нет, но состояние требует проверки."
            )
            item["next_action_tone"] = "warning"
        else:
            item["next_action_label"] = "Наблюдать"
            item["next_action_hint"] = "Действия сейчас не требуются."
            item["next_action_tone"] = "healthy"
        items.append(item)

    oldest_active_incident_minutes = max(
        (
            int(item["incident_age_minutes"] or 0)
            for item in items
            if item["active_incident"]
        ),
        default=0,
    )
    summary = {
        "total_companies": len(items),
        "enabled": sum(
            1 for item in items if item["automation_enabled"]
        ),
        "healthy": sum(
            1 for item in items
            if item["status_code"] in {"healthy", "running"}
        ),
        "problems": sum(1 for item in items if item["is_problem"]),
        "waiting": sum(
            1 for item in items if item["status_code"] == "waiting"
        ),
        "disabled": sum(
            1 for item in items if item["status_code"] == "disabled"
        ),
        "acknowledged": sum(
            1 for item in items if item["is_acknowledged"]
        ),
        "unacknowledged": sum(
            1 for item in items if item["requires_response"]
        ),
        "critical": sum(
            1
            for item in items
            if item["priority_code"] == "critical"
        ),
        "response_overdue": sum(
            1 for item in items if item["response_overdue"]
        ),
        "escalated": sum(
            1 for item in items if item["is_escalated"]
        ),
        "recovery_overdue": sum(
            1 for item in items if item["recovery_overdue"]
        ),
        "active_incidents": sum(
            1 for item in items if item["active_incident"]
        ),
        "assigned": sum(
            1
            for item in items
            if item["active_incident"] and item["is_acknowledged"]
        ),
        "unassigned": sum(
            1
            for item in items
            if item["active_incident"] and not item["is_acknowledged"]
        ),
        "my_incidents": sum(
            1 for item in items if item["is_mine"]
        ),
        "oldest_active_incident_minutes": (
            oldest_active_incident_minutes
        ),
        "oldest_active_incident_label": (
            format_calendar_incident_age(
                oldest_active_incident_minutes,
            )
            if oldest_active_incident_minutes
            else "нет"
        ),
    }
    if summary["critical"] or summary["recovery_overdue"]:
        summary["overall_status_code"] = "critical"
        summary["overall_status_label"] = "Критично"
    elif summary["unacknowledged"] or summary["problems"]:
        summary["overall_status_code"] = "warning"
        summary["overall_status_label"] = "Требует внимания"
    else:
        summary["overall_status_code"] = "healthy"
        summary["overall_status_label"] = "Стабильно"
    admin_workload = []

    for admin_username in platform_admins:
        assigned_items = [
            item
            for item in items
            if item["active_incident"]
            and item["assignee_username"] == admin_username
        ]
        oldest_age_minutes = max(
            (
                int(item["incident_age_minutes"] or 0)
                for item in assigned_items
            ),
            default=0,
        )
        admin_workload.append({
            "username": admin_username,
            "assigned": len(assigned_items),
            "critical": sum(
                1
                for item in assigned_items
                if item["priority_code"] == "critical"
            ),
            "recovery_overdue": sum(
                1
                for item in assigned_items
                if item["recovery_overdue"]
            ),
            "oldest_age_minutes": oldest_age_minutes,
            "oldest_age_label": (
                format_calendar_incident_age(oldest_age_minutes)
                if assigned_items
                else "нет"
            ),
            "is_current": admin_username == current_username,
            "filter_url": (
                "/platform/calendar-health?"
                + urlencode({
                    "assignee": (
                        "me"
                        if admin_username == current_username
                        else admin_username
                    ),
                })
            ),
        })

    admin_workload.sort(
        key=lambda item: (
            -item["assigned"],
            -item["critical"],
            item["username"].lower(),
        )
    )

    if status_filter == "problem":
        filtered_items = [
            item for item in items if item["is_problem"]
        ]
    elif status_filter == "healthy":
        filtered_items = [
            item
            for item in items
            if item["status_code"] in {"healthy", "running"}
        ]
    elif status_filter == "waiting":
        filtered_items = [
            item
            for item in items
            if item["status_code"] == "waiting"
        ]
    elif status_filter == "disabled":
        filtered_items = [
            item
            for item in items
            if item["status_code"] == "disabled"
        ]
    elif status_filter == "unacknowledged":
        filtered_items = [
            item for item in items if item["requires_response"]
        ]
    elif status_filter == "response_overdue":
        filtered_items = [
            item for item in items if item["response_overdue"]
        ]
    elif status_filter == "recovery_overdue":
        filtered_items = [
            item for item in items if item["recovery_overdue"]
        ]
    elif status_filter == "critical":
        filtered_items = [
            item
            for item in items
            if item["priority_code"] == "critical"
        ]
    else:
        filtered_items = items

    if assignee_filter == "unassigned":
        filtered_items = [
            item
            for item in filtered_items
            if item["active_incident"] and not item["is_acknowledged"]
        ]
    elif assignee_filter != "all":
        filtered_items = [
            item
            for item in filtered_items
            if item["active_incident"]
            and item["assignee_username"] == assignee_target
        ]

    filtered_items.sort(
        key=lambda item: (
            item["priority_rank"],
            -int(item["incident_age_minutes"] or 0),
            0 if item["automation_enabled"] else 1,
            item["company_name"].lower(),
        )
    )

    return {
        "summary": summary,
        "items": filtered_items,
        "status_filter": status_filter,
        "assignee_filter": assignee_filter,
        "assignee_target": assignee_target,
        "platform_admins": platform_admins,
        "admin_workload": admin_workload,
        "stale_after_hours": stale_after_hours,
        "policy": policy,
        "generated_at": now_dt.strftime("%Y-%m-%d %H:%M"),
    }


def build_platform_calendar_health_queue_url(
    status="all",
    assignee="all",
    notice="",
    error="",
    claimed=0,
    skipped=0,
    reassigned=0,
):
    allowed_statuses = {
        "all",
        "problem",
        "healthy",
        "waiting",
        "disabled",
        "unacknowledged",
        "response_overdue",
        "recovery_overdue",
        "critical",
    }
    status = str(status or "all").strip()
    assignee = str(assignee or "all").strip()[:100]

    if status not in allowed_statuses:
        status = "all"

    if not assignee:
        assignee = "all"

    params = {
        "status": status,
        "assignee": assignee,
    }

    if notice:
        params["notice"] = str(notice)
    elif error:
        params["error"] = str(error)

    if claimed:
        params["claimed"] = int(claimed)

    if skipped:
        params["skipped"] = int(skipped)

    if reassigned:
        params["reassigned"] = int(reassigned)

    return "/platform/calendar-health?" + urlencode(params)


def build_platform_calendar_health_filter_url(status="all", assignee="all"):
    allowed_statuses = {
        "all",
        "problem",
        "healthy",
        "waiting",
        "disabled",
        "unacknowledged",
        "response_overdue",
        "recovery_overdue",
        "critical",
    }
    status = str(status or "all").strip()
    assignee = str(assignee or "all").strip()[:100]

    if status not in allowed_statuses:
        status = "all"

    if not assignee:
        assignee = "all"

    params = {}

    if status != "all":
        params["status"] = status

    if assignee != "all":
        params["assignee"] = assignee

    if not params:
        return "/platform/calendar-health"

    return "/platform/calendar-health?" + urlencode(params)


def build_platform_calendar_health_export_url(status="all", assignee="all"):
    return build_platform_calendar_health_queue_url(
        status=status,
        assignee=assignee,
    ).replace(
        "/platform/calendar-health",
        "/platform/calendar-health/export",
        1,
    )


def build_platform_calendar_health_links(status="all", assignee="all"):
    status = str(status or "all").strip()
    assignee = str(assignee or "all").strip()[:100] or "all"
    action_params = urlencode({
        "status": status,
        "assignee": assignee,
    })

    return {
        "platform": "/platform",
        "base": "/platform/calendar-health",
        "page": build_platform_calendar_health_queue_url(
            status=status,
            assignee=assignee,
        ),
        "export": build_platform_calendar_health_export_url(
            status=status,
            assignee=assignee,
        ),
        "analytics": "/platform/calendar-health/analytics",
        "claim_visible": (
            "/platform/calendar-health/claim-visible?" + action_params
        ),
        "reassign_visible": (
            "/platform/calendar-health/reassign-visible?" + action_params
        ),
    }


def build_platform_calendar_company_health_links(company_id):
    company_id = int(company_id or 0)
    base_url = f"/platform/calendar-health/{company_id}"

    return {
        "platform": "/platform",
        "calendar_health": "/platform/calendar-health",
        "detail": base_url,
        "export": f"{base_url}/export",
        "acknowledge": f"{base_url}/acknowledge",
        "note": f"{base_url}/note",
        "assign": f"{base_url}/assign",
        "recover": f"{base_url}/recover",
    }


def build_platform_calendar_incident_analytics_links(days=30):
    days = int(days or 30)

    return {
        "platform": "/platform",
        "calendar_health": "/platform/calendar-health",
        "page": f"/platform/calendar-health/analytics?days={days}",
        "export": f"/platform/calendar-health/analytics/export?days={days}",
    }


def claim_visible_calendar_scheduler_incidents(
    actor_username,
    status_filter="unacknowledged",
    assignee_filter="unassigned",
    limit=25,
):
    actor_username = str(actor_username or "").strip()

    if not actor_username:
        return {
            "ok": False,
            "error": "actor_not_found",
            "claimed_count": 0,
            "skipped_count": 0,
            "visible_count": 0,
            "limit": 0,
        }

    try:
        limit = int(limit)
    except (TypeError, ValueError):
        limit = 25

    limit = max(1, min(25, limit))
    health = get_platform_calendar_health(
        status_filter=status_filter,
        assignee_filter=assignee_filter,
        current_username=actor_username,
    )
    candidates = [
        item for item in health["items"] if item["requires_response"]
    ]
    claimed = []
    skipped = []

    for item in candidates[:limit]:
        result = acknowledge_calendar_scheduler_incident(
            item["company_id"],
            actor_username,
        )

        if result["ok"]:
            claimed.append(item["company_id"])
        else:
            skipped.append({
                "company_id": item["company_id"],
                "error": result["error"],
            })

    return {
        "ok": bool(claimed),
        "error": "" if claimed else "nothing_claimed",
        "claimed_company_ids": claimed,
        "skipped": skipped,
        "claimed_count": len(claimed),
        "skipped_count": len(skipped),
        "visible_count": len(candidates),
        "limited": len(candidates) > limit,
        "limit": limit,
        "status_filter": health["status_filter"],
        "assignee_filter": health["assignee_filter"],
    }


def reassign_visible_calendar_scheduler_incidents(
    actor_username,
    assignee_username,
    status_filter="all",
    assignee_filter="all",
    limit=25,
):
    actor_username = str(actor_username or "").strip()
    assignee_username = str(assignee_username or "").strip()

    if not actor_username:
        return {
            "ok": False,
            "error": "actor_not_found",
            "reassigned_count": 0,
            "skipped_count": 0,
            "visible_count": 0,
            "limit": 0,
        }

    if not assignee_username:
        return {
            "ok": False,
            "error": "assignee_not_found",
            "reassigned_count": 0,
            "skipped_count": 0,
            "visible_count": 0,
            "limit": 0,
        }

    try:
        limit = int(limit)
    except (TypeError, ValueError):
        limit = 25

    limit = max(1, min(25, limit))
    health = get_platform_calendar_health(
        status_filter=status_filter,
        assignee_filter=assignee_filter,
        current_username=actor_username,
    )
    candidates = [
        item
        for item in health["items"]
        if item["active_incident"]
        and item["is_acknowledged"]
        and item["assignee_username"] != assignee_username
    ]
    reassigned = []
    skipped = []

    for item in candidates[:limit]:
        result = reassign_calendar_scheduler_incident(
            item["company_id"],
            actor_username,
            assignee_username,
        )

        if result["ok"]:
            reassigned.append(item["company_id"])
        else:
            skipped.append({
                "company_id": item["company_id"],
                "error": result["error"],
            })

    return {
        "ok": bool(reassigned),
        "error": "" if reassigned else "nothing_reassigned",
        "reassigned_company_ids": reassigned,
        "skipped": skipped,
        "reassigned_count": len(reassigned),
        "skipped_count": len(skipped),
        "visible_count": len(candidates),
        "limited": len(candidates) > limit,
        "limit": limit,
        "status_filter": health["status_filter"],
        "assignee_filter": health["assignee_filter"],
        "target_assignee": assignee_username,
    }


def get_platform_calendar_company_detail(
    company_id,
    now_dt=None,
):
    now_dt = now_dt or datetime.now()
    health = get_platform_calendar_health(now_dt=now_dt)
    company = next(
        (
            item
            for item in health["items"]
            if int(item["company_id"]) == int(company_id)
        ),
        None,
    )

    if not company:
        return None

    analytics = get_platform_calendar_incident_analytics(
        days=30,
        now_dt=now_dt,
    )
    company_analytics = next(
        (
            item
            for item in analytics["companies"]
            if int(item["company_id"]) == int(company_id)
        ),
        None,
    )
    if company_analytics:
        company["risk_score"] = company_analytics["risk_score"]
        company["risk_label"] = company_analytics["risk_label"]
        company["risk_tone"] = company_analytics["risk_tone"]
        company["risk_incidents"] = company_analytics["incidents"]
        company["risk_active"] = company_analytics["active"]
        company["risk_response_overdue"] = (
            company_analytics["response_overdue"]
        )
        company["risk_response_overdue_percent"] = (
            company_analytics["response_overdue_percent"]
        )
        company["risk_escalations"] = company_analytics["escalations"]
        company["risk_main_factor"] = company_analytics["risk_main_factor"]
        company["risk_trend_label"] = company_analytics["risk_trend_label"]
        company["risk_trend_tone"] = company_analytics["risk_trend_tone"]
        company["risk_trend_delta"] = company_analytics["risk_trend_delta"]
        if company["risk_score"] >= 80:
            company["risk_next_action"] = (
                "Сначала разберите активные инциденты и просроченную "
                "реакцию."
            )
        elif company["risk_score"] >= 40:
            company["risk_next_action"] = (
                "Проверьте причины просроченной реакции и эскалаций."
            )
        else:
            company["risk_next_action"] = (
                "Риск низкий. Достаточно наблюдать динамику."
            )
    else:
        company["risk_score"] = 0
        company["risk_label"] = "Низкий"
        company["risk_tone"] = "healthy"
        company["risk_incidents"] = 0
        company["risk_active"] = 0
        company["risk_response_overdue"] = 0
        company["risk_response_overdue_percent"] = 0
        company["risk_escalations"] = 0
        company["risk_main_factor"] = (
            "Серьёзных факторов риска не найдено."
        )
        company["risk_trend_label"] = "Мало данных"
        company["risk_trend_tone"] = "waiting"
        company["risk_trend_delta"] = 0
        company["risk_next_action"] = (
            "Риск низкий. Достаточно наблюдать динамику."
        )
    company["risk_summary"] = build_calendar_company_risk_summary(company)
    company["risk_analytics_url"] = (
        "/platform/calendar-health/analytics"
    )
    company["links"] = build_platform_calendar_company_health_links(company_id)

    conn = connect()
    c = conn.cursor()
    run_rows = c.execute("""
    SELECT *
    FROM calendar_plan_scheduler_runs
    WHERE company_id=?
    ORDER BY id DESC
    LIMIT 30
    """, (company_id,)).fetchall()
    incident_rows = c.execute("""
    SELECT *
    FROM calendar_scheduler_incident_events
    WHERE company_id=?
    ORDER BY id DESC
    LIMIT 30
    """, (company_id,)).fetchall()
    operation_rows = c.execute("""
    SELECT *
    FROM calendar_plan_operation_runs
    WHERE company_id=?
    ORDER BY id DESC
    LIMIT 20
    """, (company_id,)).fetchall()
    platform_admin_rows = c.execute("""
    SELECT username
    FROM users
    WHERE role='superadmin'
      AND COALESCE(is_active, 1)=1
    ORDER BY username
    """).fetchall()
    conn.close()
    run_labels = {
        "done": ("Выполнено", "healthy"),
        "skipped": ("Пропущено", "waiting"),
        "locked": ("Занято", "error"),
        "error": ("Ошибка", "error"),
        "running": ("Выполняется", "running"),
    }
    source_labels = {
        "scheduler": "По расписанию",
        "manual_run": "Вручную владельцем",
        "manual": "Ручная операция",
    }
    incident_type_labels = {
        "error": "Ошибка запуска",
        "stuck": "Зависший запуск",
        "stale": "Планировщик не запускался",
    }
    incident_event_labels = {
        "opened": ("Открыт", "error"),
        "acknowledged": ("Принят в работу", "waiting"),
        "escalated": ("Передан платформе", "error"),
        "recovery_overdue": (
            "Восстановление просрочено",
            "error",
        ),
        "recovery_started": ("Запущено восстановление", "running"),
        "recovery_failed": ("Восстановление не выполнено", "error"),
        "note": ("Рабочая заметка", "waiting"),
        "reassigned": ("Ответственный изменён", "running"),
        "recovered": ("Восстановлен", "healthy"),
    }
    operation_labels = {
        "publish_ready": "Публикация готовых планов",
        "remind_pending": "Напоминания исполнителям",
    }
    runs = []
    incidents = []
    operations = []

    for row in run_rows:
        item = dict(row)
        (
            item["status_label"],
            item["status_tone"],
        ) = run_labels.get(
            item["status"],
            ("Неизвестно", "waiting"),
        )
        item["source_label"] = source_labels.get(
            item["source"],
            "Система",
        )
        runs.append(item)

    for row in incident_rows:
        item = dict(row)
        item["incident_type_label"] = incident_type_labels.get(
            item["incident_type"],
            "Инцидент",
        )
        (
            item["event_type_label"],
            item["event_tone"],
        ) = incident_event_labels.get(
            item["event_type"],
            ("Событие", "waiting"),
        )
        incidents.append(item)

    for row in operation_rows:
        item = dict(row)
        item["action_label"] = operation_labels.get(
            item["action"],
            "Операция планов",
        )
        item["source_label"] = source_labels.get(
            item["source"],
            "Система",
        )
        operations.append(item)

    summary = {
        "runs": len(runs),
        "successful": sum(
            1 for item in runs if item["status"] == "done"
        ),
        "problems": sum(
            1
            for item in runs
            if item["status"] in {"error", "locked"}
        ),
        "changed_days": sum(
            int(item["changed_days"] or 0) for item in runs
        ),
        "notifications": sum(
            int(item["notifications_sent"] or 0) for item in runs
        ),
        "incident_events": len(incidents),
        "operations": len(operations),
    }

    return {
        "company": company,
        "summary": summary,
        "runs": runs,
        "incidents": incidents,
        "operations": operations,
        "platform_admins": [
            row["username"] for row in platform_admin_rows
        ],
        "policy": health["policy"],
        "generated_at": now_dt.strftime("%Y-%m-%d %H:%M"),
    }


def build_platform_companies_url(
    search="",
    industry="all",
    plan="all",
    extra_params=None,
    limit="all",
    feature="all",
    billing="all",
):
    params = {}
    (
        search,
        industry,
        plan,
        limit,
        feature,
        billing,
    ) = normalize_platform_company_filters(
        search,
        industry,
        plan,
        limit,
        feature,
        billing,
    )

    if search:
        params["search"] = search

    if industry != "all":
        params["industry"] = industry

    if plan != "all":
        params["plan"] = plan

    if limit != "all":
        params["limit"] = limit

    if feature != "all":
        params["feature"] = feature

    if billing != "all":
        params["billing"] = billing

    if extra_params:
        params.update(extra_params)

    if not params:
        return "/platform/companies"

    return "/platform/companies?" + urlencode(params)


def build_platform_companies_export_url(
    search="",
    industry="all",
    plan="all",
    limit="all",
    feature="all",
    billing="all",
):
    url = build_platform_companies_url(
        search=search,
        industry=industry,
        plan=plan,
        limit=limit,
        feature=feature,
        billing=billing,
    )
    return url.replace(
        "/platform/companies",
        "/platform/companies/export",
        1,
    )


def normalize_platform_company_filters(
    search="",
    industry="all",
    plan="all",
    limit="all",
    feature="all",
    billing="all",
):
    search = str(search or "").strip()[:80]
    allowed_industries = {industry_key for industry_key, _ in INDUSTRY_OPTIONS}
    allowed_limits = {"all", "ok", "warning", "danger"}
    allowed_billing = {"all", "ok", "warning", "danger"}
    allowed_features = {feature_key for feature_key, _, _ in FEATURE_DEFINITIONS}
    industry = industry if industry in allowed_industries else "all"
    plan = plan if plan in PLAN_DEFINITIONS else "all"
    limit = limit if limit in allowed_limits else "all"
    feature = feature if feature in allowed_features else "all"
    billing = billing if billing in allowed_billing else "all"

    return search, industry, plan, limit, feature, billing


def get_platform_dashboard_counts():
    conn = connect()
    c = conn.cursor()
    counts = {
        "companies": c.execute("SELECT COUNT(*) FROM companies").fetchone()[0],
        "users": c.execute("SELECT COUNT(*) FROM users").fetchone()[0],
        "tasks": c.execute("SELECT COUNT(*) FROM tasks").fetchone()[0],
        "clients": c.execute("SELECT COUNT(*) FROM clients").fetchone()[0],
    }
    conn.close()
    return counts


def get_platform_dashboard_alerts(platform_company_usage):
    return {
        "limit_alert_companies": [
            company
            for company in platform_company_usage["companies"]
            if company["user_limit_tone"] in {"warning", "danger"}
        ][:5],
        "billing_alert_companies": [
            company
            for company in platform_company_usage["companies"]
            if company["billing_status_tone"] in {"warning", "danger"}
        ][:5],
    }


def get_platform_dashboard_links():
    return {
        "page": "/platform",
        "export": "/platform/export",
        "companies": "/platform/companies",
        "companies_export": "/platform/companies/export",
        "companies_limit_ok": build_platform_companies_url(limit="ok"),
        "companies_limit_warning": build_platform_companies_url(
            limit="warning",
        ),
        "companies_limit_danger": build_platform_companies_url(
            limit="danger",
        ),
        "companies_billing_warning": build_platform_companies_url(
            billing="warning",
        ),
        "companies_billing_danger": build_platform_companies_url(
            billing="danger",
        ),
        "billing": "/platform/billing",
        "billing_export": "/platform/billing/export",
        "billing_risks": "/platform/companies?billing=warning",
        "modules": "/platform/modules",
        "modules_api": "/api/platform/modules",
        "modules_export": "/platform/modules/export",
        "presets": "/platform/presets",
        "presets_api": "/api/platform/presets",
        "presets_export": "/platform/presets/export",
        "readiness": "/platform/readiness",
        "a3_health": "/platform/a3-health",
        "a3_health_problem": "/platform/a3-health?status=problem",
        "a3_incidents": "/platform/a3-health/incidents",
        "a3_incident_analytics": (
            "/platform/a3-health/incidents/analytics"
        ),
        "a3_incident_reviews": "/platform/a3-health/incidents/reviews",
        "a3_incident_actions": "/platform/a3-health/incidents/actions",
        "calendar_health": "/platform/calendar-health",
        "calendar_health_critical": "/platform/calendar-health?status=critical",
        "calendar_health_unacknowledged": (
            "/platform/calendar-health?status=unacknowledged"
            "&assignee=unassigned"
        ),
        "calendar_health_response_overdue": (
            "/platform/calendar-health?status=response_overdue"
        ),
        "calendar_health_analytics": "/platform/calendar-health/analytics",
        "calendar_health_mine": "/platform/calendar-health?assignee=me",
        "admin": "/admin",
        "debug": "/debug",
        "system": "/system",
        "backup": "/backup",
        "admin_checklist": "/admin/checklist",
        "admin_roadmap": "/admin/roadmap",
        "admin_notes": "/admin/notes",
        "profile": "/profile",
        "logout": "/logout",
    }


def get_platform_generated_at():
    return datetime.now().strftime("%Y-%m-%d %H:%M")


def get_platform_dashboard_data():
    platform_company_usage = get_platform_company_items()
    platform_alerts = get_platform_dashboard_alerts(platform_company_usage)
    platform_module_usage = get_platform_module_usage()
    platform_preset_usage = get_platform_preset_usage()

    return {
        "generated_at": get_platform_generated_at(),
        "counts": get_platform_dashboard_counts(),
        "platform_company_usage": platform_company_usage,
        "platform_alerts": platform_alerts,
        "platform_billing_summary": get_platform_billing_invoice_summary(),
        "platform_module_usage": platform_module_usage,
        "platform_preset_usage": platform_preset_usage,
        "company_usage_summary": platform_company_usage["summary"],
        "limit_alert_companies": platform_alerts["limit_alert_companies"],
        "billing_alert_companies": platform_alerts["billing_alert_companies"],
        "module_usage_summary": platform_module_usage["summary"],
        "preset_usage_summary": platform_preset_usage["summary"],
        "links": get_platform_dashboard_links(),
    }


def get_platform_company_items(
    search="",
    industry="all",
    plan="all",
    limit="all",
    feature="all",
    billing="all",
):
    (
        search,
        selected_industry,
        selected_plan,
        selected_limit,
        selected_feature,
        selected_billing,
    ) = normalize_platform_company_filters(
        search,
        industry,
        plan,
        limit,
        feature,
        billing,
    )

    conn = connect()
    c = conn.cursor()

    query = """
    SELECT
        companies.id,
        companies.name,
        companies.owner_username,
        companies.created_at,
        settings.plan,
        settings.industry,
        (
            SELECT COUNT(*)
            FROM users
            WHERE users.company_id=companies.id
              AND users.role!='superadmin'
        ) AS users_count,
        (
            SELECT COUNT(*)
            FROM users
            WHERE users.company_id=companies.id
              AND users.role!='superadmin'
              AND COALESCE(users.is_active, 1)=1
        ) AS active_users_count,
        (
            SELECT COUNT(*)
            FROM tasks
            WHERE tasks.company_id=companies.id
              AND COALESCE(tasks.archived, 0)=0
        ) AS active_tasks_count,
        (
            SELECT COUNT(*)
            FROM tasks
            WHERE tasks.company_id=companies.id
              AND COALESCE(tasks.archived, 0)=1
        ) AS archived_tasks_count
    FROM companies
    LEFT JOIN company_settings AS settings
      ON settings.company_id=companies.id
    WHERE 1=1
    """
    params = []

    if search:
        query += """
          AND (
              lower(companies.name) LIKE ?
              OR lower(companies.owner_username) LIKE ?
          )
        """
        search_like = f"%{search.lower()}%"
        params.extend([search_like, search_like])

    if selected_industry != "all":
        query += " AND COALESCE(settings.industry, 'field_service')=?"
        params.append(selected_industry)

    if selected_plan != "all":
        query += " AND COALESCE(settings.plan, 'basic')=?"
        params.append(selected_plan)

    query += " ORDER BY companies.id DESC"
    company_rows = c.execute(query, params).fetchall()
    company_ids = [int(row["id"]) for row in company_rows]
    billing_by_company = {company_id: [] for company_id in company_ids}

    if company_ids:
        placeholders = ",".join("?" for _ in company_ids)
        billing_rows = c.execute(f"""
        SELECT *
        FROM billing_invoices
        WHERE company_id IN ({placeholders})
        ORDER BY id DESC
        """, company_ids).fetchall()

        for invoice in build_billing_invoice_rows(billing_rows):
            billing_by_company.setdefault(
                int(invoice.get("company_id") or 0),
                [],
            ).append(invoice)

    conn.close()
    industry_labels = dict(INDUSTRY_OPTIONS)
    companies = []

    for row in company_rows:
        company = dict(row)
        plan = normalize_plan(company.get("plan"))
        user_limit = get_plan_user_limit(plan)
        industry = str(company.get("industry") or "field_service")
        company["plan"] = plan
        company["plan_label"] = get_plan_label(plan)
        company["user_limit_label"] = (
            str(user_limit) if user_limit else "без лимита"
        )
        company["industry_label"] = industry_labels.get(
            industry,
            "Сфера не указана",
        )
        company["users_count"] = int(company.get("users_count") or 0)
        company["active_users_count"] = int(
            company.get("active_users_count") or 0
        )
        company["active_tasks_count"] = int(
            company.get("active_tasks_count") or 0
        )
        company["archived_tasks_count"] = int(
            company.get("archived_tasks_count") or 0
        )
        company["links"] = {
            "page": f"/platform/companies/{company['id']}",
            "settings": f"/platform/companies/{company['id']}/settings",
            "export": f"/platform/companies/{company['id']}/export",
        }

        user_limit_status = get_user_limit_status(
            company["active_users_count"],
            user_limit,
        )
        company["user_limit_status"] = user_limit_status["label"]
        company["user_limit_tone"] = user_limit_status["tone"]
        company["recommended_plan"] = None

        if company["user_limit_tone"] in {"warning", "danger"}:
            company["recommended_plan"] = get_recommended_user_limit_plan(
                plan,
                company["active_users_count"],
            )

        company_billing_invoices = billing_by_company.get(company["id"], [])
        billing_summary = build_billing_invoice_summary(company_billing_invoices)
        billing_risk = build_platform_billing_risk_summary(
            company_billing_invoices,
        )
        company["billing_invoice_summary"] = billing_summary
        company["billing_risk_summary"] = billing_risk

        if billing_risk["overdue_by_date_count"]:
            company["billing_status_tone"] = "danger"
            company["billing_status_label"] = (
                f"Просрочено: {billing_risk['overdue_by_date_count']}"
            )
        elif billing_risk["due_soon_count"]:
            company["billing_status_tone"] = "warning"
            company["billing_status_label"] = (
                f"Скоро к оплате: {billing_risk['due_soon_count']}"
            )
        elif billing_risk["draft_count"]:
            company["billing_status_tone"] = "warning"
            company["billing_status_label"] = (
                f"Черновики: {billing_risk['draft_count']}"
            )
        elif billing_summary["unpaid_amount"] > 0:
            company["billing_status_tone"] = "warning"
            company["billing_status_label"] = (
                f"К оплате: {billing_summary['unpaid_amount_label']}"
            )
        else:
            company["billing_status_tone"] = "ok"
            company["billing_status_label"] = "Счета в норме"

        companies.append(company)

    if selected_limit != "all":
        companies = [
            company
            for company in companies
            if company["user_limit_tone"] == selected_limit
        ]

    if selected_feature != "all":
        companies = [
            company
            for company in companies
            if get_company_features(company["id"]).get(selected_feature)
        ]

    if selected_billing != "all":
        companies = [
            company
            for company in companies
            if company["billing_status_tone"] == selected_billing
        ]

    summary = {
        "companies": len(companies),
        "active_users": sum(
            company["active_users_count"] for company in companies
        ),
        "active_tasks": sum(
            company["active_tasks_count"] for company in companies
        ),
        "limit_alerts": sum(
            1
            for company in companies
            if company["user_limit_tone"] in {"warning", "danger"}
        ),
        "limit_warning": sum(
            1
            for company in companies
            if company["user_limit_tone"] == "warning"
        ),
        "limit_danger": sum(
            1
            for company in companies
            if company["user_limit_tone"] == "danger"
        ),
        "limit_ok": sum(
            1
            for company in companies
            if company["user_limit_tone"] == "ok"
        ),
        "billing_unpaid_amount": round(sum(
            company["billing_invoice_summary"]["unpaid_amount"]
            for company in companies
        ), 2),
        "billing_unpaid_amount_label": format_rub_amount(sum(
            company["billing_invoice_summary"]["unpaid_amount"]
            for company in companies
        )),
        "billing_risk_companies": sum(
            1
            for company in companies
            if company["billing_status_tone"] in {"warning", "danger"}
        ),
        "billing_overdue_companies": sum(
            1
            for company in companies
            if company["billing_risk_summary"]["overdue_by_date_count"] > 0
        ),
        "billing_due_soon_companies": sum(
            1
            for company in companies
            if company["billing_risk_summary"]["due_soon_count"] > 0
        ),
    }

    return {
        "companies": companies,
        "summary": summary,
        "search": search,
        "selected_industry": selected_industry,
        "selected_plan": selected_plan,
        "selected_limit": selected_limit,
        "selected_feature": selected_feature,
        "selected_billing": selected_billing,
        "links": {
            "platform": "/platform",
            "page": "/platform/companies",
            "filtered_page": build_platform_companies_url(
                search=search,
                industry=selected_industry,
                plan=selected_plan,
                limit=selected_limit,
                feature=selected_feature,
                billing=selected_billing,
            ),
            "export": build_platform_companies_export_url(
                search=search,
                industry=selected_industry,
                plan=selected_plan,
                limit=selected_limit,
                feature=selected_feature,
                billing=selected_billing,
            ),
        },
    }


def get_platform_company_profile(company_id):
    company_id = int(company_id or 0)
    conn = connect()
    c = conn.cursor()

    company = c.execute("""
    SELECT id, name, owner_username, created_at
    FROM companies
    WHERE id=?
    """, (company_id,)).fetchone()

    if not company:
        conn.close()
        return None

    company = dict(company)
    conn.close()

    settings = get_company_settings(company_id)
    usage = get_company_user_limit_usage(company_id, settings)
    recommended_plan = None

    if usage["tone"] in {"warning", "danger"}:
        recommended_plan = get_recommended_user_limit_plan(
            usage["plan"],
            usage["active_users_count"],
        )

    features = get_company_features(company_id)
    industry_labels = dict(INDUSTRY_OPTIONS)
    industry = str(settings["industry"] or "field_service")

    conn = connect()
    c = conn.cursor()

    users = c.execute("""
    SELECT
        id,
        username,
        full_name,
        role,
        is_active,
        last_seen
    FROM users
    WHERE company_id=?
      AND role!='superadmin'
    ORDER BY
        CASE role
            WHEN 'boss' THEN 1
            WHEN 'manager' THEN 2
            ELSE 3
        END,
        COALESCE(is_active, 1) DESC,
        username
    """, (company_id,)).fetchall()

    recent_tasks = c.execute("""
    SELECT id, client, status, task_date, archived
    FROM tasks
    WHERE company_id=?
    ORDER BY id DESC
    LIMIT 8
    """, (company_id,)).fetchall()

    settings_history = c.execute("""
    SELECT *
    FROM company_settings_history
    WHERE company_id=?
    ORDER BY id DESC
    LIMIT 5
    """, (company_id,)).fetchall()

    billing_invoices = fetch_billing_invoices(c, company_id)
    for invoice in billing_invoices:
        invoice["links"] = build_platform_billing_invoice_links(
            invoice["id"],
            invoice["company_id"],
        )
    recent_billing_invoices = billing_invoices[:5]
    billing_invoice_summary = build_billing_invoice_summary(billing_invoices)
    billing_risk_summary = build_platform_billing_risk_summary(billing_invoices)
    next_payment_summary = build_billing_next_payment_summary(billing_invoices)

    task_stats = c.execute("""
    SELECT
        COUNT(*) AS total,
        SUM(CASE WHEN COALESCE(archived, 0)=0 THEN 1 ELSE 0 END) AS active,
        SUM(CASE WHEN COALESCE(archived, 0)=1 THEN 1 ELSE 0 END) AS archived,
        SUM(CASE WHEN status='Новая' THEN 1 ELSE 0 END) AS new_tasks,
        SUM(CASE WHEN status='В работе' THEN 1 ELSE 0 END) AS in_progress,
        SUM(CASE WHEN status='Завершено' THEN 1 ELSE 0 END) AS completed
    FROM tasks
    WHERE company_id=?
    """, (company_id,)).fetchone()

    conn.close()

    feature_rows = []
    for feature_key, title, description in FEATURE_DEFINITIONS:
        feature_rows.append({
            "key": feature_key,
            "title": title,
            "description": description,
            "enabled": bool(features.get(feature_key)),
        })

    enabled_features_count = sum(1 for feature in feature_rows if feature["enabled"])
    preset_drift = get_business_preset_drift(industry, features)

    return {
        "company": company,
        "settings": settings,
        "usage": usage,
        "recommended_plan": recommended_plan,
        "industry_label": industry_labels.get(industry, "Сфера не указана"),
        "features": feature_rows,
        "enabled_features_count": enabled_features_count,
        "disabled_features_count": len(feature_rows) - enabled_features_count,
        "preset_drift": preset_drift,
        "task_stats": {
            "total": int(task_stats["total"] or 0),
            "active": int(task_stats["active"] or 0),
            "archived": int(task_stats["archived"] or 0),
            "new_tasks": int(task_stats["new_tasks"] or 0),
            "in_progress": int(task_stats["in_progress"] or 0),
            "completed": int(task_stats["completed"] or 0),
        },
        "users": [dict(user) for user in users],
        "recent_tasks": [dict(task) for task in recent_tasks],
        "settings_history": [
            dict(event) for event in settings_history
        ],
        "billing_invoices": recent_billing_invoices,
        "billing_invoice_summary": billing_invoice_summary,
        "billing_risk_summary": billing_risk_summary,
        "next_payment_summary": next_payment_summary,
        "links": {
            "page": f"/platform/companies/{company['id']}",
            "companies": "/platform/companies",
            "settings": f"/platform/companies/{company['id']}/settings",
            "apply_preset": (
                f"/platform/companies/{company['id']}/apply-preset"
            ),
            "export": f"/platform/companies/{company['id']}/export",
            "billing": f"/platform/billing?company_id={company['id']}",
            "billing_export": build_platform_billing_url(
                company_id=company["id"],
                export=True,
            ),
            "billing_generate": (
                f"/platform/companies/{company['id']}/billing/generate"
            ),
        },
    }


def get_platform_module_usage():
    conn = connect()
    c = conn.cursor()
    company_rows = c.execute("""
    SELECT
        companies.id,
        companies.name,
        companies.owner_username,
        COALESCE(settings.plan, 'basic') AS plan,
        COALESCE(settings.industry, 'field_service') AS industry
    FROM companies
    LEFT JOIN company_settings AS settings
      ON settings.company_id=companies.id
    ORDER BY companies.id DESC
    """).fetchall()
    conn.close()

    industry_labels = dict(INDUSTRY_OPTIONS)
    companies = []

    for row in company_rows:
        company = dict(row)
        company["plan"] = normalize_plan(company["plan"])
        company["plan_label"] = get_plan_label(company["plan"])
        company["industry_label"] = industry_labels.get(
            company["industry"],
            "Сфера не указана",
        )
        company["links"] = {
            "page": f"/platform/companies/{company['id']}",
            "settings": f"/platform/companies/{company['id']}/settings",
            "export": f"/platform/companies/{company['id']}/export",
        }
        company["features"] = get_company_features(company["id"])
        companies.append(company)

    module_rows = []
    companies_count = len(companies)

    for feature_key, title, description in FEATURE_DEFINITIONS:
        enabled_companies = [
            company
            for company in companies
            if company["features"].get(feature_key)
        ]
        disabled_companies = [
            company
            for company in companies
            if not company["features"].get(feature_key)
        ]
        enabled_count = len(enabled_companies)
        coverage_percent = (
            int(round((enabled_count / companies_count) * 100))
            if companies_count
            else 0
        )

        module_rows.append({
            "key": feature_key,
            "title": title,
            "description": description,
            "enabled_count": enabled_count,
            "disabled_count": len(disabled_companies),
            "coverage_percent": coverage_percent,
            "enabled_companies": enabled_companies,
            "disabled_companies": disabled_companies,
            "companies": enabled_companies[:5],
            "links": {
                "page": f"/platform/modules/{feature_key}",
                "companies": build_platform_companies_url(
                    feature=feature_key,
                ),
                "companies_export": build_platform_companies_export_url(
                    feature=feature_key,
                ),
            },
        })

    enabled_links = sum(module["enabled_count"] for module in module_rows)
    possible_links = companies_count * len(module_rows)

    summary = {
        "companies_count": companies_count,
        "modules_count": len(module_rows),
        "enabled_links": enabled_links,
        "possible_links": possible_links,
        "coverage_percent": (
            int(round((enabled_links / possible_links) * 100))
            if possible_links
            else 0
        ),
    }

    return {
        "summary": summary,
        "modules": module_rows,
        "links": {
            "platform": "/platform",
            "page": "/platform/modules",
            "export": "/platform/modules/export",
        },
    }


def get_expected_business_preset_features(industry):
    industry = str(industry or "field_service")
    return set(
        BUSINESS_PRESETS.get(industry, BUSINESS_PRESETS["other"])
    ) | CORE_FEATURES


def get_business_preset_drift(industry, features):
    expected_features = get_expected_business_preset_features(industry)
    drift_items = []

    for feature_key, title, _ in FEATURE_DEFINITIONS:
        expected_enabled = feature_key in expected_features
        current_enabled = bool(features.get(feature_key))

        if current_enabled == expected_enabled:
            continue

        drift_items.append({
            "key": feature_key,
            "title": title,
            "expected_enabled": expected_enabled,
            "current_enabled": current_enabled,
            "expected_label": (
                "Должен быть включён"
                if expected_enabled
                else "Должен быть выключен"
            ),
            "current_label": (
                "Сейчас включён"
                if current_enabled
                else "Сейчас выключен"
            ),
        })

    return {
        "count": len(drift_items),
        "items": drift_items,
        "status_label": (
            "Есть отклонения"
            if drift_items
            else "Соответствует пресету"
        ),
        "tone": "warning" if drift_items else "ok",
    }


def get_platform_preset_usage():
    conn = connect()
    c = conn.cursor()
    company_rows = c.execute("""
    SELECT
        companies.id,
        COALESCE(industry, 'field_service') AS industry,
        companies.name
    FROM companies
    LEFT JOIN company_settings AS settings
      ON settings.company_id=companies.id
    """).fetchall()
    conn.close()

    company_counts = {}
    drift_counts = {}

    for row in company_rows:
        industry = str(row["industry"] or "field_service")
        company_counts[industry] = company_counts.get(industry, 0) + 1
        current_features = get_company_features(row["id"])
        drift = get_business_preset_drift(industry, current_features)

        if drift["count"] > 0:
            drift_counts[industry] = drift_counts.get(industry, 0) + 1

    feature_titles = {
        feature_key: title
        for feature_key, title, _ in FEATURE_DEFINITIONS
    }
    preset_rows = []

    for industry_key, industry_title in INDUSTRY_OPTIONS:
        expected_features = get_expected_business_preset_features(industry_key)
        labels = INDUSTRY_LABEL_PRESETS.get(
            industry_key,
            INDUSTRY_LABEL_PRESETS["field_service"],
        )
        feature_items = [
            {
                "key": feature_key,
                "title": feature_titles.get(feature_key, feature_key),
                "links": {
                    "page": f"/platform/modules/{feature_key}",
                },
            }
            for feature_key, _, _ in FEATURE_DEFINITIONS
            if feature_key in expected_features
        ]

        preset_rows.append({
            "key": industry_key,
            "title": industry_title,
            "companies_count": company_counts.get(industry_key, 0),
            "drift_count": drift_counts.get(industry_key, 0),
            "modules_count": len(feature_items),
            "features": feature_items,
            "labels": labels,
            "links": {
                "page": f"/platform/presets/{industry_key}",
                "companies": build_platform_companies_url(
                    industry=industry_key,
                ),
                "companies_export": build_platform_companies_export_url(
                    industry=industry_key,
                ),
            },
        })

    summary = {
        "presets_count": len(preset_rows),
        "companies_count": sum(company_counts.values()),
        "active_presets_count": sum(
            1
            for preset in preset_rows
            if preset["companies_count"] > 0
        ),
        "drift_count": sum(drift_counts.values()),
        "modules_count": len(FEATURE_DEFINITIONS),
    }

    return {
        "summary": summary,
        "presets": preset_rows,
        "links": {
            "platform": "/platform",
            "page": "/platform/presets",
            "export": "/platform/presets/export",
        },
    }


def get_platform_preset_profile(industry_key):
    industry_key = str(industry_key or "").strip()
    allowed_industries = {key for key, _ in INDUSTRY_OPTIONS}

    if industry_key not in allowed_industries:
        return None

    preset_usage = get_platform_preset_usage()
    preset = next(
        (
            item
            for item in preset_usage["presets"]
            if item["key"] == industry_key
        ),
        None,
    )

    if not preset:
        return None

    conn = connect()
    c = conn.cursor()
    company_rows = c.execute("""
    SELECT
        companies.id,
        companies.name,
        companies.owner_username,
        companies.created_at,
        COALESCE(settings.plan, 'basic') AS plan
    FROM companies
    LEFT JOIN company_settings AS settings
      ON settings.company_id=companies.id
    WHERE COALESCE(settings.industry, 'field_service')=?
    ORDER BY companies.id DESC
    """, (industry_key,)).fetchall()
    conn.close()

    companies = []
    for row in company_rows:
        company = dict(row)
        company["plan"] = normalize_plan(company["plan"])
        company["plan_label"] = get_plan_label(company["plan"])
        company["drift"] = get_business_preset_drift(
            industry_key,
            get_company_features(company["id"]),
        )
        company["links"] = {
            "page": f"/platform/companies/{company['id']}",
            "settings": f"/platform/companies/{company['id']}/settings",
            "export": f"/platform/companies/{company['id']}/export",
        }
        companies.append(company)

    return {
        "summary": preset_usage["summary"],
        "preset": preset,
        "companies": companies,
        "links": {
            "platform": preset_usage["links"]["platform"],
            "presets": preset_usage["links"]["page"],
            **preset["links"],
        },
    }


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(
    request: Request,
    error: StarletteHTTPException,
):
    status_code = int(getattr(error, "status_code", 500) or 500)
    request_id = get_request_id(request)
    meta = get_http_error_meta(status_code)

    if request_prefers_json(request):
        response = JSONResponse(
            {
                "ok": False,
                "error": meta["code"],
                "status_code": status_code,
                "message": meta["message"],
                "request_id": request_id,
            },
            status_code=status_code,
        )
        return finalize_response_headers(response, request_id)

    try:
        response = templates.TemplateResponse(
            request,
            "http_error.html",
            {
                "request": request,
                "status_code": status_code,
                "title": meta["title"],
                "message": meta["message"],
                "request_id": request_id,
                "links": build_error_links(),
            },
            status_code=status_code,
        )
        return finalize_response_headers(response, request_id)
    except Exception:
        response = Response(
            (
                f"{meta['title']}. "
                f"{meta['message']} "
                f"Код запроса: {request_id}."
            ),
            status_code=status_code,
            media_type="text/plain; charset=utf-8",
        )
        return finalize_response_headers(response, request_id)


def notify_error_incident(incident):
    incident_id = int(incident.get("id") or 0)
    if not incident_id:
        return {"notifications_created": 0, "telegram_sent": False}

    title = f"Повторяющаяся ошибка приложения #{incident_id}"
    message = (
        f"{incident.get('error_type') or 'Exception'} · "
        f"{incident.get('method') or '—'} "
        f"{incident.get('path_pattern') or '/'} · "
        f"повторов: {int(incident.get('occurrence_count') or 0)}."
    )
    admins = []
    connection = None
    try:
        connection = connect()
        admins = connection.execute("""
            SELECT username, company_id
            FROM users
            WHERE role='superadmin'
              AND COALESCE(is_active, 1)=1
            ORDER BY username
        """).fetchall()
    except Exception:
        admins = []
    finally:
        if connection:
            connection.close()

    notifications_created = 0
    for admin in admins:
        try:
            create_notification(
                admin["company_id"],
                admin["username"],
                title,
                message,
                "/system#error-incidents",
            )
            notifications_created += 1
        except Exception:
            continue

    telegram_sent = False
    try:
        telegram_sent = bool(send_message(
            f"⚠️ {title}\n{message}\nОткройте /system для разбора.",
        ))
    except Exception:
        telegram_sent = False
    return {
        "notifications_created": notifications_created,
        "telegram_sent": telegram_sent,
    }


def log_runtime_exception(request, error, request_id=""):
    error_id = uuid4().hex[:12]
    request_id = request_id or get_request_id(request)
    username = ""

    try:
        username = get_user(request) or ""
    except Exception:
        username = ""

    try:
        path = request.url.path
    except Exception:
        path = ""

    try:
        method = request.method
    except Exception:
        method = ""

    error_type = type(error).__name__
    incident_result = None
    try:
        incident_result = record_error_incident(
            error_type,
            method=method,
            path=path,
            source="runtime",
            severity="critical",
            error_id=error_id,
            request_id=request_id,
            username=username,
        )
    except Exception:
        incident_result = None

    incident = (
        incident_result.get("incident", {})
        if incident_result
        else {}
    )
    safe_path = incident.get("path_pattern") or normalize_error_path(path)
    details = (
        f"id={error_id}; request_id={request_id}; method={method}; "
        f"path={safe_path}; type={error_type}; "
        f"incident_id={incident.get('id') or ''}"
    )
    log_system_event(
        "runtime_error",
        "critical",
        username,
        "runtime",
        f"Ошибка приложения {error_id}",
        details,
    )

    if incident_result and incident_result.get("notification_due"):
        notify_error_incident(incident)

    return error_id


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, error: Exception):
    request_id = get_request_id(request)
    error_id = log_runtime_exception(request, error, request_id)

    if request_prefers_json(request):
        response = JSONResponse(
            {
                "ok": False,
                "error": "internal_error",
                "error_id": error_id,
                "request_id": request_id,
            },
            status_code=500,
        )
        return finalize_response_headers(response, request_id)

    try:
        response = templates.TemplateResponse(
            request,
            "error.html",
            {
                "request": request,
                "error_id": error_id,
                "request_id": request_id,
                "links": build_error_links(),
            },
            status_code=500,
        )
        return finalize_response_headers(response, request_id)
    except Exception:
        response = Response(
            (
                "Внутренняя ошибка приложения. "
                f"Код ошибки: {error_id}. "
                f"Код запроса: {request_id}."
            ),
            status_code=500,
            media_type="text/plain; charset=utf-8",
        )
        return finalize_response_headers(response, request_id)


def backup_event_severity(status):
    if status == "Успешно":
        return "ok"

    if status == "Ошибка":
        return "critical"

    return "warning"


def log_backup_event(username, action, status, file_name="", details=""):
    conn = connect()
    c = conn.cursor()
    c.execute("""
    INSERT INTO backup_events (
        username,
        action,
        status,
        file_name,
        details,
        created_at
    )
    VALUES (?, ?, ?, ?, ?, ?)
    """, (
        username,
        action,
        status,
        file_name,
        details,
        datetime.now().strftime("%Y-%m-%d %H:%M"),
    ))
    conn.commit()
    conn.close()
    log_system_event(
        "backup",
        backup_event_severity(status),
        username,
        "backup",
        f"{action}: {status}",
        details or file_name,
    )


def get_backup_event_history(limit=12):
    conn = connect()
    events = conn.execute("""
    SELECT *
    FROM backup_events
    ORDER BY id DESC
    LIMIT ?
    """, (limit,)).fetchall()
    conn.close()
    return events


def get_latest_backup_event(action="", file_name=""):
    conn = connect()
    query = """
    SELECT *
    FROM backup_events
    WHERE 1=1
    """
    params = []

    if action:
        query += " AND action=?"
        params.append(action)

    if file_name:
        query += " AND file_name=?"
        params.append(file_name)

    query += " ORDER BY id DESC LIMIT 1"
    event = conn.execute(query, params).fetchone()
    conn.close()
    return event


def list_database_backup_files():
    backup_path = DATA_DIR / "backups"

    if not backup_path.exists():
        return []

    database_runtime = get_database_runtime_config()
    extensions = (
        (".dump",)
        if database_runtime["active_backend"] == "postgresql"
        else (".db", ".sqlite", ".sqlite3")
    )
    files = [
        file
        for file in backup_path.iterdir()
        if file.is_file()
        and file.suffix.lower() in extensions
    ]
    files.sort(
        key=lambda file: file.stat().st_mtime,
        reverse=True,
    )
    return files


def get_backup_cleanup_candidates(files, now=None):
    now = now or datetime.now()
    cutoff = now - timedelta(days=BACKUP_RETENTION_DAYS)
    candidates = []

    for file in files[BACKUP_RETENTION_KEEP:]:
        file_at = datetime.fromtimestamp(file.stat().st_mtime)

        if file_at < cutoff:
            candidates.append(file)

    return candidates


def verify_database_backup_file(file_path):
    if Path(file_path).suffix.lower() == ".dump":
        return verify_postgresql_backup(file_path, BACKUP_REQUIRED_TABLES)

    result = {
        "status": "critical",
        "status_label": "Проблема",
        "message": "Копия не проверена.",
        "quick_check": "",
        "missing_tables": [],
    }
    conn = None

    try:
        backup_uri = f"file:{file_path.resolve()}?mode=ro"
        conn = sqlite3.connect(backup_uri, uri=True)
        quick_check_row = conn.execute("PRAGMA quick_check").fetchone()
        quick_check = quick_check_row[0] if quick_check_row else ""
        table_rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        ).fetchall()
        tables = {row[0] for row in table_rows}
        missing_tables = [
            table
            for table in BACKUP_REQUIRED_TABLES
            if table not in tables
        ]

        if quick_check != "ok":
            result.update({
                "status": "critical",
                "status_label": "Ошибка проверки",
                "message": "SQLite quick_check вернул ошибку.",
                "quick_check": quick_check,
                "missing_tables": missing_tables,
            })
        elif missing_tables:
            result.update({
                "status": "warning",
                "status_label": "Неполная копия",
                "message": "В копии нет части ключевых таблиц.",
                "quick_check": quick_check,
                "missing_tables": missing_tables,
            })
        else:
            result.update({
                "status": "ok",
                "status_label": "Проверена",
                "message": "Копия читается, ключевые таблицы на месте.",
                "quick_check": quick_check,
                "missing_tables": [],
            })
    except (OSError, sqlite3.Error):
        result.update({
            "status": "critical",
            "status_label": "Не читается",
            "message": "Файл не читается как SQLite база.",
            "quick_check": "",
            "missing_tables": list(BACKUP_REQUIRED_TABLES),
        })
    finally:
        if conn:
            conn.close()

    return result


def get_backup_status():
    database_runtime = get_database_runtime_config()
    object_storage_config = get_object_storage_runtime_config()
    is_postgresql = database_runtime["active_backend"] == "postgresql"
    db_path = DATA_DIR / "crm.db"
    backup_path = DATA_DIR / "backups"
    if is_postgresql:
        database_state = inspect_postgresql_database(os.getenv("DATABASE_URL"))
        db_exists = database_state["ok"]
        db_size = database_state["size"]
        db_path_label = "PostgreSQL"
        backend_label = "PostgreSQL"
        verification_method = (
            "Каталог pg_restore, манифест таблиц и количества строк"
        )
    else:
        db_exists = db_path.exists()
        db_size = db_path.stat().st_size if db_exists else 0
        db_path_label = str(db_path)
        backend_label = "SQLite"
        verification_method = "SQLite quick_check и ключевые таблицы"
    backup_path_exists = backup_path.exists()
    files = list_database_backup_files()
    latest = files[0] if files else None
    now = datetime.now()
    latest_at = None
    latest_age_hours = None

    if latest:
        latest_at = datetime.fromtimestamp(latest.stat().st_mtime)
        latest_age_hours = (now - latest_at).total_seconds() / 3600

    if object_storage_config["configured_backend"] != "s3":
        remote_copy = {
            "status": "ok",
            "status_label": "Локально",
            "message": "Внешнее зеркало резервных копий не включено.",
            "enabled": False,
        }
    elif not latest:
        remote_copy = {
            "status": "warning",
            "status_label": "Нет копии",
            "message": "Для S3-зеркала ещё нет резервной копии.",
            "enabled": True,
        }
    else:
        archive_remote = s3_object_exists(f"backups/{latest.name}")
        manifest_remote = (
            s3_object_exists(f"backups/{latest.name}.json")
            if latest.suffix.lower() == ".dump"
            else True
        )
        remote_ok = archive_remote and manifest_remote
        remote_copy = {
            "status": "ok" if remote_ok else "critical",
            "status_label": "Синхронизировано" if remote_ok else "Ошибка",
            "message": (
                "Последняя резервная копия сохранена во внешнем S3."
                if remote_ok
                else "Последняя резервная копия отсутствует в S3-зеркале."
            ),
            "enabled": True,
        }

    verifications = {
        file.name: verify_database_backup_file(file)
        for file in files[:8]
    }
    latest_verification = (
        verifications.get(latest.name) if latest else {
            "status": "empty",
            "status_label": "нет",
            "message": "Резервных копий пока нет.",
            "quick_check": "",
            "missing_tables": [],
        }
    )
    latest_restore_event = (
        get_latest_backup_event("Проверка восстановления", latest.name)
        if latest
        else None
    )

    if not latest:
        restore_check = {
            "status": "warning",
            "status_label": "нет копии",
            "message": "Проверку восстановления нельзя выполнить без backup.",
            "created_at": "",
            "username": "",
            "file_name": "",
        }
    elif latest_restore_event and latest_restore_event["status"] == "Успешно":
        restore_check = {
            "status": "ok",
            "status_label": "Проверено",
            "message": latest_restore_event["details"],
            "created_at": latest_restore_event["created_at"],
            "username": latest_restore_event["username"],
            "file_name": latest_restore_event["file_name"],
        }
    elif latest_restore_event:
        restore_check = {
            "status": "critical",
            "status_label": "Ошибка",
            "message": latest_restore_event["details"],
            "created_at": latest_restore_event["created_at"],
            "username": latest_restore_event["username"],
            "file_name": latest_restore_event["file_name"],
        }
    else:
        restore_check = {
            "status": "warning",
            "status_label": "не проверено",
            "message": "Последняя копия ещё не проходила проверку восстановления.",
            "created_at": "",
            "username": "",
            "file_name": latest.name,
        }

    if not db_exists:
        status = "critical"
        status_label = "База не найдена"
        summary = "Невозможно создать резервную копию: база недоступна."
        action = "Проверьте подключение к базе данных и её запуск."
    elif not backup_path_exists:
        status = "warning"
        status_label = "Папка не создана"
        summary = "Папка резервных копий пока не создана."
        action = "Создайте первую резервную копию перед релизом."
    elif not files:
        status = "warning"
        status_label = "Копий нет"
        summary = "Резервных копий базы пока нет."
        action = "Создайте первую резервную копию перед релизом."
    elif latest_verification["status"] == "critical":
        status = "critical"
        status_label = "Копия повреждена"
        summary = "Последняя резервная копия не прошла проверку."
        action = "Создайте новую копию и проверьте её перед запуском."
    elif latest_verification["status"] == "warning":
        status = "warning"
        status_label = "Копия неполная"
        summary = "Последняя копия читается, но в ней нет части ключевых таблиц."
        action = "Проверьте миграции и создайте новую копию."
    elif remote_copy["status"] == "critical":
        status = "critical"
        status_label = "Нет S3-копии"
        summary = "Последняя резервная копия не сохранена во внешнем S3."
        action = "Проверьте S3-конфигурацию и создайте новую копию."
    elif restore_check["status"] == "critical":
        status = "critical"
        status_label = "Восстановление не прошло"
        summary = "Последняя копия не прошла проверку восстановления."
        action = "Создайте новую копию и повторите проверку восстановления."
    elif restore_check["status"] == "warning":
        status = "warning"
        status_label = "Нужна проверка восстановления"
        summary = "Последняя копия ещё не проверялась на восстановление."
        action = "Запустите проверку восстановления перед релизом."
    elif latest_age_hours > 168:
        status = "critical"
        status_label = "Копия устарела"
        summary = "Последняя резервная копия старше 7 дней."
        action = "Создайте свежую резервную копию перед запуском."
    elif latest_age_hours > 72:
        status = "warning"
        status_label = "Нужна свежая копия"
        summary = "Последняя резервная копия старше 3 дней."
        action = "Обновите резервную копию перед запуском."
    else:
        status = "ok"
        status_label = "Копия свежая"
        summary = "Резервная копия базы актуальна."
        action = "Продолжайте регулярное резервное копирование."

    total_size = sum(file.stat().st_size for file in files)
    cleanup_candidates = get_backup_cleanup_candidates(files, now)
    cleanup_size = sum(file.stat().st_size for file in cleanup_candidates)
    recent_files = []

    for file in files[:8]:
        stat = file.stat()
        file_at = datetime.fromtimestamp(stat.st_mtime)
        file_age_hours = (now - file_at).total_seconds() / 3600
        is_stale = file in cleanup_candidates
        verification = verifications.get(file.name)
        recent_files.append({
            "name": file.name,
            "size": stat.st_size,
            "size_label": format_file_size(stat.st_size),
            "created_at": file_at.strftime("%Y-%m-%d %H:%M"),
            "age_label": format_backup_age(file_age_hours),
            "download_url": f"/backup/download?file={file.name}",
            "manifest_download_url": (
                f"/backup/download?file={file.name}.json"
                if Path(f"{file}.json").exists()
                else ""
            ),
            "is_stale": is_stale,
            "stale_label": "старая" if is_stale else "хранится",
            "verification": verification,
        })

    verification_problem_count = len([
        item
        for item in verifications.values()
        if item["status"] in ("warning", "critical")
    ])

    return {
        "status": status,
        "status_label": status_label,
        "summary": summary,
        "action": action,
        "backend": database_runtime["active_backend"],
        "backend_label": backend_label,
        "verification_method": verification_method,
        "db_exists": db_exists,
        "db_path": db_path_label,
        "db_size": db_size,
        "db_size_label": format_file_size(db_size) if db_exists else "0 байт",
        "backup_path": str(backup_path),
        "backup_path_exists": backup_path_exists,
        "count": len(files),
        "total_size": total_size,
        "total_size_label": format_file_size(total_size),
        "latest_name": latest.name if latest else "",
        "latest_download_url": (
            f"/backup/download?file={latest.name}" if latest else ""
        ),
        "latest_created_at": (
            latest_at.strftime("%Y-%m-%d %H:%M") if latest_at else ""
        ),
        "latest_age_hours": int(latest_age_hours or 0),
        "latest_age_label": format_backup_age(latest_age_hours),
        "latest_verification": latest_verification,
        "restore_check": restore_check,
        "remote_copy": remote_copy,
        "verification_checked_count": len(verifications),
        "verification_problem_count": verification_problem_count,
        "retention_days": BACKUP_RETENTION_DAYS,
        "retention_keep": BACKUP_RETENTION_KEEP,
        "cleanup_count": len(cleanup_candidates),
        "cleanup_size": cleanup_size,
        "cleanup_size_label": format_file_size(cleanup_size),
        "cleanup_url": "/backup/cleanup",
        "restore_check_url": "/backup/restore-check",
        "recent_files": recent_files,
        "url": "/backup",
        "export_url": "/backup/export",
    }


def get_backup_download_path(filename):
    filename = str(filename or "").strip()

    if not filename or Path(filename).name != filename:
        return None, "invalid_backup"

    database_runtime = get_database_runtime_config()
    is_postgresql = database_runtime["active_backend"] == "postgresql"
    is_dump = Path(filename).suffix.lower() == ".dump"
    is_manifest = filename.lower().endswith(".dump.json")
    is_sqlite = Path(filename).suffix.lower() in (
        ".db",
        ".sqlite",
        ".sqlite3",
    )
    if (is_postgresql and not (is_dump or is_manifest)) or (
        not is_postgresql and not is_sqlite
    ):
        return None, "invalid_backup"

    file_path = DATA_DIR / "backups" / filename

    if not file_path.exists() or not file_path.is_file():
        return None, "backup_not_found"
    if is_manifest:
        archive_path = Path(str(file_path)[:-5])
        if not archive_path.is_file():
            return None, "backup_not_found"

    return file_path, ""


def create_database_backup(username):
    database_runtime = get_database_runtime_config()
    if database_runtime["active_backend"] == "postgresql":
        filename, error = create_postgresql_backup(
            os.getenv("DATABASE_URL"),
            DATA_DIR / "backups",
            BACKUP_REQUIRED_TABLES,
        )
        if error:
            return filename, error
        mirror_error = mirror_database_backup(filename)
        return filename, mirror_error

    db_path = DATA_DIR / "crm.db"

    if not db_path.exists():
        return None, "db_missing"

    backup_path = DATA_DIR / "backups"
    backup_path.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    destination = backup_path / f"crm_backup_{timestamp}.db"
    shutil.copy2(db_path, destination)
    mirror_error = mirror_database_backup(destination.name)
    return destination.name, mirror_error


def mirror_database_backup(filename):
    storage_config = get_object_storage_runtime_config()
    if storage_config["configured_backend"] != "s3":
        return ""
    backup_file = DATA_DIR / "backups" / filename
    try:
        save_storage_path(
            backup_file,
            f"backups/{filename}",
            DATA_DIR,
        )
        manifest_path = Path(f"{backup_file}.json")
        if manifest_path.is_file():
            save_storage_path(
                manifest_path,
                f"backups/{filename}.json",
                DATA_DIR,
            )
    except (ObjectStorageError, ValueError):
        return "backup_storage_failed"
    return ""


def cleanup_old_database_backups():
    files = list_database_backup_files()
    candidates = get_backup_cleanup_candidates(files)
    deleted = []
    deleted_size = 0

    for file in candidates:
        try:
            deleted_size += file.stat().st_size
            deleted.append(file.name)
            file.unlink()
            manifest_path = Path(f"{file}.json")
            if manifest_path.exists():
                manifest_path.unlink()
            try:
                delete_storage_object(f"backups/{file.name}", DATA_DIR)
                delete_storage_object(
                    f"backups/{file.name}.json",
                    DATA_DIR,
                )
            except (ObjectStorageError, ValueError):
                pass
        except OSError:
            continue

    return {
        "deleted_count": len(deleted),
        "deleted_size": deleted_size,
        "deleted_size_label": format_file_size(deleted_size),
        "deleted_files": deleted,
    }


def enqueue_database_backup_job(username):
    return enqueue_background_job(
        "database_backup",
        payload={"requested_by": str(username or "")[:120]},
        requested_by=username,
        dedupe_key="database_backup",
        priority=20,
    )


def run_database_backup_job(payload, job):
    username = str(
        job.get("requested_by")
        or payload.get("requested_by")
        or "background-worker"
    )[:120]
    filename, error = create_database_backup(username)
    if error:
        details = {
            "db_missing": "Файл базы данных не найден.",
            "backup_tool_missing": "Утилита pg_dump недоступна.",
            "backup_timeout": "Создание копии превысило лимит времени.",
            "backup_schema_incomplete": "В схеме нет части ключевых таблиц.",
            "backup_storage_failed": "Копия не сохранена во внешнем S3.",
        }.get(error, "Не удалось создать резервную копию базы данных.")
        try:
            log_backup_event(
                username,
                "Фоновое создание копии",
                "Ошибка",
                filename or "",
                details,
            )
        except Exception:
            pass
        retryable = error not in {
            "db_missing",
            "backup_tool_missing",
            "backup_schema_incomplete",
        }
        raise BackgroundJobExecutionError(error, retryable=retryable)

    try:
        log_backup_event(
            username,
            "Создание копии",
            "Успешно",
            filename,
            "Резервная копия базы создана фоновой очередью.",
        )
    except Exception:
        pass
    return {"filename": filename}


def get_background_job_handlers():
    return {
        "database_backup": run_database_backup_job,
    }


def run_background_job_batch(worker_id="web-worker", limit=None):
    return process_background_jobs(
        get_background_job_handlers(),
        worker_id=worker_id,
        limit=limit,
    )


def build_backup_links():
    return {
        "platform": get_platform_dashboard_links()["page"],
        "system": "/system",
        "create": "/backup/create",
        "jobs": "/api/platform/background-jobs",
        "run_jobs": "/backup/jobs/run",
    }


def run_backup_restore_drill(filename=""):
    if filename:
        source_path, error = get_backup_download_path(filename)
    else:
        files = list_database_backup_files()
        source_path = files[0] if files else None
        error = "" if source_path else "backup_not_found"

    if error:
        return {
            "status": "critical",
            "status_label": "Проверка не выполнена",
            "message": "Резервная копия не найдена.",
            "file": "",
            "verification": None,
            "error": error,
        }

    if source_path.suffix.lower() == ".dump":
        return run_postgresql_restore_drill(
            os.getenv("DATABASE_URL"),
            source_path,
            BACKUP_REQUIRED_TABLES,
        )

    try:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir) / source_path.name
            shutil.copy2(source_path, temp_path)
            verification = verify_database_backup_file(temp_path)
    except OSError:
        return {
            "status": "critical",
            "status_label": "Ошибка копирования",
            "message": "Не удалось скопировать backup во временную папку.",
            "file": source_path.name,
            "verification": None,
            "error": "restore_check_failed",
        }

    if verification["status"] == "ok":
        return {
            "status": "ok",
            "status_label": "Восстановление проверено",
            "message": (
                "Копия успешно скопирована во временную папку и открыта."
            ),
            "file": source_path.name,
            "verification": verification,
            "error": "",
        }

    return {
        "status": "critical",
        "status_label": "Проверка провалена",
        "message": verification["message"],
        "file": source_path.name,
        "verification": verification,
        "error": "restore_check_failed",
    }


def make_release_readiness_check(
    key,
    title,
    status,
    description,
    action,
    url,
    weight=10,
    category="core",
    category_label="Основа",
):
    labels = {
        "ok": "Готово",
        "warning": "Внимание",
        "critical": "Критично",
    }
    points = {
        "ok": weight,
        "warning": weight * 0.5,
        "critical": 0,
    }
    normalized_status = (
        status if status in labels else "warning"
    )

    return {
        "key": key,
        "title": title,
        "status": normalized_status,
        "status_label": labels[normalized_status],
        "description": description,
        "action": action,
        "url": url,
        "weight": weight,
        "points": points[normalized_status],
        "category": category,
        "category_label": category_label,
    }


def make_system_check(
    key,
    title,
    status,
    value,
    description,
    action,
    url,
):
    labels = {
        "ok": "ОК",
        "warning": "Внимание",
        "critical": "Критично",
    }
    normalized_status = status if status in labels else "warning"

    return {
        "key": key,
        "title": title,
        "status": normalized_status,
        "status_label": labels[normalized_status],
        "value": value,
        "description": description,
        "action": action,
        "url": url,
    }


def get_platform_release_readiness(
    counts=None,
    calendar_health_summary=None,
    a3_health_summary=None,
):
    counts = counts or {}
    conn = connect()
    c = conn.cursor()

    if not counts:
        counts = {
            "companies": c.execute(
                "SELECT COUNT(*) FROM companies"
            ).fetchone()[0],
            "users": c.execute(
                "SELECT COUNT(*) FROM users"
            ).fetchone()[0],
            "tasks": c.execute(
                "SELECT COUNT(*) FROM tasks"
            ).fetchone()[0],
            "clients": c.execute(
                "SELECT COUNT(*) FROM clients"
            ).fetchone()[0],
        }

    platform_admins = c.execute("""
    SELECT COUNT(*)
    FROM users
    WHERE role='superadmin'
      AND COALESCE(is_active, 1)=1
    """).fetchone()[0]
    users_without_company = c.execute("""
    SELECT COUNT(*)
    FROM users
    WHERE role!='superadmin'
      AND company_id IS NULL
    """).fetchone()[0]
    conn.close()

    if calendar_health_summary is None:
        calendar_health_summary = get_platform_calendar_health()[
            "summary"
        ]
    if a3_health_summary is None:
        a3_health_summary = get_a3_platform_health()["summary"]

    production_config = get_production_config_status()
    object_storage_status = production_config["object_storage_status"]
    env_name = production_config["environment"]
    telegram_configured = production_config["telegram_configured"]
    default_secret = production_config["secret_is_weak"]
    cron_secret_configured = (
        production_config["automation_cron_secret_configured"]
    )
    security_config = production_config["security_config"]
    backup_status = get_backup_status()
    background_queue_status = get_background_queue_status()

    checks = [
        make_release_readiness_check(
            "secret_key",
            "Секрет приложения",
            "critical" if default_secret else "ok",
            (
                "SECRET_KEY отсутствует или короче 32 символов."
                if default_secret
                else "SECRET_KEY настроен."
            ),
            "Перед боевым запуском задайте SECRET_KEY длиной от 32 символов.",
            "/system",
            14,
            "security",
            "Безопасность",
        ),
        make_release_readiness_check(
            "secure_cookie",
            "Безопасные cookie",
            "ok" if COOKIE_SECURE else "warning",
            (
                "Защита cookie включена."
                if COOKIE_SECURE
                else "Защита cookie не включена в текущем окружении."
            ),
            "Для боевого режима включите COOKIE_SECURE или Railway окружение.",
            "/system",
            8,
            "security",
            "Безопасность",
        ),
        make_release_readiness_check(
            "trusted_hosts",
            "Разрешённые домены",
            (
                "ok"
                if security_config["trusted_hosts_configured"]
                else "critical"
            ),
            (
                "Host-заголовок ограничен: "
                + ", ".join(security_config["trusted_hosts"])
                if security_config["trusted_hosts_configured"]
                else "TRUSTED_HOSTS и APP_BASE_URL не настроены."
            ),
            "Задайте production-домены до допуска релиза.",
            "/system",
            8,
            "security",
            "Безопасность",
        ),
        make_release_readiness_check(
            "database",
            "База данных",
            "ok" if backup_status["db_exists"] else "critical",
            (
                f"{backup_status['backend_label']} база доступна."
                if backup_status["db_exists"]
                else f"{backup_status['backend_label']} база недоступна."
            ),
            "Проверьте подключение к базе данных и запуск init_db.",
            "/system",
            12,
            "infrastructure",
            "Инфраструктура",
        ),
        make_release_readiness_check(
            "platform_admins",
            "Администраторы платформы",
            "ok" if platform_admins else "critical",
            f"Активных superadmin: {platform_admins}.",
            "Должен быть хотя бы один активный superadmin.",
            "/debug",
            12,
            "security",
            "Безопасность",
        ),
        make_release_readiness_check(
            "tenant_data",
            "Рабочие данные",
            "ok" if counts["companies"] and counts["users"] else "warning",
            (
                f"Компаний: {counts['companies']}, "
                f"пользователей: {counts['users']}."
            ),
            "Создайте первую компанию и владельца.",
            "/platform/companies",
            10,
            "business",
            "Бизнес-данные",
        ),
        make_release_readiness_check(
            "company_isolation",
            "Изоляция компаний",
            "ok" if users_without_company == 0 else "critical",
            (
                "Все обычные пользователи привязаны к компаниям."
                if users_without_company == 0
                else (
                    "Пользователей без company_id: "
                    f"{users_without_company}."
                )
            ),
            "Исправьте пользователей без company_id перед релизом.",
            "/debug",
            12,
            "security",
            "Безопасность",
        ),
        make_release_readiness_check(
            "telegram",
            "Telegram уведомления",
            "ok" if telegram_configured else "warning",
            (
                "BOT_TOKEN и CHAT_ID настроены."
                if telegram_configured
                else "BOT_TOKEN или CHAT_ID не настроены."
            ),
            "Добавьте Telegram переменные окружения.",
            "/system",
            8,
            "integrations",
            "Интеграции",
        ),
        make_release_readiness_check(
            "automation_cron_secret",
            "Фоновые запуски",
            "ok" if cron_secret_configured else "warning",
            (
                "Секрет фоновых запусков настроен."
                if cron_secret_configured
                else "Секрет фоновых запусков не настроен."
            ),
            "Укажите AUTOMATION_CRON_SECRET для расписаний и дайджестов.",
            "/system",
            7,
            "operations",
            "Операции",
        ),
        make_release_readiness_check(
            "background_jobs",
            "Фоновая очередь",
            background_queue_status["status"],
            (
                f"Ожидают: {background_queue_status['pending']}; "
                f"в работе: {background_queue_status['running']}; "
                f"ошибок за 24 часа: {background_queue_status['failed_24h']}."
            ),
            (
                "Подключите worker или cron "
                "/automation/cron/background-jobs."
            ),
            "/system",
            7,
            "operations",
            "Операции",
        ),
        make_release_readiness_check(
            "platform_billing_reminder_cron",
            "Cron напоминаний по счетам",
            "ok" if cron_secret_configured else "warning",
            (
                "Endpoint напоминаний по счетам готов к плановому запуску."
                if cron_secret_configured
                else (
                    "Напоминания по счетам есть, но cron secret "
                    "ещё не настроен."
                )
            ),
            (
                "Подключите Railway cron на "
                "/automation/cron/platform-billing-reminders."
            ),
            "/system",
            4,
            "operations",
            "Операции",
        ),
        make_release_readiness_check(
            "uploads",
            "Хранилище файлов",
            object_storage_status["status"],
            object_storage_status["message"],
            "Проверьте backend, bucket и права файлового хранилища.",
            "/system",
            8,
            "infrastructure",
            "Инфраструктура",
        ),
        make_release_readiness_check(
            "calendar_ops",
            "Операционный контроль",
            (
                "critical"
                if calendar_health_summary["overall_status_code"]
                == "critical"
                else (
                    "warning"
                    if calendar_health_summary["problems"]
                    else "ok"
                )
            ),
            (
                "Состояние календарных автоматизаций: "
                f"{calendar_health_summary['overall_status_label']}."
            ),
            "Разберите критичные календарные инциденты.",
            "/platform/calendar-health",
            10,
            "operations",
            "Операции",
        ),
        make_release_readiness_check(
            "a3_scheduler_health",
            "Фоновые процессы A3",
            (
                "critical"
                if (
                    a3_health_summary.get("critical", 0)
                    or a3_health_summary.get("active_critical_incidents", 0)
                )
                else (
                    "warning"
                    if (
                        a3_health_summary.get("problems", 0)
                        or a3_health_summary.get("active_incidents", 0)
                    )
                    else "ok"
                )
            ),
            (
                f"Компаний: {a3_health_summary.get('total', 0)}. "
                f"Стабильно: {a3_health_summary.get('stable', 0)}. "
                "Требуют внимания: "
                f"{a3_health_summary.get('problems', 0)}. "
                "Активных инцидентов: "
                f"{a3_health_summary.get('active_incidents', 0)}. "
                "Просрочена реакция: "
                f"{a3_health_summary.get('response_overdue_incidents', 0)}. "
                "Эскалировано: "
                f"{a3_health_summary.get('escalated_incidents', 0)}. "
                "Приостановлено: "
                f"{a3_health_summary.get('paused', 0)}."
            ),
            "Проверьте основной планировщик и контрольные запуски A3.",
            (
                "/platform/a3-health/incidents"
                if a3_health_summary.get("active_incidents", 0)
                else "/platform/a3-health"
            ),
            10,
            "operations",
            "Операции",
        ),
        make_release_readiness_check(
            "backups",
            "Резервные копии",
            backup_status["status"],
            (
                f"{backup_status['summary']} "
                f"Последняя копия: {backup_status['latest_age_label']}. "
                f"Всего копий: {backup_status['count']}."
            ),
            backup_status["action"],
            "/backup",
            8,
            "infrastructure",
            "Инфраструктура",
        ),
        make_release_readiness_check(
            "backup_restore_check",
            "Проверка восстановления",
            backup_status["restore_check"]["status"],
            backup_status["restore_check"]["message"],
            "Запустите проверку восстановления последней копии.",
            "/backup",
            8,
            "infrastructure",
            "Инфраструктура",
        ),
    ]
    total_weight = sum(item["weight"] for item in checks) or 1
    score = round(
        sum(item["points"] for item in checks) * 100 / total_weight
    )
    critical_count = sum(
        1 for item in checks if item["status"] == "critical"
    )
    warning_count = sum(
        1 for item in checks if item["status"] == "warning"
    )
    categories_map = {}

    for check in checks:
        category = categories_map.setdefault(
            check["category"],
            {
                "key": check["category"],
                "label": check["category_label"],
                "checks": 0,
                "ok": 0,
                "warning": 0,
                "critical": 0,
                "weight": 0,
                "points": 0,
            },
        )
        category["checks"] += 1
        category[check["status"]] += 1
        category["weight"] += check["weight"]
        category["points"] += check["points"]

    categories = []

    for category in categories_map.values():
        category["score"] = round(
            category["points"] * 100 / category["weight"],
        ) if category["weight"] else 0
        if category["critical"]:
            category["status"] = "critical"
            category["status_label"] = "Критично"
        elif category["warning"]:
            category["status"] = "warning"
            category["status_label"] = "Внимание"
        else:
            category["status"] = "ok"
            category["status_label"] = "Готово"
        categories.append(category)

    categories.sort(
        key=lambda item: (
            {"critical": 0, "warning": 1, "ok": 2}[item["status"]],
            item["label"],
        )
    )
    action_priority = {
        "critical": 0,
        "warning": 1,
        "ok": 2,
    }
    blockers = [
        item for item in checks if item["status"] == "critical"
    ]
    next_actions = sorted(
        [item for item in checks if item["status"] != "ok"],
        key=lambda item: (
            action_priority[item["status"]],
            -item["weight"],
            item["title"],
        ),
    )[:6]

    if critical_count:
        status = "critical"
        status_label = "Требует подготовки"
        headline = "До релиза нужно закрыть критичные блокеры."
    elif warning_count:
        status = "warning"
        status_label = "Почти готово"
        headline = "Критичных блокеров нет, но есть задачи перед релизом."
    else:
        status = "ok"
        status_label = "Готово к релизу"
        headline = "Ключевые проверки готовы к запуску."

    return {
        "score": score,
        "status": status,
        "status_label": status_label,
        "headline": headline,
        "checks": checks,
        "categories": categories,
        "blockers": blockers,
        "next_actions": next_actions,
        "critical_count": critical_count,
        "warning_count": warning_count,
        "ok_count": sum(1 for item in checks if item["status"] == "ok"),
        "environment": env_name,
        "backup_status": backup_status,
        "a3_health_summary": a3_health_summary,
        "export_url": "/platform/readiness/export",
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
    }


def build_platform_readiness_links(snapshot_id=None):
    links = {
        "platform": "/platform",
        "system": "/system",
        "page": "/platform/readiness",
        "snapshot": "/platform/readiness/snapshot",
        "signoff": "/platform/readiness/signoff",
        "export": "/platform/readiness/export",
        "a3_health": "/platform/a3-health",
        "calendar_health": "/platform/calendar-health",
    }

    if snapshot_id is not None:
        snapshot_id = int(snapshot_id or 0)
        links["snapshot_page"] = f"/platform/readiness/snapshots/{snapshot_id}"
        links["snapshot_export"] = (
            f"/platform/readiness/snapshots/{snapshot_id}/export"
        )

    return links


def make_release_launch_item(
    title,
    description,
    url,
    status="warning",
):
    labels = {
        "ok": "Готово",
        "warning": "Внимание",
        "critical": "Критично",
    }
    normalized_status = status if status in labels else "warning"
    return {
        "title": title,
        "description": description,
        "url": url,
        "status": normalized_status,
        "status_label": labels[normalized_status],
    }


def get_platform_release_launch_plan(readiness):
    checks_by_key = {
        item["key"]: item for item in readiness["checks"]
    }
    categories_by_key = {
        item["key"]: item for item in readiness["categories"]
    }
    score = int(readiness["score"] or 0)
    critical_count = int(readiness["critical_count"] or 0)
    warning_count = int(readiness["warning_count"] or 0)
    calendar_check = checks_by_key.get("calendar_ops", {})
    a3_check = checks_by_key.get("a3_scheduler_health", {})
    security_category = categories_by_key.get("security", {})
    blockers = sorted(
        readiness["blockers"],
        key=lambda item: (-item["weight"], item["title"]),
    )
    warnings = sorted(
        [
            item for item in readiness["checks"]
            if item["status"] == "warning"
        ],
        key=lambda item: (-item["weight"], item["title"]),
    )

    if critical_count:
        decision = "blocked"
        label = "Запуск заблокирован"
        tone = "critical"
        recommended_mode = "Не запускать боевой режим"
        summary = "Сначала нужно закрыть критичные блокеры."
    elif score < 80 or warning_count >= 4:
        decision = "pilot"
        label = "Только пилот"
        tone = "warning"
        recommended_mode = "Закрытый пилот"
        summary = "Критичных блокеров нет, но релиз лучше начинать с пилота."
    else:
        decision = "ready"
        label = "Можно запускать"
        tone = "ok"
        recommended_mode = "Боевой запуск"
        summary = "Ключевые проверки позволяют запускать платформу."

    gates = [
        make_release_launch_item(
            "Критичных блокеров нет",
            (
                "Критичные блокеры отсутствуют."
                if critical_count == 0
                else f"Критичных блокеров: {critical_count}."
            ),
            "/platform/readiness",
            "ok" if critical_count == 0 else "critical",
        ),
        make_release_launch_item(
            "Оценка готовности не ниже 80%",
            f"Текущая оценка готовности: {score}%.",
            "/platform/readiness",
            "ok" if score >= 80 else "warning",
        ),
        make_release_launch_item(
            "Безопасность не критична",
            (
                "Критичных проблем безопасности нет."
                if not security_category.get("critical")
                else (
                    "Критичных проблем безопасности: "
                    f"{security_category['critical']}."
                )
            ),
            "/system",
            "ok" if not security_category.get("critical") else "critical",
        ),
        make_release_launch_item(
            "Операционный контроль стабилен",
            calendar_check.get(
                "description",
                "Проверьте состояние календарных автоматизаций.",
            ),
            "/platform/calendar-health",
            (
                "critical"
                if calendar_check.get("status") == "critical"
                else (
                    "warning"
                    if calendar_check.get("status") == "warning"
                    else "ok"
                )
            ),
        ),
        make_release_launch_item(
            "Фоновые процессы A3 стабильны",
            a3_check.get(
                "description",
                "Проверьте основной планировщик и контрольные запуски A3.",
            ),
            "/platform/a3-health",
            (
                "critical"
                if a3_check.get("status") == "critical"
                else (
                    "warning"
                    if a3_check.get("status") == "warning"
                    else "ok"
                )
            ),
        ),
    ]

    mandatory_items = [
        make_release_launch_item(
            item["title"],
            item["action"],
            item["url"],
            item["status"],
        )
        for item in blockers
    ]
    if not mandatory_items:
        mandatory_items = [
            make_release_launch_item(
                "Критичные блокеры закрыты",
                "Можно переходить к предрелизной подготовке.",
                "/platform/readiness",
                "ok",
            ),
        ]

    preparation_items = [
        make_release_launch_item(
            item["title"],
            item["action"],
            item["url"],
            item["status"],
        )
        for item in warnings[:5]
    ]
    preparation_items.extend([
        make_release_launch_item(
            "Сохранить финальный снимок",
            "Зафиксируйте состояние готовности перед выкладкой.",
            "/platform/readiness",
            "warning",
        ),
        make_release_launch_item(
            "Экспортировать CSV отчёт",
            "Сохраните список проверок и действий для контроля релиза.",
            "/platform/readiness/export",
            "warning",
        ),
    ])

    monitoring_items = [
        make_release_launch_item(
            "Проверить фоновые процессы A3",
            "Убедитесь, что основной и контрольный запуски продолжаются.",
            "/platform/a3-health",
            "warning",
        ),
        make_release_launch_item(
            "Проверить инциденты календаря",
            "После запуска следите за критичными инцидентами компаний.",
            "/platform/calendar-health",
            "warning",
        ),
        make_release_launch_item(
            "Проверить системные настройки",
            "Убедитесь, что окружение и интеграции работают после публикации.",
            "/system",
            "warning",
        ),
        make_release_launch_item(
            "Повторить проверку готовности после первых клиентов",
            "Сохраните новый снимок и сравните динамику.",
            "/platform/readiness",
            "warning",
        ),
    ]

    phases = [
        {
            "key": "decision",
            "title": "Решение по запуску",
            "status": tone,
            "status_label": label,
            "items": gates,
        },
        {
            "key": "mandatory",
            "title": "Обязательные исправления",
            "status": "critical" if blockers else "ok",
            "status_label": (
                "Нужно исправить" if blockers else "Готово"
            ),
            "items": mandatory_items,
        },
        {
            "key": "preparation",
            "title": "Предрелизная подготовка",
            "status": "warning" if preparation_items else "ok",
            "status_label": "Подготовка",
            "items": preparation_items,
        },
        {
            "key": "monitoring",
            "title": "Мониторинг после запуска",
            "status": "warning",
            "status_label": "Контроль",
            "items": monitoring_items,
        },
    ]

    next_items = []
    for phase in phases:
        for item in phase["items"]:
            if item["status"] != "ok":
                next_items.append({
                    "phase": phase["title"],
                    **item,
                })

    return {
        "decision": decision,
        "label": label,
        "tone": tone,
        "summary": summary,
        "recommended_mode": recommended_mode,
        "score": score,
        "critical_count": critical_count,
        "warning_count": warning_count,
        "gates": gates,
        "phases": phases,
        "next_items": next_items[:8],
        "blocked": decision == "blocked",
    }


def get_platform_release_signoff_decision(decision):
    decisions = {
        "blocked": {
            "decision": "blocked",
            "label": "Запуск отложен",
            "tone": "critical",
        },
        "pilot": {
            "decision": "pilot",
            "label": "Подтверждён пилот",
            "tone": "warning",
        },
        "production": {
            "decision": "production",
            "label": "Подтверждён боевой запуск",
            "tone": "ok",
        },
    }
    return decisions.get(decision, decisions["blocked"])


def get_platform_release_signoff_history(limit=6, snapshot_id=None):
    conn = connect()
    c = conn.cursor()

    if snapshot_id:
        rows = c.execute("""
        SELECT *
        FROM platform_release_signoffs
        WHERE snapshot_id=?
        ORDER BY id DESC
        LIMIT ?
        """, (snapshot_id, limit)).fetchall()
    else:
        rows = c.execute("""
        SELECT *
        FROM platform_release_signoffs
        ORDER BY id DESC
        LIMIT ?
        """, (limit,)).fetchall()

    conn.close()
    history = [dict(row) for row in rows]

    for item in history:
        decision = get_platform_release_signoff_decision(item["decision"])
        item["tone"] = decision["tone"]
        item["snapshot_url"] = (
            f"/platform/readiness/snapshots/{item['snapshot_id']}"
            if item.get("snapshot_id")
            else ""
        )

    return history


def create_platform_release_signoff(username, decision, comment=""):
    readiness = get_platform_release_readiness()
    launch_plan = get_platform_release_launch_plan(readiness)
    decision_data = get_platform_release_signoff_decision(decision)

    if launch_plan["blocked"] and decision_data["decision"] != "blocked":
        return None, "launch_blocked"

    snapshot_id = create_platform_release_readiness_snapshot(
        username,
        readiness,
    )
    payload = {
        "readiness": {
            "score": readiness["score"],
            "status": readiness["status"],
            "status_label": readiness["status_label"],
            "critical_count": readiness["critical_count"],
            "warning_count": readiness["warning_count"],
            "headline": readiness["headline"],
            "generated_at": readiness["generated_at"],
        },
        "launch_plan": launch_plan,
    }
    normalized_comment = str(comment or "").strip()[:800]
    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    conn = connect()
    c = conn.cursor()
    c.execute("""
    INSERT INTO platform_release_signoffs (
        snapshot_id,
        decision,
        decision_label,
        recommended_mode,
        score,
        critical_count,
        warning_count,
        comment,
        signed_by,
        signed_at,
        payload_json
    )
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        snapshot_id,
        decision_data["decision"],
        decision_data["label"],
        launch_plan["recommended_mode"],
        readiness["score"],
        readiness["critical_count"],
        readiness["warning_count"],
        normalized_comment,
        username,
        now,
        json.dumps(payload, ensure_ascii=False),
    ))
    signoff_id = c.lastrowid
    conn.commit()
    conn.close()

    return signoff_id, ""


def get_platform_release_timeline(history=None, signoffs=None, limit=12):
    history = (
        history
        if history is not None
        else get_platform_release_readiness_history()
    )
    signoffs = (
        signoffs
        if signoffs is not None
        else get_platform_release_signoff_history()
    )
    events = []

    for snapshot in history:
        events.append({
            "type": "snapshot",
            "type_label": "Снимок",
            "title": f"Снимок готовности {snapshot['score']}%",
            "description": snapshot["headline"] or "",
            "at": snapshot["created_at"],
            "actor": snapshot["created_by"] or "система",
            "tone": snapshot["status"],
            "badge": snapshot["status_label"],
            "url": snapshot["detail_url"],
            "score": int(snapshot["score"] or 0),
            "order": int(snapshot["id"] or 0),
        })

    for signoff in signoffs:
        comment = str(signoff.get("comment") or "").strip()
        description = (
            f"{signoff['recommended_mode']}. "
            f"Оценка: {signoff['score']}%."
        )
        if comment:
            description = f"{description} {comment}"
        events.append({
            "type": "signoff",
            "type_label": "Решение",
            "title": signoff["decision_label"],
            "description": description,
            "at": signoff["signed_at"],
            "actor": signoff["signed_by"] or "система",
            "tone": signoff["tone"],
            "badge": signoff["recommended_mode"],
            "url": signoff["snapshot_url"] or "/platform/readiness",
            "score": int(signoff["score"] or 0),
            "order": int(signoff["id"] or 0),
        })

    events.sort(
        key=lambda item: (
            item["at"] or "",
            item["order"],
            item["type"],
        ),
        reverse=True,
    )
    latest = events[0] if events else None
    latest_signoff = next(
        (event for event in events if event["type"] == "signoff"),
        None,
    )

    return {
        "events": events[:limit],
        "total_events": len(events),
        "snapshots_count": len(history),
        "signoffs_count": len(signoffs),
        "latest_label": latest["title"] if latest else "Событий пока нет",
        "latest_at": latest["at"] if latest else "",
        "latest_tone": latest["tone"] if latest else "warning",
        "latest_signoff_label": (
            latest_signoff["title"] if latest_signoff else "Решений пока нет"
        ),
        "latest_signoff_at": latest_signoff["at"] if latest_signoff else "",
    }


def make_release_runbook_step(
    title,
    description,
    url,
    status="warning",
    owner="Администратор платформы",
):
    labels = {
        "ok": "Готово",
        "warning": "Выполнить",
        "critical": "Блокер",
    }
    normalized_status = status if status in labels else "warning"
    return {
        "title": title,
        "description": description,
        "url": url,
        "status": normalized_status,
        "status_label": labels[normalized_status],
        "owner": owner,
    }


def get_platform_release_runbook(
    readiness=None,
    launch_plan=None,
    timeline=None,
):
    readiness = readiness or get_platform_release_readiness()
    launch_plan = launch_plan or get_platform_release_launch_plan(readiness)
    timeline = timeline or get_platform_release_timeline()
    has_signoff = timeline["signoffs_count"] > 0
    blocked = launch_plan["blocked"]
    score = int(readiness["score"] or 0)
    critical_count = int(readiness["critical_count"] or 0)
    warning_count = int(readiness["warning_count"] or 0)
    checks_by_key = {
        item["key"]: item for item in readiness["checks"]
    }
    billing_cron_check = checks_by_key.get(
        "platform_billing_reminder_cron",
        {},
    )
    a3_check = checks_by_key.get("a3_scheduler_health", {})

    if blocked:
        status = "critical"
        label = "Запуск нельзя проводить"
        summary = "Регламент готов, но сначала нужно закрыть критичные блокеры."
    elif score < 80 or warning_count >= 4:
        status = "warning"
        label = "Запускать только пилот"
        summary = "Запуск возможен как закрытый пилот с усиленным контролем."
    else:
        status = "ok"
        label = "Регламент готов"
        summary = "Можно идти по сценарию запуска и мониторинга."

    sections = [
        {
            "key": "preflight",
            "title": "Перед запуском",
            "status": "critical" if blocked else "warning",
            "status_label": "Подготовка",
            "steps": [
                make_release_runbook_step(
                    "Закрыть критичные блокеры",
                    (
                        "Критичных блокеров нет."
                        if critical_count == 0
                        else f"Критичных блокеров: {critical_count}."
                    ),
                    "/platform/readiness",
                    "ok" if critical_count == 0 else "critical",
                ),
                make_release_runbook_step(
                    "Сохранить финальный снимок",
                    "Зафиксируйте состояние платформы перед релизом.",
                    "/platform/readiness",
                    "warning",
                ),
                make_release_runbook_step(
                    "Экспортировать отчёт готовности",
                    "Сохраните отчёт готовности для контроля и разбора после запуска.",
                    "/platform/readiness/export",
                    "warning",
                ),
                make_release_runbook_step(
                    "Зафиксировать решение запуска",
                    (
                        "Решение уже зафиксировано."
                        if has_signoff
                        else "Сохраните подтверждение перед запуском."
                    ),
                    "/platform/readiness",
                    "ok" if has_signoff else "warning",
                ),
                make_release_runbook_step(
                    "Подключить cron счетов",
                    (
                        "Cron напоминаний по счетам готов."
                        if billing_cron_check.get("status") == "ok"
                        else (
                            "Добавьте Railway schedule для "
                            "POST /automation/cron/platform-billing-reminders."
                        )
                    ),
                    "/system",
                    (
                        "ok"
                        if billing_cron_check.get("status") == "ok"
                        else "warning"
                    ),
                ),
                make_release_runbook_step(
                    "Проверить фоновые процессы A3",
                    a3_check.get(
                        "description",
                        "Проверьте основной и контрольный запуски A3.",
                    ),
                    "/platform/a3-health",
                    a3_check.get("status", "warning"),
                ),
            ],
        },
        {
            "key": "launch",
            "title": "Во время запуска",
            "status": "critical" if blocked else "warning",
            "status_label": launch_plan["recommended_mode"],
            "steps": [
                make_release_runbook_step(
                    "Выполнить публикацию",
                    "Выкатите текущую основную ветку в рабочее окружение.",
                    "/system",
                    "critical" if blocked else "warning",
                ),
                make_release_runbook_step(
                    "Проверить вход суперадмина",
                    "После публикации проверьте вход владельца платформы.",
                    "/platform",
                    "warning",
                ),
                make_release_runbook_step(
                    "Проверить системные настройки",
                    "Проверьте переменные окружения, загрузки файлов и интеграции.",
                    "/system",
                    "warning",
                ),
                make_release_runbook_step(
                    "Проверить операционный контроль",
                    "Убедитесь, что нет критичных календарных инцидентов.",
                    "/platform/calendar-health",
                    "warning",
                ),
                make_release_runbook_step(
                    "Проверить выполнение A3",
                    "Убедитесь, что фоновые и контрольные запуски не остановились.",
                    "/platform/a3-health",
                    "warning",
                ),
            ],
        },
        {
            "key": "rollback",
            "title": "Откат",
            "status": "warning",
            "status_label": "План отката",
            "steps": [
                make_release_runbook_step(
                    "Остановить новые подключения",
                    "Если появились критичные ошибки, временно остановите запуск новых компаний.",
                    "/platform",
                    "warning",
                ),
                make_release_runbook_step(
                    "Вернуть предыдущую публикацию",
                    "Откатите рабочее окружение на предыдущую стабильную версию.",
                    "/system",
                    "warning",
                ),
                make_release_runbook_step(
                    "Сохранить аварийный снимок",
                    "После отката сохраните снимок готовности для разбора.",
                    "/platform/readiness",
                    "warning",
                ),
                make_release_runbook_step(
                    "Проверить инциденты",
                    "Разберите календарные и системные инциденты после отката.",
                    "/platform/calendar-health",
                    "warning",
                ),
            ],
        },
        {
            "key": "aftercare",
            "title": "После запуска",
            "status": "warning",
            "status_label": "Контроль",
            "steps": [
                make_release_runbook_step(
                    "Повторить проверку готовности",
                    "Сохраните новый снимок после первых рабочих действий.",
                    "/platform/readiness",
                    "warning",
                ),
                make_release_runbook_step(
                    "Проверить журнал релиза",
                    "Убедитесь, что снимки и решения видны в журнале.",
                    "/platform/readiness",
                    "ok" if timeline["total_events"] else "warning",
                ),
                make_release_runbook_step(
                    "Проверить инциденты платформы",
                    "Контролируйте активные проблемы компаний после запуска.",
                    "/platform/calendar-health",
                    "warning",
                ),
                make_release_runbook_step(
                    "Проверить стабильность A3",
                    "Проверьте свежесть основного и контрольного запусков по компаниям.",
                    "/platform/a3-health",
                    "warning",
                ),
                make_release_runbook_step(
                    "Экспортировать финальный отчёт",
                    "Сохраните CSV после проверки первых клиентов.",
                    "/platform/readiness/export",
                    "warning",
                ),
            ],
        },
    ]

    steps = [
        step
        for section in sections
        for step in section["steps"]
    ]
    next_steps = [
        {
            "section": section["title"],
            **step,
        }
        for section in sections
        for step in section["steps"]
        if step["status"] != "ok"
    ][:8]
    rollback_triggers = [
        "Появился новый критичный блокер готовности.",
        "Вход суперадмина или владельца компании перестал работать.",
        "Появились критичные календарные инциденты.",
        "Основной планировщик или контрольные запуски A3 остановились.",
        "Интеграции или загрузки файлов перестали работать после публикации.",
        "Оценка готовности упала относительно финального снимка.",
    ]

    return {
        "status": status,
        "label": label,
        "summary": summary,
        "mode": launch_plan["recommended_mode"],
        "score": score,
        "critical_count": critical_count,
        "warning_count": warning_count,
        "has_signoff": has_signoff,
        "sections": sections,
        "next_steps": next_steps,
        "rollback_triggers": rollback_triggers,
        "steps_count": len(steps),
        "critical_steps_count": sum(
            1 for step in steps if step["status"] == "critical"
        ),
    }


def make_release_control_item(
    title,
    description,
    value="",
    status="warning",
    url="/platform/readiness",
):
    labels = {
        "ok": "Норма",
        "warning": "Контроль",
        "critical": "Стоп",
    }
    normalized_status = status if status in labels else "warning"
    return {
        "title": title,
        "description": description,
        "value": value,
        "status": normalized_status,
        "status_label": labels[normalized_status],
        "url": url,
    }


def get_platform_release_control_center(
    readiness=None,
    launch_plan=None,
    timeline=None,
    runbook=None,
):
    readiness = readiness or get_platform_release_readiness()
    launch_plan = launch_plan or get_platform_release_launch_plan(readiness)
    timeline = timeline or get_platform_release_timeline()
    runbook = runbook or get_platform_release_runbook(
        readiness,
        launch_plan,
        timeline,
    )
    checks_by_key = {
        item["key"]: item for item in readiness["checks"]
    }
    categories_by_key = {
        item["key"]: item for item in readiness["categories"]
    }
    score = int(readiness["score"] or 0)
    critical_count = int(readiness["critical_count"] or 0)
    warning_count = int(readiness["warning_count"] or 0)
    blocked = bool(launch_plan["blocked"])
    has_signoff = bool(runbook["has_signoff"])
    calendar_check = checks_by_key.get("calendar_ops", {})
    a3_check = checks_by_key.get("a3_scheduler_health", {})
    security_category = categories_by_key.get("security", {})
    calendar_status = calendar_check.get("status", "warning")
    a3_status = a3_check.get("status", "warning")

    if blocked:
        status = "critical"
        label = "Запуск остановлен"
        risk_level = "Высокий"
        summary = "Есть критичные блокеры. Публикацию проводить нельзя."
    elif not has_signoff:
        status = "warning"
        label = "Нужно решение"
        risk_level = "Средний"
        summary = "Перед запуском нужно зафиксировать управленческое решение."
    elif score < 90 or warning_count:
        status = "warning"
        label = "Запуск под контролем"
        risk_level = "Умеренный"
        summary = "Запуск возможен, но первые часы нужно контролировать вручную."
    else:
        status = "ok"
        label = "Контроль готов"
        risk_level = "Низкий"
        summary = "Ключевые сигналы стабильны, можно идти по плану запуска."

    metrics = [
        make_release_control_item(
            "Оценка готовности",
            "Общая оценка предрелизных проверок.",
            f"{score}%",
            "ok" if score >= 90 else ("warning" if score >= 75 else "critical"),
            "/platform/readiness",
        ),
        make_release_control_item(
            "Критичные блокеры",
            "Проверки, которые останавливают запуск.",
            str(critical_count),
            "ok" if critical_count == 0 else "critical",
            "/platform/readiness",
        ),
        make_release_control_item(
            "Предупреждения",
            "Некритичные задачи, которые нужно держать под контролем.",
            str(warning_count),
            "ok" if warning_count == 0 else "warning",
            "/platform/readiness",
        ),
        make_release_control_item(
            "Решение по запуску",
            "Фиксация решения владельцем платформы.",
            "есть" if has_signoff else "нет",
            "ok" if has_signoff else "warning",
            "/platform/readiness",
        ),
        make_release_control_item(
            "Операционный контроль",
            calendar_check.get(
                "description",
                "Состояние календарных автоматизаций.",
            ),
            calendar_check.get("status_label", "Проверить"),
            (
                "critical"
                if calendar_status == "critical"
                else ("warning" if calendar_status == "warning" else "ok")
            ),
            "/platform/calendar-health",
        ),
        make_release_control_item(
            "Фоновые процессы A3",
            a3_check.get(
                "description",
                "Состояние основного и контрольного запусков A3.",
            ),
            a3_check.get("status_label", "Проверить"),
            (
                "critical"
                if a3_status == "critical"
                else ("warning" if a3_status == "warning" else "ok")
            ),
            "/platform/a3-health",
        ),
        make_release_control_item(
            "Безопасность",
            "Состояние проверок безопасности перед запуском.",
            security_category.get("status_label", "Проверить"),
            (
                "critical"
                if security_category.get("critical")
                else (
                    "warning"
                    if security_category.get("warning")
                    else "ok"
                )
            ),
            "/system",
        ),
    ]

    checkpoints = [
        make_release_control_item(
            "За сутки до запуска",
            "Закрыть критичные блокеры и сохранить финальный снимок.",
            "T-24 часа",
            "critical" if critical_count else "warning",
            "/platform/readiness",
        ),
        make_release_control_item(
            "За час до запуска",
            "Проверить вход суперадмина, системные настройки и решение.",
            "T-1 час",
            (
                "critical"
                if critical_count
                else ("ok" if has_signoff else "warning")
            ),
            "/platform/readiness",
        ),
        make_release_control_item(
            "Первые 30 минут",
            "Проверить авторизацию, A3, календарь, уведомления и загрузки файлов.",
            "T+30 минут",
            "warning",
            "/system",
        ),
        make_release_control_item(
            "Первые 24 часа",
            "Сравнить новый снимок с финальным и проверить инциденты.",
            "T+24 часа",
            "warning",
            "/platform/calendar-health",
        ),
    ]

    watch_focus = [
        make_release_control_item(
            item["title"],
            item["action"],
            item["category_label"],
            item["status"],
            item["url"],
        )
        for item in readiness["next_actions"][:5]
    ]
    if not watch_focus:
        watch_focus = [
            make_release_control_item(
                "Контроль стабильности",
                "Критичных задач нет, держите под наблюдением первые действия клиентов.",
                "Мониторинг",
                "ok",
                "/platform/readiness",
            ),
        ]

    stop_conditions = [
        "Появился новый критичный блокер готовности.",
        "Оценка готовности упала ниже 75%.",
        "Календарные инциденты стали критичными.",
        "Фоновые или контрольные запуски A3 остановились.",
        "Суперадмин или владелец компании не может войти в систему.",
        "Загрузки файлов или уведомления перестали работать.",
    ]
    next_checkpoint = next(
        (item for item in checkpoints if item["status"] != "ok"),
        checkpoints[-1],
    )

    return {
        "status": status,
        "label": label,
        "summary": summary,
        "risk_level": risk_level,
        "mode": launch_plan["recommended_mode"],
        "score": score,
        "has_signoff": has_signoff,
        "latest_event": timeline["latest_label"],
        "latest_event_at": timeline["latest_at"],
        "metrics": metrics,
        "checkpoints": checkpoints,
        "next_checkpoint": next_checkpoint,
        "watch_focus": watch_focus,
        "stop_conditions": stop_conditions,
    }


def make_release_review_item(
    title,
    description,
    value="",
    status="warning",
    url="/platform/readiness",
):
    labels = {
        "ok": "Хорошо",
        "warning": "Нужно проверить",
        "critical": "Проблема",
    }
    normalized_status = status if status in labels else "warning"
    return {
        "title": title,
        "description": description,
        "value": value,
        "status": normalized_status,
        "status_label": labels[normalized_status],
        "url": url,
    }


def get_platform_release_post_launch_review(
    readiness=None,
    comparison=None,
    trend=None,
    launch_plan=None,
    timeline=None,
    control_center=None,
    history=None,
    signoffs=None,
):
    readiness = readiness or get_platform_release_readiness()
    comparison = comparison or compare_platform_release_readiness_to_snapshot(
        readiness,
    )
    history = (
        history
        if history is not None
        else get_platform_release_readiness_history()
    )
    trend = trend or get_platform_release_readiness_trend(history)
    launch_plan = launch_plan or get_platform_release_launch_plan(readiness)
    signoffs = (
        signoffs
        if signoffs is not None
        else get_platform_release_signoff_history()
    )
    timeline = timeline or get_platform_release_timeline(history, signoffs)
    control_center = control_center or get_platform_release_control_center(
        readiness,
        launch_plan,
        timeline,
    )
    latest_signoff = signoffs[0] if signoffs else None
    score = int(readiness["score"] or 0)
    critical_count = int(readiness["critical_count"] or 0)
    warning_count = int(readiness["warning_count"] or 0)
    score_delta = int(comparison["score_delta"] or 0)
    critical_delta = int(comparison["critical_delta"] or 0)

    if not latest_signoff:
        status = "warning"
        label = "Разбор ещё рано проводить"
        outcome = "Нет решения по запуску"
        summary = "Сначала зафиксируйте решение по запуску и сохраните снимок."
    elif critical_count or critical_delta > 0 or comparison["tone"] == "critical":
        status = "critical"
        label = "Нужен разбор проблем"
        outcome = "Есть ухудшения"
        summary = "После последнего снимка появились риски или критичные блокеры."
    elif score >= 90 and trend["tone"] == "ok":
        status = "ok"
        label = "Запуск выглядит стабильным"
        outcome = "Положительная динамика"
        summary = "Готовность выросла, критичных сигналов для остановки нет."
    elif warning_count:
        status = "warning"
        label = "Запуск под наблюдением"
        outcome = "Есть предупреждения"
        summary = "Критичных блокеров нет, но часть сигналов требует контроля."
    else:
        status = "ok"
        label = "Разбор без критичных замечаний"
        outcome = "Стабильно"
        summary = "Ключевые показатели не показывают критичных проблем."

    metrics = [
        make_release_review_item(
            "Текущая готовность",
            "Оценка платформы на момент разбора.",
            f"{score}%",
            "ok" if score >= 90 else ("warning" if score >= 75 else "critical"),
            "/platform/readiness",
        ),
        make_release_review_item(
            "Динамика оценки",
            "Изменение относительно последнего сохранённого снимка.",
            str(score_delta),
            "ok" if score_delta > 0 else ("critical" if score_delta < 0 else "warning"),
            comparison["snapshot_url"] or "/platform/readiness",
        ),
        make_release_review_item(
            "Динамика критичных",
            "Изменение числа критичных блокеров после снимка.",
            str(critical_delta),
            "ok" if critical_delta < 0 else ("critical" if critical_delta > 0 else "warning"),
            comparison["snapshot_url"] or "/platform/readiness",
        ),
        make_release_review_item(
            "Последнее решение",
            "Последнее управленческое решение по запуску.",
            (
                latest_signoff["decision_label"]
                if latest_signoff
                else "не зафиксировано"
            ),
            "ok" if latest_signoff else "warning",
            (
                latest_signoff["snapshot_url"]
                if latest_signoff
                else "/platform/readiness"
            ),
        ),
        make_release_review_item(
            "Журнал релиза",
            "Количество событий в журнале релиза.",
            str(timeline["total_events"]),
            "ok" if timeline["total_events"] else "warning",
            "/platform/readiness",
        ),
        make_release_review_item(
            "Контроль запуска",
            "Текущее состояние центра контроля.",
            control_center["label"],
            control_center["status"],
            "/platform/readiness",
        ),
    ]

    positives = []
    if score >= 80:
        positives.append(make_release_review_item(
            "Готовность держится выше 80%",
            "Платформа прошла базовый порог для пилота или запуска.",
            f"{score}%",
            "ok",
            "/platform/readiness",
        ))
    if comparison["resolved_blockers"]:
        positives.append(make_release_review_item(
            "Закрыты блокеры",
            "Часть критичных проблем ушла относительно прошлого снимка.",
            str(len(comparison["resolved_blockers"])),
            "ok",
            comparison["snapshot_url"] or "/platform/readiness",
        ))
    if latest_signoff:
        positives.append(make_release_review_item(
            "Решение зафиксировано",
            "Запуск имеет сохранённое управленческое решение.",
            latest_signoff["decision_label"],
            "ok",
            latest_signoff["snapshot_url"] or "/platform/readiness",
        ))

    issues = [
        make_release_review_item(
            item["title"],
            item["action"],
            item["category_label"],
            item["status"],
            item["url"],
        )
        for item in readiness["next_actions"][:5]
    ]
    if comparison["new_blockers"]:
        issues.extend([
            make_release_review_item(
                item["title"],
                item["action"],
                item["category_label"],
                "critical",
                item["url"],
            )
            for item in comparison["new_blockers"][:3]
        ])
    if not issues:
        issues = [
            make_release_review_item(
                "Критичных замечаний нет",
                "Продолжайте мониторинг первых клиентов и операционных сигналов.",
                "Мониторинг",
                "ok",
                "/platform/readiness",
            ),
        ]

    decisions = [
        make_release_review_item(
            "Сохранить новый снимок",
            "Зафиксируйте состояние после текущего этапа запуска.",
            "обязательно",
            "warning",
            "/platform/readiness",
        ),
        make_release_review_item(
            "Сравнить с предыдущим снимком",
            comparison["summary"],
            comparison["label"],
            comparison["tone"],
            comparison["snapshot_url"] or "/platform/readiness",
        ),
        make_release_review_item(
            "Проверить операционные инциденты",
            "Убедитесь, что календарные и системные проблемы не растут.",
            control_center["risk_level"],
            control_center["status"],
            "/platform/calendar-health",
        ),
    ]

    return {
        "status": status,
        "label": label,
        "outcome": outcome,
        "summary": summary,
        "score": score,
        "score_delta": score_delta,
        "critical_delta": critical_delta,
        "latest_decision": (
            latest_signoff["decision_label"]
            if latest_signoff
            else "Решения пока нет"
        ),
        "latest_decision_at": (
            latest_signoff["signed_at"]
            if latest_signoff
            else ""
        ),
        "metrics": metrics,
        "positives": positives[:4],
        "issues": issues[:6],
        "decisions": decisions,
    }


def make_release_dashboard_item(
    title,
    description,
    value="",
    status="warning",
    url="/platform/readiness",
):
    labels = {
        "ok": "Норма",
        "warning": "Контроль",
        "critical": "Стоп",
    }
    normalized_status = status if status in labels else "warning"
    return {
        "title": title,
        "description": description,
        "value": value,
        "status": normalized_status,
        "status_label": labels[normalized_status],
        "url": url,
    }


def get_platform_release_dashboard_summary(
    readiness=None,
    history=None,
    calendar_health_summary=None,
):
    readiness = readiness or get_platform_release_readiness(
        calendar_health_summary=calendar_health_summary,
    )
    history = (
        history
        if history is not None
        else get_platform_release_readiness_history()
    )
    comparison = compare_platform_release_readiness_to_snapshot(readiness)
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

    if launch_plan["blocked"]:
        status = "critical"
        label = "Стоп релиза"
        summary = "Есть критичные блокеры. Сначала закрываем обязательные исправления."
    elif control_center["status"] == "critical":
        status = "critical"
        label = "Высокий риск"
        summary = control_center["summary"]
    elif not control_center["has_signoff"]:
        status = "warning"
        label = "Нужно решение"
        summary = "Перед запуском нужно зафиксировать решение владельца платформы."
    elif post_launch_review["status"] == "critical":
        status = "critical"
        label = "Нужен разбор"
        summary = post_launch_review["summary"]
    elif readiness["warning_count"]:
        status = "warning"
        label = "Под контролем"
        summary = "Критичных блокеров нет, но есть предупреждения перед запуском."
    else:
        status = "ok"
        label = "Готово"
        summary = "Ключевые сигналы релиза стабильны."

    latest_decision = (
        signoffs[0]["decision_label"] if signoffs else "Решения пока нет"
    )
    latest_decision_at = signoffs[0]["signed_at"] if signoffs else ""
    next_checkpoint = control_center["next_checkpoint"]

    metrics = [
        make_release_dashboard_item(
            "Оценка",
            "Текущая оценка готовности релиза.",
            f"{readiness['score']}%",
            readiness["status"],
            "/platform/readiness",
        ),
        make_release_dashboard_item(
            "Риск",
            "Уровень риска по центру контроля запуска.",
            control_center["risk_level"],
            control_center["status"],
            "/platform/readiness",
        ),
        make_release_dashboard_item(
            "Решение",
            "Последнее сохранённое решение по запуску.",
            latest_decision,
            "ok" if signoffs else "warning",
            "/platform/readiness",
        ),
        make_release_dashboard_item(
            "Снимков",
            "Количество сохранённых снимков готовности.",
            str(trend["total_snapshots"]),
            "ok" if trend["has_history"] else "warning",
            "/platform/readiness",
        ),
        make_release_dashboard_item(
            "Динамика",
            "Изменение оценки относительно истории снимков.",
            str(trend["score_change"]),
            trend["tone"],
            "/platform/readiness",
        ),
        make_release_dashboard_item(
            "Разбор",
            "Состояние пострелизного разбора.",
            post_launch_review["outcome"],
            post_launch_review["status"],
            "/platform/readiness",
        ),
    ]

    alerts = [
        make_release_dashboard_item(
            item["title"],
            item["action"],
            item["category_label"],
            item["status"],
            item["url"],
        )
        for item in readiness["next_actions"][:4]
    ]
    if not alerts:
        alerts = [
            make_release_dashboard_item(
                "Критичных задач нет",
                "Продолжайте мониторинг запуска и первых клиентов.",
                "Мониторинг",
                "ok",
                "/platform/readiness",
            ),
        ]

    quick_actions = [
        make_release_dashboard_item(
            next_checkpoint["title"],
            next_checkpoint["description"],
            next_checkpoint["value"],
            next_checkpoint["status"],
            next_checkpoint["url"],
        ),
        make_release_dashboard_item(
            "Сохранить снимок",
            "Зафиксируйте текущее состояние готовности релиза.",
            "действие",
            "warning",
            "/platform/readiness",
        ),
        make_release_dashboard_item(
            "Открыть инциденты",
            "Проверьте календарные и операционные сигналы платформы.",
            control_center["risk_level"],
            control_center["status"],
            "/platform/calendar-health",
        ),
        make_release_dashboard_item(
            "Экспортировать CSV",
            "Сохраните отчёт готовности и контроля запуска.",
            "отчёт",
            "warning",
            readiness["export_url"],
        ),
    ]

    return {
        "status": status,
        "label": label,
        "summary": summary,
        "mode": launch_plan["recommended_mode"],
        "score": readiness["score"],
        "risk_level": control_center["risk_level"],
        "latest_decision": latest_decision,
        "latest_decision_at": latest_decision_at,
        "latest_event": timeline["latest_label"],
        "latest_event_at": timeline["latest_at"],
        "next_checkpoint": next_checkpoint,
        "control_label": control_center["label"],
        "review_label": post_launch_review["label"],
        "metrics": metrics,
        "alerts": alerts,
        "quick_actions": quick_actions,
    }


def create_platform_release_readiness_snapshot(username, readiness=None):
    readiness = readiness or get_platform_release_readiness()
    conn = connect()
    c = conn.cursor()
    launch_plan = get_platform_release_launch_plan(readiness)
    payload = {
        "checks": readiness["checks"],
        "categories": readiness["categories"],
        "next_actions": readiness["next_actions"],
        "environment": readiness["environment"],
        "backup_status": readiness.get("backup_status", {}),
        "launch_plan": launch_plan,
    }
    c.execute("""
    INSERT INTO platform_release_readiness_snapshots (
        score,
        status,
        status_label,
        critical_count,
        warning_count,
        ok_count,
        headline,
        created_by,
        created_at,
        payload_json
    )
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        readiness["score"],
        readiness["status"],
        readiness["status_label"],
        readiness["critical_count"],
        readiness["warning_count"],
        readiness["ok_count"],
        readiness["headline"],
        username,
        datetime.now().strftime("%Y-%m-%d %H:%M"),
        json.dumps(payload, ensure_ascii=False),
    ))
    snapshot_id = c.lastrowid
    conn.commit()
    conn.close()
    return snapshot_id


def get_platform_release_readiness_history(limit=8):
    conn = connect()
    c = conn.cursor()
    rows = c.execute("""
    SELECT *
    FROM platform_release_readiness_snapshots
    ORDER BY id DESC
    LIMIT ?
    """, (limit,)).fetchall()
    conn.close()
    history = [dict(row) for row in rows]

    for index, item in enumerate(history):
        previous = history[index + 1] if index + 1 < len(history) else None
        delta = (
            int(item["score"] or 0) - int(previous["score"] or 0)
            if previous
            else 0
        )
        item["delta_score"] = delta
        item["detail_url"] = (
            f"/platform/readiness/snapshots/{item['id']}"
        )
        item["export_url"] = (
            f"/platform/readiness/snapshots/{item['id']}/export"
        )
        if delta > 0:
            item["delta_label"] = f"+{delta}"
            item["delta_tone"] = "ok"
        elif delta < 0:
            item["delta_label"] = str(delta)
            item["delta_tone"] = "critical"
        else:
            item["delta_label"] = "0"
            item["delta_tone"] = "warning"

    return history


def get_platform_release_readiness_snapshot(snapshot_id):
    conn = connect()
    c = conn.cursor()
    row = c.execute("""
    SELECT *
    FROM platform_release_readiness_snapshots
    WHERE id=?
    """, (snapshot_id,)).fetchone()

    if not row:
        conn.close()
        return None

    previous_row = c.execute("""
    SELECT *
    FROM platform_release_readiness_snapshots
    WHERE id<?
    ORDER BY id DESC
    LIMIT 1
    """, (snapshot_id,)).fetchone()
    conn.close()
    snapshot = dict(row)
    previous = dict(previous_row) if previous_row else None

    try:
        payload = json.loads(snapshot.get("payload_json") or "{}")
    except json.JSONDecodeError:
        payload = {}

    snapshot["checks"] = payload.get("checks") or []
    snapshot["categories"] = payload.get("categories") or []
    snapshot["next_actions"] = payload.get("next_actions") or []
    snapshot["environment"] = payload.get("environment") or ""
    snapshot["backup_status"] = payload.get("backup_status") or {}
    snapshot["blockers"] = [
        item for item in snapshot["checks"] if item["status"] == "critical"
    ]
    snapshot["launch_plan"] = (
        payload.get("launch_plan")
        or get_platform_release_launch_plan(snapshot)
    )
    snapshot["previous_id"] = previous["id"] if previous else 0
    snapshot["previous_url"] = (
        f"/platform/readiness/snapshots/{previous['id']}"
        if previous
        else ""
    )
    delta = (
        int(snapshot["score"] or 0) - int(previous["score"] or 0)
        if previous
        else 0
    )
    snapshot["delta_score"] = delta
    if delta > 0:
        snapshot["delta_label"] = f"+{delta}"
        snapshot["delta_tone"] = "ok"
    elif delta < 0:
        snapshot["delta_label"] = str(delta)
        snapshot["delta_tone"] = "critical"
    else:
        snapshot["delta_label"] = "0"
        snapshot["delta_tone"] = "warning"
    snapshot["detail_url"] = f"/platform/readiness/snapshots/{snapshot['id']}"
    snapshot["export_url"] = (
        f"/platform/readiness/snapshots/{snapshot['id']}/export"
    )
    return snapshot


def compare_platform_release_readiness_to_snapshot(
    readiness,
    snapshot=None,
):
    if snapshot is None:
        history = get_platform_release_readiness_history(limit=1)
        snapshot = (
            get_platform_release_readiness_snapshot(history[0]["id"])
            if history
            else None
        )

    if not snapshot:
        return {
            "has_snapshot": False,
            "label": "Нет снимка",
            "tone": "warning",
            "summary": "Сохраните первый снимок для сравнения.",
            "score_delta": 0,
            "critical_delta": 0,
            "warning_delta": 0,
            "new_blockers": [],
            "resolved_blockers": [],
            "snapshot_url": "",
            "snapshot_created_at": "",
        }

    current_checks = {
        item["key"]: item for item in readiness["checks"]
    }
    snapshot_checks = {
        item["key"]: item for item in snapshot["checks"]
    }
    score_delta = int(readiness["score"] or 0) - int(snapshot["score"] or 0)
    critical_delta = (
        int(readiness["critical_count"] or 0)
        - int(snapshot["critical_count"] or 0)
    )
    warning_delta = (
        int(readiness["warning_count"] or 0)
        - int(snapshot["warning_count"] or 0)
    )
    new_blockers = [
        check
        for key, check in current_checks.items()
        if check["status"] == "critical"
        and snapshot_checks.get(key, {}).get("status") != "critical"
    ]
    resolved_blockers = [
        check
        for key, check in snapshot_checks.items()
        if check["status"] == "critical"
        and current_checks.get(key, {}).get("status") != "critical"
    ]

    if new_blockers or critical_delta > 0 or score_delta < 0:
        label = "Стало хуже"
        tone = "critical"
        summary = "Появились ухудшения относительно последнего снимка."
    elif resolved_blockers or critical_delta < 0 or score_delta > 0:
        label = "Стало лучше"
        tone = "ok"
        summary = "Готовность улучшилась относительно последнего снимка."
    else:
        label = "Без изменений"
        tone = "warning"
        summary = "Ключевые показатели не изменились."

    return {
        "has_snapshot": True,
        "label": label,
        "tone": tone,
        "summary": summary,
        "score_delta": score_delta,
        "critical_delta": critical_delta,
        "warning_delta": warning_delta,
        "new_blockers": new_blockers,
        "resolved_blockers": resolved_blockers,
        "snapshot_url": snapshot["detail_url"],
        "snapshot_created_at": snapshot["created_at"],
    }


def get_platform_release_readiness_trend(history=None):
    history = (
        history
        if history is not None
        else get_platform_release_readiness_history()
    )

    if not history:
        return {
            "has_history": False,
            "label": "Нет истории",
            "tone": "warning",
            "summary": "Сохраните несколько снимков, чтобы видеть динамику.",
            "total_snapshots": 0,
            "latest_score": 0,
            "score_change": 0,
            "critical_change": 0,
            "warning_change": 0,
            "best_score": 0,
            "best_date": "",
            "worst_score": 0,
            "worst_date": "",
            "bars": [],
        }

    ordered = list(reversed(history))
    latest = history[0]
    first = ordered[0]
    latest_score = int(latest["score"] or 0)
    first_score = int(first["score"] or 0)
    score_change = latest_score - first_score
    critical_change = (
        int(latest["critical_count"] or 0)
        - int(first["critical_count"] or 0)
    )
    warning_change = (
        int(latest["warning_count"] or 0)
        - int(first["warning_count"] or 0)
    )
    best = max(history, key=lambda item: int(item["score"] or 0))
    worst = min(history, key=lambda item: int(item["score"] or 0))

    if len(history) == 1:
        label = "Нужна история"
        tone = "warning"
        summary = "Есть один снимок. Для тренда нужен ещё один."
    elif score_change > 0 and critical_change <= 0:
        label = "Тренд улучшается"
        tone = "ok"
        summary = "Оценка готовности выросла относительно первого снимка."
    elif score_change < 0 or critical_change > 0:
        label = "Тренд ухудшается"
        tone = "critical"
        summary = "Готовность снизилась или выросло число критичных блокеров."
    else:
        label = "Тренд стабильный"
        tone = "warning"
        summary = "Оценка готовности заметно не изменилась."

    bars = []
    for item in ordered[-8:]:
        score = int(item["score"] or 0)
        bars.append({
            "id": item["id"],
            "score": score,
            "height": max(score, 4),
            "created_at": item["created_at"],
            "status": item["status"],
            "detail_url": item["detail_url"],
        })

    return {
        "has_history": True,
        "label": label,
        "tone": tone,
        "summary": summary,
        "total_snapshots": len(history),
        "latest_score": latest_score,
        "score_change": score_change,
        "critical_change": critical_change,
        "warning_change": warning_change,
        "best_score": int(best["score"] or 0),
        "best_date": best["created_at"],
        "worst_score": int(worst["score"] or 0),
        "worst_date": worst["created_at"],
        "bars": bars,
    }


def compare_platform_release_readiness_snapshots(
    snapshot,
    previous_snapshot=None,
):
    if previous_snapshot is None and snapshot.get("previous_id"):
        previous_snapshot = get_platform_release_readiness_snapshot(
            snapshot["previous_id"],
        )

    if not previous_snapshot:
        return {
            "has_previous": False,
            "label": "Нет предыдущего снимка",
            "tone": "warning",
            "summary": "Это первый сохранённый снимок готовности релиза.",
            "score_delta": 0,
            "critical_delta": 0,
            "warning_delta": 0,
            "new_blockers": [],
            "resolved_blockers": [],
            "changed_checks": [],
            "changed_count": 0,
            "previous_url": "",
            "previous_created_at": "",
        }

    current_checks = {
        item["key"]: item for item in snapshot["checks"]
    }
    previous_checks = {
        item["key"]: item for item in previous_snapshot["checks"]
    }
    score_delta = (
        int(snapshot["score"] or 0)
        - int(previous_snapshot["score"] or 0)
    )
    critical_delta = (
        int(snapshot["critical_count"] or 0)
        - int(previous_snapshot["critical_count"] or 0)
    )
    warning_delta = (
        int(snapshot["warning_count"] or 0)
        - int(previous_snapshot["warning_count"] or 0)
    )
    new_blockers = [
        check
        for key, check in current_checks.items()
        if check["status"] == "critical"
        and previous_checks.get(key, {}).get("status") != "critical"
    ]
    resolved_blockers = [
        check
        for key, check in previous_checks.items()
        if check["status"] == "critical"
        and current_checks.get(key, {}).get("status") != "critical"
    ]
    changed_checks = []
    for key, check in current_checks.items():
        previous_check = previous_checks.get(key)
        if not previous_check:
            continue
        if previous_check["status"] == check["status"]:
            continue
        changed_checks.append({
            "category_label": check["category_label"],
            "title": check["title"],
            "from_status": previous_check["status_label"],
            "to_status": check["status_label"],
            "tone": check["status"],
            "action": check["action"],
        })

    if new_blockers or critical_delta > 0 or score_delta < 0:
        label = "Стало хуже"
        tone = "critical"
        summary = "В этом снимке появились ухудшения."
    elif resolved_blockers or critical_delta < 0 or score_delta > 0:
        label = "Стало лучше"
        tone = "ok"
        summary = "В этом снимке готовность улучшилась."
    else:
        label = "Без изменений"
        tone = "warning"
        summary = "Состояние совпадает с предыдущим снимком."

    return {
        "has_previous": True,
        "label": label,
        "tone": tone,
        "summary": summary,
        "score_delta": score_delta,
        "critical_delta": critical_delta,
        "warning_delta": warning_delta,
        "new_blockers": new_blockers,
        "resolved_blockers": resolved_blockers,
        "changed_checks": changed_checks[:8],
        "changed_count": len(changed_checks),
        "previous_url": previous_snapshot["detail_url"],
        "previous_created_at": previous_snapshot["created_at"],
    }


@app.get("/", response_class=HTMLResponse)
async def home(
    request: Request,
    status: str = "",
    worker: str = "",
    task_date: str = "",
    search: str = ""
):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    update_last_seen(username)

    role = get_role(username)

    if role == "superadmin":
        return RedirectResponse("/platform", status_code=302)

    if role == "worker":
        return RedirectResponse("/my-tasks", status_code=302)

    company_id = get_user_company_id(username)
    features = get_company_features(company_id)

    conn = connect()
    c = conn.cursor()
    selected_search = (search or "").strip()[:100]

    query = "SELECT * FROM tasks WHERE archived=0 AND company_id=?"
    params = [company_id]

    if role not in ("boss", "manager"):
        query += f" AND {worker_task_condition()}"
        params += worker_task_params(username)

    if status:
        query += " AND status=?"
        params.append(status)

    if worker and role in ("boss", "manager"):
        query += f" AND {worker_task_condition()}"
        params += worker_task_params(worker)

    if task_date:
        query += " AND task_date=?"
        params.append(task_date)

    if selected_search:
        search_pattern = f"%{selected_search}%"
        query += """
        AND (
            client LIKE ?
            OR phone LIKE ?
            OR address LIKE ?
            OR description LIKE ?
        )
        """
        params.extend([
            search_pattern,
            search_pattern,
            search_pattern,
            search_pattern,
        ])

    query += " ORDER BY id DESC LIMIT 500"

    tasks = c.execute(query, params).fetchall()

    if role in ("boss", "manager"):
        total_tasks = c.execute("SELECT COUNT(*) FROM tasks WHERE archived=0 AND company_id=?", (company_id,)).fetchone()[0]
        new_tasks = c.execute("SELECT COUNT(*) FROM tasks WHERE archived=0 AND company_id=? AND status='Новая'", (company_id,)).fetchone()[0]
        working_tasks = c.execute("SELECT COUNT(*) FROM tasks WHERE archived=0 AND company_id=? AND status='В работе'", (company_id,)).fetchone()[0]
        done_tasks = c.execute("SELECT COUNT(*) FROM tasks WHERE archived=0 AND company_id=? AND status='Завершено'", (company_id,)).fetchone()[0]

        revenue = c.execute("""
        SELECT SUM(price) FROM tasks WHERE archived=0 AND company_id=? AND status='Завершено'
        """, (company_id,)).fetchone()[0]
    else:
        worker_condition = worker_task_condition()
        worker_params = worker_task_params(username)

        total_tasks = c.execute(f"""
        SELECT COUNT(*) FROM tasks
        WHERE archived=0 AND company_id=? AND {worker_condition}
        """, [company_id] + worker_params).fetchone()[0]

        new_tasks = c.execute(f"""
        SELECT COUNT(*) FROM tasks
        WHERE archived=0 AND company_id=? AND {worker_condition}
          AND status='Новая'
        """, [company_id] + worker_params).fetchone()[0]

        working_tasks = c.execute(f"""
        SELECT COUNT(*) FROM tasks
        WHERE archived=0 AND company_id=? AND {worker_condition}
          AND status='В работе'
        """, [company_id] + worker_params).fetchone()[0]

        done_tasks = c.execute(f"""
        SELECT COUNT(*) FROM tasks
        WHERE archived=0 AND company_id=? AND {worker_condition}
          AND status='Завершено'
        """, [company_id] + worker_params).fetchone()[0]

        revenue = c.execute(f"""
        SELECT SUM(price) FROM tasks
        WHERE archived=0 AND company_id=? AND {worker_condition}
          AND status='Завершено'
        """, [company_id] + worker_params).fetchone()[0]

    if revenue is None:
        revenue = 0

    today = datetime.now().strftime("%Y-%m-%d")
    now_value = datetime.now().strftime("%Y-%m-%dT%H:%M")
    sla_soon_value = (datetime.now() + timedelta(hours=24)).strftime("%Y-%m-%dT%H:%M")

    today_tasks = c.execute("""
    SELECT COUNT(*)
    FROM tasks
    WHERE archived=0
      AND company_id=?
      AND task_date LIKE ?
    """, (company_id, f"{today}%")).fetchone()[0]

    overdue_tasks = c.execute("""
    SELECT COUNT(*)
    FROM tasks
    WHERE archived=0
      AND company_id=?
      AND status NOT IN ('Завершено', 'Отменено')
      AND task_date IS NOT NULL
      AND task_date!=''
      AND task_date < ?
    """, (company_id, today)).fetchone()[0]

    sla_breached_tasks = c.execute("""
    SELECT COUNT(*)
    FROM tasks
    WHERE archived=0
      AND company_id=?
      AND status NOT IN ('Завершено', 'Отменено')
      AND deadline_at IS NOT NULL
      AND deadline_at!=''
      AND deadline_at < ?
    """, (company_id, now_value)).fetchone()[0]

    sla_due_soon_tasks = c.execute("""
    SELECT COUNT(*)
    FROM tasks
    WHERE archived=0
      AND company_id=?
      AND status NOT IN ('Завершено', 'Отменено')
      AND deadline_at IS NOT NULL
      AND deadline_at!=''
      AND deadline_at >= ?
      AND deadline_at <= ?
    """, (company_id, now_value, sla_soon_value)).fetchone()[0]

    active_worker_rows = c.execute("""
    SELECT worker, workers
    FROM tasks
    WHERE archived=0
      AND company_id=?
      AND status='В работе'
    """, (company_id,)).fetchall()
    active_workers = len({
        worker_name
        for row in active_worker_rows
        for worker_name in get_task_worker_names(row)
    })


    workers = c.execute("""
    SELECT username, last_seen FROM users
    WHERE role='worker'
      AND company_id=?
      AND COALESCE(is_active, 1)=1
    ORDER BY username
    """, (company_id,)).fetchall()

    clients = []

    worker_stats = []

    if role in ("boss", "manager"):
        for w in workers:
            worker_name = w["username"]
            worker_condition = worker_task_condition()
            worker_params = worker_task_params(worker_name)

            stats = c.execute(f"""
            SELECT
                COALESCE(SUM(CASE WHEN status='Завершено' THEN 1 ELSE 0 END), 0)
                    AS completed,
                COALESCE(SUM(CASE WHEN status='В работе' THEN 1 ELSE 0 END), 0)
                    AS active,
                COALESCE(SUM(CASE WHEN status='Завершено'
                    THEN CAST(REPLACE(COALESCE(price, '0'), ',', '.') AS REAL)
                    ELSE 0 END), 0) AS revenue
            FROM tasks
            WHERE archived=0 AND company_id=? AND {worker_condition}
            """, [company_id] + worker_params).fetchone()

            worker_stats.append({
                "username": worker_name,
                "completed": stats["completed"],
                "active": stats["active"],
                "revenue": round(stats["revenue"], 2),
                "last_seen": w["last_seen"]
            })

    settings = get_company_settings(company_id)
    call_follow_up_count = 0

    if (
        role in ("boss", "manager")
        and features.get("calls", True)
        and settings
        and settings["calls_enabled"]
    ):
        call_follow_up_count = c.execute("""
        SELECT COUNT(*)
        FROM call_records
        WHERE company_id=?
          AND status='follow_up'
        """, (company_id,)).fetchone()[0]

    unread_notification_count = c.execute("""
    SELECT COUNT(*)
    FROM notifications
    WHERE company_id=?
      AND username=?
      AND is_read=0
    """, (company_id, username)).fetchone()[0]

    conn.close()

    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "tasks": tasks,
            "username": username,
            "role": role,
            "total_tasks": total_tasks,
            "new_tasks": new_tasks,
            "working_tasks": working_tasks,
            "done_tasks": done_tasks,
            "revenue": revenue,
            "today_tasks": today_tasks,
            "overdue_tasks": overdue_tasks,
            "sla_breached_tasks": sla_breached_tasks,
            "sla_due_soon_tasks": sla_due_soon_tasks,
            "active_workers": active_workers,
            "call_follow_up_count": call_follow_up_count,
            "unread_notification_count": unread_notification_count,
            "workers": workers,
            "worker_stats": worker_stats,
            "selected_status": status,
            "selected_worker": worker,
            "selected_date": task_date,
            "search": selected_search,
            "features": features,
            "settings": settings,
            "links": build_dashboard_links(),
        }
    )


@app.get("/automation/workflows", response_class=HTMLResponse)
def automation_workflows_page(request: Request):
    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role not in ("boss", "manager"):
        return RedirectResponse("/", status_code=302)

    company_id = get_user_company_id(username)
    disabled_response = require_feature(company_id, "automation")

    if disabled_response:
        return disabled_response

    return templates.TemplateResponse(
        request,
        "automation_workflows.html",
        {
            "request": request,
            "username": username,
            "role": role,
        },
    )


@app.get("/automation", response_class=HTMLResponse)
async def automation_page(
    request: Request,
    rule_filter: str = "",
    event_filter: str = "",
    trigger_filter: str = "",
    rule_trigger_filter: str = "",
    rule_action_filter: str = "",
    rule_search: str = "",
    event_search: str = "",
    event_entity_filter: str = "",
    event_date_from: str = "",
    event_date_to: str = "",
    event_rule_id: str = ""
):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role not in ("boss", "manager"):
        return RedirectResponse("/", status_code=302)

    company_id = get_user_company_id(username)
    disabled_response = require_feature(company_id, "automation")

    if disabled_response:
        return disabled_response

    trigger_labels = dict(AUTOMATION_TRIGGERS)
    trigger_groups = get_automation_trigger_groups()
    action_labels = dict(AUTOMATION_ACTIONS)
    status_labels = AUTOMATION_STATUS_LABELS
    entity_labels = {
        "task": "Заявка",
        "client": "Клиент",
        "company": "Компания"
    }
    selected_rule_filter = rule_filter if rule_filter in ("active", "disabled") else ""
    selected_event_filter = event_filter if event_filter in ("pending", "done", "skipped", "failed") else ""
    trigger_keys = {key for key, _ in AUTOMATION_TRIGGERS}
    action_keys = {key for key, _ in AUTOMATION_ACTIONS}
    selected_trigger_filter = trigger_filter if trigger_filter in trigger_keys else ""
    selected_rule_trigger_filter = rule_trigger_filter if rule_trigger_filter in trigger_keys else ""
    selected_rule_action_filter = rule_action_filter if rule_action_filter in action_keys else ""
    selected_rule_search = (rule_search or "").strip()[:80]
    selected_event_search = (event_search or "").strip()[:80]
    selected_event_entity_filter = event_entity_filter if event_entity_filter in entity_labels else ""
    selected_event_date_from = (event_date_from or "").strip()[:10]
    selected_event_date_to = (event_date_to or "").strip()[:10]
    try:
        selected_event_rule_id = int(event_rule_id or 0)
    except ValueError:
        selected_event_rule_id = 0
    if selected_event_rule_id < 0:
        selected_event_rule_id = 0
    event_filter_sql = ""
    event_params = [company_id]

    for selected_date in (selected_event_date_from, selected_event_date_to):
        if selected_date:
            try:
                datetime.strptime(selected_date, "%Y-%m-%d")
            except ValueError:
                selected_event_date_from = ""
                selected_event_date_to = ""
                break

    if selected_event_filter:
        event_filter_sql = "AND automation_events.status=?"
        event_params.append(selected_event_filter)

    if selected_event_rule_id:
        event_filter_sql += "\n      AND automation_events.rule_id=?"
        event_params.append(selected_event_rule_id)

    if selected_trigger_filter:
        event_filter_sql += "\n      AND automation_events.trigger_key=?"
        event_params.append(selected_trigger_filter)

    if selected_event_entity_filter:
        event_filter_sql += "\n      AND automation_events.entity_type=?"
        event_params.append(selected_event_entity_filter)

    if selected_event_search:
        event_filter_sql += """
      AND (
        automation_events.message LIKE ?
        OR automation_rules.name LIKE ?
      )
        """
        event_params.extend([
            f"%{selected_event_search}%",
            f"%{selected_event_search}%"
        ])

    if selected_event_date_from:
        event_filter_sql += "\n      AND substr(automation_events.created_at, 1, 10) >= ?"
        event_params.append(selected_event_date_from)

    if selected_event_date_to:
        event_filter_sql += "\n      AND substr(automation_events.created_at, 1, 10) <= ?"
        event_params.append(selected_event_date_to)

    event_export_params = {}
    if selected_event_filter:
        event_export_params["event_filter"] = selected_event_filter
    if selected_trigger_filter:
        event_export_params["trigger_filter"] = selected_trigger_filter
    if selected_event_entity_filter:
        event_export_params["event_entity_filter"] = selected_event_entity_filter
    if selected_event_search:
        event_export_params["event_search"] = selected_event_search
    if selected_event_date_from:
        event_export_params["event_date_from"] = selected_event_date_from
    if selected_event_date_to:
        event_export_params["event_date_to"] = selected_event_date_to
    if selected_event_rule_id:
        event_export_params["event_rule_id"] = selected_event_rule_id

    event_export_query = (
        "?" + urlencode(event_export_params)
        if event_export_params
        else ""
    )
    event_all_params = {}
    if selected_rule_filter:
        event_all_params["rule_filter"] = selected_rule_filter
    if selected_trigger_filter:
        event_all_params["trigger_filter"] = selected_trigger_filter
    if selected_event_entity_filter:
        event_all_params["event_entity_filter"] = selected_event_entity_filter
    if selected_event_search:
        event_all_params["event_search"] = selected_event_search
    if selected_event_date_from:
        event_all_params["event_date_from"] = selected_event_date_from
    if selected_event_date_to:
        event_all_params["event_date_to"] = selected_event_date_to
    if selected_event_rule_id:
        event_all_params["event_rule_id"] = selected_event_rule_id

    base_event_link_params = dict(event_all_params)

    def build_event_filter_href(status_key: str) -> str:
        params = {}

        if status_key:
            params["event_filter"] = status_key

        params.update(base_event_link_params)

        return "/automation" + (
            "?" + urlencode(params)
            if params
            else ""
        )

    event_filter_links = [
        {"key": "", "label": "Все", "href": build_event_filter_href("")},
        {"key": "pending", "label": "Ожидает", "href": build_event_filter_href("pending")},
        {"key": "done", "label": "Выполнено", "href": build_event_filter_href("done")},
        {"key": "skipped", "label": "Пропущено", "href": build_event_filter_href("skipped")},
        {"key": "failed", "label": "Ошибка", "href": build_event_filter_href("failed")},
    ]

    conn = connect()
    c = conn.cursor()

    rule_rows = c.execute("""
    SELECT
        automation_rules.*,
        COUNT(automation_actions.id) AS action_count,
        GROUP_CONCAT(automation_actions.action_key) AS action_keys,
        (
            SELECT action_key
            FROM automation_actions
            WHERE company_id=automation_rules.company_id
              AND rule_id=automation_rules.id
            ORDER BY sort_order, id
            LIMIT 1
        ) AS primary_action_key,
        (
            SELECT payload_json
            FROM automation_actions
            WHERE company_id=automation_rules.company_id
              AND rule_id=automation_rules.id
            ORDER BY sort_order, id
            LIMIT 1
        ) AS primary_payload_json
    FROM automation_rules
    LEFT JOIN automation_actions
      ON automation_actions.rule_id=automation_rules.id
      AND automation_actions.company_id=automation_rules.company_id
    WHERE automation_rules.company_id=?
    GROUP BY automation_rules.id
    ORDER BY automation_rules.id DESC
    """, (company_id,)).fetchall()

    event_rows = c.execute(f"""
    SELECT
        automation_events.*,
        automation_rules.name AS rule_name
    FROM automation_events
    LEFT JOIN automation_rules
      ON automation_rules.id=automation_events.rule_id
      AND automation_rules.company_id=automation_events.company_id
    WHERE automation_events.company_id=?
      {event_filter_sql}
    ORDER BY automation_events.id DESC
    LIMIT 30
    """, event_params).fetchall()

    event_count_rows = c.execute("""
    SELECT status, COUNT(*) AS count
    FROM automation_events
    WHERE company_id=?
    GROUP BY status
    """, (company_id,)).fetchall()
    event_counts = {row["status"]: row["count"] for row in event_count_rows}

    last_event_at = c.execute("""
    SELECT MAX(created_at)
    FROM automation_events
    WHERE company_id=?
    """, (company_id,)).fetchone()[0] or ""

    today_key = datetime.now().strftime("%Y-%m-%d")
    events_today = c.execute("""
    SELECT COUNT(*)
    FROM automation_events
    WHERE company_id=?
      AND substr(created_at, 1, 10)=?
    """, (company_id, today_key)).fetchone()[0] or 0

    users = c.execute("""
    SELECT username, role
    FROM users
    WHERE company_id=?
      AND COALESCE(is_active, 1)=1
    ORDER BY role, username
    """, (company_id,)).fetchall()

    conn.close()

    events = []
    for event_row in event_rows:
        event = dict(event_row)
        event["retry_state"] = build_a3_event_retry_state(event)
        events.append(event)

    rules = []
    unhealthy_rules = []
    selected_event_rule_name = ""

    for rule_row in rule_rows:
        rule = dict(rule_row)

        if selected_event_rule_id and rule.get("id") == selected_event_rule_id:
            selected_event_rule_name = rule.get("name") or ""

        health_issues = []

        if not rule.get("active", 1):
            health_issues.append("Правило отключено")

        if not rule.get("action_count"):
            health_issues.append("Действия не настроены")

        if (rule.get("success_rate") or 100) < 60:
            health_issues.append("Низкая успешность")

        if (rule.get("skipped_runs") or 0) >= 5:
            health_issues.append("Много пропущенных запусков")

        if health_issues:
            unhealthy_rules.append({
                "id": rule.get("id"),
                "name": rule.get("name"),
                "issues": health_issues,
            })

        try:
            payload = json.loads(rule.get("primary_payload_json") or "{}")
        except Exception:
            payload = {}

        rule["edit_target_username"] = payload.get("target_username") or rule["created_by"] or username
        rule["edit_message"] = payload.get("message") or ""
        rules.append(rule)

    success_rate = round(
        event_counts.get("done", 0) / max(
            event_counts.get("done", 0) + event_counts.get("skipped", 0),
            1
        ) * 100,
        1
    )

    pending_count = event_counts.get("pending", 0)
    done_count = event_counts.get("done", 0)
    skipped_count = event_counts.get("skipped", 0)

    if pending_count > 5 or skipped_count > done_count:
        health_status = "problem"
        health_title = "Проблема"
        health_message = "Есть много ожидающих или пропущенных событий. Нужно проверить правила автоматизации."
    elif pending_count > 0 or skipped_count > 0 or success_rate < 80:
        health_status = "warning"
        health_title = "Нужно внимание"
        health_message = "Автоматизация работает, но есть события, которые требуют проверки."
    else:
        health_status = "ok"
        health_title = "Стабильно"
        health_message = "Автоматизация работает стабильно."

    automation_stats = {
        "rules_total": len(rules),
        "rules_active": len([rule for rule in rules if rule["active"]]),
        "rules_disabled": len([rule for rule in rules if not rule["active"]]),
        "events_total": sum(event_counts.values()),
        "events_pending": pending_count,
        "events_done": done_count,
        "events_skipped": skipped_count,
        "events_today": events_today,
        "success_rate": success_rate,
        "last_event_at": last_event_at,
        "health_status": health_status,
        "health_title": health_title,
        "health_message": health_message
    }

    if selected_rule_filter == "active":
        rules = [rule for rule in rules if rule["active"]]
    elif selected_rule_filter == "disabled":
        rules = [rule for rule in rules if not rule["active"]]

    if selected_rule_trigger_filter:
        rules = [rule for rule in rules if rule["trigger_key"] == selected_rule_trigger_filter]

    if selected_rule_action_filter:
        rules = [
            rule for rule in rules
            if selected_rule_action_filter in (rule["action_keys"] or "").split(",")
        ]

    if selected_rule_search:
        rule_search_lower = selected_rule_search.lower()
        rules = [
            rule for rule in rules
            if rule_search_lower in (rule["name"] or "").lower()
            or rule_search_lower in (rule["edit_message"] or "").lower()
        ]

    return templates.TemplateResponse(
        request,
        "automation.html",
        {
            "request": request,
            "username": username,
            "role": role,
            "rules": rules,
            "unhealthy_rules": unhealthy_rules,
            "events": events,
            "shown_events_count": len(events),
            "users": users,
            "triggers": AUTOMATION_TRIGGERS,
            "trigger_groups": trigger_groups,
            "actions": AUTOMATION_ACTIONS,
            "trigger_labels": trigger_labels,
            "action_labels": action_labels,
            "status_labels": status_labels,
            "entity_labels": entity_labels,
            "selected_rule_filter": selected_rule_filter,
            "selected_event_filter": selected_event_filter,
            "selected_trigger_filter": selected_trigger_filter,
            "selected_rule_trigger_filter": selected_rule_trigger_filter,
            "selected_rule_action_filter": selected_rule_action_filter,
            "selected_rule_search": selected_rule_search,
            "selected_event_search": selected_event_search,
            "selected_event_entity_filter": selected_event_entity_filter,
            "selected_event_date_from": selected_event_date_from,
            "selected_event_date_to": selected_event_date_to,
            "selected_event_rule_id": selected_event_rule_id,
            "selected_event_rule_name": selected_event_rule_name,
            "event_export_query": event_export_query,
            "event_filter_links": event_filter_links,
            "automation_stats": automation_stats,
            "features": get_company_features(company_id)
        }
    )


@app.get("/automation/builder", response_class=HTMLResponse)
async def automation_builder_page(request: Request):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role not in ("boss", "manager"):
        return RedirectResponse("/", status_code=302)

    company_id = get_user_company_id(username)
    disabled_response = require_feature(company_id, "automation")

    if disabled_response:
        return disabled_response

    settings = get_company_settings(company_id)

    conn = connect()
    c = conn.cursor()

    rules = c.execute("""
    SELECT
        automation_rules.*,
        COUNT(automation_actions.id) AS action_count
    FROM automation_rules
    LEFT JOIN automation_actions
      ON automation_actions.rule_id=automation_rules.id
      AND automation_actions.company_id=automation_rules.company_id
    WHERE automation_rules.company_id=?
    GROUP BY automation_rules.id
    ORDER BY automation_rules.id DESC
    LIMIT 50
    """, (company_id,)).fetchall()

    actions = c.execute("""
    SELECT *
    FROM automation_actions
    WHERE company_id=?
    ORDER BY rule_id, sort_order, id
    """, (company_id,)).fetchall()

    workers = c.execute("""
    SELECT username, full_name
    FROM users
    WHERE company_id=?
      AND role='worker'
      AND COALESCE(is_active, 1)=1
    ORDER BY COALESCE(NULLIF(full_name, ''), username), username
    """, (company_id,)).fetchall()

    clients = c.execute("""
    SELECT id, name, phone
    FROM clients
    WHERE company_id=?
    ORDER BY name, id
    """, (company_id,)).fetchall()

    catalog_items = c.execute("""
    SELECT id, name, item_type
    FROM catalog_items
    WHERE company_id=?
      AND active=1
    ORDER BY item_type, name, id
    """, (company_id,)).fetchall()

    test_tasks = c.execute("""
    SELECT id, client, status, task_date
    FROM tasks
    WHERE company_id=?
      AND archived=0
    ORDER BY task_date DESC, id DESC
    LIMIT 100
    """, (company_id,)).fetchall()

    conn.close()

    actions_by_rule = {}

    for action in actions:
        actions_by_rule.setdefault(action["rule_id"], []).append(action)

    condition_presets = [
        ("none", "Без условий"),
        ("priority_high", "Только высокий приоритет"),
        ("emergency", "Только срочные заявки"),
        ("task_text_contains", "Текст заявки содержит"),
        ("status_new", "Только новые заявки"),
        ("status_in_progress", "Только заявки в работе"),
        ("status_done", "Только завершённые заявки"),
        ("status_cancelled", "Только отменённые заявки"),
        ("payment_unpaid", "Только неоплаченные заявки"),
        ("payment_partial", "Только частично оплаченные заявки"),
        ("payment_paid", "Только оплаченные заявки"),
        ("worker_assigned", "Только задачи с исполнителем"),
        ("worker_unassigned", "Только задачи без исполнителя"),
        ("worker_specific", "Только выбранный исполнитель"),
        ("date_today", "Только задачи на сегодня"),
        ("date_tomorrow", "Только задачи на завтра"),
        ("date_next_7_days", "Только задачи на ближайшие 7 дней"),
        ("date_overdue", "Только просроченные задачи"),
        ("date_future", "Только будущие задачи"),
        ("price_high", "Только дорогие заявки"),
        ("price_missing", "Только заявки без цены"),
        ("catalog_specific", "Только выбранная позиция каталога"),
        ("sla_today", "Только дедлайн сегодня"),
        ("sla_overdue", "Только просроченный SLA"),
        ("sla_due_24h", "Только дедлайн в ближайшие 24 часа"),
        ("client_specific", "Только выбранный клиент"),
        ("client_new", "Только новые клиенты"),
        ("client_repeat", "Только постоянные клиенты"),
        ("client_vip", "Только VIP клиенты"),
        ("client_has_debt", "Только клиенты с долгом"),
        ("client_many_tasks", "Только клиенты с большим количеством заявок"),
    ]
    condition_labels = dict(condition_presets)

    def condition_group(*keys):
        return [(key, condition_labels[key]) for key in keys]

    condition_groups = [
        ("Базовые", condition_group(
            "none",
            "priority_high",
            "emergency",
            "task_text_contains",
        )),
        ("Статус заявки", condition_group(
            "status_new",
            "status_in_progress",
            "status_done",
            "status_cancelled",
        )),
        ("Оплата", condition_group(
            "payment_unpaid",
            "payment_partial",
            "payment_paid",
        )),
        ("Исполнители", condition_group(
            "worker_assigned",
            "worker_unassigned",
            "worker_specific",
        )),
        ("Дата", condition_group(
            "date_today",
            "date_tomorrow",
            "date_next_7_days",
            "date_overdue",
            "date_future",
        )),
        ("Цена", condition_group(
            "price_high",
            "price_missing",
        )),
        ("Каталог", condition_group(
            "catalog_specific",
        )),
        ("SLA", condition_group(
            "sla_today",
            "sla_overdue",
            "sla_due_24h",
        )),
        ("Клиенты", condition_group(
            "client_specific",
            "client_new",
            "client_repeat",
            "client_vip",
            "client_has_debt",
            "client_many_tasks",
        )),
    ]
    rules_view = []
    test_rule_id = str(request.query_params.get("test_rule_id") or "")
    test_task_id = str(request.query_params.get("test_task_id") or "")
    test_result = str(request.query_params.get("test_result") or "")

    try:
        test_rule_id = int(test_rule_id)
    except ValueError:
        test_rule_id = 0

    try:
        test_task_id = int(test_task_id)
    except ValueError:
        test_task_id = 0

    try:
        test_details = json.loads(
            str(request.query_params.get("test_details") or "[]")
        )
    except Exception:
        test_details = []

    if not isinstance(test_details, list):
        test_details = []

    try:
        batch_condition_stats = json.loads(
            str(request.query_params.get("batch_condition_stats") or "[]")
        )
    except Exception:
        batch_condition_stats = []

    if not isinstance(batch_condition_stats, list):
        batch_condition_stats = []

    batch_operator = str(
        request.query_params.get("batch_operator") or "and"
    ).lower()

    if batch_operator not in ("and", "or"):
        batch_operator = "and"

    try:
        batch_rejected = json.loads(
            str(request.query_params.get("batch_rejected") or "[]")
        )
    except Exception:
        batch_rejected = []

    if not isinstance(batch_rejected, list):
        batch_rejected = []

    batch_values = {}

    for key in (
        "batch_rule_id",
        "batch_total",
        "batch_matched",
        "batch_match_rate",
        "batch_limit",
    ):
        try:
            batch_values[key] = int(request.query_params.get(key) or 0)
        except (TypeError, ValueError):
            batch_values[key] = 0

    if batch_values["batch_limit"] not in (20, 50, 100):
        batch_values["batch_limit"] = 20

    batch_assessment = automation_condition_coverage_assessment(
        batch_values["batch_total"],
        batch_values["batch_matched"],
    )
    batch_focus = automation_condition_focus_assessment(
        batch_condition_stats,
        batch_operator,
    )

    batch_task_id_set = {
        value
        for value in str(
            request.query_params.get("batch_task_ids") or ""
        ).split(",")
        if value
    }
    batch_tasks = [
        dict(task)
        for task in test_tasks
        if str(task["id"]) in batch_task_id_set
    ]
    test_tasks_by_id = {
        int(task["id"]): dict(task)
        for task in test_tasks
    }
    batch_rejected_tasks = []

    for item in batch_rejected[:10]:
        if not isinstance(item, dict):
            continue

        try:
            rejected_task_id = int(item.get("id") or 0)
        except (TypeError, ValueError):
            continue

        task = test_tasks_by_id.get(rejected_task_id)

        if not task:
            continue

        failed_conditions = item.get("failed_conditions") or []

        if not isinstance(failed_conditions, list):
            failed_conditions = []

        task["failed_conditions"] = [
            str(label)[:120]
            for label in failed_conditions[:3]
        ]
        batch_rejected_tasks.append(task)

    for rule in rules:
        rule_data = dict(rule)

        try:
            conditions = json.loads(rule_data.get("conditions_json") or "{}")
        except Exception:
            conditions = {}

        condition_items = conditions.get("conditions") or []
        condition_mode = conditions.get("mode") or (
            condition_items[0].get("mode") if condition_items else "none"
        )
        condition_secondary_mode = (
            condition_items[1].get("mode")
            if len(condition_items) > 1
            else "none"
        )
        condition_tertiary_mode = (
            condition_items[2].get("mode")
            if len(condition_items) > 2
            else "none"
        )
        condition_operator = str(conditions.get("operator") or "and").lower()
        condition_value = str(
            (condition_items[0] if condition_items else conditions).get("value") or ""
        )
        condition_secondary_value = str(
            condition_items[1].get("value") or ""
            if len(condition_items) > 1
            else ""
        )
        condition_tertiary_value = str(
            condition_items[2].get("value") or ""
            if len(condition_items) > 2
            else ""
        )

        if condition_mode not in condition_labels:
            condition_mode = "none"

        if condition_secondary_mode not in condition_labels:
            condition_secondary_mode = "none"

        if condition_tertiary_mode not in condition_labels:
            condition_tertiary_mode = "none"

        if condition_operator not in ("and", "or"):
            condition_operator = "and"

        rule_data["condition_mode"] = condition_mode
        rule_data["condition_secondary_mode"] = condition_secondary_mode
        rule_data["condition_tertiary_mode"] = condition_tertiary_mode
        rule_data["condition_operator"] = condition_operator
        rule_data["has_conditions"] = any(
            mode != "none"
            for mode in (
                condition_mode,
                condition_secondary_mode,
                condition_tertiary_mode,
            )
        )
        rule_data["condition_value"] = (
            condition_value
            if condition_mode in ("price_high", "client_many_tasks")
            else ""
        )
        rule_data["condition_secondary_value"] = (
            condition_secondary_value
            if condition_secondary_mode in ("price_high", "client_many_tasks")
            else ""
        )
        rule_data["condition_tertiary_value"] = (
            condition_tertiary_value
            if condition_tertiary_mode in ("price_high", "client_many_tasks")
            else ""
        )
        rule_data["condition_worker"] = (
            condition_value if condition_mode == "worker_specific" else ""
        )
        rule_data["condition_secondary_worker"] = (
            condition_secondary_value
            if condition_secondary_mode == "worker_specific"
            else ""
        )
        rule_data["condition_tertiary_worker"] = (
            condition_tertiary_value
            if condition_tertiary_mode == "worker_specific"
            else ""
        )
        rule_data["condition_client"] = (
            condition_value if condition_mode == "client_specific" else ""
        )
        rule_data["condition_secondary_client"] = (
            condition_secondary_value
            if condition_secondary_mode == "client_specific"
            else ""
        )
        rule_data["condition_tertiary_client"] = (
            condition_tertiary_value
            if condition_tertiary_mode == "client_specific"
            else ""
        )
        rule_data["condition_catalog"] = (
            condition_value if condition_mode == "catalog_specific" else ""
        )
        rule_data["condition_secondary_catalog"] = (
            condition_secondary_value
            if condition_secondary_mode == "catalog_specific"
            else ""
        )
        rule_data["condition_tertiary_catalog"] = (
            condition_tertiary_value
            if condition_tertiary_mode == "catalog_specific"
            else ""
        )
        rule_data["condition_text"] = (
            condition_value if condition_mode == "task_text_contains" else ""
        )
        rule_data["condition_secondary_text"] = (
            condition_secondary_value
            if condition_secondary_mode == "task_text_contains"
            else ""
        )
        rule_data["condition_tertiary_text"] = (
            condition_tertiary_value
            if condition_tertiary_mode == "task_text_contains"
            else ""
        )

        condition_payloads = (
            condition_items
            if condition_items
            else [conditions]
        )
        selected_condition_labels = []

        for index, mode in enumerate((
            condition_mode,
            condition_secondary_mode,
            condition_tertiary_mode,
        )):
            if mode == "none":
                continue

            payload = condition_payloads[index] if index < len(condition_payloads) else {}
            selected_condition_labels.append(
                payload.get("label") or condition_labels[mode]
            )

        if len(selected_condition_labels) > 1:
            separator = " и " if condition_operator == "and" else " или "
            rule_data["condition_label"] = separator.join(selected_condition_labels)
        elif selected_condition_labels:
            rule_data["condition_label"] = selected_condition_labels[0]
        else:
            rule_data["condition_label"] = condition_labels["none"]

        rule_actions = actions_by_rule.get(rule_data["id"], [])
        rule_data["dry_run"] = {}

        if (
            test_rule_id == rule_data["id"]
            and test_result in ("match", "no_match")
        ):
            rule_data["dry_run"] = automation_dry_run_readiness(
                bool(rule_data["active"]),
                test_result == "match",
                rule_actions,
            )

        rules_view.append(rule_data)

    builder_stats = {
        "total": len(rules_view),
        "active": len([rule for rule in rules_view if rule["active"]]),
        "disabled": len([rule for rule in rules_view if not rule["active"]]),
        "empty": len([
            rule
            for rule in rules_view
            if not actions_by_rule.get(rule["id"])
        ]),
        "with_conditions": len([
            rule
            for rule in rules_view
            if rule.get("has_conditions")
        ]),
    }

    return templates.TemplateResponse(
        request,
        "automation_builder.html",
        {
            "request": request,
            "username": username,
            "role": role,
            "rules": rules_view,
            "actions_by_rule": actions_by_rule,
            "trigger_labels": dict(AUTOMATION_TRIGGERS),
            "action_labels": dict(AUTOMATION_ACTIONS),
            "condition_presets": condition_presets,
            "condition_groups": condition_groups,
            "builder_stats": builder_stats,
            "workers": workers,
            "clients": clients,
            "catalog_items": catalog_items,
            "test_tasks": test_tasks,
            "test_rule_id": test_rule_id,
            "test_task_id": test_task_id,
            "test_result": test_result,
            "test_message": str(request.query_params.get("test_message") or ""),
            "test_operator": str(request.query_params.get("test_operator") or ""),
            "test_details": test_details,
            "batch_rule_id": batch_values["batch_rule_id"],
            "batch_total": batch_values["batch_total"],
            "batch_matched": batch_values["batch_matched"],
            "batch_match_rate": batch_values["batch_match_rate"],
            "batch_limit": batch_values["batch_limit"],
            "batch_tasks": batch_tasks,
            "batch_rejected_tasks": batch_rejected_tasks,
            "batch_condition_stats": batch_condition_stats,
            "batch_assessment": batch_assessment,
            "batch_focus": batch_focus,
            "settings": settings,
        }
    )


@app.post("/automation/rules/{rule_id}/test-condition")
async def test_automation_rule_condition(request: Request, rule_id: int):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role not in ("boss", "manager"):
        return RedirectResponse("/", status_code=302)

    company_id = get_user_company_id(username)
    disabled_response = require_feature(company_id, "automation")

    if disabled_response:
        return disabled_response

    form = await request.form()

    try:
        task_id = int(form.get("task_id") or 0)
    except (TypeError, ValueError):
        task_id = 0

    conn = connect()
    c = conn.cursor()

    rule = c.execute("""
    SELECT *
    FROM automation_rules
    WHERE id=?
      AND company_id=?
    """, (rule_id, company_id)).fetchone()

    task = c.execute("""
    SELECT id
    FROM tasks
    WHERE id=?
      AND company_id=?
      AND archived=0
    """, (task_id, company_id)).fetchone()

    if not rule or not task:
        conn.close()
        params = {
            "test_rule_id": rule_id,
            "test_task_id": task_id,
            "test_result": "error",
            "test_message": "Правило или заявка не найдены",
        }
        return RedirectResponse(
            f"/automation/builder?{urlencode(params)}",
            status_code=302,
        )

    diagnostics = automation_condition_diagnostics(
        c,
        company_id,
        rule,
        "task",
        task_id,
    )
    conn.close()

    condition_ok = diagnostics["matched"]
    failed_messages = [
        item["message"]
        for item in diagnostics["details"]
        if not item["matched"]
    ]
    params = {
        "test_rule_id": rule_id,
        "test_task_id": task_id,
        "test_result": "match" if condition_ok else "no_match",
        "test_message": (
            "Условия выполнены, правило может сработать"
            if condition_ok
            else ("; ".join(failed_messages) or "Условия не выполнены")[:180]
        ),
        "test_operator": diagnostics["operator_label"],
        "test_details": json.dumps(
            diagnostics["details"],
            ensure_ascii=False,
            separators=(",", ":"),
        ),
    }

    return RedirectResponse(
        f"/automation/builder?{urlencode(params)}",
        status_code=302,
    )


@app.post("/automation/rules/{rule_id}/test-condition-batch")
async def test_automation_rule_condition_batch(request: Request, rule_id: int):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role not in ("boss", "manager"):
        return RedirectResponse("/", status_code=302)

    company_id = get_user_company_id(username)
    disabled_response = require_feature(company_id, "automation")

    if disabled_response:
        return disabled_response

    form = await request.form()

    try:
        batch_limit = int(form.get("batch_limit") or 20)
    except (TypeError, ValueError):
        batch_limit = 20

    if batch_limit not in (20, 50, 100):
        batch_limit = 20

    conn = connect()
    c = conn.cursor()

    rule = c.execute("""
    SELECT *
    FROM automation_rules
    WHERE id=?
      AND company_id=?
    """, (rule_id, company_id)).fetchone()

    task_rows = c.execute("""
    SELECT id
    FROM tasks
    WHERE company_id=?
      AND archived=0
    ORDER BY task_date DESC, id DESC
    LIMIT ?
    """, (company_id, batch_limit)).fetchall()

    if not rule:
        conn.close()
        return RedirectResponse(
            "/automation/builder?batch_error=1",
            status_code=302,
        )

    summary = automation_condition_batch_summary(
        c,
        company_id,
        rule,
        [row["id"] for row in task_rows],
    )
    conn.close()

    params = {
        "batch_rule_id": rule_id,
        "batch_total": summary["total"],
        "batch_matched": summary["matched"],
        "batch_match_rate": summary["match_rate"],
        "batch_limit": batch_limit,
        "batch_task_ids": ",".join(
            str(task_id) for task_id in summary["matched_task_ids"]
        ),
        "batch_condition_stats": json.dumps(
            summary["condition_stats"],
            ensure_ascii=False,
            separators=(",", ":"),
        ),
        "batch_operator": summary["operator"],
        "batch_rejected": json.dumps(
            summary["rejected_tasks"],
            ensure_ascii=False,
            separators=(",", ":"),
        ),
    }

    return RedirectResponse(
        f"/automation/builder?{urlencode(params)}",
        status_code=302,
    )


@app.get("/automation/rules/export")
async def automation_rules_export(
    request: Request,
    rule_filter: str = "",
    rule_trigger_filter: str = "",
    rule_action_filter: str = "",
    rule_search: str = ""
):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role not in ("boss", "manager"):
        return RedirectResponse("/", status_code=302)

    company_id = get_user_company_id(username)
    disabled_response = require_feature(company_id, "automation")

    if disabled_response:
        return disabled_response

    selected_rule_filter = rule_filter if rule_filter in ("active", "disabled") else ""
    trigger_keys = {key for key, _ in AUTOMATION_TRIGGERS}
    action_keys = {key for key, _ in AUTOMATION_ACTIONS}
    selected_rule_trigger_filter = rule_trigger_filter if rule_trigger_filter in trigger_keys else ""
    selected_rule_action_filter = rule_action_filter if rule_action_filter in action_keys else ""
    selected_rule_search = (rule_search or "").strip()[:80]
    rule_filter_sql = ""
    rule_params = [company_id]

    if selected_rule_filter == "active":
        rule_filter_sql = "AND automation_rules.active=1"
    elif selected_rule_filter == "disabled":
        rule_filter_sql = "AND automation_rules.active=0"

    if selected_rule_trigger_filter:
        rule_filter_sql += "\n      AND automation_rules.trigger_key=?"
        rule_params.append(selected_rule_trigger_filter)

    if selected_rule_action_filter:
        rule_filter_sql += """
      AND EXISTS (
          SELECT 1
          FROM automation_actions action_filter
          WHERE action_filter.company_id=automation_rules.company_id
            AND action_filter.rule_id=automation_rules.id
            AND action_filter.action_key=?
      )
        """
        rule_params.append(selected_rule_action_filter)

    if selected_rule_search:
        rule_filter_sql += """
      AND (
        automation_rules.name LIKE ?
        OR EXISTS (
            SELECT 1
            FROM automation_actions search_actions
            WHERE search_actions.company_id=automation_rules.company_id
              AND search_actions.rule_id=automation_rules.id
              AND search_actions.payload_json LIKE ?
        )
      )
        """
        rule_params.extend([
            f"%{selected_rule_search}%",
            f"%{selected_rule_search}%"
        ])

    conn = connect()
    c = conn.cursor()

    rules = c.execute(f"""
    SELECT
        automation_rules.*,
        COUNT(automation_actions.id) AS action_count,
        GROUP_CONCAT(automation_actions.action_key) AS action_keys
    FROM automation_rules
    LEFT JOIN automation_actions
      ON automation_actions.rule_id=automation_rules.id
      AND automation_actions.company_id=automation_rules.company_id
    WHERE automation_rules.company_id=?
      {rule_filter_sql}
    GROUP BY automation_rules.id
    ORDER BY automation_rules.id DESC
    """, rule_params).fetchall()

    conn.close()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "id",
        "name",
        "trigger_key",
        "active",
        "action_count",
        "action_keys",
        "created_by",
        "created_at"
    ])

    for rule in rules:
        writer.writerow([
            rule["id"],
            rule["name"],
            rule["trigger_key"],
            rule["active"],
            rule["action_count"],
            rule["action_keys"] or "",
            rule["created_by"] or "",
            rule["created_at"] or ""
        ])

    content = "\ufeff" + output.getvalue()

    return Response(
        content,
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f"attachment; filename=automation_rules_{selected_rule_filter or 'all'}_{selected_rule_trigger_filter or 'all'}_{selected_rule_action_filter or 'all'}_{selected_rule_search or 'all'}.csv"
        }
    )


@app.get("/automation/events/export")
async def automation_events_export(
    request: Request,
    event_filter: str = "",
    trigger_filter: str = "",
    event_search: str = "",
    event_entity_filter: str = "",
    event_date_from: str = "",
    event_date_to: str = "",
    event_rule_id: str = ""
):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role not in ("boss", "manager"):
        return RedirectResponse("/", status_code=302)

    company_id = get_user_company_id(username)
    disabled_response = require_feature(company_id, "automation")

    if disabled_response:
        return disabled_response

    selected_event_filter = event_filter if event_filter in ("pending", "done", "skipped", "failed") else ""
    trigger_keys = {key for key, _ in AUTOMATION_TRIGGERS}
    entity_keys = {"task", "client", "company"}
    selected_trigger_filter = trigger_filter if trigger_filter in trigger_keys else ""
    selected_event_search = (event_search or "").strip()[:80]
    selected_event_entity_filter = event_entity_filter if event_entity_filter in entity_keys else ""
    selected_event_date_from = (event_date_from or "").strip()[:10]
    selected_event_date_to = (event_date_to or "").strip()[:10]
    try:
        selected_event_rule_id = int(event_rule_id or 0)
    except ValueError:
        selected_event_rule_id = 0
    if selected_event_rule_id < 0:
        selected_event_rule_id = 0
    event_filter_sql = ""
    event_params = [company_id]

    for selected_date in (selected_event_date_from, selected_event_date_to):
        if selected_date:
            try:
                datetime.strptime(selected_date, "%Y-%m-%d")
            except ValueError:
                selected_event_date_from = ""
                selected_event_date_to = ""
                break

    if selected_event_filter:
        event_filter_sql = "AND automation_events.status=?"
        event_params.append(selected_event_filter)

    if selected_event_rule_id:
        event_filter_sql += "\n      AND automation_events.rule_id=?"
        event_params.append(selected_event_rule_id)

    if selected_trigger_filter:
        event_filter_sql += "\n      AND automation_events.trigger_key=?"
        event_params.append(selected_trigger_filter)

    if selected_event_entity_filter:
        event_filter_sql += "\n      AND automation_events.entity_type=?"
        event_params.append(selected_event_entity_filter)

    if selected_event_search:
        event_filter_sql += """
      AND (
        automation_events.message LIKE ?
        OR automation_rules.name LIKE ?
      )
        """
        event_params.extend([
            f"%{selected_event_search}%",
            f"%{selected_event_search}%"
        ])

    if selected_event_date_from:
        event_filter_sql += "\n      AND substr(automation_events.created_at, 1, 10) >= ?"
        event_params.append(selected_event_date_from)

    if selected_event_date_to:
        event_filter_sql += "\n      AND substr(automation_events.created_at, 1, 10) <= ?"
        event_params.append(selected_event_date_to)

    conn = connect()
    c = conn.cursor()

    events = c.execute(f"""
    SELECT
        automation_events.*,
        automation_rules.name AS rule_name
    FROM automation_events
    LEFT JOIN automation_rules
      ON automation_rules.id=automation_events.rule_id
      AND automation_rules.company_id=automation_events.company_id
    WHERE automation_events.company_id=?
      {event_filter_sql}
    ORDER BY automation_events.id DESC
    LIMIT 500
    """, event_params).fetchall()

    conn.close()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "id",
        "rule_id",
        "rule_name",
        "trigger_key",
        "status",
        "entity_type",
        "entity_id",
        "message",
        "created_at",
        "processed_at",
        "retry_count",
        "last_retried_at",
    ])

    for event in events:
        writer.writerow([
            event["id"],
            event["rule_id"],
            event["rule_name"] or "",
            event["trigger_key"],
            event["status"],
            event["entity_type"],
            event["entity_id"],
            event["message"] or "",
            event["created_at"],
            event["processed_at"] or "",
            event["retry_count"] or 0,
            event["last_retried_at"] or "",
        ])

    content = "\ufeff" + output.getvalue()

    return Response(
        content,
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f"attachment; filename=automation_events_{selected_event_filter or 'all'}_{selected_trigger_filter or 'all'}_{selected_event_entity_filter or 'all'}_{selected_event_search or 'all'}_{selected_event_date_from or 'from'}_{selected_event_date_to or 'to'}_rule_{selected_event_rule_id or 'all'}.csv"
        }
    )


@app.post("/automation/ai-digest/run")
async def run_ai_digest_scheduler_page(request: Request):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role not in ("boss", "manager"):
        return RedirectResponse("/", status_code=302)

    company_id = get_user_company_id(username)
    disabled_response = require_feature(company_id, "automation")

    if disabled_response:
        return disabled_response

    disabled_response = require_feature(company_id, "ai_insights")

    if disabled_response:
        return disabled_response

    result = run_ai_digest_scheduler(company_id)

    return RedirectResponse(
        f"/automation?scheduler=1&daily={result['daily']}&weekly={result['weekly']}&follow_ups={result['follow_ups']}&skipped={result['skipped']}",
        status_code=302
    )


@app.post("/automation/rules")
async def create_automation_rule(request: Request):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role not in ("boss", "manager"):
        return RedirectResponse("/", status_code=302)

    company_id = get_user_company_id(username)
    disabled_response = require_feature(company_id, "automation")

    if disabled_response:
        return disabled_response

    form = await request.form()
    name = str(form.get("name") or "").strip()
    trigger_key = str(form.get("trigger_key") or "").strip()
    action_key = str(form.get("action_key") or "").strip()
    condition_mode = str(form.get("condition_mode") or "none").strip()
    target_username = str(form.get("target_username") or username).strip()
    message = str(form.get("message") or "").strip()
    task_delay_days, task_priority, task_deadline_hours = (
        automation_create_task_settings({
            "task_delay_days": form.get("task_delay_days"),
            "task_priority": form.get("task_priority"),
            "task_deadline_hours": form.get("task_deadline_hours"),
        })
    )
    task_max_daily_load = automation_task_max_daily_load({
        "task_max_daily_load": form.get("task_max_daily_load"),
    })
    task_capacity_fallback_days = automation_task_capacity_fallback_days({
        "task_capacity_fallback_days": form.get(
            "task_capacity_fallback_days"
        ),
    })
    task_business_days_only = automation_task_business_days_only({
        "task_business_days_only": form.get("task_business_days_only"),
    })

    trigger_keys = {key for key, _ in AUTOMATION_TRIGGERS}
    action_keys = {key for key, _ in AUTOMATION_ACTIONS}

    if not name:
        return RedirectResponse("/automation?error=name", status_code=302)

    if trigger_key not in trigger_keys or action_key not in action_keys:
        return RedirectResponse("/automation?error=invalid", status_code=302)

    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    if action_key in ("notification", "telegram_alert") and not message:
        message = f"Автоматизация: {name}"

    if action_key == "ai_digest" and not target_username:
        target_username = username

    if action_key == "ai_digest" and not message:
        message = "ИИ-сводка по бизнесу"

    quick_condition_presets = {
        "status_done": {
            "mode": "status_done",
            "field": "status",
            "operator": "equals",
            "value": "Завершено",
            "label": "Только завершённые заявки",
        },
        "worker_unassigned": {
            "mode": "worker_unassigned",
            "field": "workers",
            "operator": "empty",
            "label": "Только задачи без исполнителя",
        },
        "payment_paid": {
            "mode": "payment_paid",
            "field": "payment_status",
            "operator": "equals",
            "value": "Оплачено",
            "label": "Только оплаченные заявки",
        },
    }
    conditions_json = quick_condition_presets.get(condition_mode, {})

    payload = {
        "target_username": target_username,
        "message": message
    }

    if action_key == "email":
        payload["subject"] = f"Автоматизация: {name}"
    elif action_key == "create_task":
        payload["task_delay_days"] = task_delay_days
        payload["task_priority"] = task_priority
        payload["task_deadline_hours"] = task_deadline_hours
        payload["task_max_daily_load"] = task_max_daily_load
        payload["task_capacity_fallback_days"] = (
            task_capacity_fallback_days
        )
        payload["task_business_days_only"] = task_business_days_only

    conn = connect()
    c = conn.cursor()

    if not automation_action_target_is_valid(
        c,
        company_id,
        action_key,
        target_username,
    ):
        conn.close()
        return RedirectResponse("/automation?error=target", status_code=302)

    c.execute("""
    INSERT INTO automation_rules (
        company_id, name, trigger_key, conditions_json,
        active, created_by, created_at, updated_at
    )
    VALUES (?, ?, ?, ?, 1, ?, ?, ?)
    """, (
        company_id,
        name,
        trigger_key,
        json.dumps(conditions_json, ensure_ascii=False),
        username,
        now,
        now
    ))

    rule_id = c.lastrowid

    c.execute("""
    INSERT INTO automation_actions (
        company_id, rule_id, action_key, payload_json,
        sort_order, active, created_at
    )
    VALUES (?, ?, ?, ?, 1, 1, ?)
    """, (
        company_id,
        rule_id,
        action_key,
        json.dumps(payload, ensure_ascii=False),
        now
    ))

    conn.commit()
    conn.close()

    return RedirectResponse("/automation?created=1", status_code=302)




@app.get("/automation/rules/{rule_id}/events/export")
async def automation_rule_events_export(request: Request, rule_id: int):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role not in ("boss", "manager"):
        return RedirectResponse("/", status_code=302)

    company_id = get_user_company_id(username)
    disabled_response = require_feature(company_id, "automation")

    if disabled_response:
        return disabled_response

    conn = connect()
    c = conn.cursor()

    rule = c.execute("""
    SELECT *
    FROM automation_rules
    WHERE id=?
      AND company_id=?
    """, (rule_id, company_id)).fetchone()

    if not rule:
        conn.close()
        return RedirectResponse("/automation", status_code=302)

    events = c.execute("""
    SELECT *
    FROM automation_events
    WHERE company_id=?
      AND rule_id=?
    ORDER BY id DESC
    """, (company_id, rule_id)).fetchall()

    conn.close()

    output = io.StringIO()
    writer = csv.writer(output)

    writer.writerow([
        "id",
        "rule_name",
        "trigger_key",
        "entity_type",
        "entity_id",
        "status",
        "message",
        "created_at",
        "processed_at"
    ])

    for event in events:
        writer.writerow([
            event["id"],
            rule["name"],
            event["trigger_key"],
            event["entity_type"] or "",
            event["entity_id"] or "",
            event["status"],
            event["message"] or "",
            event["created_at"] or "",
            event["processed_at"] or ""
        ])

    return Response(
        content=output.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f"attachment; filename=automation_rule_{rule_id}_events.csv"
        }
    )

@app.get("/automation/rules/{rule_id}", response_class=HTMLResponse)
async def automation_rule_detail(request: Request, rule_id: int):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role not in ("boss", "manager"):
        return RedirectResponse("/", status_code=302)

    company_id = get_user_company_id(username)
    disabled_response = require_feature(company_id, "automation")

    if disabled_response:
        return disabled_response

    settings = get_company_settings(company_id)

    conn = connect()
    c = conn.cursor()

    rule = c.execute("""
    SELECT *
    FROM automation_rules
    WHERE id=?
      AND company_id=?
    """, (rule_id, company_id)).fetchone()

    if not rule:
        conn.close()
        return RedirectResponse("/automation", status_code=302)

    actions = c.execute("""
    SELECT *
    FROM automation_actions
    WHERE company_id=?
      AND rule_id=?
    ORDER BY sort_order, id
    """, (company_id, rule_id)).fetchall()

    action_runs = c.execute("""
    SELECT
        automation_action_runs.*,
        automation_actions.action_key,
        source_task.client AS source_client,
        source_task.status AS source_status,
        created_task.client AS created_client,
        created_task.status AS created_status
    FROM automation_action_runs
    JOIN automation_actions
      ON automation_actions.id=automation_action_runs.action_id
      AND automation_actions.company_id=automation_action_runs.company_id
    LEFT JOIN tasks source_task
      ON source_task.id=automation_action_runs.entity_id
      AND source_task.company_id=automation_action_runs.company_id
      AND automation_action_runs.entity_type='task'
    LEFT JOIN tasks created_task
      ON created_task.id=automation_action_runs.created_entity_id
      AND created_task.company_id=automation_action_runs.company_id
      AND automation_action_runs.created_entity_type='task'
    WHERE automation_action_runs.company_id=?
      AND automation_actions.rule_id=?
    ORDER BY automation_action_runs.id DESC
    LIMIT 30
    """, (company_id, rule_id)).fetchall()

    events = c.execute("""
    SELECT *
    FROM automation_events
    WHERE company_id=?
      AND rule_id=?
    ORDER BY id DESC
    LIMIT 20
    """, (company_id, rule_id)).fetchall()

    users = c.execute("""
    SELECT username, role
    FROM users
    WHERE company_id=?
      AND COALESCE(is_active, 1)=1
    ORDER BY
        CASE role
            WHEN 'worker' THEN 1
            WHEN 'manager' THEN 2
            WHEN 'boss' THEN 3
            ELSE 4
        END,
        username
    """, (company_id,)).fetchall()

    event_counts = {
        row["status"]: row["count"]
        for row in c.execute("""
        SELECT status, COUNT(*) as count
        FROM automation_events
        WHERE company_id=?
          AND rule_id=?
        GROUP BY status
        """, (company_id, rule_id)).fetchall()
    }

    conn.close()

    done_count = event_counts.get("done", 0)
    skipped_count = event_counts.get("skipped", 0)
    pending_count = event_counts.get("pending", 0)
    success_rate = round(done_count / max(done_count + skipped_count, 1) * 100, 1)

    a3_health_score = 100

    if not rule["active"]:
        a3_health_score -= 30

    if not actions:
        a3_health_score -= 30

    if skipped_count > 0:
        a3_health_score -= 15

    if pending_count > 0:
        a3_health_score -= 10

    a3_health_score = max(a3_health_score, 0)

    if not actions:
        diagnostic_title = "Нет действий"
        diagnostic_message = "Правило включено, но не сможет ничего выполнить без action."
        graph_status = "Проблема"
        graph_status_color = "#dc2626"
        a3_recommendation = "Добавьте хотя бы одно действие: уведомление, Telegram или ИИ-сводку."

    elif not rule["active"]:
        diagnostic_title = "Правило отключено"
        diagnostic_message = "Правило не будет запускаться, пока его не включить."
        graph_status = "Проблема"
        graph_status_color = "#dc2626"
        a3_recommendation = "Включите правило, если оно должно работать в автоматизации."

    elif skipped_count > 0 or pending_count > 0:
        diagnostic_title = "Нужно внимание"
        diagnostic_message = "У правила есть пропущенные или ожидающие события."
        graph_status = "Нужно внимание"
        graph_status_color = "#f59e0b"
        a3_recommendation = "Проверьте последние события цепочки и повторите пропущенные."

    else:
        diagnostic_title = "Стабильно"
        diagnostic_message = "Правило выглядит рабочим."
        graph_status = "Стабильно"
        graph_status_color = "#16a34a"
        a3_recommendation = "Правило работает стабильно. Продолжайте мониторинг."

    return templates.TemplateResponse(
        request,
        "automation_rule_detail.html",
        {
            "request": request,
            "username": username,
            "role": role,
            "rule": rule,
            "actions": actions,
            "action_runs": action_runs,
            "users": users,
            "events": events,
            "trigger_labels": dict(AUTOMATION_TRIGGERS),
            "action_labels": dict(AUTOMATION_ACTIONS),
            "status_labels": AUTOMATION_STATUS_LABELS,
            "done_count": done_count,
            "skipped_count": skipped_count,
            "pending_count": pending_count,
            "success_rate": success_rate,
            "diagnostic_title": diagnostic_title,
            "diagnostic_message": diagnostic_message,
            "graph_status": graph_status,
            "graph_status_color": graph_status_color,
            "a3_health_score": a3_health_score,
            "a3_recommendation": a3_recommendation,
            "settings": settings
        }
    )

@app.post("/automation/rules/{rule_id}/edit")
async def edit_automation_rule(request: Request, rule_id: int):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role not in ("boss", "manager"):
        return RedirectResponse("/", status_code=302)

    company_id = get_user_company_id(username)
    disabled_response = require_feature(company_id, "automation")

    if disabled_response:
        return disabled_response

    form = await request.form()
    name = str(form.get("name") or "").strip()
    target_username = str(form.get("target_username") or username).strip()
    message = str(form.get("message") or "").strip()

    if not name:
        return RedirectResponse("/automation?error=name", status_code=302)

    conn = connect()
    c = conn.cursor()

    rule = c.execute("""
    SELECT id
    FROM automation_rules
    WHERE id=?
      AND company_id=?
    """, (rule_id, company_id)).fetchone()

    if not rule:
        conn.close()
        return RedirectResponse("/automation", status_code=302)

    target_exists = c.execute("""
    SELECT id
    FROM users
    WHERE company_id=?
      AND username=?
    """, (company_id, target_username)).fetchone()

    if not target_exists:
        conn.close()
        return RedirectResponse("/automation?error=target", status_code=302)

    payload = {
        "target_username": target_username,
        "message": message
    }
    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    c.execute("""
    UPDATE automation_rules
    SET name=?, updated_at=?
    WHERE id=?
      AND company_id=?
    """, (
        name,
        now,
        rule_id,
        company_id
    ))

    action = c.execute("""
    SELECT id
    FROM automation_actions
    WHERE company_id=?
      AND rule_id=?
    ORDER BY sort_order, id
    LIMIT 1
    """, (company_id, rule_id)).fetchone()

    if action:
        c.execute("""
        UPDATE automation_actions
        SET payload_json=?
        WHERE id=?
          AND company_id=?
        """, (
            json.dumps(payload, ensure_ascii=False),
            action["id"],
            company_id
        ))

    conn.commit()
    conn.close()

    return RedirectResponse("/automation?updated=1", status_code=302)


@app.post("/automation/rules/{rule_id}/conditions")
async def update_automation_rule_conditions(request: Request, rule_id: int):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role not in ("boss", "manager"):
        return RedirectResponse("/", status_code=302)

    company_id = get_user_company_id(username)
    disabled_response = require_feature(company_id, "automation")

    if disabled_response:
        return disabled_response

    form = await request.form()
    condition_mode = str(form.get("condition_mode") or "none").strip()
    condition_secondary_mode = str(
        form.get("condition_secondary_mode") or "none"
    ).strip()
    condition_tertiary_mode = str(
        form.get("condition_tertiary_mode") or "none"
    ).strip()
    condition_values = [
        str(form.get("condition_value") or "").strip(),
        str(form.get("condition_secondary_value") or "").strip(),
        str(form.get("condition_tertiary_value") or "").strip(),
    ]
    condition_workers = [
        str(form.get("condition_worker") or "").strip(),
        str(form.get("condition_secondary_worker") or "").strip(),
        str(form.get("condition_tertiary_worker") or "").strip(),
    ]
    condition_clients = [
        str(form.get("condition_client") or "").strip(),
        str(form.get("condition_secondary_client") or "").strip(),
        str(form.get("condition_tertiary_client") or "").strip(),
    ]
    condition_catalog_items = [
        str(form.get("condition_catalog") or "").strip(),
        str(form.get("condition_secondary_catalog") or "").strip(),
        str(form.get("condition_tertiary_catalog") or "").strip(),
    ]
    condition_texts = [
        str(form.get("condition_text") or "").strip(),
        str(form.get("condition_secondary_text") or "").strip(),
        str(form.get("condition_tertiary_text") or "").strip(),
    ]
    condition_operator = str(form.get("condition_operator") or "and").strip().lower()
    allowed_modes = {
        "none": {},
        "priority_high": {
            "mode": "priority_high",
            "field": "priority",
            "operator": "equals",
            "value": "Высокий",
            "label": "Только высокий приоритет",
        },
        "emergency": {
            "mode": "emergency",
            "field": "priority",
            "operator": "equals",
            "value": "Срочно",
            "label": "Только срочные заявки",
        },
        "task_text_contains": {
            "mode": "task_text_contains",
            "field": "task_text",
            "operator": "contains",
            "value": "",
            "label": "Текст заявки содержит",
        },
        "status_new": {
            "mode": "status_new",
            "field": "status",
            "operator": "equals",
            "value": "Новая",
            "label": "Только новые заявки",
        },
        "status_in_progress": {
            "mode": "status_in_progress",
            "field": "status",
            "operator": "equals",
            "value": "В работе",
            "label": "Только заявки в работе",
        },
        "status_done": {
            "mode": "status_done",
            "field": "status",
            "operator": "equals",
            "value": "Завершено",
            "label": "Только завершённые заявки",
        },
        "status_cancelled": {
            "mode": "status_cancelled",
            "field": "status",
            "operator": "equals",
            "value": "Отменено",
            "label": "Только отменённые заявки",
        },
        "payment_unpaid": {
            "mode": "payment_unpaid",
            "field": "payment_status",
            "operator": "equals",
            "value": "Не оплачено",
            "label": "Только неоплаченные заявки",
        },
        "payment_partial": {
            "mode": "payment_partial",
            "field": "payment_status",
            "operator": "equals",
            "value": "Частично оплачено",
            "label": "Только частично оплаченные заявки",
        },
        "payment_paid": {
            "mode": "payment_paid",
            "field": "payment_status",
            "operator": "equals",
            "value": "Оплачено",
            "label": "Только оплаченные заявки",
        },
        "worker_assigned": {
            "mode": "worker_assigned",
            "field": "workers",
            "operator": "not_empty",
            "label": "Только задачи с исполнителем",
        },
        "worker_unassigned": {
            "mode": "worker_unassigned",
            "field": "workers",
            "operator": "empty",
            "label": "Только задачи без исполнителя",
        },
        "worker_specific": {
            "mode": "worker_specific",
            "field": "workers",
            "operator": "contains",
            "value": "",
            "label": "Только выбранный исполнитель",
        },
        "date_today": {
            "mode": "date_today",
            "field": "task_date",
            "operator": "equals_today",
            "label": "Только задачи на сегодня",
        },
        "date_tomorrow": {
            "mode": "date_tomorrow",
            "field": "task_date",
            "operator": "equals_tomorrow",
            "label": "Только задачи на завтра",
        },
        "date_next_7_days": {
            "mode": "date_next_7_days",
            "field": "task_date",
            "operator": "within_next_7_days",
            "label": "Только задачи на ближайшие 7 дней",
        },
        "date_overdue": {
            "mode": "date_overdue",
            "field": "task_date",
            "operator": "before_today",
            "label": "Только просроченные задачи",
        },
        "date_future": {
            "mode": "date_future",
            "field": "task_date",
            "operator": "after_today",
            "label": "Только будущие задачи",
        },
        "price_high": {
            "mode": "price_high",
            "field": "price",
            "operator": "gte",
            "value": "10000",
            "label": "Только дорогие заявки",
        },
        "price_missing": {
            "mode": "price_missing",
            "field": "price",
            "operator": "empty_or_zero",
            "label": "Только заявки без цены",
        },
        "catalog_specific": {
            "mode": "catalog_specific",
            "field": "catalog_item_id",
            "operator": "contains",
            "value": "",
            "label": "Только выбранная позиция каталога",
        },
        "sla_today": {
            "mode": "sla_today",
            "field": "deadline_at",
            "operator": "date_today",
            "label": "Только дедлайн сегодня",
        },
        "sla_overdue": {
            "mode": "sla_overdue",
            "field": "deadline_at",
            "operator": "before_now",
            "label": "Только просроченный SLA",
        },
        "sla_due_24h": {
            "mode": "sla_due_24h",
            "field": "deadline_at",
            "operator": "within_24h",
            "label": "Только дедлайн в ближайшие 24 часа",
        },
        "client_specific": {
            "mode": "client_specific",
            "field": "client_id",
            "operator": "equals",
            "value": "",
            "label": "Только выбранный клиент",
        },
        "client_new": {
            "mode": "client_new",
            "field": "client_id",
            "operator": "task_count_lte",
            "value": "1",
            "label": "Только новые клиенты",
        },
        "client_repeat": {
            "mode": "client_repeat",
            "field": "client_id",
            "operator": "task_count_gte",
            "value": "2",
            "label": "Только постоянные клиенты",
        },
        "client_vip": {
            "mode": "client_vip",
            "field": "client_notes",
            "operator": "contains",
            "value": "VIP",
            "label": "Только VIP клиенты",
        },
        "client_has_debt": {
            "mode": "client_has_debt",
            "field": "payment_status",
            "operator": "has_unpaid_tasks",
            "label": "Только клиенты с долгом",
        },
        "client_many_tasks": {
            "mode": "client_many_tasks",
            "field": "client_id",
            "operator": "task_count_gte",
            "value": "5",
            "label": "Только клиенты с большим количеством заявок",
        },
    }

    if (
        condition_mode not in allowed_modes
        or condition_secondary_mode not in allowed_modes
        or condition_tertiary_mode not in allowed_modes
        or condition_operator not in ("and", "or")
    ):
        return RedirectResponse("/automation/builder?conditions_error=1", status_code=302)

    selected_modes = [
        (
            mode,
            condition_values[index],
            condition_workers[index],
            condition_clients[index],
            condition_catalog_items[index],
            condition_texts[index],
        )
        for index, mode in enumerate((
            condition_mode,
            condition_secondary_mode,
            condition_tertiary_mode,
        ))
        if mode != "none"
    ]

    selected_conditions = []

    for (
        mode,
        raw_value,
        selected_worker,
        selected_client,
        selected_catalog_item,
        condition_text,
    ) in selected_modes:
        condition = dict(allowed_modes[mode])

        if mode == "task_text_contains":
            keyword = condition_text[:120].strip()

            if not keyword:
                return RedirectResponse("/automation/builder?conditions_error=1", status_code=302)

            condition["value"] = keyword
            condition["label"] = f"Текст содержит: {keyword}"

        elif mode == "worker_specific":
            if not selected_worker:
                return RedirectResponse("/automation/builder?conditions_error=1", status_code=302)

            condition["value"] = selected_worker
            condition["label"] = f"Исполнитель: {selected_worker}"

        elif mode == "client_specific":
            try:
                client_id = int(selected_client)
            except (TypeError, ValueError):
                return RedirectResponse("/automation/builder?conditions_error=1", status_code=302)

            condition["value"] = str(client_id)
            condition["label"] = f"Клиент #{client_id}"

        elif mode == "catalog_specific":
            try:
                catalog_item_id = int(selected_catalog_item)
            except (TypeError, ValueError):
                return RedirectResponse("/automation/builder?conditions_error=1", status_code=302)

            condition["value"] = str(catalog_item_id)
            condition["label"] = f"Позиция каталога #{catalog_item_id}"

        elif mode == "price_high":
            try:
                threshold = max(float(raw_value.replace(",", ".")), 0) if raw_value else 10000
            except ValueError:
                return RedirectResponse("/automation/builder?conditions_error=1", status_code=302)

            condition["value"] = f"{threshold:g}"
            condition["label"] = f"Цена заявки от {threshold:g} ₽"

        elif mode == "client_many_tasks":
            try:
                threshold = max(int(raw_value), 1) if raw_value else 5
            except ValueError:
                return RedirectResponse("/automation/builder?conditions_error=1", status_code=302)

            condition["value"] = str(threshold)
            condition["label"] = f"У клиента от {threshold} заявок"

        selected_conditions.append(condition)

    if len(selected_modes) > 1:
        conditions_payload = {
            "operator": condition_operator,
            "conditions": selected_conditions,
        }
    elif selected_modes:
        conditions_payload = selected_conditions[0]
    else:
        conditions_payload = {}

    conn = connect()
    c = conn.cursor()

    rule = c.execute("""
    SELECT id
    FROM automation_rules
    WHERE id=?
      AND company_id=?
    """, (rule_id, company_id)).fetchone()

    if not rule:
        conn.close()
        return RedirectResponse("/automation/builder?conditions_error=1", status_code=302)

    for condition in selected_conditions:
        if condition.get("mode") == "worker_specific":
            worker_exists = c.execute("""
            SELECT 1
            FROM users
            WHERE company_id=?
              AND role='worker'
              AND username=?
              AND COALESCE(is_active, 1)=1
            """, (company_id, condition["value"])).fetchone()

            if not worker_exists:
                conn.close()
                return RedirectResponse("/automation/builder?conditions_error=1", status_code=302)

        elif condition.get("mode") == "client_specific":
            client_row = c.execute("""
            SELECT id, name
            FROM clients
            WHERE company_id=?
              AND id=?
            """, (company_id, condition["value"])).fetchone()

            if not client_row:
                conn.close()
                return RedirectResponse("/automation/builder?conditions_error=1", status_code=302)

            condition["label"] = f"Клиент: {client_row['name']}"

        elif condition.get("mode") == "catalog_specific":
            catalog_item = c.execute("""
            SELECT id, name
            FROM catalog_items
            WHERE company_id=?
              AND id=?
              AND active=1
            """, (company_id, condition["value"])).fetchone()

            if not catalog_item:
                conn.close()
                return RedirectResponse("/automation/builder?conditions_error=1", status_code=302)

            condition["label"] = f"Каталог: {catalog_item['name']}"

    c.execute("""
    UPDATE automation_rules
    SET conditions_json=?,
        updated_at=?
    WHERE id=?
      AND company_id=?
    """, (
        json.dumps(conditions_payload, ensure_ascii=False),
        datetime.now().strftime("%Y-%m-%d %H:%M"),
        rule_id,
        company_id,
    ))

    conn.commit()
    conn.close()

    return RedirectResponse("/automation/builder?conditions_updated=1", status_code=302)











@app.post("/automation/diagnostics/rules/{rule_id}/add-default-action")
async def add_default_action_to_rule(request: Request, rule_id: int):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role not in ("boss", "manager"):
        return RedirectResponse("/", status_code=302)

    company_id = get_user_company_id(username)

    disabled_response = require_feature(company_id, "automation")

    if disabled_response:
        return disabled_response

    conn = connect()
    c = conn.cursor()

    rule = c.execute("""
    SELECT *
    FROM automation_rules
    WHERE id=?
      AND company_id=?
    """, (rule_id, company_id)).fetchone()

    if not rule:
        conn.close()
        return RedirectResponse(
            "/automation/diagnostics?action_added=0",
            status_code=302
        )

    existing_action = c.execute("""
    SELECT id
    FROM automation_actions
    WHERE company_id=?
      AND rule_id=?
      AND active=1
    LIMIT 1
    """, (company_id, rule_id)).fetchone()

    if existing_action:
        conn.close()
        return RedirectResponse(
            "/automation/diagnostics?action_exists=1",
            status_code=302
        )

    payload = {
        "target_username": username,
        "message": f"Автоматизация: {rule['name']}"
    }

    c.execute("""
    INSERT INTO automation_actions (
        company_id,
        rule_id,
        action_key,
        payload_json,
        active,
        created_at
    )
    VALUES (?, ?, ?, ?, 1, ?)
    """, (
        company_id,
        rule_id,
        "notification",
        json.dumps(payload, ensure_ascii=False),
        datetime.now().strftime("%Y-%m-%d %H:%M")
    ))

    conn.commit()
    conn.close()

    return RedirectResponse(
        "/automation/diagnostics?action_added=1",
        status_code=302
    )

@app.post("/automation/diagnostics/rules/{rule_id}/enable")
async def enable_automation_rule_from_diagnostics(request: Request, rule_id: int):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role not in ("boss", "manager"):
        return RedirectResponse("/", status_code=302)

    company_id = get_user_company_id(username)
    disabled_response = require_feature(company_id, "automation")

    if disabled_response:
        return disabled_response

    conn = connect()
    c = conn.cursor()

    rule = c.execute("""
    SELECT *
    FROM automation_rules
    WHERE id=?
      AND company_id=?
      AND active=0
    """, (rule_id, company_id)).fetchone()

    if not rule:
        conn.close()
        return RedirectResponse("/automation/diagnostics?enable_skipped=1", status_code=302)

    c.execute("""
    UPDATE automation_rules
    SET active=1, updated_at=?
    WHERE id=?
      AND company_id=?
    """, (
        datetime.now().strftime("%Y-%m-%d %H:%M"),
        rule_id,
        company_id
    ))

    conn.commit()
    conn.close()

    return RedirectResponse("/automation/diagnostics?enabled=1", status_code=302)

@app.post("/automation/diagnostics/retry-skipped")
async def retry_skipped_automation_events(request: Request):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role != "boss":
        return RedirectResponse("/", status_code=302)

    company_id = get_user_company_id(username)
    disabled_response = require_feature(company_id, "automation")

    if disabled_response:
        return disabled_response

    conn = connect()
    c = conn.cursor()
    retry_cutoff = (
        datetime.now() - timedelta(
            minutes=SKIPPED_EVENT_RETRY_COOLDOWN_MINUTES,
        )
    ).isoformat(timespec="seconds")

    skipped_events = c.execute("""
    SELECT id, rule_id, trigger_key, entity_type, entity_id, message
    FROM automation_events
    WHERE company_id=?
      AND status='skipped'
      AND rule_id IS NOT NULL
      AND (
        last_retried_at IS NULL
        OR last_retried_at < ?
      )
    ORDER BY id DESC
    LIMIT 10
    """, (
        company_id,
        retry_cutoff,
    )).fetchall()

    conn.close()

    retried = 0
    not_ready = 0
    failed = 0
    events_by_rule = {}

    for event in skipped_events:
        events_by_rule.setdefault(event["rule_id"], []).append(dict(event))

    for rule_id, events in events_by_rule.items():
        replay_result = replay_a3_skipped_automation_events(
            company_id=company_id,
            rule_id=rule_id,
            events=events,
        )
        retried += replay_result.get("replayed", 0)
        not_ready += replay_result.get("not_ready", 0)
        failed += replay_result.get("failed", 0)

    try:
        create_ops_timeline_event(
            company_id=company_id,
            event_type="autonomous_retry",
            severity="warning" if failed else "info",
            title="Ручной повтор пропущенных событий",
            message=(
                f"Повторно выполнено: {retried}; "
                f"условия ещё не готовы: {not_ready}; "
                f"ошибок: {failed}"
            ),
            source="manual",
            target_type="automation_event",
            cooldown_minutes=5,
        )
    except Exception:
        pass

    return RedirectResponse(
        (
            "/automation/diagnostics?retry_skipped=1"
            f"&retried={retried}"
            f"&not_ready={not_ready}"
            f"&failed={failed}"
        ),
        status_code=302
    )

@app.post("/automation/events/cleanup")
async def cleanup_automation_events(request: Request):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role not in ("boss", "manager"):
        return RedirectResponse("/", status_code=302)

    company_id = get_user_company_id(username)

    disabled_response = require_feature(company_id, "automation")

    if disabled_response:
        return disabled_response

    conn = connect()
    c = conn.cursor()

    old_events = c.execute("""
    SELECT COUNT(*)
    FROM automation_events
    WHERE company_id=?
      AND created_at != ''
      AND datetime(created_at) < datetime('now', '-30 days')
    """, (company_id,)).fetchone()[0]

    c.execute("""
    DELETE FROM automation_events
    WHERE company_id=?
      AND created_at != ''
      AND datetime(created_at) < datetime('now', '-30 days')
    """, (company_id,))

    conn.commit()
    conn.close()

    return RedirectResponse(
        f"/automation/diagnostics?cleanup=1&deleted={old_events}",
        status_code=302
    )

@app.get("/automation/diagnostics/export")
async def automation_diagnostics_export(request: Request):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role not in ("boss", "manager"):
        return RedirectResponse("/", status_code=302)

    company_id = get_user_company_id(username)
    disabled_response = require_feature(company_id, "automation")

    if disabled_response:
        return disabled_response

    conn = connect()
    c = conn.cursor()

    disabled_rules = c.execute("""
    SELECT id, name, trigger_key, created_by, updated_at
    FROM automation_rules
    WHERE company_id=?
      AND active=0
    ORDER BY updated_at DESC, id DESC
    """, (company_id,)).fetchall()

    rules_without_actions = c.execute("""
    SELECT automation_rules.id, automation_rules.name, automation_rules.trigger_key, automation_rules.created_by, automation_rules.created_at
    FROM automation_rules
    LEFT JOIN automation_actions
      ON automation_actions.rule_id=automation_rules.id
      AND automation_actions.company_id=automation_rules.company_id
      AND automation_actions.active=1
    WHERE automation_rules.company_id=?
      AND automation_rules.active=1
    GROUP BY automation_rules.id
    HAVING COUNT(automation_actions.id)=0
    ORDER BY automation_rules.id DESC
    """, (company_id,)).fetchall()

    recent_skipped_event_rows = c.execute("""
    SELECT
        automation_events.id,
        automation_rules.name AS rule_name,
        automation_events.trigger_key,
        automation_events.entity_type,
        automation_events.entity_id,
        automation_events.message,
        automation_events.created_at,
        automation_events.processed_at,
        automation_events.retry_count,
        automation_events.last_retried_at
    FROM automation_events
    LEFT JOIN automation_rules
      ON automation_rules.id=automation_events.rule_id
      AND automation_rules.company_id=automation_events.company_id
    WHERE automation_events.company_id=?
      AND automation_events.status='skipped'
    ORDER BY automation_events.id DESC
    LIMIT 50
    """, (company_id,)).fetchall()

    conn.close()

    output = io.StringIO()
    writer = csv.writer(output)

    writer.writerow([
        "section",
        "id",
        "name_or_rule",
        "trigger_key",
        "entity_type",
        "entity_id",
        "message",
        "created_at",
        "updated_or_processed_at",
        "retry_count",
        "last_retried_at",
    ])

    for rule in disabled_rules:
        writer.writerow([
            "disabled_rule",
            rule["id"],
            rule["name"],
            rule["trigger_key"],
            "",
            "",
            "",
            "",
            rule["updated_at"] or "",
            "",
            "",
        ])

    for rule in rules_without_actions:
        writer.writerow([
            "rule_without_actions",
            rule["id"],
            rule["name"],
            rule["trigger_key"],
            "",
            "",
            "",
            rule["created_at"] or "",
            "",
            "",
            "",
        ])

    for event in recent_skipped_event_rows:
        writer.writerow([
            "skipped_event",
            event["id"],
            event["rule_name"] or "",
            event["trigger_key"],
            event["entity_type"] or "",
            event["entity_id"] or "",
            event["message"] or "",
            event["created_at"] or "",
            event["processed_at"] or "",
            event["retry_count"] or 0,
            event["last_retried_at"] or "",
        ])

    csv_data = output.getvalue()

    return Response(
        content=csv_data,
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": "attachment; filename=automation_diagnostics.csv"
        }
    )

@app.get("/automation/diagnostics", response_class=HTMLResponse)
async def automation_diagnostics_page(request: Request):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role not in ("boss", "manager"):
        return RedirectResponse("/", status_code=302)

    company_id = get_user_company_id(username)
    disabled_response = require_feature(company_id, "automation")

    if disabled_response:
        return disabled_response

    conn = connect()
    c = conn.cursor()

    disabled_rules = c.execute("""
    SELECT *
    FROM automation_rules
    WHERE company_id=?
      AND active=0
    ORDER BY updated_at DESC, id DESC
    LIMIT 10
    """, (company_id,)).fetchall()

    rules_without_actions = c.execute("""
    SELECT automation_rules.*
    FROM automation_rules
    LEFT JOIN automation_actions
      ON automation_actions.rule_id=automation_rules.id
      AND automation_actions.company_id=automation_rules.company_id
      AND automation_actions.active=1
    WHERE automation_rules.company_id=?
      AND automation_rules.active=1
    GROUP BY automation_rules.id
    HAVING COUNT(automation_actions.id)=0
    ORDER BY automation_rules.id DESC
    """, (company_id,)).fetchall()

    pending_events = c.execute("""
    SELECT COUNT(*)
    FROM automation_events
    WHERE company_id=?
      AND status='pending'
    """, (company_id,)).fetchone()[0]

    skipped_events = c.execute("""
    SELECT COUNT(*)
    FROM automation_events
    WHERE company_id=?
      AND status='skipped'
    """, (company_id,)).fetchone()[0]

    done_events = c.execute("""
    SELECT COUNT(*)
    FROM automation_events
    WHERE company_id=?
      AND status='done'
    """, (company_id,)).fetchone()[0]

    recent_skipped_event_rows = c.execute("""
    SELECT
        automation_events.*,
        automation_rules.name AS rule_name
    FROM automation_events
    LEFT JOIN automation_rules
      ON automation_rules.id=automation_events.rule_id
      AND automation_rules.company_id=automation_events.company_id
    WHERE automation_events.company_id=?
      AND automation_events.status='skipped'
    ORDER BY automation_events.id DESC
    LIMIT 10
    """, (company_id,)).fetchall()

    telegram_rules = c.execute("""
    SELECT COUNT(*)
    FROM automation_actions
    WHERE company_id=?
      AND action_key='telegram_alert'
      AND active=1
    """, (company_id,)).fetchone()[0]

    ai_digest_rules = c.execute("""
    SELECT COUNT(*)
    FROM automation_actions
    WHERE company_id=?
      AND action_key='ai_digest'
      AND active=1
    """, (company_id,)).fetchone()[0]

    success_rate = round(done_events / max(done_events + skipped_events, 1) * 100, 1)

    a3_system_health_score = 100

    if pending_events > 0:
        a3_system_health_score -= min(pending_events * 5, 25)

    if skipped_events > 0:
        a3_system_health_score -= min(skipped_events * 5, 30)

    if rules_without_actions:
        a3_system_health_score -= 20

    if disabled_rules:
        a3_system_health_score -= 10

    if success_rate < 80 and (done_events + skipped_events) > 0:
        a3_system_health_score -= 15

    a3_system_health_score = max(a3_system_health_score, 0)

    if a3_system_health_score >= 85:
        a3_system_health_level = "Отлично"
        a3_system_recommendation = "Система автоматизации работает стабильно."
    elif a3_system_health_score >= 60:
        a3_system_health_level = "Нужно внимание"
        a3_system_recommendation = "Проверьте пропущенные, ожидающие события и правила без действий."
    else:
        a3_system_health_level = "Проблема"
        a3_system_recommendation = "Нужно срочно проверить диагностику, правила и действия автоматизации."

    problems = []

    if pending_events > 5:
        problems.append({
            "title": "Много ожидающих событий",
            "reason": "Некоторые события долго не обрабатываются.",
            "action": "Проверьте последние события и повторите нужные вручную."
        })

    if skipped_events > done_events:
        problems.append({
            "title": "Много пропущенных событий",
            "reason": "Автоматизация чаще пропускает события, чем выполняет.",
            "action": "Проверьте правила без действий и последние пропущенные события."
        })

    if rules_without_actions:
        problems.append({
            "title": "Есть правила без действий",
            "reason": "Правило включено, но не имеет активного действия.",
            "action": "Откройте правило и добавьте действие: уведомление, Telegram или ИИ-сводку."
        })

    if success_rate < 80 and (done_events + skipped_events) > 0:
        problems.append({
            "title": "Низкая успешность автоматизации",
            "reason": "Процент выполненных событий ниже 80%.",
            "action": "Проверьте пропущенные события и настройки получателей."
        })

    if telegram_rules:
        problems.append({
            "title": "Проверьте Telegram-уведомления",
            "reason": "В системе есть правила автоматизации для Telegram.",
            "action": "Убедитесь, что BOT_TOKEN и telegram_chat_id настроены."
        })

    if ai_digest_rules:
        problems.append({
            "title": "Проверьте ИИ-сводки",
            "reason": "В системе есть автоматизация ИИ-сводок.",
            "action": "Проверьте, что ИИ-сводки появляются в уведомлениях и в журнале событий."
        })

    if not problems:
        problems.append({
            "title": "Критичных проблем не найдено",
            "reason": "Движок автоматизации работает стабильно.",
            "action": "Продолжайте мониторить события и успешность."
        })

    conn.close()

    recent_skipped_events = []
    for event_row in recent_skipped_event_rows:
        event = dict(event_row)
        event["retry_state"] = build_a3_event_retry_state(event)
        recent_skipped_events.append(event)

    return templates.TemplateResponse(
        request,
        "automation_diagnostics.html",
        {
            "request": request,
            "username": username,
            "role": role,
            "disabled_rules": disabled_rules,
            "rules_without_actions": rules_without_actions,
            "pending_events": pending_events,
            "skipped_events": skipped_events,
            "done_events": done_events,
            "recent_skipped_events": recent_skipped_events,
            "telegram_rules": telegram_rules,
            "ai_digest_rules": ai_digest_rules,
            "success_rate": success_rate,
            "a3_system_health_score": a3_system_health_score,
            "a3_system_health_level": a3_system_health_level,
            "a3_system_recommendation": a3_system_recommendation,
            "problems": problems,
            "trigger_labels": dict(AUTOMATION_TRIGGERS),
        }
    )

@app.get("/automation/events/{event_id}", response_class=HTMLResponse)
async def automation_event_detail(request: Request, event_id: int):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role not in ("boss", "manager"):
        return RedirectResponse("/", status_code=302)

    company_id = get_user_company_id(username)

    disabled_response = require_feature(company_id, "automation")

    if disabled_response:
        return disabled_response

    conn = connect()
    c = conn.cursor()

    event = c.execute("""
    SELECT
        automation_events.*,
        automation_rules.name AS rule_name
    FROM automation_events
    LEFT JOIN automation_rules
      ON automation_rules.id=automation_events.rule_id
      AND automation_rules.company_id=automation_events.company_id
    WHERE automation_events.id=?
      AND automation_events.company_id=?
    """, (event_id, company_id)).fetchone()

    conn.close()

    if not event:
        return RedirectResponse("/automation", status_code=302)

    event = dict(event)
    event["retry_state"] = build_a3_event_retry_state(event)

    trigger_labels = dict(AUTOMATION_TRIGGERS)

    status_labels = AUTOMATION_STATUS_LABELS

    entity_labels = {
        "task": "Заявка",
        "client": "Клиент",
        "company": "Компания"
    }

    return templates.TemplateResponse(
        request,
        "automation_event_detail.html",
        {
            "request": request,
            "username": username,
            "role": role,
            "event": event,
            "trigger_labels": trigger_labels,
            "status_labels": status_labels,
            "entity_labels": entity_labels
        }
    )

@app.post("/automation/events/{event_id}/retry")
async def retry_automation_event(request: Request, event_id: int):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role != "boss":
        return RedirectResponse("/", status_code=302)

    company_id = get_user_company_id(username)
    disabled_response = require_feature(company_id, "automation")

    if disabled_response:
        return disabled_response

    conn = connect()
    c = conn.cursor()
    retry_cutoff = (
        datetime.now() - timedelta(
            minutes=SKIPPED_EVENT_RETRY_COOLDOWN_MINUTES,
        )
    ).isoformat(timespec="seconds")

    event = c.execute("""
    SELECT *
    FROM automation_events
    WHERE id=?
      AND company_id=?
      AND status IN ('pending', 'skipped')
      AND (
        last_retried_at IS NULL
        OR last_retried_at < ?
      )
    """, (
        event_id,
        company_id,
        retry_cutoff,
    )).fetchone()

    conn.close()

    if not event:
        return RedirectResponse("/automation?retry_unavailable=1", status_code=302)

    if event["rule_id"]:
        replay_result = replay_a3_skipped_automation_events(
            company_id=company_id,
            rule_id=event["rule_id"],
            events=[dict(event)],
        )

        return RedirectResponse(
            (
                "/automation?retry_skipped=1"
                f"&retried={replay_result.get('replayed', 0)}"
                f"&not_ready={replay_result.get('not_ready', 0)}"
                f"&failed={replay_result.get('failed', 0)}"
            ),
            status_code=302,
        )

    return RedirectResponse("/automation?retry_unavailable=1", status_code=302)





@app.post("/automation/rules/{rule_id}/actions/create")
async def create_rule_action(request: Request, rule_id: int):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role not in ("boss", "manager"):
        return RedirectResponse("/", status_code=302)

    company_id = get_user_company_id(username)

    disabled_response = require_feature(company_id, "automation")

    if disabled_response:
        return disabled_response

    form = await request.form()

    action_key = str(form.get("action_key") or "").strip()
    target_username = str(form.get("target_username") or "").strip()
    message = str(form.get("message") or "").strip()
    task_delay_days, task_priority, task_deadline_hours = (
        automation_create_task_settings({
            "task_delay_days": form.get("task_delay_days"),
            "task_priority": form.get("task_priority"),
            "task_deadline_hours": form.get("task_deadline_hours"),
        })
    )
    task_max_daily_load = automation_task_max_daily_load({
        "task_max_daily_load": form.get("task_max_daily_load"),
    })
    task_capacity_fallback_days = automation_task_capacity_fallback_days({
        "task_capacity_fallback_days": form.get(
            "task_capacity_fallback_days"
        ),
    })
    task_business_days_only = automation_task_business_days_only({
        "task_business_days_only": form.get("task_business_days_only"),
    })

    action_keys = {key for key, _ in AUTOMATION_ACTIONS}

    if action_key not in action_keys:
        return RedirectResponse(
            f"/automation/rules/{rule_id}?action_error=1",
            status_code=302
        )

    conn = connect()
    c = conn.cursor()

    rule = c.execute("""
    SELECT *
    FROM automation_rules
    WHERE id=?
      AND company_id=?
    """, (rule_id, company_id)).fetchone()

    if not rule:
        conn.close()
        return RedirectResponse("/automation", status_code=302)

    if not automation_action_target_is_valid(
        c,
        company_id,
        action_key,
        target_username,
    ):
        conn.close()
        return RedirectResponse(
            f"/automation/rules/{rule_id}?action_target_error=1",
            status_code=302
        )

    if action_key in ("notification", "telegram_alert") and not message:
        message = f"Автоматизация: {rule['name']}"

    if action_key == "ai_digest" and not target_username:
        target_username = username

    if action_key == "ai_digest" and not message:
        message = "ИИ-сводка по бизнесу"

    if action_key == "create_task" and not message:
        message = f"Автоматическая задача: {rule['name']}"

    payload = {
        "target_username": target_username,
        "message": message
    }

    if action_key == "email":
        payload["subject"] = f"Автоматизация: {rule['name']}"
    elif action_key == "create_task":
        payload["task_delay_days"] = task_delay_days
        payload["task_priority"] = task_priority
        payload["task_deadline_hours"] = task_deadline_hours
        payload["task_max_daily_load"] = task_max_daily_load
        payload["task_capacity_fallback_days"] = (
            task_capacity_fallback_days
        )
        payload["task_business_days_only"] = task_business_days_only

    c.execute("""
    INSERT INTO automation_actions (
        company_id,
        rule_id,
        action_key,
        payload_json,
        active,
        created_at
    )
    VALUES (?, ?, ?, ?, 1, ?)
    """, (
        company_id,
        rule_id,
        action_key,
        json.dumps(payload, ensure_ascii=False),
        datetime.now().strftime("%Y-%m-%d %H:%M")
    ))

    conn.commit()
    conn.close()

    return RedirectResponse(
        f"/automation/rules/{rule_id}?action_created=1",
        status_code=302
    )


@app.post("/automation/actions/{action_id}/toggle")
async def toggle_automation_action(request: Request, action_id: int):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role not in ("boss", "manager"):
        return RedirectResponse("/", status_code=302)

    company_id = get_user_company_id(username)

    disabled_response = require_feature(company_id, "automation")

    if disabled_response:
        return disabled_response

    conn = connect()
    c = conn.cursor()

    action = c.execute("""
    SELECT *
    FROM automation_actions
    WHERE id=?
      AND company_id=?
    """, (action_id, company_id)).fetchone()

    if not action:
        conn.close()
        return RedirectResponse("/automation", status_code=302)

    new_active = 0 if action["active"] else 1

    c.execute("""
    UPDATE automation_actions
    SET active=?
    WHERE id=?
      AND company_id=?
    """, (
        new_active,
        action_id,
        company_id
    ))

    conn.commit()
    conn.close()

    return RedirectResponse(
        f"/automation/rules/{action['rule_id']}?action_updated=1",
        status_code=302
    )


@app.post("/automation/actions/{action_id}/delete")
async def delete_automation_action(request: Request, action_id: int):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role not in ("boss", "manager"):
        return RedirectResponse("/", status_code=302)

    company_id = get_user_company_id(username)

    disabled_response = require_feature(company_id, "automation")

    if disabled_response:
        return disabled_response

    conn = connect()
    c = conn.cursor()

    action = c.execute("""
    SELECT *
    FROM automation_actions
    WHERE id=?
      AND company_id=?
    """, (action_id, company_id)).fetchone()

    if not action:
        conn.close()
        return RedirectResponse("/automation", status_code=302)

    rule_id = action["rule_id"]

    c.execute("""
    DELETE FROM automation_actions
    WHERE id=?
      AND company_id=?
    """, (
        action_id,
        company_id
    ))

    conn.commit()
    conn.close()

    return RedirectResponse(
        f"/automation/rules/{rule_id}?action_deleted=1",
        status_code=302
    )

@app.post("/automation/rules/{rule_id}/retry-skipped")
async def retry_rule_skipped_events(request: Request, rule_id: int):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role != "boss":
        return RedirectResponse("/", status_code=302)

    company_id = get_user_company_id(username)
    disabled_response = require_feature(company_id, "automation")

    if disabled_response:
        return disabled_response

    conn = connect()
    c = conn.cursor()
    retry_cutoff = (
        datetime.now() - timedelta(
            minutes=SKIPPED_EVENT_RETRY_COOLDOWN_MINUTES,
        )
    ).isoformat(timespec="seconds")

    events = c.execute("""
    SELECT id, rule_id, trigger_key, entity_type, entity_id, message
    FROM automation_events
    WHERE company_id=?
      AND rule_id=?
      AND status='skipped'
      AND (
        last_retried_at IS NULL
        OR last_retried_at < ?
      )
    ORDER BY id DESC
    LIMIT 10
    """, (
        company_id,
        rule_id,
        retry_cutoff,
    )).fetchall()

    conn.close()

    replay_result = replay_a3_skipped_automation_events(
        company_id=company_id,
        rule_id=rule_id,
        events=[dict(event) for event in events],
    )
    retried = replay_result.get("replayed", 0)
    not_ready = replay_result.get("not_ready", 0)
    failed = replay_result.get("failed", 0)

    try:
        create_ops_timeline_event(
            company_id=company_id,
            event_type="autonomous_retry",
            severity="warning" if failed else "info",
            title="Ручной повтор событий правила",
            message=(
                f"Правило #{rule_id}. "
                f"Повторно выполнено: {retried}; "
                f"условия ещё не готовы: {not_ready}; "
                f"ошибок: {failed}"
            ),
            source="manual",
            target_type="automation_rule",
            target_id=rule_id,
            cooldown_minutes=5,
        )
    except Exception:
        pass

    return RedirectResponse(
        (
            f"/automation/rules/{rule_id}?retry_skipped=1"
            f"&retried={retried}"
            f"&not_ready={not_ready}"
            f"&failed={failed}"
        ),
        status_code=302
    )

@app.post("/automation/rules/{rule_id}/run")
async def run_automation_rule_now(request: Request, rule_id: int):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role not in ("boss", "manager"):
        return RedirectResponse("/", status_code=302)

    company_id = get_user_company_id(username)
    disabled_response = require_feature(company_id, "automation")

    if disabled_response:
        return disabled_response

    conn = connect()
    c = conn.cursor()

    rule = c.execute("""
    SELECT *
    FROM automation_rules
    WHERE id=?
      AND company_id=?
      AND active=1
    """, (rule_id, company_id)).fetchone()

    conn.close()

    if not rule:
        return RedirectResponse("/automation?run_skipped=1", status_code=302)

    created_events = run_automation_event(
        company_id,
        rule["trigger_key"],
        "company",
        company_id,
        f"Ручной запуск правила: {rule['name']}",
        "/automation"
    )

    if created_events:
        return RedirectResponse("/automation?run=1", status_code=302)

    return RedirectResponse("/automation?run_skipped=1", status_code=302)

@app.post("/automation/rules/{rule_id}/toggle")
async def toggle_automation_rule(request: Request, rule_id: int):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role not in ("boss", "manager"):
        return RedirectResponse("/", status_code=302)

    company_id = get_user_company_id(username)
    disabled_response = require_feature(company_id, "automation")

    if disabled_response:
        return disabled_response

    conn = connect()
    c = conn.cursor()

    rule = c.execute("""
    SELECT active
    FROM automation_rules
    WHERE id=?
      AND company_id=?
    """, (rule_id, company_id)).fetchone()

    if not rule:
        conn.close()
        return RedirectResponse("/automation", status_code=302)

    new_active = 0 if rule["active"] else 1

    c.execute("""
    UPDATE automation_rules
    SET active=?, updated_at=?
    WHERE id=?
      AND company_id=?
    """, (
        new_active,
        datetime.now().strftime("%Y-%m-%d %H:%M"),
        rule_id,
        company_id
    ))

    conn.commit()
    conn.close()

    return RedirectResponse("/automation?toggled=1", status_code=302)


@app.post("/automation/rules/{rule_id}/enable")
async def enable_automation_rule(request: Request, rule_id: int):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role not in ("boss", "manager"):
        return RedirectResponse("/", status_code=302)

    company_id = get_user_company_id(username)
    disabled_response = require_feature(company_id, "automation")

    if disabled_response:
        return disabled_response

    conn = connect()
    c = conn.cursor()

    rule = c.execute("""
    SELECT id
    FROM automation_rules
    WHERE id=?
      AND company_id=?
    """, (rule_id, company_id)).fetchone()

    if not rule:
        conn.close()
        return RedirectResponse("/automation", status_code=302)

    c.execute("""
    UPDATE automation_rules
    SET active=1, updated_at=?
    WHERE id=?
      AND company_id=?
    """, (
        datetime.now().strftime("%Y-%m-%d %H:%M"),
        rule_id,
        company_id
    ))

    conn.commit()
    conn.close()

    return RedirectResponse("/automation?enabled=1", status_code=302)


@app.post("/automation/rules/{rule_id}/delete")
async def delete_automation_rule(request: Request, rule_id: int):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role not in ("boss", "manager"):
        return RedirectResponse("/", status_code=302)

    company_id = get_user_company_id(username)
    disabled_response = require_feature(company_id, "automation")

    if disabled_response:
        return disabled_response

    conn = connect()
    c = conn.cursor()

    rule = c.execute("""
    SELECT id
    FROM automation_rules
    WHERE id=?
      AND company_id=?
    """, (rule_id, company_id)).fetchone()

    if not rule:
        conn.close()
        return RedirectResponse("/automation", status_code=302)

    c.execute("""
    DELETE FROM automation_actions
    WHERE rule_id=?
      AND company_id=?
    """, (rule_id, company_id))

    c.execute("""
    DELETE FROM automation_rules
    WHERE id=?
      AND company_id=?
    """, (rule_id, company_id))

    conn.commit()
    conn.close()

    return RedirectResponse("/automation?deleted=1", status_code=302)


@app.get("/admin/roadmap", response_class=HTMLResponse)
async def admin_roadmap_page(request: Request):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role != "superadmin":
        return RedirectResponse("/", status_code=302)

    return templates.TemplateResponse(
        request,
        "admin_roadmap.html",
        {
            "request": request,
            "username": username,
            "role": role,
            "links": build_admin_links(),
        }
    )


@app.get("/admin/checklist", response_class=HTMLResponse)
async def admin_checklist_page(request: Request):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role != "superadmin":
        return RedirectResponse("/", status_code=302)

    return templates.TemplateResponse(
        request,
        "admin_checklist.html",
        {
            "request": request,
            "username": username,
            "role": role,
            "links": build_admin_links(),
        }
    )


def build_admin_links():
    return {
        "home": "/",
        "admin": "/admin",
        "debug": "/debug",
        "system": "/system",
        "backup": "/backup",
        "billing": "/billing",
        "integration_1c": "/integrations/1c",
        "workers": "/workers",
        "settings": "/settings",
        "checklist": "/admin/checklist",
        "roadmap": "/admin/roadmap",
        "notes": "/admin/notes",
        "health": "/health",
        "ready": "/ready",
        "clients": "/clients",
        "finance": "/finance",
        "calls": "/calls",
    }


@app.get("/admin", response_class=HTMLResponse)
async def admin_page(request: Request):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role not in ("boss", "superadmin"):
        return RedirectResponse("/", status_code=302)

    return templates.TemplateResponse(
        request,
        "admin.html",
        {
            "request": request,
            "username": username,
            "role": role,
            "links": build_admin_links(),
        }
    )


def clean_build_metadata_value(value, fallback="не задан", max_length=120):
    text = str(value or "").strip()
    return text[:max_length] if text else fallback


def get_build_metadata():
    commit_full = clean_build_metadata_value(
        os.getenv("RAILWAY_GIT_COMMIT_SHA")
        or os.getenv("GIT_COMMIT")
        or os.getenv("SOURCE_VERSION"),
        "",
        80,
    )
    commit = commit_full[:12] if commit_full else "не задан"
    railway_enabled = bool((os.getenv("RAILWAY_ENVIRONMENT") or "").strip())
    environment = clean_build_metadata_value(
        os.getenv("RAILWAY_ENVIRONMENT_NAME")
        or os.getenv("ENV")
        or ("railway" if railway_enabled else "local"),
        "local",
        80,
    )

    return {
        "version": APP_VERSION,
        "commit": commit,
        "branch": clean_build_metadata_value(
            os.getenv("RAILWAY_GIT_BRANCH")
            or os.getenv("GIT_BRANCH"),
            max_length=80,
        ),
        "deployment_id": clean_build_metadata_value(
            os.getenv("RAILWAY_DEPLOYMENT_ID"),
            max_length=80,
        ),
        "service_name": clean_build_metadata_value(
            os.getenv("RAILWAY_SERVICE_NAME"),
            max_length=80,
        ),
        "environment": environment,
        "railway": railway_enabled,
    }


def get_public_build_metadata():
    build = get_build_metadata()

    return {
        "version": build["version"],
        "commit": build["commit"],
    }


def build_system_links():
    return {
        "admin": "/admin",
        "readiness": build_platform_readiness_links()["page"],
        "export": "/system/export",
        "events_export": "/system/events/export",
        "errors_export": "/system/errors/export",
        "backup": "/backup",
        "debug": "/debug",
    }


def build_system_diagnostics(role=""):
    uploads_path = UPLOAD_DIR
    production_config = get_production_config_status()
    object_storage_status = production_config["object_storage_status"]
    uploads_exists = object_storage_status["ok"]
    uploads_files = (
        len([f for f in uploads_path.rglob("*") if f.is_file()])
        if uploads_path.exists()
        else 0
    )
    uploads_path_label = (
        "S3-совместимое хранилище"
        if object_storage_status["backend"] == "s3"
        else str(uploads_path)
    )
    database_runtime = production_config["database_runtime"]
    env_name = production_config["environment"]
    railway_environment = production_config["railway_environment"]
    default_secret = production_config["secret_is_weak"]
    telegram_configured = production_config["telegram_configured"]
    cron_secret_configured = (
        production_config["automation_cron_secret_configured"]
    )
    backup_status = get_backup_status()
    background_queue_status = get_background_queue_status()
    db_exists = backup_status["db_exists"]
    db_size = backup_status["db_size"]
    db_path_label = backup_status["db_path"]
    public_health_status = get_public_health_status()
    public_readiness_status = get_public_readiness_status()
    build_metadata = get_build_metadata()
    system_event_summary = get_recent_system_event_summary()
    error_monitoring = get_error_monitoring_overview(
        limit=30 if role == "superadmin" else 1,
    )
    if role != "superadmin":
        error_monitoring["incidents"] = []
    system_generated_at = datetime.now().strftime("%Y-%m-%d %H:%M")
    system_links = build_system_links()

    system_checks = [
        make_system_check(
            "app_runtime",
            "Приложение",
            "ok",
            APP_VERSION,
            "FastAPI приложение отвечает и отдаёт системную страницу.",
            "Продолжайте контролировать релизные проверки.",
            "/platform/readiness",
        ),
        make_system_check(
            "database_backend",
            "Backend базы",
            (
                "critical"
                if not database_runtime["configuration_valid"]
                or (
                    production_config["production_mode"]
                    and database_runtime["active_backend"] != "postgresql"
                )
                else (
                    "ok"
                    if database_runtime["active_backend"] == "postgresql"
                    else "warning"
                )
            ),
            database_runtime["active_backend_label"],
            (
                "Приложение работает на PostgreSQL."
                if database_runtime["active_backend"] == "postgresql"
                else "Приложение работает на SQLite."
            ),
            "Для production используйте проверенный PostgreSQL backend.",
            "/platform/readiness",
        ),
        make_system_check(
            "database",
            "База данных",
            "ok" if db_exists else "critical",
            format_file_size(db_size) if db_exists else "недоступна",
            (
                f"{backup_status['backend_label']} база доступна."
                if db_exists
                else f"{backup_status['backend_label']} база недоступна."
            ),
            "Проверьте подключение к базе данных и запуск init_db.",
            "/debug",
        ),
        make_system_check(
            "uploads",
            "Загруженные файлы",
            object_storage_status["status"],
            object_storage_status["backend_label"],
            object_storage_status["message"],
            "Проверьте backend, bucket и права файлового хранилища.",
            "/debug",
        ),
        make_system_check(
            "deploy_readiness",
            "Готовность деплоя",
            public_readiness_status["status"],
            public_readiness_status["status_label"],
            (
                "Публичный /ready проверяет подключение, ключевые таблицы "
                "и доступность uploads."
            ),
            (
                "Подключите /health и /ready к Railway или внешнему "
                "мониторингу."
            ),
            "/ready",
        ),
        make_system_check(
            "secret_key",
            "Секрет приложения",
            "critical" if default_secret else "ok",
            "dev" if default_secret else "настроен",
            (
                "SECRET_KEY отсутствует или короче 32 символов."
                if default_secret
                else "SECRET_KEY задан через окружение."
            ),
            "Перед боевым запуском задайте SECRET_KEY длиной от 32 символов.",
            "/platform/readiness",
        ),
        make_system_check(
            "secure_cookie",
            "Защита cookie",
            "ok" if COOKIE_SECURE else "warning",
            "включена" if COOKIE_SECURE else "выключена",
            (
                "Cookie сессии отправляются только по HTTPS."
                if COOKIE_SECURE
                else "В текущем окружении защита cookie не включена."
            ),
            "Для боевого режима включите COOKIE_SECURE или Railway окружение.",
            "/platform/readiness",
        ),
        make_system_check(
            "telegram",
            "Telegram",
            "ok" if telegram_configured else "warning",
            "настроен" if telegram_configured else "не полностью",
            (
                "BOT_TOKEN и CHAT_ID настроены."
                if telegram_configured
                else "BOT_TOKEN или CHAT_ID не настроены."
            ),
            "Добавьте Telegram переменные окружения.",
            "/debug",
        ),
        make_system_check(
            "automation_cron_secret",
            "Фоновые запуски",
            "ok" if cron_secret_configured else "warning",
            "секрет задан" if cron_secret_configured else "секрет не задан",
            (
                "Фоновые автоматизации защищены отдельным секретом."
                if cron_secret_configured
                else "Секрет фоновых запусков не настроен."
            ),
            "Укажите AUTOMATION_CRON_SECRET для расписаний и дайджестов.",
            "/platform/readiness",
        ),
        make_system_check(
            "background_jobs",
            "Фоновая очередь",
            background_queue_status["status"],
            (
                f"{background_queue_status['pending']} ожидают / "
                f"{background_queue_status['running']} выполняются"
            ),
            background_queue_status["message"],
            (
                "Запускайте worker или cron endpoint фоновой очереди "
                "не реже одного раза в минуту."
            ),
            "/api/platform/background-jobs",
        ),
        make_system_check(
            "runtime_errors",
            "Ошибки приложения",
            error_monitoring["status"],
            (
                f"{error_monitoring['summary']['open']} открыто / "
                f"{error_monitoring['summary']['repeated']} повторяются"
            ),
            (
                "Открытых ошибок приложения нет."
                if not error_monitoring["summary"]["open"]
                else (
                    "Одинаковые ошибки объединены по типу и маршруту. "
                    "Проверьте ответственного и статус устранения."
                )
            ),
            "Разберите активные инциденты в журнале ошибок приложения.",
            "/system#error-incidents",
        ),
        make_system_check(
            "http_observability",
            "HTTP-запросы",
            (
                "critical"
                if system_event_summary["http_critical_count"]
                else (
                    "warning"
                    if (
                        system_event_summary["http_warning_count"]
                        or system_event_summary["slow_request_count"]
                    )
                    else "ok"
                )
            ),
            (
                f"{system_event_summary['http_request_count']} событий"
                " / "
                f"{system_event_summary['slow_request_count']} медленных"
            ),
            (
                "За последние 24 часа HTTP-проблем не было."
                if not system_event_summary["http_request_count"]
                else (
                    "За последние 24 часа есть HTTP-ошибки или "
                    "медленные ответы."
                )
            ),
            (
                "Проверьте request_id, путь, статус и время ответа "
                "в журнале системы."
            ),
            "/system",
        ),
        make_system_check(
            "backups",
            "Резервные копии",
            backup_status["status"],
            backup_status["status_label"],
            backup_status["summary"],
            backup_status["action"],
            "/backup",
        ),
        make_system_check(
            "backup_restore_check",
            "Проверка восстановления",
            backup_status["restore_check"]["status"],
            backup_status["restore_check"]["status_label"],
            backup_status["restore_check"]["message"],
            "Запустите проверку восстановления последней копии.",
            "/backup",
        ),
    ]
    status_points = {
        "ok": 1,
        "warning": 0.5,
        "critical": 0,
    }
    system_score = round(
        sum(status_points[item["status"]] for item in system_checks)
        * 100
        / (len(system_checks) or 1)
    )
    critical_count = sum(
        1 for item in system_checks if item["status"] == "critical"
    )
    warning_count = sum(
        1 for item in system_checks if item["status"] == "warning"
    )

    if critical_count:
        system_status = "critical"
        system_status_label = "Критично"
    elif warning_count:
        system_status = "warning"
        system_status_label = "Есть предупреждения"
    else:
        system_status = "ok"
        system_status_label = "Стабильно"

    deployment_endpoints = [
        {
            "title": "Живость",
            "url": "/health",
            "access_label": "публичный",
            "status": public_health_status["status"],
            "status_label": public_health_status["status_label"],
            "summary": "Быстрая проверка, что приложение и база отвечают.",
            "method": "GET",
        },
        {
            "title": "Готовность",
            "url": "/ready",
            "access_label": "публичный",
            "status": public_readiness_status["status"],
            "status_label": public_readiness_status["status_label"],
            "summary": (
                "Готовность к трафику: база, таблицы и uploads."
            ),
            "method": "GET",
        },
        {
            "title": "Система",
            "url": "/system",
            "access_label": "только админ",
            "status": system_status,
            "status_label": system_status_label,
            "summary": "Техническая диагностика, события, backup и окружение.",
            "method": "GET",
        },
        {
            "title": "Готовность релиза",
            "url": "/platform/readiness",
            "access_label": "superadmin",
            "status": "ok" if system_status != "critical" else "critical",
            "status_label": (
                "Проверить"
                if system_status != "critical"
                else "Есть блокеры"
            ),
            "summary": "Контроль релиза, runbook, signoff и снимки готовности.",
            "method": "GET",
        },
        {
            "title": "Напоминания по счетам",
            "url": "/automation/cron/platform-billing-reminders",
            "access_label": "cron secret",
            "status": "ok" if cron_secret_configured else "warning",
            "status_label": (
                "готово" if cron_secret_configured else "нужен секрет"
            ),
            "summary": (
                "Плановый запуск уведомлений владельцам компаний "
                "по выставленным и просроченным счетам платформы."
            ),
            "method": "POST",
        },
        {
            "title": "Фоновая очередь",
            "url": "/automation/cron/background-jobs",
            "access_label": "cron secret",
            "status": background_queue_status["status"],
            "status_label": background_queue_status["status_label"],
            "summary": background_queue_status["message"],
            "method": "POST",
        },
        {
            "title": "Резервные копии",
            "url": "/backup",
            "access_label": "superadmin",
            "status": backup_status["status"],
            "status_label": backup_status["status_label"],
            "summary": "Резервные копии и проверка восстановления.",
            "method": "GET",
        },
    ]

    system_events = get_system_event_history() if role == "superadmin" else []
    system_event_retention = (
        get_system_event_retention_status()
        if role == "superadmin"
        else {}
    )

    return {
        "db_exists": db_exists,
        "db_size": db_size,
        "db_size_label": format_file_size(db_size),
        "db_path": db_path_label,
        "database_runtime": database_runtime,
        "data_dir": str(DATA_DIR),
        "uploads_exists": uploads_exists,
        "uploads_files": uploads_files,
        "uploads_path": uploads_path_label,
        "object_storage_status": object_storage_status,
        "app_version": APP_VERSION,
        "build_metadata": build_metadata,
        "env_name": env_name,
        "railway_environment": railway_environment,
        "cookie_secure": COOKIE_SECURE,
        "secret_is_default": default_secret,
        "telegram_configured": telegram_configured,
        "production_config": production_config,
        "public_health_status": public_health_status,
        "public_readiness_status": public_readiness_status,
        "deployment_endpoints": deployment_endpoints,
        "backup_status": backup_status,
        "background_queue_status": background_queue_status,
        "system_event_summary": system_event_summary,
        "error_monitoring": error_monitoring,
        "system_checks": system_checks,
        "system_score": system_score,
        "system_status": system_status,
        "system_status_label": system_status_label,
        "system_warning_count": warning_count,
        "system_critical_count": critical_count,
        "system_generated_at": system_generated_at,
        "system_events": system_events,
        "system_event_retention": system_event_retention,
        "system_links": system_links,
        "superadmin_only_urls": [
            system_links["debug"],
            system_links["readiness"],
            system_links["backup"],
        ],
    }


def get_public_health_status():
    database_runtime = get_database_runtime_config()
    database_ok = False
    database_error = ""
    conn = None

    try:
        conn = connect()
        conn.execute("SELECT 1").fetchone()
        database_ok = True
    except get_database_error_types() as error:
        database_error = error.__class__.__name__
    finally:
        if conn:
            conn.close()

    status = "ok" if database_ok else "critical"

    return {
        "ok": database_ok,
        "app": "field-service-crm",
        "version": APP_VERSION,
        "build": get_public_build_metadata(),
        "status": status,
        "status_label": "Работает" if database_ok else "Проблема",
        "database": {
            "ok": database_ok,
            "backend": database_runtime["active_backend"],
            "status": status,
            "status_label": "Доступна" if database_ok else "Недоступна",
            "error": database_error,
        },
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
    }


def get_public_readiness_status():
    database_runtime = get_database_runtime_config()
    object_storage_status = get_object_storage_status(UPLOAD_DIR)
    conn = None
    database_ok = False
    quick_check_ok = False
    quick_check = ""
    backend_check_key = "sqlite_quick_check"
    backend_check_label = "Проверка не пройдена"
    database_error = ""
    missing_tables = list(BACKUP_REQUIRED_TABLES)
    uploads_ok = object_storage_status["ok"]

    try:
        conn = connect()
        conn.execute("SELECT 1").fetchone()
        database_ok = True
        if database_runtime["active_backend"] == "postgresql":
            quick_check = "connected"
            quick_check_ok = True
            backend_check_key = "postgresql_connection_check"
            backend_check_label = "Подключение работает"
            table_rows = conn.execute("""
                SELECT table_name AS name
                FROM information_schema.tables
                WHERE table_schema=CURRENT_SCHEMA()
            """).fetchall()
        else:
            quick_check_row = conn.execute("PRAGMA quick_check").fetchone()
            quick_check = quick_check_row[0] if quick_check_row else ""
            quick_check_ok = quick_check == "ok"
            backend_check_label = (
                "Проверка пройдена"
                if quick_check_ok
                else "Проверка не пройдена"
            )
            table_rows = conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        tables = {row["name"] for row in table_rows}
        missing_tables = [
            table
            for table in BACKUP_REQUIRED_TABLES
            if table not in tables
        ]
    except get_database_error_types() as error:
        database_error = error.__class__.__name__
    finally:
        if conn:
            conn.close()

    tables_ok = database_ok and not missing_tables
    backend_release_supported = (
        database_runtime["active_backend"] != "postgresql"
        or database_runtime["postgresql_ready"]
    )
    ready = (
        database_runtime["configuration_valid"]
        and database_ok
        and quick_check_ok
        and tables_ok
        and backend_release_supported
        and uploads_ok
    )
    checks = [
        {
            "key": "database_configuration",
            "ok": database_runtime["configuration_valid"],
            "status": (
                "ok"
                if database_runtime["configuration_valid"]
                else "critical"
            ),
            "status_label": (
                database_runtime["active_backend_label"]
                if database_runtime["configuration_valid"]
                else "Ошибка конфигурации"
            ),
        },
        {
            "key": "database",
            "ok": database_ok,
            "status": "ok" if database_ok else "critical",
            "status_label": "Доступна" if database_ok else "Недоступна",
            "error": database_error,
            "backend": database_runtime["active_backend"],
        },
        {
            "key": backend_check_key,
            "ok": quick_check_ok,
            "status": "ok" if quick_check_ok else "critical",
            "status_label": backend_check_label,
            "value": quick_check,
        },
        {
            "key": "required_tables",
            "ok": tables_ok,
            "status": "ok" if tables_ok else "critical",
            "status_label": (
                "Таблицы на месте"
                if tables_ok
                else "Не хватает таблиц"
            ),
            "required": list(BACKUP_REQUIRED_TABLES),
            "missing": missing_tables,
        },
        {
            "key": "database_release_support",
            "ok": backend_release_supported,
            "status": "ok" if backend_release_supported else "critical",
            "status_label": (
                "Поддерживается для релиза"
                if backend_release_supported
                else "Экспериментальный режим"
            ),
        },
        {
            "key": "uploads",
            "ok": uploads_ok,
            "status": "ok" if uploads_ok else "critical",
            "status_label": (
                object_storage_status["backend_label"]
                if uploads_ok
                else "Недоступно"
            ),
            "backend": object_storage_status["backend"],
        },
    ]

    return {
        "ok": ready,
        "app": "field-service-crm",
        "version": APP_VERSION,
        "build": get_public_build_metadata(),
        "status": "ok" if ready else "critical",
        "status_label": "Готово" if ready else "Не готово",
        "checks": checks,
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
    }


@app.get("/health")
async def public_health():
    health = get_public_health_status()

    return JSONResponse(
        health,
        status_code=200 if health["ok"] else 503,
    )


@app.get("/ready")
async def public_ready():
    readiness = get_public_readiness_status()

    return JSONResponse(
        readiness,
        status_code=200 if readiness["ok"] else 503,
    )


@app.get("/system", response_class=HTMLResponse)
async def system_page(
    request: Request,
    notice: str = "",
    deleted: int = 0,
    incident: int = 0,
):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role not in ("boss", "superadmin"):
        return RedirectResponse("/", status_code=302)

    context = {
        "request": request,
        "username": username,
        "role": role,
        "notice": notice,
        "deleted": deleted,
        "incident": incident,
    }
    context.update(build_system_diagnostics(role))

    return templates.TemplateResponse(
        request,
        "system.html",
        context,
    )


@app.get("/system/export")
async def system_export(request: Request):
    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role != "superadmin":
        return RedirectResponse("/", status_code=302)

    diagnostics = build_system_diagnostics(role)
    production_config = diagnostics["production_config"]
    backup_status = diagnostics["backup_status"]
    event_summary = diagnostics["system_event_summary"]
    error_monitoring = diagnostics["error_monitoring"]

    output = io.StringIO()
    writer = csv.writer(output)

    writer.writerow(["Системный отчёт"])
    writer.writerow(["Сгенерировано", diagnostics["system_generated_at"]])
    writer.writerow(["Версия приложения", diagnostics["app_version"]])
    writer.writerow(["Коммит", diagnostics["build_metadata"]["commit"]])
    writer.writerow(["Ветка", diagnostics["build_metadata"]["branch"]])
    writer.writerow(["Сервис", diagnostics["build_metadata"]["service_name"]])
    writer.writerow([
        "Деплой",
        diagnostics["build_metadata"]["deployment_id"],
    ])
    writer.writerow(["Окружение", diagnostics["env_name"]])
    writer.writerow(["Статус", diagnostics["system_status_label"]])
    writer.writerow(["Оценка", diagnostics["system_score"]])
    writer.writerow(["Предупреждений", diagnostics["system_warning_count"]])
    writer.writerow(["Критичных проблем", diagnostics["system_critical_count"]])
    writer.writerow([])

    writer.writerow(["Конфигурация окружения"])
    writer.writerow(["Статус", production_config["status_label"]])
    writer.writerow(["Резюме", production_config["summary"]])
    writer.writerow(["Проверка", "Статус", "Значение", "Описание", "Действие"])
    for item in production_config["items"]:
        writer.writerow([
            item["title"],
            item["status_label"],
            item["value"],
            item["description"],
            item["action"],
        ])
    writer.writerow([])

    writer.writerow(["Проверки системы"])
    writer.writerow(["Проверка", "Статус", "Значение", "Описание", "Действие"])
    for check in diagnostics["system_checks"]:
        writer.writerow([
            check["title"],
            check["status_label"],
            check["value"],
            check["description"],
            check["action"],
        ])
    writer.writerow([])

    writer.writerow(["Контроль деплоя"])
    writer.writerow([
        "Проверка",
        "URL",
        "Доступ",
        "Статус",
        "Описание",
    ])
    for endpoint in diagnostics["deployment_endpoints"]:
        writer.writerow([
            endpoint["title"],
            endpoint["url"],
            endpoint["access_label"],
            endpoint["status_label"],
            endpoint["summary"],
        ])
    writer.writerow([])

    writer.writerow(["Пути и файлы"])
    writer.writerow(["DATA_DIR", diagnostics["data_dir"]])
    writer.writerow([
        "База данных",
        diagnostics["db_path"],
        diagnostics["db_size_label"],
    ])
    writer.writerow([
        "Uploads",
        diagnostics["uploads_path"],
        f"{diagnostics['uploads_files']} файлов",
    ])
    writer.writerow([
        "Backups",
        backup_status["backup_path"],
        backup_status["total_size_label"],
    ])
    writer.writerow([])

    writer.writerow(["Резервные копии"])
    writer.writerow(["Статус", backup_status["status_label"]])
    writer.writerow(["Резюме", backup_status["summary"]])
    writer.writerow(["Действие", backup_status["action"]])
    writer.writerow(["Копий", backup_status["count"]])
    writer.writerow(["Последняя копия", backup_status["latest_name"]])
    writer.writerow(["Возраст последней", backup_status["latest_age_label"]])
    writer.writerow([
        "Проверка восстановления",
        backup_status["restore_check"]["status_label"],
        backup_status["restore_check"]["message"],
    ])
    writer.writerow([])

    writer.writerow(["Ошибки за 24 часа"])
    writer.writerow(["Критичных", event_summary["critical_count"]])
    writer.writerow(["Ошибок приложения", event_summary["runtime_error_count"]])
    writer.writerow(["HTTP событий", event_summary["http_request_count"]])
    writer.writerow(["HTTP 5xx", event_summary["http_critical_count"]])
    writer.writerow(["HTTP предупреждений", event_summary["http_warning_count"]])
    writer.writerow(["Медленных HTTP", event_summary["slow_request_count"]])
    if event_summary["latest_http_request"]:
        latest_http = event_summary["latest_http_request"]
        writer.writerow(["Последний HTTP", latest_http["created_at"]])
        writer.writerow(["HTTP событие", latest_http["message"]])
        writer.writerow(["HTTP детали", latest_http["details"]])
    if event_summary["latest_critical"]:
        latest = event_summary["latest_critical"]
        writer.writerow(["Последняя критичная", latest["created_at"]])
        writer.writerow(["Событие", latest["message"]])
        writer.writerow(["Детали", latest["details"]])
    writer.writerow([])

    writer.writerow(["Журнал ошибок приложения"])
    writer.writerow(["Статус", error_monitoring["status_label"]])
    writer.writerow(["Открыто", error_monitoring["summary"]["open"]])
    writer.writerow([
        "Повторяющихся",
        error_monitoring["summary"]["repeated"],
    ])
    writer.writerow(["Решено", error_monitoring["summary"]["resolved"]])
    writer.writerow([
        "Порог уведомления",
        error_monitoring["policy"]["alert_threshold"],
    ])
    writer.writerow([
        "ID", "Статус", "Тип", "Метод", "Маршрут", "Повторов",
        "Первое событие", "Последнее событие", "Последний error_id",
    ])
    for incident in error_monitoring["incidents"]:
        writer.writerow([
            incident["id"],
            incident["status_label"],
            incident["error_type"],
            incident["method"],
            incident["path_pattern"],
            incident["occurrence_count"],
            incident["first_seen_at"],
            incident["last_seen_at"],
            incident["last_error_id"],
        ])
    writer.writerow([])

    writer.writerow(["Журнал системы"])
    writer.writerow([
        "Дата",
        "Уровень",
        "Источник",
        "Пользователь",
        "Событие",
        "Детали",
    ])
    for event in diagnostics["system_events"]:
        writer.writerow([
            event["created_at"],
            event["severity_label"],
            event["source"],
            event["username"],
            event["message"],
            event["details"],
        ])

    return Response(
        "\ufeff" + output.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": "attachment; filename=system_report.csv",
        },
    )


@app.get("/api/system/diagnostics")
async def api_system_diagnostics(request: Request):
    username = get_user(request)

    if not username:
        return JSONResponse({"error": "auth_required"}, status_code=401)

    role = get_role(username)

    if role != "superadmin":
        return JSONResponse({"error": "forbidden"}, status_code=403)

    diagnostics = build_system_diagnostics(role)
    diagnostics["ok"] = True
    diagnostics["export_url"] = "/system/export"

    return diagnostics


@app.get("/api/system/error-incidents")
async def api_system_error_incidents(
    request: Request,
    status: str = "all",
    limit: int = 50,
):
    username = get_user(request)
    if not username:
        return JSONResponse({"error": "auth_required"}, status_code=401)
    if get_role(username) != "superadmin":
        return JSONResponse({"error": "forbidden"}, status_code=403)
    return {
        "ok": True,
        "status": status,
        "incidents": get_error_incidents(status=status, limit=limit),
        "overview": get_error_monitoring_overview(limit=0),
        "export_url": "/system/errors/export",
    }


@app.post("/system/errors/{incident_id}/acknowledge")
async def system_error_incident_acknowledge(
    request: Request,
    incident_id: int,
):
    username = get_user(request)
    if not username:
        return RedirectResponse("/login", status_code=302)
    if get_role(username) != "superadmin":
        return RedirectResponse("/", status_code=302)
    result = acknowledge_error_incident(incident_id, username)
    notice = (
        "error_incident_acknowledged"
        if result["ok"]
        else "error_incident_action_skipped"
    )
    if result["ok"]:
        log_system_event(
            "error_incident",
            "info",
            username,
            "monitoring",
            f"Ошибка #{incident_id} принята в работу",
            "Статус инцидента изменён на acknowledged.",
        )
    return RedirectResponse(
        "/system?" + urlencode({"notice": notice, "incident": incident_id})
        + "#error-incidents",
        status_code=302,
    )


@app.post("/system/errors/{incident_id}/resolve")
async def system_error_incident_resolve(
    request: Request,
    incident_id: int,
):
    username = get_user(request)
    if not username:
        return RedirectResponse("/login", status_code=302)
    if get_role(username) != "superadmin":
        return RedirectResponse("/", status_code=302)
    result = resolve_error_incident(
        incident_id,
        username,
        "Решено вручную в системной диагностике.",
    )
    notice = (
        "error_incident_resolved"
        if result["ok"]
        else "error_incident_action_skipped"
    )
    if result["ok"]:
        log_system_event(
            "error_incident",
            "ok",
            username,
            "monitoring",
            f"Ошибка #{incident_id} решена",
            "Статус инцидента изменён на resolved.",
        )
    return RedirectResponse(
        "/system?" + urlencode({"notice": notice, "incident": incident_id})
        + "#error-incidents",
        status_code=302,
    )


@app.get("/system/errors/export")
async def system_error_incidents_export(request: Request):
    username = get_user(request)
    if not username:
        return RedirectResponse("/login", status_code=302)
    if get_role(username) != "superadmin":
        return RedirectResponse("/", status_code=302)

    incidents = get_error_incidents(limit=500)
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Журнал ошибок приложения"])
    writer.writerow([
        "ID", "Статус", "Уровень", "Тип", "Источник", "Метод",
        "Маршрут", "Повторов", "Повторных открытий", "Первое событие",
        "Последнее событие", "Принял", "Решил", "Последний error_id",
        "Последний request_id", "Уведомлений",
    ])
    for incident in incidents:
        writer.writerow([
            incident["id"],
            incident["status_label"],
            incident["severity"],
            incident["error_type"],
            incident["source"],
            incident["method"],
            incident["path_pattern"],
            incident["occurrence_count"],
            incident["reopen_count"],
            incident["first_seen_at"],
            incident["last_seen_at"],
            incident["acknowledged_by"],
            incident["resolved_by"],
            incident["last_error_id"],
            incident["last_request_id"],
            incident["notification_count"],
        ])
    return Response(
        "\ufeff" + output.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": (
                "attachment; filename=application_error_incidents.csv"
            ),
        },
    )


@app.get("/system/events/export")
async def system_events_export(request: Request):
    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role != "superadmin":
        return RedirectResponse("/", status_code=302)

    events = get_system_event_history(200)
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Журнал системы"])
    writer.writerow(["Дата", "Уровень", "Источник", "Пользователь", "Событие", "Детали"])

    for event in events:
        writer.writerow([
            event["created_at"],
            event["severity_label"],
            event["source"],
            event["username"],
            event["message"],
            event["details"],
        ])

    return Response(
        "\ufeff" + output.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": (
                "attachment; filename=system_events.csv"
            ),
        },
    )


@app.post("/system/events/cleanup")
async def system_events_cleanup(request: Request):
    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role != "superadmin":
        return RedirectResponse("/", status_code=302)

    result = cleanup_system_events(username)
    notice = (
        "system_events_cleanup_done"
        if result["deleted_count"]
        else "system_events_cleanup_empty"
    )

    return RedirectResponse(
        "/system?" + urlencode({
            "notice": notice,
            "deleted": result["deleted_count"],
        }),
        status_code=302,
    )


@app.get("/backup", response_class=HTMLResponse)
async def backup_page(
    request: Request,
    notice: str = "",
    error: str = "",
    file: str = "",
    job: str = "",
    processed: str = "",
    failed: str = "",
    deleted: str = "",
    freed: str = "",
):
    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role != "superadmin":
        return RedirectResponse("/", status_code=302)

    backup_status = get_backup_status()
    backup_events = get_backup_event_history()
    background_queue_status = get_background_queue_status()
    backup_jobs = get_recent_background_jobs(
        job_type="database_backup",
        limit=8,
    )

    return templates.TemplateResponse(
        request,
        "backup.html",
        {
            "request": request,
            "username": username,
            "role": role,
            "backup_status": backup_status,
            "backup_events": backup_events,
            "background_queue_status": background_queue_status,
            "backup_jobs": backup_jobs,
            "links": build_backup_links(),
            "notice": notice,
            "error": error,
            "file": file,
            "job": job,
            "processed": processed,
            "failed": failed,
            "deleted": deleted,
            "freed": freed,
        },
    )


@app.post("/backup/create")
async def backup_create(request: Request):
    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role != "superadmin":
        return RedirectResponse("/", status_code=302)

    try:
        queued = enqueue_database_backup_job(username)
    except Exception:
        log_backup_event(
            username,
            "Постановка копии в очередь",
            "Ошибка",
            "",
            "Не удалось поставить резервную копию в фоновую очередь.",
        )
        return RedirectResponse(
            "/backup?error=backup_queue_failed",
            status_code=302,
        )

    log_backup_event(
        username,
        "Постановка копии в очередь",
        "Успешно" if queued["created"] else "Без изменений",
        "",
        (
            "Резервная копия поставлена в фоновую очередь."
            if queued["created"]
            else "Создание резервной копии уже ожидает выполнения."
        ),
    )

    notice = "backup_queued" if queued["created"] else "backup_already_queued"
    params = urlencode({
        "notice": notice,
        "job": queued["job"]["id"],
    })
    return RedirectResponse(f"/backup?{params}", status_code=302)


@app.post("/backup/jobs/run")
async def backup_run_background_jobs(request: Request):
    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)
    if get_role(username) != "superadmin":
        return RedirectResponse("/", status_code=302)

    summary = run_background_job_batch(
        worker_id=f"backup-{username}-{uuid4().hex[:10]}",
    )
    params = urlencode({
        "notice": (
            "background_jobs_failed"
            if summary["failed"] or summary["stale_failed"]
            else "background_jobs_run"
        ),
        "processed": summary["succeeded"],
        "failed": summary["failed"] + summary["stale_failed"],
    })
    return RedirectResponse(f"/backup?{params}", status_code=302)


@app.post("/backup/cleanup")
async def backup_cleanup(request: Request):
    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role != "superadmin":
        return RedirectResponse("/", status_code=302)

    result = cleanup_old_database_backups()
    log_backup_event(
        username,
        "Очистка старых копий",
        "Успешно" if result["deleted_count"] else "Без изменений",
        "",
        (
            f"Удалено: {result['deleted_count']}. "
            f"Освобождено: {result['deleted_size_label']}."
        ),
    )
    notice = (
        "backup_cleanup_done"
        if result["deleted_count"]
        else "backup_cleanup_empty"
    )
    params = urlencode({
        "notice": notice,
        "deleted": result["deleted_count"],
        "freed": result["deleted_size_label"],
    })

    return RedirectResponse(
        f"/backup?{params}",
        status_code=302,
    )


@app.post("/backup/restore-check")
async def backup_restore_check(request: Request, file: str = ""):
    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role != "superadmin":
        return RedirectResponse("/", status_code=302)

    result = run_backup_restore_drill(file)

    if result["error"]:
        log_backup_event(
            username,
            "Проверка восстановления",
            "Ошибка",
            result["file"],
            result["message"],
        )
        return RedirectResponse(
            f"/backup?error={result['error']}&file={result['file']}",
            status_code=302,
        )

    log_backup_event(
        username,
        "Проверка восстановления",
        "Успешно",
        result["file"],
        result["message"],
    )

    return RedirectResponse(
        f"/backup?notice=restore_check_ok&file={result['file']}",
        status_code=302,
    )


@app.get("/backup/export")
async def backup_export(request: Request):
    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role != "superadmin":
        return RedirectResponse("/", status_code=302)

    backup_status = get_backup_status()
    backup_events = get_backup_event_history()
    background_queue_status = get_background_queue_status()
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Резервные копии"])
    writer.writerow(["Статус", backup_status["status_label"]])
    writer.writerow(["Backend", backup_status["backend_label"]])
    writer.writerow(["Резюме", backup_status["summary"]])
    writer.writerow(["Действие", backup_status["action"]])
    writer.writerow(["База найдена", "да" if backup_status["db_exists"] else "нет"])
    writer.writerow(["Размер базы", backup_status["db_size_label"]])
    writer.writerow([
        "Папка копий",
        "да" if backup_status["backup_path_exists"] else "нет",
    ])
    writer.writerow(["Копий", backup_status["count"]])
    writer.writerow(["Общий размер", backup_status["total_size_label"]])
    writer.writerow(["Последняя копия", backup_status["latest_name"]])
    writer.writerow(["Дата последней", backup_status["latest_created_at"]])
    writer.writerow(["Возраст последней", backup_status["latest_age_label"]])
    writer.writerow([
        "Проверка последней",
        backup_status["latest_verification"]["status_label"],
    ])
    writer.writerow([
        "Проблемных среди последних",
        backup_status["verification_problem_count"],
    ])
    writer.writerow([
        "Проверка восстановления",
        backup_status["restore_check"]["status_label"],
    ])
    writer.writerow([
        "Результат проверки восстановления",
        backup_status["restore_check"]["message"],
    ])
    writer.writerow([
        "Внешняя копия",
        backup_status["remote_copy"]["status_label"],
    ])
    writer.writerow([
        "Результат внешней копии",
        backup_status["remote_copy"]["message"],
    ])
    writer.writerow(["Хранить минимум копий", backup_status["retention_keep"]])
    writer.writerow(["Срок хранения, дней", backup_status["retention_days"]])
    writer.writerow(["К очистке", backup_status["cleanup_count"]])
    writer.writerow(["Размер к очистке", backup_status["cleanup_size_label"]])
    writer.writerow([
        "Фоновая очередь",
        background_queue_status["status_label"],
    ])
    writer.writerow(["Заданий ожидают", background_queue_status["pending"]])
    writer.writerow(["Заданий выполняются", background_queue_status["running"]])
    writer.writerow(["Ошибок очереди за 24 часа", background_queue_status["failed_24h"]])
    writer.writerow([])

    writer.writerow(["Последние копии"])
    writer.writerow(["Файл", "Дата", "Возраст", "Размер", "Хранение", "Проверка"])
    for item in backup_status["recent_files"]:
        writer.writerow([
            item["name"],
            item["created_at"],
            item["age_label"],
            item["size_label"],
            item["stale_label"],
            item["verification"]["status_label"],
        ])

    writer.writerow([])
    writer.writerow(["Журнал операций"])
    writer.writerow(["Дата", "Пользователь", "Действие", "Статус", "Файл", "Детали"])
    for event in backup_events:
        writer.writerow([
            event["created_at"],
            event["username"],
            event["action"],
            event["status"],
            event["file_name"],
            event["details"],
        ])

    return Response(
        "\ufeff" + output.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": (
                "attachment; filename=platform_backups.csv"
            ),
        },
    )


@app.get("/backup/download")
async def backup_download(request: Request, file: str = ""):
    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role != "superadmin":
        return RedirectResponse("/", status_code=302)

    file_path, error = get_backup_download_path(file)

    if error:
        return RedirectResponse(
            f"/backup?error={error}",
            status_code=302,
        )

    return FileResponse(
        file_path,
        filename=file_path.name,
        media_type="application/octet-stream",
    )


def get_a3_company_id(request: Request):
    username = get_user(request)

    if not username:
        return None

    role = get_role(username)

    if role not in ("boss", "manager"):
        return None

    company_id = get_user_company_id(username)

    if not has_feature(company_id, "automation"):
        return None

    return company_id


def get_a3_owner_company_id(request: Request):
    company_id = get_a3_company_id(request)

    if not company_id or get_role(get_user(request)) != "boss":
        return None

    return company_id


def parse_a3_governance_bool(value):
    if isinstance(value, bool):
        return 1 if value else 0

    if isinstance(value, int) and value in (0, 1):
        return value

    if isinstance(value, str):
        normalized = value.strip().lower()

        if normalized in ("1", "true", "yes", "on"):
            return 1

        if normalized in ("0", "false", "no", "off"):
            return 0

    raise ValueError("invalid boolean value")


A3_API_ERROR_MESSAGES = {
    "forbidden": "Доступ запрещён",
    "not_found": "Объект не найден",
    "unsupported_action": "Действие не поддерживается",
    "invalid_target_id": "Некорректный номер цели",
    "rule_not_found": "Правило не найдено",
    "invalid_governance_settings": "Некорректные настройки управления",
    "invalid_protected_rules": "Некорректный список защищённых правил",
    "target_not_found": "Цель не найдена",
    "protected_rule": "Правило защищено",
    "duplicate_pending_action": "Такое действие уже ждёт подтверждения",
    "cooldown_active": "Слишком много одинаковых действий за короткое время",
}

A3_SCHEDULER_ALERT_COOLDOWN_HOURS = 6
A3_SCHEDULER_RECOVERY_LOOKBACK_DAYS = 7
A3_SCHEDULER_WARNING_TITLE = "A3: проверьте фоновый планировщик"
A3_SCHEDULER_CRITICAL_TITLE = "A3: критическая ошибка планировщика"
A3_SCHEDULER_RECOVERY_TITLE = "A3: работа планировщика восстановлена"


def notify_a3_approval_required(company_id, action_count):
    if not action_count:
        return False

    try:
        conn = connect()
        c = conn.cursor()
        company = c.execute("""
            SELECT owner_username
            FROM companies
            WHERE id=?
        """, (company_id,)).fetchone()
        conn.close()

        owner_username = str(
            company["owner_username"] if company else ""
        ).strip()

        if not owner_username:
            return False

        create_notification(
            company_id,
            owner_username,
            "Требуется подтверждение ИИ-действия",
            (
                "Автоматизация подготовила критические действия: "
                f"{action_count}. Проверьте очередь подтверждений."
            ),
            "/automation",
        )
    except Exception:
        return False

    return True


def notify_a3_scheduler_reliability(
    company_id,
    reliability=None,
    now=None,
    telegram_sender=None,
):
    try:
        reliability = reliability or get_a3_cycle_reliability(company_id)
    except Exception:
        return {"created": False, "reason": "reliability_unavailable"}

    status = reliability.get("status") or "unknown"

    if status not in {"stable", "warning", "critical"}:
        return {"created": False, "reason": "status_not_alertable"}

    now_value = now or datetime.now()
    is_recovery = status == "stable"
    title = {
        "stable": A3_SCHEDULER_RECOVERY_TITLE,
        "warning": A3_SCHEDULER_WARNING_TITLE,
        "critical": A3_SCHEDULER_CRITICAL_TITLE,
    }[status]
    link = "/automation#a3-cycle-history-card"
    cutoff = (
        now_value - timedelta(hours=A3_SCHEDULER_ALERT_COOLDOWN_HOURS)
    ).strftime("%Y-%m-%d %H:%M")
    recovery_lookback = (
        now_value - timedelta(days=A3_SCHEDULER_RECOVERY_LOOKBACK_DAYS)
    ).strftime("%Y-%m-%d %H:%M")

    try:
        conn = connect()
        try:
            c = conn.cursor()
            company = c.execute("""
                SELECT
                    companies.owner_username,
                    users.telegram_chat_id
                FROM companies
                LEFT JOIN users
                  ON users.company_id=companies.id
                 AND users.username=companies.owner_username
                WHERE companies.id=?
            """, (company_id,)).fetchone()
            owner_username = str(
                company["owner_username"] if company else ""
            ).strip()
            owner_chat_id = str(
                company["telegram_chat_id"] if company else ""
            ).strip()

            if not owner_username:
                return {"created": False, "reason": "owner_not_found"}

            latest_recovery = c.execute("""
                SELECT id
                FROM notifications
                WHERE company_id=?
                  AND username=?
                  AND title=?
                  AND link=?
                ORDER BY id DESC
                LIMIT 1
            """, (
                company_id,
                owner_username,
                A3_SCHEDULER_RECOVERY_TITLE,
                link,
            )).fetchone()

            if is_recovery:
                latest_alert = c.execute("""
                    SELECT id
                    FROM notifications
                    WHERE company_id=?
                      AND username=?
                      AND title IN (?, ?)
                      AND link=?
                      AND created_at>=?
                    ORDER BY id DESC
                    LIMIT 1
                """, (
                    company_id,
                    owner_username,
                    A3_SCHEDULER_WARNING_TITLE,
                    A3_SCHEDULER_CRITICAL_TITLE,
                    link,
                    recovery_lookback,
                )).fetchone()
                duplicate = None
            else:
                latest_alert = None
                duplicate = c.execute("""
                    SELECT id
                    FROM notifications
                    WHERE company_id=?
                      AND username=?
                      AND title=?
                      AND link=?
                      AND created_at>=?
                    ORDER BY id DESC
                    LIMIT 1
                """, (
                    company_id,
                    owner_username,
                    title,
                    link,
                    cutoff,
                )).fetchone()
        finally:
            conn.close()

        if is_recovery and not latest_alert:
            return {"created": False, "reason": "no_active_alert"}

        if (
            is_recovery
            and latest_recovery
            and latest_recovery["id"] > latest_alert["id"]
        ):
            return {
                "created": False,
                "reason": "recovery_already_notified",
                "notification_id": latest_recovery["id"],
            }

        if (
            not is_recovery
            and duplicate
            and (
                not latest_recovery
                or latest_recovery["id"] < duplicate["id"]
            )
        ):
            return {
                "created": False,
                "reason": "cooldown_active",
                "notification_id": duplicate["id"],
            }

        if is_recovery:
            reliability_rate = reliability.get("reliability_rate")
            rate_label = (
                f"{reliability_rate}%"
                if reliability_rate is not None
                else "нет данных"
            )
            message = (
                "Фоновый планировщик A3 снова работает стабильно. "
                f"Надёжность последних запусков: {rate_label}. "
                "Критических ошибок подряд нет."
            )
        else:
            message = (
                f"{reliability.get('message') or 'Обнаружена проблема фонового запуска.'} "
                f"Ошибок подряд: {reliability.get('consecutive_errors') or 0}. "
                f"Последний запуск: "
                f"{reliability.get('latest_scheduler_age_label') or 'нет данных'}. "
                f"{reliability.get('recommendation') or 'Проверьте журнал A3.'}"
            )
        create_notification(
            company_id,
            owner_username,
            title,
            message,
            link,
        )
    except Exception:
        return {"created": False, "reason": "notification_failed"}

    telegram_sent = False
    if owner_chat_id:
        try:
            sender = telegram_sender or send_message_to_chat
            telegram_sent = bool(
                sender(
                    owner_chat_id,
                    f"{title}\n\n{message}",
                )
            )
        except Exception:
            telegram_sent = False

    return {
        "created": True,
        "reason": "recovery_created" if is_recovery else "created",
        "title": title,
        "username": owner_username,
        "telegram_configured": bool(owner_chat_id),
        "telegram_sent": telegram_sent,
    }


def record_a3_scheduler_timeline(
    company_id,
    severity,
    title,
    message,
):
    try:
        create_ops_timeline_event(
            company_id=company_id,
            event_type="a3_scheduler",
            severity=severity,
            title=title,
            message=message,
            source="scheduler",
            target_type="company",
            target_id=company_id,
            cooldown_minutes=30,
        )
    except Exception:
        return False

    return True


def record_a3_cycle_result(
    company_id,
    cycle=None,
    health=None,
    status="",
    message="",
    triggered_by="",
):
    cycle = cycle or {}
    result = cycle.get("result") or {}
    health = health or {}
    normalized_status = status or (
        "warning"
        if (
            result.get("failed", 0)
            or result.get("awaiting_approval", 0)
            or result.get("retry_not_ready_events", 0)
            or result.get("retry_failed_events", 0)
        )
        else "completed"
    )

    try:
        return record_a3_cycle_run(
            company_id=company_id,
            triggered_by=(
                triggered_by
                or result.get("triggered_by")
                or "system"
            ),
            status=normalized_status,
            decision_count=cycle.get("decision_count", 0),
            queued_actions=cycle.get("queued_from_decisions", 0),
            processed_actions=result.get("processed", 0),
            awaiting_approval=result.get("awaiting_approval", 0),
            failed_actions=result.get("failed", 0),
            retried_events=result.get("retried_events", 0),
            retry_not_ready_events=result.get("retry_not_ready_events", 0),
            retry_failed_events=result.get("retry_failed_events", 0),
            health_score=health.get("score"),
            health_status=health.get("status", ""),
            duration_ms=cycle.get("duration_ms", 0),
            message=message,
        )
    except Exception:
        return None


async def run_calendar_plan_scheduler(
    company_id,
    now_dt=None,
    actor_username="",
    source="scheduler",
):
    source = "manual_run" if source == "manual_run" else "scheduler"
    result = {
        "company_id": company_id,
        "enabled": False,
        "source": source,
        "publish": None,
        "remind": None,
        "changed_days": 0,
        "notifications_sent": 0,
        "skipped": False,
        "skip_reason": "",
        "range_start": "",
        "range_end": "",
        "error": "",
        "incident_alerts_sent": 0,
        "recovery_alerts_sent": 0,
    }

    if not has_feature(company_id, "calendar"):
        result["error"] = "calendar_disabled"
        return result

    settings = get_company_settings(company_id)
    auto_publish = bool(settings["calendar_auto_publish"])
    auto_remind = bool(settings["calendar_auto_remind"])
    auto_days_ahead = max(
        0,
        min(
            14,
            int(
                settings["calendar_auto_days_ahead"]
                if settings["calendar_auto_days_ahead"] is not None
                else 7
            ),
        ),
    )
    auto_window_start = str(
        settings["calendar_auto_window_start"] or "00:00"
    )
    auto_window_end = str(
        settings["calendar_auto_window_end"] or "23:59"
    )
    result["policy"] = {
        "days_ahead": auto_days_ahead,
        "window_start": auto_window_start,
        "window_end": auto_window_end,
    }

    if not auto_publish and not auto_remind:
        result["error"] = "automation_disabled"
        return result

    conn = connect()
    c = conn.cursor()

    if actor_username:
        actor = c.execute("""
        SELECT username
        FROM users
        WHERE company_id=?
          AND username=?
          AND role IN ('boss', 'manager')
          AND COALESCE(is_active, 1)=1
        LIMIT 1
        """, (company_id, actor_username)).fetchone()
    else:
        actor = c.execute("""
        SELECT username
        FROM users
        WHERE company_id=?
          AND role IN ('boss', 'manager')
          AND COALESCE(is_active, 1)=1
        ORDER BY CASE role WHEN 'boss' THEN 0 ELSE 1 END, id
        LIMIT 1
        """, (company_id,)).fetchone()

    conn.close()

    if not actor:
        result["error"] = "actor_not_found"
        return result

    now_dt = now_dt or datetime.now()
    calendar_incident_policy = get_calendar_incident_policy()
    range_start = now_dt.date()
    range_end = range_start + timedelta(days=auto_days_ahead)
    result["range_start"] = range_start.strftime("%Y-%m-%d")
    result["range_end"] = range_end.strftime("%Y-%m-%d")
    result["enabled"] = True
    started_at = datetime.now().strftime("%Y-%m-%d %H:%M")
    scheduler_run_id = create_calendar_scheduler_run(
        company_id,
        source,
        actor["username"],
        result["range_start"],
        result["range_end"],
        started_at,
    )
    result["scheduler_run_id"] = scheduler_run_id

    if source == "scheduler":
        result["recovery_alerts_sent"] += (
            close_calendar_scheduler_incident(
                company_id,
                allowed_types={"stale"},
            )
        )

    if (
        source == "scheduler"
        and not calendar_automation_time_allowed(
            now_dt,
            auto_window_start,
            auto_window_end,
        )
    ):
        result["skipped"] = True
        result["skip_reason"] = "outside_time_window"
        completed_at = datetime.now().strftime("%Y-%m-%d %H:%M")
        conn = connect()
        c = conn.cursor()
        c.execute("""
        INSERT INTO calendar_plan_scheduler_status (
            company_id, last_started_at, last_completed_at,
            last_status, last_error, last_changed_days,
            last_notifications_sent, last_source,
            last_triggered_by, last_result_json
        )
        VALUES (?, ?, ?, 'waiting', '', 0, 0, ?, ?, ?)
        ON CONFLICT(company_id) DO UPDATE SET
            last_started_at=excluded.last_started_at,
            last_completed_at=excluded.last_completed_at,
            last_status='waiting',
            last_error='',
            last_changed_days=0,
            last_notifications_sent=0,
            last_source=excluded.last_source,
            last_triggered_by=excluded.last_triggered_by,
            last_result_json=excluded.last_result_json
        WHERE calendar_plan_scheduler_status.last_status!='running'
        """, (
            company_id,
            completed_at,
            completed_at,
            source,
            actor["username"],
            json.dumps(result, ensure_ascii=False),
        ))
        conn.commit()
        conn.close()
        finish_calendar_scheduler_run(
            scheduler_run_id,
            company_id,
            "skipped",
            "Вне рабочего окна",
            result,
        )
        return result

    stale_before = (
        datetime.now() - timedelta(
            minutes=calendar_incident_policy["stuck_minutes"],
        )
    ).strftime("%Y-%m-%d %H:%M")
    first_week_start = (
        range_start - timedelta(days=range_start.weekday())
    )
    week_starts = []
    current_week_start = first_week_start

    while current_week_start <= range_end:
        week_starts.append(current_week_start)
        current_week_start += timedelta(days=7)

    conn = connect()
    c = conn.cursor()
    previous_status = c.execute("""
    SELECT last_status, last_started_at
    FROM calendar_plan_scheduler_status
    WHERE company_id=?
    """, (company_id,)).fetchone()
    stale_running = bool(
        previous_status
        and previous_status["last_status"] == "running"
        and str(previous_status["last_started_at"] or "") <= stale_before
    )
    c.execute("""
    INSERT INTO calendar_plan_scheduler_status (
        company_id, last_started_at, last_status,
        last_error, last_changed_days, last_notifications_sent,
        last_source, last_triggered_by
    )
    VALUES (?, ?, 'running', '', 0, 0, ?, ?)
    ON CONFLICT(company_id) DO UPDATE SET
        last_started_at=excluded.last_started_at,
        last_status='running',
        last_error='',
        last_source=excluded.last_source,
        last_triggered_by=excluded.last_triggered_by
    WHERE calendar_plan_scheduler_status.last_status!='running'
       OR COALESCE(
            calendar_plan_scheduler_status.last_started_at,
            ''
       )<=?
    """, (
        company_id,
        started_at,
        source,
        actor["username"],
        stale_before,
    ))
    acquired = c.rowcount > 0
    conn.commit()
    conn.close()

    if not acquired:
        result["error"] = "scheduler_already_running"
        finish_calendar_scheduler_run(
            scheduler_run_id,
            company_id,
            "locked",
            "Другой запуск уже выполняется",
            result,
        )
        return result

    if stale_running and source == "scheduler":
        result["incident_alerts_sent"] = (
            open_calendar_scheduler_incident(
                company_id,
                "stuck",
                (
                    "Предыдущий запуск не завершился за "
                    f"{calendar_incident_policy['stuck_minutes']} мин. "
                    "Система начала автоматическое восстановление."
                ),
            )
        )

    try:
        for action, result_key, enabled in (
            ("publish_ready", "publish", auto_publish),
            ("remind_pending", "remind", auto_remind),
        ):
            if not enabled:
                continue

            action_result = {
                "ok": True,
                "action": action,
                "source": source,
                "summary": {},
                "items": [],
                "weeks": [],
                "operation_run_id": 0,
                "operation_run_ids": [],
            }

            for week_start in week_starts:
                response = await api_calendar_dispatch_week_plans(
                    make_internal_calendar_plan_request(
                        actor["username"],
                        {
                            "action": action,
                            "week_start": week_start.strftime(
                                "%Y-%m-%d"
                            ),
                            "date_from": result["range_start"],
                            "date_to": result["range_end"],
                        },
                        source=source,
                    )
                )

                if isinstance(response, JSONResponse):
                    response_data = json.loads(
                        response.body.decode("utf-8")
                    )
                else:
                    response_data = response

                action_result["weeks"].append(response_data)

                if not response_data.get("ok"):
                    action_result["ok"] = False
                    result["error"] = response_data.get(
                        "error",
                        "operation_failed",
                    )
                    continue

                action_result["items"].extend(
                    response_data.get("items", [])
                )
                operation_run_id = int(
                    response_data.get("operation_run_id") or 0
                )

                if operation_run_id:
                    action_result["operation_run_ids"].append(
                        operation_run_id
                    )

                    if not action_result["operation_run_id"]:
                        action_result["operation_run_id"] = (
                            operation_run_id
                        )

                for key, value in response_data.get(
                    "summary",
                    {},
                ).items():
                    if isinstance(value, int):
                        action_result["summary"][key] = (
                            action_result["summary"].get(key, 0)
                            + value
                        )

            result[result_key] = action_result
            action_summary = action_result["summary"]
            result["changed_days"] += (
                action_summary.get("published_days", 0)
                + action_summary.get("updated_days", 0)
                + action_summary.get("affected_days", 0)
            )
            result["notifications_sent"] += (
                action_summary.get("notified_workers", 0)
                + action_summary.get("sent_reminders", 0)
            )
    except Exception as exc:
        result["error"] = str(exc)[:500]

    if result["error"] and source == "scheduler":
        result["incident_alerts_sent"] = (
            open_calendar_scheduler_incident(
                company_id,
                "error",
                (
                    "Автоматический запуск завершился с ошибкой: "
                    f"{result['error']}"
                ),
            )
        )
    elif not result["error"] and source == "scheduler":
        result["recovery_alerts_sent"] += (
            close_calendar_scheduler_incident(company_id)
        )

    completed_at = datetime.now().strftime("%Y-%m-%d %H:%M")
    conn = connect()
    c = conn.cursor()
    c.execute("""
    UPDATE calendar_plan_scheduler_status
    SET last_completed_at=?,
        last_status=?,
        last_error=?,
        last_changed_days=?,
        last_notifications_sent=?,
        last_result_json=?
    WHERE company_id=?
    """, (
        completed_at,
        "error" if result["error"] else "done",
        result["error"],
        result["changed_days"],
        result["notifications_sent"],
        json.dumps(result, ensure_ascii=False),
        company_id,
    ))
    conn.commit()
    conn.close()
    finish_calendar_scheduler_run(
        scheduler_run_id,
        company_id,
        "error" if result["error"] else "done",
        result["error"],
        result,
    )

    return result


def acknowledge_calendar_scheduler_incident(
    company_id,
    actor_username,
):
    now_value = datetime.now().strftime("%Y-%m-%d %H:%M")
    conn = connect()
    c = conn.cursor()
    incident = c.execute("""
    SELECT
        active_incident,
        incident_message,
        incident_acknowledged_at
    FROM calendar_plan_scheduler_status
    WHERE company_id=?
    """, (company_id,)).fetchone()

    if not incident or not str(incident["active_incident"] or ""):
        conn.close()
        return {
            "ok": False,
            "error": "incident_not_found",
            "message": "Активный инцидент не найден.",
        }

    if incident["incident_acknowledged_at"]:
        conn.close()
        return {
            "ok": False,
            "error": "already_acknowledged",
            "message": "Инцидент уже принят в работу.",
        }

    c.execute("""
    UPDATE calendar_plan_scheduler_status
    SET incident_acknowledged_at=?,
        incident_acknowledged_by=?,
        incident_assigned_at=?,
        incident_assigned_to=?,
        incident_assigned_by=?
    WHERE company_id=?
      AND active_incident!=''
      AND incident_acknowledged_at IS NULL
    """, (
        now_value,
        actor_username,
        now_value,
        actor_username,
        actor_username,
        company_id,
    ))

    if c.rowcount == 0:
        conn.close()
        return {
            "ok": False,
            "error": "already_acknowledged",
            "message": "Инцидент уже принят в работу.",
        }

    log_calendar_scheduler_incident_event(
        c,
        company_id,
        incident["active_incident"],
        "acknowledged",
        incident["incident_message"],
        actor_username=actor_username,
        created_at=now_value,
    )
    conn.commit()
    conn.close()

    return {
        "ok": True,
        "message": "Инцидент принят в работу.",
        "acknowledged_at": now_value,
        "acknowledged_by": actor_username,
    }


def add_calendar_scheduler_incident_note(
    company_id,
    actor_username,
    message,
):
    message = str(message or "").strip()

    if not message:
        return {
            "ok": False,
            "error": "empty_note",
            "message": "Введите текст заметки.",
        }

    if len(message) > 500:
        return {
            "ok": False,
            "error": "note_too_long",
            "message": "Заметка не должна превышать 500 символов.",
        }

    conn = connect()
    begin_locked_transaction(conn, "calendar_scheduler_incidents")
    c = conn.cursor()
    actor = c.execute("""
    SELECT username
    FROM users
    WHERE username=?
      AND role='superadmin'
      AND COALESCE(is_active, 1)=1
    LIMIT 1
    """, (actor_username,)).fetchone()
    incident = c.execute("""
    SELECT active_incident
    FROM calendar_plan_scheduler_status
    WHERE company_id=?
    """, (company_id,)).fetchone()

    if not actor:
        conn.close()
        return {
            "ok": False,
            "error": "actor_not_found",
            "message": "Администратор платформы не найден.",
        }

    if not incident or not str(incident["active_incident"] or ""):
        conn.close()
        return {
            "ok": False,
            "error": "incident_not_found",
            "message": "Активный инцидент не найден.",
        }

    log_calendar_scheduler_incident_event(
        c,
        company_id,
        incident["active_incident"],
        "note",
        message,
        actor_username=actor_username,
    )
    conn.commit()
    conn.close()
    return {
        "ok": True,
        "message": "Заметка добавлена в журнал.",
    }


def close_calendar_scheduler_incident(
    company_id,
    allowed_types=None,
    actor_username="",
    recovery_message="",
):
    now_value = datetime.now().strftime("%Y-%m-%d %H:%M")
    conn = connect()
    c = conn.cursor()
    status_row = c.execute("""
    SELECT
        active_incident,
        incident_started_at,
        incident_acknowledged_by
    FROM calendar_plan_scheduler_status
    WHERE company_id=?
    """, (company_id,)).fetchone()

    if not status_row or not str(status_row["active_incident"] or ""):
        conn.close()
        return 0

    incident_type = str(status_row["active_incident"] or "")

    if allowed_types and incident_type not in set(allowed_types):
        conn.close()
        return 0

    incident_started_at = str(
        status_row["incident_started_at"] or "неизвестно"
    )
    title = "Автоматизация календаря восстановлена"
    message = str(recovery_message or "").strip()[:500] or (
        "Планировщик снова работает штатно. "
        f"Инцидент начался: {incident_started_at}."
    )
    recipients = c.execute("""
    SELECT username, telegram_chat_id
    FROM users
    WHERE company_id=?
      AND role='boss'
      AND COALESCE(is_active, 1)=1
    ORDER BY id
    """, (company_id,)).fetchall()

    for recipient in recipients:
        c.execute("""
        INSERT INTO notifications (
            company_id, username, title, message,
            link, is_read, created_at
        )
        VALUES (?, ?, ?, ?, '/calendar/dispatch', 0, ?)
        """, (
            company_id,
            recipient["username"],
            title,
            message,
            now_value,
        ))

    c.execute("""
    UPDATE calendar_plan_scheduler_status
    SET active_incident='',
        incident_started_at=NULL,
        incident_message=NULL,
        last_recovered_at=?,
        incident_acknowledged_at=NULL,
        incident_acknowledged_by=NULL,
        incident_assigned_at=NULL,
        incident_assigned_to=NULL,
        incident_assigned_by=NULL
    WHERE company_id=?
    """, (
        now_value,
        company_id,
    ))
    log_calendar_scheduler_incident_event(
        c,
        company_id,
        incident_type,
        "recovered",
        message,
        actor_username=actor_username,
        created_at=now_value,
    )
    conn.commit()
    conn.close()

    telegram_text = f"{title}\n{message}"

    for recipient in recipients:
        chat_id = str(recipient["telegram_chat_id"] or "").strip()

        if not chat_id:
            continue

        try:
            send_message_to_chat(chat_id, telegram_text)
        except Exception:
            pass

    return len(recipients)


def create_calendar_scheduler_run(
    company_id,
    source,
    actor_username,
    range_start,
    range_end,
    started_at,
):
    conn = connect()
    c = conn.cursor()
    c.execute("""
    INSERT INTO calendar_plan_scheduler_runs (
        company_id, source, actor_username,
        range_start, range_end, status, started_at
    )
    VALUES (?, ?, ?, ?, ?, 'running', ?)
    """, (
        company_id,
        source,
        actor_username,
        range_start,
        range_end,
        started_at,
    ))
    run_id = c.lastrowid
    conn.commit()
    conn.close()
    return run_id


def escalate_calendar_scheduler_incidents(
    now_dt=None,
    after_minutes=None,
    company_id=None,
):
    now_dt = now_dt or datetime.now()
    after_minutes = get_calendar_incident_policy(
        escalation_minutes=after_minutes,
    )["escalation_minutes"]
    cutoff = now_dt - timedelta(minutes=after_minutes)
    now_value = now_dt.strftime("%Y-%m-%d %H:%M")
    conn = connect()
    begin_locked_transaction(conn, "calendar_scheduler_incidents")
    c = conn.cursor()
    incidents = c.execute("""
    SELECT
        scheduler.company_id,
        scheduler.active_incident,
        scheduler.incident_started_at,
        scheduler.incident_message,
        COALESCE(
            companies.name,
            settings.company_name,
            'Компания #' || scheduler.company_id
        ) AS company_name
    FROM calendar_plan_scheduler_status AS scheduler
    LEFT JOIN companies
      ON companies.id=scheduler.company_id
    LEFT JOIN company_settings AS settings
      ON settings.company_id=scheduler.company_id
    WHERE COALESCE(scheduler.active_incident, '')!=''
      AND scheduler.incident_acknowledged_at IS NULL
      AND (? IS NULL OR scheduler.company_id=?)
    ORDER BY scheduler.incident_started_at, scheduler.company_id
    """, (
        company_id,
        company_id,
    )).fetchall()
    recipients = c.execute("""
    SELECT username, company_id, telegram_chat_id
    FROM users
    WHERE role='superadmin'
      AND COALESCE(is_active, 1)=1
    ORDER BY id
    """).fetchall()
    escalated_items = []
    telegram_messages = []

    for incident in incidents:
        incident_started_at = parse_calendar_incident_datetime(
            incident["incident_started_at"],
        )

        if not incident_started_at or incident_started_at > cutoff:
            continue

        already_escalated = c.execute("""
        SELECT 1
        FROM calendar_scheduler_incident_events
        WHERE company_id=?
          AND event_type='escalated'
          AND created_at>=?
        LIMIT 1
        """, (
            incident["company_id"],
            incident["incident_started_at"],
        )).fetchone()

        if already_escalated:
            continue

        age_minutes = max(
            0,
            int(
                (now_dt - incident_started_at).total_seconds()
                // 60
            ),
        )
        age_label = format_calendar_incident_age(age_minutes)
        company_name = str(incident["company_name"] or "")
        title = "Критический инцидент календаря"
        message = (
            f"{company_name}: инцидент не принят {age_label}. "
            f"{incident['incident_message'] or 'Требуется проверка.'}"
        )
        log_calendar_scheduler_incident_event(
            c,
            incident["company_id"],
            incident["active_incident"],
            "escalated",
            message,
            actor_username="watchdog",
            created_at=now_value,
        )

        for recipient in recipients:
            recipient_company_id = int(
                recipient["company_id"] or incident["company_id"]
            )
            c.execute("""
            INSERT INTO notifications (
                company_id, username, title, message,
                link, is_read, created_at
            )
            VALUES (?, ?, ?, ?, ?, 0, ?)
            """, (
                recipient_company_id,
                recipient["username"],
                title,
                message,
                (
                    "/platform/calendar-health/"
                    f"{incident['company_id']}"
                ),
                now_value,
            ))
            chat_id = str(
                recipient["telegram_chat_id"] or ""
            ).strip()

            if chat_id:
                telegram_messages.append((
                    chat_id,
                    f"{title}\n{message}",
                ))

        escalated_items.append({
            "company_id": incident["company_id"],
            "company_name": company_name,
            "incident_type": incident["active_incident"],
            "incident_started_at": incident["incident_started_at"],
            "age_minutes": age_minutes,
            "age_label": age_label,
            "recipients": len(recipients),
        })

    conn.commit()
    conn.close()

    for chat_id, message in telegram_messages:
        try:
            send_message_to_chat(chat_id, message)
        except Exception:
            pass

    return {
        "checked": len(incidents),
        "escalated": len(escalated_items),
        "notifications_sent": (
            len(escalated_items) * len(recipients)
        ),
        "after_minutes": after_minutes,
        "items": escalated_items,
    }


def finish_calendar_scheduler_run(
    run_id,
    company_id,
    status,
    reason,
    result,
):
    completed_at = datetime.now().strftime("%Y-%m-%d %H:%M")
    conn = connect()
    c = conn.cursor()
    c.execute("""
    UPDATE calendar_plan_scheduler_runs
    SET status=?,
        reason=?,
        changed_days=?,
        notifications_sent=?,
        completed_at=?,
        result_json=?
    WHERE id=? AND company_id=?
    """, (
        status,
        str(reason or "")[:500],
        int(result.get("changed_days") or 0),
        int(result.get("notifications_sent") or 0),
        completed_at,
        json.dumps(result, ensure_ascii=False),
        run_id,
        company_id,
    ))
    conn.commit()
    conn.close()
    trim_calendar_scheduler_runs(company_id)


def log_calendar_scheduler_recovery_attempt(
    company_id,
    event_type,
    actor_username,
    message,
):
    if event_type not in {"recovery_started", "recovery_failed"}:
        return False

    conn = connect()
    c = conn.cursor()
    incident = c.execute("""
    SELECT active_incident
    FROM calendar_plan_scheduler_status
    WHERE company_id=?
    """, (company_id,)).fetchone()

    if not incident or not str(incident["active_incident"] or ""):
        conn.close()
        return False

    log_calendar_scheduler_incident_event(
        c,
        company_id,
        incident["active_incident"],
        event_type,
        message,
        actor_username=actor_username,
    )
    conn.commit()
    conn.close()
    return True


def make_internal_calendar_plan_request(
    username,
    payload,
    source="scheduler",
):
    body = json.dumps(payload).encode("utf-8")
    cookie = (
        f"{SESSION_COOKIE_NAME}={sign_session_value(username)}"
    )

    async def receive():
        return {
            "type": "http.request",
            "body": body,
            "more_body": False,
        }

    return Request({
        "type": "http",
        "method": "POST",
        "path": "/api/calendar/dispatch/week-plans",
        "headers": [
            (b"cookie", cookie.encode("utf-8")),
            (b"content-type", b"application/json"),
            (b"content-length", str(len(body)).encode("utf-8")),
        ],
        "query_string": b"",
        "scheme": "http",
        "client": ("127.0.0.1", 0),
        "server": ("internal", 80),
        "state": {"calendar_plan_source": source},
    }, receive)


def notify_overdue_calendar_recoveries(
    now_dt=None,
    after_minutes=None,
    company_id=None,
):
    now_dt = now_dt or datetime.now()
    after_minutes = get_calendar_incident_policy(
        recovery_minutes=after_minutes,
    )["recovery_minutes"]
    cutoff = now_dt - timedelta(minutes=after_minutes)
    now_value = now_dt.strftime("%Y-%m-%d %H:%M")
    conn = connect()
    begin_locked_transaction(conn, "calendar_scheduler_incidents")
    c = conn.cursor()
    incidents = c.execute("""
    SELECT
        scheduler.company_id,
        scheduler.active_incident,
        scheduler.incident_started_at,
        scheduler.incident_message,
        scheduler.incident_acknowledged_at,
        scheduler.incident_acknowledged_by,
        scheduler.incident_assigned_at,
        scheduler.incident_assigned_to,
        scheduler.incident_assigned_by,
        COALESCE(
            companies.name,
            settings.company_name,
            'Компания #' || scheduler.company_id
        ) AS company_name
    FROM calendar_plan_scheduler_status AS scheduler
    LEFT JOIN companies
      ON companies.id=scheduler.company_id
    LEFT JOIN company_settings AS settings
      ON settings.company_id=scheduler.company_id
    WHERE COALESCE(scheduler.active_incident, '')!=''
      AND scheduler.incident_acknowledged_at IS NOT NULL
      AND (? IS NULL OR scheduler.company_id=?)
    ORDER BY
        scheduler.incident_acknowledged_at,
        scheduler.company_id
    """, (
        company_id,
        company_id,
    )).fetchall()
    recipients = c.execute("""
    SELECT username, company_id, telegram_chat_id
    FROM users
    WHERE role='superadmin'
      AND COALESCE(is_active, 1)=1
    ORDER BY id
    """).fetchall()
    overdue_items = []
    telegram_messages = []

    for incident in incidents:
        acknowledged_at = parse_calendar_incident_datetime(
            incident["incident_acknowledged_at"],
        )

        if not acknowledged_at or acknowledged_at > cutoff:
            continue

        already_notified = c.execute("""
        SELECT 1
        FROM calendar_scheduler_incident_events
        WHERE company_id=?
          AND event_type='recovery_overdue'
          AND created_at>=?
        LIMIT 1
        """, (
            incident["company_id"],
            incident["incident_started_at"],
        )).fetchone()

        if already_notified:
            continue

        recovery_age_minutes = max(
            0,
            int(
                (now_dt - acknowledged_at).total_seconds()
                // 60
            ),
        )
        recovery_age_label = format_calendar_incident_age(
            recovery_age_minutes,
        )
        company_name = str(incident["company_name"] or "")
        assigned_to = (
            incident["incident_assigned_to"]
            or incident["incident_acknowledged_by"]
            or "не указан"
        )
        title = "Просрочено восстановление календаря"
        message = (
            f"{company_name}: инцидент в работе "
            f"{recovery_age_label}, но не восстановлен. "
            f"Ответственный: {assigned_to}."
        )
        log_calendar_scheduler_incident_event(
            c,
            incident["company_id"],
            incident["active_incident"],
            "recovery_overdue",
            message,
            actor_username="watchdog",
            created_at=now_value,
        )

        for recipient in recipients:
            recipient_company_id = int(
                recipient["company_id"] or incident["company_id"]
            )
            c.execute("""
            INSERT INTO notifications (
                company_id, username, title, message,
                link, is_read, created_at
            )
            VALUES (?, ?, ?, ?, ?, 0, ?)
            """, (
                recipient_company_id,
                recipient["username"],
                title,
                message,
                (
                    "/platform/calendar-health/"
                    f"{incident['company_id']}"
                ),
                now_value,
            ))
            chat_id = str(
                recipient["telegram_chat_id"] or ""
            ).strip()

            if chat_id:
                telegram_messages.append((
                    chat_id,
                    f"{title}\n{message}",
                ))

        overdue_items.append({
            "company_id": incident["company_id"],
            "company_name": company_name,
            "incident_type": incident["active_incident"],
            "incident_started_at": incident["incident_started_at"],
            "acknowledged_at": incident[
                "incident_acknowledged_at"
            ],
            "acknowledged_by": incident[
                "incident_acknowledged_by"
            ],
            "assigned_to": (
                incident["incident_assigned_to"]
                or incident["incident_acknowledged_by"]
            ),
            "recovery_age_minutes": recovery_age_minutes,
            "recovery_age_label": recovery_age_label,
            "recipients": len(recipients),
        })

    conn.commit()
    conn.close()

    for chat_id, message in telegram_messages:
        try:
            send_message_to_chat(chat_id, message)
        except Exception:
            pass

    return {
        "checked": len(incidents),
        "overdue": len(overdue_items),
        "notifications_sent": (
            len(overdue_items) * len(recipients)
        ),
        "after_minutes": after_minutes,
        "items": overdue_items,
    }


def open_calendar_scheduler_incident(
    company_id,
    incident_type,
    message,
):
    incident_type = (
        incident_type
        if incident_type in {"error", "stuck", "stale"}
        else "error"
    )
    message = str(message or "")[:500]
    now_value = datetime.now().strftime("%Y-%m-%d %H:%M")
    titles = {
        "error": "Ошибка автоматизации календаря",
        "stuck": "Планировщик календаря не отвечает",
        "stale": "Планировщик календаря давно не запускался",
    }
    title = titles[incident_type]
    conn = connect()
    c = conn.cursor()
    status_row = c.execute("""
    SELECT active_incident
    FROM calendar_plan_scheduler_status
    WHERE company_id=?
    """, (company_id,)).fetchone()

    if not status_row:
        conn.close()
        return 0

    active_incident = str(status_row["active_incident"] or "")

    if active_incident:
        if active_incident == incident_type:
            c.execute("""
            UPDATE calendar_plan_scheduler_status
            SET incident_message=?
            WHERE company_id=?
            """, (
                message,
                company_id,
            ))
            conn.commit()
        conn.close()
        return 0

    recipients = c.execute("""
    SELECT username, telegram_chat_id
    FROM users
    WHERE company_id=?
      AND role='boss'
      AND COALESCE(is_active, 1)=1
    ORDER BY id
    """, (company_id,)).fetchall()

    for recipient in recipients:
        c.execute("""
        INSERT INTO notifications (
            company_id, username, title, message,
            link, is_read, created_at
        )
        VALUES (?, ?, ?, ?, '/calendar/dispatch', 0, ?)
        """, (
            company_id,
            recipient["username"],
            title,
            message,
            now_value,
        ))

    c.execute("""
    UPDATE calendar_plan_scheduler_status
    SET active_incident=?,
        incident_started_at=?,
        incident_message=?,
        last_alerted_at=?,
        incident_acknowledged_at=NULL,
        incident_acknowledged_by=NULL,
        incident_assigned_at=NULL,
        incident_assigned_to=NULL,
        incident_assigned_by=NULL
    WHERE company_id=?
    """, (
        incident_type,
        now_value,
        message,
        now_value,
        company_id,
    ))
    log_calendar_scheduler_incident_event(
        c,
        company_id,
        incident_type,
        "opened",
        message,
        created_at=now_value,
    )
    conn.commit()
    conn.close()

    telegram_text = f"{title}\n{message}"

    for recipient in recipients:
        chat_id = str(recipient["telegram_chat_id"] or "").strip()

        if not chat_id:
            continue

        try:
            send_message_to_chat(chat_id, telegram_text)
        except Exception:
            pass

    return len(recipients)


def reassign_calendar_scheduler_incident(
    company_id,
    actor_username,
    assignee_username,
):
    assignee_username = str(assignee_username or "").strip()

    if not assignee_username:
        return {
            "ok": False,
            "error": "assignee_not_found",
            "message": "Выберите ответственного.",
        }

    now_value = datetime.now().strftime("%Y-%m-%d %H:%M")
    conn = connect()
    begin_locked_transaction(conn, "calendar_scheduler_incidents")
    c = conn.cursor()
    actor = c.execute("""
    SELECT username
    FROM users
    WHERE username=?
      AND role='superadmin'
      AND COALESCE(is_active, 1)=1
    LIMIT 1
    """, (actor_username,)).fetchone()
    assignee = c.execute("""
    SELECT username, company_id, telegram_chat_id
    FROM users
    WHERE username=?
      AND role='superadmin'
      AND COALESCE(is_active, 1)=1
    LIMIT 1
    """, (assignee_username,)).fetchone()
    incident = c.execute("""
    SELECT
        scheduler.active_incident,
        scheduler.incident_acknowledged_at,
        scheduler.incident_acknowledged_by,
        scheduler.incident_assigned_at,
        scheduler.incident_assigned_to,
        scheduler.incident_assigned_by,
        COALESCE(
            companies.name,
            settings.company_name,
            'Компания #' || scheduler.company_id
        ) AS company_name
    FROM calendar_plan_scheduler_status AS scheduler
    LEFT JOIN companies
      ON companies.id=scheduler.company_id
    LEFT JOIN company_settings AS settings
      ON settings.company_id=scheduler.company_id
    WHERE scheduler.company_id=?
    """, (company_id,)).fetchone()

    if not actor:
        conn.close()
        return {
            "ok": False,
            "error": "actor_not_found",
            "message": "Администратор платформы не найден.",
        }

    if not assignee:
        conn.close()
        return {
            "ok": False,
            "error": "assignee_not_found",
            "message": "Ответственный не найден или отключён.",
        }

    if not incident or not str(incident["active_incident"] or ""):
        conn.close()
        return {
            "ok": False,
            "error": "incident_not_found",
            "message": "Активный инцидент не найден.",
        }

    if not incident["incident_acknowledged_at"]:
        conn.close()
        return {
            "ok": False,
            "error": "incident_not_acknowledged",
            "message": "Сначала примите инцидент в работу.",
        }

    previous_assignee = str(
        incident["incident_assigned_to"]
        or incident["incident_acknowledged_by"]
        or ""
    )

    if previous_assignee == assignee_username:
        conn.close()
        return {
            "ok": False,
            "error": "already_assigned",
            "message": "Этот администратор уже назначен.",
        }

    c.execute("""
    UPDATE calendar_plan_scheduler_status
    SET incident_assigned_at=?,
        incident_assigned_to=?,
        incident_assigned_by=?
    WHERE company_id=?
      AND active_incident!=''
      AND incident_acknowledged_at IS NOT NULL
    """, (
        now_value,
        assignee_username,
        actor_username,
        company_id,
    ))

    if c.rowcount == 0:
        conn.close()
        return {
            "ok": False,
            "error": "incident_not_found",
            "message": "Активный инцидент уже закрыт.",
        }

    assignment_message = (
        f"Ответственный изменён: "
        f"{previous_assignee or 'не назначен'} → {assignee_username}."
    )
    log_calendar_scheduler_incident_event(
        c,
        company_id,
        incident["active_incident"],
        "reassigned",
        assignment_message,
        actor_username=actor_username,
        created_at=now_value,
    )
    c.execute("""
    INSERT INTO notifications (
        company_id, username, title, message,
        link, is_read, created_at
    )
    VALUES (?, ?, ?, ?, ?, 0, ?)
    """, (
        int(company_id),
        assignee_username,
        "Назначен календарный инцидент",
        (
            f"Вам передан инцидент: {incident['company_name']} "
            f"(#{company_id}). "
            f"Назначил: {actor_username}."
        ),
        f"/platform/calendar-health/{company_id}",
        now_value,
    ))
    conn.commit()
    conn.close()

    chat_id = str(assignee["telegram_chat_id"] or "").strip()

    if chat_id:
        try:
            send_message_to_chat(
                chat_id,
                (
                    "Назначен календарный инцидент\n"
                    f"{incident['company_name']} (#{company_id}). "
                    f"Назначил: {actor_username}."
                ),
            )
        except Exception:
            pass

    return {
        "ok": True,
        "message": "Ответственный изменён.",
        "assigned_to": assignee_username,
        "assigned_by": actor_username,
    }


def log_calendar_scheduler_incident_event(
    cursor,
    company_id,
    incident_type,
    event_type,
    message,
    actor_username="",
    created_at="",
):
    cursor.execute("""
    INSERT INTO calendar_scheduler_incident_events (
        company_id, incident_type, event_type,
        actor_username, message, created_at
    )
    VALUES (?, ?, ?, ?, ?, ?)
    """, (
        company_id,
        incident_type,
        event_type,
        actor_username,
        str(message or "")[:500],
        created_at or datetime.now().strftime("%Y-%m-%d %H:%M"),
    ))
    cursor.execute("""
    DELETE FROM calendar_scheduler_incident_events
    WHERE company_id=?
      AND id NOT IN (
          SELECT id
          FROM calendar_scheduler_incident_events
          WHERE company_id=?
          ORDER BY id DESC
          LIMIT 200
      )
    """, (
        company_id,
        company_id,
    ))


def trim_calendar_scheduler_runs(company_id, keep=100):
    keep = max(10, min(int(keep or 100), 500))
    conn = connect()
    c = conn.cursor()
    c.execute("""
    DELETE FROM calendar_plan_scheduler_runs
    WHERE company_id=?
      AND id NOT IN (
          SELECT id
          FROM calendar_plan_scheduler_runs
          WHERE company_id=?
          ORDER BY id DESC
          LIMIT ?
      )
    """, (company_id, company_id, keep))
    conn.commit()
    conn.close()


def monitor_calendar_plan_schedulers(
    now_dt=None,
    stale_after_hours=None,
    company_id=None,
    escalation_after_minutes=None,
    recovery_after_minutes=None,
):
    now_dt = now_dt or datetime.now()
    policy = get_calendar_incident_policy(
        stale_hours=stale_after_hours,
        escalation_minutes=escalation_after_minutes,
        recovery_minutes=recovery_after_minutes,
    )
    stale_after_hours = policy["stale_hours"]
    escalation_after_minutes = policy["escalation_minutes"]
    recovery_after_minutes = policy["recovery_minutes"]
    cutoff = now_dt - timedelta(hours=stale_after_hours)
    conn = connect()
    c = conn.cursor()
    companies = c.execute("""
    SELECT
        settings.company_id,
        settings.updated_at,
        MAX(runs.started_at) AS last_scheduler_run
    FROM company_settings AS settings
    LEFT JOIN calendar_plan_scheduler_runs AS runs
      ON runs.company_id=settings.company_id
     AND runs.source='scheduler'
    WHERE (
        COALESCE(settings.calendar_auto_publish, 0)=1
        OR COALESCE(settings.calendar_auto_remind, 0)=1
    )
      AND (? IS NULL OR settings.company_id=?)
    GROUP BY settings.company_id, settings.updated_at
    ORDER BY settings.company_id
    """, (
        company_id,
        company_id,
    )).fetchall()
    conn.close()
    items = []
    alerts_sent = 0

    for company in companies:
        baseline_value = str(
            company["last_scheduler_run"]
            or company["updated_at"]
            or ""
        )

        try:
            baseline_at = datetime.strptime(
                baseline_value,
                "%Y-%m-%d %H:%M",
            )
        except ValueError:
            items.append({
                "company_id": company["company_id"],
                "status": "waiting",
                "last_scheduler_run": baseline_value,
                "alerted": 0,
            })
            continue

        if baseline_at > cutoff:
            items.append({
                "company_id": company["company_id"],
                "status": "healthy",
                "last_scheduler_run": baseline_value,
                "alerted": 0,
            })
            continue

        message = (
            "Запуск автоматизации календаря по расписанию "
            f"не фиксировался более {stale_after_hours} ч. "
            f"Последняя активность: {baseline_value}."
        )
        alerted = open_calendar_scheduler_incident(
            company["company_id"],
            "stale",
            message,
        )
        alerts_sent += alerted
        items.append({
            "company_id": company["company_id"],
            "status": "stale",
            "last_scheduler_run": baseline_value,
            "alerted": alerted,
        })

    escalation = escalate_calendar_scheduler_incidents(
        now_dt=now_dt,
        after_minutes=escalation_after_minutes,
        company_id=company_id,
    )
    recovery_overdue = notify_overdue_calendar_recoveries(
        now_dt=now_dt,
        after_minutes=recovery_after_minutes,
        company_id=company_id,
    )

    return {
        "companies": len(items),
        "healthy": sum(
            1 for item in items if item["status"] == "healthy"
        ),
        "waiting": sum(
            1 for item in items if item["status"] == "waiting"
        ),
        "stale": sum(
            1 for item in items if item["status"] == "stale"
        ),
        "alerts_sent": alerts_sent,
        "escalation": escalation,
        "escalated": escalation["escalated"],
        "escalation_notifications_sent": (
            escalation["notifications_sent"]
        ),
        "recovery_overdue": recovery_overdue,
        "recoveries_overdue": recovery_overdue["overdue"],
        "recovery_overdue_notifications_sent": (
            recovery_overdue["notifications_sent"]
        ),
        "stale_after_hours": stale_after_hours,
        "policy": policy,
        "items": items,
    }


async def run_calendar_plan_scheduler_for_all_companies(now_dt=None):
    conn = connect()
    c = conn.cursor()
    companies = c.execute("""
    SELECT DISTINCT company_settings.company_id
    FROM company_settings
    WHERE COALESCE(company_settings.calendar_auto_publish, 0)=1
       OR COALESCE(company_settings.calendar_auto_remind, 0)=1
    ORDER BY company_settings.company_id
    """).fetchall()
    conn.close()
    results = []

    for company in companies:
        results.append(
            await run_calendar_plan_scheduler(
                company["company_id"],
                now_dt=now_dt,
            )
        )

    return {
        "companies": len(results),
        "changed_days": sum(
            item["changed_days"] for item in results
        ),
        "notifications_sent": sum(
            item["notifications_sent"] for item in results
        ),
        "errors": sum(1 for item in results if item["error"]),
        "results": results,
    }


def run_a3_autonomous_cycle_for_all_companies():
    summary = {
        "companies": 0,
        "skipped": 0,
        "feature_disabled": 0,
        "autonomous_disabled": 0,
        "queued": 0,
        "processed": 0,
        "awaiting_approval": 0,
        "failed": 0,
        "retried_events": 0,
        "retry_requested_events": 0,
        "retry_not_ready_events": 0,
        "retry_failed_events": 0,
        "errors": 0,
        "health_updated": 0,
        "health_errors": 0,
        "items": [],
    }

    conn = connect()
    c = conn.cursor()
    companies = c.execute("""
        SELECT id
        FROM companies
        ORDER BY id
    """).fetchall()
    conn.close()

    for company in companies:
        company_id = company["id"]

        try:
            if not has_feature(company_id, "automation"):
                summary["skipped"] += 1
                summary["feature_disabled"] += 1
                summary["items"].append({
                    "company_id": company_id,
                    "status": "skipped",
                    "reason": "feature_disabled",
                    "message": "Модуль автоматизаций выключен для компании.",
                })
                continue

            if not get_governance_settings(company_id).get(
                "autonomous_enabled",
                1,
            ):
                summary["skipped"] += 1
                summary["autonomous_disabled"] += 1
                summary["items"].append({
                    "company_id": company_id,
                    "status": "skipped",
                    "reason": "autonomous_disabled",
                    "message": "Автономный режим A3 выключен владельцем.",
                })
                continue

            cycle = run_a3_autonomous_cycle(
                company_id=company_id,
                triggered_by="scheduler",
                retry_events_handler=replay_a3_skipped_automation_events,
            )

            if cycle.get("skipped"):
                summary["skipped"] += 1
                summary["items"].append({
                    "company_id": company_id,
                    "status": "skipped",
                    "reason": cycle.get("reason"),
                    "message": "Цикл A3 уже выполняется для компании.",
                })
                continue

            result = cycle["result"]

            summary["companies"] += 1
            summary["queued"] += cycle["queued_from_decisions"]
            summary["processed"] += result.get("processed", 0)
            summary["awaiting_approval"] += result.get(
                "awaiting_approval",
                0,
            )
            summary["failed"] += result.get("failed", 0)
            summary["retried_events"] += result.get("retried_events", 0)
            summary["retry_requested_events"] += result.get(
                "retry_requested_events",
                0,
            )
            summary["retry_not_ready_events"] += result.get(
                "retry_not_ready_events",
                0,
            )
            summary["retry_failed_events"] += result.get(
                "retry_failed_events",
                0,
            )
            summary["items"].append({
                "company_id": company_id,
                "status": "completed",
                "queued": cycle["queued_from_decisions"],
                "processed": result.get("processed", 0),
                "awaiting_approval": result.get("awaiting_approval", 0),
                "failed": result.get("failed", 0),
                "retried_events": result.get("retried_events", 0),
                "retry_requested_events": result.get(
                    "retry_requested_events",
                    0,
                ),
                "retry_not_ready_events": result.get(
                    "retry_not_ready_events",
                    0,
                ),
                "retry_failed_events": result.get(
                    "retry_failed_events",
                    0,
                ),
                "disabled_rules": result.get("disabled_rules", 0),
            })

            health = None
            try:
                health = calculate_system_health(company_id)
                summary["health_updated"] += 1
                summary["items"][-1].update({
                    "health_score": health.get("score"),
                    "health_status": health.get("status"),
                })
            except Exception:
                summary["health_errors"] += 1
                summary["items"][-1]["health_status"] = "unavailable"
                record_a3_scheduler_timeline(
                    company_id=company_id,
                    severity="warning",
                    title="Не удалось обновить состояние A3",
                    message=(
                        "Цикл автоматизации завершён, но оценка "
                        "состояния A3 временно недоступна."
                    ),
                )

            notify_a3_approval_required(
                company_id,
                result.get("awaiting_approval", 0),
            )

            severity = "warning" if (
                result.get("failed", 0)
                or result.get("awaiting_approval", 0)
                or result.get("retry_not_ready_events", 0)
                or result.get("retry_failed_events", 0)
            ) else "info"
            record_a3_scheduler_timeline(
                company_id=company_id,
                severity=severity,
                title="Фоновый цикл A3 завершён",
                message=(
                    f"Добавлено в очередь: {cycle['queued_from_decisions']}; "
                    f"выполнено: {result.get('processed', 0)}; "
                    f"повторно выполнено событий: {result.get('retried_events', 0)}; "
                    f"условия ещё не готовы: {result.get('retry_not_ready_events', 0)}; "
                    f"ошибок повтора: {result.get('retry_failed_events', 0)}; "
                    f"ждут подтверждения: {result.get('awaiting_approval', 0)}; "
                    f"ошибок: {result.get('failed', 0)}"
                ),
            )
            cycle_run_id = record_a3_cycle_result(
                company_id=company_id,
                cycle=cycle,
                health=health,
                triggered_by="scheduler",
                message="Фоновый цикл A3 завершён.",
            )

            if cycle_run_id:
                notify_a3_scheduler_reliability(company_id)
        except Exception:
            summary["errors"] += 1
            summary["items"].append({
                "company_id": company_id,
                "status": "error",
                "message": "Фоновый запуск не завершился. Проверьте журнал A3.",
            })

            record_a3_scheduler_timeline(
                company_id=company_id,
                severity="error",
                title="Ошибка фонового цикла A3",
                message="Фоновый запуск не завершился. Проверьте состояние автоматизации.",
            )
            cycle_run_id = record_a3_cycle_result(
                company_id=company_id,
                status="error",
                triggered_by="scheduler",
                message="Фоновый цикл A3 завершился с ошибкой.",
            )

            if cycle_run_id:
                notify_a3_scheduler_reliability(company_id)

    return summary


def run_a3_scheduler_watchdog_for_all_companies(
    now=None,
    notifier=None,
    report=None,
    status_recorder=None,
    history_recorder=None,
    incident_syncer=None,
    followup_monitor_runner=None,
):
    watchdog_report = report or get_a3_scheduler_watchdog_report(now=now)
    notify = notifier or notify_a3_scheduler_reliability
    watchdog_report.update({
        "alerts_sent": 0,
        "recoveries_sent": 0,
        "telegram_sent": 0,
        "suppressed": 0,
        "notification_errors": 0,
    })

    for item in watchdog_report.get("items", []):
        if not item.get("alertable"):
            continue

        try:
            notification = notify(
                item["company_id"],
                reliability=item.get("reliability") or {},
                now=now,
            )
        except Exception:
            notification = {
                "created": False,
                "reason": "notification_failed",
            }

        item["notification"] = notification

        if notification.get("created"):
            if notification.get("reason") == "recovery_created":
                watchdog_report["recoveries_sent"] += 1
            else:
                watchdog_report["alerts_sent"] += 1

            if notification.get("telegram_sent"):
                watchdog_report["telegram_sent"] += 1
        elif notification.get("reason") in {
            "notification_failed",
            "reliability_unavailable",
        }:
            watchdog_report["notification_errors"] += 1
        else:
            watchdog_report["suppressed"] += 1

    recorder = status_recorder or save_a3_scheduler_watchdog_status
    try:
        watchdog_report["heartbeats_saved"] = recorder(
            watchdog_report,
            checked_at=now,
        )
        watchdog_report["heartbeat_error"] = ""
    except Exception:
        watchdog_report["heartbeats_saved"] = 0
        watchdog_report["heartbeat_error"] = (
            "Не удалось сохранить состояние контрольной проверки."
        )

    sync_incidents = incident_syncer or sync_a3_platform_incidents
    try:
        watchdog_report["incidents"] = sync_incidents(
            watchdog_report,
            now=now,
        )
        watchdog_report["incident_error"] = watchdog_report[
            "incidents"
        ].get("escalation_error", "")
    except Exception:
        watchdog_report["incidents"] = {
            "opened": 0,
            "repeated": 0,
            "resolved": 0,
            "notifications_created": 0,
            "telegram_sent": 0,
            "items_checked": 0,
            "escalated": 0,
            "escalation_error": "",
        }
        watchdog_report["incident_error"] = (
            "Не удалось синхронизировать инциденты A3."
        )

    monitor_followups = (
        followup_monitor_runner or run_a3_incident_followup_monitor
    )
    try:
        watchdog_report["followup_monitor"] = monitor_followups(now=now)
        watchdog_report["followup_monitor_error"] = ""
    except Exception:
        watchdog_report["followup_monitor"] = {
            "checked": 0,
            "due_soon": 0,
            "overdue": 0,
            "notified_actions": 0,
            "notifications_created": 0,
            "telegram_sent": 0,
            "suppressed": 0,
        }
        watchdog_report["followup_monitor_error"] = (
            "Не удалось проверить сроки контрольных мер A3."
        )

    record_history = history_recorder or record_a3_scheduler_watchdog_run
    try:
        watchdog_report["history_run_id"] = record_history(
            watchdog_report,
            checked_at=now,
        )
        watchdog_report["history_error"] = ""
    except Exception:
        watchdog_report["history_run_id"] = None
        watchdog_report["history_error"] = (
            "Не удалось сохранить историю контрольного запуска."
        )

    return watchdog_report


def a3_api_error(error, status_code, message=None):

    return JSONResponse(
        {
            "ok": False,
            "error": error,
            "message": message or A3_API_ERROR_MESSAGES.get(error, "Ошибка A3"),
        },
        status_code=status_code,
    )


def a3_result_error_response(result, status_code):
    payload = dict(result)
    error = payload.get("error")
    payload.setdefault("message", A3_API_ERROR_MESSAGES.get(error, "Ошибка A3"))

    return JSONResponse(payload, status_code=status_code)


@app.get("/api/a3/system-health")
def api_a3_system_health(request: Request):
    company_id = get_a3_company_id(request)

    if not company_id:
        return a3_api_error("forbidden", 403)

    return calculate_system_health(company_id)


@app.get("/api/a3/system-health/history")
def api_a3_system_health_history(request: Request):
    company_id = get_a3_company_id(request)

    if not company_id:
        return a3_api_error("forbidden", 403)

    return {
        "items": get_system_health_history(company_id, limit=30)
    }


@app.get("/api/a3/automation-analytics")
def api_a3_automation_analytics(request: Request):
    company_id = get_a3_company_id(request)

    if not company_id:
        return a3_api_error("forbidden", 403)

    return get_automation_analytics(company_id)


@app.get("/api/a3/unhealthy-rules")
def api_a3_unhealthy_rules(request: Request):
    company_id = get_a3_company_id(request)

    if not company_id:
        return a3_api_error("forbidden", 403)

    items = get_unhealthy_rules(company_id)

    return {
        "count": len(items),
        "items": items,
    }



@app.get("/api/a3/operations-insights")
def api_a3_operations_insights(request: Request):
    company_id = get_a3_company_id(request)

    if not company_id:
        return a3_api_error("forbidden", 403)

    return get_operations_insights(company_id)


@app.post("/api/a3/self-healing/run")
def api_a3_self_healing_run(request: Request):
    company_id = get_a3_owner_company_id(request)

    if not company_id:
        return a3_api_error("forbidden", 403)

    result = run_self_healing_cycle(
        company_id=company_id,
        retry_events_handler=replay_a3_skipped_automation_events,
    )
    health = None

    try:
        health = calculate_system_health(company_id)
    except Exception:
        health = None

    return {
        "ok": True,
        "result": result,
        "health": health,
    }


@app.get("/api/a3/recovery-history")
def api_a3_recovery_history(request: Request):
    company_id = get_a3_company_id(request)

    if not company_id:
        return a3_api_error("forbidden", 403)

    return {
        "items": get_recovery_history(company_id, limit=20)
    }


@app.get("/api/a3/scheduler-readiness")
def api_a3_scheduler_readiness(request: Request):
    company_id = get_a3_company_id(request)

    if not company_id:
        return a3_api_error("forbidden", 403)

    governance = get_governance_settings(company_id)

    return get_a3_scheduler_readiness(
        company_id=company_id,
        cron_configured=bool(
            (os.getenv("AUTOMATION_CRON_SECRET") or "").strip()
        ),
        automation_enabled=has_feature(company_id, "automation"),
        autonomous_enabled=bool(governance.get("autonomous_enabled", 1)),
    )


@app.get("/api/a3/scheduler-watchdog-status")
def api_a3_scheduler_watchdog_status(request: Request):
    company_id = get_a3_company_id(request)

    if not company_id:
        return a3_api_error("forbidden", 403)

    return get_a3_scheduler_watchdog_status(company_id)


@app.get("/api/a3/autonomous-cycle-history")
def api_a3_autonomous_cycle_history(request: Request):
    company_id = get_a3_company_id(request)

    if not company_id:
        return a3_api_error("forbidden", 403)

    query_params = getattr(request, "query_params", {}) or {}
    status_filter = normalize_a3_cycle_status_filter(
        query_params.get("status") or "all"
    )

    try:
        limit = max(
            1,
            min(
                A3_CYCLE_HISTORY_LIMIT,
                int(query_params.get("limit") or 20),
            ),
        )
    except (TypeError, ValueError):
        limit = 20

    items = get_a3_cycle_history(
        company_id,
        limit=limit,
        status_filter=status_filter,
    )

    return {
        "count": len(items),
        "status_filter": status_filter,
        "status_filter_label": a3_cycle_status_filter_label(status_filter),
        "reliability": get_a3_cycle_reliability(company_id),
        "summary": get_a3_cycle_summary(company_id),
        "items": items,
    }


@app.get("/api/a3/autonomous-cycle-history/export")
def api_a3_autonomous_cycle_history_export(request: Request):
    company_id = get_a3_company_id(request)

    if not company_id:
        return a3_api_error("forbidden", 403)

    query_params = getattr(request, "query_params", {}) or {}
    status_filter = normalize_a3_cycle_status_filter(
        query_params.get("status") or "all"
    )
    items = get_a3_cycle_history(
        company_id,
        limit=A3_CYCLE_HISTORY_EXPORT_LIMIT,
        status_filter=status_filter,
    )

    output = io.StringIO()
    output.write("\ufeff")
    writer = csv.writer(output)
    writer.writerow([
        "Фильтр",
        a3_cycle_status_filter_label(status_filter),
    ])
    writer.writerow(["Количество запусков", len(items)])
    writer.writerow([])
    writer.writerow([
        "Номер запуска",
        "Результат",
        "Источник",
        "Решений",
        "Поставлено в очередь",
        "Выполнено действий",
        "Ждут подтверждения",
        "Ошибок действий",
        "Повторено событий",
        "Событий не готовы",
        "Ошибок повтора",
        "Оценка A3",
        "Состояние A3",
        "Длительность, мс",
        "Сообщение",
        "Дата",
    ])

    for item in items:
        writer.writerow([
            item.get("id"),
            item.get("status_label") or item.get("status"),
            item.get("source_label") or item.get("triggered_by"),
            item.get("decision_count") or 0,
            item.get("queued_actions") or 0,
            item.get("processed_actions") or 0,
            item.get("awaiting_approval") or 0,
            item.get("failed_actions") or 0,
            item.get("retried_events") or 0,
            item.get("retry_not_ready_events") or 0,
            item.get("retry_failed_events") or 0,
            item.get("health_score") if item.get("health_score") is not None else "",
            item.get("health_status") or "",
            item.get("duration_ms") or 0,
            item.get("message") or "",
            item.get("created_at") or "",
        ])

    return Response(
        output.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": (
                "attachment; "
                f'filename="a3_cycle_history_{status_filter}.csv"'
            ),
        },
    )


@app.get("/api/a3/ops-timeline")
def api_a3_ops_timeline(request: Request):
    company_id = get_a3_company_id(request)

    if not company_id:
        return a3_api_error("forbidden", 403)

    return {
        "items": get_ops_timeline(company_id, limit=50)
    }


@app.get("/api/a3/predictive-signals")
def api_a3_predictive_signals(request: Request):
    company_id = get_a3_company_id(request)

    if not company_id:
        return a3_api_error("forbidden", 403)

    return get_predictive_signals(company_id)


@app.get("/api/a3/decision-engine")
def api_a3_decision_engine(request: Request):
    company_id = get_a3_company_id(request)

    if not company_id:
        return a3_api_error("forbidden", 403)

    return get_decision_engine(company_id)


@app.get("/api/a3/workflow/rules/{rule_id}/graph")
def api_a3_workflow_rule_graph(request: Request, rule_id: int):
    company_id = get_a3_company_id(request)

    if not company_id:
        return a3_api_error("forbidden", 403)

    graph = get_rule_workflow_graph(company_id, rule_id)

    if not graph:
        return a3_api_error("not_found", 404, "Цепочка не найдена")

    return graph


@app.get("/api/a3/workflow/rules/{rule_id}/debug")
def api_a3_workflow_rule_debug(request: Request, rule_id: int):
    company_id = get_a3_company_id(request)

    if not company_id:
        return a3_api_error("forbidden", 403)

    debug = get_rule_workflow_debug(company_id, rule_id)

    if not debug:
        return a3_api_error("not_found", 404, "Цепочка не найдена")

    return debug


@app.get("/api/a3/workflows/graph")
def api_a3_workflows_graph(request: Request):
    company_id = get_a3_company_id(request)

    if not company_id:
        return a3_api_error("forbidden", 403)

    return get_company_workflow_graphs(company_id, limit=50)


@app.get("/api/a3/autonomous-actions")
def api_a3_autonomous_actions(request: Request):
    company_id = get_a3_company_id(request)

    if not company_id:
        return a3_api_error("forbidden", 403)

    return {
        "items": get_autonomous_actions(company_id, limit=50),
        "summary": get_autonomous_action_summary(company_id),
    }


@app.post("/api/a3/autonomous-actions/process")
def api_a3_process_autonomous_actions(request: Request):
    company_id = get_a3_owner_company_id(request)

    if not company_id:
        return a3_api_error("forbidden", 403)

    cycle = run_a3_autonomous_cycle(
        company_id=company_id,
        triggered_by=get_user(request) or "system",
        retry_events_handler=replay_a3_skipped_automation_events,
    )
    result = cycle["result"]

    if cycle.get("skipped"):
        return {
            "ok": True,
            "skipped": True,
            "reason": cycle.get("reason"),
            "message": "Цикл A3 уже выполняется. Дождитесь его завершения.",
            "result": result,
        }

    notify_a3_approval_required(
        company_id,
        result.get("awaiting_approval", 0),
    )

    try:
        health = calculate_system_health(company_id)
    except Exception:
        health = None

    record_a3_cycle_result(
        company_id=company_id,
        cycle=cycle,
        health=health,
        message="Ручной цикл A3 завершён.",
    )

    return {
        "ok": True,
        "decision_count": cycle["decision_count"],
        "queued_from_decisions": cycle["queued_from_decisions"],
        "max_actions_per_cycle": cycle["max_actions_per_cycle"],
        "pending_action_count": cycle["pending_action_count"],
        "queue_capacity_remaining": cycle["queue_capacity_remaining"],
        "health": health,
        "result": result,
    }


@app.post("/api/a3/autonomous-actions/request-approval")
async def api_a3_request_autonomous_action_approval(request: Request):
    company_id = get_a3_company_id(request)

    if not company_id:
        return a3_api_error("forbidden", 403)

    try:
        payload = await request.json()
    except Exception:
        payload = {}

    action_type = payload.get("action_type")
    target_type = payload.get("target_type")
    target_id = payload.get("target_id")

    if (
        action_type != "disable_rule"
        or target_type != "automation_rule"
        or target_id is None
        or target_id == ""
    ):
        return a3_api_error("unsupported_action", 400)

    try:
        target_id = int(target_id)
    except Exception:
        return a3_api_error("invalid_target_id", 400)

    if target_id <= 0:
        return a3_api_error("invalid_target_id", 400)

    conn = connect()
    c = conn.cursor()

    rule = c.execute("""
    SELECT id
    FROM automation_rules
    WHERE company_id=?
      AND id=?
    """, (
        company_id,
        target_id,
    )).fetchone()

    conn.close()

    if not rule:
        return a3_api_error("rule_not_found", 404)

    request_reason = str(
        payload.get("reason") or "Запрошено из диагностики цепочки A3"
    ).strip()[:500]

    result = enqueue_autonomous_action(
        company_id=company_id,
        action_type=action_type,
        target_type=target_type,
        target_id=target_id,
        payload_json=json.dumps({
            "requested_by": get_user(request) or "system",
            "reason": request_reason,
        }, ensure_ascii=False),
        initial_status="awaiting_approval",
    )

    if not result.get("queued"):
        reason = result.get("reason")

        return {
            "ok": False,
            "queued": False,
            "reason": reason,
            "message": A3_API_ERROR_MESSAGES.get(
                reason,
                "Не удалось отправить действие на подтверждение",
            ),
        }

    notify_a3_approval_required(
        company_id,
        1,
    )
    create_ops_timeline_event(
        company_id=company_id,
        severity="warning",
        event_type="approval_requested",
        title="Запрошено подтверждение отключения правила",
        message=(
            "Критическое действие ожидает решения владельца. "
            f"Правило: #{target_id}."
        ),
        source="manual",
        target_type="automation_rule",
        target_id=target_id,
        cooldown_minutes=5,
    )

    return {
        "ok": True,
        "queued": True,
        "process_result": {
            "processed": 0,
            "awaiting_approval": 1,
            "triggered_by": get_user(request) or "system",
        },
    }


@app.get("/api/a3/governance-settings")
def api_a3_governance_settings(request: Request):
    company_id = get_a3_company_id(request)

    if not company_id:
        return a3_api_error("forbidden", 403)

    return ensure_governance_settings(company_id)


@app.post("/api/a3/governance-settings/update")
async def api_a3_governance_settings_update(request: Request):
    company_id = get_a3_owner_company_id(request)

    if not company_id:
        return a3_api_error("forbidden", 403)

    payload = {}

    try:
        payload = await request.json()
    except Exception:
        pass

    current_governance = get_governance_settings(company_id)

    try:
        autonomous_enabled = parse_a3_governance_bool(payload.get(
            "autonomous_enabled",
            current_governance.get("autonomous_enabled", 1),
        ))
        require_critical_approval = parse_a3_governance_bool(payload.get(
            "require_critical_approval",
            current_governance.get("require_critical_approval", 1),
        ))
        confidence_threshold = int(payload.get(
            "confidence_threshold",
            current_governance.get("confidence_threshold", 70),
        ))
        max_actions_per_cycle = int(payload.get(
            "max_actions_per_cycle",
            current_governance.get("max_actions_per_cycle", 20),
        ))
    except Exception:
        return a3_api_error("invalid_governance_settings", 400)

    if (
        confidence_threshold < 0
        or confidence_threshold > 100
        or max_actions_per_cycle < 1
        or max_actions_per_cycle > 100
    ):
        return a3_api_error("invalid_governance_settings", 400)

    protected_rules_json = current_governance.get("protected_rules_json") or "[]"

    if "protected_rules" in payload:
        try:
            protected_rule_ids = [
                int(rule_id)
                for rule_id in payload.get("protected_rules") or []
            ]
        except Exception:
            return a3_api_error("invalid_protected_rules", 400)

        if protected_rule_ids:
            placeholders = ",".join("?" for _ in protected_rule_ids)
            conn = connect()
            c = conn.cursor()
            rows = c.execute(f"""
            SELECT id
            FROM automation_rules
            WHERE company_id=?
              AND id IN ({placeholders})
            """, (
                company_id,
                *protected_rule_ids,
            )).fetchall()
            conn.close()

            existing_rule_ids = {row["id"] for row in rows}

            if existing_rule_ids != set(protected_rule_ids):
                return a3_api_error("invalid_protected_rules", 400)

        protected_rules_json = json.dumps(protected_rule_ids)

    return save_governance_settings(
        company_id=company_id,
        autonomous_enabled=autonomous_enabled,
        max_actions_per_cycle=max_actions_per_cycle,
        require_critical_approval=require_critical_approval,
        confidence_threshold=confidence_threshold,
        protected_rules_json=protected_rules_json,
    )


@app.post("/api/a3/autonomous-actions/{action_id}/approve")
async def api_a3_approve_autonomous_action(request: Request, action_id: int):
    company_id = get_a3_owner_company_id(request)

    if not company_id:
        return a3_api_error("forbidden", 403)

    try:
        payload = await request.json()
    except Exception:
        payload = {}

    decided_by = get_user(request) or "system"
    result = approve_autonomous_action(
        company_id=company_id,
        action_id=action_id,
        decided_by=decided_by,
        reason=payload.get("reason"),
    )

    if not result.get("ok"):
        if result.get("error") in {"unsupported_action", "protected_rule"}:
            return a3_result_error_response(result, 400)

        return a3_result_error_response(result, 404)

    return result


@app.post("/api/a3/autonomous-actions/approve-safe")
def api_a3_approve_safe_autonomous_actions(request: Request):
    company_id = get_a3_owner_company_id(request)

    if not company_id:
        return a3_api_error("forbidden", 403)

    decided_by = get_user(request) or "system"

    return approve_safe_autonomous_actions(
        company_id=company_id,
        decided_by=decided_by,
    )


@app.post("/api/a3/autonomous-actions/{action_id}/reject")
async def api_a3_reject_autonomous_action(request: Request, action_id: int):
    company_id = get_a3_owner_company_id(request)

    if not company_id:
        return a3_api_error("forbidden", 403)

    try:
        payload = await request.json()
    except Exception:
        payload = {}

    decided_by = get_user(request) or "system"
    result = reject_autonomous_action(
        company_id=company_id,
        action_id=action_id,
        decided_by=decided_by,
        reason=payload.get("reason"),
    )

    if not result.get("ok"):
        return a3_result_error_response(result, 404)

    return result


@app.post("/api/a3/autonomous-actions/reject-unsafe")
def api_a3_reject_unsafe_autonomous_actions(request: Request):
    company_id = get_a3_owner_company_id(request)

    if not company_id:
        return a3_api_error("forbidden", 403)

    decided_by = get_user(request) or "system"

    return reject_unsafe_autonomous_actions(
        company_id=company_id,
        decided_by=decided_by,
    )


@app.get("/api/a3/approval-queue")
def api_a3_approval_queue(request: Request):
    company_id = get_a3_company_id(request)

    if not company_id:
        return a3_api_error("forbidden", 403)

    items = get_approval_queue(company_id)
    summary = {
        "total": len(items),
        "safe": 0,
        "unsafe": 0,
        "protected": 0,
        "missing_target": 0,
        "unsupported": 0,
        "attention": 0,
        "overdue": 0,
    }

    for item in items:
        if item.get("approval_safety") == "safe":
            summary["safe"] += 1
        else:
            summary["unsafe"] += 1

        reason = item.get("approval_safety_reason")

        if reason == "protected_rule":
            summary["protected"] += 1
        elif reason == "missing_target":
            summary["missing_target"] += 1
        elif reason == "unsupported_action":
            summary["unsupported"] += 1

        if item.get("approval_urgency") == "attention":
            summary["attention"] += 1
        elif item.get("approval_urgency") == "overdue":
            summary["overdue"] += 1

    summary.update({
        "total_label": f"Всего: {summary['total']}",
        "safe_label": f"Можно подтвердить: {summary['safe']}",
        "unsafe_label": f"Небезопасные: {summary['unsafe']}",
        "protected_label": f"Защищённые: {summary['protected']}",
        "missing_target_label": f"Цель не найдена: {summary['missing_target']}",
        "unsupported_label": f"Неподдерживаемые: {summary['unsupported']}",
        "attention_label": f"Ждут больше 6 часов: {summary['attention']}",
        "overdue_label": f"Ждут больше суток: {summary['overdue']}",
    })

    return {
        "count": len(items),
        "summary": summary,
        "items": items,
    }


@app.get("/api/a3/approval-history")
def api_a3_approval_history(request: Request):
    company_id = get_a3_company_id(request)

    if not company_id:
        return a3_api_error("forbidden", 403)

    filters = get_a3_approval_history_filters(request)

    items = get_approval_history(
        company_id,
        decision_filter=filters["decision"],
        date_from=filters["date_from"],
        date_to=filters["date_to"],
        action_type_filter=filters["action_type"],
        target_type_filter=filters["target_type"],
        decided_by_filter=filters["decided_by"],
        target_id_filter=filters["target_id"],
    )
    summary = build_a3_approval_history_summary(items, filters)

    return {
        "count": len(items),
        "summary": summary,
        "items": items,
    }


@app.get("/api/a3/approval-history/export")
def api_a3_approval_history_export(request: Request):
    company_id = get_a3_company_id(request)

    if not company_id:
        return a3_api_error("forbidden", 403)

    filters = get_a3_approval_history_filters(request)
    items = get_approval_history(
        company_id,
        decision_filter=filters["decision"],
        date_from=filters["date_from"],
        date_to=filters["date_to"],
        action_type_filter=filters["action_type"],
        target_type_filter=filters["target_type"],
        decided_by_filter=filters["decided_by"],
        target_id_filter=filters["target_id"],
    )

    output = io.StringIO()
    output.write("\ufeff")
    writer = csv.writer(output)
    writer.writerows(
        build_a3_approval_export_filter_rows(
            filters,
            items_count=len(items),
        )
    )
    writer.writerow([
        "Номер решения",
        "Номер действия",
        "Решение",
        "Кто решил",
        "Причина",
        "Кто запросил",
        "Основание запроса",
        "Тип действия",
        "Тип цели",
        "Номер цели",
        "Название цели",
        "Цель активна",
        "Дата",
    ])

    for item in items:
        writer.writerow([
            item.get("id"),
            item.get("action_id"),
            item.get("decision_label") or item.get("decision"),
            item.get("decided_by_label") or item.get("decided_by"),
            item.get("reason") or "",
            item.get("requested_by_label") or item.get("requested_by") or "",
            item.get("request_reason") or "",
            item.get("action_label") or item.get("action_type"),
            item.get("target_label") or item.get("target_type"),
            item.get("target_id"),
            item.get("target_name") or "",
            "Да" if item.get("target_active") else "Нет",
            item.get("created_at") or "",
        ])

    filename = build_a3_approval_export_filename(filters)
    return Response(
        output.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
        },
    )


def get_a3_approval_decision_filter(request: Request) -> str:
    query_params = getattr(request, "query_params", {}) or {}
    decision_filter = query_params.get("decision") or "all"

    if decision_filter not in {"all", "approved", "rejected"}:
        return "all"

    return decision_filter


def build_a3_approval_export_filename(filters):
    filename_parts = [
        "a3_approval_history",
        filters["decision"],
        filters["action_type"],
    ]

    if filters["target_type"] != "all":
        filename_parts.append(filters["target_type"])

    return "_".join(filename_parts) + ".csv"


def build_a3_approval_export_filter_rows(filters, items_count=None):
    active_filter_labels = build_a3_approval_active_filter_labels(filters)
    rows = [
        ["Фильтры экспорта"],
        [
            "Записей",
            items_count if items_count is not None else "Не считалось",
        ],
        [
            "Лимит",
            f"Последние {APPROVAL_HISTORY_LIMIT} решений",
        ],
        [
            "Активных фильтров",
            len(active_filter_labels),
        ],
    ]

    if active_filter_labels:
        for label in active_filter_labels:
            rows.append(["Активный фильтр", label])
    else:
        rows.append(["Активные фильтры", "Нет"])

    rows.extend([
        [
            "Решение",
            get_a3_approval_decision_label(filters["decision"]),
        ],
        [
            "Тип действия",
            (
                "Все действия"
                if filters["action_type"] == "all"
                else action_label(filters["action_type"])
            ),
        ],
        [
            "Тип цели",
            (
                "Все цели"
                if filters["target_type"] == "all"
                else target_label(filters["target_type"])
            ),
        ],
        [
            "Кто решил",
            get_a3_approval_actor_label(filters["decided_by"]),
        ],
        [
            "Номер цели",
            filters["target_id"] or "Все",
        ],
        [
            "Период",
            get_a3_approval_period_label(
                filters["date_from"],
                filters["date_to"],
            ),
        ],
        [],
    ])

    return rows


def build_a3_approval_history_summary(items, filters):
    summary = {
        "total": len(items),
        "approved": 0,
        "rejected": 0,
        "history_limit": APPROVAL_HISTORY_LIMIT,
        "history_limit_label": f"Последние {APPROVAL_HISTORY_LIMIT} решений",
        "filter": filters["decision"],
        "date_from": filters["date_from"],
        "date_to": filters["date_to"],
        "period_label": get_a3_approval_period_label(
            filters["date_from"],
            filters["date_to"],
        ),
        "action_type": filters["action_type"],
        "action_label": (
            "Все действия"
            if filters["action_type"] == "all"
            else action_label(filters["action_type"])
        ),
        "target_type": filters["target_type"],
        "target_type_label": (
            "Все цели"
            if filters["target_type"] == "all"
            else target_label(filters["target_type"])
        ),
        "decided_by": filters["decided_by"],
        "decided_by_label": get_a3_approval_actor_label(
            filters["decided_by"]
        ),
        "target_id": filters["target_id"],
    }
    active_filter_labels = build_a3_approval_active_filter_labels(filters)
    summary["active_filters_count"] = len(active_filter_labels)
    summary["active_filter_labels"] = active_filter_labels

    for item in items:
        if item.get("decision") == "approved":
            summary["approved"] += 1
        elif item.get("decision") == "rejected":
            summary["rejected"] += 1

    return summary


def build_a3_approval_active_filter_labels(filters):
    labels = []

    if filters["decision"] != "all":
        labels.append(
            f"Решение: {get_a3_approval_decision_label(filters['decision'])}"
        )

    if filters["action_type"] != "all":
        labels.append(f"Действие: {action_label(filters['action_type'])}")

    if filters["target_type"] != "all":
        labels.append(f"Тип цели: {target_label(filters['target_type'])}")

    if filters["decided_by"]:
        labels.append(
            f"Кто решил: {get_a3_approval_actor_label(filters['decided_by'])}"
        )

    if filters["target_id"]:
        labels.append(f"Цель: #{filters['target_id']}")

    if filters["date_from"] or filters["date_to"]:
        period_label = get_a3_approval_period_label(
            filters["date_from"],
            filters["date_to"],
        )
        if period_label == "Выбранный период":
            labels.append(
                "Период: "
                f"{filters['date_from'] or 'начало'} - "
                f"{filters['date_to'] or 'сегодня'}"
            )
        else:
            labels.append(f"Период: {period_label}")

    return labels


def get_a3_approval_decision_label(value):
    return {
        "all": "Все решения",
        "approved": "Одобренные",
        "rejected": "Отклонённые",
    }.get(value or "all", "Все решения")


def get_a3_approval_history_filters(request: Request) -> dict:
    query_params = getattr(request, "query_params", {}) or {}
    date_from = get_a3_approval_date_filter_value(
        query_params.get("date_from")
    )
    date_to = get_a3_approval_date_filter_value(
        query_params.get("date_to")
    )
    date_from, date_to = normalize_a3_approval_date_range(
        date_from,
        date_to,
    )

    return {
        "decision": get_a3_approval_decision_filter(request),
        "action_type": get_a3_approval_action_type_filter_value(
            query_params.get("action_type")
        ),
        "target_type": get_a3_approval_target_type_filter_value(
            query_params.get("target_type")
        ),
        "decided_by": get_a3_approval_actor_filter_value(
            query_params.get("decided_by")
        ),
        "target_id": get_a3_approval_target_id_filter_value(
            query_params.get("target_id")
        ),
        "date_from": date_from,
        "date_to": date_to,
    }


def get_a3_approval_date_filter_value(value):
    value = str(value or "").strip()

    if not value:
        return None

    try:
        datetime.strptime(value, "%Y-%m-%d")
    except Exception:
        return None

    return value


def normalize_a3_approval_date_range(date_from, date_to):
    if not date_from or not date_to:
        return date_from, date_to

    try:
        from_date = datetime.strptime(date_from, "%Y-%m-%d").date()
        to_date = datetime.strptime(date_to, "%Y-%m-%d").date()
    except Exception:
        return date_from, date_to

    if from_date <= to_date:
        return date_from, date_to

    return date_to, date_from


def get_a3_approval_period_label(date_from, date_to):
    if not date_from and not date_to:
        return "За всё время"

    today = datetime.now().date()

    if date_from and date_to:
        try:
            from_date = datetime.strptime(date_from, "%Y-%m-%d").date()
            to_date = datetime.strptime(date_to, "%Y-%m-%d").date()
        except Exception:
            return "Выбранный период"

        if from_date == today and to_date == today:
            return "Сегодня"

        if to_date == today:
            days = (to_date - from_date).days + 1

            if days in {7, 30}:
                return f"Последние {days} дней"

        return "Выбранный период"

    if date_from:
        return f"С {date_from}"

    return f"До {date_to}"


def get_a3_approval_action_type_filter_value(value):
    value = str(value or "all").strip()

    if value not in {"all", "disable_rule", "retry_events", "recovery_cycle"}:
        return "all"

    return value


def get_a3_approval_target_type_filter_value(value):
    value = str(value or "all").strip()

    if value not in {
        "all",
        "automation_rule",
        "automation_event",
        "autonomous_action",
    }:
        return "all"

    return value


def get_a3_approval_actor_filter_value(value):
    value = str(value or "").strip()[:80]

    if not value:
        return None

    cleaned = "".join(
        char
        for char in value
        if char.isalnum() or char in "._-@"
    )

    if cleaned != value:
        return None

    return cleaned


def get_a3_approval_actor_label(value):
    if not value:
        return "Все пользователи"

    if value == "system":
        return "Система"

    return value


def get_a3_approval_target_id_filter_value(value):
    value = str(value or "").strip()

    if not value:
        return None

    try:
        target_id = int(value)
    except Exception:
        return None

    if target_id <= 0:
        return None

    return target_id


@app.post("/api/a3/ops-timeline")
async def api_a3_create_ops_timeline_event(request: Request):
    company_id = get_a3_company_id(request)

    if not company_id:
        return a3_api_error("forbidden", 403)

    payload = await request.json()

    result = create_ops_timeline_event(
        company_id=company_id,
        event_type=payload.get("event_type", "manual"),
        severity=payload.get("severity", "info"),
        title=payload.get("title", "Событие A3"),
        message=payload.get("message", ""),
        target_type=payload.get("target_type"),
        target_id=payload.get("target_id"),
    )

    return {
        "ok": True,
        "result": result,
    }


@app.get("/api/a3/workflow/rules/{rule_id}/timeline")
def api_a3_workflow_timeline(
    request: Request,
    rule_id: int,
    status_filter: str = "all",
    limit: int = 20,
):
    company_id = get_a3_company_id(request)

    if not company_id:
        return a3_api_error("forbidden", 403)

    timeline = get_workflow_timeline(
        company_id=company_id,
        rule_id=rule_id,
        limit=limit,
        status_filter=status_filter,
    )

    if not timeline:
        return a3_api_error("not_found", 404, "Цепочка не найдена")

    return {
        "ok": True,
        "timeline": timeline,
    }
