import atexit
import asyncio
import os
import sys
import tempfile
from datetime import datetime, timedelta
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

from starlette.requests import Request
from starlette.responses import Response


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

TEMP_DATA = tempfile.TemporaryDirectory()
atexit.register(TEMP_DATA.cleanup)
os.environ["DATA_DIR"] = TEMP_DATA.name
os.environ["SECRET_KEY"] = "smoke-security-secret"

from app import main as crm  # noqa: E402


def make_request(path="/", cookies=None, method="GET", extra_headers=None):
    headers = list(extra_headers or [])

    if cookies:
        cookie_header = "; ".join(
            f"{key}={value}" for key, value in cookies.items()
        )
        headers.append((b"cookie", cookie_header.encode("utf-8")))

    return Request({
        "type": "http",
        "method": method,
        "path": path,
        "headers": headers,
        "query_string": b"",
        "scheme": "http",
        "client": ("127.0.0.1", 50000),
        "server": ("testserver", 80),
    })


def test_fake_user_cookie_does_not_login():
    request = make_request("/", {"user": "boss"})
    assert crm.get_user(request) is None


def test_owner_cannot_access_other_company_task():
    response = asyncio.run(
        crm.task_detail(
            make_request("/task/1", {"user": "owner"}),
            1,
        )
    )
    assert response.status_code == 302
    assert response.headers["location"].startswith("/login")


def test_uploads_require_auth():
    response = asyncio.run(
        crm.uploaded_file(make_request("/uploads/test.jpg"), "test.jpg")
    )
    assert response.status_code == 404


def test_sessions_expire_and_revoke():
    now = datetime(2026, 9, 20, 12, 0, 0)
    valid = crm.sign_session_value("boss", issued_at=now)
    decoded = crm.verify_session_value(valid, now=now)
    assert decoded["username"] == "boss"
    assert decoded["session_version"] == 1

    expired = crm.sign_session_value(
        "boss",
        issued_at=now - timedelta(
            seconds=crm.SESSION_COOKIE_MAX_AGE_SECONDS + 1,
        ),
    )
    assert crm.verify_session_value(expired, now=now) is None
    assert crm.verify_session_value(valid + "tampered", now=now) is None

    connection = crm.connect()
    connection.execute("""
        UPDATE users SET session_version=session_version + 1
        WHERE username='boss'
    """)
    connection.commit()
    connection.close()
    assert crm.get_user(make_request(
        "/",
        {crm.SESSION_COOKIE_NAME: valid},
    )) is None


def test_cross_site_and_request_size_guards():
    from app.security import (
        get_cross_site_request_error,
        get_request_size_error,
        get_security_runtime_config,
        require_valid_production_security,
        SecurityConfigurationError,
    )

    assert get_cross_site_request_error(
        "POST",
        {"host": "crm.example", "origin": "https://evil.example"},
    ) == "origin_not_allowed"
    assert get_cross_site_request_error(
        "POST",
        {"host": "crm.example", "origin": "https://crm.example"},
    ) == ""
    assert get_cross_site_request_error(
        "POST",
        {"host": "crm.example", "sec-fetch-site": "cross-site"},
    ) == "cross_site_request_blocked"
    assert get_cross_site_request_error(
        "POST",
        {"host": "crm.example"},
    ) == ""
    assert get_request_size_error(
        {"content-length": "101"},
        100,
    ) == "request_too_large"
    assert get_request_size_error(
        {"content-length": "invalid"},
        100,
    ) == "invalid_content_length"
    assert get_request_size_error(
        {"content-length": "-1"},
        100,
    ) == "invalid_content_length"
    spoofed_ip_request = make_request(
        "/login",
        extra_headers=[(b"x-forwarded-for", b"203.0.113.99")],
    )
    with patch.dict(os.environ, {
        "TRUST_PROXY_HEADERS": "0",
        "RAILWAY_ENVIRONMENT": "",
    }, clear=False):
        assert crm.get_request_ip(spoofed_ip_request) == "127.0.0.1"

    with patch.dict(os.environ, {
        "ENV": "production",
        "SECRET_KEY": "short",
        "COOKIE_SECURE": "0",
        "TRUSTED_HOSTS": "",
        "RAILWAY_ENVIRONMENT": "",
        "APP_BASE_URL": "",
    }, clear=False):
        invalid = get_security_runtime_config()
        assert invalid["docs_enabled"] is False
        assert "trusted_hosts_required" in invalid["errors"]
        assert "strong_secret_key_required" in invalid["errors"]
        assert "secure_cookie_required" in invalid["errors"]
        try:
            require_valid_production_security(invalid)
        except SecurityConfigurationError:
            pass
        else:
            raise AssertionError("Invalid production security was accepted")

    with patch.dict(os.environ, {
        "ENV": "production",
        "SECRET_KEY": "s" * 32,
        "COOKIE_SECURE": "1",
        "TRUSTED_HOSTS": "crm.example,www.crm.example",
        "APP_BASE_URL": "https://crm.example",
        "RAILWAY_ENVIRONMENT": "",
    }, clear=False):
        production = require_valid_production_security()
        assert production["configuration_valid"] is True
        assert production["docs_enabled"] is False
        assert production["cookie_secure"] is True
        assert production["trusted_hosts"] == [
            "crm.example",
            "www.crm.example",
        ]
        assert production["csrf_trusted_origins"] == [
            "https://crm.example",
        ]

    with patch.dict(os.environ, {
        "ENV": "production",
        "SECRET_KEY": "s" * 32,
        "COOKIE_SECURE": "0",
        "TRUSTED_HOSTS": "crm.example",
        "APP_BASE_URL": "https://crm.example",
        "RAILWAY_ENVIRONMENT": "production",
    }, clear=False):
        railway = require_valid_production_security()
        assert railway["cookie_secure"] is True
        assert "healthcheck.railway.app" in railway["trusted_hosts"]

    with patch.dict(os.environ, {
        "ENV": "production",
        "SECRET_KEY": "s" * 32,
        "COOKIE_SECURE": "0",
        "TRUSTED_HOSTS": "",
        "APP_BASE_URL": "",
        "RAILWAY_PUBLIC_DOMAIN": "",
        "RAILWAY_STATIC_URL": "",
        "RAILWAY_ENVIRONMENT": "production",
    }, clear=False):
        railway_without_public_host = get_security_runtime_config()
        assert "healthcheck.railway.app" in railway_without_public_host[
            "trusted_hosts"
        ]
        assert "trusted_hosts_required" in railway_without_public_host["errors"]


def test_security_middleware_and_headers():
    called = {"value": False}

    async def call_next(_request):
        called["value"] = True
        return Response("ok")

    blocked = asyncio.run(crm.security_headers_middleware(
        make_request(
            "/profile/password",
            method="POST",
            extra_headers=[
                (b"host", b"crm.example"),
                (b"origin", b"https://evil.example"),
            ],
        ),
        call_next,
    ))
    assert blocked.status_code == 403
    assert called["value"] is False
    assert blocked.headers["x-frame-options"] == "DENY"
    assert "frame-ancestors 'none'" in blocked.headers[
        "content-security-policy"
    ]

    allowed = asyncio.run(crm.security_headers_middleware(
        make_request(
            "/system",
            method="POST",
            extra_headers=[
                (b"host", b"crm.example"),
                (b"origin", b"https://crm.example"),
            ],
        ),
        call_next,
    ))
    assert allowed.status_code == 200
    assert called["value"] is True
    assert allowed.headers["cache-control"] == "no-store"
    assert allowed.headers["cross-origin-opener-policy"] == "same-origin"


def test_password_and_upload_policy():
    assert crm.is_password_strong("secure123") is True
    assert crm.is_password_strong("onlyletters") is False
    assert crm.is_password_strong("12345678") is False
    assert crm.is_password_strong("a1short") is False
    assert crm.verify_password("x" * 80, crm.hash_password("secure123")) is False

    valid_upload = crm.UploadFile(
        file=BytesIO(b"small image"),
        filename="safe.jpg",
    )
    assert crm.validate_upload_file(
        valid_upload,
        crm.ALLOWED_IMAGE_EXTENSIONS,
        100,
    ) == ".jpg"
    invalid_type = crm.UploadFile(
        file=BytesIO(b"html"),
        filename="attack.html",
    )
    try:
        crm.validate_upload_file(
            invalid_type,
            crm.ALLOWED_IMAGE_EXTENSIONS,
            100,
        )
    except crm.UploadValidationError as error:
        assert error.code == "type"
    else:
        raise AssertionError("Invalid upload extension accepted")
    oversized = crm.UploadFile(
        file=BytesIO(b"x" * 101),
        filename="large.jpg",
    )
    try:
        crm.validate_upload_file(
            oversized,
            crm.ALLOWED_IMAGE_EXTENSIONS,
            100,
        )
    except crm.UploadValidationError as error:
        assert error.code == "size"
    else:
        raise AssertionError("Oversized upload accepted")

    assert not (ROOT / "app/routes/auth.py").exists()
    assert not (ROOT / "app/routes/tasks.py").exists()


if __name__ == "__main__":
    test_fake_user_cookie_does_not_login()
    test_owner_cannot_access_other_company_task()
    test_uploads_require_auth()
    test_sessions_expire_and_revoke()
    test_cross_site_and_request_size_guards()
    test_security_middleware_and_headers()
    test_password_and_upload_policy()
    print(
        "OK: production security smoke passed: sessions, CSRF/Origin, "
        "headers, request limits, passwords, uploads and tenant access."
    )
