"""Catalog, custom fields and recurring job routes."""

from datetime import datetime

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app.database import connect
from app.deps import get_role, get_user, get_user_company_id
from app.services.common import (
    build_dashboard_links,
    create_notification,
    get_company_settings,
    get_next_recurring_date,
    get_role_title,
    get_task_worker_names,
    log_task_activity,
    require_feature,
)
from app.templating import templates

router = APIRouter()


def _main_attr(name):
    from app import main

    return getattr(main, name)


def run_automation_event(*args, **kwargs):
    return _main_attr("run_automation_event")(*args, **kwargs)


def send_message(*args, **kwargs):
    return _main_attr("send_message")(*args, **kwargs)


def send_message_to_chat(*args, **kwargs):
    return _main_attr("send_message_to_chat")(*args, **kwargs)

@router.get("/recurring", response_class=HTMLResponse)
async def recurring_jobs_page(request: Request):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role not in ("boss", "manager"):
        return RedirectResponse("/", status_code=302)

    company_id = get_user_company_id(username)
    disabled_response = require_feature(company_id, "recurring")

    if disabled_response:
        return disabled_response

    settings = get_company_settings(company_id)
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
    WHERE role='worker'
      AND company_id=?
      AND COALESCE(is_active, 1)=1
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
            "workers": workers,
            "settings": settings,
        }
    )


@router.post("/recurring")
async def create_recurring_job(request: Request):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role not in ("boss", "manager"):
        return RedirectResponse("/", status_code=302)

    company_id = get_user_company_id(username)

    disabled_response = require_feature(company_id, "recurring")

    if disabled_response:
        return disabled_response


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
        WHERE username=?
          AND role='worker'
          AND company_id=?
          AND COALESCE(is_active, 1)=1
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

    job_id = c.lastrowid
    conn.commit()
    conn.close()

    run_automation_event(
        company_id,
        "recurring_job_created",
        "recurring_job",
        job_id,
        f"Шаблон регулярной работы создан: {title}",
        "/recurring",
    )

    return RedirectResponse("/recurring?created=1", status_code=302)


@router.post("/recurring/{job_id}/generate")
async def generate_recurring_task(request: Request, job_id: int):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role not in ("boss", "manager"):
        return RedirectResponse("/", status_code=302)

    company_id = get_user_company_id(username)
    disabled_response = require_feature(company_id, "recurring")

    if disabled_response:
        return disabled_response

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
    assigned_workers = get_task_worker_names(job)
    active_workers = []
    worker_chat_ids = {}

    for worker_name in assigned_workers:
        active_worker = c.execute("""
        SELECT username, telegram_chat_id
        FROM users
        WHERE company_id=?
          AND username=?
          AND role='worker'
          AND COALESCE(is_active, 1)=1
        """, (company_id, worker_name)).fetchone()

        if active_worker:
            active_workers.append(active_worker["username"])
            worker_chat_ids[active_worker["username"]] = str(
                active_worker["telegram_chat_id"] or ""
            ).strip()

    if assigned_workers and not active_workers:
        conn.close()
        return RedirectResponse(
            "/recurring?error=no_active_workers",
            status_code=302,
        )

    task_worker = active_workers[0] if active_workers else ""
    task_workers = ",".join(active_workers)

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
        task_worker,
        task_workers,
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
    notification_created_at = datetime.now().strftime("%Y-%m-%d %H:%M")
    notification_message = (
        f"Клиент: {client_name}. "
        f"Дата: {job['next_date'] or 'не указана'}. "
        f"Регулярная работа: {job['title']}"
    )

    for worker_name in active_workers:
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
            worker_name,
            f"Назначена регулярная заявка #{task_id}",
            notification_message,
            f"/task/{task_id}",
            notification_created_at,
        ))

    c.execute("""
    UPDATE recurring_jobs
    SET next_date=?,
        worker=?,
        workers=?
    WHERE id=? AND company_id=?
    """, (
        next_date,
        task_worker,
        task_workers,
        job_id,
        company_id,
    ))

    conn.commit()
    conn.close()

    log_task_activity(
        task_id,
        username,
        role,
        "Создана из регулярной работы",
        f"Шаблон: {job['title']}"
    )

    run_automation_event(
        company_id,
        "recurring_task_generated",
        "task",
        task_id,
        f"Создана регулярная заявка #{task_id}: {job['title']}",
        f"/task/{task_id}",
    )

    telegram_text = (
        f"Вам назначена регулярная заявка #{task_id}\n"
        f"Клиент: {client_name}\n"
        f"Дата: {job['next_date'] or 'не указана'}\n"
        f"Описание: {job['description'] or 'не указано'}"
    )

    for worker_name in active_workers:
        chat_id = worker_chat_ids.get(worker_name)

        if not chat_id:
            continue

        try:
            send_message_to_chat(chat_id, telegram_text)
        except Exception as error:
            print("Telegram recurring notification error:", error)

    return RedirectResponse(f"/task/{task_id}", status_code=302)


@router.post("/recurring/{job_id}/toggle")
async def toggle_recurring_job(request: Request, job_id: int):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role not in ("boss", "manager"):
        return RedirectResponse("/", status_code=302)

    company_id = get_user_company_id(username)
    disabled_response = require_feature(company_id, "recurring")

    if disabled_response:
        return disabled_response

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

    run_automation_event(
        company_id,
        "recurring_job_toggled",
        "recurring_job",
        job_id,
        (
            f"Шаблон регулярной работы "
            f"{'включён' if new_active else 'выключен'}: {job['title']}"
        ),
        "/recurring",
    )

    return RedirectResponse("/recurring", status_code=302)


@router.post("/recurring/{job_id}/date")
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

    disabled_response = require_feature(company_id, "recurring")

    if disabled_response:
        return disabled_response



    conn = connect()
    c = conn.cursor()

    job = c.execute("""
    SELECT id, title, next_date
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

    if str(job["next_date"] or "") != next_date:
        run_automation_event(
            company_id,
            "recurring_job_date_changed",
            "recurring_job",
            job_id,
            (
                f"Дата шаблона регулярной работы {job['title']}: "
                f"{job['next_date'] or 'не задана'} → {next_date}"
            ),
            "/recurring",
        )

    return RedirectResponse("/recurring?updated=1", status_code=302)

@router.get("/custom-fields", response_class=HTMLResponse)
async def custom_fields_page(request: Request):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role not in ("boss", "manager"):
        return RedirectResponse("/", status_code=302)

    company_id = get_user_company_id(username)
    disabled_response = require_feature(company_id, "custom_fields")

    if disabled_response:
        return disabled_response

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


@router.post("/custom-fields")
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

    disabled_response = require_feature(company_id, "custom_fields")

    if disabled_response:
        return disabled_response



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

    field_id = c.lastrowid
    conn.commit()
    conn.close()

    run_automation_event(
        company_id,
        "custom_field_created",
        "custom_field",
        field_id,
        f"Создано поле компании: {label}",
        "/custom-fields",
    )

    return RedirectResponse("/custom-fields?created=1", status_code=302)


@router.post("/custom-fields/{field_id}/order")
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

    disabled_response = require_feature(company_id, "custom_fields")

    if disabled_response:
        return disabled_response



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

    c.execute("""
    UPDATE custom_fields
    SET sort_order=?
    WHERE id=? AND company_id=?
    """, (sort_order, field_id, company_id))

    conn.commit()
    conn.close()

    run_automation_event(
        company_id,
        "custom_field_ordered",
        "custom_field",
        field_id,
        (
            f"Порядок поля компании изменён: "
            f"{field['label']} → {sort_order}"
        ),
        "/custom-fields",
    )

    return RedirectResponse("/custom-fields?ordered=1", status_code=302)


@router.post("/custom-fields/{field_id}/toggle")
async def toggle_custom_field(request: Request, field_id: int):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role not in ("boss", "manager"):
        return RedirectResponse("/", status_code=302)

    company_id = get_user_company_id(username)
    disabled_response = require_feature(company_id, "custom_fields")

    if disabled_response:
        return disabled_response

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

    run_automation_event(
        company_id,
        "custom_field_toggled",
        "custom_field",
        field_id,
        (
            f"Поле компании {'включено' if new_active else 'выключено'}: "
            f"{field['label']}"
        ),
        "/custom-fields",
    )

    return RedirectResponse("/custom-fields", status_code=302)

@router.get("/catalog", response_class=HTMLResponse)
async def catalog_page(request: Request):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role == "superadmin":
        return RedirectResponse("/platform", status_code=302)

    if role not in ("boss", "manager"):
        return RedirectResponse("/", status_code=302)

    company_id = get_user_company_id(username)
    disabled_response = require_feature(company_id, "catalog")

    if disabled_response:
        return disabled_response

    conn = connect()
    c = conn.cursor()

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


@router.post("/catalog")
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

    disabled_response = require_feature(company_id, "catalog")

    if disabled_response:
        return disabled_response



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

    item_id = c.lastrowid
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

    run_automation_event(
        company_id,
        "catalog_item_created",
        "catalog_item",
        item_id,
        f"Создана позиция каталога: {name}",
        "/catalog",
    )

    return RedirectResponse("/catalog?created=1", status_code=302)


@router.post("/catalog/{item_id}/toggle")
async def toggle_catalog_item(request: Request, item_id: int):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role not in ("boss", "manager"):
        return RedirectResponse("/", status_code=302)

    company_id = get_user_company_id(username)

    disabled_response = require_feature(company_id, "catalog")

    if disabled_response:
        return disabled_response



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

    run_automation_event(
        company_id,
        "catalog_item_toggled",
        "catalog_item",
        item_id,
        (
            f"Позиция каталога {'включена' if new_active else 'выключена'}: "
            f"{item['name']}"
        ),
        "/catalog",
    )

    return RedirectResponse("/catalog", status_code=302)
