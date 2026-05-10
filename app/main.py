from fastapi import FastAPI, Request, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.database import connect, init_db
from app.telegram_utils import send_message

from datetime import datetime

import shutil
import os
import urllib.parse
import uuid

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

templates = Jinja2Templates(directory="app/templates")


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
def home(
    request: Request,
    search: str = "",
    status: str = "",
    worker: str = "",
    task_date: str = ""
):

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

    query = "SELECT * FROM tasks WHERE 1=1"

    params = []

    if role != "boss":

        query += " AND worker=?"

        params.append(username)

    if search:

        query += " AND client LIKE ?"

        params.append(f"%{search}%")

    if status:

        query += " AND status=?"

        params.append(status)

    if worker:

        query += " AND worker=?"

        params.append(worker)

    if task_date:

        query += " AND task_date=?"

        params.append(task_date)

    query += " ORDER BY id DESC"

    tasks = c.execute(query, params).fetchall()

    tasks_with_maps = []

    for task in tasks:

        encoded = urllib.parse.quote(task["address"])

        map_url = f"https://maps.google.com/?q={encoded}"

        tasks_with_maps.append({
            **dict(task),
            "map_url": map_url
        })

    workers = c.execute("""
    SELECT * FROM users
    WHERE role='worker'
    """).fetchall()

    revenue = c.execute("""
    SELECT SUM(price)
    FROM tasks
    WHERE status='Завершено'
    """).fetchone()[0]

    if revenue is None:
        revenue = 0

    total_tasks = c.execute("""
    SELECT COUNT(*) FROM tasks
    """).fetchone()[0]

    new_tasks = c.execute("""
    SELECT COUNT(*) FROM tasks
    WHERE status='Новая'
    """).fetchone()[0]

    working_tasks = c.execute("""
    SELECT COUNT(*) FROM tasks
    WHERE status='В работе'
    """).fetchone()[0]

    done_tasks = c.execute("""
    SELECT COUNT(*) FROM tasks
    WHERE status='Завершено'
    """).fetchone()[0]

    monthly_revenue = c.execute("""
    SELECT task_date, SUM(price)
    FROM tasks
    WHERE status='Завершено'
    GROUP BY task_date
    ORDER BY task_date ASC
    """).fetchall()

    worker_stats = []

    for w in workers:

        completed = c.execute("""
        SELECT COUNT(*)
        FROM tasks
        WHERE worker=?
        AND status='Завершено'
        """, (w["username"],)).fetchone()[0]

        active = c.execute("""
        SELECT COUNT(*)
        FROM tasks
        WHERE worker=?
        AND status='В работе'
        """, (w["username"],)).fetchone()[0]

        worker_revenue = c.execute("""
        SELECT SUM(price)
        FROM tasks
        WHERE worker=?
        AND status='Завершено'
        """, (w["username"],)).fetchone()[0]

        if worker_revenue is None:
            worker_revenue = 0

        worker_stats.append({
            "username": w["username"],
            "completed": completed,
            "active": active,
            "revenue": worker_revenue,
            "last_seen": w["last_seen"]
        })

    conn.close()

    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "tasks": tasks_with_maps,
            "workers": workers,
            "worker_stats": worker_stats,
            "username": username,
            "role": role,
            "revenue": revenue,
            "total_tasks": total_tasks,
            "new_tasks": new_tasks,
            "working_tasks": working_tasks,
            "done_tasks": done_tasks,
            "monthly_revenue": monthly_revenue,
            "search": search,
            "selected_status": status,
            "selected_worker": worker,
            "selected_date": task_date
        }
    )


@app.post("/create")
async def create_task(
    request: Request,
    photo: UploadFile = File(None)
):

    username = get_user(request)

    if get_role(username) != "boss":

        return RedirectResponse(
            "/",
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

    photo_path = ""

    if photo and photo.filename:

        ext = photo.filename.split(".")[-1]

        filename = f"task_{uuid.uuid4()}.{ext}"

        photo_path = f"uploads/{filename}"

        with open(photo_path, "wb") as buffer:

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
        photo_path,
        price
    ))

    conn.commit()

    conn.close()

    send_message(
        f"🚨 Новая заявка\n\n"
        f"👤 {client}\n"
        f"📍 {address}\n"
        f"👷 {worker}"
    )

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

    workers = c.execute("""
    SELECT * FROM users
    WHERE role='worker'
    """).fetchall()

    conn.close()

    encoded = urllib.parse.quote(task["address"])

    map_url = f"https://maps.google.com/?q={encoded}"

    return templates.TemplateResponse(
        request,
        "task.html",
        {
            "task": task,
            "workers": workers,
            "role": get_role(username),
            "map_url": map_url
        }
    )


@app.post("/task/{task_id}/update")
async def update_task(
    request: Request,
    task_id: int,
    photo: UploadFile = File(None)
):

    username = get_user(request)

    if not username:

        return RedirectResponse(
            "/login",
            status_code=302
        )

    form = await request.form()

    status = form.get("status")
    worker = form.get("worker")
    description = form.get("description")

    conn = connect()

    c = conn.cursor()

    task = c.execute("""
    SELECT * FROM tasks
    WHERE id=?
    """, (task_id,)).fetchone()

    photo_path = task["photo"]

    if photo and photo.filename:

        ext = photo.filename.split(".")[-1]

        filename = f"update_{uuid.uuid4()}.{ext}"

        photo_path = f"uploads/{filename}"

        with open(photo_path, "wb") as buffer:

            shutil.copyfileobj(
                photo.file,
                buffer
            )

    c.execute("""
    UPDATE tasks
    SET
        status=?,
        worker=?,
        description=?,
        photo=?
    WHERE id=?
    """, (
        status,
        worker,
        description,
        photo_path,
        task_id
    ))

    conn.commit()

    conn.close()

    send_message(
        f"🛠 Заявка обновлена\n\n"
        f"ID: {task_id}\n"
        f"Статус: {status}"
    )

    return RedirectResponse(
        f"/task/{task_id}",
        status_code=302
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

    role = get_role(username)

    if role != "boss":

        return RedirectResponse(
            "/",
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

        os.makedirs("uploads", exist_ok=True)

        filename = f"task_{photo.filename}"

        filepath = f"uploads/{filename}"

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

    try:

        send_message(
            f"""
🚀 Новая заявка

👤 Клиент: {client}

📞 Телефон: {phone}

📍 Адрес: {address}

👷 Монтажник: {worker}

💰 Цена: {price}
"""
        )

    except:
        pass

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

    if not task:

        return RedirectResponse(
            "/",
            status_code=302
        )

    encoded = urllib.parse.quote(
        task["address"]
    )

    map_url = f"https://maps.google.com/?q={encoded}"

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
    task_id: int
):

    username = get_user(request)

    if not username:

        return RedirectResponse(
            "/login",
            status_code=302
        )

    form = await request.form()

    status = form.get("status")

    conn = connect()

    c = conn.cursor()

    task = c.execute("""
    SELECT * FROM tasks
    WHERE id=?
    """, (task_id,)).fetchone()

    if not task:

        conn.close()

        return RedirectResponse(
            "/",
            status_code=302
        )

    c.execute("""
    UPDATE tasks
    SET status=?
    WHERE id=?
    """, (
        status,
        task_id
    ))

    conn.commit()

    conn.close()

    try:

        send_message(
            f"""
📦 Статус заявки обновлен

👤 Клиент: {task['client']}

👷 Монтажник: {task['worker']}

📌 Новый статус: {status}
"""
        )

    except:
        pass

    return RedirectResponse(
        f"/task/{task_id}",
        status_code=302
    )

