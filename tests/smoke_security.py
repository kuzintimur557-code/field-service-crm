import atexit
import asyncio
import os
import sys
import tempfile
from pathlib import Path

from starlette.requests import Request


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

TEMP_DATA = tempfile.TemporaryDirectory()
atexit.register(TEMP_DATA.cleanup)
os.environ["DATA_DIR"] = TEMP_DATA.name
os.environ["SECRET_KEY"] = "smoke-security-secret"

from app import main as crm  # noqa: E402


def make_request(path="/", cookies=None):
    headers = []

    if cookies:
        cookie_header = "; ".join(
            f"{key}={value}" for key, value in cookies.items()
        )
        headers.append((b"cookie", cookie_header.encode("utf-8")))

    return Request({
        "type": "http",
        "method": "GET",
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


if __name__ == "__main__":
    test_fake_user_cookie_does_not_login()
    test_owner_cannot_access_other_company_task()
    test_uploads_require_auth()
    print("OK: security smoke tests passed")
