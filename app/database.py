import sqlite3
import os
from pathlib import Path
from datetime import datetime


DATA_DIR = Path(os.getenv("DATA_DIR", "."))
DATA_DIR.mkdir(parents=True, exist_ok=True)

DB_NAME = str(DATA_DIR / "crm.db")


def connect():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn


def add_column_if_missing(cursor, table, column, column_type):
    columns = cursor.execute(f"PRAGMA table_info({table})").fetchall()
    column_names = [column_info["name"] for column_info in columns]

    if column not in column_names:
        cursor.execute(f"ALTER TABLE {table} ADD COLUMN {column} {column_type}")


def init_db():
    conn = connect()
    c = conn.cursor()

    c.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE,
        password TEXT,
        role TEXT,
        last_seen TEXT
    )
    """)

    c.execute("""
    CREATE TABLE IF NOT EXISTS companies (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT,
        owner_username TEXT,
        created_at TEXT
    )
    """)

    c.execute("""
    CREATE TABLE IF NOT EXISTS company_settings (
        id INTEGER PRIMARY KEY,
        company_id INTEGER DEFAULT 1,
        company_name TEXT,
        phone TEXT,
        email TEXT,
        address TEXT,
        tax_number TEXT,
        bank_details TEXT,
        plan TEXT DEFAULT 'basic',
        industry TEXT DEFAULT 'field_service',
        task_label TEXT DEFAULT 'Заявка',
        worker_label TEXT DEFAULT 'Исполнитель',
        client_label TEXT DEFAULT 'Клиент',
        service_label TEXT DEFAULT 'Услуга',
        one_c_enabled INTEGER DEFAULT 0,
        calls_enabled INTEGER DEFAULT 0,
        ai_calls_enabled INTEGER DEFAULT 0,
        updated_at TEXT
    )
    """)

    c.execute("""
    CREATE TABLE IF NOT EXISTS clients (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT,
        phone TEXT,
        email TEXT,
        address TEXT,
        notes TEXT,
        created_at TEXT
    )
    """)

    c.execute("""
    CREATE TABLE IF NOT EXISTS client_notes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        client_id INTEGER,
        username TEXT,
        role TEXT,
        note TEXT,
        created_at TEXT
    )
    """)

    c.execute("""
    CREATE TABLE IF NOT EXISTS catalog_items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        item_type TEXT,
        name TEXT,
        unit TEXT,
        price REAL DEFAULT 0,
        cost REAL DEFAULT 0,
        active INTEGER DEFAULT 1,
        created_at TEXT
    )
    """)

    c.execute("""
    CREATE TABLE IF NOT EXISTS tasks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        client_id INTEGER,
        client TEXT,
        phone TEXT,
        address TEXT,
        description TEXT,
        task_date TEXT,
        worker TEXT,
        priority TEXT,
        price TEXT,
        photo TEXT,
        status TEXT,
        report TEXT,
        after_photo TEXT,
        archived INTEGER DEFAULT 0,
        payment_status TEXT DEFAULT 'Не оплачено'
    )
    """)

    c.execute("""
    CREATE TABLE IF NOT EXISTS task_items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        task_id INTEGER,
        catalog_item_id INTEGER,
        item_name TEXT,
        item_type TEXT,
        unit TEXT,
        qty REAL DEFAULT 1,
        price REAL DEFAULT 0,
        cost REAL DEFAULT 0,
        total REAL DEFAULT 0,
        profit REAL DEFAULT 0,
        created_at TEXT
    )
    """)

    c.execute("""
    CREATE TABLE IF NOT EXISTS task_activity (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        task_id INTEGER,
        username TEXT,
        role TEXT,
        action TEXT,
        details TEXT,
        created_at TEXT
    )
    """)

    c.execute("""
    CREATE TABLE IF NOT EXISTS notifications (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        company_id INTEGER,
        username TEXT,
        title TEXT,
        message TEXT,
        link TEXT,
        is_read INTEGER DEFAULT 0,
        created_at TEXT
    )
    """)

    c.execute("""
    CREATE TABLE IF NOT EXISTS recurring_jobs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        company_id INTEGER,
        client_id INTEGER,
        title TEXT,
        description TEXT,
        interval_type TEXT,
        next_date TEXT,
        worker TEXT,
        workers TEXT,
        priority TEXT,
        price TEXT,
        active INTEGER DEFAULT 1,
        created_at TEXT
    )
    """)

    c.execute("""
    CREATE TABLE IF NOT EXISTS custom_fields (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        company_id INTEGER,
        entity_type TEXT,
        label TEXT,
        field_type TEXT,
        options TEXT,
        is_required INTEGER DEFAULT 0,
        active INTEGER DEFAULT 1,
        sort_order INTEGER DEFAULT 0,
        created_at TEXT
    )
    """)

    c.execute("""
    CREATE TABLE IF NOT EXISTS custom_field_values (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        company_id INTEGER,
        field_id INTEGER,
        entity_type TEXT,
        entity_id INTEGER,
        value TEXT,
        created_at TEXT
    )
    """)

    c.execute("""
    CREATE TABLE IF NOT EXISTS login_attempts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT,
        ip TEXT,
        attempts INTEGER DEFAULT 0,
        blocked_until TEXT,
        updated_at TEXT
    )
    """)

    c.execute("""
    CREATE TABLE IF NOT EXISTS login_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT,
        role TEXT,
        ip TEXT,
        user_agent TEXT,
        created_at TEXT
    )
    """)

    c.execute("""
    CREATE TABLE IF NOT EXISTS task_comments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        task_id INTEGER,
        username TEXT,
        role TEXT,
        message TEXT,
        created_at TEXT
    )
    """)

    add_column_if_missing(c, "users", "company_id", "INTEGER DEFAULT 1")
    add_column_if_missing(c, "users", "full_name", "TEXT")
    add_column_if_missing(c, "users", "position", "TEXT")
    add_column_if_missing(c, "users", "phone", "TEXT")
    add_column_if_missing(c, "users", "email", "TEXT")
    add_column_if_missing(c, "users", "telegram_chat_id", "TEXT")
    add_column_if_missing(c, "task_items", "company_id", "INTEGER DEFAULT 1")
    add_column_if_missing(c, "client_notes", "company_id", "INTEGER DEFAULT 1")
    add_column_if_missing(c, "catalog_items", "company_id", "INTEGER DEFAULT 1")
    add_column_if_missing(c, "clients", "company_id", "INTEGER DEFAULT 1")
    add_column_if_missing(c, "tasks", "company_id", "INTEGER DEFAULT 1")

    add_column_if_missing(c, "tasks", "workers", "TEXT")
    add_column_if_missing(c, "tasks", "created_at", "TEXT")
    add_column_if_missing(c, "tasks", "client_id", "INTEGER")
    add_column_if_missing(c, "tasks", "after_photo", "TEXT")
    add_column_if_missing(c, "tasks", "archived", "INTEGER DEFAULT 0")
    add_column_if_missing(c, "tasks", "payment_status", "TEXT DEFAULT 'Не оплачено'")

    add_column_if_missing(c, "recurring_jobs", "company_id", "INTEGER DEFAULT 1")
    add_column_if_missing(c, "recurring_jobs", "client_id", "INTEGER")
    add_column_if_missing(c, "recurring_jobs", "workers", "TEXT")
    add_column_if_missing(c, "recurring_jobs", "active", "INTEGER DEFAULT 1")

    add_column_if_missing(c, "custom_fields", "company_id", "INTEGER DEFAULT 1")
    add_column_if_missing(c, "custom_fields", "entity_type", "TEXT")
    add_column_if_missing(c, "custom_fields", "label", "TEXT")
    add_column_if_missing(c, "custom_fields", "field_type", "TEXT DEFAULT 'text'")
    add_column_if_missing(c, "custom_fields", "options", "TEXT")
    add_column_if_missing(c, "custom_fields", "is_required", "INTEGER DEFAULT 0")
    add_column_if_missing(c, "custom_fields", "active", "INTEGER DEFAULT 1")
    add_column_if_missing(c, "custom_fields", "sort_order", "INTEGER DEFAULT 0")
    add_column_if_missing(c, "custom_field_values", "company_id", "INTEGER DEFAULT 1")
    add_column_if_missing(c, "custom_field_values", "field_id", "INTEGER")
    add_column_if_missing(c, "custom_field_values", "entity_type", "TEXT")
    add_column_if_missing(c, "custom_field_values", "entity_id", "INTEGER")
    add_column_if_missing(c, "custom_field_values", "value", "TEXT")

    add_column_if_missing(c, "company_settings", "company_id", "INTEGER DEFAULT 1")
    add_column_if_missing(c, "company_settings", "plan", "TEXT DEFAULT 'basic'")
    add_column_if_missing(c, "company_settings", "industry", "TEXT DEFAULT 'field_service'")
    add_column_if_missing(c, "company_settings", "task_label", "TEXT DEFAULT 'Заявка'")
    add_column_if_missing(c, "company_settings", "worker_label", "TEXT DEFAULT 'Исполнитель'")
    add_column_if_missing(c, "company_settings", "client_label", "TEXT DEFAULT 'Клиент'")
    add_column_if_missing(c, "company_settings", "service_label", "TEXT DEFAULT 'Услуга'")
    add_column_if_missing(c, "company_settings", "one_c_enabled", "INTEGER DEFAULT 0")
    add_column_if_missing(c, "company_settings", "calls_enabled", "INTEGER DEFAULT 0")
    add_column_if_missing(c, "company_settings", "ai_calls_enabled", "INTEGER DEFAULT 0")

    c.execute("""
    UPDATE company_settings
    SET company_id=1
    WHERE company_id IS NULL
    """)

    c.execute("""
    DELETE FROM company_settings
    WHERE id NOT IN (
        SELECT MIN(id)
        FROM company_settings
        GROUP BY company_id
    )
    """)

    c.execute("""
    CREATE UNIQUE INDEX IF NOT EXISTS idx_company_settings_company_id
    ON company_settings(company_id)
    """)

    c.execute("""
    INSERT OR IGNORE INTO companies (
        id,
        name,
        owner_username,
        created_at
    )
    VALUES (?, ?, ?, ?)
    """, (
        1,
        "Default Company",
        "boss",
        datetime.now().strftime("%Y-%m-%d %H:%M")
    ))

    c.execute("""
    INSERT OR IGNORE INTO company_settings (
        id,
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
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        1,
        1,
        "",
        "",
        "",
        "",
        "",
        "",
        "basic",
        0,
        0,
        0,
        ""
    ))

    c.execute("""
    DELETE FROM users
    WHERE id NOT IN (
        SELECT MIN(id)
        FROM users
        GROUP BY username
    )
    """)

    c.execute("""
    CREATE UNIQUE INDEX IF NOT EXISTS idx_users_username
    ON users(username)
    """)

    if os.getenv("ENV") != "production":
        c.execute("""
        INSERT OR IGNORE INTO users (username, password, role, last_seen)
        VALUES (?, ?, ?, ?)
        """, (
            "boss",
            "boss123",
            "boss",
            datetime.now().strftime("%Y-%m-%d %H:%M")
        ))

        c.execute("""
        INSERT OR IGNORE INTO users (username, password, role, last_seen)
        VALUES (?, ?, ?, ?)
        """, (
            "manager",
            "manager123",
            "manager",
            datetime.now().strftime("%Y-%m-%d %H:%M")
        ))

        c.execute("""
        INSERT OR IGNORE INTO users (username, password, role, last_seen)
        VALUES (?, ?, ?, ?)
        """, (
            "worker",
            "worker123",
            "worker",
            datetime.now().strftime("%Y-%m-%d %H:%M")
        ))

    conn.commit()
    conn.close()
