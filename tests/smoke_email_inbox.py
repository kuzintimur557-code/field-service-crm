import asyncio
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


INBOX_SECRET = "inbox-smoke-secret"


class FakeInboxRequest:
    def __init__(self, payload, token=INBOX_SECRET, broken_json=False):
        self._payload = payload
        self._broken_json = broken_json
        self.headers = {}
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
            get_email_messages,
            normalize_inbox_payload,
            save_email_message,
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

        messages = get_email_messages(1)
        assert len(messages) == 1
        assert messages[0]["status"] == "new"
        assert messages[0]["subject"] == "Нужен ремонт стиральной машины"
        assert messages[0]["raw_source"]

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
