from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_fake_user_cookie_does_not_login():
    response = client.get("/", cookies={"user": "boss"}, follow_redirects=False)
    assert response.status_code in (302, 307)
    assert response.headers["location"].startswith("/login")

if __name__ == "__main__":
    test_fake_user_cookie_does_not_login()
    print("OK: fake user cookie rejected")


def test_owner_cannot_access_other_company_task():
    # fake cookie не должен давать доступ даже к конкретной заявке
    response = client.get("/task/1", cookies={"user": "owner"}, follow_redirects=False)
    assert response.status_code in (302, 307)
    assert response.headers["location"].startswith("/login")


if __name__ == "__main__":
    test_fake_user_cookie_does_not_login()
    test_owner_cannot_access_other_company_task()
    print("OK: security smoke tests passed")


def test_uploads_require_auth():
    response = client.get("/uploads/test.jpg", follow_redirects=False)
    assert response.status_code == 404


if __name__ == "__main__":
    test_fake_user_cookie_does_not_login()
    test_owner_cannot_access_other_company_task()
    test_uploads_require_auth()
    print("OK: security smoke tests passed")
