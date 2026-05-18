import atexit
import os
import sys
import tempfile
from pathlib import Path

from fastapi.testclient import TestClient


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

TEMP_DATA = tempfile.TemporaryDirectory()
atexit.register(TEMP_DATA.cleanup)
os.environ["DATA_DIR"] = TEMP_DATA.name
os.environ["SECRET_KEY"] = "smoke-security-secret"

from app.main import app  # noqa: E402


client = TestClient(app)


def test_fake_user_cookie_does_not_login():
    response = client.get("/", cookies={"user": "boss"}, follow_redirects=False)
    assert response.status_code in (302, 307)
    assert response.headers["location"].startswith("/login")


def test_owner_cannot_access_other_company_task():
    response = client.get("/task/1", cookies={"user": "owner"}, follow_redirects=False)
    assert response.status_code in (302, 307)
    assert response.headers["location"].startswith("/login")


def test_uploads_require_auth():
    response = client.get("/uploads/test.jpg", follow_redirects=False)
    assert response.status_code == 404


if __name__ == "__main__":
    test_fake_user_cookie_does_not_login()
    test_owner_cannot_access_other_company_task()
    test_uploads_require_auth()
    print("OK: security smoke tests passed")
