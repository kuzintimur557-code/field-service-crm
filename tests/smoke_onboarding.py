import asyncio
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

from starlette.requests import Request


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    with tempfile.TemporaryDirectory() as temp_dir, patch.dict(
        os.environ,
        {
            "DATA_DIR": temp_dir,
            "SECRET_KEY": "onboarding-smoke-secret",
            "DATABASE_BACKEND": "sqlite",
            "DATABASE_URL": "",
        },
        clear=False,
    ):
        from app import main as crm
        from app.database import connect
        from app.services.subscriptions import activate_company_subscription

        def authed_request(path, username="boss"):
            return Request({
                "type": "http",
                "method": "GET",
                "path": path,
                "headers": [(
                    b"cookie",
                    f"{crm.SESSION_COOKIE_NAME}="
                    f"{crm.sign_session_value(username)}".encode(),
                )],
                "query_string": b"",
                "scheme": "http",
                "client": ("127.0.0.1", 50000),
                "server": ("testserver", 80),
            })

        # fresh company: only the seeded demo worker counts as done
        page = asyncio.run(crm.onboarding_page(authed_request("/onboarding")))
        assert page.status_code == 200
        html = page.body.decode()
        assert "Первый запуск" in html
        assert "Готово шагов: 1 из 5" in html
        assert "Заполнить профиль компании" in html

        # worker has no access to onboarding
        response = asyncio.run(crm.onboarding_page(
            authed_request("/onboarding", username="worker")
        ))
        assert response.status_code == 302
        assert response.headers["location"] == "/"

        # complete steps one by one
        conn = connect()
        c = conn.cursor()
        c.execute("""
        UPDATE company_settings
        SET company_name='Тестовая компания'
        WHERE company_id=1
        """)
        c.execute("""
        INSERT INTO clients (company_id, name, phone, created_at)
        VALUES (1, 'Первый клиент', '+79001112233', '2026-09-28 10:00')
        """)
        c.execute("""
        INSERT INTO tasks (company_id, client, status, task_date)
        VALUES (1, 'Первый клиент', 'Новая', '2026-09-28')
        """)
        conn.commit()
        conn.close()

        page = asyncio.run(crm.onboarding_page(authed_request("/onboarding")))
        html = page.body.decode()
        assert "Готово шагов: 4 из 5" in html

        activate_company_subscription(1, days=30)

        conn = connect()
        c = conn.cursor()
        c.execute("""
        INSERT INTO users (username, password, role, company_id, last_seen)
        VALUES ('master-ivan', 'x', 'worker', 1, '2026-09-28 10:00')
        """)
        conn.commit()
        conn.close()

        page = asyncio.run(crm.onboarding_page(authed_request("/onboarding")))
        html = page.body.decode()
        assert "Готово шагов: 5 из 5" in html
        assert "Всё настроено" in html

    print("Onboarding smoke passed.")


if __name__ == "__main__":
    main()
