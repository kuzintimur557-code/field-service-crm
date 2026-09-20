import json
import sys
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.check_deployment import (  # noqa: E402
    DeploymentCheckError,
    check_deployment,
    normalize_base_url,
)


COMMIT = "1234567890abcdef"
SECURITY_HEADERS = {
    "cache-control": "no-store",
    "content-security-policy": (
        "default-src 'self'; frame-ancestors 'none'"
    ),
    "x-content-type-options": "nosniff",
    "x-frame-options": "DENY",
}


def json_response(status, payload, headers=None):
    return (
        status,
        headers or {},
        json.dumps(payload).encode("utf-8"),
    )


def release_response(_base_url, path, method="GET", **_kwargs):
    if path == "/health":
        return json_response(200, {
            "ok": True,
            "app": "field-service-crm",
            "version": "test",
            "build": {"commit": COMMIT[:12]},
            "database": {"backend": "postgresql"},
        }, SECURITY_HEADERS)
    if path == "/ready":
        return json_response(200, {
            "ok": True,
            "checks": [{"key": "database"}],
        })
    if path in {"/docs", "/redoc", "/openapi.json"}:
        return json_response(404, {"detail": "Not Found"})
    if path == "/login" and method == "POST":
        return json_response(403, {
            "ok": False,
            "error": "cross_site_request_blocked",
        })
    raise AssertionError(f"Unexpected release check request: {method} {path}")


def main():
    with patch(
        "scripts.check_deployment.request_url",
        side_effect=release_response,
    ):
        result = check_deployment(
            "https://crm.example",
            expected_commit=COMMIT,
            expected_database_backend="postgresql",
        )
        assert result["ok"] is True
        assert result["commit"] == COMMIT[:12]
        assert result["database_backend"] == "postgresql"
        assert result["cross_site_post_status"] == 403
        assert set(result["closed_paths"]) == {
            "/docs",
            "/redoc",
            "/openapi.json",
        }

        try:
            check_deployment(
                "https://crm.example",
                expected_commit="f" * 40,
            )
        except DeploymentCheckError as error:
            assert "commit" in str(error)
        else:
            raise AssertionError("Mismatched release commit was accepted")

        try:
            check_deployment(
                "https://crm.example",
                expected_database_backend="sqlite",
            )
        except DeploymentCheckError as error:
            assert "database backend" in str(error)
        else:
            raise AssertionError("Unexpected production database was accepted")

    try:
        normalize_base_url("http://crm.example")
    except DeploymentCheckError:
        pass
    else:
        raise AssertionError("Plain HTTP production URL was accepted")

    assert normalize_base_url(
        "http://127.0.0.1:8011",
        allow_http=True,
    ) == "http://127.0.0.1:8011"

    print(
        "Release smoke passed: health, readiness, commit, closed docs, "
        "security headers and cross-site protection."
    )


if __name__ == "__main__":
    main()
