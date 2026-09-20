#!/usr/bin/env python3
"""Verify a live production deployment without credentials or data changes."""

import argparse
import json
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen


class DeploymentCheckError(RuntimeError):
    pass


def normalize_base_url(value, allow_http=False):
    base_url = str(value or "").strip().rstrip("/")
    parsed = urlsplit(base_url)
    allowed_schemes = {"https"}
    if allow_http:
        allowed_schemes.add("http")
    if (
        parsed.scheme.lower() not in allowed_schemes
        or not parsed.netloc
        or parsed.username
        or parsed.password
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
    ):
        raise DeploymentCheckError("invalid deployment base URL")
    return base_url


def request_url(base_url, path, method="GET", headers=None, timeout=10):
    request = Request(
        f"{base_url}{path}",
        data=b"" if method != "GET" else None,
        headers={
            "Accept": "application/json",
            "User-Agent": "field-service-release-check/1",
            **(headers or {}),
        },
        method=method,
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            body = response.read()
            return response.status, response.headers, body
    except HTTPError as error:
        return error.code, error.headers, error.read()
    except (OSError, URLError) as error:
        raise DeploymentCheckError(
            f"request failed for {path}: {error.__class__.__name__}"
        ) from error


def parse_json_response(path, status, body):
    try:
        payload = json.loads(body.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as error:
        raise DeploymentCheckError(
            f"{path} did not return valid JSON"
        ) from error
    if not isinstance(payload, dict):
        raise DeploymentCheckError(f"{path} returned a non-object payload")
    if status != 200 or payload.get("ok") is not True:
        raise DeploymentCheckError(f"{path} is not ready (HTTP {status})")
    return payload


def require_security_headers(headers):
    required = {
        "cache-control": "no-store",
        "content-security-policy": "frame-ancestors 'none'",
        "x-content-type-options": "nosniff",
        "x-frame-options": "DENY",
    }
    for name, expected in required.items():
        value = str(headers.get(name, "") or "")
        if expected.lower() not in value.lower():
            raise DeploymentCheckError(
                f"missing or invalid response header: {name}"
            )


def check_deployment(
    base_url,
    expected_commit="",
    expected_database_backend="",
    timeout=10,
    allow_http=False,
):
    base_url = normalize_base_url(base_url, allow_http=allow_http)

    health_status, health_headers, health_body = request_url(
        base_url,
        "/health",
        timeout=timeout,
    )
    health = parse_json_response("/health", health_status, health_body)
    require_security_headers(health_headers)

    ready_status, _, ready_body = request_url(
        base_url,
        "/ready",
        timeout=timeout,
    )
    readiness = parse_json_response("/ready", ready_status, ready_body)

    observed_commit = str(
        (health.get("build") or {}).get("commit") or ""
    ).strip().lower()
    expected_commit = str(expected_commit or "").strip().lower()
    if expected_commit and observed_commit != expected_commit[:12]:
        raise DeploymentCheckError(
            "live commit does not match the deployment commit"
        )

    database_backend = str(
        (health.get("database") or {}).get("backend") or ""
    ).strip().lower()
    expected_database_backend = str(
        expected_database_backend or ""
    ).strip().lower()
    if (
        expected_database_backend
        and database_backend != expected_database_backend
    ):
        raise DeploymentCheckError(
            "live database backend does not match the release requirement"
        )

    closed_paths = {}
    for path in ("/docs", "/redoc", "/openapi.json"):
        status, _, _ = request_url(base_url, path, timeout=timeout)
        closed_paths[path] = status
        if status != 404:
            raise DeploymentCheckError(
                f"production endpoint {path} is exposed (HTTP {status})"
            )

    csrf_status, _, csrf_body = request_url(
        base_url,
        "/login",
        method="POST",
        headers={
            "Origin": "https://release-check.invalid",
            "Sec-Fetch-Site": "cross-site",
        },
        timeout=timeout,
    )
    if csrf_status != 403:
        raise DeploymentCheckError(
            f"cross-site POST was not blocked (HTTP {csrf_status})"
        )
    try:
        csrf_payload = json.loads(csrf_body.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as error:
        raise DeploymentCheckError(
            "cross-site rejection did not return JSON"
        ) from error
    if csrf_payload.get("error") not in {
        "cross_site_request_blocked",
        "origin_not_allowed",
    }:
        raise DeploymentCheckError("unexpected cross-site rejection payload")

    return {
        "ok": True,
        "base_url": base_url,
        "app": health.get("app"),
        "version": health.get("version"),
        "commit": observed_commit,
        "database_backend": database_backend,
        "readiness_checks": len(readiness.get("checks") or []),
        "closed_paths": closed_paths,
        "cross_site_post_status": csrf_status,
    }


def parse_args():
    parser = argparse.ArgumentParser(
        description="Check a live Field Service CRM production deployment.",
    )
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--expected-commit", default="")
    parser.add_argument("--expected-database-backend", default="")
    parser.add_argument("--attempts", type=int, default=1)
    parser.add_argument("--interval", type=float, default=10)
    parser.add_argument("--timeout", type=float, default=10)
    parser.add_argument(
        "--allow-http",
        action="store_true",
        help="Allow HTTP for local smoke tests only.",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    attempts = max(1, min(60, args.attempts))
    interval = max(0, min(60, args.interval))
    last_error = None

    for attempt in range(1, attempts + 1):
        try:
            result = check_deployment(
                args.base_url,
                expected_commit=args.expected_commit,
                expected_database_backend=args.expected_database_backend,
                timeout=max(1, min(60, args.timeout)),
                allow_http=args.allow_http,
            )
            result["attempt"] = attempt
            print(json.dumps(result, ensure_ascii=False, sort_keys=True))
            return 0
        except DeploymentCheckError as error:
            last_error = error
            if attempt < attempts:
                time.sleep(interval)

    print(json.dumps({
        "ok": False,
        "error": str(last_error or "deployment check failed"),
        "attempts": attempts,
    }, ensure_ascii=False, sort_keys=True))
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
