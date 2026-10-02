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

_SUBSCRIPTION_STATUS_CACHE = {}
_SUBSCRIPTION_STATUS_CACHE_TTL_SECONDS = 60


def invalidate_company_subscription_cache(company_id=None):
    if company_id is None:
        _SUBSCRIPTION_STATUS_CACHE.clear()
    else:
        _SUBSCRIPTION_STATUS_CACHE.pop(int(company_id), None)


def get_company_subscription_fast(company_id, now=None):
    company_id = int(company_id)
    now = now or datetime.now()
    cached = _SUBSCRIPTION_STATUS_CACHE.get(company_id)

    if (
        cached
        and (now - cached[0]).total_seconds()
        < _SUBSCRIPTION_STATUS_CACHE_TTL_SECONDS
    ):
        return cached[1]

    subscription = get_company_subscription(company_id)
    _SUBSCRIPTION_STATUS_CACHE[company_id] = (now, subscription)
    return subscription


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


def get_company_subscription_reminders(company_id, now=None):
    now = now or datetime.now()
    subscription = get_company_subscription(company_id)

    if not subscription["is_open"]:
        if subscription["status"] == SUBSCRIPTION_PAST_DUE:
            return [{
                "title": "Подписка просрочена",
                "message": "Продлите подписку, чтобы сохранить доступ к платформе.",
                "link": "/billing",
            }]
        return []

    if subscription["status"] != SUBSCRIPTION_TRIAL:
        return []

    days_left = subscription["days_left"]
    if days_left is None or days_left not in (7, 3, 1, 0):
        return []

    if days_left == 0:
        return [{
            "title": "Пробный период закончился",
            "message": (
                "Сегодня завершается пробный период. "
                "Выберите тариф и продлите доступ на странице оплаты."
            ),
            "link": "/billing",
        }]

    return [{
        "title": "Пробный период заканчивается",
        "message": (
            f"Осталось дней: {days_left}. "
            "Выберите тариф на странице оплаты, чтобы продолжить работу."
        ),
        "link": "/billing",
    }]


def send_company_subscription_reminders(company_id, now=None):
    now = now or datetime.now()
    today = now.strftime("%Y-%m-%d")
    reminders = get_company_subscription_reminders(company_id, now)

    if not reminders:
        return []

    conn = connect()
    c = conn.cursor()
    owners = c.execute("""
    SELECT username
    FROM users
    WHERE company_id=? AND role='boss' AND COALESCE(is_active, 1)=1
    """, (company_id,)).fetchall()
    conn.close()

    sent = []

    for reminder in reminders:
        for owner in owners:
            username = owner["username"]

            conn = connect()
            c = conn.cursor()
            already = c.execute("""
            SELECT id
            FROM notifications
            WHERE company_id=? AND username=?
              AND title=? AND COALESCE(created_at, '') LIKE ?
            LIMIT 1
            """, (
                company_id,
                username,
                reminder["title"],
                f"{today}%",
            )).fetchone()
            conn.close()

            if already:
                continue

            _create_notification(
                company_id,
                username,
                reminder["title"],
                reminder["message"],
                reminder["link"],
            )
            sent.append({
                "username": username,
                "title": reminder["title"],
            })

    return sent


def run_subscription_reminders(now=None):
    now = now or datetime.now()
    conn = connect()
    c = conn.cursor()
    companies = c.execute("""
    SELECT DISTINCT company_id
    FROM company_settings
    WHERE company_id IS NOT NULL
    ORDER BY company_id
    """).fetchall()
    conn.close()

    summary = {"companies": 0, "sent": 0}

    for company in companies:
        company_id = company["company_id"]
        if not company_id:
            continue
        summary["companies"] += 1
        sent = send_company_subscription_reminders(company_id, now)
        summary["sent"] += len(sent)

    return summary


def _create_notification(company_id, username, title, message, link):
    conn = connect()

    try:
        c = conn.cursor()
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
            link,
            datetime.now().strftime("%Y-%m-%d %H:%M"),
        ))
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
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

    invalidate_company_subscription_cache(company_id)
    return get_company_subscription(company_id)
