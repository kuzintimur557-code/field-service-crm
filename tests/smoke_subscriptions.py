import asyncio
import os
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    with tempfile.TemporaryDirectory() as temp_dir, patch.dict(
        os.environ,
        {
            "DATA_DIR": temp_dir,
            "SECRET_KEY": "subscription-smoke-secret",
            "DATABASE_BACKEND": "sqlite",
            "DATABASE_URL": "",
        },
        clear=False,
    ):
        from app import main as crm
        from app.database import connect
        from app.services.subscriptions import (
            SUBSCRIPTION_ACTIVE,
            SUBSCRIPTION_CANCELED,
            SUBSCRIPTION_PAST_DUE,
            TRIAL_DAYS,
            activate_company_subscription,
            ensure_company_subscription,
            get_company_subscription,
            run_subscription_reminders,
        )

        # trial starts automatically for a company without subscription
        subscription = ensure_company_subscription(1)
        assert subscription["status"] == "trial"
        assert subscription["is_open"]
        assert subscription["label"] == "Пробный период"
        assert subscription["days_left"] is not None
        assert 1 <= subscription["days_left"] <= TRIAL_DAYS
        assert subscription["trial_ends_at"]

        # repeated calls do not reset the trial
        trial_ends_at = subscription["trial_ends_at"]
        subscription = ensure_company_subscription(1)
        assert subscription["trial_ends_at"] == trial_ends_at

        # activation moves company to active paid period
        subscription = activate_company_subscription(1, days=30)
        assert subscription["status"] == SUBSCRIPTION_ACTIVE
        assert subscription["is_open"]
        assert subscription["subscription_ends_at"]

        # expired trial closes access
        conn = connect()
        c = conn.cursor()
        c.execute("""
        UPDATE company_settings
        SET subscription_status='trial',
            trial_ends_at=?,
            subscription_ends_at=''
        WHERE company_id=1
        """, ((datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d"),))
        conn.commit()
        conn.close()

        subscription = get_company_subscription(1)
        assert not subscription["is_open"]
        assert subscription["days_left"] == 0

        # past_due and canceled are closed as well
        conn = connect()
        c = conn.cursor()
        c.execute("""
        UPDATE company_settings
        SET subscription_status='past_due'
        WHERE company_id=1
        """)
        conn.commit()
        conn.close()
        assert not get_company_subscription(1)["is_open"]

        conn = connect()
        c = conn.cursor()
        c.execute("""
        UPDATE company_settings
        SET subscription_status='canceled'
        WHERE company_id=1
        """)
        conn.commit()
        conn.close()
        subscription = get_company_subscription(1)
        assert subscription["status"] == SUBSCRIPTION_CANCELED
        assert not subscription["is_open"]
        assert subscription["label"] == "Отменена"

        # unknown status falls back to trial-open on read
        conn = connect()
        c = conn.cursor()
        c.execute("""
        UPDATE company_settings
        SET subscription_status='weird',
            trial_ends_at=?,
            subscription_ends_at=''
        WHERE company_id=1
        """, ((datetime.now() + timedelta(days=5)).strftime("%Y-%m-%d"),))
        conn.commit()
        conn.close()
        subscription = get_company_subscription(1)
        assert subscription["status"] == "trial"
        assert subscription["is_open"]

        # billing page shows subscription status
        subscription = activate_company_subscription(1, days=30)

        from starlette.requests import Request

        def authed_request(path):
            return Request({
                "type": "http",
                "method": "GET",
                "path": path,
                "headers": [(
                    b"cookie",
                    f"{crm.SESSION_COOKIE_NAME}="
                    f"{crm.sign_session_value('boss')}".encode(),
                )],
                "query_string": b"",
                "scheme": "http",
                "client": ("127.0.0.1", 50000),
                "server": ("testserver", 80),
            })

        page = asyncio.run(crm.billing_page(authed_request("/billing")))
        assert page.status_code == 200
        html = page.body.decode()
        assert "Подписка" in html
        assert "Активна" in html

        # reminder cron: trial ending soon notifies boss once per day
        conn = connect()
        c = conn.cursor()
        c.execute("""
        UPDATE company_settings
        SET subscription_status='trial',
            trial_ends_at=?,
            subscription_ends_at=''
        WHERE company_id=1
        """, ((datetime.now() + timedelta(days=3)).strftime("%Y-%m-%d"),))
        conn.commit()
        conn.close()

        summary = run_subscription_reminders()
        assert summary["sent"] >= 1

        conn = connect()
        c = conn.cursor()
        reminder_count = c.execute("""
        SELECT COUNT(*) AS count
        FROM notifications
        WHERE company_id=1 AND title='Пробный период заканчивается'
        """).fetchone()["count"]
        conn.close()
        assert reminder_count >= 1

        # same-day second run does not duplicate
        summary = run_subscription_reminders()
        conn = connect()
        c = conn.cursor()
        reminder_count_again = c.execute("""
        SELECT COUNT(*) AS count
        FROM notifications
        WHERE company_id=1 AND title='Пробный период заканчивается'
        """).fetchone()["count"]
        conn.close()
        assert reminder_count_again == reminder_count

        # past due owners get the overdue reminder
        conn = connect()
        c = conn.cursor()
        c.execute("""
        UPDATE company_settings
        SET subscription_status='past_due'
        WHERE company_id=1
        """)
        conn.commit()
        conn.close()

        summary = run_subscription_reminders()
        assert summary["sent"] >= 1

        conn = connect()
        c = conn.cursor()
        overdue_count = c.execute("""
        SELECT COUNT(*) AS count
        FROM notifications
        WHERE company_id=1 AND title='Подписка просрочена'
        """).fetchone()["count"]
        conn.close()
        assert overdue_count == 1

        # cron endpoint guard
        from starlette.requests import Request as StarletteRequest

        def cron_request(token=""):
            headers = []
            if token:
                headers.append((b"x-automation-secret", token.encode()))
            return StarletteRequest({
                "type": "http",
                "method": "POST",
                "path": "/automation/cron/subscription-reminders",
                "headers": headers,
                "query_string": b"",
                "scheme": "http",
                "client": ("127.0.0.1", 50000),
                "server": ("testserver", 80),
            })

        with patch.dict(
            os.environ,
            {"AUTOMATION_CRON_SECRET": "cron-smoke-secret"},
            clear=False,
        ):
            response = asyncio.run(
                crm.run_subscription_reminders_cron(cron_request("wrong"))
            )
            assert response.status_code == 403

            response = asyncio.run(
                crm.run_subscription_reminders_cron(cron_request(""))
            )
            assert response.status_code == 403

            response = asyncio.run(
                crm.run_subscription_reminders_cron(
                    cron_request("cron-smoke-secret")
                )
            )
            assert response["ok"] and "summary" in response

    print("Subscription smoke passed.")


if __name__ == "__main__":
    main()
