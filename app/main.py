from fastapi import FastAPI, Request, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.database import connect, init_db
from app.telegram_utils import send_message, send_photo

from datetime import datetime

import shutil
import os


app = FastAPI()

init_db()

os.makedirs("uploads", exist_ok=True)

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


@app.get("/", response_class=HTMLResponse)
async def home(request: Request):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    conn = connect()
    c = conn.cursor()

    c.execute("""
    SELECT * FROM tasks
    ORDER BY id DESC
    """)

    tasks = c.fetchall()

    conn.close()

    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "tasks": tasks,
            "username": username
        }
    )


@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):

    return templates.TemplateResponse(
        "login.html",
        {
            "request": request
        }
    )


@app.post("/login")
async def login(request: Request):

    form = await request.form()

    username = form.get("username")
    password = form.get("password")

    conn = connect()
    c = conn.cursor()

    c.execute("""
    SELECT * FROM users
    WHERE username=? AND password=?
    """, (
        username,
        password
    ))

    user = c.fetchone()

    conn.close()

    if not user:
        return RedirectResponse(
            "/login",
            status_code=302
        )

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
async def logout():

    response = RedirectResponse(
        "/login",
        status_code=302
    )

    response.delete_cookie("user")

    return response


@app.get("/create-task", response_class=HTMLResponse)
async def create_task_page(request: Request):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    return templates.TemplateResponse(
        "create_task.html",
        {
            "request": request,
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
        "new"
    ))

    conn.commit()

    task_id = c.lastrowid

    conn.close()

    text = f"""
Новая заявка #{task_id}

Клиент: {client}
Телефон: {phone}
Адрес: {address}

Описание:
{description}

Дата: {task_date}
Мастер: {worker}
Приоритет: {priority}
Цена: {price}
"""

    send_message(text)

    if filename:

        send_photo(
            f"uploads/{filename}",
            f"Фото к заявке #{task_id}"
        )

    return RedirectResponse(
        "/",
        status_code=302
    )


@app.get("/task/{task_id}", response_class=HTMLResponse)
async def task_detail(request: Request, task_id: int):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    conn = connect()
    c = conn.cursor()

    c.execute("""
    SELECT * FROM tasks
    WHERE id=?
    """, (task_id,))

    task = c.fetchone()

    conn.close()

    if not task:
        return HTMLResponse(
            "Task not found",
            status_code=404
        )

    return templates.TemplateResponse(
        "task_detail.html",
        {
            "request": request,
            "task": task,
            "username": username
        }
    )
