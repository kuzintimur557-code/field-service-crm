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
