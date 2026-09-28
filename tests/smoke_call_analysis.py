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
            "SECRET_KEY": "call-analysis-smoke-secret",
            "DATABASE_BACKEND": "sqlite",
            "DATABASE_URL": "",
        },
        clear=False,
    ):
        from app import main as crm
        from app.database import connect
        from app.services.call_analysis import analyze_call_text

        def request_with_user(path, username="boss", form=None):
            body = urlencode(form).encode() if form is not None else b""
            headers = [(
                b"cookie",
                f"{crm.SESSION_COOKIE_NAME}="
                f"{crm.sign_session_value(username)}".encode(),
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

        # analyzer rules
        positive = analyze_call_text(
            "Клиент доволен, всё отлично. Оплатил предоплату.",
            "Спасибо большое! Записали на пятницу.",
            "",
        )
        assert positive["sentiment"] == "positive"
        assert positive["sale_detected"]
        assert not positive["follow_up_detected"]

        negative = analyze_call_text(
            "Клиент недоволен: опоздали, дорого. Обещали перезвонить завтра.",
            "",
            "",
        )
        assert negative["sentiment"] == "negative"
        assert negative["follow_up_detected"]
        assert "перезвонить" in negative["follow_up_text"].lower()

        neutral = analyze_call_text("Уточнили адрес и время.", "", "")
        assert neutral["sentiment"] == "neutral"
        assert neutral["follow_up_detected"]  # "уточнить" marker
        assert not neutral["sale_detected"]

        empty = analyze_call_text("", "", "")
        assert empty["sentiment"] == ""
        assert not empty["sale_detected"]
        assert not empty["follow_up_detected"]

        # enable calls + ai for company 1
        conn = connect()
        c = conn.cursor()
        c.execute("""
        UPDATE company_settings
        SET calls_enabled=1, ai_calls_enabled=1
        WHERE company_id=1
        """)
        c.execute("""
        INSERT INTO call_records (
            company_id, username, direction, status, phone, summary, call_at
        )
        VALUES (1, 'boss', 'incoming', 'completed', '+79001112233',
                'Клиент доволен.', '2026-09-28 10:00')
        """)
        conn.commit()
        call_id = c.lastrowid
        conn.close()

        response = asyncio.run(crm.update_call_analysis(
            request_with_user(f"/calls/{call_id}/analysis", form={
                "transcript": (
                    "Спасибо! Всё отлично. Клиент оплатил счёт. "
                    "Обещала прислать адрес электронной почтой завтра."
                ),
                "ai_summary": "Продажа, нужно высылать договор.",
            }),
            call_id,
        ))
        assert response.status_code == 302

        conn = connect()
        c = conn.cursor()
        call = c.execute(
            "SELECT * FROM call_records WHERE id=?", (call_id,)
        ).fetchone()
        conn.close()

        assert call["ai_sentiment"] == "positive"
        assert call["ai_sale_detected"] == 1
        assert call["ai_follow_up_detected"] == 1
        assert call["status"] == "follow_up"

        # empty analysis resets detection, keeps user status
        response = asyncio.run(crm.update_call_analysis(
            request_with_user(f"/calls/{call_id}/analysis", form={
                "transcript": "",
                "ai_summary": "",
            }),
            call_id,
        ))
        assert response.status_code == 302

        conn = connect()
        c = conn.cursor()
        call = c.execute(
            "SELECT * FROM call_records WHERE id=?", (call_id,)
        ).fetchone()
        conn.close()

        # summary text keeps sentiment; detection resets with empty analysis
        assert call["ai_sentiment"] == "positive"
        assert call["ai_sale_detected"] == 0
        assert call["ai_follow_up_detected"] == 0
        assert call["status"] == "follow_up"

        # analysis disabled -> values stay empty
        conn = connect()
        c = conn.cursor()
        c.execute("""
        UPDATE company_settings
        SET ai_calls_enabled=0
        WHERE company_id=1
        """)
        c.execute("""
        INSERT INTO call_records (
            company_id, username, direction, status, phone, summary
        )
        VALUES (1, 'boss', 'incoming', 'completed', '+79002223344', 'Тест')
        """)
        conn.commit()
        second_call_id = c.lastrowid
        conn.close()

        response = asyncio.run(crm.update_call_analysis(
            request_with_user(f"/calls/{second_call_id}/analysis", form={
                "transcript": "Спасибо, всё отлично!",
                "ai_summary": "Продажа!",
            }),
            second_call_id,
        ))
        assert response.status_code == 302

        conn = connect()
        c = conn.cursor()
        call = c.execute(
            "SELECT * FROM call_records WHERE id=?", (second_call_id,)
        ).fetchone()
        conn.close()

        assert call["ai_sentiment"] == ""
        assert call["ai_sale_detected"] == 0
        assert call["status"] == "completed"

        # detail page renders analysis badges
        detail = asyncio.run(crm.call_detail(
            request_with_user(f"/calls/{call_id}"), call_id
        ))
        assert detail.status_code == 200
        page = detail.body.decode()
        assert "Настроение клиента" in page
        assert "Позитивное" in page

    print("Call analysis smoke passed.")


if __name__ == "__main__":
    main()
