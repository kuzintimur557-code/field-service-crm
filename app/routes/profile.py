"""Profile and password routes."""

from datetime import datetime

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app.database import connect
from app.deps import (
    SESSION_COOKIE_NAME,
    get_role,
    get_user,
    get_user_company_id,
)
from app.services.common import get_company_settings
from app.templating import templates

router = APIRouter()


def _password_helpers():
    from app.main import (
        hash_password,
        is_password_strong,
        verify_password,
    )

    return hash_password, is_password_strong, verify_password

@router.get("/profile", response_class=HTMLResponse)
async def profile_page(request: Request):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)
    company_id = get_user_company_id(username)

    context = {
        "request": request,
        "username": username,
        "role": role
    }

    if company_id:
        context["settings"] = get_company_settings(company_id)

    return templates.TemplateResponse(
        request,
        "profile.html",
        context
    )


@router.post("/profile/password")
async def change_my_password(request: Request):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    form = await request.form()
    old_password = (form.get("old_password") or "").strip()
    new_password = (form.get("new_password") or "").strip()

    if not old_password or not new_password:
        return RedirectResponse("/profile?error=empty", status_code=302)

    hash_password, is_password_strong, verify_password = _password_helpers()

    if not is_password_strong(new_password):
        return RedirectResponse("/profile?error=weak_password", status_code=302)

    conn = connect()
    c = conn.cursor()

    user = c.execute("""
    SELECT *
    FROM users
    WHERE username=?
    """, (username,)).fetchone()

    if not user:
        conn.close()
        return RedirectResponse("/logout", status_code=302)

    if not verify_password(old_password, user["password"]):
        conn.close()
        return RedirectResponse("/profile?error=wrong_old", status_code=302)

    c.execute("""
    UPDATE users
    SET password=?, session_version=COALESCE(session_version, 1) + 1
    WHERE username=?
    """, (hash_password(new_password), username))

    conn.commit()
    conn.close()

    company_id = user["company_id"] if "company_id" in user.keys() else None

    if company_id:
        from app.main import run_automation_event

        run_automation_event(
            company_id,
            "profile_password_changed",
            "user",
            user["id"],
            f"Пользователь {username} изменил свой пароль",
            "/profile",
        )

    response = RedirectResponse("/login?password_changed=1", status_code=302)
    response.delete_cookie("user")
    response.delete_cookie(SESSION_COOKIE_NAME)
    return response
