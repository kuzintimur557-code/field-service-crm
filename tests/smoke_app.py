import asyncio
import json
import os
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import urlencode

from starlette.requests import Request


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

TEMP_DATA = tempfile.TemporaryDirectory()
os.environ["DATA_DIR"] = TEMP_DATA.name
os.environ["SECRET_KEY"] = "smoke-test-secret"

from app import main as crm  # noqa: E402
from app.database import connect  # noqa: E402


def make_request(username=None, cookies=None):
    request_cookies = dict(cookies or {})

    if username:
        request_cookies[crm.SESSION_COOKIE_NAME] = crm.sign_session_value(username)

    return SimpleNamespace(cookies=request_cookies, headers={}, client=None)


def make_asgi_request(username, path="/calendar", query_string=""):
    cookie = f"{crm.SESSION_COOKIE_NAME}={crm.sign_session_value(username)}"
    query_bytes = query_string.encode("utf-8") if isinstance(query_string, str) else query_string

    return Request({
        "type": "http",
        "method": "GET",
        "path": path,
        "headers": [(b"cookie", cookie.encode("utf-8"))],
        "query_string": query_bytes,
        "scheme": "http",
        "client": ("127.0.0.1", 50000),
        "server": ("testserver", 80),
    })


def make_public_asgi_request(path="/", query_string="", headers=None):
    request_headers = list(headers or [])
    query_bytes = query_string.encode("utf-8") if isinstance(query_string, str) else query_string

    return Request({
        "type": "http",
        "method": "POST",
        "path": path,
        "headers": request_headers,
        "query_string": query_bytes,
        "scheme": "http",
        "client": ("127.0.0.1", 50000),
        "server": ("testserver", 80),
    })


def make_form_request(username, path, data):
    body = urlencode(data).encode("utf-8")
    cookie = f"{crm.SESSION_COOKIE_NAME}={crm.sign_session_value(username)}"

    async def receive():
        return {
            "type": "http.request",
            "body": body,
            "more_body": False,
        }

    return Request({
        "type": "http",
        "method": "POST",
        "path": path,
        "headers": [
            (b"cookie", cookie.encode("utf-8")),
            (b"content-type", b"application/x-www-form-urlencoded"),
            (b"content-length", str(len(body)).encode("utf-8")),
        ],
        "query_string": b"",
        "scheme": "http",
        "client": ("127.0.0.1", 50000),
        "server": ("testserver", 80),
    }, receive)


def make_multipart_request(username, path, data):
    boundary = "----smoke-boundary"
    parts = []

    for key, value in data.items():
        values = value if isinstance(value, list) else [value]

        for item in values:
            parts.append(
                f"--{boundary}\r\n"
                f"Content-Disposition: form-data; name=\"{key}\"\r\n\r\n"
                f"{item}\r\n"
            )

    parts.append(f"--{boundary}--\r\n")
    body = "".join(parts).encode("utf-8")
    cookie = f"{crm.SESSION_COOKIE_NAME}={crm.sign_session_value(username)}"

    async def receive():
        return {
            "type": "http.request",
            "body": body,
            "more_body": False,
        }

    return Request({
        "type": "http",
        "method": "POST",
        "path": path,
        "headers": [
            (b"cookie", cookie.encode("utf-8")),
            (b"content-type", f"multipart/form-data; boundary={boundary}".encode("utf-8")),
            (b"content-length", str(len(body)).encode("utf-8")),
        ],
        "query_string": b"",
        "scheme": "http",
        "client": ("127.0.0.1", 50000),
        "server": ("testserver", 80),
    }, receive)


def seed_data():
    conn = connect()
    c = conn.cursor()

    users = [
        ("super", "x", "superadmin", 1, ""),
        ("owner2", "x", "boss", 2, ""),
        ("manager1", "x", "manager", 1, ""),
        ("manager2", "x", "manager", 2, ""),
        ("worker2", "x", "worker", 2, "chat-worker2"),
        ("helper2", "x", "worker", 2, "chat-helper2"),
        ("free2", "x", "worker", 2, ""),
        ("outsider_worker", "x", "worker", 1, "chat-outsider"),
    ]

    c.executemany("""
    INSERT INTO users (username, password, role, company_id, telegram_chat_id)
    VALUES (?, ?, ?, ?, ?)
    """, users)

    c.execute("""
    INSERT INTO clients (
        company_id, name, phone, email, address, notes, created_at
    )
    VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        2,
        "Client 2",
        "+70000000000",
        "client@example.com",
        "Company 2 address",
        "Smoke client note",
        "2026-05-17 10:00",
    ))
    client_id = c.lastrowid

    c.execute("""
    INSERT INTO tasks (
        client_id, client, phone, address, description, task_date, worker, workers,
        priority, price, photo, status, report, after_photo, company_id
    )
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        client_id,
        "Client 2",
        "+70000000000",
        "Company 2 address",
        "Smoke task",
        "2026-05-17",
        "worker2",
        "worker2,helper2",
        "normal",
        "1000",
        "before.png",
        "Новая",
        "",
        "after.png",
        2,
    ))

    task_id = c.lastrowid
    conn.commit()

    task = c.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
    conn.close()

    crm.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    (crm.UPLOAD_DIR / "before.png").write_bytes(b"smoke-before")
    (crm.UPLOAD_DIR / "after.png").write_bytes(b"smoke-after")

    return task


def assert_session_cookie_auth():
    unsigned_request = make_request(cookies={"user": "owner2"})
    assert crm.get_user(unsigned_request) is None

    signed_request = make_request("owner2")
    assert crm.get_user(signed_request) == "owner2"

    signed_value = signed_request.cookies[crm.SESSION_COOKIE_NAME]
    tampered_request = make_request(cookies={
        crm.SESSION_COOKIE_NAME: signed_value[:-2] + "xx",
    })
    assert crm.get_user(tampered_request) is None


def assert_task_access(task):
    assert crm.can_access_task("super", "superadmin", task)
    assert crm.can_access_task("owner2", "boss", task)
    assert crm.can_access_task("manager2", "manager", task)
    assert not crm.can_access_task("manager1", "manager", task)
    assert crm.can_access_task("worker2", "worker", task)
    assert crm.can_access_task("helper2", "worker", task)
    assert not crm.can_access_task("outsider_worker", "worker", task)

    assert crm.get_task_worker_names(task) == ["worker2", "helper2"]

    conn = connect()
    c = conn.cursor()

    assert crm.get_task_worker_chat_ids(c, task) == [
        "chat-worker2",
        "chat-helper2",
    ]

    matched = c.execute(f"""
    SELECT *
    FROM tasks
    WHERE id=? AND {crm.worker_task_condition()}
    """, [task["id"], *crm.worker_task_params("helper2")]).fetchone()
    conn.close()

    assert matched is not None


def assert_company_features():
    features = crm.get_company_features(2)
    assert features["tasks"]
    assert features["finance"]
    assert features["notifications"]
    assert features["automation"]

    crm.update_company_features(2, {"feature_finance": "1"})

    features = crm.get_company_features(2)
    assert features["tasks"]
    assert features["notifications"]
    assert features["finance"]
    assert not features["calendar"]
    assert not features["automation"]

    beauty_labels = crm.get_industry_labels("beauty")

    assert beauty_labels["task_label"] == "Запись"
    assert beauty_labels["worker_label"] == "Мастер"
    assert beauty_labels["client_label"] == "Клиент"
    assert beauty_labels["service_label"] == "Услуга"

    crm.apply_business_preset(2, "beauty")

    conn = crm.connect()
    c = conn.cursor()

    settings = c.execute("""
    SELECT task_label, worker_label, client_label, service_label
    FROM company_settings
    WHERE company_id=?
    """, (2,)).fetchone()

    conn.close()

    assert settings["task_label"] == "Запись"
    assert settings["worker_label"] == "Мастер"
    assert settings["client_label"] == "Клиент"
    assert settings["service_label"] == "Услуга"

    features = crm.get_company_features(2)
    assert features["tasks"]
    assert features["calendar"]
    assert features["clients"]
    assert features["payroll"]
    assert features["notifications"]
    assert features["automation"]
    assert not features["sla"]

    response = asyncio.run(crm.sla_page(make_asgi_request("owner2", "/sla")))
    assert response.status_code == 302
    assert response.headers["location"] == "/"

    crm.update_company_features(2, {"feature_finance": "1"})
    response = asyncio.run(crm.reports_page(make_asgi_request("owner2", "/reports")))
    assert response.status_code == 302
    assert response.headers["location"] == "/"


def assert_automation_foundation():
    conn = connect()
    c = conn.cursor()

    table_names = {
        row["name"]
        for row in c.execute("""
        SELECT name
        FROM sqlite_master
        WHERE type='table'
          AND name IN ('automation_rules', 'automation_actions', 'automation_events')
        """).fetchall()
    }

    index_names = {
        row["name"]
        for row in c.execute("""
        SELECT name
        FROM sqlite_master
        WHERE type='index'
          AND name IN (
              'idx_automation_rules_company_active',
              'idx_automation_actions_rule',
              'idx_automation_events_company_status'
          )
        """).fetchall()
    }

    conn.close()

    assert table_names == {"automation_rules", "automation_actions", "automation_events"}
    assert index_names == {
        "idx_automation_rules_company_active",
        "idx_automation_actions_rule",
        "idx_automation_events_company_status",
    }


async def assert_automation_page():
    response = await crm.automation_page(make_asgi_request("owner2", "/automation"))
    assert response.status_code == 200
    html = response.body.decode("utf-8")
    assert "Автоматизация" in html
    assert "Новое правило" in html
    assert "Правил пока нет" in html
    assert "Просрочен SLA" in html
    assert "Создать уведомление" in html
    assert "Всего правил" in html
    assert "Включено правил" in html
    assert "Событий done" in html
    assert "AI scheduler" in html
    assert 'action="/automation/ai-digest/run"' in html

    create_response = await crm.create_automation_rule(
        make_form_request(
            "owner2",
            "/automation/rules",
            {
                "name": "SLA smoke rule",
                "trigger_key": "sla_overdue",
                "action_key": "notification",
                "target_username": "owner2",
                "message": "SLA smoke message",
            },
        )
    )
    assert create_response.status_code == 302
    assert create_response.headers["location"] == "/automation?created=1"

    conn = connect()
    c = conn.cursor()
    rule = c.execute("""
    SELECT *
    FROM automation_rules
    WHERE company_id=2
      AND name='SLA smoke rule'
    """).fetchone()
    action = c.execute("""
    SELECT *
    FROM automation_actions
    WHERE company_id=2
      AND rule_id=?
    """, (rule["id"],)).fetchone()
    conn.close()

    assert rule is not None
    assert rule["trigger_key"] == "sla_overdue"
    assert rule["active"] == 1
    assert action is not None
    assert action["action_key"] == "notification"
    assert "SLA smoke message" in action["payload_json"]

    list_response = await crm.automation_page(make_asgi_request("owner2", "/automation"))
    assert list_response.status_code == 200
    list_html = list_response.body.decode("utf-8")
    assert "SLA smoke rule" in list_html
    assert "Включено" in list_html
    assert "Создать уведомление" in list_html
    assert f"/automation/rules/{rule['id']}/toggle" in list_html
    assert f"/automation/rules/{rule['id']}/edit" in list_html

    edit_response = await crm.edit_automation_rule(
        make_form_request(
            "owner2",
            f"/automation/rules/{rule['id']}/edit",
            {
                "name": "SLA smoke rule updated",
                "target_username": "manager2",
                "message": "Updated SLA smoke message",
            },
        ),
        rule["id"],
    )
    assert edit_response.status_code == 302
    assert edit_response.headers["location"] == "/automation?updated=1"

    conn = connect()
    c = conn.cursor()
    updated_rule = c.execute("""
    SELECT *
    FROM automation_rules
    WHERE id=?
    """, (rule["id"],)).fetchone()
    updated_action = c.execute("""
    SELECT *
    FROM automation_actions
    WHERE rule_id=?
    """, (rule["id"],)).fetchone()
    conn.close()

    assert updated_rule["name"] == "SLA smoke rule updated"
    assert "manager2" in updated_action["payload_json"]
    assert "Updated SLA smoke message" in updated_action["payload_json"]

    updated_page_response = await crm.automation_page(make_asgi_request("owner2", "/automation"))
    assert updated_page_response.status_code == 200
    updated_page_html = updated_page_response.body.decode("utf-8")
    assert "SLA smoke rule updated" in updated_page_html
    assert "Updated SLA smoke message" in updated_page_html

    toggle_response = await crm.toggle_automation_rule(
        make_request("owner2"),
        rule["id"],
    )
    assert toggle_response.status_code == 302
    assert toggle_response.headers["location"] == "/automation?toggled=1"

    conn = connect()
    c = conn.cursor()
    toggled = c.execute("""
    SELECT active
    FROM automation_rules
    WHERE id=?
    """, (rule["id"],)).fetchone()
    conn.close()

    assert toggled["active"] == 0

    disabled_response = await crm.automation_page(
        make_asgi_request("owner2", "/automation"),
        rule_filter="disabled",
    )
    assert disabled_response.status_code == 200
    disabled_html = disabled_response.body.decode("utf-8")
    assert "Выключенные" in disabled_html
    assert "SLA smoke rule" in disabled_html


async def assert_automation_runner(task):
    create_response = await crm.create_automation_rule(
        make_form_request(
            "owner2",
            "/automation/rules",
            {
                "name": "SLA runner rule",
                "trigger_key": "sla_overdue",
                "action_key": "notification",
                "target_username": "owner2",
                "message": "Runner notification message",
            },
        )
    )
    assert create_response.status_code == 302

    created_events = crm.run_automation_event(
        2,
        "sla_overdue",
        "task",
        task["id"],
        "SLA event happened",
        f"/task/{task['id']}",
    )
    assert created_events == 1

    conn = connect()
    c = conn.cursor()

    event = c.execute("""
    SELECT *
    FROM automation_events
    WHERE company_id=2
      AND trigger_key='sla_overdue'
      AND entity_type='task'
      AND entity_id=?
    ORDER BY id DESC
    """, (task["id"],)).fetchone()

    notification = c.execute("""
    SELECT *
    FROM notifications
    WHERE company_id=2
      AND username='owner2'
      AND title='SLA runner rule'
    ORDER BY id DESC
    """).fetchone()

    conn.close()

    assert event is not None
    assert event["status"] == "done"
    assert event["processed_at"]
    assert notification is not None
    assert notification["message"] == "Runner notification message"
    assert notification["link"] == f"/task/{task['id']}"

    done_response = await crm.automation_page(
        make_asgi_request("owner2", "/automation"),
        event_filter="done",
    )
    assert done_response.status_code == 200
    done_html = done_response.body.decode("utf-8")
    assert "SLA event happened" in done_html
    assert "done" in done_html

    telegram_response = await crm.create_automation_rule(
        make_form_request(
            "owner2",
            "/automation/rules",
            {
                "name": "Telegram runner rule",
                "trigger_key": "sla_overdue",
                "action_key": "telegram_alert",
                "target_username": "owner2",
                "message": "Telegram runner message",
            },
        )
    )
    assert telegram_response.status_code == 302

    telegram_events = crm.run_automation_event(
        2,
        "sla_overdue",
        "task",
        task["id"],
        "Telegram event happened",
        f"/task/{task['id']}",
    )
    assert telegram_events >= 1

    conn = connect()
    c = conn.cursor()

    telegram_event = c.execute("""
    SELECT *
    FROM automation_events
    WHERE company_id=2
      AND trigger_key='sla_overdue'
      AND message='Telegram event happened'
    ORDER BY id DESC
    """).fetchone()

    conn.close()

    assert telegram_event is not None
    assert telegram_event["status"] in ("done", "skipped")
    assert telegram_event["processed_at"]

    ai_digest_response = await crm.create_automation_rule(
        make_form_request(
            "owner2",
            "/automation/rules",
            {
                "name": "AI digest runner rule",
                "trigger_key": "weekly_digest",
                "action_key": "ai_digest",
                "target_username": "owner2",
                "message": "",
            },
        )
    )
    assert ai_digest_response.status_code == 302

    ai_digest_events = crm.run_automation_event(
        2,
        "weekly_digest",
        "company",
        2,
        "Weekly digest event",
        "/ai/insights",
    )
    assert ai_digest_events >= 1

    conn = connect()
    c = conn.cursor()

    ai_digest_event = c.execute("""
    SELECT *
    FROM automation_events
    WHERE company_id=2
      AND trigger_key='weekly_digest'
      AND message='Weekly digest event'
    ORDER BY id DESC
    """).fetchone()

    ai_digest_notification = c.execute("""
    SELECT *
    FROM notifications
    WHERE company_id=2
      AND username='owner2'
      AND title='🤖 AI-сводка'
    ORDER BY id DESC
    """).fetchone()

    conn.close()

    assert ai_digest_event is not None
    assert ai_digest_event["status"] == "done"
    assert ai_digest_notification is not None
    assert "AI-сводка по бизнесу" in ai_digest_notification["message"]
    assert ai_digest_notification["link"] == "/ai/insights"

    daily_digest_response = await crm.create_automation_rule(
        make_form_request(
            "owner2",
            "/automation/rules",
            {
                "name": "Daily AI digest runner rule",
                "trigger_key": "daily_digest",
                "action_key": "ai_digest",
                "target_username": "owner2",
                "message": "",
            },
        )
    )
    assert daily_digest_response.status_code == 302

    scheduled = crm.run_ai_digest_scheduler(
        2,
        datetime(2026, 5, 25, 9, 0),
    )
    assert scheduled["daily"] >= 1
    assert scheduled["weekly"] >= 1
    assert scheduled["skipped"] == 0

    duplicate_scheduled = crm.run_ai_digest_scheduler(
        2,
        datetime(2026, 5, 25, 12, 0),
    )
    assert duplicate_scheduled["daily"] == 0
    assert duplicate_scheduled["weekly"] == 0
    assert duplicate_scheduled["skipped"] == 2

    scheduler_response = await crm.run_ai_digest_scheduler_page(make_request("owner2"))
    assert scheduler_response.status_code == 302
    assert scheduler_response.headers["location"].startswith("/automation?scheduler=1")

    conn = connect()
    c = conn.cursor()

    daily_event = c.execute("""
    SELECT *
    FROM automation_events
    WHERE company_id=2
      AND trigger_key='daily_digest'
      AND message='AI daily digest 2026-05-25'
    ORDER BY id DESC
    """).fetchone()

    weekly_event = c.execute("""
    SELECT *
    FROM automation_events
    WHERE company_id=2
      AND trigger_key='weekly_digest'
      AND message='AI weekly digest 2026-W22'
    ORDER BY id DESC
    """).fetchone()

    conn.close()

    assert daily_event is not None
    assert daily_event["status"] == "done"
    assert weekly_event is not None
    assert weekly_event["status"] == "done"

    all_companies_summary = crm.run_ai_digest_scheduler_for_all_companies(
        datetime(2026, 5, 25, 13, 0),
    )
    assert all_companies_summary["companies"] >= 1
    assert all_companies_summary["daily"] == 0
    assert all_companies_summary["weekly"] == 0
    assert all_companies_summary["skipped"] >= 0

    old_cron_secret = os.environ.get("AUTOMATION_CRON_SECRET")
    os.environ["AUTOMATION_CRON_SECRET"] = "cron-secret"

    try:
        forbidden_response = await crm.run_ai_digest_scheduler_cron(
            make_public_asgi_request("/automation/cron/ai-digest")
        )
        assert forbidden_response.status_code == 403

        cron_response = await crm.run_ai_digest_scheduler_cron(
            make_public_asgi_request(
                "/automation/cron/ai-digest",
                headers=[(b"x-automation-secret", b"cron-secret")],
            )
        )
        assert cron_response.status_code == 200
        cron_payload = json.loads(cron_response.body.decode("utf-8"))
        assert cron_payload["ok"] is True
        assert cron_payload["summary"]["companies"] >= 1
    finally:
        if old_cron_secret is None:
            os.environ.pop("AUTOMATION_CRON_SECRET", None)
        else:
            os.environ["AUTOMATION_CRON_SECRET"] = old_cron_secret


async def assert_automation_delete():
    create_response = await crm.create_automation_rule(
        make_form_request(
            "owner2",
            "/automation/rules",
            {
                "name": "Delete automation smoke",
                "trigger_key": "overdue_task",
                "action_key": "notification",
                "target_username": "owner2",
                "message": "Delete smoke",
            },
        )
    )
    assert create_response.status_code == 302

    conn = connect()
    c = conn.cursor()
    rule = c.execute("""
    SELECT id
    FROM automation_rules
    WHERE company_id=2
      AND name='Delete automation smoke'
    """).fetchone()
    conn.close()

    page_response = await crm.automation_page(make_asgi_request("owner2", "/automation"))
    assert page_response.status_code == 200
    page_html = page_response.body.decode("utf-8")
    assert f"/automation/rules/{rule['id']}/delete" in page_html

    delete_response = await crm.delete_automation_rule(
        make_request("owner2"),
        rule["id"],
    )
    assert delete_response.status_code == 302
    assert delete_response.headers["location"] == "/automation?deleted=1"

    conn = connect()
    c = conn.cursor()
    rule_count = c.execute("""
    SELECT COUNT(*)
    FROM automation_rules
    WHERE id=?
    """, (rule["id"],)).fetchone()[0]
    action_count = c.execute("""
    SELECT COUNT(*)
    FROM automation_actions
    WHERE rule_id=?
    """, (rule["id"],)).fetchone()[0]
    conn.close()

    assert rule_count == 0
    assert action_count == 0


async def assert_upload_access():
    anonymous = await crm.uploaded_file(make_request(), "before.png")
    assert anonymous.status_code == 404

    traversal = await crm.uploaded_file(make_request("owner2"), "../before.png")
    assert traversal.status_code == 404

    outsider = await crm.uploaded_file(make_request("manager1"), "before.png")
    assert outsider.status_code == 404

    owner_file = await crm.uploaded_file(make_request("owner2"), "before.png")
    assert owner_file.status_code == 200

    worker_file = await crm.uploaded_file(make_request("helper2"), "after.png")
    assert worker_file.status_code == 200


async def assert_calendar_access():
    manager_response = await crm.calendar_page(
        make_asgi_request("owner2"),
        worker="helper2",
        month="2026-05",
        date="2026-05-17",
        status="Новая",
    )
    assert manager_response.status_code == 200
    manager_html = manager_response.body.decode("utf-8")
    assert "Client 2" in manager_html
    assert "helper2" in manager_html
    assert "load-card" in manager_html
    assert "Все статусы" in manager_html
    assert "day-count" in manager_html
    assert "day-statuses" in manager_html
    assert "reschedule" in manager_html
    assert "quick-status" in manager_html
    assert "Свободные окна" in manager_html
    assert "availability-filter" in manager_html
    assert "Свободные" in manager_html
    assert "Занятые" in manager_html
    assert "Предыдущий день" in manager_html
    assert "Следующий день" in manager_html
    assert "/calendar?date=2026-05-16&amp;worker=helper2&amp;status=" in manager_html
    assert "/calendar?date=2026-05-18&amp;worker=helper2&amp;status=" in manager_html
    assert "Всего: 3" in manager_html
    assert "Свободно: 1" in manager_html
    assert "Занято: 2" in manager_html
    assert "/create-task?task_date=2026-05-17&return_to=calendar" in manager_html
    assert "/create-task?task_date=2026-05-17&worker=free2" in manager_html
    assert "free2" in manager_html
    assert "Свободен" in manager_html
    assert "Занят: 1 активных заявок" in manager_html
    assert "Рекомендован" in manager_html

    free_response = await crm.calendar_page(
        make_asgi_request("owner2"),
        date="2026-05-17",
        availability="free",
    )
    assert free_response.status_code == 200
    free_html = free_response.body.decode("utf-8")
    assert "free2" in free_html
    assert "Занят: 1 активных заявок" not in free_html
    assert "/calendar?date=2026-05-18&amp;availability=free" in free_html

    conn = connect()
    c = conn.cursor()
    task = c.execute("""
    SELECT *
    FROM tasks
    WHERE company_id=? AND client=?
    """, (2, "Client 2")).fetchone()
    conn.close()

    original_send_message = crm.send_message
    original_send_message_to_chat = crm.send_message_to_chat
    crm.send_message = lambda text: True
    crm.send_message_to_chat = lambda chat_id, text: True

    try:
        reschedule_response = await crm.update_task_date(
            make_form_request(
                "owner2",
                f"/task/{task['id']}/date",
                {
                    "task_date": "2026-05-21",
                    "return_to": "/calendar?month=2026-05&worker=helper2&status=Новая",
                },
            ),
            task["id"],
        )
    finally:
        crm.send_message = original_send_message
        crm.send_message_to_chat = original_send_message_to_chat

    assert reschedule_response.status_code == 302
    assert reschedule_response.headers["location"].startswith("/calendar?month=2026-05&worker=helper2")

    original_send_message = crm.send_message
    crm.send_message = lambda text: True

    try:
        status_response = await crm.update_task_status(
            make_form_request(
                "owner2",
                f"/task/{task['id']}/status",
                {
                    "status": "В работе",
                    "return_to": "/calendar?date=2026-05-21&worker=helper2",
                },
            ),
            task["id"],
        )
    finally:
        crm.send_message = original_send_message

    assert status_response.status_code == 302
    assert status_response.headers["location"] == "/calendar?date=2026-05-21&worker=helper2"

    invalid_worker_response = await crm.calendar_page(
        make_asgi_request("owner2"),
        worker="outsider_worker",
        month="2026-05",
        status="Новая",
    )
    assert invalid_worker_response.status_code == 200
    assert "Client 2" not in invalid_worker_response.body.decode("utf-8")

    worker_response = await crm.calendar_page(
        make_asgi_request("helper2"),
        month="2026-05",
    )
    assert worker_response.status_code == 200
    assert "Client 2" in worker_response.body.decode("utf-8")

    outsider_response = await crm.calendar_page(
        make_asgi_request("outsider_worker"),
        month="2026-05",
    )
    assert outsider_response.status_code == 200
    assert "Client 2" not in outsider_response.body.decode("utf-8")


async def assert_archive_restore(task):
    conn = connect()
    c = conn.cursor()
    c.execute("UPDATE tasks SET archived=1 WHERE id=?", (task["id"],))
    conn.commit()
    conn.close()

    archive_response = await crm.archive_page(make_asgi_request("owner2", "/archive"))
    assert archive_response.status_code == 200
    archive_html = archive_response.body.decode("utf-8")
    assert f"/task/{task['id']}/unarchive" in archive_html
    assert "Восстановить" in archive_html

    detail_response = await crm.task_detail(
        make_asgi_request("owner2", f"/task/{task['id']}"),
        task["id"],
    )
    assert detail_response.status_code == 200
    detail_html = detail_response.body.decode("utf-8")
    assert f"/task/{task['id']}/unarchive" in detail_html
    assert "Восстановить из архива" in detail_html

    restore_response = await crm.unarchive_task(make_request("owner2"), task["id"])
    assert restore_response.status_code == 302
    assert restore_response.headers["location"] == f"/task/{task['id']}"

    conn = connect()
    c = conn.cursor()
    restored = c.execute(
        "SELECT archived FROM tasks WHERE id=?",
        (task["id"],)
    ).fetchone()
    activity = c.execute("""
    SELECT *
    FROM task_activity
    WHERE task_id=? AND action='Заявка возвращена из архива'
    """, (task["id"],)).fetchone()
    conn.close()

    assert restored["archived"] == 0
    assert activity is not None


async def assert_catalog_create():
    original_send_message = crm.send_message
    original_send_message_to_chat = crm.send_message_to_chat
    crm.send_message = lambda text: True
    crm.send_message_to_chat = lambda chat_id, text: True

    try:
        response = await crm.create_catalog_item(make_form_request(
            "owner2",
            "/catalog",
            {
                "item_type": "service",
                "name": "Smoke service",
                "unit": "шт",
                "price": "1000",
                "cost": "300",
            },
        ))
    finally:
        crm.send_message = original_send_message
        crm.send_message_to_chat = original_send_message_to_chat

    assert response.status_code == 302
    assert response.headers["location"] == "/catalog?created=1"

    conn = connect()
    c = conn.cursor()
    item = c.execute("""
    SELECT *
    FROM catalog_items
    WHERE company_id=2 AND name='Smoke service'
    """).fetchone()
    conn.close()

    assert item is not None


async def assert_finance_margin(task):
    conn = connect()
    c = conn.cursor()
    item = c.execute("""
    SELECT *
    FROM catalog_items
    WHERE company_id=2 AND name='Smoke service'
    """).fetchone()
    conn.close()

    item_response = await crm.add_task_item(
        make_form_request(
            "owner2",
            f"/task/{task['id']}/items",
            {
                "catalog_item_id": str(item["id"]),
                "qty": "2",
            },
        ),
        task["id"],
    )
    assert item_response.status_code == 302
    assert item_response.headers["location"] == f"/task/{task['id']}"

    manual_item_response = await crm.add_manual_task_item(
        make_form_request(
            "owner2",
            f"/task/{task['id']}/items/manual",
            {
                "item_name": "Manual smoke item",
                "item_type": "material",
                "unit": "шт",
                "qty": "3",
                "price": "100",
                "cost": "40",
            },
        ),
        task["id"],
    )
    assert manual_item_response.status_code == 302
    assert manual_item_response.headers["location"] == f"/task/{task['id']}"

    conn = connect()
    c = conn.cursor()
    helper = c.execute("""
    SELECT id
    FROM users
    WHERE company_id=2 AND username='helper2'
    """).fetchone()
    c.execute("""
    UPDATE users
    SET commission_percent=10
    WHERE company_id=2 AND username='helper2'
    """)
    conn.commit()
    conn.close()

    commission_response = await crm.update_worker_commission(
        make_form_request(
            "owner2",
            f"/workers/{helper['id']}/commission",
            {"commission_percent": "10"},
        ),
        helper["id"],
    )
    assert commission_response.status_code == 302
    assert commission_response.headers["location"] == "/workers?commission_updated=1"

    finance_response = await crm.finance_page(
        make_asgi_request("owner2", "/finance"),
        month="2026-05",
    )
    assert finance_response.status_code == 200
    finance_html = finance_response.body.decode("utf-8")
    assert "Маржа" in finance_html
    assert "68.7%" in finance_html
    assert "Средний чек" in finance_html
    assert "2300.0 ₽" in finance_html
    assert "К оплате" in finance_html
    assert "Скидки" in finance_html
    assert "Начислено ЗП" in finance_html
    assert "Выплачено ЗП" in finance_html
    assert "Остаток ЗП" in finance_html
    assert 'name="sort"' in finance_html
    assert "Финансы по исполнителям" in finance_html
    assert "Payroll" in finance_html
    assert "790.0 ₽" in finance_html
    assert "Выплата" in finance_html
    assert "79.0 ₽ / 10.0%" in finance_html
    assert f"/workers/{helper['id']}?month=2026-05" in finance_html
    assert "Не выплачено" in finance_html
    assert "worker2, helper2" in finance_html
    assert "/payroll?month=2026-05" in finance_html

    payroll_response = await crm.payroll_page(
        make_asgi_request("owner2", "/payroll"),
        month="2026-05",
    )
    assert payroll_response.status_code == 200
    payroll_html = payroll_response.body.decode("utf-8")
    assert "Зарплаты" in payroll_html
    assert "Прибыль к распределению" in payroll_html
    assert "payout_filter=positive" in payroll_html
    assert "79.0 ₽" in payroll_html
    assert "helper2" in payroll_html
    assert "Осталось выплатить" in payroll_html
    assert "Не выплачено" in payroll_html
    assert "Выплатил" in payroll_html
    assert "Журнал выплат" in payroll_html
    assert 'href="#payout-history"' in payroll_html
    assert 'id="payout-history"' in payroll_html
    assert "За месяц выплат ещё нет" in payroll_html
    assert 'name="amount" min="0" step="0.1" value="79.0"' in payroll_html
    assert 'name="note" placeholder="Комментарий"' in payroll_html
    assert 'name="payout_filter" value=""' in payroll_html
    assert "payout_filter=paid" in payroll_html
    assert "payout_filter=partial" in payroll_html
    assert "payout_filter=unpaid" in payroll_html
    assert f"/workers/{helper['id']}?month=2026-05" in payroll_html
    assert "/finance?month=2026-05&worker=helper2" in payroll_html

    positive_payroll_response = await crm.payroll_page(
        make_asgi_request("owner2", "/payroll"),
        month="2026-05",
        payout_filter="positive",
    )
    assert positive_payroll_response.status_code == 200
    positive_payroll_html = positive_payroll_response.body.decode("utf-8")
    assert 'name="payout_filter" value="positive"' in positive_payroll_html
    assert "helper2" in positive_payroll_html
    assert "/payroll/export?month=2026-05" in payroll_html
    assert "/payroll/export?month=2026-05&payout_filter=positive" in positive_payroll_html

    unpaid_payroll_response = await crm.payroll_page(
        make_asgi_request("owner2", "/payroll"),
        month="2026-05",
        payout_filter="unpaid",
    )
    assert unpaid_payroll_response.status_code == 200
    unpaid_payroll_html = unpaid_payroll_response.body.decode("utf-8")
    assert 'name="payout_filter" value="unpaid"' in unpaid_payroll_html
    assert "helper2" in unpaid_payroll_html

    mark_paid_response = await crm.mark_payroll_paid(
        make_form_request(
            "owner2",
            f"/payroll/{helper['id']}/mark-paid",
            {"month": "2026-05", "amount": "70.0", "note": "аванс на карту", "payout_filter": "positive"},
        ),
        helper["id"],
    )
    assert mark_paid_response.status_code == 302
    assert mark_paid_response.headers["location"] == "/payroll?month=2026-05&payout_paid=1&payout_filter=positive"

    paid_payroll_response = await crm.payroll_page(
        make_asgi_request("owner2", "/payroll", "payout_paid=1"),
        month="2026-05",
        payout_filter="positive",
    )
    assert paid_payroll_response.status_code == 200
    paid_payroll_html = paid_payroll_response.body.decode("utf-8")
    assert "Уже выплачено" in paid_payroll_html
    assert "Выплата отмечена" in paid_payroll_html
    assert "Частично" in paid_payroll_html
    assert "Сумма: 70.0 ₽" in paid_payroll_html
    assert "Остаток: 9.0 ₽" in paid_payroll_html
    assert "Кем: owner2" in paid_payroll_html
    assert "Комментарий: аванс на карту" in paid_payroll_html
    assert f'action="/payroll/{helper["id"]}/note"' in paid_payroll_html
    assert 'name="payout_filter" value="positive"' in paid_payroll_html
    assert "Журнал выплат" in paid_payroll_html
    assert "70.0 ₽" in paid_payroll_html
    assert "аванс на карту" in paid_payroll_html
    assert "Отменить" in paid_payroll_html

    note_response = await crm.update_payroll_payout_note(
        make_form_request(
            "owner2",
            f"/payroll/{helper['id']}/note",
            {"month": "2026-05", "note": "наличными", "payout_filter": "partial"},
        ),
        helper["id"],
    )
    assert note_response.status_code == 302
    assert note_response.headers["location"] == "/payroll?month=2026-05&payout_note_updated=1&payout_filter=partial"

    note_page_response = await crm.payroll_page(
        make_asgi_request("owner2", "/payroll", "payout_note_updated=1"),
        month="2026-05",
        payout_filter="partial",
    )
    assert note_page_response.status_code == 200
    note_page_html = note_page_response.body.decode("utf-8")
    assert "Комментарий выплаты обновлён" in note_page_html
    assert "Комментарий: наличными" in note_page_html

    paid_filter_response = await crm.payroll_page(
        make_asgi_request("owner2", "/payroll"),
        month="2026-05",
        payout_filter="paid",
    )
    assert paid_filter_response.status_code == 200
    paid_filter_html = paid_filter_response.body.decode("utf-8")
    assert 'name="payout_filter" value="paid"' in paid_filter_html
    assert "Нет данных по выплатам" in paid_filter_html
    assert "/payroll/export?month=2026-05&payout_filter=paid" in paid_filter_html

    partial_filter_response = await crm.payroll_page(
        make_asgi_request("owner2", "/payroll"),
        month="2026-05",
        payout_filter="partial",
    )
    assert partial_filter_response.status_code == 200
    partial_filter_html = partial_filter_response.body.decode("utf-8")
    assert 'name="payout_filter" value="partial"' in partial_filter_html
    assert "helper2" in partial_filter_html
    assert "Частично" in partial_filter_html
    assert "/payroll/export?month=2026-05&payout_filter=partial" in partial_filter_html

    unpaid_after_paid_response = await crm.payroll_page(
        make_asgi_request("owner2", "/payroll"),
        month="2026-05",
        payout_filter="unpaid",
    )
    assert unpaid_after_paid_response.status_code == 200
    unpaid_after_paid_html = unpaid_after_paid_response.body.decode("utf-8")
    assert "Нет данных по выплатам" in unpaid_after_paid_html

    payroll_export_response = await crm.payroll_export(
        make_request("owner2"),
        month="2026-05",
        payout_filter="partial",
    )
    assert payroll_export_response.status_code == 200
    payroll_csv = payroll_export_response.body.decode("utf-8")
    assert "Итого выплаты" in payroll_csv
    assert "helper2" in payroll_csv
    assert "79.0" in payroll_csv
    assert "Фактически выплачено" in payroll_csv
    assert "70.0" in payroll_csv
    assert "Осталось выплатить" in payroll_csv
    assert "9.0" in payroll_csv
    assert "Статус выплаты" in payroll_csv
    assert "Кем выплачено" in payroll_csv
    assert "Комментарий" in payroll_csv
    assert "owner2" in payroll_csv
    assert "наличными" in payroll_csv
    assert "Частично" in payroll_csv
    assert "Итого выплачено" in payroll_csv
    assert "Итого осталось" in payroll_csv

    paid_worker_detail_response = await crm.worker_detail(
        make_asgi_request("owner2", f"/workers/{helper['id']}"),
        helper["id"],
        month="2026-05",
    )
    assert paid_worker_detail_response.status_code == 200
    paid_worker_detail_html = paid_worker_detail_response.body.decode("utf-8")
    assert "/payroll?month=2026-05&payout_filter=partial" in paid_worker_detail_html
    assert "Частично" in paid_worker_detail_html
    assert "Комментарий выплаты: наличными" in paid_worker_detail_html

    mark_unpaid_response = await crm.mark_payroll_unpaid(
        make_form_request(
            "owner2",
            f"/payroll/{helper['id']}/mark-unpaid",
            {"month": "2026-05", "payout_filter": "partial"},
        ),
        helper["id"],
    )
    assert mark_unpaid_response.status_code == 302
    assert mark_unpaid_response.headers["location"] == "/payroll?month=2026-05&payout_unpaid=1&payout_filter=partial"

    unpaid_again_response = await crm.payroll_page(
        make_asgi_request("owner2", "/payroll", "payout_unpaid=1"),
        month="2026-05",
        payout_filter="unpaid",
    )
    assert unpaid_again_response.status_code == 200
    unpaid_again_html = unpaid_again_response.body.decode("utf-8")
    assert "Отметка выплаты снята" in unpaid_again_html
    assert "helper2" in unpaid_again_html
    assert "Выплатил" in unpaid_again_html
    assert "Все исполнители" in finance_html
    assert "payment_filter=paid" in finance_html
    assert "payment_filter=partial" in finance_html
    assert "payment_filter=unpaid" in finance_html
    assert "profit_filter=loss" in finance_html

    unpaid_response = await crm.finance_page(
        make_asgi_request("owner2", "/finance"),
        month="2026-05",
        payment_filter="unpaid",
    )
    assert unpaid_response.status_code == 200
    unpaid_html = unpaid_response.body.decode("utf-8")
    assert 'name="payment_filter" value="unpaid"' in unpaid_html
    assert "68.7%" in unpaid_html

    worker_response = await crm.finance_page(
        make_asgi_request("owner2", "/finance"),
        month="2026-05",
        worker="helper2",
        sort="profit",
    )
    assert worker_response.status_code == 200
    worker_html = worker_response.body.decode("utf-8")
    assert '<option value="helper2" selected' in worker_html
    assert '<option value="profit" selected' in worker_html
    assert "68.7%" in worker_html

    export_response = await crm.finance_export(
        make_request("owner2"),
        month="2026-05",
        payment_filter="unpaid",
        worker="helper2",
    )
    assert export_response.status_code == 200
    export_csv = export_response.body.decode("utf-8")
    assert "Маржа %" in export_csv
    assert "Скидка" in export_csv
    assert "Финансы по исполнителям" in export_csv
    assert "Payroll статус" in export_csv
    assert "Итого начислено ЗП" in export_csv
    assert "Итого выплачено ЗП" in export_csv
    assert "Итого остаток ЗП" in export_csv
    assert "68.7" in export_csv
    assert "Не выплачено" in export_csv
    assert "worker2, helper2" in export_csv

    original_send_message = crm.send_message
    crm.send_message = lambda text: True

    try:
        payment_response = await crm.update_payment_status(
            make_form_request(
                "owner2",
                f"/task/{task['id']}/payment",
                {"payment_status": "Оплачено"},
            ),
            task["id"],
        )
    finally:
        crm.send_message = original_send_message

    assert payment_response.status_code == 302
    assert payment_response.headers["location"] == f"/task/{task['id']}"

    task_response = await crm.task_detail(
        make_asgi_request("owner2", f"/task/{task['id']}"),
        task["id"],
    )
    assert task_response.status_code == 200
    task_html = task_response.body.decode("utf-8")
    assert "Смета" in task_html
    assert "Smoke service" in task_html
    assert "Manual smoke item" in task_html
    assert "Добавить в смету" in task_html
    assert "Добавить ручную позицию" in task_html
    assert "Обновить цену по смете" in task_html
    assert "1580.0 ₽ / 68.7%" in task_html
    assert "Сохранить скидку" in task_html
    assert "Статус оплаты" in task_html
    assert "Сохранить оплату" in task_html
    assert '<option value="Оплачено" selected' in task_html

    discount_response = await crm.update_task_discount(
        make_form_request(
            "owner2",
            f"/task/{task['id']}/discount",
            {"discount_amount": "100"},
        ),
        task["id"],
    )
    assert discount_response.status_code == 302
    assert discount_response.headers["location"] == f"/task/{task['id']}"

    expense_response = await crm.add_task_expense(
        make_form_request(
            "owner2",
            f"/task/{task['id']}/expenses",
            {
                "title": "Fuel smoke expense",
                "amount": "80",
            },
        ),
        task["id"],
    )
    assert expense_response.status_code == 302
    assert expense_response.headers["location"] == f"/task/{task['id']}"

    discounted_task_response = await crm.task_detail(
        make_asgi_request("owner2", f"/task/{task['id']}"),
        task["id"],
    )
    assert discounted_task_response.status_code == 200
    discounted_task_html = discounted_task_response.body.decode("utf-8")
    assert "Fuel smoke expense" in discounted_task_html
    assert "Добавить расход" in discounted_task_html
    assert "100.0 ₽" in discounted_task_html
    assert "80.0 ₽" in discounted_task_html
    assert "2200.0 ₽" in discounted_task_html
    assert "1400.0 ₽ / 63.6%" in discounted_task_html

    discounted_finance_response = await crm.finance_page(
        make_asgi_request("owner2", "/finance"),
        month="2026-05",
    )
    assert discounted_finance_response.status_code == 200
    discounted_finance_html = discounted_finance_response.body.decode("utf-8")
    assert "2200.0 ₽" in discounted_finance_html
    assert "Скидка: 100.0 ₽" in discounted_finance_html
    assert "Расходы" in discounted_finance_html
    assert "80.0 ₽" in discounted_finance_html
    assert "63.6%" in discounted_finance_html

    loss_response = await crm.finance_page(
        make_asgi_request("owner2", "/finance"),
        month="2026-05",
        profit_filter="loss",
    )
    assert loss_response.status_code == 200
    loss_html = loss_response.body.decode("utf-8")
    assert 'name="profit_filter" value="loss"' in loss_html

    worker_detail_response = await crm.worker_detail(
        make_asgi_request("owner2", f"/workers/{helper['id']}"),
        helper["id"],
        month="2026-05",
    )
    assert worker_detail_response.status_code == 200
    worker_detail_html = worker_detail_response.body.decode("utf-8")
    assert "Финансы за месяц" in worker_detail_html
    assert "/finance?month=2026-05&worker=helper2" in worker_detail_html
    assert "/payroll?month=2026-05&payout_filter=unpaid" in worker_detail_html
    assert "Статус выплаты" in worker_detail_html
    assert "Не выплачено" in worker_detail_html
    assert "700.0 ₽" in worker_detail_html
    assert "70.0 ₽" in worker_detail_html

    apply_response = await crm.apply_task_estimate_total(
        make_request("owner2"),
        task["id"],
    )
    assert apply_response.status_code == 302
    assert apply_response.headers["location"] == f"/task/{task['id']}"

    conn = connect()
    c = conn.cursor()
    updated_task = c.execute("""
    SELECT price
    FROM tasks
    WHERE id=?
    """, (task["id"],)).fetchone()
    conn.close()
    assert updated_task["price"] == "2200.0"


async def assert_notifications(task):
    crm.create_notification(
        2,
        "owner2",
        "Smoke notification",
        "Notification body",
        f"/task/{task['id']}",
    )

    conn = connect()
    c = conn.cursor()
    notification = c.execute("""
    SELECT *
    FROM notifications
    WHERE company_id=2 AND username='owner2'
    ORDER BY id DESC
    """).fetchone()
    conn.close()

    notifications_response = await crm.notifications_page(
        make_asgi_request("owner2", "/notifications")
    )
    assert notifications_response.status_code == 200
    notifications_html = notifications_response.body.decode("utf-8")
    assert f"/notifications/{notification['id']}/open" in notifications_html
    assert "Отметить все прочитанными" in notifications_html

    open_response = await crm.open_notification(
        make_request("owner2"),
        notification["id"],
    )
    assert open_response.status_code == 302
    assert open_response.headers["location"] == f"/task/{task['id']}"

    conn = connect()
    c = conn.cursor()
    opened = c.execute("""
    SELECT is_read
    FROM notifications
    WHERE id=?
    """, (notification["id"],)).fetchone()
    conn.close()

    assert opened["is_read"] == 1

    crm.create_notification(2, "owner2", "Unread one")
    crm.create_notification(2, "owner2", "Unread two")

    read_all_response = await crm.mark_all_notifications_read(make_request("owner2"))
    assert read_all_response.status_code == 302
    assert read_all_response.headers["location"] == "/notifications"

    conn = connect()
    c = conn.cursor()
    unread_count = c.execute("""
    SELECT COUNT(*)
    FROM notifications
    WHERE company_id=2 AND username='owner2' AND is_read=0
    """).fetchone()[0]
    conn.close()

    assert unread_count == 0


async def assert_client_card(task):
    crm.log_task_activity(
        task["id"],
        "owner2",
        "boss",
        "Smoke client timeline",
        "Timeline details",
    )
    active_deadline = (datetime.now() + timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M")
    upcoming_task_date = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")

    conn = connect()
    c = conn.cursor()
    c.execute("""
    UPDATE tasks
    SET deadline_at=?, task_date=?
    WHERE id=?
    """, (active_deadline, upcoming_task_date, task["id"]))
    conn.commit()
    conn.close()

    original_send_message = crm.send_message
    crm.send_message = lambda text: True

    try:
        note_response = await crm.add_client_note(
            make_form_request(
                "owner2",
                f"/clients/{task['client_id']}/notes",
                {"note": "Smoke latest client note"},
            ),
            task["client_id"],
        )
    finally:
        crm.send_message = original_send_message

    assert note_response.status_code == 302

    upload = crm.UploadFile(
        file=crm.io.BytesIO(b"client file"),
        filename="client-contract.txt",
    )
    file_response = await crm.upload_client_file(
        make_request("owner2"),
        task["client_id"],
        upload=upload,
    )
    assert file_response.status_code == 302
    assert file_response.headers["location"] == f"/clients/{task['client_id']}?file_uploaded=1"

    response = await crm.client_detail(
        make_asgi_request("owner2", f"/clients/{task['client_id']}"),
        task["client_id"],
    )
    assert response.status_code == 200
    html = response.body.decode("utf-8")
    assert "Всего: Заявка" in html
    assert "Активные" in html
    assert "Выручка" in html
    assert "task_filter=active" in html
    assert "task_filter=completed" in html
    assert "task_filter=overdue" in html
    assert "Поиск: Заявка" in html
    assert "task_search" in html
    assert "Сортировка" in html
    assert 'name="task_sort"' in html
    assert f'href="/clients/{task["client_id"]}">Сбросить</a>' in html
    assert "Показано:" in html
    assert "Заявка #" in html
    assert ": последнее" in html
    assert ": ближайшее" in html
    assert "latest-task" in html
    assert "worker2, helper2" in html
    assert "Последний контакт" in html
    assert "Последняя заметка" in html
    assert "Следующее действие" in html
    assert "Заявка #" in html
    assert "Smoke latest client note" in html
    assert "Поиск по заметкам" in html
    assert "note_search" in html
    assert "Заметок:" in html
    assert "Создать из заметки: Заявка" in html
    assert "Файлы: Клиент" in html
    assert "client-contract.txt" in html
    assert "Загрузить файл" in html
    assert "Поиск по файлам" in html
    assert "file_search" in html
    assert "Файлов:" in html
    assert "Удалить" in html
    assert 'href="tel:+70000000000"' in html
    assert 'href="mailto:client@example.com"' in html
    assert "Лента активности" in html
    assert "activity_filter=status" in html
    assert "activity_filter=date" in html
    assert "activity_filter=comment" in html
    assert "Событий:" in html
    assert "Smoke client timeline" in html
    assert "Timeline details" in html
    assert "SLA:" in html
    assert "активен" in html
    assert f"/calendar?date={upcoming_task_date}" in html
    assert f"/create-task?client_id={task['client_id']}&return_to=client" in html
    assert f"/create-task?client_id={task['client_id']}&source_task_id={task['id']}&return_to=client" in html
    assert f"#{task['id']}" in html

    create_response = await crm.create_task_page(
        make_asgi_request("owner2", "/create-task"),
        client_id=task["client_id"],
        return_to="client",
    )
    assert create_response.status_code == 200
    create_html = create_response.body.decode("utf-8")
    assert f'name="client_id" value="{task["client_id"]}"' in create_html
    assert 'name="return_to" value="client"' in create_html
    assert 'name="client" placeholder="' in create_html
    assert 'value="Client 2"' in create_html
    assert 'name="phone" placeholder="+1 555 000 0000" value="+70000000000"' in create_html
    assert 'name="address" placeholder="Адрес"' in create_html
    assert 'value="Company 2 address"' in create_html

    repeat_response = await crm.create_task_page(
        make_asgi_request("owner2", "/create-task"),
        client_id=task["client_id"],
        source_task_id=task["id"],
        return_to="client",
    )
    assert repeat_response.status_code == 200
    repeat_html = repeat_response.body.decode("utf-8")
    assert f'name="source_task_id" value="{task["id"]}"' in repeat_html
    assert "Smoke task</textarea>" in repeat_html
    assert 'value="worker2" style="width:auto" checked' in repeat_html

    conn = connect()
    c = conn.cursor()
    client_file = c.execute("""
    SELECT id
    FROM client_files
    WHERE client_id=?
    ORDER BY id DESC
    """, (task["client_id"],)).fetchone()
    latest_note = c.execute("""
    SELECT id
    FROM client_notes
    WHERE client_id=?
    ORDER BY id DESC
    """, (task["client_id"],)).fetchone()
    conn.close()

    file_download_response = await crm.download_client_file(
        make_request("owner2"),
        task["client_id"],
        client_file["id"],
    )
    assert file_download_response.status_code == 200

    file_search_response = await crm.client_detail(
        make_asgi_request("owner2", f"/clients/{task['client_id']}"),
        task["client_id"],
        file_search="contract",
    )
    assert file_search_response.status_code == 200
    file_search_html = file_search_response.body.decode("utf-8")
    assert 'name="file_search" value="contract"' in file_search_html
    assert "client-contract.txt" in file_search_html

    outsider_file_response = await crm.download_client_file(
        make_request("manager1"),
        task["client_id"],
        client_file["id"],
    )
    assert outsider_file_response.status_code == 404

    delete_file_response = await crm.delete_client_file(
        make_request("owner2"),
        task["client_id"],
        client_file["id"],
    )
    assert delete_file_response.status_code == 302
    assert delete_file_response.headers["location"] == f"/clients/{task['client_id']}?file_deleted=1"

    conn = connect()
    c = conn.cursor()
    deleted_file_count = c.execute("""
    SELECT COUNT(*)
    FROM client_files
    WHERE id=?
    """, (client_file["id"],)).fetchone()[0]
    conn.close()
    assert deleted_file_count == 0

    note_task_response = await crm.create_task_page(
        make_asgi_request("owner2", "/create-task"),
        client_id=task["client_id"],
        note_id=latest_note["id"],
        return_to="client",
    )
    assert note_task_response.status_code == 200
    note_task_html = note_task_response.body.decode("utf-8")
    assert f'name="note_id" value="{latest_note["id"]}"' in note_task_html
    assert "Smoke latest client note</textarea>" in note_task_html

    original_send_message = crm.send_message
    original_send_message_to_chat = crm.send_message_to_chat
    crm.send_message = lambda text: True
    crm.send_message_to_chat = lambda chat_id, text: True

    try:
        task_response = await crm.create_task(
            make_multipart_request(
                "owner2",
                "/create-task",
                {
                    "client_id": str(task["client_id"]),
                    "client": "Client 2",
                    "phone": "+70000000000",
                    "address": "Company 2 address",
                    "description": "Created from client card",
                    "task_date": "2026-05-22",
                    "return_to": "client",
                    "priority": "Обычный",
                    "price": "0",
                },
            ),
            photo=None,
        )
    finally:
        crm.send_message = original_send_message
        crm.send_message_to_chat = original_send_message_to_chat

    assert task_response.status_code == 302
    assert task_response.headers["location"] == f"/clients/{task['client_id']}"

    active_response = await crm.client_detail(
        make_asgi_request("owner2", f"/clients/{task['client_id']}"),
        task["client_id"],
        task_filter="active",
    )
    assert active_response.status_code == 200
    active_html = active_response.body.decode("utf-8")
    assert "task-filters" in active_html
    assert "Created from client card" not in active_html

    search_response = await crm.client_detail(
        make_asgi_request("owner2", f"/clients/{task['client_id']}"),
        task["client_id"],
        task_search="Company 2 address",
    )
    assert search_response.status_code == 200
    search_html = search_response.body.decode("utf-8")
    assert 'name="task_search" value="Company 2 address"' in search_html
    assert f"#{task['id']}" in search_html

    sorted_response = await crm.client_detail(
        make_asgi_request("owner2", f"/clients/{task['client_id']}"),
        task["client_id"],
        task_sort="oldest",
    )
    assert sorted_response.status_code == 200
    sorted_html = sorted_response.body.decode("utf-8")
    assert '<option value="oldest" selected>Сначала старые</option>' in sorted_html

    activity_response = await crm.client_detail(
        make_asgi_request("owner2", f"/clients/{task['client_id']}"),
        task["client_id"],
        activity_filter="status",
    )
    assert activity_response.status_code == 200
    activity_html = activity_response.body.decode("utf-8")
    assert "Все события" in activity_html
    assert "Smoke client timeline" not in activity_html

    note_search_response = await crm.client_detail(
        make_asgi_request("owner2", f"/clients/{task['client_id']}"),
        task["client_id"],
        note_search="latest",
    )
    assert note_search_response.status_code == 200
    note_search_html = note_search_response.body.decode("utf-8")
    assert 'name="note_search" value="latest"' in note_search_html
    assert "Smoke latest client note" in note_search_html


async def assert_overdue_sla(task):
    conn = connect()
    c = conn.cursor()
    c.execute("""
    UPDATE tasks
    SET archived=0, status='Новая', task_date='2000-01-01', deadline_at='2000-01-01T10:00'
    WHERE id=?
    """, (task["id"],))
    conn.commit()
    conn.close()

    response = await crm.overdue_page(make_asgi_request("owner2", "/overdue"))
    assert response.status_code == 200
    html = response.body.decode("utf-8")
    assert "Нарушен SLA" in html
    assert f"#{task['id']}" in html
    assert "Создать напоминания по просрочкам" in html
    assert 'href="/automation"' in html

    sla_response = await crm.sla_page(
        make_asgi_request("owner2", "/sla"),
        filter="overdue",
    )
    assert sla_response.status_code == 200
    sla_html = sla_response.body.decode("utf-8")
    assert "Всего: Заявка" in sla_html
    assert "Просрочено" in sla_html
    assert "Просроченные" in sla_html
    assert "Все: Исполнитель" in sla_html
    assert "SLA: Исполнитель" in sla_html
    assert "helper2" in sla_html
    assert f"#{task['id']}" in sla_html

    worker_sla_response = await crm.sla_page(
        make_asgi_request("owner2", "/sla"),
        filter="overdue",
        worker="helper2",
    )
    assert worker_sla_response.status_code == 200
    worker_sla_html = worker_sla_response.body.decode("utf-8")
    assert f"#{task['id']}" in worker_sla_html

    outsider_sla_response = await crm.sla_page(
        make_asgi_request("owner2", "/sla"),
        filter="overdue",
        worker="outsider_worker",
    )
    assert outsider_sla_response.status_code == 200
    outsider_sla_html = outsider_sla_response.body.decode("utf-8")
    assert task["client"] not in outsider_sla_html

    overdue_rule_response = await crm.create_automation_rule(
        make_form_request(
            "owner2",
            "/automation/rules",
            {
                "name": "Overdue runner rule",
                "trigger_key": "overdue_task",
                "action_key": "notification",
                "target_username": "owner2",
                "message": "Overdue automation message",
            },
        )
    )
    assert overdue_rule_response.status_code == 302

    overdue_reminder_response = await crm.create_overdue_reminders(make_request("owner2"))
    assert overdue_reminder_response.status_code == 302
    assert overdue_reminder_response.headers["location"].startswith("/overdue?reminders=1&created=")

    duplicate_overdue_reminder_response = await crm.create_overdue_reminders(make_request("owner2"))
    assert duplicate_overdue_reminder_response.status_code == 302
    assert duplicate_overdue_reminder_response.headers["location"] == "/overdue?reminders=1&created=0"

    conn = connect()
    c = conn.cursor()
    overdue_notification_count = c.execute("""
    SELECT COUNT(*)
    FROM notifications
    WHERE company_id=?
      AND title='🟠 Просрочена задача'
      AND link=?
      AND is_read=0
    """, (2, f"/task/{task['id']}")).fetchone()[0]
    overdue_automation_event = c.execute("""
    SELECT *
    FROM automation_events
    WHERE company_id=?
      AND trigger_key='overdue_task'
      AND entity_type='task'
      AND entity_id=?
    ORDER BY id DESC
    """, (2, task["id"])).fetchone()
    overdue_automation_notification = c.execute("""
    SELECT *
    FROM notifications
    WHERE company_id=?
      AND username='owner2'
      AND title='Overdue runner rule'
      AND link=?
    ORDER BY id DESC
    """, (2, f"/task/{task['id']}")).fetchone()
    conn.close()

    assert overdue_notification_count == 2
    assert overdue_automation_event is not None
    assert overdue_automation_event["status"] == "done"
    assert overdue_automation_notification is not None
    assert overdue_automation_notification["message"] == "Overdue automation message"

    conn = connect()
    c = conn.cursor()
    automation_events_before = c.execute("""
    SELECT COUNT(*)
    FROM automation_events
    WHERE company_id=?
      AND trigger_key='sla_overdue'
      AND entity_type='task'
      AND entity_id=?
    """, (2, task["id"])).fetchone()[0]
    conn.close()

    reminder_response = await crm.create_sla_reminders(make_request("owner2"))
    assert reminder_response.status_code == 302
    assert reminder_response.headers["location"] == "/sla?reminders=1&created=2&filter=overdue"

    duplicate_reminder_response = await crm.create_sla_reminders(make_request("owner2"))
    assert duplicate_reminder_response.status_code == 302
    assert duplicate_reminder_response.headers["location"] == "/sla?reminders=1&created=0&filter=overdue"

    conn = connect()
    c = conn.cursor()
    notification_count = c.execute("""
    SELECT COUNT(*)
    FROM notifications
    WHERE company_id=?
      AND title='🔴 Просрочен SLA'
      AND link=?
      AND is_read=0
    """, (2, f"/task/{task['id']}")).fetchone()[0]

    automation_events_after = c.execute("""
    SELECT COUNT(*)
    FROM automation_events
    WHERE company_id=?
      AND trigger_key='sla_overdue'
      AND entity_type='task'
      AND entity_id=?
    """, (2, task["id"])).fetchone()[0]

    automation_notification = c.execute("""
    SELECT *
    FROM notifications
    WHERE company_id=?
      AND username='owner2'
      AND title='SLA runner rule'
      AND link=?
    ORDER BY id DESC
    """, (2, f"/task/{task['id']}")).fetchone()
    conn.close()

    assert notification_count == 2
    assert automation_events_after >= automation_events_before + 1
    assert automation_notification is not None

    escalation_response = await crm.create_sla_escalations(make_request("manager2"))
    assert escalation_response.status_code == 302
    assert escalation_response.headers["location"] == "/sla?escalations=1&created=1&filter=overdue"

    duplicate_escalation_response = await crm.create_sla_escalations(make_request("manager2"))
    assert duplicate_escalation_response.status_code == 302
    assert duplicate_escalation_response.headers["location"] == "/sla?escalations=1&created=0&filter=overdue"

    conn = connect()
    c = conn.cursor()
    escalation_count = c.execute("""
    SELECT COUNT(*)
    FROM notifications
    WHERE company_id=?
      AND title='🚨 SLA эскалация'
      AND link=?
      AND username=?
      AND is_read=0
    """, (2, f"/task/{task['id']}", "owner2")).fetchone()[0]
    conn.close()

    assert escalation_count == 1

    soon_deadline = (datetime.now() + timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M")
    conn = connect()
    c = conn.cursor()
    c.execute("""
    UPDATE tasks
    SET deadline_at=?
    WHERE id=?
    """, (soon_deadline, task["id"]))
    conn.commit()
    conn.close()

    soon_response = await crm.sla_page(
        make_asgi_request("owner2", "/sla"),
        filter="soon",
    )
    assert soon_response.status_code == 200
    soon_html = soon_response.body.decode("utf-8")
    assert "Горит" in soon_html
    assert "Горит SLA" in soon_html
    assert f"#{task['id']}" in soon_html


async def assert_recurring_generate(task):
    conn = connect()
    c = conn.cursor()

    c.execute("""
    INSERT INTO recurring_jobs (
        company_id, client_id, title, description, interval_type, next_date,
        worker, workers, priority, price, active, created_at
    )
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        2,
        task["client_id"],
        "Smoke recurring",
        "Generated from recurring",
        "monthly",
        "2026-05-17",
        "worker2",
        "worker2,helper2",
        "Обычный",
        "1500",
        1,
        "2026-05-17 10:00",
    ))

    job_id = c.lastrowid
    conn.commit()
    conn.close()

    page_response = await crm.recurring_jobs_page(make_asgi_request("owner2", "/recurring"))
    assert page_response.status_code == 200
    page_html = page_response.body.decode("utf-8")
    assert f"/recurring/{job_id}/generate" in page_html
    assert f"/recurring/{job_id}/toggle" in page_html

    response = await crm.generate_recurring_task(make_request("owner2"), job_id)
    assert response.status_code == 302
    task_location = response.headers["location"]
    assert task_location.startswith("/task/")
    generated_task_id = int(task_location.rsplit("/", 1)[1])

    conn = connect()
    c = conn.cursor()
    generated_task = c.execute("""
    SELECT *
    FROM tasks
    WHERE id=? AND company_id=2
    """, (generated_task_id,)).fetchone()
    job = c.execute("""
    SELECT next_date
    FROM recurring_jobs
    WHERE id=?
    """, (job_id,)).fetchone()
    activity = c.execute("""
    SELECT *
    FROM task_activity
    WHERE task_id=? AND action='Создана из регулярной работы'
    """, (generated_task_id,)).fetchone()
    conn.close()

    assert generated_task is not None
    assert generated_task["client_id"] == task["client_id"]
    assert generated_task["workers"] == "worker2,helper2"
    assert job["next_date"] == "2026-06-17"
    assert activity is not None

    date_response = await crm.update_recurring_job_date(make_form_request(
        "owner2",
        f"/recurring/{job_id}/date",
        {"next_date": "2026-07-01"},
    ), job_id)
    assert date_response.status_code == 302
    assert date_response.headers["location"] == "/recurring?updated=1"

    conn = connect()
    c = conn.cursor()
    updated_job = c.execute("""
    SELECT next_date
    FROM recurring_jobs
    WHERE id=?
    """, (job_id,)).fetchone()
    conn.close()

    assert updated_job["next_date"] == "2026-07-01"

    toggle_response = await crm.toggle_recurring_job(make_request("owner2"), job_id)
    assert toggle_response.status_code == 302
    assert toggle_response.headers["location"] == "/recurring"

    conn = connect()
    c = conn.cursor()
    disabled_job = c.execute("""
    SELECT active
    FROM recurring_jobs
    WHERE id=?
    """, (job_id,)).fetchone()
    conn.close()

    assert disabled_job["active"] == 0

    disabled_generate_response = await crm.generate_recurring_task(
        make_request("owner2"),
        job_id,
    )
    assert disabled_generate_response.status_code == 302
    assert disabled_generate_response.headers["location"] == "/recurring"


async def assert_custom_fields():
    response = await crm.create_custom_field(make_form_request(
        "owner2",
        "/custom-fields",
        {
            "entity_type": "task",
            "field_type": "text",
            "label": "VIN",
            "is_required": "on",
            "sort_order": "7",
        },
    ))
    assert response.status_code == 302
    assert response.headers["location"] == "/custom-fields?created=1"

    select_response = await crm.create_custom_field(make_form_request(
        "owner2",
        "/custom-fields",
        {
            "entity_type": "client",
            "field_type": "select",
            "label": "Client segment",
            "options": "Beauty\nAuto service\nLogistics",
            "sort_order": "8",
        },
    ))
    assert select_response.status_code == 302
    assert select_response.headers["location"] == "/custom-fields?created=1"

    empty_select_response = await crm.create_custom_field(make_form_request(
        "owner2",
        "/custom-fields",
        {
            "entity_type": "client",
            "field_type": "select",
            "label": "Empty select",
            "options": "",
        },
    ))
    assert empty_select_response.status_code == 302
    assert empty_select_response.headers["location"] == "/custom-fields?error=options"

    conn = connect()
    c = conn.cursor()
    field = c.execute("""
    SELECT *
    FROM custom_fields
    WHERE company_id=2 AND label='VIN'
    """).fetchone()
    select_field = c.execute("""
    SELECT *
    FROM custom_fields
    WHERE company_id=2 AND label='Client segment'
    """).fetchone()
    conn.close()

    assert field is not None
    assert field["entity_type"] == "task"
    assert field["is_required"] == 1
    assert field["sort_order"] == 7
    assert select_field is not None
    assert select_field["field_type"] == "select"
    assert select_field["options"] == "Beauty\nAuto service\nLogistics"

    page_response = await crm.custom_fields_page(
        make_asgi_request("owner2", "/custom-fields")
    )
    assert page_response.status_code == 200
    page_html = page_response.body.decode("utf-8")
    assert "VIN" in page_html
    assert f"/custom-fields/{field['id']}/toggle" in page_html
    assert f"/custom-fields/{field['id']}/order" in page_html

    order_response = await crm.update_custom_field_order(make_form_request(
        "owner2",
        f"/custom-fields/{field['id']}/order",
        {
            "sort_order": "3",
        },
    ), field["id"])
    assert order_response.status_code == 302
    assert order_response.headers["location"] == "/custom-fields?ordered=1"

    toggle_response = await crm.toggle_custom_field(make_request("owner2"), field["id"])
    assert toggle_response.status_code == 302
    assert toggle_response.headers["location"] == "/custom-fields"

    conn = connect()
    c = conn.cursor()
    toggled = c.execute("""
    SELECT active, sort_order
    FROM custom_fields
    WHERE id=?
    """, (field["id"],)).fetchone()
    conn.close()

    assert toggled["active"] == 0
    assert toggled["sort_order"] == 3


async def assert_client_custom_fields():
    conn = connect()
    c = conn.cursor()
    c.execute("""
    INSERT INTO custom_fields (
        company_id, entity_type, label, field_type, is_required,
        active, sort_order, created_at
    )
    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        2,
        "client",
        "Industry",
        "text",
        0,
        1,
        1,
        "2026-05-19 11:00",
    ))
    field_id = c.lastrowid
    conn.commit()
    conn.close()

    page_response = await crm.clients_page(make_asgi_request("owner2", "/clients"))
    assert page_response.status_code == 200
    page_html = page_response.body.decode("utf-8")
    assert "Industry" in page_html
    assert f"custom_field_{field_id}" in page_html
    assert "Заявок:" in page_html
    assert "Активных:" in page_html
    assert "Последняя заявка:" in page_html
    assert "Выручка:" in page_html
    assert "Поиск клиентов" in page_html
    assert "client_filter=active" in page_html
    assert "client_filter=overdue" in page_html
    assert "client_filter=empty" in page_html
    assert 'name="client_sort"' in page_html

    search_response = await crm.clients_page(
        make_asgi_request("owner2", "/clients"),
        search="Client 2",
        client_sort="name",
    )
    assert search_response.status_code == 200
    search_html = search_response.body.decode("utf-8")
    assert 'name="search" value="Client 2"' in search_html
    assert '<option value="name" selected' in search_html
    assert "Client 2" in search_html

    filtered_response = await crm.clients_page(
        make_asgi_request("owner2", "/clients"),
        client_filter="active",
    )
    assert filtered_response.status_code == 200
    filtered_html = filtered_response.body.decode("utf-8")
    assert 'name="client_filter" value="active"' in filtered_html

    original_send_message = crm.send_message
    crm.send_message = lambda text: True

    try:
        response = await crm.create_client(make_form_request(
            "owner2",
            "/clients",
            {
                "name": "Custom Field Client Company",
                "phone": "+70000000002",
                "email": "custom-client@example.com",
                "address": "Client Address",
                "notes": "Client note",
                f"custom_field_{field_id}": "Beauty",
            },
        ))
    finally:
        crm.send_message = original_send_message

    assert response.status_code == 302
    assert response.headers["location"] == "/clients?created=1"

    conn = connect()
    c = conn.cursor()
    value = c.execute("""
    SELECT custom_field_values.*, clients.id AS client_id
    FROM custom_field_values
    JOIN clients ON clients.id=custom_field_values.entity_id
    WHERE custom_field_values.field_id=?
      AND custom_field_values.entity_type='client'
      AND custom_field_values.value=?
      AND clients.name=?
      AND clients.company_id=?
    """, (field_id, "Beauty", "Custom Field Client Company", 2)).fetchone()
    conn.close()

    assert value is not None

    detail_response = await crm.client_detail(
        make_asgi_request("owner2", f"/clients/{value['client_id']}"),
        value["client_id"],
    )
    assert detail_response.status_code == 200
    detail_html = detail_response.body.decode("utf-8")
    assert "Industry" in detail_html
    assert "Beauty" in detail_html

    original_send_message = crm.send_message
    crm.send_message = lambda text: True

    try:
        edit_response = await crm.edit_client(
            make_form_request(
                "owner2",
                f"/clients/{value['client_id']}/edit",
                {
                    "name": "Custom Field Client Company",
                    "phone": "+70000000002",
                    "email": "custom-client@example.com",
                    "address": "Client Address",
                    "notes": "Client note",
                    f"custom_field_{field_id}": "Auto service",
                },
            ),
            value["client_id"],
        )
    finally:
        crm.send_message = original_send_message
    assert edit_response.status_code == 302
    assert edit_response.headers["location"] == f"/clients/{value['client_id']}?updated=1"

    conn = connect()
    c = conn.cursor()
    updated_value = c.execute("""
    SELECT value
    FROM custom_field_values
    WHERE field_id=?
      AND entity_type='client'
      AND entity_id=?
    """, (field_id, value["client_id"])).fetchone()
    conn.close()

    assert updated_value["value"] == "Auto service"


async def assert_task_custom_fields():
    conn = connect()
    c = conn.cursor()
    c.execute("""
    INSERT INTO custom_fields (
        company_id, entity_type, label, field_type, is_required,
        active, sort_order, created_at
    )
    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        2,
        "task",
        "Route",
        "text",
        0,
        1,
        1,
        "2026-05-19 10:00",
    ))
    field_id = c.lastrowid
    c.execute("""
    UPDATE custom_fields
    SET group_name=?
    WHERE id=?
    """, ("Маршрут", field_id))
    c.execute("""
    INSERT INTO custom_fields (
        company_id, entity_type, label, field_type, is_required,
        active, sort_order, created_at
    )
    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        2,
        "task",
        "Gate code",
        "text",
        0,
        1,
        2,
        "2026-05-19 10:01",
    ))
    empty_field_id = c.lastrowid
    conn.commit()
    conn.close()

    page_response = await crm.create_task_page(
        make_asgi_request("owner2", "/create-task"),
        task_date="2026-05-17",
        worker="worker2",
        return_to="calendar",
    )
    assert page_response.status_code == 200
    page_html = page_response.body.decode("utf-8")
    assert "Route" in page_html
    assert f"custom_field_{field_id}" in page_html
    assert 'name="task_date" type="date" value="2026-05-17"' in page_html
    assert 'value="worker2" style="width:auto" checked' in page_html
    assert 'name="return_to" value="calendar"' in page_html
    assert "уже есть активные заявки" in page_html
    assert "/task/" in page_html
    assert "Client 2 / Новая" in page_html
    assert "Альтернатива: free2" in page_html
    assert "free2 свободен" in page_html
    assert "Выбрать альтернативу" in page_html
    assert "/create-task?task_date=2026-05-17&amp;worker=free2&amp;return_to=calendar" in page_html

    original_send_message = crm.send_message
    original_send_message_to_chat = crm.send_message_to_chat
    crm.send_message = lambda text: True
    crm.send_message_to_chat = lambda chat_id, text: True

    try:
        response = await crm.create_task(
            make_multipart_request(
                "owner2",
                "/create-task",
                {
                    "client": "Custom Field Client",
                    "phone": "+70000000001",
                    "address": "Custom Address",
                    "description": "Custom task",
                    "task_date": "2026-05-20",
                    "workers": ["worker2"],
                    "return_to": "calendar",
                    "priority": "Обычный",
                    "price": "500",
                    f"custom_field_{field_id}": "Moscow - Tula",
                },
            ),
            photo=None,
        )
    finally:
        crm.send_message = original_send_message
        crm.send_message_to_chat = original_send_message_to_chat

    assert response.status_code == 302
    assert response.headers["location"] == "/calendar?date=2026-05-20&worker=worker2"

    conn = connect()
    c = conn.cursor()
    value = c.execute("""
    SELECT custom_field_values.*, tasks.id AS task_id
    FROM custom_field_values
    JOIN tasks ON tasks.id=custom_field_values.entity_id
    WHERE custom_field_values.field_id=?
      AND custom_field_values.value=?
      AND tasks.client=?
    """, (field_id, "Moscow - Tula", "Custom Field Client")).fetchone()
    conn.close()

    assert value is not None

    detail_response = await crm.task_detail(
        make_asgi_request("owner2", f"/task/{value['task_id']}"),
        value["task_id"],
    )
    assert detail_response.status_code == 200
    detail_html = detail_response.body.decode("utf-8")
    assert "Маршрут" in detail_html
    assert "Route" in detail_html
    assert "Moscow - Tula" in detail_html
    assert "Gate code" in detail_html
    assert "Не заполнено" in detail_html

    edit_response = await crm.update_task_custom_field(
        make_form_request(
            "owner2",
            f"/task/{value['task_id']}/custom-field",
            {
                "field_id": str(field_id),
                "value": "Moscow - Kazan",
            },
        ),
        value["task_id"],
    )
    assert edit_response.status_code == 302
    assert edit_response.headers["location"] == f"/task/{value['task_id']}"

    conn = connect()
    c = conn.cursor()
    updated_value = c.execute("""
    SELECT value
    FROM custom_field_values
    WHERE field_id=?
      AND entity_type='task'
      AND entity_id=?
    """, (field_id, value["task_id"])).fetchone()
    activity = c.execute("""
    SELECT *
    FROM task_activity
    WHERE task_id=?
      AND action='Изменено доп. поле'
    """, (value["task_id"],)).fetchone()
    conn.close()

    assert updated_value["value"] == "Moscow - Kazan"
    assert activity is not None

    updated_detail_response = await crm.task_detail(
        make_asgi_request("owner2", f"/task/{value['task_id']}"),
        value["task_id"],
    )
    assert updated_detail_response.status_code == 200
    updated_detail_html = updated_detail_response.body.decode("utf-8")
    assert "Moscow - Kazan" in updated_detail_html

    fill_empty_response = await crm.update_task_custom_field(
        make_form_request(
            "owner2",
            f"/task/{value['task_id']}/custom-field",
            {
                "field_id": str(empty_field_id),
                "value": "42",
            },
        ),
        value["task_id"],
    )
    assert fill_empty_response.status_code == 302
    assert fill_empty_response.headers["location"] == f"/task/{value['task_id']}"

    conn = connect()
    c = conn.cursor()
    filled_value = c.execute("""
    SELECT value
    FROM custom_field_values
    WHERE field_id=?
      AND entity_type='task'
      AND entity_id=?
    """, (empty_field_id, value["task_id"])).fetchone()
    conn.close()

    assert filled_value["value"] == "42"


async def assert_required_custom_fields():
    conn = connect()
    c = conn.cursor()
    c.execute("""
    INSERT INTO custom_fields (
        company_id, entity_type, label, field_type, is_required,
        active, sort_order, created_at
    )
    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        2,
        "client",
        "Required client code",
        "text",
        1,
        1,
        10,
        "2026-05-19 12:00",
    ))
    required_client_field_id = c.lastrowid
    c.execute("""
    INSERT INTO custom_fields (
        company_id, entity_type, label, field_type, is_required,
        active, sort_order, created_at
    )
    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        2,
        "task",
        "Required task code",
        "text",
        1,
        1,
        10,
        "2026-05-19 12:01",
    ))
    required_task_field_id = c.lastrowid
    client = c.execute("""
    SELECT *
    FROM clients
    WHERE company_id=?
    ORDER BY id
    LIMIT 1
    """, (2,)).fetchone()
    task = c.execute("""
    SELECT *
    FROM tasks
    WHERE company_id=?
    ORDER BY id
    LIMIT 1
    """, (2,)).fetchone()
    conn.commit()
    conn.close()

    client_response = await crm.create_client(make_form_request(
        "owner2",
        "/clients",
        {
            "name": "Missing Required Custom Field Client",
            "phone": "",
            "email": "",
            "address": "",
            "notes": "",
        },
    ))
    assert client_response.status_code == 302
    assert client_response.headers["location"] == "/clients?error=custom_required"

    task_response = await crm.create_task(
        make_multipart_request(
            "owner2",
            "/create-task",
            {
                "client": "Missing Required Custom Field Task",
                "phone": "",
                "address": "",
                "description": "",
                "task_date": "2026-05-20",
                "workers": ["worker2"],
                "return_to": "calendar",
                "priority": "Обычный",
                "price": "0",
            },
        ),
        photo=None,
    )
    assert task_response.status_code == 302
    assert task_response.headers["location"] == "/create-task?error=custom_required&task_date=2026-05-20&worker=worker2&return_to=calendar"

    conn = connect()
    c = conn.cursor()
    client_note = c.execute("""
    SELECT id
    FROM client_notes
    WHERE client_id=?
    ORDER BY id DESC
    """, (client["id"],)).fetchone()
    conn.close()

    task_note_response = await crm.create_task(
        make_multipart_request(
            "owner2",
            "/create-task",
            {
                "client_id": str(client["id"]),
                "note_id": str(client_note["id"]),
                "client": client["name"],
                "phone": client["phone"] or "",
                "address": client["address"] or "",
                "description": "Missing required from note",
                "task_date": "2026-05-20",
                "return_to": "client",
                "priority": "Обычный",
                "price": "0",
            },
        ),
        photo=None,
    )
    assert task_note_response.status_code == 302
    assert task_note_response.headers["location"] == f"/create-task?error=custom_required&task_date=2026-05-20&return_to=client&client_id={client['id']}&note_id={client_note['id']}"

    edit_client_response = await crm.edit_client(
        make_form_request(
            "owner2",
            f"/clients/{client['id']}/edit",
            {
                "name": client["name"],
                "phone": client["phone"] or "",
                "email": client["email"] or "",
                "address": client["address"] or "",
                "notes": client["notes"] or "",
                f"custom_field_{required_client_field_id}": "",
            },
        ),
        client["id"],
    )
    assert edit_client_response.status_code == 302
    assert edit_client_response.headers["location"] == f"/clients/{client['id']}?error=custom_required"

    update_task_response = await crm.update_task_custom_field(
        make_form_request(
            "owner2",
            f"/task/{task['id']}/custom-field",
            {
                "field_id": str(required_task_field_id),
                "value": "",
            },
        ),
        task["id"],
    )
    assert update_task_response.status_code == 302
    assert update_task_response.headers["location"] == f"/task/{task['id']}?error=custom_required"


def main():
    try:
        task = seed_data()
        assert_session_cookie_auth()
        assert_task_access(task)
        assert_automation_foundation()
        asyncio.run(assert_automation_page())
        asyncio.run(assert_automation_runner(task))
        asyncio.run(assert_automation_delete())
        asyncio.run(assert_upload_access())
        asyncio.run(assert_calendar_access())
        asyncio.run(assert_archive_restore(task))
        asyncio.run(assert_catalog_create())
        asyncio.run(assert_finance_margin(task))
        asyncio.run(assert_notifications(task))
        asyncio.run(assert_client_card(task))
        asyncio.run(assert_overdue_sla(task))
        asyncio.run(assert_recurring_generate(task))
        asyncio.run(assert_custom_fields())
        asyncio.run(assert_client_custom_fields())
        asyncio.run(assert_task_custom_fields())
        asyncio.run(assert_required_custom_fields())
        assert_company_features()
        print("Smoke checks passed.")
    finally:
        TEMP_DATA.cleanup()


if __name__ == "__main__":
    main()
