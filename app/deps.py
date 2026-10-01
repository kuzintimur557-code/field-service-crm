"""Shared request dependencies: sessions, authentication, tenant context.

Extracted from app.main so domain routers can import them without a
circular dependency on the application module.
"""

import base64
import hashlib
import hmac
import os
from datetime import datetime

from fastapi.responses import RedirectResponse
from starlette.requests import Request

from app.database import connect

SESSION_COOKIE_MAX_AGE_SECONDS = 60 * 60 * 24 * 7
SESSION_CLOCK_SKEW_SECONDS = 300
SESSION_COOKIE_NAME = "crm_session"

SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-change-me")


def get_user_session_version(username):
    connection = connect()
    row = connection.execute("""
        SELECT session_version
        FROM users
        WHERE username=?
    """, (username,)).fetchone()
    connection.close()
    return max(1, int(row["session_version"] or 1)) if row else 1


def sign_session_value(username, session_version=None, issued_at=None):
    username = str(username or "").strip()
    if not username or len(username) > 120:
        raise ValueError("Invalid session username")
    if session_version is None:
        session_version = get_user_session_version(username)
    session_version = max(1, int(session_version or 1))
    issued_value = issued_at or datetime.now()
    issued_timestamp = int(
        issued_value.timestamp()
        if hasattr(issued_value, "timestamp")
        else issued_value
    )
    raw = f"{issued_timestamp}:{session_version}:{username}".encode("utf-8")
    token = base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")
    signature = hmac.new(
        SECRET_KEY.encode("utf-8"),
        token.encode("ascii"),
        hashlib.sha256
    ).digest()
    sig = base64.urlsafe_b64encode(signature).decode("ascii").rstrip("=")
    return f"v1.{token}.{sig}"


def verify_session_value(value, now=None):
    if not value or len(str(value)) > 1024:
        return None

    try:
        version, token, sig = str(value).split(".", 2)
        if version != "v1":
            return None
        expected_signature = hmac.new(
            SECRET_KEY.encode("utf-8"),
            token.encode("ascii"),
            hashlib.sha256
        ).digest()
        expected_sig = base64.urlsafe_b64encode(
            expected_signature,
        ).decode("ascii").rstrip("=")
        if not hmac.compare_digest(sig, expected_sig):
            return None
        padding = "=" * (-len(token) % 4)
        payload = base64.urlsafe_b64decode(
            (token + padding).encode("ascii"),
        ).decode("utf-8")
        issued_text, session_version_text, username = payload.split(":", 2)
        issued_timestamp = int(issued_text)
        session_version = int(session_version_text)
        now_timestamp = int(
            (now or datetime.now()).timestamp()
            if hasattr(now or datetime.now(), "timestamp")
            else now
        )
        if (
            not username
            or len(username) > 120
            or session_version < 1
            or issued_timestamp > now_timestamp + SESSION_CLOCK_SKEW_SECONDS
            or now_timestamp - issued_timestamp > SESSION_COOKIE_MAX_AGE_SECONDS
        ):
            return None
        return {
            "username": username,
            "session_version": session_version,
            "issued_at": issued_timestamp,
        }
    except (TypeError, ValueError, UnicodeError, base64.binascii.Error):
        return None


def get_user(request: Request):
    signed_value = request.cookies.get(SESSION_COOKIE_NAME)
    session = verify_session_value(signed_value)

    if not session:
        return None

    username = session["username"]

    conn = connect()
    c = conn.cursor()
    user = c.execute("""
    SELECT is_active, session_version
    FROM users
    WHERE username=?
    """, (username,)).fetchone()
    conn.close()

    if (
        not user
        or user["is_active"] == 0
        or int(user["session_version"] or 1) != session["session_version"]
    ):
        return None

    return username


def is_superadmin(role):
    return role == "superadmin"


def get_user_company_id(username):
    conn = connect()
    c = conn.cursor()

    user = c.execute("""
    SELECT company_id
    FROM users
    WHERE username=?
    """, (username,)).fetchone()

    conn.close()

    if not user:
        return None

    return user["company_id"] if "company_id" in user.keys() else None


def missing_company_context_response(role):
    target = "/platform" if role == "superadmin" else "/"
    return RedirectResponse(target, status_code=302)


def require_route_company_context(username, role):
    company_id = get_user_company_id(username)

    if company_id:
        return company_id, None

    return None, missing_company_context_response(role)


def get_role(username):
    conn = connect()
    c = conn.cursor()

    user = c.execute("""
    SELECT * FROM users
    WHERE username=?
    """, (username,)).fetchone()

    conn.close()

    if not user:
        return None

    return user["role"]


def update_last_seen(username):
    conn = connect()
    c = conn.cursor()

    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    row = c.execute("""
    SELECT last_seen
    FROM users
    WHERE username=?
    """, (username,)).fetchone()

    if row and row["last_seen"] == now:
        conn.close()
        return

    c.execute("""
    UPDATE users
    SET last_seen=?
    WHERE username=?
    """, (
        now,
        username
    ))

    conn.commit()
    conn.close()
