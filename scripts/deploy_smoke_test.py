#!/usr/bin/env python3
import json
import os
import sys
import urllib.error
import urllib.request


def _request(url: str, *, method: str = "GET", headers: dict | None = None, payload: dict | None = None):
    data = None
    request_headers = dict(headers or {})
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        request_headers["Content-Type"] = "application/json"

    request = urllib.request.Request(url, data=data, headers=request_headers, method=method)
    with urllib.request.urlopen(request, timeout=30) as response:
        body = response.read().decode("utf-8") if response.length != 0 else ""
        return response.status, body


def main() -> int:
    base_url = os.environ.get("SMOKE_TEST_BASE_URL", "").rstrip("/")
    if not base_url:
        print("SMOKE_TEST_BASE_URL is required", file=sys.stderr)
        return 1

    require_auth = os.environ.get("SMOKE_TEST_REQUIRE_AUTH", "false").lower() in {"1", "true", "yes"}

    checks = [
        f"{base_url}/api/v1/health/live",
        f"{base_url}/api/v1/health/ready",
        f"{base_url}/api/v1/health/version",
    ]

    try:
        for url in checks:
            status, _ = _request(url)
            if status >= 400:
                raise RuntimeError(f"Smoke check failed for {url} with status {status}")

        email = os.environ.get("SMOKE_TEST_EMAIL")
        password = os.environ.get("SMOKE_TEST_PASSWORD")
        if require_auth and (not email or not password):
            raise RuntimeError(
                "Authenticated smoke test is required but SMOKE_TEST_EMAIL/SMOKE_TEST_PASSWORD are not set"
            )

        if require_auth:
            _, login_body = _request(
                f"{base_url}/api/v1/auth/login",
                method="POST",
                payload={"email": email, "password": password},
            )
            token = json.loads(login_body)["access_token"]
            _request(
                f"{base_url}/api/v1/users/me/settings",
                headers={"Authorization": f"Bearer {token}"},
            )
            print("Smoke test passed: health + authenticated flow")
        elif email and password:
            print("Smoke test passed: health checks only (auth credentials supplied but auth flow skipped)")
        else:
            print("Smoke test passed: health checks only (auth flow skipped)")
        return 0
    except (urllib.error.URLError, KeyError, RuntimeError, json.JSONDecodeError) as exc:
        print(f"Smoke test failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

