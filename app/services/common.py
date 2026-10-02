"""Shared company helpers: settings, feature flags, notifications, links.

Extracted from app.main so domain routers can import them without a
circular dependency on the application module.
"""

from datetime import datetime

from fastapi.responses import RedirectResponse

from app.database import connect

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
