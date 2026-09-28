from datetime import datetime, timedelta

from app.database import add_column_if_missing, connect

TRIAL_DAYS = 14
SUBSCRIPTION_ACTIVE_DAYS = 30

SUBSCRIPTION_TRIAL = "trial"
SUBSCRIPTION_ACTIVE = "active"
SUBSCRIPTION_PAST_DUE = "past_due"
SUBSCRIPTION_CANCELED = "canceled"
SUBSCRIPTION_STATUSES = {
    SUBSCRIPTION_TRIAL,
    SUBSCRIPTION_ACTIVE,
    SUBSCRIPTION_PAST_DUE,
    SUBSCRIPTION_CANCELED,
}

DATE_FORMAT = "%Y-%m-%d"


def normalize_subscription_status(status):
    status = str(status or "").strip()
    return status if status in SUBSCRIPTION_STATUSES else SUBSCRIPTION_TRIAL


def _today():
    return datetime.now()


def _parse_date(value):
    try:
        return datetime.strptime(str(value or "")[:10], DATE_FORMAT)
    except ValueError:
        return None


def ensure_company_subscription(company_id):
    conn = connect()

    try:
        c = conn.cursor()
        add_column_if_missing(c, "company_settings", "subscription_status", "TEXT")
        add_column_if_missing(c, "company_settings", "trial_ends_at", "TEXT")
        add_column_if_missing(
            c, "company_settings", "subscription_ends_at", "TEXT"
        )

        c.execute("""
        INSERT OR IGNORE INTO company_settings (company_id, plan, updated_at)
        VALUES (?, 'basic', '')
        """, (company_id,))

        row = c.execute("""
        SELECT subscription_status, trial_ends_at, subscription_ends_at
        FROM company_settings
        WHERE company_id=?
        """, (company_id,)).fetchone()

        status = str(row["subscription_status"] or "").strip() if row else ""

        if not status:
            trial_ends = (_today() + timedelta(days=TRIAL_DAYS)).strftime(
                DATE_FORMAT
            )
            c.execute("""
            UPDATE company_settings
            SET subscription_status=?,
                trial_ends_at=?
            WHERE company_id=?
            """, (SUBSCRIPTION_TRIAL, trial_ends, company_id))
            conn.commit()
            status = SUBSCRIPTION_TRIAL
            trial_ends_at = trial_ends
            subscription_ends_at = ""
        else:
            trial_ends_at = row["trial_ends_at"] or ""
            subscription_ends_at = row["subscription_ends_at"] or ""

        return get_company_subscription(company_id, _connection=conn)
    finally:
        conn.close()


def get_company_subscription(company_id, _connection=None):
    conn = _connection or connect()
    own_connection = _connection is None

    try:
        c = conn.cursor()
        add_column_if_missing(c, "company_settings", "subscription_status", "TEXT")
        add_column_if_missing(c, "company_settings", "trial_ends_at", "TEXT")
        add_column_if_missing(
            c, "company_settings", "subscription_ends_at", "TEXT"
        )

        c.execute("""
        INSERT OR IGNORE INTO company_settings (company_id, plan, updated_at)
        VALUES (?, 'basic', '')
        """, (company_id,))

        row = c.execute("""
        SELECT subscription_status, trial_ends_at, subscription_ends_at
        FROM company_settings
        WHERE company_id=?
        """, (company_id,)).fetchone()

        if row is None:
            return {
                "status": SUBSCRIPTION_TRIAL,
                "trial_ends_at": "",
                "subscription_ends_at": "",
                "is_open": True,
                "days_left": None,
                "label": "Пробный период",
            }

        status = normalize_subscription_status(row["subscription_status"])
        trial_ends_at = row["trial_ends_at"] or ""
        subscription_ends_at = row["subscription_ends_at"] or ""

        days_left = None
        is_open = status in (SUBSCRIPTION_TRIAL, SUBSCRIPTION_ACTIVE)

        if status == SUBSCRIPTION_TRIAL and trial_ends_at:
            trial_end = _parse_date(trial_ends_at)
            if trial_end:
                days_left = (trial_end - _today()).days + 1
                if days_left < 0:
                    days_left = 0
                    is_open = False

        labels = {
            SUBSCRIPTION_TRIAL: "Пробный период",
            SUBSCRIPTION_ACTIVE: "Активна",
            SUBSCRIPTION_PAST_DUE: "Просрочена",
            SUBSCRIPTION_CANCELED: "Отменена",
        }

        return {
            "status": status,
            "trial_ends_at": trial_ends_at,
            "subscription_ends_at": subscription_ends_at,
            "is_open": is_open,
            "days_left": days_left,
            "label": labels[status],
        }
    finally:
        if own_connection:
            conn.close()


def activate_company_subscription(company_id, days=SUBSCRIPTION_ACTIVE_DAYS):
    days = max(1, int(days or SUBSCRIPTION_ACTIVE_DAYS))
    ends_at = (_today() + timedelta(days=days)).strftime(DATE_FORMAT)

    conn = connect()

    try:
        c = conn.cursor()
        add_column_if_missing(c, "company_settings", "subscription_status", "TEXT")
        add_column_if_missing(c, "company_settings", "trial_ends_at", "TEXT")
        add_column_if_missing(
            c, "company_settings", "subscription_ends_at", "TEXT"
        )

        c.execute("""
        UPDATE company_settings
        SET subscription_status=?,
            subscription_ends_at=?
        WHERE company_id=?
        """, (SUBSCRIPTION_ACTIVE, ends_at, company_id))
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    return get_company_subscription(company_id)
