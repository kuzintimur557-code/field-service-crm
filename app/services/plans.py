"""Subscription plan definitions and plan helpers."""

from app.database import connect
from app.services.common import (
    get_company_settings,
    require_company_id_value,
)

PLAN_DEFINITIONS = {
    "basic": {
        "label": "Базовый",
        "settings_label": "Базовый — без 1С",
        "user_limit": 3,
        "monthly_price": 0,
        "one_c_enabled": 0,
        "calls_enabled": 0,
        "ai_calls_enabled": 0,
    },
    "team": {
        "label": "Команда",
        "settings_label": "Команда — звонки без 1С",
        "user_limit": 10,
        "monthly_price": 2990,
        "one_c_enabled": 0,
        "calls_enabled": 1,
        "ai_calls_enabled": 0,
    },
    "business": {
        "label": "Бизнес",
        "settings_label": "Бизнес — звонки без 1С",
        "user_limit": 30,
        "monthly_price": 7990,
        "one_c_enabled": 0,
        "calls_enabled": 1,
        "ai_calls_enabled": 0,
    },
    "business_1c": {
        "label": "Бизнес + 1С",
        "settings_label": "Бизнес + 1С",
        "user_limit": 30,
        "monthly_price": 11990,
        "one_c_enabled": 1,
        "calls_enabled": 1,
        "ai_calls_enabled": 0,
    },
    "enterprise_1c": {
        "label": "Корпоративный + 1С",
        "settings_label": "Корпоративный + 1С + ИИ-звонки",
        "user_limit": None,
        "monthly_price": 0,
        "one_c_enabled": 1,
        "calls_enabled": 1,
        "ai_calls_enabled": 1,
    },
}

def normalize_plan(plan):
    normalized_plan = str(plan or "basic").strip()
    return normalized_plan if normalized_plan in PLAN_DEFINITIONS else "basic"


def get_plan_label(plan):
    return PLAN_DEFINITIONS[normalize_plan(plan)]["label"]


def get_plan_options():
    return [
        (plan_key, definition["settings_label"])
        for plan_key, definition in PLAN_DEFINITIONS.items()
    ]


def get_plan_user_limit(plan):
    return PLAN_DEFINITIONS[normalize_plan(plan)]["user_limit"]


def get_plan_monthly_price(plan):
    return float(PLAN_DEFINITIONS[normalize_plan(plan)]["monthly_price"] or 0)


def get_plan_price_label(plan):
    price = get_plan_monthly_price(plan)

    if normalize_plan(plan) == "enterprise_1c" and price <= 0:
        return "по договорённости"

    return f"{format_rub_amount(price)} / месяц"


def plan_allows_active_users(plan, active_users_count):
    user_limit = get_plan_user_limit(plan)

    if user_limit is None:
        return True

    return int(active_users_count or 0) <= int(user_limit)


def get_plan_feature_flags(plan):
    definition = PLAN_DEFINITIONS[normalize_plan(plan)]
    return {
        "one_c_enabled": definition["one_c_enabled"],
        "calls_enabled": definition["calls_enabled"],
        "ai_calls_enabled": definition["ai_calls_enabled"],
    }

def format_rub_amount(amount):
    value = round(float(amount or 0), 2)

    if value.is_integer():
        return f"{int(value)} ₽"

    return f"{value:.2f} ₽"


def get_user_limit_status(active_users_count, user_limit):
    active_users_count = int(active_users_count or 0)

    if user_limit is None:
        return {
            "label": "Без лимита",
            "tone": "ok",
            "remaining": None,
        }

    user_limit = int(user_limit or 0)

    if active_users_count > user_limit:
        return {
            "label": f"Превышен лимит на {active_users_count - user_limit}",
            "tone": "danger",
            "remaining": 0,
        }

    if active_users_count == user_limit:
        return {
            "label": "Лимит заполнен",
            "tone": "warning",
            "remaining": 0,
        }

    return {
        "label": f"Осталось мест: {user_limit - active_users_count}",
        "tone": "ok",
        "remaining": user_limit - active_users_count,
    }


def get_company_user_limit_usage(company_id, settings=None):
    company_id = require_company_id_value(company_id)
    settings = settings or get_company_settings(company_id)
    plan = normalize_plan(
        settings["plan"] if settings and "plan" in settings.keys() else "basic"
    )
    user_limit = get_plan_user_limit(plan)

    conn = connect()
    c = conn.cursor()
    row = c.execute("""
    SELECT
        COUNT(*) AS users_count,
        SUM(CASE WHEN COALESCE(is_active, 1)=1 THEN 1 ELSE 0 END)
            AS active_users_count
    FROM users
    WHERE company_id=?
      AND role!='superadmin'
    """, (company_id,)).fetchone()
    conn.close()

    users_count = int(row["users_count"] or 0) if row else 0
    active_users_count = (
        int(row["active_users_count"] or 0) if row else 0
    )
    status = get_user_limit_status(active_users_count, user_limit)

    return {
        "plan": plan,
        "plan_label": get_plan_label(plan),
        "user_limit": user_limit,
        "user_limit_label": str(user_limit) if user_limit else "без лимита",
        "users_count": users_count,
        "active_users_count": active_users_count,
        "status": status["label"],
        "tone": status["tone"],
        "remaining": status["remaining"],
    }


def get_recommended_user_limit_plan(plan, active_users_count):
    current_plan = normalize_plan(plan)
    active_users_count = int(active_users_count or 0)
    plan_keys = list(PLAN_DEFINITIONS.keys())
    start_index = plan_keys.index(current_plan) + 1

    for plan_key in plan_keys[start_index:]:
        definition = PLAN_DEFINITIONS[plan_key]
        user_limit = definition["user_limit"]

        if user_limit is None or active_users_count < int(user_limit):
            return {
                "plan": plan_key,
                "label": definition["label"],
                "settings_label": definition["settings_label"],
                "user_limit": user_limit,
                "user_limit_label": (
                    str(user_limit) if user_limit else "без лимита"
                ),
                "available_slots": (
                    None if user_limit is None
                    else max(int(user_limit) - active_users_count, 0)
                ),
            }

    return None
