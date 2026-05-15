from fastapi import FastAPI, Request, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.database import connect, init_db
from app.telegram_utils import send_message, send_photo

from datetime import datetime
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


def get_user(request: Request):
    return request.cookies.get("user")


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

    conn = connect()
    c = conn.cursor()

    query = "SELECT * FROM tasks WHERE 1=1"
    params = []

    if status:
        query += " AND status=?"
        params.append(status)

    if worker:
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

    total_tasks = c.execute("SELECT COUNT(*) FROM tasks").fetchone()[0]

    new_tasks = c.execute("""
    SELECT COUNT(*) FROM tasks WHERE status='Новая'
    """).fetchone()[0]

    working_tasks = c.execute("""
    SELECT COUNT(*) FROM tasks WHERE status='В работе'
    """).fetchone()[0]

    done_tasks = c.execute("""
    SELECT COUNT(*) FROM tasks WHERE status='Завершено'
    """).fetchone()[0]

    revenue = c.execute("""
    SELECT SUM(price) FROM tasks WHERE status='Завершено'
    """).fetchone()[0]

    if revenue is None:
        revenue = 0

    workers = c.execute("""
    SELECT username FROM users WHERE role='worker' ORDER BY username
    """).fetchall()

    worker_stats = []

    for w in workers:
        worker_name = w[0]

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
            "revenue": worker_revenue
        })

    conn.close()

    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "tasks": tasks,
            "username": username,
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

    conn = connect()
    c = conn.cursor()

    tasks = c.execute("""
    SELECT *
    FROM tasks
    ORDER BY task_date ASC, id DESC
    """).fetchall()

    conn.close()

    return templates.TemplateResponse(
        request=request,
        name="calendar.html",
        context={
            "tasks": tasks,
            "username": username
        }
    )


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

    return templates.TemplateResponse(
        request=request,
        name="create_task.html",
        context={
            "username": username
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

    form = await request.form()

    client = form.get("client")
    phone = form.get("phone")
    address = form.get("address")
    description = form.get("description")
    task_date = form.get("task_date")
    worker = form.get("worker")
    priority = form.get("priority")
    price = form.get("price")

    filename = ""

    if photo and photo.filename:
        filename = f"{datetime.now().timestamp()}_{photo.filename}"
        file_path = f"uploads/{filename}"

        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(photo.file, buffer)

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
        status
    )
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        client,
        phone,
        address,
        description,
        task_date,
        worker,
        priority,
        price,
        filename,
        "Новая"
    ))

    conn.commit()
    task_id = c.lastrowid
    conn.close()

    text = f"""
🚀 Новая заявка #{task_id}

👤 Клиент: {client}
📞 Телефон: {phone}
📍 Адрес: {address}
📅 Дата: {task_date}
👷 Монтажник: {worker}
🔥 Приоритет: {priority}
💰 Цена: {price}
"""

    try:
        send_message(text)

        if filename:
            send_photo(
                f"uploads/{filename}",
                f"Фото к заявке #{task_id}"
            )
    except:
        pass

    return RedirectResponse("/", status_code=302)


@app.get("/task/{task_id}", response_class=HTMLResponse)
async def task_detail(request: Request, task_id: int):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    conn = connect()
    c = conn.cursor()

    task = c.execute("""
    SELECT * FROM tasks WHERE id=?
    """, (task_id,)).fetchone()

    conn.close()

    if not task:
        return HTMLResponse("Task not found", status_code=404)

    return templates.TemplateResponse(
        request=request,
        name="task_detail.html",
        context={
            "task": task,
            "username": username
        }
    )


@app.post("/task/{task_id}/status")
async def update_status(request: Request, task_id: int):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    form = await request.form()
    status = form.get("status")

    conn = connect()
    c = conn.cursor()

    task = c.execute("""
    SELECT * FROM tasks WHERE id=?
    """, (task_id,)).fetchone()

    if not task:
        conn.close()
        return RedirectResponse("/", status_code=302)

    c.execute("""
    UPDATE tasks SET status=? WHERE id=?
    """, (
        status,
        task_id
    ))

    conn.commit()
    conn.close()

    try:
        send_message(
            f"""
🔔 Статус заявки изменён

Заявка #{task_id}
Клиент: {task[1]}
Новый статус: {status}
"""
        )
    except:
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

    conn = connect()
    c = conn.cursor()

    task = c.execute("""
    SELECT * FROM tasks WHERE id=?
    """, (task_id,)).fetchone()

    conn.close()

    if not task:
        return HTMLResponse("Task not found", status_code=404)

    pdf_path = f"uploads/docs/task_{task_id}.pdf"

    pdf = canvas.Canvas(pdf_path)

    pdf.setFont("Helvetica-Bold", 20)
    pdf.drawString(50, 800, f"Service Report #{task[0]}")

    pdf.setFont("Helvetica", 12)

    y = 750

    lines = [
        f"Client: {task[1]}",
        f"Phone: {task[2]}",
        f"Address: {task[3]}",
        f"Description: {task[4]}",
        f"Date: {task[5]}",
        f"Worker: {task[6]}",
        f"Priority: {task[7]}",
        f"Price: ${task[8]}",
        f"Status: {task[10]}",
        "",
        "Signature: ______________________________"
    ]

    for line in lines:
        pdf.drawString(50, y, str(line))
        y -= 28

    pdf.save()

    return FileResponse(
        pdf_path,
        media_type="application/pdf",
        filename=f"task_{task_id}.pdf"
    )
