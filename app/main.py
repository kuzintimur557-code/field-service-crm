from fastapi import FastAPI, Request, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.database import connect, init_db
from app.telegram_utils import send_message, send_photo

from datetime import datetime
from pathlib import Path
from uuid import uuid4
from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

import shutil
import os


app = FastAPI()

init_db()

os.makedirs("uploads", exist_ok=True)
os.makedirs("uploads/docs", exist_ok=True)

app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")
app.mount("/static", StaticFiles(directory="app/static"), name="static")

templates = Jinja2Templates(directory="app/templates")

UPLOAD_DIR = Path("uploads")
DOCS_DIR = UPLOAD_DIR / "docs"
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


def get_user(request: Request):
    return request.cookies.get("user")


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

    query = "SELECT * FROM tasks WHERE 1=1"
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
        total_tasks = c.execute("SELECT COUNT(*) FROM tasks").fetchone()[0]
        new_tasks = c.execute("SELECT COUNT(*) FROM tasks WHERE status='Новая'").fetchone()[0]
        working_tasks = c.execute("SELECT COUNT(*) FROM tasks WHERE status='В работе'").fetchone()[0]
        done_tasks = c.execute("SELECT COUNT(*) FROM tasks WHERE status='Завершено'").fetchone()[0]

        revenue = c.execute("""
        SELECT SUM(price) FROM tasks WHERE status='Завершено'
        """).fetchone()[0]
    else:
        total_tasks = c.execute("SELECT COUNT(*) FROM tasks WHERE worker=?", (username,)).fetchone()[0]
        new_tasks = c.execute("SELECT COUNT(*) FROM tasks WHERE worker=? AND status='Новая'", (username,)).fetchone()[0]
        working_tasks = c.execute("SELECT COUNT(*) FROM tasks WHERE worker=? AND status='В работе'", (username,)).fetchone()[0]
        done_tasks = c.execute("SELECT COUNT(*) FROM tasks WHERE worker=? AND status='Завершено'", (username,)).fetchone()[0]

        revenue = c.execute("""
        SELECT SUM(price) FROM tasks
        WHERE worker=? AND status='Завершено'
        """, (username,)).fetchone()[0]

    if revenue is None:
        revenue = 0

    workers = c.execute("""
    SELECT username, last_seen FROM users
    WHERE role='worker'
    ORDER BY username
    """).fetchall()

    worker_stats = []

    if role in ("boss", "manager"):
        for w in workers:
            worker_name = w["username"]

            completed = c.execute("""
            SELECT COUNT(*) FROM tasks
            WHERE worker=? AND status='Завершено'
            """, (worker_name,)).fetchone()[0]

            active = c.execute("""
            SELECT COUNT(*) FROM tasks
            WHERE worker=? AND status='В работе'
            """, (worker_name,)).fetchone()[0]

            worker_revenue = c.execute("""
            SELECT SUM(price) FROM tasks
            WHERE worker=? AND status='Завершено'
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
        WHERE worker=? AND status='Завершено' AND task_date LIKE ?
        """, (worker_name, f"{month}%")).fetchone()[0]

        active = c.execute("""
        SELECT COUNT(*) FROM tasks
        WHERE worker=? AND status='В работе' AND task_date LIKE ?
        """, (worker_name, f"{month}%")).fetchone()[0]

        new = c.execute("""
        SELECT COUNT(*) FROM tasks
        WHERE worker=? AND status='Новая' AND task_date LIKE ?
        """, (worker_name, f"{month}%")).fetchone()[0]

        cancelled = c.execute("""
        SELECT COUNT(*) FROM tasks
        WHERE worker=? AND status='Отменено' AND task_date LIKE ?
        """, (worker_name, f"{month}%")).fetchone()[0]

        revenue = c.execute("""
        SELECT SUM(price) FROM tasks
        WHERE worker=? AND status='Завершено' AND task_date LIKE ?
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
    WHERE role='worker'
    ORDER BY username
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

    if role not in ("boss", "manager"):
        return RedirectResponse("/", status_code=302)

    form = await request.form()

    worker_username = form.get("username")
    worker_password = form.get("password")

    conn = connect()
    c = conn.cursor()

    existing = c.execute("""
    SELECT * FROM users WHERE username=?
    """, (worker_username,)).fetchone()

    if not existing:
        c.execute("""
        INSERT INTO users (username, password, role, last_seen)
        VALUES (?, ?, ?, ?)
        """, (
            worker_username,
            worker_password,
            "worker",
            ""
        ))

    conn.commit()
    conn.close()

    return RedirectResponse("/workers", status_code=302)


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

    username = form.get("username")
    password = form.get("password")

    conn = connect()
    c = conn.cursor()

    user = c.execute("""
    SELECT * FROM users WHERE username=? AND password=?
    """, (
        username,
        password
    )).fetchone()

    conn.close()

    if not user:
        return RedirectResponse("/login", status_code=302)

    update_last_seen(username)

    response = RedirectResponse("/", status_code=302)
    response.set_cookie(key="user", value=username)

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

    conn.close()

    return templates.TemplateResponse(
        request=request,
        name="create_task.html",
        context={
            "username": username,
            "workers": workers
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

    client = form.get("client")
    phone = form.get("phone")
    address = form.get("address")
    description = form.get("description")
    task_date = form.get("task_date")
    worker = form.get("worker")
    priority = form.get("priority")
    price = form.get("price")

    conn = connect()
    c = conn.cursor()

    c.execute("""
    INSERT INTO tasks (
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
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
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

    conn.close()

    return templates.TemplateResponse(
        name="task_detail.html",
        context={
            "request": request,
            "task": task,
            "username": username,
            "role": role,
            "comments": comments,
            "activity": activity
        }
    )


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

    pdf_path = DOCS_DIR / f"task_{task_id}.pdf"
    font_name = register_pdf_font()

    pdf = canvas.Canvas(str(pdf_path), pagesize=A4)
    page_width, page_height = A4

    pdf.setFont(font_name, 20)
    pdf.drawString(40, page_height - 50, f"Акт выполненных работ №{task['id']}")

    pdf.setFont(font_name, 10)
    pdf.drawString(40, page_height - 72, f"Дата формирования: {datetime.now().strftime('%Y-%m-%d %H:%M')}")

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
