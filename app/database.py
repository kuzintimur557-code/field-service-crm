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
        last_seen TEXT,
        is_active INTEGER DEFAULT 1
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
        calendar_auto_publish INTEGER DEFAULT 0,
        calendar_auto_remind INTEGER DEFAULT 0,
        calendar_auto_days_ahead INTEGER DEFAULT 7,
        calendar_auto_window_start TEXT DEFAULT '00:00',
        calendar_auto_window_end TEXT DEFAULT '23:59',
        updated_at TEXT
    )
    """)

    c.execute("""
    CREATE TABLE IF NOT EXISTS company_features (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        company_id INTEGER,
        feature_key TEXT,
        enabled INTEGER DEFAULT 1,
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
    CREATE TABLE IF NOT EXISTS client_files (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        company_id INTEGER,
        client_id INTEGER,
        username TEXT,
        original_filename TEXT,
        stored_filename TEXT,
        content_type TEXT,
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
        payment_status TEXT DEFAULT 'Не оплачено',
        deadline_at TEXT
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
    CREATE TABLE IF NOT EXISTS task_expenses (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        company_id INTEGER,
        task_id INTEGER,
        title TEXT,
        amount REAL DEFAULT 0,
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
    CREATE TABLE IF NOT EXISTS team_activity (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        company_id INTEGER,
        user_id INTEGER,
        target_username TEXT,
        actor_username TEXT,
        action TEXT,
        details TEXT,
        created_at TEXT
    )
    """)

    c.execute("""
    CREATE TABLE IF NOT EXISTS worker_unavailability (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        company_id INTEGER NOT NULL,
        worker_id INTEGER NOT NULL,
        date_from TEXT NOT NULL,
        date_to TEXT NOT NULL,
        reason TEXT,
        created_by TEXT,
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
    CREATE TABLE IF NOT EXISTS calendar_day_publications (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        company_id INTEGER NOT NULL,
        plan_date TEXT NOT NULL,
        plan_hash TEXT NOT NULL,
        task_count INTEGER DEFAULT 0,
        worker_count INTEGER DEFAULT 0,
        published_by TEXT,
        published_at TEXT,
        revision INTEGER DEFAULT 1
    )
    """)

    c.execute("""
    CREATE TABLE IF NOT EXISTS calendar_day_acknowledgements (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        company_id INTEGER NOT NULL,
        plan_date TEXT NOT NULL,
        revision INTEGER NOT NULL,
        username TEXT NOT NULL,
        acknowledged_at TEXT
    )
    """)

    c.execute("""
    CREATE TABLE IF NOT EXISTS calendar_day_ack_reminders (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        company_id INTEGER NOT NULL,
        plan_date TEXT NOT NULL,
        revision INTEGER NOT NULL,
        username TEXT NOT NULL,
        reminded_by TEXT,
        reminded_at TEXT,
        source TEXT DEFAULT 'manual'
    )
    """)

    c.execute("""
    CREATE TABLE IF NOT EXISTS calendar_plan_operation_runs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        company_id INTEGER NOT NULL,
        week_start TEXT NOT NULL,
        week_end TEXT NOT NULL,
        action TEXT NOT NULL,
        source TEXT NOT NULL DEFAULT 'manual',
        actor_username TEXT,
        changed_days INTEGER DEFAULT 0,
        notifications_sent INTEGER DEFAULT 0,
        skipped_days INTEGER DEFAULT 0,
        result_json TEXT,
        created_at TEXT NOT NULL
    )
    """)

    c.execute("""
    CREATE TABLE IF NOT EXISTS calendar_plan_scheduler_status (
        company_id INTEGER PRIMARY KEY,
        last_started_at TEXT,
        last_completed_at TEXT,
        last_status TEXT DEFAULT 'waiting',
        last_error TEXT,
        last_changed_days INTEGER DEFAULT 0,
        last_notifications_sent INTEGER DEFAULT 0,
        last_source TEXT DEFAULT 'scheduler',
        last_triggered_by TEXT,
        last_result_json TEXT,
        active_incident TEXT DEFAULT '',
        incident_started_at TEXT,
        incident_message TEXT,
        last_alerted_at TEXT,
        last_recovered_at TEXT,
        incident_acknowledged_at TEXT,
        incident_acknowledged_by TEXT
    )
    """)

    c.execute("""
    CREATE TABLE IF NOT EXISTS calendar_plan_scheduler_runs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        company_id INTEGER NOT NULL,
        source TEXT NOT NULL DEFAULT 'scheduler',
        actor_username TEXT,
        range_start TEXT,
        range_end TEXT,
        status TEXT NOT NULL DEFAULT 'running',
        reason TEXT,
        changed_days INTEGER DEFAULT 0,
        notifications_sent INTEGER DEFAULT 0,
        started_at TEXT NOT NULL,
        completed_at TEXT,
        result_json TEXT
    )
    """)

    c.execute("""
    CREATE TABLE IF NOT EXISTS calendar_scheduler_incident_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        company_id INTEGER NOT NULL,
        incident_type TEXT NOT NULL,
        event_type TEXT NOT NULL,
        actor_username TEXT,
        message TEXT,
        created_at TEXT NOT NULL
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

    c.execute("""
    CREATE TABLE IF NOT EXISTS finance_summary (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        company_id INTEGER,
        month TEXT,
        client_name TEXT,
        task_id INTEGER,
        price REAL DEFAULT 0,
        expense_total REAL DEFAULT 0,
        payroll_total REAL DEFAULT 0,
        profit REAL DEFAULT 0,
        created_at TEXT
    )
    """)


    c.execute("""
    CREATE TABLE IF NOT EXISTS payroll_payouts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        company_id INTEGER,
        worker_id INTEGER,
        month TEXT,
        amount REAL DEFAULT 0,
        status TEXT DEFAULT 'paid',
        paid_at TEXT,
        paid_by TEXT,
        note TEXT
    )
    """)

    c.execute("""
    CREATE TABLE IF NOT EXISTS automation_rules (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        company_id INTEGER,
        name TEXT,
        trigger_key TEXT,
        conditions_json TEXT,
        active INTEGER DEFAULT 1,
        created_by TEXT,
        created_at TEXT,
        updated_at TEXT
    )
    """)

    c.execute("""
    CREATE TABLE IF NOT EXISTS automation_actions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        company_id INTEGER,
        rule_id INTEGER,
        action_key TEXT,
        payload_json TEXT,
        sort_order INTEGER DEFAULT 0,
        active INTEGER DEFAULT 1,
        created_at TEXT
    )
    """)

    c.execute("""
    CREATE TABLE IF NOT EXISTS automation_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        company_id INTEGER,
        rule_id INTEGER,
        trigger_key TEXT,
        entity_type TEXT,
        entity_id INTEGER,
        status TEXT DEFAULT 'pending',
        message TEXT,
        created_at TEXT,
        processed_at TEXT
    )
    """)

    c.execute("""
    CREATE TABLE IF NOT EXISTS automation_action_runs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        company_id INTEGER NOT NULL,
        action_id INTEGER NOT NULL,
        entity_type TEXT NOT NULL,
        entity_id INTEGER NOT NULL,
        created_entity_type TEXT,
        created_entity_id INTEGER,
        created_at TEXT NOT NULL
    )
    """)

    c.execute("""
    CREATE TABLE IF NOT EXISTS autonomous_action_approvals (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        company_id INTEGER NOT NULL,
        action_queue_id INTEGER NOT NULL,
        decision TEXT NOT NULL,
        decided_by TEXT,
        reason TEXT,
        created_at TEXT NOT NULL
    )
    """)

    c.execute("""
    CREATE TABLE IF NOT EXISTS autonomous_governance_settings (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        company_id INTEGER NOT NULL,
        autonomous_enabled INTEGER NOT NULL DEFAULT 1,
        max_actions_per_cycle INTEGER NOT NULL DEFAULT 20,
        require_critical_approval INTEGER NOT NULL DEFAULT 1,
        confidence_threshold INTEGER NOT NULL DEFAULT 70,
        protected_rules_json TEXT,
        created_at TEXT NOT NULL
    )
    """)

    c.execute("""
    CREATE TABLE IF NOT EXISTS autonomous_action_queue (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        company_id INTEGER NOT NULL,
        action_type TEXT NOT NULL,
        target_type TEXT NOT NULL,
        target_id INTEGER,
        status TEXT NOT NULL DEFAULT 'pending',
        payload_json TEXT,
        created_at TEXT NOT NULL,
        processed_at TEXT
    )
    """)

    c.execute("""
    CREATE TABLE IF NOT EXISTS ops_timeline_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        company_id INTEGER NOT NULL,
        event_type TEXT NOT NULL,
        severity TEXT NOT NULL DEFAULT 'info',
        title TEXT NOT NULL,
        message TEXT NOT NULL,
        source TEXT,
        target_type TEXT,
        target_id INTEGER,
        created_at TEXT NOT NULL
    )
    """)

    c.execute("""
    CREATE TABLE IF NOT EXISTS self_healing_runs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        company_id INTEGER NOT NULL,
        retried_events INTEGER NOT NULL DEFAULT 0,
        reenabled_rules INTEGER NOT NULL DEFAULT 0,
        status TEXT NOT NULL DEFAULT 'done',
        duration_ms INTEGER NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL
    )
    """)

    c.execute("""
    CREATE TABLE IF NOT EXISTS system_health_snapshots (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        company_id INTEGER NOT NULL,
        score INTEGER NOT NULL,
        status TEXT NOT NULL,
        failed_count INTEGER NOT NULL DEFAULT 0,
        skipped_count INTEGER NOT NULL DEFAULT 0,
        disabled_rules_count INTEGER NOT NULL DEFAULT 0,
        stale_rules_count INTEGER NOT NULL DEFAULT 0,
        retry_risk_count INTEGER NOT NULL DEFAULT 0,
        unhealthy_rules_count INTEGER NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL
    )
    """)


    c.execute("""
    CREATE TABLE IF NOT EXISTS ai_assistant_notes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        company_id INTEGER,
        username TEXT,
        note TEXT,
        priority TEXT DEFAULT 'normal',
        follow_up_date TEXT,
        last_notified_at TEXT,
        notification_count INTEGER DEFAULT 0,
        is_done INTEGER DEFAULT 0,
        done_by TEXT,
        done_at TEXT,
        created_task_id INTEGER,
        created_at TEXT
    )
    """)

    c.execute("""
    CREATE TABLE IF NOT EXISTS ai_assistant_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        company_id INTEGER,
        note_id INTEGER,
        username TEXT,
        action TEXT,
        details TEXT,
        created_at TEXT
    )
    """)

    add_column_if_missing(c, "payroll_payouts", "note", "TEXT")
    add_column_if_missing(c, "ai_assistant_notes", "priority", "TEXT DEFAULT 'normal'")
    add_column_if_missing(c, "ai_assistant_notes", "follow_up_date", "TEXT")
    add_column_if_missing(c, "ai_assistant_notes", "last_notified_at", "TEXT")
    add_column_if_missing(c, "ai_assistant_notes", "notification_count", "INTEGER DEFAULT 0")
    add_column_if_missing(c, "ai_assistant_notes", "is_done", "INTEGER DEFAULT 0")
    add_column_if_missing(c, "ai_assistant_notes", "done_by", "TEXT")
    add_column_if_missing(c, "ai_assistant_notes", "done_at", "TEXT")
    add_column_if_missing(c, "ai_assistant_notes", "created_task_id", "INTEGER")

    add_column_if_missing(c, "users", "company_id", "INTEGER DEFAULT 1")
    add_column_if_missing(c, "users", "full_name", "TEXT")
    add_column_if_missing(c, "users", "position", "TEXT")
    add_column_if_missing(c, "users", "phone", "TEXT")
    add_column_if_missing(c, "users", "email", "TEXT")
    add_column_if_missing(c, "users", "telegram_chat_id", "TEXT")
    add_column_if_missing(c, "users", "commission_percent", "REAL DEFAULT 0")
    add_column_if_missing(c, "users", "is_active", "INTEGER DEFAULT 1")
    add_column_if_missing(c, "users", "disabled_at", "TEXT")
    add_column_if_missing(c, "users", "disabled_reason", "TEXT")
    add_column_if_missing(c, "users", "daily_capacity", "INTEGER DEFAULT 3")
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
    add_column_if_missing(c, "tasks", "deadline_at", "TEXT")
    add_column_if_missing(c, "tasks", "discount_amount", "REAL DEFAULT 0")
    add_column_if_missing(c, "tasks", "time_from", "TEXT")
    add_column_if_missing(c, "tasks", "time_to", "TEXT")

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
    add_column_if_missing(c, "custom_fields", "group_name", "TEXT")
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
    add_column_if_missing(c, "company_settings", "calendar_auto_publish", "INTEGER DEFAULT 0")
    add_column_if_missing(c, "company_settings", "calendar_auto_remind", "INTEGER DEFAULT 0")
    add_column_if_missing(c, "company_settings", "calendar_auto_days_ahead", "INTEGER DEFAULT 7")
    add_column_if_missing(c, "company_settings", "calendar_auto_window_start", "TEXT DEFAULT '00:00'")
    add_column_if_missing(c, "company_settings", "calendar_auto_window_end", "TEXT DEFAULT '23:59'")
    add_column_if_missing(c, "calendar_day_ack_reminders", "source", "TEXT DEFAULT 'manual'")
    add_column_if_missing(c, "calendar_plan_scheduler_status", "last_source", "TEXT DEFAULT 'scheduler'")
    add_column_if_missing(c, "calendar_plan_scheduler_status", "last_triggered_by", "TEXT")
    add_column_if_missing(c, "calendar_plan_scheduler_status", "active_incident", "TEXT DEFAULT ''")
    add_column_if_missing(c, "calendar_plan_scheduler_status", "incident_started_at", "TEXT")
    add_column_if_missing(c, "calendar_plan_scheduler_status", "incident_message", "TEXT")
    add_column_if_missing(c, "calendar_plan_scheduler_status", "last_alerted_at", "TEXT")
    add_column_if_missing(c, "calendar_plan_scheduler_status", "last_recovered_at", "TEXT")
    add_column_if_missing(c, "calendar_plan_scheduler_status", "incident_acknowledged_at", "TEXT")
    add_column_if_missing(c, "calendar_plan_scheduler_status", "incident_acknowledged_by", "TEXT")

    add_column_if_missing(c, "company_features", "company_id", "INTEGER DEFAULT 1")
    add_column_if_missing(c, "company_features", "feature_key", "TEXT")
    add_column_if_missing(c, "company_features", "enabled", "INTEGER DEFAULT 1")
    add_column_if_missing(c, "company_features", "updated_at", "TEXT")

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
    CREATE UNIQUE INDEX IF NOT EXISTS idx_company_features_company_key
    ON company_features(company_id, feature_key)
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

    default_features = [
        "tasks",
        "calendar",
        "clients",
        "catalog",
        "recurring",
        "finance",
        "payroll",
        "analytics",
        "sla",
        "archive",
        "workload",
        "notifications",
        "automation",
        "calls",
        "one_c",
        "custom_fields"
    ]

    company_rows = c.execute("SELECT id FROM companies").fetchall()
    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    for company in company_rows:
        for feature_key in default_features:
            c.execute("""
            INSERT OR IGNORE INTO company_features (
                company_id,
                feature_key,
                enabled,
                updated_at
            )
            VALUES (?, ?, ?, ?)
            """, (
                company["id"],
                feature_key,
                1,
                now
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

    c.execute("""
    CREATE UNIQUE INDEX IF NOT EXISTS idx_payroll_payouts_company_worker_month
    ON payroll_payouts(company_id, worker_id, month)
    """)

    c.execute("""
    CREATE INDEX IF NOT EXISTS idx_automation_rules_company_active
    ON automation_rules(company_id, active)
    """)

    c.execute("""
    CREATE INDEX IF NOT EXISTS idx_automation_actions_rule
    ON automation_actions(rule_id, sort_order)
    """)

    c.execute("""
    CREATE INDEX IF NOT EXISTS idx_automation_events_company_status
    ON automation_events(company_id, status, created_at)
    """)

    c.execute("""
    CREATE UNIQUE INDEX IF NOT EXISTS idx_automation_action_runs_source
    ON automation_action_runs(company_id, action_id, entity_type, entity_id)
    """)

    c.execute("""
    CREATE INDEX IF NOT EXISTS idx_system_health_snapshots_company_created
    ON system_health_snapshots(company_id, created_at)
    """)


    c.execute("""
    CREATE INDEX IF NOT EXISTS idx_ops_timeline_events_company_created
    ON ops_timeline_events(company_id, created_at)
    """)


    c.execute("""
    CREATE INDEX IF NOT EXISTS idx_autonomous_action_queue_company_status
    ON autonomous_action_queue(company_id, status, created_at)
    """)


    c.execute("""
    CREATE INDEX IF NOT EXISTS idx_autonomous_governance_company
    ON autonomous_governance_settings(company_id)
    """)


    c.execute("""
    CREATE INDEX IF NOT EXISTS idx_autonomous_action_approvals_company
    ON autonomous_action_approvals(company_id, action_queue_id)
    """)

    c.execute("""
    CREATE INDEX IF NOT EXISTS idx_ai_assistant_notes_company_created
    ON ai_assistant_notes(company_id, created_at)
    """)

    c.execute("""
    CREATE INDEX IF NOT EXISTS idx_ai_assistant_events_company_created
    ON ai_assistant_events(company_id, created_at)
    """)

    c.execute("""
    CREATE INDEX IF NOT EXISTS idx_team_activity_company_user_created
    ON team_activity(company_id, user_id, created_at)
    """)

    c.execute("""
    CREATE INDEX IF NOT EXISTS idx_worker_unavailability_company_worker_dates
    ON worker_unavailability(company_id, worker_id, date_from, date_to)
    """)

    c.execute("""
    CREATE INDEX IF NOT EXISTS idx_worker_unavailability_company_dates
    ON worker_unavailability(company_id, date_from, date_to)
    """)

    c.execute("""
    CREATE UNIQUE INDEX IF NOT EXISTS idx_calendar_day_publication_company_date
    ON calendar_day_publications(company_id, plan_date)
    """)

    c.execute("""
    CREATE UNIQUE INDEX IF NOT EXISTS idx_calendar_day_ack_unique
    ON calendar_day_acknowledgements(
        company_id, plan_date, revision, username
    )
    """)

    c.execute("""
    CREATE INDEX IF NOT EXISTS idx_calendar_day_ack_company_date
    ON calendar_day_acknowledgements(company_id, plan_date, revision)
    """)

    c.execute("""
    CREATE INDEX IF NOT EXISTS idx_calendar_day_ack_reminder_lookup
    ON calendar_day_ack_reminders(
        company_id, plan_date, revision, username, reminded_at
    )
    """)

    c.execute("""
    DROP INDEX IF EXISTS idx_calendar_day_ack_scheduler_unique
    """)

    c.execute("""
    CREATE UNIQUE INDEX IF NOT EXISTS idx_calendar_day_ack_automation_unique
    ON calendar_day_ack_reminders(
        company_id, plan_date, revision, username
    )
    WHERE source IN ('scheduler', 'manual_run')
    """)

    c.execute("""
    CREATE INDEX IF NOT EXISTS idx_calendar_plan_runs_company_week
    ON calendar_plan_operation_runs(company_id, week_start, created_at)
    """)

    c.execute("""
    CREATE INDEX IF NOT EXISTS idx_calendar_scheduler_runs_company_started
    ON calendar_plan_scheduler_runs(company_id, started_at, id)
    """)

    c.execute("""
    CREATE INDEX IF NOT EXISTS idx_calendar_incidents_company_created
    ON calendar_scheduler_incident_events(company_id, created_at, id)
    """)

    c.execute("""
    CREATE INDEX IF NOT EXISTS idx_calendar_incidents_created
    ON calendar_scheduler_incident_events(created_at, id)
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
