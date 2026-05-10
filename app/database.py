import sqlite3


DB_NAME = "crm.db"


def connect():

    conn = sqlite3.connect(DB_NAME)

    conn.row_factory = sqlite3.Row

    return conn


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
    CREATE TABLE IF NOT EXISTS tasks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        client TEXT,
        phone TEXT,
        address TEXT,
        description TEXT,
        task_date TEXT,
        worker TEXT,
        status TEXT,
        priority TEXT,
        photo TEXT,
        price REAL,
        report TEXT,
        after_photo TEXT
    )
    """)

    boss = c.execute("""
    SELECT * FROM users
    WHERE username='boss'
    """).fetchone()

    if not boss:

        c.execute("""
        INSERT INTO users (
            username,
            password,
            role,
            last_seen
        )
        VALUES (?, ?, ?, ?)
        """, (
            "boss",
            "boss123",
            "boss",
            ""
        ))

    worker = c.execute("""
    SELECT * FROM users
    WHERE username='worker'
    """).fetchone()

    if not worker:

        c.execute("""
        INSERT INTO users (
            username,
            password,
            role,
            last_seen
        )
        VALUES (?, ?, ?, ?)
        """, (
            "worker",
            "worker123",
            "worker",
            ""
        ))

    columns = [
        row["name"]
        for row in c.execute(
            "PRAGMA table_info(tasks)"
        ).fetchall()
    ]

    if "report" not in columns:

        c.execute("""
        ALTER TABLE tasks
        ADD COLUMN report TEXT
        """)

    if "after_photo" not in columns:

        c.execute("""
        ALTER TABLE tasks
        ADD COLUMN after_photo TEXT
        """)

    conn.commit()

    conn.close()
