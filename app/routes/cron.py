"""Scheduled cron endpoints protected by AUTOMATION_CRON_SECRET."""

import hmac
import os
from uuid import uuid4

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from app.services.billing import create_platform_billing_reminders

router = APIRouter()

@router.post("/automation/cron/platform-billing-reminders")
async def run_platform_billing_reminders_cron(request: Request):
    cron_secret = (os.getenv("AUTOMATION_CRON_SECRET") or "").strip()

    if not cron_secret:
        return JSONResponse(
            {
                "ok": False,
                "error": "AUTOMATION_CRON_SECRET is not configured",
            },
            status_code=503,
        )

    token = (
        request.headers.get("x-automation-secret")
        or request.query_params.get("token")
        or ""
    ).strip()

    if not token or not hmac.compare_digest(token, cron_secret):
        return JSONResponse(
            {"ok": False, "error": "forbidden"},
            status_code=403,
        )

    return JSONResponse({
        "ok": True,
        "summary": create_platform_billing_reminders("all"),
    })


@router.post("/automation/cron/ai-digest")
async def run_ai_digest_scheduler_cron(request: Request):

    cron_secret = (os.getenv("AUTOMATION_CRON_SECRET") or "").strip()

    if not cron_secret:
        return JSONResponse(
            {"ok": False, "error": "AUTOMATION_CRON_SECRET is not configured"},
            status_code=503
        )

    token = (
        request.headers.get("x-automation-secret")
        or request.query_params.get("token")
        or ""
    ).strip()

    if not token or not hmac.compare_digest(token, cron_secret):
        return JSONResponse(
            {"ok": False, "error": "forbidden"},
            status_code=403
        )

    from app.main import run_ai_digest_scheduler_for_all_companies

    summary = run_ai_digest_scheduler_for_all_companies()

    return JSONResponse({
        "ok": True,
        "summary": summary
    })


@router.post("/automation/cron/calendar-plans")
async def run_calendar_plan_scheduler_cron(request: Request):
    cron_secret = (os.getenv("AUTOMATION_CRON_SECRET") or "").strip()

    if not cron_secret:
        return JSONResponse(
            {
                "ok": False,
                "error": "AUTOMATION_CRON_SECRET is not configured",
            },
            status_code=503,
        )

    token = (
        request.headers.get("x-automation-secret")
        or request.query_params.get("token")
        or ""
    ).strip()

    if not token or not hmac.compare_digest(token, cron_secret):
        return JSONResponse(
            {"ok": False, "error": "forbidden"},
            status_code=403,
        )

    return {
        "ok": True,
        "summary": await _run_calendar_plan_scheduler_for_all_companies(),
    }


@router.post("/automation/cron/calendar-plans/watchdog")
async def run_calendar_plan_scheduler_watchdog(request: Request):
    cron_secret = (os.getenv("AUTOMATION_CRON_SECRET") or "").strip()

    if not cron_secret:
        return JSONResponse(
            {
                "ok": False,
                "error": "AUTOMATION_CRON_SECRET is not configured",
            },
            status_code=503,
        )

    token = (
        request.headers.get("x-automation-secret")
        or request.query_params.get("token")
        or ""
    ).strip()

    if not token or not hmac.compare_digest(token, cron_secret):
        return JSONResponse(
            {"ok": False, "error": "forbidden"},
            status_code=403,
        )

    return {
        "ok": True,
        "summary": _monitor_calendar_plan_schedulers(),
    }


@router.post("/automation/cron/background-jobs")
async def run_background_jobs_cron(request: Request):
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

    from app.main import run_background_job_batch

    summary = run_background_job_batch(
        worker_id=f"cron-{uuid4().hex[:12]}",
    )
    payload = {
        "ok": not summary["failed"] and not summary["stale_failed"],
        "summary": summary,
    }
    if not payload["ok"]:
        return JSONResponse(payload, status_code=503)
    return payload


@router.post("/automation/cron/database-backup")
async def run_database_backup_cron(request: Request):
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

    from app.main import (
        enqueue_database_backup_job,
        run_background_job_batch,
    )

    queued = enqueue_database_backup_job("cron")
    summary = run_background_job_batch(
        worker_id=f"cron-backup-{uuid4().hex[:12]}",
    )
    payload = {
        "ok": not summary["failed"] and not summary["stale_failed"],
        "job_created": queued["created"],
        "job_id": queued["job"]["id"],
        "summary": summary,
    }
    if not payload["ok"]:
        return JSONResponse(payload, status_code=503)
    return payload


@router.post("/automation/cron/a3-autonomous")
async def run_a3_autonomous_cron(request: Request):
    cron_secret = (os.getenv("AUTOMATION_CRON_SECRET") or "").strip()

    if not cron_secret:
        return JSONResponse(
            {"ok": False, "error": "AUTOMATION_CRON_SECRET is not configured"},
            status_code=503,
        )

    token = (
        request.headers.get("x-automation-secret")
        or request.query_params.get("token")
        or ""
    ).strip()

    if not token or not hmac.compare_digest(token, cron_secret):
        return JSONResponse(
            {"ok": False, "error": "forbidden"},
            status_code=403,
        )

    return {
        "ok": True,
        "summary": _run_a3_autonomous_cycle_for_all_companies(),
    }


@router.post("/automation/cron/a3-watchdog")
async def run_a3_scheduler_watchdog_cron(request: Request):
    cron_secret = (os.getenv("AUTOMATION_CRON_SECRET") or "").strip()

    if not cron_secret:
        return JSONResponse(
            {"ok": False, "error": "AUTOMATION_CRON_SECRET is not configured"},
            status_code=503,
        )

    token = (
        request.headers.get("x-automation-secret")
        or request.query_params.get("token")
        or ""
    ).strip()

    if not token or not hmac.compare_digest(token, cron_secret):
        return JSONResponse(
            {"ok": False, "error": "forbidden"},
            status_code=403,
        )

    return {
        "ok": True,
        "summary": _run_a3_scheduler_watchdog_for_all_companies(),
    }


@router.post("/automation/cron/a3-incident-actions")
async def run_a3_incident_action_monitor_cron(request: Request):
    cron_secret = (os.getenv("AUTOMATION_CRON_SECRET") or "").strip()

    if not cron_secret:
        return JSONResponse(
            {"ok": False, "error": "AUTOMATION_CRON_SECRET is not configured"},
            status_code=503,
        )

    token = (
        request.headers.get("x-automation-secret")
        or request.query_params.get("token")
        or ""
    ).strip()

    if not token or not hmac.compare_digest(token, cron_secret):
        return JSONResponse(
            {"ok": False, "error": "forbidden"},
            status_code=403,
        )

    return {
        "ok": True,
        "summary": _run_a3_incident_followup_monitor(),
        "quality_summary": _run_a3_followup_quality_monitor(),
        "quality_sla_summary": _run_a3_followup_quality_sla_monitor(),
    }


def _run_a3_autonomous_cycle_for_all_companies():
    from app.main import run_a3_autonomous_cycle_for_all_companies

    return run_a3_autonomous_cycle_for_all_companies()


def _run_a3_scheduler_watchdog_for_all_companies():
    from app.main import run_a3_scheduler_watchdog_for_all_companies

    return run_a3_scheduler_watchdog_for_all_companies()


def _run_a3_incident_followup_monitor():
    from app.main import run_a3_incident_followup_monitor

    return run_a3_incident_followup_monitor()


def _run_a3_followup_quality_monitor():
    from app.main import run_a3_followup_quality_monitor

    return run_a3_followup_quality_monitor()


def _run_a3_followup_quality_sla_monitor():
    from app.main import run_a3_followup_quality_sla_monitor

    return run_a3_followup_quality_sla_monitor()


async def _run_calendar_plan_scheduler_for_all_companies():
    from app.main import run_calendar_plan_scheduler_for_all_companies

    return await run_calendar_plan_scheduler_for_all_companies()


def _monitor_calendar_plan_schedulers():
    from app.main import monitor_calendar_plan_schedulers

    return monitor_calendar_plan_schedulers()
