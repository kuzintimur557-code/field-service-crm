import sqlite3

DB = "crm.db"


def connect():

    conn = sqlite3.connect(DB)

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
        role TEXT
    )
    """)

    c.execute("""
    CREATE TABLE IF NOT EXISTS tasks (

        id INTEGER PRIMARY KEY AUTOINCREMENT,
        client TEXT,
        phone TEXT,
        address TEXT,
        description TEXT,
        worker TEXT,
        status TEXT,
        priority TEXT,
        task_date TEXT,
        photo TEXT
    )
    """)

    c.execute("""
    CREATE TABLE IF NOT EXISTS comments (

        id INTEGER PRIMARY KEY AUTOINCREMENT,
        task_id INTEGER,
        username TEXT,
        text TEXT
    )
    """)

    conn.commit()

    boss = c.execute("""
    SELECT * FROM users
    WHERE username='boss'
    """).fetchone()

    if not boss:

        c.execute("""
        INSERT INTO users (
            username,
            password,
            role
        )
        VALUES (?, ?, ?)
        """, (
            "boss",
            "1234",
            "boss"
        ))

        conn.commit()

    conn.close()