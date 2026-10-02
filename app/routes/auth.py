"""Login and logout routes."""

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app.database import connect
from app.deps import (
    COOKIE_SECURE,
    SESSION_COOKIE_MAX_AGE_SECONDS,
    SESSION_COOKIE_NAME,
    clear_failed_logins,
    get_request_ip,
    get_role,
    get_user,
    is_login_blocked,
    log_login_event,
    register_failed_login,
    sign_session_value,
    update_last_seen,
)
from app.services.common import get_company_mode, get_company_settings
from app.templating import templates

router = APIRouter()


def _password_checkers():
    from app.main import (
        hash_password,
        password_needs_upgrade,
        verify_password,
    )

    return hash_password, password_needs_upgrade, verify_password

@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):

    return templates.TemplateResponse(
        request=request,
        name="login.html",
        context={}
    )


@router.post("/login")
async def login(request: Request):

    form = await request.form()

    username = (form.get("username") or "").strip()[:120]
    password = (form.get("password") or "").strip()

    hash_password, password_needs_upgrade, verify_password = (
        _password_checkers()
    )

    ip = get_request_ip(request)

    if is_login_blocked(username, ip):
        return RedirectResponse("/login?error=blocked", status_code=302)

    conn = connect()
    c = conn.cursor()

    user = c.execute("""
    SELECT *
    FROM users
    WHERE username=?
    """, (username,)).fetchone()

    if not user or not verify_password(password, user["password"]):
        conn.close()
        register_failed_login(username, ip)
        return RedirectResponse("/login?error=invalid", status_code=302)

    if user["is_active"] == 0:
        conn.close()
        return RedirectResponse("/login?error=disabled", status_code=302)

    if password_needs_upgrade(user["password"]):
        c.execute("""
        UPDATE users
        SET password=?
        WHERE username=?
        """, (hash_password(password), username))
        conn.commit()

    conn.close()

    update_last_seen(username)

    login_redirect = "/"

    if user["role"] in ("boss", "manager"):
        user_company_id = (
            user["company_id"] if "company_id" in user.keys() else None
        )

        if user_company_id:
            company_settings = get_company_settings(user_company_id)

            if get_company_mode(company_settings) == "master":
                login_redirect = "/master"

    response = RedirectResponse(login_redirect, status_code=302)
    response.delete_cookie("user")

    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=sign_session_value(
            username,
            user["session_version"] if "session_version" in user.keys() else 1,
        ),
        httponly=True,
        secure=COOKIE_SECURE,
        samesite="lax",
        max_age=SESSION_COOKIE_MAX_AGE_SECONDS,
        path="/"
    )

    return response


@router.get("/logout")
async def logout():

    response = RedirectResponse("/login", status_code=302)
    response.delete_cookie("user")
    response.delete_cookie(SESSION_COOKIE_NAME)

    return response
