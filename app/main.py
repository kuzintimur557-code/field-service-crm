from fastapi import FastAPI, Request, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse, FileResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.database import connect, init_db
from app.telegram_utils import send_message, send_photo, send_message_to_chat

from datetime import datetime, timedelta
from pathlib import Path
from uuid import uuid4
from urllib.parse import urlencode
from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

import shutil
import os
import hmac
import hashlib
import bcrypt
import base64
import secrets
import csv
import io
import calendar


APP_VERSION = "0.2.1"

SESSION_COOKIE_NAME = "crm_session"
SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-change-me")
COOKIE_SECURE = (
    os.getenv("COOKIE_SECURE", "").lower() in ("1", "true", "yes", "on")
    or bool(os.getenv("RAILWAY_ENVIRONMENT"))
)

if os.getenv("ENV") == "production" and SECRET_KEY == "dev-secret-change-me":
    raise RuntimeError("SECRET_KEY must be set in production")

app = FastAPI()

init_db()

os.makedirs("uploads/docs", exist_ok=True)

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


def get_task_worker_names(task):
    names = []

    if not task:
        return names

    task_keys = task.keys() if hasattr(task, "keys") else []

    for field in ("worker", "workers"):
        if field not in task_keys:
            continue

        for name in str(task[field] or "").split(","):
            name = name.strip()

            if name and name not in names:
                names.append(name)

    return names


def format_task_workers(task):
    names = get_task_worker_names(task)
    return ", ".join(names) if names else "Не назначены"


def worker_task_condition():
    return """
    (
        worker=?
        OR worker LIKE ?
        OR worker LIKE ?
        OR worker LIKE ?
        OR workers=?
        OR workers LIKE ?
        OR workers LIKE ?
        OR workers LIKE ?
    )
    """


def worker_task_params(username):
    return [
        username,
        f"{username},%",
        f"%,{username},%",
        f"%,{username}",
        username,
        f"{username},%",
        f"%,{username},%",
        f"%,{username}"
    ]


def task_has_worker(username, task):
    return username in get_task_worker_names(task)


def get_overdue_days(task_date, today=None):
    task_day = str(task_date or "")[:10]

    if not task_day:
        return 0

    try:
        current_day = today or datetime.now().date()
        due_day = datetime.strptime(task_day, "%Y-%m-%d").date()
        return max((current_day - due_day).days, 0)
    except Exception:
        return 0


def add_months(source_date, months):
    month = source_date.month - 1 + months
    year = source_date.year + month // 12
    month = month % 12 + 1
    day = min(source_date.day, calendar.monthrange(year, month)[1])
    return source_date.replace(year=year, month=month, day=day)


def get_next_recurring_date(current_date, interval_type):
    try:
        due_date = datetime.strptime(str(current_date or "")[:10], "%Y-%m-%d").date()
    except Exception:
        return current_date

    if interval_type == "weekly":
        next_date = due_date + timedelta(weeks=1)
    elif interval_type == "quarterly":
        next_date = add_months(due_date, 3)
    elif interval_type == "yearly":
        next_date = add_months(due_date, 12)
    else:
        next_date = add_months(due_date, 1)

    return next_date.strftime("%Y-%m-%d")


def get_task_worker_chat_ids(cursor, task):
    chat_ids = []
    task_company_id = task["company_id"] if "company_id" in task.keys() else 1

    for worker_name in get_task_worker_names(task):
        worker = cursor.execute("""
        SELECT telegram_chat_id
        FROM users
        WHERE username=? AND role='worker' AND company_id=?
        """, (worker_name, task_company_id)).fetchone()

        if worker and worker["telegram_chat_id"] and worker["telegram_chat_id"] not in chat_ids:
            chat_ids.append(worker["telegram_chat_id"])

    return chat_ids


def can_access_task(username, role, task):
    if not task:
        return False

    if role == "superadmin":
        return True

    user_company_id = get_user_company_id(username)
    task_company_id = task["company_id"] if "company_id" in task.keys() else 1

    if role in ("boss", "manager"):
        return task_company_id == user_company_id

    return task_company_id == user_company_id and task_has_worker(username, task)


def get_role_title(role):
    titles = {
        "boss": "Босс",
        "manager": "Менеджер",
        "worker": "Исполнитель"
    }
    return titles.get(role, role)


def hash_password(password):
    hashed = bcrypt.hashpw(
        password.encode("utf-8"),
        bcrypt.gensalt()
    )
    return "bcrypt$" + hashed.decode("utf-8")


def verify_password(password, stored_password):
    if not stored_password:
        return False

    stored_password = str(stored_password)

    if stored_password.startswith("bcrypt$"):
        bcrypt_hash = stored_password.replace("bcrypt$", "", 1)
        return bcrypt.checkpw(
            password.encode("utf-8"),
            bcrypt_hash.encode("utf-8")
        )

    if stored_password.startswith("sha256$"):
        try:
            _, salt, digest = stored_password.split("$", 2)
            check = hashlib.sha256((salt + password).encode("utf-8")).hexdigest()
            return secrets.compare_digest(check, digest)
        except Exception:
            return False

    return secrets.compare_digest(password, stored_password)


def password_needs_upgrade(stored_password):
    return not str(stored_password or "").startswith("bcrypt$")


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


def get_company_settings(company_id=1):
    company_id = company_id or 1

    conn = connect()
    c = conn.cursor()

    c.execute("""
    INSERT OR IGNORE INTO company_settings (
        company_id, company_name, phone, email, address, tax_number, bank_details,
        plan, industry, task_label, worker_label, client_label, service_label,
        one_c_enabled, calls_enabled, ai_calls_enabled, updated_at
    )
    VALUES (?, '', '', '', '', '', '', 'basic', 'field_service',
            'Заявка', 'Исполнитель', 'Клиент', 'Услуга', 0, 0, 0, '')
    """, (company_id,))

    conn.commit()

    settings = c.execute("""
    SELECT *
    FROM company_settings
    WHERE company_id=?
    """, (company_id,)).fetchone()

    conn.close()

    return settings


def create_notification(
    company_id,
    username,
    title,
    message="",
    link=""
):

    conn = connect()
    c = conn.cursor()

    c.execute("""
    INSERT INTO notifications (
        company_id,
        username,
        title,
        message,
        link,
        created_at
    )
    VALUES (?, ?, ?, ?, ?, ?)
    """, (
        company_id,
        username,
        title,
        message,
        link,
        datetime.now().strftime("%Y-%m-%d %H:%M")
    ))

    conn.commit()
    conn.close()


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
    signed_value = request.cookies.get(SESSION_COOKIE_NAME)
    username = verify_session_value(signed_value)

    if username:
        return username

    return None


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

    return user["company_id"] if "company_id" in user.keys() else 1


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


@app.get("/uploads/{filename:path}")
async def uploaded_file(request: Request, filename: str):

    username = get_user(request)

    if not username:
        return Response(status_code=404)

    safe_filename = Path(filename or "").name

    if not safe_filename or safe_filename != filename:
        return Response(status_code=404)

    file_path = UPLOAD_DIR / safe_filename

    if not file_path.is_file():
        return Response(status_code=404)

    role = get_role(username)

    conn = connect()
    c = conn.cursor()

    task = c.execute("""
    SELECT *
    FROM tasks
    WHERE photo=? OR after_photo=?
    """, (safe_filename, safe_filename)).fetchone()

    conn.close()

    if not task or not can_access_task(username, role, task):
        return Response(status_code=404)

    return FileResponse(str(file_path))


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


@app.post("/platform/companies")
async def create_platform_company(request: Request):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role != "superadmin":
        return RedirectResponse("/", status_code=302)

    form = await request.form()

    company_name = (form.get("company_name") or "").strip()
    owner_username = (form.get("owner_username") or "").strip()
    owner_password = (form.get("owner_password") or "").strip()

    if not company_name or not owner_username or not owner_password:
        return RedirectResponse("/platform/companies?error=empty", status_code=302)

    if not is_password_strong(owner_password):
        return RedirectResponse("/platform/companies?error=weak_password", status_code=302)

    conn = connect()
    c = conn.cursor()

    existing_user = c.execute("""
    SELECT id
    FROM users
    WHERE username=?
    """, (owner_username,)).fetchone()

    if existing_user:
        conn.close()
        return RedirectResponse("/platform/companies?error=user_exists", status_code=302)

    c.execute("""
    INSERT INTO companies (
        name,
        owner_username,
        created_at
    )
    VALUES (?, ?, ?)
    """, (
        company_name,
        owner_username,
        datetime.now().strftime("%Y-%m-%d %H:%M")
    ))

    company_id = c.lastrowid

    c.execute("""
    INSERT INTO users (
        username,
        password,
        role,
        company_id,
        last_seen
    )
    VALUES (?, ?, ?, ?, ?)
    """, (
        owner_username,
        hash_password(owner_password),
        "boss",
        company_id,
        datetime.now().strftime("%Y-%m-%d %H:%M")
    ))

    c.execute("""
    INSERT OR IGNORE INTO company_settings (
        company_id,
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
        updated_at
    )
    VALUES (?, ?, '', '', '', '', '', 'basic', 0, 0, 0, ?)
    """, (
        company_id,
        company_name,
        datetime.now().strftime("%Y-%m-%d %H:%M")
    ))

    conn.commit()
    conn.close()

    return RedirectResponse("/platform/companies?created=1", status_code=302)


@app.get("/platform/companies", response_class=HTMLResponse)
async def platform_companies_page(request: Request):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role != "superadmin":
        return RedirectResponse("/", status_code=302)

    conn = connect()
    c = conn.cursor()

    companies = c.execute("""
    SELECT *
    FROM companies
    ORDER BY id DESC
    """).fetchall()

    conn.close()

    return templates.TemplateResponse(
        request,
        "platform_companies.html",
        {
            "request": request,
            "username": username,
            "role": role,
            "companies": companies
        }
    )


@app.get("/platform", response_class=HTMLResponse)
async def platform_dashboard(request: Request):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role != "superadmin":
        return RedirectResponse("/", status_code=302)

    conn = connect()
    c = conn.cursor()

    companies_count = c.execute("SELECT COUNT(*) FROM companies").fetchone()[0]
    users_count = c.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    tasks_count = c.execute("SELECT COUNT(*) FROM tasks").fetchone()[0]
    clients_count = c.execute("SELECT COUNT(*) FROM clients").fetchone()[0]

    companies = c.execute("""
    SELECT *
    FROM companies
    ORDER BY id DESC
    """).fetchall()

    conn.close()

    return templates.TemplateResponse(
        request,
        "platform.html",
        {
            "request": request,
            "username": username,
            "role": role,
            "companies_count": companies_count,
            "users_count": users_count,
            "tasks_count": tasks_count,
            "clients_count": clients_count,
            "companies": companies
        }
    )


@app.get("/my-tasks", response_class=HTMLResponse)
async def my_tasks_page(request: Request, status: str = ""):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role != "worker":
        return RedirectResponse("/", status_code=302)

    company_id = get_user_company_id(username)

    conn = connect()
    c = conn.cursor()

    query = """
    SELECT *
    FROM tasks
    WHERE archived=0
      AND company_id=?
    """

    query += f" AND {worker_task_condition()}"
    params = [company_id] + worker_task_params(username)

    if status:
        query += " AND status=?"
        params.append(status)
    else:
        query += " AND status!='Завершено'"

    query += " ORDER BY task_date DESC"

    tasks = c.execute(query, params).fetchall()

    conn.close()

    return templates.TemplateResponse(
        request,
        "my_tasks.html",
        {
            "request": request,
            "username": username,
            "role": role,
            "tasks": tasks,
            "selected_status": status
        }
    )


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

    if role == "superadmin":
        return RedirectResponse("/platform", status_code=302)

    if role == "worker":
        return RedirectResponse("/my-tasks", status_code=302)

    company_id = get_user_company_id(username)

    conn = connect()
    c = conn.cursor()

    query = "SELECT * FROM tasks WHERE archived=0 AND company_id=?"
    params = [company_id]

    if role not in ("boss", "manager"):
        query += f" AND {worker_task_condition()}"
        params += worker_task_params(username)

    if status:
        query += " AND status=?"
        params.append(status)

    if worker and role in ("boss", "manager"):
        query += f" AND {worker_task_condition()}"
        params += worker_task_params(worker)

    if task_date:
        query += " AND task_date=?"
        params.append(task_date)

    if search:
        query += " AND client LIKE ?"
        params.append(f"%{search}%")

    query += " ORDER BY id DESC"

    tasks = c.execute(query, params).fetchall()

    if role in ("boss", "manager"):
        total_tasks = c.execute("SELECT COUNT(*) FROM tasks WHERE archived=0 AND company_id=?", (company_id,)).fetchone()[0]
        new_tasks = c.execute("SELECT COUNT(*) FROM tasks WHERE archived=0 AND company_id=? AND status='Новая'", (company_id,)).fetchone()[0]
        working_tasks = c.execute("SELECT COUNT(*) FROM tasks WHERE archived=0 AND company_id=? AND status='В работе'", (company_id,)).fetchone()[0]
        done_tasks = c.execute("SELECT COUNT(*) FROM tasks WHERE archived=0 AND company_id=? AND status='Завершено'", (company_id,)).fetchone()[0]

        revenue = c.execute("""
        SELECT SUM(price) FROM tasks WHERE archived=0 AND company_id=? AND status='Завершено'
        """, (company_id,)).fetchone()[0]
    else:
        worker_condition = worker_task_condition()
        worker_params = worker_task_params(username)

        total_tasks = c.execute(f"""
        SELECT COUNT(*) FROM tasks
        WHERE archived=0 AND company_id=? AND {worker_condition}
        """, [company_id] + worker_params).fetchone()[0]

        new_tasks = c.execute(f"""
        SELECT COUNT(*) FROM tasks
        WHERE archived=0 AND company_id=? AND {worker_condition}
          AND status='Новая'
        """, [company_id] + worker_params).fetchone()[0]

        working_tasks = c.execute(f"""
        SELECT COUNT(*) FROM tasks
        WHERE archived=0 AND company_id=? AND {worker_condition}
          AND status='В работе'
        """, [company_id] + worker_params).fetchone()[0]

        done_tasks = c.execute(f"""
        SELECT COUNT(*) FROM tasks
        WHERE archived=0 AND company_id=? AND {worker_condition}
          AND status='Завершено'
        """, [company_id] + worker_params).fetchone()[0]

        revenue = c.execute(f"""
        SELECT SUM(price) FROM tasks
        WHERE archived=0 AND company_id=? AND {worker_condition}
          AND status='Завершено'
        """, [company_id] + worker_params).fetchone()[0]

    if revenue is None:
        revenue = 0

    today = datetime.now().strftime("%Y-%m-%d")
    now_value = datetime.now().strftime("%Y-%m-%dT%H:%M")
    sla_soon_value = (datetime.now() + timedelta(hours=24)).strftime("%Y-%m-%dT%H:%M")

    today_tasks = c.execute("""
    SELECT COUNT(*)
    FROM tasks
    WHERE archived=0
      AND company_id=?
      AND task_date LIKE ?
    """, (company_id, f"{today}%")).fetchone()[0]

    overdue_tasks = c.execute("""
    SELECT COUNT(*)
    FROM tasks
    WHERE archived=0
      AND company_id=?
      AND status NOT IN ('Завершено', 'Отменено')
      AND task_date IS NOT NULL
      AND task_date!=''
      AND task_date < ?
    """, (company_id, today)).fetchone()[0]

    sla_breached_tasks = c.execute("""
    SELECT COUNT(*)
    FROM tasks
    WHERE archived=0
      AND company_id=?
      AND status NOT IN ('Завершено', 'Отменено')
      AND deadline_at IS NOT NULL
      AND deadline_at!=''
      AND deadline_at < ?
    """, (company_id, now_value)).fetchone()[0]

    sla_due_soon_tasks = c.execute("""
    SELECT COUNT(*)
    FROM tasks
    WHERE archived=0
      AND company_id=?
      AND status NOT IN ('Завершено', 'Отменено')
      AND deadline_at IS NOT NULL
      AND deadline_at!=''
      AND deadline_at >= ?
      AND deadline_at <= ?
    """, (company_id, now_value, sla_soon_value)).fetchone()[0]

    active_workers = c.execute("""
    SELECT COUNT(DISTINCT worker)
    FROM tasks
    WHERE archived=0
      AND company_id=?
      AND status='В работе'
    """, (company_id,)).fetchone()[0]


    workers = c.execute("""
    SELECT username, last_seen FROM users
    WHERE role='worker' AND company_id=?
    ORDER BY username
    """, (company_id,)).fetchall()

    clients = []

    worker_stats = []

    if role in ("boss", "manager"):
        for w in workers:
            worker_name = w["username"]
            worker_condition = worker_task_condition()
            worker_params = worker_task_params(worker_name)

            completed = c.execute(f"""
            SELECT COUNT(*) FROM tasks
            WHERE archived=0 AND company_id=? AND {worker_condition}
              AND status='Завершено'
            """, [company_id] + worker_params).fetchone()[0]

            active = c.execute(f"""
            SELECT COUNT(*) FROM tasks
            WHERE archived=0 AND company_id=? AND {worker_condition}
              AND status='В работе'
            """, [company_id] + worker_params).fetchone()[0]

            worker_revenue = c.execute(f"""
            SELECT SUM(price) FROM tasks
            WHERE archived=0 AND company_id=? AND {worker_condition}
              AND status='Завершено'
            """, [company_id] + worker_params).fetchone()[0]

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
            "today_tasks": today_tasks,
            "overdue_tasks": overdue_tasks,
            "sla_breached_tasks": sla_breached_tasks,
            "sla_due_soon_tasks": sla_due_soon_tasks,
            "active_workers": active_workers,
            "workers": workers,
            "worker_stats": worker_stats,
            "selected_status": status,
            "selected_worker": worker,
            "selected_date": task_date,
            "search": search
        }
    )


@app.get("/notifications", response_class=HTMLResponse)
async def notifications_page(request: Request):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)
    company_id = get_user_company_id(username)

    conn = connect()
    c = conn.cursor()

    notifications = c.execute("""
    SELECT *
    FROM notifications
    WHERE company_id=?
      AND username=?
    ORDER BY id DESC
    LIMIT 100
    """, (company_id, username)).fetchall()

    unread_count = c.execute("""
    SELECT COUNT(*)
    FROM notifications
    WHERE company_id=?
      AND username=?
      AND is_read=0
    """, (company_id, username)).fetchone()[0]

    conn.close()

    return templates.TemplateResponse(
        request,
        "notifications.html",
        {
            "request": request,
            "username": username,
            "role": role,
            "notifications": notifications,
            "unread_count": unread_count
        }
    )


@app.post("/notifications/read-all")
async def mark_all_notifications_read(request: Request):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    company_id = get_user_company_id(username)

    conn = connect()
    c = conn.cursor()

    c.execute("""
    UPDATE notifications
    SET is_read=1
    WHERE company_id=?
      AND username=?
    """, (company_id, username))

    conn.commit()
    conn.close()

    return RedirectResponse("/notifications", status_code=302)


@app.get("/notifications/{notification_id}/open")
async def open_notification(request: Request, notification_id: int):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    company_id = get_user_company_id(username)

    conn = connect()
    c = conn.cursor()

    notification = c.execute("""
    SELECT *
    FROM notifications
    WHERE id=?
      AND company_id=?
      AND username=?
    """, (notification_id, company_id, username)).fetchone()

    if not notification:
        conn.close()
        return RedirectResponse("/notifications", status_code=302)

    c.execute("""
    UPDATE notifications
    SET is_read=1
    WHERE id=?
      AND company_id=?
      AND username=?
    """, (notification_id, company_id, username))

    conn.commit()
    conn.close()

    link = (notification["link"] or "").strip()

    if not link or not link.startswith("/") or link.startswith("//"):
        link = "/notifications"

    return RedirectResponse(link, status_code=302)


@app.get("/workload", response_class=HTMLResponse)
async def workload_page(request: Request):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role not in ("boss", "manager"):
        return RedirectResponse("/", status_code=302)

    company_id = get_user_company_id(username)

    conn = connect()
    c = conn.cursor()

    workers = c.execute("""
    SELECT username, full_name, position, last_seen
    FROM users
    WHERE role='worker' AND company_id=?
    ORDER BY username
    """, (company_id,)).fetchall()

    stats = []

    for worker in workers:
        name = worker["username"]

        total = c.execute(f"""
        SELECT COUNT(*)
        FROM tasks
        WHERE archived=0
          AND company_id=?
          AND ({worker_task_condition()})
        """, [company_id] + worker_task_params(name)).fetchone()[0]

        active = c.execute(f"""
        SELECT COUNT(*)
        FROM tasks
        WHERE archived=0
          AND company_id=?
          AND status='В работе'
          AND ({worker_task_condition()})
        """, [company_id] + worker_task_params(name)).fetchone()[0]

        new = c.execute(f"""
        SELECT COUNT(*)
        FROM tasks
        WHERE archived=0
          AND company_id=?
          AND status='Новая'
          AND ({worker_task_condition()})
        """, [company_id] + worker_task_params(name)).fetchone()[0]

        done = c.execute(f"""
        SELECT COUNT(*)
        FROM tasks
        WHERE archived=0
          AND company_id=?
          AND status='Завершено'
          AND ({worker_task_condition()})
        """, [company_id] + worker_task_params(name)).fetchone()[0]

        if active >= 3:
            load_status = "Перегружен"
        elif active == 0 and new == 0:
            load_status = "Свободен"
        else:
            load_status = "В норме"

        stats.append({
            "worker": worker,
            "total": total,
            "active": active,
            "new": new,
            "done": done,
            "load_status": load_status
        })

    conn.close()

    return templates.TemplateResponse(
        request,
        "workload.html",
        {
            "request": request,
            "username": username,
            "role": role,
            "stats": stats
        }
    )


@app.post("/sla/reminders")
async def create_sla_reminders(request: Request):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role not in ("boss", "manager"):
        return RedirectResponse("/", status_code=302)

    company_id = get_user_company_id(username)
    now_value = datetime.now().strftime("%Y-%m-%dT%H:%M")
    soon_value = (datetime.now() + timedelta(hours=24)).strftime("%Y-%m-%dT%H:%M")

    conn = connect()
    c = conn.cursor()

    tasks = c.execute("""
    SELECT *
    FROM tasks
    WHERE archived=0
      AND company_id=?
      AND status!='Завершено'
      AND deadline_at IS NOT NULL
      AND deadline_at!=''
      AND deadline_at < ?
    ORDER BY deadline_at ASC
    """, (company_id, now_value)).fetchall()

    users = c.execute("""
    SELECT username
    FROM users
    WHERE company_id=?
      AND role IN ('boss', 'manager')
    """, (company_id,)).fetchall()

    created_count = 0

    for task in tasks:
        for user in users:
            existing_notification = c.execute("""
            SELECT id
            FROM notifications
            WHERE company_id=?
              AND username=?
              AND title=?
              AND link=?
              AND is_read=0
            """, (
                company_id,
                user["username"],
                "🔴 Просрочен SLA",
                f"/task/{task['id']}"
            )).fetchone()

            if existing_notification:
                continue

            c.execute("""
            INSERT INTO notifications (
                company_id,
                username,
                title,
                message,
                link,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """, (
                company_id,
                user["username"],
                "🔴 Просрочен SLA",
                f"Заявка #{task['id']} просрочила deadline",
                f"/task/{task['id']}",
                datetime.now().strftime("%Y-%m-%d %H:%M")
            ))
            created_count += 1

    conn.commit()
    conn.close()

    return RedirectResponse(f"/sla?reminders=1&created={created_count}&filter=overdue", status_code=302)


@app.post("/sla/escalations")
async def create_sla_escalations(request: Request):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role not in ("boss", "manager"):
        return RedirectResponse("/", status_code=302)

    company_id = get_user_company_id(username)
    escalation_cutoff = (datetime.now() - timedelta(hours=24)).strftime("%Y-%m-%dT%H:%M")

    conn = connect()
    c = conn.cursor()

    tasks = c.execute("""
    SELECT *
    FROM tasks
    WHERE archived=0
      AND company_id=?
      AND status!='Завершено'
      AND deadline_at IS NOT NULL
      AND deadline_at!=''
      AND deadline_at < ?
    ORDER BY deadline_at ASC
    """, (company_id, escalation_cutoff)).fetchall()

    bosses = c.execute("""
    SELECT username
    FROM users
    WHERE company_id=?
      AND role='boss'
    """, (company_id,)).fetchall()

    created_count = 0

    for task in tasks:
        for boss in bosses:
            existing_notification = c.execute("""
            SELECT id
            FROM notifications
            WHERE company_id=?
              AND username=?
              AND title=?
              AND link=?
              AND is_read=0
            """, (
                company_id,
                boss["username"],
                "🚨 SLA эскалация",
                f"/task/{task['id']}"
            )).fetchone()

            if existing_notification:
                continue

            c.execute("""
            INSERT INTO notifications (
                company_id,
                username,
                title,
                message,
                link,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """, (
                company_id,
                boss["username"],
                "🚨 SLA эскалация",
                f"Заявка #{task['id']} просрочила SLA больше чем на 24 часа",
                f"/task/{task['id']}",
                datetime.now().strftime("%Y-%m-%d %H:%M")
            ))
            created_count += 1

    conn.commit()
    conn.close()

    return RedirectResponse(f"/sla?escalations=1&created={created_count}&filter=overdue", status_code=302)


@app.get("/sla", response_class=HTMLResponse)
async def sla_page(request: Request, filter: str = "", worker: str = ""):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role not in ("boss", "manager"):
        return RedirectResponse("/", status_code=302)

    company_id = get_user_company_id(username)
    now_value = datetime.now().strftime("%Y-%m-%dT%H:%M")
    soon_value = (datetime.now() + timedelta(hours=24)).strftime("%Y-%m-%dT%H:%M")

    conn = connect()
    c = conn.cursor()

    tasks = c.execute("""
    SELECT *
    FROM tasks
    WHERE archived=0
      AND company_id=?
      AND deadline_at IS NOT NULL
      AND deadline_at!=''
    ORDER BY deadline_at ASC
    """, (company_id,)).fetchall()

    workers = c.execute("""
    SELECT username
    FROM users
    WHERE role='worker'
      AND company_id=?
    ORDER BY username
    """, (company_id,)).fetchall()
    worker_names = [w["username"] for w in workers]

    all_sla_tasks = list(tasks)
    sla_overdue_count = len([
        t for t in all_sla_tasks
        if t["status"] != "Завершено"
        and t["deadline_at"] < now_value
    ])
    sla_due_soon_count = len([
        t for t in all_sla_tasks
        if t["status"] != "Завершено"
        and now_value <= t["deadline_at"] <= soon_value
    ])
    sla_done_count = len([
        t for t in all_sla_tasks
        if t["status"] == "Завершено"
    ])
    sla_active_count = len([
        t for t in all_sla_tasks
        if t["status"] != "Завершено"
        and t["deadline_at"] >= now_value
    ])
    sla_stats = {
        "total": len(all_sla_tasks),
        "overdue": sla_overdue_count,
        "soon": sla_due_soon_count,
        "active": sla_active_count,
        "done": sla_done_count
    }
    worker_sla_stats = []

    for worker_row in workers:
        worker_name = worker_row["username"]
        worker_tasks = [
            t for t in all_sla_tasks
            if can_access_task(worker_name, "worker", t)
        ]
        worker_sla_stats.append({
            "username": worker_name,
            "total": len(worker_tasks),
            "overdue": len([
                t for t in worker_tasks
                if t["status"] != "Завершено"
                and t["deadline_at"] < now_value
            ]),
            "soon": len([
                t for t in worker_tasks
                if t["status"] != "Завершено"
                and now_value <= t["deadline_at"] <= soon_value
            ]),
            "done": len([
                t for t in worker_tasks
                if t["status"] == "Завершено"
            ])
        })

    if filter == "overdue":
        tasks = [
            t for t in tasks
            if t["status"] != "Завершено"
            and t["deadline_at"] < now_value
        ]

    elif filter == "active":
        tasks = [
            t for t in tasks
            if t["status"] != "Завершено"
            and t["deadline_at"] >= now_value
        ]

    elif filter == "soon":
        tasks = [
            t for t in tasks
            if t["status"] != "Завершено"
            and now_value <= t["deadline_at"] <= soon_value
        ]

    elif filter == "done":
        tasks = [
            t for t in tasks
            if t["status"] == "Завершено"
        ]

    if worker and worker in worker_names:
        tasks = [
            t for t in tasks
            if can_access_task(worker, "worker", t)
        ]
    elif worker:
        tasks = []

    conn.close()

    return templates.TemplateResponse(
        request,
        "sla.html",
        {
            "request": request,
            "username": username,
            "role": role,
            "tasks": tasks,
            "sla_stats": sla_stats,
            "worker_sla_stats": worker_sla_stats,
            "workers": workers,
            "now_value": now_value,
            "soon_value": soon_value,
            "selected_filter": filter,
            "selected_worker": worker
        }
    )


@app.get("/today", response_class=HTMLResponse)
async def today_page(request: Request):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role not in ("boss", "manager"):
        return RedirectResponse("/", status_code=302)

    company_id = get_user_company_id(username)
    today = datetime.now().strftime("%Y-%m-%d")

    conn = connect()
    c = conn.cursor()

    tasks = c.execute("""
    SELECT *
    FROM tasks
    WHERE archived=0
      AND company_id=?
      AND task_date LIKE ?
    ORDER BY task_date ASC
    """, (company_id, f"{today}%")).fetchall()

    conn.close()

    return templates.TemplateResponse(
        request,
        "today.html",
        {
            "request": request,
            "username": username,
            "role": role,
            "tasks": tasks,
            "today": today
        }
    )


@app.get("/overdue", response_class=HTMLResponse)
async def overdue_page(request: Request):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role not in ("boss", "manager"):
        return RedirectResponse("/", status_code=302)

    company_id = get_user_company_id(username)
    today_date = datetime.now().date()
    today = today_date.strftime("%Y-%m-%d")

    conn = connect()
    c = conn.cursor()

    tasks = c.execute("""
    SELECT *
    FROM tasks
    WHERE archived=0
      AND company_id=?
      AND status NOT IN ('Завершено', 'Отменено')
      AND task_date IS NOT NULL
      AND task_date!=''
      AND task_date < ?
    ORDER BY task_date ASC
    """, (company_id, today)).fetchall()

    entries = []

    for task in tasks:
        overdue_days = get_overdue_days(task["task_date"], today_date)
        entries.append({
            "task": task,
            "overdue_days": overdue_days,
            "sla_status": "Нарушен SLA" if overdue_days > 1 else "Просрочено"
        })

    conn.close()

    return templates.TemplateResponse(
        request,
        "overdue.html",
        {
            "request": request,
            "username": username,
            "role": role,
            "tasks": tasks,
            "entries": entries
        }
    )


@app.get("/calendar", response_class=HTMLResponse)
async def calendar_page(request: Request, worker: str = "", month: str = "", status: str = "", date: str = "", availability: str = ""):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    update_last_seen(username)
    role = get_role(username)

    if role == "superadmin":
        return RedirectResponse("/platform", status_code=302)

    company_id = get_user_company_id(username)

    conn = connect()
    c = conn.cursor()

    workers = []
    worker_loads = []
    worker_availability = []
    availability_summary = {
        "total": 0,
        "free": 0,
        "busy": 0
    }
    selected_availability = availability if availability in ("free", "busy") else ""
    selected_date = str(date or "").strip()

    try:
        if selected_date:
            datetime.strptime(selected_date, "%Y-%m-%d")
    except Exception:
        selected_date = ""

    availability_date = selected_date or datetime.now().strftime("%Y-%m-%d")

    query = """
    SELECT *
    FROM tasks
    WHERE archived=0 AND company_id=?
    """
    params = [company_id]

    if month:
        query += " AND task_date LIKE ?"
        params.append(f"{month}%")

    if selected_date:
        query += " AND task_date LIKE ?"
        params.append(f"{selected_date}%")

    if role in ("boss", "manager"):
        workers = c.execute("""
        SELECT username
        FROM users
        WHERE role='worker' AND company_id=?
        ORDER BY username
        """, (company_id,)).fetchall()
        worker_names = [w["username"] for w in workers]

        if worker and worker in worker_names:
            query += f" AND {worker_task_condition()}"
            params += worker_task_params(worker)
        elif worker:
            query += " AND 1=0"

        for worker_row in workers:
            worker_name = worker_row["username"]
            worker_condition = worker_task_condition()
            worker_params = worker_task_params(worker_name)
            load_params = [company_id] + worker_params
            date_filter = ""

            if month:
                date_filter = " AND task_date LIKE ?"
                load_params.append(f"{month}%")

            total = c.execute(f"""
            SELECT COUNT(*) FROM tasks
            WHERE archived=0 AND company_id=? AND {worker_condition}{date_filter}
            """, load_params).fetchone()[0]

            new = c.execute(f"""
            SELECT COUNT(*) FROM tasks
            WHERE archived=0 AND company_id=? AND {worker_condition}
              AND status='Новая'{date_filter}
            """, load_params).fetchone()[0]

            active = c.execute(f"""
            SELECT COUNT(*) FROM tasks
            WHERE archived=0 AND company_id=? AND {worker_condition}
              AND status='В работе'{date_filter}
            """, load_params).fetchone()[0]

            completed = c.execute(f"""
            SELECT COUNT(*) FROM tasks
            WHERE archived=0 AND company_id=? AND {worker_condition}
              AND status='Завершено'{date_filter}
            """, load_params).fetchone()[0]

            worker_loads.append({
                "username": worker_name,
                "total": total,
                "new": new,
                "active": active,
                "completed": completed
            })

        worker_name_set = set(worker_names)
        busy_counts = {worker_name: 0 for worker_name in worker_names}
        availability_rows = c.execute("""
        SELECT worker, workers
        FROM tasks
        WHERE archived=0
          AND company_id=?
          AND task_date LIKE ?
          AND status NOT IN ('Завершено', 'Отменено')
        """, (company_id, f"{availability_date}%")).fetchall()

        for availability_task in availability_rows:
            for worker_name in get_task_worker_names(availability_task):
                if worker_name in worker_name_set:
                    busy_counts[worker_name] += 1

        for worker_name in worker_names:
            active_count = busy_counts.get(worker_name, 0)
            worker_availability.append({
                "username": worker_name,
                "active_count": active_count,
                "is_free": active_count == 0,
                "is_recommended": False
            })

        recommended_count = min(
            [item["active_count"] for item in worker_availability],
            default=None
        )

        for item in worker_availability:
            item["is_recommended"] = recommended_count is not None and item["active_count"] == recommended_count

        availability_summary = {
            "total": len(worker_availability),
            "free": sum(1 for item in worker_availability if item["is_free"]),
            "busy": sum(1 for item in worker_availability if not item["is_free"])
        }

        if selected_availability == "free":
            worker_availability = [item for item in worker_availability if item["is_free"]]
        elif selected_availability == "busy":
            worker_availability = [item for item in worker_availability if not item["is_free"]]
    else:
        worker = ""
        query += f" AND {worker_task_condition()}"
        params += worker_task_params(username)

    if status in ("Новая", "В работе", "Завершено", "Отменено"):
        query += " AND status=?"
        params.append(status)

    current_calendar_day = datetime.strptime(availability_date, "%Y-%m-%d").date()

    def calendar_day_url(day):
        day_params = {"date": day.strftime("%Y-%m-%d")}

        if worker:
            day_params["worker"] = worker

        if status in ("Новая", "В работе", "Завершено", "Отменено"):
            day_params["status"] = status

        if selected_availability:
            day_params["availability"] = selected_availability

        return f"/calendar?{urlencode(day_params)}"

    previous_day_url = calendar_day_url(current_calendar_day - timedelta(days=1))
    today_day_url = calendar_day_url(datetime.now().date())
    next_day_url = calendar_day_url(current_calendar_day + timedelta(days=1))

    query += " ORDER BY task_date ASC, id DESC"

    tasks = c.execute(query, params).fetchall()

    conn.close()

    calendar_days = []

    for task in tasks:
        task_date = str(task["task_date"] or "").strip()
        day_label = task_date[:10] if task_date else "Без даты"

        if not calendar_days or calendar_days[-1]["date"] != day_label:
            calendar_days.append({
                "date": day_label,
                "status_counts": {
                    "Новая": 0,
                    "В работе": 0,
                    "Завершено": 0,
                    "Отменено": 0
                },
                "tasks": []
            })

        task_status = task["status"] or ""

        if task_status in calendar_days[-1]["status_counts"]:
            calendar_days[-1]["status_counts"][task_status] += 1

        calendar_days[-1]["tasks"].append({
            "task": task,
            "workers": format_task_workers(task)
        })

    return templates.TemplateResponse(
        request=request,
        name="calendar.html",
        context={
            "tasks": tasks,
            "calendar_days": calendar_days,
            "workers": workers,
            "worker_loads": worker_loads,
            "worker_availability": worker_availability,
            "availability_summary": availability_summary,
            "selected_worker": worker,
            "selected_month": month,
            "selected_status": status,
            "selected_availability": selected_availability,
            "selected_date": selected_date,
            "availability_date": availability_date,
            "previous_day_url": previous_day_url,
            "today_day_url": today_day_url,
            "next_day_url": next_day_url,
            "username": username,
            "role": role
        }
    )


@app.get("/recurring", response_class=HTMLResponse)
async def recurring_jobs_page(request: Request):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role not in ("boss", "manager"):
        return RedirectResponse("/", status_code=302)

    company_id = get_user_company_id(username)

    conn = connect()
    c = conn.cursor()

    jobs = c.execute("""
    SELECT recurring_jobs.*, clients.name AS client_name
    FROM recurring_jobs
    LEFT JOIN clients ON clients.id=recurring_jobs.client_id
    WHERE recurring_jobs.company_id=?
    ORDER BY recurring_jobs.next_date ASC, recurring_jobs.id DESC
    """, (company_id,)).fetchall()

    clients = c.execute("""
    SELECT *
    FROM clients
    WHERE company_id=?
    ORDER BY name
    """, (company_id,)).fetchall()

    workers = c.execute("""
    SELECT username
    FROM users
    WHERE role='worker' AND company_id=?
    ORDER BY username
    """, (company_id,)).fetchall()

    conn.close()

    return templates.TemplateResponse(
        request,
        "recurring.html",
        {
            "request": request,
            "username": username,
            "role": role,
            "jobs": jobs,
            "clients": clients,
            "workers": workers
        }
    )


@app.post("/recurring")
async def create_recurring_job(request: Request):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role not in ("boss", "manager"):
        return RedirectResponse("/", status_code=302)

    company_id = get_user_company_id(username)
    form = await request.form()

    client_id = form.get("client_id") or None
    title = (form.get("title") or "").strip()
    description = (form.get("description") or "").strip()
    interval_type = (form.get("interval_type") or "monthly").strip()
    next_date = (form.get("next_date") or "").strip()
    selected_workers = form.getlist("workers")
    priority = (form.get("priority") or "Обычный").strip()
    price = (form.get("price") or "0").strip()

    if not title or not next_date:
        return RedirectResponse("/recurring?error=empty", status_code=302)

    if interval_type not in ("weekly", "monthly", "quarterly", "yearly"):
        interval_type = "monthly"

    conn = connect()
    c = conn.cursor()

    if client_id:
        client = c.execute("""
        SELECT id
        FROM clients
        WHERE id=? AND company_id=?
        """, (client_id, company_id)).fetchone()

        if not client:
            client_id = None

    valid_workers = []

    for selected_worker in selected_workers:
        selected_worker = (selected_worker or "").strip()

        if not selected_worker:
            continue

        worker_user = c.execute("""
        SELECT username
        FROM users
        WHERE username=? AND role='worker' AND company_id=?
        """, (selected_worker, company_id)).fetchone()

        if worker_user and worker_user["username"] not in valid_workers:
            valid_workers.append(worker_user["username"])

    worker = valid_workers[0] if valid_workers else ""
    workers_text = ",".join(valid_workers)

    c.execute("""
    INSERT INTO recurring_jobs (
        company_id,
        client_id,
        title,
        description,
        interval_type,
        next_date,
        worker,
        workers,
        priority,
        price,
        active,
        created_at
    )
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        company_id,
        client_id,
        title,
        description,
        interval_type,
        next_date,
        worker,
        workers_text,
        priority,
        price,
        1,
        datetime.now().strftime("%Y-%m-%d %H:%M")
    ))

    conn.commit()
    conn.close()

    return RedirectResponse("/recurring?created=1", status_code=302)


@app.post("/recurring/{job_id}/generate")
async def generate_recurring_task(request: Request, job_id: int):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role not in ("boss", "manager"):
        return RedirectResponse("/", status_code=302)

    company_id = get_user_company_id(username)

    conn = connect()
    c = conn.cursor()

    job = c.execute("""
    SELECT *
    FROM recurring_jobs
    WHERE id=? AND company_id=? AND active=1
    """, (job_id, company_id)).fetchone()

    if not job:
        conn.close()
        return RedirectResponse("/recurring", status_code=302)

    client = None

    if job["client_id"]:
        client = c.execute("""
        SELECT *
        FROM clients
        WHERE id=? AND company_id=?
        """, (job["client_id"], company_id)).fetchone()

    client_name = client["name"] if client else job["title"]
    phone = client["phone"] if client else ""
    address = client["address"] if client else ""
    next_date = get_next_recurring_date(job["next_date"], job["interval_type"])

    c.execute("""
    INSERT INTO tasks (
        company_id,
        client_id,
        client,
        phone,
        address,
        description,
        task_date,
        worker,
        workers,
        priority,
        price,
        photo,
        status,
        report,
        after_photo,
        created_at,
        deadline_at
    )
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        company_id,
        job["client_id"],
        client_name,
        phone,
        address,
        job["description"],
        job["next_date"],
        job["worker"],
        job["workers"],
        job["priority"],
        job["price"],
        "",
        "Новая",
        "",
        "",
        datetime.now().strftime("%Y-%m-%d %H:%M"),
        ""
    ))

    task_id = c.lastrowid

    c.execute("""
    UPDATE recurring_jobs
    SET next_date=?
    WHERE id=? AND company_id=?
    """, (next_date, job_id, company_id))

    conn.commit()
    conn.close()

    log_task_activity(
        task_id,
        username,
        role,
        "Создана из регулярной работы",
        f"Шаблон: {job['title']}"
    )

    return RedirectResponse(f"/task/{task_id}", status_code=302)


@app.post("/recurring/{job_id}/toggle")
async def toggle_recurring_job(request: Request, job_id: int):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role not in ("boss", "manager"):
        return RedirectResponse("/", status_code=302)

    company_id = get_user_company_id(username)

    conn = connect()
    c = conn.cursor()

    job = c.execute("""
    SELECT *
    FROM recurring_jobs
    WHERE id=? AND company_id=?
    """, (job_id, company_id)).fetchone()

    if not job:
        conn.close()
        return RedirectResponse("/recurring", status_code=302)

    new_active = 0 if job["active"] else 1

    c.execute("""
    UPDATE recurring_jobs
    SET active=?
    WHERE id=? AND company_id=?
    """, (new_active, job_id, company_id))

    conn.commit()
    conn.close()

    return RedirectResponse("/recurring", status_code=302)


@app.post("/recurring/{job_id}/date")
async def update_recurring_job_date(request: Request, job_id: int):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role not in ("boss", "manager"):
        return RedirectResponse("/", status_code=302)

    form = await request.form()
    next_date = (form.get("next_date") or "").strip()

    if not next_date:
        return RedirectResponse("/recurring?error=empty", status_code=302)

    company_id = get_user_company_id(username)

    conn = connect()
    c = conn.cursor()

    job = c.execute("""
    SELECT id
    FROM recurring_jobs
    WHERE id=? AND company_id=?
    """, (job_id, company_id)).fetchone()

    if not job:
        conn.close()
        return RedirectResponse("/recurring", status_code=302)

    c.execute("""
    UPDATE recurring_jobs
    SET next_date=?
    WHERE id=? AND company_id=?
    """, (next_date, job_id, company_id))

    conn.commit()
    conn.close()

    return RedirectResponse("/recurring?updated=1", status_code=302)


@app.get("/finance/export")
async def finance_export(request: Request, month: str = ""):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role != "boss":
        return RedirectResponse("/", status_code=302)

    if not month:
        month = datetime.now().strftime("%Y-%m")

    conn = connect()
    c = conn.cursor()

    if role == "superadmin":
        return RedirectResponse("/platform", status_code=302)

    company_id = get_user_company_id(username)

    tasks = c.execute("""
    SELECT *
    FROM tasks
    WHERE archived=0 AND company_id=? AND task_date LIKE ?
    ORDER BY task_date DESC
    """, (company_id, f"{month}%")).fetchall()

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

    if role == "superadmin":
        return RedirectResponse("/platform", status_code=302)

    if role not in ("boss", "manager"):
        return RedirectResponse("/", status_code=302)

    company_id = get_user_company_id(username)

    if not month:
        month = datetime.now().strftime("%Y-%m")

    conn = connect()
    c = conn.cursor()

    tasks = c.execute("""
    SELECT *
    FROM tasks
    WHERE archived=0 AND company_id=? AND task_date LIKE ?
    ORDER BY task_date DESC
    """, (company_id, f"{month}%")).fetchall()

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

    company_id = get_user_company_id(username)

    conn = connect()
    c = conn.cursor()

    workers = c.execute("""
    SELECT username FROM users
    WHERE role='worker' AND company_id=?
    ORDER BY username
    """, (company_id,)).fetchall()

    report_rows = []

    total_completed = 0
    total_active = 0
    total_new = 0
    total_cancelled = 0
    total_revenue = 0

    for w in workers:
        worker_name = w[0]
        worker_condition = worker_task_condition()
        worker_params = worker_task_params(worker_name)

        completed = c.execute(f"""
        SELECT COUNT(*) FROM tasks
        WHERE archived=0 AND company_id=? AND {worker_condition}
          AND status='Завершено' AND task_date LIKE ?
        """, [company_id] + worker_params + [f"{month}%"]).fetchone()[0]

        active = c.execute(f"""
        SELECT COUNT(*) FROM tasks
        WHERE archived=0 AND company_id=? AND {worker_condition}
          AND status='В работе' AND task_date LIKE ?
        """, [company_id] + worker_params + [f"{month}%"]).fetchone()[0]

        new = c.execute(f"""
        SELECT COUNT(*) FROM tasks
        WHERE archived=0 AND company_id=? AND {worker_condition}
          AND status='Новая' AND task_date LIKE ?
        """, [company_id] + worker_params + [f"{month}%"]).fetchone()[0]

        cancelled = c.execute(f"""
        SELECT COUNT(*) FROM tasks
        WHERE archived=0 AND company_id=? AND {worker_condition}
          AND status='Отменено' AND task_date LIKE ?
        """, [company_id] + worker_params + [f"{month}%"]).fetchone()[0]

        revenue = c.execute(f"""
        SELECT SUM(price) FROM tasks
        WHERE archived=0 AND company_id=? AND {worker_condition}
          AND status='Завершено' AND task_date LIKE ?
        """, [company_id] + worker_params + [f"{month}%"]).fetchone()[0]

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
    WHERE company_id=? AND task_date LIKE ?
    ORDER BY task_date ASC, id DESC
    """, (company_id, f"{month}%")).fetchall()

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

    company_id = get_user_company_id(username)
    settings = get_company_settings(company_id)

    return templates.TemplateResponse(
        request,
        "calls.html",
        {
            "request": request,
            "username": username,
            "role": role,
            "settings": settings
        }
    )


@app.get("/integrations/1c", response_class=HTMLResponse)
async def integration_1c_page(request: Request):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role not in ("boss", "superadmin"):
        return RedirectResponse("/", status_code=302)

    company_id = get_user_company_id(username)
    settings = get_company_settings(company_id)

    return templates.TemplateResponse(
        request,
        "integration_1c.html",
        {
            "request": request,
            "username": username,
            "role": role,
            "settings": settings
        }
    )


@app.get("/billing", response_class=HTMLResponse)
async def billing_page(request: Request):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role not in ("boss", "superadmin"):
        return RedirectResponse("/", status_code=302)

    company_id = get_user_company_id(username)
    settings = get_company_settings(company_id)
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

    if role not in ("boss", "superadmin"):
        return RedirectResponse("/", status_code=302)

    company_id = get_user_company_id(username)
    settings = get_company_settings(company_id)

    return templates.TemplateResponse(
        request,
        "settings.html",
        {
            "request": request,
            "username": username,
            "role": role,
            "settings": settings
        }
    )


@app.post("/settings")
async def update_settings(request: Request):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role not in ("boss", "superadmin"):
        return RedirectResponse("/", status_code=302)

    form = await request.form()

    company_name = (form.get("company_name") or "").strip()
    phone = (form.get("phone") or "").strip()
    email = (form.get("email") or "").strip()
    telegram_chat_id = (form.get("telegram_chat_id") or "").strip()
    address = (form.get("address") or "").strip()
    tax_number = (form.get("tax_number") or "").strip()
    bank_details = (form.get("bank_details") or "").strip()
    plan = (form.get("plan") or "basic").strip()
    industry = (form.get("industry") or "field_service").strip()
    task_label = (form.get("task_label") or "Заявка").strip()
    worker_label = (form.get("worker_label") or "Исполнитель").strip()
    client_label = (form.get("client_label") or "Клиент").strip()
    service_label = (form.get("service_label") or "Услуга").strip()

    allowed_plans = ["basic", "team", "business", "business_1c", "enterprise_1c"]
    allowed_industries = [
        "field_service",
        "beauty",
        "auto_service",
        "logistics",
        "cleaning",
        "repair",
        "custom"
    ]

    if plan not in allowed_plans:
        plan = "basic"

    if industry not in allowed_industries:
        industry = "field_service"

    one_c_enabled = 1 if plan in ("business_1c", "enterprise_1c") else 0
    calls_enabled = 1 if plan in ("business", "business_1c", "enterprise_1c") else 0
    ai_calls_enabled = 1 if plan == "enterprise_1c" else 0
    company_id = get_user_company_id(username)

    conn = connect()
    c = conn.cursor()

    c.execute("""
    INSERT OR IGNORE INTO company_settings (
        company_id, company_name, phone, email, address, tax_number, bank_details, plan,
        industry, task_label, worker_label, client_label, service_label,
        one_c_enabled, calls_enabled, ai_calls_enabled, updated_at
    )
    VALUES (?, '', '', '', '', '', '', 'basic', 'field_service',
            'Заявка', 'Исполнитель', 'Клиент', 'Услуга', 0, 0, 0, '')
    """, (company_id,))

    c.execute("""
    UPDATE company_settings
    SET company_name=?, phone=?, email=?, address=?, tax_number=?, bank_details=?,
        plan=?, industry=?, task_label=?, worker_label=?, client_label=?, service_label=?,
        one_c_enabled=?, calls_enabled=?, ai_calls_enabled=?, updated_at=?
    WHERE company_id=?
    """, (
        company_name,
        phone,
        email,
        address,
        tax_number,
        bank_details,
        plan,
        industry,
        task_label,
        worker_label,
        client_label,
        service_label,
        one_c_enabled,
        calls_enabled,
        ai_calls_enabled,
        datetime.now().strftime("%Y-%m-%d %H:%M"),
        company_id
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


@app.get("/custom-fields", response_class=HTMLResponse)
async def custom_fields_page(request: Request):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role not in ("boss", "manager"):
        return RedirectResponse("/", status_code=302)

    company_id = get_user_company_id(username)

    conn = connect()
    c = conn.cursor()

    fields = c.execute("""
    SELECT *
    FROM custom_fields
    WHERE company_id=?
    ORDER BY entity_type, sort_order, id
    """, (company_id,)).fetchall()

    settings = get_company_settings(company_id)

    conn.close()

    return templates.TemplateResponse(
        request,
        "custom_fields.html",
        {
            "request": request,
            "username": username,
            "role": role,
            "fields": fields,
            "settings": settings
        }
    )


@app.post("/custom-fields")
async def create_custom_field(request: Request):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role not in ("boss", "manager"):
        return RedirectResponse("/", status_code=302)

    form = await request.form()
    entity_type = (form.get("entity_type") or "task").strip()
    label = (form.get("label") or "").strip()
    group_name = (form.get("group_name") or "").strip()
    field_type = (form.get("field_type") or "text").strip()
    options = (form.get("options") or "").strip()
    is_required = 1 if form.get("is_required") else 0
    sort_order_raw = (form.get("sort_order") or "").strip()

    if entity_type not in ("task", "client"):
        entity_type = "task"

    if field_type not in ("text", "number", "date", "select"):
        field_type = "text"

    if not label:
        return RedirectResponse("/custom-fields?error=empty", status_code=302)

    if field_type == "select":
        options = "\n".join(
            option.strip()
            for option in options.splitlines()
            if option.strip()
        )

        if not options:
            return RedirectResponse("/custom-fields?error=options", status_code=302)
    else:
        options = ""

    company_id = get_user_company_id(username)

    conn = connect()
    c = conn.cursor()

    sort_order = c.execute("""
    SELECT COUNT(*)
    FROM custom_fields
    WHERE company_id=? AND entity_type=?
    """, (company_id, entity_type)).fetchone()[0]

    try:
        sort_order_value = int(sort_order_raw) if sort_order_raw else sort_order + 1
    except ValueError:
        sort_order_value = sort_order + 1

    c.execute("""
    INSERT INTO custom_fields (
        company_id,
        entity_type,
        label,
        group_name,
        field_type,
        options,
        is_required,
        active,
        sort_order,
        created_at
    )
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        company_id,
        entity_type,
        label,
        group_name,
        field_type,
        options,
        is_required,
        1,
        sort_order_value,
        datetime.now().strftime("%Y-%m-%d %H:%M")
    ))

    conn.commit()
    conn.close()

    return RedirectResponse("/custom-fields?created=1", status_code=302)


@app.post("/custom-fields/{field_id}/order")
async def update_custom_field_order(request: Request, field_id: int):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role not in ("boss", "manager"):
        return RedirectResponse("/", status_code=302)

    form = await request.form()
    sort_order_raw = (form.get("sort_order") or "0").strip()

    try:
        sort_order = int(sort_order_raw)
    except ValueError:
        sort_order = 0

    company_id = get_user_company_id(username)

    conn = connect()
    c = conn.cursor()

    c.execute("""
    UPDATE custom_fields
    SET sort_order=?
    WHERE id=? AND company_id=?
    """, (sort_order, field_id, company_id))

    conn.commit()
    conn.close()

    return RedirectResponse("/custom-fields?ordered=1", status_code=302)


@app.post("/custom-fields/{field_id}/toggle")
async def toggle_custom_field(request: Request, field_id: int):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role not in ("boss", "manager"):
        return RedirectResponse("/", status_code=302)

    company_id = get_user_company_id(username)

    conn = connect()
    c = conn.cursor()

    field = c.execute("""
    SELECT *
    FROM custom_fields
    WHERE id=? AND company_id=?
    """, (field_id, company_id)).fetchone()

    if not field:
        conn.close()
        return RedirectResponse("/custom-fields", status_code=302)

    new_active = 0 if field["active"] else 1

    c.execute("""
    UPDATE custom_fields
    SET active=?
    WHERE id=? AND company_id=?
    """, (new_active, field_id, company_id))

    conn.commit()
    conn.close()

    return RedirectResponse("/custom-fields", status_code=302)


@app.get("/catalog", response_class=HTMLResponse)
async def catalog_page(request: Request):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role == "superadmin":
        return RedirectResponse("/platform", status_code=302)

    if role not in ("boss", "manager"):
        return RedirectResponse("/", status_code=302)

    conn = connect()
    c = conn.cursor()

    if role == "superadmin":
        return RedirectResponse("/platform", status_code=302)

    company_id = get_user_company_id(username)

    items = c.execute("""
    SELECT *
    FROM catalog_items
    WHERE company_id=?
    ORDER BY active DESC, item_type, name
    """, (company_id,)).fetchall()

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

    company_id = get_user_company_id(username)

    conn = connect()
    c = conn.cursor()

    c.execute("""
    INSERT INTO catalog_items (
        company_id,
        item_type,
        name,
        unit,
        price,
        cost,
        active,
        created_at
    )
    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        company_id,
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

    company_id = get_user_company_id(username)

    conn = connect()
    c = conn.cursor()

    item = c.execute("""
    SELECT *
    FROM catalog_items
    WHERE id=? AND company_id=?
    """, (item_id, company_id)).fetchone()

    if not item:
        conn.close()
        return RedirectResponse("/catalog", status_code=302)

    new_active = 0 if item["active"] else 1

    c.execute("""
    UPDATE catalog_items
    SET active=?
    WHERE id=? AND company_id=?
    """, (new_active, item_id, company_id))

    conn.commit()
    conn.close()

    return RedirectResponse("/catalog", status_code=302)


@app.get("/clients", response_class=HTMLResponse)
async def clients_page(request: Request):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role == "superadmin":
        return RedirectResponse("/platform", status_code=302)

    if role not in ("boss", "manager"):
        return RedirectResponse("/", status_code=302)

    conn = connect()
    c = conn.cursor()

    if role == "superadmin":
        return RedirectResponse("/platform", status_code=302)

    company_id = get_user_company_id(username)

    clients = c.execute("""
    SELECT *
    FROM clients
    WHERE company_id=?
    ORDER BY id DESC
    """, (company_id,)).fetchall()

    custom_fields = c.execute("""
    SELECT *
    FROM custom_fields
    WHERE company_id=?
      AND entity_type='client'
      AND active=1
    ORDER BY sort_order, id
    """, (company_id,)).fetchall()

    conn.close()

    return templates.TemplateResponse(
        request,
        "clients.html",
        {
            "request": request,
            "username": username,
            "role": role,
            "clients": clients,
            "custom_fields": custom_fields
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

    company_id = get_user_company_id(username)

    conn = connect()
    c = conn.cursor()

    client = c.execute("""
    SELECT *
    FROM clients
    WHERE id=? AND company_id=?
    """, (client_id, company_id)).fetchone()

    if not client:
        conn.close()
        return RedirectResponse("/clients", status_code=302)

    tasks = c.execute("""
    SELECT *
    FROM tasks
    WHERE client_id=? AND company_id=?
    ORDER BY id DESC
    """, (client_id, company_id)).fetchall()

    today = datetime.now().strftime("%Y-%m-%d")
    client_total_tasks = len(tasks)
    client_active_tasks = 0
    client_completed_tasks = 0
    client_overdue_tasks = 0
    client_revenue = 0

    for task in tasks:
        task_status = task["status"] or ""
        is_archived = "archived" in task.keys() and task["archived"] == 1

        if not is_archived and task_status in ("Новая", "В работе"):
            client_active_tasks += 1

        if task_status == "Завершено":
            client_completed_tasks += 1

            try:
                client_revenue += float(str(task["price"] or 0).replace(",", "."))
            except Exception:
                pass

        task_date = str(task["task_date"] or "")[:10]

        if (
            not is_archived
            and task_date
            and task_date < today
            and task_status not in ("Завершено", "Отменено")
        ):
            client_overdue_tasks += 1

    client_notes = c.execute("""
    SELECT *
    FROM client_notes
    WHERE client_id=? AND company_id=?
    ORDER BY id DESC
    """, (client_id, company_id)).fetchall()

    client_timeline = c.execute("""
    SELECT
        task_activity.*,
        tasks.id AS task_id,
        tasks.status AS task_status
    FROM task_activity
    JOIN tasks ON tasks.id=task_activity.task_id
    WHERE tasks.client_id=?
      AND tasks.company_id=?
    ORDER BY task_activity.id DESC
    LIMIT 20
    """, (client_id, company_id)).fetchall()

    client_custom_fields = c.execute("""
    SELECT custom_fields.id, custom_fields.label, custom_fields.field_type, custom_fields.options, custom_field_values.value
    FROM custom_fields
    LEFT JOIN custom_field_values
      ON custom_field_values.field_id=custom_fields.id
      AND custom_field_values.company_id=custom_fields.company_id
      AND custom_field_values.entity_type='client'
      AND custom_field_values.entity_id=?
    WHERE custom_fields.company_id=?
      AND custom_fields.entity_type='client'
      AND custom_fields.active=1
    ORDER BY custom_fields.sort_order, custom_fields.id
    """, (client_id, company_id)).fetchall()

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
            "client_notes": client_notes,
            "client_total_tasks": client_total_tasks,
            "client_active_tasks": client_active_tasks,
            "client_completed_tasks": client_completed_tasks,
            "client_overdue_tasks": client_overdue_tasks,
            "client_revenue": client_revenue,
            "client_timeline": client_timeline,
            "client_custom_fields": client_custom_fields
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

    company_id = get_user_company_id(username)

    form = await request.form()
    note = (form.get("note") or "").strip()

    if not note:
        return RedirectResponse(f"/clients/{client_id}?note_error=empty", status_code=302)

    conn = connect()
    c = conn.cursor()

    client = c.execute("""
    SELECT *
    FROM clients
    WHERE id=? AND company_id=?
    """, (client_id, company_id)).fetchone()

    if not client:
        conn.close()
        return RedirectResponse("/clients", status_code=302)

    c.execute("""
    INSERT INTO client_notes (
        company_id,
        client_id,
        username,
        role,
        note,
        created_at
    )
    VALUES (?, ?, ?, ?, ?, ?)
    """, (
        company_id,
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

    company_id = get_user_company_id(username)

    form = await request.form()

    name = (form.get("name") or "").strip()
    phone = (form.get("phone") or "").strip()
    email = (form.get("email") or "").strip()
    telegram_chat_id = (form.get("telegram_chat_id") or "").strip()
    address = (form.get("address") or "").strip()
    notes = (form.get("notes") or "").strip()

    if not name:
        return RedirectResponse(f"/clients/{client_id}?error=empty", status_code=302)

    conn = connect()
    c = conn.cursor()

    client = c.execute("""
    SELECT *
    FROM clients
    WHERE id=? AND company_id=?
    """, (client_id, company_id)).fetchone()

    if not client:
        conn.close()
        return RedirectResponse("/clients", status_code=302)

    custom_fields = c.execute("""
    SELECT *
    FROM custom_fields
    WHERE company_id=?
      AND entity_type='client'
      AND active=1
    ORDER BY sort_order, id
    """, (company_id,)).fetchall()

    for custom_field in custom_fields:
        field_name = f"custom_field_{custom_field['id']}"
        custom_value = (form.get(field_name) or "").strip()

        if custom_field["is_required"] and not custom_value:
            conn.close()
            return RedirectResponse(f"/clients/{client_id}?error=custom_required", status_code=302)

    c.execute("""
    UPDATE clients
    SET name=?, phone=?, email=?, address=?, notes=?
    WHERE id=? AND company_id=?
    """, (
        name,
        phone,
        email,
        address,
        notes,
        client_id,
        company_id
    ))

    for custom_field in custom_fields:
        field_name = f"custom_field_{custom_field['id']}"
        custom_value = (form.get(field_name) or "").strip()
        existing_value = c.execute("""
        SELECT *
        FROM custom_field_values
        WHERE company_id=?
          AND field_id=?
          AND entity_type='client'
          AND entity_id=?
        """, (company_id, custom_field["id"], client_id)).fetchone()

        if custom_value:
            if existing_value:
                c.execute("""
                UPDATE custom_field_values
                SET value=?
                WHERE id=?
                """, (custom_value, existing_value["id"]))
            else:
                c.execute("""
                INSERT INTO custom_field_values (
                    company_id,
                    field_id,
                    entity_type,
                    entity_id,
                    value,
                    created_at
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """, (
                    company_id,
                    custom_field["id"],
                    "client",
                    client_id,
                    custom_value,
                    datetime.now().strftime("%Y-%m-%d %H:%M")
                ))
        elif existing_value and not custom_field["is_required"]:
            c.execute("""
            DELETE FROM custom_field_values
            WHERE id=?
            """, (existing_value["id"],))

    linked_tasks = c.execute("""
    SELECT id
    FROM tasks
    WHERE client_id=? AND company_id=?
    """, (client_id, company_id)).fetchall()

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
    telegram_chat_id = (form.get("telegram_chat_id") or "").strip()
    address = (form.get("address") or "").strip()
    notes = (form.get("notes") or "").strip()

    if not name:
        return RedirectResponse("/clients?error=empty", status_code=302)

    company_id = get_user_company_id(username)

    conn = connect()
    c = conn.cursor()

    custom_fields = c.execute("""
    SELECT *
    FROM custom_fields
    WHERE company_id=?
      AND entity_type='client'
      AND active=1
    ORDER BY sort_order, id
    """, (company_id,)).fetchall()

    for custom_field in custom_fields:
        field_name = f"custom_field_{custom_field['id']}"
        custom_value = (form.get(field_name) or "").strip()

        if custom_field["is_required"] and not custom_value:
            conn.close()
            return RedirectResponse("/clients?error=custom_required", status_code=302)

    c.execute("""
    INSERT INTO clients (
        company_id,
        name,
        phone,
        email,
        address,
        notes,
        created_at
    )
    VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        company_id,
        name,
        phone,
        email,
        address,
        notes,
        datetime.now().strftime("%Y-%m-%d %H:%M")
    ))

    conn.commit()
    client_id = c.lastrowid

    for custom_field in custom_fields:
        field_name = f"custom_field_{custom_field['id']}"
        custom_value = (form.get(field_name) or "").strip()

        if not custom_value:
            continue

        c.execute("""
        INSERT INTO custom_field_values (
            company_id,
            field_id,
            entity_type,
            entity_id,
            value,
            created_at
        )
        VALUES (?, ?, ?, ?, ?, ?)
        """, (
            company_id,
            custom_field["id"],
            "client",
            client_id,
            custom_value,
            datetime.now().strftime("%Y-%m-%d %H:%M")
        ))

    if custom_fields:
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

    company_id = get_user_company_id(username)

    conn = connect()
    c = conn.cursor()

    tasks = c.execute("""
    SELECT *
    FROM tasks
    WHERE archived=1 AND company_id=?
    ORDER BY id DESC
    """, (company_id,)).fetchall()

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


@app.get("/more", response_class=HTMLResponse)
async def more_page(request: Request):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    return templates.TemplateResponse(
        request,
        "more.html",
        {
            "request": request,
            "username": username,
            "role": role
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

    if role == "superadmin":
        return RedirectResponse("/platform", status_code=302)

    if role not in ("boss", "manager"):
        return RedirectResponse("/", status_code=302)

    conn = connect()
    c = conn.cursor()

    company_id = get_user_company_id(username)

    workers = c.execute("""
    SELECT * FROM users
    WHERE role IN ('manager', 'worker') AND company_id=?
    ORDER BY role, username
    """, (company_id,)).fetchall()

    conn.close()

    return templates.TemplateResponse(
        request=request,
        name="workers.html",
        context={
            "workers": workers,
            "username": username,
            "role": role
        }
    )



@app.get("/workers/{worker_id}", response_class=HTMLResponse)
async def worker_detail(request: Request, worker_id: int):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role not in ("boss", "manager"):
        return RedirectResponse("/", status_code=302)

    company_id = get_user_company_id(username)

    conn = connect()
    c = conn.cursor()

    worker = c.execute("""
    SELECT *
    FROM users
    WHERE id=? AND company_id=?
    """, (worker_id, company_id)).fetchone()

    if not worker:
        conn.close()
        return RedirectResponse("/workers", status_code=302)

    worker_condition = worker_task_condition()
    worker_params = worker_task_params(worker["username"])

    total_tasks = c.execute(f"""
    SELECT COUNT(*)
    FROM tasks
    WHERE company_id=? AND {worker_condition}
    """, [company_id] + worker_params).fetchone()[0]

    done_tasks = c.execute(f"""
    SELECT COUNT(*)
    FROM tasks
    WHERE company_id=? AND {worker_condition} AND status='Завершено'
    """, [company_id] + worker_params).fetchone()[0]

    income = c.execute(f"""
    SELECT SUM(price)
    FROM tasks
    WHERE company_id=? AND {worker_condition} AND status='Завершено'
    """, [company_id] + worker_params).fetchone()[0] or 0

    conn.close()

    return templates.TemplateResponse(
        request=request,
        name="worker_detail.html",
        context={
            "request": request,
            "username": username,
            "role": role,
            "worker": worker,
            "total_tasks": total_tasks,
            "done_tasks": done_tasks,
            "income": income
        }
    )



@app.post("/workers")
async def create_worker(request: Request):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role != "boss":
        return RedirectResponse("/", status_code=302)

    company_id = get_user_company_id(username)

    form = await request.form()

    worker_username = (form.get("username") or "").strip()
    worker_password = (form.get("password") or "").strip()
    worker_role = (form.get("role") or "worker").strip()

    full_name = (form.get("full_name") or "").strip()
    position = (form.get("position") or "").strip()
    phone = (form.get("phone") or "").strip()
    email = (form.get("email") or "").strip()
    telegram_chat_id = (form.get("telegram_chat_id") or "").strip()

    conn = connect()
    c = conn.cursor()

    existing = c.execute("""
    SELECT *
    FROM users
    WHERE username=?
    """, (worker_username,)).fetchone()

    if existing:
        conn.close()
        return RedirectResponse("/workers?error=exists", status_code=302)

    c.execute("""
    INSERT INTO users (
        username,
        password,
        role,
        company_id,
        full_name,
        position,
        phone,
        email,
        telegram_chat_id,
        last_seen
    )
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        worker_username,
        hash_password(worker_password),
        worker_role,
        company_id,
        full_name,
        position,
        phone,
        email,
        telegram_chat_id,
        datetime.now().strftime("%Y-%m-%d %H:%M")
    ))

    conn.commit()
    conn.close()

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

    current_company_id = get_user_company_id(username)

    if user["username"] == username or user["role"] == "boss":
        conn.close()
        return RedirectResponse("/workers?error=cannot_delete_boss", status_code=302)

    if user["company_id"] != current_company_id:
        conn.close()
        return RedirectResponse("/workers?error=wrong_company", status_code=302)

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

    if role != "superadmin":
        return RedirectResponse("/", status_code=302)

    conn = connect()
    c = conn.cursor()

    c.execute("DELETE FROM login_attempts")

    conn.commit()
    conn.close()

    return RedirectResponse("/debug?login_attempts_cleared=1", status_code=302)


@app.get("/admin/notes", response_class=HTMLResponse)
async def admin_notes_page(request: Request):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role != "superadmin":
        return RedirectResponse("/", status_code=302)

    return templates.TemplateResponse(
        request,
        "admin_notes.html",
        {
            "request": request,
            "username": username,
            "role": role
        }
    )


@app.get("/admin/roadmap", response_class=HTMLResponse)
async def admin_roadmap_page(request: Request):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role != "superadmin":
        return RedirectResponse("/", status_code=302)

    return templates.TemplateResponse(
        request,
        "admin_roadmap.html",
        {
            "request": request,
            "username": username,
            "role": role
        }
    )


@app.get("/admin/checklist", response_class=HTMLResponse)
async def admin_checklist_page(request: Request):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role != "superadmin":
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

    if role not in ("boss", "superadmin"):
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


@app.get("/system", response_class=HTMLResponse)
async def system_page(request: Request):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role not in ("boss", "superadmin"):
        return RedirectResponse("/", status_code=302)

    db_path = DATA_DIR / "crm.db"
    uploads_path = UPLOAD_DIR

    db_exists = db_path.exists()
    db_size = db_path.stat().st_size if db_exists else 0
    uploads_exists = uploads_path.exists()
    uploads_files = len([f for f in uploads_path.rglob("*") if f.is_file()]) if uploads_exists else 0

    return templates.TemplateResponse(
        request,
        "system.html",
        {
            "request": request,
            "username": username,
            "role": role,
            "db_exists": db_exists,
            "db_size": db_size,
            "uploads_exists": uploads_exists,
            "uploads_files": uploads_files,
            "app_version": APP_VERSION
        }
    )


@app.get("/debug", response_class=HTMLResponse)
async def debug_page(request: Request):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role not in ("boss", "superadmin"):
        return RedirectResponse("/", status_code=302)

    conn = connect()
    c = conn.cursor()

    users_count = c.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    tasks_count = c.execute("SELECT COUNT(*) FROM tasks").fetchone()[0]
    active_tasks_count = c.execute("SELECT COUNT(*) FROM tasks WHERE archived=0").fetchone()[0]
    archived_tasks_count = c.execute("SELECT COUNT(*) FROM tasks WHERE archived=1").fetchone()[0]
    clients_count = c.execute("SELECT COUNT(*) FROM clients").fetchone()[0]
    catalog_count = c.execute("SELECT COUNT(*) FROM catalog_items").fetchone()[0]

    company_id = get_user_company_id(username)
    settings = get_company_settings(company_id)

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
    response.delete_cookie("user")

    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=sign_session_value(username),
        httponly=True,
        secure=COOKIE_SECURE,
        samesite="lax",
        max_age=60 * 60 * 24 * 30,
        path="/"
    )

    return response


@app.get("/logout")
async def logout():

    response = RedirectResponse("/login", status_code=302)
    response.delete_cookie("user")
    response.delete_cookie(SESSION_COOKIE_NAME)

    return response


@app.get("/create-task", response_class=HTMLResponse)
async def create_task_page(request: Request, task_date: str = "", worker: str = "", return_to: str = ""):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    update_last_seen(username)
    role = get_role(username)

    if role == "superadmin":
        return RedirectResponse("/platform", status_code=302)

    if role not in ("boss", "manager"):
        return RedirectResponse("/", status_code=302)

    company_id = get_user_company_id(username)
    selected_task_date = str(task_date or "").strip()

    try:
        if selected_task_date:
            datetime.strptime(selected_task_date, "%Y-%m-%d")
    except Exception:
        selected_task_date = ""

    conn = connect()
    c = conn.cursor()

    workers = c.execute("""
    SELECT username FROM users
    WHERE role='worker' AND company_id=?
    ORDER BY username
    """, (company_id,)).fetchall()
    worker_names = [row["username"] for row in workers]
    selected_workers = []
    selected_worker = str(worker or "").strip()
    selected_return_to = "calendar" if return_to == "calendar" else ""
    selected_worker_active_count = 0
    selected_worker_active_tasks = []
    recommended_worker = None

    if selected_worker in worker_names:
        selected_workers.append(selected_worker)

        if selected_task_date:
            selected_worker_active_tasks = c.execute(f"""
            SELECT id, client, status, task_date
            FROM tasks
            WHERE archived=0
              AND company_id=?
              AND task_date LIKE ?
              AND status NOT IN ('Завершено', 'Отменено')
              AND {worker_task_condition()}
            ORDER BY task_date ASC, id DESC
            """, [company_id, f"{selected_task_date}%", *worker_task_params(selected_worker)]).fetchall()
            selected_worker_active_count = len(selected_worker_active_tasks)

            if selected_worker_active_count > 0:
                daily_counts = {worker_name: 0 for worker_name in worker_names}
                daily_rows = c.execute("""
                SELECT worker, workers
                FROM tasks
                WHERE archived=0
                  AND company_id=?
                  AND task_date LIKE ?
                  AND status NOT IN ('Завершено', 'Отменено')
                """, (company_id, f"{selected_task_date}%")).fetchall()

                for daily_task in daily_rows:
                    for worker_name in get_task_worker_names(daily_task):
                        if worker_name in daily_counts:
                            daily_counts[worker_name] += 1

                alternatives = [
                    {
                        "username": worker_name,
                        "active_count": active_count
                    }
                    for worker_name, active_count in daily_counts.items()
                    if worker_name != selected_worker
                ]

                alternatives.sort(key=lambda item: (item["active_count"], item["username"]))
                recommended_worker = alternatives[0] if alternatives else None

                if recommended_worker:
                    switch_params = {
                        "task_date": selected_task_date,
                        "worker": recommended_worker["username"]
                    }

                    if selected_return_to:
                        switch_params["return_to"] = selected_return_to

                    recommended_worker["switch_url"] = f"/create-task?{urlencode(switch_params)}"

    clients = c.execute("""
    SELECT *
    FROM clients
    WHERE company_id=?
    ORDER BY name
    """, (company_id,)).fetchall()

    custom_fields = c.execute("""
    SELECT *
    FROM custom_fields
    WHERE company_id=?
      AND entity_type='task'
      AND active=1
    ORDER BY sort_order, id
    """, (company_id,)).fetchall()

    conn.close()

    return templates.TemplateResponse(
        request=request,
        name="create_task.html",
        context={
            "username": username,
            "workers": workers,
            "clients": clients,
            "custom_fields": custom_fields,
            "selected_task_date": selected_task_date,
            "selected_workers": selected_workers,
            "selected_return_to": selected_return_to,
            "selected_worker_active_count": selected_worker_active_count,
            "selected_worker_active_tasks": selected_worker_active_tasks,
            "recommended_worker": recommended_worker
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
    description = form.get("description")
    task_date = form.get("task_date")
    deadline_at = (form.get("deadline_at") or "").strip()
    selected_workers = form.getlist("workers")
    return_to = (form.get("return_to") or "").strip()
    priority = form.get("priority")
    price = form.get("price")
    company_id = get_user_company_id(username)

    conn = connect()
    c = conn.cursor()

    custom_fields = c.execute("""
    SELECT *
    FROM custom_fields
    WHERE company_id=?
      AND entity_type='task'
      AND active=1
    ORDER BY sort_order, id
    """, (company_id,)).fetchall()

    for custom_field in custom_fields:
        field_name = f"custom_field_{custom_field['id']}"
        custom_value = (form.get(field_name) or "").strip()

        if custom_field["is_required"] and not custom_value:
            conn.close()
            error_params = {"error": "custom_required"}
            selected_task_date = str(task_date or "")[:10]

            try:
                if selected_task_date:
                    datetime.strptime(selected_task_date, "%Y-%m-%d")
                    error_params["task_date"] = selected_task_date
            except Exception:
                pass

            selected_worker = next(
                (worker_name.strip() for worker_name in selected_workers if worker_name.strip()),
                ""
            )

            if selected_worker:
                error_params["worker"] = selected_worker

            if return_to == "calendar":
                error_params["return_to"] = "calendar"

            return RedirectResponse(f"/create-task?{urlencode(error_params)}", status_code=302)

    if client_id:
        existing_client = c.execute("""
        SELECT *
        FROM clients
        WHERE id=? AND company_id=?
        """, (client_id, company_id)).fetchone()

        if existing_client:
            client = existing_client["name"]
            phone = existing_client["phone"]
            address = existing_client["address"]

    valid_workers = []
    worker_chat_ids = []

    for selected_worker in selected_workers:
        selected_worker = (selected_worker or "").strip()

        if not selected_worker:
            continue

        worker_user = c.execute("""
        SELECT username, telegram_chat_id
        FROM users
        WHERE username=? AND role='worker' AND company_id=?
        """, (selected_worker, company_id)).fetchone()

        if worker_user and worker_user["username"] not in valid_workers:
            valid_workers.append(worker_user["username"])

            if worker_user["telegram_chat_id"]:
                worker_chat_ids.append(worker_user["telegram_chat_id"])

    worker = valid_workers[0] if valid_workers else ""
    workers_text = ",".join(valid_workers)

    c.execute("""
    INSERT INTO tasks (
        company_id,
        client_id,
        client,
        phone,
        address,
        description,
        task_date,
        worker,
        workers,
        priority,
        price,
        photo,
        status,
        report,
        after_photo,
        created_at
    )
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        company_id,
        client_id,
        client,
        phone,
        address,
        description,
        task_date,
        worker,
        workers_text,
        priority,
        price,
        "",
        "Новая",
        "",
        "",
        datetime.now().strftime("%Y-%m-%d %H:%M")
    ))

    conn.commit()
    task_id = c.lastrowid

    filename = save_upload_file(photo, task_id, "before")

    if filename:
        c.execute("""
        UPDATE tasks SET photo=? WHERE id=?
        """, (filename, task_id))
        conn.commit()

    for custom_field in custom_fields:
        field_name = f"custom_field_{custom_field['id']}"
        custom_value = (form.get(field_name) or "").strip()

        if not custom_value:
            continue

        c.execute("""
        INSERT INTO custom_field_values (
            company_id,
            field_id,
            entity_type,
            entity_id,
            value,
            created_at
        )
        VALUES (?, ?, ?, ?, ?, ?)
        """, (
            company_id,
            custom_field["id"],
            "task",
            task_id,
            custom_value,
            datetime.now().strftime("%Y-%m-%d %H:%M")
        ))

    if custom_fields:
        conn.commit()

    conn.close()

    log_task_activity(
        task_id,
        username,
        role,
        "Создана заявка",
        f"Клиент: {client}. Исполнители: {format_task_workers({'worker': worker, 'workers': workers_text})}. Дата: {task_date}"
    )

    text = f"""
🚀 Новая заявка #{task_id}

👤 Клиент: {client}
📞 Телефон: {phone}
📍 Адрес: {address}
📅 Дата: {task_date}
👷 Исполнители: {format_task_workers({'worker': worker, 'workers': workers_text})}
🔥 Приоритет: {priority}
💰 Цена: {price}
"""

    try:
        send_message(text)

        for worker_chat_id in worker_chat_ids:
            send_message_to_chat(
                worker_chat_id,
                f"""
📋 Вам назначена новая заявка #{task_id}

👤 Клиент: {client}
📞 Телефон: {phone}
📍 Адрес: {address}
📅 Дата: {task_date}
🔥 Приоритет: {priority}
"""
            )

        if filename:
            send_photo(
                f"uploads/{filename}",
                f"Фото до работы к заявке #{task_id}"
            )
    except Exception as e:
        print("Telegram notification error:", e)

    if return_to == "calendar":
        calendar_date = str(task_date or "")[:10]

        try:
            datetime.strptime(calendar_date, "%Y-%m-%d")
        except Exception:
            calendar_date = datetime.now().strftime("%Y-%m-%d")

        calendar_url = f"/calendar?date={calendar_date}"

        if worker:
            calendar_url += f"&worker={worker}"

        return RedirectResponse(calendar_url, status_code=302)

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

    company_id = task["company_id"] if "company_id" in task.keys() else get_user_company_id(username)
    linked_client = None

    if "client_id" in task.keys() and task["client_id"]:
        linked_client = c.execute("""
        SELECT *
        FROM clients
        WHERE id=? AND company_id=?
        """, (task["client_id"], company_id)).fetchone()

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
    WHERE active=1 AND company_id=?
    ORDER BY item_type, name
    """, (company_id,)).fetchall()

    estimate_total = sum(item["total"] for item in task_items)
    estimate_profit = sum(item["profit"] for item in task_items)

    sla_status = "none"

    if task["deadline_at"]:
        now_value = datetime.now().strftime("%Y-%m-%dT%H:%M")

        if task["status"] != "Завершено" and task["deadline_at"] < now_value:
            sla_status = "overdue"
        elif task["status"] != "Завершено":
            sla_status = "active"
        else:
            sla_status = "done"
    task_workers = get_task_worker_names(task)
    task_custom_fields = c.execute("""
    SELECT custom_fields.id, custom_fields.label, custom_fields.group_name, custom_fields.field_type, custom_field_values.value
    FROM custom_fields
    LEFT JOIN custom_field_values
      ON custom_field_values.field_id=custom_fields.id
      AND custom_field_values.company_id=custom_fields.company_id
      AND custom_field_values.entity_type='task'
      AND custom_field_values.entity_id=?
    WHERE custom_fields.company_id=?
      AND custom_fields.entity_type='task'
      AND custom_fields.active=1
    ORDER BY custom_fields.sort_order, custom_fields.id
    """, (task_id, company_id)).fetchall()

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
            "activities": activity,
            "linked_client": linked_client,
            "task_items": task_items,
            "catalog_items": catalog_items,
            "estimate_total": estimate_total,
            "estimate_profit": estimate_profit,
            "task_workers": task_workers,
            "task_custom_fields": task_custom_fields,
            "sla_status": sla_status
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

    if not can_access_task(username, role, task):
        conn.close()
        return RedirectResponse("/", status_code=302)

    company_id = task["company_id"] if "company_id" in task.keys() else get_user_company_id(username)

    item = c.execute("""
    SELECT *
    FROM catalog_items
    WHERE id=? AND company_id=? AND active=1
    """, (catalog_item_id, company_id)).fetchone()

    if not item:
        conn.close()
        return RedirectResponse(f"/task/{task_id}", status_code=302)

    total = float(item["price"]) * qty
    profit = (float(item["price"]) - float(item["cost"])) * qty

    c.execute("""
    INSERT INTO task_items (
        company_id,
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
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        company_id,
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

    if not can_access_task(username, role, task):
        conn.close()
        return RedirectResponse("/", status_code=302)

    company_id = task["company_id"] if "company_id" in task.keys() else get_user_company_id(username)

    item = c.execute("""
    SELECT *
    FROM task_items
    WHERE id=? AND task_id=? AND company_id=?
    """, (item_id, task_id, company_id)).fetchone()

    if not item:
        conn.close()
        return RedirectResponse(f"/task/{task_id}", status_code=302)

    c.execute("""
    DELETE FROM task_items
    WHERE id=? AND task_id=? AND company_id=?
    """, (item_id, task_id, company_id))

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
            comment_text = f"""
💬 Новый комментарий в заявке #{task_id}

Клиент: {task['client']}
Адрес: {task['address']}
Автор: {username} ({get_role_title(role)})

Комментарий:
{message}
"""

            send_message(comment_text)

            for worker_chat_id in get_task_worker_chat_ids(c, task):
                send_message_to_chat(worker_chat_id, comment_text)

        except Exception as e:
            print("Telegram comment notification error:", e)

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

    if not can_access_task(username, role, task):
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




@app.post("/task/{task_id}/complete")
async def complete_task(request: Request, task_id: int):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role != "worker":
        return RedirectResponse("/", status_code=302)

    form = await request.form()
    report = (form.get("report") or "").strip()
    after_photo = form.get("after_photo")

    if not report:
        return RedirectResponse("/my-tasks?error=report_required", status_code=302)

    company_id = get_user_company_id(username)

    conn = connect()
    c = conn.cursor()

    task = c.execute("""
    SELECT *
    FROM tasks
    WHERE id=? AND company_id=?
    """, (task_id, company_id)).fetchone()

    if not task or not task_has_worker(username, task):
        conn.close()
        return RedirectResponse("/my-tasks", status_code=302)

    filename = save_upload_file(after_photo, task_id, "after")

    c.execute("""
    UPDATE tasks
    SET status='Завершено',
        report=?,
        after_photo=?
    WHERE id=?
    """, (
        report,
        filename or task["after_photo"],
        task_id
    ))

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
        "Завершил заявку",
        report,
        datetime.now().strftime("%Y-%m-%d %H:%M")
    ))

    owners = c.execute("""
    SELECT username
    FROM users
    WHERE company_id=? AND role IN ('boss', 'manager')
    """, (company_id,)).fetchall()

    for owner in owners:
        c.execute("""
        INSERT INTO notifications (
            company_id,
            username,
            title,
            message,
            link,
            created_at
        )
        VALUES (?, ?, ?, ?, ?, ?)
        """, (
            company_id,
            owner["username"],
            "✅ Заявка завершена",
            f"Исполнитель {username} завершил заявку #{task_id}",
            f"/task/{task_id}",
            datetime.now().strftime("%Y-%m-%d %H:%M")
        ))

    conn.commit()
    conn.close()

    try:
        send_message(
            f"""
✅ Заявка завершена исполнителем

Заявка: #{task_id}
Клиент: {task["client"]}
Адрес: {task["address"]}
Исполнитель: {username}

Отчёт:
{report}
"""
        )
    except Exception:
        pass

    return RedirectResponse("/my-tasks", status_code=302)


@app.post("/task/{task_id}/start")
async def start_task(request: Request, task_id: int):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role != "worker":
        return RedirectResponse("/", status_code=302)

    company_id = get_user_company_id(username)

    conn = connect()
    c = conn.cursor()

    task = c.execute("""
    SELECT *
    FROM tasks
    WHERE id=? AND company_id=?
    """, (task_id, company_id)).fetchone()

    if not task or not task_has_worker(username, task):
        conn.close()
        return RedirectResponse("/my-tasks", status_code=302)

    c.execute("""
    UPDATE tasks
    SET status='В работе'
    WHERE id=?
    """, (task_id,))

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
        "Взял в работу",
        "Исполнитель начал выполнение заявки",
        datetime.now().strftime("%Y-%m-%d %H:%M")
    ))

    conn.commit()
    conn.close()

    return RedirectResponse("/my-tasks", status_code=302)



@app.post("/task/{task_id}/edit")
async def edit_task_field(request: Request, task_id: int):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role not in ("boss", "manager"):
        return RedirectResponse("/", status_code=302)

    form = await request.form()
    field = (form.get("field") or "").strip()
    value = (form.get("value") or "").strip()

    allowed_fields = {
        "client": "client",
        "phone": "phone",
        "address": "address",
        "description": "description",
        "priority": "priority",
        "price": "price",
        "status": "status",
        "worker": "worker"
    }

    if field not in allowed_fields:
        return RedirectResponse(f"/task/{task_id}", status_code=302)

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

    if not can_access_task(username, role, task):
        conn.close()
        return RedirectResponse("/", status_code=302)

    column = allowed_fields[field]

    c.execute(f"""
    UPDATE tasks
    SET {column}=?
    WHERE id=?
    """, (value, task_id))

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
        "Изменено поле",
        f"{field}: {value}",
        datetime.now().strftime("%Y-%m-%d %H:%M")
    ))

    conn.commit()
    conn.close()

    return RedirectResponse(f"/task/{task_id}", status_code=302)


@app.post("/task/{task_id}/custom-field")
async def update_task_custom_field(request: Request, task_id: int):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role not in ("boss", "manager"):
        return RedirectResponse("/", status_code=302)

    form = await request.form()
    field_id_raw = (form.get("field_id") or "").strip()
    value = (form.get("value") or "").strip()

    try:
        field_id = int(field_id_raw)
    except ValueError:
        return RedirectResponse(f"/task/{task_id}", status_code=302)

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

    if not can_access_task(username, role, task):
        conn.close()
        return RedirectResponse("/", status_code=302)

    company_id = task["company_id"] if "company_id" in task.keys() else get_user_company_id(username)

    custom_field = c.execute("""
    SELECT *
    FROM custom_fields
    WHERE id=?
      AND company_id=?
      AND entity_type='task'
      AND active=1
    """, (field_id, company_id)).fetchone()

    if not custom_field:
        conn.close()
        return RedirectResponse(f"/task/{task_id}", status_code=302)

    if custom_field["is_required"] and not value:
        conn.close()
        return RedirectResponse(f"/task/{task_id}?error=custom_required", status_code=302)

    existing_value = c.execute("""
    SELECT *
    FROM custom_field_values
    WHERE company_id=?
      AND field_id=?
      AND entity_type='task'
      AND entity_id=?
    """, (company_id, field_id, task_id)).fetchone()

    if value:
        if existing_value:
            c.execute("""
            UPDATE custom_field_values
            SET value=?
            WHERE id=?
            """, (value, existing_value["id"]))
        else:
            c.execute("""
            INSERT INTO custom_field_values (
                company_id,
                field_id,
                entity_type,
                entity_id,
                value,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """, (
                company_id,
                field_id,
                "task",
                task_id,
                value,
                datetime.now().strftime("%Y-%m-%d %H:%M")
            ))
    elif existing_value and not custom_field["is_required"]:
        c.execute("""
        DELETE FROM custom_field_values
        WHERE id=?
        """, (existing_value["id"],))

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
        "Изменено доп. поле",
        f"{custom_field['label']}: {value}",
        datetime.now().strftime("%Y-%m-%d %H:%M")
    ))

    conn.commit()
    conn.close()

    return RedirectResponse(f"/task/{task_id}", status_code=302)


@app.post("/task/{task_id}/deadline")
async def update_task_deadline(request: Request, task_id: int):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role not in ("boss", "manager"):
        return RedirectResponse("/", status_code=302)

    company_id = get_user_company_id(username)

    form = await request.form()
    deadline_at = (form.get("deadline_at") or "").strip()

    conn = connect()
    c = conn.cursor()

    task = c.execute("""
    SELECT *
    FROM tasks
    WHERE id=? AND company_id=?
    """, (task_id, company_id)).fetchone()

    if not task:
        conn.close()
        return RedirectResponse("/", status_code=302)

    c.execute("""
    UPDATE tasks
    SET deadline_at=?
    WHERE id=? AND company_id=?
    """, (deadline_at, task_id, company_id))

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
        "Изменён deadline",
        deadline_at or "Deadline очищен",
        datetime.now().strftime("%Y-%m-%d %H:%M")
    ))

    owners = c.execute("""
    SELECT username
    FROM users
    WHERE company_id=?
      AND role IN ('boss', 'manager')
    """, (company_id,)).fetchall()

    for owner in owners:
        if owner["username"] != username:
            c.execute("""
            INSERT INTO notifications (
                company_id,
                username,
                title,
                message,
                link,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """, (
                company_id,
                owner["username"],
                "⏰ Изменён deadline",
                f"{username} изменил deadline заявки #{task_id}",
                f"/task/{task_id}",
                datetime.now().strftime("%Y-%m-%d %H:%M")
            ))

    conn.commit()
    conn.close()

    return RedirectResponse(f"/task/{task_id}", status_code=302)


@app.post("/task/{task_id}/date")
async def update_task_date(request: Request, task_id: int):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role not in ("boss", "manager"):
        return RedirectResponse("/", status_code=302)

    form = await request.form()
    new_date = (form.get("task_date") or "").strip()
    return_to = (form.get("return_to") or "").strip()

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

    if not can_access_task(username, role, task):
        conn.close()
        return RedirectResponse("/", status_code=302)

    old_date = task["task_date"]
    worker_chat_ids = get_task_worker_chat_ids(c, task)

    c.execute("""
    UPDATE tasks
    SET task_date=?
    WHERE id=?
    """, (new_date, task_id))

    conn.commit()
    conn.close()

    log_task_activity(
        task_id,
        username,
        role,
        "Дата заявки изменена",
        f"Было: {old_date or 'Без даты'}. Стало: {new_date or 'Без даты'}"
    )

    try:
        date_text = f"""
📅 Дата заявки изменена

Заявка: #{task_id}
Клиент: {task['client']}
Адрес: {task['address']}
Старая дата: {old_date or 'Без даты'}
Новая дата: {new_date}

Изменил: {username} ({get_role_title(role)})
"""

        send_message(date_text)

        for worker_chat_id in worker_chat_ids:
            send_message_to_chat(worker_chat_id, date_text)
    except Exception:
        pass

    if return_to.startswith("/calendar"):
        return RedirectResponse(return_to, status_code=302)

    return RedirectResponse(f"/task/{task_id}", status_code=302)


@app.post("/task/{task_id}/status")
async def update_task_status(request: Request, task_id: int):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    form = await request.form()
    new_status = (form.get("status") or "").strip()
    return_to = (form.get("return_to") or "").strip()

    allowed_statuses = ("Новая", "В работе", "Завершено", "Отменено")

    if new_status not in allowed_statuses:
        if return_to.startswith("/calendar"):
            return RedirectResponse(return_to, status_code=302)

        return RedirectResponse(f"/task/{task_id}", status_code=302)

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

    if return_to.startswith("/calendar"):
        return RedirectResponse(return_to, status_code=302)

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

    if not can_access_task(username, role, task):
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

    if not can_access_task(username, role, task):
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
async def delete_task(request: Request, task_id: int):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role not in ("boss", "manager"):
        return RedirectResponse("/", status_code=302)

    company_id = get_user_company_id(username)

    conn = connect()
    c = conn.cursor()

    task = c.execute("""
    SELECT *
    FROM tasks
    WHERE id=? AND company_id=?
    """, (task_id, company_id)).fetchone()

    if not task:
        conn.close()
        return RedirectResponse("/", status_code=302)

    c.execute("""
    UPDATE tasks
    SET archived=1
    WHERE id=? AND company_id=?
    """, (task_id, company_id))

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
        "Заявка отправлена в архив",
        "Заявка скрыта с активного списка",
        datetime.now().strftime("%Y-%m-%d %H:%M")
    ))

    conn.commit()
    conn.close()

    return RedirectResponse("/?archived=1", status_code=302)


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
    task_company_id = task["company_id"] if "company_id" in task.keys() else get_user_company_id(username)
    settings = get_company_settings(task_company_id)

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
            pdf.drawString(350, y, f"{item['price']} RUB")
            pdf.drawString(430, y, f"{item['total']} RUB")
            y -= 16

        y -= 12
        pdf.setFont(font_name, 13)
        pdf.drawString(350, y, "Итого:")
        pdf.drawString(430, y, f"{estimate_total} RUB")
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
    task_company_id = task["company_id"] if "company_id" in task.keys() else get_user_company_id(username)
    settings = get_company_settings(task_company_id)

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
        ("Стоимость", f"{task['price']} RUB"),
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
            pdf.drawString(350, y, f"{item['price']} RUB")
            pdf.drawString(430, y, f"{item['total']} RUB")
            y -= 16

        y -= 8
        pdf.setFont(font_name, 11)
        pdf.drawString(350, y, "Итого:")
        pdf.drawString(430, y, f"{estimate_total} RUB")
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
