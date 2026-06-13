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
from app.services.daily_schedule import (  # noqa: E402
    build_day_readiness,
    find_common_time_slot,
)


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


def make_json_request(username, path, data):
    body = json.dumps(data).encode("utf-8")
    headers = [
        (b"content-type", b"application/json"),
        (b"content-length", str(len(body)).encode("utf-8")),
    ]

    if username:
        cookie = (
            f"{crm.SESSION_COOKIE_NAME}="
            f"{crm.sign_session_value(username)}"
        )
        headers.insert(0, (b"cookie", cookie.encode("utf-8")))

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
        "headers": headers,
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
          AND name IN (
              'automation_rules',
              'automation_actions',
              'automation_action_runs',
              'automation_events',
              'ai_assistant_notes',
              'ai_assistant_events'
          )
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
              'idx_automation_action_runs_source',
              'idx_automation_events_company_status',
              'idx_ai_assistant_notes_company_created',
              'idx_ai_assistant_events_company_created'
          )
        """).fetchall()
    }

    ai_note_columns = {
        row["name"]
        for row in c.execute("PRAGMA table_info(ai_assistant_notes)").fetchall()
    }

    conn.close()

    assert table_names == {
        "automation_rules",
        "automation_actions",
        "automation_action_runs",
        "automation_events",
        "ai_assistant_notes",
        "ai_assistant_events",
    }
    assert index_names == {
        "idx_automation_rules_company_active",
        "idx_automation_actions_rule",
        "idx_automation_action_runs_source",
        "idx_automation_events_company_status",
        "idx_ai_assistant_notes_company_created",
        "idx_ai_assistant_events_company_created",
    }
    assert "priority" in ai_note_columns
    assert "follow_up_date" in ai_note_columns
    assert "last_notified_at" in ai_note_columns
    assert "notification_count" in ai_note_columns
    assert "created_task_id" in ai_note_columns


async def assert_automation_page():
    conn = connect()
    c = conn.cursor()
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    c.execute("""
    INSERT INTO catalog_items (
        company_id, item_type, name, unit, price, cost, active, created_at
    )
    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (2, "service", "Automation service", "шт", 2000, 500, 1, now))
    automation_catalog_item_id = c.lastrowid
    c.execute("""
    INSERT INTO catalog_items (
        company_id, item_type, name, unit, price, cost, active, created_at
    )
    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (1, "service", "Outsider service", "шт", 3000, 700, 1, now))
    outsider_catalog_item_id = c.lastrowid
    conn.commit()
    conn.close()

    response = await crm.automation_page(make_asgi_request("owner2", "/automation"))
    assert response.status_code == 200
    html = response.body.decode("utf-8")
    assert "Автоматизация" in html
    assert "Новое правило" in html
    assert "Правил пока нет" in html
    assert "Просрочен SLA" in html
    assert "Создать уведомление" in html
    assert "Telegram-уведомление" in html
    assert "Всего правил" in html
    assert "Включено правил" in html
    assert "Событий сегодня" in html
    assert "Событий выполнено" in html
    assert "Успешность" in html
    assert "Последнее событие" in html
    assert "Состояние автоматизации" in html
    assert any(status in html for status in ("OK", "Нужно внимание", "Проблема"))
    assert "AI-планировщик" in html
    assert "AI-контроля" in html
    assert 'action="/automation/ai-digest/run"' in html
    assert 'href="/automation/rules/export"' in html
    assert 'href="/automation/events/export"' in html
    assert "Показано событий:" in html
    assert "Плановый запуск" in html
    assert "дневных и недельных AI-сводок" in html
    assert "AUTOMATION_CRON_SECRET" in html
    assert "заголовком x-automation-secret" in html
    assert "POST /automation/cron/ai-digest" in html
    assert 'href="/automation/diagnostics"' in html

    diagnostics_response = await crm.automation_diagnostics_page(
        make_asgi_request("owner2", "/automation/diagnostics")
    )
    assert diagnostics_response.status_code == 200
    diagnostics_html = diagnostics_response.body.decode("utf-8")
    assert "Диагностика автоматизации" in diagnostics_html
    assert "Оценка состояния A3" in diagnostics_html
    assert "Рекомендация:" in diagnostics_html
    assert "Проблемы и рекомендации" in diagnostics_html
    assert "Активные правила без действий" in diagnostics_html
    assert "Последние пропущенные события" in diagnostics_html
    assert "Повторить" in diagnostics_html
    assert 'href="/automation/diagnostics/export"' in diagnostics_html

    diagnostics_export_response = await crm.automation_diagnostics_export(
        make_request("owner2")
    )
    assert diagnostics_export_response.status_code == 200
    diagnostics_export_csv = diagnostics_export_response.body.decode("utf-8")
    assert "section,id,name_or_rule,trigger_key" in diagnostics_export_csv

    assert "Повторить пропущенные события" in diagnostics_html
    assert 'action="/automation/diagnostics/retry-skipped"' in diagnostics_html

    assert "Отключённые правила" in diagnostics_html

    conn = connect()
    c = conn.cursor()

    disabled_rule = c.execute("""
    SELECT id
    FROM automation_rules
    WHERE company_id=2
      AND active=0
    ORDER BY id DESC
    """).fetchone()

    conn.close()

    if disabled_rule:
        assert "Включить" in diagnostics_html
        assert "/automation/diagnostics/rules/" in diagnostics_html

        enable_response = await crm.enable_automation_rule_from_diagnostics(
            make_request("owner2"),
            disabled_rule["id"],
        )
        assert enable_response.status_code == 302
        assert enable_response.headers["location"] == "/automation/diagnostics?enabled=1"

    conn = connect()
    c = conn.cursor()

    c.execute("""
    INSERT INTO automation_rules (
        company_id, name, trigger_key, conditions_json,
        active, created_by, created_at, updated_at
    )
    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        2,
        "Diagnostics no-action smoke",
        "weekly_digest",
        "{}",
        1,
        "owner2",
        "2026-01-01 10:00",
        "2026-01-01 10:00",
    ))

    no_action_rule_id = c.lastrowid

    conn.commit()
    conn.close()

    add_action_response = await crm.add_default_action_to_rule(
        make_request("owner2"),
        no_action_rule_id,
    )
    assert add_action_response.status_code == 302
    assert add_action_response.headers["location"] == "/automation/diagnostics?action_added=1"

    conn = connect()
    c = conn.cursor()

    added_action = c.execute("""
    SELECT *
    FROM automation_actions
    WHERE company_id=2
      AND rule_id=?
      AND action_key='notification'
      AND active=1
    """, (no_action_rule_id,)).fetchone()

    conn.close()

    assert added_action is not None
    assert "Diagnostics no-action smoke" in added_action["payload_json"]

    retry_skipped_response = await crm.retry_skipped_automation_events(
        make_request("owner2")
    )
    assert retry_skipped_response.status_code == 302
    assert retry_skipped_response.headers["location"].startswith(
        "/automation/diagnostics?retry_skipped=1&retried="
    )

    cleanup_response = await crm.cleanup_automation_events(
        make_request("owner2")
    )
    assert cleanup_response.status_code == 302
    assert cleanup_response.headers["location"].startswith("/automation/diagnostics?cleanup=1&deleted=")

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
    assert "/automation/builder" in list_html
    assert 'id="new-rule"' in list_html
    assert f"/automation/rules/{rule['id']}/toggle" in list_html
    assert f"/automation/rules/{rule['id']}/edit" in list_html
    assert f"/automation/rules/{rule['id']}" in list_html
    assert "Открыть правило" in list_html

    rule_detail_response = await crm.automation_rule_detail(
        make_asgi_request("owner2", f"/automation/rules/{rule['id']}"),
        rule["id"],
    )
    assert rule_detail_response.status_code == 200
    rule_detail_html = rule_detail_response.body.decode("utf-8")
    assert "SLA smoke rule" in rule_detail_html
    assert "Граф автоматизации A3" in rule_detail_html
    assert "Статус цепочки" in rule_detail_html
    assert "Оценка A3" in rule_detail_html
    assert "A3 Анализ" in rule_detail_html
    assert "Рекомендация:" in rule_detail_html
    assert "Действия цепочки" in rule_detail_html
    assert "Последние события цепочки" in rule_detail_html
    assert "Быстрые действия цепочки" in rule_detail_html

    builder_response = await crm.automation_builder_page(
        make_asgi_request("owner2", "/automation/builder")
    )
    assert builder_response.status_code == 200
    builder_html = builder_response.body.decode("utf-8")
    assert "A3 Конструктор цепочек" in builder_html
    assert "Триггер" in builder_html
    assert "Условия" in builder_html
    assert "Действия" in builder_html
    assert "Проверка" in builder_html
    assert "Runtime debug" in builder_html
    assert "/automation#new-rule" in builder_html
    assert f"/automation/rules/{rule['id']}/conditions" in builder_html
    assert f"/automation/rules/{rule['id']}/test-condition" in builder_html
    assert "Сохранить условия" in builder_html
    assert "Проверить условие" in builder_html
    assert "Выберите заявку для теста" in builder_html
    assert 'name="condition_operator"' in builder_html
    assert 'name="condition_secondary_mode"' in builder_html
    assert 'name="condition_tertiary_mode"' in builder_html
    assert 'name="condition_value"' in builder_html
    assert 'name="condition_secondary_value"' in builder_html
    assert 'name="condition_tertiary_value"' in builder_html
    assert 'name="condition_worker"' in builder_html
    assert 'name="condition_secondary_worker"' in builder_html
    assert 'name="condition_tertiary_worker"' in builder_html
    assert 'name="condition_client"' in builder_html
    assert 'name="condition_secondary_client"' in builder_html
    assert 'name="condition_tertiary_client"' in builder_html
    assert 'name="condition_catalog"' in builder_html
    assert 'name="condition_secondary_catalog"' in builder_html
    assert 'name="condition_tertiary_catalog"' in builder_html
    assert 'name="condition_text"' in builder_html
    assert 'name="condition_secondary_text"' in builder_html
    assert 'name="condition_tertiary_text"' in builder_html
    assert "Только выбранный исполнитель" in builder_html
    assert "Только выбранный клиент" in builder_html
    assert "Только выбранная позиция каталога" in builder_html
    assert "Текст заявки содержит" in builder_html
    assert 'value="helper2"' in builder_html
    assert "Client 2" in builder_html
    assert "Automation service" in builder_html
    assert "Outsider service" not in builder_html
    assert "И — выполнить все" in builder_html
    assert "ИЛИ — выполнить любое" in builder_html
    assert "Только высокий приоритет" in builder_html
    assert "Только неоплаченные заявки" in builder_html
    assert "Только заявки в работе" in builder_html
    assert "Только задачи с исполнителем" in builder_html
    assert "Только задачи на сегодня" in builder_html
    assert "Только просроченные задачи" in builder_html
    assert 'optgroup label="Статус заявки"' in builder_html
    assert 'optgroup label="Оплата"' in builder_html
    assert 'optgroup label="Исполнители"' in builder_html
    assert 'optgroup label="Дата"' in builder_html
    assert "Быстрые шаблоны" in builder_html
    assert "Фильтры конструктора" in builder_html
    assert "filterBuilderChains" in builder_html
    assert 'data-builder-chain="1"' in builder_html
    assert "Без действий" in builder_html
    assert "SLA → уведомление" in builder_html
    assert "Просрочка → Telegram" in builder_html
    assert "Ежедневная AI-сводка" in builder_html
    assert 'name="trigger_key" value="sla_overdue"' in builder_html
    assert 'name="action_key" value="telegram_alert"' in builder_html
    assert 'name="action_key" value="ai_digest"' in builder_html
    assert f"/automation/rules/{rule['id']}" in builder_html

    conditions_response = await crm.update_automation_rule_conditions(
        make_form_request(
            "owner2",
            f"/automation/rules/{rule['id']}/conditions",
            {
                "condition_mode": "priority_high",
            },
        ),
        rule["id"],
    )
    assert conditions_response.status_code == 302
    assert conditions_response.headers["location"] == "/automation/builder?conditions_updated=1"

    conn = connect()
    c = conn.cursor()
    updated_conditions = c.execute("""
    SELECT conditions_json
    FROM automation_rules
    WHERE id=?
    """, (rule["id"],)).fetchone()
    conn.close()

    assert "priority_high" in updated_conditions["conditions_json"]

    combined_conditions_response = await crm.update_automation_rule_conditions(
        make_form_request(
            "owner2",
            f"/automation/rules/{rule['id']}/conditions",
            {
                "condition_mode": "priority_high",
                "condition_operator": "and",
                "condition_secondary_mode": "payment_unpaid",
                "condition_tertiary_mode": "date_today",
            },
        ),
        rule["id"],
    )
    assert combined_conditions_response.status_code == 302
    assert combined_conditions_response.headers["location"] == "/automation/builder?conditions_updated=1"

    conn = connect()
    c = conn.cursor()
    combined_conditions = c.execute("""
    SELECT conditions_json
    FROM automation_rules
    WHERE id=?
    """, (rule["id"],)).fetchone()
    conn.close()

    combined_payload = json.loads(combined_conditions["conditions_json"])
    assert combined_payload["operator"] == "and"
    assert [item["mode"] for item in combined_payload["conditions"]] == [
        "priority_high",
        "payment_unpaid",
        "date_today",
    ]

    combined_builder_response = await crm.automation_builder_page(
        make_asgi_request("owner2", "/automation/builder")
    )
    combined_builder_html = combined_builder_response.body.decode("utf-8")
    assert (
        "Только высокий приоритет и Только неоплаченные заявки"
        " и Только задачи на сегодня"
    ) in combined_builder_html
    assert '<option value="and" selected' in combined_builder_html

    custom_threshold_response = await crm.update_automation_rule_conditions(
        make_form_request(
            "owner2",
            f"/automation/rules/{rule['id']}/conditions",
            {
                "condition_mode": "price_high",
                "condition_value": "25000",
            },
        ),
        rule["id"],
    )
    assert custom_threshold_response.status_code == 302

    conn = connect()
    c = conn.cursor()
    custom_threshold = json.loads(c.execute("""
    SELECT conditions_json
    FROM automation_rules
    WHERE id=?
    """, (rule["id"],)).fetchone()["conditions_json"])
    conn.close()

    assert custom_threshold["value"] == "25000"
    assert custom_threshold["label"] == "Цена заявки от 25000 ₽"

    custom_threshold_builder = await crm.automation_builder_page(
        make_asgi_request("owner2", "/automation/builder")
    )
    custom_threshold_html = custom_threshold_builder.body.decode("utf-8")
    assert "Цена заявки от 25000 ₽" in custom_threshold_html
    assert 'name="condition_value"' in custom_threshold_html
    assert 'value="25000"' in custom_threshold_html

    worker_condition_response = await crm.update_automation_rule_conditions(
        make_form_request(
            "owner2",
            f"/automation/rules/{rule['id']}/conditions",
            {
                "condition_mode": "worker_specific",
                "condition_worker": "helper2",
            },
        ),
        rule["id"],
    )
    assert worker_condition_response.status_code == 302

    conn = connect()
    c = conn.cursor()
    worker_condition = json.loads(c.execute("""
    SELECT conditions_json
    FROM automation_rules
    WHERE id=?
    """, (rule["id"],)).fetchone()["conditions_json"])
    conn.close()

    assert worker_condition["mode"] == "worker_specific"
    assert worker_condition["value"] == "helper2"
    assert worker_condition["label"] == "Исполнитель: helper2"

    outsider_worker_response = await crm.update_automation_rule_conditions(
        make_form_request(
            "owner2",
            f"/automation/rules/{rule['id']}/conditions",
            {
                "condition_mode": "worker_specific",
                "condition_worker": "outsider_worker",
            },
        ),
        rule["id"],
    )
    assert outsider_worker_response.status_code == 302
    assert outsider_worker_response.headers["location"] == "/automation/builder?conditions_error=1"

    conn = connect()
    c = conn.cursor()
    builder_client = c.execute("""
    SELECT id
    FROM clients
    WHERE company_id=2
      AND name='Client 2'
    """).fetchone()
    conn.close()

    client_condition_response = await crm.update_automation_rule_conditions(
        make_form_request(
            "owner2",
            f"/automation/rules/{rule['id']}/conditions",
            {
                "condition_mode": "client_specific",
                "condition_client": str(builder_client["id"]),
            },
        ),
        rule["id"],
    )
    assert client_condition_response.status_code == 302

    conn = connect()
    c = conn.cursor()
    client_condition = json.loads(c.execute("""
    SELECT conditions_json
    FROM automation_rules
    WHERE id=?
    """, (rule["id"],)).fetchone()["conditions_json"])
    conn.close()

    assert client_condition["mode"] == "client_specific"
    assert client_condition["value"] == str(builder_client["id"])
    assert client_condition["label"] == "Клиент: Client 2"

    outsider_client_response = await crm.update_automation_rule_conditions(
        make_form_request(
            "owner2",
            f"/automation/rules/{rule['id']}/conditions",
            {
                "condition_mode": "client_specific",
                "condition_client": "999999",
            },
        ),
        rule["id"],
    )
    assert outsider_client_response.status_code == 302
    assert outsider_client_response.headers["location"] == "/automation/builder?conditions_error=1"

    catalog_condition_response = await crm.update_automation_rule_conditions(
        make_form_request(
            "owner2",
            f"/automation/rules/{rule['id']}/conditions",
            {
                "condition_mode": "catalog_specific",
                "condition_catalog": str(automation_catalog_item_id),
            },
        ),
        rule["id"],
    )
    assert catalog_condition_response.status_code == 302

    conn = connect()
    c = conn.cursor()
    catalog_condition = json.loads(c.execute("""
    SELECT conditions_json
    FROM automation_rules
    WHERE id=?
    """, (rule["id"],)).fetchone()["conditions_json"])
    conn.close()

    assert catalog_condition["mode"] == "catalog_specific"
    assert catalog_condition["value"] == str(automation_catalog_item_id)
    assert catalog_condition["label"] == "Каталог: Automation service"

    outsider_catalog_response = await crm.update_automation_rule_conditions(
        make_form_request(
            "owner2",
            f"/automation/rules/{rule['id']}/conditions",
            {
                "condition_mode": "catalog_specific",
                "condition_catalog": str(outsider_catalog_item_id),
            },
        ),
        rule["id"],
    )
    assert outsider_catalog_response.status_code == 302
    assert outsider_catalog_response.headers["location"] == "/automation/builder?conditions_error=1"

    text_condition_response = await crm.update_automation_rule_conditions(
        make_form_request(
            "owner2",
            f"/automation/rules/{rule['id']}/conditions",
            {
                "condition_mode": "task_text_contains",
                "condition_text": "Smoke",
            },
        ),
        rule["id"],
    )
    assert text_condition_response.status_code == 302

    conn = connect()
    c = conn.cursor()
    text_condition = json.loads(c.execute("""
    SELECT conditions_json
    FROM automation_rules
    WHERE id=?
    """, (rule["id"],)).fetchone()["conditions_json"])
    conn.close()

    assert text_condition["mode"] == "task_text_contains"
    assert text_condition["value"] == "Smoke"
    assert text_condition["label"] == "Текст содержит: Smoke"

    conn = connect()
    c = conn.cursor()
    test_task = c.execute("""
    SELECT id
    FROM tasks
    WHERE company_id=2
    ORDER BY id
    LIMIT 1
    """).fetchone()
    events_before_test = c.execute("""
    SELECT COUNT(*)
    FROM automation_events
    WHERE company_id=2
    """).fetchone()[0]
    conn.close()

    test_condition_response = await crm.test_automation_rule_condition(
        make_form_request(
            "owner2",
            f"/automation/rules/{rule['id']}/test-condition",
            {
                "task_id": str(test_task["id"]),
            },
        ),
        rule["id"],
    )
    assert test_condition_response.status_code == 302
    assert "test_result=match" in test_condition_response.headers["location"]
    assert "test_operator=" in test_condition_response.headers["location"]
    assert "test_details=" in test_condition_response.headers["location"]

    conn = connect()
    c = conn.cursor()
    events_after_test = c.execute("""
    SELECT COUNT(*)
    FROM automation_events
    WHERE company_id=2
    """).fetchone()[0]
    conn.close()

    assert events_after_test == events_before_test

    test_result_response = await crm.automation_builder_page(
        make_asgi_request(
            "owner2",
            "/automation/builder",
            test_condition_response.headers["location"].split("?", 1)[1],
        )
    )
    test_result_html = test_result_response.body.decode("utf-8")
    assert "Подходит" in test_result_html
    assert "Условия выполнены, правило может сработать" in test_result_html
    assert "Логика проверки: И" in test_result_html
    assert "Выполнено" in test_result_html
    assert "Текст содержит: Smoke" in test_result_html
    assert "Готово к запуску" in test_result_html
    assert "Будет выполнено действий: 1" in test_result_html
    assert "Будут выполнены" in test_result_html
    assert "Создать уведомление" in test_result_html
    assert "Получатель: owner2" in test_result_html
    assert "SLA smoke message" in test_result_html

    conn = connect()
    c = conn.cursor()
    diagnostic_rule = dict(rule)
    diagnostic_rule["conditions_json"] = json.dumps({
        "operator": "and",
        "conditions": [
            {
                "mode": "task_text_contains",
                "value": "Smoke",
                "label": "Текст содержит: Smoke",
            },
            {
                "mode": "status_done",
                "label": "Только завершённые заявки",
            },
        ],
    }, ensure_ascii=False)
    diagnostic_result = crm.automation_condition_diagnostics(
        c,
        2,
        diagnostic_rule,
        "task",
        test_task["id"],
    )
    conn.close()

    assert diagnostic_result["matched"] is False
    assert diagnostic_result["operator_label"] == "И"
    assert diagnostic_result["details"][0]["matched"] is True
    assert diagnostic_result["details"][1]["matched"] is False

    invalid_test_response = await crm.test_automation_rule_condition(
        make_form_request(
            "owner2",
            f"/automation/rules/{rule['id']}/test-condition",
            {
                "task_id": "999999",
            },
        ),
        rule["id"],
    )
    assert invalid_test_response.status_code == 302
    assert "test_result=error" in invalid_test_response.headers["location"]

    conn = connect()
    c = conn.cursor()
    events_before_batch_test = c.execute("""
    SELECT COUNT(*)
    FROM automation_events
    WHERE company_id=2
    """).fetchone()[0]
    conn.close()

    batch_test_response = await crm.test_automation_rule_condition_batch(
        make_form_request(
            "owner2",
            f"/automation/rules/{rule['id']}/test-condition-batch",
            {
                "batch_limit": "20",
            },
        ),
        rule["id"],
    )
    assert batch_test_response.status_code == 302
    assert "batch_rule_id=" in batch_test_response.headers["location"]
    assert "batch_total=" in batch_test_response.headers["location"]
    assert "batch_matched=" in batch_test_response.headers["location"]
    assert "batch_match_rate=" in batch_test_response.headers["location"]
    assert "batch_limit=20" in batch_test_response.headers["location"]
    assert "batch_condition_stats=" in batch_test_response.headers["location"]
    assert "batch_operator=and" in batch_test_response.headers["location"]
    assert "batch_rejected=" in batch_test_response.headers["location"]

    conn = connect()
    c = conn.cursor()
    events_after_batch_test = c.execute("""
    SELECT COUNT(*)
    FROM automation_events
    WHERE company_id=2
    """).fetchone()[0]
    conn.close()

    assert events_after_batch_test == events_before_batch_test

    batch_result_response = await crm.automation_builder_page(
        make_asgi_request(
            "owner2",
            "/automation/builder",
            batch_test_response.headers["location"].split("?", 1)[1],
        )
    )
    batch_result_html = batch_result_response.body.decode("utf-8")
    assert "Проверить последние заявки" in batch_result_html
    assert "Последние 20 заявок" in batch_result_html
    assert "Последние 50 заявок" in batch_result_html
    assert "Последние 100 заявок" in batch_result_html
    assert "Подходит" in batch_result_html
    assert "Совпадение:" in batch_result_html
    assert "Правило подходит всем заявкам" in batch_result_html
    assert "Добавьте ограничивающее условие" in batch_result_html
    assert "Результат каждого условия" in batch_result_html
    assert "Текст содержит: Smoke" in batch_result_html
    assert "Главное ограничение правила" in batch_result_html
    assert f'href="/task/{test_task["id"]}"' in batch_result_html

    rejected_preview_response = await crm.automation_builder_page(
        make_asgi_request(
            "owner2",
            "/automation/builder",
            urlencode({
                "batch_rule_id": rule["id"],
                "batch_total": 1,
                "batch_matched": 0,
                "batch_match_rate": 0,
                "batch_limit": 20,
                "batch_rejected": json.dumps([{
                    "id": test_task["id"],
                    "failed_conditions": ["Только завершённые заявки"],
                }], ensure_ascii=False),
            }),
        )
    )
    rejected_preview_html = rejected_preview_response.body.decode("utf-8")
    assert "Отклонённые заявки" in rejected_preview_html
    assert "Не выполнено: Только завершённые заявки" in rejected_preview_html
    assert "Правило слишком узкое" in rejected_preview_html

    assert crm.automation_condition_coverage_assessment(0, 0)["status"] == "no_data"
    assert crm.automation_condition_coverage_assessment(20, 0)["status"] == "too_narrow"
    assert crm.automation_condition_coverage_assessment(20, 2)["status"] == "narrow"
    assert crm.automation_condition_coverage_assessment(20, 10)["status"] == "balanced"
    assert crm.automation_condition_coverage_assessment(20, 18)["status"] == "broad"
    assert crm.automation_condition_coverage_assessment(20, 20)["status"] == "all"

    and_focus = crm.automation_condition_focus_assessment([
        {"label": "Первое", "match_rate": 80},
        {"label": "Второе", "match_rate": 20},
    ], "and")
    assert and_focus["title"] == "Главное ограничение правила"
    assert and_focus["label"] == "Второе"

    or_focus = crm.automation_condition_focus_assessment([
        {"label": "Первое", "match_rate": 80},
        {"label": "Второе", "match_rate": 20},
    ], "or")
    assert or_focus["title"] == "Главная ветка условия ИЛИ"
    assert or_focus["label"] == "Первое"

    ready_dry_run = crm.automation_dry_run_readiness(
        True,
        True,
        [{
            "active": 1,
            "action_key": "notification",
            "payload_json": json.dumps({
                "target_username": "owner2",
                "message": "Проверка",
            }),
        }],
    )
    assert ready_dry_run["status"] == "ready"
    assert len(ready_dry_run["active_actions"]) == 1
    assert ready_dry_run["executable_actions"][0]["dry_run_supported"] is True
    assert "Получатель: owner2" in ready_dry_run["executable_actions"][0]["dry_run_detail"]

    disabled_dry_run = crm.automation_dry_run_readiness(
        False,
        True,
        [{"active": 1, "action_key": "notification", "payload_json": "{}"}],
    )
    assert disabled_dry_run["status"] == "rule_disabled"

    failed_dry_run = crm.automation_dry_run_readiness(
        True,
        False,
        [{"active": 1, "action_key": "notification", "payload_json": "{}"}],
    )
    assert failed_dry_run["status"] == "condition_failed"
    assert len(failed_dry_run["active_actions"]) == 1

    empty_dry_run = crm.automation_dry_run_readiness(
        True,
        True,
        [{"active": 0, "action_key": "notification", "payload_json": "{}"}],
    )
    assert empty_dry_run["status"] == "no_actions"
    assert len(empty_dry_run["inactive_actions"]) == 1

    unsupported_dry_run = crm.automation_dry_run_readiness(
        True,
        True,
        [{
            "active": 1,
            "action_key": "email",
            "payload_json": json.dumps({
                "target_username": "owner2",
                "subject": "Тест",
            }),
        }],
    )
    assert unsupported_dry_run["status"] == "unsupported_actions"
    assert len(unsupported_dry_run["unsupported_actions"]) == 1
    assert unsupported_dry_run["unsupported_actions"][0]["dry_run_supported"] is False

    create_task_preview = crm.automation_dry_run_readiness(
        True,
        True,
        [{
            "active": 1,
            "action_key": "create_task",
            "payload_json": json.dumps({
                "target_username": "helper2",
                "message": "Автоматическая проверка клиента",
                "task_delay_days": 3,
                "task_priority": "Срочно",
                "task_deadline_hours": 24,
            }),
        }],
    )
    assert create_task_preview["status"] == "ready"
    assert create_task_preview["executable_actions"][0]["dry_run_supported"] is True
    assert "Новая задача для: helper2" in create_task_preview["executable_actions"][0]["dry_run_detail"]
    assert "через 3 дн." in create_task_preview["executable_actions"][0]["dry_run_detail"]
    assert "приоритет: Срочно" in create_task_preview["executable_actions"][0]["dry_run_detail"]
    assert "SLA: 24 ч." in create_task_preview["executable_actions"][0]["dry_run_detail"]

    auto_worker_preview = crm.automation_dry_run_readiness(
        True,
        True,
        [{
            "active": 1,
            "action_key": "create_task",
            "payload_json": json.dumps({
                "target_username": "__least_loaded__",
                "task_max_daily_load": 3,
                "task_capacity_fallback_days": 7,
                "task_business_days_only": True,
            }),
        }],
    )
    assert "авто: наименее загруженный" in (
        auto_worker_preview["executable_actions"][0]["dry_run_detail"]
    )
    assert "лимит: 3 в день" in (
        auto_worker_preview["executable_actions"][0]["dry_run_detail"]
    )
    assert "поиск окна: 7 дн." in (
        auto_worker_preview["executable_actions"][0]["dry_run_detail"]
    )
    assert "только рабочие дни" in (
        auto_worker_preview["executable_actions"][0]["dry_run_detail"]
    )
    assert "справедливое распределение" in (
        auto_worker_preview["executable_actions"][0]["dry_run_detail"]
    )

    conn = connect()
    c = conn.cursor()
    weekend_at = datetime(2026, 6, 13, 9, 0)
    any_day_worker, any_day_at = crm.automation_find_available_worker_slot(
        c,
        2,
        weekend_at,
        fallback_days=2,
        business_days_only=False,
    )
    workday_worker, workday_at = crm.automation_find_available_worker_slot(
        c,
        2,
        weekend_at,
        fallback_days=2,
        business_days_only=True,
    )
    no_workday_worker, _ = crm.automation_find_available_worker_slot(
        c,
        2,
        weekend_at,
        fallback_days=1,
        business_days_only=True,
    )

    assert any_day_worker is not None
    assert any_day_at.strftime("%Y-%m-%d") == "2026-06-13"
    assert workday_worker is not None
    assert workday_at.strftime("%Y-%m-%d") == "2026-06-15"
    assert no_workday_worker is None

    c.execute("""
    INSERT INTO automation_actions (
        company_id, rule_id, action_key, payload_json,
        sort_order, active, created_at
    )
    VALUES (?, ?, 'create_task', ?, 99, 1, ?)
    """, (
        2,
        rule["id"],
        json.dumps({
            "target_username": "helper2",
            "message": "Автоматическая проверка клиента",
            "task_delay_days": 3,
            "task_priority": "Срочно",
            "task_deadline_hours": 24,
        }, ensure_ascii=False),
        datetime.now().strftime("%Y-%m-%d %H:%M"),
    ))
    create_task_action = c.execute("""
    SELECT *
    FROM automation_actions
    WHERE id=?
    """, (c.lastrowid,)).fetchone()
    source_task = c.execute("""
    SELECT *
    FROM tasks
    WHERE company_id=2
    ORDER BY id
    LIMIT 1
    """).fetchone()

    sent_create_task_telegram = []
    original_send_message_to_chat = crm.send_message_to_chat
    crm.send_message_to_chat = (
        lambda chat_id, text:
        sent_create_task_telegram.append((chat_id, text)) or True
    )

    try:
        created_task_id = crm.execute_automation_create_task_action(
            c,
            2,
            rule,
            create_task_action,
            json.loads(create_task_action["payload_json"]),
            "task",
            source_task["id"],
            datetime.now().strftime("%Y-%m-%d %H:%M"),
        )
        duplicate_task_id = crm.execute_automation_create_task_action(
            c,
            2,
            rule,
            create_task_action,
            json.loads(create_task_action["payload_json"]),
            "task",
            source_task["id"],
            datetime.now().strftime("%Y-%m-%d %H:%M"),
        )
        client_created_task_id = crm.execute_automation_create_task_action(
            c,
            2,
            rule,
            create_task_action,
            json.loads(create_task_action["payload_json"]),
            "client",
            source_task["client_id"],
            datetime.now().strftime("%Y-%m-%d %H:%M"),
        )
        duplicate_client_task_id = crm.execute_automation_create_task_action(
            c,
            2,
            rule,
            create_task_action,
            json.loads(create_task_action["payload_json"]),
            "client",
            source_task["client_id"],
            datetime.now().strftime("%Y-%m-%d %H:%M"),
        )
    finally:
        crm.send_message_to_chat = original_send_message_to_chat

    created_task = c.execute("""
    SELECT *
    FROM tasks
    WHERE id=?
      AND company_id=2
    """, (created_task_id,)).fetchone()
    client_created_task = c.execute("""
    SELECT *
    FROM tasks
    WHERE id=?
      AND company_id=2
    """, (client_created_task_id,)).fetchone()
    create_task_run_count = c.execute("""
    SELECT COUNT(*)
    FROM automation_action_runs
    WHERE company_id=2
      AND action_id=?
      AND entity_type='task'
      AND entity_id=?
    """, (create_task_action["id"], source_task["id"])).fetchone()[0]
    create_task_activity = c.execute("""
    SELECT *
    FROM task_activity
    WHERE task_id=?
      AND action='Создана автоматизацией'
    """, (created_task_id,)).fetchall()
    create_task_notifications = c.execute("""
    SELECT *
    FROM notifications
    WHERE company_id=2
      AND username='helper2'
      AND link=?
    """, (f"/task/{created_task_id}",)).fetchall()

    assert created_task_id == duplicate_task_id
    assert client_created_task_id == duplicate_client_task_id
    assert created_task is not None
    assert client_created_task is not None
    assert created_task["client_id"] == source_task["client_id"]
    assert created_task["phone"] == source_task["phone"]
    assert created_task["address"] == source_task["address"]
    assert created_task["worker"] == "helper2"
    assert created_task["status"] == "Новая"
    assert created_task["description"] == "Автоматическая проверка клиента"
    assert created_task["task_date"] == (
        datetime.now() + timedelta(days=3)
    ).strftime("%Y-%m-%d")
    assert created_task["priority"] == "Срочно"
    assert created_task["deadline_at"] == (
        datetime.now() + timedelta(days=3, hours=24)
    ).strftime("%Y-%m-%dT%H:%M")
    assert client_created_task["client_id"] == source_task["client_id"]
    assert client_created_task["client"] == source_task["client"]
    assert client_created_task["phone"] == source_task["phone"]
    assert client_created_task["address"] == source_task["address"]
    assert client_created_task["worker"] == "helper2"
    assert create_task_run_count == 1
    assert len(create_task_activity) == 1
    assert f"Исходная заявка: #{source_task['id']}" in create_task_activity[0]["details"]
    assert len(create_task_notifications) == 1
    assert create_task_notifications[0]["title"] == (
        f"Новая автоматическая заявка #{created_task_id}"
    )
    expected_telegram_message = (
            f"Вам назначена автоматическая заявка #{created_task_id}\n"
            f"Клиент: {source_task['client']}\n"
            f"Дата: {created_task['task_date']}\n"
            f"SLA: {created_task['deadline_at']}\n"
            "Описание: Автоматическая проверка клиента"
    )
    expected_client_telegram_message = (
        f"Вам назначена автоматическая заявка #{client_created_task_id}\n"
        f"Клиент: {source_task['client']}\n"
        f"Дата: {client_created_task['task_date']}\n"
        f"SLA: {client_created_task['deadline_at']}\n"
        "Описание: Автоматическая проверка клиента"
    )
    assert sent_create_task_telegram == [
        ("chat-helper2", expected_telegram_message),
        ("chat-helper2", expected_client_telegram_message),
    ]

    c.execute("""
    INSERT INTO automation_actions (
        company_id, rule_id, action_key, payload_json,
        sort_order, active, created_at
    )
    VALUES (?, ?, 'create_task', ?, 100, 1, ?)
    """, (
        2,
        rule["id"],
        json.dumps({
            "target_username": "__least_loaded__",
            "message": "Автоматическое распределение",
            "task_delay_days": 3,
            "task_priority": "Обычный",
            "task_deadline_hours": 8,
            "task_max_daily_load": 1,
        }, ensure_ascii=False),
        datetime.now().strftime("%Y-%m-%d %H:%M"),
    ))
    auto_worker_action = c.execute("""
    SELECT *
    FROM automation_actions
    WHERE id=?
    """, (c.lastrowid,)).fetchone()
    auto_worker_task_id = crm.execute_automation_create_task_action(
        c,
        2,
        rule,
        auto_worker_action,
        json.loads(auto_worker_action["payload_json"]),
        "task",
        source_task["id"],
        datetime.now().strftime("%Y-%m-%d %H:%M"),
    )
    auto_worker_task = c.execute("""
    SELECT *
    FROM tasks
    WHERE id=?
      AND company_id=2
    """, (auto_worker_task_id,)).fetchone()

    assert auto_worker_task is not None
    assert auto_worker_task["worker"] == "free2"
    assert auto_worker_task["workers"] == "free2"
    assert crm.automation_action_target_is_valid(
        c,
        2,
        "create_task",
        "__least_loaded__",
    ) is True
    next_fair_worker = crm.automation_least_loaded_worker(
        c,
        2,
        (datetime.now() + timedelta(days=10)).strftime("%Y-%m-%d"),
    )
    assert next_fair_worker["username"] == "worker2"

    c.execute("""
    INSERT INTO tasks (
        company_id, client_id, client, description,
        task_date, worker, workers, priority,
        price, status, archived
    )
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
    """, (
        2,
        source_task["client_id"],
        source_task["client"],
        "Проверка лимита автоназначения",
        auto_worker_task["task_date"],
        "worker2",
        "worker2",
        "Обычный",
        "0",
        "Новая",
    ))
    max_load_task_id = c.lastrowid
    assert crm.automation_least_loaded_worker(
        c,
        2,
        auto_worker_task["task_date"],
        1,
    ) is None

    c.execute("""
    INSERT INTO automation_actions (
        company_id, rule_id, action_key, payload_json,
        sort_order, active, created_at
    )
    VALUES (?, ?, 'create_task', ?, 101, 1, ?)
    """, (
        2,
        rule["id"],
        json.dumps({
            "target_username": "__least_loaded__",
            "message": "Поиск ближайшего окна",
            "task_delay_days": 3,
            "task_priority": "Срочно",
            "task_deadline_hours": 8,
            "task_max_daily_load": 1,
            "task_capacity_fallback_days": 3,
        }, ensure_ascii=False),
        datetime.now().strftime("%Y-%m-%d %H:%M"),
    ))
    fallback_action = c.execute("""
    SELECT *
    FROM automation_actions
    WHERE id=?
    """, (c.lastrowid,)).fetchone()
    fallback_success_details = []
    fallback_task_id = crm.execute_automation_create_task_action(
        c,
        2,
        rule,
        fallback_action,
        json.loads(fallback_action["payload_json"]),
        "task",
        source_task["id"],
        datetime.now().strftime("%Y-%m-%d %H:%M"),
        success_details=fallback_success_details,
    )
    fallback_task = c.execute("""
    SELECT *
    FROM tasks
    WHERE id=?
      AND company_id=2
    """, (fallback_task_id,)).fetchone()
    expected_fallback_at = datetime.now() + timedelta(days=4)

    assert fallback_task is not None
    assert fallback_task["worker"] == "worker2"
    assert fallback_task["task_date"] == expected_fallback_at.strftime(
        "%Y-%m-%d"
    )
    assert fallback_task["deadline_at"] == (
        expected_fallback_at + timedelta(hours=8)
    ).strftime("%Y-%m-%dT%H:%M")
    fallback_activity = c.execute("""
    SELECT *
    FROM task_activity
    WHERE task_id=?
      AND action='Создана автоматизацией'
    """, (fallback_task_id,)).fetchone()
    fallback_notification = c.execute("""
    SELECT *
    FROM notifications
    WHERE company_id=2
      AND username='owner2'
      AND title=?
    """, (f"A3 перенёс заявку #{fallback_task_id}",)).fetchone()

    assert len(fallback_success_details) == 1
    assert f"с {auto_worker_task['task_date']}" in fallback_success_details[0]
    assert f"на {fallback_task['task_date']}" in fallback_success_details[0]
    assert fallback_activity is not None
    assert "Автоперенос:" in fallback_activity["details"]
    assert fallback_notification is not None
    assert fallback_notification["link"] == f"/task/{fallback_task_id}"

    conn.commit()
    c.execute("""
    INSERT INTO automation_rules (
        company_id, name, trigger_key, conditions_json,
        active, created_by, created_at, updated_at
    )
    VALUES (?, ?, ?, '{}', 1, ?, ?, ?)
    """, (
        2,
        "Fallback event smoke",
        "fallback_event_smoke",
        "owner2",
        datetime.now().strftime("%Y-%m-%d %H:%M"),
        datetime.now().strftime("%Y-%m-%d %H:%M"),
    ))
    fallback_rule_id = c.lastrowid
    c.execute("""
    INSERT INTO automation_actions (
        company_id, rule_id, action_key, payload_json,
        sort_order, active, created_at
    )
    VALUES (?, ?, 'create_task', ?, 1, 1, ?)
    """, (
        2,
        fallback_rule_id,
        json.dumps({
            "target_username": "__least_loaded__",
            "message": "Runtime поиск окна",
            "task_delay_days": 3,
            "task_max_daily_load": 1,
            "task_capacity_fallback_days": 3,
        }, ensure_ascii=False),
        datetime.now().strftime("%Y-%m-%d %H:%M"),
    ))
    fallback_runtime_action_id = c.lastrowid
    conn.commit()
    conn.close()

    assert crm.run_automation_event(
        2,
        "fallback_event_smoke",
        "task",
        source_task["id"],
        "Проверка автоматического переноса",
        f"/task/{source_task['id']}",
    ) == 1

    conn = connect()
    c = conn.cursor()
    fallback_runtime_event = c.execute("""
    SELECT *
    FROM automation_events
    WHERE company_id=2
      AND rule_id=?
    ORDER BY id DESC
    LIMIT 1
    """, (fallback_rule_id,)).fetchone()
    fallback_runtime_run = c.execute("""
    SELECT *
    FROM automation_action_runs
    WHERE company_id=2
      AND action_id=?
    """, (fallback_runtime_action_id,)).fetchone()
    fallback_runtime_task_id = fallback_runtime_run["created_entity_id"]
    fallback_runtime_alert = c.execute("""
    SELECT *
    FROM notifications
    WHERE company_id=2
      AND username='owner2'
      AND title=?
    """, (
        f"A3 перенёс заявку #{fallback_runtime_task_id}",
    )).fetchone()

    assert fallback_runtime_event["status"] == "done"
    assert "Результат: Заявка #" in fallback_runtime_event["message"]
    assert "перенесена" in fallback_runtime_event["message"]
    assert fallback_runtime_alert is not None

    c.execute("""
    INSERT INTO automation_rules (
        company_id, name, trigger_key, conditions_json,
        active, created_by, created_at, updated_at
    )
    VALUES (?, ?, ?, '{}', 1, ?, ?, ?)
    """, (
        2,
        "Capacity alert smoke",
        "capacity_alert_smoke",
        "owner2",
        datetime.now().strftime("%Y-%m-%d %H:%M"),
        datetime.now().strftime("%Y-%m-%d %H:%M"),
    ))
    capacity_rule_id = c.lastrowid
    c.execute("""
    INSERT INTO automation_actions (
        company_id, rule_id, action_key, payload_json,
        sort_order, active, created_at
    )
    VALUES (?, ?, 'create_task', ?, 1, 1, ?)
    """, (
        2,
        capacity_rule_id,
        json.dumps({
            "target_username": "__least_loaded__",
            "message": "Заявка при полной загрузке",
            "task_delay_days": 3,
            "task_max_daily_load": 1,
        }, ensure_ascii=False),
        datetime.now().strftime("%Y-%m-%d %H:%M"),
    ))
    conn.commit()
    conn.close()

    assert crm.run_automation_event(
        2,
        "capacity_alert_smoke",
        "task",
        source_task["id"],
        "Проверка полной загрузки",
        f"/task/{source_task['id']}",
    ) == 1
    assert crm.run_automation_event(
        2,
        "capacity_alert_smoke",
        "task",
        source_task["id"],
        "Повтор проверки полной загрузки",
        f"/task/{source_task['id']}",
    ) == 1

    conn = connect()
    c = conn.cursor()
    capacity_events = c.execute("""
    SELECT *
    FROM automation_events
    WHERE company_id=2
      AND rule_id=?
    ORDER BY id
    """, (capacity_rule_id,)).fetchall()
    capacity_alerts = c.execute("""
    SELECT *
    FROM notifications
    WHERE company_id=2
      AND username='owner2'
      AND title='A3: требуется распределение — Capacity alert smoke'
      AND is_read=0
    """).fetchall()

    assert len(capacity_events) == 2
    assert all(event["status"] == "skipped" for event in capacity_events)
    assert "Нет исполнителя с доступной загрузкой" in capacity_events[0]["message"]
    assert "Лимит на исполнителя: 1 в день" in capacity_events[0]["message"]
    assert len(capacity_alerts) == 1
    assert "Нет исполнителя с доступной загрузкой" in capacity_alerts[0]["message"]

    capacity_event_response = await crm.automation_event_detail(
        make_asgi_request(
            "owner2",
            f"/automation/events/{capacity_events[0]['id']}",
        ),
        capacity_events[0]["id"],
    )
    assert capacity_event_response.status_code == 200
    capacity_event_html = capacity_event_response.body.decode("utf-8")
    assert "Нет исполнителя с доступной загрузкой" in capacity_event_html
    assert "Лимит на исполнителя: 1 в день" in capacity_event_html
    assert "Повторить" in capacity_event_html

    action_history_response = await crm.automation_rule_detail(
        make_asgi_request(
            "owner2",
            f"/automation/rules/{rule['id']}",
        ),
        rule["id"],
    )
    action_history_html = action_history_response.body.decode("utf-8")
    assert "История выполненных действий" in action_history_html
    assert f'href="/task/{source_task["id"]}"' in action_history_html
    assert f'href="/task/{created_task_id}"' in action_history_html
    assert f"Создана заявка #{created_task_id}" in action_history_html

    c.execute("""
    DELETE FROM notifications
    WHERE company_id=2
      AND link IN (?, ?, ?, ?, ?)
    """, (
        f"/task/{created_task_id}",
        f"/task/{client_created_task_id}",
        f"/task/{auto_worker_task_id}",
        f"/task/{fallback_task_id}",
        f"/task/{fallback_runtime_task_id}",
    ))
    c.execute("""
    DELETE FROM task_activity
    WHERE task_id IN (?, ?, ?, ?, ?)
    """, (
        created_task_id,
        client_created_task_id,
        auto_worker_task_id,
        fallback_task_id,
        fallback_runtime_task_id,
    ))
    c.execute("""
    DELETE FROM automation_action_runs
    WHERE company_id=2
      AND action_id IN (?, ?, ?, ?)
    """, (
        create_task_action["id"],
        auto_worker_action["id"],
        fallback_action["id"],
        fallback_runtime_action_id,
    ))
    c.execute("""
    DELETE FROM tasks
    WHERE company_id=2
      AND id IN (?, ?, ?, ?, ?, ?)
    """, (
        created_task_id,
        client_created_task_id,
        auto_worker_task_id,
        max_load_task_id,
        fallback_task_id,
        fallback_runtime_task_id,
    ))
    c.execute("""
    DELETE FROM automation_actions
    WHERE company_id=2
      AND id=?
    """, (create_task_action["id"],))
    c.execute("""
    DELETE FROM automation_actions
    WHERE company_id=2
      AND id=?
    """, (auto_worker_action["id"],))
    c.execute("""
    DELETE FROM automation_actions
    WHERE company_id=2
      AND id=?
    """, (fallback_action["id"],))
    c.execute("""
    DELETE FROM automation_events
    WHERE company_id=2
      AND rule_id=?
    """, (fallback_rule_id,))
    c.execute("""
    DELETE FROM automation_actions
    WHERE company_id=2
      AND rule_id=?
    """, (fallback_rule_id,))
    c.execute("""
    DELETE FROM automation_rules
    WHERE company_id=2
      AND id=?
    """, (fallback_rule_id,))
    c.execute("""
    DELETE FROM notifications
    WHERE company_id=2
      AND title='A3: требуется распределение — Capacity alert smoke'
    """)
    c.execute("""
    DELETE FROM automation_events
    WHERE company_id=2
      AND rule_id=?
    """, (capacity_rule_id,))
    c.execute("""
    DELETE FROM automation_actions
    WHERE company_id=2
      AND rule_id=?
    """, (capacity_rule_id,))
    c.execute("""
    DELETE FROM automation_rules
    WHERE company_id=2
      AND id=?
    """, (capacity_rule_id,))
    conn.commit()
    conn.close()

    empty_text_condition_response = await crm.update_automation_rule_conditions(
        make_form_request(
            "owner2",
            f"/automation/rules/{rule['id']}/conditions",
            {
                "condition_mode": "task_text_contains",
                "condition_text": "",
            },
        ),
        rule["id"],
    )
    assert empty_text_condition_response.status_code == 302
    assert empty_text_condition_response.headers["location"] == "/automation/builder?conditions_error=1"

    invalid_conditions_response = await crm.update_automation_rule_conditions(
        make_form_request(
            "owner2",
            f"/automation/rules/{rule['id']}/conditions",
            {
                "condition_mode": "bad_mode",
            },
        ),
        rule["id"],
    )
    assert invalid_conditions_response.status_code == 302
    assert invalid_conditions_response.headers["location"] == "/automation/builder?conditions_error=1"

    reset_conditions_response = await crm.update_automation_rule_conditions(
        make_form_request(
            "owner2",
            f"/automation/rules/{rule['id']}/conditions",
            {
                "condition_mode": "none",
            },
        ),
        rule["id"],
    )
    assert reset_conditions_response.status_code == 302

    assert "Запустить правило" in rule_detail_html
    assert "Визуальная цепочка" in rule_detail_html
    assert "A3 Конструктор цепочки" in rule_detail_html
    assert f"/api/a3/workflow/rules/{rule['id']}/graph" in rule_detail_html
    assert "Диагностика правила" in rule_detail_html
    assert "Действия" in rule_detail_html
    assert "Последние события правила" in rule_detail_html
    assert "Запустить сейчас" in rule_detail_html
    assert "Повторить пропущенные" in rule_detail_html
    assert f"/automation/rules/{rule['id']}/events/export" in rule_detail_html

    workflow_graph = crm.api_a3_workflow_rule_graph(
        make_request("owner2"),
        rule["id"],
    )
    assert workflow_graph["ok"] is True
    assert workflow_graph["rule"]["id"] == rule["id"]
    assert workflow_graph["rule"]["trigger_key"] == "sla_overdue"
    assert "conditions" in workflow_graph["rule"]
    assert workflow_graph["rule"]["conditions"]["label"] in {
        "Без условий",
        "Только высокий приоритет",
        "Только срочные заявки",
        "Только новые заявки",
    }
    assert workflow_graph["stats"]["actions_total"] >= 1
    assert "debug" in workflow_graph
    assert "quick_actions" in workflow_graph["debug"]
    assert "ai_recommendations" in workflow_graph["debug"]
    assert "diagnosis" in workflow_graph["debug"]
    assert "next_step" in workflow_graph["debug"]["diagnosis"]
    assert "severity" in workflow_graph["debug"]
    assert "priority" in workflow_graph["debug"]
    assert "risk" in workflow_graph["debug"]
    assert workflow_graph["debug"]["risk"]["key"] in {"low", "medium", "high", "critical"}
    assert "safe_fixes" in workflow_graph["debug"]
    assert "dangerous_fixes" in workflow_graph["debug"]
    assert any(node["type"] == "trigger" for node in workflow_graph["nodes"])
    assert any(node["type"] == "rule" for node in workflow_graph["nodes"])
    assert any(node["type"] == "action" for node in workflow_graph["nodes"])
    assert any(edge["label"] == "запускает" for edge in workflow_graph["edges"])

    workflow_debug = crm.api_a3_workflow_rule_debug(
        make_request("owner2"),
        rule["id"],
    )
    assert workflow_debug["ok"] is True
    assert workflow_debug["rule"]["id"] == rule["id"]
    assert "quick_actions" in workflow_debug["debug"]
    assert "ai_recommendations" in workflow_debug["debug"]
    assert "diagnosis" in workflow_debug["debug"]
    assert "risk" in workflow_debug["debug"]
    assert "safe_fixes" in workflow_debug["debug"]
    assert "dangerous_fixes" in workflow_debug["debug"]
    assert "stats" in workflow_debug

    workflow_timeline = crm.api_a3_workflow_timeline(
        make_request("owner2"),
        rule["id"],
    )
    assert workflow_timeline["ok"] is True
    assert "sessions" in workflow_timeline["timeline"]
    assert "steps" in workflow_timeline["timeline"]
    if workflow_timeline["timeline"]["sessions"]:
        session = workflow_timeline["timeline"]["sessions"][0]
        assert "duration_seconds" in session
        assert "duration_label" in session
        assert session["execution_state"] in {"active", "finished", "warning", "problem"}

    workflows_graph = crm.api_a3_workflows_graph(make_request("owner2"))
    assert workflows_graph["ok"] is True
    assert workflows_graph["count"] >= 1
    assert any(
        item["rule"]["id"] == rule["id"]
        for item in workflows_graph["items"]
    )

    rule_events_export_response = await crm.automation_rule_events_export(
        make_request("owner2"),
        rule["id"],
    )
    assert rule_events_export_response.status_code == 200
    rule_events_export_csv = rule_events_export_response.body.decode("utf-8")
    assert "id,rule_name,trigger_key,entity_type,entity_id,status,message,created_at,processed_at" in rule_events_export_csv

    assert "/automation/actions/" in rule_detail_html
    assert "Удалить" in rule_detail_html
    assert "Добавить действие" in rule_detail_html
    assert f"/automation/rules/{rule['id']}/actions/create" in rule_detail_html
    assert "Исполнитель новой задачи" in rule_detail_html
    assert 'data-role="worker"' in rule_detail_html
    assert "Авто: наименее загруженный" in rule_detail_html
    assert "Данные берутся из исходной заявки или нового клиента" in rule_detail_html
    assert "Дата выполнения" in rule_detail_html
    assert "Через 7 дней" in rule_detail_html
    assert "Приоритет" in rule_detail_html
    assert "Срок SLA" in rule_detail_html
    assert "Лимит автоназначения" in rule_detail_html
    assert "Поиск свободного дня" in rule_detail_html
    assert "Календарь поиска" in rule_detail_html
    assert "Только рабочие дни" in rule_detail_html

    builder_response = await crm.create_rule_action(
        make_form_request(
            "owner2",
            f"/automation/rules/{rule['id']}/actions/create",
            {
                "action_key": "notification",
                "target_username": "owner2",
                "message": "Builder action message",
            },
        ),
        rule["id"],
    )
    assert builder_response.status_code == 302
    assert builder_response.headers["location"] == f"/automation/rules/{rule['id']}?action_created=1"

    conn = connect()
    c = conn.cursor()

    builder_action = c.execute("""
    SELECT *
    FROM automation_actions
    WHERE company_id=2
      AND rule_id=?
      AND payload_json LIKE '%Builder action message%'
    ORDER BY id DESC
    """, (rule["id"],)).fetchone()

    conn.close()

    assert builder_action is not None

    ai_digest_builder_response = await crm.create_rule_action(
        make_form_request(
            "owner2",
            f"/automation/rules/{rule['id']}/actions/create",
            {
                "action_key": "ai_digest",
                "target_username": "",
                "message": "",
            },
        ),
        rule["id"],
    )
    assert ai_digest_builder_response.status_code == 302
    assert ai_digest_builder_response.headers["location"] == f"/automation/rules/{rule['id']}?action_created=1"

    conn = connect()
    c = conn.cursor()

    ai_digest_builder_action = c.execute("""
    SELECT *
    FROM automation_actions
    WHERE company_id=2
      AND rule_id=?
      AND action_key='ai_digest'
    ORDER BY id DESC
    """, (rule["id"],)).fetchone()

    conn.close()

    assert ai_digest_builder_action is not None
    assert "owner2" in ai_digest_builder_action["payload_json"]
    assert "AI-сводка по бизнесу" in ai_digest_builder_action["payload_json"]

    invalid_create_task_action_response = await crm.create_rule_action(
        make_form_request(
            "owner2",
            f"/automation/rules/{rule['id']}/actions/create",
            {
                "action_key": "create_task",
                "target_username": "manager2",
                "message": "Нельзя назначить менеджеру",
            },
        ),
        rule["id"],
    )
    assert invalid_create_task_action_response.status_code == 302
    assert invalid_create_task_action_response.headers["location"] == (
        f"/automation/rules/{rule['id']}?action_target_error=1"
    )

    valid_create_task_action_response = await crm.create_rule_action(
        make_form_request(
            "owner2",
            f"/automation/rules/{rule['id']}/actions/create",
            {
                "action_key": "create_task",
                "target_username": "helper2",
                "message": "Новая задача из правила",
                "task_delay_days": "1",
                "task_priority": "Срочно",
                "task_deadline_hours": "8",
                "task_max_daily_load": "3",
                "task_capacity_fallback_days": "7",
                "task_business_days_only": "1",
            },
        ),
        rule["id"],
    )
    assert valid_create_task_action_response.status_code == 302
    assert valid_create_task_action_response.headers["location"] == (
        f"/automation/rules/{rule['id']}?action_created=1"
    )

    conn = connect()
    c = conn.cursor()
    valid_create_task_action = c.execute("""
    SELECT *
    FROM automation_actions
    WHERE company_id=2
      AND rule_id=?
      AND action_key='create_task'
    ORDER BY id DESC
    """, (rule["id"],)).fetchone()
    conn.close()

    assert valid_create_task_action is not None
    assert "helper2" in valid_create_task_action["payload_json"]
    assert "Новая задача из правила" in valid_create_task_action["payload_json"]
    assert '"task_delay_days": 1' in valid_create_task_action["payload_json"]
    assert '"task_priority": "Срочно"' in valid_create_task_action["payload_json"]
    assert '"task_deadline_hours": 8' in valid_create_task_action["payload_json"]
    assert '"task_max_daily_load": 3' in valid_create_task_action["payload_json"]
    assert '"task_capacity_fallback_days": 7' in (
        valid_create_task_action["payload_json"]
    )
    assert '"task_business_days_only": true' in (
        valid_create_task_action["payload_json"]
    )

    conn = connect()
    c = conn.cursor()

    action_for_management = c.execute("""
    SELECT *
    FROM automation_actions
    WHERE company_id=2
      AND rule_id=?
    ORDER BY id DESC
    """, (rule["id"],)).fetchone()

    conn.close()

    assert action_for_management is not None

    toggle_action_response = await crm.toggle_automation_action(
        make_request("owner2"),
        action_for_management["id"],
    )
    assert toggle_action_response.status_code == 302
    assert toggle_action_response.headers["location"] == f"/automation/rules/{rule['id']}?action_updated=1"

    conn = connect()
    c = conn.cursor()

    toggled_action = c.execute("""
    SELECT *
    FROM automation_actions
    WHERE id=?
    """, (action_for_management["id"],)).fetchone()

    conn.close()

    assert toggled_action is not None
    assert toggled_action["active"] == 0

    toggle_action_back_response = await crm.toggle_automation_action(
        make_request("owner2"),
        action_for_management["id"],
    )
    assert toggle_action_back_response.status_code == 302

    conn = connect()
    c = conn.cursor()

    c.execute("""
    INSERT INTO automation_actions (
        company_id,
        rule_id,
        action_key,
        payload_json,
        active,
        created_at
    )
    VALUES (?, ?, ?, ?, ?, ?)
    """, (
        2,
        rule["id"],
        "notification",
        "{}",
        1,
        "2026-01-01 10:00"
    ))

    delete_action_id = c.lastrowid

    conn.commit()
    conn.close()

    delete_action_response = await crm.delete_automation_action(
        make_request("owner2"),
        delete_action_id,
    )

    assert delete_action_response.status_code == 302
    assert delete_action_response.headers["location"] == f"/automation/rules/{rule['id']}?action_deleted=1"

    conn = connect()
    c = conn.cursor()

    deleted_action = c.execute("""
    SELECT *
    FROM automation_actions
    WHERE id=?
    """, (delete_action_id,)).fetchone()

    conn.close()

    assert deleted_action is None

    retry_rule_response = await crm.retry_rule_skipped_events(
        make_request("owner2"),
        rule["id"],
    )
    assert retry_rule_response.status_code == 302
    assert retry_rule_response.headers["location"].startswith(
        f"/automation/rules/{rule['id']}?retry_skipped=1&retried="
    )

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

    rule_trigger_response = await crm.automation_page(
        make_asgi_request("owner2", "/automation"),
        rule_trigger_filter="sla_overdue",
    )
    assert rule_trigger_response.status_code == 200
    rule_trigger_html = rule_trigger_response.body.decode("utf-8")
    assert 'name="rule_trigger_filter"' in rule_trigger_html
    assert 'option value="sla_overdue" selected' in rule_trigger_html
    assert "SLA smoke rule updated" in rule_trigger_html
    assert 'href="/automation/rules/export?rule_trigger_filter=sla_overdue"' in rule_trigger_html

    rule_trigger_export_response = await crm.automation_rules_export(
        make_request("owner2"),
        rule_trigger_filter="sla_overdue",
    )
    assert rule_trigger_export_response.status_code == 200
    rule_trigger_export_csv = rule_trigger_export_response.body.decode("utf-8")
    assert "SLA smoke rule updated" in rule_trigger_export_csv
    assert "sla_overdue" in rule_trigger_export_csv

    rule_search_response = await crm.automation_page(
        make_asgi_request("owner2", "/automation"),
        rule_search="Updated",
    )
    assert rule_search_response.status_code == 200
    rule_search_html = rule_search_response.body.decode("utf-8")
    assert 'name="rule_search" value="Updated"' in rule_search_html
    assert "SLA smoke rule updated" in rule_search_html
    assert "Updated SLA smoke message" in rule_search_html
    assert 'href="/automation/rules/export?rule_search=Updated"' in rule_search_html

    rule_search_export_response = await crm.automation_rules_export(
        make_request("owner2"),
        rule_search="Updated",
    )
    assert rule_search_export_response.status_code == 200
    rule_search_export_csv = rule_search_export_response.body.decode("utf-8")
    assert "SLA smoke rule updated" in rule_search_export_csv
    assert "sla_overdue" in rule_search_export_csv

    assert f"/automation/rules/{rule['id']}/run" in updated_page_html
    assert "Запустить сейчас" in updated_page_html

    run_response = await crm.run_automation_rule_now(
        make_request("owner2"),
        rule["id"],
    )
    assert run_response.status_code == 302
    assert run_response.headers["location"] == "/automation?run=1"

    conn = connect()
    c = conn.cursor()

    manual_event = c.execute("""
    SELECT *
    FROM automation_events
    WHERE company_id=2
      AND rule_id=?
      AND message=?
    ORDER BY id DESC
    """, (
        rule["id"],
        "Ручной запуск правила: SLA smoke rule updated"
    )).fetchone()

    conn.close()

    assert manual_event is not None
    assert manual_event["status"] == "done"

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
    assert 'href="/automation/rules/export?rule_filter=disabled"' in disabled_html

    disabled_export_response = await crm.automation_rules_export(
        make_request("owner2"),
        rule_filter="disabled",
    )
    assert disabled_export_response.status_code == 200
    disabled_export_csv = disabled_export_response.body.decode("utf-8")
    assert "SLA smoke rule updated" in disabled_export_csv
    assert "sla_overdue" in disabled_export_csv

    action_filter_response = await crm.automation_page(
        make_asgi_request("owner2", "/automation"),
        rule_filter="disabled",
        rule_action_filter="notification",
    )
    assert action_filter_response.status_code == 200
    action_filter_html = action_filter_response.body.decode("utf-8")
    assert 'option value="notification" selected' in action_filter_html
    assert "SLA smoke rule updated" in action_filter_html
    assert 'rule_action_filter=notification' in action_filter_html
    assert 'name="rule_action_filter" value="notification"' in action_filter_html

    action_filter_export_response = await crm.automation_rules_export(
        make_request("owner2"),
        rule_filter="disabled",
        rule_action_filter="notification",
    )
    assert action_filter_export_response.status_code == 200
    action_filter_export_csv = action_filter_export_response.body.decode("utf-8")
    assert "SLA smoke rule updated" in action_filter_export_csv
    assert "notification" in action_filter_export_csv

    enable_response = await crm.enable_automation_rule(
        make_request("owner2"),
        rule["id"],
    )
    assert enable_response.status_code == 302
    assert enable_response.headers["location"] == "/automation?enabled=1"

    second_enable_response = await crm.enable_automation_rule(
        make_request("owner2"),
        rule["id"],
    )
    assert second_enable_response.status_code == 302
    assert second_enable_response.headers["location"] == "/automation?enabled=1"

    conn = connect()
    c = conn.cursor()
    enabled_rule = c.execute("""
    SELECT active
    FROM automation_rules
    WHERE id=?
    """, (rule["id"],)).fetchone()
    conn.close()

    assert enabled_rule["active"] == 1

    cleanup_toggle_response = await crm.toggle_automation_rule(
        make_request("owner2"),
        rule["id"],
    )
    assert cleanup_toggle_response.status_code == 302


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

    conn = connect()
    c = conn.cursor()
    c.execute("""
    INSERT INTO automation_rules (
        company_id, name, trigger_key, conditions_json,
        active, created_by, created_at, updated_at
    )
    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        2,
        "Condition engine smoke",
        "worker_overload",
        json.dumps({
            "mode": "priority_high",
            "field": "priority",
            "operator": "equals",
            "value": "Срочно",
            "label": "Только высокий приоритет",
        }, ensure_ascii=False),
        1,
        "owner2",
        datetime.now().strftime("%Y-%m-%d %H:%M"),
        datetime.now().strftime("%Y-%m-%d %H:%M"),
    ))
    condition_rule_id = c.lastrowid
    c.execute("""
    INSERT INTO automation_actions (
        company_id, rule_id, action_key, payload_json,
        sort_order, active, created_at
    )
    VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        2,
        condition_rule_id,
        "notification",
        json.dumps({
            "target_username": "owner2",
            "message": "Condition matched",
        }, ensure_ascii=False),
        1,
        1,
        datetime.now().strftime("%Y-%m-%d %H:%M"),
    ))
    conn.commit()
    conn.close()

    skipped_condition_events = crm.run_automation_event(
        2,
        "worker_overload",
        "task",
        task["id"],
        "Condition should skip",
        f"/task/{task['id']}",
    )
    assert skipped_condition_events == 0

    conn = connect()
    c = conn.cursor()
    skipped_condition_event = c.execute("""
    SELECT *
    FROM automation_events
    WHERE company_id=2
      AND rule_id=?
    ORDER BY id DESC
    """, (condition_rule_id,)).fetchone()
    c.execute("""
    UPDATE tasks
    SET priority='Срочно'
    WHERE id=?
    """, (task["id"],))
    conn.commit()
    conn.close()

    assert skipped_condition_event["status"] == "skipped"
    assert "Условие не выполнено" in skipped_condition_event["message"]
    assert "Condition should skip" in skipped_condition_event["message"]

    matched_condition_events = crm.run_automation_event(
        2,
        "worker_overload",
        "task",
        task["id"],
        "Condition should match",
        f"/task/{task['id']}",
    )
    assert matched_condition_events == 1

    conn = connect()
    c = conn.cursor()
    matched_condition_event = c.execute("""
    SELECT *
    FROM automation_events
    WHERE company_id=2
      AND rule_id=?
    ORDER BY id DESC
    """, (condition_rule_id,)).fetchone()
    c.execute("""
    UPDATE tasks
    SET priority=?
    WHERE id=?
    """, (
        task["priority"],
        task["id"],
    ))
    conn.commit()
    conn.close()

    assert matched_condition_event["status"] == "done"

    conn = connect()
    c = conn.cursor()
    c.execute("""
    INSERT INTO automation_rules (
        company_id, name, trigger_key, conditions_json,
        active, created_by, created_at, updated_at
    )
    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        2,
        "Payment condition smoke",
        "unpaid_task",
        json.dumps({
            "mode": "payment_paid",
            "field": "payment_status",
            "operator": "equals",
            "value": "Оплачено",
            "label": "Только оплаченные заявки",
        }, ensure_ascii=False),
        1,
        "owner2",
        datetime.now().strftime("%Y-%m-%d %H:%M"),
        datetime.now().strftime("%Y-%m-%d %H:%M"),
    ))
    payment_rule_id = c.lastrowid
    c.execute("""
    INSERT INTO automation_actions (
        company_id, rule_id, action_key, payload_json,
        sort_order, active, created_at
    )
    VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        2,
        payment_rule_id,
        "notification",
        json.dumps({
            "target_username": "owner2",
            "message": "Payment condition matched",
        }, ensure_ascii=False),
        1,
        1,
        datetime.now().strftime("%Y-%m-%d %H:%M"),
    ))
    c.execute("""
    INSERT INTO automation_rules (
        company_id, name, trigger_key, conditions_json,
        active, created_by, created_at, updated_at
    )
    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        2,
        "Status condition smoke",
        "new_client",
        json.dumps({
            "mode": "status_in_progress",
            "field": "status",
            "operator": "equals",
            "value": "В работе",
            "label": "Только заявки в работе",
        }, ensure_ascii=False),
        1,
        "owner2",
        datetime.now().strftime("%Y-%m-%d %H:%M"),
        datetime.now().strftime("%Y-%m-%d %H:%M"),
    ))
    status_rule_id = c.lastrowid
    c.execute("""
    INSERT INTO automation_actions (
        company_id, rule_id, action_key, payload_json,
        sort_order, active, created_at
    )
    VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        2,
        status_rule_id,
        "notification",
        json.dumps({
            "target_username": "owner2",
            "message": "Status condition matched",
        }, ensure_ascii=False),
        1,
        1,
        datetime.now().strftime("%Y-%m-%d %H:%M"),
    ))
    c.execute("""
    UPDATE tasks
    SET payment_status='Оплачено',
        status='В работе'
    WHERE id=?
    """, (task["id"],))
    conn.commit()
    conn.close()

    paid_condition_events = crm.run_automation_event(
        2,
        "unpaid_task",
        "task",
        task["id"],
        "Payment condition should match",
        f"/task/{task['id']}",
    )
    assert paid_condition_events == 1

    status_condition_events = crm.run_automation_event(
        2,
        "new_client",
        "task",
        task["id"],
        "Status condition should match",
        f"/task/{task['id']}",
    )
    assert status_condition_events == 1

    conn = connect()
    c = conn.cursor()
    payment_condition_event = c.execute("""
    SELECT *
    FROM automation_events
    WHERE company_id=2
      AND rule_id=?
    ORDER BY id DESC
    """, (payment_rule_id,)).fetchone()
    status_condition_event = c.execute("""
    SELECT *
    FROM automation_events
    WHERE company_id=2
      AND rule_id=?
    ORDER BY id DESC
    """, (status_rule_id,)).fetchone()
    c.execute("""
    UPDATE tasks
    SET priority=?,
        payment_status='Не оплачено',
        status='Новая'
    WHERE id=?
    """, (
        task["priority"],
        task["id"],
    ))
    conn.commit()
    conn.close()

    assert payment_condition_event["status"] == "done"
    assert status_condition_event["status"] == "done"

    conn = connect()
    c = conn.cursor()
    c.execute("""
    INSERT INTO automation_rules (
        company_id, name, trigger_key, conditions_json,
        active, created_by, created_at, updated_at
    )
    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        2,
        "Worker condition smoke",
        "worker_overload",
        json.dumps({
            "mode": "worker_assigned",
            "field": "workers",
            "operator": "not_empty",
            "label": "Только задачи с исполнителем",
        }, ensure_ascii=False),
        1,
        "owner2",
        datetime.now().strftime("%Y-%m-%d %H:%M"),
        datetime.now().strftime("%Y-%m-%d %H:%M"),
    ))
    worker_rule_id = c.lastrowid
    c.execute("""
    INSERT INTO automation_actions (
        company_id, rule_id, action_key, payload_json,
        sort_order, active, created_at
    )
    VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        2,
        worker_rule_id,
        "notification",
        json.dumps({
            "target_username": "owner2",
            "message": "Worker condition matched",
        }, ensure_ascii=False),
        1,
        1,
        datetime.now().strftime("%Y-%m-%d %H:%M"),
    ))
    conn.commit()
    conn.close()

    worker_condition_events = crm.run_automation_event(
        2,
        "worker_overload",
        "task",
        task["id"],
        "Worker condition should match",
        f"/task/{task['id']}",
    )
    assert worker_condition_events == 1

    conn = connect()
    c = conn.cursor()
    worker_condition_event = c.execute("""
    SELECT *
    FROM automation_events
    WHERE company_id=2
      AND rule_id=?
    ORDER BY id DESC
    """, (worker_rule_id,)).fetchone()
    specific_worker_rule = {
        "conditions_json": json.dumps({
            "mode": "worker_specific",
            "value": "helper2",
            "label": "Исполнитель: helper2",
        }, ensure_ascii=False),
    }
    assert crm.automation_condition_matches(
        c, 2, specific_worker_rule, "task", task["id"]
    )[0] is True

    specific_worker_rule["conditions_json"] = json.dumps({
        "mode": "worker_specific",
        "value": "outsider_worker",
        "label": "Исполнитель: outsider_worker",
    }, ensure_ascii=False)
    assert crm.automation_condition_matches(
        c, 2, specific_worker_rule, "task", task["id"]
    )[0] is False

    task_text_rule = {
        "conditions_json": json.dumps({
            "mode": "task_text_contains",
            "value": "SMOKE",
            "label": "Текст содержит: SMOKE",
        }, ensure_ascii=False),
    }
    assert crm.automation_condition_matches(
        c, 2, task_text_rule, "task", task["id"]
    )[0] is True

    task_text_rule["conditions_json"] = json.dumps({
        "mode": "task_text_contains",
        "value": "отсутствующее слово",
        "label": "Текст содержит: отсутствующее слово",
    }, ensure_ascii=False)
    assert crm.automation_condition_matches(
        c, 2, task_text_rule, "task", task["id"]
    )[0] is False

    specific_client_rule = {
        "conditions_json": json.dumps({
            "mode": "client_specific",
            "value": str(task["client_id"]),
            "label": "Клиент: Client 2",
        }, ensure_ascii=False),
    }
    assert crm.automation_condition_matches(
        c, 2, specific_client_rule, "task", task["id"]
    )[0] is True

    specific_client_rule["conditions_json"] = json.dumps({
        "mode": "client_specific",
        "value": "999999",
        "label": "Клиент: другой",
    }, ensure_ascii=False)
    assert crm.automation_condition_matches(
        c, 2, specific_client_rule, "task", task["id"]
    )[0] is False

    automation_catalog_item = c.execute("""
    SELECT id, name, item_type, unit, price, cost
    FROM catalog_items
    WHERE company_id=2
      AND name='Automation service'
    """).fetchone()
    c.execute("""
    INSERT INTO task_items (
        company_id, task_id, catalog_item_id, item_name, item_type,
        unit, qty, price, cost, total, profit, created_at
    )
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        2,
        task["id"],
        automation_catalog_item["id"],
        automation_catalog_item["name"],
        automation_catalog_item["item_type"],
        automation_catalog_item["unit"],
        1,
        automation_catalog_item["price"],
        automation_catalog_item["cost"],
        automation_catalog_item["price"],
        automation_catalog_item["price"] - automation_catalog_item["cost"],
        datetime.now().strftime("%Y-%m-%d %H:%M"),
    ))
    conn.commit()

    specific_catalog_rule = {
        "conditions_json": json.dumps({
            "mode": "catalog_specific",
            "value": str(automation_catalog_item["id"]),
            "label": "Каталог: Automation service",
        }, ensure_ascii=False),
    }
    assert crm.automation_condition_matches(
        c, 2, specific_catalog_rule, "task", task["id"]
    )[0] is True

    specific_catalog_rule["conditions_json"] = json.dumps({
        "mode": "catalog_specific",
        "value": "999999",
        "label": "Каталог: другой",
    }, ensure_ascii=False)
    assert crm.automation_condition_matches(
        c, 2, specific_catalog_rule, "task", task["id"]
    )[0] is False
    c.execute("""
    DELETE FROM task_items
    WHERE company_id=2
      AND task_id=?
      AND catalog_item_id=?
    """, (
        task["id"],
        automation_catalog_item["id"],
    ))
    conn.commit()

    today = datetime.now().strftime("%Y-%m-%d")
    c.execute("""
    INSERT INTO automation_rules (
        company_id, name, trigger_key, conditions_json,
        active, created_by, created_at, updated_at
    )
    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        2,
        "Date condition smoke",
        "new_client",
        json.dumps({
            "mode": "date_today",
            "field": "task_date",
            "operator": "equals_today",
            "label": "Только задачи на сегодня",
        }, ensure_ascii=False),
        1,
        "owner2",
        datetime.now().strftime("%Y-%m-%d %H:%M"),
        datetime.now().strftime("%Y-%m-%d %H:%M"),
    ))
    date_rule_id = c.lastrowid
    c.execute("""
    INSERT INTO automation_actions (
        company_id, rule_id, action_key, payload_json,
        sort_order, active, created_at
    )
    VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        2,
        date_rule_id,
        "notification",
        json.dumps({
            "target_username": "owner2",
            "message": "Date condition matched",
        }, ensure_ascii=False),
        1,
        1,
        datetime.now().strftime("%Y-%m-%d %H:%M"),
    ))
    c.execute("""
    UPDATE tasks
    SET task_date=?
    WHERE id=?
    """, (today, task["id"]))
    conn.commit()
    conn.close()

    date_condition_events = crm.run_automation_event(
        2,
        "new_client",
        "task",
        task["id"],
        "Date condition should match",
        f"/task/{task['id']}",
    )
    assert date_condition_events == 1

    conn = connect()
    c = conn.cursor()

    today = datetime.now().strftime("%Y-%m-%d")

    c.execute("""
    UPDATE tasks
    SET task_date=?,
        price=?,
        payment_status='Не оплачено',
        status='Новая'
    WHERE id=?
    """, (
        today,
        "15000",
        task["id"],
    ))

    c.execute("""
    INSERT INTO automation_rules (
        company_id, name, trigger_key, conditions_json,
        active, created_by, created_at, updated_at
    )
    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        2,
        "Combined AND condition smoke",
        "combined_and_trigger",
        json.dumps({
            "operator": "and",
            "conditions": [
                {
                    "mode": "date_today",
                    "field": "task_date",
                    "operator": "equals_today",
                    "label": "Только задачи на сегодня",
                },
                {
                    "mode": "price_high",
                    "field": "price",
                    "operator": "gte",
                    "value": "10000",
                    "label": "Только дорогие заявки",
                },
            ],
        }, ensure_ascii=False),
        1,
        "owner2",
        datetime.now().strftime("%Y-%m-%d %H:%M"),
        datetime.now().strftime("%Y-%m-%d %H:%M"),
    ))
    combined_and_rule_id = c.lastrowid

    c.execute("""
    INSERT INTO automation_actions (
        company_id, rule_id, action_key, payload_json,
        sort_order, active, created_at
    )
    VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        2,
        combined_and_rule_id,
        "notification",
        json.dumps({
            "target_username": "owner2",
            "message": "Combined AND condition matched",
        }, ensure_ascii=False),
        1,
        1,
        datetime.now().strftime("%Y-%m-%d %H:%M"),
    ))

    c.execute("""
    INSERT INTO automation_rules (
        company_id, name, trigger_key, conditions_json,
        active, created_by, created_at, updated_at
    )
    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        2,
        "Combined OR condition smoke",
        "combined_or_trigger",
        json.dumps({
            "operator": "or",
            "conditions": [
                {
                    "mode": "client_vip",
                    "field": "client_notes",
                    "operator": "contains",
                    "value": "VIP",
                    "label": "Только VIP клиенты",
                },
                {
                    "mode": "price_high",
                    "field": "price",
                    "operator": "gte",
                    "value": "10000",
                    "label": "Только дорогие заявки",
                },
            ],
        }, ensure_ascii=False),
        1,
        "owner2",
        datetime.now().strftime("%Y-%m-%d %H:%M"),
        datetime.now().strftime("%Y-%m-%d %H:%M"),
    ))
    combined_or_rule_id = c.lastrowid

    c.execute("""
    INSERT INTO automation_actions (
        company_id, rule_id, action_key, payload_json,
        sort_order, active, created_at
    )
    VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        2,
        combined_or_rule_id,
        "notification",
        json.dumps({
            "target_username": "owner2",
            "message": "Combined OR condition matched",
        }, ensure_ascii=False),
        1,
        1,
        datetime.now().strftime("%Y-%m-%d %H:%M"),
    ))

    conn.commit()
    conn.close()

    combined_and_events = crm.run_automation_event(
        2,
        "combined_and_trigger",
        "task",
        task["id"],
        "Combined AND should match",
        f"/task/{task['id']}",
    )
    assert combined_and_events == 1

    combined_or_events = crm.run_automation_event(
        2,
        "combined_or_trigger",
        "task",
        task["id"],
        "Combined OR should match",
        f"/task/{task['id']}",
    )
    assert combined_or_events == 1


    conn = connect()
    c = conn.cursor()
    due_today = datetime.now().strftime("%Y-%m-%dT%H:%M")
    c.execute("""
    UPDATE tasks
    SET price=?,
        deadline_at=?,
        status='Новая'
    WHERE id=?
    """, (
        "15000",
        due_today,
        task["id"],
    ))

    price_condition_rule = {
        "conditions_json": json.dumps({
            "mode": "price_high",
            "value": "20000",
            "label": "Цена заявки от 20000 ₽",
        }, ensure_ascii=False),
    }
    assert crm.automation_condition_matches(
        c, 2, price_condition_rule, "task", task["id"]
    )[0] is False

    price_condition_rule["conditions_json"] = json.dumps({
        "mode": "price_high",
        "value": "12000",
        "label": "Цена заявки от 12000 ₽",
    }, ensure_ascii=False)
    assert crm.automation_condition_matches(
        c, 2, price_condition_rule, "task", task["id"]
    )[0] is True

    condition_smokes = [
        (
            "Price high condition smoke",
            "price_high_trigger",
            {
                "mode": "price_high",
                "field": "price",
                "operator": "gte",
                "value": "12000",
                "label": "Цена заявки от 12000 ₽",
            },
        ),
        (
            "SLA today condition smoke",
            "sla_today_trigger",
            {
                "mode": "sla_today",
                "field": "deadline_at",
                "operator": "date_today",
                "label": "Только дедлайн сегодня",
            },
        ),
    ]

    for rule_name, trigger_key, conditions in condition_smokes:
        c.execute("""
        INSERT INTO automation_rules (
            company_id, name, trigger_key, conditions_json,
            active, created_by, created_at, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            2,
            rule_name,
            trigger_key,
            json.dumps(conditions, ensure_ascii=False),
            1,
            "owner2",
            datetime.now().strftime("%Y-%m-%d %H:%M"),
            datetime.now().strftime("%Y-%m-%d %H:%M"),
        ))

        rule_id = c.lastrowid

        c.execute("""
        INSERT INTO automation_actions (
            company_id, rule_id, action_key, payload_json,
            sort_order, active, created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            2,
            rule_id,
            "notification",
            json.dumps({
                "target_username": "owner2",
                "message": f"{rule_name} matched",
            }, ensure_ascii=False),
            1,
            1,
            datetime.now().strftime("%Y-%m-%d %H:%M"),
        ))

        conn.commit()
        conn.close()

        matched = crm.run_automation_event(
            2,
            trigger_key,
            "task",
            task["id"],
            f"{rule_name} should match",
            f"/task/{task['id']}",
        )

        assert matched == 1

        conn = connect()
        c = conn.cursor()

    c.execute("""
    UPDATE tasks
    SET price=?,
        deadline_at=?
    WHERE id=?
    """, (
        "",
        (datetime.now() - timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M"),
        task["id"],
    ))

    missing_overdue_smokes = [
        (
            "Price missing condition smoke",
            "price_missing_trigger",
            {
                "mode": "price_missing",
                "field": "price",
                "operator": "empty_or_zero",
                "label": "Только заявки без цены",
            },
        ),
        (
            "SLA overdue condition smoke",
            "sla_overdue_trigger",
            {
                "mode": "sla_overdue",
                "field": "deadline_at",
                "operator": "before_now",
                "label": "Только просроченный SLA",
            },
        ),
    ]

    for rule_name, trigger_key, conditions in missing_overdue_smokes:
        c.execute("""
        INSERT INTO automation_rules (
            company_id, name, trigger_key, conditions_json,
            active, created_by, created_at, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            2,
            rule_name,
            trigger_key,
            json.dumps(conditions, ensure_ascii=False),
            1,
            "owner2",
            datetime.now().strftime("%Y-%m-%d %H:%M"),
            datetime.now().strftime("%Y-%m-%d %H:%M"),
        ))

        rule_id = c.lastrowid

        c.execute("""
        INSERT INTO automation_actions (
            company_id, rule_id, action_key, payload_json,
            sort_order, active, created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            2,
            rule_id,
            "notification",
            json.dumps({
                "target_username": "owner2",
                "message": f"{rule_name} matched",
            }, ensure_ascii=False),
            1,
            1,
            datetime.now().strftime("%Y-%m-%d %H:%M"),
        ))

        conn.commit()
        conn.close()

        matched = crm.run_automation_event(
            2,
            trigger_key,
            "task",
            task["id"],
            f"{rule_name} should match",
            f"/task/{task['id']}",
        )

        assert matched == 1

        conn = connect()
        c = conn.cursor()

    conn.commit()
    conn.close()

    conn = connect()
    c = conn.cursor()
    date_condition_event = c.execute("""
    SELECT *
    FROM automation_events
    WHERE company_id=2
      AND rule_id=?
    ORDER BY id DESC
    """, (date_rule_id,)).fetchone()
    c.execute("""
    UPDATE tasks
    SET task_date=?
    WHERE id=?
    """, (
        task["task_date"],
        task["id"],
    ))
    conn.commit()
    conn.close()

    assert worker_condition_event["status"] == "done"
    assert date_condition_event["status"] == "done"

    done_response = await crm.automation_page(
        make_asgi_request("owner2", "/automation"),
        event_filter="done",
    )
    assert done_response.status_code == 200
    done_html = done_response.body.decode("utf-8")
    assert "SLA event happened" in done_html
    assert "Выполнено" in done_html
    assert "Правило: SLA runner rule" in done_html
    assert "Обработано:" in done_html
    assert f"Объект: Заявка #{task['id']}" in done_html
    assert f'href="/task/{task["id"]}"' in done_html
    assert "Открыть заявку" in done_html
    assert 'href="/automation/events/export?event_filter=done"' in done_html
    assert "Все триггеры" in done_html

    done_export_response = await crm.automation_events_export(
        make_request("owner2"),
        event_filter="done",
    )
    assert done_export_response.status_code == 200
    done_export_csv = done_export_response.body.decode("utf-8")
    assert "SLA event happened" in done_export_csv
    assert "SLA runner rule" in done_export_csv
    assert "done" in done_export_csv

    trigger_filter_response = await crm.automation_page(
        make_asgi_request("owner2", "/automation"),
        event_filter="done",
        trigger_filter="sla_overdue",
    )
    assert trigger_filter_response.status_code == 200
    trigger_filter_html = trigger_filter_response.body.decode("utf-8")
    assert 'option value="sla_overdue" selected' in trigger_filter_html
    assert "SLA event happened" in trigger_filter_html
    assert 'href="/automation/events/export?event_filter=done&trigger_filter=sla_overdue"' in trigger_filter_html

    trigger_export_response = await crm.automation_events_export(
        make_request("owner2"),
        event_filter="done",
        trigger_filter="sla_overdue",
    )
    assert trigger_export_response.status_code == 200
    trigger_export_csv = trigger_export_response.body.decode("utf-8")
    assert "SLA event happened" in trigger_export_csv
    assert "sla_overdue" in trigger_export_csv

    entity_filter_response = await crm.automation_page(
        make_asgi_request("owner2", "/automation"),
        event_filter="done",
        event_entity_filter="task",
    )
    assert entity_filter_response.status_code == 200
    entity_filter_html = entity_filter_response.body.decode("utf-8")
    assert 'option value="task" selected' in entity_filter_html
    assert 'name="event_entity_filter" value="task"' in entity_filter_html
    assert "SLA event happened" in entity_filter_html
    assert 'href="/automation/events/export?event_filter=done&event_entity_filter=task"' in entity_filter_html

    entity_export_response = await crm.automation_events_export(
        make_request("owner2"),
        event_filter="done",
        event_entity_filter="task",
    )
    assert entity_export_response.status_code == 200
    entity_export_csv = entity_export_response.body.decode("utf-8")
    assert "SLA event happened" in entity_export_csv
    assert "task" in entity_export_csv

    event_search_response = await crm.automation_page(
        make_asgi_request("owner2", "/automation"),
        event_filter="done",
        event_search="happened",
    )
    assert event_search_response.status_code == 200
    event_search_html = event_search_response.body.decode("utf-8")
    assert 'name="event_search" value="happened"' in event_search_html
    assert "SLA event happened" in event_search_html
    assert 'href="/automation/events/export?event_filter=done&event_search=happened"' in event_search_html

    event_search_export_response = await crm.automation_events_export(
        make_request("owner2"),
        event_filter="done",
        event_search="happened",
    )
    assert event_search_export_response.status_code == 200
    event_search_export_csv = event_search_export_response.body.decode("utf-8")
    assert "SLA event happened" in event_search_export_csv
    assert "SLA runner rule" in event_search_export_csv

    event_day = event["created_at"][:10]
    event_date_response = await crm.automation_page(
        make_asgi_request("owner2", "/automation"),
        event_filter="done",
        event_date_from=event_day,
        event_date_to=event_day,
    )
    assert event_date_response.status_code == 200
    event_date_html = event_date_response.body.decode("utf-8")
    assert f'name="event_date_from" value="{event_day}"' in event_date_html
    assert f'name="event_date_to" value="{event_day}"' in event_date_html
    assert "SLA event happened" in event_date_html
    assert f"event_date_from={event_day}" in event_date_html

    event_date_export_response = await crm.automation_events_export(
        make_request("owner2"),
        event_filter="done",
        event_date_from=event_day,
        event_date_to=event_day,
    )
    assert event_date_export_response.status_code == 200
    event_date_export_csv = event_date_export_response.body.decode("utf-8")
    assert "SLA event happened" in event_date_export_csv
    assert "SLA runner rule" in event_date_export_csv

    conn = connect()
    c = conn.cursor()
    c.executemany("""
    INSERT INTO automation_events (
        company_id, rule_id, trigger_key, entity_type, entity_id,
        status, message, created_at, processed_at
    )
    VALUES (2, ?, 'sla_overdue', 'task', ?, 'skipped', ?, ?, ?)
    """, [
        (
            event["rule_id"],
            task["id"],
            f"Newer skipped event {idx}",
            f"2026-05-25 10:{idx:02d}:00",
            f"2026-05-25 10:{idx:02d}:30",
        )
        for idx in range(35)
    ])
    conn.commit()
    conn.close()

    filtered_done_response = await crm.automation_page(
        make_asgi_request("owner2", "/automation"),
        event_filter="done",
    )
    assert filtered_done_response.status_code == 200
    filtered_done_html = filtered_done_response.body.decode("utf-8")
    assert "SLA event happened" in filtered_done_html
    assert "Newer skipped event 34" not in filtered_done_html

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

    conn = connect()
    c = conn.cursor()
    c.execute("""
    UPDATE users
    SET telegram_chat_id='chat-owner2'
    WHERE company_id=2
      AND username='owner2'
    """)
    conn.commit()
    conn.close()

    sent_telegram_messages = []
    original_send_message_to_chat = crm.send_message_to_chat
    crm.send_message_to_chat = lambda chat_id, text: sent_telegram_messages.append((chat_id, text)) or True

    try:
        ai_digest_events = crm.run_automation_event(
            2,
            "weekly_digest",
            "company",
            2,
            "Weekly digest event",
            "/ai/insights",
        )
    finally:
        crm.send_message_to_chat = original_send_message_to_chat

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
    assert sent_telegram_messages
    assert sent_telegram_messages[-1][0] == "chat-owner2"
    assert "AI-сводка по бизнесу" in sent_telegram_messages[-1][1]

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
      AND message='Ежедневная AI-сводка 2026-05-25'
    ORDER BY id DESC
    """).fetchone()

    weekly_event = c.execute("""
    SELECT *
    FROM automation_events
    WHERE company_id=2
      AND trigger_key='weekly_digest'
      AND message='Еженедельная AI-сводка 2026-W22'
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


async def assert_ai_assistant_page():
    response = await crm.ai_assistant_page(make_asgi_request("owner2", "/ai/assistant"))
    assert response.status_code == 200
    html = response.body.decode("utf-8")
    assert "AI-помощник" in html
    assert "Что сделать сейчас" in html
    assert "Порядок работы" in html
    assert "AI-инсайты" in html
    assert 'action="/ai/insights/digest"' in html
    assert "Создать AI-сводку" in html
    assert "Быстрые действия" in html
    assert 'action="/overdue/reminders"' in html
    assert 'action="/sla/reminders"' in html
    assert 'action="/ai/assistant/follow-ups/notify"' in html
    assert 'action="/automation/ai-digest/run"' in html
    assert 'action="/ai/assistant/setup-digests"' in html
    assert "Запустить SLA-напоминания" in html
    assert "Запустить AI-планировщик" in html
    assert "Настроить дневные и недельные AI-сводки" in html
    assert "История действий" in html
    assert "Выполнено" in html
    assert "Журнал AI-помощника" in html
    assert 'href="/ai/assistant/events/export"' in html
    assert 'href="/ai/assistant?event_filter=created"' in html
    assert 'href="/ai/assistant?event_filter=notification_sent"' in html
    assert "Заметки владельца" in html
    assert "Выполненные решения" in html
    assert 'action="/ai/assistant/notes"' in html
    assert 'href="/ai/assistant?note_filter=due"' in html
    assert 'href="/ai/assistant?note_filter=urgent"' in html
    assert 'name="note_search"' in html
    assert 'name="priority"' in html
    assert 'name="follow_up_date"' in html
    assert "Срочно" in html
    assert "Не оплачено" in html
    assert "AI к контролю" in html
    assert "AI срочно" in html
    assert "AI активные" in html

    empty_note_response = await crm.add_ai_assistant_note(
        make_form_request(
            "owner2",
            "/ai/assistant/notes",
            {"note": ""},
        )
    )
    assert empty_note_response.status_code == 302
    assert empty_note_response.headers["location"] == "/ai/assistant?note_error=empty"

    note_response = await crm.add_ai_assistant_note(
        make_form_request(
            "owner2",
            "/ai/assistant/notes",
            {
                "note": "Проверить AI assistant рекомендацию",
                "priority": "urgent",
                "follow_up_date": "2026-05-26",
            },
        )
    )
    assert note_response.status_code == 302
    assert note_response.headers["location"] == "/ai/assistant?note_created=1"

    notes_response = await crm.ai_assistant_page(make_asgi_request("owner2", "/ai/assistant"))
    assert notes_response.status_code == 200
    notes_html = notes_response.body.decode("utf-8")
    assert "Проверить AI assistant рекомендацию" in notes_html
    assert "/create-task?ai_note_id=" in notes_html
    assert "AI к контролю" in notes_html

    urgent_filter_response = await crm.ai_assistant_page(
        make_asgi_request("owner2", "/ai/assistant"),
        note_filter="urgent",
    )
    assert urgent_filter_response.status_code == 200
    urgent_filter_html = urgent_filter_response.body.decode("utf-8")
    assert "Проверить AI assistant рекомендацию" in urgent_filter_html
    assert 'href="/ai/assistant?note_filter=urgent" class="active"' in urgent_filter_html

    search_response = await crm.ai_assistant_page(
        make_asgi_request("owner2", "/ai/assistant"),
        note_search="рекомендацию",
    )
    assert search_response.status_code == 200
    search_html = search_response.body.decode("utf-8")
    assert 'name="note_search" placeholder="Поиск по AI заметкам" value="рекомендацию"' in search_html
    assert "Проверить AI assistant рекомендацию" in search_html

    conn = connect()
    c = conn.cursor()
    saved_note = c.execute("""
    SELECT *
    FROM ai_assistant_notes
    WHERE company_id=2
      AND username='owner2'
    ORDER BY id DESC
    """).fetchone()
    conn.close()

    assert saved_note is not None
    assert saved_note["note"] == "Проверить AI assistant рекомендацию"
    assert saved_note["priority"] == "urgent"
    assert saved_note["follow_up_date"] == "2026-05-26"
    assert saved_note["is_done"] == 0

    conn = connect()
    c = conn.cursor()
    created_event = c.execute("""
    SELECT *
    FROM ai_assistant_events
    WHERE company_id=2
      AND note_id=?
      AND username='owner2'
      AND action='created'
    ORDER BY id DESC
    """, (saved_note["id"],)).fetchone()
    conn.close()

    assert created_event is not None
    assert created_event["details"] == "Проверить AI assistant рекомендацию"

    digest_message = crm.build_ai_digest_message(2)
    assert "Активные заметки владельца" in digest_message
    assert "Срочно: Проверить AI assistant рекомендацию" in digest_message
    assert "контроль: 2026-05-26" in digest_message

    conn = connect()
    c = conn.cursor()
    c.execute("""
    UPDATE users
    SET telegram_chat_id='chat-owner2'
    WHERE company_id=2
      AND username='owner2'
    """)
    conn.commit()
    conn.close()

    sent_follow_up_telegram_messages = []
    original_send_message_to_chat = crm.send_message_to_chat
    crm.send_message_to_chat = (
        lambda chat_id, text: sent_follow_up_telegram_messages.append((chat_id, text)) or True
    )

    try:
        follow_up_response = await crm.notify_ai_assistant_follow_ups(make_request("owner2"))
    finally:
        crm.send_message_to_chat = original_send_message_to_chat

    assert follow_up_response.status_code == 302
    assert follow_up_response.headers["location"].startswith(
        "/ai/assistant?follow_up_notifications="
    )
    assert sent_follow_up_telegram_messages
    assert sent_follow_up_telegram_messages[-1][0] == "chat-owner2"
    assert "Проверить AI assistant рекомендацию" in sent_follow_up_telegram_messages[-1][1]

    conn = connect()
    c = conn.cursor()
    follow_up_notification = c.execute("""
    SELECT *
    FROM notifications
    WHERE company_id=2
      AND username='owner2'
      AND title=?
    ORDER BY id DESC
    """, (f"AI контроль: заметка #{saved_note['id']}",)).fetchone()
    conn.close()

    assert follow_up_notification is not None
    assert follow_up_notification["message"] == "Проверить AI assistant рекомендацию"
    assert follow_up_notification["link"] == "/ai/assistant"

    conn = connect()
    c = conn.cursor()
    notification_event = c.execute("""
    SELECT *
    FROM ai_assistant_events
    WHERE company_id=2
      AND note_id=?
      AND username='owner2'
      AND action='notification_sent'
    ORDER BY id DESC
    """, (saved_note["id"],)).fetchone()
    conn.close()

    assert notification_event is not None

    conn = connect()
    c = conn.cursor()
    notified_note = c.execute("""
    SELECT *
    FROM ai_assistant_notes
    WHERE id=?
      AND company_id=2
    """, (saved_note["id"],)).fetchone()
    conn.close()

    assert notified_note["last_notified_at"]
    assert notified_note["notification_count"] >= 1

    notified_page_response = await crm.ai_assistant_page(make_asgi_request("owner2", "/ai/assistant"))
    assert notified_page_response.status_code == 200
    notified_html = notified_page_response.body.decode("utf-8")
    assert "раз:" in notified_html
    assert f"/ai/assistant/notes/{saved_note['id']}/postpone" in notified_html
    assert "Завтра" in notified_html
    assert "Через неделю" in notified_html

    postponed_response = await crm.postpone_ai_assistant_note(
        make_form_request(
            "owner2",
            f"/ai/assistant/notes/{saved_note['id']}/postpone",
            {"days": "1"},
        ),
        saved_note["id"],
    )
    assert postponed_response.status_code == 302
    assert postponed_response.headers["location"] == "/ai/assistant?note_postponed=1"

    conn = connect()
    c = conn.cursor()
    postponed_note = c.execute("""
    SELECT follow_up_date
    FROM ai_assistant_notes
    WHERE id=?
      AND company_id=2
    """, (saved_note["id"],)).fetchone()
    conn.close()

    assert postponed_note["follow_up_date"] == (
        datetime.now() + timedelta(days=1)
    ).strftime("%Y-%m-%d")

    conn = connect()
    c = conn.cursor()
    postponed_event = c.execute("""
    SELECT *
    FROM ai_assistant_events
    WHERE company_id=2
      AND note_id=?
      AND username='owner2'
      AND action='postponed'
    ORDER BY id DESC
    """, (saved_note["id"],)).fetchone()
    conn.close()

    assert postponed_event is not None

    scheduled_note_response = await crm.add_ai_assistant_note(
        make_form_request(
            "owner2",
            "/ai/assistant/notes",
            {
                "note": "Автоматический AI контроль",
                "priority": "normal",
                "follow_up_date": "2026-05-26",
            },
        )
    )
    assert scheduled_note_response.status_code == 302

    scheduled_follow_ups = crm.run_ai_digest_scheduler(
        2,
        datetime(2026, 5, 26, 10, 0),
    )
    assert scheduled_follow_ups["follow_ups"] >= 1

    conn = connect()
    c = conn.cursor()
    scheduled_follow_up_notification = c.execute("""
    SELECT *
    FROM notifications
    WHERE company_id=2
      AND username='owner2'
      AND message='Автоматический AI контроль'
    ORDER BY id DESC
    """).fetchone()
    conn.close()

    assert scheduled_follow_up_notification is not None

    ai_note_task_response = await crm.create_task_page(
        make_asgi_request("owner2", "/create-task"),
        ai_note_id=saved_note["id"],
    )
    assert ai_note_task_response.status_code == 200
    ai_note_task_html = ai_note_task_response.body.decode("utf-8")
    assert f'name="ai_note_id" value="{saved_note["id"]}"' in ai_note_task_html
    assert "Проверить AI assistant рекомендацию</textarea>" in ai_note_task_html

    done_response = await crm.complete_ai_assistant_note(
        make_form_request(
            "owner2",
            f"/ai/assistant/notes/{saved_note['id']}/done",
            {},
        ),
        saved_note["id"],
    )
    assert done_response.status_code == 302
    assert done_response.headers["location"] == "/ai/assistant?note_done=1"

    conn = connect()
    c = conn.cursor()
    completed_note = c.execute("""
    SELECT *
    FROM ai_assistant_notes
    WHERE id=?
      AND company_id=2
    """, (saved_note["id"],)).fetchone()
    conn.close()

    assert completed_note is not None
    assert completed_note["is_done"] == 1
    assert completed_note["done_by"] == "owner2"

    conn = connect()
    c = conn.cursor()
    done_event = c.execute("""
    SELECT *
    FROM ai_assistant_events
    WHERE company_id=2
      AND note_id=?
      AND username='owner2'
      AND action='done'
    ORDER BY id DESC
    """, (saved_note["id"],)).fetchone()
    conn.close()

    assert done_event is not None

    done_events_response = await crm.ai_assistant_page(
        make_asgi_request("owner2", "/ai/assistant"),
        event_filter="done",
    )
    assert done_events_response.status_code == 200
    done_events_html = done_events_response.body.decode("utf-8")
    assert 'href="/ai/assistant?event_filter=done" class="active"' in done_events_html
    assert 'href="/ai/assistant/events/export?event_filter=done"' in done_events_html
    assert "Выполнено" in done_events_html

    events_export_response = await crm.ai_assistant_events_export(make_request("owner2"))
    assert events_export_response.status_code == 200
    events_export_csv = events_export_response.body.decode("utf-8")
    assert "Дата,Автор,Действие,Заметка ID,Детали" in events_export_csv
    assert "owner2" in events_export_csv
    assert "created" in events_export_csv
    assert "done" in events_export_csv

    done_events_export_response = await crm.ai_assistant_events_export(
        make_request("owner2"),
        event_filter="done",
    )
    assert done_events_export_response.status_code == 200
    done_events_export_csv = done_events_export_response.body.decode("utf-8")
    assert "done" in done_events_export_csv
    assert "created" not in done_events_export_csv

    completed_page_response = await crm.ai_assistant_page(make_asgi_request("owner2", "/ai/assistant"))
    assert completed_page_response.status_code == 200
    completed_html = completed_page_response.body.decode("utf-8")
    assert "Проверить AI assistant рекомендацию" in completed_html
    assert "Без заявки" in completed_html

    completed_search_response = await crm.ai_assistant_page(
        make_asgi_request("owner2", "/ai/assistant"),
        note_search="рекомендацию",
    )
    assert completed_search_response.status_code == 200
    completed_search_html = completed_search_response.body.decode("utf-8")
    assert "Проверить AI assistant рекомендацию" in completed_search_html
    assert "Выполненные решения" in completed_search_html

    task_note_response = await crm.add_ai_assistant_note(
        make_form_request(
            "owner2",
            "/ai/assistant/notes",
            {"note": "Создать заявку из AI заметки"},
        )
    )
    assert task_note_response.status_code == 302

    conn = connect()
    c = conn.cursor()
    task_note = c.execute("""
    SELECT *
    FROM ai_assistant_notes
    WHERE company_id=2
      AND username='owner2'
      AND note='Создать заявку из AI заметки'
    ORDER BY id DESC
    """).fetchone()
    conn.close()

    assert task_note is not None

    original_send_message = crm.send_message
    original_send_message_to_chat = crm.send_message_to_chat
    crm.send_message = lambda text: True
    crm.send_message_to_chat = lambda chat_id, text: True

    try:
        created_task_response = await crm.create_task(
            make_multipart_request(
                "owner2",
                "/create-task",
                {
                    "client": "AI client",
                    "phone": "+70000000001",
                    "address": "AI address",
                    "description": "Создать заявку из AI заметки",
                    "task_date": "2026-05-26",
                    "ai_note_id": str(task_note["id"]),
                    "priority": "Обычный",
                    "price": "0",
                },
            ),
            photo=None,
        )
    finally:
        crm.send_message = original_send_message
        crm.send_message_to_chat = original_send_message_to_chat

    assert created_task_response.status_code == 302
    assert created_task_response.headers["location"] == "/"

    conn = connect()
    c = conn.cursor()
    linked_note = c.execute("""
    SELECT *
    FROM ai_assistant_notes
    WHERE id=?
      AND company_id=2
    """, (task_note["id"],)).fetchone()
    conn.close()

    assert linked_note is not None
    assert linked_note["is_done"] == 1
    assert linked_note["created_task_id"] is not None

    linked_page_response = await crm.ai_assistant_page(make_asgi_request("owner2", "/ai/assistant"))
    assert linked_page_response.status_code == 200
    linked_html = linked_page_response.body.decode("utf-8")
    assert "Создать заявку из AI заметки" in linked_html
    assert f"/task/{linked_note['created_task_id']}" in linked_html

    conn = connect()
    c = conn.cursor()
    digest_rule_ids = [
        row["id"]
        for row in c.execute("""
        SELECT id
        FROM automation_rules
        WHERE company_id=2
          AND trigger_key IN ('daily_digest', 'weekly_digest')
        """).fetchall()
    ]

    for rule_id in digest_rule_ids:
        c.execute("""
        DELETE FROM automation_actions
        WHERE company_id=2
          AND rule_id=?
        """, (rule_id,))
        c.execute("""
        DELETE FROM automation_rules
        WHERE company_id=2
          AND id=?
        """, (rule_id,))

    conn.commit()
    conn.close()

    setup_response = await crm.setup_ai_assistant_digest_rules(make_request("owner2"))
    assert setup_response.status_code == 302
    assert setup_response.headers["location"] == "/ai/assistant?digest_rules=2"

    duplicate_setup_response = await crm.setup_ai_assistant_digest_rules(make_request("owner2"))
    assert duplicate_setup_response.status_code == 302
    assert duplicate_setup_response.headers["location"] == "/ai/assistant?digest_rules=0"

    conn = connect()
    c = conn.cursor()
    digest_rule_count = c.execute("""
    SELECT COUNT(*)
    FROM automation_rules
    JOIN automation_actions
      ON automation_actions.rule_id=automation_rules.id
      AND automation_actions.company_id=automation_rules.company_id
    WHERE automation_rules.company_id=2
      AND automation_rules.trigger_key IN ('daily_digest', 'weekly_digest')
      AND automation_actions.action_key='ai_digest'
    """).fetchone()[0]
    conn.close()

    assert digest_rule_count >= 2


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
    fixed_team_start = datetime.now().date()
    fixed_team_result = crm.build_scheduling_recommendations(
        worker_capacities={"worker_a": 1, "worker_b": 1},
        assignments=[{
            "date": fixed_team_start.strftime("%Y-%m-%d"),
            "workers": ["worker_a"],
        }],
        start_date=fixed_team_start,
        search_days=3,
        fixed_workers=["worker_a", "worker_b"],
    )
    assert fixed_team_result["summary"]["required_workers"] == 2
    assert fixed_team_result["summary"]["days_with_capacity"] == 2
    assert fixed_team_result["items"][0]["date"] == (
        fixed_team_start + timedelta(days=1)
    ).strftime("%Y-%m-%d")
    assert fixed_team_result["items"][0]["worker_names"] == [
        "worker_a",
        "worker_b",
    ]
    unavailable_team_result = crm.build_scheduling_recommendations(
        worker_capacities={"worker_a": 1, "worker_b": 1},
        assignments=[],
        start_date=fixed_team_start,
        search_days=3,
        fixed_workers=["worker_a", "worker_b"],
        unavailable_dates={
            "worker_b": {fixed_team_start.strftime("%Y-%m-%d")},
        },
    )
    assert unavailable_team_result["items"][0]["date"] == (
        fixed_team_start + timedelta(days=1)
    ).strftime("%Y-%m-%d")

    conn = connect()
    c = conn.cursor()
    c.execute("""
    UPDATE users
    SET daily_capacity=1
    WHERE company_id=2
      AND username IN ('worker2', 'helper2')
    """)
    conn.commit()
    conn.close()

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
    assert "Лимит исчерпан" in manager_html
    assert "Предыдущий день" in manager_html
    assert "Следующий день" in manager_html
    assert "Недельный планировщик" in manager_html
    assert "Предыдущая" in manager_html
    assert "Текущая неделя" in manager_html
    assert "Следующая" in manager_html
    assert "Общая вместимость" in manager_html
    assert "Загрузка недели" in manager_html
    assert "Дней без мест" in manager_html
    assert "Дата нужной недели" in manager_html
    assert "Перейти" in manager_html
    assert "Умный подбор окна" in manager_html
    assert "Найти окно" in manager_html
    assert "Начать поиск" in manager_html
    assert "Проверено дней:" in manager_html
    assert "Дней с нужной командой:" in manager_html
    assert "Средняя загрузка после назначения:" in manager_html
    assert "Обязательный исполнитель: helper2" in manager_html
    assert "week-cell" in manager_html
    assert "Рекомендованное свободное окно" in manager_html
    assert "/calendar?date=2026-05-16&amp;worker=helper2&amp;status=" in manager_html
    assert "/calendar?date=2026-05-18&amp;worker=helper2&amp;status=" in manager_html
    assert "/calendar?week_start=2026-05-04&amp;worker=helper2&amp;status=" in manager_html
    assert "/calendar?week_start=2026-05-18&amp;worker=helper2&amp;status=" in manager_html
    assert "Всего: 3" in manager_html
    assert "Свободно: 1" in manager_html
    assert "Лимит исчерпан: 2" in manager_html
    assert "/create-task?task_date=2026-05-17&return_to=calendar" in manager_html
    assert "/create-task?task_date=2026-05-17&worker=free2" in manager_html
    assert "free2" in manager_html
    assert "Свободен: 3 мест" in manager_html
    assert "Лимит исчерпан: 1 из 1" in manager_html
    assert "availability-progress" in manager_html
    assert "Рекомендован" in manager_html
    helper_availability = next(
        item
        for item in manager_response.context["worker_availability"]
        if item["username"] == "helper2"
    )
    assert helper_availability["available_slots"] == 0
    assert helper_availability["is_at_capacity"] is True
    assert helper_availability["load_percent"] == 100
    assert manager_response.context["selected_week_start"] == "2026-05-11"
    assert manager_response.context["selected_week_end"] == "2026-05-17"
    assert len(manager_response.context["weekly_capacity_days"]) == 7
    assert len(manager_response.context["weekly_capacity_rows"]) == 1
    assert all(
        row["username"] != "outsider_worker"
        for row in manager_response.context["weekly_capacity_rows"]
    )
    assert manager_response.context["weekly_capacity_summary"] == {
        "assignments": 1,
        "capacity": 7,
        "available_slots": 6,
        "full_cells": 1,
        "unavailable_cells": 0,
        "conflict_assignments": 0,
        "utilization_percent": 14,
    }
    helper_week = next(
        row
        for row in manager_response.context["weekly_capacity_rows"]
        if row["username"] == "helper2"
    )
    helper_sunday = next(
        cell
        for cell in helper_week["cells"]
        if cell["date"] == "2026-05-17"
    )
    assert helper_sunday["task_count"] == 1
    assert helper_sunday["available_slots"] == 0
    assert helper_sunday["status"] == "full"
    assert helper_sunday["calendar_url"].startswith(
        "/calendar?date=2026-05-17&worker=helper2"
    )
    assert helper_sunday["create_url"].startswith(
        "/create-task?task_date=2026-05-17&worker=helper2"
    )
    today_value = datetime.now().date()
    assert manager_response.context["selected_schedule_start"] == (
        today_value.strftime("%Y-%m-%d")
    )
    assert manager_response.context["selected_schedule_days"] == 14
    assert manager_response.context["selected_schedule_workers"] == 1
    assert manager_response.context["smart_schedule_items"]
    assert (
        manager_response.context["smart_schedule_items"][0]["date"]
        == today_value.strftime("%Y-%m-%d")
    )
    assert (
        manager_response.context["smart_schedule_items"][0]["worker_names"]
        == ["helper2"]
    )
    assert all(
        "outsider_worker" not in item["worker_names"]
        for item in manager_response.context["smart_schedule_items"]
    )

    free_response = await crm.calendar_page(
        make_asgi_request("owner2"),
        date="2026-05-17",
        availability="free",
    )
    assert free_response.status_code == 200
    free_html = free_response.body.decode("utf-8")
    assert "free2" in free_html
    assert "Лимит исчерпан: 1 из 1" not in free_html
    assert "/calendar?date=2026-05-18&amp;availability=free" in free_html
    assert len(free_response.context["weekly_capacity_rows"]) == 3
    assert all(
        row["username"] != "outsider_worker"
        for row in free_response.context["weekly_capacity_rows"]
    )

    team_schedule_response = await crm.calendar_page(
        make_asgi_request("owner2"),
        schedule_start="2026-05-17",
        schedule_days=7,
        schedule_workers=2,
    )
    assert team_schedule_response.status_code == 200
    team_schedule_html = team_schedule_response.body.decode("utf-8")
    assert '<option value="7" selected>7 дней</option>' in team_schedule_html
    assert '<option value="2" selected>2</option>' in team_schedule_html
    assert "Создать заявку" in team_schedule_html
    assert team_schedule_response.context["smart_schedule_summary"] == {
        "search_days": 7,
        "required_workers": 2,
        "days_with_capacity": 7,
        "total_open_slots": 35,
        "found": 7,
    }
    best_team_slot = team_schedule_response.context["smart_schedule_items"][0]
    assert best_team_slot["date"] == today_value.strftime("%Y-%m-%d")
    assert best_team_slot["worker_names"] == ["free2", "helper2"]
    assert "workers_csv=free2%2Chelper2" in best_team_slot["create_url"]
    assert "outsider_worker" not in best_team_slot["worker_names"]

    team_create_response = await crm.create_task_page(
        make_asgi_request("owner2", "/create-task"),
        task_date=best_team_slot["date"],
        worker=best_team_slot["worker_names"][0],
        workers_csv=",".join(best_team_slot["worker_names"]),
        return_to="calendar",
    )
    assert team_create_response.status_code == 200
    assert team_create_response.context["selected_workers"] == [
        "free2",
        "helper2",
    ]
    team_create_html = team_create_response.body.decode("utf-8")
    assert 'value="free2" data-at-capacity="0" checked' in team_create_html
    assert 'value="helper2" data-at-capacity="0" checked' in team_create_html

    schedule_api = crm.api_calendar_smart_schedule(
        make_request("owner2"),
        start="2026-05-17",
        days=7,
        workers=2,
    )
    assert schedule_api["ok"] is True
    assert schedule_api["company_id"] == 2
    assert schedule_api["start"] == today_value.strftime("%Y-%m-%d")
    assert schedule_api["end"] == (
        today_value + timedelta(days=6)
    ).strftime("%Y-%m-%d")
    assert schedule_api["summary"]["required_workers"] == 2
    assert schedule_api["items"][0]["worker_names"] == [
        "free2",
        "helper2",
    ]
    assert all(
        "outsider_worker" not in item["worker_names"]
        for item in schedule_api["items"]
    )
    assert "workers_csv=free2%2Chelper2" in (
        schedule_api["items"][0]["create_url"]
    )

    invalid_worker_api = crm.api_calendar_smart_schedule(
        make_request("owner2"),
        start="2026-05-17",
        worker="outsider_worker",
    )
    assert invalid_worker_api.status_code == 400
    assert json.loads(invalid_worker_api.body)["error"] == "invalid_worker"

    worker_api = crm.api_calendar_smart_schedule(
        make_request("helper2"),
        start="2026-05-17",
    )
    assert worker_api.status_code == 403
    assert json.loads(worker_api.body)["error"] == "forbidden"

    anonymous_api = crm.api_calendar_smart_schedule(
        make_request(),
        start="2026-05-17",
    )
    assert anonymous_api.status_code == 401
    assert json.loads(anonymous_api.body)["error"] == "unauthorized"

    conn = connect()
    c = conn.cursor()
    helper = c.execute("""
    SELECT id
    FROM users
    WHERE company_id=2 AND username='helper2'
    """).fetchone()
    task = c.execute("""
    SELECT *
    FROM tasks
    WHERE company_id=? AND client=?
    """, (2, "Client 2")).fetchone()
    unavailable_end = today_value + timedelta(days=1)
    c.execute("""
    INSERT INTO worker_unavailability (
        company_id, worker_id, date_from, date_to,
        reason, created_by, created_at
    )
    VALUES (2, ?, ?, ?, 'Отпуск smoke', 'owner2', ?)
    """, (
        helper["id"],
        today_value.strftime("%Y-%m-%d"),
        unavailable_end.strftime("%Y-%m-%d"),
        datetime.now().strftime("%Y-%m-%d %H:%M"),
    ))
    unavailable_period_id = c.lastrowid
    conn.commit()
    conn.close()

    unavailable_calendar = await crm.calendar_page(
        make_asgi_request("owner2"),
        worker="helper2",
        date=today_value.strftime("%Y-%m-%d"),
        week_start=today_value.strftime("%Y-%m-%d"),
        schedule_start=today_value.strftime("%Y-%m-%d"),
        schedule_days=7,
    )
    unavailable_html = unavailable_calendar.body.decode("utf-8")
    helper_availability = next(
        item
        for item in unavailable_calendar.context["worker_availability"]
        if item["username"] == "helper2"
    )
    assert helper_availability["is_unavailable"] is True
    assert helper_availability["available_slots"] == 0
    assert helper_availability["unavailable_reason"] == "Отпуск smoke"
    assert "Недоступны: 1" in unavailable_html
    assert "Отпуск smoke" in unavailable_html
    helper_week = unavailable_calendar.context["weekly_capacity_rows"][0]
    unavailable_cells = [
        cell
        for cell in helper_week["cells"]
        if cell["status"] == "unavailable"
    ]
    assert len(unavailable_cells) == 2
    assert helper_week["total_capacity"] == 5
    assert helper_week["unavailable_days"] == 2
    assert (
        unavailable_calendar.context["smart_schedule_items"][0]["date"]
        == (today_value + timedelta(days=2)).strftime("%Y-%m-%d")
    )

    unavailable_filter = await crm.calendar_page(
        make_asgi_request("owner2"),
        date=today_value.strftime("%Y-%m-%d"),
        availability="unavailable",
    )
    assert unavailable_filter.context["selected_availability"] == "unavailable"
    assert [
        item["username"]
        for item in unavailable_filter.context["worker_availability"]
    ] == ["helper2"]

    unavailable_api = crm.api_calendar_smart_schedule(
        make_request("owner2"),
        start=today_value.strftime("%Y-%m-%d"),
        days=7,
        worker="helper2",
    )
    assert unavailable_api["items"][0]["date"] == (
        today_value + timedelta(days=2)
    ).strftime("%Y-%m-%d")

    unavailable_create_page = await crm.create_task_page(
        make_asgi_request("owner2", "/create-task"),
        task_date=today_value.strftime("%Y-%m-%d"),
        worker="helper2",
    )
    assert unavailable_create_page.context["selected_worker_unavailable"] is True
    assert "Исполнитель недоступен на эту дату" in (
        unavailable_create_page.body.decode("utf-8")
    )
    helper_option = next(
        item
        for item in unavailable_create_page.context["worker_options"]
        if item["username"] == "helper2"
    )
    assert helper_option["is_unavailable"] is True

    blocked_create = await crm.create_task(
        make_form_request(
            "owner2",
            "/create-task",
            {
                "client": "Blocked absence client",
                "task_date": today_value.strftime("%Y-%m-%d"),
                "workers": "helper2",
                "priority": "Обычный",
            },
        ),
    )
    assert blocked_create.status_code == 302
    assert "error=worker_unavailable" in blocked_create.headers["location"]
    conn = connect()
    c = conn.cursor()
    assert c.execute("""
    SELECT COUNT(*)
    FROM tasks
    WHERE company_id=2 AND client='Blocked absence client'
    """).fetchone()[0] == 0
    conn.close()

    unavailable_reschedule = await crm.update_task_date(
        make_form_request(
            "owner2",
            f"/task/{task['id']}/date",
            {"task_date": today_value.strftime("%Y-%m-%d")},
        ),
        task["id"],
    )
    assert unavailable_reschedule.status_code == 302
    assert unavailable_reschedule.headers["location"] == (
        f"/task/{task['id']}?date_error=worker_unavailable&worker=helper2"
    )

    conn = connect()
    c = conn.cursor()
    c.execute(
        "DELETE FROM worker_unavailability WHERE id=?",
        (unavailable_period_id,),
    )
    conn.commit()
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
    worker_html = worker_response.body.decode("utf-8")
    assert "Client 2" in worker_html
    assert "Недельный планировщик" not in worker_html

    outsider_response = await crm.calendar_page(
        make_asgi_request("outsider_worker"),
        month="2026-05",
    )
    assert outsider_response.status_code == 200
    assert "Client 2" not in outsider_response.body.decode("utf-8")

    conn = connect()
    c = conn.cursor()
    c.execute("""
    UPDATE users
    SET daily_capacity=3
    WHERE company_id=2
      AND username IN ('worker2', 'helper2')
    """)
    conn.commit()
    conn.close()


async def assert_schedule_conflicts():
    today = datetime.now().date()
    unavailable_date = today + timedelta(days=3)
    overload_date = today + timedelta(days=4)
    unassigned_date = today + timedelta(days=5)
    conn = connect()
    c = conn.cursor()
    workers = c.execute("""
    SELECT id, username
    FROM users
    WHERE company_id=2
      AND username IN ('worker2', 'helper2', 'free2')
    """).fetchall()
    worker_ids = {
        row["username"]: row["id"]
        for row in workers
    }
    c.execute("""
    UPDATE users
    SET daily_capacity=1
    WHERE company_id=2
      AND username IN ('worker2', 'helper2')
    """)
    c.execute("""
    UPDATE users
    SET daily_capacity=3
    WHERE company_id=2 AND username='free2'
    """)
    c.execute("""
    INSERT INTO worker_unavailability (
        company_id, worker_id, date_from, date_to,
        reason, created_by, created_at
    )
    VALUES (2, ?, ?, ?, 'Отпуск центра конфликтов', 'owner2', ?)
    """, (
        worker_ids["helper2"],
        unavailable_date.strftime("%Y-%m-%d"),
        unavailable_date.strftime("%Y-%m-%d"),
        datetime.now().strftime("%Y-%m-%d %H:%M"),
    ))
    absence_id = c.lastrowid
    conflict_task_ids = []

    for client, task_date, worker_name in (
        (
            "Conflict unavailable",
            unavailable_date,
            "helper2",
        ),
        (
            "Conflict overload one",
            overload_date,
            "worker2",
        ),
        (
            "Conflict overload two",
            overload_date,
            "worker2",
        ),
    ):
        c.execute("""
        INSERT INTO tasks (
            company_id, client, description, task_date,
            worker, workers, status, archived, created_at
        )
        VALUES (2, ?, 'Schedule conflict smoke', ?, ?, ?, 'Новая', 0, ?)
        """, (
            client,
            task_date.strftime("%Y-%m-%d"),
            worker_name,
            worker_name,
            datetime.now().strftime("%Y-%m-%d %H:%M"),
        ))
        conflict_task_ids.append(c.lastrowid)

    c.execute("""
    INSERT INTO tasks (
        company_id, client, description, task_date,
        worker, workers, status, archived, created_at
    )
    VALUES (2, 'Conflict unassigned', 'No team', ?, '', '', 'Новая', 0, ?)
    """, (
        unassigned_date.strftime("%Y-%m-%d"),
        datetime.now().strftime("%Y-%m-%d %H:%M"),
    ))
    conflict_task_ids.append(c.lastrowid)
    c.execute("""
    INSERT INTO tasks (
        company_id, client, description, task_date,
        worker, workers, status, archived, created_at
    )
    VALUES (1, 'Outsider conflict', 'Other company', ?,
            'outsider_worker', 'outsider_worker', 'Новая', 0, ?)
    """, (
        unavailable_date.strftime("%Y-%m-%d"),
        datetime.now().strftime("%Y-%m-%d %H:%M"),
    ))
    outsider_task_id = c.lastrowid
    conn.commit()
    conn.close()

    conflicts, summary = crm.get_company_schedule_conflicts(
        2,
        today.strftime("%Y-%m-%d"),
        (today + timedelta(days=30)).strftime("%Y-%m-%d"),
    )
    created_conflicts = [
        conflict
        for conflict in conflicts
        if conflict["task_id"] in conflict_task_ids
    ]
    assert len(created_conflicts) == 3
    assert summary["total"] >= 3
    assert summary["critical"] >= 2
    assert summary["warning"] >= 1
    assert summary["unavailable"] >= 1
    assert summary["overload"] >= 1
    assert summary["unassigned"] >= 1
    unavailable_conflict = next(
        conflict
        for conflict in created_conflicts
        if conflict["task"]["client"] == "Conflict unavailable"
    )
    assert unavailable_conflict["severity"] == "critical"
    assert unavailable_conflict["recommendations"]
    assert any(
        issue["type"] == "unavailable"
        for issue in unavailable_conflict["issues"]
    )
    assert all(
        recommendation["date"] != unavailable_date.strftime("%Y-%m-%d")
        or recommendation["worker_names"] != ["helper2"]
        for recommendation in unavailable_conflict["recommendations"]
    )

    page = await crm.calendar_conflicts_page(
        make_asgi_request(
            "owner2",
            "/calendar/conflicts",
        ),
        days=30,
    )
    assert page.status_code == 200
    page_html = page.body.decode("utf-8")
    assert "Центр конфликтов расписания" in page_html
    assert "Conflict unavailable" in page_html
    assert "Conflict overload two" in page_html
    assert "Conflict unassigned" in page_html
    assert "Отпуск центра конфликтов" in page_html
    assert "Сохранить команду" in page_html
    assert "Сохранить дату" in page_html
    assert "Лучший вариант" in page_html
    assert "/calendar/conflicts/" in page_html

    filtered_page = await crm.calendar_conflicts_page(
        make_asgi_request(
            "owner2",
            "/calendar/conflicts",
        ),
        days=30,
        conflict_type="unavailable",
    )
    assert all(
        any(
            issue["type"] == "unavailable"
            for issue in conflict["issues"]
        )
        for conflict in filtered_page.context["conflicts"]
    )

    api_result = crm.api_calendar_conflicts(
        make_request("owner2"),
        days=30,
    )
    assert api_result["ok"] is True
    assert api_result["company_id"] == 2
    assert any(
        item["task_id"] == unavailable_conflict["task_id"]
        for item in api_result["items"]
    )
    assert all(
        item["task_id"] != outsider_task_id
        for item in api_result["items"]
    )

    worker_api = crm.api_calendar_conflicts(
        make_request("helper2"),
        days=30,
    )
    assert worker_api.status_code == 403
    anonymous_api = crm.api_calendar_conflicts(
        make_request(),
        days=30,
    )
    assert anonymous_api.status_code == 401

    recommendation = unavailable_conflict["recommendations"][0]
    original_send_message_to_chat = crm.send_message_to_chat
    crm.send_message_to_chat = lambda chat_id, text: True

    try:
        resolved = await crm.resolve_calendar_conflict(
            make_form_request(
                "owner2",
                (
                    "/calendar/conflicts/"
                    f"{unavailable_conflict['task_id']}/resolve"
                ),
                {
                    "new_date": recommendation["date"],
                    "workers_csv": ",".join(
                        recommendation["worker_names"]
                    ),
                    "expected_date": unavailable_conflict["task_date"],
                    "expected_workers": unavailable_conflict["workers_csv"],
                    "return_days": "30",
                },
            ),
            unavailable_conflict["task_id"],
        )
    finally:
        crm.send_message_to_chat = original_send_message_to_chat

    assert resolved.status_code == 302
    assert resolved.headers["location"] == (
        "/calendar/conflicts?days=30&resolved=1"
        f"&task_id={unavailable_conflict['task_id']}"
    )
    conn = connect()
    c = conn.cursor()
    resolved_task = c.execute("""
    SELECT task_date, worker, workers
    FROM tasks
    WHERE id=? AND company_id=2
    """, (unavailable_conflict["task_id"],)).fetchone()
    resolution_activity = c.execute("""
    SELECT action, details
    FROM task_activity
    WHERE task_id=?
      AND action='Конфликт расписания устранён'
    ORDER BY id DESC
    LIMIT 1
    """, (unavailable_conflict["task_id"],)).fetchone()
    conn.close()
    assert resolved_task["task_date"] == recommendation["date"]
    assert resolved_task["workers"] == ",".join(
        recommendation["worker_names"]
    )
    assert resolution_activity is not None
    assert unavailable_conflict["task_date"] in resolution_activity["details"]
    assert recommendation["date"] in resolution_activity["details"]

    stale = await crm.resolve_calendar_conflict(
        make_form_request(
            "owner2",
            (
                "/calendar/conflicts/"
                f"{unavailable_conflict['task_id']}/resolve"
            ),
            {
                "new_date": recommendation["date"],
                "workers_csv": ",".join(recommendation["worker_names"]),
                "expected_date": unavailable_conflict["task_date"],
                "expected_workers": unavailable_conflict["workers_csv"],
                "return_days": "30",
            },
        ),
        unavailable_conflict["task_id"],
    )
    assert stale.headers["location"] == (
        "/calendar/conflicts?days=30&error=stale"
    )

    outsider_resolution = await crm.resolve_calendar_conflict(
        make_form_request(
            "owner2",
            f"/calendar/conflicts/{outsider_task_id}/resolve",
            {
                "new_date": recommendation["date"],
                "workers_csv": "free2",
                "expected_date": "",
                "expected_workers": "",
                "return_days": "30",
            },
        ),
        outsider_task_id,
    )
    assert outsider_resolution.headers["location"] == "/"

    conn = connect()
    c = conn.cursor()
    placeholders = ",".join("?" for _ in conflict_task_ids)
    c.execute(
        f"DELETE FROM task_activity WHERE task_id IN ({placeholders})",
        conflict_task_ids,
    )
    c.execute(
        f"DELETE FROM tasks WHERE id IN ({placeholders})",
        conflict_task_ids,
    )
    c.execute(
        "DELETE FROM worker_unavailability WHERE id=?",
        (absence_id,),
    )
    c.execute(
        "DELETE FROM tasks WHERE id=? AND company_id=1",
        (outsider_task_id,),
    )
    c.execute("""
    UPDATE users
    SET daily_capacity=3
    WHERE company_id=2
      AND username IN ('worker2', 'helper2', 'free2')
    """)
    conn.commit()
    conn.close()


async def assert_dispatch_board():
    today = datetime.now().date()
    board_start = today + timedelta(days=21)
    board_start -= timedelta(days=board_start.weekday())
    original_date = board_start.strftime("%Y-%m-%d")
    capacity_date = (board_start + timedelta(days=1)).strftime("%Y-%m-%d")
    unavailable_date = (
        board_start + timedelta(days=2)
    ).strftime("%Y-%m-%d")
    success_date = (board_start + timedelta(days=3)).strftime("%Y-%m-%d")
    original_calendar_settings = crm.get_company_settings(2)
    original_auto_publish = int(
        original_calendar_settings["calendar_auto_publish"] or 0
    )
    original_auto_remind = int(
        original_calendar_settings["calendar_auto_remind"] or 0
    )
    original_auto_days_ahead = int(
        original_calendar_settings["calendar_auto_days_ahead"]
        if original_calendar_settings[
            "calendar_auto_days_ahead"
        ] is not None
        else 7
    )
    original_auto_window_start = str(
        original_calendar_settings["calendar_auto_window_start"]
        or "00:00"
    )
    original_auto_window_end = str(
        original_calendar_settings["calendar_auto_window_end"]
        or "23:59"
    )
    conn = connect()
    c = conn.cursor()
    original_scheduler_status = c.execute("""
    SELECT *
    FROM calendar_plan_scheduler_status
    WHERE company_id=2
    """).fetchone()
    c.execute("""
    DELETE FROM calendar_plan_scheduler_status
    WHERE company_id=2
    """)
    c.execute("""
    DELETE FROM calendar_plan_scheduler_runs
    WHERE company_id=2
    """)
    c.execute("""
    DELETE FROM calendar_scheduler_incident_events
    WHERE company_id=2
    """)
    conn.commit()
    conn.close()
    publication_tasks = []

    for offset in range(4):
        publication_tasks.append({
            "id": 9000 + offset,
            "task_date": (
                board_start + timedelta(days=offset)
            ).strftime("%Y-%m-%d"),
            "worker": "helper2",
            "workers": "helper2",
            "time_from": f"{9 + offset:02d}:00",
            "time_to": f"{10 + offset:02d}:00",
        })

    waiting_snapshot = crm.build_day_plan_snapshot(
        [publication_tasks[1]]
    )
    accepted_snapshot = crm.build_day_plan_snapshot(
        [publication_tasks[2]]
    )
    weekly_publication = crm.build_week_publication_summary(
        week_start=board_start,
        tasks=publication_tasks,
        publications=[
            {
                "plan_date": publication_tasks[1]["task_date"],
                "plan_hash": waiting_snapshot["hash"],
                "revision": 1,
            },
            {
                "plan_date": publication_tasks[2]["task_date"],
                "plan_hash": accepted_snapshot["hash"],
                "revision": 2,
            },
            {
                "plan_date": publication_tasks[3]["task_date"],
                "plan_hash": "stale-plan",
                "revision": 1,
            },
        ],
        acknowledgements=[{
            "plan_date": publication_tasks[2]["task_date"],
            "revision": 2,
            "username": "helper2",
            "acknowledged_at": "2026-06-12 09:00",
        }],
        active_worker_names=["helper2"],
    )
    assert [
        day["display_state"]
        for day in weekly_publication["days"][:4]
    ] == ["draft", "waiting", "accepted", "changed"]
    assert weekly_publication["summary"] == {
        "active_days": 4,
        "draft_days": 1,
        "published_days": 2,
        "changed_days": 1,
        "accepted_days": 1,
        "pending_acknowledgements": 1,
        "remindable_workers": 1,
    }

    conn = connect()
    c = conn.cursor()
    helper = c.execute("""
    SELECT id, daily_capacity, telegram_chat_id
    FROM users
    WHERE company_id=2 AND username='helper2'
    """).fetchone()
    c.execute("""
    UPDATE users
    SET daily_capacity=1, telegram_chat_id='dispatch-smoke-chat'
    WHERE company_id=2 AND username='helper2'
    """)
    c.execute("""
    INSERT INTO worker_unavailability (
        company_id, worker_id, date_from, date_to,
        reason, created_by, created_at
    )
    VALUES (2, ?, ?, ?, 'Выходной диспетчера', 'owner2', ?)
    """, (
        helper["id"],
        unavailable_date,
        unavailable_date,
        datetime.now().strftime("%Y-%m-%d %H:%M"),
    ))
    absence_id = c.lastrowid
    c.execute("""
    INSERT INTO tasks (
        company_id, client, description, task_date,
        worker, workers, status, archived, created_at,
        time_from, time_to
    )
    VALUES (2, 'Dispatch mover', 'Dispatch smoke', ?,
            'helper2', 'helper2', 'Новая', 0, ?, '09:00', '10:00')
    """, (
        original_date,
        datetime.now().strftime("%Y-%m-%d %H:%M"),
    ))
    mover_id = c.lastrowid
    c.execute("""
    INSERT INTO tasks (
        company_id, client, description, task_date,
        worker, workers, status, archived, created_at,
        time_from, time_to
    )
    VALUES (2, 'Dispatch blocker', 'Dispatch smoke', ?,
            'helper2', 'helper2', 'Новая', 0, ?, '10:00', '11:00')
    """, (
        capacity_date,
        datetime.now().strftime("%Y-%m-%d %H:%M"),
    ))
    blocker_id = c.lastrowid
    c.execute("""
    INSERT INTO tasks (
        company_id, client, description, task_date,
        worker, workers, status, archived, created_at
    )
    VALUES (2, 'Dispatch backlog', 'Dispatch smoke', '',
            '', '', 'Новая', 0, ?)
    """, (datetime.now().strftime("%Y-%m-%d %H:%M"),))
    backlog_id = c.lastrowid
    c.execute("""
    INSERT INTO tasks (
        company_id, client, description, task_date,
        worker, workers, status, archived, created_at
    )
    VALUES (1, 'Dispatch outsider', 'Dispatch smoke', ?,
            'outsider_worker', 'outsider_worker', 'Новая', 0, ?)
    """, (
        original_date,
        datetime.now().strftime("%Y-%m-%d %H:%M"),
    ))
    outsider_id = c.lastrowid
    publication_tasks = c.execute("""
    SELECT *
    FROM tasks
    WHERE company_id=2
      AND archived=0
      AND status!='Отменено'
      AND task_date LIKE ?
    ORDER BY id
    """, (f"{original_date}%",)).fetchall()
    publication_snapshot = crm.build_day_plan_snapshot(publication_tasks)
    published_at = datetime.now().strftime("%Y-%m-%d %H:%M")
    c.execute("""
    INSERT INTO calendar_day_publications (
        company_id, plan_date, plan_hash, task_count, worker_count,
        published_by, published_at, revision
    )
    VALUES (2, ?, ?, ?, ?, 'owner2', ?, 1)
    """, (
        original_date,
        publication_snapshot["hash"],
        publication_snapshot["task_count"],
        publication_snapshot["worker_count"],
        published_at,
    ))

    for worker_name in publication_snapshot["workers"]:
        c.execute("""
        INSERT INTO calendar_day_acknowledgements (
            company_id, plan_date, revision, username, acknowledged_at
        )
        VALUES (2, ?, 1, ?, ?)
        """, (original_date, worker_name, published_at))

    conn.commit()
    conn.close()

    page = await crm.calendar_dispatch_page(
        make_asgi_request(
            "owner2",
            "/calendar/dispatch",
        ),
        week_start=original_date,
    )
    assert page.status_code == 200
    page_html = page.body.decode("utf-8")
    assert "Диспетчерская доска" in page_html
    assert "Dispatch mover" in page_html
    assert "Dispatch blocker" in page_html
    assert "Dispatch backlog" in page_html
    assert "Dispatch outsider" not in page_html
    assert 'draggable="true"' in page_html
    assert "/api/calendar/dispatch/move" in page_html
    assert "Новая дата для заявки" in page_html
    assert len(page.context["board_columns"]) == 8
    assert page.context["summary"]["tasks"] == 3
    assert page.context["summary"]["backlog"] == 1
    assert "Планы команды на неделю" in page_html
    assert "План принят" in page_html
    assert page.context["week_publication"]["summary"][
        "published_days"
    ] == 1
    assert page.context["week_publication"]["summary"][
        "accepted_days"
    ] == 1
    publication_day = next(
        day
        for day in page.context["week_publication"]["days"]
        if day["date"] == original_date
    )
    assert publication_day["display_state"] == "accepted"
    assert publication_day["acknowledged_count"] == (
        publication_day["worker_count"]
    )
    assert publication_day["url"] == (
        f"/calendar/day?date={original_date}"
    )
    assert page.context["week_publication"]["summary"][
        "publishable_days"
    ] == 1
    assert 'id="publish-week-plans"' in page_html
    assert 'id="remind-week-plans"' in page_html
    assert "/api/calendar/dispatch/week-plans" in page_html
    assert "Автоматизация планов" in page_html
    assert 'id="save-calendar-automation"' in page_html
    assert 'id="run-calendar-automation"' in page_html
    assert "/api/calendar/dispatch/automation-run" in page_html
    assert page.context["calendar_auto_publish"] is False
    assert page.context["calendar_auto_remind"] is False
    assert page.context["calendar_auto_days_ahead"] == (
        original_auto_days_ahead
    )
    assert 'id="calendar-auto-days-ahead"' in page_html
    assert 'id="calendar-auto-window-start"' in page_html
    assert 'id="calendar-auto-window-end"' in page_html
    assert page.context["calendar_scheduler_status"]["tone"] == "disabled"
    assert page.context["calendar_scheduler_runs"] == []
    assert page.context["calendar_scheduler_run_summary"][
        "total_runs"
    ] == 0
    assert page.context["calendar_scheduler_incident"][
        "active"
    ] is False
    assert page.context["calendar_scheduler_incident_events"] == []
    assert "Автоматизация выключена" in page_html
    backlog_column = page.context["board_columns"][0]
    assert backlog_column["is_backlog"] is True
    assert any(
        item["task"]["id"] == backlog_id
        for item in backlog_column["tasks"]
    )

    filtered_page = await crm.calendar_dispatch_page(
        make_asgi_request(
            "owner2",
            "/calendar/dispatch",
        ),
        week_start=original_date,
        worker="helper2",
    )
    assert filtered_page.context["selected_worker"] == "helper2"
    assert filtered_page.context["summary"]["tasks"] == 2
    assert "Dispatch backlog" not in filtered_page.body.decode("utf-8")

    anonymous_week_action = (
        await crm.api_calendar_dispatch_week_plans(
            make_json_request(
                None,
                "/api/calendar/dispatch/week-plans",
                {
                    "action": "publish_ready",
                    "week_start": original_date,
                },
            )
        )
    )
    assert anonymous_week_action.status_code == 401
    worker_week_action = (
        await crm.api_calendar_dispatch_week_plans(
            make_json_request(
                "helper2",
                "/api/calendar/dispatch/week-plans",
                {
                    "action": "publish_ready",
                    "week_start": original_date,
                },
            )
        )
    )
    assert worker_week_action.status_code == 403
    invalid_week_action = (
        await crm.api_calendar_dispatch_week_plans(
            make_json_request(
                "owner2",
                "/api/calendar/dispatch/week-plans",
                {
                    "action": "remove_all",
                    "week_start": original_date,
                },
            )
        )
    )
    assert invalid_week_action.status_code == 400
    invalid_week_date = (
        await crm.api_calendar_dispatch_week_plans(
            make_json_request(
                "owner2",
                "/api/calendar/dispatch/week-plans",
                {
                    "action": "publish_ready",
                    "week_start": "bad-date",
                },
            )
        )
    )
    assert invalid_week_date.status_code == 400
    anonymous_automation_settings = (
        await crm.api_calendar_dispatch_automation_settings(
            make_json_request(
                None,
                "/api/calendar/dispatch/automation-settings",
                {
                    "auto_publish": True,
                    "auto_remind": True,
                },
            )
        )
    )
    assert anonymous_automation_settings.status_code == 401
    manager_automation_settings = (
        await crm.api_calendar_dispatch_automation_settings(
            make_json_request(
                "manager1",
                "/api/calendar/dispatch/automation-settings",
                {
                    "auto_publish": True,
                    "auto_remind": True,
                },
            )
        )
    )
    assert manager_automation_settings.status_code == 403
    anonymous_automation_run = (
        await crm.api_calendar_dispatch_automation_run(
            make_json_request(
                None,
                "/api/calendar/dispatch/automation-run",
                {},
            )
        )
    )
    assert anonymous_automation_run.status_code == 401
    manager_automation_run = (
        await crm.api_calendar_dispatch_automation_run(
            make_json_request(
                "manager1",
                "/api/calendar/dispatch/automation-run",
                {},
            )
        )
    )
    assert manager_automation_run.status_code == 403
    anonymous_incident_ack = (
        await crm.api_calendar_dispatch_incident_acknowledge(
            make_json_request(
                None,
                "/api/calendar/dispatch/incident/acknowledge",
                {},
            )
        )
    )
    assert anonymous_incident_ack.status_code == 401
    manager_incident_ack = (
        await crm.api_calendar_dispatch_incident_acknowledge(
            make_json_request(
                "manager1",
                "/api/calendar/dispatch/incident/acknowledge",
                {},
            )
        )
    )
    assert manager_incident_ack.status_code == 403
    disabled_automation_run = (
        await crm.api_calendar_dispatch_automation_run(
            make_json_request(
                "owner2",
                "/api/calendar/dispatch/automation-run",
                {},
            )
        )
    )
    assert disabled_automation_run.status_code == 409
    assert json.loads(disabled_automation_run.body)[
        "error"
    ] == "automation_disabled"
    invalid_days_settings = (
        await crm.api_calendar_dispatch_automation_settings(
            make_json_request(
                "owner2",
                "/api/calendar/dispatch/automation-settings",
                {
                    "auto_publish": True,
                    "auto_remind": True,
                    "days_ahead": 15,
                    "window_start": "08:00",
                    "window_end": "20:00",
                },
            )
        )
    )
    assert invalid_days_settings.status_code == 400
    assert json.loads(invalid_days_settings.body)[
        "error"
    ] == "invalid_days_ahead"
    invalid_window_settings = (
        await crm.api_calendar_dispatch_automation_settings(
            make_json_request(
                "owner2",
                "/api/calendar/dispatch/automation-settings",
                {
                    "auto_publish": True,
                    "auto_remind": True,
                    "days_ahead": 1,
                    "window_start": "25:00",
                    "window_end": "20:00",
                },
            )
        )
    )
    assert invalid_window_settings.status_code == 400
    assert json.loads(invalid_window_settings.body)[
        "error"
    ] == "invalid_time_window"
    saved_automation_settings = (
        await crm.api_calendar_dispatch_automation_settings(
            make_json_request(
                "owner2",
                "/api/calendar/dispatch/automation-settings",
                {
                    "auto_publish": True,
                    "auto_remind": True,
                    "days_ahead": 1,
                    "window_start": "00:00",
                    "window_end": "23:59",
                },
            )
        )
    )
    assert saved_automation_settings == {
        "ok": True,
        "auto_publish": True,
        "auto_remind": True,
        "days_ahead": 1,
        "window_start": "00:00",
        "window_end": "23:59",
        "message": "Настройки автоматизации сохранены.",
    }
    assert crm.calendar_automation_time_allowed(
        datetime(2026, 6, 12, 23, 30),
        "22:00",
        "06:00",
    ) is True
    assert crm.calendar_automation_time_allowed(
        datetime(2026, 6, 12, 12, 0),
        "22:00",
        "06:00",
    ) is False
    original_calendar_scheduler = crm.run_calendar_plan_scheduler
    manual_run_arguments = {}

    async def fake_manual_calendar_scheduler(
        company_id,
        now_dt=None,
        actor_username="",
        source="scheduler",
    ):
        manual_run_arguments.update({
            "company_id": company_id,
            "actor_username": actor_username,
            "source": source,
        })
        return {
            "company_id": company_id,
            "enabled": True,
            "source": source,
            "publish": None,
            "remind": None,
            "changed_days": 2,
            "notifications_sent": 3,
            "error": "",
        }

    crm.run_calendar_plan_scheduler = fake_manual_calendar_scheduler

    try:
        manual_automation_run = (
            await crm.api_calendar_dispatch_automation_run(
                make_json_request(
                    "owner2",
                    "/api/calendar/dispatch/automation-run",
                    {},
                )
            )
        )
    finally:
        crm.run_calendar_plan_scheduler = original_calendar_scheduler

    assert manual_automation_run["ok"] is True
    assert manual_automation_run["message"] == (
        "Автоматизация выполнена. "
        "Изменено дней: 2. Уведомлений: 3."
    )
    assert manual_run_arguments == {
        "company_id": 2,
        "actor_username": "owner2",
        "source": "manual_run",
    }
    outsider_week_action = (
        await crm.api_calendar_dispatch_week_plans(
            make_json_request(
                "manager1",
                "/api/calendar/dispatch/week-plans",
                {
                    "action": "publish_ready",
                    "week_start": original_date,
                },
            )
        )
    )
    assert outsider_week_action["summary"]["published_days"] == 0
    assert outsider_week_action["summary"]["updated_days"] == 0
    assert outsider_week_action["summary"]["notified_workers"] == 0

    original_send_message_to_chat = crm.send_message_to_chat
    week_plan_messages = []
    crm.send_message_to_chat = (
        lambda chat_id, text: week_plan_messages.append(
            (chat_id, text)
        )
    )

    try:
        week_publish = await crm.api_calendar_dispatch_week_plans(
            make_json_request(
                "owner2",
                "/api/calendar/dispatch/week-plans",
                {
                    "action": "publish_ready",
                    "week_start": original_date,
                },
            )
        )
        week_remind = await crm.api_calendar_dispatch_week_plans(
            make_json_request(
                "owner2",
                "/api/calendar/dispatch/week-plans",
                {
                    "action": "remind_pending",
                    "week_start": original_date,
                },
            )
        )
        week_remind_again = (
            await crm.api_calendar_dispatch_week_plans(
                make_json_request(
                    "owner2",
                    "/api/calendar/dispatch/week-plans",
                    {
                        "action": "remind_pending",
                        "week_start": original_date,
                    },
                )
            )
        )
    finally:
        crm.send_message_to_chat = original_send_message_to_chat

    assert week_publish["summary"] == {
        "published_days": 1,
        "updated_days": 0,
        "notified_workers": 1,
        "skipped_days": 6,
    }
    assert any(
        item["date"] == capacity_date
        and item["status"] == "published"
        for item in week_publish["items"]
    )
    assert week_remind["summary"]["affected_days"] == 1
    assert week_remind["summary"]["sent_reminders"] == 1
    assert week_remind_again["summary"]["sent_reminders"] == 0
    assert week_remind_again["summary"]["cooldown_workers"] == 1
    assert len(week_plan_messages) == 2
    assert all(
        chat_id == "dispatch-smoke-chat"
        for chat_id, _ in week_plan_messages
    )
    assert capacity_date in week_plan_messages[0][1]
    assert capacity_date in week_plan_messages[1][1]

    published_week_page = await crm.calendar_dispatch_page(
        make_asgi_request("owner2", "/calendar/dispatch"),
        week_start=original_date,
    )
    published_week_summary = published_week_page.context[
        "week_publication"
    ]["summary"]
    assert published_week_summary["published_days"] == 2
    assert published_week_summary["pending_acknowledgements"] == 1
    assert published_week_summary["remindable_workers"] == 0
    assert len(published_week_page.context["week_plan_runs"]) == 3
    assert all(
        item["source"] == "manual"
        for item in published_week_page.context["week_plan_runs"]
    )
    published_week_html = published_week_page.body.decode("utf-8")
    assert "История операций недели" in published_week_html
    assert "Публикация готовых планов" in published_week_html
    assert "Ожидает первого запуска" in published_week_html
    assert "/api/calendar/dispatch/automation-settings" in (
        published_week_html
    )
    conn = connect()
    c = conn.cursor()
    c.execute("""
    UPDATE calendar_day_ack_reminders
    SET reminded_at=?
    WHERE company_id=2
      AND plan_date=?
      AND revision=1
      AND username='helper2'
    """, (
        (datetime.now() - timedelta(
            minutes=crm.REMINDER_COOLDOWN_MINUTES + 1
        )).strftime("%Y-%m-%d %H:%M"),
        capacity_date,
    ))
    conn.commit()
    conn.close()
    scheduler_now = datetime(
        board_start.year,
        board_start.month,
        board_start.day,
        12,
        0,
    )
    scheduler_messages = []
    original_send_message_to_chat = crm.send_message_to_chat
    crm.send_message_to_chat = (
        lambda chat_id, text: scheduler_messages.append(
            (chat_id, text)
        )
    )

    conn = connect()
    c = conn.cursor()
    c.execute("""
    UPDATE company_settings
    SET calendar_auto_days_ahead=0
    WHERE company_id=2
    """)
    conn.commit()
    conn.close()
    horizon_today_result = await crm.run_calendar_plan_scheduler(
        2,
        now_dt=scheduler_now,
        actor_username="owner2",
        source="manual_run",
    )
    assert horizon_today_result["policy"]["days_ahead"] == 0
    assert horizon_today_result["changed_days"] == 0
    assert horizon_today_result["notifications_sent"] == 0
    assert any(
        item["date"] == capacity_date
        and item["reason"] == "Вне горизонта автоматизации"
        for item in horizon_today_result["remind"]["items"]
    )
    conn = connect()
    c = conn.cursor()
    c.execute("""
    UPDATE company_settings
    SET calendar_auto_days_ahead=1
    WHERE company_id=2
    """)
    conn.commit()
    conn.close()

    try:
        scheduler_result = await crm.run_calendar_plan_scheduler(
            2,
            now_dt=scheduler_now,
            actor_username="owner2",
            source="manual_run",
        )
    finally:
        crm.send_message_to_chat = original_send_message_to_chat

    assert scheduler_result["enabled"] is True
    assert scheduler_result["source"] == "manual_run"
    assert scheduler_result["range_start"] == original_date
    assert scheduler_result["range_end"] == capacity_date
    assert len(scheduler_result["publish"]["weeks"]) == 1
    assert scheduler_result["publish"]["source"] == "manual_run"
    assert scheduler_result["remind"]["source"] == "manual_run"
    assert scheduler_result["changed_days"] == 1
    assert scheduler_result["notifications_sent"] == 1
    assert scheduler_result["remind"]["summary"][
        "automatic_skips"
    ] == 0
    assert len(scheduler_messages) == 1

    conn = connect()
    c = conn.cursor()
    scheduler_reminder = c.execute("""
    SELECT source
    FROM calendar_day_ack_reminders
    WHERE company_id=2
      AND plan_date=?
      AND revision=1
      AND username='helper2'
    ORDER BY id DESC
    LIMIT 1
    """, (capacity_date,)).fetchone()
    c.execute("""
    UPDATE calendar_day_ack_reminders
    SET reminded_at=?
    WHERE company_id=2
      AND plan_date=?
      AND revision=1
      AND username='helper2'
    """, (
        (datetime.now() - timedelta(
            minutes=crm.REMINDER_COOLDOWN_MINUTES + 1
        )).strftime("%Y-%m-%d %H:%M"),
        capacity_date,
    ))
    conn.commit()
    conn.close()
    assert scheduler_reminder["source"] == "manual_run"

    scheduler_page = await crm.calendar_dispatch_page(
        make_asgi_request("owner2", "/calendar/dispatch"),
        week_start=original_date,
    )
    assert scheduler_page.context["calendar_scheduler_status"][
        "tone"
    ] == "healthy"
    assert "вручную, owner2" in scheduler_page.context[
        "calendar_scheduler_status"
    ]["message"]
    assert scheduler_page.context["week_plan_runs"][0][
        "source_label"
    ] == "Запуск владельцем"
    assert len(scheduler_page.context["calendar_scheduler_runs"]) == 2
    assert scheduler_page.context["calendar_scheduler_runs"][0][
        "source_label"
    ] == "Вручную"
    assert scheduler_page.context["calendar_scheduler_run_summary"][
        "done_runs"
    ] == 2
    assert "Журнал автоматизации" in (
        scheduler_page.body.decode("utf-8")
    )
    assert "Автоматизация работает" in (
        scheduler_page.body.decode("utf-8")
    )

    repeated_scheduler = await crm.run_calendar_plan_scheduler(
        2,
        now_dt=scheduler_now,
    )
    assert repeated_scheduler["changed_days"] == 0
    assert repeated_scheduler["notifications_sent"] == 0
    assert repeated_scheduler["remind"]["summary"][
        "automatic_skips"
    ] == 1
    assert repeated_scheduler["publish"]["operation_run_id"] == 0
    assert repeated_scheduler["remind"]["operation_run_id"] == 0

    conn = connect()
    c = conn.cursor()
    c.execute("""
    UPDATE calendar_plan_scheduler_status
    SET last_status='running',
        last_started_at=?
    WHERE company_id=2
    """, (datetime.now().strftime("%Y-%m-%d %H:%M"),))
    conn.commit()
    conn.close()
    locked_scheduler = await crm.run_calendar_plan_scheduler(
        2,
        now_dt=scheduler_now,
    )
    assert locked_scheduler["error"] == "scheduler_already_running"
    assert locked_scheduler["publish"] is None
    assert locked_scheduler["remind"] is None

    conn = connect()
    c = conn.cursor()
    c.execute("""
    UPDATE calendar_plan_scheduler_status
    SET last_started_at=?
    WHERE company_id=2
    """, (
        (datetime.now() - timedelta(minutes=31)).strftime(
            "%Y-%m-%d %H:%M"
        ),
    ))
    conn.commit()
    conn.close()
    recovered_scheduler = await crm.run_calendar_plan_scheduler(
        2,
        now_dt=scheduler_now,
    )
    assert recovered_scheduler["error"] == ""
    assert recovered_scheduler["changed_days"] == 0
    assert recovered_scheduler["notifications_sent"] == 0
    assert recovered_scheduler["incident_alerts_sent"] == 1
    assert recovered_scheduler["recovery_alerts_sent"] == 1
    conn = connect()
    c = conn.cursor()
    c.execute("""
    UPDATE company_settings
    SET calendar_auto_window_start='13:00',
        calendar_auto_window_end='14:00'
    WHERE company_id=2
    """)
    conn.commit()
    conn.close()
    outside_window_scheduler = (
        await crm.run_calendar_plan_scheduler(
            2,
            now_dt=scheduler_now,
        )
    )
    assert outside_window_scheduler["error"] == ""
    assert outside_window_scheduler["skipped"] is True
    assert outside_window_scheduler[
        "skip_reason"
    ] == "outside_time_window"
    waiting_page = await crm.calendar_dispatch_page(
        make_asgi_request("owner2", "/calendar/dispatch"),
        week_start=original_date,
    )
    assert waiting_page.context["calendar_scheduler_status"][
        "tone"
    ] == "waiting"
    assert waiting_page.context["calendar_scheduler_runs"][0][
        "status"
    ] == "skipped"
    assert waiting_page.context["calendar_scheduler_runs"][0][
        "reason"
    ] == "Вне рабочего окна"
    assert waiting_page.context["calendar_scheduler_run_summary"][
        "skipped_runs"
    ] == 1
    assert "Ожидает рабочего окна" in (
        waiting_page.body.decode("utf-8")
    )
    conn = connect()
    c = conn.cursor()
    c.execute("""
    UPDATE company_settings
    SET calendar_auto_window_start='00:00',
        calendar_auto_window_end='23:59'
    WHERE company_id=2
    """)
    conn.commit()
    conn.close()
    final_scheduler = await crm.run_calendar_plan_scheduler(
        2,
        now_dt=scheduler_now,
    )
    assert final_scheduler["error"] == ""
    assert final_scheduler["skipped"] is False
    stale_run_at = (
        datetime.now() - timedelta(hours=7)
    ).strftime("%Y-%m-%d %H:%M")
    conn = connect()
    c = conn.cursor()
    c.execute("""
    UPDATE calendar_plan_scheduler_runs
    SET started_at=?,
        completed_at=?
    WHERE company_id=2
      AND source='scheduler'
    """, (
        stale_run_at,
        stale_run_at,
    ))
    conn.commit()
    conn.close()
    stale_watchdog = crm.monitor_calendar_plan_schedulers(
        now_dt=datetime.now(),
        company_id=2,
    )
    company_watchdog = next(
        item
        for item in stale_watchdog["items"]
        if item["company_id"] == 2
    )
    assert company_watchdog["status"] == "stale"
    assert company_watchdog["alerted"] == 1
    repeated_watchdog = crm.monitor_calendar_plan_schedulers(
        now_dt=datetime.now(),
        company_id=2,
    )
    repeated_company_watchdog = next(
        item
        for item in repeated_watchdog["items"]
        if item["company_id"] == 2
    )
    assert repeated_company_watchdog["status"] == "stale"
    assert repeated_company_watchdog["alerted"] == 0
    stale_page = await crm.calendar_dispatch_page(
        make_asgi_request("owner2", "/calendar/dispatch"),
        week_start=original_date,
    )
    stale_page_html = stale_page.body.decode("utf-8")
    assert stale_page.context["calendar_scheduler_incident"][
        "type"
    ] == "stale"
    assert 'id="acknowledge-calendar-incident"' in stale_page_html
    assert "Cron не запускался" in stale_page_html
    acknowledged_incident = (
        await crm.api_calendar_dispatch_incident_acknowledge(
            make_json_request(
                "owner2",
                "/api/calendar/dispatch/incident/acknowledge",
                {},
            )
        )
    )
    assert acknowledged_incident["ok"] is True
    repeated_acknowledgement = (
        await crm.api_calendar_dispatch_incident_acknowledge(
            make_json_request(
                "owner2",
                "/api/calendar/dispatch/incident/acknowledge",
                {},
            )
        )
    )
    assert repeated_acknowledgement.status_code == 409
    assert json.loads(repeated_acknowledgement.body)[
        "error"
    ] == "already_acknowledged"
    acknowledged_page = await crm.calendar_dispatch_page(
        make_asgi_request("owner2", "/calendar/dispatch"),
        week_start=original_date,
    )
    assert "Принят в работу" in (
        acknowledged_page.body.decode("utf-8")
    )
    assert "Ответственный:" in (
        acknowledged_page.body.decode("utf-8")
    )
    assert acknowledged_page.context[
        "calendar_scheduler_incident"
    ]["assigned_to"] == "owner2"
    stale_recovery = await crm.run_calendar_plan_scheduler(
        2,
        now_dt=scheduler_now,
    )
    assert stale_recovery["error"] == ""
    assert stale_recovery["recovery_alerts_sent"] == 1

    original_week_plan_api = crm.api_calendar_dispatch_week_plans

    async def failing_week_plan_api(request):
        raise RuntimeError("calendar smoke failure")

    crm.api_calendar_dispatch_week_plans = failing_week_plan_api

    try:
        failed_scheduler = await crm.run_calendar_plan_scheduler(
            2,
            now_dt=scheduler_now,
        )
        repeated_failed_scheduler = (
            await crm.run_calendar_plan_scheduler(
                2,
                now_dt=scheduler_now,
            )
        )
    finally:
        crm.api_calendar_dispatch_week_plans = original_week_plan_api

    assert failed_scheduler["error"] == "calendar smoke failure"
    assert failed_scheduler["incident_alerts_sent"] == 1
    assert repeated_failed_scheduler["error"] == "calendar smoke failure"
    assert repeated_failed_scheduler["incident_alerts_sent"] == 0
    scheduler_recovery = await crm.run_calendar_plan_scheduler(
        2,
        now_dt=scheduler_now,
    )
    assert scheduler_recovery["error"] == ""
    assert scheduler_recovery["recovery_alerts_sent"] == 1
    old_cron_secret = os.environ.get("AUTOMATION_CRON_SECRET")
    os.environ["AUTOMATION_CRON_SECRET"] = "calendar-cron-secret"

    async def fake_calendar_scheduler_for_all_companies(now_dt=None):
        return {
            "companies": 1,
            "changed_days": 0,
            "notifications_sent": 0,
            "errors": 0,
            "results": [],
        }

    original_scheduler_for_all = (
        crm.run_calendar_plan_scheduler_for_all_companies
    )
    original_calendar_watchdog = (
        crm.monitor_calendar_plan_schedulers
    )
    crm.run_calendar_plan_scheduler_for_all_companies = (
        fake_calendar_scheduler_for_all_companies
    )
    crm.monitor_calendar_plan_schedulers = (
        lambda: {
            "companies": 1,
            "healthy": 1,
            "waiting": 0,
            "stale": 0,
            "alerts_sent": 0,
            "stale_after_hours": 6,
            "items": [],
        }
    )

    try:
        forbidden_calendar_cron = (
            await crm.run_calendar_plan_scheduler_cron(
                make_public_asgi_request(
                    "/automation/cron/calendar-plans"
                )
            )
        )
        assert forbidden_calendar_cron.status_code == 403
        calendar_cron = await crm.run_calendar_plan_scheduler_cron(
            make_public_asgi_request(
                "/automation/cron/calendar-plans",
                headers=[
                    (
                        b"x-automation-secret",
                        b"calendar-cron-secret",
                    ),
                ],
            )
        )
        forbidden_calendar_watchdog = (
            await crm.run_calendar_plan_scheduler_watchdog(
                make_public_asgi_request(
                    "/automation/cron/calendar-plans/watchdog"
                )
            )
        )
        assert forbidden_calendar_watchdog.status_code == 403
        calendar_watchdog = (
            await crm.run_calendar_plan_scheduler_watchdog(
                make_public_asgi_request(
                    "/automation/cron/calendar-plans/watchdog",
                    headers=[
                        (
                            b"x-automation-secret",
                            b"calendar-cron-secret",
                        ),
                    ],
                )
            )
        )
    finally:
        crm.run_calendar_plan_scheduler_for_all_companies = (
            original_scheduler_for_all
        )
        crm.monitor_calendar_plan_schedulers = (
            original_calendar_watchdog
        )
        if old_cron_secret is None:
            os.environ.pop("AUTOMATION_CRON_SECRET", None)
        else:
            os.environ["AUTOMATION_CRON_SECRET"] = old_cron_secret

    assert calendar_cron["ok"] is True
    assert calendar_cron["summary"]["companies"] >= 1
    assert calendar_watchdog["ok"] is True
    assert calendar_watchdog["summary"]["healthy"] == 1
    conn = connect()
    c = conn.cursor()
    operation_runs = c.execute("""
    SELECT source, action
    FROM calendar_plan_operation_runs
    WHERE company_id=2
      AND week_start=?
    ORDER BY id
    """, (original_date,)).fetchall()
    scheduler_status = c.execute("""
    SELECT *
    FROM calendar_plan_scheduler_status
    WHERE company_id=2
    """).fetchone()
    scheduler_runs = c.execute("""
    SELECT status, source, reason
    FROM calendar_plan_scheduler_runs
    WHERE company_id=2
    ORDER BY id
    """).fetchall()
    scheduler_alerts = c.execute("""
    SELECT title
    FROM notifications
    WHERE company_id=2
      AND username='owner2'
      AND link='/calendar/dispatch'
      AND title IN (
          'Планировщик календаря не отвечает',
          'Планировщик календаря давно не запускался',
          'Ошибка автоматизации календаря',
          'Автоматизация календаря восстановлена'
      )
    ORDER BY id
    """).fetchall()
    incident_events = c.execute("""
    SELECT incident_type, event_type, actor_username
    FROM calendar_scheduler_incident_events
    WHERE company_id=2
    ORDER BY id
    """).fetchall()
    conn.close()
    assert sum(
        1 for row in operation_runs if row["source"] == "manual"
    ) == 3
    assert sum(
        1 for row in operation_runs if row["source"] == "scheduler"
    ) == 0
    assert sum(
        1 for row in operation_runs if row["source"] == "manual_run"
    ) == 1
    assert scheduler_status["last_status"] == "done"
    assert scheduler_status["last_error"] == ""
    assert scheduler_status["last_changed_days"] == 0
    assert scheduler_status["last_notifications_sent"] == 0
    assert scheduler_status["last_source"] == "scheduler"
    assert scheduler_status["last_triggered_by"] == "owner2"
    assert scheduler_status["active_incident"] == ""
    assert scheduler_status["last_alerted_at"]
    assert scheduler_status["last_recovered_at"]
    assert len(scheduler_runs) == 11
    assert sum(
        1 for row in scheduler_runs if row["status"] == "done"
    ) == 7
    assert sum(
        1 for row in scheduler_runs if row["status"] == "error"
    ) == 2
    assert sum(
        1 for row in scheduler_runs if row["status"] == "locked"
    ) == 1
    assert sum(
        1 for row in scheduler_runs if row["status"] == "skipped"
    ) == 1
    assert sum(
        1 for row in scheduler_runs
        if row["source"] == "manual_run"
    ) == 2
    assert any(
        row["reason"] == "Другой запуск уже выполняется"
        for row in scheduler_runs
    )
    assert [
        row["title"] for row in scheduler_alerts
    ] == [
        "Планировщик календаря не отвечает",
        "Автоматизация календаря восстановлена",
        "Планировщик календаря давно не запускался",
        "Автоматизация календаря восстановлена",
        "Ошибка автоматизации календаря",
        "Автоматизация календаря восстановлена",
    ]
    assert [
        (row["incident_type"], row["event_type"])
        for row in incident_events
    ] == [
        ("stuck", "opened"),
        ("stuck", "recovered"),
        ("stale", "opened"),
        ("stale", "acknowledged"),
        ("stale", "recovered"),
        ("error", "opened"),
        ("error", "recovered"),
    ]
    assert incident_events[3]["actor_username"] == "owner2"

    conn = connect()
    c = conn.cursor()

    for index in range(105):
        c.execute("""
        INSERT INTO calendar_plan_scheduler_runs (
            company_id, source, actor_username,
            range_start, range_end, status,
            changed_days, notifications_sent,
            started_at, completed_at
        )
        VALUES (
            2, 'scheduler', 'owner2',
            ?, ?, 'done', 0, 0, ?, ?
        )
        """, (
            original_date,
            capacity_date,
            f"2026-01-01 00:{index % 60:02d}",
            f"2026-01-01 00:{index % 60:02d}",
        ))

    conn.commit()
    conn.close()
    crm.trim_calendar_scheduler_runs(2, keep=100)
    conn = connect()
    c = conn.cursor()
    retained_scheduler_runs = c.execute("""
    SELECT COUNT(*)
    FROM calendar_plan_scheduler_runs
    WHERE company_id=2
    """).fetchone()[0]
    conn.close()
    assert retained_scheduler_runs == 100

    anonymous = await crm.api_calendar_dispatch_move(
        make_json_request(
            None,
            "/api/calendar/dispatch/move",
            {
                "task_id": mover_id,
                "target_date": success_date,
                "expected_date": original_date,
            },
        )
    )
    assert anonymous.status_code == 401
    worker_response = await crm.api_calendar_dispatch_move(
        make_json_request(
            "helper2",
            "/api/calendar/dispatch/move",
            {
                "task_id": mover_id,
                "target_date": success_date,
                "expected_date": original_date,
            },
        )
    )
    assert worker_response.status_code == 403

    unavailable = await crm.api_calendar_dispatch_move(
        make_json_request(
            "owner2",
            "/api/calendar/dispatch/move",
            {
                "task_id": mover_id,
                "target_date": unavailable_date,
                "expected_date": original_date,
            },
        )
    )
    assert unavailable.status_code == 409
    unavailable_data = json.loads(unavailable.body)
    assert unavailable_data["error"] == "worker_unavailable"
    assert unavailable_data["worker"] == "helper2"
    assert unavailable_data["reason"] == "Выходной диспетчера"
    assert unavailable_data["suggestions"]

    capacity = await crm.api_calendar_dispatch_move(
        make_json_request(
            "owner2",
            "/api/calendar/dispatch/move",
            {
                "task_id": mover_id,
                "target_date": capacity_date,
                "expected_date": original_date,
            },
        )
    )
    assert capacity.status_code == 409
    capacity_data = json.loads(capacity.body)
    assert capacity_data["error"] == "capacity_reached"
    assert capacity_data["active_count"] == 1
    assert capacity_data["daily_capacity"] == 1
    assert capacity_data["suggestions"]

    stale = await crm.api_calendar_dispatch_move(
        make_json_request(
            "owner2",
            "/api/calendar/dispatch/move",
            {
                "task_id": mover_id,
                "target_date": success_date,
                "expected_date": capacity_date,
            },
        )
    )
    assert stale.status_code == 409
    assert json.loads(stale.body)["error"] == "stale"

    outsider = await crm.api_calendar_dispatch_move(
        make_json_request(
            "owner2",
            "/api/calendar/dispatch/move",
            {
                "task_id": outsider_id,
                "target_date": success_date,
                "expected_date": original_date,
            },
        )
    )
    assert outsider.status_code == 404

    original_send_message_to_chat = crm.send_message_to_chat
    telegram_messages = []
    crm.send_message_to_chat = lambda chat_id, text: telegram_messages.append(
        (chat_id, text)
    )

    try:
        moved = await crm.api_calendar_dispatch_move(
            make_json_request(
                "owner2",
                "/api/calendar/dispatch/move",
                {
                    "task_id": mover_id,
                    "target_date": success_date,
                    "expected_date": original_date,
                },
            )
        )
        moved_to_backlog = await crm.api_calendar_dispatch_move(
            make_json_request(
                "owner2",
                "/api/calendar/dispatch/move",
                {
                    "task_id": mover_id,
                    "target_date": "",
                    "expected_date": success_date,
                },
            )
        )
    finally:
        crm.send_message_to_chat = original_send_message_to_chat

    assert moved["ok"] is True
    assert moved["changed"] is True
    assert moved["old_date"] == original_date
    assert moved["new_date"] == success_date

    assert moved_to_backlog["ok"] is True
    assert moved_to_backlog["new_date"] == ""
    assert len(telegram_messages) == 2
    assert all(
        chat_id == "dispatch-smoke-chat"
        for chat_id, _ in telegram_messages
    )
    assert success_date in telegram_messages[0][1]
    assert "не назначена" in telegram_messages[1][1]

    conn = connect()
    c = conn.cursor()
    moved_task = c.execute("""
    SELECT task_date
    FROM tasks
    WHERE id=? AND company_id=2
    """, (mover_id,)).fetchone()
    activity_rows = c.execute("""
    SELECT action, details
    FROM task_activity
    WHERE task_id=?
      AND action='Перенесено на диспетчерской доске'
    ORDER BY id
    """, (mover_id,)).fetchall()
    notification_count = c.execute("""
    SELECT COUNT(*)
    FROM notifications
    WHERE company_id=2
      AND username='helper2'
      AND title=?
    """, (f"Изменена дата заявки #{mover_id}",)).fetchone()[0]
    assert moved_task["task_date"] == ""
    assert len(activity_rows) == 2
    assert original_date in activity_rows[0]["details"]
    assert success_date in activity_rows[0]["details"]
    assert notification_count == 2

    task_ids = [mover_id, blocker_id, backlog_id, outsider_id]
    placeholders = ",".join("?" for _ in task_ids)
    c.execute(
        f"DELETE FROM task_activity WHERE task_id IN ({placeholders})",
        task_ids,
    )
    c.execute(
        "DELETE FROM notifications WHERE title=?",
        (f"Изменена дата заявки #{mover_id}",),
    )
    c.execute(
        f"DELETE FROM tasks WHERE id IN ({placeholders})",
        task_ids,
    )
    c.execute("""
    DELETE FROM calendar_day_publications
    WHERE company_id=2 AND plan_date IN (?, ?)
    """, (original_date, capacity_date))
    c.execute("""
    DELETE FROM calendar_day_acknowledgements
    WHERE company_id=2 AND plan_date IN (?, ?)
    """, (original_date, capacity_date))
    c.execute("""
    DELETE FROM calendar_day_ack_reminders
    WHERE company_id=2 AND plan_date IN (?, ?)
    """, (original_date, capacity_date))
    c.execute("""
    DELETE FROM notifications
    WHERE company_id=2
      AND (
          (
              link IN (?, ?)
              AND title IN (
                  'План дня опубликован',
                  'План дня обновлён',
                  'Подтвердите план дня'
              )
          )
          OR (
              link='/calendar/dispatch'
              AND title IN (
                  'Планировщик календаря не отвечает',
                  'Планировщик календаря давно не запускался',
                  'Ошибка автоматизации календаря',
                  'Автоматизация календаря восстановлена'
              )
          )
      )
    """, (
        f"/calendar/day?date={original_date}",
        f"/calendar/day?date={capacity_date}",
    ))
    c.execute("""
    DELETE FROM calendar_plan_operation_runs
    WHERE company_id IN (1, 2)
    """)
    c.execute("""
    DELETE FROM calendar_plan_scheduler_status
    WHERE company_id=2
    """)
    c.execute("""
    DELETE FROM calendar_plan_scheduler_runs
    WHERE company_id=2
    """)
    c.execute("""
    DELETE FROM calendar_scheduler_incident_events
    WHERE company_id=2
    """)
    if original_scheduler_status:
        c.execute("""
        INSERT INTO calendar_plan_scheduler_status (
            company_id, last_started_at, last_completed_at,
            last_status, last_error, last_changed_days,
            last_notifications_sent, last_source,
            last_triggered_by, last_result_json,
            active_incident, incident_started_at,
            incident_message, last_alerted_at,
            last_recovered_at,
            incident_acknowledged_at,
            incident_acknowledged_by,
            incident_assigned_at,
            incident_assigned_to,
            incident_assigned_by
        )
        VALUES (
            ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
            ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
        )
        """, (
            original_scheduler_status["company_id"],
            original_scheduler_status["last_started_at"],
            original_scheduler_status["last_completed_at"],
            original_scheduler_status["last_status"],
            original_scheduler_status["last_error"],
            original_scheduler_status["last_changed_days"],
            original_scheduler_status["last_notifications_sent"],
            original_scheduler_status["last_source"],
            original_scheduler_status["last_triggered_by"],
            original_scheduler_status["last_result_json"],
            original_scheduler_status["active_incident"],
            original_scheduler_status["incident_started_at"],
            original_scheduler_status["incident_message"],
            original_scheduler_status["last_alerted_at"],
            original_scheduler_status["last_recovered_at"],
            original_scheduler_status["incident_acknowledged_at"],
            original_scheduler_status["incident_acknowledged_by"],
            original_scheduler_status["incident_assigned_at"],
            original_scheduler_status["incident_assigned_to"],
            original_scheduler_status["incident_assigned_by"],
        ))
    c.execute("""
    UPDATE company_settings
    SET calendar_auto_publish=?,
        calendar_auto_remind=?,
        calendar_auto_days_ahead=?,
        calendar_auto_window_start=?,
        calendar_auto_window_end=?
    WHERE company_id=2
    """, (
        original_auto_publish,
        original_auto_remind,
        original_auto_days_ahead,
        original_auto_window_start,
        original_auto_window_end,
    ))
    c.execute(
        "DELETE FROM worker_unavailability WHERE id=?",
        (absence_id,),
    )
    c.execute("""
    UPDATE users
    SET daily_capacity=?, telegram_chat_id=?
    WHERE company_id=2 AND username='helper2'
    """, (
        helper["daily_capacity"],
        helper["telegram_chat_id"],
    ))
    conn.commit()
    conn.close()


async def assert_dispatch_planner():
    plan_start = datetime.now().date() + timedelta(days=35)
    plan_start -= timedelta(days=plan_start.weekday())
    start_value = plan_start.strftime("%Y-%m-%d")
    dated_value = (plan_start + timedelta(days=3)).strftime("%Y-%m-%d")
    past_value = (
        datetime.now().date() - timedelta(days=1)
    ).strftime("%Y-%m-%d")
    conn = connect()
    c = conn.cursor()
    original_workers = c.execute("""
    SELECT username, daily_capacity, telegram_chat_id
    FROM users
    WHERE company_id=2
      AND username IN ('worker2', 'helper2', 'free2')
    ORDER BY username
    """).fetchall()
    c.execute("""
    UPDATE users
    SET daily_capacity=1
    WHERE company_id=2
      AND username IN ('worker2', 'helper2', 'free2')
    """)
    c.execute("""
    UPDATE users
    SET telegram_chat_id='planner-helper-chat'
    WHERE company_id=2 AND username='helper2'
    """)
    created_at = datetime.now().strftime("%Y-%m-%d %H:%M")
    task_values = [
        (
            2,
            "Planner urgent",
            "Dispatch planner smoke",
            "",
            "",
            "",
            "Срочно",
            "Новая",
            created_at,
        ),
        (
            2,
            "Planner normal",
            "Dispatch planner smoke",
            "",
            "",
            "",
            "Обычный",
            "Новая",
            created_at,
        ),
        (
            2,
            "Planner fixed team",
            "Dispatch planner smoke",
            "",
            "helper2",
            "helper2",
            "Обычный",
            "Новая",
            created_at,
        ),
        (
            2,
            "Planner dated",
            "Dispatch planner smoke",
            dated_value,
            "",
            "",
            "Обычный",
            "Новая",
            created_at,
        ),
        (
            2,
            "Planner past",
            "Dispatch planner smoke",
            past_value,
            "",
            "",
            "Обычный",
            "Новая",
            created_at,
        ),
        (
            1,
            "Planner outsider",
            "Dispatch planner smoke",
            "",
            "",
            "",
            "Срочно",
            "Новая",
            created_at,
        ),
    ]
    task_ids = []

    for task_values_row in task_values:
        c.execute("""
        INSERT INTO tasks (
            company_id, client, description, task_date,
            worker, workers, priority, status, archived, created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, ?)
        """, task_values_row)
        task_ids.append(c.lastrowid)

    urgent_id, normal_id, fixed_id, dated_id, past_id, outsider_id = (
        task_ids
    )
    conn.commit()
    conn.close()

    page = await crm.calendar_dispatch_page(
        make_asgi_request("owner2", "/calendar/dispatch"),
        week_start=start_value,
    )
    page_html = page.body.decode("utf-8")
    assert "Автопланирование" in page_html
    assert "/api/calendar/dispatch/plan" in page_html
    assert "/api/calendar/dispatch/plan/apply" in page_html
    assert page.context["planning_queue_count"] >= 5

    anonymous_preview = crm.api_calendar_dispatch_plan(
        make_request(),
        start=start_value,
    )
    assert anonymous_preview.status_code == 401
    worker_preview = crm.api_calendar_dispatch_plan(
        make_request("helper2"),
        start=start_value,
    )
    assert worker_preview.status_code == 403
    invalid_preview = crm.api_calendar_dispatch_plan(
        make_request("owner2"),
        start="bad-date",
    )
    assert invalid_preview.status_code == 400

    preview = crm.api_calendar_dispatch_plan(
        make_request("owner2"),
        start=start_value,
        days=14,
        limit=50,
    )
    assert preview["ok"] is True
    assert preview["company_id"] == 2
    preview_items = {
        item["task_id"]: item
        for item in preview["items"]
    }
    assert outsider_id not in preview_items
    assert urgent_id in preview_items
    assert normal_id in preview_items
    assert fixed_id in preview_items
    assert dated_id in preview_items
    assert preview["items"][0]["task_id"] == urgent_id
    assert preview_items[fixed_id]["target_workers"] == ["helper2"]
    assert preview_items[dated_id]["target_date"] == dated_value
    assert preview_items[urgent_id]["target_time_from"]
    assert preview_items[urgent_id]["target_time_to"]
    assert (
        preview_items[urgent_id]["target_time_label"]
        == (
            f"{preview_items[urgent_id]['target_time_from']}–"
            f"{preview_items[urgent_id]['target_time_to']}"
        )
    )
    assert any(
        item["task_id"] == past_id
        and item["reason"] == "Дата заявки уже прошла."
        for item in preview["unscheduled"]
    )
    reserved_slots = [
        (item["target_date"], worker_name)
        for item in preview["items"]
        for worker_name in item["target_workers"]
    ]
    assert len(reserved_slots) == len(set(reserved_slots))

    anonymous_apply = await crm.api_calendar_dispatch_plan_apply(
        make_json_request(
            None,
            "/api/calendar/dispatch/plan/apply",
            {"items": [preview_items[urgent_id]]},
        )
    )
    assert anonymous_apply.status_code == 401
    worker_apply = await crm.api_calendar_dispatch_plan_apply(
        make_json_request(
            "helper2",
            "/api/calendar/dispatch/plan/apply",
            {"items": [preview_items[urgent_id]]},
        )
    )
    assert worker_apply.status_code == 403
    empty_apply = await crm.api_calendar_dispatch_plan_apply(
        make_json_request(
            "owner2",
            "/api/calendar/dispatch/plan/apply",
            {"items": []},
        )
    )
    assert empty_apply.status_code == 400

    missing_time_item = {
        **preview_items[urgent_id],
        "target_time_from": "",
        "target_time_to": "",
    }
    missing_time_apply = await crm.api_calendar_dispatch_plan_apply(
        make_json_request(
            "owner2",
            "/api/calendar/dispatch/plan/apply",
            {"items": [missing_time_item]},
        )
    )
    assert missing_time_apply["summary"] == {
        "requested": 1,
        "applied": 0,
        "skipped": 1,
    }
    assert missing_time_apply["skipped"][0]["reason"] == (
        "Не выбрано временное окно."
    )

    conn = connect()
    c = conn.cursor()
    c.execute("""
    UPDATE tasks
    SET worker='worker2', workers='worker2'
    WHERE id=? AND company_id=2
    """, (normal_id,))
    conn.commit()
    conn.close()
    forged_outsider = {
        **preview_items[urgent_id],
        "task_id": outsider_id,
    }
    original_send_message_to_chat = crm.send_message_to_chat
    telegram_messages = []
    crm.send_message_to_chat = lambda chat_id, text: telegram_messages.append(
        (chat_id, text)
    )

    try:
        apply_result = await crm.api_calendar_dispatch_plan_apply(
            make_json_request(
                "owner2",
                "/api/calendar/dispatch/plan/apply",
                {
                    "items": [
                        preview_items[urgent_id],
                        preview_items[normal_id],
                        preview_items[fixed_id],
                        preview_items[dated_id],
                        forged_outsider,
                    ],
                },
            )
        )
    finally:
        crm.send_message_to_chat = original_send_message_to_chat

    assert apply_result["ok"] is True
    assert apply_result["summary"] == {
        "requested": 5,
        "applied": 3,
        "skipped": 2,
    }
    assert {
        item["task_id"]
        for item in apply_result["applied"]
    } == {urgent_id, fixed_id, dated_id}
    skipped_by_id = {
        item["task_id"]: item["reason"]
        for item in apply_result["skipped"]
    }
    assert "изменилась после расчёта" in skipped_by_id[normal_id]
    assert skipped_by_id[outsider_id] == "Заявка не найдена."

    conn = connect()
    c = conn.cursor()
    planned_tasks = c.execute(f"""
    SELECT id, task_date, worker, workers, time_from, time_to
    FROM tasks
    WHERE id IN ({",".join("?" for _ in task_ids)})
    """, task_ids).fetchall()
    planned_by_id = {
        row["id"]: row
        for row in planned_tasks
    }

    for task_id in (urgent_id, fixed_id, dated_id):
        planned = planned_by_id[task_id]
        preview_item = preview_items[task_id]
        assert planned["task_date"] == preview_item["target_date"]
        assert planned["workers"] == preview_item["target_workers_csv"]
        assert planned["time_from"] == preview_item["target_time_from"]
        assert planned["time_to"] == preview_item["target_time_to"]

    activity_count = c.execute(f"""
    SELECT COUNT(*)
    FROM task_activity
    WHERE task_id IN ({",".join("?" for _ in task_ids)})
      AND action='Применён автоматический план'
    """, task_ids).fetchone()[0]
    notification_count = c.execute(f"""
    SELECT COUNT(*)
    FROM notifications
    WHERE link IN ({",".join("?" for _ in task_ids)})
      AND title LIKE 'Запланирована заявка #%'
    """, [f"/task/{task_id}" for task_id in task_ids]).fetchone()[0]
    assert activity_count == 3
    assert notification_count >= 3
    assert any(
        chat_id == "planner-helper-chat"
        for chat_id, _ in telegram_messages
    )

    placeholders = ",".join("?" for _ in task_ids)
    c.execute(
        f"DELETE FROM task_activity WHERE task_id IN ({placeholders})",
        task_ids,
    )
    c.execute(
        f"DELETE FROM notifications WHERE link IN ({placeholders})",
        [f"/task/{task_id}" for task_id in task_ids],
    )
    c.execute(
        f"DELETE FROM tasks WHERE id IN ({placeholders})",
        task_ids,
    )

    for worker_row in original_workers:
        c.execute("""
        UPDATE users
        SET daily_capacity=?, telegram_chat_id=?
        WHERE company_id=2 AND username=?
        """, (
            worker_row["daily_capacity"],
            worker_row["telegram_chat_id"],
            worker_row["username"],
        ))

    conn.commit()
    conn.close()


async def assert_platform_calendar_health():
    policy_environment_names = (
        "CALENDAR_INCIDENT_RESPONSE_MINUTES",
        "CALENDAR_INCIDENT_ESCALATION_MINUTES",
        "CALENDAR_INCIDENT_RECOVERY_MINUTES",
        "CALENDAR_WATCHDOG_STALE_HOURS",
        "CALENDAR_SCHEDULER_STUCK_MINUTES",
    )
    previous_policy_environment = {
        name: os.environ.get(name)
        for name in policy_environment_names
    }

    try:
        os.environ["CALENDAR_INCIDENT_RESPONSE_MINUTES"] = "45"
        os.environ["CALENDAR_INCIDENT_ESCALATION_MINUTES"] = "20"
        os.environ["CALENDAR_INCIDENT_RECOVERY_MINUTES"] = "90"
        os.environ["CALENDAR_WATCHDOG_STALE_HOURS"] = "12"
        os.environ["CALENDAR_SCHEDULER_STUCK_MINUTES"] = "invalid"
        configured_policy = crm.get_calendar_incident_policy()
        assert configured_policy == {
            "response_minutes": 45,
            "escalation_minutes": 45,
            "recovery_minutes": 90,
            "stale_hours": 12,
            "stuck_minutes": 30,
        }
        bounded_policy = crm.get_calendar_incident_policy(
            response_minutes=500,
            escalation_minutes=1,
            recovery_minutes=10,
            stale_hours=100,
            stuck_minutes=2,
        )
        assert bounded_policy == {
            "response_minutes": 240,
            "escalation_minutes": 240,
            "recovery_minutes": 240,
            "stale_hours": 72,
            "stuck_minutes": 5,
        }
    finally:
        for name, value in previous_policy_environment.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value

    assert crm.get_calendar_incident_priority(
        "stale",
        "stale",
        False,
        20,
        response_target_minutes=25,
    )["response_overdue"] is False
    assert crm.get_calendar_incident_priority(
        "stale",
        "stale",
        False,
        20,
        response_target_minutes=15,
    )["response_overdue"] is True
    assert crm.get_calendar_incident_priority(
        "stale",
        "stale",
        True,
        20,
        recovery_overdue=True,
    )["code"] == "critical"
    conn = connect()
    scheduler_status_columns = {
        row["name"]
        for row in conn.execute(
            "PRAGMA table_info(calendar_plan_scheduler_status)"
        ).fetchall()
    }
    conn.close()
    assert {
        "incident_assigned_at",
        "incident_assigned_to",
        "incident_assigned_by",
    }.issubset(scheduler_status_columns)

    company_id = 901
    bulk_company_ids = [902, 903]
    company_name = "Smoke Calendar Health"
    owner_username = "smoke_health_owner"
    backup_admin_username = "smoke_platform_backup"
    now_dt = datetime.now()
    old_value = (
        now_dt - timedelta(hours=8)
    ).strftime("%Y-%m-%d %H:%M")
    incident_value = (
        now_dt - timedelta(hours=2)
    ).strftime("%Y-%m-%d %H:%M")
    conn = connect()
    c = conn.cursor()
    c.execute("""
    INSERT INTO companies (
        id, name, owner_username, created_at
    )
    VALUES (?, ?, ?, ?)
    """, (
        company_id,
        company_name,
        owner_username,
        old_value,
    ))
    c.execute("""
    INSERT INTO users (
        username, password, role, company_id,
        is_active, last_seen
    )
    VALUES (?, 'x', 'boss', ?, 1, ?)
    """, (
        owner_username,
        company_id,
        old_value,
    ))
    c.execute("""
    INSERT INTO users (
        username, password, role, company_id,
        is_active, last_seen
    )
    VALUES (?, 'x', 'superadmin', 1, 1, ?)
    """, (
        backup_admin_username,
        old_value,
    ))
    c.execute("""
    INSERT INTO company_settings (
        company_id, company_name,
        calendar_auto_publish, calendar_auto_remind,
        calendar_auto_days_ahead,
        calendar_auto_window_start,
        calendar_auto_window_end,
        updated_at
    )
    VALUES (?, ?, 1, 1, 5, '08:00', '20:00', ?)
    """, (
        company_id,
        company_name,
        old_value,
    ))
    c.execute("""
    INSERT INTO calendar_plan_scheduler_runs (
        company_id, source, actor_username,
        range_start, range_end, status, reason,
        changed_days, notifications_sent,
        started_at, completed_at
    )
    VALUES (
        ?, 'scheduler', ?, '2026-06-01', '2026-06-05',
        'done', '', 2, 3, ?, ?
    )
    """, (
        company_id,
        owner_username,
        old_value,
        old_value,
    ))
    c.execute("""
    INSERT INTO calendar_plan_scheduler_runs (
        company_id, source, actor_username,
        range_start, range_end, status, reason,
        changed_days, notifications_sent,
        started_at, completed_at
    )
    VALUES (
        ?, 'scheduler', ?, '2026-06-06', '2026-06-10',
        'error', 'Smoke scheduler failure', 0, 1, ?, ?
    )
    """, (
        company_id,
        owner_username,
        incident_value,
        incident_value,
    ))
    c.execute("""
    INSERT INTO calendar_scheduler_incident_events (
        company_id, incident_type, event_type,
        actor_username, message, created_at
    )
    VALUES (?, 'stale', 'opened', '', ?, ?)
    """, (
        company_id,
        "Планировщик не запускался более шести часов.",
        incident_value,
    ))
    c.execute("""
    INSERT INTO calendar_plan_operation_runs (
        company_id, week_start, week_end,
        action, source, actor_username,
        changed_days, notifications_sent,
        skipped_days, result_json, created_at
    )
    VALUES (
        ?, '2026-06-01', '2026-06-07',
        'publish_ready', 'scheduler', ?,
        2, 3, 1, '{}', ?
    )
    """, (
        company_id,
        owner_username,
        old_value,
    ))
    c.execute("""
    INSERT INTO calendar_plan_scheduler_status (
        company_id, last_started_at, last_completed_at,
        last_status, last_error, last_changed_days,
        last_notifications_sent, last_source,
        last_triggered_by, active_incident,
        incident_started_at, incident_message,
        last_alerted_at
    )
    VALUES (
        ?, ?, ?, 'done', '', 2, 3, 'scheduler',
        ?, 'stale', ?, ?, ?
    )
    """, (
        company_id,
        old_value,
        old_value,
        owner_username,
        incident_value,
        "Планировщик не запускался более шести часов.",
        incident_value,
    ))
    conn.commit()
    conn.close()

    try:
        sample_sessions = crm.build_calendar_incident_sessions(
            [
                {
                    "id": 1,
                    "company_id": 77,
                    "company_name": "Тестовая компания",
                    "incident_type": "error",
                    "event_type": "opened",
                    "actor_username": "",
                    "message": "Ошибка",
                    "created_at": "2026-06-10 10:00",
                },
                {
                    "id": 2,
                    "company_id": 77,
                    "company_name": "Тестовая компания",
                    "incident_type": "error",
                    "event_type": "acknowledged",
                    "actor_username": "super",
                    "message": "Ошибка",
                    "created_at": "2026-06-10 10:20",
                },
                {
                    "id": 3,
                    "company_id": 77,
                    "company_name": "Тестовая компания",
                    "incident_type": "error",
                    "event_type": "recovery_started",
                    "actor_username": "super",
                    "message": "Проверка",
                    "created_at": "2026-06-10 10:25",
                },
                {
                    "id": 4,
                    "company_id": 77,
                    "company_name": "Тестовая компания",
                    "incident_type": "error",
                    "event_type": "recovery_overdue",
                    "actor_username": "watchdog",
                    "message": "Просрочено",
                    "created_at": "2026-06-10 10:55",
                },
                {
                    "id": 5,
                    "company_id": 77,
                    "company_name": "Тестовая компания",
                    "incident_type": "error",
                    "event_type": "recovered",
                    "actor_username": "super",
                    "message": "Готово",
                    "created_at": "2026-06-10 11:00",
                },
                {
                    "id": 6,
                    "company_id": 77,
                    "company_name": "Тестовая компания",
                    "incident_type": "stale",
                    "event_type": "opened",
                    "actor_username": "",
                    "message": "Нет запуска",
                    "created_at": "2026-06-10 12:00",
                },
            ],
            now_dt=datetime(2026, 6, 10, 13, 0),
            recovery_target_minutes=30,
        )
        assert len(sample_sessions) == 2
        assert sample_sessions[0]["response_minutes"] == 20
        assert sample_sessions[0]["recovery_minutes"] == 40
        assert sample_sessions[0]["response_sla_met"] is True
        assert sample_sessions[0]["recovery_sla_met"] is False
        assert sample_sessions[0]["recovery_overdue_events"] == 1
        assert sample_sessions[0]["recovery_attempts"] == 1
        assert sample_sessions[0]["status_label"] == "Восстановлен"
        assert sample_sessions[1]["is_active"] is True
        assert sample_sessions[1]["age_minutes"] == 60
        assert sample_sessions[1]["status_label"] == "Ожидает реакции"
        assert crm.format_calendar_incident_age(None) == "неизвестно"
        assert crm.format_calendar_incident_age(29) == "29 мин"
        assert crm.format_calendar_incident_age(90) == "1 ч 30 мин"
        assert crm.format_calendar_incident_age(1500) == "1 д 1 ч"
        immediate_error_priority = (
            crm.get_calendar_incident_priority(
                "error",
                "error",
                False,
                5,
            )
        )
        assert immediate_error_priority["code"] == "critical"
        acknowledged_priority = crm.get_calendar_incident_priority(
            "stale",
            "stale",
            True,
            180,
        )
        assert acknowledged_priority["code"] == "medium"
        health = crm.get_platform_calendar_health(
            now_dt=now_dt,
            status_filter="problem",
        )
        assert health["policy"] == crm.get_calendar_incident_policy()
        company = next(
            item
            for item in health["items"]
            if item["company_id"] == company_id
        )
        assert company["company_name"] == company_name
        assert company["owner_username"] == owner_username
        assert company["status_code"] == "stale"
        assert company["status_label"] == "Давно не запускалась"
        assert company["last_scheduler_run_status_label"] == "Ошибка"
        assert company["automation_enabled"] is True
        assert company["is_problem"] is True
        assert company["is_acknowledged"] is False
        assert company["requires_response"] is True
        assert company["priority_code"] == "critical"
        assert company["priority_label"] == "Критический"
        assert company["response_overdue"] is True
        assert company["incident_age_minutes"] == 120
        assert company["incident_age_label"] == "2 ч"
        assert company["last_activity_at"] == incident_value
        assert company["detail_url"] == (
            f"/platform/calendar-health/{company_id}"
        )
        assert health["summary"]["problems"] >= 1
        assert health["summary"]["critical"] >= 1
        assert health["summary"]["unacknowledged"] >= 1
        assert health["summary"]["active_incidents"] >= 1
        assert health["summary"]["assigned"] == 0
        assert health["summary"]["unassigned"] >= 1
        assert health["summary"]["my_incidents"] == 0
        assert {
            item["username"] for item in health["admin_workload"]
        } >= {"super", backup_admin_username}
        assert all(
            item["assigned"] == 0
            for item in health["admin_workload"]
        )
        assert all(item["is_problem"] for item in health["items"])

        critical_health = crm.get_platform_calendar_health(
            now_dt=now_dt,
            status_filter="critical",
        )
        assert critical_health["status_filter"] == "critical"
        assert any(
            item["company_id"] == company_id
            for item in critical_health["items"]
        )
        assert all(
            item["priority_code"] == "critical"
            for item in critical_health["items"]
        )
        unacknowledged_health = crm.get_platform_calendar_health(
            now_dt=now_dt,
            status_filter="unacknowledged",
        )
        assert any(
            item["company_id"] == company_id
            for item in unacknowledged_health["items"]
        )
        assert all(
            item["requires_response"]
            for item in unacknowledged_health["items"]
        )
        unassigned_health = crm.get_platform_calendar_health(
            now_dt=now_dt,
            assignee_filter="unassigned",
        )
        assert unassigned_health["assignee_filter"] == "unassigned"
        assert any(
            item["company_id"] == company_id
            for item in unassigned_health["items"]
        )
        assert all(
            item["active_incident"] and not item["is_acknowledged"]
            for item in unassigned_health["items"]
        )
        empty_personal_health = crm.get_platform_calendar_health(
            now_dt=now_dt,
            assignee_filter="me",
            current_username="super",
        )
        assert empty_personal_health["assignee_filter"] == "me"
        assert empty_personal_health["assignee_target"] == "super"
        assert empty_personal_health["items"] == []
        invalid_assignee_health = crm.get_platform_calendar_health(
            now_dt=now_dt,
            assignee_filter="missing_admin",
            current_username="super",
        )
        assert invalid_assignee_health["assignee_filter"] == "all"
        normalized = crm.get_platform_calendar_health(
            now_dt=now_dt,
            status_filter="unknown",
        )
        assert normalized["status_filter"] == "all"
        assert crm.build_platform_calendar_health_queue_url(
            status="unknown",
            assignee="",
            notice="acknowledged",
        ) == (
            "/platform/calendar-health?"
            "status=all&assignee=all&notice=acknowledged"
        )

        anonymous = await crm.platform_calendar_health_page(
            make_public_asgi_request("/platform/calendar-health"),
        )
        assert anonymous.status_code == 302
        assert anonymous.headers["location"] == "/login"
        boss = await crm.platform_calendar_health_page(
            make_asgi_request(
                "owner2",
                "/platform/calendar-health",
            ),
        )
        assert boss.status_code == 302
        assert boss.headers["location"] == "/"
        page = await crm.platform_calendar_health_page(
            make_asgi_request(
                "super",
                "/platform/calendar-health",
            ),
            status="problem",
        )
        assert page.status_code == 200
        assert page.context["selected_status"] == "problem"
        assert page.context["selected_assignee"] == "all"
        assert any(
            item["company_id"] == company_id
            for item in page.context["companies"]
        )
        html = page.body.decode("utf-8")
        assert "Здоровье календарных автоматизаций" in html
        assert "Рабочая очередь компаний" in html
        assert "Критические" in html
        assert "Не приняты" in html
        assert "Критический" in html
        assert "Реакция просрочена" in html
        assert "Назначено мне" in html
        assert "Нагрузка администраторов" in html
        assert "Мои инциденты" in html
        assert "Без ответственного" in html
        assert "Принять себе" in html
        assert (
            "return_to=queue&amp;status=problem&amp;assignee=all"
            in html
        )
        assert backup_admin_username in html
        assert (
            f"реакция: {health['policy']['response_minutes']} мин."
            in html
        )
        assert (
            f"эскалация: {health['policy']['escalation_minutes']} мин."
            in html
        )
        assert (
            "восстановление: "
            f"{health['policy']['recovery_minutes']} мин."
            in html
        )
        assert "Возраст: 2 ч" in html
        assert "/platform/calendar-health/analytics" in html
        assert company_name in html
        assert "Планировщик не запускался более шести часов." in html
        assert f"/platform/calendar-health/{company_id}" in html
        detail = crm.get_platform_calendar_company_detail(
            company_id,
            now_dt=now_dt,
        )
        assert detail["company"]["company_name"] == company_name
        assert detail["policy"] == health["policy"]
        assert "super" in detail["platform_admins"]
        assert backup_admin_username in detail["platform_admins"]
        assert detail["summary"] == {
            "runs": 2,
            "successful": 1,
            "problems": 1,
            "changed_days": 2,
            "notifications": 4,
            "incident_events": 1,
            "operations": 1,
        }
        assert detail["runs"][0]["status_label"] == "Ошибка"
        assert detail["runs"][0]["reason"] == "Smoke scheduler failure"
        assert detail["incidents"][0]["event_type_label"] == "Открыт"
        assert detail["operations"][0]["action_label"] == (
            "Публикация готовых планов"
        )
        assert crm.get_platform_calendar_company_detail(
            999999,
            now_dt=now_dt,
        ) is None
        anonymous_detail = (
            await crm.platform_calendar_company_health_page(
                make_public_asgi_request(
                    f"/platform/calendar-health/{company_id}"
                ),
                company_id,
            )
        )
        assert anonymous_detail.status_code == 302
        assert anonymous_detail.headers["location"] == "/login"
        boss_detail = (
            await crm.platform_calendar_company_health_page(
                make_asgi_request(
                    "owner2",
                    f"/platform/calendar-health/{company_id}",
                ),
                company_id,
            )
        )
        assert boss_detail.status_code == 302
        assert boss_detail.headers["location"] == "/"
        detail_page = (
            await crm.platform_calendar_company_health_page(
                make_asgi_request(
                    "super",
                    f"/platform/calendar-health/{company_id}",
                ),
                company_id,
            )
        )
        assert detail_page.status_code == 200
        detail_html = detail_page.body.decode("utf-8")
        assert "Последние запуски" in detail_html
        assert "История инцидентов" in detail_html
        assert "Операции с планами" in detail_html
        assert "Smoke scheduler failure" in detail_html
        assert "Публикация готовых планов" in detail_html
        assert (
            f"/platform/calendar-health/{company_id}/acknowledge"
            in detail_html
        )
        assert (
            f"/platform/calendar-health/{company_id}/recover"
            not in detail_html
        )
        assert (
            f"/platform/calendar-health/{company_id}/note"
            in detail_html
        )
        assert "Рабочая заметка" in detail_html
        assert (
            "Передача станет доступна после принятия инцидента"
            in detail_html
        )
        assert "Сначала примите инцидент в работу." in detail_html
        assert "Регламент: реакция" in detail_html
        anonymous_note = await crm.platform_calendar_incident_note(
            make_public_asgi_request(
                f"/platform/calendar-health/{company_id}/note"
            ),
            company_id,
        )
        assert anonymous_note.status_code == 302
        assert anonymous_note.headers["location"] == "/login"
        boss_note = await crm.platform_calendar_incident_note(
            make_form_request(
                "owner2",
                f"/platform/calendar-health/{company_id}/note",
                {"message": "Недоступная заметка"},
            ),
            company_id,
        )
        assert boss_note.status_code == 302
        assert boss_note.headers["location"] == "/"
        assignment_before_acknowledge = (
            await crm.platform_calendar_incident_assign(
                make_form_request(
                    "super",
                    (
                        f"/platform/calendar-health/{company_id}"
                        "/assign"
                    ),
                    {
                        "assignee_username": (
                            backup_admin_username
                        ),
                    },
                ),
                company_id,
            )
        )
        assert assignment_before_acknowledge.headers["location"] == (
            f"/platform/calendar-health/{company_id}"
            "?error=incident_not_acknowledged"
        )
        recovery_before_acknowledge = (
            await crm.platform_calendar_incident_recover(
                make_form_request(
                    "super",
                    (
                        f"/platform/calendar-health/{company_id}"
                        "/recover"
                    ),
                    {
                        "recovery_note": (
                            "Проверка до принятия инцидента."
                        ),
                    },
                ),
                company_id,
            )
        )
        assert recovery_before_acknowledge.headers["location"] == (
            f"/platform/calendar-health/{company_id}"
            "?error=incident_not_acknowledged"
        )
        anonymous_acknowledge = (
            await crm.platform_calendar_incident_acknowledge(
                make_public_asgi_request(
                    (
                        f"/platform/calendar-health/{company_id}"
                        "/acknowledge"
                    )
                ),
                company_id,
            )
        )
        assert anonymous_acknowledge.status_code == 302
        assert anonymous_acknowledge.headers["location"] == "/login"
        boss_acknowledge = (
            await crm.platform_calendar_incident_acknowledge(
                make_asgi_request(
                    "owner2",
                    (
                        f"/platform/calendar-health/{company_id}"
                        "/acknowledge"
                    ),
                ),
                company_id,
            )
        )
        assert boss_acknowledge.status_code == 302
        assert boss_acknowledge.headers["location"] == "/"
        platform_acknowledge = (
            await crm.platform_calendar_incident_acknowledge(
                make_asgi_request(
                    "super",
                    (
                        f"/platform/calendar-health/{company_id}"
                        "/acknowledge"
                    ),
                ),
                company_id,
                return_to="queue",
                status="unacknowledged",
                assignee="unassigned",
            )
        )
        assert platform_acknowledge.status_code == 302
        assert platform_acknowledge.headers["location"] == (
            "/platform/calendar-health?"
            "status=unacknowledged"
            "&assignee=unassigned"
            "&notice=acknowledged"
        )
        claimed_queue_page = await crm.platform_calendar_health_page(
            make_asgi_request(
                "super",
                (
                    "/platform/calendar-health"
                    "?status=unacknowledged"
                    "&assignee=unassigned"
                    "&notice=acknowledged"
                ),
            ),
            status="unacknowledged",
            assignee="unassigned",
            notice="acknowledged",
        )
        claimed_queue_html = claimed_queue_page.body.decode("utf-8")
        assert "Инцидент принят в работу и назначен вам." in (
            claimed_queue_html
        )
        assert all(
            item["company_id"] != company_id
            for item in claimed_queue_page.context["companies"]
        )
        conn = connect()
        c = conn.cursor()
        for bulk_company_id in bulk_company_ids:
            c.execute("""
            INSERT INTO companies (
                id, name, owner_username, created_at
            )
            VALUES (?, ?, ?, ?)
            """, (
                bulk_company_id,
                f"Bulk Calendar Health {bulk_company_id}",
                f"bulk_owner_{bulk_company_id}",
                old_value,
            ))
            c.execute("""
            INSERT INTO company_settings (
                company_id, company_name,
                calendar_auto_publish, calendar_auto_remind,
                calendar_auto_days_ahead,
                calendar_auto_window_start,
                calendar_auto_window_end,
                updated_at
            )
            VALUES (?, ?, 1, 1, 5, '08:00', '20:00', ?)
            """, (
                bulk_company_id,
                f"Bulk Calendar Health {bulk_company_id}",
                old_value,
            ))
            c.execute("""
            INSERT INTO calendar_plan_scheduler_status (
                company_id, last_status, active_incident,
                incident_started_at, incident_message
            )
            VALUES (?, 'error', 'error', ?, ?)
            """, (
                bulk_company_id,
                incident_value,
                "Массовая проверка очереди календаря.",
            ))
            c.execute("""
            INSERT INTO calendar_scheduler_incident_events (
                company_id, incident_type, event_type,
                actor_username, message, created_at
            )
            VALUES (?, 'error', 'opened', '', ?, ?)
            """, (
                bulk_company_id,
                "Массовая проверка очереди календаря.",
                incident_value,
            ))
        conn.commit()
        conn.close()
        bulk_page = await crm.platform_calendar_health_page(
            make_asgi_request(
                "super",
                (
                    "/platform/calendar-health"
                    "?status=unacknowledged"
                    "&assignee=unassigned"
                ),
            ),
            status="unacknowledged",
            assignee="unassigned",
        )
        bulk_html = bulk_page.body.decode("utf-8")
        assert bulk_page.context["visible_claimable_count"] == 2
        assert "Принять видимые · 2" in bulk_html
        assert (
            "/platform/calendar-health/claim-visible"
            in bulk_html
        )
        bulk_response = (
            await crm.platform_calendar_claim_visible_incidents(
                make_asgi_request(
                    "super",
                    "/platform/calendar-health/claim-visible",
                ),
                status="unacknowledged",
                assignee="unassigned",
            )
        )
        assert bulk_response.headers["location"] == (
            "/platform/calendar-health?"
            "status=unacknowledged"
            "&assignee=unassigned"
            "&notice=bulk_acknowledged"
            "&claimed=2"
        )
        bulk_done_page = await crm.platform_calendar_health_page(
            make_asgi_request(
                "super",
                (
                    "/platform/calendar-health"
                    "?status=unacknowledged"
                    "&assignee=unassigned"
                    "&notice=bulk_acknowledged"
                    "&claimed=2"
                ),
            ),
            status="unacknowledged",
            assignee="unassigned",
            notice="bulk_acknowledged",
            claimed=2,
        )
        assert "Принято инцидентов: 2." in (
            bulk_done_page.body.decode("utf-8")
        )
        assert bulk_done_page.context["visible_claimable_count"] == 0
        repeated_bulk_response = (
            await crm.platform_calendar_claim_visible_incidents(
                make_asgi_request(
                    "super",
                    "/platform/calendar-health/claim-visible",
                ),
                status="unacknowledged",
                assignee="unassigned",
            )
        )
        assert repeated_bulk_response.headers["location"] == (
            "/platform/calendar-health?"
            "status=unacknowledged"
            "&assignee=unassigned"
            "&notice=bulk_empty"
        )
        conn = connect()
        c = conn.cursor()
        bulk_status_rows = c.execute(f"""
        SELECT
            company_id,
            incident_acknowledged_by,
            incident_assigned_to,
            incident_assigned_by
        FROM calendar_plan_scheduler_status
        WHERE company_id IN ({','.join('?' for _ in bulk_company_ids)})
        ORDER BY company_id
        """, bulk_company_ids).fetchall()
        bulk_events = c.execute(f"""
        SELECT company_id, event_type, actor_username
        FROM calendar_scheduler_incident_events
        WHERE company_id IN ({','.join('?' for _ in bulk_company_ids)})
          AND event_type='acknowledged'
        ORDER BY company_id
        """, bulk_company_ids).fetchall()
        conn.close()
        assert [row["company_id"] for row in bulk_status_rows] == (
            bulk_company_ids
        )
        assert all(
            row["incident_acknowledged_by"] == "super"
            and row["incident_assigned_to"] == "super"
            and row["incident_assigned_by"] == "super"
            for row in bulk_status_rows
        )
        assert [
            (row["company_id"], row["event_type"], row["actor_username"])
            for row in bulk_events
        ] == [
            (bulk_company_ids[0], "acknowledged", "super"),
            (bulk_company_ids[1], "acknowledged", "super"),
        ]
        conn = connect()
        c = conn.cursor()
        for bulk_company_id in bulk_company_ids:
            c.execute(
                "DELETE FROM calendar_plan_scheduler_status WHERE company_id=?",
                (bulk_company_id,),
            )
            c.execute(
                "DELETE FROM calendar_scheduler_incident_events WHERE company_id=?",
                (bulk_company_id,),
            )
            c.execute(
                "DELETE FROM company_settings WHERE company_id=?",
                (bulk_company_id,),
            )
            c.execute(
                "DELETE FROM companies WHERE id=?",
                (bulk_company_id,),
            )
        conn.commit()
        conn.close()
        repeated_platform_acknowledge = (
            await crm.platform_calendar_incident_acknowledge(
                make_asgi_request(
                    "super",
                    (
                        f"/platform/calendar-health/{company_id}"
                        "/acknowledge"
                    ),
                ),
                company_id,
            )
        )
        assert repeated_platform_acknowledge.headers["location"] == (
            f"/platform/calendar-health/{company_id}"
            "?error=already_acknowledged"
        )
        acknowledged_detail = (
            await crm.platform_calendar_company_health_page(
                make_asgi_request(
                    "super",
                    f"/platform/calendar-health/{company_id}",
                ),
                company_id,
                notice="acknowledged",
            )
        )
        acknowledged_html = acknowledged_detail.body.decode("utf-8")
        assert "Инцидент принят в работу от имени платформы." in (
            acknowledged_html
        )
        assert "Принят в работу" in acknowledged_html
        assert (
            f"/platform/calendar-health/{company_id}/acknowledge"
            not in acknowledged_html
        )
        assert (
            f"/platform/calendar-health/{company_id}/assign"
            in acknowledged_html
        )
        assert (
            f"/platform/calendar-health/{company_id}"
            "/acknowledge?return_to=queue"
            not in acknowledged_html
        )
        assert (
            f"/platform/calendar-health/{company_id}/recover"
            in acknowledged_html
        )
        assert "Результат диагностики" in acknowledged_html
        assert "Возможна публикация планов" in acknowledged_html
        assert backup_admin_username in acknowledged_html
        personal_health = crm.get_platform_calendar_health(
            now_dt=now_dt,
            status_filter="problem",
            assignee_filter="me",
            current_username="super",
        )
        assert personal_health["assignee_filter"] == "me"
        assert personal_health["assignee_target"] == "super"
        assert [
            item["company_id"] for item in personal_health["items"]
        ] == [company_id]
        assert personal_health["items"][0]["is_mine"] is True
        assert personal_health["summary"]["assigned"] == 1
        assert personal_health["summary"]["my_incidents"] == 1
        super_workload = next(
            item
            for item in personal_health["admin_workload"]
            if item["username"] == "super"
        )
        assert super_workload["assigned"] == 1
        assert super_workload["is_current"] is True
        personal_page = await crm.platform_calendar_health_page(
            make_asgi_request(
                "super",
                "/platform/calendar-health",
            ),
            status="problem",
            assignee="me",
        )
        assert personal_page.context["selected_assignee"] == "me"
        personal_html = personal_page.body.decode("utf-8")
        assert "Ответственный super" in personal_html
        assert "· вы" in personal_html
        assert "status=critical" in personal_html
        assert "assignee=me" in personal_html
        empty_note = await crm.platform_calendar_incident_note(
            make_form_request(
                "super",
                f"/platform/calendar-health/{company_id}/note",
                {"message": "   "},
            ),
            company_id,
        )
        assert empty_note.headers["location"] == (
            f"/platform/calendar-health/{company_id}"
            "?error=empty_note"
        )
        long_note = await crm.platform_calendar_incident_note(
            make_form_request(
                "super",
                f"/platform/calendar-health/{company_id}/note",
                {"message": "x" * 501},
            ),
            company_id,
        )
        assert long_note.headers["location"] == (
            f"/platform/calendar-health/{company_id}"
            "?error=note_too_long"
        )
        added_note = await crm.platform_calendar_incident_note(
            make_form_request(
                "super",
                f"/platform/calendar-health/{company_id}/note",
                {
                    "message": (
                        "Проверяем журнал и настройки окна запуска."
                    ),
                },
            ),
            company_id,
        )
        assert added_note.headers["location"] == (
            f"/platform/calendar-health/{company_id}"
            "?notice=note_added"
        )
        missing_assignee = (
            await crm.platform_calendar_incident_assign(
                make_form_request(
                    "super",
                    (
                        f"/platform/calendar-health/{company_id}"
                        "/assign"
                    ),
                    {"assignee_username": "missing_admin"},
                ),
                company_id,
            )
        )
        assert missing_assignee.headers["location"] == (
            f"/platform/calendar-health/{company_id}"
            "?error=assignee_not_found"
        )
        assigned_incident = (
            await crm.platform_calendar_incident_assign(
                make_form_request(
                    "super",
                    (
                        f"/platform/calendar-health/{company_id}"
                        "/assign"
                    ),
                    {
                        "assignee_username": (
                            backup_admin_username
                        ),
                    },
                ),
                company_id,
            )
        )
        assert assigned_incident.headers["location"] == (
            f"/platform/calendar-health/{company_id}"
            "?notice=assigned"
        )
        repeated_assignment = (
            await crm.platform_calendar_incident_assign(
                make_form_request(
                    "super",
                    (
                        f"/platform/calendar-health/{company_id}"
                        "/assign"
                    ),
                    {
                        "assignee_username": (
                            backup_admin_username
                        ),
                    },
                ),
                company_id,
            )
        )
        assert repeated_assignment.headers["location"] == (
            f"/platform/calendar-health/{company_id}"
            "?error=already_assigned"
        )
        conn = connect()
        c = conn.cursor()
        assigned_status = c.execute("""
        SELECT
            incident_acknowledged_at,
            incident_acknowledged_by,
            incident_assigned_at,
            incident_assigned_to,
            incident_assigned_by
        FROM calendar_plan_scheduler_status
        WHERE company_id=?
        """, (company_id,)).fetchone()
        collaboration_events = c.execute("""
        SELECT event_type, actor_username, message
        FROM calendar_scheduler_incident_events
        WHERE company_id=?
          AND event_type IN ('note', 'reassigned')
        ORDER BY id
        """, (company_id,)).fetchall()
        assignment_notifications = c.execute("""
        SELECT username, title, message, link
        FROM notifications
        WHERE username=?
          AND title='Назначен календарный инцидент'
          AND link=?
        """, (
            backup_admin_username,
            f"/platform/calendar-health/{company_id}",
        )).fetchall()
        conn.close()
        assert assigned_status["incident_acknowledged_at"]
        assert assigned_status["incident_acknowledged_by"] == "super"
        assert assigned_status["incident_assigned_at"]
        assert assigned_status["incident_assigned_to"] == (
            backup_admin_username
        )
        assert assigned_status["incident_assigned_by"] == "super"
        assert [
            row["event_type"] for row in collaboration_events
        ] == ["note", "reassigned"]
        assert collaboration_events[0]["actor_username"] == "super"
        assert collaboration_events[0]["message"] == (
            "Проверяем журнал и настройки окна запуска."
        )
        assert backup_admin_username in (
            collaboration_events[1]["message"]
        )
        assert len(assignment_notifications) == 1
        assert company_name in assignment_notifications[0]["message"]
        reassigned_health = crm.get_platform_calendar_health(
            now_dt=now_dt,
            assignee_filter=backup_admin_username,
            current_username="super",
        )
        assert reassigned_health["assignee_filter"] == (
            backup_admin_username
        )
        assert [
            item["company_id"] for item in reassigned_health["items"]
        ] == [company_id]
        assert reassigned_health["items"][0]["is_mine"] is False
        assert reassigned_health["items"][0][
            "assignee_username"
        ] == backup_admin_username
        assert reassigned_health["summary"]["my_incidents"] == 0
        backup_workload = next(
            item
            for item in reassigned_health["admin_workload"]
            if item["username"] == backup_admin_username
        )
        assert backup_workload["assigned"] == 1
        assert backup_workload["critical"] == 0
        assert backup_workload["filter_url"].endswith(
            f"assignee={backup_admin_username}"
        )
        previous_admin_workload = next(
            item
            for item in reassigned_health["admin_workload"]
            if item["username"] == "super"
        )
        assert previous_admin_workload["assigned"] == 0
        combined_reassigned_health = (
            crm.get_platform_calendar_health(
                now_dt=now_dt,
                status_filter="critical",
                assignee_filter=backup_admin_username,
                current_username="super",
            )
        )
        assert combined_reassigned_health["items"] == []
        assigned_detail = (
            await crm.platform_calendar_company_health_page(
                make_asgi_request(
                    "super",
                    f"/platform/calendar-health/{company_id}",
                ),
                company_id,
                notice="assigned",
            )
        )
        assigned_html = assigned_detail.body.decode("utf-8")
        assert "Ответственный за инцидент изменён." in assigned_html
        assert "Рабочая заметка" in assigned_html
        assert "Ответственный изменён" in assigned_html
        assert "принял super" in assigned_html
        assert "Сейчас отвечает:" in assigned_html
        assert "Назначил: super" in assigned_html
        assert backup_admin_username in assigned_html
        assert (
            "Запуск доступен только ответственному:"
            in assigned_html
        )
        assert (
            f"/platform/calendar-health/{company_id}/recover"
            not in assigned_html
        )
        acknowledged_health = crm.get_platform_calendar_health(
            now_dt=now_dt,
            status_filter="problem",
            current_username="super",
        )
        acknowledged_company = next(
            item
            for item in acknowledged_health["items"]
            if item["company_id"] == company_id
        )
        assert acknowledged_company["priority_code"] == "medium"
        assert acknowledged_company["priority_label"] == "В работе"
        assert acknowledged_company["requires_response"] is False
        assert acknowledged_company["response_overdue"] is False
        assert acknowledged_company["assignee_username"] == (
            backup_admin_username
        )
        assert acknowledged_company["is_mine"] is False
        acknowledged_at = (
            now_dt - timedelta(minutes=110)
        ).strftime("%Y-%m-%d %H:%M")
        conn = connect()
        c = conn.cursor()
        c.execute("""
        UPDATE calendar_plan_scheduler_status
        SET incident_acknowledged_at=?
        WHERE company_id=?
        """, (
            acknowledged_at,
            company_id,
        ))
        c.execute("""
        UPDATE calendar_scheduler_incident_events
        SET created_at=?
        WHERE company_id=? AND event_type='acknowledged'
        """, (
            acknowledged_at,
            company_id,
        ))
        conn.commit()
        conn.close()
        recovery_watchdog = crm.monitor_calendar_plan_schedulers(
            now_dt=now_dt,
            company_id=company_id,
            recovery_after_minutes=60,
        )
        recovery_overdue = recovery_watchdog["recovery_overdue"]
        assert recovery_watchdog["recoveries_overdue"] == 1
        assert (
            recovery_watchdog[
                "recovery_overdue_notifications_sent"
            ]
            == 2
        )
        assert recovery_overdue["checked"] == 1
        assert recovery_overdue["overdue"] == 1
        assert recovery_overdue["notifications_sent"] == 2
        assert recovery_overdue["items"][0]["company_id"] == (
            company_id
        )
        assert recovery_overdue["items"][0][
            "recovery_age_minutes"
        ] == 110
        repeated_recovery_watchdog = (
            crm.monitor_calendar_plan_schedulers(
                now_dt=now_dt + timedelta(minutes=5),
                company_id=company_id,
                recovery_after_minutes=60,
            )
        )
        assert repeated_recovery_watchdog[
            "recoveries_overdue"
        ] == 0
        assert repeated_recovery_watchdog[
            "recovery_overdue"
        ]["notifications_sent"] == 0
        conn = connect()
        c = conn.cursor()
        recovery_overdue_events = c.execute("""
        SELECT event_type, actor_username
        FROM calendar_scheduler_incident_events
        WHERE company_id=? AND event_type='recovery_overdue'
        """, (company_id,)).fetchall()
        recovery_overdue_notifications = c.execute("""
        SELECT company_id, username, title, link
        FROM notifications
        WHERE username='super'
          AND title='Просрочено восстановление календаря'
          AND link=?
        """, (
            f"/platform/calendar-health/{company_id}",
        )).fetchall()
        conn.close()
        assert [
            (row["event_type"], row["actor_username"])
            for row in recovery_overdue_events
        ] == [("recovery_overdue", "watchdog")]
        assert len(recovery_overdue_notifications) == 1
        overdue_health = crm.get_platform_calendar_health(
            now_dt=now_dt,
            status_filter="recovery_overdue",
            recovery_target_minutes=60,
        )
        overdue_company = next(
            item
            for item in overdue_health["items"]
            if item["company_id"] == company_id
        )
        assert overdue_company["priority_code"] == "critical"
        assert overdue_company["recovery_overdue"] is True
        assert overdue_company["recovery_age_minutes"] == 110
        assert overdue_company["recovery_overdue_notified"] is True
        assert overdue_health["summary"]["recovery_overdue"] >= 1
        previous_recovery_policy = os.environ.get(
            "CALENDAR_INCIDENT_RECOVERY_MINUTES"
        )
        os.environ["CALENDAR_INCIDENT_RECOVERY_MINUTES"] = "60"

        try:
            overdue_page = await crm.platform_calendar_health_page(
                make_asgi_request(
                    "super",
                    "/platform/calendar-health",
                ),
                status="recovery_overdue",
            )
            overdue_detail_page = (
                await crm.platform_calendar_company_health_page(
                    make_asgi_request(
                        "super",
                        f"/platform/calendar-health/{company_id}",
                    ),
                    company_id,
                )
            )
        finally:
            if previous_recovery_policy is None:
                os.environ.pop(
                    "CALENDAR_INCIDENT_RECOVERY_MINUTES",
                    None,
                )
            else:
                os.environ[
                    "CALENDAR_INCIDENT_RECOVERY_MINUTES"
                ] = previous_recovery_policy

        assert "Восстановление просрочено" in (
            overdue_page.body.decode("utf-8")
        )
        assert "Восстановление просрочено" in (
            overdue_detail_page.body.decode("utf-8")
        )
        overdue_detail = crm.get_platform_calendar_company_detail(
            company_id,
            now_dt=now_dt,
        )
        assert overdue_detail["incidents"][0][
            "event_type_label"
        ] == "Восстановление просрочено"
        anonymous_recovery = (
            await crm.platform_calendar_incident_recover(
                make_public_asgi_request(
                    f"/platform/calendar-health/{company_id}/recover"
                ),
                company_id,
            )
        )
        assert anonymous_recovery.status_code == 302
        assert anonymous_recovery.headers["location"] == "/login"
        boss_recovery = (
            await crm.platform_calendar_incident_recover(
                make_asgi_request(
                    "owner2",
                    f"/platform/calendar-health/{company_id}/recover",
                ),
                company_id,
            )
        )
        assert boss_recovery.status_code == 302
        assert boss_recovery.headers["location"] == "/"
        wrong_assignee_recovery = (
            await crm.platform_calendar_incident_recover(
                make_form_request(
                    "super",
                    (
                        f"/platform/calendar-health/{company_id}"
                        "/recover"
                    ),
                    {
                        "recovery_note": (
                            "Проверка выполнена не ответственным."
                        ),
                    },
                ),
                company_id,
            )
        )
        assert wrong_assignee_recovery.headers["location"] == (
            f"/platform/calendar-health/{company_id}"
            "?error=incident_not_assignee"
        )
        empty_recovery_note = (
            await crm.platform_calendar_incident_recover(
                make_form_request(
                    backup_admin_username,
                    (
                        f"/platform/calendar-health/{company_id}"
                        "/recover"
                    ),
                    {"recovery_note": "   "},
                ),
                company_id,
            )
        )
        assert empty_recovery_note.headers["location"] == (
            f"/platform/calendar-health/{company_id}"
            "?error=recovery_note_required"
        )
        long_recovery_note = (
            await crm.platform_calendar_incident_recover(
                make_form_request(
                    backup_admin_username,
                    (
                        f"/platform/calendar-health/{company_id}"
                        "/recover"
                    ),
                    {"recovery_note": "x" * 501},
                ),
                company_id,
            )
        )
        assert long_recovery_note.headers["location"] == (
            f"/platform/calendar-health/{company_id}"
            "?error=recovery_note_too_long"
        )
        original_calendar_scheduler = crm.run_calendar_plan_scheduler
        successful_recovery_note = (
            "Проверены настройки окна и очередь запусков."
        )

        async def successful_platform_recovery(
            recovery_company_id,
            now_dt=None,
            actor_username="",
            source="scheduler",
        ):
            assert recovery_company_id == company_id
            assert actor_username == ""
            assert source == "manual_run"
            return {
                "error": "",
                "changed_days": 0,
                "notifications_sent": 0,
            }

        crm.run_calendar_plan_scheduler = successful_platform_recovery

        try:
            platform_recovery = (
                await crm.platform_calendar_incident_recover(
                    make_form_request(
                        backup_admin_username,
                        (
                            f"/platform/calendar-health/{company_id}"
                            "/recover"
                        ),
                        {
                            "recovery_note": (
                                successful_recovery_note
                            ),
                        },
                    ),
                    company_id,
                )
            )
        finally:
            crm.run_calendar_plan_scheduler = (
                original_calendar_scheduler
            )

        assert platform_recovery.status_code == 302
        assert platform_recovery.headers["location"] == (
            f"/platform/calendar-health/{company_id}"
            "?notice=recovered"
        )
        conn = connect()
        c = conn.cursor()
        recovered_status = c.execute("""
        SELECT
            active_incident,
            last_recovered_at,
            incident_acknowledged_at,
            incident_acknowledged_by,
            incident_assigned_at,
            incident_assigned_to,
            incident_assigned_by
        FROM calendar_plan_scheduler_status
        WHERE company_id=?
        """, (company_id,)).fetchone()
        recovery_events = c.execute("""
        SELECT event_type, actor_username, message
        FROM calendar_scheduler_incident_events
        WHERE company_id=?
        ORDER BY id
        """, (company_id,)).fetchall()
        conn.close()
        assert recovered_status["active_incident"] == ""
        assert recovered_status["last_recovered_at"]
        assert recovered_status["incident_acknowledged_at"] is None
        assert recovered_status["incident_acknowledged_by"] is None
        assert recovered_status["incident_assigned_at"] is None
        assert recovered_status["incident_assigned_to"] is None
        assert recovered_status["incident_assigned_by"] is None
        assert [
            (row["event_type"], row["actor_username"])
            for row in recovery_events
        ] == [
            ("opened", ""),
            ("acknowledged", "super"),
            ("note", "super"),
            ("reassigned", "super"),
            ("recovery_overdue", "watchdog"),
            ("recovery_started", backup_admin_username),
            ("recovered", backup_admin_username),
        ]
        assert successful_recovery_note in recovery_events[-2]["message"]
        assert successful_recovery_note in recovery_events[-1]["message"]
        recovered_detail = crm.get_platform_calendar_company_detail(
            company_id,
        )
        assert recovered_detail["incidents"][0][
            "event_type_label"
        ] == "Восстановлен"
        missing_incident_recovery = (
            await crm.platform_calendar_incident_recover(
                make_form_request(
                    backup_admin_username,
                    f"/platform/calendar-health/{company_id}/recover",
                    {"recovery_note": "Повторный запуск."},
                ),
                company_id,
            )
        )
        assert missing_incident_recovery.headers["location"] == (
            f"/platform/calendar-health/{company_id}"
            "?error=incident_not_found"
        )
        crm.open_calendar_scheduler_incident(
            company_id,
            "error",
            "Повторная ошибка для проверки неудачного восстановления.",
        )
        crm.acknowledge_calendar_scheduler_incident(
            company_id,
            "super",
        )
        failed_recovery_note = (
            "Проверена очередь, ошибка повторяется."
        )

        async def failed_platform_recovery(
            recovery_company_id,
            now_dt=None,
            actor_username="",
            source="scheduler",
        ):
            assert recovery_company_id == company_id
            assert actor_username == ""
            assert source == "manual_run"
            return {
                "error": "smoke_recovery_failure",
                "changed_days": 0,
                "notifications_sent": 0,
            }

        crm.run_calendar_plan_scheduler = failed_platform_recovery

        try:
            failed_recovery = (
                await crm.platform_calendar_incident_recover(
                    make_form_request(
                        "super",
                        (
                            f"/platform/calendar-health/{company_id}"
                            "/recover"
                        ),
                        {
                            "recovery_note": (
                                failed_recovery_note
                            ),
                        },
                    ),
                    company_id,
                )
            )
        finally:
            crm.run_calendar_plan_scheduler = (
                original_calendar_scheduler
            )

        assert failed_recovery.headers["location"] == (
            f"/platform/calendar-health/{company_id}"
            "?error=recovery_failed"
        )
        conn = connect()
        c = conn.cursor()
        failed_status = c.execute("""
        SELECT active_incident
        FROM calendar_plan_scheduler_status
        WHERE company_id=?
        """, (company_id,)).fetchone()
        failed_events = c.execute("""
        SELECT event_type, actor_username, message
        FROM calendar_scheduler_incident_events
        WHERE company_id=?
        ORDER BY id DESC
        LIMIT 2
        """, (company_id,)).fetchall()
        conn.close()
        assert failed_status["active_incident"] == "error"
        assert [row["event_type"] for row in failed_events] == [
            "recovery_failed",
            "recovery_started",
        ]
        assert all(
            row["actor_username"] == "super"
            for row in failed_events
        )
        assert all(
            failed_recovery_note in row["message"]
            for row in failed_events
        )
        failed_detail = crm.get_platform_calendar_company_detail(
            company_id,
        )
        assert failed_detail["incidents"][0][
            "event_type_label"
        ] == "Восстановление не выполнено"
        failed_page = (
            await crm.platform_calendar_company_health_page(
                make_asgi_request(
                    "super",
                    f"/platform/calendar-health/{company_id}",
                ),
                company_id,
                error="recovery_failed",
            )
        )
        assert (
            "Восстановление завершилось с ошибкой."
            in failed_page.body.decode("utf-8")
        )
        conn = connect()
        c = conn.cursor()
        c.execute("""
        UPDATE calendar_plan_scheduler_status
        SET incident_acknowledged_at=NULL,
            incident_acknowledged_by=NULL,
            incident_assigned_at=NULL,
            incident_assigned_to=NULL,
            incident_assigned_by=NULL
        WHERE company_id=?
        """, (company_id,))
        c.execute("""
        DELETE FROM calendar_scheduler_incident_events
        WHERE id=(
            SELECT id
            FROM calendar_scheduler_incident_events
            WHERE company_id=?
              AND event_type='acknowledged'
            ORDER BY id DESC
            LIMIT 1
        )
        """, (company_id,))
        conn.commit()
        conn.close()
        escalation_now = datetime.now() + timedelta(minutes=45)
        escalation_watchdog = crm.monitor_calendar_plan_schedulers(
            now_dt=escalation_now,
            company_id=company_id,
            escalation_after_minutes=30,
        )
        escalation = escalation_watchdog["escalation"]
        assert escalation_watchdog["escalated"] == 1
        assert (
            escalation_watchdog["escalation_notifications_sent"]
            == 2
        )
        assert escalation["checked"] == 1
        assert escalation["escalated"] == 1
        assert escalation["notifications_sent"] == 2
        assert escalation["items"][0]["company_id"] == company_id
        assert escalation["items"][0]["age_minutes"] == 45
        repeated_watchdog = (
            crm.monitor_calendar_plan_schedulers(
                now_dt=escalation_now + timedelta(minutes=10),
                company_id=company_id,
                escalation_after_minutes=30,
            )
        )
        repeated_escalation = repeated_watchdog["escalation"]
        assert repeated_watchdog["escalated"] == 0
        assert repeated_escalation["escalated"] == 0
        assert repeated_escalation["notifications_sent"] == 0
        conn = connect()
        c = conn.cursor()
        escalation_events = c.execute("""
        SELECT event_type, actor_username
        FROM calendar_scheduler_incident_events
        WHERE company_id=? AND event_type='escalated'
        """, (company_id,)).fetchall()
        platform_notifications = c.execute("""
        SELECT company_id, username, title, link
        FROM notifications
        WHERE username='super'
          AND title='Критический инцидент календаря'
          AND link=?
        """, (
            f"/platform/calendar-health/{company_id}",
        )).fetchall()
        conn.close()
        assert [
            (row["event_type"], row["actor_username"])
            for row in escalation_events
        ] == [("escalated", "watchdog")]
        assert len(platform_notifications) == 1
        assert platform_notifications[0]["company_id"] == 1
        assert platform_notifications[0]["title"] == (
            "Критический инцидент календаря"
        )
        escalated_health = crm.get_platform_calendar_health(
            now_dt=escalation_now,
            status_filter="problem",
        )
        escalated_company = next(
            item
            for item in escalated_health["items"]
            if item["company_id"] == company_id
        )
        assert escalated_company["is_escalated"] is True
        assert escalated_health["summary"]["escalated"] >= 1
        escalated_page = await crm.platform_calendar_health_page(
            make_asgi_request(
                "super",
                "/platform/calendar-health",
            ),
            status="problem",
        )
        assert "Передано платформе" in (
            escalated_page.body.decode("utf-8")
        )
        escalated_detail = crm.get_platform_calendar_company_detail(
            company_id,
        )
        assert escalated_detail["incidents"][0][
            "event_type_label"
        ] == "Передан платформе"
        analytics = crm.get_platform_calendar_incident_analytics(
            days=30,
            now_dt=escalation_now,
        )
        analytics_company = next(
            item
            for item in analytics["companies"]
            if item["company_id"] == company_id
        )
        assert analytics["days"] == 30
        assert analytics["policy"] == crm.get_calendar_incident_policy()
        assert analytics["summary"]["incidents"] >= 2
        assert analytics["summary"]["recovered"] >= 1
        assert analytics["summary"]["active"] >= 1
        assert analytics["summary"]["recovery_attempts"] >= 2
        assert analytics["summary"]["recovery_failures"] >= 1
        assert analytics["summary"]["escalations"] >= 1
        assert analytics["summary"]["recovery_sla_percent"] == 100
        assert analytics["summary"]["recovery_overdue"] == 0
        assert analytics["summary"]["recovery_overdue_events"] >= 1
        assert analytics_company["incidents"] == 2
        assert analytics_company["recovered"] == 1
        assert analytics_company["active"] == 1
        assert analytics_company["escalations"] == 1
        assert analytics_company["recovery_overdue"] == 0
        assert analytics_company["detail_url"] == (
            f"/platform/calendar-health/{company_id}"
        )
        assert any(
            item["type"] == "error"
            for item in analytics["types"]
        )
        assert analytics["daily"]
        assert analytics["recent_sessions"][0][
            "status_label"
        ] == "Передан платформе"
        normalized_analytics = (
            crm.get_platform_calendar_incident_analytics(
                days=11,
                now_dt=escalation_now,
            )
        )
        assert normalized_analytics["days"] == 30
        anonymous_analytics = (
            await crm.platform_calendar_incident_analytics_page(
                make_public_asgi_request(
                    "/platform/calendar-health/analytics"
                ),
            )
        )
        assert anonymous_analytics.status_code == 302
        assert anonymous_analytics.headers["location"] == "/login"
        boss_analytics = (
            await crm.platform_calendar_incident_analytics_page(
                make_asgi_request(
                    "owner2",
                    "/platform/calendar-health/analytics",
                ),
            )
        )
        assert boss_analytics.status_code == 302
        assert boss_analytics.headers["location"] == "/"
        analytics_page = (
            await crm.platform_calendar_incident_analytics_page(
                make_asgi_request(
                    "super",
                    "/platform/calendar-health/analytics",
                ),
                days=30,
            )
        )
        assert analytics_page.status_code == 200
        assert analytics_page.context["selected_days"] == 30
        analytics_html = analytics_page.body.decode("utf-8")
        assert "Аналитика календарных инцидентов" in analytics_html
        assert (
            "Реакция до "
            f"{analytics['policy']['response_minutes']} минут"
            in analytics_html
        )
        assert (
            "Восстановление до "
            f"{analytics['policy']['recovery_minutes']} минут"
            in analytics_html
        )
        assert "Среднее восстановление" in analytics_html
        assert "Последние инциденты" in analytics_html
        assert "Динамика" in analytics_html
        assert company_name in analytics_html
        missing_detail = (
            await crm.platform_calendar_company_health_page(
                make_asgi_request(
                    "super",
                    "/platform/calendar-health/999999",
                ),
                999999,
            )
        )
        assert missing_detail.status_code == 302
        assert missing_detail.headers["location"] == (
            "/platform/calendar-health?error=company_not_found"
        )
        platform_page = await crm.platform_dashboard(
            make_asgi_request("super", "/platform"),
        )
        assert "/platform/calendar-health" in (
            platform_page.body.decode("utf-8")
        )
    finally:
        conn = connect()
        c = conn.cursor()
        for bulk_company_id in bulk_company_ids:
            c.execute(
                "DELETE FROM calendar_plan_scheduler_status WHERE company_id=?",
                (bulk_company_id,),
            )
            c.execute(
                "DELETE FROM calendar_scheduler_incident_events WHERE company_id=?",
                (bulk_company_id,),
            )
            c.execute(
                "DELETE FROM calendar_plan_scheduler_runs WHERE company_id=?",
                (bulk_company_id,),
            )
            c.execute(
                "DELETE FROM calendar_plan_operation_runs WHERE company_id=?",
                (bulk_company_id,),
            )
            c.execute(
                "DELETE FROM notifications WHERE company_id=?",
                (bulk_company_id,),
            )
            c.execute(
                "DELETE FROM company_settings WHERE company_id=?",
                (bulk_company_id,),
            )
            c.execute(
                "DELETE FROM users WHERE company_id=?",
                (bulk_company_id,),
            )
            c.execute(
                "DELETE FROM companies WHERE id=?",
                (bulk_company_id,),
            )
        c.execute(
            "DELETE FROM calendar_plan_scheduler_status WHERE company_id=?",
            (company_id,),
        )
        c.execute(
            "DELETE FROM calendar_plan_scheduler_runs WHERE company_id=?",
            (company_id,),
        )
        c.execute(
            "DELETE FROM calendar_scheduler_incident_events WHERE company_id=?",
            (company_id,),
        )
        c.execute(
            "DELETE FROM calendar_plan_operation_runs WHERE company_id=?",
            (company_id,),
        )
        c.execute(
            "DELETE FROM notifications WHERE company_id=?",
            (company_id,),
        )
        c.execute("""
        DELETE FROM notifications
        WHERE username=? OR link=?
        """, (
            backup_admin_username,
            f"/platform/calendar-health/{company_id}",
        ))
        c.execute(
            "DELETE FROM users WHERE username=?",
            (backup_admin_username,),
        )
        c.execute(
            "DELETE FROM company_settings WHERE company_id=?",
            (company_id,),
        )
        c.execute(
            "DELETE FROM users WHERE company_id=?",
            (company_id,),
        )
        c.execute(
            "DELETE FROM companies WHERE id=?",
            (company_id,),
        )
        conn.commit()
        conn.close()


async def assert_daily_route_schedule():
    route_date = (
        datetime.now().date() + timedelta(days=42)
    ).strftime("%Y-%m-%d")
    created_at = datetime.now().strftime("%Y-%m-%d %H:%M")
    conn = connect()
    c = conn.cursor()
    task_values = [
        (
            2,
            "Route morning",
            "Daily route smoke",
            route_date,
            "worker2",
            "worker2",
            "09:00",
            "10:00",
        ),
        (
            2,
            "Route overlap",
            "Daily route smoke",
            route_date,
            "worker2",
            "worker2,helper2",
            "09:30",
            "10:30",
        ),
        (
            2,
            "Route without time",
            "Daily route smoke",
            route_date,
            "helper2",
            "helper2",
            "",
            "",
        ),
        (
            2,
            "Route unassigned",
            "Daily route smoke",
            route_date,
            "",
            "",
            "11:00",
            "12:00",
        ),
        (
            1,
            "Route outsider",
            "Other company",
            route_date,
            "outsider_worker",
            "outsider_worker",
            "09:00",
            "10:00",
        ),
    ]
    task_ids = []

    for values in task_values:
        c.execute("""
        INSERT INTO tasks (
            company_id, client, description, task_date,
            worker, workers, time_from, time_to,
            priority, status, archived, created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'Обычный', 'Новая', 0, ?)
        """, (*values, created_at))
        task_ids.append(c.lastrowid)

    morning_id, overlap_id, without_time_id, unassigned_id, outsider_id = (
        task_ids
    )
    conn.commit()
    conn.close()

    assert crm.normalize_time_window("09:00", "10:00") == (
        "09:00",
        "10:00",
        None,
    )
    assert crm.normalize_time_window("10:00", "09:00")[2]
    slot = find_common_time_slot(
        assignments=[
            {
                "date": route_date,
                "workers": ["worker2"],
                "time_from": "08:00",
                "time_to": "09:30",
            },
            {
                "date": route_date,
                "workers": ["helper2"],
                "time_from": "09:30",
                "time_to": "10:30",
            },
        ],
        target_date=route_date,
        target_workers=["worker2", "helper2"],
    )
    assert slot == {
        "time_from": "10:30",
        "time_to": "11:30",
        "duration_minutes": 60,
    }

    anonymous_page = await crm.calendar_day_route_page(
        make_public_asgi_request("/calendar/day"),
        date=route_date,
    )
    assert anonymous_page.status_code == 302
    assert anonymous_page.headers["location"] == "/login"

    owner_page = await crm.calendar_day_route_page(
        make_asgi_request("owner2", "/calendar/day"),
        date=route_date,
    )
    assert owner_page.status_code == 200
    owner_html = owner_page.body.decode("utf-8")
    assert "Маршрут дня" in owner_html
    assert "Route morning" in owner_html
    assert "Route overlap" in owner_html
    assert "Route without time" in owner_html
    assert "Route unassigned" in owner_html
    assert "Route outsider" not in owner_html
    assert "09:00–10:00" in owner_html
    assert f"#{overlap_id}" in owner_html
    assert "Пересечение:" in owner_html
    assert "Шкала рабочего дня" in owner_html
    assert "08:00–20:00 · шаг 30 минут" in owner_html
    assert "/api/calendar/day/move-time" in owner_html
    assert "/api/calendar/dispatch/plan/apply" in owner_html
    assert 'draggable="true"' in owner_html
    assert "Свободное окно" in owner_html
    assert "Рекомендуем:" in owner_html
    assert "Назначить" in owner_html
    assert "Автозаполнение дня" in owner_html
    assert "Применить план (2)" in owner_html
    assert "Автоисправление пересечений" in owner_html
    assert "Исправить пересечения (1)" in owner_html
    assert "ГОТОВНОСТЬ ДНЯ" in owner_html
    assert "Расписание нужно исправить до начала работ." in owner_html
    assert 'href="#conflict-repair"' in owner_html
    assert "План не опубликован" in owner_html
    assert 'id="publish-day-plan"' in owner_html
    assert 'id="publish-day-plan"\n                type="button"\n                disabled' in owner_html
    assert owner_page.context["day_publication"]["state"] == "draft"
    readiness = owner_page.context["day_readiness"]
    assert readiness["score"] == 35
    assert readiness["status"] == "Критично"
    assert readiness["issue_counts"] == {
        "conflicts": 2,
        "unassigned": 1,
        "without_time": 1,
        "inactive_workers": 0,
        "unavailable_workers": 0,
        "overloaded_workers": 0,
    }
    assert owner_page.context["schedule"]["summary"] == {
        "workers": 2,
        "tasks": 4,
        "scheduled": 3,
        "without_time": 1,
        "conflicts": 2,
        "unassigned": 1,
    }
    worker2_schedule = next(
        item
        for item in owner_page.context["schedule"]["workers"]
        if item["username"] == "worker2"
    )
    assert len(worker2_schedule["timeline"]["slots"]) == 24
    assert worker2_schedule["timeline"]["free_windows"][0]["label"] == (
        "08:00–09:00"
    )
    assert any(
        item["status"] == "conflict"
        and set(item["task_ids"]) == {morning_id, overlap_id}
        for item in worker2_schedule["timeline"]["slots"]
    )
    without_time_item = next(
        item
        for worker_schedule in owner_page.context["schedule"]["workers"]
        for item in worker_schedule["items"]
        if item["task_id"] == without_time_id
    )
    assert without_time_item["duration_minutes"] == 60
    assert without_time_item["available_slots"]
    assert without_time_item["available_slots"][0]["label"] == (
        "08:00–09:00"
    )
    unassigned_item = owner_page.context["schedule"]["unassigned"][0]
    assert unassigned_item["task_id"] == unassigned_id
    assert unassigned_item["assignment_suggestions"]
    assert unassigned_item["recommended_assignment"]["keeps_current_time"]
    assert unassigned_item["recommended_assignment"]["time_label"] == (
        "11:00–12:00"
    )
    day_auto_plan = owner_page.context["day_auto_plan"]
    assert day_auto_plan["summary"] == {
        "eligible": 2,
        "planned": 2,
        "unscheduled": 0,
        "limited": 0,
    }
    auto_plan_by_id = {
        item["task_id"]: item
        for item in day_auto_plan["items"]
    }
    assert set(auto_plan_by_id) == {
        without_time_id,
        unassigned_id,
    }
    assert auto_plan_by_id[without_time_id]["target_workers"] == [
        "helper2"
    ]
    assert auto_plan_by_id[without_time_id]["target_time_from"]
    assert auto_plan_by_id[unassigned_id]["target_time_label"] == (
        "11:00–12:00"
    )
    conflict_repair = owner_page.context["day_conflict_repair"]
    assert conflict_repair["summary"] == {
        "conflict_tasks": 1,
        "planned": 1,
        "unscheduled": 0,
        "limited": 0,
    }
    repair_item = conflict_repair["items"][0]
    assert repair_item["task_id"] == overlap_id
    assert repair_item["conflict_task_ids"] == [morning_id]
    assert repair_item["old_time_label"] == "09:30–10:30"
    assert repair_item["target_time_label"] == "10:00–11:00"

    anonymous_publication = await crm.api_calendar_day_publication(
        make_json_request(
            None,
            "/api/calendar/day/publication",
            {"date": route_date, "action": "publish"},
        )
    )
    assert anonymous_publication.status_code == 401
    worker_publication = await crm.api_calendar_day_publication(
        make_json_request(
            "worker2",
            "/api/calendar/day/publication",
            {"date": route_date, "action": "publish"},
        )
    )
    assert worker_publication.status_code == 403
    not_ready_publication = await crm.api_calendar_day_publication(
        make_json_request(
            "owner2",
            "/api/calendar/day/publication",
            {"date": route_date, "action": "publish"},
        )
    )
    assert not_ready_publication.status_code == 409
    not_ready_payload = json.loads(
        not_ready_publication.body.decode("utf-8")
    )
    assert not_ready_payload["error"] == "day_not_ready"
    assert not_ready_payload["score"] == 35
    anonymous_acknowledgement = await crm.api_calendar_day_acknowledge(
        make_json_request(
            None,
            "/api/calendar/day/acknowledge",
            {"date": route_date},
        )
    )
    assert anonymous_acknowledgement.status_code == 401
    owner_acknowledgement = await crm.api_calendar_day_acknowledge(
        make_json_request(
            "owner2",
            "/api/calendar/day/acknowledge",
            {"date": route_date},
        )
    )
    assert owner_acknowledgement.status_code == 403
    unpublished_acknowledgement = (
        await crm.api_calendar_day_acknowledge(
            make_json_request(
                "worker2",
                "/api/calendar/day/acknowledge",
                {"date": route_date},
            )
        )
    )
    assert unpublished_acknowledgement.status_code == 404
    anonymous_reminder = (
        await crm.api_calendar_day_acknowledgements_remind(
            make_json_request(
                None,
                "/api/calendar/day/acknowledgements/remind",
                {"date": route_date},
            )
        )
    )
    assert anonymous_reminder.status_code == 401
    worker_reminder = (
        await crm.api_calendar_day_acknowledgements_remind(
            make_json_request(
                "worker2",
                "/api/calendar/day/acknowledgements/remind",
                {"date": route_date},
            )
        )
    )
    assert worker_reminder.status_code == 403
    unpublished_reminder = (
        await crm.api_calendar_day_acknowledgements_remind(
            make_json_request(
                "owner2",
                "/api/calendar/day/acknowledgements/remind",
                {"date": route_date},
            )
        )
    )
    assert unpublished_reminder.status_code == 404

    filtered_page = await crm.calendar_day_route_page(
        make_asgi_request("owner2", "/calendar/day"),
        date=route_date,
        worker="helper2",
    )
    filtered_html = filtered_page.body.decode("utf-8")
    assert "Route overlap" in filtered_html
    assert "Route without time" in filtered_html
    assert "Route morning" not in filtered_html
    assert "Route unassigned" not in filtered_html
    assert "Автозаполнение дня" not in filtered_html
    assert "Автоисправление пересечений" not in filtered_html
    assert all(
        issue["target"] == "#day-routes"
        for issue in filtered_page.context["day_readiness"]["issues"]
    )
    assert (
        filtered_page.context["day_readiness"]["issue_counts"][
            "inactive_workers"
        ]
        == 0
    )

    worker_page = await crm.calendar_day_route_page(
        make_asgi_request("worker2", "/calendar/day"),
        date=route_date,
        worker="helper2",
    )
    worker_html = worker_page.body.decode("utf-8")
    assert "Route morning" in worker_html
    assert "Route overlap" in worker_html
    assert "Route without time" not in worker_html
    assert 'class="schedule-form"' not in worker_html
    assert f'data-task-id="{morning_id}"' not in worker_html
    assert "/api/calendar/day/move-time" not in worker_html
    assert "Автозаполнение дня" not in worker_html
    assert "Автоисправление пересечений" not in worker_html
    assert "План не опубликован" in worker_html
    assert 'id="publish-day-plan"' not in worker_html
    assert all(
        issue["target"] == "#day-routes"
        for issue in worker_page.context["day_readiness"]["issues"]
    )
    assert (
        worker_page.context["day_readiness"]["issue_counts"][
            "inactive_workers"
        ]
        == 0
    )

    outsider_page = await crm.calendar_day_route_page(
        make_asgi_request("outsider_worker", "/calendar/day"),
        date=route_date,
    )
    outsider_html = outsider_page.body.decode("utf-8")
    assert "Route outsider" in outsider_html
    assert "Route morning" not in outsider_html

    conflicts, summary = crm.get_company_schedule_conflicts(
        2,
        route_date,
        route_date,
    )
    overlap_conflicts = [
        conflict
        for conflict in conflicts
        if conflict["task_id"] in (morning_id, overlap_id)
    ]
    assert len(overlap_conflicts) == 2
    assert summary["time_overlap"] >= 2
    assert all(
        any(
            issue["type"] == "time_overlap"
            for issue in conflict["issues"]
        )
        for conflict in overlap_conflicts
    )
    conflict_page = await crm.calendar_conflicts_page(
        make_asgi_request("owner2", "/calendar/conflicts"),
        days=60,
        conflict_type="time_overlap",
    )
    assert conflict_page.status_code == 200
    assert "Пересечение времени" in conflict_page.body.decode("utf-8")

    move_payload = {
        "task_id": without_time_id,
        "target_date": route_date,
        "target_time_from": "11:00",
        "expected_date": route_date,
        "expected_time_from": "",
        "expected_time_to": "",
    }
    anonymous_move = await crm.api_calendar_day_move_time(
        make_json_request(
            None,
            "/api/calendar/day/move-time",
            move_payload,
        )
    )
    assert anonymous_move.status_code == 401
    worker_move = await crm.api_calendar_day_move_time(
        make_json_request(
            "helper2",
            "/api/calendar/day/move-time",
            move_payload,
        )
    )
    assert worker_move.status_code == 403
    invalid_time_move = await crm.api_calendar_day_move_time(
        make_json_request(
            "owner2",
            "/api/calendar/day/move-time",
            {
                **move_payload,
                "target_time_from": "11:15",
            },
        )
    )
    assert invalid_time_move.status_code == 400
    assert json.loads(invalid_time_move.body)["error"] == "invalid_time"
    stale_move = await crm.api_calendar_day_move_time(
        make_json_request(
            "owner2",
            "/api/calendar/day/move-time",
            {
                **move_payload,
                "expected_time_from": "08:00",
            },
        )
    )
    assert stale_move.status_code == 409
    assert json.loads(stale_move.body)["error"] == "stale"
    outsider_move = await crm.api_calendar_day_move_time(
        make_json_request(
            "owner2",
            "/api/calendar/day/move-time",
            {
                **move_payload,
                "task_id": outsider_id,
            },
        )
    )
    assert outsider_move.status_code == 404
    conflict_move = await crm.api_calendar_day_move_time(
        make_json_request(
            "owner2",
            "/api/calendar/day/move-time",
            {
                **move_payload,
                "target_time_from": "10:00",
            },
        )
    )
    assert conflict_move.status_code == 409
    conflict_move_data = json.loads(conflict_move.body)
    assert conflict_move_data["error"] == "time_conflict"
    assert conflict_move_data["conflicts"][0]["task_id"] == overlap_id
    assert conflict_move_data["suggestions"]
    assert conflict_move_data["suggestions"][0]["label"] == (
        "08:00–09:00"
    )

    original_send_message_to_chat = crm.send_message_to_chat
    route_telegram_messages = []
    crm.send_message_to_chat = (
        lambda chat_id, text: route_telegram_messages.append(
            (chat_id, text)
        )
    )

    try:
        moved_time = await crm.api_calendar_day_move_time(
            make_json_request(
                "owner2",
                "/api/calendar/day/move-time",
                move_payload,
            )
        )
    finally:
        crm.send_message_to_chat = original_send_message_to_chat

    assert moved_time["ok"] is True
    assert moved_time["changed"] is True
    assert moved_time["target_time_from"] == "11:00"
    assert moved_time["target_time_to"] == "12:00"
    assert route_telegram_messages == [
        (
            "chat-helper2",
            (
                f"Изменено расписание заявки #{without_time_id}\n"
                "Клиент: Route without time\n"
                f"Дата: {route_date}\n"
                "Время: 11:00–12:00"
            ),
        )
    ]
    conn = connect()
    c = conn.cursor()
    moved_time_row = c.execute("""
    SELECT time_from, time_to
    FROM tasks
    WHERE id=? AND company_id=2
    """, (without_time_id,)).fetchone()
    route_activity = c.execute("""
    SELECT details
    FROM task_activity
    WHERE task_id=?
      AND action='Время изменено на маршруте дня'
    ORDER BY id DESC
    LIMIT 1
    """, (without_time_id,)).fetchone()
    route_notification = c.execute("""
    SELECT message
    FROM notifications
    WHERE company_id=2
      AND username='helper2'
      AND title=?
    ORDER BY id DESC
    LIMIT 1
    """, (
        f"Изменено расписание заявки #{without_time_id}",
    )).fetchone()
    conn.close()
    assert moved_time_row["time_from"] == "11:00"
    assert moved_time_row["time_to"] == "12:00"
    assert "11:00–12:00" in route_activity["details"]
    assert route_notification["message"] == (
        f"{route_date}, 11:00–12:00"
    )

    invalid_time = await crm.update_task_date(
        make_form_request(
            "owner2",
            f"/task/{without_time_id}/date",
            {
                "task_date": route_date,
                "time_from": "12:00",
                "time_to": "11:00",
            },
        ),
        without_time_id,
    )
    assert invalid_time.headers["location"] == (
        f"/task/{without_time_id}?date_error=invalid_time"
    )

    overlap_update = await crm.update_task_date(
        make_form_request(
            "owner2",
            f"/task/{without_time_id}/date",
            {
                "task_date": route_date,
                "time_from": "10:00",
                "time_to": "11:00",
            },
        ),
        without_time_id,
    )
    assert overlap_update.headers["location"] == (
        f"/task/{without_time_id}?date_error=time_conflict"
        f"&conflict_task_id={overlap_id}"
    )

    original_send_message = crm.send_message
    original_send_message_to_chat = crm.send_message_to_chat
    crm.send_message = lambda text: True
    crm.send_message_to_chat = lambda chat_id, text: True

    try:
        valid_update = await crm.update_task_date(
            make_form_request(
                "owner2",
                f"/task/{without_time_id}/date",
                {
                    "task_date": route_date,
                    "time_from": "10:30",
                    "time_to": "11:30",
                    "return_to": (
                        f"/calendar/day?date={route_date}&worker=helper2"
                    ),
                },
            ),
            without_time_id,
        )
    finally:
        crm.send_message = original_send_message
        crm.send_message_to_chat = original_send_message_to_chat

    assert valid_update.headers["location"] == (
        f"/calendar/day?date={route_date}&worker=helper2"
    )
    conn = connect()
    c = conn.cursor()
    updated = c.execute("""
    SELECT time_from, time_to
    FROM tasks
    WHERE id=? AND company_id=2
    """, (without_time_id,)).fetchone()
    activity = c.execute("""
    SELECT details
    FROM task_activity
    WHERE task_id=? AND action='Расписание заявки изменено'
    ORDER BY id DESC
    LIMIT 1
    """, (without_time_id,)).fetchone()
    assert updated["time_from"] == "10:30"
    assert updated["time_to"] == "11:30"
    assert "10:30–11:30" in activity["details"]
    conn.close()

    assignment_page = await crm.calendar_day_route_page(
        make_asgi_request("owner2", "/calendar/day"),
        date=route_date,
    )
    assignment_item = next(
        item
        for item in assignment_page.context["schedule"]["unassigned"]
        if item["task_id"] == unassigned_id
    )
    recommendation = assignment_item["recommended_assignment"]
    assert recommendation
    stale_assignment = await crm.api_calendar_dispatch_plan_apply(
        make_json_request(
            "owner2",
            "/api/calendar/dispatch/plan/apply",
            {
                "items": [{
                    "task_id": unassigned_id,
                    "current_date": route_date,
                    "expected_workers": "",
                    "expected_time_from": "10:00",
                    "expected_time_to": "11:00",
                    "target_date": route_date,
                    "target_workers": [recommendation["worker"]],
                    "target_time_from": recommendation["time_from"],
                    "target_time_to": recommendation["time_to"],
                }],
            },
        )
    )
    assert stale_assignment["summary"]["applied"] == 0
    assert "изменилась после расчёта" in (
        stale_assignment["skipped"][0]["reason"]
    )
    original_send_message_to_chat = crm.send_message_to_chat
    assignment_messages = []
    crm.send_message_to_chat = (
        lambda chat_id, text: assignment_messages.append(
            (chat_id, text)
        )
    )

    try:
        assignment_result = await crm.api_calendar_dispatch_plan_apply(
            make_json_request(
                "owner2",
                "/api/calendar/dispatch/plan/apply",
                {
                    "items": [{
                        "task_id": unassigned_id,
                        "current_date": route_date,
                        "expected_workers": "",
                        "expected_time_from": "11:00",
                        "expected_time_to": "12:00",
                        "target_date": route_date,
                        "target_workers": [recommendation["worker"]],
                        "target_time_from": recommendation["time_from"],
                        "target_time_to": recommendation["time_to"],
                    }],
                },
            )
        )
    finally:
        crm.send_message_to_chat = original_send_message_to_chat

    assert assignment_result["summary"] == {
        "requested": 1,
        "applied": 1,
        "skipped": 0,
    }
    conn = connect()
    c = conn.cursor()
    assigned = c.execute("""
    SELECT worker, workers, time_from, time_to
    FROM tasks
    WHERE id=? AND company_id=2
    """, (unassigned_id,)).fetchone()
    assignment_activity = c.execute("""
    SELECT details
    FROM task_activity
    WHERE task_id=?
      AND action='Применён автоматический план'
    ORDER BY id DESC
    LIMIT 1
    """, (unassigned_id,)).fetchone()
    assert assigned["worker"] == recommendation["worker"]
    assert assigned["workers"] == recommendation["worker"]
    assert assigned["time_from"] == recommendation["time_from"]
    assert assigned["time_to"] == recommendation["time_to"]
    assert recommendation["worker"] in assignment_activity["details"]

    c.execute("""
    UPDATE tasks
    SET time_from='', time_to=''
    WHERE id=? AND company_id=2
    """, (without_time_id,))
    c.execute("""
    UPDATE tasks
    SET worker='', workers='', time_from='11:00', time_to='12:00'
    WHERE id=? AND company_id=2
    """, (unassigned_id,))
    conn.commit()
    conn.close()
    bulk_plan_page = await crm.calendar_day_route_page(
        make_asgi_request("owner2", "/calendar/day"),
        date=route_date,
    )
    bulk_plan = bulk_plan_page.context["day_auto_plan"]
    assert bulk_plan["summary"]["planned"] == 2
    assert {
        item["task_id"]
        for item in bulk_plan["items"]
    } == {without_time_id, unassigned_id}
    bulk_result = await crm.api_calendar_dispatch_plan_apply(
        make_json_request(
            "owner2",
            "/api/calendar/dispatch/plan/apply",
            {"items": bulk_plan["items"]},
        )
    )
    assert bulk_result["summary"] == {
        "requested": 2,
        "applied": 2,
        "skipped": 0,
    }
    conn = connect()
    c = conn.cursor()
    bulk_rows = c.execute("""
    SELECT id, worker, workers, time_from, time_to
    FROM tasks
    WHERE id IN (?, ?)
    ORDER BY id
    """, (without_time_id, unassigned_id)).fetchall()
    assert all(row["workers"] for row in bulk_rows)
    assert all(row["time_from"] and row["time_to"] for row in bulk_rows)
    conn.close()

    repair_page = await crm.calendar_day_route_page(
        make_asgi_request("owner2", "/calendar/day"),
        date=route_date,
    )
    repair_plan = repair_page.context["day_conflict_repair"]
    assert repair_plan["summary"]["planned"] == 1
    repair_result = await crm.api_calendar_dispatch_plan_apply(
        make_json_request(
            "owner2",
            "/api/calendar/dispatch/plan/apply",
            {"items": repair_plan["items"]},
        )
    )
    assert repair_result["summary"] == {
        "requested": 1,
        "applied": 1,
        "skipped": 0,
    }
    conn = connect()
    c = conn.cursor()
    repaired_overlap = c.execute("""
    SELECT time_from, time_to
    FROM tasks
    WHERE id=? AND company_id=2
    """, (overlap_id,)).fetchone()
    assert repaired_overlap["time_from"] == "10:00"
    assert repaired_overlap["time_to"] == "11:00"
    remaining_conflicts, _ = crm.get_company_schedule_conflicts(
        2,
        route_date,
        route_date,
    )
    assert not any(
        conflict["task_id"] in (morning_id, overlap_id)
        and any(
            issue["type"] == "time_overlap"
            for issue in conflict["issues"]
        )
        for conflict in remaining_conflicts
    )
    ready_page = await crm.calendar_day_route_page(
        make_asgi_request("owner2", "/calendar/day"),
        date=route_date,
    )
    ready_state = ready_page.context["day_readiness"]
    assert ready_state["score"] == 100
    assert ready_state["status"] == "Готово"
    assert not ready_state["issues"]
    assert "Расписание готово к работе." in (
        ready_page.body.decode("utf-8")
    )
    ready_html = ready_page.body.decode("utf-8")
    assert 'id="publish-day-plan"' in ready_html
    assert 'id="publish-day-plan"\n                type="button"\n                disabled' not in ready_html
    expected_publication_workers = set(
        ready_page.context["day_publication"]["workers"]
    )

    publication_result = await crm.api_calendar_day_publication(
        make_json_request(
            "owner2",
            "/api/calendar/day/publication",
            {"date": route_date, "action": "publish"},
        )
    )
    assert publication_result["ok"] is True
    assert publication_result["state"] == "published"
    assert publication_result["notified_workers"] == len(
        expected_publication_workers
    )
    first_published_worker_page = await crm.calendar_day_route_page(
        make_asgi_request("worker2", "/calendar/day"),
        date=route_date,
    )
    first_published_worker_html = (
        first_published_worker_page.body.decode("utf-8")
    )
    assert "Приняли: 0/" in first_published_worker_html
    assert 'id="acknowledge-day-plan"' in first_published_worker_html
    assert (
        first_published_worker_page.context["day_publication"][
            "current_user_acknowledged"
        ]
        is False
    )
    owner_pending_page = await crm.calendar_day_route_page(
        make_asgi_request("owner2", "/calendar/day"),
        date=route_date,
    )
    owner_pending_html = owner_pending_page.body.decode("utf-8")
    assert 'id="remind-day-plan"' in owner_pending_html
    assert "Напомнить (" in owner_pending_html
    reminder_messages = []
    original_send_message_to_chat = crm.send_message_to_chat
    crm.send_message_to_chat = (
        lambda chat_id, text: reminder_messages.append((chat_id, text))
    )

    try:
        reminder_result = (
            await crm.api_calendar_day_acknowledgements_remind(
                make_json_request(
                    "owner2",
                    "/api/calendar/day/acknowledgements/remind",
                    {"date": route_date},
                )
            )
        )
    finally:
        crm.send_message_to_chat = original_send_message_to_chat

    assert set(reminder_result["sent"]) == expected_publication_workers
    assert not reminder_result["cooldown"]
    repeated_reminder = (
        await crm.api_calendar_day_acknowledgements_remind(
            make_json_request(
                "owner2",
                "/api/calendar/day/acknowledgements/remind",
                {"date": route_date},
            )
        )
    )
    assert not repeated_reminder["sent"]
    assert set(
        repeated_reminder["cooldown"]
    ) == expected_publication_workers
    expired_reminder_at = (
        datetime.now() - timedelta(minutes=31)
    ).strftime("%Y-%m-%d %H:%M")
    conn = connect()
    c = conn.cursor()
    c.execute("""
    UPDATE calendar_day_ack_reminders
    SET reminded_at=?
    WHERE company_id=2 AND plan_date=? AND revision=1
    """, (expired_reminder_at, route_date))
    conn.commit()
    conn.close()
    crm.send_message_to_chat = lambda chat_id, text: True

    try:
        renewed_reminder = (
            await crm.api_calendar_day_acknowledgements_remind(
                make_json_request(
                    "owner2",
                    "/api/calendar/day/acknowledgements/remind",
                    {"date": route_date},
                )
            )
        )
    finally:
        crm.send_message_to_chat = original_send_message_to_chat

    assert set(
        renewed_reminder["sent"]
    ) == expected_publication_workers
    assert not renewed_reminder["cooldown"]
    reminded_page = await crm.calendar_day_route_page(
        make_asgi_request("owner2", "/calendar/day"),
        date=route_date,
    )
    reminded_html = reminded_page.body.decode("utf-8")
    assert "Напоминание отправлено" in reminded_html
    assert "напомнили " in reminded_html
    assert (
        reminded_page.context["day_publication"][
            "remindable_count"
        ]
        == 0
    )
    acknowledgement_result = await crm.api_calendar_day_acknowledge(
        make_json_request(
            "worker2",
            "/api/calendar/day/acknowledge",
            {"date": route_date},
        )
    )
    assert acknowledgement_result["ok"] is True
    assert acknowledgement_result["revision"] == 1
    conn = connect()
    c = conn.cursor()
    published_row = c.execute("""
    SELECT *
    FROM calendar_day_publications
    WHERE company_id=2 AND plan_date=?
    """, (route_date,)).fetchone()
    publication_notifications = c.execute("""
    SELECT username, title, is_read
    FROM notifications
    WHERE company_id=2
      AND link=?
      AND title='План дня опубликован'
    ORDER BY username
    """, (f"/calendar/day?date={route_date}",)).fetchall()
    assert published_row["revision"] == 1
    assert published_row["task_count"] == 4
    assert {
        row["username"] for row in publication_notifications
    } == expected_publication_workers
    assert all(
        row["title"] == "План дня опубликован"
        for row in publication_notifications
    )
    worker_acknowledgement = c.execute("""
    SELECT *
    FROM calendar_day_acknowledgements
    WHERE company_id=2
      AND plan_date=?
      AND revision=1
      AND username='worker2'
    """, (route_date,)).fetchone()
    assert worker_acknowledgement is not None
    worker_publication_notification = next(
        row
        for row in publication_notifications
        if row["username"] == "worker2"
    )
    assert worker_publication_notification["is_read"] == 1
    worker_reminder_notification = c.execute("""
    SELECT is_read
    FROM notifications
    WHERE company_id=2
      AND username='worker2'
      AND link=?
      AND title='Подтвердите план дня'
    ORDER BY id DESC
    LIMIT 1
    """, (f"/calendar/day?date={route_date}",)).fetchone()
    assert worker_reminder_notification["is_read"] == 1
    reminder_history_count = c.execute("""
    SELECT COUNT(*)
    FROM calendar_day_ack_reminders
    WHERE company_id=2
      AND plan_date=?
      AND revision=1
    """, (route_date,)).fetchone()[0]
    assert reminder_history_count == (
        len(expected_publication_workers) * 2
    )
    acknowledged_worker_page = await crm.calendar_day_route_page(
        make_asgi_request("worker2", "/calendar/day"),
        date=route_date,
    )
    acknowledged_worker_html = (
        acknowledged_worker_page.body.decode("utf-8")
    )
    assert "План принят вами" in acknowledged_worker_html
    assert 'id="acknowledge-day-plan"' not in acknowledged_worker_html
    acknowledged_owner_page = await crm.calendar_day_route_page(
        make_asgi_request("owner2", "/calendar/day"),
        date=route_date,
    )
    acknowledged_owner_html = (
        acknowledged_owner_page.body.decode("utf-8")
    )
    assert "Приняли: 1/" in acknowledged_owner_html
    assert "confirmation-chip confirmed" in acknowledged_owner_html
    outsider_unpublish = await crm.api_calendar_day_publication(
        make_json_request(
            "manager1",
            "/api/calendar/day/publication",
            {"date": route_date, "action": "unpublish"},
        )
    )
    assert outsider_unpublish.status_code == 404
    assert c.execute("""
    SELECT COUNT(*)
    FROM calendar_day_publications
    WHERE company_id=2 AND plan_date=?
    """, (route_date,)).fetchone()[0] == 1
    c.execute("""
    UPDATE tasks
    SET time_from='19:00', time_to='20:00'
    WHERE id=? AND company_id=2
    """, (overlap_id,))
    conn.commit()
    conn.close()

    changed_page = await crm.calendar_day_route_page(
        make_asgi_request("owner2", "/calendar/day"),
        date=route_date,
    )
    changed_html = changed_page.body.decode("utf-8")
    assert changed_page.context["day_publication"]["state"] == "changed"
    assert "После публикации есть изменения" in changed_html
    assert "Обновить публикацию" in changed_html
    assert "Снять публикацию" in changed_html
    changed_acknowledgement = await crm.api_calendar_day_acknowledge(
        make_json_request(
            "worker2",
            "/api/calendar/day/acknowledge",
            {"date": route_date},
        )
    )
    assert changed_acknowledgement.status_code == 409
    assert json.loads(
        changed_acknowledgement.body.decode("utf-8")
    )["error"] == "plan_changed"
    changed_reminder = (
        await crm.api_calendar_day_acknowledgements_remind(
            make_json_request(
                "owner2",
                "/api/calendar/day/acknowledgements/remind",
                {"date": route_date},
            )
        )
    )
    assert changed_reminder.status_code == 409
    assert json.loads(
        changed_reminder.body.decode("utf-8")
    )["error"] == "plan_changed"

    republish_result = await crm.api_calendar_day_publication(
        make_json_request(
            "owner2",
            "/api/calendar/day/publication",
            {"date": route_date, "action": "publish"},
        )
    )
    assert republish_result["state"] == "published"
    conn = connect()
    c = conn.cursor()
    republished_row = c.execute("""
    SELECT revision
    FROM calendar_day_publications
    WHERE company_id=2 AND plan_date=?
    """, (route_date,)).fetchone()
    assert republished_row["revision"] == 2
    conn.close()

    published_worker_page = await crm.calendar_day_route_page(
        make_asgi_request("worker2", "/calendar/day"),
        date=route_date,
    )
    published_worker_html = published_worker_page.body.decode("utf-8")
    assert "План опубликован" in published_worker_html
    assert 'id="unpublish-day-plan"' not in published_worker_html
    assert "Приняли: 0/" in published_worker_html
    assert 'id="acknowledge-day-plan"' in published_worker_html
    assert "План принят вами" not in published_worker_html
    republished_owner_page = await crm.calendar_day_route_page(
        make_asgi_request("owner2", "/calendar/day"),
        date=route_date,
    )
    assert (
        republished_owner_page.context["day_publication"][
            "remindable_count"
        ]
        == len(expected_publication_workers)
    )
    second_acknowledgement = await crm.api_calendar_day_acknowledge(
        make_json_request(
            "worker2",
            "/api/calendar/day/acknowledge",
            {"date": route_date},
        )
    )
    assert second_acknowledgement["revision"] == 2
    conn = connect()
    c = conn.cursor()
    acknowledgement_revisions = c.execute("""
    SELECT revision
    FROM calendar_day_acknowledgements
    WHERE company_id=2
      AND plan_date=?
      AND username='worker2'
    ORDER BY revision
    """, (route_date,)).fetchall()
    assert [
        row["revision"] for row in acknowledgement_revisions
    ] == [1, 2]
    conn.close()

    unpublish_result = await crm.api_calendar_day_publication(
        make_json_request(
            "owner2",
            "/api/calendar/day/publication",
            {"date": route_date, "action": "unpublish"},
        )
    )
    assert unpublish_result["state"] == "draft"
    conn = connect()
    c = conn.cursor()
    assert c.execute("""
    SELECT COUNT(*)
    FROM calendar_day_publications
    WHERE company_id=2 AND plan_date=?
    """, (route_date,)).fetchone()[0] == 0
    assert c.execute("""
    SELECT COUNT(*)
    FROM calendar_day_acknowledgements
    WHERE company_id=2 AND plan_date=?
    """, (route_date,)).fetchone()[0] == 0
    assert c.execute("""
    SELECT COUNT(*)
    FROM calendar_day_ack_reminders
    WHERE company_id=2 AND plan_date=?
    """, (route_date,)).fetchone()[0] == 0
    conn.close()

    empty_readiness = build_day_readiness(
        tasks=[],
        worker_names=["worker2"],
        worker_capacities={"worker2": 3},
    )
    assert empty_readiness["score"] == 100
    assert empty_readiness["status"] == "День свободен"

    conn = connect()
    c = conn.cursor()
    placeholders = ",".join("?" for _ in task_ids)
    c.execute(
        "DELETE FROM calendar_day_publications WHERE plan_date=?",
        (route_date,),
    )
    c.execute(
        "DELETE FROM calendar_day_acknowledgements WHERE plan_date=?",
        (route_date,),
    )
    c.execute(
        "DELETE FROM calendar_day_ack_reminders WHERE plan_date=?",
        (route_date,),
    )
    c.execute(
        "DELETE FROM notifications WHERE link=?",
        (f"/calendar/day?date={route_date}",),
    )
    c.execute(
        f"DELETE FROM task_activity WHERE task_id IN ({placeholders})",
        task_ids,
    )
    c.execute(
        f"DELETE FROM notifications WHERE link IN ({placeholders})",
        [f"/task/{task_id}" for task_id in task_ids],
    )
    c.execute(
        f"DELETE FROM tasks WHERE id IN ({placeholders})",
        task_ids,
    )
    conn.commit()
    conn.close()


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
    INSERT INTO users (
        username, password, role, company_id, telegram_chat_id
    )
    VALUES (?, ?, 'worker', 2, ?)
    """, (
        "inactive_candidate2",
        "x",
        "chat-inactive-candidate2",
    ))
    inactive_candidate = c.execute("""
    SELECT id
    FROM users
    WHERE company_id=2 AND username='inactive_candidate2'
    """).fetchone()
    c.executemany("""
    INSERT INTO users (
        username, password, role, company_id, telegram_chat_id
    )
    VALUES (?, ?, 'worker', 2, '')
    """, [
        ("delete_candidate2", "x"),
        ("history_candidate2", "x"),
    ])
    delete_candidate = c.execute("""
    SELECT id
    FROM users
    WHERE company_id=2 AND username='delete_candidate2'
    """).fetchone()
    history_candidate = c.execute("""
    SELECT id
    FROM users
    WHERE company_id=2 AND username='history_candidate2'
    """).fetchone()
    c.execute("""
    INSERT INTO tasks (
        company_id, client, description, task_date,
        worker, workers, status, archived
    )
    VALUES (2, 'History client', 'Archived history', '2026-01-01',
            'history_candidate2', 'history_candidate2', 'Завершено', 1)
    """)
    c.execute("""
    UPDATE users
    SET commission_percent=10
    WHERE company_id=2 AND username='helper2'
    """)
    conn.commit()
    conn.close()

    invalid_role_response = await crm.create_worker(
        make_form_request(
            "owner2",
            "/workers",
            {
                "username": "forged_admin",
                "password": "strong123",
                "role": "superadmin",
            },
        )
    )
    assert invalid_role_response.status_code == 302
    assert invalid_role_response.headers["location"] == "/workers?error=invalid_role"

    weak_password_response = await crm.create_worker(
        make_form_request(
            "owner2",
            "/workers",
            {
                "username": "weak_worker",
                "password": "123",
                "role": "worker",
            },
        )
    )
    assert weak_password_response.status_code == 302
    assert weak_password_response.headers["location"] == "/workers?error=weak_password"

    created_worker_response = await crm.create_worker(
        make_form_request(
            "owner2",
            "/workers",
            {
                "username": "audit_manager2",
                "password": "strong123",
                "role": "manager",
                "full_name": "Аудит Менеджер",
            },
        )
    )
    assert created_worker_response.status_code == 302
    assert created_worker_response.headers["location"] == "/workers?created=1"

    conn = connect()
    c = conn.cursor()
    assert c.execute("""
    SELECT id
    FROM users
    WHERE username IN ('forged_admin', 'weak_worker')
    """).fetchone() is None
    created_worker = c.execute("""
    SELECT id
    FROM users
    WHERE company_id=2 AND username='audit_manager2'
    """).fetchone()
    created_worker_activity = c.execute("""
    SELECT action, details, actor_username
    FROM team_activity
    WHERE company_id=2 AND user_id=?
    ORDER BY id DESC
    LIMIT 1
    """, (created_worker["id"],)).fetchone()
    assert created_worker_activity["action"] == "Пользователь создан"
    assert created_worker_activity["details"] == "Роль: Менеджер"
    assert created_worker_activity["actor_username"] == "owner2"
    c.execute("DELETE FROM users WHERE id=?", (created_worker["id"],))
    conn.commit()
    outsider = c.execute("""
    SELECT id, password
    FROM users
    WHERE company_id=1 AND username='outsider_worker'
    """).fetchone()
    conn.close()

    cross_company_password_response = await crm.change_team_user_password(
        make_form_request(
            "owner2",
            f"/workers/{outsider['id']}/password",
            {"password": "changed123"},
        ),
        outsider["id"],
    )
    assert cross_company_password_response.status_code == 302
    assert cross_company_password_response.headers["location"] == "/workers"

    cross_company_profile_response = await crm.update_team_user_profile(
        make_form_request(
            "owner2",
            f"/workers/{outsider['id']}/profile",
            {
                "full_name": "Подменённое имя",
                "position": "",
                "phone": "",
                "email": "",
                "telegram_chat_id": "",
            },
        ),
        outsider["id"],
    )
    assert cross_company_profile_response.status_code == 302
    assert cross_company_profile_response.headers["location"] == "/workers"

    conn = connect()
    c = conn.cursor()
    unchanged_outsider = c.execute("""
    SELECT password, full_name
    FROM users
    WHERE id=?
    """, (outsider["id"],)).fetchone()
    conn.close()
    assert unchanged_outsider["password"] == outsider["password"]
    assert unchanged_outsider["full_name"] != "Подменённое имя"

    cross_company_delete_response = await crm.delete_team_user(
        make_form_request(
            "owner2",
            f"/workers/{outsider['id']}/delete",
            {},
        ),
        outsider["id"],
    )
    assert cross_company_delete_response.status_code == 302
    assert cross_company_delete_response.headers["location"] == "/workers"

    active_delete_response = await crm.delete_team_user(
        make_form_request(
            "owner2",
            f"/workers/{helper['id']}/delete",
            {},
        ),
        helper["id"],
    )
    assert active_delete_response.status_code == 302
    assert active_delete_response.headers["location"].startswith(
        "/workers?error=active_tasks&count="
    )

    active_clean_delete_response = await crm.delete_team_user(
        make_form_request(
            "owner2",
            f"/workers/{delete_candidate['id']}/delete",
            {},
        ),
        delete_candidate["id"],
    )
    assert active_clean_delete_response.status_code == 302
    assert (
        active_clean_delete_response.headers["location"]
        == "/workers?error=disable_before_delete"
    )

    history_toggle_response = await crm.toggle_team_user_active(
        make_form_request(
            "owner2",
            f"/workers/{history_candidate['id']}/toggle-active",
            {"disabled_reason": "Сотрудник уволен"},
        ),
        history_candidate["id"],
    )
    assert history_toggle_response.status_code == 302
    assert history_toggle_response.headers["location"] == "/workers?status_updated=1"

    conn = connect()
    c = conn.cursor()
    disabled_history_candidate = c.execute("""
    SELECT is_active, disabled_at, disabled_reason
    FROM users
    WHERE id=?
    """, (history_candidate["id"],)).fetchone()
    conn.close()
    assert disabled_history_candidate["is_active"] == 0
    assert disabled_history_candidate["disabled_at"]
    assert disabled_history_candidate["disabled_reason"] == "Сотрудник уволен"

    history_delete_response = await crm.delete_team_user(
        make_form_request(
            "owner2",
            f"/workers/{history_candidate['id']}/delete",
            {},
        ),
        history_candidate["id"],
    )
    assert history_delete_response.status_code == 302
    assert history_delete_response.headers["location"].startswith(
        "/workers?error=user_has_history&count="
    )

    history_reenable_response = await crm.toggle_team_user_active(
        make_form_request(
            "owner2",
            f"/workers/{history_candidate['id']}/toggle-active",
            {},
        ),
        history_candidate["id"],
    )
    assert history_reenable_response.status_code == 302
    assert history_reenable_response.headers["location"] == "/workers?status_updated=1"

    conn = connect()
    c = conn.cursor()
    reenabled_history_candidate = c.execute("""
    SELECT is_active, disabled_at, disabled_reason
    FROM users
    WHERE id=?
    """, (history_candidate["id"],)).fetchone()
    assert reenabled_history_candidate["is_active"] == 1
    assert reenabled_history_candidate["disabled_at"] is None
    assert reenabled_history_candidate["disabled_reason"] is None
    history_activity = c.execute("""
    SELECT action, details, actor_username
    FROM team_activity
    WHERE company_id=2 AND user_id=?
    ORDER BY id
    """, (history_candidate["id"],)).fetchall()
    assert [event["action"] for event in history_activity] == [
        "Пользователь отключён",
        "Пользователь включён",
    ]
    assert history_activity[0]["details"] == "Сотрудник уволен"
    assert history_activity[0]["actor_username"] == "owner2"
    assert history_activity[1]["details"] == "Доступ восстановлен"
    conn.close()

    history_password_response = await crm.change_team_user_password(
        make_form_request(
            "owner2",
            f"/workers/{history_candidate['id']}/password",
            {"password": "secure456"},
        ),
        history_candidate["id"],
    )
    assert history_password_response.status_code == 302
    assert (
        history_password_response.headers["location"]
        == "/workers?password_changed=1"
    )

    history_commission_response = await crm.update_worker_commission(
        make_form_request(
            "owner2",
            f"/workers/{history_candidate['id']}/commission",
            {"commission_percent": "7.5"},
        ),
        history_candidate["id"],
    )
    assert history_commission_response.status_code == 302
    assert (
        history_commission_response.headers["location"]
        == "/workers?commission_updated=1"
    )

    conn = connect()
    c = conn.cursor()
    management_activity = c.execute("""
    SELECT action, details
    FROM team_activity
    WHERE company_id=2 AND user_id=?
    ORDER BY id DESC
    LIMIT 2
    """, (history_candidate["id"],)).fetchall()
    conn.close()
    assert management_activity[0]["action"] == "Процент обновлён"
    assert management_activity[0]["details"] == "0% → 7.5%"
    assert management_activity[1]["action"] == "Пароль обновлён"
    assert management_activity[1]["details"] == "Пароль изменён владельцем компании"
    assert "secure456" not in management_activity[1]["details"]

    profile_update_response = await crm.update_team_user_profile(
        make_form_request(
            "owner2",
            f"/workers/{history_candidate['id']}/profile",
            {
                "full_name": "Исторический Сотрудник",
                "position": "Старший специалист",
                "phone": "+7 900 000-00-00",
                "email": "history@example.test",
                "telegram_chat_id": "history-chat",
                "daily_capacity": "4",
            },
        ),
        history_candidate["id"],
    )
    assert profile_update_response.status_code == 302
    assert profile_update_response.headers["location"] == (
        f"/workers/{history_candidate['id']}?profile_updated=1"
    )

    conn = connect()
    c = conn.cursor()
    updated_profile = c.execute("""
    SELECT full_name, position, phone, email, telegram_chat_id, daily_capacity
    FROM users
    WHERE id=? AND company_id=2
    """, (history_candidate["id"],)).fetchone()
    profile_activity = c.execute("""
    SELECT action, details
    FROM team_activity
    WHERE company_id=2 AND user_id=? AND action='Карточка обновлена'
    ORDER BY id DESC
    LIMIT 1
    """, (history_candidate["id"],)).fetchone()
    conn.close()
    assert updated_profile["full_name"] == "Исторический Сотрудник"
    assert updated_profile["position"] == "Старший специалист"
    assert updated_profile["telegram_chat_id"] == "history-chat"
    assert updated_profile["daily_capacity"] == 4
    assert profile_activity["details"] == (
        "Изменены поля: ФИО, Должность, Телефон, "
        "Электронная почта, ID чата Telegram, Дневной лимит заявок"
    )
    assert "+7 900 000-00-00" not in profile_activity["details"]
    assert "history@example.test" not in profile_activity["details"]

    absence_start = datetime.now().date() + timedelta(days=10)
    absence_end = absence_start + timedelta(days=2)
    absence_response = await crm.create_worker_unavailability(
        make_form_request(
            "manager2",
            f"/workers/{history_candidate['id']}/unavailability",
            {
                "date_from": absence_start.strftime("%Y-%m-%d"),
                "date_to": absence_end.strftime("%Y-%m-%d"),
                "reason": "Учебный отпуск",
            },
        ),
        history_candidate["id"],
    )
    assert absence_response.status_code == 302
    assert absence_response.headers["location"] == (
        f"/workers/{history_candidate['id']}?unavailability_created=1"
    )

    overlap_response = await crm.create_worker_unavailability(
        make_form_request(
            "owner2",
            f"/workers/{history_candidate['id']}/unavailability",
            {
                "date_from": absence_start.strftime("%Y-%m-%d"),
                "date_to": absence_end.strftime("%Y-%m-%d"),
                "reason": "Повтор",
            },
        ),
        history_candidate["id"],
    )
    assert overlap_response.headers["location"] == (
        f"/workers/{history_candidate['id']}?unavailability_error=overlap"
    )

    conn = connect()
    c = conn.cursor()
    absence_period = c.execute("""
    SELECT *
    FROM worker_unavailability
    WHERE company_id=2 AND worker_id=?
    """, (history_candidate["id"],)).fetchone()
    outsider_worker = c.execute("""
    SELECT id
    FROM users
    WHERE company_id=1 AND username='outsider_worker'
    """).fetchone()
    absence_activity = c.execute("""
    SELECT action, details, actor_username
    FROM team_activity
    WHERE company_id=2
      AND user_id=?
      AND action='Добавлен период недоступности'
    ORDER BY id DESC
    LIMIT 1
    """, (history_candidate["id"],)).fetchone()
    conn.close()
    assert absence_period["reason"] == "Учебный отпуск"
    assert absence_period["created_by"] == "manager2"
    assert absence_activity["actor_username"] == "manager2"
    assert "Учебный отпуск" in absence_activity["details"]

    cross_company_absence = await crm.create_worker_unavailability(
        make_form_request(
            "owner2",
            f"/workers/{outsider_worker['id']}/unavailability",
            {
                "date_from": absence_start.strftime("%Y-%m-%d"),
                "date_to": absence_end.strftime("%Y-%m-%d"),
                "reason": "Чужая компания",
            },
        ),
        outsider_worker["id"],
    )
    assert cross_company_absence.headers["location"] == "/workers"

    team_activity_response = await crm.team_activity_page(
        make_asgi_request(
            "owner2",
            "/workers/activity?action=commission",
        ),
        action="commission",
    )
    team_activity_html = team_activity_response.body.decode("utf-8")
    assert team_activity_response.status_code == 200
    assert team_activity_response.context["action"] == "commission"
    assert team_activity_response.context["events"]
    assert all(
        event["company_id"] == 2
        for event in team_activity_response.context["events"]
    )
    assert all(
        event["action"] == "Процент обновлён"
        for event in team_activity_response.context["events"]
    )
    assert "История команды" in team_activity_html
    assert "0% → 7.5%" in team_activity_html
    assert "secure456" not in team_activity_html

    history_worker_response = await crm.worker_detail(
        make_asgi_request(
            "owner2",
            f"/workers/{history_candidate['id']}",
        ),
        history_candidate["id"],
    )
    history_worker_html = history_worker_response.body.decode("utf-8")
    assert "История управления" in history_worker_html
    assert "Пользователь отключён" in history_worker_html
    assert "Пользователь включён" in history_worker_html
    assert "Сотрудник уволен" in history_worker_html
    assert "Пароль обновлён" in history_worker_html
    assert "Процент обновлён" in history_worker_html
    assert "Карточка обновлена" in history_worker_html
    assert "Редактировать карточку" in history_worker_html
    assert "Сохранить карточку" in history_worker_html
    assert "Недоступность сотрудника" in history_worker_html
    assert "Учебный отпуск" in history_worker_html
    assert "Добавлен период недоступности" in history_worker_html
    assert "0% → 7.5%" in history_worker_html

    delete_absence_response = await crm.delete_worker_unavailability(
        make_form_request(
            "manager2",
            (
                f"/workers/{history_candidate['id']}/unavailability/"
                f"{absence_period['id']}/delete"
            ),
            {},
        ),
        history_candidate["id"],
        absence_period["id"],
    )
    assert delete_absence_response.headers["location"] == (
        f"/workers/{history_candidate['id']}?unavailability_deleted=1"
    )
    conn = connect()
    c = conn.cursor()
    assert c.execute("""
    SELECT COUNT(*)
    FROM worker_unavailability
    WHERE id=?
    """, (absence_period["id"],)).fetchone()[0] == 0
    deleted_absence_activity = c.execute("""
    SELECT action
    FROM team_activity
    WHERE company_id=2
      AND user_id=?
      AND action='Удалён период недоступности'
    ORDER BY id DESC
    LIMIT 1
    """, (history_candidate["id"],)).fetchone()
    conn.close()
    assert deleted_absence_activity is not None

    clean_toggle_response = await crm.toggle_team_user_active(
        make_form_request(
            "owner2",
            f"/workers/{delete_candidate['id']}/toggle-active",
            {},
        ),
        delete_candidate["id"],
    )
    assert clean_toggle_response.status_code == 302
    assert clean_toggle_response.headers["location"] == "/workers?status_updated=1"

    clean_delete_response = await crm.delete_team_user(
        make_form_request(
            "owner2",
            f"/workers/{delete_candidate['id']}/delete",
            {},
        ),
        delete_candidate["id"],
    )
    assert clean_delete_response.status_code == 302
    assert clean_delete_response.headers["location"] == "/workers?deleted=1"

    conn = connect()
    c = conn.cursor()
    assert c.execute("""
    SELECT id
    FROM users
    WHERE id=?
    """, (delete_candidate["id"],)).fetchone() is None
    deleted_user_activity = c.execute("""
    SELECT action, details, actor_username
    FROM team_activity
    WHERE company_id=2
      AND user_id=?
      AND action='Пользователь удалён'
    """, (delete_candidate["id"],)).fetchone()
    assert deleted_user_activity["details"] == "Роль: Исполнитель"
    assert deleted_user_activity["actor_username"] == "owner2"
    preserved_users = c.execute("""
    SELECT id
    FROM users
    WHERE id IN (?, ?, ?)
    """, (
        outsider["id"],
        helper["id"],
        history_candidate["id"],
    )).fetchall()
    conn.close()
    assert len(preserved_users) == 3

    membership_activity_response = await crm.team_activity_page(
        make_asgi_request(
            "owner2",
            "/workers/activity?action=membership",
        ),
        action="membership",
    )
    membership_activity_html = membership_activity_response.body.decode("utf-8")
    assert membership_activity_response.status_code == 200
    assert membership_activity_response.context["action"] == "membership"
    assert all(
        event["action"] in ("Пользователь создан", "Пользователь удалён")
        for event in membership_activity_response.context["events"]
    )
    assert "audit_manager2" in membership_activity_html
    assert "delete_candidate2" in membership_activity_html
    deleted_events = [
        event for event in membership_activity_response.context["events"]
        if event["action"] == "Пользователь удалён"
    ]
    assert deleted_events
    assert deleted_events[0]["current_user_id"] is None

    membership_export_response = await crm.team_activity_export(
        make_request("owner2"),
        action="membership",
    )
    assert membership_export_response.status_code == 200
    assert (
        membership_export_response.headers["content-disposition"]
        == "attachment; filename=team_activity_membership.csv"
    )
    membership_export_csv = membership_export_response.body.decode("utf-8")
    assert membership_export_csv.startswith("\ufeff")
    assert "Сотрудник,Действие,Подробности,Выполнил,Дата" in (
        membership_export_csv
    )
    assert "Пользователь создан" in membership_export_csv
    assert "Пользователь удалён" in membership_export_csv
    assert "Пароль обновлён" not in membership_export_csv

    searched_activity_response = await crm.team_activity_page(
        make_asgi_request(
            "owner2",
            "/workers/activity",
        ),
        action="all",
        search="delete_candidate2",
        date_from="2020-01-01",
        date_to="2030-12-31",
    )
    searched_activity_html = searched_activity_response.body.decode("utf-8")
    assert searched_activity_response.context["events"]
    assert all(
        "delete_candidate2" in (
            (event["target_username"] or "")
            + (event["actor_username"] or "")
        )
        for event in searched_activity_response.context["events"]
    )
    assert 'value="delete_candidate2"' in searched_activity_html
    assert "date_from=2020-01-01" in searched_activity_html
    assert "date_to=2030-12-31" in searched_activity_html

    searched_export_response = await crm.team_activity_export(
        make_request("owner2"),
        action="all",
        search="delete_candidate2",
        date_from="2020-01-01",
        date_to="2030-12-31",
    )
    searched_export_csv = searched_export_response.body.decode("utf-8")
    assert "delete_candidate2" in searched_export_csv
    assert "history_candidate2" not in searched_export_csv

    active_task_block_response = await crm.toggle_team_user_active(
        make_form_request(
            "owner2",
            f"/workers/{helper['id']}/toggle-active",
            {},
        ),
        helper["id"],
    )
    assert active_task_block_response.status_code == 302
    assert active_task_block_response.headers["location"].startswith(
        "/workers?error=active_tasks&count="
    )
    assert crm.get_user(make_request("helper2")) == "helper2"

    toggle_response = await crm.toggle_team_user_active(
        make_form_request(
            "owner2",
            f"/workers/{inactive_candidate['id']}/toggle-active",
            {},
        ),
        inactive_candidate["id"],
    )
    assert toggle_response.status_code == 302
    assert toggle_response.headers["location"] == "/workers?status_updated=1"
    assert crm.get_user(make_request("inactive_candidate2")) is None

    disabled_login_response = await crm.login(
        make_form_request(
            "anonymous",
            "/login",
            {"username": "inactive_candidate2", "password": "x"},
        )
    )
    assert disabled_login_response.status_code == 302
    assert disabled_login_response.headers["location"] == "/login?error=disabled"

    conn = connect()
    c = conn.cursor()
    assert crm.automation_action_target_is_valid(
        c,
        2,
        "create_task",
        "inactive_candidate2",
    ) is False
    conn.close()

    workers_response = await crm.workers_page(
        make_asgi_request("owner2", "/workers?status=inactive"),
        status="inactive",
    )
    workers_html = workers_response.body.decode("utf-8")
    assert "Отключён" in workers_html
    assert "Включить пользователя" in workers_html
    assert "Активные" in workers_html
    assert "Отключённые" in workers_html
    assert workers_response.context["status"] == "inactive"
    assert workers_response.context["team_counts"]["inactive_count"] >= 1

    active_workers_response = await crm.workers_page(
        make_asgi_request("owner2", "/workers"),
    )
    assert active_workers_response.context["status"] == "active"
    assert all(
        worker["is_active"] is None or worker["is_active"]
        for worker in active_workers_response.context["workers"]
    )
    assert "История управления командой" in (
        active_workers_response.body.decode("utf-8")
    )

    task_detail_response = await crm.task_detail(
        make_asgi_request("owner2", f"/task/{task['id']}"),
        task["id"],
    )
    task_detail_html = task_detail_response.body.decode("utf-8")
    assert f"/task/{task['id']}/workers" in task_detail_html
    assert "Умный перенос" in task_detail_html
    assert "Подбор даты для текущей команды:" in task_detail_html
    assert "Загрузка команды после переноса:" in task_detail_html
    assert task_detail_response.context["smart_reschedule_items"]
    assert len(task_detail_response.context["smart_reschedule_items"]) <= 5
    assert all(
        item["worker_names"]
        == task_detail_response.context["task_workers"]
        for item in task_detail_response.context["smart_reschedule_items"]
    )
    assert all(
        "outsider_worker" not in item["worker_names"]
        for item in task_detail_response.context["smart_reschedule_items"]
    )
    assert (
        f'action="/task/{task["id"]}/date"'
        in task_detail_html
    )
    assert all(
        worker["username"] != "inactive_candidate2"
        for worker in task_detail_response.context["available_workers"]
    )

    update_workers_response = await crm.update_task_workers(
        make_multipart_request(
            "owner2",
            f"/task/{task['id']}/workers",
            {
                "workers": [
                    "worker2",
                    "free2",
                    "inactive_candidate2",
                    "outsider_worker",
                ],
            },
        ),
        task["id"],
    )
    assert update_workers_response.status_code == 302
    assert update_workers_response.headers["location"] == f"/task/{task['id']}"

    conn = connect()
    c = conn.cursor()
    reassigned_task = c.execute("""
    SELECT worker, workers
    FROM tasks
    WHERE id=?
    """, (task["id"],)).fetchone()
    reassignment_activity = c.execute("""
    SELECT details
    FROM task_activity
    WHERE task_id=? AND action='Изменены исполнители'
    ORDER BY id DESC
    """, (task["id"],)).fetchone()
    assignment_notification = c.execute("""
    SELECT title, message, link
    FROM notifications
    WHERE company_id=2
      AND username='free2'
      AND link=?
    ORDER BY id DESC
    """, (f"/task/{task['id']}",)).fetchone()
    conn.close()

    assert reassigned_task["worker"] == "worker2"
    assert reassigned_task["workers"] == "worker2,free2"
    assert reassignment_activity["details"] == "worker2, free2"
    assert assignment_notification["title"] == f"Назначена заявка #{task['id']}"
    assert assignment_notification["link"] == f"/task/{task['id']}"

    create_task_response = await crm.create_task_page(
        make_asgi_request("owner2", "/create-task")
    )
    assert all(
        worker["username"] != "inactive_candidate2"
        for worker in create_task_response.context["workers"]
    )

    recurring_response = await crm.recurring_jobs_page(
        make_asgi_request("owner2", "/recurring")
    )
    assert all(
        worker["username"] != "inactive_candidate2"
        for worker in recurring_response.context["workers"]
    )

    calendar_response = await crm.calendar_page(
        make_asgi_request("owner2", "/calendar")
    )
    assert all(
        worker["username"] != "inactive_candidate2"
        for worker in calendar_response.context["workers"]
    )

    automation_builder_response = await crm.automation_builder_page(
        make_asgi_request("owner2", "/automation/builder")
    )
    assert all(
        worker["username"] != "inactive_candidate2"
        for worker in automation_builder_response.context["workers"]
    )

    toggle_response = await crm.toggle_team_user_active(
        make_form_request(
            "owner2",
            f"/workers/{inactive_candidate['id']}/toggle-active",
            {},
        ),
        inactive_candidate["id"],
    )
    assert toggle_response.status_code == 302
    assert crm.get_user(make_request("inactive_candidate2")) == (
        "inactive_candidate2"
    )

    sent_reassignment_telegram = []
    original_send_message_to_chat = crm.send_message_to_chat
    crm.send_message_to_chat = (
        lambda chat_id, text:
        sent_reassignment_telegram.append((chat_id, text)) or True
    )

    try:
        restore_workers_response = await crm.update_task_workers(
            make_multipart_request(
                "owner2",
                f"/task/{task['id']}/workers",
                {"workers": ["worker2", "helper2"]},
            ),
            task["id"],
        )
    finally:
        crm.send_message_to_chat = original_send_message_to_chat

    assert restore_workers_response.status_code == 302
    assert sent_reassignment_telegram
    assert sent_reassignment_telegram[-1][0] == "chat-helper2"
    assert f"Вам назначена заявка #{task['id']}" in (
        sent_reassignment_telegram[-1][1]
    )

    conn = connect()
    c = conn.cursor()
    helper_notification_count = c.execute("""
    SELECT COUNT(*)
    FROM notifications
    WHERE company_id=2
      AND username='helper2'
      AND title=?
      AND link=?
    """, (
        f"Назначена заявка #{task['id']}",
        f"/task/{task['id']}",
    )).fetchone()[0]
    activity_count_before_duplicate = c.execute("""
    SELECT COUNT(*)
    FROM task_activity
    WHERE task_id=? AND action='Изменены исполнители'
    """, (task["id"],)).fetchone()[0]
    conn.close()

    duplicate_telegram = []
    original_send_message_to_chat = crm.send_message_to_chat
    crm.send_message_to_chat = (
        lambda chat_id, text:
        duplicate_telegram.append((chat_id, text)) or True
    )

    try:
        duplicate_response = await crm.update_task_workers(
            make_multipart_request(
                "owner2",
                f"/task/{task['id']}/workers",
                {"workers": ["worker2", "helper2"]},
            ),
            task["id"],
        )
    finally:
        crm.send_message_to_chat = original_send_message_to_chat

    assert duplicate_response.status_code == 302
    assert duplicate_telegram == []

    conn = connect()
    c = conn.cursor()
    assert c.execute("""
    SELECT COUNT(*)
    FROM notifications
    WHERE company_id=2
      AND username='helper2'
      AND title=?
      AND link=?
    """, (
        f"Назначена заявка #{task['id']}",
        f"/task/{task['id']}",
    )).fetchone()[0] == helper_notification_count
    assert c.execute("""
    SELECT COUNT(*)
    FROM task_activity
    WHERE task_id=? AND action='Изменены исполнители'
    """, (task["id"],)).fetchone()[0] == activity_count_before_duplicate
    conn.close()

    removed_worker_telegram = []
    original_send_message_to_chat = crm.send_message_to_chat
    crm.send_message_to_chat = (
        lambda chat_id, text:
        removed_worker_telegram.append((chat_id, text)) or True
    )

    try:
        remove_helper_response = await crm.update_task_workers(
            make_multipart_request(
                "owner2",
                f"/task/{task['id']}/workers",
                {"workers": ["worker2"]},
            ),
            task["id"],
        )
    finally:
        crm.send_message_to_chat = original_send_message_to_chat

    assert remove_helper_response.status_code == 302
    assert removed_worker_telegram
    assert removed_worker_telegram[-1][0] == "chat-helper2"
    assert f"С вас снята заявка #{task['id']}" in (
        removed_worker_telegram[-1][1]
    )

    conn = connect()
    c = conn.cursor()
    removal_notification = c.execute("""
    SELECT title, link
    FROM notifications
    WHERE company_id=2
      AND username='helper2'
      AND title=?
    ORDER BY id DESC
    """, (f"Снято назначение с заявки #{task['id']}",)).fetchone()
    conn.close()

    assert removal_notification["link"] == "/my-tasks"

    restore_after_removal = await crm.update_task_workers(
        make_multipart_request(
            "owner2",
            f"/task/{task['id']}/workers",
            {"workers": ["worker2", "helper2"]},
        ),
        task["id"],
    )
    assert restore_after_removal.status_code == 302

    conn = connect()
    c = conn.cursor()
    assert crm.automation_action_target_is_valid(
        c,
        2,
        "create_task",
        "inactive_candidate2",
    ) is True
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
    assert "Зарплаты" in finance_html
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
    assert "Статус зарплаты" in export_csv
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
    assert "Текущая загрузка" in worker_detail_html
    assert worker_detail_response.context["active_tasks_count"] >= 1
    assert worker_detail_response.context["today_tasks_count"] >= 0
    assert worker_detail_response.context["future_tasks_count"] >= 0
    assert any(
        active_task["id"] == task["id"]
        for active_task in worker_detail_response.context["active_tasks"]
    )
    assert f"/task/{task['id']}" in worker_detail_html
    assert (
        "Создать заявку на сегодня" in worker_detail_html
        and "Открыть календарь сотрудника" in worker_detail_html
    )
    assert "worker=helper2" in worker_detail_html
    assert "return_to=calendar" in worker_detail_html
    assert "Загрузка на 7 дней" in worker_detail_html
    assert len(worker_detail_response.context["weekly_schedule"]) == 7
    assert worker_detail_response.context["nearest_free_date"]
    assert worker_detail_response.context["daily_capacity"] == 3
    assert all(
        day["calendar_url"].startswith("/calendar?date=")
        and "worker=helper2" in day["calendar_url"]
        and day["create_url"].startswith("/create-task?task_date=")
        and day["available_slots"] == max(
            worker_detail_response.context["daily_capacity"]
            - day["task_count"],
            0,
        )
        for day in worker_detail_response.context["weekly_schedule"]
    )

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
    assert 'value="worker2" data-at-capacity="0" checked' in repeat_html

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

    conn = connect()
    c = conn.cursor()
    c.execute("""
    UPDATE users
    SET is_active=0
    WHERE company_id=2 AND username='helper2'
    """)
    conn.commit()
    conn.close()

    recurring_telegram = []
    original_send_message_to_chat = crm.send_message_to_chat
    crm.send_message_to_chat = (
        lambda chat_id, text:
        recurring_telegram.append((chat_id, text)) or True
    )

    try:
        response = await crm.generate_recurring_task(
            make_request("owner2"),
            job_id,
        )
    finally:
        crm.send_message_to_chat = original_send_message_to_chat

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
    SELECT next_date, worker, workers
    FROM recurring_jobs
    WHERE id=?
    """, (job_id,)).fetchone()
    activity = c.execute("""
    SELECT *
    FROM task_activity
    WHERE task_id=? AND action='Создана из регулярной работы'
    """, (generated_task_id,)).fetchone()
    recurring_notification = c.execute("""
    SELECT title, message, link
    FROM notifications
    WHERE company_id=2
      AND username='worker2'
      AND link=?
    ORDER BY id DESC
    """, (f"/task/{generated_task_id}",)).fetchone()
    inactive_notification_count = c.execute("""
    SELECT COUNT(*)
    FROM notifications
    WHERE company_id=2
      AND username='helper2'
      AND link=?
    """, (f"/task/{generated_task_id}",)).fetchone()[0]
    conn.close()

    assert generated_task is not None
    assert generated_task["client_id"] == task["client_id"]
    assert generated_task["worker"] == "worker2"
    assert generated_task["workers"] == "worker2"
    assert job["next_date"] == "2026-06-17"
    assert job["worker"] == "worker2"
    assert job["workers"] == "worker2"
    assert activity is not None
    assert recurring_notification["title"] == (
        f"Назначена регулярная заявка #{generated_task_id}"
    )
    assert recurring_notification["link"] == f"/task/{generated_task_id}"
    assert inactive_notification_count == 0
    assert recurring_telegram == [
        (
            "chat-worker2",
            (
                f"Вам назначена регулярная заявка #{generated_task_id}\n"
                "Клиент: Client 2\n"
                "Дата: 2026-05-17\n"
                "Описание: Generated from recurring"
            ),
        )
    ]

    conn = connect()
    c = conn.cursor()
    c.execute("""
    UPDATE users
    SET is_active=0
    WHERE company_id=2 AND username='worker2'
    """)
    conn.commit()
    tasks_before_blocked_generation = c.execute("""
    SELECT COUNT(*)
    FROM tasks
    WHERE company_id=2
    """).fetchone()[0]
    conn.close()

    blocked_response = await crm.generate_recurring_task(
        make_request("owner2"),
        job_id,
    )
    assert blocked_response.status_code == 302
    assert blocked_response.headers["location"] == (
        "/recurring?error=no_active_workers"
    )

    conn = connect()
    c = conn.cursor()
    assert c.execute("""
    SELECT COUNT(*)
    FROM tasks
    WHERE company_id=2
    """).fetchone()[0] == tasks_before_blocked_generation
    c.execute("""
    UPDATE users
    SET is_active=1
    WHERE company_id=2
      AND username IN ('worker2', 'helper2')
    """)
    conn.commit()
    conn.close()

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
    original_run_automation_event = crm.run_automation_event
    new_client_events = []
    crm.send_message = lambda text: True
    crm.run_automation_event = (
        lambda company_id, trigger_key, entity_type="", entity_id=None,
        message="", link="":
        new_client_events.append({
            "company_id": company_id,
            "trigger_key": trigger_key,
            "entity_type": entity_type,
            "entity_id": entity_id,
            "message": message,
            "link": link,
        }) or 1
    )

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
        crm.run_automation_event = original_run_automation_event

    assert response.status_code == 302
    assert response.headers["location"] == "/clients?created=1"
    assert len(new_client_events) == 1
    assert new_client_events[0]["company_id"] == 2
    assert new_client_events[0]["trigger_key"] == "new_client"
    assert new_client_events[0]["entity_type"] == "client"
    assert new_client_events[0]["message"] == (
        "Создан новый клиент: Custom Field Client Company"
    )

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
    assert new_client_events[0]["entity_id"] == value["client_id"]
    assert new_client_events[0]["link"] == f"/clients/{value['client_id']}"

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
    c.execute("""
    UPDATE users
    SET daily_capacity=1
    WHERE company_id=2 AND username='worker2'
    """)
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
    assert 'value="worker2" data-at-capacity="1" checked' in page_html
    assert 'name="return_to" value="calendar"' in page_html
    assert "У выбранного исполнителя на эту дату:" in page_html
    assert page_response.context["selected_worker_daily_capacity"] == 1
    assert page_response.context["selected_worker_at_capacity"] is True
    assert "Свободных мест нет" in page_html
    assert "Назначение превысит дневной лимит" in page_html
    assert 'name="allow_capacity_override" value="1"' in page_html
    assert "Назначить выбранных исполнителей сверх дневного лимита" in page_html
    assert "syncCapacityConfirmation" in page_html
    assert "worker-option at-capacity" in page_html
    assert "Лимит 1/1" in page_html
    assert "Свободно 3 · 0/3" in page_html
    worker2_option = next(
        item
        for item in page_response.context["worker_options"]
        if item["username"] == "worker2"
    )
    free2_option = next(
        item
        for item in page_response.context["worker_options"]
        if item["username"] == "free2"
    )
    assert worker2_option["is_at_capacity"] is True
    assert worker2_option["available_slots"] == 0
    assert free2_option["available_slots"] == 3
    assert page_response.context["selected_worker_available_slots"] == max(
        page_response.context["selected_worker_daily_capacity"]
        - page_response.context["selected_worker_active_count"],
        0,
    )
    assert "/task/" in page_html
    assert "Client 2 / Новая" in page_html
    assert "Альтернатива: free2" in page_html
    assert "свободно" in page_html
    assert "Выбрать альтернативу" in page_html
    assert "/create-task?task_date=2026-05-17&amp;worker=free2&amp;return_to=calendar" in page_html

    blocked_response = await crm.create_task(
        make_multipart_request(
            "owner2",
            "/create-task",
            {
                "client": "Blocked Capacity Client",
                "task_date": "2026-05-17",
                "workers": ["free2", "worker2"],
                "return_to": "calendar",
                "priority": "Обычный",
            },
        ),
        photo=None,
    )
    assert blocked_response.status_code == 302
    assert blocked_response.headers["location"] == (
        "/create-task?error=capacity_confirmation"
        "&task_date=2026-05-17&worker=worker2"
        "&workers_csv=free2%2Cworker2&return_to=calendar"
    )

    conn = connect()
    c = conn.cursor()
    blocked_task_count = c.execute("""
    SELECT COUNT(*)
    FROM tasks
    WHERE company_id=2 AND client='Blocked Capacity Client'
    """).fetchone()[0]
    conn.close()
    assert blocked_task_count == 0

    original_send_message = crm.send_message
    original_send_message_to_chat = crm.send_message_to_chat
    crm.send_message = lambda text: True
    crm.send_message_to_chat = lambda chat_id, text: True

    try:
        override_response = await crm.create_task(
            make_multipart_request(
                "owner2",
                "/create-task",
                {
                    "client": "Confirmed Capacity Client",
                    "task_date": "2026-05-17",
                    "workers": ["worker2"],
                    "return_to": "calendar",
                    "priority": "Срочно",
                    "allow_capacity_override": "1",
                },
            ),
            photo=None,
        )
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

    assert override_response.status_code == 302
    assert override_response.headers["location"] == (
        "/calendar?date=2026-05-17&worker=worker2"
    )

    conn = connect()
    c = conn.cursor()
    override_task = c.execute("""
    SELECT id
    FROM tasks
    WHERE company_id=2 AND client='Confirmed Capacity Client'
    ORDER BY id DESC
    LIMIT 1
    """).fetchone()
    override_activity = c.execute("""
    SELECT details
    FROM task_activity
    WHERE task_id=?
      AND action='Превышен дневной лимит'
    ORDER BY id DESC
    LIMIT 1
    """, (override_task["id"],)).fetchone()
    conn.close()
    assert override_activity["details"] == (
        "Подтверждено при создании. worker2: 1 из 1"
    )

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
    assignment_notification = c.execute("""
    SELECT title, message, link
    FROM notifications
    WHERE company_id=2
      AND username='worker2'
      AND link=?
    ORDER BY id DESC
    """, (f"/task/{value['task_id']}",)).fetchone()
    unexpected_notification_count = c.execute("""
    SELECT COUNT(*)
    FROM notifications
    WHERE company_id=2
      AND username IN ('helper2', 'free2', 'outsider_worker')
      AND link=?
    """, (f"/task/{value['task_id']}",)).fetchone()[0]
    conn.close()

    assert value is not None
    assert assignment_notification["title"] == (
        f"Назначена новая заявка #{value['task_id']}"
    )
    assert assignment_notification["link"] == f"/task/{value['task_id']}"
    assert "Клиент: Custom Field Client" in assignment_notification["message"]
    assert unexpected_notification_count == 0

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



async def assert_a3_workflow_center():
    public_response = crm.automation_workflows_page(make_request())
    assert public_response.status_code == 302
    assert public_response.headers["location"] == "/login"

    request = make_request("owner2")

    response = crm.automation_workflows_page(request)

    body = response.body.decode()

    assert "A3 Цепочки автоматизации" in body
    assert "/automation/builder" in body
    assert "Конструктор" in body
    assert "Условие:" in body
    assert "/api/a3/workflows/graph" in body
    assert "Фильтры" in body
    assert "Проблемные цепочки" in body
    assert "AI-рекомендации" in body
    assert "Состояние:" in body
    assert "Запустить" in body
    assert "Повторить" in body
    assert "Исправлено" in body
    assert "Центр проблем" in body
    assert "Последние события" in body
    assert "/api/a3/workflow/rules/" in body
    assert "Обновить историю" in body
    assert "Последние события" in body
    assert "/api/a3/workflow/rules/" in body
    assert "Обновить историю" in body
    assert "Воспроизвести" in body
    assert "Воспроизведение:" in body
    assert "timeline-progress-" in body
    assert "Пауза" in body
    assert "Остановить" in body
    assert "Скорость: обычно" in body
    assert "data-timeline-level" in body
    assert "Сессия: нет" in body
    assert "Сессия: активно" in body
    assert "chain.replaying" in body
    assert "Debug цепочки" in body
    assert "handleDebugAction" in body
    assert "/enable" in body
    assert "/retry-skipped" in body
    assert "Повтор пропущенных событий отправлен" in body
    assert "AI debug рекомендации" in body
    assert "Debug:" in body
    assert "Диагноз" in body
    assert "Следующий шаг:" in body
    assert "Риск:" in body
    assert "Безопасные исправления" in body
    assert "Автоисправления не требуются" in body
    assert "Требует подтверждения" in body
    assert "Очередь подтверждений" in body
    assert "workflow-approval-queue" in body
    assert "workflow-approval-history" in body
    assert "loadWorkflowApprovalQueue" in body
    assert "loadWorkflowApprovalHistory" in body
    assert "approveWorkflowAction" in body
    assert "rejectWorkflowAction" in body
    assert "Нет действий, ожидающих подтверждения" in body
    assert "Последние решения" in body
    assert "История решений пока пустая" in body
    assert "requestDangerousFixApproval" in body
    assert "/api/a3/autonomous-actions/request-approval" in body
    assert "/api/a3/approval-queue" in body
    assert "Ждёт подтверждения:" in body
    assert "Действие отправлено на подтверждение" in body
    assert "Сессии выполнения" in body
    assert "Активная сессия" in body
    assert "workflowSessionStatusLabel" in body
    assert "workflowExecutionStateLabel" in body
    assert "workflowSessionCounters" in body
    assert "Состояние:" in body
    assert "Длительность:" in body
    assert "selectWorkflowSession" in body
    assert "data-session-index" in body
    assert "filterWorkflowTimeline" in body
    assert "data-timeline-filter" in body
    assert "По выбранному фильтру событий нет" in body

    public_timeline_response = crm.api_a3_workflow_timeline(
        make_request(),
        1,
    )
    assert public_timeline_response.status_code == 403

    missing_timeline_response = crm.api_a3_workflow_timeline(
        request,
        999999,
    )
    assert missing_timeline_response.status_code == 404

    automation_response = crm.automation_page(request)

    automation_body = automation_response.body.decode()

    assert "/automation/workflows" in automation_body


async def assert_a3_api_layer():
    request = make_request("owner2")

    data = crm.api_a3_system_health(request)
    assert "score" in data
    assert 0 <= data["score"] <= 100
    assert data["status"] in {"healthy", "warning", "degraded", "critical"}

    conn = connect()
    c = conn.cursor()
    snapshot_count_before = c.execute("""
    SELECT COUNT(*)
    FROM system_health_snapshots
    WHERE company_id=2
    """).fetchone()[0]
    conn.close()

    second_health = crm.api_a3_system_health(request)
    assert second_health["status"] in {"healthy", "warning", "degraded", "critical"}

    conn = connect()
    c = conn.cursor()
    snapshot_count_after = c.execute("""
    SELECT COUNT(*)
    FROM system_health_snapshots
    WHERE company_id=2
    """).fetchone()[0]
    conn.close()

    assert snapshot_count_after == snapshot_count_before

    history = crm.api_a3_system_health_history(request)
    assert "items" in history

    analytics = crm.api_a3_automation_analytics(request)
    assert "events_total" in analytics
    assert "done_total" in analytics
    assert "pending_total" in analytics

    insights = crm.api_a3_operations_insights(request)
    assert "items" in insights

    recovery_result = crm.api_a3_self_healing_run(request)
    assert recovery_result["ok"] is True
    assert "result" in recovery_result

    recovery_history = crm.api_a3_recovery_history(request)
    assert "items" in recovery_history

    timeline = crm.api_a3_ops_timeline(request)
    assert "items" in timeline

    first_timeline_id = crm.create_ops_timeline_event(
        2,
        "smoke_event",
        "warning",
        "Smoke timeline event",
        "Smoke timeline dedupe",
    )
    second_timeline_id = crm.create_ops_timeline_event(
        2,
        "smoke_event",
        "warning",
        "Smoke timeline event",
        "Smoke timeline dedupe",
    )
    assert first_timeline_id == second_timeline_id

    predictive = crm.api_a3_predictive_signals(request)
    assert "items" in predictive

    decisions = crm.api_a3_decision_engine(request)
    assert "items" in decisions

    actions = crm.api_a3_autonomous_actions(request)
    assert "items" in actions

    conn = connect()
    c = conn.cursor()
    c.execute("""
    INSERT INTO automation_rules (
        company_id, name, trigger_key, conditions_json,
        active, created_by, created_at, updated_at
    )
    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        2,
        "A3 disabled unhealthy smoke",
        "weekly_digest",
        "{}",
        0,
        "owner2",
        datetime.now().isoformat(timespec="seconds"),
        datetime.now().isoformat(timespec="seconds"),
    ))
    disabled_unhealthy_rule_id = c.lastrowid
    conn.commit()
    conn.close()

    unhealthy_rules = crm.api_a3_unhealthy_rules(request)
    assert "items" in unhealthy_rules
    assert any(
        item["id"] == disabled_unhealthy_rule_id
        and "Правило отключено" in item["issues"]
        for item in unhealthy_rules["items"]
    )

    conn = connect()
    c = conn.cursor()
    c.execute("""
    INSERT INTO autonomous_action_queue (
        company_id, action_type, target_type, target_id,
        status, payload_json, created_at
    )
    VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        2,
        "disable_rule",
        "automation_rule",
        0,
        "awaiting_approval",
        "{}",
        datetime.now().isoformat(timespec="seconds"),
    ))
    approve_action_id = c.lastrowid
    c.execute("""
    INSERT INTO autonomous_action_queue (
        company_id, action_type, target_type, target_id,
        status, payload_json, created_at
    )
    VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        2,
        "disable_rule",
        "automation_rule",
        0,
        "awaiting_approval",
        "{}",
        datetime.now().isoformat(timespec="seconds"),
    ))
    reject_action_id = c.lastrowid
    conn.commit()
    conn.close()

    approval_queue = crm.api_a3_approval_queue(request)
    assert "items" in approval_queue
    assert any(item["id"] == approve_action_id for item in approval_queue["items"])
    assert any(item["id"] == reject_action_id for item in approval_queue["items"])

    approve_result = crm.api_a3_approve_autonomous_action(request, approve_action_id)
    assert approve_result["ok"] is True

    reject_result = crm.api_a3_reject_autonomous_action(request, reject_action_id)
    assert reject_result["ok"] is True

    conn = connect()
    c = conn.cursor()
    approved_row = c.execute("""
    SELECT status
    FROM autonomous_action_queue
    WHERE id=?
    """, (approve_action_id,)).fetchone()
    rejected_row = c.execute("""
    SELECT status
    FROM autonomous_action_queue
    WHERE id=?
    """, (reject_action_id,)).fetchone()
    conn.close()

    assert approved_row["status"] == "approved"
    assert rejected_row["status"] == "rejected"

    approval_history = crm.api_a3_approval_history(request)
    assert "items" in approval_history
    assert any(
        item["action_id"] == approve_action_id
        and item["decision"] == "approved"
        for item in approval_history["items"]
    )
    assert any(
        item["action_id"] == reject_action_id
        and item["decision"] == "rejected"
        for item in approval_history["items"]
    )

    conn = connect()
    c = conn.cursor()
    c.execute("""
    INSERT INTO automation_rules (
        company_id, name, trigger_key, conditions_json,
        active, created_by, created_at, updated_at
    )
    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        2,
        "A3 approved disable smoke",
        "weekly_digest",
        "{}",
        1,
        "owner2",
        datetime.now().isoformat(timespec="seconds"),
        datetime.now().isoformat(timespec="seconds"),
    ))
    disable_rule_id = c.lastrowid
    c.execute("""
    INSERT INTO autonomous_action_queue (
        company_id, action_type, target_type, target_id,
        status, payload_json, created_at
    )
    VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        2,
        "disable_rule",
        "automation_rule",
        disable_rule_id,
        "approved",
        "{}",
        datetime.now().isoformat(timespec="seconds"),
    ))
    conn.commit()
    conn.close()

    process_result = crm.api_a3_process_autonomous_actions(request)
    assert process_result["ok"] is True
    assert "result" in process_result
    assert process_result["result"]["processed"] >= 1

    approval_request = await crm.api_a3_request_autonomous_action_approval(
        make_json_request(
            "owner2",
            "/api/a3/autonomous-actions/request-approval",
            {
                "action_type": "disable_rule",
                "target_type": "automation_rule",
                "target_id": disable_rule_id,
                "reason": "Smoke approval request",
            },
        )
    )
    assert approval_request["ok"] is True
    assert approval_request["queued"] is True

    approval_request_duplicate = await crm.api_a3_request_autonomous_action_approval(
        make_json_request(
            "owner2",
            "/api/a3/autonomous-actions/request-approval",
            {
                "action_type": "disable_rule",
                "target_type": "automation_rule",
                "target_id": disable_rule_id,
                "reason": "Smoke approval request duplicate",
            },
        )
    )
    assert approval_request_duplicate["ok"] is False
    assert approval_request_duplicate["reason"] == "duplicate_pending_action"

    updated_approval_queue = crm.api_a3_approval_queue(request)
    assert any(
        item["action_type"] == "disable_rule"
        and item["target_id"] == disable_rule_id
        for item in updated_approval_queue["items"]
    )

    conn = connect()
    c = conn.cursor()
    disabled_rule = c.execute("""
    SELECT active
    FROM automation_rules
    WHERE id=?
      AND company_id=2
    """, (disable_rule_id,)).fetchone()
    conn.close()

    assert disabled_rule["active"] == 0

    governance = crm.api_a3_governance_settings(request)
    assert "autonomous_enabled" in governance
    assert "require_critical_approval" in governance

    update_result = await crm.api_a3_governance_settings_update(
        make_json_request(
            "owner2",
            "/api/a3/governance-settings/update",
            {
                "autonomous_enabled": True,
                "require_critical_approval": True,
                "confidence_threshold": 75,
                "max_actions_per_cycle": 5,
            },
        )
    )
    assert update_result["ok"] is True

    updated_governance = crm.api_a3_governance_settings(request)
    assert updated_governance["confidence_threshold"] == 75
    assert updated_governance["max_actions_per_cycle"] == 5


def main():
    try:
        task = seed_data()
        assert_session_cookie_auth()
        assert_task_access(task)
        assert_automation_foundation()
        asyncio.run(assert_automation_page())
        asyncio.run(assert_automation_runner(task))
        asyncio.run(assert_automation_delete())
        asyncio.run(assert_ai_assistant_page())
        asyncio.run(assert_upload_access())
        asyncio.run(assert_calendar_access())
        asyncio.run(assert_schedule_conflicts())
        asyncio.run(assert_dispatch_board())
        asyncio.run(assert_dispatch_planner())
        asyncio.run(assert_platform_calendar_health())
        asyncio.run(assert_daily_route_schedule())
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
        asyncio.run(assert_a3_api_layer())

        print("Smoke checks passed.")
    finally:
        TEMP_DATA.cleanup()


if __name__ == "__main__":
    main()
