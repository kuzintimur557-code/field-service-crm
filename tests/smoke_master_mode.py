import asyncio
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch
from urllib.parse import urlencode

from starlette.requests import Request


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    with tempfile.TemporaryDirectory() as temp_dir, patch.dict(
        os.environ,
        {
            "DATA_DIR": temp_dir,
            "SECRET_KEY": "master-mode-smoke-secret",
            "DATABASE_BACKEND": "sqlite",
            "DATABASE_URL": "",
        },
        clear=False,
    ):
        from app import main as crm
        from app.database import connect

        def request_with_user(
            path, username=None, password=None, form=None, method=None
        ):
            if username is not None and password is not None:
                body = urlencode({
                    "username": username,
                    "password": password,
                }).encode()
                headers = [(
                    b"content-type",
                    b"application/x-www-form-urlencoded",
                )]
            else:
                body = urlencode(form).encode() if form is not None else b""
                headers = []

                if username is not None:
                    headers.append((
                        b"cookie",
                        f"{crm.SESSION_COOKIE_NAME}="
                        f"{crm.sign_session_value(username)}".encode(),
                    ))

                if form is not None:
                    headers.append((
                        b"content-type",
                        b"application/x-www-form-urlencoded",
                    ))

            if method is None:
                method = "POST" if body else "GET"

            scope = {
                "type": "http",
                "method": method,
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

        # default mode: boss lands on the dashboard
        response = asyncio.run(crm.login(
            request_with_user("/login", username="boss", password="boss123")
        ))
        assert response.status_code == 302
        assert response.headers["location"] == "/"

        # settings form switches the company to master mode
        response = asyncio.run(crm.update_settings(
            request_with_user("/settings", username="boss", form={
                "company_name": "",
                "phone": "",
                "email": "",
                "telegram_chat_id": "",
                "address": "",
                "tax_number": "",
                "bank_details": "",
                "plan": "basic",
                "industry": "field_service",
                "task_label": "Заявка",
                "worker_label": "Исполнитель",
                "client_label": "Клиент",
                "service_label": "Услуга",
                "mode": "master",
            })
        ))
        assert response.status_code == 302

        conn = connect()
        c = conn.cursor()
        mode = c.execute(
            "SELECT mode FROM company_settings WHERE company_id=1"
        ).fetchone()["mode"]
        conn.close()
        assert mode == "master"

        # login now lands on the master today page
        response = asyncio.run(crm.login(
            request_with_user("/login", username="boss", password="boss123")
        ))
        assert response.headers["location"] == "/master"

        # master today page renders stats and actions
        conn = connect()
        c = conn.cursor()
        c.execute("""
        INSERT INTO tasks (
            company_id, client, phone, task_date, time_from, status, price
        )
        VALUES (1, 'Клиент Мастера', '+79001112233',
                datetime('now', 'localtime'), '10:00', 'Новая', '2000')
        """)
        conn.commit()
        conn.close()

        page = asyncio.run(crm.master_today_page(
            request_with_user("/master", username="boss")
        ))
        assert page.status_code == 200
        html = page.body.decode()
        assert "Сегодня" in html
        assert "Клиент Мастера" in html
        assert "Новая запись" in html
        assert "Голос" in html
        assert "Клиенты" in html
        assert "Деньги" in html

        # voice page renders the capture form
        page = asyncio.run(crm.master_voice_page(
            request_with_user("/master/voice", username="boss")
        ))
        assert page.status_code == 200
        assert "Говорить" in page.body.decode()
        assert "/ai/assistant/notes" in page.body.decode()

        # workers stay on their own panel
        response = asyncio.run(crm.master_today_page(
            request_with_user("/master", username="worker")
        ))
        assert response.status_code == 302
        assert response.headers["location"] == "/"

        # invalid mode values fall back to company
        response = asyncio.run(crm.update_settings(
            request_with_user("/settings", username="boss", form={
                "plan": "basic",
                "industry": "field_service",
                "mode": "hacker",
            })
        ))
        assert response.status_code == 302

        conn = connect()
        c = conn.cursor()
        mode = c.execute(
            "SELECT mode FROM company_settings WHERE company_id=1"
        ).fetchone()["mode"]
        conn.close()
        assert mode == "company"

    print("Master mode smoke passed.")


if __name__ == "__main__":
    main()
