import sqlite3


DB_NAME = "crm.db"


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
        username TEXT,
        password TEXT,
        role TEXT,
        last_seen TEXT
    )
    """)

    c.execute("""
    CREATE TABLE IF NOT EXISTS company_settings (
        id INTEGER PRIMARY KEY,
        company_name TEXT,
        phone TEXT,
        email TEXT,
        address TEXT,
        tax_number TEXT,
        bank_details TEXT,
        plan TEXT DEFAULT 'basic',
        one_c_enabled INTEGER DEFAULT 0,
        calls_enabled INTEGER DEFAULT 0,
        ai_calls_enabled INTEGER DEFAULT 0,
        updated_at TEXT
    )

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

    CREATE TABLE IF NOT EXISTS client_notes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        client_id INTEGER,
        username TEXT,
        role TEXT,
        note TEXT,
        created_at TEXT
    )

    CREATE TABLE IF NOT EXISTS clients (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT,
        phone TEXT,
        email TEXT,
        address TEXT,
        notes TEXT,
        created_at TEXT
    )

    CREATE TABLE IF NOT EXISTS task_activity (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        task_id INTEGER,
        username TEXT,
        role TEXT,
        action TEXT,
        details TEXT,
        created_at TEXT
    )

    CREATE TABLE IF NOT EXISTS task_comments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        task_id INTEGER,
        username TEXT,
        role TEXT,
        message TEXT,
        created_at TEXT
    )

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
        price REAL,
        photo TEXT,
        status TEXT
    )
    """)

    add_column_if_missing(c, "tasks", "report", "TEXT")
    add_column_if_missing(c, "tasks", "after_photo", "TEXT")

    boss = c.execute("""
    SELECT * FROM users WHERE username='boss'
    """).fetchone()

    if not boss:
        c.execute("""
        INSERT INTO users (username, password, role, last_seen)
        VALUES (?, ?, ?, ?)
        """, (
            "boss",
            "boss123",
            "boss",
            ""
        ))

    worker = c.execute("""
    SELECT * FROM users WHERE username='worker'
    """).fetchone()

    if not worker:
        c.execute("""
        INSERT INTO users (username, password, role, last_seen)
        VALUES (?, ?, ?, ?)
        """, (
            "worker",
            "worker123",
            "worker",
            ""
        ))

    conn.commit()
    conn.close()
