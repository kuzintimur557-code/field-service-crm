"""Production web-security configuration and request guards."""

import os
from urllib.parse import urlsplit


SAFE_HTTP_METHODS = {"GET", "HEAD", "OPTIONS", "TRACE"}


class SecurityConfigurationError(RuntimeError):
    pass


def _environment_int(name, default, minimum, maximum):
    try:
        value = int(str(os.getenv(name) or default).strip())
    except (TypeError, ValueError):
        value = default
    return max(minimum, min(maximum, value))


def _split_values(value):
    return [
        item.strip()
        for item in str(value or "").split(",")
        if item.strip()
    ]


def _hostname_from_url(value):
    text = str(value or "").strip()
    if not text:
        return ""
    parsed = urlsplit(text if "://" in text else f"//{text}")
    return str(parsed.hostname or "").strip().lower()


def _normalized_origin(value):
    text = str(value or "").strip()
    if not text:
        return ""
    try:
        parsed = urlsplit(text)
    except ValueError:
        return ""
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return ""
    if parsed.username or parsed.password or parsed.path not in {"", "/"}:
        return ""
    if parsed.query or parsed.fragment:
        return ""
    return f"{parsed.scheme.lower()}://{parsed.netloc.lower()}"


def get_security_runtime_config():
    production_mode = bool(
        str(os.getenv("ENV") or "").strip().lower() == "production"
        or str(os.getenv("RAILWAY_ENVIRONMENT") or "").strip()
    )
    cookie_secure = bool(
        str(os.getenv("COOKIE_SECURE") or "").strip().lower()
        in {"1", "true", "yes", "on"}
        or str(os.getenv("RAILWAY_ENVIRONMENT") or "").strip()
    )
    trusted_hosts = _split_values(os.getenv("TRUSTED_HOSTS"))
    for source in (
        os.getenv("APP_BASE_URL"),
        os.getenv("RAILWAY_PUBLIC_DOMAIN"),
        os.getenv("RAILWAY_STATIC_URL"),
    ):
        host = _hostname_from_url(source)
        if host and host not in trusted_hosts:
            trusted_hosts.append(host)

    csrf_trusted_origins = []
    for value in (
        _split_values(os.getenv("CSRF_TRUSTED_ORIGINS"))
        + [str(os.getenv("APP_BASE_URL") or "")]
    ):
        normalized = _normalized_origin(value)
        if normalized and normalized not in csrf_trusted_origins:
            csrf_trusted_origins.append(normalized)

    errors = []
    if production_mode and not trusted_hosts:
        errors.append("trusted_hosts_required")
    if any(
        "://" in host or "/" in host or not host
        for host in trusted_hosts
    ):
        errors.append("invalid_trusted_host")
    if production_mode and len(str(os.getenv("SECRET_KEY") or "")) < 32:
        errors.append("strong_secret_key_required")
    if production_mode and not cookie_secure:
        errors.append("secure_cookie_required")

    return {
        "production_mode": production_mode,
        "docs_enabled": not production_mode,
        "cookie_secure": cookie_secure,
        "trusted_hosts": trusted_hosts,
        "trusted_hosts_configured": bool(trusted_hosts),
        "csrf_trusted_origins": csrf_trusted_origins,
        "csrf_origin_guard_enabled": True,
        "max_request_bytes": _environment_int(
            "MAX_REQUEST_BYTES",
            60 * 1024 * 1024,
            1024 * 1024,
            1024 * 1024 * 1024,
        ),
        "configuration_valid": not errors,
        "errors": errors,
    }


def require_valid_production_security(config=None):
    config = config or get_security_runtime_config()
    if config["production_mode"] and not config["configuration_valid"]:
        raise SecurityConfigurationError(
            "Production security configuration is invalid: "
            + ", ".join(config["errors"])
        )
    return config


def _header_value(headers, name):
    try:
        return str(headers.get(name, "") or "").strip()
    except Exception:
        return ""


def _same_host(origin, host):
    normalized = _normalized_origin(origin)
    if not normalized:
        return False
    try:
        origin_host = urlsplit(normalized).netloc.lower()
    except ValueError:
        return False
    return bool(host) and origin_host == str(host).strip().lower()


def get_cross_site_request_error(
    method,
    headers,
    trusted_origins=None,
):
    """Return a safe error code for a cross-site state-changing request."""
    if str(method or "GET").upper() in SAFE_HTTP_METHODS:
        return ""

    fetch_site = _header_value(headers, "sec-fetch-site").lower()
    if fetch_site == "cross-site":
        return "cross_site_request_blocked"

    host = _header_value(headers, "host")
    allowed_origins = {
        normalized
        for normalized in (
            _normalized_origin(item) for item in (trusted_origins or [])
        )
        if normalized
    }
    origin = _header_value(headers, "origin")
    if origin:
        normalized_origin = _normalized_origin(origin)
        if (
            normalized_origin not in allowed_origins
            and not _same_host(origin, host)
        ):
            return "origin_not_allowed"
        return ""

    referer = _header_value(headers, "referer")
    if referer:
        parsed = urlsplit(referer)
        referer_origin = (
            f"{parsed.scheme.lower()}://{parsed.netloc.lower()}"
            if parsed.scheme in {"http", "https"} and parsed.netloc
            else ""
        )
        if (
            referer_origin not in allowed_origins
            and not _same_host(referer_origin, host)
        ):
            return "referer_not_allowed"
    return ""


def get_request_size_error(headers, maximum_bytes):
    value = _header_value(headers, "content-length")
    if not value:
        return ""
    try:
        size = int(value)
    except ValueError:
        return "invalid_content_length"
    if size < 0:
        return "invalid_content_length"
    if size > int(maximum_bytes):
        return "request_too_large"
    return ""
