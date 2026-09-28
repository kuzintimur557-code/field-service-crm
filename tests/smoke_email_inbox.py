import asyncio
import os
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from unittest.mock import patch
from urllib.parse import urlencode

from starlette.requests import Request


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


INBOX_SECRET = "inbox-smoke-secret"


class FakeInboxRequest:
    def __init__(self, payload, token=INBOX_SECRET, broken_json=False):
        self._payload = payload
        self._broken_json = broken_json
        self.headers = {"content-type": "application/json"}
        self.cookies = {}
        if token:
            self.headers["x-inbox-secret"] = token

    async def json(self):
        if self._broken_json:
            raise ValueError("broken")
        return self._payload


def valid_payload(**overrides):
    payload = {
        "company_id": 1,
        "provider": "test",
        "message_id": "<msg-001@test>",
        "from_email": "client@example.com",
        "from_name": "Тест Клиент",
        "subject": "Нужен ремонт стиральной машины",
        "text": "Добрый день! Адрес: Ленина 10. Телефон +79001112233.",
        "received_at": "2026-09-28 10:00",
    }
    payload.update(overrides)
    return payload


def main():
    with tempfile.TemporaryDirectory() as temp_dir, patch.dict(
        os.environ,
        {
            "DATA_DIR": temp_dir,
            "SECRET_KEY": "inbox-smoke-secret-key",
            "DATABASE_BACKEND": "sqlite",
            "DATABASE_URL": "",
            "INBOX_WEBHOOK_SECRET": INBOX_SECRET,
        },
        clear=False,
    ):
        from app import main as crm
        from app.database import connect
        from app.services.email_inbox import (
            build_email_dedupe_key,
            extract_email_fields,
            find_or_create_inbox_client,
            get_email_messages,
            normalize_inbox_payload,
            parse_extracted_fields,
            save_email_message,
            suggest_inbox_slots,
        )

        def call(payload, token=INBOX_SECRET, broken_json=False):
            request = FakeInboxRequest(payload, token=token, broken_json=broken_json)
            return asyncio.run(crm.receive_inbox_email(request))

        # dedupe key: stable by message_id, falls back to content hash
        first = normalize_inbox_payload(valid_payload())
        second = normalize_inbox_payload(valid_payload())
        assert first["dedupe_key"] == second["dedupe_key"]
        assert first["dedupe_key"] == build_email_dedupe_key(first)
        changed = normalize_inbox_payload(valid_payload(subject="Другая тема"))
        assert changed["dedupe_key"] == first["dedupe_key"]  # same message_id
        no_id_a = normalize_inbox_payload(valid_payload(message_id=""))
        no_id_b = normalize_inbox_payload(valid_payload(message_id="", subject="Иная"))
        assert no_id_a["dedupe_key"] != no_id_b["dedupe_key"]

        # validation
        for bad in ({}, {"company_id": 1}, {"company_id": "abc"}, {"company_id": 0}):
            try:
                normalize_inbox_payload(bad)
            except ValueError:
                pass
            else:
                raise AssertionError(f"payload must be rejected: {bad}")

        # endpoint guards
        response = call(valid_payload(), token="")
        assert response.status_code == 403
        response = call(valid_payload(), token="wrong")
        assert response.status_code == 403
        response = call(valid_payload(), broken_json=True)
        assert response.status_code == 400
        response = call(valid_payload(company_id=999999))
        assert response.status_code == 404
        response = call({"company_id": 1})
        assert response.status_code == 400

        # happy path + dedupe
        response = call(valid_payload())
        assert not hasattr(response, "status_code") or response.status_code == 200
        assert response["ok"] and response["created"] and response["id"]
        message_id = response["id"]

        response = call(valid_payload())
        assert response["ok"] and not response["created"]
        assert response["duplicate"] and response["id"] == message_id

        # raw .eml intake
        def raw_request(body, token=INBOX_SECRET, query=b"company_id=1"):
            headers = [(b"content-type", b"message/rfc822")]
            if token:
                headers.append((b"x-inbox-secret", token.encode()))
            scope = {
                "type": "http",
                "method": "POST",
                "path": "/api/inbox/email",
                "headers": headers,
                "query_string": query,
                "scheme": "http",
                "client": ("127.0.0.1", 50000),
                "server": ("testserver", 80),
            }

            async def receive():
                return {"type": "http.request", "body": body, "more_body": False}

            return Request(scope, receive)

        eml = (
            "From: Иван Петров <ivan@example.com>\r\n"
            "Message-ID: <raw-001@test>\r\n"
            "Subject: Sanтехника\r\n"
            "Date: Mon, 28 Sep 2026 10:00:00 +0300\r\n"
            "Content-Type: text/plain; charset=utf-8\r\n"
            "\r\n"
            "Здравствуйте! Нужен сантехник. Телефон +79005556677\r\n"
        ).encode("utf-8")

        response = asyncio.run(crm.receive_inbox_email(raw_request(eml)))
        assert response["ok"] and response["created"]
        raw_message_id = response["id"]

        response = asyncio.run(crm.receive_inbox_email(raw_request(eml)))
        assert response["ok"] and response["duplicate"]
        assert response["id"] == raw_message_id

        conn = connect()
        c = conn.cursor()
        raw_message = c.execute(
            "SELECT * FROM email_messages WHERE id=?", (raw_message_id,)
        ).fetchone()
        conn.close()
        assert raw_message["from_email"] == "ivan@example.com"
        assert raw_message["from_name"] == "Иван Петров"
        assert "Иван Петров" in raw_message["raw_source"]
        assert parse_extracted_fields(
            raw_message["extracted_json"]
        )["phone"] == "+79005556677"

        # invalid raw email and missing company rejected
        response = asyncio.run(crm.receive_inbox_email(raw_request(b"")))
        assert response.status_code == 400
        response = asyncio.run(crm.receive_inbox_email(raw_request(eml, query=b"")))
        assert response.status_code == 400

        messages = get_email_messages(1)
        assert len(messages) == 2
        assert messages[1]["status"] == "new"
        assert messages[1]["subject"] == "Нужен ремонт стиральной машины"
        assert messages[1]["raw_source"]

        extracted = parse_extracted_fields(messages[1]["extracted_json"])
        assert extracted["phone"] == "+79001112233"
        assert "Ленина 10" in extracted["address"]

        # extraction rules
        fields = extract_email_fields(
            "Здравствуйте! Меня зовут Анна. Нужна уборка квартиры завтра. "
            "Адрес: ул. Мира, д. 5, кв. 12. Мой телефон 8 900 111-22-33",
            "Уборка",
            "",
            ["Уборка квартиры", "Химчистка"],
            now=datetime(2026, 9, 28),
        )
        assert fields["phone"] == "+79001112233"
        assert fields["name"] == "Анна"
        assert "Мира" in fields["address"]
        assert fields["date"] == "2026-09-29"
        assert fields["service"] == "Уборка квартиры"

        assert extract_email_fields(
            "приедете 05.10?", "", "", [], now=datetime(2026, 9, 28)
        )["date"] == "2026-10-05"
        assert extract_email_fields(
            "жду в пятницу", "", "", [], now=datetime(2026, 9, 28)
        )["date"] == "2026-10-02"
        assert extract_email_fields(
            "жду 12 декабря", "", "", [], now=datetime(2026, 9, 28)
        )["date"] == "2026-12-12"
        assert extract_email_fields("просто вопрос", "", "", [])["date"] == ""

        # notifications for boss/manager of the company
        conn = connect()
        c = conn.cursor()
        notifications = c.execute("""
        SELECT * FROM notifications
        WHERE company_id=1 AND link='/inbox'
        """).fetchall()
        conn.close()
        assert notifications, "expected inbox notifications"

        # feature flag off -> 403
        conn = connect()
        c = conn.cursor()
        c.execute("""
        UPDATE company_features
        SET enabled=0
        WHERE company_id=1 AND feature_key='inbox'
        """)
        conn.commit()
        conn.close()

        response = call(valid_payload(message_id="<msg-002@test>"))
        assert response.status_code == 403

        conn = connect()
        c = conn.cursor()
        c.execute("""
        UPDATE company_features
        SET enabled=1
        WHERE company_id=1 AND feature_key='inbox'
        """)
        conn.commit()
        conn.close()

        # service-level duplicate via save
        result = save_email_message(normalize_inbox_payload(valid_payload()))
        assert not result["created"]
        assert result["message"]["id"] == message_id

        # --- draft confirmation flow ---

        def authed_request(path, username="boss", form=None):
            body = urlencode(form).encode() if form is not None else b""
            headers = [(
                b"cookie",
                f"{crm.SESSION_COOKIE_NAME}={crm.sign_session_value(username)}".encode(),
            )]
            if form is not None:
                headers.append((
                    b"content-type",
                    b"application/x-www-form-urlencoded",
                ))
            scope = {
                "type": "http",
                "method": "POST" if form is not None else "GET",
                "path": path,
                "headers": headers,
                "query_string": b"",
                "scheme": "http",
                "client": ("127.0.0.1", 50000),
                "server": ("testserver", 80),
            }

            async def receive():
                return {
                    "type": "http.request",
                    "body": body,
                    "more_body": False,
                }

            return Request(scope, receive)

        detail = asyncio.run(crm.inbox_detail_page(
            authed_request(f"/inbox/{message_id}"), message_id
        ))
        assert detail.status_code == 200
        assert "Нужен ремонт стиральной машины" in detail.body.decode()
        assert "Свободные окна" in detail.body.decode()

        # worker cannot open inbox detail
        forbidden = asyncio.run(crm.inbox_detail_page(
            authed_request(f"/inbox/{message_id}", username="worker"), message_id
        ))
        assert forbidden.status_code == 302
        assert forbidden.headers["location"] == "/"

        # unknown message -> back to inbox
        missing = asyncio.run(crm.inbox_detail_page(
            authed_request("/inbox/999999"), 999999
        ))
        assert missing.status_code == 302
        assert missing.headers["location"] == "/inbox"

        # client name is required
        empty_client = asyncio.run(crm.inbox_confirm(
            authed_request(f"/inbox/{message_id}/confirm", form={
                "client_name": "",
                "phone": "+79001112233",
            }),
            message_id,
        ))
        assert empty_client.status_code == 302
        assert "error=client_required" in empty_client.headers["location"]

        # invalid date rejected
        bad_date = asyncio.run(crm.inbox_confirm(
            authed_request(f"/inbox/{message_id}/confirm", form={
                "client_name": "Тест Клиент",
                "task_date": "32.13.2026",
            }),
            message_id,
        ))
        assert "error=invalid_date" in bad_date.headers["location"]

        # confirm creates client + task only after manager approval
        confirmed = asyncio.run(crm.inbox_confirm(
            authed_request(f"/inbox/{message_id}/confirm", form={
                "client_name": "Тест Клиент",
                "phone": "+79001112233",
                "email": "client@example.com",
                "address": "Ленина 10",
                "task_date": "2026-10-01",
                "description": "Ремонт стиральной машины",
                "price": "1500",
            }),
            message_id,
        ))
        assert confirmed.status_code == 302
        location = confirmed.headers["location"]
        assert location.startswith("/task/")
        task_id = int(location.rsplit("/", 1)[1])

        conn = connect()
        c = conn.cursor()
        task = c.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
        saved_message = c.execute(
            "SELECT * FROM email_messages WHERE id=?", (message_id,)
        ).fetchone()
        activity = c.execute("""
        SELECT * FROM task_activity WHERE task_id=? AND action='Создано из письма'
        """, (task_id,)).fetchone()
        conn.close()

        assert task["company_id"] == 1
        assert task["client"] == "Тест Клиент"
        assert task["status"] == "Новая"
        assert task["task_date"] == "2026-10-01"
        assert saved_message["status"] == "confirmed"
        assert saved_message["task_id"] == task_id
        assert saved_message["client_id"] == task["client_id"]
        assert activity is not None

        # already processed -> no duplicate task
        again = asyncio.run(crm.inbox_confirm(
            authed_request(f"/inbox/{message_id}/confirm", form={
                "client_name": "Тест Клиент",
            }),
            message_id,
        ))
        assert again.headers["location"] == "/inbox"

        # same phone -> same client, no duplicates
        client_id = task["client_id"]
        assert find_or_create_inbox_client(
            1, "Тест Клиент", "+79001112233", "", ""
        ) == client_id

        # reject flow
        rejected = call(valid_payload(message_id="<msg-003@test>"))
        reject_id = rejected["id"]
        reject_response = asyncio.run(crm.inbox_reject(
            authed_request(f"/inbox/{reject_id}/reject", form={}),
            reject_id,
        ))
        assert reject_response.status_code == 302
        conn = connect()
        c = conn.cursor()
        rejected_message = c.execute(
            "SELECT status FROM email_messages WHERE id=?", (reject_id,)
        ).fetchone()
        conn.close()
        assert rejected_message["status"] == "rejected"

        # free slot suggestions respect worker capacity
        slots = suggest_inbox_slots(1, "2026-09-28")
        assert slots
        assert slots[0]["date"] == "2026-09-28"
        assert slots[0]["worker"] == "worker"
        assert slots[0]["free_slots"] == 3

        conn = connect()
        c = conn.cursor()
        c.execute("""
        INSERT INTO tasks (company_id, worker, task_date, status)
        VALUES (1, 'worker', '2026-10-02', 'Новая')
        """)
        conn.commit()
        conn.close()

        slots = suggest_inbox_slots(1, "2026-10-02")
        assert slots[0]["date"] == "2026-10-02"
        assert slots[0]["free_slots"] == 2

        assert suggest_inbox_slots(999999, "2026-10-02") == []

        # inbox page: unauthenticated -> redirect to login
        anon_request = FakeInboxRequest({}, token="")
        anon_request.scope_path = "/inbox"
        page_response = asyncio.run(crm.inbox_page(anon_request))
        assert page_response.status_code == 302

        # inbox template renders with real messages
        from types import SimpleNamespace

        template = crm.templates.get_template("inbox.html")
        html = template.render(
            request=SimpleNamespace(url=SimpleNamespace(path="/inbox")),
            username="boss",
            role="boss",
            settings={"task_label": "Заявка", "client_label": "Клиент"},
            links=crm.build_dashboard_links(),
            messages=messages,
            selected_status="",
        )
        assert "Нужен ремонт стиральной машины" in html
        assert "client@example.com" in html

        # missing secret configuration -> 503
        with patch.dict(os.environ, {"INBOX_WEBHOOK_SECRET": ""}, clear=False):
            response = call(valid_payload())
            assert response.status_code == 503

    print("Email inbox smoke passed.")


if __name__ == "__main__":
    main()
