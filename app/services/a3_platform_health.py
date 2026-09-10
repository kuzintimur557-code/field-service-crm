from datetime import datetime
from urllib.parse import urlencode

from app.services.a3_scheduler_watchdog import (
    get_a3_scheduler_watchdog_report,
    get_a3_scheduler_watchdog_status,
)
from app.services.a3_platform_incidents import get_a3_platform_incident_summary


A3_PLATFORM_HEALTH_STATUS_LABELS = {
    "all": "Все",
    "problem": "Требуют внимания",
    "critical": "Критические",
    "warning": "Предупреждения",
    "stable": "Стабильные",
    "waiting": "Ожидают запуска",
    "paused": "Приостановлены",
}


def normalize_a3_platform_health_status(value):
    normalized = str(value or "all").strip().lower()
    return (
        normalized
        if normalized in A3_PLATFORM_HEALTH_STATUS_LABELS
        else "all"
    )


def build_a3_platform_health_url(status="all", search=""):
    params = {}
    normalized_status = normalize_a3_platform_health_status(status)
    normalized_search = str(search or "").strip()[:100]

    if normalized_status != "all":
        params["status"] = normalized_status
    if normalized_search:
        params["search"] = normalized_search

    query = urlencode(params)
    return "/platform/a3-health" + (f"?{query}" if query else "")


def _resolve_platform_status(item, watchdog):
    main_status = item.get("status") or "error"
    watchdog_status = watchdog.get("status") or "unknown"

    if main_status in {"critical", "error"} or watchdog_status == "critical":
        return "critical", "Критично", "danger"
    if main_status == "skipped":
        return "paused", "Приостановлено", "muted"
    if main_status == "waiting":
        return "waiting", "Ожидает запуска", "warning"
    if main_status == "warning" or watchdog_status in {
        "warning",
        "unknown",
        "error",
        "waiting",
    }:
        return "warning", "Нужно внимание", "warning"
    if main_status == "stable" and watchdog_status == "stable":
        return "stable", "Стабильно", "success"

    return "warning", "Нужно проверить", "warning"


def _matches_status(item_status, selected_status):
    if selected_status == "all":
        return True
    if selected_status == "problem":
        return item_status in {"critical", "warning", "waiting"}
    return item_status == selected_status


def get_a3_platform_health(status_filter="all", search="", now=None):
    now_value = now or datetime.now()
    selected_status = normalize_a3_platform_health_status(status_filter)
    selected_search = str(search or "").strip()[:100]
    report = get_a3_scheduler_watchdog_report(now=now_value)
    all_items = []

    for report_item in report.get("items", []):
        company_id = report_item["company_id"]
        watchdog = get_a3_scheduler_watchdog_status(
            company_id,
            now=now_value,
        )
        status, status_label, status_tone = _resolve_platform_status(
            report_item,
            watchdog,
        )
        reliability = report_item.get("reliability") or {}
        recommendation = (
            watchdog.get("recommendation")
            if watchdog.get("status") in {"critical", "warning", "unknown"}
            else reliability.get("recommendation")
        ) or "Продолжайте контролировать фоновые процессы A3."
        company_name = report_item.get("company_name") or f"Компания #{company_id}"
        owner_username = report_item.get("owner_username") or "Не указан"

        all_items.append({
            "company_id": company_id,
            "company_name": company_name,
            "owner_username": owner_username,
            "status": status,
            "status_label": status_label,
            "status_tone": status_tone,
            "main_status": report_item.get("status") or "error",
            "main_status_label": (
                report_item.get("status_label") or "Ошибка проверки"
            ),
            "main_message": report_item.get("message") or "Нет данных.",
            "latest_scheduler_run_at": reliability.get(
                "latest_scheduler_run_at"
            ),
            "latest_scheduler_age_label": reliability.get(
                "latest_scheduler_age_label"
            ) or "Основных запусков пока нет",
            "watchdog_status": watchdog.get("status") or "unknown",
            "watchdog_status_label": (
                watchdog.get("status_label") or "Контроль не запускался"
            ),
            "watchdog_checked_at": watchdog.get("checked_at"),
            "watchdog_checked_age_label": (
                watchdog.get("checked_age_label") or "Проверок пока нет"
            ),
            "notification_created": bool(
                watchdog.get("notification_created")
            ),
            "telegram_sent": bool(watchdog.get("telegram_sent")),
            "recommendation": recommendation,
            "company_url": f"/platform/companies/{company_id}",
        })

    summary = {
        "total": len(all_items),
        "stable": sum(item["status"] == "stable" for item in all_items),
        "warning": sum(item["status"] == "warning" for item in all_items),
        "critical": sum(item["status"] == "critical" for item in all_items),
        "waiting": sum(item["status"] == "waiting" for item in all_items),
        "paused": sum(item["status"] == "paused" for item in all_items),
    }
    summary["problems"] = (
        summary["critical"] + summary["warning"] + summary["waiting"]
    )
    incident_summary = get_a3_platform_incident_summary()
    summary["active_incidents"] = incident_summary["active"]
    summary["active_critical_incidents"] = incident_summary["critical"]
    summary["unacknowledged_incidents"] = incident_summary["unacknowledged"]

    search_lower = selected_search.lower()
    filtered_items = [
        item
        for item in all_items
        if _matches_status(item["status"], selected_status)
        and (
            not search_lower
            or search_lower in item["company_name"].lower()
            or search_lower in item["owner_username"].lower()
            or search_lower == str(item["company_id"])
        )
    ]
    status_order = {
        "critical": 0,
        "warning": 1,
        "waiting": 2,
        "paused": 3,
        "stable": 4,
    }
    filtered_items.sort(
        key=lambda item: (
            status_order.get(item["status"], 9),
            item["company_name"].lower(),
        )
    )
    summary["visible"] = len(filtered_items)

    if summary["critical"]:
        overall_status = "critical"
        overall_label = "Есть критические проблемы"
        overall_tone = "danger"
    elif summary["problems"]:
        overall_status = "warning"
        overall_label = "Требуется внимание"
        overall_tone = "warning"
    else:
        overall_status = "stable"
        overall_label = "Фоновые процессы стабильны"
        overall_tone = "success"

    status_options = []
    for key, label in A3_PLATFORM_HEALTH_STATUS_LABELS.items():
        count = (
            summary["problems"]
            if key == "problem"
            else summary.get(key, summary["total"])
        )
        status_options.append({
            "key": key,
            "label": label,
            "count": count,
            "url": build_a3_platform_health_url(key, selected_search),
        })

    return {
        "generated_at": now_value.strftime("%Y-%m-%d %H:%M"),
        "status_filter": selected_status,
        "search": selected_search,
        "overall_status": overall_status,
        "overall_label": overall_label,
        "overall_tone": overall_tone,
        "summary": summary,
        "items": filtered_items,
        "all_items": all_items,
        "status_options": status_options,
        "export_url": (
            "/platform/a3-health/export"
            + (
                "?" + urlencode({
                    key: value
                    for key, value in {
                        "status": selected_status if selected_status != "all" else "",
                        "search": selected_search,
                    }.items()
                    if value
                })
                if selected_status != "all" or selected_search
                else ""
            )
        ),
    }
