"""Subscription plan definitions and plan helpers."""

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
