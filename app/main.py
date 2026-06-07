from app.services.workflow_timeline import get_workflow_timeline
from app.services.automation_analytics import (
    get_automation_analytics,
    get_unhealthy_rules,
)
from app.services.autonomous_actions import (
    approve_autonomous_action,
    enqueue_autonomous_action,
    get_autonomous_actions,
    process_autonomous_actions,
    reject_autonomous_action,
)
from app.services.decision_engine import get_decision_engine

from app.services.governance import (
    ensure_governance_settings,
    get_governance_settings,
    save_governance_settings,
    get_approval_queue,
    get_approval_history,
)
from app.services.ops_timeline import (
    create_ops_timeline_event,
    get_ops_timeline,
)
from app.services.operations_insights import get_operations_insights
from app.services.predictive_signals import get_predictive_signals
from app.services.self_healing import (
    get_recovery_history,
    run_self_healing_cycle,
)
from app.services.system_health import (
    calculate_system_health,
    get_system_health_history,
)
from app.services.workflow_graph import (
    get_company_workflow_graphs,
    get_rule_workflow_debug,
    get_rule_workflow_graph,
)
from fastapi import FastAPI, Request, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse, FileResponse, Response, JSONResponse
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
import json


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
        "AI daily digest": "Ежедневная AI-сводка",
        "AI weekly digest": "Еженедельная AI-сводка",
        "Deadline": "Срок",
        "deadline": "срок",
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    return text


templates.env.globals["role_label"] = role_label
templates.env.globals["ui_text"] = ui_text



def get_current_company_id(request=None):
    try:
        if request and hasattr(request, "session"):
            company_id = request.session.get("company_id")

            if company_id:
                return int(company_id)
    except Exception:
        pass

    try:
        user = get_current_user(request)

        if user and user.get("company_id"):
            return int(user["company_id"])
    except Exception:
        pass

    return 1

DATA_DIR = Path(os.getenv("DATA_DIR", "."))
UPLOAD_DIR = DATA_DIR / "uploads"
DOCS_DIR = UPLOAD_DIR / "docs"
CLIENT_FILES_DIR = UPLOAD_DIR / "client_files"

UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
DOCS_DIR.mkdir(parents=True, exist_ok=True)
CLIENT_FILES_DIR.mkdir(parents=True, exist_ok=True)
ALLOWED_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".heic", ".heif"}
ALLOWED_CLIENT_FILE_EXTENSIONS = {
    ".pdf", ".jpg", ".jpeg", ".png", ".webp", ".doc", ".docx",
    ".xls", ".xlsx", ".csv", ".txt"
}
PDF_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}

AUTOMATION_TRIGGERS = [
    ("overdue_task", "Просрочена задача"),
    ("sla_overdue", "Просрочен SLA"),
    ("unpaid_task", "Нет оплаты"),
    ("worker_overload", "Перегрузка сотрудника"),
    ("new_client", "Новый клиент"),
    ("daily_digest", "Ежедневная AI-сводка"),
    ("weekly_digest", "Еженедельная AI-сводка")
]

AUTOMATION_ACTIONS = [
    ("notification", "Создать уведомление"),
    ("telegram_alert", "Telegram-уведомление"),
    ("ai_digest", "AI-сводка"),
    ("email", "Электронная почта"),
    ("create_task", "Создать задачу")
]

AUTOMATION_STATUS_LABELS = {
    "pending": "Ожидает",
    "done": "Выполнено",
    "skipped": "Пропущено"
}

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
    ("ai_insights", "AI-инсайты", "AI-рекомендации и бизнес-инсайты"),
    ("calls", "Звонки", "История и будущая телефония"),
    ("one_c", "1С", "Интеграция с 1С"),
    ("custom_fields", "Поля компании", "Настраиваемые поля")
]

CORE_FEATURES = {"tasks", "notifications"}

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


INDUSTRY_LABEL_PRESETS = {
    "field_service": {
        "task_label": "Заявка",
        "worker_label": "Исполнитель",
        "client_label": "Клиент",
        "service_label": "Услуга"
    },
    "beauty": {
        "task_label": "Запись",
        "worker_label": "Мастер",
        "client_label": "Клиент",
        "service_label": "Услуга"
    },
    "cleaning": {
        "task_label": "Заказ",
        "worker_label": "Клинер",
        "client_label": "Клиент",
        "service_label": "Уборка"
    },
    "repair": {
        "task_label": "Заказ",
        "worker_label": "Мастер",
        "client_label": "Клиент",
        "service_label": "Работа"
    },
    "auto_service": {
        "task_label": "Заказ-наряд",
        "worker_label": "Мастер",
        "client_label": "Клиент",
        "service_label": "Работа"
    },
    "logistics": {
        "task_label": "Рейс",
        "worker_label": "Водитель",
        "client_label": "Клиент",
        "service_label": "Перевозка"
    },
    "agency": {
        "task_label": "Проект",
        "worker_label": "Специалист",
        "client_label": "Клиент",
        "service_label": "Услуга"
    },
    "medical": {
        "task_label": "Приём",
        "worker_label": "Специалист",
        "client_label": "Пациент",
        "service_label": "Услуга"
    },
    "education": {
        "task_label": "Занятие",
        "worker_label": "Преподаватель",
        "client_label": "Ученик",
        "service_label": "Курс"
    },
    "restaurant": {
        "task_label": "Заказ",
        "worker_label": "Сотрудник",
        "client_label": "Гость",
        "service_label": "Блюдо"
    },
    "ecommerce": {
        "task_label": "Заказ",
        "worker_label": "Сотрудник",
        "client_label": "Покупатель",
        "service_label": "Товар"
    },
    "other": {
        "task_label": "Задача",
        "worker_label": "Сотрудник",
        "client_label": "Клиент",
        "service_label": "Услуга"
    },
    "custom": {
        "task_label": "Задача",
        "worker_label": "Сотрудник",
        "client_label": "Клиент",
        "service_label": "Услуга"
    }
}


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


def safe_client_file_filename(client_id, original_filename):
    original = Path(original_filename or "file").name
    extension = Path(original).suffix.lower()

    if extension not in ALLOWED_CLIENT_FILE_EXTENSIONS:
        extension = ".bin"

    return f"client_{client_id}_{uuid4().hex}{extension}"


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


def ensure_company_features(company_id=1):
    company_id = company_id or 1

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


def get_company_features(company_id=1):
    company_id = company_id or 1
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
    return get_company_features(company_id).get(feature_key, True)


def require_feature(company_id, feature_key):
    if has_feature(company_id, feature_key):
        return None

    return RedirectResponse("/", status_code=302)


def update_company_features(company_id, form):
    company_id = company_id or 1
    ensure_company_features(company_id)

    conn = connect()
    c = conn.cursor()
    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    for feature_key, _, _ in FEATURE_DEFINITIONS:
        enabled = 1 if feature_key in CORE_FEATURES else int(form.get(f"feature_{feature_key}") == "1")

        c.execute("""
        UPDATE company_features
        SET enabled=?, updated_at=?
        WHERE company_id=? AND feature_key=?
        """, (
            enabled,
            now,
            company_id,
            feature_key
        ))

    conn.commit()
    conn.close()


def get_industry_labels(industry):
    return INDUSTRY_LABEL_PRESETS.get(
        industry,
        INDUSTRY_LABEL_PRESETS["other"]
    )



def apply_business_preset(company_id, industry):
    company_id = company_id or 1
    ensure_company_features(company_id)

    enabled_features = set(BUSINESS_PRESETS.get(industry) or BUSINESS_PRESETS["other"])
    enabled_features.update(CORE_FEATURES)
    labels = get_industry_labels(industry)

    conn = connect()
    c = conn.cursor()
    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    for feature_key, _, _ in FEATURE_DEFINITIONS:
        enabled = 1 if feature_key in enabled_features else 0

        c.execute("""
        UPDATE company_features
        SET enabled=?, updated_at=?
        WHERE company_id=? AND feature_key=?
        """, (
            enabled,
            now,
            company_id,
            feature_key
        ))

    c.execute("""
    UPDATE company_settings
    SET
        task_label=?,
        worker_label=?,
        client_label=?,
        service_label=?,
        updated_at=?
    WHERE company_id=?
    """, (
        labels["task_label"],
        labels["worker_label"],
        labels["client_label"],
        labels["service_label"],
        now,
        company_id
    ))

    conn.commit()
    conn.close()


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


def log_ai_assistant_event(company_id, note_id, username, action, details=""):
    conn = connect()
    c = conn.cursor()

    c.execute("""
    INSERT INTO ai_assistant_events (
        company_id, note_id, username, action, details, created_at
    )
    VALUES (?, ?, ?, ?, ?, ?)
    """, (
        company_id,
        note_id,
        username,
        action,
        details,
        datetime.now().strftime("%Y-%m-%d %H:%M")
    ))

    conn.commit()
    conn.close()


def create_ai_follow_up_notifications(company_id, username, now_dt=None):
    now_dt = now_dt or datetime.now()
    today_key = now_dt.strftime("%Y-%m-%d")
    now = now_dt.strftime("%Y-%m-%d %H:%M")
    created_count = 0

    conn = connect()
    c = conn.cursor()

    due_notes = c.execute("""
    SELECT *
    FROM ai_assistant_notes
    WHERE company_id=?
      AND COALESCE(is_done, 0)=0
      AND follow_up_date IS NOT NULL
      AND follow_up_date!=''
      AND follow_up_date <= ?
    ORDER BY
      CASE COALESCE(priority, 'normal')
        WHEN 'urgent' THEN 0
        WHEN 'normal' THEN 1
        ELSE 2
      END,
      follow_up_date ASC,
      id DESC
    """, (company_id, today_key)).fetchall()

    for note in due_notes:
        title = f"AI контроль: заметка #{note['id']}"
        message = note["note"]
        duplicate_count = c.execute("""
        SELECT COUNT(*)
        FROM notifications
        WHERE company_id=?
          AND username=?
          AND title=?
          AND created_at LIKE ?
        """, (
            company_id,
            username,
            title,
            f"{today_key}%"
        )).fetchone()[0]

        if duplicate_count:
            continue

        c.execute("""
        INSERT INTO notifications (
            company_id, username, title, message, link, created_at
        )
        VALUES (?, ?, ?, ?, ?, ?)
        """, (
            company_id,
            username,
            title,
            message,
            "/ai/assistant",
            now
        ))
        created_count += 1

        c.execute("""
        UPDATE ai_assistant_notes
        SET last_notified_at=?,
            notification_count=COALESCE(notification_count, 0) + 1
        WHERE id=?
          AND company_id=?
        """, (
            now,
            note["id"],
            company_id
        ))

        c.execute("""
        INSERT INTO ai_assistant_events (
            company_id, note_id, username, action, details, created_at
        )
        VALUES (?, ?, ?, ?, ?, ?)
        """, (
            company_id,
            note["id"],
            username,
            "notification_sent",
            title,
            now
        ))

        user_row = c.execute("""
        SELECT telegram_chat_id
        FROM users
        WHERE company_id=?
          AND username=?
        """, (company_id, username)).fetchone()

        if user_row and user_row["telegram_chat_id"]:
            try:
                send_message_to_chat(
                    user_row["telegram_chat_id"],
                    f"{title}\n{message}"
                )
            except Exception:
                pass

    conn.commit()
    conn.close()

    return created_count


def create_ai_follow_up_notifications_for_company(company_id, now_dt=None):
    if not has_feature(company_id, "notifications"):
        return 0

    conn = connect()
    c = conn.cursor()

    recipients = c.execute("""
    SELECT username
    FROM users
    WHERE company_id=?
      AND role IN ('boss', 'manager')
    ORDER BY role, username
    """, (company_id,)).fetchall()

    conn.close()

    created_count = 0

    for recipient in recipients:
        created_count += create_ai_follow_up_notifications(
            company_id,
            recipient["username"],
            now_dt
        )

    return created_count




def build_ai_digest_message(company_id, cursor=None):
    conn = None
    c = cursor

    if c is None:
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

    settings = c.execute("""
    SELECT *
    FROM company_settings
    WHERE company_id=?
    """, (company_id,)).fetchone()

    overdue_tasks = c.execute("""
    SELECT COUNT(*)
    FROM tasks
    WHERE company_id=?
      AND archived=0
      AND status!='Завершено'
      AND task_date < date('now')
    """, (company_id,)).fetchone()[0]

    unpaid_total = c.execute("""
    SELECT COALESCE(SUM(price), 0)
    FROM tasks
    WHERE company_id=?
      AND archived=0
      AND payment_status!='Оплачено'
    """, (company_id,)).fetchone()[0]

    active_notes = c.execute("""
    SELECT note, priority, follow_up_date
    FROM ai_assistant_notes
    WHERE company_id=?
      AND COALESCE(is_done, 0)=0
    ORDER BY
      CASE
        WHEN follow_up_date IS NOT NULL
         AND follow_up_date!=''
         AND follow_up_date <= date('now') THEN 0
        ELSE 1
      END,
      CASE COALESCE(priority, 'normal')
        WHEN 'urgent' THEN 0
        WHEN 'normal' THEN 1
        ELSE 2
      END,
      id DESC
    LIMIT 3
    """, (company_id,)).fetchall()

    if conn:
        conn.commit()
        conn.close()

    message_lines = [
        "AI-сводка по бизнесу",
        f"Просроченные {settings['task_label'] or 'задачи'}: {overdue_tasks}",
        f"Неоплаченная сумма: ₽{round(float(unpaid_total or 0), 1)}"
    ]

    if overdue_tasks:
        message_lines.append("Рекомендация: проверьте ответственных и сроки.")

    if unpaid_total:
        message_lines.append("Рекомендация: запустите напоминания по оплатам.")

    if active_notes:
        message_lines.append("Активные заметки владельца:")

        for note in active_notes:
            priority_prefix = "Срочно: " if note["priority"] == "urgent" else ""
            follow_up_suffix = f" (контроль: {note['follow_up_date']})" if note["follow_up_date"] else ""
            message_lines.append(f"- {priority_prefix}{note['note']}{follow_up_suffix}")

    return "\n".join(message_lines)


def build_owner_ai_assistant_context(company_id, note_filter="", note_search="", event_filter=""):
    settings = get_company_settings(company_id)
    task_label = settings["task_label"] or "задачи"
    worker_label = settings["worker_label"] or "сотрудник"
    trigger_labels = dict(AUTOMATION_TRIGGERS)
    selected_note_filter = note_filter if note_filter in ("due", "urgent") else ""
    selected_note_search = (note_search or "").strip()[:80]
    selected_event_filter = event_filter if event_filter in (
        "created",
        "notification_sent",
        "postponed",
        "done"
    ) else ""
    note_filter_sql = ""
    note_params = [company_id]
    completed_note_params = [company_id]
    event_filter_sql = ""
    event_params = [company_id]

    if selected_note_filter == "due":
        note_filter_sql = """
          AND follow_up_date IS NOT NULL
          AND follow_up_date!=''
          AND follow_up_date <= date('now')
        """
    elif selected_note_filter == "urgent":
        note_filter_sql = """
          AND COALESCE(priority, 'normal')='urgent'
        """

    note_search_sql = ""

    if selected_note_search:
        note_search_sql = "AND note LIKE ?"
        note_params.append(f"%{selected_note_search}%")
        completed_note_params.append(f"%{selected_note_search}%")

    if selected_event_filter:
        event_filter_sql = "AND action=?"
        event_params.append(selected_event_filter)

    conn = connect()
    c = conn.cursor()

    overdue_tasks = c.execute("""
    SELECT COUNT(*)
    FROM tasks
    WHERE company_id=?
      AND archived=0
      AND status NOT IN ('Завершено', 'Отменено')
      AND task_date < date('now')
    """, (company_id,)).fetchone()[0]

    active_tasks = c.execute("""
    SELECT COUNT(*)
    FROM tasks
    WHERE company_id=?
      AND archived=0
      AND status IN ('Новая', 'В работе')
    """, (company_id,)).fetchone()[0]

    unpaid_total = c.execute("""
    SELECT COALESCE(SUM(CAST(REPLACE(COALESCE(price, '0'), ',', '.') AS REAL)), 0)
    FROM tasks
    WHERE company_id=?
      AND archived=0
      AND payment_status!='Оплачено'
    """, (company_id,)).fetchone()[0]

    worker_count = c.execute("""
    SELECT COUNT(*)
    FROM users
    WHERE company_id=?
      AND role='worker'
    """, (company_id,)).fetchone()[0]

    assistant_note_stats = c.execute("""
    SELECT
        COUNT(*) AS active_count,
        SUM(CASE WHEN COALESCE(priority, 'normal')='urgent' THEN 1 ELSE 0 END) AS urgent_count,
        SUM(
            CASE
                WHEN follow_up_date IS NOT NULL
                 AND follow_up_date!=''
                 AND follow_up_date <= date('now')
                THEN 1
                ELSE 0
            END
        ) AS due_count
    FROM ai_assistant_notes
    WHERE company_id=?
      AND COALESCE(is_done, 0)=0
    """, (company_id,)).fetchone()

    overdue_rows = c.execute("""
    SELECT id, client, task_date, workers, worker, status
    FROM tasks
    WHERE company_id=?
      AND archived=0
      AND status NOT IN ('Завершено', 'Отменено')
      AND task_date < date('now')
    ORDER BY task_date ASC
    LIMIT 5
    """, (company_id,)).fetchall()

    action_history = c.execute("""
    SELECT
        automation_events.*,
        automation_rules.name AS rule_name
    FROM automation_events
    LEFT JOIN automation_rules
      ON automation_rules.id=automation_events.rule_id
      AND automation_rules.company_id=automation_events.company_id
    WHERE automation_events.company_id=?
      AND automation_events.trigger_key IN (
          'overdue_task',
          'sla_overdue',
          'daily_digest',
          'weekly_digest'
      )
    ORDER BY automation_events.id DESC
    LIMIT 8
    """, (company_id,)).fetchall()

    assistant_notes = c.execute(f"""
    SELECT *
    FROM ai_assistant_notes
    WHERE company_id=?
      AND COALESCE(is_done, 0)=0
      {note_filter_sql}
      {note_search_sql}
    ORDER BY
      CASE
        WHEN follow_up_date IS NOT NULL
         AND follow_up_date!=''
         AND follow_up_date <= date('now') THEN 0
        ELSE 1
      END,
      CASE COALESCE(priority, 'normal')
        WHEN 'urgent' THEN 0
        WHEN 'normal' THEN 1
        ELSE 2
      END,
      id DESC
    LIMIT 8
    """, note_params).fetchall()

    ai_events = c.execute(f"""
    SELECT *
    FROM ai_assistant_events
    WHERE company_id=?
      {event_filter_sql}
    ORDER BY id DESC
    LIMIT 10
    """, event_params).fetchall()

    completed_notes = c.execute(f"""
    SELECT
        ai_assistant_notes.*,
        tasks.client AS created_task_client,
        tasks.status AS created_task_status
    FROM ai_assistant_notes
    LEFT JOIN tasks
      ON tasks.id=ai_assistant_notes.created_task_id
      AND tasks.company_id=ai_assistant_notes.company_id
    WHERE ai_assistant_notes.company_id=?
      AND COALESCE(ai_assistant_notes.is_done, 0)=1
      {note_search_sql}
    ORDER BY ai_assistant_notes.id DESC
    LIMIT 8
    """, completed_note_params).fetchall()

    conn.close()

    action_history_rows = []

    for event in action_history:
        event_row = dict(event)
        event_row["trigger_label"] = trigger_labels.get(event["trigger_key"], event["trigger_key"])
        event_row["status_label"] = AUTOMATION_STATUS_LABELS.get(event["status"], event["status"])
        action_history_rows.append(event_row)

    priorities = []

    if overdue_tasks:
        priorities.append({
            "level": "danger",
            "title": "Сначала разберите просрочки",
            "reason": f"Просрочено: {overdue_tasks} ({task_label}).",
            "action": "Открыть просрочки",
            "link": "/overdue"
        })

    if unpaid_total:
        priorities.append({
            "level": "warning",
            "title": "Проверьте неоплаченные работы",
            "reason": f"Неоплаченная сумма: ₽{round(float(unpaid_total or 0), 1)}.",
            "action": "Открыть финансы",
            "link": "/finance"
        })

    if worker_count and active_tasks > worker_count * 3:
        priorities.append({
            "level": "warning",
            "title": "Проверьте загрузку команды",
            "reason": f"Активных {task_label}: {active_tasks}, {worker_label}: {worker_count}.",
            "action": "Открыть загрузку",
            "link": "/workload"
        })

    if not priorities:
        priorities.append({
            "level": "success",
            "title": "Критичных действий сейчас нет",
            "reason": "AI-помощник не видит срочных просрочек, перегруза или кассового риска.",
            "action": "Смотреть AI-инсайты",
            "link": "/ai/insights"
        })

    next_steps = [
        "Проверьте самый старый риск первым.",
        "Назначьте ответственного и дату следующего действия.",
        "После исправления запустите AI-сводку повторно."
    ]

    return {
        "settings": settings,
        "metrics": {
            "overdue_tasks": overdue_tasks,
            "active_tasks": active_tasks,
            "unpaid_total": round(float(unpaid_total or 0), 1),
            "worker_count": worker_count,
            "ai_notes_active": assistant_note_stats["active_count"] or 0,
            "ai_notes_urgent": assistant_note_stats["urgent_count"] or 0,
            "ai_notes_due": assistant_note_stats["due_count"] or 0
        },
        "priorities": priorities,
        "next_steps": next_steps,
        "overdue_rows": overdue_rows,
        "action_history": action_history_rows,
        "assistant_notes": assistant_notes,
        "ai_events": ai_events,
        "selected_note_filter": selected_note_filter,
        "selected_note_search": selected_note_search,
        "selected_event_filter": selected_event_filter,
        "completed_notes": completed_notes
    }


def automation_single_condition_matches(c, company_id, rule, entity_type, entity_id, condition):
    rule_data = dict(rule)
    rule_data["conditions_json"] = json.dumps(condition or {}, ensure_ascii=False)
    return automation_condition_matches(
        c,
        company_id,
        rule_data,
        entity_type,
        entity_id,
    )


def automation_combined_conditions_match(c, company_id, rule, entity_type, entity_id, conditions):
    items = conditions.get("conditions") or []
    operator = str(conditions.get("operator") or "and").lower()

    if not items:
        return True, ""

    results = [
        automation_single_condition_matches(
            c,
            company_id,
            rule,
            entity_type,
            entity_id,
            item,
        )
        for item in items
    ]

    if operator == "or":
        if any(result[0] for result in results):
            return True, ""

        message = "; ".join([result[1] for result in results if result[1]])
        return False, message or "Ни одно условие не выполнено"

    if all(result[0] for result in results):
        return True, ""

    message = "; ".join([result[1] for result in results if result[1]])
    return False, message or "Не все условия выполнены"


def automation_condition_diagnostics(c, company_id, rule, entity_type, entity_id):
    try:
        conditions = json.loads(rule["conditions_json"] or "{}")
    except Exception:
        conditions = {}

    items = conditions.get("conditions") or [conditions]
    operator = str(conditions.get("operator") or "and").lower()

    if operator not in ("and", "or"):
        operator = "and"

    details = []

    for condition in items:
        mode = str(condition.get("mode") or "none")
        matched, message = automation_single_condition_matches(
            c,
            company_id,
            rule,
            entity_type,
            entity_id,
            condition,
        )
        details.append({
            "label": str(condition.get("label") or (
                "Без условий" if mode == "none" else mode
            )),
            "matched": bool(matched),
            "message": (
                "Условие выполнено"
                if matched
                else str(message or "Условие не выполнено")
            )[:180],
        })

    results = [item["matched"] for item in details]
    overall = any(results) if operator == "or" else all(results)

    return {
        "matched": overall,
        "operator": operator,
        "operator_label": "ИЛИ" if operator == "or" else "И",
        "details": details,
    }


def automation_condition_batch_summary(c, company_id, rule, task_ids):
    matched_task_ids = []
    rejected_tasks = []
    condition_stats = []
    operator = "and"

    for task_id in task_ids:
        diagnostics = automation_condition_diagnostics(
            c,
            company_id,
            rule,
            "task",
            task_id,
        )
        operator = diagnostics["operator"]

        if not condition_stats:
            condition_stats = [
                {
                    "label": detail["label"],
                    "matched": 0,
                }
                for detail in diagnostics["details"]
            ]

        for index, detail in enumerate(diagnostics["details"]):
            if detail["matched"]:
                condition_stats[index]["matched"] += 1

        if diagnostics["matched"]:
            matched_task_ids.append(task_id)
        elif len(rejected_tasks) < 10:
            rejected_tasks.append({
                "id": task_id,
                "failed_conditions": [
                    detail["label"]
                    for detail in diagnostics["details"]
                    if not detail["matched"]
                ],
            })

    total = len(task_ids)
    matched_count = len(matched_task_ids)

    for item in condition_stats:
        item["match_rate"] = round(
            (item["matched"] / total) * 100
        ) if total else 0

    return {
        "total": total,
        "matched": matched_count,
        "match_rate": round((matched_count / total) * 100) if total else 0,
        "matched_task_ids": matched_task_ids[:10],
        "rejected_tasks": rejected_tasks,
        "condition_stats": condition_stats,
        "operator": operator,
    }


def automation_condition_coverage_assessment(total, matched):
    total = max(int(total or 0), 0)
    matched = max(min(int(matched or 0), total), 0)

    if total == 0:
        return {
            "status": "no_data",
            "tone": "off",
            "title": "Недостаточно данных",
            "message": "Добавьте заявки или увеличьте период проверки.",
        }

    match_rate = round((matched / total) * 100)

    if match_rate == 0:
        return {
            "status": "too_narrow",
            "tone": "warn",
            "title": "Правило слишком узкое",
            "message": "Ни одна заявка не подходит. Проверьте значения и сочетание условий.",
        }

    if match_rate <= 15:
        return {
            "status": "narrow",
            "tone": "warn",
            "title": "Правило узкое",
            "message": "Срабатываний мало. Убедитесь, что нужные заявки не отсеиваются.",
        }

    if match_rate <= 80:
        return {
            "status": "balanced",
            "tone": "ok",
            "title": "Правило сбалансировано",
            "message": "Условия выделяют заметную часть заявок и не охватывают все подряд.",
        }

    if match_rate < 100:
        return {
            "status": "broad",
            "tone": "warn",
            "title": "Правило широкое",
            "message": "Проверьте, не будет ли автоматизация срабатывать слишком часто.",
        }

    return {
        "status": "all",
        "tone": "warn",
        "title": "Правило подходит всем заявкам",
        "message": "Добавьте ограничивающее условие, если автоматизация не должна запускаться всегда.",
    }


def automation_condition_focus_assessment(condition_stats, operator="and"):
    valid_stats = [
        item
        for item in (condition_stats or [])
        if isinstance(item, dict) and item.get("label")
    ]

    if not valid_stats:
        return {}

    operator = "or" if operator == "or" else "and"

    if operator == "or":
        focus = max(
            valid_stats,
            key=lambda item: int(item.get("match_rate") or 0),
        )
        return {
            "title": "Главная ветка условия ИЛИ",
            "label": str(focus["label"]),
            "match_rate": int(focus.get("match_rate") or 0),
            "message": "Эта ветка даёт больше всего совпадений.",
        }

    focus = min(
        valid_stats,
        key=lambda item: int(item.get("match_rate") or 0),
    )
    return {
        "title": "Главное ограничение правила",
        "label": str(focus["label"]),
        "match_rate": int(focus.get("match_rate") or 0),
        "message": "Это условие сильнее остальных сокращает количество подходящих заявок.",
    }


def automation_action_dry_run_preview(action):
    action_data = dict(action)

    try:
        payload = json.loads(action_data.get("payload_json") or "{}")
    except Exception:
        payload = {}

    action_key = str(action_data.get("action_key") or "")
    target = str(payload.get("target_username") or "").strip()
    message = str(payload.get("message") or "").strip()
    subject = str(payload.get("subject") or "").strip()
    task_delay_days, task_priority, task_deadline_hours = (
        automation_create_task_settings(payload)
    )
    task_max_daily_load = automation_task_max_daily_load(payload)
    supported = action_key in {
        "notification",
        "telegram_alert",
        "ai_digest",
        "create_task",
    }

    if action_key == "notification":
        detail = f"Получатель: {target or 'создатель правила'}"
    elif action_key == "telegram_alert":
        detail = f"Telegram: {target or 'создатель правила'}"
    elif action_key == "ai_digest":
        detail = f"AI-сводка для: {target or 'создатель правила'}"
    elif action_key == "email":
        detail = f"Почта: {target or 'получатель не указан'}"
    elif action_key == "create_task":
        target_label = (
            "авто: наименее загруженный"
            if target == "__least_loaded__"
            else target or "без исполнителя"
        )
        schedule_label = (
            "сегодня"
            if task_delay_days == 0
            else f"через {task_delay_days} дн."
        )
        deadline_label = (
            "без SLA"
            if task_deadline_hours == 0
            else f"SLA: {task_deadline_hours} ч."
        )
        load_limit_detail = ""

        if target == "__least_loaded__":
            load_limit_label = (
                "без лимита загрузки"
                if task_max_daily_load == 0
                else f"лимит: {task_max_daily_load} в день"
            )
            load_limit_detail = f" · {load_limit_label}"

        detail = (
            f"Новая задача для: {target_label}"
            f" · {schedule_label}"
            f" · приоритет: {task_priority}"
            f" · {deadline_label}"
            f"{load_limit_detail}"
            " · данные клиента из исходной заявки"
        )
    else:
        detail = "Неизвестное действие"

    if subject:
        detail = f"{detail} · Тема: {subject}"

    if message:
        detail = f"{detail} · {message[:140]}"

    action_data["dry_run_supported"] = supported
    action_data["dry_run_detail"] = detail
    return action_data


def automation_create_task_settings(payload):
    try:
        task_delay_days = int(payload.get("task_delay_days") or 0)
    except (TypeError, ValueError):
        task_delay_days = 0

    if task_delay_days not in (0, 1, 3, 7):
        task_delay_days = 0

    task_priority = str(payload.get("task_priority") or "Обычный").strip()

    if task_priority not in ("Обычный", "Срочно"):
        task_priority = "Обычный"

    try:
        task_deadline_hours = int(payload.get("task_deadline_hours") or 0)
    except (TypeError, ValueError):
        task_deadline_hours = 0

    if task_deadline_hours not in (0, 4, 8, 24, 72):
        task_deadline_hours = 0

    return task_delay_days, task_priority, task_deadline_hours


def automation_task_max_daily_load(payload):
    try:
        max_daily_load = int(payload.get("task_max_daily_load") or 0)
    except (TypeError, ValueError):
        max_daily_load = 0

    if max_daily_load not in (0, 1, 2, 3, 5):
        max_daily_load = 0

    return max_daily_load


def automation_least_loaded_worker(
    c,
    company_id,
    task_date,
    max_daily_load=0,
):
    workers = c.execute("""
    SELECT username, telegram_chat_id
    FROM users
    WHERE company_id=?
      AND role='worker'
    ORDER BY username
    """, (company_id,)).fetchall()

    if not workers:
        return None

    worker_load = {
        worker["username"]: 0
        for worker in workers
    }
    tasks = c.execute("""
    SELECT worker, workers
    FROM tasks
    WHERE company_id=?
      AND archived=0
      AND task_date LIKE ?
      AND status NOT IN ('Завершено', 'Отменено')
    """, (company_id, f"{task_date}%")).fetchall()

    for task in tasks:
        for worker_name in get_task_worker_names(task):
            if worker_name in worker_load:
                worker_load[worker_name] += 1

    available_workers = [
        worker
        for worker in workers
        if (
            not max_daily_load
            or worker_load[worker["username"]] < max_daily_load
        )
    ]

    if not available_workers:
        return None

    selected_worker = min(
        available_workers,
        key=lambda worker: (
            worker_load[worker["username"]],
            worker["username"],
        ),
    )

    return {
        "username": selected_worker["username"],
        "telegram_chat_id": selected_worker["telegram_chat_id"],
        "active_count": worker_load[selected_worker["username"]],
    }


def automation_action_target_is_valid(c, company_id, action_key, target_username):
    target_username = str(target_username or "").strip()

    if action_key == "create_task":
        if not target_username:
            return True

        if target_username == "__least_loaded__":
            return bool(c.execute("""
            SELECT id
            FROM users
            WHERE company_id=?
              AND role='worker'
            LIMIT 1
            """, (company_id,)).fetchone())

        return bool(c.execute("""
        SELECT id
        FROM users
        WHERE company_id=?
          AND username=?
          AND role='worker'
        """, (company_id, target_username)).fetchone())

    if not target_username:
        return action_key not in ("notification", "telegram_alert", "email")

    return bool(c.execute("""
    SELECT id
    FROM users
    WHERE company_id=?
      AND username=?
    """, (company_id, target_username)).fetchone())


def execute_automation_create_task_action(
    c,
    company_id,
    rule,
    action,
    payload,
    entity_type,
    entity_id,
    now,
):
    if entity_type not in ("task", "client") or not entity_id:
        return None

    previous_run = c.execute("""
    SELECT created_entity_id
    FROM automation_action_runs
    WHERE company_id=?
      AND action_id=?
      AND entity_type=?
      AND entity_id=?
    """, (
        company_id,
        action["id"],
        entity_type,
        entity_id,
    )).fetchone()

    if previous_run:
        return previous_run["created_entity_id"]

    if entity_type == "task":
        source_row = c.execute("""
        SELECT
            client_id,
            client,
            phone,
            address
        FROM tasks
        WHERE company_id=?
          AND id=?
          AND archived=0
        """, (company_id, entity_id)).fetchone()
        source_label = f"Исходная заявка: #{entity_id}"
    else:
        source_row = c.execute("""
        SELECT
            id AS client_id,
            name AS client,
            phone,
            address
        FROM clients
        WHERE company_id=?
          AND id=?
        """, (company_id, entity_id)).fetchone()
        source_label = f"Исходный клиент: #{entity_id}"

    if not source_row:
        return None

    description = str(payload.get("message") or "").strip()
    task_delay_days, task_priority, task_deadline_hours = (
        automation_create_task_settings(payload)
    )
    task_max_daily_load = automation_task_max_daily_load(payload)
    scheduled_at = datetime.now() + timedelta(days=task_delay_days)
    task_date = scheduled_at.strftime("%Y-%m-%d")
    deadline_at = ""

    if task_deadline_hours:
        deadline_at = (
            scheduled_at + timedelta(hours=task_deadline_hours)
        ).strftime("%Y-%m-%dT%H:%M")

    target_username = str(payload.get("target_username") or "").strip()
    target_worker = ""
    target_chat_id = ""

    if target_username == "__least_loaded__":
        selected_worker = automation_least_loaded_worker(
            c,
            company_id,
            task_date,
            task_max_daily_load,
        )

        if selected_worker:
            target_worker = selected_worker["username"]
            target_chat_id = str(
                selected_worker["telegram_chat_id"] or ""
            ).strip()
        else:
            return None
    elif target_username:
        worker_row = c.execute("""
        SELECT username, telegram_chat_id
        FROM users
        WHERE company_id=?
          AND username=?
          AND role='worker'
        """, (company_id, target_username)).fetchone()

        if worker_row:
            target_worker = worker_row["username"]
            target_chat_id = str(worker_row["telegram_chat_id"] or "").strip()

    if not description:
        description = f"Автоматическая задача: {rule['name']}"

    c.execute("""
    INSERT INTO tasks (
        company_id, client_id, client, phone, address,
        description, task_date, worker, workers,
        priority, price, photo, status, report,
        after_photo, created_at, deadline_at
    )
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        company_id,
        source_row["client_id"],
        source_row["client"],
        source_row["phone"],
        source_row["address"],
        description,
        task_date,
        target_worker,
        target_worker,
        task_priority,
        "0",
        "",
        "Новая",
        "",
        "",
        now,
        deadline_at,
    ))
    created_task_id = c.lastrowid

    c.execute("""
    INSERT INTO task_activity (
        task_id, username, role, action, details, created_at
    )
    VALUES (?, ?, 'system', 'Создана автоматизацией', ?, ?)
    """, (
        created_task_id,
        rule["created_by"] or "automation",
        (
            f"Правило: {rule['name']}. "
            f"{source_label}. "
            f"Исполнитель: {target_worker or 'не назначен'}. "
            f"Дата: {task_date}. Приоритет: {task_priority}. "
            f"SLA: {deadline_at or 'не задан'}"
        ),
        now,
    ))

    if target_worker:
        c.execute("""
        INSERT INTO notifications (
            company_id, username, title, message,
            link, created_at
        )
        VALUES (?, ?, ?, ?, ?, ?)
        """, (
            company_id,
            target_worker,
            f"Новая автоматическая заявка #{created_task_id}",
            description,
            f"/task/{created_task_id}",
            now,
        ))

    c.execute("""
    INSERT INTO automation_action_runs (
        company_id, action_id, entity_type, entity_id,
        created_entity_type, created_entity_id, created_at
    )
    VALUES (?, ?, ?, ?, 'task', ?, ?)
    """, (
        company_id,
        action["id"],
        entity_type,
        entity_id,
        created_task_id,
        now,
    ))

    if target_chat_id:
        try:
            send_message_to_chat(
                target_chat_id,
                (
                    f"Вам назначена автоматическая заявка #{created_task_id}\n"
                    f"Клиент: {source_row['client'] or 'Без клиента'}\n"
                    f"Дата: {task_date}\n"
                    f"SLA: {deadline_at or 'не задан'}\n"
                    f"Описание: {description}"
                ),
            )
        except Exception:
            pass

    return created_task_id


def automation_dry_run_readiness(rule_active, condition_matched, actions):
    active_actions = [
        automation_action_dry_run_preview(action)
        for action in (actions or [])
        if action["active"]
    ]
    inactive_actions = [
        automation_action_dry_run_preview(action)
        for action in (actions or [])
        if not action["active"]
    ]
    executable_actions = [
        action
        for action in active_actions
        if action["dry_run_supported"]
    ]
    unsupported_actions = [
        action
        for action in active_actions
        if not action["dry_run_supported"]
    ]

    if not rule_active:
        status = {
            "status": "rule_disabled",
            "tone": "off",
            "title": "Запуск заблокирован",
            "message": "Правило выключено. Включите его перед реальным запуском.",
        }
    elif not condition_matched:
        status = {
            "status": "condition_failed",
            "tone": "warn",
            "title": "Запуск заблокирован",
            "message": "Условия не выполнены для выбранной заявки.",
        }
    elif not active_actions:
        status = {
            "status": "no_actions",
            "tone": "warn",
            "title": "Нет активных действий",
            "message": "Добавьте или включите хотя бы одно действие цепочки.",
        }
    elif not executable_actions:
        status = {
            "status": "unsupported_actions",
            "tone": "warn",
            "title": "Действия ещё не поддерживаются",
            "message": "Настроенные действия пока не исполняются текущим runtime.",
        }
    else:
        status = {
            "status": "ready",
            "tone": "ok",
            "title": "Готово к запуску",
            "message": f"Будет выполнено действий: {len(executable_actions)}.",
        }

    status["active_actions"] = active_actions
    status["executable_actions"] = executable_actions
    status["unsupported_actions"] = unsupported_actions
    status["inactive_actions"] = inactive_actions
    return status


def automation_condition_number(conditions, default, minimum=0):
    try:
        value = float(str(conditions.get("value", default)).replace(",", "."))
    except (TypeError, ValueError):
        value = float(default)

    return max(value, minimum)



def automation_condition_matches(c, company_id, rule, entity_type, entity_id):
    try:
        conditions = json.loads(rule["conditions_json"] or "{}")
    except Exception:
        conditions = {}

    if conditions.get("conditions"):
        return automation_combined_conditions_match(
            c,
            company_id,
            rule,
            entity_type,
            entity_id,
            conditions,
        )

    mode = conditions.get("mode") or "none"

    if mode == "none":
        return True, ""

    if entity_type != "task" or not entity_id:
        return False, f"Условие не выполнено: {conditions.get('label') or mode}"

    task = c.execute("""
    SELECT
        id,
        client_id,
        client,
        phone,
        address,
        description,
        priority,
        status,
        payment_status,
        worker,
        workers,
        task_date,
        price,
        deadline_at
    FROM tasks
    WHERE company_id=?
      AND id=?
    """, (
        company_id,
        entity_id,
    )).fetchone()

    if not task:
        return False, f"Условие не выполнено: задача #{entity_id} не найдена"

    priority = str(task["priority"] or "").strip().lower()
    status = str(task["status"] or "").strip().lower()
    payment_status = str(task["payment_status"] or "").strip().lower()
    task_search_text = " ".join([
        str(task["client"] or ""),
        str(task["phone"] or ""),
        str(task["address"] or ""),
        str(task["description"] or ""),
    ]).lower()
    task_date = str(task["task_date"] or "")[:10]
    deadline_at = str(task["deadline_at"] or "")
    deadline_date = deadline_at[:10]

    try:
        task_price = float(
            str(task["price"] or "0")
            .replace(" ", "")
            .replace(",", ".")
        )
    except Exception:
        task_price = 0

    today_dt = datetime.now()
    today = today_dt.strftime("%Y-%m-%d")
    next_24h = today_dt + timedelta(hours=24)
    price_threshold = automation_condition_number(conditions, 10000)
    client_task_threshold = int(automation_condition_number(conditions, 5, 1))

    client_id = task["client_id"]
    client = None

    if client_id:
        client = c.execute("""
        SELECT id, name, phone, notes, created_at
        FROM clients
        WHERE id=?
          AND company_id=?
        """, (client_id, company_id)).fetchone()

    client_task_count = 0
    client_unpaid_count = 0

    if client_id:
        client_task_count = c.execute("""
        SELECT COUNT(*)
        FROM tasks
        WHERE company_id=?
          AND client_id=?
        """, (
            company_id,
            client_id,
        )).fetchone()[0]

        client_unpaid_count = c.execute("""
        SELECT COUNT(*)
        FROM tasks
        WHERE company_id=?
          AND client_id=?
          AND payment_status IN ('Не оплачено', 'unpaid', 'not_paid')
        """, (
            company_id,
            client_id,
        )).fetchone()[0]

    if mode == "priority_high":
        if priority in ("срочно", "высокий", "urgent", "high"):
            return True, ""

    elif mode == "emergency":
        if priority in ("срочно", "urgent", "emergency"):
            return True, ""

    elif mode == "task_text_contains":
        keyword = str(conditions.get("value") or "").strip().lower()
        if keyword and keyword in task_search_text:
            return True, ""

    elif mode == "status_new":
        if status in ("новая", "new"):
            return True, ""

    elif mode == "status_in_progress":
        if status in ("в работе", "in_progress", "working"):
            return True, ""

    elif mode == "status_done":
        if status in ("завершено", "done", "completed"):
            return True, ""

    elif mode == "payment_unpaid":
        if payment_status in ("не оплачено", "unpaid", "not_paid"):
            return True, ""

    elif mode == "payment_partial":
        if payment_status in ("частично оплачено", "partial", "partially_paid"):
            return True, ""

    elif mode == "payment_paid":
        if payment_status in ("оплачено", "paid"):
            return True, ""

    elif mode == "worker_assigned":
        if get_task_worker_names(task):
            return True, ""

    elif mode == "worker_specific":
        selected_worker = str(conditions.get("value") or "").strip()
        if selected_worker and task_has_worker(selected_worker, task):
            return True, ""

    elif mode == "date_today":
        if task_date == today:
            return True, ""

    elif mode == "date_overdue":
        if task_date and task_date < today and status not in ("завершено", "done", "completed", "отменено", "cancelled"):
            return True, ""

    elif mode == "date_future":
        if task_date and task_date > today:
            return True, ""

    elif mode == "price_high":
        if task_price >= price_threshold:
            return True, ""

    elif mode == "price_missing":
        if task_price <= 0:
            return True, ""

    elif mode == "catalog_specific":
        try:
            selected_catalog_item_id = int(conditions.get("value"))
        except (TypeError, ValueError):
            selected_catalog_item_id = 0

        if selected_catalog_item_id:
            task_item = c.execute("""
            SELECT 1
            FROM task_items
            WHERE company_id=?
              AND task_id=?
              AND catalog_item_id=?
            LIMIT 1
            """, (
                company_id,
                entity_id,
                selected_catalog_item_id,
            )).fetchone()

            if task_item:
                return True, ""

    elif mode == "sla_today":
        if deadline_date == today:
            return True, ""

    elif mode == "sla_overdue":
        if deadline_at and deadline_at < today_dt.isoformat(timespec="minutes") and status not in ("завершено", "done", "completed", "отменено", "cancelled"):
            return True, ""

    elif mode == "sla_due_24h":
        if deadline_at and status not in ("завершено", "done", "completed", "отменено", "cancelled"):
            try:
                deadline_dt = datetime.fromisoformat(deadline_at.replace("Z", "+00:00").replace("+00:00", ""))
                if today_dt <= deadline_dt <= next_24h:
                    return True, ""
            except Exception:
                pass

    elif mode == "client_specific":
        try:
            selected_client_id = int(conditions.get("value"))
        except (TypeError, ValueError):
            selected_client_id = 0

        if client and selected_client_id and client_id == selected_client_id:
            return True, ""

    elif mode == "client_new":
        if client_task_count <= 1:
            return True, ""

    elif mode == "client_repeat":
        if client_task_count >= 2:
            return True, ""

    elif mode == "client_vip":
        client_notes = str(client["notes"] or "").lower() if client else ""
        if "vip" in client_notes or "вип" in client_notes:
            return True, ""

    elif mode == "client_has_debt":
        if client_unpaid_count > 0:
            return True, ""

    elif mode == "client_many_tasks":
        if client_task_count >= client_task_threshold:
            return True, ""

    else:
        return False, f"Условие не поддерживается: {mode}"

    return False, f"Условие не выполнено: {conditions.get('label') or mode}"


def run_automation_event(
    company_id,
    trigger_key,
    entity_type="",
    entity_id=None,
    message="",
    link=""
):
    company_id = company_id or 1

    if not has_feature(company_id, "automation"):
        return 0

    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    created_events = 0

    conn = connect()
    c = conn.cursor()

    rules = c.execute("""
    SELECT *
    FROM automation_rules
    WHERE company_id=?
      AND trigger_key=?
      AND active=1
    ORDER BY id
    """, (company_id, trigger_key)).fetchall()

    for rule in rules:
        condition_ok, condition_message = automation_condition_matches(
            c,
            company_id,
            rule,
            entity_type,
            entity_id,
        )

        if not condition_ok:
            skipped_message = condition_message

            if message:
                skipped_message = f"{condition_message}. Событие: {message}"

            c.execute("""
            INSERT INTO automation_events (
                company_id, rule_id, trigger_key, entity_type,
                entity_id, status, message, created_at, processed_at
            )
            VALUES (?, ?, ?, ?, ?, 'skipped', ?, ?, ?)
            """, (
                company_id,
                rule["id"],
                trigger_key,
                entity_type,
                entity_id,
                skipped_message,
                now,
                now,
            ))
            continue

        c.execute("""
        INSERT INTO automation_events (
            company_id, rule_id, trigger_key, entity_type,
            entity_id, status, message, created_at
        )
        VALUES (?, ?, ?, ?, ?, 'pending', ?, ?)
        """, (
            company_id,
            rule["id"],
            trigger_key,
            entity_type,
            entity_id,
            message,
            now
        ))

        event_id = c.lastrowid
        handled_actions = 0

        actions = c.execute("""
        SELECT *
        FROM automation_actions
        WHERE company_id=?
          AND rule_id=?
          AND active=1
        ORDER BY sort_order, id
        """, (company_id, rule["id"])).fetchall()

        for action in actions:
            try:
                payload = json.loads(action["payload_json"] or "{}")
            except Exception:
                payload = {}

            if action["action_key"] == "notification":
                target_username = (payload.get("target_username") or rule["created_by"] or "").strip()
                notification_message = (payload.get("message") or message or "").strip()

                if target_username:
                    c.execute("""
                    INSERT INTO notifications (
                        company_id, username, title, message, link, created_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?)
                    """, (
                        company_id,
                        target_username,
                        rule["name"],
                        notification_message,
                        link,
                        now
                    ))
                    handled_actions += 1

            if action["action_key"] == "telegram_alert":
                target_username = (payload.get("target_username") or rule["created_by"] or "").strip()
                telegram_message = (payload.get("message") or message or "").strip()

                if target_username and telegram_message:
                    user_row = c.execute("""
                    SELECT telegram_chat_id
                    FROM users
                    WHERE company_id=?
                      AND username=?
                    """, (company_id, target_username)).fetchone()

                    if user_row and user_row["telegram_chat_id"]:
                        try:
                            send_message_to_chat(
                                user_row["telegram_chat_id"],
                                telegram_message
                            )
                            handled_actions += 1
                        except Exception:
                            pass

            if action["action_key"] == "ai_digest":
                target_username = (payload.get("target_username") or rule["created_by"] or "").strip()

                if target_username:
                    digest_message = build_ai_digest_message(company_id, c)

                    c.execute("""
                    INSERT INTO notifications (
                        company_id, username, title, message, link, created_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?)
                    """, (
                        company_id,
                        target_username,
                        "🤖 AI-сводка",
                        digest_message,
                        "/ai/insights",
                        now
                    ))

                    handled_actions += 1

                    user_row = c.execute("""
                    SELECT telegram_chat_id
                    FROM users
                    WHERE company_id=?
                      AND username=?
                    """, (company_id, target_username)).fetchone()

                    if user_row and user_row["telegram_chat_id"]:
                        try:
                            send_message_to_chat(
                                user_row["telegram_chat_id"],
                                digest_message
                            )
                        except Exception:
                            pass

            if action["action_key"] == "create_task":
                created_task_id = execute_automation_create_task_action(
                    c,
                    company_id,
                    rule,
                    action,
                    payload,
                    entity_type,
                    entity_id,
                    now,
                )

                if created_task_id:
                    handled_actions += 1

        status = "done" if handled_actions else "skipped"

        c.execute("""
        UPDATE automation_events
        SET status=?, processed_at=?
        WHERE id=?
          AND company_id=?
        """, (
            status,
            now,
            event_id,
            company_id
        ))

        created_events += 1

    conn.commit()
    conn.close()

    return created_events


def run_ai_digest_scheduler(company_id, now_dt=None):
    company_id = company_id or 1

    result = {
        "daily": 0,
        "weekly": 0,
        "follow_ups": 0,
        "skipped": 0
    }

    if not has_feature(company_id, "automation") or not has_feature(company_id, "ai_insights"):
        return result

    now_dt = now_dt or datetime.now()
    today_key = now_dt.strftime("%Y-%m-%d")
    iso_year, iso_week, _ = now_dt.isocalendar()
    week_key = f"{iso_year}-W{iso_week:02d}"
    daily_message = f"Ежедневная AI-сводка {today_key}"

    conn = connect()
    c = conn.cursor()

    daily_rules = c.execute("""
    SELECT COUNT(*)
    FROM automation_rules
    WHERE company_id=?
      AND trigger_key='daily_digest'
      AND active=1
    """, (company_id,)).fetchone()[0]

    weekly_rules = c.execute("""
    SELECT COUNT(*)
    FROM automation_rules
    WHERE company_id=?
      AND trigger_key='weekly_digest'
      AND active=1
    """, (company_id,)).fetchone()[0]

    daily_already_sent = c.execute("""
    SELECT COUNT(*)
    FROM automation_events
    WHERE company_id=?
      AND trigger_key='daily_digest'
      AND message=?
    """, (company_id, daily_message)).fetchone()[0]

    weekly_message = f"Еженедельная AI-сводка {week_key}"
    weekly_already_sent = c.execute("""
    SELECT COUNT(*)
    FROM automation_events
    WHERE company_id=?
      AND trigger_key='weekly_digest'
      AND message=?
    """, (company_id, weekly_message)).fetchone()[0]

    conn.close()

    result["follow_ups"] = create_ai_follow_up_notifications_for_company(
        company_id,
        now_dt
    )

    if daily_rules and not daily_already_sent:
        result["daily"] = run_automation_event(
            company_id,
            "daily_digest",
            "company",
            company_id,
            daily_message,
            "/ai/insights"
        )
    elif daily_rules:
        result["skipped"] += 1

    if weekly_rules and not weekly_already_sent:
        result["weekly"] = run_automation_event(
            company_id,
            "weekly_digest",
            "company",
            company_id,
            weekly_message,
            "/ai/insights"
        )
    elif weekly_rules:
        result["skipped"] += 1

    return result


def run_ai_digest_scheduler_for_all_companies(now_dt=None):
    summary = {
        "companies": 0,
        "daily": 0,
        "weekly": 0,
        "follow_ups": 0,
        "skipped": 0
    }

    conn = connect()
    c = conn.cursor()

    companies = c.execute("""
    SELECT id
    FROM companies
    ORDER BY id
    """).fetchall()

    conn.close()

    for company in companies:
        result = run_ai_digest_scheduler(company["id"], now_dt)
        summary["companies"] += 1
        summary["daily"] += result["daily"]
        summary["weekly"] += result["weekly"]
        summary["follow_ups"] += result["follow_ups"]
        summary["skipped"] += result["skipped"]

    return summary


def ensure_ai_digest_automation_rules(company_id, username):
    company_id = company_id or 1
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    created_count = 0
    defaults = [
        ("daily_digest", "Ежедневная AI-сводка"),
        ("weekly_digest", "Еженедельная AI-сводка")
    ]

    conn = connect()
    c = conn.cursor()

    for trigger_key, name in defaults:
        existing = c.execute("""
        SELECT automation_rules.id
        FROM automation_rules
        JOIN automation_actions
          ON automation_actions.rule_id=automation_rules.id
          AND automation_actions.company_id=automation_rules.company_id
        WHERE automation_rules.company_id=?
          AND automation_rules.trigger_key=?
          AND automation_actions.action_key='ai_digest'
        LIMIT 1
        """, (company_id, trigger_key)).fetchone()

        if existing:
            continue

        c.execute("""
        INSERT INTO automation_rules (
            company_id, name, trigger_key, conditions_json,
            active, created_by, created_at, updated_at
        )
        VALUES (?, ?, ?, ?, 1, ?, ?, ?)
        """, (
            company_id,
            name,
            trigger_key,
            json.dumps({}, ensure_ascii=False),
            username,
            now,
            now
        ))

        rule_id = c.lastrowid
        payload = {
            "target_username": username,
            "message": ""
        }

        c.execute("""
        INSERT INTO automation_actions (
            company_id, rule_id, action_key, payload_json,
            sort_order, active, created_at
        )
        VALUES (?, ?, 'ai_digest', ?, 1, 1, ?)
        """, (
            company_id,
            rule_id,
            json.dumps(payload, ensure_ascii=False),
            now
        ))

        created_count += 1

    conn.commit()
    conn.close()

    return created_count


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
    ensure_company_features(company_id)

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
    features = get_company_features(company_id)

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

    settings = get_company_settings(company_id)

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
            "search": search,
            "features": features,
            "settings": settings
        }
    )


@app.get("/notifications", response_class=HTMLResponse)
async def notifications_page(request: Request):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)
    company_id = get_user_company_id(username)
    disabled_response = require_feature(company_id, "notifications")

    if disabled_response:
        return disabled_response

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



@app.get("/automation/workflows", response_class=HTMLResponse)
def automation_workflows_page(request: Request):
    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role not in ("boss", "manager"):
        return RedirectResponse("/", status_code=302)

    company_id = get_user_company_id(username)
    disabled_response = require_feature(company_id, "automation")

    if disabled_response:
        return disabled_response

    return templates.TemplateResponse(
        request,
        "automation_workflows.html",
        {
            "request": request,
            "username": username,
            "role": role,
        },
    )


@app.get("/automation", response_class=HTMLResponse)
async def automation_page(
    request: Request,
    rule_filter: str = "",
    event_filter: str = "",
    trigger_filter: str = "",
    rule_trigger_filter: str = "",
    rule_action_filter: str = "",
    rule_search: str = "",
    event_search: str = "",
    event_entity_filter: str = "",
    event_date_from: str = "",
    event_date_to: str = ""
):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role not in ("boss", "manager"):
        return RedirectResponse("/", status_code=302)

    company_id = get_user_company_id(username)
    disabled_response = require_feature(company_id, "automation")

    if disabled_response:
        return disabled_response

    trigger_labels = dict(AUTOMATION_TRIGGERS)
    action_labels = dict(AUTOMATION_ACTIONS)
    status_labels = AUTOMATION_STATUS_LABELS
    entity_labels = {
        "task": "Заявка",
        "client": "Клиент",
        "company": "Компания"
    }
    selected_rule_filter = rule_filter if rule_filter in ("active", "disabled") else ""
    selected_event_filter = event_filter if event_filter in ("pending", "done", "skipped") else ""
    trigger_keys = {key for key, _ in AUTOMATION_TRIGGERS}
    action_keys = {key for key, _ in AUTOMATION_ACTIONS}
    selected_trigger_filter = trigger_filter if trigger_filter in trigger_keys else ""
    selected_rule_trigger_filter = rule_trigger_filter if rule_trigger_filter in trigger_keys else ""
    selected_rule_action_filter = rule_action_filter if rule_action_filter in action_keys else ""
    selected_rule_search = (rule_search or "").strip()[:80]
    selected_event_search = (event_search or "").strip()[:80]
    selected_event_entity_filter = event_entity_filter if event_entity_filter in entity_labels else ""
    selected_event_date_from = (event_date_from or "").strip()[:10]
    selected_event_date_to = (event_date_to or "").strip()[:10]
    event_filter_sql = ""
    event_params = [company_id]

    for selected_date in (selected_event_date_from, selected_event_date_to):
        if selected_date:
            try:
                datetime.strptime(selected_date, "%Y-%m-%d")
            except ValueError:
                selected_event_date_from = ""
                selected_event_date_to = ""
                break

    if selected_event_filter:
        event_filter_sql = "AND automation_events.status=?"
        event_params.append(selected_event_filter)

    if selected_trigger_filter:
        event_filter_sql += "\n      AND automation_events.trigger_key=?"
        event_params.append(selected_trigger_filter)

    if selected_event_entity_filter:
        event_filter_sql += "\n      AND automation_events.entity_type=?"
        event_params.append(selected_event_entity_filter)

    if selected_event_search:
        event_filter_sql += """
      AND (
        automation_events.message LIKE ?
        OR automation_rules.name LIKE ?
      )
        """
        event_params.extend([
            f"%{selected_event_search}%",
            f"%{selected_event_search}%"
        ])

    if selected_event_date_from:
        event_filter_sql += "\n      AND substr(automation_events.created_at, 1, 10) >= ?"
        event_params.append(selected_event_date_from)

    if selected_event_date_to:
        event_filter_sql += "\n      AND substr(automation_events.created_at, 1, 10) <= ?"
        event_params.append(selected_event_date_to)

    conn = connect()
    c = conn.cursor()

    rule_rows = c.execute("""
    SELECT
        automation_rules.*,
        COUNT(automation_actions.id) AS action_count,
        GROUP_CONCAT(automation_actions.action_key) AS action_keys,
        (
            SELECT action_key
            FROM automation_actions
            WHERE company_id=automation_rules.company_id
              AND rule_id=automation_rules.id
            ORDER BY sort_order, id
            LIMIT 1
        ) AS primary_action_key,
        (
            SELECT payload_json
            FROM automation_actions
            WHERE company_id=automation_rules.company_id
              AND rule_id=automation_rules.id
            ORDER BY sort_order, id
            LIMIT 1
        ) AS primary_payload_json
    FROM automation_rules
    LEFT JOIN automation_actions
      ON automation_actions.rule_id=automation_rules.id
      AND automation_actions.company_id=automation_rules.company_id
    WHERE automation_rules.company_id=?
    GROUP BY automation_rules.id
    ORDER BY automation_rules.id DESC
    """, (company_id,)).fetchall()

    events = c.execute(f"""
    SELECT
        automation_events.*,
        automation_rules.name AS rule_name
    FROM automation_events
    LEFT JOIN automation_rules
      ON automation_rules.id=automation_events.rule_id
      AND automation_rules.company_id=automation_events.company_id
    WHERE automation_events.company_id=?
      {event_filter_sql}
    ORDER BY automation_events.id DESC
    LIMIT 30
    """, event_params).fetchall()

    event_count_rows = c.execute("""
    SELECT status, COUNT(*) AS count
    FROM automation_events
    WHERE company_id=?
    GROUP BY status
    """, (company_id,)).fetchall()
    event_counts = {row["status"]: row["count"] for row in event_count_rows}

    last_event_at = c.execute("""
    SELECT MAX(created_at)
    FROM automation_events
    WHERE company_id=?
    """, (company_id,)).fetchone()[0] or ""

    today_key = datetime.now().strftime("%Y-%m-%d")
    events_today = c.execute("""
    SELECT COUNT(*)
    FROM automation_events
    WHERE company_id=?
      AND substr(created_at, 1, 10)=?
    """, (company_id, today_key)).fetchone()[0] or 0

    users = c.execute("""
    SELECT username, role
    FROM users
    WHERE company_id=?
    ORDER BY role, username
    """, (company_id,)).fetchall()

    conn.close()

    rules = []
    unhealthy_rules = []

    for rule_row in rule_rows:
        rule = dict(rule_row)

        health_issues = []

        if not rule.get("active", 1):
            health_issues.append("Правило отключено")

        if not rule.get("action_count"):
            health_issues.append("Действия не настроены")

        if (rule.get("success_rate") or 100) < 60:
            health_issues.append("Низкая успешность")

        if (rule.get("skipped_runs") or 0) >= 5:
            health_issues.append("Много пропущенных запусков")

        if health_issues:
            unhealthy_rules.append({
                "id": rule.get("id"),
                "name": rule.get("name"),
                "issues": health_issues,
            })

        try:
            payload = json.loads(rule.get("primary_payload_json") or "{}")
        except Exception:
            payload = {}

        rule["edit_target_username"] = payload.get("target_username") or rule["created_by"] or username
        rule["edit_message"] = payload.get("message") or ""
        rules.append(rule)

    success_rate = round(
        event_counts.get("done", 0) / max(
            event_counts.get("done", 0) + event_counts.get("skipped", 0),
            1
        ) * 100,
        1
    )

    pending_count = event_counts.get("pending", 0)
    done_count = event_counts.get("done", 0)
    skipped_count = event_counts.get("skipped", 0)

    if pending_count > 5 or skipped_count > done_count:
        health_status = "problem"
        health_title = "Проблема"
        health_message = "Есть много ожидающих или пропущенных событий. Нужно проверить правила автоматизации."
    elif pending_count > 0 or skipped_count > 0 or success_rate < 80:
        health_status = "warning"
        health_title = "Нужно внимание"
        health_message = "Автоматизация работает, но есть события, которые требуют проверки."
    else:
        health_status = "ok"
        health_title = "OK"
        health_message = "Автоматизация работает стабильно."

    automation_stats = {
        "rules_total": len(rules),
        "rules_active": len([rule for rule in rules if rule["active"]]),
        "rules_disabled": len([rule for rule in rules if not rule["active"]]),
        "events_total": sum(event_counts.values()),
        "events_pending": pending_count,
        "events_done": done_count,
        "events_skipped": skipped_count,
        "events_today": events_today,
        "success_rate": success_rate,
        "last_event_at": last_event_at,
        "health_status": health_status,
        "health_title": health_title,
        "health_message": health_message
    }

    if selected_rule_filter == "active":
        rules = [rule for rule in rules if rule["active"]]
    elif selected_rule_filter == "disabled":
        rules = [rule for rule in rules if not rule["active"]]

    if selected_rule_trigger_filter:
        rules = [rule for rule in rules if rule["trigger_key"] == selected_rule_trigger_filter]

    if selected_rule_action_filter:
        rules = [
            rule for rule in rules
            if selected_rule_action_filter in (rule["action_keys"] or "").split(",")
        ]

    if selected_rule_search:
        rule_search_lower = selected_rule_search.lower()
        rules = [
            rule for rule in rules
            if rule_search_lower in (rule["name"] or "").lower()
            or rule_search_lower in (rule["edit_message"] or "").lower()
        ]

    return templates.TemplateResponse(
        request,
        "automation.html",
        {
            "request": request,
            "username": username,
            "role": role,
            "rules": rules,
            "unhealthy_rules": unhealthy_rules,
            "events": events,
            "shown_events_count": len(events),
            "users": users,
            "triggers": AUTOMATION_TRIGGERS,
            "actions": AUTOMATION_ACTIONS,
            "trigger_labels": trigger_labels,
            "action_labels": action_labels,
            "status_labels": status_labels,
            "entity_labels": entity_labels,
            "selected_rule_filter": selected_rule_filter,
            "selected_event_filter": selected_event_filter,
            "selected_trigger_filter": selected_trigger_filter,
            "selected_rule_trigger_filter": selected_rule_trigger_filter,
            "selected_rule_action_filter": selected_rule_action_filter,
            "selected_rule_search": selected_rule_search,
            "selected_event_search": selected_event_search,
            "selected_event_entity_filter": selected_event_entity_filter,
            "selected_event_date_from": selected_event_date_from,
            "selected_event_date_to": selected_event_date_to,
            "automation_stats": automation_stats,
            "features": get_company_features(company_id)
        }
    )


@app.get("/automation/builder", response_class=HTMLResponse)
async def automation_builder_page(request: Request):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role not in ("boss", "manager"):
        return RedirectResponse("/", status_code=302)

    company_id = get_user_company_id(username)
    disabled_response = require_feature(company_id, "automation")

    if disabled_response:
        return disabled_response

    conn = connect()
    c = conn.cursor()

    rules = c.execute("""
    SELECT
        automation_rules.*,
        COUNT(automation_actions.id) AS action_count
    FROM automation_rules
    LEFT JOIN automation_actions
      ON automation_actions.rule_id=automation_rules.id
      AND automation_actions.company_id=automation_rules.company_id
    WHERE automation_rules.company_id=?
    GROUP BY automation_rules.id
    ORDER BY automation_rules.id DESC
    LIMIT 50
    """, (company_id,)).fetchall()

    actions = c.execute("""
    SELECT *
    FROM automation_actions
    WHERE company_id=?
    ORDER BY rule_id, sort_order, id
    """, (company_id,)).fetchall()

    workers = c.execute("""
    SELECT username, full_name
    FROM users
    WHERE company_id=?
      AND role='worker'
    ORDER BY COALESCE(NULLIF(full_name, ''), username), username
    """, (company_id,)).fetchall()

    clients = c.execute("""
    SELECT id, name, phone
    FROM clients
    WHERE company_id=?
    ORDER BY name, id
    """, (company_id,)).fetchall()

    catalog_items = c.execute("""
    SELECT id, name, item_type
    FROM catalog_items
    WHERE company_id=?
      AND active=1
    ORDER BY item_type, name, id
    """, (company_id,)).fetchall()

    test_tasks = c.execute("""
    SELECT id, client, status, task_date
    FROM tasks
    WHERE company_id=?
      AND archived=0
    ORDER BY task_date DESC, id DESC
    LIMIT 100
    """, (company_id,)).fetchall()

    conn.close()

    actions_by_rule = {}

    for action in actions:
        actions_by_rule.setdefault(action["rule_id"], []).append(action)

    condition_presets = [
        ("none", "Без условий"),
        ("priority_high", "Только высокий приоритет"),
        ("emergency", "Только срочные заявки"),
        ("task_text_contains", "Текст заявки содержит"),
        ("status_new", "Только новые заявки"),
        ("status_in_progress", "Только заявки в работе"),
        ("status_done", "Только завершённые заявки"),
        ("payment_unpaid", "Только неоплаченные заявки"),
        ("payment_partial", "Только частично оплаченные заявки"),
        ("payment_paid", "Только оплаченные заявки"),
        ("worker_assigned", "Только задачи с исполнителем"),
        ("worker_specific", "Только выбранный исполнитель"),
        ("date_today", "Только задачи на сегодня"),
        ("date_overdue", "Только просроченные задачи"),
        ("date_future", "Только будущие задачи"),
        ("price_high", "Только дорогие заявки"),
        ("price_missing", "Только заявки без цены"),
        ("catalog_specific", "Только выбранная позиция каталога"),
        ("sla_today", "Только дедлайн сегодня"),
        ("sla_overdue", "Только просроченный SLA"),
        ("sla_due_24h", "Только дедлайн в ближайшие 24 часа"),
        ("client_specific", "Только выбранный клиент"),
        ("client_new", "Только новые клиенты"),
        ("client_repeat", "Только постоянные клиенты"),
        ("client_vip", "Только VIP клиенты"),
        ("client_has_debt", "Только клиенты с долгом"),
        ("client_many_tasks", "Только клиенты с большим количеством заявок"),
    ]
    condition_groups = [
        ("Базовые", condition_presets[:4]),
        ("Статус заявки", condition_presets[4:7]),
        ("Оплата", condition_presets[7:10]),
        ("Исполнители", condition_presets[10:12]),
        ("Дата", condition_presets[12:15]),
        ("Цена", condition_presets[15:17]),
        ("Каталог", condition_presets[17:18]),
        ("SLA", condition_presets[18:21]),
        ("Клиенты", condition_presets[21:]),
    ]
    condition_labels = dict(condition_presets)
    rules_view = []
    test_rule_id = str(request.query_params.get("test_rule_id") or "")
    test_task_id = str(request.query_params.get("test_task_id") or "")
    test_result = str(request.query_params.get("test_result") or "")

    try:
        test_rule_id = int(test_rule_id)
    except ValueError:
        test_rule_id = 0

    try:
        test_task_id = int(test_task_id)
    except ValueError:
        test_task_id = 0

    try:
        test_details = json.loads(
            str(request.query_params.get("test_details") or "[]")
        )
    except Exception:
        test_details = []

    if not isinstance(test_details, list):
        test_details = []

    try:
        batch_condition_stats = json.loads(
            str(request.query_params.get("batch_condition_stats") or "[]")
        )
    except Exception:
        batch_condition_stats = []

    if not isinstance(batch_condition_stats, list):
        batch_condition_stats = []

    batch_operator = str(
        request.query_params.get("batch_operator") or "and"
    ).lower()

    if batch_operator not in ("and", "or"):
        batch_operator = "and"

    try:
        batch_rejected = json.loads(
            str(request.query_params.get("batch_rejected") or "[]")
        )
    except Exception:
        batch_rejected = []

    if not isinstance(batch_rejected, list):
        batch_rejected = []

    batch_values = {}

    for key in (
        "batch_rule_id",
        "batch_total",
        "batch_matched",
        "batch_match_rate",
        "batch_limit",
    ):
        try:
            batch_values[key] = int(request.query_params.get(key) or 0)
        except (TypeError, ValueError):
            batch_values[key] = 0

    if batch_values["batch_limit"] not in (20, 50, 100):
        batch_values["batch_limit"] = 20

    batch_assessment = automation_condition_coverage_assessment(
        batch_values["batch_total"],
        batch_values["batch_matched"],
    )
    batch_focus = automation_condition_focus_assessment(
        batch_condition_stats,
        batch_operator,
    )

    batch_task_id_set = {
        value
        for value in str(
            request.query_params.get("batch_task_ids") or ""
        ).split(",")
        if value
    }
    batch_tasks = [
        dict(task)
        for task in test_tasks
        if str(task["id"]) in batch_task_id_set
    ]
    test_tasks_by_id = {
        int(task["id"]): dict(task)
        for task in test_tasks
    }
    batch_rejected_tasks = []

    for item in batch_rejected[:10]:
        if not isinstance(item, dict):
            continue

        try:
            rejected_task_id = int(item.get("id") or 0)
        except (TypeError, ValueError):
            continue

        task = test_tasks_by_id.get(rejected_task_id)

        if not task:
            continue

        failed_conditions = item.get("failed_conditions") or []

        if not isinstance(failed_conditions, list):
            failed_conditions = []

        task["failed_conditions"] = [
            str(label)[:120]
            for label in failed_conditions[:3]
        ]
        batch_rejected_tasks.append(task)

    for rule in rules:
        rule_data = dict(rule)

        try:
            conditions = json.loads(rule_data.get("conditions_json") or "{}")
        except Exception:
            conditions = {}

        condition_items = conditions.get("conditions") or []
        condition_mode = conditions.get("mode") or (
            condition_items[0].get("mode") if condition_items else "none"
        )
        condition_secondary_mode = (
            condition_items[1].get("mode")
            if len(condition_items) > 1
            else "none"
        )
        condition_tertiary_mode = (
            condition_items[2].get("mode")
            if len(condition_items) > 2
            else "none"
        )
        condition_operator = str(conditions.get("operator") or "and").lower()
        condition_value = str(
            (condition_items[0] if condition_items else conditions).get("value") or ""
        )
        condition_secondary_value = str(
            condition_items[1].get("value") or ""
            if len(condition_items) > 1
            else ""
        )
        condition_tertiary_value = str(
            condition_items[2].get("value") or ""
            if len(condition_items) > 2
            else ""
        )

        if condition_mode not in condition_labels:
            condition_mode = "none"

        if condition_secondary_mode not in condition_labels:
            condition_secondary_mode = "none"

        if condition_tertiary_mode not in condition_labels:
            condition_tertiary_mode = "none"

        if condition_operator not in ("and", "or"):
            condition_operator = "and"

        rule_data["condition_mode"] = condition_mode
        rule_data["condition_secondary_mode"] = condition_secondary_mode
        rule_data["condition_tertiary_mode"] = condition_tertiary_mode
        rule_data["condition_operator"] = condition_operator
        rule_data["condition_value"] = (
            condition_value
            if condition_mode in ("price_high", "client_many_tasks")
            else ""
        )
        rule_data["condition_secondary_value"] = (
            condition_secondary_value
            if condition_secondary_mode in ("price_high", "client_many_tasks")
            else ""
        )
        rule_data["condition_tertiary_value"] = (
            condition_tertiary_value
            if condition_tertiary_mode in ("price_high", "client_many_tasks")
            else ""
        )
        rule_data["condition_worker"] = (
            condition_value if condition_mode == "worker_specific" else ""
        )
        rule_data["condition_secondary_worker"] = (
            condition_secondary_value
            if condition_secondary_mode == "worker_specific"
            else ""
        )
        rule_data["condition_tertiary_worker"] = (
            condition_tertiary_value
            if condition_tertiary_mode == "worker_specific"
            else ""
        )
        rule_data["condition_client"] = (
            condition_value if condition_mode == "client_specific" else ""
        )
        rule_data["condition_secondary_client"] = (
            condition_secondary_value
            if condition_secondary_mode == "client_specific"
            else ""
        )
        rule_data["condition_tertiary_client"] = (
            condition_tertiary_value
            if condition_tertiary_mode == "client_specific"
            else ""
        )
        rule_data["condition_catalog"] = (
            condition_value if condition_mode == "catalog_specific" else ""
        )
        rule_data["condition_secondary_catalog"] = (
            condition_secondary_value
            if condition_secondary_mode == "catalog_specific"
            else ""
        )
        rule_data["condition_tertiary_catalog"] = (
            condition_tertiary_value
            if condition_tertiary_mode == "catalog_specific"
            else ""
        )
        rule_data["condition_text"] = (
            condition_value if condition_mode == "task_text_contains" else ""
        )
        rule_data["condition_secondary_text"] = (
            condition_secondary_value
            if condition_secondary_mode == "task_text_contains"
            else ""
        )
        rule_data["condition_tertiary_text"] = (
            condition_tertiary_value
            if condition_tertiary_mode == "task_text_contains"
            else ""
        )

        condition_payloads = (
            condition_items
            if condition_items
            else [conditions]
        )
        selected_condition_labels = []

        for index, mode in enumerate((
            condition_mode,
            condition_secondary_mode,
            condition_tertiary_mode,
        )):
            if mode == "none":
                continue

            payload = condition_payloads[index] if index < len(condition_payloads) else {}
            selected_condition_labels.append(
                payload.get("label") or condition_labels[mode]
            )

        if len(selected_condition_labels) > 1:
            separator = " и " if condition_operator == "and" else " или "
            rule_data["condition_label"] = separator.join(selected_condition_labels)
        elif selected_condition_labels:
            rule_data["condition_label"] = selected_condition_labels[0]
        else:
            rule_data["condition_label"] = condition_labels["none"]

        rule_actions = actions_by_rule.get(rule_data["id"], [])
        rule_data["dry_run"] = {}

        if (
            test_rule_id == rule_data["id"]
            and test_result in ("match", "no_match")
        ):
            rule_data["dry_run"] = automation_dry_run_readiness(
                bool(rule_data["active"]),
                test_result == "match",
                rule_actions,
            )

        rules_view.append(rule_data)

    return templates.TemplateResponse(
        request,
        "automation_builder.html",
        {
            "request": request,
            "username": username,
            "role": role,
            "rules": rules_view,
            "actions_by_rule": actions_by_rule,
            "trigger_labels": dict(AUTOMATION_TRIGGERS),
            "action_labels": dict(AUTOMATION_ACTIONS),
            "condition_presets": condition_presets,
            "condition_groups": condition_groups,
            "workers": workers,
            "clients": clients,
            "catalog_items": catalog_items,
            "test_tasks": test_tasks,
            "test_rule_id": test_rule_id,
            "test_task_id": test_task_id,
            "test_result": test_result,
            "test_message": str(request.query_params.get("test_message") or ""),
            "test_operator": str(request.query_params.get("test_operator") or ""),
            "test_details": test_details,
            "batch_rule_id": batch_values["batch_rule_id"],
            "batch_total": batch_values["batch_total"],
            "batch_matched": batch_values["batch_matched"],
            "batch_match_rate": batch_values["batch_match_rate"],
            "batch_limit": batch_values["batch_limit"],
            "batch_tasks": batch_tasks,
            "batch_rejected_tasks": batch_rejected_tasks,
            "batch_condition_stats": batch_condition_stats,
            "batch_assessment": batch_assessment,
            "batch_focus": batch_focus,
        }
    )


@app.post("/automation/rules/{rule_id}/test-condition")
async def test_automation_rule_condition(request: Request, rule_id: int):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role not in ("boss", "manager"):
        return RedirectResponse("/", status_code=302)

    company_id = get_user_company_id(username)
    disabled_response = require_feature(company_id, "automation")

    if disabled_response:
        return disabled_response

    form = await request.form()

    try:
        task_id = int(form.get("task_id") or 0)
    except (TypeError, ValueError):
        task_id = 0

    conn = connect()
    c = conn.cursor()

    rule = c.execute("""
    SELECT *
    FROM automation_rules
    WHERE id=?
      AND company_id=?
    """, (rule_id, company_id)).fetchone()

    task = c.execute("""
    SELECT id
    FROM tasks
    WHERE id=?
      AND company_id=?
      AND archived=0
    """, (task_id, company_id)).fetchone()

    if not rule or not task:
        conn.close()
        params = {
            "test_rule_id": rule_id,
            "test_task_id": task_id,
            "test_result": "error",
            "test_message": "Правило или заявка не найдены",
        }
        return RedirectResponse(
            f"/automation/builder?{urlencode(params)}",
            status_code=302,
        )

    diagnostics = automation_condition_diagnostics(
        c,
        company_id,
        rule,
        "task",
        task_id,
    )
    conn.close()

    condition_ok = diagnostics["matched"]
    failed_messages = [
        item["message"]
        for item in diagnostics["details"]
        if not item["matched"]
    ]
    params = {
        "test_rule_id": rule_id,
        "test_task_id": task_id,
        "test_result": "match" if condition_ok else "no_match",
        "test_message": (
            "Условия выполнены, правило может сработать"
            if condition_ok
            else ("; ".join(failed_messages) or "Условия не выполнены")[:180]
        ),
        "test_operator": diagnostics["operator_label"],
        "test_details": json.dumps(
            diagnostics["details"],
            ensure_ascii=False,
            separators=(",", ":"),
        ),
    }

    return RedirectResponse(
        f"/automation/builder?{urlencode(params)}",
        status_code=302,
    )


@app.post("/automation/rules/{rule_id}/test-condition-batch")
async def test_automation_rule_condition_batch(request: Request, rule_id: int):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role not in ("boss", "manager"):
        return RedirectResponse("/", status_code=302)

    company_id = get_user_company_id(username)
    disabled_response = require_feature(company_id, "automation")

    if disabled_response:
        return disabled_response

    form = await request.form()

    try:
        batch_limit = int(form.get("batch_limit") or 20)
    except (TypeError, ValueError):
        batch_limit = 20

    if batch_limit not in (20, 50, 100):
        batch_limit = 20

    conn = connect()
    c = conn.cursor()

    rule = c.execute("""
    SELECT *
    FROM automation_rules
    WHERE id=?
      AND company_id=?
    """, (rule_id, company_id)).fetchone()

    task_rows = c.execute("""
    SELECT id
    FROM tasks
    WHERE company_id=?
      AND archived=0
    ORDER BY task_date DESC, id DESC
    LIMIT ?
    """, (company_id, batch_limit)).fetchall()

    if not rule:
        conn.close()
        return RedirectResponse(
            "/automation/builder?batch_error=1",
            status_code=302,
        )

    summary = automation_condition_batch_summary(
        c,
        company_id,
        rule,
        [row["id"] for row in task_rows],
    )
    conn.close()

    params = {
        "batch_rule_id": rule_id,
        "batch_total": summary["total"],
        "batch_matched": summary["matched"],
        "batch_match_rate": summary["match_rate"],
        "batch_limit": batch_limit,
        "batch_task_ids": ",".join(
            str(task_id) for task_id in summary["matched_task_ids"]
        ),
        "batch_condition_stats": json.dumps(
            summary["condition_stats"],
            ensure_ascii=False,
            separators=(",", ":"),
        ),
        "batch_operator": summary["operator"],
        "batch_rejected": json.dumps(
            summary["rejected_tasks"],
            ensure_ascii=False,
            separators=(",", ":"),
        ),
    }

    return RedirectResponse(
        f"/automation/builder?{urlencode(params)}",
        status_code=302,
    )


@app.get("/automation/rules/export")
async def automation_rules_export(
    request: Request,
    rule_filter: str = "",
    rule_trigger_filter: str = "",
    rule_action_filter: str = "",
    rule_search: str = ""
):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role not in ("boss", "manager"):
        return RedirectResponse("/", status_code=302)

    company_id = get_user_company_id(username)
    disabled_response = require_feature(company_id, "automation")

    if disabled_response:
        return disabled_response

    selected_rule_filter = rule_filter if rule_filter in ("active", "disabled") else ""
    trigger_keys = {key for key, _ in AUTOMATION_TRIGGERS}
    action_keys = {key for key, _ in AUTOMATION_ACTIONS}
    selected_rule_trigger_filter = rule_trigger_filter if rule_trigger_filter in trigger_keys else ""
    selected_rule_action_filter = rule_action_filter if rule_action_filter in action_keys else ""
    selected_rule_search = (rule_search or "").strip()[:80]
    rule_filter_sql = ""
    rule_params = [company_id]

    if selected_rule_filter == "active":
        rule_filter_sql = "AND automation_rules.active=1"
    elif selected_rule_filter == "disabled":
        rule_filter_sql = "AND automation_rules.active=0"

    if selected_rule_trigger_filter:
        rule_filter_sql += "\n      AND automation_rules.trigger_key=?"
        rule_params.append(selected_rule_trigger_filter)

    if selected_rule_action_filter:
        rule_filter_sql += """
      AND EXISTS (
          SELECT 1
          FROM automation_actions action_filter
          WHERE action_filter.company_id=automation_rules.company_id
            AND action_filter.rule_id=automation_rules.id
            AND action_filter.action_key=?
      )
        """
        rule_params.append(selected_rule_action_filter)

    if selected_rule_search:
        rule_filter_sql += """
      AND (
        automation_rules.name LIKE ?
        OR EXISTS (
            SELECT 1
            FROM automation_actions search_actions
            WHERE search_actions.company_id=automation_rules.company_id
              AND search_actions.rule_id=automation_rules.id
              AND search_actions.payload_json LIKE ?
        )
      )
        """
        rule_params.extend([
            f"%{selected_rule_search}%",
            f"%{selected_rule_search}%"
        ])

    conn = connect()
    c = conn.cursor()

    rules = c.execute(f"""
    SELECT
        automation_rules.*,
        COUNT(automation_actions.id) AS action_count,
        GROUP_CONCAT(automation_actions.action_key) AS action_keys
    FROM automation_rules
    LEFT JOIN automation_actions
      ON automation_actions.rule_id=automation_rules.id
      AND automation_actions.company_id=automation_rules.company_id
    WHERE automation_rules.company_id=?
      {rule_filter_sql}
    GROUP BY automation_rules.id
    ORDER BY automation_rules.id DESC
    """, rule_params).fetchall()

    conn.close()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "id",
        "name",
        "trigger_key",
        "active",
        "action_count",
        "action_keys",
        "created_by",
        "created_at"
    ])

    for rule in rules:
        writer.writerow([
            rule["id"],
            rule["name"],
            rule["trigger_key"],
            rule["active"],
            rule["action_count"],
            rule["action_keys"] or "",
            rule["created_by"] or "",
            rule["created_at"] or ""
        ])

    content = "\ufeff" + output.getvalue()

    return Response(
        content,
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f"attachment; filename=automation_rules_{selected_rule_filter or 'all'}_{selected_rule_trigger_filter or 'all'}_{selected_rule_action_filter or 'all'}_{selected_rule_search or 'all'}.csv"
        }
    )


@app.get("/automation/events/export")
async def automation_events_export(
    request: Request,
    event_filter: str = "",
    trigger_filter: str = "",
    event_search: str = "",
    event_entity_filter: str = "",
    event_date_from: str = "",
    event_date_to: str = ""
):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role not in ("boss", "manager"):
        return RedirectResponse("/", status_code=302)

    company_id = get_user_company_id(username)
    disabled_response = require_feature(company_id, "automation")

    if disabled_response:
        return disabled_response

    selected_event_filter = event_filter if event_filter in ("pending", "done", "skipped") else ""
    trigger_keys = {key for key, _ in AUTOMATION_TRIGGERS}
    entity_keys = {"task", "client", "company"}
    selected_trigger_filter = trigger_filter if trigger_filter in trigger_keys else ""
    selected_event_search = (event_search or "").strip()[:80]
    selected_event_entity_filter = event_entity_filter if event_entity_filter in entity_keys else ""
    selected_event_date_from = (event_date_from or "").strip()[:10]
    selected_event_date_to = (event_date_to or "").strip()[:10]
    event_filter_sql = ""
    event_params = [company_id]

    for selected_date in (selected_event_date_from, selected_event_date_to):
        if selected_date:
            try:
                datetime.strptime(selected_date, "%Y-%m-%d")
            except ValueError:
                selected_event_date_from = ""
                selected_event_date_to = ""
                break

    if selected_event_filter:
        event_filter_sql = "AND automation_events.status=?"
        event_params.append(selected_event_filter)

    if selected_trigger_filter:
        event_filter_sql += "\n      AND automation_events.trigger_key=?"
        event_params.append(selected_trigger_filter)

    if selected_event_entity_filter:
        event_filter_sql += "\n      AND automation_events.entity_type=?"
        event_params.append(selected_event_entity_filter)

    if selected_event_search:
        event_filter_sql += """
      AND (
        automation_events.message LIKE ?
        OR automation_rules.name LIKE ?
      )
        """
        event_params.extend([
            f"%{selected_event_search}%",
            f"%{selected_event_search}%"
        ])

    if selected_event_date_from:
        event_filter_sql += "\n      AND substr(automation_events.created_at, 1, 10) >= ?"
        event_params.append(selected_event_date_from)

    if selected_event_date_to:
        event_filter_sql += "\n      AND substr(automation_events.created_at, 1, 10) <= ?"
        event_params.append(selected_event_date_to)

    conn = connect()
    c = conn.cursor()

    events = c.execute(f"""
    SELECT
        automation_events.*,
        automation_rules.name AS rule_name
    FROM automation_events
    LEFT JOIN automation_rules
      ON automation_rules.id=automation_events.rule_id
      AND automation_rules.company_id=automation_events.company_id
    WHERE automation_events.company_id=?
      {event_filter_sql}
    ORDER BY automation_events.id DESC
    LIMIT 500
    """, event_params).fetchall()

    conn.close()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "id",
        "rule_id",
        "rule_name",
        "trigger_key",
        "status",
        "entity_type",
        "entity_id",
        "message",
        "created_at",
        "processed_at"
    ])

    for event in events:
        writer.writerow([
            event["id"],
            event["rule_id"],
            event["rule_name"] or "",
            event["trigger_key"],
            event["status"],
            event["entity_type"],
            event["entity_id"],
            event["message"] or "",
            event["created_at"],
            event["processed_at"] or ""
        ])

    content = "\ufeff" + output.getvalue()

    return Response(
        content,
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f"attachment; filename=automation_events_{selected_event_filter or 'all'}_{selected_trigger_filter or 'all'}_{selected_event_entity_filter or 'all'}_{selected_event_search or 'all'}_{selected_event_date_from or 'from'}_{selected_event_date_to or 'to'}.csv"
        }
    )


@app.post("/automation/ai-digest/run")
async def run_ai_digest_scheduler_page(request: Request):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role not in ("boss", "manager"):
        return RedirectResponse("/", status_code=302)

    company_id = get_user_company_id(username)
    disabled_response = require_feature(company_id, "automation")

    if disabled_response:
        return disabled_response

    disabled_response = require_feature(company_id, "ai_insights")

    if disabled_response:
        return disabled_response

    result = run_ai_digest_scheduler(company_id)

    return RedirectResponse(
        f"/automation?scheduler=1&daily={result['daily']}&weekly={result['weekly']}&follow_ups={result['follow_ups']}&skipped={result['skipped']}",
        status_code=302
    )


@app.post("/automation/cron/ai-digest")
async def run_ai_digest_scheduler_cron(request: Request):

    cron_secret = (os.getenv("AUTOMATION_CRON_SECRET") or "").strip()

    if not cron_secret:
        return JSONResponse(
            {"ok": False, "error": "AUTOMATION_CRON_SECRET is not configured"},
            status_code=503
        )

    token = (
        request.headers.get("x-automation-secret")
        or request.query_params.get("token")
        or ""
    ).strip()

    if not token or not hmac.compare_digest(token, cron_secret):
        return JSONResponse(
            {"ok": False, "error": "forbidden"},
            status_code=403
        )

    summary = run_ai_digest_scheduler_for_all_companies()

    return JSONResponse({
        "ok": True,
        "summary": summary
    })


@app.post("/automation/rules")
async def create_automation_rule(request: Request):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role not in ("boss", "manager"):
        return RedirectResponse("/", status_code=302)

    company_id = get_user_company_id(username)
    disabled_response = require_feature(company_id, "automation")

    if disabled_response:
        return disabled_response

    form = await request.form()
    name = str(form.get("name") or "").strip()
    trigger_key = str(form.get("trigger_key") or "").strip()
    action_key = str(form.get("action_key") or "").strip()
    target_username = str(form.get("target_username") or username).strip()
    message = str(form.get("message") or "").strip()
    task_delay_days, task_priority, task_deadline_hours = (
        automation_create_task_settings({
            "task_delay_days": form.get("task_delay_days"),
            "task_priority": form.get("task_priority"),
            "task_deadline_hours": form.get("task_deadline_hours"),
        })
    )
    task_max_daily_load = automation_task_max_daily_load({
        "task_max_daily_load": form.get("task_max_daily_load"),
    })

    trigger_keys = {key for key, _ in AUTOMATION_TRIGGERS}
    action_keys = {key for key, _ in AUTOMATION_ACTIONS}

    if not name:
        return RedirectResponse("/automation?error=name", status_code=302)

    if trigger_key not in trigger_keys or action_key not in action_keys:
        return RedirectResponse("/automation?error=invalid", status_code=302)

    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    if action_key in ("notification", "telegram_alert") and not message:
        message = f"Автоматизация: {name}"

    if action_key == "ai_digest" and not target_username:
        target_username = username

    if action_key == "ai_digest" and not message:
        message = "AI-сводка по бизнесу"

    payload = {
        "target_username": target_username,
        "message": message
    }

    if action_key == "email":
        payload["subject"] = f"Автоматизация: {name}"
    elif action_key == "create_task":
        payload["task_delay_days"] = task_delay_days
        payload["task_priority"] = task_priority
        payload["task_deadline_hours"] = task_deadline_hours
        payload["task_max_daily_load"] = task_max_daily_load

    conn = connect()
    c = conn.cursor()

    if not automation_action_target_is_valid(
        c,
        company_id,
        action_key,
        target_username,
    ):
        conn.close()
        return RedirectResponse("/automation?error=target", status_code=302)

    c.execute("""
    INSERT INTO automation_rules (
        company_id, name, trigger_key, conditions_json,
        active, created_by, created_at, updated_at
    )
    VALUES (?, ?, ?, ?, 1, ?, ?, ?)
    """, (
        company_id,
        name,
        trigger_key,
        json.dumps({}, ensure_ascii=False),
        username,
        now,
        now
    ))

    rule_id = c.lastrowid

    c.execute("""
    INSERT INTO automation_actions (
        company_id, rule_id, action_key, payload_json,
        sort_order, active, created_at
    )
    VALUES (?, ?, ?, ?, 1, 1, ?)
    """, (
        company_id,
        rule_id,
        action_key,
        json.dumps(payload, ensure_ascii=False),
        now
    ))

    conn.commit()
    conn.close()

    return RedirectResponse("/automation?created=1", status_code=302)




@app.get("/automation/rules/{rule_id}/events/export")
async def automation_rule_events_export(request: Request, rule_id: int):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role not in ("boss", "manager"):
        return RedirectResponse("/", status_code=302)

    company_id = get_user_company_id(username)
    disabled_response = require_feature(company_id, "automation")

    if disabled_response:
        return disabled_response

    conn = connect()
    c = conn.cursor()

    rule = c.execute("""
    SELECT *
    FROM automation_rules
    WHERE id=?
      AND company_id=?
    """, (rule_id, company_id)).fetchone()

    if not rule:
        conn.close()
        return RedirectResponse("/automation", status_code=302)

    events = c.execute("""
    SELECT *
    FROM automation_events
    WHERE company_id=?
      AND rule_id=?
    ORDER BY id DESC
    """, (company_id, rule_id)).fetchall()

    conn.close()

    output = io.StringIO()
    writer = csv.writer(output)

    writer.writerow([
        "id",
        "rule_name",
        "trigger_key",
        "entity_type",
        "entity_id",
        "status",
        "message",
        "created_at",
        "processed_at"
    ])

    for event in events:
        writer.writerow([
            event["id"],
            rule["name"],
            event["trigger_key"],
            event["entity_type"] or "",
            event["entity_id"] or "",
            event["status"],
            event["message"] or "",
            event["created_at"] or "",
            event["processed_at"] or ""
        ])

    return Response(
        content=output.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f"attachment; filename=automation_rule_{rule_id}_events.csv"
        }
    )

@app.get("/automation/rules/{rule_id}", response_class=HTMLResponse)
async def automation_rule_detail(request: Request, rule_id: int):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role not in ("boss", "manager"):
        return RedirectResponse("/", status_code=302)

    company_id = get_user_company_id(username)
    disabled_response = require_feature(company_id, "automation")

    if disabled_response:
        return disabled_response

    conn = connect()
    c = conn.cursor()

    rule = c.execute("""
    SELECT *
    FROM automation_rules
    WHERE id=?
      AND company_id=?
    """, (rule_id, company_id)).fetchone()

    if not rule:
        conn.close()
        return RedirectResponse("/automation", status_code=302)

    actions = c.execute("""
    SELECT *
    FROM automation_actions
    WHERE company_id=?
      AND rule_id=?
    ORDER BY sort_order, id
    """, (company_id, rule_id)).fetchall()

    action_runs = c.execute("""
    SELECT
        automation_action_runs.*,
        automation_actions.action_key,
        source_task.client AS source_client,
        source_task.status AS source_status,
        created_task.client AS created_client,
        created_task.status AS created_status
    FROM automation_action_runs
    JOIN automation_actions
      ON automation_actions.id=automation_action_runs.action_id
      AND automation_actions.company_id=automation_action_runs.company_id
    LEFT JOIN tasks source_task
      ON source_task.id=automation_action_runs.entity_id
      AND source_task.company_id=automation_action_runs.company_id
      AND automation_action_runs.entity_type='task'
    LEFT JOIN tasks created_task
      ON created_task.id=automation_action_runs.created_entity_id
      AND created_task.company_id=automation_action_runs.company_id
      AND automation_action_runs.created_entity_type='task'
    WHERE automation_action_runs.company_id=?
      AND automation_actions.rule_id=?
    ORDER BY automation_action_runs.id DESC
    LIMIT 30
    """, (company_id, rule_id)).fetchall()

    events = c.execute("""
    SELECT *
    FROM automation_events
    WHERE company_id=?
      AND rule_id=?
    ORDER BY id DESC
    LIMIT 20
    """, (company_id, rule_id)).fetchall()

    users = c.execute("""
    SELECT username, role
    FROM users
    WHERE company_id=?
    ORDER BY
        CASE role
            WHEN 'worker' THEN 1
            WHEN 'manager' THEN 2
            WHEN 'boss' THEN 3
            ELSE 4
        END,
        username
    """, (company_id,)).fetchall()

    event_counts = {
        row["status"]: row["count"]
        for row in c.execute("""
        SELECT status, COUNT(*) as count
        FROM automation_events
        WHERE company_id=?
          AND rule_id=?
        GROUP BY status
        """, (company_id, rule_id)).fetchall()
    }

    conn.close()

    done_count = event_counts.get("done", 0)
    skipped_count = event_counts.get("skipped", 0)
    pending_count = event_counts.get("pending", 0)
    success_rate = round(done_count / max(done_count + skipped_count, 1) * 100, 1)

    a3_health_score = 100

    if not rule["active"]:
        a3_health_score -= 30

    if not actions:
        a3_health_score -= 30

    if skipped_count > 0:
        a3_health_score -= 15

    if pending_count > 0:
        a3_health_score -= 10

    a3_health_score = max(a3_health_score, 0)

    if not actions:
        diagnostic_title = "Нет действий"
        diagnostic_message = "Правило включено, но не сможет ничего выполнить без action."
        graph_status = "Проблема"
        graph_status_color = "#dc2626"
        a3_recommendation = "Добавьте хотя бы одно действие: уведомление, Telegram или AI-сводку."

    elif not rule["active"]:
        diagnostic_title = "Правило отключено"
        diagnostic_message = "Правило не будет запускаться, пока его не включить."
        graph_status = "Проблема"
        graph_status_color = "#dc2626"
        a3_recommendation = "Включите правило, если оно должно работать в автоматизации."

    elif skipped_count > 0 or pending_count > 0:
        diagnostic_title = "Нужно внимание"
        diagnostic_message = "У правила есть пропущенные или ожидающие события."
        graph_status = "Нужно внимание"
        graph_status_color = "#f59e0b"
        a3_recommendation = "Проверьте последние события цепочки и повторите пропущенные."

    else:
        diagnostic_title = "OK"
        diagnostic_message = "Правило выглядит рабочим."
        graph_status = "OK"
        graph_status_color = "#16a34a"
        a3_recommendation = "Правило работает стабильно. Продолжайте мониторинг."

    return templates.TemplateResponse(
        request,
        "automation_rule_detail.html",
        {
            "request": request,
            "username": username,
            "role": role,
            "rule": rule,
            "actions": actions,
            "action_runs": action_runs,
            "users": users,
            "events": events,
            "trigger_labels": dict(AUTOMATION_TRIGGERS),
            "action_labels": dict(AUTOMATION_ACTIONS),
            "status_labels": AUTOMATION_STATUS_LABELS,
            "done_count": done_count,
            "skipped_count": skipped_count,
            "pending_count": pending_count,
            "success_rate": success_rate,
            "diagnostic_title": diagnostic_title,
            "diagnostic_message": diagnostic_message,
            "graph_status": graph_status,
            "graph_status_color": graph_status_color,
            "a3_health_score": a3_health_score,
            "a3_recommendation": a3_recommendation
        }
    )

@app.post("/automation/rules/{rule_id}/edit")
async def edit_automation_rule(request: Request, rule_id: int):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role not in ("boss", "manager"):
        return RedirectResponse("/", status_code=302)

    company_id = get_user_company_id(username)
    disabled_response = require_feature(company_id, "automation")

    if disabled_response:
        return disabled_response

    form = await request.form()
    name = str(form.get("name") or "").strip()
    target_username = str(form.get("target_username") or username).strip()
    message = str(form.get("message") or "").strip()

    if not name:
        return RedirectResponse("/automation?error=name", status_code=302)

    conn = connect()
    c = conn.cursor()

    rule = c.execute("""
    SELECT id
    FROM automation_rules
    WHERE id=?
      AND company_id=?
    """, (rule_id, company_id)).fetchone()

    if not rule:
        conn.close()
        return RedirectResponse("/automation", status_code=302)

    target_exists = c.execute("""
    SELECT id
    FROM users
    WHERE company_id=?
      AND username=?
    """, (company_id, target_username)).fetchone()

    if not target_exists:
        conn.close()
        return RedirectResponse("/automation?error=target", status_code=302)

    payload = {
        "target_username": target_username,
        "message": message
    }
    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    c.execute("""
    UPDATE automation_rules
    SET name=?, updated_at=?
    WHERE id=?
      AND company_id=?
    """, (
        name,
        now,
        rule_id,
        company_id
    ))

    action = c.execute("""
    SELECT id
    FROM automation_actions
    WHERE company_id=?
      AND rule_id=?
    ORDER BY sort_order, id
    LIMIT 1
    """, (company_id, rule_id)).fetchone()

    if action:
        c.execute("""
        UPDATE automation_actions
        SET payload_json=?
        WHERE id=?
          AND company_id=?
        """, (
            json.dumps(payload, ensure_ascii=False),
            action["id"],
            company_id
        ))

    conn.commit()
    conn.close()

    return RedirectResponse("/automation?updated=1", status_code=302)


@app.post("/automation/rules/{rule_id}/conditions")
async def update_automation_rule_conditions(request: Request, rule_id: int):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role not in ("boss", "manager"):
        return RedirectResponse("/", status_code=302)

    company_id = get_user_company_id(username)
    disabled_response = require_feature(company_id, "automation")

    if disabled_response:
        return disabled_response

    form = await request.form()
    condition_mode = str(form.get("condition_mode") or "none").strip()
    condition_secondary_mode = str(
        form.get("condition_secondary_mode") or "none"
    ).strip()
    condition_tertiary_mode = str(
        form.get("condition_tertiary_mode") or "none"
    ).strip()
    condition_values = [
        str(form.get("condition_value") or "").strip(),
        str(form.get("condition_secondary_value") or "").strip(),
        str(form.get("condition_tertiary_value") or "").strip(),
    ]
    condition_workers = [
        str(form.get("condition_worker") or "").strip(),
        str(form.get("condition_secondary_worker") or "").strip(),
        str(form.get("condition_tertiary_worker") or "").strip(),
    ]
    condition_clients = [
        str(form.get("condition_client") or "").strip(),
        str(form.get("condition_secondary_client") or "").strip(),
        str(form.get("condition_tertiary_client") or "").strip(),
    ]
    condition_catalog_items = [
        str(form.get("condition_catalog") or "").strip(),
        str(form.get("condition_secondary_catalog") or "").strip(),
        str(form.get("condition_tertiary_catalog") or "").strip(),
    ]
    condition_texts = [
        str(form.get("condition_text") or "").strip(),
        str(form.get("condition_secondary_text") or "").strip(),
        str(form.get("condition_tertiary_text") or "").strip(),
    ]
    condition_operator = str(form.get("condition_operator") or "and").strip().lower()
    allowed_modes = {
        "none": {},
        "priority_high": {
            "mode": "priority_high",
            "field": "priority",
            "operator": "equals",
            "value": "Высокий",
            "label": "Только высокий приоритет",
        },
        "emergency": {
            "mode": "emergency",
            "field": "priority",
            "operator": "equals",
            "value": "Срочно",
            "label": "Только срочные заявки",
        },
        "task_text_contains": {
            "mode": "task_text_contains",
            "field": "task_text",
            "operator": "contains",
            "value": "",
            "label": "Текст заявки содержит",
        },
        "status_new": {
            "mode": "status_new",
            "field": "status",
            "operator": "equals",
            "value": "Новая",
            "label": "Только новые заявки",
        },
        "status_in_progress": {
            "mode": "status_in_progress",
            "field": "status",
            "operator": "equals",
            "value": "В работе",
            "label": "Только заявки в работе",
        },
        "status_done": {
            "mode": "status_done",
            "field": "status",
            "operator": "equals",
            "value": "Завершено",
            "label": "Только завершённые заявки",
        },
        "payment_unpaid": {
            "mode": "payment_unpaid",
            "field": "payment_status",
            "operator": "equals",
            "value": "Не оплачено",
            "label": "Только неоплаченные заявки",
        },
        "payment_partial": {
            "mode": "payment_partial",
            "field": "payment_status",
            "operator": "equals",
            "value": "Частично оплачено",
            "label": "Только частично оплаченные заявки",
        },
        "payment_paid": {
            "mode": "payment_paid",
            "field": "payment_status",
            "operator": "equals",
            "value": "Оплачено",
            "label": "Только оплаченные заявки",
        },
        "worker_assigned": {
            "mode": "worker_assigned",
            "field": "workers",
            "operator": "not_empty",
            "label": "Только задачи с исполнителем",
        },
        "worker_specific": {
            "mode": "worker_specific",
            "field": "workers",
            "operator": "contains",
            "value": "",
            "label": "Только выбранный исполнитель",
        },
        "date_today": {
            "mode": "date_today",
            "field": "task_date",
            "operator": "equals_today",
            "label": "Только задачи на сегодня",
        },
        "date_overdue": {
            "mode": "date_overdue",
            "field": "task_date",
            "operator": "before_today",
            "label": "Только просроченные задачи",
        },
        "date_future": {
            "mode": "date_future",
            "field": "task_date",
            "operator": "after_today",
            "label": "Только будущие задачи",
        },
        "price_high": {
            "mode": "price_high",
            "field": "price",
            "operator": "gte",
            "value": "10000",
            "label": "Только дорогие заявки",
        },
        "price_missing": {
            "mode": "price_missing",
            "field": "price",
            "operator": "empty_or_zero",
            "label": "Только заявки без цены",
        },
        "catalog_specific": {
            "mode": "catalog_specific",
            "field": "catalog_item_id",
            "operator": "contains",
            "value": "",
            "label": "Только выбранная позиция каталога",
        },
        "sla_today": {
            "mode": "sla_today",
            "field": "deadline_at",
            "operator": "date_today",
            "label": "Только дедлайн сегодня",
        },
        "sla_overdue": {
            "mode": "sla_overdue",
            "field": "deadline_at",
            "operator": "before_now",
            "label": "Только просроченный SLA",
        },
        "sla_due_24h": {
            "mode": "sla_due_24h",
            "field": "deadline_at",
            "operator": "within_24h",
            "label": "Только дедлайн в ближайшие 24 часа",
        },
        "client_specific": {
            "mode": "client_specific",
            "field": "client_id",
            "operator": "equals",
            "value": "",
            "label": "Только выбранный клиент",
        },
        "client_new": {
            "mode": "client_new",
            "field": "client_id",
            "operator": "task_count_lte",
            "value": "1",
            "label": "Только новые клиенты",
        },
        "client_repeat": {
            "mode": "client_repeat",
            "field": "client_id",
            "operator": "task_count_gte",
            "value": "2",
            "label": "Только постоянные клиенты",
        },
        "client_vip": {
            "mode": "client_vip",
            "field": "client_notes",
            "operator": "contains",
            "value": "VIP",
            "label": "Только VIP клиенты",
        },
        "client_has_debt": {
            "mode": "client_has_debt",
            "field": "payment_status",
            "operator": "has_unpaid_tasks",
            "label": "Только клиенты с долгом",
        },
        "client_many_tasks": {
            "mode": "client_many_tasks",
            "field": "client_id",
            "operator": "task_count_gte",
            "value": "5",
            "label": "Только клиенты с большим количеством заявок",
        },
    }

    if (
        condition_mode not in allowed_modes
        or condition_secondary_mode not in allowed_modes
        or condition_tertiary_mode not in allowed_modes
        or condition_operator not in ("and", "or")
    ):
        return RedirectResponse("/automation/builder?conditions_error=1", status_code=302)

    selected_modes = [
        (
            mode,
            condition_values[index],
            condition_workers[index],
            condition_clients[index],
            condition_catalog_items[index],
            condition_texts[index],
        )
        for index, mode in enumerate((
            condition_mode,
            condition_secondary_mode,
            condition_tertiary_mode,
        ))
        if mode != "none"
    ]

    selected_conditions = []

    for (
        mode,
        raw_value,
        selected_worker,
        selected_client,
        selected_catalog_item,
        condition_text,
    ) in selected_modes:
        condition = dict(allowed_modes[mode])

        if mode == "task_text_contains":
            keyword = condition_text[:120].strip()

            if not keyword:
                return RedirectResponse("/automation/builder?conditions_error=1", status_code=302)

            condition["value"] = keyword
            condition["label"] = f"Текст содержит: {keyword}"

        elif mode == "worker_specific":
            if not selected_worker:
                return RedirectResponse("/automation/builder?conditions_error=1", status_code=302)

            condition["value"] = selected_worker
            condition["label"] = f"Исполнитель: {selected_worker}"

        elif mode == "client_specific":
            try:
                client_id = int(selected_client)
            except (TypeError, ValueError):
                return RedirectResponse("/automation/builder?conditions_error=1", status_code=302)

            condition["value"] = str(client_id)
            condition["label"] = f"Клиент #{client_id}"

        elif mode == "catalog_specific":
            try:
                catalog_item_id = int(selected_catalog_item)
            except (TypeError, ValueError):
                return RedirectResponse("/automation/builder?conditions_error=1", status_code=302)

            condition["value"] = str(catalog_item_id)
            condition["label"] = f"Позиция каталога #{catalog_item_id}"

        elif mode == "price_high":
            try:
                threshold = max(float(raw_value.replace(",", ".")), 0) if raw_value else 10000
            except ValueError:
                return RedirectResponse("/automation/builder?conditions_error=1", status_code=302)

            condition["value"] = f"{threshold:g}"
            condition["label"] = f"Цена заявки от {threshold:g} ₽"

        elif mode == "client_many_tasks":
            try:
                threshold = max(int(raw_value), 1) if raw_value else 5
            except ValueError:
                return RedirectResponse("/automation/builder?conditions_error=1", status_code=302)

            condition["value"] = str(threshold)
            condition["label"] = f"У клиента от {threshold} заявок"

        selected_conditions.append(condition)

    if len(selected_modes) > 1:
        conditions_payload = {
            "operator": condition_operator,
            "conditions": selected_conditions,
        }
    elif selected_modes:
        conditions_payload = selected_conditions[0]
    else:
        conditions_payload = {}

    conn = connect()
    c = conn.cursor()

    rule = c.execute("""
    SELECT id
    FROM automation_rules
    WHERE id=?
      AND company_id=?
    """, (rule_id, company_id)).fetchone()

    if not rule:
        conn.close()
        return RedirectResponse("/automation/builder?conditions_error=1", status_code=302)

    for condition in selected_conditions:
        if condition.get("mode") == "worker_specific":
            worker_exists = c.execute("""
            SELECT 1
            FROM users
            WHERE company_id=?
              AND role='worker'
              AND username=?
            """, (company_id, condition["value"])).fetchone()

            if not worker_exists:
                conn.close()
                return RedirectResponse("/automation/builder?conditions_error=1", status_code=302)

        elif condition.get("mode") == "client_specific":
            client_row = c.execute("""
            SELECT id, name
            FROM clients
            WHERE company_id=?
              AND id=?
            """, (company_id, condition["value"])).fetchone()

            if not client_row:
                conn.close()
                return RedirectResponse("/automation/builder?conditions_error=1", status_code=302)

            condition["label"] = f"Клиент: {client_row['name']}"

        elif condition.get("mode") == "catalog_specific":
            catalog_item = c.execute("""
            SELECT id, name
            FROM catalog_items
            WHERE company_id=?
              AND id=?
              AND active=1
            """, (company_id, condition["value"])).fetchone()

            if not catalog_item:
                conn.close()
                return RedirectResponse("/automation/builder?conditions_error=1", status_code=302)

            condition["label"] = f"Каталог: {catalog_item['name']}"

    c.execute("""
    UPDATE automation_rules
    SET conditions_json=?,
        updated_at=?
    WHERE id=?
      AND company_id=?
    """, (
        json.dumps(conditions_payload, ensure_ascii=False),
        datetime.now().strftime("%Y-%m-%d %H:%M"),
        rule_id,
        company_id,
    ))

    conn.commit()
    conn.close()

    return RedirectResponse("/automation/builder?conditions_updated=1", status_code=302)











@app.post("/automation/diagnostics/rules/{rule_id}/add-default-action")
async def add_default_action_to_rule(request: Request, rule_id: int):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role not in ("boss", "manager"):
        return RedirectResponse("/", status_code=302)

    company_id = get_user_company_id(username)

    disabled_response = require_feature(company_id, "automation")

    if disabled_response:
        return disabled_response

    conn = connect()
    c = conn.cursor()

    rule = c.execute("""
    SELECT *
    FROM automation_rules
    WHERE id=?
      AND company_id=?
    """, (rule_id, company_id)).fetchone()

    if not rule:
        conn.close()
        return RedirectResponse(
            "/automation/diagnostics?action_added=0",
            status_code=302
        )

    existing_action = c.execute("""
    SELECT id
    FROM automation_actions
    WHERE company_id=?
      AND rule_id=?
      AND active=1
    LIMIT 1
    """, (company_id, rule_id)).fetchone()

    if existing_action:
        conn.close()
        return RedirectResponse(
            "/automation/diagnostics?action_exists=1",
            status_code=302
        )

    payload = {
        "target_username": username,
        "message": f"Автоматизация: {rule['name']}"
    }

    c.execute("""
    INSERT INTO automation_actions (
        company_id,
        rule_id,
        action_key,
        payload_json,
        active,
        created_at
    )
    VALUES (?, ?, ?, ?, 1, ?)
    """, (
        company_id,
        rule_id,
        "notification",
        json.dumps(payload, ensure_ascii=False),
        datetime.now().strftime("%Y-%m-%d %H:%M")
    ))

    conn.commit()
    conn.close()

    return RedirectResponse(
        "/automation/diagnostics?action_added=1",
        status_code=302
    )

@app.post("/automation/diagnostics/rules/{rule_id}/enable")
async def enable_automation_rule_from_diagnostics(request: Request, rule_id: int):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role not in ("boss", "manager"):
        return RedirectResponse("/", status_code=302)

    company_id = get_user_company_id(username)
    disabled_response = require_feature(company_id, "automation")

    if disabled_response:
        return disabled_response

    conn = connect()
    c = conn.cursor()

    rule = c.execute("""
    SELECT *
    FROM automation_rules
    WHERE id=?
      AND company_id=?
      AND active=0
    """, (rule_id, company_id)).fetchone()

    if not rule:
        conn.close()
        return RedirectResponse("/automation/diagnostics?enable_skipped=1", status_code=302)

    c.execute("""
    UPDATE automation_rules
    SET active=1, updated_at=?
    WHERE id=?
      AND company_id=?
    """, (
        datetime.now().strftime("%Y-%m-%d %H:%M"),
        rule_id,
        company_id
    ))

    conn.commit()
    conn.close()

    return RedirectResponse("/automation/diagnostics?enabled=1", status_code=302)

@app.post("/automation/diagnostics/retry-skipped")
async def retry_skipped_automation_events(request: Request):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role not in ("boss", "manager"):
        return RedirectResponse("/", status_code=302)

    company_id = get_user_company_id(username)
    disabled_response = require_feature(company_id, "automation")

    if disabled_response:
        return disabled_response

    conn = connect()
    c = conn.cursor()

    skipped_events = c.execute("""
    SELECT *
    FROM automation_events
    WHERE company_id=?
      AND status='skipped'
    ORDER BY id DESC
    LIMIT 10
    """, (company_id,)).fetchall()

    conn.close()

    retried = 0

    for event in skipped_events:
        created_events = run_automation_event(
            company_id,
            event["trigger_key"],
            event["entity_type"] or "",
            event["entity_id"],
            event["message"] or "Повтор пропущенного события",
            "/automation/diagnostics"
        )

        if created_events:
            retried += created_events

    return RedirectResponse(
        f"/automation/diagnostics?retry_skipped=1&retried={retried}",
        status_code=302
    )

@app.post("/automation/events/cleanup")
async def cleanup_automation_events(request: Request):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role not in ("boss", "manager"):
        return RedirectResponse("/", status_code=302)

    company_id = get_user_company_id(username)

    disabled_response = require_feature(company_id, "automation")

    if disabled_response:
        return disabled_response

    conn = connect()
    c = conn.cursor()

    old_events = c.execute("""
    SELECT COUNT(*)
    FROM automation_events
    WHERE company_id=?
      AND created_at != ''
      AND datetime(created_at) < datetime('now', '-30 days')
    """, (company_id,)).fetchone()[0]

    c.execute("""
    DELETE FROM automation_events
    WHERE company_id=?
      AND created_at != ''
      AND datetime(created_at) < datetime('now', '-30 days')
    """, (company_id,))

    conn.commit()
    conn.close()

    return RedirectResponse(
        f"/automation/diagnostics?cleanup=1&deleted={old_events}",
        status_code=302
    )

@app.get("/automation/diagnostics/export")
async def automation_diagnostics_export(request: Request):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role not in ("boss", "manager"):
        return RedirectResponse("/", status_code=302)

    company_id = get_user_company_id(username)
    disabled_response = require_feature(company_id, "automation")

    if disabled_response:
        return disabled_response

    conn = connect()
    c = conn.cursor()

    disabled_rules = c.execute("""
    SELECT id, name, trigger_key, created_by, updated_at
    FROM automation_rules
    WHERE company_id=?
      AND active=0
    ORDER BY updated_at DESC, id DESC
    """, (company_id,)).fetchall()

    rules_without_actions = c.execute("""
    SELECT automation_rules.id, automation_rules.name, automation_rules.trigger_key, automation_rules.created_by, automation_rules.created_at
    FROM automation_rules
    LEFT JOIN automation_actions
      ON automation_actions.rule_id=automation_rules.id
      AND automation_actions.company_id=automation_rules.company_id
      AND automation_actions.active=1
    WHERE automation_rules.company_id=?
      AND automation_rules.active=1
    GROUP BY automation_rules.id
    HAVING COUNT(automation_actions.id)=0
    ORDER BY automation_rules.id DESC
    """, (company_id,)).fetchall()

    recent_skipped_events = c.execute("""
    SELECT
        automation_events.id,
        automation_rules.name AS rule_name,
        automation_events.trigger_key,
        automation_events.entity_type,
        automation_events.entity_id,
        automation_events.message,
        automation_events.created_at,
        automation_events.processed_at
    FROM automation_events
    LEFT JOIN automation_rules
      ON automation_rules.id=automation_events.rule_id
      AND automation_rules.company_id=automation_events.company_id
    WHERE automation_events.company_id=?
      AND automation_events.status='skipped'
    ORDER BY automation_events.id DESC
    LIMIT 50
    """, (company_id,)).fetchall()

    conn.close()

    output = io.StringIO()
    writer = csv.writer(output)

    writer.writerow(["section", "id", "name_or_rule", "trigger_key", "entity_type", "entity_id", "message", "created_at", "updated_or_processed_at"])

    for rule in disabled_rules:
        writer.writerow([
            "disabled_rule",
            rule["id"],
            rule["name"],
            rule["trigger_key"],
            "",
            "",
            "",
            "",
            rule["updated_at"] or ""
        ])

    for rule in rules_without_actions:
        writer.writerow([
            "rule_without_actions",
            rule["id"],
            rule["name"],
            rule["trigger_key"],
            "",
            "",
            "",
            rule["created_at"] or "",
            ""
        ])

    for event in recent_skipped_events:
        writer.writerow([
            "skipped_event",
            event["id"],
            event["rule_name"] or "",
            event["trigger_key"],
            event["entity_type"] or "",
            event["entity_id"] or "",
            event["message"] or "",
            event["created_at"] or "",
            event["processed_at"] or ""
        ])

    csv_data = output.getvalue()

    return Response(
        content=csv_data,
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": "attachment; filename=automation_diagnostics.csv"
        }
    )

@app.get("/automation/diagnostics", response_class=HTMLResponse)
async def automation_diagnostics_page(request: Request):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role not in ("boss", "manager"):
        return RedirectResponse("/", status_code=302)

    company_id = get_user_company_id(username)
    disabled_response = require_feature(company_id, "automation")

    if disabled_response:
        return disabled_response

    conn = connect()
    c = conn.cursor()

    disabled_rules = c.execute("""
    SELECT *
    FROM automation_rules
    WHERE company_id=?
      AND active=0
    ORDER BY updated_at DESC, id DESC
    LIMIT 10
    """, (company_id,)).fetchall()

    rules_without_actions = c.execute("""
    SELECT automation_rules.*
    FROM automation_rules
    LEFT JOIN automation_actions
      ON automation_actions.rule_id=automation_rules.id
      AND automation_actions.company_id=automation_rules.company_id
      AND automation_actions.active=1
    WHERE automation_rules.company_id=?
      AND automation_rules.active=1
    GROUP BY automation_rules.id
    HAVING COUNT(automation_actions.id)=0
    ORDER BY automation_rules.id DESC
    """, (company_id,)).fetchall()

    pending_events = c.execute("""
    SELECT COUNT(*)
    FROM automation_events
    WHERE company_id=?
      AND status='pending'
    """, (company_id,)).fetchone()[0]

    skipped_events = c.execute("""
    SELECT COUNT(*)
    FROM automation_events
    WHERE company_id=?
      AND status='skipped'
    """, (company_id,)).fetchone()[0]

    done_events = c.execute("""
    SELECT COUNT(*)
    FROM automation_events
    WHERE company_id=?
      AND status='done'
    """, (company_id,)).fetchone()[0]

    recent_skipped_events = c.execute("""
    SELECT
        automation_events.*,
        automation_rules.name AS rule_name
    FROM automation_events
    LEFT JOIN automation_rules
      ON automation_rules.id=automation_events.rule_id
      AND automation_rules.company_id=automation_events.company_id
    WHERE automation_events.company_id=?
      AND automation_events.status='skipped'
    ORDER BY automation_events.id DESC
    LIMIT 10
    """, (company_id,)).fetchall()

    telegram_rules = c.execute("""
    SELECT COUNT(*)
    FROM automation_actions
    WHERE company_id=?
      AND action_key='telegram_alert'
      AND active=1
    """, (company_id,)).fetchone()[0]

    ai_digest_rules = c.execute("""
    SELECT COUNT(*)
    FROM automation_actions
    WHERE company_id=?
      AND action_key='ai_digest'
      AND active=1
    """, (company_id,)).fetchone()[0]

    success_rate = round(done_events / max(done_events + skipped_events, 1) * 100, 1)

    a3_system_health_score = 100

    if pending_events > 0:
        a3_system_health_score -= min(pending_events * 5, 25)

    if skipped_events > 0:
        a3_system_health_score -= min(skipped_events * 5, 30)

    if rules_without_actions:
        a3_system_health_score -= 20

    if disabled_rules:
        a3_system_health_score -= 10

    if success_rate < 80 and (done_events + skipped_events) > 0:
        a3_system_health_score -= 15

    a3_system_health_score = max(a3_system_health_score, 0)

    if a3_system_health_score >= 85:
        a3_system_health_level = "Отлично"
        a3_system_recommendation = "Система автоматизации работает стабильно."
    elif a3_system_health_score >= 60:
        a3_system_health_level = "Нужно внимание"
        a3_system_recommendation = "Проверьте пропущенные, ожидающие события и правила без действий."
    else:
        a3_system_health_level = "Проблема"
        a3_system_recommendation = "Нужно срочно проверить диагностику, правила и действия автоматизации."

    problems = []

    if pending_events > 5:
        problems.append({
            "title": "Много ожидающих событий",
            "reason": "Некоторые события долго не обрабатываются.",
            "action": "Проверьте последние события и повторите нужные вручную."
        })

    if skipped_events > done_events:
        problems.append({
            "title": "Много пропущенных событий",
            "reason": "Автоматизация чаще пропускает события, чем выполняет.",
            "action": "Проверьте правила без действий и последние пропущенные события."
        })

    if rules_without_actions:
        problems.append({
            "title": "Есть правила без действий",
            "reason": "Правило включено, но не имеет активного действия.",
            "action": "Откройте правило и добавьте действие: уведомление, Telegram или AI-сводку."
        })

    if success_rate < 80 and (done_events + skipped_events) > 0:
        problems.append({
            "title": "Низкая успешность автоматизации",
            "reason": "Процент выполненных событий ниже 80%.",
            "action": "Проверьте пропущенные события и настройки получателей."
        })

    if telegram_rules:
        problems.append({
            "title": "Проверьте Telegram-уведомления",
            "reason": "В системе есть правила автоматизации для Telegram.",
            "action": "Убедитесь, что BOT_TOKEN и telegram_chat_id настроены."
        })

    if ai_digest_rules:
        problems.append({
            "title": "Проверьте AI-сводки",
            "reason": "В системе есть автоматизация AI-сводок.",
            "action": "Проверьте, что AI-сводки появляются в уведомлениях и в журнале событий."
        })

    if not problems:
        problems.append({
            "title": "Критичных проблем не найдено",
            "reason": "Движок автоматизации работает стабильно.",
            "action": "Продолжайте мониторить события и успешность."
        })

    conn.close()

    return templates.TemplateResponse(
        request,
        "automation_diagnostics.html",
        {
            "request": request,
            "username": username,
            "role": role,
            "disabled_rules": disabled_rules,
            "rules_without_actions": rules_without_actions,
            "pending_events": pending_events,
            "skipped_events": skipped_events,
            "done_events": done_events,
            "recent_skipped_events": recent_skipped_events,
            "telegram_rules": telegram_rules,
            "ai_digest_rules": ai_digest_rules,
            "success_rate": success_rate,
            "a3_system_health_score": a3_system_health_score,
            "a3_system_health_level": a3_system_health_level,
            "a3_system_recommendation": a3_system_recommendation,
            "problems": problems,
            "trigger_labels": dict(AUTOMATION_TRIGGERS),
        }
    )

@app.get("/automation/events/{event_id}", response_class=HTMLResponse)
async def automation_event_detail(request: Request, event_id: int):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role not in ("boss", "manager"):
        return RedirectResponse("/", status_code=302)

    company_id = get_user_company_id(username)

    disabled_response = require_feature(company_id, "automation")

    if disabled_response:
        return disabled_response

    conn = connect()
    c = conn.cursor()

    event = c.execute("""
    SELECT
        automation_events.*,
        automation_rules.name AS rule_name
    FROM automation_events
    LEFT JOIN automation_rules
      ON automation_rules.id=automation_events.rule_id
      AND automation_rules.company_id=automation_events.company_id
    WHERE automation_events.id=?
      AND automation_events.company_id=?
    """, (event_id, company_id)).fetchone()

    conn.close()

    if not event:
        return RedirectResponse("/automation", status_code=302)

    trigger_labels = dict(AUTOMATION_TRIGGERS)

    status_labels = AUTOMATION_STATUS_LABELS

    entity_labels = {
        "task": "Заявка",
        "client": "Клиент",
        "company": "Компания"
    }

    return templates.TemplateResponse(
        request,
        "automation_event_detail.html",
        {
            "request": request,
            "username": username,
            "role": role,
            "event": event,
            "trigger_labels": trigger_labels,
            "status_labels": status_labels,
            "entity_labels": entity_labels
        }
    )

@app.post("/automation/events/{event_id}/retry")
async def retry_automation_event(request: Request, event_id: int):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role not in ("boss", "manager"):
        return RedirectResponse("/", status_code=302)

    company_id = get_user_company_id(username)
    disabled_response = require_feature(company_id, "automation")

    if disabled_response:
        return disabled_response

    conn = connect()
    c = conn.cursor()

    event = c.execute("""
    SELECT *
    FROM automation_events
    WHERE id=?
      AND company_id=?
      AND status IN ('pending', 'skipped')
    """, (event_id, company_id)).fetchone()

    conn.close()

    if not event:
        return RedirectResponse("/automation?retry_skipped=1", status_code=302)

    created_events = run_automation_event(
        company_id,
        event["trigger_key"],
        event["entity_type"] or "",
        event["entity_id"],
        event["message"] or "Повтор события автоматизации",
        "/automation"
    )

    if created_events:
        return RedirectResponse("/automation?retry=1", status_code=302)

    return RedirectResponse("/automation?retry_skipped=1", status_code=302)





@app.post("/automation/rules/{rule_id}/actions/create")
async def create_rule_action(request: Request, rule_id: int):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role not in ("boss", "manager"):
        return RedirectResponse("/", status_code=302)

    company_id = get_user_company_id(username)

    disabled_response = require_feature(company_id, "automation")

    if disabled_response:
        return disabled_response

    form = await request.form()

    action_key = str(form.get("action_key") or "").strip()
    target_username = str(form.get("target_username") or "").strip()
    message = str(form.get("message") or "").strip()
    task_delay_days, task_priority, task_deadline_hours = (
        automation_create_task_settings({
            "task_delay_days": form.get("task_delay_days"),
            "task_priority": form.get("task_priority"),
            "task_deadline_hours": form.get("task_deadline_hours"),
        })
    )
    task_max_daily_load = automation_task_max_daily_load({
        "task_max_daily_load": form.get("task_max_daily_load"),
    })

    action_keys = {key for key, _ in AUTOMATION_ACTIONS}

    if action_key not in action_keys:
        return RedirectResponse(
            f"/automation/rules/{rule_id}?action_error=1",
            status_code=302
        )

    conn = connect()
    c = conn.cursor()

    rule = c.execute("""
    SELECT *
    FROM automation_rules
    WHERE id=?
      AND company_id=?
    """, (rule_id, company_id)).fetchone()

    if not rule:
        conn.close()
        return RedirectResponse("/automation", status_code=302)

    if not automation_action_target_is_valid(
        c,
        company_id,
        action_key,
        target_username,
    ):
        conn.close()
        return RedirectResponse(
            f"/automation/rules/{rule_id}?action_target_error=1",
            status_code=302
        )

    if action_key in ("notification", "telegram_alert") and not message:
        message = f"Автоматизация: {rule['name']}"

    if action_key == "ai_digest" and not target_username:
        target_username = username

    if action_key == "ai_digest" and not message:
        message = "AI-сводка по бизнесу"

    if action_key == "create_task" and not message:
        message = f"Автоматическая задача: {rule['name']}"

    payload = {
        "target_username": target_username,
        "message": message
    }

    if action_key == "email":
        payload["subject"] = f"Автоматизация: {rule['name']}"
    elif action_key == "create_task":
        payload["task_delay_days"] = task_delay_days
        payload["task_priority"] = task_priority
        payload["task_deadline_hours"] = task_deadline_hours
        payload["task_max_daily_load"] = task_max_daily_load

    c.execute("""
    INSERT INTO automation_actions (
        company_id,
        rule_id,
        action_key,
        payload_json,
        active,
        created_at
    )
    VALUES (?, ?, ?, ?, 1, ?)
    """, (
        company_id,
        rule_id,
        action_key,
        json.dumps(payload, ensure_ascii=False),
        datetime.now().strftime("%Y-%m-%d %H:%M")
    ))

    conn.commit()
    conn.close()

    return RedirectResponse(
        f"/automation/rules/{rule_id}?action_created=1",
        status_code=302
    )


@app.post("/automation/actions/{action_id}/toggle")
async def toggle_automation_action(request: Request, action_id: int):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role not in ("boss", "manager"):
        return RedirectResponse("/", status_code=302)

    company_id = get_user_company_id(username)

    disabled_response = require_feature(company_id, "automation")

    if disabled_response:
        return disabled_response

    conn = connect()
    c = conn.cursor()

    action = c.execute("""
    SELECT *
    FROM automation_actions
    WHERE id=?
      AND company_id=?
    """, (action_id, company_id)).fetchone()

    if not action:
        conn.close()
        return RedirectResponse("/automation", status_code=302)

    new_active = 0 if action["active"] else 1

    c.execute("""
    UPDATE automation_actions
    SET active=?
    WHERE id=?
      AND company_id=?
    """, (
        new_active,
        action_id,
        company_id
    ))

    conn.commit()
    conn.close()

    return RedirectResponse(
        f"/automation/rules/{action['rule_id']}?action_updated=1",
        status_code=302
    )


@app.post("/automation/actions/{action_id}/delete")
async def delete_automation_action(request: Request, action_id: int):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role not in ("boss", "manager"):
        return RedirectResponse("/", status_code=302)

    company_id = get_user_company_id(username)

    disabled_response = require_feature(company_id, "automation")

    if disabled_response:
        return disabled_response

    conn = connect()
    c = conn.cursor()

    action = c.execute("""
    SELECT *
    FROM automation_actions
    WHERE id=?
      AND company_id=?
    """, (action_id, company_id)).fetchone()

    if not action:
        conn.close()
        return RedirectResponse("/automation", status_code=302)

    rule_id = action["rule_id"]

    c.execute("""
    DELETE FROM automation_actions
    WHERE id=?
      AND company_id=?
    """, (
        action_id,
        company_id
    ))

    conn.commit()
    conn.close()

    return RedirectResponse(
        f"/automation/rules/{rule_id}?action_deleted=1",
        status_code=302
    )

@app.post("/automation/rules/{rule_id}/retry-skipped")
async def retry_rule_skipped_events(request: Request, rule_id: int):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role not in ("boss", "manager"):
        return RedirectResponse("/", status_code=302)

    company_id = get_user_company_id(username)
    disabled_response = require_feature(company_id, "automation")

    if disabled_response:
        return disabled_response

    conn = connect()
    c = conn.cursor()

    events = c.execute("""
    SELECT *
    FROM automation_events
    WHERE company_id=?
      AND rule_id=?
      AND status='skipped'
    ORDER BY id DESC
    LIMIT 10
    """, (company_id, rule_id)).fetchall()

    conn.close()

    retried = 0

    for event in events:
        created_events = run_automation_event(
            company_id,
            event["trigger_key"],
            event["entity_type"] or "",
            event["entity_id"],
            event["message"] or "Повтор пропущенного события правила",
            f"/automation/rules/{rule_id}"
        )

        if created_events:
            retried += created_events

    return RedirectResponse(
        f"/automation/rules/{rule_id}?retry_skipped=1&retried={retried}",
        status_code=302
    )

@app.post("/automation/rules/{rule_id}/run")
async def run_automation_rule_now(request: Request, rule_id: int):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role not in ("boss", "manager"):
        return RedirectResponse("/", status_code=302)

    company_id = get_user_company_id(username)
    disabled_response = require_feature(company_id, "automation")

    if disabled_response:
        return disabled_response

    conn = connect()
    c = conn.cursor()

    rule = c.execute("""
    SELECT *
    FROM automation_rules
    WHERE id=?
      AND company_id=?
      AND active=1
    """, (rule_id, company_id)).fetchone()

    conn.close()

    if not rule:
        return RedirectResponse("/automation?run_skipped=1", status_code=302)

    created_events = run_automation_event(
        company_id,
        rule["trigger_key"],
        "company",
        company_id,
        f"Ручной запуск правила: {rule['name']}",
        "/automation"
    )

    if created_events:
        return RedirectResponse("/automation?run=1", status_code=302)

    return RedirectResponse("/automation?run_skipped=1", status_code=302)

@app.post("/automation/rules/{rule_id}/toggle")
async def toggle_automation_rule(request: Request, rule_id: int):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role not in ("boss", "manager"):
        return RedirectResponse("/", status_code=302)

    company_id = get_user_company_id(username)
    disabled_response = require_feature(company_id, "automation")

    if disabled_response:
        return disabled_response

    conn = connect()
    c = conn.cursor()

    rule = c.execute("""
    SELECT active
    FROM automation_rules
    WHERE id=?
      AND company_id=?
    """, (rule_id, company_id)).fetchone()

    if not rule:
        conn.close()
        return RedirectResponse("/automation", status_code=302)

    new_active = 0 if rule["active"] else 1

    c.execute("""
    UPDATE automation_rules
    SET active=?, updated_at=?
    WHERE id=?
      AND company_id=?
    """, (
        new_active,
        datetime.now().strftime("%Y-%m-%d %H:%M"),
        rule_id,
        company_id
    ))

    conn.commit()
    conn.close()

    return RedirectResponse("/automation?toggled=1", status_code=302)


@app.post("/automation/rules/{rule_id}/enable")
async def enable_automation_rule(request: Request, rule_id: int):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role not in ("boss", "manager"):
        return RedirectResponse("/", status_code=302)

    company_id = get_user_company_id(username)
    disabled_response = require_feature(company_id, "automation")

    if disabled_response:
        return disabled_response

    conn = connect()
    c = conn.cursor()

    rule = c.execute("""
    SELECT id
    FROM automation_rules
    WHERE id=?
      AND company_id=?
    """, (rule_id, company_id)).fetchone()

    if not rule:
        conn.close()
        return RedirectResponse("/automation", status_code=302)

    c.execute("""
    UPDATE automation_rules
    SET active=1, updated_at=?
    WHERE id=?
      AND company_id=?
    """, (
        datetime.now().strftime("%Y-%m-%d %H:%M"),
        rule_id,
        company_id
    ))

    conn.commit()
    conn.close()

    return RedirectResponse("/automation?enabled=1", status_code=302)


@app.post("/automation/rules/{rule_id}/delete")
async def delete_automation_rule(request: Request, rule_id: int):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role not in ("boss", "manager"):
        return RedirectResponse("/", status_code=302)

    company_id = get_user_company_id(username)
    disabled_response = require_feature(company_id, "automation")

    if disabled_response:
        return disabled_response

    conn = connect()
    c = conn.cursor()

    rule = c.execute("""
    SELECT id
    FROM automation_rules
    WHERE id=?
      AND company_id=?
    """, (rule_id, company_id)).fetchone()

    if not rule:
        conn.close()
        return RedirectResponse("/automation", status_code=302)

    c.execute("""
    DELETE FROM automation_actions
    WHERE rule_id=?
      AND company_id=?
    """, (rule_id, company_id))

    c.execute("""
    DELETE FROM automation_rules
    WHERE id=?
      AND company_id=?
    """, (rule_id, company_id))

    conn.commit()
    conn.close()

    return RedirectResponse("/automation?deleted=1", status_code=302)


@app.get("/workload", response_class=HTMLResponse)
async def workload_page(request: Request):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role not in ("boss", "manager"):
        return RedirectResponse("/", status_code=302)

    company_id = get_user_company_id(username)
    disabled_response = require_feature(company_id, "workload")

    if disabled_response:
        return disabled_response

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
    disabled_response = require_feature(company_id, "sla")

    if disabled_response:
        return disabled_response

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
    automation_tasks = []

    for task in tasks:
        task_created_count = 0

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
                f"Заявка #{task['id']} просрочила срок SLA",
                f"/task/{task['id']}",
                datetime.now().strftime("%Y-%m-%d %H:%M")
            ))
            created_count += 1
            task_created_count += 1

        if task_created_count:
            automation_tasks.append(task)

    conn.commit()
    conn.close()

    for task in automation_tasks:
        run_automation_event(
            company_id,
            "sla_overdue",
            "task",
            task["id"],
            f"Заявка #{task['id']} просрочила срок SLA",
            f"/task/{task['id']}"
        )

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

    disabled_response = require_feature(company_id, "sla")

    if disabled_response:
        return disabled_response


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
    settings = get_company_settings(company_id)
    disabled_response = require_feature(company_id, "sla")

    if disabled_response:
        return disabled_response

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
            "selected_worker": worker,
            "settings": settings
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


@app.post("/overdue/reminders")
async def create_overdue_reminders(request: Request):

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
      AND status NOT IN ('Завершено', 'Отменено')
      AND task_date IS NOT NULL
      AND task_date!=''
      AND task_date < ?
    ORDER BY task_date ASC
    """, (company_id, today)).fetchall()

    users = c.execute("""
    SELECT username
    FROM users
    WHERE company_id=?
      AND role IN ('boss', 'manager')
    """, (company_id,)).fetchall()

    created_count = 0
    automation_tasks = []

    for task in tasks:
        task_created_count = 0

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
                "🟠 Просрочена задача",
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
                "🟠 Просрочена задача",
                f"Задача #{task['id']} просрочена по дате",
                f"/task/{task['id']}",
                datetime.now().strftime("%Y-%m-%d %H:%M")
            ))
            created_count += 1
            task_created_count += 1

        if task_created_count:
            automation_tasks.append(task)

    conn.commit()
    conn.close()

    for task in automation_tasks:
        run_automation_event(
            company_id,
            "overdue_task",
            "task",
            task["id"],
            f"Задача #{task['id']} просрочена по дате",
            f"/task/{task['id']}"
        )

    return RedirectResponse(f"/overdue?reminders=1&created={created_count}", status_code=302)


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
    disabled_response = require_feature(company_id, "calendar")

    if disabled_response:
        return disabled_response

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
    disabled_response = require_feature(company_id, "recurring")

    if disabled_response:
        return disabled_response

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

    disabled_response = require_feature(company_id, "recurring")

    if disabled_response:
        return disabled_response



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
async def finance_export(
    request: Request,
    month: str = "",
    payment_filter: str = "",
    worker: str = "",
    profit_filter: str = ""
):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role != "boss":
        return RedirectResponse("/", status_code=302)

    if not month:
        month = datetime.now().strftime("%Y-%m")
    selected_payment_filter = payment_filter if payment_filter in ("paid", "partial", "unpaid") else ""
    selected_worker = str(worker or "").strip()
    selected_profit_filter = profit_filter if profit_filter == "loss" else ""

    conn = connect()
    c = conn.cursor()

    if role == "superadmin":
        return RedirectResponse("/platform", status_code=302)

    company_id = get_user_company_id(username)

    disabled_response = require_feature(company_id, "finance")

    if disabled_response:
        return disabled_response



    workers = c.execute("""
    SELECT id, username, commission_percent
    FROM users
    WHERE role='worker' AND company_id=?
    ORDER BY username
    """, (company_id,)).fetchall()
    worker_names = [row["username"] for row in workers]
    worker_ids = {
        row["username"]: row["id"]
        for row in workers
    }
    worker_commissions = {
        row["username"]: float(row["commission_percent"] or 0)
        for row in workers
    }
    payroll_payouts = c.execute("""
    SELECT worker_id, amount
    FROM payroll_payouts
    WHERE company_id=? AND month=? AND status='paid'
    """, (company_id, month)).fetchall()
    payroll_payout_map = {
        row["worker_id"]: round(float(row["amount"] or 0), 1)
        for row in payroll_payouts
    }

    tasks = c.execute("""
    SELECT *
    FROM tasks
    WHERE archived=0 AND company_id=? AND task_date LIKE ?
    ORDER BY task_date DESC
    """, (company_id, f"{month}%")).fetchall()

    output = io.StringIO()
    writer = csv.writer(output)
    worker_finance = {}

    writer.writerow([
        "ID",
        "Дата",
        "Клиент",
        "Телефон",
        "Адрес",
        "Исполнитель",
        "Статус заявки",
        "Статус оплаты",
        "Скидка",
        "Сумма",
        "Расходы",
        "Прибыль",
        "Маржа %"
    ])

    for task in tasks:
        if selected_worker and selected_worker not in get_task_worker_names(task):
            continue

        items = c.execute("""
        SELECT *
        FROM task_items
        WHERE task_id=?
        """, (task["id"],)).fetchall()
        expenses = c.execute("""
        SELECT *
        FROM task_expenses
        WHERE task_id=?
        """, (task["id"],)).fetchall()

        task_total = sum(item["total"] for item in items)
        task_profit = sum(item["profit"] for item in items)
        discount_amount = float(task["discount_amount"] or 0) if "discount_amount" in task.keys() else 0
        task_expenses_total = sum(expense["amount"] for expense in expenses)

        if not items:
            try:
                task_total = float(task["price"] or 0)
            except Exception:
                task_total = 0
            task_profit = 0

        if discount_amount < 0:
            discount_amount = 0

        task_total = max(task_total - discount_amount, 0)
        task_profit = task_profit - discount_amount - task_expenses_total

        payment_status = task["payment_status"] if "payment_status" in task.keys() else "Не оплачено"
        task_margin = round((task_profit / task_total) * 100, 1) if task_total else 0

        if selected_payment_filter == "paid" and payment_status != "Оплачено":
            continue
        if selected_payment_filter == "partial" and payment_status != "Частично оплачено":
            continue
        if selected_payment_filter == "unpaid" and payment_status != "Не оплачено":
            continue
        if selected_profit_filter == "loss" and task_profit >= 0:
            continue

        task_worker_names = [
            worker_name for worker_name in get_task_worker_names(task)
            if worker_name in worker_names
        ]

        if not task_worker_names:
            task_worker_names = ["Не назначены"]

        worker_share_count = len(task_worker_names)

        for worker_name in task_worker_names:
            if worker_name not in worker_finance:
                worker_finance[worker_name] = {
                    "worker_id": worker_ids.get(worker_name),
                    "worker": worker_name,
                    "commission_percent": worker_commissions.get(worker_name, 0),
                    "tasks": 0,
                    "total": 0,
                    "expenses": 0,
                    "profit": 0
                }

            worker_finance[worker_name]["tasks"] += 1
            worker_finance[worker_name]["total"] += task_total / worker_share_count
            worker_finance[worker_name]["expenses"] += task_expenses_total / worker_share_count
            worker_finance[worker_name]["profit"] += task_profit / worker_share_count

        writer.writerow([
            task["id"],
            task["task_date"],
            task["client"],
            task["phone"],
            task["address"],
            format_task_workers(task),
            task["status"],
            payment_status,
            discount_amount,
            task_total,
            task_expenses_total,
            task_profit,
            task_margin
        ])

    worker_finance_rows = []

    for worker_row in worker_finance.values():
        worker_row["total"] = round(worker_row["total"], 1)
        worker_row["expenses"] = round(worker_row["expenses"], 1)
        worker_row["profit"] = round(worker_row["profit"], 1)
        worker_row["payout"] = round(worker_row["profit"] * worker_row["commission_percent"] / 100, 1)
        worker_row["paid_amount"] = payroll_payout_map.get(worker_row["worker_id"], 0)
        worker_row["due_amount"] = round(max(worker_row["payout"] - worker_row["paid_amount"], 0), 1)
        worker_row["payout_status"] = "Не выплачено"
        if worker_row["paid_amount"] > 0:
            worker_row["payout_status"] = "Выплачено" if worker_row["paid_amount"] >= worker_row["payout"] else "Частично"
        worker_finance_rows.append(worker_row)

    worker_finance_rows.sort(key=lambda row: row["profit"], reverse=True)

    if worker_finance_rows:
        total_worker_payout = round(sum(row["payout"] for row in worker_finance_rows), 1)
        total_worker_paid = round(sum(row["paid_amount"] for row in worker_finance_rows), 1)
        total_worker_due = round(sum(row["due_amount"] for row in worker_finance_rows), 1)

        writer.writerow([])
        writer.writerow(["Финансы по исполнителям"])
        writer.writerow([
            "Исполнитель",
            "Заявки",
            "Выручка",
            "Расходы",
            "Прибыль",
            "Процент",
            "Выплата",
            "Статус зарплаты",
            "Выплачено",
            "Остаток"
        ])

        for worker_row in worker_finance_rows:
            writer.writerow([
                worker_row["worker"],
                worker_row["tasks"],
                worker_row["total"],
                worker_row["expenses"],
                worker_row["profit"],
                worker_row["commission_percent"],
                worker_row["payout"],
                worker_row["payout_status"],
                worker_row["paid_amount"],
                worker_row["due_amount"]
            ])

        writer.writerow([])
        writer.writerow(["Итого начислено ЗП", total_worker_payout])
        writer.writerow(["Итого выплачено ЗП", total_worker_paid])
        writer.writerow(["Итого остаток ЗП", total_worker_due])

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


@app.get("/finance/summary/export")
async def finance_summary_export(request: Request, month: str = ""):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role not in ("boss", "manager"):
        return RedirectResponse("/", status_code=302)

    company_id = get_user_company_id(username)
    disabled_response = require_feature(company_id, "finance")

    if disabled_response:
        return disabled_response

    if not month:
        month = datetime.now().strftime("%Y-%m")

    conn = connect()
    c = conn.cursor()

    rows = c.execute("""
    SELECT
        month,
        client_name,
        price,
        expense_total,
        payroll_total,
        profit
    FROM finance_summary
    WHERE company_id=?
      AND month=?
    ORDER BY client_name
    """, (company_id, month)).fetchall()

    output = io.StringIO()
    writer = csv.writer(output)

    writer.writerow([
        "Месяц",
        "Клиент",
        "Выручка",
        "Расходы",
        "Зарплаты",
        "Прибыль",
        "Чистая прибыль"
    ])

    for row in rows:
        row_profit = float(row["profit"] or 0)
        row_payroll = float(row["payroll_total"] or 0)

        writer.writerow([
            row["month"],
            row["client_name"] or "Unknown",
            round(float(row["price"] or 0), 2),
            round(float(row["expense_total"] or 0), 2),
            round(row_payroll, 2),
            round(row_profit, 2),
            round(row_profit - row_payroll, 2)
        ])

    conn.close()

    content = output.getvalue()
    output.close()

    return Response(
        content,
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f"attachment; filename=finance_summary_{month}.csv"
        }
    )





@app.get("/sla/analytics/export")
async def sla_analytics_export(request: Request):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role not in ("boss", "manager"):
        return RedirectResponse("/", status_code=302)

    company_id = get_user_company_id(username)
    disabled_response = require_feature(company_id, "sla")

    if disabled_response:
        return disabled_response

    conn = connect()
    c = conn.cursor()

    rows = c.execute("""
    SELECT
        id,
        client,
        workers,
        task_date,
        status
    FROM tasks
    WHERE company_id=?
    ORDER BY task_date DESC
    """, (company_id,)).fetchall()

    conn.close()

    today = datetime.now().date()

    output = io.StringIO()
    writer = csv.writer(output)

    writer.writerow([
        "ID заявки",
        "Клиент",
        "Исполнители",
        "Дата заявки",
        "Статус",
        "Просрочено",
        "Дней просрочки"
    ])

    for row in rows:
        is_overdue = False
        age_days = 0

        try:
            task_date_value = datetime.strptime(row["task_date"], "%Y-%m-%d").date()
            age_days = (today - task_date_value).days
            is_overdue = row["status"] != "done" and task_date_value < today
        except Exception:
            pass

        writer.writerow([
            row["id"],
            row["client"] or "Unknown",
            row["workers"] or "",
            row["task_date"] or "",
            row["status"] or "",
            "yes" if is_overdue else "no",
            age_days
        ])

    content = output.getvalue()
    output.close()

    return Response(
        content,
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": "attachment; filename=sla_analytics.csv"
        }
    )



@app.get("/sla/analytics", response_class=HTMLResponse)
async def sla_analytics_page(request: Request):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role not in ("boss", "manager"):
        return RedirectResponse("/", status_code=302)

    company_id = get_user_company_id(username)
    settings = get_company_settings(company_id)
    disabled_response = require_feature(company_id, "sla")

    if disabled_response:
        return disabled_response

    conn = connect()
    c = conn.cursor()

    total_tasks = c.execute("""
    SELECT COUNT(*)
    FROM tasks
    WHERE company_id=?
    """, (company_id,)).fetchone()[0]

    completed_tasks = c.execute("""
    SELECT COUNT(*)
    FROM tasks
    WHERE company_id=?
      AND status='done'
    """, (company_id,)).fetchone()[0]

    open_tasks = c.execute("""
    SELECT COUNT(*)
    FROM tasks
    WHERE company_id=?
      AND status!='done'
    """, (company_id,)).fetchone()[0]

    overdue_tasks = c.execute("""
    SELECT COUNT(*)
    FROM tasks
    WHERE company_id=?
      AND status!='done'
      AND task_date < date('now')
    """, (company_id,)).fetchone()[0]

    clients = c.execute("""
    SELECT DISTINCT client
    FROM tasks
    WHERE company_id=?
      AND client IS NOT NULL
      AND client!=''
    ORDER BY client
    """, (company_id,)).fetchall()

    client_rows = []

    for client in clients:
        client_name = client["client"]

        total_client_tasks = c.execute("""
        SELECT COUNT(*)
        FROM tasks
        WHERE company_id=?
          AND client=?
        """, (company_id, client_name)).fetchone()[0]

        completed_client_tasks = c.execute("""
        SELECT COUNT(*)
        FROM tasks
        WHERE company_id=?
          AND client=?
          AND status='done'
        """, (company_id, client_name)).fetchone()[0]

        open_client_tasks = c.execute("""
        SELECT COUNT(*)
        FROM tasks
        WHERE company_id=?
          AND client=?
          AND status!='done'
        """, (company_id, client_name)).fetchone()[0]

        overdue_client_tasks = c.execute("""
        SELECT COUNT(*)
        FROM tasks
        WHERE company_id=?
          AND client=?
          AND status!='done'
          AND task_date < date('now')
        """, (company_id, client_name)).fetchone()[0]

        client_overdue_rate = round(
            (overdue_client_tasks / total_client_tasks * 100),
            1
        ) if total_client_tasks else 0

        client_rows.append({
            "client": client_name,
            "total_tasks": total_client_tasks,
            "completed_tasks": completed_client_tasks,
            "open_tasks": open_client_tasks,
            "overdue_tasks": overdue_client_tasks,
            "overdue_rate": client_overdue_rate,
            "sla_score": round(100 - client_overdue_rate, 1)
        })

    sla_client_rows = sorted(
        client_rows,
        key=lambda row: row["overdue_tasks"],
        reverse=True
    )[:20]

    overdue_task_rows = c.execute("""
    SELECT
        id,
        client,
        workers,
        task_date,
        status
    FROM tasks
    WHERE company_id=?
      AND status!='done'
      AND task_date < date('now')
    ORDER BY task_date ASC
    LIMIT 30
    """, (company_id,)).fetchall()

    today = datetime.now().date()
    sla_overdue_tasks = []

    for row in overdue_task_rows:
        try:
            task_date_value = datetime.strptime(row["task_date"], "%Y-%m-%d").date()
            age_days = (today - task_date_value).days
        except Exception:
            age_days = 0

        sla_overdue_tasks.append({
            "id": row["id"],
            "client": row["client"] or "Unknown",
            "workers": row["workers"] or "",
            "task_date": row["task_date"],
            "status": row["status"],
            "age_days": age_days
        })


    workers = c.execute("""
    SELECT id, username
    FROM users
    WHERE company_id=?
      AND role='worker'
    ORDER BY username
    """, (company_id,)).fetchall()

    worker_rows = []

    for worker in workers:
        username_value = worker["username"]

        total_worker_tasks = c.execute("""
        SELECT COUNT(*)
        FROM tasks
        WHERE company_id=?
          AND workers LIKE ?
        """, (company_id, f"%{username_value}%")).fetchone()[0]

        completed_worker_tasks = c.execute("""
        SELECT COUNT(*)
        FROM tasks
        WHERE company_id=?
          AND workers LIKE ?
          AND status='done'
        """, (company_id, f"%{username_value}%")).fetchone()[0]

        open_worker_tasks = c.execute("""
        SELECT COUNT(*)
        FROM tasks
        WHERE company_id=?
          AND workers LIKE ?
          AND status!='done'
        """, (company_id, f"%{username_value}%")).fetchone()[0]

        overdue_worker_tasks = c.execute("""
        SELECT COUNT(*)
        FROM tasks
        WHERE company_id=?
          AND workers LIKE ?
          AND status!='done'
          AND task_date < date('now')
        """, (company_id, f"%{username_value}%")).fetchone()[0]

        worker_overdue_rate = round(
            (overdue_worker_tasks / total_worker_tasks * 100),
            1
        ) if total_worker_tasks else 0

        worker_rows.append({
            "worker": username_value,
            "total_tasks": total_worker_tasks,
            "completed_tasks": completed_worker_tasks,
            "open_tasks": open_worker_tasks,
            "overdue_tasks": overdue_worker_tasks,
            "overdue_rate": worker_overdue_rate,
            "sla_score": round(100 - worker_overdue_rate, 1)
        })

    sla_worker_rows = sorted(
        worker_rows,
        key=lambda row: row["overdue_tasks"],
        reverse=True
    )

    monthly_task_rows = c.execute("""
    SELECT
        substr(task_date, 1, 7) as month,
        COUNT(*) as total_tasks,
        SUM(CASE WHEN status='done' THEN 1 ELSE 0 END) as completed_tasks,
        SUM(CASE WHEN status!='done' AND task_date < date('now') THEN 1 ELSE 0 END) as overdue_tasks
    FROM tasks
    WHERE company_id=?
      AND task_date IS NOT NULL
      AND task_date!=''
    GROUP BY substr(task_date, 1, 7)
    ORDER BY month DESC
    LIMIT 12
    """, (company_id,)).fetchall()

    sla_monthly_rows = []

    for row in monthly_task_rows:
        monthly_total = int(row["total_tasks"] or 0)
        monthly_overdue = int(row["overdue_tasks"] or 0)

        monthly_overdue_rate = round(
            (monthly_overdue / monthly_total * 100),
            1
        ) if monthly_total else 0

        sla_monthly_rows.append({
            "month": row["month"],
            "total_tasks": monthly_total,
            "completed_tasks": int(row["completed_tasks"] or 0),
            "overdue_tasks": monthly_overdue,
            "overdue_rate": monthly_overdue_rate,
            "sla_score": round(100 - monthly_overdue_rate, 1)
        })

    completed_rows = c.execute("""
    SELECT
        created_at,
        task_date
    FROM tasks
    WHERE company_id=?
      AND status='done'
      AND created_at IS NOT NULL
      AND task_date IS NOT NULL
      AND task_date!=''
    """, (company_id,)).fetchall()

    completion_days = []

    for row in completed_rows:
        try:
            created_date = datetime.strptime(
                row["created_at"][:10],
                "%Y-%m-%d"
            ).date()

            completed_date = datetime.strptime(
                row["task_date"][:10],
                "%Y-%m-%d"
            ).date()

            days = (completed_date - created_date).days

            if days >= 0:
                completion_days.append(days)

        except Exception:
            pass

    average_completion_days = round(
        sum(completion_days) / len(completion_days),
        1
    ) if completion_days else 0

    fastest_completion_days = min(completion_days) if completion_days else 0
    slowest_completion_days = max(completion_days) if completion_days else 0

    conn.close()

    overdue_rate = round(
        (overdue_tasks / total_tasks * 100),
        1
    ) if total_tasks else 0

    overall_sla_score = round(100 - overdue_rate, 1)

    return templates.TemplateResponse(
        request,
        "sla_analytics.html",
        {
            "request": request,
            "username": username,
            "role": role,
            "total_tasks": total_tasks,
            "completed_tasks": completed_tasks,
            "open_tasks": open_tasks,
            "overdue_tasks": overdue_tasks,
            "overdue_rate": overdue_rate,
            "overall_sla_score": overall_sla_score,
            "average_completion_days": average_completion_days,
            "fastest_completion_days": fastest_completion_days,
            "slowest_completion_days": slowest_completion_days,
            "sla_worker_rows": sla_worker_rows,
            "sla_client_rows": sla_client_rows,
            "sla_overdue_tasks": sla_overdue_tasks,
            "sla_monthly_rows": sla_monthly_rows,
            "settings": settings
        }
    )


@app.get("/owner/dashboard/export")
async def owner_dashboard_export(request: Request):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role != "boss":
        return RedirectResponse("/", status_code=302)

    company_id = get_user_company_id(username)

    disabled_response = require_feature(company_id, "analytics")

    if disabled_response:
        return disabled_response



    conn = connect()
    c = conn.cursor()

    rows = c.execute("""
    SELECT
        month,
        SUM(price) as revenue,
        SUM(payroll_total) as payroll,
        SUM(profit) as profit,
        COUNT(task_id) as jobs_count,
        AVG(price) as average_job_value
    FROM finance_summary
    WHERE company_id=?
    GROUP BY month
    ORDER BY month DESC
    """, (company_id,)).fetchall()

    conn.close()

    output = io.StringIO()
    writer = csv.writer(output)

    writer.writerow([
        "Месяц",
        "Выручка",
        "Зарплаты",
        "Прибыль",
        "Чистая прибыль",
        "Количество заявок",
        "Средний чек"
    ])

    for row in rows:
        revenue = float(row["revenue"] or 0)
        payroll = float(row["payroll"] or 0)
        profit = float(row["profit"] or 0)

        writer.writerow([
            row["month"],
            round(revenue, 2),
            round(payroll, 2),
            round(profit, 2),
            round(profit - payroll, 2),
            int(row["jobs_count"] or 0),
            round(float(row["average_job_value"] or 0), 2)
        ])

    content = output.getvalue()
    output.close()

    return Response(
        content,
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": "attachment; filename=owner_dashboard.csv"
        }
    )



@app.get("/owner/dashboard", response_class=HTMLResponse)
async def owner_dashboard_page(request: Request, month: str = ""):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role != "boss":
        return RedirectResponse("/", status_code=302)

    company_id = get_user_company_id(username)
    disabled_response = require_feature(company_id, "analytics")

    if disabled_response:
        return disabled_response

    if not month:
        month = datetime.now().strftime("%Y-%m")

    conn = connect()
    c = conn.cursor()

    total_clients = c.execute("""
    SELECT COUNT(*)
    FROM clients
    WHERE company_id=?
    """, (company_id,)).fetchone()[0]

    total_workers = c.execute("""
    SELECT COUNT(*)
    FROM users
    WHERE company_id=?
      AND role='worker'
    """, (company_id,)).fetchone()[0]

    total_tasks = c.execute("""
    SELECT COUNT(*)
    FROM tasks
    WHERE company_id=?
    """, (company_id,)).fetchone()[0]

    total_completed_tasks = c.execute("""
    SELECT COUNT(*)
    FROM tasks
    WHERE company_id=?
      AND status='done'
    """, (company_id,)).fetchone()[0]

    total_revenue = c.execute("""
    SELECT COALESCE(SUM(price), 0)
    FROM finance_summary
    WHERE company_id=?
    """, (company_id,)).fetchone()[0]

    total_profit = c.execute("""
    SELECT COALESCE(SUM(profit), 0)
    FROM finance_summary
    WHERE company_id=?
    """, (company_id,)).fetchone()[0]

    total_payroll = c.execute("""
    SELECT COALESCE(SUM(payroll_total), 0)
    FROM finance_summary
    WHERE company_id=?
    """, (company_id,)).fetchone()[0]

    unpaid_total = c.execute("""
    SELECT COALESCE(SUM(price), 0)
    FROM tasks
    WHERE company_id=?
      AND payment_status!='paid'
    """, (company_id,)).fetchone()[0]

    average_job_value = c.execute("""
    SELECT COALESCE(AVG(price), 0)
    FROM tasks
    WHERE company_id=?
    """, (company_id,)).fetchone()[0]

    unpaid_tasks = c.execute("""
    SELECT
        id,
        client,
        task_date,
        price
    FROM tasks
    WHERE company_id=?
      AND payment_status!='paid'
      AND COALESCE(price, 0) > 0
    ORDER BY task_date ASC
    LIMIT 20
    """, (company_id,)).fetchall()

    unpaid_aging_summary = {
        "0_7": 0,
        "8_30": 0,
        "31_plus": 0
    }

    unpaid_risk_tasks = []

    today = datetime.now().date()

    for row in unpaid_tasks:
        unpaid_amount = float(row["price"] or 0)

        try:
            task_date = datetime.strptime(row["task_date"], "%Y-%m-%d").date()
            age_days = (today - task_date).days
        except Exception:
            age_days = 0

        if age_days <= 7:
            unpaid_aging_summary["0_7"] += unpaid_amount
        elif age_days <= 30:
            unpaid_aging_summary["8_30"] += unpaid_amount
        else:
            unpaid_aging_summary["31_plus"] += unpaid_amount

        unpaid_risk_tasks.append({
            "id": row["id"],
            "client_name": row["client"] or "Не указан",
            "task_date": row["task_date"],
            "unpaid_amount": round(unpaid_amount, 1),
            "age_days": age_days
        })

    unpaid_aging_summary = {
        "0_7": round(unpaid_aging_summary["0_7"], 1),
        "8_30": round(unpaid_aging_summary["8_30"], 1),
        "31_plus": round(unpaid_aging_summary["31_plus"], 1)
    }

    repeat_clients_summary = c.execute("""
    SELECT
        COUNT(*) as repeat_clients_count,
        COALESCE(SUM(revenue), 0) as repeat_clients_revenue
    FROM (
        SELECT
            client_name,
            COUNT(task_id) as jobs_count,
            SUM(price) as revenue
        FROM finance_summary
        WHERE company_id=?
        GROUP BY client_name
        HAVING jobs_count > 1
    )
    """, (company_id,)).fetchone()

    top_repeat_clients = c.execute("""
    SELECT
        client_name,
        COUNT(task_id) as jobs_count,
        SUM(price) as revenue,
        SUM(profit) as profit,
        SUM(payroll_total) as payroll
    FROM finance_summary
    WHERE company_id=?
    GROUP BY client_name
    HAVING jobs_count > 1
    ORDER BY revenue DESC
    LIMIT 10
    """, (company_id,)).fetchall()

    top_owner_clients = c.execute("""
    SELECT
        client_name,
        SUM(price) as revenue,
        SUM(profit) as profit,
        SUM(payroll_total) as payroll,
        COUNT(task_id) as jobs_count
    FROM finance_summary
    WHERE company_id=?
    GROUP BY client_name
    ORDER BY profit DESC
    LIMIT 10
    """, (company_id,)).fetchall()

    top_owner_workers = c.execute("""
    SELECT
        users.username as worker_name,
        SUM(payroll_payouts.amount) as total_paid,
        COUNT(payroll_payouts.id) as payouts_count
    FROM payroll_payouts
    JOIN users ON users.id = payroll_payouts.worker_id
    WHERE payroll_payouts.company_id=?
      AND payroll_payouts.status='paid'
    GROUP BY payroll_payouts.worker_id
    ORDER BY total_paid DESC
    LIMIT 10
    """, (company_id,)).fetchall()

    low_margin_clients = c.execute("""
    SELECT
        client_name,
        SUM(price) as revenue,
        SUM(profit) as profit,
        SUM(payroll_total) as payroll,
        COUNT(task_id) as jobs_count
    FROM finance_summary
    WHERE company_id=?
    GROUP BY client_name
    HAVING revenue > 0
       AND ((SUM(profit) - SUM(payroll_total)) / SUM(price) * 100) < 15
    ORDER BY ((SUM(profit) - SUM(payroll_total)) / SUM(price) * 100) ASC
    LIMIT 10
    """, (company_id,)).fetchall()

    negative_months = c.execute("""
    SELECT
        month,
        SUM(price) as revenue,
        SUM(profit) as profit,
        SUM(payroll_total) as payroll
    FROM finance_summary
    WHERE company_id=?
    GROUP BY month
    HAVING (SUM(profit) - SUM(payroll_total)) < 0
    ORDER BY month DESC
    LIMIT 10
    """, (company_id,)).fetchall()

    owner_monthly_metrics = c.execute("""
    SELECT
        month,
        SUM(price) as revenue,
        SUM(payroll_total) as payroll,
        SUM(profit) as profit,
        COUNT(task_id) as jobs_count,
        AVG(price) as average_job_value
    FROM finance_summary
    WHERE company_id=?
    GROUP BY month
    ORDER BY month DESC
    LIMIT 12
    """, (company_id,)).fetchall()

    total_revenue = round(float(total_revenue or 0), 1)
    total_profit = round(float(total_profit or 0), 1)
    total_payroll = round(float(total_payroll or 0), 1)
    unpaid_total = round(float(unpaid_total or 0), 1)
    average_job_value = round(float(average_job_value or 0), 1)

    net_profit = round(total_profit - total_payroll, 1)

    payroll_ratio = round((total_payroll / total_revenue * 100), 1) if total_revenue else 0
    profit_margin = round((net_profit / total_revenue * 100), 1) if total_revenue else 0
    completion_rate = round((total_completed_tasks / total_tasks * 100), 1) if total_tasks else 0
    unpaid_ratio = round((unpaid_total / total_revenue * 100), 1) if total_revenue else 0

    repeat_clients_count = int(repeat_clients_summary["repeat_clients_count"] or 0)
    repeat_clients_revenue = round(float(repeat_clients_summary["repeat_clients_revenue"] or 0), 1)

    top_repeat_clients = [
        {
            "client_name": row["client"] or "Не указан",
            "jobs_count": int(row["jobs_count"] or 0),
            "revenue": round(float(row["revenue"] or 0), 1),
            "profit": round(float(row["profit"] or 0), 1),
            "payroll": round(float(row["payroll"] or 0), 1),
            "net_profit": round(float(row["profit"] or 0) - float(row["payroll"] or 0), 1)
        }
        for row in top_repeat_clients
    ]

    top_owner_clients = [
        {
            "client_name": row["client"] or "Не указан",
            "revenue": round(float(row["revenue"] or 0), 1),
            "profit": round(float(row["profit"] or 0), 1),
            "payroll": round(float(row["payroll"] or 0), 1),
            "net_profit": round(float(row["profit"] or 0) - float(row["payroll"] or 0), 1),
            "jobs_count": int(row["jobs_count"] or 0)
        }
        for row in top_owner_clients
    ]

    top_owner_workers = [
        {
            "worker_name": row["worker_name"],
            "total_paid": round(float(row["total_paid"] or 0), 1),
            "payouts_count": int(row["payouts_count"] or 0)
        }
        for row in top_owner_workers
    ]

    low_margin_clients = [
        {
            "client_name": row["client"] or "Unknown",
            "revenue": round(float(row["revenue"] or 0), 1),
            "profit": round(float(row["profit"] or 0), 1),
            "payroll": round(float(row["payroll"] or 0), 1),
            "net_profit": round(float(row["profit"] or 0) - float(row["payroll"] or 0), 1),
            "margin": round(((float(row["profit"] or 0) - float(row["payroll"] or 0)) / float(row["revenue"] or 1) * 100), 1),
            "jobs_count": int(row["jobs_count"] or 0)
        }
        for row in low_margin_clients
    ]

    negative_months = [
        {
            "month": row["month"],
            "revenue": round(float(row["revenue"] or 0), 1),
            "profit": round(float(row["profit"] or 0), 1),
            "payroll": round(float(row["payroll"] or 0), 1),
            "net_profit": round(float(row["profit"] or 0) - float(row["payroll"] or 0), 1)
        }
        for row in negative_months
    ]

    owner_monthly_metrics = [
        {
            "month": row["month"],
            "revenue": round(float(row["revenue"] or 0), 1),
            "payroll": round(float(row["payroll"] or 0), 1),
            "profit": round(float(row["profit"] or 0), 1),
            "net_profit": round(float(row["profit"] or 0) - float(row["payroll"] or 0), 1),
            "jobs_count": int(row["jobs_count"] or 0),
            "average_job_value": round(float(row["average_job_value"] or 0), 1)
        }
        for row in owner_monthly_metrics
    ]

    selected_month_metrics = c.execute("""
    SELECT
        COALESCE(SUM(price), 0) as revenue,
        COALESCE(SUM(payroll_total), 0) as payroll,
        COALESCE(SUM(profit), 0) as profit
    FROM finance_summary
    WHERE company_id=?
      AND month=?
    """, (company_id, month)).fetchone()

    selected_month_date = datetime.strptime(month + "-01", "%Y-%m-%d")
    previous_month = (selected_month_date.replace(day=1) - timedelta(days=1)).strftime("%Y-%m")

    previous_month_metrics = c.execute("""
    SELECT
        COALESCE(SUM(price), 0) as revenue,
        COALESCE(SUM(payroll_total), 0) as payroll,
        COALESCE(SUM(profit), 0) as profit
    FROM finance_summary
    WHERE company_id=?
      AND month=?
    """, (company_id, previous_month)).fetchone()

    selected_revenue = float(selected_month_metrics["revenue"] or 0)
    selected_payroll = float(selected_month_metrics["payroll"] or 0)
    selected_profit = float(selected_month_metrics["profit"] or 0)
    selected_net_profit = selected_profit - selected_payroll

    previous_revenue = float(previous_month_metrics["revenue"] or 0)
    previous_payroll = float(previous_month_metrics["payroll"] or 0)
    previous_profit = float(previous_month_metrics["profit"] or 0)
    previous_net_profit = previous_profit - previous_payroll

    owner_month_comparison = {
        "selected_month": month,
        "previous_month": previous_month,
        "revenue_growth": round(((selected_revenue - previous_revenue) / previous_revenue * 100), 1) if previous_revenue else 0,
        "payroll_growth": round(((selected_payroll - previous_payroll) / previous_payroll * 100), 1) if previous_payroll else 0,
        "net_profit_growth": round(((selected_net_profit - previous_net_profit) / previous_net_profit * 100), 1) if previous_net_profit else 0,
        "selected_revenue": round(selected_revenue, 1),
        "selected_payroll": round(selected_payroll, 1),
        "selected_net_profit": round(selected_net_profit, 1),
        "previous_revenue": round(previous_revenue, 1),
        "previous_payroll": round(previous_payroll, 1),
        "previous_net_profit": round(previous_net_profit, 1)
    }

    owner_chart_data = list(reversed(owner_monthly_metrics))

    conn.close()

    return templates.TemplateResponse(
        request,
        "owner_dashboard.html",
        {
            "request": request,
            "username": username,
            "role": role,
            "total_clients": total_clients,
            "total_workers": total_workers,
            "total_tasks": total_tasks,
            "total_completed_tasks": total_completed_tasks,
            "total_revenue": total_revenue,
            "total_profit": total_profit,
            "total_payroll": total_payroll,
            "net_profit": net_profit,
            "unpaid_total": unpaid_total,
            "average_job_value": average_job_value,
            "payroll_ratio": payroll_ratio,
            "profit_margin": profit_margin,
            "completion_rate": completion_rate,
            "unpaid_ratio": unpaid_ratio,
            "unpaid_aging_summary": unpaid_aging_summary,
            "unpaid_risk_tasks": unpaid_risk_tasks,
            "repeat_clients_count": repeat_clients_count,
            "repeat_clients_revenue": repeat_clients_revenue,
            "top_repeat_clients": top_repeat_clients,
            "top_owner_clients": top_owner_clients,
            "top_owner_workers": top_owner_workers,
            "low_margin_clients": low_margin_clients,
            "negative_months": negative_months,
            "owner_monthly_metrics": owner_monthly_metrics,
            "owner_chart_data": owner_chart_data,
            "owner_month_comparison": owner_month_comparison
        }
    )


@app.get("/finance/summary", response_class=HTMLResponse)
async def finance_summary_page(request: Request, month: str = ""):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role not in ("boss", "manager"):
        return RedirectResponse("/", status_code=302)

    company_id = get_user_company_id(username)
    disabled_response = require_feature(company_id, "finance")

    if disabled_response:
        return disabled_response

    if not month:
        month = datetime.now().strftime("%Y-%m")

    conn = connect()
    c = conn.cursor()

    finance_rows = c.execute("""
    SELECT
        price,
        expense_total,
        payroll_total,
        profit
    FROM finance_summary
    WHERE company_id=?
      AND month=?
    """, (company_id, month)).fetchall()

    revenue = round(sum(float(row["price"] or 0) for row in finance_rows), 1)
    expenses = round(sum(float(row["expense_total"] or 0) for row in finance_rows), 1)
    payroll_total = round(sum(float(row["payroll_total"] or 0) for row in finance_rows), 1)
    profit = round(sum(float(row["profit"] or 0) for row in finance_rows), 1)
    net_profit = round(profit - payroll_total, 1)

    monthly_rows = c.execute("""
    SELECT
        month,
        SUM(price) as revenue,
        SUM(expense_total) as expenses,
        SUM(payroll_total) as payroll_total,
        SUM(profit) as profit
    FROM finance_summary
    WHERE company_id=?
    GROUP BY month
    ORDER BY month DESC
    LIMIT 12
    """, (company_id,)).fetchall()

    monthly_summary = []

    for row in monthly_rows:
        row_profit = round(float(row["profit"] or 0), 1)
        row_payroll = round(float(row["payroll_total"] or 0), 1)

        monthly_summary.append({
            "month": row["month"],
            "revenue": round(float(row["revenue"] or 0), 1),
            "expenses": round(float(row["expenses"] or 0), 1),
            "payroll_total": row_payroll,
            "profit": row_profit,
            "net_profit": round(row_profit - row_payroll, 1)
        })

    monthly_chart_data = list(reversed(monthly_summary))

    top_profitable_clients = c.execute("""
    SELECT
        client_name,
        SUM(profit) as total_profit,
        SUM(price) as revenue
    FROM finance_summary
    WHERE company_id=?
      AND month=?
    GROUP BY client_name
    ORDER BY total_profit DESC
    LIMIT 10
    """, (company_id, month)).fetchall()

    top_profitable_workers = c.execute("""
    SELECT
        users.username as worker_name,
        SUM(payroll_payouts.amount) as total_paid,
        COUNT(payroll_payouts.id) as payouts_count
    FROM payroll_payouts
    JOIN users ON users.id = payroll_payouts.worker_id
    WHERE payroll_payouts.company_id=?
      AND payroll_payouts.month=?
      AND payroll_payouts.status='paid'
    GROUP BY payroll_payouts.worker_id
    ORDER BY total_paid DESC
    LIMIT 10
    """, (company_id, month)).fetchall()

    conn.close()

    return templates.TemplateResponse(
        request,
        "finance_summary.html",
        {
            "request": request,
            "username": username,
            "role": role,
            "month": month,
            "revenue": revenue,
            "expenses": expenses,
            "payroll_total": payroll_total,
            "profit": profit,
            "net_profit": net_profit,
            "monthly_summary": monthly_summary,
            "monthly_chart_data": monthly_chart_data,
            "top_profitable_clients": top_profitable_clients,
            "top_profitable_workers": top_profitable_workers
        }
    )




@app.get("/finance", response_class=HTMLResponse)
async def finance_page(
    request: Request,
    month: str = "",
    payment_filter: str = "",
    worker: str = "",
    sort: str = "",
    profit_filter: str = ""
):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role == "superadmin":
        return RedirectResponse("/platform", status_code=302)

    if role not in ("boss", "manager"):
        return RedirectResponse("/", status_code=302)

    company_id = get_user_company_id(username)
    disabled_response = require_feature(company_id, "finance")

    if disabled_response:
        return disabled_response

    if not month:
        month = datetime.now().strftime("%Y-%m")
    selected_payment_filter = payment_filter if payment_filter in ("paid", "partial", "unpaid") else ""
    selected_worker = str(worker or "").strip()
    selected_sort = sort if sort in ("total", "profit", "margin", "expenses") else "date"
    selected_profit_filter = profit_filter if profit_filter == "loss" else ""

    conn = connect()
    c = conn.cursor()

    tasks = c.execute("""
    SELECT *
    FROM tasks
    WHERE archived=0 AND company_id=? AND task_date LIKE ?
    ORDER BY task_date DESC
    """, (company_id, f"{month}%")).fetchall()

    workers = c.execute("""
    SELECT id, username, commission_percent
    FROM users
    WHERE role='worker' AND company_id=?
    ORDER BY username
    """, (company_id,)).fetchall()
    worker_names = [row["username"] for row in workers]
    worker_ids = {
        row["username"]: row["id"]
        for row in workers
    }
    worker_commissions = {
        row["username"]: float(row["commission_percent"] or 0)
        for row in workers
    }
    payroll_payouts = c.execute("""
    SELECT worker_id, amount
    FROM payroll_payouts
    WHERE company_id=? AND month=? AND status='paid'
    """, (company_id, month)).fetchall()
    payroll_payout_map = {
        row["worker_id"]: round(float(row["amount"] or 0), 1)
        for row in payroll_payouts
    }

    if selected_worker not in worker_names:
        selected_worker = ""

    total_estimate = 0
    total_profit = 0
    total_expenses = 0
    total_discounts = 0
    paid_total = 0
    partial_total = 0
    unpaid_total = 0

    rows = []
    worker_finance = {}

    for task in tasks:
        if selected_worker and selected_worker not in get_task_worker_names(task):
            continue

        items = c.execute("""
        SELECT *
        FROM task_items
        WHERE task_id=?
        """, (task["id"],)).fetchall()
        expenses = c.execute("""
        SELECT *
        FROM task_expenses
        WHERE task_id=?
        """, (task["id"],)).fetchall()

        task_total = sum(item["total"] for item in items)
        task_profit = sum(item["profit"] for item in items)
        discount_amount = float(task["discount_amount"] or 0) if "discount_amount" in task.keys() else 0
        task_expenses_total = sum(expense["amount"] for expense in expenses)

        if not items:
            try:
                task_total = float(task["price"] or 0)
            except Exception:
                task_total = 0
            task_profit = 0

        if discount_amount < 0:
            discount_amount = 0

        task_total = max(task_total - discount_amount, 0)
        task_profit = task_profit - discount_amount - task_expenses_total

        payment_status = task["payment_status"] if "payment_status" in task.keys() else "Не оплачено"
        task_margin = round((task_profit / task_total) * 100, 1) if task_total else 0

        if selected_payment_filter == "paid" and payment_status != "Оплачено":
            continue
        if selected_payment_filter == "partial" and payment_status != "Частично оплачено":
            continue
        if selected_payment_filter == "unpaid" and payment_status != "Не оплачено":
            continue
        if selected_profit_filter == "loss" and task_profit >= 0:
            continue

        task_worker_names = [
            worker_name for worker_name in get_task_worker_names(task)
            if worker_name in worker_names
        ]

        if not task_worker_names:
            task_worker_names = ["Не назначены"]

        worker_share_count = len(task_worker_names)

        for worker_name in task_worker_names:
            if worker_name not in worker_finance:
                worker_finance[worker_name] = {
                    "worker_id": worker_ids.get(worker_name),
                    "worker": worker_name,
                    "commission_percent": worker_commissions.get(worker_name, 0),
                    "tasks": 0,
                    "total": 0,
                    "expenses": 0,
                    "profit": 0,
                    "payout": 0,
                    "margin": 0
                }

            worker_finance[worker_name]["tasks"] += 1
            worker_finance[worker_name]["total"] += task_total / worker_share_count
            worker_finance[worker_name]["expenses"] += task_expenses_total / worker_share_count
            worker_finance[worker_name]["profit"] += task_profit / worker_share_count

        total_estimate += task_total
        total_profit += task_profit
        total_expenses += task_expenses_total
        total_discounts += discount_amount

        if payment_status == "Оплачено":
            paid_total += task_total
        elif payment_status == "Частично оплачено":
            partial_total += task_total
        else:
            unpaid_total += task_total

        rows.append({
            "id": task["id"],
            "client": task["client"],
            "worker": format_task_workers(task),
            "task_date": task["task_date"],
            "status": task["status"],
            "payment_status": payment_status,
            "discount": discount_amount,
            "total": task_total,
            "expenses": task_expenses_total,
            "profit": task_profit,
            "margin": task_margin
        })

    if selected_sort == "total":
        rows.sort(key=lambda row: row["total"], reverse=True)
    elif selected_sort == "profit":
        rows.sort(key=lambda row: row["profit"], reverse=True)
    elif selected_sort == "margin":
        rows.sort(key=lambda row: row["margin"], reverse=True)
    elif selected_sort == "expenses":
        rows.sort(key=lambda row: row["expenses"], reverse=True)

    worker_finance_stats = []

    for worker_row in worker_finance.values():
        worker_row["total"] = round(worker_row["total"], 1)
        worker_row["expenses"] = round(worker_row["expenses"], 1)
        worker_row["profit"] = round(worker_row["profit"], 1)
        worker_row["payout"] = round(worker_row["profit"] * worker_row["commission_percent"] / 100, 1)
        worker_row["paid_amount"] = payroll_payout_map.get(worker_row["worker_id"], 0)
        worker_row["due_amount"] = round(max(worker_row["payout"] - worker_row["paid_amount"], 0), 1)
        worker_row["payout_status"] = "Не выплачено"
        if worker_row["paid_amount"] > 0:
            worker_row["payout_status"] = "Выплачено" if worker_row["paid_amount"] >= worker_row["payout"] else "Частично"
        worker_row["margin"] = round((worker_row["profit"] / worker_row["total"]) * 100, 1) if worker_row["total"] else 0
        worker_finance_stats.append(worker_row)

    worker_finance_stats.sort(key=lambda row: row["profit"], reverse=True)
    total_worker_payout = round(sum(row["payout"] for row in worker_finance_stats), 1)
    total_worker_paid = round(sum(row["paid_amount"] for row in worker_finance_stats), 1)
    total_worker_due = round(sum(row["due_amount"] for row in worker_finance_stats), 1)

    settings = get_company_settings(company_id)

    conn.close()
    total_margin = round((total_profit / total_estimate) * 100, 1) if total_estimate else 0
    average_estimate = round(total_estimate / len(rows), 1) if rows else 0
    outstanding_total = partial_total + unpaid_total

    return templates.TemplateResponse(
        request,
        "finance.html",
        {
            "request": request,
            "username": username,
            "role": role,
            "month": month,
            "selected_payment_filter": selected_payment_filter,
            "selected_worker": selected_worker,
            "selected_sort": selected_sort,
            "selected_profit_filter": selected_profit_filter,
            "workers": workers,
            "worker_finance_stats": worker_finance_stats,
            "rows": rows,
            "total_estimate": total_estimate,
            "total_profit": total_profit,
            "total_expenses": total_expenses,
            "total_discounts": total_discounts,
            "total_margin": total_margin,
            "average_estimate": average_estimate,
            "outstanding_total": outstanding_total,
            "paid_total": paid_total,
            "partial_total": partial_total,
            "unpaid_total": unpaid_total,
            "total_worker_payout": total_worker_payout,
            "total_worker_paid": total_worker_paid,
            "total_worker_due": total_worker_due,
            "settings": settings
        }
    )


@app.get("/payroll", response_class=HTMLResponse)
async def payroll_page(request: Request, month: str = "", payout_filter: str = ""):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role == "superadmin":
        return RedirectResponse("/platform", status_code=302)

    if role not in ("boss", "manager"):
        return RedirectResponse("/", status_code=302)

    company_id = get_user_company_id(username)
    disabled_response = require_feature(company_id, "payroll")

    if disabled_response:
        return disabled_response

    if not month:
        month = datetime.now().strftime("%Y-%m")
    selected_payout_filter = payout_filter if payout_filter in ("positive", "paid", "partial", "unpaid") else ""

    conn = connect()
    c = conn.cursor()

    workers = c.execute("""
    SELECT id, username, full_name, commission_percent
    FROM users
    WHERE role='worker' AND company_id=?
    ORDER BY username
    """, (company_id,)).fetchall()
    worker_map = {
        worker["username"]: worker
        for worker in workers
    }

    tasks = c.execute("""
    SELECT *
    FROM tasks
    WHERE archived=0 AND company_id=? AND task_date LIKE ?
    """, (company_id, f"{month}%")).fetchall()

    paid_payouts = c.execute("""
    SELECT worker_id, amount, paid_at, paid_by, note
    FROM payroll_payouts
    WHERE company_id=? AND month=? AND status='paid'
    """, (company_id, month)).fetchall()
    paid_payout_map = {
        payout["worker_id"]: payout
        for payout in paid_payouts
    }
    payout_history_rows = c.execute("""
    SELECT
        p.worker_id,
        p.amount,
        p.paid_at,
        p.paid_by,
        p.note,
        u.username,
        u.full_name
    FROM payroll_payouts p
    JOIN users u ON u.id=p.worker_id
    WHERE p.company_id=? AND p.month=? AND p.status='paid'
    ORDER BY p.paid_at DESC
    """, (company_id, month)).fetchall()
    payout_history = [
        {
            "worker_id": row["worker_id"],
            "worker_name": row["full_name"] or row["username"],
            "worker_username": row["username"],
            "amount": round(float(row["amount"] or 0), 1),
            "paid_at": row["paid_at"],
            "paid_by": row["paid_by"],
            "note": row["note"] or ""
        }
        for row in payout_history_rows
    ]

    payroll_rows = {
        worker["username"]: {
            "id": worker["id"],
            "username": worker["username"],
            "name": worker["full_name"] or worker["username"],
            "commission_percent": float(worker["commission_percent"] or 0),
            "tasks": 0,
            "total": 0,
            "profit": 0,
            "payout": 0
        }
        for worker in workers
    }

    for task in tasks:
        task_worker_names = [
            worker_name for worker_name in get_task_worker_names(task)
            if worker_name in worker_map
        ]

        if not task_worker_names:
            continue

        items = c.execute("""
        SELECT *
        FROM task_items
        WHERE task_id=?
        """, (task["id"],)).fetchall()
        expenses = c.execute("""
        SELECT *
        FROM task_expenses
        WHERE task_id=?
        """, (task["id"],)).fetchall()

        task_total = sum(item["total"] for item in items)
        task_profit = sum(item["profit"] for item in items)
        discount_amount = float(task["discount_amount"] or 0) if "discount_amount" in task.keys() else 0
        task_expenses_total = sum(expense["amount"] for expense in expenses)

        if not items:
            try:
                task_total = float(task["price"] or 0)
            except Exception:
                task_total = 0
            task_profit = 0

        if discount_amount < 0:
            discount_amount = 0

        task_total = max(task_total - discount_amount, 0)
        task_profit = task_profit - discount_amount - task_expenses_total
        share_count = len(task_worker_names)

        for worker_name in task_worker_names:
            payroll_rows[worker_name]["tasks"] += 1
            payroll_rows[worker_name]["total"] += task_total / share_count
            payroll_rows[worker_name]["profit"] += task_profit / share_count

    rows = []

    for row in payroll_rows.values():
        row["total"] = round(row["total"], 1)
        row["profit"] = round(row["profit"], 1)
        row["payout"] = round(row["profit"] * row["commission_percent"] / 100, 1)
        paid_payout = paid_payout_map.get(row["id"])
        row["payout_paid"] = bool(paid_payout)
        row["paid_at"] = paid_payout["paid_at"] if paid_payout else ""
        row["paid_by"] = paid_payout["paid_by"] if paid_payout else ""
        row["payout_note"] = paid_payout["note"] if paid_payout else ""
        row["paid_amount"] = round(float(paid_payout["amount"] or 0), 1) if paid_payout else 0
        row["due_amount"] = round(max(row["payout"] - row["paid_amount"], 0), 1)
        row["payout_status"] = "Не выплачено"
        if row["payout_paid"]:
            row["payout_status"] = "Выплачено" if row["paid_amount"] >= row["payout"] else "Частично"
        rows.append(row)

    if selected_payout_filter == "positive":
        rows = [row for row in rows if row["payout"] > 0]
    if selected_payout_filter == "paid":
        rows = [row for row in rows if row["payout"] > 0 and row["payout_paid"] and row["paid_amount"] >= row["payout"]]
    if selected_payout_filter == "partial":
        rows = [row for row in rows if row["payout"] > 0 and row["payout_paid"] and row["paid_amount"] < row["payout"]]
    if selected_payout_filter == "unpaid":
        rows = [row for row in rows if row["payout"] > 0 and not row["payout_paid"]]

    rows.sort(key=lambda row: row["payout"], reverse=True)
    total_payout = round(sum(row["payout"] for row in rows), 1)
    total_paid = round(sum(row["paid_amount"] for row in rows if row["payout_paid"]), 1)
    total_due = round(sum(row["due_amount"] for row in rows), 1)
    total_profit = round(sum(row["profit"] for row in rows), 1)
    settings = get_company_settings(company_id)

    conn.close()

    return templates.TemplateResponse(
        request,
        "payroll.html",
        {
            "request": request,
            "username": username,
            "role": role,
            "month": month,
            "selected_payout_filter": selected_payout_filter,
            "rows": rows,
            "total_payout": total_payout,
            "total_paid": total_paid,
            "total_due": total_due,
            "total_profit": total_profit,
            "payout_history": payout_history,
            "settings": settings
        }
    )


@app.get("/payroll/history", response_class=HTMLResponse)
async def payroll_history_page(request: Request, month: str = "", worker: str = "", paid_by: str = "", date_from: str = "", date_to: str = "", sort: str = "date_desc"):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role not in ("boss", "manager"):
        return RedirectResponse("/", status_code=302)

    company_id = get_user_company_id(username)
    disabled_response = require_feature(company_id, "payroll")

    if disabled_response:
        return disabled_response

    if not month:
        month = datetime.now().strftime("%Y-%m")

    conn = connect()
    c = conn.cursor()

    query = """
    SELECT
        p.id,
        p.worker_id,
        p.amount,
        p.paid_at,
        p.paid_by,
        p.note,
        u.full_name as worker_name,
        u.username as worker_username
    FROM payroll_payouts p
    JOIN users u ON u.id=p.worker_id
    WHERE p.company_id=?
      AND p.month=?
    """

    params = [company_id, month]

    if worker:
        query += """
          AND (
            lower(u.username) LIKE ?
            OR lower(u.full_name) LIKE ?
          )
        """
        search = f"%{worker.lower()}%"
        params.extend([search, search])

    if paid_by:
        query += """
          AND lower(p.paid_by) LIKE ?
        """
        params.append(f"%{paid_by.lower()}%")

    if date_from:
        query += """
          AND p.paid_at >= ?
        """
        params.append(date_from)

    if date_to:
        query += """
          AND p.paid_at <= ?
        """
        params.append(date_to + " 23:59")

    if sort == "date_asc":
        query += """
        ORDER BY p.paid_at ASC
        """
    elif sort == "amount_desc":
        query += """
        ORDER BY p.amount DESC
        """
    elif sort == "amount_asc":
        query += """
        ORDER BY p.amount ASC
        """
    elif sort == "worker":
        query += """
        ORDER BY u.username ASC
        """
    else:
        sort = "date_desc"
        query += """
        ORDER BY p.paid_at DESC
        """

    payout_history_rows = c.execute(query, params).fetchall()

    payout_history = [
        dict(row)
        for row in payout_history_rows
    ]

    total_paid = round(sum(
        float(row["amount"] or 0)
        for row in payout_history
    ), 1)

    payouts_count = len(payout_history)

    workers_count = len(set(
        row["worker_id"]
        for row in payout_history
    ))

    average_payout = round(
        total_paid / payouts_count,
        1
    ) if payouts_count else 0

    top_workers_map = {}

    for row in payout_history:
        key = row["worker_id"]

        if key not in top_workers_map:
            top_workers_map[key] = {
                "worker_id": row["worker_id"],
                "worker_name": row["worker_name"],
                "worker_username": row["worker_username"],
                "amount": 0
            }

        top_workers_map[key]["amount"] += float(row["amount"] or 0)

    top_workers = sorted(
        top_workers_map.values(),
        key=lambda item: item["amount"],
        reverse=True
    )[:3]

    for item in top_workers:
        item["amount"] = round(item["amount"], 1)

    conn.close()

    return templates.TemplateResponse(
        request,
        "payroll_history.html",
        {
            "request": request,
            "username": username,
            "role": role,
            "month": month,
            "worker": worker,
            "paid_by": paid_by,
            "date_from": date_from,
            "date_to": date_to,
            "sort": sort,
            "payout_history": payout_history,
            "total_paid": total_paid,
            "payouts_count": payouts_count,
            "workers_count": workers_count,
            "average_payout": average_payout,
            "top_workers": top_workers
        }
    )


@app.get("/payroll/history/export")
async def payroll_history_export(
    request: Request,
    month: str = "",
    worker: str = "",
    paid_by: str = "",
    date_from: str = "",
    date_to: str = "",
    sort: str = "date_desc"
):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role not in ("boss", "manager"):
        return RedirectResponse("/", status_code=302)

    company_id = get_user_company_id(username)

    disabled_response = require_feature(company_id, "payroll")

    if disabled_response:
        return disabled_response


    if not month:
        month = datetime.now().strftime("%Y-%m")

    conn = connect()
    c = conn.cursor()

    query = """
    SELECT
        p.month,
        p.amount,
        p.paid_at,
        p.paid_by,
        p.note,
        u.username,
        u.full_name,
        u.position
    FROM payroll_payouts p
    JOIN users u ON u.id=p.worker_id
    WHERE p.company_id=?
      AND p.month=?
    """

    params = [company_id, month]

    if worker:
        query += """
          AND (
            lower(u.username) LIKE ?
            OR lower(u.full_name) LIKE ?
          )
        """
        search = f"%{worker.lower()}%"
        params.extend([search, search])

    if paid_by:
        query += """
          AND lower(p.paid_by) LIKE ?
        """
        params.append(f"%{paid_by.lower()}%")

    if date_from:
        query += """
          AND p.paid_at >= ?
        """
        params.append(date_from)

    if date_to:
        query += """
          AND p.paid_at <= ?
        """
        params.append(date_to + " 23:59")

    if sort == "date_asc":
        query += """
        ORDER BY p.paid_at ASC
        """
    elif sort == "amount_desc":
        query += """
        ORDER BY p.amount DESC
        """
    elif sort == "amount_asc":
        query += """
        ORDER BY p.amount ASC
        """
    elif sort == "worker":
        query += """
        ORDER BY u.username ASC
        """
    else:
        sort = "date_desc"
        query += """
        ORDER BY p.paid_at DESC
        """

    payouts = c.execute(query, params).fetchall()

    conn.close()

    output = io.StringIO()
    writer = csv.writer(output)

    writer.writerow(["Журнал выплат"])
    writer.writerow(["Месяц", month])
    writer.writerow(["Фильтр исполнитель", worker or ""])
    writer.writerow(["Фильтр кем выплачено", paid_by or ""])
    writer.writerow(["Дата от", date_from or ""])
    writer.writerow(["Дата до", date_to or ""])
    writer.writerow(["Сортировка", sort])
    writer.writerow([])

    writer.writerow([
        "Исполнитель",
        "ФИО",
        "Должность",
        "Месяц",
        "Сумма выплаты",
        "Дата выплаты",
        "Кем выплачено",
        "Комментарий"
    ])

    total_paid = 0

    for payout in payouts:
        amount = round(float(payout["amount"] or 0), 1)
        total_paid += amount

        writer.writerow([
            payout["username"],
            payout["full_name"] or "",
            payout["position"] or "",
            payout["month"],
            amount,
            payout["paid_at"] or "",
            payout["paid_by"] or "",
            payout["note"] or ""
        ])

    writer.writerow([])
    writer.writerow(["Итого выплачено", round(total_paid, 1)])

    response = Response(
        content=output.getvalue(),
        media_type="text/csv; charset=utf-8"
    )

    response.headers["Content-Disposition"] = f"attachment; filename=payroll_history_{month}.csv"

    return response


@app.get("/payroll/export")
async def payroll_export(request: Request, month: str = "", payout_filter: str = ""):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role != "boss":
        return RedirectResponse("/", status_code=302)

    if not month:
        month = datetime.now().strftime("%Y-%m")
    selected_payout_filter = payout_filter if payout_filter in ("positive", "paid", "partial", "unpaid") else ""

    company_id = get_user_company_id(username)
    disabled_response = require_feature(company_id, "payroll")

    if disabled_response:
        return disabled_response

    conn = connect()
    c = conn.cursor()

    workers = c.execute("""
    SELECT id, username, full_name, commission_percent
    FROM users
    WHERE role='worker' AND company_id=?
    ORDER BY username
    """, (company_id,)).fetchall()
    worker_map = {
        worker["username"]: worker
        for worker in workers
    }

    tasks = c.execute("""
    SELECT *
    FROM tasks
    WHERE archived=0 AND company_id=? AND task_date LIKE ?
    """, (company_id, f"{month}%")).fetchall()

    paid_payouts = c.execute("""
    SELECT worker_id, amount, paid_at, paid_by, note
    FROM payroll_payouts
    WHERE company_id=? AND month=? AND status='paid'
    """, (company_id, month)).fetchall()
    paid_payout_map = {
        payout["worker_id"]: payout
        for payout in paid_payouts
    }

    payroll_rows = {
        worker["username"]: {
            "id": worker["id"],
            "username": worker["username"],
            "name": worker["full_name"] or worker["username"],
            "commission_percent": float(worker["commission_percent"] or 0),
            "tasks": 0,
            "total": 0,
            "profit": 0,
            "payout": 0
        }
        for worker in workers
    }

    for task in tasks:
        task_worker_names = [
            worker_name for worker_name in get_task_worker_names(task)
            if worker_name in worker_map
        ]

        if not task_worker_names:
            continue

        items = c.execute("""
        SELECT *
        FROM task_items
        WHERE task_id=?
        """, (task["id"],)).fetchall()
        expenses = c.execute("""
        SELECT *
        FROM task_expenses
        WHERE task_id=?
        """, (task["id"],)).fetchall()

        task_total = sum(item["total"] for item in items)
        task_profit = sum(item["profit"] for item in items)
        discount_amount = float(task["discount_amount"] or 0) if "discount_amount" in task.keys() else 0
        task_expenses_total = sum(expense["amount"] for expense in expenses)

        if not items:
            try:
                task_total = float(task["price"] or 0)
            except Exception:
                task_total = 0
            task_profit = 0

        if discount_amount < 0:
            discount_amount = 0

        task_total = max(task_total - discount_amount, 0)
        task_profit = task_profit - discount_amount - task_expenses_total
        share_count = len(task_worker_names)

        for worker_name in task_worker_names:
            payroll_rows[worker_name]["tasks"] += 1
            payroll_rows[worker_name]["total"] += task_total / share_count
            payroll_rows[worker_name]["profit"] += task_profit / share_count

    rows = []

    for row in payroll_rows.values():
        row["total"] = round(row["total"], 1)
        row["profit"] = round(row["profit"], 1)
        row["payout"] = round(row["profit"] * row["commission_percent"] / 100, 1)
        paid_payout = paid_payout_map.get(row["id"])
        row["payout_paid"] = bool(paid_payout)
        row["paid_at"] = paid_payout["paid_at"] if paid_payout else ""
        row["paid_by"] = paid_payout["paid_by"] if paid_payout else ""
        row["payout_note"] = paid_payout["note"] if paid_payout else ""
        row["paid_amount"] = round(float(paid_payout["amount"] or 0), 1) if paid_payout else 0
        row["due_amount"] = round(max(row["payout"] - row["paid_amount"], 0), 1)
        row["payout_status"] = "Не выплачено"
        if row["payout_paid"]:
            row["payout_status"] = "Выплачено" if row["paid_amount"] >= row["payout"] else "Частично"
        rows.append(row)

    if selected_payout_filter == "positive":
        rows = [row for row in rows if row["payout"] > 0]
    if selected_payout_filter == "paid":
        rows = [row for row in rows if row["payout"] > 0 and row["payout_paid"] and row["paid_amount"] >= row["payout"]]
    if selected_payout_filter == "partial":
        rows = [row for row in rows if row["payout"] > 0 and row["payout_paid"] and row["paid_amount"] < row["payout"]]
    if selected_payout_filter == "unpaid":
        rows = [row for row in rows if row["payout"] > 0 and not row["payout_paid"]]

    rows.sort(key=lambda row: row["payout"], reverse=True)
    total_payout = round(sum(row["payout"] for row in rows), 1)
    total_paid = round(sum(row["paid_amount"] for row in rows if row["payout_paid"]), 1)
    total_due = round(sum(row["due_amount"] for row in rows), 1)
    total_profit = round(sum(row["profit"] for row in rows), 1)

    conn.close()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "Исполнитель",
        "Логин",
        "Заявки",
        "Выручка",
        "Прибыль",
        "Процент",
        "Выплата",
        "Фактически выплачено",
        "Осталось выплатить",
        "Статус выплаты",
        "Дата выплаты",
        "Кем выплачено",
        "Комментарий"
    ])

    for row in rows:
        writer.writerow([
            row["name"],
            row["username"],
            row["tasks"],
            row["total"],
            row["profit"],
            row["commission_percent"],
            row["payout"],
            row["paid_amount"],
            row["due_amount"],
            row["payout_status"],
            row["paid_at"],
            row["paid_by"],
            row["payout_note"]
        ])

    writer.writerow([])
    writer.writerow(["Итого прибыль", total_profit])
    writer.writerow(["Итого выплаты", total_payout])
    writer.writerow(["Итого выплачено", total_paid])
    writer.writerow(["Итого осталось", total_due])

    content = output.getvalue()
    output.close()

    return Response(
        content,
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f"attachment; filename=payroll_{month}.csv"
        }
    )


@app.post("/payroll/{worker_id}/mark-paid")
async def mark_payroll_paid(request: Request, worker_id: int):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role != "boss":
        return RedirectResponse("/payroll?error=only_boss", status_code=302)

    company_id = get_user_company_id(username)

    disabled_response = require_feature(company_id, "payroll")

    if disabled_response:
        return disabled_response


    form = await request.form()
    month = (form.get("month") or datetime.now().strftime("%Y-%m")).strip()
    amount = form.get("amount") or "0"
    note = (form.get("note") or "").strip()
    payout_filter = form.get("payout_filter") or ""
    selected_payout_filter = payout_filter if payout_filter in ("positive", "paid", "partial", "unpaid") else ""

    try:
        amount = float(str(amount).replace(",", "."))
    except Exception:
        amount = 0

    if amount < 0:
        amount = 0

    conn = connect()
    c = conn.cursor()

    worker = c.execute("""
    SELECT *
    FROM users
    WHERE id=? AND company_id=? AND role='worker'
    """, (worker_id, company_id)).fetchone()

    if not worker:
        conn.close()
        redirect_url = f"/payroll?month={month}"
        if selected_payout_filter:
            redirect_url += f"&payout_filter={selected_payout_filter}"
        return RedirectResponse(redirect_url, status_code=302)

    paid_at = datetime.now().strftime("%Y-%m-%d %H:%M")

    c.execute("""
    INSERT INTO payroll_payouts (
        company_id,
        worker_id,
        month,
        amount,
        status,
        paid_at,
        paid_by,
        note
    )
    VALUES (?, ?, ?, ?, 'paid', ?, ?, ?)
    ON CONFLICT(company_id, worker_id, month)
    DO UPDATE SET
        amount=excluded.amount,
        status='paid',
        paid_at=excluded.paid_at,
        paid_by=excluded.paid_by,
        note=excluded.note
    """, (company_id, worker_id, month, amount, paid_at, username, note))

    conn.commit()
    conn.close()

    redirect_url = f"/payroll?month={month}&payout_paid=1"
    if selected_payout_filter:
        redirect_url += f"&payout_filter={selected_payout_filter}"
    return RedirectResponse(redirect_url, status_code=302)


@app.post("/payroll/{worker_id}/note")
async def update_payroll_payout_note(request: Request, worker_id: int):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role != "boss":
        return RedirectResponse("/payroll?error=only_boss", status_code=302)

    company_id = get_user_company_id(username)

    disabled_response = require_feature(company_id, "payroll")

    if disabled_response:
        return disabled_response


    form = await request.form()
    month = (form.get("month") or datetime.now().strftime("%Y-%m")).strip()
    note = (form.get("note") or "").strip()
    payout_filter = form.get("payout_filter") or ""
    selected_payout_filter = payout_filter if payout_filter in ("positive", "paid", "partial", "unpaid") else ""

    conn = connect()
    c = conn.cursor()

    c.execute("""
    UPDATE payroll_payouts
    SET note=?
    WHERE company_id=? AND worker_id=? AND month=? AND status='paid'
    """, (note, company_id, worker_id, month))

    conn.commit()
    conn.close()

    redirect_url = f"/payroll?month={month}&payout_note_updated=1"
    if selected_payout_filter:
        redirect_url += f"&payout_filter={selected_payout_filter}"
    return RedirectResponse(redirect_url, status_code=302)


@app.post("/payroll/{worker_id}/mark-unpaid")
async def mark_payroll_unpaid(request: Request, worker_id: int):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role != "boss":
        return RedirectResponse("/payroll?error=only_boss", status_code=302)

    company_id = get_user_company_id(username)

    disabled_response = require_feature(company_id, "payroll")

    if disabled_response:
        return disabled_response


    form = await request.form()
    month = (form.get("month") or datetime.now().strftime("%Y-%m")).strip()
    payout_filter = form.get("payout_filter") or ""
    selected_payout_filter = payout_filter if payout_filter in ("positive", "paid", "partial", "unpaid") else ""

    conn = connect()
    c = conn.cursor()

    c.execute("""
    DELETE FROM payroll_payouts
    WHERE company_id=? AND worker_id=? AND month=?
    """, (company_id, worker_id, month))

    conn.commit()
    conn.close()

    redirect_url = f"/payroll?month={month}&payout_unpaid=1"
    if selected_payout_filter:
        redirect_url += f"&payout_filter={selected_payout_filter}"
    return RedirectResponse(redirect_url, status_code=302)


@app.get("/reports", response_class=HTMLResponse)
async def reports_page(request: Request, month: str = ""):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    update_last_seen(username)
    role = get_role(username)

    if role not in ("boss", "manager"):
        return RedirectResponse("/", status_code=302)

    company_id = get_user_company_id(username)
    disabled_response = require_feature(company_id, "analytics")

    if disabled_response:
        return disabled_response

    if not month:
        month = datetime.now().strftime("%Y-%m")

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
    disabled_response = require_feature(company_id, "calls")

    if disabled_response:
        return disabled_response

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



@app.get("/ai/insights", response_class=HTMLResponse)
async def ai_insights_page(request: Request):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role not in ("boss", "manager"):
        return RedirectResponse("/", status_code=302)

    company_id = get_user_company_id(username)
    disabled_response = require_feature(company_id, "ai_insights")

    if disabled_response:
        return disabled_response

    settings = get_company_settings(company_id)

    conn = connect()
    c = conn.cursor()

    overdue_tasks = c.execute("""
    SELECT COUNT(*)
    FROM tasks
    WHERE company_id=?
      AND archived=0
      AND status!='Завершено'
      AND task_date < date('now')
    """, (company_id,)).fetchone()[0]

    unpaid_total = c.execute("""
    SELECT COALESCE(SUM(price), 0)
    FROM tasks
    WHERE company_id=?
      AND archived=0
      AND payment_status!='Оплачено'
    """, (company_id,)).fetchone()[0]

    low_margin_clients = c.execute("""
    SELECT
        client,
        COUNT(*) as tasks_count,
        COALESCE(SUM(price), 0) as revenue
    FROM tasks
    WHERE company_id=?
      AND archived=0
    GROUP BY client
    HAVING revenue > 0
    ORDER BY revenue ASC
    LIMIT 5
    """, (company_id,)).fetchall()

    worker_rows = c.execute("""
    SELECT username
    FROM users
    WHERE company_id=?
      AND role='worker'
    ORDER BY username
    """, (company_id,)).fetchall()

    weak_workers = []

    for worker_row in worker_rows:
        worker_name = worker_row["username"]
        worker_condition = worker_task_condition()
        worker_params = worker_task_params(worker_name)

        completed_count = c.execute(f"""
        SELECT COUNT(*)
        FROM tasks
        WHERE company_id=?
          AND archived=0
          AND status='Завершено'
          AND {worker_condition}
        """, [company_id] + worker_params).fetchone()[0]

        active_count = c.execute(f"""
        SELECT COUNT(*)
        FROM tasks
        WHERE company_id=?
          AND archived=0
          AND status!='Завершено'
          AND {worker_condition}
        """, [company_id] + worker_params).fetchone()[0]

        weak_workers.append({
            "username": worker_name,
            "completed_count": completed_count,
            "active_count": active_count
        })

    weak_workers.sort(key=lambda row: (row["completed_count"], -row["active_count"]))

    insights = []

    if overdue_tasks:
        insights.append({
            "level": "danger",
            "title": "Есть риск по просрочкам",
            "message": f"Просрочено {overdue_tasks} {settings['task_label'] or 'задач'}. Рекомендуется проверить ответственных и сроки."
        })

    if unpaid_total:
        insights.append({
            "level": "warning",
            "title": "Есть риск неоплаты",
            "message": f"Неоплаченная сумма: ₽{round(float(unpaid_total or 0), 1)}. Рекомендуется запустить напоминания клиентам."
        })

    if weak_workers:
        weakest_worker = weak_workers[0]
        insights.append({
            "level": "info",
            "title": "Сотрудник требует внимания",
            "message": f"{settings['worker_label'] or 'Сотрудник'} {weakest_worker['username']} имеет мало завершённых задач: {weakest_worker['completed_count']}."
        })

    if low_margin_clients:
        client = low_margin_clients[0]
        insights.append({
            "level": "info",
            "title": "Клиент с низкой выручкой",
            "message": f"{settings['client_label'] or 'Клиент'} {client['client'] or 'Не указан'} принёс ₽{round(float(client['revenue'] or 0), 1)}."
        })

    if not insights:
        insights.append({
            "level": "success",
            "title": "Критичных рисков не найдено",
            "message": "Сейчас система не видит явных проблем по просрочкам, оплатам и сотрудникам."
        })

    risk_score = 0

    risk_score += overdue_tasks * 10

    if unpaid_total:
        risk_score += min(int(float(unpaid_total) / 1000), 40)

    if weak_workers:
        weakest_worker = weak_workers[0]
        if weakest_worker["completed_count"] == 0:
            risk_score += 20

    if risk_score > 100:
        risk_score = 100

    if risk_score >= 70:
        risk_level = "danger"
        risk_title = "Высокий риск"
    elif risk_score >= 40:
        risk_level = "warning"
        risk_title = "Средний риск"
    else:
        risk_level = "success"
        risk_title = "Низкий риск"

    weekly_summary = []

    weekly_summary.append(f"За неделю система видит {overdue_tasks} просроченных {settings['task_label'] or 'задач'}.")

    if unpaid_total:
        weekly_summary.append(f"Неоплаченная сумма составляет ₽{round(float(unpaid_total or 0), 1)}.")

    if weak_workers:
        weekly_summary.append(f"Требует внимания {settings['worker_label'] or 'сотрудник'}: {weak_workers[0]['username']}.")

    weekly_summary.append(f"Общий уровень риска: {risk_title} ({risk_score}/100).")

    conn.close()

    return templates.TemplateResponse(
        request,
        "ai_insights.html",
        {
            "request": request,
            "username": username,
            "role": role,
            "settings": settings,
            "insights": insights,
            "overdue_tasks": overdue_tasks,
            "unpaid_total": unpaid_total,
            "weak_workers": weak_workers[:5],
            "low_margin_clients": low_margin_clients,
            "risk_score": risk_score,
            "risk_level": risk_level,
            "risk_title": risk_title,
            "weekly_summary": weekly_summary
        }
    )


@app.get("/ai/assistant", response_class=HTMLResponse)
async def ai_assistant_page(
    request: Request,
    note_filter: str = "",
    note_search: str = "",
    event_filter: str = ""
):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role not in ("boss", "manager"):
        return RedirectResponse("/", status_code=302)

    company_id = get_user_company_id(username)
    disabled_response = require_feature(company_id, "ai_insights")

    if disabled_response:
        return disabled_response

    assistant = build_owner_ai_assistant_context(
        company_id,
        note_filter,
        note_search,
        event_filter
    )

    return templates.TemplateResponse(
        request,
        "ai_assistant.html",
        {
            "request": request,
            "username": username,
            "role": role,
            "settings": assistant["settings"],
            "metrics": assistant["metrics"],
            "priorities": assistant["priorities"],
            "next_steps": assistant["next_steps"],
            "overdue_rows": assistant["overdue_rows"],
            "action_history": assistant["action_history"],
            "assistant_notes": assistant["assistant_notes"],
            "ai_events": assistant["ai_events"],
            "selected_note_filter": assistant["selected_note_filter"],
            "selected_note_search": assistant["selected_note_search"],
            "selected_event_filter": assistant["selected_event_filter"],
            "completed_notes": assistant["completed_notes"],
            "features": get_company_features(company_id)
        }
    )


@app.get("/ai/assistant/events/export")
async def ai_assistant_events_export(request: Request, event_filter: str = ""):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role not in ("boss", "manager"):
        return RedirectResponse("/", status_code=302)

    company_id = get_user_company_id(username)
    disabled_response = require_feature(company_id, "ai_insights")

    if disabled_response:
        return disabled_response

    selected_event_filter = event_filter if event_filter in (
        "created",
        "notification_sent",
        "postponed",
        "done"
    ) else ""
    event_filter_sql = ""
    event_params = [company_id]

    if selected_event_filter:
        event_filter_sql = "AND action=?"
        event_params.append(selected_event_filter)

    conn = connect()
    c = conn.cursor()

    events = c.execute(f"""
    SELECT *
    FROM ai_assistant_events
    WHERE company_id=?
      {event_filter_sql}
    ORDER BY id DESC
    LIMIT 500
    """, event_params).fetchall()

    conn.close()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Дата", "Автор", "Действие", "Заметка ID", "Детали"])

    for event in events:
        writer.writerow([
            event["created_at"],
            event["username"],
            event["action"],
            event["note_id"],
            event["details"],
        ])

    content = output.getvalue()
    output.close()

    return Response(
        content,
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f"attachment; filename=ai_assistant_events_{selected_event_filter or 'all'}.csv"
        }
    )


@app.post("/ai/assistant/notes")
async def add_ai_assistant_note(request: Request):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role not in ("boss", "manager"):
        return RedirectResponse("/", status_code=302)

    company_id = get_user_company_id(username)
    disabled_response = require_feature(company_id, "ai_insights")

    if disabled_response:
        return disabled_response

    form = await request.form()
    note = str(form.get("note") or "").strip()
    priority = str(form.get("priority") or "normal").strip()
    follow_up_date = str(form.get("follow_up_date") or "").strip()

    if priority not in ("urgent", "normal", "later"):
        priority = "normal"

    if follow_up_date:
        try:
            datetime.strptime(follow_up_date, "%Y-%m-%d")
        except Exception:
            follow_up_date = ""

    if not note:
        return RedirectResponse("/ai/assistant?note_error=empty", status_code=302)

    conn = connect()
    c = conn.cursor()

    c.execute("""
    INSERT INTO ai_assistant_notes (
        company_id, username, note, priority, follow_up_date, created_at
    )
    VALUES (?, ?, ?, ?, ?, ?)
    """, (
        company_id,
        username,
        note,
        priority,
        follow_up_date,
        datetime.now().strftime("%Y-%m-%d %H:%M")
    ))

    conn.commit()
    note_id = c.lastrowid
    conn.close()

    log_ai_assistant_event(
        company_id,
        note_id,
        username,
        "created",
        note
    )

    return RedirectResponse("/ai/assistant?note_created=1", status_code=302)


@app.post("/ai/assistant/notes/{note_id}/done")
async def complete_ai_assistant_note(request: Request, note_id: int):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role not in ("boss", "manager"):
        return RedirectResponse("/", status_code=302)

    company_id = get_user_company_id(username)
    disabled_response = require_feature(company_id, "ai_insights")

    if disabled_response:
        return disabled_response

    conn = connect()
    c = conn.cursor()

    c.execute("""
    UPDATE ai_assistant_notes
    SET is_done=1,
        done_by=?,
        done_at=?
    WHERE id=?
      AND company_id=?
    """, (
        username,
        datetime.now().strftime("%Y-%m-%d %H:%M"),
        note_id,
        company_id
    ))

    conn.commit()
    conn.close()

    log_ai_assistant_event(
        company_id,
        note_id,
        username,
        "done",
        "AI заметка выполнена"
    )

    return RedirectResponse("/ai/assistant?note_done=1", status_code=302)


@app.post("/ai/assistant/notes/{note_id}/postpone")
async def postpone_ai_assistant_note(request: Request, note_id: int):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role not in ("boss", "manager"):
        return RedirectResponse("/", status_code=302)

    company_id = get_user_company_id(username)
    disabled_response = require_feature(company_id, "ai_insights")

    if disabled_response:
        return disabled_response

    form = await request.form()
    days = str(form.get("days") or "1").strip()

    if days not in ("1", "7"):
        days = "1"

    next_date = (datetime.now() + timedelta(days=int(days))).strftime("%Y-%m-%d")

    conn = connect()
    c = conn.cursor()

    c.execute("""
    UPDATE ai_assistant_notes
    SET follow_up_date=?
    WHERE id=?
      AND company_id=?
      AND COALESCE(is_done, 0)=0
    """, (
        next_date,
        note_id,
        company_id
    ))

    conn.commit()
    conn.close()

    log_ai_assistant_event(
        company_id,
        note_id,
        username,
        "postponed",
        f"Контроль перенесён на {next_date}"
    )

    return RedirectResponse("/ai/assistant?note_postponed=1", status_code=302)


@app.post("/ai/assistant/follow-ups/notify")
async def notify_ai_assistant_follow_ups(request: Request):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role not in ("boss", "manager"):
        return RedirectResponse("/", status_code=302)

    company_id = get_user_company_id(username)
    disabled_response = require_feature(company_id, "ai_insights")

    if disabled_response:
        return disabled_response

    disabled_response = require_feature(company_id, "notifications")

    if disabled_response:
        return disabled_response

    created_count = create_ai_follow_up_notifications(company_id, username)

    return RedirectResponse(
        f"/ai/assistant?follow_up_notifications={created_count}",
        status_code=302
    )


@app.post("/ai/assistant/setup-digests")
async def setup_ai_assistant_digest_rules(request: Request):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role not in ("boss", "manager"):
        return RedirectResponse("/", status_code=302)

    company_id = get_user_company_id(username)
    disabled_response = require_feature(company_id, "ai_insights")

    if disabled_response:
        return disabled_response

    disabled_response = require_feature(company_id, "automation")

    if disabled_response:
        return disabled_response

    created_count = ensure_ai_digest_automation_rules(company_id, username)

    return RedirectResponse(f"/ai/assistant?digest_rules={created_count}", status_code=302)


@app.post("/ai/insights/digest")
async def create_ai_insights_digest(request: Request):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role not in ("boss", "manager"):
        return RedirectResponse("/", status_code=302)

    company_id = get_user_company_id(username)
    disabled_response = require_feature(company_id, "ai_insights")

    if disabled_response:
        return disabled_response

    settings = get_company_settings(company_id)

    conn = connect()
    c = conn.cursor()

    overdue_tasks = c.execute("""
    SELECT COUNT(*)
    FROM tasks
    WHERE company_id=?
      AND archived=0
      AND status!='Завершено'
      AND task_date < date('now')
    """, (company_id,)).fetchone()[0]

    unpaid_total = c.execute("""
    SELECT COALESCE(SUM(price), 0)
    FROM tasks
    WHERE company_id=?
      AND archived=0
      AND payment_status!='Оплачено'
    """, (company_id,)).fetchone()[0]

    message_lines = [
        "AI-сводка по бизнесу",
        f"Просроченные {settings['task_label'] or 'задачи'}: {overdue_tasks}",
        f"Неоплаченная сумма: ₽{round(float(unpaid_total or 0), 1)}"
    ]

    if overdue_tasks:
        message_lines.append("Рекомендация: проверьте ответственных и сроки.")

    if unpaid_total:
        message_lines.append("Рекомендация: запустите напоминания по оплатам.")

    digest_message = "\\n".join(message_lines)

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
        "🤖 AI-сводка",
        digest_message,
        "/ai/insights",
        datetime.now().strftime("%Y-%m-%d %H:%M")
    ))

    conn.commit()
    conn.close()

    return RedirectResponse("/ai/insights?digest=1", status_code=302)

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
    features = get_company_features(company_id)

    return templates.TemplateResponse(
        request,
        "settings.html",
        {
            "request": request,
            "username": username,
            "role": role,
            "settings": settings,
            "features": features,
            "feature_definitions": FEATURE_DEFINITIONS,
            "core_features": CORE_FEATURES,
            "industry_options": INDUSTRY_OPTIONS,
            "business_presets": BUSINESS_PRESETS
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
    allowed_industries = [industry_key for industry_key, _ in INDUSTRY_OPTIONS]

    if plan not in allowed_plans:
        plan = "basic"

    if industry not in allowed_industries:
        industry = "field_service"

    one_c_enabled = 1 if plan in ("business_1c", "enterprise_1c") else 0
    calls_enabled = 1 if plan in ("business", "business_1c", "enterprise_1c") else 0
    ai_calls_enabled = 1 if plan == "enterprise_1c" else 0
    company_id = get_user_company_id(username)

    if form.get("apply_business_preset") == "1":
        apply_business_preset(company_id, industry)
    else:
        update_company_features(company_id, form)

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

    disabled_response = require_feature(company_id, "custom_fields")

    if disabled_response:
        return disabled_response



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

    return RedirectResponse("/catalog", status_code=302)


@app.get("/clients", response_class=HTMLResponse)
async def clients_page(
    request: Request,
    search: str = "",
    client_filter: str = "",
    client_sort: str = ""
):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role == "superadmin":
        return RedirectResponse("/platform", status_code=302)

    if role not in ("boss", "manager"):
        return RedirectResponse("/", status_code=302)

    company_id = get_user_company_id(username)
    disabled_response = require_feature(company_id, "clients")

    if disabled_response:
        return disabled_response

    conn = connect()
    c = conn.cursor()

    today = datetime.now().strftime("%Y-%m-%d")
    selected_search = str(search or "").strip()
    selected_client_filter = client_filter if client_filter in ("active", "overdue", "empty") else ""
    selected_client_sort = client_sort if client_sort in ("name", "tasks", "active", "overdue") else "newest"
    search_value = f"%{selected_search.lower()}%"

    search_condition = ""
    params = [today, company_id]

    if selected_search:
        search_condition = """
          AND (
            lower(clients.name) LIKE ?
            OR lower(clients.phone) LIKE ?
            OR lower(clients.email) LIKE ?
            OR lower(clients.address) LIKE ?
            OR lower(clients.notes) LIKE ?
          )
        """
        params.extend([search_value, search_value, search_value, search_value, search_value])

    clients = c.execute(f"""
    SELECT
        clients.*,
        COUNT(tasks.id) AS task_count,
        MAX(tasks.task_date) AS last_task_date,
        SUM(CASE
            WHEN tasks.status='Завершено'
            THEN CAST(REPLACE(COALESCE(tasks.price, '0'), ',', '.') AS REAL)
            ELSE 0
        END) AS completed_revenue,
        SUM(CASE
            WHEN tasks.archived=0
             AND tasks.status IN ('Новая', 'В работе')
            THEN 1 ELSE 0
        END) AS active_task_count,
        SUM(CASE
            WHEN tasks.archived=0
             AND tasks.task_date IS NOT NULL
             AND substr(tasks.task_date, 1, 10) < ?
             AND tasks.status NOT IN ('Завершено', 'Отменено')
            THEN 1 ELSE 0
        END) AS overdue_task_count
    FROM clients
    LEFT JOIN tasks
      ON tasks.client_id=clients.id
      AND tasks.company_id=clients.company_id
    WHERE clients.company_id=?
    {search_condition}
    GROUP BY clients.id
    ORDER BY clients.id DESC
    """, params).fetchall()

    if selected_client_filter == "active":
        clients = [client for client in clients if client["active_task_count"]]
    elif selected_client_filter == "overdue":
        clients = [client for client in clients if client["overdue_task_count"]]
    elif selected_client_filter == "empty":
        clients = [client for client in clients if not client["task_count"]]

    if selected_client_sort == "name":
        clients = sorted(clients, key=lambda client: str(client["name"] or "").lower())
    elif selected_client_sort == "tasks":
        clients = sorted(clients, key=lambda client: client["task_count"] or 0, reverse=True)
    elif selected_client_sort == "active":
        clients = sorted(clients, key=lambda client: client["active_task_count"] or 0, reverse=True)
    elif selected_client_sort == "overdue":
        clients = sorted(clients, key=lambda client: client["overdue_task_count"] or 0, reverse=True)

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
            "selected_search": selected_search,
            "selected_client_filter": selected_client_filter,
            "selected_client_sort": selected_client_sort,
            "custom_fields": custom_fields
        }
    )


@app.get("/clients/{client_id}", response_class=HTMLResponse)
async def client_detail(
    request: Request,
    client_id: int,
    task_filter: str = "",
    task_search: str = "",
    task_sort: str = "",
    activity_filter: str = "",
    note_search: str = "",
    file_search: str = ""
):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role not in ("boss", "manager"):
        return RedirectResponse("/", status_code=302)

    company_id = get_user_company_id(username)
    settings = get_company_settings(company_id)
    task_label = settings["task_label"] or "Заявка"
    disabled_response = require_feature(company_id, "clients")

    if disabled_response:
        return disabled_response

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
    selected_task_filter = task_filter if task_filter in ("active", "completed", "overdue") else ""
    selected_task_search = str(task_search or "").strip()
    selected_task_sort = task_sort if task_sort in ("oldest", "date_asc", "date_desc") else "newest"
    selected_activity_filter = activity_filter if activity_filter in ("status", "date", "comment") else ""
    selected_note_search = str(note_search or "").strip()
    selected_file_search = str(file_search or "").strip()
    search_value = selected_task_search.lower()
    note_search_value = selected_note_search.lower()
    file_search_value = selected_file_search.lower()
    latest_task = tasks[0] if tasks else None
    client_task_workers = {task["id"]: format_task_workers(task) for task in tasks}

    today = datetime.now().strftime("%Y-%m-%d")
    client_now_value = datetime.now().strftime("%Y-%m-%dT%H:%M")
    client_total_tasks = len(tasks)
    client_active_tasks = 0
    client_completed_tasks = 0
    client_overdue_tasks = 0
    client_revenue = 0
    upcoming_tasks = []

    for task in tasks:
        task_status = task["status"] or ""
        is_archived = "archived" in task.keys() and task["archived"] == 1
        task_date = str(task["task_date"] or "")[:10]

        if not is_archived and task_status in ("Новая", "В работе"):
            client_active_tasks += 1

        if (
            not is_archived
            and task_date
            and task_date >= today
            and task_status not in ("Завершено", "Отменено")
        ):
            upcoming_tasks.append(task)

        if task_status == "Завершено":
            client_completed_tasks += 1

            try:
                client_revenue += float(str(task["price"] or 0).replace(",", "."))
            except Exception:
                pass

        if (
            not is_archived
            and task_date
            and task_date < today
            and task_status not in ("Завершено", "Отменено")
        ):
            client_overdue_tasks += 1

    upcoming_task = None

    if upcoming_tasks:
        upcoming_task = sorted(
            upcoming_tasks,
            key=lambda item: (str(item["task_date"] or ""), item["id"] or 0)
        )[0]

    client_next_action = {
        "title": "Активных работ нет",
        "text": f"Можно создать запись в разделе «{task_label}» или добавить заметку.",
        "link": f"/create-task?client_id={client_id}&return_to=client",
        "link_text": f"Создать: {task_label}"
    }

    if client_overdue_tasks:
        client_next_action = {
            "title": f"Просрочено: {task_label}",
            "text": "Проверьте просрочки, перенесите дату или закройте работу.",
            "link": f"/clients/{client_id}?task_filter=overdue",
            "link_text": "Открыть просрочки"
        }
    elif upcoming_task:
        client_next_action = {
            "title": f"{task_label} #{upcoming_task['id']}: ближайшее",
            "text": f"{upcoming_task['task_date'] or 'Без даты'} / {upcoming_task['status']}",
            "link": f"/task/{upcoming_task['id']}",
            "link_text": f"Открыть: {task_label}"
        }
    elif client_active_tasks:
        client_next_action = {
            "title": f"Активно: {task_label}",
            "text": "Есть работы без будущей даты. Проверьте активный список.",
            "link": f"/clients/{client_id}?task_filter=active",
            "link_text": "Показать активные"
        }

    filtered_tasks = []

    for task in tasks:
        task_status = task["status"] or ""
        is_archived = "archived" in task.keys() and task["archived"] == 1
        task_date = str(task["task_date"] or "")[:10]
        is_overdue = (
            not is_archived
            and task_date
            and task_date < today
            and task_status not in ("Завершено", "Отменено")
        )

        if selected_task_filter == "active" and (is_archived or task_status not in ("Новая", "В работе")):
            continue

        if selected_task_filter == "completed" and task_status != "Завершено":
            continue

        if selected_task_filter == "overdue" and not is_overdue:
            continue

        if search_value:
            search_text = " ".join([
                str(task["id"] or ""),
                str(task["description"] or ""),
                str(task["address"] or ""),
                str(task["worker"] or ""),
                str(task["workers"] or ""),
                str(task_status or "")
            ]).lower()

            if search_value not in search_text:
                continue

        filtered_tasks.append(task)

    if selected_task_sort == "oldest":
        filtered_tasks.sort(key=lambda item: item["id"] or 0)
    elif selected_task_sort == "date_asc":
        filtered_tasks.sort(key=lambda item: (str(item["task_date"] or ""), item["id"] or 0))
    elif selected_task_sort == "date_desc":
        filtered_tasks.sort(key=lambda item: (str(item["task_date"] or ""), item["id"] or 0), reverse=True)

    client_notes = c.execute("""
    SELECT *
    FROM client_notes
    WHERE client_id=? AND company_id=?
    ORDER BY id DESC
    """, (client_id, company_id)).fetchall()
    latest_client_note = client_notes[0] if client_notes else None
    client_note_count = len(client_notes)

    if note_search_value:
        client_notes = [
            note for note in client_notes
            if note_search_value in str(note["note"] or "").lower()
        ]

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
    latest_activity = client_timeline[0] if client_timeline else None
    last_contact = None

    if latest_client_note:
        last_contact = {
            "type": "Заметка",
            "date": latest_client_note["created_at"],
            "text": latest_client_note["note"]
        }

    if latest_activity and (
        not last_contact
        or str(latest_activity["created_at"] or "") > str(last_contact["date"] or "")
    ):
        last_contact = {
            "type": latest_activity["action"],
            "date": latest_activity["created_at"],
            "text": latest_activity["details"]
        }

    if selected_activity_filter:
        filtered_timeline = []

        for item in client_timeline:
            action = str(item["action"] or "").lower()

            if selected_activity_filter == "status" and "статус" not in action:
                continue

            if selected_activity_filter == "date" and "дат" not in action and "срок" not in action:
                continue

            if selected_activity_filter == "comment" and "коммент" not in action:
                continue

            filtered_timeline.append(item)

        client_timeline = filtered_timeline

    client_files = c.execute("""
    SELECT *
    FROM client_files
    WHERE client_id=? AND company_id=?
    ORDER BY id DESC
    """, (client_id, company_id)).fetchall()
    client_file_count = len(client_files)

    if file_search_value:
        client_files = [
            client_file for client_file in client_files
            if file_search_value in " ".join([
                str(client_file["original_filename"] or ""),
                str(client_file["username"] or ""),
                str(client_file["content_type"] or "")
            ]).lower()
        ]

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
            "tasks": filtered_tasks,
            "latest_task": latest_task,
            "upcoming_task": upcoming_task,
            "client_task_workers": client_task_workers,
            "shown_task_count": len(filtered_tasks),
            "selected_task_filter": selected_task_filter,
            "selected_task_search": selected_task_search,
            "selected_task_sort": selected_task_sort,
            "selected_activity_filter": selected_activity_filter,
            "selected_note_search": selected_note_search,
            "selected_file_search": selected_file_search,
            "client_notes": client_notes,
            "client_files": client_files,
            "latest_client_note": latest_client_note,
            "last_contact": last_contact,
            "client_next_action": client_next_action,
            "shown_note_count": len(client_notes),
            "client_note_count": client_note_count,
            "shown_file_count": len(client_files),
            "client_file_count": client_file_count,
            "shown_activity_count": len(client_timeline),
            "client_total_tasks": client_total_tasks,
            "client_now_value": client_now_value,
            "client_active_tasks": client_active_tasks,
            "client_completed_tasks": client_completed_tasks,
            "client_overdue_tasks": client_overdue_tasks,
            "client_revenue": client_revenue,
            "client_timeline": client_timeline,
            "client_custom_fields": client_custom_fields,
            "settings": settings
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


@app.post("/clients/{client_id}/files")
async def upload_client_file(
    request: Request,
    client_id: int,
    upload: UploadFile = File(None)
):

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
    SELECT id
    FROM clients
    WHERE id=? AND company_id=?
    """, (client_id, company_id)).fetchone()

    if not client:
        conn.close()
        return RedirectResponse("/clients", status_code=302)

    if not upload or not upload.filename:
        conn.close()
        return RedirectResponse(f"/clients/{client_id}?file_error=empty", status_code=302)

    original_filename = Path(upload.filename).name
    stored_filename = safe_client_file_filename(client_id, original_filename)
    file_path = CLIENT_FILES_DIR / stored_filename

    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(upload.file, buffer)

    c.execute("""
    INSERT INTO client_files (
        company_id,
        client_id,
        username,
        original_filename,
        stored_filename,
        content_type,
        created_at
    )
    VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        company_id,
        client_id,
        username,
        original_filename,
        stored_filename,
        upload.content_type or "",
        datetime.now().strftime("%Y-%m-%d %H:%M")
    ))

    conn.commit()
    conn.close()

    return RedirectResponse(f"/clients/{client_id}?file_uploaded=1", status_code=302)


@app.get("/clients/{client_id}/files/{file_id}")
async def download_client_file(request: Request, client_id: int, file_id: int):

    username = get_user(request)

    if not username:
        return Response(status_code=404)

    role = get_role(username)

    if role not in ("boss", "manager"):
        return Response(status_code=404)

    company_id = get_user_company_id(username)

    conn = connect()
    c = conn.cursor()

    client_file = c.execute("""
    SELECT *
    FROM client_files
    WHERE id=?
      AND client_id=?
      AND company_id=?
    """, (file_id, client_id, company_id)).fetchone()

    conn.close()

    if not client_file:
        return Response(status_code=404)

    stored_filename = Path(client_file["stored_filename"] or "").name
    file_path = CLIENT_FILES_DIR / stored_filename

    if not stored_filename or not file_path.is_file():
        return Response(status_code=404)

    return FileResponse(
        str(file_path),
        filename=client_file["original_filename"] or stored_filename
    )


@app.post("/clients/{client_id}/files/{file_id}/delete")
async def delete_client_file(request: Request, client_id: int, file_id: int):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role not in ("boss", "manager"):
        return RedirectResponse("/", status_code=302)

    company_id = get_user_company_id(username)

    conn = connect()
    c = conn.cursor()

    client_file = c.execute("""
    SELECT *
    FROM client_files
    WHERE id=?
      AND client_id=?
      AND company_id=?
    """, (file_id, client_id, company_id)).fetchone()

    if not client_file:
        conn.close()
        return RedirectResponse(f"/clients/{client_id}", status_code=302)

    stored_filename = Path(client_file["stored_filename"] or "").name
    file_path = CLIENT_FILES_DIR / stored_filename

    c.execute("""
    DELETE FROM client_files
    WHERE id=? AND client_id=? AND company_id=?
    """, (file_id, client_id, company_id))
    conn.commit()
    conn.close()

    if stored_filename and file_path.is_file():
        try:
            file_path.unlink()
        except Exception:
            pass

    return RedirectResponse(f"/clients/{client_id}?file_deleted=1", status_code=302)


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
Электронная почта: {email}
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

    run_automation_event(
        company_id,
        "new_client",
        "client",
        client_id,
        f"Создан новый клиент: {name}",
        f"/clients/{client_id}",
    )

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
    disabled_response = require_feature(company_id, "archive")

    if disabled_response:
        return disabled_response

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
    company_id = get_user_company_id(username)
    features = get_company_features(company_id)

    return templates.TemplateResponse(
        request,
        "more.html",
        {
            "request": request,
            "username": username,
            "role": role,
            "features": features
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
async def worker_detail(request: Request, worker_id: int, month: str = ""):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role not in ("boss", "manager"):
        return RedirectResponse("/", status_code=302)

    company_id = get_user_company_id(username)

    if not month:
        month = datetime.now().strftime("%Y-%m")

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

    month_tasks = c.execute(f"""
    SELECT *
    FROM tasks
    WHERE archived=0
      AND company_id=?
      AND {worker_condition}
      AND task_date LIKE ?
    """, [company_id] + worker_params + [f"{month}%"]).fetchall()

    finance_total = 0
    finance_profit = 0
    finance_expenses = 0

    for task in month_tasks:
        items = c.execute("""
        SELECT *
        FROM task_items
        WHERE task_id=?
        """, (task["id"],)).fetchall()
        expenses = c.execute("""
        SELECT *
        FROM task_expenses
        WHERE task_id=?
        """, (task["id"],)).fetchall()

        task_total = sum(item["total"] for item in items)
        task_profit = sum(item["profit"] for item in items)
        discount_amount = float(task["discount_amount"] or 0) if "discount_amount" in task.keys() else 0
        task_expenses_total = sum(expense["amount"] for expense in expenses)

        if not items:
            try:
                task_total = float(task["price"] or 0)
            except Exception:
                task_total = 0
            task_profit = 0

        if discount_amount < 0:
            discount_amount = 0

        task_total = max(task_total - discount_amount, 0)
        task_profit = task_profit - discount_amount - task_expenses_total

        task_worker_count = len(get_task_worker_names(task)) or 1
        finance_total += task_total / task_worker_count
        finance_profit += task_profit / task_worker_count
        finance_expenses += task_expenses_total / task_worker_count

    commission_percent = float(worker["commission_percent"] or 0) if "commission_percent" in worker.keys() else 0
    finance_total = round(finance_total, 1)
    finance_profit = round(finance_profit, 1)
    finance_expenses = round(finance_expenses, 1)
    finance_payout = round(finance_profit * commission_percent / 100, 1)
    finance_margin = round((finance_profit / finance_total) * 100, 1) if finance_total else 0

    payroll_payout = c.execute("""
    SELECT *
    FROM payroll_payouts
    WHERE company_id=? AND worker_id=? AND month=? AND status='paid'
    """, (company_id, worker_id, month)).fetchone()
    payroll_paid_amount = round(float(payroll_payout["amount"] or 0), 1) if payroll_payout else 0
    payroll_due_amount = round(max(finance_payout - payroll_paid_amount, 0), 1)
    payroll_status = "Не выплачено"

    if payroll_payout:
        payroll_status = "Выплачено" if payroll_paid_amount >= finance_payout else "Частично"

    conn.close()

    return templates.TemplateResponse(
        request=request,
        name="worker_detail.html",
        context={
            "request": request,
            "username": username,
            "role": role,
            "worker": worker,
            "month": month,
            "total_tasks": total_tasks,
            "done_tasks": done_tasks,
            "income": income,
            "finance_total": finance_total,
            "finance_profit": finance_profit,
            "finance_expenses": finance_expenses,
            "finance_payout": finance_payout,
            "finance_margin": finance_margin,
            "payroll_status": payroll_status,
            "payroll_paid_amount": payroll_paid_amount,
            "payroll_due_amount": payroll_due_amount,
            "payroll_note": payroll_payout["note"] if payroll_payout else ""
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
    commission_percent = form.get("commission_percent") or "0"

    try:
        commission_percent = float(str(commission_percent).replace(",", "."))
    except Exception:
        commission_percent = 0

    if commission_percent < 0:
        commission_percent = 0

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
        commission_percent,
        last_seen
    )
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
        commission_percent,
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


@app.post("/workers/{user_id}/commission")
async def update_worker_commission(request: Request, user_id: int):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role != "boss":
        return RedirectResponse("/workers?error=only_boss", status_code=302)

    company_id = get_user_company_id(username)
    form = await request.form()
    commission_percent = form.get("commission_percent") or "0"

    try:
        commission_percent = float(str(commission_percent).replace(",", "."))
    except Exception:
        commission_percent = 0

    if commission_percent < 0:
        commission_percent = 0

    conn = connect()
    c = conn.cursor()

    user = c.execute("""
    SELECT *
    FROM users
    WHERE id=? AND company_id=?
    """, (user_id, company_id)).fetchone()

    if not user:
        conn.close()
        return RedirectResponse("/workers", status_code=302)

    if user["role"] == "boss":
        conn.close()
        return RedirectResponse("/workers?error=cannot_change_boss", status_code=302)

    c.execute("""
    UPDATE users
    SET commission_percent=?
    WHERE id=? AND company_id=?
    """, (commission_percent, user_id, company_id))

    conn.commit()
    conn.close()

    return RedirectResponse("/workers?commission_updated=1", status_code=302)


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
        "app": "Бизнес CRM"
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
async def create_task_page(
    request: Request,
    task_date: str = "",
    worker: str = "",
    return_to: str = "",
    client_id: int = 0,
    note_id: int = 0,
    source_task_id: int = 0,
    ai_note_id: int = 0
):

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
    selected_return_to = return_to if return_to in ("calendar", "client") else ""
    selected_worker_active_count = 0
    selected_worker_active_tasks = []
    recommended_worker = None
    selected_client = None
    selected_address = ""
    selected_description = ""
    selected_note_id = 0
    selected_source_task_id = 0
    selected_ai_note_id = 0

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

                    if client_id:
                        switch_params["client_id"] = client_id

                    if source_task_id:
                        switch_params["source_task_id"] = source_task_id

                    if ai_note_id:
                        switch_params["ai_note_id"] = ai_note_id

                    recommended_worker["switch_url"] = f"/create-task?{urlencode(switch_params)}"

    clients = c.execute("""
    SELECT *
    FROM clients
    WHERE company_id=?
    ORDER BY name
    """, (company_id,)).fetchall()

    if client_id:
        selected_client = c.execute("""
        SELECT *
        FROM clients
        WHERE id=? AND company_id=?
        """, (client_id, company_id)).fetchone()

        if selected_client:
            selected_address = selected_client["address"] or ""

        if selected_client and source_task_id:
            source_task = c.execute("""
            SELECT *
            FROM tasks
            WHERE id=?
              AND client_id=?
              AND company_id=?
            """, (source_task_id, client_id, company_id)).fetchone()

            if source_task:
                selected_address = source_task["address"] or selected_address
                selected_description = source_task["description"] or ""
                selected_source_task_id = source_task_id

                if not selected_workers:
                    selected_workers = [
                        worker_name for worker_name in get_task_worker_names(source_task)
                        if worker_name in worker_names
                    ]

        if selected_client and note_id:
            selected_note = c.execute("""
            SELECT note
            FROM client_notes
            WHERE id=?
              AND client_id=?
              AND company_id=?
            """, (note_id, client_id, company_id)).fetchone()

            if selected_note:
                selected_description = selected_note["note"] or ""
                selected_note_id = note_id

    if ai_note_id:
        selected_ai_note = c.execute("""
        SELECT *
        FROM ai_assistant_notes
        WHERE id=?
          AND company_id=?
          AND COALESCE(is_done, 0)=0
        """, (ai_note_id, company_id)).fetchone()

        if selected_ai_note:
            selected_description = selected_ai_note["note"] or selected_description
            selected_ai_note_id = ai_note_id

    settings = get_company_settings(company_id)

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
            "selected_client": selected_client,
            "selected_address": selected_address,
            "selected_description": selected_description,
            "selected_note_id": selected_note_id,
            "selected_source_task_id": selected_source_task_id,
            "selected_ai_note_id": selected_ai_note_id,
            "selected_task_date": selected_task_date,
            "selected_workers": selected_workers,
            "selected_return_to": selected_return_to,
            "selected_worker_active_count": selected_worker_active_count,
            "selected_worker_active_tasks": selected_worker_active_tasks,
            "recommended_worker": recommended_worker,
            "settings": settings
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
    note_id = (form.get("note_id") or "").strip()
    source_task_id = (form.get("source_task_id") or "").strip()
    ai_note_id = (form.get("ai_note_id") or "").strip()
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
            elif return_to == "client" and client_id:
                error_params["return_to"] = "client"
                error_params["client_id"] = client_id

                if note_id.isdigit():
                    note = c.execute("""
                    SELECT id
                    FROM client_notes
                    WHERE id=?
                      AND client_id=?
                      AND company_id=?
                    """, (int(note_id), client_id, company_id)).fetchone()

                    if note:
                        error_params["note_id"] = note_id

                if source_task_id.isdigit():
                    source_task = c.execute("""
                    SELECT id
                    FROM tasks
                    WHERE id=?
                      AND client_id=?
                      AND company_id=?
                    """, (int(source_task_id), client_id, company_id)).fetchone()

                    if source_task:
                        error_params["source_task_id"] = source_task_id

            if ai_note_id.isdigit():
                ai_note = c.execute("""
                SELECT id
                FROM ai_assistant_notes
                WHERE id=?
                  AND company_id=?
                  AND COALESCE(is_done, 0)=0
                """, (int(ai_note_id), company_id)).fetchone()

                if ai_note:
                    error_params["ai_note_id"] = ai_note_id

            conn.close()
            return RedirectResponse(f"/create-task?{urlencode(error_params)}", status_code=302)

    if client_id:
        submitted_address = (address or "").strip()
        existing_client = c.execute("""
        SELECT *
        FROM clients
        WHERE id=? AND company_id=?
        """, (client_id, company_id)).fetchone()

        if existing_client:
            client = existing_client["name"]
            phone = existing_client["phone"]
            address = submitted_address or existing_client["address"]

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

    if ai_note_id.isdigit():
        c.execute("""
        UPDATE ai_assistant_notes
        SET is_done=1,
            done_by=?,
            done_at=?,
            created_task_id=?
        WHERE id=?
          AND company_id=?
          AND COALESCE(is_done, 0)=0
        """, (
            username,
            datetime.now().strftime("%Y-%m-%d %H:%M"),
            task_id,
            int(ai_note_id),
            company_id
        ))
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

    if return_to == "client" and client_id:
        return RedirectResponse(f"/clients/{client_id}", status_code=302)

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

    task_expenses = c.execute("""
    SELECT *
    FROM task_expenses
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
    expenses_total = sum(expense["amount"] for expense in task_expenses)
    discount_amount = float(task["discount_amount"] or 0) if "discount_amount" in task.keys() else 0

    if discount_amount < 0:
        discount_amount = 0

    estimate_final_total = max(estimate_total - discount_amount, 0)
    estimate_final_profit = estimate_profit - discount_amount - expenses_total
    estimate_margin = round((estimate_final_profit / estimate_final_total) * 100, 1) if estimate_final_total else 0

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

    settings = get_company_settings(company_id)

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
            "task_expenses": task_expenses,
            "catalog_items": catalog_items,
            "estimate_total": estimate_total,
            "estimate_profit": estimate_profit,
            "expenses_total": expenses_total,
            "discount_amount": discount_amount,
            "estimate_final_total": estimate_final_total,
            "estimate_final_profit": estimate_final_profit,
            "estimate_margin": estimate_margin,
            "task_workers": task_workers,
            "task_custom_fields": task_custom_fields,
            "sla_status": sla_status,
            "settings": settings
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


@app.post("/task/{task_id}/items/manual")
async def add_manual_task_item(request: Request, task_id: int):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role not in ("boss", "manager"):
        return RedirectResponse("/", status_code=302)

    form = await request.form()
    item_name = (form.get("item_name") or "").strip()
    item_type = form.get("item_type") if form.get("item_type") in ("service", "material") else "service"
    unit = (form.get("unit") or "шт").strip()
    qty = form.get("qty") or "1"
    price = form.get("price") or "0"
    cost = form.get("cost") or "0"

    try:
        qty = float(str(qty).replace(",", "."))
    except Exception:
        qty = 1

    try:
        price = float(str(price).replace(",", "."))
    except Exception:
        price = 0

    try:
        cost = float(str(cost).replace(",", "."))
    except Exception:
        cost = 0

    if not item_name:
        return RedirectResponse(f"/task/{task_id}?error=manual_item_empty", status_code=302)

    if qty <= 0:
        qty = 1

    if price < 0:
        price = 0

    if cost < 0:
        cost = 0

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
    total = price * qty
    profit = (price - cost) * qty

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
        None,
        item_name,
        item_type,
        unit,
        qty,
        price,
        cost,
        total,
        profit,
        datetime.now().strftime("%Y-%m-%d %H:%M")
    ))

    conn.commit()
    conn.close()

    log_task_activity(
        task_id,
        username,
        role,
        "Добавлена ручная позиция в смету",
        f"{item_name} × {qty}"
    )

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


@app.post("/task/{task_id}/estimate/apply")
async def apply_task_estimate_total(request: Request, task_id: int):

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
    estimate_total = c.execute("""
    SELECT SUM(total)
    FROM task_items
    WHERE task_id=? AND company_id=?
    """, (task_id, company_id)).fetchone()[0] or 0
    discount_amount = float(task["discount_amount"] or 0) if "discount_amount" in task.keys() else 0

    if discount_amount < 0:
        discount_amount = 0

    final_total = max(estimate_total - discount_amount, 0)

    c.execute("""
    UPDATE tasks
    SET price=?
    WHERE id=? AND company_id=?
    """, (str(final_total), task_id, company_id))

    conn.commit()
    conn.close()

    log_task_activity(
        task_id,
        username,
        role,
        "Цена обновлена по смете",
        f"Новая цена: {final_total}"
    )

    return RedirectResponse(f"/task/{task_id}", status_code=302)


@app.post("/task/{task_id}/expenses")
async def add_task_expense(request: Request, task_id: int):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role not in ("boss", "manager"):
        return RedirectResponse("/", status_code=302)

    form = await request.form()
    title = (form.get("title") or "").strip()
    amount = form.get("amount") or "0"

    try:
        amount = float(str(amount).replace(",", "."))
    except Exception:
        amount = 0

    if not title:
        return RedirectResponse(f"/task/{task_id}?error=expense_empty", status_code=302)

    if amount < 0:
        amount = 0

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

    c.execute("""
    INSERT INTO task_expenses (
        company_id,
        task_id,
        title,
        amount,
        created_at
    )
    VALUES (?, ?, ?, ?, ?)
    """, (
        company_id,
        task_id,
        title,
        amount,
        datetime.now().strftime("%Y-%m-%d %H:%M")
    ))

    conn.commit()
    conn.close()

    log_task_activity(
        task_id,
        username,
        role,
        "Добавлен расход",
        f"{title}: {amount}"
    )

    return RedirectResponse(f"/task/{task_id}", status_code=302)


@app.post("/task/{task_id}/expenses/{expense_id}/delete")
async def delete_task_expense(request: Request, task_id: int, expense_id: int):

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
    expense = c.execute("""
    SELECT *
    FROM task_expenses
    WHERE id=? AND task_id=? AND company_id=?
    """, (expense_id, task_id, company_id)).fetchone()

    if not expense:
        conn.close()
        return RedirectResponse(f"/task/{task_id}", status_code=302)

    c.execute("""
    DELETE FROM task_expenses
    WHERE id=? AND task_id=? AND company_id=?
    """, (expense_id, task_id, company_id))

    conn.commit()
    conn.close()

    log_task_activity(
        task_id,
        username,
        role,
        "Удалён расход",
        f"{expense['title']}: {expense['amount']}"
    )

    return RedirectResponse(f"/task/{task_id}", status_code=302)


@app.post("/task/{task_id}/discount")
async def update_task_discount(request: Request, task_id: int):

    username = get_user(request)

    if not username:
        return RedirectResponse("/login", status_code=302)

    role = get_role(username)

    if role not in ("boss", "manager"):
        return RedirectResponse("/", status_code=302)

    form = await request.form()
    discount_amount = form.get("discount_amount") or "0"

    try:
        discount_amount = float(str(discount_amount).replace(",", "."))
    except Exception:
        discount_amount = 0

    if discount_amount < 0:
        discount_amount = 0

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
    old_discount = task["discount_amount"] if "discount_amount" in task.keys() else 0

    c.execute("""
    UPDATE tasks
    SET discount_amount=?
    WHERE id=? AND company_id=?
    """, (discount_amount, task_id, company_id))

    conn.commit()
    conn.close()

    log_task_activity(
        task_id,
        username,
        role,
        "Изменена скидка",
        f"{old_discount} → {discount_amount}"
    )

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

    disabled_response = require_feature(company_id, "custom_fields")

    if disabled_response:
        conn.close()
        return disabled_response

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
        "Изменён срок",
        deadline_at or "Срок очищен",
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
                "⏰ Изменён срок",
                f"{username} изменил срок заявки #{task_id}",
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
            y = draw_text(pdf, f"Электронная почта: {settings['email']}", 40, y, font_name, size=10)
        if settings["address"]:
            y = draw_text(pdf, f"Адрес: {settings['address']}", 40, y, font_name, size=10)
        if settings["tax_number"]:
            y = draw_text(pdf, f"Налоговый номер: {settings['tax_number']}", 40, y, font_name, size=10)
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
            y = draw_text(pdf, f"Электронная почта: {settings['email']}", 40, y, font_name, size=10)
        if settings["address"]:
            y = draw_text(pdf, f"Адрес: {settings['address']}", 40, y, font_name, size=10)
        if settings["tax_number"]:
            y = draw_text(pdf, f"Налоговый номер: {settings['tax_number']}", 40, y, font_name, size=10)
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


def get_a3_company_id(request: Request):
    username = get_user(request)

    if not username:
        return None

    role = get_role(username)

    if role not in ("boss", "manager"):
        return None

    return get_user_company_id(username)


@app.get("/api/a3/system-health")
def api_a3_system_health(request: Request):
    company_id = get_a3_company_id(request)

    if not company_id:
        return JSONResponse({"ok": False, "error": "forbidden"}, status_code=403)

    return calculate_system_health(company_id)


@app.get("/api/a3/system-health/history")
def api_a3_system_health_history(request: Request):
    company_id = get_a3_company_id(request)

    if not company_id:
        return JSONResponse({"ok": False, "error": "forbidden"}, status_code=403)

    return {
        "items": get_system_health_history(company_id, limit=30)
    }


@app.get("/api/a3/automation-analytics")
def api_a3_automation_analytics(request: Request):
    company_id = get_a3_company_id(request)

    if not company_id:
        return JSONResponse({"ok": False, "error": "forbidden"}, status_code=403)

    return get_automation_analytics(company_id)


@app.get("/api/a3/unhealthy-rules")
def api_a3_unhealthy_rules(request: Request):
    company_id = get_a3_company_id(request)

    if not company_id:
        return JSONResponse({"ok": False, "error": "forbidden"}, status_code=403)

    items = get_unhealthy_rules(company_id)

    return {
        "count": len(items),
        "items": items,
    }



@app.get("/api/a3/operations-insights")
def api_a3_operations_insights(request: Request):
    company_id = get_a3_company_id(request)

    if not company_id:
        return JSONResponse({"ok": False, "error": "forbidden"}, status_code=403)

    return get_operations_insights(company_id)


@app.post("/api/a3/self-healing/run")
def api_a3_self_healing_run(request: Request):
    company_id = get_a3_company_id(request)

    if not company_id:
        return JSONResponse({"ok": False, "error": "forbidden"}, status_code=403)

    result = run_self_healing_cycle(company_id=company_id)

    return {
        "ok": True,
        "result": result,
    }


@app.get("/api/a3/recovery-history")
def api_a3_recovery_history(request: Request):
    company_id = get_a3_company_id(request)

    if not company_id:
        return JSONResponse({"ok": False, "error": "forbidden"}, status_code=403)

    return {
        "items": get_recovery_history(company_id, limit=20)
    }


@app.get("/api/a3/ops-timeline")
def api_a3_ops_timeline(request: Request):
    company_id = get_a3_company_id(request)

    if not company_id:
        return JSONResponse({"ok": False, "error": "forbidden"}, status_code=403)

    return {
        "items": get_ops_timeline(company_id, limit=50)
    }


@app.get("/api/a3/predictive-signals")
def api_a3_predictive_signals(request: Request):
    company_id = get_a3_company_id(request)

    if not company_id:
        return JSONResponse({"ok": False, "error": "forbidden"}, status_code=403)

    return get_predictive_signals(company_id)


@app.get("/api/a3/decision-engine")
def api_a3_decision_engine(request: Request):
    company_id = get_a3_company_id(request)

    if not company_id:
        return JSONResponse({"ok": False, "error": "forbidden"}, status_code=403)

    return get_decision_engine(company_id)


@app.get("/api/a3/workflow/rules/{rule_id}/graph")
def api_a3_workflow_rule_graph(request: Request, rule_id: int):
    company_id = get_a3_company_id(request)

    if not company_id:
        return JSONResponse({"ok": False, "error": "forbidden"}, status_code=403)

    graph = get_rule_workflow_graph(company_id, rule_id)

    if not graph:
        return JSONResponse({"ok": False, "error": "not_found"}, status_code=404)

    return graph


@app.get("/api/a3/workflow/rules/{rule_id}/debug")
def api_a3_workflow_rule_debug(request: Request, rule_id: int):
    company_id = get_a3_company_id(request)

    if not company_id:
        return JSONResponse({"ok": False, "error": "forbidden"}, status_code=403)

    debug = get_rule_workflow_debug(company_id, rule_id)

    if not debug:
        return JSONResponse({"ok": False, "error": "not_found"}, status_code=404)

    return debug


@app.get("/api/a3/workflows/graph")
def api_a3_workflows_graph(request: Request):
    company_id = get_a3_company_id(request)

    if not company_id:
        return JSONResponse({"ok": False, "error": "forbidden"}, status_code=403)

    return get_company_workflow_graphs(company_id, limit=50)


@app.get("/api/a3/autonomous-actions")
def api_a3_autonomous_actions(request: Request):
    company_id = get_a3_company_id(request)

    if not company_id:
        return JSONResponse({"ok": False, "error": "forbidden"}, status_code=403)

    return {
        "items": get_autonomous_actions(company_id, limit=50)
    }


@app.post("/api/a3/autonomous-actions/process")
def api_a3_process_autonomous_actions(request: Request):
    company_id = get_a3_company_id(request)

    if not company_id:
        return JSONResponse({"ok": False, "error": "forbidden"}, status_code=403)

    result = process_autonomous_actions(company_id=company_id)

    return {
        "ok": True,
        "result": result,
    }


@app.post("/api/a3/autonomous-actions/request-approval")
async def api_a3_request_autonomous_action_approval(request: Request):
    company_id = get_a3_company_id(request)

    if not company_id:
        return JSONResponse({"ok": False, "error": "forbidden"}, status_code=403)

    try:
        payload = await request.json()
    except Exception:
        payload = {}

    action_type = payload.get("action_type")
    target_type = payload.get("target_type")
    target_id = payload.get("target_id")

    if action_type != "disable_rule" or target_type != "automation_rule" or not target_id:
        return JSONResponse(
            {
                "ok": False,
                "error": "unsupported_action",
            },
            status_code=400,
        )

    conn = connect()
    c = conn.cursor()

    rule = c.execute("""
    SELECT id
    FROM automation_rules
    WHERE company_id=?
      AND id=?
    """, (
        company_id,
        target_id,
    )).fetchone()

    conn.close()

    if not rule:
        return JSONResponse(
            {
                "ok": False,
                "error": "rule_not_found",
            },
            status_code=404,
        )

    result = enqueue_autonomous_action(
        company_id=company_id,
        action_type=action_type,
        target_type=target_type,
        target_id=target_id,
        payload_json=json.dumps({
            "requested_by": get_user(request) or "system",
            "reason": payload.get("reason") or "Запрошено из A3 workflow debug",
        }, ensure_ascii=False),
    )

    if not result.get("queued"):
        return {
            "ok": False,
            "queued": False,
            "reason": result.get("reason"),
        }

    process_result = process_autonomous_actions(company_id=company_id)

    return {
        "ok": True,
        "queued": True,
        "process_result": process_result,
    }


@app.get("/api/a3/governance-settings")
def api_a3_governance_settings(request: Request):
    company_id = get_a3_company_id(request)

    if not company_id:
        return JSONResponse({"ok": False, "error": "forbidden"}, status_code=403)

    return ensure_governance_settings(company_id)


@app.post("/api/a3/governance-settings/update")
async def api_a3_governance_settings_update(request: Request):
    company_id = get_a3_company_id(request)

    if not company_id:
        return JSONResponse({"ok": False, "error": "forbidden"}, status_code=403)

    payload = {}

    try:
        payload = await request.json()
    except Exception:
        pass

    autonomous_enabled = 1 if payload.get("autonomous_enabled", True) else 0
    require_critical_approval = 1 if payload.get("require_critical_approval", True) else 0
    confidence_threshold = int(payload.get("confidence_threshold", 70))
    max_actions_per_cycle = int(payload.get("max_actions_per_cycle", 20))

    return save_governance_settings(
        company_id=company_id,
        autonomous_enabled=autonomous_enabled,
        max_actions_per_cycle=max_actions_per_cycle,
        require_critical_approval=require_critical_approval,
        confidence_threshold=confidence_threshold,
        protected_rules_json="[]",
    )


@app.post("/api/a3/autonomous-actions/{action_id}/approve")
def api_a3_approve_autonomous_action(request: Request, action_id: int):
    company_id = get_a3_company_id(request)

    if not company_id:
        return JSONResponse({"ok": False, "error": "forbidden"}, status_code=403)

    decided_by = get_user(request) or "system"
    result = approve_autonomous_action(
        company_id=company_id,
        action_id=action_id,
        decided_by=decided_by,
    )

    if not result.get("ok"):
        return JSONResponse(result, status_code=404)

    return result


@app.post("/api/a3/autonomous-actions/{action_id}/reject")
def api_a3_reject_autonomous_action(request: Request, action_id: int):
    company_id = get_a3_company_id(request)

    if not company_id:
        return JSONResponse({"ok": False, "error": "forbidden"}, status_code=403)

    decided_by = get_user(request) or "system"
    result = reject_autonomous_action(
        company_id=company_id,
        action_id=action_id,
        decided_by=decided_by,
    )

    if not result.get("ok"):
        return JSONResponse(result, status_code=404)

    return result


@app.get("/api/a3/approval-queue")
def api_a3_approval_queue(request: Request):
    company_id = get_a3_company_id(request)

    if not company_id:
        return JSONResponse({"ok": False, "error": "forbidden"}, status_code=403)

    items = get_approval_queue(company_id)

    return {
        "count": len(items),
        "items": items,
    }


@app.get("/api/a3/approval-history")
def api_a3_approval_history(request: Request):
    company_id = get_a3_company_id(request)

    if not company_id:
        return JSONResponse({"ok": False, "error": "forbidden"}, status_code=403)

    items = get_approval_history(company_id)

    return {
        "count": len(items),
        "items": items,
    }


@app.post("/api/a3/ops-timeline")
async def api_a3_create_ops_timeline_event(request: Request):
    company_id = get_a3_company_id(request)

    if not company_id:
        return JSONResponse({"ok": False, "error": "forbidden"}, status_code=403)

    payload = await request.json()

    result = create_ops_timeline_event(
        company_id=company_id,
        event_type=payload.get("event_type", "manual"),
        severity=payload.get("severity", "info"),
        title=payload.get("title", "Событие A3"),
        message=payload.get("message", ""),
        target_type=payload.get("target_type"),
        target_id=payload.get("target_id"),
    )

    return {
        "ok": True,
        "result": result,
    }


@app.get("/api/a3/workflow/rules/{rule_id}/timeline")
def api_a3_workflow_timeline(
    request: Request,
    rule_id: int,
):
    company_id = get_a3_company_id(request)

    if not company_id:
        return JSONResponse({"ok": False, "error": "forbidden"}, status_code=403)

    timeline = get_workflow_timeline(
        company_id=company_id,
        rule_id=rule_id,
    )

    if not timeline:
        return JSONResponse({"ok": False, "error": "not_found"}, status_code=404)

    return {
        "ok": True,
        "timeline": timeline,
    }
