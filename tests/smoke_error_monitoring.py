import asyncio
import json
import os
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from starlette.requests import Request


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def make_request(path="/system", method="GET"):
    return Request({
        "type": "http",
        "method": method,
        "path": path,
        "headers": [],
        "query_string": b"",
        "scheme": "http",
        "client": ("127.0.0.1", 50000),
        "server": ("testserver", 80),
    })


def main():
    with tempfile.TemporaryDirectory() as temp_dir, patch.dict(
        os.environ,
        {
            "DATA_DIR": temp_dir,
            "SECRET_KEY": "error-monitoring-smoke-secret",
            "DATABASE_BACKEND": "sqlite",
            "DATABASE_URL": "",
            "ERROR_MONITOR_ALERT_THRESHOLD": "2",
            "ERROR_MONITOR_ALERT_COOLDOWN_MINUTES": "60",
            "ERROR_MONITOR_RECENT_HOURS": "24",
        },
        clear=False,
    ):
        from app import database
        from app.services.error_monitoring import (
            acknowledge_error_incident,
            build_error_fingerprint,
            get_error_incidents,
            get_error_monitoring_overview,
            normalize_error_path,
            record_error_incident,
            resolve_error_incident,
        )

        database.init_db()
        base_now = datetime(2026, 9, 19, 12, 0, 0)
        uuid_path = "/api/tasks/550e8400-e29b-41d4-a716-446655440000"
        assert normalize_error_path("/task/123?token=private") == "/task/:id"
        assert normalize_error_path(uuid_path) == "/api/tasks/:uuid"
        assert normalize_error_path(
            "/reset/opaqueSecretTokenValue123",
        ) == "/reset/:value"
        assert build_error_fingerprint(
            "ValueError", "get", "/task/123",
        ) == build_error_fingerprint(
            "ValueError", "GET", "/task/999",
        )

        first = record_error_incident(
            "ValueError",
            method="GET",
            path="/task/123?password=private-password",
            error_id="error-one",
            request_id="request-one",
            username="super",
            now=base_now,
        )
        second = record_error_incident(
            "ValueError",
            method="GET",
            path="/task/999",
            error_id="error-two",
            request_id="request-two",
            username="super",
            now=base_now + timedelta(minutes=1),
        )
        assert first["created"] is True
        assert first["notification_due"] is False
        assert second["created"] is False
        assert second["notification_due"] is True
        assert second["incident"]["occurrence_count"] == 2
        assert second["incident"]["path_pattern"] == "/task/:id"
        assert second["incident"]["notification_count"] == 1

        suppressed = record_error_incident(
            "ValueError",
            method="GET",
            path="/task/777",
            now=base_now + timedelta(minutes=30),
        )
        assert suppressed["notification_due"] is False
        repeated = record_error_incident(
            "ValueError",
            method="GET",
            path="/task/888",
            now=base_now + timedelta(minutes=62),
        )
        assert repeated["notification_due"] is True
        assert repeated["incident"]["notification_count"] == 2

        incident_id = repeated["incident"]["id"]
        acknowledged = acknowledge_error_incident(incident_id, "super")
        assert acknowledged["ok"] is True
        assert acknowledged["incident"]["status"] == "acknowledged"
        resolved = resolve_error_incident(
            incident_id,
            "super",
            "Исправлено и проверено.",
        )
        assert resolved["ok"] is True
        assert resolved["incident"]["status"] == "resolved"
        reopened = record_error_incident(
            "ValueError",
            method="GET",
            path="/task/456",
            now=base_now + timedelta(minutes=123),
        )
        assert reopened["reopened"] is True
        assert reopened["incident"]["status"] == "active"
        assert reopened["incident"]["reopen_count"] == 1
        assert reopened["incident"]["resolved_by"] is None

        def record_concurrent(index):
            return record_error_incident(
                "LookupError",
                method="POST",
                path=f"/clients/{1000 + index}/sync",
                now=base_now,
            )

        with ThreadPoolExecutor(max_workers=2) as executor:
            concurrent = list(executor.map(record_concurrent, range(2)))
        assert sum(1 for result in concurrent if result["created"]) == 1
        lookup = next(
            item for item in get_error_incidents()
            if item["error_type"] == "LookupError"
        )
        assert lookup["occurrence_count"] == 2

        database_text = json.dumps(
            get_error_incidents(),
            ensure_ascii=False,
            default=str,
        )
        assert "private-password" not in database_text
        overview = get_error_monitoring_overview(
            now=base_now + timedelta(minutes=123),
        )
        assert overview["status"] == "critical"
        assert overview["summary"]["open"] >= 2
        assert overview["summary"]["repeated"] >= 2

        connection = database.connect()
        connection.execute("""
            INSERT INTO users (
                username, password, role, company_id, is_active, last_seen
            ) VALUES ('super', 'test', 'superadmin', 1, 1, '')
        """)
        connection.commit()
        connection.close()

        from app import main as crm

        notification_calls = []
        with patch.object(crm, "get_user", return_value="super"), patch.object(
            crm,
            "send_message",
            return_value=True,
        ) as telegram_mock, patch.object(
            crm,
            "create_notification",
            side_effect=lambda *args: notification_calls.append(args),
        ):
            secret = "api-key-must-never-be-persisted"
            crm.log_runtime_exception(
                make_request("/api/orders/101"),
                RuntimeError(secret),
                "runtime-request-one",
            )
            crm.log_runtime_exception(
                make_request("/api/orders/202"),
                RuntimeError(secret),
                "runtime-request-two",
            )
            assert telegram_mock.call_count == 1
            assert len(notification_calls) == 1

        events = crm.get_system_event_history(100)
        serialized_events = json.dumps(events, ensure_ascii=False)
        assert secret not in serialized_events
        assert "incident_id=" in serialized_events

        with patch.object(crm, "get_user", return_value=""), patch.object(
            crm,
            "get_role",
            return_value="",
        ):
            unauthorized = asyncio.run(crm.api_system_error_incidents(
                make_request("/api/system/error-incidents"),
            ))
        assert unauthorized.status_code == 401

        with patch.object(crm, "get_user", return_value="owner"), patch.object(
            crm,
            "get_role",
            return_value="boss",
        ):
            forbidden = asyncio.run(crm.api_system_error_incidents(
                make_request("/api/system/error-incidents"),
            ))
        assert forbidden.status_code == 403

        with patch.object(crm, "get_user", return_value="super"), patch.object(
            crm,
            "get_role",
            return_value="superadmin",
        ):
            api_payload = asyncio.run(crm.api_system_error_incidents(
                make_request("/api/system/error-incidents"),
            ))
            export = asyncio.run(crm.system_error_incidents_export(
                make_request("/system/errors/export"),
            ))
            page = asyncio.run(crm.system_page(make_request("/system")))
            route_incident = record_error_incident(
                "RouteActionError",
                method="POST",
                path="/api/route-actions/42",
                now=base_now,
            )["incident"]
            acknowledged_response = asyncio.run(
                crm.system_error_incident_acknowledge(
                    make_request(
                        f"/system/errors/{route_incident['id']}/acknowledge",
                        method="POST",
                    ),
                    route_incident["id"],
                ),
            )
            resolved_response = asyncio.run(
                crm.system_error_incident_resolve(
                    make_request(
                        f"/system/errors/{route_incident['id']}/resolve",
                        method="POST",
                    ),
                    route_incident["id"],
                ),
            )
        assert api_payload["ok"] is True
        assert api_payload["incidents"]
        assert export.status_code == 200
        assert export.headers["content-disposition"] == (
            "attachment; filename=application_error_incidents.csv"
        )
        assert "Журнал ошибок приложения" in export.body.decode("utf-8")
        page_html = page.body.decode("utf-8")
        assert "Журнал ошибок приложения" in page_html
        assert "Текст исключения и данные запроса не сохраняются" in page_html
        assert "/api/orders/:id" in page_html
        assert acknowledged_response.status_code == 302
        assert "notice=error_incident_acknowledged" in (
            acknowledged_response.headers["location"]
        )
        assert resolved_response.status_code == 302
        assert "notice=error_incident_resolved" in (
            resolved_response.headers["location"]
        )
        route_state = next(
            item for item in get_error_incidents()
            if item["id"] == route_incident["id"]
        )
        assert route_state["status"] == "resolved"
        assert route_state["resolved_by"] == "super"

        print(
            "Error monitoring smoke passed: grouped incidents, lifecycle, "
            "cooldown, safe storage, notifications, API and UI."
        )


if __name__ == "__main__":
    main()
