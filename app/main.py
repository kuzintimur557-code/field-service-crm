from fastapi import FastAPI, Request, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse, FileResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.database import connect, init_db
from app.telegram_utils import send_message, send_photo

from datetime import datetime, timedelta
from pathlib import Path
from uuid import uuid4
from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

import shutil
import os
import hmac
import hashlib
import base64
import secrets
import csv
import io


APP_VERSION = "0.2.0"

SESSION_COOKIE_NAME = "crm_session"
SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-change-me")

app = FastAPI()

init_db()

os.makedirs("uploads", exist_ok=True)
os.makedirs("uploads/docs", exist_ok=True)

app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")
app.mount("/static", StaticFiles(directory="app/static"), name="static")

templates = Jinja2Templates(directory="app/templates")

DATA_DIR = Path(os.getenv("DATA_DIR", "."))
UPLOAD_DIR = DATA_DIR / "uploads"
DOCS_DIR = UPLOAD_DIR / "docs"

UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
DOCS_DIR.mkdir(parents=True, exist_ok=True)
ALLOWED_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".heic", ".heif"}
PDF_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}


def safe_upload_filename(task_id, prefix, original_filename):
    original = Path(original_filename or "photo").name
    extension = Path(original).suffix.lower()

    if extension not in ALLOWED_IMAGE_EXTENSIONS:
        extension = ".jpg"

    return f"task_{task_id}_{prefix}_{uuid4().hex}{extension}"


def save_upload_file(upload_file, task_id, prefix):
    if not upload_file or not upload_file.filename:
        return ""

    filename = safe_upload_filename(task_id, prefix, upload_file.filename)
    file_path = UPLOAD_DIR / filename

    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(upload_file.file, buffer)

    return filename


def can_access_task(username, role, task):
    if not task:
        return False

    if role in ("boss", "manager"):
        return True

    return task["worker"] == username


def get_role_title(role):
    titles = {
        "boss": "Босс",
        "manager": "Менеджер",
        "worker": "Исполнитель"
    }
    return titles.get(role, role)


def hash_password(password):
    salt = secrets.token_hex(16)
    digest = hashlib.sha256((salt + password).encode("utf-8")).hexdigest()
    return f"sha256${salt}${digest}"


def verify_password(password, stored_password):
    if not stored_password:
        return False

    if stored_password.startswith("sha256$"):
        try:
            _, salt, digest = stored_password.split("$", 2)
            check = hashlib.sha256((salt + password).encode("utf-8")).hexdigest()
            return secrets.compare_digest(check, digest)
        except Exception:
            return False

    # старый формат: обычный текст
    return secrets.compare_digest(password, stored_password)


def password_needs_upgrade(stored_password):
    return not str(stored_password or "").startswith("sha256$")


def is_password_strong(password):
    return len(password or "") >= 6


def get_plan_user_limit(plan):
    limits = {
        "basic": 3,
        "team": 10,
        "business": 30,
        "business_1c": 30,
        "enterprise_1c": None
    }
    return limits.get(plan, 3)


def get_company_settings():
    ip = get_request_ip(request)

    if is_login_blocked(username, ip):
        return RedirectResponse("/login?error=blocked", status_code=302)

    conn = connect()
    c = conn.cursor()

    c.execute("""
    INSERT OR IGNORE INTO company_settings (
        id, company_name, phone, email, address, tax_number, bank_details, updated_at
    )
    VALUES (1, '', '', '', '', '', '', '')
    """)

    conn.commit()

    settings = c.execute("""
    SELECT *
    FROM company_settings
    WHERE id=1
    """).fetchone()

    conn.close()

    return settings


def log_task_activity(task_id, username, role, action, details=""):
    conn = connect()
    c = conn.cursor()

    c.execute("""
    INSERT INTO task_activity (
        task_id,
        username,
        role,
        action,
        details,
        created_at
    )
    VALUES (?, ?, ?, ?, ?, ?)
    """, (
        task_id,
        username,
        role,
        action,
        details,
        datetime.now().strftime("%Y-%m-%d %H:%M")
    ))

    conn.commit()
    conn.close()


def register_pdf_font():
    font_paths = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
        "/Library/Fonts/Arial Unicode.ttf",
    ]

    for font_path in font_paths:
        if os.path.exists(font_path):
            try:
                pdfmetrics.registerFont(TTFont("CRMFont", font_path))
                return "CRMFont"
            except Exception:
                pass

    return "Helvetica"


def draw_text(pdf, text, x, y, font_name, size=10, max_chars=88, line_height=16):
    pdf.setFont(font_name, size)
    text = str(text or "")
    lines = []

    for paragraph in text.split("\n"):
        words = paragraph.split()

        if not words:
            lines.append("")
            continue

        line = ""

        for word in words:
            candidate = f"{line} {word}".strip()

            if len(candidate) <= max_chars:
                line = candidate
            else:
                lines.append(line)
                line = word

        if line:
            lines.append(line)

    for line in lines:
        if y < 70:
            pdf.showPage()
            y = 800
            pdf.setFont(font_name, size)

        pdf.drawString(x, y, line)
        y -= line_height

    return y


def draw_pdf_image(pdf, filename, title, x, y, font_name):
    if not filename:
        return y

    file_path = UPLOAD_DIR / filename

    if not file_path.exists():
        return y

    if file_path.suffix.lower() not in PDF_IMAGE_EXTENSIONS:
        pdf.setFont(font_name, 10)
        pdf.drawString(x, y, f"{title}: файл сохранён, но формат не вставляется в PDF")
        return y - 24

    if y < 270:
        pdf.showPage()
        y = 800

    try:
        pdf.setFont(font_name, 11)
        pdf.drawString(x, y, title)
        y -= 16
        image = ImageReader(str(file_path))
        pdf.drawImage(
            image,
            x,
            y - 170,
            width=240,
            height=170,
            preserveAspectRatio=True,
            mask="auto"
        )
        y -= 200
    except Exception:
        pdf.setFont(font_name, 10)
        pdf.drawString(x, y, f"{title}: не удалось вставить изображение")
        y -= 24

    return y


def sign_session_value(username):
    raw = username.encode("utf-8")
    signature = hmac.new(
        SECRET_KEY.encode("utf-8"),
        raw,
        hashlib.sha256
    ).digest()

    token = base64.urlsafe_b64encode(raw).decode("utf-8")
    sig = base64.urlsafe_b64encode(signature).decode("utf-8")

    return f"{token}.{sig}"


def verify_session_value(value):
    if not value or "." not in value:
        return None

    try:
        token, sig = value.split(".", 1)
        username = base64.urlsafe_b64decode(token.encode("utf-8")).decode("utf-8")

        expected_signature = hmac.new(
            SECRET_KEY.encode("utf-8"),
            username.encode("utf-8"),
            hashlib.sha256
        ).digest()

        expected_sig = base64.urlsafe_b64encode(expected_signature).decode("utf-8")

        if not hmac.compare_digest(sig, expected_sig):
            return None

        return username
    except Exception:
        return None


def get_user(request: Request):
    user_cookie = request.cookies.get("user")
    if user_cookie:
        return user_cookie

    signed_value = request.cookies.get(SESSION_COOKIE_NAME)
    username = verify_session_value(signed_value)

    if username:
        return username

    return None


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


def get_request_ip(request):
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()

    return request.client.host if request.client else ""


def is_login_blocked(username, ip):
    conn = connect()
    c = conn.cursor()

    row = c.execute("""
    SELECT *
    FROM login_attempts
    WHERE username=? AND ip=?
    """, (username, ip)).fetchone()

    conn.close()

    if not row or not row["blocked_until"]:
        return False

    try:
        blocked_until = datetime.strptime(row["blocked_until"], "%Y-%m-%d %H:%M:%S")
        return datetime.now() < blocked_until
    except Exception:
        return False


def register_failed_login(username, ip):
    conn = connect()
    c = conn.cursor()

    row = c.execute("""
    SELECT *
    FROM login_attempts
    WHERE username=? AND ip=?
    """, (username, ip)).fetchone()

    now = datetime.now()
    blocked_until = ""

    if row:
        attempts = int(row["attempts"] or 0) + 1

        if attempts >= 5:
            blocked_until = (now + timedelta(minutes=10)).strftime("%Y-%m-%d %H:%M:%S")

        c.execute("""
        UPDATE login_attempts
        SET attempts=?, blocked_until=?, updated_at=?
        WHERE id=?
        """, (
            attempts,
            blocked_until,
            now.strftime("%Y-%m-%d %H:%M:%S"),
            row["id"]
        ))
    else:
        c.execute("""
        INSERT INTO login_attempts (
            username,
            ip,
            attempts,
            blocked_until,
            updated_at
        )
        VALUES (?, ?, ?, ?, ?)
        """, (
            username,
            ip,
            1,
            "",
            now.strftime("%Y-%m-%d %H:%M:%S")
        ))

    conn.commit()
    conn.close()


def clear_failed_logins(username, ip):
    conn = connect()
    c = conn.cursor()

    c.execute("""
    DELETE FROM login_attempts
    WHERE username=? AND ip=?
    """, (username, ip))

    conn.commit()
    conn.close()


def log_login_event(request, username, role):
    conn = connect()
    c = conn.cursor()

    ip = request.client.host if request.client else ""
    user_agent = request.headers.get("user-agent", "")

    c.execute("""
    INSERT INTO login_events (
        username,
        role,
        ip,
        user_agent,
        created_at
    )
    VALUES (?, ?, ?, ?, ?)
    """, (
        username,
        role,
        ip,
        user_agent,
        datetime.now().strftime("%Y-%m-%d %H:%M")
    ))

    conn.commit()
    conn.close()


def update_last_seen(username):
    conn = connect()
    c = conn.cursor()

    c.execute("""
    UPDATE users
    SET last_seen=?
    WHERE username=?
    """, (
        datetime.now().strftime("%Y-%m-%d %H:%M"),
        username
    ))

    conn.commit()
    conn.close()


@app.get("/", response_class=HTMLResponse)
async def home(
    request: Request,
    status: str = "",
    worker: str = "",
    task_date: str = "",
    search: str = ""
):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    update_last_seen(username)

    role = get_role(username)

    conn = connect()
    c = conn.cursor()

    query = "SELECT * FROM tasks WHERE archived=0"
    params = []

    if role not in ("boss", "manager"):
        query += " AND worker=?"
        params.append(username)

    if status:
        query += " AND status=?"
        params.append(status)

    if worker and role in ("boss", "manager"):
        query += " AND worker=?"
        params.append(worker)

    if task_date:
        query += " AND task_date=?"
        params.append(task_date)

    if search:
        query += " AND client LIKE ?"
        params.append(f"%{search}%")

    query += " ORDER BY id DESC"

    tasks = c.execute(query, params).fetchall()

    if role in ("boss", "manager"):
        total_tasks = c.execute("SELECT COUNT(*) FROM tasks WHERE archived=0").fetchone()[0]
        new_tasks = c.execute("SELECT COUNT(*) FROM tasks WHERE archived=0 AND status='Новая'").fetchone()[0]
        working_tasks = c.execute("SELECT COUNT(*) FROM tasks WHERE archived=0 AND status='В работе'").fetchone()[0]
        done_tasks = c.execute("SELECT COUNT(*) FROM tasks WHERE archived=0 AND status='Завершено'").fetchone()[0]

        revenue = c.execute("""
        SELECT SUM(price) FROM tasks WHERE archived=0 AND status='Завершено'
        """).fetchone()[0]
    else:
        total_tasks = c.execute("SELECT COUNT(*) FROM tasks WHERE worker=?", (username,)).fetchone()[0]
        new_tasks = c.execute("SELECT COUNT(*) FROM tasks WHERE archived=0 AND worker=? AND status='Новая'", (username,)).fetchone()[0]
        working_tasks = c.execute("SELECT COUNT(*) FROM tasks WHERE archived=0 AND worker=? AND status='В работе'", (username,)).fetchone()[0]
        done_tasks = c.execute("SELECT COUNT(*) FROM tasks WHERE archived=0 AND worker=? AND status='Завершено'", (username,)).fetchone()[0]

        revenue = c.execute("""
        SELECT SUM(price) FROM tasks
        WHERE archived=0 AND worker=? AND status='Завершено'
        """, (username,)).fetchone()[0]

    if revenue is None:
        revenue = 0

    workers = c.execute("""
    SELECT username, last_seen FROM users
    WHERE role='worker'
    ORDER BY username
    """).fetchall()

    clients = []

    worker_stats = []

    if role in ("boss", "manager"):
        for w in workers:
            worker_name = w["username"]

            completed = c.execute("""
            SELECT COUNT(*) FROM tasks
            WHERE archived=0 AND worker=? AND status='Завершено'
            """, (worker_name,)).fetchone()[0]

            active = c.execute("""
            SELECT COUNT(*) FROM tasks
            WHERE archived=0 AND worker=? AND status='В работе'
            """, (worker_name,)).fetchone()[0]

            worker_revenue = c.execute("""
            SELECT SUM(price) FROM tasks
            WHERE archived=0 AND worker=? AND status='Завершено'
            """, (worker_name,)).fetchone()[0]

            if worker_revenue is None:
                worker_revenue = 0

            worker_stats.append({
                "username": worker_name,
                "completed": completed,
                "active": active,
                "revenue": worker_revenue,
                "last_seen": w["last_seen"]
            })

    conn.close()

    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "tasks": tasks,
            "username": username,
            "role": role,
            "total_tasks": total_tasks,
            "new_tasks": new_tasks,
            "working_tasks": working_tasks,
            "done_tasks": done_tasks,
            "revenue": revenue,
            "workers": workers,
            "worker_stats": worker_stats,
            "selected_status": status,
            "selected_worker": worker,
            "selected_date": task_date,
            "search": search
        }
    )


@app.get("/calendar", response_class=HTMLResponse)
async def calendar_page(request: Request):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    update_last_seen(username)
    role = get_role(username)

    conn = connect()
    c = conn.cursor()

    if role in ("boss", "manager"):
        tasks = c.execute("""
        SELECT * FROM tasks
        ORDER BY task_date ASC, id DESC
        """).fetchall()
    else:
        tasks = c.execute("""
        SELECT * FROM tasks
        WHERE worker=?
        ORDER BY task_date ASC, id DESC
        """, (username,)).fetchall()

    conn.close()

    return templates.TemplateResponse(
        request=request,
        name="calendar.html",
        context={
            "tasks": tasks,
            "username": username,
            "role": role
        }
    )


@app.get("/finance/export")
async def finance_export(request: Request, month: str = ""):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role not in ("boss", "manager"):
        return RedirectResponse("/", status_code=302)

    if not month:
        month = datetime.now().strftime("%Y-%m")

    conn = connect()
    c = conn.cursor()

    tasks = c.execute("""
    SELECT *
    FROM tasks
    WHERE archived=0 AND task_date LIKE ?
    ORDER BY task_date DESC
    """, (f"{month}%",)).fetchall()

    output = io.StringIO()
    writer = csv.writer(output)

    writer.writerow([
        "ID",
        "Дата",
        "Клиент",
        "Телефон",
        "Адрес",
        "Исполнитель",
        "Статус заявки",
        "Статус оплаты",
        "Сумма",
        "Прибыль"
    ])

    for task in tasks:
        items = c.execute("""
        SELECT *
        FROM task_items
        WHERE task_id=?
        """, (task["id"],)).fetchall()

        task_total = sum(item["total"] for item in items)
        task_profit = sum(item["profit"] for item in items)

        if not items:
            try:
                task_total = float(task["price"] or 0)
            except Exception:
                task_total = 0
            task_profit = 0

        payment_status = task["payment_status"] if "payment_status" in task.keys() else "Не оплачено"

        writer.writerow([
            task["id"],
            task["task_date"],
            task["client"],
            task["phone"],
            task["address"],
            task["worker"],
            task["status"],
            payment_status,
            task_total,
            task_profit
        ])

    conn.close()

    content = output.getvalue()
    output.close()

    return Response(
        content,
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f"attachment; filename=finance_{month}.csv"
        }
    )


@app.get("/finance", response_class=HTMLResponse)
async def finance_page(request: Request, month: str = ""):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role not in ("boss", "manager"):
        return RedirectResponse("/", status_code=302)

    if not month:
        month = datetime.now().strftime("%Y-%m")

    conn = connect()
    c = conn.cursor()

    tasks = c.execute("""
    SELECT *
    FROM tasks
    WHERE archived=0 AND task_date LIKE ?
    ORDER BY task_date DESC
    """, (f"{month}%",)).fetchall()

    total_estimate = 0
    total_profit = 0
    paid_total = 0
    partial_total = 0
    unpaid_total = 0

    rows = []

    for task in tasks:
        items = c.execute("""
        SELECT *
        FROM task_items
        WHERE task_id=?
        """, (task["id"],)).fetchall()

        task_total = sum(item["total"] for item in items)
        task_profit = sum(item["profit"] for item in items)

        if not items:
            try:
                task_total = float(task["price"] or 0)
            except Exception:
                task_total = 0
            task_profit = 0

        payment_status = task["payment_status"] if "payment_status" in task.keys() else "Не оплачено"

        total_estimate += task_total
        total_profit += task_profit

        if payment_status == "Оплачено":
            paid_total += task_total
        elif payment_status == "Частично оплачено":
            partial_total += task_total
        else:
            unpaid_total += task_total

        rows.append({
            "id": task["id"],
            "client": task["client"],
            "worker": task["worker"],
            "task_date": task["task_date"],
            "status": task["status"],
            "payment_status": payment_status,
            "total": task_total,
            "profit": task_profit
        })

    conn.close()

    return templates.TemplateResponse(
        request,
        "finance.html",
        {
            "request": request,
            "username": username,
            "role": role,
            "month": month,
            "rows": rows,
            "total_estimate": total_estimate,
            "total_profit": total_profit,
            "paid_total": paid_total,
            "partial_total": partial_total,
            "unpaid_total": unpaid_total
        }
    )


@app.get("/reports", response_class=HTMLResponse)
async def reports_page(request: Request, month: str = ""):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    update_last_seen(username)
    role = get_role(username)

    if role not in ("boss", "manager"):
        return RedirectResponse("/", status_code=302)

    if not month:
        month = datetime.now().strftime("%Y-%m")

    conn = connect()
    c = conn.cursor()

    workers = c.execute("""
    SELECT username FROM users
    WHERE role='worker'
    ORDER BY username
    """).fetchall()

    report_rows = []

    total_completed = 0
    total_active = 0
    total_new = 0
    total_cancelled = 0
    total_revenue = 0

    for w in workers:
        worker_name = w[0]

        completed = c.execute("""
        SELECT COUNT(*) FROM tasks
        WHERE archived=0 AND worker=? AND status='Завершено' AND task_date LIKE ?
        """, (worker_name, f"{month}%")).fetchone()[0]

        active = c.execute("""
        SELECT COUNT(*) FROM tasks
        WHERE archived=0 AND worker=? AND status='В работе' AND task_date LIKE ?
        """, (worker_name, f"{month}%")).fetchone()[0]

        new = c.execute("""
        SELECT COUNT(*) FROM tasks
        WHERE archived=0 AND worker=? AND status='Новая' AND task_date LIKE ?
        """, (worker_name, f"{month}%")).fetchone()[0]

        cancelled = c.execute("""
        SELECT COUNT(*) FROM tasks
        WHERE archived=0 AND worker=? AND status='Отменено' AND task_date LIKE ?
        """, (worker_name, f"{month}%")).fetchone()[0]

        revenue = c.execute("""
        SELECT SUM(price) FROM tasks
        WHERE archived=0 AND worker=? AND status='Завершено' AND task_date LIKE ?
        """, (worker_name, f"{month}%")).fetchone()[0]

        if revenue is None:
            revenue = 0

        total_worker_tasks = completed + active + new + cancelled

        report_rows.append({
            "worker": worker_name,
            "completed": completed,
            "active": active,
            "new": new,
            "cancelled": cancelled,
            "revenue": revenue,
            "total": total_worker_tasks
        })

        total_completed += completed
        total_active += active
        total_new += new
        total_cancelled += cancelled
        total_revenue += revenue

    tasks = c.execute("""
    SELECT * FROM tasks
    WHERE task_date LIKE ?
    ORDER BY task_date ASC, id DESC
    """, (f"{month}%",)).fetchall()

    conn.close()

    return templates.TemplateResponse(
        request=request,
        name="reports.html",
        context={
            "username": username,
            "month": month,
            "report_rows": report_rows,
            "tasks": tasks,
            "total_completed": total_completed,
            "total_active": total_active,
            "total_new": total_new,
            "total_cancelled": total_cancelled,
            "total_revenue": total_revenue
        }
    )


@app.get("/calls", response_class=HTMLResponse)
async def calls_page(request: Request):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role not in ("boss", "manager"):
        return RedirectResponse("/", status_code=302)

    settings = get_company_settings()

    return templates.TemplateResponse(
        request,
        "calls.html",
        {
            "request": request,
            "username": username,
            "role": role,
            "settings": settings,
            "recent_users": recent_users,
            "login_events": login_events,
            "login_attempts": login_attempts
        }
    )


@app.get("/integrations/1c", response_class=HTMLResponse)
async def integration_1c_page(request: Request):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role != "boss":
        return RedirectResponse("/", status_code=302)

    settings = get_company_settings()

    return templates.TemplateResponse(
        request,
        "integration_1c.html",
        {
            "request": request,
            "username": username,
            "role": role,
            "settings": settings,
            "recent_users": recent_users,
            "login_events": login_events,
            "login_attempts": login_attempts
        }
    )


@app.get("/billing", response_class=HTMLResponse)
async def billing_page(request: Request):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role != "boss":
        return RedirectResponse("/", status_code=302)

    settings = get_company_settings()
    plan = settings["plan"] if settings and "plan" in settings.keys() else "basic"
    user_limit = get_plan_user_limit(plan)

    return templates.TemplateResponse(
        request,
        "billing.html",
        {
            "request": request,
            "username": username,
            "role": role,
            "settings": settings,
            "recent_users": recent_users,
            "login_events": login_events,
            "login_attempts": login_attempts,
            "plan": plan,
            "user_limit": user_limit
        }
    )


@app.get("/settings", response_class=HTMLResponse)
async def settings_page(request: Request):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role != "boss":
        return RedirectResponse("/", status_code=302)

    settings = get_company_settings()

    return templates.TemplateResponse(
        request,
        "settings.html",
        {
            "request": request,
            "username": username,
            "role": role,
            "settings": settings,
            "recent_users": recent_users,
            "login_events": login_events,
            "login_attempts": login_attempts
        }
    )


@app.post("/settings")
async def update_settings(request: Request):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role != "boss":
        return RedirectResponse("/", status_code=302)

    form = await request.form()

    company_name = (form.get("company_name") or "").strip()
    phone = (form.get("phone") or "").strip()
    email = (form.get("email") or "").strip()
    address = (form.get("address") or "").strip()
    tax_number = (form.get("tax_number") or "").strip()
    bank_details = (form.get("bank_details") or "").strip()
    plan = (form.get("plan") or "basic").strip()

    allowed_plans = ["basic", "team", "business", "business_1c", "enterprise_1c"]

    if plan not in allowed_plans:
        plan = "basic"

    one_c_enabled = 1 if plan in ("business_1c", "enterprise_1c") else 0
    calls_enabled = 1 if plan in ("business", "business_1c", "enterprise_1c") else 0
    ai_calls_enabled = 1 if plan == "enterprise_1c" else 0

    conn = connect()
    c = conn.cursor()

    c.execute("""
    INSERT OR IGNORE INTO company_settings (
        id, company_name, phone, email, address, tax_number, bank_details, updated_at
    )
    VALUES (1, '', '', '', '', '', '', '')
    """)

    c.execute("""
    UPDATE company_settings
    SET company_name=?, phone=?, email=?, address=?, tax_number=?, bank_details=?,
        plan=?, one_c_enabled=?, calls_enabled=?, ai_calls_enabled=?, updated_at=?
    WHERE id=1
    """, (
        company_name,
        phone,
        email,
        address,
        tax_number,
        bank_details,
        plan,
        one_c_enabled,
        calls_enabled,
        ai_calls_enabled,
        datetime.now().strftime("%Y-%m-%d %H:%M")
    ))

    conn.commit()
    conn.close()

    try:
        send_message(
            f"""
⚙️ Настройки компании обновлены

Компания: {company_name}
Изменил: {username} ({get_role_title(role)})
"""
        )
    except Exception:
        pass

    return RedirectResponse("/settings?updated=1", status_code=302)


@app.get("/catalog", response_class=HTMLResponse)
async def catalog_page(request: Request):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role not in ("boss", "manager"):
        return RedirectResponse("/", status_code=302)

    conn = connect()
    c = conn.cursor()

    items = c.execute("""
    SELECT *
    FROM catalog_items
    ORDER BY active DESC, item_type, name
    """).fetchall()

    conn.close()

    return templates.TemplateResponse(
        request,
        "catalog.html",
        {
            "request": request,
            "username": username,
            "role": role,
            "items": items
        }
    )


@app.post("/catalog")
async def create_catalog_item(request: Request):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role not in ("boss", "manager"):
        return RedirectResponse("/", status_code=302)

    form = await request.form()

    item_type = (form.get("item_type") or "service").strip()
    name = (form.get("name") or "").strip()
    unit = (form.get("unit") or "шт").strip()
    price = form.get("price") or "0"
    cost = form.get("cost") or "0"

    if item_type not in ("service", "material"):
        item_type = "service"

    if not name:
        return RedirectResponse("/catalog?error=empty", status_code=302)

    try:
        price = float(str(price).replace(",", "."))
    except Exception:
        price = 0

    try:
        cost = float(str(cost).replace(",", "."))
    except Exception:
        cost = 0

    conn = connect()
    c = conn.cursor()

    c.execute("""
    INSERT INTO catalog_items (
        item_type,
        name,
        unit,
        price,
        cost,
        active,
        created_at
    )
    VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        item_type,
        name,
        unit,
        price,
        cost,
        1,
        datetime.now().strftime("%Y-%m-%d %H:%M")
    ))

    conn.commit()
    conn.close()

    try:
        send_message(
            f"""
📦 Добавлена позиция в каталог

Тип: {"Услуга" if item_type == "service" else "Материал"}
Название: {name}
Цена: {price}
Себестоимость: {cost}

Создал: {username} ({get_role_title(role)})
"""
        )
    except Exception:
        pass

    return RedirectResponse("/catalog?created=1", status_code=302)


@app.post("/catalog/{item_id}/toggle")
async def toggle_catalog_item(request: Request, item_id: int):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role not in ("boss", "manager"):
        return RedirectResponse("/", status_code=302)

    conn = connect()
    c = conn.cursor()

    item = c.execute("""
    SELECT *
    FROM catalog_items
    WHERE id=?
    """, (item_id,)).fetchone()

    if not item:
        conn.close()
        return RedirectResponse("/catalog", status_code=302)

    new_active = 0 if item["active"] else 1

    c.execute("""
    UPDATE catalog_items
    SET active=?
    WHERE id=?
    """, (new_active, item_id))

    conn.commit()
    conn.close()

    return RedirectResponse("/catalog", status_code=302)


@app.get("/clients", response_class=HTMLResponse)
async def clients_page(request: Request):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role not in ("boss", "manager"):
        return RedirectResponse("/", status_code=302)

    conn = connect()
    c = conn.cursor()

    clients = c.execute("""
    SELECT *
    FROM clients
    ORDER BY id DESC
    """).fetchall()

    conn.close()

    return templates.TemplateResponse(
        request,
        "clients.html",
        {
            "request": request,
            "username": username,
            "role": role,
            "clients": clients
        }
    )


@app.get("/clients/{client_id}", response_class=HTMLResponse)
async def client_detail(request: Request, client_id: int):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role not in ("boss", "manager"):
        return RedirectResponse("/", status_code=302)

    conn = connect()
    c = conn.cursor()

    client = c.execute("""
    SELECT *
    FROM clients
    WHERE id=?
    """, (client_id,)).fetchone()

    if not client:
        conn.close()
        return RedirectResponse("/clients", status_code=302)

    tasks = c.execute("""
    SELECT *
    FROM tasks
    WHERE client_id=?
    ORDER BY id DESC
    """, (client_id,)).fetchall()

    client_notes = c.execute("""
    SELECT *
    FROM client_notes
    WHERE client_id=?
    ORDER BY id DESC
    """, (client_id,)).fetchall()

    conn.close()

    return templates.TemplateResponse(
        request,
        "client_detail.html",
        {
            "request": request,
            "username": username,
            "role": role,
            "client": client,
            "tasks": tasks,
            "client_notes": client_notes
        }
    )


@app.post("/clients/{client_id}/notes")
async def add_client_note(request: Request, client_id: int):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role not in ("boss", "manager"):
        return RedirectResponse("/", status_code=302)

    form = await request.form()
    note = (form.get("note") or "").strip()

    if not note:
        return RedirectResponse(f"/clients/{client_id}?note_error=empty", status_code=302)

    conn = connect()
    c = conn.cursor()

    client = c.execute("""
    SELECT *
    FROM clients
    WHERE id=?
    """, (client_id,)).fetchone()

    if not client:
        conn.close()
        return RedirectResponse("/clients", status_code=302)

    c.execute("""
    INSERT INTO client_notes (
        client_id,
        username,
        role,
        note,
        created_at
    )
    VALUES (?, ?, ?, ?, ?)
    """, (
        client_id,
        username,
        role,
        note,
        datetime.now().strftime("%Y-%m-%d %H:%M")
    ))

    conn.commit()
    conn.close()

    try:
        send_message(
            f"""
📝 Новая заметка по клиенту

Клиент: {client['name']}
Автор: {username} ({get_role_title(role)})

Заметка:
{note}
"""
        )
    except Exception:
        pass

    return RedirectResponse(f"/clients/{client_id}?note_created=1", status_code=302)


@app.post("/clients/{client_id}/edit")
async def edit_client(request: Request, client_id: int):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role not in ("boss", "manager"):
        return RedirectResponse("/", status_code=302)

    form = await request.form()

    name = (form.get("name") or "").strip()
    phone = (form.get("phone") or "").strip()
    email = (form.get("email") or "").strip()
    address = (form.get("address") or "").strip()
    notes = (form.get("notes") or "").strip()

    if not name:
        return RedirectResponse(f"/clients/{client_id}?error=empty", status_code=302)

    conn = connect()
    c = conn.cursor()

    client = c.execute("""
    SELECT *
    FROM clients
    WHERE id=?
    """, (client_id,)).fetchone()

    if not client:
        conn.close()
        return RedirectResponse("/clients", status_code=302)

    c.execute("""
    UPDATE clients
    SET name=?, phone=?, email=?, address=?, notes=?
    WHERE id=?
    """, (
        name,
        phone,
        email,
        address,
        notes,
        client_id
    ))

    linked_tasks = c.execute("""
    SELECT id
    FROM tasks
    WHERE client_id=?
    """, (client_id,)).fetchall()

    conn.commit()
    conn.close()

    for task in linked_tasks:
        try:
            log_task_activity(
                task["id"],
                username,
                role,
                "Обновлена карточка клиента",
                name
            )
        except Exception:
            pass

    try:
        send_message(
            f"""
👤 Карточка клиента обновлена

Клиент: {name}
Телефон: {phone}
Email: {email}
Адрес: {address}

Изменил: {username} ({get_role_title(role)})
"""
        )
    except Exception:
        pass

    return RedirectResponse(f"/clients/{client_id}?updated=1", status_code=302)


@app.post("/clients")
async def create_client(request: Request):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role not in ("boss", "manager"):
        return RedirectResponse("/", status_code=302)

    form = await request.form()

    name = (form.get("name") or "").strip()
    phone = (form.get("phone") or "").strip()
    email = (form.get("email") or "").strip()
    address = (form.get("address") or "").strip()
    notes = (form.get("notes") or "").strip()

    if not name:
        return RedirectResponse("/clients?error=empty", status_code=302)

    conn = connect()
    c = conn.cursor()

    c.execute("""
    INSERT INTO clients (
        name,
        phone,
        email,
        address,
        notes,
        created_at
    )
    VALUES (?, ?, ?, ?, ?, ?)
    """, (
        name,
        phone,
        email,
        address,
        notes,
        datetime.now().strftime("%Y-%m-%d %H:%M")
    ))

    conn.commit()
    conn.close()

    try:
        send_message(
            f"""
👤 Новый клиент

Имя: {name}
Телефон: {phone}
Адрес: {address}

Создал: {username} ({get_role_title(role)})
"""
        )
    except Exception:
        pass

    return RedirectResponse("/clients?created=1", status_code=302)


@app.get("/archive", response_class=HTMLResponse)
async def archive_page(request: Request):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role not in ("boss", "manager"):
        return RedirectResponse("/", status_code=302)

    conn = connect()
    c = conn.cursor()

    tasks = c.execute("""
    SELECT *
    FROM tasks
    WHERE archived=1
    ORDER BY id DESC
    """).fetchall()

    conn.close()

    return templates.TemplateResponse(
        request,
        "archive.html",
        {
            "request": request,
            "username": username,
            "role": role,
            "tasks": tasks
        }
    )


@app.get("/profile", response_class=HTMLResponse)
async def profile_page(request: Request):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    return templates.TemplateResponse(
        request,
        "profile.html",
        {
            "request": request,
            "username": username,
            "role": role
        }
    )


@app.post("/profile/password")
async def change_my_password(request: Request):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    form = await request.form()
    old_password = (form.get("old_password") or "").strip()
    new_password = (form.get("new_password") or "").strip()

    if not old_password or not new_password:
        return RedirectResponse("/profile?error=empty", status_code=302)

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
    SET password=?
    WHERE username=?
    """, (hash_password(new_password), username))

    conn.commit()
    conn.close()

    response = RedirectResponse("/login?password_changed=1", status_code=302)
    response.delete_cookie("user")
    response.delete_cookie(SESSION_COOKIE_NAME)
    return response


@app.get("/workers", response_class=HTMLResponse)
async def workers_page(request: Request):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    update_last_seen(username)
    role = get_role(username)

    if role not in ("boss", "manager"):
        return RedirectResponse("/", status_code=302)

    conn = connect()
    c = conn.cursor()

    workers = c.execute("""
    SELECT * FROM users
    WHERE role IN ('manager', 'worker')
    ORDER BY role, username
    """).fetchall()

    conn.close()

    return templates.TemplateResponse(
        request=request,
        name="workers.html",
        context={
            "workers": workers,
            "username": username
        }
    )


@app.post("/workers")
async def create_worker(request: Request):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role != "boss":
        return RedirectResponse("/workers?error=only_boss", status_code=302)

    form = await request.form()

    worker_username = (form.get("username") or "").strip()
    worker_password = (form.get("password") or "").strip()
    worker_role = (form.get("role") or "worker").strip()

    if not worker_username or not worker_password:
        return RedirectResponse("/workers?error=empty", status_code=302)

    if worker_role not in ("manager", "worker"):
        return RedirectResponse("/workers?error=bad_role", status_code=302)

    conn = connect()
    c = conn.cursor()

    existing = c.execute("""
    SELECT * FROM users WHERE username=?
    """, (worker_username,)).fetchone()

    if existing:
        conn.close()
        return RedirectResponse("/workers?error=exists", status_code=302)

    settings = get_company_settings()
    current_plan = settings["plan"] if settings and "plan" in settings.keys() else "basic"
    user_limit = get_plan_user_limit(current_plan)

    users_count = c.execute("""
    SELECT COUNT(*)
    FROM users
    """).fetchone()[0]

    if user_limit is not None and users_count >= user_limit:
        conn.close()
        return RedirectResponse("/workers?error=user_limit", status_code=302)

    c.execute("""
    INSERT INTO users (username, password, role, last_seen)
    VALUES (?, ?, ?, ?)
    """, (
        worker_username,
        worker_password,
        worker_role,
        datetime.now().strftime("%Y-%m-%d %H:%M")
    ))

    conn.commit()
    conn.close()

    try:
        send_message(
            f"""
👥 Создан новый пользователь

Логин: {worker_username}
Роль: {get_role_title(worker_role)}
Создал: {username} ({get_role_title(role)})
"""
        )
    except Exception:
        pass

    return RedirectResponse("/workers?created=1", status_code=302)


@app.post("/workers/{user_id}/password")
async def change_team_user_password(request: Request, user_id: int):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role != "boss":
        return RedirectResponse("/workers?error=only_boss", status_code=302)

    form = await request.form()
    new_password = (form.get("password") or "").strip()

    if not new_password:
        return RedirectResponse("/workers?error=empty_password", status_code=302)

    if not is_password_strong(new_password):
        return RedirectResponse("/workers?error=weak_password", status_code=302)

    conn = connect()
    c = conn.cursor()

    user = c.execute("""
    SELECT *
    FROM users
    WHERE id=?
    """, (user_id,)).fetchone()

    if not user:
        conn.close()
        return RedirectResponse("/workers", status_code=302)

    if user["username"] == username:
        conn.close()
        return RedirectResponse("/workers?error=cannot_change_self_here", status_code=302)

    c.execute("""
    UPDATE users
    SET password=?
    WHERE id=?
    """, (hash_password(new_password), user_id))

    conn.commit()
    conn.close()

    return RedirectResponse("/workers?password_changed=1", status_code=302)


@app.post("/workers/{user_id}/delete")
async def delete_team_user(request: Request, user_id: int):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role != "boss":
        return RedirectResponse("/workers?error=only_boss", status_code=302)

    conn = connect()
    c = conn.cursor()

    user = c.execute("""
    SELECT *
    FROM users
    WHERE id=?
    """, (user_id,)).fetchone()

    if not user:
        conn.close()
        return RedirectResponse("/workers", status_code=302)

    if user["username"] == username or user["role"] == "boss":
        conn.close()
        return RedirectResponse("/workers?error=cannot_delete_boss", status_code=302)

    c.execute("""
    DELETE FROM users
    WHERE id=?
    """, (user_id,))

    conn.commit()
    conn.close()

    return RedirectResponse("/workers?deleted=1", status_code=302)


@app.post("/debug/login-attempts/clear")
async def clear_login_attempts_admin(request: Request):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role != "boss":
        return RedirectResponse("/", status_code=302)

    conn = connect()
    c = conn.cursor()

    c.execute("DELETE FROM login_attempts")

    conn.commit()
    conn.close()

    return RedirectResponse("/debug?login_attempts_cleared=1", status_code=302)


@app.get("/admin/checklist", response_class=HTMLResponse)
async def admin_checklist_page(request: Request):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role != "boss":
        return RedirectResponse("/", status_code=302)

    return templates.TemplateResponse(
        request,
        "admin_checklist.html",
        {
            "request": request,
            "username": username,
            "role": role
        }
    )


@app.get("/admin", response_class=HTMLResponse)
async def admin_page(request: Request):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role != "boss":
        return RedirectResponse("/", status_code=302)

    return templates.TemplateResponse(
        request,
        "admin.html",
        {
            "request": request,
            "username": username,
            "role": role
        }
    )


@app.get("/debug", response_class=HTMLResponse)
async def debug_page(request: Request):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role != "boss":
        return RedirectResponse("/", status_code=302)

    conn = connect()
    c = conn.cursor()

    users_count = c.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    tasks_count = c.execute("SELECT COUNT(*) FROM tasks").fetchone()[0]
    active_tasks_count = c.execute("SELECT COUNT(*) FROM tasks WHERE archived=0").fetchone()[0]
    archived_tasks_count = c.execute("SELECT COUNT(*) FROM tasks WHERE archived=1").fetchone()[0]
    clients_count = c.execute("SELECT COUNT(*) FROM clients").fetchone()[0]
    catalog_count = c.execute("SELECT COUNT(*) FROM catalog_items").fetchone()[0]

    settings = get_company_settings()

    recent_users = c.execute("""
    SELECT username, role, last_seen
    FROM users
    ORDER BY last_seen DESC
    """).fetchall()

    login_events = c.execute("""
    SELECT *
    FROM login_events
    ORDER BY id DESC
    LIMIT 20
    """).fetchall()

    login_attempts = c.execute("""
    SELECT *
    FROM login_attempts
    ORDER BY id DESC
    LIMIT 20
    """).fetchall()

    conn.close()

    return templates.TemplateResponse(
        request,
        "debug.html",
        {
            "request": request,
            "username": username,
            "role": role,
            "users_count": users_count,
            "tasks_count": tasks_count,
            "active_tasks_count": active_tasks_count,
            "archived_tasks_count": archived_tasks_count,
            "clients_count": clients_count,
            "catalog_count": catalog_count,
            "settings": settings,
            "recent_users": recent_users,
            "login_events": login_events,
            "login_attempts": login_attempts
        }
    )


@app.get("/favicon.ico")
async def favicon():
    return FileResponse("app/static/favicon.svg", media_type="image/svg+xml")


@app.get("/health")
async def health_check():
    return {
        "status": "ok",
        "app": "Field Service CRM"
    }


@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):

    return templates.TemplateResponse(
        request=request,
        name="login.html",
        context={}
    )


@app.post("/login")
async def login(request: Request):

    form = await request.form()

    username = (form.get("username") or "").strip()
    password = (form.get("password") or "").strip()

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

    if password_needs_upgrade(user["password"]):
        c.execute("""
        UPDATE users
        SET password=?
        WHERE username=?
        """, (hash_password(password), username))
        conn.commit()

    conn.close()

    update_last_seen(username)

    response = RedirectResponse("/", status_code=302)

    response.set_cookie(
        key="user",
        value=username,
        httponly=True,
        secure=False,
        samesite="lax",
        max_age=60 * 60 * 24 * 30,
        path="/"
    )

    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=sign_session_value(username),
        httponly=True,
        secure=False,
        samesite="lax",
        max_age=60 * 60 * 24 * 30,
        path="/"
    )

    return response


@app.get("/logout")
async def logout():

    response = RedirectResponse("/login", status_code=302)
    response.delete_cookie("user")

    return response


@app.get("/create-task", response_class=HTMLResponse)
async def create_task_page(request: Request):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    update_last_seen(username)
    role = get_role(username)

    if role not in ("boss", "manager"):
        return RedirectResponse("/", status_code=302)

    conn = connect()
    c = conn.cursor()

    workers = c.execute("""
    SELECT username FROM users
    WHERE role='worker'
    ORDER BY username
    """).fetchall()

    clients = c.execute("""
    SELECT *
    FROM clients
    ORDER BY name
    """).fetchall()

    conn.close()

    return templates.TemplateResponse(
        request=request,
        name="create_task.html",
        context={
            "username": username,
            "workers": workers,
            "clients": clients
        }
    )



@app.post("/create-task")
async def create_task(
    request: Request,
    photo: UploadFile = File(None)
):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role not in ("boss", "manager"):
        return RedirectResponse("/", status_code=302)

    form = await request.form()

    client_id = form.get("client_id") or None
    client = form.get("client")
    phone = form.get("phone")
    address = form.get("address")

    if client_id:
        existing_client = c.execute("""
        SELECT *
        FROM clients
        WHERE id=?
        """, (client_id,)).fetchone()

        if existing_client:
            client = existing_client["name"]
            phone = existing_client["phone"]
            address = existing_client["address"]
    description = form.get("description")
    task_date = form.get("task_date")
    worker = form.get("worker")
    priority = form.get("priority")
    price = form.get("price")

    conn = connect()
    c = conn.cursor()

    c.execute("""
    INSERT INTO tasks (
        client_id,
        client,
        phone,
        address,
        description,
        task_date,
        worker,
        priority,
        price,
        photo,
        status,
        report,
        after_photo
    )
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        client_id,
        client,
        phone,
        address,
        description,
        task_date,
        worker,
        priority,
        price,
        "",
        "Новая",
        "",
        ""
    ))

    conn.commit()
    task_id = c.lastrowid

    filename = save_upload_file(photo, task_id, "before")

    if filename:
        c.execute("""
        UPDATE tasks SET photo=? WHERE id=?
        """, (filename, task_id))
        conn.commit()

    conn.close()

    log_task_activity(
        task_id,
        username,
        role,
        "Создана заявка",
        f"Клиент: {client}. Исполнитель: {worker}. Дата: {task_date}"
    )

    text = f"""
🚀 Новая заявка #{task_id}

👤 Клиент: {client}
📞 Телефон: {phone}
📍 Адрес: {address}
📅 Дата: {task_date}
👷 Исполнитель: {worker}
🔥 Приоритет: {priority}
💰 Цена: {price}
"""

    try:
        send_message(text)

        if filename:
            send_photo(
                f"uploads/{filename}",
                f"Фото до работы к заявке #{task_id}"
            )
    except Exception:
        pass

    return RedirectResponse("/", status_code=302)


@app.get("/task/{task_id}", response_class=HTMLResponse)
async def task_detail(request: Request, task_id: int):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    conn = connect()
    c = conn.cursor()

    task = c.execute("""
    SELECT * FROM tasks WHERE id=?
    """, (task_id,)).fetchone()

    if not task:
        conn.close()
        return RedirectResponse("/", status_code=302)

    if not can_access_task(username, role, task):
        conn.close()
        return RedirectResponse("/", status_code=302)

    linked_client = None

    if "client_id" in task.keys() and task["client_id"]:
        linked_client = c.execute("""
        SELECT *
        FROM clients
        WHERE id=?
        """, (task["client_id"],)).fetchone()

    comments = c.execute("""
    SELECT *
    FROM task_comments
    WHERE task_id=?
    ORDER BY id ASC
    """, (task_id,)).fetchall()

    activity = c.execute("""
    SELECT *
    FROM task_activity
    WHERE task_id=?
    ORDER BY id DESC
    """, (task_id,)).fetchall()

    task_items = c.execute("""
    SELECT *
    FROM task_items
    WHERE task_id=?
    ORDER BY id DESC
    """, (task_id,)).fetchall()

    catalog_items = c.execute("""
    SELECT *
    FROM catalog_items
    WHERE active=1
    ORDER BY item_type, name
    """).fetchall()

    estimate_total = sum(item["total"] for item in task_items)
    estimate_profit = sum(item["profit"] for item in task_items)

    conn.close()

    return templates.TemplateResponse(
        request,
        "task_detail.html",
        {
            "request": request,
            "task": task,
            "username": username,
            "role": role,
            "comments": comments,
            "activity": activity,
            "linked_client": linked_client,
            "task_items": task_items,
            "catalog_items": catalog_items,
            "estimate_total": estimate_total,
            "estimate_profit": estimate_profit
        }
    )


@app.post("/task/{task_id}/items")
async def add_task_item(request: Request, task_id: int):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role not in ("boss", "manager"):
        return RedirectResponse("/", status_code=302)

    form = await request.form()

    catalog_item_id = form.get("catalog_item_id")
    qty = form.get("qty") or "1"

    try:
        qty = float(str(qty).replace(",", "."))
    except Exception:
        qty = 1

    if qty <= 0:
        qty = 1

    conn = connect()
    c = conn.cursor()

    task = c.execute("""
    SELECT *
    FROM tasks
    WHERE id=?
    """, (task_id,)).fetchone()

    if not task:
        conn.close()
        return RedirectResponse("/", status_code=302)

    item = c.execute("""
    SELECT *
    FROM catalog_items
    WHERE id=?
    """, (catalog_item_id,)).fetchone()

    if not item:
        conn.close()
        return RedirectResponse(f"/task/{task_id}", status_code=302)

    total = float(item["price"]) * qty
    profit = (float(item["price"]) - float(item["cost"])) * qty

    c.execute("""
    INSERT INTO task_items (
        task_id,
        catalog_item_id,
        item_name,
        item_type,
        unit,
        qty,
        price,
        cost,
        total,
        profit,
        created_at
    )
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        task_id,
        item["id"],
        item["name"],
        item["item_type"],
        item["unit"],
        qty,
        item["price"],
        item["cost"],
        total,
        profit,
        datetime.now().strftime("%Y-%m-%d %H:%M")
    ))

    conn.commit()
    conn.close()

    try:
        log_task_activity(
            task_id,
            username,
            role,
            "Добавлена позиция в смету",
            f"{item['name']} × {qty}"
        )
    except Exception:
        pass

    return RedirectResponse(f"/task/{task_id}", status_code=302)


@app.post("/task/{task_id}/items/{item_id}/delete")
async def delete_task_item(request: Request, task_id: int, item_id: int):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role not in ("boss", "manager"):
        return RedirectResponse("/", status_code=302)

    conn = connect()
    c = conn.cursor()

    task = c.execute("""
    SELECT *
    FROM tasks
    WHERE id=?
    """, (task_id,)).fetchone()

    if not task:
        conn.close()
        return RedirectResponse("/", status_code=302)

    item = c.execute("""
    SELECT *
    FROM task_items
    WHERE id=? AND task_id=?
    """, (item_id, task_id)).fetchone()

    if not item:
        conn.close()
        return RedirectResponse(f"/task/{task_id}", status_code=302)

    c.execute("""
    DELETE FROM task_items
    WHERE id=? AND task_id=?
    """, (item_id, task_id))

    conn.commit()
    conn.close()

    try:
        log_task_activity(
            task_id,
            username,
            role,
            "Удалена позиция из сметы",
            f"{item['item_name']} × {item['qty']}"
        )
    except Exception:
        pass

    return RedirectResponse(f"/task/{task_id}", status_code=302)


@app.post("/task/{task_id}/comment")
async def add_task_comment(request: Request, task_id: int):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    form = await request.form()
    message = (form.get("message") or "").strip()

    conn = connect()
    c = conn.cursor()

    task = c.execute("""
    SELECT * FROM tasks WHERE id=?
    """, (task_id,)).fetchone()

    if not task:
        conn.close()
        return RedirectResponse("/", status_code=302)

    if not can_access_task(username, role, task):
        conn.close()
        return RedirectResponse("/", status_code=302)

    if message:
        c.execute("""
        INSERT INTO task_comments (
            task_id,
            username,
            role,
            message,
            created_at
        )
        VALUES (?, ?, ?, ?, ?)
        """, (
            task_id,
            username,
            role,
            message,
            datetime.now().strftime("%Y-%m-%d %H:%M")
        ))

        conn.commit()

        log_task_activity(
            task_id,
            username,
            role,
            "Добавлен комментарий",
            message
        )

        try:
            send_message(
                f"""
💬 Новый комментарий в заявке #{task_id}

Клиент: {task['client']}
Адрес: {task['address']}
Автор: {username} ({get_role_title(role)})

Комментарий:
{message}
"""
            )
        except Exception:
            pass

    conn.close()

    return RedirectResponse(f"/task/{task_id}", status_code=302)


@app.post("/task/{task_id}/payment")
async def update_payment_status(request: Request, task_id: int):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role not in ("boss", "manager"):
        return RedirectResponse("/", status_code=302)

    form = await request.form()
    new_status = form.get("payment_status") or "Не оплачено"

    allowed = [
        "Не оплачено",
        "Частично оплачено",
        "Оплачено"
    ]

    if new_status not in allowed:
        new_status = "Не оплачено"

    conn = connect()
    c = conn.cursor()

    task = c.execute("""
    SELECT *
    FROM tasks
    WHERE id=?
    """, (task_id,)).fetchone()

    if not task:
        conn.close()
        return RedirectResponse("/", status_code=302)

    old_status = task["payment_status"] if "payment_status" in task.keys() else "Не оплачено"

    c.execute("""
    UPDATE tasks
    SET payment_status=?
    WHERE id=?
    """, (new_status, task_id))

    conn.commit()
    conn.close()

    try:
        log_task_activity(
            task_id,
            username,
            role,
            "Изменён статус оплаты",
            f"{old_status} → {new_status}"
        )
    except Exception:
        pass

    try:
        send_message(
            f"""
💳 Изменён статус оплаты

Заявка: #{task_id}
Клиент: {task['client']}

Было: {old_status}
Стало: {new_status}

Изменил: {username} ({get_role_title(role)})
"""
        )
    except Exception:
        pass

    return RedirectResponse(f"/task/{task_id}", status_code=302)


@app.post("/task/{task_id}/status")
async def update_task_status(request: Request, task_id: int):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    form = await request.form()
    new_status = form.get("status")

    conn = connect()
    c = conn.cursor()

    task = c.execute("""
    SELECT * FROM tasks WHERE id=?
    """, (task_id,)).fetchone()

    if not task:
        conn.close()
        return RedirectResponse("/", status_code=302)

    if not can_access_task(username, role, task):
        conn.close()
        return RedirectResponse("/", status_code=302)

    old_status = task["status"]

    c.execute("""
    UPDATE tasks
    SET status=?
    WHERE id=?
    """, (new_status, task_id))

    conn.commit()
    conn.close()

    if old_status != new_status:
        log_task_activity(
            task_id,
            username,
            role,
            "Изменён статус",
            f"{old_status} → {new_status}"
        )

        role_title = get_role_title(role)

        status_icons = {
            "Новая": "🆕",
            "В работе": "🚧",
            "Завершено": "✅",
            "Отменено": "❌"
        }

        icon = status_icons.get(new_status, "🔄")

        try:
            send_message(
                f"""
{icon} Статус заявки #{task_id} изменён

Клиент: {task['client']}
Адрес: {task['address']}
Исполнитель: {task['worker']}

Было: {old_status}
Стало: {new_status}

Изменил: {username} ({role_title})
"""
            )
        except Exception:
            pass

    return RedirectResponse(f"/task/{task_id}", status_code=302)


@app.post("/task/{task_id}/before-photo")
async def update_before_photo(
    request: Request,
    task_id: int,
    before_photo: UploadFile = File(None)
):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    conn = connect()
    c = conn.cursor()

    task = c.execute("""
    SELECT * FROM tasks WHERE id=?
    """, (task_id,)).fetchone()

    if not task:
        conn.close()
        return RedirectResponse("/", status_code=302)

    if not can_access_task(username, role, task):
        conn.close()
        return RedirectResponse("/", status_code=302)

    filename = save_upload_file(before_photo, task_id, "before")

    if filename:
        c.execute("""
        UPDATE tasks SET photo=? WHERE id=?
        """, (filename, task_id))
        conn.commit()

    conn.close()

    if filename:
        log_task_activity(
            task_id,
            username,
            role,
            "Загружено фото до",
            filename
        )

    try:
        if filename:
            send_photo(
                f"uploads/{filename}",
                f"Фото до работы по заявке #{task_id}"
            )
    except Exception:
        pass

    return RedirectResponse(f"/task/{task_id}", status_code=302)


@app.post("/task/{task_id}/report")
async def update_report(
    request: Request,
    task_id: int,
    after_photo: UploadFile = File(None)
):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    form = await request.form()
    report = form.get("report")

    conn = connect()
    c = conn.cursor()

    task = c.execute("""
    SELECT * FROM tasks WHERE id=?
    """, (task_id,)).fetchone()

    if not task:
        conn.close()
        return RedirectResponse("/", status_code=302)

    if not can_access_task(username, role, task):
        conn.close()
        return RedirectResponse("/", status_code=302)

    after_filename = task["after_photo"] if "after_photo" in task.keys() else ""
    new_after_filename = save_upload_file(after_photo, task_id, "after")

    if new_after_filename:
        after_filename = new_after_filename

    c.execute("""
    UPDATE tasks
    SET report=?, after_photo=?
    WHERE id=?
    """, (
        report,
        after_filename,
        task_id
    ))

    conn.commit()
    conn.close()

    log_task_activity(
        task_id,
        username,
        role,
        "Обновлён отчёт исполнителя",
        report or ""
    )

    if new_after_filename:
        log_task_activity(
            task_id,
            username,
            role,
            "Загружено фото после",
            new_after_filename
        )

    try:
        send_message(
            f"""
📝 Отчёт по заявке #{task_id}

Клиент: {task['client']}
Исполнитель: {task['worker']}

Отчёт:
{report}
"""
        )

        if new_after_filename:
            send_photo(
                f"uploads/{new_after_filename}",
                f"Фото после работы по заявке #{task_id}"
            )
    except Exception:
        pass

    return RedirectResponse(
        f"/task/{task_id}",
        status_code=302
    )



@app.post("/task/{task_id}/archive")
async def archive_task(request: Request, task_id: int):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role not in ("boss", "manager"):
        return RedirectResponse("/", status_code=302)

    conn = connect()
    c = conn.cursor()

    task = c.execute("""
    SELECT * FROM tasks WHERE id=?
    """, (task_id,)).fetchone()

    if not task:
        conn.close()
        return RedirectResponse("/", status_code=302)

    c.execute("""
    UPDATE tasks
    SET archived=1
    WHERE id=?
    """, (task_id,))

    conn.commit()
    conn.close()

    try:
        log_task_activity(
            task_id,
            username,
            role,
            "Заявка отправлена в архив",
            f"Клиент: {task['client']}"
        )
    except Exception:
        pass

    return RedirectResponse("/", status_code=302)


@app.post("/task/{task_id}/unarchive")
async def unarchive_task(request: Request, task_id: int):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role not in ("boss", "manager"):
        return RedirectResponse("/", status_code=302)

    conn = connect()
    c = conn.cursor()

    task = c.execute("""
    SELECT * FROM tasks WHERE id=?
    """, (task_id,)).fetchone()

    if not task:
        conn.close()
        return RedirectResponse("/", status_code=302)

    c.execute("""
    UPDATE tasks
    SET archived=0
    WHERE id=?
    """, (task_id,))

    conn.commit()
    conn.close()

    try:
        log_task_activity(
            task_id,
            username,
            role,
            "Заявка возвращена из архива",
            f"Клиент: {task['client']}"
        )
    except Exception:
        pass

    return RedirectResponse(f"/task/{task_id}", status_code=302)


@app.post("/task/{task_id}/delete")
async def delete_task_forever(request: Request, task_id: int):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role != "boss":
        return RedirectResponse("/", status_code=302)

    conn = connect()
    c = conn.cursor()

    task = c.execute("""
    SELECT *
    FROM tasks
    WHERE id=?
    """, (task_id,)).fetchone()

    if not task:
        conn.close()
        return RedirectResponse("/", status_code=302)

    if "archived" in task.keys() and task["archived"] != 1:
        conn.close()
        return RedirectResponse(f"/task/{task_id}", status_code=302)

    c.execute("DELETE FROM task_items WHERE task_id=?", (task_id,))
    c.execute("DELETE FROM task_comments WHERE task_id=?", (task_id,))
    c.execute("DELETE FROM task_activity WHERE task_id=?", (task_id,))
    c.execute("DELETE FROM tasks WHERE id=?", (task_id,))

    conn.commit()
    conn.close()

    try:
        send_message(
            f"""
🗑 Заявка удалена навсегда

Заявка: #{task_id}
Клиент: {task['client']}
Адрес: {task['address']}

Удалил: {username} ({get_role_title(role)})
"""
        )
    except Exception:
        pass

    return RedirectResponse("/archive", status_code=302)


@app.get("/task/{task_id}/invoice")
async def task_invoice_pdf(request: Request, task_id: int):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    conn = connect()
    c = conn.cursor()

    task = c.execute("""
    SELECT * FROM tasks WHERE id=?
    """, (task_id,)).fetchone()

    if not task:
        conn.close()
        return HTMLResponse("Task not found", status_code=404)

    if not can_access_task(username, role, task):
        conn.close()
        return RedirectResponse("/", status_code=302)

    task_items = c.execute("""
    SELECT *
    FROM task_items
    WHERE task_id=?
    ORDER BY id ASC
    """, (task_id,)).fetchall()

    conn.close()

    estimate_total = sum(item["total"] for item in task_items)
    payment_status = task["payment_status"] if "payment_status" in task.keys() else "Не оплачено"
    settings = get_company_settings()

    pdf_path = DOCS_DIR / f"task_{task_id}_invoice.pdf"
    font_name = register_pdf_font()

    pdf = canvas.Canvas(str(pdf_path), pagesize=A4)
    page_width, page_height = A4

    pdf.setFont(font_name, 22)
    pdf.drawString(40, page_height - 50, f"Счёт по заявке №{task['id']}")

    pdf.setFont(font_name, 10)
    pdf.drawString(40, page_height - 72, f"Дата формирования: {datetime.now().strftime('%Y-%m-%d %H:%M')}")

    y = page_height - 100

    if settings and settings["company_name"]:
        pdf.setFont(font_name, 11)
        pdf.drawString(40, y, "Исполнитель / компания:")
        y -= 16
        y = draw_text(pdf, settings["company_name"], 40, y, font_name, size=10)
        if settings["phone"]:
            y = draw_text(pdf, f"Телефон: {settings['phone']}", 40, y, font_name, size=10)
        if settings["email"]:
            y = draw_text(pdf, f"Email: {settings['email']}", 40, y, font_name, size=10)
        if settings["address"]:
            y = draw_text(pdf, f"Адрес: {settings['address']}", 40, y, font_name, size=10)
        if settings["tax_number"]:
            y = draw_text(pdf, f"VAT / налоговый номер: {settings['tax_number']}", 40, y, font_name, size=10)
        y -= 12
    else:
        y = page_height - 115

    fields = [
        ("Клиент", task["client"]),
        ("Телефон", task["phone"]),
        ("Адрес", task["address"]),
        ("Дата заявки", task["task_date"]),
        ("Исполнитель", task["worker"]),
        ("Статус оплаты", payment_status),
    ]

    for label, value in fields:
        pdf.setFont(font_name, 10)
        pdf.drawString(40, y, f"{label}:")
        y = draw_text(pdf, value, 150, y, font_name, size=10, max_chars=58, line_height=15)
        y -= 4

    y -= 16
    pdf.setFont(font_name, 13)
    pdf.drawString(40, y, "Позиции счёта")
    y -= 24

    if task_items:
        pdf.setFont(font_name, 9)
        pdf.drawString(40, y, "Наименование")
        pdf.drawString(275, y, "Кол-во")
        pdf.drawString(350, y, "Цена")
        pdf.drawString(430, y, "Сумма")
        y -= 14

        for item in task_items:
            if y < 90:
                pdf.showPage()
                y = page_height - 60
                pdf.setFont(font_name, 9)

            item_name = str(item["item_name"] or "")
            if len(item_name) > 42:
                item_name = item_name[:39] + "..."

            pdf.drawString(40, y, item_name)
            pdf.drawString(275, y, f"{item['qty']} {item['unit']}")
            pdf.drawString(350, y, f"${item['price']}")
            pdf.drawString(430, y, f"${item['total']}")
            y -= 16

        y -= 12
        pdf.setFont(font_name, 13)
        pdf.drawString(350, y, "Итого:")
        pdf.drawString(430, y, f"${estimate_total}")
    else:
        y = draw_text(pdf, "Позиции счёта пока не добавлены", 40, y, font_name, size=10)

    y -= 35

    if settings and settings["bank_details"]:
        pdf.setFont(font_name, 12)
        pdf.drawString(40, y, "Банковские реквизиты")
        y -= 18
        y = draw_text(pdf, settings["bank_details"], 40, y, font_name, size=10)
        y -= 12

    pdf.setFont(font_name, 10)
    pdf.drawString(40, y, "Спасибо за обращение!")

    pdf.save()

    try:
        log_task_activity(
            task_id,
            username,
            role,
            "Сформирован PDF счёт",
            f"task_{task_id}_invoice.pdf"
        )
    except Exception:
        pass

    return FileResponse(
        str(pdf_path),
        media_type="application/pdf",
        filename=f"task_{task_id}_invoice.pdf"
    )


@app.get("/task/{task_id}/pdf")
async def task_pdf(request: Request, task_id: int):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    conn = connect()
    c = conn.cursor()

    task = c.execute("""
    SELECT * FROM tasks WHERE id=?
    """, (task_id,)).fetchone()

    conn.close()

    if not task:
        return HTMLResponse("Task not found", status_code=404)

    if not can_access_task(username, role, task):
        return RedirectResponse("/", status_code=302)

    task_items = c.execute("""
    SELECT *
    FROM task_items
    WHERE task_id=?
    ORDER BY id ASC
    """, (task_id,)).fetchall()

    estimate_total = sum(item["total"] for item in task_items)
    settings = get_company_settings()

    pdf_path = DOCS_DIR / f"task_{task_id}.pdf"
    font_name = register_pdf_font()

    pdf = canvas.Canvas(str(pdf_path), pagesize=A4)
    page_width, page_height = A4

    pdf.setFont(font_name, 20)
    pdf.drawString(40, page_height - 50, f"Акт выполненных работ №{task['id']}")

    pdf.setFont(font_name, 10)
    pdf.drawString(40, page_height - 72, f"Дата формирования: {datetime.now().strftime('%Y-%m-%d %H:%M')}")

    y = page_height - 100

    if settings and settings["company_name"]:
        pdf.setFont(font_name, 11)
        pdf.drawString(40, y, "Исполнитель / компания:")
        y -= 16
        y = draw_text(pdf, settings["company_name"], 40, y, font_name, size=10)
        if settings["phone"]:
            y = draw_text(pdf, f"Телефон: {settings['phone']}", 40, y, font_name, size=10)
        if settings["email"]:
            y = draw_text(pdf, f"Email: {settings['email']}", 40, y, font_name, size=10)
        if settings["address"]:
            y = draw_text(pdf, f"Адрес: {settings['address']}", 40, y, font_name, size=10)
        if settings["tax_number"]:
            y = draw_text(pdf, f"VAT / налоговый номер: {settings['tax_number']}", 40, y, font_name, size=10)
        y -= 12
    else:
        y = page_height - 110

    fields = [
        ("Клиент", task["client"]),
        ("Телефон", task["phone"]),
        ("Адрес", task["address"]),
        ("Дата заявки", task["task_date"]),
        ("Исполнитель", task["worker"]),
        ("Приоритет", task["priority"]),
        ("Стоимость", f"${task['price']}"),
        ("Статус", task["status"]),
        ("Статус оплаты", task["payment_status"] if "payment_status" in task.keys() else "Не оплачено"),
    ]

    for label, value in fields:
        pdf.setFont(font_name, 10)
        pdf.drawString(40, y, f"{label}:")
        y = draw_text(pdf, value, 145, y, font_name, size=10, max_chars=58, line_height=15)
        y -= 4

    y -= 8
    pdf.setFont(font_name, 12)
    pdf.drawString(40, y, "Описание работ")
    y -= 20
    y = draw_text(pdf, task["description"], 40, y, font_name, size=10)

    y -= 14
    pdf.setFont(font_name, 12)
    pdf.drawString(40, y, "Отчёт исполнителя")
    y -= 20
    y = draw_text(pdf, task["report"] if "report" in task.keys() else "", 40, y, font_name, size=10)

    y -= 18
    pdf.setFont(font_name, 12)
    pdf.drawString(40, y, "Смета / выполненные работы")
    y -= 22

    if task_items:
        pdf.setFont(font_name, 9)
        pdf.drawString(40, y, "Наименование")
        pdf.drawString(275, y, "Кол-во")
        pdf.drawString(350, y, "Цена")
        pdf.drawString(430, y, "Сумма")
        y -= 14

        for item in task_items:
            if y < 90:
                pdf.showPage()
                y = page_height - 60
                pdf.setFont(font_name, 9)

            pdf.setFont(font_name, 9)

            item_name = str(item["item_name"] or "")
            if len(item_name) > 42:
                item_name = item_name[:39] + "..."

            pdf.drawString(40, y, item_name)
            pdf.drawString(275, y, f"{item['qty']} {item['unit']}")
            pdf.drawString(350, y, f"${item['price']}")
            pdf.drawString(430, y, f"${item['total']}")
            y -= 16

        y -= 8
        pdf.setFont(font_name, 11)
        pdf.drawString(350, y, "Итого:")
        pdf.drawString(430, y, f"${estimate_total}")
        y -= 18
    else:
        y = draw_text(pdf, "Смета пока не заполнена", 40, y, font_name, size=10)
        y -= 10

    y -= 18
    y = draw_pdf_image(pdf, task["photo"], "Фото до работы", 40, y, font_name)
    y = draw_pdf_image(pdf, task["after_photo"] if "after_photo" in task.keys() else "", "Фото после работы", 40, y, font_name)

    if y < 120:
        pdf.showPage()
        y = page_height - 60

    pdf.setFont(font_name, 11)
    pdf.drawString(40, y, "Подпись клиента: ______________________________")
    y -= 35
    pdf.drawString(40, y, "Подпись исполнителя: ___________________________")

    pdf.save()

    log_task_activity(
        task_id,
        username,
        role,
        "Сформирован PDF акт",
        f"task_{task_id}_act.pdf"
    )

    return FileResponse(
        str(pdf_path),
        media_type="application/pdf",
        filename=f"task_{task_id}_act.pdf"
    )
