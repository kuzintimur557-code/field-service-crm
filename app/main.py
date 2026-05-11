from fastapi import FastAPI, Request, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.database import connect, init_db
from app.telegram_utils import send_message

from datetime import datetime
from reportlab.pdfgen import canvas

import shutil
import os
import urllib.parse


app = FastAPI()

init_db()

app.mount(
    "/uploads",
    StaticFiles(directory="uploads"),
    name="uploads"
)

app.mount(
    "/static",
    StaticFiles(directory="app/static"),
    name="static"
)

templates = Jinja2Templates(
    directory="app/templates"
)


def get_user(request: Request):

    return request.cookies.get("user")


def update_last_seen(username):

    conn = connect()

    c = conn.cursor()

    c.execute("""
    UPDATE users
    SET last_seen=?
    WHERE username=?
    """, (
        str(datetime.now()),
        username
    ))

    conn.commit()

    conn.close()


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


@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request):

    return templates.TemplateResponse(
        request,
        "login.html",
        {}
    )


@app.post("/login")
async def login(request: Request):

    form = await request.form()

    username = form.get("username")
    password = form.get("password")

    conn = connect()

    c = conn.cursor()

    user = c.execute("""
    SELECT * FROM users
    WHERE username=? AND password=?
    """, (
        username,
        password
    )).fetchone()

    conn.close()

    if not user:

        return RedirectResponse(
            "/login",
            status_code=302
        )

    update_last_seen(username)

    response = RedirectResponse(
        "/",
        status_code=302
    )

    response.set_cookie(
        key="user",
        value=username
    )

    return response


@app.get("/logout")
def logout():

    response = RedirectResponse(
        "/login",
        status_code=302
    )

    response.delete_cookie("user")

    return response


@app.get("/", response_class=HTMLResponse)
def home(request: Request):

    username = get_user(request)

    if not username:

        return RedirectResponse(
            "/login",
            status_code=302
        )

    update_last_seen(username)

    role = get_role(username)

    conn = connect()

    c = conn.cursor()

    if role == "boss":

        tasks = c.execute("""
        SELECT * FROM tasks
        ORDER BY id DESC
        """).fetchall()

    else:

        tasks = c.execute("""
        SELECT * FROM tasks
        WHERE worker=?
        ORDER BY id DESC
        """, (username,)).fetchall()

    revenue = c.execute("""
    SELECT SUM(price)
    FROM tasks
    WHERE status='Завершено'
    """).fetchone()[0]

    if revenue is None:
        revenue = 0

    total_tasks = c.execute("""
    SELECT COUNT(*)
    FROM tasks
    """).fetchone()[0]

    new_tasks = c.execute("""
    SELECT COUNT(*)
    FROM tasks
    WHERE status='Новая'
    """).fetchone()[0]

    working_tasks = c.execute("""
    SELECT COUNT(*)
    FROM tasks
    WHERE status='В работе'
    """).fetchone()[0]

    done_tasks = c.execute("""
    SELECT COUNT(*)
    FROM tasks
    WHERE status='Завершено'
    """).fetchone()[0]

    conn.close()

    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "tasks": tasks,
            "username": username,
            "role": role,
            "revenue": revenue,
            "total_tasks": total_tasks,
            "new_tasks": new_tasks,
            "working_tasks": working_tasks,
            "done_tasks": done_tasks
        }
    )


@app.get("/create-task", response_class=HTMLResponse)
def create_task_page(request: Request):

    username = get_user(request)

    if not username:

        return RedirectResponse(
            "/login",
            status_code=302
        )

    role = get_role(username)

    if role != "boss":

        return RedirectResponse(
            "/",
            status_code=302
        )

    conn = connect()

    c = conn.cursor()

    workers = c.execute("""
    SELECT * FROM users
    WHERE role='worker'
    """).fetchall()

    conn.close()

    return templates.TemplateResponse(
        request,
        "create_task.html",
        {
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

        return RedirectResponse(
            "/login",
            status_code=302
        )

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

        os.makedirs(
            "uploads",
            exist_ok=True
        )

        filename = (
            f"task_{photo.filename}"
        )

        filepath = (
            f"uploads/{filename}"
        )

        with open(filepath, "wb") as buffer:

            shutil.copyfileobj(
                photo.file,
                buffer
            )

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
        status,
        priority,
        photo,
        price,
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
        "Новая",
        priority,
        filename,
        price,
        "",
        ""
    ))

    conn.commit()

    conn.close()

    return RedirectResponse(
        "/",
        status_code=302
    )


@app.get("/task/{task_id}", response_class=HTMLResponse)
def task_page(
    request: Request,
    task_id: int
):

    username = get_user(request)

    if not username:

        return RedirectResponse(
            "/login",
            status_code=302
        )

    conn = connect()

    c = conn.cursor()

    task = c.execute("""
    SELECT * FROM tasks
    WHERE id=?
    """, (task_id,)).fetchone()

    conn.close()

    encoded = urllib.parse.quote(
        task["address"]
    )

    map_url = (
        f"https://maps.google.com/?q={encoded}"
    )

    return templates.TemplateResponse(
        request,
        "task.html",
        {
            "task": task,
            "map_url": map_url
        }
    )


@app.post("/task/{task_id}")
async def update_task(
    request: Request,
    task_id: int,
    after_photo: UploadFile = File(None)
):

    username = get_user(request)

    if not username:

        return RedirectResponse(
            "/login",
            status_code=302
        )

    form = await request.form()

    status = form.get("status")
    report = form.get("report")

    conn = connect()

    c = conn.cursor()

    task = c.execute("""
    SELECT * FROM tasks
    WHERE id=?
    """, (task_id,)).fetchone()

    after_filename = task["after_photo"]

    if after_photo and after_photo.filename:

        os.makedirs(
            "uploads",
            exist_ok=True
        )

        after_filename = (
            f"after_{after_photo.filename}"
        )

        filepath = (
            f"uploads/{after_filename}"
        )

        with open(filepath, "wb") as buffer:

            shutil.copyfileobj(
                after_photo.file,
                buffer
            )

    c.execute("""
    UPDATE tasks
    SET
        status=?,
        report=?,
        after_photo=?
    WHERE id=?
    """, (
        status,
        report,
        after_filename,
        task_id
    ))

    conn.commit()

    conn.close()

    return RedirectResponse(
        f"/task/{task_id}",
        status_code=302
    )


@app.get("/task/{task_id}/pdf")
def generate_pdf(
    request: Request,
    task_id: int
):

    username = get_user(request)

    if not username:

        return RedirectResponse(
            "/login",
            status_code=302
        )

    conn = connect()

    c = conn.cursor()

    task = c.execute("""
    SELECT * FROM tasks
    WHERE id=?
    """, (task_id,)).fetchone()

    conn.close()

    if not task:

        return RedirectResponse(
            "/",
            status_code=302
        )

    os.makedirs(
        "uploads/docs",
        exist_ok=True
    )

    filename = (
        f"uploads/docs/task_{task_id}.pdf"
    )

    pdf = canvas.Canvas(filename)

    pdf.setFont(
        "Helvetica-Bold",
        22
    )

    pdf.drawString(
        50,
        800,
        "Field Service Report"
    )

    pdf.setFont(
        "Helvetica",
        14
    )

    y = 740

    lines = [
        f"Client: {task['client']}",
        f"Phone: {task['phone']}",
        f"Address: {task['address']}",
        f"Worker: {task['worker']}",
        f"Date: {task['task_date']}",
        f"Status: {task['status']}",
        f"Price: ${task['price']}",
        "",
        "Report:",
        task["report"] or ""
    ]

    for line in lines:

        pdf.drawString(
            50,
            y,
            str(line)
        )

        y -= 30

    pdf.save()

    return FileResponse(
        filename,
        media_type='application/pdf',
        filename=f"task_{task_id}.pdf"
    )
