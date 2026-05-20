import asyncio
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


def make_asgi_request(username, path="/calendar"):
    cookie = f"{crm.SESSION_COOKIE_NAME}={crm.sign_session_value(username)}"

    return Request({
        "type": "http",
        "method": "GET",
        "path": path,
        "headers": [(b"cookie", cookie.encode("utf-8"))],
        "query_string": b"",
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

    response = await crm.client_detail(
        make_asgi_request("owner2", f"/clients/{task['client_id']}"),
        task["client_id"],
    )
    assert response.status_code == 200
    html = response.body.decode("utf-8")
    assert "Всего заявок" in html
    assert "Активные" in html
    assert "Выручка" in html
    assert "task_filter=active" in html
    assert "task_filter=completed" in html
    assert "task_filter=overdue" in html
    assert "Лента активности" in html
    assert "Smoke client timeline" in html
    assert "Timeline details" in html
    assert f"/create-task?client_id={task['client_id']}&return_to=client" in html
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
    assert 'name="client" placeholder="Имя клиента" value="Client 2"' in create_html
    assert 'name="phone" placeholder="+1 555 000 0000" value="+70000000000"' in create_html
    assert 'name="address" placeholder="Адрес объекта" value="Company 2 address"' in create_html

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

    sla_response = await crm.sla_page(
        make_asgi_request("owner2", "/sla"),
        filter="overdue",
    )
    assert sla_response.status_code == 200
    sla_html = sla_response.body.decode("utf-8")
    assert "Всего SLA" in sla_html
    assert "Просрочено" in sla_html
    assert "Просроченные" in sla_html
    assert "Все исполнители" in sla_html
    assert "SLA по исполнителям" in sla_html
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
    conn.close()

    assert notification_count == 2

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
        asyncio.run(assert_upload_access())
        asyncio.run(assert_calendar_access())
        asyncio.run(assert_archive_restore(task))
        asyncio.run(assert_catalog_create())
        asyncio.run(assert_notifications(task))
        asyncio.run(assert_client_card(task))
        asyncio.run(assert_overdue_sla(task))
        asyncio.run(assert_recurring_generate(task))
        asyncio.run(assert_custom_fields())
        asyncio.run(assert_client_custom_fields())
        asyncio.run(assert_task_custom_fields())
        asyncio.run(assert_required_custom_fields())
        print("Smoke checks passed.")
    finally:
        TEMP_DATA.cleanup()


if __name__ == "__main__":
    main()
