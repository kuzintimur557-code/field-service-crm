import atexit
import asyncio
import os
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

TEMP_DATA = tempfile.TemporaryDirectory()
atexit.register(TEMP_DATA.cleanup)
os.environ.update({
    "APP_BASE_URL": "https://crm.example",
    "COOKIE_SECURE": "1",
    "DATA_DIR": TEMP_DATA.name,
    "ENV": "production",
    "RAILWAY_ENVIRONMENT": "",
    "SECRET_KEY": "production-security-smoke-secret-32",
    "TRUSTED_HOSTS": "crm.example",
})

from app.main import app  # noqa: E402


async def get_page(host):
    sent = []
    request_delivered = False

    async def receive():
        nonlocal request_delivered
        if request_delivered:
            return {"type": "http.disconnect"}
        request_delivered = True
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message):
        sent.append(message)

    await app({
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.3"},
        "http_version": "1.1",
        "method": "GET",
        "scheme": "https",
        "path": "/login",
        "raw_path": b"/login",
        "query_string": b"",
        "root_path": "",
        "headers": [(b"host", host.encode("ascii"))],
        "client": ("127.0.0.1", 50000),
        "server": (host, 443),
        "state": {},
    }, receive, send)

    start = next(message for message in sent if message["type"] == "http.response.start")
    headers = {
        key.decode("latin-1"): value.decode("latin-1")
        for key, value in start["headers"]
    }
    return start["status"], headers


def main():
    assert app.docs_url is None
    assert app.redoc_url is None
    assert app.openapi_url is None

    rejected_status, _ = asyncio.run(get_page("untrusted.example"))
    assert rejected_status == 400

    accepted_status, accepted_headers = asyncio.run(get_page("crm.example"))
    assert accepted_status == 200
    assert accepted_headers["x-frame-options"] == "DENY"
    assert "frame-ancestors 'none'" in accepted_headers[
            "content-security-policy"
    ]
    assert accepted_headers["cache-control"] == "no-store"

    print(
        "OK: production startup smoke passed: docs disabled, trusted hosts "
        "enforced and security headers present."
    )


if __name__ == "__main__":
    main()
