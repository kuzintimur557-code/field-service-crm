"""Shared company helpers: settings, feature flags, notifications, links.

Extracted from app.main so domain routers can import them without a
circular dependency on the application module.
"""

import calendar
from datetime import datetime

from fastapi.responses import RedirectResponse

from app.database import connect
from app.deps import get_user_company_id
from app.services.email_inbox import find_or_create_inbox_client

FEATURE_DEFINITIONS = [
    ("tasks", "Заявки", "Создание и ведение заявок"),
    ("calendar", "Календарь", "Планирование работ по дням"),
    ("clients", "Клиенты", "База клиентов и карточки"),
    ("catalog", "Каталог", "Услуги, товары и материалы"),
    ("recurring", "Регулярные работы", "Повторяющиеся заявки"),
    ("finance", "Финансы", "Выручка, расходы и прибыль"),
    ("payroll", "Зарплаты", "Выплаты и комиссии исполнителей"),
    ("analytics", "Аналитика", "Панель владельца и графики"),
    ("sla", "SLA", "Сроки, просрочки и качество сервиса"),
    ("archive", "Архив", "Архивированные заявки"),
    ("workload", "Загрузка", "Загрузка исполнителей"),
    ("notifications", "Уведомления", "Центр уведомлений"),
    ("automation", "Автоматизация", "Правила, триггеры и действия"),
    ("ai_insights", "ИИ-инсайты", "ИИ-рекомендации и бизнес-инсайты"),
    ("calls", "Звонки", "История и будущая телефония"),
    ("inbox", "Почта", "Приём заявок из email-писем"),
    ("one_c", "1С", "Интеграция с 1С"),
    ("custom_fields", "Поля компании", "Настраиваемые поля")
]

CORE_FEATURES = {"tasks", "notifications"}

def require_company_id_value(company_id):
    if not company_id:
        raise ValueError("company_id is required")

    return company_id


def get_company_settings(company_id):
    company_id = require_company_id_value(company_id)

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


def ensure_company_features(company_id):
    company_id = require_company_id_value(company_id)

    conn = connect()
    c = conn.cursor()
    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    for feature_key, _, _ in FEATURE_DEFINITIONS:
        c.execute("""
        INSERT OR IGNORE INTO company_features (
            company_id,
            feature_key,
            enabled,
            updated_at
        )
        VALUES (?, ?, ?, ?)
        """, (
            company_id,
            feature_key,
            1,
            now
        ))

    conn.commit()
    conn.close()

def get_company_features(company_id):
    company_id = require_company_id_value(company_id)
    ensure_company_features(company_id)

    features = {
        feature_key: True
        for feature_key, _, _ in FEATURE_DEFINITIONS
    }

    conn = connect()
    c = conn.cursor()

    rows = c.execute("""
    SELECT feature_key, enabled
    FROM company_features
    WHERE company_id=?
    """, (company_id,)).fetchall()

    conn.close()

    for row in rows:
        features[row["feature_key"]] = bool(row["enabled"])

    for feature_key in CORE_FEATURES:
        features[feature_key] = True

    return features

def has_feature(company_id, feature_key):
    if not company_id:
        return False

    return get_company_features(company_id).get(feature_key, True)


def require_feature(company_id, feature_key):
    if has_feature(company_id, feature_key):
        return None

    return RedirectResponse("/", status_code=302)

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

def build_dashboard_links():
    return {
        "home": "/",
        "my_tasks": "/my-tasks",
        "create_task": "/create-task",
        "calendar": "/calendar",
        "sla": "/sla",
        "clients": "/clients",
        "catalog": "/catalog",
        "custom_fields": "/custom-fields",
        "recurring": "/recurring",
        "finance": "/finance",
        "payroll": "/payroll",
        "owner_dashboard": "/owner/dashboard",
        "sla_analytics": "/sla/analytics",
        "archive": "/archive",
        "calls": "/calls",
        "calls_follow_up": "/calls?status=follow_up",
        "inbox": "/inbox",
        "automation": "/automation",
        "ai_insights": "/ai/insights",
        "ai_assistant": "/ai/assistant",
        "workers": "/workers",
        "admin": "/admin",
        "settings": "/settings",
        "notifications": "/notifications",
        "profile": "/profile",
        "more": "/more",
        "logout": "/logout",
        "today": "/today",
        "overdue": "/overdue",
        "sla_overdue": "/sla?filter=overdue",
        "sla_soon": "/sla?filter=soon",
        "workload": "/workload",
    }


def create_call_follow_up_notification(
    company_id,
    username,
    client_name="",
    client_id=None,
    summary="",
    phone="",
    call_id=None
):
    link = f"/calls/{call_id}" if call_id else (f"/clients/{client_id}" if client_id else "/calls")
    details = summary or phone or "Проверьте звонок и запланируйте следующий контакт."
    client_part = f"Клиент: {client_name}. " if client_name else ""

    create_notification(
        company_id,
        username,
        "Нужен контакт по звонку",
        f"{client_part}{details}",
        link,
    )


def get_company_mode(settings):
    keys = settings.keys() if settings and hasattr(settings, "keys") else []
    mode = str(settings["mode"] or "company") if "mode" in keys else "company"
    return mode if mode in ("company", "master") else "company"


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


def role_label(role):
    labels = {
        "superadmin": "Суперадмин",
        "boss": "Владелец",
        "manager": "Менеджер",
        "worker": "Исполнитель",
    }
    return labels.get(role, role or "")


def ui_text(value):
    text = str(value or "")
    replacements = {
        "Automation:": "Автоматизация:",
        "AI daily digest": "Ежедневная ИИ-сводка",
        "AI weekly digest": "Еженедельная ИИ-сводка",
        "Deadline": "Срок",
        "deadline": "срок",
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    return text


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


def get_task_company_id(task):
    if not task:
        return None

    task_keys = task.keys() if hasattr(task, "keys") else []

    if "company_id" not in task_keys:
        return None

    return task["company_id"]


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
    task_company_id = get_task_company_id(task)

    if not task_company_id:
        return chat_ids

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

    task_company_id = get_task_company_id(task)

    if not task_company_id:
        return False

    user_company_id = get_user_company_id(username)

    if role == "superadmin":
        return True

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


def get_workers_for_company(
    company_id: int,
    status: str = "active",
    search: str = "",
):
    if status not in ("active", "inactive", "all"):
        status = "active"

    selected_search = str(search or "").strip()[:100]

    status_condition = ""
    if status == "active":
        status_condition = "AND COALESCE(is_active, 1)=1"
    elif status == "inactive":
        status_condition = "AND is_active=0"

    search_condition = ""
    worker_params = [company_id]

    if selected_search:
        search_pattern = f"%{selected_search.lower()}%"
        search_condition = """
      AND (
          LOWER(COALESCE(username, '')) LIKE ?
          OR LOWER(COALESCE(full_name, '')) LIKE ?
          OR LOWER(COALESCE(position, '')) LIKE ?
          OR LOWER(COALESCE(phone, '')) LIKE ?
          OR LOWER(COALESCE(email, '')) LIKE ?
          OR LOWER(COALESCE(telegram_chat_id, '')) LIKE ?
      )
        """
        worker_params.extend([
            search_pattern,
            search_pattern,
            search_pattern,
            search_pattern,
            search_pattern,
            search_pattern,
        ])

    conn = connect()
    c = conn.cursor()

    workers = c.execute(f"""
    SELECT * FROM users
    WHERE role IN ('manager', 'worker') AND company_id=?
      {status_condition}
      {search_condition}
    ORDER BY role, is_active DESC, username
    """, worker_params).fetchall()

    conn.close()

    return {
        "workers": workers,
        "status": status,
        "search": selected_search,
    }


TEAM_ACTIVITY_FILTERS = {
    "all": None,
    "membership": ("Пользователь создан", "Пользователь удалён"),
    "access": ("Пользователь отключён", "Пользователь включён"),
    "password": ("Пароль обновлён",),
    "commission": ("Процент обновлён",),
    "limits": ("Лимит тарифа",),
    "billing": ("Счёт платформы создан", "Статус счёта платформы"),
}


INDUSTRY_OPTIONS = [
    ("field_service", "Сервис / выездные работы"),
    ("beauty", "Бьюти"),
    ("cleaning", "Клининг"),
    ("repair", "Ремонт"),
    ("auto_service", "Автосервис"),
    ("logistics", "Грузоперевозки"),
    ("agency", "Агентство"),
    ("medical", "Медицина"),
    ("education", "Обучение"),
    ("restaurant", "Ресторан / кафе"),
    ("ecommerce", "Интернет-магазин"),
    ("other", "Другая сфера"),
    ("custom", "Своя сфера")
]


def get_industry_label(industry):
    return dict(INDUSTRY_OPTIONS).get(
        str(industry or "field_service"),
        "Сфера не указана",
    )


BUSINESS_PRESETS = {
    "field_service": {
        "calendar", "clients", "catalog", "recurring", "finance", "payroll",
        "analytics", "ai_insights", "sla", "archive", "workload", "notifications", "automation", "calls",
        "custom_fields"
    },
    "beauty": {
        "calendar", "clients", "catalog", "finance", "payroll", "analytics", "ai_insights",
        "notifications", "automation", "calls", "custom_fields"
    },
    "cleaning": {
        "calendar", "clients", "recurring", "finance", "payroll", "analytics", "ai_insights",
        "sla", "archive", "workload", "notifications", "automation", "calls", "custom_fields"
    },
    "repair": {
        "calendar", "clients", "catalog", "finance", "payroll", "analytics", "ai_insights",
        "sla", "archive", "workload", "notifications", "automation", "calls", "custom_fields"
    },
    "auto_service": {
        "calendar", "clients", "catalog", "finance", "payroll", "analytics", "ai_insights",
        "sla", "archive", "workload", "notifications", "automation", "calls", "custom_fields"
    },
    "logistics": {
        "calendar", "clients", "recurring", "finance", "payroll", "analytics", "ai_insights",
        "sla", "archive", "workload", "notifications", "automation", "calls", "custom_fields"
    },
    "agency": {
        "clients", "finance", "payroll", "analytics", "ai_insights", "archive",
        "notifications", "automation", "calls", "custom_fields"
    },
    "medical": {
        "calendar", "clients", "finance", "payroll", "analytics", "ai_insights",
        "notifications", "automation", "calls", "custom_fields"
    },
    "education": {
        "calendar", "clients", "recurring", "finance", "payroll", "analytics", "ai_insights",
        "notifications", "automation", "custom_fields"
    },
    "restaurant": {
        "calendar", "clients", "catalog", "finance", "payroll", "analytics", "ai_insights",
        "notifications", "automation", "custom_fields"
    },
    "ecommerce": {
        "clients", "catalog", "finance", "payroll", "analytics", "ai_insights",
        "archive", "notifications", "automation", "custom_fields"
    },
    "other": {
        "calendar", "clients", "catalog", "recurring", "finance", "payroll",
        "analytics", "ai_insights", "sla", "archive", "workload", "notifications", "automation", "calls",
        "custom_fields"
    },
    "custom": {
        "calendar", "clients", "catalog", "recurring", "finance", "payroll",
        "analytics", "ai_insights", "sla", "archive", "workload", "notifications", "automation", "calls",
        "custom_fields"
    }
}

def get_industry_label(industry):
    return dict(INDUSTRY_OPTIONS).get(industry, industry or "")


def build_settings_links():
    return {
        "home": "/",
        "debug": "/debug",
        "billing": "/billing",
        "custom_fields": "/custom-fields",
        "history": "/settings/history",
    }


def create_task_from_draft(
    company_id,
    username,
    role,
    client_name,
    phone="",
    email="",
    address="",
    task_date="",
    description="",
    price="",
    worker="",
    source_kind="",
    details="",
):
    client_id = find_or_create_inbox_client(
        company_id, client_name, phone, email, address
    )

    conn = connect()
    c = conn.cursor()

    try:
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
            status,
            created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            company_id,
            client_id,
            client_name,
            phone,
            address,
            description,
            task_date,
            worker,
            worker,
            "Обычный",
            price,
            "Новая",
            datetime.now().strftime("%Y-%m-%d %H:%M"),
        ))

        task_id = c.lastrowid
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    if worker:
        create_notification(
            company_id,
            worker,
            f"Назначена новая заявка #{task_id}",
            (
                f"Клиент: {client_name}. "
                f"Дата: {task_date or 'не указана'}."
            ),
            f"/task/{task_id}",
        )

    action_labels = {
        "voice": "Создано из голосового ввода",
        "email": "Создано из письма",
    }
    log_task_activity(
        task_id,
        username,
        role,
        action_labels.get(source_kind, "Создано из черновика"),
        details[:200],
    )

    return task_id, client_id
