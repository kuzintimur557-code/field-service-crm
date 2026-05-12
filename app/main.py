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

    response = RedirectResponse(
        "/",
        status_code=302
    )

    response.set_cookie(
        key="user",
        value=username
    )

    return response


@app.get("/")
def home(request: Request):

    username = get_user(request)

    if not username:

        return RedirectResponse(
            "/login",
            status_code=302
        )

    conn = connect()

    c = conn.cursor()

    tasks = c.execute("""
    SELECT * FROM tasks
    ORDER BY id DESC
    """).fetchall()

    workers = c.execute("""
    SELECT * FROM users
    WHERE role='worker'
    """).fetchall()

    conn.close()

    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "tasks": tasks,
            "workers": workers,
            "username": username
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
    file_path = ""

    if photo and photo.filename:

        os.makedirs(
            "uploads",
            exist_ok=True
        )

        filename = (
            f"{datetime.now().timestamp()}_{photo.filename}"
        )

        file_path = (
            f"uploads/{filename}"
        )

        with open(file_path, "wb") as buffer:

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
        price
    )
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
        price
    ))

    conn.commit()

    conn.close()

    message = f'''
🔥 Новая заявка

👤 Клиент: {client}
📞 Телефон: {phone}
📍 Адрес: {address}
🛠 Монтажник: {worker}
📅 Дата: {task_date}
💰 Сумма: {price}
'''

    if filename:

        send_photo(
            file_path,
            message
        )

    else:

        send_message(message)

    return RedirectResponse(
        "/",
        status_code=302
    )
@app.get("/task/{task_id}", response_class=HTMLResponse)
async def task_page(request: Request, task_id: int):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    conn = connect()
    c = conn.cursor()

    c.execute("""
    SELECT *
    FROM tasks
    WHERE id=?
    """, (task_id,))

    task = c.fetchone()

    conn.close()

    if not task:
        return HTMLResponse("Заявка не найдена", status_code=404)

    return templates.TemplateResponse(
        "task.html",
        {
            "request": request,
            "task": task,
            "user": username
        }
    )
